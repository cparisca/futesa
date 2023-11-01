# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from .browsable_object import BrowsableObject, InputLine, WorkedDays, Payslips
from odoo.tools import float_compare, float_is_zero
import math

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

import logging

_logger = logging.getLogger(__name__)

class hr_vacation(models.Model):
    _name = 'hr.vacation'
    _description = 'Historico de vacaciones'
    
    employee_id = fields.Many2one('hr.employee', 'Empleado')
    employee_identification = fields.Char('Identificación empleado')
    initial_accrual_date = fields.Date('Fecha inicial de causación')
    final_accrual_date = fields.Date('Fecha final de causación')
    departure_date = fields.Date('Fechas salida')
    return_date = fields.Date('Fecha regreso')
    base_value = fields.Float('Base vacaciones disfrutadas')
    base_value_money = fields.Float('Base vacaciones remuneradas')
    business_units = fields.Integer('Unidades hábiles')
    value_business_days = fields.Float('Valor días hábiles')
    holiday_units = fields.Integer('Unidades festivos')
    holiday_value = fields.Float('Valor días festivos')
    units_of_money = fields.Integer('Unidades dinero')
    money_value = fields.Float('Valor en dinero')
    total = fields.Float('Total')
    payslip = fields.Many2one('hr.payslip', 'Liquidación')
    leave_id = fields.Many2one('hr.leave', 'Ausencia')
    contract_id = fields.Many2one('hr.contract', 'Contrato')

    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "Vacaciones {} del {} al {}".format(record.employee_id.name, str(record.departure_date),str(record.return_date))))
        return result

    @api.model
    def create(self, vals):
        if vals.get('employee_identification'):
            obj_employee = self.env['hr.employee'].search([('identification_id', '=', vals.get('employee_identification'))])            
            vals['employee_id'] = obj_employee.id
        if vals.get('employee_id'):
            obj_employee = self.env['hr.employee'].search([('id', '=', vals.get('employee_id'))])            
            vals['employee_identification'] = obj_employee.identification_id            
        
        res = super(hr_vacation, self).create(vals)
        return res

class hr_payslip_paid_vacation(models.Model):
    _name = 'hr.payslip.paid.vacation'
    _description = 'Liquidación vacaciones remuneradas'

    slip_id = fields.Many2one('hr.payslip',string='Nómina', required=True)
    paid_vacation_days = fields.Integer(string='Cantidad de días', required=True)
    start_date_paid_vacation = fields.Date(string='Fecha inicial', required=True)
    end_date_paid_vacation = fields.Date(string='Fecha final', required=True)

    @api.onchange('paid_vacation_days','start_date_paid_vacation')
    def _onchange_paid_vacation_days(self):
        for record in self:
            if record.paid_vacation_days > 0 and record.start_date_paid_vacation:
                date_to = record.start_date_paid_vacation - timedelta(days=1)
                cant_days = record.paid_vacation_days
                days = 0
                days_31 = 0
                while cant_days > 0:
                    date_add = date_to + timedelta(days=1)
                    cant_days = cant_days - 1
                    days += 1
                    days_31 += 1 if date_add.day == 31 else 0
                    date_to = date_add

                record.end_date_paid_vacation = date_to
                record.paid_vacation_days = days - days_31

class Hr_payslip_line(models.Model):
    _inherit = 'hr.payslip.line'

    initial_accrual_date = fields.Date('C. Inicio')
    final_accrual_date = fields.Date('C. Fin')
    vacation_departure_date = fields.Date('Fechas salida vacaciones')
    vacation_return_date = fields.Date('Fechas regreso vacaciones')
    vacation_leave_id = fields.Many2one('hr.leave', 'Ausencia')
    business_units = fields.Integer('Unidades hábiles')
    business_31_units = fields.Integer('Unidades hábiles - Días 31')
    holiday_units = fields.Integer('Unidades festivos')
    holiday_31_units = fields.Integer('Unidades festivos  - Días 31')

class Hr_payslip(models.Model):
    _inherit = 'hr.payslip'

    paid_vacation_ids = fields.One2many('hr.payslip.paid.vacation', 'slip_id',string='Vacaciones remuneradas')
    refund_date = fields.Date(string='Fecha reintegro')

    #--------------------------------------------------LIQUIDACIÓN DE VACACIONES---------------------------------------------------------#
    def _get_payslip_lines_vacation(self,inherit_contrato=0,localdict=None,inherit_nomina=0):
        def _sum_salary_rule_category(localdict, category, amount):
            if category.parent_id:
                localdict = _sum_salary_rule_category(localdict, category.parent_id, amount)
            localdict['categories'].dict[category.code] = localdict['categories'].dict.get(category.code, 0) + amount
            return localdict

        def _sum_salary_rule(localdict, rule, amount):
            localdict['rules_computed'].dict[rule.code] = localdict['rules_computed'].dict.get(rule.code, 0) + amount
            return localdict

        self.ensure_one()
        result = {}
        result_not = {}
        rules_dict = {}
        worked_days_dict = {line.code: line for line in self.worked_days_line_ids if line.code}
        inputs_dict = {line.code: line for line in self.input_line_ids if line.code}
        pay_vacations_in_payroll = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.pay_vacations_in_payroll')) or False
        round_payroll = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.round_payroll')) or False

        employee = self.employee_id
        contract = self.contract_id
        year = self.date_from.year
        annual_parameters = self.env['hr.annual.parameters'].search([('year', '=', year)])

        #Se obtienen las entradas de trabajo
        date_from = datetime.combine(self.date_from, datetime.min.time())
        date_to = datetime.combine(self.date_to, datetime.max.time())
        #Primero, encontró una entrada de trabajo que no excedió el intervalo.
        work_entries = self.env['hr.work.entry'].search(
            [
                ('state', 'in', ['validated', 'draft']),
                ('date_start', '>=', date_from),
                ('date_stop', '<=', date_to),
                ('contract_id', '=', contract.id),
                ('leave_id','!=',False),
            ]
        )
        #En segundo lugar, encontró entradas de trabajo que exceden el intervalo y calculan la duración correcta. 
        work_entries |= self.env['hr.work.entry'].search(
            [
                '&', '&',
                ('state', 'in', ['validated', 'draft']),
                ('contract_id', '=', contract.id),
                '|', '|', '&', '&',
                ('date_start', '>=', date_from),
                ('date_start', '<', date_to),
                ('date_stop', '>', date_to),
                '&', '&',
                ('date_start', '<', date_from),
                ('date_stop', '<=', date_to),
                ('date_stop', '>', date_from),
                '&',
                ('date_start', '<', date_from),
                ('date_stop', '>', date_to),
            ]
        )
        
        initial_accrual_date = False
        final_accrual_date = False
        leave_holidays = 0
        leave_business_days = 0
        leave_number_of_days = 0
        leaves_time = []
        leaves_money = []
        leaves = {}
        leave_time_ids = []
        for leave in work_entries.sorted(key=lambda w:w.date_start):
            if leave.leave_id.holiday_status_id.is_vacation:
                leave_holidays = leave.leave_id.holidays
                leave_business_days = leave.leave_id.business_days
                leave_number_of_days = leave.leave_id.number_of_days
                code = leave.work_entry_type_id.code
                leaves.setdefault(leave.leave_id,{})
                leaves[leave.leave_id].update({
                        'IDLEAVE' : leave.leave_id.id,
                        code : leave_number_of_days,
                        'HOLIDAYS%s'%code : leave_holidays,
                        'BUSINESS%s'%code : leave_business_days,
                    })
                #Días pertenecientes a la liquidación de nómina
                if inherit_nomina != 0:
                    # Obtener si el dia sabado es habil | Guardar dias fines de semana 5=Sabado & 6=Domingo
                    lst_days = [5, 6] if employee.sabado == False else [6]
                    #Obtener fechas
                    initial_date = leave.leave_id.request_date_from if leave.leave_id.request_date_from >= self.date_from else self.date_from
                    end_date = leave.leave_id.request_date_to if leave.leave_id.request_date_to <= self.date_to else self.date_to
                    #Dias
                    vac_days_in_payslip = 0
                    holidays = 0
                    business_days = 0
                    days_31_b = 0
                    days_31_h = 0
                    while initial_date <= end_date:
                        vac_days_in_payslip += 1
                        if not initial_date.weekday() in lst_days:
                            # Obtener dias festivos parametrizados
                            obj_holidays = self.env['lavish.holidays'].search([('date', '=', initial_date)])
                            if obj_holidays:
                                holidays += 1
                                days_31_h += 1 if initial_date.day == 31 else 0
                            else:
                                business_days += 1
                                days_31_b += 1 if initial_date.day == 31 else 0
                        else:
                            holidays += 1
                            days_31_h += 1 if initial_date.day == 31 else 0
                        initial_date = initial_date + timedelta(days=1)
                    leaves[leave.leave_id].update({
                        'IDLEAVE' : leave.leave_id.id,
                        'ORIGINAL_%s'%code : leave_number_of_days,
                        'ORIGINAL_HOLIDAYS%s'%code : leave_holidays,
                        'ORIGINAL_BUSINESS%s'%code : leave_business_days,
                        code : vac_days_in_payslip,
                        'HOLIDAYS%s'%code : holidays,
                        'BUSINESS%s'%code : business_days,
                        '31HOLIDAYS%s'%code : days_31_h,
                        '31BUSINESS%s'%code : days_31_b,
                    })

        leaves_time = list(leaves.values())

        #Vacaciones Remuneradas
        if len(self.paid_vacation_ids) > 0:
            for paid in self.paid_vacation_ids.sorted(key=lambda w:w.start_date_paid_vacation):
                leaves = {}

                leave_number_of_days = paid.paid_vacation_days
                leaves['IDPAID'] = paid.id
                leaves['VACREMUNERADAS'] = leave_number_of_days
                leaves['DATE'] = paid.start_date_paid_vacation

                leaves_money.append(leaves)
        
        '''
        Validar que no queden las deducciones en la nómina si ya estan en vacaciones
        '''

        #Calcular antiguedad del empleado
        antiquity_employee = relativedelta(fields.Date.today() , contract.date_start).years

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
                    'leaves':  BrowsableObject(employee.id, leaves, self.env),
                    'employee': employee,
                    'contract': contract,
                    'annual_parameters': annual_parameters,
                    'antiquity_employee': antiquity_employee,
                    'inherit_contrato':inherit_contrato,
                    'values_base_vacremuneradas': 0,
                    'values_base_vacdisfrutadas': 0,
                }
            }
        else:
            localdict.update({
                'antiquity_employee': antiquity_employee,
                'inherit_contrato':inherit_contrato,})        
        #Ejecutar las reglas salariales y su respectiva lógica
        for rule in sorted(self.struct_id.rule_ids, key=lambda x: x.sequence):
            localdict.update({
                'result': None,
                'result_qty': 1.0,
                'result_rate': 100})
            if rule._satisfy_condition(localdict):
                if rule.code == 'VACDISFRUTADAS' and (self.get_pay_vacations_in_payroll() == False or inherit_nomina!=0):
                    initial_accrual_date = False
                    final_accrual_date = False                    
                    for leaves in leaves_time:
                        if inherit_nomina != 0:
                            id_leave = leaves.get('IDLEAVE')
                            obj_leave = self.env['hr.leave'].search([('id', '=', id_leave)])
                            days_vacations = leaves.get('VACDISFRUTADAS',0)
                            days_vacations_business = leaves.get('BUSINESSVACDISFRUTADAS',0)
                            days_vacations_31_business = leaves.get('31BUSINESSVACDISFRUTADAS',0)
                            days_vacations_holidays = leaves.get('HOLIDAYSVACDISFRUTADAS',0)
                            days_vacations_31_holidays = leaves.get('31HOLIDAYSVACDISFRUTADAS',0)
                        else:
                            id_leave = leaves.get('IDLEAVE')
                            obj_leave = self.env['hr.leave'].search([('id', '=', id_leave)])
                            obj_leave_equals = self.env['hr.leave'].search([('state','=','validate'),('employee_id','=',employee.id),('id','!=',id_leave),('is_vacation','=',True),('request_date_from', '>=', obj_leave.request_date_from),('request_date_to', '<=', obj_leave.request_date_to)])
                            days_vacations = obj_leave.number_of_days if obj_leave.business_days + obj_leave.days_31_business == 0 else obj_leave.business_days + obj_leave.days_31_business
                            days_vacations_business = obj_leave.business_days
                            days_vacations_31_business = obj_leave.days_31_business
                            days_vacations_holidays = obj_leave.holidays
                            days_vacations_31_holidays = obj_leave.days_31_holidays
                            for leave_equals in obj_leave_equals:
                                days_vacations += leave_equals.number_of_days if leave_equals.business_days + leave_equals.days_31_business == 0 else leave_equals.business_days + leave_equals.days_31_business
                                days_vacations_business += leave_equals.business_days
                                days_vacations_31_business += leave_equals.days_31_business
                                days_vacations_holidays += leave_equals.holidays
                                days_vacations_31_holidays += leave_equals.days_31_holidays
                            #Remuneradas
                            for paid_vacation in self.paid_vacation_ids:
                                if obj_leave.request_date_from:
                                    if paid_vacation.start_date_paid_vacation >= obj_leave.request_date_from and paid_vacation.end_date_paid_vacation <= obj_leave.request_date_to:
                                        days_vacations += paid_vacation.paid_vacation_days

                        localdict.update({'leaves':  BrowsableObject(employee.id, leaves, self.env)})
                        amount, qty, rate = rule._compute_rule(localdict)
                        #check if there is already a rule computed with that code
                        previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
                        #set/overwrite the amount computed for this rule in the localdict
                        tot_rule = (amount * qty * rate / 100.0) + previous_amount
                        localdict[rule.code] = tot_rule
                        rules_dict[rule.code] = rule
                        # sum the amount for its salary category
                        localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount) 
                        localdict = _sum_salary_rule(localdict, rule, tot_rule)
                        #Calculo fechas de causacion                        
                        if initial_accrual_date and final_accrual_date:
                            initial_accrual_date = final_accrual_date + timedelta(days=1)
                            days = ((days_vacations_business+days_vacations_31_business) * 365) / 15
                            final_accrual_date = initial_accrual_date + timedelta(days=days-1)
                        else:
                            obj_vacation = self.env['hr.vacation'].search([('employee_id', '=', employee.id)])     
                            if obj_vacation:
                                query = 'Select Max(final_accrual_date) as final_accrual_date From hr_vacation Where employee_id = '+ str(employee.id)

                                self.env.cr.execute(query)
                                result_query = self.env.cr.fetchone()
                                accrual_date = result_query[0] + timedelta(days=1)
                                accrual_date = accrual_date if accrual_date >= contract.date_start else contract.date_start
                            else:
                                accrual_date = contract.date_start

                            #fecha inicial causación
                            initial_accrual_date = accrual_date
                            #fecha final causación
                            days = ((days_vacations_business+days_vacations_31_business) * 365) / 15
                            final_accrual_date = initial_accrual_date + timedelta(days=days-1)   
                            #dias360 = self.dias360(initial_accrual_date,final_accrual_date)

                        # create/overwrite the rule in the temporary results
                        if amount != 0 and initial_accrual_date:                    
                            result[str(id_leave)+'_'+rule.code] = {
                                'sequence': rule.sequence,
                                'code': rule.code,
                                'name': rule.name,
                                'note': rule.note,
                                'initial_accrual_date': initial_accrual_date,
                                'final_accrual_date': final_accrual_date,
                                'amount_base': amount*30,
                                'business_units': days_vacations_business,
                                'business_31_units': days_vacations_31_business,
                                'holiday_units': days_vacations_holidays,
                                'holiday_31_units': days_vacations_31_holidays,
                                'salary_rule_id': rule.id,
                                'contract_id': contract.id,
                                'employee_id': employee.id,                        
                                'amount': amount,
                                'quantity': qty,
                                'rate': rate,
                                'slip_id': self.id,
                                #Info vacaciones
                                'vacation_departure_date': obj_leave.request_date_from,
                                'vacation_return_date': obj_leave.request_date_to,
                                'vacation_leave_id': obj_leave.id,
                            }
                if rule.code == 'VACREMUNERADAS':
                    initial_accrual_date = False
                    final_accrual_date = False                    
                    for leaves in leaves_money:
                        id_leave = leaves.get('IDPAID')
                        obj_leave_equals = self.env['hr.leave'].search([('state','=','validate'),('employee_id','=',employee.id),('is_vacation','=',True),('request_date_from', '=', leaves.get('DATE'))])  #('request_date_to', '<=', obj_leave.request_date_to)
                        days_vacations = leaves.get('VACREMUNERADAS')
                        if pay_vacations_in_payroll == False:
                            for leave_equals in obj_leave_equals:
                                days_vacations += leave_equals.number_of_days if leave_equals.business_days + leave_equals.days_31_business == 0 else leave_equals.business_days + leave_equals.days_31_business

                        localdict.update({'leaves':  BrowsableObject(employee.id, leaves, self.env)})
                        amount, qty, rate = rule._compute_rule(localdict)
                        #check if there is already a rule computed with that code
                        previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
                        #set/overwrite the amount computed for this rule in the localdict
                        tot_rule = (amount * qty * rate / 100.0) + previous_amount
                        localdict[rule.code] = tot_rule
                        rules_dict[rule.code] = rule
                        # sum the amount for its salary category
                        localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount) 
                        localdict = _sum_salary_rule(localdict, rule, tot_rule)
                        #Calculo fechas de causacion                        
                        if initial_accrual_date and final_accrual_date:
                            initial_accrual_date = final_accrual_date + timedelta(days=1)
                            days = (days_vacations * 365) / 15
                            final_accrual_date = initial_accrual_date + timedelta(days=days-1)
                        else:
                            obj_vacation = self.env['hr.vacation'].search([('employee_id', '=', employee.id)])     
                            if obj_vacation:
                                query = 'Select Max(final_accrual_date) as final_accrual_date From hr_vacation Where employee_id = '+ str(employee.id)

                                self.env.cr.execute(query)
                                result_query = self.env.cr.fetchone()
                                accrual_date = result_query[0] + timedelta(days=1)
                                accrual_date = accrual_date if accrual_date >= contract.date_start else contract.date_start
                            else:
                                accrual_date = contract.date_start

                            #fecha inicial causación
                            initial_accrual_date = accrual_date
                            #fecha final causación
                            days = (days_vacations * 365) / 15                            
                            #for obj_leave in leaves_all_obj:
                            final_accrual_date = initial_accrual_date + timedelta(days=days-1)   
                            #dias360 = self.dias360(initial_accrual_date,final_accrual_date)

                        # create/overwrite the rule in the temporary results
                        if amount != 0:                    
                            result[str(id_leave)+'_'+rule.code] = {
                                'sequence': rule.sequence,
                                'code': rule.code,
                                'name': rule.name,
                                'note': rule.note,
                                'initial_accrual_date': initial_accrual_date,
                                'final_accrual_date': final_accrual_date,
                                'amount_base': amount*30,
                                'salary_rule_id': rule.id,
                                'contract_id': contract.id,
                                'employee_id': employee.id,                        
                                'amount': amount,
                                'quantity': qty,
                                'rate': rate,
                                'slip_id': self.id,
                            }
                else:
                    amount, qty, rate = rule._compute_rule(localdict)
                    dias_ausencias,amount_base = 0,0
                    initial_accrual_date = False
                    final_accrual_date = False

                    if rule.code == 'VACCONTRATO' and inherit_contrato != 0 :    
                        amount_base = amount
                        initial_accrual_date = self.date_vacaciones
                        final_accrual_date = self.date_liquidacion
                        acumulados_promedio = 0
                        dias_trabajados = self.dias360(self.date_vacaciones, self.date_liquidacion)
                        dias_ausencias =  sum([i.number_of_days for i in self.env['hr.leave'].search([('date_from','>=',self.date_vacaciones),('date_to','<=',self.date_liquidacion),('state','=','validate'),('employee_id','=',self.employee_id.id),('unpaid_absences','=',True)])])
                        dias_ausencias += sum([i.days for i in self.env['hr.absence.history'].search([('star_date', '>=', self.date_vacaciones), ('end_date', '<=', self.date_liquidacion),('employee_id', '=', self.employee_id.id), ('leave_type_id.unpaid_absences', '=', True)])])
                        dias_liquidacion = dias_trabajados - dias_ausencias

                        if (self.date_liquidacion - contract.date_start).days <= 365:
                            if dias_liquidacion > 0:
                                acumulados_promedio = (amount_base/dias_liquidacion)*30
                            else:
                                acumulados_promedio = 0
                        else:
                            acumulados_promedio = amount_base/12

                        amount_base = contract.wage + acumulados_promedio

                        amount = amount_base / 720
                        qty = dias_liquidacion
                # VACACIONES SOLAMENTE DEDUCCIONES
                    if (rule.code in ['VACREMUNERADAS','VACDISFRUTADAS']):
                        amount, qty, rate  = 0,1.0,100
                    #check if there is already a rule computed with that code
                    previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
                    #set/overwrite the amount computed for this rule in the localdict
                    tot_rule = (amount * qty * rate / 100.0) + previous_amount
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
                            'initial_accrual_date': initial_accrual_date,
                            'final_accrual_date': final_accrual_date,
                            'amount_base': amount_base,                       
                            'amount': amount,
                            'quantity': qty,
                            'rate': rate,
                            'days_unpaid_absences':dias_ausencias,
                            'slip_id': self.id,
                        }
        
        #Ejecutar reglas salariales de la nómina de pago regular
        _logger.info(result)
        # if inherit_contrato == 0 and inherit_nomina == 0:
        #     obj_struct_payroll = self.env['hr.payroll.structure'].search([('regular_pay','=',True),('process','=','nomina')])
        #     struct_original = self.struct_id.id
        #     self.struct_id = obj_struct_payroll.id
        #     result_payroll = self._get_payslip_lines(inherit_vacation=1,localdict=localdict)
        #     self.struct_id = struct_original
        
        #     result_finally = {**result,**result_payroll}        
        #     #Retornar resultado final de la liquidación de nómina
        #     return result_finally.values()  
        # else:
        return localdict,result   
         
    # def _get_payslip_lines_vacation(self,inherit_contrato=0,localdict=None,inherit_nomina=0):
    #     def _sum_salary_rule_category(localdict, category, amount):
    #         if category.parent_id:
    #             localdict = _sum_salary_rule_category(localdict, category.parent_id, amount)
    #         localdict['categories'].dict[category.code] = localdict['categories'].dict.get(category.code, 0) + amount
    #         return localdict

    #     def _sum_salary_rule(localdict, rule, amount):
    #         localdict['rules_computed'].dict[rule.code] = localdict['rules_computed'].dict.get(rule.code, 0) + amount
    #         return localdict

    #     self.ensure_one()
    #     result = {}
    #     result_not = {}
    #     rules_dict = {}
    #     worked_days_dict = {line.code: line for line in self.worked_days_line_ids if line.code}
    #     inputs_dict = {line.code: line for line in self.input_line_ids if line.code}
    #     pay_vacations_in_payroll = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.pay_vacations_in_payroll')) or False
    #     round_payroll = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.round_payroll')) or False

    #     employee = self.employee_id
    #     contract = self.contract_id
    #     year = self.date_from.year
    #     annual_parameters = self.env['hr.annual.parameters'].search([('year', '=', year)])

    #     #Se obtienen las entradas de trabajo
    #     date_from = datetime.combine(self.date_from, datetime.min.time())
    #     date_to = datetime.combine(self.date_to, datetime.max.time())
    #     #Primero, encontró una entrada de trabajo que no excedió el intervalo.
    #     work_entries = self.env['hr.work.entry'].search(
    #         [
    #             ('state', 'in', ['validated', 'draft']),
    #             ('date_start', '>=', date_from),
    #             ('date_stop', '<=', date_to),
    #             ('contract_id', '=', contract.id),
    #             ('leave_id','!=',False),
    #         ]
    #     )
    #     #En segundo lugar, encontró entradas de trabajo que exceden el intervalo y calculan la duración correcta. 
    #     work_entries |= self.env['hr.work.entry'].search(
    #         [
    #             '&', '&',
    #             ('state', 'in', ['validated', 'draft']),
    #             ('contract_id', '=', contract.id),
    #             '|', '|', '&', '&',
    #             ('date_start', '>=', date_from),
    #             ('date_start', '<', date_to),
    #             ('date_stop', '>', date_to),
    #             '&', '&',
    #             ('date_start', '<', date_from),
    #             ('date_stop', '<=', date_to),
    #             ('date_stop', '>', date_from),
    #             '&',
    #             ('date_start', '<', date_from),
    #             ('date_stop', '>', date_to),
    #         ]
    #     )
        
    #     initial_accrual_date = False
    #     final_accrual_date = False
    #     leave_holidays = 0
    #     leave_business_days = 0
    #     leave_number_of_days = 0
    #     # leaves_time = []
    #     leaves_money = []
    #     leaves = {}
    #     for leave in work_entries.sorted(key=lambda w:w.date_start):
    #         if leave.leave_id.holiday_status_id.is_vacation:
    #             leave_holidays = leave.leave_id.holidays
    #             leave_business_days = leave.leave_id.business_days
    #             leave_number_of_days = leave.leave_id.number_of_days
    #             code = leave.work_entry_type_id.code
    #             leaves.setdefault(leave.leave_id,{})
    #             leaves[leave.leave_id].update({
    #                     'IDLEAVE' : leave.leave_id.id,
    #                     code : leave_number_of_days,
    #                     'HOLIDAYS%s'%code : leave_holidays,
    #                     'BUSINESS%s'%code : leave_business_days,
    #                 })
    #             #Días pertenecientes a la liquidación de nómina
    #             if inherit_nomina != 0:
    #                 # Obtener si el dia sabado es habil | Guardar dias fines de semana 5=Sabado & 6=Domingo
    #                 lst_days = [5, 6] if employee.sabado == False else [6]
    #                 #Obtener fechas
    #                 initial_date = leave.leave_id.request_date_from if leave.leave_id.request_date_from >= self.date_from else self.date_from
    #                 end_date = leave.leave_id.request_date_to if leave.leave_id.request_date_to <= self.date_to else self.date_to
    #                 #Dias
    #                 vac_days_in_payslip = 0
    #                 holidays = 0
    #                 business_days = 0
    #                 days_31_b = 0
    #                 days_31_h = 0
    #                 while initial_date <= end_date:
    #                     vac_days_in_payslip += 1
    #                     if not initial_date.weekday() in lst_days:
    #                         # Obtener dias festivos parametrizados
    #                         obj_holidays = self.env['lavish.holidays'].search([('date', '=', initial_date)])
    #                         if obj_holidays:
    #                             holidays += 1
    #                             days_31_h += 1 if initial_date.day == 31 else 0
    #                         else:
    #                             business_days += 1
    #                             days_31_b += 1 if initial_date.day == 31 else 0
    #                     else:
    #                         holidays += 1
    #                         days_31_h += 1 if initial_date.day == 31 else 0
    #                     initial_date = initial_date + timedelta(days=1)
    #                 leaves[leave.leave_id].update({
    #                     'IDLEAVE' : leave.leave_id.id,
    #                     'ORIGINAL_%s'%code : leave_number_of_days,
    #                     'ORIGINAL_HOLIDAYS%s'%code : leave_holidays,
    #                     'ORIGINAL_BUSINESS%s'%code : leave_business_days,
    #                     code : vac_days_in_payslip,
    #                     'HOLIDAYS%s'%code : holidays,
    #                     'BUSINESS%s'%code : business_days,
    #                     '31HOLIDAYS%s'%code : days_31_h,
    #                     '31BUSINESS%s'%code : days_31_b,
    #                 })

    #     leaves_time = list(leaves.values())
        
    #     _logger.info('\n\n %r \n\n', leaves_time)
    #     #Vacaciones Remuneradas
    #     # leaves_time = list(set(leaves_time))
    #     if len(self.paid_vacation_ids) > 0:
    #         for paid in self.paid_vacation_ids.sorted(key=lambda w:w.start_date_paid_vacation):
    #             leaves = {
    #                 'IDPAID' : paid.id,
    #                 'VACREMUNERADAS' : paid.paid_vacation_days,
    #                 'DATE' : paid.start_date_paid_vacation,
    #                 }
    #             leaves_money.append(leaves)
    #     '''
    #     Validar que no queden las deducciones en la nómina si ya estan en vacaciones
    #     '''

    #     #Calcular antiguedad del empleado
    #     antiquity_employee = relativedelta(fields.Date.today() , contract.date_start).years

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
    #                 'leaves':  BrowsableObject(employee.id, leaves, self.env),
    #                 'employee': employee,
    #                 'contract': contract,
    #                 'annual_parameters': annual_parameters,
    #                 'antiquity_employee': antiquity_employee,
    #                 'inherit_contrato':inherit_contrato,
    #                 'values_base_vacremuneradas': 0,
    #                 'values_base_vacdisfrutadas': 0,
    #                 'values_base_seguridad_social': 1.0,
    #                 'values_base_seguridad_social_no_salarial': 0.0,
    #                 'values_base_provisiones': 0.0,
    #             }
    #         }
    #     else:
    #         localdict.update({
    #             'antiquity_employee': antiquity_employee,
    #             'inherit_contrato':inherit_contrato,})        
        
    #     #Ejecutar las reglas salariales y su respectiva lógica
    #     for rule in sorted(self.struct_id.rule_ids, key=lambda x: x.sequence):
    #         localdict.update({
    #             'result': None,
    #             'result_qty': 1.0,
    #             'result_rate': 100})
    #         if rule._satisfy_condition(localdict):
    #             if rule.code == 'VACDISFRUTADAS' or (self.get_pay_vacations_in_payroll() == False or inherit_nomina!=0):
    #                 initial_accrual_date = False
    #                 final_accrual_date = False                    
    #                 for leaves in leaves_time:
    #                     _logger.info(leaves.get('IDLEAVE'))
    #                     _logger.info(leaves.get('31HOLIDAYSVACDISFRUTADAS',0))
    #                     if inherit_nomina != 0:
    #                         id_leave = leaves.get('IDLEAVE')
    #                         obj_leave = self.env['hr.leave'].search([('id', '=', id_leave)])
    #                         days_vacations = leaves.get('VACDISFRUTADAS',0)
    #                         days_vacations_business = leaves.get('BUSINESSVACDISFRUTADAS',0)
    #                         days_vacations_31_business = leaves.get('31BUSINESSVACDISFRUTADAS',0)
    #                         days_vacations_holidays = leaves.get('HOLIDAYSVACDISFRUTADAS',0)
    #                         days_vacations_31_holidays = leaves.get('31HOLIDAYSVACDISFRUTADAS',0)
    #                     else:
    #                         id_leave = leaves.get('IDLEAVE')
    #                         obj_leave = self.env['hr.leave'].search([('id', '=', id_leave)])
    #                         obj_leave_equals = self.env['hr.leave'].search([('state','=','validate'),('employee_id','=',employee.id),('id','!=',id_leave),('is_vacation','=',True),('request_date_from', '>=', obj_leave.request_date_from),('request_date_to', '<=', obj_leave.request_date_to)])
    #                         days_vacations = obj_leave.number_of_days if obj_leave.business_days + obj_leave.days_31_business == 0 else obj_leave.business_days + obj_leave.days_31_business
    #                         days_vacations_business = obj_leave.business_days
    #                         days_vacations_31_business = obj_leave.days_31_business
    #                         days_vacations_holidays = obj_leave.holidays
    #                         days_vacations_31_holidays = obj_leave.days_31_holidays
    #                         for leave_equals in obj_leave_equals:
    #                             days_vacations += leave_equals.number_of_days if leave_equals.business_days + leave_equals.days_31_business == 0 else leave_equals.business_days + leave_equals.days_31_business
    #                             days_vacations_business += leave_equals.business_days
    #                             days_vacations_31_business += leave_equals.days_31_business
    #                             days_vacations_holidays += leave_equals.holidays
    #                             days_vacations_31_holidays += leave_equals.days_31_holidays
    #                         #Remuneradas
    #                         for paid_vacation in self.paid_vacation_ids:
    #                            if obj_leave.request_date_from:
    #                                if paid_vacation.start_date_paid_vacation >= obj_leave.request_date_from and paid_vacation.end_date_paid_vacation <= obj_leave.request_date_to:
    #                                    days_vacations += paid_vacation.paid_vacation_days
    #                     obj_leave_days = self.env['hr.leave'].search([('id', '=', id_leave)])
    #                     _logger.info(obj_leave_days)
    #                     days_vacations_d = obj_leave_days.business_days
    #                     localdict.update({'leaves':  BrowsableObject(employee.id, leaves, self.env)})
    #                     amount, qty, rate = rule._compute_rule(localdict)
    #                     #check if there is already a rule computed with that code
    #                     previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
    #                     #set/overwrite the amount computed for this rule in the localdict
    #                     tot_rule = (amount * qty * rate / 100.0) + previous_amount
    #                     localdict[rule.code] = tot_rule
    #                     rules_dict[rule.code] = rule
    #                     # sum the amount for its salary category
    #                     localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount) 
    #                     localdict = _sum_salary_rule(localdict, rule, tot_rule)
    #                     #Calculo fechas de causacion                        
    #                     if initial_accrual_date and final_accrual_date:
    #                         initial_accrual_date = final_accrual_date + timedelta(days=1)
    #                         days = (days_vacations * 365) / 15
    #                         final_accrual_date = initial_accrual_date + timedelta(days=days-1)
    #                     else:
    #                         obj_vacation = self.env['hr.vacation'].search([('employee_id', '=', employee.id)])     
    #                         if obj_vacation:
    #                             query = 'Select Max(final_accrual_date) as final_accrual_date From hr_vacation Where employee_id = '+ str(employee.id)

    #                             self.env.cr.execute(query)
    #                             result_query = self.env.cr.fetchone()
    #                             accrual_date = result_query[0] + timedelta(days=1)
    #                             accrual_date = accrual_date if accrual_date >= contract.date_start else contract.date_start
    #                         else:
    #                             accrual_date = contract.date_start

    #                         #fecha inicial causación
    #                         initial_accrual_date = accrual_date
    #                         #fecha final causación
    #                         days = (days_vacations * 365) / 15
    #                         final_accrual_date = initial_accrual_date + timedelta(days=days-1)   
    #                         #dias360 = self.dias360(initial_accrual_date,final_accrual_date)

    #                     # create/overwrite the rule in the temporary results
    #                    #if amount != 0:
    #                     result[str(id_leave)+'_'+rule.code] = {
    #                         'sequence': rule.sequence,
    #                         'code': rule.code,
    #                         'name': rule.name,
    #                         'note': rule.note,
    #                         'initial_accrual_date': initial_accrual_date,
    #                         'final_accrual_date': final_accrual_date,
    #                         'amount_base': amount*30,
    #                         'business_units': days_vacations_business,
    #                         'business_31_units': days_vacations_31_business,
    #                         'holiday_units': days_vacations_holidays,
    #                         'holiday_31_units': days_vacations_31_holidays,
    #                         'salary_rule_id': rule.id,
    #                         'contract_id': contract.id,
    #                         'employee_id': employee.id,                        
    #                         'amount': amount,
    #                         'quantity': qty,
    #                         'rate': rate,
    #                         'slip_id': self.id,
    #                         #Info vacaciones
    #                         'vacation_departure_date': obj_leave.request_date_from,
    #                         'vacation_return_date': obj_leave.request_date_to,
    #                         'vacation_leave_id': obj_leave.id,
    #                     }
    #                     continue
    #             elif rule.code == 'VACREMUNERADAS':
    #                 initial_accrual_date = False
    #                 final_accrual_date = False                    
    #                 for leaves in leaves_money:
    #                     id_leave = leaves.get('IDPAID')
    #                     obj_leave_equals = self.env['hr.leave'].search([('state','=','validate'),('employee_id','=',employee.id),('is_vacation','=',True),('request_date_from', '=', leaves.get('DATE'))])  #('request_date_to', '<=', obj_leave.request_date_to)
    #                     days_vacations = leaves.get('VACREMUNERADAS')
    #                     if pay_vacations_in_payroll == False:
    #                         for leave_equals in obj_leave_equals:
    #                             days_vacations += leave_equals.number_of_days if leave_equals.business_days + leave_equals.days_31_business == 0 else leave_equals.business_days + leave_equals.days_31_business

    #                     localdict.update({'leaves':  BrowsableObject(employee.id, leaves, self.env)})
    #                     amount, qty, rate = rule._compute_rule(localdict)
    #                     #check if there is already a rule computed with that code
    #                     previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
    #                     #set/overwrite the amount computed for this rule in the localdict
    #                     tot_rule = (amount * qty * rate / 100.0) + previous_amount
    #                     localdict[rule.code] = tot_rule
    #                     rules_dict[rule.code] = rule
    #                     # sum the amount for its salary category
    #                     localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount) 
    #                     localdict = _sum_salary_rule(localdict, rule, tot_rule)
    #                     #Calculo fechas de causacion                        
    #                     if initial_accrual_date and final_accrual_date:
    #                         initial_accrual_date = final_accrual_date + timedelta(days=1)
    #                         days = (days_vacations * 365) / 15
    #                         final_accrual_date = initial_accrual_date + timedelta(days=days-1)
    #                     else:
    #                         obj_vacation = self.env['hr.vacation'].search([('employee_id', '=', employee.id)])     
    #                         if obj_vacation:
    #                             query = 'Select Max(final_accrual_date) as final_accrual_date From hr_vacation Where employee_id = '+ str(employee.id)

    #                             self.env.cr.execute(query)
    #                             result_query = self.env.cr.fetchone()
    #                             accrual_date = result_query[0] + timedelta(days=1)
    #                             accrual_date = accrual_date if accrual_date >= contract.date_start else contract.date_start
    #                         else:
    #                             accrual_date = contract.date_start

    #                         #fecha inicial causación
    #                         initial_accrual_date = accrual_date
    #                         #fecha final causación
    #                         days = (days_vacations * 365) / 15                            
    #                         #for obj_leave in leaves_all_obj:
    #                         final_accrual_date = initial_accrual_date + timedelta(days=days-1)   
    #                         #dias360 = self.dias360(initial_accrual_date,final_accrual_date)

    #                     # create/overwrite the rule in the temporary results
    #                     if amount != 0:
    #                         result[str(id_leave)+'_'+rule.code] = {
    #                             'sequence': rule.sequence,
    #                             'code': rule.code,
    #                             'name': rule.name,
    #                             'note': rule.note,
    #                             'initial_accrual_date': initial_accrual_date,
    #                             'final_accrual_date': final_accrual_date,
    #                             'amount_base': amount*30,
    #                             'salary_rule_id': rule.id,
    #                             'contract_id': contract.id,
    #                             'employee_id': employee.id,                        
    #                             'amount': amount,
    #                             'quantity': qty,
    #                             'rate': rate,
    #                             'slip_id': self.id,
    #                         }
    #             else:
    #                 amount, qty, rate = rule._compute_rule(localdict)
    #                 dias_ausencias,amount_base = 0,0
    #                 initial_accrual_date = False
    #                 final_accrual_date = False

    #                 if rule.code == 'VACCONTRATO' and inherit_contrato != 0:    
    #                     amount_base = amount
    #                     initial_accrual_date = self.date_vacaciones
    #                     final_accrual_date = self.date_liquidacion
    #                     acumulados_promedio = 0
    #                     dias_trabajados = self.dias360(self.date_vacaciones, self.date_liquidacion)
    #                     dias_ausencias =  sum([i.number_of_days for i in self.env['hr.leave'].search([('date_from','>=',self.date_vacaciones),('date_to','<=',self.date_liquidacion),('state','=','validate'),('employee_id','=',self.employee_id.id),('unpaid_absences','=',True)])])
    #                     dias_ausencias += sum([i.days for i in self.env['hr.absence.history'].search([('star_date', '>=', self.date_vacaciones), ('end_date', '<=', self.date_liquidacion),('employee_id', '=', self.employee_id.id), ('leave_type_id.unpaid_absences', '=', True)])])
    #                     dias_vacation = sum([i.units_of_money for i in self.env['hr.vacation'].search([('contract_id', '>=', self.contract_id.id), ('employee_id', '=', self.employee_id.id)])])
    #                     dias_liquidacion = dias_trabajados - dias_ausencias - (dias_vacation / 0.0417)
    #                     if (self.date_liquidacion - contract.date_start).days <= 365:
    #                         if dias_liquidacion > 0:
    #                             acumulados_promedio = (amount_base/dias_liquidacion)*30
    #                         else:
    #                             acumulados_promedio = 0
    #                     else:
    #                         acumulados_promedio = amount_base/12

    #                     amount_base = contract.wage + acumulados_promedio

    #                     amount = amount_base / 720
    #                     qty = dias_liquidacion

    #                 #check if there is already a rule computed with that code
    #                 previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
    #                 #set/overwrite the amount computed for this rule in the localdict
    #                 tot_rule = (amount * qty * rate / 100.0) + previous_amount
    #                 localdict[rule.code] = tot_rule
    #                 rules_dict[rule.code] = rule
    #                 # sum the amount for its salary category
    #                 localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount) 
    #                 localdict = _sum_salary_rule(localdict, rule, tot_rule)
    #                 # create/overwrite the rule in the temporary results
    #                 if amount != 0:
    #                     result[rule.code] = {
    #                         'sequence': rule.sequence,
    #                         'code': rule.code,
    #                         'name': rule.name,
    #                         'note': rule.note,
    #                         'salary_rule_id': rule.id,
    #                         'contract_id': contract.id,
    #                         'employee_id': employee.id, 
    #                         'initial_accrual_date': initial_accrual_date,
    #                         'final_accrual_date': final_accrual_date,
    #                         'amount_base': amount_base,                       
    #                         'amount': amount,
    #                         'quantity': qty,
    #                         'rate': rate,
    #                         'days_unpaid_absences':dias_ausencias,
    #                         'slip_id': self.id,
    #                     }
    #     def _sum_salary_rule(localdict, rule, amount):
    #         localdict['rules_computed'].dict[rule.code] = localdict['rules_computed'].dict.get(rule.code, 0) + amount
    #         #Sumatoria de valores que son base para los procesos
    #         if rule.base_seguridad_social:
    #             localdict['values_base_seguridad_social'] += amount if rule.base_seguridad_social else 1.0
    #         if rule.category_id.code == 'DEV_NO_SALARIAL':
    #             localdict['values_base_seguridad_social_no_salarial'] += amount if rule.category_id.code == 'DEV_NO_SALARIAL' else 1.0
    #         if rule.base_prima:
    #             localdict['values_base_provisiones'] += amount if rule.base_prima else 1.0
    #         if rule.base_vacaciones:
    #             localdict['values_base_vacaciones'] += amount if rule.base_vacaciones else 1.0
    #         return localdict
        
    #     #Ejecutar reglas salariales de la nómina de pago regular
    #     # if inherit_contrato == 0 and inherit_nomina == 0:
    #     #     obj_struct_payroll = self.env['hr.payroll.structure'].search([('regular_pay','=',True),('process','=','nomina')])
    #     #     struct_original = self.struct_id.id
    #     #     self.struct_id = obj_struct_payroll.id
    #     #     result_payroll = self._get_payslip_lines(inherit_vacation=1,localdict=localdict)
    #     #     self.struct_id = struct_original
    #     #     result_finally = {**result,**result_payroll}        
    #     #     #Retornar resultado final de la liquidación de nómina
    #     #     return result_finally.values()  
    #     #else:
    #     return localdict,result



    # def _get_payslip_lines_vacation_prv(self,inherit_contrato=0,localdict=None,inherit_nomina=0):
    #     def _sum_salary_rule_category(localdict, category, amount):
    #         if category.parent_id:
    #             localdict = _sum_salary_rule_category(localdict, category.parent_id, amount)
    #         localdict['categories'].dict[category.code] = localdict['categories'].dict.get(category.code, 0) + amount
    #         return localdict

    #     def _sum_salary_rule(localdict, rule, amount):
    #         localdict['rules_computed'].dict[rule.code] = localdict['rules_computed'].dict.get(rule.code, 0) + amount
    #         return localdict

    #     self.ensure_one()
    #     result = {}
    #     result_not = {}
    #     rules_dict = {}
    #     worked_days_dict = {line.code: line for line in self.worked_days_line_ids if line.code}
    #     inputs_dict = {line.code: line for line in self.input_line_ids if line.code}
    #     pay_vacations_in_payroll = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.pay_vacations_in_payroll')) or False
    #     round_payroll = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.round_payroll')) or False

    #     employee = self.employee_id
    #     contract = self.contract_id
    #     year = self.date_from.year
    #     annual_parameters = self.env['hr.annual.parameters'].search([('year', '=', year)])

    #     #Se obtienen las entradas de trabajo
    #     date_from = datetime.combine(self.date_from, datetime.min.time())
    #     date_to = datetime.combine(self.date_to, datetime.max.time())
    #     #Primero, encontró una entrada de trabajo que no excedió el intervalo.
    #     work_entries = self.env['hr.work.entry'].search(
    #         [
    #             ('state', 'in', ['validated', 'draft']),
    #             ('date_start', '>=', date_from),
    #             ('date_stop', '<=', date_to),
    #             ('contract_id', '=', contract.id),
    #             ('leave_id','!=',False)
    #         ]
    #     )
    #     #En segundo lugar, encontró entradas de trabajo que exceden el intervalo y calculan la duración correcta. 
    #     work_entries += self.env['hr.work.entry'].search(
    #         [
    #             '&', '&',
    #             ('state', 'in', ['validated', 'draft']),
    #             ('contract_id', '=', contract.id),
    #             '|', '|', '&', '&',
    #             ('date_start', '>=', date_from),
    #             ('date_start', '<', date_to),
    #             ('date_stop', '>', date_to),
    #             '&', '&',
    #             ('date_start', '<', date_from),
    #             ('date_stop', '<=', date_to),
    #             ('date_stop', '>', date_from),
    #             '&',
    #             ('date_start', '<', date_from),
    #             ('date_stop', '>', date_to),
    #         ]
    #     )
        
    #     initial_accrual_date = False
    #     final_accrual_date = False
    #     leave_holidays = 0
    #     leave_business_days = 0
    #     leave_number_of_days = 0
    #     leaves_time = []
    #     leaves_money = []
    #     leaves = {}
    #     for leave in work_entries.sorted(key=lambda w:w.date_start):
    #         leaves = {}          
    #         if leave.leave_id.holiday_status_id.is_vacation:
    #             leave_holidays = leave.leave_id.holidays
    #             leave_business_days = leave.leave_id.business_days
    #             leave_number_of_days = leave.leave_id.number_of_days

    #             leaves['IDLEAVE'] = leave.leave_id.id
    #             leaves[leave.work_entry_type_id.code] = leave_number_of_days
    #             leaves['HOLIDAYS'+leave.work_entry_type_id.code] = leave_holidays          
    #             leaves['BUSINESS'+leave.work_entry_type_id.code] = leave_business_days     

    #             #Días pertenecientes a la liquidación de nómina
    #             if inherit_nomina != 0:
    #                 # Obtener si el dia sabado es habil | Guardar dias fines de semana 5=Sabado & 6=Domingo
    #                 lst_days = [5, 6] if employee.sabado == False else [6]
    #                 #Obtener fechas
    #                 initial_date = leave.leave_id.request_date_from if leave.leave_id.request_date_from >= self.date_from else self.date_from
    #                 end_date = leave.leave_id.request_date_to if leave.leave_id.request_date_to <= self.date_to else self.date_to
    #                 #Dias
    #                 vac_days_in_payslip = 0
    #                 holidays = 0
    #                 business_days = 0
    #                 days_31_b = 0
    #                 days_31_h = 0
    #                 while initial_date <= end_date:
    #                     vac_days_in_payslip += 1
    #                     if not initial_date.weekday() in lst_days:
    #                         # Obtener dias festivos parametrizados
    #                         obj_holidays = self.env['lavish.holidays'].search([('date', '=', initial_date)])
    #                         if obj_holidays:
    #                             holidays += 1
    #                             days_31_h += 1 if initial_date.day == 31 else 0
    #                         else:
    #                             business_days += 1
    #                             days_31_b += 1 if initial_date.day == 31 else 0
    #                     else:
    #                         holidays += 1
    #                         days_31_h += 1 if initial_date.day == 31 else 0
    #                     initial_date = initial_date + timedelta(days=1)

    #                 leaves['ORIGINAL_'+leave.work_entry_type_id.code] = leave_number_of_days
    #                 leaves['ORIGINAL_HOLIDAYS' + leave.work_entry_type_id.code] = leaves['HOLIDAYS' + leave.work_entry_type_id.code]
    #                 leaves['ORIGINAL_BUSINESS' + leave.work_entry_type_id.code] = leaves['BUSINESS' + leave.work_entry_type_id.code]
    #                 leaves[leave.work_entry_type_id.code] = vac_days_in_payslip
    #                 leaves['HOLIDAYS' + leave.work_entry_type_id.code] = holidays
    #                 leaves['BUSINESS' + leave.work_entry_type_id.code] = business_days
    #                 leaves['31HOLIDAYS' + leave.work_entry_type_id.code] = days_31_h
    #                 leaves['31BUSINESS' + leave.work_entry_type_id.code] = days_31_b

    #             leaves_time.append(leaves)

    #     #Vacaciones Remuneradas
    #     if len(self.paid_vacation_ids) > 0:
    #         for paid in self.paid_vacation_ids.sorted(key=lambda w:w.start_date_paid_vacation):
    #             leaves = {}

    #             leave_number_of_days = paid.paid_vacation_days
    #             leaves['IDPAID'] = paid.id
    #             leaves['VACREMUNERADAS'] = leave_number_of_days
    #             leaves['DATE'] = paid.start_date_paid_vacation

    #             leaves_money.append(leaves)
        
    #     '''
    #     Validar que no queden las deducciones en la nómina si ya estan en vacaciones
    #     '''

    #     #Calcular antiguedad del empleado
    #     antiquity_employee = relativedelta(fields.Date.today() , contract.date_start).years

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
    #                 'leaves':  BrowsableObject(employee.id, leaves, self.env),
    #                 'employee': employee,
    #                 'contract': contract,
    #                 'annual_parameters': annual_parameters,
    #                 'antiquity_employee': antiquity_employee,
    #                 'inherit_contrato':inherit_contrato,
    #                 'values_base_vacremuneradas': 0,
    #                 'values_base_vacdisfrutadas': 0,
    #             }
    #         }
    #     else:
    #         localdict.update({
    #             'antiquity_employee': antiquity_employee,
    #             'inherit_contrato':inherit_contrato,})        
        
    #     #Ejecutar las reglas salariales y su respectiva lógica
    #     for rule in sorted(self.struct_id.rule_ids, key=lambda x: x.sequence):
    #         localdict.update({
    #             'result': None,
    #             'result_qty': 1.0,
    #             'result_rate': 100})
    #         if rule._satisfy_condition(localdict):

    #             if rule.code == 'VACDISFRUTADAS': #or (self.get_pay_vacations_in_payroll() == False or inherit_nomina!=0):
    #                 initial_accrual_date = False
    #                 final_accrual_date = False                    
    #                 for leaves in leaves_money:
    #                     id_leave = leaves.get('IDPAID')
    #                     obj_leave_equals = self.env['hr.leave'].search([('state','=','validate'),('employee_id','=',employee.id),('is_vacation','=',True),('request_date_from', '=', leaves.get('DATE'))])  #('request_date_to', '<=', obj_leave.request_date_to)
    #                     days_vacations = leaves.get('VACDISFRUTADAS')
    #                     #if pay_vacations_in_payroll == False:
    #                     for leave_equals in obj_leave_equals:
    #                         days_vacations += leave_equals.number_of_days #if leave_equals.business_days + leave_equals.days_31_business == 0 else leave_equals.business_days + leave_equals.days_31_business

    #                     localdict.update({'leaves':  BrowsableObject(employee.id, leaves, self.env)})
    #                     amount, qty, rate = rule._compute_rule(localdict)
    #                     #check if there is already a rule computed with that code
    #                     previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
    #                     #set/overwrite the amount computed for this rule in the localdict
    #                     tot_rule = (amount * qty * rate / 100.0) + previous_amount
    #                     localdict[rule.code] = tot_rule
    #                     rules_dict[rule.code] = rule
    #                     # sum the amount for its salary category
    #                     localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount) 
    #                     localdict = _sum_salary_rule(localdict, rule, tot_rule)
    #                     #Calculo fechas de causacion                        
    #                     if initial_accrual_date and final_accrual_date:
    #                         initial_accrual_date = final_accrual_date + timedelta(days=1)
    #                         days = (days_vacations * 365) / 15
    #                         final_accrual_date = initial_accrual_date + timedelta(days=days-1)
    #                     else:
    #                         obj_vacation = self.env['hr.vacation'].search([('employee_id', '=', employee.id)])     
    #                         if obj_vacation:
    #                             query = 'Select Max(final_accrual_date) as final_accrual_date From hr_vacation Where employee_id = '+ str(employee.id)

    #                             self.env.cr.execute(query)
    #                             result_query = self.env.cr.fetchone()
    #                             accrual_date = result_query[0] + timedelta(days=1)
    #                             accrual_date = accrual_date if accrual_date >= contract.date_start else contract.date_start
    #                         else:
    #                             accrual_date = contract.date_start

    #                         #fecha inicial causación
    #                         initial_accrual_date = accrual_date
    #                         #fecha final causación
    #                         days = (days_vacations * 365) / 15                            
    #                         #for obj_leave in leaves_all_obj:
    #                         final_accrual_date = initial_accrual_date + timedelta(days=days-1)   
    #                         #dias360 = self.dias360(initial_accrual_date,final_accrual_date)

    #                     # create/overwrite the rule in the temporary results
    #                     if amount != 0:                    
    #                         result[str(id_leave)+'_'+rule.code] = {
    #                             'sequence': rule.sequence,
    #                             'code': rule.code,
    #                             'name': rule.name,
    #                             'note': rule.note,
    #                             'initial_accrual_date': initial_accrual_date,
    #                             'final_accrual_date': final_accrual_date,
    #                             'amount_base': amount*30,
    #                             'salary_rule_id': rule.id,
    #                             'contract_id': contract.id,
    #                             'employee_id': employee.id,                        
    #                             'amount': amount,
    #                             'quantity': qty + 1,
    #                             'rate': rate,
    #                             'slip_id': self.id,
    #                         }
    #             else:
    #                 amount, qty, rate = rule._compute_rule(localdict)
    #                 dias_ausencias,amount_base = 0,0
    #                 initial_accrual_date = False
    #                 final_accrual_date = False

    #                 if rule.code == 'VACCONTRATO' and inherit_contrato != 0:    
    #                     amount_base = amount
    #                     initial_accrual_date = self.date_vacaciones
    #                     final_accrual_date = self.date_liquidacion
    #                     acumulados_promedio = 0
    #                     dias_trabajados = self.dias360(self.date_vacaciones, self.date_liquidacion)
    #                     dias_ausencias =  sum([i.number_of_days for i in self.env['hr.leave'].search([('date_from','>=',self.date_vacaciones),('date_to','<=',self.date_liquidacion),('state','=','validate'),('employee_id','=',self.employee_id.id),('unpaid_absences','=',True)])])
    #                     dias_ausencias += sum([i.days for i in self.env['hr.absence.history'].search([('star_date', '>=', self.date_vacaciones), ('end_date', '<=', self.date_liquidacion),('employee_id', '=', self.employee_id.id), ('leave_type_id.unpaid_absences', '=', True)])])
    #                     dias_vacation = sum([i.units_of_money for i in self.env['hr.vacation'].search([('contract_id', '>=', self.contract_id.id), ('employee_id', '=', self.employee_id.id)])])
    #                     dias_liquidacion = dias_trabajados - dias_ausencias - (dias_vacation / 0.0417)
    #                     if (self.date_liquidacion - contract.date_start).days <= 365:
    #                         if dias_liquidacion > 0:
    #                             acumulados_promedio = (amount_base/dias_liquidacion)*30
    #                         else:
    #                             acumulados_promedio = 0
    #                     else:
    #                         acumulados_promedio = amount_base/12

    #                     amount_base = contract.wage + acumulados_promedio

    #                     amount = amount_base / 720
    #                     qty = dias_liquidacion

    #                 #check if there is already a rule computed with that code
    #                 previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
    #                 #set/overwrite the amount computed for this rule in the localdict
    #                 tot_rule = (amount * qty * rate / 100.0) + previous_amount
    #                 localdict[rule.code] = tot_rule
    #                 rules_dict[rule.code] = rule
    #                 # sum the amount for its salary category
    #                 localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount) 
    #                 localdict = _sum_salary_rule(localdict, rule, tot_rule)
    #                 # create/overwrite the rule in the temporary results
    #                 if amount != 0:                    
    #                     result[rule.code] = {
    #                         'sequence': rule.sequence,
    #                         'code': rule.code,
    #                         'name': rule.name,
    #                         'note': rule.note,
    #                         'salary_rule_id': rule.id,
    #                         'contract_id': contract.id,
    #                         'employee_id': employee.id, 
    #                         'initial_accrual_date': initial_accrual_date,
    #                         'final_accrual_date': final_accrual_date,
    #                         'amount_base': amount_base,                       
    #                         'amount': amount,
    #                         'quantity': qty,
    #                         'rate': rate,
    #                         'days_unpaid_absences':dias_ausencias,
    #                         'slip_id': self.id,
    #                     }
    #     def _sum_salary_rule(localdict, rule, amount):
    #         localdict['rules_computed'].dict[rule.code] = localdict['rules_computed'].dict.get(rule.code, 0) + amount
    #         #Sumatoria de valores que son base para los procesos
    #         if rule.base_seguridad_social:
    #             localdict['values_base_seguridad_social'] += amount if rule.base_seguridad_social else 1.0
    #         if rule.category_id.code == 'DEV_NO_SALARIAL':
    #             localdict['values_base_seguridad_social_no_salarial'] += amount if rule.category_id.code == 'DEV_NO_SALARIAL' else 1.0
    #         if rule.base_prima:
    #             localdict['values_base_provisiones'] += amount if rule.base_prima else 1.0
    #         if rule.base_vacaciones:
    #             localdict['values_base_vacaciones'] += amount if rule.base_vacaciones else 1.0
    #         return localdict
        
    #     #Ejecutar reglas salariales de la nómina de pago regular
    #     if inherit_contrato == 0 and inherit_nomina == 0:
    #         obj_struct_payroll = self.env['hr.payroll.structure'].search([('regular_pay','=',True),('process','=','nomina')])
    #         struct_original = self.struct_id.id
    #         self.struct_id = obj_struct_payroll.id
    #         result_payroll = self._get_payslip_lines(inherit_vacation=1,localdict=localdict)
    #         self.struct_id = struct_original
        
    #         result_finally = {**result,**result_payroll}        
    #         #Retornar resultado final de la liquidación de nómina
    #         return result_finally.values()  
    #     else:
    #         return localdict,result           