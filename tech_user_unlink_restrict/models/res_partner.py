# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _check_admin_user(self):
        for rec in self:
            if rec.id in [1, 2, 3, 4, 5, 6, 7]:
                raise ValidationError(_("No se pueden borrar los usuarios Admin"))

    def unlink(self):
        self._check_admin_user()
        return super(ResPartner, self).unlink()
