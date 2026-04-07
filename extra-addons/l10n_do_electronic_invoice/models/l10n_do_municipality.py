from odoo import fields, models, api

class L10nDoMunicipality(models.Model):
    _name = 'l10n_do.municipality'
    _description = 'Municipio de República Dominicana (DGII)'
    _order = 'code'

    # -------------------------------------------------------------------------
    # MODELO DE MUNICIPIOS (DGII)
    # -------------------------------------------------------------------------
    # Estructura diseñada para mapear la división territorial dominicana.
    # Almacena el código de 6 dígitos que exige la API de facturación electrónica.
    
    name = fields.Char(
        string="Nombre", 
        required=True,
        help="Nombre del municipio (Ej. Santo Domingo de Guzmán)."
    )
    
    code = fields.Char(
        string="Código DGII", 
        required=True, 
        size=6, 
        help="Código de 6 dígitos que va en el payload de la factura (Nodo: District)."
    )
    
    state_id = fields.Many2one(
        comodel_name='res.country.state', 
        string="Provincia", 
        required=False,
        domain="[('country_id.code', '=', 'DO')]",
        help="Provincia a la que pertenece este municipio."
    )

    @api.model
    def _sync_dgii_codes_and_states(self):
        """
        Odoo 15/18: Función de sincronización automática post-instalación.
        Busca las provincias por texto ignorando tildes y mayúsculas, asigna 
        el código DGII de 6 dígitos al modelo nativo y relaciona los municipios.
        Esto evita colisiones con IDs externos modificados por terceros.
        """
        import unicodedata
        
        def n(text): 
            if not text: return ""
            return unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8').upper()

        mapeo = {
            '01': 'DISTRITO NACIONAL', '02': 'AZUA', '03': 'BAHORUCO', '04': 'BARAHONA', '05': 'DAJABON', 
            '06': 'DUARTE', '07': 'ELIAS PINA', '08': 'EL SEIBO', '09': 'ESPAILLAT', '10': 'INDEPENDENCIA', 
            '11': 'LA ALTAGRACIA', '12': 'LA ROMANA', '13': 'LA VEGA', '14': 'MARIA TRINIDAD SANCHEZ', 
            '15': 'MONTE CRISTI', '16': 'PEDERNALES', '17': 'PERAVIA', '18': 'PUERTO PLATA', 
            '19': 'HERMANAS MIRABAL', '20': 'SAMANA', '21': 'SAN CRISTOBAL', '22': 'SAN JUAN', 
            '23': 'SAN PEDRO DE MACORIS', '24': 'SANCHEZ RAMIREZ', '25': 'SANTIAGO', 
            '26': 'SANTIAGO RODRIGUEZ', '27': 'VALVERDE', '28': 'MONSENOR NOUEL', '29': 'MONTE PLATA', 
            '30': 'HATO MAYOR', '31': 'SAN JOSE DE OCOA', '32': 'SANTO DOMINGO'
        }
        
        do_country = self.env['res.country'].search([('code', '=', 'DO')], limit=1)
        if not do_country:
            return

        provincias = self.env['res.country.state'].search([('country_id', '=', do_country.id)])
        estado_por_prefijo = {}

        # 1. Inyectar código DGII a las provincias encontradas
        for prefix, name in mapeo.items():
            for state in provincias:
                if name == n(state.name):
                    state.l10n_do_dgii_code = prefix + '0000'
                    estado_por_prefijo[prefix] = state.id
                    break

        # 2. Relacionar los municipios con su provincia
        for mun in self.search([]):
            prefix = mun.code[:2]
            if prefix in estado_por_prefijo:
                mun.state_id = estado_por_prefijo[prefix]