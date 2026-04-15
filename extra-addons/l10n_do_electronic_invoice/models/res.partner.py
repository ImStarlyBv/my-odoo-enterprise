from odoo import models, fields, api
from odoo import models, fields, api, _
from odoo.exceptions import AccessError


class Partner(models.Model):
    _inherit = "res.partner"


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

    l10n_do_municipality_id = fields.Many2one(
        comodel_name='l10n_do.municipality',
        string="Municipio (DGII)",
        domain="[('state_id', '=', state_id)]",
        help="Municipio oficial de la DGII. Reemplaza visualmente a la 'Ciudad' en RD."
    )
    #   # Campos adicionales del JSON
    # l10n_do_additional_info = fields.Text(
    #     string="Información Adicional del Cliente",
    #     help="Información adicional relevante del cliente."
    # )
    # l10n_do_contact_phone = fields.Char(
    #     string="Teléfono de Contacto",
    #     help="Teléfono del cliente para fines de contacto."
    # )
    # l10n_do_contact_email = fields.Char(
    #     string="Correo Electrónico de Contacto",
    #     help="Correo electrónico del cliente para contacto."
    # )

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
        """ Compute the type of partner depending on soft decisions"""
        company_id = self.env["res.company"].search(
            [("id", "=", self.env.user.company_id.id)]
        )
        for partner in self:
            vat = str(partner.vat if partner.vat else partner.name)
            is_dominican_partner = bool(partner.country_id == self.env.ref("base.do"))

            if partner.country_id and not is_dominican_partner:
                partner.l10n_do_dgii_tax_payer_type = "foreigner"

            elif vat and (
                not partner.l10n_do_dgii_tax_payer_type
                or partner.l10n_do_dgii_tax_payer_type == "non_payer"
            ):
                if partner.country_id and is_dominican_partner:
                    if vat.isdigit() and len(vat) == 9:
                        if not partner.vat:
                            partner.vat = vat
                        if partner.name and "MINISTERIO" in partner.name:
                            partner.l10n_do_dgii_tax_payer_type = "governmental"
                        elif partner.name and any(
                            [n for n in ("IGLESIA", "ZONA FRANCA") if n in partner.name]
                        ):
                            partner.l10n_do_dgii_tax_payer_type = "special"
                        elif vat.startswith("1"):
                            partner.l10n_do_dgii_tax_payer_type = "taxpayer"
                        elif vat.startswith("4"):
                            partner.l10n_do_dgii_tax_payer_type = "nonprofit"
                        else:
                            partner.l10n_do_dgii_tax_payer_type = "taxpayer"

                    elif len(vat) == 11:
                        if vat.isdigit():
                            if not partner.vat:
                                partner.vat = vat
                            payer_type = (
                                "taxpayer"
                                if company_id.l10n_do_default_client == "fiscal"
                                else "non_payer"
                            )
                            partner.l10n_do_dgii_tax_payer_type = payer_type
                        else:
                            partner.l10n_do_dgii_tax_payer_type = "non_payer"
                    else:
                        partner.l10n_do_dgii_tax_payer_type = "non_payer"
            elif not partner.l10n_do_dgii_tax_payer_type:
                partner.l10n_do_dgii_tax_payer_type = "non_payer"
            else:
                partner.l10n_do_dgii_tax_payer_type = (
                    partner.l10n_do_dgii_tax_payer_type
                )

    def _inverse_l10n_do_dgii_tax_payer_type(self):
        for partner in self:
            partner.l10n_do_dgii_tax_payer_type = partner.l10n_do_dgii_tax_payer_type

    @api.onchange('state_id')
    def _onchange_state_id_clear_municipality(self):
        """
        Control de integridad: Si el usuario cambia la provincia (estado), 
        limpiamos el municipio actual si este no pertenece a la nueva provincia.
        Evita que se guarde 'Santiago' con municipio 'Distrito Nacional'.
        """
        for partner in self:
            if partner.state_id and partner.l10n_do_municipality_id.state_id != partner.state_id:
                partner.l10n_do_municipality_id = False

    @api.onchange('l10n_do_municipality_id')
    def _onchange_l10n_do_municipality_sync_city(self):
        """
        Compatibilidad nativa: La API de Odoo, reportes y pasarelas de pago 
        dependen del campo de texto libre 'city'. 
        Para no romper eso, cuando el usuario selecciona el municipio, 
        copiamos automáticamente su nombre al campo 'city' estándar.
        """
        for partner in self:
            if partner.l10n_do_municipality_id:
                partner.city = partner.l10n_do_municipality_id.name

    @api.model_create_multi
    def create(self, vals_list):
        """
        Odoo 15/18: Intercepción de creación.
        1. Si envían el ID del municipio, forzamos el texto de 'city'.
        2. Si envían el texto de 'city' pero no el ID, intentamos buscar el municipio oficial.
        """
        for vals in vals_list:
            # Sincronización: ID -> Texto
            if vals.get('l10n_do_municipality_id'):
                municipality = self.env['l10n_do.municipality'].browse(vals['l10n_do_municipality_id'])
                if municipality.exists():
                    vals['city'] = municipality.name
            
            # Sincronización Inversa (Bidireccional): Texto -> ID
            elif vals.get('city') and vals.get('country_id'):
                country = self.env['res.country'].browse(vals['country_id'])
                if country.code == 'DO':
                    # Búsqueda flexible ignorando mayúsculas
                    domain = [('name', '=ilike', vals['city'])]
                    if vals.get('state_id'):
                        domain.append(('state_id', '=', vals['state_id']))
                    
                    municipio = self.env['l10n_do.municipality'].search(domain, limit=1)
                    if municipio:
                        vals['l10n_do_municipality_id'] = municipio.id

        return super().create(vals_list)

    def write(self, vals):
        """
        Odoo 15/18: Intercepción de actualización.
        Aplica la misma lógica bidireccional al editar registros.
        """
        # Sincronización: ID -> Texto
        if vals.get('l10n_do_municipality_id'):
            municipality = self.env['l10n_do.municipality'].browse(vals['l10n_do_municipality_id'])
            if municipality.exists():
                vals['city'] = municipality.name
                
        # Sincronización Inversa (Bidireccional): Texto -> ID
        elif vals.get('city') and not vals.get('l10n_do_municipality_id'):
            for partner in self:
                if partner.country_code == 'DO':
                    domain = [('name', '=ilike', vals['city'])]
                    if partner.state_id:
                        domain.append(('state_id', '=', partner.state_id.id))
                    
                    municipio = self.env['l10n_do.municipality'].search(domain, limit=1)
                    if municipio:
                        vals['l10n_do_municipality_id'] = municipio.id
                        break # Asumimos la primera coincidencia para la transacción

        return super().write(vals)

