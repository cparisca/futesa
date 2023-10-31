from odoo import models, fields, api, _

class account_tax_type(models.Model):
    _name = 'account.tax.type'
    _description = 'Tipo de Impuestos'

    code = fields.Char('Código')
    name = fields.Char('Descripción')
    retention = fields.Boolean('Retención')
    not_iclude = fields.Boolean('No incluir en FE')

class account_tax(models.Model):
    _inherit = 'account.tax'

    tax_type = fields.Many2one('account.tax.type', 'Tipo de Impuestos')