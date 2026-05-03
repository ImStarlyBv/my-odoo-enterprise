from odoo import models, fields


class L10nDoEcfDocTypeConfig(models.Model):
    """Controla qué tipos de comprobante e-CF se envían a la API de la DGII.
    Si no existe registro para un tipo, se asume envío habilitado (ver _ecf_should_send).
    """
    _name = 'l10n_do.ecf.doc.type.config'
    _description = 'Configuración de envío por tipo de comprobante e-CF'
    _order = 'doc_type'

    company_id = fields.Many2one('res.company', required=True, ondelete='cascade')
    doc_type = fields.Selection(
        selection=[
            ('31', 'E31 – Factura de Crédito Fiscal (B2B)'),
            ('32', 'E32 – Factura de Consumo (B2C)'),
            ('33', 'E33 – Nota de Débito'),
            ('34', 'E34 – Nota de Crédito'),
            ('41', 'E41 – Comprobante de Compras'),
            ('43', 'E43 – Gastos Menores'),
            ('44', 'E44 – Regímenes Especiales'),
            ('45', 'E45 – Gubernamental'),
            ('46', 'E46 – Exportaciones'),
            ('47', 'E47 – Compras al Exterior'),
        ],
        string='Tipo de Comprobante',
        required=True,
    )
    send_to_dgii = fields.Boolean(string='Enviar a la DGII', default=True)

    _sql_constraints = [
        (
            'uniq_company_doc_type',
            'UNIQUE(company_id, doc_type)',
            'Ya existe una configuración para este tipo de comprobante en esta empresa.',
        )
    ]
