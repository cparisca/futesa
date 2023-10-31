from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError, UserError
from odoo import models, fields, api, _

import base64
import io
import xlsxwriter
import math

#Código fiscal
class fiscal_accounting_code_details(models.Model):
    _name = 'fiscal.accounting.code.details'
    _description = 'Código Fiscal - Cuentas'

    fiscal_accounting_id = fields.Many2one('fiscal.accounting.code',string='Código fiscal', required=True)
    account_id = fields.Many2one('account.account',string='Cuenta', required=True)
    move_type = fields.Selection([('debit', 'Débito'),
                                     ('credit', 'Crédito'),
                                     ('net', 'Neto')], string='Tipo de movimiento', required=True)

    _sql_constraints = [('fiscal_account_id_uniq', 'unique(fiscal_accounting_id,account_id)',
                         'Ya existe la cuenta en este código fiscal, por favor verficar.')]

class fiscal_accounting_code(models.Model):
    _name = 'fiscal.accounting.code'
    _description = 'Código Fiscal'
    _rec_name = 'code_description'

    company_id = fields.Many2one('res.company', string='Compañía', readonly=True, required=True,
                                 default=lambda self: self.env.company)
    concept_dian = fields.Char(string="Código Fiscal", required=True)
    code_description = fields.Char(string="Descripción del Código", required=True)
    format_id = fields.Many2one('format.encab', string='Formato')
    #concept = fields.Char(string="Concepto")
    account_type = fields.Selection([('movement', 'Movimiento'),
                              ('balance', 'Balance'),
                              ], 'Tipo de cuenta')
    move_type = fields.Selection([('debit', 'Débito'),
                                  ('credit', 'Crédito'),
                                  ('net', 'Neto')], string='Tipo de movimiento', default='net',required=True)
    retention_associated = fields.Many2one('fiscal.accounting.code', string='Retención Asociada')
    required_retention_associated = fields.Boolean('Aplica para todos los conceptos del formato asociado')
    accounting_details_ids = fields.Many2many('account.account',string='Cuentas')
    #concept = fields.Char(string="Concepto")
    #account_code = fields.Char(string="Código de cuenta")
    #excluded_documents_ids = fields.Many2many('account.journal', string="Documentos Excluidos")
    #fiscal_group_id = fields.Many2one('fiscal.accounting.group',string="Grupo Fiscal")

    _sql_constraints = [('fiscal_code_uniq', 'unique(company_id,concept_dian)',
                         'El concepto DIAN digitado ya esta registrado para esta compañía, por favor verificar.')]

#Grupo Fiscal
class fiscal_accounting_group(models.Model):
    _name = 'fiscal.accounting.group'
    _description = 'Grupo Fiscal'
    _rec_name = 'group_description'

    company_id = fields.Many2one('res.company', string='Compañía', readonly=True, required=True,
                                 default=lambda self: self.env.company)
    fiscal_group = fields.Char(string="Grupo Fiscal", required=True)
    group_description = fields.Char(string="Descripción del Grupo", required=True)
    operator = fields.Selection([('>', 'Mayor que'),
                              ('<', 'Menor que'),
                              ('==', 'Igual que'),
                              ('!=', 'Distinto de'),
                              ('<=','Menor o igual que'),
                              ('>=', 'Mayor o igual que'),
                              ], 'Operador')
    amount = fields.Float(string="Monto")
    tax_type = fields.Selection([('dian', "DIAN Art 631"),
                              ('treasury', "Tesoreria Distrital"),
                              ], "Tipo de impuesto")
    concept_dian_ids = fields.Many2many('fiscal.accounting.code', string="Códigos Fiscales")
    excluded_thirdparty_ids = fields.Many2many('res.partner', string="Tercero Excluido")
    partner_minor_amounts = fields.Many2one('res.partner', string="Tercero Cuantías menores")

    _sql_constraints = [('fiscal_group_uniq', 'unique(company_id,fiscal_group)',
                         'El grupo fiscal digitado ya esta registrado para esta compañía, por favor verificar.')]


class format_encab(models.Model):
    _name = 'format.encab'
    _description = 'Formato de Código Fiscal Encabezado'

    format_id = fields.Char(string="Código Formato", required=True)
    description = fields.Char(string="Descripción del formato", required=True)
    details_ids = fields.One2many('format.detail','format_id',string = 'Campos Disponibles')
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True, required=True,default=lambda self: self.env.company)
    format_associated_id = fields.Many2one('format.encab', string='Formato Asociado')
    fields_associated_code_fiscal_ids = fields.Many2many('fiscal.accounting.code', string='Conceptos Asociados')

    _sql_constraints = [('format_encab_uniq', 'unique(format_id,company_id)',
                         'El formato fiscal digitado ya esta registrado para esta compañía, por favor verificar.')]

    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "{}/{}".format(record.format_id,record.description)))
        return result

    @api.onchange('format_associated_id')
    def get_code_fiscal(self):
        for record in self:
            record.fields_associated_code_fiscal_ids = self.env['fiscal.accounting.code'].search(
                [('format_id', '=', self.format_associated_id.id), ('format_id', '!=', False)]).ids

class format_detail(models.Model):
    _name = 'format.detail'
    _description = 'Formato de Código Fiscal Detalle'

    format_id = fields.Many2one('format.encab',string='Código Formato', required=True, ondelete='cascade')
    sequence = fields.Integer(string="Secuencia", required=True)
    available_fields = fields.Selection([('fiscal_accounting_id', 'Concepto Fiscal'),
                              ('concept_dian',  'Concepto DIAN'),
                              ('format',  'Formato Archivo'),
                              ('x_document_type', 'Tipo Documento Tercero'),
                              ('vat', 'Número Documento Tercero'),
                              ('x_first_name', 'Primer Nombre'),
                              ('x_second_name', 'Segundo Nombre'),
                              ('x_first_lastname', 'Primer Apellido'),
                              ('x_second_lastname', 'Segundo Apellido'),
                              ('commercial_company_name', 'Razón Social'),
                              ('x_digit_verification', 'Dígito de Verificación'),
                              ('street', 'Dirección'),
                              ('state_id', 'Código Departamento'),
                              ('x_city', 'Código Ciudad'),
                              ('amount', 'Valor Pesos'),
                              ('operator', 'Operador'),
                              ('tax', 'Base Impuestos'),
                              ('x_code_dian', 'Código País DIAN'),
                              ('phone', 'Teléfono Tercero'),
                              ('unit_rate', 'Tarifa Aplicada'),
                              ('email', 'Email'),
                              ('higher_value_iva', 'Mayor Valor Iva'),
                              ], 'Campos Seleccionados', required=True)

class generate_media_magnetic(models.TransientModel):
    _name = 'generate.media.magnetic'
    _description = 'Generar Medios Magneticos'

    company_id = fields.Many2one('res.company',string='Compañia', readonly=True,required=True, default=lambda self: self.env.company)
    type_media_magnetic = fields.Selection([('dian', 'Generar Artículo 631'),
                                            ('distrital', 'Generar Impuesto Distrital')],'Tipo de medio magnético', default='dian')
    year =  fields.Integer(string="Año", required=True)

    excel_file = fields.Binary('Excel file')
    excel_file_name = fields.Char('Excel name')

    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "Generar Medios Magnético {}".format(record.type_media_magnetic.upper())))
        return result

    def generate_media_magnetic_dian(self):
        #Variables excel
        filename = f'MedioMagtenico_{str(self.year)}.xlsx'
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})
        #Variables proceso
        date_start = str(self.year) +'-01-01'
        date_end = str(self.year) +'-12-31'
        date_start = datetime.strptime(date_start, '%Y-%m-%d').date()
        date_end = datetime.strptime(date_end, '%Y-%m-%d').date()
        minor_amounts = 0
        account_moves_ids = []
        #Traer todos los formatos
        obj_formats = self.env['format.encab'].search([('id','!=',False)])

        for format in obj_formats:
            obj_account_fiscal = self.env['fiscal.accounting.code'].search([('format_id','=',format.id)])
            lst_Mvto = []
            lst_partner_minor = []
            for fiscal in obj_account_fiscal:
                obj_group_fiscal = self.env['fiscal.accounting.group'].search([('concept_dian_ids', 'in', fiscal.ids)],
                                                                              limit=1)
                format_fields = fiscal.format_id.details_ids

                if fiscal.account_type == 'balance':
                    partner_ids = self.env['account.move.line'].search(
                        [('date', '<=', date_end), ('parent_state', '=', 'posted'),
                         ('account_id', 'in', fiscal.accounting_details_ids.ids)]).partner_id.ids
                else:
                    partner_ids = self.env['account.move.line'].search(
                        [('date', '>=', date_start), ('date', '<=', date_end), ('parent_state', '=', 'posted'),
                         ('move_id.accounting_closing_id', '=', False),
                         ('account_id', 'in', fiscal.accounting_details_ids.ids)]).partner_id.ids
                obj_partner_ids = self.env['res.partner'].search([('id','in',partner_ids)])

                dict_partner_minor = {}
                dict_partner_minor_associated = {}

                for partner in obj_partner_ids:
                    try:
                        if fiscal.account_type == 'balance':
                            moves = self.env['account.move.line'].search(
                                [('date', '<', date_start), ('parent_state', '=', 'posted'),
                                 ('account_id', 'in', fiscal.accounting_details_ids.ids),
                                 ('partner_id', '=', partner.id)])
                            moves += self.env['account.move.line'].search(
                                [('date', '>=', date_start), ('date', '<=', date_end),('parent_state','=','posted'),
                                 ('move_id.accounting_closing_id', '=', False),
                                 ('account_id', 'in', fiscal.accounting_details_ids.ids), ('partner_id', '=', partner.id)])
                        else:
                            moves = self.env['account.move.line'].search(
                                [('date', '>=', date_start), ('date', '<=', date_end),('parent_state','=','posted'),
                                 ('move_id.accounting_closing_id','=',False),('account_id', 'in', fiscal.accounting_details_ids.ids),('partner_id', '=', partner.id)])
                        account_moves_ids = account_moves_ids + moves.ids
                        amount = 0
                        tax_base_amount = 0
                        for i in moves:
                            if fiscal.move_type == 'debit':
                                amount += i.debit
                            elif fiscal.move_type == 'credit':
                                amount += i.credit
                            else:
                                amount += i.balance
                            tax_base_amount += i.tax_base_amount

                        if len(obj_group_fiscal) > 0:
                            ldict = {'amount':amount,'validation_minor':False}
                            code_python = f'validation_minor = True if amount {obj_group_fiscal.operator} {obj_group_fiscal.amount}  else False'
                            exec(code_python,ldict)
                            validation_minor = ldict.get('validation_minor')
                        else:
                            validation_minor = False

                        if validation_minor == False:
                            #Armamos el dict con la información
                            dict_documents = dict(self.env['res.partner']._fields['x_document_type'].selection)
                            document_type = dict_documents.get(partner.x_document_type) if partner.x_document_type else ''
                            info = {'fiscal_accounting_id': fiscal.concept_dian,
                                    'concept_dian': fiscal.code_description,
                                    'format':fiscal.format_id.format_id,
                                    'x_document_type': partner.x_document_type,
                                    'vat': partner.vat,
                                    'x_first_name': partner.x_first_name or '',
                                    'x_second_name': partner.x_second_name if partner.x_second_name else '',
                                    'x_first_lastname': partner.x_first_lastname or '',
                                    'x_second_lastname': partner.x_second_lastname or '',
                                    'commercial_company_name': partner.name,
                                    'x_digit_verification': partner.x_digit_verification,
                                    'street': partner.street,
                                    'state_id': partner.x_city.code[:2],
                                    'x_city': partner.x_city.code,
                                    'amount': amount,
                                    'operator':obj_group_fiscal.operator,
                                    'tax': tax_base_amount,
                                    'x_code_dian': '169',#partner.country_id.code,
                                    'phone': partner.phone or partner.mobile,
                                    'unit_rate': 0,
                                    'email': partner.email,
                                    'higher_value_iva': 0,
                                }
                            #Formatos asociados
                            info_associated = {}
                            obj_account_fiscal_associated = self.env['fiscal.accounting.code'].search([('format_id', '=', format.format_associated_id.id)])
                            for fiscal_associated in obj_account_fiscal_associated:
                                if (fiscal_associated.required_retention_associated == False):
                                    obj_retention_associated = self.env['fiscal.accounting.code'].search([('id','in',fiscal_associated.ids),('retention_associated','=',fiscal.id)])
                                else:
                                    obj_retention_associated = self.env['fiscal.accounting.code'].search([('id', 'in', fiscal_associated.ids)])
                                moves_associated = self.env['account.move.line'].search(
                                    [('date', '>=', date_start), ('date', '<=', date_end),('parent_state','=','posted'),
                                    ('move_id.accounting_closing_id','=',False),('account_id', 'in', obj_retention_associated.accounting_details_ids.ids), ('partner_id', '=', partner.id)])
                                amount_associated = sum([i.balance for i in moves_associated])
                                name_associated = fiscal_associated.code_description.replace(' ','_')
                                info_associated[name_associated] = amount_associated
                            #Guardado final
                            media_magnetic = {}
                            for field in sorted(format_fields, key=lambda x: x.sequence):
                                if field.available_fields in info:
                                    media_magnetic[field.available_fields] = info.get(field.available_fields)
                            lst_Mvto.append({**media_magnetic, **info_associated})
                        else:
                            #Armamos el dict con la información
                            dict_partner_minor['fiscal_info'] = fiscal
                            dict_partner_minor['group_fiscal'] = obj_group_fiscal
                            dict_partner_minor['amount'] = dict_partner_minor.get('amount',0) + amount
                            dict_partner_minor['tax'] = dict_partner_minor.get('tax', 0) + tax_base_amount

                            #Formatos asociados
                            obj_account_fiscal_associated = self.env['fiscal.accounting.code'].search([('format_id', '=', format.format_associated_id.id)])
                            for fiscal_associated in obj_account_fiscal_associated:
                                if (fiscal_associated.required_retention_associated == False):
                                    obj_retention_associated = self.env['fiscal.accounting.code'].search([('id','in',fiscal_associated.ids),('retention_associated','=',fiscal.id)])
                                else:
                                    obj_retention_associated = self.env['fiscal.accounting.code'].search([('id', 'in', fiscal_associated.ids)])
                                moves_associated = self.env['account.move.line'].search(
                                    [('date', '>=', date_start), ('date', '<=', date_end),('parent_state','=','posted'),
                                    ('move_id.accounting_closing_id','=',False),('account_id', 'in', obj_retention_associated.accounting_details_ids.ids), ('partner_id', '=', partner.id)])
                                amount_associated = sum([i.balance for i in moves_associated])
                                name_associated = fiscal_associated.code_description.replace(' ','_')
                                dict_partner_minor_associated[name_associated] = dict_partner_minor_associated.get(name_associated, 0) + amount_associated
                    except Exception as e:
                        raise ValidationError(f'El tercero ID:{partner.id} NOMBRE:{partner.name} genero el siguente error: {e}')
                if len(dict_partner_minor) > 0:
                    dict_documents = dict(self.env['res.partner']._fields['x_document_type'].selection)
                    document_type = dict_documents.get(
                        dict_partner_minor.get('group_fiscal').partner_minor_amounts.x_document_type) if dict_partner_minor.get('group_fiscal').partner_minor_amounts.x_document_type else ''
                    info = {'fiscal_accounting_id': dict_partner_minor.get('fiscal_info').concept_dian,
                            'concept_dian': dict_partner_minor.get('fiscal_info').code_description,
                            'format': dict_partner_minor.get('fiscal_info').format_id.format_id,
                            'x_document_type':  dict_partner_minor.get('group_fiscal').partner_minor_amounts.x_document_type,
                            'vat': dict_partner_minor.get('group_fiscal').partner_minor_amounts.vat,
                            'x_first_name': dict_partner_minor.get('group_fiscal').partner_minor_amounts.x_first_name or '',
                            'x_second_name': dict_partner_minor.get('group_fiscal').partner_minor_amounts.x_second_name or '',
                            'x_first_lastname': dict_partner_minor.get('group_fiscal').partner_minor_amounts.x_first_lastname or '',
                            'x_second_lastname': dict_partner_minor.get('group_fiscal').partner_minor_amounts.x_second_lastname or '' ,
                            'commercial_company_name': dict_partner_minor.get('group_fiscal').partner_minor_amounts.name,
                            'x_digit_verification': dict_partner_minor.get('group_fiscal').partner_minor_amounts.x_digit_verification,
                            'street': dict_partner_minor.get('group_fiscal').partner_minor_amounts.street,
                            'state_id': dict_partner_minor.get('group_fiscal').partner_minor_amounts.x_city.code[:2],
                            'x_city': dict_partner_minor.get('group_fiscal').partner_minor_amounts.x_city.code,
                            'amount': dict_partner_minor.get('amount',0),
                            'operator': dict_partner_minor.get('group_fiscal').operator,
                            'tax': dict_partner_minor.get('tax',0),
                            'x_code_dian': '169', #dict_partner_minor.get('group_fiscal').partner_minor_amounts.country_id.code,
                            'phone': dict_partner_minor.get('group_fiscal').partner_minor_amounts.phone or dict_partner_minor.get('group_fiscal').partner_minor_amounts.mobile,
                            'unit_rate': 0,
                            'email': dict_partner_minor.get('group_fiscal').partner_minor_amounts.email,
                            'higher_value_iva': 0,
                            }
                    #Guardado final
                    media_magnetic = {}
                    for field in sorted(format_fields, key=lambda x: x.sequence):
                        if field.available_fields in info:
                            media_magnetic[field.available_fields] = info.get(field.available_fields)
                    lst_Mvto.append({**media_magnetic, **dict_partner_minor_associated})
                    lst_partner_minor.append({**dict_partner_minor, **dict_partner_minor_associated})
            #Generar hoja de excel
            sheet = book.add_worksheet(format.format_id)
            if len(lst_Mvto) == 0:
                continue
            columns = []
            for field in lst_Mvto[0].keys():
                field_name = dict(self.env['format.detail']._fields['available_fields'].selection).get(field,field.replace('_',' '))
                columns.append(field_name)
            # Agregar columnas
            aument_columns = 0
            for column in columns:
                sheet.write(0, aument_columns, column)
                aument_columns = aument_columns + 1
            # Agregar valores
            aument_columns = 0
            aument_rows = 1
            for info in lst_Mvto:
                for row in info.values():
                    width = len(str(row)) + 10
                    sheet.write(aument_rows, aument_columns, row)
                    # Ajustar tamaño columna
                    sheet.set_column(aument_columns, aument_columns, width)
                    aument_columns = aument_columns + 1
                aument_rows = aument_rows + 1
                aument_columns = 0

            # Convertir en tabla
            array_header_table = []
            for i in columns:
                dict_h = {'header': i}
                array_header_table.append(dict_h)
            sheet.add_table(0, 0, aument_rows-1, len(columns)-1, {'style': 'Table Style Medium 2', 'columns': array_header_table})

        # Generar hoja de excel resumen
        sheet_resumen = book.add_worksheet("Resumen")
        columns = ['Documento','Fecha','Referencia','Débito','Crédito','Balance','Número Documento','Nombre','Cuenta','Descripción Cuenta','Cuenta Analítíca']
        # Agregar columnas
        aument_columns = 0
        for column in columns:
            sheet_resumen.write(0, aument_columns, column)
            aument_columns = aument_columns + 1
        #Agrefar info
        date_format = book.add_format({'num_format': 'dd/mm/yyyy'})
        info_moves = self.env['account.move.line'].search([('id', 'in', account_moves_ids)])
        aument_rows_resumen = 1
        for move in info_moves:
            sheet_resumen.write(aument_rows_resumen, 0, move.move_name)
            sheet_resumen.set_column(0, 0, len(str(move.move_name))+13)
            sheet_resumen.write_datetime(aument_rows_resumen, 1, move.date, date_format)
            sheet_resumen.set_column(1, 1, len(str(move.date)) + 10)
            sheet_resumen.write(aument_rows_resumen, 2, move.ref)
            sheet_resumen.set_column(2, 2, len(str(move.ref)) + 10)
            sheet_resumen.write(aument_rows_resumen, 3, move.debit)
            sheet_resumen.set_column(3, 3, len(str(move.debit)) + 10)
            sheet_resumen.write(aument_rows_resumen, 4, move.credit)
            sheet_resumen.set_column(4, 4, len(str(move.credit)) + 15)
            sheet_resumen.write(aument_rows_resumen, 5, move.balance)
            sheet_resumen.set_column(5, 5, len(str(move.balance)) + 10)
            sheet_resumen.write(aument_rows_resumen, 6, move.partner_id.vat)
            sheet_resumen.set_column(6, 6, len(str(move.partner_id.vat)) + 13)
            sheet_resumen.write(aument_rows_resumen, 7, move.partner_id.name)
            sheet_resumen.set_column(7, 7, len(str(move.partner_id.name)) + 13)
            sheet_resumen.write(aument_rows_resumen, 8, move.account_id.code)
            sheet_resumen.set_column(8, 8, len(str(move.account_id.code)) + 13)
            sheet_resumen.write(aument_rows_resumen, 9, move.account_id.name)
            sheet_resumen.set_column(9, 9, len(str(move.account_id.name)) + 15)
            sheet_resumen.write(aument_rows_resumen, 10, move.analytic_account_id.name)
            sheet_resumen.set_column(10, 10, len(str(move.analytic_account_id.name)) + 15)
            aument_rows_resumen = aument_rows_resumen + 1

        # Convertir en tabla
        array_header_table_resumen = []
        for i in columns:
            dict_h = {'header': i}
            array_header_table_resumen.append(dict_h)
        sheet_resumen.add_table(0, 0, aument_rows_resumen - 1, len(columns) - 1,
                        {'style': 'Table Style Medium 2', 'columns': array_header_table_resumen})

        book.close()
        self.write({
            'excel_file': base64.encodestring(stream.getvalue()),
            'excel_file_name': filename,
        })

        action = {
            'name': 'Export Medio magnetico información exogena',
            'type': 'ir.actions.act_url',
            'url': "web/content/?model=generate.media.magnetic&id=" + str(
                self.id) + "&filename_field=excel_file_name&field=excel_file&download=true&filename=" + self.excel_file_name,
            'target': 'self',
        }
        return action

    def generate_media_magnetic_distrital(self):
        date_start = str(self.year) +'-01-01'
        date_end = str(self.year) +'-12-31'
        lst_Mvto = []

    def generate_media_magnetic(self):
        if self.type_media_magnetic == 'dian':
            return self.generate_media_magnetic_dian()
        if self.type_media_magnetic == 'distrital':
            return self.generate_media_magnetic_distrital()

