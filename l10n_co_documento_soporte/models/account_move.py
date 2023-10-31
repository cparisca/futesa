import logging
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from pytz import timezone

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    # Campo utilizado para hacer visible campos en lineas de factura dependiendo si es o no Compra con Documento Soporte
    is_ds = fields.Boolean(
        "Factura DS", related="journal_id.sequence_id.use_dian_control", store=True
    )

    nc_discrepancy_response = fields.Selection(
        [('1', 'Devolución parcial de los bienes y/o no aceptación parcial del servicio'),
         ('2', 'nulación del documento soporte en adquisiciones efectuadas a sujetos no obligados a expedir factura deventa o documento equivalente'),
         ('3', 'Rebaja o descuento parcial o total'),
         ('4', 'Ajuste de precio'),
         ('5', 'Otros')], 'Razon de la devolucion (En la pestaña otra informacion)', help = 'Especifique la razon de la devolucion')

    nc_naturaleza_correccion = fields.Text('Naturaleza corrección (En la pestaña otra informacion)', help = 'Naturaleza de la corrección')

    def hook_type_invoice(self, data):
        data = super(AccountMove, self).hook_type_invoice(data)
        data.append("in_invoice")
        return data

    def write(self, vals):
        for invoice in self:
            before_state = invoice.state
            after_state = invoice.state

            if "state" in vals:
                after_state = vals["state"]

            rec_dian_document = self.env["dian.document"].search(
                [("document_id", "=", invoice.id)]
            )
            if not rec_dian_document:
                if (before_state == "draft" and after_state == "posted" and invoice.move_type == "in_invoice"
                    and not invoice.debit_origin_id
                    and invoice.journal_id.sequence_id.use_dian_control
                ):
                    (
                        invoice.env["dian.document"]
                        .sudo()
                        .create({"document_id": invoice.id, "document_type": "f"})
                    )

                if (
                    before_state == "draft"
                    and after_state == "posted"
                    and invoice.move_type == "in_refund"
                ):
                    (
                        invoice.env["dian.document"]
                        .sudo()
                        .create({"document_id": invoice.id, "document_type": "c"})
                    )
                if (
                    before_state == "draft"
                    and after_state == "posted"
                    and invoice.move_type == "in_refund"
                    and invoice.debit_origin_id
                ):
                    (
                        invoice.env["dian.document"]
                        .sudo()
                        .create({"document_id": invoice.id, "document_type": "d"})
                    )
        return super(AccountMove, self).write(vals)

    def _get_datetime_bogota(self):
        fmt = "%Y-%m-%dT%H:%M:%S"
        now_utc = datetime.now(timezone("UTC")) - timedelta(hours=5)
        now_bogota = now_utc
        return now_bogota.strftime(fmt)

    def validate_dian(self):
        if self.move_type in ["out_invoice", "out_refund"]:
            return super(AccountMove, self).validate_dian()

        elif self.move_type in ["in_invoice", "in_refund"]:
            # Validamos que el partner tenga DV
            if self.partner_id.dv not in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]:
                raise UserError(_("El contacto a facturar no tiene Digito Verificador"))
            # Validamos que el partner tenga ZIP
            if not self.partner_id.zip:
                raise UserError(
                    _("Debe ingresar el zip code o codigo postal del cliente")
                )

            # Validamos si la fecha corresponde para validar como reporte semanal si asi corresponde

            document_dian = self.env["dian.document"].search(
                [("document_id", "=", self.id)]
            )
            if not document_dian:
                if (self.state == "posted"  and self.move_type == "in_invoice" and not self.is_debit_note):

                    document_dian = (
                        self.env["dian.document"]
                        .sudo()
                        .create({"document_id": self.id, "document_type": "f"})
                    )

            if self.in_contingency_4:
                # Documento de ND
                if self.move_type == "in_invoice" and self.debit_origin_id:
                    raise ValidationError(
                        _(
                            "No puede validar notas de débito mientras se encuentra en estado de contingencia tipo 4"
                        )
                    )
                # Documento de NC
                elif self.move_type == "in_refund":
                    raise ValidationError(
                        _(
                            "No puede validar notas de crédito mientras se encuentra en estado de contingencia tipo 4"
                        )
                    )
                if self.state_contingency == "exitosa":
                    raise ValidationError(
                        _(
                            "Factura de contingencia tipo 4 ya fue enviada al cliente. Una vez se restablezca el servicio, debe pulsar este bóton para enviar la contingencia tipo 4 bota la DIAN"
                        )
                    )

            if document_dian.state == "rechazado":
                document_dian.response_message_dian = " "
                document_dian.xml_response_dian = " "
                document_dian.xml_send_query_dian = " "
                document_dian.response_message_dian = " "
                document_dian.xml_document = " "
                document_dian.xml_file_name = " "
                document_dian.zip_file_name = " "
                document_dian.cufe = " "
                document_dian.date_document_dian = " "
                document_dian.write({"state": "por_notificar", "resend": False})
                if self.in_contingency_4 and not self.contingency_3:
                    document_type = document_dian.document_type
                else:
                    document_type = (
                        document_dian.document_type
                        if not self.contingency_3
                        else "contingency"
                    )
                document_dian.send_pending_dian(document_dian.id, document_type)

            if document_dian.state == ("por_notificar"):
                if self.in_contingency_4 and not self.contingency_3:
                    document_type = document_dian.document_type
                else:
                    document_type = (
                        document_dian.document_type
                        if not self.contingency_3
                        else "contingency"
                    )
                document_dian.send_pending_dian(document_dian.id, document_type)

            company = (
                self.env["res.company"].sudo().search([("id", "=", self.company_id.id)])
            )
            # Ambiente pruebas
            if not company.production and not self.in_contingency_4:
                if document_dian.state == "por_validar":
                    document_dian.request_validating_dian(document_dian.id)
            # Determina si existen facturas con contingencias tipo 4 que no han sidoenviadas a la DIAN
            # company.exists_invoice_contingency_4 = False
            documents_dian_contingency = self.env["dian.document"].search(
                [
                    ("state", "=", "por_notificar"),
                    ("contingency_4", "=", True),
                    ("document_type", "=", "f"),
                ]
            )
            company.exists_invoice_contingency_4 = bool(documents_dian_contingency)
            return False
