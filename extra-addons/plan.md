# Plan de Implementación: Extractor JSON para Facturación Electrónica (Odoo 18)

## Objetivo
Crear un módulo `l10n_do_ecf` que herede `account.move` en Odoo 18 y extraiga el JSON para el API de la DGII (Digifact/SiaFe), **sin recalcular nada**: todo dato numérico lo toma directamente de Odoo.

---

## Contexto del Módulo Existente (Odoo 15)

El módulo actual (`facturacion_electronica`) tiene esta arquitectura:

```
models/
  facturacion_electronica.py  ← hereda account.move; orquesta todo
  payload_builder.py          ← convierte dict interno → JSON final
  codes_and_prefix.py         ← tablas de códigos DGII (tipo NCF, tipo item, impuestos)
  res_company.py              ← campos extra en company (is_live, municipio, etc.)
  res_partner.py              ← campos extra en partner (municipio, código DGII)
  l10n_do_municipality.py     ← modelo auxiliar para municipios DGII
  res_country_state.py        ← campo l10n_do_dgii_code en res.country.state
```

### Flujo de datos (Odoo 15)
1. `action_post()` → `get_invoice_data()` construye un dict intermedio con todos los datos crudos de Odoo.  
2. `_compute_tax_totals()` agrupa impuestos leyendo `tax_totals_json` (campo JSON serializado) y `invoice_line_ids`.  
3. `PayloadBuilder(invoice_data, doc_type).build_payload()` ensambla el JSON final.  
4. El JSON se envía al API externo (SiaFe/Digifact).

### Arquitectura real del módulo (archivos completos)

```
facturacion_electronica/
├── __manifest__.py              ← v15.0.1.0.0; deps: account, l10n_do, l10n_do_accounting, odoo_multi_branch_base
├── models/
│   ├── facturacion_electronica.py   ← núcleo: hereda account.move
│   ├── payload_builder.py           ← PayloadBuilder: dict → JSON SiaFe/Digifact
│   ├── codes_and_prefix.py          ← CodesAndPrefix: códigos NCF, tipos item, TAX_CODES
│   ├── account_tax.py               ← campo extra x_dgii_code en account.tax
│   ├── res_company.py               ← is_live, l10n_do_municipality_id, l10n_do_enable_resend_button
│   ├── res_partner.py               ← l10n_do_municipality_id en res.partner
│   ├── l10n_do_municipality.py      ← modelo l10n_do.municipality
│   ├── res_country_state.py         ← l10n_do_dgii_code en res.country.state
│   ├── l10n_latam_document_type.py  ← campos extra en tipo de documento latam
│   ├── res_currency.py              ← helpers de tasa de cambio
│   └── uom_uom.py                   ← código DGII en unidades de medida
└── wizard/
    ├── wizard_update_invoice.py
    └── wizard_edit_info.py
```

---

## Cambio de Enfoque: Extracción de Odoo 15 (sin recalcular)

### Problema actual en `_compute_tax_totals()`

El método actualmente **recalcula manualmente** datos que Odoo ya calculó:

| doc_type | Qué recalcula actualmente (a eliminar) |
|---|---|
| 31, 32, 34, 44, 45 | Itera línea por línea: `base_line = precio_unit * qty`, `tax_amount = base_line * rate / 100`. Sobrescribe `InvoiceTotal` con la suma manual. |
| 41 | Calcula retenciones ISR/ITBIS: `monto = (tax.amount / 100) * base_line`. Llama a `_get_price_unit_wo_tax_for_payload` que a su vez puede invocar `compute_all`. |
| Todos | `_get_price_unit_wo_tax_for_payload()` llama a `line.tax_ids._origin.compute_all(...)` cuando hay impuestos `price_include=True`. |

### Fuentes de datos disponibles en Odoo 15 (no requieren recálculo)

#### Nivel de documento (`account.move`)

| Campo Odoo 15 | Tipo | Descripción | Uso en JSON DGII |
|---|---|---|---|
| `tax_totals_json` | `Text` (JSON) | Totales y grupos de impuesto calculados por Odoo | Base imponible, grupos ITBIS, totales |
| `amount_untaxed` | `Monetary` | Base imponible sin impuesto | `TaxableAmount` global |
| `amount_tax` | `Monetary` | Total de impuestos del documento | Suma de `TotalTax.Amount` |
| `amount_total` | `Monetary` | Total con impuestos | `InvoiceTotal` |

#### Estructura de `tax_totals_json` (Odoo 15)

```python
tax_data = json.loads(self.tax_totals_json or '{}')

# Totales globales (ya calculados por Odoo):
base  = tax_data.get('amount_untaxed', 0.0)   # ← usar en lugar de self.amount_untaxed
total = tax_data.get('amount_total',   0.0)

# Grupos de impuesto (ya agrupados por Odoo):
groups = tax_data.get('groups_by_subtotal', {}).get('Base imponible', [])
# Cada grupo tiene:
# {
#     'tax_group_name':        'ITBIS 18%',
#     'tax_group_amount':      198641.07,    ← monto del impuesto (listo)
#     'tax_group_base_amount': 1103561.52,   ← base gravada (lista)
#     'tax_group_id':          <int>,
# }
```

#### Nivel de línea (`account.move.line`)

| Campo Odoo 15 | Tipo | Descripción | Uso en JSON DGII |
|---|---|---|---|
| `price_subtotal` | `Monetary` | Total línea sin impuesto | base por línea; `total_item` |
| `price_tax` | `Monetary` | Total impuesto de la línea | monto retención por línea |
| `price_total` | `Monetary` | Total línea con impuesto | verificación |
| `price_unit` | `Float` | Precio unitario bruto | precio cuando no hay `price_include` |
| `quantity` | `Float` | Cantidad | `qty` del item |
| `discount` | `Float` | Descuento en % | `Discount.Rate` |
| `tax_ids` | `Many2many` | Impuestos asignados | detectar tipo ITBIS/ISR/retención |

### Mapa de extracción: campo Odoo → campo JSON DGII

| Campo JSON DGII | Campo Odoo 15 a leer | Fórmula |
|---|---|---|
| `TaxableAmount` global | `tax_totals_json['amount_untaxed']` | `_convert_to_dop(base)` |
| `InvoiceTotal` | `tax_totals_json['amount_total']` | `_convert_to_dop(total)` (doc 46/47: usar base) |
| `TaxableAmount` por grupo (TotalTax) | `group['tax_group_base_amount']` | `_convert_to_dop(group_base)` |
| `Amount` impuesto por grupo (TotalTax) | `group['tax_group_amount']` | `_convert_to_dop(group_amount)` |
| `Rate` por grupo (TotalTax) | derivado | `group_amount / group_base * 100` |
| `Items.Price` (precio unit sin tax) | `line.price_subtotal / line.quantity` | si qty > 0; si no: `line.price_unit` |
| `Items.total_item` | `line.price_subtotal` | ya sin impuesto |
| `MontoISRRetenido` por línea | `line.price_subtotal` como base | `abs(tax.amount / 100 * line_base)` para impuestos ISR |
| `MontoITBISRetenido` por línea | `line.price_subtotal` como base | igual, para impuestos retención ITBIS |

### Implementación actualizada de `_get_price_unit_wo_tax_for_payload`

```python
# ANTES — llama a compute_all (a eliminar):
def _get_price_unit_wo_tax_for_payload(self, line):
    if any(t.price_include for t in line.tax_ids):
        taxes_res = line.tax_ids._origin.compute_all(
            line.price_unit, currency=..., quantity=1.0, ...
        )
        return self._convert_to_dop(taxes_res['total_excluded'])
    return self._convert_to_dop(line.price_unit)

# DESPUÉS — lee price_subtotal ya calculado por Odoo:
def _get_price_unit_wo_tax_for_payload(self, line):
    """Precio unitario neto. Odoo ya calculó price_subtotal sin importar price_include."""
    if line.quantity:
        return self._convert_to_dop(float(line.price_subtotal) / float(line.quantity))
    return self._convert_to_dop(float(line.price_unit or 0.0))
```

### Implementación actualizada de `_compute_tax_totals` — bloque 31/32/34/44/45

```python
# ANTES — itera líneas y recalcula (a eliminar):
for line in self.invoice_line_ids.filtered(lambda l: not l.display_type):
    d_price_unit_dop = Decimal(str(self._get_price_unit_wo_tax_for_payload(line)))
    d_line_base = d_price_unit_dop * Decimal(str(line.quantity))
    d_tax_amount = d_line_base * d_rate / Decimal("100")
    grouped_taxes[key]["TaxableAmount"] += d_line_base
    grouped_taxes[key]["Amount"] += d_tax_amount

# DESPUÉS — lee grupos de tax_totals_json (Odoo ya los calculó):
tax_data = json.loads(self.tax_totals_json or '{}')
groups = tax_data.get('groups_by_subtotal', {}).get('Base imponible', [])

for group in groups:
    lower = (group.get('tax_group_name', '') or '').lower()
    if any(k in lower for k in ('isr', 'renta', 'retencion', 'retención')):
        continue  # retenciones van a additional_info, no a TotalTax

    tax_base   = self._convert_to_dop(group.get('tax_group_base_amount', 0.0))
    tax_amount = self._convert_to_dop(group.get('tax_group_amount', 0.0))
    rate = round((tax_amount / tax_base) * 100, 2) if tax_base else 0.0
    code = _resolve_tax_code(group.get('tax_group_name', ''), rate, codes_prefix)

    total_tax_list.append({
        "Code": code,
        "TaxableAmount": "{:.2f}".format(tax_base),
        "Rate": "{:.2f}".format(rate),
        "Amount": "{:.2f}".format(tax_amount),
    })
```

### Implementación actualizada de `_compute_tax_totals` — bloque doc_type 41 (retenciones)

```python
# ANTES — calcula base como precio_unit * qty (recalculado):
base_line = self._get_price_unit_wo_tax_for_payload(line) * float(line.quantity or 0.0)
monto_isr = (tax_amount / 100.0) * base_line

# DESPUÉS — usa price_subtotal (ya calculado por Odoo):
base_line = self._convert_to_dop(float(line.price_subtotal or 0.0))
monto_isr = abs(float(tax.amount or 0.0) / 100.0 * base_line)
```

### Helper auxiliar: `_resolve_tax_code`

Mapea nombre de grupo + tasa → código DGII sin recalcular:

```python
def _resolve_tax_code(tax_group_name, rate, codes_prefix):
    """Determina el código DGII (ITBIS1/ITBIS2/ITBIS3/EXENTO/etc.) a partir
    del nombre del grupo de impuesto y la tasa calculada."""
    TAX_CODES = codes_prefix.get_tax_codes()
    name_upper = (tax_group_name or '').upper()

    for key, info in TAX_CODES.items():
        if key.upper() in name_upper:
            if isinstance(info, dict) and 'code' not in info:
                for _, rate_info in info.items():
                    if abs(rate - rate_info['rate']) < 0.01:
                        return rate_info['code']
            else:
                return info.get('code', 'ITBIS3')

    # Fallback por tasa numérica
    if abs(rate - 18.0) < 0.01: return "ITBIS1"
    if abs(rate - 16.0) < 0.01: return "ITBIS2"
    if abs(rate -  9.0) < 0.01: return "ITBIS3"
    if abs(rate -  0.0) < 0.01: return "EXENTO"
    return "ITBIS3"
```

### Pasos pendientes de refactorización (Odoo 15)

- [ ] Reemplazar `_get_price_unit_wo_tax_for_payload` — usar `price_subtotal / quantity` (eliminar llamada a `compute_all`)
- [ ] Refactorizar bloque `doc_type in ("31","32","34","44","45")` en `_compute_tax_totals` — leer `groups_by_subtotal` en lugar de iterar líneas y recalcular impuesto
- [ ] Refactorizar bloque `doc_type == "41"` — usar `line.price_subtotal` como base de retenciones en lugar de `_get_price_unit_wo_tax_for_payload(line) * qty`
- [ ] Eliminar la rama `doc_type == "44"` que recalcula `calculated_total` línea por línea (reemplazar por lectura de `amount_untaxed`)
- [ ] Limpiar `_logger.info` de depuración redundantes en `_compute_tax_totals` y `_compute_is_electronic`
- [ ] Activar `enviar_factura_dgii` con lógica de reintento por error 9035 (actualmente comentado; hay dos versiones, la activa carece del while de reintentos)
- [ ] Verificar existencia de `_validate_taxes_by_ecf()` — referenciado en `action_post()` pero no encontrado en el archivo principal

---

## Cambios Críticos en Odoo 18 vs Odoo 15

| Área | Odoo 15 | Odoo 18 |
|---|---|---|
| Totales de impuesto | `tax_totals_json` (string JSON) | `tax_totals` (dict Python) |
| Grupos de impuesto en totales | `groups_by_subtotal['Base imponible']` | `tax_totals['subtotals'][n]['tax_groups']` |
| Base imponible | `tax_totals_json['amount_untaxed']` | `tax_totals['amount_untaxed']` |
| Total con impuestos | `tax_totals_json['amount_total']` | `tax_totals['amount_total']` |
| Ramas (`res.branch`) | Disponible en módulo enterprise | Renombrado/reorganizado; verificar si existe o usar `company_id` |
| Secuencia | `_set_next_sequence()` con retorno de string | Mismo nombre pero lógica interna refactorizada; `_sequence_field` y `_sequence_fixed_regex` importan |
| Validación de fecha secuencia | `@api.constrains` sobre `_constrains_date_sequence` | Igual pero el override debe llamar a `super()` explícito |
| `compute_all` en impuestos | `tax_ids.compute_all(...)` | Igual, sin cambio |
| `price_include` | Igual | Igual |
| `l10n_latam_document_type_id` | Viene de `l10n_latam_invoice_document` | Mismo módulo en Odoo 18 |
| `l10n_do_*` campos | Módulo `l10n_do_accounting` | Módulo renombrado a `l10n_do`; verificar prefijos |

---

## Estructura de Archivos Propuesta

```
l10n_do_ecf/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── account_move.py           ← hereda account.move (núcleo)
│   ├── ecf_payload_builder.py    ← idéntico a payload_builder.py (sin cambios)
│   ├── ecf_codes.py              ← idéntico a codes_and_prefix.py (sin cambios)
│   ├── res_company.py            ← campos extra en company
│   ├── res_partner.py            ← campos extra en partner (municipio)
│   ├── l10n_do_municipality.py   ← modelo auxiliar (copiar tal cual)
│   └── res_country_state.py      ← campo l10n_do_dgii_code (copiar tal cual)
├── data/
│   ├── l10n_do.municipality.csv
│   ├── res.country.state.csv
│   ├── ir_cron_data.xml          ← cron de sincronización si aplica
│   └── sync_data.xml
├── security/
│   └── ir.model.access.csv
└── views/
    ├── account_move_views.xml
    ├── res_company_views.xml
    ├── res_partner_views.xml
    └── l10n_do_municipality_views.xml
```

---

## Implementación: `models/account_move.py`

### 1. Campos a declarar

```python
class AccountMoveECF(models.Model):
    _inherit = 'account.move'

    # Estado del proceso ECF
    ecf_is_electronic = fields.Boolean(compute='_compute_ecf_is_electronic', store=True)
    ecf_validation_status = fields.Selection([
        ('pending', 'Pendiente'),
        ('success', 'Validado'),
        ('error', 'Error'),
    ], default='pending', store=True, copy=False)
    ecf_fiscal_number  = fields.Char(copy=False)          # e-NCF devuelto por DGII
    ecf_sequence       = fields.Char(copy=False)          # secuencia interna 10 dígitos
    ecf_qr_code        = fields.Text(store=True, copy=False)
    ecf_api_message    = fields.Text()

    # Moneda
    l10n_do_currency_rate = fields.Float(digits=(12, 4), default=1.0)
    show_exchange_rate    = fields.Boolean(compute='_compute_show_exchange_rate')
```

### 2. `_compute_ecf_is_electronic`

```python
@api.depends('l10n_latam_document_type_id')
def _compute_ecf_is_electronic(self):
    for move in self:
        move.ecf_is_electronic = (
            move.l10n_latam_document_type_id.code == 'E'
        )
```

### 3. Override de secuencia

```python
def _set_next_sequence(self):
    # Bloquear generación automática para documentos E y B
    if not self.l10n_latam_document_type_id:
        return super()._set_next_sequence()

    prefix = self.l10n_latam_document_type_id.doc_code_prefix
    code_map = {
        'E31': 'account.move.invoice.cliente',
        'E34': 'account.move.credit.cliente',
        'E33': 'account.move.debit.cliente',
        # ... resto de prefijos E y B
    }
    seq_code = code_map.get(prefix)
    if seq_code:
        return self.env['ir.sequence'].next_by_code(seq_code)
    return super()._set_next_sequence()
```

### 4. Override de validación de fecha de secuencia

```python
def _constrains_date_sequence(self):
    # Excluir documentos E (electrónicos) y B (proveedores)
    to_validate = self.filtered(
        lambda m: not m.ecf_is_electronic
        and (
            not m.l10n_latam_document_type_id
            or m.l10n_latam_document_type_id.code not in ('E', 'B')
        )
    )
    if to_validate:
        return super(AccountMoveECF, to_validate)._constrains_date_sequence()
```

### 5. Tasa de cambio

```python
@api.onchange('currency_id', 'invoice_date')
def _onchange_ecf_currency_rate(self):
    if not self.currency_id or not self.company_id:
        return
    if self.reversed_entry_id:
        self.l10n_do_currency_rate = self.reversed_entry_id.l10n_do_currency_rate
        return
    if self.currency_id == self.company_id.currency_id:
        self.l10n_do_currency_rate = 1.0
    else:
        date = self.invoice_date or fields.Date.today()
        self.l10n_do_currency_rate = self.env['res.currency']._get_conversion_rate(
            self.currency_id, self.company_id.currency_id, self.company_id, date
        )
```

---

## Implementación: Método Principal `get_invoice_data()`

Este método es el núcleo del extractor. **No debe hacer cálculos propios**: solo lee campos de Odoo.

### Firma y validaciones previas

```python
def get_invoice_data(self):
    self.ensure_one()
    if self.l10n_latam_document_type_id.code == 'B':
        return True  # Facturas de proveedor no se envían al API

    codes = EcfCodes()
    is_electronic = self.l10n_latam_document_type_id.code == 'E'
    doc_type = codes.get_ncf_electronic_type(
        self.l10n_latam_document_type_id.doc_code_prefix, is_electronic
    )
    if not doc_type:
        raise UserError("Tipo de documento no reconocido para eCF.")

    # Asignar nombre si aún no tiene
    if not self.name or self.name == '/':
        self.name = self._set_next_sequence()

    sequence = (
        self.l10n_latam_document_number[3:]
        if self.l10n_latam_document_number
        else self._ecf_next_sequence()
    )
    ...
```

### Sección `seller` — datos de la empresa emisora

```python
"seller": {
    "tax_id":     self.company_id.vat or "",
    "name":       self.company_id.name or "",
    "phones":     _split_phones(self.company_id.phone),
    "emails":     _split_emails(self.company_id.email),
    "website":    self.company_id.website or "",
    "branch_name": main_branch.code if main_branch else "0001",
    "branch_address": {
        "Address":  main_branch.street if main_branch else "",
        "District": self.company_id.l10n_do_municipality_id.code or "",
        "State":    self.company_id.state_id.l10n_do_dgii_code or "",
        "Country":  "DO",
    },
    "additional_info": [
        {"Name": "NombreComercial",      "Value": self.company_id.name or ""},
        {"Name": "ActividadEconomica",   "Value": self.company_id.l10n_do_activity or "Comercio"},
        {"Name": "NumeroFacturaInterna", "Value": self.name},
        {"Name": "InformacionAdicionalEmisor", "Value": self.narration or ""},
    ],
}
```

> **Nota Odoo 18**: `res.branch` puede no existir en Community. Si no existe, usar `self.company_id` directamente como sucursal principal.

### Sección `buyer` — datos del cliente

```python
"buyer": {
    "tax_id": self.partner_id.vat or "",
    "name":   self.partner_id.name or "",
    "phones": _split_phones(self.partner_id.phone),
    "emails": _split_emails(self.partner_id.email),
    "address": {
        "Address":  self.partner_id.street or "",
        "District": self.partner_id.l10n_do_municipality_id.code or "",
        "State":    self.partner_id.state_id.l10n_do_dgii_code or "",
        "Country":  "DO",
    },
    "additional_info": [
        {"Name": "InformacionAdicionalComprador", "Value": ""},
    ],
}
```

### Sección `items` — líneas de factura

```python
"items": [
    {
        "codes": [_get_product_code(line.product_id)],
        "type": codes.get_item_type_sufix(line.product_id.detailed_type)
                if doc_type not in ("41", "47") else "2",
        "description": line.product_id.name or "SIN_DESCRIPCION",
        "qty":  f"{line.quantity:.2f}",
        "unit_of_measure": line.product_uom_id.l10n_do_dgii_code or "32",
        # Precio unitario SIN impuesto incluido (ver helper _price_unit_excl_tax)
        "price": f"{_price_unit_excl_tax(line):.2f}",
        "discounts": {
            "Discount": [{
                "Code":   "%" if line.discount > 0 else "$",
                "Rate":   f"{line.discount:.2f}",
                "Amount": f"{_price_unit_excl_tax(line) * line.discount / 100 * line.quantity:.2f}",
            }]
        },
        "charges": {"Charge": [{"Code": "$", "Amount": "0.00"}]},
        "totals": {
            "total_item": f"{_price_unit_excl_tax(line) * line.quantity:.2f}"
        },
        "additional_info": [
            {"Name": "DescripcionItem",       "Value": line.product_id.name or ""},
            {"Name": "IndicadorFacturacion",   "Value": _get_indicador_facturacion(doc_type, line)},
            {"Name": "MontoISRRetenido",        "Value": "0.00"},  # Ver sección retenciones
        ],
    }
    for line in self.invoice_line_ids.filtered(lambda l: not l.display_type)
]
```

---

## Implementación: `_compute_tax_totals_ecf()` — Adaptación a Odoo 18

### Diferencia principal: `tax_totals` en Odoo 18

En Odoo 15, los totales se leían desde `json.loads(self.tax_totals_json)`.  
En **Odoo 18**, el campo es `self.tax_totals` (ya es un dict, no string).

```python
# Odoo 15
tax_data = json.loads(self.tax_totals_json)
base = tax_data.get('amount_untaxed', 0.0)
total = tax_data.get('amount_total', 0.0)
tax_groups = tax_data.get('groups_by_subtotal', {}).get('Base imponible', [])

# Odoo 18 — equivalente
tax_data = self.tax_totals or {}
base  = tax_data.get('amount_untaxed', 0.0)
total = tax_data.get('amount_total', 0.0)
# En Odoo 18 la estructura es: tax_totals['subtotals'] → lista de subtotales
# Cada subtotal tiene 'tax_groups' con los grupos
tax_groups = []
for subtotal in tax_data.get('subtotals', []):
    tax_groups.extend(subtotal.get('tax_groups', []))
```

### Estructura esperada de `tax_totals` en Odoo 18

```python
{
    'amount_untaxed': 1103561.52,
    'amount_total':   1302202.59,
    'subtotals': [
        {
            'name': 'Base imponible',
            'amount': 1103561.52,
            'tax_groups': [
                {
                    'tax_group_name': 'ITBIS 18%',
                    'tax_group_amount': 198641.07,
                    'tax_group_base_amount': 1103561.52,
                    'tax_group_id': <id>,
                }
            ]
        }
    ]
}
```

### Lógica de agrupación por tipo de documento

La lógica varía según `doc_type`. **No cambiar la lógica de negocio, solo el origen del dato**:

| doc_type | Fuente de totales | Notas |
|---|---|---|
| 31, 32, 34, 44, 45 | Calcular por línea (Precio × Qty × Tasa) | Garantiza coherencia con validador Digifact |
| 41 | Calcular retenciones ISR/ITBIS por línea | `tax_ids` con nombre que contiene "isr" o "itbis retencion" |
| 46 | Base sin ITBIS; código `ITBIS3` Rate 0 | |
| 47 | Total = base; código `EXENTO` | |
| 33 | Normal con referencia a NCF modificado | |
| 43 | Sin comprador real, sin subtotales normales | |

---

## Validaciones Obligatorias

Implementar como `@api.constrains` o dentro de `action_post()`:

```python
# 1. RNC del emisor obligatorio para documentos E
if is_electronic and not self.company_id.vat:
    raise UserError("La empresa no tiene RNC configurado.")

# 2. NCF de referencia para Notas de Crédito/Débito
if doc_type in ("33", "34") and not self.l10n_do_origin_ncf:
    raise UserError("Las notas de crédito/débito requieren NCF de referencia.")

# 3. Fecha de vencimiento del NCF
vencimiento = self.get_ncf_expiry_date(self.journal_id, self.l10n_latam_document_type_id)
if not vencimiento:
    raise UserError("No se encontró fecha de vencimiento para el NCF.")

# 4. Municipio y provincia del emisor (necesarios para AddressInfo)
if not self.company_id.state_id:
    raise UserError("La empresa no tiene provincia configurada.")

# 5. Tipo de cambio para moneda extranjera
if self.currency_id != self.company_id.currency_id and self.l10n_do_currency_rate <= 0:
    raise UserError("Tasa de cambio DOP inválida.")

# 6. Líneas de factura sin tipo de display (no puede ir vacía)
if not self.invoice_line_ids.filtered(lambda l: not l.display_type):
    raise UserError("La factura no tiene líneas de producto.")

# 7. Secuencia única (verificar contra error 9035 del API)
# Manejado con el método _is_duplicate_encf_error() y _next_test_sequence()
```

---

## Helper: `_price_unit_excl_tax(line)`

Extrae el precio sin impuesto incluido. **Sin recalcular, solo lee de Odoo:**

```python
def _price_unit_excl_tax(self, line):
    """Precio unitario neto (sin impuesto incluido), convertido a DOP."""
    price = float(line.price_unit or 0.0)
    if not line.tax_ids or not any(t.price_include for t in line.tax_ids):
        return self._convert_to_dop(price)
    # Si hay impuesto incluido, Odoo ya calculó el base en price_subtotal / quantity
    if line.quantity:
        return self._convert_to_dop(float(line.price_subtotal) / float(line.quantity))
    return self._convert_to_dop(price)
```

> **Odoo 18 alternativa**: `line.price_subtotal` ya viene sin impuesto. Dividir entre `line.quantity` da el unitario neto sin necesidad de `compute_all`.

---

## Helper: Conversión a DOP

```python
def _convert_to_dop(self, amount):
    from decimal import Decimal, ROUND_HALF_UP
    rate = Decimal(str(self.l10n_do_currency_rate or 1.0))
    d_amount = Decimal(str(amount)) if amount else Decimal('0')
    return float((d_amount * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
```

---

## Formato del JSON Final (Referencia)

Basado en `factura original.txt`, el JSON tiene esta estructura de primer nivel:

```json
{
  "Version": "1.0",
  "CountryCode": "DO",
  "IdUser": <int>,
  "TaxID": "<RNC emisor>",
  "Header": { ... },
  "Seller": { ... },
  "Buyer": { ... },
  "Items": [ ... ],
  "Totals": { ... },
  "AdditionalDocumentInfo": { ... },
  "Payments": [ ... ]
}
```

### Reglas de presencia por `doc_type`

| Campo/Sección | 31 | 32 | 33 | 34 | 41 | 43 | 44 | 45 | 46 | 47 |
|---|---|---|---|---|---|---|---|---|---|---|
| `FechaVencimientoSecuencia` | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `IndicadorNotaCredito` | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `IndicadorEnvioDiferido` | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | ✗ |
| `IndicadorMontoGravado` | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✗ |
| `TipoIngresos` | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | ✗ |
| `FechaDesde/Hasta` | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ |
| `Discounts/Charges` en Items | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✗ |
| `TotalTaxes` → TaxableAmount + Rate | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✗ |
| `TotalTaxes` → EXENTO (sin Rate) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✓ |
| `AdditionalInfo` en Totals | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `AdditionalDocumentInfo` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ |
| `INFORMACION_REFERENCIA` en AddlDocInfo | ✗ | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✗ | ✗ |
| `Buyer` completo | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ |

---

## Códigos de Impuesto DGII (`ecf_codes.py`)

```python
TAX_CODES = {
    "ITBIS": {
        "18%": {"code": "ITBIS1", "rate": 18.00},
        "16%": {"code": "ITBIS2", "rate": 16.00},
        "9%":  {"code": "ITBIS3", "rate": 9.00},
        "8%":  {"code": "ITBIS4", "rate": 8.00},
        "0%":  {"code": "EXENTO", "rate": 0.00},
    },
    "Propina":  {"10%": {"code": "001", "rate": 10.00}},
    "CDT":      {"2%":  {"code": "002", "rate": 2.00}},
    "ISC": {
        "16%": {"code": "ISC", "rate": 16.00},
        "10%": {"code": "ISC", "rate": 10.00},
        "17%": {"code": "ISC", "rate": 17.00},
    },
    "ISR": {
        "2%":  {"code": "ISR", "rate": -2.00},
        "5%":  {"code": "ISR", "rate": -5.00},
        "10%": {"code": "ISR", "rate": -10.00},
        "27%": {"code": "ISR", "rate": -27.00},
    },
}
```

**Detección de retenciones**: buscar en `tax.name.lower()` las cadenas `"isr"`, `"renta"`, `"retencion"`, `"retención"`, o en `tax.tax_group_id.name.lower()` la cadena `"ret"`.

---

## `IndicadorFacturacion` — Tabla de valores

| Valor | Significado | Condición |
|---|---|---|
| `"1"` | ITBIS 18% | `tax.amount ≈ 18.0` y nombre contiene ITBIS |
| `"2"` | ITBIS 16% | `tax.amount ≈ 16.0` y nombre contiene ITBIS |
| `"3"` | ITBIS 0% (exportación) | doc_type 46, o tasa 0 no exento |
| `"4"` | Exento | doc_type 43/44/47, o nombre/grupo contiene "exento" |
| `"0"` | No facturable | fallback |

---

## Notas de Implementación Importantes

1. **No recalcular impuestos**: usar `line.price_subtotal` (ya contiene descuento aplicado por Odoo). Multiplicar por tasa solo para *agrupar* en TotalTax.

2. **`price_subtotal` vs `price_unit`**: para el JSON se envía el precio **unitario** sin impuesto. En líneas con impuesto incluido, calcular como `price_subtotal / quantity`.

3. **Conversión DOP**: si `l10n_do_currency_rate == 1.0` (moneda DOP), no hay conversión. Si es USD u otra, multiplicar por la tasa antes de formatear.

4. **Secuencia de 10 dígitos**: siempre formatear con `f"{n:010d}"`.

5. **Manejo de secuencia duplicada (error 9035)**: detectar en respuesta API y reintentar con `sequence + 1`.

6. **Fecha ISO 8601**: `invoice_date.strftime('%Y-%m-%d')` para todos los campos de fecha.

7. **Teléfonos/emails**: separar por `;`, `,` o espacio usando `re.split(r'[;, ]+', value)`.

8. **`res.branch` en Odoo 18**: si el módulo no está disponible, buscar sucursal principal directamente:
   ```python
   main_branch = self.env['res.branch'].search(
       [('company_id', '=', self.env.company.id), ('principal_branch', '=', True)], limit=1
   ) if 'res.branch' in self.env else False
   ```

9. **`l10n_do_ecf_modification_code`**: campo que debe existir en `account.move` (heredado de `l10n_do`). Si no existe en Odoo 18, declararlo como `fields.Char`.

10. **`l10n_do_origin_ncf`**: campo para NCF de la factura original en notas de crédito/débito. Verificar nombre exacto en el módulo `l10n_do` para Odoo 18.

---

## Orden de Implementación Sugerido

1. Copiar `ecf_codes.py` y `ecf_payload_builder.py` sin cambios (no dependen de versión Odoo).
2. Implementar modelos auxiliares: `l10n_do_municipality.py`, `res_country_state.py`, `account_tax.py`.
3. Implementar `res_company.py` y `res_partner.py` con campos extra.
4. Implementar `account_move.py`: campos, `_compute_ecf_is_electronic`, `_constrains_date_sequence`, tasa de cambio.
5. Implementar `_compute_tax_totals_ecf()` adaptado a `tax_totals` dict de Odoo 18.
6. Implementar `get_invoice_data()` completo leyendo `_compute_tax_totals_ecf()`.
7. Conectar `get_invoice_data()` → `EcfPayloadBuilder.build_payload()` → envío al API.
8. Agregar validaciones en `action_post()`.
9. Probar con cada `doc_type`: 31, 32, 33, 34, 41, 43, 44, 45, 46, 47.
