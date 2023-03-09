##############################################################################
#
#    Copyright (C) 2018-2020 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __manifest__.py
#
##############################################################################
from urllib.parse import urlencode

from odoo import models, api, fields
from odoo.http import request


class ResPartner(models.Model):
    _inherit = "res.partner"

    date_opt_out = fields.Date()
    primary_mailing_contact_ids = fields.One2many(
        "mail.mass_mailing.contact", "partner_id", "Primary Mass Mailing Contacts",
        oldname="mailing_contact_ids")
    mass_mailing_contact_ids = fields.Many2many(
        "mail.mass_mailing.contact", "mass_mailing_contact_partner_rel",
        "mass_mailing_contact_id", "partner_id", "Mass Mailing Contacts")
    church_name = fields.Char(related="church_id.name")

    # Add some computed fields to be used in mailchimp merge fields
    partner_image_url = fields.Char(compute="_compute_partner_image_url")
    wordpress_form_data = fields.Char(compute="_compute_wp_formdata")

    @api.multi
    def _compute_partner_image_url(self):
        try:
            base_url = request.website.domain
        except AttributeError:
            base_url = self.env["ir.config_parameter"].sudo().get_param(
                "web.external.url")
        for partner in self:
            if partner.image:
                partner.partner_image_url = \
                    f"{base_url}/web/image/res.partner/{partner.id}/image/profile.jpg"

    @api.multi
    def _compute_wp_formdata(self):
        country_filter_id = self.env["res.config.settings"].get_param(
            "mass_mailing_country_filter_id")
        for partner in self:
            locale_partner = partner.with_context(lang=partner.lang)
            child = self.env.context.get("mailchimp_child",
                                         partner.mapped("sponsored_child_ids"))
            if country_filter_id:
                child = child.filtered(
                    lambda c: c.field_office_id.id == country_filter_id)
            data = {
                "firstname": locale_partner.preferred_name,
                "pname": locale_partner.name,
                "email": locale_partner.email,
                "pstreet": locale_partner.street,
                "pcity": locale_partner.city,
                "pzip": locale_partner.zip,
                "pcountry": locale_partner.country_id.name,
                "sponsor_ref": locale_partner.ref,
                "child_ref": child.local_id if len(child) == 1 else False,
            }
            filter_data = {key: val for key, val in data.items() if val}
            partner.wordpress_form_data = urlencode(filter_data)

    @api.multi
    def _compute_mailchimp_subscription_list_ids(self):
        # Take subscriptions from all associated contacts
        for partner in self:
            partner.subscription_list_ids = partner.mapped("mass_mailing_contact_ids.subscription_list_ids")

    @api.model
    def create(self, vals):
        if "opt_out" in vals and "email" in vals:
            vals["date_opt_out"] = fields.Date.today() if vals["opt_out"] else False
            contact_rel_to_opt_out = self.env["mail.mass_mailing.list_contact_rel"].search(
                [("contact_id.email", "=", vals["email"])]
            )
            contact_rel_to_opt_out.with_context({"opt_out_from_partner": True}).write({
                "opt_out": vals["opt_out"]
            })
        return super().create(vals)

    @api.multi
    def write(self, vals):
        """
        - Update opt_out date
        - Opt_out from all mailing lists if general opt_out is checked.
        - Push tags into mailing contacts
        - Remove mailing contact if email address is removed
        """
        if "opt_out" in vals:
            vals["date_opt_out"] = fields.Date.today() if vals["opt_out"] else False
            contact_rel_to_opt_out = self.env["mail.mass_mailing.list_contact_rel"].search(
                [("contact_id.email", "in", self.mapped("email"))]
            )
            contact_rel_to_opt_out.with_context({"opt_out_from_partner": True}).write({
                "opt_out": vals["opt_out"]
            })
        for partner in self.filtered(lambda c: c.mass_mailing_contact_ids):
            mailing_contacts = partner.mass_mailing_contact_ids
            mailing_contact_vals = {}
            if "opt_out" in vals and vals["opt_out"] != partner.opt_out:
                mailing_contacts = mailing_contacts.with_context(
                    opt_out_from_partner=True)
                mailing_contact_vals["opt_out"] = vals["opt_out"]
            if "category_id" in vals:
                mailing_contact_vals["tag_ids"] = vals["category_id"]
            if "email" in vals and not vals["email"] and not self.env.context.get(
                    "import_from_mailchimp"):
                # In this case we don't need anymore the mailchimp contacts
                mailing_contacts.unlink()
            if mailing_contact_vals:
                mailing_contacts.write(mailing_contact_vals)
        return super().write(vals)

    def update_contact_email(self, email):
        """ Override from mailchimp to manage contact merge or unmerge. """
        for partner in self.filtered(lambda x: x.subscription_list_ids):
            mailing_contacts = partner.mass_mailing_contact_ids
            other_partners = mailing_contacts.mapped("partner_ids") - partner
            if other_partners:
                # Dissociate this partner from others inside the mass_mailing.contact
                mailchimp_lists = mailing_contacts.mapped("subscription_list_ids.mailchimp_list_id")
                mailing_contacts.write({"partner_ids": [(3, partner.id)]})
                mailing_contacts.with_delay(eta=6).action_update_to_mailchimp()
                partner.with_delay(eta=5).action_export_partner_mailchimp(mailchimp_lists)
            else:
                super(ResPartner, partner).update_contact_email(email)

    @api.multi
    def update_selected_child_for_mailchimp(self, child):
        # Allows to force selecting one child for displaying in email templates.
        self.ensure_one()
        for contact in self.with_context(
                mailchimp_child=child).mass_mailing_contact_ids:
            contact.action_update_to_mailchimp()

    def get_mailing_contact_to_update(self):
        # Only return directly linked contacts
        self.ensure_one()
        return self.mass_mailing_contact_ids

    @api.multi
    def forget_me(self):
        self.mass_mailing_contact_ids.unlink()
        super().forget_me()
        return True
