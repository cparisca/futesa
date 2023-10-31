# -*- coding: utf-8 -*-

from odoo import models, fields, api,tools, _
from odoo.exceptions import UserError, except_orm, UserError
import itertools
import psycopg2
from datetime import datetime

class HrSalaryIncreaseEmployees(models.Model):
    _name = 'hr.increment.employees'
    _description = 'Salary Increments Wizard'
    employee_ids = fields.Many2many('hr.employee', 'hr_employee_increase_rel', 'increment_id', 'employee_id', 'Employees')

    
    def compute_increment(self):
        increments = self.env['hr.salary.increase.line']
        [data] = self.read()
        active_id = self.env.context.get('active_id')
        if not data['employee_ids']:
            raise UserError(_("You must select employee(s) to generate Increment(s)."))
        for employee in self.env['hr.employee'].browse(data['employee_ids']):
            res = {
                'employee_id': employee.id,
                'increase_id':active_id,
                'include':True,
            }
            # raise UserError(self.env['hr.salary.increase.line'].search([('increase_id','=',active_id)]))
            for emp in self.env['hr.salary.increase.line'].search([('increase_id','=',active_id)]):
                if emp.employee_id == employee:
                    raise UserError('You cannot Set Employee Twice in the same Increment!')
            increments += self.env['hr.salary.increase.line'].create(res)
        return {'type': 'ir.actions.act_window_close'}