/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosPayment } from "@point_of_sale/app/models/pos_payment";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { Orderline } from "@point_of_sale/app/generic_components/orderline/orderline";
import { _t } from "@web/core/l10n/translation";

// ---------------------------------------------------------------------------
// PosStore
// ---------------------------------------------------------------------------
patch(PosStore.prototype, {
    async processServerData() {
        await super.processServerData(...arguments);
        this.document_types = this.models["l10n_latam.document.type"]?.getAll() || [];
    },

    /** @param {number|Object} id */
    get_doc_type_by_id(id) {
        const targetId = id && typeof id === "object" ? id.id : id;
        return (
            this.document_types.find((dt) => dt.id === targetId) ||
            this.get_doc_type_by_ncf_type("consumer")
        );
    },

    /** @param {string} prefix — e.g. "B02", "E32", "B04" */
    get_doc_type_by_prefix(prefix) {
        return this.document_types.find((dt) => dt.doc_code_prefix === prefix) || false;
    },

    /**
     * Finds the first document type matching an l10n_do_ncf_type.
     * @param {string} ncf_type — e.g. "consumer", "fiscal", "credit_note"
     */
    get_doc_type_by_ncf_type(ncf_type) {
        return this.document_types.find((dt) => dt.l10n_do_ncf_type === ncf_type) || false;
    },

    /**
     * Returns the default document type for the current order: the one
     * configured on the POS, else "consumer" (B02) as the safe default.
     */
    get_default_doc_type() {
        const configured = this.config.l10n_do_default_document_type_id;
        const configuredId =
            configured && typeof configured === "object" ? configured.id : configured;
        return (
            (configuredId && this.document_types.find((dt) => dt.id === configuredId)) ||
            this.get_doc_type_by_ncf_type("consumer") ||
            this.document_types[0] ||
            false
        );
    },

    isCreditNoteMode() {
        const order = this.get_order();
        return (
            this.config.l10n_do_is_fiscal &&
            order &&
            order._isRefundOrder()
        );
    },

    get_credit_note_payment_method() {
        return (
            this.models["pos.payment.method"].getAll().find((pm) => pm.is_credit_note) || false
        );
    },

    /** @param {string} ncf */
    async get_credit_note(ncf) {
        return this.data.call("pos.order", "get_credit_note", [false, ncf]);
    },

    /** @param {number} partner_id */
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
        // Char/Date fields default values (do not overwrite m2o
        // l10n_latam_document_type_id here — the related_models create()
        // already set it as a proper record reference; setting it directly
        // would replace the link with a raw number and break serialization).
        if (this.l10n_do_fiscal_number === undefined) {
            this.l10n_do_fiscal_number = vals.l10n_do_fiscal_number || "";
        }
        if (this.l10n_do_origin_ncf === undefined) {
            this.l10n_do_origin_ncf = vals.l10n_do_origin_ncf || "";
        }
        if (this.l10n_do_ncf_expiration_date === undefined) {
            this.l10n_do_ncf_expiration_date = vals.l10n_do_ncf_expiration_date || false;
        }
        this.document_type = false;
        // e-CF fields (populated after _finalize_fiscal_order if E3x)
        this.l10n_do_is_ecf = false;
        this.ecf_qr_image = "";
        this.ecf_codigo_seguridad = "";
        this.ecf_pending = false;
        this.ecf_error = "";

        if (this.config?.l10n_do_is_fiscal) {
            const savedDate = this.l10n_do_ncf_expiration_date;
            const existing = this.l10n_latam_document_type_id;
            if (existing) {
                this.set_document_type(this._get_doc_type_by_id(existing));
            } else {
                this.set_document_type(this._get_default_doc_type());
            }
            // Prefer the date stored on the order (e.g. from a confirmed invoice)
            // over the doc type default, so fiscal numbers already issued aren't affected.
            if (savedDate) {
                this.l10n_do_ncf_expiration_date = savedDate;
            }
        }
    },

    _get_document_types_all() {
        return this.models?.["l10n_latam.document.type"]?.getAll() || [];
    },

    _get_doc_type_by_ncf_type(ncf_type) {
        return (
            this._get_document_types_all().find(
                (dt) => dt.l10n_do_ncf_type === ncf_type
            ) || false
        );
    },

    _get_doc_type_by_id(id) {
        const targetId = id && typeof id === "object" ? id.id : id;
        return (
            this._get_document_types_all().find((dt) => dt.id === targetId) ||
            this._get_doc_type_by_ncf_type("consumer")
        );
    },

    _get_default_doc_type() {
        const configured = this.config?.l10n_do_default_document_type_id;
        const configuredId =
            configured && typeof configured === "object" ? configured.id : configured;
        return (
            (configuredId &&
                this._get_document_types_all().find((dt) => dt.id === configuredId)) ||
            this._get_doc_type_by_ncf_type("consumer") ||
            this._get_document_types_all()[0] ||
            false
        );
    },

    _get_default_consumer_partner() {
        const ref = this.config?.l10n_do_default_consumer_partner_id;
        if (!ref) return false;
        const partnerId = Array.isArray(ref) ? ref[0] : (typeof ref === "object" ? ref.id : ref);
        if (!partnerId) return false;
        return this.models?.["res.partner"]?.get(partnerId) || false;
    },

    /**
     * Sets the document type and applies its fiscal position to all lines.
     * @param {Object} doc_type — l10n_latam.document.type record from PosStore
     */
    set_document_type(doc_type) {
        this.document_type = doc_type;
        // Use update() so the many2one relation is properly linked; setting
        // the id directly would store a number and serialize as false.
        this.update({ l10n_latam_document_type_id: doc_type || false });
        this.l10n_do_ncf_expiration_date = doc_type?.l10n_do_ncf_expiration_date || false;

        if (doc_type?.fiscal_position_id) {
            const fpId =
                typeof doc_type.fiscal_position_id === "object"
                    ? doc_type.fiscal_position_id.id
                    : doc_type.fiscal_position_id;
            const fp = this.models?.["account.fiscal.position"]?.find((p) => p.id === fpId);
            if (fp) {
                this.update({ fiscal_position_id: fp });
                for (const line of this.get_orderlines()) {
                    line.set_quantity(line.quantity);
                }
            }
        }

    },

    /**
     * If the current doc type is consumer/e-consumer and the order has no
     * partner, assigns the POS default consumer partner.
     * Called from the UI (button handler) only — NOT during initial setup,
     * since set_partner triggers pricelist/fiscal-position updates that
     * can crash before the order is fully loaded.
     */
    apply_default_consumer_partner_if_needed() {
        if (!this.config?.l10n_do_is_fiscal) return;
        const doc_type = this.document_type;
        const ncfType = doc_type?.l10n_do_ncf_type;
        if (ncfType !== "consumer" && ncfType !== "e-consumer") return;
        if (doc_type?.is_vat_required) return;
        if (this.get_partner()) return;
        const defaultPartner = this._get_default_consumer_partner();
        if (!defaultPartner) return;
        this._setting_default_consumer = true;
        try {
            this.set_partner(defaultPartner);
        } finally {
            this._setting_default_consumer = false;
        }
    },

    get_document_type() {
        if (!this.document_type && this.config?.l10n_do_is_fiscal) {
            if (this.l10n_latam_document_type_id) {
                this.document_type = this._get_doc_type_by_id(this.l10n_latam_document_type_id);
            } else {
                this.document_type = this._get_default_doc_type();
            }
        }
        return this.document_type;
    },

    /**
     * When the partner changes, auto-select the document type based on
     * l10n_do_dgii_tax_payer_type.
     *
     * Mapping:
     *   taxpayer      → fiscal   (B01 / E31)
     *   special       → special  (B14 / E44)
     *   governmental  → governmental (B15 / E45)
     *   anything else → POS default document type (B02 / E32)
     *
     * With `l10n_do_prefer_ecf` the electronic type (E31/E44/E45) is used
     * when the journal has it; otherwise the traditional B-type.
     */
    set_partner(partner) {
        super.set_partner(partner);
        if (!this.config?.l10n_do_is_fiscal) return;
        // Avoid infinite recursion when set_document_type assigns the default consumer.
        if (this._setting_default_consumer) return;

        const payerTypeToNcfType = {
            taxpayer: "fiscal",
            special: "special",
            governmental: "governmental",
        };
        const ncfType = payerTypeToNcfType[partner?.l10n_do_dgii_tax_payer_type];
        if (!ncfType) {
            // Consumidor final o sin cliente: comprobante por defecto de la caja.
            this.set_document_type(this._get_default_doc_type());
            return;
        }
        const ecfType =
            this.config.l10n_do_prefer_ecf && this._get_doc_type_by_ncf_type(`e-${ncfType}`);
        this.set_document_type(
            ecfType || this._get_doc_type_by_ncf_type(ncfType) || this._get_default_doc_type()
        );
    },

    /**
     * Stores fiscal data received from backend after _finalize_fiscal_order().
     * Also stores e-CF fields (is_ecf, ecf_qr_image, ecf_codigo_seguridad, ecf_pending).
     * @param {Object} data — result of pos.order._finalize_fiscal_order()
     */
    set_l10n_do_fiscal_data(data) {
        this.l10n_do_fiscal_number = data.l10n_do_fiscal_number || "";
        this.l10n_do_ncf_expiration_date = data.l10n_do_ncf_expiration_date || false;
        if (data.l10n_latam_document_type_id) {
            const dt = this._get_doc_type_by_id(data.l10n_latam_document_type_id);
            if (dt) this.set_document_type(dt);
        }
        // e-CF
        this.l10n_do_is_ecf = data.is_ecf || false;
        this.ecf_qr_image = data.ecf_qr_image || "";
        this.ecf_codigo_seguridad = data.ecf_codigo_seguridad || "";
        this.ecf_pending = data.ecf_pending || false;
        this.ecf_error = data.ecf_error || "";
    },

    /**
     * Updates e-CF QR/security data after polling. Called from PaymentScreen
     * when poll_ecf_status() returns ready=true.
     * @param {string} ecf_qr_image — base64 PNG
     * @param {string} ecf_codigo_seguridad — DGII security code
     */
    set_ecf_data(ecf_qr_image, ecf_codigo_seguridad) {
        this.ecf_qr_image = ecf_qr_image || "";
        this.ecf_codigo_seguridad = ecf_codigo_seguridad || "";
        this.ecf_pending = false;
    },

    /**
     * Sets the origin NCF from the original order (used for B04/E34).
     * @param {Object} origin_order — pos.order with l10n_do_fiscal_number
     */
    set_origin_ncf(origin_order) {
        this.l10n_do_origin_ncf = origin_order.l10n_do_fiscal_number || "";
    },

    /**
     * Agrega los totales fiscales DGII para el pie del recibo:
     * subtotal sin impuestos, ITBIS agrupado por tasa, y total.
     *
     * Los montos se pre-formatean con la moneda de la orden para que
     * el template XML sólo use t-esc sin lógica de formato.
     *
     * @returns {Object} { subtotal, itbis_groups, total }
     *   itbis_groups: [{ label, amount }] ordenado de mayor a menor tasa
     */
    get_l10n_do_fiscal_totals() {
        const fmt = (v) => {
            const sym = this.currency?.symbol || "";
            return `${sym} ${Number(v).toFixed(2)}`;
        };

        let subtotal_raw = 0;
        const itbis_by_rate = {};

        for (const line of this.get_orderlines()) {
            const prices = line.get_all_prices?.();
            if (!prices) continue;

            subtotal_raw += prices.priceWithoutTax || 0;

            for (const taxData of prices.taxesData || []) {
                if (taxData.tax?.tax_group_id?.name !== "ITBIS") continue;
                const rate = taxData.tax.amount ?? 0;
                if (!itbis_by_rate[rate]) {
                    itbis_by_rate[rate] = { rate, amount: 0 };
                }
                itbis_by_rate[rate].amount += taxData.tax_amount_currency || 0;
            }
        }

        const itbis_groups = Object.values(itbis_by_rate)
            .sort((a, b) => b.rate - a.rate)
            .map((g) => ({
                label: `ITBIS ${g.rate}%`,
                amount: fmt(g.amount),
            }));

        return {
            subtotal: fmt(subtotal_raw),
            itbis_groups,
            total: fmt(this.get_total_with_tax()),
        };
    },

    export_for_printing(baseUrl, headerData) {
        const result = super.export_for_printing(baseUrl, headerData);
        result.l10n_do_is_fiscal = !!this.config?.l10n_do_is_fiscal;
        if (this.config?.l10n_do_is_fiscal) {
            result.l10n_do_fiscal_number = this.l10n_do_fiscal_number;
            result.l10n_do_origin_ncf = this.l10n_do_origin_ncf;
            result.l10n_do_ncf_expiration_date = this.l10n_do_ncf_expiration_date;
            result.document_type = this.document_type;
            result.partner = this.get_partner();
            result.l10n_do_fiscal_totals = this.get_l10n_do_fiscal_totals();
            // e-CF
            result.is_ecf = this.l10n_do_is_ecf;
            result.ecf_qr_image = this.ecf_qr_image;
            result.ecf_codigo_seguridad = this.ecf_codigo_seguridad;
        }
        return result;
    },

    // Compatibility alias used internally
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

    /**
     * @param {string} ncf — NCF of the credit note used as payment
     * @param {number} partner_id — ID of the credit note's partner
     */
    set_credit_note_data(ncf, partner_id) {
        this.credit_note_ncf = ncf;
        this.credit_note_partner_id = partner_id;
    },
});

// ---------------------------------------------------------------------------
// PosOrderline — ITBIS breakdown for fiscal receipts
// ---------------------------------------------------------------------------

// Register l10n_do_itbis prop so Owl validation passes
Orderline.props.line.shape.l10n_do_itbis = { type: Number, optional: true };

patch(PosOrderline.prototype, {
    getDisplayData() {
        const result = super.getDisplayData(...arguments);
        result.l10n_do_itbis = this.get_itbis();
        return result;
    },

    /**
     * Sums ITBIS tax amounts from taxesData for this line.
     * Uses the tax group name "ITBIS" to identify applicable taxes.
     */
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
