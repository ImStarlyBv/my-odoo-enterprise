# Plan de Implementación: Fusión de l10n_do_accounting + l10n_do_accounting_v2

## Objetivo

Habilitar que `l10n_do_pos` pueda crear y enviar facturación electrónica (e-CF) desde POS,
incorporando al módulo base únicamente lo necesario del v2 para ese fin.
**No se porta lógica del v2 que ya exista en el módulo base o que no sea requerida para POS + e-CF.**

---

## Contexto y diagnóstico

### Módulo base: `l10n_do_accounting` (18.0.1.0.4)
- Usa la infraestructura estándar de Odoo: `l10n_latam.document.type`
- Gestiona NCF a través de `l10n_do_fiscal_number` en `account.move`
- Incluye soporte para e-CF (factura electrónica), monkey patch de `_compute_name`
- Sin soporte para POS (no tiene modelos de secuencia propia)

### Módulo a absorber: `l10n_do_accounting_v2` (16.0.2.2.9)
- Usa modelos propios: `account.fiscal.type` y `account.fiscal.sequence`
- Gestiona NCF a través de `fiscal_type_id` + `fiscal_sequence_id` en `account.move`
- Compatible con `l10n_do_pos` gracias a los modelos propios
- Incluye controlador web para validación RNC/cédula contra DGII
- Sin soporte e-CF

### Por qué es compatible con POS
`l10n_do_pos` depende de `account.fiscal.type` y `account.fiscal.sequence` (modelos del v2).
El módulo base no los tiene, por eso no es compatible con POS actualmente.

---

## Arquitectura de la fusión

**Estrategia elegida:** Mantener el enfoque `l10n_latam` del módulo base como eje principal
para la facturación estándar, e incorporar los modelos propios del v2 como capa adicional
que los convierte en compatibles con POS. Ambos enfoques coexisten dentro del mismo módulo.

```
l10n_do_accounting (fusionado)
├── Infraestructura l10n_latam (original)       ← facturación estándar (18.0)
├── account.fiscal.type  (nuevo, del v2)         ← requerido por l10n_do_pos
├── account.fiscal.sequence  (nuevo, del v2)     ← requerido por l10n_do_pos
├── Controlador web DGII  (nuevo, del v2)        ← validación RNC/cédula pública
└── Campos adicionales en account.move (del v2) ← campos POS y validaciones extra
```

---

## Inventario de cambios por archivo

### FASE 1 — Nuevos modelos (del v2)

#### 1.1 `models/account_fiscal_type.py` (NUEVO)
- Crear modelo `account.fiscal.type` completo desde `l10n_do_accounting_v2/models/account_fiscal_sequence.py` (líneas 373–502)
- Campos: `name`, `active`, `sequence`, `prefix`, `padding`, `type`, `journal_type`, `fiscal_position_id`, `journal_id`, `assigned_sequence`, `requires_document`
- Métodos: `_compute_journal_type`, `check_format_fiscal_number`
- Adaptar a Odoo 18: reemplazar `company_dependent=True` si aplica

#### 1.2 `models/account_fiscal_sequence.py` (NUEVO)
- Crear modelo `account.fiscal.sequence` completo desde `l10n_do_accounting_v2/models/account_fiscal_sequence.py` (líneas 1–372)
- Incluir función helper `get_l10n_do_datetime()`
- Campos: `name`, `expiration_date`, `fiscal_type_id`, `type`, `sequence_start`, `sequence_end`, `sequence_remaining`, `sequence_id`, `warning_gap`, `remaining_percentage`, `number_next_actual`, `next_fiscal_number`, `state`, `can_be_queue`, `company_id`
- Métodos: todos los `_compute_*`, `_validate_*`, `action_confirm`, `_action_confirm`, `action_cancel`, `_action_cancel`, `action_queue`, `_expire_sequences`, `_get_queued_fiscal_sequence`, `get_fiscal_number`, `_update_sequences`
- Adaptar a Odoo 18: revisar `states={}` deprecated (reemplazar con `readonly` computado o attrs)

---

### FASE 2 — Controlador web (del v2)

#### 2.1 `controllers/__init__.py` (NUEVO)
- Crear con `from . import controllers`

#### 2.2 `controllers/controllers.py` (NUEVO)
- Copiar íntegro desde `l10n_do_accounting_v2/controllers/controllers.py`
- Endpoints: `/dgii_ws` (búsqueda RNC en DGII), `/validate_rnc/` (validación RNC/cédula)
- Sin cambios de código necesarios; es compatible con Odoo 18

---

### FASE 3 — Modificaciones a modelos existentes

#### 3.1 `models/account_move.py` — Agregar campos del v2
Agregar los siguientes campos a la clase `AccountMove` existente:

| Campo nuevo | Tipo | Origen |
|---|---|---|
| `fiscal_type_id` | Many2one → `account.fiscal.type` | v2 |
| `available_fiscal_type_ids` | Many2many computed | v2 |
| `fiscal_sequence_id` | Many2one → `account.fiscal.sequence` | v2 |
| `fiscal_sequence_status` | Selection computed | v2 |
| `ncf_expiration_date` | Date (reemplaza/unifica con `l10n_do_ncf_expiration_date`) | v2 |
| `origin_out` | Char (alias de `l10n_do_origin_ncf`) | v2 |
| `is_debit_note` | Boolean | v2 |

**Nota sobre colisiones de campos:**
- `income_type` → ya existe en v1 como `l10n_do_income_type`; crear alias o renombrar
- `expense_type` → ya existe en v1 como `l10n_do_expense_type`; crear alias o renombrar
- `annulation_type` → ya existe en v1 como `l10n_do_cancellation_type`; crear alias o renombrar

**Métodos a agregar/integrar en `account_move.py`:**
- `_compute_available_fiscal_type` (nuevo, del v2)
- `_get_fiscal_domain` (nuevo, del v2)
- `_compute_is_l10n_do_fiscal_invoice` (nuevo, del v2 — renombrar si ya existe variante en v1)
- `_compute_fiscal_sequence` (nuevo, del v2)
- `_compute_fiscal_sequence_status` (nuevo, del v2)
- `_get_l10n_do_amounts` → integrar con el `_get_l10n_do_line_amounts` de v1 (ampliar, no reemplazar)
- `validate_products_export_ncf` (nuevo, del v2)

**Métodos a modificar en `account_move.py`:**
- `_post`: Agregar asignación de `ref` desde `fiscal_sequence_id.get_fiscal_number()` cuando el move viene de POS (tiene `fiscal_type_id` seteado y no tiene `l10n_latam_document_type_id`). No tocar el flujo de validación existente del v1.
- `create`: Agregar asignación de `fiscal_type_id` desde `partner_id.sale_fiscal_type_id` cuando el move viene de POS
- Agregar compute que propague `l10n_latam_document_type_id` desde `fiscal_type_id.l10n_latam_document_type_id`

**Métodos del v2 que NO se portan (ya cubiertos por el módulo base):**
- `button_cancel` / `action_invoice_cancel` → cubierto por `wizard/account_move_cancel.py`
- `refund()` / `_prepare_refund()` → cubierto por `wizard/account_move_reversal.py`
- Validaciones de notas de crédito (30 días, monto máximo) → fuera del scope de POS
- `validate_products_export_ncf` → validación de backend, no aplica en POS

#### 3.2 `models/account_journal.py` — Sin cambios mayores
- Verificar que `l10n_do_fiscal_journal` ya exista en v1; si no, portarlo del v2

#### 3.3 `models/res_partner.py` — Agregar campos del v2
Agregar a `ResPartner`:
- `sale_fiscal_type_id` → Many2one a `account.fiscal.type`
- `purchase_fiscal_type_id` → Many2one a `account.fiscal.type`
- `expense_type` → Selection (si ya está como `l10n_do_expense_type`, crear alias)

#### 3.4 `models/__init__.py` — Actualizar imports
```python
from . import account_fiscal_type      # NUEVO
from . import account_fiscal_sequence  # NUEVO
# ... resto igual
```

---

### FASE 4 — Wizards (del v2)

#### 4.1 `wizard/account_fiscal_sequence_validate_wizard.py` (NUEVO)
- Copiar desde `l10n_do_accounting_v2/wizard/account_fiscal_sequence_validate_wizard.py`
- Adaptar referencias XML ID al módulo `l10n_do_accounting`

**Wizards del v2 descartados (fuera de scope):**
- `account_invoice_cancel.py` → el módulo base ya tiene `account_move_cancel.py`
- `account_invoice_refund.py` → el módulo base ya tiene `account_move_reversal.py`
- No se porta ninguna lógica de cancelación ni refund del v2

---

### FASE 5 — Vistas XML (del v2)

#### 5.1 `views/account_fiscal_sequence_views.xml` (NUEVO)
- Copiar íntegro desde v2, actualizar módulo en XML IDs (`l10n_do_accounting_v2.` → `l10n_do_accounting.`)

#### 5.2 `views/account_move_views.xml` — Agregar campos del v2
- Agregar `fiscal_type_id`, `fiscal_sequence_id`, `fiscal_sequence_status`, `origin_out`, `is_debit_note` en los formularios existentes
- Integrar widget de estado de secuencia fiscal

#### 5.4 `views/account_journal_views.xml` — Verificar
- Si v2 agrega campos extras al journal no presentes en v1, portarlos

#### 5.5 `views/res_partner_views.xml` — Agregar campos del v2
- Agregar `sale_fiscal_type_id`, `purchase_fiscal_type_id` al formulario de partner

#### 5.6 `views/res_company_views.xml` — Verificar
- Comparar ambas versiones; integrar campos faltantes

#### 5.7 `views/account_dgii_menuitem.xml` — Agregar ítem de Fiscal Sequences
- Agregar opción de menú para gestionar `account.fiscal.sequence`
- Agregar opción de menú para gestionar `account.fiscal.type`

#### 5.8 `views/report_templates.xml` y `views/report_invoice.xml` — Comparar y unificar
- v1 tiene soporte e-CF en el reporte; v2 tiene layout diferente
- Mantener e-CF del v1, agregar variables del v2 (`fiscal_type_id`, `origin_out`, etc.)

#### 5.9 `views/layouts.xml` (NUEVO)
- Copiar desde v2; verificar si existe equivalente en v1

---

### FASE 6 — Datos y seguridad

#### 6.1 `data/account_fiscal_type_data.xml` (NUEVO)
- Copiar desde v2: tipos fiscales predefinidos (B01, B02, B03, B04, B11–B17, etc.)

#### 6.2 `data/ir_cron_data.xml` (NUEVO)
- Copiar desde v2: cron para `_expire_sequences()` (expiración automática de secuencias)

#### 6.3 `data/ir_config_parameters.xml` (NUEVO)
- Copiar desde v2: parámetro `dgii.wsmovil` para habilitar consulta web DGII

#### 6.4 `data/update_sequences.xml` (NUEVO)
- Copiar desde v2: llamada a `_update_sequences` para migrar datos

#### 6.5 `security/ir.model.access.csv` — Agregar permisos para nuevos modelos
```csv
# Agregar:
access_account_fiscal_type,account.fiscal.type,...
access_account_fiscal_sequence,account.fiscal.sequence,...
access_account_invoice_cancel,account.invoice.cancel,...
```

#### 6.6 `security/ir_rule.xml` (NUEVO)
- Copiar desde v2: reglas de registro multi-compañía para `account.fiscal.sequence`

#### 6.7 `security/res_groups.xml` — Revisar
- Unificar grupos de seguridad de ambos módulos si difieren

---

### FASE 7 — i18n / Traducciones

#### 7.1 `i18n/es_DO.po` — Fusionar
- Combinar los archivos `es_DO.po` de ambos módulos
- Agregar las entradas faltantes del v2 al archivo del v1

#### 7.2 `i18n/es.po` (NUEVO)
- Copiar desde v2

---

### FASE 8 — JavaScript / Assets

#### 8.1 `static/src/js/l10n_do_accounting.js` (NUEVO)
- Copiar desde v2 si no existe equivalente en v1

#### 8.2 `static/src/scss/style.scss` (NUEVO)
- Copiar desde v2 si no existe equivalente en v1

#### 8.3 `static/src/xml/l10n_do_accounting.xml` (NUEVO)
- Copiar templates OWL/QWeb del v2 si aplican en Odoo 18

---

### FASE 9 — Manifest `__manifest__.py`

Actualizar el manifest del módulo base:

```python
{
    "name": "Fiscal Accounting (Rep. Dominicana)",
    "version": "18.0.2.0.0",  # bumped
    "depends": [
        "l10n_latam_invoice_document",
        "l10n_do",
        "web",  # NUEVO (requerido por controller)
    ],
    "data": [
        # SEGURIDAD
        "security/ir_rule.xml",              # NUEVO
        "security/ir.model.access.csv",
        "security/res_groups.xml",
        # DATOS
        "data/l10n_latam.document.type.csv",
        "data/account_fiscal_type_data.xml", # NUEVO
        "data/ir_config_parameters.xml",     # NUEVO
        "data/ir_cron_data.xml",             # NUEVO
        "data/update_sequences.xml",         # NUEVO
        # WIZARDS
        "wizard/account_move_reversal_views.xml",
        "wizard/account_move_cancel_views.xml",
        "wizard/account_debit_note_views.xml",
        "wizard/account_fiscal_sequence_validate_wizard_views.xml",  # NUEVO
        "wizard/account_invoice_cancel_views.xml",                   # NUEVO
        "wizard/account_invoice_refund_views.xml",                   # NUEVO
        # VISTAS
        "views/res_config_settings_view.xml",
        "views/account_move_views.xml",
        "views/res_partner_views.xml",
        "views/res_company_views.xml",
        "views/account_dgii_menuitem.xml",
        "views/account_journal_views.xml",
        "views/l10n_latam_document_type_views.xml",
        "views/account_fiscal_sequence_views.xml",  # NUEVO
        "views/account_invoice_cancel_views.xml",   # NUEVO
        "views/layouts.xml",                        # NUEVO
        "views/report_templates.xml",
        "views/report_invoice.xml",
    ],
    "assets": {                                     # NUEVO bloque
        "web.assets_backend": [
            "l10n_do_accounting/static/src/js/l10n_do_accounting.js",
            "l10n_do_accounting/static/src/scss/style.scss",
        ],
        "web.assets_qweb": [
            "l10n_do_accounting/static/src/xml/l10n_do_accounting.xml",
        ],
    },
}
```

---

## Puntos de atención / Riesgos

### A. Colisión de campos en `account.move`
Los siguientes campos tienen nombres distintos en ambos módulos para el mismo dato:

| Dato | v1 (base) | v2 |
|---|---|---|
| Número fiscal | `l10n_do_fiscal_number` | `ref` (campo estándar de Odoo) |
| Fecha vencimiento | `l10n_do_ncf_expiration_date` | `ncf_expiration_date` |
| Tipo ingreso | `l10n_do_income_type` | `income_type` |
| Tipo gasto | `l10n_do_expense_type` | `expense_type` |
| Tipo anulación | `l10n_do_cancellation_type` | `annulation_type` |
| NCF origen | `l10n_do_origin_ncf` | `origin_out` |

**Decisión (confirmada):** Mantener los nombres del v1 (prefijo `l10n_do_`) como campos canónicos (almacenados en BD).
Crear campos `related` de solo lectura con los nombres del v2 para que `l10n_do_pos` los encuentre sin romper la lógica existente.

```python
# Ejemplo en account.move:
ncf_expiration_date = fields.Date(related="l10n_do_ncf_expiration_date", store=False)
income_type         = fields.Selection(related="l10n_do_income_type", store=False)
expense_type        = fields.Selection(related="l10n_do_expense_type", store=False)
annulation_type     = fields.Selection(related="l10n_do_cancellation_type", store=False)
origin_out          = fields.Char(related="l10n_do_origin_ncf", store=False)
```

El campo `ref` de Odoo ya es el número de factura estándar; el v2 lo usa como NCF.
En el módulo fusionado se mantiene `l10n_do_fiscal_number` como campo propio y
se sigue escribiendo `ref` al confirmar (igual que hace el v2) para compatibilidad POS.

### B. API de Odoo 16 vs 18
**Scope reducido (confirmado):** Solo se porta lo necesario para POS + e-CF, lo que elimina
los casos más complejos de migración de API.

Adaptaciones pendientes en el código que sí se porta:
- `states={'draft': [('readonly', False)]}` en `account.fiscal.sequence` → reemplazar con
  `readonly` computado en Python basado en `state != 'draft'`
- `invoice.number` → **descartado** (estaba en el método `refund()` que no se porta)
- `_prepare_refund` → **descartado** (wizard de v2 no se porta)
- `action_invoice_cancel` → **descartado** (wizard de v2 no se porta)

### C. Coexistencia l10n_latam + fiscal.type
**Decisión (confirmada):** Campo puente `l10n_latam_document_type_id` en `account.fiscal.type`.
El mapeo vive en la configuración de POS: el usuario asocia cada tipo fiscal al tipo latam correspondiente.

**Flujo:**
```
POS → fiscal_type_id → (puente) → l10n_latam_document_type_id → l10n_do_electronic_invoice
```

**Implementación:**
- Agregar en `account.fiscal.type`:
  ```python
  l10n_latam_document_type_id = fields.Many2one(
      'l10n_latam.document.type',
      string="Tipo de Documento e-CF",
  )
  ```
- Agregar compute/onchange en `account.move` que propague el campo latam desde `fiscal_type_id`
  cuando el move viene de POS o cuando `fiscal_type_id` está seteado
- Si `fiscal_type_id.l10n_latam_document_type_id` está vacío → no aplica FE (tipos POS sin NCF electrónico)
- `l10n_do_electronic_invoice` no requiere ningún cambio

**Dónde aparece el mapeo en la UI:**
- Formulario de `account.fiscal.type` → campo "Tipo de Documento e-CF (l10n_latam)"
- El campo se muestra en la vista de configuración de tipos fiscales (accesible desde Contabilidad > Configuración)

### D. Tests
- Mover/adaptar los tests del v2 (`test_account_fiscal_sequence.py`, `test_account_invoice.py`) al directorio `tests/` del módulo base
- Actualizar `tests/__init__.py` para incluirlos
- Asegurarse que `tests/common.py` sea compatible con ambos conjuntos de tests

---

## Orden de implementación (pasos concretos)

```
[ ] PASO 1:  Crear models/account_fiscal_type.py
             - Modelo account.fiscal.type con campo puente l10n_latam_document_type_id
             - Adaptar states={} a Odoo 18

[ ] PASO 2:  Crear models/account_fiscal_sequence.py
             - Modelo account.fiscal.sequence completo
             - Adaptar states={} a Odoo 18 (readonly computado por state)

[ ] PASO 3:  Actualizar models/__init__.py
             - Agregar imports de account_fiscal_type y account_fiscal_sequence

[ ] PASO 4:  Crear controllers/__init__.py y controllers/controllers.py
             - Copiar íntegro del v2, sin cambios

[ ] PASO 5:  Modificar models/account_move.py — campos nuevos
             - Agregar fiscal_type_id, fiscal_sequence_id, fiscal_sequence_status
             - Agregar campos related de compatibilidad POS (ncf_expiration_date, etc.)
             - Agregar compute que propague l10n_latam_document_type_id desde fiscal_type_id

[ ] PASO 6:  Modificar models/account_move.py — lógica POS en _post y create
             - En _post: asignar ref desde fiscal_sequence_id.get_fiscal_number() si viene de POS
             - En create: asignar fiscal_type_id desde partner_id.sale_fiscal_type_id si POS

[ ] PASO 7:  Modificar models/res_partner.py
             - Agregar sale_fiscal_type_id y purchase_fiscal_type_id

[ ] PASO 8:  Crear wizard/account_fiscal_sequence_validate_wizard.py y su vista XML
             - Adaptar XML IDs al módulo l10n_do_accounting

[ ] PASO 9:  Crear views/account_fiscal_sequence_views.xml
             - Vistas list/form para account.fiscal.sequence y account.fiscal.type
             - Incluir campo l10n_latam_document_type_id en el form de fiscal.type

[ ] PASO 10: Modificar views/account_move_views.xml
             - Agregar fiscal_type_id, fiscal_sequence_id, fiscal_sequence_status

[ ] PASO 11: Modificar views/res_partner_views.xml
             - Agregar sale_fiscal_type_id, purchase_fiscal_type_id

[ ] PASO 12: Modificar views/account_dgii_menuitem.xml
             - Agregar acciones de menú para Tipos Fiscales y Secuencias Fiscales

[ ] PASO 13: Crear data/account_fiscal_type_data.xml
             - Tipos fiscales predefinidos (B01–B17, E31–E47)

[ ] PASO 14: Crear data/ir_cron_data.xml y data/ir_config_parameters.xml

[ ] PASO 15: Actualizar security/ir.model.access.csv e ir_rule.xml

[ ] PASO 16: Actualizar __manifest__.py completo

[ ] PASO 17: Instalar en entorno de prueba y verificar que l10n_do_pos funcione
```

---

## Archivos afectados — Resumen

| Archivo | Acción | Notas |
|---|---|---|
| `__manifest__.py` | Modificar | Nuevas deps, datos, vistas |
| `__init__.py` | Sin cambio | |
| `controllers/__init__.py` | Crear | Del v2, sin cambios |
| `controllers/controllers.py` | Crear | Del v2, sin cambios |
| `models/__init__.py` | Modificar | 2 imports nuevos |
| `models/account_fiscal_type.py` | Crear | Del v2 + campo puente latam |
| `models/account_fiscal_sequence.py` | Crear | Del v2, adaptado a Odoo 18 |
| `models/account_move.py` | Modificar | Campos + lógica POS en _post/create |
| `models/account_journal.py` | Sin cambio | `l10n_do_fiscal_journal` ya existe |
| `models/res_partner.py` | Modificar | sale/purchase_fiscal_type_id |
| `models/res_company.py` | Sin cambio | |
| `models/monkey_patch.py` | Sin cambio | |
| `wizard/account_fiscal_sequence_validate_wizard.py` | Crear | Del v2 |
| `wizard/account_fiscal_sequence_validate_wizard_views.xml` | Crear | Del v2 |
| `wizard/__init__.py` | Modificar | 1 import nuevo |
| `wizard/account_invoice_cancel.py` | ~~Descartar~~ | Ya existe account_move_cancel.py |
| `wizard/account_invoice_refund.py` | ~~Descartar~~ | Ya existe account_move_reversal.py |
| `views/account_fiscal_sequence_views.xml` | Crear | Incluye campo puente en fiscal.type |
| `views/account_move_views.xml` | Modificar | fiscal_type_id, fiscal_sequence_status |
| `views/res_partner_views.xml` | Modificar | sale/purchase_fiscal_type_id |
| `views/account_dgii_menuitem.xml` | Modificar | Menús Tipos y Secuencias Fiscales |
| `views/account_journal_views.xml` | Sin cambio | |
| `views/res_company_views.xml` | Sin cambio | |
| `views/layouts.xml` | ~~Descartar~~ | Layout del v2 no aplica en 18 |
| `views/report_templates.xml` | Sin cambio | |
| `views/report_invoice.xml` | Sin cambio | |
| `data/account_fiscal_type_data.xml` | Crear | Tipos B01–B17, E31–E47 |
| `data/ir_cron_data.xml` | Crear | Cron expiración secuencias |
| `data/ir_config_parameters.xml` | Crear | Param dgii.wsmovil |
| `data/update_sequences.xml` | ~~Descartar~~ | Solo relevante para migración desde v2 |
| `security/ir.model.access.csv` | Modificar | Permisos fiscal.type y fiscal.sequence |
| `security/ir_rule.xml` | Crear | Multi-compañía fiscal.sequence |
| `security/res_groups.xml` | Sin cambio | |
| `i18n/es_DO.po` | Sin cambio | Los strings nuevos son en inglés por ahora |
| `static/src/*` | ~~Descartar~~ | JS del v2 es para Odoo 16, no compatible con 18 |
