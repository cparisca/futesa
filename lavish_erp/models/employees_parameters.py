# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
import logging
import datetime
_logger = logging.getLogger(__name__)

# ÁREAS
class x_areas(models.Model):
    _name = 'lavish.areas'
    _description = 'Áreas'
    _order = 'code,name'

    code = fields.Char(string='Código', required=True)
    name = fields.Char(string='Nombre', required=True)

    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "{} | {}".format(record.code, record.name)))
        return result

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        args = args or []
        domain = []
        if name:
            domain = ['|', ('name', operator, name), ('code', operator, name)]
        areas_ids = self._search(expression.AND([domain, args]), limit=limit, access_rights_uid=name_get_uid)
        return areas_ids#self.browse(areas_ids).name_get()

# CARGOS
class x_job_title(models.Model):
    _name = 'lavish.job_title'
    _description = 'Cargos'
    _order = 'area_id,code,name'

    area_id = fields.Many2one('lavish.areas', string='Área')
    code = fields.Char(string='Código', required=True)
    name = fields.Char(string='Nombre', required=True)

    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "{} | {}".format(record.code, record.name)))
        return result

# GRUPOS DE TRABAJO
class x_work_groups(models.Model):
    _name = 'lavish.work_groups'
    _description = 'Grupos de Trabajo'

    code = fields.Char(string='Código', required=True)
    name = fields.Char(string='Nombre', required=True)

    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "{} | {}".format(record.code, record.name)))
        return result
