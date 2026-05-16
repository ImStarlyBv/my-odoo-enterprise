from odoo import models, fields, _
from odoo.exceptions import ValidationError


class AccountFiscalSequenceValidateWizard(models.TransientModel):
    """Wizard de confirmación para cambios de estado en secuencias fiscales.

    Muestra al usuario un mensaje de advertencia antes de confirmar o cancelar
    una secuencia fiscal. El contexto debe incluir ``action`` con valor
    ``"confirm"`` o ``"cancel"`` para determinar qué método ejecutar sobre
    la secuencia.
    """

    _name = "account.fiscal.sequence.validate_wizard"
    _description = "Validación de Cambio de Estado en Secuencia Fiscal"

    name = fields.Char(
        string="Mensaje",
        help="Texto de advertencia que se muestra al usuario antes de confirmar.",
    )
    fiscal_sequence_id = fields.Many2one(
        comodel_name="account.fiscal.sequence",
        string="Secuencia Fiscal",
    )

    def confirm_cancel(self):
        """Ejecuta la acción indicada en el contexto sobre la secuencia fiscal.

        Lee ``action`` del contexto: ``"confirm"`` llama a ``_action_confirm()``;
        ``"cancel"`` llama a ``_action_cancel()``.

        :raises ValidationError: si no hay secuencia fiscal vinculada.
        """
        self.ensure_one()
        if not self.fiscal_sequence_id:
            raise ValidationError(
                _("There is no Fiscal Sequence to perform this action.")
            )
        action = self._context.get("action", False)
        if action == "confirm":
            self.fiscal_sequence_id._action_confirm()
        elif action == "cancel":
            self.fiscal_sequence_id._action_cancel()
