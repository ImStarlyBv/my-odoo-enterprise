from odoo import models


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def create(self, vals):
        if isinstance(vals, list):
            for v in vals:
                v['to_buy'] = False
        else:
            vals['to_buy'] = False
        return super().create(vals)

    def write(self, vals):
        vals['to_buy'] = False
        return super().write(vals)
