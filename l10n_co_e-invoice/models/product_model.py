# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class ProductModel(models.Model):
    _name = 'product.model'
    _description = 'Modelo para los modelos de los productos'

    name = fields.Char(string="Nombre", required=True)
    active = fields.Boolean(string="Active", default=True)

    product_ids = fields.One2many(
        'product.template', 
        'model_id', string = 'Productos')


    @api.constrains('name')
    def _check_model_name(self):
        if self.search_count([('name', 'ilike', self.name)]) > 1:
            raise ValidationError('Ya hay un modelo con este nombre')
