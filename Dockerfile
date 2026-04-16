FROM ubuntu:24.04

SHELL ["/bin/bash", "-xo", "pipefail", "-c"]

# -----------------------------------------------------------------------------
# DOCUMENTACIÓN DE ENTORNO:
# Definimos variables de entorno. Aseguramos que el PATH apunte al entorno
# virtual para no tener que escribir rutas absolutas al invocar python o pip.
# -----------------------------------------------------------------------------
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    DEBIAN_FRONTEND=noninteractive \
    VIRTUAL_ENV=/opt/odoo/venv \
    PATH="/opt/odoo/venv/bin:$PATH"

# Instalar dependencias del sistema operativo
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-dev python3-venv build-essential \
    libxml2-dev libxslt1-dev libldap2-dev libsasl2-dev libtiff5-dev \
    libjpeg8-dev libopenjp2-7-dev zlib1g-dev libfreetype6-dev liblcms2-dev \
    libwebp-dev libharfbuzz-dev libfribidi-dev libxcb1-dev libpq-dev \
    libssl-dev libffi-dev libjpeg-dev node-less npm git curl wget \
    ca-certificates fonts-liberation fonts-noto fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Instalar wkhtmltopdf
RUN curl -sSL https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.jammy_amd64.deb -o /tmp/wkhtmltox.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb \
    && rm -rf /tmp/wkhtmltox.deb /var/lib/apt/lists/*

# Crear usuario odoo
RUN useradd --create-home --home-dir /opt/odoo --no-log-init odoo

# -----------------------------------------------------------------------------
# CORRECCIÓN ESTRUCTURAL 1: PREPARACIÓN DE DIRECTORIOS COMO ROOT
# Creamos las carpetas necesarias y asignamos permisos a Odoo ANTES de copiar
# los miles de archivos del código fuente.
# -----------------------------------------------------------------------------
RUN mkdir -p /opt/odoo/data /etc/odoo /opt/odoo/enterprise \
    && chown -R odoo:odoo /opt/odoo /etc/odoo

# Definir directorio de trabajo
WORKDIR /opt/odoo/enterprise

# -----------------------------------------------------------------------------
# CORRECCIÓN ESTRUCTURAL 2: CAMBIO DE USUARIO TEMPRANO
# Pasamos a ejecutar comandos como 'odoo'. Esto asegura que el entorno virtual
# y todo lo que instalemos le pertenezca sin usar comandos chown posteriores.
# -----------------------------------------------------------------------------
USER odoo

# -----------------------------------------------------------------------------
# CORRECCIÓN ESTRUCTURAL 3: SEPARAR DEPENDENCIAS DEL CÓDIGO
# Copiamos SOLO el archivo requirements.txt. Si cambias código en tu proyecto
# pero no tocas este archivo, Docker usará su caché y saltará esta instalación.
# -----------------------------------------------------------------------------
COPY --chown=odoo:odoo requirements.txt ./

# Creamos el venv e instalamos dependencias.
RUN python3 -m venv /opt/odoo/venv \
    && pip install --no-cache-dir --upgrade pip wheel setuptools \
    && pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# CORRECCIÓN ESTRUCTURAL 4: COPIAR EL CÓDIGO CON PERMISOS NATIVOS
# Copiamos el resto del proyecto aplicando el flag --chown directamente.
# Esto evita que Docker cree una nueva capa para duplicar archivos solo para
# cambiar permisos (lo que causaba tus 5 minutos de espera).
# -----------------------------------------------------------------------------
COPY --chown=odoo:odoo . .

# Copiar archivo de configuración
COPY --chown=odoo:odoo odoo.conf /etc/odoo/odoo.conf

EXPOSE 8069 8071 8072

# Punto de entrada y comando
ENTRYPOINT ["/opt/odoo/venv/bin/python3", "/opt/odoo/enterprise/odoo-bin"]
CMD ["--config=/etc/odoo/odoo.conf"]
