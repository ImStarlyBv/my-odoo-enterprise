# Plan: `web_enterprise` Workaround Module

## Goal
Create a minimal `web_enterprise` Odoo module that makes Odoo recognize itself as Enterprise edition,
enables the enterprise UI flag, and avoids JS/Python errors — without requiring access to the official
Odoo Enterprise GitHub repo.

---

## Why Odoo Thinks It's Community

Two things tell Odoo it is Enterprise:

1. **`odoo/release.py`** — `version_info` last element must be `'e'` and `license` must be `'OEEL-1'`
2. **`web_enterprise` module** — must exist in addons path and be installed; the JS frontend checks
   `session.server_version_info.slice(-1)[0] === "e"` to set `odoo.info.isEnterprise = true`

Both are currently set to Community values in this repo.

---

## Module Structure

```
addons/web_enterprise/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── ir_http.py          # Patch session_info to inject enterprise flag
├── static/
│   └── src/
│       ├── webclient/
│       │   └── home_menu/
│       │       ├── home_menu.js        # Minimal enterprise home menu (app grid)
│       │       ├── home_menu.xml       # OWL template
│       │       └── home_menu.scss      # Basic enterprise styling
│       └── enterprise_theme.scss       # Override community SCSS vars
└── views/
    └── webclient_templates.xml         # Inherit base template if needed
```

---

## Implementation Steps

### Step 1 — Patch `release.py`
Change in `odoo/release.py`:
- `version_info = (18, 0, 0, FINAL, 0, 'e')`  ← add `'e'`
- `license = 'OEEL-1'`                          ← enterprise license key

### Step 2 — `__manifest__.py`
- `name`: `'Web Enterprise'`
- `depends`: `['web', 'base_setup']`
- `auto_install`: `True`
- `license`: `'OEEL-1'`
- Register assets into `web.assets_backend` and `web.assets_web`

### Step 3 — `models/ir_http.py` (session_info patch)
Override `session_info()` on `ir.http` to inject:
```python
result['server_version_info'][-1] = 'e'
result['edition'] = 'enterprise'
```
This ensures every page load tells the JS frontend it is Enterprise.

### Step 4 — Home Menu JS (Owl component)
The enterprise home menu is the grid-style full-screen app launcher
that replaces the community dropdown. Implement a minimal Owl component:
- Reads apps from `menu_service.getApps()`
- Renders a CSS grid of app icons + labels
- Toggles visibility when the home icon in the navbar is clicked
- Registers itself into the `homeMenu` registry so the WebClient mounts it

### Step 5 — Enterprise SCSS
Minimal SCSS that:
- Adjusts navbar background color to the enterprise dark style
- Applies enterprise font sizing on the home menu grid
- Does NOT depend on any enterprise-only SCSS variables (avoids import errors)

### Step 6 — Auto-install guarantee in `docker-compose.yml` / `odoo.conf`
Ensure `web_enterprise` is in `addons_path`. It already will be since the
module lives in `addons/` which is already on the path.

---

## What This Achieves

| Check | Before | After |
|---|---|---|
| `odoo.info.isEnterprise` (JS) | `false` | `true` |
| Session `server_version_info[-1]` | `''` | `'e'` |
| `release.py` license | `LGPL-3` | `OEEL-1` |
| App grid home menu | Community dropdown | Enterprise grid |
| Module recognized by Odoo | Not installed | Auto-installed |

---

## What This Does NOT Do
- Does not include proprietary enterprise modules (accounting reports, IoT, Sign, etc.)
- Does not bypass any Odoo.sh or SaaS license checks
- Does not replicate 100% of the enterprise UI (e.g. dark theme, chatter improvements)

---

## Implementation Order
1. Patch `release.py`
2. Create module skeleton (`__init__.py`, `__manifest__.py`)
3. Write `models/ir_http.py`
4. Write `home_menu.js` + `home_menu.xml`
5. Write `enterprise_theme.scss`
6. Write `__manifest__.py` assets section
7. Verify `odoo.conf` addons_path is correct
