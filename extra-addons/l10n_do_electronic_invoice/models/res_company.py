from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    # Campos nativos (Para asegurar visibilidad/sobreescritura menor si fuese necesaria)
    vat = fields.Char(string="RNC")
    phone = fields.Char(string="Teléfono")
    email = fields.Char(string="Email")
    website = fields.Char(string="Sitio Web")

    # Campos traídos del archivo huérfano viejo
    is_live = fields.Boolean(
        string="Modo Producción", 
        default=False,
        help="Si está marcado, las facturas electrónicas e-CF se enviarán a producción de DGII/DigiFact."
    )
    l10n_do_enable_resend_button = fields.Boolean(
        string="Habilitar Botón de Reenvío DGII",
        default=False,
        help="Si se marca, aparecerá el botón 'Reenviar a DGII' en las facturas publicadas para corregir errores."
    )
    l10n_do_default_client = fields.Selection(
        selection=[
            ('fiscal', 'Cliente de Consumo'),
            ('final', 'Cliente Final'),
        ],
        string='Default Client Type',
        default='final',
        help='Default taxpayer type for clients with 11-digit VAT (Cédula).'
    )
    # Referencia al municipio
    l10n_do_municipality_id = fields.Many2one(
        comodel_name='l10n_do.municipality',
        related='partner_id.l10n_do_municipality_id',
        readonly=False,
        string="Municipio (DGII)"
    )

    # Nativos para la generación del e-CF
    l10n_do_trade_name = fields.Char(
        string="Nombre Comercial (DigiFact)", 
        help="Nombre comercial (NombreComercial) tal como se reporta a la DGII."
    )
    l10n_do_economic_activity = fields.Char(
        string="Actividad Económica (DigiFact)", 
        help="Descripción de la actividad económica (ActividadEconomica) principal."
    )
    l10n_do_branch_code = fields.Char(
        string="Código Sucursal",
        default="0001",
        help="Código de sucursal para BranchInfo.Name (Normalmente '0001')"
    )
