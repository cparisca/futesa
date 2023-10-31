import logging

_logger = logging.getLogger(__name__)

from odoo import models, api, _, fields
from odoo.exceptions import UserError, ValidationError
import pytz

try:
    from lxml import etree
except ImportError:
    _logger.warning("Cannot import  etree *************************************")


try:
    import pyqrcode
except ImportError:
    _logger.warning("Cannot import pyqrcode library ***************************")


try:
    import re
except ImportError:
    _logger.warning("Cannot import re library")

try:
    import uuid
except ImportError:
    _logger.warning("Cannot import uuid library")

try:
    import requests
except ImportError:
    _logger.warning("no se ha cargado requests")

try:
    import xmltodict
except ImportError:
    _logger.warning("Cannot import xmltodict library")

try:
    import hashlib
except ImportError:
    _logger.warning("Cannot import hashlib library ****************************")

import re


NC_RAZONES = {
    '1' :  'Devolución parcial de los bienes y/o no aceptación parcial del servicio',
    '2' :  'Anulación del documento soporte en adquisiciones efectuadas a sujetos no obligados a expedir factura deventa o documento equivalente',
    '3' :  'Rebaja o descuento parcial o total',
    '4' :  'Ajuste de precio',
    '5' :  'Otros'
}
class DianDocument(models.Model):
    _inherit = 'dian.document'

    @api.model
    def _generate_xml_filename(self, data_resolution, NitSinDV, doctype, is_debit_note):
        if doctype == 'in_invoice' or doctype == 'in_refund':
            docdian = 'ds' if doctype == 'in_invoice' else 'nas'

            len_prefix = len(data_resolution["Prefix"])
            len_invoice = len(data_resolution["InvoiceID"])
            dian_code_int = int(data_resolution["InvoiceID"][len_prefix:len_invoice])
            dian_code_hex = self.IntToHex(dian_code_int)
            dian_code_hex.zfill(10)
            file_name_xml = docdian + NitSinDV.zfill(10) + dian_code_hex.zfill(10) + ".xml"
            return file_name_xml
        else:
            return super(DianDocument, self)._generate_xml_filename(data_resolution, NitSinDV, doctype, is_debit_note)

    def _generate_zip_filename(self, data_resolution, NitSinDV, doctype, is_debit_note):
        if doctype == 'in_invoice' or doctype == 'in_refund':
            docdian = 'ds' if doctype == 'in_invoice' else 'nas'
            secuenciador = data_resolution["InvoiceID"]
            dian_code_int = int(re.sub(r"\D", "", secuenciador))
            # dian_code_int = int(data_resolution['InvoiceID'][len_prefix:len_invoice])
            dian_code_hex = self.IntToHex(dian_code_int)
            dian_code_hex.zfill(10)
            file_name_zip = docdian + NitSinDV.zfill(10) + dian_code_hex.zfill(10) + ".zip"
            return file_name_zip
        else:
            return super(DianDocument, self)._generate_zip_filename(data_resolution, NitSinDV, doctype, is_debit_note)

    @api.model
    def _get_doctype(self, doctype, is_debit_note, in_contingency_4):
        docdian = False
        if self.document_id.move_type in ['in_invoice','in_refund']:
            if doctype == 'in_invoice' and not is_debit_note:
                docdian = "05"
            elif doctype == "in_refund":
                docdian = "95"
            elif doctype == "in_invoice" and is_debit_note or self.document_id.debit_origin_id or self.document_id.is_debit_note:
                docdian = "92"
            return docdian
        else:
            return super(DianDocument, self)._get_doctype(doctype, is_debit_note, in_contingency_4)

    @api.model
    def _get_dian_constants(self, data_header_doc):
        dian_constants = super(DianDocument, self)._get_dian_constants(data_header_doc)
        if self.document_id.move_type == 'in_invoice' or self.document_id.move_type == 'in_refund':
            #Consultamos si el roveedor es residente o no para el valor de CustomizationID
            if self.document_id.partner_id.type_residence == "si":
                dian_constants["CustomizationID"] = 10
            elif self.document_id.partner_id.type_residence == "no":
                dian_constants["CustomizationID"] = 11
            else:
                raise ValidationError('El proveedor {0} no tiene la informacion de residencia en su formulario'.format(self.document_id.partner_id.name))

            if self.document_id.move_type == 'in_invoice' and self.document_id.is_debit_note == False:
                dian_constants["ProfileID"] = "DIAN 2.1: documento soporte en adquisiciones efectuadas a no obligados a facturar."
           
            if self.document_id.move_type == 'in_invoice' and self.document_id.is_debit_note or self.document_id.debit_origin_id:
                dian_constants["ProfileID"] = "DIAN 2.1: Nota Débito de Factura Electrónica de Venta"
            if self.document_id.move_type == 'in_refund':
                dian_constants["ProfileID"] = "DIAN 2.1: Nota de ajuste al documento soporte en adquisiciones efectuadas a sujetos no obligados a expedir factura o documento equivalente"

            dian_constants['DiscrepancyResponseID'] = ''
            dian_constants['DiscrepancyResponseCode'] = ''
            if self.document_id.move_type == 'in_refund':
                dian_constants['DiscrepancyResponseID'] = data_header_doc.invoice_origin
                dian_constants['DiscrepancyResponseCode'] = self.document_id.nc_discrepancy_response
                dian_constants['DiscrepancyResponseDescription'] = self.document_id.nc_naturaleza_correccion



            dian_constants['URLQRCode'] = 'https://catalogo-vpfe-hab.dian.gov.co/document/searchqr?documentkey'
            if data_header_doc.company_id.production:
                dian_constants['URLQRCode'] = 'https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey'

        return dian_constants

    @api.model
    def _generate_cufe(
        self,
        invoice_id,
        NumFac,
        FecFac,
        HoraFac,
        ValFac,
        NitOFE,
        TipAdq,
        NumAdq,
        ClTec,
        ValPag,
        data_taxs,
        TipoAmbiente,
    ):
        if self.document_id.move_type == 'in_invoice':
            ValFac = str(ValFac)
            CodImp1 = "01"
            ValImp1 = 0
            _logger.warning('***** data_tex {0}'.format(data_taxs))
            if data_taxs.get("iva_lines"):
                for iva_line in range(data_taxs.get("iva_lines")):
                    iva_line_str = str(iva_line + 1)
                    ValImp1 += float(data_taxs["iva_" + iva_line_str])

            ValImp1 = str("{:.2f}".format(ValImp1))
            ValPag = str(ValPag)
            CUFE = (
                NumFac
                + FecFac
                + HoraFac
                + ValFac
                + CodImp1
                + ValImp1
                + ValPag
                + NitOFE
                + NumAdq
                + self.env.company.software_pin
                + TipoAmbiente
            )
            CUFE = hashlib.sha384(CUFE.encode())
            CUFE = CUFE.hexdigest()
            return CUFE
        else:
            return super(DianDocument, self)._generate_cufe(invoice_id, NumFac, FecFac, HoraFac, ValFac, NitOFE, TipAdq, NumAdq, ClTec, ValPag, data_taxs, TipoAmbiente)

    @api.model
    def _generate_cude(
        self,
        invoice_id,
        NumFac,
        FecFac,
        HoraFac,
        ValFac,
        NitOFE,
        TipAdq,
        NumAdq,
        PINSoftware,
        ValPag,
        data_taxs,
        TipoAmbiente,
    ):
        if self.document_id.move_type == 'in_refund':
            CodImp1 = "01"
            ValImp1 = 0

            if data_taxs.get("iva_lines"):
                for iva_line in range(data_taxs.get("iva_lines")):
                    iva_line_str = str(iva_line + 1)
                    ValImp1 += float(data_taxs["iva_" + iva_line_str])

            ValImp1 = str(self._complements_second_decimal_total(ValImp1))
            ValPag = str(ValPag)
            TipAdq = str(TipAdq)
            CUDE = (
                NumFac
                + FecFac
                + HoraFac
                + ValFac
                + CodImp1
                + ValImp1
                + ValPag
                + NitOFE
                + NumAdq
                + self.env.company.software_pin
                + TipoAmbiente
            )
            CUDE = hashlib.sha384(CUDE.encode())
            CUDE = CUDE.hexdigest()
            return CUDE
        else:

            return super(DianDocument, self)._generate_cude(invoice_id,NumFac,FecFac,HoraFac,ValFac,NitOFE,TipAdq,NumAdq,PINSoftware,ValPag,data_taxs,TipoAmbiente)

    @api.model
    def _generate_barcode(
        self, dian_constants, data_constants_document, CUFE, data_taxs
    ):
        if self.document_id.move_type in ['in_invoice','in_refund']:
            NumFac = data_constants_document["InvoiceID"]
            FecFac = data_constants_document["IssueDateCufe"]
            Time = data_constants_document["IssueTime"]
            ValFac = data_constants_document["LineExtensionAmount"]
            NitOFE = dian_constants["SupplierID"]
            DocAdq = data_constants_document["CustomerID"]
            # ValFacIm = data_constants_document["PayableAmount"]
            ValIva = data_taxs["iva_1"] if "iva_1" in data_taxs else "0"
            ValOtroIm = str(data_taxs.get("inc_04", 0) + data_taxs.get("ica_03", 0))
            ValTotFac = data_constants_document["TotalTaxInclusiveAmount"]
            datos_qr = (
                " NumFac: "
                + NumFac
                + " FecFac: "
                + FecFac
                + " HorFac: "
                + Time
                + " DocAdq: "
                + DocAdq
                + " NitFac: "
                + NitOFE
                + " ValFac: "
                + str(ValFac)
                + " ValIva: "
                + str(ValIva)
                + " ValTotFac: "
                + str(ValTotFac)
                + " CUFE: "
                + CUFE
            )
            # Genera código QR
            qr_code = pyqrcode.create(datos_qr)
            qr_code = qr_code.png_as_base64_str(scale=2)
            return qr_code
        else:
            return super(DianDocument, self)._generate_barcode(dian_constants, data_constants_document, CUFE, data_taxs)

    def _template_basic_data_fe_xml(self):
        xml = super(DianDocument, self)._template_basic_data_fe_xml()
        if self.document_id.move_type == 'in_invoice':
            xml = """<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"  xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" xmlns:sts="dian:gov:co:facturaelectronica:Structures-2-1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2 http://docs.oasis-open.org/ubl/os-UBL-2.1/xsd/maindoc/UBL-Invoice-2.1.xsd" xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#">
        <ext:UBLExtensions>
            <ext:UBLExtension>
                <ext:ExtensionContent>
                    <sts:DianExtensions>
                        <sts:InvoiceControl>
                            <sts:InvoiceAuthorization>%(InvoiceAuthorization)s</sts:InvoiceAuthorization>
                            <sts:AuthorizationPeriod>
                                <cbc:StartDate>%(StartDate)s</cbc:StartDate>
                                <cbc:EndDate>%(EndDate)s</cbc:EndDate>
                            </sts:AuthorizationPeriod>
                            <sts:AuthorizedInvoices>
                                <sts:Prefix>%(Prefix)s</sts:Prefix>
                                <sts:From>%(From)s</sts:From>
                                <sts:To>%(To)s</sts:To>
                            </sts:AuthorizedInvoices>
                        </sts:InvoiceControl>
                        <sts:InvoiceSource>
                            <cbc:IdentificationCode listAgencyID="6" listAgencyName="United Nations Economic Commission for Europe" listSchemeURI="urn:oasis:names:specification:ubl:codelist:gc:CountryIdentificationCode-2.1">%(IdentificationCode)s</cbc:IdentificationCode>
                        </sts:InvoiceSource>
                        <sts:SoftwareProvider>
                            <sts:ProviderID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="%(SoftwareProviderSchemeID)s" schemeName="31">%(SoftwareProviderID)s</sts:ProviderID>
                            <sts:SoftwareID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)">%(SoftwareID)s</sts:SoftwareID>
                        </sts:SoftwareProvider>
                        <sts:SoftwareSecurityCode schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)">%(SoftwareSecurityCode)s</sts:SoftwareSecurityCode>
                        <sts:AuthorizationProvider>
                            <sts:AuthorizationProviderID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="4" schemeName="31">800197268</sts:AuthorizationProviderID>
                        </sts:AuthorizationProvider>
                        <sts:QRCode>URL=%(URLQRCode)s=%(UUID)s</sts:QRCode>
                    </sts:DianExtensions>
                </ext:ExtensionContent>
            </ext:UBLExtension>
            <ext:UBLExtension>
                <ext:ExtensionContent></ext:ExtensionContent>
            </ext:UBLExtension>
        </ext:UBLExtensions>
       <cbc:UBLVersionID>%(UBLVersionID)s</cbc:UBLVersionID>
       <cbc:CustomizationID>%(CustomizationID)s</cbc:CustomizationID>
       <cbc:ProfileID>%(ProfileID)s</cbc:ProfileID>
       <cbc:ProfileExecutionID>%(ProfileExecutionID)s</cbc:ProfileExecutionID>
       <cbc:ID>%(InvoiceID)s</cbc:ID>
       <cbc:UUID schemeID="%(ProfileExecutionID)s" schemeName="CUDS-SHA384">%(UUID)s</cbc:UUID>
       <cbc:IssueDate>%(IssueDate)s</cbc:IssueDate>
       <cbc:IssueTime>%(IssueTime)s</cbc:IssueTime>
       <cbc:InvoiceTypeCode>%(InvoiceTypeCode)s</cbc:InvoiceTypeCode>
       <cbc:DocumentCurrencyCode>%(DocumentCurrencyCode)s</cbc:DocumentCurrencyCode>
       <cbc:LineCountNumeric>%(LineCountNumeric)s</cbc:LineCountNumeric>
       <cac:AccountingSupplierParty>
          <cbc:AdditionalAccountID>%(SupplierAdditionalAccountID)s</cbc:AdditionalAccountID>
          <cac:Party>
             <cac:PartyName>
                <cbc:Name>%(SupplierPartyName)s</cbc:Name>
             </cac:PartyName>
             <cac:PhysicalLocation>
                <cac:Address>
                   <cbc:ID>%(SupplierCityCode)s</cbc:ID>
                   <cbc:CityName>%(SupplierCityName)s</cbc:CityName>
                    <cbc:PostalZone>""" + self.document_id.partner_id.zip + """</cbc:PostalZone>
                   <cbc:CountrySubentity>%(SupplierCountrySubentity)s</cbc:CountrySubentity>
                   <cbc:CountrySubentityCode>%(SupplierCountrySubentityCode)s</cbc:CountrySubentityCode>
                   <cac:AddressLine>
                      <cbc:Line>%(SupplierLine)s</cbc:Line>
                   </cac:AddressLine>
                   <cac:Country>
                      <cbc:IdentificationCode>%(SupplierCountryCode)s</cbc:IdentificationCode>
                      <cbc:Name languageID="es">%(SupplierCountryName)s</cbc:Name>
                   </cac:Country>
                </cac:Address>
             </cac:PhysicalLocation>
             <cac:PartyTaxScheme>
                <cbc:RegistrationName>%(SupplierPartyName)s</cbc:RegistrationName>
                <cbc:CompanyID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="%(schemeID)s" schemeName="31">%(ProviderID)s</cbc:CompanyID>
                <cbc:TaxLevelCode listName="48">%(SupplierTaxLevelCode)s</cbc:TaxLevelCode>
                <cac:RegistrationAddress>
                   <cbc:ID>%(SupplierCityCode)s</cbc:ID>
                   <cbc:CityName>%(SupplierCityName)s</cbc:CityName>
                   <cbc:CountrySubentity>%(SupplierCountrySubentity)s</cbc:CountrySubentity>
                   <cbc:CountrySubentityCode>%(SupplierCountrySubentityCode)s</cbc:CountrySubentityCode>

                   <cac:AddressLine>
                      <cbc:Line>%(SupplierLine)s</cbc:Line>
                   </cac:AddressLine>
                   <cac:Country>
                      <cbc:IdentificationCode>%(SupplierCountryCode)s</cbc:IdentificationCode>
                      <cbc:Name languageID="es">%(SupplierCountryName)s</cbc:Name>
                   </cac:Country>
                </cac:RegistrationAddress>
                <cac:TaxScheme>
                   <cbc:ID>%(TaxSchemeID)s</cbc:ID>
                   <cbc:Name>%(TaxSchemeName)s</cbc:Name>
                </cac:TaxScheme>
             </cac:PartyTaxScheme>
             <cac:PartyLegalEntity>
                <cbc:RegistrationName>%(SupplierPartyName)s</cbc:RegistrationName>
                <cbc:CompanyID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="%(schemeID)s" schemeName="31">%(ProviderID)s</cbc:CompanyID>
                <cac:CorporateRegistrationScheme>
                   <cbc:ID>%(Prefix)s</cbc:ID>
                </cac:CorporateRegistrationScheme>
             </cac:PartyLegalEntity>
             <cac:Contact>
               <cbc:ElectronicMail>%(SupplierElectronicMail)s</cbc:ElectronicMail>
             </cac:Contact>
          </cac:Party>
       </cac:AccountingSupplierParty>
       <cac:AccountingCustomerParty>
          <cbc:AdditionalAccountID>%(CustomerAdditionalAccountID)s</cbc:AdditionalAccountID>
          <cac:Party>
             <cac:PartyIdentification>
                <cbc:ID schemeName="%(SchemeNameAdquiriente)s" schemeID="%(SchemeIDAdquiriente)s">%(IDAdquiriente)s</cbc:ID>
             </cac:PartyIdentification>
             <cac:PartyName>
                <cbc:Name>%(CustomerPartyName)s</cbc:Name>
             </cac:PartyName>
             <cac:PhysicalLocation>
                <cac:Address>
                   <cbc:ID>%(CustomerCityCode)s</cbc:ID>
                   <cbc:CityName>%(CustomerCityName)s</cbc:CityName>
                   <cbc:CountrySubentity>%(CustomerCountrySubentity)s</cbc:CountrySubentity>
                   <cbc:CountrySubentityCode>%(CustomerCountrySubentityCode)s</cbc:CountrySubentityCode>
                   <cac:AddressLine>
                      <cbc:Line>%(CustomerLine)s</cbc:Line>
                   </cac:AddressLine>
                   <cac:Country>
                      <cbc:IdentificationCode>%(CustomerCountryCode)s</cbc:IdentificationCode>
                      <cbc:Name languageID="es">%(CustomerCountryName)s</cbc:Name>
                   </cac:Country>
                </cac:Address>
             </cac:PhysicalLocation>
             <cac:PartyTaxScheme>
                <cbc:RegistrationName>%(CustomerPartyName)s</cbc:RegistrationName>
                <cbc:CompanyID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="%(CustomerschemeID)s" schemeName="31">%(CustomerID)s</cbc:CompanyID>
                <cbc:TaxLevelCode listName="48">%(CustomerTaxLevelCode)s</cbc:TaxLevelCode>
                <cac:RegistrationAddress>
                   <cbc:ID>%(CustomerCityCode)s</cbc:ID>
                   <cbc:CityName>%(CustomerCityName)s</cbc:CityName>
                   <cbc:CountrySubentity>%(CustomerCountrySubentity)s</cbc:CountrySubentity>
                   <cbc:CountrySubentityCode>%(CustomerCountrySubentityCode)s</cbc:CountrySubentityCode>
                   <cac:AddressLine>
                      <cbc:Line>%(CustomerLine)s</cbc:Line>
                   </cac:AddressLine>
                   <cac:Country>
                      <cbc:IdentificationCode>%(CustomerCountryCode)s</cbc:IdentificationCode>
                      <cbc:Name languageID="es">%(CustomerCountryName)s</cbc:Name>
                   </cac:Country>
                </cac:RegistrationAddress>
                <cac:TaxScheme>
                   <cbc:ID>%(TaxSchemeID)s</cbc:ID>
                   <cbc:Name>%(TaxSchemeName)s</cbc:Name>
                </cac:TaxScheme>
             </cac:PartyTaxScheme>
             <cac:PartyLegalEntity>
                <cbc:RegistrationName>%(CustomerPartyName)s</cbc:RegistrationName>
                <cbc:CompanyID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="%(CustomerschemeID)s" schemeName="31">%(CustomerID)s</cbc:CompanyID>
            </cac:PartyLegalEntity>
            <cac:Contact>
               <cbc:ElectronicMail>%(CustomerElectronicMail)s</cbc:ElectronicMail>
            </cac:Contact>
            <cac:Person>
               <cbc:FirstName>%(Firstname)s</cbc:FirstName>
            </cac:Person>
          </cac:Party>
       </cac:AccountingCustomerParty>
       <cac:PaymentMeans>
          <cbc:ID>%(PaymentMeansID)s</cbc:ID>
          <cbc:PaymentMeansCode>%(PaymentMeansCode)s</cbc:PaymentMeansCode>
          <cbc:PaymentDueDate>%(PaymentDueDate)s</cbc:PaymentDueDate>
          <cbc:PaymentID>1234</cbc:PaymentID>
       </cac:PaymentMeans>
       <cac:PaymentExchangeRate>
          <cbc:SourceCurrencyCode>%(CurrencyID)s</cbc:SourceCurrencyCode>
          <cbc:SourceCurrencyBaseRate>1.00</cbc:SourceCurrencyBaseRate>
          <cbc:TargetCurrencyCode>COP</cbc:TargetCurrencyCode>
          <cbc:TargetCurrencyBaseRate>1.00</cbc:TargetCurrencyBaseRate>
          <cbc:CalculationRate>%(CalculationRate)s</cbc:CalculationRate>
          <cbc:Date>%(DateRate)s</cbc:Date>
       </cac:PaymentExchangeRate>%(data_taxs_xml)s
       <cac:LegalMonetaryTotal>
          <cbc:LineExtensionAmount currencyID="%(CurrencyID)s">%(TotalLineExtensionAmount)s</cbc:LineExtensionAmount>
          <cbc:TaxExclusiveAmount currencyID="%(CurrencyID)s">%(TotalTaxExclusiveAmount)s</cbc:TaxExclusiveAmount>
          <cbc:TaxInclusiveAmount currencyID="%(CurrencyID)s">%(TotalTaxInclusiveAmount)s</cbc:TaxInclusiveAmount>
          <cbc:PayableAmount currencyID="%(CurrencyID)s">%(PayableAmount)s</cbc:PayableAmount>
       </cac:LegalMonetaryTotal>%(data_lines_xml)s
    </Invoice>
    """
        return xml


    def _template_line_data_xml(self):
        xml = super(DianDocument, self)._template_line_data_xml()
        if self.document_id.move_type == 'in_invoice':
            invoice_has_iva = self.document_id.line_ids.tax_ids.filtered(lambda r: r.tax_group_fe == 'iva_fe')
            xml = """
            <cac:InvoiceLine>
            <cbc:ID>%(ILLinea)s</cbc:ID>
            <cbc:Note>%(InvoiceLineNote)s</cbc:Note>
            <cbc:InvoicedQuantity unitCode="EA">%(ILInvoicedQuantity)s</cbc:InvoicedQuantity>
            <cbc:LineExtensionAmount currencyID="%(CurrencyID)s">%(ILLineExtensionAmount)s</cbc:LineExtensionAmount>
            <cbc:FreeOfChargeIndicator>false</cbc:FreeOfChargeIndicator>
            <cac:InvoicePeriod>
                <cbc:StartDate>%(InvoicePeriodStartDate)s</cbc:StartDate>
                <cbc:DescriptionCode>%(InvoicePeriod)s</cbc:DescriptionCode>
                <cbc:Description>%(InvoicePeriodDescription)s</cbc:Description>
            </cac:InvoicePeriod>
            """ + ("""<cac:TaxTotal>
               <cbc:TaxAmount currencyID="%(CurrencyID)s">%(ILTaxAmount)s</cbc:TaxAmount>%(InvoiceLineTaxSubtotal)s
            </cac:TaxTotal>""" if invoice_has_iva else '')  + """<cac:Item>
                <cbc:Description>%(ILDescription)s</cbc:Description>
                <cac:StandardItemIdentification>
                  <cbc:ID schemeAgencyID="10" schemeID="001" schemeName="UNSPSC">%(ID_UNSPSC)s</cbc:ID>
                </cac:StandardItemIdentification>
                %(InformationContentProviderParty)s
            </cac:Item>
            <cac:Price>
                <cbc:PriceAmount currencyID="%(CurrencyID)s">%(ILPriceAmount)s</cbc:PriceAmount>
                <cbc:BaseQuantity unitCode="NIU">%(ILInvoicedQuantity)s</cbc:BaseQuantity>
            </cac:Price>
            </cac:InvoiceLine>"""
        return xml


    def _template_credit_line_data_xml(self):
        xml = super(DianDocument, self)._template_credit_line_data_xml()
        if self.document_id.move_type == 'in_refund':
            xml = """
            <cac:CreditNoteLine>
            <cbc:ID>%(ILLinea)s</cbc:ID>
            <cbc:CreditedQuantity unitCode="EA">%(ILInvoicedQuantity)s</cbc:CreditedQuantity>
            <cbc:LineExtensionAmount currencyID="%(CurrencyID)s">%(ILLineExtensionAmount)s</cbc:LineExtensionAmount>
            <cbc:FreeOfChargeIndicator>false</cbc:FreeOfChargeIndicator>
            <cac:Item>
                <cbc:Description>%(ILDescription)s</cbc:Description>
                <cac:StandardItemIdentification>
                  <cbc:ID schemeAgencyID="10" schemeID="001" schemeName="UNSPSC">%(ID_UNSPSC)s</cbc:ID>
                </cac:StandardItemIdentification>
                %(InformationContentProviderParty)s
            </cac:Item>
            <cac:Price>
                <cbc:PriceAmount currencyID="%(CurrencyID)s">%(ILPriceAmount)s</cbc:PriceAmount>
                <cbc:BaseQuantity unitCode="NIU">%(ILInvoicedQuantity)s</cbc:BaseQuantity>
            </cac:Price>
            </cac:CreditNoteLine>"""
        return xml



    def _template_basic_data_nc_xml(self):
        xml = super(DianDocument, self)._template_basic_data_nc_xml()
        if self.document_id.move_type == 'in_refund':
            xml = """
            <CreditNote xmlns="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" xmlns:sts="dian:gov:co:facturaelectronica:Structures-2-1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2 http://docs.oasis-open.org/ubl/os-UBL-2.1/xsd/maindoc/UBL-CreditNote-2.1.xsd" xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#">
                <ext:UBLExtensions>
                    <ext:UBLExtension>
                        <ext:ExtensionContent>
                            <sts:DianExtensions>
                                <sts:InvoiceSource>
                                    <cbc:IdentificationCode listAgencyID="6" listAgencyName="United Nations Economic Commission for Europe" listSchemeURI="urn:oasis:names:specification:ubl:codelist:gc:CountryIdentificationCode-2.1">%(IdentificationCode)s</cbc:IdentificationCode>
                                </sts:InvoiceSource>
                                <sts:SoftwareProvider>
                                    <sts:ProviderID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="%(SoftwareProviderSchemeID)s" schemeName="31">%(SoftwareProviderID)s</sts:ProviderID>
                                    <sts:SoftwareID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)">%(SoftwareID)s</sts:SoftwareID>
                                </sts:SoftwareProvider>
                                <sts:SoftwareSecurityCode schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)">%(SoftwareSecurityCode)s</sts:SoftwareSecurityCode>
                                <sts:AuthorizationProvider>
                                    <sts:AuthorizationProviderID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="4" schemeName="31">800197268</sts:AuthorizationProviderID>
                                </sts:AuthorizationProvider>
                                <sts:QRCode>URL=%(URLQRCode)s=%(UUID)s</sts:QRCode>
                            </sts:DianExtensions>
                        </ext:ExtensionContent>
                    </ext:UBLExtension>
                    <ext:UBLExtension>
                        <ext:ExtensionContent></ext:ExtensionContent>
                    </ext:UBLExtension>
                </ext:UBLExtensions>

                <cbc:UBLVersionID>%(UBLVersionID)s</cbc:UBLVersionID>
                <cbc:CustomizationID>%(CustomizationID)s</cbc:CustomizationID>
                <cbc:ProfileID>%(ProfileID)s</cbc:ProfileID>
                <cbc:ProfileExecutionID>%(ProfileExecutionID)s</cbc:ProfileExecutionID>
                <cbc:ID>%(InvoiceID)s</cbc:ID>
                <cbc:UUID schemeID="%(ProfileExecutionID)s" schemeName="CUDS-SHA384">%(UUID)s</cbc:UUID>
                <cbc:IssueDate>%(IssueDate)s</cbc:IssueDate>
                <cbc:IssueTime>%(IssueTime)s</cbc:IssueTime>
                <cbc:CreditNoteTypeCode>%(CreditNoteTypeCode)s</cbc:CreditNoteTypeCode>
                <cbc:DocumentCurrencyCode>%(DocumentCurrencyCode)s</cbc:DocumentCurrencyCode>
                <cbc:LineCountNumeric>%(LineCountNumeric)s</cbc:LineCountNumeric>
                <cac:DiscrepancyResponse>
                    <cbc:ReferenceID>%(DiscrepancyResponseID)s</cbc:ReferenceID>
                    <cbc:ResponseCode>%(DiscrepancyResponseCode)s</cbc:ResponseCode>
                    <cbc:Description>%(DiscrepancyResponseDescription)s</cbc:Description>
                </cac:DiscrepancyResponse>
                <cac:BillingReference>
                   <cac:InvoiceDocumentReference>
                      <cbc:ID>%(InvoiceReferenceID)s</cbc:ID>
                      <cbc:UUID schemeName="CUDS-SHA384">%(InvoiceReferenceUUID)s</cbc:UUID>
                      <cbc:IssueDate>%(InvoiceReferenceDate)s</cbc:IssueDate>
                   </cac:InvoiceDocumentReference>
                </cac:BillingReference>
                <cac:AccountingSupplierParty>
                  <cbc:AdditionalAccountID>%(SupplierAdditionalAccountID)s</cbc:AdditionalAccountID>
                  <cac:Party>
                     <cac:PartyName>
                        <cbc:Name>%(SupplierPartyName)s</cbc:Name>
                     </cac:PartyName>
                     <cac:PhysicalLocation>
                        <cac:Address>
                           <cbc:ID>%(SupplierCityCode)s</cbc:ID>
                           <cbc:CityName>%(SupplierCityName)s</cbc:CityName>
                           <cbc:PostalZone>""" + self.document_id.partner_id.zip + """</cbc:PostalZone>
                           <cbc:CountrySubentity>%(SupplierCountrySubentity)s</cbc:CountrySubentity>
                           <cbc:CountrySubentityCode>%(SupplierCountrySubentityCode)s</cbc:CountrySubentityCode>
                           <cac:AddressLine>
                              <cbc:Line>%(SupplierLine)s</cbc:Line>
                           </cac:AddressLine>
                           <cac:Country>
                              <cbc:IdentificationCode>%(SupplierCountryCode)s</cbc:IdentificationCode>
                              <cbc:Name languageID="es">%(SupplierCountryName)s</cbc:Name>
                           </cac:Country>
                        </cac:Address>
                     </cac:PhysicalLocation>
                     <cac:PartyTaxScheme>
                        <cbc:RegistrationName>%(SupplierPartyName)s</cbc:RegistrationName>
                        <cbc:CompanyID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="%(schemeID)s" schemeName="31">%(ProviderID)s</cbc:CompanyID>
                        <cbc:TaxLevelCode listName="48">%(SupplierTaxLevelCode)s</cbc:TaxLevelCode>
                        <cac:RegistrationAddress>
                           <cbc:ID>%(SupplierCityCode)s</cbc:ID>
                           <cbc:CityName>%(SupplierCityName)s</cbc:CityName>
                           <cbc:CountrySubentity>%(SupplierCountrySubentity)s</cbc:CountrySubentity>
                           <cbc:CountrySubentityCode>%(SupplierCountrySubentityCode)s</cbc:CountrySubentityCode>
                           <cac:AddressLine>
                              <cbc:Line>%(SupplierLine)s</cbc:Line>
                           </cac:AddressLine>
                           <cac:Country>
                              <cbc:IdentificationCode>%(SupplierCountryCode)s</cbc:IdentificationCode>
                              <cbc:Name languageID="es">%(SupplierCountryName)s</cbc:Name>
                           </cac:Country>
                        </cac:RegistrationAddress>
                        <cac:TaxScheme>
                           <cbc:ID>%(TaxSchemeID)s</cbc:ID>
                           <cbc:Name>%(TaxSchemeName)s</cbc:Name>
                        </cac:TaxScheme>
                     </cac:PartyTaxScheme>
                     <cac:PartyLegalEntity>
                        <cbc:RegistrationName>%(SupplierPartyName)s</cbc:RegistrationName>
                        <cbc:CompanyID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="%(schemeID)s" schemeName="31">%(ProviderID)s</cbc:CompanyID>
                        <cac:CorporateRegistrationScheme>
                           <cbc:ID>%(Prefix)s</cbc:ID>
                        </cac:CorporateRegistrationScheme>
                     </cac:PartyLegalEntity>
                     <cac:Contact>
                       <cbc:ElectronicMail>%(SupplierElectronicMail)s</cbc:ElectronicMail>
                     </cac:Contact>
                  </cac:Party>
                </cac:AccountingSupplierParty>
                <cac:AccountingCustomerParty>
                   <cbc:AdditionalAccountID>%(CustomerAdditionalAccountID)s</cbc:AdditionalAccountID>
                   <cac:Party>
                      <cac:PartyIdentification>
                         <cbc:ID schemeName="%(SchemeNameAdquiriente)s" schemeID="%(SchemeIDAdquiriente)s">%(IDAdquiriente)s</cbc:ID>
                      </cac:PartyIdentification>
                      <cac:PartyName>
                         <cbc:Name>%(CustomerPartyName)s</cbc:Name>
                      </cac:PartyName>
                      <cac:PhysicalLocation>
                         <cac:Address>
                            <cbc:ID>%(CustomerCityCode)s</cbc:ID>
                            <cbc:CityName>%(CustomerCityName)s</cbc:CityName>
                            <cbc:CountrySubentity>%(CustomerCountrySubentity)s</cbc:CountrySubentity>
                            <cbc:CountrySubentityCode>%(CustomerCountrySubentityCode)s</cbc:CountrySubentityCode>
                            <cac:AddressLine>
                               <cbc:Line>%(CustomerLine)s</cbc:Line>
                            </cac:AddressLine>
                            <cac:Country>
                               <cbc:IdentificationCode>%(CustomerCountryCode)s</cbc:IdentificationCode>
                               <cbc:Name languageID="es">%(CustomerCountryName)s</cbc:Name>
                            </cac:Country>
                         </cac:Address>
                      </cac:PhysicalLocation>
                      <cac:PartyTaxScheme>
                         <cbc:RegistrationName>%(CustomerPartyName)s</cbc:RegistrationName>
                         <cbc:CompanyID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="%(CustomerschemeID)s" schemeName="31">%(CustomerID)s</cbc:CompanyID>
                         <cbc:TaxLevelCode listName="48">%(CustomerTaxLevelCode)s</cbc:TaxLevelCode>
                         <cac:RegistrationAddress>
                            <cbc:ID>%(CustomerCityCode)s</cbc:ID>
                            <cbc:CityName>%(CustomerCityName)s</cbc:CityName>
                            <cbc:CountrySubentity>%(CustomerCountrySubentity)s</cbc:CountrySubentity>
                            <cbc:CountrySubentityCode>%(CustomerCountrySubentityCode)s</cbc:CountrySubentityCode>
                            <cac:AddressLine>
                               <cbc:Line>%(CustomerLine)s</cbc:Line>
                            </cac:AddressLine>
                            <cac:Country>
                               <cbc:IdentificationCode>%(CustomerCountryCode)s</cbc:IdentificationCode>
                               <cbc:Name languageID="es">%(CustomerCountryName)s</cbc:Name>
                            </cac:Country>
                         </cac:RegistrationAddress>
                         <cac:TaxScheme>
                            <cbc:ID>%(TaxSchemeID)s</cbc:ID>
                            <cbc:Name>%(TaxSchemeName)s</cbc:Name>
                         </cac:TaxScheme>
                      </cac:PartyTaxScheme>
                      <cac:PartyLegalEntity>
                         <cbc:RegistrationName>%(CustomerPartyName)s</cbc:RegistrationName>
                         <cbc:CompanyID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="%(CustomerschemeID)s" schemeName="31">%(CustomerID)s</cbc:CompanyID>
                     </cac:PartyLegalEntity>
                     <cac:Contact>
                        <cbc:ElectronicMail>%(CustomerElectronicMail)s</cbc:ElectronicMail>
                     </cac:Contact>
                     <cac:Person>
                        <cbc:FirstName>%(Firstname)s</cbc:FirstName>
                     </cac:Person>
                   </cac:Party>
                </cac:AccountingCustomerParty>
                <cac:PaymentMeans>
                   <cbc:ID>%(PaymentMeansID)s</cbc:ID>
                   <cbc:PaymentMeansCode>%(PaymentMeansCode)s</cbc:PaymentMeansCode>
                   <cbc:PaymentDueDate>%(PaymentDueDate)s</cbc:PaymentDueDate>
                   <cbc:PaymentID>1234</cbc:PaymentID>
                </cac:PaymentMeans>
                <cac:PaymentExchangeRate>
                  <cbc:SourceCurrencyCode>%(CurrencyID)s</cbc:SourceCurrencyCode>
                  <cbc:SourceCurrencyBaseRate>1.00</cbc:SourceCurrencyBaseRate>
                  <cbc:TargetCurrencyCode>COP</cbc:TargetCurrencyCode>
                  <cbc:TargetCurrencyBaseRate>1.00</cbc:TargetCurrencyBaseRate>
                  <cbc:CalculationRate>%(CalculationRate)s</cbc:CalculationRate>
                  <cbc:Date>%(DateRate)s</cbc:Date>
               </cac:PaymentExchangeRate>
                %(data_taxs_xml)s
                <cac:LegalMonetaryTotal>
                   <cbc:LineExtensionAmount currencyID="%(CurrencyID)s">%(TotalLineExtensionAmount)s</cbc:LineExtensionAmount>
                   <cbc:TaxExclusiveAmount currencyID="%(CurrencyID)s">%(TotalTaxExclusiveAmount)s</cbc:TaxExclusiveAmount>
                   <cbc:TaxInclusiveAmount currencyID="%(CurrencyID)s">%(TotalTaxInclusiveAmount)s</cbc:TaxInclusiveAmount>
                   <cbc:PayableAmount currencyID="%(CurrencyID)s">%(PayableAmount)s</cbc:PayableAmount>
                </cac:LegalMonetaryTotal>%(data_credit_lines_xml)s

            </CreditNote>"""
        return xml

    def _template_debit_line_data_xml(self):
        xml = super(DianDocument, self)._template_debit_line_data_xml()
        if self.document_id.move_type == 'in_invoice' and self.document_id.debit_origin_id:
            template_debit_line_data_xml = """
    <cac:DebitNoteLine>
        <cbc:ID>%(ILLinea)s</cbc:ID>
        <cbc:DebitedQuantity unitCode="EA">%(ILInvoicedQuantity)s</cbc:DebitedQuantity>
        <cbc:LineExtensionAmount currencyID="%(CurrencyID)s">%(ILLineExtensionAmount)s</cbc:LineExtensionAmount>
        <cac:TaxTotal>
            <cbc:RoundingAmount currencyID="{{currency_id}}">0</cbc:RoundingAmount>
            <cbc:TaxAmount currencyID="%(CurrencyID)s">%(ILTaxAmount)s</cbc:TaxAmount>
                <cac:TaxSubtotal>
                    <cbc:TaxableAmount currencyID="%(CurrencyID)s">%(ILTaxableAmount)s</cbc:TaxableAmount>
                    <cbc:TaxAmount currencyID="%(CurrencyID)s">%(ILTaxAmount)s</cbc:TaxAmount>
                    <cac:TaxCategory>
                        <cbc:Percent>%(ILPercent)s</cbc:Percent>
                        <cac:TaxScheme>
                            <cbc:ID>%(ILID)s</cbc:ID>
                            <cbc:Name>%(ILName)s</cbc:Name>
                        </cac:TaxScheme>
                    </cac:TaxCategory>
                </cac:TaxSubtotal>
        </cac:TaxTotal>
        <cac:Item>
            <cbc:Description>%(ILDescription)s</cbc:Description>
            <cac:StandardItemIdentification>
              <cbc:ID schemeID="999">%(ID_UNSPSC)s</cbc:ID>
            </cac:StandardItemIdentification>
            %(InformationContentProviderParty)s
        </cac:Item>
        <cac:Price>
            <cbc:PriceAmount currencyID="%(CurrencyID)s">%(ILPriceAmount)s</cbc:PriceAmount>
            <cbc:BaseQuantity unitCode="NIU">1.0000</cbc:BaseQuantity>
        </cac:Price>
    </cac:DebitNoteLine>"""
        return xml

    def _template_basic_data_nd_xml(self):
        xml = super(DianDocument, self)._template_basic_data_nd_xml()
        if self.document_id.move_type == 'in_invoice' and self.document_id.debit_origin_id:
            xml = """
<DebitNote xmlns="urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2" xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" xmlns:sts="http://www.dian.gov.co/contratos/facturaelectronica/v1/Structures" xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" xmlns:xades141="http://uri.etsi.org/01903/v1.4.1#" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2 http://docs.oasis-open.org/ubl/os-UBL-2.1/xsd/maindoc/UBL-DebitNote-2.1.xsd">
    <ext:UBLExtensions>
        <ext:UBLExtension>
            <ext:ExtensionContent>
                <sts:DianExtensions>
                    <sts:InvoiceSource>
                        <cbc:IdentificationCode listAgencyID="6" listAgencyName="United Nations Economic Commission for Europe" listSchemeURI="urn:oasis:names:specification:ubl:codelist:gc:CountryIdentificationCode-2.1">%(IdentificationCode)s</cbc:IdentificationCode>
                    </sts:InvoiceSource>
                    <sts:SoftwareProvider>
                        <sts:ProviderID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="%(CustomerschemeID)s" schemeName="31">%(ProviderID)s</sts:ProviderID>
                        <sts:SoftwareID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)">%(SoftwareID)s</sts:SoftwareID>
                    </sts:SoftwareProvider>
                    <sts:SoftwareSecurityCode schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)">%(SoftwareSecurityCode)s</sts:SoftwareSecurityCode>
                    <sts:AuthorizationProvider>
                        <sts:AuthorizationProviderID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="4" schemeName="31">800197268</sts:AuthorizationProviderID>
                    </sts:AuthorizationProvider>
                    <sts:QRCode>URL=%(URLQRCode)s=%(UUID)s</sts:QRCode>
                </sts:DianExtensions>
            </ext:ExtensionContent>
        </ext:UBLExtension>
        <ext:UBLExtension>
            <ext:ExtensionContent/>
        </ext:UBLExtension>
    </ext:UBLExtensions>
    <cbc:UBLVersionID>%(UBLVersionID)s</cbc:UBLVersionID>
    <cbc:CustomizationID>%(CustomizationID)s</cbc:CustomizationID>
    <cbc:ProfileID>DIAN 2.1: Nota Débito de Factura Electrónica de Venta</cbc:ProfileID>
    <cbc:ProfileExecutionID>%(ProfileExecutionID)s</cbc:ProfileExecutionID>
    <cbc:ID>%(InvoiceID)s</cbc:ID>
    <cbc:UUID schemeID="%(ProfileExecutionID)s" schemeName="CUDE-SHA384">%(UUID)s</cbc:UUID>
    <cbc:IssueDate>%(IssueDate)s</cbc:IssueDate>
    <cbc:IssueTime>%(IssueTime)s</cbc:IssueTime>
    <cbc:Note>%(DescriptionDebitCreditNote)s</cbc:Note>
    <cbc:DocumentCurrencyCode>%(DocumentCurrencyCode)s</cbc:DocumentCurrencyCode>
    <cbc:LineCountNumeric>%(LineCountNumeric)s</cbc:LineCountNumeric>
    <cac:DiscrepancyResponse>
        <cbc:ReferenceID>%(DiscrepancyResponseID)s</cbc:ReferenceID>
        <cbc:ResponseCode>%(DiscrepancyResponseCode)s</cbc:ResponseCode>
        <cbc:Description>%(DiscrepancyResponseDescription)s</cbc:Description>
    </cac:DiscrepancyResponse>
    <cac:BillingReference>
        <cac:InvoiceDocumentReference>
            <cbc:ID>%(InvoiceReferenceID)s</cbc:ID>
            <cbc:UUID schemeName="CUFE-SHA384">%(InvoiceReferenceUUID)s</cbc:UUID>
            <cbc:IssueDate>%(InvoiceReferenceDate)s</cbc:IssueDate>
        </cac:InvoiceDocumentReference>
    </cac:BillingReference>
    <cac:AccountingSupplierParty>
        <cbc:AdditionalAccountID schemeAgencyID="195">%(SupplierAdditionalAccountID)s</cbc:AdditionalAccountID>
        <cac:Party>
            <cac:PartyName>
                <cbc:Name>%(SupplierPartyName)s</cbc:Name>
            </cac:PartyName>
            <cac:PhysicalLocation>
                <cac:Address>
                    <cbc:ID>%(SupplierCityCode)s</cbc:ID>
                    <cbc:CityName>%(SupplierCityName)s</cbc:CityName>
                    <cbc:PostalZone>%(SupplierPostal)s</cbc:PostalZone>
                    <cbc:CountrySubentity>%(SupplierCountrySubentity)s</cbc:CountrySubentity>
                    <cbc:CountrySubentityCode>%(SupplierCountrySubentityCode)s</cbc:CountrySubentityCode>
                    <cac:AddressLine>
                        <cbc:Line>%(SupplierLine)s</cbc:Line>
                    </cac:AddressLine>
                    <cac:Country>
                        <cbc:IdentificationCode>%(SupplierCountryCode)s</cbc:IdentificationCode>
                        <cbc:Name languageID="es">%(SupplierCountryName)s</cbc:Name>
                    </cac:Country>
                </cac:Address>
            </cac:PhysicalLocation>
            <cac:PartyTaxScheme>
                <cbc:RegistrationName>%(SupplierPartyName)s</cbc:RegistrationName>
                <cbc:CompanyID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="%(schemeID)s" schemeName="31">%(ProviderID)s</cbc:CompanyID>
                <cbc:TaxLevelCode listName="48">%(SupplierTaxLevelCode)s</cbc:TaxLevelCode>
                <cac:RegistrationAddress>
                    <cbc:ID>%(SupplierCityCode)s</cbc:ID>
                    <cbc:CityName>%(SupplierCityName)s</cbc:CityName>
                    <cbc:PostalZone>%(SupplierPostal)s</cbc:PostalZone>
                    <cbc:CountrySubentity>%(SupplierCountrySubentity)s</cbc:CountrySubentity>
                    <cbc:CountrySubentityCode>%(SupplierCountrySubentityCode)s</cbc:CountrySubentityCode>
                    <cac:AddressLine>
                        <cbc:Line>%(SupplierLine)s</cbc:Line>
                    </cac:AddressLine>
                    <cac:Country>
                        <cbc:IdentificationCode>%(SupplierCountryCode)s</cbc:IdentificationCode>
                        <cbc:Name languageID="es">%(SupplierCountryName)s</cbc:Name>
                    </cac:Country>
                </cac:RegistrationAddress>
                <cac:TaxScheme>
                    <cbc:ID>%(TaxSchemeID)s</cbc:ID>
                    <cbc:Name>%(TaxSchemeName)s</cbc:Name>
                </cac:TaxScheme>
            </cac:PartyTaxScheme>
            <cac:PartyLegalEntity>
                <cbc:RegistrationName>%(SupplierPartyName)s</cbc:RegistrationName>
                <cbc:CompanyID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="%(schemeID)s" schemeName="31">%(ProviderID)s</cbc:CompanyID>
                <cac:CorporateRegistrationScheme>
                    <cbc:ID>%(Prefix)s</cbc:ID>
                    <cbc:Name>%(SupplierPartyName)s</cbc:Name>
                </cac:CorporateRegistrationScheme>
            </cac:PartyLegalEntity>
            <cac:Contact>
                <cbc:Telephone>%(SupplierPartyPhone)s</cbc:Telephone>
                <cbc:ElectronicMail>%(SupplierElectronicMail)s</cbc:ElectronicMail>
            </cac:Contact>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:AccountingCustomerParty>
        <cbc:AdditionalAccountID>%(CustomerAdditionalAccountID)s</cbc:AdditionalAccountID>
        <cac:Party>
            <cac:PartyIdentification>
                <cbc:ID schemeName="%(SchemeNameAdquiriente)s" schemeID="%(SchemeIDAdquiriente)s">%(IDAdquiriente)s</cbc:ID>
            </cac:PartyIdentification>
            <cac:PartyName>
                <cbc:Name>%(CustomerPartyName)s</cbc:Name>
            </cac:PartyName>
            <cac:PhysicalLocation>
                <cac:Address>
                    <cbc:ID>%(CustomerCityCode)s</cbc:ID>
                    <cbc:CityName>%(CustomerCityName)s</cbc:CityName>
                    <cbc:PostalZone>%(CustomerPostal)s</cbc:PostalZone>
                    <cbc:CountrySubentity>%(CustomerCountrySubentity)s</cbc:CountrySubentity>
                    <cbc:CountrySubentityCode>%(CustomerCountrySubentityCode)s</cbc:CountrySubentityCode>
                    <cac:AddressLine>
                        <cbc:Line>%(CustomerLine)s</cbc:Line>
                    </cac:AddressLine>
                    <cac:Country>
                        <cbc:IdentificationCode>%(CustomerCountryCode)s</cbc:IdentificationCode>
                        <cbc:Name languageID="es">%(CustomerCountryName)s</cbc:Name>
                    </cac:Country>
                </cac:Address>
            </cac:PhysicalLocation>
            <cac:PartyTaxScheme>
                <cbc:RegistrationName>%(CustomerPartyName)s</cbc:RegistrationName>
                <cbc:CompanyID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="%(CustomerschemeID)s" schemeName="31">%(CustomerID)s</cbc:CompanyID>
                <cbc:TaxLevelCode listName="48">%(CustomerTaxLevelCode)s</cbc:TaxLevelCode>
                <cac:RegistrationAddress>
                    <cbc:ID>%(CustomerCityCode)s</cbc:ID>
                    <cbc:CityName>%(CustomerCityName)s</cbc:CityName>
                    <cbc:CountrySubentity>%(CustomerCountrySubentity)s</cbc:CountrySubentity>
                    <cbc:CountrySubentityCode>%(CustomerCountrySubentityCode)s</cbc:CountrySubentityCode>
                    <cac:AddressLine>
                        <cbc:Line>%(CustomerLine)s</cbc:Line>
                    </cac:AddressLine>
                    <cac:Country>
                        <cbc:IdentificationCode>%(CustomerCountryCode)s</cbc:IdentificationCode>
                        <cbc:Name languageID="es">%(CustomerCountryName)s</cbc:Name>
                    </cac:Country>
                </cac:RegistrationAddress>
                <cac:TaxScheme>
                    <cbc:ID>%(TaxSchemeID)s</cbc:ID>
                    <cbc:Name>%(TaxSchemeName)s</cbc:Name>
                </cac:TaxScheme>
            </cac:PartyTaxScheme>
            <cac:PartyLegalEntity>
                <cbc:RegistrationName>%(CustomerPartyName)s</cbc:RegistrationName>
                <cbc:CompanyID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeID="%(CustomerschemeID)s" schemeName="31">%(CustomerID)s</cbc:CompanyID>
            </cac:PartyLegalEntity>
            <cac:Contact>
                <cbc:Telephone>%(CustomerElectronicPhone)s</cbc:Telephone>
                <cbc:ElectronicMail>%(CustomerElectronicMail)s</cbc:ElectronicMail>
            </cac:Contact>
            <cac:Person>
                <cbc:FirstName>%(Firstname)s</cbc:FirstName>
            </cac:Person>
        </cac:Party>
    </cac:AccountingCustomerParty>
    <cac:TaxRepresentativeParty>
        <cac:PartyIdentification>
            <cbc:ID schemeAgencyID="195" schemeAgencyName="CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)" schemeName="31" schemeID="%(CustomerschemeID)s">%(CustomerID)s</cbc:ID>
        </cac:PartyIdentification>
        <cac:PartyName>
            <cbc:Name>%(CustomerPartyName)s</cbc:Name>
        </cac:PartyName>
    </cac:TaxRepresentativeParty>
    <cac:PaymentMeans>
        <cbc:ID>%(PaymentMeansID)s</cbc:ID>
        <cbc:PaymentMeansCode>%(PaymentMeansCode)s</cbc:PaymentMeansCode>
        <cbc:PaymentDueDate>%(PaymentDueDate)s</cbc:PaymentDueDate>
        <cbc:PaymentID>1234</cbc:PaymentID>
    </cac:PaymentMeans>
    <cac:PaymentExchangeRate>
        <cbc:SourceCurrencyCode>%(CurrencyID)s</cbc:SourceCurrencyCode>
        <cbc:SourceCurrencyBaseRate>1.00</cbc:SourceCurrencyBaseRate>
        <cbc:TargetCurrencyCode>COP</cbc:TargetCurrencyCode>
        <cbc:TargetCurrencyBaseRate>1.00</cbc:TargetCurrencyBaseRate>
        <cbc:CalculationRate>%(CalculationRate)s</cbc:CalculationRate>
        <cbc:Date>%(DateRate)s</cbc:Date>
    </cac:PaymentExchangeRate>
                %(data_taxs_xml)s
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="%(CurrencyID)s">%(TotalLineExtensionAmount)s</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="%(CurrencyID)s">%(TotalTaxExclusiveAmount)s</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="%(CurrencyID)s">%(TotalTaxInclusiveAmount)s</cbc:TaxInclusiveAmount>
        <cbc:PayableAmount currencyID="%(CurrencyID)s">%(PayableAmount)s</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>%(data_debit_lines_xml)s
</DebitNote>"""
        return xml