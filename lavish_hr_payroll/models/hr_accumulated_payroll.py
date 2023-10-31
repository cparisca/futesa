from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta

class hr_accumulated_payroll(models.Model):
    _name = 'hr.accumulated.payroll'
    _description = 'Acumulados de nómina'

    employee_id = fields.Many2one('hr.employee', string='Empleado')    
    employee_identification = fields.Char('Identificación empleado')
    salary_rule_id = fields.Many2one('hr.salary.rule',string='Regla salarial', required=True)
    date = fields.Date('Fecha', required=True)
    amount = fields.Float(string='Valor')       

    @api.model
    def create(self, vals):
        if vals.get('employee_identification'):
            obj_employee = self.env['hr.employee'].search([('identification_id', '=', vals.get('employee_identification'))])            
            vals['employee_id'] = obj_employee.id
        if vals.get('employee_id'):
            obj_employee = self.env['hr.employee'].search([('id', '=', vals.get('employee_id'))])            
            vals['employee_identification'] = obj_employee.identification_id            
        
        res = super(hr_accumulated_payroll, self).create(vals)
        return res               