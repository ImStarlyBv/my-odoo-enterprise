# l10n_do_electronic_invoice

Módulo Odoo 18 para la generación del payload JSON de **Comprobantes Fiscales Electrónicos (e-CF)** de la DGII — República Dominicana.

---

## Descripción

Este módulo extiende `account.move` para construir el JSON que requiere la API del proveedor de e-CF habilitado por la DGII. Todos los datos se leen directamente de Odoo sin recalcular impuestos ni totales: los importes se obtienen de los campos ya calculados por el motor contable (`price_subtotal`, `amount_untaxed`, `amount_total`, líneas de asiento con `display_type='tax'`).

### Tipos de documento soportados

| Código | Descripción |
|--------|-------------|
| E31    | Factura de Crédito Fiscal Electrónica |
| E32    | Factura de Consumidor Final Electrónica |
| E33    | Nota de Débito Electrónica |
| E34    | Nota de Crédito Electrónica |
| E41    | Compras / Gastos con retención |
| E43    | Regímenes Especiales de Tributación |
| E44    | Gubernamental Electrónica |
| E45    | Comprobante de Exportación Electrónico |
| E46    | Comprobante para Pagos al Exterior |
| E47    | Comprobante para Pagos de Servicios Electrónico |

---

## Dependencias

- `l10n_do_accounting` — provee los campos `is_ecf_invoice`, `l10n_do_fiscal_number`, `l10n_do_ncf_expiration_date`, `l10n_do_income_type`, `l10n_do_ecf_modification_code`, y la lógica de secuencias NCF.

---

## Arquitectura

```
l10n_do_electronic_invoice/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── account_move.py         ← núcleo: genera el payload JSON
│   ├── res_company.py          ← campos is_live, nombre comercial, actividad económica
│   ├── res_partner.py          ← campo l10n_do_municipality_id + sync con ciudad
│   ├── res_country_state.py    ← campo l10n_do_dgii_code (código DGII de provincia)
│   ├── l10n_do_municipality.py ← modelo l10n_do.municipality
│   └── product_template.py     ← l10n_do_product_type, l10n_do_billing_indicator
├── wizard/
│   ├── ecf_preview_wizard.py   ← wizard de previsualización
│   └── ecf_preview_wizard_views.xml
├── views/
│   ├── account_move_views.xml  ← botón "Ver JSON e-CF" + campos en Otra Info
│   ├── res_company_views.xml   ← pestaña "Facturación Electrónica (e-CF)"
│   └── res_partner_views.xml   ← campo municipio en formulario de contacto
├── security/
│   └── ir.model.access.csv
├── data/
│   └── l10n_do.municipality.csv
└── tests/
    └── test_ecf_json.py
```

---

## Flujo de datos

```
account.move (publicada)
    │
    ▼
_build_ecf_payload()
    ├── _ecf_get_doc_type()            → código numérico ('31', '32', …)
    ├── _ecf_get_tax_totals()          → impuestos/retenciones desde asiento
    │       ├── line_ids (tax lines)   → importes reales sin recalcular
    │       └── invoice_line_ids       → bases por línea (price_subtotal)
    ├── _ecf_get_header()              → Header + AdditionalIssueDocInfo
    ├── _ecf_get_seller()              → Seller + BranchInfo
    ├── _ecf_get_buyer()               → Buyer (RNC / NO_APLICA)
    ├── _ecf_get_items()               → Items[] con Codes, Discounts, Totals
    ├── _ecf_get_totals()              → Totals con TotalTaxes + GrandTotal
    ├── _ecf_get_payments()            → Payments[]
    └── _ecf_get_additional_doc_info() → AdditionalDocumentInfo
            ├── SUBTOTALES (siempre, excepto E46)
            └── INFORMACION_REFERENCIA (solo E33 y E34)
```

---

## Mapeo de campos

### Nivel de documento

| Campo JSON | Campo Odoo | Notas |
|---|---|---|
| `TaxId` | `company_id.vat` | RNC del emisor |
| `Header.DocType` | `l10n_latam_document_type_id.doc_code_prefix` sin `'E'` | `'31'`, `'32'`, … |
| `Header.IssuedDateTime` | `invoice_date` | ISO 8601 |
| `Totals.TotalTaxableAmount` | `amount_untaxed` | Base imponible total |
| `Totals.GrandTotal.InvoiceTotal` | `amount_total` | Total con impuestos |
| `Seller.TaxID` | `company_id.vat` | |
| `Buyer.TaxID` | `partner_id.vat` o `'NO_APLICA'` | Consumidor final / E43 / E47 |

### Nivel de línea

| Campo JSON | Campo Odoo | Descripción |
|---|---|---|
| `Items[].Price` | `line.price_subtotal / line.quantity` | Precio unitario sin impuesto |
| `Items[].Totals.TotalItem` | `line.price_subtotal` | Total sin impuesto |
| `Items[].Discounts` | `line.discount`, `line.price_unit` | Solo si `discount > 0` |
| `MontoISRRetenido` | `abs(tax.amount/100) × price_subtotal` | Sin `compute_all` |
| `MontoITBISRetenido` | ídem para ITBIS con `amount < 0` | Solo E41 |

---

## Impuestos (TotalTaxes)

Los grupos de impuesto se construyen leyendo las líneas `display_type='tax'` del asiento ya publicado. La identificación del tipo se hace por nombre del impuesto:

| Condición | Clasificación |
|---|---|
| Nombre contiene `ITBIS` y `amount > 0` | ITBIS positivo (ITBIS1/2/3/4) |
| Nombre contiene `ITBIS` y `amount < 0` | ITBIS retenido (E41) |
| Nombre contiene `ISR`, `RENTA` o `RETENCION` y `amount < 0` | ISR retenido (E41) |
| Línea sin ITBIS positivo | Exento |

Mapa de tasas → códigos DGII:

| Tasa | Código |
|---|---|
| 18% | `ITBIS1` |
| 16% | `ITBIS2` |
| 9%  | `ITBIS3` |
| 8%  | `ITBIS4` |
| 0%  | `EXENTO` |

---

## Campos agregados en `account.move`

| Campo | Tipo | Descripción |
|---|---|---|
| `ecf_validation_status` | Selection | Pendiente / Validado / Error |
| `ecf_api_message` | Text | Respuesta del API |
| `ecf_qr_code` | Text | Código QR retornado por la DGII |
| `l10n_do_currency_rate` | Float(12,4) | Tasa DOP al momento de emitir |
| `show_exchange_rate` | Boolean | True si moneda ≠ DOP (computed) |
| `l10n_do_payment_type` | Selection | Tipo de pago DGII (1–8) |
| `l10n_do_seller_code` | Char | `CodigoVendedor` |
| `l10n_do_purchase_order_number` | Char | `NumeroPedidoInterno` |
| `l10n_do_sales_zone` | Char | `ZonaVenta` |
| `l10n_do_sales_route` | Char | `RutaVenta` |
| `l10n_do_additional_seller_info` | Char | `InformacionAdicionalEmisor` |
| `l10n_do_modification_reason` | Char | Razón de modificación (E33/E34) |
| `l10n_do_indicador_monto_gravado` | Selection | `IndicadorMontoGravado` (0/1) |

---

## Campos en `res.company`

| Campo | Descripción |
|---|---|
| `is_live` | `True` → producción DGII; `False` → ambiente de pruebas |
| `l10n_do_trade_name` | `NombreComercial` para el e-CF |
| `l10n_do_economic_activity` | `ActividadEconomica` para el e-CF |
| `l10n_do_branch_code` | Código de sucursal (`BranchInfo.Name`), default `'0001'` |
| `l10n_do_municipality_id` | Municipio DGII de la empresa (para `District` en Seller) |
| `l10n_do_default_client` | Tipo de cliente para cédulas de 11 dígitos |

---

## Campos en `product.template`

| Campo | Descripción |
|---|---|
| `l10n_do_product_type` | `'1'` Bien / `'2'` Servicio — sobreescribe la inferencia automática |
| `l10n_do_billing_indicator` | `'1'`–`'4'` — sobreescribe el `IndicadorFacturacion` por línea |

---

## Configuración

### 1. Empresa emisora

En **Configuración → Empresa → Facturación Electrónica (e-CF)**:

- Activar **Modo Producción** cuando se opere en producción DGII.
- Completar **Nombre Comercial**, **Actividad Económica** y **Código Sucursal**.
- Configurar **RNC** (`vat`), dirección, provincia y municipio.

### 2. Tipos de documento

`l10n_do_accounting` instala los tipos (E31–E47) con sus secuencias NCF. Los diarios de venta deben tener asignado el tipo de documento correcto.

### 3. Impuestos

| Tipo | Configuración en Odoo |
|---|---|
| ITBIS 18% | `amount = 18`, nombre contiene `ITBIS` |
| ITBIS Exento | `amount = 0`, nombre contiene `ITBIS` |
| ISR Retenido 2% | `amount = -2`, nombre contiene `ISR` o `RETENCION` |
| ITBIS Retenido | `amount < 0`, nombre contiene `ITBIS` |

### 4. Municipios

El CSV `data/l10n_do.municipality.csv` carga los municipios. La acción de servidor **Sincronizar Municipios DGII** (lista de contactos) enlaza automáticamente el campo `city` con el municipio correspondiente para contactos de RD.

---

## Uso

En cualquier factura publicada de tipo e-CF aparece el botón **Ver JSON e-CF** en la cabecera. Al hacer clic se abre el wizard con el JSON listo para inspeccionar.

El método principal es público y puede llamarse directamente:

```python
payload = invoice._build_ecf_payload()
json_str = json.dumps(payload, indent=4, ensure_ascii=False)
```

Para integrar el envío al API, sobreescribir `action_send_ecf` en `l10n_do.ecf.preview.wizard` o extender `_build_ecf_payload` en un módulo hijo.

---

## Tests

```bash
# Todos los tests del módulo
python odoo-bin -d <base> --test-enable --stop-after-init -i l10n_do_electronic_invoice

# Solo generación de JSON
python odoo-bin -d <base> --test-tags /l10n_do_electronic_invoice:TestEcfJsonGeneration
```

Cobertura: E31 B2B, E32 consumidor final, E34 nota de crédito, múltiples ítems, validación sin nombre, tipo de pago automático, serialización JSON, flag `is_live`, código EAN, descuentos, direcciones, extracción de emails/teléfonos.

---

## Notas técnicas

1. **Sin `compute_all`**: las retenciones por línea se calculan como `abs(tax.amount / 100) × price_subtotal`. No se invoca el motor de impuestos en tiempo de extracción.

2. **`price_subtotal / quantity`**: el precio unitario neto se extrae de este cociente, lo que maneja correctamente impuestos con `price_include=True` (Odoo ya descontó el impuesto al calcular `price_subtotal`).

3. **`tax_totals` en Odoo 18**: es un `dict` Python (no JSON string como en v15). Este módulo no lo usa directamente; en cambio lee las líneas reales del asiento (`line_ids` filtradas por `display_type='tax'`).

4. **`is_ecf_invoice`**: provisto por `l10n_do_accounting`; detecta e-CF cuando `l10n_do_ncf_type[:2] == "e-"`. No se redeclara en este módulo.

5. **`_constrains_date_sequence`**: sobreescrito para excluir los e-CF de la validación cronológica de Odoo, ya que la DGII gestiona la secuencia de forma independiente.

6. **Conversión de moneda**: el campo `l10n_do_currency_rate` se calcula automáticamente al cambiar `currency_id` o `invoice_date`. El método `_convert_to_dop(amount)` aplica la tasa con `Decimal` para precisión en la conversión.
