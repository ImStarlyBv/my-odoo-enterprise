from odoo import api, models, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    """
    Expone campos fiscales dominicanos del partner al frontend del POS
    y protege al partner consumidor por defecto de ser eliminado.
    """
    _inherit = 'res.partner'

    @api.model
    def _load_pos_data_fields(self, config_id):
        result = super()._load_pos_data_fields(config_id)
        result += ['vat', 'l10n_do_dgii_tax_payer_type']
        return result

    def unlink(self):
        """Bloquea la eliminación del partner consumidor por defecto del POS."""
        consumer = self.env.ref('l10n_do_pos.default_pos_partner', raise_if_not_found=False)
        if consumer and consumer in self:
            raise UserError(_('No puedes eliminar el cliente consumidor por defecto del POS.'))
        return super().unlink()
