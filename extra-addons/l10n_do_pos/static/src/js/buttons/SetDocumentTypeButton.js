/** @odoo-module */

import { Component } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { SelectionPopup } from "@point_of_sale/app/utils/input_popups/selection_popup";
import { TextInputPopup } from "@point_of_sale/app/utils/input_popups/text_input_popup";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

/**
 * Botón en PaymentScreen que permite al cajero seleccionar el tipo de
 * comprobante fiscal (B01, B02, B14, B15, etc.) para la orden actual.
 *
 * Si el tipo seleccionado requiere RNC/Cédula (is_vat_required) y el cliente
 * no tiene uno, abre un popup para buscarlo o ingresarlo manualmente.
 */
export class SetDocumentTypeButton extends Component {
    static template = "l10n_do_pos.SetDocumentTypeButton";
    static props = {};

    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");
    }

    get currentOrder() {
        return this.pos.get_order();
    }

    get currentDocTypeName() {
        return this.currentOrder?.document_type?.name || _t("Seleccionar Comprobante");
    }

    /**
     * True si el tipo de comprobante seleccionado es electrónico (prefijo E3x).
     * Se usa para mostrar el badge "e-CF" en el botón.
     */
    get isEcfType() {
        const prefix = this.currentOrder?.document_type?.doc_code_prefix || "";
        return prefix.startsWith("E");
    }

    /** True si hay un tipo de comprobante seleccionado. */
    get hasDocType() {
        return !!this.currentOrder?.document_type;
    }

    async onClick() {
        const current = this.currentOrder?.document_type;

        const list = this.pos.document_types
            .filter((dt) => dt.internal_type === "invoice")
            .map((dt) => ({
                id: dt.id,
                label: dt.name,
                isSelected: current ? dt.id === current.id : false,
                item: dt,
            }));

        const selected = await makeAwaitable(this.dialog, SelectionPopup, {
            title: _t("Tipo de comprobante"),
            list,
        });

        if (!selected) return;

        const partner = this.currentOrder.get_partner();
        if (selected.is_vat_required && (!partner || !partner.vat)) {
            const found = await this._resolvePartnerWithVat(partner);
            if (!found) return;
        }

        this.currentOrder.set_document_type(selected);
    }

    /**
     * Intenta resolver un partner con RNC/Cédula válido.
     * Primero muestra un popup para ingresar el número; luego busca en la
     * BD local. Si no existe, abre PartnerList para seleccionar/crear uno.
     *
     * @returns {boolean} true si se encontró/asignó partner, false si canceló
     */
    async _resolvePartnerWithVat(currentPartner) {
        const vat = await makeAwaitable(this.dialog, TextInputPopup, {
            startingValue: currentPartner?.vat || "",
            title: _t("El tipo seleccionado requiere RNC o Cédula del cliente"),
            placeholder: _t("RNC (9 dígitos) o Cédula (11 dígitos)"),
        });

        if (!vat) return false;

        const cleaned = vat.replace(/[-\s]/g, "");
        if (
            (cleaned.length !== 9 && cleaned.length !== 11) ||
            Number.isNaN(Number(cleaned))
        ) {
            this.dialog.add(AlertDialog, {
                title: _t("RNC / Cédula inválido"),
                body: _t(
                    "El RNC debe tener 9 dígitos y la Cédula 11, sin guiones ni espacios."
                ),
            });
            return this._resolvePartnerWithVat(currentPartner);
        }

        const partner = this.pos.models["res.partner"]
            .getAll()
            .find((p) => p.vat === cleaned);

        if (partner) {
            this.currentOrder.set_partner(partner);
            return true;
        }

        // Partner no encontrado localmente — abrir pantalla de partner
        const newPartner = await this.pos.editPartner();
        if (newPartner) {
            this.currentOrder.set_partner(newPartner);
            return true;
        }

        return false;
    }
}
