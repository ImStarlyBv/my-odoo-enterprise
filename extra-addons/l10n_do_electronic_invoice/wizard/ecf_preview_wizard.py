from odoo import models, fields


class EcfPreviewWizard(models.TransientModel):
    _name = 'l10n_do.ecf.preview.wizard'
    _description = 'Previsualización del JSON e-CF'

    move_id = fields.Many2one('account.move', string='Factura')
    json_preview = fields.Text(string='Cuerpo del JSON (e-CF)', readonly=True)

    def action_send_ecf(self):
        """Placeholder para el envío al API del proveedor de e-CF."""
        pass
