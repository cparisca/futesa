# -*- coding: utf-8 -*-

from odoo import tools
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class lavish_pivot_report_cxc(models.Model):
    _name = "lavish.pivot.report.cxc"
    _description = "Reporte CXC - Recaudos"
    _auto = False
    _order = 'mov_origin,date_mov'

    period = fields.Char(string='Periodo')
    date_mov = fields.Date(string='Fecha movimiento')
    journal_id = fields.Many2one('account.journal',string='Diario')
    mov_sequence = fields.Many2one('account.move',string='Secuencia')
    mov_origin = fields.Many2one('account.move',string='Movimiento origen')
    type_document = fields.Char(string='Tipo de documento')
    vat = fields.Char(string='Número de documento')
    partner_id = fields.Many2one('res.partner',string='Cliente')
    invoice_user_id = fields.Many2one('res.users', string='Vendedor')
    account_id = fields.Many2one('account.account',string='Cuenta')
    debit = fields.Float(string='Débito')
    credit = fields.Float(string='Crédito')
    balance = fields.Float(string='Balance')
    amount_untaxed_signed = fields.Float(string='Impuestos no incluidos')

    @api.model
    def _query(self):
        return f'''
                select Row_Number() Over(Order By mov_origin,date_mov) as id,* from (
                    -- MOV ORIGINAL
                    select to_char(a."date",'yyyyMM') as period,a."date" as date_mov,
                            d.id as journal_id,a.move_id as mov_sequence, a.move_id as mov_origin,
                            case when e.document_type = '13' then 'Cédula de ciudadania'
                            else case when e.document_type = '31' then 'NIT'
                            else ''
                            end 
                            end as type_document,e.vat as vat,e.id as partner_id,b.invoice_user_id,
                            --b.supplier_invoice_number as supplier_invoice_number,
                            f.id as account_id,b.amount_untaxed_signed as amount_untaxed_signed,
                            a.debit as debit,a.credit as credit,a.balance as balance	
                    from account_move_line as a
                    inner join account_move as b on a.move_id = b.id and b.state = 'posted'
                    inner join res_company as c on a.company_id = c.id
                    inner join account_journal as d on a.journal_id = d.id
                    inner join res_partner as e on a.partner_id = e.id
                    inner join account_account as f on a.account_id = f.id
                    inner join account_account_type as g on f.user_type_id = g.id and g.type in ('receivable','payable')
                    where c.id = {self.env.company.id} and b.move_type like 'out_%'
                Union
                    -- PAGOS
                    select to_char(coalesce(i."date",a."date"),'yyyyMM') as period,coalesce(i."date",a."date") as date_mov,
                            coalesce(l.id,d.id) as journal_id,coalesce(i.move_id,a.move_id) as mov_sequence, a.move_id as mov_origin,
                            case when coalesce(m.document_type,e.document_type) = '13' then 'Cédula de ciudadania'
                            else case when coalesce(m.document_type,e.document_type) = '31' then 'NIT'
                            else ''
                            end 
                            end as type_document,coalesce(m.vat,e.vat) as vat,coalesce(m.id,e.id) as partner_id,b.invoice_user_id,
                            --coalesce(j.supplier_invoice_number,b.supplier_invoice_number) as supplier_invoice_number,
                            coalesce(n.id,f.id) as account_id,b.amount_untaxed_signed as amount_untaxed_signed,
                            coalesce(i.debit,a.debit) as debit,coalesce(i.credit,a.credit) as credit,coalesce(i.balance,a.balance) as balance
                    from account_move_line as a
                    inner join account_move as b on a.move_id = b.id and b.state = 'posted'
                    inner join res_company as c on a.company_id = c.id
                    inner join account_journal as d on a.journal_id = d.id
                    inner join res_partner as e on a.partner_id = e.id
                    inner join account_account as f on a.account_id = f.id
                    inner join account_account_type as g on f.user_type_id = g.id and g.type in ('receivable','payable')
                    inner join account_partial_reconcile as h on a.id = h.debit_move_id  
                    inner join account_move_line as i on h.credit_move_id = i.id --or a.id = i.id  
                    inner join account_move as j on i.move_id = j.id and j.state = 'posted'
                    inner join res_company as k on i.company_id = k.id
                    inner join account_journal as l on i.journal_id = l.id
                    inner join res_partner as m on i.partner_id = m.id
                    inner join account_account as n on i.account_id = n.id 
                    where c.id = {self.env.company.id} and b.move_type like 'out_%'      
                ) as a
            '''

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute('''
            CREATE OR REPLACE VIEW %s AS (
                %s
            )
        ''' % (
            self._table, self._query()
        ))