from odoo import models, fields


class EcfPreviewWizard(models.TransientModel):
    _name = 'l10n_do.ecf.preview.wizard'
    _description = 'Previsualización del JSON e-CF'

    move_id = fields.Many2one('account.move', string='Factura')
    json_preview = fields.Text(string='Cuerpo del JSON (e-CF)', readonly=True)

    def action_send_ecf(self):
        """Delega el envío al método del modelo y cierra el wizard."""
        self.ensure_one()
        self.move_id.action_send_ecf()
        return {'type': 'ir.actions.act_window_close'}
