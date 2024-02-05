
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime, timedelta, date
from odoo.exceptions import UserError, ValidationError
from calendar import monthrange
import time

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)

class HrContractRtfLog(models.Model):
    _name = 'hr.contract.rtf.log'

    name = fields.Char('Descripcion')
    value = fields.Char('Detalle')
    contract_id = fields.Many2one('hr.contract', 'Contrato')

class hr_contract(models.Model):
    _inherit = 'hr.contract'

    prima_ids = fields.One2many('hr.history.prima', 'contract_id', string="Historico de prima", readonly=True)
    cesantia_ids = fields.One2many('hr.history.cesantias', 'contract_id', string="Historico de cesantías", readonly=True)
    vacaciones_ids = fields.One2many('hr.vacation', 'contract_id', string="Historico de vacaciones", readonly=True)
    contract_days = fields.Integer(string='Días de Contrato')
    rtf_log = fields.One2many('hr.contract.rtf.log', 'contract_id', string="Calculo tarifa RTFP2")
    rtf_rate = fields.Float(string='Porcentaje de retencion', digits='Payroll', default=1.0)
    ded_dependents = fields.Boolean('Dependiente', tracking=True)
    pr_rtf = fields.Boolean('Primer Calculo', tracking=True)
    def days_between(self,start_date,end_date):
        s1, e1 =  start_date , end_date + timedelta(days=1)
        #Convert to 360 days
        s360 = (s1.year * 12 + s1.month) * 30 + s1.day
        e360 = (e1.year * 12 + e1.month) * 30 + e1.day
        #Count days between the two 360 dates and return tuple (months, days)
        res = divmod(e360 - s360, 30)
        return ((res[0] * 30) + res[1]) or 0
    @api.onchange('date_end', 'contract_days', 'date_start')
    def _compute_contract_days(self):

        def monthdelta(d1, d2):
            delta = 0
            while True:
                mdays = monthrange(d1.year, d1.month)[1]
                d1 += timedelta(days=mdays)
                if d1 <= d2:
                    delta += 1
                else:
                    break
            return delta

        if 'field_onchange' in self.env.context and self.env.context['field_onchange'] == 'contract_days':
            if self.contract_days > 0:
                months = int(self.contract_days / 30)
                days = self.contract_days - (30 * months)
                start = fields.Date.from_string(self.date_start)
                date_end = start + relativedelta(months=months) + relativedelta(days=days)
                self.date_end = fields.Date.to_string(date_end)
            else:
                self.date_end = False

        elif 'field_onchange' in self.env.context and self.env.context['field_onchange'] == 'date_start':
            self.date_end, self.contract_days = False, False

        else:
            if self.date_end:
                month = monthdelta(fields.Date.from_string(self.date_start),
                                   fields.Date.from_string(self.date_end))
                end = int(self.date_end.day)
                start = int(self.date_start.day)
                if start > end:
                    days = (30 - int(start) + int(end))
                else:
                    days = int(end) - int(start)
                self.contract_days = 0
                self.contract_days = month * 30 + days
            else:
                self.contract_days = 0
    def get_calcula_rtefte_ordinaria(self, base_rtefte_uvt):
        res_initial = self.env['hr.calculation.rtefte.ordinary'].search([('range_initial', '<=', base_rtefte_uvt)])
        max_value = 0
        for i in res_initial:
            if i.range_finally > max_value:
                max_value = i.range_finally                
        res = self.env['hr.calculation.rtefte.ordinary'].search([('range_initial', '<=', base_rtefte_uvt),('range_finally', '=', max_value)])
        return res and res[0] or 0.0
    def get_contract_deductions_rtf(self, contract_id,code):
        #,('date_start', '>=', to_date),('date_end', '<=', to_date)
        res = self.env['hr.contract.deductions.rtf'].search([('contract_id', '=', contract_id),('input_id.code','=',code)])
        return res and res[0] or 0.0
    def compute_rtf2(self):
        hp = self.env['hr.payslip']
        hpl = self.env['hr.payslip.line']
        hpa = self.env['hr.accumulated.payroll']
        log_data = []
        for k in self:
            log = []
            # Definir fechas
            date = datetime.now().date() 
            seg = 1 if date.month < 6 or date.month == 12 else 2
            if seg == 1:
                year = date.year - 1 if date.month == 12 else date.year - 2
                ref_date_from = str(year) + '-12-01'
                ref_date_from = datetime.strptime(ref_date_from, '%Y-%m-%d').date()
                if k.date_start > ref_date_from:
                    ref_date_from = k.date_start
                ref_date_to = str(year + 1) + '-11-30'
                ref_date_to = datetime.strptime(ref_date_to, '%Y-%m-%d').date()
            else:
                year = date.year - 1
                ref_date_from = str(year) + '-06-01'
                ref_date_from = datetime.strptime(ref_date_from, '%Y-%m-%d').date()
                if k.date_start > ref_date_from:
                    ref_date_from = k.date_start
                ref_date_to = str(year + 1) + '-05-31'
                ref_date_to = datetime.strptime(ref_date_to, '%Y-%m-%d').date()
            payslip_count = hp.search_count([
                ('date_to', '>=', ref_date_from),
                ('date_to', '<=', ref_date_to),
                ('contract_id', '=', k.id)
            ])
            def format_currency(amount):
                return "${:,.2f}".format(amount).replace(',', 'X').replace('.', ',').replace('X', '.')

            self.env.cr.execute("DELETE FROM hr_contract_rtf_log where contract_id = %s", (k.id,))
            _logger.info(payslip_count < 6)
            if payslip_count > 6:
                log += [('FECHA INICIO', ref_date_from)]
                log += [('FECHA FIN', ref_date_to)]

                uvt = self.env['hr.annual.parameters'].search([('year', '=', ref_date_to.year)]).value_uvt
                log += [('VALOR UVT', format_currency(uvt))]

                days = k.days_between(ref_date_from, ref_date_to)
                log += [('DIAS INTERVALO', days)]
                payslip_ids = hpl.search([
                    ('slip_id.state', 'in', ['done', 'paid']),
                    ('slip_id.contract_id', '=', k.id),
                    ('slip_id.date_to', '>', ref_date_from),
                    ('slip_id.date_from', '<', ref_date_to),
                ])
                o_earn = 0.0
                earn = 0.0
                earn = sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.category_id.code == 'BASIC')])
                o_earn = sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.code == 'COMISIONES')])
                o_sal = sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.category_id.code == 'DEV_SALARIAL' or m.salary_rule_id.category_id.parent_id.code == 'DEV_SALARIAL' and not m.salary_rule_id.category_id.code == 'BASIC')]) - o_earn
                comp = sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.category_id.code == 'COMPLEMENTARIOS')])
                nt_earn = sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.category_id.code == 'DEV_NO_SALARIAL' or m.salary_rule_id.category_id.parent_id.code == 'DEV_NO_SALARIAL' and not  m.salary_rule_id.code == 'AUX000')])


                log += [('1.SALARIO', format_currency(earn))]
                log += [('2.COMISIONES', format_currency(o_earn))]
                log += [('3.OTROS INGRESOS SALARIALES', format_currency(o_sal))]
                log += [('4.INGRESOS COMPLEMENTARIOS', format_currency(comp))]
                log += [('5.INGRESOS NO SALARIALES', format_currency(nt_earn))]

                taxed_inc = earn + o_earn + o_sal + comp + nt_earn
                log += [('6.INGRESOS TOTALES [1+2+3+4+5]', format_currency(taxed_inc))]


                untaxed_inc = 0  # Ingresos no gravados
                ing_no_const = 0  # Ingresos no constitutivos de renta
                vol_cont = 0  # Aportes voluntarios de pension y afc
                ap_vol = 0
                afc = 0
                log += [('NOMINAS EN PERIODO', payslip_count)]
                ss01 = sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.code == 'SSOCIAL001')])
                ss02 = sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.code in ('SSOCIAL002','SSOCIAL003','SSOCIAL004'))])
                ing_no_const = ss01 +ss02
                afc = sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.code == 'AFC')])
                earn = sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.category_id.code == 'BASIC')])

                log += [('7.APT Salud Empleado - 12 meses anteriores. (Tope max 25 SMMLV)', format_currency(ss01))]
                log += [('8.APT PENSION Empleado - 12 meses anteriores. (Tope max 25 SMMLV)', format_currency(ss02))]
                log += [('9.INGRESOS NO CONSTITUTIVOS DE RENTA', format_currency(ing_no_const))]
                #log += [('10.APORTES VOLUNTARIOS PENSION', ap_vol if ap_vol < 2500 * uvt else 2500*uvt)]
                log += [('11.AFC', format_currency(afc))]

                net_income = taxed_inc + ing_no_const
                log += [('12.INGRESOS NETOS [7-9]', format_currency(net_income))]

                dep_base = taxed_inc * 0.1
                if k.ded_dependents:
                    ded_depend = dep_base if dep_base <= 72 * uvt else 72 * uvt
                else:
                    ded_depend = 0
                log += [('13.DEDUCCION DEPENDIENTES', format_currency(ded_depend))]

                #Medicina prepagada
                base_mp = self.get_contract_deductions_rtf(k.id,'MEDPRE').value_monthly
                ded_mp = base_mp if base_mp <= 192 * uvt else 192 * uvt

                log += [('14.DEDUCCION MEDICINA PREPAGADA', format_currency(ded_mp))]

                # Deducion por vivienda
                base_liv = self.get_contract_deductions_rtf(k.id,'INTVIV').value_monthly
                ded_liv = base_liv if base_liv <= 1200 * uvt else 1200 * uvt
                log += [('15.DEDUCCION POR INT DE VIVIENDA', format_currency(ded_liv) )]

                total_deduct = ded_depend + ded_mp + ded_liv
                log += [('16.TOTAL DEDUCIBLES [13+14+15]', format_currency(total_deduct))]

                #     # Aportes voluntarios
                #     vol_cont = vol_cont if vol_cont <= net_income * 0.3 else net_income * 0.3
                #     log += [('17.TOTAL DEDUCIBLES VOLUNTARIOS', vol_cont)]

                # Top25 deducible por ley de los ingresos - deducciones existentes
                base25 = (net_income - total_deduct - vol_cont) * 0.25
                top25 = base25 if base25 <= 2880 * uvt else 2880 * uvt
                log += [('18.TOP 25% [(12-16-17)*25% o 2880 UVT]', format_currency(top25))]

                # Top40
                base40 = net_income * 0.4
                baserex = total_deduct + vol_cont + top25
                rent_ex = baserex if baserex <= base40 else base40
                log += [('19.RENTA EXENTA [16+17+18 o 12x40%]', format_currency(rent_ex))]

                brtf = net_income - rent_ex
                log += [('20.BASE RETENCION GLOBAL [12-19]', format_currency(brtf))]
                if days == 360:
                    factor = 13
                else:
                    factor = days / 30
                log += [('21.FACTOR MES [13:360, days/30]', format_currency(factor))]

                brtf_month = brtf / factor if factor else 0
                log += [('22.BASE RTF MES [20/21]', format_currency(brtf_month))]

                b_uvt = brtf_month / uvt if uvt else 0
                log += [('23.BASE UVT [22/UVT]', float(b_uvt))]

                rate =  k.get_calcula_rtefte_ordinaria(b_uvt)
                porc = rate.porc / 100
                conv = ((b_uvt - rate.subtract_uvt) * porc) + rate.addition_uvt
                log += [('24.UVT APLICACION TABLA', format_currency(conv))]
                rtf = conv * uvt
                log += [('25.RETENCION APLICACION [24xUVT]', format_currency(rtf))]
                if b_uvt and uvt:
                    rate_p2 = rtf * 100 / b_uvt / uvt
                else:
                    rate_p2 = 0
                k.rtf_rate = rate_p2
                log += [('26.PORCENTAJE CALCULADO [25/23/UVT]', float(rate_p2))]
            if payslip_count < 6:
                log += [('FECHA INICIO', ref_date_from)]
                log += [('FECHA FIN', ref_date_to)]

                uvt = self.env['hr.annual.parameters'].search([('year', '=', ref_date_to.year)]).value_uvt
                log += [('VALOR UVT', format_currency(uvt))]

                days = k.days_between(ref_date_from, ref_date_to)
                log += [('DIAS INTERVALO', days)]
                payslip_ids = hpl.search([
                    ('slip_id.state', 'in', ['done', 'paid']),
                    ('slip_id.contract_id', '=', k.id),
                    ('slip_id.date_to', '>', ref_date_from),
                    ('slip_id.date_from', '<', ref_date_to),
                ])
                o_earn = 0.0
                earn = 0.0
                earn = k.wage * 12 #sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.category_id.code == 'BASIC')])
                o_earn = sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.code == 'COMISIONES')])
                o_sal = sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.category_id.code == 'DEV_SALARIAL' or m.salary_rule_id.category_id.parent_id.code == 'DEV_SALARIAL' and not m.salary_rule_id.category_id.code == 'BASIC')]) - o_earn
                comp = sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.category_id.code == 'COMPLEMENTARIOS')])
                nt_earn = sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.category_id.code == 'DEV_NO_SALARIAL' or m.salary_rule_id.category_id.parent_id.code == 'DEV_NO_SALARIAL' and not  m.salary_rule_id.code == 'AUX000')])


                log += [('1.SALARIO', format_currency(earn))]
                log += [('2.COMISIONES', format_currency(o_earn))]
                log += [('3.OTROS INGRESOS SALARIALES', format_currency(o_sal))]
                log += [('4.INGRESOS COMPLEMENTARIOS', format_currency(comp))]
                log += [('5.INGRESOS NO SALARIALES', format_currency(nt_earn))]

                taxed_inc = earn + o_earn + o_sal + comp + nt_earn
                log += [('6.INGRESOS TOTALES [1+2+3+4+5]', format_currency(taxed_inc))]


                untaxed_inc = 0  # Ingresos no gravados
                ing_no_const = 0  # Ingresos no constitutivos de renta
                vol_cont = 0  # Aportes voluntarios de pension y afc
                ap_vol = 0
                afc = 0
                log += [('NOMINAS EN PERIODO', payslip_count)]
                ss01 = sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.code == 'SSOCIAL001')])
                ss02 = sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.code in ('SSOCIAL002','SSOCIAL003','SSOCIAL004'))])
                ing_no_const = ss01 +ss02
                afc = sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.code == 'AFC')])
                earn = sum([x.total for x in payslip_ids.filtered(lambda m: m.salary_rule_id.category_id.code == 'BASIC')])

                log += [('7.APT Salud Empleado - 12 meses anteriores. (Tope max 25 SMMLV)', format_currency(ss01))]
                log += [('8.APT PENSION Empleado - 12 meses anteriores. (Tope max 25 SMMLV)', format_currency(ss02))]
                log += [('9.INGRESOS NO CONSTITUTIVOS DE RENTA', format_currency(ing_no_const))]
                #log += [('10.APORTES VOLUNTARIOS PENSION', ap_vol if ap_vol < 2500 * uvt else 2500*uvt)]
                log += [('11.AFC', format_currency(afc))]

                net_income = taxed_inc + ing_no_const
                log += [('12.INGRESOS NETOS [7-9]', format_currency(net_income))]

                dep_base = taxed_inc * 0.1
                if k.ded_dependents:
                    ded_depend = dep_base if dep_base <= 72 * uvt else 72 * uvt
                else:
                    ded_depend = 0
                log += [('13.DEDUCCION DEPENDIENTES', format_currency(ded_depend))]

                #Medicina prepagada
                base_mp = self.get_contract_deductions_rtf(k.id,'MEDPRE').value_monthly
                ded_mp = base_mp if base_mp <= 192 * uvt else 192 * uvt

                log += [('14.DEDUCCION MEDICINA PREPAGADA', format_currency(ded_mp))]

                # Deducion por vivienda
                base_liv = self.get_contract_deductions_rtf(k.id,'INTVIV').value_monthly
                ded_liv = base_liv if base_liv <= 1200 * uvt else 1200 * uvt
                log += [('15.DEDUCCION POR INT DE VIVIENDA', format_currency(ded_liv) )]

                total_deduct = ded_depend + ded_mp + ded_liv
                log += [('16.TOTAL DEDUCIBLES [13+14+15]', format_currency(total_deduct))]

            #     # Aportes voluntarios
            #     vol_cont = vol_cont if vol_cont <= net_income * 0.3 else net_income * 0.3
            #     log += [('17.TOTAL DEDUCIBLES VOLUNTARIOS', vol_cont)]

                # Top25 deducible por ley de los ingresos - deducciones existentes
                base25 = (net_income - total_deduct - vol_cont) * 0.25
                top25 = base25 if base25 <= 2880 * uvt else 2880 * uvt
                log += [('18.TOP 25% [(12-16-17)*25% o 2880 UVT]', format_currency(top25))]

                # Top40
                base40 = net_income * 0.4
                baserex = total_deduct + vol_cont + top25
                rent_ex = baserex if baserex <= base40 else base40
                log += [('19.RENTA EXENTA [16+17+18 o 12x40%]', format_currency(rent_ex))]

                brtf = net_income - rent_ex
                log += [('20.BASE RETENCION GLOBAL [12-19]', format_currency(brtf))]
                if days == 360:
                    factor = 13
                else:
                    factor = days / 30
                log += [('21.FACTOR MES [13:360, days/30]', format_currency(factor))]

                brtf_month = brtf / factor if factor else 0
                log += [('22.BASE RTF MES [20/21]', format_currency(brtf_month))]

                b_uvt = brtf_month / uvt if uvt else 0
                log += [('23.BASE UVT [22/UVT]', float(b_uvt))]

                rate =  k.get_calcula_rtefte_ordinaria(b_uvt)
                porc = rate.porc / 100
                conv = ((b_uvt - rate.subtract_uvt) * porc) + rate.addition_uvt
                log += [('24.UVT APLICACION TABLA', format_currency(conv))]
                rtf = conv * uvt
                log += [('25.RETENCION APLICACION [24xUVT]', format_currency(rtf))]
                if b_uvt and uvt:
                    rate_p2 = rtf * 100 / b_uvt / uvt
                else:
                    rate_p2 = 0
                k.rtf_rate = rate_p2
                log += [('26.PORCENTAJE CALCULADO [25/23/UVT]', float(rate_p2))]
            for line in log:
                log_data.append({
                    'name': line[0],
                    'value': line[1],
                    'contract_id': k.id
                })
        self.env['hr.contract.rtf.log'].sudo().create(log_data)
        return

    def create_payslip_reliquidation(self):
        """
        Funcion de reliquidar contratos
        """
        payslip_type_liq = self.env['hr.payroll.structure'].search([('process','=','contrato')])
        
        if not payslip_type_liq:
            raise UserError('Debe configurar en los tipos de nomina, un tipo con el codigo <Liquidacion>')
        elif len(payslip_type_liq) > 1:
            raise UserError('Se encontraron {N} tipos de nomina con el codigo <Liquidacion>'.format(N=len(payslip_type_liq)))
        
        new_payslip_ids = []
        for contract in self:
            payslips_ids = self.env['hr.payslip'].search([('contract_id','=',contract.id),('tipo_nomina','=',payslip_type_liq.id)])
            no_done_payslips = [p for p in payslips_ids if p.state != 'done']

            if not payslips_ids:
                raise UserError('Debe crear primero una nomina de tipo <Liquidacion> para el contrato {C}'.format(C=contract.name))
            elif no_done_payslips:
                raise UserError('Este proceso se debe hacer unicamente para ajustar la nomina de tipo <Liquidacion> que ya esta causada. Se encontraron las nominas {N} de tipo <Liquidacion> en estado {E}'.format(N=[p.number for p in no_done_payslips], E=[p.state for p in no_done_payslips]))
            

            if not (contract.employee_id and payslips_ids.journal_id):
                message = 'Del contrato {C} la siguiente informacion es errónea\n'.format(C=contract.name)
                message += '    -Empleado = {E}\n'.format(E=contract.employee_id.name if contract.employee_id else False)
                message += '    -Diario de Salarios = {L}\n'.format(L=contract.journal_id.name if contract.journal_id else False)
                raise UserError(message)
            
            notes = 'Reliquidacion de {E}\n'.format(E=contract.employee_id.name)
            notes += 'Inicio de contrato = {F}\n'.format(F=contract.date_start)
            notes += 'Fin de contrato = {F}\n'.format(F=contract.date_end)
            notes += 'Dias de contrato = {D}\n'.format(D=contract.contract_days)
            
            new_payslip = {
                'employee_id': contract.employee_id.id,
                'payslip_period_id': contract.payslip_period_id.id,
                'contract_id': contract.id,
                'name': '',
                'note': notes,
                'contract_create': True,
                'liquidacion_date': contract.payslip_period_id.end_date,
                'journal_id': contract.journal_id.id,
                'tipo_nomina': payslip_type_liq.id,
            }
            new_payslip_id = self.env['hr.payslip'].create(new_payslip)
            new_payslip_id.compute_sheet()            
            new_payslip_ids.append(new_payslip_id.id)
        
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'hr.payslip',
            'target': 'current',
            'context': {},
            'domain': [('id','in',new_payslip_ids)],
        }
    #Libro de vacaciones
    def get_info_book_vacation(self):
        return self.env['hr.vacation'].search([('contract_id','=',self.id)])

    def get_accumulated_vacation_days(self,ignore_payslip_id=0,method_old=0):
        date_start = self.date_start
        date_end = self.retirement_date if self.retirement_date else datetime.now().date()
        employee_id = self.employee_id.id
        if method_old != 0:
            #------------------ CALCULO ANTIGUO------------------------------------
            #Días de servicio
            days_service = self.dias360(date_start, date_end)
            #Ausencias no remuneradas
            days_unpaid_absences = sum([i.number_of_days for i in self.env['hr.leave'].search(
                [('date_from', '>=', date_start), ('date_to', '<=', date_end),
                 ('state', '=', 'validate'), ('employee_id', '=', employee_id),
                 ('unpaid_absences', '=', True)])])
            days_unpaid_absences += sum([i.days for i in self.env['hr.absence.history'].search(
                [('star_date', '>=', date_start), ('end_date', '<=', date_end),
                 ('employee_id', '=', employee_id), ('leave_type_id.unpaid_absences', '=', True)])])
            #Días a disfrutar
            days_vacations_total = ((days_service - days_unpaid_absences) * 15) / 360
            #Días ya pagados
            if ignore_payslip_id == 0:
                days_paid = sum([i.business_units+i.units_of_money for i in self.env['hr.vacation'].search([('contract_id', '=', self.id)])])
            else:
                days_paid = sum([i.business_units + i.units_of_money for i in
                                 self.env['hr.vacation'].search([('contract_id', '=', self.id),('payslip','!=',ignore_payslip_id)])])
            #Dias faltantes por disfrutar
            days_vacations = round(days_vacations_total - days_paid,2)
        else:
            # ------------------ NUEVO CALCULO------------------------------------
            date_vacation = date_start
            if ignore_payslip_id == 0:
                obj_vacation = self.env['hr.vacation'].search([('employee_id', '=', employee_id), ('contract_id', '=', self.id)])
            else:
                obj_vacation = self.env['hr.vacation'].search([('employee_id', '=', employee_id), ('contract_id', '=', self.id),('payslip','!=',ignore_payslip_id)])
            if obj_vacation:
                for history in sorted(obj_vacation, key=lambda x: x.final_accrual_date):
                    if history.leave_id:
                        if history.leave_id.holiday_status_id.unpaid_absences == False:
                            date_vacation = history.final_accrual_date + timedelta(days=1) if history.final_accrual_date > date_vacation else date_vacation
                    else:
                        date_vacation = history.final_accrual_date + timedelta(days=1) if history.final_accrual_date > date_vacation else date_vacation

            dias_trabajados = self.dias360(date_vacation, date_end)
            dias_ausencias = sum([i.number_of_days for i in self.env['hr.leave'].search(
                [('date_from', '>=', date_vacation), ('date_to', '<=', date_end),
                 ('state', '=', 'validate'), ('employee_id', '=', employee_id),
                 ('unpaid_absences', '=', True)])])
            dias_ausencias += sum([i.days for i in self.env['hr.absence.history'].search(
                [('star_date', '>=', date_vacation), ('end_date', '<=', date_end),
                 ('employee_id', '=', employee_id), ('leave_type_id.unpaid_absences', '=', True)])])
            days_vacations = ((dias_trabajados - dias_ausencias) * 15) / 360
        return days_vacations

    #Libro de cesantias
    def get_info_book_cesantias(self):
        return self.env['hr.history.cesantias'].search([('contract_id','=',self.id)])
    #Verificar historico de salario
    
    def get_wage_in_date(self,process_date):
        wage_in_date = self.wage
        for change in sorted(self.change_wage_ids, key=lambda x: x.date_start):
            if process_date >= change.date_start:
                wage_in_date = change.wage
        return wage_in_date


#---------------------- IBC ------------------------>

    def GetIBCSLastMonth(self, date_to, contract_id):
        # Calculate the start and end date of the previous month
        date_actual = date_to
        month = date_to.month - 1
        year = date_to.year
        if month == 0:
            month = 12
            year -= 1
        day = 30 if month != 2 else 28
        from_date = datetime(year, month, 1).date()
        to_date = datetime(year, month, day).date()
        annual_parameters = self.env['hr.annual.parameters'].search([('year', '=', date_actual.year)])
        # Find payslip lines for the given code and date range
        PayslipLine = self.env['hr.payslip.line']
        payslip_lines = PayslipLine.search([
            ('slip_id.state', 'in', ['done', 'paid']),
            ('slip_id.contract_id', '=', contract_id.id),
            ('slip_id.date_to', '>', from_date),
            ('slip_id.date_from', '<', to_date),
            #('salary_rule_id.code', '=', code)
        ])
        value_base = 0
        base_40 = 0
        value_base_no_dev = 0
        # Calculate the IBC by summing up the totals of matching payslip lines
        for line in payslip_lines:
            value_base += abs(line.total) if line.salary_rule_id.category_id.code == 'DEV_SALARIAL' or line.salary_rule_id.category_id.parent_id.code == 'DEV_SALARIAL' else 0
            value_base_no_dev += abs(line.total) if line.salary_rule_id.category_id.code == 'DEV_NO_SALARIAL' or line.salary_rule_id.category_id.parent_id.code == 'DEV_NO_SALARIAL' else 0
        gran_total = value_base + value_base_no_dev 
        statute_value = gran_total*(annual_parameters.value_porc_statute_1395/100)
        total_statute = value_base_no_dev-statute_value 
        if total_statute > 0: 
            base_40 = total_statute     
        ibc = value_base + base_40
        # If IBC is not zero, return it
        if ibc:
            return ibc
        # Check for custom IBC (u_ibc) on the contract, if it matches the IBC date
        if contract_id.fecha_ibc and from_date.year == contract_id.fecha_ibc.year and from_date.month == contract_id.fecha_ibc.month:
            return contract_id.u_ibc
        # If no IBC is found, return the contract's wage
        return contract_id.wage


    def MethodAverageAnnual(self,date_to,contract_id, nowage=None, noavg=None):
        """
        Calcula el salario promedio anual para el cálculo de la indemnización.
        @param date_to: Fecha final del periodo.
        @param contract_id: ID del contrato.
        @param nowage: True si no se tiene en cuenta el salario actual para el cálculo del promedio.
        @param noavg: True si se quiere obtener el total y no el promedio.
        @return: Salario promedio anual.
        """
        wage = 0.0
        first_day_of_current_month = date_to.replace(day=1)
        last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
        to_date = last_day_of_previous_month
        date_start = date_to + relativedelta(months=-11)
        date_from = date(date_start.year,date_start.month,1)
        initial_process_date = contract_id.date_start
        initial_process_date = initial_process_date if date_from < initial_process_date else date_from

        payslips = self.env['hr.payslip.line'].search([('date_from','>=',date_from),('date_from','<',to_date),('employee_id', '=', contract_id.employee_id.id),('category_id.code','=','DEV_SALARIAL')], order="date_from desc")
        hr_accumula = self.env['hr.accumulated.payroll'].search([('date','>=',date_from),('date','<',to_date),('employee_id', '=', contract_id.employee_id.id),('salary_rule_id.category_id.code','=','DEV_SALARIAL')], order="date desc")
        obj_wage = self.env['hr.contract.change.wage'].search([('contract_id', '=', contract_id.id), ('date_start', '>=', initial_process_date), ('date_start', '<=', to_date)])
        dias_trabajados = self.dias360(initial_process_date, to_date)
        dias_ausencias =  sum([i.number_of_days for i in self.env['hr.leave'].search([('date_from','>=',initial_process_date),('date_to','<=',to_date),('state','=','validate'),('employee_id','=',self.employee_id.id),('unpaid_absences','=',True)])])
        dias_ausencias += sum([i.days for i in self.env['hr.absence.history'].search([('star_date', '>=', initial_process_date), ('end_date', '<=', to_date),('employee_id', '=', self.employee_id.id),('leave_type_id.unpaid_absences', '=', True)])])
        dias_liquidacion = dias_trabajados - dias_ausencias
        if len(obj_wage) > 0 and nowage:
            wage_average = 0
            while initial_process_date <= to_date:
                if initial_process_date.day != 31:
                    if initial_process_date.month == 2 and  initial_process_date.day == 28 and (initial_process_date + timedelta(days=1)).day != 29:
                        wage_average += (contract_id.get_wage_in_date(initial_process_date) / 30)*3
                    elif initial_process_date.month == 2 and initial_process_date.day == 29:
                        wage_average += (contract_id.get_wage_in_date(initial_process_date) / 30)*2
                    else:
                        wage_average += contract_id.get_wage_in_date(initial_process_date)/30
                initial_process_date = initial_process_date + timedelta(days=1)
            if dias_trabajados != 0:
                wage = contract_id.wage if wage_average == 0 else (wage_average/dias_trabajados)*30
            else:
                wage = 0
        amount=0
        if payslips:
            for payslip in payslips:
                amount += payslip.total
            if hr_accumula:
                for hr in hr_accumula:
                    amount += hr.amount
                    _logger.info(amount)
            if noavg:
                return (amount+((wage/30)*dias_liquidacion))
            else:
                return ((amount+((wage/30)*dias_liquidacion))/dias_liquidacion)*30
        else:
            return 0

    def mount_rule_before(self, code, from_date, contract_id):
        date_actual = from_date
        month = from_date.month - 1
        year = from_date.year
        if month == 0:
            month = 12
            year -= 1
        day = 30 if month != 2 else 28
        from_date = datetime(year, month, 1).date()
        to_date = datetime(year, month, day).date()
        annual_parameters = self.env['hr.annual.parameters'].search([('year', '=', date_actual.year)])
        # Find payslip lines for the given code and date range
        PayslipLine = self.env['hr.payslip.line']
        payslip_lines = PayslipLine.search([
            ('slip_id.state', 'in', ['done', 'paid']),
            ('slip_id.contract_id', '=', contract_id.id),
            ('slip_id.date_to', '>', from_date),
            ('slip_id.date_from', '<', to_date),
            #('salary_rule_id.code', '=', code)
        ])
        value_base = 0
        base_40 = 0
        value_base_no_dev = 0
        # Calculate the IBC by summing up the totals of matching payslip lines
        for line in payslip_lines:
            value_base += abs(line.total) if line.salary_rule_id.category_id.code == 'DEV_SALARIAL' or line.salary_rule_id.category_id.parent_id.code == 'DEV_SALARIAL' else 0
            value_base_no_dev += abs(line.total) if line.salary_rule_id.category_id.code == 'DEV_NO_SALARIAL' or line.salary_rule_id.category_id.parent_id.code == 'DEV_NO_SALARIAL' else 0
        gran_total = value_base + value_base_no_dev 
        statute_value = gran_total*(annual_parameters.value_porc_statute_1395/100)
        total_statute = value_base_no_dev-statute_value 
        if total_statute > 0: 
            base_40 = total_statute     
        ibc = value_base + base_40
        # If IBC is not zero, return it
        if ibc:
            return ibc
        # Check for custom IBC (u_ibc) on the contract, if it matches the IBC date
        if contract_id.fecha_ibc and from_date.year == contract_id.fecha_ibc.year and from_date.month == contract_id.fecha_ibc.month:
            return contract_id.u_ibc
        # If no IBC is found, return the contract's wage
        return contract_id.wage

    def is_working_day(self, date):
        work_days = [int(x.dayofweek)
                     for x in self.resource_calendar_id.attendance_ids]
        return date.weekday() in work_days


    def has_change_salary(self, date_from, date_to):
        wages_in_period = filter(lambda x: date_from <= x.date_start <= date_to, self.change_wage_ids)
        return len(list(wages_in_period)) >= 1