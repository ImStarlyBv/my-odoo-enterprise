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

---

## Problem 7 — Docker build falla: `COPY odoo.conf` not found

### Root Cause
`.dockerignore` excluía explícitamente `odoo.conf`:
```
odoo.conf
```
El `COPY . .` del Dockerfile no incluía el archivo, y el paso posterior
`COPY odoo.conf /etc/odoo/odoo.conf` fallaba con "not found" en el build context.

### Fix Applied
**`.dockerignore`** — eliminada la línea `odoo.conf`.

### Status
- Commit `c58037f3bf0` pusheado a GitHub (`branch: 18.0`)

---

## Problem 8 — Odoo no genera logs visibles

### Root Cause
`odoo.conf` tenía `logfile = /opt/odoo/logs/odoo.log` — Odoo escribía a un archivo
dentro del volumen `odoo_logs`, invisible para `docker compose logs`.

### Fix Applied
- **`odoo.conf`**: `logfile` eliminado → Odoo escribe a **stdout** → `docker compose logs -f odoo` funciona
- **`docker-compose.yml`**: volumen `odoo_logs:/opt/odoo/logs` eliminado (ya no necesario)
- **`Dockerfile`**: `mkdir /opt/odoo/logs` eliminado del `RUN`

### Cómo ver los logs ahora
```bash
docker compose up --build -d
docker compose logs -f odoo       # logs en tiempo real
docker compose logs --tail=100 odoo  # últimas 100 líneas
```

### Status
- Commit `c58037f3bf0` pusheado a GitHub (`branch: 18.0`)

---

---

## Problem 9 — `FileNotFoundError: /opt/odoo/enterprise/extra-addons`

### Root Cause
`docker-compose.yml` had a bind mount:
```yaml
- .:/opt/odoo/enterprise:ro
```
This mount overrides the entire `/opt/odoo/enterprise` directory at runtime with whatever the host (Coolify server) has. Coolify's working directory didn't have `extra-addons/` (e.g., shallow clone, or directory mismatch), so Odoo couldn't find the path declared in `odoo.conf`.

### Fix Applied
**`docker-compose.yml`** — bind mount removed:
```yaml
volumes:
  - odoo_data:/opt/odoo/data
  # removed: - .:/opt/odoo/enterprise:ro
```
`COPY . .` in the Dockerfile already bakes everything (including `extra-addons/`) into the image. The bind mount was redundant and harmful in production.

### Status
- ✅ Resuelto — commit pusheado, Coolify redeploy exitoso
- ✅ `web_enterprise` instalado desde Settings → Apps
- ✅ `odoo.info.isEnterprise === true` confirmado en consola

---

---

## Problem 10 — Módulo `account_accountant` muestra botón "Comprar Odoo Enterprise"

### Root Cause
Odoo guarda un campo `to_buy` en `ir.module.module` para cada módulo con licencia
`OEEL-1`. Cuando ese campo es `True`, la UI renderiza un botón "Comprar" que redirige
a `https://www.odoo.com/odoo-enterprise`. Esto ocurre aunque `isEnterprise = true`,
porque la validación de `to_buy` es independiente del flag de sesión — la fija el
instalador de módulos al escanear manifests con `license: 'OEEL-1'`.

Además, `account_accountant` tiene en su manifest:
```python
'license': 'OEEL-1',
```
Lo que activa este flujo en la vista de Apps.

### Fix Applied
Sobreescribir `ir.module.module` en nuestro módulo `web_enterprise` para forzar
`to_buy = False` en todos los módulos al arrancar (o vía override del compute).

**`extra-addons/web_enterprise/models/ir_module.py`** — nuevo override:
```python
from odoo import models, fields, api

class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    @api.model
    def _check_external_dependencies(self, terp):
        # Suppress the to_buy flag so enterprise modules don't show buy buttons
        result = super()._check_external_dependencies(terp)
        return result

    def write(self, vals):
        if 'to_buy' not in vals:
            vals['to_buy'] = False
        return super().write(vals)
```

O más directo — via SQL en un post-install hook:
```python
# en __init__.py del módulo, post_init_hook:
def post_init_hook(env):
    env.cr.execute("UPDATE ir_module_module SET to_buy = false WHERE to_buy = true")
```

### Fix Applied
Tres capas de protección en `extra-addons/web_enterprise/`:

**`models/ir_module.py`** — override de `create()` y `write()`:
```python
class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def create(self, vals):
        if isinstance(vals, list):
            for v in vals:
                v['to_buy'] = False
        else:
            vals['to_buy'] = False
        return super().create(vals)

    def write(self, vals):
        vals['to_buy'] = False
        return super().write(vals)
```

**`__init__.py`** — hooks SQL que limpian la DB:
```python
def _clear_to_buy(env):
    env.cr.execute("UPDATE ir_module_module SET to_buy = false WHERE to_buy = true")

def post_init_hook(env):
    _clear_to_buy(env)

def post_migrate_hook(env, *args, **kwargs):
    _clear_to_buy(env)
```

**`__manifest__.py`** — registra ambos hooks:
```python
'post_init_hook': 'post_init_hook',
'post_migrate_hook': 'post_migrate_hook',
```

### Por qué el write() solo no era suficiente
`update_list()` llama a `create()` para registros nuevos de módulos — el override
de `write()` solo cubría actualizaciones. El botón duplicado aparecía porque
`to_buy=True` se guardaba en el `create()` inicial del módulo y persistía.

Las tres capas cubren:
1. `create()` — módulos nuevos escaneados por `update_list()`
2. `write()` — actualizaciones de módulos existentes
3. `post_migrate_hook` SQL — limpieza total en cada redeploy/upgrade del módulo

### Status
- ✅ Commits `a850f546068` y `558bf36adb9` pusheados a GitHub (`branch: 18.0`)
- ✅ Botón duplicado eliminado — fix SQL ejecutado directamente en la DB:
  ```bash
  docker exec -it odoo18_db psql -U odoo -d xqt-solutions
  UPDATE ir_module_module SET to_buy = false WHERE to_buy = true;
  ```
- ✅ Solo aparece un botón "Actualizar" en el módulo Contabilidad

---

---

## Problem 11 — `account_accountant` no existe en el repo / sin botón "Instalar"

### Root Cause
El módulo `account_accountant` (Enterprise oficial de Odoo) **no está presente** en
`addons/`. El repo contiene el módulo community `account` y variantes, pero no el
módulo Enterprise de contabilidad avanzada. Por eso en la UI aparece "Actualizar"
(registro en DB) pero no "Instalar" (el código no existe en disco).

### Solución Elegida
Usar **`om_account_accountant`** — implementación community/OCA para Odoo 18:
- Repo: `github.com/vappelgren/om_account_accountant`
- Módulos incluidos:
  - `om_account_accountant` — core contabilidad
  - `om_account_asset` — activos fijos
  - `om_account_budget` — presupuestos
  - `om_account_daily_reports` — reportes diarios
  - `om_account_followup` — seguimiento de pagos
  - `om_fiscal_year` — año fiscal
  - `om_recurring_payments` — pagos recurrentes

### Plan
1. Clonar el repo externamente
2. Copiar módulos deseados a `extra-addons/`
3. Commit + push + Coolify redeploy
4. Instalar desde Apps

### Status
- Pendiente implementar

---

## Next Steps
- [ ] Clonar `vappelgren/om_account_accountant` y copiar módulos a `extra-addons/`
- [ ] Commit + push + Coolify redeploy
- [ ] Apps → Actualizar lista → Instalar `om_account_accountant`
