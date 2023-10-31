# -*- coding: utf-8 -*-
{
    'name': "Incremento de salario",
    'summary': """Incremento de salario""",
    'description': """Incremento de salario""",
    'category': 'HR',
    'version': '15.0.1',
    'sequence': 8,
    'author': 'Lavish',
    'license': 'OPL-1',
    'depends': ['hr', 'hr_contract','hr_payroll'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/hr_increament_by_employees_views.xml',
        'views/hr_salary_increase_views.xml',
        'views/hr_payroll_view.xml',
        'data/mail_data.xml',
        'data/hr_payroll_data.xml',
    ],
    'demo': [
    ],
}
