# Facturación Electrónica e-CF — República Dominicana

**Versión:** 18.0.1.0.0 · **Licencia:** OPL-1 · **Autor:** Omar Bautista

Módulo Odoo 18 para la emisión completa de **Comprobantes Fiscales Electrónicos (e-CF)** de la DGII. Genera el payload JSON, lo envía automáticamente a `api.ecf-software.online` al confirmar cada factura, y persiste la respuesta (trackId, código de seguridad, QR, estado DGII) directamente en el registro contable.

---

## Tipos de comprobante soportados

| Código | Tipo | Uso principal |
|--------|------|---------------|
| **E31** | Factura de Crédito Fiscal | Ventas B2B con RNC |
| **E32** | Factura de Consumidor Final | Ventas B2C (con o sin RNC) |
| **E33** | Nota de Débito | Ajuste al alza sobre factura emitida |
| **E34** | Nota de Crédito | Devolución o ajuste a la baja |
| **E41** | Comprobante de Compras | Registro de compras a proveedores locales |
| **E43** | Gastos Menores | Gastos sin comprobante formal |
| **E44** | Regímenes Especiales | Empresas bajo régimen especial de tributación |
| **E45** | Gubernamental | Ventas a entidades del Estado |
| **E46** | Exportaciones | Ventas al exterior (sin ITBIS) |
| **E47** | Compras al Exterior | Servicios o bienes adquiridos fuera del país |

---

## Funcionalidades

- **Auto-envío al confirmar:** al publicar una factura e-CF, si `ecf_auto_send` está activo, el módulo llama a la API de inmediato sin intervención del usuario.
- **Envío manual:** botón _"Enviar a DGII"_ en el wizard de previsualización JSON para control total.
- **Previsualización JSON:** botón _"Ver JSON e-CF"_ disponible en borradores y facturas confirmadas.
- **Respuesta persistida:** `trackId`, `eNCF`, código de seguridad, URL QR e imagen QR (PNG) se guardan en la factura.
- **Diagnóstico de errores:** botón _"Ver Respuesta API"_ (rojo) visible solo cuando hay un error; muestra la respuesta cruda en un wizard.
- **Control por tipo de comprobante:** cada tipo (E31–E47) puede habilitarse o deshabilitarse por separado para el envío automático.
- **Validación E32 ≥ 250 000 DOP:** bloquea la confirmación si el comprador no tiene RNC/Cédula.
- **Soporte multidivisa:** la tasa de cambio DOP se calcula automáticamente al cambiar la moneda o la fecha.
- **Municipios DGII:** catálogo completo de municipios sincronizable con el campo `city` del contacto.

---

## Configuración

### 1. Credenciales de la API _(obligatorio antes de cualquier envío)_

`Configuración → Empresa → pestaña "Facturación Electrónica (e-CF)"`

| Campo | Descripción |
|-------|-------------|
| **URL de la API** | `https://api.ecf-software.online` (predeterminado) |
| **API Key** | Bearer token del tenant. Se emite **una sola vez**; guárdalo en un lugar seguro. |
| **Envío automático** | Activa el auto-envío al confirmar facturas e-CF. |

> **Importante:** si el API Key se pierde, debes registrar un nuevo tenant en la API
> o solicitarlo al administrador. No existe forma de recuperarlo.

---

### 2. Datos del emisor

`Configuración → Empresa → pestaña "Facturación Electrónica (e-CF)"`

| Campo | Descripción |
|-------|-------------|
| **RNC** | Identificador tributario de la empresa (campo `vat`). Requerido. |
| **Nombre Comercial** | Se incluye en el bloque `seller` del e-CF. |
| **Actividad Económica** | Código de actividad económica ante la DGII. |
| **Código de Sucursal** | `BranchInfo.Name` — default `0001`. |
| **Municipio** | Municipio DGII de la sede principal. |
| **Modo Producción** | `True` → DGII real · `False` → ambiente de certificación. |

---

### 3. Tipos de comprobante habilitados

`Configuración → Empresa → pestaña "Facturación Electrónica (e-CF)" → tabla "Tipos de Comprobante"`

Cada fila tiene un toggle **"Enviar a la DGII"**. Los tipos deshabilitados quedan con estado `skipped` al confirmar (no se envían ni bloquean).

Usa el botón **"Inicializar tipos de comprobante"** en instalaciones nuevas para crear los 10 registros con el toggle activo por defecto.

---

### 4. Impuestos

El módulo identifica los impuestos por **nombre**, no por cuenta ni etiqueta:

| Condición en el nombre | Clasificación |
|------------------------|---------------|
| Contiene `ITBIS` y `amount > 0` | ITBIS gravado (18%, 16%, 9%, 8%) |
| Contiene `ITBIS` y `amount < 0` | ITBIS retenido (solo E41) |
| Contiene `ISR`, `RENTA` o `RETENCION` y `amount < 0` | ISR retenido |
| Sin ITBIS positivo en la línea | Exento |

---

### 5. Municipios

El CSV `data/l10n_do.municipality.csv` carga el catálogo al instalar el módulo. Para enlazar contactos existentes usa la acción de servidor **"Sincronizar Municipios DGII"** desde la lista de contactos: actualiza `l10n_do_municipality_id` según el campo `city`.

---

## Flujo de envío

```
[Borrador] ──── Confirmar ────────────────────────────────────────────────────────┐
                    │                                                              │
                    │  ecf_auto_send = True                                       │
                    ▼                                                              │
          ¿Tipo habilitado?                                                        │
           NO → status = 'skipped'                                                │
           SÍ → _build_ecf_payload()                                              │
                    │                                                              │
                    ▼                                                              │
          POST /api/factura/generar-comprobante                                   │
                    │                                                              │
         ┌──────────┴──────────┐                                                  │
       200 OK              Error HTTP / timeout                                   │
         │                     │                                                  │
         ▼                     ▼                                                  │
  Guardar en factura:     status = 'error'                                       │
  · ecf_track_id          ecf_api_message = respuesta cruda                      │
  · ecf_codigo_seguridad  Botón "Ver Respuesta API" (rojo) visible               │
  · ecf_qr_url            Reintentar con "Enviar a DGII"                         │
  · ecf_qr_image (PNG)                                                            │
  · ecf_validation_status                                                         │
    '1' Aceptado                                                                  │
    '3' En Proceso ──── (botón "Re-consultar DGII" pendiente — Bloque 4)         │
    '4' Aceptado Condicional                                                      │
    ''  → 'rfce' (E32 < 250K, sin DGII)  ◄────────────────────────────────────┘
```

---

## Pautas importantes de e-CF

### E32 y el path RFCE

Las facturas E32 con monto **menor a 250 000 DOP** no pasan por la DGII. La API las registra localmente y devuelve un `trackId` que comienza con `"RFCE-"` y un `estado` vacío. Esto **no es un error** — el módulo lo interpreta como `status = 'rfce'`.

Para E32 con monto **igual o mayor a 250 000 DOP**, el comprador **debe tener RNC o Cédula** configurados. Sin ellos, la confirmación se bloquea.

### Notas de Crédito y Débito (E33 / E34)

- Requieren el campo **Código de Modificación** (`l10n_do_ecf_modification_code`) antes de confirmar.
- El NCF original se toma de la factura referenciada (`reversed_entry_id` o `debit_origin_id`).
- La fecha de la factura original se formatea como `dd-MM-yyyy` en el bloque `InformacionReferencia`.

### Estado "En Proceso" (código `3`)

La DGII puede tardar horas en procesar un comprobante. Un estado `3` no significa error — significa que el e-CF fue recibido y está pendiente de validación. El Bloque 4 del roadmap implementará la re-consulta automática por cron.

### E41 y E47 (compras / exterior)

Estos tipos son para **registrar gastos y compras**, no ventas. En la mayoría de empresas no se emiten localmente y conviene deshabilitarlos en la tabla de tipos de comprobante para evitar envíos accidentales.

### Ambiente de certificación vs producción

El campo **"Modo Producción"** en la empresa (`is_live`) envía el flag `"live": "1"` o `"0"` al API. Usar siempre `is_live = False` en entornos de prueba para no generar e-CF reales.

### Secuencias NCF

La DGII asigna bloques finitos de números de comprobante por tipo. Cuando el bloque se agota, la empresa debe solicitar una nueva autorización. El Bloque 10 del roadmap implementará el control de secuencias con advertencia automática y bloqueo al agotarse.

---

## Referencia de campos

### `account.move` — campos agregados

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ecf_validation_status` | Selection | Estado: `pending`, `success`, `error`, `3`, `4`, `rfce`, `skipped` |
| `ecf_api_message` | Text | Respuesta completa del API (éxito o error) |
| `ecf_track_id` | Char | `trackId` de la DGII (o `RFCE-{eNCF}` para RFCE) |
| `ecf_qr_url` | Char | URL de verificación DGII del e-CF |
| `ecf_qr_image` | Binary | Imagen PNG del QR generada desde `ecf_qr_url` |
| `ecf_codigo_seguridad` | Char | Primeros 6 caracteres del SignatureValue |
| `ecf_fecha_firma` | Datetime | Fecha de firma digital (llega via webhook) |
| `l10n_do_currency_rate` | Float(12,4) | Tasa de cambio DOP al momento de emitir |
| `l10n_do_payment_type` | Selection | Forma de pago DGII (1–8), calculado desde el diario |
| `l10n_do_modification_reason` | Char | Razón de modificación libre (E33/E34) |
| `l10n_do_indicador_monto_gravado` | Selection | `IndicadorMontoGravado` (0/1) |

### `res.company` — campos agregados

| Campo | Descripción |
|-------|-------------|
| `ecf_api_url` | URL base de la API (default: `https://api.ecf-software.online`) |
| `ecf_api_key` | Bearer token del tenant (campo password) |
| `ecf_auto_send` | Auto-envío al confirmar (default: `True`) |
| `is_live` | Modo producción DGII (`True`) o certificación (`False`) |
| `l10n_do_trade_name` | Nombre comercial para el e-CF |
| `l10n_do_economic_activity` | Actividad económica DGII |
| `l10n_do_branch_code` | Código de sucursal (default: `0001`) |
| `ecf_doc_type_config_ids` | One2many → configuración por tipo de comprobante |

### `l10n_do.ecf.doc.type.config` — modelo de configuración por tipo

| Campo | Descripción |
|-------|-------------|
| `doc_type` | Código del tipo (31–47) |
| `send_to_dgii` | Toggle de envío para este tipo |
| `company_id` | Empresa propietaria del registro |

### `product.template` — campos agregados

| Campo | Valores | Descripción |
|-------|---------|-------------|
| `l10n_do_product_type` | `1` Bien / `2` Servicio | Sobreescribe la inferencia automática |
| `l10n_do_billing_indicator` | `1`–`4` | `IndicadorFacturacion` fijo por producto |

---

## Arquitectura

```
l10n_do_electronic_invoice/
├── __manifest__.py
├── models/
│   ├── account_move.py          ← núcleo: payload, envío, auto-send, helpers
│   ├── ecf_doc_type_config.py   ← config de envío por tipo de comprobante
│   ├── res_company.py           ← campos API, is_live, datos emisor
│   ├── res_partner.py           ← municipio + sync ciudad
│   ├── res_country_state.py     ← código DGII de provincia
│   ├── l10n_do_municipality.py  ← modelo l10n_do.municipality
│   └── product_template.py      ← tipo producto + indicador facturación
├── wizard/
│   ├── ecf_preview_wizard.py    ← previsualización JSON + botón "Enviar a DGII"
│   ├── ecf_preview_wizard_views.xml
│   ├── ecf_error_wizard.py      ← muestra respuesta API en estado error
│   └── ecf_error_wizard_views.xml
├── views/
│   ├── account_move_views.xml          ← botones en header + campos en Otra Info
│   ├── res_company_views.xml           ← pestaña e-CF + tabla de tipos
│   ├── ecf_doc_type_config_views.xml   ← vista lista del modelo de config
│   └── res_partner_views.xml           ← campo municipio en contacto
├── security/
│   └── ir.model.access.csv
└── data/
    └── l10n_do.municipality.csv
```

### Construcción del payload

```
_build_ecf_payload()
    ├── _ecf_get_doc_type()             → '31', '32', …
    ├── _ecf_get_tax_totals()           → impuestos desde asiento (sin recalcular)
    ├── _ecf_get_header()               → docType, issuedDateTime, additionalInfo
    ├── _ecf_get_seller()               → taxID, name, contact, branchInfo
    ├── _ecf_get_buyer()                → taxID / 'NO_APLICA'
    ├── _ecf_get_items()                → items[] con codes, discounts, totals
    ├── _ecf_get_totals()               → totalTaxes + grandTotal
    ├── _ecf_get_payments()             → payments[] (excluido en E34/E43)
    └── _ecf_get_additional_doc_info()  → InformacionReferencia (E33/E34)
```

---

## Notas técnicas

1. **Sin `compute_all`:** las retenciones por línea se calculan como `abs(tax.amount / 100) × price_subtotal`. No se invoca el motor de impuestos en tiempo de generación del payload.

2. **Precio unitario neto:** se extrae como `price_subtotal / quantity`. Maneja correctamente impuestos con `price_include = True` porque Odoo ya descontó el impuesto al calcular `price_subtotal`.

3. **`_constrains_date_sequence` anulado:** los e-CF usan secuencias de la DGII que no siguen el orden cronológico que Odoo valida. Se filtra para que solo aplique a comprobantes no-ECF.

4. **`is_ecf_invoice`:** campo provisto por `l10n_do_accounting`; detecta e-CF cuando `l10n_do_ncf_type[:2] == "e-"`. No se redeclara en este módulo.

5. **Conversión de moneda:** el campo `l10n_do_currency_rate` usa `Decimal` con `ROUND_HALF_UP` para evitar diferencias de centavos en la conversión a DOP.

6. **`tax_totals` en Odoo 18:** es un `dict` Python (no JSON string como en v15). Este módulo no lo usa; lee directamente las líneas `line_ids` con `display_type='tax'` del asiento contable publicado.

---

## Tests

```bash
# Todos los tests del módulo
python odoo-bin -d <base> --test-enable --stop-after-init -i l10n_do_electronic_invoice

# Solo generación de JSON
python odoo-bin -d <base> --test-tags /l10n_do_electronic_invoice:TestEcfJsonGeneration
```

Cobertura: E31 B2B, E32 consumidor final, E34 nota de crédito, múltiples ítems, validación sin nombre, tipo de pago automático, serialización JSON, flag `is_live`, código EAN, descuentos, municipios, extracción de emails/teléfonos.
