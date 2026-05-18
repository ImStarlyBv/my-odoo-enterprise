from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PosConfig(models.Model):
    """
    Extiende pos.config con campos fiscales RD (NCF/eCF).

    Un POS se considera "fiscal" cuando su diario de facturación tiene tipos
    de documento dominicanos asignados (l10n_do_document_type_ids). No se
    requiere un booleano manual: se computa desde el diario.
    """
    _inherit = 'pos.config'

    l10n_do_is_fiscal = fields.Boolean(
        string='POS Fiscal RD',
        compute='_compute_l10n_do_is_fiscal',
        store=True,
        help='True cuando el diario de facturación tiene tipos NCF/eCF dominicanos.',
    )
    l10n_do_default_consumer_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Cliente consumidor por defecto',
        default=lambda self: self.env.ref(
            'l10n_do_pos.default_pos_partner', raise_if_not_found=False
        ),
        help='Partner usado para ventas B02/E32 sin cliente identificado.',
    )
    l10n_do_allow_vendor_ncf = fields.Boolean(
        string='Permitir registro de NCF proveedor',
        default=False,
        help='Habilita el botón para registrar comprobantes de proveedor desde el POS.',
    )
    l10n_do_vendor_ncf_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario NCF proveedor',
        domain=[('type', '=', 'purchase')],
        help='Diario donde se crearán los borradores de facturas de proveedor.',
    )
    l10n_do_order_history_type = fields.Selection(
        selection=[
            ('all', 'Todas las órdenes'),
            ('days', 'Por días'),
        ],
        string='Límite de historial',
        default='all',
        help='Controla cuántas órdenes se muestran en el historial del POS.',
    )
    l10n_do_order_history_days = fields.Integer(
        string='Días de historial',
        default=30,
    )
    l10n_do_ecf_auto_send = fields.Boolean(
        string='Enviar e-CF automáticamente',
        default=True,
        help=(
            'Si está activo, los comprobantes electrónicos (E3x) se envían '
            'a la DGII automáticamente al confirmar la orden. '
            'Requiere que el módulo l10n_do_electronic_invoice esté instalado.'
        ),
    )

    @api.depends('invoice_journal_id.l10n_do_document_type_ids')
    def _compute_l10n_do_is_fiscal(self):
        """Un POS es fiscal cuando su diario tiene tipos de documento dominicanos."""
        for config in self:
            config.l10n_do_is_fiscal = bool(
                config.invoice_journal_id.l10n_do_document_type_ids
            )

    @api.constrains('l10n_do_allow_vendor_ncf', 'l10n_do_vendor_ncf_journal_id')
    def _check_vendor_ncf_journal(self):
        """El diario de proveedor es obligatorio cuando se habilita el registro de NCF proveedor."""
        for rec in self:
            if rec.l10n_do_allow_vendor_ncf and not rec.l10n_do_vendor_ncf_journal_id:
                raise ValidationError(_(
                    'Debes seleccionar un diario de proveedor cuando '
                    '"Permitir registro de NCF proveedor" está activado.'
                ))

    @api.constrains('l10n_do_order_history_days')
    def _check_order_history_days(self):
        for rec in self:
            if rec.l10n_do_order_history_type == 'days' and rec.l10n_do_order_history_days <= 0:
                raise ValidationError(_('Los días del historial deben ser mayores a 0.'))
