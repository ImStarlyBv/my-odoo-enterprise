from odoo import api, models, _
from odoo.exceptions import ValidationError


class AccountFiscalType(models.Model):
    _inherit = ['account.fiscal.type', 'pos.load.mixin']
    _name = 'account.fiscal.type'

    @api.model
    def _load_pos_data_domain(self, data):
        return [('active', '=', True), ('type', 'in', ('out_invoice', 'out_refund'))]

    @api.model
    def _load_pos_data_fields(self, config_id):
        return ['id', 'name', 'requires_document', 'fiscal_position_id', 'prefix', 'type']

    def get_active_sessions(self):
        self.ensure_one()
        return self.env['pos.session'].sudo().search([
            ('state', '!=', 'closed'),
            ('pos_config_id.l10n_do_fiscal_journal', '=', True),
        ])

    def get_pos_config_names(self, pos_sessions):
        self.ensure_one()
        pos_configs = pos_sessions.mapped('config_id')
        return ', '.join(pos_configs.mapped('name'))

    def write(self, vals):
        if 'active' in vals and vals['active'] is False:
            for fiscal_type in self:
                pos_sessions = fiscal_type.get_active_sessions()
                if pos_sessions:
                    raise ValidationError(
                        _('You cannot archive a fiscal type that is currently in use by active POS sessions: %s') % fiscal_type.get_pos_config_names(pos_sessions))
        return super(AccountFiscalType, self).write(vals)
