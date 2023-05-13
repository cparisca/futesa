# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta


class TicketAlarm(models.Model):
    _name = "sh.ticket.alarm"
    _description = "Ticket Reminder"

    name = fields.Char(string="Name", readonly=True)
    type = fields.Selection([('email', 'Email'), (
        'popup', 'Popup')], string="Type", required=True, default='email')
    sh_remind_before = fields.Integer(
        string="Reminder Before")
    sh_reminder_unit = fields.Selection([('Hour(s)', 'Hour(s)'), (
        'Minute(s)', 'Minute(s)'), ('Second(s)', 'Second(s)')], string="Reminder Unit", default='Hour(s)', required=True)
    company_id = fields.Many2one(
        'res.company', 'Company', default=lambda self: self.env.company)

    @api.constrains('sh_remind_before','sh_reminder_unit')
    def _check_sh_reminder_unit(self):
        if self.filtered(lambda c: c.sh_reminder_unit == 'Minute(s)' and c.sh_remind_before < 5):
            raise ValidationError(
                _("Reminder Before can't set less than 5 Minutes."))
        elif self.filtered(lambda c: c.sh_reminder_unit == 'Second(s)' and c.sh_remind_before < 300):
            raise ValidationError(
                _("Reminder Before can't set less than 300 Seconds."))
        elif self.filtered(lambda c: c.sh_reminder_unit == 'Hour(s)' and c.sh_remind_before < 1):
            raise ValidationError(
                _("Reminder Before can't set less than 1 Hour."))

    def name_get(self):
        # Prefetch the fields used by the `name_get`, so `browse` doesn't fetch other fields
        self.browse(self.ids).read(
            ['sh_remind_before', 'sh_reminder_unit', 'type'])
        return [(alarm.id, '%s%s%s' % (str(alarm.sh_remind_before)+' ', str(alarm.sh_reminder_unit)+' ', '['+str(alarm.type)+']'))
                for alarm in self]

    @api.onchange('sh_remind_before', 'type', 'sh_reminder_unit')
    def _onchange_name(self):
        for rec in self:
            rec.name = rec.name_get()[0][1]

    @api.model
    def _run_ticket_reminder(self):
        if self.env.company.sh_display_ticket_reminder:
            alarm_ids = self.env['sh.ticket.alarm'].sudo().search([])
            if alarm_ids:
                for alarm in alarm_ids:
                    ticket_ids = self.env['helpdesk.ticket'].sudo().search(
                        [('sh_ticket_alarm_ids', 'in', [alarm.id])])
                    if ticket_ids:
                        for ticket in ticket_ids:
                            deadline_date = False
                            if alarm.sh_reminder_unit == 'Hour(s)' and ticket.sh_due_date:
                                deadline_date_hours_added = ticket.sh_due_date + \
                                    timedelta(hours=5, minutes=30, seconds=0)
                                deadline_date = deadline_date_hours_added - \
                                    timedelta(hours=alarm.sh_remind_before)
                            elif alarm.sh_reminder_unit == 'Minute(s)' and ticket.sh_due_date:
                                deadline_date_minutes_added = ticket.sh_due_date + \
                                    timedelta(hours=5, minutes=30, seconds=0)
                                deadline_date = deadline_date_minutes_added - \
                                    timedelta(minutes=alarm.sh_remind_before)
                            elif alarm.sh_reminder_unit == 'Second(s)' and ticket.sh_due_date:
                                deadline_date_seconds_added = ticket.sh_due_date + \
                                    timedelta(hours=5, minutes=30, seconds=0)
                                deadline_date = deadline_date_seconds_added - \
                                    timedelta(seconds=alarm.sh_remind_before)
                            if deadline_date and deadline_date != False:
                                if alarm.type == 'popup':
                                    now = fields.Datetime.now() + timedelta(hours=5, minutes=30, seconds=0)
                                    if fields.Date.today() == deadline_date.date() and deadline_date.hour == now.hour and deadline_date.minute == now.minute:
                                        notifications = []
                                        message = "<h2><u>Ticket Information</u></h2></br>"
                                        if ticket.create_date:
                                            message += "<strong>Create Date :</strong>" + \
                                                str(ticket.create_date) + \
                                                "</br>"
                                        if ticket.sh_due_date:
                                            message += "<strong>Due Date :</strong>" + \
                                                str(ticket.sh_due_date) + \
                                                "</br>"
                                        if ticket.ticket_type_id:
                                            message += "<strong>Type :</strong>" + \
                                                str(ticket.ticket_type_id.name) + \
                                                "</br>"
                                        if ticket.category_id:
                                            message += "<strong>Category :</strong>" + \
                                                str(ticket.category_id.name) + \
                                                "</br>"
                                        if ticket.sub_category_id:
                                            message += "<strong>Sub Category :</strong>" + \
                                                str(ticket.sub_category_id.name) + "</br>"
                                        if ticket.priority:
                                            message += "<strong>Priority :</strong>" + \
                                                str(ticket.priority) + \
                                                "</br>"
                                        if ticket.team_id:
                                            message += "<strong>Team :</strong>" + \
                                                str(ticket.team_id.name) + \
                                                "</br>"
                                        if ticket.user_id:
                                            message += "<strong>Assigned To :</strong>" + \
                                                str(ticket.user_id.name) + \
                                                "</br>"
                                        multi_users = []
                                        if ticket.sh_user_ids:
                                            for user in ticket.sh_user_ids:
                                                if user.name not in multi_users:
                                                    multi_users.append(
                                                        user.name)
                                        if len(multi_users) > 0:
                                            message += '<strong>Assigned Users : </strong>'
                                            for user_name in multi_users:
                                                message += '<span class="badge badge-info" style="padding-right:5px">' + \
                                                    str(user_name) + '</span>'
                                            message += '</br>'
                                        tags = []
                                        if ticket.tag_ids:
                                            for tag in ticket.tag_ids:
                                                if tag.name not in tags:
                                                    tags.append(tag.name)
                                        if len(tags) > 0:
                                            message += '<strong>Tags : </strong>'
                                            for tag_name in tags:
                                                message += '<span class="badge badge-info" style="padding-right:5px">' + \
                                                    str(tag_name) + '</span>'
                                            message += '</br>'
                                        products = []
                                        if ticket.product_ids:
                                            for product in ticket.product_ids:
                                                if product.name_get()[0][1] not in products:
                                                    products.append(
                                                        product.name_get()[0][1])
                                        if len(products) > 0:
                                            message += '<strong>Products : </strong>'
                                            for product_name in products:
                                                message += '<span class="badge badge-info" style="padding-right:5px">' + \
                                                    str(product_name) + \
                                                    '</span>'
                                            message += '</br>'
                                        if ticket.partner_id:
                                            message += "<strong>Partner :</strong>" + \
                                                str(ticket.partner_id.name) + \
                                                "</br>"
                                        if ticket.person_name:
                                            message += "<strong>Person Name :</strong>" + \
                                                str(ticket.person_name) + \
                                                "</br>"
                                        if ticket.email:
                                            message += "<strong>Email :</strong>" + \
                                                str(ticket.email) + "</br>"
                                        model_href = str(self.env['ir.config_parameter'].sudo().get_param(
                                            'web.base.url')) + '/web#id='+str(ticket.id)+'&model=helpdesk.ticket&view_type=form'
                                        message += "<a style = 'color:#7C7BAD;padding-right:10px' class = 'btn btn-link' data-dismiss = 'toast' > Close "
                                        message += "<a href=" + \
                                            str(
                                                model_href)+" target='_blank' class='btn btn-link' style='padding-right:10px;'>Ticket</a>"
                                        partners = []
                                        if ticket.user_id:
                                            if ticket.user_id.partner_id not in partners:
                                                partners.append(
                                                    ticket.user_id.partner_id)
                                        if ticket.sh_user_ids:
                                            for user_id in ticket.sh_user_ids:
                                                if user_id.partner_id not in partners:
                                                    partners.append(
                                                        user_id.partner_id)
                                        if len(partners) > 0:
                                            for partner_id in partners:
                                                self.env['bus.bus']._sendone(partner_id, 'sh_helpdesk_enterprise_notification_info', {
                                                    'title': _('Ticket Reminder '+'('+str(ticket.name)+')'),
                                                    'message': _(message),
                                                    'sticky': True,
                                                    'warning': True,
                                                })

                                elif alarm.type == 'email':
                                    now = fields.Datetime.now() + timedelta(hours=5, minutes=30, seconds=0)
                                    email_formatted = []
                                    if ticket.user_id:
                                        if str(ticket.user_id.partner_id.email_formatted) not in email_formatted:
                                            email_formatted.append(
                                                str(ticket.user_id.email_formatted))
                                    if ticket.sh_user_ids:
                                        for user_id in ticket.sh_user_ids:
                                            if str(user_id.partner_id.email_formatted) not in email_formatted:
                                                email_formatted.append(
                                                    str(user_id.partner_id.email_formatted))
                                    if fields.Date.today() == deadline_date.date() and deadline_date.hour == now.hour and deadline_date.minute == now.minute:
                                        reminder_template = self.env.ref(
                                            'sh_helpdesk_enterprise.sh_ticket_reminder_mail_template_enterprise')
                                        if reminder_template and len(email_formatted) > 0:
                                            emails = ','.join(email_formatted)
                                            email_values = {'email_to': emails}
                                            reminder_template.sudo().send_mail(
                                                ticket.id, force_send=True, email_values=email_values)
