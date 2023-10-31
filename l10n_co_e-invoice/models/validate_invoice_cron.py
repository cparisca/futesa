import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ValidateInvoiceCron(models.TransientModel):
    _name = "validate.invoice.cron"
    _description = "Validator Invoice Cron"

    def validate_invoice(self):
        inv_to_validate = self.env["account.move"].search(
            [("validate_cron", "=", True), ("state", "=", "draft")]
        )
        for i in inv_to_validate:
            i.action_post()
            i.validate_dian()

        sql = "select am.id from account_move am, dian_document dd where am.validate_cron is true and am.state = 'posted' and dd.document_id = am.id and dd.state != 'exitoso';"
        self.env.cr.execute(sql)
        sql_result = self.env.cr.dictfetchall()

        inv_to_validate_dian = (
            self.env["account.move"].sudo().browse([n.get("id") for n in sql_result])
        )
        for idian in inv_to_validate_dian:
            idian.validate_dian()

        _logger.warning(
            "inv_to_validate: {}, inv_to_validate_dian: {}".format(
                inv_to_validate, inv_to_validate_dian
            )
        )
