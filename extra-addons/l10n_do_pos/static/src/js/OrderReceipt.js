/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";

patch(OrderReceipt.prototype, {
    doesAnyOrderlineHaveTaxLabel() {
        if (this.props.data?.l10n_do_fiscal_journal) {
            return true;
        }
        return super.doesAnyOrderlineHaveTaxLabel(...arguments);
    },
});
