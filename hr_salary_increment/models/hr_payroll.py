from odoo import models, fields, api , tools, _
from odoo.exceptions import except_orm, Warning, RedirectWarning, UserError
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo.osv import osv

class HrSalaryIncreaseLine(models.Model):
	_inherit="hr.salary.increase.line"

	payroll_id = fields.Many2one('hr.payslip')

class hr_payslip(models.Model):
	_inherit = 'hr.payslip'

	# @api.depends('leave_ids.number_of_hours_display')
	@api.depends('increase_ids.amount')
	def compute_total_bonus(self):
		total = 0.00
		for line in self.increase_ids:
			total += line.amount * line.no_of_month
		self.total_increase = total

	increase_ids = fields.One2many('hr.salary.increase.line', 'payroll_id', string="Bonus",readonly=True)
	total_increase = fields.Float(string="Total Amount", compute= 'compute_total_bonus')


	def get_increase(self):
		array = []
		domain = [('employee_id','=',self.employee_id.id),('state','=','confirm'),('date_applied_on','>=',self.date_from),('date_applied_on','<=',self.date_to)]
		increase_ids = self.env['hr.salary.increase.line'].search(domain)
		for increase in increase_ids:
			if increase.increase_type != 'promotion':
				array.append(increase.id)
			else:
				date = fields.Datetime.from_string(increase.date).date()
				date_applied_on = fields.Datetime.from_string(increase.date_applied_on).date()

				if date < self.date_from and date_applied_on >= self.date_from and date_applied_on <= self.date_to :
					array.append(increase.id)

		for increase in self.increase_ids:
			if increase.id not in array:
				increase.payroll_id = False
		self.increase_ids = array
		return array

