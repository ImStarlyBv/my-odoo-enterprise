{
    'name': "Fiscal POS (Rep. Dominicana)",
    'summary': "POS con NCF/e-CF DGII: comprobantes fiscales, notas de crédito y registro de NCF proveedor.",
    'description': """
        Extiende el Punto de Venta de Odoo 18 para cumplir con la normativa DGII
        de la República Dominicana: NCF automático, e-CF con QR, validaciones de
        monto y RNC, devoluciones B04/E34, pagos con Nota de Crédito y registro
        de NCF de proveedores desde el cajero.

        Compatible con l10n_do_electronic_invoice (opcional). Sin él, los tipos
        E3x funcionan en modo contingencia (sin envío a DGII).
    """,
    'author': "Guavana, Indexa, Iterativo SRL",
    'license': 'LGPL-3',
    'website': "https://github.com/odoo-dominicana",
    'category': 'Localization',
    'version': '18.0.1.0.0',
    'depends': [
        'base',
        'point_of_sale',
        'l10n_do_accounting',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/data.xml',
        'views/res_config_settings_views.xml',
        'views/pos_order_views.xml',
        'views/pos_payment_method_views.xml',
        'views/account_vendor_ncf_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            # SCSS — estilos del recibo fiscal, botones NCF y e-CF
            'l10n_do_pos/static/src/scss/pos.scss',
            # JS — patches de modelos primero; botones y pantallas después
            # Todos usan @odoo-module: el sistema de módulos resuelve imports.
            'l10n_do_pos/static/src/js/models.js',
            'l10n_do_pos/static/src/js/buttons/SetDocumentTypeButton.js',
            'l10n_do_pos/static/src/js/buttons/VendorNcfButton.js',
            'l10n_do_pos/static/src/js/Chrome.js',
            'l10n_do_pos/static/src/js/PaymentScreen.js',
            'l10n_do_pos/static/src/js/TicketScreen.js',
            # XML — templates de componentes y extensiones de vistas POS
            'l10n_do_pos/static/src/xml/SetDocumentTypeButton.xml',
            'l10n_do_pos/static/src/xml/VendorNcfButton.xml',
            'l10n_do_pos/static/src/xml/OrderReceipt.xml',
            'l10n_do_pos/static/src/xml/PaymentScreen.xml',
            'l10n_do_pos/static/src/xml/TicketScreen.xml',
        ],
    },
    'post_init_hook': '_l10n_do_pos_post_init',
    'installable': True,
}
