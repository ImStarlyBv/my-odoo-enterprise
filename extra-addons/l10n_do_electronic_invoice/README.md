# Electronic Invoicing DGII (DigiFact) - l10n_do_electronic_invoice

## Description

This Odoo module implements **Electronic Invoicing (e-CF)** for the **Dominican Republic**, generating the complete JSON payload required by the **DGII** (Dirección General de Impuestos Internos) and designed for integration with the **DigiFact** API.

It extends Odoo's accounting models to capture all fiscal fields required by Dominican Republic regulations, supporting all electronic document types (E31, E32, E33, E34, E41, E43, E44, E46, E47).

---

## Version

**18.0.1.0.0**

---

## Category

Accounting / Localizations

---

## Dependencies

- `l10n_do_accounting`

---

## Features

### 1. Complete JSON Payload Generation

Generates the full e-CF JSON structure required by DGII, including:

- **Header**: Document type, NCF, dates, payment types, totals
- **Seller (Emisor)**: Company data, trade name, economic activity, branch info, contacts, address
- **Buyer (Receptor)**: Partner data, VAT identification, address (handles final consumer cases)
- **Items**: Product codes, type, description, quantity, price, discounts, charges, taxes
- **Totals**: Taxable amounts, ITBIS (18%, 16%, 0%), ISR, exemptions, retention info, grand total
- **Payments**: Payment details with dates, types, and amounts
- **Additional Document Info**: Subtotals, reference information (varies by document type)

### 2. Supported Electronic Document Types

| Code | Type | Description |
|------|------|-------------|
| E31 | Electronic Invoice (Credit) | Standard B2B invoices |
| E32 | Electronic Invoice (Final Consumer) | B2C invoices |
| E33 | Electronic Debit Note | Debit notes |
| E34 | Electronic Credit Note | Credit notes |
| E41 | Electronic Invoice with Retentions | Invoices with ISR/ITBIS withholdings |
| E43 | Electronic Invoice for Special Operations | Special fiscal operations |
| E44 | Electronic Invoice for Small Taxpayers | Régimen especial taxpayers |
| E46 | Electronic Invoice for Government | Governmental entities |
| E47 | Electronic Invoice for Export | Export operations |

### 3. DGII Payment Types

Automatically computes payment type from reconciled payments:

| Code | Payment Method |
|------|----------------|
| 1 | Cash (Efectivo) |
| 2 | Bank Transfer / Check |
| 3 | Credit/Debit Card |
| 4 | Credit (Venta a Crédito) |
| 5 | Bonds / Certificates |
| 6 | Swap / Permuta |
| 7 | Credit Note (Nota de Crédito) |
| 8 | Mixed / Otros |

### 4. Dominican Republic Territorial Data

- **155 municipalities** loaded with official 6-digit DGII codes
- Automatic synchronization with Odoo's province/state records
- Municipality codes follow the pattern `PPMM00` (Province-Municipality)

### 5. JSON Preview Wizard

Preview the generated e-CF JSON payload before submission via a dedicated wizard accessible from invoice form view.

---

## Models

### Extended Models

#### `account.move` (Invoice)

New fields:
- `l10n_do_payment_type` - DGII payment type code (auto-computed)
- `l10n_do_seller_code` - Seller code for e-CF payload
- `l10n_do_purchase_order_number` - Internal purchase order number
- `l10n_do_sales_zone` - Sales zone (ZonaVenta)
- `l10n_do_sales_route` - Sales route (RutaVenta)
- `l10n_do_additional_seller_info` - Additional seller information
- `l10n_do_modification_reason` - Required for Credit/Debit Notes
- `l10n_do_indicador_monto_gravado` - Taxable amount indicator

Key methods:
- `_build_digifact_payload()` - Assembles the complete JSON payload
- `action_preview_digifact_json()` - Opens the JSON preview wizard
- `_digifact_get_header()` - Builds the Header block
- `_digifact_get_seller()` - Builds the Seller block
- `_digifact_get_buyer()` - Builds the Buyer block
- `_digifact_get_items()` - Builds the Items array
- `_digifact_get_totals()` - Builds the Totals block
- `_digifact_get_payments()` - Builds the Payments array
- `_digifact_get_tax_totals()` - Extracts tax totals (ITBIS, ISR, exemptions)

#### `product.template`

New fields:
- `l10n_do_product_type` - Product type (1=Good, 2=Service)
- `l10n_do_billing_indicator` - Billing indicator (1=Taxed ITBIS, 2=Other Exemptions, 3=Exempt Goods, 4=Exempt Services)

#### `res.company`

New fields:
- `is_live` - Environment toggle (test vs production)
- `l10n_do_enable_resend_button` - Enable "Reenviar a DGII" button
- `l10n_do_default_client` - Default client type (fiscal vs final)
- `l10n_do_municipality_id` - Company municipality (DGII code)
- `l10n_do_trade_name` - Commercial name (NombreComercial)
- `l10n_do_economic_activity` - Economic activity description
- `l10n_do_branch_code` - Branch code (default "0001")

#### `res.country.state`

New fields:
- `l10n_do_dgii_code` - 6-digit DGII province code

#### `l10n_do.municipality`

New model:
- `name` - Municipality name
- `code` - 6-digit DGII code
- `state_id` - Link to province

---

## Installation

1. Ensure `l10n_do_accounting` is installed
2. Place this module in your Odoo addons path
3. Update the app list in Odoo
4. Install "Electronic Invoicing DGII (DigiFact)"
5. Configure your company settings under the "DigiFact / e-CF" tab:
   - Set `is_live` to enable production mode
   - Configure trade name, economic activity, branch code, and municipality

---

## Configuration

### Company Settings

Navigate to **Settings > Companies** and configure the **DigiFact / e-CF** tab:

**Envío (Submission):**
- **Es Ambiente Real (is_live)**: Toggle between test and production endpoints
- **Habilitar Reenvío**: Enable the "Reenviar a DGII" button on invoices
- **Cliente por Defecto**: Default client type (fiscal or final consumer)

**Datos del Emisor (Emitter Data):**
- **Nombre Comercial**: Commercial name as reported to DGII
- **Actividad Económica**: Economic activity description
- **Código de Sucursal**: Branch code (default: "0001")
- **Municipio**: Municipality with DGII code

### Product Settings

On each product's **Invoicing** tab, configure:
- **Tipo de Producto (DGII)**: Good (1) or Service (2)
- **Indicador de Facturación**: Tax treatment for the product

---

## Usage

### Generating e-CF JSON

1. Create or open an invoice with a valid fiscal prefix (e-CF types: E31, E32, E33, etc.)
2. Fill in the required fields under the **Facturacion Electronica (DigiFact)** group in the "Other Info" tab
3. Click **"Ver JSON e-CF"** button in the header to preview the payload
4. Review the generated JSON in the wizard

### Item Code Assignment

Products are mapped to e-CF item codes using the following priority:
1. **EAN Barcode** (if available)
2. **Internal Reference** (default_code / PLU)
3. **SIN_CODIGO** (fallback if neither exists)

### Item Type Assignment

- Products with DGII type **47** (Special Operations) are always classified as **Service (2)**
- Otherwise, uses the product's `l10n_do_product_type` field
- Defaults to **Good (1)** if not specified

---

## Tax Mapping

The module maps Odoo taxes to DGII tax codes:

| DGII Code | Description |
|-----------|-------------|
| ITBIS1 | ITBIS at 18% |
| ITBIS2 | ITBIS at 16% |
| ITBIS3 | ITBIS at 0% |
| EXENTO | Tax exempt |

Line-level retentions (ITBIS, ISR) are also supported and included in the items array.

---

## File Structure

```
l10n_do_electronic_invoice/
├── __init__.py
├── __manifest__.py
├── data/
│   └── l10n_do.municipality.csv      # 155 municipalities with DGII codes
├── models/
│   ├── __init__.py
│   ├── account_move.py               # Core e-CF payload generation
│   ├── l10n_do_municipality.py       # Municipality model & sync
│   ├── product_template.py           # Product DGII fields
│   ├── res_company.py                # Company DigiFact config
│   └── res_country_state.py          # State DGII code extension
├── security/
│   └── ir.model.access.csv           # Wizard access rights
├── views/
│   ├── account_move_views.xml        # Invoice form extensions
│   ├── product_views.xml             # Product form extensions
│   └── res_company_views.xml         # Company form extensions
└── wizard/
    ├── __init__.py
    ├── digifact_preview_wizard.py    # JSON preview wizard
    └── digifact_preview_wizard_views.xml
```

---

## API Integration (Future)

The module is designed for integration with the DigiFact API endpoint:

```
POST /EcfController/GenerarComprobante
```

The `action_send_to_digifact()` method in the preview wizard is a placeholder for future API submission functionality.

---

## License

OPL-1 (Odoo Proprietary License v1)

---

## Author

**Omar Bautista**

---

## Support

For questions or issues related to this module, please contact the module author or your Odoo implementation partner.

---

## Notes

- This module is designed for **Odoo 18.0** with Dominican Republic accounting localization
- The `is_live` flag on the company determines whether invoices are sent to the production or test DigiFact endpoint
- Final consumer invoices (E32) automatically handle missing buyer VAT by using "NO_APLICA" placeholders
- Municipality codes are automatically synchronized with province records during installation
