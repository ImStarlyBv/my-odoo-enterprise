# Odoo 18 — Suite de Cumplimiento Fiscal República Dominicana

Personalización de **Odoo 18 Enterprise** para el cumplimiento fiscal de la República Dominicana, con soporte completo para Comprobantes Fiscales Electrónicos (e-CF), integración con la DGII y gestión de NCF.

---

## Descripción general

Este proyecto extiende Odoo 18 con módulos customizados que permiten a empresas dominicanas operar dentro del marco normativo de la **Dirección General de Impuestos Internos (DGII)**, incluyendo la generación de e-CF, declaraciones fiscales mensuales, integración con POS y validación de RNC/Cédula.

---

## Módulos incluidos

### `l10n_do_accounting` — Contabilidad fiscal RD
Marco base para la gestión de NCF (Números de Comprobantes Fiscales) según la **Norma 06-18 de la DGII**.

- Secuencias de comprobantes fiscales por tipo de documento
- Anulaciones, notas de crédito y débito con códigos fiscales
- Clasificación de ingresos y gastos por tipo (01–06)
- Tipos de cancelación DGII
- Flag de empresa en modo producción/prueba

### `l10n_do_electronic_invoice` — Factura Electrónica (e-CF)
Generación del payload JSON para envío a la API de la DGII (DigiFact).

| Tipo | Código | Descripción |
|------|--------|-------------|
| E31  | 31 | Factura de Crédito Fiscal (B2B) |
| E32  | 32 | Factura de Consumo (B2C) |
| E33  | 33 | Nota de Débito |
| E34  | 34 | Nota de Crédito |
| E41  | 41 | Comprobante de Compras |
| E43  | 43 | Gastos Menores |
| E44  | 44 | Regímenes Especiales |
| E45  | 45 | Gubernamental |
| E46  | 46 | Exportaciones |
| E47  | 47 | Compras al Exterior |

**Flujo de envío:**
1. Factura confirmada → campos e-CF calculados
2. Usuario abre el **Asistente de Vista Previa ECF**
3. Se genera el JSON con datos de empresa, cliente, líneas, impuestos y forma de pago
4. El asistente muestra el JSON antes de enviar
5. La respuesta de la API almacena: Track ID, código de seguridad, QR y estado de validación

**Estados de validación:** `pending` → `success` / `error` / `rfce` / `skipped`

### `l10n_do_pos` — Punto de Venta Fiscal
Integración de NCF en el módulo Point of Sale de Odoo.

- Generación de secuencias fiscales desde sesiones POS
- Mapeo de métodos de pago fiscales
- Interfaz JavaScript/SCSS para el POS

### `l10n_do_rnc` — Consulta RNC / Cédula
Búsqueda automática de razón social a partir del RNC o Cédula del contribuyente.

- Validación de formato con `stdnum.do`
- Dos servicios de búsqueda configurables:
  - **DGII** — consulta gratuita nativa
  - **Jenrax** — API comercial (requiere API key)
- Previene duplicados de RNC/Cédula por empresa

### `dgii_reports` — Reportes DGII
Generación de declaraciones fiscales mensuales requeridas por la DGII.

- Períodos en formato MM/AAAA
- Estados: `draft` → `generated` → `sent`
- Detalle por tipo de comprobante, impuesto y forma de pago
- Alerta si existe un período anterior pendiente
- Asistente de regeneración de reportes

---

## Impuestos soportados

| Impuesto | Tasas |
|----------|-------|
| ITBIS (IVA) | 18%, 16%, 9%, 8%, 0% (Exento) |
| ISR (Retención) | Detectado por nombre del impuesto |

**Métodos de pago DGII:** Efectivo (1), Cheque/Transferencia (2), Tarjeta (3), Crédito (4), Bono (5), Permuta (6), Otros (8)

---

## Requisitos

- Odoo 18.0 Enterprise
- Python 3.10+
- Dependencias Python: `stdnum`, `requests`
- Módulos Odoo base: `l10n_do`, `l10n_latam_invoice_document`, `account`, `point_of_sale`

---

## Instalación

1. Clonar este repositorio en el directorio de addons de Odoo:
   ```bash
   git clone <url-del-repo> /ruta/odoo/extra-addons
   ```

2. Agregar la ruta al `odoo.conf`:
   ```ini
   addons_path = /ruta/odoo/addons,/ruta/odoo/extra-addons
   ```

3. Actualizar la lista de aplicaciones en Odoo e instalar los módulos en este orden:
   1. `l10n_do_accounting`
   2. `l10n_do_electronic_invoice`
   3. `l10n_do_rnc`
   4. `l10n_do_pos`
   5. `dgii_reports`

---

## Configuración inicial

1. **Empresa:** Configurar RNC, dirección y municipio DGII en `Ajustes > Empresa`
2. **Modo producción:** Activar el flag `is_live` en la empresa cuando esté listo para producción
3. **Diarios fiscales:** Asignar tipo de NCF a cada diario contable
4. **RNC Lookup:** Seleccionar servicio (DGII o Jenrax) en `Ajustes > Facturación`
5. **e-CF Config:** Configurar por tipo de documento en `Contabilidad > Configuración > Tipos e-CF`

---

## Estructura del proyecto

```
extra-addons/
├── l10n_do_accounting/         # NCF base y cumplimiento fiscal
├── l10n_do_electronic_invoice/ # Generación de e-CF (JSON + DGII API)
├── l10n_do_pos/                # POS con NCF
├── l10n_do_rnc/                # Validación y consulta RNC/Cédula
├── dgii_reports/               # Declaraciones fiscales DGII
├── account_accountant/         # Contabilidad avanzada (Enterprise)
├── mail_enterprise/            # Chatter Enterprise
└── web_enterprise/             # UI Enterprise
```

---

## Normativa de referencia

- Norma 06-18 DGII — Comprobantes Fiscales Electrónicos
- Tipos de e-CF: E31–E47 según catálogo DGII
- Formatos de RNC y Cédula según estándar dominicano

---

## Licencia

Los módulos `l10n_do_*`, `dgii_reports` y `l10n_do_pos` son desarrollos propios sujetos a los términos definidos por el propietario del repositorio.

Los módulos `account_accountant`, `mail_enterprise` y `web_enterprise` están sujetos a la licencia **OEEL-1** de Odoo S.A.
