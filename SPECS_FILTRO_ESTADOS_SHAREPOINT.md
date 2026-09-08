# ESPECIFICACIÓN TÉCNICA Y ARQUITECTÓNICA (SPECS)
## Módulo: "Seguimiento de Proyectos — Catálogo Canónico y Corrección del Filtro de Estados SharePoint" (`app-lti`)

- **Documento:** SPECS-LTI-MOD-007
- **Versión:** 1.0.0
- **Fecha:** 2026-09-08
- **Autor:** Subagente 1 (Planificador & Arquitecto de Software)
- **Destinatario:** Subagente 2 (Codificador & Implementador), Subagente 3 (Auditor de Calidad / Code Reviewer), Subagente 4 (Tester QA), Subagente 5 (Desplegador / DevOps)
- **Ubicación del Proyecto:** `/home/bobbasystem/Desarrollos/app-lti`

---

## CONTROL DE VERSIONES Y REGISTRO DE CAMBIOS

| Versión | Fecha | Autor | Descripción del Cambio |
|---|---|---|---|
| **1.0.0** | 2026-09-08 | Subagente 1 (Planificador) | **Especificación Técnica Inicial:**<br>1. Diagnóstico de causa raíz del problema reportado por el usuario en el módulo *Seguimiento Proyectos*, donde el filtro *Estado Sharepoint* (`#filter-estado-sp`) únicamente presentaba la opción `'Atendido'`.<br>2. Transición del antipatrón de consulta dinámica a base de datos (`SELECT DISTINCT Estado FROM dbo.Proyectos`) hacia el **Catálogo Canónico Oficial** de estados del ciclo de vida de proyectos SharePoint: `['Generado', 'En revision', 'Atendido']`, replicando la solución arquitectónica implementada en `get_lideres_list()`.<br>3. Especificación técnica de contratos de API Backend (`backend/db.py`, `backend/main.py`, `/api/estados`).<br>4. Especificación técnica de Frontend UI (`frontend/index.html`, `frontend/js/app.js`) con fallback defensivo, preservación de estado seleccionado y sincronización en ciclo de vida de cambio de módulo.<br>5. Matriz exhaustiva de pruebas de Backend y E2E Playwright. |

---

## 1. DIAGNÓSTICO DETALLADO Y CAUSA RAÍZ

### 1.1. Descripción del Problema Reportado por el Usuario
Al acceder al módulo **"Seguimiento Proyectos"**, al desplegar el selector de filtro **"Estado Sharepoint"** (`#filter-estado-sp`), la única opción disponible además del comodín general era `"Atendido"`. Los estados **"Generado"** y **"En revision"** no aparecían disponibles para filtrar los proyectos.

```text
ESTADO ACTUAL PROBLEMÁTICO:
Selector #filter-estado-sp:
├── [ — Estado Sharepoint (Todos) — ] (value="")
└── [ Atendido ]                      (value="Atendido")  <-- Único estado disponible en UI
```

### 1.2. Causa Raíz Técnica (Backend DB & API)
En el backend (`backend/db.py`), la función `get_estados_list()` ejecutaba una consulta SQL dinámica dependiente del estado actual de los registros en la base de datos:

```python
# CÓDIGO ANTERIOR EN backend/db.py (Líneas 354-367):
def get_estados_list():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT Estado 
                FROM dbo.Proyectos 
                WHERE Estado IS NOT NULL 
                  AND LTRIM(RTRIM(Estado)) <> ''
                  AND (Tipo_Servicio IS NULL OR Tipo_Servicio <> 'Reunión')
                ORDER BY Estado ASC
            """)
            estados_sp = [r['Estado'] for r in cursor.fetchall()]
            ...
```

**Mecanismo de Falla:**
1. En entornos de producción o pruebas donde todos los registros existentes en `dbo.Proyectos` (excluyendo tipo reunión) se encuentran finalizados o cerrados con `Estado = 'Atendido'`, la consulta `SELECT DISTINCT Estado` devuelve un conjunto de una sola fila: `[{'Estado': 'Atendido'}]`.
2. Como resultado, la API `GET /api/estados` respondía con el payload JSON:
   ```json
   {
     "estados_sharepoint": ["Atendido"],
     "estados_sga": [...]
   }
   ```
3. El frontend consumía esta lista y poblaba dinámicamente el `<select id="filter-estado-sp">`, omitiendo los estados canónicos `'Generado'` y `'En revision'`.
4. El usuario quedaba imposibilitado de filtrar proyectos en curso (`'Generado'`) o en evaluación técnica (`'En revision'`), o de auditar si existían proyectos en esos estados.

### 1.3. Comparación y Paralelismo Arquitectónico con `get_lideres_list()`
El sistema `app-lti` ya enfrentó un problema análogo con el selector de **Líderes TI** (`#filter-lt`), donde una consulta dinámica `SELECT DISTINCT LT_Asignado` generaba inconsistencias, nombres duplicados por tipeo o desaparición de líderes si no tenían proyectos asignados.

La solución arquitectónica establecida en `SPECS_MEJORAS_SEGUIMIENTO_LIDERES_KPIS.md` fue establecer un **Catálogo Canónico Oficial y Autoritativo** en `get_lideres_list()`:
```python
def get_lideres_list():
    """Retorna la lista oficial y estricta de Líderes TI activos."""
    return [
        "Alejandro Aguilar",
        "Erwin Sandoval",
        "Juan Barrera",
        "Samuel Paredes",
        "Solange Ortiz"
    ]
```

De igual forma, el ciclo de vida de los proyectos SharePoint en `app-lti` cuenta con una definición canónica de 3 estados de negocio, respaldada en:
- `backend/main.py`: `estados_permitidos = ["Generado", "En revision", "Atendido"]`
- `backend/db.py` (`insert_solicitud_lti`): Estado inicial inmutable = `'Generado'`.
- `SPECS_EDIT_DELETE_PROYECTOS.md`: Estados permitidos para actualización: `'Generado'`, `'En revision'`, `'Atendido'`.
- `frontend/index.html` (`#edit-project-estado`): Opciones canónicas fijadas en el modal de edición.

Por tanto, la obtención de estados de SharePoint debe desacoplarse de los datos transitorios de la BD y regirse por el **Catálogo Canónico Oficial**.

```mermaid
flowchart TD
    subgraph Antiguo_Flujo_Fragil["Antiguo Flujo Frágil (Dependiente de Registros)"]
        A1["Cliente / Frontend"] -->|GET /api/estados| B1["backend/main.py"]
        B1 --> C1["backend/db.py: get_estados_list()"]
        C1 -->|SELECT DISTINCT Estado FROM dbo.Proyectos| D1[("MSSQL dbo.Proyectos\n(Solo registros 'Atendido')")]
        D1 -->|Retorna ['Atendido']| C1
        C1 -->|{'estados_sharepoint': ['Atendido']}| A1
        A1 -->|Renderiza solo 'Atendido'| E1["❌ UI Incompleta: Faltan 'Generado' y 'En revision'"]
    end

    subgraph Nuevo_Flujo_Canonico["Nuevo Flujo Canónico & Resiliente"]
        A2["Cliente / Frontend"] -->|GET /api/estados| B2["backend/main.py"]
        B2 --> C2["backend/db.py: get_estados_list()"]
        C2 -->|Catálogo Canónico Inmutable| D2["CANONICAL_ESTADOS_SP:\n['Generado', 'En revision', 'Atendido']"]
        D2 --> C2
        C2 -->|{'estados_sharepoint': ['Generado', 'En revision', 'Atendido']}| A2
        A2 -->|Renderiza catálogo completo + Fallback UI| E2["✅ UI Completa: Todos los estados disponibles"]
    end
```

---

## 2. ESPECIFICACIÓN TÉCNICA BACKEND

### 2.1. Catálogo Canónico en `backend/db.py`
En `backend/db.py`, se define la constante y se actualiza la función `get_estados_list()`:

```python
# =============================================================================
# CATÁLOGOS CANÓNICOS DEL SISTEMA
# =============================================================================

CANONICAL_ESTADOS_SHAREPOINT = [
    "Generado",
    "En revision",
    "Atendido"
]

def get_estados_list() -> dict:
    """
    Retorna el catálogo canónico oficial de estados de proyectos SharePoint (dbo.Proyectos)
    y la lista de estados dinámicos de solots SGA (dbo.CT_BACKLOG_OPERACIONES2).
    
    Para SharePoint, devuelve siempre los 3 estados oficiales del ciclo de vida:
    ['Generado', 'En revision', 'Atendido'], evitando dependencias frágiles de los
    registros transitorios existentes en la tabla.
    """
    estados_sp = list(CANONICAL_ESTADOS_SHAREPOINT)
    estados_sga = []

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT ESTADO_OTP 
                FROM dbo.CT_BACKLOG_OPERACIONES2 
                WHERE ESTADO_OTP IS NOT NULL 
                  AND LTRIM(RTRIM(ESTADO_OTP)) <> ''
                ORDER BY ESTADO_OTP ASC
            """)
            estados_sga = [r['ESTADO_OTP'] for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error al obtener lista de estados SGA desde BD: {e}")
        estados_sga = []
    finally:
        conn.close()

    return {
        "estados_sharepoint": estados_sp,
        "estados_sga": estados_sga
    }
```

### 2.2. Contrato de la API REST `/api/estados` en `backend/main.py`
El endpoint `GET /api/estados` expone los catálogos garantizando el contrato:

- **Método HTTP:** `GET`
- **Ruta:** `/api/estados`
- **Autenticación:** Requerida vía Bearer JWT Token (`require_lti_or_admin`).
- **Permisos RBAC:**
  - `ADMIN`: Permitido (HTTP 200).
  - `LTI`: Permitido (HTTP 200).
  - `PM`: Acceso denegado (HTTP 403 Forbidden).

#### Estructura de Respuesta JSON (HTTP 200 OK):
```json
{
  "estados_sharepoint": [
    "Generado",
    "En revision",
    "Atendido"
  ],
  "estados_sga": [
    "ASIGNADA",
    "CANCELADA",
    "EN EJECUCION",
    "LIQUIDADA",
    "PENDIENTE"
  ]
}
```

### 2.3. Filtrado de Proyectos por Estado SharePoint (`/api/proyectos`)
En `get_proyectos(lt_filter, search, estado_sp, estado_sga)` en `backend/db.py`:
Cuando el usuario selecciona un estado en `#filter-estado-sp`, el frontend envía el parámetro `estado_sp` en el query string:
`GET /api/proyectos?estado_sp=Generado`

La consulta SQL aplica el filtro exacto:
```sql
SELECT p.ID, p.Cliente, p.Numero_Proyecto, p.LT_Asignado, p.Estado, p.Detalle, p.Comentario, p.Tipo_Servicio, p.Creado
FROM dbo.Proyectos p
WHERE (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')
  AND p.Estado = %s
ORDER BY 
    CASE WHEN p.Creado IS NOT NULL THEN 0 ELSE 1 END,
    p.Creado DESC,
    p.ID DESC;
```

---

## 3. ESPECIFICACIÓN TÉCNICA FRONTEND

### 3.1. Estructura HTML (`frontend/index.html`)
Para ofrecer renderizado instantáneo y protección defensiva contra latencia o fallos de red, el elemento `<select id="filter-estado-sp">` debe incluir las opciones canónicas predeterminadas:

```html
<!-- Filtro Estado Sharepoint -->
<div style="min-width: 200px;">
  <select id="filter-estado-sp" class="form-select" title="Estado en Sharepoint (dbo.Proyectos)">
    <option value="">— Estado Sharepoint (Todos) —</option>
    <option value="Generado">Generado</option>
    <option value="En revision">En revision</option>
    <option value="Atendido">Atendido</option>
  </select>
</div>
```

### 3.2. Lógica de Consumo y Renderizado Defensivo (`frontend/js/app.js`)

#### 3.2.1. Constante Canónica y Fallback
En `frontend/js/app.js`, se define el catálogo canónico por defecto:

```javascript
const CANONICAL_ESTADOS_SHAREPOINT = ['Generado', 'En revision', 'Atendido'];
```

#### 3.2.2. Método `loadEstados()`
El método `loadEstados()` en `app.js` se actualiza con manejo robusto de excepciones, preservación de estado seleccionado y fallback automático:

```javascript
async loadEstados() {
  const selectSp = document.getElementById('filter-estado-sp');
  const previousValue = selectSp ? selectSp.value : '';

  try {
    const res = await Auth.fetchWithAuth('/api/estados');
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    
    // Asignación con fallback canónico si la lista viene vacía
    if (Array.isArray(data.estados_sharepoint) && data.estados_sharepoint.length > 0) {
      this.estadosSharepoint = data.estados_sharepoint;
    } else {
      this.estadosSharepoint = [...CANONICAL_ESTADOS_SHAREPOINT];
    }
  } catch (e) {
    console.warn('No se pudieron obtener los estados desde API, aplicando catálogo canónico:', e);
    this.estadosSharepoint = [...CANONICAL_ESTADOS_SHAREPOINT];
  }

  if (selectSp) {
    selectSp.innerHTML = '';
    
    // 1. Opción por defecto (Todos)
    const defaultOpt = document.createElement('option');
    defaultOpt.value = '';
    defaultOpt.textContent = '— Estado Sharepoint (Todos) —';
    selectSp.appendChild(defaultOpt);

    // 2. Opciones canónicas
    this.estadosSharepoint.forEach(est => {
      const opt = document.createElement('option');
      opt.value = est;
      opt.textContent = est;
      selectSp.appendChild(opt);
    });

    // 3. Restaurar valor previamente seleccionado si sigue existiendo
    if (previousValue && this.estadosSharepoint.includes(previousValue)) {
      selectSp.value = previousValue;
    }
  }
}
```

#### 3.2.3. Ciclo de Vida y Cambio de Módulo (`switchModule`)
En `switchModule(moduleName)`:
- Cuando el usuario navega a `'projects'`, si `this.estadosSharepoint` está vacío o el select contiene solo 1 opción, se dispara `this.loadEstados()`.
- En `loadInitialData()` se mantiene la invocación concurrente `Promise.all([this.loadLideres(), this.loadEstados(), this.loadKPIs()])`.

#### 3.2.4. Reactividad del Filtro
El evento `change` de `#filter-estado-sp` dispara inmediatamente `this.loadProjects()`, transmitiendo `estado_sp` en el query string de `/api/proyectos`.

---

## 4. MATRIZ DE CASOS DE PRUEBA PARA QA (TEST MATRIX)

### 4.1. Pruebas Backend e Integración de API

| ID Caso | Nombre del Caso de Prueba | Precondiciones / Datos de Entrada | Pasos de Ejecución | Resultado Esperado |
|---|---|---|---|---|
| **TC-EST-01** | Catálogo Canónico Completo en `/api/estados` | Usuario autenticado como `ADMIN` o `LTI`. BD contiene únicamente proyectos con `Estado = 'Atendido'`. | Ejecutar `GET /api/estados` con header de autorización. | HTTP 200 OK. `estados_sharepoint` contiene exactamente `["Generado", "En revision", "Atendido"]` en dicho orden. |
| **TC-EST-02** | Control RBAC en `/api/estados` | Usuario autenticado con rol `PM`. | Ejecutar `GET /api/estados` con token de PM. | HTTP 403 Forbidden. |
| **TC-EST-03** | Filtrado por Estado `'Generado'` | Existen proyectos en BD en diversos estados. | Ejecutar `GET /api/proyectos?estado_sp=Generado`. | HTTP 200 OK. Todos los registros devueltos tienen `Estado == "Generado"`. |
| **TC-EST-04** | Filtrado por Estado `'En revision'` | Existen proyectos en BD en diversos estados. | Ejecutar `GET /api/proyectos?estado_sp=En+revision`. | HTTP 200 OK. Todos los registros devueltos tienen `Estado == "En revision"`. |
| **TC-EST-05** | Filtrado por Estado `'Atendido'` | Existen proyectos en BD en diversos estados. | Ejecutar `GET /api/proyectos?estado_sp=Atendido`. | HTTP 200 OK. Todos los registros devueltos tienen `Estado == "Atendido"`. |
| **TC-EST-06** | Comodín Todos los Estados | Filtro `estado_sp` vacío o no enviado. | Ejecutar `GET /api/proyectos`. | HTTP 200 OK. Devuelve todos los proyectos sin restringir por estado. |
| **TC-EST-07** | Resiliencia ante Excepción de BD en SGA | Simular fallo o timeout en consulta a `CT_BACKLOG_OPERACIONES2`. | Invocar `get_estados_list()`. | Función no revienta; retorna `estados_sharepoint` completo y `estados_sga` como lista vacía `[]`. |

### 4.2. Pruebas Frontend E2E (Playwright)

| ID Caso | Nombre del Caso de Prueba | Pasos de Ejecución | Resultado Esperado |
|---|---|---|---|
| **TC-E2E-01** | Renderizado del Selector `#filter-estado-sp` | Iniciar sesión como `aaguilar` (ADMIN) o `jbarrera` (LTI). Visualizar módulo *Seguimiento Proyectos*. | `#filter-estado-sp` es visible y contiene 4 opciones: `— Estado Sharepoint (Todos) —`, `Generado`, `En revision`, `Atendido`. |
| **TC-E2E-02** | Filtrado Reactivo al Seleccionar `'Generado'` | Seleccionar `'Generado'` en `#filter-estado-sp`. | La tabla de proyectos se recarga mostrando solo proyectos con badge `Generado`. El badge de contador `#projects-count-badge` refleja el número exacto. |
| **TC-E2E-03** | Filtrado Reactivo al Seleccionar `'En revision'` | Seleccionar `'En revision'` en `#filter-estado-sp`. | La tabla de proyectos muestra solo proyectos en estado `'En revision'`. Si no hay registros, muestra el empty-state amigable. |
| **TC-E2E-04** | Filtrado Reactivo al Seleccionar `'Atendido'` | Seleccionar `'Atendido'` en `#filter-estado-sp`. | La tabla muestra proyectos atendidos con badges de éxito (`badge-success`). |
| **TC-E2E-05** | Fallback Defensivo ante Error de Red en `/api/estados` | Interceptar `/api/estados` con status 500 o abort. Recargar vista. | El selector `#filter-estado-sp` mantiene disponibles las 3 opciones canónicas gracias al fallback de frontend. |
| **TC-E2E-06** | Preservación de Filtro al Conmutar Módulos | Seleccionar `'Generado'`, navegar a *Búsqueda Directa* y volver a *Seguimiento Proyectos*. | El selector `#filter-estado-sp` conserva la opción `'Generado'` y la tabla permanece filtrada coherentemente. |

---

## 5. PLAN DE IMPLEMENTACIÓN PARA SUBAGENTE CODER

1. **Backend (`backend/db.py`):**
   - Incorporar la constante `CANONICAL_ESTADOS_SHAREPOINT = ["Generado", "En revision", "Atendido"]`.
   - Modificar `get_estados_list()` para utilizar `CANONICAL_ESTADOS_SHAREPOINT` como valor de `estados_sharepoint`, manteniendo la consulta segura a `dbo.CT_BACKLOG_OPERACIONES2` para `estados_sga` con bloque `try/except`.
2. **Frontend HTML (`frontend/index.html`):**
   - Actualizar `#filter-estado-sp` para pre-renderizar las opciones canónicas estáticas.
3. **Frontend JS (`frontend/js/app.js`):**
   - Definir `const CANONICAL_ESTADOS_SHAREPOINT = ['Generado', 'En revision', 'Atendido'];` en el ámbito del módulo.
   - Refactorizar `loadEstados()` para incluir fallback defensivo y preservación de selección.
4. **Documentación (`README.md`):**
   - Registrar la especificación en la sección de SPECS y listar la característica del catálogo canónico de estados.
5. **Testing (`tests/`):**
   - Ejecutar la suite completa de pruebas unitarias, de integración y Playwright E2E.
