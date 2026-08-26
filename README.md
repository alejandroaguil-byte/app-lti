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
   - Filtros por Estado del proyecto y por Líder TI.
   - Exportación de listados a formato CSV / Excel.

---

## 🛠️ Stack Tecnológico

- **Backend**: Python 3.12 + FastAPI + Uvicorn + PyMSSQL + PyJWT + Bcrypt.
- **Base de Datos**: Microsoft SQL Server (`Sharepoint_Proyectos`).
- **Frontend**: SPA con HTML5 Semántico, Vanilla JavaScript y CSS3 nativo con variables de diseño.

---

## 📁 Estructura del Proyecto

```text
app-lti/
├── backend/
│   ├── main.py              # API FastAPI, rutas REST y servidor de estáticos
│   ├── db.py                # Conexión MSSQL, serialización y consultas optimizadas
│   ├── auth.py              # Autenticación JWT y hashing de claves
│   ├── config.py            # Carga de credenciales y configuración
│   └── seed_users.py        # Poblador de usuarios iniciales en dbo.App_Usuarios
├── frontend/
│   ├── index.html           # Estructura principal y plantillas de tabs
│   ├── css/
│   │   └── styles.css       # Sistema de diseño, temas claro/oscuro y componentes
│   └── js/
│       ├── app.js           # Lógica de renderizado, búsqueda, filtros y drill down
│       └── auth.js          # Control de sesión y peticiones autenticadas
├── requirements.txt         # Dependencias Python
├── run.sh                   # Script de inicio rápido del servidor
└── README.md                # Documentación
```

---

## 🚀 Cómo Iniciar la Aplicación

Ejecuta el script de inicio en la terminal:

```bash
cd /home/bobbasystem/Desarrollos/app-lti
./run.sh
```

El servidor iniciará en: **`http://localhost:8000`**

---

## 🔐 Cuentas Iniciales de Acceso

Las cuentas se crean automáticamente al iniciar la aplicación si no existen:

| Usuario | Nombre Completo | Rol | Contraseña Inicial |
| :--- | :--- | :--- | :--- |
| `admin` | Administrador del Sistema | `ADMIN` (Ve todos los proyectos) | `Lti2026!` |
| `esandoval` | Erwin Sandoval | `LIDER_TI` | `Lti2026!` |
| `ltiznado` | Luis Tiznado | `LIDER_TI` | `Lti2026!` |
| `jbarrera` | Juan Barrera | `LIDER_TI` | `Lti2026!` |
| `aaguilar` | Alejandro Aguilar | `LIDER_TI` | `Lti2026!` |
| `nfigueroa` | Nicolas Figueroa | `LIDER_TI` | `Lti2026!` |
| `rtoledo` | Ricardo Toledo | `LIDER_TI` | `Lti2026!` |
| `sparedes` | Samuel Paredes | `LIDER_TI` | `Lti2026!` |
| `sortiz` | Solange Ortiz | `LIDER_TI` | `Lti2026!` |
| `ygonzalez` | Yulie Gonzalez | `LIDER_TI` | `Lti2026!` |

---

## 📚 Documentación y Especificaciones Técnicas (SPECS)

- [SPECS_MEJORAS_SEGUIMIENTO_LIDERES_KPIS.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_MEJORAS_SEGUIMIENTO_LIDERES_KPIS.md): Especificación técnica para tipografía uniforme, filtro líderes TI con opción 'Sin asignar', restricción de líderes a los 5 activos en orden alfabético y tarjeta KPI interactiva 'Pendientes de Asignar'.
- [SPECS_SOLICITUD_LTI.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_SOLICITUD_LTI.md): Especificación técnica del módulo Solicitud LTI (v1.3.0) con autocompletado SGA, solots Liray, estado fijo 'Generado', tipo servicio fijo 'Otros' y creación desatendida sin asignación de líder inicial.
- [SPECS_EDIT_DELETE_PROYECTOS.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_EDIT_DELETE_PROYECTOS.md): Especificación técnica para edición y eliminación de proyectos en `dbo.Proyectos`.

