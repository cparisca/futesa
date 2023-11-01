# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from .browsable_object import BrowsableObject, InputLine, WorkedDays, Payslips
from odoo.tools import float_compare, float_is_zero

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import math
import logging

_logger = logging.getLogger(__name__)
class hr_history_cesantias(models.Model):
    _name = 'hr.history.cesantias'
    _description = 'Historico de cesantias'
    
    employee_id = fields.Many2one('hr.employee', 'Empleado')
    employee_identification = fields.Char('Identificación empleado')
    type_history = fields.Selection(
        [('cesantias', 'Cesantías'), ('intcesantias', 'Intereses de cesantías'), ('all', 'Ambos')], string='Tipo',
        default='all', required=True)
    initial_accrual_date = fields.Date('Fecha inicial de causación')
    final_accrual_date = fields.Date('Fecha final de causación')
    settlement_date = fields.Date('Fecha de liquidación')
    time = fields.Float('Tiempo')
    severance_value = fields.Float('Valor de cesantías')
    severance_interest_value = fields.Float('Valor intereses de cesantías')
    payslip = fields.Many2one('hr.payslip', 'Liquidación')
    contract_id = fields.Many2one('hr.contract', 'Contrato')
    base_value = fields.Float('Valor base')
    
    def name_get(self):
        result = []
        for record in self:
            type_text = 'Intereses de cesantías' if record.type_history == 'intcesantias' else 'Cesantías'
            result.append((record.id, "{} {} del {} al {}".format(type_text,record.employee_id.name, str(record.initial_accrual_date),str(record.final_accrual_date))))
        return result

    @api.model
    def create(self, vals):
        if vals.get('employee_identification'):
            obj_employee = self.env['hr.employee'].search([('identification_id', '=', vals.get('employee_identification'))])            
            vals['employee_id'] = obj_employee.id
        if vals.get('employee_id'):
            obj_employee = self.env['hr.employee'].search([('id', '=', vals.get('employee_id'))])            
            vals['employee_identification'] = obj_employee.identification_id            
        
        res = super(hr_history_cesantias, self).create(vals)
        return res

class Hr_payslip(models.Model):
    _inherit = 'hr.payslip'

    is_advance_severance = fields.Boolean(string='Es avance de cesantías')
    value_advance_severance = fields.Float(string='Valor a pagar avance')
    employee_severance_pay = fields.Boolean(string='Pago cesantías al empleado')
    severance_payments_reverse = fields.Many2many('hr.history.cesantias',
                                                  string='Historico de cesantias/int.cesantias a tener encuenta',
                                                  domain="[('employee_id', '=', employee_id)]")

    #--------------------------------------------------LIQUIDACIÓN DE CESANTIAS---------------------------------------------------------#

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
        if inherit_contrato==0:
            date_cesantias = self.contract_id.date_start
            obj_cesantias = self.env['hr.history.cesantias'].search([('employee_id', '=', self.employee_id.id),('contract_id', '=', self.contract_id.id),('type_history','=','all')])
            if self.struct_id.process == 'cesantias':
                obj_cesantias += self.env['hr.history.cesantias'].search([('employee_id', '=', self.employee_id.id),('contract_id', '=', self.contract_id.id),('type_history','=','cesantias')])
            if self.struct_id.process == 'intereses_cesantias':
                obj_cesantias += self.env['hr.history.cesantias'].search([('employee_id', '=', self.employee_id.id), ('contract_id', '=', self.contract_id.id),('type_history','=','intcesantias')])

            if obj_cesantias:
                for history in sorted(obj_cesantias, key=lambda x: x.final_accrual_date):
                    date_cesantias = history.final_accrual_date + timedelta(days=1) if history.final_accrual_date > date_cesantias else date_cesantias
            if date_cesantias > self.date_to:
                result = {}
                return result.values()
            else:
                self.date_from = date_cesantias if self.date_from < date_cesantias else self.date_from

        self.ensure_one()
        result = {}
        rules_dict = {}
        worked_days_dict = {line.code: line for line in self.worked_days_line_ids if line.code}
        inputs_dict = {line.code: line for line in self.input_line_ids if line.code}
        round_payroll = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.round_payroll')) or False
        cesantias_salary_take = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.cesantias_salary_take')) or False

        employee = self.employee_id
        contract = self.contract_id

        if contract.modality_salary == 'integral' or contract.contract_type == 'aprendizaje' or contract.subcontract_type == 'obra_integral':
            return result.values()

        year = self.date_from.year
        annual_parameters = self.env['hr.annual.parameters'].search([('year', '=', year)])
        
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
            if rule._satisfy_condition(localdict):                
                amount, qty, rate = rule._compute_rule(localdict)
                dias_ausencias, amount_base = 0, 0
                #Cuando es cesantias o intereses de cesantias, la regla retorna la base y el calculo se realiza a continuación
                amount_base = amount

                if rule.code == 'CESANTIAS' or rule.code == 'INTCESANTIAS':
                    dias_trabajados = self.dias360(self.date_from, self.date_to)
                    dias_ausencias =  sum([i.number_of_days for i in self.env['hr.leave'].search([('date_from','>=',self.date_from),('date_to','<=',self.date_to),('state','=','validate'),('employee_id','=',self.employee_id.id),('unpaid_absences','=',True)])])
                    dias_ausencias += sum([i.days for i in self.env['hr.absence.history'].search([('star_date', '>=', self.date_from), ('end_date', '<=', self.date_to),('employee_id', '=', self.employee_id.id), ('leave_type_id.unpaid_absences', '=', True)])])
                    if inherit_contrato != 0:
                        dias_trabajados = self.dias360(self.date_cesantias, self.date_liquidacion)
                        dias_ausencias =  sum([i.number_of_days for i in self.env['hr.leave'].search([('date_from','>=',self.date_cesantias),('date_to','<=',self.date_liquidacion),('state','=','validate'),('employee_id','=',self.employee_id.id),('unpaid_absences','=',True)])])
                        dias_ausencias += sum([i.days for i in self.env['hr.absence.history'].search([('star_date', '>=', self.date_cesantias), ('end_date', '<=', self.date_liquidacion),('employee_id', '=', self.employee_id.id), ('leave_type_id.unpaid_absences', '=', True)])])
                    dias_liquidacion = dias_trabajados - dias_ausencias

                    #Acumulados
                    if dias_trabajados != 0:
                        acumulados_promedio = (amount / dias_trabajados) * 30  # dias_liquidacion // HISTORIA: Promedio de la base variable no tome ausentismos
                    else:
                        acumulados_promedio = 0
                    #Salario - Se toma el salario correspondiente a la fecha de liquidación
                    wage,auxtransporte,auxtransporte_tope = 0,0,0
                    if contract.subcontract_type not in ('obra_parcial','obra_integral'):
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
                    value_rules_base_auxtransporte_tope = localdict['payslip'].get_accumulated_cesantias(self.date_from, self.date_to, 1)
                    if inherit_contrato != 0:
                        value_rules_base_auxtransporte_tope = localdict['payslip'].get_accumulated_cesantias(self.date_cesantias,self.date_liquidacion,1)
                    if dias_trabajados != 0:
                        value_rules_base_auxtransporte_tope = (value_rules_base_auxtransporte_tope / dias_trabajados) * 30  # dias_liquidacion // HISTORIA: Promedio de la base variable no tome ausentismos
                    else:
                        value_rules_base_auxtransporte_tope = 0
                    if (wage+value_rules_base_auxtransporte_tope) <= auxtransporte_tope:
                        amount_base = round(wage + auxtransporte + acumulados_promedio, 0) if round_payroll == False else wage + auxtransporte + acumulados_promedio
                    else:
                        amount_base = round(wage + acumulados_promedio, 0) if round_payroll == False else wage + acumulados_promedio

                    #amount = round(amount_base * dias_liquidacion / 360, 0)
                    amount = round(amount_base / 360, 0) if round_payroll == False else amount_base / 360
                    qty = dias_liquidacion

                    if rule.code == 'INTCESANTIAS':
                        # Revisar si tuvo avance y calcular los intereses pendientes
                        date_check = (self.date_cesantias or self.date_from) - timedelta(days=1)
                        obj_check_advance = self.env['hr.history.cesantias'].search(
                            [('employee_id', '=', self.employee_id.id), ('contract_id', '=', self.contract_id.id),
                             ('type_history', '=', 'cesantias'), ('settlement_date', '=', date_check),
                             ('payslip.is_advance_severance', '=', True)])
                        if len(obj_check_advance) == 1:
                            amount_base = round(amount * qty * rate / 100.0,0) if round_payroll == False else amount * qty * rate / 100.0
                            amount_base += obj_check_advance.severance_value
                            amount = round(amount_base / 360, 0) if round_payroll == False else amount_base / 360
                            qty = dias_liquidacion+obj_check_advance.time
                        else:
                            amount_base = round(amount * qty * rate / 100.0,0) if round_payroll == False else amount * qty * rate / 100.0
                            amount = round(amount_base / 360, 0) if round_payroll == False else amount_base / 360
                            qty = dias_liquidacion
                        rate = 12

                entity_cesantias = False
                if rule.code == 'CESANTIAS':
                    for entity in self.employee_id.social_security_entities:
                        if entity.contrib_id.type_entities == 'cesantias':
                            entity_cesantias = entity.partner_id

                amount = round(amount,0) if round_payroll == False else round(amount, 2)
                if self.is_advance_severance and self.value_advance_severance > 0:
                    if rule.code == 'CESANTIAS':
                        if self.value_advance_severance > (amount * qty * rate / 100.0):
                            raise ValidationError(f'No se puede hacer el avance ya que el valor es superior a lo permitido ({(amount * qty * rate / 100.0)})')
                        equivalent_days = (self.value_advance_severance * qty) / (amount * qty * rate / 100.0)
                        amount,amount_base,qty = (self.value_advance_severance)/round(equivalent_days,0),0,round(equivalent_days,0)
                        self.date_to = self.date_from + timedelta(days=equivalent_days)
                    if rule.code == 'INTCESANTIAS':
                        amount, amount_base, qty = 0, 0, 0
                #check if there is already a rule computed with that code
                previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
                #set/overwrite the amount computed for this rule in the localdict
                tot_rule_original = (amount * qty * rate / 100.0)
                part_decimal, part_value = math.modf(tot_rule_original)
                tot_rule = amount * qty * rate / 100.0
                if part_decimal >= 0.5 and math.modf(tot_rule)[1] == part_value:
                    tot_rule = (part_value + 1) + previous_amount
                else:
                    tot_rule = tot_rule + previous_amount
                tot_rule = round(tot_rule, 0)
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
                        if amount != 0 or payments.severance_value != 0:
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
                        if amount != 0 or payments.severance_interest_value != 0:
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
                                'entity_id': entity_cesantias.id if entity_cesantias != False else entity_cesantias,
                                'slip_id': self.id,
                                'is_history_reverse': True,
                            }

        
        if inherit_contrato == 0:
            return result.values()  
        else:
            return localdict,result           