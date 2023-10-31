# -*- coding: utf-8 -*-
{
    'name': "lavish_erp",
    'summary': """
        lavish ERP""",
    'description': """
        .lavish ERP.
    """,
    'author': "lavish S.A.S",
    'website': "http://www.lavish.com.co",
    'category': 'lavishERP',
    'version': '0.1',
    'application': True,
    "license": "AGPL-3",
    'depends': ['base',
        'contacts',
        'account',
        'account_tax_python',
        'l10n_co',
        'base_address_city',
        "purchase",
        "sale"],
    #'assets': {
    #    'web.assets_backend': [
    #        'lavish_erp/static/scss/style.scss',
    #    ],
    #},
    'data': [
        'data/res.city.csv',
        'data/res_country_state.xml',
        'data/res.bank.csv',
        'security/ir.model.access.csv',
        'views/journal.xml',
        'views/res_country_state.xml',
        'views/res_country_view.xml',
        'views/product_category_view.xml',
        'views/general_actions.xml',
        'views/res_partner.xml',
        'views/res_users.xml',
        'views/general_menus.xml'       
    ]    
}
