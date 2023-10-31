

from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError

from datetime import datetime

#MOVIMIENTO CONTABLE ENCABEZADO

class account_move(models.Model):
    _inherit = 'account.move'

    supplier_invoice_number = fields.Char(string='Nº de factura del proveedor',help="La referencia de esta factura proporcionada por el proveedor.", copy=False)
    supplier_invoice_attachment = fields.Many2one('documents.document',string="Soporte") #fields.Binary(string="Soporte")
    iva_amount = fields.Float('Valor IVA', compute='_compute_amount_iva', store=True)
    tax_base_amount = fields.Float('Valor Base Impuestos', compute='_compute_tax_base_amount', store=True)
    l10n_co_edi_type = fields.Selection([('1', 'Factura de venta'),
                                        ('2', 'Factura de exportación'),
                                        ('3', 'Notas electrónicas'),
                                        ('4', 'Factura de contingencia'),
                                        ], string='Tipo de Documento')
    accounting_closing_id = fields.Many2one('annual.accounting.closing', string='Cierre contable anual', ondelete='cascade')
    is_invoice_ref = fields.Boolean('No referencia factura', default=False)
    move_ref_id = fields.Many2one('account.move', string='Factura a rectificar', domain="[('state', '=', 'posted'),('move_type', '=', 'out_invoice')]")

    @api.onchange('move_ref_id')
    def _get_entities(self):
        for record in self:
            if record.move_ref_id.name:
                record.ref = 'Reversión de: ' + record.move_ref_id.name

    # # Borrar
    # def button_process_edi_web_services(self):
    #     return

    # supplier_invoice_attachment_name = fields.Char(string="Soporte Filename")
    @api.depends('line_ids', 'invoice_line_ids')
    def _compute_amount_iva(self):
        iva_amount = 0

        if self.invoice_line_ids.tax_id:
            obj_taxes = self.env['account.tax'].search([('name', 'ilike', 'IVA')])

            percent = obj_taxes[0].amount

            for lines in self.invoice_line_ids:
                for taxes in lines.tax_ids:
                    if taxes.ids[0] in obj_taxes.ids:
                        iva_amount += lines.price_subtotal * percent / 100

        self.iva_amount = iva_amount

    @api.depends('line_ids', 'invoice_line_ids')
    def _compute_tax_base_amount(self):
        for record in self:
            tax_base_amount = 0

            if record.invoice_line_ids.tax_id:
                for lines in record.invoice_line_ids:
                    if tax_base_amount > 0:
                        break

                    # for taxes in lines.tax_ids:
                    #     if not taxes.l10n_co_edi_type.retention:
                    #         tax_base_amount = record.amount_untaxed
                    #         break

            record.tax_base_amount = tax_base_amount

    @api.constrains('line_ids','invoice_line_ids')
    def _check_line_ids(self):
        for record in self:
            for lines in record.line_ids:
                # if lines.required_partner and not lines.partner_id:
                    # raise ValidationError(_(str(lines.ref)+' - La cuenta "' + lines.account_id.name + '" obliga un tercero y este no ha sido digitado. Por favor verifique!'))

                if 'stock_move_id' in self.env['account.move']._fields:
                    if lines.required_analytic_account and not lines.analytic_account_id and not record.stock_move_id.picking_id:
                        if lines.price_total > 0:
                            raise ValidationError(_(str(lines.ref)+' - La cuenta "' + lines.account_id.name + '" obliga cuenta analítica y esta no ha sido digitada. Por favor verifique!'))
                else:
                    if lines.required_analytic_account and not lines.analytic_account_id:
                        if lines.price_total > 0:
                            raise ValidationError(_(str(lines.ref)+' - La cuenta "' + lines.account_id.name + '" obliga cuenta analítica y esta no ha sido digitada. Por favor verifique!'))

            # for lines in record.invoice_line_ids:
            #     if lines.required_partner and not lines.partner_id:
            #         raise ValidationError(_(str(lines.ref)+' - La cuenta "' + lines.account_id.name + '" obliga un tercero y este no ha sido digitado. Por favor verifique!'))

                if 'stock_move_id' in self.env['account.move']._fields:
                    if lines.required_analytic_account and not lines.analytic_account_id and not record.stock_move_id.picking_id:
                        if lines.price_total > 0:
                            raise ValidationError(_(str(lines.ref)+' - La cuenta "' + lines.account_id.name + '" obliga cuenta analítica y esta no ha sido digitada. Por favor verifique!'))
                else:
                    if lines.required_analytic_account and not lines.analytic_account_id:
                        if lines.price_total > 0:
                            raise ValidationError(_(str(lines.ref)+' - La cuenta "' + lines.account_id.name + '" obliga cuenta analítica y esta no ha sido digitada. Por favor verifique!'))

    @api.constrains('supplier_invoice_number')
    def _check_supplier_invoice(self):
        for record in self:
            if record.move_type == 'in_invoice' and record.is_rcm == False:
                obj_move = self.env['account.move'].search([('supplier_invoice_number', '=', record.supplier_invoice_number),('id','!=',record.id)])
                if len(obj_move) > 0:
                    raise ValidationError('El número de factura digitado ya existe, por favor verificar.')

    # @api.constrains('line_ids','invoice_line_ids') # SE COMENTA DEBIDO A QUE AHORA SE HACE EN LA TABLA DE IMPUESTOS ACCOUNT.TAX
    # def _check_minimum_base(self):
    #     for record in self:
    #         for line in record.invoice_line_ids:
    #             if line.tax_ids:
    #                 for tax in line.tax_ids:
    #                     if record.amount_untaxed < tax.minimum_base and tax.has_minimum_base:
    #                         line.tax_ids -= tax
    #                         value_tax_debit,value_tax_credit = 0,0
    #                         for line_tax in record.line_ids.filtered(lambda line: line.tax_ids):
    #                             if len(line_tax.tax_ids) > 0:
    #                                 if tax.id in line_tax.tax_ids.ids:# or tax_line.name == tax.name:
    #                                     try:
    #                                         line_tax.tax_ids -= tax
    #                                         #record._onchange_recompute_dynamic_lines()
    #                                     except Exception as e:
    #                                         pass
    #                                         #record._onchange_recompute_dynamic_lines()
    #                         for tax_line in record.line_ids.filtered(lambda line: line.tax_repartition_line_id):#record.line_ids.filtered(lambda line: line.tax_line_id):
    #                             if tax_line.tax_repartition_line_id.tax_id.id == tax.id:# or tax.id in tax_line.tax_ids.ids:# or tax_line.name == tax.name:
    #                                 value_tax_debit += tax_line.debit
    #                                 value_tax_credit += tax_line.credit
    #                                 try:
    #                                     tax_line.unlink()
    #                                 except Exception as e:
    #                                     pass
    #                         try:
    #                             record._recompute_dynamic_lines(recompute_all_taxes=True)
    #                         except Exception as e:
    #                             obj_line_receivable = record.line_ids.filtered(lambda line: line.account_id.user_type_id.type == 'receivable')  # Cuenta por cobrar
    #                             obj_line_payable = record.line_ids.filtered(lambda line: line.account_id.user_type_id.type == 'payable')  # Cuenta por pagar
    #                             if len(obj_line_receivable) > 0:
    #                                 obj_line_receivable.debit += value_tax_debit + value_tax_credit
    #                                 #obj_line_receivable.debit -= value_tax_credit
    #                             else:
    #                                 if len(obj_line_payable) > 0:
    #                                     #obj_line_payable.credit -= value_tax_debit
    #                                     obj_line_payable.credit += value_tax_credit + value_tax_debit
    #                             record._recompute_dynamic_lines(recompute_all_taxes=True)

    @api.constrains('tax_totals_json','amount_untaxed_signed','amount_total_signed')
    def _check_minimum_base(self):
        for record in self:
            #Revisar base minima
            for line in record.line_ids.filtered('tax_repartition_line_id'):
                try:
                    if line.tax_line_id.has_minimum_base and line.tax_base_amount < line.tax_line_id.minimum_base and line.tax_base_amount > 0 and line.move_id.move_type not in ['out_refund', 'in_refund']:
                        for item in record.invoice_line_ids:
                            for tax in item.tax_ids:
                                if line.tax_line_id.id in tax.ids:
                                    item.tax_ids -= tax
                        #record._recompute_tax_lines()
                        record._recompute_dynamic_lines(recompute_all_taxes=True)
                except:
                    pass

    # def _move_autocomplete_invoice_lines_values(self):
    #     values = super(account_move, self)._move_autocomplete_invoice_lines_values()
    #     self._check_minimum_base()
    #     self.line_ids._onchange_price_subtotal()
    #     self._recompute_dynamic_lines(recompute_all_taxes=True)
    #     values = self._convert_to_write(self._cache)
    #     values.pop('invoice_line_ids', None)
    #     return values

    @api.onchange('partner_id')
    def _onchange_assign_invoice_user(self):
        self.invoice_user_id = self.partner_id.user_id

    @api.model
    def create(self, vals):
        invoice = super(account_move, self).create(vals)
        if invoice.partner_id:
            invoice.partner_id.validate_check_fields_required()
        return invoice

    def write(self, vals):
        invoice = super(account_move, self).write(vals)
        for record in self:
            if record.partner_id:
                record.partner_id.validate_check_fields_required()
        return invoice

class lavish_confirm_wizard(models.TransientModel):
    _inherit = 'lavish.confirm.wizard'

    accounting_closing_id = fields.Many2one('annual.accounting.closing', string='Cierre contable anual', ondelete='cascade')

    def yes(self):
        if self.accounting_closing_id:
            obj_move = self.env['account.move'].search([('accounting_closing_id', '=', self.accounting_closing_id.id)])
            obj_move.unlink()
            self.accounting_closing_id.generate_accounting_closing()
        obj_confirm = super(lavish_confirm_wizard, self).yes()
        return obj_confirm

class annual_accounting_closing(models.Model):
    _name = 'annual.accounting.closing'
    _description = 'Cierre contable anual'

    name = fields.Char('Nombre')
    balance = fields.Float('Saldo', readonly=True)
    closing_year = fields.Integer('Año de cierre')
    counter_contab = fields.Integer(compute='compute_counter_contab', string='Movimientos')
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True, required=True, default=lambda self: self.env.company)
    journal_id = fields.Many2one('account.journal', string='Diario destino', company_dependent=True, required=True)
    counterparty_account = fields.Many2one('account.account', string='Cuenta contrapartida')
    filter_account_ids = fields.Many2many('account.group', string="Cuentas a cerrar")
    partner_id = fields.Many2one('res.partner', 'Tercero de cierre', default=lambda self: self.env.company.partner_id.id)
    closing_by_partner = fields.Boolean('Cerrar por tercero')

    def compute_counter_contab(self):
        count = self.env['account.move'].search_count([('accounting_closing_id', '=', self.id)])
        self.counter_contab = count

    def call_up_closing_wizard(self):
        yes_no = ''
        no_delete = False

        if self.counter_contab > 0:
            obj_contab = self.env['account.move'].search([('accounting_closing_id', '=', self.id)])
            for rows in obj_contab:
                if rows.state != 'draft':
                    no_delete = True
                    break
            if no_delete:
                return {'messages': [{'record': False, 'type': 'warning',
                                      'message': 'Ya hay documentos publicados. No es posible continuar!', }]}
            else:
                yes_no = "El movimiento contable actual para el cierre será borrado para crear uno nuevo. Desea continuar?"

            return {
                'name': 'Deseas continuar?',
                'type': 'ir.actions.act_window',
                'res_model': 'lavish.confirm.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_accounting_closing_id': self.id,
                            'default_yes_no': yes_no}
            }
        else:
            self.generate_accounting_closing()

    def return_action_to_open(self):
        res = {
            'name': 'Movimientos',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move',
            'target': 'current',
            'domain': "[('accounting_closing_id','in',[" + str(self._ids[0]) + "])]"
        }
        return res

    def generate_accounting_closing(self):
        year = str(self.closing_year)
        start_date = '01/01/' + year
        end_date = '31/12/' + year
        row_count = 0
        accounts = ''

        if self.closing_by_partner:
            if not self.partner_id:
                raise ValidationError(_("No se ha especificado el tercero de cierre. Por favor verifique!"))
            if not self.filter_account_ids:
                raise ValidationError(_("No se han especificado las cuentas de cierre. Por favor verifique!"))
        else:
            if not self.counterparty_account:
                raise ValidationError(_("No se han especificado la cuenta de contrapartida. Por favor verifique!"))

        if self.filter_account_ids:
            for account in self.filter_account_ids:
                row_count += 1
                if row_count == 1:
                    if row_count == len(self.filter_account_ids):
                        accounts = '(' + account.code_prefix_start + '%)'
                    else:
                        accounts = '(' + account.code_prefix_start + '%|'
                elif row_count == len(self.filter_account_ids):
                    accounts += account.code_prefix_start + '%)'
                else:
                    accounts += account.code_prefix_start + '%|'
        else:
            accounts = '4%|5%|6%|7%'

        d_start_date = datetime.strptime(start_date, '%d/%m/%Y')
        d_end_date = datetime.strptime(end_date, '%d/%m/%Y')

        query = '''
                select aml.account_id, aml.partner_id, aml.analytic_account_id, sum(aml.debit-aml.credit) as saldo
                from account_move am 
                inner join account_move_line aml on am.id = aml.move_id 
                inner join account_account aa on aml.account_id = aa.id and code similar to '%s' 
                where am."date" between '%s' and '%s' and am.company_id = %s and am.state = 'posted'
                group by aml.account_id, aml.partner_id, aml.analytic_account_id 
                ''' % (accounts, str(d_start_date), str(d_end_date), self.company_id.id)

        self.env.cr.execute(query)
        result_query = self.env.cr.fetchall()

        if not result_query:
            raise ValidationError(_("No se encontraron movimientos para el año especificado. Por favor verifique!"))

        line_ids = []
        move_dict = {
            'company_id': self.env.company.id,
            'ref': 'Cierre contable año: ' + year,
            'journal_id': self.journal_id.id,
            'date': d_end_date,
            'accounting_closing_id': self.id
        }

        total = 0
        for result in result_query:
            account_id = result[0]
            partner_id = result[1]
            analytic_account_id = result[2]
            balance = result[3]

            debit = 0
            credit = 0
            total += balance

            if balance > 0:
                credit = abs(balance)
            elif balance < 0:
                debit = abs(balance)
            else:
                continue

            line = {
                'name': 'Cierre contable año: ' + year,
                'partner_id': partner_id,
                'account_id': account_id,
                'journal_id': self.journal_id.id,
                'date': d_end_date,
                'debit': debit,
                'credit': credit,
                'analytic_account_id': analytic_account_id,
            }
            line_ids.append(line)

            if self.closing_by_partner:
                line = {
                    'name': 'Cierre contable año: ' + year,
                    'partner_id': self.partner_id.id,
                    'account_id': account_id,
                    'journal_id': self.journal_id.id,
                    'date': d_end_date,
                    'debit': credit,
                    'credit': debit,
                    'analytic_account_id': analytic_account_id,
                }
                line_ids.append(line)
        debit = 0
        credit = 0
        if total > 0:
            debit = abs(total)
        elif total < 0:
            credit = abs(total)

        if not self.closing_by_partner:
            line = {
                'name': 'Cierre contable año: ' + year,
                'partner_id': self.env.company.partner_id.id,
                'account_id': self.counterparty_account.id,
                'journal_id': self.journal_id.id,
                'date': d_end_date,
                'debit': debit,
                'credit': credit
            }
            line_ids.append(line)

        move_dict['line_ids'] = [(0, 0, line_vals) for line_vals in line_ids]
        move = self.env['account.move'].create(move_dict)
        self.balance = total

        return True


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.onchange('amount_currency')
    def _onchange_amount_currency(self):
        for line in self:
            if not line.move_id.company_id:
                company = self.env.company
            else:
                company = line.move_id.company_id
            balance = line.currency_id._convert(line.amount_currency, company.currency_id, company, line.move_id.date or fields.Date.context_today(line))
            line.debit = balance if balance > 0.0 else 0.0
            line.credit = -balance if balance < 0.0 else 0.0

            if not line.move_id.is_invoice(include_receipts=True):
                continue

            line.update(line._get_fields_onchange_balance())
            line.update(line._get_price_total_and_subtotal())

    @api.onchange('currency_id')
    def _onchange_currency(self):
        for line in self:
            if not line.move_id.company_id:
                company = self.env.company
            else:
                company = line.move_id.company_id

            if line.move_id.is_invoice(include_receipts=True):
                line._onchange_price_subtotal()
            elif not line.move_id.reversed_entry_id:
                balance = line.currency_id._convert(line.amount_currency, company.currency_id, company, line.move_id.date or fields.Date.context_today(line))
                line.debit = balance if balance > 0.0 else 0.0
                line.credit = -balance if balance < 0.0 else 0.0
