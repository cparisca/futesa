from odoo import models, fields, api

class HrWorkEntryType(models.Model):    
    _inherit = "hr.work.entry.type"
    
    deduct_deductions = fields.Selection([('all', 'Todas las deducciones'),
                                          ('law', 'Solo las deducciones de ley')],'Tener en cuenta al descontar', default='all')    #Vacaciones
    not_contribution_base = fields.Boolean(string='No es base de aportes',help='Este tipo de ausencia no es base para seguridad social')
    short_name = fields.Char(string='Nombre corto/reportes')
#Tipos de Ausencia
class hr_leave_type(models.Model):
    _inherit = 'hr.leave.type'
    code= fields.Char('Codigo')
    is_vacation = fields.Boolean('Tipo de ausencia para vacaciones disfrutadas')
    #Validación
    obligatory_attachment  = fields.Boolean('Obligar adjunto')
    #Configuración de la EPS/ARL
    num_days_no_assume = fields.Integer('Número de días que no asume')
    recognizing_factor_eps_arl = fields.Float('Factor que reconoce la EPS/ARL', digits=(25,5))
    periods_calculations_ibl = fields.Integer('Periodos para cálculo de IBL')
    eps_arl_input_id = fields.Many2one('hr.salary.rule', 'Regla de la incapacidad EPS/ARL')
    #Configuración de la Empresa
    recognizing_factor_company = fields.Float('Factor que reconoce la empresa', digits=(25,5))
    periods_calculations_ibl_company = fields.Integer('Periodos para cálculo de IBL Empresa')
    company_input_id = fields.Many2one('hr.salary.rule', 'Regla de la incapacidad empresa')
    unpaid_absences = fields.Boolean('Ausencia no remunerada')
    discounting_bonus_days = fields.Boolean('Descontar en Prima')
    evaluates_day_off = fields.Boolean('Evalúa festivos')
    apply_day_31 = fields.Boolean(string='Aplica día 31')
    discount_rest_day = fields.Boolean(string='Descontar día de descanso')
    published_portal = fields.Boolean(string='Permitir uso en portal de autogestión')
    type_of_entity_association = fields.Many2one('hr.contribution.register', 'Tipo de entidad asociada')
    VALUES = [
        ('sln', 'Suspensión temporal del contrato de trabajo o Comisión de servicios'),
        ('ige', 'Incapacidad EPS'),
        ('irl', 'Incapacidad por accidente de trabajo o Enfermedad laboral'),
        ('lma', 'Licencia de Maternidad'),
        ('lpa', 'Licencia de Paternidad'),
        ('vco', 'Vacaciones Compensadas'),
        ('vdi', 'Vacaciones Disfrutadas'),
        ('vre', 'Vacaciones por Retiro'),
        ('lr', 'Licencia remunerada'),
        ('lnr', 'Licencia no Remunerada'),
        ('lt', 'Licencia de Luto'),
    ]
    VALORES = [
        ('IBC', 'IBC MES ANTERIOR'),
        ('YEAR', 'PROMEDIO AÑO ANTERIOR'),
        ('WAGE', 'SUELDO ACTUAL'),
    ]
    novelty = fields.Selection(
      string="Tipo de Ausencia",
      selection=VALUES,)
    liquidacion_value = fields.Selection(
      string="Tipo de liquidacion de valores",
      selection=VALORES,)
    def get_rate_concept_id(self, sequence):
      if self.novelty != 'ige':
          rate = 1
          if 1 <= sequence <= self.num_days_no_assume:
              rate = self.recognizing_factor_company
              concept_id = self.company_input_id.id
          else:
              rate = self.recognizing_factor_eps_arl
              concept_id = self.eps_arl_input_id.id
      elif 3 <= sequence <= 90:
          rate = self.recognizing_factor_eps_arl
          concept_id = self.eps_arl_input_id.id
      elif 91 <= sequence <= 180:
          rate = self.recognizing_factor_eps_arl
          concept_id = self.eps_arl_input_id.id
      elif 181 <= sequence:
          rate = self.recognizing_factor_eps_arl
          concept_id = self.eps_arl_input_id.id
      else:
          rate = 1
          concept_id = None
      return rate, concept_id or None

    _sql_constraints = [('hr_leave_type_code_uniq', 'unique(code)',
                         'Ya existe este código de nómina, por favor verficar.')]
    

    