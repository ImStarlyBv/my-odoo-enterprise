FROM ubuntu:24.04

SHELL ["/bin/bash", "-xo", "pipefail", "-c"]

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    DEBIAN_FRONTEND=noninteractive \
    VIRTUAL_ENV=/opt/odoo/venv \
    PATH="/opt/odoo/venv/bin:$PATH"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libldap2-dev \
    libsasl2-dev \
    libtiff5-dev \
    libjpeg8-dev \
    libopenjp2-7-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libwebp-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    libxcb1-dev \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    libjpeg-dev \
    node-less \
    npm \
    git \
    curl \
    wget \
    ca-certificates \
    fonts-liberation \
    fonts-noto \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Install wkhtmltopdf (required for PDF reports)
RUN curl -sSL https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.jammy_amd64.deb -o /tmp/wkhtmltox.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb \
    && rm -rf /tmp/wkhtmltox.deb /var/lib/apt/lists/*

# Create odoo user
RUN useradd --create-home --home-dir /opt/odoo --no-log-init odoo

# Set work directory
WORKDIR /opt/odoo/enterprise

# Copy source
COPY . .

# Create virtualenv and install Python dependencies
RUN python3 -m venv /opt/odoo/venv \
    && pip install --no-cache-dir --upgrade pip wheel setuptools \
    && pip install --no-cache-dir -r requirements.txt

# Create required directories
RUN mkdir -p /opt/odoo/data /opt/odoo/logs /etc/odoo \
    && chown -R odoo:odoo /opt/odoo

# Copy odoo config
COPY odoo.conf /etc/odoo/odoo.conf
RUN chown odoo:odoo /etc/odoo/odoo.conf

USER odoo

EXPOSE 8069 8071 8072

ENTRYPOINT ["/opt/odoo/venv/bin/python3", "/opt/odoo/enterprise/odoo-bin"]
CMD ["--config=/etc/odoo/odoo.conf"]
