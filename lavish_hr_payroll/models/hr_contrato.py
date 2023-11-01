# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from .browsable_object import BrowsableObject, InputLine, WorkedDays, Payslips
from odoo.tools import float_compare, float_is_zero

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import logging
_logger = logging.getLogger(__name__)

class Hr_payslip(models.Model):
    _inherit = 'hr.payslip'

    reason_retiro = fields.Many2one('hr.departure.reason', string='Motivo de retiro')
    have_compensation = fields.Boolean('Indemnización', default=False)
    settle_payroll_concepts = fields.Boolean('Liquida conceptos de nómina', default=True)
    novelties_payroll_concepts = fields.Boolean('Liquida conceptos de novedades', default=True)

    @api.onchange('employee_id','contract_id','struct_id','date_to')
    def load_dates_liq_contrato(self):
        if self.struct_id.process == 'contrato':
            self.date_liquidacion = self.date_to
            #Obtener fecha prima
            date_prima = self.contract_id.date_start     
            obj_prima = self.env['hr.history.prima'].search([('employee_id', '=', self.employee_id.id),('contract_id', '=', self.contract_id.id)])
            if obj_prima:
                for history in sorted(obj_prima, key=lambda x: x.final_accrual_date):
                    date_prima = history.final_accrual_date + timedelta(days=1) if history.final_accrual_date > date_prima else date_prima             
            self.date_prima = date_prima
            #Obtener fecha vacaciones
            date_vacation = self.contract_id.date_start     
            obj_vacation = self.env['hr.vacation'].search([('employee_id', '=', self.employee_id.id),('contract_id', '=', self.contract_id.id)])
            if obj_vacation:
                for history in sorted(obj_vacation, key=lambda x: x.final_accrual_date):
                    if history.leave_id:
                        if history.leave_id.holiday_status_id.unpaid_absences == False:
                            date_vacation = history.final_accrual_date + timedelta(days=1) if history.final_accrual_date > date_vacation else date_vacation
                    else:
                        date_vacation = history.final_accrual_date + timedelta(days=1) if history.final_accrual_date > date_vacation else date_vacation
            self.date_vacaciones = date_vacation
            #Obtener fecha cesantias
            date_cesantias = self.contract_id.date_start     
            obj_cesantias = self.env['hr.history.cesantias'].search([('employee_id', '=', self.employee_id.id),('contract_id', '=', self.contract_id.id)])
            if obj_cesantias:
                for history in sorted(obj_cesantias, key=lambda x: x.final_accrual_date):
                    date_cesantias = history.final_accrual_date + timedelta(days=1) if history.final_accrual_date > date_cesantias else date_cesantias             
            self.date_cesantias = date_cesantias


    #--------------------------------------------------LIQUIDACIÓN DE CONTRATO---------------------------------------------------------#

    def _get_payslip_lines_contrato(self):
        def _sum_salary_rule_category(localdict, category, amount):
            if category.parent_id:
                localdict = _sum_salary_rule_category(localdict, category.parent_id, amount)
            localdict['categories'].dict[category.code] = localdict['categories'].dict.get(category.code, 0) + amount
            return localdict

        def _sum_salary_rule(localdict, rule, amount):
            localdict['rules_computed'].dict[rule.code] = localdict['rules_computed'].dict.get(rule.code, 0) + amount
            return localdict

        employee = self.employee_id
        contract = self.contract_id
        result_finally = {}
        struct_original = self.struct_id.id

        # 1.Devengos
        obj_struct_payroll = self.env['hr.payroll.structure'].search([('regular_pay','=',True),('process','=','nomina')])        
        self.struct_id = obj_struct_payroll.id
        localdict, result_dev = self._get_payslip_lines(inherit_contrato_dev=1)

        # 2.Reglas salariales por Liq. de Contrato - Ej: Indemnizaciones
        result_contrato = {}
        rules_dict = {}
        self.struct_id = struct_original
        for rule in sorted(self.struct_id.rule_ids, key=lambda x: x.sequence):
            localdict.update({                
                'result': None,
                'result_qty': 1.0,
                'result_rate': 100})
            if rule._satisfy_condition(localdict):                
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
                # create/overwrite the rule in the temporary results
                if amount != 0:                    
                    result_contrato[rule.code] = {
                        'sequence': rule.sequence,
                        'code': rule.code,
                        'name': rule.name,
                        'note': rule.note,
                        'salary_rule_id': rule.id,
                        'contract_id': contract.id,
                        'employee_id': employee.id,                        
                        'amount': amount,
                        'quantity': qty,
                        'rate': rate,
                        'slip_id': self.id,
                    }

        # 3.Deducciones que son base para prestaciones
        obj_struct_payroll = self.env['hr.payroll.structure'].search([('process', '=', 'nomina')])
        self.struct_id = obj_struct_payroll.id
        localdict, result_ded_bases = self._get_payslip_lines(inherit_contrato_ded_bases=1, localdict=localdict)

        if contract.contract_type != 'aprendizaje':
            # 3.Vacaciones
            obj_struct_payroll = self.env['hr.payroll.structure'].search([('process','=','vacaciones')])
            self.struct_id = obj_struct_payroll.id
            localdict, result_vac = self._get_payslip_lines_vacation(inherit_contrato=1,localdict=localdict)
            if contract.modality_salary != 'integral':
                # 4.Cesantias e intereses
                obj_struct_payroll = self.env['hr.payroll.structure'].search([('process','=','cesantias')])
                self.struct_id = obj_struct_payroll.id
                localdict, result_cesantias = self._get_payslip_lines_cesantias(inherit_contrato=1,localdict=localdict)
                obj_struct_payroll = self.env['hr.payroll.structure'].search([('process', '=', 'intereses_cesantias')])
                self.struct_id = obj_struct_payroll.id
                localdict, result_intcesantias = self._get_payslip_lines_cesantias(inherit_contrato=1, localdict=localdict)

                # 5.Prima
                obj_struct_payroll = self.env['hr.payroll.structure'].search([('process','=','prima')])
                self.struct_id = obj_struct_payroll.id
                localdict, result_prima = self._get_payslip_lines_prima(inherit_contrato=1,localdict=localdict)
            else:
                result_cesantias = {}
                result_intcesantias = {}
                result_prima = {}
        else:
            result_vac = {}
            result_cesantias = {}
            result_intcesantias = {}
            result_prima = {}
        # 6.Deducciones
        obj_struct_payroll = self.env['hr.payroll.structure'].search([('regular_pay','=',True),('process','=','nomina')])        
        self.struct_id = obj_struct_payroll.id
        localdict, result_ded = self._get_payslip_lines(inherit_contrato_ded=1,localdict=localdict)

        # 7.Guardar proceso
        self.struct_id = struct_original
        result_finally = {**result_dev,**result_contrato,**result_ded_bases,**result_vac,**result_cesantias,**result_intcesantias,**result_prima,**result_ded}
        return result_finally.values()  