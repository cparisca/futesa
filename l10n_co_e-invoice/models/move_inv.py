# -*- coding: utf-8 -*-
import json
import datetime
from datetime import timedelta, date
import hashlib
import logging
import os
import pyqrcode
import zipfile
import pytz
import time
import traceback
#from .amount_to_txt_es import amount_to_text_es
#from .signature import *
from enum import Enum
#from jinja2 import Template
import ast
from collections import defaultdict
from contextlib import contextmanager
from functools import lru_cache

from odoo import api, fields, models, Command, _
from odoo.tools import frozendict, formatLang, format_date, float_compare
from odoo.tools.sql import create_index

from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError, Warning
from odoo import models, fields, api, _, Command
from odoo.tools.misc import get_lang
from lxml import etree
from io import BytesIO
from xml.sax import saxutils
#from .helpers import WsdlQueryHelper
import xml.etree.ElementTree as ET
_logger = logging.getLogger(__name__)
urllib3_logger = logging.getLogger('urllib3')
urllib3_logger.setLevel(logging.ERROR)

class Invoice(models.Model):
    _inherit = "account.move"

    fecha_envio = fields.Datetime(string='Fecha de envío en UTC',copy=False)
    fecha_entrega = fields.Datetime(string='Fecha de entrega',copy=False)
    fecha_xml = fields.Datetime(string='Fecha de factura Publicada',copy=False)
    total_withholding_amount = fields.Float(string='Total de retenciones')
    invoice_trade_sample = fields.Boolean(string='Tiene muestras comerciales',)
    trade_sample_price = fields.Selection([('01', 'Valor comercial')],   string='Referencia a precio real',  )

    @api.depends(
        'line_ids.debit',
        'line_ids.credit',
        'line_ids.currency_id',
        'line_ids.amount_currency',
        'line_ids.amount_residual',
        'line_ids.amount_residual_currency',
        'line_ids.payment_id.state')
    def _compute_amount(self):
        invoice_ids = [move.id for move in self if move.id and move.is_invoice(include_receipts=True)]
        self.env['account.payment'].flush(['state'])
        in_payment_set = {}
        for move in self:
            total_untaxed = 0.0
            total_untaxed_currency = 0.0
            total_tax = 0.0
            total_tax_currency = 0.0
            total_residual = 0.0
            total_to_pay = 0.0
            total_residual_currency = 0.0
            total = 0.0
            total_currency = 0.0
            currencies = set()

            for line in move.line_ids:
                if move.move_type in ['in_invoice', 'in_refund'] or (not line.product_id.enable_charges and line.name!='Descuento A Total de Factura'):
                    if line.currency_id and line.currency_id!=move.company_id.currency_id:
                        currencies.add(line.currency_id)
                    if move.is_invoice(include_receipts=True):
                        # === Invoices ===
                        if not line.exclude_from_invoice_tab:
                            # Untaxed amount.
                            total_untaxed += line.balance
                            total_untaxed_currency += line.amount_currency
                            total += line.balance
                            total_currency += line.amount_currency
                        elif line.tax_line_id:
                            # Tax amount.
                            total_tax += line.balance
                            total_tax_currency += line.amount_currency
                            total += line.balance
                            total_currency += line.amount_currency
                        elif line.account_id.user_type_id.type in ('receivable', 'payable'):
                            # Residual amount.
                            total_to_pay += line.balance
                            total_residual += line.amount_residual
                            total_residual_currency += line.amount_residual_currency
                    else:
                        # === Miscellaneous journal entry ===
                        if line.debit:
                            total += line.balance
                            total_currency += line.amount_currency
                elif move.move_type not in ['in_invoice', 'in_refund'] and (line.product_id.enable_charges or line.name == 'Descuento A Total de Factura'):
                    total += line.balance
                    total_currency += line.amount_currency

            if move.move_type == 'entry' or move.is_outbound():
                sign = 1
            else:
                sign = -1

            move.amount_untaxed = sign * (total_untaxed_currency if len(currencies) == 1 else total_untaxed)
            move.amount_tax = sign * (total_tax_currency if len(currencies) == 1 else total_tax)
            move.amount_total = sign * (total_currency if len(currencies) == 1 else total)
            move.amount_residual = -sign * (total_residual_currency if len(currencies) == 1 else total_residual)
            move.amount_untaxed_signed = -total_untaxed
            move.amount_tax_signed = -total_tax
            move.amount_total_signed = -total
            move.amount_residual_signed = total_residual

            currency = len(currencies) == 1 and currencies.pop() or move.company_id.currency_id
            is_paid = currency and currency.is_zero(move.amount_residual) or not move.amount_residual
            new_pmt_state = 'not_paid' if move.move_type != 'entry' else False

            if move.is_invoice(include_receipts=True) and move.state == 'posted':

                if currency.is_zero(move.amount_residual):
                    reconciled_payments = move._get_reconciled_payments()
                    if not reconciled_payments or all(payment.is_matched for payment in reconciled_payments):
                        new_pmt_state = 'paid'
                    else:
                        new_pmt_state = move._get_invoice_in_payment_state()
                elif currency.compare_amounts(total_to_pay, total_residual) != 0:
                    new_pmt_state = 'partial'

            if new_pmt_state == 'paid' and move.move_type in ('in_invoice', 'out_invoice', 'entry'):
                reverse_type = move.move_type == 'in_invoice' and 'in_refund' or move.move_type == 'out_invoice' and 'out_refund' or 'entry'
                reverse_moves = self.env['account.move'].search([('reversed_entry_id', '=', move.id), ('state', '=', 'posted'), ('move_type', '=', reverse_type)])

                # We only set 'reversed' state in cas of 1 to 1 full reconciliation with a reverse entry; otherwise, we use the regular 'paid' state
                reverse_moves_full_recs = reverse_moves.mapped('line_ids.full_reconcile_id')
                if reverse_moves_full_recs.mapped('reconciled_line_ids.move_id').filtered(lambda x: x not in (
                        reverse_moves + reverse_moves_full_recs.mapped('exchange_move_id'))) == move:
                    new_pmt_state = 'reversed'

            move.payment_state = new_pmt_state


    def _recompute_tax_lines(self, recompute_tax_base_amount=False):
        ''' Compute the dynamic tax lines of the journal entry.
        :param lines_map: The line_ids dispatched by type containing:
            * base_lines: The lines having a tax_ids set.
            * tax_lines: The lines having a tax_line_id set.
            * terms_lines: The lines generated by the payment terms of the invoice.
            * rounding_lines: The cash rounding lines of the invoice.
        '''
        self.ensure_one()
        in_draft_mode = self != self._origin

        def _serialize_tax_grouping_key(grouping_dict):
            ''' Serialize the dictionary values to be used in the taxes_map.
            :param grouping_dict: The values returned by '_get_tax_grouping_key_from_tax_line' or '_get_tax_grouping_key_from_base_line'.
            :return: A string representing the values.
            '''
            return '-'.join(str(v) for v in grouping_dict.values())

        def _compute_base_line_taxes(base_line):
            ''' Compute taxes amounts both in company currency / foreign currency as the ratio between
            amount_currency & balance could not be the same as the expected currency rate.
            The 'amount_currency' value will be set on compute_all(...)['taxes'] in multi-currency.
            :param base_line:   The account.move.line owning the taxes.
            :return:            The result of the compute_all method.
            '''
            move = base_line.move_id

            is_invoice = False

            if move.is_invoice(include_receipts=True):
                handle_price_include = True
                sign = -1 if move.is_inbound() else 1
                quantity = base_line.quantity
                is_refund = move.move_type in ('out_refund', 'in_refund')
                price_unit_wo_discount = sign * base_line.price_unit * (1 - (base_line.discount / 100.0))
                is_invoice = True
            else:
                handle_price_include = False
                quantity = 1.0
                tax_type = base_line.tax_ids[0].type_tax_use if base_line.tax_ids else None
                is_refund = (tax_type == 'sale' and base_line.debit) or (tax_type == 'purchase' and base_line.credit)
                price_unit_wo_discount = base_line.balance

            if base_line.price_unit != 0 or is_invoice == False:
                balance_taxes_res = base_line.tax_ids._origin.with_context(
                    force_sign=move._get_tax_force_sign()).compute_all(
                    price_unit_wo_discount,
                    currency=base_line.company_currency_id,
                    quantity=quantity,
                    product=base_line.product_id,
                    partner=base_line.partner_id,
                    is_refund=is_refund,
                    handle_price_include=handle_price_include,
                )
            else:
                balance_taxes_res = base_line.tax_ids._origin.with_context(
                    force_sign=move._get_tax_force_sign()).compute_all(
                    (sign * base_line.line_price_reference),
                    currency=base_line.company_currency_id,
                    quantity=quantity,
                    product=base_line.product_id,
                    partner=base_line.partner_id,
                    is_refund=is_refund,
                    handle_price_include=handle_price_include,
                )

            if move.move_type == 'entry':
                repartition_field = is_refund and 'refund_repartition_line_ids' or 'invoice_repartition_line_ids'
                repartition_tags = base_line.tax_ids.flatten_taxes_hierarchy().mapped(repartition_field).filtered(
                    lambda x: x.repartition_type == 'base').tag_ids
                tags_need_inversion = (tax_type == 'sale' and not is_refund) or (tax_type == 'purchase' and is_refund)
                if tags_need_inversion:
                    balance_taxes_res['base_tags'] = base_line._revert_signed_tags(repartition_tags).ids
                    for tax_res in balance_taxes_res['taxes']:
                        tax_res['tag_ids'] = base_line._revert_signed_tags(
                            self.env['account.account.tag'].browse(tax_res['tag_ids'])).ids

            return balance_taxes_res

        taxes_map = {}

        # ==== Add tax lines ====
        to_remove = self.env['account.move.line']
        for line in self.line_ids.filtered('tax_repartition_line_id'):
            grouping_dict = self._get_tax_grouping_key_from_tax_line(line)
            grouping_key = _serialize_tax_grouping_key(grouping_dict)
            if grouping_key in taxes_map:
                # A line with the same key does already exist, we only need one
                # to modify it; we have to drop this one.
                to_remove += line
            else:
                taxes_map[grouping_key] = {
                    'tax_line': line,
                    'amount': 0.0,
                    'tax_base_amount': 0.0,
                    'grouping_dict': False,
                }
        if not recompute_tax_base_amount:
            self.line_ids -= to_remove

        # ==== Mount base lines ====
        for line in self.line_ids.filtered(lambda line: not line.tax_repartition_line_id):
            # Don't call compute_all if there is no tax.
            if not line.tax_ids:
                if not recompute_tax_base_amount:
                    line.tax_tag_ids = [(5, 0, 0)]
                continue

            compute_all_vals = _compute_base_line_taxes(line)

            # Assign tags on base line
            if not recompute_tax_base_amount:
                line.tax_tag_ids = compute_all_vals['base_tags'] or [(5, 0, 0)]

            tax_exigible = True
            for tax_vals in compute_all_vals['taxes']:
                grouping_dict = self._get_tax_grouping_key_from_base_line(line, tax_vals)
                grouping_key = _serialize_tax_grouping_key(grouping_dict)

                tax_repartition_line = self.env['account.tax.repartition.line'].browse(
                    tax_vals['tax_repartition_line_id'])
                tax = tax_repartition_line.invoice_tax_id or tax_repartition_line.refund_tax_id

                if tax.tax_exigibility == 'on_payment':
                    tax_exigible = False

                taxes_map_entry = taxes_map.setdefault(grouping_key, {
                    'tax_line': None,
                    'amount': 0.0,
                    'tax_base_amount': 0.0,
                    'grouping_dict': False,
                })
                taxes_map_entry['amount'] += tax_vals['amount']
                taxes_map_entry['tax_base_amount'] += self._get_base_amount_to_display(tax_vals['base'],
                                                                                       tax_repartition_line,
                                                                                       tax_vals['group'])
                taxes_map_entry['grouping_dict'] = grouping_dict
            #if not recompute_tax_base_amount:
                #line.tax_exigible = tax_exigible

        # ==== Process taxes_map ====
        for taxes_map_entry in taxes_map.values():
            # The tax line is no longer used in any base lines, drop it.
            if taxes_map_entry['tax_line'] and not taxes_map_entry['grouping_dict']:
                if not recompute_tax_base_amount:
                    self.line_ids -= taxes_map_entry['tax_line']
                continue

            currency = self.env['res.currency'].browse(taxes_map_entry['grouping_dict']['currency_id'])
            if not currency:
                currency = self.env['res.currency'].search([('id','=',8)])

            # Don't create tax lines with zero balance.
            if currency.is_zero(taxes_map_entry['amount']):
                if taxes_map_entry['tax_line'] and not recompute_tax_base_amount:
                    self.line_ids -= taxes_map_entry['tax_line']
                continue

            # tax_base_amount field is expressed using the company currency.
            tax_base_amount = currency._convert(taxes_map_entry['tax_base_amount'], self.company_currency_id,
                                                self.company_id, self.date or fields.Date.context_today(self))

            # Recompute only the tax_base_amount.
            if recompute_tax_base_amount:
                if taxes_map_entry['tax_line']:
                    taxes_map_entry['tax_line'].tax_base_amount = tax_base_amount
                continue

            balance = currency._convert(
                taxes_map_entry['amount'],
                self.journal_id.company_id.currency_id,
                self.journal_id.company_id,
                self.date or fields.Date.context_today(self),
            )
            to_write_on_line = {
                'amount_currency': taxes_map_entry['amount'],
                'currency_id': taxes_map_entry['grouping_dict']['currency_id'],
                'debit': balance > 0.0 and balance or 0.0,
                'credit': balance < 0.0 and -balance or 0.0,
                'tax_base_amount': tax_base_amount,
            }

            if taxes_map_entry['tax_line']:
                # Update an existing tax line.
                taxes_map_entry['tax_line'].update(to_write_on_line)
            else:
                create_method = in_draft_mode and self.env['account.move.line'].new or self.env[
                    'account.move.line'].create
                tax_repartition_line_id = taxes_map_entry['grouping_dict']['tax_repartition_line_id']
                tax_repartition_line = self.env['account.tax.repartition.line'].browse(tax_repartition_line_id)
                tax = tax_repartition_line.invoice_tax_id or tax_repartition_line.refund_tax_id
                taxes_map_entry['tax_line'] = create_method({
                    **to_write_on_line,
                    'name': tax.name,
                    'move_id': self.id,
                    'partner_id': line.partner_id.id,
                    'company_id': line.company_id.id,
                    'company_currency_id': line.company_currency_id.id,
                    'tax_base_amount': tax_base_amount,
                    'exclude_from_invoice_tab': True,
                    #'tax_exigible': tax.tax_exigibility == 'on_invoice',
                    **taxes_map_entry['grouping_dict'],
                })

            if in_draft_mode:
                taxes_map_entry['tax_line'].update(
                    taxes_map_entry['tax_line']._get_fields_onchange_balance(force_computation=True))


    def _recompute_dynamic_lines(self, recompute_all_taxes=False, recompute_tax_base_amount=False):
        ''' Recompute all lines that depend of others.

        For example, tax lines depends of base lines (lines having tax_ids set). This is also the case of cash rounding
        lines that depend of base lines or tax lines depending the cash rounding strategy. When a payment term is set,
        this method will auto-balance the move with payment term lines.

        :param recompute_all_taxes: Force the computation of taxes. If set to False, the computation will be done
                                    or not depending of the field 'recompute_tax_line' in lines.
        '''
        for invoice in self:
        
            # Dispatch lines and pre-compute some aggregated values like taxes.
            for line in invoice.line_ids:
                if line.recompute_tax_line:
                    recompute_all_taxes = True
                    line.recompute_tax_line = False

                if invoice.move_type == 'out_invoice': #and resolucion.tipo == 'facturacion-electronica':
                    if line.price_unit==0:
                        recompute_all_taxes = True
                        line.recompute_tax_line = False


            # Compute taxes.
            if recompute_all_taxes:
                invoice._recompute_tax_lines()
            if recompute_tax_base_amount:
                invoice._recompute_tax_lines(recompute_tax_base_amount=True)

            if invoice.is_invoice(include_receipts=True):

                # Compute cash rounding.
                invoice._recompute_cash_rounding_lines()

                # Compute payment terms.
                invoice._recompute_payment_terms_lines()

                # Only synchronize one2many in onchange.
                if invoice != invoice._origin:
                    invoice.invoice_line_ids = invoice.line_ids.filtered(lambda line: not line.exclude_from_invoice_tab)
    @api.model
    def _get_time(self):
        fmt = "%H:%M:%S"
        now_utc = datetime.now(timezone("UTC"))
        now_time = now_utc.strftime(fmt)
        return now_time

    @api.model
    def _get_time_colombia(self):
        fmt = "%H:%M:%S-05:00"
        now_utc = datetime.datetime.now(timezone("UTC"))
        now_time = now_utc.strftime(fmt)
        return now_time

    def calcular_texto_descuento(self, id):

        if id == '00':
            return 'Descuento no condicionado'
        elif id == '01':
            return 'Descuento condicionado'
        else:
            return ''
    
    @staticmethod
    def _str_to_datetime(date):
        date = date.replace(tzinfo=pytz.timezone('UTC'))
        return date
    
    def generar_invoice_tax(self,document=None):
        contacto_compañia = self.company_id.partner_id.id
        invoice = self
        self.fecha_xml = datetime.datetime.combine(self.invoice_date, datetime.datetime.now(pytz.timezone(str(self.user_id.partner_id.tz))).time())-timedelta(hours=(datetime.datetime.now(pytz.timezone(str(self.user_id.partner_id.tz))).utcoffset().total_seconds()/3600)) if self.user_id.partner_id.tz else datetime.datetime.combine(self.invoice_date, datetime.datetime.now(pytz.timezone('America/Bogota')).time())-timedelta(hours=(datetime.datetime.now(pytz.timezone('America/Bogota')).utcoffset().total_seconds()/3600))
        if not self.fecha_entrega:
            self.fecha_entrega = datetime.datetime.combine(self.invoice_date, datetime.datetime.now(pytz.timezone(str(self.user_id.partner_id.tz))).time())-timedelta(hours=(datetime.datetime.now(pytz.timezone(str(self.user_id.partner_id.tz))).utcoffset().total_seconds()/3600)) if self.user_id.partner_id.tz else datetime.datetime.combine(self.invoice_date, datetime.datetime.now(pytz.timezone('America/Bogota')).time())-timedelta(hours=(datetime.datetime.now(pytz.timezone('America/Bogota')).utcoffset().total_seconds()/3600))
        if not self.invoice_date_due:
            self._onchange_invoice_date()
            self._recompute_payment_terms_lines()

        create_date = self._str_to_datetime(self.fecha_xml)
        deliver_date = self._str_to_datetime(self.fecha_entrega)

        key_data = '{}{}{}'.format(invoice.company_id.software_identification_code, invoice.company_id.software_pin, invoice.name)
        sha384 = hashlib.sha384()
        sha384.update(key_data.encode())
        software_security_code = sha384.hexdigest()

        # reconciled_vals = self._get_reconciled_info_JSON_values()
        # invoice_prepaids = []
        # for reconciled_val in reconciled_vals:
        #     move_line_pago = self.env['account.move.line'].sudo().search([('id', '=', reconciled_val.get('payment_id'))])
        #     mapa_prepaid={
        #         'id': reconciled_val.get('payment_id'),
        #         'paid_amount': reconciled_val.get('amount'),
        #         'currency_id': str(self.currency_id.name),
        #         'received_date': str(move_line_pago.date),
        #         'paid_date': str(move_line_pago.date),
        #         'paid_time': '12:00:00'
        #     }
        #     invoice_prepaids.append(mapa_prepaid)

        invoice_lines = []

        tax_exclusive_amount = 0
        self.total_withholding_amount = 0.0
        tax_total_values = {}
        ret_total_values = {}
        # Bloque de código para imitar la estructura requerida por el XML de la DIAN para los totales externos
        # a las líneas de la factura.
        for line_id in self.invoice_line_ids.filtered(lambda r: r.product_id and r.display_type not in ['note', 'comment'] and r.price_subtotal > 0.0):
            for tax in line_id.tax_ids:
                if tax.tributes == 'ZZ':
                    continue

                #Impuestos
                if '-' not in str(tax.amount) and tax.tributes != 'ZZ':
                    # Inicializa contador a cero para cada ID de impuesto
                    if tax.codigo_dian not in tax_total_values:
                        tax_total_values[tax.codigo_dian] = dict()
                        tax_total_values[tax.codigo_dian]['total'] = 0
                        tax_total_values[tax.codigo_dian]['info'] = dict()

                    # Suma al total de cada código, y añade información por cada tarifa.
                    if line_id.price_subtotal != 0:
                        price_subtotal_calc = line_id.price_subtotal
                    else:
                        taxes = False
                        if line_id.tax_line_id and line_id.tax_line_id != 'ZZ':
                            taxes = line_id.tax_line_id.compute_all(line_id.line_price_reference, line_id.currency_id, line_id.quantity,product=line_id.product_id,partner=self.partner_id)
                        price_subtotal_calc = taxes['total_excluded'] if taxes else line_id.quantity * line_id.line_price_reference

                    if tax.amount not in tax_total_values[tax.codigo_dian]['info']:
                        aux_total = tax_total_values[tax.codigo_dian]['total']
                        aux_total = aux_total + price_subtotal_calc * tax['amount'] / 100
                        aux_total = round(aux_total, 2)
                        tax_total_values[tax.codigo_dian]['total'] = aux_total
                        tax_total_values[tax.codigo_dian]['info'][tax.amount] = {
                            'taxable_amount': price_subtotal_calc,
                            'value': round(price_subtotal_calc * tax['amount'] / 100, 2),
                            'technical_name': tax.nombre_dian,
                        }

                    else:
                        aux_tax = tax_total_values[tax.codigo_dian]['info'][tax.amount]['value']
                        aux_total = tax_total_values[tax.codigo_dian]['total']
                        aux_taxable = tax_total_values[tax.codigo_dian]['info'][tax.amount]['taxable_amount']
                        aux_tax = aux_tax + price_subtotal_calc * tax['amount'] / 100
                        aux_total = aux_total + price_subtotal_calc * tax['amount'] / 100
                        aux_taxable = aux_taxable + price_subtotal_calc
                        aux_tax = round(aux_tax, 2)
                        aux_total = round(aux_total, 2)
                        aux_taxable = round(aux_taxable, 2)
                        tax_total_values[tax.codigo_dian]['info'][tax.amount]['value'] = aux_tax
                        tax_total_values[tax.codigo_dian]['total'] = aux_total
                        tax_total_values[tax.codigo_dian]['info'][tax.amount]['taxable_amount'] = aux_taxable

                #retenciones
                else:
                    if tax.tributes != 'ZZ':
                        # Inicializa contador a cero para cada ID de impuesto
                        if line_id.price_subtotal != 0:
                            price_subtotal_calc = line_id.price_subtotal
                        else:
                            taxes = False
                            if line_id.tax_line_id and line_id.tax_line_id != 'ZZ':
                                taxes = line_id.tax_line_id.compute_all(line_id.line_price_reference, line_id.currency_id, line_id.quantity,product=line_id.product_id,partner=self.partner_id)
                            price_subtotal_calc = taxes['total_excluded'] if taxes else line_id.quantity * line_id.line_price_reference

                        if tax.codigo_dian not in ret_total_values:
                            ret_total_values[tax.codigo_dian] = dict()
                            ret_total_values[tax.codigo_dian]['total'] = 0
                            ret_total_values[tax.codigo_dian]['info'] = dict()

                        # Suma al total de cada código, y añade información por cada tarifa.
                        if abs(tax.amount) not in ret_total_values[tax.codigo_dian]['info']:
                            aux_total = ret_total_values[tax.codigo_dian]['total']
                            aux_total = aux_total + price_subtotal_calc * abs(tax['amount']) / 100
                            aux_total = round(aux_total, 2)
                            ret_total_values[tax.codigo_dian]['total'] = abs(aux_total)

                            ret_total_values[tax.codigo_dian]['info'][abs(tax.amount)] = {
                                'taxable_amount': abs(price_subtotal_calc),
                                'value': abs(round(price_subtotal_calc * tax['amount'] / 100, 2)),
                                'technical_name': tax.nombre_dian,
                            }

                        else:
                            aux_tax = ret_total_values[tax.codigo_dian]['info'][abs(tax.amount)]['value']
                            aux_total = ret_total_values[tax.codigo_dian]['total']
                            aux_taxable = ret_total_values[tax.codigo_dian]['info'][abs(tax.amount)]['taxable_amount']
                            aux_tax = aux_tax + price_subtotal_calc * abs(tax['amount']) / 100
                            aux_total = aux_total + price_subtotal_calc * abs(tax['amount']) / 100
                            aux_taxable = aux_taxable + price_subtotal_calc
                            aux_tax = round(aux_tax, 2)
                            aux_total = round(aux_total, 2)
                            aux_taxable = round(aux_taxable, 2)
                            ret_total_values[tax.codigo_dian]['info'][abs(tax.amount)]['value'] = abs(aux_tax)
                            ret_total_values[tax.codigo_dian]['total'] = abs(aux_total)
                            ret_total_values[tax.codigo_dian]['info'][abs(tax.amount)]['taxable_amount'] = abs(aux_taxable)

        for ret in ret_total_values.items():
            self.total_withholding_amount += abs(ret[1]['total'])

        contador = 1
        total_impuestos=0
        for index, invoice_line_id in enumerate(self.invoice_line_ids.filtered(lambda r: r.product_id and r.display_type not in ['note', 'comment'] and r.price_subtotal > 0.0)):
            if invoice_line_id.price_unit>=0:
                if invoice_line_id.price_subtotal != 0:
                    price_subtotal_calc = invoice_line_id.price_subtotal
                else:
                    taxes = False
                    if invoice_line_id.tax_line_id and invoice_line_id.tax_line_id.tributes != 'ZZ':
                        taxes = invoice_line_id.tax_line_id.compute_all(invoice_line_id.line_price_reference, invoice_line_id.currency_id, invoice_line_id.quantity,product=invoice_line_id.product_id,partner=self.partner_id)
                    price_subtotal_calc = taxes['total_excluded'] if taxes else invoice_line_id.quantity * invoice_line_id.line_price_reference

                taxes = invoice_line_id.tax_ids
                tax_values = [price_subtotal_calc * tax['amount'] / 100 for tax in taxes]
                tax_values = [round(value, 2) for value in tax_values]
                tax_info = dict()


                for tax in invoice_line_id.tax_ids:
                    if '-' not in str(tax.amount) and tax.tributes != 'ZZ':
                        # Inicializa contador a cero para cada ID de impuesto
                        if tax.codigo_dian not in tax_info:
                            tax_info[tax.codigo_dian] = dict()
                            tax_info[tax.codigo_dian]['total'] = 0
                            tax_info[tax.codigo_dian]['info'] = dict()

                        # Suma al total de cada código, y añade información por cada tarifa para cada línea.
                        if invoice_line_id.price_subtotal != 0:
                            price_subtotal_calc = invoice_line_id.price_subtotal
                        else:
                            taxes = False
                            if invoice_line_id.tax_line_id:
                                taxes = invoice_line_id.tax_line_id.compute_all(invoice_line_id.line_price_reference, invoice_line_id.currency_id, invoice_line_id.quantity,product=invoice_line_id.product_id,partner=self.partner_id)
                            price_subtotal_calc = taxes['total_excluded'] if taxes else invoice_line_id.quantity * invoice_line_id.line_price_reference

                        total_impuestos += round(price_subtotal_calc * tax['amount'] / 100, 2)
                        if tax.amount not in tax_info[tax.codigo_dian]['info']:
                            aux_total = tax_info[tax.codigo_dian]['total']
                            aux_total = aux_total + price_subtotal_calc * tax['amount'] / 100
                            aux_total = round(aux_total, 2)
                            tax_info[tax.codigo_dian]['total'] = aux_total

                            tax_info[tax.codigo_dian]['info'][tax.amount] = {
                                'taxable_amount': price_subtotal_calc,
                                'value': round(price_subtotal_calc * tax['amount'] / 100, 2),
                                'technical_name': tax.nombre_dian,
                            }

                        else:
                            aux_tax = tax_info[tax.codigo_dian]['info'][tax.amount]['value']
                            aux_total = tax_info[tax.codigo_dian]['total']
                            aux_taxable = tax_info[tax.codigo_dian]['info'][tax.amount]['taxable_amount']
                            aux_tax = aux_tax + price_subtotal_calc * tax['amount'] / 100
                            aux_total = aux_total + price_subtotal_calc * tax['amount'] / 100
                            aux_taxable = aux_taxable + price_subtotal_calc
                            aux_tax = round(aux_tax, 2)
                            aux_total = round(aux_total, 2)
                            aux_taxable = round(aux_taxable, 2)
                            tax_info[tax.codigo_dian]['info'][tax.amount]['value'] = aux_tax
                            tax_info[tax.codigo_dian]['total'] = aux_total
                            tax_info[tax.codigo_dian]['info'][tax.amount]['taxable_amount'] = aux_taxable

                if invoice_line_id.discount:
                    discount_line = invoice_line_id.price_unit * invoice_line_id.quantity * invoice_line_id.discount / 100
                    discount_line = round(discount_line, 2)
                    discount_percentage = invoice_line_id.discount
                    base_discount = invoice_line_id.price_unit * invoice_line_id.quantity
                else:
                    discount_line = 0
                    discount_percentage = 0
                    base_discount = 0

                if invoice_line_id.product_id and not invoice_line_id.product_id.enable_charges or invoice_line_id.price_subtotal > 0.0:
                    mapa_line={
                        'id': index + contador,
                        'product_id': invoice_line_id.product_id,
                        'invoiced_quantity': invoice_line_id.quantity,
                        'uom_product_id': invoice_line_id.product_uom_id, # invoice_line_id.product_uom_id.codigo_fe_dian if invoice_line_id.product_uom_id else False,
                        'line_extension_amount': invoice_line_id.price_subtotal,
                        'item_description': saxutils.escape(invoice_line_id.name),
                        'price': (invoice_line_id.price_subtotal + discount_line)/ invoice_line_id.quantity,
                        'total_amount_tax': invoice.amount_tax,
                        'tax_info': tax_info,
                        'discount': discount_line,
                        'discount_percentage': discount_percentage,
                        'base_discount': base_discount,
                        'invoice_start_date': datetime.datetime.now().astimezone(pytz.timezone("America/Bogota")).strftime('%Y-%m-%d'),
                        'transmission_type_code': 1,
                        'transmission_description': 'Por operación',
                        'discount_text': self.calcular_texto_descuento(invoice_line_id.invoice_discount_text),
                        'discount_code': invoice_line_id.invoice_discount_text,
                        'multiplier_discount': discount_percentage,
                        'line_trade_sample_price': invoice_line_id.line_trade_sample_price,
                        'line_price_reference': (invoice_line_id.line_price_reference*invoice_line_id.quantity),
                        'brand_name': invoice_line_id.product_id.brand_id.name,
                        'model_name': invoice_line_id.product_id.model_id.name,
                    }
                    #if invoice_line_id.move_id.usa_aiu and invoice_line_id.product_id and invoice_line_id.product_id.tipo_aiu:
                    #    mapa_line.update({'note': 'Contrato de servicios AIU por concepto de: ' + invoice_line_id.move_id.objeto_contrato})
                    invoice_lines.append(mapa_line)

                    taxs = 0
                    if invoice_line_id.tax_ids.ids:
                        for item in invoice_line_id.tax_ids:
                            if not item.amount < 0:
                                taxs += 1
                                # si existe tax para una linea, entonces el price_subtotal
                                # de la linea se incluye en tax_exclusive_amount
                                if taxs > 1:  # si hay mas de un impuesto no se incluye  a la suma del tax_exclusive_amount
                                    pass
                                else:
                                    if line_id.price_subtotal != 0:
                                        tax_exclusive_amount += invoice_line_id.price_subtotal
                                    else:
                                        taxes = False
                                        if invoice_line_id.tax_line_id and line_id.tax_line_id != 'ZZ':
                                            taxes = invoice_line_id.tax_line_id.compute_all(invoice_line_id.line_price_reference, invoice_line_id.currency_id, invoice_line_id.quantity,product=invoice_line_id.product_id,partner=self.partner_id)
                                        price_subtotal_calc = taxes['total_excluded'] if taxes else invoice_line_id.quantity * invoice_line_id.line_price_reference
                                        tax_exclusive_amount += (price_subtotal_calc)
            else:
                contador -= 1
            #fin for
        cufe_cuds = ""
        cude_seed = ""
        qr = ""
        if self.move_type in ["out_invoice", "out_refund"]:
            cufe_cuds,qr,cude_seed = self.calcular_cufe(tax_total_values, invoice.amount_untaxed, total_impuestos)
        if self.move_type in ["in_invoice", "in_refund"]:
            cufe_cuds,qr,cude_seed = self.calcular_cuds(tax_total_values,invoice.amount_untaxed, total_impuestos)       
        tax_xml = self.generate_tax_xml(tax_total_values,self.currency_id.name)
        ret_xml = self.generate_ret_xml(ret_total_values,self.currency_id.name)
        line = self.create_invoice_lines(invoice_lines,self.currency_id.name)

        return {
                'cufe': cufe_cuds,
                'cude_seed': cude_seed,
                'qr':qr,
                'tax_xml': tax_xml,
                'ret_xml': ret_xml,
                'invoice_delivery_date': deliver_date.astimezone(pytz.timezone('America/Bogota')).strftime('%Y-%m-%d'),
                'invoice_delivery_time': deliver_date.astimezone(pytz.timezone('America/Bogota')).strftime('%H:%M:%S'),
                'invoice_issue_date': create_date.astimezone(pytz.timezone("America/Bogota")).strftime('%Y-%m-%d'),
                'invoice_issue_time': create_date.astimezone(pytz.timezone("America/Bogota")).strftime('%H:%M:%S-05:00'),
                'software_security_code': software_security_code,
                'line': line,
                'line_extension_amount': '{:.2f}'.format(invoice.amount_untaxed),
                'tax_inclusive_amount': '{:.2f}'.format(invoice.amount_untaxed + total_impuestos),
                'tax_exclusive_amount': '{:.2f}'.format(tax_exclusive_amount),
                'payable_amount': '{:.2f}'.format(invoice.amount_untaxed + total_impuestos), #invoice.amount_total + invoice.total_withholding_amount),
                #'payable_amount_discount': '{:.2f}'.format(invoice.amount_total + invoice.invoice_discount - invoice.invoice_charges_freight + invoice.total_withholding_amount),
            }


    def calcular_cufe(self, tax_total_values,amount_untaxed,total_impuestos):
        rec_active_resolution = (self.journal_id.sequence_id.dian_resolution_ids.filtered(lambda r: r.active_resolution))
        if rec_active_resolution:
            rec_dian_sequence = self.env["ir.sequence"].search([("id", "=", rec_active_resolution.sequence_id.id)])
        create_date = self._str_to_datetime(self.fecha_xml)
        tax_computed_values = {tax: value['total'] for tax, value in tax_total_values.items()}

        numfac = self.name
        fecfac = create_date.astimezone(pytz.timezone('America/Bogota')).strftime('%Y-%m-%d')
        horfac = create_date.astimezone(pytz.timezone('America/Bogota')).strftime('%H:%M:%S-05:00')
        valfac = '{:.2f}'.format(amount_untaxed)
        codimp1 = '01'
        valimp1 = '{:.2f}'.format(tax_computed_values.get('01', 0))
        codimp2 = '04'
        valimp2 = '{:.2f}'.format(tax_computed_values.get('04', 0))
        codimp3 = '03'
        valimp3 = '{:.2f}'.format(tax_computed_values.get('03', 0))
        valtot = '{:.2f}'.format(amount_untaxed+total_impuestos)
        contacto_compañia = self.company_id.partner_id
        nitofe = str(contacto_compañia.vat_co)
        if self.company_id.production:
            tipoambiente = '1'
        else:
            tipoambiente = '2'
        numadq = str(self.partner_id.vat_co) or str(self.partner_id.parent_id.vat_co)
        if self.move_type == 'out_invoice' and not self.is_debit_note:
            citec =  rec_active_resolution.technical_key #self.journal_id.company_resolucion_factura_id.clave_tecnica
        else:
            citec = self.company_id.software_pin

        total_otros_impuestos = sum([value for key, value in tax_computed_values.items() if key != '01'])
        iva = tax_computed_values.get('01', '0.00')

        cufe = (
                numfac + fecfac + horfac + valfac + codimp1 + valimp1 + codimp2 +
                valimp2 + codimp3 + valimp3 + valtot + nitofe + numadq + citec +
                tipoambiente
        )
        cufe_seed = cufe

        sha384 = hashlib.sha384()
        sha384.update(cufe.encode())
        cufe = sha384.hexdigest()

        qr_code = 'NumFac: {}\n' \
                  'FecFac: {}\n' \
                  'HorFac: {}\n' \
                  'NitFac: {}\n' \
                  'DocAdq: {}\n' \
                  'ValFac: {}\n' \
                  'ValIva: {}\n' \
                  'ValOtroIm: {:.2f}\n' \
                  'ValFacIm: {}\n' \
                  'CUFE: {}'.format(
                    numfac,
                    fecfac,
                    horfac,
                    nitofe,
                    numadq,
                    valfac,
                    iva,
                    total_otros_impuestos,
                    valtot,
                    cufe
                    )

        qr = pyqrcode.create(qr_code, error='L')        
        return cufe, qr.png_as_base64_str(scale=2),cufe_seed

    def calcular_cuds(self, tax_total_values, amount_untaxed, total_impuestos):    
        create_date = self._str_to_datetime(self.fecha_xml)
        tax_computed_values = {tax: value['total'] for tax, value in tax_total_values.items()}
        numfac = self.name
        fecfac = create_date.astimezone(pytz.timezone('America/Bogota')).strftime('%Y-%m-%d')
        horfac = create_date.astimezone(pytz.timezone('America/Bogota')).strftime('%H:%M:%S-05:00')
        valfac = '{:.2f}'.format(amount_untaxed)
        codimp1 = '01'
        valimp1 = '{:.2f}'.format(tax_computed_values.get('01', 0))
        valtot = '{:.2f}'.format(amount_untaxed+total_impuestos) if self.move_type != 'entry' else '{:.2f}'.format(self.amount_total)
        company_contact = self.company_id.partner_id
        nitofe = str(company_contact.vat_co)
        if self.company_id.production:
            tipoambiente = '1'
        else:
            tipoambiente = '2'
        numadq = str(self.partner_id.vat_co) or str(self.partner_id.parent_id.vat_co)
        citec = self.company_id.software_pin

        total_otros_impuestos = sum([value for key, value in tax_computed_values.items() if key != '01'])
        iva = tax_computed_values.get('01', '0.00')

        cuds = (
                numfac + fecfac + horfac + valfac + codimp1 + valimp1 + valtot + numadq + nitofe + citec +
                tipoambiente
        )
        cuds_seed = cuds

        sha384 = hashlib.sha384()
        sha384.update(cuds.encode())
        cuds = sha384.hexdigest()

        if not self.company_id.production:
            qr_code = 'NumFac: {}\n' \
                    'FecFac: {}\n' \
                    'HorFac: {}\n' \
                    'NitFac: {}\n' \
                    'DocAdq: {}\n' \
                    'ValFac: {}\n' \
                    'ValIva: {}\n' \
                    'ValOtroIm: {:.2f}\n' \
                    'ValFacIm: {}\n' \
                    'CUDS: {}\n' \
                    'https://catalogo-vpfe-hab.dian.gov.co/document/searchqr?documentkey={}'.format(
                    numfac,
                    fecfac,
                    horfac,
                    nitofe,
                    numadq,
                    valfac,
                    iva,
                    total_otros_impuestos,
                    valtot,
                    cuds,
                    cuds
                    )
        else:
            qr_code = 'NumFac: {}\n' \
                  'FecFac: {}\n' \
                  'HorFac: {}\n' \
                  'NitFac: {}\n' \
                  'DocAdq: {}\n' \
                  'ValFac: {}\n' \
                  'ValIva: {}\n' \
                  'ValOtroIm: {:.2f}\n' \
                  'ValFacIm: {}\n' \
                  'CUDS: {}\n' \
                  'https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey={}'.format(
                    numfac,
                    fecfac,
                    horfac,
                    nitofe,
                    numadq,
                    valfac,
                    iva,
                    total_otros_impuestos,
                    valtot,
                    cuds,
                    cuds
                    )

        qr = pyqrcode.create(qr_code, error='L')

        return cuds, qr.png_as_base64_str(scale=2),cuds_seed



    @api.model
    def generate_tax_xml(self,tax_total_values, currency_id):
        total_tax = 0 
        for tax_id, data in tax_total_values.items():
            total_tax += data['total']  # Add up the total amount of each tax.

        tax_total = ET.Element('cac:TaxTotal')
        # Create the TaxAmount element at the top
        ET.SubElement(tax_total, 'cbc:TaxAmount', {'currencyID': currency_id}).text = '%0.2f' % float(total_tax)
        ET.SubElement(tax_total, 'cbc:RoundingAmount', {'currencyID': currency_id}).text = "0"
        for tax_id, data in tax_total_values.items():
            for amount, info in data['info'].items():
                tax_subtotal = ET.SubElement(tax_total, 'cac:TaxSubtotal')
                ET.SubElement(tax_subtotal, 'cbc:TaxableAmount', {'currencyID': currency_id}).text = '%0.2f' % float(info['taxable_amount'])
                ET.SubElement(tax_subtotal, 'cbc:TaxAmount', {'currencyID': currency_id}).text = '%0.2f' % float(info['value'])
                tax_category = ET.SubElement(tax_subtotal, 'cac:TaxCategory')
                ET.SubElement(tax_category, 'cbc:Percent').text = '%0.2f' % float(amount)
                tax_scheme = ET.SubElement(tax_category, 'cac:TaxScheme')
                ET.SubElement(tax_scheme, 'cbc:ID').text = str(tax_id)
                ET.SubElement(tax_scheme, 'cbc:Name').text = str(info['technical_name'])
        tax_total = ET.tostring(tax_total, encoding='utf-8', method='xml')
        tax_total = tax_total.decode('utf-8')
        return tax_total

    @api.model
    def generate_ret_xml(self,ret_total_values,currency_id):
        if ret_total_values and self.move_type in ["out_invoice","in_invoice"] and self.is_debit_note == False:
            total_tax = 0  # Variable to store the sum of all taxes.

            for tax_id, data in ret_total_values.items():
                total_tax += data['total']  # Add up the total amount of each tax.

            with_tax_total = ET.Element('cac:WithholdingTaxTotal')
            # Create the TaxAmount element at the top
            ET.SubElement(with_tax_total, 'cbc:TaxAmount', {'currencyID': currency_id}).text = '%0.2f' % float(total_tax)

            for tax_id, data in ret_total_values.items():
                for amount, info in data['info'].items():
                    tax_subtotal = ET.SubElement(with_tax_total, 'cac:TaxSubtotal')
                    if tax_id == '06':
                        ET.SubElement(tax_subtotal, 'cbc:TaxableAmount', {'currencyID': currency_id}).text = '%0.2f' %  float(info['taxable_amount'])
                        ET.SubElement(tax_subtotal, 'cbc:TaxAmount', {'currencyID': currency_id}).text = '%0.2f' % float(info['value'])
                    else:
                        ET.SubElement(tax_subtotal, 'cbc:TaxableAmount', {'currencyID': currency_id}).text = '%0.3f' %  float(info['taxable_amount'])
                        ET.SubElement(tax_subtotal, 'cbc:TaxAmount', {'currencyID': currency_id}).text = '%0.3f' % float(info['value'])
                    tax_category = ET.SubElement(tax_subtotal, 'cac:TaxCategory')
                    if tax_id == '06':
                        ET.SubElement(tax_category, 'cbc:Percent').text = '%0.2f' % float(amount)
                    else:
                        ET.SubElement(tax_category, 'cbc:Percent').text = '%0.3f' % float(amount)

                    tax_scheme = ET.SubElement(tax_category, 'cac:TaxScheme')
                    ET.SubElement(tax_scheme, 'cbc:ID').text = str(tax_id)
                    ET.SubElement(tax_scheme, 'cbc:Name').text = str(info['technical_name'])

            with_tax_total = ET.tostring(with_tax_total, encoding='utf-8', method='xml')
            with_tax_total = with_tax_total.decode('utf-8')
        else:
            with_tax_total = " "
        return with_tax_total
    
    @api.model
    def create_invoice_lines(self, invoice_lines, currency_id):
        invoice_lines_tags = []  # Lista para almacenar las etiquetas XML de cada línea de factura

        for invoice_line in invoice_lines:
            if (self.move_type == "out_invoice" and not self.is_debit_note)  or (self.move_type == "in_invoice" and not self.is_debit_note):
                invoice_line_tag = ET.Element('cac:InvoiceLine')
            if  self.is_debit_note:
                invoice_line_tag = ET.Element('cac:DebitNoteLine')
            if self.move_type == "out_refund" or self.move_type == "in_refund":
                invoice_line_tag = ET.Element('cac:CreditNoteLine')
            ET.SubElement(invoice_line_tag, 'cbc:ID').text = str(int(invoice_line.get('id', 0)))
            ET.SubElement(invoice_line_tag, 'cbc:Note').text = str(invoice_line.get('note', ''))
            if (self.move_type == "out_invoice" and not self.is_debit_note)  or (self.move_type == "in_invoice" and not self.is_debit_note):
                if invoice_line.get('uom_product_id'):
                    ET.SubElement(invoice_line_tag, 'cbc:InvoicedQuantity', {'unitCode': "EA"}).text = str(invoice_line['invoiced_quantity']) #{'unitCode': invoice_line['uom_product_id'].name}).text = str(invoice_line['invoiced_quantity'])
                else:
                    ET.SubElement(invoice_line_tag, 'cbc:InvoicedQuantity', {'unitCode': "EA"}).text = str(invoice_line['invoiced_quantity'])
            if self.is_debit_note:
                if invoice_line.get('uom_product_id'):
                    ET.SubElement(invoice_line_tag, 'cbc:DebitedQuantity', {'unitCode': "EA"}).text = str(invoice_line['invoiced_quantity']) #{'unitCode': invoice_line['uom_product_id'].name}).text = str(invoice_line['invoiced_quantity'])
                else:
                    ET.SubElement(invoice_line_tag, 'cbc:DebitedQuantity', {'unitCode': "EA"}).text = str(invoice_line['invoiced_quantity'])
            if self.move_type == "out_refund" or self.move_type == "in_refund":
                if invoice_line.get('uom_product_id'):
                    ET.SubElement(invoice_line_tag, 'cbc:CreditedQuantity', {'unitCode': "EA"}).text = str(invoice_line['invoiced_quantity']) #{'unitCode': invoice_line['uom_product_id'].name}).text = str(invoice_line['invoiced_quantity'])
                else:
                    ET.SubElement(invoice_line_tag, 'cbc:CreditedQuantity', {'unitCode': "EA"}).text = str(invoice_line['invoiced_quantity'])
            ET.SubElement(invoice_line_tag, 'cbc:LineExtensionAmount', {'currencyID': currency_id}).text = str(invoice_line['line_extension_amount'])
            if self.move_type == "in_invoice" and not self.is_debit_note:
                invoice_period = ET.SubElement(invoice_line_tag, "cac:InvoicePeriod")
                ET.SubElement(invoice_period, "cbc:StartDate").text = str(invoice_line['invoice_start_date'])
                ET.SubElement(invoice_period, "cbc:DescriptionCode").text = str(invoice_line['transmission_type_code'])
                ET.SubElement(invoice_period, "cbc:Description").text = str(invoice_line['transmission_description'])
            if invoice_line['line_extension_amount'] == 0:
                pricing_ref = ET.SubElement(invoice_line_tag, 'cac:PricingReference')
                alt_condition_price = ET.SubElement(pricing_ref, 'cac:AlternativeConditionPrice')
                ET.SubElement(alt_condition_price, 'cbc:PriceAmount', {'currencyID': currency_id}).text = str(invoice_line['line_price_reference'])
                ET.SubElement(alt_condition_price, 'cbc:PriceTypeCode').text = str(invoice_line['line_trade_sample_price'])

            if float(invoice_line.get('line_extension_amount', 0)) > 0 and float(invoice_line.get('discount', 0)) > 0:
                amount_base = float(invoice_line['line_extension_amount']) + float(invoice_line['discount'])
                allowance_charge = ET.SubElement(invoice_line_tag, 'cac:AllowanceCharge')
                ET.SubElement(allowance_charge, 'cbc:ID').text = '1'
                ET.SubElement(allowance_charge, 'cbc:ChargeIndicator').text = 'false'
                ET.SubElement(allowance_charge, 'cbc:AllowanceChargeReasonCode').text = invoice_line.get('discount_code')
                ET.SubElement(allowance_charge, 'cbc:AllowanceChargeReason').text = invoice_line.get('discount_text')
                ET.SubElement(allowance_charge, 'cbc:MultiplierFactorNumeric').text = str(invoice_line.get('discount_percentage'))
                ET.SubElement(allowance_charge, 'cbc:Amount', {'currencyID': currency_id}).text = str(invoice_line.get('discount'))
                ET.SubElement(allowance_charge, 'cbc:BaseAmount', {'currencyID': currency_id}).text = str(amount_base)

            for tax_id, data in invoice_line['tax_info'].items():
                tax_total = ET.SubElement(invoice_line_tag, 'cac:TaxTotal')
                ET.SubElement(tax_total, 'cbc:TaxAmount', {'currencyID': currency_id}).text = str(data['total'])
                ET.SubElement(tax_total, 'cbc:RoundingAmount', {'currencyID': currency_id}).text = '0'
                for amount, info in data['info'].items():
                    tax_subtotal = ET.SubElement(tax_total, 'cac:TaxSubtotal')
                    ET.SubElement(tax_subtotal, 'cbc:TaxableAmount', {'currencyID': currency_id}).text = str(info['taxable_amount'])
                    ET.SubElement(tax_subtotal, 'cbc:TaxAmount', {'currencyID': currency_id}).text = str(info['value'])
                    tax_category = ET.SubElement(tax_subtotal, 'cac:TaxCategory')
                    ET.SubElement(tax_category, 'cbc:Percent').text = '{:0.2f}'.format(float(amount))
                    tax_scheme = ET.SubElement(tax_category, 'cac:TaxScheme')
                    ET.SubElement(tax_scheme, 'cbc:ID').text = tax_id
                    ET.SubElement(tax_scheme, 'cbc:Name').text = info['technical_name']

            item = ET.SubElement(invoice_line_tag, 'cac:Item')
            ET.SubElement(item, 'cbc:Description').text = invoice_line['item_description']
            standard_item_identification = ET.SubElement(item, 'cac:StandardItemIdentification')
            if self.move_type == "out_invoice" or self.move_type == "out_refund":
                ET.SubElement(standard_item_identification, 'cbc:ID', {'schemeID': '999'}).text = str(invoice_line['product_id'].default_code)
            if self.move_type == "in_invoice" or self.move_type == "in_refund":
                ET.SubElement(standard_item_identification, 'cbc:ID', {'schemeID': '999','schemeName':'Estándar de adopción del contribuyente'}).text = str(invoice_line['product_id'].default_code)

            price = ET.SubElement(invoice_line_tag, 'cac:Price')
            ET.SubElement(price, 'cbc:PriceAmount', {'currencyID': currency_id}).text = str(invoice_line['price'])
            if invoice_line.get('uom_product_id'):
                ET.SubElement(price, 'cbc:BaseQuantity', {'unitCode': "EA"}).text = str(invoice_line['invoiced_quantity']) #{'unitCode': invoice_line['uom_product_id'].name}).text = str(invoice_line['invoiced_quantity'])
            else:
                ET.SubElement(price, 'cbc:BaseQuantity', {'unitCode': "EA"}).text = str(invoice_line['invoiced_quantity'])

            invoice_lines_tags.append(invoice_line_tag)  # Agregar la etiqueta de la línea a la lista

        #return invoice_lines_tags
        xml_str = [ET.tostring(tag, encoding='utf-8', method='xml') for tag in invoice_lines_tags]

        _logger.info(xml_str)
        #xml_str = ET.tostring(invoice_lines_element, encoding='utf-8', method='xml')
        str_decoded = ''
        for byte_str in xml_str:
            str_decoded += byte_str.decode('utf-8')
            _logger.info(str_decoded)
        return str_decoded
    
    def AccountingCustomerParty(self,customer_data):
        nsmap = {
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
        }

        AccountingCustomerParty = etree.Element('cac:AccountingCustomerParty', nsmap=nsmap)
        
        AdditionalAccountID = etree.SubElement(AccountingCustomerParty, 'cbc:AdditionalAccountID')
        AdditionalAccountID.text = customer_data['invoice_customer_additional_account_id']
        
        Party = etree.SubElement(AccountingCustomerParty, 'cac:Party')
        
        PartyIdentification = etree.SubElement(Party, 'cac:PartyIdentification')
        ID = etree.SubElement(PartyIdentification, 'cbc:ID')
        
        if customer_data['invoice_customer_document_type'] == '31':
            ID.set('schemeID', customer_data['invoice_customer_identification_digit'])
            ID.set('schemeName', '31')
        else:
            ID.set('schemeName', customer_data['invoice_customer_document_type'])
        
        ID.text = customer_data['invoice_customer_identification']
        
        PartyName = etree.SubElement(Party, 'cac:PartyName')
        Name = etree.SubElement(PartyName, 'cbc:Name')
        Name.text = customer_data['invoice_customer_party_name']
        
        PhysicalLocation = etree.SubElement(Party, 'cac:PhysicalLocation')
        Address = etree.SubElement(PhysicalLocation, 'cac:Address')
        
        ID = etree.SubElement(Address, 'cbc:ID')
        ID.text = customer_data['invoice_customer_city_code']
        
        CityName = etree.SubElement(Address, 'cbc:CityName')
        CityName.text = customer_data['invoice_customer_city']
        
        PostalZone = etree.SubElement(Address, 'cbc:PostalZone')
        PostalZone.text = customer_data['invoice_customer_postal_code']
        
        CountrySubentity = etree.SubElement(Address, 'cbc:CountrySubentity')
        CountrySubentity.text = customer_data['invoice_customer_department']
        
        CountrySubentityCode = etree.SubElement(Address, 'cbc:CountrySubentityCode')
        CountrySubentityCode.text = customer_data['invoice_customer_department_code']
        
        AddressLine = etree.SubElement(Address, 'cac:AddressLine')
        Line = etree.SubElement(AddressLine, 'cbc:Line')
        Line.text = customer_data['invoice_customer_address_line']
        
        Country = etree.SubElement(Address, 'cac:Country')
        IdentificationCode = etree.SubElement(Country, 'cbc:IdentificationCode')
        IdentificationCode.text = customer_data['invoice_customer_country_code']
        
        Name = etree.SubElement(Country, 'cbc:Name')
        Name.set('languageID', 'es')
        Name.text = customer_data['invoice_customer_country']
        
        PartyTaxScheme = etree.SubElement(Party, 'cac:PartyTaxScheme')
        
        RegistrationName = etree.SubElement(PartyTaxScheme, 'cbc:RegistrationName')
        if not customer_data['invoice_registration_name']:
            RegistrationName.text = customer_data['invoice_customer_first_name'] + customer_data['invoice_customer_middle_name'] + customer_data['invoice_customer_family_name'] + customer_data['invoice_customer_family_last_name']
        else:
            RegistrationName.text = customer_data['invoice_registration_name']
        
        CompanyID = etree.SubElement(PartyTaxScheme, 'cbc:CompanyID')
        if customer_data['invoice_customer_document_type'] == '31':
            CompanyID.set('schemeAgencyID', '195')
            CompanyID.set('schemeAgencyName', 'CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)')
            CompanyID.set('schemeID', customer_data['invoice_customer_identification_digit'])
            CompanyID.set('schemeName', '31')
        else:
            CompanyID.set('schemeAgencyID', '195')
            CompanyID.set('schemeAgencyName', 'CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)')
            CompanyID.set('schemeName', customer_data['invoice_customer_document_type'])
        CompanyID.text = customer_data['invoice_customer_identification']
        
        TaxLevelCode = etree.SubElement(PartyTaxScheme, 'cbc:TaxLevelCode')
        TaxLevelCode.text = customer_data['invoice_customer_tax_level_code']
        
        TaxScheme = etree.SubElement(PartyTaxScheme, 'cac:TaxScheme')
        ID = etree.SubElement(TaxScheme, 'cbc:ID')
        ID.text = customer_data['invoice_customer_responsabilidad_tributaria']
        Name = etree.SubElement(TaxScheme, 'cbc:Name')
        Name.text = customer_data['invoice_customer_responsabilidad_tributaria_text']
        
        PartyLegalEntity = etree.SubElement(Party, 'cac:PartyLegalEntity')
        
        RegistrationName = etree.SubElement(PartyLegalEntity, 'cbc:RegistrationName')
        if not customer_data['invoice_registration_name']:
            RegistrationName.text = customer_data['invoice_customer_first_name'] + customer_data['invoice_customer_middle_name'] + customer_data['invoice_customer_family_name'] + customer_data['invoice_customer_family_last_name']
        else:
            RegistrationName.text = customer_data['invoice_registration_name']
        
        CompanyID = etree.SubElement(PartyLegalEntity, 'cbc:CompanyID')
        if customer_data['invoice_customer_document_type'] == '31':
            CompanyID.set('schemeAgencyID', '195')
            CompanyID.set('schemeAgencyName', 'CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)')
            CompanyID.set('schemeID', customer_data['invoice_customer_identification_digit'])
            CompanyID.set('schemeName', '31')
        else:
            CompanyID.set('schemeAgencyID', '195')
            CompanyID.set('schemeAgencyName', 'CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)')
            CompanyID.set('schemeName', customer_data['invoice_customer_document_type'])
        CompanyID.text = customer_data['invoice_customer_identification']
        
        CorporateRegistrationScheme = etree.SubElement(PartyLegalEntity, 'cac:CorporateRegistrationScheme')
        Name = etree.SubElement(CorporateRegistrationScheme, 'cbc:Name')
        Name.text = customer_data['invoice_customer_commercial_registration']
        
        Contact = etree.SubElement(Party, 'cac:Contact')
        Telephone = etree.SubElement(Contact, 'cbc:Telephone')
        Telephone.text = customer_data['invoice_customer_phone']
        ElectronicMail = etree.SubElement(Contact, 'cbc:ElectronicMail')
        ElectronicMail.text = customer_data['invoice_customer_email']
        
        return AccountingCustomerParty

    def AccountingSupplierParty(self,supplier_data):
        nsmap = {
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
        }

        AccountingSupplierParty = etree.Element('cac:AccountingSupplierParty', nsmap=nsmap)
        
        AdditionalAccountID = etree.SubElement(AccountingSupplierParty, 'cbc:AdditionalAccountID')
        AdditionalAccountID.set('schemeAgencyID', '195')
        AdditionalAccountID.text = supplier_data['invoice_supplier_additional_account_id']
        
        Party = etree.SubElement(AccountingSupplierParty, 'cac:Party')
        
        PartyName = etree.SubElement(Party, 'cac:PartyName')
        Name = etree.SubElement(PartyName, 'cbc:Name')
        Name.text = supplier_data['invoice_supplier_party_name']
        
        PhysicalLocation = etree.SubElement(Party, 'cac:PhysicalLocation')
        Address = etree.SubElement(PhysicalLocation, 'cac:Address')
        
        ID = etree.SubElement(Address, 'cbc:ID')
        ID.text = supplier_data['invoice_supplier_city_code']
        
        CityName = etree.SubElement(Address, 'cbc:CityName')
        CityName.text = supplier_data['invoice_supplier_city']
        
        PostalZone = etree.SubElement(Address, 'cbc:PostalZone')
        PostalZone.text = supplier_data['invoice_supplier_postal_code']
        
        CountrySubentity = etree.SubElement(Address, 'cbc:CountrySubentity')
        CountrySubentity.text = supplier_data['invoice_supplier_department']
        
        CountrySubentityCode = etree.SubElement(Address, 'cbc:CountrySubentityCode')
        CountrySubentityCode.text = supplier_data['invoice_supplier_department_code']
        
        AddressLine = etree.SubElement(Address, 'cac:AddressLine')
        Line = etree.SubElement(AddressLine, 'cbc:Line')
        Line.text = supplier_data['invoice_supplier_address_line']
        
        Country = etree.SubElement(Address, 'cac:Country')
        
        IdentificationCode = etree.SubElement(Country, 'cbc:IdentificationCode')
        IdentificationCode.text = 'CO'
        
        Name = etree.SubElement(Country, 'cbc:Name')
        Name.set('languageID', 'es')
        Name.text = 'Colombia'
        
        PartyTaxScheme = etree.SubElement(Party, 'cac:PartyTaxScheme')
        
        RegistrationName = etree.SubElement(PartyTaxScheme, 'cbc:RegistrationName')
        RegistrationName.text = supplier_data['invoice_supplier_party_name']
        
        CompanyID = etree.SubElement(PartyTaxScheme, 'cbc:CompanyID')
        CompanyID.set('schemeAgencyID', '195')
        CompanyID.set('schemeAgencyName', 'CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)')
        CompanyID.set('schemeID', supplier_data['invoice_supplier_identification_digit'])
        CompanyID.set('schemeName', '31')
        CompanyID.text = supplier_data['invoice_supplier_identification']
        
        TaxLevelCode = etree.SubElement(PartyTaxScheme, 'cbc:TaxLevelCode')
        TaxLevelCode.text = supplier_data['invoice_supplier_tax_level_code']
        
        RegistrationAddress = etree.SubElement(PartyTaxScheme, 'cac:RegistrationAddress')
        
        ID = etree.SubElement(RegistrationAddress, 'cbc:ID')
        ID.text = supplier_data['invoice_supplier_city_code']
        
        CityName = etree.SubElement(RegistrationAddress, 'cbc:CityName')
        CityName.text = supplier_data['invoice_supplier_city']
        
        PostalZone = etree.SubElement(RegistrationAddress, 'cbc:PostalZone')
        PostalZone.text = supplier_data['invoice_supplier_postal_code']
        
        CountrySubentity = etree.SubElement(RegistrationAddress, 'cbc:CountrySubentity')
        CountrySubentity.text = supplier_data['invoice_supplier_department']
        
        CountrySubentityCode = etree.SubElement(RegistrationAddress, 'cbc:CountrySubentityCode')
        CountrySubentityCode.text = supplier_data['invoice_supplier_department_code']
        
        AddressLine = etree.SubElement(RegistrationAddress, 'cac:AddressLine')
        Line = etree.SubElement(AddressLine, 'cbc:Line')
        Line.text = supplier_data['invoice_supplier_address_line']
        
        Country = etree.SubElement(RegistrationAddress, 'cac:Country')
        
        IdentificationCode = etree.SubElement(Country, 'cbc:IdentificationCode')
        IdentificationCode.text = 'CO'
        
        Name = etree.SubElement(Country, 'cbc:Name')
        Name.set('languageID', 'es')
        Name.text = 'Colombia'
        
        TaxScheme = etree.SubElement(PartyTaxScheme, 'cac:TaxScheme')
        
        ID = etree.SubElement(TaxScheme, 'cbc:ID')
        ID.text = supplier_data['invoice_supplier_responsabilidad_tributaria']
        
        Name = etree.SubElement(TaxScheme, 'cbc:Name')
        Name.text = supplier_data['invoice_supplier_responsabilidad_tributaria_text']
        
        PartyLegalEntity = etree.SubElement(Party, 'cac:PartyLegalEntity')
        
        RegistrationName = etree.SubElement(PartyLegalEntity, 'cbc:RegistrationName')
        RegistrationName.text = supplier_data['invoice_supplier_party_name']
        
        CompanyID = etree.SubElement(PartyLegalEntity, 'cbc:CompanyID')
        CompanyID.set('schemeAgencyID', '195')
        CompanyID.set('schemeAgencyName', 'CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)')
        CompanyID.set('schemeID', supplier_data['invoice_supplier_identification_digit'])
        CompanyID.set('schemeName', '31')
        CompanyID.text = supplier_data['invoice_supplier_identification']
        
        CorporateRegistrationScheme = etree.SubElement(PartyLegalEntity, 'cac:CorporateRegistrationScheme')
        
        ID = etree.SubElement(CorporateRegistrationScheme, 'cbc:ID')
        ID.text = supplier_data['invoice_prefix']
        
        Name = etree.SubElement(CorporateRegistrationScheme, 'cbc:Name')
        Name.text = supplier_data['invoice_supplier_commercial_registration']
        
        Contact = etree.SubElement(Party, 'cac:Contact')
        
        Telephone = etree.SubElement(Contact, 'cbc:Telephone')
        Telephone.text = supplier_data['invoice_supplier_phone']
        
        ElectronicMail = etree.SubElement(Contact, 'cbc:ElectronicMail')
        ElectronicMail.text = supplier_data['invoice_supplier_email']
        
        return AccountingSupplierParty

class InvoiceLine(models.Model):
    _inherit = "account.move.line"
    #region Campos
    line_price_reference = fields.Float(string='Precio de referencia')
    line_trade_sample_price = fields.Selection(string='Tipo precio de referencia',
                                               related='move_id.trade_sample_price')
    line_trade_sample = fields.Boolean(string='Muestra comercial', related='move_id.invoice_trade_sample')
    invoice_discount_text = fields.Selection(
        selection=[
            ('00', 'Descuento no condicionado'),
            ('01', 'Descuento condicionado')
        ],
        string='Motivo de Descuento',
    )
    #endregion

    # region Se agrega en el onchange_product_id la asignación al precio de referencia
    @api.onchange('product_id')
    def _onchange_product_id(self):
        for line in self:
            if not line.product_id or line.display_type in ('line_section', 'line_note'):
                continue

            line.name = line._get_computed_name()
            line.account_id = line._get_computed_account()
            line.tax_ids = line._get_computed_taxes()
            line.product_uom_id = line._get_computed_uom()
            line.price_unit = line._get_computed_price_unit()

            # Manage the fiscal position after that and adapt the price_unit.
            # E.g. mapping a price-included-tax to a price-excluded-tax must
            # remove the tax amount from the price_unit.
            # However, mapping a price-included tax to another price-included tax must preserve the balance but
            # adapt the price_unit to the new tax.
            # E.g. mapping a 10% price-included tax to a 20% price-included tax for a price_unit of 110 should preserve
            # 100 as balance but set 120 as price_unit.
            if line.tax_ids and line.move_id.fiscal_position_id:
                line.price_unit = line._get_price_total_and_subtotal()['price_subtotal']
                line.tax_ids = line.move_id.fiscal_position_id.map_tax(line.tax_ids)
                accounting_vals = line._get_fields_onchange_subtotal(price_subtotal=line.price_unit,
                                                                     currency=line.move_id.company_currency_id)
                balance = accounting_vals['debit'] - accounting_vals['credit']
                line.price_unit = line._get_fields_onchange_balance(price_subtotal=line.price_unit,
                                                                     currency=line.move_id.company_currency_id).get('price_unit', line.price_unit)

            # Convert the unit price to the invoice's currency.
            company = line.move_id.company_id
            line.price_unit = company.currency_id._convert(line.price_unit, line.move_id.currency_id, company,
                                                           line.move_id.date)
            line.line_price_reference = line.price_unit

        if len(self) == 1:
            return {'domain': {'product_uom_id': [('category_id', '=', self.product_uom_id.category_id.id)]}}
    #endregion

    #region Recalcula el price_unit dependiendo de la unidad de medida
    @api.onchange('product_uom_id')
    def _onchange_uom_id(self):
        ''' Recompute the 'price_unit' depending of the unit of measure. '''
        price_unit = self._get_computed_price_unit()

        # See '_onchange_product_id' for details.
        taxes = self._get_computed_taxes()
        if taxes and self.move_id.fiscal_position_id:
            price_subtotal = self._get_price_total_and_subtotal(price_unit=price_unit, taxes=taxes)['price_subtotal']
            accounting_vals = self._get_fields_onchange_subtotal(price_subtotal=price_subtotal,
                                                       currency=self.move_id.company_currency_id)
            balance = accounting_vals['debit'] - accounting_vals['credit']
            price_unit = self._get_fields_onchange_balance(price_subtotal=price_subtotal,currency=self.move_id.company_currency_id).get("price_unit",price_unit)
        # Convert the unit price to the invoice's currency.
        company = self.move_id.company_id
        self.price_unit = company.currency_id._convert(price_unit, self.move_id.currency_id, company, self.move_id.date)
        self.line_price_reference = self.price_unit
    #endregion
