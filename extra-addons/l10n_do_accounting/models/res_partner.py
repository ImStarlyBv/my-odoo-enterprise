from odoo import models, fields, api, _
from odoo.exceptions import AccessError


class Partner(models.Model):
    _inherit = "res.partner"

    def _get_l10n_do_dgii_payer_types_selection(self):
        """Return the list of payer types needed in invoices to clasify accordingly to
        DGII requirements."""
        return [
            ("taxpayer", _("Fiscal Tax Payer")),
            ("non_payer", _("Non Tax Payer")),
            ("nonprofit", _("Nonprofit Organization")),
            ("special", _("special from Tax Paying")),
            ("governmental", _("Governmental")),
            ("foreigner", _("Foreigner")),
        ]

    def _get_l10n_do_expense_type(self):
        """Return the list of expenses needed in invoices to clasify accordingly to
        DGII requirements."""
        return [
            ("01", _("01 - Personal")),
            ("02", _("02 - Work, Supplies and Services")),
            ("03", _("03 - Leasing")),
            ("04", _("04 - Fixed Assets")),
            ("05", _("05 - Representation")),
            ("06", _("06 - Admitted Deductions")),
            ("07", _("07 - Financial Expenses")),
            ("08", _("08 - Extraordinary Expenses")),
            ("09", _("09 - Cost & Expenses part of Sales")),
            ("10", _("10 - Assets Acquisitions")),
            ("11", _("11 - Insurance Expenses")),
        ]

    l10n_do_dgii_tax_payer_type = fields.Selection(
        selection="_get_l10n_do_dgii_payer_types_selection",
        compute="_compute_l10n_do_dgii_payer_type",
        inverse="_inverse_l10n_do_dgii_tax_payer_type",
        string="Taxpayer Type",
        index=True,
        store=True,
    )
    l10n_do_expense_type = fields.Selection(
        selection="_get_l10n_do_expense_type",
        string="Cost & Expense Type",
        store=True,
    )
    country_id = fields.Many2one(
        default=lambda self: self.env.ref("base.do")
        if self.env.user.company_id.country_id == self.env.ref("base.do")
        else False
    )

    # ── Campos de tipo fiscal POS (portados de l10n_do_accounting_v2) ─────────
    sale_fiscal_type_id = fields.Many2one(
        comodel_name="account.fiscal.type",
        string="Sale Fiscal Type",
        domain=[("type", "=", "out_invoice")],
        compute="_compute_sale_fiscal_type_id",
        inverse="_inverse_sale_fiscal_type_id",
        index=True,
        store=True,
    )
    purchase_fiscal_type_id = fields.Many2one(
        comodel_name="account.fiscal.type",
        string="Purchase Fiscal Type",
        domain=[("type", "=", "in_invoice")],
    )
    is_fiscal_info_required = fields.Boolean(
        compute="_compute_is_fiscal_info_required",
        help=(
            "True si el tipo fiscal de venta del partner requiere documento "
            "(RNC/Cédula). Usado para mostrar/ocultar campos fiscales en la vista."
        ),
    )

    def _check_l10n_do_fiscal_fields(self, vals):
        if not self or self.parent_id:
            # Do not perform any check because child contacts
            # have readonly fiscal field. This also allows set
            # contacts parent, even if this changes any of its
            # fiscal fields.
            return

        fiscal_fields = [
            field
            for field in ["name", "vat", "country_id"]  # l10n_do_dgii_tax_payer_type ?
            if field in vals
        ]
        if (
            fiscal_fields
            and not self.env.user.has_group(
                "l10n_do_accounting.group_l10n_do_edit_fiscal_partner"
            )
            and self.env["account.move"]
            .sudo()
            .search(
                [
                    ("l10n_latam_use_documents", "=", True),
                    ("country_code", "=", "DO"),
                    ("commercial_partner_id", "=", self.id),
                    ("state", "=", "posted"),
                ],
                limit=1,
            )
        ):
            raise AccessError(
                _(
                    "You are not allowed to modify %s after partner "
                    "fiscal document issuing"
                )
                % (", ".join(self._fields[f].string for f in fiscal_fields))
            )

    def write(self, vals):
        res = super(Partner, self).write(vals)
        self._check_l10n_do_fiscal_fields(vals)

        return res

    @api.depends("vat", "country_id", "name")
    def _compute_l10n_do_dgii_payer_type(self):
        """Compute the type of partner depending on soft decisions"""
        for partner in self:
            vat = partner.vat or partner.name or ""
            vat_len = len(vat) if vat else 0
            upper_name = partner.name.upper() if partner.name else ""
            is_dominican_partner = partner.country_code == "DO"

            if not is_dominican_partner:
                partner.l10n_do_dgii_tax_payer_type = "foreigner"
                continue

            if not vat.isdigit():
                partner.l10n_do_dgii_tax_payer_type = "non_payer"
                continue

            if vat_len == 11:
                partner.l10n_do_dgii_tax_payer_type = "non_payer"
            elif vat_len == 9:
                if "MINISTERIO" in upper_name and not vat.startswith("4"):
                    partner.l10n_do_dgii_tax_payer_type = "governmental"
                elif "ZONA FRANCA" in upper_name:
                    partner.l10n_do_dgii_tax_payer_type = "special"
                elif "IGLESIA" in upper_name or (
                    "MINISTERIO" in upper_name and vat.startswith("4")
                ):
                    partner.l10n_do_dgii_tax_payer_type = "special"
                elif not vat.startswith("4"):
                    partner.l10n_do_dgii_tax_payer_type = "taxpayer"
                else:
                    partner.l10n_do_dgii_tax_payer_type = "nonprofit"
            else:
                partner.l10n_do_dgii_tax_payer_type = "non_payer"

    def _inverse_l10n_do_dgii_tax_payer_type(self):
        for partner in self:
            partner.l10n_do_dgii_tax_payer_type = partner.l10n_do_dgii_tax_payer_type

    # ── Métodos de tipo fiscal POS ────────────────────────────────────────────

    @api.depends("sale_fiscal_type_id", "country_id", "parent_id")
    def _compute_is_fiscal_info_required(self):
        """
        True si el tipo fiscal de venta exige documento (RNC/Cédula), el partner
        es dominicano y no es un contacto hijo.
        """
        do_ref = self.env.ref("base.do")
        for partner in self:
            partner.is_fiscal_info_required = (
                bool(partner.sale_fiscal_type_id)
                and partner.sale_fiscal_type_id.requires_document
                and partner.country_id == do_ref
                and not partner.parent_id
            )

    def _get_fiscal_type_domain(self, prefix):
        """
        Retorna el tipo fiscal de venta (out_invoice) que coincide con el prefijo dado.

        :param prefix: Prefijo del NCF (ej. "B01", "B02").
        :return: Recordset de ``account.fiscal.type`` (vacío si no existe).
        """
        return self.env["account.fiscal.type"].search(
            [("type", "=", "out_invoice"), ("prefix", "=", prefix)], limit=1
        )

    @api.depends("vat", "country_id", "name")
    def _compute_sale_fiscal_type_id(self):
        """
        Calcula el tipo fiscal de venta predeterminado del partner basándose en
        su país, RNC/cédula y nombre. Equivalente a ``l10n_do_dgii_tax_payer_type``
        pero para el modelo fiscal del v2.
        """
        for partner in self.sudo():
            vat = (
                partner.name
                if partner.name and isinstance(partner.name, str) and partner.name.isdigit()
                else partner.vat
            )
            is_do = partner.country_id == self.env.ref("base.do")
            new_type = self._determine_fiscal_type(partner, vat, is_do)
            partner.sale_fiscal_type_id = new_type
            partner.sudo().set_fiscal_position_from_fiscal_type(new_type)

    def _determine_fiscal_type(self, partner, vat, is_dominican_partner):
        """
        Lógica de determinación del tipo fiscal a partir del perfil del partner.

        :param partner: Recordset del partner a evaluar.
        :param vat: RNC o cédula (puede ser None).
        :param is_dominican_partner: True si el país del partner es DO.
        :return: Recordset de ``account.fiscal.type`` correspondiente.
        """
        not_digit_name = (
            partner.name
            and isinstance(partner.name, str)
            and not partner.name.isdigit()
        )

        if not is_dominican_partner:
            return self._get_fiscal_type_domain("B16")
        elif partner.parent_id:
            return partner.parent_id.sale_fiscal_type_id
        elif vat and isinstance(vat, str) and not partner.sale_fiscal_type_id and not_digit_name:
            return self._determine_fiscal_type_by_vat(partner, vat)
        elif is_dominican_partner and not partner.sale_fiscal_type_id and not_digit_name:
            return self._get_fiscal_type_domain("B02")
        else:
            return partner.sale_fiscal_type_id

    def _determine_fiscal_type_by_vat(self, partner, vat):
        """
        Refina la determinación del tipo fiscal usando el RNC/cédula del partner.

        - RNC (9 dígitos): determina si es Gubernamental (B15), Especial (B14)
          o Crédito Fiscal (B01) según el nombre.
        - Cédula (11 dígitos) u otros: Consumo (B02).

        :param partner: Recordset del partner.
        :param vat: Número de RNC o cédula.
        :return: Recordset de ``account.fiscal.type``.
        """
        if vat.isdigit() and len(vat) == 9:
            upper_name = (partner.name or "").upper()
            if "MINISTERIO" in upper_name:
                return self._get_fiscal_type_domain("B15")
            if any(kw in upper_name for kw in ("IGLESIA", "ZONA FRANCA")):
                return self._get_fiscal_type_domain("B14")
            return self._get_fiscal_type_domain("B01")
        return self._get_fiscal_type_domain("B02")

    def _inverse_sale_fiscal_type_id(self):
        """
        Inverse de ``sale_fiscal_type_id``: al guardar el tipo fiscal manualmente,
        actualiza también la posición fiscal del partner si el tipo tiene una definida.
        """
        for partner in self:
            partner.sale_fiscal_type_id = partner.sale_fiscal_type_id
            self.sudo().set_fiscal_position_from_fiscal_type(partner.sale_fiscal_type_id)

    def set_fiscal_position_from_fiscal_type(self, fiscal_type):
        """
        Actualiza la posición fiscal del partner para cada compañía, tomando
        la posición configurada en el tipo fiscal (``fiscal_position_id``,
        que es company-dependent).

        :param fiscal_type: Recordset de ``account.fiscal.type`` a aplicar.
        """
        if not fiscal_type:
            return
        for company in self.env["res.company"].sudo().search([]):
            company_fiscal_type = fiscal_type.with_company(company).sudo()
            if company_fiscal_type.fiscal_position_id:
                self.with_company(company).sudo().write({
                    "property_account_position_id": company_fiscal_type.fiscal_position_id.id,
                })
