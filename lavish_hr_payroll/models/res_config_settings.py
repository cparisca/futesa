# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models

class ResCompany(models.Model):
    _inherit = 'res.company'

    payroll_electronic_operator = fields.Selection([('Carvajal', 'Carvajal'),
                                                    ('FacturaTech', 'FacturaTech')],
                                                   string='Operador', default='Carvajal')
    payroll_electronic_username_ws = fields.Char(string='Usuario WS')
    payroll_electronic_password_ws = fields.Char(string='Contraseña WS')
    payroll_electronic_company_id_ws = fields.Char(string='Identificador compañia WS')
    payroll_electronic_account_id_ws = fields.Char(string='Identificador cuenta WS')
    payroll_electronic_service_ws = fields.Char(string='Servicio WS', default='PAYROLL')
    payroll_peoplepass_journal_id = fields.Many2one('account.journal',string='Diario contabilización pago valor no incluido')
    payroll_peoplepass_debit_account_id = fields.Many2one('account.account',string='Cuenta contabilización pago valor no incluido débito')
    payroll_peoplepass_credit_account_id = fields.Many2one('account.account',string='Cuenta contabilización pago valor no incluido crédito')
    # Certificado ingreso y retenciones
    validated_certificate = fields.Many2one('documents.tag', string='Certificado validado')

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    module_hr_payroll_batch_account = fields.Selection([('0','Crear un solo movimiento contable'),
                                                        ('1','Crear movimiento contable por empleado')],
                                        string='Contabilización por lote')
    addref_work_address_account_moves = fields.Boolean('¿Agregar ubicación laboral del empleado en la descripción de los movimientos contables?')
    round_payroll = fields.Boolean('NO redondear decimales en procesos de liquidación')
    pay_vacations_in_payroll = fields.Boolean('¿Liquidar vacaciones en nómina?')
    pay_cesantias_in_payroll = fields.Boolean('¿Liquidar Interese de cesantia en nómina?')
    pay_primas_in_payroll = fields.Boolean('¿Liquidar Primas en nómina?')
    vacation_days_calculate_absences = fields.Char('Días de vacaciones para calcular deducciones')
    cesantias_salary_take = fields.Boolean('Promediar salario de los últimos 3 meses, si ahí variación en cesantías')
    prima_salary_take = fields.Boolean('Promediar salario de los últimos 6 meses, si ahí variación en prima')
    #PeoplePass
    payroll_peoplepass_journal_id = fields.Many2one(related='company_id.payroll_peoplepass_journal_id',string='Diario contabilización pago valor no incluido', readonly=False)
    payroll_peoplepass_debit_account_id = fields.Many2one(related='company_id.payroll_peoplepass_debit_account_id',string='Cuenta contabilización pago valor no incluido débito', readonly=False)
    payroll_peoplepass_credit_account_id = fields.Many2one(related='company_id.payroll_peoplepass_credit_account_id',string='Cuenta contabilización pago valor no incluido crédito', readonly=False)
   #Nómina electronica
    payroll_electronic_operator = fields.Selection(related='company_id.payroll_electronic_operator', string='Operador',readonly=False)
    payroll_electronic_username_ws = fields.Char(related='company_id.payroll_electronic_username_ws',string='Usuario WS', readonly=False)
    payroll_electronic_password_ws = fields.Char(related='company_id.payroll_electronic_password_ws',string='Contraseña WS', readonly=False)
    payroll_electronic_company_id_ws = fields.Char(related='company_id.payroll_electronic_company_id_ws',string='Identificador compañia WS', readonly=False)
    payroll_electronic_account_id_ws = fields.Char(related='company_id.payroll_electronic_account_id_ws',string='Identificador cuenta WS', readonly=False)
    payroll_electronic_service_ws = fields.Char(related='company_id.payroll_electronic_service_ws',string='Servicio WS', default='PAYROLL', readonly=False)

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        set_param = self.env['ir.config_parameter'].sudo().set_param
        set_param('lavish_hr_payroll.module_hr_payroll_batch_account', self.module_hr_payroll_batch_account)
        set_param('lavish_hr_payroll.addref_work_address_account_moves', self.addref_work_address_account_moves)
        set_param('lavish_hr_payroll.round_payroll', self.round_payroll)
        set_param('lavish_hr_payroll.pay_vacations_in_payroll', self.pay_vacations_in_payroll)
        set_param('lavish_hr_payroll.pay_cesantias_in_payroll', self.pay_cesantias_in_payroll)
        set_param('lavish_hr_payroll.pay_primas_in_payroll', self.pay_primas_in_payroll)
        set_param('lavish_hr_payroll.vacation_days_calculate_absences', self.vacation_days_calculate_absences)
        set_param('lavish_hr_payroll.cesantias_salary_take', self.cesantias_salary_take)
        set_param('lavish_hr_payroll.prima_salary_take', self.prima_salary_take)

    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        get_param = self.env['ir.config_parameter'].sudo().get_param
        res['module_hr_payroll_batch_account'] = get_param('lavish_hr_payroll.module_hr_payroll_batch_account')
        res['addref_work_address_account_moves'] = get_param('lavish_hr_payroll.addref_work_address_account_moves')
        res['round_payroll'] = get_param('lavish_hr_payroll.round_payroll')
        res['pay_vacations_in_payroll'] = get_param('lavish_hr_payroll.pay_vacations_in_payroll')
        res['pay_cesantias_in_payroll'] = get_param('lavish_hr_payroll.pay_cesantias_in_payroll')
        res['pay_primas_in_payroll'] = get_param('lavish_hr_payroll.pay_primas_in_payroll')
        res['vacation_days_calculate_absences'] = get_param('lavish_hr_payroll.vacation_days_calculate_absences')
        res['cesantias_salary_take'] = get_param('lavish_hr_payroll.cesantias_salary_take')
        res['prima_salary_take'] = get_param('lavish_hr_payroll.prima_salary_take')
        return res