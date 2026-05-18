==================================
Fiscal POS — República Dominicana
==================================

:Autor: Guavana, Indexa, Iterativo SRL
:Versión: 18.0.1.0.0
:Licencia: LGPL-3
:Dependencia principal: l10n_do_accounting, point_of_sale
:Módulo opcional: l10n_do_electronic_invoice (para e-CF / comprobantes electrónicos)

Descripción
===========

Extiende el Punto de Venta de Odoo 18 para cumplir con la normativa de
comprobantes fiscales de la Dirección General de Impuestos Internos (DGII)
de la República Dominicana.

El módulo integra la generación de NCF y e-CF directamente en el flujo de
cobro del POS, sin requerir que el cajero acceda a contabilidad.

Características principales
============================

- **NCF automático**: Cada venta genera una factura con NCF asignado por
  la secuencia del diario (sin intervención manual del cajero).
- **Tipos de comprobante**: B01 Crédito Fiscal, B02 Consumidor Final,
  B14 Gubernamental, B15 Especial, B04 Nota de Crédito, y sus equivalentes
  electrónicos E3x.
- **e-CF**: Si ``l10n_do_electronic_invoice`` está instalado, el e-CF se
  envía automáticamente a la DGII al validar la orden. El QR y código de
  seguridad se muestran en el recibo.
- **Validaciones DGII**: Venta ≥ RD$250,000 requiere cliente identificado;
  B01/E31 requieren RNC/Cédula; B14 no puede tener ITBIS.
- **Notas de crédito**: Devoluciones generan B04/E34. El método de pago
  "Nota de Crédito" permite descontar NCs existentes de la venta.
- **NCF proveedor desde POS**: Botón opcional para que el cajero registre
  comprobantes de proveedores (B01/E31) como facturas borrador en
  contabilidad.
- **Recibo fiscal DGII**: Muestra nombre/RNC del cliente, tipo de
  comprobante, NCF, fecha de vencimiento, ITBIS desglosado por tasa y
  subtotales.
- **Historial de órdenes**: Filtrado por NCF; límite de días configurable.

Instalación
===========

1. Copiar el módulo en la carpeta de addons del servidor Odoo 18.
2. Activar el modo desarrollador en Odoo.
3. Ir a **Aplicaciones → Actualizar lista de aplicaciones**.
4. Buscar ``l10n_do_pos`` e instalar.

El módulo instala automáticamente:

- Un partner "Cliente de consumo" (usado en ventas B02 sin cliente identificado).
- Un método de pago "Nota de Crédito" (para aplicar NCs en ventas).
- Si existe el POS principal (``pos_config_main``), ambos registros se
  asignan a él vía ``post_init_hook``.

Configuración
=============

Ir a **Punto de venta → Configuración → Ajustes** y seleccionar el POS a configurar.

Sección **Contabilidad**:

Cliente consumidor por defecto
    Partner usado en ventas B02/E32 (consumidor final sin RNC).
    El campo solo aparece si el diario del POS tiene tipos NCF dominicanos.

Registrar NCF proveedor desde POS
    Activa el botón "NCF Proveedor" en la pantalla de pago.
    Requiere seleccionar un **Diario de compras** donde se crearán los
    borradores de facturas de proveedor.

Historial de órdenes
    Controla cuántas órdenes se muestran en el historial:

    - *Todas las órdenes*: sin límite de fecha.
    - *Por días*: solo órdenes de los últimos N días.

Enviar e-CF automáticamente
    Activo por defecto. Al validar una orden con tipo E3x, el comprobante
    electrónico se envía a la DGII sin intervención adicional.
    Requiere ``l10n_do_electronic_invoice`` instalado.

Requisito del diario de ventas
    El POS solo es fiscal (``l10n_do_is_fiscal = True``) cuando su diario
    de facturación tiene tipos de documento dominicanos configurados en
    **Contabilidad → Configuración → Diarios**.

Uso — Cajero
============

Flujo de venta normal (B02 consumidor)
---------------------------------------

1. Agregar productos a la orden.
2. Ir a **Pago**.
3. El botón **Seleccionar Comprobante** muestra el tipo seleccionado
   automáticamente (B02 por defecto, o el que corresponda al cliente).
4. Seleccionar método de pago y validar.
5. El sistema genera la factura, asigna el NCF y lo muestra en el recibo.

Flujo de venta B01 (crédito fiscal)
-------------------------------------

1. Seleccionar el cliente con RNC registrado (o asignar uno).
   El tipo cambia automáticamente a B01 según el tipo de contribuyente.
2. Si el tipo seleccionado requiere RNC y el cliente no lo tiene, el sistema
   solicitará ingresar o buscar el RNC antes de continuar.
3. Validar el pago — el recibo incluirá RNC/razón social del cliente.

Devoluciones (B04 / E34)
--------------------------

1. En **Historial de órdenes**, seleccionar la orden original.
2. Pulsar **Devolución**.
3. El sistema valida que la orden tenga NCF y busca el tipo B04/E34
   disponible en el diario.
4. Si la devolución es posterior a 30 días, el ITBIS se elimina de las
   líneas devueltas (normativa DGII).
5. El cajero puede aplicar la NC resultante como método de pago en futuras
   ventas seleccionando **Nota de Crédito** al cobrar.

NCF Proveedor desde POS
-------------------------

*(Requiere activar "Registrar NCF proveedor desde POS" en ajustes.)*

1. En la pantalla de pago, pulsar **NCF Proveedor**.
2. Ingresar el NCF del proveedor (formato B01XXXXXXXX o E31XXXXXXXXXX).
3. Ingresar el RNC del proveedor (9 dígitos).
4. Ingresar el monto del comprobante.
5. Confirmar — se crea una factura borrador en
   **Contabilidad → Proveedores → NCF Proveedor POS**.

El contador debe revisar y confirmar la factura borrador para que quede
registrada en la contabilidad formal.

Notas técnicas
==============

Asignación del NCF
    El NCF **no** se pre-genera en el frontend. Se asigna al confirmar la
    ``account.move`` (``action_post``), cuando la secuencia del diario lo
    asigna automáticamente. Luego se lee de vuelta y se almacena en la
    orden POS para mostrarlo en el recibo.

Asientos de cierre de sesión
    En POS fiscal, los asientos de cierre de sesión (líneas de cobro,
    pagos bancarios, líneas de efectivo) se vacían deliberadamente. Cada
    pago ya generó su propio ``account.payment`` vinculado a la factura
    correspondiente. Generar los asientos estándar de Odoo produciría
    duplicaciones en la contabilidad.

Modo sin l10n_do_electronic_invoice
    El módulo funciona sin ``l10n_do_electronic_invoice``. Los tipos E3x
    serán visibles si el diario los tiene configurados, pero las facturas
    se crearán sin envío a DGII (modo contingencia). Se recomienda
    mostrar una advertencia al administrador si esto ocurre.

l10n_latam_manual_document_number
    Las facturas de venta creadas desde POS usan
    ``l10n_latam_manual_document_number = False`` para que la secuencia
    del diario asigne el NCF. Solo las facturas de proveedor registradas
    manualmente (NCF Proveedor POS) usan ``manual = True``.

Soporte
=======

- GitHub: https://github.com/odoo-dominicana
- Issues: https://github.com/odoo-dominicana/issues
