from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.osv.expression import AND
from datetime import timedelta


class PosOrder(models.Model):
    """
    Extiende pos.order con campos NCF/eCF para el POS fiscal dominicano.

    El NCF NO se pre-genera en el frontend. Se asigna al confirmar la
    account.move (action_post), momento en que la secuencia del diario
    asigna el número automáticamente. Luego se lee de vuelta y se guarda
    aquí para mostrarlo en el recibo.

    Para e-CF (prefijo E3x): si `l10n_do_electronic_invoice` está instalado
    y `pos.config.l10n_do_ecf_auto_send = True`, la factura se envía a la
    DGII automáticamente. El QR y código de seguridad se leen vía polling.
    """
    _inherit = 'pos.order'

    l10n_latam_document_type_id = fields.Many2one(
        comodel_name='l10n_latam.document.type',
        string='Tipo de comprobante',
    )
    l10n_do_fiscal_number = fields.Char(
        string='NCF',
        copy=False,
        help='Número de comprobante fiscal asignado por la secuencia del diario.',
    )
    l10n_do_origin_ncf = fields.Char(
        string='NCF afectado',
        copy=False,
        help='NCF de la orden original cuando esta orden es una nota de crédito (B04/E34).',
    )
    l10n_do_ncf_expiration_date = fields.Date(
        string='Vence NCF',
        copy=False,
    )

    # ---------------------------------------------------------------------------
    # Helpers internos
    # ---------------------------------------------------------------------------

    def _l10n_do_ecf_module_installed(self):
        """Devuelve True si l10n_do_electronic_invoice está instalado."""
        return self.env['ir.module.module'].sudo().search_count([
            ('name', '=', 'l10n_do_electronic_invoice'),
            ('state', '=', 'installed'),
        ]) > 0

    def _read_ecf_data(self, invoice):
        """
        Lee los campos de e-CF de la factura de forma segura (getattr con
        default) para no romper cuando el módulo no está instalado.

        :param invoice: account.move record
        :return: dict con ecf_qr_image, ecf_codigo_seguridad, is_ecf
        """
        return {
            'is_ecf': bool(getattr(invoice, 'is_ecf_invoice', False)),
            'ecf_qr_image': getattr(invoice, 'ecf_qr_image', False) or False,
            'ecf_codigo_seguridad': getattr(invoice, 'ecf_codigo_seguridad', False) or False,
        }

    # ---------------------------------------------------------------------------
    # Facturación
    # ---------------------------------------------------------------------------

    def _prepare_invoice_vals(self):
        """
        Pasa los datos fiscales dominicanos a la factura que se creará.
        l10n_latam_manual_document_number = False para que la secuencia
        del diario asigne el NCF automáticamente.
        """
        invoice_vals = super()._prepare_invoice_vals()
        if self.config_id.l10n_do_is_fiscal:
            invoice_vals.update({
                'l10n_latam_document_type_id': self.l10n_latam_document_type_id.id,
                'l10n_latam_manual_document_number': False,
            })
            if self.l10n_do_origin_ncf:
                invoice_vals['l10n_do_origin_ncf'] = self.l10n_do_origin_ncf
        return invoice_vals

    def _process_saved_order(self, draft):
        """
        Fuerza to_invoice = True en POS fiscal para que toda venta genere
        una account.move. El partner consumidor por defecto se asigna si la
        orden no tiene cliente.
        """
        if (
            not draft
            and self.state != 'invoiced'
            and self.amount_total != 0
            and self.config_id.l10n_do_is_fiscal
        ):
            if not self.partner_id:
                consumer = self.config_id.l10n_do_default_consumer_partner_id
                if not consumer:
                    raise UserError(_(
                        'Este punto de venta no tiene un cliente consumidor por '
                        'defecto. Configure uno en los ajustes del POS.'
                    ))
                self.write({'partner_id': consumer.id})
            self.write({'to_invoice': True})
        return super()._process_saved_order(draft)

    def _finalize_fiscal_order(self):
        """
        Crea la factura sincrónicamente y lee el NCF asignado por la secuencia.
        Si el NCF es e-CF (prefijo E) y `l10n_do_ecf_auto_send` está activo,
        envía la factura a la DGII vía `action_send_ecf()`.

        Llamado desde PaymentScreen._finalizeValidation() después de que super
        guarda la orden al servidor. El frontend usa el resultado para poblar
        la orden local y re-renderizar el recibo reactivamente.

        :return: dict con l10n_do_fiscal_number, l10n_do_ncf_expiration_date,
                 l10n_latam_document_type_id, is_ecf, ecf_qr_image,
                 ecf_codigo_seguridad, ecf_pending
        """
        self.ensure_one()

        # Si la factura ya existe (creada por _process_saved_order), no recrear
        if not self.account_move_ids:
            self.write({'to_invoice': True})
            self._generate_pos_order_invoice()

        invoice = self.account_move_ids[:1]

        if invoice and invoice.l10n_do_fiscal_number:
            self.write({
                'l10n_do_fiscal_number': invoice.l10n_do_fiscal_number,
                'l10n_do_ncf_expiration_date': invoice.l10n_do_ncf_expiration_date,
                'l10n_latam_document_type_id': invoice.l10n_latam_document_type_id.id,
            })

        ecf_data = self._read_ecf_data(invoice) if invoice else {
            'is_ecf': False, 'ecf_qr_image': False, 'ecf_codigo_seguridad': False,
        }

        # Enviar e-CF si el módulo está instalado y el auto-envío está activo
        ecf_pending = False
        if (
            ecf_data['is_ecf']
            and self.config_id.l10n_do_ecf_auto_send
            and self._l10n_do_ecf_module_installed()
            and invoice
            and hasattr(invoice, 'action_send_ecf')
        ):
            invoice.action_send_ecf()
            # Re-leer los datos eCF después del envío
            ecf_data = self._read_ecf_data(invoice)
            ecf_pending = not ecf_data['ecf_qr_image']

        return {
            'l10n_do_fiscal_number': self.l10n_do_fiscal_number,
            'l10n_do_ncf_expiration_date': (
                str(self.l10n_do_ncf_expiration_date)
                if self.l10n_do_ncf_expiration_date else False
            ),
            'l10n_latam_document_type_id': self.l10n_latam_document_type_id.id,
            'is_ecf': ecf_data['is_ecf'],
            'ecf_qr_image': ecf_data['ecf_qr_image'],
            'ecf_codigo_seguridad': ecf_data['ecf_codigo_seguridad'],
            'ecf_pending': ecf_pending,
        }

    # ---------------------------------------------------------------------------
    # Polling e-CF
    # ---------------------------------------------------------------------------

    @api.model
    def poll_ecf_status(self, order_id):
        """
        Verifica si el QR del e-CF ya está disponible en la factura.
        Llamado desde el frontend en intervalos cortos tras `_finalize_fiscal_order`.

        :param order_id: int — ID del pos.order
        :return: dict {ready, ecf_qr_image, ecf_codigo_seguridad}
        """
        order = self.browse(order_id)
        invoice = order.account_move_ids[:1]
        if not invoice:
            return {'ready': False, 'ecf_qr_image': False, 'ecf_codigo_seguridad': False}

        ecf_data = order._read_ecf_data(invoice)
        return {
            'ready': bool(ecf_data['ecf_qr_image']),
            'ecf_qr_image': ecf_data['ecf_qr_image'],
            'ecf_codigo_seguridad': ecf_data['ecf_codigo_seguridad'],
        }

    @api.model
    def get_ecf_receipt_data(self, order_id):
        """
        Retorna los datos de e-CF para reimpresión del recibo.
        :param order_id: int — ID del pos.order
        :return: dict con ecf_qr_image, ecf_codigo_seguridad, is_ecf
        """
        order = self.browse(order_id)
        invoice = order.account_move_ids[:1]
        if not invoice:
            return {'is_ecf': False, 'ecf_qr_image': False, 'ecf_codigo_seguridad': False}
        return order._read_ecf_data(invoice)

    # ---------------------------------------------------------------------------
    # Notas de Crédito
    # ---------------------------------------------------------------------------

    @api.model
    def register_vendor_ncf(self, config_id, vendor_data):
        """
        Crea un borrador de account.move tipo in_invoice para un NCF de proveedor
        registrado desde el POS. La factura queda en borrador para que el contador
        la revise, asigne cuentas contables y la confirme.

        :param config_id: int — ID del pos.config activo
        :param vendor_data: dict con ncf (str), vendor_rnc (str), amount (float)
        :return: dict {move_id, move_name, partner_name}
        :raises UserError: si el diario de proveedor no está configurado
        """
        config = self.env['pos.config'].browse(config_id)
        if not config.l10n_do_vendor_ncf_journal_id:
            raise UserError(_(
                'El POS no tiene un diario de proveedor configurado para registrar NCF. '
                'Configúralo en los ajustes del POS.'
            ))

        journal = config.l10n_do_vendor_ncf_journal_id
        ncf = (vendor_data.get('ncf') or '').strip().upper()
        vendor_rnc = (vendor_data.get('vendor_rnc') or '').replace('-', '').strip()
        amount = float(vendor_data.get('amount') or 0.0)

        # Buscar proveedor por RNC en la BD
        partner_id = False
        if vendor_rnc:
            partner = self.env['res.partner'].search([
                ('vat', '=', vendor_rnc),
                ('company_id', 'in', [False, self.env.company.id]),
            ], limit=1)
            if partner:
                partner_id = partner.id

        # Buscar tipo de documento cuyo prefijo coincida con el NCF
        doc_type_id = False
        for jdt in journal.l10n_do_document_type_ids:
            prefix = jdt.l10n_latam_document_type_id.doc_code_prefix or ''
            if prefix and ncf.startswith(prefix):
                doc_type_id = jdt.l10n_latam_document_type_id.id
                break

        move_vals = {
            'move_type': 'in_invoice',
            'journal_id': journal.id,
            'partner_id': partner_id,
            'l10n_latam_manual_document_number': True,
            'l10n_do_fiscal_number': ncf,
            'l10n_do_pos_vendor_ncf': True,
            'invoice_line_ids': [(0, 0, {
                'name': _('Compra registrada desde POS — NCF %s') % ncf,
                'quantity': 1,
                'price_unit': amount,
            })],
        }
        if doc_type_id:
            move_vals['l10n_latam_document_type_id'] = doc_type_id

        move = self.env['account.move'].create(move_vals)

        return {
            'move_id': move.id,
            'move_name': move.name,
            'partner_name': move.partner_id.name if move.partner_id else _('Sin proveedor'),
        }

    def get_credit_note(self, ncf):
        """
        Busca una nota de crédito dominicana activa por su NCF.
        :param ncf: str — número de comprobante de la NC (e.g. 'B0400000001')
        :return: dict con partner_id, residual_amount, ncf
        :raises UserError: si no existe la NC
        """
        credit_note = self.env['account.move'].search([
            ('l10n_do_fiscal_number', '=', ncf),
            ('move_type', '=', 'out_refund'),
            ('company_id', '=', self.env.company.id),
            ('state', '=', 'posted'),
        ], limit=1)
        if not credit_note:
            raise UserError(_('Nota de crédito no encontrada: %s') % ncf)
        return {
            'partner_id': credit_note.partner_id.id,
            'residual_amount': credit_note.amount_residual,
            'ncf': credit_note.l10n_do_fiscal_number,
        }

    def get_credit_notes(self, partner_id):
        """
        Lista las notas de crédito disponibles (saldo > 0) de un cliente.
        :param partner_id: int — ID del res.partner
        :return: list de dicts [{id, label, item}]
        :raises UserError: si el cliente no tiene NCs disponibles
        """
        credit_notes = self.env['account.move'].search([
            ('partner_id', '=', partner_id),
            ('move_type', '=', 'out_refund'),
            ('l10n_do_fiscal_number', '!=', False),
            ('amount_residual', '>', 0.0),
            ('company_id', '=', self.env.company.id),
            ('state', '=', 'posted'),
        ])
        if not credit_notes:
            raise UserError(_('Este cliente no tiene notas de crédito disponibles.'))
        return [{
            'id': cn.id,
            'label': '%s - %s %s' % (
                cn.l10n_do_fiscal_number,
                cn.currency_id.name,
                cn.amount_residual,
            ),
            'item': {
                'partner_id': cn.partner_id.id,
                'residual_amount': cn.amount_residual,
                'ncf': cn.l10n_do_fiscal_number,
            },
        } for cn in credit_notes]

    # ---------------------------------------------------------------------------
    # Historial de órdenes
    # ---------------------------------------------------------------------------

    @api.model
    def search_paid_order_ids(self, config_id, domain, limit, offset):
        """
        Filtra el historial de órdenes en POS fiscal:
        - Solo muestra órdenes con NCF asignado
        - Respeta el límite de días configurado en el POS
        - Excluye órdenes borrador y canceladas
        """
        pos_config = self.env['pos.config'].browse(config_id)
        if not pos_config.l10n_do_is_fiscal:
            return super().search_paid_order_ids(config_id, domain, limit, offset)

        fiscal_config_ids = self.env['pos.config'].search([
            ('l10n_do_is_fiscal', '=', True),
        ]).ids

        fiscal_domain = [
            ('config_id', 'in', fiscal_config_ids),
            ('l10n_do_fiscal_number', '!=', False),
            ('amount_total', '>', 0),
            ('state', 'not in', ['draft', 'cancel']),
        ]

        if pos_config.l10n_do_order_history_type == 'days':
            since = fields.Datetime.now() - timedelta(
                days=pos_config.l10n_do_order_history_days
            )
            fiscal_domain.append(('create_date', '>=', since))

        real_domain = AND([domain, fiscal_domain])
        ids = self.search(real_domain, limit=limit, offset=offset).ids
        total_count = self.search_count(real_domain)
        return {'ids': ids, 'totalCount': total_count}
