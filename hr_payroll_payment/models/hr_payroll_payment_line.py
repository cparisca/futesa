from odoo import fields, models, api
from odoo.exceptions import UserError
from odoo import _ as translate


class HrPayrollPaymentLine(models.Model):
    _name = 'hr.payroll.payment.line'
    _description = 'Line Payroll payment Draft request'
    _rec_name = "partner_id"


    hr_payment_id = fields.Many2one("hr.payroll.payment", copy=False, ondelete="cascade")
    move_line_id = fields.Many2one("account.move.line", copy=False, string="Line to reconcile")
    slip_id = fields.Many2one("hr.payslip", compute="get_reference_payslip", store=True)
   # currency_id = fields.Many2one("res.currency", related="move_line_id.move_id.currency_id")
   # employee_id = fields.Many2one("hr.employee", related="move_line_id.employee_id", store=True)
    #debit = fields.Monetary(string="Debit", related="move_line_id.debit", currency_field='currency_id',)
   # credit = fields.Monetary(string="Credit", related="move_line_id.credit", currency_field='currency_id',)
    balance = fields.Monetary(string="Balance",  related="move_line_id.balance", currency_field='currency_id',)
    importe = fields.Float('Importe')
    tax_ids = fields.Many2many(
        domain="[('type_tax_use', '=', 'sale')",
        comodel_name='account.tax',
        string="Taxes",
        check_company=True,
        help="Taxes that apply on the base amount")
    description = fields.Char("Description")
    account_id = fields.Many2one("account.account", string="Account",)
    partner_id = fields.Many2one("res.partner", string="Partner")
    approval_state = fields.Selection(
        [('not_approved', 'No Approved'),
         ('approved', 'Approved')], default='not_approved', copy=False, string="Approved")
    
    def action_approval_state(self, state):
        action = {}
        self.check_lines_approvals()
        for line in self:
            if line.approval_state == 'approved' and state == 'not_approved':
                line.update_amount_pay()
            line.write({'approval_state': state})
        return action


    def unlink(self):
        for line in self:
            if line.approval_state == 'approved':
                raise UserError(translate(
                    "Not is possible delete an payable line in approved state. Instead not approved line to delete it"))
        return super().unlink()
