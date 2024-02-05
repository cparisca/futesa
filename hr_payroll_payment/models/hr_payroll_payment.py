from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError


from odoo.osv import expression


class HrPayrollPayment(models.Model):
    _name = 'hr.payroll.payment'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin', ]
    _description = 'Payroll payment Draft request'
    _rec_name = "display_name"

    date_start = fields.Date(string="Initial Date", required=True, copy=False)
    date_end = fields.Date(sring="End Date", required=True, copy=False)
    description = fields.Text(string="Description", copy=False, required=True)
    reference = fields.Char(string="Reference", default="/")
    company_id = fields.Many2one("res.company", required=True, readonly=True, default=lambda self: self.env.company)
    partner_ids = fields.Many2many("res.partner", string="Partners", compute="compute_partner_ids")
    payment_line_ids = fields.One2many("hr.payroll.payment.line", 'hr_payment_id', string="Payment Lines")
    group_ids = fields.One2many("hr.group.partner", "hr_payment_id", string="Partners grouped")
    analytic_account_id = fields.Many2one('account.analytic.account', string='Cuenta analítica')
    state = fields.Selection(
        selection=[('draft', 'Draft'),
                   ('request_approval', 'Request Approval'),
                   ('validated', 'Validated'),
                   ('generated', 'Generated'),
                   ('canceled', 'Canceled'), ], copy=False, default='draft', required=True, index=True, )

    employee_ids = fields.Many2many("hr.employee")
    hr_paylip_ids = fields.Many2many("hr.payslip")
    hr_paylip_run_ids = fields.Many2many("hr.payslip.run")
    hr_paylip_ss_ids = fields.Many2many("hr.payroll.social.security")
    product_id = fields.Many2one('product.product', string='Servicio Para Facturacion', ondelete='restrict')