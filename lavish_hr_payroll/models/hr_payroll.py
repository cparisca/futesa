# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, SUPERUSER_ID , tools
from odoo.exceptions import UserError, ValidationError
from .browsable_object import BrowsableObject, InputLine, WorkedDays, Payslips, LeavedDays
import math

from collections import defaultdict, Counter
import calendar
from datetime import datetime, timedelta, date, time
from calendar import monthrange
from odoo import registry as registry_get
import math
import pytz
import odoo
import threading
import logging
from odoo.tools import float_round, date_utils, float_is_zero
from odoo.tools.float_utils import float_compare
from odoo.tools.misc import format_date
from dateutil.relativedelta import relativedelta
_logger = logging.getLogger(__name__)
DAY_TYPE = [
    ('W', 'Trabajado'),
    ('A', 'Ausencia'),
    ('X', 'Sin contrato'),
]

#---------------------------LIQUIDACIÓN DE NÓMINA-------------------------------#
class HrPayslipRun(models.Model):
    _name = 'hr.absence.days'
    _description = 'Ausencias'

    sequence = fields.Integer(string='Secuencia',required=True, index=True, default=5,
                              help='Use to arrange calculation sequence')
    payroll_id = fields.Many2one('hr.payslip', string='Payroll')
    employee_id = fields.Many2one('hr.employee', string='Employee')
    leave_type = fields.Char(string='Leave Type')
    total_days = fields.Float(string='Dias Totales')
    days_used = fields.Float(string='Dias a usar')
    days = fields.Float(string='Dias Usado',compute="_days_used")
    total = fields.Float(string='pendiente', compute="_total_leave")
    leave_id = fields.Many2one('hr.leave', string='Novedad')
    work_entry_type_id = fields.Many2one('hr.work.entry.type', related="leave_id.holiday_status_id.work_entry_type_id", string='Type', required=True, help="The code that can be used in the salary rules")

    
    @api.depends('total_days','days_used')
    def _total_leave(self):
        for rec in self:
            rec.total = rec.days_used + rec.days

    @api.depends('total_days', 'days_used')
    def _days_used(self):
        self.days = 0.0
        # leave_obj = self.env['hr.absence.days'] 

        # for rec in self:
        #     if not rec.payroll_id.date_to:
        #         continue  # Si no hay fecha 'date_to', pasamos al siguiente registro
            
        #     # Obtiene todos los leaves que cumplen con la condición sin iterar sobre ellos
        #     leaves = leave_obj.search([
        #         ('id', 'in', rec.leave_id.leave_ids.ids),
        #         ('payroll_id.date_to', '<', rec.payroll_id.date_to)
        #     ])
        #     # Calcula la suma de days_used
        #     total_days = sum(leave.days_used + (1 if leave.payroll_id.date_to and leave.payroll_id.date_to.day == 31 else 0) for leave in leaves)
            
        #     rec.days = total_days


class HrPayslipRun(models.Model):
    _name = 'hr.payslip.run'
    _inherit = ['hr.payslip.run','mail.thread', 'mail.activity.mixin']
    time_process = fields.Char(string='Tiempo ejecución')
    observations = fields.Text('Observaciones')
    definitive_plan = fields.Boolean(string='Plano definitivo generado')
    
    
    def compute_sheet_thread(self):
        for rec in self:
            for line in rec.slip_ids:
                if line.state == 'draft':
                    line.compute_sheet_thread()

    def compute_sheet(self):
        for rec in self:
            for line in rec.slip_ids:
                if line.state in ('draft', 'verify'):
                    line.compute_sheet()

    def compute_sheet_2(self):
        for rec in self:
            for line in rec.slip_ids:
                if line.state in ('draft', 'verify'):
                    line.compute_sheet_2()
    
    def action_payslip_done_2(self):
        for rec in self:
            for line in rec.slip_ids:
                if line.state in ('draft', 'verify','done'):
                    line.action_payslip_done_2()


    def assign_status_verify(self):
        for record in self:
            if len(record.slip_ids) > 0:
                record.write({'state':'verify'})
            else:
                raise ValidationError(_("No existen nóminas asociadas a este lote, no es posible pasar a estado verificar."))

    def action_validate(self):
        settings_batch_account = self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.module_hr_payroll_batch_account') or False
        slips_original = self.mapped('slip_ids').filtered(lambda slip: slip.state != 'cancel')
        if settings_batch_account == '1':  # Si en ajustes tiene configurado 'Crear movimiento contable por empleado' ejecutar maximo 200 por envio
            slips = slips_original.filtered(lambda x: len(x.move_id) == 0 or x.move_id == False)[0:200]
        else:
            slips = slips_original
        slips.action_payslip_done()
        if len(slips_original.filtered(lambda x: len(x.move_id) == 0 or x.move_id == False)) == 0:
            self.action_close()

    def restart_payroll_batch(self):
        self.mapped('slip_ids').action_payslip_cancel()
        self.mapped('slip_ids').unlink()
        return self.write({'state': 'draft','observations':False,'time_process':False})

    def restart_payroll_account_batch(self):
        for payslip in self.slip_ids:
            #Eliminar contabilización y el calculo
            payslip.mapped('move_id').unlink()
            #Eliminar historicos
            self.env['hr.vacation'].search([('payslip', '=', payslip.id)]).unlink()
            self.env['hr.history.prima'].search([('payslip', '=', payslip.id)]).unlink()
            self.env['hr.history.cesantias'].search([('payslip', '=', payslip.id)]).unlink()
            #Reversar Liquidación
            payslip.write({'state': 'verify'})
        return self.write({'state': 'verify'})

    def restart_full_payroll_batch(self):
        for payslip in self.slip_ids:
            #Eliminar contabilización
            payslip.mapped('move_id').unlink() 
            #Eliminar historicos            
            self.env['hr.vacation'].search([('payslip', '=', payslip.id)]).unlink()
            self.env['hr.history.prima'].search([('payslip', '=', payslip.id)]).unlink()
            self.env['hr.history.cesantias'].search([('payslip', '=', payslip.id)]).unlink()
            #Reversar Liquidación
            payslip.write({'state':'verify'})
            payslip.action_payslip_cancel()
            payslip.unlink()
        
        # self.mapped('slip_ids').action_payslip_cancel()
        # self.mapped('slip_ids').unlink()
        return self.write({'state': 'draft'})

class HrPayslipEmployees(models.TransientModel):
    _inherit = 'hr.payslip.employees'	

    @api.model
    def _get_default_structure(self):
        return self.env['hr.payroll.structure'].search([('process','=','nomina')],limit=1)


    date_liquidacion = fields.Date('Fecha liquidación de contrato')
    date_prima = fields.Date('Fecha liquidación de prima')
    date_cesantias = fields.Date('Fecha liquidación de cesantías')
    pay_cesantias_in_payroll = fields.Boolean('¿Liquidar Interese de cesantia en nómina?')
    pay_primas_in_payroll = fields.Boolean('¿Liquidar Primas en nómina?')

    structure_id = fields.Many2one('hr.payroll.structure', string='Salary Structure', default=_get_default_structure)
    struct_process = fields.Selection(related='structure_id.process', string='Proceso', store=True)
    method_schedule_pay  = fields.Selection([('days', 'Por Dias/horas'),
                                            ('weekly', 'Semanalmente'),
                                            ('bi-weekly', 'Quincenal'),
                                            ('monthly', 'Mensual'),
                                            ('other', 'Ambos')], 'Frecuencia de Pago', default='other')
    analytic_account_ids = fields.Many2many('account.analytic.account', string='Cuentas analíticas')
    branch_ids = fields.Many2many('lavish.res.branch', string='Sucursales')
    state_contract = fields.Selection([('open','En Proceso'),('finished','Finalizado Por Liquidar')], string='Estado Contrato', default='open')
    settle_payroll_concepts = fields.Boolean('Liquida conceptos de nómina', default=True)
    novelties_payroll_concepts = fields.Boolean('Liquida conceptos de novedades', default=True)
    prima_run_reverse_id = fields.Many2one('hr.payslip.run', string='Lote de prima a ajustar')

    def _get_available_contracts_domain(self):
        domain = [('contract_id.state', '=', self.state_contract or 'open'), ('company_id', '=', self.env.company.id)]
        if self.method_schedule_pay and self.method_schedule_pay != 'other':
            domain.append(('contract_id.method_schedule_pay','=',self.method_schedule_pay))
        if len(self.analytic_account_ids) > 0:
            domain.append(('contract_id.employee_id.analytic_account_id', 'in', self.analytic_account_ids.ids))
        if len(self.branch_ids) > 0:
            domain.append(('branch_id', 'in', self.branch_ids.ids))
        if self.prima_run_reverse_id:
            employee_ids = self.env['hr.payslip'].search([('payslip_run_id', '=', self.prima_run_reverse_id.id)]).employee_id.ids
            domain.append(('id','in',employee_ids))
        return domain

    @api.depends('structure_id','department_id','method_schedule_pay','analytic_account_ids','branch_ids','state_contract','prima_run_reverse_id')
    def _compute_employee_ids(self):
        for wizard in self:
            domain = wizard._get_available_contracts_domain()
            if wizard.department_id:
                domain.append(('department_id', 'child_of', self.department_id.id))
            wizard.employee_ids = self.env['hr.employee'].search(domain)

    def _check_undefined_slots(self, work_entries, payslip_run):
        """
        Check if a time slot in the contract's calendar is not covered by a work entry
        """
        calendar_is_not_covered = self.env['hr.contract']
        work_entries_by_contract = defaultdict(lambda: self.env['hr.work.entry'])
        for work_entry in work_entries:
            work_entries_by_contract[work_entry.contract_id] |= work_entry

        for contract, work_entries in work_entries_by_contract.items():
            calendar_start = pytz.utc.localize(datetime.combine(max(contract.date_start, payslip_run.date_start), datetime.min.time()))
            calendar_end = pytz.utc.localize(datetime.combine(min(contract.date_end or date.max, payslip_run.date_end), datetime.max.time()))
            outside = contract.resource_calendar_id._attendance_intervals_batch(calendar_start, calendar_end)[False] - work_entries._to_intervals()
            if outside:
                calendar_is_not_covered |= contract
                #calendar_is_not_covered.append(contract.id)
                #raise UserError(_("Some part of %s's calendar is not covered by any work entry. Please complete the schedule.") % contract.employee_id.name)

        return calendar_is_not_covered

    def _filter_contracts(self, contracts):
        # Could be overriden to avoid having 2 'end of the year bonus' payslips, etc.
        return contracts


    def compute_sheet(self):
        self.ensure_one()
        if not self.env.context.get('active_id'):
            from_date = fields.Date.to_date(self.env.context.get('default_date_start'))
            end_date = fields.Date.to_date(self.env.context.get('default_date_end'))
            today = fields.date.today()
            first_day = today + relativedelta(day=1)
            last_day = today + relativedelta(day=31)
            if from_date == first_day and end_date == last_day:
                batch_name = from_date.strftime('%B %Y')
            else:
                batch_name = _('From %s to %s', format_date(self.env, from_date), format_date(self.env, end_date))
            payslip_run = self.env['hr.payslip.run'].create({
                'name': batch_name,
                'date_start': from_date,
                'date_end': end_date,
            })
        else:
            payslip_run = self.env['hr.payslip.run'].browse(self.env.context.get('active_id'))

        employees = self.with_context(active_test=False).employee_ids
        if not employees:
            raise UserError(_("You must select employee(s) to generate payslip(s)."))

        #Prevent a payslip_run from having multiple payslips for the same employee
        employees -= payslip_run.slip_ids.employee_id
        success_result = {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.run',
            'views': [[False, 'form']],
            'res_id': payslip_run.id,
        }
        if not employees:
            return success_result

        payslips = self.env['hr.payslip']
        Payslip = self.env['hr.payslip']

        contracts = employees._get_contracts(
            payslip_run.date_start, payslip_run.date_end, states=['open', 'close']
        ).filtered(lambda c: c.active)
        contracts._generate_work_entries(payslip_run.date_start, payslip_run.date_end)
        work_entries = self.env['hr.work.entry'].search([
            ('date_start', '<=', payslip_run.date_end),
            ('date_stop', '>=', payslip_run.date_start),
            ('employee_id', 'in', employees.ids),
        ])
        self._check_undefined_slots(work_entries, payslip_run)

        if(self.structure_id.type_id.default_struct_id == self.structure_id):
            work_entries = work_entries.filtered(lambda work_entry: work_entry.state != 'validated')
            if work_entries._check_if_error():
                work_entries_by_contract = defaultdict(lambda: self.env['hr.work.entry'])

                for work_entry in work_entries.filtered(lambda w: w.state == 'conflict'):
                    work_entries_by_contract[work_entry.contract_id] |= work_entry

                for contract, work_entries in work_entries_by_contract.items():
                    conflicts = work_entries._to_intervals()
                    time_intervals_str = "\n - ".join(['', *["%s -> %s" % (s[0], s[1]) for s in conflicts._items]])
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Some work entries could not be validated.'),
                        'message': _('Time intervals to look for:%s', time_intervals_str),
                        'sticky': False,
                    }
                }


        default_values = Payslip.default_get(Payslip.fields_get())
        payslips_vals = []
        for contract in self._filter_contracts(contracts):
            values = dict(default_values, **{
                'name': _('New Payslip'),
                'employee_id': contract.employee_id.id,
                'credit_note': payslip_run.credit_note,
                'payslip_run_id': payslip_run.id,
                'date_from': payslip_run.date_start,
                'date_liquidacion': self.date_liquidacion,
                'date_prima': self.date_prima,
                'date_cesantias': self.date_cesantias,
                'pay_cesantias_in_payroll': self.pay_cesantias_in_payroll,
                'pay_primas_in_payroll': self.pay_primas_in_payroll,
                'date_to': payslip_run.date_end,
                'contract_id': contract.id,
                'struct_id': self.structure_id.id or contract.structure_type_id.default_struct_id.id,
            })
            payslips_vals.append(values)
        payslips = Payslip.with_context(tracking_disable=True).create(payslips_vals)
        payslips._compute_name()
        payslips._compute_worked_days_line_ids()
        payslips.compute_sheet()
        payslip_run.state = 'verify'

        return success_result

    def clean_employees(self):   
        self.employee_ids = [(5,0,0)]
        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.payslip.employees',
            'res_id': self.id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

class Hr_payslip_line(models.Model):
    _inherit = 'hr.payslip.line'

    entity_id = fields.Many2one('hr.employee.entities', string="Entidad")
    loan_id = fields.Many2one('hr.loans', 'Prestamo', readonly=True)
    days_unpaid_absences = fields.Integer(string='Días de ausencias no pagadas',readonly=True)
    amount_base = fields.Float('Base')
    is_history_reverse = fields.Boolean(string='Es historico para reversar')
    branch_employee_id = fields.Many2one(related='employee_id.branch_id', string='Sucursal', store=True)
    state_slip = fields.Selection(related='slip_id.state', string='Estado Nómina', store=True)
    analytic_account_slip_id = fields.Many2one(related='slip_id.analytic_account_id', string='Cuenta Analitica', store=True)
    struct_slip_id = fields.Many2one(related='slip_id.struct_id', string='Estructura', store=True)
    subtotal =  fields.Float('Subtotal')

    @api.depends('quantity', 'amount', 'rate','subtotal')
    def _compute_total(self):
        #round_payroll = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.round_payroll')) or False
        for line in self:
            if line.subtotal != 0.0:
                line.total = line.subtotal
            else:
                amount_total_original = float(line.quantity) * line.amount * line.rate / 100
                part_decimal, part_value = math.modf(amount_total_original)
                amount_total = float(line.quantity) * line.amount * line.rate / 100 #if round_payroll == False else float(line.quantity) * line.amount * line.rate / 100
                if part_decimal >= 0.5 and math.modf(amount_total)[1] == part_value:
                    line.total = part_value+1
                else:
                    line.total = round(amount_total,0) 
    def count_category_ids(self):
        count_category_ids = self.env['hr.payslip.line'].search_count([('slip_id', '=', self.slip_id.id), ('category_id', '=', self.category_id.id)])
        return count_category_ids

class Hr_payslip_not_line(models.Model):
    _name = 'hr.payslip.not.line'
    _description = 'Reglas no aplicadas' 

    name = fields.Char(string='Nombre',required=True, translate=True)
    note = fields.Text(string='Descripción')
    sequence = fields.Integer(string='Secuencia',required=True, index=True, default=5,
                              help='Use to arrange calculation sequence')
    code = fields.Char(string='Código',required=True)
    slip_id = fields.Many2one('hr.payslip', string='Nómina', required=True, ondelete='cascade')
    salary_rule_id = fields.Many2one('hr.salary.rule', string='Regla', required=True)
    category_id = fields.Many2one(related='salary_rule_id.category_id', string='Categoría',readonly=True, store=True)
    contract_id = fields.Many2one('hr.contract', string='Contrato', required=True, index=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    entity_id = fields.Many2one('hr.employee.entities', string="Entidad")
    loan_id = fields.Many2one('hr.loans', 'Prestamo', readonly=True)   
    rate = fields.Float(string='Porcentaje (%)', digits='Payroll Rate', default=100.0)
    amount = fields.Float(string='Importe',digits='Payroll')
    quantity = fields.Float(string='Cantidad',digits='Payroll', default=1.0)
    total = fields.Float(compute='_compute_total', string='Total', digits='Payroll', store=True) 
    subtotal =  fields.Float('Subtotal')
    @api.depends('quantity', 'amount', 'rate','subtotal')
    def _compute_total(self):
        #round_payroll = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.round_payroll')) or False
        for line in self:
            if line.subtotal != 0.0:
                line.total = line.subtotal
            else:
                amount_total_original = float(line.quantity) * line.amount * line.rate / 100
                part_decimal, part_value = math.modf(amount_total_original)
                amount_total = float(line.quantity) * line.amount * line.rate / 100 #if round_payroll == False else float(line.quantity) * line.amount * line.rate / 100
                if part_decimal >= 0.5 and math.modf(amount_total)[1] == part_value:
                    line.total = part_value+1
                else:
                    line.total = round(amount_total,0) 

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if 'employee_id' not in values or 'contract_id' not in values:
                payslip = self.env['hr.payslip'].browse(values.get('slip_id'))
                values['employee_id'] = values.get('employee_id') or payslip.employee_id.id
                values['contract_id'] = values.get('contract_id') or payslip.contract_id and payslip.contract_id.id
                if not values['contract_id']:
                    raise UserError(_('You must set a contract to create a payslip line.'))
        return super(Hr_payslip_not_line, self).create(vals_list)

class Hr_payslip(models.Model):
    _inherit = 'hr.payslip'

    leave_ids = fields.One2many('hr.absence.days', 'payroll_id', string='Novedades', readonly=True)
    leave_days_ids =fields.One2many('hr.leave.line', 'payslip_id', string='Detalle de Ausencia', readonly=True)
    payslip_day_ids = fields.One2many(comodel_name='hr.payslip.day', inverse_name='payslip_id', string='Días de Nómina', readonly=True)
    rtefte_id = fields.Many2one('hr.employee.rtefte', 'RteFte', readonly=True)
    not_line_ids = fields.One2many('hr.payslip.not.line', 'slip_id', string='Reglas no aplicadas', readonly=True)
    observation = fields.Text(string='Observación')
    analytic_account_id = fields.Many2one(related='contract_id.analytic_account_id',string='Cuenta analítica', store=True)
    struct_process = fields.Selection(related='struct_id.process', string='Proceso', store=True)
    employee_branch_id = fields.Many2one(related='employee_id.branch_id', string='Sucursal empleado', store=True)
    definitive_plan = fields.Boolean(string='Plano definitivo generado')
    #Fechas liquidación de contrato
    date_liquidacion = fields.Date('Fecha liquidación de contrato')
    date_prima = fields.Date('Fecha liquidación de prima')
    date_cesantias = fields.Date('Fecha liquidación de cesantías')
    date_vacaciones = fields.Date('Fecha liquidación de vacaciones')
    worked_days_line_ids = fields.One2many('hr.payslip.worked_days', 'payslip_id', compute=False, )
    pay_cesantias_in_payroll = fields.Boolean('¿Liquidar Interese de cesantia en nómina?')
    pay_primas_in_payroll = fields.Boolean('¿Liquidar Primas en nómina?')
    pay_vacations_in_payroll = fields.Boolean('¿Liquidar vacaciones en nómina?')
    provisiones = fields.Boolean('Provisiones')
    journal_struct_id = fields.Many2one('account.journal', string='Salary Journal', domain="[('company_id', '=', company_id)]")
    earnings_ids = fields.One2many(comodel_name='hr.payslip.line', compute="_compute_concepts_category", string='Conceptos de Nómina / Devengos')
    deductions_ids = fields.One2many(comodel_name='hr.payslip.line', compute="_compute_concepts_category", string='Conceptos de Nómina / Deducciones')
    bases_ids = fields.One2many(comodel_name='hr.payslip.line', compute="_compute_concepts_category", string='Conceptos de Nómina / Bases')
    provisions_ids = fields.One2many(comodel_name='hr.payslip.line', compute="_compute_concepts_category", string='Conceptos de Nómina / Provisiones')
    outcome_ids = fields.One2many(comodel_name='hr.payslip.line', compute="_compute_concepts_category", string='Conceptos de Nómina / Totales')
    
    @api.depends('line_ids')
    def _compute_concepts_category(self):
        category_mapping = {
            'EARNINGS': ['BASIC', 'AUX', 'AUS', 'ALW', 'ACCIDENTE_TRABAJO', 'DEV_NO_SALARIAL', 'DEV_SALARIAL', 'TOTALDEV', 'HEYREC', 'COMISIONES', 'INCAPACIDAD', 'LICENCIA_MATERNIDAD', 'LICENCIA_NO_REMUNERADA', 'LICENCIA_REMUNERADA', 'PRESTACIONES_SOCIALES', 'PRIMA', 'VACACIONES'],
            'DEDUCTIONS': ['DED', 'DEDUCCIONES', 'TOTALDED', 'SANCIONES', 'DESCUENTO_AFC', 'SSOCIAL'],
            'PROVISIONS': ['PROV'],
            'OUTCOME': ['NET']}
        categorized_lines = {
            'EARNINGS': [],
            'DEDUCTIONS': [],
            'PROVISIONS': [],
            'BASES': [],
            'OUTCOME': []}
        for payslip_line in self.line_ids:
            category_found = False
            for category, codes in category_mapping.items():
                if payslip_line.category_id.code in codes or payslip_line.category_id.parent_id.code in codes:
                    categorized_lines[category].append(payslip_line.id)
                    category_found = True
                    break
            if not category_found:
                categorized_lines['BASES'].append(payslip_line.id)
        for category, line_ids in categorized_lines.items():
            setattr(self, f'{category.lower()}_ids', self.env['hr.payslip.line'].browse(line_ids))
    
    def compute_sheet_leave(self):
        for rec in self:
            rec.leave_ids.unlink()
            rec.payslip_day_ids.unlink()
            date_from = datetime.combine(rec.date_from, datetime.min.time())
            date_to = datetime.combine(rec.date_to, datetime.max.time())
            employee_id = rec.employee_id.id
            work_entries = self.env['hr.leave'].search([
                ('state', 'not in', ['cancel', 'refuse']),
                ('date_to', '>=', date_from),
                ('date_from', '<=', date_to),
                ('employee_id', '=', employee_id),
            ])
            leave_vals = [{
                'leave_id': leave.id,
                'leave_type': leave.holiday_status_id.name,
                'employee_id': employee_id,
                'total_days': leave.number_of_days,
                'payroll_id': rec.id,
            } for leave in work_entries]
            if leave_vals:
                leave_records = self.env['hr.absence.days'].create(leave_vals)
                leave_records._days_used()
                relevant_lines = leave_records.mapped('leave_id.line_ids').filtered(lambda l: l.date <= rec.date_to and not l.payslip_id)
                relevant_lines.write({'payslip_id': rec.id})
            self.compute_worked_days()      

    def compute_worked_days(self):
        for rec in self:
            payslip_day_ids = []
            wage_changes_sorted = sorted(rec.contract_id.change_wage_ids, key=lambda x: x.date_start)
            last_wage_change_before_payslip = max((change for change in wage_changes_sorted if change.date_start < rec.date_from), default=None)
            current_wage_day = last_wage_change_before_payslip.wage / 30 if last_wage_change_before_payslip else rec.contract_id.wage / 30
            date_tmp = rec.date_from
            while date_tmp <= rec.date_to:
                is_absence_day = any(leave.date_from.date() <= date_tmp <= leave.date_to.date() for leave in rec.leave_ids.leave_id)
                is_within_contract = rec.contract_id.date_start <= date_tmp <= (rec.contract_id.date_end or date_tmp)
                wage_change_today = next((change for change in wage_changes_sorted if change.date_start == date_tmp), None)
                if wage_change_today:
                    current_wage_day = wage_change_today.wage / 30
                if is_within_contract:
                    day_type = 'A' if is_absence_day else 'W'
                    payslip_day_data = {'payslip_id': rec.id, 'day': date_tmp.day, 'day_type': day_type}
                    if not is_absence_day:
                        payslip_day_data['subtotal'] = current_wage_day
                    payslip_day_ids.append(payslip_day_data)
                else:
                    payslip_day_ids.append({'payslip_id': rec.id, 'day': date_tmp.day, 'day_type': 'X'})
                date_tmp += timedelta(days=1)
            rec.payslip_day_ids.create(payslip_day_ids)
        return True


    def name_get(self):
        result = []
        for record in self:
            if record.payslip_run_id:
                result.append((record.id, "{} - {}".format(record.payslip_run_id.name,record.employee_id.name)))
            else:
                result.append((record.id, "{} - {} - {}".format(record.struct_id.name,record.employee_id.name,str(record.date_from))))
        return result

    def get_hr_payslip_reports_template(self):
        type_report = self.struct_process if self.struct_process != 'otro' else 'nomina'
        obj = self.env['hr.payslip.reports.template'].search([('company_id','=',self.employee_id.company_id.id),('type_report','=',type_report)])
        if len(obj) == 0:
            raise ValidationError(_('No tiene configurada plantilla de liquidacion. Por favor verifique!'))
        return obj

    def get_pay_vacations_in_payroll(self):
        return bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.pay_vacations_in_payroll')) or False

    def get_increase(self):
        return True

    @api.onchange('employee_id', 'struct_id', 'contract_id', 'date_from', 'date_to')
    def _onchange_employee(self):
        if (not self.employee_id) or (not self.date_from) or (not self.date_to):
            return

        employee = self.employee_id
        date_from = self.date_from
        date_to = self.date_to

        self.company_id = employee.company_id
        if not self.contract_id or self.employee_id != self.contract_id.employee_id:  # Add a default contract if not already defined
            contracts = employee._get_contracts(date_from, date_to)

            if not contracts or not contracts[0].structure_type_id.default_struct_id:
                self.contract_id = False
                self.struct_id = False
                return
            self.contract_id = contracts[0]
            self.struct_id = contracts[0].structure_type_id.default_struct_id

        payslip_name = self.struct_id.payslip_name or _('Recibo de Salario')

        mes = self.date_from.month
        month_name = self.env['hr.birthday.list'].get_name_month(mes)
        date_name = month_name + ' ' + str(self.date_from.year)
        self.name = '%s - %s - %s' % (payslip_name, self.employee_id.name or '', date_name)
        self.analytic_account_id = self.contract_id.analytic_account_id
        if date_to > date_utils.end_of(fields.Date.today(), 'month'):
            self.warning_message = _(
                "This payslip can be erroneous! Work entries may not be generated for the period from %s to %s." %
                (date_utils.add(date_utils.end_of(fields.Date.today(), 'month'), days=1), date_to))
        else:
            self.warning_message = False
        self.worked_days_line_ids = self._get_new_worked_days_lines()

    def compute_sheet(self):
        for payslip in self.filtered(lambda slip: slip.state not in ['cancel', 'done','paid']):
            payslip.line_ids.unlink()
            payslip.not_line_ids.unlink()
            payslip.leave_ids.unlink()
            payslip.compute_sheet_leave()
            payslip._compute_extra_hours()
            payslip._compute_novedades()
            payslip._assign_old_payslips()
            payslip.get_increase()
            payslip.input_line_ids = payslip.get_inputs(payslip.date_from, payslip.date_to, payslip.struct_id.process)
            #Seleccionar proceso a ejecutar
            lines = []
            if payslip.struct_id.process == 'nomina':
                lines = [(0, 0, line) for line in payslip._get_payslip_lines()]
            elif payslip.struct_id.process == 'vacaciones':
                lines = [(0, 0, line) for line in payslip._get_payslip_lines()]
            elif payslip.struct_id.process == 'cesantias' or payslip.struct_id.process == 'intereses_cesantias':
                lines = [(0, 0, line) for line in payslip._get_payslip_lines_cesantias()]
            elif payslip.struct_id.process == 'prima':
                lines = [(0, 0, line) for line in payslip._get_payslip_lines_prima()]
            elif payslip.struct_id.process == 'contrato':                
                lines = [(0, 0, line) for line in payslip._get_payslip_lines()]                
            elif payslip.struct_id.process == 'otro':
                lines = [(0, 0, line) for line in payslip._get_payslip_lines_other()]
            else:
                raise ValidationError(_('La estructura seleccionada se encuentra en desarrollo.'))
            if lines:
                payslip.write({'line_ids': lines, 'state': 'verify', 'compute_date': fields.Date.today()})
        return True

    def action_payslip_draft(self):
        for payslip in self:
            for line in payslip.input_line_ids:
                if line.loan_line_id:
                    line.loan_line_id.paid = False
                    line.loan_line_id.payslip_id = False
                    line.loan_line_id.loan_id._compute_loan_amount()
            payslip.leave_ids.leave_id.line_ids.filtered(lambda l: l.date <= payslip.date_to).write({'payslip_id': False})
        return self.write({'state': 'draft'})

    def restart_payroll(self):
        for payslip in self:
            for line in payslip.input_line_ids:
                if line.loan_line_id:
                    line.loan_line_id.paid = False
                    line.loan_line_id.payslip_id = False
                    line.loan_line_id.loan_id._compute_loan_amount()
            #Eliminar contabilización y el calculo
            payslip.leave_ids.leave_id.line_ids.filtered(lambda l: l.date <= payslip.date_to).write({'payslip_id': False})
            payslip.mapped('move_id').unlink()
            # Modificar cuotas de prestamos pagadas
            obj_payslip_line = self.env['hr.payslip.line'].search([('slip_id', '=', payslip.id), ('loan_id', '!=', False)])
            for payslip_line in obj_payslip_line:
                obj_loan_line = self.env['hr.loans.line'].search(
                    [('employee_id', '=', payslip_line.employee_id.id), ('prestamo_id', '=', payslip_line.loan_id.id),
                     ('payslip_id', '>=', payslip.id)])
                obj_loan_line.write({
                    'paid': False,
                    'payslip_id': False
                })
                obj_loan = self.env['hr.loans'].search(
                    [('employee_id', '=', payslip_line.employee_id.id), ('id', '=', payslip_line.loan_id.id)])
                if obj_loan.balance_amount > 0:
                    self.env['hr.contract.concepts'].search([('loan_id', '=', payslip_line.loan_id.id)]).write(
                        {'state': 'done'})
            payslip.line_ids.unlink()
            payslip.not_line_ids.unlink()
            #Eliminar historicos            
            self.env['hr.vacation'].search([('payslip', '=', payslip.id)]).unlink()
            self.env['hr.history.prima'].search([('payslip', '=', payslip.id)]).unlink()
            self.env['hr.history.cesantias'].search([('payslip', '=', payslip.id)]).unlink()
            #Reversar Liquidación            
            payslip.action_payslip_draft()            

    #--------------------------------------------------LIQUIDACIÓN DE LA NÓMINA PERIÓDICA---------------------------------------------------------#
    def _get_worked_day_lines_values(self, domain=None):
        res = super()._get_worked_day_lines_values(domain=domain)
        wm = self.env['hr.work.entry.type'].search([("code", "=", "VACATIONS_MONEY")], limit=1)
        vacations_money = self.env['hr.leave'].search([
            ('employee_id', '=', self.employee_id.id),
            ('holiday_status_id.code', '=', 'VACATIONS_MONEY'),
            ("request_date_from", ">=", self.date_from),
            ("request_date_to", "<=", self.date_to),
            ('state', '=', 'validate')
        ])
        work_entry_type = self.env['hr.work.entry.type'].search([('code','=','WORK100')]).id
        if vacations_money:
            vacations_money_days = sum(vacations_money.mapped('number_of_days'))
            vacations_money_hours = vacations_money_days * self.contract_id.resource_calendar_id.hours_per_day
            res.append({
                'sequence': wm.sequence,
                'work_entry_type_id': wm.id,
                'number_of_days': vacations_money_days,
                'number_of_hours': vacations_money_hours,
            })
        elif self.date_to.month == 2 and self.date_to.day in (28,29):
            days_summary = 2 if self.date_to.day == 28 else 1
            hours_summary = 16 if self.date_to.day == 28 else 8
            for item in res:
                if item['work_entry_type_id'] == work_entry_type:  
                    item['number_of_days'] -= days_summary
                    item['number_of_hours'] -= hours_summary
                else:
                    work_hours = self.contract_id._get_work_hours(self.date_to, self.date_to)
                    work_hours_ordered = sorted(work_hours.items(), key=lambda x: x[1])
                    biggest_work = work_hours_ordered[-1][0] if work_hours_ordered else 0
                    #Primer día de marzo
                    march_date_from = self.date_to + timedelta(days=1)
                    march_date_to = self.date_to + timedelta(days=1)
                    march_work_hours = self.contract_id._get_work_hours(march_date_from, march_date_to)
                    march_work_hours_ordered = sorted(march_work_hours.items(), key=lambda x: x[1])
                    march_biggest_work = march_work_hours_ordered[-1][0] if march_work_hours_ordered else 0
                    #Proceso a realizar
                    #if march_biggest_work == 0 or biggest_work != march_biggest_work: #Si la ausencia no continua hasta marzo se agregan 2 días trabajados para completar los 30 días en febrero
                    # 25/02/2023 | Se realiza que siempre cree 2 días laborados para completar  los 30 dias ignorando si la ausencia continua en marzo
                    # Por ende se comenta la funcionalidad anterior.
                    work_entry_type = self.env['hr.work.entry.type'].search([('code','=','WORK100')])
                    res.append({
                        'sequence': work_entry_type.sequence,
                        'work_entry_type_id': work_entry_type.id,
                        'number_of_days': days_summary,
                        'number_of_hours': hours_summary,
                        'amount': 0,
                    })
        elif calendar.monthrange(self.date_to.year, self.date_to.month)[1] == 31 and self.date_to.day == 31:
            days_to_deduct = 1
            hours_to_deduct = 8
            for item in res:
                if item['work_entry_type_id'] == work_entry_type:  
                    item['number_of_days'] -= days_to_deduct
                    item['number_of_hours'] -= hours_to_deduct
        return res
    def _get_base_local_dict(self):
        return {
            'float_round': float_round,
            'float_compare': float_compare,
            "relativedelta": relativedelta,
            "ceil": math.ceil,
            "floor": math.floor,
            'UserError': UserError,
            'date': date,
            'datetime': datetime,
        }

    def _get_localdict(self):
        self.ensure_one()
        # Check for multiple inputs of the same type and keep a copy of
        # them because otherwise they are lost when building the dict
        input_list = [line.code for line in self.input_line_ids if line.code]
        cnt = Counter(input_list)
        multi_input_lines = [k for k, v in cnt.items() if v > 1]
        same_type_input_lines = {line_code: [line for line in self.input_line_ids if line.code == line_code] for line_code in multi_input_lines}

        localdict = {
            **self._get_base_local_dict(),
            **{
                'categories': defaultdict(lambda: 0),
                'rules': defaultdict(lambda: dict(total=0, amount=0, quantity=0)),
                'payslip': self,
                'worked_days': {line.code: line for line in self.worked_days_line_ids if line.code},
                'inputs': {line.code: line for line in self.input_line_ids if line.code},
                'employee': self.employee_id,
                'contract': self.contract_id,
                'result_rules': defaultdict(lambda: dict(total=0, amount=0, quantity=0, rate=0)),
                'same_type_input_lines': same_type_input_lines,
                'annual_parameters' : self.env['hr.annual.parameters'].search([('year', '=', self.date_from.year)]),
                'rules_computed': BrowsableObject(self.employee_id.id, {}, self.env),
            }
        }
        return localdict


    def _get_payslip_lines(self,inherit_vacation=0,inherit_prima=0,inherit_contrato_dev=0, inherit_contrato_ded_bases=0,inherit_contrato_ded=0,localdict=None):
        line_vals = []
        for payslip in self:

            localdict = self.env.context.get('force_payslip_localdict', None)
            if localdict is None:
                localdict = payslip._get_localdict()
            def _sum_salary_rule(localdict, rule, amount):
                localdict['rules_computed'].dict[rule.code] = localdict['rules_computed'].dict.get(rule.code, 0) + amount
            rules_dict = localdict['rules']
            result_rules_dict = localdict['result_rules']
            date_from = datetime.combine(payslip.date_from, datetime.min.time())
            date_to = datetime.combine(payslip.date_to, datetime.max.time())
            self.env['hr.employee.deduction.retention'].search([('employee_id', '=', localdict['employee'].id),('year', '=', payslip.date_from.year),('month', '=', payslip.date_from.month)]).unlink()
            self.env['hr.employee.rtefte'].search([('employee_id', '=', localdict['employee'].id),('year', '=', payslip.date_from.year),('month', '=', payslip.date_from.month)]).unlink()
            blacklisted_rule_ids = self.env.context.get('prevent_payslip_computation_line_ids', [])
            result = {}
            result_not = {}
            pay_vacations_in_payroll = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.pay_vacations_in_payroll')) or False
            pay_cesantias_in_payroll = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.pay_cesantias_in_payroll')) or False
            pay_primas_in_payroll = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.pay_primas_in_payroll')) or False        
            vacation_days_calculate_absences = int(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.vacation_days_calculate_absences')) or 5
            obj_novelties =  self.novedades_ids #self.env['hr.novelties.different.concepts'].search([('employee_id', '=', employee.id), ('date', '>=', self.date_from),('date', '<=', self.date_to)])
            for concepts in obj_novelties:
                if concepts.amount != 0 and inherit_prima == 0:
                    previous_amount = concepts.salary_rule_id.code in localdict and localdict[concepts.salary_rule_id.code] or 0.0
                    tot_rule = concepts.amount * 1.0 * 100 / 100.0
                    if (inherit_contrato_dev != 0 or inherit_contrato_ded != 0) and self.novelties_payroll_concepts == False and not concepts.salary_rule_id.code in ['TOTALDEV','TOTALDED','NET','IBC_R','IBC_A','IBC_P']:
                        tot_rule = 0
                    if inherit_contrato_dev != 0 and concepts.salary_rule_id.dev_or_ded != 'devengo':                            
                        tot_rule = 0
                    if inherit_contrato_ded != 0 and concepts.salary_rule_id.dev_or_ded != 'deduccion'and not concepts.salary_rule_id.code in ['TOTALDEV','NET',]:                            
                        tot_rule = 0
                    if tot_rule != 0:
                        localdict[concepts.salary_rule_id.code+'-PCD'] = tot_rule
                        rules_dict[concepts.salary_rule_id.code+'-PCD'] = concepts.salary_rule_id
                        localdict = concepts.salary_rule_id.category_id._sum_salary_rule_category(localdict, tot_rule - previous_amount)
                        localdict = _sum_salary_rule(localdict, concepts.salary_rule_id, tot_rule)
                        result_item = concepts.salary_rule_id.code+'-PCD'+str(concepts.id)
                        result[result_item] = {
                            'sequence': concepts.salary_rule_id.sequence,
                            'code': concepts.salary_rule_id.code,
                            'name': concepts.salary_rule_id.name,
                            'note': concepts.salary_rule_id.note,
                            'salary_rule_id': concepts.salary_rule_id.id,
                            'contract_id': payslip.contract_id.id,
                            'employee_id': payslip.employee_id.id,
                            'entity_id': concepts.partner_id.id if concepts.partner_id else False,
                            'amount': tot_rule,
                            'quantity': 1.0,
                            'rate': 100,
                            'slip_id': self.id,}

            def calculate_total_rule(concept, date_from, worked_days_line_ids, employee):
                tot_rule = concept.amount
                if concept.input_id.dev_or_ded == 'deduccion':
                    tot_rule = -tot_rule
                if concept.input_id.modality_value == "fijo":
                    if concept.aplicar == "0":
                        return tot_rule
                    elif concept.aplicar == "15" and date_from.day <= 15:
                        return tot_rule
                    elif concept.aplicar == "30" and date_from.day > 16:
                        return tot_rule
                elif concept.input_id.modality_value == "diario":
                    qty = 1
                    for linea in worked_days_line_ids:
                        if linea.work_entry_type_id.code == 'WORK100':
                            qty = linea.number_of_days
                    if concept.aplicar == "0":
                        return (tot_rule / 30) * qty
                    elif concept.aplicar == "15" and date_from.day <= 15:
                        return (tot_rule / 30) * qty
                    elif concept.aplicar == "30" and date_from.day > 16:
                        start_date = self.date_to.replace(day=1)  # Primer día del mes
                        end_date = start_date + relativedelta(months=1) - relativedelta(days=1)  # Último
                        dias = self.env['hr.payslip.worked_days'].search([
                                ('payslip_id.employee_id.id', '=', employee.id),
                                ('payslip_id.date_to', '>=', start_date),
                                ('payslip_id.date_to', '<=', end_date),
                                ('payslip_id.struct_id.process', '=', 'nomina'),
                                ('work_entry_type_id.code','=','WORK100')])
                        for linea in self.worked_days_line_ids:
                            if dias:
                                qty = sum(d.number_of_days for d in dias)
                                tot_rule = (tot_rule/30) * qty
                        return (tot_rule / 30) * qty

            obj_concept = localdict['contract'].concepts_ids
            for concept in obj_concept.filtered(lambda l: l.state == 'done'):
                entity_id = concept.partner_id.id
                loan_id = concept.loan_id.id 
                date_start_concept = concept.date_start if concept.date_start else datetime.strptime('01/01/1900', '%d/%m/%Y').date()
                date_end_concept = concept.date_end if concept.date_end else datetime.strptime('31/12/2080', '%d/%m/%Y').date()
                previous_amount = concept.input_id.code in localdict and localdict[concept.input_id.code] or 0.0
                if (concept.state == 'done' and 
                    date_start_concept <= date_to.date() and 
                    date_end_concept >= date_from.date() and 
                    concept.amount != 0 and 
                    inherit_prima == 0 and 
                    concept.input_id.amount_select != "code" and self.settle_payroll_concepts ):
                    #localdict.update({'id_contract_concepts': concept.id})
                    tot_rule = calculate_total_rule(concept, self.date_from, self.worked_days_line_ids, localdict['employee'])
                    #LIQUIDACION DE CONTRATO SOLO DEV OR DED DEPENDIENTO SU ORIGEN
                    if (inherit_contrato_dev != 0 or inherit_contrato_ded != 0) and self.novelties_payroll_concepts == False and not concept.input_id.code in ['TOTALDEV','TOTALDED','NET','IBC_R','IBC_A','IBC_P']:
                        tot_rule = 0
                    if inherit_contrato_dev != 0 and concept.input_id.dev_or_ded != 'devengo':                            
                        tot_rule = 0
                    if inherit_contrato_ded != 0 and concept.input_id.dev_or_ded != 'deduccion'and not concept.input_id.code in ['TOTALDEV','NET',]:                            
                        tot_rule = 0
                    if tot_rule != 0:
                        localdict[concept.input_id.code+'-PCD' + str(concept.id)] = tot_rule
                        rules_dict[concept.input_id.code+'-PCD' + str(concept.id)] = concept.input_id
                        # sum the amount for its salary category
                        localdict = concept.input_id.category_id._sum_salary_rule_category(localdict, tot_rule - previous_amount)
                        localdict = _sum_salary_rule(localdict, concept.input_id, tot_rule)
                    result_item = concept.input_id.code + '-PCD' + str(concept.id)
                    result[result_item] = {
                        'sequence': concept.input_id.sequence,
                        'code': concept.input_id.code,
                        'name': concept.input_id.name,
                        'note': concept.input_id.note,
                        'salary_rule_id': concept.input_id.id,
                        'contract_id': payslip.contract_id.id,
                        'employee_id': payslip.employee_id.id,
                        'entity_id': entity_id or False,
                        'loan_id': loan_id,
                        'amount': tot_rule,
                        'quantity': 1.00,
                        'rate': 100,
                        'slip_id': self.id,
                    }
            all_rules = self.env['hr.salary.rule'].browse([])
            obj_struct_payroll = self.env['hr.payroll.structure'].search([('process', '=', 'nomina')])
            if obj_struct_payroll:
                specific_rule_codes = ['DEV_SALARIAL', 'DEV_NO_SALARIAL', 'AUX', 'COMISIONES','AUS']
                specific_rules = self.env['hr.salary.rule'].search([
                    ('category_id.code', 'in', specific_rule_codes),
                ])
                all_rules |= specific_rules
                specific_rules = self.env['hr.salary.rule'].search([
                    ('category_id.parent_id.code', 'in', specific_rule_codes),
                ])
                all_rules |= specific_rules
            for rule in sorted(all_rules, key=lambda x: x.sequence):
                if rule.id in blacklisted_rule_ids:
                    continue
                localdict.update({
                    'result': None,
                    'result_qty': 1.0,
                    'result_rate': 100,
                    'result_name': False
                })
                if rule._satisfy_condition(localdict):
                    # Retrieve the line name in the employee's lang
                    employee_lang = payslip.employee_id.lang
                    amount, qty, rate = rule._compute_rule(localdict)
                    #check if there is already a rule computed with that code
                    previous_amount = localdict.get(rule.code, 0.0)
                    #set/overwrite the amount computed for this rule in the localdict
                    tot_rule = amount * qty * rate / 100.0
                    localdict[rule.code] = tot_rule
                    result_rules_dict[rule.code] = {'total': tot_rule, 'amount': amount, 'quantity': qty, 'rate': rate}
                    rules_dict[rule.code] = rule
                    # sum the amount for its salary category
                    localdict = rule.category_id._sum_salary_rule_category(localdict, tot_rule - previous_amount)
                    rule_name = payslip._get_rule_name(localdict, rule, employee_lang)
                    # create/overwrite the rule in the temporary results
                    result[rule.code] = {
                        'sequence': rule.sequence,
                        'code': rule.code,
                        'name': rule_name,
                        'salary_rule_id': rule.id,
                        'contract_id': payslip.contract_id.id,
                        'employee_id': payslip.employee_id.id,
                        'amount': amount,
                        'quantity': qty,
                        'rate': rate,
                        'slip_id': payslip.id,
                    }
                    _logger.info(localdict.items())
                return localdict,result 
    # def _get_payslip_lines(self,inherit_vacation=0,inherit_prima=0,inherit_contrato_dev=0, inherit_contrato_ded_bases=0,inherit_contrato_ded=0,localdict=None):
    #     def _sum_salary_rule_category(localdict, category, amount):
    #         if category.parent_id:
    #             localdict = _sum_salary_rule_category(localdict, category.parent_id, amount)
    #         localdict['categories'].dict[category.code] = localdict['categories'].dict.get(category.code, 0) + amount
    #         return localdict
    #     def _sum_salary_rule(localdict, rule, amount):
    #         localdict['rules_computed'].dict[rule.code] = localdict['rules_computed'].dict.get(rule.code, 0) + amount
    #         #Sumatoria de valores que son base para los procesos
    #         if rule.category_id.code != 'BASIC':
    #             localdict['values_base_prima'] += amount if rule.base_prima else 0.0
    #             localdict['values_base_cesantias'] += amount if rule.base_cesantias else 0.0
    #             localdict['values_base_int_cesantias'] += amount if rule.base_intereses_cesantias else 0.0
    #             localdict['values_base_vacremuneradas'] += amount if rule.base_vacaciones_dinero else 0.0
    #             localdict['values_base_vacdisfrutadas'] += amount if rule.base_vacaciones else 0.0
    #         return localdict
    #     self.ensure_one()
    #     result = {}
    #     result_not = {}
    #     rules_dict = {}
    #     if inherit_contrato_ded_bases + inherit_contrato_ded + inherit_contrato_dev == 1 and self.date_from == self.date_to:
    #         worked_days_dict = {}
    #     else:
    #         worked_days_dict = {line.code: line for line in self.worked_days_line_ids if line.code}
    #     blacklisted_rule_ids = self.env.context.get('prevent_payslip_computation_line_ids', [])
    #     localdict = self.env.context.get('force_payslip_localdict', None)
    #     leaved_days_dict = {line.leave_id.holiday_status_id.code: line for line in self.leave_ids if line.leave_id.holiday_status_id.code}
    #     worked_days_dict = {line.code: line for line in self.worked_days_line_ids if line.code}
    #     inputs_dict = {line.code: line for line in self.input_line_ids if line.code}
    #     pay_vacations_in_payroll = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.pay_vacations_in_payroll')) or False
    #     pay_cesantias_in_payroll = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.pay_cesantias_in_payroll')) or False
    #     pay_primas_in_payroll = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.pay_primas_in_payroll')) or False        
    #     vacation_days_calculate_absences = int(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.vacation_days_calculate_absences')) or 5
    #     worked_days_entry = 0
    #     leaves_days_law = 0
    #     leaves_days_all = 0
    #     for days in self.worked_days_line_ids:
    #         worked_days_entry = worked_days_entry + (days.number_of_days if days.work_entry_type_id.is_leave == False else 0)
    #         leaves_days_law = leaves_days_law + (days.number_of_days if days.work_entry_type_id.is_leave and days.work_entry_type_id.deduct_deductions == 'law' else 0)
    #         leaves_days_all = leaves_days_all + (days.number_of_days if days.work_entry_type_id.is_leave and days.work_entry_type_id.deduct_deductions == 'all' else 0)
    #     employee = self.employee_id
    #     contract = self.contract_id
    #     year = self.date_from.year
    #     annual_parameters = self.env['hr.annual.parameters'].search([('year', '=', year)])
    #     #Se eliminan registros actuales para el periodo ejecutado de Retención en la fuente
    #     self.env['hr.employee.deduction.retention'].search([('employee_id', '=', employee.id),('year', '=', self.date_from.year),('month', '=', self.date_from.month)]).unlink()
    #     self.env['hr.employee.rtefte'].search([('employee_id', '=', employee.id),('year', '=', self.date_from.year),('month', '=', self.date_from.month)]).unlink()

    #     #Se obtienen las entradas de trabajo
    #     date_from = datetime.combine(self.date_from, datetime.min.time())
    #     date_to = datetime.combine(self.date_to, datetime.max.time())
    #     #Primero, encontró una entrada de trabajo que no excedió el intervalo.
        
    #     if localdict == None:
    #         localdict = {
    #             **self._get_base_local_dict(),
    #             **{
    #                 'categories': BrowsableObject(employee.id, {}, self.env),
    #                 'rules_computed': BrowsableObject(employee.id, {}, self.env),
    #                 'rules': BrowsableObject(employee.id, rules_dict, self.env),
    #                 'payslip': Payslips(employee.id, self, self.env),
    #                 'worked_days': WorkedDays(employee.id, worked_days_dict, self.env),
    #                 'inputs': InputLine(employee.id, inputs_dict, self.env),
    #                 'leaved_days': LeavedDays(employee.id, leaved_days_dict, self.env),   
    #                 'employee': employee,
    #                 'contract': contract,
    #                 'annual_parameters': annual_parameters,
    #                 'values_leaves_all' : 0.0,
    #                 'values_leaves_law' : 0.0,
    #                 'values_base_prima': 0.0,
    #                 'values_base_cesantias': 0.0,
    #                 'values_base_int_cesantias': 0.0,
    #                 'values_base_vacremuneradas': 0.0,
    #                 'values_base_seguridad_social': 0.0,
    #                 'values_base_seguridad_social_no_salarial': 0.0,
    #                 'values_base_provisiones': 0.0,
    #                 'values_base_vacaciones': 0.0,
    #                 'values_base_vacdisfrutadas': 0.0,
    #                 'id_contract_concepts':0.0,
    #                 'inherit_contrato':inherit_contrato_ded+inherit_contrato_dev,
    #                 'inherit_prima':inherit_prima,
    #             }
    #         }
    #     else:
    #         localdict.update({
    #             'worked_days': WorkedDays(employee.id, worked_days_dict, self.env),
    #             'inputs': InputLine(employee.id, inputs_dict, self.env),
    #             'values_leaves_all' : localdict.get('values_leaves_all',0),
    #             'values_leaves_law' : localdict.get('values_leaves_law',0),
    #             #Sumatoria de valores que son base para los procesos
    #             'values_base_prima': localdict.get('values_base_prima',0),
    #             'values_base_cesantias': localdict.get('values_base_cesantias',0),
    #             'values_base_int_cesantias': localdict.get('values_base_int_cesantias',0),
    #             'values_base_compensation': localdict.get('values_base_compensation',0),
    #             'values_base_vacremuneradas': localdict.get('values_base_vacremuneradas',0),
    #             'values_base_vacdisfrutadas': localdict.get('values_base_vacdisfrutadas',0),
    #             'inherit_contrato':inherit_contrato_ded_bases+inherit_contrato_ded+inherit_contrato_dev,
    #             'inherit_prima':inherit_prima,})
    #     #Ejecutar vacaciones dentro de la nómina - 16/02/2022
    #     if (pay_vacations_in_payroll == True and inherit_vacation == 0 and inherit_contrato_ded+inherit_contrato_dev == 0 and inherit_prima == 0):
    #         struct_original = self.struct_id.id
    #         #Vacaciones
    #         obj_struct_vacation = self.env['hr.payroll.structure'].search([('process', '=', 'vacaciones')])
    #         self.struct_id = obj_struct_vacation.id
    #         localdict, result_vac = self._get_payslip_lines_vacation(inherit_contrato=0, localdict=localdict, inherit_nomina=1)
    #         self.struct_id = struct_original
    #     else:
    #         result_vac = {}
    #     if (self.struct_id.process == 'contrato'):
    #         struct_original = self.struct_id.id
    #         #Vacaciones
    #         obj_struct_payroll = self.env['hr.payroll.structure'].search([('process','=','vacaciones')])
    #         self.struct_id = obj_struct_payroll.id
    #         localdict, result_vac_l = self._get_payslip_lines_vacation(inherit_contrato=1,localdict=localdict)
    #         #Continuar con la nómina
    #         self.struct_id = struct_original
    #     else:
    #         result_vac_l = {}
    #     #Cargar novedades por conceptos diferentes
    #     if (contract.modality_salary != 'integral' or contract.contract_type != 'aprendizaje') :
    #         if (pay_cesantias_in_payroll == True and self.pay_cesantias_in_payroll == True) or (self.struct_id.process == 'contrato'):
    #             struct_original = self.struct_id.id
    #             obj_struct_payroll = self.env['hr.payroll.structure'].search([('process', '=', 'intereses_cesantias')])
    #             if (self.struct_id.process == 'contrato'):
    #                 obj_struct_payroll = self.env['hr.payroll.structure'].search([('process','=','cesantias')])
    #             self.struct_id = obj_struct_payroll.id
    #             localdict, result_intcesantias = self.with_context(direct=True)._get_payslip_lines_cesantias(inherit_contrato=1, localdict=localdict)
    #             #Continuar con la nómina
    #             self.struct_id = struct_original
    #         else:
    #             result_intcesantias = {}
    #         if (pay_primas_in_payroll == True and self.pay_primas_in_payroll == True) or (self.struct_id.process == 'contrato'):
    #             struct_original = self.struct_id.id
    #             obj_struct_payroll = self.env['hr.payroll.structure'].search([('process','=','prima')])
    #             self.struct_id = obj_struct_payroll.id
    #             localdict, result_prima = self._get_payslip_lines_prima(inherit_contrato=1,localdict=localdict)
    #             self.struct_id = struct_original
    #         else:
    #             result_prima = {}
    #     obj_novelties =  self.novedades_ids #self.env['hr.novelties.different.concepts'].search([('employee_id', '=', employee.id), ('date', '>=', self.date_from),('date', '<=', self.date_to)])
    #     for concepts in obj_novelties:
    #         if concepts.amount != 0 and inherit_prima == 0:
    #             previous_amount = concepts.salary_rule_id.code in localdict and localdict[concepts.salary_rule_id.code] or 0.0
    #             #set/overwrite the amount computed for this rule in the localdict
    #             tot_rule = concepts.amount * 1.0 * 100 / 100.0
    #             #LIQUIDACION DE CONTRATO SOLO DEV OR DED DEPENDIENTO SU ORIGEN
    #             if (inherit_contrato_dev != 0 or inherit_contrato_ded != 0) and self.novelties_payroll_concepts == False and not concepts.salary_rule_id.code in ['TOTALDEV','TOTALDED','NET','IBC_R','IBC_A','IBC_P']:
    #                 tot_rule = 0
    #             if inherit_contrato_dev != 0 and concepts.salary_rule_id.dev_or_ded != 'devengo':                            
    #                 tot_rule = 0
    #             if inherit_contrato_ded != 0 and concepts.salary_rule_id.dev_or_ded != 'deduccion'and not concepts.salary_rule_id.code in ['TOTALDEV','NET',]:                            
    #                 tot_rule = 0
    #             if tot_rule != 0:
    #                 localdict[concepts.salary_rule_id.code+'-PCD'] = tot_rule
    #                 rules_dict[concepts.salary_rule_id.code+'-PCD'] = concepts.salary_rule_id
    #                 localdict = _sum_salary_rule_category(localdict, concepts.salary_rule_id.category_id, tot_rule - previous_amount)
    #                 localdict = _sum_salary_rule(localdict, concepts.salary_rule_id, tot_rule)
    #                 result_item = concepts.salary_rule_id.code+'-PCD'+str(concepts.id)
    #                 result[result_item] = {
    #                     'sequence': concepts.salary_rule_id.sequence,
    #                     'code': concepts.salary_rule_id.code,
    #                     'name': concepts.salary_rule_id.name,
    #                     'note': concepts.salary_rule_id.note,
    #                     'salary_rule_id': concepts.salary_rule_id.id,
    #                     'contract_id': contract.id,
    #                     'employee_id': employee.id,
    #                     'entity_id': concepts.partner_id.id if concepts.partner_id else False,
    #                     'amount': tot_rule,
    #                     'quantity': 1.0,
    #                     'rate': 100,
    #                     'slip_id': self.id,}

    #     def calculate_total_rule(concept, date_from, worked_days_line_ids, employee):
    #         tot_rule = concept.amount

    #         if concept.input_id.dev_or_ded == 'deduccion':
    #             tot_rule = -tot_rule

    #         if concept.input_id.modality_value == "fijo":
    #             if concept.aplicar == "0":
    #                 return tot_rule
    #             elif concept.aplicar == "15" and date_from.day <= 15:
    #                 return tot_rule
    #             elif concept.aplicar == "30" and date_from.day > 16:
    #                 return tot_rule

    #         elif concept.input_id.modality_value == "diario":
    #             qty = 1  # Default value
    #             for linea in worked_days_line_ids:
    #                 if linea.work_entry_type_id.code == 'WORK100':
    #                     qty = linea.number_of_days

    #             if concept.aplicar == "0":
    #                 return (tot_rule / 30) * qty
    #             elif concept.aplicar == "15" and date_from.day <= 15:
    #                 return (tot_rule / 30) * qty
    #             elif concept.aplicar == "30" and date_from.day > 16:
    #                 start_date = self.date_to.replace(day=1)  # Primer día del mes
    #                 end_date = start_date + relativedelta(months=1) - relativedelta(days=1)  # Último
    #                 dias = self.env['hr.payslip.worked_days'].search([
    #                         ('payslip_id.employee_id.id', '=', employee.id),
    #                         ('payslip_id.date_to', '>=', start_date),
    #                         ('payslip_id.date_to', '<=', end_date),
    #                         ('payslip_id.struct_id.process', '=', 'nomina'),
    #                         ('work_entry_type_id.code','=','WORK100')])
    #                 for linea in self.worked_days_line_ids:
    #                     if dias:
    #                         qty = sum(d.number_of_days for d in dias)
    #                         tot_rule = (tot_rule/30) * qty
    #                 return (tot_rule / 30) * qty

    #     obj_concept = contract.concepts_ids
    #     for concept in obj_concept.filtered(lambda l: l.state == 'done'):
    #         entity_id = concept.partner_id.id
    #         loan_id = concept.loan_id.id 
    #         date_start_concept = concept.date_start if concept.date_start else datetime.strptime('01/01/1900', '%d/%m/%Y').date()
    #         date_end_concept = concept.date_end if concept.date_end else datetime.strptime('31/12/2080', '%d/%m/%Y').date()
    #         previous_amount = concept.input_id.code in localdict and localdict[concept.input_id.code] or 0.0
    #         if (concept.state == 'done' and 
    #             date_start_concept <= date_to.date() and 
    #             date_end_concept >= date_from.date() and 
    #             concept.amount != 0 and 
    #             inherit_prima == 0 and 
    #             concept.input_id.amount_select != "code" and self.settle_payroll_concepts ):
    #             #localdict.update({'id_contract_concepts': concept.id})
    #             tot_rule = calculate_total_rule(concept, self.date_from, self.worked_days_line_ids, employee)
    #             #LIQUIDACION DE CONTRATO SOLO DEV OR DED DEPENDIENTO SU ORIGEN
    #             if (inherit_contrato_dev != 0 or inherit_contrato_ded != 0) and self.novelties_payroll_concepts == False and not concept.input_id.code in ['TOTALDEV','TOTALDED','NET','IBC_R','IBC_A','IBC_P']:
    #                 tot_rule = 0
    #             if inherit_contrato_dev != 0 and concept.input_id.dev_or_ded != 'devengo':                            
    #                 tot_rule = 0
    #             if inherit_contrato_ded != 0 and concept.input_id.dev_or_ded != 'deduccion'and not concept.input_id.code in ['TOTALDEV','NET',]:                            
    #                 tot_rule = 0
    #             if tot_rule != 0:
    #                 localdict[concept.input_id.code+'-PCD' + str(concept.id)] = tot_rule
    #                 rules_dict[concept.input_id.code+'-PCD' + str(concept.id)] = concept.input_id
    #                 # sum the amount for its salary category
    #                 localdict = _sum_salary_rule_category(localdict, concept.input_id.category_id, tot_rule - previous_amount)
    #                 localdict = _sum_salary_rule(localdict, concept.input_id, tot_rule)
    #                 #Guardar valores de ausencias dependiendo parametrización
    #                 if concept.input_id.is_leave:
    #                     amount_leave = tot_rule if concept.input_id.deduct_deductions == 'all' else 0
    #                     localdict['values_leaves_all'] = localdict['values_leaves_all'] + amount_leave
    #                     amount_leave_law = tot_rule if concept.input_id.deduct_deductions == 'law' else 0
    #                     localdict['values_leaves_law'] = localdict['values_leaves_law'] + amount_leave_law
    #             result_item = concept.input_id.code + '-PCD' + str(concept.id)
    #             result[result_item] = {
    #                 'sequence': concept.input_id.sequence,
    #                 'code': concept.input_id.code,
    #                 'name': concept.input_id.name,
    #                 'note': concept.input_id.note,
    #                 'salary_rule_id': concept.input_id.id,
    #                 'contract_id': contract.id,
    #                 'employee_id': employee.id,
    #                 'entity_id': entity_id or False,
    #                 'loan_id': loan_id,
    #                 'amount': tot_rule,
    #                 'quantity': 2.00,
    #                 'rate': 100,
    #                 'slip_id': self.id,
    #             }
    #     #Ejecutar las reglas salariales y su respectiva lógica
    #     all_rules = self.env['hr.salary.rule'].browse([])
    #     if not self.struct_id.process == 'vacaciones':
    #         all_rules = self.struct_id.rule_ids
    #     specific_rules = self.env['hr.salary.rule'].browse([])
    #     obj_struct_payroll = self.env['hr.payroll.structure'].search([('process', '=', 'nomina')])
    #     if obj_struct_payroll:
    #         if (self.settle_payroll_concepts and self.struct_id.process == 'contrato'):
    #             all_rules |= obj_struct_payroll.mapped('rule_ids')
    #         if self.struct_id.process == 'vacaciones':
    #         # Fetching rules with specific codes
    #             specific_rule_codes = ['IBC_R', 'TOTALDEV', 'TOTALDED', 'NET']
    #             specific_rules = self.env['hr.salary.rule'].search([
    #                 '|',('code', 'in', specific_rule_codes),
    #                 ('type_concepts', '=', 'ley'),  
    #                 ('id', 'in', obj_struct_payroll.mapped('rule_ids').ids)  # Asegura que solo consideramos reglas en la estructura que encontramos
    #             ])
    #             all_rules |= specific_rules
    #     #for rule in sorted(self.struct_id.rule_ids, key=lambda x: x.sequence):
    #     for rule in sorted(all_rules, key=lambda x: x.sequence):
    #         if rule.id in blacklisted_rule_ids:
    #             continue
    #         localdict.update({
    #             'result': None,
    #             'result_qty': 1.0,
    #             'result_rate': 100,
    #             'result_name': False
    #         })
    #         if rule._satisfy_condition(localdict):
    #             entity_id,loan_id = 0,0
    #             #Obtener entidades de seguridad social
    #             if rule.category_id.code == 'SSOCIAL':
    #                 for entity in employee.social_security_entities:
    #                     if entity.contrib_id.type_entities == 'eps' and rule.code == 'SSOCIAL001': # SALUD 
    #                         entity_id = entity.partner_id.id
    #                     if entity.contrib_id.type_entities == 'pension' and (rule.code == 'SSOCIAL002' or rule.code == 'SSOCIAL003' or rule.code == 'SSOCIAL004'): # Pension
    #                         entity_id = entity.partner_id.id
    #                     if entity.contrib_id.type_entities == 'subsistencia' and rule.code == 'SSOCIAL003': # Subsistencia 
    #                         entity_id = entity.partner_id.id
    #                     if entity.contrib_id.type_entities == 'solidaridad' and rule.code == 'SSOCIAL004': # Solidaridad 
    #                         entity_id = entity.partner_id.id
    #             #Valida que si la regla esta en la pestaña de Devengo & Deducciones del contrato
    #             amount, qty, rate = rule._compute_rule(localdict)
    #             #Validar si no tiene dias trabajados, si no tiene revisar las ausencias y sus caracteristicas para calcular la deducción
    #             if rule.dev_or_ded == 'deduccion' and rule.type_concepts != 'ley' and (worked_days_entry + leaves_days_all) == 0 and inherit_prima==0:
    #                 amount, qty, rate  = 0,1.0,100 
    #             #LIQUIDACION DE CONTRATO SOLO DEV OR DED DEPENDIENTO SU ORIGEN
    #             if str(rule.amount_python_compute).find('get_overtime') != -1: #Verficiar si la regla utiliza la tabla hr.overtime por ende es un concepto de novedad del menu horas extras
    #                 if (inherit_contrato_dev != 0 or inherit_contrato_ded != 0) and self.novelties_payroll_concepts == False and not rule.code in ['TOTALDEV','TOTALDED','NET','IBC_R','IBC_A','IBC_P']:
    #                     amount, qty, rate = 0,1.0,100
    #             else:
    #                 if (inherit_contrato_dev != 0 or inherit_contrato_ded != 0) and self.settle_payroll_concepts == False and rule.type_concepts != 'ley' and not rule.code in ['TOTALDEV','TOTALDED','NET','IBC_R','IBC_A','IBC_P']:
    #                     amount, qty, rate = 0,1.0,100
    #             # PRIMA SOLAMENTE DEDUCCIONES QUE ESTEN CONFIGURADAS
    #             # VACACIONES SOLAMENTE DEDUCCIONES
    #             if (inherit_contrato_dev != 0 and rule.dev_or_ded != 'devengo')\
    #                     or (inherit_contrato_ded != 0 and rule.dev_or_ded != 'deduccion' and not rule.code in ['TOTALDEV','NET']) \
    #                     or (inherit_prima != 0 and rule.dev_or_ded != 'deduccion' and not rule.code in ['TOTALDEV','NET']) \
    #                     or (inherit_prima != 0 and rule.dev_or_ded == 'deduccion' and rule.deduction_applies_bonus == False) \
    #                     or (inherit_vacation != 0 and rule.dev_or_ded != 'deduccion' and not rule.code in ['TOTALDEV','NET','IBC_R','IBC_A','IBC_P']):
    #                 amount, qty, rate  = 0,1.0,100
    #             #check if there is already a rule computed with that code
    #             previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
    #             #set/overwrite the amount computed for this rule in the localdict
    #             tot_rule = (amount * qty * rate / 100.0) + previous_amount
    #             localdict[rule.code] = tot_rule
    #             rules_dict[rule.code] = rule
    #             # sum the amount for its salary category
    #             localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount) 
    #             localdict = _sum_salary_rule(localdict, rule, tot_rule)
    #             #Guardar valores de ausencias dependiendo parametrización
    #             if rule.is_leave:
    #                 amount_leave = (float(qty) * amount * rate / 100) if rule.deduct_deductions == 'all' else 0
    #                 localdict['values_leaves_all'] = localdict['values_leaves_all'] + amount_leave
    #                 amount_leave_law = (float(qty) * amount * rate / 100) if rule.deduct_deductions == 'law' else 0
    #                 localdict['values_leaves_law'] = localdict['values_leaves_law'] + amount_leave_law
                
    #             # create/overwrite the rule in the temporary results
    #             if amount != 0:
    #                 if rule.dev_or_ded == 'deduccion' and inherit_prima == 0:
    #                     if rule.type_concepts == 'ley':
    #                         value_tmp_neto = localdict['categories'].dict.get('DEV_SALARIAL',0) + localdict['categories'].dict.get('DEV_NO_SALARIAL',0) + localdict['categories'].dict.get('PRESTACIONES_SOCIALES',0) + localdict['categories'].dict.get('DEDUCCIONES',0)
    #                     else:
    #                         value_tmp_neto = (localdict['categories'].dict.get('DEV_SALARIAL',0) + localdict['categories'].dict.get('DEV_NO_SALARIAL',0) + localdict['categories'].dict.get('PRESTACIONES_SOCIALES',0) + localdict['categories'].dict.get('DEDUCCIONES',0)) - localdict['values_leaves_law']
    #                 else:
    #                     value_tmp_neto = 1
    #                 if value_tmp_neto >= 0:
    #                     result[rule.code] = {
    #                         'sequence': rule.sequence,
    #                         'code': rule.code,
    #                         'name': rule.name,
    #                         'note': rule.note,
    #                         'salary_rule_id': rule.id,
    #                         'contract_id': contract.id,
    #                         'employee_id': employee.id,
    #                         'entity_id': entity_id,
    #                         'loan_id': loan_id,
    #                         'amount': amount, #Se redondean los decimales de todas las reglas
    #                         'quantity': qty,
    #                         'rate': rate,
    #                         'subtotal':(amount * qty) * rate / 100,
    #                         'slip_id': self.id,
    #                     }
    #                 else:
    #                     localdict = _sum_salary_rule_category(localdict, rule.category_id, (tot_rule - previous_amount)*-1) 
    #                     localdict = _sum_salary_rule(localdict, rule, (tot_rule)*-1)
    #                     result_not[rule.code] = {
    #                         'sequence': rule.sequence,
    #                         'code': rule.code,
    #                         'name': rule.name,
    #                         'note': rule.note,
    #                         'salary_rule_id': rule.id,
    #                         'contract_id': contract.id,
    #                         'employee_id': employee.id,
    #                         'entity_id': entity_id,
    #                         'loan_id': loan_id,
    #                         'amount': amount, #Se redondean los decimales de todas las reglas
    #                         'quantity': qty,
    #                         'rate': rate,
    #                         'subtotal':(amount * qty) * rate / 100,
    #                         'slip_id': self.id}
    #     #_logger.info(localdict.items())
    #     #Cargar detalle retención en la fuente si tuvo
    #     ranges = {
    #         (1, 4): "Ingreso Base",
    #         (5, 8): "Menos Deducciones",
    #         (9, 13): "Subtotal 1",
    #         (14, 21): "Subtotal 2",
    #         (23, 30): "Subtotal 3",
    #         (31, 37): "Subtotal 4",
    #         (38, 38): "Retención Anterior",
    #         (39, 41): "Total"
    #     }
    #     obj_rtefte = self.env['hr.employee.rtefte'].search([
    #         ('employee_id', '=', employee.id),
    #         ('year', '=', self.date_from.year),
    #         ('month', '=', self.date_from.month)
    #     ])

    #     # Diccionario para rastrear deducciones procesadas
    #     processed_deductions = {}

    #     if obj_rtefte:
    #         html_report = """
    #         <table border="1" style="width: 100%; border-collapse: collapse;">
    #             <thead>
    #                 <tr>
    #                     <th>Concept Deduction Code</th>
    #                     <th>Result Calculation</th>
    #                 </tr>
    #             </thead>
    #             <tbody>
    #         """
    #         current_range = None

    #         for rtefte in obj_rtefte:
    #             for deduction in sorted(rtefte.deduction_retention, key=lambda x: x.concept_deduction_order):
    #                 # Verificar si la deducción ya fue procesada
    #                 if deduction.concept_deduction_code in processed_deductions:
    #                     continue
    #                 processed_deductions[deduction.concept_deduction_code] = True

    #                 # Encuentra el rango actual
    #                 for r, title in ranges.items():
    #                     if r[0] <= deduction.concept_deduction_order <= r[1]:
    #                         if current_range != r:
    #                             html_report += f"""
    #                             <tr>
    #                                 <td colspan="2" style="text-align:center; background-color: #f2f2f2;">{title}</td>
    #                             </tr>
    #                             """
    #                             current_range = r
    #                         break

    #                 # Agrega el registro actual
    #                 html_report += f"""
    #                 <tr>
    #                     <td>{deduction.concept_deduction_code}</td>
    #                     <td>${deduction.result_calculation:,.2f}</td>
    #                 </tr>
    #                 """

    #         html_report += """
    #             </tbody>
    #         </table>
    #         """

    #         self.resulados_rt = html_report
    #         self.rtefte_id = rtefte.id
    #     # Agregar reglas no aplicadas
    #     not_lines = [(0, 0, not_line) for not_line in result_not.values()]
    #     self.not_line_ids = not_lines
    #     #Retornar resultado final de la liquidación de nómina
    #     if inherit_vacation != 0 or inherit_prima != 0:
    #         return result            
    #     elif inherit_contrato_dev != 0 or inherit_contrato_ded != 0:  
    #         return localdict,result
    #     else:
    #         result_finally = {**result, **result_vac, **result_vac_l, **result_intcesantias, **result_prima}
    #         return result_finally.values()



    def _get_payslip_lines_cesantias(self,inherit_contrato=0,localdict=None):
        def _sum_salary_rule_category(localdict, category, amount):
            if category.parent_id:
                localdict = _sum_salary_rule_category(localdict, category.parent_id, amount)
            localdict['categories'].dict[category.code] = localdict['categories'].dict.get(category.code, 0) + amount
            return localdict

        def _sum_salary_rule(localdict, rule, amount):
            localdict['rules_computed'].dict[rule.code] = localdict['rules_computed'].dict.get(rule.code, 0) + amount
            return localdict

        #Validar fecha inicial de causación
        #if inherit_contrato==0:
        date_cesantias = self.contract_id.date_start
        if not self.date_cesantias:  # Si self.date_cesantias es False o None
            self.date_cesantias = date_cesantias
        obj_cesantias = self.env['hr.history.cesantias'].search([('employee_id', '=', self.employee_id.id),('contract_id', '=', self.contract_id.id),('type_history','=','all')])
        if obj_cesantias:
            for history in sorted(obj_cesantias, key=lambda x: x.final_accrual_date):
                date_cesantias = history.final_accrual_date + timedelta(days=1) if history.final_accrual_date > date_cesantias else date_cesantias

        # 1. Verificar que la fecha no sea un rango mayor a un año
        if not self.date_cesantias:  # Si self.date_cesantias es False o None
            self.date_cesantias = date_cesantias
        else:
            self.date_cesantias = min(date_cesantias, self.date_cesantias)

        # Verificar que date_cesantias no sea anterior al 1 de enero del año de self.date_to
        if date_cesantias.year == self.date_to.year - 1 and date_cesantias < date(self.date_to.year, 1, 1):
            self.date_cesantias = date(self.date_to.year, 1, 1)

        if date_cesantias > self.date_to:
            result = {}
            return result.values()
        else:
            if not self.date_cesantias:  # Si self.date_cesantias es False o None
                self.date_cesantias = date_cesantias
            else:
                self.date_cesantias = date_cesantias if self.date_cesantias < date_cesantias else self.date_cesantias

        self.ensure_one()
        result = {}
        rules_dict = {}
        worked_days_dict = {line.code: line for line in self.worked_days_line_ids if line.code}
        inputs_dict = {line.code: line for line in self.input_line_ids if line.code}
        cesantias_salary_take = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.cesantias_salary_take')) or False

        employee = self.employee_id
        contract = self.contract_id
        ctx = self._context or {}
        if contract.modality_salary == 'integral' or contract.contract_type == 'aprendizaje':
            if not ctx.get('direct', False):
                return result.values()

        year = self.date_liquidacion.year or  self.date_from.year
        annual_parameters = self.env['hr.annual.parameters'].search([('year', '=', int(year))])
        
        if localdict == None:
            localdict = {
                **self._get_base_local_dict(),
                **{
                    'categories': BrowsableObject(employee.id, {}, self.env),
                    'rules_computed': BrowsableObject(employee.id, {}, self.env),
                    'rules': BrowsableObject(employee.id, rules_dict, self.env),
                    'payslip': Payslips(employee.id, self, self.env),
                    'worked_days': WorkedDays(employee.id, worked_days_dict, self.env),
                    'inputs': InputLine(employee.id, inputs_dict, self.env),                    
                    'employee': employee,
                    'contract': contract,
                    'annual_parameters': annual_parameters,
                    'inherit_contrato':inherit_contrato,
                    'values_base_cesantias': 0,
                    'values_base_int_cesantias': 0,                    
                }
            }
        else:
            localdict.update({
                'inherit_contrato':inherit_contrato,})

        #Ejecutar las reglas salariales y su respectiva lógica
        for rule in sorted(self.struct_id.rule_ids, key=lambda x: x.sequence):
            localdict.update({                
                'result': None,
                'result_qty': 1.0,
                'result_rate': 100})
            if rule._satisfy_condition(localdict) or rule.code == 'CESANTIAS' or rule.code == 'INTCESANTIAS':                
                amount, qty, rate = rule._compute_rule(localdict)
                dias_ausencias, amount_base = 0, 0
                #Cuando es cesantias o intereses de cesantias, la regla retorna la base y el calculo se realiza a continuación
                amount_base = amount
                if rule.code == 'CESANTIAS' or rule.code == 'INTCESANTIAS':
                    dias_trabajados = self.dias360(self.date_cesantias, self.date_to)
                    dias_ausencias =  sum([i.number_of_days for i in self.env['hr.leave'].search([('date_from','>=',self.date_cesantias),('date_to','<=',self.date_to),('state','=','validate'),('employee_id','=',self.employee_id.id),('unpaid_absences','=',True)])])
                    dias_ausencias += sum([i.days for i in self.env['hr.absence.history'].search([('star_date', '>=', self.date_cesantias), ('end_date', '<=', self.date_to),('employee_id', '=', self.employee_id.id), ('leave_type_id.unpaid_absences', '=', True)])])
                    if inherit_contrato != 0:
                        dias_trabajados = self.dias360(self.date_cesantias, self.date_liquidacion)
                        dias_ausencias =  sum([i.number_of_days for i in self.env['hr.leave'].search([('date_from','>=',self.date_cesantias),('date_to','<=',self.date_liquidacion),('state','=','validate'),('employee_id','=',self.employee_id.id),('unpaid_absences','=',True)])])
                        dias_ausencias += sum([i.days for i in self.env['hr.absence.history'].search([('star_date', '>=', self.date_cesantias), ('end_date', '<=', self.date_liquidacion),('employee_id', '=', self.employee_id.id), ('leave_type_id.unpaid_absences', '=', True)])])
                    dias_liquidacion = dias_trabajados - dias_ausencias

                    #Acumulados
                    if dias_trabajados != 0:
                        acumulados_promedio = (amount / dias_trabajados) * 30  # dias_liquidacion
                    else:
                        acumulados_promedio = 0
                    #Salario - Se toma el salario correspondiente a la fecha de liquidación
                    wage = 0
                    obj_wage = self.env['hr.contract.change.wage'].search([('contract_id','=',contract.id),('date_start','<',self.date_to)])
                    for change in sorted(obj_wage, key=lambda x: x.date_start): #Obtiene el ultimo salario vigente antes de la fecha de liquidacion
                        wage = change.wage
                    wage = contract.wage if wage == 0 else wage
                    initial_process_date = self.date_cesantias if inherit_contrato != 0 else self.date_to - relativedelta(months=3)
                    end_process_date = self.date_liquidacion if inherit_contrato != 0 else self.date_to
                    obj_wage = self.env['hr.contract.change.wage'].search([('contract_id', '=', contract.id), ('date_start', '>=', initial_process_date),('date_start', '<=', end_process_date)])
                    if cesantias_salary_take and len(obj_wage) > 0:
                        wage_average = 0
                        dias_trabajados_average = self.dias360(initial_process_date, end_process_date)
                        while initial_process_date <= end_process_date:
                            if initial_process_date.day != 31:
                                if initial_process_date.month == 2 and initial_process_date.day == 28 and (initial_process_date + timedelta(days=1)).day != 29:
                                    wage_average += (contract.get_wage_in_date(initial_process_date) / 30) * 3
                                elif initial_process_date.month == 2 and initial_process_date.day == 29:
                                    wage_average += (contract.get_wage_in_date(initial_process_date) / 30) * 2
                                else:
                                    wage_average += contract.get_wage_in_date(initial_process_date) / 30
                            initial_process_date = initial_process_date + timedelta(days=1)
                        if dias_trabajados_average != 0:
                            wage = contract.wage if wage_average == 0 else (wage_average / dias_trabajados_average) * 30
                        else:
                            wage = 0
                    #Auxilio de transporte
                    auxtransporte = annual_parameters.transportation_assistance_monthly
                    auxtransporte_tope = annual_parameters.top_max_transportation_assistance
                    #Calculo base
                    if wage <= auxtransporte_tope:
                        amount_base = wage + auxtransporte + acumulados_promedio
                    else:
                        amount_base = wage + acumulados_promedio

                    amount = amount_base / 360
                    qty = dias_liquidacion

                    if rule.code == 'INTCESANTIAS':
                        amount_base =  amount * qty * rate / 100.0
                        amount =  amount_base / 360
                        qty = dias_liquidacion
                        rate = 12

                entity_cesantias = False
                if rule.code == 'CESANTIAS':
                    for entity in self.employee_id.social_security_entities:
                        if entity.contrib_id.type_entities == 'cesantias':
                            entity_cesantias = entity.partner_id

                amount =  amount
                #check if there is already a rule computed with that code
                previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
                #set/overwrite the amount computed for this rule in the localdict
                tot_rule = amount * qty * rate / 100.0
                tot_rule += previous_amount
                localdict[rule.code] = tot_rule
                rules_dict[rule.code] = rule
                # sum the amount for its salary category
                localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount) 
                localdict = _sum_salary_rule(localdict, rule, tot_rule)
                # create/overwrite the rule in the temporary results
                if amount != 0:                    
                    result[rule.code] = {
                        'sequence': rule.sequence,
                        'code': rule.code,
                        'name': rule.name,
                        'note': rule.note,
                        'salary_rule_id': rule.id,
                        'contract_id': contract.id,
                        'employee_id': employee.id,
                        'amount_base': amount_base,
                        'amount': amount,
                        'quantity': qty,
                        'rate': rate,
                        'subtotal':(amount * qty) * rate / 100,
                        'entity_id':entity_cesantias.id if entity_cesantias != False else entity_cesantias,
                        'days_unpaid_absences':dias_ausencias,
                        'slip_id': self.id,
                    }

                # Historico de cesantias/int.cesantias a tener encuenta
                for payments in self.severance_payments_reverse:
                    if rule.code == 'CESANTIAS' and payments.type_history in ('cesantias','all'):
                        previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
                        # set/overwrite the amount computed for this rule in the localdict
                        tot_rule = payments.severance_value + previous_amount
                        localdict[rule.code] = tot_rule
                        rules_dict[rule.code] = rule
                        # sum the amount for its salary category
                        localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount)
                        localdict = _sum_salary_rule(localdict, rule, tot_rule)
                        # create/overwrite the rule in the temporary results
                        if amount != 0:
                            result['His_'+str(payments.id)+'_'+rule.code] = {
                                'sequence': rule.sequence,
                                'code': rule.code,
                                'name': rule.name + ' ' + str(payments.final_accrual_date.year),
                                'note': rule.note,
                                'salary_rule_id': rule.id,
                                'contract_id': contract.id,
                                'employee_id': employee.id,
                                'amount_base': payments.base_value,
                                'amount': payments.severance_value / payments.time,
                                'quantity': payments.time,
                                'rate': rate,
                                'subtotal':(amount * qty) * rate / 100,
                                'entity_id': entity_cesantias.id if entity_cesantias != False else entity_cesantias,
                                'slip_id': self.id,
                                'is_history_reverse': True,
                            }
                    if rule.code == 'INTCESANTIAS' and payments.type_history in ('intcesantias','all'):
                        previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
                        # set/overwrite the amount computed for this rule in the localdict
                        tot_rule = payments.severance_interest_value + previous_amount
                        localdict[rule.code] = tot_rule
                        rules_dict[rule.code] = rule
                        # sum the amount for its salary category
                        localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount)
                        localdict = _sum_salary_rule(localdict, rule, tot_rule)
                        # create/overwrite the rule in the temporary results
                        if amount != 0:
                            result['His_' + str(payments.id) + '_' + rule.code] = {
                                'sequence': rule.sequence,
                                'code': rule.code,
                                'name': rule.name + ' ' + str(payments.final_accrual_date.year),
                                'note': rule.note,
                                'salary_rule_id': rule.id,
                                'contract_id': contract.id,
                                'employee_id': employee.id,
                                'amount_base': payments.base_value if payments.type_history == 'intcesantias' else payments.severance_value,
                                'amount': payments.severance_interest_value / payments.time / 0.12,
                                'quantity': payments.time,
                                'rate': 12,
                                'subtotal':(amount * qty) * 12 / 100,
                                'entity_id': entity_cesantias.id if entity_cesantias != False else entity_cesantias,
                                'slip_id': self.id,
                                'is_history_reverse': True,
                            }

        
        if inherit_contrato == 0:
            return result.values()  
        else:
            return localdict,result  
            #Vacaciones

    def action_payslip_done(self):
        #res = super(Hr_payslip, self).action_payslip_done()
        if any(slip.state == 'cancel' for slip in self):
            raise ValidationError(_("You can't validate a cancelled payslip."))
        self.write({'state' : 'done', 'posted_before': True})
        self.mapped('payslip_run_id').action_close()
        pay_vacations_in_payroll = bool(self.env['ir.config_parameter'].sudo().get_param(
            'lavish_hr_payroll.pay_vacations_in_payroll')) or False
        
         
        #Contabilización
        self._action_create_account_move()
        #Actualizar en la tabla de prestamos la cuota pagada

        for record in self:
            for line in record.input_line_ids:
                if line.loan_line_id:
                    line.loan_line_id.paid = True
                    line.loan_line_id.payslip_id = self.id
                    line.loan_line_id.loan_id._compute_loan_amount()
            obj_payslip_line = self.env['hr.payslip.line'].search([('slip_id', '=', record.id),('loan_id', '!=', False)])
            for payslip_line in obj_payslip_line:
                obj_loan_line = self.env['hr.loans.line'].search([('employee_id', '=', payslip_line.employee_id.id),('prestamo_id', '=', payslip_line.loan_id.id),
                                                                    ('date','>=',record.date_from),('date','<=',record.date_to)])
                data = {
                    'paid':True,
                    'payslip_id': record.id
                }
                obj_loan_line.write(data)
                
                obj_loan = self.env['hr.loans'].search([('employee_id', '=', payslip_line.employee_id.id),('id', '=', payslip_line.loan_id.id)])
                if obj_loan.balance_amount <= 0:
                    self.env['hr.contract.concepts'].search([('loan_id', '=', payslip_line.loan_id.id)]).write({'state':'cancel'})

            if record.struct_id.process == 'vacaciones' or (pay_vacations_in_payroll == True and record.struct_id.process != 'contrato'):
                history_vacation = []
                for line in sorted(record.line_ids.filtered(lambda filter: filter.initial_accrual_date), key=lambda x: x.initial_accrual_date):                
                    if line.code == 'VACDISFRUTADAS':
                        info_vacation = {
                            'employee_id': record.employee_id.id,
                            'contract_id': record.contract_id.id,
                            'initial_accrual_date': line.initial_accrual_date,
                            'final_accrual_date': line.final_accrual_date,
                            'departure_date': record.date_from if not line.vacation_departure_date else line.vacation_departure_date,
                            'return_date': record.date_to if not line.vacation_return_date else line.vacation_return_date,
                            'business_units': line.business_units + line.business_31_units,
                            'value_business_days': line.business_units * line.amount,
                            'holiday_units': line.holiday_units + line.holiday_31_units,
                            'holiday_value': line.holiday_units * line.amount,                            
                            'base_value': line.amount_base,
                            'total': (line.business_units * line.amount)+(line.holiday_units * line.amount),
                            'payslip': record.id,
                            'leave_id': False if not line.vacation_leave_id else line.vacation_leave_id.id
                        }
                    if line.code == 'VACREMUNERADAS':
                        info_vacation = {
                            'employee_id': record.employee_id.id,
                            'contract_id': record.contract_id.id,
                            'initial_accrual_date': line.initial_accrual_date,
                            'final_accrual_date': line.final_accrual_date,
                            'departure_date': record.date_from,
                            'return_date': record.date_to,                            
                            'units_of_money': line.quantity,
                            'money_value': line.total,
                            'base_value_money': line.amount_base,
                            'total': line.total,
                            'payslip': record.id
                        }
                    if line.code == 'VACATIONS_MONEY':
                        info_vacation = {
                            'employee_id': record.employee_id.id,
                            'contract_id': record.contract_id.id,
                            'initial_accrual_date': line.initial_accrual_date,
                            'final_accrual_date': line.final_accrual_date,
                            'departure_date': record.date_from,
                            'return_date': record.date_to,                            
                            'units_of_money': line.quantity,
                            'money_value': line.total,
                            'base_value_money': line.amount_base,
                            'total': line.total,
                            'payslip': record.id
                        }

                    if pay_vacations_in_payroll == True:
                        #Si el historico ya existe no vuelva a crearlo
                        obj_history_vacation_exists = self.env['hr.vacation'].search([('employee_id','=',record.employee_id.id),
                                                                                      ('contract_id','=',record.contract_id.id),
                                                                                      ('initial_accrual_date','=',line.initial_accrual_date),
                                                                                      ('final_accrual_date','=',line.final_accrual_date),
                                                                                      ('leave_id','=',line.vacation_leave_id.id)])
                        if len(obj_history_vacation_exists) == 0:
                            history_vacation.append(info_vacation)
                    else:
                        history_vacation.append(info_vacation)

                if history_vacation: 
                    for history in history_vacation:
                        self.env['hr.vacation'].create(history) 

            if record.struct_id.process == 'cesantias' or record.struct_id.process == 'intereses_cesantias':
                his_cesantias = {}         
                his_intcesantias = {}

                for line in record.line_ids:                
                    #Historico cesantias                
                    if line.code == 'CESANTIAS' and line.is_history_reverse == False:
                        his_cesantias = {
                            'employee_id': record.employee_id.id,
                            'contract_id': record.contract_id.id,
                            'type_history': 'cesantias',
                            'initial_accrual_date': record.date_from,
                            'final_accrual_date': record.date_to,
                            'settlement_date': record.date_to,                        
                            'time': line.quantity,
                            'base_value':line.amount_base,
                            'severance_value': line.total,                        
                            'payslip': record.id
                        }             

                    if line.code == 'INTCESANTIAS' and line.is_history_reverse == False:
                        his_intcesantias = {
                            'employee_id': record.employee_id.id,
                            'contract_id': record.contract_id.id,
                            'type_history': 'intcesantias',
                            'initial_accrual_date': record.date_from,
                            'final_accrual_date': record.date_to,
                            'settlement_date': record.date_to,
                            'time': line.quantity,
                            'base_value': line.amount_base,
                            'severance_interest_value': line.total,
                            'payslip': record.id
                        }

                info_cesantias = {**his_cesantias,**his_intcesantias}        
                if info_cesantias:
                    self.env['hr.history.cesantias'].create(info_cesantias) 

            if record.struct_id.process == 'prima':            
                for line in record.line_ids:                
                    if line.code == 'PRIMA':
                        his_prima = {
                            'employee_id': record.employee_id.id,
                            'contract_id': record.contract_id.id,
                            'initial_accrual_date': record.date_from,
                            'final_accrual_date': record.date_to,
                            'settlement_date': record.date_to,  
                            'time': line.quantity,
                            'base_value':line.amount_base,
                            'bonus_value': line.total,                        
                            'payslip': record.id                      
                        }
                        self.env['hr.history.prima'].create(his_prima) 

            if record.struct_id.process == 'contrato' or record.struct_id.process == 'nomina':  
                his_cesantias = {}         
                his_intcesantias = {}

                for line in record.line_ids:                                
                    #Historico vacaciones
                    if line.code == 'VACCONTRATO':
                        info_vacation = {
                            'employee_id': record.employee_id.id,
                            'contract_id': record.contract_id.id,
                            'initial_accrual_date': line.initial_accrual_date,
                            'final_accrual_date': line.final_accrual_date,
                            'departure_date': record.date_liquidacion,
                            'return_date': record.date_liquidacion,                            
                            'units_of_money': (line.quantity*15)/360,
                            'money_value': line.total,
                            'base_value_money': line.amount_base,
                            'total': line.total,
                            'payslip': record.id
                        }
                        self.env['hr.vacation'].create(info_vacation) 
                    
                    #Historico prima
                    if line.code == 'PRIMA':
                        his_prima = {
                            'employee_id': record.employee_id.id,
                            'contract_id': record.contract_id.id,
                            'initial_accrual_date': record.date_prima,
                            'final_accrual_date': record.date_liquidacion,
                            'settlement_date': record.date_liquidacion,  
                            'time': line.quantity,
                            'base_value':line.amount_base,
                            'bonus_value': line.total,                        
                            'payslip': record.id                      
                        }
                        self.env['hr.history.prima'].create(his_prima) 

                    #Historico cesantias                
                    if line.code == 'CESANTIAS' and line.is_history_reverse == False:
                        his_cesantias = {
                            'employee_id': record.employee_id.id,
                            'contract_id': record.contract_id.id,
                            'initial_accrual_date': record.date_cesantias,
                            'final_accrual_date': record.date_liquidacion,
                            'settlement_date': record.date_liquidacion,                        
                            'time': line.quantity,
                            'base_value':line.amount_base,
                            'severance_value': line.total,                        
                            'payslip': record.id
                        }               

                    if line.code == 'INTCESANTIAS' and line.is_history_reverse == False:
                        his_intcesantias = {
                            'severance_interest_value': line.total,
                        }

                info_cesantias = {**his_cesantias,**his_intcesantias}        
                if info_cesantias:
                    self.env['hr.history.cesantias'].create(info_cesantias) 

                if record.struct_id.process == 'contrato':
                    obj_contrato = self.env['hr.contract'].search([('id','=',record.contract_id.id)])
                    values_update = {'retirement_date':record.date_liquidacion,
                                    'state':'close'}
                    obj_contrato.write(values_update) 

        #return res

            #Validar Historico de cesantias/int.cesantias a tener encuenta
            #Una vez confirmado va a la liquidacion asociado y deja en 0 el valor de CESANTIAS y INT CESANTIAS
            #Para evitar la duplicidad de los valores ya que fueron heredados a esta liquidación
            for payments in self.severance_payments_reverse:
                if payments.payslip:
                    value_cesantias = 0
                    value_intcesantias = 0
                    for line in payments.payslip.line_ids:
                        if line.code == 'CESANTIAS':
                            value_cesantias = line.total
                            line.write({'amount':0})
                        if line.code == 'INTCESANTIAS':
                            value_intcesantias = line.total
                            line.write({'amount':0})
                        if line.code == 'NET':
                            amount = line.total - (value_cesantias+value_intcesantias)
                            line.write({'amount':amount})

                    if payments.payslip.observation:
                        payments.payslip.write({'observation':payments.payslip.observation+ '\n El valor se trasladó a la liquidación '+self.number+' de '+self.struct_id.name })
                    else:
                        payments.payslip.write({'observation': 'El valor se trasladó a la liquidación ' + self.number + ' de ' + self.struct_id.name})




class HrPayslipDay(models.Model):
    _name = 'hr.payslip.day'
    _description = 'Días de Nómina'
    _order = 'day'

    payslip_id = fields.Many2one(comodel_name='hr.payslip', string='Nómina', required=True)
    day_type = fields.Selection(string='Tipo', selection=DAY_TYPE)
    day = fields.Integer(string='Día')
    name = fields.Char(string='Nombre', compute="_compute_name")
    subtotal =  fields.Float('Subtotal')
    @api.depends('day', 'day_type')
    def _compute_name(self):
        for record in self:
            record.name = str(record.day) + record.day_type