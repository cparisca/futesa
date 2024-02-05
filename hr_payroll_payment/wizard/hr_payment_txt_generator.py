from odoo import fields, models, api, _
from odoo.exceptions import UserError

from ..models.hr_payroll_payment import apply_object
import base64
import json
import openpyxl
from io import BytesIO


class HRPaymentTXTGenerator(models.TransientModel):
    _name = 'hr.payment.txt.generator'
    _description = 'HR Payment TXT generator'

    payment_txt_config_id = fields.Many2one('hr.payment.txt.config', string="Configuration", required=True,
                                            tracking=True)
    company_id = fields.Many2one("res.company", readonly=True)
    journal_id = fields.Many2one("account.journal", related="company_id.payment_journal_id")
    partners = fields.Char(compute="compute_partner")
    hr_payment = fields.Many2one("hr.payroll.payment")
    list_employees = fields.Char(string="List employees", compute="_compute_employee_id_domain")
    employee_ids = fields.Many2many('hr.employee', string="Employees")

    attachment_name = fields.Char(string="Attachment Name")
    attachment_id = fields.Binary(string="Attachment")

    def load_employee_excel(self):
        if self.attachment_id:
            wb = openpyxl.load_workbook(filename=BytesIO(base64.b64decode(self.attachment_id)), read_only=True)
            ws = wb.active
            row = 0
            employee_id = False
            employee_list = []
            for record in ws.iter_rows(min_row=1, max_row=None, min_col=1, max_col=1, values_only=True):
                row += 1
                identification_id = record[0] if record else False
                if any(record):
                    employee_id = self.env['hr.employee'].search([('identification_id', '=', identification_id)])
                    if employee_id:
                        if employee_id in self.hr_payment.employee_ids:
                            employee_list.append(employee_id.id)
                else:
                    break
            if employee_list:
                self.employee_ids = [(6, 0, employee_list)]

            return {
                'name': 'Process Employees',
                'view_mode': 'form',
                'view_id': False,
                'res_model': self._name,
                'domain': [],
                'context': dict(self._context, active_ids=self.ids),
                'type': 'ir.actions.act_window',
                'target': 'new',
                'res_id': self.id,
            }

    @api.depends('company_id')
    def _compute_employee_id_domain(self):
        for record in self:
            if record.hr_payment:
                record.list_employees = json.dumps([('id', 'in', record.hr_payment.employee_ids.ids)])
            else:
                record.list_employees = json.dumps([])

    @api.depends("hr_payment")
    def compute_partner(self):
        for generator in self:
            display = ''
            partners = generator.hr_payment.group_ids.mapped(apply_object)
            if generator.hr_payment and generator.hr_payment.group_ids and partners:
                partners = partners.mapped('partner_id')
                display = ','.join([partner.name for partner in partners])
            generator.partners = display

    def start(self):
        self.ensure_one()
        txt = self.payment_txt_config_id.get_txt(self, self.hr_payment)
        filename = self.hr_payment.reference + ' - (' + self.payment_txt_config_id.display_name + ').txt'
        file = base64.b64encode(txt.encode('utf-8')).decode('utf-8', 'ignore')
        self.hr_payment.adding_plain_file(self, filename, file)
