/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

patch(TicketScreen.prototype, {
    async onDoRefund() {
        const order = this.getSelectedOrder();

        if (order && this.pos.config.l10n_do_fiscal_journal) {
            const refund_fiscal_type = this.pos.get_fiscal_type_by_prefix("B04");
            const credit_note_payment_method = this.pos.get_credit_note_payment_method();

            if (!credit_note_payment_method) {
                this.dialog.add(AlertDialog, {
                    title: _t("Error"),
                    body: _t("There are no credit note payment method configured."),
                });
                return;
            }

            if (!refund_fiscal_type) {
                this.dialog.add(AlertDialog, {
                    title: _t("Error"),
                    body: _t(
                        "The fiscal type credit note does not exist. Please activate or configure it."
                    ),
                });
                return;
            }

            if (order.ncf === "") {
                this.dialog.add(AlertDialog, {
                    title: _t("Error"),
                    body: _t("This order has no NCF"),
                });
                return;
            }
        }

        await super.onDoRefund(...arguments);
    },

    async postRefund(destinationOrder) {
        await super.postRefund(destinationOrder);

        const order = this.getSelectedOrder();
        if (
            order &&
            this.pos.config.l10n_do_fiscal_journal &&
            destinationOrder._isRefundAndSaleOrder() &&
            order.ncf
        ) {
            const refund_fiscal_type = this.pos.get_fiscal_type_by_prefix("B04");
            const credit_note_payment_method = this.pos.get_credit_note_payment_method();

            destinationOrder.set_ncf_origin_out(order);
            destinationOrder.set_fiscal_type(refund_fiscal_type);

            const orderDate = new Date(order.validation_date);
            const timeDifferenceDays = (new Date() - orderDate) / (1000 * 60 * 60 * 24);
            if (timeDifferenceDays > 30) {
                // Remove ITBIS taxes from refund lines older than 30 days
                destinationOrder.lines.forEach((orderline) => {
                    orderline.update({ tax_ids: [] });
                });
            }

            destinationOrder.add_paymentline(credit_note_payment_method);
            this.pos.showScreen("PaymentScreen", { orderUuid: destinationOrder.uuid });
        }
    },

    _getSearchFields() {
        const fields = super._getSearchFields(...arguments);
        if (this.pos.config.l10n_do_fiscal_journal) {
            fields.NCF = {
                repr: (order) => order.ncf,
                displayName: _t("NCF"),
                modelField: "ncf",
            };
        }
        return fields;
    },

    _returnAllOrder() {
        const order = this.getSelectedOrder();
        if (!order) {
            this.numberBuffer.reset();
            return;
        }
        for (const orderline of order.lines) {
            const toRefundDetail = this.getToRefundDetail(orderline);
            if (toRefundDetail) {
                const refundableQty =
                    toRefundDetail.line.qty - toRefundDetail.line.refunded_qty;
                if (refundableQty > 0) {
                    toRefundDetail.qty = refundableQty;
                }
            }
        }
    },
});
