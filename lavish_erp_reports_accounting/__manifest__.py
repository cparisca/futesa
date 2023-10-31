# -*- coding: utf-8 -*-
{
    'name': "lavish_erp_reports_accounting",

    'summary': """
        lavish ERP Reportes Contables""",

    'description': """
        .lavish ERP Reportes Contables.
        Balance
        Auxiliar
        Libro Diario
        Libro Mayor
        Consultas
        Balance analítico
        Balance Costo por Vehículo
    """,

    'author': "lavish S.A.S",
    #'website': "http://www.lavish.com.co",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    "version": "15.0.1.0.0",    

    # any module necessary for this one to work correctly
    'depends': ['base','contacts','account','lavish_account'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',       
        'views/reports_views.xml',
        'views/action_balance_report.xml',
        'views/action_books_reports.xml',
        'views/actions_inform_sales.xml',
        'reports/balance_report.xml',
        'reports/balance_report_template.xml',
        'reports/consecutive_audit_report.xml',
        'reports/consecutive_audit_report_template.xml',
        'reports/accounting_accrual_report_template.xml',
        'reports/report_accounting_receipt.xml',
        'reports/report_accounting_receipt_template.xml',
        'views/actions_balance_cxc_cxp_report.xml',
        'views/actions_pivot_cxc_report.xml',
        'views/actions_tracking_activities.xml',
        'views/actions_consecutive_audit_report.xml',
        'views/actions_co_cgn_inform.xml',
        'views/menus.xml',
    ],
    'license': 'LGPL-3',
}
