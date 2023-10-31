from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

# Se hereda res.users debido a un error al seleccionar un usuario como gerente en el que en realidad no deberia
# haber error pero lo hay. El cambio esta hecho entre la línea 39 y 44
class res_user(models.Model):
    _inherit = "res.users"

    @api.constrains('groups_id')
    def _check_one_user_type(self):
        """We check that no users are both portal and users (same with public).
           This could typically happen because of implied groups.
        """
        user_types_category = self.env.ref('base.module_category_user_type', raise_if_not_found=False)
        user_types_groups = self.env['res.groups'].search(
            [('category_id', '=', user_types_category.id)]) if user_types_category else False
        if user_types_groups:  # needed at install
            if self._has_multiple_groups(user_types_groups.ids):
                raise ValidationError(_('The user cannot have more than one user types.'))

    def _has_multiple_groups(self, group_ids):
        """The method is not fast if the list of ids is very long;
           so we rather check all users than limit to the size of the group
        :param group_ids: list of group ids
        :return: boolean: is there at least a user in at least 2 of the provided groups
        """
        if group_ids:
            args = [tuple(group_ids)]
            if len(self.ids) == 1:
                where_clause = "AND r.uid = %s"
                args.append(self.id)
            else:
                where_clause = ""  # default; we check ALL users (actually pretty efficient)
            query = """
                    SELECT 1 FROM res_groups_users_rel WHERE EXISTS(
                        SELECT r.uid
                        FROM res_groups_users_rel r
                        WHERE r.gid IN %s""" + where_clause + """
                        GROUP BY r.uid HAVING COUNT(r.gid) > 1
                    )
            """
            result = self.env.cr.execute(query, args)
            if not result:
                return False
            else:
                return True
            #return bool(self.env.cr.fetchall())
        else:
            return False

class ResCompany(models.Model):
    _inherit = 'res.company'

    validated_certificate = fields.Many2one('documents.tag', string='Certificado validado')

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    validated_certificate = fields.Many2one(related='company_id.validated_certificate',string='Certificado validado', readonly=False)