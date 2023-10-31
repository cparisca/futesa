from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

import base64
import io
import xlsxwriter


class Hr_payslip(models.Model):
    _inherit = 'hr.payslip'

    excel_value_base_file = fields.Binary('Excel Valores base file')
    excel_value_base_file_name = fields.Char('Excel Valores base filename')
    excel_lines = fields.Binary('Excel líneas de recibo de nómina')
    excel_lines_filename = fields.Char('Excel líneas de recibo de nómina filename')

    def get_query(self,process,date_start,date_end):
        # formatear fechas
        date_start = str(date_start.year) + '-' + str(date_start.month) + '-' + str(date_start.day)
        date_end = str(date_end.year) + '-' + str(date_end.month) + '-' + str(date_end.day)

        query = """Select * from (
                    Select hc.name,hp.date_from,COALESCE(sum(pl.total),0) as accumulated, 
                        case when hp.id = %s then 'Liquidación Actual' else 'Liquidaciones' end as origin  
                        From hr_payslip as hp 
                        Inner Join hr_payslip_line as pl on  hp.id = pl.slip_id 
                        Inner Join hr_salary_rule hc on pl.salary_rule_id = hc.id and hc.%s = true
                        Inner Join hr_salary_rule_category hsc on hc.category_id = hsc.id and hsc.code != 'BASIC'
                        WHERE (hp.state = 'done' and hp.contract_id = %s
                                AND (hp.date_from between '%s' and '%s'
                                    or
                                    hp.date_to between '%s' and '%s' )) or hp.id = %s
                        group by hc.name,hp.date_from,hp.id
                    Union 
                    Select hc.name,pl.date,COALESCE(sum(pl.amount),0) as accumulated, 'Acumulados' as origin
                        From hr_accumulated_payroll as pl
                        Inner Join hr_salary_rule hc on pl.salary_rule_id = hc.id and hc.%s = true
                        Inner Join hr_salary_rule_category hsc on hc.category_id = hsc.id and hsc.code != 'BASIC'
                        WHERE pl.employee_id = %s and pl.date between '%s' and '%s'
                        group by hc.name,pl.date) as a order by a.date_from,a.name
                """ % (
        self.id, process, self.contract_id.id, date_start, date_end, date_start, date_end, self.id,process, self.employee_id.id, date_start,
        date_end)

        return query

    def base_values_export_excel(self):
        query_vacaciones = ''
        query_vacaciones_dinero = ''
        query_prima = ''
        query_cesantias = ''

        if self.struct_id.process == 'vacaciones':
            date_start = self.date_from - relativedelta(years=1)
            date_start = self.contract_id.date_start if date_start <= self.contract_id.date_start else date_start
            date_end = self.date_from
            query_vacaciones = self.get_query('base_vacaciones',date_start,date_end)
            query_vacaciones_dinero = self.get_query('base_vacaciones_dinero', date_start, date_end)
        elif self.struct_id.process == 'prima':
            date_start = self.date_from
            date_start = self.contract_id.date_start if date_start <= self.contract_id.date_start else date_start
            date_end = self.date_to
            query_prima = self.get_query('base_prima', date_start, date_end)
        elif self.struct_id.process == 'cesantias' or self.struct_id.process == 'intereses_cesantias':
            date_start = self.date_from
            date_start = self.contract_id.date_start if date_start <= self.contract_id.date_start else date_start
            date_end = self.date_to
            query_cesantias = self.get_query('base_cesantias', date_start, date_end)
        elif self.struct_id.process == 'contrato' or self.struct_id.process == 'nomina':
            date_start = self.date_liquidacion - relativedelta(years=1) or self.date_from
            date_end = self.date_liquidacion or self.date_to
            query_vacaciones_dinero = self.get_query('base_vacaciones_dinero', date_start, date_end)
            date_start = self.date_prima or self.date_from
            date_end = self.date_liquidacion or self.date_to
            query_prima = self.get_query('base_prima', date_start, date_end)
            date_start = self.date_cesantias or self.date_from
            date_end = self.date_liquidacion or self.date_to
            query_cesantias = self.get_query('base_cesantias', date_start, date_end)
        else:
            raise ValidationError(_('Esta estructura salarial no posee exportación de valores base a excel.'))

        #Generar EXCEL
        filename = f'Acumulados valores variables - {self.employee_id.name}.xlsx'
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})
        date_format = book.add_format({'num_format': 'dd/mm/yyyy'})

        if query_vacaciones != '':
            columns = ['Regla Salarial', 'Fecha', 'Valor', 'Origen']
            sheet_vacaciones = book.add_worksheet('VACACIONES DISFRUTADAS')
            # Agregar columnas
            aument_columns = 0
            for column in columns:
                sheet_vacaciones.write(0, aument_columns, column)
                aument_columns = aument_columns + 1

            #Agregar Información generada en la consulta
            self._cr.execute(query_vacaciones)
            result_query = self._cr.dictfetchall()
            aument_columns = 0
            aument_rows = 1
            for query in result_query:
                for row in query.values():
                    width = len(str(row)) + 10
                    if str(type(row)).find('date') > -1:
                        sheet_vacaciones.write_datetime(aument_rows, aument_columns, row, date_format)
                    else:
                        sheet_vacaciones.write(aument_rows, aument_columns, row)
                    sheet_vacaciones.set_column(aument_columns, aument_columns, width)
                    aument_columns = aument_columns + 1
                aument_rows = aument_rows + 1
                aument_columns = 0
            # Convertir en tabla
            array_header_table = []
            aument_rows = 2 if aument_rows == 1 else aument_rows
            for i in columns:
                dict = {'header': i}
                array_header_table.append(dict)
            sheet_vacaciones.add_table(0, 0, aument_rows - 1, len(columns) - 1,
                                              {'style': 'Table Style Medium 2', 'columns': array_header_table})
        if query_vacaciones_dinero != '':
            columns = ['Regla Salarial', 'Fecha', 'Valor', 'Origen']
            sheet_vacaciones_dinero = book.add_worksheet('VACACIONES REMUNERADAS')
            # Agregar columnas
            aument_columns = 0
            for column in columns:
                sheet_vacaciones_dinero.write(0, aument_columns, column)
                aument_columns = aument_columns + 1

            #Agregar Información generada en la consulta
            self._cr.execute(query_vacaciones_dinero)
            result_query = self._cr.dictfetchall()
            aument_columns = 0
            aument_rows = 1
            for query in result_query:
                for row in query.values():
                    width = len(str(row)) + 10
                    if str(type(row)).find('date') > -1:
                        sheet_vacaciones_dinero.write_datetime(aument_rows, aument_columns, row, date_format)
                    else:
                        sheet_vacaciones_dinero.write(aument_rows, aument_columns, row)
                    sheet_vacaciones_dinero.set_column(aument_columns, aument_columns, width)
                    aument_columns = aument_columns + 1
                aument_rows = aument_rows + 1
                aument_columns = 0
            # Convertir en tabla
            array_header_table = []
            aument_rows = 2 if aument_rows == 1 else aument_rows
            for i in columns:
                dict = {'header': i}
                array_header_table.append(dict)
            sheet_vacaciones_dinero.add_table(0, 0, aument_rows - 1, len(columns) - 1,
                                  {'style': 'Table Style Medium 2', 'columns': array_header_table})
        if query_prima != '':
            columns = ['Regla Salarial', 'Fecha', 'Valor', 'Origen']
            sheet_prima = book.add_worksheet('PRIMA')
            # Agregar columnas
            aument_columns = 0
            for column in columns:
                sheet_prima.write(0, aument_columns, column)
                aument_columns = aument_columns + 1

            #Agregar Información generada en la consulta
            self._cr.execute(query_prima)
            result_query = self._cr.dictfetchall()
            aument_columns = 0
            aument_rows = 1
            for query in result_query:
                for row in query.values():
                    width = len(str(row)) + 10
                    if str(type(row)).find('date') > -1:
                        sheet_prima.write_datetime(aument_rows, aument_columns, row, date_format)
                    else:
                        sheet_prima.write(aument_rows, aument_columns, row)
                    sheet_prima.set_column(aument_columns, aument_columns, width)
                    aument_columns = aument_columns + 1
                aument_rows = aument_rows + 1
                aument_columns = 0
            # Convertir en tabla
            array_header_table = []
            aument_rows = 2 if aument_rows == 1 else aument_rows
            for i in columns:
                dict = {'header': i}
                array_header_table.append(dict)
            sheet_prima.add_table(0, 0, aument_rows - 1, len(columns) - 1,
                                      {'style': 'Table Style Medium 2', 'columns': array_header_table})
        if query_cesantias != '':
            columns = ['Regla Salarial', 'Fecha', 'Valor', 'Origen']
            sheet_cesantias = book.add_worksheet('CESANTIAS')
            # Agregar columnas
            aument_columns = 0
            for column in columns:
                sheet_cesantias.write(0, aument_columns, column)
                aument_columns = aument_columns + 1

            #Agregar Información generada en la consulta
            self._cr.execute(query_cesantias)
            result_query = self._cr.dictfetchall()
            aument_columns = 0
            aument_rows = 1
            for query in result_query:
                for row in query.values():
                    width = len(str(row)) + 10
                    if str(type(row)).find('date') > -1:
                        sheet_cesantias.write_datetime(aument_rows, aument_columns, row, date_format)
                    else:
                        sheet_cesantias.write(aument_rows, aument_columns, row)
                    sheet_cesantias.set_column(aument_columns, aument_columns, width)
                    aument_columns = aument_columns + 1
                aument_rows = aument_rows + 1
                aument_columns = 0
            # Convertir en tabla
            array_header_table = []
            aument_rows = 2 if aument_rows == 1 else aument_rows
            for i in columns:
                dict = {'header': i}
                array_header_table.append(dict)
            sheet_cesantias.add_table(0, 0, aument_rows - 1, len(columns) - 1,
                            {'style': 'Table Style Medium 2', 'columns': array_header_table})
        book.close()
        self.write({
            'excel_value_base_file': base64.b64encode(stream.getvalue()).decode('utf-8'),
            'excel_value_base_file_name': filename,
        })

        action = {
            'name': 'Export Acumulados variables',
            'type': 'ir.actions.act_url',
            'url': "web/content/?model=hr.payslip&id=" + str(
                self.id) + "&filename_field=excel_value_base_file_name&field=excel_value_base_file&download=true&filename=" + self.excel_value_base_file_name,
            'target': 'self',
        }
        return action

    def get_excel_lines(self):
        # Generar EXCEL
        filename = f'Líneas de recibo de nómina - {self.display_name}.xlsx'
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})
        date_format = book.add_format({'num_format': 'dd/mm/yyyy'})
        number_format = book.add_format({'num_format': '#,##'})

        columns = ['Nombre', 'Categoría', 'Cantidad', 'C. Inicio', 'C. Fin', 'Base', 'Entidad', 'Prestamo', 'Regla',
                   'Importe', 'Total']

        sheet = book.add_worksheet('Líneas')
        # Agregar columnas
        aument_columns = 0
        for column in columns:
            sheet.write(0, aument_columns, column)
            aument_columns = aument_columns + 1

        # Agregar Información
        aument_rows = 1
        for line in self.line_ids:
            sheet.write(aument_rows, 0, line.name)
            sheet.write(aument_rows, 1, line.category_id.display_name)
            sheet.write(aument_rows, 2, line.quantity,number_format)
            if line.initial_accrual_date:
                sheet.write_datetime(aument_rows, 3, line.initial_accrual_date, date_format)
            else:
                sheet.write(aument_rows, 3, '')
            if line.final_accrual_date:
                sheet.write_datetime(aument_rows, 4, line.final_accrual_date, date_format)
            else:
                sheet.write(aument_rows, 4, '')
            sheet.write(aument_rows, 5, line.amount_base,number_format)
            if line.entity_id:
                sheet.write(aument_rows, 6, line.entity_id.display_name)
            else:
                sheet.write(aument_rows, 6, '')
            if line.loan_id:
                sheet.write(aument_rows, 7, line.loan_id.display_name)
            else:
                sheet.write(aument_rows, 7, '')
            sheet.write(aument_rows, 8, line.salary_rule_id.display_name)
            sheet.write(aument_rows, 9, line.amount,number_format)
            sheet.write(aument_rows, 10, line.total,number_format)
            aument_rows = aument_rows + 1
        # Tamaño columnas
        sheet.set_column('A:B', 30)
        sheet.set_column('C:C', 10)
        sheet.set_column('D:F', 15)
        sheet.set_column('G:I', 30)
        sheet.set_column('J:K', 15)
        # Convertir en tabla
        array_header_table = []
        aument_rows = 2 if aument_rows == 1 else aument_rows
        for i in columns:
            dict = {'header': i}
            array_header_table.append(dict)
        sheet.add_table(0, 0, aument_rows - 1, len(columns) - 1,
                                   {'style': 'Table Style Medium 2', 'columns': array_header_table})

        book.close()
        self.write({
            'excel_lines': base64.encodebytes(stream.getvalue()),
            'excel_lines_filename': filename,
        })

        action = {
            'name': 'Export Excel líneas de recibo de nómina',
            'type': 'ir.actions.act_url',
            'url': "web/content/?model=hr.payslip&id=" + str(
                self.id) + "&filename_field=excel_lines_filename&field=excel_lines&download=true&filename=" + self.excel_lines_filename,
            'target': 'self',
        }
        return action

