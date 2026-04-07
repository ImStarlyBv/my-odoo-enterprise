from odoo import models, fields

class DigifactPreviewWizard(models.TransientModel):
    _name = 'digifact.preview.wizard'
    _description = 'Wizard de Previsualización del JSON e-CF'

    move_id = fields.Many2one('account.move', string='Factura')
    json_preview = fields.Text(string='Cuerpo del JSON (e-CF)', readonly=True)

    def action_send_to_digifact(self):
        """
        Futuro método para enviar el JSON a la API de Digifact.
        Por ahora, al apretar el botón, solo lo cierra.
        """
        # Aquí se armaría la cabecera HTTP y se dispararía el request a la URL correspondiente.
        pass
