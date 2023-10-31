# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from .browsable_object import BrowsableObject, InputLine, WorkedDays, Payslips
from odoo.tools import float_compare, float_is_zero

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import math

class hr_history_prima(models.Model):
    _name = 'hr.history.prima'
    _description = 'Historico de prima'
    
    employee_id = fields.Many2one('hr.employee', 'Empleado')
    employee_identification = fields.Char('Identificación empleado')
    initial_accrual_date = fields.Date('Fecha inicial de causación')
    final_accrual_date = fields.Date('Fecha final de causación')
    settlement_date = fields.Date('Fecha de liquidación')
    time = fields.Float('Tiempo')
    base_value = fields.Float('Valor base')
    bonus_value = fields.Float('Valor de prima')
    payslip = fields.Many2one('hr.payslip', 'Liquidación')
    contract_id = fields.Many2one('hr.contract', 'Contrato')
    
    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "Prima {} del {} al {}".format(record.employee_id.name, str(record.initial_accrual_date),str(record.final_accrual_date))))
        return result

    @api.model
    def create(self, vals):
        if vals.get('employee_identification'):
            obj_employee = self.env['hr.employee'].search([('identification_id', '=', vals.get('employee_identification'))])            
            vals['employee_id'] = obj_employee.id
        if vals.get('employee_id'):
            obj_employee = self.env['hr.employee'].search([('id', '=', vals.get('employee_id'))])            
            vals['employee_identification'] = obj_employee.identification_id            
        
        res = super(hr_history_prima, self).create(vals)
        return res
class Hr_payslip(models.Model):
    _inherit = 'hr.payslip'

    prima_run_reverse_id = fields.Many2one('hr.payslip.run', string='Lote de prima a ajustar')
    prima_payslip_reverse_id = fields.Many2one('hr.payslip', string='Prima a ajustar', domain="[('employee_id', '=', employee_id)]")

    #--------------------------------------------------LIQUIDACIÓN DE PRIMA---------------------------------------------------------#

    def _get_payslip_lines_prima(self,inherit_contrato=0,localdict=None, values_base_prima=0):
        def _sum_salary_rule_category(localdict, category, amount):
            if category.parent_id:
                localdict = _sum_salary_rule_category(localdict, category.parent_id, amount)
            localdict['categories'].dict[category.code] = localdict['categories'].dict.get(category.code, 0) + amount
            return localdict

        def _sum_salary_rule(localdict, rule, amount):
            localdict['rules_computed'].dict[rule.code] = localdict['rules_computed'].dict.get(rule.code, 0) + amount
            return localdict

        # Validar si es ajuste de prima
        if self.prima_run_reverse_id and not self.prima_payslip_reverse_id:
            prima_payslip_reverse_obj = self.env['hr.payslip'].search(
                [('payslip_run_id', '=', self.prima_run_reverse_id.id),
                 ('employee_id', '=', self.employee_id.id)], limit=1)
            if len(prima_payslip_reverse_obj) == 1:
                self.prima_payslip_reverse_id = prima_payslip_reverse_obj.id

        #Validar fecha inicial de causación
        if inherit_contrato == 0:
            date_prima = self.contract_id.date_start

            # Buscar registros en 'hr.history.prima'
            obj_prima = self.env['hr.history.prima'].search([
                ('employee_id', '=', self.employee_id.id),
                ('contract_id', '=', self.contract_id.id)
            ], order="final_accrual_date asc")

            if obj_prima:
                last_history_date = obj_prima[-1].final_accrual_date  # obtenemos la última fecha ya que está ordenado ascendentemente
                date_prima = max(last_history_date + timedelta(days=1), date_prima)

            # Si 'date_from' es falso (vacío) o es anterior a 'date_prima', establecerlo como 'date_prima'
            if not self.date_prima or self.date_prima < date_prima:
                self.date_prima = date_prima

            # Asegurarse de que 'date_from' no sea más de 6 meses antes de 'date_to'
            if self.date_prima < self.date_to - timedelta(days=180):  # 180 días es aproximadamente 6 meses
                self.date_prima = self.date_to - timedelta(days=180)

        self.ensure_one()
        result = {}
        rules_dict = {}
        worked_days_dict = {line.code: line for line in self.worked_days_line_ids if line.code}
        inputs_dict = {line.code: line for line in self.input_line_ids if line.code}
        round_payroll = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.round_payroll')) or False
        prima_salary_take = bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.prima_salary_take')) or False
        
        employee = self.employee_id
        contract = self.contract_id

        # Se eliminan registros actuales para el periodo ejecutado de Retención en la fuente
        self.env['hr.employee.deduction.retention'].search(
            [('employee_id', '=', employee.id), ('year', '=', self.date_to.year),
             ('month', '=', self.date_to.month)]).unlink()
        self.env['hr.employee.rtefte'].search([('employee_id', '=', employee.id), ('year', '=', self.date_to.year),
                                               ('month', '=', self.date_to.month)]).unlink()

        if contract.modality_salary == 'integral' or contract.contract_type == 'aprendizaje' or contract.subcontract_type == 'obra_integral':
            return result.values()

        year = self.date_from.year
        annual_parameters = self.env['hr.annual.parameters'].search([('year', '=', year)])
        leaves = {}
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
                    'inherit_contrato':inherit_contrato,   
                    'values_base_prima': values_base_prima,                 
                }
            }
        else:
            localdict.update({
                'inherit_contrato':inherit_contrato,})        
        
        all_rules = self.env['hr.salary.rule'].browse([])
        if not self.struct_id.process == 'vacaciones':
            all_rules = self.struct_id.rule_ids
        specific_rules = self.env['hr.salary.rule'].browse([])
        obj_struct_payroll = self.env['hr.payroll.structure'].search([
            ('regular_pay', '=', True),
            ('process', '=', 'nomina')
        ])
        if obj_struct_payroll:
            if self.struct_id.process == 'prima' and  inherit_contrato == 0:
            # Fetching rules with specific codes
                specific_rule_codes = ['IBC_R', 'TOTALDEV', 'TOTALDED', 'NET']
                specific_rules = self.env['hr.salary.rule'].search([
                    '|',  # Esto indica que la siguiente condición es un OR
                    ('code', 'in', specific_rule_codes),
                    ('type_concepts', '=', 'ley'),  
                    ('id', 'in', obj_struct_payroll.mapped('rule_ids').ids)  # Asegura que solo consideramos reglas en la estructura que encontramos
                ])
                all_rules |= specific_rules
        #for rule in sorted(self.struct_id.rule_ids, key=lambda x: x.sequence):
        for rule in sorted(all_rules, key=lambda x: x.sequence):
            localdict.update({                
                'result': None,
                'result_qty': 1.0,
                'result_rate': 100})
            if rule._satisfy_condition(localdict) or rule.code == "PRIMA":                
                amount, qty, rate = rule._compute_rule(localdict)
                dias_ausencias, amount_base = 0, 0
                dias_trabajados = 0.0
                wage_average=0.0
                wage = 0.0
                acumulados_promedio = 0.0
                amount_base = 0.0
                auxtransporte = 0.0
                if rule.code == 'PRIMA':
                    amount_base = amount
                    dias_trabajados = self.dias360(self.date_prima, self.date_to)
                    dias_ausencias =  sum([i.number_of_days for i in self.env['hr.leave'].search([('date_from','>=',self.date_prima),('date_to','<=',self.date_to),('state','=','validate'),('employee_id','=',self.employee_id.id),('unpaid_absences','=',True)])])
                    dias_ausencias += sum([i.days for i in self.env['hr.absence.history'].search([('star_date', '>=', self.date_prima), ('end_date', '<=', self.date_to),('employee_id', '=', self.employee_id.id), ('leave_type_id.unpaid_absences', '=', True)])])
                    if inherit_contrato != 0:
                        dias_trabajados = self.dias360(self.date_prima, self.date_liquidacion)
                        dias_ausencias =  sum([i.number_of_days for i in self.env['hr.leave'].search([('date_from','>=',self.date_prima),('date_to','<=',self.date_liquidacion),('state','=','validate'),('employee_id','=',self.employee_id.id),('unpaid_absences','=',True)])])
                        dias_ausencias += sum([i.days for i in self.env['hr.absence.history'].search([('star_date', '>=', self.date_prima), ('end_date', '<=', self.date_liquidacion),('employee_id', '=', self.employee_id.id),('leave_type_id.unpaid_absences', '=', True)])])
                    dias_liquidacion = dias_trabajados - dias_ausencias

                    if rule.restart_one_month_prima:
                        dias_acumulados_promedio = self.dias360(self.date_from, self.date_to + relativedelta(months=-1))
                        if dias_acumulados_promedio <= 0:
                            dias_acumulados_promedio = dias_trabajados
                    else:
                        dias_acumulados_promedio = dias_trabajados
                    if dias_acumulados_promedio != 0:
                        acumulados_promedio = (amount/dias_acumulados_promedio) * 30 # dias_liquidacion
                    else:
                        acumulados_promedio = 0
                    wage,auxtransporte,auxtransporte_tope = 0,0,0
                    if contract.subcontract_type not in ('obra_parcial', 'obra_integral'):
                        wage = 0
                        obj_wage = self.env['hr.contract.change.wage'].search([('contract_id', '=', contract.id), ('date_start', '<', self.date_to)])
                        for change in sorted(obj_wage, key=lambda x: x.date_start):  # Obtiene el ultimo salario vigente antes de la fecha de liquidacion
                            wage = change.wage
                        wage = contract.wage if wage == 0 else wage
                        initial_process_date = self.date_prima if inherit_contrato != 0 else self.date_from
                        end_process_date = self.date_liquidacion if inherit_contrato != 0 else self.date_to
                        obj_wage = self.env['hr.contract.change.wage'].search([('contract_id', '=', contract.id), ('date_start', '>=', initial_process_date), ('date_start', '<=', end_process_date)])
                        if prima_salary_take and len(obj_wage) > 0:
                            wage_average = 0
                            while initial_process_date <= end_process_date:
                                if initial_process_date.day != 31:
                                    if initial_process_date.month == 2 and  initial_process_date.day == 28 and (initial_process_date + timedelta(days=1)).day != 29:
                                        wage_average += (contract.get_wage_in_date(initial_process_date) / 30)*3
                                    elif initial_process_date.month == 2 and initial_process_date.day == 29:
                                        wage_average += (contract.get_wage_in_date(initial_process_date) / 30)*2
                                    else:
                                        wage_average += contract.get_wage_in_date(initial_process_date)/30
                                initial_process_date = initial_process_date + timedelta(days=1)
                            if dias_trabajados != 0:
                                wage = contract.wage if wage_average == 0 else (wage_average/dias_trabajados)*30
                            else:
                                wage = 0
                        auxtransporte = annual_parameters.transportation_assistance_monthly
                        auxtransporte_tope = annual_parameters.top_max_transportation_assistance
                    value_rules_base_auxtransporte_tope = localdict['payslip'].get_accumulated_prima(self.date_from,self.date_to,1)
                    if inherit_contrato != 0:
                        value_rules_base_auxtransporte_tope = localdict['payslip'].get_accumulated_prima(self.date_prima,self.date_liquidacion,1)
                    if dias_acumulados_promedio != 0:
                        value_rules_base_auxtransporte_tope = (value_rules_base_auxtransporte_tope/dias_acumulados_promedio) * 30 # dias_liquidacion
                    else:
                        auxtransporte = 0.0
                        amount_base =  wage + acumulados_promedio

                    #amount = round(amount_base * dias_liquidacion / 360, 0)
                    amount =  amount_base / 360
                    qty = dias_liquidacion

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
                        'days_unpaid_absences':dias_ausencias,
                        'slip_id': self.id,
                    }
                if rule.code == 'PRIMA':
                    for record in self:
                        log_content = ""
                        log = [
                            ('PRIMA', ''),
                            ('DATOS', 'VALORES'),
                            ('FECHA DESDE', record.date_prima),
                            ('FECHA HASTA', record.date_to),
                            ('DIAS LABORADOS', dias_trabajados),
                            ('DIAS DE SUSPENSION', dias_ausencias),
                            ('CAMBIO DE SALARIO', wage_average),
                            ('TOTAL AUXILIO TRANSPORTE', auxtransporte),
                            ('TOTAL SALARIO', wage),
                            ('TOTAL VARIABLE', acumulados_promedio),
                            ('BASE', amount_base),
                            ('NETO PRIMA A LA FECHA', qty*amount)
                        ]
                        style_classes = {
                            'TOTAL SALARIO': 'font-weight: bold;',
                            'DATOS': 'font-weight: bold;',
                            'TOTAL VARIABLE': 'font-weight: bold;',
                            'BASE': 'font-weight: bold;',
                            'NETO PRIMA A LA FECHA': 'background-color: lightblue; border: 1px solid black; display: inline-block; padding: 2px; border-radius: 5px; font-weight: bold;',
                            }
                        label_style_classes = {
                            'NETO PRIMA A LA FECHA': 'font-weight: bold;',
                            'DATOS': 'font-weight: bold;',
                        }
                        log_content += '<table style="border-collapse: collapse; width: 100%;">'
                        for item in log:
                            label_style = label_style_classes.get(item[0], "")
                            value_style = style_classes.get(item[0], "")
                            style = style_classes.get(item[0], "")
                            value = item[1]
                            # Convertir fechas a string
                            if isinstance(value, date):
                                value = value.strftime('%Y-%m-%d')
                            # Dar formato de moneda a los números, excluyendo valores que contienen la palabra "DIA"
                            elif isinstance(value, (int, float)) and "DIA" not in item[0]:
                                value = '$ {:,.2f}'.format(value)
                            
                            log_content += f'''<tr>
                                <td style="width: 50%; text-align: right; padding-right: 10px; {label_style}">{item[0]}:</td>
                                <td style="{value_style}">{value}</td>
                            </tr>'''
                        log_content += '</table>'
                    self.resulados_op = log_content 


        # Ejecutar reglas salariales de la nómina de pago regular
        if inherit_contrato == 0:
            obj_struct_payroll = self.env['hr.payroll.structure'].search(
                [('regular_pay', '=', True), ('process', '=', 'nomina')])
            struct_original = self.struct_id.id
            self.struct_id = obj_struct_payroll.id
            result_payroll = self._get_payslip_lines(inherit_prima=1, localdict=localdict)
            self.struct_id = struct_original

            result_finally = {**result, **result_payroll}
            # Retornar resultado final de la liquidación de nómina
            return result_finally.values()
        else:
            return localdict, result
