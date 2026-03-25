import { registry } from "@web/core/registry";
import { CharField } from "@web/views/fields/char/char_field";
import { useEffect, useRef } from "@odoo/owl";

class FieldDgiiAutoComplete extends CharField {
    static template = "web.CharField";

    setup() {
        super.setup();
        this.input = useRef("input");
        useEffect(
            (inputEl) => {
                if (!inputEl) return;
                $(inputEl).autocomplete({
                    source: "/dgii_ws/",
                    minLength: 3,
                    select: function (event, ui) {
                        const $rnc = $("input[name$='vat']");
                        $(inputEl).val(ui.item.name);
                        $rnc.val(ui.item.rnc).trigger("change");
                        return false;
                    },
                });
                return () => {
                    if ($(inputEl).autocomplete("instance")) {
                        $(inputEl).autocomplete("destroy");
                    }
                };
            },
            () => [this.input.el]
        );
    }
}

registry.category("fields").add("dgii_autocomplete", {
    component: FieldDgiiAutoComplete,
    supportedTypes: ["char"],
});
