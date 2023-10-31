# -*- coding: utf-8 -*-
{
    'name': "lavish_account",

    'summary': """
        Módulo para personalización de la contabilidad Colombiana. """,

    'description': """
        Módulo para personalización de la contabilidad Colombiana. 
    """,

    'author': "lavish S.A.S",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'account',
    "version": "15.0.1.0.0",

    # any module necessary for this one to work correctly
    'depends': ['base','account','lavish_erp','account_reports','documents','l10n_co_reports'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/actions_payment_file.xml',
        'views/actions_account_account.xml',
        'views/actions_account_move.xml',
        'views/actions_documents.xml',
        'views/actions_account_aged_partner.xml',
        'views/actions_exogenous_information.xml',
        'views/actions_bank_statements_report.xml',
        'views/actions_res_partner_fe.xml',
        'views/actions_account_journal.xml',
        'views/actions_reconciling_items.xml',
        'views/actions_res_config_settings.xml',
        'views/menus.xml',
    ],
    'license': 'LGPL-3',
}
