/** @odoo-module */

import { Component } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { SelectionPopup } from "@point_of_sale/app/utils/input_popups/selection_popup";
import { TextInputPopup } from "@point_of_sale/app/utils/input_popups/text_input_popup";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";
import { _t } from "@web/core/l10n/translation";

export class SetFiscalTypeButton extends Component {
    static template = "l10n_do_pos.SetFiscalTypeButton";
    static props = {};

    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");
    }

    get currentOrder() {
        return this.pos.get_order();
    }

    get currentFiscalTypeName() {
        return this.currentOrder && this.currentOrder.fiscal_type
            ? this.currentOrder.fiscal_type.name
            : _t("Select Fiscal Type");
    }

    async onClick() {
        const currentFiscalType = this.currentOrder.fiscal_type;
        const fiscalPosList = [];

        for (const fiscalPos of this.pos.fiscal_types) {
            if (fiscalPos.type !== "out_invoice") continue;
            fiscalPosList.push({
                id: fiscalPos.id,
                label: fiscalPos.name,
                isSelected: currentFiscalType ? fiscalPos.id === currentFiscalType.id : false,
                item: fiscalPos,
            });
        }

        const selectedFiscalType = await makeAwaitable(this.dialog, SelectionPopup, {
            title: _t("Select Fiscal Type"),
            list: fiscalPosList,
        });

        if (selectedFiscalType) {
            const partner = this.currentOrder.get_partner();
            if (selectedFiscalType.requires_document && (!partner || !partner.vat)) {
                await this.open_vat_popup();
            }
            this.currentOrder.set_fiscal_type(selectedFiscalType);
        }
    }

    async open_vat_popup() {
        const vat = await makeAwaitable(this.dialog, TextInputPopup, {
            startingValue: "",
            title: _t(
                "You need to select a customer with RNC or Cedula for this fiscal type."
            ),
            placeholder: _t("RNC or Cedula"),
        });

        if (!vat) return;

        if (!(vat.length === 9 || vat.length === 11) || Number.isNaN(Number(vat))) {
            this.dialog.add(AlertDialog, {
                title: _t("This is not a valid RNC or Cedula"),
                body: _t(
                    "Please ensure the RNC has exactly 9 digits or the Cedula has 11 digits"
                ),
            });
            await this.open_vat_popup();
            return;
        }

        const partner = this.pos.models["res.partner"]
            .getAll()
            .find((p) => p.vat === vat);

        if (partner) {
            this.currentOrder.set_partner(partner);
        } else {
            const newPartner = await makeAwaitable(this.dialog, PartnerList, {
                partner: this.currentOrder.get_partner(),
            });
            if (newPartner) {
                this.currentOrder.set_partner(newPartner);
                this.currentOrder.updatePricelist(newPartner);
            }
        }
    }
}
