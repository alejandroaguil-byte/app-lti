# Documento de Cierre: Remediación de Seguridad y Despliegue App LTI

**Fecha de Ejecución:** 2026-10-06  
**Ambientes Impactados:** Desarrollo (`bobbadeveloper`) y Producción (`iacdi`)  
**Documento Base:** [`REMEDIACION-APP-LTI.md`](./REMEDIACION-APP-LTI.md)  
**Estado:** **100% Aplicado y Verificado**

---

## 1. Contexto y Objetivos

A raíz de una auditoría de seguridad del Portal de Acceso (Cyber Neo), se identificaron 6 observaciones técnicas en App LTI relacionadas con exposición de red, persistencia como servicio del sistema, gestión de credenciales JWT y exposición de endpoints de documentación.

El objetivo fue aplicar las correcciones a nivel de código y de infraestructura garantizando:
1. Cero caídas o regresiones funcionales.
2. Protección de red enlazando a `127.0.0.1`.
3. Eliminación de fallbacks inseguros en el backend.
4. Despliegue del servicio hardened en producción y su inclusión en el auto-recovery del Portal de Acceso.

---

## 2. Matriz de Remediaciones Aplicadas

| # | Observación Original | Riesgo Identificado | Solución Aplicada |
|---|---|---|---|
| **1** | App ejecutada manualmente en sesión de usuario. | Caída del servicio ante reinicio de servidor o logout; sin monitoreo. | Migrado a servicio systemd `/etc/systemd/system/app-lti.service` bajo usuario `iacdi` (auto-restart habilitado). |
| **2** | Ejecución con `--reload` en producción. | Consumo excesivo de recursos y recargas inesperadas en caliente. | En producción corre en modo estándar (sin `--reload`). En desarrollo se mantiene con `--reload` vía `ENV=development`. |
| **3** | Escucha en `0.0.0.0:8000`. | Acceso directo no cifrado por LAN/Tailscale saltándose Nginx y rate limits. | Forzado a escuchar **exclusivamente en `127.0.0.1:8000`** en ambos ambientes. |
| **4** | Proceso ejecutándose con usuario personal `bobbasystem`. | Riesgo de escalamiento de privilegios al home y llaves SSH. | En producción corre con el usuario de servicio dedicado `iacdi`, con sandbox y permisos restringidos. |
| **5** | Clave secreta JWT fallback quemada en código (`backend/config.py`). | Riesgo de forja de sesiones si faltaba la variable en `.env`. | Clave quemada eliminada. El backend valida obligatoriamente `JWT_ACCESS_SECRET` o `PORTAL_JWT_SECRET`; si falta, aborta el inicio con `RuntimeError`. |
| **6** | Documentación `/docs` y `/openapi.json` expuesta en producción. | Exposición de especificaciones completas de endpoints a usuarios finales. | Documentación condicionada a `ENV=development`. En producción responde `404 Not Found`. |

---

## 3. Cambios en el Código Fuente

### 3.1 Validación Estricta de JWT (`backend/config.py`)
Se removió el literal de respaldo quemado:
```python
# Antes:
JWT_SECRET = os.getenv('JWT_SECRET', 'app-lti-super-secret-key-2026-claro')
JWT_ACCESS_SECRET = os.getenv('JWT_ACCESS_SECRET') or os.getenv('PORTAL_JWT_SECRET') or JWT_SECRET

# Ahora:
JWT_ACCESS_SECRET = os.getenv('JWT_ACCESS_SECRET') or os.getenv('PORTAL_JWT_SECRET')
if not JWT_ACCESS_SECRET:
    raise RuntimeError('Falta JWT_ACCESS_SECRET (o PORTAL_JWT_SECRET) en .env: debe ser el mismo valor que en el Portal de Acceso')
PORTAL_JWT_SECRET = JWT_ACCESS_SECRET
```

### 3.2 Ocultamiento de `/docs` y `/openapi.json` (`backend/main.py`)
Se limitaron los endpoints de Swagger y se aseguró la ruta catch-all de frontend:
```python
# Inicialización condicional de Swagger/OpenAPI:
_is_dev = os.getenv("ENV", "").lower() in ("dev", "development") or os.getenv("APP_ENV", "").lower() in ("dev", "development")
app = FastAPI(
    title="App LTI - Seguimiento Líderes TI",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None
)

# En la ruta catch-all:
@app.get("/{full_path:path}")
def serve_catch_all(full_path: str):
    if not _is_dev and full_path in ("docs", "redoc", "openapi.json"):
        raise HTTPException(status_code=404, detail="Not Found")
    file_path = os.path.join(frontend_dir, full_path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    return FileResponse(os.path.join(frontend_dir, "index.html"))
```

---

## 4. Configuración por Entorno

### 4.1 Ambiente de Desarrollo (`bobbadeveloper`)
- **Ruta del Proyecto:** `/home/bobbasystem/Desarrollos/app-lti`
- **Servicio Systemd de Usuario:** `~/.config/systemd/user/app-lti.service`
- **Configuración de Ejecución:**
  - `ExecStart="/home/bobbasystem/Desarrollos/Carga Data SM/venv/bin/uvicorn" backend.main:app --host 127.0.0.1 --port 8000 --reload`
  - `Environment="ENV=development"`
- **Verificación:**
  - `http://127.0.0.1:8000/api/health` ➔ `200 OK`
  - `http://127.0.0.1:8000/docs` ➔ `200 OK` (disponible para desarrollo)
  - Pruebas automáticas: **291 passed** (0 errores).

### 4.2 Ambiente de Producción (`iacdi`)
- **Ruta del Proyecto:** `/home/iacdi/Desarrollos/app-lti`
- **Servicio Systemd Global:** `/etc/systemd/system/app-lti.service`
  - **Usuario:** `iacdi`
  - **Escucha:** `127.0.0.1:8000` (con `--proxy-headers --forwarded-allow-ips 127.0.0.1`)
  - **Hardening:** `ProtectSystem=strict`, `ProtectHome=read-only`, `PrivateTmp=true`, `NoNewPrivileges=true`.
  - **Sin `--reload`**.
- **Archivo `.env`:** Configurado con `ENV=production`.
- **Integración con Health-Check del Portal:**
  - En `/home/iacdi/portal-acceso/deploy/healthcheck-integrated-apps.sh` se registró:
    `[app-lti]=8000`
  - El timer `portal-acceso-health-check.timer` verifica periódicamente la app en `http://127.0.0.1:8000/` y la reinicia automáticamente ante cualquier fallo o caída limpia.
- **Servicio de Usuario Desactivado:**
  - `systemctl --user disable --now app-lti` en `iacdi` para evitar colisiones de puerto.
- **Verificación:**
  - `https://127.0.0.1/app-lti/api/health` ➔ `200 OK`
  - `https://127.0.0.1/app-lti/api/lideres` ➔ `401 Unauthorized` (SSO activo)
  - `http://127.0.0.1:8000/docs` ➔ `404 Not Found` (protegido)
  - `http://127.0.0.1:8000/openapi.json` ➔ `404 Not Found` (protegido)

---

## 5. Procedimientos Operativos para el Futuro

### 5.1 Despliegue de Cambios a Producción
Para enviar nuevas versiones desde desarrollo a producción:
```bash
cd /home/bobbasystem/Desarrollos/app-lti
bash deploy_to_iacdi.sh
ssh iacdi "sudo systemctl restart app-lti"
```

### 5.2 Comprobar Logs y Estado en Producción
```bash
# Estado del servicio
ssh iacdi "systemctl status app-lti"

# Logs en tiempo real
ssh iacdi "journalctl -u app-lti -f"

# Revisar estado del chequeo de salud del Portal
ssh iacdi "systemctl status portal-acceso-health-check.service"
```

### 5.3 Rollback de Emergencia (si fuese necesario)
Si se requiriera volver atrás a la modalidad previa en el servidor `iacdi`:
```bash
ssh iacdi
sudo bash /home/iacdi/Desarrollos/app-lti/deploy/rollback-app-lti.sh
```
*(Nota: Este script reinstala la unidad transitoria manual como `bobbasystem` en `0.0.0.0:8000`).*
