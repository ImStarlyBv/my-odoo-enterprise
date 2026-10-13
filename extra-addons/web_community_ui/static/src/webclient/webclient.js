/** @odoo-module **/

import { WebClient } from "@web/webclient/webclient";
import { useService } from "@web/core/utils/hooks";
import { NavBarUI } from "./navbar/navbar";

export class WebClientUI extends WebClient {
    static components = {
        ...WebClient.components,
        NavBar: NavBarUI,
    };
    setup() {
        super.setup();
        this.hm = useService("home_menu");
    }
    _loadDefaultApp() {
        return this.hm.toggle(true);
    }
}
