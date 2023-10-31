# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta


class account_bank_statment(models.Model):
    _inherit = "account.bank.statement"

    reconciling_id = fields.Many2one('lavish.reconciling.items.encab', 'Partida conciliatoria')


class lavish_reconciling_items_encab(models.Model):
    _name = 'lavish.reconciling.items.encab'
    _description = 'Encabezado partidas conciliatorias'

    name = fields.Char(string='Nombre', required=True)
    year = fields.Integer('Año', required=True)
    month = fields.Selection([('1', 'Enero'),('2', 'Febrero'),('3', 'Marzo'),('4', 'Abril'),('5', 'Mayo'),
                              ('6', 'Junio'),('7', 'Julio'),('8', 'Agosto'),('9', 'Septiembre'),('10', 'Octubre'),
                              ('11', 'Noviembre'),('12', 'Diciembre')], string='Mes', required=True)
    reconciling_detail = fields.One2many('lavish.reconciling.items.detail', 'reconciling_encab', string='Detalle partidas conciliatorias')
    state = fields.Selection([('draft','Borrador'),('processed','Procesado')], 'Estado', default='draft')
    counter_extract = fields.Integer(compute='compute_counter_extract', string='Extractos')
    search_all = fields.Boolean('Busqueda todos los meses anteriores')

    def compute_counter_extract(self):
        count = self.env['account.bank.statement'].search_count([('reconciling_id', '=', self.id)])
        self.counter_extract = count

    def return_action_to_open(self):
        res = {
            'name': 'Extractos bancarios',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.bank.statement',
            'target': 'current',
            'domain': "[('reconciling_id','in',[" + str(self._ids[0]) + "])]"
        }
        return res

    def search_reconciling_items(self):
        date_start = '01/' + str(self.month) + '/' + str(self.year)
        date_start = datetime.strptime(date_start, '%d/%m/%Y')

        date_end = date_start + relativedelta(months=1)
        date_end = date_end - timedelta(days=1)

        date_start = date_start.date()
        date_end = date_end.date()

        if self.search_all:
            statements = self.env['account.bank.statement'].search([('date', '<=', date_end), ('state', '!=', 'confirm')])
        else:
            statements = self.env['account.bank.statement'].search([('date', '>=', date_start), ('date', '<=', date_end), ('state', '!=', 'confirm')])

        if statements:
            query = f'''
                    select D.date, A.payment_ref, A.partner_id, A.amount, A.statement_id, A.move_id, C.journal_id, A.id 
                    from account_bank_statement_line A
                    inner join account_move B on A.move_id = B.id and B.state = 'posted' 
                    inner join account_move_line C on B.id = C.move_id  
                    inner join account_bank_statement D on A.statement_id = D.id and D.id in {tuple(statements.ids)}
                    inner join account_account E on C.account_id = E.id and lower(E."name") like '%transitoria%'
                    where not A.is_reconciled 
                    order by C.journal_id, D.date 
                '''

            self._cr.execute(query)
            list_items = self._cr.dictfetchall()

            reconciling_detail = []
            self.reconciling_detail.unlink()

            for row in list_items:
                reconciling_detail.append({'reconciling_encab': self.id,
                                           'date': row['date'],
                                           'payment_ref': row['payment_ref'],
                                           'partner_id': row['partner_id'],
                                           'amount': row['amount'],
                                           'statement_id': row['statement_id'],
                                           'move_id': row['move_id'],
                                           'journal_id': row['journal_id'],
                                           'bank_statement_line': row['id']})

            self.env['lavish.reconciling.items.detail'].create(reconciling_detail)
        else:
            raise ValidationError(_('No se encontraron extractos en el mes/año seleccionado. Por favor verifique!'))
        return True

    def process(self):
        list_moves = []
        list_statement = []
        moves_vals_list = []

        date_start = '01/' + str(self.month) + '/' + str(self.year)
        date_start = datetime.strptime(date_start, '%d/%m/%Y')

        date_end = date_start + relativedelta(months=1)

        date_start = date_start.date()
        date_end = date_end.date()
        date_end_p = (date_end - timedelta(days=1))

        if self.search_all:
            date_end_p = date.today()

        tmp_journal_id = 0
        tmp_currency_id = 0
        row = 0
        cant_row = len(self.reconciling_detail)
        create_last = True

        # Reversión de movimientos contables
        for item in self.reconciling_detail:
            row += 1
            if tmp_journal_id == 0:
                tmp_currency_id = item.move_id.currency_id.id
                tmp_journal_id = item.journal_id.id
                obj_statement = self.env['account.bank.statement'].create(
                    {
                        'name': 'PARTIDAS CONCILIATORIAS ' + str(date_start) + ' al ' + str(date_end) + ' ' + item.move_id.journal_id.name,
                        'journal_id': tmp_journal_id,
                        # 'date': date_end,
                        'date': date_start if self.search_all else date_end,
                        'company_id': self.env.company.id,
                        'reconciling_id': self.id
                    }
                )

            if tmp_journal_id == item.journal_id.id:
                list_moves.append((4, item.move_id.id))
                list_statement.append({
                    'date': date_start if self.search_all else date_end,
                    'name': "/",
                    'partner_id': item.move_id.partner_id.id,
                    'amount': item.move_id.amount_total,
                    'statement_id': obj_statement.id,
                    'payment_ref': item.move_id.line_ids[0].name,
                })

            if tmp_journal_id != item.journal_id.id or row == cant_row:
                obj_reversal = self.env['account.move.reversal'].create(
                                    {
                                        'move_ids': list_moves,
                                        'date_mode': 'custom',
                                        'date': date_end_p,
                                        # 'date': date.today(),
                                        'reason': 'lavish: Cierre partidas conciliatorias',
                                        'journal_id': tmp_journal_id,
                                        'company_id': self.env.company.id,
                                    }
                                )
                obj_result = obj_reversal.reverse_moves()
                self.env['account.bank.statement.line'].create(list_statement)

                list_moves = []
                list_statement = []

                list_moves.append((4, item.move_id.id))

                if tmp_journal_id != item.journal_id.id:
                    obj_statement = self.env['account.bank.statement'].create(
                        {
                            'name': 'PARTIDAS CONCILIATORIAS ' + str(date_start) + ' al ' + str(date_end) + ' ' + item.move_id.journal_id.name,
                            'journal_id': item.journal_id.id,
                            'date': date_start if self.search_all else date_end,
                            'company_id': self.env.company.id,
                            'reconciling_id': self.id
                        }
                    )
                else:
                    if row == cant_row:
                        create_last = False

                tmp_journal_id = item.journal_id.id

                list_statement.append({
                    'date': date_start if self.search_all else date_end,
                    'name': "/",
                    'partner_id': item.move_id.partner_id.id,
                    'amount': item.move_id.amount_total,
                    'statement_id': obj_statement.id,
                    'payment_ref': item.move_id.line_ids[0].name,
                })

                if row != cant_row:
                    obj_reversal = self.env['account.move.reversal'].create(
                        {
                            'move_ids': list_moves,
                            'date_mode': 'custom',
                            # 'date': date.today(),
                            'date': date_end_p,
                            'reason': 'lavish: Cierre partidas conciliatorias',
                            'journal_id': tmp_journal_id,
                            'company_id': self.env.company.id,
                        }
                    )
                    obj_result = obj_reversal.reverse_moves()
                else:
                    if create_last:
                        self.env['account.bank.statement.line'].create(list_statement)

        # Se marca la linea del extracto como conciliado
        self.reconciling_detail.bank_statement_line.write({'is_reconciled': True})

        obj_reverse_moves = self.env['account.move'].search([('state', '=', 'draft'), ('ref', 'like', 'Reversión de:%'), ('date', '=', date_end_p)])
        # obj_reverse_moves = self.env['account.move'].search([('state', '=', 'draft'), ('ref', 'like', 'Reversión de:%'), ('date', '=', date.today())])
        for row in obj_reverse_moves:
            row.action_post()

        self.state = 'processed'

        return True


class lavish_reconciling_items_detail(models.Model):
    _name = 'lavish.reconciling.items.detail'
    _description = 'Detalle partidas conciliatorias'
    _order = 'journal_id,date'

    reconciling_encab = fields.Many2one('lavish.reconciling.items.encab', 'Encabezado partidas conciliatorias')
    date = fields.Date('Fecha')
    payment_ref = fields.Char('Etiqueta')
    partner_id = fields.Many2one('res.partner', 'Asociado')
    amount = fields.Float('Importe')
    statement_id = fields.Many2one('account.bank.statement', 'Extracto')
    move_id = fields.Many2one('account.move', 'Movimiento Contable')
    journal_id = fields.Many2one('account.journal', string='Diario')
    bank_statement_line = fields.Many2one('account.bank.statement.line', string='Det. Extracto')


class SequenceMixin(models.AbstractModel):
    """Mechanism used to have an editable sequence number.

    Be careful of how you use this regarding the prefixes. More info in the
    docstring of _get_last_sequence.
    """

    _inherit = 'sequence.mixin'

    def _constrains_date_sequence(self):
        # Make it possible to bypass the constraint to allow edition of already messed up documents.
        # /!\ Do not use this to completely disable the constraint as it will make this mixin unreliable.
        constraint_date = fields.Date.to_date(self.env['ir.config_parameter'].sudo().get_param(
            'sequence.mixin.constraint_start_date',
            '1970-01-01'
        ))
        for record in self:
            date = fields.Date.to_date(record[record._sequence_date_field])
            sequence = record[record._sequence_field]
            if sequence and date and date > constraint_date:
                format_values = record._get_sequence_format_param(sequence)[1]
                if (
                    format_values['year'] and format_values['year'] != date.year % 10**len(str(format_values['year']))
                    or format_values['month'] and format_values['month'] != date.month
                ):
                    raise ValidationError(_(
                        "The %(date_field)s (%(date)s) doesn't match the sequence number of the related %(model)s (%(sequence)s)\n"
                        "You will need to clear the %(model)s's %(sequence_field)s to proceed.\n"
                        "In doing so, you might want to resequence your entries in order to maintain a continuous date-based sequence.",
                        date=format_date(self.env, date),
                        sequence=sequence,
                        date_field=record._fields[record._sequence_date_field]._description_string(self.env),
                        sequence_field=record._fields[record._sequence_field]._description_string(self.env),
                        model=self.env['ir.model']._get(record._name).display_name,
                    ))