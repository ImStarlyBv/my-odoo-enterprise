# web_enterprise

Modulo complementario para Odoo 18 que habilita la interfaz de edicion Enterprise y suprime los avisos de compra de modulos.

---

## Proposito

Este modulo **no descarga ni otorga licencias de Odoo Enterprise**. Su funcion es permitir que una instancia de Odoo Community reconozca y ejecute modulos que requieren la edicion Enterprise, siempre que esos modulos ya hayan sido obtenidos por medios legales y se encuentren fisicamente en el servidor.

> **Importante:** Para usar modulos Enterprise debes contar con una licencia valida de Odoo Enterprise o haberlos adquirido directamente en [https://apps.odoo.com](https://apps.odoo.com). Este modulo no reemplaza ni elude dicha licencia.

---

## Que hace

### 1. Identifica la instancia como Enterprise

Extiende `ir.http` para modificar la informacion de sesion que el servidor envia al navegador:

- Establece el campo `edition` en `'enterprise'`.
- Agrega el marcador `'e'` al final de `server_version_info`.

Esto hace que el cliente JavaScript active las rutas de codigo y componentes exclusivos de la edicion Enterprise.

### 2. Elimina los avisos de compra

Extiende `ir.module.module` para forzar el campo `to_buy = False` en todos los modulos:

- Sobreescribe los metodos `create()` y `write()` para que ningun modulo sea marcado como "por comprar".
- Los hooks `post_init_hook` y `post_migrate_hook` limpian ese flag en la base de datos al instalar o migrar el modulo.

De esta forma desaparecen los botones y avisos que piden adquirir modulos desde la tienda integrada de Odoo.

### 3. Menu de aplicaciones estilo Enterprise

Incluye un componente OWL (`HomeMenu`) que reemplaza el lanzador de aplicaciones predeterminado:

- Grilla de iconos con nombre de cada aplicacion.
- Campo de busqueda para filtrar apps en tiempo real.
- Tema oscuro (`#1a1a2e`) coherente con la estetica Enterprise.

---

## Lo que este modulo NO hace

| Capacidad | Estado |
|---|---|
| Descargar modulos desde apps.odoo.com | No |
| Autenticar una licencia Enterprise con Odoo S.A. | No |
| Habilitar funciones Enterprise sin tener el codigo fuente | No |
| Reemplazar una suscripcion Enterprise oficial | No |

Para instalar un modulo Enterprise debes colocar su carpeta en el `addons_path` del servidor de forma manual, igual que cualquier otro modulo de terceros.

---

## Instalacion

1. Copia la carpeta `web_enterprise` dentro de tu `addons_path`.
2. Reinicia el servidor Odoo.
3. Activa el modo desarrollador.
4. Ve a **Aplicaciones → Actualizar lista de aplicaciones**.
5. Busca **Web Enterprise** e instala.

---

## Dependencias

- `web`
- `base_setup`

---

## Version y licencia

| Campo | Valor |
|---|---|
| Version | 18.0.1.0.0 |
| Licencia | LGPL-3 |
| Categoria | Web |
