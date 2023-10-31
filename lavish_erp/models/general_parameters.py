# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import datetime
_logger = logging.getLogger(__name__)


# Fechas comemorativas
class lavish_dates_commemorated(models.Model):
    _name = 'lavish.dates.commemorated'
    _description = 'Fechas conmemorativas'

    name = fields.Char('Descripción', required=True)
    date = fields.Date('Fecha', required=True)

    _sql_constraints = [('date_commemorated_uniq', 'unique(date)', 'Ya existe un día conmemorativo en esta fecha, por favor verificar.')]

# Dias festivos
class lavishHolidays(models.Model):
    _name = 'lavish.holidays'
    _description = 'Días festivos'

    name = fields.Char('Descripción', required=True)
    date = fields.Date('Fecha', required=True)

    _sql_constraints = [('date_holiday_uniq', 'unique(date)', 'Ya existe un día festivo en esta fecha, por favor verificar.')]

#Codigo postal
class lavishZipCode(models.Model):
    _name = 'lavish.zip.code'
    _rec_name = 'code'
    _description = 'Código postal'

    code = fields.Char('Código', required=True)

    _sql_constraints = [('zip_postal_uniq', 'unique(code)', 'Ya existe ese código postal, por favor verificar.')]

# CIIU
class Ciiu(models.Model):
    _name = 'lavish.ciiu'
    _parent_store = True
    _parent_name  = 'parent_id'
    _description = 'CIIU - Actividades economicas'

    code = fields.Char('Codigo', required=True)
    name = fields.Char('Name', required=True)
    porcent_ica = fields.Float(string='Porcentaje ICA')
    parent_id = fields.Many2one('lavish.ciiu','Parent Tag', ondelete='cascade')
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('lavish.ciiu', 'parent_id', 'Child Tags')    
    
    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "{}".format(record.name)))
        return result

# SECTORES
class Sectors(models.Model):
    _name = 'lavish.sectors'
    _description = 'Sectores'

    code = fields.Char(string='Código', required=True)
    name = fields.Char(string='Nombre', required=True)

    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "{} | {}".format(record.code, record.name)))
        return result

# TIPOS DE VINCULACION
class x_vinculation_types(models.Model):
    _name = 'lavish.vinculation_types'
    _description = 'Tipos de vinculación'

    code = fields.Char(string='Código', required=True)
    name = fields.Char(string='Nombre', required=True)
    active = fields.Boolean(string='Activo')
    
    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "{} | {}".format(record.code, record.name)))
        return result

# RESPONSABILIDADES RUT
class x_responsibilities_rut(models.Model):
    _name = 'lavish.responsibilities_rut'
    _description = 'Responsabilidades RUT'

    code = fields.Char(string='Identificador', size=10, required=True)
    description = fields.Char(string='Descripción', size=100, required=True)
    valid_for_fe = fields.Boolean(string='Valido para facturación electrónica')
    
    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "{} | {}".format(record.code, record.description)))
        return result

# TIPOS DE CONTACTO
class x_contact_types(models.Model):
    _name = 'lavish.contact_types'
    _description = 'Tipos de contacto'
    
    code = fields.Char(string='Código', required=True)
    name = fields.Char(string='Nombre', required=True)

    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "{} | {}".format(record.code, record.name)))
        return result

# TIPOS DE TERCERO
class x_type_thirdparty(models.Model):
    _name = 'lavish.type_thirdparty'
    _description = 'Tipos de tercero'
    
    code = fields.Char(string='Código', required=True)
    name = fields.Char(string='Nombre', required=True)
    is_company = fields.Boolean('¿Es un tipo de tercero compañia?')
    is_individual = fields.Boolean('¿Es un tipo de tercero individual?')
    types = fields.Selection([('1', 'Cliente / Cuenta'),
                              ('2', 'Contacto'),
                              ('3', 'Proveedor'),
                              ('4', 'Funcionario / Contratista'),
                              ('5', 'Candidato')], string='Tipo', required=True)
    fields_mandatory = fields.Many2many('ir.model.fields', domain="[('model', '=', 'res.partner'),('ttype', 'not in', ['many2many','one2many'])]", string='Campos obligatorios')

    _sql_constraints = [('type_thirdparty_uniq', 'unique(types)',
                         'Ya existe un tipo de tercero de este tipo, por favor verificar.')]

    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "{}".format(record.name)))
        return result

# Racngos de activos
class x_asset_range(models.Model):
    _name = 'lavish.asset_range'
    _description = 'Rangos de activos'
    
    initial_value = fields.Float(string='Valor inicial', required=True)
    final_value = fields.Float(string='Valor final', required=True)
    name = fields.Char(string='Nombre', required=True)
    active = fields.Boolean(string='Activo')
    
    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "{}".format(record.name)))
        return result

# Grupo Presupuestal
class x_budget_group(models.Model):
    _name = 'lavish.budget_group'
    _description = 'Grupos presupuestal'

    code = fields.Char(string='Código', required=True)
    name = fields.Char(string='Nombre', required=True)
     
    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "{}".format(record.name)))
        return result