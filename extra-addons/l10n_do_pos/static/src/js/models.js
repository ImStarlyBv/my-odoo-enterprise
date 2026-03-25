/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosPayment } from "@point_of_sale/app/models/pos_payment";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";

// ---------------------------------------------------------------------------
// PosStore
// ---------------------------------------------------------------------------
patch(PosStore.prototype, {
    async processServerData() {
        await super.processServerData(...arguments);
        this.fiscal_types = this.models["account.fiscal.type"]?.getAll() || [];
    },

    get_fiscal_type_by_id(id) {
        const targetId = id && typeof id === "object" ? id.id : id;
        return (
            this.fiscal_types.find((ft) => ft.id === targetId) ||
            this.get_fiscal_type_by_prefix("B02")
        );
    },

    get_fiscal_type_by_prefix(prefix) {
        const result = this.fiscal_types.find((ft) => ft.prefix === prefix);
        if (!result) {
            this.dialog.add(AlertDialog, {
                title: _t("Fiscal type not found"),
                body: sprintf(_t("This fiscal type does not exist. (%s)"), prefix),
            });
            return false;
        }
        return result;
    },

    async get_fiscal_data(order) {
        return this.data.call("pos.order", "get_next_fiscal_sequence", [
            false,
            order.fiscal_type?.id,
            this.company.id,
            [],
            order.export_as_JSON ? order.export_as_JSON() : {},
        ]);
    },

    isCreditNoteMode() {
        const current_order = this.get_order();
        return (
            this.config.l10n_do_fiscal_journal &&
            current_order &&
            current_order._isRefundAndSaleOrder()
        );
    },

    get_credit_note_payment_method() {
        return (
            this.models["pos.payment.method"].getAll().find((pm) => pm.is_credit_note) || false
        );
    },

    async get_credit_note(ncf) {
        return this.data.call("pos.order", "get_credit_note", [false, ncf]);
    },

    async get_credit_notes(partner_id) {
        return this.data.call("pos.order", "get_credit_notes", [false, partner_id]);
    },
});

// ---------------------------------------------------------------------------
// PosOrder
// ---------------------------------------------------------------------------
patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(vals);
        this.ncf = vals.ncf || "";
        this.ncf_origin_out = vals.ncf_origin_out || "";
        this.ncf_expiration_date = vals.ncf_expiration_date || "";
        this.fiscal_type_id = vals.fiscal_type_id || false;
        this.fiscal_sequence_id = vals.fiscal_sequence_id || false;
        this.fiscal_type = false;

        if (this.config?.l10n_do_fiscal_journal) {
            const partner = this.get_partner();
            if (partner?.sale_fiscal_type_id) {
                this.set_fiscal_type(
                    this.pos.get_fiscal_type_by_id(partner.sale_fiscal_type_id)
                );
            } else {
                this.set_fiscal_type(this.pos.get_fiscal_type_by_prefix("B02"));
            }
        }
    },

    set_fiscal_type(fiscal_type) {
        this.fiscal_type = fiscal_type;
        this.fiscal_type_id = fiscal_type?.id || false;

        if (fiscal_type?.fiscal_position_id) {
            const fpId =
                typeof fiscal_type.fiscal_position_id === "object"
                    ? fiscal_type.fiscal_position_id.id
                    : Array.isArray(fiscal_type.fiscal_position_id)
                    ? fiscal_type.fiscal_position_id[0]
                    : fiscal_type.fiscal_position_id;
            const fp = this.models?.["account.fiscal.position"]?.find((p) => p.id === fpId);
            if (fp) {
                this.update({ fiscal_position_id: fp });
                for (const line of this.get_orderlines()) {
                    line.set_quantity(line.quantity);
                }
            }
        }
    },

    get_fiscal_type() {
        return this.fiscal_type;
    },

    set_partner(partner) {
        super.set_partner(partner);
        if (this.config?.l10n_do_fiscal_journal) {
            if (partner?.sale_fiscal_type_id) {
                this.set_fiscal_type(
                    this.pos.get_fiscal_type_by_id(partner.sale_fiscal_type_id)
                );
            } else {
                this.set_fiscal_type(this.pos.get_fiscal_type_by_prefix("B02"));
            }
        }
    },

    export_for_printing(baseUrl, headerData) {
        const result = super.export_for_printing(baseUrl, headerData);
        result.l10n_do_fiscal_journal = this.config?.l10n_do_fiscal_journal;
        if (this.config?.l10n_do_fiscal_journal) {
            result.ncf = this.ncf;
            result.ncf_origin_out = this.ncf_origin_out;
            result.ncf_expiration_date = this.ncf_expiration_date || "";
            result.fiscal_type = this.fiscal_type;
            result.partner = this.get_partner();
        }
        return result;
    },

    set_ncf_origin_out(origin_order) {
        this.ncf_origin_out = origin_order.ncf;
    },

    set_l10n_do_fiscal_data(fiscal_data) {
        this.ncf = fiscal_data.ncf;
        this.ncf_expiration_date = fiscal_data.ncf_expiration_date;
        this.fiscal_sequence_id = fiscal_data.fiscal_sequence_id;
    },

    // Alias for Odoo 18 — in Odoo 16 this was _isRefundAndSaleOrder()
    _isRefundAndSaleOrder() {
        return this._isRefundOrder();
    },
});

// ---------------------------------------------------------------------------
// PosPayment
// ---------------------------------------------------------------------------
patch(PosPayment.prototype, {
    setup(vals) {
        super.setup(vals);
        this.credit_note_ncf = vals.credit_note_ncf || "";
        this.credit_note_partner_id = vals.credit_note_partner_id || false;
    },

    set_fiscal_data(ncf, partner_id) {
        this.credit_note_ncf = ncf;
        this.credit_note_partner_id = partner_id;
    },
});

// ---------------------------------------------------------------------------
// PosOrderline
// ---------------------------------------------------------------------------
patch(PosOrderline.prototype, {
    getDisplayData() {
        const result = super.getDisplayData(...arguments);
        result.l10n_do_itbis = this.get_itbis();
        return result;
    },

    get_itbis() {
        let itbis = 0;
        const prices = this.get_all_prices?.();
        if (prices?.taxesData) {
            for (const taxData of prices.taxesData) {
                if (taxData.tax?.tax_group_id?.name === "ITBIS") {
                    itbis += taxData.tax_amount_currency || 0;
                }
            }
        }
        return itbis;
    },
});
