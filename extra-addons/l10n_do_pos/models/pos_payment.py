from odoo import api, fields, models, _
from odoo.tools import float_is_zero


class PosPayment(models.Model):
    """
    Extiende pos.payment para crear account.payment individuales en POS fiscal.

    En un POS normal, Odoo agrupa los pagos por método al cerrar la sesión.
    En POS fiscal, cada pago genera su propio account.payment inmediatamente
    para que la conciliación quede vinculada a la factura correspondiente.

    Tipos de pago manejados:
    - Efectivo (is_cash_count=True): se agrupa por sesión en un solo payment
    - No efectivo (tarjeta, banco, etc.): un account.payment por pago
    - Nota de crédito (is_credit_note=True): se concilia con la account.move
      de la NC existente sin crear un nuevo payment
    """
    _inherit = 'pos.payment'

    def _get_payment_values(self, payment):
        """
        Construye los vals para crear un account.payment desde un pos.payment.
        :param payment: pos.payment recordset (puede ser uno o varios agrupados)
        :return: dict de vals para account.payment.create()
        """
        amount = sum(payment.mapped('amount')) if len(payment) > 1 else payment.amount
        payment_record = payment[0] if len(payment) > 1 else payment
        payment_method = payment_record.payment_method_id
        session = payment_record.session_id
        return {
            'amount': amount,
            'payment_type': 'inbound' if amount >= 0 else 'outbound',
            'date': payment_record.payment_date,
            'partner_id': payment_record.partner_id.id if payment_record.partner_id else False,
            'currency_id': payment_record.currency_id.id,
            'pos_session_id': session.id,
            'ref': _('%s POS payments from %s') % (payment_method.name, session.name),
            'pos_payment_method_id': payment_method.id,
            'journal_id': payment_method.journal_id.id,
        }

    def _create_payment_moves(self, is_reverse=False):
        """
        Crea account.payment individuales para cada pago en POS fiscal.

        - Pagos no efectivo (tarjeta, banco): un account.payment por pago
        - Pagos en efectivo: un único account.payment agrupado por sesión
        - Pagos NC: concilia la account.move de la NC existente sin crear payment

        Para POS no fiscal delega al comportamiento estándar de Odoo.
        """
        if not self:
            return self.env['account.move']

        config = self.mapped('session_id.config_id')[:1]
        if not config.l10n_do_is_fiscal:
            return super()._create_payment_moves(is_reverse)

        result = self.env['account.move']

        # --- Pagos no efectivo (tarjeta, banco, etc.) ---
        non_cash = self.filtered(
            lambda p: not p.payment_method_id.is_cash_count
            and not p.payment_method_id.is_credit_note
        )
        for payment in non_cash:
            order = payment.pos_order_id
            if (
                payment.payment_method_id.type == 'pay_later'
                or float_is_zero(payment.amount, precision_rounding=order.currency_id.rounding)
            ):
                continue
            account_payment = self.env['account.payment'].create(
                self._get_payment_values(payment)
            )
            account_payment.action_post()
            account_payment.move_id.write({'pos_payment_ids': payment.ids})
            payment.write({'account_move_id': account_payment.move_id.id})
            result |= account_payment.move_id

        # --- Pagos en efectivo: agrupados en un solo account.payment ---
        cash_payments = self.filtered(
            lambda p: p.payment_method_id.is_cash_count
            and not p.payment_method_id.is_credit_note
        )
        if cash_payments:
            vals = self._get_payment_values(cash_payments)
            if vals['amount'] > 0:
                account_payment_cash = self.env['account.payment'].create(vals)
                account_payment_cash.action_post()
                account_payment_cash.move_id.write({'pos_payment_ids': cash_payments.ids})
                cash_payments.write({'account_move_id': account_payment_cash.move_id.id})
                result |= account_payment_cash.move_id

        # --- Pagos con Nota de Crédito: conciliar la NC existente ---
        for cn_payment in self.filtered(
            lambda p: p.payment_method_id.is_credit_note and p.name
        ):
            credit_note = self.env['account.move'].search([
                ('partner_id', '=', cn_payment.partner_id.id),
                ('l10n_do_fiscal_number', '=', cn_payment.name),
                ('move_type', '=', 'out_refund'),
                ('company_id', '=', self.env.company.id),
                ('state', '=', 'posted'),
            ], limit=1)
            if credit_note and cn_payment.amount > 0:
                credit_note.write({'pos_payment_ids': cn_payment.ids})
                cn_payment.write({'account_move_id': credit_note.id})
                result |= credit_note

        return result
