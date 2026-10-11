from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.l10n_do_accounting.tests.common import L10nDOTestsCommon


@tagged('post_install', '-at_install')
class TestFiscalPos(L10nDOTestsCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref('point_of_sale.group_pos_manager')
        cls.env.user.groups_id |= cls.env.ref(
            'l10n_do_accounting.group_l10n_do_fiscal_invoice_cancel')
        cls.cash_pm = cls.env['pos.payment.method'].create({
            'name': 'Cash',
            'journal_id': cls.company_data['default_journal_cash'].id,
        })
        cls.bank_pm = cls.env['pos.payment.method'].create({
            'name': 'Card',
            'journal_id': cls.company_data['default_journal_bank'].id,
        })
        cls.config = cls.env['pos.config'].create({
            'name': 'Fiscal POS',
            'invoice_journal_id': cls.fiscal_sale_journal.id,
            'payment_method_ids': [(6, 0, (cls.cash_pm | cls.bank_pm).ids)],
            'l10n_do_default_consumer_partner_id': cls.consumo_partner.id,
        })
        cls.pos_product = cls.env['product.product'].create({
            'name': 'POS product',
            'type': 'service',
            'lst_price': 100,
            'available_in_pos': True,
            'taxes_id': [(6, 0, cls.do_company.account_sale_tax_id.ids)],
        })

    def _open_session(self):
        self.config.open_ui()
        session = self.config.current_session_id
        session.set_opening_control(0, False)
        return session

    def _sell(self, session, payment_method, uuid):
        taxes = self.pos_product.taxes_id
        totals = taxes.compute_all(self.pos_product.lst_price, self.config.currency_id, 1)
        result = self.env['pos.order'].sync_from_ui([{
            'amount_paid': totals['total_included'],
            'amount_return': 0,
            'amount_tax': totals['total_included'] - totals['total_excluded'],
            'amount_total': totals['total_included'],
            'date_order': fields.Datetime.to_string(fields.Datetime.now()),
            'fiscal_position_id': False,
            'pricelist_id': self.config.pricelist_id.id,
            'name': 'Order %s' % uuid,
            'last_order_preparation_change': '{}',
            'lines': [(0, 0, {
                'pack_lot_ids': [],
                'price_unit': self.pos_product.lst_price,
                'product_id': self.pos_product.id,
                'price_subtotal': totals['total_excluded'],
                'price_subtotal_incl': totals['total_included'],
                'qty': 1,
                'tax_ids': [(6, 0, taxes.ids)],
            })],
            'partner_id': self.consumo_partner.id,
            'session_id': session.id,
            'sequence_number': 2,
            'payment_ids': [(0, 0, {
                'amount': totals['total_included'],
                'name': fields.Datetime.now(),
                'payment_method_id': payment_method.id,
            })],
            'uuid': uuid,
            'user_id': self.env.uid,
            'to_invoice': False,
            'l10n_latam_document_type_id': self.do_document_type['consumer'].id,
        }])
        return self.env['pos.order'].browse(result['pos.order'][0]['id'])

    def test_01_close_fiscal_session_with_orders(self):
        self.assertTrue(self.config.l10n_do_is_fiscal)
        session = self._open_session()
        cash_order = self._sell(session, self.cash_pm, '00001-001-0001')
        self._sell(session, self.bank_pm, '00001-001-0002')
        self.assertEqual(cash_order.state, 'invoiced')
        self.assertEqual(cash_order.account_move.state, 'posted')

        session.post_closing_cash_details(cash_order.amount_total)
        result = session.close_session_from_ui()
        self.assertTrue(result.get('successful'), result)
        self.assertEqual(session.state, 'closed')

    def test_02_reset_and_cancel_customer_invoice(self):
        invoice = self._create_l10n_do_invoice(data={'document_number': 'B0100000001'})
        invoice.action_post()
        invoice.button_draft()
        self.assertEqual(invoice.state, 'draft')
        invoice.action_post()
        invoice.with_context(skip_cancel_wizard=True).button_cancel()
        self.assertEqual(invoice.state, 'cancel')

    def test_03_invoice_of_open_session_is_protected(self):
        session = self._open_session()
        order = self._sell(session, self.cash_pm, '00001-001-0003')
        with self.assertRaises(UserError):
            order.account_move.button_draft()
