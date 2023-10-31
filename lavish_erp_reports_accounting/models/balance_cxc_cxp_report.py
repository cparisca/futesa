from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
from pytz import timezone

import base64
import io
import xlsxwriter

class lavish_report_cxc_cxp(models.TransientModel):
    _name = 'lavish.report.cxc.cxp'
    _description = 'Saldos de CxC-CxP'

    company_id = fields.Many2one('res.company', string='Compañia', required=True,default=lambda self: self.env.company)
    cutoff_date = fields.Date(string='Fecha de corte')
    partner_id = fields.Many2one('res.partner', string='Tercero')
    accounts = fields.Selection([('receivable', 'Cuentas CxC'),
                                   ('payable', 'Cuentas CXP')
                                  ],string='Tipo de cuenta', required=True, default='receivable')
    invoice_ids = fields.Many2many('account.move', string='Facturas', domain="['|',('move_type', 'ilike', 'out'),('move_type', 'ilike', 'in')]")
    only_earrings = fields.Boolean(string='Sólo pendientes')
    accounting_account_ids = fields.Many2many('account.account', string='Cuenta', domain="[('user_type_id.type', '=', accounts)]")

    excel_file = fields.Binary('Excel')
    excel_file_name = fields.Char('Excel filename')
    def generate_excel(self):
        query_where = ''
        # Filtro de compañia
        query_where = query_where + f"where c.id = {self.env.company.id} "
        #Filtro fechas
        if self.cutoff_date:
            query_where = query_where + f"and a.date <= '{str(self.cutoff_date)}' "
        # Filtro partner
        if self.partner_id:
            query_where = query_where + f"and b.invoice_partner_display_name = '{self.partner_id.name}' "
        #Filtro del check
        if self.only_earrings == True:
            query_where = query_where + f"and b.payment_state = 'not_paid' "
        # Filtro facturas
        str_ids_invoice = ''
        for i in self.invoice_ids:
            str_ids_invoice = str(i.id) if str_ids_invoice == '' else str_ids_invoice + ',' + str(i.id)
        if str_ids_invoice != '':
            query_where = query_where + f"and b.id in ({str_ids_invoice}) "
        # Filtro venta y compras
        if self.accounts == 'receivable':
            query_where = query_where + f"and b.move_type like 'out_%'"
        if self.accounts == 'payable':
            query_where = query_where + f"and b.move_type like 'in_%'"
        # Filtro cuentas
        str_ids_accounts = ''
        for i in self.accounting_account_ids:
            str_ids_accounts = str(i.id) if str_ids_accounts == '' else str_ids_accounts + ',' + str(i.id)
        if str_ids_accounts != '':
            query_where = query_where + f"and f.id in ({str_ids_accounts}) "

        #Consulta sql acumulado
        query_report = f'''
                        select periodo,fecha_movimiento,diario,secuencia,currency,tipo_documento,ruc,partner,td,no_factura_provedor,fecha_doc,cuenta_contable,
                                sum(debito) as debito,sum(credito) as credito,sum(balance) as balance,
                                sum(amount_untaxed_signed) as amount_untaxed_signed,sum(amount_total) as amount_total,sum(amount_residual_signed) as amount_residual_signed
                        from (
                            select to_char(a."date",'yyyyMM') as periodo,a."date" as fecha_movimiento,
                                    d."name" as diario,a.move_name as secuencia,rc."name" as currency,
                                    case when e.document_type = '13' then 'Cédula de ciudadania'
                                    else case when e.document_type = '31' then 'NIT'
                                    else ''
                                    end 
                                    end as tipo_documento,e.vat as ruc,b.invoice_partner_display_name as partner,
                                    d."name" as td,b.supplier_invoice_number as no_factura_provedor,
                                    a."date" as fecha_doc,concat(f.code,' ',f."name") as cuenta_contable,
                                    sum(a.debit) as debito,sum(a.credit) as credito,sum(a.balance) as balance,
                                    b.amount_untaxed_signed, b.amount_total, b.amount_residual_signed
                            from account_move_line as a
                            inner join account_move as b on a.move_id = b.id and b.state = 'posted'
                            inner join res_currency as rc on b.currency_id = rc.id
                            inner join res_company as c on a.company_id = c.id
                            inner join account_journal as d on a.journal_id = d.id
                            inner join res_partner as e on a.partner_id = e.id
                            inner join account_account as f on a.account_id = f.id
                            inner join account_account_type as g on f.user_type_id = g.id and g.type in ('receivable','payable')
                            %s
                            group by a."date",rc."name",d."name",a.move_name,e.document_type,e.vat,b.invoice_partner_display_name,b.supplier_invoice_number,f.code,f."name",
			                        b.amount_untaxed_signed, b.amount_total, b.amount_residual_signed
			                Union
			                select to_char(a."date",'yyyyMM') as periodo,a."date" as fecha_movimiento,
                                    d."name" as diario,a.move_name as secuencia,rc."name" as currency,
                                    case when e.document_type = '13' then 'Cédula de ciudadania'
                                    else case when e.document_type = '31' then 'NIT'
                                    else ''
                                    end 
                                    end as tipo_documento,e.vat as ruc,b.invoice_partner_display_name as partner,
                                    d."name" as td,b.supplier_invoice_number as no_factura_provedor,
                                    a."date" as fecha_doc,concat(f.code,' ',f."name") as cuenta_contable,
                                    sum(coalesce(i.debit,a.debit)) as debito,sum(coalesce(coalesce(h.credit_amount_currency,i.credit),a.credit)) as credito,
                                    sum(coalesce(i.debit,a.debit))-sum(coalesce(coalesce(h.credit_amount_currency,i.credit),a.credit)) as balance, 
                                    --sum(coalesce(i.balance,a.balance)) as balance,
                                    0 as amount_untaxed_signed, 0 as amount_total, 0 as amount_residual_signed
                            from account_move_line as a
                            inner join account_move as b on a.move_id = b.id and b.state = 'posted'
                            inner join res_currency as rc on b.currency_id = rc.id
                            inner join res_company as c on a.company_id = c.id
                            inner join account_journal as d on a.journal_id = d.id
                            inner join res_partner as e on a.partner_id = e.id
                            inner join account_account as f on a.account_id = f.id
                            inner join account_account_type as g on f.user_type_id = g.id and g.type in ('receivable','payable')
                            inner join account_partial_reconcile as h on a.id = h.debit_move_id  
                            inner join account_move_line as i on h.credit_move_id = i.id --or a.id = i.id  
                            inner join account_move as j on i.move_id = j.id and j.state = 'posted'
                            inner join res_currency as rcc on j.currency_id = rcc.id 
                            inner join res_company as k on i.company_id = k.id
                            inner join account_journal as l on i.journal_id = l.id
                            inner join res_partner as m on i.partner_id = m.id
                            inner join account_account as n on i.account_id = n.id 
                            %s
                            group by a."date",rc."name",d."name",a.move_name,e.document_type,e.vat,b.invoice_partner_display_name,b.supplier_invoice_number,f.code,f."name",
                                    b.amount_untaxed_signed, b.amount_total, b.amount_residual_signed
                        ) as a
                        group by periodo,fecha_movimiento,diario,secuencia,currency,tipo_documento,ruc,partner,td,no_factura_provedor,fecha_doc,cuenta_contable
                        order by secuencia,fecha_movimiento
                            ''' % (query_where,query_where)

        self._cr.execute(query_report)
        result_query_acumulado = self._cr.dictfetchall()

        #Consulta sql detalle
        query_report = f'''
                select * from (
                    -- MOV ORIGINAL
                    select to_char(a."date",'yyyyMM') as periodo,a."date" as fecha_movimiento,
                            d."name" as diario,a.move_name as secuencia, a.move_name as mov_original,
                            rc."name" as currency,
                            case when e.document_type = '13' then 'Cédula de ciudadania'
                            else case when e.document_type = '31' then 'NIT'
                            else ''
                            end 
                            end as tipo_documento,e.vat as ruc,b.invoice_partner_display_name as partner,
                            d."name" as td,b.supplier_invoice_number as no_factura_provedor,
                            a."date" as fecha_doc,concat(f.code,' ',f."name") as cuenta_contable,
                            a.debit as debito,a.credit as credito	
                    from account_move_line as a
                    inner join account_move as b on a.move_id = b.id and b.state = 'posted'
                    inner join res_currency as rc on b.currency_id = rc.id 
                    inner join res_company as c on a.company_id = c.id
                    inner join account_journal as d on a.journal_id = d.id
                    inner join res_partner as e on a.partner_id = e.id
                    inner join account_account as f on a.account_id = f.id
                    inner join account_account_type as g on f.user_type_id = g.id and g.type in ('receivable','payable')
                    %s
                Union
                    -- PAGOS
                    select to_char(coalesce(i."date",a."date"),'yyyyMM') as periodo,coalesce(i."date",a."date") as fecha_movimiento,
                            coalesce(l."name",d."name") as diario,coalesce(i.move_name,a.move_name) as secuencia, a.move_name as mov_original,
                            coalesce(rcc."name",rc."name") as currency,
                            case when coalesce(m.document_type,e.document_type) = '13' then 'Cédula de ciudadania'
                            else case when coalesce(m.document_type,e.document_type) = '31' then 'NIT'
                            else ''
                            end 
                            end as tipo_documento,coalesce(m.vat,e.vat) as ruc,coalesce(j.invoice_partner_display_name,b.invoice_partner_display_name) as partner,
                            coalesce(l."name",d."name") as td,coalesce(j.supplier_invoice_number,b.supplier_invoice_number) as no_factura_provedor,
                            coalesce(i."date",a."date") as fecha_doc,concat(coalesce(n.code,f.code),' ',coalesce(n."name",f."name")) as cuenta_contable,
                            coalesce(i.debit,a.debit) as debito,coalesce(coalesce(h.credit_amount_currency,i.credit),a.credit) as credito		
                    from account_move_line as a
                    inner join account_move as b on a.move_id = b.id and b.state = 'posted'
                    inner join res_currency as rc on b.currency_id = rc.id
                    inner join res_company as c on a.company_id = c.id
                    inner join account_journal as d on a.journal_id = d.id
                    inner join res_partner as e on a.partner_id = e.id
                    inner join account_account as f on a.account_id = f.id
                    inner join account_account_type as g on f.user_type_id = g.id and g.type in ('receivable','payable')
                    inner join account_partial_reconcile as h on a.id = h.debit_move_id  
                    inner join account_move_line as i on h.credit_move_id = i.id --or a.id = i.id  
                    inner join account_move as j on i.move_id = j.id and j.state = 'posted'
                    inner join res_currency as rcc on j.currency_id = rcc.id
                    inner join res_company as k on i.company_id = k.id
                    inner join account_journal as l on i.journal_id = l.id
                    inner join res_partner as m on i.partner_id = m.id
                    inner join account_account as n on i.account_id = n.id 
                    %s     
                ) as a           
                order by mov_original,fecha_movimiento
                    ''' % (query_where,query_where)

        self._cr.execute(query_report)
        result_query = self._cr.dictfetchall()

        # Generar EXCEL
        filename = 'Reporte Saldos CxC y CxP'
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})

        # ------------------------ HOJA ACUMULADOS ----------------------------------
        # Columnas
        columns = ['Periodo', 'Fecha movimiento', 'Diario', 'Secuencia', 'Moneda', 'Tipo de documento', 'Nit',
                   'Partner', 'Tipo de documento factura',
                   'Numero de factura', 'fecha documento', 'Cuenta contable', 'Debito', 'Credito','Balance','Impuestos no incluidos','Total','Importe adeudado']
        sheet_acumulado = book.add_worksheet('Saldos CxC y CxP')
        # Formato para fechas y numeros
        date_format = book.add_format({'num_format': 'dd/mm/yyyy'})
        number_format = book.add_format({'num_format': '#,##'})

        # Agregar columnas
        aument_columns = 0
        for column in columns:
            sheet_acumulado.write(0, aument_columns, column)
            aument_columns = aument_columns + 1

        # Agregar query
        aument_columns = 0
        aument_rows = 1
        for query in result_query_acumulado:
            for row in query.values():
                width = len(str(row)) + 10
                if str(type(row)).find('date') > -1:
                    sheet_acumulado.write_datetime(aument_rows, aument_columns, row, date_format)
                else:
                    sheet_acumulado.write(aument_rows, aument_columns, row)
                # Ajustar tamaño columna
                sheet_acumulado.set_column(aument_columns, aument_columns, width)
                aument_columns = aument_columns + 1
            aument_rows = aument_rows + 1
            aument_columns = 0

        # Convertir en tabla
        array_header_table = []
        for i in columns:
            dict = {'header': i}
            array_header_table.append(dict)

        sheet_acumulado.add_table(0, 0, aument_rows - 1, len(columns) - 1,
                        {'style': 'Table Style Medium 2', 'columns': array_header_table})

        # ------------------------ HOJA DETALLE ----------------------------------

        # Columnas
        columns = ['Periodo', 'Fecha movimiento', 'Diario', 'Secuencia', 'Documento origen', 'Moneda', 'Tipo de documento', 'Nit', 'Partner', 'Tipo de documento factura',
                   'Numero de factura', 'fecha documento', 'Cuenta contable', 'Debito', 'Credito']
        sheet = book.add_worksheet('Detalle')
        # Formato para fechas y numeros
        date_format = book.add_format({'num_format': 'dd/mm/yyyy'})
        number_format = book.add_format({'num_format': '#,##'})

        # Agregar columnas
        aument_columns = 0
        for column in columns:
            sheet.write(0, aument_columns, column)
            aument_columns = aument_columns + 1

        # Agregar query
        aument_columns = 0
        aument_rows = 1
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

        sheet.add_table(0, 0, aument_rows-1, len(columns)-1, {'style': 'Table Style Medium 2', 'columns': array_header_table})

        # ------------------------ GUARDAR EXCEL ----------------------------------
        book.close()

        self.write({
            'excel_file': base64.encodestring(stream.getvalue()),
            'excel_file_name': filename,
        })

        action = {
            'name': 'Saldos CxC y CxP',
            'type': 'ir.actions.act_url',
            'url': "web/content/?model=lavish.report.cxc.cxp&id=" + str(
                self.id) + "&filename_field=excel_file_name&field=excel_file&download=true&filename=" + self.excel_file_name,
            'target': 'self',
        }
        return action
