# Deployment Progress — Odoo Enterprise 18.0

## Environment
- Odoo version: 18.0 FINAL
- Python: 3.12 (Ubuntu 24.04 Noble)
- Database: PostgreSQL 16
- Platform: Coolify

---

## Files Created

### `Dockerfile`
- Base: `ubuntu:24.04`
- Installs all system dependencies (libxml2, libldap, libpq, node-less, etc.)
- Installs `wkhtmltopdf 0.12.6.1` for PDF report generation
- Creates `odoo` user, sets workdir to `/opt/odoo/enterprise`
- Copies source from `my-odoo-enterprise/`
- Installs Python deps from `requirements.txt` and runs `pip install -e .`
- Entrypoint: `odoo-bin --config=/etc/odoo/odoo.conf`
- Exposes: `8069` (HTTP), `8072` (longpolling)

### `docker-compose.yml`
- `db` service: `postgres:16`, healthcheck on `pg_isready`
- `odoo` service: built from Dockerfile, waits for db healthy
- Ports: `expose` only (no host mapping) — Coolify assigns external ports automatically
- Volumes: `odoo_db_data`, `odoo_data` (filestore), `odoo_logs`
- Source mounted as `:ro` at `/opt/odoo/enterprise`

### `odoo.conf`
- DB: connects to `db` service (internal Docker network)
- `addons_path`: enterprise addons + core odoo addons
- `data_dir`: `/opt/odoo/data`
- `logfile`: `/opt/odoo/logs/odoo.log`
- Workers: `0` (single-threaded, change for production)
- Longpolling port: `8072`

### `.dockerignore`
- Excludes `.git`, `doc/`, `debian/`, `__pycache__`, `*.pyc`

---

## Port Strategy (Coolify)
- `expose` directive used instead of `ports: "host:container"`
- Coolify reads the exposed port and routes traffic automatically
- Odoo HTTP → `8069`
- PostgreSQL → `5432` (internal only, not reachable from outside)
- Longpolling/gevent → `8072`

---

## To Deploy on Coolify
1. Push this repo (with `my-odoo-enterprise/` included or as submodule)
2. Create a new **Docker Compose** service in Coolify
3. Point to this repo root (where `docker-compose.yml` lives)
4. Coolify will detect port `8069` and assign a domain automatically
5. First run: navigate to the domain → create initial database

---

## Production Checklist
- [ ] Change `admin_passwd` in `odoo.conf`
- [ ] Change `POSTGRES_PASSWORD` in `docker-compose.yml`
- [ ] Set `workers = 4` (or more) in `odoo.conf` for multi-worker mode
- [ ] Enable `proxy_mode = True` in `odoo.conf` (Coolify uses a reverse proxy)
- [ ] Set up SSL via Coolify's Let's Encrypt integration
- [ ] Configure SMTP for outgoing email
- [ ] Set `db_name` to a fixed DB name if single-tenant
