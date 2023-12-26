# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, tools

#class loan_report(models.Model):
#    _name = "loan.report"
#    _rec_name = 'date'

class InstallmentAnalyticLineView(models.Model):
    _name = 'installment.analytic.line.view'
    _table = 'installment_analytic_line_view'
    _description = "Installment Analytic Line View"
    _auto = False
    _rec_name = "date"
    
    
    name = fields.Char('Name')
    employee_id = fields.Many2one('hr.employee',string='Employee')
    loan_id = fields.Many2one('employee.loan',string='Loan',required="1", ondelete='cascade')
    date = fields.Date('Date')
    is_paid = fields.Boolean('Paid')
    amount = fields.Float('Loan Amount')
    interest = fields.Float('Total Interest')
    ins_interest = fields.Float('Interest')
    installment_amt = fields.Float('Installment Amt')
#    total_installment = fields.Float('Total')
#    total_installment = fields.Float('Total',compute='get_total_installment')
    payslip_id = fields.Many2one('hr.payslip',string='Payslip')
    is_skip = fields.Boolean('Skip Installment')
    
#    @api.depends('installment_amt','ins_interest')
#    def get_total_installment(self):
#        print ("self=======",self)
#        for line in self:
#            print ("line=======",line)
#            line.total_installment = line.ins_interest + line.installment_amt
    
    def init(self):
        tools.drop_view_if_exists(self._cr, 'installment_analytic_line_view')
        self._cr.execute("""
          CREATE OR REPLACE VIEW installment_analytic_line_view AS
          SELECT l.id,
                 l.name,
                 l.loan_id,
                 l.employee_id,
                 l.date,
                 l.is_paid,
                 l.amount,
                 l.interest,
                 l.ins_interest,
                 l.installment_amt,
                 l.payslip_id,
                 l.is_skip
          FROM installment_line l;
                    """)


#    @api.model_cr
#    def init(self):
#        #self._table = sale_report
#        tools.drop_view_if_exists(self._cr, 'installment_analytic_line_view')
#        
#        self._cr.execute("""CREATE or REPLACE VIEW loan_report_asign AS ( SELECT
#        MIN(id) as id,
#            p.name as name,
#            p.employee_id as employee_id,
#            p.date as date,
#            p.is_paid as is_paid,
#            p.amount as amount,
#            p.interest as interest,
#            p.ins_interest as ins_interest,
#            p.installment_amt as installment_amt,
#            p.payslip_id as payslip_id,
#            p.is_skip as is_skip
#            
#        FROM installment_line p
#        group by p.id
#         )""")
        
            
