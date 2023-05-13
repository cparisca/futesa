# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import fields, models


class MassUpdateWizard(models.TransientModel):

    _name = "sh.helpdesk.ticket.mass.update.wizard"
    _description = "Mass Update Wizard"

    helpdesks_ticket_ids = fields.Many2many(comodel_name='helpdesk.ticket')
    check_assign_to = fields.Boolean(string='Assign To ', default=False)
    assign_to = fields.Many2one(comodel_name='res.users',
                                string='Assign To',
                                domain=[('share', '=', False)])
    check_sh_display_multi_user = fields.Boolean()
    check_assign_to_multiuser = fields.Boolean(default=False,
                                               string="Assign Multi User")
    ticket_update_type = fields.Selection([
        ('add', 'Add'),
        ('replace', 'Replace'),
    ],
                                          default="add",
                                          string="Ticket Type Update ")
    assign_to_multiuser = fields.Many2many('res.users',
                                           string="Assign Multi Users",
                                           domain=[('share', '=', False)])

    check_helpdesks_state = fields.Boolean(default=False, string="Stage")
    helpdesk_stages = fields.Many2one('helpdesk.stage', string="Stages")

    check_add_remove = fields.Boolean(string="Add/Remove", default=False)
    followers = fields.Many2many('res.partner', string="Followers")

    ticket_follower_update_type = fields.Selection([
        ('add', 'Add'),
        ('remove', 'Remove'),
    ],
                                                   default="add",
                                                   string="Ticket Type Update")

    def update_record(self):

        # <-- ASSIGN TO UPDATE -->
        if self.check_assign_to:
            self.helpdesks_ticket_ids.write({'user_id': self.assign_to.id})

        # <-- ASSIGN MULTIUSER UPDATE -->

        if self.check_assign_to_multiuser:

            if self.ticket_update_type == 'add':
                get_list = []
                for rec in self.helpdesks_ticket_ids.sh_user_ids:
                    if rec:
                        get_list.append(rec.id)
                for rec1 in self.assign_to_multiuser:
                    if rec1:
                        get_list.append(rec1.id)
                self.helpdesks_ticket_ids.write(
                    {'sh_user_ids': [(6, 0, get_list)]})

            if self.ticket_update_type == "replace":
                self.helpdesks_ticket_ids.write(
                    {'sh_user_ids': [(6, 0, self.assign_to_multiuser.ids)]})

        # <-- STATE UPDATE -->

        if self.check_helpdesks_state:
            for rec in self.helpdesks_ticket_ids:
                if self.helpdesk_stages:
                    rec.stage_id = self.helpdesk_stages.id

        # <-- ADD/REMOVE FOLLOWER UPDATE -->

        for rec in self.helpdesks_ticket_ids:
            ids_list = []
            if self.ticket_follower_update_type == "add":
                rec.message_subscribe(partner_ids=self.followers.ids)
            if self.ticket_follower_update_type == "remove":
                for follower in self.followers.ids:
                    if follower in rec.message_partner_ids.ids:
                        ids_list.append(follower)
                        final_list = ids_list
                        rec.message_unsubscribe(partner_ids=final_list)
