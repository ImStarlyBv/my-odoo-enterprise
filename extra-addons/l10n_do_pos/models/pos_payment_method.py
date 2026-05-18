from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PosPaymentMethod(models.Model):
    """
    Agrega el campo is_credit_note para identificar el método de pago
    especial que permite aplicar notas de crédito como medio de pago en el POS.

    Restricciones:
    - split_transactions debe estar activo (el sistema necesita identificar el partner)
    - No debe tener journal_id (la NC no genera un nuevo movimiento bancario)
    """
    _inherit = 'pos.payment.method'

    is_credit_note = fields.Boolean(
        string='Nota de Crédito',
        help='Activa este método para permitir pagar con notas de crédito dominicanas.',
    )

    @api.model
    def _load_pos_data_fields(self, config_id):
        result = super()._load_pos_data_fields(config_id)
        result.append('is_credit_note')
        return result

    @api.constrains('is_credit_note', 'split_transactions', 'journal_id')
    def _check_is_credit_note(self):
        for rec in self:
            if rec.is_credit_note:
                if not rec.split_transactions:
                    raise ValidationError(_(
                        '"Identificar cliente" debe estar activo en el método '
                        'de pago Nota de Crédito.'
                    ))
                if rec.journal_id:
                    raise ValidationError(_(
                        'El método de pago Nota de Crédito no debe tener diario.'
                    ))
