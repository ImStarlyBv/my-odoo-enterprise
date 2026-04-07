from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    l10n_do_product_type = fields.Selection(
        selection=[
            ('1', 'Bien'),
            ('2', 'Servicio')
        ],
        string="Tipo Comprobante (DGII)",
        default='1',
        help="Tipo de ítem según DGII (1 para bienes físicos, 2 para servicios abstractos)."
    )

    l10n_do_billing_indicator = fields.Selection(
        selection=[
            ('1', 'Gravado - ITBIS'),
            ('2', 'Otras Exenciones'),
            ('3', 'Bienes Exentos'),
            ('4', 'Servicios Exentos')
        ],
        string="Indicador Facturación (DGII)",
        help="Usado para enviar al e-CF el indicador correcto si no se deriva de los impuestos automáticamente."
    )
