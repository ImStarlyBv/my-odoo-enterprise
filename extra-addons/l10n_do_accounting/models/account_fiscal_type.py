# © 2019 José López <jlopez@indexa.do>
# © 2019 Raul Ovalle <rovalle@guavana.com>

import re

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AccountFiscalType(models.Model):
    """
    Tipo de comprobante fiscal dominicano (NCF).

    Define el prefijo, padding y comportamiento de secuencia para cada categoría
    de documento fiscal (B01, B02, E31, etc.). Requerido por l10n_do_pos para
    clasificar transacciones POS.

    El campo ``l10n_latam_document_type_id`` actúa como puente hacia la
    infraestructura l10n_latam, permitiendo que facturas generadas desde POS
    hereden el tipo de documento electrónico (e-CF) correcto sin romper el
    flujo de facturación estándar.
    """

    _name = "account.fiscal.type"
    _description = "Account Fiscal Type"
    _order = "sequence"

    name = fields.Char(
        string="Name",
        required=True,
        copy=False,
    )
    active = fields.Boolean(
        string="Active",
        default=True,
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
    )
    prefix = fields.Char(
        string="Prefix",
        copy=False,
    )
    padding = fields.Integer(
        string="Padding",
        default=8,
    )
    type = fields.Selection(
        string="Type",
        selection=[
            ("out_invoice", "Sale"),
            ("in_invoice", "Purchase"),
            ("out_refund", "Customer Credit Note"),
            ("in_refund", "Supplier Credit Note"),
            ("out_debit", "Customer Debit Note"),
            ("in_debit", "Supplier Debit Note"),
        ],
        required=True,
        default="in_invoice",
    )
    journal_type = fields.Selection(
        string="Journal Type",
        selection=[
            ("sale", "Sale"),
            ("purchase", "Purchase"),
        ],
        compute="_compute_journal_type",
    )
    fiscal_position_id = fields.Many2one(
        comodel_name="account.fiscal.position",
        string="Fiscal Position",
        company_dependent=True,
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Journal",
        company_dependent=True,
    )
    assigned_sequence = fields.Boolean(
        string="Assigned Sequence",
        default=True,
        help=(
            "If checked, this Fiscal Type will use a Fiscal Sequence "
            "to generate Fiscal Numbers."
        ),
    )
    requires_document = fields.Boolean(
        string="Requires a document?",
        help="If checked, this Fiscal Type will require a document to be generated.",
    )
    # Puente hacia l10n_latam: permite que una factura POS propague
    # l10n_latam_document_type_id y active así la generación de e-CF.
    # Si está vacío, el tipo fiscal no genera comprobante electrónico.
    l10n_latam_document_type_id = fields.Many2one(
        comodel_name="l10n_latam.document.type",
        string="Tipo de Documento e-CF (l10n_latam)",
        help=(
            "Mapea este tipo fiscal POS al tipo de documento l10n_latam "
            "correspondiente. Se usa para propagar l10n_latam_document_type_id "
            "en account.move cuando la factura proviene de POS, habilitando "
            "la generación de e-CF. Si está vacío, el tipo no emite e-CF."
        ),
    )

    _sql_constraints = [
        (
            "type_prefix_uniq",
            "unique (type, prefix)",
            "There must be only one Fiscal Type of this Type and Prefix",
        )
    ]

    @api.depends("type")
    def _compute_journal_type(self):
        """Deriva el tipo de diario (sale/purchase) del prefijo del tipo de documento."""
        for fiscal_type in self:
            fiscal_type.journal_type = (
                "sale" if fiscal_type.type[:3] == "out" else "purchase"
            )

    def check_format_fiscal_number(self, fiscal_number, type=''):
        """
        Valida que ``fiscal_number`` coincida con el prefijo y padding esperados
        para este tipo fiscal.

        :param fiscal_number: NCF a validar (ej. "B0100000001").
        :param type: Tipo de movimiento usado cuando ``self`` está vacío, para
                     buscar el tipo fiscal por prefijo + tipo.
        :raises ValidationError: Si el formato no es válido.
        """
        if not fiscal_number:
            raise ValidationError(_('Fiscal number can not be blank'))

        if len(fiscal_number) < 3:
            raise ValidationError(
                _('This origin fiscal number must have more than 3 characters')
            )

        fiscal_type = self
        message = ''

        if not self:
            fiscal_type = self.search([
                ('prefix', '=', fiscal_number[0:3]),
                ('type', '=', type),
            ])

        if not fiscal_type:
            if type in ('in_refund', 'out_refund'):
                message = _(
                    'The fiscal number type (%s) is not a credit note.'
                ) % fiscal_number[0:3]

            raise ValidationError(
                _('This document type (%s) does not exist.' % fiscal_number[0:3])
                if not message
                else message
            )

        origin_out_padding = (
            len(fiscal_number) - len(fiscal_type.prefix)
            if fiscal_type.prefix
            else len(fiscal_number)
        )

        if origin_out_padding != fiscal_type.padding:
            raise ValidationError(
                _(
                    'The document type (%s) has (%s) digits. '
                    'You are trying to input (%s) digits.'
                ) % (fiscal_type.name, fiscal_type.padding, origin_out_padding)
            )

        if not re.match('^[0-9]+$', fiscal_number[3:]):
            raise ValidationError(
                _('After the document type, all characters must be digits from 0 to 9.')
            )

        if fiscal_type.prefix and fiscal_number[0:3] != fiscal_type.prefix:
            raise ValidationError(
                _('The document type (%s) must start with (%s)') % (
                    fiscal_type.name, fiscal_type.prefix)
            )
