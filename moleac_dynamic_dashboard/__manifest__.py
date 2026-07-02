{
    'name': 'BSI Dynamic Dashboard',
    'version': '19.0.1.2.0',
    'category': 'Accounting/Reporting',
    'summary': 'Dynamic Balance Sheet with inline data mapping and live preview',
    'author': 'BSI',
    'depends': ['account', 'analytic','bsi_moleac_dashboard_mapping'],
    'data': [
        'security/ir.model.access.csv',
        'views/bsi_dashboard_filter_template_views.xml',
        'views/bsi_dashboard_export_wizard_views.xml',
        'views/bsi_dashboard_config_views.xml',
        'views/bsi_dashboard_menu.xml',
        'report/report_bsi_dashboard_action.xml',
        'report/report_bsi_dashboard_template.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'moleac_dynamic_dashboard/static/src/css/dynamic_dashboard.css',
            'moleac_dynamic_dashboard/static/src/js/dashboard_collapse.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
}
