from odoo import models, fields, api, _
from datetime import datetime, timedelta, date
from odoo.exceptions import UserError, ValidationError
import time

class hr_type_overtime(models.Model):
    _name = 'hr.type.overtime'
    _description = 'Tipos de horas extras'

    name = fields.Char(string="Descripción", required=True)
    salary_rule = fields.Many2one('hr.salary.rule', string="Regla salarial", required=True)
    type_overtime = fields.Selection([('overtime_rn','RN | Recargo nocturno'),
                                      ('overtime_ext_d','EXT-D | Extra diurna'),
                                      ('overtime_ext_n','EXT-N | Extra nocturna'),
                                      ('overtime_eddf','E-D-D/F | Extra diurna dominical/festivo'),
                                      ('overtime_endf','E-N-D/F | Extra nocturna dominical/festivo'),
                                      ('overtime_dof','D o F | Dominicales o festivos'),
                                      ('overtime_rndf','RN-D/F | Recargo nocturno dominical/festivo'),
                                      ('overtime_rdf','R-D/F | Recargo dominical/festivo'),
                                      ('overtime_rnf','RN-F | Recargo nocturno festivo')],'Tipo',  required=True)
    percentage = fields.Float(string='Porcentaje')
    equivalence_number_ne = fields.Integer(string='Num. Equivalencia NE')
    start_time = fields.Float('Hora inicio', required=True, default=0)
    end_time = fields.Float('Hora finalización', required=True, default=0)
    start_time_two = fields.Float('Segunda hora de inicio', required=True, default=0)
    end_time_two = fields.Float('Segunda hora de finalización', required=True, default=0)
    contains_holidays = fields.Boolean(string='¿Tener en cuenta días festivos?')
    mon = fields.Boolean(default=False, string='Lun')
    tue = fields.Boolean(default=False, string='Mar')
    wed = fields.Boolean(default=False, string='Mié')
    thu = fields.Boolean(default=False, string='Jue')
    fri = fields.Boolean(default=False, string='Vie')
    sat = fields.Boolean(default=False, string='Sáb')
    sun = fields.Boolean(default=False, string='Dom')

    _sql_constraints = [('change_type_uniq', 'unique(type_overtime)', 'Ya existe este tipo de hora extra, por favor verficar.')]

class hr_overtime(models.Model):
    _name = 'hr.overtime'
    _description = 'Novedades | Horas extras'
    
    branch_id = fields.Many2one('lavish.res.branch', 'Sucursal')
    date = fields.Date('Fecha Novedad', required=True)
    date_end = fields.Date('Fecha Final Novedad', required=True)
    employee_id = fields.Many2one('hr.employee', string="Empleado", index=True)
    employee_identification = fields.Char('Identificación empleado')
    department_id = fields.Many2one('hr.department', related="employee_id.department_id", readonly=True,string="Departamento")
    job_id = fields.Many2one('hr.job', related="employee_id.job_id", readonly=True,string="Servicio")
    overtime_rn = fields.Float('RN', help='Horas recargo nocturno (35%)') # EXTRA_RECARGO
    overtime_ext_d = fields.Float('EXT-D', help='Horas extra diurnas (125%)') # EXTRA_DIURNA
    overtime_ext_n = fields.Float('EXT-N', help='Horas extra nocturna (175%)') # EXTRA_NOCTURNA
    overtime_eddf = fields.Float('E-D-D/F', help='Horas extra diurnas dominical/festiva (200%)') # EXTRA_DIURNA_DOMINICAL
    overtime_endf = fields.Float('E-N-D/F', help='Horas extra nocturna dominical/festiva (250%)') # EXTRA_NOCTURNA_DOMINICAL
    overtime_dof = fields.Float('D o F', help='Horas dominicales (175%)') # DOMINICALES O FESTIVOS
    overtime_rndf = fields.Float('RN-D/F', help='Horas recargo festivo (110%)') # EXTRA_RECARGO_DOMINICAL
    overtime_rdf = fields.Float('R-D/F', help='Recargos dominicales (0.75%)', default=0)  # EXTRA_RECARGO_DOMINICAL_FESTIVO
    overtime_rnf = fields.Float('RN-F', help='Recargo festivo nocturno (210%)')  # EXTRA_RECARGO_NOCTURNO_FESTIVO
    days_actually_worked = fields.Integer('Días efectivamente laborados')
    days_snack = fields.Integer('Días refrigerio')
    justification = fields.Char('Justificación')
    state = fields.Selection([('revertido','Revertido'),('procesado','Procesado'),('nuevo','Nuevo')],'Estado')
    payslip_run_id = fields.Many2one('hr.payslip','Ref. Liquidación')
    shift_hours = fields.Float('Horas del Turno')

    @api.model
    def create(self, vals):
        total = vals.get('shift_hours',0) + vals.get('days_snack',0) + vals.get('days_actually_worked',0) + vals.get('overtime_rn',0) + vals.get('overtime_ext_d',0) + vals.get('overtime_ext_n',0) + vals.get('overtime_eddf',0) + vals.get('overtime_endf',0) + vals.get('overtime_dof',0) + vals.get('overtime_rndf',0) + vals.get('overtime_rdf',0) + vals.get('overtime_rnf',0)
        if total > 0:            
            if vals.get('employee_identification'):
                obj_employee = self.env['hr.employee'].search([('company_id','=',self.env.company.id),('identification_id', '=', vals.get('employee_identification'))],limit=1)
                vals['employee_id'] = obj_employee.id
            if vals.get('employee_id'):
                obj_employee = self.env['hr.employee'].search([('company_id','=',self.env.company.id),('id', '=', vals.get('employee_id'))],limit=1)
                vals['employee_identification'] = obj_employee.identification_id
            registrar_novedad = super(hr_overtime, self).create(vals)
            return registrar_novedad
        else:
            raise UserError(_('Valores en 0 detectados | No se ha detectado la cantidad de horas / dias de la novedad ingresada!'))       