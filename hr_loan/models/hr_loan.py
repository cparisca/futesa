# -*- coding: utf-8 -*-

from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class HrLoanType(models.Model):
    _name = 'hr.loan.type'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Loan Type"

    name = fields.Char()
    rule_code = fields.Char(string="Codigo")
    rule_structure_id = fields.Many2one('hr.payroll.structure', string="estructura salarial")
    category_id = fields.Many2one('hr.salary.rule.category', string="Categoria")
    default_account = fields.Many2one('account.account',string="Account name")
    credit_account_id = fields.Many2one('account.account', string="Cuenta de débito")
    debit_account_id = fields.Many2one('account.account', string="crédito de cuenta")
    journal_id = fields.Many2one('account.journal', string="Diario")

    def write(self, vals):
        res = super(HrLoanType, self).write(vals)
        if vals.get('rule_code', False) or vals.get('name', False) or vals.get('rule_structure_id', False):
            is_rule_exite = self.env['hr.salary.rule'].search(
                [('code', '=', self.rule_code), ('name', '=', self.name), ('struct_id', '=', self.rule_structure_id.id)], limit=1)
            if not is_rule_exite:
                amount_python_compute = 'result = inputs.' + self.rule_code + ' and - (inputs.' + self.rule_code + '.amount)'
                condition_python = 'result = inputs.' + self.rule_code + ' and (inputs.' + self.rule_code + '.amount)'

                deduct_rules_sequence = self.env['hr.salary.rule'].search([('category_id', '=', self.category_id.id)], order="sequence desc", limit=1).sequence
                obj = self.env['hr.salary.rule'].create({
                    'name': self.name,
                    'sequence': deduct_rules_sequence,
                    'dev_or_ded': "deduccion",
                    'category_id': self.category_id.id,
                    'condition_select': "python",
                    'condition_python': condition_python,
                    'amount_select': "code",
                    'amount_python_compute': amount_python_compute,
                    'code': self.rule_code,
                    'struct_id': self.rule_structure_id.id
                })
            return res

    @api.model
    def create(self, values):
        res = super(HrLoanType, self).create(values)
        is_rule_exite = self.env['hr.salary.rule'].search(
            [('code', '=', res.rule_code), ('name', '=', res.name),
             ('struct_id', '=', res.rule_structure_id.id)], limit=1)
        if not is_rule_exite:
            amount_python_compute = 'result = inputs.'+res.rule_code+' and - (inputs.'+res.rule_code+'.amount)'
            condition_python = 'result = inputs.'+res.rule_code+' and (inputs.'+res.rule_code+'.amount)'

            deduct_rules_sequence = self.env['hr.salary.rule'].search([('category_id', '=', self.category_id.id)], order="sequence desc", limit=1).sequence

            input_type = self.env['hr.payslip.input.type'].create({
                'code': res.rule_code,
                'name': res.name,
            })

            obj = self.env['hr.salary.rule'].create({
                        'name': res.name,
                        'sequence': deduct_rules_sequence,
                        'dev_or_ded': "deduccion",
                        'category_id': self.category_id.id,
                        'condition_select': "python",
                        'condition_python': condition_python,
                        'amount_select': "code",
                        'amount_python_compute': amount_python_compute,
                        'code': res.rule_code,
                        'struct_id': res.rule_structure_id.id
            })
        return res


class HrLoan(models.Model):
    _name = 'hr.loan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Loan Request"

    @api.model
    def default_get(self, field_list):
        result = super(HrLoan, self).default_get(field_list)
        if result.get('user_id'):
            ts_user_id = result['user_id']
        else:
            ts_user_id = self.env.context.get('user_id', self.env.user.id)
        result['employee_id'] = self.env['hr.employee'].search([('user_id', '=', ts_user_id)], limit=1).id
        return result

    def _compute_loan_amount(self):
        total_paid = 0.0
        for loan in self:
            for line in loan.loan_lines:
                if line.paid:
                    total_paid += line.amount
            balance_amount = loan.loan_amount - total_paid
            loan.total_amount = loan.loan_amount
            loan.balance_amount = balance_amount
            loan.total_paid_amount = total_paid

    name = fields.Char(string="Numero", default="/", readonly=True, help="Name of the loan")
    reason = fields.Char(string="Razón")
    is_responsible_approve = fields.Boolean(compute="is_responsible_approve_chk", default=False)
    responsible_approve_id = fields.Many2one('res.users', string='Responsable de Aprobar', required=True,
                                 domain=lambda self: [('groups_id', '=', self.env.ref('hr_loan.group_loan_request_approver').id)])
    date = fields.Date(string="Fecha", default=fields.Date.today(), help="Date")
    employee_id = fields.Many2one('hr.employee', string="Employee", required=True, help="Employee",  domain=[('contract_id', '!=', False)])
    department_id = fields.Many2one('hr.department', related="employee_id.department_id", readonly=True,
                                    string="Departamento", help="Employee")
    installment = fields.Integer(string="Número de cuotas", default=1, help="Number of installments")
    payment_date = fields.Date(string="Fecha de inicio del pago", required=True, default=fields.Date.today(), help="Date of "
                                                                                                             "the "
                                                                                                             "paymemt")
    loan_lines = fields.One2many('hr.loan.line', 'loan_id', string="Loan Line", index=True)
    company_id = fields.Many2one('res.company', 'Empresa', readonly=True, help="Company",
                                 default=lambda self: self.env.user.company_id,
                                 states={'draft': [('readonly', False)]})
    currency_id = fields.Many2one('res.currency', string='Moneda', required=True, help="Currency",
                                  default=lambda self: self.env.user.company_id.currency_id)
    job_position = fields.Many2one('hr.job', related="employee_id.job_id", readonly=True, string="Job Position",
                                   help="Job position")
    loan_amount = fields.Float(string="Loan Amount", required=True, help="Loan amount")
    total_amount = fields.Float(string="Total Amount", store=True, readonly=True, compute='_compute_loan_amount',
                                help="Total loan amount")
    balance_amount = fields.Float(string="Balance", store=True, compute='_compute_loan_amount',
                                  help="Balance amount")
    total_paid_amount = fields.Float(string="Cantidad total pagada", store=True, compute='_compute_loan_amount',
                                     help="Total paid amount")
    loan_type_id = fields.Many2one('hr.loan.type', string="Tipo de Prestamo")

    move_id = fields.Many2one('account.move', 'Accounting Entry', readonly=True, copy=False)
    payment_id = fields.Many2one('account.payment', 'Accounting Entry', readonly=True, copy=False)
    journal_id = fields.Many2one('account.journal', string="Diario De Pago")
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('waiting_approval_1', 'Enviar'),
        ('approve', 'Aprobar'),
        ('refuse', 'Rechazar'),
        ('cancel', 'Cancelar'),
    ], string="State", default='draft', copy=False, )

    prestamo_pending_amount = fields.Float(string="Monto Cuotas Pendientes", compute='_compute_pending_amount')
    prestamo_pending_count = fields.Integer(string="N° Cuotas x Pagar", compute='_compute_pending_amount')
    payment_date_end = fields.Date(string="Fecha de Ultima Cuota", readonly=True)
    type_installment = fields.Selection([('period', 'N° de Periodos'),
                                        ('counts', 'N° de Cuotas (Personalizadas)')], 'Calcular en base a', required=True, default='period')
    apply_charge = fields.Selection([('15','Primera quincena'),
                                    ('30','Segunda quincena'),
                                    ('0','Siempre')],'Aplicar cobro',  required=True, help='Indica a que quincena se va a aplicar la deduccion')
    def _compute_pending_amount(self):
        pend_total = 0
        pend_count = 0
        for loan in self: 
            for line in loan.loan_lines:
                if not line.paid:
                    pend_total += line.amount
                    pend_count += 1
        self.prestamo_pending_amount = pend_total
        self.prestamo_pending_count = pend_count

    @api.onchange('loan_lines')
    def onchange_total_paid_amount(self):
        total = 0.0
        for line in self.loan_lines:
            total += line.amount
        print("total", total)
        if total > self.total_amount:
            raise ValidationError(_('El monto total debe ser mayor o igual al monto total pagado'))

    @api.model
    def create(self, values):
        values['name'] = self.env['ir.sequence'].get('hr.loan.seq') or ' '
        res = super(HrLoan, self).create(values)
        return res

    def compute_installment(self):
        total_lines = 0
        
        for prestamo in self:
            date_pay = prestamo.payment_date
            if (date_pay.month != 2 and date_pay.day != 15 and date_pay.day != 30) or (date_pay.month == 2 and date_pay.day != 28 and date_pay.day != 15):
                if date_pay.month == 2:
                    raise UserError(_('Atención: La fecha de la primera cuota debe ser un día 15 o 28'))
                else:
                     raise UserError(_('Atención: La fecha de la primera cuota debe ser un día 15 o 30'))
            for line in prestamo.loan_lines:
                total_lines += line.amount
                date_last = line.date
            if int(total_lines) > 0:
               date_pay = date_last 
            if int(total_lines) >= int(prestamo.loan_amount):
                prestamo.loan_lines = [(5,0,0)]
                #raise UserError(_('Atención: ya se han calculado las cuotas. Bórrela(s) si desea recalcular el pago del saldo pendiente'))
            else:
                if prestamo.type_installment == 'counts':
                    amount = (prestamo.loan_amount - total_lines) / prestamo.installment
                    date_start = date_pay
                    date_end = date_pay
                    for i in range(1, prestamo.installment + 1):
                        self.env['hr.loan.line'].create({
                            'date': date_start,
                            'amount': amount,
                            'currency_id': prestamo.currency_id.id,
                            'employee_id': prestamo.employee_id.id,
                            'loan_id': prestamo.id})
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
                        amount = (prestamo.loan_amount - total_lines) / (prestamo.installment*2)
                        date_start = date_pay
                        date_end = date_pay
                        for i in range(1, prestamo.installment + 1):
                            # Primera Quincena
                            day = 15
                            month = int(date_start.month)
                            year = int(date_start.year)
                            self.env['hr.loan.line'].create({
                                'date': str(year)+'-'+str(month)+'-'+str(day),
                                'amount': amount,
                                'currency_id': prestamo.currency_id.id,
                                'employee_id': prestamo.employee_id.id,
                                'loan_id': prestamo.id})
                            # Segunda Quincena
                            day = 30 if month != 2 else 28
                            self.env['hr.loan.line'].create({
                                'date': str(year)+'-'+str(month)+'-'+str(day),
                                'amount': amount,
                                'currency_id': prestamo.currency_id.id,
                                'employee_id': prestamo.employee_id.id,
                                'loan_id': prestamo.id})
                            date_end = str(year)+'-'+str(month)+'-'+str(day)
                            date_start = date_pay + relativedelta(months=i)
                        self.payment_date_end = date_end
                    else:
                        amount = (prestamo.loan_amount - total_lines) / prestamo.installment
                        date_start = date_pay
                        date_end = date_pay
                        for i in range(1, prestamo.installment + 1):
                            self.env['hr.loan.line'].create({
                                'date': date_start,
                                'amount': amount,
                                'currency_id': prestamo.currency_id.id,
                                'employee_id': prestamo.employee_id.id,
                                'loan_id': prestamo.id})
                            date_end = date_start
                            date_start = date_pay + relativedelta(months=i)
                        self.payment_date_end = date_end
            self._compute_loan_amount()
        return True

    # def compute_installment(self):
    #     """This automatically create the installment the employee need to pay to
    #     company based on payment start date and the no of installments.
    #         """
    #     for loan in self:
    #         loan.loan_lines.unlink()
    #         date_start = datetime.strptime(str(loan.payment_date), '%Y-%m-%d')
    #         amount = loan.loan_amount / loan.installment
    #         for i in range(1, loan.installment_count + 1):
    #             self.env['hr.loan.line'].create({
    #                 'date': date_start,
    #                 'amount': amount,
    #                 'employee_id': loan.employee_id.id,
    #                 'loan_id': loan.id,

    #             })
    #             date_start = date_start + relativedelta(months=1)
    #         loan._compute_loan_amount()
    #     return True


    def action_refuse(self):
        moves = self.mapped('move_id')
        moves.filtered(lambda x: x.state == 'posted').button_cancel()
        # moves.unlink()
        return self.write({'state': 'refuse'})

    def action_submit(self):
        self.write({'state': 'waiting_approval_1'})
        self.activity_schedule('mail.mail_activity_data_todo', user_id=self.responsible_approve_id.id)

    def action_cancel(self):
        moves = self.mapped('move_id')
        moves.filtered(lambda x: x.state == 'posted').button_cancel()
        # moves.unlink()
        self.write({'state': 'cancel'})

    def action_reset_to_draft(self):
        moves = self.mapped('move_id')
        moves.filtered(lambda x: x.state == 'posted').button_cancel()
        # moves.unlink()
        self.write({'state': 'draft'})

    def action_approve(self):
        for data in self:
            if not data.loan_lines:
                raise ValidationError(_("Por favor calcule la cuota"))
            else:
                #self.action_create_journal_entry()
                self.action_create_payment()

                self.write({'state': 'approve'})

    def is_responsible_approve_chk(self):
        for rec in self:
            rec.is_responsible_approve = False
            if self.env.user.id == rec.responsible_approve_id.id and self.env.user.has_group('hr_loan.group_loan_request_approver'):
                rec.is_responsible_approve = True

    @api.model
    def _prepare_journal_entry_line(self, account,partner=False, debit=0, credit=0):
        vals = {
            "date_maturity": self.date,
            "debit": debit,
            "credit": credit,
            "partner_id": partner,
            "account_id": account
        }
        return vals

    @api.onchange('apply_charge')    
    def apply_charge_function(self):
        date_today = fields.Date.today()
        day = int(date_today.day)
        month = int(date_today.month)
        year = int(date_today.year)
        if self.apply_charge == '15':
            month = month + 1 if month != 12 else 1
            year = year + 1 if month == 12 else year                
            payment_date = str(year)+'-'+str(month)+'-15'
            self.payment_date = payment_date            
        if self.apply_charge == '30':
            day = 30 if month != 2 else 28 
            month = month + 1 if month != 12 else 1
            year = year + 1 if month == 12 else year
            payment_date = str(year)+'-'+str(month)+'-'+str(day)
            self.payment_date = payment_date
        if self.apply_charge == '0':
            month = month + 1 if month != 12 else 1
            year = year + 1 if month == 12 else year                
            payment_date = str(year)+'-'+str(month)+'-15'
            self.payment_date = payment_date 

    def clean_installment(self):
        self.loan_lines = [(5,0,0)]

    def action_create_journal_entry(self):
        debit_account_id = self.loan_type_id.debit_account_id
        credit_account_id = self.loan_type_id.credit_account_id
        journal = self.loan_type_id.journal_id
        if not debit_account_id :
            raise ValidationError(_("Agregue una cuenta de débito"))
        if not credit_account_id :
            raise ValidationError(_("Agregue una cuenta de crédito"))
        if not journal :
            raise ValidationError(_("Agregar diario"))
        if not self.employee_id.address_home_id.id :
            partner = self.env['res.partner'].create(
                    {'name': self.employee_id.name,
                     'street': self.employee_id.address or False,
                     })
            self.employee_id.address_home_id = partner.id
        move_lines = []

        # add total debit journal item
        move_lines.append([0, 0, self._prepare_journal_entry_line(debit_account_id.id,partner=self.employee_id.address_home_id.id, debit=self.total_amount)])
        # add total credit journal item
        move_lines.append([0, 0, self._prepare_journal_entry_line(credit_account_id.id, credit=self.total_amount)])
        vals = {
            'date': self.date,
            'journal_id': journal.id,
            'line_ids': move_lines
        }
        # print(vals)
        move = self.env['account.move'].create(vals)
        self.move_id = move.id
        return True

    def action_create_payment(self):
        payment_obj = self.env['account.payment']
        payment_obj.create({
            'payment_type':'outbound',
            'partner_type':'supplier',
            'currency_id': self.currency_id.id,
            'date': self.date,
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'partner_id':self.employee_id.address_home_id.id,
            'amount':self.loan_amount,
            'loan_type_id':self.loan_type_id.id,
            'is_loan': True,
            'destination_account_id':self.loan_type_id.default_account.id,

        })
        self.payment_id = payment_obj.id
        return True   

    def unlink(self):
        for loan in self:
            if loan.state not in ('draft', 'cancel'):
                raise UserError(
                    'No puede eliminar un préstamo que no está en estado de borrador o cancelado')
        return super(HrLoan, self).unlink()


class InstallmentLine(models.Model):
    _name = "hr.loan.line"
    _description = "Installment Line"

    date = fields.Date(string="Fecha de pago", required=True, help="Fecha")
    employee_id = fields.Many2one('hr.employee', string="Employee", help="Employee")
    amount = fields.Float(string="Monto", required=True, help="Amount")
    paid = fields.Boolean(string="Pagada", help="Paid")
    loan_id = fields.Many2one('hr.loan', string="Referencia", help="Loan")
    payslip_id = fields.Many2one('hr.payslip', string="Referencia Nomina", help="Payslip")
    currency_id = fields.Many2one('res.currency', string='Moneda', required=True, default=lambda self: self.env.user.company_id.currency_id)


    def unlink(self):
        for line in self:
            if line.paid:
                raise ValidationError(_('No se puede eliminar la línea paga'))
        return super(InstallmentLine, self).unlink()


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _compute_employee_loans(self):
        """This compute the loan amount and total loans count of an employee.
            """
        self.loan_count = self.env['hr.loan'].search_count([('employee_id', '=', self.id)])

    loan_count = fields.Integer(string="Loan Count", compute='_compute_employee_loans')
