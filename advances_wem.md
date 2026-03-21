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

## Next Steps
- [ ] Trigger Coolify redeploy and confirm Docker build succeeds
- [ ] On first Odoo startup, run `--init=web_enterprise` or install via Settings > Apps
- [ ] Verify `odoo.info.isEnterprise === true` in browser console
- [ ] Install Docker Desktop locally (`winget install -e --id Docker.DockerDesktop`)
        for local testing before pushing to Coolify
