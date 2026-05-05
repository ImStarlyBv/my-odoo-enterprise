import base64
import json
import re
from datetime import date
from io import BytesIO

import requests

from odoo import models, fields, api, _
from odoo.exceptions import UserError

# Mapeo forma de pago del diario → código DGII
PAYMENT_FORM_TO_DGII_CODE = {
    'cash': '1',
    'bank': '2',
    'card': '3',
    'credit': '4',
    'bond': '5',
    'swap': '6',
    'others': '8',
}

# Mapeo tasa ITBIS → código DGII
ITBIS_CODE_MAP = {
    18.0: 'ITBIS1',
    16.0: 'ITBIS2',
    9.0:  'ITBIS3',
    8.0:  'ITBIS4',
    0.0:  'EXENTO',
}


def _is_retention_tax(tax):
    return float(tax.amount or 0.0) < 0


def _is_itbis_tax(tax):
    return 'ITBIS' in (tax.name or '').upper()


def _is_isr_tax(tax):
    name_upper = (tax.name or '').upper()
    return any(k in name_upper for k in ('ISR', 'RENTA', 'RETENCION', 'RETENCI'))


class AccountMove(models.Model):
    _inherit = 'account.move'

    # =========================================================================
    # ESTADO ECF
    # =========================================================================

    ecf_validation_status = fields.Selection(
        selection=[
            ('pending', 'Pendiente'),
            ('success', 'Validado'),
            ('error', 'Error'),
            ('3', 'En Proceso'),
            ('4', 'Aceptado Condicional'),
            ('rfce', 'RFCE (sin DGII)'),
            ('skipped', 'No enviado (deshabilitado)'),
        ],
        string='Estado e-CF',
        default='pending',
        store=True,
        copy=False,
    )
    ecf_api_message = fields.Text(
        string='Mensaje API DGII',
        copy=False,
    )
    ecf_track_id = fields.Char(
        string='Track ID (DGII)',
        readonly=True,
        store=True,
        copy=False,
    )
    ecf_qr_url = fields.Char(
        string='URL QR e-CF',
        readonly=True,
        store=True,
        copy=False,
    )
    ecf_qr_image = fields.Binary(
        string='Imagen QR e-CF',
        readonly=True,
        store=True,
        copy=False,
    )
    ecf_codigo_seguridad = fields.Char(
        string='Código de Seguridad',
        readonly=True,
        store=True,
        copy=False,
    )
    ecf_fecha_firma = fields.Datetime(
        string='Fecha de Firma',
        readonly=True,
        store=True,
        copy=False,
    )

    # =========================================================================
    # MONEDA / TASA DE CAMBIO
    # =========================================================================

    l10n_do_currency_rate = fields.Float(
        string='Tasa de Cambio (DOP)',
        digits=(12, 4),
        default=1.0,
        help='Tasa de conversión a DOP al momento de emitir la factura.',
    )
    show_exchange_rate = fields.Boolean(
        string='Mostrar Tasa de Cambio',
        compute='_compute_show_exchange_rate',
    )

    # =========================================================================
    # DATOS ADICIONALES PARA EL PAYLOAD
    # =========================================================================

    l10n_do_payment_type = fields.Selection(
        selection=[
            ('1', 'Efectivo'),
            ('2', 'Cheques / Transferencias / Depósito'),
            ('3', 'Tarjeta Crédito / Débito'),
            ('4', 'Compra a Crédito'),
            ('5', 'Bonos o Certificados de Regalo'),
            ('6', 'Permuta'),
            ('7', 'Nota de Crédito'),
            ('8', 'Mixto'),
        ],
        string='Tipo de Pago (DGII)',
        compute='_compute_l10n_do_payment_type',
        store=True,
        readonly=False,
        copy=False,
    )
    l10n_do_seller_code = fields.Char(string='Código Vendedor')
    l10n_do_purchase_order_number = fields.Char(string='Número Pedido Interno')
    l10n_do_sales_zone = fields.Char(string='Zona de Venta')
    l10n_do_sales_route = fields.Char(string='Ruta de Venta')
    l10n_do_additional_seller_info = fields.Char(string='Info Adicional Emisor')
    l10n_do_modification_reason = fields.Char(string='Razón de Modificación', copy=False)
    l10n_do_indicador_monto_gravado = fields.Selection(
        selection=[('0', 'No'), ('1', 'Sí')],
        string='Indicador Monto Gravado',
        default='0',
    )

    # =========================================================================
    # CAMPOS COMPUTADOS
    # =========================================================================

    @api.depends('currency_id', 'company_id')
    def _compute_show_exchange_rate(self):
        for move in self:
            move.show_exchange_rate = bool(
                move.currency_id
                and move.company_id.currency_id
                and move.currency_id != move.company_id.currency_id
            )

    @api.depends('invoice_payments_widget')
    def _compute_l10n_do_payment_type(self):
        for move in self:
            if move.move_type == 'out_refund':
                move.l10n_do_payment_type = '7'
                continue
            payment_type = '1'
            reconciled = move._get_reconciled_payments()
            if reconciled:
                journal = reconciled[0].journal_id
                if hasattr(journal, 'l10n_do_payment_form') and journal.l10n_do_payment_form:
                    payment_type = PAYMENT_FORM_TO_DGII_CODE.get(journal.l10n_do_payment_form, '1')
            move.l10n_do_payment_type = payment_type

    # =========================================================================
    # ONCHANGES
    # =========================================================================

    @api.onchange('currency_id', 'invoice_date')
    def _onchange_ecf_currency_rate(self):
        for move in self:
            if not move.currency_id or not move.company_id:
                continue
            if move.reversed_entry_id:
                move.l10n_do_currency_rate = move.reversed_entry_id.l10n_do_currency_rate
                continue
            if move.currency_id == move.company_id.currency_id:
                move.l10n_do_currency_rate = 1.0
            else:
                rate_date = move.invoice_date or fields.Date.today()
                move.l10n_do_currency_rate = move.env['res.currency']._get_conversion_rate(
                    move.currency_id,
                    move.company_id.currency_id,
                    move.company_id,
                    rate_date,
                )

    # =========================================================================
    # OVERRIDE DE CONSTRAINT DE SECUENCIA
    # Los e-CF usan secuencias propias de la DGII que no siguen el patrón
    # cronológico que Odoo valida, por lo que se excluyen de esa validación.
    # =========================================================================

    def _constrains_date_sequence(self):
        to_validate = self.filtered(lambda m: not m.is_ecf_invoice)
        if to_validate:
            return super(AccountMove, to_validate)._constrains_date_sequence()

    # =========================================================================
    # HELPERS UTILITARIOS
    # =========================================================================

    def _ecf_get_doc_type(self):
        """Extrae el código numérico del tipo de documento. 'E31' → '31'."""
        self.ensure_one()
        prefix = self.l10n_latam_document_type_id.doc_code_prefix or ''
        return prefix.lstrip('E')

    def _ecf_get_sequence(self):
        """Extrae la parte numérica del NCF. 'E310000000101' → '0000000101'."""
        self.ensure_one()
        fiscal = self.l10n_do_fiscal_number or self.l10n_latam_document_number or ''
        return fiscal[3:] if len(fiscal) > 3 else '0000000001'

    def _ecf_is_consumer_final(self, doc_type):
        self.ensure_one()
        if doc_type in ('43', '47'):
            return True
        partner = self.partner_id
        return not partner.vat or partner.l10n_do_dgii_tax_payer_type == 'non_payer'

    def _ecf_extract_emails(self, record):
        raw = record.email or ''
        if not raw.strip():
            return ['']
        emails = [e.strip() for e in re.split(r'[;,\s]+', raw) if e.strip()]
        return emails or ['']

    def _ecf_extract_phones(self, record):
        raw = record.phone or ''
        if not raw.strip():
            return ['']
        phones = [p.strip() for p in re.split(r'[;,]+', raw) if p.strip()]
        return phones or ['']

    def _ecf_get_item_codes(self, product):
        if product.barcode:
            return [{'name': 'EAN', 'value': product.barcode}]
        if product.default_code:
            return [{'name': 'PLU', 'value': product.default_code}]
        return [{'name': 'SIN_CODIGO', 'value': '0'}]

    def _ecf_get_item_type(self, line, doc_type):
        """Tipo de ítem DGII: '1' = Bien, '2' = Servicio."""
        if doc_type == '47':
            return '2'
        product = line.product_id
        if not product:
            return '1'
        if hasattr(product, 'l10n_do_product_type') and product.l10n_do_product_type:
            return product.l10n_do_product_type
        return '2' if product.type == 'service' else '1'

    def _ecf_get_indicador_facturacion(self, doc_type, line):
        """IndicadorFacturacion por línea según DGII."""
        product = line.product_id
        if product and hasattr(product, 'l10n_do_billing_indicator') and product.l10n_do_billing_indicator:
            return product.l10n_do_billing_indicator
        if doc_type in ('43', '44', '47'):
            return '2'
        has_itbis = any(_is_itbis_tax(t) and not _is_retention_tax(t) for t in line.tax_ids)
        if has_itbis:
            return '1'
        return '4' if self._ecf_get_item_type(line, doc_type) == '2' else '3'

    def _ecf_format_amount(self, amount):
        return '{:.2f}'.format(abs(float(amount or 0.0)))

    def _ecf_get_price_unit_without_tax(self, line):
        """Precio unitario neto. Odoo ya calculó price_subtotal sin importar price_include."""
        if line.quantity:
            return float(line.price_subtotal) / float(line.quantity)
        return float(line.price_unit or 0.0)

    def _convert_to_dop(self, amount):
        """Convierte un monto a DOP usando la tasa almacenada (Decimal para precisión)."""
        from decimal import Decimal, ROUND_HALF_UP
        rate = Decimal(str(self.l10n_do_currency_rate or 1.0))
        d = Decimal(str(float(amount or 0.0)))
        return float((d * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def _ecf_get_ncf_expiry_date(self):
        self.ensure_one()
        if self.l10n_do_ncf_expiration_date:
            return self.l10n_do_ncf_expiration_date.strftime('%Y-%m-%d')
        return ''

    def _ecf_get_ref_invoice(self):
        self.ensure_one()
        return self.reversed_entry_id or self.debit_origin_id or self.env['account.move']

    def _ecf_should_send(self):
        """Devuelve True si el tipo de comprobante está habilitado para envío a la DGII.
        Si no existe registro de configuración para el tipo, se asume True.
        """
        self.ensure_one()
        config = self.env['l10n_do.ecf.doc.type.config'].search([
            ('company_id', '=', self.company_id.id),
            ('doc_type', '=', self._ecf_get_doc_type()),
        ], limit=1)
        return config.send_to_dgii if config else True

    def _ecf_generate_qr_image(self):
        """Lee ecf_qr_url, genera PNG con qrcode y lo guarda en base64 en ecf_qr_image.
        Si la librería qrcode no está instalada, omite silenciosamente.
        """
        self.ensure_one()
        if not self.ecf_qr_url:
            return
        try:
            import qrcode
        except ImportError:
            return
        qr = qrcode.make(self.ecf_qr_url)
        buf = BytesIO()
        qr.save(buf, format='PNG')
        self.ecf_qr_image = base64.b64encode(buf.getvalue())

    # =========================================================================
    # EXTRACCIÓN DE TOTALES DE IMPUESTOS (Odoo 18, sin recalcular)
    # =========================================================================

    def _ecf_get_tax_totals(self, doc_type):
        """Lee totales de impuestos desde los datos calculados por Odoo.

        Fuentes:
        - self.line_ids (display_type='tax'): importes reales del asiento contable
        - line.price_subtotal: base por línea ya calculada por Odoo

        Retorna dict con:
          total_taxes          lista TotalTax para el JSON
          total_itbis          suma ITBIS positivo
          total_exempt         suma bases de líneas sin ITBIS
          total_isr_retencion  total ISR retenido
          total_itbis_retenido total ITBIS retenido
          line_retentions      {line.id: {MontoISRRetenido, MontoITBISRetenido}}
        """
        self.ensure_one()

        # Leer asientos de impuesto reales del diario
        tax_lines = self.line_ids.filtered(
            lambda l: l.display_type == 'tax' and l.tax_line_id
        )

        itbis_groups = {}   # code → {Code, Rate, TaxableAmount, Amount}
        total_itbis = 0.0
        total_isr_retencion = 0.0
        total_itbis_retenido = 0.0

        for tl in tax_lines:
            tax = tl.tax_line_id
            amount = abs(float(tl.amount_currency or 0.0))
            rate = abs(float(tax.amount or 0.0))
            is_ret = _is_retention_tax(tax)

            if _is_itbis_tax(tax):
                if is_ret:
                    total_itbis_retenido += amount
                else:
                    code = ITBIS_CODE_MAP.get(round(rate, 1), 'ITBIS1')
                    if code not in itbis_groups:
                        itbis_groups[code] = {'Code': code, 'Rate': rate, 'TaxableAmount': 0.0, 'Amount': 0.0}
                    itbis_groups[code]['Amount'] += amount
                    total_itbis += amount
            elif _is_isr_tax(tax) and is_ret:
                total_isr_retencion += amount

        # Calcular bases imponibles desde líneas de producto
        product_lines = self.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
        total_exempt = 0.0

        for line in product_lines:
            codes_on_line = set()
            for tax in line.tax_ids:
                if _is_itbis_tax(tax) and not _is_retention_tax(tax):
                    code = ITBIS_CODE_MAP.get(round(abs(float(tax.amount or 0.0)), 1), 'ITBIS1')
                    if code in itbis_groups:
                        itbis_groups[code]['TaxableAmount'] += abs(float(line.price_subtotal or 0.0))
                    codes_on_line.add(code)
            if not codes_on_line:
                total_exempt += abs(float(line.price_subtotal or 0.0))

        # Construir lista formateada (camelCase según spec de la API)
        total_tax_list = []
        for code in sorted(itbis_groups.keys()):
            entry = itbis_groups[code]
            total_tax_list.append({
                'code': entry['Code'],
                'taxableAmount': self._ecf_format_amount(entry['TaxableAmount']),
                'rate': self._ecf_format_amount(entry['Rate']),
                'amount': self._ecf_format_amount(entry['Amount']),
            })

        if total_exempt > 0:
            total_tax_list.append({
                'code': 'EXENTO',
                'amount': self._ecf_format_amount(total_exempt),
            })

        # Sin impuestos ni exentos pero con base → ITBIS3 a 0%
        if not total_tax_list and self.amount_untaxed:
            total_tax_list.append({
                'code': 'ITBIS3',
                'taxableAmount': self._ecf_format_amount(self.amount_untaxed),
                'rate': '0.00',
                'amount': '0.00',
            })

        # Retenciones por línea: price_subtotal × tasa (sin compute_all)
        line_retentions = {}
        for line in product_lines:
            isr_ret = 0.0
            itbis_ret = 0.0
            base = abs(float(line.price_subtotal or 0.0))
            for tax in line.tax_ids:
                if not _is_retention_tax(tax):
                    continue
                ret_amount = abs(float(tax.amount or 0.0)) / 100.0 * base
                if _is_itbis_tax(tax):
                    itbis_ret += ret_amount
                else:
                    isr_ret += ret_amount
            line_retentions[line.id] = {
                'MontoISRRetenido': self._ecf_format_amount(isr_ret),
                'MontoITBISRetenido': self._ecf_format_amount(itbis_ret),
            }

        return {
            'total_taxes': total_tax_list,
            'total_itbis': total_itbis,
            'total_exempt': total_exempt,
            'total_isr_retencion': total_isr_retencion,
            'total_itbis_retenido': total_itbis_retenido,
            'line_retentions': line_retentions,
        }

    # =========================================================================
    # SECCIONES DEL JSON
    # =========================================================================

    def _ecf_get_header(self, doc_type):
        self.ensure_one()
        inv_date = self.invoice_date or date.today()

        additional_info = [
            {'name': 'Secuencia', 'value': self._ecf_get_sequence()},
        ]

        # FechaVencimientoSecuencia: excluir para 32 y 34
        if doc_type not in ('32', '34'):
            ncf_expiry = self._ecf_get_ncf_expiry_date()
            if ncf_expiry:
                additional_info.append({'name': 'FechaVencimientoSecuencia', 'value': ncf_expiry})

        # IndicadorNotaCredito: solo para tipo 34
        if doc_type == '34':
            ref_invoice = self._ecf_get_ref_invoice()
            indicator = '0'
            if ref_invoice and ref_invoice.invoice_date:
                indicator = '1' if (inv_date - ref_invoice.invoice_date).days > 30 else '0'
            additional_info.append({'name': 'IndicadorNotaCredito', 'value': indicator})

        # IndicadorEnvioDiferido: excluir solo para 43
        if doc_type != '43':
            additional_info.append({'name': 'IndicadorEnvioDiferido', 'value': '1'})

        # IndicadorMontoGravado: excluir para 43
        if doc_type != '43':
            additional_info.append({
                'name': 'IndicadorMontoGravado',
                'value': self.l10n_do_indicador_monto_gravado or '0',
            })

        # TipoIngresos: excluir para 41, 43, 47
        if doc_type not in ('41', '43', '47'):
            additional_info.append({
                'name': 'TipoIngresos',
                'value': self.l10n_do_income_type or '01',
            })

        # TipoPago: excluir para 43
        if doc_type != '43':
            additional_info.append({'name': 'TipoPago', 'value': self.l10n_do_payment_type or '1'})

        # FechaDesde / FechaHasta: excluir para 43
        if doc_type != '43':
            additional_info.append({'name': 'FechaDesde', 'value': inv_date.strftime('%Y-%m-%d')})
            end_date = self.invoice_date_due or inv_date
            additional_info.append({'name': 'FechaHasta', 'value': end_date.strftime('%Y-%m-%d')})

        return {
            'docType': doc_type,
            'issuedDateTime': inv_date.strftime('%Y-%m-%dT00:00:00'),
            'additionalIssueDocInfo': additional_info,
        }

    def _ecf_get_seller(self, doc_type):
        self.ensure_one()
        company = self.company_id

        additional_info = [
            {'name': 'NombreComercial', 'value': company.l10n_do_trade_name or company.name or ''},
            {'name': 'ActividadEconomica', 'value': company.l10n_do_economic_activity or ''},
        ]

        if doc_type not in ('41', '43', '47'):
            additional_info.append({'name': 'CodigoVendedor', 'value': self.l10n_do_seller_code or ''})

        additional_info.extend([
            {'name': 'NumeroFacturaInterna', 'value': self.name or ''},
            {'name': 'NumeroPedidoInterno', 'value': self.l10n_do_purchase_order_number or self.invoice_origin or self.name or ''},
        ])

        if doc_type not in ('41', '43', '47'):
            additional_info.append({'name': 'ZonaVenta', 'value': self.l10n_do_sales_zone or ''})
            additional_info.append({'name': 'RutaVenta', 'value': self.l10n_do_sales_route or ''})

        additional_info.append({'name': 'InformacionAdicionalEmisor', 'value': self.l10n_do_additional_seller_info or ''})

        district_code = company.l10n_do_municipality_id.code if hasattr(company, 'l10n_do_municipality_id') and company.l10n_do_municipality_id else '010100'
        state_code = company.state_id.l10n_do_dgii_code if company.state_id and hasattr(company.state_id, 'l10n_do_dgii_code') else '010000'

        return {
            'taxID': self._ecf_sanitize_tax_id(company.vat),
            'name': company.name or '',
            'contact': {
                'phoneList': {'phone': self._ecf_extract_phones(company)},
                'emailList': {'email': self._ecf_extract_emails(company)},
                'website': company.website or '',
            },
            'additionlInfo': additional_info,
            'branchInfo': {
                'name': company.l10n_do_branch_code or '0001',
                'addressInfo': {
                    'address': company.street or '',
                    'district': district_code,
                    'state': state_code,
                    'country': 'DO',
                },
            },
        }

    def _ecf_sanitize_tax_id(self, vat):
        """Removes dashes and non-numeric chars from TaxID per DGII spec."""
        return re.sub(r'[^0-9]', '', vat or '')

    def _ecf_get_buyer(self, doc_type):
        self.ensure_one()
        partner = self.partner_id
        is_consumer = self._ecf_is_consumer_final(doc_type)

        if doc_type in ('43', '47'):
            return {
                'taxID': 'NO_APLICA',
                'name': '' if doc_type == '43' else (partner.name or ''),
                'contact': {
                    'phoneList': {'phone': self._ecf_extract_phones(partner)},
                    'emailList': {'email': self._ecf_extract_emails(partner)},
                },
                'additionlInfo': [],
                'addressInfo': self._ecf_get_address_info(partner),
            }

        if is_consumer:
            return {'taxID': 'NO_APLICA'}

        return {
            'taxID': self._ecf_sanitize_tax_id(partner.vat),
            'name': partner.name or '',
            'contact': {
                'phoneList': {'phone': self._ecf_extract_phones(partner)},
                'emailList': {'email': self._ecf_extract_emails(partner)},
            },
            'additionlInfo': [],
            'addressInfo': self._ecf_get_address_info(partner),
        }

    def _ecf_get_address_info(self, partner):
        district_code = partner.l10n_do_municipality_id.code if hasattr(partner, 'l10n_do_municipality_id') and partner.l10n_do_municipality_id else '010100'
        state_code = partner.state_id.l10n_do_dgii_code if partner.state_id and hasattr(partner.state_id, 'l10n_do_dgii_code') else '010000'
        return {
            'address': partner.street or '',
            'district': district_code,
            'state': state_code,
            'country': 'DO',
        }

    def _ecf_get_items(self, doc_type, tax_data):
        self.ensure_one()
        items = []
        product_lines = self.invoice_line_ids.filtered(lambda l: l.display_type == 'product')

        for line in product_lines:
            product = line.product_id
            price_unit = self._ecf_get_price_unit_without_tax(line)

            item = {
                'codes': self._ecf_get_item_codes(product),
                'type': self._ecf_get_item_type(line, doc_type),
                'description': (line.name or (product.name if product else 'SIN_DESCRIPCION'))[:80],
                'qty': self._ecf_format_amount(line.quantity),
                'unitOfMeasure': (
                    product.uom_id.l10n_do_dgii_code
                    if product and product.uom_id and hasattr(product.uom_id, 'l10n_do_dgii_code') and product.uom_id.l10n_do_dgii_code
                    else '43'
                ),
                'price': self._ecf_format_amount(price_unit),
            }

            # Discounts y Charges: excluir para 43 y 47
            if doc_type not in ('43', '47'):
                discount_rate = float(line.discount or 0.0)
                if discount_rate > 0:
                    discount_amount = float(line.price_unit or 0.0) * (discount_rate / 100.0) * float(line.quantity or 0.0)
                    item['discounts'] = {
                        'discount': [{'code': '%', 'amount': self._ecf_format_amount(discount_amount), 'rate': self._ecf_format_amount(discount_rate)}],
                    }
                else:
                    item['discounts'] = {
                        'discount': [{'code': '$', 'amount': '0.00', 'rate': '0.00'}],
                    }
                item['charges'] = {'charge': [{'code': '$', 'amount': '0.00'}]}

            item['totals'] = {'totalItem': self._ecf_format_amount(line.price_subtotal)}

            retention = tax_data.get('line_retentions', {}).get(line.id, {})
            additional_info = [
                {'name': 'DescripcionItem', 'value': product.name if product else ''},
                {'name': 'IndicadorFacturacion', 'value': self._ecf_get_indicador_facturacion(doc_type, line)},
            ]

            # MontoISRRetenido: solo cuando hay monto (se omite cuando es "0.00")
            isr_retenido = retention.get('MontoISRRetenido', '0.00')
            if doc_type not in ('47',) and float(isr_retenido) > 0:
                additional_info.append({'name': 'MontoISRRetenido', 'value': isr_retenido})

            if doc_type in ('41', '47'):
                # nombre correcto del campo: IndicadorAgenteRetencionoPercepcion (con 'o')
                additional_info.append({'name': 'IndicadorAgenteRetencionoPercepcion', 'value': '1'})
                if doc_type == '41':
                    additional_info.append({
                        'name': 'MontoITBISRetenido',
                        'value': retention.get('MontoITBISRetenido', '0.00'),
                    })

            item['additionalInfo'] = additional_info
            items.append(item)

        return items

    def _ecf_get_totals(self, doc_type, tax_data):
        self.ensure_one()
        product_lines = self.invoice_line_ids.filtered(lambda l: l.display_type == 'product')

        totals = {
            'qtyItems': len(product_lines),
            'totalTaxableAmount': self._ecf_format_amount(self.amount_untaxed),
        }

        if doc_type == '47':
            totals['totalTaxes'] = {
                'totalTax': [{'code': 'EXENTO', 'amount': self._ecf_format_amount(self.amount_total)}],
            }
        else:
            totals['totalTaxes'] = {'totalTax': tax_data.get('total_taxes', [])}

        totals['grandTotal'] = {'invoiceTotal': self._ecf_format_amount(self.amount_total)}

        # E41 requiere TotalITBISRetenido y TotalISRRetencion (XSD obliga, no tienen default)
        if doc_type in ('41', '47'):
            totals_additional = [
                {'name': 'TotalISRRetencion', 'value': self._ecf_format_amount(tax_data.get('total_isr_retencion', 0.0))},
            ]
            if doc_type == '41':
                totals_additional.append({
                    'name': 'TotalITBISRetenido',
                    'value': self._ecf_format_amount(tax_data.get('total_itbis_retenido', 0.0)),
                })
            totals['additionalInfo'] = totals_additional

        return totals

    def _ecf_get_additional_doc_info(self, doc_type, tax_data):
        self.ensure_one()

        # Tipos que no usan additionalDocumentInfo
        if doc_type in ('43', '44', '47'):
            return {}

        data_blocks = []

        # Bloque InformacionReferencia: solo para notas de crédito/débito (33, 34)
        if doc_type in ('33', '34'):
            ref_invoice = self._ecf_get_ref_invoice()
            ref_info = [
                {
                    'name': 'NCFModificado',
                    'value': (ref_invoice.l10n_do_fiscal_number or ref_invoice.l10n_latam_document_number or '') if ref_invoice else '',
                },
                {
                    'name': 'FechaNCFModificado',
                    'value': ref_invoice.invoice_date.strftime('%d-%m-%Y') if ref_invoice and ref_invoice.invoice_date else '',
                },
                {
                    'name': 'CodigoModificacion',
                    'value': self.l10n_do_ecf_modification_code or '',
                },
            ]
            if self.l10n_do_modification_reason:
                ref_info.append({'name': 'RazonModificacion', 'value': self.l10n_do_modification_reason})
            data_blocks.append({'name': 'InformacionReferencia', 'info': ref_info})

        if not data_blocks:
            return {}

        return {
            'additionalInfo': [{
                'aditionalData': {'data': data_blocks},
            }],
        }

    def _ecf_get_payments(self, doc_type, tax_data):
        self.ensure_one()
        # La API no emite TablaFormasPago para E34 ni E43
        if doc_type in ('34', '43'):
            return []
        if doc_type == '41':
            net = self.amount_total - tax_data.get('total_isr_retencion', 0.0) - tax_data.get('total_itbis_retenido', 0.0)
            amount = self._ecf_format_amount(net)
        else:
            # MontoPago = monto total con impuestos que paga el comprador
            amount = self._ecf_format_amount(self.amount_total)
        return [{'code': self.l10n_do_payment_type or '1', 'amount': amount}]

    # =========================================================================
    # CONSTRUCTOR PRINCIPAL
    # =========================================================================

    def _build_ecf_payload(self):
        """Construye el dict completo del payload JSON e-CF para esta factura.
        Todos los importes se leen de Odoo sin recálculo propio.
        """
        self.ensure_one()

        doc_type = self._ecf_get_doc_type()

        if not self.name or self.name == '/':
            raise UserError(_('La factura debe tener un nombre válido antes de generar el JSON e-CF.'))

        if doc_type in ('33', '34') and not self.l10n_do_ecf_modification_code:
            raise UserError(_('Las Notas de Crédito/Débito (E33/E34) requieren un Código de Modificación.'))

        tax_data = self._ecf_get_tax_totals(doc_type)
        is_live_flag = '1' if getattr(self.company_id, 'is_live', False) else '0'

        return {
            'live': is_live_flag,
            'version': '1.0',
            'countryCode': 'DO',
            'idUser': self.env.user.id,
            'taxID': self._ecf_sanitize_tax_id(self.company_id.vat),
            'header': self._ecf_get_header(doc_type),
            'seller': self._ecf_get_seller(doc_type),
            'buyer': self._ecf_get_buyer(doc_type),
            'items': self._ecf_get_items(doc_type, tax_data),
            'totals': self._ecf_get_totals(doc_type, tax_data),
            'payments': self._ecf_get_payments(doc_type, tax_data),
            'additionalDocumentInfo': self._ecf_get_additional_doc_info(doc_type, tax_data),
        }

    # =========================================================================
    # CICLO DE VIDA: CONFIRMACIÓN CON AUTO-ENVÍO ECF
    # =========================================================================

    def action_post(self):
        """Override: si ecf_auto_send está activo en la empresa, envía al DGII al confirmar."""
        res = super().action_post()
        for move in self.filtered('is_ecf_invoice'):
            if not move.company_id.ecf_auto_send:
                continue
            if not move._ecf_should_send():
                move.write({
                    'ecf_validation_status': 'skipped',
                    'ecf_api_message': 'Tipo deshabilitado en configuración de la empresa.',
                })
                continue
            try:
                move.action_send_ecf()
            except Exception as e:
                move.write({
                    'ecf_api_message': str(e),
                    'ecf_validation_status': 'error',
                })
        return res

    # =========================================================================
    # ACCIÓN WIZARD DE PREVISUALIZACIÓN
    # =========================================================================

    def action_send_ecf(self):
        """Envía el payload e-CF a api.ecf-software.online y persiste la respuesta."""
        self.ensure_one()

        # Verificar si el tipo está habilitado para envío en la configuración de la empresa
        if not self._ecf_should_send():
            self.write({
                'ecf_validation_status': 'skipped',
                'ecf_api_message': 'Tipo de comprobante deshabilitado en la configuración de la empresa.',
            })
            return

        # Validación previa: E32 ≥ 250,000 DOP exige RNC del comprador
        if self._ecf_get_doc_type() == '32' and self.amount_total >= 250000:
            if not self.partner_id.vat:
                raise UserError(_(
                    'E32 con monto ≥ 250,000 DOP requiere que el cliente tenga RNC o Cédula.'
                ))

        api_url = (self.company_id.ecf_api_url or '').rstrip('/')
        api_key = self.company_id.ecf_api_key
        if not api_url or not api_key:
            raise UserError(_('Configure la URL y el API Key ECF en la empresa antes de enviar.'))

        payload = self._build_ecf_payload()

        try:
            response = requests.post(
                f'{api_url}/api/factura/generar-comprobante',
                json=payload,
                headers={'Authorization': f'Bearer {api_key}'},
                timeout=30,
            )
            data = response.json()
        except Exception as e:
            self.write({
                'ecf_api_message': str(e),
                'ecf_validation_status': 'error',
            })
            return

        if response.ok:
            qr_url = data.get('qrUrl') or ''
            self.write({
                'ecf_track_id': data.get('trackId'),
                'ecf_qr_url': qr_url,
                'ecf_codigo_seguridad': data.get('codigoSeguridad'),
                'ecf_api_message': str(data),
                'ecf_validation_status': data.get('estado') or 'rfce',
            })
            if qr_url:
                self._ecf_generate_qr_image()
        else:
            self.write({
                'ecf_api_message': data.get('error', str(data)),
                'ecf_validation_status': 'error',
            })

    def action_view_ecf_error(self):
        """Abre un wizard con la última respuesta cruda de la API. Solo visible en estado error."""
        self.ensure_one()
        wizard = self.env['l10n_do.ecf.error.wizard'].create({
            'move_id': self.id,
            'api_response': self.ecf_api_message or '(sin respuesta registrada)',
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Respuesta API — %s' % (self.name or ''),
            'res_model': 'l10n_do.ecf.error.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }

    def action_preview_ecf_json(self):
        """Abre el wizard mostrando el JSON e-CF generado para esta factura."""
        self.ensure_one()
        payload = self._build_ecf_payload()
        json_str = json.dumps(payload, indent=4, ensure_ascii=False)

        wizard = self.env['l10n_do.ecf.preview.wizard'].create({
            'move_id': self.id,
            'json_preview': json_str,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'JSON e-CF: %s' % (self.name or ''),
            'res_model': 'l10n_do.ecf.preview.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }
