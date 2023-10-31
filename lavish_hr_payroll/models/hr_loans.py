# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta

class HrLoans(models.Model):
    _name = 'hr.loans'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "HR Solicitud de Prestamo"
    
    def _compute_prestamo_amount(self):
        total_paid = 0.0
        for prestamo in self:
            for line in prestamo.prestamo_lines:
                if line.paid:
                    total_paid += line.amount
            balance_amount = prestamo.prestamo_amount - total_paid
            self.total_amount = prestamo.prestamo_amount
            self.balance_amount = balance_amount
            self.total_paid_amount = total_paid

    def _compute_pending_amount(self):
        pend_total = 0
        pend_count = 0
        for loan in self: 
            for line in loan.prestamo_lines:
                if not line.paid:
                    pend_total += line.amount
                    pend_count += 1
        self.prestamo_pending_amount = pend_total
        self.prestamo_pending_count = pend_count

    name = fields.Char(string="Prestamo", default="/", readonly=True)
    date = fields.Date(string="Fecha de Desembolso", default=fields.Date.today(), readonly=False)
    employee_id = fields.Many2one('hr.employee', string="Empleado", required=True)
    department_id = fields.Many2one('hr.department', related="employee_id.department_id", readonly=True,
                                    string="Departamento")
    contract_id = fields.Many2one('hr.contract', string="Contrato", required=True, domain="[('employee_id','=', employee_id)]")
    entity_id = fields.Many2one('hr.employee.entities', string="Entidad", required=True)
    type_installment = fields.Selection([('period', 'N° de Periodos'),
                                        ('counts', 'N° de Cuotas (Personalizadas)')], 'Calcular en base a', required=True, default='period')
    installment = fields.Integer(string="N° de Periodos", default=1)
    installment_count = fields.Integer(string="N° de Cuotas (Personalizadas)", default=0)
    payment_date = fields.Date(string="Fecha de Primera Cuota", required=True, default=fields.Date.today())
    apply_charge = fields.Selection([('15','Primera quincena'),
                                    ('30','Segunda quincena'),
                                    ('0','Siempre')],'Aplicar cobro',  required=True, help='Indica a que quincena se va a aplicar la deduccion')
    salary_rule = fields.Many2one('hr.salary.rule', string="Regla salarial", required=True , tracking=True,)
    prestamo_lines = fields.One2many('hr.loans.line', 'prestamo_id', string="Detalle", index=True, ondelete='cascade' )    
    currency_id = fields.Many2one('res.currency', string='Moneda', required=True , tracking=True,)
    prestamo_original_amount = fields.Float(string="Valor Original del Préstamo", required=True, default=0)
    prestamo_amount = fields.Float(string="Valor Préstamo", required=True , tracking=True,)
    total_amount = fields.Float(string="Importe Total", readonly=True, compute='_compute_prestamo_amount')    
    total_paid_amount = fields.Float(string="Importe Total Pagado", compute='_compute_prestamo_amount')
    balance_amount = fields.Float(string="Saldo", compute='_compute_prestamo_amount')
    
    prestamo_pending_amount = fields.Float(string="Monto Cuotas Pendientes", compute='_compute_pending_amount')
    prestamo_pending_count = fields.Integer(string="N° Cuotas x Pagar", compute='_compute_pending_amount')
    payment_date_end = fields.Date(string="Fecha de Ultima Cuota", readonly=True)
    description = fields.Text(string='Descripción')

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('waiting_approval', 'Esperando Aprobación'),
        ('approve', 'Aprobado'),
        ('refuse', 'Rechazado'),
        ('cancel', 'Cancelado'),
    ], string="Estado", default='draft', tracking=True, copy=False)

    @api.model
    def create(self, values):        
        values['name'] = self.env['ir.sequence'].get('hr.loans.seq') or ' '
        res = super(HrLoans, self).create(values)
        return res

    def unlink(self):
        if self.state == 'approve':
            raise ValidationError(_('No se puede eliminar un prestamo Aprobado!'))
        return super(HrLoans, self).unlink()

    @api.onchange('employee_id')    
    def onchange_employee(self):
        obj_contratc = self.env['hr.contract'].search([('employee_id', '=', self.employee_id.id),('state','=','open')])
        if obj_contratc:
            for contract in obj_contratc:
                self.contract_id = contract.id        
        else:
            self.contract_id = False
            
    @api.onchange('apply_charge')    
    def apply_charge_function(self):
        date_today = fields.Date.today()
        day = int(date_today.day)
        month = int(date_today.month)
        year = int(date_today.year)
        if self.apply_charge == '15':
            #if day > 15:
            month = month + 1 if month != 12 else 1
            year = year + 1 if month == 12 else year                
            payment_date = str(year)+'-'+str(month)+'-15'
            self.payment_date = payment_date            
        if self.apply_charge == '30':
            #if day > 30:
            day = 30 if month != 2 else 28 
            month = month + 1 if month != 12 else 1
            year = year + 1 if month == 12 else year
            # else:
            #     day = 30 if month != 2 else 28 
            payment_date = str(year)+'-'+str(month)+'-'+str(day)
            self.payment_date = payment_date
        if self.apply_charge == '0':
            # if day < 15:
            #     payment_date = str(year)+'-'+str(month)+'-15'
            # else:
            #     day = 30 if month != 2 else 28 
            #     payment_date = str(year)+'-'+str(month)+'-'+str(day)
            month = month + 1 if month != 12 else 1
            year = year + 1 if month == 12 else year                
            payment_date = str(year)+'-'+str(month)+'-15'
            self.payment_date = payment_date    

    def clean_installment(self):
        self.prestamo_lines = [(5,0,0)]

    def action_submit(self):
        for prestamo in self:
            for line in prestamo.prestamo_lines:
                if line.amount <= 0:
                    raise UserError(_('Error: debe ingresar montos positivos para las cuotas'))

        self.write({'state': 'waiting_approval'})

    def action_refuse(self):
        self.write({'state': 'refuse'})
    
    def action_cancel(self):
        for record in self:
            obj_concept = self.env['hr.contract.concepts'].search([('contract_id','=',record.contract_id.id),('loan_id','=',record.id)])
            obj_concept.write({'state': 'cancel'})
            record.write({'state': 'cancel'})

    def action_approve(self):
        for data in self:
            if not data.prestamo_lines:
                raise UserError(_('Error: aún no ha calculado las cuotas para el pago'))
            else:
                #Registrar como concepto en el contrato del empleado
                amount = 0
                for detail in data.prestamo_lines:
                    amount = detail.amount
                    
                data = {'input_id': data.salary_rule.id,
                        'show_voucher': True,
                        'period': 'limited',
                        'date_start': data.payment_date,
                        'date_end': data.payment_date_end,
                        'amount': amount,
                        'aplicar': data.apply_charge,
                        'partner_id': data.entity_id.id,
                        'contract_id': data.contract_id.id,
                        'loan_id': data.id,
                        'state':'done'}

                self.env['hr.contract.concepts'].create(data)
                self.write({'state': 'approve'})

    def compute_installment(self):
        total_lines = 0
        
        for prestamo in self:
            date_pay = prestamo.payment_date
            if (date_pay.month != 2 and date_pay.day != 15 and date_pay.day != 30) or (date_pay.month == 2 and date_pay.day != 28 and date_pay.day != 15):
                if date_pay.month == 2:
                    raise UserError(_('Atención: La fecha de la primera cuota debe ser un día 15 o 28'))
                else:
                     raise UserError(_('Atención: La fecha de la primera cuota debe ser un día 15 o 30'))
            for line in prestamo.prestamo_lines:
                total_lines += line.amount
                date_last = line.date
            if int(total_lines) > 0:
               date_pay = date_last 
            if int(total_lines) >= int(prestamo.prestamo_amount):
                raise UserError(_('Atención: ya se han calculado las cuotas. Bórrela(s) si desea recalcular el pago del saldo pendiente'))
            else:
                if prestamo.type_installment == 'counts':
                    amount = (prestamo.prestamo_amount - total_lines) / prestamo.installment_count
                    date_start = date_pay
                    date_end = date_pay
                    for i in range(1, prestamo.installment_count + 1):
                        self.env['hr.loans.line'].create({
                            'date': date_start,
                            'amount': amount,
                            'currency_id': prestamo.currency_id.id,
                            'employee_id': prestamo.employee_id.id,
                            'prestamo_id': prestamo.id})
                        if prestamo.apply_charge == '0':
                            date_end = date_start
                            if date_start.day == 15:
                                year = int(date_start.year)
                                month = int(date_start.month)
                                day = 30 if month != 2 else 28
                                date_start = str(year)+'-'+str(month)+'-'+str(day)
                                date_start = datetime.strptime(date_start, '%Y-%m-%d').date()
                            else:
                                year = int(date_start.year)+1 if int(date_start.month) == 12 else int(date_start.year)
                                month = 1 if int(date_start.month) == 12 else int(date_start.month)+1
                                day = 15
                                date_start = str(year) + '-' + str(month) + '-' + str(day)
                                date_start = datetime.strptime(date_start, '%Y-%m-%d').date()
                        else:
                            date_end = date_start
                            date_start = date_pay + relativedelta(months=i)
                    self.payment_date_end = date_end
                else:
                    if prestamo.apply_charge == '0':
                        amount = (prestamo.prestamo_amount - total_lines) / (prestamo.installment*2)
                        date_start = date_pay
                        date_end = date_pay
                        for i in range(1, prestamo.installment + 1):
                            # Primera Quincena
                            day = 15
                            month = int(date_start.month)
                            year = int(date_start.year)
                            self.env['hr.loans.line'].create({
                                'date': str(year)+'-'+str(month)+'-'+str(day),
                                'amount': amount,
                                'currency_id': prestamo.currency_id.id,
                                'employee_id': prestamo.employee_id.id,
                                'prestamo_id': prestamo.id})
                            # Segunda Quincena
                            day = 30 if month != 2 else 28
                            self.env['hr.loans.line'].create({
                                'date': str(year)+'-'+str(month)+'-'+str(day),
                                'amount': amount,
                                'currency_id': prestamo.currency_id.id,
                                'employee_id': prestamo.employee_id.id,
                                'prestamo_id': prestamo.id})
                            date_end = str(year)+'-'+str(month)+'-'+str(day)
                            date_start = date_pay + relativedelta(months=i)
                        self.payment_date_end = date_end
                    else:
                        amount = (prestamo.prestamo_amount - total_lines) / prestamo.installment
                        date_start = date_pay
                        date_end = date_pay
                        for i in range(1, prestamo.installment + 1):
                            self.env['hr.loans.line'].create({
                                'date': date_start,
                                'amount': amount,
                                'currency_id': prestamo.currency_id.id,
                                'employee_id': prestamo.employee_id.id,
                                'prestamo_id': prestamo.id})
                            date_end = date_start
                            date_start = date_pay + relativedelta(months=i)
                        self.payment_date_end = date_end
        return True

        
class HrLoansLine(models.Model):
    _name = "hr.loans.line"
    _description = "Detalle del prestamo"

    currency_id = fields.Many2one('res.currency', string='Moneda', required=True, default=lambda self: self.env.user.company_id.currency_id)
    prestamo_id = fields.Many2one('hr.loans', string="Prestamo", required=True, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string="Empleado", required=True)
    date = fields.Date(string="Fecha Cuota", required=True)    
    amount = fields.Float(string="Importe", required=True)
    paid = fields.Boolean(string="Pagado")
    payslip_id = fields.Many2one('hr.payslip', string="Ref. Liquidación")


class hr_contract_concepts(models.Model):
    _inherit = 'hr.contract.concepts'
    
    loan_id = fields.Many2one('hr.loans', 'Prestamo', readonly=True)

    def change_state_cancel(self):
        super(hr_contract_concepts, self).change_state_cancel()
        if self.loan_id:
            obj_loan = self.env['hr.loans'].search([('id', '=', self.loan_id.id)])
            obj_loan.write({'state': 'cancel'})

    _sql_constraints = [('change_contract_uniq', 'unique(input_id, contract_id, loan_id)', 'Ya existe esta regla para este contrato, por favor verficar.')]