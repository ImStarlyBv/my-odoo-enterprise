from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.osv.expression import AND
from datetime import timedelta


class PosOrder(models.Model):
    _inherit = 'pos.order'

    ncf = fields.Char(
        string='NCF',
        copy=False,
    )
    ncf_origin_out = fields.Char(
        string='Affects',
        copy=False,
    )
    ncf_expiration_date = fields.Date(
        string='NCF expiration date',
    )
    fiscal_type_id = fields.Many2one(
        string='Fiscal type',
        comodel_name='account.fiscal.type',
    )
    fiscal_sequence_id = fields.Many2one(
        string='Fiscal Sequence',
        comodel_name='account.fiscal.sequence',
        copy=False,
    )
    is_used_in_order = fields.Boolean(
        default=False
    )

    def _prepare_invoice_vals(self):
        invoice_vals = super(PosOrder, self)._prepare_invoice_vals()

        if self.config_id.invoice_journal_id.l10n_do_fiscal_journal:
            invoice_vals['ref'] = self.ncf
            invoice_vals['origin_out'] = self.ncf_origin_out
            invoice_vals['ncf_expiration_date'] = self.ncf_expiration_date
            invoice_vals['fiscal_type_id'] = self.fiscal_type_id.id
            invoice_vals['fiscal_sequence_id'] = self.fiscal_sequence_id.id

        return invoice_vals

    def _process_saved_order(self, draft):
        """Auto-invoice fiscal orders after they are saved."""
        if not draft and \
                self.state != 'invoiced' and \
                self.amount_total != 0 and \
                self.ncf and \
                self.config_id.invoice_journal_id.l10n_do_fiscal_journal:

            if not self.partner_id:
                if not self.config_id.pos_partner_id:
                    raise UserError(_(
                        'This point of sale has no default customer. '
                        'Please set a default customer in the POS configuration.'
                    ))
                self.write({'partner_id': self.config_id.pos_partner_id.id})

            self.write({'to_invoice': True})

        return super(PosOrder, self)._process_saved_order(draft)

    def get_next_fiscal_sequence(
            self,
            fiscal_type_id,
            company_id,
            payments,
            order_json
        ):
        """
        Search active fiscal sequence dependent on fiscal type.
        :return: {ncf, expiration date, fiscal sequence}
        """
        fiscal_type = self.env['account.fiscal.type'].browse(fiscal_type_id)

        fiscal_sequence = self.env['account.fiscal.sequence'].search([
            ('fiscal_type_id', '=', fiscal_type_id),
            ('state', '=', 'active'),
            ('company_id', '=', company_id)
        ], limit=1)

        if not fiscal_sequence:
            raise UserError(
                _(u"There is no current active NCF of {}, please create a new fiscal sequence of type {}.").format(
                    fiscal_type.name,
                    fiscal_type.name,
            ))

        new_ncf = fiscal_sequence.get_fiscal_number()

        ncf_log = self.env['pos.order.ncf.log'].sudo().create({
            'l10n_do_ncf': new_ncf,
            'order_json': order_json,
            'company_id': company_id
        })

        return {
            'ncf': new_ncf,
            'fiscal_sequence_id': fiscal_sequence.id,
            'ncf_expiration_date': fiscal_sequence.expiration_date,
            'ncf_log_id': ncf_log.id
        }

    def get_credit_note(self, ncf):
        credit_note = self.env['account.move'].search([
            ('ref', '=', ncf),
            ('move_type', '=', 'out_refund'),
            ('is_l10n_do_fiscal_invoice', '=', True),
            ('company_id', '=', self.env.company.id),
            ('state', '=', 'posted')
        ], limit=1)

        if not credit_note:
            raise UserError(_('Credit note not found'))

        return {
            'partner_id': credit_note.partner_id.id,
            'residual_amount': credit_note.amount_residual,
            'ncf': credit_note.ref,
        }

    def get_credit_notes(self, partner_id):
        credit_notes = self.env['account.move'].search([
            ('partner_id', '=', partner_id),
            ('move_type', '=', 'out_refund'),
            ('is_l10n_do_fiscal_invoice', '=', True),
            ('amount_residual', '>', 0.0),
            ('company_id', '=', self.env.company.id),
            ('state', '=', 'posted')
        ])

        if not credit_notes:
            raise UserError(_('This customer does not have credit notes'))

        return [{
            'id': credit_note.id,
            'label': "%s - %s %s" % (credit_note.ref, credit_note.currency_id.name, credit_note.amount_residual),
            'item': {
                'partner_id': credit_note.partner_id.id,
                'residual_amount': credit_note.amount_residual,
                'ncf': credit_note.ref,
            }} for credit_note in credit_notes]

    @api.model
    def search_paid_order_ids(self, config_id, domain, limit, offset):
        pos_config = self.env['pos.config'].browse(config_id)

        if pos_config.invoice_journal_id.l10n_do_fiscal_journal:
            config_ids = self.env['pos.config'].search([('invoice_journal_id.l10n_do_fiscal_journal', '=', True)]).ids

            default_domain = [
                '&', '&', '&',
                ('config_id', 'in', config_ids),
                ('ncf', '!=', False),
                ('amount_total', '>', 0),
                '!', '|',
                ('state', '=', 'draft'),
                ('state', '=', 'cancelled')
            ]

            if pos_config.l10n_do_type_limit_order_history == 'days':
                default_domain.insert(3, '&')
                default_domain.insert(4,
                    ('create_date', '>=', fields.Datetime.now() - timedelta(days=pos_config.l10n_do_type_limit_order_history_days)))

            real_domain = AND([domain, default_domain])
            ids = self.search(AND([domain, default_domain]), limit=limit, offset=offset).ids
            totalCount = self.search_count(real_domain)

            return {'ids': ids, 'totalCount': totalCount}

        return super(PosOrder, self).search_paid_order_ids(config_id, domain, limit, offset)


class PosOrderNcfLog(models.Model):
    _name = 'pos.order.ncf.log'
    _description = 'Each time an NCF is generated, it is necessary to log the order in JSON so that the client can continue in case of an error.'
    _rec_name = 'l10n_do_ncf'

    l10n_do_ncf = fields.Char(
        string='NCF',
        required=True
    )
    order_json = fields.Text(
        string='Order in JSON',
        required=True
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
