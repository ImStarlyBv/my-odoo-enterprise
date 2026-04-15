# -----------------------------------------------------------------------------
# DOCUMENTACIÓN DE ESTRUCTURA PARA ODOO 18:
# 1. Heredamos la imagen oficial. Odoo S.A. ya resolvió las dependencias del SO,
#    wkhtmltopdf y la compilación de Python.
# 2. El cambio a 'root' es obligatorio temporalmente para usar pip install.
# 3. Aplicamos '--break-system-packages' conscientemente. Al estar en un
#    contenedor Docker aislado, sobreescribir la restricción PEP 668 de Debian
#    es seguro y necesario para instalar las dependencias de tus módulos custom.
# 4. Los módulos se inyectan en /mnt/extra-addons, que Odoo lee por defecto.
# -----------------------------------------------------------------------------
FROM odoo:18.0

USER root

# Inyectar dependencias y forzar la instalación global en el contenedor
COPY ./requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

# Copiar el código fuente con los permisos correctos al directorio de addons
COPY --chown=odoo:odoo . /mnt/extra-addons/

# Regresar al usuario de bajo privilegio para ejecución segura
USER odoo
