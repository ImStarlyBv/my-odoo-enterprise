from odoo import fields, models

class ResCountryState(models.Model):
    _inherit = 'res.country.state'

    # Este campo almacena el código oficial de 6 dígitos de la DGII para la provincia.
    # Es vital para el payload del e-CF (Nodo: State). 
    # Ejemplo: Distrito Nacional = '010000', Santiago = '250000'.
    l10n_do_dgii_code = fields.Char(
        string="Código DGII (Provincia)", 
        size=6, 
        help="Código oficial de 6 dígitos establecido por la DGII para la provincia."
    )
