import base64
import logging
import tempfile
import xmltodict
import xml.etree.ElementTree as ET
from datetime import datetime
from odoo import  _, api, fields, models, tools
from odoo.exceptions import ValidationError
from zipfile import ZipFile
_logger = logging.getLogger(__name__)


class RecepcionFacturaDian(models.Model):
    _name = 'recepcion.factura.dian'
    _description = 'Recepcion Factura Dian'
    _inherit = ['mail.thread']

    name = fields.Char('Nombre')
    cufe = fields.Char('Cufe')
    company_id = fields.Many2one('res.company', string='Compañia',  default=lambda self: self.env.company)
    supplier_id = fields.Many2one('res.partner','Proveedor')
    state = fields.Selection([('draft', 'Borrador'), ('read', 'Leido'), ('procces', 'Procesado'), ('send', 'Enviado')],'State',default='draft')
    zip_file = fields.Binary('Archivo Zip')
    pdf_file = fields.Binary('Factura')
    xml_text = fields.Text('Contenido XML')
    invoice_xml = fields.Text('Factura XML')
    file_name = fields.Char('File name')
    date_invoice = fields.Date('Fecha de factura')
    order_line_ids = fields.One2many('recepcion.factura.dian.line','recepcion_id','Lineas de factura')
    n_invoice = fields.Char('Nº Factura')
    total_untax = fields.Float('Total sin impuestos')
    total_tax = fields.Float('Total impuestos')
    total = fields.Float('Total')
    application_response_ids = fields.Many2many('dian.application.response')
    tiene_eventos = fields.Boolean(compute='_compute_tiene_eventos', store=True)

    @api.depends('application_response_ids')
    def _compute_tiene_eventos(self):
        for rec in self:
            rec.tiene_eventos = bool(rec.application_response_ids)

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        if custom_values is None:
            for attachement_id in msg_dict.get('attachments'):
                if attachement_id.fname[-3:].lower() == 'zip':
                    custom_values = {
                        'zip_file': base64.b64encode(attachement_id.content)
                    }
            if 'zip_file' in custom_values:
                recepcion_id = super(RecepcionFacturaDian, self).message_new(msg_dict, custom_values)
                recepcion_id.read_zip()
                recepcion_id.process_xml()
            return False
        else:
            return False

    def return_inverse_number_document_type(self, document_type):
        documento = 'no_identification'
        if document_type:
            document_type = int(document_type)
            document_types = {
                31: 'rut',
                13: 'national_citizen_id',
                11: 'civil_registration',
                12: 'id_card',
                22: 'foreign_id_card',
                41: 'passport',
            }
            documento = document_types.get(document_type)
        return documento




    def process_xml(self):
        dict_data_xml = xmltodict.parse(self.xml_text)
        dict_xml_invoice = xmltodict.parse(self.invoice_xml)
        supplier = self.env['res.partner'].search([('vat_co','=',dict_data_xml['AttachedDocument']['cac:SenderParty']['cac:PartyTaxScheme']['cbc:CompanyID']['#text'])],limit=1)
        if 'Invoice' not in dict_xml_invoice:
            return False
        if len(supplier) < 1:
            respon_fiscal = []
            for f in dict_data_xml['AttachedDocument']['cac:SenderParty']['cac:PartyTaxScheme']['cbc:TaxLevelCode']["#text"].split(';'):
                respon_fiscal.append((4, self.env['dian.fiscal.responsability'].search([('code','=',f)]).id ))
            documento = self.return_inverse_number_document_type(dict_data_xml['AttachedDocument']['cac:SenderParty']['cac:PartyTaxScheme']['cbc:CompanyID']['@schemeName'])
            supplier = self.env['res.partner'].create({
                'name' : dict_data_xml['AttachedDocument']['cac:SenderParty']['cac:PartyTaxScheme']['cbc:RegistrationName'],
                'is_company' : True,
                'vat_co' : dict_data_xml['AttachedDocument']['cac:SenderParty']['cac:PartyTaxScheme']['cbc:CompanyID']['#text'],
                'personType' : '2',
                'l10n_latam_identification_type_id' : self.env['l10n_latam.identification.type'].search([
                    ('l10n_co_document_code','=', documento )
                ]).id,
                #'type_residence' : 'si',
                'companyName' : dict_data_xml['AttachedDocument']['cac:SenderParty']['cac:PartyTaxScheme']['cbc:RegistrationName'],
                'fiscal_responsability_ids' : respon_fiscal,
                'tribute_id' : self.env['dian.tributes'].search([('code','=', dict_data_xml['AttachedDocument']['cac:SenderParty']['cac:PartyTaxScheme']['cac:TaxScheme']['cbc:ID'])]).id,
            })
        self.supplier_id = supplier
        self.date_invoice = datetime.strptime(dict_xml_invoice['Invoice']['cbc:IssueDate'], '%Y-%m-%d')

        #Cargamos y calculamos lineas de facturas
        _productos = []
        cac_invoice_line = dict_xml_invoice['Invoice']['cac:InvoiceLine'] if isinstance(dict_xml_invoice['Invoice']['cac:InvoiceLine'], list) \
            else [dict_xml_invoice['Invoice']['cac:InvoiceLine']]
        for line in cac_invoice_line:
            _productos.append((0,0,{
                'name' : line['cac:Item']['cbc:Description'],
                'qty' : line['cbc:InvoicedQuantity']['#text'],
                'uom' : line['cbc:InvoicedQuantity']['@unitCode'],
                'price' : line['cbc:LineExtensionAmount']['#text'],
                'total' : float(line['cbc:LineExtensionAmount']['#text']) * float(line['cbc:InvoicedQuantity']['#text']),
            }))
        self.order_line_ids = False
        self.order_line_ids = _productos

        #Numero de Factura
        self.n_invoice = dict_xml_invoice['Invoice']['cbc:ID']

        #Cargamos totales
        self.total_tax = dict_xml_invoice['Invoice']['cac:TaxTotal']['cbc:TaxAmount']['#text'] \
            if 'cac:TaxTotal' in dict_xml_invoice['Invoice'] else 0
        self.total_untax = dict_xml_invoice['Invoice']['cac:LegalMonetaryTotal']['cbc:LineExtensionAmount']['#text']
        self.total = dict_xml_invoice['Invoice']['cac:LegalMonetaryTotal']['cbc:PayableAmount']['#text']

        #Cambiamos nombre y estado
        self.name = supplier.name + ' - ' +self.n_invoice
        self.state = 'procces'

    def add_application_response(self):
        response_code = self._context.get('response_code')
        ar = self.env['dian.application.response'].generate_from_attached_document(self.xml_text, response_code)
        self.application_response_ids = [(4,ar.id)]

    def action_register_event(self):
        action = self.env.ref('l10n_co_e-invoice.action_register_event_dian').sudo().read()[0]
        return action

    def read_zip(self):
        file = base64.decodestring(self.zip_file)
        fobj = tempfile.NamedTemporaryFile(delete=False)
        fname = fobj.name
        fobj.write(file)
        fobj.close()
        f = open(fname, 'r+b')

        with ZipFile(f, 'r') as zip_file:
            for nombre in zip_file.namelist() :
                if nombre[-4:] == '.xml':
                    self.name = nombre[:-4]
                    _contenido = zip_file.open(nombre)
                    self.xml_text = _contenido.read()
                if nombre[-4:] == '.pdf':
                    self.pdf_file = base64.b64encode(zip_file.open(nombre).read())
            f.close()

        self.invoice_xml = xmltodict.parse(self.xml_text)['AttachedDocument']['cac:Attachment']['cac:ExternalReference']['cbc:Description']

        #Cambiamos estado
        self.state = 'read'
        return


class RecepcionFacturaDianLine(models.Model):
    _name = 'recepcion.factura.dian.line'

    name = fields.Char('Producto')
    recepcion_id = fields.Many2one('recepcion.factura.dian','Recepcion de factura DIAN')
    uom = fields.Char('Unidad de Medida')
    qty = fields.Float('Cantidad')
    price = fields.Float('Precio')
    total = fields.Float('Total')
