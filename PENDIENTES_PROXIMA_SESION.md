# 📌 MEMORIA Y REGISTRO DE SESIÓN — APP LTI / HALO

**Fecha de Registro:** 2026-10-14  
**Proyecto:** HALO — App Líderes TI (`/home/bobbasystem/Desarrollos/app-lti`)  
**Rama Git Activa:** `main` / `sso-portal-acceso`  
**Versión / Tag Oficial:** `v1.8.0` ([GitHub Release v1.8.0](https://github.com/alejandroaguil-byte/app-lti/releases/tag/v1.8.0))  
**Servidores Sincronizados:**
- Desarrollo: `bobbadeveloper` (Localhost:8000)
- Producción: `iacdi` (Tailscale `100.82.24.75:8000` / Nginx `https://200.14.222.162/app-lti/`)

---

## 🛠️ TRABAJO COMPLETADO EN ESTA SESIÓN (2026-10-14)

### 1. Pipeline de 5 Subagentes (`flujo-5-agentes`): Módulo Notificaciones Solicitud LTI
- **Estado:** ✅ **100% COMPLETADO, TESTEADO Y CERTIFICADO**.
- **Planificador de Specs (`planificador_specs`)**: Generó `SPECS_NOTIFICACIONES_CORREO_SOLICITUD_LTI.md` con los 3 eventos de correo, contratos REST, esquema MSSQL y plantillas HTML con paleta HALO.
- **Coder (`coder`)**: Implementó:
  1. *Evento 1 (Creación)*: Correo automático a `alejandro.aguilarm@clarovtr.cl` y `pablo.castillo@clarovtr.cl` con la ficha completa del requerimiento (N° Proyecto, Cliente, PM Solicitante, Estado 'Generado' y Detalle con Solots Liray).
  2. *Evento 2 (Recordatorio)*: Worker asíncrono en segundo plano (`lifespan` + `asyncio`) que audita cada 6 horas solicitudes sin líder técnico asignado, con control de persistencia en MSSQL (`Ultimo_Recordatorio` y `Contador_Recordatorios` en `dbo.Proyectos`) para evitar spam o duplicados.
  3. *Evento 3 (Asignación)*: Al asignar un líder técnico en `PUT /api/proyectos/{id}`, notificación automática al PM solicitante con copia (**CC**) al Líder Técnico asignado.
  4. *Resolución de Identidad*: Integración con el directorio de usuarios de Portal Halo, aprovisionamiento JIT y resolución empresarial `@clarovtr.cl`.
- **Revisor de Código (`code_reviewer`)**: Auditó seguridad (prevención CRLF y SQL injection), resiliencia SMTP y aprobó con **0 errores**.
- **QA Tester (`qa_tester`)**: Ejecutó 90/90 tests (26 unitarios de notificaciones + 64 integración/regresión), certificando el **100% de éxito**.
- **Validador de Specs (`specs_validator`)**: Certificó estricto cumplimiento del principio *"Ni más ni menos"*.

---

### 2. Saneamiento y Filtro Anti-Dummy de Recordatorios
- **Estado:** ✅ **100% OPERATIVO EN PRODUCCIÓN**.
- **Detección:** Los recordatorios de 6 horas estaban considerando 11 proyectos dummy históricos de SharePoint (ej. `0001111111`, tipo `Reunión`, demos).
- **Corrección:** Implementación de `is_valid_project_number()` y cláusulas SQL en `backend/db.py` y `backend/main.py` para ignorar permanentemente números dummy y tipos no operacionales.
- **Verificación en Producción:** Endpoint `/api/solicitudes/recordatorios/estado` confirmó:
  - `total_proyectos_sin_asignar: 1` (proyecto real legítimo).
  - `total_proyectos_requieren_recordatorio: 0`.

---

### 3. Emisión del Comunicado Oficial a Project Managers (PMs)
- **Estado:** ✅ **DESPACHADO Y RECIBIDO EXITOSAMENTE**.
- **Herramienta:** Script `scripts/enviar_comunicado_pms.py` con soporte para destinatarios múltiples y Copia Oculta (**BCC**) vía RFC SMTP.
- **Destinatarios `To`:** 31 Project Managers oficiales extraídos del directorio corporativo.
- **Destinatarios `BCC`:** `alejandro.aguilarm@clarovtr.cl` y `pablo.castillo@clarovtr.cl`.
- **Contenido:** Aviso formal de migración obligatoria desde SharePoint hacia la App LTI a partir del Lunes 08:30 AM, con enlace oficial `https://200.14.222.162/login.html`.
- **Confirmación:** Correo recibido conforme en bandeja de entrada.

---

### 4. Estandarización de Identidad Institucional PCDI
- **Estado:** ✅ **HOMOLOGADO Y REGISTRADO COMO REGLA PERMANENTE**.
- **Acción:** Se erradicó la denominación *"Dirección de Operaciones TI"* de todas las plantillas de correo y scripts.
- **Nuevo Estándar:** **`PCDI • Claro Chile / VTR`**.
- **Regla Obligatoria:** Fijada en `AGENTS.md` y `.agents/rules/flujo_5_agentes.md` para todos los desarrollos futuros.

---

### 5. Control de Versiones, GitHub y Release Oficial
- **Estado:** ✅ **PUBLICADO EN GITHUB**.
- **Ramas:** `main` y `sso-portal-acceso` sincronizadas al último commit (`fe67539`).
- **Documentación:** `README.md` actualizado y `RELEASE_v1.8.0.md` generado.
- **Release:** Publicado formalmente en [GitHub Release v1.8.0](https://github.com/alejandroaguil-byte/app-lti/releases/tag/v1.8.0).

---

## 🚀 ESTADO EN PRODUCCIÓN (`iacdi` / `100.82.24.75`)
- Archivos sincronizados en `/home/iacdi/Desarrollos/app-lti`.
- Servicio `app-lti.service` activo y verificado en ejecución (`active (running)`).
- Endpoints operativos:
  - `GET /api/health` &rarr; `200 OK`
  - `GET /api/solicitudes/recordatorios/estado` &rarr; `200 OK`
- URL de acceso institucional: **`https://200.14.222.162/login.html`** &rarr; App LTI.

---

## 📋 PENDIENTES PARA LA PRÓXIMA SESIÓN
- **0 pendientes bloqueantes.**
- Monitoreo preventivo del ingreso de solicitudes por los PMs a partir del lunes a las 08:30 AM.
- Sesión cerrada en estado 100% operativo y certificado.
