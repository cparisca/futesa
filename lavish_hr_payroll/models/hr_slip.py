# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, SUPERUSER_ID , tools
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero, float_round, date_utils
from collections import defaultdict
from datetime import datetime, timedelta, date, time
from odoo.tools.misc import format_date
from dateutil.relativedelta import relativedelta

class Hr_payslip(models.Model):
    _inherit = 'hr.payslip'

    #obligaciones_ids = fields.One2many('hr.payslip.obligacion.tributaria.line', 'payslip_id', 'Obligaciones Tributarias', readonly=True, ondelete='cascade')
    extrahours_ids = fields.One2many('hr.overtime', 'payslip_run_id',  string='Horas Extra Detallada', )
    novedades_ids = fields.One2many('hr.novelties.different.concepts', 'payslip_id',  string='Novedades Detalladas')
    payslip_old_ids = fields.Many2many('hr.payslip', 'hr_payslip_rel', 'current_payslip_id', 'old_payslip_id', string='Nominas relacionadas')
    resulados_op = fields.Text('Resultados')
    resulados_rt = fields.Text('Resultados RT')
    def old_payslip_moth(self):
        # 1. Busca las nóminas de tipo vacaciones o prima.
        payslip_objs = self.env['hr.payslip'].search([('struct_id.process', 'in', ['vacaciones', 'prima'])])
        # 2. Asigna esos registros al campo many2many.
        for record in self:
            record.payslip_old_ids = [(6, 0, payslip_objs.ids)]

    def _assign_old_payslips(self):
        for payslip in self:
            # Considera el mes actual del payslip
            start_date = payslip.date_from.replace(day=1)
            end_date = (start_date + relativedelta(months=1, days=-1))
            
            # Busca las nóminas de tipo 'vacaciones' o 'prima', que pertenezcan al mismo mes, empleado y contrato
            domain = [
                ('id', '!=', payslip.id),  # Para excluir la nómina actual
                ('employee_id', '=', payslip.employee_id.id),
                ('contract_id', '=', payslip.contract_id.id),
                ('date_from', '>=', start_date.strftime('%Y-%m-%d')),
                ('date_to', '<=', end_date.strftime('%Y-%m-%d')),
                ('struct_id.process', 'in', ['vacaciones', 'prima']),
            ]
            old_payslips = self.env['hr.payslip'].search(domain)
            # Asigna esos registros al campo many2many
            payslip.payslip_old_ids = [(6, 0, old_payslips.ids)]

    def _compute_extra_hours(self):
        for payslip in self:
            if payslip.struct_id.process in ('nomina', 'contrato', 'otro'):
                query = """
                UPDATE hr_overtime
                SET payslip_run_id = %s
                WHERE 
                    (state = 'validated' OR payslip_run_id IS NULL)
                    AND date_end BETWEEN %s AND %s
                    AND employee_id = %s
                """
                self.env.cr.execute(query, (payslip.id, payslip.date_from, payslip.date_to, payslip.employee_id.id))

    def _compute_novedades(self):
        for payslip in self:
            query_params = [payslip.id, payslip.employee_id.id]
            date_conditions = ""
            if payslip.struct_id.process in ('nomina', 'contrato', 'otro', 'prima'):
                date_conditions = "AND date >= %s AND date <= %s"
                query_params.extend([payslip.date_from, payslip.date_to])

            query = """
            UPDATE hr_novelties_different_concepts
            SET payslip_id = %s
            WHERE payslip_id IS NULL 
            AND employee_id = %s 
            """ + date_conditions
            self.env.cr.execute(query, tuple(query_params))
