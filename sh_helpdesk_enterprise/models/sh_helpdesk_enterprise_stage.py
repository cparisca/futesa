# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.

from odoo import api, fields, models


class HelpdeskStage(models.Model):
    _inherit = "helpdesk.stage"

    sh_next_stage = fields.Many2one(
        comodel_name='helpdesk.stage',
        string='Next Stage',
    )

    sh_group_ids = fields.Many2many(
        comodel_name='res.groups',
        string='Groups'
    )
    is_cancel_button_visible = fields.Boolean(
        string='Is Cancel Button Visible ?'
    )
    is_done_button_visible = fields.Boolean(
        string='Is Resolved Button Visible ?'
    )
