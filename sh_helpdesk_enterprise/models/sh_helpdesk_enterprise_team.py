# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.

from odoo import api, fields, models


class HelpdeskTeam(models.Model):
    _inherit = "helpdesk.team"

    sh_resource_calendar_id = fields.Many2one(
        'resource.calendar', string="Working Schedule", required=True, default=lambda self: self.env.company.resource_calendar_id)
