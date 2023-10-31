# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api, fields, models, _

TRIBUTES = [('01','IVA'), 
            ('02','IC'), 
            ('03','ICA'), 
            ('04','INC'), 
            ('05','ReteIVA'), 
            ('06','ReteFuente'),
            ('07','ReteICA'), 
            ('08','ReteCREE'), 
            ('20','FtoHorticultura'), 
            ('21','Timbre'),
            ('22','Bolsas'), 
            ('23','INCarbono'), 
            ('24','INCombustibles'),
            ('25','Sobretasa Combustibles'), 
            ('26','Sordicom'),
            ('ZY','No causa'),
            ('ZZ','Nombre de la figura tributaria')]

class AccountTaxGroup(models.Model):
    _inherit = 'account.tax.group'

    code = fields.Char(string="Identifier")
    description = fields.Char(string="Description")
    is_percent = fields.Boolean(string="Is percent", default=True)

class AccountTax(models.Model):
    _inherit = 'account.tax'
    
    tributes = fields.Selection(TRIBUTES, string="Tributo DIAN")
    codigo_dian = fields.Char(
        string='Código DIAN',
        compute='_dian_detalle',store = True
    )

    nombre_dian = fields.Char(
        string='Nombre técnico DIAN',
        compute='_dian_detalle',store = True
    )
    description_dian = fields.Char(
        string='Descripción DIAN',
        compute='_dian_detalle',store = True
    )
    @api.depends('tributes')
    def _dian_detalle(self,):
        description = ''
        name = ''
        for rec in self:
            code = rec.tributes
            if code == '01':
                description = 'Impuesto de Valor Agregado'
                name = 'IVA'
            elif code == '02':
                description = 'Impuesto al Consumo'
                name = 'IC'
            elif code == '03':
                description = 'Impuesto de Industria, Comercio y Aviso'
                name = 'ICA'
            elif code == '04':
                description = 'Impuesto Nacional al Consumo'
                name = 'INC'
            elif code == '05':
                description = 'Retención sobre el IVA'
                name = 'ReteIVA'
            elif code == '06':
                description = 'Retención sobre Renta'
                name = 'ReteRenta'
            elif code == '07':
                description = 'Retención sobre el ICA'
                name = 'ReteICA'
            elif code == '08':
                description = 'Impuesto al Consumo Departamental Porcentual'
                name = 'IC Porcentual'
            elif code == '20':
                description = 'Cuota de Fomento Hortifrutícula'
                name = 'FtoHoticultura'
            elif code == '21':
                description = 'Impuesto de Timbre'
                name = 'Timbre'
            elif code == '22':
                description = 'Impuesto al Consumo de Bolsa Plástica'
                name = 'INC Bolsas'
            elif code == '23':
                description = 'Impuesto Nacional al Carbono'
                name = 'INCarbono'
            elif code == '24':
                description = 'Impuesto Nacional a los Combustibles'
                name = 'INCombustibles'
            elif code == '25':
                description = 'Sobretasa a los combustibles'
                name = 'Sobretasa Combustibles'
            elif code == '26':
                description = 'Contribución minoristas (Combustibles)'
                name = 'Sordicom'
            elif code == '30':
                description = 'Impuesto al Consumo de Datos'
                name = 'IC Datos'
            elif code == 'ZZ':
                description = 'Otros Tributos, tasas, contribuciones, y similares'
                name = 'Nombre de la figura tributaria'
            else:
                description = ''
                name = ''
        rec.codigo_dian = code
        rec.description_dian = description
        rec.nombre_dian = name
