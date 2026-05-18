# Plan de Implementación — `l10n_do_pos` (Refactored para Odoo 18)

> **Estado:** Planificación  
> **Fecha:** 2026-05-17  
> **Objetivo:** Reescribir `l10n_do_pos` para que sea 100% compatible con
> `l10n_do_accounting` (estructura latam + `l10n_latam_document_type`) y
> preparado para enlazarse con `l10n_do_electronic_invoice`.

---

## 1. Contexto y Problema

### 1.1 Por qué el módulo original no sirve

El `l10n_do_pos` original fue escrito para una arquitectura anterior que mantenía
sus propios modelos `account.fiscal.type` y `account.fiscal.sequence`. Esos modelos
**no existen** en el `l10n_do_accounting` actual.

| Concepto original | Equivalente actual |
|---|---|
| `account.fiscal.type` | `l10n_latam.document.type` (campo `l10n_do_ncf_type`) |
| `account.fiscal.sequence` | Secuencia del diario (`ir.sequence`) gestionada por `l10n_do_accounting` |
| `fiscal_type_id` en orden POS | `l10n_latam_document_type_id` en orden POS |
| `ncf` generado antes de pagar | NCF asignado al confirmar `account.move` |
| `pos.order.ncf.log` | No necesario — el NCF queda en la factura |

### 1.2 Qué se conserva del módulo original (ideas, no código)

- Botón de selección de tipo de comprobante en pantalla de pago
- Auto-facturación de todas las órdenes fiscales
- Partner por defecto para consumidor final
- Método de pago "Nota de Crédito" (crédito desde NC existente)
- Validaciones DGII en frontend (RNC/Cédula, montos, ITBIS para B14/E44)
- Flujo de devolución con B04/E34
- Historial de tickets filtrado y con búsqueda por NCF
- Protección de facturas vinculadas a sesiones abiertas
- ITBIS desglosado por línea en el recibo

### 1.3 Qué es nuevo (no estaba en el módulo original)

- Soporte nativo para comprobantes electrónicos (E3x) en el POS
- QR code en recibo para e-CF (desde `ecf_qr_image` de `account.move`)
- Registro de comprobante de proveedor (B01/E31) desde POS
- Cliente por defecto configurable para E32 (consumidor electrónico)
- Indicador de tipo NCF vs e-CF en toda la UI del POS
- Integración opcional con `l10n_do_electronic_invoice` (depende si está instalado)
- Recibo DGII-compliant con todos los campos requeridos

---

## 2. Arquitectura del Nuevo Módulo

### 2.1 Dependencias

```
l10n_do_pos
├── point_of_sale          (obligatorio)
├── l10n_do_accounting     (obligatorio)
└── l10n_do_electronic_invoice  (opcional — detectado vía `ir.module.module`)
```

`l10n_do_electronic_invoice` **no va en `depends`** para no forzar su instalación.
Se detecta en runtime con `self.env['ir.module.module'].search([('name', '=', 'l10n_do_electronic_invoice'), ('state', '=', 'installed')])`.

### 2.2 Estructura de archivos

```
l10n_do_pos/
├── __init__.py
├── __manifest__.py
├── data/
│   └── pos_data.xml                    # partner consumidor, método NC
├── i18n/
│   └── es_DO.po
├── models/
│   ├── __init__.py
│   ├── pos_config.py                   # config + flag fiscal + partner defecto
│   ├── pos_order.py                    # campos NCF, doc type, vendor NCF, prepare_invoice_vals
│   ├── pos_session.py                  # carga doc types en frontend, overrides de cierre
│   ├── pos_payment.py                  # manejo de pago tipo NC
│   ├── pos_payment_method.py           # campo is_credit_note
│   ├── l10n_latam_document_type.py     # pos.load.mixin para cargar tipos en POS
│   ├── account_move.py                 # protección vs sesión abierta
│   ├── res_partner.py                  # exponer campos vat, dgii_payer_type en POS
│   └── res_config_settings.py          # campos POS en ajustes
├── security/
│   ├── ir.model.access.csv
│   └── ir_rule.xml
├── static/src/
│   ├── js/
│   │   ├── models.js                   # patch PosStore, PosOrder, PosPayment, Orderline
│   │   ├── PaymentScreen.js            # validaciones + flujo NCF/eCF
│   │   ├── TicketScreen.js             # devoluciones + búsqueda NCF
│   │   ├── Chrome.js                   # firstScreen para modo NC
│   │   └── buttons/
│   │       ├── SetDocumentTypeButton.js
│   │       └── VendorNcfButton.js      # botón para registrar NCF proveedor
│   ├── xml/
│   │   ├── OrderReceipt.xml            # recibo DGII (NCF, QR, ITBIS, datos cliente)
│   │   ├── PaymentScreen.xml           # inyectar botones, ocultar Invoice btn
│   │   ├── TicketScreen.xml            # columna NCF en historial
│   │   ├── SetDocumentTypeButton.xml
│   │   └── VendorNcfButton.xml
│   └── scss/
│       └── pos.scss
├── views/
│   ├── res_config_settings_views.xml
│   ├── pos_order_views.xml
│   └── pos_payment_method_views.xml
└── wizard/
    └── vendor_ncf_wizard.py            # opcional: wizard backend para B01/E31
```

---

## 3. Flujo Principal — Venta Fiscal

### 3.1 Detección de POS fiscal

Un POS es "fiscal" cuando su diario de facturación (`invoice_journal_id`) tiene
tipos de documento dominicanos asociados (`l10n_do_document_type_ids`). No se
necesita un campo booleano extra: se computa desde el diario.

```python
# pos.config
@api.depends('invoice_journal_id.l10n_do_document_type_ids')
def _compute_l10n_do_is_fiscal(self):
    for config in self:
        config.l10n_do_is_fiscal = bool(
            config.invoice_journal_id.l10n_do_document_type_ids
        )
```

### 3.2 Tipos de documento disponibles en el POS

Al abrir sesión, `pos.session._load_pos_data_models()` incluye
`l10n_latam.document.type`. Se filtra por:
- `country_id = DO`
- `internal_type in ('invoice', 'credit_note', 'debit_note')`
- Solo los tipos configurados en el diario de facturación del POS

```python
# l10n_latam_document_type.py (hereda pos.load.mixin)
def _load_pos_data_domain(self, data):
    config = self.env['pos.config'].browse(data['config_id'])
    doc_type_ids = config.invoice_journal_id.l10n_do_document_type_ids\
        .mapped('l10n_latam_document_type_id').ids
    return [('id', 'in', doc_type_ids)]

def _load_pos_data_fields(self, config_id):
    return [
        'id', 'name', 'doc_code_prefix',
        'l10n_do_ncf_type', 'is_vat_required',
        'internal_type',
    ]
```

### 3.3 Selección de tipo de comprobante

El `SetDocumentTypeButton` en `PaymentScreen`:
- Lista solo tipos de venta (`internal_type = 'invoice'`) para órdenes normales
- Pre-selecciona según el `l10n_do_dgii_payer_type` del cliente:
  - `taxpayer` → B01/E31 (Crédito Fiscal)
  - `non_payer` / sin cliente → B02/E32 (Consumidor)
  - `governmental` → B15/E45
  - `special` → B14/E44
- Al cambiar tipo, aplica la `fiscal_position_id` asociada al tipo de documento

### 3.4 Creación del NCF — Diferencia clave con el módulo original

**El NCF NO se pre-genera en el frontend.** Se asigna al confirmar la `account.move`.

```
Usuario paga
    └─> _finalizeValidation()
            └─> order.to_invoice = True  (siempre en POS fiscal)
                └─> _process_saved_order()
                        └─> action_pos_order_invoice()
                                └─> account.move.action_post()
                                        └─> l10n_do_accounting asigna NCF vía ir.sequence
                                                └─> NCF disponible en move.l10n_do_fiscal_number
```

Después de crear la factura, el POS lee el NCF de vuelta y lo almacena en
`pos.order.l10n_do_fiscal_number` para mostrarlo en el recibo.

```python
# pos_order.py
def _finalize_fiscal_order(self):
    """Factura inmediatamente y recupera el NCF asignado."""
    self.ensure_one()
    self.write({'to_invoice': True})
    self._generate_pos_order_invoice()
    invoice = self.account_move_ids[:1]
    if invoice:
        self.write({
            'l10n_do_fiscal_number': invoice.l10n_do_fiscal_number,
            'l10n_do_ncf_expiration_date': invoice.l10n_do_ncf_expiration_date,
            'l10n_latam_document_type_id': invoice.l10n_latam_document_type_id.id,
        })
```

**Ventaja:** Eliminamos la tabla `pos.order.ncf.log`, el riesgo de NCF huérfanos
y toda la lógica de recuperación de fallos. La secuencia la gestiona el ORM de Odoo.

### 3.5 Recibo DGII

El recibo impreso debe incluir (según normativa DGII):

**Cabecera:**
- Nombre / RNC del emisor
- Dirección del emisor
- Teléfono del emisor

**Cuerpo fiscal:**
- "Autorizado por la DGII" (si es NCF)  
- Tipo de comprobante (Crédito Fiscal, Consumo, etc.)
- Número de comprobante (NCF): `B0200000001` o `E320000000001`
- Válido hasta (fecha de vencimiento)
- Nombre y RNC/Cédula del receptor (obligatorio para B01/E31, recomendado el resto)

**Líneas:**
- Descripción, Cantidad, Precio Unitario, ITBIS, Subtotal

**Pie:**
- Subtotal sin impuestos
- ITBIS 18% (y/o 16%, 0%)
- ISC si aplica
- Total

**Solo para e-CF (E3x):**
- Código de Seguridad (`ecf_codigo_seguridad` de `account.move`)
- QR Code (`ecf_qr_image` de `account.move` — imagen base64)
- Sello electrónico (si está disponible)

---

## 4. Flujo de Devolución (B04 / E34)

```
TicketScreen → Refund
    └─> Valida: orden tiene NCF
    └─> Busca tipo B04 (NCF) o E34 (e-CF) según prefijo del NCF original
    └─> Crea orden de devolución con:
            - l10n_do_origin_ncf = NCF de la orden original
            - l10n_latam_document_type_id = B04 o E34
    └─> Si orden > 30 días: remueve ITBIS de líneas (norma DGII)
    └─> Agrega línea de pago tipo "Nota de Crédito"
    └─> Envía a PaymentScreen
```

---

## 5. Registro de Comprobante de Proveedor (B01/E31)

Feature nuevo: desde el POS se puede registrar el NCF del proveedor para un
recibo de compra, sin salir a contabilidad.

**Botón:** `VendorNcfButton` — visible solo si el POS tiene habilitado
`allow_vendor_ncf = True` en configuración.

**Flujo:**
1. Cajero recibe factura del proveedor
2. Toca el botón "Registrar NCF Proveedor"
3. Popup solicita: NCF proveedor, RNC proveedor, monto
4. Se valida formato (B01XXXXXXXX o E31XXXXXXXXXXXX)
5. Se crea un `account.move` de tipo `in_invoice` con los datos
6. La factura queda en borrador para que contabilidad la complete

**Modelos backend:**

```python
# pos_order.py
def register_vendor_ncf(self, vendor_data):
    """Crea borrador de factura de compra desde POS."""
    move = self.env['account.move'].create({
        'move_type': 'in_invoice',
        'l10n_do_fiscal_number': vendor_data['ncf'],
        'partner_id': vendor_data['partner_id'],
        'l10n_latam_document_type_id': vendor_data['doc_type_id'],
        'l10n_latam_manual_document_number': True,
        'invoice_date': fields.Date.today(),
        'journal_id': self.config_id.vendor_ncf_journal_id.id,
    })
    return {'move_id': move.id, 'name': move.name}
```

---

## 6. Integración con `l10n_do_electronic_invoice`

Cuando el módulo `l10n_do_electronic_invoice` está instalado:

### 6.1 En el backend

- `pos.order._finalize_fiscal_order()` detecta si la factura es e-CF
  (`move.is_ecf_invoice`) y ejecuta `move.action_send_ecf()` automáticamente
  (si la empresa tiene API configurada)
- El resultado (QR URL, código de seguridad) se guarda en `account.move`
- `pos.order._read_ecf_data()` lee esos campos de vuelta para el recibo

### 6.2 En el frontend

- Después de `_finalizeValidation()`, si el NCF es E3x, se hace una llamada RPC
  para verificar si el QR ya está disponible (polling breve, máx 5s)
- Si está disponible: el recibo se imprime con QR
- Si no está disponible aún: el recibo se imprime sin QR y el QR llega después
  al backend (el cliente puede solicitar reimpresión)

### 6.3 Detección en runtime

```python
# utils.py
def is_ecf_module_installed(env):
    return env['ir.module.module'].sudo().search_count([
        ('name', '=', 'l10n_do_electronic_invoice'),
        ('state', '=', 'installed'),
    ]) > 0
```

---

## 7. Validaciones Frontend (PaymentScreen)

| Condición | Bloqueo |
|---|---|
| Monto total = 0 | Bloqueo total |
| Sin tipo de comprobante | Bloqueo total |
| Tipo requiere RNC y cliente sin RNC/cédula | Bloqueo + popup para buscar/crear cliente |
| RNC distinto de 9 dígitos o Cédula distinto de 11 dígitos | Error con instrucciones |
| Venta ≥ RD$ 250,000 sin cliente identificado | Bloqueo (norma DGII) |
| B14/E44 con ITBIS o ISC en líneas | Error con instrucción de cambiar posición fiscal |
| Tipo `out_refund` con monto positivo | Error |
| Tipo `out_invoice` con monto negativo | Error |
| Líneas con cantidad 0 | Error |
| Tarjeta excede total | Error |
| Pay Later excede total | Error |
| Tarjeta + Pay Later excede total | Error |
| Tarjeta cubre 100% y hay efectivo también | Error |
| NC ya usada en esta orden | Error |
| NC sin saldo disponible | Error |
| NC de partner distinto al de la orden | Error |

---

## 8. Cierre de Sesión — Contabilización de Pagos

El cierre estándar de Odoo genera asientos combinados por método de pago.
Para POS fiscal, cada factura ya tiene su `account.payment` vinculado
(creado en el momento de pago). Por eso, al cerrar sesión se **vacían**
las estructuras de asientos del POS para no duplicar:

```python
# pos_session.py
def _create_invoice_receivable_lines(self, data):
    if self.config_id.l10n_do_is_fiscal:
        data.update({'combine_invoice_receivable_lines': {}, 'split_invoice_receivable_lines': {}})
        return data
    return super()._create_invoice_receivable_lines(data)

def _create_bank_payment_moves(self, data):
    if self.config_id.l10n_do_is_fiscal:
        data.update({'payment_method_to_receivable_lines': {}, 'payment_to_receivable_lines': {}})
        return data
    return super()._create_bank_payment_moves(data)
```

Cada `pos.payment` crea su propio `account.payment` en `_create_payment_moves()`,
separado por método de pago (efectivo, tarjeta, NC).

---

## 9. Configuración POS (Ajustes)

| Campo | Modelo | Descripción |
|---|---|---|
| `l10n_do_is_fiscal` | `pos.config` (computed) | POS tiene tipos doc RD |
| `l10n_do_default_consumer_partner_id` | `pos.config` | Partner para B02/E32 sin cliente |
| `l10n_do_allow_vendor_ncf` | `pos.config` | Habilitar botón NCF proveedor |
| `l10n_do_vendor_ncf_journal_id` | `pos.config` | Diario para facturas proveedor desde POS |
| `l10n_do_order_history_type` | `pos.config` | all / days |
| `l10n_do_order_history_days` | `pos.config` | Días de historial |

---

## 10. Checklist de Compatibilidad Odoo 18

- [ ] Usar `pos.load.mixin` (no `pos.loader`) para cargar modelos al frontend
- [ ] Usar `this.models["nombre.modelo"]` en JS (no `this.db.get_*`)
- [ ] `PosStore.processServerData()` para inicializar datos custom
- [ ] Templates OWL/XML con `t-name` usando herencia via `t-inherit`
- [ ] No usar `PartnerListScreen` ni `PartnerDetailsEdit` (no existen en 18)
- [ ] Usar `pos.editPartner()` para crear/editar clientes
- [ ] `makeAwaitable(dialog, ...)` para popups async
- [ ] `this.data.call(model, method, args)` para RPC al backend
- [ ] No usar `PosModel` global (obsoleto)

---

## 11. Fases de Implementación

### Fase 1 — Base (MVP Fiscal NCF)
> Permite hacer ventas B01, B02, B04, B14 desde POS con NCF asignado por `l10n_do_accounting`.

1. Limpiar módulo original (eliminar dependencias de `account.fiscal.type/sequence`)
2. Implementar detección de POS fiscal desde el diario
3. Cargar `l10n_latam.document.type` en el POS (`pos.load.mixin`)
4. `SetDocumentTypeButton` con selección y auto-asignación por tipo cliente
5. `pos.order`: campos NCF, doc type, `_prepare_invoice_vals`, auto-facturación
6. `pos.session`: overrides de cierre de sesión
7. `pos.payment`/`pos.payment_method`: método NC
8. `PaymentScreen`: todas las validaciones DGII
9. `TicketScreen`: flujo B04, búsqueda por NCF
10. `OrderReceipt`: recibo DGII-compliant (cabecera, NCF, ITBIS, cliente)
11. Partner consumidor final + datos iniciales

### Fase 2 — e-CF en POS
> Permite emitir E31, E32, E34 desde POS.

1. Extender `SetDocumentTypeButton` para mostrar tipos E3x
2. Ajustar validaciones para e-CF (E32 < 250k sin RNC, E31 requiere RNC)
3. Después de `action_post()`, detectar `is_ecf_invoice` y leer QR/código seguridad
4. `OrderReceipt`: sección QR + código seguridad para e-CF
5. Lógica de polling si el QR aún no está disponible

### Fase 3 — NCF Proveedor desde POS
> Cajero puede registrar B01/E31 de proveedor sin ir a contabilidad.

1. `VendorNcfButton` en POS (configurable, desactivado por defecto)
2. Popup: RNC proveedor, NCF, monto, tipo doc
3. Backend: `pos.order.register_vendor_ncf()` crea `account.move` borrador
4. Vista backend: listado de NCF proveedor registrados desde POS

### Fase 4 — Pulido y extras
> QA, traducciones, documentación, pruebas.

1. Traducciones `es_DO.po`
2. Pruebas unitarias backend (flujo de facturación, validaciones)
3. Pruebas manuales frontend (escenarios: B01, B02, B04, E32, devolución, NC como pago)
4. Ajustes de diseño del recibo (SCSS)
5. Documentación README.md

---

## 12. Decisiones de Diseño Importantes

### ¿Por qué no pre-generar el NCF en el frontend?

El módulo original pre-generaba el NCF antes de confirmar el pago para poder
imprimirlo en el recibo inmediatamente. Esto requería una tabla de log
(`pos.order.ncf.log`) para recuperarse si el pedido fallaba después.

En el nuevo diseño, **la factura se crea sincrónicamente** durante
`_finalizeValidation()` antes de imprimir el recibo. El NCF viene de la
`account.move` ya confirmada. Esto:
- Elimina NCF huérfanos (un NCF sin factura es un problema fiscal)
- Elimina la tabla de log
- Mantiene la auditoría en `account.move` (la fuente de verdad)
- Simplifica el código un 40%

El precio: `_finalizeValidation()` tarda ~500ms más (una llamada extra al servidor).
Aceptable para el caso de uso.

### ¿Por qué `l10n_do_electronic_invoice` como dependencia opcional?

No todos los comercios RD emiten e-CF. Muchos siguen usando NCF físicos (B-prefix).
Forzar la instalación de `l10n_do_electronic_invoice` agregaría requisitos
(certificados, API DGII) innecesarios para estos casos. La detección en runtime
permite que el módulo POS funcione para ambos escenarios con un solo código.

### ¿Por qué no usar `account.fiscal.type` del módulo original?

Ese modelo no existe en `l10n_do_accounting`. Recrearlo sería duplicar la lógica
que ya maneja `l10n_latam.document.type`. El campo `l10n_do_ncf_type` en ese
modelo ya clasifica: `fiscal`, `consumer`, `credit_note`, `e-fiscal`, `e-consumer`, etc.
