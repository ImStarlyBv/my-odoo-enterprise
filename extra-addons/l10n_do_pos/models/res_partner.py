# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError

class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _load_pos_data_fields(self, config_id):
        result = super()._load_pos_data_fields(config_id)
        result.append('sale_fiscal_type_id')
        return result

    def unlink(self):
        pos_consumer_partner_id = self.env.ref('l10n_do_pos.default_pos_partner').id
        if self.filtered(lambda p: p.id == pos_consumer_partner_id):
            raise UserError(_("You can't delete this partner."))
        return super(ResPartner, self).unlink()