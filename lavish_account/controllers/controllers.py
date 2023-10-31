# -*- coding: utf-8 -*-
# from odoo import http


# class lavishAccount(http.Controller):
#     @http.route('/lavish_account/lavish_account/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/lavish_account/lavish_account/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('lavish_account.listing', {
#             'root': '/lavish_account/lavish_account',
#             'objects': http.request.env['lavish_account.lavish_account'].search([]),
#         })

#     @http.route('/lavish_account/lavish_account/objects/<model("lavish_account.lavish_account"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('lavish_account.object', {
#             'object': obj
#         })
