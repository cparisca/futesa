# -*- coding: utf-8 -*-

from logging import exception
from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from pytz import timezone

import base64
import io
import xlsxwriter
import math

class hr_payroll_social_security(models.Model):
    _inherit = 'hr.payroll.social.security'

    def get_excel(self):
        filename = 'Seguridad Social Periodo {}-{}.xlsx'.format(self.month, str(self.year))
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})
        sheet = book.add_worksheet('Seguridad Social')

        columns = [
            'N° de identificación', 'Empleado', 'Sucursal', 'Contrato', 'Días liquidados', 'Días incapacidad EPS',
            'Días licencia', 'Días licencia remunerada', 'Días maternidad', 'Días vacaciónes', 'Días incapacidad ARP',
            'Ingreso', 'Retiro', 'Sueldo', 'Tercero EPS', 'Valor base salud', 'Porc. Aporte salud empleados',
            'Valor salud empleado', 'Valor salud empleado nómina', 'Porc. Aporte salud empresa',
            'Valor salud empresa', 'Valor salud total', 'Diferencia salud', 'Tercero pensión',
            'Valor base fondo de pensión', 'Porc. Aporte pensión empleado', 'Valor pensión empleado',
            'Valor pensión empleado nómina', 'Porc. Aporte pensión empresa', 'Valor pensión empresa',
            'Valor pensión total', 'Diferencia pensión', 'Tiene AVP', 'Valor AVP','Tercero fondo solidaridad',
            'Porc. Fondo solidaridad', 'Valor fondo solidaridad', 'Valor fondo subsistencia', 'Tercero ARP',
            'Valor base ARP', 'Porc. Aporte ARP', 'Valor ARP', 'Exonerado ley 1607',
            'Tercero caja compensación', 'Valor base caja com', 'Porc. Aporte caja com', 'Valor caja com',
            'Tercero SENA', 'Valor base SENA', 'Porc. Aporte SENA', 'Valor SENA',
            'Tercero ICBF', 'Valor base ICBF', 'Porc. Aporte ICBF', 'Valor ICBF', 'Fecha Inicio SLN', 'Fecha Fin SLN',
            'Fecha Inicio IGE', 'Fecha Fin IGE',
            'Fecha Inicio LMA', 'Fecha Fin LMA', 'Fecha Inicio VACLR', 'Fecha Fin VACLR', 'Fecha Inicio VCT',
            'Fecha Fin VCT', 'Fecha Inicio IRL', 'Fecha Fin IRL'
        ]

        # Agregar textos al excel
        text_title = 'Seguridad Social'
        text_generate = 'Informe generado el %s' % (datetime.now(timezone(self.env.user.tz)))
        cell_format_title = book.add_format({'bold': True, 'align': 'left'})
        cell_format_title.set_font_name('Calibri')
        cell_format_title.set_font_size(15)
        cell_format_title.set_bottom(5)
        cell_format_title.set_bottom_color('#1F497D')
        cell_format_title.set_font_color('#1F497D')
        sheet.merge_range('A1:BO1', text_title, cell_format_title)
        cell_format_text_generate = book.add_format({'bold': False, 'align': 'left'})
        cell_format_text_generate.set_font_name('Calibri')
        cell_format_text_generate.set_font_size(10)
        cell_format_text_generate.set_bottom(5)
        cell_format_text_generate.set_bottom_color('#1F497D')
        cell_format_text_generate.set_font_color('#1F497D')
        sheet.merge_range('A2:BO2', text_generate, cell_format_text_generate)
        # Formato para fechas
        date_format = book.add_format({'num_format': 'dd/mm/yyyy'})

        # Agregar columnas
        aument_columns = 0
        for column in columns:
            sheet.write(2, aument_columns, column)
            sheet.set_column(aument_columns, aument_columns, len(str(column)) + 10)
            aument_columns = aument_columns + 1

        # Agregar valores
        aument_rows = 3
        for item in self.executing_social_security_ids:
            sheet.write(aument_rows, 0, item.employee_id.identification_id)
            sheet.write(aument_rows, 1, item.employee_id.name)
            sheet.write(aument_rows, 2, item.employee_id.branch_social_security_id.name)
            sheet.write(aument_rows, 3, item.contract_id.name)
            sheet.write(aument_rows, 4, item.nDiasLiquidados)
            sheet.write(aument_rows, 5, item.nDiasIncapacidadEPS)
            sheet.write(aument_rows, 6, item.nDiasLicencia)
            sheet.write(aument_rows, 7, item.nDiasLicenciaRenumerada)
            sheet.write(aument_rows, 8, item.nDiasMaternidad)
            sheet.write(aument_rows, 9, item.nDiasVacaciones)
            sheet.write(aument_rows, 10, item.nDiasIncapacidadARP)
            sheet.write(aument_rows, 11, item.nIngreso)
            sheet.write(aument_rows, 12, item.nRetiro)
            sheet.write(aument_rows, 13, item.nSueldo)
            sheet.write(aument_rows, 14, item.TerceroEPS.name if item.TerceroEPS else '')
            sheet.write(aument_rows, 15, item.nValorBaseSalud)
            sheet.write(aument_rows, 16, item.nPorcAporteSaludEmpleado)
            sheet.write(aument_rows, 17, item.nValorSaludEmpleado)
            sheet.write(aument_rows, 18, item.nValorSaludEmpleadoNomina)
            sheet.write(aument_rows, 19, item.nPorcAporteSaludEmpresa)
            sheet.write(aument_rows, 20, item.nValorSaludEmpresa)
            sheet.write(aument_rows, 21, item.nValorSaludTotal)
            sheet.write(aument_rows, 22, item.nDiferenciaSalud)
            sheet.write(aument_rows, 23, item.TerceroPension.name if item.TerceroPension else '')
            sheet.write(aument_rows, 24, item.nValorBaseFondoPension)
            sheet.write(aument_rows, 25, item.nPorcAportePensionEmpleado)
            sheet.write(aument_rows, 26, item.nValorPensionEmpleado)
            sheet.write(aument_rows, 27, item.nValorPensionEmpleadoNomina)
            sheet.write(aument_rows, 28, item.nPorcAportePensionEmpresa)
            sheet.write(aument_rows, 29, item.nValorPensionEmpresa)
            sheet.write(aument_rows, 30, item.nValorPensionTotal)
            sheet.write(aument_rows, 31, item.nDiferenciaPension)
            sheet.write(aument_rows, 32, item.cAVP)
            sheet.write(aument_rows, 33, item.nAporteVoluntarioPension)
            sheet.write(aument_rows, 34, item.TerceroFondoSolidaridad.name if item.TerceroFondoSolidaridad else '')
            sheet.write(aument_rows, 35, item.nPorcFondoSolidaridad)
            sheet.write(aument_rows, 36, item.nValorFondoSolidaridad)
            sheet.write(aument_rows, 37, item.nValorFondoSubsistencia)
            sheet.write(aument_rows, 38, item.TerceroARP.name if item.TerceroARP else '')
            sheet.write(aument_rows, 39, item.nValorBaseARP)
            sheet.write(aument_rows, 40, item.nPorcAporteARP)
            sheet.write(aument_rows, 41, item.nValorARP)
            sheet.write(aument_rows, 42, item.cExonerado1607)
            sheet.write(aument_rows, 43, item.TerceroCajaCom.name if item.TerceroCajaCom else '')
            sheet.write(aument_rows, 44, item.nValorBaseCajaCom)
            sheet.write(aument_rows, 45, item.nPorcAporteCajaCom)
            sheet.write(aument_rows, 46, item.nValorCajaCom)
            sheet.write(aument_rows, 47, item.TerceroSENA.name if item.TerceroSENA else '')
            sheet.write(aument_rows, 48, item.nValorBaseSENA)
            sheet.write(aument_rows, 49, item.nPorcAporteSENA)
            sheet.write(aument_rows, 50, item.nValorSENA)
            sheet.write(aument_rows, 51, item.TerceroICBF.name if item.TerceroICBF else '')
            sheet.write(aument_rows, 52, item.nValorBaseICBF)
            sheet.write(aument_rows, 53, item.nPorcAporteICBF)
            sheet.write(aument_rows, 54, item.nValorICBF)
            sheet.write(aument_rows, 55, item.dFechaInicioSLN, date_format)
            sheet.write(aument_rows, 56, item.dFechaFinSLN, date_format)
            sheet.write(aument_rows, 57, item.dFechaInicioIGE, date_format)
            sheet.write(aument_rows, 58, item.dFechaFinIGE, date_format)
            sheet.write(aument_rows, 59, item.dFechaInicioLMA, date_format)
            sheet.write(aument_rows, 60, item.dFechaFinLMA, date_format)
            sheet.write(aument_rows, 61, item.dFechaInicioVACLR, date_format)
            sheet.write(aument_rows, 62, item.dFechaFinVACLR, date_format)
            sheet.write(aument_rows, 63, item.dFechaInicioVCT, date_format)
            sheet.write(aument_rows, 64, item.dFechaFinVCT, date_format)
            sheet.write(aument_rows, 65, item.dFechaInicioIRL, date_format)
            sheet.write(aument_rows, 66, item.dFechaFinIRL, date_format)
            aument_rows = aument_rows + 1

        # Convertir en tabla
        array_header_table = []
        for i in columns:
            dict = {'header': i}
            array_header_table.append(dict)

        sheet.add_table(2, 0, aument_rows - 1, len(columns) - 1,
                        {'style': 'Table Style Medium 2', 'columns': array_header_table})

        book.close()

        self.write({
            'excel_file': base64.b64encode(stream.getvalue()).decode('utf-8'),
            'excel_file_name': filename,
        })

        action = {
            'name': 'Export Seguridad Social',
            'type': 'ir.actions.act_url',
            'url': "web/content/?model=hr.payroll.social.security&id=" + str(
                self.id) + "&filename_field=excel_file_name&field=excel_file&download=true&filename=" + self.excel_file_name,
            'target': 'self',
        }
        return action

    def get_excel_errors(self):
        filename = 'Seguridad Social Advertencias Periodo {}-{}.xlsx'.format(self.month, str(self.year))
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})
        sheet = book.add_worksheet('Seguridad Social')

        columns = [
            'Empleado', 'Sucursal', 'Advertencia'
        ]

        # Agregar columnas
        aument_columns = 0
        for columns in columns:
            sheet.write(0, aument_columns, columns)
            aument_columns = aument_columns + 1

        # Agregar valores
        aument_rows = 1
        for item in self.errors_social_security_ids:
            sheet.write(aument_rows, 0, item.employee_id.name)
            sheet.write(aument_rows, 1, item.branch_id.name)
            sheet.write(aument_rows, 2, item.description)
            aument_rows = aument_rows + 1
        book.close()

        self.write({
            'excel_file': base64.b64encode(stream.getvalue()).decode('utf-8'),
            'excel_file_name': filename,
        })

        action = {
            'name': 'Export Seguridad Social',
            'type': 'ir.actions.act_url',
            'url': "web/content/?model=hr.payroll.social.security&id=" + str(
                self.id) + "&filename_field=excel_file_name&field=excel_file&download=true&filename=" + self.excel_file_name,
            'target': 'self',
        }
        return action

    #METODOS REPORTE SEGURIDAD SOCIAL POR TIPO Y ENTIDAD
    def info_totals(self):
        dict_totals = {}
        for record in self:
            total_amount_employees = sum([i.nValorSaludEmpleadoNomina+i.nValorPensionEmpleadoNomina+i.nDiferenciaSalud+i.nDiferenciaPension for i in record.executing_social_security_ids])
            total_amount_company = sum([i.nValorSaludEmpresa+i.nValorPensionEmpresa+i.nValorARP+i.nValorCajaCom+i.nValorSENA+i.nValorICBF for i in record.executing_social_security_ids])
            dict_totals = {'total_employees':len(record.executing_social_security_ids.employee_id),
                           'total_amount_employees': float("{:.2f}".format(total_amount_employees)),
                           'total_amount_company': float("{:.2f}".format(total_amount_company)),
                           'total_amount_final': float("{:.2f}".format(total_amount_employees+total_amount_company))}
        return dict_totals

    def get_info_eps(self):
        lst_eps = []
        for record in self:
            obj_type_eps = self.env['hr.contribution.register'].search([('type_entities','=','eps')],limit=1)
            obj_entities = self.env['hr.employee.entities'].search([('types_entities','in',obj_type_eps.ids)])

            for entity in sorted(obj_entities,key=lambda x: x.partner_id.name):
                info = record.executing_social_security_ids.filtered(lambda x: x.TerceroEPS.id == entity.id and x.nValorSaludEmpleadoNomina+x.nValorSaludEmpresa+x.nDiferenciaSalud != 0)
                nValorSaludEmpleadoTotal,nValorSaludEmpresaTotal,nDiferenciaSaludTotal = 0,0,0
                for i in info:
                    nValorSaludEmpleadoTotal += i.nValorSaludEmpleadoNomina
                    nValorSaludEmpresaTotal += i.nValorSaludEmpresa
                    nDiferenciaSaludTotal += i.nDiferenciaSalud

                if nValorSaludEmpleadoTotal + nValorSaludEmpresaTotal + nDiferenciaSaludTotal != 0:
                    dict_eps = {'name': entity.partner_id.name,
                                'identifcation': entity.partner_id.vat,
                                'cod_pila': entity.code_pila_eps,
                                'num_employees': len(info.employee_id),
                                'value_employees': float("{:.2f}".format(nValorSaludEmpleadoTotal)),
                                'value_company': float("{:.2f}".format(nValorSaludEmpresaTotal)),
                                'dif_round': float("{:.2f}".format(nDiferenciaSaludTotal)),
                                }
                    lst_eps.append(dict_eps)

        return lst_eps

    def get_info_pension(self):
        lst_eps = []
        for record in self:
            obj_type_eps = self.env['hr.contribution.register'].search([('type_entities','=','pension')],limit=1)
            obj_entities = self.env['hr.employee.entities'].search([('types_entities','in',obj_type_eps.ids)])

            for entity in sorted(obj_entities,key=lambda x: x.partner_id.name):
                info = record.executing_social_security_ids.filtered(lambda x: x.TerceroPension.id == entity.id and x.nValorPensionEmpleadoNomina+x.nValorPensionEmpresa+x.nDiferenciaPension != 0)
                nValorPensionEmpleadoTotal,nValorPensionEmpresaTotal,nDiferenciaPensionTotal = 0,0,0
                for i in info:
                    nValorPensionEmpleadoTotal += i.nValorPensionEmpleadoNomina
                    nValorPensionEmpresaTotal += i.nValorPensionEmpresa
                    nDiferenciaPensionTotal += i.nDiferenciaPension

                if nValorPensionEmpleadoTotal + nValorPensionEmpresaTotal + nDiferenciaPensionTotal != 0:
                    dict_eps = {'name': entity.partner_id.name,
                                'identifcation': entity.partner_id.vat,
                                'cod_pila': entity.code_pila_eps,
                                'num_employees': len(info.employee_id),
                                'value_employees': float("{:.2f}".format(nValorPensionEmpleadoTotal)),
                                'value_company': float("{:.2f}".format(nValorPensionEmpresaTotal)),
                                'dif_round': float("{:.2f}".format(nDiferenciaPensionTotal)),
                                }
                    lst_eps.append(dict_eps)

        return lst_eps

    def get_info_solidaridad(self):
        lst_eps = []
        for record in self:
            obj_type_eps = self.env['hr.contribution.register'].search([('type_entities','in',['pension', 'solidaridad', 'subsistencia'])],limit=1)
            obj_entities = self.env['hr.employee.entities'].search([('types_entities','in',obj_type_eps.ids)])

            for entity in sorted(obj_entities,key=lambda x: x.partner_id.name):
                info = record.executing_social_security_ids.filtered(lambda x: x.TerceroFondoSolidaridad.id == entity.id and x.nValorFondoSolidaridad+x.nValorFondoSubsistencia != 0)
                nValorFondoSolidaridad,nValorFondoSubsistencia = 0,0
                for i in info:
                    nValorFondoSolidaridad += i.nValorFondoSolidaridad
                    nValorFondoSubsistencia += i.nValorFondoSubsistencia

                if nValorFondoSolidaridad + nValorFondoSubsistencia != 0:
                    dict_eps = {'name': entity.partner_id.name,
                                'identifcation': entity.partner_id.vat,
                                'cod_pila': entity.code_pila_eps,
                                'num_employees': len(info.employee_id),
                                'value_solidaridad': float("{:.2f}".format(nValorFondoSolidaridad+nValorFondoSubsistencia))                                
                                }
                    lst_eps.append(dict_eps)

        return lst_eps

    def get_info_arp(self):
        lst_eps = []
        for record in self:
            obj_type_eps = self.env['hr.contribution.register'].search([('type_entities','=','riesgo')],limit=1)
            obj_entities = self.env['hr.employee.entities'].search([('types_entities','in',obj_type_eps.ids)])

            for entity in sorted(obj_entities,key=lambda x: x.partner_id.name):
                info = record.executing_social_security_ids.filtered(lambda x: x.TerceroARP.id == entity.id and x.nValorARP != 0)
                nValorARP = 0
                for i in info:
                    nValorARP += i.nValorARP

                if nValorARP != 0:
                    dict_eps = {'name': entity.partner_id.name,
                                'identifcation': entity.partner_id.vat,
                                'cod_pila': entity.code_pila_eps,
                                'num_employees': len(info.employee_id),
                                'value_arp': float("{:.2f}".format(nValorARP)),
                                }
                    lst_eps.append(dict_eps)

        return lst_eps

    def get_info_compensacion(self): 
        lst_eps = []
        for record in self:
            obj_type_eps = self.env['hr.contribution.register'].search([('type_entities','=','caja')],limit=1)
            obj_entities = self.env['hr.employee.entities'].search([('types_entities','in',obj_type_eps.ids)])

            for entity in sorted(obj_entities,key=lambda x: x.partner_id.name):
                info = record.executing_social_security_ids.filtered(lambda x: x.TerceroCajaCom.id == entity.id and x.nValorCajaCom != 0)
                nValorCajaCom = 0
                for i in info:
                    nValorCajaCom += i.nValorCajaCom

                if nValorCajaCom != 0:
                    dict_eps = {'name': entity.partner_id.name,
                                'identifcation': entity.partner_id.vat,
                                'cod_pila': entity.code_pila_ccf,
                                'num_employees': len(info.employee_id),
                                'value_cajacom': float("{:.2f}".format(nValorCajaCom)),
                                }
                    lst_eps.append(dict_eps)

        return lst_eps

    def get_info_sena(self): 
        lst_eps = []
        for record in self:
            obj_type_eps = self.env['hr.contribution.register'].search([('type_entities','=','sena')],limit=1)
            obj_entities = self.env['hr.employee.entities'].search([('types_entities','in',obj_type_eps.ids)])

            for entity in sorted(obj_entities,key=lambda x: x.partner_id.name):
                info = record.executing_social_security_ids.filtered(lambda x: x.TerceroSENA.id == entity.id and x.nValorSENA != 0)
                nValorSENA = 0
                for i in info:
                    nValorSENA += i.nValorSENA

                if nValorSENA != 0:
                    dict_eps = {'name': entity.partner_id.name,
                                'identifcation': entity.partner_id.vat,
                                'cod_pila': entity.code_pila_eps,
                                'num_employees': len(info.employee_id),
                                'value_sena': float("{:.2f}".format(nValorSENA)),
                                }
                    lst_eps.append(dict_eps)

        return lst_eps

    def get_info_icbf(self): 
        lst_eps = []
        for record in self:
            obj_type_eps = self.env['hr.contribution.register'].search([('type_entities','=','icbf')],limit=1)
            obj_entities = self.env['hr.employee.entities'].search([('types_entities','in',obj_type_eps.ids)])

            for entity in sorted(obj_entities,key=lambda x: x.partner_id.name):
                info = record.executing_social_security_ids.filtered(lambda x: x.TerceroICBF.id == entity.id and x.nValorICBF != 0)
                nValorICBF = 0
                for i in info:
                    nValorICBF += i.nValorICBF

                if nValorICBF != 0:
                    dict_eps = {'name': entity.partner_id.name,
                                'identifcation': entity.partner_id.vat,
                                'cod_pila': entity.code_pila_eps,
                                'num_employees': len(info.employee_id),
                                'value_icbf': float("{:.2f}".format(nValorICBF)),
                                }
                    lst_eps.append(dict_eps)

        return lst_eps




