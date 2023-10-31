from odoo import fields, models, api, _

class AdvanceType(models.Model):
	_name = "advance.type"
	_description = "Tipo de anticipo"

	name = fields.Char(string="Name", required=True)
	account_id = fields.Many2one('account.account', string="Cuenta de anticipo", required=True, domain=[('internal_type','in',('payable','receivable'))])
	internal_type = fields.Selection(related='account_id.internal_type', string="Internal Type", store=True, readonly=True)
	company_id = fields.Many2one('res.company', related='account_id.company_id', string='Company', store=True, readonly=True)
