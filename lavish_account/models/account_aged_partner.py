# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, _lt
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import format_date

from odoo.tools import float_is_zero
from datetime import datetime
from dateutil.relativedelta import relativedelta

class AccountReport(models.AbstractModel):
    _inherit = 'account.report'
    
    filter_accounts = None

    ####################################################
    # OPTIONS: accounts
    ####################################################

    @api.model
    def _get_filter_accounts(self):
        account_type = self.env.context.get('model',None)
        if account_type != 'account.aged.payable' and account_type != 'account.aged.receivable':
            return self.env['account.account'].with_context(active_test=False).search([
                ('company_id', 'in', self.env.user.company_ids.ids or [self.env.company.id])
            ], order="company_id, code, name")
        else:
            return self.env['account.account'].with_context(active_test=False).search([
                ('company_id', 'in', self.env.user.company_ids.ids or [self.env.company.id]),
                ('internal_type','=',account_type.split('.')[2])
            ], order="company_id, code, name")

    @api.model
    def _init_filter_accounts(self, options, previous_options=None):
        if self.filter_accounts is None:
            return

        previous_company = False
        if previous_options and previous_options.get('accounts'):
            account_map = dict((opt['id'], opt['selected']) for opt in previous_options['accounts'] if opt['id'] != 'divider' and 'selected' in opt)
        else:
            account_map = {}
        options['accounts'] = []

        group_header_displayed = False
        default_group_ids = []
        
        for j in self._get_filter_accounts():
            if j.company_id != previous_company:
                options['accounts'].append({'id': 'divider', 'name': j.company_id.name})
                previous_company = j.company_id
            options['accounts'].append({
                'id': j.id,
                'name': j.name,
                'code': j.code,                
                'selected': account_map.get(j.id, j.id in default_group_ids),
            })

    @api.model
    def _get_options_accounts(self, options):
        return [
            account for account in options.get('accounts', []) if
            not account['id'] in ('divider', 'group') and account['selected']
        ]

    @api.model
    def _get_options_accounts_domain(self, options):
        # retorna para filtrar la entidad account_account
        selected_accounts = self._get_options_accounts(options)
        return selected_accounts and [('account_id', 'in', [j['id'] for j in selected_accounts])] or []

    @api.model
    def _get_options_domain(self, options):
        domain = super(AccountReport, self)._get_options_domain(options)        
        domain += self._get_options_accounts_domain(options)
        return domain

class AccountAgedPartner(models.AbstractModel):
    _inherit = "account.aged.partner"

    filter_accounts = True

    supplier_invoice_number = fields.Char(string='Nº de factura del proveedor')

    @api.model
    def _get_column_details(self, options):
        columns = [
            self._header_column(),
            self._field_column('report_date'),
            self._field_column('move_ref'),
            self._field_column('supplier_invoice_number'),

            self._field_column('account_name', name=_("Account"), ellipsis=True),
            self._field_column('expected_pay_date'),
            self._field_column('period0', name=_("As of: %s", format_date(self.env, options['date']['date_to']))),
            self._field_column('period1', sortable=True),
            self._field_column('period2', sortable=True),
            self._field_column('period3', sortable=True),
            self._field_column('period4', sortable=True),
            self._field_column('period5', sortable=True),
            self._custom_column(  # Avoid doing twice the sub-select in the view
                name=_('Total'),
                classes=['number'],
                formatter=self.format_value,
                getter=(
                    lambda v: v['period0'] + v['period1'] + v['period2'] + v['period3'] + v['period4'] + v['period5']),
                sortable=True,
            ),
        ]

        if self.user_has_groups('base.group_multi_currency'):
            columns[2:2] = [
                self._field_column('amount_currency'),
                self._field_column('currency_id'),
            ]
        return columns

    @api.model
    def _get_sql(self):
        options = self.env.context['report_options']
        query = ("""
                SELECT
                    {move_line_fields},
                    account_move_line.amount_currency as amount_currency,
                    account_move_line.partner_id AS partner_id,
                    partner.name AS partner_name,
                    COALESCE(trust_property.value_text, 'normal') AS partner_trust,
                    COALESCE(account_move_line.currency_id, journal.currency_id) AS report_currency_id,
                    account_move_line.payment_id AS payment_id,
                    COALESCE(account_move_line.date_maturity, account_move_line.date) AS report_date,
                    account_move_line.expected_pay_date AS expected_pay_date,
                    move.move_type AS move_type,
                    move.name AS move_name,
                    move.ref AS move_ref,
                    COALESCE(move.supplier_invoice_number,'') AS supplier_invoice_number,
                    account.code || ' ' || account.name AS account_name,
                    account.code AS account_code,""" + ','.join([("""
                    CASE WHEN period_table.period_index = {i}
                    THEN %(sign)s * ROUND((
                        account_move_line.balance - COALESCE(SUM(part_debit.amount), 0) + COALESCE(SUM(part_credit.amount), 0)
                    ) * currency_table.rate, currency_table.precision)
                    ELSE 0 END AS period{i}""").format(i=i) for i in range(6)]) + """
                FROM account_move_line
                JOIN account_move move ON account_move_line.move_id = move.id
                JOIN account_journal journal ON journal.id = account_move_line.journal_id
                JOIN account_account account ON account.id = account_move_line.account_id
                LEFT JOIN res_partner partner ON partner.id = account_move_line.partner_id
                LEFT JOIN ir_property trust_property ON (
                    trust_property.res_id = 'res.partner,'|| account_move_line.partner_id
                    AND trust_property.name = 'trust'
                    AND trust_property.company_id = account_move_line.company_id
                )
                JOIN {currency_table} ON currency_table.company_id = account_move_line.company_id
                LEFT JOIN LATERAL (
                    SELECT part.amount, part.debit_move_id
                    FROM account_partial_reconcile part
                    WHERE part.max_date <= %(date)s
                ) part_debit ON part_debit.debit_move_id = account_move_line.id
                LEFT JOIN LATERAL (
                    SELECT part.amount, part.credit_move_id
                    FROM account_partial_reconcile part
                    WHERE part.max_date <= %(date)s
                ) part_credit ON part_credit.credit_move_id = account_move_line.id
                JOIN {period_table} ON (
                    period_table.date_start IS NULL
                    OR COALESCE(account_move_line.date_maturity, account_move_line.date) <= DATE(period_table.date_start)
                )
                AND (
                    period_table.date_stop IS NULL
                    OR COALESCE(account_move_line.date_maturity, account_move_line.date) >= DATE(period_table.date_stop)
                )
                WHERE account.internal_type = %(account_type)s
                AND account.exclude_from_aged_reports IS NOT TRUE
                GROUP BY account_move_line.id, partner.id, trust_property.id, journal.id, move.id, account.id,
                         period_table.period_index, currency_table.rate, currency_table.precision
                HAVING ROUND(account_move_line.balance - COALESCE(SUM(part_debit.amount), 0) + COALESCE(SUM(part_credit.amount), 0), currency_table.precision) != 0
            """).format(
            move_line_fields=self._get_move_line_fields('account_move_line'),
            currency_table=self.env['res.currency']._get_query_currency_table(options),
            period_table=self._get_query_period_table(options),
        )
        params = {
            'account_type': options['filter_account_type'],
            'sign': 1 if options['filter_account_type'] == 'receivable' else -1,
            'date': options['date']['date_to'],
        }
        return self.env.cr.mogrify(query, params).decode(self.env.cr.connection.encoding)