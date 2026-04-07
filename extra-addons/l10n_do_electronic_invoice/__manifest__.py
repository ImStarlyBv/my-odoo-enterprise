{
    'name': 'Electronic Invoicing DGII (DigiFact)',
    'version': '18.0.1.0.0',
    'summary': 'Generador del JSON de Factura Electrónica (e-CF) para DigiFact - República Dominicana',
    'category': 'Accounting/Localizations',
    'author': 'Omar Bautista',
    'license': 'OPL-1',
    'depends': [
        'l10n_do_accounting',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/digifact_preview_wizard_views.xml',
        'views/res_company_views.xml',
        'data/l10n_do.municipality.csv',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
