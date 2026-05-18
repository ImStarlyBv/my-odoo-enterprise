# TODO — `l10n_do_pos` Refactored (Odoo 18)

> Leyenda: `[ ]` pendiente · `[~]` en progreso · `[x]` completado · `[!]` bloqueado

---

## FASE 1 — Base Fiscal NCF (MVP)

### 1.1 Limpieza del módulo existente
- [x] Eliminar `models/account_fiscal_type.py` y referencias a `account.fiscal.sequence`
- [x] Eliminar todos los imports de `account.fiscal.type` / `account.fiscal.sequence` en `pos_order.py`, `pos_session.py`
- [x] Eliminar `pos.order.ncf.log` model y referencias
- [x] Eliminar `get_next_fiscal_sequence()` del backend
- [x] Limpiar `__manifest__.py`: versión actualizada a `18.0.1.0.0`
- [x] Limpiar `__init__.py` de models
- [x] Eliminar `data/data.xml` de referencias a `default_pos_partner` antigua (recrear limpia)
- [x] Eliminar JS legacy: `PartnerListScreen.js`, `OrderReceipt.js`, `SetFiscalTypeButton.js`, referencias a `fiscal_type` en `models.js`

### 1.2 Backend — `pos.config`
- [x] Agregar campo computed `l10n_do_is_fiscal` (detecta si el diario tiene `l10n_do_document_type_ids`)
- [x] Agregar campo `l10n_do_default_consumer_partner_id` (Many2one `res.partner`)
- [x] Agregar campo `l10n_do_allow_vendor_ncf` (Boolean, default False)
- [x] Agregar campo `l10n_do_vendor_ncf_journal_id` (Many2one `account.journal`)
- [x] Agregar campos `l10n_do_order_history_type` / `l10n_do_order_history_days`
- [x] Agregar constraint: si `allow_vendor_ncf` es True, `vendor_ncf_journal_id` es requerido
- [x] Exponer `l10n_do_is_fiscal` y `l10n_do_default_consumer_partner_id` via `_load_pos_data_fields`

### 1.3 Backend — `l10n_latam_document_type` (pos.load.mixin)
- [x] Heredar `pos.load.mixin` + `l10n_latam.document.type`
- [x] Implementar `_load_pos_data_domain`: filtrar por tipos del diario del POS config
- [x] Implementar `_load_pos_data_fields`: id, name, doc_code_prefix, l10n_do_ncf_type, is_vat_required, internal_type
- [x] Agregar protección en `write()`: no archivar tipo si hay sesión POS activa con ese tipo

### 1.4 Backend — `pos.order`
- [x] Eliminar campos `ncf`, `ncf_origin_out`, `ncf_expiration_date`, `fiscal_type_id`, `fiscal_sequence_id`, `is_used_in_order`
- [x] Agregar campo `l10n_latam_document_type_id` (Many2one `l10n_latam.document.type`)
- [x] Agregar campo `l10n_do_fiscal_number` (Char, copy=False)
- [x] Agregar campo `l10n_do_origin_ncf` (Char, copy=False) — NCF de la orden que afecta
- [x] Agregar campo `l10n_do_ncf_expiration_date` (Date)
- [x] Implementar `_prepare_invoice_vals()`: pasar `l10n_latam_document_type_id`, `l10n_do_origin_ncf`, `l10n_latam_manual_document_number = False`
- [x] Implementar `_process_saved_order()`: forzar `to_invoice = True` si es POS fiscal
- [x] Implementar `_finalize_fiscal_order()`: crear factura sincrónicamente y leer NCF de vuelta
- [x] Implementar `get_credit_note(ncf)`: buscar NC por NCF
- [x] Implementar `get_credit_notes(partner_id)`: listar NCs disponibles del cliente
- [ ] Implementar `register_vendor_ncf(vendor_data)`: crear borrador `account.move` tipo `in_invoice` (Fase 3)
- [x] Sobrescribir `search_paid_order_ids()`: filtrar por NCF y límite de días en POS fiscal

### 1.5 Backend — `pos.session`
- [x] Agregar `l10n_latam.document.type` a `_load_pos_data_models()`
- [x] Sobrescribir `_create_invoice_receivable_lines()`: retornar vacío si POS fiscal
- [x] Sobrescribir `_create_bank_payment_moves()`: retornar vacío si POS fiscal
- [x] Sobrescribir `_create_cash_statement_lines_and_cash_move_lines()`: retornar vacío si POS fiscal

### 1.6 Backend — `pos.payment`
- [x] Sobrescribir `_create_payment_moves()`: crear `account.payment` por pago (efectivo, banco, NC)
- [x] Implementar `_get_payment_values(payment)`: construir vals del `account.payment`
- [x] Manejar pagos NC: vincular `account.move` de NC existente

### 1.7 Backend — `pos.payment_method`
- [x] Agregar campo `is_credit_note` (Boolean)
- [x] Agregar a `_load_pos_data_fields()`: exponer `is_credit_note`
- [x] Agregar constraint: `is_credit_note` requiere `split_transactions = True` y sin `journal_id`

### 1.8 Backend — `account.move`
- [x] Sobrescribir `button_cancel()`: bloquear si vinculada a sesión POS abierta
- [x] Sobrescribir `button_draft()`: bloquear si vinculada a sesión POS abierta

### 1.9 Backend — `res.partner`
- [x] Exponer en `_load_pos_data_fields()`: `vat`, `l10n_do_dgii_tax_payer_type`
- [x] Proteger partner consumidor por defecto de eliminación (`unlink()`)

### 1.10 Backend — `res.config.settings`
- [x] Exponer `l10n_do_is_fiscal` (related de `pos_config_id`)
- [x] Exponer `l10n_do_default_consumer_partner_id` (related, readonly=False)
- [x] Exponer `l10n_do_allow_vendor_ncf` (related, readonly=False)
- [x] Exponer `l10n_do_vendor_ncf_journal_id` (related, readonly=False)
- [x] Exponer `l10n_do_order_history_type` / `l10n_do_order_history_days`

### 1.11 Datos iniciales
- [x] Record `res.partner` id=`default_pos_partner` (Cliente de Consumo)
- [x] Record `pos.payment.method` id=`credit_note` (Nota de Crédito, split_transactions=True, is_credit_note=True)
- [x] `post_init_hook` en `__init__.py`: asignar `default_consumer_partner_id` al POS principal si existe

### 1.12 Seguridad
- [x] Actualizar `ir.model.access.csv` (eliminar accesos de modelos eliminados)
- [x] Revisar `ir_rule.xml` (eliminar reglas obsoletas)
- [x] Actualizar vistas backend: `pos_order_views.xml` (campos NCF nuevos, eliminar vistas ncf.log)
- [x] Actualizar vistas backend: `res_config_settings_views.xml` (campos nuevos, eliminar obsoletos)

---

## FASE 1 — Frontend (JS/XML)

### 1.13 `models.js` — PosStore patch
- [x] `processServerData()`: cargar `document_types` desde `l10n_latam.document.type`
- [x] `get_doc_type_by_id(id)`: buscar tipo por ID
- [x] `get_doc_type_by_prefix(prefix)`: buscar tipo por `doc_code_prefix` (B02, E32, B04, etc.)
- [x] `get_default_doc_type()`: retornar tipo `consumer` por defecto
- [x] `isCreditNoteMode()`: detectar si orden actual es devolución con NC
- [x] `get_credit_note_payment_method()`: buscar método `is_credit_note`
- [x] `get_credit_note(ncf)`: llamada RPC a `pos.order.get_credit_note`
- [x] `get_credit_notes(partner_id)`: llamada RPC a `pos.order.get_credit_notes`

### 1.14 `models.js` — PosOrder patch
- [x] `setup()`: inicializar `l10n_latam_document_type_id`, `l10n_do_fiscal_number`, `l10n_do_origin_ncf`
- [x] `set_document_type(doc_type)`: asignar tipo + aplicar `fiscal_position_id` si tiene
- [x] `get_document_type()`: getter del tipo actual
- [x] `set_partner()`: al cambiar cliente, auto-seleccionar tipo según `l10n_do_dgii_tax_payer_type`
- [x] `set_l10n_do_fiscal_data(data)`: recibir NCF, vencimiento, tipo desde backend
- [x] `set_origin_ncf(order)`: asignar `l10n_do_origin_ncf` desde orden original
- [x] `export_for_printing()`: incluir datos fiscales en datos del recibo
- [x] `_isRefundAndSaleOrder()`: alias de `_isRefundOrder()` para compatibilidad

### 1.15 `models.js` — PosPayment patch
- [x] `setup()`: inicializar `credit_note_ncf`, `credit_note_partner_id`
- [x] `set_credit_note_data(ncf, partner_id)`: setter

### 1.16 `models.js` — PosOrderline patch
- [x] `getDisplayData()`: incluir `l10n_do_itbis` para el recibo
- [x] `get_itbis()`: calcular ITBIS de la línea desde `taxesData` (grupo "ITBIS")

### 1.17 `SetDocumentTypeButton.js` + XML
- [x] Crear componente `SetDocumentTypeButton`
- [x] `onClick()`: mostrar `SelectionPopup` con tipos `internal_type = 'invoice'`
- [x] Mostrar nombre del tipo actual (o "Seleccionar Comprobante")
- [x] Si tipo requiere RNC y cliente no tiene: abrir popup para ingresar RNC o buscar cliente
- [x] Validar RNC (9 dígitos) / Cédula (11 dígitos) en el popup

### 1.18 `PaymentScreen.js`
- [x] Registrar `SetDocumentTypeButton` en `PaymentScreen.components`
- [x] `validateOrder()`: implementar todas las validaciones del §7 del plan
- [x] `_finalizeValidation()`: llamar `_finalize_fiscal_order()` RPC, recuperar NCF, almacenar en orden
- [x] `addNewPaymentLine()`: interceptar `is_credit_note`, buscar NC disponible del cliente
- [x] `updateSelectedPaymentline()`: bloquear edición de línea NC
- [x] `analyze_payment_methods()`: validar restricciones de combinación de métodos

### 1.19 `TicketScreen.js`
- [x] `onDoRefund()`: validar NCF, buscar B04/E34, verificar método NC configurado
- [x] `postRefund()`: asignar doc type B04/E34, NCF origen, limpiar ITBIS si >30 días
- [x] `_getSearchFields()`: agregar campo "NCF" para búsqueda en historial
- [x] `_returnAllOrder()`: seleccionar todas las líneas para devolución

### 1.20 `Chrome.js`
- [x] `get firstScreen()`: si modo NC → ir directo a `PaymentScreen`

### 1.21 `OrderReceipt.xml`
- [x] Cabecera cliente: nombre, RNC/Cédula, dirección (si B01/E31 o cliente registrado)
- [x] Sección fiscal: "Autorizado por la DGII", tipo comprobante
- [x] NCF: número, fecha vencimiento, NCF afectado (si NC)
- [x] Encabezado de columnas: DESCRIPCIÓN | ITBIS | VALOR
- [x] Pie: Subtotal gravado, ITBIS por tasa (agrupado), Total

### 1.22 `PaymentScreen.xml`
- [x] Inyectar `<SetDocumentTypeButton>` después del botón de cliente
- [x] Ocultar botón "Invoice" cuando POS es fiscal (`t-if="!pos.config.l10n_do_is_fiscal"`)
- [x] Bloquear contenedor de métodos de pago en modo NC

### 1.23 `TicketScreen.xml`
- [x] Agregar columna "NCF" en la lista de órdenes (si POS fiscal)

### 1.24 `pos.scss`
- [x] Estilos para `SetDocumentTypeButton`
- [x] Estilos para sección NCF en recibo
- [x] Estilos para tipo fiscal en encabezado del recibo

---

## FASE 2 — e-CF en POS

### 2.1 Backend
- [x] `pos.order._finalize_fiscal_order()`: detectar `is_ecf_invoice`, llamar `action_send_ecf()` si módulo instalado
- [x] `pos.order.get_ecf_receipt_data(order_id)`: retornar `ecf_qr_image`, `ecf_codigo_seguridad`
- [x] Nuevo método RPC `pos.order.poll_ecf_status()`: verificar si e-CF ya fue procesado
- [x] `pos.config`: campo `l10n_do_ecf_auto_send` (Boolean, default True)

### 2.2 Frontend
- [x] `PaymentScreen._finalizeValidation()`: después de obtener NCF, si es E3x, hacer polling `poll_ecf_status()` (máx 6s, 3 intentos c/2s)
- [x] `PosOrder.set_l10n_do_fiscal_data()`: almacenar `is_ecf`, `ecf_qr_image`, `ecf_codigo_seguridad`, `ecf_pending`
- [x] `PosOrder.set_ecf_data()`: actualizar solo los campos QR tras polling exitoso
- [x] `OrderReceipt.xml`: sección e-CF condicional con QR image (base64) y código de seguridad
- [x] Mostrar indicador visual E3x vs B-prefix en `SetDocumentTypeButton` (badge + icono)
- [x] Toast/alerta si e-CF está pendiente de procesamiento en DGII

---

## FASE 3 — NCF Proveedor desde POS

### 3.1 Backend
- [x] `pos.order.register_vendor_ncf(vendor_data)`: crear `account.move` tipo `in_invoice` en borrador
- [x] Campo `l10n_do_pos_vendor_ncf` en `account.move` para identificar facturas creadas desde POS
- [x] `pos.config`: campo `l10n_do_vendor_ncf_journal_id` ✓ (ya existe en 1.2)
- [x] `res.config.settings`: exponer campo de diario proveedor ✓ (ya existe en 1.10)

### 3.2 Frontend
- [x] Crear `VendorNcfButton.js` + XML
- [x] Visible solo si `pos.config.l10n_do_allow_vendor_ncf = True`
- [x] Popup campos: NCF (con validación B01/E31 formato), RNC Proveedor, Monto
- [x] Buscar proveedor por RNC en el backend al crear la factura
- [x] Llamada RPC a `register_vendor_ncf()` con los datos
- [x] Mensaje de éxito + código de la factura borrador creada

### 3.3 Vista backend
- [x] `views/pos_order_views.xml`: agregar columna NCF en listado de órdenes POS ✓ (hecho en 1.12)
- [x] Vista/menú en Contabilidad para ver NCF proveedor registrados desde POS (`account_vendor_ncf_views.xml`)

---

## FASE 4 — Pulido y QA

### 4.1 Traducciones
- [ ] Completar `i18n/es_DO.po` con todas las cadenas nuevas
- [ ] Revisar strings en XML y JS para que pasen por `_t()`

### 4.2 Pruebas backend
- [ ] Test: venta B02 sin cliente → usa partner consumidor, asigna NCF correcto
- [ ] Test: venta B01 con cliente sin RNC → debe fallar la validación
- [ ] Test: venta B01 con cliente con RNC → factura con B01
- [ ] Test: devolución B04 desde TicketScreen → NC correcta
- [ ] Test: NC como método de pago → `account.move` NC marcada como pagada
- [ ] Test: cierre de sesión → no se duplican asientos

### 4.3 Pruebas manuales frontend
- [ ] Escenario B02 consumidor: venta completa → recibo con NCF
- [ ] Escenario B01 crédito fiscal: con RNC → recibo con RNC cliente
- [ ] Escenario B14 sin ITBIS: posición fiscal aplicada correctamente
- [ ] Escenario devolución B04 < 30 días: ITBIS correcto
- [ ] Escenario devolución B04 > 30 días: sin ITBIS
- [ ] Escenario pago con NC: NC aparece como línea, saldo se actualiza
- [ ] Escenario venta > 250k sin cliente: bloqueado
- [ ] Escenario e-CF E32: recibo con QR (si módulo instalado)

### 4.4 Documentación
- [x] Actualizar `README.rst` con instrucciones de instalación, configuración y uso por cajero
- [x] Documentar campos de `pos.config` con `help=` strings ✓ (ya estaban completos)
- [x] Comentar métodos no obvios (por qué se vacían los asientos de cierre, etc.) ✓ (hecho en los modelos)

### 4.5 Manifest y packaging
- [x] Actualizar versión a `18.0.1.0.0`
- [x] Listar assets explícitamente en `__manifest__.py` (orden garantizado: models.js → botones → pantallas → XML)
- [x] `post_init_hook` revisado: eliminar context key obsoleto de Odoo 15, agregar guard contra duplicados en `payment_method_ids`
- [x] Instalación sin `l10n_do_electronic_invoice`: segura — uso de `_l10n_do_ecf_module_installed()`, `getattr` con defaults y `hasattr` en toda la lógica ECF
- [x] Instalación con `l10n_do_electronic_invoice`: QR visible — `_read_ecf_data()` lee `ecf_qr_image` y `ecf_codigo_seguridad`; polling hasta 3 intentos antes de mostrar advertencia

---

## Notas Técnicas Importantes

### Sobre `l10n_latam_manual_document_number`
Las facturas creadas desde POS deben tener `l10n_latam_manual_document_number = False`
para que la secuencia del diario asigne el NCF automáticamente. Solo las facturas de
proveedor (registro manual B01/E31) usan `manual = True`.

### Sobre el timing del NCF en el recibo
`_finalize_fiscal_order()` se llama en `_finalizeValidation()` DESPUÉS de `super`
(que guarda la orden al servidor y crea la factura vía `_process_saved_order`).
El NCF ya está asignado en la `account.move` confirmada. Se lee de vuelta y
se almacena en la orden local. Owl re-renderiza el recibo reactivamente.
`ui.block()` antes de super y `ui.unblock()` en finally evitan doble click.

### Sobre tipos E3x sin `l10n_do_electronic_invoice`
Si la empresa tiene configurados tipos E3x en el diario pero no tiene instalado
`l10n_do_electronic_invoice`, los tipos E3x serán visibles en el POS pero la
factura se creará sin envío a DGII (como si fuera contingencia). Se debe mostrar
advertencia al administrador en la configuración del POS.

### Sobre el método de pago "Nota de Crédito"
El método NC no tiene diario. El pago se registra vinculando directamente la
`account.move` de la NC existente a la nueva factura mediante conciliación.
El monto residual de la NC se actualiza al cerrar sesión.
