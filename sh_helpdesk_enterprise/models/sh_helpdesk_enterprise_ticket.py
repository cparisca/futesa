# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.

from odoo import models, fields, api, _, SUPERUSER_ID, tools
from datetime import datetime
from odoo.exceptions import UserError, ValidationError
import random
from odoo.tools import email_re
from datetime import timedelta
import uuid


class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    state = fields.Selection([('customer_replied', 'Customer Replied'),
                              ('staff_replied', 'Staff Replied')],
                             string="Replied Status",
                             default='customer_replied',
                             required=True,
                             tracking=True)

    sh_user_ids = fields.Many2many('res.users', string="Assign Multi Users",domain=lambda self: [('groups_id', 'in', self.env.ref('helpdesk.group_helpdesk_user').id)])
    sh_due_date = fields.Datetime(
        'Reminder Due Date', default=datetime.today())
    category_id = fields.Many2one('sh.helpdesk.category',
                                  string="Category",
                                  tracking=True)
    sub_category_id = fields.Many2one('sh.helpdesk.subcategory',
                                      string="Sub Category")
    person_name = fields.Char(string='Person Name', tracking=True)
    replied_date = fields.Datetime('Replied Date', tracking=True)
    sh_ticket_alarm_ids = fields.Many2many('sh.ticket.alarm',
                                           string='Ticket Reminders')
    close_date = fields.Datetime(string='Close Date', tracking=True)
    close_by = fields.Many2one('res.users', string='Closed By', tracking=True)
    comment = fields.Text(string="Comment", tracking=True, translate=True)
    cancel_date = fields.Datetime(string='Cancelled Date', tracking=True)
    cancel_by = fields.Many2one('res.users',
                                string='Cancelled By',
                                tracking=True)
    product_ids = fields.Many2many('product.product', string='Products')
    cancel_reason = fields.Char("Cancel Reason", tracking=True, translate=True)
    priority_new = fields.Selection([('none', 'No Rating yet'),('ko', 'Dissatisfied'),
        ('ok', 'Okay'),('top', 'Satisfied')],
        string="Customer Rating",tracking=True,compute='_compute_rating')
    customer_comment = fields.Text("Customer Comment", tracking=True,compute='_compute_rating')
    done_stage_boolean = fields.Boolean('Done Stage',
                                        compute='_compute_stage_booleans',
                                        store=True)
    cancel_stage_boolean = fields.Boolean('Cancel Stage',
                                          compute='_compute_stage_booleans',
                                          store=True)
    reopen_stage_boolean = fields.Boolean('Reopened Stage',
                                          compute='_compute_stage_booleans',
                                          store=True)
    closed_stage_boolean = fields.Boolean('Closed Stage',
                                          compute='_compute_stage_booleans',
                                          store=True)
    open_boolean = fields.Boolean('Open Ticket',
                                  compute='_compute_stage_booleans',
                                  store=True)

    ticket_from_website = fields.Boolean('Ticket From Website')
    cancel_button_boolean = fields.Boolean(
        "Cancel Button",
        compute='_compute_cancel_button_boolean',
        search='_search_cancel_button_boolean')
    done_button_boolean = fields.Boolean(
        "Done Button",
        compute='_compute_done_button_boolean',
        search='_search_done_button_boolean')
    sh_display_multi_user = fields.Boolean(
        compute="_compute_sh_display_multi_user")

    category_bool = fields.Boolean(string='Category Setting',
                                   related='company_id.category',
                                   store=True)
    sub_category_bool = fields.Boolean(string='Sub Category Setting',
                                       related='company_id.sub_category',
                                       store=True)
    rating_bool = fields.Boolean(string='Rating Setting',
                                 related='company_id.customer_rating', store=True)
    sh_display_product = fields.Boolean(compute='_compute_sh_display_product')
    ticket_allocated = fields.Boolean("Allocated")
    description = fields.Html(string="Description")
    sh_ticket_report_url = fields.Char(compute='_compute_report_url')
    report_token = fields.Char("Access Token")
    portal_ticket_url_wp = fields.Char(compute='_compute_ticket_portal_url_wp')
    form_url = fields.Char('Form Url', compute='_compute_form_url')

    def _compute_form_url(self):
        if self:
            base_url = self.env['ir.config_parameter'].sudo().get_param(
                'web.base.url')
            url_str = ''
            action = self.env.ref('helpdesk.helpdesk_ticket_action_main_my').id
            if base_url:
                url_str += str(base_url) + '/web#'
            for rec in self:
                url_str += 'id='+str(rec.id)+'&action='+str(action) + \
                    '&model=helpdesk.ticket&view_type=form'
                rec.form_url = url_str

    def _compute_ticket_portal_url_wp(self):
        for rec in self:
            rec.portal_ticket_url_wp = False
            if rec.company_id.sh_pdf_in_message:
                base_url = self.env['ir.config_parameter'].sudo().get_param(
                    'web.base.url')
                ticket_url = base_url + rec.get_portal_url()
                self.sudo().write({'portal_ticket_url_wp': ticket_url})

    def _get_token(self):
        """ Get the current record access token """
        if self.report_token:
            return self.report_token
        else:
            report_token = str(uuid.uuid4())
            self.write({'report_token': report_token})
            return report_token

    def get_download_report_url(self):
        url = ''
        if self.id:
            self.ensure_one()
            url = '/download/ht/' + '%s?access_token=%s' % (self.id,
                                                            self._get_token())
        return url

    def _compute_report_url(self):
        for rec in self:
            rec.sh_ticket_report_url = False
            if rec.company_id.sh_pdf_in_message:
                base_url = self.env['ir.config_parameter'].sudo().get_param(
                    'web.base.url')
                ticket_url = "%0A%0A Click here to download Ticket Document : %0A" + \
                    base_url+rec.get_download_report_url()
                self.sudo().write({
                    'sh_ticket_report_url':
                    base_url + rec.get_download_report_url()
                })

    def _track_template(self, changes):
        res = super(HelpdeskTicket, self)._track_template(changes)
        ticket = self[0]
        if 'stage_id' in changes and ticket.stage_id.template_id:
            template_ids = []
            template_ids.append(self.env.ref(
                'sh_helpdesk_enterprise.sh_ticket_done_template_enterprise').id)
            template_ids.append(self.env.ref(
                'sh_helpdesk_enterprise.sh_ticket_cancelled_template_enterprise').id)
            template_ids.append(self.env.ref(
                'sh_helpdesk_enterprise.sh_ticket_reopened_template_enterprise').id)
            template_ids.append(self.env.ref(
                'sh_helpdesk_enterprise.sh_ticket_user_allocation_template_enterprise').id)
            if ticket.stage_id.template_id.id in template_ids:
                res['stage_id'] = (ticket.stage_id.template_id, {
                    'auto_delete_message': False,
                    'subtype_id': False,
                    'email_layout_xmlid': 'custom_layout'
                }
                )
        return res

    def action_send_whatsapp(self):
        self.ensure_one()
        if not self.partner_id.mobile:
            raise UserError(_("Partner Mobile Number Not Exist !"))
        template = self.env.ref(
            'sh_helpdesk_enterprise.sh_send_whatsapp_email_template')

        ctx = {
            'default_model': 'helpdesk.ticket',
            'default_res_id': self.ids[0],
            'default_use_template': bool(template.id),
            'default_template_id': template.id,
            'default_composition_mode': 'comment',
            'custom_layout': "mail.mail_notification_paynow",
            'force_email': True,
            'default_is_wp': True,
        }
        attachment_ids = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'helpdesk.ticket'),
            ('res_id', '=', str(self.id))
        ])
        if attachment_ids:
            ctx.update({'attachment_ids': [(6, 0, attachment_ids.ids)]})
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': ctx,
        }

    def _get_report_base_filename(self):
        self.ensure_one()
        return '%s %s' % ('Ticket', self.name)

    def preview_ticket(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': self.get_portal_url(),
        }

    def action_mass_update_wizard(self):
        return {
            'name': 'Mass Update Ticket',
            'res_model': 'sh.helpdesk.ticket.mass.update.wizard',
            'view_mode': 'form',
            'context': {
                'default_helpdesks_ticket_ids': [(6, 0, self.env.context.get('active_ids'))],
                'default_check_sh_display_multi_user': self.env.user.company_id.sh_display_multi_user
            },
            'target': 'new',
            'type': 'ir.actions.act_window',
        }

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        if self.partner_id:
            self.person_name = self.partner_id.name
            self.email = self.partner_id.email
            self.partner_phone = self.partner_id.phone
        else:
            self.person_name = False
            self.email = False
            self.partner_phone = False

    @api.model
    def create(self, vals):
        if not vals.get('partner_id') and vals.get('email', False):
            emails = email_re.findall(vals.get('email') or '')
            email = emails and emails[0] or ''
            name = str(vals.get('email')).split('"')
            partner_id = self.env['res.partner'].create({
                'name':
                name[1],
                'email':
                email,
                'company_type':
                'person',
            })
            vals.update({
                'partner_id': partner_id.id,
                'email': email,
                'person_name': partner_id.name,
            })
        number = random.randrange(1, 10)
        company_id = self.env.company
        if 'company_id' in vals:
            self = self.with_company(vals['company_id'])
        if company_id.new_stage_id:
            vals['stage_id'] = company_id.new_stage_id.id

        vals['color'] = number
        res = super(HelpdeskTicket, self).create(vals)
        return res

    @api.depends('company_id')
    def _compute_sh_display_product(self):
        if self:
            for rec in self:
                rec.sh_display_product = False
                if rec.company_id and rec.company_id.sh_configure_activate:
                    rec.sh_display_product = True

    @api.onchange('category_id')
    def onchange_category(self):
        if self.category_id:
            sub_category_ids = self.env['sh.helpdesk.subcategory'].sudo().search([
                ('parent_category_id', '=', self.category_id.id)
            ]).ids
            return {
                'domain': {
                    'sub_category_id': [('id', 'in', sub_category_ids)]
                }
            }
        else:
            self.sub_category_id = False

    @api.depends('company_id')
    def _compute_sh_display_multi_user(self):
        if self:
            for rec in self:
                rec.sh_display_multi_user = False
                if rec.company_id and rec.company_id.sh_display_multi_user:
                    rec.sh_display_multi_user = True

    @api.depends('stage_id')
    def _compute_cancel_button_boolean(self):
        if self:
            for rec in self:
                rec.cancel_button_boolean = False
                if rec.stage_id.is_cancel_button_visible:
                    rec.cancel_button_boolean = True

    @api.depends('stage_id')
    def _compute_done_button_boolean(self):
        if self:
            for rec in self:
                rec.done_button_boolean = False
                if rec.stage_id.is_done_button_visible:
                    rec.done_button_boolean = True

    @api.depends('stage_id')
    def _compute_stage_booleans(self):
        if self:
            for rec in self:
                rec.cancel_stage_boolean = False
                rec.done_stage_boolean = False
                rec.reopen_stage_boolean = False
                rec.closed_stage_boolean = False
                rec.open_boolean = False
                if rec.stage_id.id == rec.company_id.cancel_stage_id.id:
                    rec.cancel_stage_boolean = True
                    rec.open_boolean = True
                elif rec.stage_id.id == rec.company_id.done_stage_id.id:
                    rec.done_stage_boolean = True
                    rec.open_boolean = True
                elif rec.stage_id.id == rec.company_id.reopen_stage_id.id:
                    rec.reopen_stage_boolean = True
                    rec.open_boolean = False
                elif rec.stage_id.id == rec.company_id.close_stage_id.id:
                    rec.closed_stage_boolean = True
                    rec.open_boolean = True

    def action_approve(self):
        self.ensure_one()
        if self.stage_id.sh_next_stage:
            self.stage_id = self.stage_id.sh_next_stage.id

    def action_reply(self):
        self.ensure_one()
        ir_model_data = self.env['ir.model.data']
        template_id = self.company_id.reply_mail_template_id.id
        try:
            compose_form_id = ir_model_data._xmlid_lookup(
                'mail.email_compose_message_wizard_form')[2]
        except ValueError:
            compose_form_id = False
        ctx = {
            'default_model': 'helpdesk.ticket',
            'default_res_id': self.ids[0],
            'default_use_template': bool(template_id),
            'default_template_id': template_id,
            'default_composition_mode': 'comment',
            'force_email': True
        }
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form_id, 'form')],
            'view_id': compose_form_id,
            'target': 'new',
            'context': ctx,
        }

    def action_done(self):
        self.ensure_one()
        self.stage_id = self.company_id.done_stage_id.id

    def action_closed(self):
        self.ensure_one()

        self.write({
            'close_date': datetime.today(),
            'close_by': self.env.user.id,
            'closed_stage_boolean': True,
            'stage_id': self.company_id.close_stage_id.id
        })

    def action_cancel(self):
        self.ensure_one()
        stage_id = self.company_id.cancel_stage_id
        self.stage_id = stage_id.id
        self.cancel_date = fields.Datetime.now()
        self.cancel_by = self.env.user.id
        self.cancel_stage_boolean = True

    def action_open(self):
        self.write({
            'stage_id': self.company_id.reopen_stage_id.id,
            'open_boolean': True,
        })

    def write(self, vals):
        if vals.get('state'):
            if vals.get('state') == 'customer_replied':
                if self.env.user.company_id.sh_customer_replied:
                    for rec in self:
                        if rec.stage_id.id != self.env.user.company_id.new_stage_id.id:
                            vals.update({
                                'stage_id':
                                self.env.user.company_id.
                                sh_customer_replied_stage_id.id
                            })
            elif vals.get('state') == 'staff_replied':
                if self.env.user.company_id.sh_staff_replied:
                    for rec in self:
                        if rec.stage_id.id != self.env.user.company_id.new_stage_id.id:
                            vals.update({
                                'stage_id':
                                self.env.user.company_id.
                                sh_staff_replied_stage_id.id
                            })

        user_groups = self.env.user.groups_id.ids
        if vals.get('stage_id'):
            stage_id = self.env['helpdesk.stage'].sudo().search(
                [('id', '=', vals.get('stage_id'))], limit=1)
            if stage_id and stage_id.sh_group_ids:
                is_group_exist = False
                list_user_groups = user_groups
                list_stage_groups = stage_id.sh_group_ids.ids
                for item in list_stage_groups:
                    if item in list_user_groups:
                        is_group_exist = True
                        break
                if not is_group_exist:
                    raise UserError(
                        _('You have not access to edit this support request.'))
        res = super(HelpdeskTicket, self).write(vals)
        return res

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """ Overrides mail_thread message_new that is called by the mailgateway
            through message_process.
            This override updates the document according to the email.
        """
        defaults = {
            'email': msg_dict.get('from'),
            'partner_id': msg_dict.get('author_id', False),
            'description': msg_dict.get('body'),
            'name': msg_dict.get('subject') or _("No Subject"),
            'state': 'customer_replied',
            'replied_date': msg_dict.get('date')
        }
        if custom_values is None:
            custom_values = {}
        if custom_values.get('team_id'):
            team_id = self.env['helpdesk.team'].sudo().browse(
                custom_values.get('team_id'))
            if team_id:
                defaults.update({
                    'team_id': team_id.id,
                })
        if 'to' in msg_dict and msg_dict.get('to') != '':
            to = {tools.email_normalize(email): tools.formataddr((name, tools.email_normalize(email)))
                  for (name, email) in tools.email_split_tuples(msg_dict.get('to'))}
            for k, v in to.items():
                user_id = self.env['res.users'].sudo().search(
                    [('partner_id.email', '=', k)], limit=1)
        defaults.update(custom_values)
        return super(HelpdeskTicket, self).message_new(msg_dict, custom_values=defaults)

    def _message_post_after_hook(self, message, msg_vals):
        if self.email and not self.partner_id:
            # we consider that posting a message with a specified recipient (not a follower, a specific one)
            # on a document without customer means that it was created through the chatter using
            # suggested recipients. This heuristic allows to avoid ugly hacks in JS.
            new_partner = message.partner_ids.filtered(
                lambda partner: partner.email == self.email)
            if new_partner:
                self.search([
                    ('partner_id', '=', False),
                    ('email', '=', new_partner.email),
                ]).write({'partner_id': new_partner.id})

        return super(HelpdeskTicket,
                     self)._message_post_after_hook(message, msg_vals)

    @api.returns('self', lambda value: value.id)
    def copy(self, default=None):
        res = super(HelpdeskTicket, self).copy(default=default)
        res.state = 'customer_replied'
        return res

    def _compute_access_url(self):
        super(HelpdeskTicket, self)._compute_access_url()
        for ticket in self:
            ticket.access_url = '/helpdesk/ticket/%s' % (ticket.id)

    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, **kwargs):
        if kwargs.get('subtype') != 'mail.mt_note':
            if self and kwargs and 'author_id' in kwargs and kwargs.get('author_id'):
                author_id = self.env['res.partner'].sudo().search(
                    [('id', '=', kwargs.get('author_id'))], limit=1)
                if author_id:
                    user_id = self.env['res.users'].sudo().search(
                        [('partner_id', '=', author_id.id)], limit=1)
                    if user_id:
                        if 'subtype_id' not in kwargs:
                            if self.team_id:
                                if self.team_id.alias_name and self.team_id.alias_domain:
                                    email = str(self.team_id.alias_name) + \
                                        '@' + str(self.team_id.alias_domain)
                                    mail_server_id = self.env['ir.mail_server'].sudo().search(
                                        [('smtp_user', '=', email)], limit=1)
                                    if mail_server_id:
                                        kwargs.update({
                                            'email_from': email,
                                            'mail_server_id': mail_server_id.id
                                        })
                                    # self.state = 'staff_replied'
                                    self.replied_date = fields.Datetime.now()
                    else:
                        partner_ids = []
                        if 'to' in kwargs:
                            email_to = kwargs.get('to').split(",")
                            if len(email_to) > 1:
                                del email_to[0]
                                for email in email_to:
                                    email_address = email.strip()
                                    partner_id = self.env['res.partner'].search([
                                        ('email', '=', email_address)
                                    ], limit=1)
                                    if partner_id:
                                        partner_ids.append(partner_id.id)
                                    else:
                                        partner_id = self.env['res.partner'].sudo().create({
                                            'name': email_address,
                                            'email': email_address,
                                        })
                                        partner_ids.append(partner_id.id)
                        if partner_ids:
                            self.message_subscribe(partner_ids=partner_ids)
                        self.state = 'customer_replied'
                        if 'date' not in kwargs:
                            self.replied_date = fields.Datetime.now()
                        else:
                            self.replied_date = kwargs.get('date')

                if self.team_id:
                    if self.team_id.alias_name and self.team_id.alias_domain:
                        email = str(self.team_id.alias_name)+'@' + \
                            str(self.team_id.alias_domain)
                        mail_server_id = self.env['ir.mail_server'].sudo().search(
                            [('smtp_user', '=', email)], limit=1)
                        if mail_server_id:
                            kwargs.update({
                                'email_from': email,
                                'mail_server_id': mail_server_id.id
                            })

                        self.replied_date = fields.Datetime.now()
        return super(HelpdeskTicket, self.with_context(mail_post_autofollow=True)).message_post(**kwargs)
    

    def _compute_rating(self):
        if self:
            for rec in self:
                rec.priority_new='none'
                rec.customer_comment=''
                find_rating=self.env['rating.rating'].search([('res_id','=',rec.id),('res_model','=','helpdesk.ticket')],limit=1)
                if find_rating:
                    rec.priority_new=find_rating.rating_text
                    rec.customer_comment=find_rating.feedback