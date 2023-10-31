from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.misc import formatLang, format_date, get_lang
import logging
import json
from json import dumps
from odoo.tools import float_is_zero, UserError, datetime

_logger = logging.getLogger(__name__)

class AccountPaymentRegister(models.TransientModel):
	_inherit='account.payment.register'

	account_id = fields.Many2one(
		comodel_name='account.account',
		string='Cuenta de origen',
		store=True, readonly=False,
		domain="[('deprecated', '=', False), ('company_id', '=', company_id)]",
		check_company=True)
	destination_account_id = fields.Many2one(
		comodel_name='account.account',
		string='Destination Account',
		store=True, readonly=False,
		domain="[('user_type_id.type', 'in', ('receivable', 'payable')), ('company_id', '=', company_id)]",
		check_company=True)
	change_destination_account = fields.Char(string="cambio de cuenta destino")

	def _create_payment_vals_from_wizard(self):
		payment_vals = super(AccountPaymentRegister, self)._create_payment_vals_from_wizard()
		if self.account_id:
			payment_vals['account_id'] = self.account_id.id
		if self.destination_account_id:
			payment_vals['destination_account_id'] = self.destination_account_id.id
		return payment_vals

class AccountMove(models.Model):
	_inherit = "account.move"
	pay_id = fields.Many2one(
		comodel_name='account.payment',
		string='Pago',
		required=False)

	prepaid_ids  = fields.One2many(
		comodel_name='account.payment',
		inverse_name='invoice_id',
		string='Anticipos',
		required=False)
 
	def _get_reconciled_invoices(self):
		"""Helper used to retrieve the reconciled payments on this journal entry"""
		if self._context.get('account_id'):
			reconciled_lines = self.line_ids.filtered(lambda line: line.account_id.user_type_id.type in (
				'receivable', 'payable') and line.account_id == self._context.get('account_id'))
		else:
			reconciled_lines = self.line_ids.filtered(
				lambda line: line.account_id.user_type_id.type in ('receivable', 'payable'))
		reconciled_amls = reconciled_lines.mapped('matched_debit_ids.debit_move_id') + \
						  reconciled_lines.mapped('matched_credit_ids.credit_move_id')
		return reconciled_amls.move_id.filtered(lambda move: move.is_invoice(include_receipts=True))

	@api.onchange('partner_id')
	def _onchange_partner_id(self):
		obj_payments = self.env['account.payment'].search(
			[('partner_id', '=', self.partner_id.id), ('advance', '=', True)])

		payment_list_ids = obj_payments.ids
		self.prepaid_ids = [(6, 0, payment_list_ids)]

	def pay_in_advance(self):

		list_line = []
		advance_sum = 0

		processed_payment= []

		if self.prepaid_ids:
			for element in self.prepaid_ids:
					if element.process_prepaid and element.processed != True :
						advance_sum = advance_sum + element.amount
					if advance_sum:
						processed_payment.append(element.id)
					else:
						raise UserError('Debe seleccionar los anticipos para realizar el pago de la factura')
		else:
			raise UserError('No existen anticipos para esta factura')

		if advance_sum:

			list_line.append(
				(0, 0, {'account_id': self.partner_id.property_account_payable_id.id,
						'partner_id': self.partner_id.id,
						'debit': advance_sum,
						'credit': 0.0,
						}))


			list_line.append(
				(0, 0, {'account_id': self.prepaid_ids[0].destination_account_id.id,
						'partner_id': self.partner_id.id,
						'debit': 0.0,
						'credit': advance_sum,
						}))

			vals = {
				'date': self.date,
				'line_ids': list_line,
				'move_type': 'entry'
			}
			obj_account_move = self.env['account.move'].create(vals)
			obj_account_move.action_post()
			for pay in self.prepaid_ids:
				if pay.id in processed_payment:
					pay.processed = True

	def _compute_payments_widget_to_reconcile_info(self):
		for move in self:
			move.invoice_outstanding_credits_debits_widget = json.dumps(False)
			move.invoice_has_outstanding = False

			if move.state != 'posted' \
					or move.payment_state not in ('not_paid', 'partial') \
					or not move.is_invoice(include_receipts=True):
				continue

			pay_term_lines = move.line_ids\
				.filtered(lambda line: line.account_id.user_type_id.type in ('receivable', 'payable'))

			domain = [
				('account_id', 'in', pay_term_lines.account_id.ids),
				('parent_state', '=', 'posted'),
				('partner_id', '=', move.commercial_partner_id.id),
				('reconciled', '=', False),
				'|', ('amount_residual', '!=', 0.0), ('amount_residual_currency', '!=', 0.0),
			]

			payments_widget_vals = {'outstanding': True, 'content': [], 'move_id': move.id}
			if move.is_inbound():
				domain.append(('balance', '<', 0.0))
				payments_widget_vals['title'] = _('Outstanding credits')
			else:
				domain.append(('balance', '>', 0.0))
				payments_widget_vals['title'] = _('Outstanding debits')

			for line in self.env['account.move.line'].search(domain):

				if line.currency_id == move.currency_id:
					# Same foreign currency.
					amount = abs(line.amount_residual_currency)
				else:
					# Different foreign currencies.
					amount = move.company_currency_id._convert(
						abs(line.amount_residual),
						move.currency_id,
						move.company_id,
						line.date,
					)
				if move.currency_id.is_zero(amount):
					continue
				payments_widget_vals['content'].append({
					'journal_name': line.ref or line.move_id.name,
					'amount': amount,
					'currency': move.currency_id.symbol,
					'id': line.id,
					'move_id': line.move_id.id,
					'position': move.currency_id.position,
					'digits': [69, move.currency_id.decimal_places],
					'payment_date': fields.Date.to_string(line.date),
				})
			if not payments_widget_vals['content']:
				continue
			move.invoice_outstanding_credits_debits_widget = json.dumps(payments_widget_vals)
			move.invoice_has_outstanding = True


	def js_assign_outstanding_line(self, line_id):
		self.ensure_one()
		lines = self.env['account.move.line'].browse(line_id)
		lines += self.line_ids.filtered(lambda line: line.account_id == lines[0].account_id and not line.reconciled)
		if len(lines)==1 and self.move_type=='out_invoice':
			lines += self.line_ids.filtered(lambda line: line.account_id == self.partner_id.property_account_receivable_id and not line.reconciled)
		if len(lines)==1 and self.move_type=='in_invoice':
			lines += self.line_ids.filtered(lambda line: line.account_id == self.partner_id.property_account_payable_id and not line.reconciled)
		return lines.reconcile()
		
class AccountMoveLine(models.Model):
	_inherit = "account.move.line"

	inv_id = fields.Many2one('account.move', string='Invoice')
	processed  = fields.Boolean(
		string='Procesado',
		required=False)

	@api.depends('ref', 'move_id')
	def name_get(self):
		super().name_get()
		result = []
		for line in self:
			if self._context.get('show_number', False):
				name = '%s - %s' %(line.move_id.name, abs(line.amount_residual_currency or line.amount_residual))
				result.append((line.id, name))
			elif line.ref:
				result.append((line.id, (line.move_id.name or '') + '(' + line.ref + ')'))
			else:
				result.append((line.id, line.move_id.name))
		return result

	# def _create_exchange_difference_move(self):
	# 	exchange_move = super(AccountMoveLine, self)._create_exchange_difference_move()
	# 	exchange_move_lines = exchange_move.line_ids.filtered(lambda line: line.account_id == account)
	# 	self._append_move_diff_payment(aml_to_fix, move)
	# 	return

	@api.model
	def _compute_amount_fields(self, amount, src_currency, company_currency):
		""" Helper function to compute value for fields debit/credit/amount_currency based on an amount and the currencies given in parameter"""
		amount_currency = False
		currency_id = False
		date = self.env.context.get('date') or fields.Date.today()
		company = self.env.context.get('company_id')
		company = self.env['res.company'].browse(company) if company else self.env.company
		if src_currency and src_currency != company_currency:
			amount_currency = amount
			amount = src_currency._convert(amount, company_currency, company, date)
			currency_id = src_currency.id
		debit = amount > 0 and amount or 0.0
		credit = amount < 0 and -amount or 0.0
		return debit, credit, amount_currency, currency_id

	def _append_move_diff_payment(self, aml_to_fix, move):
		for aml in aml_to_fix:
			if aml.payment_id:
				aml.payment_id.move_diff_ids += move

	def reconcile(self):
		res = super(AccountMoveLine, self).reconcile()
		if res.get('full_reconcile'):
			exchange_move = res.get('full_reconcile').exchange_move_id
			if exchange_move:
				line_ids = exchange_move.line_ids
				self._append_move_diff_payment(line_ids, exchange_move)
		return res
	def _check_reconcile_validity(self):
		company_ids = set()
		all_accounts = []
		for line in self:
			company_ids.add(line.company_id.id)
			all_accounts.append(line.account_id)
			if (line.matched_debit_ids or line.matched_credit_ids) and line.reconciled:
				raise UserError(_('You are trying to reconcile some entries that are already reconciled.'))
		if len(company_ids) > 1:
			raise UserError(_('To reconcile the entries company should be the same for all entries.'))
		if not (all_accounts[0].reconcile or all_accounts[0].internal_type == 'liquidity'):
			raise UserError(_('Account %s (%s) does not allow reconciliation. First change the configuration of this account to allow it.') % (all_accounts[0].name, all_accounts[0].code))


	def reconcile(self):
		''' Reconcile the current move lines all together.
		:return: A dictionary representing a summary of what has been done during the reconciliation:
				* partials:			 A recorset of all account.partial.reconcile created during the reconciliation.
				* full_reconcile:	   An account.full.reconcile record created when there is nothing left to reconcile
										in the involved lines.
				* tax_cash_basis_moves: An account.move recordset representing the tax cash basis journal entries.
		'''
		results = {}
		if not self:
			return results
		# List unpaid invoices
		not_paid_invoices = self.move_id.filtered(
			lambda move: move.is_invoice(include_receipts=True) and move.payment_state not in ('paid', 'in_payment')
		)
		# ==== Check the lines can be reconciled together ====
		company = None
		account = None
		for line in self:
			if line.reconciled:
				raise UserError(_("You are trying to reconcile some entries that are already reconciled."))
			if not line.account_id.reconcile and line.account_id.internal_type != 'liquidity':
				raise UserError(
					_("Account %s does not allow reconciliation. First change the configuration of this account to allow it.")
					% line.account_id.display_name)
			if line.move_id.state != 'posted':
				raise UserError(_('You can only reconcile posted entries.'))
			if company is None:
				company = line.company_id
			elif line.company_id != company:
				raise UserError(_("Entries doesn't belong to the same company: %s != %s")
								% (company.display_name, line.company_id.display_name))
			if account is None:
				account = line.account_id
		sorted_lines = self.sorted(key=lambda line: (line.date_maturity or line.date, line.currency_id))
		# ==== Collect all involved lines through the existing reconciliation ====
		involved_lines = sorted_lines
		involved_partials = self.env['account.partial.reconcile']
		current_lines = involved_lines
		current_partials = involved_partials
		while current_lines:
			current_partials = (
										   current_lines.matched_debit_ids + current_lines.matched_credit_ids) - current_partials
			involved_partials += current_partials
			current_lines = (current_partials.debit_move_id + current_partials.credit_move_id) - current_lines
			involved_lines += current_lines
		# ==== Create partials ====
		partials = self.env['account.partial.reconcile'].create(sorted_lines._prepare_reconciliation_partials())
		# Track newly created partials.
		results['partials'] = partials
		involved_partials += partials
		# ==== Create entries for cash basis taxes ====
		is_cash_basis_needed = account.user_type_id.type in ('receivable', 'payable')
		if is_cash_basis_needed and not self._context.get('move_reverse_cancel'):
			tax_cash_basis_moves = partials._create_tax_cash_basis_moves()
			results['tax_cash_basis_moves'] = tax_cash_basis_moves
		# ==== Check if a full reconcile is needed ====
		if involved_lines[0].currency_id and all(
				line.currency_id == involved_lines[0].currency_id for line in involved_lines):
			is_full_needed = all(line.currency_id.is_zero(line.amount_residual_currency) for line in involved_lines)
		else:
			is_full_needed = all(line.company_currency_id.is_zero(line.amount_residual) for line in involved_lines)
		if is_full_needed:
			# ==== Create the exchange difference move ====
			if self._context.get('no_exchange_difference'):
				exchange_move = None
			else:
				exchange_move = involved_lines._create_exchange_difference_move()
				if exchange_move:
					exchange_move_lines = exchange_move.line_ids.filtered(lambda line: line.account_id == account)
					# Track newly created lines.
					involved_lines += exchange_move_lines
					# Track newly created partials.
					exchange_diff_partials = exchange_move_lines.matched_debit_ids \
											 + exchange_move_lines.matched_credit_ids
					involved_partials += exchange_diff_partials
					results['partials'] += exchange_diff_partials
					exchange_move._post(soft=False)
			# ==== Create the full reconcile ====
			results['full_reconcile'] = self.env['account.full.reconcile'].create({
				'exchange_move_id': exchange_move and exchange_move.id,
				'partial_reconcile_ids': [(6, 0, involved_partials.ids)],
				'reconciled_line_ids': [(6, 0, involved_lines.ids)],
			})
		# Trigger action for paid invoices
		not_paid_invoices \
			.filtered(lambda move: move.payment_state in ('paid', 'in_payment')) \
			.action_invoice_paid()
		return results



class AccountFullReconcile(models.Model):
	_inherit = "account.full.reconcile"

	@api.model
	def create(self, vals):
		self._set_invoice_diff_by_aml(vals)
		res = super(AccountFullReconcile, self).create(vals)
		return res

	def _set_invoice_diff_by_aml(self, vals):
		if vals.get('reconciled_line_ids'):
			move_lines = self.env['account.move.line'].browse(vals['reconciled_line_ids'][0][2])
			extrange_diff_pay = move_lines.filtered(lambda l: l.name == _('Currency exchange rate difference'))
			if extrange_diff_pay:
				for rec in move_lines - extrange_diff_pay:
					if rec.move_id:
						values = {
							'ref': rec.move_id.name
							}
						extrange_diff_pay.write(values)

class AccountPartialReconcile(models.Model):
	_inherit = "account.partial.reconcile"

	@api.model
	def create(self, vals):
		reconciliation = super(AccountPartialReconcile, self).create(vals)
		vals_asiento ={}
		factura = self.env['account.move.line'].search([('id','=',vals['debit_move_id'])])
		pago = self.env['account.move.line'].search([('id','=',vals['credit_move_id'])])
		if factura.account_id!=pago.account_id:
			x = datetime.now()
			milisc = x.strftime("_" + "%f")
			asiento = self.env['account.move'].create({
				'partner_id':factura.move_id.partner_id.id,
				#'name': factura.move_id.name+"_pago"+ milisc if factura.move_id.move_type in ['out_invoice','in_invoice'] else pago.move_id.name+"_pago"+ milisc,
				'date': reconciliation['create_date'],
				'ref': factura.move_id.name + milisc,
				'journal_id': pago.move_id.journal_id.id if factura.move_id.move_type in ['out_invoice','in_invoice'] else factura.move_id.journal_id.id,
				'company_id': factura.move_id.company_id.id if factura.move_id.move_type in ['out_invoice','in_invoice'] else pago.move_id.company_id.id,
				'move_type': 'entry',
				'state': 'draft'
			})
			if factura.move_id.move_type in ['out_invoice', 'in_invoice']:
				movimiento_credito=self.with_context(check_move_validity=False).env['account.move.line'].create(
					{
						'partner_id': factura.move_id.partner_id.id,
						'account_id': factura.account_id.id ,
						'credit': vals['amount'],
						'debit': 0 ,
						'move_id': asiento.id,
						'currency_id': factura.currency_id.id
					})
				movimiento_debito=self.with_context(check_move_validity=False).env['account.move.line'].create(
					{
						'partner_id': factura.move_id.partner_id.id,
						'account_id': pago.account_id.id if factura.move_id.move_type in ['out_invoice','in_invoice'] else factura.account_id.id,
						'credit': 0,
						'debit': vals['amount'],
						'move_id': asiento.id,
						'currency_id': pago.currency_id.id
					})
			else:
				movimiento_debito=self.with_context(check_move_validity=False).env['account.move.line'].create(
					{
						'partner_id': factura.move_id.partner_id.id,
						'account_id': pago.account_id.id,
						'credit': 0,
						'debit': vals['amount'],
						'move_id': asiento.id,
						'currency_id': pago.currency_id.id
					})
				movimiento_credito = self.with_context(check_move_validity=False).env['account.move.line'].create(
					{
						'partner_id': factura.move_id.partner_id.id,
						'account_id': factura.account_id.id,
						'credit': vals['amount'],
						'debit': 0,
						'move_id': asiento.id,
						'currency_id': factura.currency_id.id
					})

			asiento.action_post()
			vals_nuevo_asiento={
					'debit_move_id': movimiento_debito.id,
					'credit_move_id': movimiento_credito.id,
					'amount': vals['amount'],
					#'amount_currency': vals['amount_currency'],
					#'currency_id': vals['currency_id']
				}

			super(AccountPartialReconcile, self).create(vals_nuevo_asiento)
		return reconciliation

	def unlink(self):
		# Code before unlink: can use `self`, with the old values
		for record in self: 
			factura = self.env['account.move.line'].search([('id','=',record.debit_move_id.id)])
			pago = self.env['account.move.line'].search([('id','=',record.credit_move_id.id)])

			if factura.account_id!=pago.account_id:
				x = datetime.now()
				milisc = x.strftime("_" + "%f")
				asiento = self.env['account.move'].create({
					'partner_id': factura.move_id.partner_id.id,
					#'name': factura.move_id.name+"_eli_pago"+ milisc if factura.move_id.move_type in ['out_invoice','in_invoice'] else pago.move_id.name+"_pago"+ milisc,
					'ref': factura.move_id.name + "inv_"+milisc,
					'journal_id': pago.move_id.journal_id.id if factura.move_id.move_type in ['out_invoice','in_invoice'] else factura.move_id.journal_id.id,
					'company_id': factura.move_id.company_id.id if factura.move_id.move_type in ['out_invoice','in_invoice'] else pago.move_id.company_id.id,
					'move_type': 'entry',
					'state': 'draft'
				})

				if factura.move_id.move_type in ['out_invoice', 'in_invoice']:
					movimiento_debito = self.with_context(check_move_validity=False).env['account.move.line'].create(
						{
							'partner_id': factura.move_id.partner_id.id,
							'account_id': factura.account_id.id,
							'credit': 0,
							'debit': record['amount'],
							'move_id': asiento.id,
							'currency_id': factura.currency_id.id
						})
					movimiento_credito = self.with_context(check_move_validity=False).env['account.move.line'].create(
						{
							'partner_id': factura.move_id.partner_id.id,
							'account_id': pago.account_id.id if factura.move_id.move_type in ['out_invoice',																					 'in_invoice'] else factura.account_id.id,
							'credit': record['amount'],
							'debit': 0,
							'move_id': asiento.id,
							'currency_id': pago.currency_id.id
						})
				else:
					movimiento_credito = self.with_context(check_move_validity=False).env['account.move.line'].create(
						{
							'partner_id': factura.move_id.partner_id.id,
							'account_id': pago.account_id.id,
							'credit': record['amount'],
							'debit': 0,
							'move_id': asiento.id,
							'currency_id': pago.currency_id.id
						})
					movimiento_debito = self.with_context(check_move_validity=False).env['account.move.line'].create(
						{
							'partner_id': factura.move_id.partner_id.id,
							'account_id': factura.account_id.id,
							'credit': 0,
							'debit': record['amount'],
							'move_id': asiento.id,
							'currency_id': factura.currency_id.id
						})

				asiento.action_post()
				vals_nuevo_asiento = {
					'debit_move_id': movimiento_debito.id,
					'credit_move_id': movimiento_credito.id,
					'amount': record['amount'],
					#'amount_currency': record['amount_currency'],
					#'currency_id': record['currency_id']
				}

				super(AccountPartialReconcile, record).create(vals_nuevo_asiento)
		reconciliation=super(AccountPartialReconcile, self).unlink()
		return reconciliation
