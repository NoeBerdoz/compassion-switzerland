# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015 Compassion CH (http://www.compassion.ch)
#    Releasing children from poverty in Jesus' name
#    @author: Emanuel Cino <ecino@compassion.ch>
#
#    The licence is in the file __openerp__.py
#
##############################################################################

import logging

from dateutil.relativedelta import relativedelta

from openerp import api, models, fields, _
from openerp.exceptions import Warning

logger = logging.getLogger(__name__)


class RecurringContracts(models.Model):
    _inherit = 'recurring.contract.group'

    scan_line = fields.Char(compute='_compute_scan_line')
    format_ref = fields.Char(compute='_compute_format_ref')

    @api.multi
    def _compute_scan_line(self):
        """ Generate a scan line for contract group. """
        acc_number = self.get_company_bvr_account()
        for group in self.filtered('bvr_reference'):
            group.scan_line = self.get_scan_line(
                acc_number, group.bvr_reference)

    @api.multi
    def _compute_format_ref(self):
        slip_obj = self.env['l10n_ch.payment_slip']
        for group in self:
            group.format_ref = slip_obj._space(group.bvr_reference.lstrip('0'))

    @api.multi
    def get_months(self, months):
        """
        Given the list of months to print,
        returns the list of months grouped by the frequency payment
        of the contract group and only containing unpaid sponsorships.
        :param months: list of dates in string format
        :return: list of dates grouped in string format
        """
        self.ensure_one()
        freq = self.advance_billing_months
        payment_term = self.with_context(lang='en_US').payment_term_id
        # Take first open invoice or next_invoice_date
        open_invoice = min(
            [fields.Date.from_string(i)
             for i in self.contract_ids.mapped('first_open_invoice')
             if i] or [fields.Date.from_string(i)
                       for i in self.contract_ids.mapped('next_invoice_date')])
        if open_invoice:
            first_invoice_date = open_invoice.replace(day=1)
        else:
            raise Warning(_("No open invoice found !"))

        # Only keep unpaid months
        valid_months = [
            month for month in months
            if fields.Date.from_string(month) >= first_invoice_date
        ]
        if 'Permanent' in payment_term.name:
            return valid_months[:1]
        if freq == 1:
            return valid_months
        else:
            # Group months
            result = list()
            count = 1
            month_start = ""
            for month in valid_months:
                if not month_start:
                    month_start = month
                if count < freq:
                    count += 1
                else:
                    result.append(month_start + " - " + month)
                    month_start = ""
                    count = 1
            return result

    @api.multi
    def get_communication(self, start, stop, sponsorships):
        """
        Get the communication to print on the payment slip for sponsorship
        :param start: the month start for which we print the payment slip
        :param stop: the month stop for which we print the payment slip
        :param sponsorships: recordset of sponsorships for which to print the
                             payment slips
        :return: string of the communication
        """
        self.ensure_one()
        payment_term = self.with_context(lang='en_US').payment_term_id
        date_start = fields.Date.from_string(start)
        date_stop = fields.Date.from_string(stop)
        freq = self.advance_billing_months
        amount = 0
        number_sponsorship = 0
        month = date_start
        for i in range(0, freq):
            valid = sponsorships.filtered(
                lambda s: s.first_open_invoice and
                fields.Date.from_string(s.first_open_invoice) <= month
                or fields.Date.from_string(s.next_invoice_date) <= month
            )
            number_sponsorship = max(number_sponsorship, len(valid))
            amount += sum(valid.mapped('total_amount'))
            month += relativedelta(months=1)
        vals = {
            'amount': "CHF {:.0f}".format(amount),
            'subject': _("for") + " ",
        }
        if start == stop:
            vals['date'] = date_start.strftime("%B %Y")
        else:
            vals['date'] = date_start.strftime("%B %Y") + " - " + \
                           date_stop.strftime("%B %Y")
        if 'Permanent' in payment_term.name:
            vals['payment_type'] = _('ISR for standing order')
            vals['date'] = ''
        else:
            vals['payment_type'] = _('ISR') + ' ' + _(
                self.contract_ids[0].group_freq)
        if number_sponsorship > 1:
            vals['subject'] += str(number_sponsorship) + " " + _(
                "sponsorships")
        else:
            vals['subject'] = valid.child_id.firstname + " ({})".format(
                valid.child_id.local_id)

        return "{payment_type} {amount}<br/>{subject}<br/>{date}".format(
            **vals)

    @api.model
    def get_scan_line(self, account, reference):
        """ Generate a scan line given the reference """
        line = "042>"
        line += reference.replace(" ", "").rjust(27, '0')
        line += '+ '
        account_components = account.split('-')
        bank_identifier = "%s%s%s" % (
            account_components[0],
            account_components[1].rjust(6, '0'),
            account_components[2]
        )
        line += bank_identifier
        line += '>'
        return line

    @api.model
    def get_company_bvr_account(self):
        """ Utility to find the bvr account of the company. """
        company = self.env['res.company'].browse(1)
        bank = company.bank_ids.filtered(lambda b: b.state == 'bvr')[0]
        bank.ensure_one()
        return bank.acc_number
