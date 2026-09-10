# SPECS — Integración de App LTI al SSO del Portal de Acceso

| Versión | Fecha | Autor | Estado | Descripción |
|---|---|---|---|---|
| 1.0.0 | 2026-09-09 | Claude Sonnet 5 | Propuesta Inicial | Borrador de migración de login propio a SSO vía Portal |
| 2.0.0 | 2026-09-09 | Arquitecto y Planificador de Specs | **Ratificada / Lista para Implementación** | Especificación técnica definitiva con decisiones de usuario aprobadas, alcance local exclusivo en `bobbadeveloper` y plan de desarrollo detallado para el Coder |

---

## 0. Objetivo y Alcance

App LTI disponía de un sistema de login propio (credenciales locales en tabla `dbo.App_Usuarios` con `password_hash`, JWT local Bearer almacenado en `localStorage`, formulario de login modal/overlay y 38 usuarios iniciales hardcodeados en `backend/seed_users.py`).

El objetivo de esta integración es desacoplar la autenticación local y conectar App LTI al **Single Sign-On (SSO)** del **Portal de Acceso** (`~/portal-acceso`), alineándola con el estándar corporativo adoptado por `provision-plataformas`, `vlan-manager-v2` y `starlink-sync`.

Al culminar esta implementación:
1. **SSO Transparente**: Todo usuario con sesión iniciada en el Portal de Acceso entra automáticamente a App LTI sin volver a autenticarse.
2. **Sin Credenciales Locales**: App LTI ya no almacena contraseñas ni hashes (`password_hash`), ni emite tokens propios, ni muestra pantalla de login local.
3. **Gestión de Identidades Centralizada**: El alta de usuarios y contraseñas pasa 100% al Portal de Acceso. App LTI mantiene exclusivamente la administración de roles de negocio (`PM`, `LTI`, `ADMIN`) y vinculación de Líder TI (`lt_asignado`).

> [!CAUTION]
> ### REGLA CRÍTICA DE ENTORNO (NO TOCAR PRODUCCIÓN)
> La implementación y pruebas se realizan **EXCLUSIVAMENTE** en la estación de desarrollo local **`bobbadeveloper`** (`/home/bobbasystem/Desarrollos/app-lti`).
> **Queda estrictamente prohibido ejecutar scripts de despliegue (`./deploy_to_iacdi.sh`), conectarse por SSH a `iacdi` o modificar archivos en el servidor de producción.** La sincronización hacia `iacdi` solo se realizará en una fase posterior autorizada formalmente por el usuario.

---

## 1. Decisiones Técnicas Ratificadas por el Usuario

En la fase de definición con el usuario, se han confirmado las 4 decisiones estructurales:

### 1.1 Slug y Ruta Canónica en Nginx
- **Slug oficial**: `app-lti`.
- **Ruta de acceso web**: `https://200.14.222.162/app-lti/`.
- **Configuración Nginx**: `location /app-lti/ { proxy_pass http://127.0.0.1:8000/; ... }`. La barra final en `location` y `proxy_pass` permite que FastAPI reciba las rutas relativas a su raíz interna (`/`, `/api/...`, `/css/...`, `/js/...`).
- **Rutas de Frontend**: Todos los recursos en `index.html` y llamadas fetch en `app.js` deben ser relativos o agnósticos al prefijo `/app-lti/` para garantizar funcionamiento dual (directo en `http://localhost:8000` o proxied en `https://200.14.222.162/app-lti/`).

### 1.2 Reemplazo de Cuentas Hardcodeadas por Cuentas del Portal
- **Eliminación del Seed de 38 cuentas anteriores**: Desaparecen los usernames obsoletos tipo `calbornoz`, `aaguilar`, `jbarrera`, `sortiz`, `admin`, etc.
- **Formato canónico**: Se adopta el estándar oficial del Portal de Acceso: `nombre.apellido` en minúsculas (ejemplos: `alejandro.aguilar`, `solange.ortiz`, `juan.barrera`, `samuel.paredes`, `erwin.sandoval`, etc.).
- **Desactivación de borrado destructivo**: Se elimina completamente la sentencia `DELETE FROM dbo.App_Usuarios WHERE username NOT IN (...)` en `backend/seed_users.py`. App LTI no debe eliminar cuentas de la base de datos de manera arbitraria al arrancar el servicio.
- **Aprovisionamiento Just-In-Time (JIT)**: Cuando un usuario autenticado por el Portal ingresa a App LTI y no existe aún en `dbo.App_Usuarios`, el backend lo registra automáticamente (JIT Provisioning) con su `username` del portal, estado `activo = 1` y rol predeterminado (`PM` o según su `toolAccess`), permitiendo que el Administrador de App LTI solo deba asignarle su `lt_asignado` y rol específico.

### 1.3 Mapeo de `toolAccess` y Jerarquía de Roles
El JWT del Portal entrega `adminLevel` (0: usuario, 1: admin, 2: superadmin) y un diccionario `toolAccess`:
```json
{
  "sub": 15,
  "username": "alejandro.aguilar",
  "email": "alejandro.aguilarm@clarovtr.cl",
  "adminLevel": 2,
  "purpose": "session",
  "toolAccess": {
    "app-lti": "operador"
  }
}
```

La lógica de autorización en App LTI se rige por la siguiente matriz:

| `adminLevel` Portal | `toolAccess["app-lti"]` Portal | Rol en `dbo.App_Usuarios` | Permiso Efectivo en App LTI | Capacidades / Módulos |
|---|---|---|---|---|
| 2 (Super Admin) | *(Cualquiera / Ausente)* | `ADMIN` | **ADMIN** | Acceso total: Seguimiento, Búsqueda, Tickets, Solicitud, Mantenedor Roles, Eliminar proyectos |
| 2 (Super Admin) | *(Cualquiera / Ausente)* | `LTI` | **LTI** | Operación completa: Seguimiento, Búsqueda, Tickets, Solicitud, Editar proyectos |
| 2 (Super Admin) | *(Cualquiera / Ausente)* | `PM` (o no existe) | **LTI** (o ADMIN según BD) | Permiso operativo habilitado por Super Admin |
| 0 ó 1 | `"operador"` | `ADMIN` | **ADMIN** | Acceso total según perfil local de App LTI |
| 0 ó 1 | `"operador"` | `LTI` | **LTI** | Perfil operativo según perfil local de App LTI |
| 0 ó 1 | `"operador"` | `PM` (o nuevo JIT) | **PM** | Lectura y Solicitud LTI hasta que ADMIN asigne rol superior |
| 0 ó 1 | `"lectura"` o Ausente | *(Cualquiera)* | **PM (Solo Lectura)** | **Restricción Forzosa**: Solo visualización y Solicitud LTI. No puede crear tickets, ni editar proyectos, ni ver mantenedor de usuarios |
| *(Cualquiera)* | *(Cualquiera)* | `activo = 0` (Local) | **403 FORBIDDEN** | Acceso bloqueado administrativamente en App LTI |

> [!IMPORTANT]
> **El Portal manda sobre la capacidad de escritura**: Si en el Portal el usuario tiene `"lectura"` o no tiene la herramienta asignada (y no es Super Admin), su rol efectivo se degrada inmediatamente a `PM`, impidiendo cualquier mutación destructiva o creación de tickets, independientemente de lo que guarde la tabla local.

### 1.4 Centralización de Gestión de Cuentas y Limpieza de App LTI
- **Alta de cuentas**: 100% en el Portal de Acceso (módulo Panel de Administración &rarr; Usuarios). Se elimina el formulario y modal "Nuevo Usuario" (`create-user-modal`) y se deshabilita `POST /api/usuarios`.
- **Contraseñas**: 100% en el Portal de Acceso. Se elimina el modal "Resetear Contraseña" (`reset-user-password-modal`), se deshabilitan `POST /api/usuarios/{id}/reset-password` y `POST /api/auth/change-password`. Se retira la columna `password_hash` de `dbo.App_Usuarios`.
- **Mantenedor Local de App LTI**: Se conserva exclusivamente para:
  - Listar usuarios existentes en App LTI (`GET /api/usuarios`).
  - Asignar `rol` (`PM`, `LTI`, `ADMIN`) y `lt_asignado` (`PUT /api/usuarios/{id}`).
  - Alternar estado `activo` (`PATCH /api/usuarios/{id}/toggle-status`).
  - Eliminar registro local de vinculación (`DELETE /api/usuarios/{id}`), aclarando en el modal que solo borra la configuración en App LTI y no la cuenta corporativa del Portal.

---

## 2. Arquitectura de Autenticación SSO

```
+-------------------------------------------------------------------------------+
|                       NAVEGADOR DEL USUARIO                                   |
|  Accede a: https://200.14.222.162/app-lti/                                    |
|  Cookies HttpOnly automáticas: access_token, refresh_token (SameSite=Lax, /)  |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
|                   NGINX (Portal de Acceso - 200.14.222.162)                   |
|  location /app-lti/ { proxy_pass http://127.0.0.1:8000/; }                    |
|  location /api/auth/refresh { proxy_pass http://127.0.0.1:3001; } (Portal)   |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
|                   FASTAPI BACKEND (App LTI - Puerto 8000)                     |
|                                                                               |
|  1. Request Cookies -> access_token                                           |
|  2. PyJWT decode con JWT_ACCESS_SECRET (HS256)                                |
|  3. Validar payload.purpose == "session" & exp                                |
|  4. Extraer payload.username ("nombre.apellido") y adminLevel/toolAccess       |
|  5. Consultar dbo.App_Usuarios (si no existe -> JIT Provisioning)             |
|  6. Calcular Rol Efectivo (Portal + BD Local)                                 |
|  7. Inyectar `current_user` en endpoints protegidos (Depends)                |
+-------------------------------------------------------------------------------+
```

### 2.1 Especificación del JWT del Portal
- **Algoritmo**: `HS256`.
- **Firma**: `JWT_ACCESS_SECRET` (variable configurada en `.env`).
- **Duración típica**: 15 minutos (refresh token de 7 días gestionado por el Portal).
- **Nombre de cookie**: `access_token`.
- **Payload**:
  ```python
  {
      "sub": int,           # ID numérico de usuario en portal
      "username": str,      # "nombre.apellido"
      "email": str,         # "nombre.apellido@clarovtr.cl"
      "roles": list[str],   # Roles generales del portal
      "adminLevel": int,    # 0=Normal, 1=Admin, 2=Super Admin
      "purpose": "session", # Validador estricto de propósito
      "toolAccess": {       # Opcional si adminLevel == 2
          "app-lti": "operador" | "lectura"
      },
      "iat": int,
      "exp": int
  }
  ```

### 2.2 Ciclo de Vida de Peticiones y Refresh en Frontend
1. Toda petición fetch a la API de App LTI debe incluir `{ credentials: 'include' }` para que el navegador adjunte automáticamente la cookie `access_token`.
2. Se eliminan el almacenamiento de tokens en `localStorage` (`app_lti_token`) y el header `Authorization: Bearer ...`.
3. Si FastAPI responde `401 Unauthorized` (token expirado):
   - El frontend intercepta el 401 en `authFetch()`.
   - Ejecuta de inmediato `POST /api/auth/refresh` (hacia el Portal, ruta absoluta en el mismo origen) con `credentials: 'include'`.
   - El Portal renueva la cookie `access_token` HttpOnly.
   - `authFetch()` reintenta la petición original fallida automáticamente sin interrumpir la interacción del usuario.
   - Las llamadas concurrentes comparten una única promesa de refresh (`refreshPromise`) para no duplicar llamadas al endpoint de refresh.
   - Si el refresh falla (sesión totalmente caducada), redirige al usuario a la página de login del Portal (`/login` o `/`).

---

## 3. Modificaciones Detalladas por Componente

### 3.1 Backend: `backend/config.py` y `.env`
- Incorporar la lectura de `PORTAL_JWT_SECRET` / `JWT_ACCESS_SECRET` desde el entorno.
  ```python
  PORTAL_JWT_SECRET = os.getenv("PORTAL_JWT_SECRET") or os.getenv("JWT_ACCESS_SECRET") or os.getenv("JWT_SECRET", "lti-dev-secret-key-2026")
  ```
- Mantener fallback para desarrollo local en `bobbadeveloper` que permita pruebas unitarias sin dependencias externas.

### 3.2 Backend: `backend/auth.py`
- **Reemplazar `get_current_user`**:
  - Obtener el cookie `access_token` desde `fastapi.Request.cookies` (o fallback a header `Authorization: Bearer` en desarrollo/tests para compatibilidad de testing).
  - Decodificar el token con `PORTAL_JWT_SECRET` y algoritmo `HS256`.
  - Validar que `payload.get("purpose") == "session"`.
  - Extraer `username = payload.get("username", "").strip().lower()`.
  - Evaluar permisos del Portal:
    ```python
    is_super_admin = payload.get("adminLevel", 0) >= 2
    tool_perm = (payload.get("toolAccess") or {}).get("app-lti")
    has_operator = is_super_admin or tool_perm == "operador"
    has_read = has_operator or tool_perm == "lectura" or is_super_admin
    ```
  - Si el usuario no tiene ni `has_read` ni `is_super_admin`: emitir `403 Forbidden` ("No tienes permisos asignados para acceder a App LTI en el Portal de Acceso").
  - Buscar usuario en `dbo.App_Usuarios` por `username`.
  - **Aprovisionamiento JIT**: Si no existe en la base de datos:
    - Crear el usuario automáticamente con:
      - `username`: `username`
      - `nombre_completo`: `payload.get("username", "").replace(".", " ").title()`
      - `rol`: `"PM"` (o `"ADMIN"` si es superadmin inicial)
      - `lt_asignado`: Si coincide con alguno de los líderes oficiales, asignar automáticamente; de lo contrario `None`
      - `activo`: 1
  - Validar estado `activo`: Si `user.get("activo")` es 0/False, emitir `403 Forbidden` ("Usuario bloqueado en App LTI").
  - **Calcular Rol Efectivo**:
    - Si `has_operator`: Rol efectivo = `user.get("rol", "PM").upper()`. (Puede ser ADMIN o LTI si así está registrado).
    - Si solo `has_read` (o no tiene operador): Rol efectivo = `"PM"`. (Forzar a solo lectura/solicitud).
  - Devolver diccionario enriquecido:
    ```python
    {
        "id": user["id"],
        "username": user["username"],
        "nombre_completo": user["nombre_completo"],
        "lt_asignado": user["lt_asignado"],
        "rol": effective_role,
        "raw_rol": user["rol"],
        "portal_access": "operador" if has_operator else "lectura",
        "is_super_admin": is_super_admin
    }
    ```
- Mantener los decoradores/helpers `require_admin`, `require_lti_or_admin`, `require_non_pm` usando el rol efectivo `current_user["rol"]`.

### 3.3 Backend: `backend/db.py`
- **`init_auth_tables()`**:
  - En la creación de `dbo.App_Usuarios`, omitir `password_hash` si la tabla no existe:
    ```sql
    CREATE TABLE dbo.App_Usuarios (
        id INT IDENTITY(1,1) PRIMARY KEY,
        username VARCHAR(100) NOT NULL UNIQUE,
        nombre_completo VARCHAR(150) NOT NULL,
        lt_asignado VARCHAR(150) NULL,
        rol VARCHAR(50) NOT NULL DEFAULT 'PM',
        activo BIT NOT NULL DEFAULT 1,
        created_at DATETIME NOT NULL DEFAULT GETDATE(),
        updated_at DATETIME NOT NULL DEFAULT GETDATE()
    );
    ```
  - Si la tabla ya existe y contiene `password_hash`, no romper.
- **Creación y consulta JIT**:
  - Función `get_or_create_jit_user(username, nombre_completo, default_rol="PM")` que busca por username o inserta idempotentemente sin requerir `password_hash`.
- **Actualización de Usuarios (`update_usuario`)**:
  - Se mantiene para editar `nombre_completo`, `lt_asignado`, `rol`, `activo`.
- **Depuración de funciones de contraseñas**:
  - `reset_user_password` se deja obsoleta o se retira.
  - `create_usuario` se adapta para no requerir `password_hash`.

### 3.4 Backend: `backend/seed_users.py`
- Eliminar la lista `USERS_CANONICAL_SEED` con 38 cuentas con prefijos antiguos.
- Reemplazar por semilla canónica orientada a los roles y líderes reales del Portal (`nombre.apellido`):
  ```python
  CANONICAL_PORTAL_USERS = [
      ("Alejandro Aguilar", "ADMIN", "alejandro.aguilar", "Alejandro Aguilar"),
      ("Solange Ortiz", "LTI", "solange.ortiz", "Solange Ortiz"),
      ("Juan Barrera", "LTI", "juan.barrera", "Juan Barrera"),
      ("Samuel Paredes", "LTI", "samuel.paredes", "Samuel Paredes"),
      ("Erwin Sandoval", "LTI", "erwin.sandoval", "Erwin Sandoval"),
  ]
  ```
- **Eliminar definitivamente la sentencia destructiva**:
  ```python
  # ELIMINADO: cursor.execute(f"DELETE FROM dbo.App_Usuarios WHERE username NOT IN ...")
  ```
- Al sincronizar, solo insertar o actualizar los líderes/administradores conocidos si no existen, preservando cualquier otro usuario provisto vía JIT o creado por el portal.

### 3.5 Backend: `backend/main.py`
- Retirar endpoints de autenticación propia:
  - `POST /api/auth/login` &rarr; Retirar o retornar 404/410 Gone ("Autenticación migrada a SSO Portal de Acceso").
  - `POST /api/auth/change-password` &rarr; Retirar o retornar 404/410 Gone.
- Mantener y ajustar `GET /api/auth/me`:
  - Utiliza `Depends(get_current_user)`.
  - Retorna los datos del usuario actual y su rol efectivo.
- Retirar endpoints de gestión de contraseñas y alta de usuario:
  - `POST /api/usuarios` &rarr; Retirar o retornar 405 Method Not Allowed ("El alta de usuarios se realiza exclusivamente en el Portal de Acceso").
  - `POST /api/usuarios/{user_id}/reset-password` &rarr; Retirar o retornar 405.
- Mantener `GET /api/usuarios`, `GET /api/usuarios/{id}`, `PUT /api/usuarios/{id}`, `PATCH /api/usuarios/{id}/toggle-status`, `DELETE /api/usuarios/{id}` protegidos con `require_admin`.
- Ajustar configuración de `CORSMiddleware`: permitir origen del portal `https://200.14.222.162` y orígenes locales de desarrollo (`http://localhost:8000`, `http://127.0.0.1:8000`), con `allow_credentials=True`.

### 3.6 Frontend: `frontend/js/auth.js`
- Reescribir con patrón de SSO corporativo (`starlink-sync`):
  - No almacenar tokens en `localStorage`. Almacenar solo metadata de UI del usuario (`app_lti_user`).
  - Implementar `authFetch(url, options)` con `{ credentials: 'include' }`.
  - Manejo de Refresh con promesa única compartida (`isRefreshing`, `refreshPromise`).
  - Redirección automática a `/login` del Portal ante fallo definitivo de autenticación.
  - Exponer métodos: `authFetch`, `getUser`, `setUser`, `checkSession`, `logout` (que llama a `/api/auth/logout` del portal o limpia estado y redirige).

### 3.7 Frontend: `frontend/index.html`
- **Eliminar pantalla de login (`auth-view`)**:
  - Remover el formulario de login y la ayuda con usuarios hardcodeados (`esandoval`, `admin`, `Lti2026!`).
  - Reemplazar por un loader o splash de verificación de sesión SSO ("Comprobando sesión en Portal de Acceso...").
- **Ajustar Mantenedor de Usuarios**:
  - Eliminar o remover el botón `btn-open-create-user-modal` ("+ Nuevo Usuario").
  - Eliminar el modal `create-user-modal`.
  - Eliminar el modal `reset-user-password-modal`.
  - En el modal `delete-user-modal`, actualizar el texto aclaratorio: *"El registro de roles y líder asignado será eliminado de App LTI. La cuenta del usuario en el Portal de Acceso NO será eliminada."*
- **Asegurar compatibilidad de rutas relativas**:
  - Validar `<link rel="stylesheet" href="css/styles.css">` o base URL relativa para que funcione sin alteración bajo `/app-lti/`.

### 3.8 Frontend: `frontend/js/app.js`
- En `init()`:
  - Llamar a `await Auth.checkSession()` o `GET /api/auth/me`.
  - Si la sesión es válida, invocar `showAppView()` y cargar datos iniciales.
  - Si no es válida o devuelve 401, redirigir a la pantalla de login del Portal de Acceso.
- Eliminar listeners del login form y modal de reseteo de contraseña.
- Eliminar o desactivar `openCreateUserModal` y `openResetUserPasswordModal`.
- En la tabla de usuarios (`renderUsuariosTable`):
  - Ocultar/retirar la acción del botón de llave (`btn-action-user-key`).
  - Dejar solo acciones de Editar (`✏️`), Bloquear/Desbloquear (`🔒`/`🔓`) y Eliminar mapeo local (`🗑️`).

---

## 4. Plan de Implementación Paso a Paso para el Coder

| Paso | Área | Archivos Involucrados | Descripción de Tareas |
|---|---|---|---|
| **Paso 1** | Configuración & Variables | `backend/config.py`, `.env.example`, `.env` | Configurar lectura de `PORTAL_JWT_SECRET` / `JWT_ACCESS_SECRET` manteniendo compatibilidad local en `bobbadeveloper`. |
| **Paso 2** | Base de Datos & Seeds | `backend/db.py`, `backend/seed_users.py` | 1. Modificar `init_auth_tables()` para esquema sin `password_hash`.<br>2. Agregar soporte JIT `get_or_create_jit_user`.<br>3. Adaptar `seed_users.py` con cuentas canónicas (`nombre.apellido`), eliminando borrado destructivo y contraseñas por defecto. |
| **Paso 3** | Autenticación Backend | `backend/auth.py` | 1. Implementar `decode_portal_token` validando HS256 y `purpose == 'session'`.<br>2. Adaptar `get_current_user` para leer cookie `access_token` (con fallback a header Bearer para pruebas unitarias).<br>3. Implementar lógica de permisos y rol efectivo (`toolAccess` + rol local + JIT). |
| **Paso 4** | Endpoints API | `backend/main.py` | 1. Retirar/desactivar `POST /api/auth/login`, `POST /api/auth/change-password`, `POST /api/usuarios`, `POST /api/usuarios/{id}/reset-password`.<br>2. Adaptar `GET /api/auth/me` y `PUT /api/usuarios/{id}`.<br>3. Configurar CORS con soporte de credenciales. |
| **Paso 5** | Módulo Frontend Auth | `frontend/js/auth.js` | Reescribir `Auth` con `credentials: 'include'`, refresh automático vía `POST /api/auth/refresh` y redirección a login del Portal. |
| **Paso 6** | UI & Templates | `frontend/index.html`, `frontend/js/app.js` | 1. Eliminar pantalla/formulario de login local.<br>2. Eliminar modales de "Nuevo Usuario" y "Resetear Contraseña".<br>3. Adaptar tabla de usuarios y flujo de inicio con comprobación de sesión SSO. |
| **Paso 7** | Pruebas & Verificación Local | `tests/`, bash tests | 1. Ejecutar pruebas unitarias y funcionales en `bobbadeveloper`.<br>2. Validar que no se rompan las llamadas a proyectos, KPIs, tickets ni solicitudes LTI.<br>3. Verificar estricto cumplimiento de NO tocar `iacdi`. |

---

## 5. Historial de Cambios de Esquema de Base de Datos

En caso de requerir ajustar la columna `password_hash` en bases de datos existentes:
```sql
-- Script de migración opcional para liberar restricción NOT NULL o retirar columna
IF EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'App_Usuarios' AND COLUMN_NAME = 'password_hash')
BEGIN
    ALTER TABLE dbo.App_Usuarios ALTER COLUMN password_hash VARCHAR(255) NULL;
    -- Opcional (tras validación total de SSO):
    -- ALTER TABLE dbo.App_Usuarios DROP COLUMN password_hash;
END
```

---

## 6. Verificación de Seguridad y Buenas Prácticas

- [x] **Sin secretos en código**: `PORTAL_JWT_SECRET` se obtiene exclusivamente mediante variables de entorno.
- [x] **Cookies Seguras**: El navegador maneja la cookie `access_token` como `HttpOnly` y `SameSite=Lax`, previniendo ataques XSS de extracción de token.
- [x] **Defensa en Profundidad**: Aún si un usuario tiene perfil ADMIN en la base de datos local, si el Portal de Acceso revoca su permiso o lo degrada a `"lectura"`, App LTI restringe sus privilegios a solo lectura inmediatamente.
- [x] **Aislamiento de Entorno**: El código respeta íntegramente el ambiente de desarrollo local `bobbadeveloper` sin impactar la base de datos productiva ni el servicio en `iacdi`.
