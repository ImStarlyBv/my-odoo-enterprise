# -----------------------------------------------------------------------------
# DOCUMENTACIÓN DE ESTRUCTURA PARA ODOO 18:
# 1. Heredamos la imagen oficial. Odoo S.A. ya resolvió las dependencias del SO.
# 2. El cambio a 'root' es obligatorio para usar pip install.
# 3. Aplicamos '--break-system-packages' para sobreescribir la restricción PEP 668.
# 4. Aplicamos '--ignore-installed' para evitar que pip intente desinstalar
#    paquetes nativos de Debian (como cryptography) que rompen el despliegue.
# 5. Los módulos se inyectan en /mnt/extra-addons, que Odoo lee por defecto.
# -----------------------------------------------------------------------------
FROM odoo:18.0

USER root

# Inyectar dependencias y forzar la instalación omitiendo desinstalaciones de sistema
COPY ./requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --break-system-packages --ignore-installed -r /tmp/requirements.txt

# Copiar el código fuente con los permisos correctos al directorio de addons
COPY odoo.conf /etc/odoo/odoo.conf 
COPY --chown=odoo:odoo . /mnt/extra-addons/

# Regresar al usuario de bajo privilegio para ejecución segura
USER odoo
