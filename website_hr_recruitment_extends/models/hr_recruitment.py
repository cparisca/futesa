# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.tools.translate import html_translate


class Job(models.Model):
    _inherit = 'hr.job'

    def _get_default_job_website_description(self):
        default_description = self.env.ref("website_hr_recruitment_extends.default_website_job_description", raise_if_not_found=False)
        return (default_description._render({
                'job_id': self,
            }) if default_description else "")

    website_job_description = fields.Html(
        string='Website description', 
        translate=html_translate, 
        sanitize_attributes=False, 
        default=_get_default_job_website_description, 
        prefetch=False, 
        sanitize_form=False
    )

    @api.model_create_multi
    def create(self, vals_list):
        res = super(Job, self).create(vals_list)
        for rec in res:
            default_description = self.env.ref("website_hr_recruitment_extends.default_website_job_description", raise_if_not_found=False)
            rec.website_job_description = default_description._render({
                'job_id': rec,
            }) if default_description else ""
        return res
    
    def write(self, vals):
        res = super(Job, self).write(vals)
        if vals.get('description'):
            for rec in self:
                default_description = self.env.ref("website_hr_recruitment_extends.default_website_job_description", raise_if_not_found=False)
                rec.website_job_description = default_description._render({
                    'job_id': rec,
                }) if default_description else ""
        return res
