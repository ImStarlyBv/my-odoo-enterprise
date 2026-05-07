import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


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
        help="Si está marcado, las facturas electrónicas e-CF se enviarán al entorno de producción de la DGII."
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
        string="Nombre Comercial (e-CF)",
        help="Nombre comercial (NombreComercial) tal como se reporta a la DGII."
    )
    l10n_do_economic_activity = fields.Char(
        string="Actividad Económica (e-CF)",
        help="Descripción de la actividad económica (ActividadEconomica) principal."
    )
    l10n_do_branch_code = fields.Char(
        string="Código Sucursal",
        default="0001",
        help="Código de sucursal para BranchInfo.Name (Normalmente '0001')"
    )

    ecf_doc_type_config_ids = fields.One2many(
        comodel_name='l10n_do.ecf.doc.type.config',
        inverse_name='company_id',
        string='Tipos de Comprobante',
    )

    def action_init_ecf_doc_type_config(self):
        """Crea los registros de configuración para los 10 tipos e-CF si no existen.
        Idempotente: no modifica registros ya existentes.

        allow_manual_ncf refleja el comportamiento base de l10n_do_accounting:
        - E41 (e-informal), E43 (e-minor), E47 (e-exterior) → automático (False)
        - E31 (e-fiscal) y demás tipos de compra → manual (True)
        """
        doc_types = ['31', '32', '33', '34', '41', '43', '44', '45', '46', '47']
        # Tipos de compra cuyo comportamiento base es AUTO — preservar con False
        _auto_purchase_types = {'41', '43', '47'}
        Config = self.env['l10n_do.ecf.doc.type.config']
        for company in self:
            existing = Config.search([('company_id', '=', company.id)]).mapped('doc_type')
            missing = [t for t in doc_types if t not in existing]
            if missing:
                for doc_type in missing:
                    Config.create({
                        'company_id': company.id,
                        'doc_type': doc_type,
                        'send_to_dgii': True,
                        'allow_manual_ncf': doc_type not in _auto_purchase_types,
                    })
                _logger.info(
                    "ECF: inicializados %d tipos de comprobante para '%s': %s",
                    len(missing), company.name, missing,
                )
            else:
                _logger.debug("ECF: tipos de comprobante ya inicializados para '%s'", company.name)

    # Conexión con api.ecf-software.online
    ecf_api_url = fields.Char(
        string="URL de la API ECF",
        default="https://api.ecf-software.online",
        help="Endpoint base de la API de facturación electrónica.",
    )
    ecf_api_key = fields.Char(
        string="API Key (Bearer Token)",
        password=True,
        help="Token de autenticación emitido por api.ecf-software.online. Se emite una sola vez.",
    )
    ecf_auto_send = fields.Boolean(
        string="Envío Automático al Confirmar",
        default=True,
        help="Si está activo, al confirmar una factura e-CF se envía automáticamente a la API.",
    )
