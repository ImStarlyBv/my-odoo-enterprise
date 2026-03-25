/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";

patch(PosStore.prototype, {
    get firstScreen() {
        if (this.config?.l10n_do_fiscal_journal && this.isCreditNoteMode()) {
            return "PaymentScreen";
        }
        return super.firstScreen;
    },
});
