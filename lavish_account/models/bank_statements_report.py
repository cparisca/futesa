from odoo import tools
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
from pytz import timezone
from xlrd import open_workbook

import base64
import io
import xlsxwriter


class lavish_bank_statements_report(models.TransientModel):
    _name = 'lavish.bank.statements.report'
    _description = 'Reporte extractos bancarios'

    reference = fields.Char(string='Referencia', required=True)
    date = fields.Date(string='Fecha', required=True)
    journal_id = fields.Many2one('account.journal', string='Diario', required=True)
    excel_origin = fields.Binary(string='Excel Original', required=True)
    excel_origin_filename = fields.Char(string='Excel Original Nombre')

    def generate_excel(self):
        if self.excel_origin:
            columns = ['Fecha', 'Numero', 'Valor', 'Descripción']
            wb = open_workbook(file_contents=base64.decodestring(self.excel_origin))
            dict_value_update_detail = {}
            values_update_detail = []
            # Se guarda el contenido del excel en una lista de diccionarios
            try:
                for s in wb.sheets():
                    for row in range(s.nrows):
                        dict_value_update_detail = {}
                        for col in range(s.ncols):
                            dict_value_update_detail[columns[col]] = (s.cell(row, col).value)
                        values_update_detail.append(dict_value_update_detail)
            except Exception as e:
                raise ValidationError(_('Archivo cargado invalido, por favor verificar.'))
            values_finally = []
            for record in values_update_detail:
                num = str(record['Numero']).split('.')[0]
                obj_partner = self.env['res.partner'].search([('vat', '=', num)], limit=1)

                dict_vals = {
                    'reference':self.reference,
                    'date': self.date,
                    'journal': self.journal_id.name,
                    'ext_date': record['Fecha'],
                    'ext_tag': record['Descripción']+' '+num,
                    'ext_asociate': obj_partner.name if len(obj_partner) > 0 else '',
                    'ext_import': record['Valor'],
                }
                values_finally.append(dict_vals)

            filename = 'CONVERTIDO '+self.excel_origin_filename
            stream = io.BytesIO()
            book = xlsxwriter.Workbook(stream, {'in_memory': True})
            sheet = book.add_worksheet('Extracto bancario')
            date_format = book.add_format({'num_format': 'dd/mm/yyyy'})
            columns = ['Referencia', 'Fecha', 'Diario', 'Líneas de extracto/Fecha', 'Líneas de extracto/Etiqueta', 'Líneas de extracto/Asociado', 'Líneas de extracto/Importe', 'Líneas de extracto/Validación de inactividad']

            # Agregar columnas
            aument_columns = 0
            for column in columns:
                sheet.write(0, aument_columns, column)
                sheet.set_column(aument_columns, aument_columns, len(str(column)) + 10)
                aument_columns = aument_columns + 1

            # Agregar valores
            aument_rows = 1
            for item in values_finally:
                if aument_rows == 1:
                    sheet.write(aument_rows, 0, item['reference'])
                    sheet.write(aument_rows, 1, item['date'], date_format)
                    sheet.write(aument_rows, 2, item['journal'])
                sheet.write(aument_rows, 3, item['ext_date'], date_format)
                sheet.write(aument_rows, 4, item['ext_tag'])
                sheet.write(aument_rows, 5, item['ext_asociate'])
                sheet.write(aument_rows, 6, item['ext_import'])
                sheet.write(aument_rows, 7, 'False')

                aument_rows = aument_rows + 1

            # Convertir en tabla
            array_header_table = []
            for i in columns:
                dict = {'header': i}
                array_header_table.append(dict)

            sheet.add_table(0, 0, aument_rows - 1, len(columns) - 1,
                            {'style': 'Table Style Medium 7', 'columns': array_header_table})

            book.close()

            self.write({
                'excel_origin': base64.encodestring(stream.getvalue()),
                'excel_origin_filename': filename,
            })

            action = {
                'name': 'Extracto bancario',
                'type': 'ir.actions.act_url',
                'url': "web/content/?model=lavish.bank.statements.report&id=" + str(
                    self.id) + "&filename_field=excel_origin_filename&field=excel_origin&download=true&filename=" + self.excel_origin_filename,
                'target': 'self',
            }
            return action