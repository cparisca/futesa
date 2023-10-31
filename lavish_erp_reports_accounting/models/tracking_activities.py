from odoo import tools
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class lavish_tracking_activities(models.Model):
    _name = 'lavish.tracking.activities'
    _description = 'Seguimiento de actividades'
    _auto = False

    activity = fields.Html(string='Contenido Actividad')
    activity_type_id = fields.Many2one('mail.activity.type',string='Tipo de actividad')
    create_uid = fields.Many2one('res.users',string='Creado por')
    create_date = fields.Datetime(string='Fecha creación', help='Esta fecha se pierde una vez sea realizada la actividad')
    user_id = fields.Many2one('res.users',string='Asignado a')
    date_deadline = fields.Datetime(string='Fecha vencimiento', help='Esta fecha se pierde una vez sea realizada la actividad')
    date_done = fields.Datetime(string='Fecha de realizado')
    state = fields.Char(string='Estado')

    @api.model
    def _query(self):
        return f'''
        Select Row_Number() Over(Order By state,create_date,user_id) as id, * 
        From (
            Select a.summary || ' <br> ' || a.note as activity, a.activity_type_id as activity_type_id,
                a.create_uid as create_uid, a.create_date as create_date,a.user_id as user_id, 
                a.date_deadline as date_deadline, '1900-01-01' as date_done,'POR HACER' as state
            From mail_activity as a
            Union
            Select 
                a.body as activity, a.mail_activity_type_id,b.id as create_uid, '1900-01-01' as create_date,a.create_uid, '1900-01-01' as date_deadline, a.create_date as date_done,
                'REALIZADO' as state
            From mail_message as a 
            Inner join res_users as b on a.author_id = b.partner_id
            Where mail_activity_type_id is not null
        ) as A
        '''

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute('''
            CREATE OR REPLACE VIEW %s AS (
                %s
            )
        ''' % (
            self._table, self._query()
        ))