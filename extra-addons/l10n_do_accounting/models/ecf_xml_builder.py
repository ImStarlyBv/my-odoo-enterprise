# -*- coding: utf-8 -*-
"""
EcfXmlBuilder — Constructor genérico de XML para Comprobantes Fiscales
Electrónicos (e-CF) de la República Dominicana (DGII).

Soporta todos los tipos:
  E31 – Factura de Crédito Fiscal Electrónica
  E32 – Factura de Consumo Electrónica
  E33 – Nota de Débito Electrónica
  E34 – Nota de Crédito Electrónica
  E41 – Comprobante de Compras Electrónico
  E43 – Gastos Menores Electrónico
  E44 – Regímenes Especiales Electrónico
  E45 – Gubernamental Electrónico
  E46 – Exportaciones Electrónicas
  E47 – Pagos al Exterior Electrónico

Uso:
    from .ecf_xml_builder import EcfXmlBuilder
    xml_str = EcfXmlBuilder(invoice).build()
"""

from lxml import etree

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

ECF_VERSION = "1.0"

# Mapeo l10n_do_ncf_type → número entero de TipoeCF de la DGII
ECF_TYPE_MAP = {
    "e-fiscal": 31,
    "e-consumer": 32,
    "e-debit_note": 33,
    "e-credit_note": 34,
    "e-informal": 41,
    "e-minor": 43,
    "e-special": 44,
    "e-governmental": 45,
    "e-export": 46,
    "e-exterior": 47,
}

# Tipos que incluyen sección <Comprador>
ECF_TYPES_WITH_BUYER = {31, 32, 33, 34, 44, 45, 46, 47}

# Tipos que requieren <TipoIngresos> (solo Crédito Fiscal)
ECF_TYPES_WITH_INCOME_TYPE = {31}

# Tipos que incluyen <IndicadorEnvioDiferido>
ECF_TYPES_WITH_DEFERRED = {31, 32, 44, 45, 46, 47}

# Tipos que incluyen <IndicadorServicioTodoIncluido>
ECF_TYPES_WITH_ALL_INCLUSIVE = {31, 32}

# Tipos que incluyen <OtraMoneda>
ECF_TYPES_WITH_OTHER_CURRENCY = {31, 32, 33, 34, 44, 45, 46, 47}

# Tipos que incluyen información de Transporte
ECF_TYPES_WITH_TRANSPORT = {31}

# Tipos que incluyen InformacionesAdicionales
ECF_TYPES_WITH_ADD_INFO = {31, 32}

# Tipos que incluyen <Retencion> en los ítems (e-informal / compras)
ECF_TYPES_WITH_ITEM_RETENTION = {41}

# Tipos que incluyen <TablaImpuestoAdicional> en ítems
ECF_TYPES_WITH_ITEM_ADDL_TAX = {31, 32}

# Tipos que incluyen <GradosAlcohol> en ítems
ECF_TYPES_WITH_ALCOHOL = {31, 32}

# Tipos que incluyen <Mineria> en ítems
ECF_TYPES_WITH_MINING = {31}

# Tipos que incluyen <IndicadorNorma1007> en descuentos
ECF_TYPES_WITH_NORM_1007 = {31, 32}

# Tipos que incluyen CodigoVendedor / ZonaVenta / RutaVenta en el Emisor
ECF_TYPES_WITH_VENDOR_CODE = {31, 32}

# Tipos de pago DGII derivados de invoice_payment_term_id (días)
# La lógica real se computa en _get_tipo_pago()
TIPO_PAGO_CONTADO = "1"
TIPO_PAGO_CREDITO = "2"

# IndicadorBienoServicio según product.type de Odoo
PRODUCT_TYPE_MAP = {
    "consu": "1",      # Bien (consumible)
    "product": "1",    # Bien (almacenable)
    "service": "2",    # Servicio
}

# IndicadorFacturacion: 1 = gravado ITBIS 18%, 2 = gravado 16%, 3 = exento, 4 = otras tasas
INDICATOR_GRAVADO_I1 = "1"
INDICATOR_GRAVADO_I2 = "2"
INDICATOR_EXENTO = "3"
INDICATOR_OTHER = "4"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_date(date_val):
    """Convierte date/datetime de Odoo → 'DD-MM-YYYY' requerido por DGII."""
    if not date_val:
        return ""
    return date_val.strftime("%d-%m-%Y")


def _fmt_decimal(value, decimals=2):
    """Formatea un número como string con los decimales indicados."""
    if value is None:
        return "0.00"
    return f"{float(value):.{decimals}f}"


def _opt_elem(parent, tag, value):
    """
    Agrega un sub-elemento opcional a parent SOLO si value es
    algo distinto de None / False / cadena vacía.
    Devuelve el elemento creado o None.
    """
    if value is not None and value is not False and str(value).strip() != "":
        elem = etree.SubElement(parent, tag)
        elem.text = str(value).strip()
        return elem
    return None


def _req_elem(parent, tag, value):
    """
    Agrega un sub-elemento requerido. Siempre lo agrega;
    si value está vacío lo deja vacío para que el validador lo detecte.
    """
    elem = etree.SubElement(parent, tag)
    elem.text = str(value).strip() if value else ""
    return elem


# ---------------------------------------------------------------------------
# Builder principal
# ---------------------------------------------------------------------------

class EcfXmlBuilder:
    """
    Constructor de XML para e-CF dominicano.

    Parámetros
    ----------
    move : account.move
        Factura / comprobante en estado 'posted' o 'draft'.
    """

    def __init__(self, move):
        self.move = move
        doc_type = move.l10n_latam_document_type_id
        self.ncf_type = doc_type.l10n_do_ncf_type if doc_type else ""
        self.ecf_type = ECF_TYPE_MAP.get(self.ncf_type, 0)

        # Banderas de secciones disponibles para este tipo
        self.has_comprador = self.ecf_type in ECF_TYPES_WITH_BUYER
        self.has_tipo_ingresos = self.ecf_type in ECF_TYPES_WITH_INCOME_TYPE
        self.has_deferred = self.ecf_type in ECF_TYPES_WITH_DEFERRED
        self.has_all_inclusive = self.ecf_type in ECF_TYPES_WITH_ALL_INCLUSIVE
        self.has_otra_moneda = self.ecf_type in ECF_TYPES_WITH_OTHER_CURRENCY
        self.has_transporte = self.ecf_type in ECF_TYPES_WITH_TRANSPORT
        self.has_add_info = self.ecf_type in ECF_TYPES_WITH_ADD_INFO
        self.has_item_retention = self.ecf_type in ECF_TYPES_WITH_ITEM_RETENTION
        self.has_item_addl_tax = self.ecf_type in ECF_TYPES_WITH_ITEM_ADDL_TAX
        self.has_alcohol = self.ecf_type in ECF_TYPES_WITH_ALCOHOL
        self.has_mining = self.ecf_type in ECF_TYPES_WITH_MINING
        self.has_norm_1007 = self.ecf_type in ECF_TYPES_WITH_NORM_1007
        self.has_vendor_code = self.ecf_type in ECF_TYPES_WITH_VENDOR_CODE

        # Montos calculados (ITBIS, retención, exentos, etc.)
        self._amounts = move._get_l10n_do_amounts() if move else {}

        # Líneas de producto (excluye líneas de impuestos y secciones)
        self._product_lines = move.invoice_line_ids.filtered(
            lambda l: l.display_type == "product"
        ) if move else []

    # ------------------------------------------------------------------
    # Punto de entrada principal
    # ------------------------------------------------------------------

    def build(self):
        """
        Construye y devuelve el string XML completo del comprobante.

        Returns
        -------
        str
            XML codificado en UTF-8, con declaración XML.
        """
        if not self.ecf_type:
            raise ValueError(
                f"El tipo de NCF '{self.ncf_type}' no es un tipo electrónico válido. "
                f"Los tipos válidos son: {list(ECF_TYPE_MAP.keys())}"
            )

        ecf_root = etree.Element("ECF")
        ecf_root.append(self._build_encabezado())
        ecf_root.append(self._build_detalles_items())

        subtotales = self._build_subtotales()
        if subtotales is not None:
            ecf_root.append(subtotales)

        descuentos = self._build_descuentos_o_recargos()
        if descuentos is not None:
            ecf_root.append(descuentos)

        paginacion = self._build_paginacion()
        if paginacion is not None:
            ecf_root.append(paginacion)

        info_ref = self._build_informacion_referencia()
        if info_ref is not None:
            ecf_root.append(info_ref)

        # FechaHoraFirma y Firma digital — pendiente implementación futura
        # Se deja el nodo vacío para que el proceso de firmado lo complete
        fecha_firma = etree.SubElement(ecf_root, "FechaHoraFirma")
        fecha_firma.text = ""  # será completado por el módulo de firma (TODO)

        return etree.tostring(
            ecf_root,
            xml_declaration=True,
            encoding="UTF-8",
            pretty_print=True,
        ).decode("utf-8")

    # ------------------------------------------------------------------
    # Encabezado
    # ------------------------------------------------------------------

    def _build_encabezado(self):
        encabezado = etree.Element("Encabezado")

        version = etree.SubElement(encabezado, "Version")
        version.text = ECF_VERSION

        encabezado.append(self._build_id_doc())
        encabezado.append(self._build_emisor())

        if self.has_comprador:
            comprador = self._build_comprador()
            if comprador is not None:
                encabezado.append(comprador)

        # InformacionesAdicionales — solo E31, E32
        if self.has_add_info:
            add_info = self._build_informaciones_adicionales()
            if add_info is not None:
                encabezado.append(add_info)

        # Transporte — solo E31
        if self.has_transporte:
            transporte = self._build_transporte()
            if transporte is not None:
                encabezado.append(transporte)

        encabezado.append(self._build_totales())

        # OtraMoneda — ausente en E41
        if self.has_otra_moneda:
            otra_moneda = self._build_otra_moneda()
            if otra_moneda is not None:
                encabezado.append(otra_moneda)

        return encabezado

    # ------------------------------------------------------------------
    # IdDoc
    # ------------------------------------------------------------------

    def _build_id_doc(self):
        move = self.move
        id_doc = etree.Element("IdDoc")

        _req_elem(id_doc, "TipoeCF", str(self.ecf_type))
        _req_elem(id_doc, "eNCF", move.l10n_do_fiscal_number or "")
        _req_elem(
            id_doc,
            "FechaVencimientoSecuencia",
            _fmt_date(move.l10n_do_ncf_expiration_date),
        )

        # IndicadorMontoGravado: 1 si hay base gravada, 0 si todo exento
        monto_gravado_total = (
            self._amounts.get("itbis_18_base_amount", 0)
            + self._amounts.get("itbis_16_base_amount", 0)
        )
        indicador_gravado = "1" if monto_gravado_total > 0 else "0"
        _opt_elem(id_doc, "IndicadorMontoGravado", indicador_gravado)

        # IndicadorEnvioDiferido — solo tipos que lo permiten
        if self.has_deferred and getattr(move.company_id, "l10n_do_ecf_deferred_submissions", False):
            _opt_elem(id_doc, "IndicadorEnvioDiferido", "1")

        # TipoIngresos — requerido solo en E31
        if self.has_tipo_ingresos:
            income = move.l10n_do_income_type or "01"
            _req_elem(id_doc, "TipoIngresos", income)

        # IndicadorServicioTodoIncluido — solo E31, E32 (propinas)
        if self.has_all_inclusive:
            # Solo se agrega si la empresa aplica propina obligatoria (10%)
            # Se deja como OPT; el integrador puede sobrecargar este método
            pass  # _opt_elem(id_doc, "IndicadorServicioTodoIncluido", "1")

        # TipoPago — opcional en todos los tipos
        tipo_pago = self._get_tipo_pago()
        _opt_elem(id_doc, "TipoPago", tipo_pago)

        # FechaLimitePago — si hay fecha de vencimiento
        if move.invoice_date_due:
            _opt_elem(id_doc, "FechaLimitePago", _fmt_date(move.invoice_date_due))

        # TerminoPago — descripción del término (ej: "30 dias")
        if move.invoice_payment_term_id:
            _opt_elem(id_doc, "TerminoPago", move.invoice_payment_term_id.name)

        # TablaFormasPago — opcional (puede extenderse para múltiples medios de pago)
        tabla_formas = self._build_tabla_formas_pago()
        if tabla_formas is not None:
            id_doc.append(tabla_formas)

        # TotalPaginas — siempre 1 por ahora (paginación simple)
        _opt_elem(id_doc, "TotalPaginas", "1")

        return id_doc

    def _get_tipo_pago(self):
        """
        Deduce el TipoPago de la DGII desde invoice_payment_term_id de Odoo.

        Mapeo:
          Sin término de pago o término con 0 días  → 1 (Contado)
          Término con días > 0                       → 2 (Crédito)
        """
        move = self.move
        term = move.invoice_payment_term_id
        if not term:
            return TIPO_PAGO_CONTADO

        # Inspeccionar las líneas del término de pago
        # Si hay líneas con días > 0 se considera crédito
        has_days = any(
            getattr(line, "days", 0) > 0 or getattr(line, "nb_days", 0) > 0
            for line in term.line_ids
        ) if hasattr(term, "line_ids") else False

        return TIPO_PAGO_CREDITO if has_days else TIPO_PAGO_CONTADO

    def _build_tabla_formas_pago(self):
        """
        Construye TablaFormasPago.
        Por ahora mapea el monto total con la forma de pago derivada de TipoPago.
        Se puede ampliar cuando el módulo de registro de pagos esté disponible.
        """
        move = self.move
        if not move.amount_total:
            return None

        tabla = etree.Element("TablaFormasPago")
        _opt_elem(tabla, "FormaPago", self._get_tipo_pago())
        _opt_elem(tabla, "MontoPago", _fmt_decimal(abs(move.amount_total)))
        return tabla

    # ------------------------------------------------------------------
    # Emisor
    # ------------------------------------------------------------------

    def _build_emisor(self):
        move = self.move
        company = move.company_id
        emisor = etree.Element("Emisor")

        _req_elem(emisor, "RNCEmisor", (company.vat or "").strip())
        _req_elem(emisor, "RazonSocialEmisor", company.name or "")
        _opt_elem(
            emisor,
            "NombreComercial",
            company.partner_id.commercial_company_name or company.name,
        )

        # Sucursal y código interno — si se usan múltiples compañías en Odoo
        # se puede referenciar el nombre de la compañía hija
        _opt_elem(emisor, "Sucursal", None)  # sin valor por defecto
        _opt_elem(emisor, "CodigoInterno", None)  # sin valor por defecto

        _req_elem(emisor, "DireccionEmisor", company.street or "")
        _opt_elem(emisor, "Municipio", None)   # Campo pendiente en res.company
        _opt_elem(emisor, "Provincia", None)   # Campo pendiente en res.company
        _opt_elem(emisor, "TelefonoEmisor", company.phone)
        _opt_elem(emisor, "CorreoEmisor", company.email)
        _opt_elem(emisor, "WebSite", company.website)
        _req_elem(emisor, "FechaEmision", _fmt_date(move.invoice_date))

        # CodigoVendedor / ZonaVenta / RutaVenta — solo E31, E32
        if self.has_vendor_code:
            _opt_elem(emisor, "CodigoVendedor", None)
            _opt_elem(emisor, "ZonaVenta", None)
            _opt_elem(emisor, "RutaVenta", None)

        return emisor

    # ------------------------------------------------------------------
    # Comprador — AUSENTE en E41 (compras) y E43 (gastos menores)
    # ------------------------------------------------------------------

    def _build_comprador(self):
        """
        Construye la sección <Comprador>.
        Retorna None si el partner no tiene RNC/cédula y el tipo no lo requiere.
        En E32 (consumo) el comprador es opcional salvo montos >= RD$250,000.
        """
        move = self.move
        partner = move.commercial_partner_id
        if not partner:
            return None

        comprador = etree.Element("Comprador")
        vat = (partner.vat or "").strip()

        _opt_elem(comprador, "RNCComprador", vat if vat else None)
        _req_elem(comprador, "RazonSocialComprador", partner.name or "")
        _opt_elem(comprador, "ContactoComprador", move.partner_id.name if move.partner_id != partner else None)
        _opt_elem(comprador, "CorreoComprador", move.partner_id.email)
        _opt_elem(comprador, "DireccionComprador", partner.street)
        _opt_elem(comprador, "FechaPago", _fmt_date(move.invoice_date_due))

        # Si es consumo y el monto es < 250k y no hay RNC, omitir comprador
        if self.ecf_type == 32 and not vat and move.amount_total < 250000:
            return None

        return comprador

    # ------------------------------------------------------------------
    # InformacionesAdicionales — solo E31, E32
    # ------------------------------------------------------------------

    def _build_informaciones_adicionales(self):
        """
        Construye información adicional como número de orden, contrato, etc.
        Por ahora retorna None (sin datos adicionales). Se puede extender
        agregando campos extra en account.move.
        """
        return None  # Extensible por el integrador

    # ------------------------------------------------------------------
    # Transporte — solo E31
    # ------------------------------------------------------------------

    def _build_transporte(self):
        """
        Sección de transporte para facturas de crédito fiscal.
        Se deja como None hasta que se agreguen campos de envío en account.move.
        """
        return None  # Extensible por el integrador

    # ------------------------------------------------------------------
    # Totales
    # ------------------------------------------------------------------

    def _build_totales(self):
        move = self.move
        amounts = self._amounts
        totales = etree.Element("Totales")

        itbis_18_base = amounts.get("itbis_18_base_amount", 0)
        itbis_16_base = amounts.get("itbis_16_base_amount", 0)
        exempt = amounts.get("exempt_amount", 0)

        monto_gravado_total = itbis_18_base + itbis_16_base
        if monto_gravado_total:
            _opt_elem(totales, "MontoGravadoTotal", _fmt_decimal(monto_gravado_total))
            _opt_elem(totales, "MontoGravadoI1", _fmt_decimal(itbis_18_base))
            _opt_elem(totales, "MontoGravadoI2", _fmt_decimal(itbis_16_base))
            _opt_elem(totales, "MontoGravadoI3", "0.00")  # ITBIS tasa 0 (no soportado aún)

        _opt_elem(totales, "MontoExento", _fmt_decimal(exempt) if exempt else None)

        itbis_18 = amounts.get("itbis_18_tax_amount", 0)
        itbis_16 = amounts.get("itbis_16_tax_amount", 0)
        if itbis_18:
            _opt_elem(totales, "ITBIS1", "18")
            _opt_elem(totales, "TotalITBIS1", _fmt_decimal(itbis_18))
        if itbis_16:
            _opt_elem(totales, "ITBIS2", "16")
            _opt_elem(totales, "TotalITBIS2", _fmt_decimal(itbis_16))

        # Retenciones — presentes en todos los tipos cuando aplican
        itbis_ret = amounts.get("itbis_withholding_amount", 0)
        isr_ret = amounts.get("isr_withholding_amount", 0)
        _opt_elem(totales, "TotalITBISRetenido", _fmt_decimal(itbis_ret) if itbis_ret else None)
        _opt_elem(totales, "TotalISRRetencion", _fmt_decimal(isr_ret) if isr_ret else None)

        # Percepciones (no soportadas aún, siempre 0 si se agregan)
        # _opt_elem(totales, "TotalITBISPercepcion", "0.00")
        # _opt_elem(totales, "TotalISRPercepcion", "0.00")

        # MontoTotal — REQUERIDO en todos los tipos
        _req_elem(totales, "MontoTotal", _fmt_decimal(abs(move.amount_total)))

        # Campos opcionales de cobro
        _opt_elem(totales, "ValorPagar", _fmt_decimal(abs(move.amount_residual)) if move.amount_residual else None)

        return totales

    # ------------------------------------------------------------------
    # OtraMoneda — ausente en E41
    # ------------------------------------------------------------------

    def _build_otra_moneda(self):
        """
        Construye la sección <OtraMoneda> cuando la factura está en
        una moneda diferente a DOP (moneda de la empresa).
        """
        move = self.move
        if move.currency_id == move.company_id.currency_id:
            return None  # Misma moneda, no se agrega la sección

        otra = etree.Element("OtraMoneda")
        _opt_elem(otra, "TipoMoneda", move.currency_id.name)

        # Tasa de cambio al momento de la factura
        rate = (move.currency_id + move.company_id.currency_id)._get_rates(
            move.company_id, move.date
        ).get(move.currency_id.id, 1)
        _opt_elem(otra, "TipoCambio", _fmt_decimal(rate, 4))

        amounts_currency = self._amounts
        monto_gravado_currency = (
            amounts_currency.get("itbis_18_base_amount_currency", 0)
            + amounts_currency.get("itbis_16_base_amount_currency", 0)
        )
        _opt_elem(otra, "MontoGravadoTotalOtraMoneda", _fmt_decimal(monto_gravado_currency))
        _opt_elem(otra, "MontoExentoOtraMoneda", _fmt_decimal(amounts_currency.get("exempt_amount_currency", 0)))
        _opt_elem(otra, "TotalITBIS1OtraMoneda", _fmt_decimal(amounts_currency.get("itbis_18_tax_amount_currency", 0)))
        _opt_elem(otra, "TotalITBIS2OtraMoneda", _fmt_decimal(amounts_currency.get("itbis_16_tax_amount_currency", 0)))
        _opt_elem(otra, "MontoTotalOtraMoneda", _fmt_decimal(abs(move.amount_total_signed)))

        return otra

    # ------------------------------------------------------------------
    # Ítems / Líneas de detalle
    # ------------------------------------------------------------------

    def _build_detalles_items(self):
        detalles = etree.Element("DetallesItems")
        for idx, line in enumerate(self._product_lines, start=1):
            detalles.append(self._build_item(line, idx))
        return detalles

    def _build_item(self, line, idx):
        item = etree.Element("Item")
        _req_elem(item, "NumeroLinea", str(idx))

        # IndicadorFacturacion — según impuesto de la línea
        _req_elem(item, "IndicadorFacturacion", self._get_indicador_facturacion(line))

        # Descripción
        product = line.product_id
        nombre = (product.name if product else "") or line.name or ""
        _req_elem(item, "NombreItem", nombre[:150])  # máx 150 chars

        # IndicadorBienoServicio: 1=Bien, 2=Servicio
        tipo_producto = PRODUCT_TYPE_MAP.get(product.type, "1") if product else "1"
        _opt_elem(item, "IndicadorBienoServicio", tipo_producto)

        # Descripción larga (si difiere del nombre)
        if line.name and line.name != nombre:
            _opt_elem(item, "DescripcionItem", line.name[:250])

        _req_elem(item, "CantidadItem", _fmt_decimal(line.quantity, 2))

        # UnidadMedida — código DGII de la UoM (se deja por defecto "99" = Otro)
        uom = product.uom_id if product else None
        _opt_elem(item, "UnidadMedida", self._get_uom_code(uom))

        _req_elem(item, "PrecioUnitarioItem", _fmt_decimal(line.price_unit))

        # Descuento por línea
        if line.discount:
            discount_amount = line.price_unit * line.quantity * (line.discount / 100.0)
            _opt_elem(item, "DescuentoMonto", _fmt_decimal(discount_amount))

        # Subdescuentos y subrecargos
        sub_desc = self._build_tabla_sub_descuento(line)
        if sub_desc is not None:
            item.append(sub_desc)

        sub_rec = self._build_tabla_sub_recargo(line)
        if sub_rec is not None:
            item.append(sub_rec)

        # MontoItem — subtotal antes de impuestos
        _req_elem(item, "MontoItem", _fmt_decimal(abs(line.price_subtotal)))

        # MontoITBIS — calculado del campo extendido en account.move.line
        itbis_amount = getattr(line, "l10n_do_itbis_amount", 0) or 0
        _opt_elem(item, "MontoITBIS", _fmt_decimal(itbis_amount) if itbis_amount else None)

        # TablaImpuestoAdicional — solo E31, E32
        if self.has_item_addl_tax:
            addl_tax = self._build_tabla_impuesto_adicional(line)
            if addl_tax is not None:
                item.append(addl_tax)

        # GradosAlcohol — solo E31, E32
        if self.has_alcohol:
            _opt_elem(item, "GradosAlcohol", None)  # Extensible

        # Retencion — SOLO E41 (compras), OPT bloque pero REQ internamente
        if self.has_item_retention:
            retencion = self._build_item_retencion(line)
            if retencion is not None:
                item.append(retencion)

        # Mineria — solo E31
        if self.has_mining:
            pass  # Extensible: _build_mineria(line)

        return item

    def _get_indicador_facturacion(self, line):
        """
        Determina IndicadorFacturacion según los impuestos de la línea:
          1 = Gravado ITBIS 18%
          2 = Gravado ITBIS 16%
          3 = Exento / sin ITBIS
          4 = Gravado con otras tasas
        """
        if not line.tax_ids:
            return INDICATOR_EXENTO

        itbis_taxes = [
            t for t in line.tax_ids
            if hasattr(t, "tax_group_id") and "itbis" in (t.tax_group_id.name or "").lower()
        ]
        if not itbis_taxes:
            return INDICATOR_EXENTO

        rates = [abs(t.amount) for t in itbis_taxes if t.amount]
        if not rates:
            return INDICATOR_EXENTO
        max_rate = max(rates)
        if max_rate >= 18:
            return INDICATOR_GRAVADO_I1
        elif max_rate >= 16:
            return INDICATOR_GRAVADO_I2
        else:
            return INDICATOR_OTHER

    def _get_uom_code(self, uom):
        """
        Devuelve el código DGII de la unidad de medida.
        Por defecto retorna "99" (Otro). El integrador puede ampliar
        este método con un mapa de UoM de Odoo → códigos DGII.
        """
        if not uom:
            return "99"
        # Mapa básico de unidades comunes → código DGII
        UOM_DGII_MAP = {
            "Unidades": "01",
            "Unit(s)": "01",
            "kg": "02",
            "g": "06",
            "lb": "03",
            "oz": "05",
            "L": "09",
            "mL": "10",
            "m": "11",
            "cm": "12",
            "m²": "16",
            "m³": "17",
            "docenas": "21",
            "cajas": "23",
            "horas": "43",
            "días": "44",
            "Hours": "43",
            "Days": "44",
        }
        return UOM_DGII_MAP.get(uom.name, "99")

    def _build_tabla_sub_descuento(self, line):
        """
        Construye TablaSubDescuento para una línea.
        Solo agrega el nodo si hay descuento > 0.
        """
        if not line.discount or line.discount <= 0:
            return None
        tabla = etree.Element("TablaSubDescuento")
        sub = etree.SubElement(tabla, "SubDescuento")
        _req_elem(sub, "TipoSubDescuento", "%")
        _req_elem(sub, "SubDescuentoPorcentaje", _fmt_decimal(line.discount))
        _req_elem(sub, "DescuentoPorcentajeIndicadorFacturacion", self._get_indicador_facturacion(line))
        descuento_monto = line.price_unit * line.quantity * (line.discount / 100.0)
        _req_elem(sub, "MontoSubDescuento", _fmt_decimal(descuento_monto))
        return tabla

    def _build_tabla_sub_recargo(self, line):
        """
        Por ahora no hay recargos en las líneas de Odoo (no tiene campo nativo).
        Retorna None. Extensible por el integrador.
        """
        return None

    def _build_tabla_impuesto_adicional(self, line):
        """
        Construye TablaImpuestoAdicional para la línea — solo E31, E32.
        Por ahora retorna None (impuestos selectivos no implementados).
        Extensible para ISC, aranceles, etc.
        """
        return None

    def _build_item_retencion(self, line):
        """
        Construye el bloque <Retencion> dentro de un <Item> — SOLO E41 (compras).

        Cuando existe el bloque, IndicadorAgenteRetencionoPercepcion es REQ:
          1 = Retención
          2 = Percepción
        """
        # Buscar impuestos de retención en esta línea
        isr_taxes = [
            t for t in line.tax_ids
            if hasattr(t, "tax_group_id")
            and "isr" in (t.tax_group_id.name or "").lower()
            and t.amount < 0
        ]
        itbis_ret_taxes = [
            t for t in line.tax_ids
            if hasattr(t, "tax_group_id")
            and "itbis" in (t.tax_group_id.name or "").lower()
            and t.amount < 0
        ]

        if not isr_taxes and not itbis_ret_taxes:
            return None  # No hay retenciones en esta línea

        retencion = etree.Element("Retencion")
        _req_elem(retencion, "IndicadorAgenteRetencionoPercepcion", "1")  # 1 = Retención

        # MontoITBISRetenido
        if itbis_ret_taxes:
            itbis_ret_amount = sum(
                abs(line.price_subtotal * abs(t.amount) / 100.0) for t in itbis_ret_taxes
            )
            _opt_elem(retencion, "MontoITBISRetenido", _fmt_decimal(itbis_ret_amount))

        # MontoISRRetenido
        if isr_taxes:
            isr_ret_amount = sum(
                abs(line.price_subtotal * abs(t.amount) / 100.0) for t in isr_taxes
            )
            _opt_elem(retencion, "MontoISRRetenido", _fmt_decimal(isr_ret_amount))

        _opt_elem(retencion, "MontoITBISPercibido", None)
        _opt_elem(retencion, "MontoISRPercibido", None)

        return retencion

    # ------------------------------------------------------------------
    # Subtotales
    # ------------------------------------------------------------------

    def _build_subtotales(self):
        amounts = self._amounts
        product_lines = self._product_lines
        if not product_lines:
            return None

        sub = etree.Element("Subtotales")

        itbis_18_base = amounts.get("itbis_18_base_amount", 0)
        itbis_16_base = amounts.get("itbis_16_base_amount", 0)
        exempt = amounts.get("exempt_amount", 0)
        itbis_18 = amounts.get("itbis_18_tax_amount", 0)
        itbis_16 = amounts.get("itbis_16_tax_amount", 0)
        monto_gravado_total = itbis_18_base + itbis_16_base

        _opt_elem(sub, "SubTotalMontoGravadoTotal", _fmt_decimal(monto_gravado_total))
        _opt_elem(sub, "SubTotalMontoGravadoI1", _fmt_decimal(itbis_18_base))
        _opt_elem(sub, "SubTotalMontoGravadoI2", _fmt_decimal(itbis_16_base))
        _opt_elem(sub, "SubTotalMontoGravadoI3", "0.00")
        _opt_elem(sub, "SubTotalExento", _fmt_decimal(exempt))
        _opt_elem(sub, "SubTotaITBIS1", _fmt_decimal(itbis_18))
        _opt_elem(sub, "SubTotaITBIS2", _fmt_decimal(itbis_16))
        _opt_elem(sub, "SubTotaITBIS3", "0.00")
        _opt_elem(sub, "SubTotalImpuestoAdicional", "0.00")

        monto_subtotal = monto_gravado_total + exempt + itbis_18 + itbis_16
        _opt_elem(sub, "MontoSubTotal", _fmt_decimal(monto_subtotal))
        _opt_elem(sub, "Lineas", str(len(product_lines)))

        return sub

    # ------------------------------------------------------------------
    # Descuentos o Recargos globales
    # ------------------------------------------------------------------

    def _build_descuentos_o_recargos(self):
        """
        Construye la sección de descuentos/recargos a nivel de documento.
        Solo se agrega si hay descuentos en la factura.

        Nota: IndicadorNorma1007 NO aplica en E41 (ausente).
        """
        move = self.move
        # Calcular descuento global de la factura
        total_discount = sum(
            line.price_unit * line.quantity * (line.discount / 100.0)
            for line in self._product_lines
            if line.discount
        )
        if not total_discount:
            return None

        dr = etree.Element("DescuentosORecargos")
        _req_elem(dr, "TipoAjuste", "D")  # D = Descuento
        _req_elem(dr, "DescuentoMonto", _fmt_decimal(total_discount))
        _req_elem(dr, "RecargoMonto", "0.00")

        # IndicadorFacturacionDR: basado en el tipo más común de las líneas
        _req_elem(dr, "IndicadorFacturacionDR", INDICATOR_GRAVADO_I1)

        # IndicadorNorma1007 — solo E31, E32
        if self.has_norm_1007:
            _opt_elem(dr, "IndicadorNorma1007", None)  # Extensible

        return dr

    # ------------------------------------------------------------------
    # Paginación
    # ------------------------------------------------------------------

    def _build_paginacion(self):
        """
        Construye la sección de paginación (1 sola página por defecto).
        Para documentos con muchas líneas, se puede paginar en múltiples bloques.
        """
        amounts = self._amounts
        product_lines = self._product_lines
        if not product_lines:
            return None

        pag = etree.Element("Paginacion")
        _req_elem(pag, "PaginaNo", "1")
        _req_elem(pag, "NoLineaDesde", "1")
        _req_elem(pag, "NoLineaHasta", str(len(product_lines)))

        itbis_18_base = amounts.get("itbis_18_base_amount", 0)
        itbis_16_base = amounts.get("itbis_16_base_amount", 0)
        exempt = amounts.get("exempt_amount", 0)
        itbis_18 = amounts.get("itbis_18_tax_amount", 0)
        itbis_16 = amounts.get("itbis_16_tax_amount", 0)
        monto_gravado = itbis_18_base + itbis_16_base

        _opt_elem(pag, "SubtotalMontoGravadoPagina", _fmt_decimal(monto_gravado))
        _opt_elem(pag, "SubtotalMontoGravado1Pagina", _fmt_decimal(itbis_18_base))
        _opt_elem(pag, "SubtotalMontoGravado2Pagina", _fmt_decimal(itbis_16_base))
        _opt_elem(pag, "SubtotalMontoGravado3Pagina", "0.00")
        _opt_elem(pag, "SubtotalExentoPagina", _fmt_decimal(exempt))

        total_itbis = itbis_18 + itbis_16
        _opt_elem(pag, "SubtotalItbisPagina", _fmt_decimal(total_itbis))
        _opt_elem(pag, "SubtotalItbis1Pagina", _fmt_decimal(itbis_18))
        _opt_elem(pag, "SubtotalItbis2Pagina", _fmt_decimal(itbis_16))
        _opt_elem(pag, "SubtotalItbis3Pagina", "0.00")
        _opt_elem(pag, "SubtotalImpuestoAdicionalPagina", "0.00")

        # SubtotalImpuestoAdicional (bloque)
        sub_imp = etree.SubElement(pag, "SubtotalImpuestoAdicional")
        _opt_elem(sub_imp, "SubtotalImpEsp", "0.00")
        _opt_elem(sub_imp, "SubtotalImpAdvalorem", "0.00")
        _opt_elem(sub_imp, "SubtotalOtrosImpuesto", "0.00")

        monto_subtotal_pag = monto_gravado + exempt + total_itbis
        _opt_elem(pag, "MontoSubtotalPagina", _fmt_decimal(monto_subtotal_pag))

        return pag

    # ------------------------------------------------------------------
    # InformacionReferencia — para anulaciones, notas de crédito/débito
    # ------------------------------------------------------------------

    def _build_informacion_referencia(self):
        """
        Construye la sección <InformacionReferencia> cuando el comprobante
        modifica/referencia otro (nota de crédito, débito, anulación).

        Fuente: move.l10n_do_origin_ncf y move.l10n_do_ecf_modification_code.
        """
        move = self.move
        origin_ncf = move.l10n_do_origin_ncf
        mod_code = move.l10n_do_ecf_modification_code

        if not origin_ncf:
            return None

        ref = etree.Element("InformacionReferencia")
        _req_elem(ref, "NCFModificado", origin_ncf)

        # Fecha del NCF modificado — usamos la fecha de la factura referenciada si existe
        reversed_invoice = move.reversed_entry_id
        fecha_ref = reversed_invoice.invoice_date if reversed_invoice else move.invoice_date
        _opt_elem(ref, "FechaNCFModificado", _fmt_date(fecha_ref))

        _opt_elem(ref, "CodigoModificacion", mod_code)

        # Razón de modificación (descripción libre del código)
        reason_map = {
            "1": "Anulación Total",
            "2": "Corrección de Texto",
            "3": "Corrección de Montos",
            "4": "Reemplazo de NCF en Contingencia",
            "5": "Referencia a Factura de Consumo",
        }
        _opt_elem(ref, "RazonModificacion", reason_map.get(mod_code or "", ""))

        return ref
