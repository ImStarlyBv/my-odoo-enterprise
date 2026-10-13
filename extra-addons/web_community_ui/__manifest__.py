# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Web Community UI',
    'category': 'Hidden',
    'version': '1.0',
    'description': """
Web Client UI for Community.
============================

This module brings an enhanced web client design and responsiveness
(home menu launcher, navbar, dark mode) to a Community database.

It does not detect or spoof the edition, does not contain any subscription
or expiration machinery and does not promote any paid service.
        """,
    'depends': ['web', 'base_setup'],
    'auto_install': ['web'],
    'data': [
        'views/webclient_templates.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            ('after', 'web/static/src/scss/primary_variables.scss', 'web_community_ui/static/src/**/*.variables.scss'),
            ('before', 'web/static/src/scss/primary_variables.scss', 'web_community_ui/static/src/scss/primary_variables.scss'),
        ],
        'web._assets_secondary_variables': [
            ('before', 'web/static/src/scss/secondary_variables.scss', 'web_community_ui/static/src/scss/secondary_variables.scss'),
        ],
        'web._assets_backend_helpers': [
            ('before', 'web/static/src/scss/bootstrap_overridden.scss', 'web_community_ui/static/src/scss/bootstrap_overridden.scss'),
        ],
        'web.assets_frontend': [
            'web_community_ui/static/src/webclient/home_menu/home_menu_background.scss', # used by login page
            'web_community_ui/static/src/webclient/navbar/navbar.scss',
        ],
        'web.assets_backend': [
            'web_community_ui/static/src/webclient/**/*.scss',
            'web_community_ui/static/src/views/**/*.scss',

            'web_community_ui/static/src/core/**/*',
            'web_community_ui/static/src/webclient/**/*.js',
            'web_community_ui/static/src/webclient/**/*.xml',
            'web_community_ui/static/src/views/**/*.js',
            'web_community_ui/static/src/views/**/*.xml',
            ('remove', 'web_community_ui/static/src/views/pivot/**'),

            # Don't include dark mode files in light mode
            ('remove', 'web_community_ui/static/src/**/*.dark.scss'),
        ],
        'web.assets_backend_lazy': [
            'web_community_ui/static/src/views/pivot/**',
        ],
        'web.assets_backend_lazy_dark': [
            ('include', 'web.dark_mode_variables'),
            # web._assets_backend_helpers
            ('before', 'web_community_ui/static/src/scss/bootstrap_overridden.scss', 'web_community_ui/static/src/scss/bootstrap_overridden.dark.scss'),
            ('after', 'web/static/lib/bootstrap/scss/_functions.scss', 'web_community_ui/static/src/scss/bs_functions_overridden.dark.scss'),
        ],
        'web.assets_web': [
            ('replace', 'web/static/src/main.js', 'web_community_ui/static/src/main.js'),
        ],
        # ========= Dark Mode =========
        "web.dark_mode_variables": [
            # web._assets_primary_variables
            ('before', 'web_community_ui/static/src/scss/primary_variables.scss', 'web_community_ui/static/src/scss/primary_variables.dark.scss'),
            ('before', 'web_community_ui/static/src/**/*.variables.scss', 'web_community_ui/static/src/**/*.variables.dark.scss'),
            # web._assets_secondary_variables
            ('before', 'web_community_ui/static/src/scss/secondary_variables.scss', 'web_community_ui/static/src/scss/secondary_variables.dark.scss'),
        ],
        "web.assets_web_dark": [
            ('include', 'web.dark_mode_variables'),
            # web._assets_backend_helpers
            ('before', 'web_community_ui/static/src/scss/bootstrap_overridden.scss', 'web_community_ui/static/src/scss/bootstrap_overridden.dark.scss'),
            ('after', 'web/static/lib/bootstrap/scss/_functions.scss', 'web_community_ui/static/src/scss/bs_functions_overridden.dark.scss'),
            # assets_backend
            'web_community_ui/static/src/**/*.dark.scss',
        ],
    },
    'license': 'LGPL-3',
}
