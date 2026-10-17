# App LTI — Observaciones de seguridad y remediación propuesta

**Fecha:** 2026-10-06
**Origen:** auditoría de seguridad del Portal de Acceso (Cyber Neo). Al revisar el portal se detectaron estos puntos en App LTI.
**Estado:** nada aplicado. Los scripts están listos en esta misma carpeta (`deploy/`) para revisarlos y ejecutarlos cuando se acuerde.

---

## 1. Observaciones

| # | Observación | Riesgo |
|---|---|---|
| 1 | La app corre **a mano** desde una sesión de `bobbasystem` (`uvicorn ... --reload`), no como servicio systemd. | Si el servidor se reinicia o se cierra ese proceso, **la app queda caída** y nadie se entera. El health-check del portal no la vigila. |
| 2 | Corre en **modo desarrollo** (`--reload`). | Recarga el código en vivo cada vez que alguien guarda un archivo, incluso a medio editar. Consume más recursos. |
| 3 | Escucha en **todas las interfaces** (`--host 0.0.0.0 --port 8000`). | Además de nginx (`/app-lti/`), se puede entrar directo por la LAN (`192.168.10.20:8000`) o Tailscale (`100.82.24.75:8000`), **sin HTTPS** y sin el límite de peticiones de nginx. Los datos piden login, pero esa puerta no debería existir. El firewall tiene política DROP por defecto; hay que confirmar que no exista una regla que abra el 8000. |
| 4 | Corre con el **usuario personal** de un desarrollador. | Si alguien explota una falla de la app, obtiene los permisos de ese usuario (su home, sus llaves SSH, etc.). |
| 5 | `backend/config.py:49-50`: si falta `JWT_ACCESS_SECRET`, la app usa una **clave JWT de respaldo escrita en el código**. | Hoy el `.env` sí define la clave, así que no es explotable. Pero si alguna vez falta la variable, cualquiera que conozca el literal (también aparece documentado en `LEVANTAMIENTO.md` del portal) podría **forjar sesiones**. |
| 6 | La documentación de la API (`/docs`, `/openapi.json`) es pública. | Expone todos los endpoints y sus parámetros. Riesgo bajo. |

Revisado y **sin problemas**: la app no escribe archivos propios; `seed_default_users()` solo registra nombres y roles (sin contraseñas, el login es por SSO); importar `backend.main` no tiene efectos secundarios (el seed corre en `lifespan`); Chromium (Playwright) ya se lanza con `--no-sandbox`.

---

## 2. Remediación propuesta

### 2.1 Servicio systemd (observaciones 1–4) — requiere sudo

Archivos en esta carpeta:

| Archivo | Qué hace |
|---|---|
| `app-lti.service` | Servicio: usuario `iacdi` (igual que las demás apps), **solo `127.0.0.1:8000`** (nginx es la única entrada), **sin `--reload`**, se reinicia si se cae, arranca con el servidor y tiene hardening (sistema de archivos de solo lectura salvo `data/`, donde se guardan los adjuntos de proyectos, `/tmp` privado, etc.). |
| `install-app-lti.sh` | Instalador (ver detalle abajo). |
| `rollback-app-lti.sh` | Vuelve exactamente a como está hoy (proceso de `bobbasystem` en `0.0.0.0:8000` con `--reload`). |

El instalador hace esto, en orden:
1. **Pruebas previas como `iacdi` y con el mismo sandbox del servicio**: que la app importe y que **Chromium arranque**. Si algo falla, **aborta sin tocar nada**.
   - Lo más probable es que falle Chromium si `iacdi` no tiene descargados los navegadores de Playwright (hoy seguramente están solo en el home de `bobbasystem`). El script indica cómo instalarlos.
2. Instala y habilita la unidad.
3. Detiene el proceso manual y arranca el servicio (**corte de unos segundos**).
4. Verifica `/api/health`; **si no responde, vuelve solo al proceso manual**.

### 2.2 Clave JWT de respaldo (observación 5) — cambio de código en tu repo

En `backend/config.py`, reemplazar las líneas 49-50 para que la app **no arranque** si falta la clave:

```python
# Antes
JWT_SECRET = os.getenv('JWT_SECRET', '<literal>')
JWT_ACCESS_SECRET = os.getenv('JWT_ACCESS_SECRET') or os.getenv('PORTAL_JWT_SECRET') or JWT_SECRET

# Después
JWT_ACCESS_SECRET = os.getenv('JWT_ACCESS_SECRET') or os.getenv('PORTAL_JWT_SECRET')
if not JWT_ACCESS_SECRET:
    raise RuntimeError('Falta JWT_ACCESS_SECRET (o PORTAL_JWT_SECRET) en .env: debe ser el mismo valor que en el Portal de Acceso')
```

`JWT_SECRET` solo se usa en esa línea (verificado con grep en `backend/`), así que se puede eliminar. El literal antiguo hay que darlo por **quemado**: no usarlo nunca como clave real.

### 2.3 Documentación de la API (observación 6) — cambio de código, opcional

En `backend/main.py`, desactivar `/docs` en producción:

```python
app = FastAPI(title="App LTI - Seguimiento Líderes TI", version="2.0.0", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
```

(o condicionarlo a una variable de entorno si se usa en desarrollo).

### 2.4 Agregar App LTI al health-check del portal — después de 2.1

El health-check reinicia automáticamente las apps que dejan de responder. Una vez instalado el servicio:
1. En `/home/iacdi/portal-acceso/deploy/healthcheck-integrated-apps.sh` agregar la línea `[app-lti]=8000` dentro de `SERVICES=( ... )`.
2. `sudo bash /home/iacdi/portal-acceso/deploy/install-health-check.sh`

(`/` responde 200, que es lo que revisa el health-check.)

### 2.5 Cómo seguir desarrollando

El servicio queda para producción. Para desarrollar con recarga automática, levantar **otra** instancia desde tu copia de trabajo, en otro puerto y solo en localhost:

```bash
cd ~/Desarrollos/app-lti      # tu repo, no la copia desplegada
venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload
```

---

## 3. Comandos

```bash
# 0) Revisar los archivos antes de ejecutar nada
cat /home/iacdi/Desarrollos/app-lti/deploy/app-lti.service
cat /home/iacdi/Desarrollos/app-lti/deploy/install-app-lti.sh

# 1) Confirmar que el firewall no abre el 8000 (no debería mostrar nada)
sudo ufw status | grep 8000

# 2) Instalar (si aborta por Chromium, ver el paso 2b)
sudo bash /home/iacdi/Desarrollos/app-lti/deploy/install-app-lti.sh

# 2b) Solo si el instalador lo pide: descargar Chromium para iacdi y repetir el paso 2
sudo -u iacdi /home/iacdi/Desarrollos/app-lti/venv/bin/playwright install chromium

# Volver atrás (si algo no funciona)
sudo bash /home/iacdi/Desarrollos/app-lti/deploy/rollback-app-lti.sh
```

---

## 4. Set de pruebas

### 4.1 Antes de instalar

| # | Prueba | Comando | Esperado |
|---|---|---|---|
| A1 | Estado actual | `ss -ltn '( sport = :8000 )'` | `0.0.0.0:8000` (situación actual) |
| A2 | App responde | `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/health` | `200` |
| A3 | Firewall | `sudo ufw status \| grep 8000` | sin resultados |

### 4.2 Después de instalar

| # | Prueba | Comando | Esperado |
|---|---|---|---|
| P1 | Servicio activo y habilitado | `systemctl is-active app-lti; systemctl is-enabled app-lti` | `active` / `enabled` |
| P2 | Corre como iacdi | `systemctl show app-lti -p User` | `User=iacdi` |
| P3 | Solo escucha en localhost | `ss -ltn '( sport = :8000 )'` | `127.0.0.1:8000` (ya **no** `0.0.0.0`) |
| P4 | Sin `--reload` | `ps -o args= -p $(systemctl show app-lti -p MainPID --value)` | sin `--reload` |
| P5 | Health local | `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/health` | `200` |
| P6 | Vía nginx | `curl -sk -o /dev/null -w '%{http_code}\n' https://127.0.0.1/app-lti/` | `200` |
| P7 | **Acceso directo bloqueado** (desde OTRO equipo de la red) | `curl -m 5 http://192.168.10.20:8000/api/health` | falla (conexión rechazada o timeout) |
| P8 | Funcional | Entrar al Portal → App LTI → listar proyectos, abrir una ficha | funciona igual que antes |
| P9 | **Playwright** | Ejecutar una automatización de ticket (en modo prueba si existe) | Chromium arranca y el flujo termina |
| P10 | Se recupera si se cae | `sudo systemctl kill -s SIGKILL app-lti; sleep 5; systemctl is-active app-lti` | `active` (systemd lo levantó solo) |
| P11 | Logs limpios | `journalctl -u app-lti -n 50 --no-pager` | sin errores |

### 4.3 Prueba de rollback (opcional)

| # | Prueba | Comando | Esperado |
|---|---|---|---|
| R1 | Volver atrás | `sudo bash .../deploy/rollback-app-lti.sh` | "App LTI de vuelta como antes" |
| R2 | Estado restaurado | `ss -ltn '( sport = :8000 )'` | `0.0.0.0:8000` |
| R3 | Reinstalar | `sudo bash .../deploy/install-app-lti.sh` | igual que P1–P6 |

### 4.4 Después del cambio de código (2.2)

| # | Prueba | Esperado |
|---|---|---|
| C1 | Arrancar con `JWT_ACCESS_SECRET` comentado en `.env` (en tu entorno de desarrollo) | la app **no arranca** y muestra el mensaje de error |
| C2 | Con la variable definida | login por SSO funciona normal |
