# © 2019 José López <jlopez@indexa.do>
# © 2019 Raul Ovalle <rovalle@guavana.com>

import pytz
from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


def get_l10n_do_datetime():
    """
    Retorna el datetime actual en la zona horaria de República Dominicana
    (America/Santo_Domingo), independientemente del timezone del servidor
    o del usuario. Se usa para lógica de expiración automática de secuencias.
    """
    return pytz.timezone("America/Santo_Domingo").localize(datetime.now())


class AccountFiscalSequence(models.Model):
    """
    Secuencia de comprobantes fiscales para República Dominicana.

    Representa una autorización de rango de NCF emitida por la DGII
    (ej. del B0100000001 al B0100000500). Gestiona el estado del rango
    (borrador → activo → agotado/expirado) y genera números fiscales
    incrementales mediante ``get_fiscal_number()``.

    Hereda ``mail.thread`` y ``mail.activity.mixin`` para trazabilidad
    de cambios de estado.

    Nota Odoo 18: los campos editables solo en estado ``draft`` se controlan
    mediante ``readonly="state != 'draft'"`` en las vistas XML. El modelo
    no usa el atributo ``states={}`` (deprecado desde Odoo 17).
    """

    _name = "account.fiscal.sequence"
    _description = "Account Fiscal Sequence"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(
        string="Authorization number",
        required=True,
        tracking=True,
    )
    expiration_date = fields.Date(
        string="Expiration Date",
        required=True,
        tracking=True,
        default=datetime.strptime(
            str(int(str(fields.Date.today())[0:4]) + 1) + "-12-31", "%Y-%m-%d"
        ).date(),
    )
    fiscal_type_id = fields.Many2one(
        comodel_name="account.fiscal.type",
        string="Fiscal type",
        required=True,
        tracking=True,
    )
    type = fields.Selection(
        related="fiscal_type_id.type",
        store=True,
    )
    sequence_start = fields.Integer(
        string="Start",
        required=True,
        tracking=True,
        default=1,
        copy=False,
    )
    sequence_end = fields.Integer(
        string="End",
        required=True,
        tracking=True,
        default=1,
        copy=False,
    )
    sequence_remaining = fields.Integer(
        string="Remaining",
        compute="_compute_sequence_remaining",
    )
    # Referencia a ir.sequence interna; solo lectura, gestionada por el modelo.
    sequence_id = fields.Many2one(
        comodel_name="ir.sequence",
        string="Internal Sequence",
        readonly=True,
        copy=False,
    )
    warning_gap = fields.Integer(
        compute="_compute_warning_gap",
    )
    remaining_percentage = fields.Float(
        default=35,
        required=True,
        help=(
            "Fiscal Sequence remaining percentage to reach to start "
            "warning notifications."
        ),
    )
    number_next_actual = fields.Integer(
        string="Next Number",
        help="Next number of this sequence",
    )
    next_fiscal_number = fields.Char(
        compute="_compute_next_fiscal_number",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("queue", "Queue"),
            ("active", "Active"),
            ("depleted", "Depleted"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        tracking=True,
        copy=False,
    )
    can_be_queue = fields.Boolean(
        compute="_compute_can_be_queue",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
        tracking=True,
    )

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    @api.depends("state")
    def _compute_can_be_queue(self):
        """
        True si la secuencia puede ponerse en cola: solo cuando está en borrador
        y ya existe exactamente una secuencia activa o en cola para el mismo tipo
        fiscal y compañía (evita tener más de una en cola).
        """
        for rec in self:
            rec.can_be_queue = (
                bool(
                    2
                    > self.search_count(
                        [
                            ("state", "in", ("active", "queue")),
                            ("fiscal_type_id", "=", rec.fiscal_type_id.id),
                            ("company_id", "=", rec.company_id.id),
                        ]
                    )
                    > 0
                )
                if rec.state == "draft"
                else False
            )

    @api.depends("remaining_percentage")
    def _compute_warning_gap(self):
        """Cantidad de comprobantes restantes que dispara la alerta de bajo stock."""
        for rec in self:
            rec.warning_gap = (rec.sequence_end - (rec.sequence_start - 1)) * (
                rec.remaining_percentage / 100
            )

    @api.depends("sequence_end", "number_next_actual")
    def _compute_sequence_remaining(self):
        """Comprobantes restantes en el rango autorizado."""
        for rec in self:
            rec.sequence_remaining = rec.sequence_end - rec.number_next_actual + 1

    @api.depends("fiscal_type_id.prefix", "fiscal_type_id.padding", "number_next_actual")
    def _compute_next_fiscal_number(self):
        """NCF completo del próximo comprobante a emitir (prefijo + número con padding)."""
        for seq in self:
            seq.next_fiscal_number = "%s%s" % (
                seq.fiscal_type_id.prefix,
                str(seq.number_next_actual).zfill(seq.fiscal_type_id.padding),
            )

    def _compute_display_name(self):
        """Nombre visible: número de autorización — tipo fiscal."""
        for sequence in self:
            sequence.display_name = "%s - %s" % (
                sequence.name,
                sequence.fiscal_type_id.name,
            )

    # ------------------------------------------------------------------
    # Onchange
    # ------------------------------------------------------------------

    @api.onchange("fiscal_type_id")
    def _onchange_fiscal_type_id(self):
        """
        Al cambiar el tipo fiscal en borrador, propone el inicio de secuencia
        como el número siguiente al último rango usado (activo o agotado).
        """
        if self.fiscal_type_id and self.state == "draft":
            last_seq = self.search(
                [
                    ("fiscal_type_id", "=", self.fiscal_type_id.id),
                    ("state", "in", ("depleted", "active")),
                    ("company_id", "=", self.company_id.id),
                ],
                order="sequence_end desc",
                limit=1,
            )
            self.sequence_start = last_seq.sequence_end + 1 if last_seq else 1

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    @api.constrains("fiscal_type_id", "state")
    def _validate_unique_active_type(self):
        """Solo puede existir una secuencia activa por tipo fiscal y compañía."""
        domain = [
            ("state", "=", "active"),
            ("fiscal_type_id", "=", self.fiscal_type_id.id),
            ("company_id", "=", self.company_id.id),
        ]
        if self.search_count(domain) > 1:
            raise ValidationError(_("Another sequence is active for this type."))

    @api.constrains("sequence_start", "sequence_end", "state", "fiscal_type_id", "company_id")
    def _validate_sequence_range(self):
        """
        Valida que el rango sea positivo, que end > start, y que no se solape
        con rangos activos o en cola para el mismo tipo fiscal y compañía.
        """
        for rec in self.filtered(lambda s: s.state != "cancelled"):
            if any(v <= 0 for v in [rec.sequence_start, rec.sequence_end]):
                raise ValidationError(_("Sequence values must be greater than zero."))
            if rec.sequence_start >= rec.sequence_end:
                raise ValidationError(
                    _("End sequence must be greater than start sequence.")
                )
            domain = [
                ("sequence_start", ">=", rec.sequence_start),
                ("sequence_end", "<=", rec.sequence_end),
                ("fiscal_type_id", "=", rec.fiscal_type_id.id),
                ("state", "in", ("active", "queue")),
                ("company_id", "=", rec.company_id.id),
            ]
            if self.search_count(domain) > 1:
                raise ValidationError(
                    _("You cannot use another Fiscal Sequence range.")
                )

    # ------------------------------------------------------------------
    # CRUD overrides
    # ------------------------------------------------------------------

    def unlink(self):
        """Elimina también la ir.sequence interna si existe."""
        for rec in self:
            if rec.sequence_id:
                rec.sequence_id.sudo().unlink()
        return super().unlink()

    def copy(self, default=None):
        """La duplicación de secuencias fiscales no está permitida."""
        if default != 'etc':
            raise UserError(_("You cannot duplicate a Fiscal Sequence."))
        return super().copy(default=default)

    # ------------------------------------------------------------------
    # Actions (UI)
    # ------------------------------------------------------------------

    def action_view_sequence(self):
        """Abre el formulario de la ir.sequence interna asociada."""
        self.ensure_one()
        sequence_id = self.sequence_id
        action = self.env.ref("base.ir_sequence_form").read()[0]
        if sequence_id:
            action["views"] = [(self.env.ref("base.sequence_view").id, "form")]
            action["res_id"] = sequence_id.id
        else:
            action = {"type": "ir.actions.act_window_close"}
        return action

    def action_confirm(self):
        """
        Abre el wizard de confirmación antes de activar la secuencia.
        Una vez confirmada, la secuencia ya no puede editarse.
        """
        self.ensure_one()
        msg = _(
            "Are you sure want to confirm this Fiscal Sequence? "
            "Once you confirm this Fiscal Sequence cannot be edited."
        )
        action = self.sudo().env.ref(
            "l10n_do_accounting.account_fiscal_sequence_validate_wizard_action"
        ).read()[0]
        action["context"] = {
            "default_name": msg,
            "default_fiscal_sequence_id": self.id,
            "action": "confirm",
        }
        return action

    def _action_confirm(self):
        """
        Lógica real de confirmación: activa la secuencia si no ha expirado,
        o la marca como expirada si la fecha de expiración ya pasó.

        :return: El próximo número fiscal si la secuencia queda activa, None si expiró.
        """
        for rec in self:
            l10n_do_date = get_l10n_do_datetime().date()
            if l10n_do_date >= rec.expiration_date:
                rec.state = "expired"
            else:
                rec.write({
                    "state": "active",
                    "number_next_actual": rec.sequence_start,
                })
                return rec.next_fiscal_number

    def action_cancel(self):
        """
        Abre el wizard de confirmación antes de cancelar la secuencia.
        Una vez cancelada no puede usarse.
        """
        self.ensure_one()
        msg = _(
            "Are you sure want to cancel this Fiscal Sequence? "
            "Once you cancel this Fiscal Sequence cannot be used."
        )
        action = self.env.ref(
            "l10n_do_accounting.account_fiscal_sequence_validate_wizard_action"
        ).read()[0]
        action["context"] = {
            "default_name": msg,
            "default_fiscal_sequence_id": self.id,
            "action": "cancel",
        }
        return action

    def _action_cancel(self):
        """
        Lógica real de cancelación: pone la secuencia en estado 'cancelled'
        y desactiva la ir.sequence interna (preservada solo para auditoría).
        """
        for rec in self:
            rec.state = "cancelled"
            if rec.sequence_id:
                rec.sequence_id.sudo().write({"active": False})

    def action_queue(self):
        """Pone la secuencia en cola para activarse cuando la actual se agote."""
        for rec in self:
            rec.state = "queue"

    # ------------------------------------------------------------------
    # Cron / business logic
    # ------------------------------------------------------------------

    def _expire_sequences(self):
        """
        Llamado por ir.cron diariamente. Marca como expiradas todas las
        secuencias activas cuya ``expiration_date`` ya pasó según la hora
        local de República Dominicana.
        """
        l10n_do_date = get_l10n_do_datetime().date()
        for seq in self.search([("state", "=", "active")]).filtered(
            lambda s: l10n_do_date >= s.expiration_date
        ):
            seq.state = "expired"

    def _get_queued_fiscal_sequence(self):
        """
        Retorna la secuencia en cola más próxima (menor sequence_start) para el
        mismo tipo fiscal y compañía de ``self``. Usada al agotar la secuencia activa.

        :return: Recordset de ``account.fiscal.sequence`` (vacío si no hay ninguna en cola).
        """
        return self.search(
            [
                ("state", "=", "queue"),
                ("fiscal_type_id", "=", self.fiscal_type_id.id),
                ("company_id", "=", self.company_id.id),
            ],
            order="sequence_start asc",
            limit=1,
        )

    def get_fiscal_number(self):
        """
        Genera y retorna el próximo número fiscal de esta secuencia.

        Incrementa ``number_next_actual``, valida que el NCF no exista ya en
        ``account.move`` y, si la secuencia se agota, la marca como ``depleted``
        y activa la siguiente en cola.

        :return: String con el NCF generado (ej. "B0100000001").
        :raises ValidationError: Si el NCF ya existe o no quedan comprobantes.
        """
        self.ensure_one()
        if not self.fiscal_type_id.assigned_sequence:
            return False

        if self.sequence_remaining > 0:
            next_actual_sequence = self.number_next_actual + 1
            next_actual_fiscal_number = self.next_fiscal_number

            already_exists = self.env["account.move"].search_count(
                [
                    ("ref", "=", next_actual_fiscal_number),
                    ("company_id", "=", self.company_id.id),
                    ("fiscal_type_id", "=", self.fiscal_type_id.id),
                ],
                limit=1,
            )
            if already_exists:
                raise ValidationError(
                    _("The fiscal number %s already exists") % next_actual_fiscal_number
                )

            if (self.sequence_remaining - 1) < 1:
                self.state = "depleted"
                queue_seq = self._get_queued_fiscal_sequence()
                if queue_seq:
                    queue_seq._action_confirm()

            self.write({"number_next_actual": next_actual_sequence})
            return next_actual_fiscal_number
        else:
            raise ValidationError(
                _("No Fiscal Sequence available for this type of document.")
            )

    @api.model
    def _update_sequences(self):
        """
        Migración de datos: sincroniza ``number_next_actual`` desde la ir.sequence
        interna para registros donde el campo quedó en 0 (migración desde v1).
        """
        for rec in self.search([]):
            if rec.sequence_id and rec.number_next_actual <= 0:
                rec.write({"number_next_actual": rec.sequence_id.number_next_actual})
