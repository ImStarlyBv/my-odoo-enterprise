# -*- coding: utf-8 -*-
from odoo import models

class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _get_do_base_taxes(self):
        """
        DOCUMENTACIÓN DE MIGRACIÓN:
        - Odoo 15: Los impuestos se definían en XML usando el modelo 'account.tax.template'[cite: 1, 2, 3, 4, 5, 6, 7, 8].
          El sistema leía el XML al instalar el módulo y luego transfería esos datos a 'account.tax'.
        - Odoo 18: El modelo 'account.tax.template' ya no existe. El XML de la versión 15 rompe el servidor.
          Ahora heredamos 'account.chart.template' e interceptamos el método '_get_do_base_taxes()'.
          Modificamos el diccionario de impuestos en memoria inyectando nuestros campos personalizados 
          (l10n_do_tax_type, isr_retention_type, tax_group_id) antes de que Odoo los guarde en la base de datos.
        """
        taxes = super()._get_do_base_taxes()

        # Diccionario de mapeo: Clave (ID del impuesto) -> Valor (Campos a inyectar)
        # Nota: Los campos relacionales (tax_group_id) se pasan como cadenas de texto (XML ID)
        # para que el motor de Odoo 18 los resuelva automáticamente en la carga.
        tax_updates = {
            # --- Ventas --- [cite: 1]
            'tax_18_sale': {'l10n_do_tax_type': 'itbis'},
            'tax_18_sale_incl': {'l10n_do_tax_type': 'itbis'},
            'tax_18_of_10': {'l10n_do_tax_type': 'itbis'},
            'tax_tip_sale': {'l10n_do_tax_type': 'tip'},
            'ret_5_income_gov': {'l10n_do_tax_type': 'isr', 'isr_retention_type': '07'},

            # --- Compras --- [cite: 2, 3, 4]
            'tax_tip_purch': {'l10n_do_tax_type': 'tip'},
            'tax_18_purch': {'l10n_do_tax_type': 'itbis'},
            'tax_18_purch_incl': {'l10n_do_tax_type': 'itbis'},
            'tax_16_purch': {'l10n_do_tax_type': 'itbis'},
            'tax_16_purch_incl': {'l10n_do_tax_type': 'itbis'},
            'tax_9_purch': {'l10n_do_tax_type': 'itbis'},
            'tax_9_purch_incl': {'l10n_do_tax_type': 'itbis'},
            'tax_8_purch': {'l10n_do_tax_type': 'itbis'},
            'tax_8_purch_incl': {'l10n_do_tax_type': 'itbis'},
            'tax_18_purch_serv': {'l10n_do_tax_type': 'itbis'},
            'tax_18_purch_serv_incl': {'l10n_do_tax_type': 'itbis'},
            'tax_18_10_total_mount': {'l10n_do_tax_type': 'itbis'},
            'tax_18_property_cost': {'l10n_do_tax_type': 'itbis'},
            'ret_10_income_person': {'l10n_do_tax_type': 'isr', 'isr_retention_type': '02'},
            
            # --- Retenciones y Costos --- [cite: 5]
            'ret_100_tax_person': {'l10n_do_tax_type': 'ritbis', 'tax_group_id': 'l10n_do.tax_group_retencion_18'},
            'ret_100_tax_security': {'l10n_do_tax_type': 'ritbis', 'tax_group_id': 'l10n_do.tax_group_retencion_18'},
            'tax_18_serv_cost': {'l10n_do_tax_type': 'itbis'},
            'ret_10_income_rent': {'l10n_do_tax_type': 'isr', 'isr_retention_type': '01'},
            
            # --- Dividendos, Transferencias e Importaciones --- [cite: 6]
            'ret_10_income_dividend': {'l10n_do_tax_type': 'isr', 'isr_retention_type': '03'},
            'ret_2_income_person': {'l10n_do_tax_type': 'isr', 'isr_retention_type': '03'},
            'ret_2_income_transfer': {'l10n_do_tax_type': 'isr', 'isr_retention_type': '03'},
            'tax_18_importation': {'l10n_do_tax_type': 'itbis'},
            
            # --- Telecomunicaciones, Bancos y Otras Retenciones --- [cite: 7, 8]
            'tax_10_telco': {'l10n_do_tax_type': 'isc'},
            'tax_2_telco': {'l10n_do_tax_type': 'other'},
            'tax_0015_bank': {'l10n_do_tax_type': 'other'},
            'ret_100_tax_nonprofit': {'l10n_do_tax_type': 'ritbis', 'tax_group_id': 'l10n_do.tax_group_retencion_18'},
            'ret_30_tax_moral': {'l10n_do_tax_type': 'ritbis', 'tax_group_id': 'l10n_do.tax_group_retencion_54'},
            'ret_75_tax_nonformal': {'l10n_do_tax_type': 'ritbis', 'tax_group_id': 'l10n_do.group_ret'},
            'ret_27_income_remittance': {'l10n_do_tax_type': 'isr', 'isr_retention_type': '03'},
        }

        # Aplicamos las modificaciones de forma iterativa y eficiente.
        for tax_id, tax_data in tax_updates.items():
            if tax_id in taxes:
                taxes[tax_id].update(tax_data)

        return taxes