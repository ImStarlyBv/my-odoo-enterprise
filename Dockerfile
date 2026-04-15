# -----------------------------------------------------------------------------
# DOCUMENTACIÓN:
# Usar la imagen oficial ahorra descargas, instalaciones de sistema (apt) y
# compilaciones de Python. Odoo ya se encarga de optimizarla.
# -----------------------------------------------------------------------------
FROM odoo:18.0

# Cambiamos a root momentáneamente por si necesitamos instalar algo extra,
# aunque Odoo 18 ya trae el 99% de los requerimientos de módulos base.
USER root

# 1. Copiamos tus requerimientos extra (si los tienes)
COPY ./requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# 2. Copiamos tu código directamente a la carpeta de módulos extra de Odoo
# Odoo monta y lee sus módulos custom desde /mnt/extra-addons automáticamente.
COPY --chown=odoo:odoo . /mnt/extra-addons/

# Volvemos al usuario seguro de Odoo
USER odoo

# La imagen base de Odoo ya tiene el ENTRYPOINT y EXPOSE configurados.
