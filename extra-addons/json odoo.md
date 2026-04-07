    def get_invoice_data(self):
        """
            Extrae los datos del registro actual y los convierte en un formato compatible con PayloadBuilder.
        """
        # TODO: Cambiar el user_id por el usuario que esta logueado
        # TODO: Agregar cual validacion/constraint necesario para enviar la data correcta al api
        # TODO: Mejorar la respuesta de la api para que sea mas clara
        # TODO: Verificar todos los metodos que se involucran en el calculo de los impuestos
        #Buscar el vencimiento segun el tipo de comprobante fiscal
        vencimientoncf = self.get_ncf_expiry_date(self.journal_id, self.l10n_latam_document_type_id)
        if not vencimientoncf:
            vencimientoncf = (date.today() + timedelta(days=30))  # Por defecto, 30 días a partir de hoy

        self.l10n_do_ncf_expiration_date = vencimientoncf

        #raise ValidationError(vencimientoncf)
        if self.l10n_latam_document_type_id.code == "B":
            return True
        self.ensure_one()  # Me aseguro que solo haya un registro activo
        codes_prefix = CodesAndPrefix()
        totals = self._get_dgii_tax_totals()
        isElectronic = True if self.l10n_latam_document_type_id.code == 'E' else False
        doc_type = codes_prefix.get_ncf_electronic_type(self.l10n_latam_document_type_id.doc_code_prefix, isElectronic)

        # --- NO CAMBIAR NOMBRE SI YA ESTÁ PUBLICADO ---
        if not self.name or self.name == '/':
            self.name = self._set_next_sequence()
        # ----------------------------------------------------------

        ref_inovice = self.get_ref_invoice()

        if self.l10n_latam_document_number:
            # Retorna el valor desde el carácter en la posición 3 hasta el final
            sequence = self.l10n_latam_document_number[3:]
            #raise ValidationError(sequence)
        else:
            sequence = self._invoice_api_sequence()
            #raise ValidationError(sequence)
        _logger.info(f"La secuencia es {sequence}")
        main_branch = self.env['res.branch'].search([('company_id', '=', self.env.company.id), ('principal_branch', '=', True)], limit=1)

        is_live_flag = 1 if getattr(self.env.company, 'is_live', False) else 0
        #raise ValidationError(sequence)
        
        return {
            "user_id": self.env.user.id,#5,  # self.env.user.id, se mantiene fijo por ahora
            "doc_type": doc_type,
            "issued_date": self.invoice_date.strftime('%Y-%m-%d') if self.invoice_date else date.today().strftime('%Y-%m-%d'), # Este formato de fecha no da problema con el api siafe pero directamente a digifact si
            "sequence": sequence,  # Cambia al formato funcional del JSON probado
            "income_type": "01",
            "start_date": self.invoice_date.isoformat() if self.invoice_date else date.today().strftime('%Y-%m-%d'),
            "end_date": self.invoice_date_due.isoformat() if self.invoice_date_due else date.today().strftime('%Y-%m-%d'),
            "vencsequence_date": vencimientoncf.isoformat(),  # Fecha de vencimiento del NCF
            "is_live": is_live_flag,  # 🔹 Valor que indica si el json ira a produccion o no
            "seller": {
                "tax_id": self.env.company.vat,#"132752155",#?elf.env.company.vat or "",
                "name": self.env.company.name,#"DIGIFACT SERVICIOS SAS",#?self.env.company.name or "",
                "phones" : [
                    phone.strip()  # Elimina espacios en blanco alrededor de cada email
                    for phone in re.split(r'[;, ]+', self.format_phone_number(self.env.company.phone)) if phone.strip()
                ] if self.format_phone_number(self.env.company.phone) else [],
                "emails" : [
                    email.strip() # Elimina espacios en blanco alrededor de cada email
                    for email in re.split(r'[;, ]+', self.env.company.email) if email.strip()
                ] if self.env.company.email else [],
                "website": self.env.company.website or "",
                #"branchCode": main_branch.code or "0001", # ? Revisar addional info
                "branch_name": main_branch.code or "", # ? Revisar addional info
                "BranchInfo": {
                    "Name": main_branch.name or "",
                    "AddressInfo": {
                        "Address": main_branch.street or "",
                        "District": self.env.company.l10n_do_municipality_id.code or "", # Extrae el 010100 dinámicamente
                        "State": self.env.company.state_id.l10n_do_dgii_code or "",      # Extrae el 010000 dinámicamente
                        "Country": "DO",
                    }
                },
                "branch_address": {
                    "Address": main_branch.street or "",
                    "District": self.env.company.l10n_do_municipality_id.code or "",
                    "State": self.env.company.state_id.l10n_do_dgii_code or "",
                    "Country": "DO",
                },
                "additional_info": [
                    {"Name": "NombreComercial", "Value": self.env.company.name or ""},
                    {"Name": "ActividadEconomica", "Value": "Comercio"},
                    *(
                        [{"Name": "CodigoVendedor", "Value": "1234112"}]
                        if doc_type not in ["41", "43", "47"] else []
                    ),
                    {"Name": "NumeroFacturaInterna", "Value": self.name}, # Esto es una secuencia self.name
                    {"Name": "NumeroPedidoInterno", "Value": "123456"},
                    *(
                        [{"Name": "ZonaVenta", "Value": "zona de prueba"}]
                        if doc_type not in ["41", "43", "47"] else []
                    ),
                    *(
                        [{"Name": "RutaVenta", "Value": "ruta"}]
                        if doc_type not in ["41", "43", "47"] else []
                    ),
                    {"Name": "InformacionAdicionalEmisor", "Value": ""} # quizas ponerle el valor de nota interna narration
                ],
            },
            "buyer": { # If credit note, this is the buyer of the original invoice
                "tax_id": self.partner_id.vat or "",
                "name": self.partner_id.name or "",
                "phones" : [
                    phone.strip()  # Elimina espacios en blanco alrededor de cada email
                    for phone in re.split(r'[;, ]+', self.format_phone_number(self.partner_id.phone)) if phone.strip()
                ] if self.format_phone_number(self.partner_id.phone) else [],
                "emails" : [
                    email.strip()  # Elimina espacios en blanco alrededor de cada email
                    for email in re.split(r'[;, ]+', self.partner_id.email) if email.strip()
                ] if self.partner_id.email else [],
                "address": {
                    "Address": self.partner_id.street or "",
                    "District": self.partner_id.l10n_do_municipality_id.code or "", # Municipio del cliente
                    "State": self.partner_id.state_id.l10n_do_dgii_code or "",      # Provincia del cliente
                    "Country": "DO",
                },
                "additional_info": [
                    {"Name": "InformacionAdicionalComprador", "Value": "Detalles adicionales"},
                ]
            },
            "items": [
                {
                    "codes": [{
                        "Name": "EAN" if line.product_id.barcode else ("PLU" if line.product_id.default_code else "SIN_CODIGO"),
                        "Value": line.product_id.barcode or line.product_id.default_code or "0"
                    }],
                    "type": (codes_prefix.get_item_type_sufix(line.product_id.type)) if doc_type not in ["47"] else "2",
                    "description": line.product_id.name or "SIN_DESCRIPCION",
                    "qty": "{:.2f}".format(float(line.quantity)),
                    "unit_of_measure": "32",#line.product_id.uom_id.x_dgii_code if line.product_id.uom_id.x_dgii_code else "32",
                    "price": "{:.2f}".format(self._get_price_unit_wo_tax_for_payload(line)),
                    "discounts": {
                        "Discount": [
                            {
                                "Code": "%" if line.discount > 0 else "$", 
                                "Rate": "{:.2f}".format(line.discount),
                                "Amount": self._convert_to_dop(
                                        self._get_price_unit_wo_tax_for_payload(line) * line.discount * line.quantity
                                    )
                            },
                        ]
                    },
                    **(
                        {
                            "Taxes":{
                                "Tax":[
                                    {
                                        "Code":"001",
                                        "Description":"IMPUESTO_ADICIONAL",
                                        "Amount":"0.00"
                                    }
                                ]
                            },
                        } if line.tax_ids else {}
                    ),
                    "charges": {
                        "Charge": [
                            {"Code": "$", "Amount": "0.00"},
                        ]
                    },
                    "totals": { # Sumatoria de los decuentos y cargas
                        "total_item": "{:.2f}".format((self._get_price_unit_wo_tax_for_payload(line) * line.quantity)),
                             # sum hay que pasarle un iterable, en este campo va la sumatoria de todos los  items 
                    },
                    "additional_info": [
                        # 1. Descripción del ítem
                        {"Name": "DescripcionItem", "Value": line.product_id.name or ""},
                        
                        # 2. Indicador de Facturación
                        {
                            "Name": "IndicadorFacturacion",
                            "Value": self.get_indicador_facturacion(
                                doc_type,
                                line.tax_ids[0] if line.tax_ids else None
                            )
                        },
                        
                        # 3. Indicador Agente Retención (Solo 41 y 47) [cite: 203]
                        *(
                            [{"Name": "IndicadorAgenteRetencionPercepcion", "Value": "1"}]
                            if doc_type in ["41", "47"] else []
                        ),
                        
                        # 4. Monto ISR Retenido (Inyectamos el valor directo, sin bucles internos)
                        *(
                            [{
                                "Name": "MontoISRRetenido",
                                "Value": totals["additional_info_item"][index]["MontoISRRetenido"]
                            }]
                            # Validamos que aplique al doc y que la llave exista para esta línea específica
                            if doc_type in ["41", "47"] and "MontoISRRetenido" in totals["additional_info_item"][index]
                            else []
                        ),
                        
                        # 5. Monto ITBIS Retenido (Inyectamos el valor directo)
                        *(
                            [{
                                "Name": "MontoITBISRetenido",
                                "Value": totals["additional_info_item"][index]["MontoITBISRetenido"]
                            }]
                            # Validamos que sea 41 y que la llave exista
                            if doc_type == "41" and "MontoITBISRetenido" in totals["additional_info_item"][index]
                            else []
                        ),
                    ]
                } for index, line in enumerate(self.invoice_line_ids)
            ],
            "totals": {
                "qty_items": totals['qty_items'],
                "total_taxable_amount": float(totals['total_taxable_amount']) if totals else 0.00,
                "total_taxes": {
                    "TotalTax": totals['total_taxes']['TotalTax']
                },
                "grand_total": {
                    "InvoiceTotal": totals['grand_total']['InvoiceTotal'],
                },
                **(
                    {
                        "additional_info": [
                            {
                                "Name": "TotalISRRetencion",
                                "Value": totals["additional_info_totals"]["TotalISRRetencion"],
                            },
                            *(
                                [{
                                    "Name": "TotalITBISRetenido",
                                    "Value": totals["additional_info_totals"]["TotalITBISRetenido"],
                                }]
                                # FI05 solo aplica para tipos como el 41
                                if doc_type == "41" else []
                            ),
                        ]
                    }
                    # 41 y 47 reportan TotalISRRetencion; solo 41 agrega TotalITBISRetenido
                    if doc_type in ["41", "47"] else {}
                )
            },
            # Pagos: por defecto usamos el total gravado.
            # Para el 41 el monto a pagar es el total de la factura
            # menos las retenciones (ISR + ITBIS retenido).
            "payments": [
                {
                    "Code": "1",
                    "Amount": (
                        # 41: neto a pagar = total factura - retenciones
                        "{:.2f}".format(
                            float(totals['grand_total']['InvoiceTotal']) -
                            float(totals.get("additional_info_totals", {}).get("TotalISRRetencion", 0.0) or 0.0) -
                            float(totals.get("additional_info_totals", {}).get("TotalITBISRetenido", 0.0) or 0.0)
                        )
                        if totals and doc_type == "41"
                        # Otros documentos: mantén el comportamiento actual
                        else totals['total_taxable_amount'] if totals else "0.00"
                    ),
                },
            ],
            "additional_document_info": {
                "AdditionalInfo": [
                    {
                        "AditionalData": {
                            "Data": [
                                *([{
                                    "Info": [
                                        ({"Name": "SubTotalMontoGravado1" , "Value": totals['total_taxable_amount']}),
                                        {"Name": "SubTotalITBIS", "Value": "{:.2f}".format(
                                            sum(
                                                float(tax.get('Amount', 0.0))
                                                for tax in totals['total_taxes']['TotalTax']
                                                if str(tax.get('Code', '')).upper().startswith('ITBIS')
                                            )
                                        )},
                                        {
                                            "Name": "SubTotalMontoGravadoTotal",
                                            "Value": (
                                                # 41: el subtotal total gravado coincide con el neto pagado
                                                "{:.2f}".format(
                                                    float(totals['grand_total']['InvoiceTotal']) -
                                                    float(totals.get("additional_info_totals", {}).get("TotalISRRetencion", 0.0) or 0.0) -
                                                    float(totals.get("additional_info_totals", {}).get("TotalITBISRetenido", 0.0) or 0.0)
                                                )
                                                if doc_type == "41"
                                                else totals['grand_total']['InvoiceTotal']
                                            ),
                                        },
                                    ],
                                    "Name": "SUBTOTALES",
                                    "Id": 0,
                                    }] if doc_type not in ["43","44", "46","47"] else {}
                                ),
                                *([{
                                    "Info": [
                                        {
                                            "Name": "FechaNCFModificado",
                                            "Value": ref_inovice.date.strftime('%Y-%m-%d') if doc_type == "33" or doc_type == "34" else ""
                                        },
                                        {"Name": "NCFModificado", "Value": ref_inovice.l10n_latam_document_number or "" if doc_type == "33" or doc_type == "34" else ""},
                                        {"Name": "CodigoModificacion","Value": self.l10n_do_ecf_modification_code}
                                    ],
                                    "Name": "INFORMACION_REFERENCIA"
                                }] if doc_type not in ["46"] else {}),
                                { #Documento E43, E47
                                    "Info": [
                                        {
                                            "Name": "NombrePuertoSalida",
                                            "Value" : "Puerto"
                                        }
                                    ],
                                    "Name": "",
                                    "Id": 0
                                }
                            ]
                        },
                    }
                ]
            },
        }