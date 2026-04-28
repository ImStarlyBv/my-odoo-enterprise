import json
from datetime import date

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


@tagged('post_install', '-at_install')
class TestEcfJsonGeneration(TransactionCase):

    def setUp(self):
        super().setUp()

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

        self.municipality = self.env['l10n_do.municipality'].search([], limit=1)
        if not self.municipality:
            self.municipality = self.env['l10n_do.municipality'].create({
                'name': 'Santo Domingo de Guzman',
                'code': '010100',
            })
        self.company.l10n_do_municipality_id = self.municipality.id

        self.user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Test User ECF',
            'login': 'test_user_ecf',
            'email': 'test@example.com',
            'company_id': self.company.id,
            'company_ids': [(4, self.company.id)],
        })

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

        self.sale_journal = self.env['account.journal'].create({
            'name': 'Test Sale Journal',
            'type': 'sale',
            'code': 'TSJ',
            'company_id': self.company.id,
        })

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
    # TEST 1: E31 básico (B2B)
    # =========================================================================

    def test_01_e31_invoice_basic(self):
        """E31 invoice (B2B) genera payload JSON válido."""
        invoice = self._create_invoice(
            self.partner_fiscal, self.doc_type_e31, self.product_good, quantity=2, price_unit=100.0,
        )

        payload = invoice._build_ecf_payload()

        self.assertIn('Version', payload)
        self.assertEqual(payload['Version'], '1.0')
        self.assertEqual(payload['CountryCode'], 'DO')
        self.assertEqual(payload['TaxId'], self.company.vat)
        self.assertEqual(payload['live'], '0')

        header = payload['Header']
        self.assertEqual(header['DocType'], '31')
        self.assertIn('IssuedDateTime', header)
        self.assertIn('AdditionalIssueDocInfo', header)

        seller = payload['Seller']
        self.assertEqual(seller['TaxID'], self.company.vat)
        self.assertEqual(seller['Name'], self.company.name)
        self.assertIn('BranchInfo', seller)
        self.assertEqual(seller['BranchInfo']['Name'], '0001')

        buyer = payload['Buyer']
        self.assertEqual(buyer['TaxID'], self.partner_fiscal.vat)
        self.assertEqual(buyer['Name'], self.partner_fiscal.name)
        self.assertIn('AddressInfo', buyer)

        items = payload['Items']
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item['Description'], self.product_good.name)
        self.assertEqual(item['Qty'], '2.00')
        self.assertEqual(item['Price'], '100.00')
        self.assertEqual(item['Type'], '1')

        totals = payload['Totals']
        self.assertEqual(totals['QtyItems'], 1)
        self.assertIn('GrandTotal', totals)
        self.assertIn('InvoiceTotal', totals['GrandTotal'])

        payments = payload['Payments']
        self.assertEqual(len(payments), 1)
        self.assertIn('Code', payments[0])
        self.assertIn('Amount', payments[0])

    # =========================================================================
    # TEST 2: E32 consumidor final
    # =========================================================================

    def test_02_e32_consumer_final(self):
        """E32 con consumidor final genera TaxID = NO_APLICA."""
        if not self.doc_type_e32:
            self.skipTest('Tipo E32 no disponible')

        invoice = self._create_invoice(self.partner_consumer, self.doc_type_e32, self.product_good)
        payload = invoice._build_ecf_payload()

        self.assertEqual(payload['Buyer']['TaxID'], 'NO_APLICA')
        self.assertEqual(payload['Header']['DocType'], '32')

    # =========================================================================
    # TEST 3: E34 nota de crédito con referencia
    # =========================================================================

    def test_03_e34_credit_note(self):
        """E34 genera bloque de referencia con NCF modificado."""
        if not self.doc_type_e34:
            self.skipTest('Tipo E34 no disponible')

        self._create_invoice(self.partner_fiscal, self.doc_type_e31, self.product_good)
        credit_note = self._create_invoice(
            self.partner_fiscal, self.doc_type_e34, self.product_good, price_unit=-100.0,
        )
        credit_note.l10n_do_ecf_modification_code = '1'

        payload = credit_note._build_ecf_payload()

        self.assertEqual(payload['Header']['DocType'], '34')
        add_info = payload.get('AdditionalDocumentInfo', {})
        self.assertIn('AdditionalInfo', add_info)

    # =========================================================================
    # TEST 4: múltiples ítems
    # =========================================================================

    def test_04_multiple_items(self):
        """Factura con múltiples ítems genera el array Items correcto."""
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_fiscal.id,
            'company_id': self.company.id,
            'journal_id': self.sale_journal.id,
            'l10n_latam_document_type_id': self.doc_type_e31.id,
            'invoice_date': date.today(),
            'invoice_line_ids': [
                (0, 0, {'product_id': self.product_good.id, 'name': self.product_good.name, 'quantity': 1, 'price_unit': 100.0}),
                (0, 0, {'product_id': self.product_service.id, 'name': self.product_service.name, 'quantity': 3, 'price_unit': 50.0}),
            ],
        })
        invoice.action_post()

        payload = invoice._build_ecf_payload()
        items = payload['Items']

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['Type'], '1')  # Bien
        self.assertEqual(items[1]['Type'], '2')  # Servicio
        self.assertEqual(payload['Totals']['QtyItems'], 2)

    # =========================================================================
    # TEST 5: validación — sin nombre
    # =========================================================================

    def test_05_validation_no_name(self):
        """Factura sin nombre lanza UserError."""
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_fiscal.id,
            'company_id': self.company.id,
            'journal_id': self.sale_journal.id,
            'l10n_latam_document_type_id': self.doc_type_e31.id,
            'invoice_date': date.today(),
        })
        with self.assertRaises(UserError):
            invoice._build_ecf_payload()

    # =========================================================================
    # TEST 6: tipo de pago computado
    # =========================================================================

    def test_06_payment_type_computation(self):
        """Tipo de pago se calcula correctamente."""
        invoice = self._create_invoice(self.partner_fiscal, self.doc_type_e31, self.product_good, post=False)
        self.assertEqual(invoice.l10n_do_payment_type, '1')
        invoice.action_post()
        self.assertIn(invoice.l10n_do_payment_type, ['1', '7'])

    # =========================================================================
    # TEST 7: serialización JSON
    # =========================================================================

    def test_07_json_serialization(self):
        """El payload se serializa a JSON sin errores y es válido."""
        invoice = self._create_invoice(self.partner_fiscal, self.doc_type_e31, self.product_good)
        payload = invoice._build_ecf_payload()
        json_str = json.dumps(payload, indent=4, ensure_ascii=False)
        reparsed = json.loads(json_str)
        self.assertEqual(reparsed['Version'], payload['Version'])
        self.assertEqual(reparsed['Header']['DocType'], payload['Header']['DocType'])

    # =========================================================================
    # TEST 8: flag is_live
    # =========================================================================

    def test_08_company_is_live(self):
        """El flag is_live se refleja correctamente en el payload."""
        invoice = self._create_invoice(self.partner_fiscal, self.doc_type_e31, self.product_good)
        self.assertEqual(invoice._build_ecf_payload()['live'], '0')

        self.company.is_live = True
        self.assertEqual(invoice._build_ecf_payload()['live'], '1')
        self.company.is_live = False

    # =========================================================================
    # TEST 9: código EAN de producto
    # =========================================================================

    def test_09_product_with_barcode(self):
        """El código EAN del producto se usa en el bloque Codes."""
        product = self.env['product.product'].create({
            'name': 'Product with Barcode',
            'type': 'consu',
            'list_price': 75.0,
            'barcode': '7891234567890',
        })
        invoice = self._create_invoice(self.partner_fiscal, self.doc_type_e31, product)
        item = invoice._build_ecf_payload()['Items'][0]
        self.assertEqual(item['Codes'][0]['Name'], 'EAN')
        self.assertEqual(item['Codes'][0]['Value'], '7891234567890')

    # =========================================================================
    # TEST 10: descuentos
    # =========================================================================

    def test_10_discount_handling(self):
        """Los descuentos se incluyen correctamente en el JSON."""
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
                'discount': 10.0,
            })],
        })
        invoice.action_post()
        item = invoice._build_ecf_payload()['Items'][0]
        self.assertIn('Discounts', item)
        self.assertEqual(item['Discounts']['Discount'][0]['Code'], '%')
        self.assertEqual(item['Discounts']['Discount'][0]['Rate'], '10.00')

    # =========================================================================
    # TEST 11: información de dirección
    # =========================================================================

    def test_11_address_information(self):
        """Emisor y comprador tienen bloque AddressInfo correcto."""
        invoice = self._create_invoice(self.partner_fiscal, self.doc_type_e31, self.product_good)
        payload = invoice._build_ecf_payload()

        seller_address = payload['Seller']['BranchInfo']['AddressInfo']
        self.assertEqual(seller_address['Country'], 'DO')
        self.assertIn('Address', seller_address)

        buyer_address = payload['Buyer']['AddressInfo']
        self.assertEqual(buyer_address['Country'], 'DO')
        self.assertEqual(buyer_address['Address'], self.partner_fiscal.street)

    # =========================================================================
    # TEST 12: extracción de emails y teléfonos
    # =========================================================================

    def test_12_email_phone_extraction(self):
        """Múltiples emails/teléfonos separados por ; o , se extraen correctamente."""
        self.partner_fiscal.email = 'test1@example.com;test2@example.com'
        self.partner_fiscal.phone = '809-555-1234,809-555-5678'

        invoice = self._create_invoice(self.partner_fiscal, self.doc_type_e31, self.product_good)
        buyer_contact = invoice._build_ecf_payload()['Buyer']['Contact']

        self.assertIn('test1@example.com', buyer_contact['EmailList']['Email'])
        self.assertIn('test2@example.com', buyer_contact['EmailList']['Email'])
        self.assertIn('809-555-1234', buyer_contact['PhoneList']['Phone'])
        self.assertIn('809-555-5678', buyer_contact['PhoneList']['Phone'])
