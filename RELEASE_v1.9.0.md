# 🚀 Release v1.9.0 — Asignación Directa de LTI, Interfaz HALO Simplificada y Protección de Datos Productivos

**Fecha de Lanzamiento:** 16 de Octubre de 2026  
**Rama Base:** `main`  
**Tag:** `v1.9.0` (código desplegado: `b6952ab`; el tag agrega solo esta documentación)  
**Versión anterior:** `v1.8.0`

---

## 🌟 Resumen de la Versión

Esta versión permite asignar un Líder TI a cualquier proyecto, incluidos los que solo existen en el backlog de operaciones SGA, y garantiza que los coordinadores puedan hacerlo sin importar su rol. Además simplifica la interfaz HALO en tres fases (navegación, iconografía y tablero), agrupa las alertas SLA por proyecto, incorpora un tour guiado para PMs y blinda la ejecución de pruebas y el envío de correos frente a la base de datos productiva compartida.

---

## 📦 Nuevas Funcionalidades y Mejoras

### 1. Asignación Directa de LTI
- **Asignadores autorizados**: `alejandro.aguilar` y `pablo.castillo` nunca quedan por debajo del rol `LTI`. Si el Portal (`"lectura"`) o el rol local los dejaría como `PM`, su rol efectivo pasa a `LTI`. Siguen necesitando acceso en el Portal y estar activos. Lista configurable en `LTI_ASSIGNER_USERNAMES` (`backend/config.py`).
- **Asignación desde el backlog**: nuevo botón **Asignar LTI** en Búsqueda → Solots (`CT_BACKLOG_OPERACIONES2`), con endpoint `POST /api/backlog/asignar-lti` (roles `LTI`/`ADMIN`):
  - Si el proyecto ya existe en `dbo.Proyectos`, solo cambia `LT_Asignado`.
  - Si no existe, se crea con el cliente y el PM del backlog, estado `Generado`.
  - La tabla del backlog nunca se modifica.
  - Si el proyecto no tenía LTI, se envía el correo de asignación habitual.
- Las solicitudes creadas por los PM se siguen asignando desde Proyectos → "⋯" → **Editar**.

### 2. Interfaz HALO Simplificada
- **Fase 1 — Navegación**: menú lateral con 4 módulos y grupo Administración → Usuarios; menú de usuario único en la cabecera (tema, preferencias solo ADMIN, cerrar sesión); clic en la fila abre el proyecto y las acciones pasan al menú "⋯"; Eliminar solo dentro del detalle; Hitos dentro de Resumen y pestaña Historial.
- **Fase 2 — Iconos y color**: set único de iconos de línea (`frontend/js/icons.js`) sin emojis en la página; color con significado (rojo HALO solo para acción principal, activo, eliminar y crítico; teal para información); sin jerga técnica visible.
- **Fase 3 — Tablero**: 4 KPI principales (asignados, en curso, pendientes de asignar, efectividad); salud como filtro segmentado sobre la tabla.

### 3. Alertas SLA Agrupadas por Proyecto
- La campana cuenta proyectos con atrasos en lugar de ítems sueltos; cada tarjeta muestra contadores, mayor atraso y acceso directo "Ver proyecto".
- `GET /api/alertas/sla` agrega `proyectos` y nuevos totales en `resumen` (cambio aditivo, sin romper campos existentes).

### 4. Tour Guiado para PMs
- Tour de 8 pasos sobre el formulario de Solicitud LTI, mostrado automáticamente al rol PM en su primer ingreso y relanzable con "Ver tour".

### 5. Seguridad de Correos y Datos
- `EMAIL_REDIRECT_TO` (solo desarrollo) redirige todo correo a una dirección con prefijo `[DEV]`; en ese modo el monitor de 6 horas no marca recordatorios.
- Los proyectos QA/TEST no generan correos de creación, asignación ni recordatorio en ningún ambiente.
- El seed de arranque ya no sobrescribe rol, LT, nombre ni estado de cuentas existentes.
- Las pruebas solo borran proyectos creados en su propia sesión con prefijo `000QA-` y apuntan por defecto al servidor local.

---

## 🧪 Pruebas y Certificación de Calidad
- **Asignación directa de LTI**: 32 pruebas de backend (`tests/test_asignacion_lti_directa.py`) y 3 E2E (`tests/test_functional_asignacion_lti_directa.py`), escritas antes del código y con escrituras simuladas o proyectos `QA`.
- **Suite completa**: 427 pruebas aprobadas. Fallas conocidas ajenas a esta versión: `test_tc_etl_006` (deriva de datos productivos) y 5 pruebas de `test_functional_iacdi_deployment.py` que apuntan a la IP Tailscale directa, mientras producción escucha solo en `127.0.0.1` detrás de nginx.
- **Verificación independiente**: auditoría de especificaciones de la asignación directa sin bloqueantes.

---

## 🌐 Estado en Producción (`iacdi`)
- **Servidor:** `100.82.24.75` (Tailscale), servicio `app-lti.service` reiniciado y verificado el 16/10/2026.
- **Verificaciones:** `/api/health` OK, `POST /api/backlog/asignar-lti` responde 401 sin sesión, `https /app-lti/` responde 200; archivos desplegados idénticos a `b6952ab`.
- **URL Aplicativo:** `https://200.14.222.162/app-lti/`
- **Rollback:** `git checkout v1.8.0` (o `931b9be` para conservar la interfaz simplificada), `./deploy_to_iacdi.sh` y `sudo systemctl restart app-lti.service`.
