# © 2018 Eneldo Serrata <eneldo@marcos.do>
# © 2018 Kevin Jiménez <kevinjimenezlorenzo@gmail.com>
# © 2018 Jorge Hernández <jhernandez@gruponeotec.com>
# © 2018 Francisco Peñaló <frankpenalo24@gmail.com>

import json
import re
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

try:
    from stdnum.do import rnc, cedula
except (ImportError, IOError) as err:
    _logger.debug(str(err))


class Odoojs(http.Controller):
    """
    Controlador web para consultas de RNC/cédula contra los servicios de la DGII.

    Expone dos endpoints públicos:
    - ``/dgii_ws``: búsqueda de contribuyentes por nombre o número (requiere
      que el parámetro del sistema ``dgii.wsmovil`` esté en ``True``).
    - ``/validate_rnc/``: valida si un número es un RNC o cédula válido y
      retorna la información del contribuyente si existe.

    Depende del paquete ``python-stdnum`` (``stdnum.do``). Si no está
    instalado, el import falla silenciosamente y los endpoints retornan vacío.
    """

    @http.route('/dgii_ws', auth='public', cors="*")
    def index(self, **kwargs):
        """
        Busca contribuyentes en el web service de la DGII por nombre o RNC/cédula.

        Solo ejecuta la consulta si el parámetro del sistema ``dgii.wsmovil``
        está activado. Retorna una lista JSON con los resultados o vacío.

        :param term: Nombre o número (9 dígitos RNC / 11 dígitos cédula) a buscar.
        :return: JSON con lista de dicts ``{rnc, name, label}`` o respuesta vacía.
        """
        term = kwargs.get("term", False)
        query_dgii_wsmovil = request.env['ir.config_parameter'].sudo().get_param(
            'dgii.wsmovil'
        )

        if term and query_dgii_wsmovil == 'True':
            if term.isdigit() and len(term) in [9, 11]:
                result = rnc.check_dgii(term)
            else:
                result = rnc.search_dgii(term, end_at=20, start_at=1)

            if result is not None:
                if not isinstance(result, list):
                    result = [result]

                for d in result:
                    # Eliminar espacios duplicados del nombre
                    d["name"] = " ".join(
                        re.split(r"\s+", d["name"], flags=re.UNICODE)
                    )
                    d["label"] = u"{} - {}".format(d["rnc"], d["name"])

                return json.dumps(result)

    @http.route('/validate_rnc/', auth='public', cors="*")
    def validate_rnc(self, **kwargs):
        """
        Valida si el número proporcionado es un RNC o cédula dominicana válida.

        Para RNC (9 dígitos) y cédula (11 dígitos) realiza la validación de
        formato con ``python-stdnum`` y opcionalmente consulta la DGII para
        obtener la razón social.

        :param rnc: Número a validar (RNC de 9 dígitos o cédula de 11 dígitos).
        :return: JSON ``{"is_valid": bool, "info": dict|None}``.
        """
        num = kwargs.get("rnc", False)
        if num.isdigit():
            if (len(num) == 9 and rnc.is_valid(num)) or (
                len(num) == 11 and cedula.is_valid(num)
            ):
                try:
                    info = rnc.check_dgii(num)
                except Exception as err:
                    info = None
                    _logger.error(">>> " + str(err))

                if info is not None:
                    # Eliminar espacios duplicados del nombre
                    info["name"] = " ".join(
                        re.split(r"\s+", info["name"], flags=re.UNICODE)
                    )

                return json.dumps({"is_valid": True, "info": info})

        return json.dumps({"is_valid": False})
