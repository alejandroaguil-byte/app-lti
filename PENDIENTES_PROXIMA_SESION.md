# 📌 MEMORIA Y REGISTRO DE SESIÓN — APP LTI / HALO

**Fecha de Registro:** 2026-10-06  
**Proyecto:** HALO — App Líderes TI (`/home/bobbasystem/Desarrollos/app-lti`)  
**Rama Git Activa:** `sso-portal-acceso`  
**Servidores Sincronizados:**
- Desarrollo: `bobbadeveloper` (Localhost:8000)
- Producción: `iacdi` (Tailscale `100.82.24.75:8000` / Nginx `http://127.0.0.1:8000/app-lti/`)

---

## 🛠️ TRABAJO COMPLETADO EN ESTA SESIÓN (2026-10-06)

### 1. Item 2.4: Integración en Health-Check & Auto-Restart en Producción (`iacdi`)
- **Estado:** ✅ **100% COMPLETADO Y CERTIFICADO**.
- **Instalación:** Se ejecutó con `sudo` el script de despliegue `/home/iacdi/portal-acceso/deploy/install-health-check.sh`, actualizando la copia que corre periódicamente en `/usr/local/sbin/portal-acceso-healthcheck.sh`.
- **Verificación de Health-Check:** Muestra las 6 líneas "OK" operativas (incluyendo `app-lti.service`).
- **Verificaciones de Seguridad y Resiliencia:**
  1. **Firewall / UFW:** Se ejecutó `sudo ufw status`. El puerto `8000` **no** está expuesto al exterior. El servicio `uvicorn` escucha exclusivamente en `127.0.0.1:8000` (acceso únicamente vía proxy reverso Nginx con TLS y rate-limiting).
  2. **Playwright bajo usuario `iacdi`:** Se validó la ejecución desatendida del motor Chromium v151 con el venv de producción bajo la configuración de hardening systemd (`PrivateTmp=true`, sin `MemoryDenyWriteExecute`).
  3. **Prueba de Recuperación (Auto-Restart):** Se detuvo intencionalmente `app-lti.service` y se ejecutó el health-check. El sistema detectó la caída y reinició el servicio automáticamente en 2 segundos, dejándolo nuevamente en `active (running)`.

---

### 2. Blindaje RBAC para Rol PM en Endpoints de Tickets
- **Estado:** ✅ **100% COMPLETADO Y VALIDADO**.
- **Requerimiento:** Asegurar que los usuarios con rol `PM` únicamente puedan interactuar con el formulario de Solicitud Líder TI.
- **Implementación en Backend (`backend/main.py`):**
  - Se actualizaron los decoradores de `/api/automation/create-ticket` y `/api/automation/send-ticket-email` de `get_current_user` a `require_lti_or_admin`.
  - Ahora cualquier intento de un usuario con rol `PM` de interactuar con la generación de tickets o envío de correos vía API directa es rechazado con `403 Forbidden` (`detail: "Permiso denegado. Los usuarios con rol PM solo tienen acceso al módulo de Solicitud LTI."`).
- **Pruebas Automatizadas:** Se añadió el caso `test_pm_forbidden_from_ticket_automation` en `tests/test_sso_portal_auth.py` (13/13 pruebas aprobadas).

---

### 3. Homologación de Tipografía Institucional con el Resto del Portal
- **Estado:** ✅ **100% COMPLETADO Y HOMOLOGADO**.
- **Auditoría:** Se analizaron las demás apps del portal (`asignacion-ingenieros-app`, `cv-certificaciones`, `mapa-proyecto`, `provision-plataformas`, `ausencias`, `portal-acceso`).
- **Implementación (`frontend/index.html` y `frontend/css/styles.css`):**
  - Se eliminó la dependencia externa a Google Fonts *Roboto* en `frontend/index.html`.
  - Se estandarizó la variable global `--font-sans` a la pila tipográfica nativa del sistema:
    `-apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, Helvetica, Arial, sans-serif;`
  - Se estandarizó `--font-mono` a `ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;`.
  - La apariencia visual ahora es 100% homogénea con las demás aplicaciones del Portal HALO.

---

### 4. Rediseño UI: Barra Lateral Expandible (Sidebar) & Agrupador "Configuraciones"
- **Estado:** ✅ **100% IMPLEMENTADO, TESTEADO Y DESPLEGADO**.
- **Diseño General:**
  - Se eliminó la acumulación horizontal de botones superiores.
  - Se implementó una barra lateral sticky fija a la izquierda (`.nav-subbar` / `.app-sidebar`) con el área de trabajo ocupando el 100% restante con layout fluido flexbox.
  - **Botón de Toggle Expandir / Contraer:**
    * Botón hamburguesa `#sidebar-toggle-btn` en la cabecera superior junto a la marca HALO.
    * Botón chevron `#sidebar-inner-toggle-btn` en el encabezado interno del sidebar.
  - **Modo Expandido (~250px):** Muestra iconos y nombres completos de secciones y switches.
  - **Modo Colapsado (~68px):** Modo compacto con tooltips nativos en cada icono al pasar el mouse.
  - **Persistencia:** Guarda el estado en `localStorage` (`halo_sidebar_collapsed`).
- **Secciones del Sidebar:**
  1. **📌 MÓDULOS DE NAVEGACIÓN:**
     - 📊 `Seguimiento Proyectos` (`#nav-btn-projects`)
     - 🔎 `Búsqueda Directa en Tablas` (`#nav-btn-direct-search`)
     - 🤖 `Generador de Tickets` (`#nav-btn-tickets`)
     - 📝 `Solicitud LTI` (`#nav-btn-solicitud-lti`)
     - 👥 `Usuarios` (`#nav-btn-usuarios`, protegido por RBAC, sólo ADMIN).
  2. **⚙️ CONFIGURACIONES (Switches ON/OFF):**
     - 🚦 `Salud: ON / OFF` (`#health-score-toggle-btn`)
     - ⚡ `Diagnóstico: ON / OFF` (`#diag-toggle-btn`)
     - 📄 `Ficha PDF: ON / OFF` (`#pdf-export-toggle-btn`)
     - ⏱️ `Timeline: ON / OFF` (`#timeline-toggle-btn`)
     - 🔔 `Alertas: ON / OFF` (`#alerts-toggle-btn`)
     - *Regla RBAC para PM:* Para rol PM, la sección completa de configuraciones se oculta automáticamente (`display: none;`).
  3. **👤 PIE DEL SIDEBAR:**
     - Badge de Rol (`#user-role-badge`)
     - Conmutador de Tema Claro / Oscuro (`#theme-toggle-btn`)
- **Versionado de Assets:** Cache busters actualizados a `css/styles.css?v=9.0` y `js/app.js?v=9.0`.

---

## 🧪 RESULTADOS DE PRUEBAS AUTOMATIZADAS
- `tests/test_sso_portal_auth.py`: **13/13 pasadas (100%)**
- `tests/test_functional_mantenedor_usuarios.py`: **18/18 pasadas (100%)**
- `tests/test_functional_solicitud_lti.py`: **20/20 pasadas (100%)**
- `tests/test_timeline_visual.py` & `tests/test_alertas_sla.py` & `tests/test_ficha_ejecutiva_pdf.py`: **34/34 pasadas (100%)**
- Total suites ejecutadas: **0 fallos, 100% aprobadas**.

---

## 🚀 ESTADO DE PRODUCCIÓN EN SERVIDOR `iacdi`
- Código fuente sincronizado vía `rsync` con `deploy_to_iacdi.sh`.
- Servicio `app-lti.service` reiniciado y respondiendo `200 OK` en `/api/health`.
- Todo limpio y listo para el cierre de sesión.
