from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import Form

from . import common


@tagged("-at_install", "post_install")
class FiscalNotesTest(common.L10nDOTestsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref(
            "l10n_do_accounting.group_l10n_do_debit_note"
        ) | cls.env.ref("l10n_do_accounting.group_l10n_do_fiscal_credit_note")
        # Fiscal journals in real databases often have no default account
        cls.fiscal_sale_journal.default_account_id = False

    def _posted_invoice(self, **data):
        data.setdefault("document_number", "B0100000001")
        invoice = self._create_l10n_do_invoice(data=data)
        invoice.action_post()
        return invoice

    def _refund(self, invoice, **values):
        wizard_form = Form(
            self.env["account.move.reversal"].with_context(
                active_model="account.move", active_ids=invoice.ids
            )
        )
        wizard_form.reason = "test"
        for name, value in values.items():
            setattr(wizard_form, name, value)
        action = wizard_form.save().refund_moves()
        return self.env["account.move"].browse(action["res_id"])

    def test_001_partial_refund_percentage(self):
        invoice = self._posted_invoice()
        refund = self._refund(
            invoice, l10n_do_refund_type="percentage", l10n_do_percentage=25
        )
        line = refund.invoice_line_ids
        self.assertEqual(len(line), 1)
        self.assertTrue(line.account_id)
        self.assertEqual(line.tax_ids, invoice.invoice_line_ids.tax_ids)
        self.assertAlmostEqual(refund.amount_untaxed, invoice.amount_untaxed * 0.25)
        self.assertAlmostEqual(refund.amount_total, invoice.amount_total * 0.25)

    def test_002_partial_refund_fixed_amount(self):
        invoice = self._posted_invoice()
        refund = self._refund(
            invoice, l10n_do_refund_type="fixed_amount", l10n_do_amount=40
        )
        self.assertTrue(refund.invoice_line_ids.account_id)
        self.assertAlmostEqual(refund.amount_untaxed, 40)

    def test_003_debit_note_percentage(self):
        invoice = self._posted_invoice()
        wizard_form = Form(
            self.env["account.debit.note"].with_context(
                active_model="account.move", active_ids=invoice.ids
            )
        )
        wizard_form.reason = "test"
        wizard_form.l10n_do_debit_type = "percentage"
        wizard_form.l10n_do_percentage = 10
        action = wizard_form.save().create_debit()
        debit_note = self.env["account.move"].browse(action["res_id"])
        self.assertTrue(debit_note.invoice_line_ids.account_id)
        self.assertAlmostEqual(debit_note.amount_untaxed, invoice.amount_untaxed * 0.1)

    def test_004_taxpayer_without_vat_cannot_post(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Taxpayer without VAT",
                "l10n_do_dgii_tax_payer_type": "taxpayer",
                "country_id": self.env.ref("base.do").id,
            }
        )
        invoice = self._create_l10n_do_invoice(
            data={"partner": partner, "document_number": "B0100000001"}
        )
        with self.assertRaises(ValidationError):
            invoice.action_post()

    def test_005_consumer_over_250k_without_vat_cannot_post(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Consumer without VAT",
                "l10n_do_dgii_tax_payer_type": "non_payer",
                "country_id": self.env.ref("base.do").id,
            }
        )
        data = {
            "partner": partner,
            "document_type": self.do_document_type["consumer"],
            "document_number": "B0200000001",
        }
        small = self._create_l10n_do_invoice(data=data)
        small.action_post()
        self.assertEqual(small.state, "posted")

        big = self._create_l10n_do_invoice(
            data=dict(
                data, document_number=False, lines=[{"price_unit": 260000}]
            )
        )
        with self.assertRaises(ValidationError):
            big.action_post()
