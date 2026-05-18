/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

patch(TicketScreen.prototype, {
    /**
     * Antes de procesar la devolución, valida:
     * - La orden tiene NCF
     * - Existe un tipo de comprobante B04 o E34
     * - Existe el método de pago Nota de Crédito
     */
    async onDoRefund() {
        const order = this.getSelectedOrder();

        if (order && this.pos.config.l10n_do_is_fiscal) {
            if (!order.l10n_do_fiscal_number) {
                this.dialog.add(AlertDialog, {
                    title: _t("Error"),
                    body: _t("Esta orden no tiene NCF asignado. No se puede generar una devolución."),
                });
                return;
            }

            // Detectar tipo: B-prefix → B04, E-prefix → E34
            const isEcf = order.l10n_do_fiscal_number.startsWith("E");
            const creditNoteNcfType = isEcf ? "e-credit_note" : "credit_note";
            const refundDocType = this.pos.get_doc_type_by_ncf_type(creditNoteNcfType);

            if (!refundDocType) {
                this.dialog.add(AlertDialog, {
                    title: _t("Error"),
                    body: isEcf
                        ? _t("No existe el tipo E34 (Nota de Crédito Electrónica). Configúralo en el diario.")
                        : _t("No existe el tipo B04 (Nota de Crédito). Configúralo en el diario."),
                });
                return;
            }

            const creditNotePaymentMethod = this.pos.get_credit_note_payment_method();
            if (!creditNotePaymentMethod) {
                this.dialog.add(AlertDialog, {
                    title: _t("Error"),
                    body: _t("No hay método de pago Nota de Crédito configurado en este POS."),
                });
                return;
            }
        }

        await super.onDoRefund(...arguments);
    },

    /**
     * Después de crear la orden de devolución:
     * - Asigna el tipo B04/E34 según el prefijo del NCF original
     * - Guarda el NCF de la orden original como NCF afectado
     * - Si han pasado más de 30 días, elimina el ITBIS (norma DGII)
     * - Agrega el pago NC y navega al PaymentScreen
     */
    async postRefund(destinationOrder) {
        await super.postRefund(destinationOrder);

        const origin = this.getSelectedOrder();
        if (
            !origin ||
            !this.pos.config.l10n_do_is_fiscal ||
            !destinationOrder._isRefundOrder() ||
            !origin.l10n_do_fiscal_number
        ) return;

        const isEcf = origin.l10n_do_fiscal_number.startsWith("E");
        const creditNoteNcfType = isEcf ? "e-credit_note" : "credit_note";
        const refundDocType = this.pos.get_doc_type_by_ncf_type(creditNoteNcfType);
        const creditNotePaymentMethod = this.pos.get_credit_note_payment_method();

        destinationOrder.set_origin_ncf(origin);
        destinationOrder.set_document_type(refundDocType);

        // Remover ITBIS si la orden original tiene más de 30 días (norma DGII)
        const orderDate = new Date(origin.validation_date);
        const daysDiff = (new Date() - orderDate) / (1000 * 60 * 60 * 24);
        if (daysDiff > 30) {
            for (const line of destinationOrder.lines) {
                line.update({ tax_ids: [] });
            }
        }

        destinationOrder.add_paymentline(creditNotePaymentMethod);
        this.pos.showScreen("PaymentScreen", { orderUuid: destinationOrder.uuid });
    },

    /**
     * Agrega el campo NCF al buscador del historial de órdenes.
     */
    _getSearchFields() {
        const fields = super._getSearchFields(...arguments);
        if (this.pos.config.l10n_do_is_fiscal) {
            fields.NCF = {
                repr: (order) => order.l10n_do_fiscal_number || "",
                displayName: _t("NCF"),
                modelField: "l10n_do_fiscal_number",
            };
        }
        return fields;
    },

    /**
     * Selecciona todas las líneas de la orden para devolución completa.
     */
    _returnAllOrder() {
        const order = this.getSelectedOrder();
        if (!order) {
            this.numberBuffer.reset();
            return;
        }
        for (const orderline of order.lines) {
            const toRefundDetail = this.getToRefundDetail(orderline);
            if (toRefundDetail) {
                const refundableQty = toRefundDetail.line.qty - toRefundDetail.line.refunded_qty;
                if (refundableQty > 0) {
                    toRefundDetail.qty = refundableQty;
                }
            }
        }
    },
});
