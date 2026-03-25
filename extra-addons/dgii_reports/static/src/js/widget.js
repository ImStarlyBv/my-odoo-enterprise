import { registry } from "@web/core/registry";
import { UrlField } from "@web/views/fields/url/url_field";

class UrlDgiiReportsWidget extends UrlField {
    get formattedHref() {
        const value = this.props.record.data[this.props.name];
        return value ? `/dgii_reports/${value}` : "";
    }
}

registry.category("fields").add("dgii_reports_url", {
    component: UrlDgiiReportsWidget,
    supportedTypes: ["char"],
});
