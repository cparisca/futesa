from odoo import api, fields, models,  _
from odoo.exceptions import RedirectWarning, UserError, ValidationError, AccessError
from odoo.tools import float_compare, float_is_zero, date_utils, email_split, email_re, html_escape, is_html_empty
from odoo.tools.misc import formatLang, format_date, get_lang
from odoo.osv import expression
import logging
from datetime import date, timedelta
from collections import defaultdict
from contextlib import contextmanager
from itertools import zip_longest
from hashlib import sha256
from json import dumps

import ast
import json
import re
import warnings

def calc_check_digits(number):
    """Calculate the extra digits that should be appended to the number to make it a valid number.
    Source: python-stdnum iso7064.mod_97_10.calc_check_digits
    """
    number_base10 = ''.join(str(int(x, 36)) for x in number)
    checksum = int(number_base10) % 97
    return '%02d' % ((98 - 100 * checksum) % 97)
class Hr_payslip(models.Model):
    _name  = 'hr.payslip'
    _inherit = ['hr.payslip', 'sequence.mixin']
    _sequence_index = "journal_id"
    _sequence_field = "number"
    _sequence_date_field = "date_to"

    posted_before = fields.Boolean(help="Technical field for knowing if the move has been posted before", copy=False)
    journal_struct_id = fields.Many2one('account.journal', store=True, index=True, string='Salary Journal', domain="[('company_id', '=', company_id)]")
    number = fields.Char(string='Number', copy=False, compute='_compute_name_slip', readonly=False, store=True, index=True, tracking=True)
    highest_name = fields.Char(compute='_compute_highest_name')
    show_name_warning = fields.Boolean(store=False)
    journal_id = fields.Many2one('account.journal', related="struct_id.journal_id", string='Salary Journal', store=True, domain="[('company_id', '=', company_id)]")
    to_check = fields.Boolean(
        string='Para verificar',
        tracking=True,
        help="Si esta casilla de verificación está marcada, significa que el usuario no estaba seguro de todo lo relacionado"
              "información en el momento de la creación de la mudanza y que la mudanza necesita ser"
              "comprobado de nuevo",
    )

    def init(self):
        super().init()
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS hr_payslip_journal_struct_id_to_check_idx
             ON hr_payslip(journal_id) WHERE to_check = true;
        """)

    @property
    def _sequence_monthly_regex(self):
        return self.journal_id.sequence_override_regex or super()._sequence_monthly_regex

    @property
    def _sequence_yearly_regex(self):
        return self.journal_id.sequence_override_regex or super()._sequence_yearly_regex

    @property
    def _sequence_fixed_regex(self):
        return self.journal_id.sequence_override_regex or super()._sequence_fixed_regex


    @api.depends('state', 'journal_id', 'date_to')
    def _compute_name_slip(self):
        #self._onchange_journal()
        def journal_key(move):
            return (move.journal_id, move.journal_id.refund_sequence)

        def date_key(move):
            return (move.date_to.year, move.date_to.month)

        grouped = defaultdict(  # key: journal_id, move_type
            lambda: defaultdict(  # key: first adjacent (date_to.year, date_to.month)
                lambda: {
                    'records': self.env['hr.payslip'],
                    'format': False,
                    'format_values': False,
                    'reset': False
                }
            )
        )
        self = self.sorted(lambda m: (m.date_to, m.number or '', m.id))

        # Group the moves by journal and month
        for move in self:
            move_has_name = move.number and move.number != '/'
            if move_has_name or move.state not in  ('done','paid'):
                try:
                    if not move.posted_before:
                        # The move was never posted, so the number can potentially be changed.
                        move._constrains_date_sequence()
                    # Either the move was posted before, or the number already matches the date_to (or no number or date_to).
                    # We can skip recalculating the number when either
                    # - the move already has a number, or
                    # - the move has no number, but is in a period with other moves (so number should be `/`), or
                    # - the move has (temporarily) no date_to set
                    if (
                        move_has_name and move.posted_before
                        or not move_has_name and move._get_last_sequence(lock=False)
                        or not move.date_to
                    ):
                        continue
                except ValidationError:
                    # The move was never posted and the current number doesn't match the date_to. We should calculate the
                    # number later on, unless ...
                    if move._get_last_sequence(lock=False):
                        # ... we are in a period already containing moves: reset the number to `/` (draft)
                        move.number = '/'
                        continue
            group = grouped[journal_key(move)][date_key(move)]
            if not group['records']:
                # Compute all the values needed to sequence this whole group
                move._set_next_sequence()
                group['format'], group['format_values'] = move._get_sequence_format_param(move.number)
                group['reset'] = move._deduce_sequence_number_reset(move.number)
            group['records'] += move

        # Fusion the groups depending on the sequence reset and the format used because `seq` is
        # the same counter for multiple groups that might be spread in multiple months.
        final_batches = []
        for journal_group in grouped.values():
            journal_group_changed = True
            for date_group in journal_group.values():
                if (
                    journal_group_changed
                    or final_batches[-1]['format'] != date_group['format']
                    or dict(final_batches[-1]['format_values'], seq=0) != dict(date_group['format_values'], seq=0)
                ):
                    final_batches += [date_group]
                    journal_group_changed = False
                elif date_group['reset'] == 'never':
                    final_batches[-1]['records'] += date_group['records']
                elif (
                    date_group['reset'] == 'year'
                    and final_batches[-1]['records'][0].date_to.year == date_group['records'][0].date_to.year
                ):
                    final_batches[-1]['records'] += date_group['records']
                else:
                    final_batches += [date_group]

        # Give the number based on previously computed values
        for batch in final_batches:
            for move in batch['records']:
                move.number = batch['format'].format(**batch['format_values'])
                batch['format_values']['seq'] += 1
            batch['records']._compute_split_sequence()

        self.filtered(lambda m: not m.number).number = '/'
    
    @api.depends('journal_id', 'date_to','state')
    def _compute_highest_name(self):
        for record in self:
            record.highest_name = record._get_last_sequence(lock=False)

    @api.onchange('number', 'highest_name')
    def _onchange_name_warning(self):
        if self.number and self.number != '/' and self.number <= (self.highest_name or ''):
            self.show_name_warning = True
        else:
            self.show_name_warning = False

        origin_name = self._origin.number
        if not origin_name or origin_name == '/':
            origin_name = self.highest_name
        if self.number and self.number != '/' and origin_name and origin_name != '/':
            new_format, new_format_values = self._get_sequence_format_param(self.number)
            origin_format, origin_format_values = self._get_sequence_format_param(origin_name)

            if (
                new_format != origin_format
                or dict(new_format_values, seq=0) != dict(origin_format_values, seq=0)
            ):
                changed = _(
                    "Antes era '%(previous)s' y ahora es '%(current)s'.",
                    previous=origin_name,
                    current=self.number,
                )
                reset = self._deduce_sequence_number_reset(self.number)
                if reset == 'month':
                    detected = _(
                            "La secuencia se reiniciará en 1 al comienzo de cada año.\n"
                            "El año detectado aquí es '%(year)s'.\n"
                            "El número incremental en este caso es '%(formatted_seq)s'."
                    )
                elif reset == 'year':
                    detected = _(
                        "La secuencia se reiniciará en 1 al comienzo de cada año.\n"
                        "El año detectado aquí es'%(year)s'.\n"
                        "El número creciente en este caso es '%(formatted_seq)s'."
                    )
                else:
                    detected = _(
                        "La secuencia nunca se reiniciará.\n"
                         "El número incremental en este caso es '%(formatted_seq)s'."
                    )
                new_format_values['formatted_seq'] = "{seq:0{seq_length}d}".format(**new_format_values)
                detected = detected % new_format_values
                return {'warning': {
                    'title': _("El formato de la secuencia ha cambiado"),
                     'message': "%s\n\n%s" % (changed, detected)
                }}

    # @api.onchange('journal_id')
    # def _onchange_journal(self):
    #     for rec in self:
    #         if rec.journal_id and rec.journal_id.currency_id:
    #             new_currency = rec.journal_id.currency_id
    #             if new_currency != rec.currency_id:
    #                 rec.currency_id = new_currency
    #         if rec.state == 'draft' and rec._get_last_sequence(lock=False) and rec.number and rec.number != '/':
    #             rec.number = '/'

    def _get_last_sequence_domain(self, relaxed=False):
        self.ensure_one()
        if not self.date_to or not self.journal_id:
            return "WHERE FALSE", {}
        where_string = "WHERE journal_id = %(journal_id)s AND number != '/'"
        param = {'journal_id': self.journal_id.id}

        if not relaxed:
            domain = [('journal_id', '=', self.journal_id.id), ('id', '!=', self.id or self._origin.id), ('number', 'not in', ('/', '', False))]
            if self.journal_id.refund_sequence:
                if self.credit_note:
                    domain += [('credit_note','=',True)]
                else:
                    domain += [('credit_note','=',False)]
            reference_move_name = self.search(domain + [('date_to', '<=', self.date_to)], order='date_to desc', limit=1).number
            if not reference_move_name:
                reference_move_name = self.search(domain, order='date_to asc', limit=1).number
            sequence_number_reset = self._deduce_sequence_number_reset(reference_move_name)
            if sequence_number_reset == 'year':
                where_string += " AND date_trunc('year', date_to::timestamp without time zone) = date_trunc('year', %(date)s) "
                param['date'] = self.date_to
                param['anti_regex'] = re.sub(r"\?P<\w+>", "?:", self._sequence_monthly_regex.split('(?P<seq>')[0]) + '$'
            elif sequence_number_reset == 'month':
                where_string += " AND date_trunc('month', date_to::timestamp without time zone) = date_trunc('month', %(date)s) "
                param['date'] = self.date_to
            else:
                param['anti_regex'] = re.sub(r"\?P<\w+>", "?:", self._sequence_yearly_regex.split('(?P<seq>')[0]) + '$'

            if param.get('anti_regex') and not self.journal_id.sequence_override_regex:
                where_string += " AND sequence_prefix !~ %(anti_regex)s "

        if self.journal_id.refund_sequence:
            if self.credit_note:
                where_string += " AND credit_note = True"
            else:
                where_string += " AND credit_note = False"
        return where_string, param


    def _get_starting_sequence(self):
        starting_sequence = ''
        self.ensure_one()
        if self.journal_id:
            starting_sequence = "%s0000" % (self.journal_id.code)
        if self.credit_note:
            starting_sequence = "NCNOE" + "0000"
        return starting_sequence