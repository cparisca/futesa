# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class account_journal(models.Model):
    _inherit = 'account.journal'

    type = fields.Selection(tracking=True)
    company_id = fields.Many2one(tracking=True)
    code = fields.Char(tracking=True)
    sequence_number_next = fields.Integer(tracking=True)
    default_account_id = fields.Many2one(tracking=True)

class ProductTemplate(models.Model):
    _inherit = "product.template"

    income_return_account = fields.Many2one('account.account',string='Cuenta devolución de ingresos')

    account_analytic_id = fields.Many2one('account.analytic.account', string='Cuenta analitica', tracking=True)

    @api.model
    def create(self, vals):
        res = super(ProductTemplate, self).create(vals)
        for record in res:
            if record.account_analytic_id:
                obj_product_product = self.env['product.product'].search([('product_tmpl_id', '=', record.id)])
                obj_account_analytic_default = self.env['account.analytic.default'].search(
                    [('product_id', 'in', obj_product_product.ids)])
                if len(obj_account_analytic_default) > 0:
                    obj_account_analytic_default.write({'analytic_id': record.account_analytic_id.id})
                else:
                    for p in obj_product_product:
                        self.env['account.analytic.default'].create({'analytic_id': record.account_analytic_id.id,
                                                                     'product_id': p.id})
        return res

    def write(self, vals):
        res = super(ProductTemplate, self).write(vals)
        for record in self:
            if record.account_analytic_id:
                obj_product_product = self.env['product.product'].search([('product_tmpl_id','=',record.id)])
                obj_account_analytic_default = self.env['account.analytic.default'].search([('product_id','in',obj_product_product.ids)])
                if len(obj_account_analytic_default) > 0:
                    obj_account_analytic_default.write({'analytic_id':record.account_analytic_id.id})
                else:
                    for p in obj_product_product:
                        self.env['account.analytic.default'].create({'analytic_id':record.account_analytic_id.id,
                                                                    'product_id':p.id})
        return res

class account_move(models.Model):
    _inherit = 'account.move'

    @api.model
    def create(self, vals):
        invoice = super(account_move, self).create(vals)

        for lines in invoice.line_ids:
            if lines.move_id.move_type in ['out_refund', 'in_refund']:
                if lines.product_id.product_tmpl_id.income_return_account:
                    lines.account_id = lines.product_id.product_tmpl_id.income_return_account.id

        return invoice


class AccountMoveReversal(models.TransientModel):
    _inherit = "account.move.reversal"

    def reverse_moves(self):
        obj_reversal = super(AccountMoveReversal, self).reverse_moves()

        if 'res_id' in obj_reversal:
            obj_lines = self.env['account.move.line'].search([('move_id', '=', obj_reversal['res_id']), ('product_id', '!=', False), ('product_id.product_tmpl_id.income_return_account', '!=', False)])
            for lines in obj_lines:
                if lines.move_id.move_type in ['out_refund', 'in_refund']:
                    if lines.product_id.product_tmpl_id.income_return_account:
                        lines.account_id = lines.product_id.product_tmpl_id.income_return_account.id
