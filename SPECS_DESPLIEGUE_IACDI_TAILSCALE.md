# ESPECIFICACIÓN TÉCNICA Y DE DESPLIEGUE (SPECS)
## Módulo: Despliegue, Configuración de Servicio Systemd y Entorno de Desarrollo en Servidor IACDI vía Tailscale (`app-lti`)

- **Documento:** SPECS-LTI-DEP-008
- **Versión:** 1.3.0
- **Fecha:** 2026-09-22
- **Autor:** Subagente Planificador & Diseñador de Specs (`planificador_specs`)
- **Destinatario:** Subagente Codificador & Implementador (`coder`) / Subagente QA (`tester`)
- **Ubicación del Proyecto Local:** `/home/bobbasystem/Desarrollos/app-lti`
- **Ubicación del Proyecto Remoto (IACDI):** `/home/iacdi/Desarrollos/app-lti`

---

## CONTROL DE VERSIONES Y REGISTRO DE CAMBIOS

| Versión | Fecha | Autor | Descripción del Cambio |
|---|---|---|---|
| **1.0.0** | 2026-09-08 | Subagente Planificador | Versión inicial de especificación técnica de despliegue en servidor `iacdi` (Ubuntu Linux, Python 3.14.4, IP Tailscale `100.82.24.75`, puerto 8000, enlace MSSQL `192.168.10.6:1433`, servicio systemd de usuario con Linger habilitado, sincronización rsync y modo desarrollo continuo con hot reload). |
| **1.3.0** | 2026-09-22 | Subagente Planificador | Despliegue formal de la versión v1.3.0 en producción IACDI: Semáforo de Salud de Proyectos (Verde/Amarillo/Rojo/Gris), Kill-Switch reactivo persistente en UI, Rediseño corporativo HALO, filtros integrados de salud y actualización de contratos API. Incluye procedimiento de consolidación Git en rama `sso-portal-acceso`, sincronización rsync sin pisar `.env`, verificación de servicio systemd y plan de contingencia/rollback. |

---

## 1. RESUMEN EJECUTIVO Y OBJETIVOS

### 1.1. Contexto del Requerimiento
Se requiere la publicación oficial y parametrización de la plataforma **App LTI** dentro del servidor remoto institucional `iacdi`. El servidor cuenta con conectividad nativa a la red de bases de datos de la organización (`192.168.10.6:1433`), acceso seguro por SSH y presencia en la red privada de malla **Tailscale** bajo la dirección IP `100.82.24.75`.

El servidor `iacdi` cumplirá una doble función estratégica:
1. **Host de Ejecución y Publicación Interna:** Permitir a los Líderes Técnicos (LTI), Project Managers (PM) y Administradores conectarse de forma segura a través de Tailscale (`http://100.82.24.75:8000`) para operar la plataforma en tiempo real.
2. **Entorno de Desarrollo Continuo y Nuevas Funcionalidades:** Establecer un flujo de despliegue ágil y seguro (hot-reload con Uvicorn, scripts de sincronización `rsync`, persistencia con `systemd --user` y `linger`), permitiendo codificar, probar e incorporar nuevos módulos sin interrumpir la operación ni depender de accesos VPN corporativos rígidos.

### 1.2. Objetivos Principales de la Especificación
1. **Estandarizar la Estructura Remota:** Desplegar el código fuente completo en `/home/iacdi/Desarrollos/app-lti` bajo el usuario `iacdi`.
2. **Aislamiento y Dependencias:** Configurar un entorno virtual Python dedicado (`venv`) con Python 3.14.4 y todas las dependencias requeridas en `requirements.txt`.
3. **Persistencia y Gobernanza mediante Systemd:** Implementar un servicio de usuario systemd (`app-lti.service`) con arranque automático, reintentos defensivos (`Restart=always`), carga de variables de entorno (`.env`) y soporte de linger para mantenerse activo tras el cierre de sesiones SSH.
4. **Integración con Base de Datos:** Configurar la conexión hacia el motor Microsoft SQL Server `192.168.10.6:1433` (`Sharepoint_Proyectos`) y asegurar la ejecución idempotente del seed de usuarios (`backend.seed_users`).
5. **Estrategia de Desarrollo y Despliegue:** Proveer scripts automatizados de sincronización local-remota (`deploy_to_iacdi.sh`), un script de inicio adaptativo (`run.sh`) y soporte de recarga en caliente (`--reload`).
6. **Plan de Pruebas y Validación:** Definir una batería completa de casos de prueba de aceptación técnica (conectividad, servicio, base de datos, API, UI y persistencia).

---

## 2. ARQUITECTURA DE RED Y TOPOLOGÍA

```mermaid
flowchart TB
    subgraph TAILSCALE_NET["🌐 Red Privada Tailscale (Tailnet)"]
        subgraph DEV_CLIENT["💻 Estación Local / Cliente"]
            DevBrowser["Navegador Web / SPA Client<br>(http://100.82.24.75:8000)"]
            DevSSH["SSH Client & rsync<br>(iacdi@100.82.24.75)"]
        end

        subgraph IACDI_SERVER["🖥️ Servidor IACDI (Ubuntu Linux - 100.82.24.75)"]
            subgraph SYSTEMD_USER["⚙️ Systemd User Runtime (Linger Enabled)"]
                AppService["app-lti.service<br>(Unit: ~/.config/systemd/user/app-lti.service)"]
            end

            subgraph APP_CONTAINER["📦 App LTI Application Stack"]
                Uvicorn["Uvicorn ASGI Server<br>(0.0.0.0:8000 / --reload)"]
                FastAPI["FastAPI Backend<br>(backend/main.py)"]
                StaticSPA["Static Files & SPA Frontend<br>(frontend/index.html, app.js, styles.css)"]
                Venv["Python 3.14.4 Virtualenv<br>(/home/iacdi/Desarrollos/app-lti/venv)"]
            end

            EnvFile[".env Configuration<br>(chmod 600)"]
        end
    end

    subgraph LAN_INTRA["🏢 Red Interna Corporativa / LAN"]
        MSSQL[("🗄️ Microsoft SQL Server<br>192.168.10.6:1433<br>DB: Sharepoint_Proyectos")]
        O365["📧 Microsoft Office 365 SMTP<br>smtp.office365.com:587 (STARTTLS)"]
        HPSM["🤖 Micro Focus Service Manager<br>(Playwright Automation Bot)"]
    end

    DevBrowser -->|HTTP TCP :8000| Uvicorn
    DevSSH -->|SSH TCP :22 / rsync| IACDI_SERVER
    AppService -->|Manage / Supervise| Uvicorn
    Uvicorn --> FastAPI
    FastAPI --> StaticSPA
    FastAPI -->|Load Config| EnvFile
    FastAPI -->|pyodbc / pymssql TCP :1433| MSSQL
    FastAPI -->|SMTP TLS :587| O365
    FastAPI -->|Headless Browser| HPSM
```

### 2.1. Parámetros de Red y Conectividad

| Componente | Dirección / Host | Puerto | Protocolo | Propósito |
|---|---|---|---|---|
| **Servidor IACDI (Tailscale)** | `100.82.24.75` | `8000` | HTTP (TCP) | Acceso web a la interfaz SPA y endpoints REST de la API. |
| **Servidor IACDI (SSH)** | `100.82.24.75` / `iacdi` | `22` | SSH (TCP) | Administración remota, sincronización rsync y desarrollo. |
| **Base de Datos MSSQL** | `192.168.10.6` | `1433` | TDS / MSSQL | Conexión a base de datos `Sharepoint_Proyectos` (Tablas `Proyectos`, `App_Usuarios`, `CT_BACKLOG_OPERACIONES2`, `registrosRF_SD_SM`, `registrosSM_RFC`). |
| **Servidor SMTP (Office 365)** | `smtp.office365.com` | `587` | SMTP + STARTTLS | Envío de notificaciones por correo de tickets y peticiones. |
| **Escucha de Uvicorn** | `0.0.0.0` | `8000` | HTTP | Permite atender peticiones tanto locales (`127.0.0.1`) como de la interfaz Tailscale (`100.82.24.75`). |

---

## 3. ESTRUCTURA DE ARCHIVOS Y DIRECTORIOS EN EL SERVIDOR `IACDI`

El árbol de directorios en el servidor remoto se organiza de forma canónica y limpia bajo el home del usuario `iacdi`:

```text
/home/iacdi/
├── .config/
│   └── systemd/
│       └── user/
│           └── app-lti.service               # Unidad de servicio systemd a nivel de usuario
└── Desarrollos/
    └── app-lti/                              # Raíz del proyecto
        ├── .env                              # Archivo de credenciales reales (permisos 600)
        ├── .env.example                      # Plantilla de variables de entorno
        ├── .gitignore                        # Reglas de exclusión para Git
        ├── README.md                         # Documentación de operaciones y arquitectura
        ├── SPECS_*.md                        # Especificaciones técnicas
        ├── requirements.txt                  # Lista de dependencias Python
        ├── run.sh                            # Script adaptativo de arranque local/servidor
        ├── deploy_to_iacdi.sh                # Script de sincronización desde estación local
        ├── venv/                             # Entorno virtual Python 3.14.4
        │   ├── bin/
        │   │   ├── python3
        │   │   ├── uvicorn
        │   │   └── pip
        │   └── lib/
        ├── backend/                          # Capa Backend FastAPI
        │   ├── __init__.py
        │   ├── main.py                       # App FastAPI, CORS, rutas y estáticos
        │   ├── config.py                     # Lector de configuración y variables .env
        │   ├── db.py                         # Conector pymssql, queries y CRUD
        │   ├── auth.py                       # JWT token handling y hashing bcrypt
        │   ├── seed_users.py                 # Poblador y sincronizador de usuarios
        │   ├── email_service.py              # Servicio de correo Office 365 SMTP
        │   └── ticket_automation.py          # Automatización Playwright Service Manager
        ├── frontend/                         # Capa Frontend SPA Vanilla
        │   ├── index.html                    # Single Page Application principal
        │   ├── css/
        │   │   └── styles.css                # Estilos, temas, modales y dropzone
        │   └── js/
        │       ├── app.js                    # Lógica UI, CRUD, streaming y drilldown
        │       └── auth.js                   # Gestión de tokens JWT y fetch autenticado
        └── csv/
            └── Listado_Permisos_Usuarios.xlsx # Archivo de referencia de usuarios
```

---

## 4. CONFIGURACIÓN DE VARIABLES DE ENTORNO (`.env`)

En el servidor remoto `/home/iacdi/Desarrollos/app-lti/.env` se debe configurar el archivo con permisos restringidos (`chmod 600`):

```ini
# ==============================================================================
# CONFIGURACIÓN DEL SERVIDOR DE CORREO (OFFICE 365 SMTP)
# ==============================================================================
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USER=alejandro.aguilarm@clarovtr.cl
SMTP_PASS=TuPasswordDeOffice365OAppPassword
SMTP_FROM=alejandro.aguilarm@clarovtr.cl
SMTP_TIMEOUT=30
SMTP_DEFAULT_RECIPIENT=alejandro.aguilarm@clarovtr.cl

# ==============================================================================
# CONFIGURACIÓN GENERAL Y BASE DE DATOS (MSSQL)
# ==============================================================================
DB_SERVER=192.168.10.6
DB_PORT=1433
DB_USER=sa
DB_PASSWORD=
DB_NAME=Sharepoint_Proyectos
JWT_SECRET=app-lti-super-secret-key-2026-claro
```

### 4.1. Reglas de Seguridad para `.env`
1. **Permisos de archivo:** `chmod 600 /home/iacdi/Desarrollos/app-lti/.env` (solo lectura y escritura para el usuario `iacdi`).
2. **Exclusión en Git:** Confirmar que `.env` esté presente en `.gitignore`.
3. **Exclusión en Sync:** El script de sincronización `deploy_to_iacdi.sh` **no debe sobrescribir** el `.env` del servidor remoto.

---

## 5. ENTORNO VIRTUAL PYTHON 3.14 Y DEPENDENCIAS

### 5.1. Creación del Entorno Virtual en `iacdi`
En el servidor `iacdi`, se inicializa el entorno virtual con Python 3.14.4:

```bash
cd /home/iacdi/Desarrollos/app-lti
python3 -m venv venv
```

### 5.2. Instalación de Dependencias
Se instalan y actualizan los paquetes desde `requirements.txt`:

```bash
/home/iacdi/Desarrollos/app-lti/venv/bin/pip install --upgrade pip
/home/iacdi/Desarrollos/app-lti/venv/bin/pip install -r requirements.txt
```

### 5.3. Tabla de Dependencias (`requirements.txt`)

| Paquete | Versión Mínima | Justificación Técnica |
|---|---|---|
| `fastapi` | `>=0.110.0` | Framework web asíncrono para la API REST y servidor de SPA. |
| `uvicorn` | `>=0.28.0` | Servidor ASGI de alto rendimiento con soporte para `--reload`. |
| `pymssql` | `>=2.2.0` | Driver nativo C-TDS para conexión directa a SQL Server `192.168.10.6`. |
| `pyjwt` | `>=2.8.0` | Generación y validación de tokens JWT (`HS256`). |
| `bcrypt` | `>=4.1.0` | Hashing seguro de contraseñas de usuarios. |
| `python-multipart`| `>=0.0.9` | Soporte para `multipart/form-data` en subida de adjuntos SMTP y login. |
| `pydantic` | `>=2.6.0` | Validación estricta de esquemas de datos y peticiones API. |
| `playwright` | `>=1.50.0` | Automatización de navegador para interacción con Service Manager. |

---

## 6. INICIALIZACIÓN Y POBLADO DE BASE DE DATOS

El sistema cuenta con un inicializador de base de datos (`backend.seed_users`) que:
1. Verifica y crea la tabla `dbo.App_Usuarios` si no existe.
2. Sincroniza idempotentemente los **38 usuarios canónicos** (31 PMs, 4 LTIs, 2 ADMINs y 1 superadmin raíz `admin`).
3. Asigna la contraseña inicial por defecto `Lti2026!`.

### 6.1. Ejecución Manual de Inicialización:
```bash
cd /home/iacdi/Desarrollos/app-lti
PYTHONPATH=/home/iacdi/Desarrollos/app-lti /home/iacdi/Desarrollos/app-lti/venv/bin/python3 -m backend.seed_users
```

> [!NOTE]
> La aplicación también ejecuta `seed_default_users()` automáticamente en el evento `lifespan` de FastAPI durante el arranque, garantizando que ante cualquier actualización de esquema la base de datos quede lista.

---

## 7. DEFINICIÓN DEL SERVICIO SYSTEMD DE USUARIO (`app-lti.service`)

Para garantizar la disponibilidad continua de la aplicación, su ejecución en segundo plano y su reinicio automático ante fallos o reboots del servidor, se utiliza el gestor **Systemd User Units**.

### 7.1. Archivo de Unidad: `~/.config/systemd/user/app-lti.service`

```ini
[Unit]
Description=App LTI - Portal de Seguimiento Líderes TI (Uvicorn FastAPI)
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/iacdi/Desarrollos/app-lti
ExecStart=/home/iacdi/Desarrollos/app-lti/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
Restart=always
RestartSec=5s
Environment=PYTHONPATH=/home/iacdi/Desarrollos/app-lti
EnvironmentFile=/home/iacdi/Desarrollos/app-lti/.env
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

### 7.2. Desglose Técnico de Directivas

| Directiva | Valor | Justificación Técnica |
|---|---|---|
| `WorkingDirectory` | `/home/iacdi/Desarrollos/app-lti` | Establece el directorio de trabajo para la resolución de rutas relativas de backend, frontend y `.env`. |
| `ExecStart` | `.../venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload` | Ejecuta Uvicorn apuntando a la app FastAPI. El parámetro `--host 0.0.0.0` expone el servicio a la IP Tailscale (`100.82.24.75`). El flag `--reload` permite que cualquier cambio en código fuente se aplique inmediatamente. |
| `Restart` | `always` | Reinicia automáticamente el proceso ante fallos inesperados, excepciones no capturadas o cierres del proceso. |
| `RestartSec` | `5s` | Espera 5 segundos antes de reiniciar para evitar sobrecarga en caso de fallos recurrentes. |
| `EnvironmentFile` | `/home/iacdi/Desarrollos/app-lti/.env` | Inyecta las variables de entorno de BD, JWT y SMTP directamente al proceso. |
| `WantedBy` | `default.target` | Permite que el servicio inicie automáticamente al arrancar la sesión de usuario de systemd. |

### 7.3. Habilitación de Linger (Persistencia sin Sesión SSH)
Por defecto, los servicios `systemd --user` se detienen cuando el usuario cierra su sesión SSH. Para evitar esto y permitir que el servicio corra permanentemente incluso tras desconectarse o tras un reinicio de la máquina, se activa **Linger**:

```bash
loginctl enable-linger iacdi
```

*Verificación de Linger:*
```bash
loginctl show-user iacdi --property=Linger
# Debe retornar: Linger=yes
```

### 7.4. Comandos de Control del Servicio

```bash
# 1. Recargar configuración de systemd tras crear o modificar el servicio
systemctl --user daemon-reload

# 2. Habilitar arranque automático del servicio al iniciar el sistema
systemctl --user enable app-lti.service

# 3. Iniciar el servicio
systemctl --user start app-lti.service

# 4. Consultar estado detallado del servicio
systemctl --user status app-lti.service

# 5. Reiniciar el servicio
systemctl --user restart app-lti.service

# 6. Detener el servicio
systemctl --user stop app-lti.service

# 7. Monitorear logs en tiempo real (seguimiento activo)
journalctl --user -u app-lti -f -n 100
```

---

## 8. ESTRATEGIA DE SINCRONIZACIÓN Y DESARROLLO CONTINUO

Para facilitar el desarrollo iterativo continuo desde la máquina local (`bobbasystem`) hacia el servidor remoto (`iacdi`), se definen dos herramientas esenciales:

### 8.1. Script de Inicio Adaptativo (`run.sh`)
El script `run.sh` se adapta automáticamente para funcionar tanto en la estación local como en el servidor `iacdi`, detectando el entorno virtual disponible en el directorio del proyecto (`./venv`) antes de recurrir a rutas globales o al Python del sistema.

```bash
#!/usr/bin/env bash
# ==============================================================================
# Script de inicio para App LTI (Servidor Web y API FastAPI)
# Compatible con Entorno Local (bobbasystem) y Servidor Remoto (iacdi)
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Prioridad: Entorno virtual local del proyecto
if [ -f "$DIR/venv/bin/python3" ] && [ -f "$DIR/venv/bin/uvicorn" ]; then
    VENV_PYTHON="$DIR/venv/bin/python3"
    VENV_UVICORN="$DIR/venv/bin/uvicorn"
# 2. Fallback: Entorno virtual de desarrollo bobbasystem
elif [ -f "/home/bobbasystem/Desarrollos/Carga Data SM/venv/bin/python3" ]; then
    VENV_PYTHON="/home/bobbasystem/Desarrollos/Carga Data SM/venv/bin/python3"
    VENV_UVICORN="/home/bobbasystem/Desarrollos/Carga Data SM/venv/bin/uvicorn"
# 3. Fallback: Python y Uvicorn del sistema
else
    echo "[INFO] Usando python3 y uvicorn del sistema..."
    VENV_PYTHON="python3"
    VENV_UVICORN="uvicorn"
fi

echo "=================================================="
echo "Iniciando App LTI - Portal de Líderes TI"
echo "Directorio : $DIR"
echo "Python     : $VENV_PYTHON"
echo "Uvicorn    : $VENV_UVICORN"
echo "=================================================="

# Poblar usuarios y tablas si es necesario
echo "[MSSQL] Verificando tablas de autenticación y usuarios..."
PYTHONPATH="$DIR" "$VENV_PYTHON" -m backend.seed_users

# Iniciar servidor Uvicorn
PORT=8000
echo "[WEB] Servidor disponible en: http://0.0.0.0:$PORT"
echo "Presione Ctrl+C para detener el servidor."

PYTHONPATH="$DIR" "$VENV_UVICORN" backend.main:app --host 0.0.0.0 --port "$PORT" --reload
```

### 8.2. Script de Sincronización Remota (`deploy_to_iacdi.sh`)
Ubicado en la raíz del proyecto local, permite transferir rápidamente los cambios de código fuente hacia el servidor `iacdi` mediante `rsync` a través de Tailscale/SSH:

```bash
#!/usr/bin/env bash
# ==============================================================================
# Script de Sincronización y Despliegue hacia Servidor IACDI vía Tailscale/SSH
# ==============================================================================

set -e

REMOTE_HOST="iacdi"
REMOTE_IP="100.82.24.75"
REMOTE_USER="iacdi"
REMOTE_DIR="/home/iacdi/Desarrollos/app-lti"

LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=================================================="
echo "Sincronizando App LTI hacia Servidor IACDI"
echo "Destino: $REMOTE_USER@$REMOTE_HOST ($REMOTE_IP):$REMOTE_DIR"
echo "=================================================="

# Sincronización con rsync excluyendo venv, git, cache y .env remoto
rsync -avz --progress \
    --exclude 'venv/' \
    --exclude '.git/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.pytest_cache/' \
    --exclude '.env' \
    --exclude '.DS_Store' \
    "$LOCAL_DIR/" "$REMOTE_HOST:$REMOTE_DIR/"

echo ""
echo "[INFO] Código sincronizado exitosamente."
echo "[INFO] Si el servicio app-lti.service está corriendo con --reload, los cambios ya están activos."
echo "[INFO] Para verificar logs remotos: ssh $REMOTE_HOST 'journalctl --user -u app-lti -n 20 --no-pager'"
echo "=================================================="
```

---

## 9. MATRIZ DE PRUEBAS Y CRITERIOS DE ACEPTACIÓN

| ID Prueba | Módulo / Componente | Descripción de la Prueba | Pasos de Ejecución | Resultado Esperado | Criterio de Aceptación |
|---|---|---|---|---|---|
| **TC-DEP-01** | Red & Tailscale | Conectividad TCP al puerto 8000 en IP Tailscale. | Ejecutar `curl -I http://100.82.24.75:8000` desde una máquina conectada a Tailscale. | HTTP/1.1 200 OK y respuesta del servidor Uvicorn. | **PASSED:** El puerto 8000 responde y sirve contenido sin timeouts. |
| **TC-DEP-02** | Base de Datos MSSQL | Conectividad TCP y autenticación contra `192.168.10.6:1433`. | Ejecutar script de prueba de conexión o `seed_users.py`. | Conexión exitosa, sin errores de socket ni timeouts. | **PASSED:** Consulta SQL retorna resultados de `Sharepoint_Proyectos`. |
| **TC-DEP-03** | Seed de Usuarios | Poblado de los 38 usuarios iniciales en `dbo.App_Usuarios`. | Ejecutar `PYTHONPATH=. venv/bin/python3 -m backend.seed_users`. | Mensaje `[SEED] Sincronización de usuarios completada: N insertados, M actualizados.` | **PASSED:** 38 cuentas creadas con sus respectivos roles (PM, LTI, ADMIN). |
| **TC-DEP-04** | Servicio Systemd | Configuración y arranque del servicio de usuario. | Ejecutar `systemctl --user start app-lti` y verificar `systemctl --user status app-lti`. | Estado `Active: active (running)` y logs limpios en journal. | **PASSED:** Proceso corriendo bajo PID asignado. |
| **TC-DEP-05** | Persistencia Linger | Verificación de permanencia del servicio tras cierre de SSH. | Iniciar servicio, salir de sesión SSH (`exit`), esperar 30s y reconectar o hacer curl. | El servicio sigue activo ininterrumpidamente (`Active: active (running)`). | **PASSED:** `loginctl show-user iacdi` confirma `Linger=yes`. |
| **TC-DEP-06** | Acceso Web SPA | Carga de interfaz gráfica y estilos en navegador. | Abrir `http://100.82.24.75:8000` en navegador web. | Renderizado completo de la pantalla de login con temas claro/oscuro. | **PASSED:** HTML, JS y CSS cargan con código 200/304 sin errores de consola. |
| **TC-DEP-07** | Autenticación JWT | Inicio de sesión con perfiles PM, LTI y ADMIN. | Ingresar credenciales (`admin` / `Lti2026!`, `jbarrera`, `calbornoz`). | Generación de token JWT, almacenamiento en `localStorage` y redirección a dashboard según rol. | **PASSED:** Token emitido y validado en `/api/auth/me`. |
| **TC-DEP-08** | API Proyectos & KPIs | Consulta de proyectos, KPIs y drilldown. | Navegar por la tabla de proyectos, aplicar filtros de estado y abrir drilldown modal. | Endpoints `/api/proyectos`, `/api/dashboard-kpis`, `/api/solots` responden en < 500ms. | **PASSED:** Datos reales de MSSQL visualizados en frontend. |
| **TC-DEP-09** | Hot-Reload en Desarrollo | Actualización en caliente al modificar archivos. | Modificar un archivo en `backend/` o `frontend/` y guardar. | Uvicorn detecta el cambio (`Reloading...`) y reinicia el worker en < 2s sin tirar el servicio. | **PASSED:** Cambios reflejados inmediatamente sin intervención manual. |
| **TC-DEP-10** | Resiliencia Auto-Restart | Recuperación automática ante terminación de proceso. | Ejecutar `pkill -9 -f uvicorn` sobre el proceso de la app. | Systemd detecta la caída y reinicia el servicio automáticamente tras 5s. | **PASSED:** Estado vuelve a `active (running)` automáticamente. |

---

## 10. GUÍA RÁPIDA DE OPERACIONES Y CHEATSHEET DE COMANDOS

### 10.1. Comandos de Administración del Servicio en `iacdi`

```bash
# Conexión SSH directa al servidor
ssh iacdi@100.82.24.75   # o simplemente 'ssh iacdi' si está en ~/.ssh/config

# Ir al directorio del proyecto
cd /home/iacdi/Desarrollos/app-lti

# Estado del servicio
systemctl --user status app-lti.service

# Reiniciar servicio
systemctl --user restart app-lti.service

# Ver logs en vivo
journalctl --user -u app-lti -f

# Ver últimas 50 líneas de log
journalctl --user -u app-lti -n 50 --no-pager
```

### 10.2. Comandos de Sincronización desde Máquina Local

```bash
# Desde /home/bobbasystem/Desarrollos/app-lti
chmod +x deploy_to_iacdi.sh
./deploy_to_iacdi.sh
```

---

## 11. CHECKLIST PARA EL SUBAGENTE CODER

- [x] Crear el script de sincronización local `deploy_to_iacdi.sh` con permisos de ejecución (`chmod +x`).
- [x] Actualizar `run.sh` con detección adaptativa de entornos virtuales (`venv/bin/python3` prioritario).
- [x] Generar el archivo de unidad systemd de usuario `app-lti.service` listo para su instalación en `~/.config/systemd/user/`.
- [x] Actualizar la documentación `README.md` incorporando las instrucciones de despliegue, arquitectura Tailscale y comandos systemd.
- [x] Ejecutar el despliegue inicial hacia el servidor `iacdi` (creación de venv, instalación de dependencias, configuración de .env, habilitación de linger y activación de `app-lti.service`).
- [x] Verificar la correcta ejecución del servicio y reportar el estado al Subagente QA/Tester.

---

## 12. PLAN FORMAL DE DESPLIEGUE A PRODUCCIÓN IACDI (v1.3.0)

### 12.1. Alcance y Nuevas Capacidades en Versión 1.3.0
La versión **v1.3.0** introduce en producción una suite integral de monitoreo operativo y rediseño corporativo:
1. **Semáforo de Salud de Proyectos (Health Score):**
   - Algoritmo de ponderación en backend (`backend/db.py`) y serialización REST en `/api/proyectos`.
   - Estados: `CRITICAL` (Rojo: Solots vencidas o tickets estancados > 14 días), `WARNING` (Amarillo: Solots próximas a vencer <= 7 días o tickets en atención > 7 días), `HEALTHY` (Verde: Solots/Tickets al día y en curso) y `NEUTRAL` (Gris: Sin Solots ni tickets asociados).
   - Badges visuales con tooltip interactivo detallando motivos.
2. **Kill-Switch Reactivo Persistente:**
   - Toggle interactivo en la barra superior (`#toggle-health-score`).
   - Persistencia local mediante `localStorage.setItem('healthScoreEnabled', ...)`.
   - Desactivación instantánea sin recarga: oculta columnas, badges y filtros de salud sin impactar la estabilidad del sistema ni generar errores JS.
3. **Rediseño Corporativo HALO:**
   - Estandarización de tipografía Google Fonts (*Plus Jakarta Sans* y *Roboto*).
   - Paleta de diseño institucional Claro/VTR y nuevo isotipo/favicon SVG (`frontend/favicon.svg`).
   - KPIs de salud interactivos (`kpi-critico`, `kpi-riesgo`, `kpi-saludable`) con filtrado cruzado bidireccional.
4. **Módulo de Peticiones y Automatización de Tickets:**
   - Soporte para creación de peticiones LTI con streaming de logs y notificaciones SMTP Office 365.

---

### 12.2. Estrategia de Consolidación Git (Rama `sso-portal-acceso`)
Antes de transferir a producción, todo cambio debe quedar versionado de manera limpia e inmutable:

1. **Rama de trabajo:** `sso-portal-acceso`.
2. **Revisión de cambios pendientes:**
   - Archivos de Backend: `backend/db.py`, `backend/main.py`, `backend/ticket_automation.py`.
   - Archivos de Frontend: `frontend/index.html`, `frontend/css/styles.css`, `frontend/js/app.js`, `frontend/favicon.svg`.
   - Documentación Técnica: `SPECS_SEMAFORO_SALUD_PROYECTOS.md`, `SPECS_REDISENO_PORTAL_HALO.md`, `SPECS_DESPLIEGUE_IACDI_TAILSCALE.md`, `SPECS_TICKET_GENERATOR_PETICIONES.md`, `README.md`.
   - Batería de Pruebas: `tests/test_health_score.py`, `tests/test_functional_health_score.py`, `tests/test_functional_rediseno_halo.py`, `tests/test_functional_ticket_peticiones.py`, `tests/test_functional_filtro_estados_sharepoint.py`.
3. **Comando de Commit Semántico:**
   ```bash
   git add backend/ frontend/ tests/ SPECS_*.md README.md .env.example .gitignore portal_login.py portal_login_v2.py
   git commit -m "feat(salud): implementar semaforo de salud de proyectos, kill-switch ui y rediseno halo v1.3.0"
   ```

---

### 12.3. Procedimiento de Sincronización Remota (rsync)
La sincronización se realiza mediante el script oficial `deploy_to_iacdi.sh` o su comando directo `rsync`.

> [!CAUTION]
> **Protección del archivo `.env` en producción:** El archivo `/home/iacdi/Desarrollos/app-lti/.env` contiene las credenciales activas del servidor MSSQL y Office 365 SMTP. Está estrictamente protegido por la directiva `--exclude '.env'`. Bajo ninguna circunstancia debe ser sobrescrito desde el entorno local.

```bash
# 1. Asegurar permisos de ejecución en local
chmod +x deploy_to_iacdi.sh

# 2. Ejecutar sincronización hacia IACDI
./deploy_to_iacdi.sh
```

**Comando equivalente exacto ejecutado por el script:**
```bash
rsync -avz --progress \
    --exclude 'venv/' \
    --exclude '.git/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.pytest_cache/' \
    --exclude '.env' \
    --exclude '.DS_Store' \
    /home/bobbasystem/Desarrollos/app-lti/ iacdi:/home/iacdi/Desarrollos/app-lti/
```

**Verificación posterior a la sincronización en IACDI:**
```bash
# Verificar que .env mantenga permisos 600 y propietario iacdi
ssh iacdi "ls -la /home/iacdi/Desarrollos/app-lti/.env"
```

---

### 12.4. Ciclo de Vida del Servicio Systemd Remoto y Verificación
Dado que el servicio `app-lti.service` está configurado con `--reload`, los cambios en código Python y estáticos son detectados automáticamente. Sin embargo, para garantizar una carga limpia de memoria, limpieza de módulos cacheados y reinicio controlado, se ejecuta el ciclo systemd explícito:

```bash
# 1. Reinicio del servicio systemd de usuario
ssh iacdi "systemctl --user restart app-lti.service"

# 2. Comprobación del estado activo
ssh iacdi "systemctl --user is-active app-lti.service"
# Debe responder: active

# 3. Inspección detallada del status
ssh iacdi "systemctl --user status app-lti.service --no-pager"

# 4. Lectura de las últimas líneas del journal para verificar ausencia de excepciones
ssh iacdi "journalctl --user -u app-lti.service -n 35 --no-pager"

# 5. Confirmación de permanencia de Linger
ssh iacdi "loginctl show-user iacdi --property=Linger"
# Debe retornar: Linger=yes
```

---

### 12.5. Batería de Pruebas de Humo y Validación en Vivo (Tailscale 100.82.24.75)
Una vez reiniciado el servicio en `iacdi`, se ejecutan las siguientes pruebas de validación HTTP directas a través de la IP Tailscale `100.82.24.75:8000`:

#### TC-PROD-01: Disponibilidad y Carga del Frontend SPA (HALO)
```bash
curl -s http://100.82.24.75:8000/ | grep -E "HALO — App Líderes TI|favicon.svg|toggle-health-score"
```
*Criterio:* Debe retornar las etiquetas HTML correspondientes al nuevo branding, favicon y el switch del semáforo.

#### TC-PROD-02: Endpoint de Proyectos con Estructura de Salud
```bash
curl -s http://100.82.24.75:8000/api/proyectos | python3 -c "
import sys, json
data = json.load(sys.stdin)
assert isinstance(data, list), 'Formato de respuesta debe ser lista'
assert len(data) > 0, 'Debe retornar proyectos'
sample = data[0]
assert 'salud' in sample, 'Falta campo salud en proyecto'
assert 'score' in sample['salud'], 'Falta score'
assert 'color' in sample['salud'], 'Falta color'
assert 'label' in sample['salud'], 'Falta label'
print(f'✅ API Proyectos OK: {len(data)} proyectos analizados. Muestra salud: {sample[\"salud\"][\"label\"]} ({sample[\"salud\"][\"score\"]})')
"
```
*Criterio:* Código 200, serialización válida y presencia del objeto `salud` estructurado.

#### TC-PROD-03: Endpoint de KPIs de Salud
```bash
curl -s http://100.82.24.75:8000/api/dashboard-kpis | python3 -c "
import sys, json
kpis = json.load(sys.stdin)
print('✅ KPIs obtenidos:', kpis)
"
```
*Criterio:* Código 200 y métricas consolidadas sin excepciones MSSQL.

#### TC-PROD-04: Recurso de Favicon SVG
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://100.82.24.75:8000/favicon.svg
```
*Criterio:* HTTP 200 OK.

---

### 12.6. Plan de Contingencia y Rollback Operativo

En caso de detectarse cualquier anomalía operativa, inconsistencia de datos o degradación del servicio tras el despliegue, se aplicará el siguiente protocolo de contingencia según el nivel de impacto:

```mermaid
flowchart TD
    Incident[Alerta de Incidente en Producción] --> CheckSeverity{¿Nivel de Afectación?}
    
    CheckSeverity -->|UI / Visual / Usabilidad| SoftRollback[NIVEL 1: Activación Kill-Switch UI]
    CheckSeverity -->|Error 500 / Excepción Backend / Caída| HardRollback[NIVEL 2: Rollback Git & Re-sync]

    SoftRollback --> KillSwitchAction["Desmarcar toggle 'Semáforo de Salud' o inyectar:<br>localStorage.setItem('healthScoreEnabled', 'false')"]
    KillSwitchAction --> SoftVerified[La interfaz oculta instantáneamente el semáforo y vuelve a modo clásico sin downtime]

    HardRollback --> RevertGit["Revertir commit local:<br>git checkout HEAD~1"]
    RevertGit --> Resync["Sincronizar versión anterior:<br>./deploy_to_iacdi.sh"]
    Resync --> RestartSystemd["Reiniciar servicio:<br>ssh iacdi 'systemctl --user restart app-lti'"]
    RestartSystemd --> HardVerified[Servicio restaurado al estado inmediatamente anterior]
```

#### Protocolo de Rollback Nivel 1 (Kill-Switch sin intervención de servidor):
Si la incidencia es meramente de presentación visual o confusión de usuarios con el semáforo:
- Indicar a los usuarios desactivar el toggle en el navbar superior `#toggle-health-score`.
- O inyectar de forma preventiva en el frontend el valor `false` para la clave `healthScoreEnabled`.
- **Efecto:** Cero downtime, el sistema oculta badges, motivos y filtros sin necesidad de reiniciar el servicio ni sincronizar código.

#### Protocolo de Rollback Nivel 2 (Rollback de Código Completo):
Si se presenta una excepción fatal no capturada en FastAPI o falla de inicio del servicio:
1. Revertir el árbol local al commit inmediatamente anterior:
   ```bash
   git reset --hard HEAD~1
   ```
2. Ejecutar la sincronización rsync:
   ```bash
   ./deploy_to_iacdi.sh
   ```
3. Reiniciar el servicio en `iacdi`:
   ```bash
   ssh iacdi "systemctl --user restart app-lti.service"
   ```
4. Verificar retorno a estado operativo:
   ```bash
   ssh iacdi "systemctl --user status app-lti.service"
   curl -s http://100.82.24.75:8000/ | grep "<title>"
   ```

---

### 12.7. Checklist de Ejecución para el Subagente Coder

- [ ] **1. Consolidación Git:** Ejecutar `git add` y `git commit` semántico en la rama `sso-portal-acceso`.
- [ ] **2. Ejecución de Sync:** Ejecutar `./deploy_to_iacdi.sh` asegurando exclusión de `.env` y `.git`.
- [ ] **3. Reinicio de Servicio:** Ejecutar `systemctl --user restart app-lti.service` vía SSH en `iacdi`.
- [ ] **4. Comprobación de Logs:** Revisar `journalctl --user -u app-lti.service -n 35` verificando arranque limpio de Uvicorn.
- [ ] **5. Smoke Tests en Vivo:** Ejecutar verificaciones HTTP contra `http://100.82.24.75:8000` (`/`, `/favicon.svg`, `/api/proyectos`, `/api/dashboard-kpis`).
- [ ] **6. Reporte Final:** Entregar los resultados al Subagente Tester para validación final.

