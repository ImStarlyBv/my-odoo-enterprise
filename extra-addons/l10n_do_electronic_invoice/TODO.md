# TODO: Automatización ECF — Odoo → api.ecf-software.online

**Objetivo:** Que n8n cree facturas de prueba en Odoo (E31–E47), el módulo genere
el JSON, lo envíe a la API automáticamente, y guarde la respuesta en la factura.
Sin intervención manual.

**API base:** `https://api.ecf-software.online`  
**Autenticación:** `Authorization: Bearer <apiKey>` en todos los endpoints excepto `/health`

---

## Referencia rápida: endpoints relevantes

| Método | Ruta | Uso |
|---|---|---|
| `GET` | `/health` | Verificar que la API está viva |
| `GET` | `/api/tenants/me` | Verificar tenant y apiKey |
| `GET` | `/api/certificates/active` | Verificar que hay certificado cargado |
| `POST` | `/api/factura/generar-comprobante` | **Enviar comprobante** |
| `GET` | `/api/comprobantes?docType=31` | Listar comprobantes por tipo |
| `GET` | `/api/comprobantes/encf/:eNCF` | Buscar por número de comprobante |
| `POST` | `/api/comprobantes/:id/consultar-estado` | Re-consultar estado en DGII |
| `POST` | `/api/webhooks/transacciones-odoo` | **Sync de vuelta a Odoo** (diseñado para esto) |
| `POST` | `/api/webhooks/consultar-transacciones` | Batch: re-consultar todos los pendientes |
| `POST` | `/api/webhooks/notifi-cert` | Verificar vencimiento del certificado |

### Respuesta de `generar-comprobante` (campos a guardar en Odoo)
```json
{
  "trackId":        "abc-123",        → ecf_track_id
  "eNCF":           "E310000000001",  → l10n_latam_document_number (o campo propio)
  "qrUrl":          "https://...",    → ecf_qr_url (texto) + ecf_qr_image (Binary, generado)
  "codigoSeguridad":"A1B2C3",         → ecf_codigo_seguridad
  "estado":         "1"               → ecf_validation_status
}
```
> `fechaFirma` viene del webhook `/transacciones-odoo` (no de `generar-comprobante`) → `ecf_fecha_firma`

> Para E32 < 250,000 DOP: `trackId = "RFCE-{eNCF}"` y `estado = ""` (no pasa por DGII).

### Códigos DGII (`estado`)
| Código | Significado |
|---|---|
| `"1"` | Aceptado |
| `"2"` | Rechazado |
| `"3"` | En Proceso |
| `"4"` | Aceptado Condicional |
| `"0"` | No encontrado |

---

## Bloque 1: Campos nuevos en `account.move` ✅

El módulo ya tiene `ecf_validation_status`, `ecf_api_message`, `ecf_qr_code`.
Faltan campos para la respuesta completa de la API.

- [x] **1.1** Agregar en `models/account_move.py`:
  - `ecf_track_id` — Char, readonly (trackId de DGII)
  - `ecf_codigo_seguridad` — Char, readonly (primeros 6 chars del SignatureValue)
  - `ecf_fecha_firma` — Datetime, readonly (viene de `/transacciones-odoo`)
  - `ecf_qr_url` — Char, readonly (URL de verificación DGII)
  - `ecf_qr_image` — Binary, readonly (imagen PNG del QR, generada desde `ecf_qr_url`)
  - `ecf_qr_code` renombrado a `ecf_qr_url` (Text→Char)
  - `ecf_validation_status` ampliado: `'3'` En Proceso, `'4'` Aceptado Condicional, `'rfce'` RFCE sin DGII

- [x] **1.2** Agregar en `res.company`:
  - `ecf_api_key` — Char, password (Bearer token de la API)
  - `ecf_api_url` — Char, default `https://api.ecf-software.online`
  - `ecf_auto_send` — Boolean, default True (anticipado del Bloque 3.2)

- [x] **1.3** Actualizar vistas:
  - `account_move_views.xml`: `ecf_track_id`, `ecf_codigo_seguridad`, `ecf_fecha_firma` en "Otra Info"; `ecf_qr_image` como widget image (solo si tiene valor)
  - `res_company_views.xml`: `ecf_api_url`, `ecf_api_key`, `ecf_auto_send` en "Configuración de Envío"

---

## Bloque 2: Implementar el envío desde Odoo ✅

El módulo genera el JSON (`_build_ecf_payload()`). Falta enviarlo.

- [x] **2.1** Implementar `action_send_ecf()` en `models/account_move.py`:
  ```python
  def action_send_ecf(self):
      payload = self._build_ecf_payload()
      api_url = self.company_id.ecf_api_url
      api_key = self.company_id.ecf_api_key
      response = requests.post(
          f"{api_url}/api/factura/generar-comprobante",
          json=payload,
          headers={"Authorization": f"Bearer {api_key}"},
          timeout=30,
      )
      data = response.json()
      if response.ok:
          qr_url = data.get("qrUrl", "")
          self.write({
              "ecf_track_id": data.get("trackId"),
              "ecf_qr_url": qr_url,          # URL de verificación DGII (texto)
              "ecf_codigo_seguridad": data.get("codigoSeguridad"),
              "ecf_api_message": str(data),
              "ecf_validation_status": data.get("estado") or "rfce",
          })
          # Generar imagen QR desde la URL y guardarla en base64 → ecf_qr_image
          # (requiere librería qrcode instalada en el servidor — ver Bloque 8.1)
          if qr_url:
              self._ecf_generate_qr_image()
      else:
          self.write({
              "ecf_api_message": data.get("error", str(data)),
              "ecf_validation_status": "error",
          })
  ```
  > `_ecf_generate_qr_image()` lee `self.ecf_qr_url`, genera el PNG con la lib `qrcode`,
  > lo codifica en base64 y lo guarda en `self.ecf_qr_image`. Ver implementación en Bloque 8.2.

- [x] **2.2** Actualizar `action_send_ecf()` del wizard para llamar al método del modelo
      (wizard delega a `move_id.action_send_ecf()` y cierra el diálogo)
      Agregado botón "Enviar a DGII" en `ecf_preview_wizard_views.xml`.

- [x] **2.3** Validación E32 ≥ 250,000 DOP:
      `UserError` si doc_type='32', amount_total ≥ 250000 y partner sin VAT.

- [ ] **2.4** Probar manualmente E31 desde UI: confirmar → "Ver JSON" →
      "Enviar" → verificar que se guardan `ecf_track_id` y `codigoSeguridad`

- [x] **2.5** Botón "Ver Respuesta API" visible solo cuando `ecf_validation_status == 'error'`:

  **Por qué:** cuando falla el envío (error de conexión, dato inválido, rechazo de la API),
  el `ecf_api_message` ya tiene la respuesta cruda guardada. Sin un botón explícito el usuario
  no puede inspeccionarla sin entrar a "Otra Info", y si reenvía para capturar el error pierde
  la respuesta anterior.

  **Implementación:**

  - [x] **2.5.1** Agregar `action_view_ecf_error()` en `account_move.py`:
    ```python
    def action_view_ecf_error(self):
        self.ensure_one()
        wizard = self.env['l10n_do.ecf.error.wizard'].create({
            'move_id': self.id,
            'api_response': self.ecf_api_message or '(sin respuesta)',
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Respuesta API — %s' % (self.name or ''),
            'res_model': 'l10n_do.ecf.error.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }
    ```

  - [x] **2.5.2** Crear `wizard/ecf_error_wizard.py`:
    ```python
    class EcfErrorWizard(models.TransientModel):
        _name = 'l10n_do.ecf.error.wizard'
        _description = 'Última respuesta de la API ECF'

        move_id = fields.Many2one('account.move', readonly=True)
        api_response = fields.Text(string='Respuesta de la API', readonly=True)
    ```

  - [x] **2.5.3** Crear `wizard/ecf_error_wizard_views.xml`:
    - Formulario con `api_response` en monoespaciado (igual que el preview JSON)
    - Solo botón "Cerrar" en el footer

  - [x] **2.5.4** Agregar botón en `account_move_views.xml` (header de la factura):
    ```xml
    <button name="action_view_ecf_error"
            type="object"
            string="Ver Respuesta API"
            class="btn-danger"
            invisible="ecf_validation_status != 'error'"/>
    ```

  - [x] **2.5.5** Registrar el wizard en `__manifest__.py` → `data` y en `security/ir.model.access.csv`

---

## Bloque 3: Auto-envío al confirmar la factura

- [x] **3.0** Configuración de envío por tipo de comprobante:

  **Por qué:** algunos tipos no los emite el cliente (p. ej. E41/E47 son para registrar
  compras de proveedores en contabilidad, no se generan localmente), y en entornos de
  prueba o depuración puede convenir deshabilitar tipos concretos sin tocar el toggle
  global `ecf_auto_send`.

  - [x] **3.0.1** Crear modelo `l10n_do.ecf.doc.type.config` en `models/ecf_doc_type_config.py`:
    ```python
    class L10nDoEcfDocTypeConfig(models.Model):
        _name = 'l10n_do.ecf.doc.type.config'
        _description = 'Configuración de envío por tipo de comprobante e-CF'

        company_id = fields.Many2one('res.company', required=True, ondelete='cascade')
        doc_type = fields.Selection([
            ('31', 'E31 – Factura de Crédito Fiscal (B2B)'),
            ('32', 'E32 – Factura de Consumo (B2C)'),
            ('33', 'E33 – Nota de Débito'),
            ('34', 'E34 – Nota de Crédito'),
            ('41', 'E41 – Comprobante de Compras'),
            ('43', 'E43 – Gastos Menores'),
            ('44', 'E44 – Regímenes Especiales'),
            ('45', 'E45 – Gubernamental'),
            ('46', 'E46 – Exportaciones'),
            ('47', 'E47 – Compras al Exterior'),
        ], required=True, string='Tipo de Comprobante')
        send_to_dgii = fields.Boolean(string='Enviar a la DGII', default=True)

        _sql_constraints = [('uniq', 'UNIQUE(company_id, doc_type)',
                             'Ya existe configuración para este tipo en esta empresa.')]
    ```

  - [x] **3.0.2** Agregar a `res.company`:
    ```python
    ecf_doc_type_config_ids = fields.One2many(
        'l10n_do.ecf.doc.type.config', 'company_id',
        string='Tipos de Comprobante',
    )
    ```

  - [x] **3.0.3** Agregar helper `_ecf_should_send()` en `account.move`:
    ```python
    def _ecf_should_send(self):
        """Devuelve True si el tipo de este comprobante está habilitado para envío.
        Si no existe registro de config, se asume True (comportamiento por defecto).
        """
        self.ensure_one()
        config = self.env['l10n_do.ecf.doc.type.config'].search([
            ('company_id', '=', self.company_id.id),
            ('doc_type', '=', self._ecf_get_doc_type()),
        ], limit=1)
        return config.send_to_dgii if config else True
    ```

  - [x] **3.0.4** Usar `_ecf_should_send()` en `action_send_ecf()`:
    - Si devuelve `False`: escribir `ecf_validation_status = 'skipped'` y
      `ecf_api_message = 'Tipo deshabilitado en configuración de la empresa.'`; retornar sin llamar a la API.
    - Agregar `'skipped'` a la selection de `ecf_validation_status`.

  - [x] **3.0.5** Botón "Inicializar tipos de comprobante" en la vista de company:
    - Llama a `action_init_ecf_doc_type_config()` en `res.company`
    - Crea los 10 registros con `send_to_dgii=True` si no existen (idempotente)
    - Útil para instancias nuevas o al instalar el módulo por primera vez

  - [x] **3.0.6** Vista One2many en `res_company_views.xml`:
    - Dentro de la pestaña ECF, debajo de "Configuración de Envío"
    - Columnas: Tipo de Comprobante, Enviar a la DGII (toggle)
    - Editable inline

  - [x] **3.0.7** Registrar en `models/__init__.py`, `__manifest__.py` data y
        `security/ir.model.access.csv`

- [x] **3.1** Sobrescribir `action_post()` en `account.move`:
  ```python
  def action_post(self):
      res = super().action_post()
      if self.company_id.ecf_auto_send:
          for move in self.filtered("is_ecf_invoice"):
              if not move._ecf_should_send():
                  move.write({
                      'ecf_validation_status': 'skipped',
                      'ecf_api_message': 'Tipo deshabilitado en configuración de la empresa.',
                  })
                  continue
              try:
                  move.action_send_ecf()
              except Exception as e:
                  move.ecf_api_message = str(e)
                  move.ecf_validation_status = 'error'
      return res
  ```

- [x] **3.2** `ecf_auto_send` (Boolean, default True) en `res.company` — anticipado en Bloque 1.2

- [ ] **3.3** Probar flujo completo: crear factura → confirmar → verificar
      que el eNCF queda guardado automáticamente

---

## Bloque 4: Sync de estado de vuelta a Odoo

La API tiene un webhook específico para Odoo: `POST /api/webhooks/transacciones-odoo`.

- [ ] **4.1** Agregar botón "Re-consultar Estado DGII" en `account.move` que llame
      `POST /api/comprobantes/{id}/consultar-estado` y actualice `ecf_validation_status`

- [ ] **4.2** Implementar método `action_sync_ecf_status()`:
  - Si `ecf_track_id` empieza con `"RFCE-"`: skip (no pasa por DGII)
  - Si `ecf_validation_status == "3"` (En Proceso): re-consultar
  - Usar `POST /api/webhooks/transacciones-odoo` con `{"eNCF": self.ecf_track_id}`
    para obtener `estado`, `fechaFirma`, `codigoSeguridad`, `qrUrl`

- [ ] **4.3** Scheduled action en Odoo: cada hora re-consultar facturas
      con `ecf_validation_status = "3"` (En Proceso) usando el batch
      `POST /api/webhooks/consultar-transacciones`

---

## Bloque 5: Configurar Odoo para acceso externo (para n8n)

- [ ] **5.1** Verificar que el JSON-RPC de Odoo responde en
      `http://tu-odoo/web/dataset/call_kw`

- [ ] **5.2** Crear usuario técnico en Odoo para n8n con permisos
      de Facturación (crear/confirmar facturas)

- [ ] **5.3** Anotar los IDs necesarios (consultando desde Odoo):
  - IDs de `l10n_latam.document.type` para E31, E32, E33, E34, E41,
    E43, E44, E45, E46, E47 (campo `doc_code_prefix`)
  - ID del diario de ventas (`account.journal`)
  - ID partner de prueba B2B (con RNC) y B2C (sin RNC)
  - ID producto de prueba
  - ID impuesto ITBIS 18% e impuesto exento

---

## Bloque 6: Workflow n8n de pruebas automatizadas

Con Odoo capaz de auto-enviar al confirmar (Bloque 3 completo).

- [ ] **6.1** Crear workflow en n8n con trigger manual ("Run ECF Test Suite")

- [ ] **6.2** Nodo Set con variables globales:
  - `odoo_url`, `odoo_db`, `odoo_user`, `odoo_password`
  - `doc_type_ids`: `{E31: id, E32: id, E33: id, ...}`
  - `partner_b2b_id`, `partner_b2c_id`, `product_id`, `tax_itbis_id`
  - `journal_id`

- [ ] **6.3** Nodo autenticación XML-RPC a Odoo:
  - `POST /xmlrpc/2/common` → `authenticate` → obtener `uid`

- [ ] **6.4** Para cada tipo (E31–E47): nodos HTTP Request que:
  1. `account.move.create` — crear borrador con campos mínimos
  2. `account.move.action_post` — confirmar (dispara auto-envío)
  3. Esperar 3s → `account.move.read` — leer `ecf_validation_status`

- [ ] **6.5** Nodo final: armar reporte de resultados
  ```
  E31: ✓ Aceptado  (E310000000001)
  E32: ✓ RFCE      (E320000000001)
  E33: ✗ Error     (MISSING_ENCF)
  ...
  ```

- [ ] **6.6** Probar extremo a extremo con E31 primero, luego resto

---

## Bloque 7: Cobertura de tipos con casos especiales

- [ ] **7.1** E31 — B2B con RNC, ITBIS 18%, pago en efectivo
- [ ] **7.2** E32 — partner sin RNC, monto < 250K (path RFCE, sin DGII)
- [ ] **7.3** E32 ≥ 250K — partner sin RNC debe fallar con `INVALID_E32`; con RNC debe pasar
- [ ] **7.4** E33 Nota de Débito — requiere `l10n_do_ecf_modification_code` y NCF original
- [ ] **7.5** E34 Nota de Crédito — igual a E33 con `CodigoModificacion` diferente
- [ ] **7.6** E41 Compras — impuesto ISR negativo en líneas
- [ ] **7.7** E43 Gastos Menores — sin secuencia de vencimiento, sin ITBIS
- [ ] **7.8** E44 Regímenes Especiales — partner con RNC, ITBIS 18%
- [ ] **7.9** E45 Gubernamental — partner gubernamental
- [ ] **7.10** E46 Exportaciones — partner extranjero (`country_id != DO`), sin ITBIS
- [ ] **7.11** E47 Compras al Exterior — partner extranjero con `IdentificadorExtranjero`

---

## Bloque 8: QR y datos ECF en la impresión de factura

El QR de verificación DGII debe aparecer en el PDF impreso de la factura.

- [ ] **8.1** Agregar dependencia `qrcode` (o `python-qrcode`) en el entorno Python
      del servidor Odoo. Verificar que esté disponible con `import qrcode`.

- [ ] **8.2** Implementar método `_ecf_generate_qr_image()` en `account.move`:
  ```python
  def _ecf_generate_qr_image(self):
      import qrcode, base64
      from io import BytesIO
      qr = qrcode.make(self.ecf_qr_url)
      buffer = BytesIO()
      qr.save(buffer, format="PNG")
      self.ecf_qr_image = base64.b64encode(buffer.getvalue())
  ```
  Llamar este método justo después de guardar `ecf_qr_url` en `action_send_ecf()`.

- [ ] **8.3** Agregar bloque ECF al reporte PDF de facturas.
  Crear `report/account_invoice_ecf.xml` heredando la plantilla QWeb de facturas
  (`account.report_invoice_document`) y agregar al pie:
  ```xml
  <t t-if="o.ecf_qr_image">
    <div class="ecf-footer">
      <img t-att-src="'data:image/png;base64,' + o.ecf_qr_image.decode()"
           style="width:80px; height:80px;"/>
      <div>
        <strong>eNCF:</strong> <t t-esc="o.l10n_latam_document_number"/><br/>
        <strong>Código de Seguridad:</strong> <t t-esc="o.ecf_codigo_seguridad"/><br/>
        <strong>Fecha de Firma:</strong> <t t-esc="o.ecf_fecha_firma"/><br/>
        <strong>Estado DGII:</strong> <t t-esc="o.ecf_validation_status"/>
      </div>
    </div>
  </t>
  ```

- [ ] **8.4** Agregar la vista de reporte en `__manifest__.py` → clave `data`

- [ ] **8.5** Probar impresión PDF de una factura E31 enviada exitosamente:
  - Verificar que el QR aparece y es escaneable
  - Verificar que el QR apunta a la URL de verificación DGII correcta
  - Verificar que `fechaFirma` y `codigoSeguridad` aparecen legibles

---

## Bloque 9: Alertas de certificado

- [ ] **9.1** Cron semanal en Odoo que llame `POST /api/webhooks/notifi-cert`
      y si `warning = true` envíe un mail al usuario contable con días restantes

---

## Bloque 10: Control de secuencias NCF autorizadas por la DGII

La DGII asigna bloques de números de comprobante por tipo (ej: E31 del 1 al 500).
Cuando se agotan, hay que solicitar una nueva autorización. Sin control en Odoo,
el módulo seguiría generando NCF fuera del rango autorizado, lo cual es inválido.

### Reglas de negocio
- Si `sequence_max == 0` → sin configurar, no se aplica ninguna validación (compatible
  con instalaciones existentes que no hayan configurado el límite).
- Si `remaining == 0` → bloquear confirmación de factura con `UserError`.
- Si `0 < remaining <= warning_threshold` → permitir, pero mostrar advertencia visible
  en el formulario de la factura.

### Cómo calcular `last_used`
- Buscar en `account.move` el número más alto entre facturas `state='posted'`
  cuyo `l10n_latam_document_number` empiece con `E{doc_type}`.
- Extraer la parte numérica: `'E310000000050'[3:]` → `int('0000000050')` → `50`.
- `remaining = sequence_max - last_used`.

---

- [ ] **10.1** Agregar campos de secuencia en `models/ecf_doc_type_config.py`:

  ```python
  sequence_max = fields.Integer(
      string='Último NCF Autorizado (DGII)',
      default=0,
      help='Número más alto del bloque autorizado por la DGII. 0 = sin límite configurado.',
  )
  warning_threshold = fields.Integer(
      string='Alerta cuando queden menos de',
      default=50,
      help='Muestra advertencia en la factura cuando los comprobantes restantes caen por debajo de este número.',
  )
  last_used_sequence = fields.Integer(
      string='Último NCF usado',
      compute='_compute_sequence_stats',
      help='Número más alto emitido en facturas confirmadas de este tipo.',
  )
  remaining_sequences = fields.Integer(
      string='Comprobantes restantes',
      compute='_compute_sequence_stats',
  )
  sequence_status = fields.Selection(
      selection=[
          ('unconfigured', 'Sin configurar'),
          ('ok', 'Disponible'),
          ('low', 'Pocos disponibles'),
          ('exhausted', 'Agotado'),
      ],
      string='Estado de secuencia',
      compute='_compute_sequence_stats',
  )
  ```

- [ ] **10.2** Implementar `_compute_sequence_stats()` en `ecf_doc_type_config.py`:

  ```python
  def _compute_sequence_stats(self):
      """Lee las facturas confirmadas y calcula el estado de la secuencia NCF."""
      for config in self:
          if not config.company_id or not config.doc_type or not config.sequence_max:
              config.last_used_sequence = 0
              config.remaining_sequences = 0
              config.sequence_status = 'unconfigured'
              continue

          prefix = 'E' + config.doc_type
          # Buscar el máximo número de secuencia entre facturas confirmadas del tipo
          self.env.cr.execute("""
              SELECT COALESCE(
                  MAX(CAST(SUBSTRING(l10n_latam_document_number FROM %s) AS INTEGER)),
                  0
              )
              FROM account_move
              WHERE company_id = %s
                AND state = 'posted'
                AND l10n_latam_document_number SIMILAR TO %s
          """, (len(prefix) + 1, config.company_id.id, prefix + '[0-9]+'))
          last_used = self.env.cr.fetchone()[0] or 0

          remaining = config.sequence_max - last_used
          config.last_used_sequence = last_used
          config.remaining_sequences = max(remaining, 0)

          if remaining <= 0:
              config.sequence_status = 'exhausted'
          elif remaining <= config.warning_threshold:
              config.sequence_status = 'low'
          else:
              config.sequence_status = 'ok'
  ```

  > No se usa `store=True` — la vista de configuración es de baja frecuencia y siempre
  > necesita datos frescos del estado real de la base de datos.

- [ ] **10.3** Agregar helper `_ecf_get_sequence_config()` y `_ecf_check_sequence_limit()`
      en `account_move.py`:

  ```python
  def _ecf_get_sequence_config(self):
      """Devuelve el registro de config de secuencia para el tipo de comprobante actual."""
      self.ensure_one()
      return self.env['l10n_do.ecf.doc.type.config'].search([
          ('company_id', '=', self.company_id.id),
          ('doc_type', '=', self._ecf_get_doc_type()),
      ], limit=1)

  def _ecf_check_sequence_limit(self):
      """Verifica que quedan NCF disponibles antes de confirmar.

      Retorna (str | None): mensaje de advertencia, o None si todo está bien.
      Lanza UserError si la secuencia está agotada.
      """
      self.ensure_one()
      config = self._ecf_get_sequence_config()
      if not config or not config.sequence_max:
          return None  # sin límite configurado, no se valida

      status = config.sequence_status
      if status == 'exhausted':
          raise UserError(_(
              'No quedan comprobantes fiscales electrónicos disponibles para %s.\n'
              'Solicite una nueva autorización a la DGII antes de continuar.'
          ) % config.doc_type_label)

      if status == 'low':
          return _(
              'Advertencia: quedan solo %d comprobante(s) disponibles para %s. '
              'Solicite una nueva autorización pronto.'
          ) % (config.remaining_sequences, config.doc_type_label)

      return None
  ```

  > `doc_type_label` se agrega como campo relacionado o método de selección — ver 10.5.

- [ ] **10.4** Llamar `_ecf_check_sequence_limit()` en `action_post()` (antes del `super()`):

  ```python
  def action_post(self):
      for move in self.filtered('is_ecf_invoice'):
          warning = move._ecf_check_sequence_limit()
          # Guardar advertencia en el mensaje de seguimiento si aplica
          if warning:
              move.message_post(body=warning, message_type='comment')
      return super().action_post()
      # ... resto del auto-envío ECF (ya implementado)
  ```

  > La advertencia se registra en el chatter; no bloquea. El bloqueo solo ocurre
  > si `sequence_status == 'exhausted'` (UserError levantado antes de llegar al super).

- [ ] **10.5** Agregar campo `ecf_sequence_warning` en `account.move` para mostrar
      la advertencia en el formulario de la factura **antes de confirmar**:

  ```python
  ecf_sequence_warning = fields.Char(
      string='Advertencia de secuencia NCF',
      compute='_compute_ecf_sequence_warning',
  )

  @api.depends('l10n_latam_document_type_id', 'company_id')
  def _compute_ecf_sequence_warning(self):
      for move in self:
          if not move.is_ecf_invoice or move.state != 'draft':
              move.ecf_sequence_warning = False
              continue
          config = move._ecf_get_sequence_config()
          if not config or not config.sequence_max:
              move.ecf_sequence_warning = False
              continue
          if config.sequence_status == 'exhausted':
              move.ecf_sequence_warning = _(
                  'AGOTADO: no quedan comprobantes %s. '
                  'La factura no podrá confirmarse.'
              ) % config.doc_type
          elif config.sequence_status == 'low':
              move.ecf_sequence_warning = _(
                  'Quedan %d comprobante(s) %s. Solicite nueva autorización pronto.'
              ) % (config.remaining_sequences, config.doc_type)
          else:
              move.ecf_sequence_warning = False
  ```

- [ ] **10.6** Mostrar advertencia en `account_move_views.xml` (dentro del formulario,
      debajo del header):

  ```xml
  <!-- Advertencia de secuencia NCF -->
  <div class="alert alert-warning mb-0"
       role="alert"
       invisible="not ecf_sequence_warning or ecf_sequence_warning == ''">
      <i class="fa fa-exclamation-triangle me-1"/>
      <field name="ecf_sequence_warning" readonly="1" class="d-inline"/>
  </div>
  <!-- Bloqueo visual cuando está agotado (campo mismo texto, clase danger) -->
  ```

  > Usar dos `<div>` con `invisible` diferente si se quiere `alert-danger` para agotado
  > vs `alert-warning` para pocos. Requiere un segundo campo `ecf_sequence_exhausted`
  > booleano, o un Selection con valores 'low'/'exhausted'.

- [ ] **10.7** Actualizar vista One2many de tipos en `res_company_views.xml`:
  - Agregar columnas `sequence_max`, `warning_threshold`, `remaining_sequences`
  - Agregar columna `sequence_status` con widget `statusbar` o campo `badge`
    (verde = ok, naranja = low, rojo = exhausted)

- [ ] **10.8** Probar:
  - Configurar E31 con `sequence_max = 5`, `warning_threshold = 3`
  - Confirmar 3 facturas → verificar que aparece la advertencia en la 4ta y 5ta
  - Confirmar la 6ta → verificar que lanza `UserError`
  - Verificar que con `sequence_max = 0` no hay ninguna validación

---

## Orden de ejecución recomendado

```
Bloque 1 → Bloque 2 → Bloque 3 → Bloque 4 → Bloque 5 → Bloque 8 → Bloque 6 (solo E31) → Bloque 7 → Bloque 9 → Bloque 10
```

- No arrancar Bloque 6 hasta que Bloque 3 esté funcionando.
- Bloque 8 (QR en impresión) va antes de las pruebas masivas para que cada prueba
  ya genere el PDF correcto desde el inicio.
- Bloque 10 es independiente, se puede implementar en paralelo con cualquier otro bloque.

---

## Notas y decisiones

- **RFCE path (E32 < 250K):** la API no envía a DGII, solo registra localmente.
  `trackId` comienza con `"RFCE-"` y `estado` llega vacío. Odoo debe manejar este caso
  como válido, no como error.
- **Ambientes DGII:** la API usa `DGII_ENVIRONMENT` (CERT/PROD/test). Para pruebas
  usar CERT o un ambiente diferente. El campo `is_live` en `res.company` debería
  correlacionarse con esto.
- **apiKey nunca se devuelve:** se emite una sola vez en `POST /api/tenants`.
  Si se pierde hay que registrar un nuevo tenant o pedirla al admin de la API.
- **E33 vs E34:** la documentación de la API define E33=Nota de Débito y
  E34=Nota de Crédito. Verificar que los `doc_code_prefix` en `l10n_do_accounting`
  coincidan con esto.
