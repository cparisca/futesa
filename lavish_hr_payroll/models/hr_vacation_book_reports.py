from odoo import tools
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from pytz import timezone

import base64
import io
import xlsxwriter


class hr_vacation_book(models.TransientModel):
    _name = "hr.vacation.book"
    _description = "Libro de vacaciones"

    final_year = fields.Integer('Año', required=True)
    final_month = fields.Selection([('1', 'Enero'),
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
    employee = fields.Many2many('hr.employee', string='Empleado')
    contract = fields.Many2many('hr.contract', string='Contrato')
    branch = fields.Many2many('lavish.res.branch', string='Sucursal',
                              domain=lambda self: [('id', 'in', self.env.user.branch_ids.ids)])
    analytic_account = fields.Many2many('account.analytic.account', string='Cuenta Analítica')

    excel_file = fields.Binary(string='Reporte libro de vacaciones')
    excel_file_name = fields.Char(string='Filename Reporte libro de vacaciones')

    def generate_excel(self):
        # Periodo
        date_from = f'{str(self.final_year)}-{str(self.final_month)}-01'
        date_initial = datetime.strptime(date_from, '%Y-%m-%d').date()
        date_from = str(date_initial)
        final_year = self.final_year if self.final_month != '12' else self.final_year + 1
        final_month = int(self.final_month) + 1 if self.final_month != '12' else 1
        date_to = f'{str(final_year)}-{str(final_month)}-01'
        date_end = (datetime.strptime(date_to,'%Y-%m-%d') - timedelta(days=1)).date()
        date_to = str(date_end)
        # Filtro compañia
        query_where = f"where b.id = {self.env.company.id} "
        # Filtro Empleado
        str_ids_employee = ''
        for i in self.employee:
            str_ids_employee = str(i.id) if str_ids_employee == '' else str_ids_employee + ',' + str(i.id)
        if str_ids_employee != '':
            query_where = query_where + f"and a.id in ({str_ids_employee}) "
        # Filtro Contratos
        str_ids_contract = ''
        for i in self.contract:
            str_ids_contract = str(i.id) if str_ids_contract == '' else str_ids_contract + ',' + str(i.id)
        if str_ids_contract != '':
            query_where = query_where + f"and hc.id in ({str_ids_contract}) "
        # Filtro Sucursal
        str_ids_branch = ''
        for i in self.branch:
            str_ids_branch = str(i.id) if str_ids_branch == '' else str_ids_branch + ',' + str(i.id)
        if str_ids_branch == '' and len(self.env.user.branch_ids.ids) > 0:
            for i in self.env.user.branch_ids.ids:
                str_ids_branch = str(i) if str_ids_branch == '' else str_ids_branch + ',' + str(i)
        if str_ids_branch != '':
            query_where = query_where + f"and d.id in ({str_ids_branch}) "
        # Filtro Cuenta analitica
        str_ids_analytic = ''
        for i in self.analytic_account:
            str_ids_analytic = str(i.id) if str_ids_analytic == '' else str_ids_analytic + ',' + str(i.id)
        if str_ids_analytic != '':
            query_where = query_where + f"and f.id in ({str_ids_analytic}) "
    # ----------------------------------Ejecutar consulta
        query_report = f'''
                        select distinct a.identification_id as cedula,a."name" as empleado,b."name" as compania, 
                                coalesce(c."name",'') as ubicacion_laboral,coalesce(d."name",'') as sucursal, coalesce(e."name",'') as departamento,
                                coalesce(f."name",'') as cuenta_analitica, coalesce(p.value_wage,hc.wage) as salario,hc.date_start as fecha_ingreso,
                                0 as dias_laborados,
                                -- Se toman los días de la provision para restarlos con el calculo del reporte
                                coalesce(p."time",0) as dias_pagados, 
                                0 as dias_disfrutados,0 as dias_remunerados,
                                0 as valor_dias_disfrutados, 0 as valor_dias_remunerados,                       
                                0 as dias_adeudados, 0 dias_vac_pendientes, coalesce(p.amount,0) as valor_a_pagar
                        from hr_employee as a 
                        inner join res_company as b on a.company_id = b.id
                        inner join hr_contract as hc on a.id = hc.employee_id and hc.active = true and hc.date_start <= '{date_to}'
                                                and (hc.state = 'open' or ((hc.retirement_date >= '{date_from}' and hc.retirement_date <= '{date_to}') or (hc.retirement_date >= '{date_to}')))
                        left join res_partner as c on a.address_id = c.id
                        left join lavish_res_branch as d on a.branch_id = d.id
                        left join hr_department as e on a.department_id = e.id 
                        left join account_analytic_account as f on a.analytic_account_id = f.id   
                        --Provision
                        left join ( 
                                    select c.employee_id,c.contract_id,c.value_wage,c.value_base,c."time",c.value_balance,c.value_payments,c.amount,c.current_payable_value 
                                    from 
                                    (
                                        select max(date_end) as max_date_provision,company_id
                                        from hr_executing_provisions where date_end <= '{date_to}' and company_id  = {self.env.company.id}
                                        group by company_id
                                    ) as a
                                    inner join hr_executing_provisions as b on a.max_date_provision = b.date_end and a.company_id = b.company_id
                                    inner join hr_executing_provisions_details as c on b.id = c.executing_provisions_id and c.provision = 'vacaciones'
                        ) as p on a.id = p.employee_id and hc.id = p.contract_id
                        {query_where}
                        order by a."name",b."name"
                    '''

        self._cr.execute(query_report)
        result_query = self._cr.dictfetchall()
        # Generar EXCEL
        filename = 'Reporte libro de vacaciones'
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})
        # Agregar textos al excel
        text_company = self.env.company.name
        text_title = 'Informe libro de vacaciones'
        text_dates = 'Fecha de corte %s' % (date_to)
        text_generate = 'Informe generado el %s' % (datetime.now(timezone(self.env.user.tz)))
        cell_format_title = book.add_format({'bold': True, 'align': 'left'})
        cell_format_title.set_font_name('Calibri')
        cell_format_title.set_font_size(15)
        cell_format_title.set_bottom(5)
        cell_format_title.set_bottom_color('#1F497D')
        cell_format_title.set_font_color('#1F497D')
        cell_format_text_generate = book.add_format({'bold': False, 'align': 'left'})
        cell_format_text_generate.set_font_name('Calibri')
        cell_format_text_generate.set_font_size(10)
        cell_format_text_generate.set_bottom(5)
        cell_format_text_generate.set_bottom_color('#1F497D')
        cell_format_text_generate.set_font_color('#1F497D')
        # Formato para fechas
        date_format = book.add_format({'num_format': 'dd/mm/yyyy'})

        #----------------------------------Hoja 1 - Libro de vacaciones

        # Columnas
        columns = ['Cédula', 'Nombres y Apellidos', 'Compañía', 'Ubicación laboral', 'Seccional', 'Departamento',
                   'Cuenta analítica','Salario Base', 'Fecha Ingreso', 'Días Laborados','Días Pagados',
                   'Dias de vacaciones disfrutados','Días de vacaciones remunerados',
                   'Valor días de vacaciones Disfrutados','Valor días de vacaciones remunerados',
                   'Dias laborados que se adeudan','Dias de vacaciones pendientes','Valor a Pagar']
        sheet = book.add_worksheet('Libro de vacaciones')
        sheet.merge_range('A1:R1', text_company, cell_format_title)
        sheet.merge_range('A2:R2', text_title, cell_format_title)
        sheet.merge_range('A3:R3', text_dates, cell_format_title)
        sheet.merge_range('A4:R4', text_generate, cell_format_text_generate)
        # Agregar columnas
        aument_columns = 0
        for column in columns:
            sheet.write(4, aument_columns, column)
            aument_columns = aument_columns + 1
        # Agregar query
        aument_columns = 0
        aument_rows = 5
        for query in result_query:
            date_start = ''
            employee_id,identification_id = 0,0
            days_labor,days_unpaid_absences,days_paid,days_paid_money = 0,0,0,0
            value_business_days,money_value = 0,0
            for row in query.values():
                width = len(str(row)) + 10
                # La columna 0 es Id Empleado por ende se guarda su valor en la variable employee_id
                identification_id = row if aument_columns == 0 else identification_id
                employee_id = self.env['hr.employee'].search([('identification_id','=',identification_id)],limit=1).id
                # La columna 8 es Fecha Ingreso por ende se guarda su valor en la variable date_start
                date_start = row if aument_columns == 8 else date_start
                if aument_columns <= 8:
                    if str(type(row)).find('date') > -1:
                        sheet.write_datetime(aument_rows, aument_columns, row, date_format)
                    else:
                        sheet.write(aument_rows, aument_columns, row)
                else:
                    if aument_columns == 9: # Dias Laborados
                        days_labor = self.dias360(date_start,date_end)
                        sheet.write(aument_rows, aument_columns, days_labor)
                    elif aument_columns == 10: # Días Totales Pagados
                        days_paid_money = sum([i.units_of_money for i in
                                         self.env['hr.vacation'].search([('employee_id', '=', employee_id),('departure_date','<=',date_end)])])
                        days_paid = days_labor - row
                        sheet.write(aument_rows, aument_columns,days_paid)
                    elif aument_columns == 11: # Días Disfrutados
                        sheet.write(aument_rows, aument_columns,((days_paid * 15) / 360)-days_paid_money)
                    elif aument_columns == 12: # Dias remunerados
                        sheet.write(aument_rows, aument_columns,days_paid_money)
                    elif aument_columns == 13: # Valor Dias disfrutados
                        value_business_days = sum([i.value_business_days for i in
                                               self.env['hr.vacation'].search([('employee_id', '=', employee_id),
                                                                               ('departure_date', '<=', date_end)])])
                        sheet.write(aument_rows, aument_columns,value_business_days)
                    elif aument_columns == 14: # Valor Dias remunerados
                        money_value = sum([i.money_value for i in
                                                   self.env['hr.vacation'].search([('employee_id', '=', employee_id),
                                                                                   ('departure_date', '<=', date_end)])])
                        sheet.write(aument_rows, aument_columns,money_value)
                    elif aument_columns == 15: # Días de Vacaciones Adeudados
                        sheet.write(aument_rows, aument_columns,(days_labor-days_paid))
                    elif aument_columns == 16: # Dias de vacaciones pendientes
                        sheet.write(aument_rows, aument_columns,(((days_labor-days_paid)*15)/360))
                    elif aument_columns == 17: # Valor a pagar
                        sheet.write(aument_rows, aument_columns,row)
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

        #----------------------------------Hoja 2 - Detalle del libro de vacaciones
        query_report = f'''
                        select distinct a.identification_id as cedula,a."name" as empleado,b."name" as compania, 
                            hv.initial_accrual_date as causacion_inicial,hv.final_accrual_date as causacion_final,
                            hv.departure_date as fecha_salida,hv.return_date as fecha_regreso,
                            sum(coalesce(hv.business_units,0)) as dias_habiles,sum(coalesce(hv.value_business_days,0)) as valor_dias_habiles,
                            sum(coalesce(hv.holiday_units,0)) as dias_festivas,sum(coalesce(hv.holiday_value,0)) as valor_dias_festivos,
                            sum(coalesce(hv.units_of_money,0)) as dias_dinero,sum(coalesce(hv.money_value,0)) as valor_dias_dinero
                        from hr_employee as a 
                        inner join res_company as b on a.company_id = b.id
                        inner join hr_contract as hc on a.id = hc.employee_id and hc.active = true and hc.date_start <= '{date_to}'
                                                and (hc.state = 'open' or ((hc.retirement_date >= '{date_from}' and hc.retirement_date <= '{date_to}') or (hc.retirement_date >= '{date_to}')))
                        inner join hr_vacation as hv on a.id = hv.employee_id and hc.id = hv.contract_id and hv.departure_date <= '{date_to}' 
                        left join res_partner as c on a.address_id = c.id
                        left join lavish_res_branch as d on a.branch_id = d.id
                        left join hr_department as e on a.department_id = e.id 
                        left join account_analytic_account as f on a.analytic_account_id = f.id
                        {query_where} 
                        group by a.identification_id,a."name",b."name",hv.initial_accrual_date,
                        hv.final_accrual_date,hv.departure_date,hv.return_date
                        order by a."name",b."name"
                    '''
        self._cr.execute(query_report)
        result_query = self._cr.dictfetchall()
        # Columnas
        columns = ['Cédula', 'Nombres y Apellidos', 'Compañía',
                   'Causación Inicial', 'Causación Final', 'Fecha Salida', 'Fecha Regreso', 'Días hábiles', 'Valor días hábiles',
                   'Días festivos', 'Valor días festivos','Días en dinero', 'Valor días en dinero']
        sheet_detail = book.add_worksheet('Detalle')
        # Agregar columnas
        aument_columns = 0
        for column in columns:
            sheet_detail.write(0, aument_columns, column)
            aument_columns = aument_columns + 1
        # Agregar query
        aument_columns = 0
        aument_rows = 1
        for query in result_query:
            for row in query.values():
                width = len(str(row)) + 10
                if str(type(row)).find('date') > -1:
                    sheet_detail.write_datetime(aument_rows, aument_columns, row, date_format)
                else:
                    sheet_detail.write(aument_rows, aument_columns, row)
                # Ajustar tamaño columna
                sheet_detail.set_column(aument_columns, aument_columns, width)
                aument_columns = aument_columns + 1
            aument_rows = aument_rows + 1
            aument_columns = 0

        # Convertir en tabla
        array_header_table = []
        for i in columns:
            dict = {'header': i}
            array_header_table.append(dict)

        sheet_detail.add_table(0, 0, aument_rows, len(columns) - 1,
                        {'style': 'Table Style Medium 2', 'columns': array_header_table})



        # Guadar Excel
        book.close()

        self.write({
            'excel_file': base64.b64encode(stream.getvalue()).decode('utf-8'),
            'excel_file_name': filename,
        })

        action = {
            'name': 'Reporte Libro de Vacaciones',
            'type': 'ir.actions.act_url',
            'url': "web/content/?model=hr.vacation.book&id=" + str(
                self.id) + "&filename_field=excel_file_name&field=excel_file&download=true&filename=" + self.excel_file_name,
            'target': 'self',
        }
        return action

