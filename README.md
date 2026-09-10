# App LTI - Portal de Seguimiento para Líderes TI 🚀

Aplicación web desarrollada para que los **Líderes TI** realicen el seguimiento integral y en tiempo real de sus proyectos asignados, Solots de backlog de operaciones (SGA), tickets de requerimientos/incidentes (HPSM) y Solicitudes de Cambio (RFCs).

---

## 🌟 Características Principales

1. **Dashboard Personalizado por Líder TI**:
   - Al iniciar sesión, cada Líder TI visualiza automáticamente sus proyectos asignados.
   - Perfil Administrador (`admin`) con capacidad de auditar todos los proyectos y filtrar por cualquier Líder TI.
   - Indicadores ejecutivos en tiempo real (KPIs): Total Proyectos, Solots en Backlog, Tickets SD y RFCs asociadas.

2. **Vista Principal de Proyectos**:
   - **Campos mostrados**:
     - `Cliente (Título)`
     - `N° Proyecto`
     - `LT Asignado`
     - `Solicitante`
     - `Estado` (con badges dinámicos según avance)
     - `Creado` (Fecha de creación)
     - `Detalle`
     - `Acciones / Drill Down`

3. **Drill Down Interactivo (Tabs)**:
   - **📋 Pestaña 1: Resumen y Detalle Técnico**: Ficha técnica del proyecto, desglose de totales y detalle de configuración.
   - **⚡ Pestaña 2: Solot (`CT_BACKLOG_OPERACIONES2`)**:
     - *N° Cliente* (`ID_CLI`)
     - *N° Proyecto* (`NRO_PROYECTO`)
     - *Solot* (`ID_OTP`)
     - *Descripcion* (`DESCR_OTP`)
     - *Estado* (`ESTADO_OTP`)
     - *Fecha compromiso* (`FECHA_COMPROMETIDA`)
     - *Fecha creacion* (`FECHA_INSERT`)
     - *Contrato* (`PLAZO_CONTRATO`)
     - *Producto* (`PRODUCTO`)
     - *Servicio* (`SERVICIO`)
     - *N° Servicio* (`NRO_SERVICIO`)
   - **🎫 Pestaña 3: Tickets SD (`registrosRF_SD_SM`)**:
     - *ID* (`CC_INCIDENT_ID`)
     - *Solicitante* (`REQUESTOR_NAME`)
     - *Estado* (`STATUS`)
     - *Fecha creacion* (`SUBMIT_DATE`)
     - *Fecha cierre* (`CLOSE_DATE`)
     - *Titulo* (`BRIEF_DESCRIPTION`)
     - *Categoria* (`CATEGORY`)
     - *Servicio* (`CC_DETALLE_SERVICIO`)
     - *Grupo de Asignacion* (`ASSIGNED_GROUP`)
     - *Asignado* (`ASSIGNED_TO`)
     - *RF* (`RF_ID`)
   - **🔄 Pestaña 4: RFCs (`registrosSM_RFC`)**:
     - *ID* (`NUMBER`)
     - *Titulo* (`BRIEF_DESCRIPTION`)
     - *Descripción* (`DESCRIPTION`)
     - *Solicitante* (`REQUESTED_BY`)
     - *Fecha cierre* (`CLOSE_TIME`)
     - *N° Proyecto* (`CC_PROYECT_NUMBER`)
     - *Servicio Padre* (`CC_SERVICIO_PADRE`)
     - *Grupo de Asignación* (`ASSIGN_DEPT`)
     - *Asignado* (`ASSIGNED_TO`)

4. **Diseño & Experiencia de Usuario (UI/UX)**:
   - Soporte nativo para **Modo Claro** y **Modo Oscuro** con toggle persistente (`localStorage`).
   - Búsqueda en tiempo real (por Cliente, N° Proyecto o Detalle).
   - Filtro por Estado SharePoint con catálogo canónico oficial (`Generado`, `En revision`, `Atendido`) y selector de Líder TI.

5. **Generador Automatizado de Tickets y Peticiones (Service Manager Bot - v1.2.0)**:
   - **Catálogo Dinámico de Contactos**: Selección entre los 5 líderes técnicos oficiales (`ALEJANDRO JAVIER AGUILAR MORALES`, `JUAN BARRERA RAMOS`, `SAMUEL PAREDES SAEZ`, `SOLANGE ANGELICA ORTIZ VIROLDE`, `Erwin Patricio Sandoval Cadiz`).
   - **Catálogo Oficial de Grupos de Asignación**: 11 grupos y torres de soporte técnico (`Lideres Tecnicos`, `ProvisionConectividadTI`, `ProvisionVirtualizacionTI`, `Plataforma T3 / Soporte Especializado`, `Torre Linux`, `Torre Microsoft`, `Torre Monitoreo`, `Torre Plataformas Internas`, `Torre Respaldos`, `Torre SAP`, `Torre Virtualizacion`) con búsqueda modal desatendida.
   - **Niveles Normalizados de Impacto & Urgencia**: Mapeo exacto con los 3 niveles de Impacto (`1 - Alto (Perdida Total)`, `2 - Moderada (Perdida Parcial)`, `3 - Menor (Existen WorkAround)`) y los 4 niveles de Urgencia (`1 - Crítica (Atención Inmediata)`, `2 - Alta (Resolución a corto plazo)`, `3 - Media (Resolución a mediano plazo)`, `4 - Baja (No requiere urgencia)`).
   - **Formulario Limpio sin Hardcodes**: Campos de Título y Descripción limpios con placeholders guiados y validación obligatoria antes de la ejecución.
   - **Automatización Desatendida & SSE**: Async Playwright con streaming lineal en tiempo real, creación de Interacción (SD), vinculación de Petición Relacionada (`Alejandro.Aguilar`), captura de doble ID, logout limpio (`Info. del usuario` &rarr; `Cerrar sesión` &rarr; `Sí`) y modal interactivo de éxito con botón directo a notificación por correo.

6. **Envío Automatizado de Notificación por Correo (Office 365 SMTP - v1.2.0)**:
   - Botón directo **"📧 Enviar correo"** integrado en el popup de confirmación de tickets.
   - Modal de redacción con animación nativa y prellenado inteligente:
     * **Para**: `alejandro.aguilarm@clarovtr.cl` (editable, soporte multi-destinatario).
     * **Asunto**: Título ingresado en el generador de tickets (editable).
     * **Cuerpo**: Descripción detallada del ticket (editable).
     * **Adjunto**: Zona de carga para adjuntar archivos de soporte/evidencias (opcional, máx. 15MB).
   - Conexión segura estándar a través de **Microsoft Office 365 SMTP** (`smtp.office365.com`, puerto 587, STARTTLS).
   - Manejo defensivo de excepciones SMTP, timeouts y validación de variables de entorno sin interrumpir el flujo del usuario.

---

## 🛠️ Stack Tecnológico

- **Backend**: Python 3.12 + FastAPI + Uvicorn + Playwright Async + PyMSSQL + PyJWT + SMTPLib (STARTTLS).
- **Autenticación**: Single Sign-On (SSO) corporativo vía Portal de Acceso (Cookies HttpOnly `access_token` / `refresh_token`, firma HS256).
- **Base de Datos**: Microsoft SQL Server (`Sharepoint_Proyectos`).
- **Frontend**: SPA con HTML5 Semántico, Vanilla JavaScript y CSS3 nativo con variables de diseño.

---

## 📁 Estructura del Proyecto

```text
app-lti/
├── backend/
│   ├── main.py              # API FastAPI, rutas REST, streaming y servidor de estáticos
│   ├── db.py                # Conexión MSSQL, serialización, consultas y aprovisionamiento JIT
│   ├── auth.py              # Verificación de JWT SSO del Portal, cookies HttpOnly y cálculo de roles
│   ├── config.py            # Carga de variables (.env) y configuración global
│   ├── email_service.py     # Servicio de envío de correos vía Office 365 SMTP + STARTTLS
│   ├── seed_users.py        # Poblador idempotente de roles para líderes y administradores
│   └── ticket_automation.py # Automatización Playwright Async + SSE para Service Manager
├── frontend/
│   ├── index.html           # Estructura principal sin login propio, adaptada a sesión SSO
│   ├── css/
│   │   └── styles.css       # Sistema de diseño, consola terminal, dropzone y temas claro/oscuro
│   └── js/
│       ├── app.js           # Lógica de renderizado, streaming SSE, modales, clipboard y email
│       └── auth.js          # Manejo de sesión SSO por cookies con auto-refresh (/api/auth/refresh)
├── .env.example             # Plantilla de variables de entorno (SMTP, BD, PORTAL_JWT_SECRET)
├── requirements.txt         # Dependencias Python
├── run.sh                   # Script de inicio rápido del servidor
└── README.md                # Documentación
```

---

## ⚙️ Configuración y Variables de Entorno (`.env`)

Para habilitar el envío de correos vía **Microsoft Office 365** y personalizar los accesos del sistema, cree un archivo `.env` en la raíz del proyecto basándose en `.env.example`:

```ini
# ==============================================================================
# CONFIGURACIÓN DEL SERVIDOR DE CORREO (OFFICE 365 SMTP)
# ==============================================================================
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USER=alejandro.aguilarm@clarovtr.cl
SMTP_PASS=TuPasswordDeOffice365
SMTP_FROM=alejandro.aguilarm@clarovtr.cl
SMTP_TIMEOUT=30
SMTP_DEFAULT_RECIPIENT=alejandro.aguilarm@clarovtr.cl

# ==============================================================================
# CONFIGURACIÓN GENERAL Y BASE DE DATOS
# ==============================================================================
DB_SERVER=192.168.10.6
DB_PORT=1433
DB_USER=sa
DB_PASSWORD=
DB_NAME=Sharepoint_Proyectos

# ==============================================================================
# INTEGRACIÓN SSO PORTAL DE ACCESO (HS256)
# ==============================================================================
PORTAL_JWT_SECRET=tu-portal-jwt-secret-aqui
JWT_ACCESS_SECRET=tu-portal-jwt-secret-aqui
```

> [!NOTE]
> Si la cuenta de Office 365 tiene habilitada la autenticación multifactor (MFA), debe utilizar una **Contraseña de Aplicación (App Password)** generada desde el panel de seguridad de Microsoft 365.
> Si las credenciales no están configuradas en el archivo `.env`, el sistema informará al usuario de manera amigable sin interrumpir la operación de la plataforma.

---

## 🚀 Cómo Iniciar la Aplicación (Entorno Local `bobbadeveloper`)

Ejecuta el script de inicio en la terminal de desarrollo local:

```bash
cd /home/bobbasystem/Desarrollos/app-lti
./run.sh
```

El servidor iniciará en: **`http://localhost:8000`**

> [!CAUTION]
> ### Regla Estricta de Entorno
> La implementación y verificación activa se realiza **exclusivamente en `bobbadeveloper`** (`/home/bobbasystem/Desarrollos/app-lti`). Está estrictamente prohibido ejecutar `deploy_to_iacdi.sh` o realizar cambios directos en el servidor `iacdi` sin autorización explícita.

---

## 🌐 Topología y Acceso vía Portal de Acceso (Producción `iacdi`)

En el entorno integrado, App LTI corre detrás del reverse proxy Nginx del **Portal de Acceso** (`~/portal-acceso`), configurado bajo el mismo origen seguro:

- **Ruta Oficial de Acceso:** **`https://200.14.222.162/app-lti/`**
- **Slug de Herramienta en Portal:** `app-lti`
- **Host SSH Remoto (Producción):** `iacdi` (`100.82.24.75`, usuario `iacdi`)
- **Directorio Remoto:** `/home/iacdi/Desarrollos/app-lti`
- **Base de Datos:** Microsoft SQL Server `192.168.10.6:1433` (`Sharepoint_Proyectos`)

---

## 🔐 Control de Acceso Basado en Roles (RBAC) & SSO del Portal

App LTI utiliza autenticación federada **Single Sign-On (SSO)** mediante las cookies seguras HttpOnly (`access_token`, `refresh_token`) emitidas por el **Portal de Acceso**.

### 1. Formato Canónico de Cuentas
- Desaparecen las cuentas hardcodeadas anteriores.
- Se utiliza el formato corporativo oficial del Portal: **`nombre.apellido`** en minúsculas (ejemplos: `alejandro.aguilar`, `solange.ortiz`, `juan.barrera`, `samuel.paredes`, `erwin.sandoval`).
- **Aprovisionamiento Just-In-Time (JIT):** Cuando un usuario con sesión válida en el Portal accede por primera vez a App LTI, el sistema lo registra automáticamente en `dbo.App_Usuarios`, permitiendo que el Administrador de App LTI configure su rol operativo y Líder TI asignado sin necesidad de crear cuentas manuales.

### 2. Mapeo de `toolAccess` del Portal y Permisos Efectivos

El token JWT del Portal define la capacidad de escritura de la sesión:
- **Portal `"operador"` (o Super Admin `adminLevel >= 2`):** Permite ejecutar operaciones según el rol registrado en App LTI (`ADMIN` o `LTI`), habilitando edición de proyectos, creación de tickets Service Manager y gestión de solicitudes.
- **Portal `"lectura"` o sin asignación:** Restringe forzosamente la sesión al perfil **`PM` (Solo Lectura / Solicitud LTI)**, impidiendo cualquier acción de escritura o acceso al mantenedor de usuarios, independientemente del rol local.
- **Bloqueo Local:** Si el usuario tiene `activo = 0` en `dbo.App_Usuarios`, el backend deniega el acceso con `403 Forbidden`.

### 3. Centralización de Gestión de Identidades
- **Alta de cuentas y contraseñas:** Centralizadas al 100% en el Portal de Acceso. App LTI no almacena `password_hash` ni expone formularios de creación de cuentas o reseteo de claves.
- **Mantenedor Local de App LTI (`👥 Usuarios`):** Exclusivo para administradores locales, permitiendo asignar el rol del negocio (`PM`, `LTI`, `ADMIN`), vincular el Líder TI responsable (`lt_asignado`) y alternar el estado activo/bloqueado.

---

## 📚 Documentación y Especificaciones Técnicas (SPECS)

- [SPECS_INTEGRACION_SSO_PORTAL_ACCESO.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_INTEGRACION_SSO_PORTAL_ACCESO.md): **(v2.0.0 Ratificada)** Especificación técnica definitiva de integración Single Sign-On (SSO) con el Portal de Acceso, cookies HttpOnly, mapeo de `toolAccess`, formato canónico `nombre.apellido`, aprovisionamiento JIT y arquitectura desacoplada sin contraseñas locales.
- [SPECS_DESPLIEGUE_IACDI_TAILSCALE.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_DESPLIEGUE_IACDI_TAILSCALE.md): (v1.0.0) Especificación técnica y de infraestructura para el despliegue, configuración del servicio systemd de usuario con Linger, entorno de desarrollo continuo y conectividad en servidor `iacdi` (IP Tailscale `100.82.24.75:8000`, enlace MSSQL `192.168.10.6:1433`).
- [SPECS_FILTRO_ESTADOS_SHAREPOINT.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_FILTRO_ESTADOS_SHAREPOINT.md): (v1.0.0) Especificación técnica de Catálogo Canónico y Corrección del Filtro de Estados SharePoint (`Generado`, `En revision`, `Atendido`), desacople de consultas dependientes de BD y renderizado defensivo con fallback en UI.
- [SPECS_TICKET_GENERATOR_CAMPOS_DINAMICOS.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_TICKET_GENERATOR_CAMPOS_DINAMICOS.md): (v1.0.0) Especificación técnica de Catálogo Dinámico de Contactos (5 líderes), Catálogo de Grupos de Asignación (11 torres), Normalización de Impacto y Urgencia con Service Manager, Limpieza de Valores de Prueba Hardcodeados y Placeholders Guiados.
- [SPECS_ENVIO_CORREO_TICKETS.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_ENVIO_CORREO_TICKETS.md): (v1.1.0) Especificación técnica de Envío Automatizado de Notificación por Correo tras la creación de Tickets y Peticiones vía Office 365 SMTP, integración REST dual `multipart/form-data` y JSON (`application/json`), corrección de `Auth.fetchWithAuth` para `FormData`, modal de redacción con adjuntos y parametrización `.env`.
- [SPECS_TICKET_GENERATOR_PETICIONES.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_TICKET_GENERATOR_PETICIONES.md): (v1.1.0) Especificación técnica de Automatización de Tickets e Interacciones, Vinculación de Peticiones Relacionadas, Cierre de Sesión Seguro (Logout), Arquitectura Directa Lineal SSE y Modal con Doble Identificador (SD + Petición).
- [SPECS_MANTENEDOR_USUARIOS_Y_ROLES.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_MANTENEDOR_USUARIOS_Y_ROLES.md): Especificación técnica de Gestión de Usuarios, RBAC (PM, LTI, ADMIN), Mantenedor de Usuarios (`👥 Usuarios`), Poblado desde Excel y Protección destructiva de Proyectos.
- [SPECS_EDIT_DELETE_PROYECTOS.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_EDIT_DELETE_PROYECTOS.md): Especificación técnica para edición y eliminación de proyectos en `dbo.Proyectos`.
- [SPECS_SOLICITUD_LTI.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_SOLICITUD_LTI.md): Especificación técnica del módulo Solicitud LTI con autocompletado SGA, solots Liray y creación desatendida.
- [SPECS_MEJORAS_SEGUIMIENTO_LIDERES_KPIS.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_MEJORAS_SEGUIMIENTO_LIDERES_KPIS.md): Especificación técnica para tipografía uniforme, filtro líderes TI con opción 'Sin asignar' y KPI interactiva 'Pendientes de Asignar'.
