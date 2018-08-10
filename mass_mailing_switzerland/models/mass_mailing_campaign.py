# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2016-2017 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from odoo import api, models, fields

from odoo.addons.queue_job.job import job, related_action

from lxml import etree


class MassMailingCampaign(models.Model):
    _inherit = 'mail.mass_mailing.campaign'
    _order = 'id desc'

    clicks_ratio = fields.Integer(compute='_compute_ratios', store=True,
                                  oldname='click_ratio')
    unsub_ratio = fields.Integer(compute='_compute_ratios', store=True)
    contract_ids = fields.One2many(
        'recurring.contract', related='campaign_id.contract_ids'
    )
    correspondence_ids = fields.One2many(
        'correspondence', related='campaign_id.correspondence_ids'
    )
    invoice_line_ids = fields.One2many(
        'account.invoice.line', related='campaign_id.invoice_line_ids'
    )

    @api.depends('mass_mailing_ids.clicks_ratio',
                 'mass_mailing_ids.unsub_ratio')
    def _compute_ratios(self):
        for campaign in self:
            total_clicks = 0
            total_unsub = 0
            total_sent = len(campaign.mapped(
                'mass_mailing_ids.statistics_ids'))
            for mailing in campaign.mass_mailing_ids:
                total_clicks += (mailing.clicks_ratio / 100.0) * len(
                    mailing.statistics_ids)
                total_unsub += (mailing.unsub_ratio / 100.0) * len(
                    mailing.statistics_ids)
            if total_sent:
                campaign.clicks_ratio = (total_clicks / total_sent) * 100
                campaign.unsub_ratio = (total_unsub / total_sent) * 100

    @api.multi
    def open_unsub(self):
        return self.mass_mailing_ids.open_unsub()

    @api.multi
    def open_clicks(self):
        return self.mass_mailing_ids.open_clicks()

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False,
                        submenu=False):
        res = super(MassMailingCampaign, self).fields_view_get(view_id=view_id,
                        view_type=view_type, toolbar=toolbar, submenu=submenu)
        doc = etree.XML(res['arch'])
        if view_type == 'tree':
            for node in doc.xpath("//field[@name='invoice_ids']"):
                node.set('invisible', '1')
        return res

class Mail(models.Model):
    _inherit = 'mail.mail'

    @job(default_channel='root.mass_mailing')
    @related_action(action='related_action_emails')
    @api.multi
    def send_sendgrid_job(self, mass_mailing_ids=False):
        # Make send method callable in a job
        self.send_sendgrid()
        if mass_mailing_ids:
            mass_mailings = self.env['mail.mass_mailing'].browse(
                mass_mailing_ids)
            mass_mailings.write({'state': 'done'})
        return True
