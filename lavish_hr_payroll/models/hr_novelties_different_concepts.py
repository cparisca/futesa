from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class hr_novelties_different_concepts(models.Model):
    _name = 'hr.novelties.different.concepts'
    _description = 'Novedades por conceptos diferentes'

    employee_id = fields.Many2one('hr.employee', string='Empleado', index=True)
    employee_identification = fields.Char('Identificación empleado')
    salary_rule_id = fields.Many2one('hr.salary.rule', string='Regla salarial', required=True, domain=[('novedad_ded', '=', 'Noved')] )
    dev_or_ded = fields.Selection('Naturaleza',related='salary_rule_id.dev_or_ded',store=True, readonly=True)    
    date = fields.Date('Fecha', required=True)
    amount = fields.Float('Valor', required=True)
    description = fields.Char('Descripción') 
    partner_id = fields.Many2one('hr.employee.entities', 'Entidad') 
    payslip_id = fields.Many2one('hr.payslip', 'Pagado en nomina', readonly=True)
    @api.constrains('amount')
    def _check_amount(self):  
        for record in self:
            if record.dev_or_ded == 'deduccion' and record.amount > 0:
                raise UserError(_('La regla es de tipo deducción, el valor ingresado debe ser negativo'))  
            if record.dev_or_ded == 'devengo' and record.amount < 0:
                raise UserError(_('La regla es de tipo devengo, el valor ingresado debe ser positivo')) 

    @api.model
    def create(self, vals):
        if vals.get('employee_identification'):
            obj_employee = self.env['hr.employee'].search([('identification_id', '=', vals.get('employee_identification'))])            
            vals['employee_id'] = obj_employee.id
        if vals.get('employee_id'):
            obj_employee = self.env['hr.employee'].search([('id', '=', vals.get('employee_id'))])            
            vals['employee_identification'] = obj_employee.identification_id            
        
        res = super(hr_novelties_different_concepts, self).create(vals)
        return res
    def action_delete_novedad(self):
        self.unlink()