/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { SelectionPopup } from "@point_of_sale/app/utils/input_popups/selection_popup";
import { TextInputPopup } from "@point_of_sale/app/utils/input_popups/text_input_popup";
import { _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";
import { SetFiscalTypeButton } from "@l10n_do_pos/js/buttons/SetFiscalTypeButton";

// Register SetFiscalTypeButton so it can be used in PaymentScreen templates
PaymentScreen.components = { ...PaymentScreen.components, SetFiscalTypeButton };

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        if (this.pos.config.l10n_do_fiscal_journal) {
            const current_order = this.currentOrder;
            const client = current_order.get_partner();
            const total = current_order.get_total_with_tax();
            const fiscal_type = current_order.get_fiscal_type();

            if (total === 0) {
                this.dialog.add(AlertDialog, {
                    title: _t("Sale in 0"),
                    body: _t("You cannot make sales in 0, please add a product with value"),
                });
                return;
            }

            if (!await this.analyze_payment_methods()) {
                return;
            }

            if (!current_order.fiscal_type) {
                this.dialog.add(AlertDialog, {
                    title: _t("Required fiscal type"),
                    body: _t("Please select a fiscal type"),
                });
                return;
            }

            if (fiscal_type.requires_document && !client) {
                this.dialog.add(AlertDialog, {
                    title: _t("Required document (RNC/Cedula)"),
                    body: sprintf(
                        _t("For invoice fiscal type %s its necessary customer, please select customer"),
                        fiscal_type.name
                    ),
                });
                return;
            }

            if (fiscal_type.requires_document && !client.vat) {
                this.dialog.add(AlertDialog, {
                    title: _t("Required document (RNC/Cedula)"),
                    body: sprintf(
                        _t("For invoice fiscal type %s it is necessary for the customer have RNC or Cedula"),
                        fiscal_type.name
                    ),
                });
                return;
            }

            if (
                fiscal_type.requires_document &&
                !(client.vat.length === 9 || client.vat.length === 11)
            ) {
                this.dialog.add(AlertDialog, {
                    title: _t("Incorrect document (RNC/Cedula)"),
                    body: sprintf(
                        _t("For invoice fiscal type %s it is necessary for the customer have correct RNC or Cedula without dashes or spaces"),
                        fiscal_type.name
                    ),
                });
                return;
            }

            if (total >= 250000.0 && (!client || !client.vat)) {
                this.dialog.add(AlertDialog, {
                    title: _t("Sale greater than RD$ 250,000.00"),
                    body: _t("For this sale it is necessary for the customer have ID"),
                });
                return;
            }

            if (["B14", "E14"].includes(fiscal_type.code)) {
                let has_taxes = false;
                current_order.get_orderlines().forEach((orderline) => {
                    orderline._getProductTaxesAfterFiscalPosition?.().forEach((tax) => {
                        if (
                            (tax.tax_group_id?.name === "ITBIS" && tax.amount !== 0) ||
                            tax.tax_group_id?.name === "ISC"
                        ) {
                            has_taxes = true;
                        }
                    });
                });
                if (has_taxes) {
                    this.dialog.add(AlertDialog, {
                        title: sprintf(_t("Error with Fiscal Type %s"), fiscal_type.name),
                        body: sprintf(
                            _t("You cannot pay order of Fiscal Type %s with ITBIS/ISC. Please select correct fiscal position for remove ITBIS and ISC"),
                            fiscal_type.name
                        ),
                    });
                    return;
                }
            }

            if (fiscal_type.type === "out_refund" && total > 0) {
                this.dialog.add(AlertDialog, {
                    title: sprintf(_t("Error with Fiscal Type %s"), fiscal_type.name),
                    body: sprintf(
                        _t("You cannot pay order of Fiscal Type %s with amount greater than 0. Please select delete the order and create a new one"),
                        fiscal_type.name
                    ),
                });
                return;
            }

            if (fiscal_type.type === "out_invoice" && total < 0) {
                this.dialog.add(AlertDialog, {
                    title: sprintf(_t("Error with Fiscal Type %s"), fiscal_type.name),
                    body: sprintf(
                        _t("You cannot pay order of Fiscal Type %s with amount less than 0. Please select delete the order and create a new one"),
                        fiscal_type.name
                    ),
                });
                return;
            }

            const zeroQtyLines = current_order
                .get_orderlines()
                .filter((l) => l.quantity === 0)
                .map((l) => l.product_id.display_name);

            if (zeroQtyLines.length > 0) {
                this.dialog.add(AlertDialog, {
                    title: _t("Zero Quantity Products"),
                    body:
                        _t("The following products have zero quantity in the order: ") +
                        zeroQtyLines.join(", ") +
                        _t(". Please remove them or set a valid quantity."),
                });
                return;
            }

            for (const line of current_order.payment_ids) {
                if (line.credit_note_partner_id && client && line.credit_note_partner_id !== client.id) {
                    this.dialog.add(AlertDialog, {
                        title: _t("Credit Note Partner Mismatch"),
                        body: _t(
                            "The customer associated with the credit note does not match the customer on the order. Please select the correct customer."
                        ),
                    });
                    return;
                }
            }
        }

        await super.validateOrder(...arguments);
    },

    async _finalizeValidation() {
        const current_order = this.currentOrder;
        if (
            this.pos.config.l10n_do_fiscal_journal &&
            !current_order.to_invoice &&
            !current_order.ncf
        ) {
            this.env.services.ui.block();
            try {
                const fiscal_data = await this.pos.get_fiscal_data(current_order);
                console.log("NCF Generated", fiscal_data);
                current_order.set_l10n_do_fiscal_data(fiscal_data);
            } catch (error) {
                this.env.services.ui.unblock();
                throw error;
            }
            this.env.services.ui.unblock();
        }
        await super._finalizeValidation();
    },

    async addNewPaymentLine(paymentMethod) {
        if (
            this.pos.config.l10n_do_fiscal_journal &&
            paymentMethod?.is_credit_note
        ) {
            const current_partner = this.currentOrder.get_partner();
            let credit_note;

            if (current_partner && current_partner.id !== this.pos.config.pos_partner_id?.[0]) {
                const credit_notes = await this.pos.get_credit_notes(current_partner.id);
                credit_note = await makeAwaitable(this.dialog, SelectionPopup, {
                    title: _t("Select Credit Note"),
                    list: credit_notes,
                });
                if (!credit_note) return;
            } else {
                const ncf = await makeAwaitable(this.dialog, TextInputPopup, {
                    startingValue: "",
                    title: _t("Please enter the NCF"),
                    placeholder: _t("NCF"),
                });
                if (!ncf) return;
                credit_note = await this.pos.get_credit_note(ncf);
            }

            const credit_note_partner = this.pos.models["res.partner"].get(credit_note.partner_id);

            for (const line of this.currentOrder.payment_ids) {
                if (line.payment_method_id?.is_credit_note && line.credit_note_ncf === credit_note.ncf) {
                    this.dialog.add(AlertDialog, {
                        title: _t("Error"),
                        body: _t("The credit note has already been used in this order"),
                    });
                    return false;
                }
            }

            if (credit_note.residual_amount <= 0) {
                this.dialog.add(AlertDialog, {
                    title: _t("Error"),
                    body: sprintf(_t("Credit note %s has no available amount."), credit_note.ncf),
                });
                return false;
            }

            if (!credit_note_partner) {
                this.dialog.add(AlertDialog, {
                    title: _t("Error"),
                    body: _t(
                        "The customer of the credit note is not the same as the current order, please select the correct customer."
                    ),
                });
                return false;
            }

            const amount_due_before_payment = this.currentOrder.get_due();
            const newPaymentline = this.currentOrder.add_paymentline(paymentMethod);

            if (newPaymentline) {
                if (!current_partner) {
                    this.currentOrder.set_partner(credit_note_partner);
                }
                newPaymentline.set_fiscal_data(credit_note.ncf, credit_note.partner_id);
                if (credit_note.residual_amount < amount_due_before_payment) {
                    newPaymentline.set_amount(credit_note.residual_amount);
                }
                this.numberBuffer.reset();
                return true;
            }
            return false;
        }

        return super.addNewPaymentLine(...arguments);
    },

    updateSelectedPaymentline() {
        if (
            this.selectedPaymentLine?.payment_method_id?.is_credit_note &&
            this.pos.config.l10n_do_fiscal_journal
        ) {
            this.dialog.add(AlertDialog, {
                title: _t("Error"),
                body: _t("You cannot edit a credit note payment line"),
            });
            return;
        }
        super.updateSelectedPaymentline(...arguments);
    },

    async analyze_payment_methods() {
        const current_order = this.currentOrder;
        let total_in_bank = 0;
        let total_in_pay_later = 0;
        let has_cash = false;
        const total = current_order.get_total_with_tax();

        for (const payment_line of current_order.payment_ids) {
            if (payment_line.payment_method_id?.type === "bank") {
                total_in_bank = +Number(payment_line.amount);
            }
            if (
                payment_line.payment_method_id?.type === "pay_later" &&
                !payment_line.payment_method_id?.is_credit_note
            ) {
                total_in_pay_later = +Number(payment_line.amount);
            }
            if (payment_line.payment_method_id?.type === "cash") {
                has_cash = true;
            }
            if (
                payment_line.payment_method_id?.is_credit_note &&
                !current_order._isRefundAndSaleOrder()
            ) {
                if (!payment_line.credit_note_ncf) {
                    this.dialog.add(AlertDialog, {
                        title: _t("Error in credit note"),
                        body: _t(
                            "There is an error with the payment of credit note, please delete the payment of the credit note and enter it again."
                        ),
                    });
                    return false;
                }

                const credit_note = await this.pos.get_credit_note(payment_line.credit_note_ncf);

                if (credit_note.residual_amount <= 0) {
                    this.dialog.add(AlertDialog, {
                        title: _t("Error in credit note"),
                        body: _t(
                            "The credit note has no residual amount, please delete the payment of the credit note and enter it again."
                        ),
                    });
                    return false;
                }

                if (credit_note.residual_amount < payment_line.amount) {
                    this.dialog.add(AlertDialog, {
                        title: _t("Error in credit note"),
                        body: _t(
                            "The amount of the credit note is less than the amount entered, please delete the payment of the credit note and enter it again."
                        ),
                    });
                    return false;
                }
            }
        }

        if (
            Math.abs(Math.round(Math.abs(total) * 100) / 100) <
            Math.round(Math.abs(total_in_bank) * 100) / 100
        ) {
            this.dialog.add(AlertDialog, {
                title: _t("Card payment"),
                body: _t("Card payments cannot exceed the total order"),
            });
            return false;
        }

        if (
            Math.abs(Math.round(Math.abs(total) * 100) / 100) <
            Math.round(Math.abs(total_in_pay_later) * 100) / 100
        ) {
            this.dialog.add(AlertDialog, {
                title: _t("Pay later payment"),
                body: _t("Pay later payment cannot exceed the total order"),
            });
            return false;
        }

        if (
            Math.abs(Math.round(Math.abs(total) * 100) / 100) <
            Math.round(Math.abs(total_in_pay_later + total_in_bank) * 100) / 100
        ) {
            this.dialog.add(AlertDialog, {
                title: _t("Card and pay later payment"),
                body: _t("The sum for Card and Pay Later payment cannot exceed the total order."),
            });
            return false;
        }

        if (
            Math.round(Math.abs(total_in_bank) * 100) / 100 ===
                Math.round(Math.abs(total) * 100) / 100 &&
            has_cash
        ) {
            this.dialog.add(AlertDialog, {
                title: _t("Card and cash payment"),
                body: _t(
                    "The total payment with the card is sufficient to pay the order, please eliminate the payment in cash or reduce the amount to be paid by card"
                ),
            });
            return false;
        }

        if (
            Math.round(Math.abs(total_in_pay_later) * 100) / 100 ===
                Math.round(Math.abs(total) * 100) / 100 &&
            total_in_pay_later &&
            has_cash
        ) {
            this.dialog.add(AlertDialog, {
                title: _t("Pay later and cash payment"),
                body: _t(
                    "The total payment with the pay later is sufficient to pay the order, please eliminate the payment in cash or reduce the amount to be paid by pay later"
                ),
            });
            return false;
        }

        return true;
    },
});
