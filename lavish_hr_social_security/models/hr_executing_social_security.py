from logging import exception
from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError

class hr_executing_social_security(models.Model):
    _name = 'hr.executing.social.security'
    _description = 'Ejecución de seguridad social'

    executing_social_security_id =  fields.Many2one('hr.payroll.social.security', 'Ejecución de seguridad social', required=True, ondelete='cascade')
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

class hr_errors_social_security(models.Model):
    _name = 'hr.errors.social.security'
    _description = 'Ejecución de seguridad social errores'

    executing_social_security_id =  fields.Many2one('hr.payroll.social.security', 'Ejecución de seguridad social', required=True, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', 'Empleado',required=True)
    branch_id =  fields.Many2one('lavish.res.branch', 'Sucursal', )
    description = fields.Text('Observación')