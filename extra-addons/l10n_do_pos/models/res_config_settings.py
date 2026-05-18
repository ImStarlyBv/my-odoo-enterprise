from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    """Expone los campos fiscales RD de pos.config en la pantalla de ajustes del POS."""
    _inherit = 'res.config.settings'

    l10n_do_is_fiscal = fields.Boolean(
        related='pos_config_id.l10n_do_is_fiscal',
        readonly=True,
    )
    l10n_do_default_consumer_partner_id = fields.Many2one(
        comodel_name='res.partner',
        related='pos_config_id.l10n_do_default_consumer_partner_id',
        readonly=False,
    )
    l10n_do_allow_vendor_ncf = fields.Boolean(
        related='pos_config_id.l10n_do_allow_vendor_ncf',
        readonly=False,
    )
    l10n_do_vendor_ncf_journal_id = fields.Many2one(
        comodel_name='account.journal',
        related='pos_config_id.l10n_do_vendor_ncf_journal_id',
        readonly=False,
    )
    l10n_do_order_history_type = fields.Selection(
        related='pos_config_id.l10n_do_order_history_type',
        readonly=False,
    )
    l10n_do_order_history_days = fields.Integer(
        related='pos_config_id.l10n_do_order_history_days',
        readonly=False,
    )
