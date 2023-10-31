from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class hr_absence_history(models.Model):
    _name = 'hr.absence.history'
    _description = 'Historico de ausencias'

    leave_type_id = fields.Many2one('hr.leave.type', string='Tipo de Tiempo Libre', required=True)
    star_date = fields.Date('Fecha de Inicio', required=True)
    end_date = fields.Date('Fecha de Final', required=True)
    days = fields.Integer('Días', required=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado')
    employee_identification = fields.Char('Identificación empleado')
    description = fields.Char(string='Descripción')

    @api.model
    def create(self, vals):
        if vals.get('employee_identification'):
            obj_employee = self.env['hr.employee'].search(
                [('identification_id', '=', vals.get('employee_identification'))])
            vals['employee_id'] = obj_employee.id
        if vals.get('employee_id'):
            obj_employee = self.env['hr.employee'].search([('id', '=', vals.get('employee_id'))])
            vals['employee_identification'] = obj_employee.identification_id

        res = super(hr_absence_history, self).create(vals)
        return res