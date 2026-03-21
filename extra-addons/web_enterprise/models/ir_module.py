from odoo import models


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def write(self, vals):
        vals['to_buy'] = False
        return super().write(vals)
