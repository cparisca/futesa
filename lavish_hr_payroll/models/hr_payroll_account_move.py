# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from .browsable_object import BrowsableObject, InputLine, WorkedDays, Payslips
from odoo.tools import float_compare, float_is_zero

from collections import defaultdict
from datetime import datetime, timedelta, date, time
import pytz
from logging import exception
from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from decimal import *

import base64
import io
import xlsxwriter
import odoo
import threading
import math
class BrowsableObject(object):
    def __init__(self, employee_id, dict, env):
        self.employee_id = employee_id
        self.dict = dict
        self.env = env

    def __getattr__(self, attr):
        return attr in self.dict and self.dict.__getitem__(attr) or 0.0
class account_move_line(models.Model):
    _inherit = 'account.move.line'

    hr_salary_rule_id = fields.Many2one('hr.salary.rule', string='Regla salarial')
    hr_struct_id_id = fields.Many2one('hr.payroll.structure', string='Estructura salarial')
    is_payroll = fields.Boolean('Pago a Terceros')

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    drink_volume = fields.Float(string='Drink Volume (ml)', default=0.0)
    drink_volume_tax_checker = fields.Boolean(string='Drink Volume Tax Checker')
    enable_charges = fields.Boolean(string='Cargo de Factura Electrónica',)
    aiu_type = fields.Selection(
        selection=[('administracion', 'Administracion'),
                   ('imprevistos', 'Imprevistos'),
                   ('utilidad', 'Utilidad')
                   ],string='Seleccione AIU')
class account_move(models.Model):
    _inherit = 'account.move'

    product_id = fields.Many2one('product.product', string='Servicio Para Facturar', domain="[('sale_ok', '=', True),('type','=','service')]", ondelete='restrict')
    date_start = fields.Date(string="Initial Date",  copy=False)
    date_end = fields.Date(sring="End Date", copy=False)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Cuenta analítica')
    hr_paylip_ids = fields.Many2many("hr.payslip")
    hr_paylip_run_ids = fields.Many2many("hr.payslip.run")
    is_payroll = fields.Boolean('Pago a Terceros')
    executing_social_security_ids = fields.One2many('hr.account.executing.social.security', 'executing_social_security_id', string='Ejecución')
    aiu_invoice = fields.Boolean(default=False,string='Factura de AIU')
    percent_administration = fields.Float(string='Administracion %')
    percent_contingencies = fields.Float(string='Imprevistos %')
    percent_utility = fields.Float(string='Utilidad %')

    @api.onchange('aiu_invoice', 'percent_administration', 'percent_contingencies', 'percent_utility', 'invoice_line_ids')
    def calcular_aiu(self):
        self.ensure_one()
    
        if self.aiu_invoice:
            base_aiu = sum(line.price_subtotal for line in self.invoice_line_ids if not line.exclude_from_invoice_tab and not line.product_id.enable_charges)
    
            mapa_linea = {
                'name': self.payment_reference or '',
                'quantity': 1.0,
                'amount_currency': 0,
                'partner_id': self.commercial_partner_id.id,
                'exclude_from_invoice_tab': False,
                'currency_id': self.currency_id.id if self.currency_id != self.company_id.currency_id else self.company_id.currency_id.id,
                'move_id': self.id
            }
    
            for field, aiu_type in [('percent_administration', 'administracion'), ('percent_contingencies', 'imprevistos'), ('percent_utility', 'utilidad')]:
                if getattr(self, field) > 0:
                    producto = self.env['product.product'].sudo().search([('aiu_type', '=', aiu_type), '|', ('company_id', '=', False), ('company_id', '=', self.company_id.id)])
                    if producto.id not in [line.product_id.id for line in self.invoice_line_ids]:
                        self.invoice_line_ids = [(0, 0, mapa_linea)]
                        line = self.invoice_line_ids[-1]
                        line.product_id = producto
                        line.quantity = 1
                        line.amount_currency = 0
                        line.tax_ids = producto.taxes_id.ids
                        line.analytic_account_id = self.analytic_account_id.id
                        line.currency_id = self.currency_id.id
                        line.partner_id = self.commercial_partner_id.id
                        line.price_unit = base_aiu * getattr(self, field) / 100
                        line.name = line._get_computed_name()
                        line.account_id = line._get_computed_account()
                        line._onchange_mark_recompute_taxes()
                        line._set_price_and_tax_after_fpos()
                        line._onchange_price_subtotal()
                        line._compute_tax_line_id()
                        line._compute_tax_audit()
                    else:
                        line = next((line for line in self.invoice_line_ids if line.product_id.id == producto.id), None)
                        if line:
                            line.price_unit = base_aiu * getattr(self, field) / 100
                            line.name = line._get_computed_name()
                            line.account_id = line._get_computed_account()
                            line._onchange_mark_recompute_taxes()
                            line._set_price_and_tax_after_fpos()
                            line._onchange_price_subtotal()
                            line._compute_tax_line_id()
                            line._compute_tax_audit()
            self._recompute_dynamic_lines(recompute_all_taxes=True, recompute_tax_base_amount=True)
            self._onchange_tax_totals_json()

    def _check_balanced(self):
        ''' Assert the move is fully balanced debit = credit.
        An error is raised if it's not the case.
        '''
        moves = self.filtered(lambda move: move.line_ids)
        if not moves:
            return

        # /!\ As this method is called in create / write, we can't make the assumption the computed stored fields
        # are already done. Then, this query MUST NOT depend of computed stored fields (e.g. balance).
        # It happens as the ORM makes the create with the 'no_recompute' statement.
        self.env['account.move.line'].flush(self.env['account.move.line']._fields)
        self.env['account.move'].flush(['journal_id'])
        self._cr.execute('''
            SELECT line.move_id, ROUND(SUM(line.debit - line.credit), currency.decimal_places)
            FROM account_move_line line
            JOIN account_move move ON move.id = line.move_id
            JOIN account_journal journal ON journal.id = move.journal_id
            JOIN res_company company ON company.id = journal.company_id
            JOIN res_currency currency ON currency.id = company.currency_id
            WHERE line.move_id IN %s
            GROUP BY line.move_id, currency.decimal_places
            HAVING ROUND(SUM(line.debit - line.credit), currency.decimal_places) != 0.0;
        ''', [tuple(self.ids)])

        query_res = self._cr.fetchall()
        if query_res:
            ids = [res[0] for res in query_res]
            sums = [res[1] for res in query_res]
            #raise UserError(_("Cannot create unbalanced journal entry. Ids: %s\nDifferences debit - credit: %s") % (ids, sums))

    def executing_social_security_thread(self,date_start,date_end,obj_employee):
        env = self.env
        def roundup100(amount):
            return math.ceil(amount / 100.0) * 100

        def roundupdecimal(amount):
            return math.ceil(amount)

        #Obtener parametros anuales
        annual_parameters = env['hr.annual.parameters'].search([('year', '=', date_start.year)])

        #Recorre empleados y realizar la respectiva lógica
        for o_employee in obj_employee:
            employee = env['hr.employee'].search([('id','=',o_employee.id)])
            obj_contracts = env['hr.contract'].search([('state','=','close'),('employee_id','=',employee.id),('retirement_date','>=',date_start),('retirement_date','<=',date_end+relativedelta(months=1))], limit = 1)
            obj_contracts += env['hr.contract'].search([('state','=','open'), ('employee_id', '=', employee.id), ('date_start', '<=', date_end)])
            obj_contracts += env['hr.contract'].search([('state', '=', 'finished'), ('employee_id', '=', employee.id),('date_end', '>=', date_start),('date_end', '<=', date_end + relativedelta(months=1))], limit=1)

            for obj_contract in obj_contracts:
                #Obtener nóminas en ese rango de fechas
                obj_payslip = env['hr.payslip'].search([('state','=','done'),('employee_id','=',employee.id),('contract_id','=',obj_contract.id)])
                obj_payslip = obj_payslip.filtered(lambda p: (p.date_from >= date_start and p.date_from <= date_end) or (p.date_to >= date_start and p.date_to <= date_end))

                #Primero, encontró una entrada de trabajo que no excedió el intervalo.
                datetime_start = datetime.combine(date_start, datetime.min.time())
                datetime_end = datetime.combine(date_end, datetime.max.time())
                work_entries = env['hr.work.entry'].search(
                    [
                        ('state', 'in', ['validated', 'draft']),
                        ('date_start', '>=', datetime_start),
                        ('date_stop', '<=', datetime_end),
                        ('contract_id', '=', obj_contract.id),
                        ('leave_id','!=',False)
                    ]
                )
                #En segundo lugar, encontró entradas de trabajo que exceden el intervalo y calculan la duración correcta.
                work_entries += env['hr.work.entry'].search(
                    [
                        '&', '&', '&',
                        ('leave_id','!=',False),
                        ('state', 'in', ['validated', 'draft']),
                        ('contract_id', '=', obj_contract.id),
                        '|', '|', '&', '&',
                        ('date_start', '>=', datetime_start),
                        ('date_start', '<', datetime_end),
                        ('date_stop', '>', datetime_end),
                        '&', '&',
                        ('date_start', '<', datetime_start),
                        ('date_stop', '<=', datetime_end),
                        ('date_stop', '>', datetime_start),
                        '&',
                        ('date_start', '<', datetime_start),
                        ('date_stop', '>', datetime_end),
                    ]
                )

                # Obtener parametrización de cotizantes
                obj_parameterization_contributors = env['hr.parameterization.of.contributors'].search(
                    [('type_of_contributor', '=', employee.tipo_coti_id.id),
                     ('contributor_subtype', '=', employee.subtipo_coti_id.id)], limit=1)
                #Variables
                bEsAprendiz = True if obj_contract.contract_type == 'aprendizaje' else False
                nDiasLiquidados = 0
                nNumeroHorasLaboradas = 0
                nIngreso = False
                nRetiro = False
                #Sueldo
                nSueldo = obj_contract.wage
                #Listas y diccionarios
                category_news = ['INCAPACIDAD','LICENCIA_NO_REMUNERADA','LICENCIA_REMUNERADA','LICENCIA_MATERNIDAD','VACACIONES','ACCIDENTE_TRABAJO']
                dict_social_security = {
                    'BaseSeguridadSocial':BrowsableObject(employee.id, {}, env),
                    'BaseParafiscales':BrowsableObject(employee.id, {}, env),
                    'Dias':BrowsableObject(employee.id, {}, env)
                }
                #Valores
                nValorBaseSalud,nValorBaseFondoPension,nValorBaseARP,nValorBaseCajaCom,nValorBaseSENA,nValorBaseICBF = 0,0,0,0,0,0
                nValorSaludEmpleadoNomina,nValorPensionEmpleadoNomina,nAporteVoluntarioPension,nValorFondoSolidaridad,nValorFondoSubsistencia = 0,0,0,0,0
                #Entidades
                TerceroEPS,TerceroPension,TerceroFondoSolidaridad,TerceroFondoSubsistencia = False,False,False,False
                TerceroCesantias,TerceroCajaCompensacion,TerceroARP,TerceroSENA,TerceroICBF = False,False,False,False,False
                for entity in employee.social_security_entities:
                    if entity.contrib_id.type_entities == 'eps': # Salud
                        TerceroEPS = entity.partner_id
                    if entity.contrib_id.type_entities == 'pension': # Pension
                        TerceroPension = entity.partner_id
                    if entity.contrib_id.type_entities == 'solidaridad': # Solidaridad
                        TerceroFondoSolidaridad = entity.partner_id
                    if entity.contrib_id.type_entities == 'subsistencia': # Subsistencia
                        TerceroFondoSubsistencia = entity.partner_id
                    if entity.contrib_id.type_entities == 'caja': # Caja de compensación
                        TerceroCajaCompensacion = entity.partner_id
                    if entity.contrib_id.type_entities == 'riesgo': # Aseguradora de riesgos laborales
                        TerceroARP = entity.partner_id
                    if entity.contrib_id.type_entities == 'cesantias': # Cesantias
                        TerceroCesantias = entity.partner_id

                id_type_entities_sena = env['hr.contribution.register'].search([('type_entities','=','sena')], limit=1).id
                TerceroSENA = env['hr.employee.entities'].search([('types_entities','in',[id_type_entities_sena])]) # SENA
                id_type_entities_icbf = env['hr.contribution.register'].search([('type_entities','=','icbf')], limit=1).id
                TerceroICBF = env['hr.employee.entities'].search([('types_entities','in',[id_type_entities_icbf])]) #  ICBF

                leave_list = []
                leave_time_ids = []
                for leave in work_entries:
                    if leave.leave_id.id not in leave_time_ids:
                        #Obtener fechas y dias
                        request_date_from = leave.leave_id.request_date_from if leave.leave_id.request_date_from >= date_start else date_start
                        request_date_to = leave.leave_id.request_date_to if leave.leave_id.request_date_to <= date_end else date_end
                        if request_date_from.month == 2 and request_date_to.month == 2:
                            number_of_days = (request_date_to-request_date_from).days + 1
                        else:
                            number_of_days = self.dias360(request_date_from,request_date_to)

                        leave_dict = {'id':leave.leave_id.id,
                                        'type':leave.leave_id.holiday_status_id.code,
                                        'date_start': request_date_from,
                                        'date_end': request_date_to,
                                        'days':  number_of_days,
                                        'days_totals': leave.leave_id.number_of_days
                                    }
                        leave_list.append(leave_dict)
                        leave_time_ids.append(leave.leave_id.id)

                cant_payslip = 0
                for payslip in obj_payslip:
                    #Variables
                    cant_payslip += 1
                    contract_id = payslip.contract_id
                    analytic_account_id = payslip.analytic_account_id

                    #Obtener si es un ingreso o un retiro
                    if payslip.contract_id.date_start:
                        nIngreso = True if payslip.contract_id.date_start.month == date_start.month and payslip.contract_id.date_start.year == date_start.year else False
                    if payslip.contract_id.retirement_date:
                        nRetiro = True if payslip.contract_id.retirement_date.month == date_start.month and payslip.contract_id.retirement_date.year == date_start.year else False
                    if payslip.contract_id.date_end and nRetiro == False:
                        nRetiro = True if payslip.contract_id.date_end.month == date_start.month and payslip.contract_id.date_end.year == date_start.year else False
                    #Obtener dias laborados normales
                    for days in payslip.worked_days_line_ids:
                        nDiasLiquidados	+= days.number_of_days if days.work_entry_type_id.code in ('WORK100','COMPENSATORIO') else 0
                        nNumeroHorasLaboradas += days.number_of_hours if days.work_entry_type_id.code in ('WORK100','COMPENSATORIO') else 0
                    #Obtener dias laborados con tipo de subcontrato parcial o parcial integral
                    #if payslip.contract_id.subcontract_type in ('obra_parcial','obra_integral'):
                    #    obj_overtime = env['hr.overtime'].search([('employee_id', '=', employee.id), ('date', '>=', date_start),('date_end', '<=', date_end)])
                    #    if len(obj_overtime) > 0:
                    #        nDiasLiquidados = round(sum(o.days_actually_worked for o in obj_overtime))#round(sum(o.shift_hours for o in obj_overtime) / 8)
                    #        nNumeroHorasLaboradas = round(sum(o.days_actually_worked for o in obj_overtime)*8)#round(sum(o.shift_hours for o in obj_overtime))
                    #Obtener valores
                    for line in payslip.line_ids:
                        #Bases seguridad social
                        if line.salary_rule_id.base_seguridad_social:
                            dict_social_security['BaseSeguridadSocial'].dict['TOTAL'] = dict_social_security['BaseSeguridadSocial'].dict.get('TOTAL', 0) + line.total
                            if line.salary_rule_id.category_id.code in category_news:
                                dict_social_security['BaseSeguridadSocial'].dict[line.salary_rule_id.category_id.code] = dict_social_security['BaseSeguridadSocial'].dict.get(line.salary_rule_id.category_id.code, 0) + line.total
                                dict_social_security['BaseSeguridadSocial'].dict['DIAS_'+line.salary_rule_id.category_id.code] = dict_social_security['BaseSeguridadSocial'].dict.get('DIAS_'+line.salary_rule_id.category_id.code, 0) + line.quantity
                            else:
                                if payslip.date_from >= date_start and payslip.date_from <= date_end:
                                    if line.salary_rule_id.category_id.code == 'BASIC' and contract_id.modality_salary == 'integral':
                                        value = (line.total*annual_parameters.porc_integral_salary)/100
                                        dict_social_security['BaseSeguridadSocial'].dict['BASE'] = dict_social_security['BaseSeguridadSocial'].dict.get('BASE', 0) + value
                                    else:
                                        dict_social_security['BaseSeguridadSocial'].dict['BASE'] = dict_social_security['BaseSeguridadSocial'].dict.get('BASE', 0) + line.total
                        #Bases parafiscales
                        if line.salary_rule_id.base_parafiscales:
                            dict_social_security['BaseParafiscales'].dict['TOTAL'] = dict_social_security['BaseParafiscales'].dict.get('TOTAL', 0) + line.total
                            if line.salary_rule_id.category_id.code in category_news:
                                dict_social_security['BaseParafiscales'].dict[line.salary_rule_id.category_id.code] = dict_social_security['BaseParafiscales'].dict.get(line.salary_rule_id.category_id.code, 0) + line.total
                                dict_social_security['BaseParafiscales'].dict['DIAS_'+line.salary_rule_id.category_id.code] = dict_social_security['BaseParafiscales'].dict.get('DIAS_'+line.salary_rule_id.category_id.code, 0) + line.quantity
                            else:
                                if payslip.date_from >= date_start and payslip.date_from <= date_end:
                                    if line.salary_rule_id.category_id.code == 'BASIC' and contract_id.modality_salary == 'integral':
                                        value = (line.total*annual_parameters.porc_integral_salary)/100
                                        dict_social_security['BaseParafiscales'].dict['BASE'] = dict_social_security['BaseParafiscales'].dict.get('BASE', 0) + value
                                    else:
                                        dict_social_security['BaseParafiscales'].dict['BASE'] = dict_social_security['BaseParafiscales'].dict.get('BASE', 0) + line.total

                        #Salud
                        nValorBaseSalud += line.total if line.salary_rule_id.base_seguridad_social else 0
                        nValorSaludEmpleadoNomina += abs(line.total) if line.code == 'SSOCIAL001' else 0
                        #Pension y fondo de solidaridad
                        nValorBaseFondoPension += line.total if line.salary_rule_id.base_seguridad_social else 0
                        nValorPensionEmpleadoNomina += abs(line.total) if line.code == 'SSOCIAL002' else 0
                        nAporteVoluntarioPension += abs(line.total) if line.salary_rule_id.code == 'AVP' else 0
                        nValorFondoSubsistencia += abs(line.total) if line.code == 'SSOCIAL003' else 0
                        nValorFondoSolidaridad += abs(line.total) if line.code == 'SSOCIAL004' else 0
                        #ARL
                        nValorBaseARP += line.total if line.salary_rule_id.base_seguridad_social else 0
                        nPorcAporteARP = payslip.contract_id.risk_id.percent
                        #Caja de compensación
                        nValorBaseCajaCom += line.total if line.salary_rule_id.base_parafiscales else 0
                        #SENA & ICBF
                        nValorBaseSENA += line.total if line.salary_rule_id.base_parafiscales else 0
                        nValorBaseICBF += line.total if line.salary_rule_id.base_parafiscales else 0

                if cant_payslip > 0 and employee.tipo_coti_id.code != '51': # Proceso para tipos de cotizante diferente a 51 - Trabajador de Tiempo Parcial
                    #Validar que la suma de los dias sea igual a 30 y en caso de se superior restar en los dias liquidados la diferencia
                    nDiasTotales = nDiasLiquidados
                    nDiasRetiro = 0 # Historia: Ajuste seguridad social unidades laboradas
                    for leave in leave_list:
                        nDiasTotales += leave['days'] if leave['type'] != 'COMPENSATORIO' else 0

                    if nRetiro and payslip.contract_id.retirement_date:
                        if payslip.contract_id.retirement_date.day < nDiasTotales:
                            nDiasRetiro = (30 - payslip.contract_id.retirement_date.day) if (30 - nDiasTotales) < 0 else (nDiasTotales - payslip.contract_id.retirement_date.day)

                    if nIngreso == False and nRetiro == False and self.date_end.month == 2:
                        nDiasLiquidados = (nDiasLiquidados-(nDiasTotales-30)) if (30-nDiasTotales) < 0 else (nDiasLiquidados+(30-nDiasTotales))
                    else:
                        nDiasLiquidados = (nDiasLiquidados - (nDiasTotales - 30)) if (30 - nDiasTotales) < 0 else nDiasLiquidados
                    nDiasLiquidados = nDiasLiquidados-nDiasRetiro
                    #Guardar linea principal
                    result = {
                        'executing_social_security_id': self.id,
                        'employee_id':employee.id,
                        'contract_id': contract_id.id,
                        'analytic_account_id': analytic_account_id.id,
                        'branch_id':employee.branch_id.id,
                        'nDiasLiquidados':nDiasLiquidados,
                        'nNumeroHorasLaboradas':nNumeroHorasLaboradas,
                        'nIngreso':nIngreso,
                        'nRetiro':nRetiro,
                        'nSueldo':nSueldo,
                        #Salud
                        'TerceroEPS':TerceroEPS.id if TerceroEPS else False,
                        'nValorBaseSalud':nValorBaseSalud,
                        'nValorSaludEmpleadoNomina':nValorSaludEmpleadoNomina,
                        #Pension
                        'TerceroPension':TerceroPension.id if TerceroPension else False,
                        'nValorBaseFondoPension':nValorBaseFondoPension,
                        'nValorPensionEmpleadoNomina':nValorPensionEmpleadoNomina+nValorFondoSubsistencia+nValorFondoSolidaridad,
                        'cAVP': True if nAporteVoluntarioPension > 0 else False,
                        'nAporteVoluntarioPension': nAporteVoluntarioPension,
                        #Fondo Solidaridad y Subsistencia
                        'TerceroFondoSolidaridad': TerceroFondoSolidaridad.id if TerceroFondoSolidaridad else TerceroPension.id if TerceroPension else False,
                        #ARP/ARL - Administradora de riesgos profesionales/laborales
                        'TerceroARP':TerceroARP.id if TerceroARP else False,
                        'nValorBaseARP':nValorBaseARP,
                        #Caja de Compensación
                        'TerceroCajaCom': TerceroCajaCompensacion.id if TerceroCajaCompensacion else False,
                        'nValorBaseCajaCom':nValorBaseCajaCom,
                        #SENA & ICBF
                        'cExonerado1607': employee.company_id.exonerated_law_1607 if bEsAprendiz == False and nSueldo < (annual_parameters.smmlv_monthly*10) else False,
                        'TerceroSENA': TerceroSENA.id if TerceroSENA else False,
                        'nValorBaseSENA':nValorBaseSENA,
                        'TerceroICBF': TerceroICBF.id if TerceroICBF else False,
                        'nValorBaseICBF':nValorBaseICBF,
                    }

                    obj_executing = env['hr.account.executing.social.security'].create(result)

                    #Una vez creada la linea principal, se obtienen las ausencias con sus respectivas fechas y se recalculan las lineas
                    for leave in leave_list:
                        result['leave_id'] = leave['id']
                        result['nDiasLiquidados'] = 0
                        result['nNumeroHorasLaboradas'] = 0
                        #Incapacidad EPS
                        nDiasIncapacidadEPS = leave['days'] if leave['type'] in ('EGA','EGH') else 0 # Categoria: INCAPACIDAD
                        dict_social_security['Dias'].dict['nDiasIncapacidadEPS'] = dict_social_security['Dias'].dict.get('nDiasIncapacidadEPS', 0) + nDiasIncapacidadEPS
                        result['nDiasIncapacidadEPS'] = nDiasIncapacidadEPS
                        result['dFechaInicioIGE'] = leave['date_start'] if leave['type'] in ('EGA','EGH') else False
                        result['dFechaFinIGE'] = leave['date_end'] if leave['type'] in ('EGA','EGH') else False
                        #Licencia
                        nDiasLicencia = leave['days'] if leave['type'] in ('LICENCIA_NO_REMUNERADA','INAS_INJU','SANCION','SUSP_CONTRATO','DNR') else 0 # Categoria: LICENCIA_NO_REMUNERADA
                        dict_social_security['Dias'].dict['nDiasLicencia'] = dict_social_security['Dias'].dict.get('nDiasLicencia', 0) + nDiasLicencia
                        result['nDiasLicencia'] = nDiasLicencia
                        result['dFechaInicioSLN'] = leave['date_start'] if leave['type'] in ('LICENCIA_NO_REMUNERADA','INAS_INJU','SANCION','SUSP_CONTRATO','DNR') else False
                        result['dFechaFinSLN'] = leave['date_end'] if leave['type'] in ('LICENCIA_NO_REMUNERADA','INAS_INJU','SANCION','SUSP_CONTRATO','DNR') else False
                        #Licencia Remunerada
                        nDiasLicenciaRenumerada = leave['days'] if leave['type'] in ('LICENCIA_REMUNERADA','LUTO','REP_VACACIONES') else 0 # Categoria: LICENCIA_REMUNERADA
                        dict_social_security['Dias'].dict['nDiasLicenciaRenumerada'] = dict_social_security['Dias'].dict.get('nDiasLicenciaRenumerada', 0) + nDiasLicenciaRenumerada
                        result['nDiasLicenciaRenumerada']	= nDiasLicenciaRenumerada
                        result['dFechaInicioVACLR'] = leave['date_start'] if leave['type'] in ('LICENCIA_REMUNERADA','LUTO','VACDISFRUTADAS','REP_VACACIONES') else False
                        result['dFechaFinVACLR'] = leave['date_end'] if leave['type'] in ('LICENCIA_REMUNERADA','LUTO','VACDISFRUTADAS','REP_VACACIONES') else False
                        #Maternida
                        nDiasMaternidad = leave['days'] if leave['type'] in ('MAT','PAT') else 0 # Categoria: LICENCIA_MATERNIDAD
                        dict_social_security['Dias'].dict['nDiasMaternidad'] = dict_social_security['Dias'].dict.get('nDiasMaternidad', 0) + nDiasMaternidad
                        result['nDiasMaternidad'] = nDiasMaternidad
                        result['dFechaInicioLMA'] = leave['date_start'] if leave['type'] in ('MAT','PAT') else False
                        result['dFechaFinLMA'] = leave['date_end'] if leave['type'] in ('MAT','PAT') else False
                        #Vacaciones
                        nDiasVacaciones = leave['days'] if leave['type'] == 'VACDISFRUTADAS' else 0 # Categoria: VACACIONES
                        dict_social_security['Dias'].dict['nDiasVacaciones'] = dict_social_security['Dias'].dict.get('nDiasVacaciones', 0) + nDiasVacaciones
                        result['nDiasVacaciones'] = nDiasVacaciones
                        result['dFechaInicioVACLR'] = leave['date_start'] if leave['type'] in ('LICENCIA_REMUNERADA','LUTO','VACDISFRUTADAS','REP_VACACIONES') else False
                        result['dFechaFinVACLR'] = leave['date_end'] if leave['type'] in ('LICENCIA_REMUNERADA','LUTO','VACDISFRUTADAS','REP_VACACIONES') else False
                        #ARL
                        nDiasIncapacidadARP = leave['days'] if leave['type'] in ('EP','AT') else 0 # Categoria: ACCIDENTE_TRABAJO
                        dict_social_security['Dias'].dict['nDiasIncapacidadARP'] = dict_social_security['Dias'].dict.get('nDiasIncapacidadARP', 0) + nDiasIncapacidadARP
                        result['nDiasIncapacidadARP'] = nDiasIncapacidadARP
                        result['dFechaInicioIRL'] = leave['date_start'] if leave['type'] in ('EP','AT') else False
                        result['dFechaFinIRL'] = leave['date_end'] if leave['type'] in ('EP','AT') else False

                        #Ingreso & Retiro - cuando existen novedades
                        nDiasAusencias = nDiasIncapacidadEPS+nDiasLicencia+nDiasLicenciaRenumerada+nDiasMaternidad+nDiasVacaciones+nDiasIncapacidadARP
                        result['nIngreso'] = False if nDiasAusencias > 0 else result['nIngreso']
                        result['nRetiro'] = False if nDiasAusencias > 0 else result['nRetiro']

                        obj_executing += env['hr.account.executing.social.security'].create(result)

                    #Recorrer items creados
                    cant_items = len(obj_executing)
                    item = 1
                    #Valores TOTALES
                    nValorSaludTotalEmpleado,nValorSaludTotalEmpresa = 0,0
                    nValorPensioTotalEmpleado,nValorPensionTotalEmpresa,nValorTotalFondos = 0,0,0
                    nValorSaludTotal,nValorPensionTotal = 0,0
                    nRedondeoDecimalesDif = 5 # Max diferencia de decimales
                    #Verificar si existe retiro sin tener dias trabajados
                    if nRetiro == True:
                        for executing_ret in sorted(obj_executing, key=lambda x: (x.nDiasLiquidados, x.nDiasIncapacidadEPS, x.nDiasVacaciones, x.nDiasMaternidad,x.nDiasIncapacidadARP, x.nDiasLicenciaRenumerada, x.nDiasLicencia)):
                            if executing_ret.nDiasLiquidados == 0 and executing_ret.nDiasIncapacidadEPS == 0 and executing_ret.nDiasLicencia == 0 and executing_ret.nDiasLicenciaRenumerada == 0 and executing_ret.nDiasMaternidad == 0 and executing_ret.nDiasVacaciones == 0 and executing_ret.nDiasIncapacidadARP == 0:
                                nDiasLiquidados_totales = sum([x.nDiasLiquidados for x in obj_executing])
                                if nDiasLiquidados_totales == 0:
                                    executing_ret.write({'nDiasLiquidados': 1})
                    #Ejecución de valores
                    for executing in sorted(obj_executing,key=lambda x: (x.nDiasLiquidados,x.nDiasIncapacidadEPS,x.nDiasVacaciones,x.nDiasMaternidad,x.nDiasIncapacidadARP,x.nDiasLicenciaRenumerada,x.nDiasLicencia)):
                        #Valores
                        nPorcAporteSaludEmpleado,nPorcAporteSaludEmpresa,nValorBaseSalud,nValorSaludEmpleado,nValorSaludEmpresa = 0,0,0,0,0
                        nPorcAportePensionEmpleado,nPorcAportePensionEmpresa,nValorBaseFondoPension,nValorPensionEmpleado,nValorPensionEmpresa = 0,0,0,0,0
                        nPorcFondoSolidaridad,nValorFondoSolidaridad,nValorFondoSubsistencia = 0,0,0
                        nValorBaseARP,nValorARP = 0,0
                        nValorBaseCajaCom,nPorcAporteCajaCom,nValorCajaCom = 0,0,0
                        nValorBaseSENA,nPorcAporteSENA,nValorSENA = 0,0,0
                        nValorBaseICBF,nPorcAporteICBF,nValorICBF = 0,0,0
                        #Dias
                        nDiasLicencia = executing.nDiasLicencia
                        nDiasVacaciones = executing.nDiasVacaciones
                        nDiasAusencias = executing.nDiasIncapacidadEPS+executing.nDiasLicencia+executing.nDiasLicenciaRenumerada+executing.nDiasMaternidad+executing.nDiasIncapacidadARP
                        nDias = executing.nDiasLiquidados+executing.nDiasIncapacidadEPS+executing.nDiasLicencia+executing.nDiasLicenciaRenumerada+executing.nDiasMaternidad+executing.nDiasVacaciones+executing.nDiasIncapacidadARP

                        #Calculos valores base dependiendo los días
                        salario_minimo_diario = Decimal(Decimal(annual_parameters.smmlv_monthly)/Decimal(30))
                        if executing.nDiasLiquidados > 0:
                            if dict_social_security['BaseSeguridadSocial'].dict.get('BASE', 0) > 0:
                                nValorDiario = Decimal(Decimal(dict_social_security['BaseSeguridadSocial'].dict['BASE']) / Decimal(executing.nDiasLiquidados))
                                nValorDiario = nValorDiario if nValorDiario >= salario_minimo_diario else salario_minimo_diario
                                nValorBaseSalud = nValorDiario * executing.nDiasLiquidados
                                nValorBaseFondoPension = nValorDiario * executing.nDiasLiquidados
                                nValorBaseARP = nValorDiario * executing.nDiasLiquidados
                            if dict_social_security['BaseParafiscales'].dict.get('BASE', 0) > 0:
                                nValorDiario = Decimal(Decimal(dict_social_security['BaseParafiscales'].dict['BASE']) / Decimal(executing.nDiasLiquidados))
                                nValorDiario = nValorDiario if nValorDiario >= salario_minimo_diario else salario_minimo_diario
                                nValorBaseCajaCom = nValorDiario * executing.nDiasLiquidados
                                nValorBaseSENA = nValorDiario * executing.nDiasLiquidados
                                nValorBaseICBF = nValorDiario * executing.nDiasLiquidados

                        if executing.nDiasIncapacidadEPS > 0:
                            if dict_social_security['BaseSeguridadSocial'].dict.get('INCAPACIDAD', 0) > 0:
                                nValorDiario = Decimal(Decimal(dict_social_security['BaseSeguridadSocial'].dict['INCAPACIDAD']) / Decimal(dict_social_security['Dias'].dict['nDiasIncapacidadEPS']))
                                nValorDiario = nValorDiario if nValorDiario >= salario_minimo_diario else salario_minimo_diario
                                nValorBaseSalud = nValorDiario * executing.nDiasIncapacidadEPS
                                nValorBaseFondoPension = nValorDiario * executing.nDiasIncapacidadEPS
                                nValorBaseARP = nValorDiario * executing.nDiasIncapacidadEPS
                            if dict_social_security['BaseParafiscales'].dict.get('INCAPACIDAD',0) > 0:
                                nValorDiario = Decimal(Decimal(dict_social_security['BaseParafiscales'].dict['INCAPACIDAD']) / Decimal(dict_social_security['Dias'].dict['nDiasIncapacidadEPS']))
                                nValorDiario = nValorDiario if nValorDiario >= salario_minimo_diario else salario_minimo_diario
                                nValorBaseCajaCom = nValorDiario * executing.nDiasIncapacidadEPS
                                nValorBaseSENA = nValorDiario * executing.nDiasIncapacidadEPS
                                nValorBaseICBF = nValorDiario * executing.nDiasIncapacidadEPS

                        if executing.nDiasLicencia > 0:
                            if dict_social_security['BaseSeguridadSocial'].dict.get('LICENCIA_NO_REMUNERADA', 0) > 0:
                                nValorBaseSalud = Decimal(Decimal(dict_social_security['BaseSeguridadSocial'].dict['LICENCIA_NO_REMUNERADA']) / Decimal(dict_social_security['Dias'].dict['nDiasLicencia'])) * executing.nDiasLicencia
                                nValorBaseFondoPension = Decimal(Decimal(dict_social_security['BaseSeguridadSocial'].dict['LICENCIA_NO_REMUNERADA']) / Decimal(dict_social_security['Dias'].dict['nDiasLicencia'])) * executing.nDiasLicencia
                                nValorBaseARP = Decimal(Decimal(dict_social_security['BaseSeguridadSocial'].dict['LICENCIA_NO_REMUNERADA']) / Decimal(dict_social_security['Dias'].dict['nDiasLicencia'])) * executing.nDiasLicencia
                            if dict_social_security['BaseParafiscales'].dict.get('LICENCIA_NO_REMUNERADA', 0) > 0:
                                nValorBaseCajaCom = Decimal(Decimal(dict_social_security['BaseParafiscales'].dict['LICENCIA_NO_REMUNERADA']) / Decimal(dict_social_security['Dias'].dict['nDiasLicencia'])) * executing.nDiasLicencia
                                nValorBaseSENA = Decimal(Decimal(dict_social_security['BaseParafiscales'].dict['LICENCIA_NO_REMUNERADA']) / Decimal(dict_social_security['Dias'].dict['nDiasLicencia'])) * executing.nDiasLicencia
                                nValorBaseICBF = Decimal(Decimal(dict_social_security['BaseParafiscales'].dict['LICENCIA_NO_REMUNERADA']) / Decimal(dict_social_security['Dias'].dict['nDiasLicencia'])) * executing.nDiasLicencia

                        if executing.nDiasLicenciaRenumerada > 0:
                            if dict_social_security['BaseSeguridadSocial'].dict.get('LICENCIA_REMUNERADA', 0) > 0:
                                nValorDiario = Decimal(Decimal(dict_social_security['BaseSeguridadSocial'].dict['LICENCIA_REMUNERADA']) / Decimal(dict_social_security['Dias'].dict['nDiasLicenciaRenumerada']))
                                nValorDiario = nValorDiario if nValorDiario >= salario_minimo_diario else salario_minimo_diario
                                nValorBaseSalud = nValorDiario * executing.nDiasLicenciaRenumerada
                                nValorBaseFondoPension = nValorDiario * executing.nDiasLicenciaRenumerada
                                nValorBaseARP = nValorDiario * executing.nDiasLicenciaRenumerada
                            if dict_social_security['BaseParafiscales'].dict.get('LICENCIA_REMUNERADA', 0) > 0:
                                nValorDiario = Decimal(Decimal(dict_social_security['BaseParafiscales'].dict['LICENCIA_REMUNERADA']) / Decimal(dict_social_security['Dias'].dict['nDiasLicenciaRenumerada']))
                                nValorDiario = nValorDiario if nValorDiario >= salario_minimo_diario else salario_minimo_diario
                                nValorBaseCajaCom = nValorDiario * executing.nDiasLicenciaRenumerada
                                nValorBaseSENA = nValorDiario * executing.nDiasLicenciaRenumerada
                                nValorBaseICBF = nValorDiario * executing.nDiasLicenciaRenumerada

                        if executing.nDiasMaternidad > 0:
                            if dict_social_security['BaseSeguridadSocial'].dict.get('LICENCIA_MATERNIDAD', 0) > 0:
                                nValorDiario = Decimal(Decimal(dict_social_security['BaseSeguridadSocial'].dict['LICENCIA_MATERNIDAD']) / Decimal(dict_social_security['Dias'].dict['nDiasMaternidad']))
                                nValorDiario = nValorDiario if nValorDiario >= salario_minimo_diario else salario_minimo_diario
                                nValorBaseSalud = nValorDiario * executing.nDiasMaternidad
                                nValorBaseFondoPension = nValorDiario * executing.nDiasMaternidad
                                nValorBaseARP = nValorDiario * executing.nDiasMaternidad
                            if dict_social_security['BaseParafiscales'].dict.get('LICENCIA_MATERNIDAD', 0) > 0:
                                nValorDiario = Decimal(Decimal(dict_social_security['BaseParafiscales'].dict['LICENCIA_MATERNIDAD']) / Decimal(dict_social_security['Dias'].dict['nDiasMaternidad']))
                                nValorDiario = nValorDiario if nValorDiario >= salario_minimo_diario else salario_minimo_diario
                                nValorBaseCajaCom = nValorDiario * executing.nDiasMaternidad
                                nValorBaseSENA = nValorDiario * executing.nDiasMaternidad
                                nValorBaseICBF = nValorDiario * executing.nDiasMaternidad

                        if executing.nDiasVacaciones > 0:
                            if dict_social_security['BaseSeguridadSocial'].dict.get('VACACIONES', 0) > 0:
                                nValorDiario = Decimal(Decimal(dict_social_security['BaseSeguridadSocial'].dict['VACACIONES']) / Decimal(dict_social_security['BaseSeguridadSocial'].dict['DIAS_VACACIONES']))
                                nValorDiario = nValorDiario if nValorDiario >= salario_minimo_diario else salario_minimo_diario
                                nValorBaseSalud = nValorDiario * executing.nDiasVacaciones
                                nValorBaseFondoPension = nValorDiario * executing.nDiasVacaciones
                                nValorBaseARP = nValorDiario * executing.nDiasVacaciones
                            if dict_social_security['BaseParafiscales'].dict.get('VACACIONES',0) > 0:
                                nValorDiario = Decimal(Decimal(dict_social_security['BaseParafiscales'].dict['VACACIONES']) / Decimal(dict_social_security['BaseParafiscales'].dict['DIAS_VACACIONES']))
                                nValorDiario = nValorDiario if nValorDiario >= salario_minimo_diario else salario_minimo_diario
                                nValorBaseCajaCom = nValorDiario * executing.nDiasVacaciones
                                nValorBaseSENA = nValorDiario * executing.nDiasVacaciones
                                nValorBaseICBF = nValorDiario * executing.nDiasVacaciones

                        if executing.nDiasIncapacidadARP > 0:
                            if dict_social_security['BaseSeguridadSocial'].dict.get('ACCIDENTE_TRABAJO', 0) > 0:
                                nValorDiario = Decimal(Decimal(dict_social_security['BaseSeguridadSocial'].dict['ACCIDENTE_TRABAJO']) / Decimal(dict_social_security['Dias'].dict['nDiasIncapacidadARP']))
                                nValorDiario = nValorDiario if nValorDiario >= salario_minimo_diario else salario_minimo_diario
                                nValorBaseSalud = nValorDiario * executing.nDiasIncapacidadARP
                                nValorBaseFondoPension = nValorDiario * executing.nDiasIncapacidadARP
                                nValorBaseARP = nValorDiario * executing.nDiasIncapacidadARP
                            if dict_social_security['BaseParafiscales'].dict.get('ACCIDENTE_TRABAJO',0) > 0:
                                nValorDiario = Decimal(Decimal(dict_social_security['BaseParafiscales'].dict['ACCIDENTE_TRABAJO']) / Decimal(dict_social_security['Dias'].dict['nDiasIncapacidadARP']))
                                nValorDiario = nValorDiario if nValorDiario >= salario_minimo_diario else salario_minimo_diario
                                nValorBaseCajaCom = nValorDiario * executing.nDiasIncapacidadARP
                                nValorBaseSENA = nValorDiario * executing.nDiasIncapacidadARP
                                nValorBaseICBF = nValorDiario * executing.nDiasIncapacidadARP

                        valor_base_sueldo =(Decimal(executing.nSueldo) / Decimal(30)) * Decimal(nDias)
                        #----------------CALCULOS SALUD
                        if obj_parameterization_contributors.liquidated_eps_employee or obj_parameterization_contributors.liquidates_eps_company:
                            if nValorBaseSalud == 0:
                                nValorBaseSalud = float(roundupdecimal(valor_base_sueldo))
                            else:
                                nValorBaseSalud = float(roundupdecimal(valor_base_sueldo) if abs((valor_base_sueldo) - nValorBaseSalud) < nRedondeoDecimalesDif else roundupdecimal(nValorBaseSalud))
                            #nValorBaseSalud = (valor_base_sueldo) if nValorBaseSalud == 0 else (nValorBaseSalud)
                            if nValorBaseSalud > 0:
                                nValorBaseSalud = annual_parameters.top_twenty_five_smmlv if nValorBaseSalud >= annual_parameters.top_twenty_five_smmlv else nValorBaseSalud
                                if bEsAprendiz == False:
                                    nPorcAporteSaludEmpleado = annual_parameters.value_porc_health_employee
                                    nValorSaludEmpleado = nValorBaseSalud*(nPorcAporteSaludEmpleado/100) if nDiasLicencia==0 else 0
                                else:
                                    nValorSaludEmpleado = 0
                                if not employee.company_id.exonerated_law_1607 or (employee.company_id.exonerated_law_1607 and (nValorBaseSalud >= (annual_parameters.smmlv_monthly*10) or dict_social_security['BaseSeguridadSocial'].dict.get('TOTAL',0) >= (annual_parameters.smmlv_monthly*10))) or bEsAprendiz == True:
                                    nPorcAporteSaludEmpresa = annual_parameters.value_porc_health_company if not bEsAprendiz else annual_parameters.value_porc_health_employee+annual_parameters.value_porc_health_company
                                    nValorSaludEmpresa = nValorBaseSalud*(nPorcAporteSaludEmpresa/100)
                                else:
                                    nPorcAporteSaludEmpresa,nValorSaludEmpresa = 0,0
                                nValorSaludTotal += (nValorSaludEmpleado+nValorSaludEmpresa)
                                nValorSaludTotalEmpleado += nValorSaludEmpleado
                                nValorSaludTotalEmpresa += nValorSaludEmpresa
                        else:
                            nValorBaseSalud = 0
                        #----------------CALCULOS PENSION
                        if bEsAprendiz == False and employee.subtipo_coti_id.not_contribute_pension == False and (obj_parameterization_contributors.liquidate_employee_pension or obj_parameterization_contributors.liquidated_company_pension or obj_parameterization_contributors.liquidates_solidarity_fund):
                            if nValorBaseFondoPension == 0:
                                nValorBaseFondoPension = float(roundupdecimal(valor_base_sueldo))
                            else:
                                nValorBaseFondoPension = float(roundupdecimal(valor_base_sueldo) if abs((valor_base_sueldo) - nValorBaseFondoPension) < nRedondeoDecimalesDif else roundupdecimal(nValorBaseFondoPension))
                            #nValorBaseFondoPension = (valor_base_sueldo) if nValorBaseFondoPension == 0 else (nValorBaseFondoPension)
                            if nValorBaseFondoPension > 0:
                                nValorBaseFondoPensionTotal = dict_social_security['BaseSeguridadSocial'].dict.get('TOTAL', 0)  # BASEnValorBaseFondoPensionTotal = dict_social_security['BaseSeguridadSocial'].dict.get('TOTAL', 0) #BASE
                                if contract_id.modality_salary == 'integral':
                                    porc_integral_salary = annual_parameters.porc_integral_salary / 100
                                    nValorBaseFondoPensionTotal = nValorBaseFondoPensionTotal * porc_integral_salary
                                    nValorBaseFondoPensionTotal = annual_parameters.top_twenty_five_smmlv if nValorBaseFondoPensionTotal >= annual_parameters.top_twenty_five_smmlv else nValorBaseFondoPensionTotal
                                    nValorBaseFondoPension = annual_parameters.top_twenty_five_smmlv if nValorBaseFondoPension >= annual_parameters.top_twenty_five_smmlv else nValorBaseFondoPension
                                else:
                                    nValorBaseFondoPensionTotal = annual_parameters.top_twenty_five_smmlv if nValorBaseFondoPensionTotal >= annual_parameters.top_twenty_five_smmlv else nValorBaseFondoPensionTotal
                                    nValorBaseFondoPension = annual_parameters.top_twenty_five_smmlv if nValorBaseFondoPension >= annual_parameters.top_twenty_five_smmlv else nValorBaseFondoPension
                                nPorcAportePensionEmpleado = annual_parameters.value_porc_pension_employee if executing.nDiasLicencia == 0 else 0
                                nPorcAportePensionEmpresa = annual_parameters.value_porc_pension_company if executing.nDiasLicencia == 0 else annual_parameters.value_porc_pension_company + annual_parameters.value_porc_pension_employee
                                nValorPensionEmpleado = nValorBaseFondoPension*(nPorcAportePensionEmpleado/100) if nDiasLicencia==0 else 0
                                nValorPensionEmpresa = nValorBaseFondoPension*(nPorcAportePensionEmpresa/100)
                                nValorPensionTotal += (nValorPensionEmpleado+nValorPensionEmpresa)
                                nValorPensioTotalEmpleado += nValorPensionEmpleado
                                nValorPensionTotalEmpresa += nValorPensionEmpresa
                                #Calculos fondo solidaridad
                                if (nValorBaseFondoPensionTotal/annual_parameters.smmlv_monthly) >= 4 and (nValorBaseFondoPensionTotal/annual_parameters.smmlv_monthly) < 16:
                                    nPorcFondoSolidaridad = 1
                                if  (nValorBaseFondoPensionTotal/annual_parameters.smmlv_monthly) >= 16 and (nValorBaseFondoPensionTotal/annual_parameters.smmlv_monthly) <= 17:
                                    nPorcFondoSolidaridad = 1.2
                                if  (nValorBaseFondoPensionTotal/annual_parameters.smmlv_monthly) > 17 and (nValorBaseFondoPensionTotal/annual_parameters.smmlv_monthly) <= 18:
                                    nPorcFondoSolidaridad = 1.4
                                if  (nValorBaseFondoPensionTotal/annual_parameters.smmlv_monthly) > 18 and (nValorBaseFondoPensionTotal/annual_parameters.smmlv_monthly) <= 19:
                                    nPorcFondoSolidaridad = 1.6
                                if  (nValorBaseFondoPensionTotal/annual_parameters.smmlv_monthly) > 19 and (nValorBaseFondoPensionTotal/annual_parameters.smmlv_monthly) <= 20:
                                    nPorcFondoSolidaridad = 1.8
                                if  (nValorBaseFondoPensionTotal/annual_parameters.smmlv_monthly) > 20:
                                    nPorcFondoSolidaridad = 2
                                if nPorcFondoSolidaridad > 0:
                                    if contract_id.modality_salary == 'integral' and nPorcFondoSolidaridad == 2:
                                        nValorFondoSolidaridad = roundup100(nValorBaseFondoPension * 0.005)
                                        nValorFondoSubsistencia = roundup100(nValorBaseFondoPension * 0.015)
                                        nValorTotalFondos += (nValorFondoSolidaridad + nValorFondoSubsistencia)
                                    else:
                                        nPorcFondoSolidaridadCalculo = (nPorcFondoSolidaridad/100)-0.005
                                        nValorFondoSolidaridad = roundup100(nValorBaseFondoPension*0.005)
                                        nValorFondoSubsistencia = roundup100(nValorBaseFondoPension*nPorcFondoSolidaridadCalculo)
                                        nValorTotalFondos += (nValorFondoSolidaridad + nValorFondoSubsistencia)
                        else:
                            nValorBaseFondoPension = 0
                        #----------------CALCULOS ARP
                        if obj_parameterization_contributors.liquidated_arl:
                            if nValorBaseARP == 0:
                                nValorBaseARP = float(roundupdecimal(valor_base_sueldo))
                            else:
                                nValorBaseARP = float(roundupdecimal(valor_base_sueldo) if abs((valor_base_sueldo) - nValorBaseARP) < nRedondeoDecimalesDif else roundupdecimal(nValorBaseARP))
                            #nValorBaseARP = (valor_base_sueldo) if nValorBaseARP == 0 else (nValorBaseARP)
                            nValorBaseARP = annual_parameters.top_twenty_five_smmlv if nValorBaseARP >= annual_parameters.top_twenty_five_smmlv else nValorBaseARP
                            if nValorBaseARP > 0 and nDiasAusencias == 0 and nDiasVacaciones == 0:
                                nValorARP = roundup100(nValorBaseARP * nPorcAporteARP / 100)
                        else:
                            nValorBaseARP = 0
                        #----------------CALCULOS CAJA DE COMPENSACIÓN
                        if bEsAprendiz == False and obj_parameterization_contributors.liquidated_compensation_fund:
                            if nValorBaseCajaCom == 0:
                                nValorBaseCajaCom = float(roundupdecimal(valor_base_sueldo))
                            else:
                                nValorBaseCajaCom = float(roundupdecimal(valor_base_sueldo) if abs((valor_base_sueldo) - nValorBaseCajaCom) < nRedondeoDecimalesDif else roundupdecimal(nValorBaseCajaCom))
                            #nValorBaseCajaCom = (valor_base_sueldo) if nValorBaseCajaCom == 0 else (nValorBaseCajaCom)
                            if nValorBaseCajaCom > 0 and nDiasAusencias-executing.nDiasLicenciaRenumerada == 0:
                                nPorcAporteCajaCom = annual_parameters.value_porc_compensation_box_company
                                nValorCajaCom = roundup100(nValorBaseCajaCom * nPorcAporteCajaCom / 100)
                        else:
                            nValorBaseCajaCom = 0
                        #----------------CALCULOS SENA & ICBF
                        if bEsAprendiz == False and obj_parameterization_contributors.liquidated_sena and obj_parameterization_contributors.liquidated_icbf:
                            if nValorBaseSENA == 0:
                                nValorBaseSENA = float(roundupdecimal(valor_base_sueldo))
                            else:
                                nValorBaseSENA = float(roundupdecimal(valor_base_sueldo) if abs((valor_base_sueldo) - nValorBaseSENA) < nRedondeoDecimalesDif else roundupdecimal(nValorBaseSENA))
                            #nValorBaseSENA = ((executing.nValorBaseSENA / 30) * nDias) if nValorBaseSENA == 0 else (nValorBaseSENA)
                            if nValorBaseICBF == 0:
                                nValorBaseICBF = float(roundupdecimal(valor_base_sueldo))
                            else:
                                nValorBaseICBF = float(roundupdecimal(valor_base_sueldo) if abs((valor_base_sueldo) - nValorBaseICBF) < nRedondeoDecimalesDif else roundupdecimal(nValorBaseICBF))
                            #nValorBaseICBF = ((executing.nValorBaseICBF / 30) * nDias) if nValorBaseICBF == 0 else (nValorBaseICBF)
                            if not employee.company_id.exonerated_law_1607 or (employee.company_id.exonerated_law_1607 and (nValorBaseSENA >= (annual_parameters.smmlv_monthly*10) or dict_social_security['BaseParafiscales'].dict.get('TOTAL',0) >= (annual_parameters.smmlv_monthly*10))):
                                if nValorBaseSENA > 0 and nDiasAusencias == 0:
                                    nPorcAporteSENA = annual_parameters.value_porc_sena_company
                                    nValorSENA = roundup100(nValorBaseSENA * nPorcAporteSENA / 100)
                                if nValorBaseICBF > 0 and nDiasAusencias == 0:
                                    nPorcAporteICBF = annual_parameters.value_porc_icbf_company
                                    nValorICBF = roundup100(nValorBaseICBF * nPorcAporteICBF / 100)
                            else:
                                nValorBaseSENA,nValorBaseICBF = 0,0
                                nPorcAporteSENA,nValorSENA = 0,0
                                nPorcAporteICBF,nValorICBF = 0,0
                        else:
                            nValorBaseSENA,nValorBaseICBF = 0,0

                        result_update = {
                            #Ingreso o Retiro / Se marca la novedad en la segunda linea cuando los dias liquidados son 0
                            'nIngreso': nIngreso if nDiasLiquidados == 0 and executing.nDiasLiquidados == 0 and item == 2 else executing.nIngreso,
                            'nRetiro': nRetiro  if nDiasLiquidados == 0 and executing.nDiasLiquidados == 0 and item == 2 else executing.nRetiro,
                            #Salud
                            'nValorBaseSalud':nValorBaseSalud,
                            'nPorcAporteSaludEmpleado': nPorcAporteSaludEmpleado if nValorSaludEmpleado > 0 else 0,
                            'nValorSaludEmpleado':nValorSaludEmpleado,
                            'nPorcAporteSaludEmpresa':nPorcAporteSaludEmpresa if nValorSaludEmpresa > 0 else 0,
                            'nValorSaludEmpresa':nValorSaludEmpresa,
                            'nValorSaludEmpleadoNomina': 0,
                            #Pension
                            'nValorBaseFondoPension':nValorBaseFondoPension,
                            'nPorcAportePensionEmpleado': nPorcAportePensionEmpleado if nValorPensionEmpleado > 0 else 0,
                            'nValorPensionEmpleado':nValorPensionEmpleado,
                            'nPorcAportePensionEmpresa': nPorcAportePensionEmpresa if nValorPensionEmpresa > 0 else 0,
                            'nValorPensionEmpresa':nValorPensionEmpresa,
                            'nValorPensionEmpleadoNomina': 0,
                            'cAVP': False if nDiasLiquidados == 0 and executing.nDiasLiquidados == 0 else executing.cAVP,
                            'nAporteVoluntarioPension': 0 if nDiasLiquidados == 0 and executing.nDiasLiquidados == 0 else executing.nAporteVoluntarioPension,
                            #Fondo Solidaridad y Subsistencia
                            'nPorcFondoSolidaridad': nPorcFondoSolidaridad,
                            'nValorFondoSolidaridad':nValorFondoSolidaridad,
                            'nValorFondoSubsistencia':nValorFondoSubsistencia,
                            #ARP/ARL - Administradora de riesgos profesionales/laborales
                            'nValorBaseARP':nValorBaseARP,
                            'nPorcAporteARP':nPorcAporteARP if nValorARP > 0 else 0,
                            'nValorARP':nValorARP,
                            #Caja de Compensación
                            'nValorBaseCajaCom':nValorBaseCajaCom,
                            'nPorcAporteCajaCom':nPorcAporteCajaCom if nValorCajaCom > 0 else 0,
                            'nValorCajaCom':nValorCajaCom,
                            #SENA & ICBF
                            'cExonerado1607': executing.cExonerado1607 if nValorBaseSalud < (annual_parameters.smmlv_monthly * 10) else False,
                            'nValorBaseSENA':nValorBaseSENA,
                            'nPorcAporteSENA':nPorcAporteSENA if nValorSENA > 0 else 0,
                            'nValorSENA':nValorSENA,
                            'nValorBaseICBF':nValorBaseICBF,
                            'nPorcAporteICBF':nPorcAporteICBF if nValorICBF > 0 else 0,
                            'nValorICBF':nValorICBF,
                        }

                        if item == cant_items:
                            result_update['nValorSaludTotal'] = roundup100(nValorSaludTotal)
                            result_update['nValorPensionTotal'] = roundup100(nValorPensionTotal)
                            result_update['nValorSaludEmpleadoNomina'] = executing.nValorSaludEmpleadoNomina
                            result_update['nValorPensionEmpleadoNomina'] = executing.nValorPensionEmpleadoNomina
                            result_update['nDiferenciaSalud'] = (roundup100(nValorSaludTotal) - (nValorSaludTotalEmpleado+nValorSaludTotalEmpresa)) + (nValorSaludTotalEmpleado-executing.nValorSaludEmpleadoNomina)
                            result_update['nDiferenciaPension'] = (roundup100(nValorPensionTotal) - (nValorPensioTotalEmpleado+nValorPensionTotalEmpresa)) + ((nValorPensioTotalEmpleado+nValorTotalFondos)-executing.nValorPensionEmpleadoNomina)

                        executing.write(result_update)

                        if executing.nDiasLiquidados == 0 and executing.nDiasIncapacidadEPS == 0 and executing.nDiasLicencia == 0 and executing.nDiasLicenciaRenumerada == 0 and executing.nDiasMaternidad == 0 and executing.nDiasVacaciones == 0 and executing.nDiasIncapacidadARP == 0:
                            executing.unlink()

                        item += 1
                elif cant_payslip > 0 and employee.tipo_coti_id.code == '51': # Proceso para el tipo de cotizante 51 - Trabajador de Tiempo Parcial:
                    # Guardar linea principal
                    result = {
                        'executing_social_security_id': self.id,
                        'employee_id': employee.id,
                        'contract_id': contract_id.id,
                        'analytic_account_id': analytic_account_id.id,
                        'branch_id': employee.branch_id.id,
                        'nDiasLiquidados': nDiasLiquidados,
                        'nNumeroHorasLaboradas': nNumeroHorasLaboradas,
                        'nIngreso': nIngreso,
                        'nRetiro': nRetiro,
                        'nSueldo': nSueldo,
                        # Salud
                        'TerceroEPS': TerceroEPS.id if TerceroEPS else False,
                        'nValorBaseSalud': nValorBaseSalud,
                        'nValorSaludEmpleadoNomina': nValorSaludEmpleadoNomina,
                        # Pension
                        'TerceroPension': TerceroPension.id if TerceroPension else False,
                        'nValorBaseFondoPension': nValorBaseFondoPension,
                        'nValorPensionEmpleadoNomina': nValorPensionEmpleadoNomina + nValorFondoSubsistencia + nValorFondoSolidaridad,
                        # Fondo Solidaridad y Subsistencia
                        'TerceroFondoSolidaridad': TerceroFondoSolidaridad.id if TerceroFondoSolidaridad else TerceroPension.id if TerceroPension else False,
                        # ARP/ARL - Administradora de riesgos profesionales/laborales
                        'TerceroARP': TerceroARP.id if TerceroARP else False,
                        'nValorBaseARP': nValorBaseARP,
                        # Caja de Compensación
                        'TerceroCajaCom': TerceroCajaCompensacion.id if TerceroCajaCompensacion else False,
                        'nValorBaseCajaCom': nValorBaseCajaCom,
                        # SENA & ICBF
                        'cExonerado1607': employee.company_id.exonerated_law_1607 if bEsAprendiz == False and nSueldo < (
                                    annual_parameters.smmlv_monthly * 10) else False,
                        'TerceroSENA': TerceroSENA.id if TerceroSENA else False,
                        'nValorBaseSENA': nValorBaseSENA,
                        'TerceroICBF': TerceroICBF.id if TerceroICBF else False,
                        'nValorBaseICBF': nValorBaseICBF,
                    }
                    # Una vez creada la linea principal, se obtienen las ausencias con sus respectivas fechas
                    nDiasIncapacidadEPS,nDiasLicencia,nDiasLicenciaRenumerada,nDiasMaternidad,nDiasVacaciones,nDiasIncapacidadARP = 0,0,0,0,0,0
                    for leave in leave_list:
                        # Incapacidad EPS
                        nDiasIncapacidadEPS = nDiasIncapacidadEPS+leave['days'] if leave['type'] in ('EGA', 'EGH') else nDiasIncapacidadEPS  # Categoria: INCAPACIDAD
                        dict_social_security['Dias'].dict['nDiasIncapacidadEPS'] = nDiasIncapacidadEPS
                        result['nDiasIncapacidadEPS'] = nDiasIncapacidadEPS
                        result['dFechaInicioIGE'] = leave['date_start'] if leave['type'] in ('EGA', 'EGH') else result.get('dFechaInicioIGE', False)
                        result['dFechaFinIGE'] = leave['date_end'] if leave['type'] in ('EGA', 'EGH') else result.get('dFechaFinIGE', False)
                        # Licencia
                        nDiasLicencia = nDiasLicencia+leave['days'] if leave['type'] in ('LICENCIA_NO_REMUNERADA', 'INAS_INJU', 'SANCION','SUSP_CONTRATO','DNR') else nDiasLicencia # Categoria: LICENCIA_NO_REMUNERADA
                        dict_social_security['Dias'].dict['nDiasLicencia'] = nDiasLicencia
                        result['nDiasLicencia'] = nDiasLicencia
                        result['dFechaInicioSLN'] = leave['date_start'] if leave['type'] in ('LICENCIA_NO_REMUNERADA', 'INAS_INJU', 'SANCION', 'SUSP_CONTRATO','DNR') else result.get('dFechaInicioSLN', False)
                        result['dFechaFinSLN'] = leave['date_end'] if leave['type'] in ('LICENCIA_NO_REMUNERADA', 'INAS_INJU', 'SANCION', 'SUSP_CONTRATO','DNR') else result.get('dFechaFinSLN', False)
                        # Licencia Remunerada
                        nDiasLicenciaRenumerada = nDiasLicenciaRenumerada+leave['days'] if leave['type'] in ('LICENCIA_REMUNERADA', 'LUTO','REP_VACACIONES') else nDiasLicenciaRenumerada  # Categoria: LICENCIA_REMUNERADA
                        dict_social_security['Dias'].dict['nDiasLicenciaRenumerada'] = nDiasLicenciaRenumerada
                        result['nDiasLicenciaRenumerada'] = nDiasLicenciaRenumerada
                        result['dFechaInicioVACLR'] = leave['date_start'] if leave['type'] in ('LICENCIA_REMUNERADA', 'LUTO', 'VACDISFRUTADAS', 'REP_VACACIONES') else result.get('dFechaInicioVACLR', False)
                        result['dFechaFinVACLR'] = leave['date_end'] if leave['type'] in ('LICENCIA_REMUNERADA', 'LUTO', 'VACDISFRUTADAS', 'REP_VACACIONES') else result.get('dFechaFinVACLR', False)
                        # Maternida
                        nDiasMaternidad = nDiasMaternidad+leave['days'] if leave['type'] in ('MAT', 'PAT') else nDiasMaternidad # Categoria: LICENCIA_MATERNIDAD
                        dict_social_security['Dias'].dict['nDiasMaternidad'] = nDiasMaternidad
                        result['nDiasMaternidad'] = nDiasMaternidad
                        result['dFechaInicioLMA'] = leave['date_start'] if leave['type'] in ('MAT', 'PAT') else result.get('dFechaInicioLMA', False)
                        result['dFechaFinLMA'] = leave['date_end'] if leave['type'] in ('MAT', 'PAT') else result.get('dFechaFinLMA', False)
                        # Vacaciones
                        nDiasVacaciones = nDiasVacaciones+leave['days'] if leave['type'] == 'VACDISFRUTADAS' else nDiasVacaciones  # Categoria: VACACIONES
                        dict_social_security['Dias'].dict['nDiasVacaciones'] = nDiasVacaciones
                        result['nDiasVacaciones'] = nDiasVacaciones
                        result['dFechaInicioVACLR'] = leave['date_start'] if leave['type'] in ('LICENCIA_REMUNERADA', 'LUTO', 'VACDISFRUTADAS', 'REP_VACACIONES') else result.get('dFechaInicioVACLR', False)
                        result['dFechaFinVACLR'] = leave['date_end'] if leave['type'] in ('LICENCIA_REMUNERADA', 'LUTO', 'VACDISFRUTADAS', 'REP_VACACIONES') else result.get('dFechaFinVACLR', False)
                        # ARL
                        nDiasIncapacidadARP = nDiasIncapacidadARP+leave['days'] if leave['type'] in ('EP', 'AT') else nDiasIncapacidadARP # Categoria: ACCIDENTE_TRABAJO
                        dict_social_security['Dias'].dict['nDiasIncapacidadARP'] = nDiasIncapacidadARP
                        result['nDiasIncapacidadARP'] = nDiasIncapacidadARP
                        result['dFechaInicioIRL'] = leave['date_start'] if leave['type'] in ('EP', 'AT') else result.get('dFechaInicioIRL', False)
                        result['dFechaFinIRL'] = leave['date_end'] if leave['type'] in ('EP', 'AT') else result.get('dFechaFinIRL', False)

                    obj_executing = env['hr.account.executing.social.security'].create(result)

                    # Valores TOTALES
                    nValorSaludTotalEmpleado, nValorSaludTotalEmpresa = 0, 0
                    nValorPensioTotalEmpleado, nValorPensionTotalEmpresa, nValorTotalFondos = 0, 0, 0
                    nValorSaludTotal, nValorPensionTotal = 0, 0
                    nRedondeoDecimalesDif = 5  # Max diferencia de decimales
                    for executing in obj_executing:
                        # Valores
                        nPorcAporteSaludEmpleado, nPorcAporteSaludEmpresa, nValorBaseSalud, nValorSaludEmpleado, nValorSaludEmpresa = 0, 0, 0, 0, 0
                        nPorcAportePensionEmpleado, nPorcAportePensionEmpresa, nValorBaseFondoPension, nValorPensionEmpleado, nValorPensionEmpresa = 0, 0, 0, 0, 0
                        nPorcFondoSolidaridad, nValorFondoSolidaridad, nValorFondoSubsistencia = 0, 0, 0
                        nValorBaseARP, nValorARP = 0, 0
                        nValorBaseCajaCom, nPorcAporteCajaCom, nValorCajaCom = 0, 0, 0
                        nValorBaseSENA, nPorcAporteSENA, nValorSENA = 0, 0, 0
                        nValorBaseICBF, nPorcAporteICBF, nValorICBF = 0, 0, 0
                        # Dias
                        nDiasLicencia = executing.nDiasLicencia
                        nDiasVacaciones = executing.nDiasVacaciones
                        nDiasAusencias = executing.nDiasIncapacidadEPS + executing.nDiasLicencia + executing.nDiasLicenciaRenumerada + executing.nDiasMaternidad + executing.nDiasIncapacidadARP
                        nDias = executing.nDiasLiquidados + executing.nDiasIncapacidadEPS + executing.nDiasLicencia + executing.nDiasLicenciaRenumerada + executing.nDiasMaternidad + executing.nDiasVacaciones + executing.nDiasIncapacidadARP

                        obj_overtime = env['hr.overtime'].search(
                            [('employee_id', '=', employee.id), ('date', '>=', date_start),
                             ('date_end', '<=', date_end)])
                        if len(obj_overtime) > 0:
                            nDias = round(sum(o.days_actually_worked for o in obj_overtime))#round(sum(o.shift_hours for o in obj_overtime)/8)
                            nNumeroHorasLaboradas = round(sum(o.days_actually_worked for o in obj_overtime)*8) #round(sum(o.shift_hours for o in obj_overtime))
                        # Calculos valores base dependiendo los días
                        if nDias > 0:
                            #Documentación - http://aportesenlinea.custhelp.com/app/answers/detail/a_id/464/~/condiciones-cotizante-51
                            nValorBaseSalud = 0
                            nValorBaseFondoPension = 0
                            nValorBaseARP = annual_parameters.smmlv_monthly  # "IBC Riesgos Laborales" debe ser igual a un salario mínimo legal mensual vigente.
                            nValorBaseCajaCom = 0
                            nValorBaseSENA = 0
                            nValorBaseICBF = 0
                            nValorBaseFondoPension = employee.tipo_coti_id.get_value_cotizante_51(date_start.year,nDias)
                            nValorBaseCajaCom = employee.tipo_coti_id.get_value_cotizante_51(date_start.year,nDias)
                            # ----------------CALCULOS SALUD
                            if nValorBaseSalud > 0:
                                if bEsAprendiz == False:
                                    nPorcAporteSaludEmpleado = annual_parameters.value_porc_health_employee
                                    nValorSaludEmpleado = nValorBaseSalud * (nPorcAporteSaludEmpleado / 100)
                                else:
                                    nValorSaludEmpleado = 0
                                if not employee.company_id.exonerated_law_1607 or (employee.company_id.exonerated_law_1607 and nValorBaseSalud >= (annual_parameters.smmlv_monthly * 10)) or bEsAprendiz == True:
                                    nPorcAporteSaludEmpresa = annual_parameters.value_porc_health_company if not bEsAprendiz else annual_parameters.value_porc_health_employee + annual_parameters.value_porc_health_company
                                    nValorSaludEmpresa = nValorBaseSalud * (nPorcAporteSaludEmpresa / 100)
                                else:
                                    nPorcAporteSaludEmpresa, nValorSaludEmpresa = 0, 0
                                nValorSaludTotal += (nValorSaludEmpleado + nValorSaludEmpresa)
                                nValorSaludTotalEmpleado += nValorSaludEmpleado
                                nValorSaludTotalEmpresa += nValorSaludEmpresa
                            # ----------------CALCULOS PENSION
                            if bEsAprendiz == False and employee.subtipo_coti_id.not_contribute_pension == False:
                                if nValorBaseFondoPension > 0:
                                    nPorcAportePensionEmpleado = annual_parameters.value_porc_pension_employee
                                    nPorcAportePensionEmpresa = annual_parameters.value_porc_pension_company
                                    nValorPensionEmpleado = nValorBaseFondoPension * (nPorcAportePensionEmpleado / 100)
                                    nValorPensionEmpresa = nValorBaseFondoPension * (nPorcAportePensionEmpresa / 100)
                                    nValorPensionTotal += (nValorPensionEmpleado + nValorPensionEmpresa)
                                    nValorPensioTotalEmpleado += nValorPensionEmpleado
                                    nValorPensionTotalEmpresa += nValorPensionEmpresa
                            else:
                                nValorBaseFondoPension = 0
                            # ----------------CALCULOS ARP
                            if nValorBaseARP > 0:
                                nValorARP = roundup100(nValorBaseARP * nPorcAporteARP / 100)
                            # ----------------CALCULOS CAJA DE COMPENSACIÓN
                            if bEsAprendiz == False:
                                if nValorBaseCajaCom > 0:
                                    nPorcAporteCajaCom = annual_parameters.value_porc_compensation_box_company
                                    nValorCajaCom = roundup100(nValorBaseCajaCom * nPorcAporteCajaCom / 100)
                            else:
                                nValorBaseCajaCom = 0
                            # ----------------CALCULOS SENA & ICBF
                            if bEsAprendiz == False:
                                if not employee.company_id.exonerated_law_1607 or (
                                        employee.company_id.exonerated_law_1607 and nValorBaseSENA >= (
                                        annual_parameters.smmlv_monthly * 10)):
                                    if nValorBaseSENA > 0:
                                        nPorcAporteSENA = annual_parameters.value_porc_sena_company
                                        nValorSENA = roundup100(nValorBaseSENA * nPorcAporteSENA / 100)
                                    if nValorBaseICBF > 0:
                                        nPorcAporteICBF = annual_parameters.value_porc_icbf_company
                                        nValorICBF = roundup100(nValorBaseICBF * nPorcAporteICBF / 100)
                                else:
                                    nValorBaseSENA, nValorBaseICBF = 0, 0
                                    nPorcAporteSENA, nValorSENA = 0, 0
                                    nPorcAporteICBF, nValorICBF = 0, 0
                            else:
                                nValorBaseSENA, nValorBaseICBF = 0, 0

                        result_update = {
                            'nDiasLiquidados': nDias,
                            'nNumeroHorasLaboradas': nNumeroHorasLaboradas,
                            # Salud
                            'nValorBaseSalud': nValorBaseSalud,
                            'nPorcAporteSaludEmpleado': nPorcAporteSaludEmpleado if nValorSaludEmpleado > 0 else 0,
                            'nValorSaludEmpleado': nValorSaludEmpleado,
                            'nPorcAporteSaludEmpresa': nPorcAporteSaludEmpresa if nValorSaludEmpresa > 0 else 0,
                            'nValorSaludEmpresa': nValorSaludEmpresa,
                            # Pension
                            'nValorBaseFondoPension': nValorBaseFondoPension,
                            'nPorcAportePensionEmpleado': nPorcAportePensionEmpleado if nValorPensionEmpleado > 0 else 0,
                            'nValorPensionEmpleado': nValorPensionEmpleado,
                            'nPorcAportePensionEmpresa': nPorcAportePensionEmpresa if nValorPensionEmpresa > 0 else 0,
                            'nValorPensionEmpresa': nValorPensionEmpresa,
                            # Fondo Solidaridad y Subsistencia
                            'nPorcFondoSolidaridad': nPorcFondoSolidaridad,
                            'nValorFondoSolidaridad': nValorFondoSolidaridad,
                            'nValorFondoSubsistencia': nValorFondoSubsistencia,
                            # ARP/ARL - Administradora de riesgos profesionales/laborales
                            'nValorBaseARP': nValorBaseARP,
                            'nPorcAporteARP': nPorcAporteARP if nValorARP > 0 else 0,
                            'nValorARP': nValorARP,
                            # Caja de Compensación
                            'nValorBaseCajaCom': nValorBaseCajaCom,
                            'nPorcAporteCajaCom': nPorcAporteCajaCom if nValorCajaCom > 0 else 0,
                            'nValorCajaCom': nValorCajaCom,
                            # SENA & ICBF
                            'nValorBaseSENA': nValorBaseSENA,
                            'nPorcAporteSENA': nPorcAporteSENA if nValorSENA > 0 else 0,
                            'nValorSENA': nValorSENA,
                            'nValorBaseICBF': nValorBaseICBF,
                            'nPorcAporteICBF': nPorcAporteICBF if nValorICBF > 0 else 0,
                            'nValorICBF': nValorICBF,
                        }

                        result_update['nValorSaludTotal'] = roundup100(nValorSaludTotal)
                        result_update['nValorPensionTotal'] = roundup100(nValorPensionTotal)
                        result_update['nValorSaludEmpleadoNomina'] = executing.nValorSaludEmpleadoNomina
                        result_update['nValorPensionEmpleadoNomina'] = executing.nValorPensionEmpleadoNomina
                        result_update['nDiferenciaSalud'] = (roundup100(nValorSaludTotal) - (nValorSaludTotalEmpleado + nValorSaludTotalEmpresa)) + (nValorSaludTotalEmpleado - executing.nValorSaludEmpleadoNomina)
                        result_update['nDiferenciaPension'] = (roundup100(nValorPensionTotal) - (nValorPensioTotalEmpleado + nValorPensionTotalEmpresa)) + ((nValorPensioTotalEmpleado + nValorTotalFondos) - executing.nValorPensionEmpleadoNomina)
                        executing.write(result_update)


    def executing_social_security(self,employee_id=0):
        #Eliminar ejecución
        if employee_id == 0:
            self.env['hr.account.executing.social.security'].search([('executing_social_security_id','=',self.id)]).unlink()
        else:
            self.env['hr.account.executing.social.security'].search([('executing_social_security_id', '=', self.id),('employee_id','=',employee_id)]).unlink()
        #Obtener fechas del periodo seleccionado
        try:            
            date_start = self.date_start
            date_end = self.date_end
        except:
            raise UserError(_('El año digitado es invalido, por favor verificar.'))

        #Obtener empleados que tuvieron liquidaciones en el mes
        if employee_id == 0:
            query = '''
                select distinct b.id 
                from hr_payslip a 
                inner join hr_employee b on a.employee_id = b.id
                where a.state = 'done' and a.company_id = %s and ((a.date_from >= '%s' and a.date_from <= '%s') or (a.date_to >= '%s' and a.date_to <= '%s'))
            ''' % (self.company_id.id,date_start,date_end,date_start,date_end)
        else:
            query = '''
                select distinct b.id 
                from hr_payslip a 
                inner join hr_employee b on a.employee_id = b.id and b.id = %s
                where a.state = 'done' and a.company_id = %s and ((a.date_from >= '%s' and a.date_from <= '%s') or (a.date_to >= '%s' and a.date_to <= '%s'))
            ''' % (employee_id,self.company_id.id, date_start, date_end, date_start, date_end)

        self.env.cr.execute(query)
        result_query = self.env.cr.fetchall()

        employee_ids = []
        for result in result_query:
            employee_ids.append(result)
        obj_employee = self.env['hr.employee'].search([('id', 'in', employee_ids),('analytic_account_id','=', self.analytic_account_id.id)])
        
        #Guardo los empleados en lotes de a 20
        employee_array, i, j = [], 0 , 20            
        while i <= len(obj_employee):                
            employee_array.append(obj_employee[i:j])
            i = j
            j += 20   

        #Los lotes anteriores, los separo en los de 5, para ejecutar un maximo de 5 hilos
        employee_array_def, i, j = [], 0 , 5            
        while i <= len(employee_array):                
            employee_array_def.append(employee_array[i:j])
            i = j
            j += 5  

        #----------------------------Recorrer multihilos
        i = 1
        for employee in employee_array_def:
            for emp in employee:
                self.executing_social_security_thread(date_start,date_end,emp,)                
                i += 1   


    def compute_concepts_category(self):
        self.invoice_line_ids.filtered(lambda line: line.is_payroll == True).unlink()
        category_mapping = {
            'DEVENGADOS': ['BASIC', 'AUX', 'AUS', 'ALW', 'ACCIDENTE_TRABAJO',  'DEV_SALARIAL',  'HEYREC', 'COMISIONES', 'INCAPACIDAD', 'LICENCIA_MATERNIDAD', 'LICENCIA_REMUNERADA'],
            'DEVENGOS NO SALARIALES':['DEV_NO_SALARIAL'],
            'PRESTACIONES SOCIALES': ['PRESTACIONES_SOCIALES','PRIMA', 'VACACIONES'],
            'PROVISIONES PRESTACIONES SOCIALES': ['PROV'],
            }
        
        categorized_lines = {
            'DEVENGADOS': [],
            'DEVENGOS NO SALARIALES': [],
            'PRESTACIONES SOCIALES': [],
            'PROVISIONES PRESTACIONES SOCIALES': [],
            }
        category_totals = {category: 0.0 for category in category_mapping}
        for payslip_line in self.hr_paylip_ids.line_ids:
            category_found = False
            for category, codes in category_mapping.items():
                if payslip_line.category_id.code in codes or payslip_line.category_id.parent_id.code in codes:
                    category_totals[category] += payslip_line.total
                    category_found = True
                    break

            if not category_found:
                # Considerar cómo manejar las líneas que no coinciden con ninguna categoría
                pass
    def compute_concepts_category(self):
        self.executing_social_security()
        self.invoice_line_ids.filtered(lambda line: line.is_payroll == True).unlink()
        category_mapping = {
            'DEVENGADOS': ['BASIC', 'AUX', 'AUS', 'ALW', 'ACCIDENTE_TRABAJO',  'DEV_SALARIAL',  'HEYREC', 'COMISIONES', 'INCAPACIDAD', 'LICENCIA_MATERNIDAD', 'LICENCIA_REMUNERADA'],
            'DEVENGOS NO SALARIALES':['DEV_NO_SALARIAL'],
            'PRESTACIONES SOCIALES': ['PRESTACIONES_SOCIALES','PRIMA', 'VACACIONES'],
            'PROVISIONES PRESTACIONES SOCIALES': ['PROV'],

            }
        
        categorized_lines = {
            'DEVENGADOS': [],
            'DEVENGOS NO SALARIALES': [],
            'PRESTACIONES SOCIALES': [],
            'PROVISIONES PRESTACIONES SOCIALES': [],
            }
        category_totals = {category: 0.0 for category in category_mapping}
        category_totals['SEGURIDAD SOCIAL'] = 0.0
        category_totals['PARAFISCALES'] = 0.0
        for payslip_line in self.hr_paylip_ids.line_ids:
            category_found = False
            for category, codes in category_mapping.items():
                if payslip_line.category_id.code in codes or payslip_line.category_id.parent_id.code in codes:
                    category_totals[category] += payslip_line.total
                    category_found = True
                    break

            if not category_found:
                # Considerar cómo manejar las líneas que no coinciden con ninguna categoría
                pass
        for security_record in self.executing_social_security_ids:
                category_totals['SEGURIDAD SOCIAL'] += security_record.nValorSaludTotal + security_record.nValorPensionTotal + security_record.nValorFondoSubsistencia + security_record.nValorFondoSolidaridad
                category_totals['PARAFISCALES'] += security_record.nValorARP + security_record.nValorCajaCom + security_record.nValorSENA + security_record.nValorICBF
                
        # Crear líneas de factura con el total por categoría
        for category, total in category_totals.items():
            if total != 0.0:
                invoice_line_vals = {
                    'product_id': self.product_id.id,
                    'name': f'{category}',
                    'quantity': 1,
                    'partner_id':self.partner_id.id,
                    'amount_currency': -total,
                    'price_unit': total,
                    'tax_ids':self.product_id.taxes_id.ids,
                    'exclude_from_invoice_tab': False,
                    'analytic_account_id':self.analytic_account_id.id,
                    'account_id': self.product_id.property_account_income_id.id,  # Reemplazar con la cuenta contable adecuada
                    'move_id': self.id,
                    'is_payroll':True,# Reemplazar con el ID de la factura asociada
                }
                invoice_line = self.env['account.move.line'].create(invoice_line_vals)
                #categorized_lines[category].append(invoice_line.id)
        self.with_context(check_move_validity=False)._onchange_recompute_dynamic_lines()
        self.with_context(check_move_validity=False).calcular_aiu()


    def get_payslip_period(self):
        payslip_ids = self.env['hr.payslip'].search([
            ('employee_id.analytic_account_id','=', self.analytic_account_id.id),
            ('state','=','done'),
            ('date_to','>=', self.date_start),
            ('date_to','<=',self.date_end)
        ])

        if payslip_ids:
            payslip_data = [(4, payslip_id.id) for payslip_id in payslip_ids]
            self.write({'hr_paylip_ids': payslip_data})


    def hr_accounting_public_employees(self):
        for record in self:
            for line in record.line_ids:
                if line.hr_salary_rule_id:
                    if line.hr_salary_rule_id.account_id_cxp:
                        #Obtener regla NETO
                        obj_rule_net = self.env['hr.salary.rule'].search(
                            [('code', '=', 'NET'), ('struct_id', '=', line.hr_struct_id_id.id)], limit=1)
                        line_net = record.line_ids.filtered(lambda x: x.hr_salary_rule_id == obj_rule_net)
                        #Crear nueva linea con el registro de credito para publicos
                        addref_work_address_account_moves = self.env['ir.config_parameter'].sudo().get_param(
                            'lavish_hr_payroll.addref_work_address_account_moves') or False
                        if addref_work_address_account_moves and line.partner_id:
                            if line.partner_id.parent_id:
                                name = f"{line.partner_id.parent_id.vat} {line.partner_id.display_name}|{line.hr_salary_rule_id.name}"
                            else:
                                name = f"{line.partner_id.vat} {line.partner_id.display_name}|{line.hr_salary_rule_id.name}"
                        else:
                            name = line.hr_salary_rule_id.name

                        line_create = {
                            'move_id':record.id,
                            'name': name,
                            'partner_id': line.partner_id.id,
                            'account_id': line.hr_salary_rule_id.account_id_cxp.id,
                            'journal_id': line.journal_id.id,
                            'date': line.date,
                            'debit': line.credit,
                            'credit': line.debit,
                            'analytic_account_id': line.analytic_account_id.id,
                            'hr_salary_rule_id': line.hr_salary_rule_id.id,
                        }
                        if line_net.debit == 0 and line_net.credit > 0:
                            if line.debit > 0:
                                if line_net.credit - line.debit >= 0:
                                    line_update_create = {'credit':line_net.credit - line.debit}
                                else:
                                    line_update_create = {'account_id':line.hr_salary_rule_id.account_id_cxp.id,
                                                          'debit':abs(line_net.credit - line.debit),
                                                          'credit':0}
                            if line.credit > 0:
                                line_update_create = {'credit':line_net.credit + line.credit}
                        else:
                            line_update_create = {'account_id': line.hr_salary_rule_id.account_id_cxp.id,
                                                  'debit': line_net.debit + line.debit,
                                                  'credit': 0}
                        record.write({'line_ids': [(0, 0, line_create),(1, line_net.id, line_update_create)]})
class Hr_payslip(models.Model):
    _inherit = 'hr.payslip'

    # ---------------------------------------CONTABILIZACIÓN DE LA NÓMINA---------------------------------------------#

    # Items contabilidad
    def _prepare_line_values(self, line, account_id, date, debit, credit, analytic_account_id):
        addref_work_address_account_moves = self.env['ir.config_parameter'].sudo().get_param(
            'lavish_hr_payroll.addref_work_address_account_moves') or False
        if addref_work_address_account_moves and line.slip_id.employee_id.address_id:
            if line.slip_id.employee_id.address_id.parent_id:
                name = f"{line.slip_id.employee_id.address_id.parent_id.vat} {line.slip_id.employee_id.address_id.display_name}|{line.name}"
            else:
                name = f"{line.slip_id.employee_id.address_id.vat} {line.slip_id.employee_id.address_id.display_name}|{line.name}"
        else:
            name = line.name

        return {
            'name': name,
            'partner_id': line.partner_id.id,
            'account_id': account_id,
            'journal_id': line.slip_id.struct_id.journal_id.id,
            'date': date,
            'debit': debit,
            'credit': credit,
            'analytic_account_id': analytic_account_id,
            'hr_salary_rule_id': line.salary_rule_id.id,
            'hr_struct_id_id': line.slip_id.struct_id.id,
            'tax_base_amount': sum([i.result_calculation for i in line.slip_id.rtefte_id.deduction_retention.filtered(lambda x: x.concept_deduction_code == 'TOTAL_ING_BASE_O')]) if line.salary_rule_id.code == 'RETFTE001' or line.salary_rule_id.code == 'RETFTE_PRIMA001' else 0,
            # line.salary_rule_id.analytic_account_id.id or line.slip_id.contract_id.analytic_account_id.id,
        }

    # Verificar existencia de items
    def _get_existing_lines(self, line_ids, line, account_id, debit, credit):
        existing_lines = (
            line_id for line_id in line_ids if
            line_id['name'] == line.name
            and line_id['partner_id'] == line.partner_id.id
            and line_id['account_id'] == account_id
            and line_id['analytic_account_id'] == (
                        line.salary_rule_id.analytic_account_id.id or line.slip_id.contract_id.analytic_account_id.id)
            and ((line_id['debit'] > 0 and credit <= 0) or (line_id['credit'] > 0 and debit <= 0)))
        return next(existing_lines, False)

    # # Contabilización de la liquidación de nómina - se sobreescribe el metodo original
  
    def _action_create_account_move(self):
        # lavish - Obtener modalidad de contabilización
        settings_batch_account = self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.module_hr_payroll_batch_account') or False
        precision = self.env['decimal.precision'].precision_get('Payroll')
        # Add payslip without run
        payslips_to_post = self#.filtered(lambda slip: not slip.payslip_run_id)
        # Adding pay slips from a batch and deleting pay slips with a batch that is not ready for validation.
        # A payslip need to have a done state and not an accounting move.
        payslips_to_post = payslips_to_post.filtered(lambda slip: slip.state == 'done' and not slip.move_id)
        # Check that a journal exists on all the structures
        if any(not payslip.struct_id for payslip in payslips_to_post):
            raise ValidationError(_('One of the contract for these payslips has no structure type.'))
        if any(not structure.journal_id for structure in payslips_to_post.mapped('struct_id')):
            raise ValidationError(_('One of the payroll structures has no account journal defined on it.'))
        slip_mapped_data = {
            slip.struct_id.journal_id.id: {fields.Date().end_of(slip.date_to, 'month'): self.env['hr.payslip']} for slip
            in payslips_to_post}
        for slip in payslips_to_post:
            slip_mapped_data[slip.struct_id.journal_id.id][fields.Date().end_of(slip.date_to, 'month')] |= slip
        for journal_id in slip_mapped_data:  # For each journal_id.
            for slip_date in slip_mapped_data[journal_id]:  # For each month.
                line_ids = []
                debit_sum = 0.0
                credit_sum = 0.0
                if slip.struct_id.process in ['vacaciones','contrato']:
                    date = slip.date_from  # slip_date
                else:
                    date = slip.date_to  # slip_date
                move_dict = {
                    'narration': '',
                    'ref': date.strftime('%B %Y'),
                    'journal_id': journal_id,
                    'date': date,
                }
                for slip in slip_mapped_data[journal_id][slip_date]:
                    if len(slip.line_ids) > 0:
                        if settings_batch_account == '1':  # Si en ajustes tiene configurado 'Crear movimiento contable por empleado'
                            # Se limpian los datos para crear un nuevo movimiento
                            line_ids = []
                            debit_sum = 0.0
                            credit_sum = 0.0
                            # date = slip_date
                            move_dict = {
                                'narration': '',
                                'ref': slip.display_name,
                                'journal_id': journal_id,
                                'date': date,
                                'partner_id': slip.employee_id.address_id.id, 
                            }
                        move_dict['narration'] += slip.number or '' + ' - ' + slip.employee_id.name
                        move_dict['narration'] += '\n'
                        print(slip.line_ids.filtered(lambda line: line.category_id and line.salary_rule_id.not_computed_in_net ==False))
                        for line in slip.line_ids.filtered(lambda line: line.category_id and line.salary_rule_id.not_computed_in_net ==False):
                            amount = -line.total if slip.credit_note else line.total
                            if line.code == 'NET':  # Check if the line is the 'Net Salary'.
                                obj_rule_net = self.env['hr.salary.rule'].search([('code', '=', 'NET'), ('struct_id', '=', slip.struct_id.id)], limit=1)
                                if len(obj_rule_net) > 0:
                                    line.write({'salary_rule_id': obj_rule_net.id})
                                for tmp_line in slip.line_ids.filtered(lambda line: line.category_id and line.salary_rule_id.not_computed_in_net ==False):
                                    if tmp_line.salary_rule_id.not_computed_in_net:  # Check if the rule must be computed in the 'Net Salary' or not.
                                        if amount > 0:
                                            amount -= abs(tmp_line.total)
                                        elif amount < 0:
                                            amount += abs(tmp_line.total)
                            if float_is_zero(amount, precision_digits=precision):
                                continue
                            debit_account_id = line.salary_rule_id.account_debit.id
                            credit_account_id = line.salary_rule_id.account_credit.id
                            # Lógica de lavish - Obtener cuenta contable de acuerdo a la parametrización de la regla salarial
                            debit_third_id = line.partner_id.id
                            credit_third_id = line.partner_id.id
                            analytic_account_id = line.employee_id.analytic_account_id.id  # line.salary_rule_id.analytic_account_id.id or line.slip_id.contract_id.analytic_account_id.id
                            for account_rule in line.salary_rule_id.salary_rule_accounting:
                                # Validar ubicación de trabajo
                                bool_work_location = False
                                if account_rule.work_location.id == slip.employee_id.address_id.id or account_rule.work_location.id == False:
                                    bool_work_location = True
                                # Validar compañia
                                bool_company = False
                                if account_rule.company.id == slip.employee_id.company_id.id or account_rule.company.id == False:
                                    bool_company = True
                                # Validar departamento
                                bool_department = False
                                if account_rule.department.id == slip.employee_id.department_id.id or account_rule.department.id == slip.employee_id.department_id.parent_id.id or account_rule.department.id == slip.employee_id.department_id.parent_id.parent_id.id or account_rule.department.id == False:
                                    bool_department = True
                                if bool_department and bool_company and bool_work_location and (account_rule.debit_account or account_rule.credit_account):
                                    debit_account_id = account_rule.debit_account.id
                                    credit_account_id = account_rule.credit_account.id
                                    # Tercero debito
                                    if account_rule.third_debit == 'entidad':
                                        debit_third_id = line.entity_id.partner_id
                                        # Recorrer entidades empleado
                                        for entity in slip.employee_id.social_security_entities:
                                            if entity.contrib_id.type_entities == 'eps' and line.code == 'SSOCIAL001':  # SALUD
                                                debit_third_id = entity.partner_id.partner_id
                                            if entity.contrib_id.type_entities == 'pension' and (
                                                    line.code == 'SSOCIAL002' or line.code == 'SSOCIAL003' or line.code == 'SSOCIAL004'):  # Pension
                                                debit_third_id = entity.partner_id.partner_id
                                            if entity.contrib_id.type_entities == 'subsistencia' and line.code == 'SSOCIAL003':  # Subsistencia
                                                debit_third_id = entity.partner_id.partner_id
                                            if entity.contrib_id.type_entities == 'solidaridad' and line.code == 'SSOCIAL004':  # Solidaridad
                                                debit_third_id = entity.partner_id.partner_id
                                    elif account_rule.third_debit == 'compañia':
                                        debit_third_id = slip.employee_id.company_id.partner_id
                                    elif account_rule.third_debit == 'empleado':
                                        debit_third_id = slip.employee_id.address_home_id
                                    # Tercero credito
                                    if account_rule.third_credit == 'entidad':
                                        credit_third_id = line.entity_id.partner_id
                                        # Recorrer entidades empleado
                                        for entity in slip.employee_id.social_security_entities:
                                            if entity.contrib_id.type_entities == 'eps' and line.code == 'SSOCIAL001':  # SALUD
                                                credit_third_id = entity.partner_id.partner_id
                                            if entity.contrib_id.type_entities == 'pension' and (
                                                    line.code == 'SSOCIAL002' or line.code == 'SSOCIAL003' or line.code == 'SSOCIAL004'):  # Pension
                                                credit_third_id = entity.partner_id.partner_id
                                            if entity.contrib_id.type_entities == 'subsistencia' and line.code == 'SSOCIAL003':  # Subsistencia
                                                credit_third_id = entity.partner_id.partner_id
                                            if entity.contrib_id.type_entities == 'solidaridad' and line.code == 'SSOCIAL004':  # Solidaridad
                                                credit_third_id = entity.partner_id.partner_id
                                    elif account_rule.third_credit == 'compañia':
                                        credit_third_id = slip.employee_id.company_id.partner_id
                                    elif account_rule.third_credit == 'empleado':
                                        credit_third_id = slip.employee_id.address_home_id
                                    # Asignación de Tercero final y Cuenta analitica cuando la cuenta contable inicie por 4,5,6 o 7
                                    if debit_account_id:
                                        analytic_account_id = line.employee_id.analytic_account_id.id if account_rule.debit_account.code[
                                                                                                        0:1] in ['4',
                                                                                                                '5',
                                                                                                                '6',
                                                                                                                '7'] else analytic_account_id
                                    elif credit_account_id:
                                        line.partner_id = credit_third_id
                                        analytic_account_id = line.employee_id.analytic_account_id.id if account_rule.credit_account.code[
                                                                                                        0:1] in ['4',
                                                                                                                '5',
                                                                                                                '6',
                                                                                                                '7'] else analytic_account_id

                                    #break

                            if debit_account_id:
                                debit = amount if amount > 0.0 else 0.0
                                credit = -amount if amount < 0.0 else 0.0
                                existing_debit_lines = (
                                    line_id for line_id in line_ids if
                                    line_id['partner_id'] == debit_third_id.id
                                    and line_id['account_id'] == debit_account_id
                                    and ((line_id['debit'] > 0 and credit <= 0) or (line_id['credit'] > 0 and debit <= 0)))
                                debit_line = next(existing_debit_lines, False)

                                if not debit_line:
                                    debit_line = {
                                        'name': line.name,
                                        'hr_salary_rule_id': line.salary_rule_id.id,
                                        'hr_struct_id_id': line.slip_id.struct_id.id,
                                        'partner_id': debit_third_id.id,
                                        'account_id': debit_account_id,
                                        'journal_id': slip.struct_id.journal_id.id,
                                        'date': date,
                                        'debit': debit,
                                        'credit': credit,
                                        'analytic_account_id': line.salary_rule_id.analytic_account_id.id or slip.contract_id.analytic_account_id.id,
                                        }
                                    line_ids.append(debit_line)
                                else:
                                    line_name_pieces = set(debit_line['name'].split(', '))
                                    line_name_pieces.add(line.name)
                                    debit_line['name'] = ', '.join(line_name_pieces)
                                    debit_line['debit'] += debit
                                    debit_line['credit'] += credit
                            if credit_account_id:
                                credit_line = False 
                                if amount < 0.0 and line.salary_rule_id.dev_or_ded == 'deduccion':
                                    amount = amount * -1
                                debit = -amount if amount < 0.0 else 0.0
                                credit = amount if amount > 0.0 else 0.0
                                existing_credit_line = (
                                    line_id for line_id in line_ids if
                                    # line_id['name'] == line.name,
                                    line_id['partner_id'] == credit_third_id.id
                                    and line_id['account_id'] == credit_account_id
                                    and ((line_id['debit'] > 0 and credit <= 0) or (line_id['credit'] > 0 and debit <= 0))
                                )
                                credit_line = next(existing_credit_line, False)
                                
                                if not credit_line:
                                    credit_line = {
                                        'name': line.name,
                                        'hr_salary_rule_id': line.salary_rule_id.id,
                                        'hr_struct_id_id': line.slip_id.struct_id.id,
                                        'partner_id': credit_third_id.id,
                                        'account_id': credit_account_id,
                                        'journal_id': slip.struct_id.journal_id.id,
                                        'date': date,
                                        'debit': debit,
                                        'credit': credit,
                                        'analytic_account_id': analytic_account_id, 
                                        }
                                    if line.salary_rule_id.code == 'RETFTE001':
                                        tax_ids = False
                                        tax_tag_ids = False
                                        tax_repartition_line_id = False
                                        if line.salary_rule_id.account_tax_id:
                                            tax_repartition_line_id = (
                                                self.env["account.tax.repartition.line"]
                                                .search(
                                                    [
                                                        (
                                                            "invoice_tax_id",
                                                            "=",
                                                            line.salary_rule_id.account_tax_id.id,
                                                        ),
                                                        ("account_id", "=", credit_account_id),
                                                    ]
                                                )
                                                .id
                                            )
                                            tax_ids =  [line.salary_rule_id.account_tax_id.id]
                                            tax_tag_ids = (
                                                self.env["account.tax.repartition.line"]
                                                .search(
                                                    [
                                                        (
                                                            "invoice_tax_id",
                                                            "=",
                                                            line.salary_rule_id.account_tax_id.id,
                                                        ),
                                                        ("repartition_type", "=", "tax"),
                                                        ("account_id", "=", credit_account_id),
                                                    ]
                                                )
                                                .tag_ids
                                            )
                                        base_tax = 0.0
                                        if slip.rtefte_id:
                                            base_tax = sum(x.result_calculation for x in slip.rtefte_id.deduction_retention.filtered(lambda s: s.concept_deduction_code == 'SUBTOTAL_IBR3_O'))
                                        credit_line['tax_line_id'] = line.salary_rule_id.account_tax_id.id or False
                                        credit_line['tax_base_amount'] = base_tax
                                        credit_line['tax_ids'] = tax_ids
                                        credit_line['tax_repartition_line_id'] = tax_repartition_line_id
                                        credit_line['tax_tag_ids'] = tax_tag_ids

                                    line_ids.append(credit_line)
                                else:
                                    line_name_pieces = set(credit_line['name'].split(', '))
                                    line_name_pieces.add(line.name)
                                    credit_line['name'] = ', '.join(line_name_pieces)
                                    credit_line['debit'] += debit
                                    credit_line['credit'] += credit

                        for line_id in line_ids:  # Get the debit and credit sum.
                            debit_sum += line_id['debit']
                            credit_sum += line_id['credit']
                        #Descripción ajuste al peso
                        addref_work_address_account_moves = self.env['ir.config_parameter'].sudo().get_param(
                            'lavish_hr_payroll.addref_work_address_account_moves') or False
                        if addref_work_address_account_moves and slip.employee_id.address_id:
                            if slip.employee_id.address_id.parent_id:
                                adjustment_entry_name = f"{slip.employee_id.address_id.parent_id.vat} {slip.employee_id.address_id.display_name}|Ajuste al peso"
                            else:
                                adjustment_entry_name = f"{slip.employee_id.address_id.vat} {slip.employee_id.address_id.display_name}|Ajuste al peso"
                        else:
                            adjustment_entry_name = 'Ajuste al peso'

                        if float_compare(credit_sum, debit_sum, precision_digits=precision) == -1:
                            acc_id = slip.journal_id.default_account_id.id
                            if not acc_id:
                                raise UserError(
                                    _('The Expense Journal "%s" has not properly configured the Credit Account!') % (
                                        slip.journal_id.name))
                            existing_adjustment_line = (
                                line_id for line_id in line_ids if line_id['name'] == adjustment_entry_name#_('Adjustment Entry')
                            )
                            adjust_credit = next(existing_adjustment_line, False)

                            if not adjust_credit:
                                adjust_credit = {
                                    'name': adjustment_entry_name,#_('Adjustment Entry'),
                                    'partner_id': slip.employee_id.address_home_id.id,
                                    'account_id': acc_id,
                                    'journal_id': slip.journal_id.id,
                                    'date': date,
                                    'debit': 0.0,
                                    'credit': debit_sum - credit_sum,
                                    'analytic_account_id': slip.employee_id.analytic_account_id.id,
                                }
                                line_ids.append(adjust_credit)
                            else:
                                adjust_credit['credit'] = debit_sum - credit_sum

                        elif float_compare(debit_sum, credit_sum, precision_digits=precision) == -1:
                            acc_id = slip.journal_id.default_account_id.id
                            if not acc_id:
                                raise UserError(
                                    _('The Expense Journal "%s" has not properly configured the Debit Account!') % (
                                        slip.journal_id.name))
                            existing_adjustment_line = (
                                line_id for line_id in line_ids if line_id['name'] == adjustment_entry_name#_('Adjustment Entry')
                            )
                            adjust_debit = next(existing_adjustment_line, False)

                            if not adjust_debit:
                                adjust_debit = {
                                    'name': adjustment_entry_name,#_('Adjustment Entry'),
                                    'partner_id': slip.employee_id.address_home_id.id,
                                    'account_id': acc_id,
                                    'journal_id': slip.journal_id.id,
                                    'date': date,
                                    'debit': credit_sum - debit_sum,
                                    'credit': 0.0,
                                    'analytic_account_id': slip.employee_id.analytic_account_id.id,
                                }
                                line_ids.append(adjust_debit)
                            else:
                                adjust_debit['debit'] = credit_sum - debit_sum

                        if settings_batch_account == '1':
                            # Add accounting lines in the move
                            move_dict['line_ids'] = [(0, 0, line_vals) for line_vals in line_ids]
                            move = self.env['account.move'].create(move_dict)
                            slip.write({'move_id': move.id, 'date': date})

                if settings_batch_account == '0':
                    # Add accounting lines in the move
                    move_dict['line_ids'] = [(0, 0, line_vals) for line_vals in line_ids]
                    move = self.env['account.move'].create(move_dict)
                    for slip in slip_mapped_data[journal_id][slip_date]:
                        slip.write({'move_id': move.id, 'date': date})
        return True


class hr_executing_social_security(models.Model):
    _name = 'hr.account.executing.social.security'
    _description = 'Ejecución de seguridad social'

    executing_social_security_id =  fields.Many2one('account.move', 'Ejecución de seguridad social', required=True, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', 'Empleado',required=True)
    branch_id =  fields.Many2one('lavish.res.branch', 'Sucursal', )
    contract_id =  fields.Many2one('hr.contract', 'Contrato', required=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Cuenta analítica')
    nNumeroHorasLaboradas = fields.Integer('Horas laboradas')
    nDiasLiquidados = fields.Integer('Días liquidados')
    nDiasIncapacidadEPS = fields.Integer('Días incapacidad EPS')
    nDiasLicencia = fields.Integer('Días licencia')
    nDiasLicenciaRenumerada = fields.Integer('Días licencia remunerada')
    nDiasMaternidad = fields.Integer('Días maternidad')
    nDiasVacaciones = fields.Integer('Días vacaciónes')
    nDiasIncapacidadARP = fields.Integer('Días incapacidad ARP')
    nIngreso = fields.Boolean('Ingreso')
    nRetiro = fields.Boolean('Retiro')
    nSueldo = fields.Float('Sueldo')
    TerceroEPS = fields.Many2one('hr.employee.entities', 'Tercero EPS')
    nValorBaseSalud = fields.Float('Valor base salud')
    nPorcAporteSaludEmpleado = fields.Float('Porc. Aporte salud empleados')
    nValorSaludEmpleado = fields.Float('Valor salud empleado')
    nValorSaludEmpleadoNomina = fields.Float('Valor salud empleado nómina')
    nPorcAporteSaludEmpresa = fields.Float('Porc. Aporte salud empresa')
    nValorSaludEmpresa = fields.Float('Valor salud empresa')
    nValorSaludTotal = fields.Float('Valor salud total')
    nDiferenciaSalud = fields.Float('Diferencia salud')
    TerceroPension = fields.Many2one('hr.employee.entities', 'Tercero pensión')
    nValorBaseFondoPension = fields.Float('Valor base fondo de pensión')
    nPorcAportePensionEmpleado = fields.Float('Porc. Aporte pensión empleado')
    nValorPensionEmpleado = fields.Float('Valor pensión empleado')
    nValorPensionEmpleadoNomina = fields.Float('Valor pensión empleado nómina')
    nPorcAportePensionEmpresa = fields.Float('Porc. Aporte pensión empresa')
    nValorPensionEmpresa = fields.Float('Valor pensión empresa')
    nValorPensionTotal = fields.Float('Valor pensión total')
    nDiferenciaPension = fields.Float('Diferencia pensión')
    cAVP = fields.Boolean('Tiene AVP')
    nAporteVoluntarioPension = fields.Float('Valor AVP')
    TerceroFondoSolidaridad = fields.Many2one('hr.employee.entities', 'Tercero fondo solidaridad')
    nPorcFondoSolidaridad = fields.Float('Porc. Fondo solidaridad')
    nValorFondoSolidaridad = fields.Float('Valor fondo solidaridad')
    nValorFondoSubsistencia = fields.Float('Valor fondo subsistencia')
    TerceroARP = fields.Many2one('hr.employee.entities', 'Tercero ARP')
    nValorBaseARP = fields.Float('Valor base ARP')
    nPorcAporteARP = fields.Float('Porc. Aporte ARP')
    nValorARP = fields.Float('Valor ARP')
    cExonerado1607 = fields.Boolean('Exonerado ley 1607')
    TerceroCajaCom = fields.Many2one('hr.employee.entities', 'Tercero caja compensación')
    nValorBaseCajaCom = fields.Float('Valor base caja com')
    nPorcAporteCajaCom = fields.Float('Porc. Aporte caja com')
    nValorCajaCom = fields.Float('Valor caja com')
    TerceroSENA = fields.Many2one('hr.employee.entities', 'Tercero SENA')
    nValorBaseSENA = fields.Float('Valor base SENA')
    nPorcAporteSENA = fields.Float('Porc. Aporte SENA')
    nValorSENA = fields.Float('Valor SENA')
    TerceroICBF = fields.Many2one('hr.employee.entities', 'Tercero ICBF')
    nValorBaseICBF = fields.Float('Valor base ICBF')
    nPorcAporteICBF = fields.Float('Porc. Aporte ICBF')
    nValorICBF = fields.Float('Valor ICBF')
    leave_id = fields.Many2one('hr.leave', 'Ausencia')
    dFechaInicioSLN = fields.Date('Fecha Inicio SLN')
    dFechaFinSLN = fields.Date('Fecha Fin SLN')
    dFechaInicioIGE = fields.Date('Fecha Inicio IGE')
    dFechaFinIGE = fields.Date('Fecha Fin IGE')
    dFechaInicioLMA = fields.Date('Fecha Inicio LMA')
    dFechaFinLMA = fields.Date('Fecha Fin LMA')
    dFechaInicioVACLR = fields.Date('Fecha Inicio VACLR')
    dFechaFinVACLR = fields.Date('Fecha Fin VACLR')
    dFechaInicioVCT = fields.Date('Fecha Inicio VCT')
    dFechaFinVCT = fields.Date('Fecha Fin VCT')
    dFechaInicioIRL = fields.Date('Fecha Inicio IRL')
    dFechaFinIRL = fields.Date('Fecha Fin IRL')

    def executing_social_security_employee(self):
        self.ensure_one()
        if self.executing_social_security_id.state != 'accounting':
            self.executing_social_security_id.executing_social_security(self.employee_id.id)
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }
        else:
            raise ValidationError('No puede recalcular una seguridad en estado contabilizado, por favor verificar.')