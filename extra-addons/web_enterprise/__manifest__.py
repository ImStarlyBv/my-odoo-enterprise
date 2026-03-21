{
    'name': 'Web Enterprise',
    'category': 'Web',
    'version': '18.0.1.0.0',
    'description': 'Enterprise edition UI — minimal workaround implementation.',
    'depends': ['web', 'base_setup'],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
    ],
    'assets': {
        'web.assets_backend': [
            'web_enterprise/static/src/enterprise_theme.scss',
            'web_enterprise/static/src/webclient/home_menu/home_menu.scss',
            'web_enterprise/static/src/webclient/home_menu/home_menu.xml',
            'web_enterprise/static/src/webclient/home_menu/home_menu.js',
        ],
    },
}
