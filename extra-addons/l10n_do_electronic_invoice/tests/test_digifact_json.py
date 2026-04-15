import json
from datetime import date, timedelta

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


@tagged('post_install', '-at_install')
class TestDigifactJsonGeneration(TransactionCase):

    def setUp(self):
        super().setUp()

        # Companies
        self.company = self.env['res.company'].create({
            'name': 'Test Company SRL',
            'vat': '130862015',
            'street': 'Av. Winston Churchill #1000',
            'city': 'Santo Domingo',
            'country_id': self.env.ref('base.do').id,
            'l10n_do_trade_name': 'Test Trade Name',
            'l10n_do_economic_activity': 'Comercio al por mayor',
            'l10n_do_branch_code': '0001',
            'is_live': False,
        })

        # Municipality (create a test one if not exists)
        self.municipality = self.env['l10n_do.municipality'].search([], limit=1)
        if not self.municipality:
            self.municipality = self.env['l10n_do.municipality'].create({
                'name': 'Santo Domingo de Guzman',
                'code': '010100',
            })
        self.company.l10n_do_municipality_id = self.municipality.id

        # Users
        self.user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Test User',
            'login': 'test_user_digifact',
            'email': 'test@example.com',
            'company_id': self.company.id,
            'company_ids': [(4, self.company.id)],
        })

        # Partners
        self.partner_fiscal = self.env['res.partner'].create({
            'name': 'Test Partner Fiscal',
            'vat': '131735015',
            'l10n_do_dgii_tax_payer_type': 'taxpayer',
            'street': 'Av. 27 de Febrero #500',
            'city': 'Santo Domingo',
            'country_id': self.env.ref('base.do').id,
        })

        self.partner_consumer = self.env['res.partner'].create({
            'name': 'Test Consumer',
            'l10n_do_dgii_tax_payer_type': 'non_payer',
        })

        # Products
        self.product_good = self.env['product.product'].create({
            'name': 'Test Product Good',
            'type': 'consu',
            'list_price': 100.0,
            'default_code': 'TEST001',
            'l10n_do_product_type': '1',
            'l10n_do_billing_indicator': '1',
        })

        self.product_service = self.env['product.product'].create({
            'name': 'Test Product Service',
            'type': 'service',
            'list_price': 50.0,
            'default_code': 'TEST002',
            'l10n_do_product_type': '2',
            'l10n_do_billing_indicator': '4',
        })

        # Journals
        self.sale_journal = self.env['account.journal'].create({
            'name': 'Test Sale Journal',
            'type': 'sale',
            'code': 'TSJ',
            'company_id': self.company.id,
        })

        # Document types (use existing or create test ones)
        self.doc_type_e31 = self.env['l10n_latam.document.type'].search([
            ('country_id.code', '=', 'DO'),
            ('doc_code_prefix', '=', 'E31'),
        ], limit=1)

        if not self.doc_type_e31:
            self.doc_type_e31 = self.env['l10n_latam.document.type'].create({
                'name': 'Electronic Invoice (Credit)',
                'code': 'e31',
                'doc_code_prefix': 'E31',
                'country_id': self.env.ref('base.do').id,
            })

        self.doc_type_e32 = self.env['l10n_latam.document.type'].search([
            ('country_id.code', '=', 'DO'),
            ('doc_code_prefix', '=', 'E32'),
        ], limit=1)

        self.doc_type_e34 = self.env['l10n_latam.document.type'].search([
            ('country_id.code', '=', 'DO'),
            ('doc_code_prefix', '=', 'E34'),
        ], limit=1)

        # Sequences
        self.sequence_e31 = self.env['ir.sequence'].create({
            'name': 'Test E31 Sequence',
            'code': 'l10n_do_accounting.invoice.%s' % self.doc_type_e31.id,
            'prefix': 'E31',
            'suffix': '',
            'padding': 8,
            'number_next': 1,
            'number_increment': 1,
            'company_id': self.company.id,
        })

    def _create_invoice(self, partner, doc_type, product, quantity=1, price_unit=None, post=True):
        """Helper to create a test invoice."""
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'company_id': self.company.id,
            'journal_id': self.sale_journal.id,
            'l10n_latam_document_type_id': doc_type.id,
            'invoice_date': date.today(),
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'name': product.name,
                'quantity': quantity,
                'price_unit': price_unit or product.list_price,
            })],
        }

        invoice = self.env['account.move'].create(invoice_vals)

        if post:
            invoice.action_post()

        return invoice

    # =========================================================================
    # TEST 1: Basic E31 Invoice (B2B)
    # =========================================================================

    def test_01_e31_invoice_basic(self):
        """Test E31 invoice (B2B) generates valid JSON payload."""
        invoice = self._create_invoice(
            self.partner_fiscal,
            self.doc_type_e31,
            self.product_good,
            quantity=2,
            price_unit=100.0,
        )

        payload = invoice._build_digifact_payload()

        # Verify top-level keys
        self.assertIn('Version', payload)
        self.assertEqual(payload['Version'], '1.0')
        self.assertEqual(payload['CountryCode'], 'DO')
        self.assertEqual(payload['TaxId'], self.company.vat)
        self.assertEqual(payload['live'], '0')  # is_live=False

        # Verify Header
        header = payload['Header']
        self.assertEqual(header['DocType'], '31')
        self.assertIn('IssuedDateTime', header)
        self.assertIn('AdditionalIssueDocInfo', header)

        # Verify Seller
        seller = payload['Seller']
        self.assertEqual(seller['TaxID'], self.company.vat)
        self.assertEqual(seller['Name'], self.company.name)
        self.assertIn('BranchInfo', seller)
        self.assertEqual(seller['BranchInfo']['Name'], '0001')

        # Verify Buyer
        buyer = payload['Buyer']
        self.assertEqual(buyer['TaxID'], self.partner_fiscal.vat)
        self.assertEqual(buyer['Name'], self.partner_fiscal.name)
        self.assertIn('AddressInfo', buyer)

        # Verify Items
        items = payload['Items']
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item['Description'], self.product_good.name)
        self.assertEqual(item['Qty'], '2.00')
        self.assertEqual(item['Price'], '100.00')
        self.assertEqual(item['Type'], '1')  # Good

        # Verify Totals
        totals = payload['Totals']
        self.assertEqual(totals['QtyItems'], 1)
        self.assertIn('GrandTotal', totals)
        self.assertIn('InvoiceTotal', totals['GrandTotal'])

        # Verify Payments
        payments = payload['Payments']
        self.assertEqual(len(payments), 1)
        self.assertIn('Code', payments[0])
        self.assertIn('Amount', payments[0])

        print('\n✓ E31 Invoice Basic Test PASSED')
        print('Payload sample:')
        print(json.dumps(payload, indent=2, ensure_ascii=False)[:500] + '...')

    # =========================================================================
    # TEST 2: E32 Final Consumer Invoice
    # =========================================================================

    def test_02_e32_consumer_final(self):
        """Test E32 invoice with final consumer (NO_APLICA)."""
        if not self.doc_type_e32:
            self.skipTest('E32 document type not available')

        invoice = self._create_invoice(
            self.partner_consumer,
            self.doc_type_e32,
            self.product_good,
        )

        payload = invoice._build_digifact_payload()

        # Buyer should be NO_APLICA
        buyer = payload['Buyer']
        self.assertEqual(buyer['TaxID'], 'NO_APLICA')

        # DocType should be 32
        self.assertEqual(payload['Header']['DocType'], '32')

        print('\n✓ E32 Final Consumer Test PASSED')

    # =========================================================================
    # TEST 3: E34 Credit Note with Reference
    # =========================================================================

    def test_03_e34_credit_note(self):
        """Test E34 credit note generates with reference info."""
        if not self.doc_type_e34:
            self.skipTest('E34 document type not available')

        # Create original invoice first
        original_invoice = self._create_invoice(
            self.partner_fiscal,
            self.doc_type_e31,
            self.product_good,
        )

        # Create credit note referencing original
        credit_note = self._create_invoice(
            self.partner_fiscal,
            self.doc_type_e34,
            self.product_good,
            price_unit=-100.0,
        )

        # Set modification reason (required for E33/E34)
        credit_note.l10n_do_ecf_modification_code = '1'

        payload = credit_note._build_digifact_payload()

        # Verify Header
        self.assertEqual(payload['Header']['DocType'], '34')

        # Verify AdditionalDocumentInfo has reference info
        add_info = payload.get('AdditionalDocumentInfo', {})
        self.assertIn('AdditionalInfo', add_info)

        print('\n✓ E34 Credit Note Test PASSED')

    # =========================================================================
    # TEST 4: Multiple Items
    # =========================================================================

    def test_04_multiple_items(self):
        """Test invoice with multiple items generates correct Items array."""
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_fiscal.id,
            'company_id': self.company.id,
            'journal_id': self.sale_journal.id,
            'l10n_latam_document_type_id': self.doc_type_e31.id,
            'invoice_date': date.today(),
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.product_good.id,
                    'name': self.product_good.name,
                    'quantity': 1,
                    'price_unit': 100.0,
                }),
                (0, 0, {
                    'product_id': self.product_service.id,
                    'name': self.product_service.name,
                    'quantity': 3,
                    'price_unit': 50.0,
                }),
            ],
        })
        invoice.action_post()

        payload = invoice._build_digifact_payload()

        items = payload['Items']
        self.assertEqual(len(items), 2)

        # Check item types
        self.assertEqual(items[0]['Type'], '1')  # Good
        self.assertEqual(items[1]['Type'], '2')  # Service

        # Check QtyItems in totals
        self.assertEqual(payload['Totals']['QtyItems'], 2)

        print('\n✓ Multiple Items Test PASSED')

    # =========================================================================
    # TEST 5: Validation - No Name
    # =========================================================================

    def test_05_validation_no_name(self):
        """Test that invoice without name raises error."""
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_fiscal.id,
            'company_id': self.company.id,
            'journal_id': self.sale_journal.id,
            'l10n_latam_document_type_id': self.doc_type_e31.id,
            'invoice_date': date.today(),
        })
        # Don't post, so name stays as '/'

        with self.assertRaises(UserError):
            invoice._build_digifact_payload()

        print('\n✓ Validation No Name Test PASSED')

    # =========================================================================
    # TEST 6: Payment Type Computation
    # =========================================================================

    def test_06_payment_type_computation(self):
        """Test that payment type is computed correctly."""
        invoice = self._create_invoice(
            self.partner_fiscal,
            self.doc_type_e31,
            self.product_good,
            post=False,
        )

        # Before posting, should be default
        self.assertEqual(invoice.l10n_do_payment_type, '1')  # Default cash

        # Post and check
        invoice.action_post()

        # Payment type should still be default until payment is registered
        self.assertIn(invoice.l10n_do_payment_type, ['1', '7'])

        print('\n✓ Payment Type Computation Test PASSED')

    # =========================================================================
    # TEST 7: JSON Serialization
    # =========================================================================

    def test_07_json_serialization(self):
        """Test that payload can be serialized to JSON without errors."""
        invoice = self._create_invoice(
            self.partner_fiscal,
            self.doc_type_e31,
            self.product_good,
        )

        payload = invoice._build_digifact_payload()

        # Should not raise exception
        json_str = json.dumps(payload, indent=4, ensure_ascii=False)

        # Should be valid JSON when re-parsed
        reparsed = json.loads(json_str)
        self.assertEqual(reparsed['Version'], payload['Version'])
        self.assertEqual(reparsed['Header']['DocType'], payload['Header']['DocType'])

        print('\n✓ JSON Serialization Test PASSED')

    # =========================================================================
    # TEST 8: Company Configuration (is_live)
    # =========================================================================

    def test_08_company_is_live(self):
        """Test that is_live flag is correctly set in payload."""
        # Test with is_live=False
        invoice = self._create_invoice(
            self.partner_fiscal,
            self.doc_type_e31,
            self.product_good,
        )
        payload = invoice._build_digifact_payload()
        self.assertEqual(payload['live'], '0')

        # Toggle to is_live=True
        self.company.is_live = True
        payload = invoice._build_digifact_payload()
        self.assertEqual(payload['live'], '1')

        # Reset
        self.company.is_live = False

        print('\n✓ Company is_live Test PASSED')

    # =========================================================================
    # TEST 9: Product with Barcode
    # =========================================================================

    def test_09_product_with_barcode(self):
        """Test that product barcode is used as item code."""
        product = self.env['product.product'].create({
            'name': 'Product with Barcode',
            'type': 'consu',
            'list_price': 75.0,
            'barcode': '7891234567890',
        })

        invoice = self._create_invoice(
            self.partner_fiscal,
            self.doc_type_e31,
            product,
        )

        payload = invoice._build_digifact_payload()
        item = payload['Items'][0]

        self.assertEqual(item['Codes'][0]['Name'], 'EAN')
        self.assertEqual(item['Codes'][0]['Value'], '7891234567890')

        print('\n✓ Product with Barcode Test PASSED')

    # =========================================================================
    # TEST 10: Discount Handling
    # =========================================================================

    def test_10_discount_handling(self):
        """Test that discounts are properly included in JSON."""
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_fiscal.id,
            'company_id': self.company.id,
            'journal_id': self.sale_journal.id,
            'l10n_latam_document_type_id': self.doc_type_e31.id,
            'invoice_date': date.today(),
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product_good.id,
                'name': self.product_good.name,
                'quantity': 10,
                'price_unit': 100.0,
                'discount': 10.0,  # 10% discount
            })],
        })
        invoice.action_post()

        payload = invoice._build_digifact_payload()
        item = payload['Items'][0]

        # Should have Discounts block
        self.assertIn('Discounts', item)
        self.assertEqual(item['Discounts']['Discount'][0]['Code'], '%')
        self.assertEqual(item['Discounts']['Discount'][0]['Rate'], '10.00')

        print('\n✓ Discount Handling Test PASSED')

    # =========================================================================
    # TEST 11: Address Information
    # =========================================================================

    def test_11_address_information(self):
        """Test that seller and buyer addresses are properly formatted."""
        invoice = self._create_invoice(
            self.partner_fiscal,
            self.doc_type_e31,
            self.product_good,
        )

        payload = invoice._build_digifact_payload()

        # Check seller address
        seller_address = payload['Seller']['BranchInfo']['AddressInfo']
        self.assertEqual(seller_address['Country'], 'DO')
        self.assertIn('Address', seller_address)

        # Check buyer address
        buyer_address = payload['Buyer']['AddressInfo']
        self.assertEqual(buyer_address['Country'], 'DO')
        self.assertEqual(buyer_address['Address'], self.partner_fiscal.street)

        print('\n✓ Address Information Test PASSED')

    # =========================================================================
    # TEST 12: Email and Phone Extraction
    # =========================================================================

    def test_12_email_phone_extraction(self):
        """Test that multiple emails/phones are extracted correctly."""
        self.partner_fiscal.email = 'test1@example.com;test2@example.com'
        self.partner_fiscal.phone = '809-555-1234,809-555-5678'

        invoice = self._create_invoice(
            self.partner_fiscal,
            self.doc_type_e31,
            self.product_good,
        )

        payload = invoice._build_digifact_payload()

        buyer_contact = payload['Buyer']['Contact']

        # Check emails
        emails = buyer_contact['EmailList']['Email']
        self.assertIn('test1@example.com', emails)
        self.assertIn('test2@example.com', emails)

        # Check phones
        phones = buyer_contact['PhoneList']['Phone']
        self.assertIn('809-555-1234', phones)
        self.assertIn('809-555-5678', phones)

        print('\n✓ Email and Phone Extraction Test PASSED')
