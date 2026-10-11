from unittest.mock import patch

import requests

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.l10n_do_accounting.tests.common import L10nDOTestsCommon

POST = 'odoo.addons.l10n_do_electronic_invoice.models.account_move.requests.post'


class FakeResponse:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self.ok = status_code < 400
        self._data = data
        self.text = str(data)

    def json(self):
        return self._data


@tagged('post_install', '-at_install')
class TestEcfSend(L10nDOTestsCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.do_company.write({
            'l10n_do_ecf_issuer': True,
            'ecf_api_url': 'https://ecf.invalid',
            'ecf_api_key': 'test-key',
            'ecf_auto_send': True,
            'l10n_do_enable_resend_button': True,
        })
        cls.e_fiscal = cls.do_document_type['e-fiscal']
        cls.e_fiscal.ecf_sequence_max = 100
        cls.accepted = FakeResponse(200, {
            'trackId': 'TRACK-1', 'qrUrl': '', 'codigoSeguridad': 'ABC123', 'estado': '1',
        })

    def _ecf_invoice(self):
        # El e-NCF lo asigna la secuencia: en e-CF el número no es editable
        return self._create_l10n_do_invoice(data={'document_type': self.e_fiscal})

    def test_01_accepted(self):
        invoice = self._ecf_invoice()
        with patch(POST, return_value=self.accepted):
            invoice.action_post()
        self.assertEqual(invoice.state, 'posted')
        self.assertEqual(invoice.ecf_validation_status, '1')
        self.assertEqual(invoice.ecf_track_id, 'TRACK-1')

    def test_02_timeout_posts_and_queues(self):
        invoice = self._ecf_invoice()
        with patch(POST, side_effect=requests.exceptions.Timeout()):
            invoice.action_post()
        self.assertEqual(invoice.state, 'posted')
        self.assertEqual(invoice.ecf_validation_status, 'to_send')
        self.assertTrue(invoice.l10n_do_fiscal_number)

    def test_03_connection_error_and_5xx_queue(self):
        invoice = self._ecf_invoice()
        with patch(POST, side_effect=requests.exceptions.ConnectionError('down')):
            invoice.action_post()
        self.assertEqual(invoice.ecf_validation_status, 'to_send')
        with patch(POST, return_value=FakeResponse(502, 'Bad Gateway')):
            invoice.action_resend_dgii()
        self.assertEqual(invoice.ecf_validation_status, 'to_send')
        with patch(POST, return_value=FakeResponse(401, {'error': 'Invalid API key'})):
            invoice.action_resend_dgii()
        self.assertEqual(invoice.ecf_validation_status, 'to_send')

    def test_04_api_rejection_blocks_posting(self):
        invoice = self._ecf_invoice()
        with patch(POST, return_value=FakeResponse(400, {'error': 'RNC inválido'})), \
                self.assertRaises(ValidationError):
            invoice.action_post()
        self.assertEqual(invoice.state, 'draft')

    def test_05_cron_sends_pending(self):
        invoice = self._ecf_invoice()
        with patch(POST, side_effect=requests.exceptions.Timeout()):
            invoice.action_post()
        with patch(POST, return_value=self.accepted):
            self.env['account.move']._cron_ecf_send_pending()
        self.assertEqual(invoice.ecf_validation_status, '1')

    def test_06_cron_ships_disabled(self):
        cron = self.env.ref('l10n_do_electronic_invoice.ir_cron_ecf_send_pending')
        self.assertFalse(cron.active)

    def test_07_dgii_rejected_status_is_stored(self):
        invoice = self._ecf_invoice()
        rejected = FakeResponse(200, {'trackId': 'TRACK-2', 'estado': '2'})
        with patch(POST, return_value=rejected):
            invoice.action_post()
        self.assertEqual(invoice.ecf_validation_status, '2')

    def test_08_sequence_limit_applies_on_direct_post(self):
        """El POS publica con _post directo: el límite de NCF debe aplicar igual."""
        first = self._ecf_invoice()
        with patch(POST, return_value=self.accepted):
            first.action_post()
        self.e_fiscal.ecf_sequence_max = 1
        self.e_fiscal.invalidate_recordset()
        second = self._ecf_invoice()
        with self.assertRaises(UserError):
            second._post()

    def test_09_cannot_resend_sent_ecf(self):
        invoice = self._ecf_invoice()
        with patch(POST, return_value=self.accepted) as post:
            invoice.action_post()
            with self.assertRaises(ValidationError):
                invoice.action_resend_dgii()
            self.assertEqual(post.call_count, 1)
