# Plan de Implementación: Módulo `l10n_do_electronic_invoice` (Odoo 18)

## Objetivo

Crear un módulo llamado **`l10n_do_electronic_invoice`** que, a partir de una factura confirmada (`account.move`), construya limpiamente el JSON para la API DigiFact y lo muestre en un **wizard de previsualización** para depuración y envío manual.

> **No hay envío automático al confirmar.** El usuario verá el JSON, podrá revisarlo y luego enviarlo.  
> **El módulo `ecf_xml_builder` existente se elimina** y no coexiste.

---

## Estado de campos por modelo — lo que ya existe

### `res.company` (archivo `res_company.py` en extra-addons)
| Campo | Estado |
|---|---|
| `vat` | ✅ nativo Odoo |
| `name`, `phone`, `email`, `website` | ✅ nativo Odoo |
| `is_live` | ✅ **ya existe** en `res_company.py` del módulo anterior |
| `l10n_do_enable_resend_button` | ✅ ya existe |
| `l10n_do_default_client` | ✅ ya existe |
| `l10n_do_municipality_id` | ✅ ya existe → `Many2one('l10n_do.municipality')` → da el `code` para `District` |
| `state_id.l10n_do_dgii_code` | ✅ ya existe en `res_country_state.py` → da código 6 dígitos para `State` |

### `account.move` (en `l10n_do_accounting`)
| Campo | Estado |
|---|---|
| `invoice_date`, `name`, `invoice_origin` | ✅ nativo |
| `amount_untaxed`, `amount_total` | ✅ nativo |
| `l10n_do_income_type` | ✅ ya existe |
| `l10n_do_ecf_modification_code` | ✅ ya existe |
| `l10n_do_origin_ncf` | ✅ ya existe (NCF modificado) |
| `l10n_do_fiscal_number` | ✅ ya existe |
| `l10n_latam_document_type_id` | ✅ ya existe |
| `is_ecf_invoice` | ✅ ya existe |
| `reversed_entry_id` | ✅ nativo Odoo |

### `res.country.state`
| Campo | Estado |
|---|---|
| `l10n_do_dgii_code` | ✅ ya existe en `res_country_state.py` |

### `res.partner`
| Campo | Estado |
|---|---|
| `vat`, `name`, `phone`, `email`, `street`, `state_id` | ✅ nativo |
| `l10n_do_municipality_id` | ✅ ya existe (usado en `json odoo.md`) |
| `l10n_do_dgii_tax_payer_type` | ✅ ya existe |

### `res.branch` (módulo `branch` de Odoo)
| Campo | Estado |
|---|---|
| `code`, `name`, `street`, `company_id`, `principal_branch` | ✅ ya existe según `json odoo.md` |

### `l10n_latam.document.type`
| Campo | Estado |
|---|---|
| `doc_code_prefix` | ✅ ya existe → `"E31"`, `"E32"`, etc. |
| `l10n_do_ncf_type` | ✅ ya existe → `"e-fiscal"`, `"e-consumer"`, etc. |

---

## Mapeo `doc_code_prefix` → `DocType` numérico

Basado en el CSV `l10n_latam.document.type.csv`:

| `doc_code_prefix` | `DocType` JSON | Nombre |
|---|---|---|
| `E31` | `"31"` | Crédito Fiscal Electrónica |
| `E32` | `"32"` | Consumo Electrónica |
| `E33` | `"33"` | Nota de Débito Electrónica |
| `E34` | `"34"` | Nota de Crédito Electrónica |
| `E41` | `"41"` | Compras Electrónica |
| `E43` | `"43"` | Gasto Menor Electrónica |
| `E44` | `"44"` | Régimen Especial Electrónica |
| `E45` | `"45"` | Gubernamental Electrónica |
| `E46` | `"46"` | Exportación Electrónica |
| `E47` | `"47"` | Pago al Exterior Electrónica |

**Lógica de extracción:**
```python
doc_type = invoice.l10n_latam_document_type_id.doc_code_prefix.lstrip("E")
# "E31" → "31"
```

---

## Campos nuevos a crear en el módulo `l10n_do_electronic_invoice`

### En `res.company` (solo agregar lo que falta)

| Campo | Nombre técnico | Tipo | Notas |
|---|---|---|---|
| Nombre comercial | `l10n_do_trade_name` | `Char` | `NombreComercial` en AdditionlInfo |
| Actividad económica | `l10n_do_economic_activity` | `Char` | `ActividadEconomica` en AdditionlInfo |
| URL DigiFact | `l10n_do_digifact_url` | `Char` | Calculado o fijo por `is_live` |
| API Key DigiFact | `l10n_do_digifact_api_key` | `Char` | Credencial (opcional por ahora) |

> `is_live` ya existe → URL se deriva:
> - `is_live=True` → `https://ecf.dgii.gov.do/recepcion/...`
> - `is_live=False` → `https://ecf.dgii.gov.do/testecf/...`

### En `account.move`

| Campo | Nombre técnico | Tipo | Notas |
|---|---|---|---|
| Tipo de pago DGII | `l10n_do_payment_type` | `Selection` | `"1"` Efectivo, `"2"` Cheque/Transf., `"3"` Tarjeta, `"4"` Crédito, `"5"` Bonos, `"6"` Permuta, `"7"` Nota Crédito, `"8"` Mixto |
| Código vendedor | `l10n_do_seller_code` | `Char` | `CodigoVendedor` (omitir en 41/43/47) |
| Número pedido interno | `l10n_do_purchase_order_number` | `Char` | `NumeroPedidoInterno` |
| Zona venta | `l10n_do_sales_zone` | `Char` | (omitir en 41/43/47) |
| Ruta venta | `l10n_do_sales_route` | `Char` | (omitir en 41/43/47) |
| Info adicional emisor | `l10n_do_additional_seller_info` | `Char` | Texto libre, puede mapearse desde `narration` |
| Razón de modificación | `l10n_do_modification_reason` | `Char` | ⚠️ CRÍTICO para E33/E34 |
| Indicador monto gravado | `l10n_do_indicador_monto_gravado` | `Selection` `"0"/"1"` | Default `"0"` |

### En `product.template`

| Campo | Nombre técnico | Tipo | Notas |
|---|---|---|---|
| Tipo DGII | `l10n_do_product_type` | `Selection` | `"1"` Bien, `"2"` Servicio. Para tipo 47 siempre `"2"` |
| Indicador facturación | `l10n_do_billing_indicator` | `Selection` | `"1"` Gravado ITBIS, `"2"` Otras exentas, `"3"` Bienes exentos, `"4"` Servicios exentos |

### En `uom.uom` (opcional, para later)

| Campo | Nombre técnico | Tipo | Notas |
|---|---|---|---|
| Código DGII | `l10n_do_uom_code` | `Char` | Por defecto `"32"` (unidad) |

---

## Lógica de negocio del `get_invoice_data()` — integrada del módulo anterior

### Determinación de `doc_type`
```python
doc_type = invoice.l10n_latam_document_type_id.doc_code_prefix.lstrip("E")
# Quita la "E" de prefijos electrónicos: "E31" → "31"
```

### Secuencia
```python
if invoice.l10n_latam_document_number:
    sequence = invoice.l10n_latam_document_number[3:]  # "E310000000001" → "0000000001"
else:
    sequence = invoice._invoice_api_sequence()  # fallback
```

### Consumidor final
```python
is_consumer = (
    not invoice.partner_id.vat 
    or invoice.partner_id.l10n_do_dgii_tax_payer_type == "non_payer"
)
buyer_tax_id = "NO_APLICA" if is_consumer else invoice.partner_id.vat
```
Cuando `"NO_APLICA"`: omitir `Contact`, `AdditionlInfo`, `AddressInfo` del Buyer Y `Discounts`/`Charges` en ítems.

### Sucursal (BranchInfo)
```python
main_branch = env['res.branch'].search([
    ('company_id', '=', env.company.id),
    ('principal_branch', '=', True)
], limit=1)
# → main_branch.code, main_branch.name, main_branch.street
```

### Código municipio
```python
"District": env.company.l10n_do_municipality_id.code or ""
"State": env.company.state_id.l10n_do_dgii_code or ""
```

### Tipo de ítem
```python
# Para doc_type == "47" siempre es "2" (servicio)
# Para otros: mapear desde product.type
# "consu"/"product" → "1" (Bien), "service" → "2" (Servicio)
```

### Código de producto (Codes)
```python
# EAN si tiene barcode, PLU si tiene default_code, SIN_CODIGO si no tiene nada
"Name": "EAN" if product.barcode else ("PLU" if product.default_code else "SIN_CODIGO")
"Value": product.barcode or product.default_code or "0"
```

### Precio unitario sin impuesto
```python
# Usar método _get_price_unit_wo_tax_for_payload(line) del módulo anterior
# Aplica descuento: price_unit * (1 - discount/100)
```

### Descuentos por línea
```python
"Code": "%" if line.discount > 0 else "$"
"Rate": "{:.2f}".format(line.discount)
"Amount": price_sin_tax * line.discount * line.quantity
```

### IndicadorFacturacion (lógica `get_indicador_facturacion`)
```python
# doc_type en ["43", "44", "47"] → "2" (otras exentas)
# Línea sin impuesto → "3" (bienes exentos) o "4" (servicios exentos)
# Línea con ITBIS → "1" (gravada)
# Preferible: campo en product.template, fallback a esta lógica
```

### Reglas por `doc_type` (campos omitidos)
| Tipos | Campos omitidos |
|---|---|
| `43`, `44`, `47` | `TotalTaxableAmount`, bloque `SUBTOTALES` de AdditionalDocumentInfo, `CodigoVendedor`, `ZonaVenta`, `RutaVenta` |
| `46` | bloque `INFORMACION_REFERENCIA` de AdditionalDocumentInfo |
| Solo `33`, `34` | Requieren `FechaNCFModificado`, `NCFModificado`, `CodigoModificacion` en AdditionalDocumentInfo |
| `41`, `47` | Requieren `IndicadorAgenteRetencionPercepcion`, `MontoISRRetenido`, `TotalISRRetencion` |
| Solo `41` | Además: `TotalITBISRetenido`, `MontoITBISRetenido` por línea |

### Retenciones ISR/ITBIS (tipos 41 y 47)
El módulo anterior ya tiene `_get_dgii_tax_totals()` que calcula:
- `total_taxes.TotalTax` → lista de impuestos agrupados por código
- `additional_info_totals.TotalISRRetencion`
- `additional_info_totals.TotalITBISRetenido`
- `additional_info_item[index].MontoISRRetenido` por línea
- `additional_info_item[index].MontoITBISRetenido` por línea

Este método **se reutilizará e integrará** en el nuevo módulo.

### Pago neto para tipo 41
```python
# Tipo 41: monto neto = total - ISR retenido - ITBIS retenido
amount_net = amount_total - TotalISRRetencion - TotalITBISRetenido
```

---

## Estructura final del módulo

```
extra-addons/
└── l10n_do_electronic_invoice/
    ├── __manifest__.py
    ├── __init__.py
    ├── models/
    │   ├── __init__.py
    │   ├── res_company.py           # l10n_do_trade_name, l10n_do_economic_activity, is_live (ya existe, se reutiliza)
    │   ├── res_country_state.py     # Incluir l10n_do_dgii_code (ya existe en extra-addons raíz)
    │   ├── account_move.py          # Campos nuevos + _build_digifact_payload() + _get_dgii_tax_totals()
    │   ├── product_template.py      # l10n_do_product_type, l10n_do_billing_indicator
    │   └── uom_uom.py               # l10n_do_uom_code (opcional)
    ├── wizard/
    │   ├── __init__.py
    │   └── digifact_preview_wizard.py  # Wizard de previsualización del JSON
    ├── views/
    │   ├── res_company_views.xml    # Pestaña "DigiFact / e-CF" en configuración
    │   ├── account_move_views.xml   # Botón "Previsualizar JSON" en factura
    │   ├── product_views.xml        # Campos DGII en producto
    │   ├── uom_views.xml            # Campo código DGII en UdM
    │   └── digifact_wizard_views.xml # Vista del wizard con JSON formateado
    └── security/
        └── ir.model.access.csv
```

---

## Fases de Implementación

### Fase 1 — Modelos y campos (sin lógica de negocio)
1. `res_company.py` → agregar `l10n_do_trade_name`, `l10n_do_economic_activity`
2. `res_country_state.py` → mover al módulo (ya existe como archivo suelto)
3. `account_move.py` → agregar campos nuevos listados arriba
4. `product_template.py` → `l10n_do_product_type`, `l10n_do_billing_indicator`
5. `uom_uom.py` → `l10n_do_uom_code`

### Fase 2 — Motor de construcción del JSON
Método principal `_build_digifact_payload()` con subfunciones:
- `_digifact_doc_type()` → extrae número de doc_code_prefix
- `_digifact_sequence()` → extrae secuencia del NCF
- `_digifact_get_header()` → Header + AdditionalIssueDocInfo
- `_digifact_get_seller()` → Seller con BranchInfo desde res.branch
- `_digifact_get_buyer()` → Buyer con lógica consumidor final
- `_digifact_get_items()` → Items con Codes, Discounts, Charges, Totals, AdditionalInfo
- `_digifact_get_totals()` → Totals con TotalTaxes agrupados
- `_digifact_get_additional_doc_info()` → bloque complejo con SUBTOTALES e INFO_REFERENCIA
- `_digifact_get_payments()` → Payments con lógica neto para tipo 41
- `_get_dgii_tax_totals()` → cálculo impuestos (reutilizar del módulo anterior)
- `_get_price_unit_wo_tax_for_payload(line)` → precio sin impuesto por línea
- `get_indicador_facturacion(doc_type, tax)` → indicador 1-4 por línea
- `format_phone_number(phone)` → normalizar teléfono

### Fase 3 — Wizard de previsualización
- `digifact_preview_wizard.py`:
  - `json_preview` → campo `Text` con el JSON formateado (pretty-print)
  - `action_preview_json()` en `account.move` → abre el wizard
- Vista con área de texto de solo lectura mostrando el JSON indentado
- Botón "Copiar" (JS) y botón "Cerrar"

### Fase 4 — Vistas
- Botón "Ver JSON e-CF" en la factura (solo si `is_ecf_invoice = True`)
- Configuración de compañía con pestaña "DigiFact"
- Campos DGII en producto y UdM

---

## Reglas de negocio críticas

> [!IMPORTANT]
> Estas validaciones deben implementarse antes de construir el payload.

1. **`buyer_tax_id = "NO_APLICA"`** → omitir Contact, AdditionlInfo, AddressInfo del Buyer; omitir Discounts/Charges en ítems
2. **DocTypes `43`, `44`, `47`** → no incluir `TotalTaxableAmount`, no incluir bloque SUBTOTALES; omitir CodigoVendedor, ZonaVenta, RutaVenta
3. **`NumeroFacturaInterna`** → siempre `invoice.name` real, nunca vacío ni `"0"`
4. **`RazonModificacion`** → requerido para E33/E34 (validar antes de mostrar wizard)
5. **`InvoiceTotal`** → siempre `amount_total` de Odoo sin redondeos manuales
6. **NO incluir** campo `Id` en `AdditionalDocumentInfo`
7. **Tipo 47** → todos los ítems son tipo `"2"` (servicio)
8. **Tipos 41 y 47** → agregar `IndicadorAgenteRetencionPercepcion` y montos de retención

---

## Campos de `res.company` que llegan del archivo anterior (sin crear nuevamente)

| Campo | Origen |
|---|---|
| `is_live` | `res_company.py` (extra-addons raíz) → copiar al módulo |
| `l10n_do_enable_resend_button` | idem |
| `l10n_do_default_client` | idem |
| `l10n_do_municipality_id` | idem → ya usa `l10n_do.municipality` model |

> [!WARNING]
> Los archivos sueltos `res_company.py` y `res_country_state.py` en la raíz de extra-addons **no pertenecen a ningún módulo todavía**. Hay que integrarlos formalmente en `l10n_do_electronic_invoice`.

---

## Verificación

1. E31 con partner con RNC → JSON completo con TaxID real, Discounts, TotalTaxableAmount
2. E32/E43 consumidor final → `"NO_APLICA"`, sin Contact/Address buyer, sin Discounts  
3. E34 nota de crédito → incluye NCFModificado, CodigoModificacion, RazonModificacion
4. E41 compra → retenciones ISR/ITBIS por línea, TotalISRRetencion en totals
5. E47 pago exterior → todos ítems tipo "2", sin SUBTOTALES, pago neto
6. Wizard muestra JSON válido y parseable (sin campos `Id` huérfanos)
