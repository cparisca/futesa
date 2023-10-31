from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
from pytz import timezone

import base64
import io
import xlsxwriter


class lavish_inform_sales_purchases(models.TransientModel):
    _name = 'lavish.inform.sales.purchases'
    _description = 'informe de compras y ventas'

    company_id = fields.Many2one('res.company', string='Compañia', required=True,
                                   default=lambda self: self.env.company)
    sales_purchases = fields.Selection([('sales', 'Ventas'),
                                          ('purchases', 'Compras')],
                                         string='Ventas/Compras', required=True, default='sales')
    start_date = fields.Date(string='Fecha incial', required=True)
    finish_date = fields.Date(string='Fecha final', required=True)

    excel_file = fields.Binary('Excel')
    excel_file_name = fields.Char('Excel filename')

    def report_excel(self):
        query_where = ''
        # Filtro de compañia
        query_where = query_where + f"where f.id = {self.env.company.id} "
        # Filtro fechas
        if self.start_date:
            query_where = query_where + f"and a.invoice_date >= '{str(self.start_date)}' "
        if self.finish_date:
            query_where = query_where + f"and a.invoice_date <= '{str(self.finish_date)}' "
        # Filtro venta y compras
        if self.sales_purchases == 'sales':
            query_where = query_where + f"and a.move_type like 'out_%'"
        if self.sales_purchases == 'purchases':
            query_where = query_where + f"and a.move_type like 'in_%'"
        query_report = f'''
                    select compañia,tipo_movimento,periodo,fecha_contable,codigo_corto,voucher,fecha_em,fecha_ven,
                            serie,tipo_de_documento,ruc,dv,partner,
                            venta_g,sum(iva) as iva,sum(reteiva) as reteiva,
                            sum(reterenta)as reterenta,sum(reteica)as reteica,
                            total,sum(autorenta_cd)as autorenta_cd,sum(autorenta_db)as autorenta_db,divisa,
                            total_divisa,nota_devolucion,glosa
                    from (
                    select f."name" as compañia,
                        case when a.move_type = 'out_invoice' then 'Ventas'
                            else case when a.move_type = 'out_refund' then 'Ventas'
                                else case when a.move_type = 'in_invoice' then 'Compras'
                                    else case when a.move_type = 'in_refund' then 'Compras'
                                        else ''
                                        end
                                    end
                                end
                            end as tipo_movimento,
                        a.invoice_date as periodo, a."date" as fecha_contable, b.code as codigo_corto, a.name as voucher,a.invoice_date as fecha_em, 
                        case when a.invoice_payment_term_id = null then a.invoice_date + h.days
                        else a.invoice_date_due
                        end as fecha_ven, a.name as serie, 
                        case when c.document_type = '11' then '11 - Registro civil de nacimiento'
                            else case when c.document_type = '12' then '12 - Tarjeta de identidad'
                                else case when c.document_type = '13' then '13 - Cédula de ciudadania'
                                    else case when c.document_type = '21' then '21 - Tarjeta de extranjeria'
                                        else case when c.document_type = '22' then '22 - Cédula de extranjeria'
                                            else case when c.document_type = '31' then '31 - NIT'
                                                else case when c.document_type = '41' then '41 - Pasaporte'
                                                    else case when c.document_type = '42' then '42 - Tipo de documento extranjero'
                                                        else case when c.document_type = '43' then '43 - Sin indetificación del exterior o para uso definido por la DIAN'
                                                            else case when c.document_type = '44' then '44 - Documento de identificación extranjero persona juridica'
                                                                else ''
                                                                end
                                                            end
                                                        end
                                                    end
                                                end
                                            end
                                        end
                                    end
                                end
                            end as tipo_de_documento,
                        c.vat as ruc, c.x_digit_verification as dv, c."name" as partner,
                        case when a.move_type = 'out_refund' or a.move_type = 'in_refund' then abs(a.amount_untaxed_signed)* -1 else abs(a.amount_untaxed_signed) end as venta_g,
                        case when '%s' = 'sales' 
                            then 
                                case when a.move_type = 'out_refund'
                                then
                                    case when sum(debit) > 0 
                                        then abs(sum(case when (aml."name" like '%%IVA%%' or aa."name" like '%%IVA%%') then abs(balance) else 0 end)) * -1
                                        else abs(sum(case when (aml."name" like '%%IVA%%' or aa."name" like '%%IVA%%') then abs(balance) else 0 end)) 
                                    end
                                else
                                    case when sum(debit) > 0 
                                        then abs(sum(case when (aml."name" like '%%IVA%%' or aa."name" like '%%IVA%%') then abs(balance) else 0 end)) * -1
                                        else abs(sum(case when (aml."name" like '%%IVA%%' or aa."name" like '%%IVA%%') then abs(balance) else 0 end))
                                    end
                                end
                            else 
                                case when a.move_type = 'in_refund'
                                then
                                    case when sum(debit) > 0 
                                        then abs(sum(case when (aml."name" like '%%IVA%%' or aa."name" like '%%IVA%%') then abs(balance) else 0 end))
                                        else abs(sum(case when (aml."name" like '%%IVA%%' or aa."name" like '%%IVA%%') then abs(balance) else 0 end)) * -1 
                                    end
                                else
                                    case when sum(debit) > 0 
                                        then abs(sum(case when (aml."name" like '%%IVA%%' or aa."name" like '%%IVA%%') then abs(balance) else 0 end)) 
                                        else abs(sum(case when (aml."name" like '%%IVA%%' or aa."name" like '%%IVA%%') then abs(balance) else 0 end)) * -1
                                    end
                                end
                        end as iva,
                        case when '%s' = 'sales' 
                            then 
                                case when a.move_type = 'out_refund'
                                then
                                    case when sum(debit) > 0 
                                        then abs(sum(case when (aml."name" like '%%RteIVA%%' or aa."name" like '%%RteIVA%%') then abs(balance) else 0 end)) * -1
                                        else abs(sum(case when (aml."name" like '%%RteIVA%%' or aa."name" like '%%RteIVA%%') then abs(balance) else 0 end)) 
                                    end
                                else
                                    case when sum(debit) > 0 
                                        then abs(sum(case when (aml."name" like '%%RteIVA%%' or aa."name" like '%%RteIVA%%') then abs(balance) else 0 end)) * -1
                                        else abs(sum(case when (aml."name" like '%%RteIVA%%' or aa."name" like '%%RteIVA%%') then abs(balance) else 0 end))
                                    end
                                end
                            else 
                                case when a.move_type = 'in_refund'
                                then
                                    case when sum(debit) > 0 
                                        then abs(sum(case when (aml."name" like '%%RteIVA%%' or aa."name" like '%%RteIVA%%') then abs(balance) else 0 end)) 
                                        else abs(sum(case when (aml."name" like '%%RteIVA%%' or aa."name" like '%%RteIVA%%') then abs(balance) else 0 end)) * -1
                                    end
                                else
                                    case when sum(debit) > 0 
                                        then abs(sum(case when (aml."name" like '%%RteIVA%%' or aa."name" like '%%RteIVA%%') then abs(balance) else 0 end)) 
                                        else abs(sum(case when (aml."name" like '%%RteIVA%%' or aa."name" like '%%RteIVA%%') then abs(balance) else 0 end)) * -1
                                    end
                                end
                        end as reteiva,
                        case when '%s' = 'sales'
                            then
                                case when a.move_type = 'out_refund'
                                then
                                    case when sum(debit) > 0 
                                        then abs(sum(case when (aml."name" like '%%RteFte%%' or aa."name" like '%%RteFte%%') then abs(balance) else 0 end)) * -1
                                        else abs(sum(case when (aml."name" like '%%RteFte%%' or aa."name" like '%%RteFte%%') then abs(balance) else 0 end)) 
                                    end
                                else
                                    case when sum(debit) > 0
                                        then abs(sum(case when (aml."name" like '%%RteFte%%' or aa."name" like '%%RteFte%%') then abs(balance) else 0 end)) * -1
                                        else abs(sum(case when (aml."name" like '%%RteFte%%' or aa."name" like '%%RteFte%%') then abs(balance) else 0 end))
                                    end
                                end
                            else 
                                case when a.move_type = 'in_refund'
                                then
                                    case when sum(debit) > 0 
                                        then abs(sum(case when (aml."name" like '%%RteFte%%' or aa."name" like '%%RteFte%%') then abs(balance) else 0 end)) 
                                        else abs(sum(case when (aml."name" like '%%RteFte%%' or aa."name" like '%%RteFte%%') then abs(balance) else 0 end)) * -1
                                    end
                                else
                                    case when sum(debit) > 0
                                        then abs(sum(case when (aml."name" like '%%RteFte%%' or aa."name" like '%%RteFte%%') then abs(balance) else 0 end)) 
                                        else abs(sum(case when (aml."name" like '%%RteFte%%' or aa."name" like '%%RteFte%%') then abs(balance) else 0 end)) * -1
                                    end
                                end
                        end as reterenta,
                        case when '%s' = 'sales' 
                            then
                                case when a.move_type = 'out_refund'
                                then
                                    case when sum(debit) > 0 
                                        then abs(sum(case when (aml."name" like '%%RteICA%%' or aa."name" like '%%RteICA%%') then abs(balance) else 0 end)) * -1
                                        else abs(sum(case when (aml."name" like '%%RteICA%%' or aa."name" like '%%RteICA%%') then abs(balance) else 0 end)) 
                                    end
                                else
                                    case when sum(debit) > 0
                                        then abs(sum(case when (aml."name" like '%%RteICA%%' or aa."name" like '%%RteICA%%') then abs(balance) else 0 end)) * -1
                                        else abs(sum(case when (aml."name" like '%%RteICA%%' or aa."name" like '%%RteICA%%') then abs(balance) else 0 end))
                                    end
                                end
                            else 
                                case when a.move_type = 'in_refund'
                                then
                                    case when sum(debit) > 0 
                                        then abs(sum(case when (aml."name" like '%%RteICA%%' or aa."name" like '%%RteICA%%') then abs(balance) else 0 end)) 
                                        else abs(sum(case when (aml."name" like '%%RteICA%%' or aa."name" like '%%RteICA%%') then abs(balance) else 0 end)) * -1
                                    end
                                else
                                    case when sum(debit) > 0
                                        then abs(sum(case when (aml."name" like '%%RteICA%%' or aa."name" like '%%RteICA%%') then abs(balance) else 0 end)) 
                                        else abs(sum(case when (aml."name" like '%%RteICA%%' or aa."name" like '%%RteICA%%') then abs(balance) else 0 end)) * -1
                                    end
                                end
                        end as reteica,   
                        case when a.move_type = 'out_refund' or a.move_type = 'in_refund' then abs(a.amount_total_signed)* -1 else abs(a.amount_total_signed) end as total,
                        case when '%s' = 'sales' 
                            then
                                case when a.move_type = 'out_refund'
                                    then sum(case when (aml."name" like '%%Autorretención%%' or aa."name" like '%%Autorretención%%') then abs(credit) else 0 end) * -1
                                    else sum(case when (aml."name" like '%%Autorretención%%' or aa."name" like '%%Autorretención%%') then abs(credit) else 0 end)
                                end
                            else
                                case when a.move_type = 'in_refund'
                                    then sum(case when (aml."name" like '%%Autorretención%%' or aa."name" like '%%Autorretención%%') then abs(credit) else 0 end) 
                                    else sum(case when (aml."name" like '%%Autorretención%%' or aa."name" like '%%Autorretención%%') then abs(credit) else 0 end) * -1
                                end
                        end as autorenta_cd,
                        case when '%s' = 'sales' 
                            then
                                case when a.move_type = 'out_refund'
                                    then sum(case when (aml."name" like '%%Autorretención%%' or aa."name" like '%%Autorretención%%') then abs(debit) else 0 end) 
                                    else sum(case when (aml."name" like '%%Autorretención%%' or aa."name" like '%%Autorretención%%') then abs(debit) else 0 end) * -1
                                end
                            else
                                case when a.move_type = 'in_refund'
                                    then sum(case when (aml."name" like '%%Autorretención%%' or aa."name" like '%%Autorretención%%') then abs(debit) else 0 end) * -1
                                    else sum(case when (aml."name" like '%%Autorretención%%' or aa."name" like '%%Autorretención%%') then abs(debit) else 0 end) 
                                end
                        end as autorenta_db,
                        e."name" as divisa, 
                        case when a.move_type = 'out_refund' or a.move_type = 'in_refund' then abs(a.amount_total_in_currency_signed)* -1 else abs(a.amount_total_in_currency_signed) end as total_divisa,
                        a."ref" as nota_devolucion,
                        concat(a."ref", ' ', a.supplier_invoice_number) as glosa
                        from account_move_line as aml
                        inner join account_move as a on aml.move_id = a.id and a.state = 'posted'
                        inner join account_journal as b on a.journal_id = b.id
                        inner join res_partner as c on a.partner_id = c.id
                        inner join res_currency as e on a.currency_id = e.id
                        inner join res_company as f on aml.company_id = f.id
                        inner join account_account as aa on aml.account_id = aa.id
                        left join account_payment_term as g on a.invoice_payment_term_id = g.id
                        left join account_payment_term_line as h on g.id = h.payment_id
                        %s
                        group by f."name",a.move_type,a.invoice_date,a."date",b.code,a.name,a.invoice_payment_term_id,a.invoice_date_due,a.invoice_date,h.days,c.document_type,c.vat,
                        c.x_digit_verification,c."name",a.amount_untaxed_signed,a.amount_total_signed,e."name",a.amount_total_in_currency_signed,
                        a."ref",a.supplier_invoice_number,aa."name"
                    ) as a  
                    group by compañia,tipo_movimento,periodo,fecha_contable,codigo_corto,voucher,fecha_em,fecha_ven,venta_g,
                    serie,tipo_de_documento,ruc,dv,partner,divisa,nota_devolucion,glosa,total,total_divisa
                    ''' % (self.sales_purchases,self.sales_purchases,self.sales_purchases,self.sales_purchases,self.sales_purchases,self.sales_purchases,query_where)
        # Ajuste TRM de PGM
        # a.amount_negotiated_trm as trm -- linea 86
        # a.amount_negotiated_trm -- linea 98
        self._cr.execute(query_report)
        result_query = self._cr.dictfetchall()

        # Generar EXCEL
        filename = 'Informe Ventas y Compras'
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})

        # Columnas
        columns = ['Compañia', 'Tipo factura', 'Periodo', 'Fecha contable', 'Código corto', 'Secuencia',
                   'Fecha emisión factura', 'Fecha de vencimiento', 'Asiento contable',
                   'Tipo de documento', 'NIT', 'Dígito de verificación', 'Partner', 'valor antes de impuestos', 'IVA',
                   'RETEIVA', 'RETEFUENTE', 'RETEICA', 'TOTAL',
                   'AUTORETENCIONES CREDITO', 'AUTORETENCIONES DEBITO', 'Moneda', 'Total divisa',
                   'Nota de devolución', 'Glosa'] #'TRM'
        sheet = book.add_worksheet('Informe Ventas y Compras')

        # Agregar textos al excel
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

        sheet.add_table(0, 0, aument_rows - 1, len(columns) - 1,
                        {'style': 'Table Style Medium 2', 'columns': array_header_table})

        # Guadar Excel
        book.close()

        self.write({
            'excel_file': base64.encodestring(stream.getvalue()),
            'excel_file_name': filename,
        })

        action = {
            'name': 'Informe Ventas y Compras',
            'type': 'ir.actions.act_url',
            'url': "web/content/?model=lavish.inform.sales.purchases&id=" + str(
                self.id) + "&filename_field=excel_file_name&field=excel_file&download=true&filename=" + self.excel_file_name,
            'target': 'self',
        }
        return action
