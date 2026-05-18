/** @odoo-module */

import { Component } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { TextInputPopup } from "@point_of_sale/app/utils/input_popups/text_input_popup";
import { AlertDialog, ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";

/**
 * Valida que el NCF sea tipo B01 (11 chars) o E31 (13 chars).
 * Solo se permiten NCF de proveedor: Crédito Fiscal B01 y e-CF E31.
 */
function isValidVendorNcf(ncf) {
    if (!ncf) return false;
    const s = ncf.trim().toUpperCase();
    if (s.startsWith("B01") && s.length === 11 && /^\d+$/.test(s.slice(3))) return true;
    if (s.startsWith("E31") && s.length === 13 && /^\d+$/.test(s.slice(3))) return true;
    return false;
}

function isValidRnc(rnc) {
    const cleaned = (rnc || "").replace(/[-\s]/g, "");
    return cleaned.length === 9 && /^\d+$/.test(cleaned);
}

/**
 * Botón en PaymentScreen para registrar un NCF de proveedor desde el POS.
 * Solo visible cuando `pos.config.l10n_do_allow_vendor_ncf = True`.
 *
 * Flujo:
 *   1. Ingresar NCF (validación B01/E31)
 *   2. Ingresar RNC del proveedor (9 dígitos)
 *   3. Ingresar monto del comprobante
 *   4. Confirmación resumen
 *   5. RPC → crea factura borrador en Contabilidad
 *   6. Notificación de éxito con nombre de la factura creada
 */
export class VendorNcfButton extends Component {
    static template = "l10n_do_pos.VendorNcfButton";
    static props = {};

    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");
        this.notification = useService("notification");
    }

    async onClick() {
        const ncf = await this._promptNcf();
        if (!ncf) return;

        const rnc = await this._promptRnc();
        if (!rnc) return;

        const amount = await this._promptAmount();
        if (amount === null) return;

        // Confirmación antes de registrar
        const confirmed = await new Promise((resolve) => {
            this.dialog.add(ConfirmationDialog, {
                title: _t("Confirmar registro de NCF proveedor"),
                body: sprintf(
                    _t("NCF: %s\nRNC: %s\nMonto: RD$%s\n\n¿Registrar este comprobante?"),
                    ncf,
                    rnc,
                    amount.toFixed(2)
                ),
                confirmLabel: _t("Registrar"),
                cancelLabel: _t("Cancelar"),
                confirm: () => resolve(true),
                cancel: () => resolve(false),
            });
        });
        if (!confirmed) return;

        try {
            const result = await this.pos.data.call(
                "pos.order",
                "register_vendor_ncf",
                [this.pos.config.id, { ncf, vendor_rnc: rnc, amount }]
            );
            this.notification.add(
                sprintf(
                    _t("NCF registrado correctamente: %s — Factura borrador: %s (%s)"),
                    ncf,
                    result.move_name,
                    result.partner_name
                ),
                { type: "success", sticky: false }
            );
        } catch (error) {
            this.dialog.add(AlertDialog, {
                title: _t("Error al registrar NCF"),
                body: error.data?.message || error.message || _t("Error desconocido."),
            });
        }
    }

    /**
     * Solicita un NCF válido para proveedor (B01/E31). Reintenta si el formato
     * es incorrecto. Retorna null si el usuario cancela.
     */
    async _promptNcf() {
        while (true) {
            const ncf = await makeAwaitable(this.dialog, TextInputPopup, {
                startingValue: "",
                title: _t("NCF del proveedor"),
                placeholder: _t("B01XXXXXXXX o E31XXXXXXXXXX"),
            });
            if (ncf === null || ncf === undefined || ncf.trim() === "") return null;
            const normalized = ncf.trim().toUpperCase();
            if (isValidVendorNcf(normalized)) return normalized;
            this.dialog.add(AlertDialog, {
                title: _t("NCF inválido"),
                body: _t(
                    "Solo se aceptan NCF tipo B01 (11 caracteres) o E31 (13 caracteres).\n"
                    + "Ejemplo B01: B01XXXXXXXX   Ejemplo E31: E31XXXXXXXXXX"
                ),
            });
        }
    }

    /**
     * Solicita un RNC válido de 9 dígitos. Reintenta si el formato es incorrecto.
     * Retorna null si el usuario cancela.
     */
    async _promptRnc() {
        while (true) {
            const rnc = await makeAwaitable(this.dialog, TextInputPopup, {
                startingValue: "",
                title: _t("RNC del proveedor"),
                placeholder: _t("RNC (9 dígitos sin guiones)"),
            });
            if (rnc === null || rnc === undefined || rnc.trim() === "") return null;
            const cleaned = rnc.replace(/[-\s]/g, "");
            if (isValidRnc(cleaned)) return cleaned;
            this.dialog.add(AlertDialog, {
                title: _t("RNC inválido"),
                body: _t("El RNC debe tener exactamente 9 dígitos numéricos."),
            });
        }
    }

    /**
     * Solicita un monto positivo. Reintenta si el valor no es numérico o <= 0.
     * Retorna null si el usuario cancela.
     */
    async _promptAmount() {
        while (true) {
            const amountStr = await makeAwaitable(this.dialog, TextInputPopup, {
                startingValue: "",
                title: _t("Monto del comprobante"),
                placeholder: _t("Ej: 15000.00"),
            });
            if (amountStr === null || amountStr === undefined || amountStr.trim() === "") {
                return null;
            }
            const amount = parseFloat(amountStr.replace(",", "."));
            if (!Number.isNaN(amount) && amount > 0) return amount;
            this.dialog.add(AlertDialog, {
                title: _t("Monto inválido"),
                body: _t("El monto debe ser un número positivo mayor que cero."),
            });
        }
    }
}
