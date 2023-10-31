from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

#Configuración contabilización cierre de nómina (Seguridad social & Provisiones)
class hr_closing_configuration_detail(models.Model):
    _name ='hr.closing.configuration.detail'
    _description = 'Configuración contabilización cierre de nómina (Seguridad social & Provisiones)'

    process_id = fields.Many2one('hr.closing.configuration.header', string = 'Proceso')
    department = fields.Many2one('hr.department', string = 'Departamento')
    company = fields.Many2one('res.company', string = 'Compañía', required=True)
    work_location = fields.Many2one('res.partner', string = 'Ubicación de trabajo')
    third_debit = fields.Selection([('entidad', 'Entidad'),
                                    ('compañia', 'Compañia'),
                                    ('empleado', 'Empleado')], string='Tercero débito')
    third_credit = fields.Selection([('entidad', 'Entidad'),
                                    ('compañia', 'Compañia'),
                                    ('empleado', 'Empleado')], string='Tercero crédito')
    debit_account = fields.Many2one('account.account', string = 'Cuenta débito', company_dependent=True)
    credit_account = fields.Many2one('account.account', string = 'Cuenta crédito', company_dependent=True)

#Configuración parametrización contabilización cierre de nómina (Seguridad social & Provisiones)
class hr_closing_configuration_header(models.Model):
    _name = 'hr.closing.configuration.header'
    _description = 'Configuración parametrización contabilización cierre de nómina (Seguridad social & Provisiones)'

    process = fields.Selection([('vacaciones', 'Vacaciones'),
                                ('prima', 'Prima'),
                                ('cesantias', 'Cesantías'),
                                ('intcesantias', 'Intereses de cesantías'),
                                ('ss_empresa_salud', 'Seguridad social - Aporte empresa salud'),
                                ('ss_empresa_pension', 'Seguridad social - Aporte empresa pensión'),
                                ('ss_empresa_arp', 'Seguridad social - Aporte ARP'),
                                ('ss_empresa_caja', 'Seguridad social - Aporte caja de compensación'),
                                ('ss_empresa_sena', 'Seguridad social - Aporte SENA'),
                                ('ss_empresa_icbf', 'Seguridad social - Aporte ICBF'),
                                ], string='Proceso')
    description = fields.Text(string='Descripción')
    journal_id = fields.Many2one('account.journal',string='Diario', company_dependent=True)
    detail_ids = fields.One2many('hr.closing.configuration.detail','process_id',string='Contabilización')
    debit_account_difference = fields.Many2one('account.account', string='Cuenta débito diferencia', company_dependent=True)
    credit_account_difference = fields.Many2one('account.account', string='Cuenta crédito diferencia', company_dependent=True)

    _sql_constraints = [('closing_process_uniq', 'unique(process)',
                         'El proceso seleccionado ya esta registrado, por favor verificar.')]

    def name_get(self):
        result = []
        for record in self:
            process_str = dict(self._fields['process'].selection).get(record.process)
            result.append((record.id, "{}".format(process_str)))
        return result
