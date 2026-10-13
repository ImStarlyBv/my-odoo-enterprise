# web_community_ui

Modulo para Odoo 18 que traslada una interfaz de cliente web mejorada (menu de
inicio, barra de navegacion y modo oscuro) a una instancia de **Odoo
Community**.

---

## Proposito

Aportar unicamente la capa de interfaz mejorada. El modulo:

- **No** detecta ni simula la edicion (no parchea `odoo.release`).
- **No** contiene logica de suscripcion, caducidad ni avisos de compra.
- **No** promociona ni instala productos de pago.
- **No** descarga ni habilita modulos de pago.

Es, en la practica, una *skin* de UI sobre Community.

---

## Que incluye

### Cliente web
- `static/src/main.js` reemplaza el entrypoint de `web` y arranca
  `WebClientUI`.
- Barra de navegacion mejorada (`webclient/navbar`).
- Menu de inicio con grid de apps, buscador y reordenacion por drag & drop
  (`webclient/home_menu`).
- Menu hamburguesa (`webclient/burger_menu`) y accion de compartir URL
  (`webclient/share_url`).
- Modo oscuro / claro (`webclient/color_scheme`).
- Ajustes de vistas para movil (`views/pivot`).

### Estilos
- Variables de color y espaciado (`static/src/scss/*.variables.scss`).
- Hojas de estilo especificas: navbar, menu de inicio, list, kanban, etc.
- Variantes `.dark.scss` para modo oscuro.

---

## Que NO incluye

| Capacidad | Estado |
|---|---|
| Deteccion / spoofing de edicion de pago | No |
| Panel de caducidad o aviso de compra | No |
| Suscripcion o ping a odoo.com | No |
| Promocion / instalacion de productos de pago | No |
| Descarga o habilitacion de modulos de pago | No |

---

## Instalacion

1. Copia la carpeta `web_community_ui` dentro de tu `addons_path`.
2. Reinicia el servidor Odoo.
3. Activa el modo desarrollador.
4. Ve a **Aplicaciones -> Actualizar lista de aplicaciones**.
5. Busca **Web Community UI** e instala.

---

## Dependencias

- `web`
- `base_setup`

---

## Traducciones

- Espanol: `i18n/es.po`
- Plantilla base (ingles de origen): `i18n/web_community_ui.pot`

---

## Version y licencia

| Campo | Valor |
|---|---|
| Version | 18.0.1.0.0 |
| Licencia | LGPL-3 |
| Categoria | Web |
