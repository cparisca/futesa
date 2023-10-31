from odoo import models, api, _, _lt, fields
from odoo.tools.misc import format_date
from datetime import timedelta

from collections import defaultdict

class ReportPartnerLedger(models.AbstractModel):
    _inherit = "account.partner.ledger"

    @api.model
    def _get_lines_without_partner(self, options, expanded_partner=None, offset=0, limit=0):
        ''' Get the detail of lines without partner reconciled with a line with a partner. Those lines should be
        considered as belonging the partner for the reconciled amount as it may clear some of the partner invoice/bill
        and they have to be accounted in the partner balance.'''

        params = []
        if expanded_partner:
            partner_clause = '= %s'
            params = [expanded_partner.id] + params
        else:
            partner_clause = 'IS NOT NULL'
        new_options = self._get_options_without_partner(options)
        params += [options['date']['date_from'], options['date']['date_to']]
        tables, where_clause, where_params = self._query_get(new_options, domain=[])
        params += where_params + [offset]
        limit_clause = ''
        if limit != 0:
            params += [limit]
            limit_clause = "LIMIT %s"
        query = '''
                SELECT
                    account_move_line.id,
                    account_move_line.date,
                    account_move_line.date_maturity,
                    account_move_line.name,
                    account_move_line.ref,
                    account_move_line.company_id,
                    account_move_line.account_id,
                    account_move_line.payment_id,
                    aml_with_partner.partner_id,
                    account_move_line.currency_id,
                    account_move_line.amount_currency,
                    account_move_line.matching_number,
                    CASE WHEN aml_with_partner.balance > 0 THEN 0 ELSE partial.amount END AS debit,
                    CASE WHEN aml_with_partner.balance < 0 THEN 0 ELSE partial.amount END AS credit,
                    CASE WHEN aml_with_partner.balance > 0 THEN -partial.amount ELSE partial.amount END AS balance,
                    account_move_line.move_name             AS move_name,
                    account_move_encab.move_type            AS move_type,
                    account_move_encab.invoice_date         AS move_invoice_date,
                    account.code                            AS account_code,
                    account.name                            AS account_name,
                    journal.code                            AS journal_code,
                    journal.name                            AS journal_name,
                    full_rec.name                           AS full_rec_name
                FROM {tables},
                    account_partial_reconcile partial
                    LEFT JOIN account_full_reconcile full_rec ON full_rec.id = partial.full_reconcile_id,
                    account_move_line aml_with_partner
                    LEFT JOIN "account_move" AS "account_move_encab" ON ("aml_with_partner"."move_id" = "account_move_encab"."id"),
                    account_journal journal,
                    account_account account
                WHERE (account_move_line.id = partial.debit_move_id OR account_move_line.id = partial.credit_move_id)
                   AND account_move_line.partner_id IS NULL
                   AND (aml_with_partner.id = partial.debit_move_id OR aml_with_partner.id = partial.credit_move_id)
                   AND aml_with_partner.partner_id {partner_clause}
                   AND journal.id = account_move_line.journal_id
                   AND account.id = account_move_line.account_id
                   AND partial.max_date BETWEEN %s AND %s
                   AND {where_clause}
                ORDER BY account_move_line.date, account_move_line.id
                OFFSET %s
                {limit_clause}
            '''.format(tables=tables, partner_clause=partner_clause, where_clause=where_clause,
                       limit_clause=limit_clause)

        return query, params

    @api.model
    def _get_query_amls(self, options, expanded_partner=None, offset=None, limit=None):
        ''' Construct a query retrieving the account.move.lines when expanding a report line with or without the load
        more.
        :param options:             The report options.
        :param expanded_partner:    The res.partner record corresponding to the expanded line.
        :param offset:              The offset of the query (used by the load more).
        :param limit:               The limit of the query (used by the load more).
        :return:                    (query, params)
        '''
        unfold_all = options.get('unfold_all') or (self._context.get('print_mode') and not options['unfolded_lines'])

        # Get sums for the account move lines.
        # period: [('date' <= options['date_to']), ('date', '>=', options['date_from'])]
        if expanded_partner is not None:
            domain = [('partner_id', '=', expanded_partner.id)]
        elif unfold_all:
            domain = []
        elif options['unfolded_lines']:
            domain = [('partner_id', 'in', [int(line[8:]) for line in options['unfolded_lines']])]

        new_options = self._get_options_sum_balance(options)
        tables, where_clause, where_params = self._query_get(new_options, domain=domain)
        ct_query = self.env['res.currency']._get_query_currency_table(options)

        query = '''
                SELECT
                    account_move_line.id,
                    account_move_line.date,
                    account_move_line.date_maturity,
                    account_move_line.name,
                    account_move_line.ref,
                    account_move_line.company_id,
                    account_move_line.account_id,
                    account_move_line.payment_id,
                    account_move_line.partner_id,
                    account_move_line.currency_id,
                    account_move_line.amount_currency,
                    account_move_line.matching_number,
                    ROUND(account_move_line.debit * currency_table.rate, currency_table.precision)   AS debit,
                    ROUND(account_move_line.credit * currency_table.rate, currency_table.precision)  AS credit,
                    ROUND(account_move_line.balance * currency_table.rate, currency_table.precision) AS balance,
                    account_move_line.move_name             AS move_name,
                    company.currency_id                     AS company_currency_id,
                    partner.name                            AS partner_name,
                    account_move_encab.move_type            AS move_type,
                    account_move_encab.invoice_date         AS move_invoice_date,
                    account.code                            AS account_code,
                    account.name                            AS account_name,
                    journal.code                            AS journal_code,
                    journal.name                            AS journal_name
                FROM %s
                LEFT JOIN %s ON currency_table.company_id = account_move_line.company_id
                LEFT JOIN "account_move" AS "account_move_encab" ON ("account_move_line"."move_id" = "account_move_encab"."id")
                LEFT JOIN res_company company               ON company.id = account_move_line.company_id
                LEFT JOIN res_partner partner               ON partner.id = account_move_line.partner_id
                LEFT JOIN account_account account           ON account.id = account_move_line.account_id
                LEFT JOIN account_journal journal           ON journal.id = account_move_line.journal_id
                WHERE %s
                ORDER BY account_move_line.date, account_move_line.id
            ''' % (tables, ct_query, where_clause)

        if offset:
            query += ' OFFSET %s '
            where_params.append(offset)
        if limit:
            query += ' LIMIT %s '
            where_params.append(limit)

        return query, where_params

    @api.model
    def _get_report_line_partner(self, options, partner, initial_balance, debit, credit, balance):
        company_currency = self.env.company.currency_id
        unfold_all = self._context.get('print_mode') and not options.get('unfolded_lines')

        columns = [
            {'name': self.format_value(initial_balance), 'class': 'number'},
            {'name': self.format_value(debit), 'class': 'number'},
            {'name': self.format_value(credit), 'class': 'number'},
        ]
        if self.user_has_groups('base.group_multi_currency'):
            columns.append({'name': ''})
        columns.append({'name': self.format_value(balance), 'class': 'number'})

        return {
            'id': 'partner_%s' % (partner.id if partner else 0),
            'partner_id': partner.id if partner else None,
            'name': partner is not None and (partner.name or '')[:128] or _('Unknown Partner'),
            'columns': columns,
            'level': 2,
            'trust': partner.trust if partner else None,
            'unfoldable': not company_currency.is_zero(debit) or not company_currency.is_zero(credit),
            'unfolded': 'partner_%s' % (partner.id if partner else 0) in options['unfolded_lines'] or unfold_all,
            'colspan': 8,
        }

    @api.model
    def _get_report_line_move_line(self, options, partner, aml, cumulated_init_balance, cumulated_balance):
        if aml['payment_id']:
            caret_type = 'account.payment'
        else:
            caret_type = 'account.move'

        date_maturity = aml['date_maturity'] and format_date(self.env, fields.Date.from_string(aml['date_maturity']))
        columns = [
            {'name': aml['move_invoice_date']},
            {'name': aml['journal_code']},
            {'name': aml['account_code']},
            {'name': self._format_aml_name(aml['name'], aml['ref'], aml['move_name']),
             'class': 'o_account_report_line_ellipsis'},
            {'name': aml['name']},
            {'name': date_maturity or '', 'class': 'date'},
            {'name': aml['matching_number'] or ''},
            {'name': self.format_value(cumulated_init_balance), 'class': 'number'},
            {'name': self.format_value(aml['debit'], blank_if_zero=True), 'class': 'number'},
            {'name': self.format_value(aml['credit'], blank_if_zero=True), 'class': 'number'},
        ]
        if self.user_has_groups('base.group_multi_currency'):
            if aml['currency_id']:
                currency = self.env['res.currency'].browse(aml['currency_id'])
                formatted_amount = self.format_value(aml['amount_currency'], currency=currency, blank_if_zero=True)
                columns.append({'name': formatted_amount, 'class': 'number'})
            else:
                columns.append({'name': ''})
        columns.append({'name': self.format_value(cumulated_balance), 'class': 'number'})
        return {
            'id': aml['id'],
            'parent_id': 'partner_%s' % (partner.id if partner else 0),
            'name': format_date(self.env, aml['date']),
            'class': 'text' + aml.get('class', ''),  # do not format as date to prevent text centering
            'columns': columns,
            'caret_options': caret_type,
            'level': 2,
        }

    @api.model
    def _get_report_line_load_more(self, options, partner, offset, remaining, progress):
        return {
            'id': 'loadmore_%s' % (partner.id if partner else 0),
            'offset': offset,
            'progress': progress,
            'remaining': remaining,
            'class': 'o_account_reports_load_more text-center',
            'parent_id': 'partner_%s' % (partner.id if partner else 0),
            'name': _('Load more... (%s remaining)', remaining),
            'colspan': 11 if self.user_has_groups('base.group_multi_currency') else 10,
            'columns': [{}],
        }

    @api.model
    def _get_report_line_total(self, options, initial_balance, debit, credit, balance):
        columns = [
            {'name': self.format_value(initial_balance), 'class': 'number'},
            {'name': self.format_value(debit), 'class': 'number'},
            {'name': self.format_value(credit), 'class': 'number'},
        ]
        if self.user_has_groups('base.group_multi_currency'):
            columns.append({'name': ''})
        columns.append({'name': self.format_value(balance), 'class': 'number'})
        return {
            'id': 'partner_ledger_total_%s' % self.env.company.id,
            'name': _('Total'),
            'class': 'total',
            'level': 1,
            'columns': columns,
            'colspan': 7,
        }

    def _get_columns_name(self, options):
        columns = [
            {},
            {'name': _('Fecha factura')},
            {'name': _('JRNL')},
            {'name': _('Account')},
            {'name': _('Ref')},
            {'name': _('Etiqueta')},
            {'name': _('Due Date'), 'class': 'date'},
            {'name': _('Matching Number')},
            {'name': _('Initial Balance'), 'class': 'number'},
            {'name': _('Debit'), 'class': 'number'},
            {'name': _('Credit'), 'class': 'number'}]

        if self.user_has_groups('base.group_multi_currency'):
            columns.append({'name': _('Amount Currency'), 'class': 'number'})

        columns.append({'name': _('Balance'), 'class': 'number'})

        return columns
