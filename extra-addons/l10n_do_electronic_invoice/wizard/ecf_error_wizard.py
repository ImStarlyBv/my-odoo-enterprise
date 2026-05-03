from odoo import models, fields


class EcfErrorWizard(models.TransientModel):
    _name = 'l10n_do.ecf.error.wizard'
    _description = 'Última respuesta de la API ECF'

    move_id = fields.Many2one('account.move', readonly=True)
    api_response = fields.Text(string='Respuesta de la API', readonly=True)
