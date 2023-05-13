# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.

from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    category = fields.Boolean('Category')
    sub_category = fields.Boolean('Sub Category')
    customer_rating = fields.Boolean('Customer Rating')
    close_days = fields.Integer('No of Days')

    new_stage_id = fields.Many2one('helpdesk.stage', string="Draft/New Stage")
    done_stage_id = fields.Many2one('helpdesk.stage', string="Resolved Stage")
    cancel_stage_id = fields.Many2one('helpdesk.stage', string="Cancel Stage")
    reopen_stage_id = fields.Many2one('helpdesk.stage',
                                      string="Re-Opened Stage")
    close_stage_id = fields.Many2one('helpdesk.stage', string="Closed Stage")
    sh_customer_replied = fields.Boolean(
        'Stage change when customer replied ?')
    sh_customer_replied_stage_id = fields.Many2one(
        'helpdesk.stage', string='Customer Replied Stage')
    sh_staff_replied = fields.Boolean('Stage change when staff replied ?')
    sh_staff_replied_stage_id = fields.Many2one('helpdesk.stage',
                                                string='Staff Replied Stage')
    allocation_mail_template_id = fields.Many2one(
        'mail.template', string='Ticket Allocation To User Mail Template',domain=[('model_id', '=', 'helpdesk.ticket')])
    reply_mail_template_id = fields.Many2one(
        'mail.template', string='Ticket Reply Mail Template',domain=[('model_id', '=', 'helpdesk.ticket')])
    sh_receive_email_seeing_ticket = fields.Boolean(
        'Get email when customer view ticket ?')
    sh_display_multi_user = fields.Boolean('Display Multi Users ?')
    sh_configure_activate = fields.Boolean('Manage Multi Products')
    sh_display_ticket_reminder = fields.Boolean('Ticket Reminder ?')
    access_for_everyone = fields.Boolean(string='Access For Everyone')
    sh_ticket_product_detail = fields.Boolean(
        "Ticket Product details in Message?", default=True)
    sh_pdf_in_message = fields.Boolean("Send Report URL in Message?",
                                       default=True)
    sh_ticket_url_in_message = fields.Boolean("Send Ticket URL in Message?",
                                              default=True)
    sh_signature = fields.Boolean("Signature?", default=True)
    sh_display_in_chatter = fields.Boolean("Display in Chatter Message?",
                                           default=True)
    sh_file_size = fields.Integer('Portal Attachment Size(KB)')
    

class HelpdeskSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    access_for_everyone = fields.Boolean(
        string='Portal View Ticket with Access Token',
        related='company_id.access_for_everyone',
        readonly=False)
    sh_pdf_in_message = fields.Boolean("Send Report URL in Message?",
                                       related='company_id.sh_pdf_in_message',
                                       readonly=False)
    sh_ticket_url_in_message = fields.Boolean(
        "Send Ticket URL in Message?",
        related='company_id.sh_ticket_url_in_message',
        readonly=False)
    sh_display_in_chatter = fields.Boolean(
        "Display in Chatter Message?",
        related='company_id.sh_display_in_chatter',
        readonly=False)
    sh_signature = fields.Boolean("Signature?",
                                  related='company_id.sh_signature',
                                  readonly=False)
    sh_ticket_product_detail = fields.Boolean(
        "Ticket Product details in Message?",
        related='company_id.sh_ticket_product_detail',
        readonly=False)
    company_id = fields.Many2one('res.company',
                                 string='Company',
                                 required=True,
                                 default=lambda self: self.env.company)
    category = fields.Boolean(string='Category',
                              related='company_id.category',
                              readonly=False)
    sub_category = fields.Boolean(string='Sub Category',
                                  related='company_id.sub_category',
                                  readonly=False)
    customer_rating = fields.Boolean(string='Customer Rating',
                                     related='company_id.customer_rating',
                                     readonly=False)
    close_days = fields.Integer(string='No of Days',
                                related='company_id.close_days',
                                readonly=False)
    new_stage_id = fields.Many2one('helpdesk.stage',
                                   string="Draft/New Stage",
                                   related='company_id.new_stage_id',
                                   readonly=False)
    done_stage_id = fields.Many2one('helpdesk.stage',
                                    string="Resolved Stage",
                                    related='company_id.done_stage_id',
                                    readonly=False)
    cancel_stage_id = fields.Many2one('helpdesk.stage',
                                      string="Cancel Stage",
                                      related='company_id.cancel_stage_id',
                                      readonly=False)
    allocation_mail_template_id = fields.Many2one(
        'mail.template',
        string='Ticket Allocation To User Mail Template',
        related='company_id.allocation_mail_template_id',
        readonly=False)
    reply_mail_template_id = fields.Many2one(
        'mail.template',
        string='Ticket Reply Mail Template',
        related='company_id.reply_mail_template_id',
        readonly=False)
    reopen_stage_id = fields.Many2one('helpdesk.stage',
                                      string="Re-Opened Stage",
                                      readonly=False,
                                      related='company_id.reopen_stage_id')
    close_stage_id = fields.Many2one('helpdesk.stage',
                                     string="Closed Stage",
                                     readonly=False,
                                     related='company_id.close_stage_id')

    sh_display_multi_user = fields.Boolean(
        'Display Multi Users ?',
        related='company_id.sh_display_multi_user',
        readonly=False)
    sh_configure_activate = fields.Boolean(
        'Manage Multi Products',
        related='company_id.sh_configure_activate',
        readonly=False)
    sh_display_ticket_reminder = fields.Boolean(
        'Ticket Reminder ?',
        related='company_id.sh_display_ticket_reminder',
        readonly=False)

    sh_customer_replied = fields.Boolean(
        'Stage change when customer replied ?',
        related='company_id.sh_customer_replied',
        readonly=False)
    sh_customer_replied_stage_id = fields.Many2one(
        'helpdesk.stage',
        string='Customer Replied Stage',
        related='company_id.sh_customer_replied_stage_id',
        readonly=False)
    sh_staff_replied = fields.Boolean('Stage change when staff replied ?',
                                      related='company_id.sh_staff_replied',
                                      readonly=False)
    sh_staff_replied_stage_id = fields.Many2one(
        'helpdesk.stage',
        string='Staff Replied Stage',
        related='company_id.sh_staff_replied_stage_id',
        readonly=False)
    sh_file_size = fields.Integer('Portal Attachment Size(KB)',
                                  related='company_id.sh_file_size',
                                  readonly=False)
   