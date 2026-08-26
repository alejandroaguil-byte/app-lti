# ESPECIFICACIÓN TÉCNICA Y FUNCIONAL (SPECS)
## Módulo: "Solicitud LTI" — Portal de Seguimiento Líderes TI (`app-lti`)

- **Documento:** SPECS-LTI-MOD-004
- **Versión:** 1.3.0
- **Fecha:** 2026-08-26
- **Autor:** Subagente 1 (Planificador & Arquitecto de Software)
- **Destinatario:** Subagente 2 (Codificador & Implementador)
- **Ubicación del Proyecto:** `/home/bobbasystem/Desarrollos/app-lti`

---

## CONTROL DE VERSIONES Y REGISTRO DE CAMBIOS

| Versión | Fecha | Autor | Descripción del Cambio |
|---|---|---|---|
| **1.0.0** | 2026-08-25 | Subagente 1 | Versión inicial de especificación del módulo "Solicitud LTI" (Autocompletado SGA, anti-duplicados, persistencia MSSQL). |
| **1.1.0** | 2026-08-25 | Subagente 1 | **Actualización de Requerimiento de Negocio:** El campo **Estado** al solicitar debe quedar obligatoriamente fijado en `'Generado'`, con el control visual bloqueado (`disabled`) en frontend sin posibilidad de modificación por el usuario, y forzado de forma inmutable en el Backend. |
| **1.2.0** | 2026-08-25 | Subagente 1 | **Actualización Integral de Flujo y Detalle Inteligente:**<br>1. **Autocompletado de Detalle:** Prellenado estructurado de Solots asociados con `'Liray'` en `DESCR_OTP`.<br>2. **Campo Tipo de Servicio Oculto y Fijo:** Fijado en `'Otros'`, bloqueado y **oculto (`hidden`)**.<br>3. **Nuevos Helpers & Endpoints:** `/api/solicitudes/solots-liray` y enriquecimiento de `/api/solicitudes/autocomplete-proyectos`. |
| **1.3.0** | 2026-08-26 | Subagente 1 | **Reorganización del Formulario y Desacople de Asignación Inicial de LT:**<br>1. **Ocultar/Eliminar Campo "LT Asignado":** El solicitante no asigna Líder Técnico en el formulario de creación inicial. El proyecto se persiste con `LT_Asignado = NULL` (o en blanco), ingresando directamente como registro **Pendiente de Asignación** para su posterior distribución operativa en el módulo *Seguimiento Proyectos*.<br>2. **Rebalanceo de Layout UI (Grid 2 Columnas):** Fila 1: N° Proyecto y Cliente; Fila 2: Fecha de Solicitud y Estado (`🔒 Fijo: Generado`); Fila 3: Detalle (ancho completo); Fila 4: Acciones.<br>3. **Estandarización Tipográfica:** Alineación con las variables globales del Design System `--font-sans` y tipografía unificada para inputs, labels y textareas.<br>4. **Ajuste de Validaciones Backend & Frontend:** `lt_asignado` pasa a ser opcional en `SolicitudCreacionRequest` y se omite en la validación de campos obligatorios en el cliente. |

---

## 1. RESUMEN EJECUTIVO Y OBJETIVOS

El proyecto `app-lti` es una plataforma empresarial moderna (FastAPI + Microsoft SQL Server + Vanilla JS/CSS3) diseñada para el control y auditoría 360° de proyectos de telecomunicaciones, Solots de operaciones (`dbo.CT_BACKLOG_OPERACIONES2`), Tickets de Incidentes HPSM (`dbo.registrosRF_SD_SM`) y RFCs (`dbo.registrosSM_RFC`).

### Objetivo Principal del Módulo (v1.3.0):
Implementar y afinar el módulo **"Solicitud LTI"** accesible desde la navegación superior, que permita a cualquier usuario autorizado ingresar nuevas solicitudes de proyectos en `dbo.Proyectos` sin requerir la preasignación de un Líder Técnico en esta etapa temprana:

1. **Ingreso Limpio y Desatendido:**
   - El formulario no solicita Líder Técnico; el registro se genera con `LT_Asignado = NULL` para alimentar automáticamente la bandeja de **"Pendientes de Asignar"** en el módulo de Seguimiento.
2. **Autocompletado reactivo e inteligente:**
   - **N° de Proyecto y Cliente:** Búsqueda rápida sobre el backlog SGA (`dbo.CT_BACKLOG_OPERACIONES2`).
   - **Detalle del Requerimiento:** Prellenado automático y estructurado con todos los Solots asociados que contengan `'Liray'` en la descripción (`DESCR_OTP`), detallando Solot, Producto, Servicio, N° de Servicio y Descripción.
   - **Flexibilidad total:** Si el proyecto es manual o no tiene Solots Liray, se ingresa libremente.
3. **Campos Fijos e Inmutables:**
   - **Estado:** Siempre fijado en `'Generado'`, visualmente bloqueado (`disabled`) en UI e impuesto de forma inmutable en el backend.
   - **Tipo de Servicio:** Siempre fijado en `'Otros'`, bloqueado y **oculto en la UI** (`<input type="hidden">`).
4. **Validación estricta de duplicados** en `dbo.Proyectos` (409 Conflict con sugerencia de complementar Detalle).
5. **Tipografía Uniforme & UX/UI Coherente:**
   - Tipografía estandarizada basada en `'Roboto'`, `'Plus Jakarta Sans'` y fuentes del sistema.
   - Soporte nativo para modo claro y oscuro, retroalimentación reactiva de carga y toasts informativos.

---

## 2. ARQUITECTURA DE DATOS & OPERACIONES SQL

### 2.1. Estructura de la Tabla `dbo.Proyectos` (Destino del `INSERT`)

| Nombre Columna | Tipo de Dato MSSQL | Nullable | Identity | Mapeo y Comportamiento en v1.3.0 |
|---|---|---|---|---|
| `ID` | `numeric(18,0)` | **NO** | **NO** (Manual) | Clave Primaria. Calculada de forma segura como `ISNULL(MAX(ID), 0) + 1`. |
| `Cliente` | `varchar(100)` | SÍ | NO | Nombre o Razón Social del cliente. Requerido. |
| `Numero_Proyecto` | `varchar(50)` | SÍ | NO | Identificador de proyecto. Normalizado con formato estándar `000...`. Requerido. |
| `LT_Asignado` | `varchar(50)` | SÍ | NO | **Sin Asignar al Crear (`NULL`):** No se captura en el formulario de creación. Queda en `NULL` para ingresar como pendiente de asignación. |
| `Estado` | `nvarchar(MAX)` | SÍ | NO | **Inmutable en Creación:** Se fija siempre en `'Generado'`. |
| `Detalle` | `nvarchar(MAX)` | SÍ | NO | Descripción técnica. Autocompletado con Solots Liray o manual. Requerido. |
| `Tipo_Servicio` | `varchar(30)` | SÍ | NO | **Fijo y Oculto:** Se fija siempre en `'Otros'`. |
| `Comentario` | `nvarchar(MAX)` | SÍ | NO | Inicialmente `NULL`. |
| `Creado` | `datetime` | SÍ | NO | Timestamp de fecha/hora de solicitud (`YYYY-MM-DD HH:MM:SS`). |
| `Solicitante` | `varchar(50)` | SÍ | NO | Nombre completo del usuario autenticado que ingresa la solicitud. |

> **Cálculo Seguro de PK `ID`:**
> ```sql
> SELECT ISNULL(MAX(ID), 0) + 1 AS next_id FROM dbo.Proyectos WITH (UPDLOCK, HOLDLOCK);
> ```

---

## 3. ESPECIFICACIÓN FUNCIONAL DEL FORMULARIO (v1.3.0)

### 3.1. Matriz de Campos de la UI

| Campo | Tipo Control | Requerido | Visibilidad | Valor por Defecto | Reglas & Comportamiento v1.3.0 |
|---|---|---|---|---|---|
| **N° de Proyecto** | `input[type="text"]` con Autocomplete | **SÍ** | **Visible** | Vacío | • Normalización automática (con o sin ceros a la izquierda).<br>• Debounce 250ms con búsqueda en SGA.<br>• Al seleccionar, prellena **Cliente** y **Detalle** (con Solots Liray si existen). |
| **Cliente** | `input[type="text"]` | **SÍ** | **Visible** | Vacío | • Razón social del cliente.<br>• Prellenado desde SGA o ingreso manual. |
| **Fecha de Solicitud** | `input[type="date"]` | **SÍ** | **Visible** | Fecha actual (`YYYY-MM-DD`) | • Fecha de registro del requerimiento. Obligatoria. |
| **Estado** | `select` bloqueado (`disabled`) | **SÍ (Fijo)** | **Visible (Bloqueado)** | `'Generado'` | • **Inmutable:** No modificable en creación.<br>• Atributo `disabled` activo con opción única `Generado` y badge `🔒 Fijo`. |
| **LT Asignado** | *Eliminado de la UI* | **NO** | **OCULTO / NO PRESENTE** | `NULL` | • **Desacoplado de Creación:** El solicitante no asigna líder en esta etapa.<br>• Se envía `null` al backend y se almacena `NULL` en base de datos. |
| **Tipo de Servicio** | `input[type="hidden"]` | **SÍ (Fijo)** | **OCULTO (`hidden`)** | `'Otros'` | • Se envía transparentemente en el payload como `'Otros'`. |
| **Detalle del Requerimiento** | `textarea` (filas: 6) | **SÍ** | **Visible** | Vacío o Solots Liray | • Autocompleta Solots Liray estructurados si existen en SGA.<br>• Totalmente editable por el solicitante. |

---

### 3.2. Formato de Solots Liray en el Detalle

```text
SOLOTS ASOCIADOS (LIRAY):
==================================================
[1] Solot: 17636212
    • Producto: Monitoreo Proactivo
    • Servicio: Monitoreo Proactivo
    • N° Servicio: 02-25-0010465061
    • Descripción: Instalacion | Fibra Optica 1 Gbps Carrier Class(1:1) _ | AVDA LIRAY SN     | COLINA | CHACABUCO | RM | IP Data MPLS
-----------------------------------
[2] Solot: 17636211
    • Producto: VRF Datos Adicional
    • Servicio: Fibra Optica 1 Gbps VRF Prueba
    • N° Servicio: 02-26-0010465054
    • Descripción: Instalacion | Fibra Optica 1 Gbps VRF Prueba | AVDA LIRAY SN     | COLINA | CHACABUCO | RM | VRF Datos Adicional
```

---

## 4. ESPECIFICACIÓN DE ENDPOINTS BACKEND (FastAPI)

### 4.1. `POST /api/solicitudes/crear`
Crea la solicitud en `dbo.Proyectos` sin requerir `lt_asignado` (persistiendo `NULL`).

- **Método HTTP:** `POST`
- **Ruta:** `/api/solicitudes/crear`
- **Autenticación:** Bearer Token JWT (`Depends(get_current_user)`)
- **Pydantic Schema:**
```python
class SolicitudCreacionRequest(BaseModel):
    cliente: str
    numero_proyecto: str
    lt_asignado: Optional[str] = None  # Opcional, por defecto None
    estado: Optional[str] = "Generado"  # Backend fuerza incondicionalmente 'Generado'
    fecha_solicitud: str  # Formato YYYY-MM-DD
    detalle: str
    tipo_servicio: Optional[str] = "Otros"  # Backend fuerza 'Otros'
```

- **Controlador en `backend/main.py`:**
```python
@app.post("/api/solicitudes/crear", status_code=status.HTTP_201_CREATED)
def crear_solicitud(
    req: SolicitudCreacionRequest,
    current_user: dict = Depends(get_current_user)
):
    cliente = (req.cliente or "").strip()
    numero_proyecto = (req.numero_proyecto or "").strip()
    lt_asignado = req.lt_asignado.strip() if req.lt_asignado and req.lt_asignado.strip() else None
    estado = "Generado"  # Regla Inmutable
    fecha_solicitud = (req.fecha_solicitud or "").strip()
    detalle = (req.detalle or "").strip()
    tipo_servicio = "Otros"  # Regla Fija

    # Validación: Solo cliente, numero_proyecto, fecha_solicitud y detalle son obligatorios
    if not cliente or not numero_proyecto or not fecha_solicitud or not detalle:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los campos N° de Proyecto, Cliente, Fecha de Solicitud y Detalle son obligatorios"
        )

    solicitante = current_user.get("nombre_completo") or current_user.get("username")
    result = create_solicitud_lti(
        cliente=cliente,
        numero_proyecto=numero_proyecto,
        lt_asignado=lt_asignado,  # Pasa como None si no fue provisto
        estado=estado,
        fecha_solicitud=fecha_solicitud,
        detalle=detalle,
        solicitante=solicitante,
        tipo_servicio=tipo_servicio
    )
    if not result.get("success"):
        if result.get("error") == "duplicate":
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "detail": "El proyecto ya se encuentra registrado",
                    "error": "duplicate",
                    "existing": result.get("existing")
                }
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Error al crear la solicitud")
        )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "message": "Solicitud LTI creada exitosamente (Pendiente de Asignación)",
            "data": result.get("data")
        }
    )
```

- **Función en `backend/db.py`:**
```python
def create_solicitud_lti(
    cliente: str, 
    numero_proyecto: str, 
    lt_asignado: Optional[str] = None, 
    estado: str = "Generado", 
    fecha_solicitud: str = None, 
    detalle: str = "", 
    solicitante: Optional[str] = None, 
    tipo_servicio: Optional[str] = "Otros"
) -> dict:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Verificar duplicados
            num_clean = str(numero_proyecto).strip()
            num_without_zeros = num_clean.lstrip('0')
            num_with_zeros = f"000{num_without_zeros}" if num_without_zeros else num_clean

            cursor.execute("""
                SELECT TOP 1 ID, Cliente, Numero_Proyecto, LT_Asignado, Estado, Detalle, Comentario, Tipo_Servicio, Creado, Solicitante
                FROM dbo.Proyectos WITH (NOLOCK)
                WHERE LTRIM(RTRIM(Numero_Proyecto)) = %s 
                   OR LTRIM(RTRIM(Numero_Proyecto)) = %s
                   OR LTRIM(RTRIM(Numero_Proyecto)) = %s
            """, (num_clean, num_without_zeros, num_with_zeros))
            existing = cursor.fetchone()
            if existing:
                return {
                    "success": False,
                    "error": "duplicate",
                    "existing": serialize_row(existing)
                }

            # 2. Calcular siguiente ID
            cursor.execute("SELECT ISNULL(MAX(ID), 0) + 1 AS next_id FROM dbo.Proyectos WITH (UPDLOCK, HOLDLOCK)")
            next_id = int(cursor.fetchone()['next_id'])

            # 3. Formatear fecha
            try:
                now = datetime.datetime.now()
                parsed_date = datetime.datetime.strptime(str(fecha_solicitud)[:10], '%Y-%m-%d')
                dt_to_insert = parsed_date.replace(hour=now.hour, minute=now.minute, second=now.second)
            except Exception:
                dt_to_insert = datetime.datetime.now()

            formatted_num = format_numero_proyecto(num_clean)

            # 4. Insertar en dbo.Proyectos con LT_Asignado = NULL si no se envía
            insert_sql = """
                INSERT INTO dbo.Proyectos (
                    ID, Cliente, Numero_Proyecto, LT_Asignado, Estado, Detalle, Tipo_Servicio, Creado, Solicitante
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_sql, (
                next_id,
                cliente.strip()[:100],
                formatted_num[:50],
                (lt_asignado.strip()[:50] if lt_asignado and lt_asignado.strip() else None),
                'Generado',
                detalle.strip(),
                'Otros',
                dt_to_insert,
                (solicitante.strip() if solicitante else None)[:50] if solicitante else None
            ))
            conn.commit()

            cursor.execute("SELECT * FROM dbo.Proyectos WHERE ID = %s", (next_id,))
            created_row = cursor.fetchone()
            return {
                "success": True,
                "data": serialize_row(created_row)
            }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "error": str(e)}
    finally:
        conn.close()
```

---

## 5. ESPECIFICACIÓN FRONTEND (HTML / CSS / JS)

### 5.1. Estructura HTML Actualizada (`frontend/index.html`)

```html
<!-- MÓDULO 4: SOLICITUD LTI -->
<div id="module-solicitud-lti-container" class="module-container" style="display: none;">
  <section class="solicitud-lti-section">
    <!-- Header Banner -->
    <div class="drilldown-header" style="margin-bottom: 1.5rem;">
      <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 1rem;">
        <div>
          <h2 style="font-size: 1.35rem; font-weight: 700; margin-bottom: 0.35rem; display: flex; align-items: center; gap: 0.5rem;">
            📝 Nueva Solicitud LTI
            <span class="badge badge-info" style="font-size: 0.72rem; vertical-align: middle;">dbo.Proyectos</span>
          </h2>
          <p style="color: var(--text-secondary); font-size: 0.88rem;">
            Registra una nueva solicitud de proyecto técnico. Escribe el N° de proyecto para autocompletar desde SGA o ingresa los datos manualmente. La solicitud ingresará pendiente de asignación de Líder TI.
          </p>
        </div>
        <div style="display: flex; align-items: center; gap: 0.75rem;">
          <span class="badge badge-success" style="padding: 0.35rem 0.75rem; font-size: 0.8rem;">
            🟢 Base de Datos Conectada
          </span>
        </div>
      </div>
    </div>

    <!-- Banner de Alerta / Duplicados -->
    <div id="solicitud-duplicate-alert" class="solicitud-alert-banner alert-warning" style="display: none;">
      <div class="alert-icon">⚠️</div>
      <div class="alert-content">
        <div class="alert-title" id="duplicate-alert-title">El N° de proyecto ya existe en el sistema</div>
        <div class="alert-description" id="duplicate-alert-desc">
          Este proyecto ya fue ingresado previamente. Puedes complementar el campo "Detalle" o consultar su estado en Seguimiento.
        </div>
        <div class="alert-actions" style="margin-top: 0.6rem;">
          <button type="button" id="btn-view-duplicate-project" class="btn btn-secondary btn-sm">
            🔍 Ver Proyecto en Seguimiento
          </button>
        </div>
      </div>
    </div>

    <!-- Banner de Error General -->
    <div id="solicitud-error-alert" class="solicitud-alert-banner alert-danger" style="display: none;">
      <div class="alert-icon">❌</div>
      <div class="alert-content">
        <div class="alert-title">No se pudo guardar la solicitud</div>
        <div class="alert-description" id="solicitud-error-desc">Verifica que todos los campos requeridos estén completos.</div>
      </div>
    </div>

    <!-- Tarjeta Principal del Formulario -->
    <div class="solicitud-card">
      <div class="solicitud-card-header">
        <div class="ticket-card-title">
          <span>📋 Formulario de Registro de Solicitud</span>
        </div>
        <span class="badge badge-neutral" style="font-size: 0.75rem;">Todos los campos con (*) son obligatorios</span>
      </div>

      <form id="solicitud-lti-form" onsubmit="event.preventDefault();">
        <!-- Campo Oculto y Fijo: Tipo de Servicio -->
        <input type="hidden" id="solicitud-tipo-servicio" value="Otros">

        <div class="solicitud-form-grid">
          
          <!-- Fila 1: N° Proyecto (con autocomplete) y Cliente -->
          <div class="form-group autocomplete-container">
            <label class="form-label" for="solicitud-nro-proyecto">
              N° de Proyecto <span class="form-required">*</span>
            </label>
            <div class="input-with-icon">
              <span class="input-icon">🔢</span>
              <input 
                type="text" 
                id="solicitud-nro-proyecto" 
                class="form-input" 
                placeholder="Ej: 0001614653 o 1614653" 
                required 
                autocomplete="off"
              >
              <span id="autocomplete-spinner" class="spinner-inline" style="display: none; position: absolute; right: 12px; top: 12px;"></span>
            </div>
            <!-- Dropdown flotante de sugerencias -->
            <div id="solicitud-autocomplete-dropdown" class="autocomplete-dropdown" style="display: none;"></div>
            <span class="form-help-text">Escribe para autocompletar cliente y solots Liray desde SGA.</span>
          </div>

          <div class="form-group">
            <label class="form-label" for="solicitud-cliente">
              Cliente <span class="form-required">*</span>
            </label>
            <div class="input-with-icon">
              <span class="input-icon">🏢</span>
              <input 
                type="text" 
                id="solicitud-cliente" 
                class="form-input" 
                placeholder="Razón Social o Nombre del Cliente" 
                required
              >
            </div>
            <span class="form-help-text">Nombre de la empresa o cliente asociado.</span>
          </div>

          <!-- Fila 2: Fecha de Solicitud y Estado Fijo -->
          <div class="form-group">
            <label class="form-label" for="solicitud-fecha">
              Fecha de Solicitud <span class="form-required">*</span>
            </label>
            <div class="input-with-icon">
              <span class="input-icon">📅</span>
              <input 
                type="date" 
                id="solicitud-fecha" 
                class="form-input" 
                required
              >
            </div>
            <span class="form-help-text">Fecha en que se recibe o registra la solicitud.</span>
          </div>

          <div class="form-group">
            <label class="form-label" for="solicitud-estado">
              Estado <span class="form-required">*</span>
              <span class="badge-locked">🔒 Fijo</span>
            </label>
            <div class="input-with-icon">
              <span class="input-icon">📊</span>
              <select id="solicitud-estado" class="form-select" disabled title="El estado inicial de toda solicitud queda fijado automáticamente en 'Generado'">
                <option value="Generado" selected>Generado</option>
              </select>
            </div>
            <span class="form-help-text input-help-text">Estado inicial fijo: 'Generado' (no modificable en la creación).</span>
          </div>

          <!-- Fila 3: Detalle (Ancho Completo) con soporte Liray -->
          <div class="form-group full-width">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
              <label class="form-label" for="solicitud-detalle" style="margin-bottom: 0;">
                Detalle del Requerimiento / Proyecto <span class="form-required">*</span>
              </label>
              <span id="detalle-solots-badge" class="badge badge-info" style="display: none; font-size: 0.72rem;">
                ⚡ Solots Liray detectados
              </span>
            </div>
            <textarea 
              id="solicitud-detalle" 
              class="form-textarea" 
              rows="6" 
              placeholder="Se autocompletará con los Solots Liray si existen en SGA. También puedes redactar o complementar los requerimientos técnicos..." 
              required
            ></textarea>
            <span class="form-help-text">Descripción técnica del proyecto. Puedes editar y agregar notas libremente.</span>
          </div>

        </div>

        <!-- Botones de Acción -->
        <div class="solicitud-form-actions">
          <button type="button" id="btn-submit-solicitud" class="btn btn-primary btn-execute">
            <span id="solicitud-spinner" class="spinner-inline" style="display: none;"></span>
            <span id="solicitud-btn-icon">🚀</span>
            <span id="solicitud-btn-text">Solicitar</span>
          </button>
          <button type="button" id="btn-reset-solicitud" class="btn btn-secondary">
            <span>🧹 Limpiar Formulario</span>
          </button>
        </div>
      </form>
    </div>
  </section>
</div>
```

---

### 5.2. Lógica JavaScript (`frontend/js/app.js`)

```javascript
// Validación y Envío en submitSolicitudForm
async submitSolicitudForm() {
  const nroProyectoEl = document.getElementById('solicitud-nro-proyecto');
  const clienteEl = document.getElementById('solicitud-cliente');
  const fechaEl = document.getElementById('solicitud-fecha');
  const detalleEl = document.getElementById('solicitud-detalle');
  const errorBanner = document.getElementById('solicitud-error-alert');
  const errorDesc = document.getElementById('solicitud-error-desc');
  const dupBanner = document.getElementById('solicitud-duplicate-alert');

  if (dupBanner) dupBanner.style.display = 'none';
  if (errorBanner) errorBanner.style.display = 'none';

  // Remover marcas de error previas
  [nroProyectoEl, clienteEl, fechaEl, detalleEl].forEach(el => {
    if (el) el.classList.remove('is-invalid');
  });

  const nroProyecto = (nroProyectoEl?.value || '').trim();
  const cliente = (clienteEl?.value || '').trim();
  const fecha = (fechaEl?.value || '').trim();
  const detalle = (detalleEl?.value || '').trim();

  let hasErrors = false;
  if (!nroProyecto) { nroProyectoEl?.classList.add('is-invalid'); hasErrors = true; }
  if (!cliente) { clienteEl?.classList.add('is-invalid'); hasErrors = true; }
  if (!fecha) { fechaEl?.classList.add('is-invalid'); hasErrors = true; }
  if (!detalle) { detalleEl?.classList.add('is-invalid'); hasErrors = true; }

  if (hasErrors) {
    if (errorBanner) {
      errorDesc.textContent = 'Los campos N° de Proyecto, Cliente, Fecha de Solicitud y Detalle son obligatorios.';
      errorBanner.style.display = 'flex';
    }
    return;
  }

  this.setSolicitudSubmitting(true);

  try {
    const payload = {
      cliente,
      numero_proyecto: nroProyecto,
      lt_asignado: null, // No se asigna líder en fase inicial
      estado: 'Generado',
      fecha_solicitud: fecha,
      detalle,
      tipo_servicio: 'Otros'
    };

    const res = await Auth.fetchWithAuth('/api/solicitudes/crear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.status === 201) {
      const respData = await res.json();
      this.openSolicitudSuccessModal(respData.data);
      this.resetSolicitudForm();
    } else if (res.status === 409) {
      const dupData = await res.json();
      this.handleDuplicateSolicitud(dupData);
    } else {
      const errData = await res.json().catch(() => ({}));
      if (errorBanner) {
        errorDesc.textContent = errData.detail || 'Ocurrió un error al procesar la solicitud.';
        errorBanner.style.display = 'flex';
      }
    }
  } catch (e) {
    if (errorBanner) {
      errorDesc.textContent = `Error de red o conexión: ${e.message}`;
      errorBanner.style.display = 'flex';
    }
  } finally {
    this.setSolicitudSubmitting(false);
  }
}
```

---

## 6. CRITERIOS DE ACEPTACIÓN & CASOS DE PRUEBA (QA)

| ID | Caso de Prueba | Procedimiento | Resultado Esperado |
|---|---|---|---|
| **CP-01** | Ausencia del campo LT Asignado en UI | 1. Iniciar sesión y navegar a "📝 Solicitud LTI".<br>2. Inspeccionar los campos visuales. | El selector `#solicitud-lt-asignado` **no existe en la UI visible**. La cuadrícula muestra de forma balanceada N° Proyecto y Cliente en fila 1; Fecha de Solicitud y Estado en fila 2. |
| **CP-02** | Campo Estado Bloqueado e Inmutable | Inspeccionar `#solicitud-estado`. | Está en `Generado`, disabled, con badge `🔒 Fijo` y cursor `not-allowed`. |
| **CP-03** | Autocompletado de Proyecto y Solots Liray | Escribir `1614653` y seleccionar coincidencia. | Autocompleta N° Proyecto, Cliente y Detalle con los 2 Solots Liray. Badge `⚡ Solots Liray detectados` visible. |
| **CP-04** | Validación de Campos Obligatorios | Presionar "Solicitar" con el formulario vacío. | Muestra banner de error y marca en rojo únicamente N° Proyecto, Cliente, Fecha y Detalle. No hay error referente a LT Asignado. |
| **CP-05** | Creación Exitosa sin LT Asignado | Completar formulario y enviar. | HTTP 201 Created. Registro insertado en MSSQL con `LT_Asignado = NULL`, `Estado = 'Generado'`, `Tipo_Servicio = 'Otros'`. Se abre modal de éxito. |
| **CP-06** | Proyecto Creado Aparece como "Pendiente de Asignar" | Ir a Seguimiento Proyectos y filtrar por "Sin asignar" o pulsar tarjeta KPI "Pendientes de Asignar". | El nuevo proyecto aparece listado en la tabla con celda de LT Asignado vacía o `-` y badge de estado `'Generado'`. |
| **CP-07** | Control Anti-Duplicados (409 Conflict) | Re-ingresar un proyecto ya existente. | Retorna 409 y despliega el banner de advertencia con botón para ver proyecto original. |
| **CP-08** | Estandarización Tipográfica | Inspeccionar con DevTools en tema claro y oscuro. | Todos los textos, labels, inputs y badges utilizan la familia de fuentes estandarizada y mantienen legibilidad óptima. |

---

*Fin del Documento de Especificaciones Técnicas (SPECS-LTI-MOD-004 v1.3.0)*
