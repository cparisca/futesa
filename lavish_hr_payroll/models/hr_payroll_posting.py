# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

import base64
import datetime
#---------------------------Modelo para contabilizar el pago de nómina-------------------------------#

class hr_payroll_posting_account_move(models.Model):
    _name = 'hr.payroll.posting.account.move'
    _description = 'Pago contabilización de nomina - Movimientos Contables'

    payroll_posting = fields.Many2one('hr.payroll.posting',string='Contabilización', required=True)
    journal_id = fields.Many2one('account.journal', string='Diario', domain=[('is_payroll_spreader', '=', True)])
    move_id = fields.Many2one('account.move', string='Movimiento Contable', readonly=True)

class hr_payroll_posting_distribution(models.Model):
    _name = 'hr.payroll.posting.distribution'
    _description = 'Pago contabilización de nomina - distribución'

    payroll_posting = fields.Many2one('hr.payroll.posting',string='Contabilización', required=True)
    partner_id = fields.Many2one('res.company',string='Ubicación laboral', required=True)
    account_id = fields.Many2one('account.account',string='Cuenta', required=True)

class hr_payroll_posting(models.Model):
    _name = 'hr.payroll.posting'
    _description = 'Pago contabilización de nomina'
    _rec_name = 'description'

    payment_type = fields.Selection([('225', 'Pago de Nómina')], string='Tipo de pago', required=True, default='225', readonly=True)
    journal_id = fields.Many2one('account.journal', string='Diario', domain=[('is_payroll_spreader', '=', True)])
    company_id = fields.Many2one('res.company',string='Compañia', required=True, default=lambda self: self.env.company)
    vat_payer = fields.Char(string='NIT Pagador', readonly=True, related='company_id.partner_id.vat')
    payslip_id = fields.Many2one('hr.payslip.run',string='Lote de nómina')
    description = fields.Char(string='Descripción', required=True) 
    state = fields.Selection([('draft', 'Borrador'),('done', 'Hecho')], string='Estado', default='draft')
    source_information = fields.Selection([('lote', 'Por lote'),
                                          ('liquidacion', 'Por liquidaciones')],'Origen información', default='lote') 
    liquidations_ids= fields.Many2many('hr.payslip', string='Liquidaciones')
    payroll_posting_distribution_ids = fields.One2many('hr.payroll.posting.distribution', 'payroll_posting',string='Distribución')
    payroll_posting_account_move_ids = fields.One2many('hr.payroll.posting.account.move', 'payroll_posting',string='Movimientos Contables')
    disaggregate_counterparty = fields.Boolean(string='¿Desea desagregar la contrapartida?')

    def payroll_posting(self):
        type_flat_file = ['bancolombiasap', 'bancolombiapab', 'davivienda1', 'occired', 'avvillas1', 'bancobogota','popular','bbva']
        value_total_not_include = 0
        line_ids_not_include = []
        for type in type_flat_file:
            obj_payslip = self.env['hr.payslip']
            # Validaciones
            if self.payment_type != '225':
                raise ValidationError(
                    _('El tipo de pago seleccionado no esta desarrollado por ahora, seleccione otro por favor.'))
            # Definir díario principal
            obj_journal = self.env['account.journal'].search([('plane_type', '=', type)])
            for journal in obj_journal:
                self.journal_id = journal if len(journal) > 0 else False
                #Origen de la información
                if self.journal_id:
                    #---------------------------CONTABILIZACIÓN-------------------------------------------
                    #Inicializar variables
                    debit_account_id = False
                    credit_account_id = False
                    line_ids = []
                    debit_sum = 0.0
                    move_dict = {
                                'company_id': self.company_id.id,
                                'ref': self.description,
                                'journal_id': self.journal_id.id,
                                'date': fields.Date.today(),
                            }
                    #Origen de la Información
                    obj_payslip = self.env['hr.payslip']
                    obj_payslip_tmp = self.env['hr.payslip']
                    if self.source_information == 'lote':
                        obj_payslip_tmp = self.env['hr.payslip'].search([('payslip_run_id', '=', self.payslip_id.id),
                                                                         ('employee_id.company_id', '=',
                                                                          self.company_id.id)])
                    elif self.source_information == 'liquidacion':
                        obj_payslip_tmp = self.env['hr.payslip'].search([('id', 'in', self.liquidations_ids.ids),
                                                                         ('employee_id.company_id', '=',
                                                                          self.company_id.id)])
                    else:
                        raise ValidationError(_('No se ha configurado origen de información.'))
                    # Filtro por diario / Cuenta bancaria dispersora nómina
                    for payslip in obj_payslip_tmp:
                        count_bank_main = 0
                        for bank in payslip.employee_id.address_home_id.bank_ids:
                            if bank.is_main == True:
                                count_bank_main += 1
                                if bank.payroll_dispersion_account.id == self.journal_id.id:
                                    obj_payslip += payslip
                        if count_bank_main != 1:
                            raise ValidationError(
                                _(f'El empleado {payslip.employee_id.name} no tiene configurado cuenta bancaria principal o tiene más de una, por favor verificar'))

                    if len(obj_payslip) > 0:
                        dict_distribution = {}
                        for payslip in obj_payslip:
                            # ------------------PASO 1 | Obtener cuentas contables del proceso----------------------------------
                            # Debito - se obtiene de la regla Neto
                            struct_id = 0
                            struct_id = payslip.struct_id.id
                            obj_rule_neto = self.env['hr.salary.rule'].search([('code', '=', 'NET'), ('struct_id', '=', struct_id)])
                            if len(obj_rule_neto) == 0:
                                struct_id = self.env['hr.payroll.structure'].search([('process', '=', 'nomina')],limit=1).id
                                obj_rule_neto = self.env['hr.salary.rule'].search([('code', '=', 'NET'), ('struct_id', '=', struct_id)])
                            for contab in obj_rule_neto.salary_rule_accounting:
                                if contab.company.id == self.company_id.id:
                                    debit_account_id = contab.debit_account.id if contab.debit_account else contab.credit_account.id
                            # Credito - se obtiene del diario seleccionado
                            credit_account_id = self.journal_id.default_account_id.id  # if self.journal_id.default_account_id else self.journal_id.default_account_id.id
                            # Validar cuentas
                            if not debit_account_id:
                                raise ValidationError(_('No se ha configurado la cuenta contable para la regla salarial Neto.'))
                            if not credit_account_id:
                                raise ValidationError(_('No se ha configurado la cuenta contable para el diario ' + str(self.journal_id.name) + '.'))
                            # ------------------PASO 2 | Obtener las lineas del debito (Valor Neto x Empleado)----------------------------------
                            value = payslip.line_ids.filtered(lambda line: line.code == 'NET').total
                            value = value if value > 0 else 0
                            value_not_include = sum([i.total for i in payslip.line_ids.filtered(lambda line: line.salary_rule_id.not_include_flat_payment_file == True)])
                            value_diff_account = sum([i.total for i in payslip.line_ids.filtered(lambda line: line.salary_rule_id.account_id_cxp)])
                            if value_not_include > 0:
                                value = value - value_not_include
                                value = 0 if value < 0 else value
                                value_total_not_include += value_not_include
                            lst_diff_account_debit = []
                            if value_diff_account > 0:
                                value = value - value_diff_account
                                value = 0 if value < 0 else value
                                for diff in payslip.line_ids.filtered(lambda line: line.salary_rule_id.account_id_cxp):
                                    lst_diff_account_debit.append({
                                        'name': self.description + ' | ' + payslip.employee_id.name + ' | '+ diff.salary_rule_id.name,
                                        'partner_id': payslip.employee_id.address_home_id.id,
                                        'account_id': diff.salary_rule_id.account_id_cxp.id,
                                        'journal_id': self.journal_id.id,
                                        'date': fields.Date.today(),
                                        'debit': diff.total,
                                        'credit': 0,
                                        # 'analytic_account_id': analytic_account_id,
                                    })
                                #if value - value_diff_account >= 0:
                                #    value = value - value_diff_account
                                #    value = 0 if value < 0 else value
                                #else:
                                #    value = abs(value - value_diff_account)
                                #    debit_account_id = account_id_cxp.id
                            if not payslip.employee_id.address_home_id.id:
                                raise ValidationError(_('El empleado '+payslip.employee_id.name+' no tiene un tercero asociado, por favor verificar.'))
                            line_debit = {
                                'name': self.description + ' | ' + payslip.employee_id.name,
                                'partner_id': payslip.employee_id.address_home_id.id,
                                'account_id': debit_account_id,
                                'journal_id': self.journal_id.id,
                                'date': fields.Date.today(),
                                'debit': value,
                                'credit': 0,
                                #'analytic_account_id': analytic_account_id,
                            }
                            if value_not_include > 0:
                                line_debit_not_include = {
                                    'name': self.description + ' | ' + payslip.employee_id.name,
                                    'partner_id': payslip.employee_id.address_home_id.id,
                                    'account_id': self.company_id.payroll_peoplepass_debit_account_id.id,
                                    'journal_id': self.company_id.payroll_peoplepass_journal_id.id,
                                    'date': fields.Date.today(),
                                    'debit': value_not_include,
                                    'credit': 0,
                                    # 'analytic_account_id': analytic_account_id,
                                }
                                line_ids_not_include.append(line_debit_not_include)

                            dict_distribution[payslip.employee_id.address_id.id] = dict_distribution.get(payslip.employee_id.address_id.id, 0)+value

                            debit_sum = debit_sum + value + value_diff_account
                            line_ids.append(line_debit)
                            for diff_line in lst_diff_account_debit:
                                line_ids.append(diff_line)
                            if self.disaggregate_counterparty == True:
                                line_credit = {
                                    'name': self.description + ' | ' + payslip.employee_id.name,
                                    'partner_id': self.company_id.partner_id.id,
                                    'account_id': credit_account_id,
                                    'journal_id': self.journal_id.id,
                                    'date': fields.Date.today(),
                                    'debit': 0,
                                    'credit': value,
                                    # 'analytic_account_id': analytic_account_id,
                                }
                                line_ids.append(line_credit)
                                if value_not_include > 0:
                                    line_credit_not_include = {
                                        'name': self.description + ' | ' + payslip.employee_id.name,
                                        'partner_id': self.company_id.partner_id.id,
                                        'account_id': self.company_id.payroll_peoplepass_credit_account_id.id,
                                        'journal_id': self.company_id.payroll_peoplepass_journal_id.id,
                                        'date': fields.Date.today(),
                                        'debit': 0,
                                        'credit': value_not_include,
                                        # 'analytic_account_id': analytic_account_id,
                                    }
                                    line_ids_not_include.append(line_credit_not_include)

                        #------------------PASO 3 | Obtener las linea del credito----------------------------------
                        if self.disaggregate_counterparty == False:
                            if len(self.payroll_posting_distribution_ids) > 0:
                                for distribution in self.payroll_posting_distribution_ids:
                                    line_credit = {
                                            'name': self.description,
                                            'partner_id': distribution.partner_id.partner_id.id,
                                            'account_id': distribution.account_id.id,
                                            'journal_id': self.journal_id.id,
                                            'date': fields.Date.today(),
                                            'debit': 0,
                                            'credit': dict_distribution.get(distribution.partner_id.partner_id.id, 0),
                                            #'analytic_account_id': analytic_account_id,
                                        }
                                    line_ids.append(line_credit)
                            else:
                                line_credit = {
                                        'name': self.description,
                                        'partner_id': self.company_id.partner_id.id,
                                        'account_id': credit_account_id,
                                        'journal_id': self.journal_id.id,
                                        'date': fields.Date.today(),
                                        'debit': 0,
                                        'credit': debit_sum,
                                        #'analytic_account_id': analytic_account_id,
                                    }
                                line_ids.append(line_credit)

                        move_dict['line_ids'] = [(0, 0, line_vals) for line_vals in line_ids]
                        move = self.env['account.move'].create(move_dict)
                        self.env['hr.payroll.posting.account.move'].create({
                            'payroll_posting':self.id,
                            'journal_id':self.journal_id.id,
                            'move_id':move.id
                        })
        if value_total_not_include > 0:
            if not self.company_id.payroll_peoplepass_journal_id.id:
                raise ValidationError(_('Debe configurar el diario para las reglas no incluidas, por favor verificar.'))
            if not self.company_id.payroll_peoplepass_debit_account_id.id:
                raise ValidationError(_('Debe configurar la cuenta débito para las reglas no incluidas, por favor verificar.'))
            if not self.company_id.payroll_peoplepass_credit_account_id.id:
                raise ValidationError(_('Debe configurar la cuenta crédito para las reglas no incluidas, por favor verificar.'))

            move_dict = {
                'company_id': self.company_id.id,
                'ref': self.description,
                'journal_id': self.company_id.payroll_peoplepass_journal_id.id,
                'date': fields.Date.today(),
            }
            if self.disaggregate_counterparty == False:
                line_credit_not_include = {
                    'name': self.description,
                    'partner_id': self.company_id.partner_id.id,
                    'account_id': self.company_id.payroll_peoplepass_credit_account_id.id,
                    'journal_id': self.company_id.payroll_peoplepass_journal_id.id,
                    'date': fields.Date.today(),
                    'debit': 0,
                    'credit': value_total_not_include,
                    # 'analytic_account_id': analytic_account_id,
                }
                line_ids_not_include.append(line_credit_not_include)
            move_dict['line_ids'] = [(0, 0, line_vals) for line_vals in line_ids_not_include]
            move = self.env['account.move'].create(move_dict)
            self.env['hr.payroll.posting.account.move'].create({
                'payroll_posting': self.id,
                'journal_id': self.company_id.payroll_peoplepass_journal_id.id,
                'move_id': move.id
            })

        if self.source_information == 'lote':
            self.payslip_id.write({'definitive_plan':True})
        elif self.source_information == 'liquidacion':
            for liq in self.liquidations_ids:
                liq.write({'definitive_plan':True})
        self.write({'state': 'done'})

    def payroll_rever_posting(self):
        for moves in self.payroll_posting_account_move_ids:
            self.env['account.move'].search([('id', '=', moves.move_id.id)]).unlink()
            moves.unlink()
        if self.source_information == 'lote':
            self.payslip_id.write({'definitive_plan':False})
        elif self.source_information == 'liquidacion':
            for liq in self.liquidations_ids:
                liq.write({'definitive_plan':False})
        self.write({'state': 'draft'})

    @api.constrains('payslip_id','liquidations_ids')
    def _check_uniq_payslip_id(self):  
        for record in self:
            obj_lote = False
            obj_liq = False
            if record.source_information == 'lote':
                obj_lote = self.env['hr.payroll.posting'].search([('payslip_id','=',record.payslip_id.id),('id','!=',record.id)])
            if record.source_information == 'liquidacion':
                obj_liq = self.env['hr.payroll.posting'].search([('liquidations_ids','in',record.liquidations_ids.ids),('id','!=',record.id)])

            if obj_lote or obj_liq:
                raise ValidationError(_('Ya existe un pago de contabilización para este lote/liquidación, por favor verificar'))  

    def unlink(self):
        if any(self.filtered(lambda posting: posting.state not in ('draft'))):
            raise ValidationError(_('No se puede eliminar una contabilización del pago en estado hecho!'))
        return super(hr_payroll_posting, self).unlink()