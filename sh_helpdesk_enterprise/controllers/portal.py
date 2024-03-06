# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.


from operator import itemgetter

from markupsafe import Markup

from odoo import http, fields
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request
from odoo.tools.translate import _
from odoo.tools import groupby as groupbyelem
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.osv.expression import OR, AND
from odoo.addons.helpdesk.controllers.portal import CustomerPortal
import json
import base64
import werkzeug
import logging
_logger = logging.getLogger(__name__)


class HelpdeskPoral(CustomerPortal):
    
    @http.route('/portal-user-data', type="http", auth="public", csrf=False)
    def portal_user_data(self, **kw):
        dic = {}
        if kw.get('team_id') and kw.get('team_id') != 'team':
            users_list = []
            team_id = request.env['helpdesk.team'].sudo().search([
                ('id', '=', int(kw.get('team_id')))
            ])
            for member in team_id.team_members:
                user_dic = {
                    'id': member.id,
                    'name': member.name,
                }
                users_list.append(user_dic)
            dic.update({'users': users_list})
        else:
            dic.update({'users': []})
        return json.dumps(dic)
    
    # def _prepare_home_portal_values(self, counters):
    #     values = super()._prepare_home_portal_values(counters)
    #     if request.env.user.sh_portal_user_access:
    #         return values   
    #     else:
    #         del values['ticket_count']
    #         return values
    
    
    @http.route('/portal-subcategory-data', type="http", auth="public", csrf=False)
    def portal_sub_category_data(self, **kw):
        dic = {}
        if kw.get('category_id') and kw.get('category_id') != 'category':
            sub_categ_list = []
            sub_categ_ids = request.env['sh.helpdesk.subcategory'].sudo().search(
                [('parent_category_id', '=', int(kw.get('category_id')))])
            for sub in sub_categ_ids:
                sub_categ_dic = {
                    'id': sub.id,
                    'name': sub.name,
                }
                sub_categ_list.append(sub_categ_dic)
            dic.update({
                'sub_categories': sub_categ_list
            })
        else:
            dic.update({
                'sub_categories': []
            })
        return json.dumps(dic)

    @http.route('/selected-partner-data',
                type="http",
                auth="public",
                csrf=False)
    def selected_partner_data(self, **kw):
        dic = {}
        if kw.get('partner_id') and kw.get('partner_id') != '':
            partner = request.env['res.partner'].sudo().search(
                [('id', '=', int(kw.get('partner_id')))], limit=1)
            if partner:
                dic.update({
                    'name': partner.name,
                    'email': partner.email,
                })
        return json.dumps(dic)


    @http.route('/portal-partner-data', type="http", auth="public", csrf=False)
    def portal_partner_data(self, **kw):
        dic = {}
        partner_list = []
        for partner in request.env['res.partner'].sudo().search([]):
            partner_dic = {
                'id': partner.id,
                'name': partner.name,
            }
            partner_list.append(partner_dic)
        dic.update({'partners': partner_list})
        return json.dumps(dic)

    @http.route('/portal-create-ticket', type='http', auth='public', csrf=False)
    def portal_create_ticket(self, **kw):
        try:
            ticket_dic = {}
            if kw.get('portal_email'):
                partner_id = request.env['res.partner'].sudo().search([('email','=',kw.get('portal_email'))],limit=1)
                if partner_id:
                    ticket_dic.update({
                        'partner_id':partner_id.id,
                    })
                    if kw.get('portal_email_subject'):
                        ticket_dic.update({
                            'name':kw.get('portal_email_subject')
                        })
                    if kw.get('portal_contact_name'):
                        ticket_dic.update({
                            'person_name':kw.get('portal_contact_name'),
                        })
                    if kw.get('portal_type') and kw.get('portal_type')!='type':
                        ticket_dic.update({
                            'ticket_type_id':int(kw.get('portal_type')),
                        })
                    if kw.get('PriorityRadioOptions'):
                        ticket_dic.update({
                            'priority':kw.get('PriorityRadioOptions'),
                        })
                    if kw.get('portal_category') and kw.get('portal_category')!='category':
                        ticket_dic.update({
                            'category_id':int(kw.get('portal_category')),
                        })
                    if kw.get('portal_subcategory') and kw.get('portal_subcategory')!='sub_category':
                        ticket_dic.update({
                            'sub_category_id':int(kw.get('portal_subcategory')),
                        })
                    if kw.get('portal_description'):
                        ticket_dic.update({
                            'description':kw.get('portal_description'),
                        })
                    team_id = request.env['helpdesk.team'].sudo().search([('member_ids', 'in', request.env.uid)], limit=1).id
                    if not team_id:
                        team_id = request.env['helpdesk.team'].sudo().search([], limit=1).id
                    ticket_dic.update({
                        'team_id':team_id,
                        'name':kw.get('portal_email_subject') if kw.get('portal_email_subject') else '',
                    })
                    ticket_id = request.env['helpdesk.ticket'].sudo().create(ticket_dic)
                    if ticket_id:
                        if 'portal_file' in request.params:
                            attached_files = request.httprequest.files.getlist(
                                'portal_file')
                            attachment_ids = []
                            for attachment in attached_files:
                                result = base64.b64encode(attachment.read())
                                attachment_id = request.env['ir.attachment'].sudo().create({
                                    'name': attachment.filename,
                                    'res_model': 'helpdesk.ticket',
                                    'res_id': ticket_id.id,
                                    'display_name': attachment.filename,
                                    'datas': result,
                                })
                                attachment_ids.append(attachment_id.id)
            return werkzeug.utils.redirect("/my/tickets")
        except Exception as e:
            _logger.exception('Something went wrong %s',str(e))
    
    
    @http.route([
        '/my/ticket/close/<int:ticket_id>',
        '/my/ticket/close/<int:ticket_id>/<access_token>',
    ], type='http', auth="public", website=True)
    def ticket_close(self, ticket_id=None, access_token=None, **kw):
        try:
            ticket_sudo = self._document_check_access('helpdesk.ticket', ticket_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if not ticket_sudo.team_id.allow_portal_ticket_closing:
            raise UserError(_("The team does not allow ticket closing through portal"))

        if not ticket_sudo.closed_by_partner:
            closing_stage = ticket_sudo.team_id._get_closing_stage()
            if ticket_sudo.company_id.close_stage_id:
                closing_stage = ticket_sudo.company_id.close_stage_id
            if ticket_sudo.stage_id != closing_stage:
                ticket_sudo.write({'stage_id': closing_stage[0].id, 'closed_by_partner': True,'close_date':fields.Datetime.now(),'close_by':request.env.user.id})
            else:
                ticket_sudo.write({'closed_by_partner': True,'close_date':fields.Datetime.now(),'close_by':request.env.user.id})
            body = _('Ticket closed by the customer')
            ticket_sudo.with_context(mail_create_nosubscribe=True).message_post(body=body, message_type='comment', subtype_xmlid='mail.mt_note')

        return request.redirect('/my/ticket/%s/%s' % (ticket_id, access_token or ''))
