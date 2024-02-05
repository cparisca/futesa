# -*- coding: utf-8 -*-
import babel
import time
from datetime import datetime

from odoo import models, fields, api, tools, _


class HrPayslipInput(models.Model):
    _inherit = 'hr.payslip.input'

    loan_line_id = fields.Many2one('hr.loan.line', string="Cuotas de préstamo", help="Cuota de préstamo")
    desc = fields.Char("Razón")


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'


    total_amount_paid = fields.Float(string="Total Loan Amount")
    loan_line_ids = fields.One2many('hr.loan.line', 'payslip_id', string="Cuotas de préstamo", help="Cuota de préstamo")
    def get_inputs(self, date_from, date_to,process):
        """This Compute the other inputs to employee payslip. """
        res = []
        lon_obj = self.env['hr.loan'].search([('employee_id', '=', self.employee_id.id)])
        input_type = self.env['hr.payslip.input.type']
        for loan in lon_obj:
            total = 0.0
            total_paid = 0.0
            for loan_line in loan.loan_lines:
                if not loan_line.paid:
                    total_paid += loan_line.amount
                if date_from <= loan_line.date <= date_to and not loan_line.paid and process == 'nomina':
                    total += loan_line.amount
                    input_type_id = input_type.search([('code', '=', loan_line.loan_id.loan_type_id.rule_code)], limit=1)
                    if input_type_id:
                        vals = {
                            'input_type_id': input_type_id.id,
                            'name': loan_line.loan_id.loan_type_id.name,
                            'code': loan_line.loan_id.loan_type_id.rule_code,
                            'loan_line_id': loan_line.id,
                            'desc': loan_line.loan_id.reason,
                            'amount': total,
                        }
                        res.append((0, 0, vals))
                if not loan_line.paid and process == 'contrato':
                    total += loan_line.amount
                    input_type_id = input_type.search([('code', '=', loan_line.loan_id.loan_type_id.rule_code)], limit=1)
                    if input_type_id:
                        vals = {
                            'input_type_id': input_type_id.id,
                            'name': loan_line.loan_id.loan_type_id.name,
                            'code': loan_line.loan_id.loan_type_id.rule_code,
                            'loan_line_id': loan_line.id,
                            'desc': loan_line.loan_id.reason,
                            'amount': total,
                        }
                        res.append((0, 0, vals))
                self.total_amount_paid = total_paid
        return res
