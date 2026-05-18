/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";

patch(PosStore.prototype, {
    /**
     * En modo Nota de Crédito (orden de devolución en POS fiscal),
     * arranca directamente en el PaymentScreen.
     */
    get firstScreen() {
        if (this.config?.l10n_do_is_fiscal && this.isCreditNoteMode()) {
            return "PaymentScreen";
        }
        return super.firstScreen;
    },
});
