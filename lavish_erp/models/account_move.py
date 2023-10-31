from email.policy import default
from odoo import models, fields,api , _
import json
import logging
from collections import defaultdict
from datetime import datetime

from odoo.exceptions import ValidationError
from odoo.tools import formatLang

class AccountMove(models.Model):
    _inherit = "account.move"
    
    resolution_number = fields.Char("Resolution number in invoice")
    resolution_date = fields.Date(string="Resolution Date")
    resolution_date_to = fields.Date(string="Resolution Date To")
    resolution_number_from = fields.Integer(string="Resolution  Number From")
    resolution_number_to = fields.Integer(string="Resolution Number To")

    def validate_number_phone(self, data):
        """
            Funcion que es utilizada en el reporte de factura para retornar la información de:
                ->	Telefono
                ->	Celular
        """
        if data.phone and data.mobile:
            return data.phone + " - " + data.mobile
        if data.phone and not data.mobile:
            return data.phone
        if data.mobile and not data.phone:
            return data.mobile

    def validate_state_city(self, data):
        """
            Funcion que es utilizada en el reporte de factura para retornar la información de:
                ->	Pais
                ->	Departamento
                ->	Ciudad
        """
        return (
            ((data.country_id.name + " ") if data.country_id.name else " ")
            + (" " + (data.state_id.name + " ") if data.state_id.name else " ")
            + (" " + data.city_id.name if data.city_id.name else "")
        )


    @api.model
    def create(self, vals):
        if not ("invoice_date" in vals) or not vals["invoice_date"]:
            vals["invoice_date"] = fields.Date.context_today(self)
        res = super(AccountMove, self).create(vals)
        return res

    def action_post(self):
        """
            Funcion que permite guardar los datos de la resolucion de la factura cuando esta es confirmada
        """
        result = super(AccountMove, self).action_post()
        for inv in self:
            sequence = self.env["ir.sequence.dian_resolution"].search(
                [
                    ("sequence_id", "=", self.journal_id.sequence_id.id),
                    ("active_resolution", "=", True),
                ],
                limit=1,
            )
            inv.resolution_number = sequence["resolution_number"]
            inv.resolution_date = sequence["date_from"]
            inv.resolution_date_to = sequence["date_to"]
            inv.resolution_number_from = sequence["number_from"]
            inv.resolution_number_to = sequence["number_to"]
        return result
class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

