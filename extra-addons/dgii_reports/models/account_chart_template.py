# -*- coding: utf-8 -*-
from odoo import models
from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    @template('do', 'account.tax')
    def _get_do_dgii_account_tax(self):
        # Inject custom DGII fields (l10n_do_tax_type, isr_retention_type, tax_group_id)
        # into the Dominican Republic taxes defined by l10n_do's CSV data.
        return {
            # --- Ventas ---
            'tax_18_sale': {'l10n_do_tax_type': 'itbis'},
            'tax_18_sale_incl': {'l10n_do_tax_type': 'itbis'},
            'tax_18_of_10': {'l10n_do_tax_type': 'itbis'},
            'tax_tip_sale': {'l10n_do_tax_type': 'tip'},
            'ret_5_income_gov': {'l10n_do_tax_type': 'isr', 'isr_retention_type': '07'},

            # --- Compras ---
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

            # --- Retenciones y Costos ---
            'ret_100_tax_person': {'l10n_do_tax_type': 'ritbis', 'tax_group_id': 'l10n_do.tax_group_retencion_18'},
            'ret_100_tax_security': {'l10n_do_tax_type': 'ritbis', 'tax_group_id': 'l10n_do.tax_group_retencion_18'},
            'tax_18_serv_cost': {'l10n_do_tax_type': 'itbis'},
            'ret_10_income_rent': {'l10n_do_tax_type': 'isr', 'isr_retention_type': '01'},

            # --- Dividendos, Transferencias e Importaciones ---
            'ret_10_income_dividend': {'l10n_do_tax_type': 'isr', 'isr_retention_type': '03'},
            'ret_2_income_person': {'l10n_do_tax_type': 'isr', 'isr_retention_type': '03'},
            'ret_2_income_transfer': {'l10n_do_tax_type': 'isr', 'isr_retention_type': '03'},
            'tax_18_importation': {'l10n_do_tax_type': 'itbis'},

            # --- Telecomunicaciones, Bancos y Otras Retenciones ---
            'tax_10_telco': {'l10n_do_tax_type': 'isc'},
            'tax_2_telco': {'l10n_do_tax_type': 'other'},
            'tax_0015_bank': {'l10n_do_tax_type': 'other'},
            'ret_100_tax_nonprofit': {'l10n_do_tax_type': 'ritbis', 'tax_group_id': 'l10n_do.tax_group_retencion_18'},
            'ret_30_tax_moral': {'l10n_do_tax_type': 'ritbis', 'tax_group_id': 'l10n_do.tax_group_retencion_54'},
            'ret_75_tax_nonformal': {'l10n_do_tax_type': 'ritbis', 'tax_group_id': 'l10n_do.group_ret'},
            'ret_27_income_remittance': {'l10n_do_tax_type': 'isr', 'isr_retention_type': '03'},
        }
