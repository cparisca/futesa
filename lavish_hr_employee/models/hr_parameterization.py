# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime, timedelta, date
from odoo.exceptions import UserError, ValidationError
import time

#Tabla de tipos de empleados
class hr_types_employee(models.Model):
    _name = 'hr.types.employee'
    _description = 'Tipos de empleado'

    code = fields.Char('Código',required=True)
    name = fields.Char('Nombre',required=True)

    _sql_constraints = [('change_code_uniq', 'unique(code)', 'Ya existe un tipo de empleado con este código, por favor verificar')]

#Tabla de tiesgos profesionales
class hr_contract_risk(models.Model):
    _name = 'hr.contract.risk'
    _description = 'Riesgos profesionales'

    code = fields.Char('Codigo', size=10, required=True)
    name = fields.Char('Nombre', size=100, required=True)
    percent = fields.Float('Porcentaje', digits=(12,3), required=True, help='porcentaje del riesgo profesional')
    date = fields.Date('Fecha vigencia')

    _sql_constraints = [('change_code_uniq', 'unique(code)', 'Ya existe un riesgo con este código, por favor verificar')]  

class lavish_economic_activity_level_risk(models.Model):
    _name = 'lavish.economic.activity.level.risk'
    _description = 'Actividad económica por nivel de riesgo'

    risk_class_id = fields.Many2one('hr.contract.risk','Clase de riesgo', required=True)
    code_ciiu_id = fields.Many2one('lavish.ciiu','CIIU', required=True)
    code = fields.Char('Código', required=True)
    name = fields.Char('Descripción', required=True)

    _sql_constraints = [('economic_activity_level_risk_uniq', 'unique(risk_class_id,code_ciiu_id,code)', 'Ya existe un riesgo con este código, por favor verificar')]

    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "{}{}{} | {}".format(record.risk_class_id.code, record.code_ciiu_id.code, record.code, record.code_ciiu_id.name)))
        return result

#Tabla tipos de entidades
class hr_contrib_register(models.Model):
    _name = 'hr.contribution.register'
    _description = 'Tipo de Entidades'
    
    name = fields.Char('Nombre', required=True)
    type_entities = fields.Selection([('none', 'No aplica'),
                             ('eps', 'Entidad promotora de salud'),
                             ('pension', 'Fondo de pensiones'),
                             ('cesantias', 'Fondo de cesantias'),
                             ('caja', 'Caja de compensación'),
                             ('riesgo', 'Aseguradora de riesgos profesionales'),
                             ('sena', 'SENA'),
                             ('icbf', 'ICBF'),
                             ('solidaridad', 'Fondo de solidaridad'),
                             ('subsistencia', 'Fondo de subsistencia')], 'Tipo', required=True)
    note = fields.Text('Description')

    _sql_constraints = [('change_name_uniq', 'unique(name)', 'Ya existe un tipo de entidad con este nombre, por favor verificar')]         

#Tabla de entidades
class hr_employee_entities(models.Model):
    _name = 'hr.employee.entities'
    _description = 'Entidades empleados'

    partner_id = fields.Many2one('res.partner', 'Entidad', help='Entidad relacionada')
    name = fields.Char(related="partner_id.name", readonly=True,string="Nombre")
    business_name = fields.Char(related="partner_id.business_name", readonly=True,string="Nombre de negocio")
    types_entities = fields.Many2many('hr.contribution.register',string='Tipo de entidad')
    code_pila_eps = fields.Char('Código PILA')
    code_pila_ccf = fields.Char('Código PILA para CCF')
    code_pila_regimen = fields.Char('Código PILA Regimen de excepción')
    code_pila_exterior = fields.Char('Código PILA Reside en el exterior')
    order = fields.Selection([('territorial', 'Orden Terrritorial'),
                             ('nacional', 'Orden Nacional')], 'Orden de la entidad')
    debit_account = fields.Many2one('account.account', string='Cuenta débito', company_dependent=True)
    credit_account = fields.Many2one('account.account', string='Cuenta crédito', company_dependent=True)
    _sql_constraints = [('change_partner_uniq', 'unique(partner_id)', 'Ya existe una entidad asociada a este tercero, por favor verificar')]         

    def name_get(self):
        result = []
        for record in self:
            if record.partner_id.business_name: 
                result.append((record.id, "{}".format(record.partner_id.business_name)))
            else: 
                result.append((record.id, "{}".format(record.partner_id.name)))
        return result

#Categorias reglas salariales herencia

class hr_categories_salary_rules(models.Model):
    _inherit = 'hr.salary.rule.category'
    
    group_payroll_voucher = fields.Boolean('Agrupar comprobante de nómina')
    sequence = fields.Integer(tracking=True)
#Contabilización reglas salariales
class hr_salary_rule_accounting(models.Model):
    _name ='hr.salary.rule.accounting'
    _description = 'Contabilización reglas salariales'    

    salary_rule = fields.Many2one('hr.salary.rule', string = 'Regla salarial')
    department = fields.Many2one('hr.department', string = 'Departamento')
    company = fields.Many2one('res.company', string = 'Compañía')
    work_location = fields.Many2one('res.partner', string = 'Ubicación de trabajo')
    third_debit = fields.Selection([('entidad', 'Entidad'),
                                    ('compañia', 'Compañia'),
                                    ('empleado', 'Empleado')], string='Tercero débito') 
    third_credit = fields.Selection([('entidad', 'Entidad'),
                                    ('compañia', 'Compañia'),
                                    ('empleado', 'Empleado')], string='Tercero crédito')
    debit_account = fields.Many2one('account.account', string = 'Cuenta débito', company_dependent=True)
    credit_account = fields.Many2one('account.account', string = 'Cuenta crédito', company_dependent=True)

#Estructura Salariales - Herencia
class hr_payroll_structure(models.Model):
    _inherit = 'hr.payroll.structure'

    @api.model
    def _get_default_rule_ids(self):
        default_rules = []
        if self.country_id.code == 'CO':
            if self.process == 'prima':
                # Añade las reglas para 'primas'
                default_rules.append((0, 0, {
                    # Detalles de la regla para 'primas'
                }))
            elif self.process == 'vacaciones':
                # Añade las reglas para 'nomina base'
                default_rules.append((0, 0, {
                    # Detalles de la regla para 'nomina base'
                }))
            elif self.process == 'cesantias':
                # Añade la regla para 'cesantias'
                default_rules.append((0, 0, {
                    'name': _('Cesantias'),
                    'sequence': 1,
                    'code': 'CESANTIAS',
                    'category_id': self.env.ref('lavish_hr_employee.PRESTACIONES_SOCIALES').id,
                    'condition_select': 'python',
                    'condition_python': 'result = payslip.get_salary_rule(\'CESANTIAS\',employee.type_employee.id)',
                    'amount_select': 'code',
                    'amount_python_compute': """
                        result = 0.0
                        obj_salary_rule = result
                        if obj_salary_rule:
                            date_start = payslip.date_from
                            date_end = payslip.date_to
                            if inherit_contrato != 0:
                                date_start = payslip.date_cesantias
                                date_end = payslip.date_liquidacion
                            accumulated = payslip.get_accumulated_cesantias(date_start,date_end) + values_base_cesantias
                            result = accumulated""",
                }))
        return default_rules

    process = fields.Selection([('nomina', 'Nónima'),
                                ('vacaciones', 'Vacaciones'),
                                ('prima', 'Prima'),
                                ('cesantias', 'Cesantías'),
                                ('intereses_cesantias', 'Intereses de cesantías'),
                                ('contrato', 'Liq. de Contrato'),
                                ('otro', 'Otro')], string='Proceso')
    regular_pay = fields.Boolean('Pago standar')
    rule_ids = fields.One2many(
        'hr.salary.rule', 'struct_id',
        string='Salary Rules', default=_get_default_rule_ids)

    @api.onchange('regular_pay')
    def onchange_regular_pay(self):
        for record in self:
            record.process = 'nomina' if record.regular_pay == True else False  
  
    @api.onchange('process')
    def _onchange_process(self):
        # Solo cambia las reglas si el registro no ha sido guardado todavía
        if not self._origin:
            self.rule_ids = self._get_default_rule_ids()
#Tipos entradas de trabajo - Herencia
class hr_work_entry_type(models.Model):
    _name = 'hr.work.entry.type'
    _inherit = ['hr.work.entry.type','mail.thread', 'mail.activity.mixin']

    code = fields.Char(tracking=True)
    sequence = fields.Integer(tracking=True)
    round_days = fields.Selection(tracking=True)
    round_days_type = fields.Selection(tracking=True)
    is_leave = fields.Boolean(tracking=True)
    is_unforeseen = fields.Boolean(tracking=True)

#Reglas Salariales - Herencia
class hr_salary_rule(models.Model):
    _name = 'hr.salary.rule'
    _inherit = ['hr.salary.rule','mail.thread', 'mail.activity.mixin']

    #Trazabilidad
    struct_id = fields.Many2one(tracking=True)
    active = fields.Boolean(tracking=True)
    sequence = fields.Integer(tracking=True)
    condition_select = fields.Selection(tracking=True)
    amount_select = fields.Selection(tracking=True)
    amount_python_compute = fields.Text(tracking=True)
    appears_on_payslip = fields.Boolean(tracking=True)
    proyectar_nom = fields.Boolean('Proyectar en nomina')
    proyectar_ret = fields.Boolean('Proyectar en Retencion')
    #Campos lavish
    types_employee = fields.Many2many('hr.types.employee',string='Tipos de Empleado', tracking=True)
    dev_or_ded = fields.Selection([('devengo', 'Devengo'),
                                     ('deduccion', 'Deducción')],'Naturaleza', tracking=True)
    type_concepts = fields.Selection([('contrato', 'Fijo Contrato'),
                                     ('ley', 'Por Ley'),
                                     ('novedad', 'Novedad Variable'),
                                     ('prestacion', 'Prestación Social'),
                                     ('tributaria', 'Deducción Tributaria')],'Tipo', required=True, default='contrato', tracking=True)
    aplicar_cobro = fields.Selection([('15','Primera quincena'),
                                        ('30','Segunda quincena'),
                                        ('0','Siempre')],'Aplicar cobro', tracking=True)
    modality_value = fields.Selection([('fijo', 'Valor fijo'),
                                       ('diario', 'Valor diario'),
                                       ('diario_efectivo', 'Valor diario del día efectivamente laborado')],'Modalidad de valor', tracking=True)
    deduction_applies_bonus = fields.Boolean('Aplicar deducción en Prima', tracking=True)
    account_tax_id = fields.Many2one("account.tax", "Impuesto de Retefuente Laboral")
    #Es incapacidad / deducciones
    is_leave = fields.Boolean('Es Ausencia', tracking=True)
    is_recargo = fields.Boolean('Es Recargos', tracking=True)
    deduct_deductions = fields.Selection([('all', 'Todas las deducciones'),
                                          ('law', 'Solo las deducciones de ley')],'Tener en cuenta al descontar', default='all', tracking=True)    #Vacaciones
    restart_one_month_prima = fields.Boolean('Restar 1 mes al promedio de los acumulados en prima', tracking=True)
    #Base de prestaciones
    base_prima = fields.Boolean('Para prima', tracking=True)
    base_cesantias = fields.Boolean('Para cesantías', tracking=True)
    base_vacaciones = fields.Boolean('Para vacaciones tomadas', tracking=True)
    base_vacaciones_dinero = fields.Boolean('Para vacaciones dinero', tracking=True)
    base_intereses_cesantias = fields.Boolean('Para intereses de cesantías', tracking=True)
    base_auxtransporte_tope = fields.Boolean('Para tope de auxilio de transporte', tracking=True)
    base_compensation = fields.Boolean('Para liquidación de indemnización', tracking=True)
    #Base de Seguridad Social
    base_seguridad_social = fields.Boolean('Para seguridad social', tracking=True)
    base_arl = fields.Boolean('Para seguridad social', tracking=True)
    base_parafiscales = fields.Boolean('Para parafiscales', tracking=True)
    excluir_ret = fields.Boolean('excluir de Calculo retefuente', tracking=True)
    #Contabilización
    salary_rule_accounting = fields.One2many('hr.salary.rule.accounting', 'salary_rule', string="Contabilización", tracking=True)
    #Reportes
    display_days_worked = fields.Boolean(string='Mostrar la cantidad de días trabajados en los formatos de impresión', tracking=True)
    short_name = fields.Char(string='Nombre corto/reportes')
    process = fields.Selection([('nomina', 'Nónima'),
                                ('vacaciones', 'Vacaciones'),
                                ('prima', 'Prima'),
                                ('cesantias', 'Cesantías'),
                                ('intereses_cesantias', 'Intereses de cesantías'),
                                ('contrato', 'Liq. de Contrato'),
                                ('otro', 'Otro')], string='Proceso')
    novedad_ded = fields.Selection([('cont', 'Contrato'),
                                    ('Noved', 'Novedad'),
                                    ('0', 'No'),],'Opcion de Novedad', tracking=True)
    not_include_flat_payment_file = fields.Boolean(string='No incluir en archivo plano de pagos')
    #Empleados publicos
    account_id_cxp = fields.Many2one('account.account',string='Cuenta CXP', company_dependent=True)
    state_budget_item = fields.Char(string='Rubro')
    state_budget_resource = fields.Char(string='Recurso')

#Sanciones
class hr_types_faults(models.Model):
    _name = 'hr.types.faults'
    _description = 'Tipos de faltas'

    name = fields.Char('Nombre', required=True)
    description = fields.Text('Descripción')