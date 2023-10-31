# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

import base64
import datetime
#---------------------------Modelo para generar Archivo plano de pago de nómina-------------------------------#

class hr_payroll_flat_file(models.TransientModel):
    _name = 'hr.payroll.flat.file'
    _description = 'Archivo plano de pago de nómina'

    journal_id = fields.Many2one('account.journal', string='Diario', domain=[('is_payroll_spreader', '=', True)], required=True)    
    payment_type = fields.Selection([('225', 'Pago de Nómina')], string='Tipo de pago', required=True, default='225', readonly=True)
    company_id = fields.Many2one('res.company',string='Compañia', required=True, default=lambda self: self.env.company)
    vat_payer = fields.Char(string='NIT Pagador', store=True, readonly=True, related='company_id.partner_id.vat')
    payslip_id = fields.Many2one('hr.payslip.run',string='Lote de nómina', domain=[('definitive_plan', '=', False)])
    transmission_date = fields.Date(string="Fecha transmisión de lote", required=True, default=fields.Date.today())
    application_date = fields.Date(string="Fecha aplicación transacciones", required=True, default=fields.Date.today())
    description = fields.Char(string='Descripción', size=10, required=True)
    type_flat_file = fields.Selection([('sap', 'Bancolombia SAP'),
                                        ('pab', 'Bancolombia PAB'),
                                        ('occired','Occired')],'Tipo de archivo', default='sap') 
    source_information = fields.Selection([('lote', 'Por lote'),
                                          ('liquidacion', 'Por liquidaciones')],'Origen información', default='lote') 
    liquidations_ids= fields.Many2many('hr.payslip', string='Liquidaciones', domain=[('definitive_plan', '=', False),('payslip_run_id', '=', False)])                               
    
    txt_file = fields.Binary('TXT file')
    txt_file_name = fields.Char('TXT name', size=64)

    def name_get(self):
        result = []
        for record in self:            
            result.append((record.id, "Archivo de Pago - ".format(record.description)))
        return result

    def generate_flat_file_sap(self):
        filler = ' '
        def left(s, amount):
                return s[:amount]
            
        def right(s, amount):
            return s[-amount:]
        #Validaciones 
        if self.payment_type != '225':
            raise ValidationError(_('El tipo de pago seleccionado no esta desarrollado por ahora, seleccione otro por favor.'))
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

        if self.source_information == 'lote':
            obj_payslip = self.env['hr.payslip'].search([('payslip_run_id', '=', self.payslip_id.id),('employee_id.address_id','=',self.company_id.partner_id.id)])
        elif self.source_information == 'liquidacion':
            obj_payslip = self.env['hr.payslip'].search([('id', 'in', self.liquidations_ids.ids),('employee_id.address_id','=',self.company_id.partner_id.id)])
        else:
            raise ValidationError(_('No se ha configurado origen de información.'))
        
        for payslip in obj_payslip:
            cant_detalle = cant_detalle + 1
            self.validation_values(payslip.contract_id.employee_id)
            tipo_registro = '6'
            if payslip.contract_id.employee_id.permit_no:
                nit_beneficiario = right(15 * '0' + payslip.contract_id.employee_id.permit_no, 15)
            else:
                nit_beneficiario = right(15*'0'+payslip.contract_id.employee_id.identification_id,15)
            nombre_beneficiario = left(payslip.contract_id.employee_id.name+18*filler,18) 
            #Inf Bancaria
            banco = ''
            cuenta_beneficiario = ''
            indicador_lugar_pago = ''
            tipo_transaccion = ''
            for bank in payslip.contract_id.employee_id.address_home_id.bank_ids:
                if bank.is_main:
                    banco = right(9*'0'+str(bank.bank_id.bic),9)
                    cuenta_beneficiario = right(17*'0'+str(bank.acc_number).replace("-",""),17)
                    indicador_lugar_pago = 'S'
                    tipo_transaccion = '37' if bank.type_account == 'A' else '27' # 27: Abono a cuenta corriente / 37: Abono a cuenta ahorros 
            if cuenta_beneficiario == '':
                raise ValidationError(_('El empleado '+payslip.contract_id.employee_id.name+' no tiene configurada la información bancaria, por favor verificar.'))
            #Obtener valor de transacción 
            valor_transacción = 10*'0'
            for line in payslip.line_ids:
                if line.code == 'NET':
                    total_valor_transaccion = total_valor_transaccion + line.total
                    valor = str(line.total).split(".") # Eliminar decimales
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

        #Crear archivo
        filename= 'Archivo de Pago '+str(self.description)+'.txt'    
        self.write({
            'txt_file': base64.encodestring((content_txt).encode()),
            'txt_file_name': filename,
        })           

        #Guardar en copia de seguridad
        obj_backup = self.env['lavish.payroll.flat.file.backup']
        if self.payslip_id.id:
            values = {
                'generation_date':fields.Date.today(),
                'journal_id': self.journal_id.id,
                'payment_type': self.payment_type,
                'company_id': self.company_id.id,
                'payslip_id': self.payslip_id.id,
                'transmission_date': self.transmission_date,
                'application_date': self.application_date,
                'description': self.description,
                'txt_file': self.txt_file,
                'txt_file_name': self.txt_file_name
            }
        else:
            values = {
                'generation_date':fields.Date.today(),
                'journal_id': self.journal_id.id,
                'payment_type': self.payment_type,
                'company_id': self.company_id.id,                
                'transmission_date': self.transmission_date,
                'application_date': self.application_date,
                'description': self.description,
                'txt_file': self.txt_file,
                'txt_file_name': self.txt_file_name
            }
        obj_backup.create(values)

        #Descargar archivo plano
        action = {
                    'name': 'ArchivoPagos',
                    'type': 'ir.actions.act_url',
                    'url': "web/content/?model=hr.payroll.flat.file&id=" + str(self.id) + "&filename_field=txt_file_name&field=txt_file&download=true&filename=" + self.txt_file_name,
                    'target': 'self',
                }
        return action

    def generate_flat_file_pab(self):
        filler = ' '
        def left(s, amount):
                return s[:amount]
            
        def right(s, amount):
            return s[-amount:]
        #Validaciones 
        if self.payment_type != '225':
            raise ValidationError(_('El tipo de pago seleccionado no esta desarrollado por ahora, seleccione otro por favor.'))
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

        if self.source_information == 'lote':
            obj_payslip = self.env['hr.payslip'].search([('payslip_run_id', '=', self.payslip_id.id),('employee_id.address_id','=',self.company_id.partner_id.id)])
        elif self.source_information == 'liquidacion':
            obj_payslip = self.env['hr.payslip'].search([('id', 'in', self.liquidations_ids.ids),('employee_id.address_id','=',self.company_id.partner_id.id)])
        else:
            raise ValidationError(_('No se ha configurado origen de información.'))
        
        for payslip in obj_payslip:
            cant_detalle = cant_detalle + 1
            self.validation_values(payslip.contract_id.employee_id)
            tipo_registro = '6'
            if payslip.contract_id.employee_id.permit_no:
                nit_beneficiario = left(payslip.contract_id.employee_id.permit_no+15*' ',15)
            else:
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
            for line in payslip.line_ids:
                if line.code == 'NET':
                    total_valor_transaccion = total_valor_transaccion + line.total
                    valor = str(line.total).split(".") # Eliminar decimales
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

        #Crear archivo
        filename= 'Archivo de Pago '+str(self.description)+'.txt'    
        self.write({
            'txt_file': base64.encodestring((content_txt).encode()),
            'txt_file_name': filename,
        })           

        #Guardar en copia de seguridad
        obj_backup = self.env['lavish.payroll.flat.file.backup']
        if self.payslip_id.id:
            values = {
                'generation_date':fields.Date.today(),
                'journal_id': self.journal_id.id,
                'payment_type': self.payment_type,
                'company_id': self.company_id.id,
                'payslip_id': self.payslip_id.id,
                'transmission_date': self.transmission_date,
                'application_date': self.application_date,
                'description': self.description,
                'txt_file': self.txt_file,
                'txt_file_name': self.txt_file_name
            }
        else:
            values = {
                'generation_date':fields.Date.today(),
                'journal_id': self.journal_id.id,
                'payment_type': self.payment_type,
                'company_id': self.company_id.id,                
                'transmission_date': self.transmission_date,
                'application_date': self.application_date,
                'description': self.description,
                'txt_file': self.txt_file,
                'txt_file_name': self.txt_file_name
            }
        obj_backup.create(values)

        #Descargar archivo plano
        action = {
                    'name': 'ArchivoPagos',
                    'type': 'ir.actions.act_url',
                    'url': "web/content/?model=hr.payroll.flat.file&id=" + str(self.id) + "&filename_field=txt_file_name&field=txt_file&download=true&filename=" + self.txt_file_name,
                    'target': 'self',
                }
        return action
    
    #Lógica de occired
    def generate_flat_file_occired(self):
        filler = ' '
        def left(s, amount):
                return s[:amount]
            
        def right(s, amount):
            return s[-amount:]

        #Validaciones 
        if self.payment_type != '225':
            raise ValidationError(_('El tipo de pago seleccionado no esta desarrollado por ahora, seleccione otro por favor.'))
            
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

        if self.source_information == 'lote':
            obj_payslip = self.env['hr.payslip'].search([('payslip_run_id', '=', self.payslip_id.id),('employee_id.address_id','=',self.company_id.partner_id.id)])
        elif self.source_information == 'liquidacion':
            obj_payslip = self.env['hr.payslip'].search([('id', 'in', self.liquidations_ids.ids),('employee_id.address_id','=',self.company_id.partner_id.id)])
        else:
            raise ValidationError(_('No se ha configurado origen de información.'))

        #Agregar query
        for payslip in obj_payslip:
            cant_detalle = cant_detalle + 1
            consecutivo = right('0000'+str(cant_detalle),4)
            forma_de_pago = '3' # 1: Pago en Cheque  2: Pago abono a cuenta  - Banco de Occidente  3: Abono a cuenta otras entidades
            self.validation_values(payslip.contract_id.employee_id)
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
            if payslip.contract_id.employee_id.permit_no:
                nit_beneficiario = right(11*'0'+payslip.contract_id.employee_id.permit_no,11)
            else:
                nit_beneficiario = right(11*'0'+payslip.contract_id.employee_id.identification_id,11)
            nombre_beneficiario = left(payslip.contract_id.employee_id.name+30*' ',30)
            fecha_pago = str(self.application_date.year)+right('00'+str(self.application_date.month),2)+right('00'+str(self.application_date.day),2) 
            
            #Obtener valor de transacción 
            valor_transaccion = 13*'0'
            valor_transaccion_decimal = 2*'0'
            for line in payslip.line_ids:
                if line.code == 'NET':
                    total_valor_transaccion = total_valor_transaccion + line.total
                    valor = str(line.total).split(".") # Eliminar decimales
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
        
        #Crear archivo
        filename= 'Archivo de Pago '+str(self.description)+'.txt'    
        self.write({
            'txt_file': base64.encodestring((content_txt).encode()),
            'txt_file_name': filename,
        })           

        #Guardar en copia de seguridad
        obj_backup = self.env['lavish.payroll.flat.file.backup']
        if self.payslip_id.id:
            values = {
                'generation_date':fields.Date.today(),
                'journal_id': self.journal_id.id,
                'payment_type': self.payment_type,
                'company_id': self.company_id.id,
                'payslip_id': self.payslip_id.id,
                'transmission_date': self.transmission_date,
                'application_date': self.application_date,
                'description': self.description,
                'txt_file': self.txt_file,
                'txt_file_name': self.txt_file_name
            }
        else:
            values = {
                'generation_date':fields.Date.today(),
                'journal_id': self.journal_id.id,
                'payment_type': self.payment_type,
                'company_id': self.company_id.id,                
                'transmission_date': self.transmission_date,
                'application_date': self.application_date,
                'description': self.description,
                'txt_file': self.txt_file,
                'txt_file_name': self.txt_file_name
            }
        obj_backup.create(values)

        #Descargar archivo plano
        action = {
                    'name': 'ArchivoPagos',
                    'type': 'ir.actions.act_url',
                    'url': "web/content/?model=hr.payroll.flat.file&id=" + str(self.id) + "&filename_field=txt_file_name&field=txt_file&download=true&filename=" + self.txt_file_name,
                    'target': 'self',
                }
        return action       

    def validation_values(self,obj_employee):
        if not obj_employee.identification_id:
            raise ValidationError(_('El empleado ' + obj_employee.name + ' no tiene configurado un número de identificación, por favor verificar.'))
        if not obj_employee.work_email:
            raise ValidationError(_('El empleado ' + obj_employee.name + ' no tiene configurado el correo electronico, por favor verificar.'))
        for bank in obj_employee.address_home_id.bank_ids:
            if bank.is_main:
                if not bank.type_account:
                    raise ValidationError(_('El empleado ' + obj_employee.name + ' no tiene configurado un tipo de cuenta bancaria, por favor verificar.'))
                if not bank.bank_id:
                    raise ValidationError(_('El empleado ' + obj_employee.name + ' no tiene configurado banco, por favor verificar.'))
                if not bank.bank_id.bic:
                    raise ValidationError(_('El banco ' + bank.bank_id.name + ' no tiene configurado código, por favor verificar.'))
                if not bank.acc_number:
                    raise ValidationError(_('El empleado ' + obj_employee.name + ' no tiene configurado un número de cuenta bancaria, por favor verificar.'))

    def generate_flat_file(self):
        if self.type_flat_file == 'sap':
            return self.generate_flat_file_sap()
        if self.type_flat_file == 'pab':
            return self.generate_flat_file_pab()
        if self.type_flat_file == 'occired':
            return self.generate_flat_file_occired()
