import json
import re
from datetime import date, datetime

from odoo import models, fields, api, _
from odoo.exceptions import UserError


# Mapeo del l10n_do_payment_form del diario al código DGII numérico
PAYMENT_FORM_TO_DGII_CODE = {
    'cash': '1',       # Efectivo
    'bank': '2',       # Cheques / Transferencias / Depósito
    'card': '3',       # Tarjeta Crédito / Débito
    'credit': '4',     # Compra a Crédito
    'bond': '5',       # Bonos o Certificados de Regalo
    'swap': '6',       # Permuta
    'others': '8',     # Mixto
}


class AccountMove(models.Model):
    _inherit = 'account.move'

    # =========================================================================
    # CAMPOS NUEVOS PARA EL PAYLOAD DIGIFACT
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
        help='Código de tipo de pago que se envía en el e-CF. '
             'Se calcula automáticamente desde el pago registrado, pero puede editarse.',
    )

    l10n_do_seller_code = fields.Char(
        string='Código Vendedor',
        help='Código del vendedor asignado para el payload del e-CF (CodigoVendedor).',
    )
    l10n_do_purchase_order_number = fields.Char(
        string='Número Pedido Interno',
        help='Número del pedido interno (NumeroPedidoInterno) para el payload e-CF.',
    )
    l10n_do_sales_zone = fields.Char(
        string='Zona de Venta',
        help='Zona de venta para el payload del e-CF (ZonaVenta).',
    )
    l10n_do_sales_route = fields.Char(
        string='Ruta de Venta',
        help='Ruta de venta para el payload del e-CF (RutaVenta).',
    )
    l10n_do_additional_seller_info = fields.Char(
        string='Info Adicional Emisor',
        help='Información adicional del emisor (InformacionAdicionalEmisor).',
    )
    l10n_do_modification_reason = fields.Char(
        string='Razón de Modificación',
        copy=False,
        help='Razón de modificación obligatoria para Notas de Crédito / Débito (E33/E34).',
    )
    l10n_do_indicador_monto_gravado = fields.Selection(
        selection=[('0', 'No'), ('1', 'Sí')],
        string='Indicador Monto Gravado',
        default='0',
        help='Indicador de monto gravado para el e-CF.',
    )

    # =========================================================================
    # COMPUTE: TIPO DE PAGO DESDE EL PAGO REGISTRADO
    # =========================================================================

    @api.depends('invoice_payments_widget')
    def _compute_l10n_do_payment_type(self):
        """Calcula el tipo de pago DGII desde el pago registrado en la factura.
        Usa el campo l10n_do_payment_form del diario del pago.
        Si no hay pago registrado, default a '1' (Efectivo).
        Si es nota de crédito (out_refund), default a '7'.
        """
        for move in self:
            if move.move_type == 'out_refund':
                move.l10n_do_payment_type = '7'
                continue

            # Buscar pagos conciliados con esta factura
            payment_type = '1'  # Default: Efectivo
            reconciled_payments = move._get_reconciled_payments()
            if reconciled_payments:
                # Tomar el primer pago como referencia
                first_payment = reconciled_payments[0]
                journal = first_payment.journal_id
                if hasattr(journal, 'l10n_do_payment_form') and journal.l10n_do_payment_form:
                    payment_type = PAYMENT_FORM_TO_DGII_CODE.get(
                        journal.l10n_do_payment_form, '1'
                    )
            move.l10n_do_payment_type = payment_type

    # =========================================================================
    # HELPERS UTILITARIOS
    # =========================================================================

    def _digifact_get_doc_type(self):
        """Extrae el código numérico del tipo de documento.
        Ej: 'E31' -> '31', 'E34' -> '34'
        """
        self.ensure_one()
        prefix = self.l10n_latam_document_type_id.doc_code_prefix or ''
        return prefix.lstrip('E')

    def _digifact_get_sequence(self):
        """Extrae la secuencia numérica del NCF.
        Ej: 'E340000000101' -> '0000000101'
        l10n_do_accounting ya genera la secuencia completa en l10n_do_fiscal_number.
        """
        self.ensure_one()
        fiscal_number = self.l10n_do_fiscal_number or self.l10n_latam_document_number or ''
        if len(fiscal_number) > 3:
            return fiscal_number[3:]
        return '0000000001'

    def _digifact_is_consumer_final(self, doc_type):
        """Determina si el comprador es consumidor final.
        Para doc_type 43 y 47, siempre es consumidor final.
        """
        self.ensure_one()
        if doc_type in ('43', '47'):
            return True
        partner = self.partner_id
        return (
            not partner.vat
            or partner.l10n_do_dgii_tax_payer_type == 'non_payer'
        )

    def _digifact_extract_emails(self, record):
        """Extrae lista de emails limpios de un partner o company.
        Devuelve siempre una lista; si no hay emails, retorna [''].
        """
        email_raw = record.email or ''
        if not email_raw.strip():
            return ['']
        emails = [e.strip() for e in re.split(r'[;,\s]+', email_raw) if e.strip()]
        return emails or ['']

    def _digifact_extract_phones(self, record):
        """Extrae lista de teléfonos limpios de un partner o company.
        Devuelve siempre una lista; si no hay teléfonos, retorna [''].
        """
        phone_raw = record.phone or ''
        if not phone_raw.strip():
            return ['']
        phones = [p.strip() for p in re.split(r'[;,]+', phone_raw) if p.strip()]
        return phones or ['']

    def _digifact_get_item_codes(self, product):
        """Genera el bloque Codes[] para un producto.
        Prioridad: barcode (EAN) > default_code (PLU) > SIN_CODIGO
        """
        if product.barcode:
            return [{'Name': 'EAN', 'Value': product.barcode}]
        elif product.default_code:
            return [{'Name': 'PLU', 'Value': product.default_code}]
        return [{'Name': 'SIN_CODIGO', 'Value': '0'}]

    def _digifact_get_item_type(self, line, doc_type):
        """Determina el tipo de ítem (1=Bien, 2=Servicio).
        Para doc_type '47' siempre es '2' (servicio).
        Para los demás, se infiere del tipo del producto en Odoo.
        """
        if doc_type == '47':
            return '2'
        product = line.product_id
        if not product:
            return '1'
        # En Odoo 18: product.type puede ser 'consu', 'service', 'product'
        if product.type == 'service':
            return '2'
        return '1'

    def _digifact_get_indicador_facturacion(self, doc_type, line):
        """Determina el IndicadorFacturacion para una línea.
        '1' = Gravado ITBIS
        '2' = Otras exenciones
        '3' = Bienes exentos
        '4' = Servicios exentos
        """
        # Tipos sin gravamen: siempre '2'
        if doc_type in ('43', '44', '47'):
            return '2'

        # Si la línea tiene impuestos con monto > 0, está gravada
        has_tax = any(tax.amount > 0 for tax in line.tax_ids)
        if has_tax:
            return '1'

        # Si no tiene impuestos o todos son 0%, depende del tipo de producto
        item_type = self._digifact_get_item_type(line, doc_type)
        if item_type == '2':
            return '4'  # servicio exento
        return '3'  # bien exento

    def _digifact_format_amount(self, amount):
        """Formatea un monto a string con 2 decimales."""
        return '{:.2f}'.format(abs(amount))

    def _digifact_get_price_unit_without_tax(self, line):
        """Obtiene el precio unitario sin impuestos desde Odoo.
        Odoo ya calcula price_subtotal = (price_unit * qty * (1 - discount/100))
        Así que el precio unitario sin impuesto es price_subtotal / quantity.
        """
        if line.quantity:
            return line.price_subtotal / line.quantity
        return line.price_unit

    def _digifact_get_ncf_expiry_date(self):
        """Obtiene la fecha de vencimiento del NCF desde el diario.
        l10n_do_accounting almacena esto en l10n_do_ncf_expiration_date del move.
        """
        self.ensure_one()
        if self.l10n_do_ncf_expiration_date:
            return self.l10n_do_ncf_expiration_date.strftime('%Y-%m-%d')
        return ''

    def _digifact_get_ref_invoice(self):
        """Obtiene la factura de referencia para notas de crédito/débito."""
        self.ensure_one()
        return self.reversed_entry_id or self.debit_origin_id or self.env['account.move']

    # =========================================================================
    # EXTRACCION DE TOTALES DE IMPUESTOS (Usando datos de Odoo)
    # =========================================================================

    def _digifact_get_tax_totals(self, doc_type):
        """Extrae los totales de impuestos directamente desde los datos calculados
        por Odoo en la factura. NO recalcula nada.

        Retorna un dict con:
        - 'total_taxes': lista de dicts con Code, TaxableAmount, Rate, Amount
        - 'total_itbis': suma total de ITBIS
        - 'total_exempt': suma total de líneas exentas
        - 'total_isr_retencion': total ISR retenido (para doc 41/47)
        - 'total_itbis_retenido': total ITBIS retenido (para doc 41)
        - 'line_retentions': dict {line_id: {MontoISRRetenido, MontoITBISRetenido}}
        """
        self.ensure_one()

        group_itbis = self.env.ref(
            'account.%s_tax_group_itbis' % self.company_id.id,
            raise_if_not_found=False,
        )
        group_isr = self.env.ref(
            'account.%s_tax_group_isr' % self.company_id.id,
            raise_if_not_found=False,
        )

        # Mapeo de tasas ITBIS a códigos DGII
        itbis_code_map = {
            18.0: 'ITBIS1',
            16.0: 'ITBIS2',
            0.0: 'ITBIS3',
        }

        tax_lines = self.line_ids.filtered(
            lambda l: l.display_type == 'tax'
            and l.tax_line_id
            and l.currency_id == self.currency_id
        )

        # Agrupar impuestos por código DGII
        tax_groups = {}
        total_itbis = 0.0
        total_isr_retencion = 0.0
        total_itbis_retenido = 0.0

        for tl in tax_lines:
            tax = tl.tax_line_id
            tax_amount = abs(tl.amount_currency)
            tax_rate = abs(tax.amount)

            if group_itbis and tl.tax_group_id == group_itbis:
                if tax.amount < 0:
                    # ITBIS Retenido
                    total_itbis_retenido += tax_amount
                else:
                    code = itbis_code_map.get(tax_rate, 'ITBIS1')
                    total_itbis += tax_amount
                    if code not in tax_groups:
                        tax_groups[code] = {
                            'Code': code,
                            'Rate': self._digifact_format_amount(tax_rate),
                            'TaxableAmount': 0.0,
                            'Amount': 0.0,
                        }
                    tax_groups[code]['Amount'] += tax_amount
            elif group_isr and tl.tax_group_id == group_isr:
                if tax.amount < 0:
                    total_isr_retencion += tax_amount

        # Calcular las bases imponibles y montos exentos desde las líneas de producto
        product_lines = self.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
        )
        total_exempt = 0.0

        for line in product_lines:
            line_has_itbis = False
            for tax in line.tax_ids:
                if group_itbis and tax.tax_group_id == group_itbis and tax.amount >= 0:
                    rate = abs(tax.amount)
                    code = itbis_code_map.get(rate, 'ITBIS1')
                    if code in tax_groups:
                        tax_groups[code]['TaxableAmount'] += abs(line.price_subtotal)
                    line_has_itbis = True

            # Si la línea NO tiene ITBIS positivo, es exenta
            if not line_has_itbis:
                total_exempt += abs(line.price_subtotal)

        # Formatear los montos
        total_tax_list = []
        for code in sorted(tax_groups.keys()):
            entry = tax_groups[code]
            total_tax_list.append({
                'Code': entry['Code'],
                'TaxableAmount': self._digifact_format_amount(entry['TaxableAmount']),
                'Rate': entry['Rate'],
                'Amount': self._digifact_format_amount(entry['Amount']),
            })

        # Agregar bloque EXENTO si hay montos exentos
        if total_exempt > 0:
            total_tax_list.append({
                'Code': 'EXENTO',
                'Amount': self._digifact_format_amount(total_exempt),
            })

        # Si no hay impuestos y no hay exentos pero sí hay base, agregar ITBIS3 (0%)
        if not total_tax_list and self.amount_untaxed:
            total_tax_list.append({
                'Code': 'ITBIS3',
                'TaxableAmount': self._digifact_format_amount(self.amount_untaxed),
                'Rate': '0.00',
                'Amount': '0.00',
            })

        # Retenciones por línea (para doc 41 / 47)
        line_retentions = {}
        for line in product_lines:
            isr_ret = 0.0
            itbis_ret = 0.0
            for tax in line.tax_ids:
                if tax.amount < 0:
                    # Calcular el monto de retención para esta línea específica
                    tax_data = tax.compute_all(
                        price_unit=line.price_unit * (1 - (line.discount / 100.0)),
                        quantity=line.quantity,
                        currency=line.currency_id,
                    )
                    for t in tax_data.get('taxes', []):
                        if t['id'] == tax.id:
                            if group_isr and tax.tax_group_id == group_isr:
                                isr_ret += abs(t['amount'])
                            elif group_itbis and tax.tax_group_id == group_itbis:
                                itbis_ret += abs(t['amount'])
            line_retentions[line.id] = {
                'MontoISRRetenido': self._digifact_format_amount(isr_ret),
                'MontoITBISRetenido': self._digifact_format_amount(itbis_ret),
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
    # CONSTRUCTORES DE SECCIONES DEL JSON
    # =========================================================================

    def _digifact_get_header(self, doc_type):
        """Construye el bloque Header del JSON.
        Cada campo se incluye/excluye según el tipo de documento,
        siguiendo exactamente la lógica del PayloadBuilder original.
        """
        self.ensure_one()
        inv_date = self.invoice_date or date.today()

        additional_info = [
            {'Name': 'Secuencia', 'Value': self._digifact_get_sequence()},
        ]

        # FechaVencimientoSecuencia: excluir para 32 y 34
        if doc_type not in ('32', '34'):
            ncf_expiry = self._digifact_get_ncf_expiry_date()
            if ncf_expiry:
                additional_info.append(
                    {'Name': 'FechaVencimientoSecuencia', 'Value': ncf_expiry}
                )

        # IndicadorNotaCredito: solo para tipo 34
        if doc_type == '34':
            ref_invoice = self._digifact_get_ref_invoice()
            indicator = '0'
            if ref_invoice and ref_invoice.invoice_date:
                days_diff = (inv_date - ref_invoice.invoice_date).days
                indicator = '1' if days_diff > 30 else '0'
            additional_info.append(
                {'Name': 'IndicadorNotaCredito', 'Value': indicator}
            )

        # IndicadorEnvioDiferido: excluir para 41, 47, 43
        if doc_type not in ('41', '47', '43'):
            additional_info.append(
                {'Name': 'IndicadorEnvioDiferido', 'Value': '1'}
            )

        # IndicadorMontoGravado: excluir para 43, 44, 46, 47
        if doc_type not in ('43', '44', '46', '47'):
            additional_info.append(
                {'Name': 'IndicadorMontoGravado', 'Value': self.l10n_do_indicador_monto_gravado or '0'}
            )

        # TipoIngresos: excluir para 41, 43, 47
        if doc_type not in ('41', '43', '47'):
            additional_info.append(
                {'Name': 'TipoIngresos', 'Value': self.l10n_do_income_type or '01'}
            )

        # TipoPago: siempre se incluye
        additional_info.append(
            {'Name': 'TipoPago', 'Value': self.l10n_do_payment_type or '1'}
        )

        # FechaDesde (fecha factura) / FechaHasta (fecha vencimiento): excluir para 41, 43
        if doc_type not in ('41', '43'):
            additional_info.append(
                {'Name': 'FechaDesde', 'Value': inv_date.strftime('%Y-%m-%d')}
            )
            end_date = self.invoice_date_due or inv_date
            additional_info.append(
                {'Name': 'FechaHasta', 'Value': end_date.strftime('%Y-%m-%d')}
            )

        return {
            'DocType': doc_type,
            'IssuedDateTime': inv_date.strftime('%Y-%m-%dT00:00:00'),
            'AdditionalIssueDocInfo': additional_info,
        }

    def _digifact_get_seller(self, doc_type):
        """Construye el bloque Seller del JSON."""
        self.ensure_one()
        company = self.company_id

        # Información adicional del emisor
        additional_info = [
            {'Name': 'NombreComercial', 'Value': company.l10n_do_trade_name or company.name or ''},
            {'Name': 'ActividadEconomica', 'Value': company.l10n_do_economic_activity or ''},
        ]

        # CodigoVendedor: solo si NO es 41, 43, 47
        if doc_type not in ('41', '43', '47'):
            additional_info.append(
                {'Name': 'CodigoVendedor', 'Value': self.l10n_do_seller_code or ''}
            )

        additional_info.append(
            {'Name': 'NumeroFacturaInterna', 'Value': self.name or ''}
        )
        additional_info.append(
            {'Name': 'NumeroPedidoInterno', 'Value': self.l10n_do_purchase_order_number or self.invoice_origin or self.name or ''}
        )

        # ZonaVenta, RutaVenta: solo si NO es 41, 43, 47
        if doc_type not in ('41', '43', '47'):
            additional_info.append(
                {'Name': 'ZonaVenta', 'Value': self.l10n_do_sales_zone or ''}
            )
            additional_info.append(
                {'Name': 'RutaVenta', 'Value': self.l10n_do_sales_route or ''}
            )

        additional_info.append(
            {'Name': 'InformacionAdicionalEmisor', 'Value': self.l10n_do_additional_seller_info or ''}
        )

        # BranchInfo: dirección principal de la empresa
        district_code = ''
        state_code = ''
        if hasattr(company, 'l10n_do_municipality_id') and company.l10n_do_municipality_id:
            district_code = company.l10n_do_municipality_id.code or ''
        if company.state_id and hasattr(company.state_id, 'l10n_do_dgii_code'):
            state_code = company.state_id.l10n_do_dgii_code or ''

        return {
            'TaxID': company.vat or '',
            'Name': company.name or '',
            'Contact': {
                'PhoneList': {'Phone': self._digifact_extract_phones(company)},
                'EmailList': {'Email': self._digifact_extract_emails(company)},
                'Website': company.website or '',
            },
            'AdditionlInfo': additional_info,
            'BranchInfo': {
                'Name': company.l10n_do_branch_code or '0001',
                'AddressInfo': {
                    'Address': company.street or '',
                    'District': district_code,
                    'State': state_code,
                    'Country': 'DO',
                },
            },
        }

    def _digifact_get_buyer(self, doc_type):
        """Construye el bloque Buyer del JSON.
        Para tipos 43 y 47: TaxID='NO_APLICA'.
        Para tipo 43: Name=''.
        Contact, AdditionlInfo y AddressInfo siempre se envían (excepto
        cuando es consumidor final por falta de VAT en otros tipos).
        """
        self.ensure_one()
        partner = self.partner_id
        is_consumer = self._digifact_is_consumer_final(doc_type)

        if doc_type in ('43', '47'):
            # Tipos 43 y 47: siempre NO_APLICA
            buyer = {
                'TaxID': 'NO_APLICA',
                'Name': '' if doc_type == '43' else (partner.name or ''),
                'Contact': {
                    'PhoneList': {'Phone': self._digifact_extract_phones(partner)},
                    'EmailList': {'Email': self._digifact_extract_emails(partner)},
                },
                'AdditionlInfo': [
                    {'Name': 'InformacionAdicionalComprador', 'Value': 'Detalles adicionales'},
                ],
                'AddressInfo': self._digifact_get_address_info(partner),
            }
        elif is_consumer:
            # Consumidor final (sin RNC): solo TaxID
            buyer = {
                'TaxID': 'NO_APLICA',
            }
        else:
            # Comprador con RNC válido
            buyer = {
                'TaxID': partner.vat or '',
                'Name': partner.name or '',
                'Contact': {
                    'PhoneList': {'Phone': self._digifact_extract_phones(partner)},
                    'EmailList': {'Email': self._digifact_extract_emails(partner)},
                },
                'AdditionlInfo': [
                    {'Name': 'InformacionAdicionalComprador', 'Value': 'Detalles adicionales'},
                ],
                'AddressInfo': self._digifact_get_address_info(partner),
            }

        return buyer

    def _digifact_get_address_info(self, partner):
        """Extrae el bloque AddressInfo de un partner."""
        district_code = ''
        state_code = ''
        if hasattr(partner, 'l10n_do_municipality_id') and partner.l10n_do_municipality_id:
            district_code = partner.l10n_do_municipality_id.code or ''
        if partner.state_id and hasattr(partner.state_id, 'l10n_do_dgii_code'):
            state_code = partner.state_id.l10n_do_dgii_code or ''
        return {
            'Address': partner.street or '',
            'District': district_code,
            'State': state_code,
            'Country': 'DO',
        }

    def _digifact_get_items(self, doc_type, tax_data):
        """Construye el bloque Items[] del JSON.
        Discounts y Charges se excluyen para tipos 43 y 47 (según PayloadBuilder).
        """
        self.ensure_one()
        items = []

        product_lines = self.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
        )

        for line in product_lines:
            product = line.product_id
            price_unit = self._digifact_get_price_unit_without_tax(line)

            item = {
                'Codes': self._digifact_get_item_codes(product),
                'Type': self._digifact_get_item_type(line, doc_type),
                'Description': line.name or (product.name if product else 'SIN_DESCRIPCION'),
                'Qty': self._digifact_format_amount(line.quantity),
                'UnitOfMeasure': '32',  # TODO: mapear desde uom si se agrega l10n_do_uom_code
                'Price': self._digifact_format_amount(price_unit),
            }

            # Discounts y Charges: excluir para tipos 43 y 47
            if doc_type not in ('43', '47'):
                discount_amount = 0.0
                discount_rate = 0.0
                discount_code = '$'
                if line.discount > 0:
                    discount_code = '%'
                    discount_rate = line.discount
                    discount_amount = line.price_unit * (line.discount / 100.0) * line.quantity

                item['Discounts'] = {
                    'Discount': [{
                        'Code': discount_code,
                        'Amount': self._digifact_format_amount(discount_amount),
                        'Rate': self._digifact_format_amount(discount_rate),
                    }],
                }
                item['Charges'] = {
                    'Charge': [{'Code': '$', 'Amount': '0.00'}],
                }

            item['Totals'] = {
                'TotalItem': self._digifact_format_amount(line.price_subtotal),
            }

            # AdditionalInfo por línea
            additional_info = [
                {'Name': 'DescripcionItem', 'Value': product.name if product else ''},
                {'Name': 'IndicadorFacturacion', 'Value': self._digifact_get_indicador_facturacion(doc_type, line)},
            ]

            # MontoISRRetenido siempre se incluye (como 0.00 si no hay retención)
            retention = tax_data.get('line_retentions', {}).get(line.id, {})
            additional_info.append({
                'Name': 'MontoISRRetenido',
                'Value': retention.get('MontoISRRetenido', '0.00'),
            })

            # Retenciones extendidas (para doc 41 / 47)
            if doc_type in ('41', '47'):
                additional_info.append({'Name': 'IndicadorAgenteRetencionPercepcion', 'Value': '1'})
                if doc_type == '41':
                    additional_info.append({
                        'Name': 'MontoITBISRetenido',
                        'Value': retention.get('MontoITBISRetenido', '0.00'),
                    })

            item['AdditionalInfo'] = additional_info
            items.append(item)

        return items

    def _digifact_get_totals(self, doc_type, tax_data):
        """Construye el bloque Totals del JSON.
        Los montos se toman directamente de Odoo, no se recalculan.
        TotalTaxableAmount siempre se envía como string formateado.
        Para tipo 47: TotalTaxes usa EXENTO con Amount = InvoiceTotal.
        """
        self.ensure_one()

        product_lines = self.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
        )
        qty_items = len(product_lines)

        totals = {
            'QtyItems': qty_items,
            'TotalTaxableAmount': self._digifact_format_amount(self.amount_untaxed),
        }

        # TotalTaxes: para tipo 47 usa EXENTO
        if doc_type == '47':
            totals['TotalTaxes'] = {
                'TotalTax': [{
                    'Code': 'EXENTO',
                    'Amount': self._digifact_format_amount(self.amount_total),
                }],
            }
        else:
            totals['TotalTaxes'] = {
                'TotalTax': tax_data.get('total_taxes', []),
            }

        totals['GrandTotal'] = {
            'InvoiceTotal': self._digifact_format_amount(self.amount_total),
        }

        # AdditionalInfo en Totals (retenciones para doc 41 / 47)
        if doc_type in ('41', '47'):
            totals_additional = [
                {
                    'Name': 'TotalISRRetencion',
                    'Value': self._digifact_format_amount(tax_data.get('total_isr_retencion', 0.0)),
                },
            ]
            if doc_type == '41':
                totals_additional.append({
                    'Name': 'TotalITBISRetenido',
                    'Value': self._digifact_format_amount(tax_data.get('total_itbis_retenido', 0.0)),
                })
            totals['AdditionalInfo'] = totals_additional

        return totals

    def _digifact_get_additional_doc_info(self, doc_type, tax_data):
        """Construye el bloque AdditionalDocumentInfo del JSON.

        Comportamiento por tipo de documento:
        - Tipos 44, 47: retorna dict vacío {}
        - Tipo 43: bloque especial con NombrePuertoSalida
        - Tipo 46: sin bloque SUBTOTALES; si hay referencia se agrega
        - Otros: bloque SUBTOTALES + bloque INFORMACION_REFERENCIA (si aplica)
        """
        self.ensure_one()

        # Tipos que NO llevan AdditionalDocumentInfo completo
        if doc_type in ('44', '47'):
            return {}

        # Tipo 43: bloque especial hardcoded (según PayloadBuilder original)
        if doc_type == '43':
            return {
                'AdditionalInfo': [{
                    'AditionalData': {
                        'Data': [{
                            'Info': [
                                {'Name': 'NombrePuertoSalida', 'Value': 'Puerto'},
                            ],
                            'Name': '',
                            'Id': 0,
                        }],
                    },
                }],
            }

        data_blocks = []

        # Bloque SUBTOTALES: para todos excepto tipo 46
        if doc_type not in ('46',):
            subtotals_info = [
                {'Name': 'SubTotalMontoGravado1', 'Value': self._digifact_format_amount(self.amount_untaxed)},
                {'Name': 'SubTotalITBIS', 'Value': self._digifact_format_amount(tax_data.get('total_itbis', 0.0))},
            ]

            # SubTotalMontoGravadoTotal
            if doc_type == '41':
                # Para 41: total - retenciones
                grand_total = self.amount_total
                net = grand_total - tax_data.get('total_isr_retencion', 0.0) - tax_data.get('total_itbis_retenido', 0.0)
                subtotals_info.append({
                    'Name': 'SubTotalMontoGravadoTotal',
                    'Value': self._digifact_format_amount(net),
                })
            else:
                subtotals_info.append({
                    'Name': 'SubTotalMontoGravadoTotal',
                    'Value': self._digifact_format_amount(self.amount_total),
                })

            data_blocks.append({
                'Name': 'INFORMACION_REFERENCIA',
                'Info': subtotals_info,
            })

        # Bloque INFORMACION_REFERENCIA para Notas Crédito/Débito (33, 34)
        if doc_type in ('33', '34'):
            ref_invoice = self._digifact_get_ref_invoice()
            ref_info = [
                {
                    'Name': 'FechaNCFModificado',
                    'Value': ref_invoice.invoice_date.strftime('%Y-%m-%d') if ref_invoice and ref_invoice.invoice_date else '',
                },
                {
                    'Name': 'NCFModificado',
                    'Value': (ref_invoice.l10n_do_fiscal_number or ref_invoice.l10n_latam_document_number or '') if ref_invoice else '',
                },
                {
                    'Name': 'CodigoModificacion',
                    'Value': self.l10n_do_ecf_modification_code or '',
                },
            ]
            data_blocks.append({
                'Info': ref_info,
                'Name': 'INFORMACION_REFERENCIA',
            })

        return {
            'AdditionalInfo': [{
                'AditionalData': {
                    'Data': data_blocks,
                },
            }],
        }

    def _digifact_get_payments(self, doc_type, tax_data):
        """Construye el bloque Payments del JSON.
        Para doc 41: monto neto = total - ISR retenido - ITBIS retenido.
        Para otros: amount_untaxed.
        """
        self.ensure_one()

        if doc_type == '41':
            net_amount = (
                self.amount_total
                - tax_data.get('total_isr_retencion', 0.0)
                - tax_data.get('total_itbis_retenido', 0.0)
            )
            amount = self._digifact_format_amount(net_amount)
        else:
            amount = self._digifact_format_amount(self.amount_untaxed)

        return [{
            'Code': self.l10n_do_payment_type or '1',
            'Amount': amount,
        }]

    # =========================================================================
    # CONSTRUCTOR PRINCIPAL DEL PAYLOAD
    # =========================================================================

    def _build_digifact_payload(self):
        """Construye el dict completo del payload DigiFact para esta factura.
        Este JSON es el que se envía al endpoint POST /EcfController/GenerarComprobante.

        Returns:
            dict: Payload completo listo para serializar a JSON.
        """
        self.ensure_one()

        doc_type = self._digifact_get_doc_type()

        # Validaciones previas
        if not self.name or self.name == '/':
            raise UserError(_(
                'La factura debe tener un nombre válido (NumeroFacturaInterna) antes de generar el JSON.'
            ))

        if doc_type in ('33', '34') and not self.l10n_do_ecf_modification_code:
            raise UserError(_(
                'Las Notas de Crédito/Débito (E33/E34) requieren un Código de Modificación.'
            ))

        # Extraer totales de impuestos una sola vez
        tax_data = self._digifact_get_tax_totals(doc_type)

        # Flag de ambiente (producción / test)
        is_live_flag = '1' if getattr(self.company_id, 'is_live', False) else '0'

        payload = {
            'live': is_live_flag,
            'Version': '1.0',
            'CountryCode': 'DO',
            'IdUser': self.env.user.id,
            'TaxId': self.company_id.vat or '',
            'Header': self._digifact_get_header(doc_type),
            'Seller': self._digifact_get_seller(doc_type),
            'Buyer': self._digifact_get_buyer(doc_type),
            'Items': self._digifact_get_items(doc_type, tax_data),
            'Totals': self._digifact_get_totals(doc_type, tax_data),
            'Payments': self._digifact_get_payments(doc_type, tax_data),
            'AdditionalDocumentInfo': self._digifact_get_additional_doc_info(doc_type, tax_data),
        }

        return payload

    # =========================================================================
    # ACCIÓN PARA EL WIZARD DE PREVISUALIZACIÓN
    # =========================================================================

    def action_preview_digifact_json(self):
        """Abre el wizard mostrando el JSON generado para esta factura."""
        self.ensure_one()

        payload = self._build_digifact_payload()
        json_str = json.dumps(payload, indent=4, ensure_ascii=False)

        wizard = self.env['digifact.preview.wizard'].create({
            'move_id': self.id,
            'json_preview': json_str,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'JSON e-CF: %s' % (self.name or ''),
            'res_model': 'digifact.preview.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }
