# -*- coding: utf-8 -*-
{
    'name': "HR Loans",

    'summary': """
        Loan Requests to employees""",

    'description': """
        Loan Requests to employees
    """,
    'author': "Lavish",
    'category': 'Human Resources',
    'version': '0.1',
    'license': 'OPL-1',
    'depends': ['mail', 'hr', 'hr_payroll', 'hr_payroll_account'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/hr_loan_seq.xml',
        'data/salary_rule_loan.xml',
        'views/hr_loan.xml',
        'views/hr_payroll.xml',
    ]
}
