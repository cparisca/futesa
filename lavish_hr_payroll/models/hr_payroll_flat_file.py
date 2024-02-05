# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta
from pytz import timezone

import base64
import io
import xlsxwriter
#---------------------------Modelo para generar Archivo plano de pago de nómina-------------------------------#

class hr_payroll_flat_file_detail(models.Model):
    _name = 'hr.payroll.flat.file.detail'
    _description = 'Archivo plano de pago de nómina detalle - Archivos planos'

    flat_file_id = fields.Many2one('hr.payroll.flat.file',string='Proceso')
    journal_id = fields.Many2one('account.journal', string='Diario', domain=[('is_payroll_spreader', '=', True)])
    plane_type = fields.Selection([('bancolombiasap', 'Bancolombia SAP'),
                                   ('bancolombiapab', 'Bancolombia PAB'),
                                   ('davivienda1', 'Davivienda 1'),
                                   ('occired', 'Occired'),
                                   ('avvillas1', 'AV VILLAS 1'),
                                   ('bancobogota', 'Banco Bogotá'),
                                   ('popular', 'Banco Popular'),
                                   ('bbva', 'Banco BBVA'),
                                   ('not_include', 'Reglas no incluidas'),
                                   ], string='Tipo de Plano')
    txt_file = fields.Binary('Archivo plano file')
    txt_file_name = fields.Char('Archivo plano filename')
    excel_file = fields.Binary('Excel')
    excel_file_name = fields.Char('Excel filename')
    liquidations_ids= fields.Many2many('hr.payslip', string='Liquidaciones', domain=[('definitive_plan', '=', False),('payslip_run_id', '=', False)])
    def download_txt(self):
        if self.txt_file:
            action = {
                'name': 'ArchivoPlano',
                'type': 'ir.actions.act_url',
                'url': "web/content/?model=hr.payroll.flat.file.detail&id=" + str(
                    self.id) + "&filename_field=txt_file_name&field=txt_file&download=true&filename=" + self.txt_file_name,
                'target': 'self',
            }
            return action
        else:
            raise ValidationError('No se genero archivo plano.')

    def download_excel(self):
        if self.excel_file:
            action = {
                'name': 'ArchivoPlano',
                'type': 'ir.actions.act_url',
                'url': "web/content/?model=hr.payroll.flat.file.detail&id=" + str(
                    self.id) + "&filename_field=excel_file_name&field=excel_file&download=true&filename=" + self.excel_file_name,
                'target': 'self',
            }
            return action
        else:
            raise ValidationError('No se genero archivo excel.')

class hr_payroll_flat_file(models.Model):
    _name = 'hr.payroll.flat.file'
    _description = 'Archivo plano de pago de nómina'

    journal_id = fields.Many2one('account.journal', string='Diario', domain=[('is_payroll_spreader', '=', True)])
    payment_type = fields.Selection([('225', 'Pago de Nómina')], string='Tipo de pago', required=True, default='225', readonly=True)
    company_id = fields.Many2one('res.company',string='Compañia', required=True, default=lambda self: self.env.company)
    vat_payer = fields.Char(string='NIT Pagador', store=True, readonly=True, related='company_id.partner_id.vat')
    payslip_id = fields.Many2one('hr.payslip.run',string='Lote de nómina', domain=[('definitive_plan', '=', False)])
    transmission_date = fields.Datetime(string="Fecha transmisión de lote", required=True, default=fields.Datetime.now())
    application_date = fields.Date(string="Fecha aplicación transacciones", required=True, default=fields.Date.today())
    description = fields.Char(string='Descripción', required=True)
    type_flat_file = fields.Selection([('sap', 'Bancolombia SAP'),
                                        ('pab', 'Bancolombia PAB'),
                                        ('occired','Occired')],'Tipo de archivo', default='sap') 
    source_information = fields.Selection([('lote', 'Por lote'),
                                          ('liquidacion', 'Por liquidaciones')],'Origen información', default='lote') 
    liquidations_ids= fields.Many2many('hr.payslip', string='Liquidaciones', domain=[('definitive_plan', '=', False),('payslip_run_id', '=', False)])
    flat_file_detail_ids = fields.One2many('hr.payroll.flat.file.detail','flat_file_id',string='Archivos planos')
    flat_rule_not_included = fields.Boolean('Plano de reglas no incluidas')
    
    def name_get(self):
        result = []
        for record in self:            
            result.append((record.id, "Archivo de Pago - {}".format(record.description)))
        return result

    #Lógica de bancolombia sap
    def generate_flat_file_sap(self,obj_payslip):
        filler = ' '
        def left(s, amount):
                return s[:amount]
            
        def right(s, amount):
            return s[-amount:]
        #----------------------------------Registro de Control de Lote----------------------------------
        tipo_registro = '1'
        nit_entidad = right(10*'0'+self.vat_payer,10)
        nombre_entidad = left(self.company_id.partner_id.name+16*filler,16) 
        clase_transacciones = self.payment_type
        descripcion = left(self.description+10*filler,10)
        fecha_transmision = str(self.transmission_date.year)[-2:]+right('00'+str(self.transmission_date.month),2)+right('00'+str(self.transmission_date.day),2)
        secuencia = 'A'
        fecha_aplicacion = str(self.application_date.year)[-2:]+right('00'+str(self.application_date.month),2)+right('00'+str(self.application_date.day),2)
        num_registros = 'NumRegs' # Mas adelante se reeemplaza con el valor correcto
        sum_debitos = 12*'0'
        sum_creditos = 'SumCreditos' # Mas adelante se reeemplaza con el valor correcto
        #Obtener cuenta
        cuenta_cliente = ''
        tipo_cuenta = ''
        for journal in self.journal_id:            
            cuenta_cliente = right(11*'0'+str(journal.bank_account_id.acc_number).replace("-",""),11)
            tipo_cuenta = 'S' if journal.bank_account_id.type_account == 'A' else 'D' # S : aho / D : cte
        if cuenta_cliente == '':
            raise ValidationError(_('No existe una cuenta bancaria configurada como dispersora de nómina, por favor verificar.'))
        #Concatenar encabezado
        encab_content = '''%s%s%s%s%s%s%s%s%s%s%s%s%s''' % (tipo_registro,nit_entidad,nombre_entidad,clase_transacciones,descripcion,fecha_transmision,secuencia,fecha_aplicacion,num_registros,sum_debitos,sum_creditos,cuenta_cliente,tipo_cuenta)
        #----------------------------------Registro Detalle de Transacciones---------------------------------
        detalle_content = ''
        #Traer la información
        cant_detalle = 0
        total_valor_transaccion = 0
        for payslip in obj_payslip:
            cant_detalle = cant_detalle + 1

            tipo_registro = '6'
            nit_beneficiario = nit_entidad = right(15*'0'+payslip.contract_id.employee_id.identification_id,15)
            nombre_beneficiario = left(payslip.contract_id.employee_id.name+18*filler,18) 
            #Inf Bancaria
            banco = ''
            cuenta_beneficiario = ''
            indicador_lugar_pago = ''
            tipo_transaccion = ''
            for bank in payslip.contract_id.employee_id.address_home_id.bank_ids:
                if bank.is_main:
                    banco = right(9*'0'+bank.bank_id.bic,9)
                    cuenta_beneficiario = right(17*'0'+str(bank.acc_number).replace("-",""),17)
                    indicador_lugar_pago = 'S'
                    tipo_transaccion = '37' if bank.type_account == 'A' else '27' # 27: Abono a cuenta corriente / 37: Abono a cuenta ahorros 
            if cuenta_beneficiario == '':
                raise ValidationError(_('El empleado '+payslip.contract_id.employee_id.name+' no tiene configurada la información bancaria, por favor verificar.'))
            #Obtener valor de transacción 
            valor_transacción = 10*'0'
            valor_not_include = 0
            for line in payslip.line_ids:
                valor_not_include += line.total if line.salary_rule_id.not_include_flat_payment_file else 0
                if line.code == 'NET':
                    total_valor_transaccion = (total_valor_transaccion + line.total) - valor_not_include
                    total_valor_transaccion = 0 if total_valor_transaccion < 0 else total_valor_transaccion
                    val_write = line.total - valor_not_include
                    val_write = 0 if val_write < 0 else val_write
                    valor = str(val_write).split(".") # Eliminar decimales
                    valor_transacción = right(10*'0'+str(valor[0]),10)
            concepto = 9*filler
            referencia = 12*filler
            relleno = filler

            content_line = '''%s%s%s%s%s%s%s%s%s%s%s''' % (tipo_registro,nit_beneficiario,nombre_beneficiario,banco,cuenta_beneficiario,indicador_lugar_pago,tipo_transaccion,valor_transacción,concepto,referencia,relleno)
            if cant_detalle == 1:
                detalle_content = content_line
            else:
                detalle_content = detalle_content +'\n'+ content_line

        #----------------------------------Generar archivo---------------------------------
        #Reemplazar valores del encabezado
        encab_content = encab_content.replace("NumRegs", right(6*'0'+str(cant_detalle),6))
        valor_total = str(total_valor_transaccion).split(".") # Eliminar decimales
        encab_content = encab_content.replace("SumCreditos", right(12*'0'+str(valor_total[0]),12))
        #Unir Encabezado y Detalle
        content_txt = encab_content +'\n'+ detalle_content 

        #Retornar archivo
        return base64.encodebytes((content_txt).encode())

    #Lógica de bancolombia pab
    def generate_flat_file_pab(self,obj_payslip):
        filler = ' '
        def left(s, amount):
                return s[:amount]
            
        def right(s, amount):
            return s[-amount:]
        #----------------------------------Registro de Control de Lote----------------------------------
        tipo_registro = '1'
        nit_entidad = right(15*'0'+self.vat_payer,15)
        aplication = 'I'
        filler_one = filler*15
        clase_transacciones = self.payment_type
        descripcion = left(self.description+10*filler,10)
        fecha_transmision = str(self.transmission_date.year)+right('00'+str(self.transmission_date.month),2)+right('00'+str(self.transmission_date.day),2)
        secuencia = '01'
        fecha_aplicacion = str(self.application_date.year)+right('00'+str(self.application_date.month),2)+right('00'+str(self.application_date.day),2)
        num_registros = 'NumRegs' # Mas adelante se reeemplaza con el valor correcto
        sum_debitos = 17*'0'
        sum_creditos = 'SumCreditos' # Mas adelante se reeemplaza con el valor correcto
        #Obtener cuenta
        cuenta_cliente = ''
        tipo_cuenta = ''
        for journal in self.journal_id:            
            cuenta_cliente = right(11*'0'+str(journal.bank_account_id.acc_number).replace("-",""),11)
            tipo_cuenta = 'S' if journal.bank_account_id.type_account == 'A' else 'D' # S : aho / D : cte
        if cuenta_cliente == '':
            raise ValidationError(_('No existe una cuenta bancaria configurada como dispersora de nómina, por favor verificar.'))
        filler_two = filler*149

        #Concatenar encabezado
        encab_content = '%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s' % (tipo_registro,nit_entidad,aplication,filler_one,clase_transacciones,descripcion,fecha_transmision,secuencia,fecha_aplicacion,num_registros,sum_debitos,sum_creditos,cuenta_cliente,tipo_cuenta,filler_two)
        #----------------------------------Registro Detalle de Transacciones---------------------------------
        detalle_content = ''
        #Traer la información
        cant_detalle = 0
        total_valor_transaccion = 0

        for payslip in obj_payslip:
            cant_detalle = cant_detalle + 1

            tipo_registro = '6'
            nit_beneficiario = left(payslip.contract_id.employee_id.identification_id+15*' ',15)
            nombre_beneficiario = left(payslip.contract_id.employee_id.name+30*' ',30) 
            #Inf Bancaria
            banco = ''
            cuenta_beneficiario = ''
            indicador_lugar_pago = ''
            tipo_transaccion = ''
            for bank in payslip.contract_id.employee_id.address_home_id.bank_ids:
                if bank.is_main:
                    banco = right(9*'0'+bank.bank_id.bic,9)
                    cuenta_beneficiario = left(str(bank.acc_number).replace("-","")+17*' ',17)
                    indicador_lugar_pago = 'S'
                    tipo_transaccion = '37' if bank.type_account == 'A' else '27' # 27: Abono a cuenta corriente / 37: Abono a cuenta ahorros 
            if cuenta_beneficiario == '':
                raise ValidationError(_('El empleado '+payslip.contract_id.employee_id.name+' no tiene configurada la información bancaria, por favor verificar.'))
            #Obtener valor de transacción 
            valor_transaccion = 15*'0'
            valor_transaccion_decimal = 2*'0'
            valor_not_include = 0
            for line in payslip.line_ids:
                valor_not_include += line.total if line.salary_rule_id.not_include_flat_payment_file else 0
                if line.code == 'NET':
                    total_valor_transaccion = (total_valor_transaccion + line.total) - valor_not_include
                    total_valor_transaccion = 0 if total_valor_transaccion < 0 else total_valor_transaccion
                    val_write = line.total - valor_not_include
                    val_write = 0 if val_write < 0 else val_write
                    valor = str(val_write).split(".") # Eliminar decimales
                    valor_transaccion = right(15*'0'+str(valor[0]),15)
                    valor_transaccion_decimal = right(2*'0'+str(valor[1]),2)
            fecha_aplicacion_det = fecha_aplicacion
            referencia = 21*filler
            tipo_identificacion = ' ' # Es requerido solo si el pago es para entregar por ventanilla por ende enviamos vacio
            oficina_entrega = 5*'0'
            numero_fax = 15*filler
            email = left(payslip.contract_id.employee_id.work_email+80*' ',80)
            identificacion_autorizado = 15*filler # Solo se llena cuando es cheques
            relleno = filler*27

            content_line = '''%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s''' % (tipo_registro,nit_beneficiario,nombre_beneficiario,banco,cuenta_beneficiario,indicador_lugar_pago,tipo_transaccion,valor_transaccion,valor_transaccion_decimal,fecha_aplicacion_det,referencia,tipo_identificacion,oficina_entrega,numero_fax,email,identificacion_autorizado,relleno)
            if cant_detalle == 1:
                detalle_content = content_line
            else:
                detalle_content = detalle_content +'\n'+ content_line

        #----------------------------------Generar archivo---------------------------------
        #Reemplazar valores del encabezado
        encab_content = encab_content.replace("NumRegs", right(6*'0'+str(cant_detalle),6))
        valor_total = str(total_valor_transaccion).split(".")[0] # Eliminar decimales
        if len(str(total_valor_transaccion).split(".")) > 1:
            valor_total_decimal = str(total_valor_transaccion).split(".")[1]
        else:
            valor_total_decimal = '00'
        encab_content = encab_content.replace("SumCreditos", right(15*'0'+str(valor_total),15)+right(2*'0'+str(valor_total_decimal),2))
        #Unir Encabezado y Detalle
        content_txt = encab_content +'\n'+ detalle_content

        # Retornar archivo
        return base64.encodebytes((content_txt).encode())

    #Lógica de occired
    def generate_flat_file_occired(self,obj_payslip):
        filler = ' '
        def left(s, amount):
                return s[:amount]
            
        def right(s, amount):
            return s[-amount:]
        #----------------------------------Registro de Control de Lote----------------------------------
        tipo_registro_encab = '1'
        consecutivo = '0000'
        date_today = self.transmission_date
        fecha_pago = str(date_today.year)+right('00'+str(date_today.month),2)+right('00'+str(date_today.day),2) 
        numero_registro = 'NumRegs'
        valor_total = 'ValTotal'
        cuenta_principal = ''
        for journal in self.journal_id:            
            cuenta_principal = right(16*'0'+str(journal.bank_account_id.acc_number).replace("-",""),16)
        if cuenta_principal == '':
            raise ValidationError(_('No existe una cuenta bancaria configurada como dispersora de nómina, por favor verificar.'))
        identificacion_del_archivo = 6*'0'
        ceros = 142*'0'            
        
        encab_content_txt = '''%s%s%s%s%s%s%s%s''' % (tipo_registro_encab,consecutivo,fecha_pago,numero_registro,valor_total,cuenta_principal,identificacion_del_archivo,ceros)
        
        #----------------------------------Registro Detalle de Transacciones---------------------------------
        det_content_txt = ''
        tipo_registro_det = '2'
        #Traer la información
        cant_detalle = 0
        total_valor_transaccion = 0

        #Agregar query
        for payslip in obj_payslip:
            cant_detalle = cant_detalle + 1
            consecutivo = right('0000'+str(cant_detalle),4)
            forma_de_pago = '3' # 1: Pago en Cheque  2: Pago abono a cuenta  - Banco de Occidente  3: Abono a cuenta otras entidades
            
            #Inf Bancaria
            tipo_transaccion = ''
            banco_destino = ''
            no_cuenta_beneficiario = ''
            for bank in payslip.contract_id.employee_id.address_home_id.bank_ids:
                if bank.is_main:
                    tipo_transaccion = 'A' if bank.type_account == 'A' else 'C' # C: Abono a cuenta corriente / A: Abono a cuenta ahorros 
                    banco_destino = '0'+right(3*'0'+bank.bank_id.bic,3)
                    forma_de_pago = '2' if bank.bank_id.bic == '1023' else forma_de_pago
                    no_cuenta_beneficiario = right(16*'0'+str(bank.acc_number).replace("-",""),16)  
            if no_cuenta_beneficiario == '':
                raise ValidationError(_('El empleado '+payslip.contract_id.employee_id.name+' no tiene configurada la información bancaria, por favor verificar.'))
            
            nit_beneficiario = right(11*'0'+payslip.contract_id.employee_id.identification_id,11)        
            nombre_beneficiario = left(payslip.contract_id.employee_id.name+30*' ',30)
            fecha_pago = str(self.application_date.year)+right('00'+str(self.application_date.month),2)+right('00'+str(self.application_date.day),2) 
            
            #Obtener valor de transacción 
            valor_transaccion = 13*'0'
            valor_transaccion_decimal = 2*'0'
            valor_not_include = 0
            for line in payslip.line_ids:
                valor_not_include += line.total if line.salary_rule_id.not_include_flat_payment_file else 0
                if line.code == 'NET':
                    total_valor_transaccion = (total_valor_transaccion + line.total) - valor_not_include
                    total_valor_transaccion = 0 if total_valor_transaccion < 0 else total_valor_transaccion
                    val_write = line.total - valor_not_include
                    val_write = 0 if val_write < 0 else val_write
                    valor = str(val_write).split(".") # Eliminar decimales
                    valor_transaccion = right(13*'0'+str(valor[0]),13)
                    valor_transaccion_decimal = right(2*'0'+str(valor[1]),2)         
            
            numbers = [temp for temp in payslip.number.split("/") if temp.isdigit()]
            documento_autorizado = ''
            for i in numbers:
                documento_autorizado = documento_autorizado + str(i)
            documento_autorizado = right(filler*12+documento_autorizado,12)
        
            referencia = 80*filler
                
            content_line = '''%s%s%s%s%s%s%s%s%s%s%s%s%s%s''' % (tipo_registro_det,consecutivo,cuenta_principal,nombre_beneficiario,nit_beneficiario,banco_destino,fecha_pago,forma_de_pago,valor_transaccion,valor_transaccion_decimal,no_cuenta_beneficiario,documento_autorizado,tipo_transaccion,referencia)
            if cant_detalle == 1:
                det_content_txt = content_line
            else:
                det_content_txt = det_content_txt +'\n'+ content_line
            
        #Encabezado - parte 2            
        encab_content_txt = encab_content_txt.replace("NumRegs", right('0000'+str(cant_detalle),4))        
        valor = str(total_valor_transaccion).split(".") # Eliminar decimales
        parte_entera = right(16*'0'+str(valor[0]),16)
        if len(valor)>1:
            parte_decimal = right(2*'0'+str(valor[1]),2) 
        else:
            parte_decimal = 2*'0'
        encab_content_txt = encab_content_txt.replace("ValTotal", parte_entera+''+parte_decimal)
        
        #Totales
        tipo_registro_tot = '3'
        secuencia = '9999'
        numero_registro = right('0000'+str(cant_detalle),4)
        valor = str(total_valor_transaccion).split(".") # Eliminar decimales
        parte_entera = right(16*'0'+str(valor[0]),16)
        if len(valor)>1:
            parte_decimal = right(2*'0'+str(valor[1]),2) 
        else: 
            parte_decimal = 2*'0'
        valor_total = parte_entera+''+parte_decimal
        ceros = 172*'0'

        tot_content_txt = '''%s%s%s%s%s''' % (tipo_registro_tot,secuencia,numero_registro,valor_total,ceros)

        #Unir Encabezado, Detalle y Totales
        if det_content_txt == '':
            raise ValidationError(_('No existe información en las liquidaciones seleccionadas, por favor verificar.'))
        
        content_txt = encab_content_txt +'\n'+ det_content_txt +'\n'+ tot_content_txt

        # Retornar archivo
        return base64.encodebytes((content_txt).encode())

    # Lógica de avvillas
    def generate_flat_file_avvillas(self,obj_payslip):
        filler = ' '
        def left(s, amount):
            return s[:amount]

        def right(s, amount):
            return s[-amount:]
        # ----------------------------------Registro de Control----------------------------------
        tipo_registro_encab = '01'
        date_today = str(self.transmission_date.date()).replace('-', '')
        transmission_time = str((self.transmission_date-timedelta(hours=5)).time()).replace(':', '')
        office_code = '088'
        acquirer_code = '02'
        file_name = 50 * filler
        backfill = 120 * filler

        encab_content_txt = '''%s%s%s%s%s%s%s''' % (tipo_registro_encab, date_today, transmission_time, office_code, acquirer_code, file_name, backfill)

        # ----------------------------------Registro Detalle---------------------------------
        det_content_txt = ''
        tipo_registro_det = '02'
        codigo_transaccion = '000023'  # 000023 pago nomina- TD plus y abono afc #000024 pago provedores
        tipo_producto_origen = '01' if self.journal_id.bank_account_id.type_account == 'A' else '06'  # 01: Abono a cuenta ahorros /  06: Abono a cuenta corriente
        cuenta_origen = right(16 * '0' + str(self.journal_id.bank_account_id.acc_number), 16)
        entidad_destino = '052'

        numero_factura = 16 * '0'
        referencia_1 = 16 * '0'
        referencia_2 = 16 * '0'
        cant_detalle = 0
        total_valor_transaccion = 0
        numero_autorizacion = 6 * '0'
        codigo_respuesta = '00'  # 00 Transaccion correcto
        retencion_contingente = 18 * '0'
        relleno = 2 * filler

        # Agregar query
        for payslip in obj_payslip:
            cant_detalle = cant_detalle + 1
            secuencia = right(9*'0' + str(cant_detalle), 9)
            nombre = left(payslip.contract_id.employee_id.name + 30 * ' ', 30)
            numero_documento = right(11 * '0' + payslip.contract_id.employee_id.identification_id, 11)

            # Inf Bancaria
            tipo_producto_destino = ''
            no_cuenta_beneficiario = ''
            for bank in payslip.contract_id.employee_id.address_home_id.bank_ids:
                if bank.is_main:
                    tipo_producto_destino = '01' if bank.type_account == 'A' else '06'  # 01: Abono a cuenta ahorros /  06: Abono a cuenta corriente
                    no_cuenta_beneficiario = right(16 * '0' + str(bank.acc_number).replace("-", ""), 16)
            if no_cuenta_beneficiario == '':
                raise ValidationError( _('El empleado ' + payslip.contract_id.employee_id.name + ' no tiene configurada la información bancaria, por favor verificar.'))

            # Obtener valor de transacción
            valor_transaccion = 16 * '0'
            valor_transaccion_decimal = 2 * '0'
            valor_not_include = 0
            for line in payslip.line_ids:
                valor_not_include += line.total if line.salary_rule_id.not_include_flat_payment_file else 0
                if line.code == 'NET':
                    total_valor_transaccion = (total_valor_transaccion + line.total) - valor_not_include
                    total_valor_transaccion = 0 if total_valor_transaccion < 0 else total_valor_transaccion
                    val_write = line.total - valor_not_include
                    val_write = 0 if val_write < 0 else val_write
                    valor = str(val_write).split(".")  # Eliminar decimales
                    valor_transaccion = right(16 * '0' + str(valor[0]), 16)
                    valor_transaccion_decimal = right(2 * '0' + str(valor[1]), 2)

            content_line = '''%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s''' % (
            tipo_registro_det, codigo_transaccion, tipo_producto_origen, cuenta_origen, entidad_destino,
            tipo_producto_destino, no_cuenta_beneficiario, secuencia, valor_transaccion, valor_transaccion_decimal,
            numero_factura, referencia_1, referencia_2, nombre, numero_documento, numero_autorizacion, codigo_respuesta,
            retencion_contingente, relleno)
            if cant_detalle == 1:
                det_content_txt = content_line
            else:
                det_content_txt = det_content_txt + '\n' + content_line

        # Totales
        tipo_registro_tot = '03'
        cantidad_registros = right(9 * '0' + str(cant_detalle), 9)
        valor = str(total_valor_transaccion).split(".")  # Eliminar decimales
        parte_entera = right(18 * '0' + str(valor[0]), 18)
        if len(valor) > 1:
            parte_decimal = right(2 * '0' + str(valor[1]), 2)
        else:
            parte_decimal = 2 * '0'
        valor_total_tra = parte_entera + '' + parte_decimal
        digito_chequeo = 15 * filler
        relleno = 145 * filler

        tot_content_txt = '''%s%s%s%s%s''' % (
        tipo_registro_tot, cantidad_registros, valor_total_tra, digito_chequeo, relleno)

        # Unir Encabezado, Detalle y Totales
        if det_content_txt == '':
            raise ValidationError(
                _('No existe información en las liquidaciones seleccionadas, por favor verificar.'))

        content_txt = encab_content_txt + '\n' + det_content_txt + '\n' + tot_content_txt

        # Retornar archivo
        return base64.encodebytes((content_txt).encode())

    # Lógica de Davivienda
    def generate_flat_file_davivienda(self,obj_payslip):
        filler = ' '
        def left(s, amount):
            return s[:amount]

        def right(s, amount):
            return s[-amount:]
        # ----------------------------------Registro de Control----------------------------------
        tipo_registro_encab = 'RC'
        nit_empresa = right(16*'0'+self.vat_payer+''+str(self.company_id.partner_id.dv),16)
        codigo_servicio = 4*'0'  # NOMI pago nomina
        codigo_subservicio = 4*'0'  # NOMI Para el servicio de Nómina
        cuenta_empresa = right(16 * '0' + str(self.journal_id.bank_account_id.acc_number), 16)
        tipo_cuenta = 'CA' if self.journal_id.bank_account_id.type_account == 'A' else 'CC'  # CC: Cuenta corriente / CA: Cuenta ahorros
        codigo_banco = '000051'
        valor_total_trasladados = 'ValorTotalTraslados' # Mas adelante se reeemplaza con el valor correcto
        numero_trasladados = 'NumTraslados' # Mas adelante se reeemplaza con el valor correcto
        fecha_proceso = str(self.transmission_date.date()).replace('-', '')
        hora_proceso = str((self.transmission_date-timedelta(hours=5)).time()).replace(':', '')
        codigo_operador = 4 * '0'
        codigo_no_procesado = 4 * '9'
        fecha_generacion = 8 * '0'
        hora_generacion = 6 * '0'
        indicador_incripcion = '00'
        tipo_identificacion = '03'  # 03 NIT
        numero_cliente_asignado = 12 * '0'
        oficina_recaudo = 4 * '0'
        campo_futuro = 40 * '0'

        encab_content_txt = '''%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s''' % (
        tipo_registro_encab, nit_empresa, codigo_servicio, codigo_subservicio, cuenta_empresa, tipo_cuenta, codigo_banco, valor_total_trasladados,
        numero_trasladados, fecha_proceso, hora_proceso, codigo_operador, codigo_no_procesado, fecha_generacion,
        hora_generacion, indicador_incripcion, tipo_identificacion, numero_cliente_asignado, oficina_recaudo,
        campo_futuro)

        # ----------------------------------Registro Detalle de Transacciones---------------------------------
        detalle_content = ''
        # Traer la información
        cant_detalle = 0
        total_valor_transaccion = 0
        for payslip in obj_payslip:
            cant_detalle = cant_detalle + 1

            tipo_registro = 'TR'
            referencia = 16*'0'
            cod_banco = '000051'
            talon = 6 * '0'
            validar_ach = '1'
            resultado_proceso = '9999'
            mensaje_respuesta = 40 * '0'
            valor_acumulado = 18 * '0'
            fecha_aplicacion = 8 * '0'
            oficina_recaudo = 4 * '0'
            motivo = 4 * '0'
            relleno = 7 * '0'

            tipo_identificacion_beneficiario = payslip.contract_id.employee_id.address_home_id.document_type
            if tipo_identificacion_beneficiario == '11':
                tipo_identificacion_beneficiario =  '13' #  Registro Civil de Nacimiento
            elif tipo_identificacion_beneficiario == '12':
                tipo_identificacion_beneficiario = '04'  # Tarjeta de identidad
            elif tipo_identificacion_beneficiario == '13':
                tipo_identificacion_beneficiario = '01'  # Cedula de ciudadania
            elif tipo_identificacion_beneficiario == '22':
                tipo_identificacion_beneficiario = '02'  # Cedula de extranjeria
            elif tipo_identificacion_beneficiario == '31':
                tipo_identificacion_beneficiario = '03'  # NIT
            elif tipo_identificacion_beneficiario == '41':
                tipo_identificacion_beneficiario = '05'  # Pasaporte
            else:
                raise ValidationError(_('El tipo de documento del empleado '+payslip.contract_id.employee_id.name+' no es valido, por favor verificar.'))

            nit_beneficiario = nit_entidad = right(16 * '0' + payslip.contract_id.employee_id.identification_id, 16)
            # Inf Bancaria
            banco = ''
            cuenta_beneficiario = ''
            indicador_lugar_pago = ''
            tipo_transaccion = ''
            for bank in payslip.contract_id.employee_id.address_home_id.bank_ids:
                if bank.is_main:
                    banco = right(9 * '0' + bank.bank_id.bic, 9)
                    cuenta_beneficiario = right(16 * '0' + str(bank.acc_number).replace("-", ""), 16)
                    indicador_lugar_pago = 'S'
                    tipo_transaccion = 'CA' if bank.type_account == 'A' else 'CC'  # CC: Abono a cuenta corriente / CA: Abono a cuenta ahorros
                    tipo_transaccion = 'DP' if bank.type_account == 'DP' else tipo_transaccion  # DP: Daviplata
            if cuenta_beneficiario == '':
                raise ValidationError(
                    _('El empleado ' + payslip.contract_id.employee_id.name + ' no tiene configurada la información bancaria, por favor verificar.'))
            # Obtener valor de transacción
            valor_transacción = 18 * '0'
            valor_not_include = 0
            for line in payslip.line_ids:
                valor_not_include += line.total if line.salary_rule_id.not_include_flat_payment_file else 0
                if line.code == 'NET':
                    total_valor_transaccion = (total_valor_transaccion + line.total) - valor_not_include
                    total_valor_transaccion = 0 if total_valor_transaccion < 0 else total_valor_transaccion
                    val_write = line.total - valor_not_include
                    val_write = 0 if val_write < 0 else val_write
                    valor = str(val_write).split(".")  # Eliminar decimales
                    valor_transacción = right(16 * '0' + str(valor[0]), 16) +''+ right(2 * '0' + str(valor[1]), 2)

            content_line = '''%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s''' % (
            tipo_registro, nit_beneficiario, referencia, cuenta_beneficiario, tipo_transaccion, cod_banco,
            valor_transacción, talon, tipo_identificacion_beneficiario, validar_ach, resultado_proceso,
            mensaje_respuesta, valor_acumulado, fecha_aplicacion, oficina_recaudo, motivo, relleno)

            if cant_detalle == 1:
                detalle_content = content_line
            else:
                detalle_content = detalle_content + '\n' + content_line

        # ----------------------------------Generar archivo---------------------------------
        # Reemplazar valores del encabezado
        valor_total = str(total_valor_transaccion).split(".")  # Eliminar decimales
        encab_content_txt = encab_content_txt.replace("ValorTotalTraslados", right(16 * '0' + str(valor_total[0]), 16) +''+ right(2 * '0' + str(valor_total[1]), 2))
        encab_content_txt = encab_content_txt.replace("NumTraslados", right(6 * '0' + str(cant_detalle), 6))
        # Unir Encabezado y Detalle
        content_txt = encab_content_txt + '\n' + detalle_content

        # Retornar archivo
        return base64.encodebytes((content_txt).encode())

    # Lógica de Banco Bogotá excel
    def generate_flat_file_bogota_excel(self, obj_payslip):
        # Generar EXCEL
        filename = f'Plano de nómina del banco de Bogotá.xlsx'
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})
        # Columnas
        columns = ['Tipo Identificación Beneficiario', 'Nombre del Beneficiario', 'Número de Identificación Beneficiario', 'Tipo de Cuenta Destino', 'Número Cuenta Destino', 'Valor a Pagar',
                   'Código Entidad Financiera Destino','Referencia /Factura','Correo electrónico o E-mail','Mensaje a enviar',]
        sheet = book.add_worksheet('Dispersión de fondos')
        # Formato para fechas
        date_format = book.add_format({'num_format': 'dd/mm/yyyy'})
        # Agregar columnas
        aument_columns = 0
        for column in columns:
            sheet.write(0, aument_columns, column)
            aument_columns = aument_columns + 1
        # Agregar nominas
        aument_columns = 0
        aument_rows = 1
        #for employee in obj_payslip.employee_id.ids:
        for payslip in obj_payslip:
            # Tipo documento
            sheet.write(aument_rows, 0, payslip.employee_id.address_home_id.document_type)
            # Nombre
            sheet.write(aument_rows, 1, payslip.employee_id.name)
            # Identificación
            sheet.write(aument_rows, 2, payslip.employee_id.identification_id)
            # Tipo de cuenta
            banco = ''
            cuenta_beneficiario = ''
            tipo_cuenta = ''
            for bank in payslip.employee_id.address_home_id.bank_ids:
                if bank.is_main:
                    banco = bank.bank_id.bic
                    cuenta_beneficiario = str(bank.acc_number).replace("-", "")
                    tipo_cuenta = 'Ahorros' if bank.type_account == 'A' else 'Corriente'
            sheet.write(aument_rows, 3, tipo_cuenta)
            # Numero de cuenta
            sheet.write(aument_rows, 4, cuenta_beneficiario)
            #Valor
            valor = 0
            valor_not_include = 0
            for line in payslip.line_ids:
                valor_not_include += line.total if line.salary_rule_id.not_include_flat_payment_file else 0
                if line.code == 'NET':
                    valor = line.total - valor_not_include
                    valor = 0 if valor < 0 else valor
            sheet.write(aument_rows, 5, valor)
            #Codigo entidad financiera
            sheet.write(aument_rows, 6, banco)
            #Referencia/factura
            sheet.write(aument_rows, 7, '')
            #Correo electronico
            sheet.write(aument_rows, 8, payslip.employee_id.work_email)
            #A enviar
            sheet.write(aument_rows, 9, '')
            # Ajustar tamaño columna
            # sheet.set_column(aument_columns, aument_columns, width)
            aument_rows = aument_rows + 1
        # Convertir en tabla
        array_header_table = []
        for i in columns:
            dict = {'header': i}
            array_header_table.append(dict)

        sheet.add_table(0, 0, aument_rows - 1, len(columns) - 1,
                        {'style': 'Table Style Medium 2', 'columns': array_header_table})
        # Guadar Excel
        book.close()

        # self.write({
        #     'excel_file': base64.encodebytes(stream.getvalue()),
        #     'excel_file_name': filename,
        # })

        return base64.encodebytes(stream.getvalue())

    # Archivo plano patrimonio autonomo popular
    def generate_flat_file_popular_excel(self,obj_payslip):
        filename = f'Plano de patrimonio autonomo popular.xlsx'
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})

        # Columnas
        columns = ['Item', 'No. Factura', 'Tipo ID', 'Numero identificación', 'Nombre 1', 'Nombre 2', 'Apellido 1', 'Apellido 2',
                   'Concepto de pago', 'Valor bruto', 'Valor IVA', 'Retención en la fuente', 'Rete IVA', 'RETE ICA', 'Valor neto a girar',
                   'Valor retención en la fuente', 'Tipo de pago', 'Banco', 'No Cuenta', 'Tipo', 'Repetir causante',
                   'Tipo ID', 'Numero de identificación beneficiario', 'Nombre 1', 'Nombre 2', 'Apellido 1', 'Apellido 2', 'Concepto de pago']
        sheet = book.add_worksheet('Patrimonio autonomo popular')
        # Formato para fechas
        date_format = book.add_format({'num_format': 'dd/mm/yyyy'})
        # Agregar columnas
        aument_columns = 0
        for column in columns:
            sheet.write(0, aument_columns, column)
            aument_columns = aument_columns + 1
        # Agregar nominas
        aument_columns = 0
        aument_rows = 1
        cont_item = 1
        for payslip in obj_payslip:
            sheet.write(aument_rows, 0, cont_item)
            sheet.write(aument_rows, 1, self.payslip_id.name)
            sheet.write(aument_rows, 2, 'cédula')
            sheet.write(aument_rows, 3, payslip.employee_id.identification_id)
            sheet.write(aument_rows, 4, payslip.employee_id.address_home_id.firs_name if payslip.employee_id.address_home_id.firs_name!=False else '')
            sheet.write(aument_rows, 5, payslip.employee_id.address_home_id.second_name if payslip.employee_id.address_home_id.second_name!=False else '')
            sheet.write(aument_rows, 6, payslip.employee_id.address_home_id.first_lastname if payslip.employee_id.address_home_id.first_lastname!=False else '')
            sheet.write(aument_rows, 7, payslip.employee_id.address_home_id.second_lastname if payslip.employee_id.address_home_id.second_lastname!=False else '')
            sheet.write(aument_rows, 8, self.payslip_id.name)
            valor = 0
            valor_rtfte = 0
            valor_not_include = 0
            valor_totaldev,valor_totalded = 0,0
            for line in payslip.line_ids:
                valor_not_include += line.total if line.salary_rule_id.not_include_flat_payment_file else 0
                if line.code == 'NET':
                    valor = line.total - valor_not_include
                    valor = 0 if valor < 0 else valor
                if line.code == 'RETFTE001' or line.code == 'RETFTE_PRIMA001':
                    valor_rtfte = abs(line.total)
                    #valor_rtfte = 0 if valor < 0 else valor
                if line.code == 'TOTALDEV':
                    valor_totaldev = abs(line.total)
                    #valor_totaldev = 0 if valor < 0 else valor
                if line.code == 'TOTALDED':
                    valor_totalded = abs(line.total)
                    #valor_totalded = 0 if valor < 0 else valor
            sheet.write(aument_rows, 9, valor_totaldev)
            sheet.write(aument_rows, 10, '')
            sheet.write(aument_rows, 11, valor_totalded)
            sheet.write(aument_rows, 12, '')
            sheet.write(aument_rows, 13, '')
            sheet.write(aument_rows, 14, valor)#valor
            sheet.write(aument_rows, 15, valor_rtfte)  # valor
            sheet.write(aument_rows, 16, 'ACH')#
            banco = ''
            cuenta_beneficiario = ''
            tipo_cuenta = ''
            for bank in payslip.employee_id.address_home_id.bank_ids:
                if bank.is_main:
                    banco = bank.bank_id.name
                    cuenta_beneficiario = bank.acc_number
                    tipo_cuenta = 'CH' if bank.type_account == 'A' else 'CC'
            sheet.write(aument_rows, 17, banco)
            sheet.write(aument_rows, 18, cuenta_beneficiario)
            sheet.write(aument_rows, 19, tipo_cuenta)
            sheet.write(aument_rows, 20, '')#si
            sheet.write(aument_rows, 21, '')#Cédula
            sheet.write(aument_rows, 22, '')#payslip.employee_id.identification_id
            sheet.write(aument_rows, 23, '')#payslip.employee_id.address_home_id.firs_name if payslip.employee_id.address_home_id.firs_name!=False else ''
            sheet.write(aument_rows, 24, '')#payslip.employee_id.address_home_id.second_name if payslip.employee_id.address_home_id.second_name!=False else ''
            sheet.write(aument_rows, 25, '')#payslip.employee_id.address_home_id.first_lastname if payslip.employee_id.address_home_id.first_lastname!=False else ''
            sheet.write(aument_rows, 26, '')#payslip.employee_id.address_home_id.second_lastname if payslip.employee_id.address_home_id.second_lastname!=False else ''
            sheet.write(aument_rows, 27, '')#self.payslip_id.name
            aument_rows = aument_rows + 1
            cont_item = cont_item + 1
        # Convertir en tabla
        array_header_table = []
        for i in columns:
            dict = {'header': i}
            array_header_table.append(dict)

        sheet.add_table(0, 0, aument_rows - 1, len(columns) - 1,
                        {'style': 'Table Style Medium 2', 'columns': array_header_table})
        # Guadar Excel
        book.close()
        return base64.encodebytes(stream.getvalue())

    # Lógica de Banco Bogotá
    def generate_flat_file_bogota(self, obj_payslip):
        filler = ' '

        def left(s, amount):
            return s[:amount]

        def right(s, amount):
            return s[-amount:]
        # ----------------------------------Registro de Control----------------------------------
        tipo_registro_encab = '1'
        date_today = self.transmission_date
        fecha_pago = str(date_today.year) + right('00' + str(date_today.month), 2) + right('00' + str(date_today.day), 2)
        numero_registro = 'NumRegs'
        valor_total = 'ValorTotalRegs'
        # Inf Bancaria
        cuenta_principal = ''
        tipo_cuenta = ''
        for journal in self.journal_id:
            tipo_cuenta = '02' if self.journal_id.bank_account_id.type_account == 'A' else '01'  # 01: Cuenta corriente / 02: Cuenta ahorros
            cuenta_principal = right(17 * '0' + str(journal.bank_account_id.acc_number).replace("-", ""), 17)
        if cuenta_principal == '':
            raise ValidationError(_('No existe una cuenta bancaria configurada como dispersora de nómina, por favor verificar.'))
        nombre_entidad = left(self.company_id.partner_id.name + 40 * filler, 40)
        nit_empresa = right(11 * '0' + self.vat_payer + '' + str(self.company_id.partner_id.dv), 11)
        codigo_transaccion = '021'  # 021 pago nomina- TD plus y abono afc #022 pago provedores #023 pago Transferencias
        cod_ciudad = '0001' #right(17 * '0' + self.company_id.partner_id.x_city.code, 4)
        fecha_creacion = fecha_pago
        codigo_oficina = '999'
        tipo_identificacion_titular = 'N'
        espacios = filler*29
        valor_libranzas = 18*'0'
        espacios_two = filler*80

        encab_content_txt = '''%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s''' % (
        tipo_registro_encab, fecha_pago, numero_registro,valor_total ,tipo_cuenta,cuenta_principal,nombre_entidad,nit_empresa,
        codigo_transaccion,cod_ciudad,fecha_creacion,codigo_oficina,tipo_identificacion_titular,espacios,valor_libranzas,
        filler,filler,espacios_two)

        # ----------------------------------Registro del detalle----------------------------------
        det_content_txt = ''
        tipo_registro_det = '2'
        cant_detalle = 0
        total_valor_transaccion = 0

        for payslip in obj_payslip:
            cant_detalle = cant_detalle + 1

            # Tipo documento
            document_type = 'C'
            document_type = payslip.employee_id.address_home_id.document_type
            if document_type == '13':
                document_type = 'C'
            elif document_type == '12':
                document_type = 'T'
            elif document_type == '22':
                document_type = 'E'
            elif document_type == '31':
                document_type = 'N'
            elif document_type == '41':
                document_type = 'P'
            elif document_type == '44':
                document_type = 'E'
            else:
                raise ValidationError(
                    _('El empleado ' + payslip.contract_id.employee_id.name + ' no tiene tipo de documento valido, por favor verificar.'))
            nit_beneficiario = right(11 * '0' + payslip.contract_id.employee_id.identification_id, 11)
            nombre_beneficiario = left(payslip.contract_id.employee_id.name + 40 * ' ', 40)

            # Inf Bancaria
            tipo_transaccion = ''
            banco_destino = ''
            no_cuenta_beneficiario = ''
            for bank in payslip.employee_id.address_home_id.bank_ids:
                if bank.is_main:
                    tipo_transaccion = '02' if bank.type_account == 'A' else '01'  # 01: Abono a cuenta corriente / 02: Abono a cuenta ahorros
                    banco_destino = right(3 * '0' + bank.bank_id.bic, 3)
                    no_cuenta_beneficiario = left(str(bank.acc_number).replace("-", "") + 17 * ' ', 17)
            if no_cuenta_beneficiario == '':
                raise ValidationError(
                    _('El empleado ' + payslip.contract_id.employee_id.name + ' no tiene configurada la información bancaria, por favor verificar.'))

            # Obtener valor de transacción
            valor_transaccion = 16 * '0'
            valor_transaccion_decimal = 2 * '0'
            valor_not_include = 0
            for line in payslip.line_ids:
                valor_not_include += line.total if line.salary_rule_id.not_include_flat_payment_file else 0
                if line.code == 'NET':
                    total_valor_transaccion = (total_valor_transaccion + line.total) - valor_not_include
                    total_valor_transaccion = 0 if total_valor_transaccion < 0 else total_valor_transaccion
                    val_write = line.total - valor_not_include
                    val_write = 0 if val_write < 0 else val_write
                    valor = str(val_write).split(".")  # Eliminar decimales
                    valor_transaccion = right(16 * '0' + str(valor[0]), 16)
                    valor_transaccion_decimal = right(2 * '0' + str(valor[1]), 2)

            forma_de_pago = 'A'
            codigo_oficina = '000'
            cod_ciudad = '0001' #right(4 * '0' +  payslip.employee_id.address_home_id.x_city.code, 4)
            espacios = filler*80
            cero = '0'
            numbers = [temp for temp in payslip.number.split("/") if temp.isdigit()]
            num_factura = ''
            for i in numbers:
                num_factura = num_factura + str(i)
            num_factura = right('0' * 10 + num_factura, 10)
            informar = 'N'
            espacios_two = filler*8
            valor_libranza = 18*filler
            creditos = filler*11
            espacios_three = filler*11
            indicador = 'N'
            espacios_four = filler*8

            content_line = '''%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s''' % (
            tipo_registro_det,document_type,nit_beneficiario,nombre_beneficiario,tipo_transaccion,no_cuenta_beneficiario,
            valor_transaccion,valor_transaccion_decimal,forma_de_pago,codigo_oficina,banco_destino,cod_ciudad,espacios,
            cero,num_factura,informar,espacios_two,valor_libranza,creditos,espacios_three,indicador,espacios_four)
            if cant_detalle == 1:
                det_content_txt = content_line
            else:
                det_content_txt = det_content_txt + '\n' + content_line

        # Reemplazar valores del encabezado
        encab_content_txt = encab_content_txt.replace("NumRegs", right(5 * '0' + str(cant_detalle), 5))
        valor_total = str(total_valor_transaccion).split(".")  # Eliminar decimales
        encab_content_txt = encab_content_txt.replace("ValorTotalRegs", right(18 * '0' + str(valor_total[0]), 18))
        # Unir Encabezado, Detalle y Totales
        if det_content_txt == '':
            raise ValidationError(_('No existe información en las liquidaciones seleccionadas, por favor verificar.'))

        content_txt = encab_content_txt + '\n' + det_content_txt

        # Retornar archivo
        return base64.encodebytes((content_txt).encode())


    # Lógica de Plano de reglas no incluidas
    def generate_rule_not_included(self,obj_payslip):

        # Generar EXCEL
        filename = f'Plano de reglas no incluidas.xlsx'
        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})
        # Columnas
        columns = ['TIPO_DOCUMENTO', 'DOCUMENTO', 'PRODUCTO', 'IDENTIFICADOR', 'VALOR', 'FECHA']
        sheet = book.add_worksheet('Plano para Bono de peoplepass')
        # Formato para fechas
        date_format = book.add_format({'num_format': 'dd/mm/yyyy'})
        # Agregar columnas
        aument_columns = 0
        for column in columns:
            sheet.write(0, aument_columns, column)
            aument_columns = aument_columns + 1
        # Agregar nominas
        aument_columns = 0
        aument_rows = 1
        for payslip in obj_payslip:
            valor_not_include = 0
            for line in payslip.line_ids:
                valor_not_include += line.total if line.salary_rule_id.not_include_flat_payment_file else 0
            if valor_not_include == 0:
                pass
            else:
                #Tipo documento
                document_type = payslip.employee_id.address_home_id.document_type
                if document_type == '13':
                    document_type = 'CC'
                elif document_type == '12':
                    document_type = 'TI'
                elif document_type == '41':
                    document_type = 'PP'
                elif document_type == '22':
                    document_type = 'CE'
                elif record.document_type == '31':
                    document_type = 'NTN'
                sheet.write(aument_rows, 0, document_type)
                #Documento
                sheet.write(aument_rows, 1, payslip.employee_id.identification_id)
                #Producto
                sheet.write(aument_rows, 2, 'Bienestar')
                #Identificador
                sheet.write(aument_rows, 3, '-')
                #Valor
                sheet.write(aument_rows, 4, valor_not_include)
                #Fecha
                sheet.write_datetime(aument_rows, 5, fields.Date.today(), date_format)
                # Ajustar tamaño columna
                #sheet.set_column(aument_columns, aument_columns, width)
                aument_rows = aument_rows + 1
        # Convertir en tabla
        array_header_table = []
        for i in columns:
            dict = {'header': i}
            array_header_table.append(dict)

        sheet.add_table(0, 0, aument_rows - 1, len(columns) - 1,
                        {'style': 'Table Style Medium 2', 'columns': array_header_table})
        # Guadar Excel
        book.close()

        # self.write({
        #     'excel_file': base64.encodebytes(stream.getvalue()),
        #     'excel_file_name': filename,
        # })

        return base64.encodebytes(stream.getvalue())

    def generate_flat_file_bbva(self, obj_payslip):
        filler = ' '

        def left(s, amount):
            return s[:amount]

        def right(s, amount):
            return s[-amount:]

        det_content_txt = ''
        cant_detalle = 0

        for payslip in obj_payslip:
            cant_detalle = cant_detalle + 1
            # Tipo documento
            document_type = '01'
            document_type = payslip.employee_id.address_home_id.document_type
            if document_type == '13':
                document_type = '01'
            elif document_type == '12':
                document_type = '04'
            elif document_type == '22':
                document_type = '02'
            elif document_type == '31':
                document_type = '03'
            elif document_type == '41':
                document_type = '05'
            else:
                raise ValidationError(_('El empleado ' + payslip.contract_id.employee_id.name + ' no tiene tipo de documento valido, por favor verificar.'))
            nit_beneficiario = right(15 * '0' + payslip.contract_id.employee_id.identification_id, 15)
            codigo_nit = '0'
            for vat in payslip.employee_id.address_home_id.document_type:
                dig_verificacion = payslip.employee_id.address_home_id.dv
                if document_type == '31':
                    codigo_nit = dig_verificacion
            forma_pago = '1'
            banco_destino = ''
            for bank in payslip.contract_id.employee_id.address_home_id.bank_ids:
                if bank.is_main == True:
                    banco_destino = bank.bank_id.bic
            # oficina_receptora = '0000'
            # digito_verificacion = '00'
            # tipo_transaccion = ''
            # for bank in payslip.employee_id.address_home_id.bank_ids:
            #     if bank.is_main and banco_destino == '0013':
            #         tipo_transaccion = '0200' if bank.type_account == 'A' else '0100' # 0100: Abono a cuenta corriente / 0200: Abono a cuenta ahorros
            #     else:
            #         tipo_transaccion = '0000'
            cuenta = ''
            for bank in payslip.contract_id.employee_id.address_home_id.bank_ids:
                if bank.is_main == True and banco_destino == '0013':
                    cuenta = right(16 * '0' + (bank.acc_number[-16:]), 16)
                else:
                    cuenta = '0000000000000000'
            tipo_cuenta_nacham = ''
            for bank in payslip.employee_id.address_home_id.bank_ids:
                if bank.is_main == True and banco_destino != '0013':
                    tipo_cuenta_nacham = '02' if bank.type_account == 'A' else '01'  # 01: Abono a cuenta corriente / 02: Abono a cuenta ahorros
                elif banco_destino == '0013':
                    tipo_cuenta_nacham = '00'
            no_cuenta_nacham = ''
            for bank in payslip.contract_id.employee_id.address_home_id.bank_ids:
                if bank.is_main == True and banco_destino != '0013':
                    no_cuenta_nacham = left(str(bank.acc_number).replace("-", "") + 17 * ' ', 17)
                elif banco_destino == '0013':
                    no_cuenta_nacham = '00000000000000000'
            # Obtener valor de transacción
            total_valor_transaccion = 0
            valor_transaccion = 13 * '0'
            valor_transaccion_decimal = 2 * '0'
            valor_not_include = 0
            for line in payslip.line_ids:
                valor_not_include += line.total if line.salary_rule_id.not_include_flat_payment_file else 0
                if line.code == 'NET':
                    total_valor_transaccion = (total_valor_transaccion + line.total) - valor_not_include
                    total_valor_transaccion = 0 if total_valor_transaccion < 0 else total_valor_transaccion
                    val_write = line.total - valor_not_include
                    val_write = 0 if val_write < 0 else val_write
                    valor = str(val_write).split(".")  # Eliminar decimales
                    valor_transaccion = right(13 * '0' + str(valor[0]), 13)
                    valor_transaccion_decimal = right(2 * '0' + str(valor[1]), 2)
            fecha_mov = '00000000'
            codigo_oficina_pagadora = '0000'
            nombre_beneficiario = left(payslip.contract_id.employee_id.name + 36 * ' ' , 36)
            direccion_beneficiario = left(payslip.contract_id.employee_id.address_home_id.street + 36 * ' ', 36)
            direccion_beneficiario_dos = '                                   '
            email_beneficiario = '                                                 '
            concepto = left(self.description + 40 * ' ', 40)

            content_line = '''%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s''' % (
                document_type, nit_beneficiario, codigo_nit, forma_pago, banco_destino, cuenta,tipo_cuenta_nacham,
                no_cuenta_nacham,valor_transaccion,valor_transaccion_decimal,fecha_mov,codigo_oficina_pagadora,
                nombre_beneficiario,direccion_beneficiario,direccion_beneficiario_dos,email_beneficiario,concepto)

            if cant_detalle == 1:
                det_content_txt = content_line
            else:
                det_content_txt = det_content_txt + '\n' + content_line
        if det_content_txt == '':
            raise ValidationError(_('No existe información en las liquidaciones seleccionadas, por favor verificar.'))

        content_txt = det_content_txt

        # Retornar archivo
        return base64.encodebytes((content_txt).encode())

    #Ejecutar proceso
    def generate_flat_file(self):
        self.env['hr.payroll.flat.file.detail'].search([('flat_file_id','=',self.id)]).unlink()
        self.transmission_date = fields.Datetime.now()
        self.application_date = fields.Date.today()
        if self.flat_rule_not_included:
            file_base64 = False
            obj_payslip = self.env['hr.payslip']
            obj_payslip_tmp = self.env['hr.payslip']
            if self.source_information == 'lote':
                obj_payslip_tmp = self.env['hr.payslip'].search([('payslip_run_id', '=', self.payslip_id.id),
                                                                 ('employee_id.company_id', '=', self.company_id.id)])
            elif self.source_information == 'liquidacion':
                obj_payslip_tmp = self.env['hr.payslip'].search([('id', 'in', self.liquidations_ids.ids),
                                                                 ('employee_id.company_id', '=', self.company_id.id)])
            else:
                raise ValidationError(_('No se ha configurado origen de información.'))
            # Filtro por diario / Cuenta bancaria dispersora nómina
            for payslip in obj_payslip_tmp:
                count_bank_main = 0
                for bank in payslip.employee_id.address_home_id.bank_ids:
                    if bank.is_main == True:
                        count_bank_main += 1
                        obj_payslip += payslip
                if count_bank_main != 1:
                    raise ValidationError(_(f'El empleado {payslip.employee_id.name} no tiene configurado cuenta bancaria principal o tiene más de una, por favor verificar'))
            if len(obj_payslip) > 0:
                file_base64 = self.generate_rule_not_included(obj_payslip)
                if file_base64:
                    filename = 'Plano de reglas no incluidas.xlsx'
                    values_flat_file = {
                        'flat_file_id': self.id,
                        'journal_id': False,
                        'plane_type': 'not_include',
                        'txt_file': file_base64,
                        'txt_file_name': filename,
                    }
                    self.env['hr.payroll.flat.file.detail'].create(values_flat_file)
        else:
            type_flat_file = ['bancolombiasap','bancolombiapab','davivienda1','occired','avvillas1','bancobogota','popular','bbva']
            for type in type_flat_file:
                obj_payslip = self.env['hr.payslip']
                # Validaciones
                if self.payment_type != '225':
                    raise ValidationError(_('El tipo de pago seleccionado no esta desarrollado por ahora, seleccione otro por favor.'))
                # Definir díario principal
                obj_journal = self.env['account.journal'].search([('plane_type', '=', type)])
                for journal in obj_journal:
                    self.journal_id = journal if len(journal) > 0 else False
                    #Origen de la información
                    if self.journal_id:
                        obj_payslip = self.env['hr.payslip']
                        obj_payslip_tmp = self.env['hr.payslip']
                        if self.source_information == 'lote':
                            obj_payslip_tmp = self.env['hr.payslip'].search([('payslip_run_id', '=', self.payslip_id.id),
                                                                         ('employee_id.company_id', '=', self.company_id.id)])
                        elif self.source_information == 'liquidacion':
                            obj_payslip_tmp = self.env['hr.payslip'].search([('id', 'in', self.liquidations_ids.ids),
                                                                         ('employee_id.company_id', '=', self.company_id.id)])
                        else:
                            raise ValidationError(_('No se ha configurado origen de información.'))
                        #Filtro por diario / Cuenta bancaria dispersora nómina
                        for payslip in obj_payslip_tmp:
                            count_bank_main = 0
                            for bank in payslip.employee_id.address_home_id.bank_ids:
                                if bank.is_main == True:
                                    count_bank_main += 1
                                    if bank.payroll_dispersion_account.id == self.journal_id.id:
                                        obj_payslip += payslip
                            if count_bank_main != 1:
                                raise ValidationError(_(f'El empleado {payslip.employee_id.name} no tiene configurado cuenta bancaria principal o tiene más de una, por favor verificar'))

                    if len(obj_payslip) > 0:
                        #Ejecutar plano
                        file_base64 = False
                        file_base64_excel = False
                        if type == 'bancolombiasap':
                            file_base64 = self.generate_flat_file_sap(obj_payslip)
                        if type == 'bancolombiapab':
                            file_base64 = self.generate_flat_file_pab(obj_payslip)
                        if type == 'davivienda1':
                            file_base64 = self.generate_flat_file_davivienda(obj_payslip)
                        if type == 'occired':
                            file_base64 = self.generate_flat_file_occired(obj_payslip)
                        if type == 'avvillas1':
                            file_base64 = self.generate_flat_file_avvillas(obj_payslip)
                        if type == 'bbva':
                            file_base64 = self.generate_flat_file_bbva(obj_payslip)
                        if type == 'bancobogota':
                            file_base64 = self.generate_flat_file_bogota(obj_payslip)
                            file_base64_excel = self.generate_flat_file_bogota_excel(obj_payslip)
                        if type == 'popular':
                            file_base64_excel = self.generate_flat_file_popular_excel(obj_payslip)
                        #Guardar plano generado
                        if file_base64 or file_base64_excel:
                            filename = self.journal_id.name + ' - Archivo de Pago ' + str(self.description) + '.txt'
                            values_flat_file = {
                                'flat_file_id': self.id,
                                'journal_id': self.journal_id.id,
                                'plane_type': type,
                                'txt_file': file_base64 if file_base64 else False,
                                'txt_file_name': filename if file_base64 else False,
                                'excel_file': file_base64_excel if file_base64_excel else False,
                                'excel_file_name': self.journal_id.name + ' - Archivo de Pago ' + str(self.description) + '.xlsx' if file_base64_excel else False,
                            }
                            self.env['hr.payroll.flat.file.detail'].create(values_flat_file)
                            # Guardar en copia de seguridad
                            # if file_base64:
                            #     obj_backup = self.env['lavish.payroll.flat.file.backup']
                            #     values = {}
                            #     if self.source_information == 'lote':
                            #         values = {
                            #             'generation_date': fields.Date.today(),
                            #             'journal_id': self.journal_id.id,
                            #             'payment_type': self.payment_type,
                            #             'company_id': self.company_id.id,
                            #             'payslip_id': self.payslip_id.id,
                            #             'transmission_date': self.transmission_date,
                            #             'application_date': self.application_date,
                            #             'description': self.description,
                            #             'txt_file': file_base64,
                            #             'txt_file_name': filename
                            #         }
                            #     elif self.source_information == 'liquidacion':
                            #         values = {
                            #             'generation_date': fields.Date.today(),
                            #             'journal_id': self.journal_id.id,
                            #             'payment_type': self.payment_type,
                            #             'company_id': self.company_id.id,
                            #             'liquidations_ids': self.liquidations_ids.ids,
                            #             'transmission_date': self.transmission_date,
                            #             'application_date': self.application_date,
                            #             'description': self.description,
                            #             'txt_file': file_base64,
                            #             'txt_file_name': filename
                            #         }
                            #     else:
                            #         raise ValidationError(_('No se ha configurado origen de información.'))

                            #     obj_backup.create(values)
