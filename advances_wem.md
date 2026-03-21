# Advances — Web Enterprise Module & Docker Fix

## Session: 2026-03-21

---

## Problem 1 — Odoo running as Community instead of Enterprise

### Root Cause
- `odoo/release.py` had `version_info[-1] = ''` (Community) and `license = 'LGPL-3'`
- No `web_enterprise` module existed in `addons/` — this is the module the JS frontend
  checks to set `odoo.info.isEnterprise = true`

### Fix Applied
**`odoo/release.py`** — two lines patched:
```python
version_info = (18, 0, 0, FINAL, 0, 'e')   # was ''
license = 'OEEL-1'                           # was 'LGPL-3'
```

**New module: `addons/web_enterprise/`** — minimal workaround implementation:

| File | What it does |
|---|---|
| `__manifest__.py` | Declares module, `auto_install: True`, `license: OEEL-1`, registers assets |
| `models/ir_http.py` | Inherits `ir.http`, overrides `session_info()` to inject `server_version_info[-1] = 'e'` and `edition = 'enterprise'` into every page session |
| `static/src/webclient/home_menu/home_menu.js` | Owl component — enterprise-style full-screen app grid with search, reads from `menu_service` |
| `static/src/webclient/home_menu/home_menu.xml` | OWL template for the app grid |
| `static/src/webclient/home_menu/home_menu.scss` | Dark full-screen launcher styling (grid layout, dark bg `#1a1a2e`) |
| `static/src/enterprise_theme.scss` | Dark navbar overrides |

### Status
- Module created and committed to GitHub (`branch: 18.0`)
- Needs: Odoo restart + `--init=web_enterprise` or install via Settings > Apps on first run

---

## Problem 2 — Docker build failure (exit code 1 at pip install)

### Root Cause
```
RUN pip3 install --no-cache-dir --break-system-packages \
    wheel setuptools \
    && pip3 install --no-cache-dir --break-system-packages -r requirements.txt \
    && pip3 install --no-cache-dir --break-system-packages -e .
```
Two issues:
1. `--break-system-packages` is fragile on Ubuntu 24.04 (Noble) — pip conflicts with
   system package manager ownership of `/usr/lib/python3`
2. `pip install -e .` re-resolved all deps from `setup.py` with loose constraints,
   conflicting with the already-pinned versions from `requirements.txt`

### Fix Applied
**`Dockerfile`** — pip install section replaced with virtualenv approach:
```dockerfile
ENV VIRTUAL_ENV=/opt/odoo/venv \
    PATH="/opt/odoo/venv/bin:$PATH"

RUN python3 -m venv /opt/odoo/venv \
    && pip install --no-cache-dir --upgrade pip wheel setuptools \
    && pip install --no-cache-dir -r requirements.txt
```
**`ENTRYPOINT`** changed to use venv Python explicitly:
```dockerfile
ENTRYPOINT ["/opt/odoo/venv/bin/python3", "/opt/odoo/enterprise/odoo-bin"]
```

### Why This Works
- Virtualenv is fully isolated from system Python — no `--break-system-packages` needed
- `pip install -e .` removed — Odoo runs as a script via `odoo-bin`, no editable install needed
- `PATH` override ensures all subsequent `pip`/`python3` calls inside the container use the venv

### Status
- Committed and pushed to GitHub (`branch: 18.0`, commit `2ab06fe7ca1`)
- Awaiting Coolify redeploy to confirm build passes

---

---

## Problem 3 — `web_enterprise` not visible under Apps

### Root Cause
- `category: 'Hidden'` in `__manifest__.py` hides the module from the Apps UI
- Even with `auto_install: True`, Odoo needs to scan for new modules first before
  auto-install triggers — this scan never happened after the module was added

### Fix Applied
**`addons/web_enterprise/__manifest__.py`** — category changed:
```python
'category': 'Web',   # was 'Hidden'
```

**`docker-compose.yml`** — `--init=web_enterprise` added to startup command:
```yaml
command:
  - --config=/etc/odoo/odoo.conf
  - --init=web_enterprise
```
This forces Odoo to install the module on every container start (idempotent — safe to run repeatedly).

### Status
- Committed and pushed to GitHub (`branch: 18.0`, commit `94556ee70ad`)
- After Coolify redeploy: module appears under Settings > Apps > Web category
  and is auto-installed on startup

---

---

## Problem 4 — `database "odoo" does not exist` crash loop

### Root Cause
`--init=web_enterprise` en `docker-compose.yml` hace que Odoo intente conectarse a una
base de datos llamada `"odoo"` al arrancar. PostgreSQL solo tiene la base `"postgres"`
(definida en `POSTGRES_DB: postgres`). Sin `-d <dbname>`, Odoo defaultea a `"odoo"` → crash loop.

### Fix Applied
**`docker-compose.yml`** — eliminado `--init=web_enterprise`:
```yaml
command:
  - --config=/etc/odoo/odoo.conf
```
El módulo se instala manualmente desde la UI después del redeploy.

### Status
- Commit `981c5154a1c` pusheado a GitHub (`branch: 18.0`)

---

## Problem 5 — Módulo `web_enterprise` no aparece en Apps

### Root Cause
- Licencia `OEEL-1` en `__manifest__.py` — Odoo Community ignora módulos con esa licencia
- Sin archivo `security/ir.model.access.csv` referenciado en `data`

### Fix Applied
- `license` cambiado a `LGPL-3`
- Añadido `security/ir.model.access.csv` (vacío, sin modelos nuevos)
- Declarado en `data` del manifest

### Status
- Commit `936fe25cbaf` pusheado
- Pendiente verificar tras redeploy limpio

---

---

## Problem 6 — Módulo `web_enterprise` no aparece tras "Actualizar lista de aplicaciones"

### Root Cause
Dos causas combinadas:
1. El módulo estaba en `addons/` junto a 596 módulos enterprise. Odoo Community
   puede tener ambigüedad al escanear ese path tan grande donde conviven módulos
   community y enterprise antes de que el modo enterprise esté activo.
2. `auto_install: True` con deps ya instaladas (`web`, `base_setup`) hace que Odoo
   intente instalarlo automáticamente al hacer "Actualizar lista". Si hay cualquier
   error en assets/modelos, falla silenciosamente y no aparece en "No instalados".

### Fix Applied
- Módulo movido a `extra-addons/web_enterprise/` (directorio limpio, separado de los 596 módulos enterprise de `addons/`)
- `odoo.conf`: `extra-addons` añadido PRIMERO en `addons_path`:
  ```
  addons_path = /opt/odoo/enterprise/extra-addons,/opt/odoo/enterprise/addons,...
  ```
- Manifest: `auto_install: False`, `installable: True` explícito

### Por qué funciona
- Path limpio sin conflictos → Odoo lo escanea sin ambigüedad
- `auto_install: False` → aparece como "No instalado" en la UI, instalable manualmente
- El usuario puede verlo en **Ajustes → Aplicaciones → buscar "web_enterprise"**

### Status
- Commit `c0c1f806c88` pusheado a GitHub (`branch: 18.0`)

---

## Next Steps
- [ ] Coolify redeploy con commit `c0c1f806c88`
- [ ] Ajustes → Aplicaciones → **Actualizar lista de aplicaciones**
- [ ] Buscar `web_enterprise` en la lista → aparece como "No instalado" → Instalar
- [ ] Verificar en consola: `odoo.info.isEnterprise` → `true`
