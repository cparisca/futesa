from odoo import tools
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
from pytz import timezone

import base64
import io
import xlsxwriter


class hr_auditing_reports(models.TransientModel):
    _name = "hr.auditing.reports"
    _description = "Reporte auditoria"

    year = fields.Integer('Año', required=True)
    month = fields.Selection([('1', 'Enero'),
                            ('2', 'Febrero'),
                            ('3', 'Marzo'),
                            ('4', 'Abril'),
                            ('5', 'Mayo'),
                            ('6', 'Junio'),
                            ('7', 'Julio'),
                            ('8', 'Agosto'),
                            ('9', 'Septiembre'),
                            ('10', 'Octubre'),
                            ('11', 'Noviembre'),
                            ('12', 'Diciembre')
                            ], string='Mes', required=True)
    type_process = fields.Selection([('1', 'No incluidos en liquidaciones'),
                            ('2', 'No incluidos en seguridad social'),
                            #('3', 'No incluidos en Nómina Electrónica'),
                            ], string='Tipo', required=True, default='1')

    excel_file = fields.Binary('Excel')
    excel_file_name = fields.Char('Excel filename')

    def generate_excel_auditing(self):

        # Periodo
        date_from = f'{str(self.year)}-{str(self.month)}-01'
        date_initial = datetime.strptime(date_from, '%Y-%m-%d').date()
        date_from = str(date_initial)
        final_year = self.year if self.month != '12' else self.year + 1
        final_month = int(self.month) + 1 if self.month != '12' else 1
        date_to = f'{str(final_year)}-{str(final_month)}-01'
        date_end = (datetime.strptime(date_to, '%Y-%m-%d') - timedelta(days=1)).date()
        date_to = str(date_end)

        # ----------------------------------Ejecutar consulta
        if self.type_process == '1': #No incluidos en liquidaciones del mes
            query_report = f'''
             Select a.identification_id, a."name" as name_employee,b.date_start ,b."name" as name_contract,b.state,coalesce(b.retirement_date,'1900-01-01') as retirement_date
                from hr_employee as a
                inner join hr_contract as b on a.id = b.employee_id and b.date_start <= '{date_to}' and (b.state = 'open' or ('{date_to}' <= b.retirement_date))
                left join hr_payslip as c on a.id = c.employee_id and c.date_from between '{date_from}' and '{date_to}'
                where a.company_id = {self.env.company.id} and c.id is null
            '''
        if self.type_process == '2': #No incluidos en seguridad social del mes
            query_report = f'''
            Select a.identification_id, a."name" as name_employee,b.date_start ,b."name" as name_contract,b.state,coalesce(b.retirement_date,'1900-01-01') as retirement_date
                from hr_employee as a
                inner join hr_contract as b on a.id = b.employee_id and b.date_start <= '{date_to}' and (b.state = 'open' or ('{date_to}' <= b.retirement_date))
                left join (select distinct employee_id from hr_payroll_social_security as c
                            inner join hr_executing_social_security as d on c.id = d.executing_social_security_id
                            where c."year" = {self.year} and c."month" = '{self.month}' ) as p on a.id = p.employee_id
                where a.company_id = {self.env.company.id} and p.employee_id is null
            '''
        if self.type_process == '3': #No incluidos en Nómina Electrónica
            query_report = f'''
            Select a.identification_id, a."name" as name_employee,b.date_start ,b."name" as name_contract,b.state,coalesce(b.retirement_date,'1900-01-01') as retirement_date
                from hr_employee as a
                inner join hr_contract as b on a.id = b.employee_id and b.date_start <= '{date_to}' and (b.state = 'open' or ('{date_to}' <= b.retirement_date))
                left join (select distinct employee_id from hr_electronic_payroll as c
                			inner join hr_electronic_payroll_detail as d on c.id = d.electronic_payroll_id
                			where c."year" = {self.year} and c."month" = '{self.month}' ) as p on a.id = p.employee_id
                where a.company_id = {self.env.company.id} and p.employee_id is null
            '''

        self._cr.execute(query_report)
        result_query = self._cr.dictfetchall()

        # Generar EXCEL
        filename = 'Reporte Auditoria'
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})

        # Columnas
        columns = ['Identificación', 'Nombres', 'Fecha Ingreso', 'Contrato', 'Estado', 'Fecha de Retiro']
        sheet = book.add_worksheet('Auditoria')

        # Agregar textos al excel
        text_title = 'Informe de auditoria'
        dict_type = {'1':'No incluidos en liquidaciones',
                    '2':'No incluidos en seguridad social',
                    '3':'No incluidos en Nómina Electrónica'}
        text_type = dict_type.get(self.type_process)
        text_dates = f'Periodo: {str(self.year)}-{str(self.month)}'
        text_report = 'Informe generado el %s' % (datetime.now(timezone(self.env.user.tz)))
        cell_format_title = book.add_format({'bold': True, 'align': 'left'})
        cell_format_title.set_font_name('Calibri')
        cell_format_title.set_font_size(15)
        cell_format_title.set_bottom(5)
        cell_format_title.set_bottom_color('#1F497D')
        cell_format_title.set_font_color('#1F497D')
        sheet.merge_range('A1:F1', text_title, cell_format_title)
        sheet.merge_range('A2:F2', text_type, cell_format_title)
        sheet.merge_range('A3:F3', text_dates, cell_format_title)
        cell_format_title = book.add_format({'bold': True, 'align': 'left'})
        cell_format_title.set_font_name('Calibri')
        cell_format_title.set_font_size(10)
        cell_format_title.set_bottom(5)
        cell_format_title.set_bottom_color('#1F497D')
        cell_format_title.set_font_color('#1F497D')
        sheet.merge_range('A4:F4', text_report, cell_format_title)
        # Formato para fechas
        date_format = book.add_format({'num_format': 'dd/mm/yyyy'})

        # Agregar columnas
        aument_columns = 0
        for column in columns:
            sheet.write(4, aument_columns, column)
            aument_columns = aument_columns + 1

        # Agregar query
        aument_columns = 0
        aument_rows = 5
        if len(result_query) != 0:
            for query in result_query:
                for row in query.values():
                    width = len(str(row)) + 10
                    if str(type(row)).find('date') > -1:
                        sheet.write_datetime(aument_rows, aument_columns, row, date_format)
                    else:
                        sheet.write(aument_rows, aument_columns, row)
                    # Ajustar tamaño columna
                    sheet.set_column(aument_columns, aument_columns, width)
                    aument_columns = aument_columns + 1
                aument_rows = aument_rows + 1
                aument_columns = 0

            # Convertir en tabla
            array_header_table = []
            for i in columns:
                dict = {'header': i}
                array_header_table.append(dict)

            sheet.add_table(4, 0, aument_rows-1, len(columns)-1, {'style': 'Table Style Medium 2', 'columns': array_header_table})
        # Guadar Excel
        book.close()

        self.write({
            'excel_file': base64.b64encode(stream.getvalue()).decode('utf-8'),
            'excel_file_name': filename,
        })

        action = {
            'name': 'Reporte Auditoria',
            'type': 'ir.actions.act_url',
            'url': "web/content/?model=hr.auditing.reports&id=" + str(
                self.id) + "&filename_field=excel_file_name&field=excel_file&download=true&filename=" + self.excel_file_name,
            'target': 'self',
        }
        return action
