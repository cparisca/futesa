# -*- coding: utf-8 -*-
##############################################################################

from odoo import fields, models
from datetime import datetime
from odoo.exceptions import UserError
import calendar
from odoo.exceptions import ValidationError

MONTH_SELECTION = [
    ('1', "ENERO"), ('2', "FEBRERO"), ('3', "MARZO"), ('4', "ABRIL"),
    ('5', "MAYO"), ('6', "JUNIO"), ('7', "JULIO"), ('8', "AGOSTO"),
    ('9', "SETIEMBRE"), ('10', "OCTUBRE"), ('11', "NOVIEMBRE"),
    ('12', "DICIEMBRE")]


def year_now():
    return datetime.now().year

YEAR_SELECTION = [(str(year), year) for year in range(2015, year_now()+3)]


def stryear(): return datetime.now().strftime('%Y')


def strmonth(): return datetime.now().strftime('%m')


class HRLoanEmployee(models.Model):
    _name = 'hr.loan.employee'
    _description = 'Prestamos Empleados'
    _rec_name = 'employee_id'
    #_order = 'sequence'

    employee_id = fields.Many2one('hr.employee','Empleado',
        required=True)
    amount = fields.Float('Monto',
        required=True)
    date = fields.Date('Fecha',
        default=lambda self:datetime.now().date())
    qty_to_paid = fields.Integer('Cantidad de Meses a pagar',
        required=True)
    qty_mnth_grace = fields.Integer('Meses de gracia',
        required=True, default=0)
    line_ids = fields.One2many('hr.loan.employee.line',
        'loan_id','Meses')
    state = fields.Selection([('draft','Borrador'),
        ('tovalidate','A validar'),('validate','Validado')], default="draft")
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.user.company_id,
        required=True, index=True, readonly=True)
    type_loan = fields.Selection([('advance','Adelanto'),
        ('loan','Prestamo')],'Tipo')

    def create_lines(self):
        line = self.env['hr.loan.employee.line']

        if self.amount > 0:
            month_actual = self.date.month
            year_actual = self.date.year
            month_actual += self.qty_mnth_grace
            for i in range(0,self.qty_to_paid):
                if month_actual == 13:
                    month_actual = 1
                    year_actual += 1
                dictl = {
                    'month_line':str(month_actual),
                    'amount':(self.amount/self.qty_to_paid),
                    'year_line':str(year_actual),
                    'loan_id':self.id
                    }
                line.create(dictl)
                month_actual += 1

            self.state = 'tovalidate'
        else:
            raise UserError("El monto debe ser positivo")

    def validate_loan(self):
        total = 0
        for i in self.line_ids:
            total += i.amount

        if total != self.amount:
            raise UserError("El monto total de las lineas debe ser igual a: "+ str(self.amount))

        if self.type_loan == 'advance':

            input_type_id = self.env.ref('hr_others_incomes_expenses.payslip_input_type_adel')
            name_income = 'Adelanto'
        else:
            input_type_id = self.env. ref('hr_others_incomes_expenses.payslip_input_type_pres')
            name_income = 'Prestamo'
        for i in self.line_ids:
            last_day_month = i.year_line + '-'+i.month_line+'-'+str(calendar.monthrange(int(i.year_line),int(i.month_line))[1])

            if self.env['hr.others.incomes.expenses.line'].search([('loan_line_id','=',i.id)]):
                if self.env['hr.others.incomes.expenses.line'].search([('loan_line_id','=',i.id)]).other_income_expense_id.state != 'validate':
                    self.env['hr.others.incomes.expenses.line'].search([('loan_line_id','=',i.id)]).write({
                        'amount':i.amount,
                        })
            else:
                if self.env['hr.others.incomes.expenses'].search([('date','=',last_day_month),
                    ('input_type_id','=',input_type_id.id)]):
                    income= self.env['hr.others.incomes.expenses'].search([('date','=',last_day_month),
                    ('input_type_id','=',input_type_id.id)])
                    income.write({
                        'line_ids':[(0,0,{
                            'employee_id':self.employee_id.id,
                            'amount':i.amount,
                            'loan_line_id':i.id
                            })]
                        })
                else:
                    self.env['hr.others.incomes.expenses'].create({
                        'name':name_income,
                        'input_type_id':input_type_id.id,
                        'date':last_day_month,
                        'line_ids':[(0,0,{
                            'employee_id':self.employee_id.id,
                            'amount':i.amount,
                            'loan_line_id':i.id
                            })]
                    })
        self.state = 'validate'

    def return_to_validate(self):
        self.state = 'tovalidate'


class HRLoanEmployeeLine(models.Model):
    _name = 'hr.loan.employee.line'
    _description = 'Prestamos Empleados'
    _rec_name = 'month_line'
    #_order = 'sequence'

    month_line = fields.Selection(MONTH_SELECTION,'Mes')
    year_line = fields.Char('Año')
    amount = fields.Float('Monto')
    loan_id = fields.Many2one('hr.loan.employee','Prestamo')

    def write(self, vals):
        other_id = self.env['hr.others.incomes.expenses.line'].search([('loan_line_id','=',self.id)])
        if other_id:
            if other_id.other_income_expense_id.state == 'validate':
                raise ValidationError("No se puede modificar esta linea ya que el registro en Otros Ingresos o Egresos se encuentra validado")
        return super(HRLoanEmployeeLine, self).write(vals)

class HrOthersIncomesExpensesLine(models.Model):
    _inherit = 'hr.others.incomes.expenses.line'
    
    loan_line_id = fields.Many2one('hr.loan.employee.line')

