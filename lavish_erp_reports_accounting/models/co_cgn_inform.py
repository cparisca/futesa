from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError
from datetime import datetime,timedelta
from pytz import timezone

import base64
import io
import xlsxwriter
import pandas as pd
import threading
import time

class lavish_co_cgn_inform(models.TransientModel):
    _name = 'lavish.co.cgn.inform'
    _description = 'Informe CO-CGN/Operaciones Recíprocas'

    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)
    date_start = fields.Date(string='Fecha inicial', required=True)
    date_end = fields.Date(string='Fecha final', required=True)
    type_report = fields.Selection([
        ('cgn', 'CGN'),
        ('orp', 'Operaciones Recíprocas')
    ], string='Reporte', required=True, default='cgn')
    type_return = fields.Selection([
        ('1', 'Plano'),
        ('2', 'Excel')
    ], string='Archivo a generar', required=True, default='1')
    excel_file = fields.Binary('Excel file')
    excel_file_name = fields.Char('Excel filename')
    txt_file = fields.Binary('TXT file')
    txt_file_name = fields.Char('TXT filename')

    def execute_report(self):
        lst_report = []
        lst_levels_group = []
        #Filtro para obtener movimientos
        query_where = f"where a.company_id = {self.company_id.id} and a.parent_state = 'posted' and a.date <= '{self.date_end}' "
        #domain = [('company_id', '=', self.company_id.id), ('parent_state', '=', 'posted'),
        #          ('date', '<=', self.date_end)]
        if self.type_report == 'orp':
            query_where += f"\n and d.partner_with_reciprocal_operations = true "
            #domain.append(('partner_id.partner_with_reciprocal_operations','=',True))
        # --------------------------------LOGICA POR SQL--------------------------------------------------------------
        # Obtener la cantidad de niveles existentes en el plan de cuenta
        obj_account_account = self.env['account.account'].search([])
        lst_levels_group = []
        lst_levels_group_str = []
        df_name_columns_account = []
        for account in obj_account_account:
            i = 1
            have_parent = True
            group_account = account.group_id
            while have_parent:
                if group_account.parent_id:
                    name_in_dict = (i, 'Nivel_' + str(i), 'Nivel_' + str(i) + '_CGN')
                    group_account = group_account.parent_id
                    if not name_in_dict in lst_levels_group:
                        lst_levels_group.append(name_in_dict)
                        lst_levels_group_str.append('Nivel_' + str(i))
                        df_name_columns_account.append('Nivel_' + str(i))
                        df_name_columns_account.append('Nivel_' + str(i) + '_CGN')
                    i += 1
                else:
                    have_parent = False
        query_select_levels_group = ''
        query_from_levels_group = ''
        for q_group in lst_levels_group:
            query_select_levels_group += f'''c{q_group[0]}.code_prefix_start as "{q_group[1]}", coalesce(c{q_group[0]}.code_cgn,'.') as "{q_group[2]}",'''
            query_from_levels_group += f'left join account_group as c{q_group[0]} on c{q_group[0] - 1}.parent_id = c{q_group[0]}.id '
        query_select_levels_group = '--NO AHI GRUPOS DE CUENTA' if query_select_levels_group == '' else query_select_levels_group
        query_from_levels_group = '--NO AHI GRUPOS DE CUENTA' if query_from_levels_group == '' else query_from_levels_group
        # --------------QUERY FINAL
        df_name_columns = df_name_columns_account + ['Nivel_0', 'Nivel_0_CGN', 'Nivel_Tercero',
                                                     'Nivel_ORP', 'TipoRegistro', 'Tercero', 'CodigoTerceroORP',
                                                     'Cuenta', 'CuentaCGN', 'SaldoInicial', 'Debito', 'Credito',
                                                     'SaldoFinal', 'ValorCorriente', 'ValorNoCorriente']
        query = f'''
                    Select -- Cuenta niveles
                            {query_select_levels_group}
                            c0.code_prefix_start as "Nivel_0", coalesce(c0.code_cgn,'.') as "Nivel_0_CGN",  
                            ' ' as "Nivel_Tercero", ' ' as "Nivel_ORP",'D' as "TipoRegistro",                          
                            --Tercero
                            coalesce(d.name,'') as "Tercero",
                            coalesce(d.code_partner_reciprocal_operations,'') as "CodigoTerceroORP",
                            -- Cuenta
                            c.code as "Cuenta", coalesce(c.code_cgn,'.') as "CuentaCGN",
                            --Valores
                            case when c.code like '2%' or c.code like '3%' or c.code like '4%'
                                then 
                                    case when a."date" < '{self.date_start}' then (a.debit - a.credit)*-1
                                        else 0 end 
                                else
                                    case when a."date" < '{self.date_start}' then a.debit - a.credit
                                        else 0 end 
                            end as "SaldoInicial",
                            case when a.date >= '{self.date_start}' and a.date <= '{self.date_end}' then a.debit
                                else 0 end as "Debito",	
                            case when a.date >= '{self.date_start}' and a.date <= '{self.date_end}' then a.credit
                                else 0 end as "Credito",
                            case when c.code like '2%' or c.code like '3%' or c.code like '4%' 
                                then
                                    ((case when a."date" < '{self.date_start}' then a.debit - a.credit else 0 end) + ((case when a.date >= '{self.date_start}' and a.date <= '{self.date_end}' then a.debit else 0 end) - (case when a.date >= '{self.date_start}' and a.date <= '{self.date_end}' then a.credit else 0 end)))*-1
                                else 
                                    (case when a."date" < '{self.date_start}' then a.debit - a.credit else 0 end) + ((case when a.date >= '{self.date_start}' and a.date <= '{self.date_end}' then a.debit else 0 end) - (case when a.date >= '{self.date_start}' and a.date <= '{self.date_end}' then a.credit else 0 end)) 
                            end as "SaldoFinal",                            
                            case when c.account_value = '1' then a.debit - a.credit else 0 end as "ValorCorriente",
                            case when c.account_value = '2' then a.debit - a.credit else 0 end as "ValorNoCorriente"
                    From account_move_line as a
                    inner join account_move as b on a.move_id = b.id 
                    inner join account_account as c on a.account_id = c.id
                    left join res_partner as d on a.partner_id = d.id  
                    left join account_group as c0 on c.group_id = c0.id
                    {query_from_levels_group}
                    {query_where}
            '''
        self.env.cr.execute(query)
        lst_report = self.env.cr.fetchall()
        # Logica Hilos // SE INACTIVA 29/07/2023
        '''
        obj_moves = self.env['account.move.line'].search(domain)
        x = int(self.env['ir.config_parameter'].sudo().get_param('lavish_account.qty_thread_moves_balance')) or 10000
        if len(obj_moves) == 0:
            raise ValidationError(_('No se encontro información con los filtros seleccionados, por favor verificar.'))

        moves_array = lambda obj_moves, x: [obj_moves[i:i + x] for i in range(0, len(obj_moves), x)]
        moves_array = moves_array(obj_moves, x)

        x = int(self.env['ir.config_parameter'].sudo().get_param('lavish_account.qty_thread_balance')) or 5  # psutil.cpu_count()//2
        moves_array_def = lambda moves_array, x: [moves_array[i:i + x] for i in range(0, len(moves_array), x)]
        moves_array_def = moves_array_def(moves_array, x)

        def get_dict_moves(moves_ids):
            time.sleep(1)
            # Crear cursor
            new_cr = self.pool.cursor()
            self_thread = self.with_env(self.env(cr=new_cr))
            #1 y 2. Recorrer las cuentas contables y obtener su info
            # Obtener movimientos de esa cuenta
            obj_moves = self_thread.env['account.move.line'].search([('id', 'in', moves_ids)]).with_env(self_thread.env(cr=new_cr))
            for move in obj_moves:
                if move.account_id.code:
                    group_account, have_parent, i, dict_levels_account, dict_initial = move.account_id.group_id, True, 1, {}, {}
                    # Validar cuantos niveles posee esta cuenta contable
                    while have_parent:
                        if group_account.parent_id:
                            name_in_dict = 'Nivel_' + str(i)
                            dict_levels_account[name_in_dict] = group_account.parent_id.code_prefix_start
                            dict_levels_account[name_in_dict+'_CGN'] = group_account.parent_id.code_cgn if group_account.parent_id.code_cgn else '.'
                            group_account = group_account.parent_id
                            i += 1
                            if not name_in_dict in lst_levels_group:
                                lst_levels_group.append(name_in_dict)
                        else:
                            have_parent = False
                    if self.type_report == 'cgn':
                        # Obtener valores
                        amount_initial, debit, credit = 0, 0, 0
                        amount_current, amount_non_current = 0, 0
                        if move.date < self.date_start:
                            amount_initial += (move.debit - move.credit)
                        else:
                            debit += move.debit
                            credit += move.credit
                        if move.account_id.account_value == '1':
                            amount_current += (move.debit - move.credit)
                        if move.account_id.account_value == '2':
                            amount_non_current += (move.debit - move.credit)
                        if move.account_id.code[0:1] in ['2', '3', '4']:
                            amount_final = (amount_initial + (debit - credit)) * -1
                            amount_initial = amount_initial * -1  # if amount_initial < 0 else amount_initial
                        else:
                            amount_final = amount_initial + (debit - credit)
                        #Guardar info
                        dict_info = {
                            'Nivel_0': move.account_id.group_id.code_prefix_start,
                            'Nivel_0_CGN': move.account_id.group_id.code_cgn if move.account_id.group_id.code_cgn else '.',
                            'TipoRegistro': 'D',
                            'Cuenta': move.account_id.code,
                            'CuentaCGN': move.account_id.code_cgn if move.account_id.code_cgn else '.',
                            'SaldoInicial': amount_initial,
                            'Debito': debit,
                            'Credito': credit,
                            'SaldoFinal': amount_final,
                            'ValorCorriente': amount_current,
                            'ValorNoCorriente': amount_non_current,
                        }
                        lst_report.append({**dict_levels_account, **dict_info})
                    if self.type_report == 'orp':
                        # Obtener valores
                        amount_initial, debit, credit = 0, 0, 0
                        amount_current, amount_non_current = 0, 0
                        code_partner_reciprocal_operations, name_partner = '', ''
                        if move.partner_id.code_partner_reciprocal_operations:
                            code_partner_reciprocal_operations = move.partner_id.code_partner_reciprocal_operations
                            name_partner = move.partner_id.name
                        if move.date < self.date_start:
                            amount_initial += (move.debit - move.credit)
                        else:
                            debit += move.debit
                            credit += move.credit
                        if move.account_id.account_value == '1':
                            amount_current += (move.debit - move.credit)
                        if move.account_id.account_value == '2':
                            amount_non_current += (move.debit - move.credit)
                        if move.account_id.code[0:1] in ['2', '3', '4']:
                            amount_final = (amount_initial + (debit - credit)) * -1
                            amount_initial = amount_initial * -1# if amount_initial < 0 else amount_initial
                        else:
                            amount_final = amount_initial + (debit - credit)
                        #Guardar info
                        dict_info = {
                            'Nivel_0': move.account_id.group_id.code_prefix_start,
                            'Nivel_0_CGN': move.account_id.group_id.code_cgn if move.account_id.group_id.code_cgn else '.',
                            'Nivel_Tercero': '',
                            'Nivel_ORP': '',
                            'TipoRegistro': 'D',
                            'Tercero': name_partner,
                            'CodigoTerceroORP': code_partner_reciprocal_operations,
                            'Cuenta': move.account_id.code,
                            'CuentaCGN': move.account_id.code_cgn if move.account_id.code_cgn else '.',
                            'SaldoInicial': amount_initial,
                            'Debito': debit,
                            'Credito': credit,
                            'SaldoFinal': amount_final,
                            'ValorCorriente': amount_current,
                            'ValorNoCorriente': amount_non_current,
                        }
                        lst_report.append({**dict_levels_account, **dict_info})
        #Lllamar hilos
        lst_report = []
        cont_blocks = 1
        for moves_group in moves_array_def:
            threads = []
            for i_moves in moves_group:
                if len(i_moves) > 0:
                    t = threading.Thread(target=get_dict_moves, args=(i_moves.ids,))
                    t.setDaemon(True)
                    threads.append(t)
                    t.start()
            for thread in threads:
                thread.join()
            cont_blocks += 1
        '''
        lst_levels_group = lst_levels_group_str
        if len(lst_report) == 0:
            raise ValidationError(_('No se encontro información con los filtros seleccionados, por favor verificar.'))
        #3. Convertir en dataframe de pandas
        df_report = pd.DataFrame(lst_report)
        df_report = df_report.set_axis(df_name_columns, axis=1)
        #4. Agrupar por niveles y cuentas
        lst_group_by = ['TipoRegistro', 'Cuenta', 'CuentaCGN']
        lst_levels_group_by = ['TipoRegistro', 'Nivel_0', 'Nivel_0_CGN']
        if self.type_report == 'orp':
            lst_group_by = ['TipoRegistro', 'Cuenta', 'CuentaCGN', 'Tercero', 'CodigoTerceroORP']
            lst_levels_group_by = ['TipoRegistro', 'Nivel_0', 'Nivel_0_CGN', 'Nivel_Tercero', 'Nivel_ORP']
        lst_dataframes = []
        lst_dataframes.append(df_report.groupby(by=lst_group_by, group_keys=False,as_index=False).sum())
        lst_dataframes.append(df_report.groupby(by=lst_levels_group_by, group_keys=False, as_index=False).sum())
        for lvl in lst_levels_group:
            lst_levels_group_by = ['TipoRegistro', lvl, lvl+'_CGN']
            if self.type_report == 'orp':
                lst_levels_group_by = ['TipoRegistro', lvl, lvl + '_CGN', 'Nivel_Tercero', 'Nivel_ORP']
            lst_dataframes.append(df_report.groupby(by=lst_levels_group_by, group_keys=False, as_index=False).sum())
        #5. Crear dataframe final y ordenar
        df_report_finally = False
        columns = lst_group_by + ['SaldoInicial', 'Debito', 'Credito', 'SaldoFinal', 'ValorCorriente', 'ValorNoCorriente']
        for df in lst_dataframes:
            df.columns = columns
            if type(df_report_finally) is bool:
                df_report_finally = df
            else:
                df_report_finally = df_report_finally.append(df)
        df_report_finally = df_report_finally.sort_values(by=lst_group_by)
        #6. Eliminar duplicados para garantizar la información
        df_report_finally = df_report_finally.groupby(by=lst_group_by, group_keys=False, as_index=False).sum()
        df_report_finally = df_report_finally.drop_duplicates()
        df_report_finally = df_report_finally[(df_report_finally['SaldoInicial'] != 0) | (df_report_finally['Debito'] != 0) | (df_report_finally['Credito'] != 0) | (df_report_finally['SaldoFinal'] != 0)]
        #7. Exportar a el archivo correspondiente
        if self.type_return == '1':
            def left(s, amount):
                return s[:amount]

            def right(s, amount):
                return s[-amount:]

            filename = f'{self.company_id.name} Informe CO_CGN {self.date_start}-{self.date_end}.txt'
            # Encabezado del archivo
            type_register = 'S'
            entity_code = self.company_id.entity_code_cgn if self.company_id.entity_code_cgn else ''
            period = '1' + right('00' + str(self.date_start.month), 2) + right('00' + str(self.date_end.month),2)
            year = str(self.date_start.year)
            name_of_form = 'CGN2015_001_SALDOS_Y_MOVIMIENTOS'
            if self.type_report == 'orp':
                name_of_form = 'CGN2015_002_OPERACIONES_RECIPROCAS_CONVERGENCIA'
            date_send = ''
            encab_content_txt = '''%s\t%s\t%s\t%s\t%s\t%s''' % (type_register,entity_code,period,year,name_of_form,date_send)
            #Detalle del archivo
            det_content_txt = ''
            cant_detalle = 0
            for index,row in df_report_finally.iterrows():
                cant_detalle = cant_detalle + 1
                type_register = 'D'
                if self.type_report == 'cgn':
                    concept = row['CuentaCGN'] if row['CuentaCGN']!='.' else row['Cuenta']
                    amount_initial = round(row['SaldoInicial'],2)
                    debit = round(row['Debito'],2)
                    credit = round(row['Credito'],2)
                    amount_final = round(row['SaldoFinal'],2)
                    amount_current = round(row['ValorCorriente'],2)
                    amount_non_current = round(row['ValorNoCorriente'],2)
                    content_line = '''%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s''' % (type_register, concept, amount_initial, debit, credit, amount_final, amount_current, amount_non_current)
                elif self.type_report == 'orp':
                    concept = row['CuentaCGN'] if row['CuentaCGN'] != '.' else row['Cuenta']
                    entity_reciprocal = row['CodigoTerceroORP']
                    amount_current = round(row['ValorCorriente'], 2)
                    amount_non_current = round(row['ValorNoCorriente'], 2)
                    content_line = '''%s\t%s\t%s\t%s\t%s''' % (type_register, concept, entity_reciprocal, amount_current, amount_non_current)
                else:
                    raise ValidationError('Debe seleccionar el tipo de reporte, por favor verificar.')
                if cant_detalle == 1:
                    det_content_txt = content_line
                else:
                    det_content_txt = det_content_txt + '\n' + content_line
            content_txt = encab_content_txt + '\n' + det_content_txt
            # Crear archivo
            self.write({
                'txt_file': base64.encodestring((content_txt).encode()),
                'txt_file_name': filename,
            })

            action = {
                'name': 'ArchivoPagos',
                'type': 'ir.actions.act_url',
                'url': "web/content/?model=lavish.co.cgn.inform&id=" + str(
                    self.id) + "&filename_field=txt_file_name&field=txt_file&download=true&filename=" + self.txt_file_name,
                'target': 'self',
            }
            return action
        else:
            filename = f'{self.company_id.name} Informe CO_CGN {self.date_start}-{self.date_end}.xlsx'
            if self.type_report == 'orp':
                filename = f'{self.company_id.name} Informe CO_ORP {self.date_start}-{self.date_end}.xlsx'
            stream = io.BytesIO()
            writer = pd.ExcelWriter(stream, engine='xlsxwriter')
            writer.book.filename = stream
            columns = lst_group_by + ['SaldoInicial', 'Debito', 'Credito', 'SaldoFinal', 'ValorCorriente', 'ValorNoCorriente']
            if self.type_report == 'orp':
                columns = lst_group_by + ['ValorCorriente','ValorNoCorriente']
            df_report_finally.to_excel(writer, sheet_name='Informe', float_format="%.2f", columns=columns,
                                       header=columns, index=False, startrow=3, startcol=0)
            worksheet = writer.sheets['Informe']
            # Agregar formatos al excel
            cell_format_title = writer.book.add_format({'bold': True, 'align': 'center'})
            cell_format_title.set_font_name('Calibri')
            cell_format_title.set_font_size(15)
            cell_format_title.set_font_color('#1F497D')
            cell_format_text_generate = writer.book.add_format({'text_wrap': True, 'bold': False, 'align': 'left'})
            cell_format_text_generate.set_font_name('Calibri')
            cell_format_text_generate.set_font_size(10)
            cell_format_text_generate.set_font_color('#1F497D')
            # Encabezado
            cant_columns = (len(lst_group_by) - 1) + 6
            text_generate = 'Generado por: \n %s \nFecha: \n %s %s' % (
                self.env.user.name, datetime.now(timezone(self.env.user.tz)).date(),
                datetime.now(timezone(self.env.user.tz)).time())
            worksheet.merge_range(0, 0, 0, cant_columns - 2, self.company_id.name, cell_format_title)
            worksheet.merge_range(0, cant_columns - 1, 2, cant_columns, text_generate, cell_format_text_generate)
            if self.type_report == 'orp':
                worksheet.merge_range(1, 0, 1, cant_columns - 2, 'INFORME Operaciones Recíprocas', cell_format_title)
            else:
                worksheet.merge_range(1, 0, 1, cant_columns - 2, 'INFORME CGN', cell_format_title)
            worksheet.merge_range(2, 0, 2, cant_columns - 2, str(self.date_start) + ' - ' + str(self.date_end), cell_format_title)
            # Dar tamaño a las columnas y formato
            position_initial = 0
            for c in columns:
                size = len(c)
                size_tmp = max(len(str(j)) for j in df_report_finally[c])
                size = size if size >= size_tmp else size_tmp

                format_align = writer.book.add_format({'align': 'left'})
                number_format = writer.book.add_format({'num_format': '#,##0.00'})
                if c in ['SaldoInicial', 'Debito', 'Credito', 'SaldoFinal', 'ValorCorriente', 'ValorNoCorriente']:
                    worksheet.set_column(position_initial, position_initial, size + 10, number_format)
                else:
                    worksheet.set_column(position_initial, position_initial, size + 10, format_align)
                position_initial += 1
            # Guardar excel
            writer.save()

            self.write({
                'excel_file': base64.encodebytes(stream.getvalue()),
                'excel_file_name': filename,
            })

            action = {
                'name': filename,
                'type': 'ir.actions.act_url',
                'url': "web/content/?model=lavish.co.cgn.inform&id=" + str(
                    self.id) + "&filename_field=excel_file_name&field=excel_file&download=true&filename=" + self.excel_file_name,
                'target': 'self',
            }
            return action





