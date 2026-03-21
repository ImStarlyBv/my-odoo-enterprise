/** @odoo-module **/

import { Component, useState, useExternalListener } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

export class HomeMenu extends Component {
    static template = "web_enterprise.HomeMenu";
    static props = {
        hasBackgroundAction: { type: Boolean },
    };

    setup() {
        this.menuService = useService("menu");
        this.state = useState({ inputValue: "" });
        useExternalListener(window, "keydown", this._onKeydown);
    }

    get apps() {
        const search = this.state.inputValue.trim().toLowerCase();
        return this.menuService.getApps().filter((app) => {
            if (!search) return true;
            return app.label.toLowerCase().includes(search);
        });
    }

    openApp(app) {
        this.menuService.selectMenu(app);
        this.env.bus.trigger("HOME-MENU:TOGGLED");
    }

    _onKeydown(ev) {
        if (ev.key === "Escape") {
            this.state.inputValue = "";
        }
    }
}

registry.category("home_menu").add("web_enterprise.HomeMenu", HomeMenu);
