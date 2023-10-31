# -*- coding: utf-8 -*-
from pytz import country_names
from odoo import SUPERUSER_ID, api, fields, models, _, exceptions
from odoo.exceptions import ValidationError, except_orm, Warning, UserError,RedirectWarning
import re
import logging
from lxml import etree
_logger = logging.getLogger(__name__)


#---------------------------Modelo RES-PARTNER / TERCEROS-------------------------------#
REGIMEN_TRIBUTATE = [
    ("23", "Persona Natural"),
    ("6", "Persona Natural Regimen Simplificado"),
    ("45", "Persona Natural Autorretenedor"),
    ("7", "Persona Juridica"),
    ("44", "Persona Juridica Regimen Simplificado"),
    ("25", "Persona Juridica Autorretenedor"),
    ("46", "Empresas de comercio internacional"),
    ("22", "Tercero del Exterior"),
    ("11", "Grandes contribuyentes autorretenedores"),
    ("24", "Grandes contribuyentes no autorretenedores"),
    ("47", "Sociedad sin animo de lucro"),
]

class_dian = [
    ("1", "Normal"),
    ("2", "Exportador"),
    ("3", "Importador"),
    ("7", "Tercero en Zona Franca"),
    ("8", "Importador en Zona Franca"),
    ("9", "Excluidos"),
]

PERSON_TYPE = [("1", "Persona Natural"), ("2", "Persona Juridica")]

TYPE_COMPANY = [("person", "Persona Natural"), ("company", "Persona Juridica")]
class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    type_account = fields.Selection([('A', 'Ahorros'), ('C', 'Corriente')], 'Tipo de Cuenta', required=True, default='A')
    is_main = fields.Boolean('Es Principal')
    
class ResPartner(models.Model):
    _inherit = 'res.partner'
    _order = 'name'

    @api.depends("vat_co")
    def _compute_concat_nit(self):
        """
        Concatenating and formatting the NIT number in order to have it
        consistent everywhere where it is needed
        @return: void
        """
        for partner in self:
            partner.formatedNit = ""
            if partner.l10n_latam_identification_type_id.l10n_co_document_code:
                if not partner.vat_co:
                    partner.vat_co = ""
                else:
                    partner.formatedNit = ""
                    s = str(partner.vat_co)[::-1]
                    newnit = ".".join(s[i : i + 3] for i in range(0, len(s), 3))
                    newnit = newnit[::-1]
                    nitList = [
                        newnit,
                        self._check_dv(str(partner.vat_co)),
                    ]
                    formatedNitList = []
                    for item in nitList:
                        if item != "":
                            formatedNitList.append(item)
                            partner.formatedNit = "-".join(formatedNitList)
                    for pnitem in self:
                        pnitem.dv = nitList[1]
            else:
                if not partner.vat_co:
                    partner.vat_co = ""
                else:
                    dv = self._check_dv(str(partner.vat_co))
                    for pnitem in self:
                        pnitem.dv = dv

    #TRACK VISIBILITY OLD FIELDS
    vat = fields.Char(tracking=True)
    street = fields.Char(tracking=True)
    country_id = fields.Many2one(tracking=True)
    state_id = fields.Many2one(tracking=True)
    zip = fields.Char(tracking=True)
    phone = fields.Char(tracking=True)
    mobile = fields.Char(tracking=True)
    email = fields.Char(tracking=True)
    website = fields.Char(tracking=True)
    lang = fields.Selection(tracking=True)
    category_id = fields.Many2many(tracking=True)
    user_id = fields.Many2one(tracking=True)    
    comment = fields.Text(tracking=True)
    name = fields.Char(tracking=True)
    city = fields.Char(string='Descripción ciudad')
    dv = fields.Integer(string=None,compute="_compute_verification_digit", store=True)
    #INFORMACION BASICA
    x_pn_retri = fields.Selection(REGIMEN_TRIBUTATE, string="Regimen de tributacion", default="23")
    class_dian = fields.Selection(class_dian, string="Clasificacion Dian", default="1")
    personType = fields.Selection(PERSON_TYPE, "Tipo de persona", default="1")
    company_type = fields.Selection(TYPE_COMPANY, string="Company Type")

    formatedNit = fields.Char(
        string="NIT Formatted", compute="_compute_concat_nit", store=True
    )
    l10n_latam_identification_type_id = fields.Many2one(
        default=lambda self: self.env.ref(
            "l10n_co_res_partner.no_identification", raise_if_not_found=False
        )
    )

    l10n_co_document_code = fields.Char(
        related="l10n_latam_identification_type_id.l10n_co_document_code", readonly=True
    )
    vat_co = fields.Char(
        string="Numero RUT/NIT/CC",
    )
    vat_ref = fields.Char(
        string="NIT Formateado",
        compute="_compute_vat_ref",
        readonly=True,
    )
    vat_vd = fields.Char(
        string=u"Digito Verificación", size=1, tracking=True
    )
    ciiu_id = fields.Many2one(
        string='Actividad CIIU',
        comodel_name='lavish.ciiu',
        help=u'Código industrial internacional uniforme (CIIU)'
    )

    taxes_ids = fields.Many2many(
        string="Customer taxes",
        comodel_name="account.tax",
        relation="partner_tax_sale_rel",
        column1="partner_id",
        column2="tax_id",
        domain="[('type_tax_use','=','sale')]",
        help="Taxes applied for sale.",
    )
    supplier_taxes_ids =  fields.Many2many(
        string="Supplier taxes",
        comodel_name="account.tax",
        relation="partner_tax_purchase_rel",
        column1="partner_id",
        column2="tax_id",
        domain="[('type_tax_use','=','purchase')]",
        help="Taxes applied for purchase.",
    )
    country_id = fields.Many2one('res.country', string='Country', ondelete='restrict', default=lambda self: self.env.company.country_id.id)
    same_vat_partner_id = fields.Many2one('res.partner', string='Partner with same Tax ID', compute='_compute_no_same_vat_partner_id', store=False)
    type_thirdparty = fields.Many2many('lavish.type_thirdparty',string='Tipo de tercero', tracking=True, ondelete='restrict', domain="['|',('is_company','=',is_company),('is_individual','!=',is_company)]") 
    document_type = fields.Selection(string=u'Tipo de Documento',
        selection=[
            ('11', u'11 - Registro civil de nacimiento'),
            ('12', u'12 - Tarjeta de identidad'),
            ('13', u'13 - Cédula de ciudadanía'),
            ('21', u'21 - Tarjeta de extranjería'),
            ('22', u'22 - Cédula de extranjería'),
            ('31', u'31 - NIT/RUT'),
            ('41', u'41 - Pasaporte'),
            ('42', u'42 - Documento de identificación extranjero'),
            ('47', u'47 - PEP'),
            ('50', u'50 - NIT de otro pais'),
            ('91', u'91 - NUIP'),
        ],
        help = u'Identificacion del Cliente, segun los tipos definidos por la DIAN.', tracking=True)
    business_name = fields.Char(string='Nombre de negocio', tracking=True)
    firs_name = fields.Char(string='Primer nombre', tracking=True)
    second_name = fields.Char(string='Segundo nombre', tracking=True)
    first_lastname = fields.Char(string='Primer apellido', tracking=True)
    second_lastname = fields.Char(string='Segundo apellido', tracking=True)
    is_ica = fields.Boolean(string='Aplicar ICA', tracking=True)
    #UBICACIÓN PRINCIPAL
    work_groups = fields.Many2many('lavish.work_groups', string='Grupos de trabajo', tracking=True, ondelete='restrict')
    sector_id = fields.Many2one('lavish.sectors', string='Sector', tracking=True, ondelete='restrict')
    ciiu_activity = fields.Many2one('lavish.ciiu', string='Códigos CIIU', tracking=True, ondelete='restrict')
    #GRUPO EMPRESARIAL
    is_business_group = fields.Boolean(string='¿Es un Grupo Empresarial?', tracking=True)
    name_business_group = fields.Char(string='Nombre Grupo Empresarial', tracking=True)

    acceptance_data_policy = fields.Boolean(string='Acepta política de tratamiento de datos', tracking=True)
    acceptance_date = fields.Date(string='Fecha de aceptación', tracking=True)
    not_contacted_again = fields.Boolean(string='No volver a ser contactado', tracking=True)
    date_decoupling = fields.Date(string="Fecha de desvinculación", tracking=True)
    reason_desvinculation_text = fields.Text(string='Motivo desvinculación') 
    
    #INFORMACION FINANCIERA
    company_size = fields.Selection([   ('1', 'Mipyme'),
                                        ('2', 'Pyme'),
                                        ('3', 'Mediana'),
                                        ('4', 'Grande')
                                    ], string='Tamaño empresa', tracking=True)

    #INFORMACION TRIBUTARIA
    tax_responsibilities = fields.Many2many('lavish.responsibilities_rut', string='Responsabilidades Tributarias', tracking=True, ondelete='restrict')

    #INFORMACION COMERCIAL
    account_origin = fields.Selection([
                                        ('1', 'Campañas'),
                                        ('2', 'Eventos'),
                                        ('3', 'Referenciado'),
                                        ('4', 'Telemercadeo'),
                                        ('5', 'Web'),
                                        ('6', 'Otro')
                                    ], string='Origen de la cuenta', tracking=True)
    

    #INFORMACIÓN CONTACTO
    contact_type = fields.Many2many('lavish.contact_types', string='Tipo de contacto', tracking=True, ondelete='restrict')
    contact_job_title = fields.Many2one('lavish.job_title', string='Cargo', tracking=True, ondelete='restrict')
    contact_area = fields.Many2one('lavish.areas', string='Área', tracking=True, ondelete='restrict')
    
    #INFORMACION FACTURACION ELECTRÓNICA
    email_invoice_electronic = fields.Char(string='Correo electrónico para recepción electrónica de facturas', tracking=True)


    @api.depends('vat')
    def _compute_no_same_vat_partner_id(self):
        for partner in self:
            partner.same_vat_partner_id = ""
    
    @api.onchange("l10n_latam_identification_type_id")
    def onchange_document_type(self):
        if self.l10n_latam_identification_type_id.l10n_co_document_code == 'rut':
            self.document_type = '31'
        elif self.l10n_latam_identification_type_id.l10n_co_document_code == 'id_document':
            self.document_type = '13'
        elif self.l10n_latam_identification_type_id.l10n_co_document_code == 'id_card':
            self.document_type = '12'
        elif self.l10n_latam_identification_type_id.l10n_co_document_code == 'passport':
            self.document_type = '41'
        elif self.l10n_latam_identification_type_id.l10n_co_document_code == 'foreign_id_card':
            self.document_type = '22'
        elif self.l10n_latam_identification_type_id.l10n_co_document_code == 'external_id':
            self.document_type = '42'
        elif self.l10n_latam_identification_type_id.l10n_co_document_code == 'diplomatic_card':
            self.document_type = '42'
        elif self.l10n_latam_identification_type_id.l10n_co_document_code == 'residence_document':
            self.document_type = '42'
        elif self.l10n_latam_identification_type_id.l10n_co_document_code == 'civil_registration':
            self.document_type = '11'
        elif self.l10n_latam_identification_type_id.l10n_co_document_code == 'national_citizen_id':
            self.document_type = '13'

    def _address_fields(self):
        result = super(ResPartner, self)._address_fields()
        result = result + ['city_id']
        return result


    def _compute_vat_ref(self):
        """
        Compute vat_ref field
        """
        for partner in self:
            if partner.document_type == '31' and partner.vat_co and partner.vat_co.isdigit() and len(partner.vat_co.strip()) > 0:
                partner.vat_ref = "%s-%s" % (partner.vat_co,partner.vat_vd)
            else:
                partner.vat_ref = partner.vat_co


    @api.onchange('vat_co','city_id','l10n_latam_identification_type_id')
    def _compute_concat_nit(self):
        """
        Concatenating and formatting the NIT number in order to have it
        consistent everywhere where it is needed
        @return: void
        """
        # Executing only for Document Type 31 (NIT)
        for partner in self:

            _logger.info('document')
            _logger.info(partner.l10n_latam_identification_type_id.name)
            if partner.l10n_latam_identification_type_id.name == 'NIT':
                # First check if entered value is valid
                _logger.info('if')
                # self._check_ident()
                #self._check_ident_num()

                # Instead of showing "False" we put en empty string
                if partner.vat_co == False:
                    partner.vat_co = ''
                else:
                    _logger.info('else')
                    partner.vat_vd = ''

                    # Formatting the NIT: xx.xxx.xxx-x
                    s = str(partner.vat_co)[::-1]
                    newnit = '.'.join(s[i:i + 3] for i in range(0, len(s), 3))
                    newnit = newnit[::-1]

                    nitList = [
                        newnit,
                        # Calling the NIT Function
                        # which creates the Verification Code:
                        self._check_dv(str(partner.vat_co).replace('-', '',).replace('.', '',))
                    ]

                    formatedNitList = []

                    for item in nitList:
                        if item != '':
                            formatedNitList.append(item)
                            partner.vat_vd = '-'.join(formatedNitList)

                    # Saving Verification digit in a proper field
                    for pnitem in self:
                        _logger.info(nitList[1])
                        _logger.info('nitlist')
                        pnitem.vat_vd = nitList[1]
                    

    def _check_dv(self, nit):
        """
        Function to calculate the check digit (DV) of the NIT. So there is no
        need to type it manually.
        @param nit: Enter the NIT number without check digit
        @return: String
        """
        for item in self:
            if item.l10n_latam_identification_type_id.name != 'NIT':
                return str(nit)

            nitString = '0'*(15-len(nit)) + nit
            vl = list(nitString)
            result = (
                int(vl[0])*71 + int(vl[1])*67 + int(vl[2])*59 + int(vl[3])*53 +
                int(vl[4])*47 + int(vl[5])*43 + int(vl[6])*41 + int(vl[7])*37 +
                int(vl[8])*29 + int(vl[9])*23 + int(vl[10])*19 + int(vl[11])*17 +
                int(vl[12])*13 + int(vl[13])*7 + int(vl[14])*3
            ) % 11

            if result in (0, 1):
                return str(result)
            else:
                return str(11-result)
            
    @api.depends('vat_co')
    def _compute_verification_digit(self):
        #Logica para calcular digito de verificación
        multiplication_factors = [71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3]

        for partner in self:
            if partner.vat_co and partner.l10n_latam_identification_type_id.name != 'NIT' and len(partner.vat_co) <= len(multiplication_factors):
                number = 0
                padded_vat = partner.vat_co

                while len(padded_vat) < len(multiplication_factors):
                    padded_vat = '0' + padded_vat

                # if there is a single non-integer in vat the verification code should be False
                try:
                    for index, vat_number in enumerate(padded_vat):
                        number += int(vat_number) * multiplication_factors[index]

                    number %= 11

                    if number < 2:
                        partner.dv = number
                    else:
                        partner.dv = 11 - number
                except ValueError:
                    partner.dv = False
            else:
                partner.dv = False
    @api.onchange('vat_co','city_id','l10n_latam_identification_type_id')
    def _compute_nit(self):
       for partner in self:
            if partner.document_type == '31':
                partner.vat = "%s-%s" % (partner.vat_co,partner.vat_vd)
            else:
                partner.vat = partner.vat_co      
    @api.constrains("vat", "l10n_latam_identification_type_id")
    def check_vat(self):
        # check_vat is implemented by base_vat which this localization
        # doesn't directly depend on. It is however automatically
        # installed for Colombia.
        with_vat = self.filtered(
            lambda x: x.l10n_latam_identification_type_id.is_vat
            and x.country_id.code != "CO"
        )
        return super(ResPartner, with_vat).check_vat()

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if self._context.get('search_by_vat', False):
            if name:
                args = args if args else []
                args.extend(['|', ['name', 'ilike', name], ['vat', 'ilike', name]])
                name = ''
        return super(ResPartner, self).name_search(name=name, args=args, operator=operator, limit=limit)

    def _display_address(self, without_company=False):
        """
        The purpose of this function is to build and return an address formatted accordingly to the
        standards of the country where it belongs.
        :param address: browse record of the res.partner to format
        :returns: the address formatted in a display that fit its country habits (or the default ones
            if not country is specified)
        :rtype: string
        """
        # get the information that will be injected into the display format
        # get the address format
        address_format = self._get_address_format()
        args = {
            "state_code": self.state_id.code or "",
            "state_name": self.state_id.name or "",
            "country_code": self.country_id.code or "",
            "country_name": self._get_country_name(),
            "company_name": self.commercial_company_name or "",
        }
        for field in self._formatting_address_fields():
            args[field] = getattr(self, field) or ""
        if without_company:
            args["company_name"] = ""
        elif self.commercial_company_name:
            address_format = "%(company_name)s\n" + address_format

        args["city"] = args["city"].capitalize() + ","
        return address_format % args


    @api.onchange('type_thirdparty')
    def _onchange_type_thirdparty(self):
        for record in self:
            if record.type_thirdparty:
                for i in record.type_thirdparty:
                    if i.id == 2 and record.company_type == 'company':
                        raise UserError(_('Una compañia no puede estar catalogada como contacto, por favor verificar.')) 


    @api.onchange('firs_name', 'second_name', 'first_lastname', 'second_lastname')
    def _onchange_person_names(self):
        if self.company_type == 'person':
            names = [name for name in [self.firs_name, self.second_name, self.first_lastname, self.second_lastname] if name]
            self.name = u' '.join(names)

    @api.depends('company_type', 'name', 'firs_name', 'second_name', 'first_lastname', 'second_lastname')
    def copy(self, default=None):
        default = default or {}
        if self.company_type == 'person':
            default.update({
                'firs_name': self.firs_name and self.firs_name + _('(copy)') or '',
                'second_name': self.second_name and self.second_name + _('(copy)') or '',
                'first_lastname': self.first_lastname and self.first_lastname + _('(copy)') or '',
                'second_lastname': self.second_lastname and self.second_lastname + _('(copy)') or '',
            })
        return super(ResPartner, self).copy(default=default)


    @api.constrains('bank_ids')
    def _check_bank_ids(self):
        for record in self:
            if len(record.bank_ids) > 0:
                count_main = 0
                for bank in record.bank_ids:
                    count_main += 1 if bank.is_main else 0
                if count_main > 1:
                    raise ValidationError(_('No puede tener más de una cuenta principal, por favor verificar.'))
    @api.onchange('name')
    def _onchange_info_name_upper(self):
        for record in self:            
            record.name = record.name.upper() if record.name else False
    
    @api.model
    def ___fields_view_get_address(self, arch):
        arch = super(ResPartner, self)._fields_view_get_address(arch)
        # render the partner address accordingly to address_view_id
        doc = etree.fromstring(arch)
        def _arch_location(node):
            in_subview = False
            view_type = False
            parent = node.getparent()
            while parent is not None and (not view_type or not in_subview):
                if parent.tag == "field":
                    in_subview = True
                elif parent.tag in ["form"]:
                    view_type = parent.tag
                parent = parent.getparent()
            return {
                "view_type": view_type,
                "in_subview": in_subview,
            }

        for city_node in doc.xpath("//field[@name='city']"):
            location = _arch_location(city_node)
            if location["view_type"] == "form" or not location["in_subview"]:
                parent = city_node.getparent()
                parent.remove(city_node)

        arch = etree.tostring(doc, encoding="unicode")
        return arch


class ResCountry(models.Model):
    _inherit = 'res.country'


    def name_get(self):
        rec = []
        for recs in self:
            name = '%s [%s]' % (recs.name or '', recs.code or '')
            rec += [ (recs.id, name) ]
        return rec

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """
        Se hereda metodo name search y se sobreescribe para hacer la busqueda 
        por el codigo del pais
        """
        if not args:
            args = []
        args = args[:]
        ids = []
        if name:
            ids = self.search([('code_dian', '=like', name + "%")] + args, limit=limit)
            if not ids:
                ids = self.search([('code', operator, name)] + args,limit=limit)
                if not ids:
                    ids = self.search([('name', operator, name)] + args,limit=limit)
        else:
            ids = self.search(args, limit=100)

        if ids:
            return ids.name_get()
        return self.name_get()

class ResCountryState(models.Model):
    _inherit = 'res.country.state'


    def name_get(self):
        rec = []
        for recs in self:
            name = '%s [%s]' % (recs.name or '', recs.code or '')
            rec += [ (recs.id, name) ]
        return rec

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """
        Se hereda metodo name search y se sobreescribe para hacer la busqueda 
        por el codigo del estado/departamento
        """
        if not args:
            args = []
        args = args[:]
        ids = []
        if name:
            ids = self.search([('code', '=like', name + "%")] + args, limit=limit)
            if not ids:
                ids = self.search([('name', operator, name)] + args,limit=limit)
        else:
            ids = self.search(args, limit=100)

        if ids:
            return ids.name_get()
        return self.name_get()

class ResCity(models.Model):
    _inherit = 'res.city'

    name = fields.Char(translate=False)
    code_dian = fields.Char(string="Code")
    postal_code = fields.Char(string=u'Postal code',)

    def name_get(self):
        rec = []
        for recs in self:
            name = '%s / %s [%s]' % (recs.name or '', recs.state_id.name or '', recs.code or '')
            rec += [ (recs.id, name) ]
        return rec

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """
        Se hereda metodo name search y se sobreescribe para hacer la busqueda 
        por el codigo de la ciudad
        """
        if not args:
            args = []
        args = args[:]
        ids = []
        if name:
            ids = self.search([('code', '=like', name + "%")] + args, limit=limit)
            if not ids:
                ids = self.search([('name', operator, name)] + args,limit=limit)
        else:
            ids = self.search(args, limit=100)

        if ids:
            return ids.name_get()
        return self.name_get()

class ResBank(models.Model):
    _inherit = 'res.bank'

    city_id = fields.Many2one('res.city', string="City of Address")
    bank_code = fields.Char(string='Bank Code')            

class ResCompany(models.Model):
    _inherit = 'res.company'

    def _get_default_partner(self):
        res_partner = self.env['res.partner'].sudo()
        partner_id = res_partner.browse(1)
        return partner_id.id

    city_id = fields.Many2one('res.city', compute="_compute_address", inverse="_inverse_city_id", string="City of Address")
    vat_vd = fields.Integer(compute="_compute_address", inverse="_inverse_vat_vd", string="Verification digit")
    default_partner_id = fields.Many2one('res.partner', string="Default partner", required=True, default=_get_default_partner)

    default_taxes_ids = fields.Many2many(
        string="Customer taxes",
        comodel_name="account.tax",
        relation="company_default_taxes_rel",
        column1="product_id",
        column2="tax_id",
        domain="[('type_tax_use','=','sale')]",
        help="Taxes applied for sale.",
    )
    default_supplier_taxes_ids = fields.Many2many(
        string="Supplier taxes",
        comodel_name="account.tax",
        relation="company_default_supplier_taxes_rel",
        column1="product_id",
        column2="tax_id",
        domain="[('type_tax_use','=','purchase')]",
        help="Taxes applied for purchase.",
    )

    def _get_company_address_fields(self, partner):
        result = super(ResCompany, self)._get_company_address_fields(partner)
        result['city_id'] = partner.city_id.id
        result['vat_vd'] = partner.vat_vd
        return result

    def _inverse_vat_vd(self):
        for company in self:
            company.partner_id.vat_vd = company.vat_vd
            company.default_partner_id.vat_vd = company.vat_vd


    def _inverse_city_id(self):
        for company in self:
            company.partner_id.city_id = company.city_id
            company.default_partner_id.city_id = company.city_id

    def _inverse_street(self):
        result = super(ResCompany, self)._inverse_street()
        for company in self:
            company.default_partner_id.street = company.street

    def _inverse_country(self):
        result = super(ResCompany, self)._inverse_country()
        for company in self:
            company.default_partner_id.country_id = company.country_id    