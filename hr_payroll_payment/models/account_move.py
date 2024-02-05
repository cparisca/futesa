from odoo import fields, models, api, _



class AccountMove(models.Model):
    _inherit = 'account.move'

    is_payroll = fields.Boolean('Pago a Terceros')
    lotes = fields.One2many('hr.payslip.run','move_id',string='lotes de nomina')
    nominas = fields.One2many('hr.payslip','invoice_id',string='lotes de nomina')
    hr_ss = fields.One2many('hr.payroll.social.security','invoice_id',string='lotes de nomina')
    
    
class hr_payroll_social_security(models.Model):
    _inherit = 'hr.payroll.social.security'

    invoice_id = fields.Many2one('account.move')

class HrPayslip(models.Model):
    _name = 'hr.payslip.run'
    
    move_id = fields.Many2one('account.move')
class HrPayslipRun(models.Model):
    _name = 'hr.payslip'
    
    invoice_id = fields.Many2one('account.move')