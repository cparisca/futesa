# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
class ValidateInvoice(models.TransientModel):
    _name = 'ati.validate.invoice'
    _description = "Wizard - Validate multiple invoice"

    def validate_invoice(self):
        invoices = self._context.get('active_ids')
        for i in invoices:
            invoice_tmp = self.env['account.move'].browse(i)
            invoice_tmp.action_post()
            invoice_tmp.validate_dian()

class AccountMoveReversal(models.TransientModel):
    _inherit = "account.move.reversal"

    concepto_credit_note = fields.Selection([("1","Devolución parcial de los bienes y/o no aceptación parcial del servicio"),
                                            ("2", "Anulación de factura electrónica"),
                                            ("3", "Rebaja  o descuento parcial o total"),
                                            ("4", "Ajuste de precio"),
                                            ("5", "Otros"),], u"Credito Concepto Corrección",)
    concept_debit_note = fields.Selection(
        [
            ("1", "Intereses"),
            ("2", "Gastos por cobrar"),
            ("3", "Cambio del valor"),
            ("4", "Otros"),
        ],
        u"Debito Concepto Corrección",
    )

