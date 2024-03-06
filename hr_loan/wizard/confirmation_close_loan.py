from odoo import fields, models, _
from odoo.exceptions import UserError


class ConfirmationCloseLoan(models.TransientModel):
    _name = 'extender.loan'
    _description = 'Ampliar fechas'

    loan_id = fields.Many2one('hr.loan', string='Loan Id')
    external_loan_id = fields.Many2one('hr.external.loan', string='External Loan Id')

    def compute_sheet(self):
        if self.loan_id:
            self.loan_id.set_close()
        elif self.external_loan_id:
            self.external_loan_id.set_close()
        else:
            raise UserError(_('The operation is not valid'))
