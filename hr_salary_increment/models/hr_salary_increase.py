# -*- coding: utf-8 -*-

from odoo import models, fields, api,tools, _
from odoo.exceptions import UserError, except_orm, UserError
import itertools
import psycopg2
from datetime import datetime
from dateutil import relativedelta

class HrSalaryIncrease(models.Model):
    _name = 'hr.salary.increase'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Salary Increments'

    name = fields.Char(string='Referencia', required=True)
    employee_id = fields.Many2one('hr.employee','Empleado')
    date = fields.Datetime('Fecha efectiva')
    date_applied_on = fields.Datetime('Aplicado en')
    percentage = fields.Float(string="Porcentaje(%)")
    increase_type = fields.Selection([('promotion','Promoción'),('annual','Incremento Anual'),('bonus','Bono ')],'Tipo de aumento',default='annual')
    applied_for = fields.Selection([('employee','Empleado'),('batch','Masivo')],'Solicitud',default='batch')
    state = fields.Selection([('draft', 'Draft'), ('hr_mgr', 'Waitting HR Manager'),('confirm', 'Confirmed'), ('cancel', 'Rejected')], default='draft',)
    computed = fields.Boolean('¿Está computado?', default=False)
    company_id = fields.Many2one('res.company', 'Empresa', required=True, index=True, default=lambda self: self.env.company)
    

    line_ids = fields.One2many('hr.salary.increase.line', 'increase_id', string='Lines')

    def update_activities(self):
        for rec in self:
            users = []
            if rec.state not in ['draft','hr_mgr','confirm','cancel']:
                continue
            message = ""
            if rec.state == 'hr_mgr':
                users = self.env.ref('hr.group_hr_manager').users
                message = "Approve"

            elif rec.state == 'cancel':
                users = [self.create_uid]
                message = "Rejected"
            for user in users:
                self.activity_schedule('hr_salary_increment.mail_act_approval', user_id=user.id, note=message)

    
    @api.constrains('date','date_applied_on')
    def check_date(self):
        if self.date_applied_on and self.date_applied_on < self.date:
            raise UserError('¡La fecha de aplicación debe ser mayor que la fecha de vigencia!')


    def action_generate(self):
        domain = []
        employees = self.env['hr.employee'].search(domain)
        for employee in employees:
            if employee.contract_id:
                self.env['hr.salary.increase.line'].create({
                    'employee_id': employee.id,
                    'increase_id': self.id
                })
    

    def action_compute(self):
        for rec in self:
            for line in rec.line_ids:
                if not line.employee_id.contract_id:
                    continue
                amount = line.amount
                if line.employee_id.contract_id and line.increase_type in ['bonus']:
                    perc = line.percentage
                    if perc > 0:
                        amount = (line.employee_id.contract_id.wage * perc) / 100

                if line.employee_id.contract_id and line.increase_type in ['promotion', 'annual']:
                    perc = rec.percentage
                    if perc > 0:
                        amount = (line.employee_id.contract_id.wage * perc) / 100
                line.amount = amount
                line.basic = line.employee_id.contract_id.wage
                line.new_basic = line.employee_id.contract_id.wage + amount
        self.computed = True

    def action_submit(self):
        if not self.computed:
            raise UserError('Por favor calcule antes de enviar')
        for rec in self:
            rec.state = "hr_mgr"
            rec.update_activities()


    def action_confirm(self):
        self.action_compute()
        for line in self.line_ids:
            amount = line.amount
            if not line.date_applied_on:
                raise UserError('Establezca Fecha de aplicación')
            for rec in self.env['hr.payslip'].search([('employee_id','=',line.employee_id.id),('date_from','<=',line.date_applied_on),('date_to','>=',line.date_applied_on),('state','not in',['draft'])]):
                raise UserError('No puedes aplicar Bono para este Mes, ¡La Nómina ya está Confirmada! %s ' % (rec.employee_id.name) )
            if line.employee_id.contract_id and line.increase_type in ['bonus']:
                perc = line.percentage
                if perc > 0:
                    amount = (line.employee_id.contract_id.wage * perc) / 100
            if line.employee_id.contract_id and line.increase_type in ['promotion','annual']:
                perc = self.percentage
                if perc > 0:
                    amount = (line.employee_id.contract_id.wage * perc) / 100
                line.employee_id.contract_id.change_wage_ids.create({'wage': line.new_basic,
                                                                    'date_start' : self.date.date(),
                                                                    'contract_id':  line.employee_id.contract_id.id, }) 
                line.employee_id.contract_id.change_wage()
            line.amount = amount
        self.state = "confirm"
        self.activity_unlink(['hr_salary_increment.mail_act_approval'])

    def action_reject(self):
        for rec in self:
            rec.state = 'cancel'
        self.activity_unlink(['hr_salary_increment.mail_act_approval'])

    
    def action_reset_draft(self):
        for rec in self:
            rec.state = 'draft'



class HRSalaryIncreaseLine(models.Model):
    _name = 'hr.salary.increase.line'
    _description = 'Salary Increments Line'

    increase_id = fields.Many2one('hr.salary.increase')
    employee_id = fields.Many2one('hr.employee', string="Name")
    include = fields.Boolean("Include?", default=True)
    date_applied_on = fields.Datetime('Applied On',related="increase_id.date_applied_on")
    date = fields.Datetime('Effective Date',related="increase_id.date")
    no_of_month = fields.Float(compute='compute_no_month')
    amount = fields.Float()
    state = fields.Selection([('draft', 'Draft'), ('hr_mgr', 'Waitting HR Manager'), ('confirm', 'Confirmed'), ('cancel', 'Rejected')],default='draft')
    note = fields.Char()
    percentage = fields.Float(string="Percentage(%)")
    computed = fields.Boolean('Is Computed ?', related="increase_id.computed")

    
    increase_type = fields.Selection('Increase Type',related="increase_id.increase_type",readonly="True")
    basic = fields.Float("Basic")
    total_allowances = fields.Float("Total Allowances",)

    new_basic = fields.Float("New Basic")
    new_total_allowances = fields.Float("New Total Allowances",)


    @api.constrains('date','date_applied_on')
    def check_date(self):
        if self.date_applied_on < self.date:
            raise UserError('Applied On Date must be greater than Effective Date!')

    @api.depends('date','date_applied_on')
    def compute_no_month(self):
        for rec in self:
            rec.no_of_month = 0
            if rec.date and rec.date_applied_on:
                try:
                    effective_date = datetime.strptime(str(rec.date), '%Y-%m-%d %H:%M:%S')
                    applied_on_date = datetime.strptime(str(rec.date_applied_on), '%Y-%m-%d %H:%M:%S')
                except:
                    d1,m1 = str(rec.date).split('.')
                    d2,m2 = str(rec.date_applied_on).split('.')
                    effective_date = datetime.strptime(d1, '%Y-%m-%d %H:%M:%S')
                    applied_on_date = datetime.strptime(d2, '%Y-%m-%d %H:%M:%S')
                date = relativedelta.relativedelta(applied_on_date, effective_date)
                if date.months < 1 or rec.increase_type == 'promotion':
                    rec.no_of_month = 1 
                else:
                    rec.no_of_month = date.months