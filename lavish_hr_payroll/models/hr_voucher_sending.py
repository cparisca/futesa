# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import ValidationError
from odoo import registry as registry_get
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

import odoo
import base64
import threading
import logging

_logger = logging.getLogger(__name__)
#---------------------------Modelo para generar Archivo plano de pago de nómina-------------------------------#

class mail_mail(models.Model):
    _inherit = 'mail.mail'

    payroll_voucher = fields.Boolean(string='Email para comprobante de nómina')
    payroll_voucher_id = fields.Many2one('hr.voucher.sending', string='Ejecución comprobantes de nómina')

class hr_voucher_sending_failed(models.Model):
    _name = 'hr.voucher.sending.failed'
    _description = 'Ejecución comprobantes de nómina Fallidos'
    
    voucher_id = fields.Many2one('hr.voucher.sending', 'Ejecución comprobantes')
    payslip_id = fields.Many2one('hr.payslip',string='Nómina')    
    employee_id = fields.Many2one(related='payslip_id.employee_id', string='Empleado')
    description = fields.Char('Mensaje')

class hr_voucher_sending(models.Model):
    _name = 'hr.voucher.sending'
    _description = 'Ejecución comprobantes de nómina'

    send_type = fields.Selection([('send', 'Enviar por correo electrónico')], string='Proceso', default='send',required=True)
    generation_type = fields.Selection([('lote', 'Por lote'),
                                        ('individual', 'Por Empleado')], string='Tipo', default='lote', required=True)
    #Campo Lote
    payslip_run_id = fields.Many2one('hr.payslip.run',string='Lote de nómina')    
    #Campos Empleados
    employee_id = fields.Many2one('hr.employee',string='Empleado')    
    payslip_id = fields.Many2one('hr.payslip',string='Nómina', domain="[('employee_id','=',[employee_id])]")
        
    #Inf Adicional Correo
    subject = fields.Char(string='Asunto')    
    description = fields.Text(string='Cuerpo del correo') 

    #Envios
    mail_mail_ids = fields.One2many('mail.mail','payroll_voucher_id','Correos electrónicos')
    #Envios fallidos
    vouchers_failed_ids = fields.One2many('hr.voucher.sending.failed', 'voucher_id','Envíos fallidos')

    #Campo de control
    txt_status_process = fields.Text(string='Estado del proceso')

    def name_get(self):
        result = []
        for record in self: 
            if record.payslip_run_id:
                result.append((record.id, "Comprobantes de nómina - ".format(record.payslip_run_id.name)))
            else:
                result.append((record.id, "Comprobantes de nómina - ".format(record.payslip_id.name)))
        return result

    def create_document_inmemory(self,records):
        with odoo.api.Environment.manage():
            registry = odoo.registry(self._cr.dbname)
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                _logger.info(f'(START) HILO/REGISTRO - Envio de comprobantes, cantidad: {len(records)}')
                for payslip in records:
                    obj_payslip = env['hr.payslip'].search([('id', '=', payslip)])
                    try:
                        report = obj_payslip.struct_id.report_id
                        pdf_content, content_type = report._render_qweb_pdf(obj_payslip.id)
                        pdf_name = obj_payslip.struct_id.name +' - '+obj_payslip.employee_id.name+' - '+str(obj_payslip.date_to) + '.pdf'

                        email_vals = {}
                        identificacion  = obj_payslip.employee_id.identification_id
                        nombre_empleado = obj_payslip.employee_id.name
                        correo_envio    = obj_payslip.employee_id.work_email
                        # body message
                        message = "Estimado "+ nombre_empleado + "<br/><br/>"
                        message += "Adjunto encontrará la información de la última liquidación y pago de su nómina.<br/><br/><br/>"
                        message += "Por favor no responda este correo, esto es un mensaje automático."
                        pdf_content = base64.b64encode(pdf_content)

                        data_attach = {'name':"Comprobante_nomina_"+identificacion+"_"+obj_payslip.name+".pdf", 'type':'binary', 'datas':pdf_content,'res_name':pdf_name,'store_fname':pdf_name,'res_model':'hr.payslip','res_id':obj_payslip.id}
                        atts_id = env['ir.attachment'].create(data_attach)
                        if atts_id:
                            email_vals.update({'subject':self.subject,
                                                'email_to': correo_envio,
                                                'email_from': self.env.user.email, 
                                                'body_html':message.encode('utf-8'),
                                                'payroll_voucher': True,
                                                'payroll_voucher_id': self.id,
                                                'attachment_ids': [(6, 0, [atts_id.id])] })
                            # create and send email
                            if email_vals:
                                email_id = env['mail.mail'].create(email_vals)
                                if email_id:
                                    email_id.send()                    
                    except Exception as error:
                        values = {
                            'voucher_id': self.id,
                            'payslip_id': obj_payslip.id,
                            'description': str(e.args[0])
                        }
                        env['hr.voucher.sending.failed'].create(values)
                _logger.info(f'(END) HILO/REGISTRO - Envio de comprobantes, cantidad: {len(records)}')

    def generate_voucher(self):
        self.env['hr.voucher.sending.failed'].search([('voucher_id', '=', self.id)]).unlink()
        date_start_process = datetime.now()
        date_finally_process = datetime.now()
        array_thread = []
        if self.generation_type == 'lote':
            obj_payslip = self.env['hr.payslip'].search([('payslip_run_id', '=', self.payslip_run_id.id)])
            #Guardar las liquidaciones en un arreglo en lotes de 50
            payslips_array, i, j = [], 0 , 100
            while i <= len(obj_payslip):                
                payslips_array.append(obj_payslip[i:j].ids)
                i = j
                j += 100
            #Enviar comprobantes en los lotes ejecutados
            for send in payslips_array:
                t = threading.Thread(target=self.create_document_inmemory, args=(send,))
                array_thread.append(t)
                t.start()

            for hilo in array_thread:
                hilo.join()
        else:
            send = [self.payslip_id.id]
            t = threading.Thread(target=self.create_document_inmemory, args=(send,))
            array_thread.append(t)
            t.start()

            for hilo in array_thread:
                hilo.join()

        date_finally_process = datetime.now()
        time_process = date_finally_process - date_start_process
        time_process = time_process.seconds / 60
        print(time_process)
        self.txt_status_process = 'Tiempo del proceso: '+ str(time_process) + ' \n El o los correos seran enviados en su totalidad en las próximas 24 horas.'

    def generate_voucher_failed(self):
        obj_payslip = self.env['hr.payslip'].search([('id', 'in', self.vouchers_failed_ids.payslip_id.ids)])
        date_start_process = datetime.now()
        date_finally_process = datetime.now()
        array_thread = []
        payslips_array, i, j = [], 0 , 50            
        while i <= len(obj_payslip):                
            payslips_array.append(obj_payslip[i:j].ids)
            i = j
            j += 50     

        self.env['hr.voucher.sending.failed'].search([('voucher_id', '=', self.id)]).unlink()
        #Enviar comprobantes en los lotes ejecutados
        i = 1
        for send in payslips_array:
            #msg = 'Enviando Comprobantes | Parte '+str(i)+' de '+str(len(payslips_array))+' | Total de comprobantes: '+str(len(obj_payslip))
            t = threading.Thread(target=self.create_document_inmemory, args=(send,))                
            t.start()
            array_thread.append(t)
            i += 1

        for hilo in array_thread:
            hilo.join()

        date_finally_process = datetime.now()
        time_process = date_finally_process - date_start_process
        time_process = time_process.seconds / 60
        print(time_process)                 
        




    
    
