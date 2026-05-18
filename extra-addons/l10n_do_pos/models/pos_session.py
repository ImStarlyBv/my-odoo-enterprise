from odoo import models


class PosSession(models.Model):
    """
    Extiende pos.session para el POS fiscal dominicano.

    En un POS fiscal, cada factura ya tiene su account.payment vinculado
    (creado por pos.payment._create_payment_moves). Para evitar duplicar
    asientos, se vacían las estructuras de contabilización que Odoo genera
    por defecto al cerrar la sesión.
    """
    _inherit = 'pos.session'

    def _load_pos_data_models(self, config_id):
        """Agrega l10n_latam.document.type a los modelos cargados en el POS."""
        result = super()._load_pos_data_models(config_id)
        result.append('l10n_latam.document.type')
        return result

    def _create_invoice_receivable_lines(self, data):
        """En POS fiscal no se generan líneas de cobro combinadas por sesión."""
        if self.config_id.l10n_do_is_fiscal:
            data.update({
                'combine_invoice_receivable_lines': {},
                'split_invoice_receivable_lines': {},
            })
            return data
        return super()._create_invoice_receivable_lines(data)

    def _create_bank_payment_moves(self, data):
        """En POS fiscal los pagos bancarios ya fueron registrados por pos.payment."""
        if self.config_id.l10n_do_is_fiscal:
            data.update({
                'payment_method_to_receivable_lines': {},
                'payment_to_receivable_lines': {},
            })
            return data
        return super()._create_bank_payment_moves(data)

    def _create_cash_statement_lines_and_cash_move_lines(self, data):
        """En POS fiscal el efectivo ya fue contabilizado por pos.payment."""
        if self.config_id.l10n_do_is_fiscal:
            AccountMoveLine = self.env['account.move.line']
            data.update({
                'split_cash_receivable_lines': AccountMoveLine,
                'split_cash_statement_lines': AccountMoveLine,
                'combine_cash_receivable_lines': AccountMoveLine,
                'combine_cash_statement_lines': AccountMoveLine,
            })
            return data
        return super()._create_cash_statement_lines_and_cash_move_lines(data)
