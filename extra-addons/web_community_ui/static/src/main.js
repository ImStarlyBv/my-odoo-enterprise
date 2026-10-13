/** @odoo-module **/

import { startWebClient } from "@web/start";
import { WebClientUI } from "./webclient/webclient";

/**
 * This file starts the web client. In the manifest, it replaces the community
 * main.js to load a different webclient class (WebClientUI instead of
 * WebClient).
 */
startWebClient(WebClientUI);
