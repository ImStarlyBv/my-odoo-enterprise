/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { SelectionPopup } from "@point_of_sale/app/utils/input_popups/selection_popup";
import { TextInputPopup } from "@point_of_sale/app/utils/input_popups/text_input_popup";
import { SetDocumentTypeButton } from "@l10n_do_pos/js/buttons/SetDocumentTypeButton";
import { VendorNcfButton } from "@l10n_do_pos/js/buttons/VendorNcfButton";
import { _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";

PaymentScreen.components = { ...PaymentScreen.components, SetDocumentTypeButton, VendorNcfButton };

patch(PaymentScreen.prototype, {
    /**
     * Validaciones DGII antes de procesar el pago.
     * Orden de validaciones según normativa:
     *  1. Total > 0
     *  2. Métodos de pago compatibles
     *  3. Tipo de comprobante seleccionado
     *  4. RNC/Cédula cuando el tipo lo requiere
     *  5. Venta >= RD$250,000 requiere cliente identificado
     *  6. B14/E44 no puede tener ITBIS ni ISC
     *  7. Dirección de la orden (refund vs invoice)
     *  8. Líneas con cantidad cero
     *  9. Partner de NC coincide con orden
     */
    async validateOrder(isForceValidate) {
        if (!this.pos.config.l10n_do_is_fiscal) {
            return super.validateOrder(...arguments);
        }

        const order = this.currentOrder;
        const client = order.get_partner();
        const total = order.get_total_with_tax();
        const doc_type = order.get_document_type();

        if (total === 0) {
            this.dialog.add(AlertDialog, {
                title: _t("Venta en cero"),
                body: _t("No puedes realizar ventas en cero. Agrega un producto con valor."),
            });
            return;
        }

        if (!await this.analyze_payment_methods()) return;

        if (!doc_type) {
            this.dialog.add(AlertDialog, {
                title: _t("Tipo de comprobante requerido"),
                body: _t("Selecciona un tipo de comprobante para continuar."),
            });
            return;
        }

        if (doc_type.is_vat_required && !client) {
            this.dialog.add(AlertDialog, {
                title: _t("Cliente requerido"),
                body: sprintf(
                    _t("El tipo \"%s\" requiere un cliente con RNC o Cédula."),
                    doc_type.name
                ),
            });
            return;
        }

        if (doc_type.is_vat_required && !client?.vat) {
            this.dialog.add(AlertDialog, {
                title: _t("RNC / Cédula requerido"),
                body: sprintf(
                    _t("El tipo \"%s\" requiere que el cliente tenga RNC o Cédula."),
                    doc_type.name
                ),
            });
            return;
        }

        if (doc_type.is_vat_required && client?.vat) {
            const cleaned = client.vat.replace(/[-\s]/g, "");
            if (cleaned.length !== 9 && cleaned.length !== 11) {
                this.dialog.add(AlertDialog, {
                    title: _t("RNC / Cédula inválido"),
                    body: _t("El RNC debe tener 9 dígitos y la Cédula 11, sin guiones ni espacios."),
                });
                return;
            }
        }

        if (total >= 250000.0 && (!client || !client.vat)) {
            this.dialog.add(AlertDialog, {
                title: _t("Venta mayor a RD$ 250,000.00"),
                body: _t("La normativa DGII exige identificar al cliente en ventas iguales o mayores a RD$ 250,000."),
            });
            return;
        }

        // B14 / E44 no pueden tener ITBIS ni ISC
        const specialTypes = ["special", "e-special"];
        if (specialTypes.includes(doc_type.l10n_do_ncf_type)) {
            let hasTaxes = false;
            for (const line of order.get_orderlines()) {
                for (const tax of line._getProductTaxesAfterFiscalPosition?.() || []) {
                    if (
                        (tax.tax_group_id?.name === "ITBIS" && tax.amount !== 0) ||
                        tax.tax_group_id?.name === "ISC"
                    ) {
                        hasTaxes = true;
                        break;
                    }
                }
                if (hasTaxes) break;
            }
            if (hasTaxes) {
                this.dialog.add(AlertDialog, {
                    title: sprintf(_t("Error con %s"), doc_type.name),
                    body: sprintf(
                        _t("El tipo \"%s\" no puede tener ITBIS ni ISC. Cambia la posición fiscal para eliminarlos."),
                        doc_type.name
                    ),
                });
                return;
            }
        }

        if (doc_type.internal_type === "credit_note" && total > 0) {
            this.dialog.add(AlertDialog, {
                title: sprintf(_t("Error con %s"), doc_type.name),
                body: _t("Una nota de crédito no puede tener monto positivo."),
            });
            return;
        }

        if (doc_type.internal_type === "invoice" && total < 0) {
            this.dialog.add(AlertDialog, {
                title: sprintf(_t("Error con %s"), doc_type.name),
                body: _t("Una factura de venta no puede tener monto negativo."),
            });
            return;
        }

        const zeroQtyLines = order
            .get_orderlines()
            .filter((l) => l.quantity === 0)
            .map((l) => l.product_id.display_name);

        if (zeroQtyLines.length > 0) {
            this.dialog.add(AlertDialog, {
                title: _t("Productos con cantidad cero"),
                body: _t("Los siguientes productos tienen cantidad cero: ") + zeroQtyLines.join(", "),
            });
            return;
        }

        for (const line of order.payment_ids) {
            if (
                line.credit_note_partner_id &&
                client &&
                line.credit_note_partner_id !== client.id
            ) {
                this.dialog.add(AlertDialog, {
                    title: _t("Cliente de NC no coincide"),
                    body: _t("El cliente de la nota de crédito no coincide con el de la orden."),
                });
                return;
            }
        }

        await super.validateOrder(...arguments);
    },

    /**
     * Después de que super guarda la orden al servidor (lo que dispara
     * _process_saved_order → invoice creation → NCF assignment), leemos
     * el NCF de vuelta y lo almacenamos en la orden local.
     *
     * Si el NCF es e-CF (prefijo E3x) y el QR no está disponible aún,
     * se hace polling hasta 3 veces (cada 2s). Si el QR no llega, se
     * muestra una alerta informando que el recibo se imprimirá sin QR.
     *
     * Owl re-renderiza el recibo reactivamente con los datos disponibles.
     */
    async _finalizeValidation() {
        const order = this.currentOrder;
        const isFiscal = this.pos.config.l10n_do_is_fiscal;

        if (isFiscal) {
            this.env.services.ui.block();
        }

        try {
            await super._finalizeValidation(...arguments);

            if (isFiscal && order.id && !order.l10n_do_fiscal_number) {
                const data = await this.pos.data.call(
                    "pos.order",
                    "_finalize_fiscal_order",
                    [order.id]
                );
                order.set_l10n_do_fiscal_data(data);

                // Polling e-CF: si el QR no llegó aún, reintentar hasta 3 veces
                if (data.is_ecf && data.ecf_pending) {
                    let qrReady = false;
                    for (let attempt = 0; attempt < 3 && !qrReady; attempt++) {
                        await new Promise((resolve) => setTimeout(resolve, 2000));
                        const ecfResult = await this.pos.data.call(
                            "pos.order",
                            "poll_ecf_status",
                            [order.id]
                        );
                        qrReady = ecfResult.ready;
                        if (qrReady) {
                            order.set_ecf_data(
                                ecfResult.ecf_qr_image,
                                ecfResult.ecf_codigo_seguridad
                            );
                        }
                    }
                    if (!qrReady) {
                        this.env.services.notification.add(
                            _t("El e-CF fue enviado a la DGII pero el QR aún no está disponible. El recibo se imprimirá sin código QR."),
                            { type: "warning", sticky: false }
                        );
                    }
                }
            }
        } finally {
            if (isFiscal) {
                this.env.services.ui.unblock();
            }
        }
    },

    /**
     * Intercepta la adición de líneas de pago con método Nota de Crédito.
     * Abre un selector o popup para elegir la NC y valida su disponibilidad.
     */
    async addNewPaymentLine(paymentMethod) {
        if (!this.pos.config.l10n_do_is_fiscal || !paymentMethod?.is_credit_note) {
            return super.addNewPaymentLine(...arguments);
        }

        const currentPartner = this.currentOrder.get_partner();
        const consumerPartnerId = this.pos.config.l10n_do_default_consumer_partner_id?.[0];
        let credit_note;

        if (currentPartner && currentPartner.id !== consumerPartnerId) {
            const credit_notes = await this.pos.get_credit_notes(currentPartner.id);
            credit_note = await makeAwaitable(this.dialog, SelectionPopup, {
                title: _t("Seleccionar Nota de Crédito"),
                list: credit_notes,
            });
            if (!credit_note) return false;
        } else {
            const ncf = await makeAwaitable(this.dialog, TextInputPopup, {
                startingValue: "",
                title: _t("Ingresa el NCF de la Nota de Crédito"),
                placeholder: _t("NCF"),
            });
            if (!ncf) return false;
            credit_note = await this.pos.get_credit_note(ncf);
        }

        // Verificar NC ya usada en esta orden
        for (const line of this.currentOrder.payment_ids) {
            if (
                line.payment_method_id?.is_credit_note &&
                line.credit_note_ncf === credit_note.ncf
            ) {
                this.dialog.add(AlertDialog, {
                    title: _t("Error"),
                    body: _t("Esta nota de crédito ya fue aplicada a esta orden."),
                });
                return false;
            }
        }

        if (credit_note.residual_amount <= 0) {
            this.dialog.add(AlertDialog, {
                title: _t("Error"),
                body: sprintf(_t("La nota de crédito %s no tiene saldo disponible."), credit_note.ncf),
            });
            return false;
        }

        const credit_note_partner = this.pos.models["res.partner"].get(credit_note.partner_id);
        if (!credit_note_partner) {
            this.dialog.add(AlertDialog, {
                title: _t("Error"),
                body: _t("El cliente de la nota de crédito no está en el POS. Selecciona el cliente correcto."),
            });
            return false;
        }

        const due_before = this.currentOrder.get_due();
        const newLine = this.currentOrder.add_paymentline(paymentMethod);
        if (newLine) {
            if (!currentPartner) {
                this.currentOrder.set_partner(credit_note_partner);
            }
            newLine.set_credit_note_data(credit_note.ncf, credit_note.partner_id);
            if (credit_note.residual_amount < due_before) {
                newLine.set_amount(credit_note.residual_amount);
            }
            this.numberBuffer.reset();
            return true;
        }
        return false;
    },

    updateSelectedPaymentline() {
        if (
            this.pos.config.l10n_do_is_fiscal &&
            this.selectedPaymentLine?.payment_method_id?.is_credit_note
        ) {
            this.dialog.add(AlertDialog, {
                title: _t("Error"),
                body: _t("No puedes editar una línea de pago con Nota de Crédito."),
            });
            return;
        }
        super.updateSelectedPaymentline(...arguments);
    },

    /**
     * Valida restricciones de combinación de métodos de pago según la DGII.
     * @returns {boolean} false si hay un error de combinación
     */
    async analyze_payment_methods() {
        const order = this.currentOrder;
        const total = order.get_total_with_tax();
        let total_in_bank = 0;
        let total_in_pay_later = 0;
        let has_cash = false;

        for (const line of order.payment_ids) {
            if (line.payment_method_id?.type === "bank") {
                total_in_bank += Number(line.amount);
            }
            if (
                line.payment_method_id?.type === "pay_later" &&
                !line.payment_method_id?.is_credit_note
            ) {
                total_in_pay_later += Number(line.amount);
            }
            if (line.payment_method_id?.type === "cash") {
                has_cash = true;
            }
            if (line.payment_method_id?.is_credit_note && !order._isRefundOrder()) {
                if (!line.credit_note_ncf) {
                    this.dialog.add(AlertDialog, {
                        title: _t("Error en Nota de Crédito"),
                        body: _t("Hay un error en el pago con NC. Elimina la línea y vuélvela a agregar."),
                    });
                    return false;
                }
                const cn = await this.pos.get_credit_note(line.credit_note_ncf);
                if (cn.residual_amount <= 0) {
                    this.dialog.add(AlertDialog, {
                        title: _t("Error en Nota de Crédito"),
                        body: _t("La nota de crédito no tiene saldo. Elimina la línea y selecciona otra."),
                    });
                    return false;
                }
                if (cn.residual_amount < line.amount) {
                    this.dialog.add(AlertDialog, {
                        title: _t("Error en Nota de Crédito"),
                        body: _t("El monto de la NC es menor al monto ingresado. Ajusta o elimina la línea."),
                    });
                    return false;
                }
            }
        }

        const abs = (v) => Math.round(Math.abs(v) * 100) / 100;

        if (abs(total) < abs(total_in_bank)) {
            this.dialog.add(AlertDialog, {
                title: _t("Pago con tarjeta"),
                body: _t("El pago con tarjeta no puede exceder el total de la orden."),
            });
            return false;
        }

        if (abs(total) < abs(total_in_pay_later)) {
            this.dialog.add(AlertDialog, {
                title: _t("Pago a crédito"),
                body: _t("El pago a crédito no puede exceder el total de la orden."),
            });
            return false;
        }

        if (abs(total) < abs(total_in_pay_later + total_in_bank)) {
            this.dialog.add(AlertDialog, {
                title: _t("Tarjeta + crédito"),
                body: _t("La suma de tarjeta y crédito no puede exceder el total de la orden."),
            });
            return false;
        }

        if (abs(total_in_bank) === abs(total) && has_cash) {
            this.dialog.add(AlertDialog, {
                title: _t("Tarjeta + efectivo"),
                body: _t("La tarjeta cubre el total. Elimina el efectivo o reduce el monto de tarjeta."),
            });
            return false;
        }

        if (abs(total_in_pay_later) === abs(total) && total_in_pay_later && has_cash) {
            this.dialog.add(AlertDialog, {
                title: _t("Crédito + efectivo"),
                body: _t("El crédito cubre el total. Elimina el efectivo o reduce el monto a crédito."),
            });
            return false;
        }

        return true;
    },
});
