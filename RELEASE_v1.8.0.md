# 🚀 Release v1.8.0 — Notificaciones Solicitud LTI, Recordatorios 6h, Filtro Anti-Dummy e Identidad Institucional PCDI

**Fecha de Lanzamiento:** 14 de Octubre de 2026  
**Rama Base:** `main` / `sso-portal-acceso`  
**Tag:** `v1.8.0`  

---

## 🌟 Resumen de la Versión

Esta versión incorpora el sistema completo de trazabilidad, notificaciones y recordatorios automatizados para el ciclo de vida del módulo **Solicitud LTI**, el saneamiento y filtrado de datos históricos de SharePoint, la herramienta de difusión masiva hacia los Project Managers (PMs) para la migración de plataforma y la estandarización estricta de identidad institucional bajo la denominación **PCDI**.

---

## 📦 Nuevas Funcionalidades y Mejoras

### 1. Sistema Automatizado de Notificaciones para Solicitud LTI
- **Notificación Inmediata al Crear**: Al generarse una solicitud LTI por un PM, se despacha automáticamente vía `BackgroundTasks` de FastAPI un correo electrónico institucional a los coordinadores (`alejandro.aguilarm@clarovtr.cl` y `pablo.castillo@clarovtr.cl`) con el detalle completo del requerimiento y Solots Liray formateadas.
- **Worker Asíncrono de Recordatorio Periódico (Cada 6 Horas)**: Monitoreo en segundo plano (`lifespan` + `asyncio`) que audita solicitudes sin líder técnico asignado, emitiendo alertas periódicas con control de persistencia en MSSQL (`Ultimo_Recordatorio` y `Contador_Recordatorios` en `dbo.Proyectos`) para garantizar cero duplicados o spam ante reinicios.
- **Notificación al Asignar Líder Técnico**: Al asignar un líder técnico en la edición del proyecto (`PUT /api/proyectos/{id}`), se notifica de inmediato al PM solicitante con copia (**CC**) al Líder Técnico asignado.
- **Resolución Inteligente de Destinatarios**: Mapeo multicapa de correos corporativos conectando el directorio de usuarios de Portal HALO, aprovisionamiento JIT, catálogo canónico y fallback empresarial `@clarovtr.cl`.

### 2. Filtro Anti-Spam y Exclusión de Proyectos Dummy
- Implementación de la función `is_valid_project_number()` y cláusulas SQL defensivas para omitir permanentemente proyectos de prueba, reuniones y demos (ej. `0001111111`, `1111111`, tipo `Reunión`).

### 3. Herramienta de Difusión y Comunicados Masivos a PMs
- Script oficial `scripts/enviar_comunicado_pms.py` para emitir comunicados institucionales hacia la nómina global de 31 Project Managers en `To:`, con soporte para Copia Oculta (**BCC**) hacia los coordinadores conforme a estándares RFC SMTP.
- Enlace oficial corporativo incorporado: `https://200.14.222.162/login.html`.

### 4. Estandarización de Identidad Institucional PCDI
- Reemplazo y erradicación definitiva del término *"Dirección de Operaciones TI"*.
- Todas las comunicaciones, pies de firma y membretes quedan normalizados bajo:  
  **`PCDI • Claro Chile / VTR`**.
- Regla mandatoria consolidada en `AGENTS.md` y `.agents/rules/flujo_5_agentes.md`.

---

## 🧪 Pruebas y Certificación de Calidad
- **Batería de Pruebas Unitarias e Integración**: 26/26 pruebas aprobadas al 100% en `tests/test_notificaciones_solicitud_lti.py`.
- **Certificación de Especificaciones**: Cumplimiento del principio estricto *"Ni más ni menos"* auditado mediante el pipeline oficial `flujo-5-agentes`.

---

## 🌐 Estado en Producción (`iacdi`)
- **Servidor:** `100.82.24.75` (Tailscale)
- **Servicio Systemd:** `app-lti.service` activo y verificado en ejecución.
- **URL Aplicativo:** `https://200.14.222.162/app-lti/`
