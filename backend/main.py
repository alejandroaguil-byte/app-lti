import os
import re
import uuid
import base64
import logging
import asyncio
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, status, Query, UploadFile, File, Form, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, HTMLResponse
from pydantic import BaseModel

logger = logging.getLogger("main")

from .config import BASE_DIR, CORS_ORIGINS
from . import config as app_config
from .auth import (
    get_current_user,
    require_admin,
    require_lti_or_admin,
    require_non_pm,
    ve_todos_los_proyectos,
    resolver_lt_scope,
    proyecto_en_alcance
)
from .db import (
    get_user_by_username,
    get_usuario_by_username,
    get_all_usuarios,
    get_usuario_by_id,
    update_usuario,
    toggle_user_status,
    delete_usuario,
    get_lideres_list,
    get_estados_list,
    CANONICAL_ESTADOS_SHAREPOINT,
    normalizar_estado_proyecto,
    resolver_estado_por_asignacion,
    get_proyectos,
    get_proyecto_by_id,
    get_solots_by_proyecto,
    get_tickets_by_proyecto,
    get_rfcs_by_proyecto,
    get_dashboard_kpis,
    kpis_vacios,
    procesar_alertas_sla,
    search_direct_tables,
    get_db_connection,
    get_solicitud_catalogos,
    get_solots_liray_by_proyecto,
    format_solots_liray_text,
    search_backlog_proyectos_autocomplete,
    check_proyecto_exists,
    create_solicitud_lti,
    update_proyecto,
    init_bitacora_tables,
    normalizar_numero_asociado,
    get_asociaciones_proyecto,
    create_asociacion,
    delete_asociacion,
    create_bitacora_entry,
    get_bitacora_by_proyecto,
    get_bitacora_entry,
    create_adjunto,
    get_adjunto,
    get_adjuntos_dir,
    adjunto_path,
    remove_adjunto_files,
    assign_lti_from_backlog,
    delete_proyecto,
    get_diagnostico_proyecto,
    get_ficha_ejecutiva_data,
    generar_ficha_ejecutiva_html,
    get_timeline_proyecto,
    get_alertas_tempranas_sla,
    get_proyectos_pendientes_recordatorio,
    registrar_recordatorio_enviado,
    resolve_user_email,
    is_valid_project_number
)
from .seed_users import seed_default_users
from .ticket_automation import stream_ticket_creation
from .email_service import (
    send_ticket_notification_email,
    send_solicitud_creada_email,
    send_solicitud_recordatorio_email,
    send_solicitud_asignada_email,
    is_email_redirect_active,
    COORDINADORES_LTI_EMAILS
)

from contextlib import asynccontextmanager

_reminder_task: Optional[asyncio.Task] = None
REMINDER_CHECK_SECONDS = int(os.getenv("REMINDER_CHECK_SECONDS", "600"))
REMINDER_INTERVAL_HOURS = int(os.getenv("REMINDER_INTERVAL_HOURS", "6"))
REMINDER_INTERVAL_MINUTES = REMINDER_INTERVAL_HOURS * 60


def run_reminder_cycle() -> int:
    """Ejecuta un ciclo del monitor de 6 horas. Retorna la cantidad de recordatorios procesados.

    Con EMAIL_REDIRECT_TO activo (desarrollo) no procesa nada: la BD es compartida con producción
    y marcar recordatorios aquí impediría que producción los envíe a los coordinadores.
    """
    if is_email_redirect_active():
        logger.debug("[SCHEDULER] EMAIL_REDIRECT_TO activo: ciclo de recordatorios omitido (lo atiende producción).")
        return 0

    logger.debug("[SCHEDULER] Evaluando solicitudes LTI sin asignar pendientes de recordatorio...")
    pendientes = get_proyectos_pendientes_recordatorio(intervalo_minutos=REMINDER_INTERVAL_MINUTES)
    validos = [
        p for p in pendientes 
        if is_valid_project_number(
            p.get("Numero_Proyecto"), 
            p.get("Cliente"), 
            p.get("Tipo_Servicio"),
            p.get("Solicitante")
        )
    ]
    if not validos:
        logger.debug("[SCHEDULER] No hay solicitudes pendientes de recordatorio en este ciclo.")
        return 0

    logger.info(f"[SCHEDULER] Se encontraron {len(validos)} solicitudes válidas pendientes para recordatorio.")
    send_solicitud_recordatorio_email(validos, horas_transcurridas=REMINDER_INTERVAL_HOURS)
    for p in validos:
        registrar_recordatorio_enviado(p["ID"])
        logger.info(f"[SCHEDULER] Recordatorio marcado en BD para proyecto ID {p['ID']} (N° {p.get('Numero_Proyecto')}).")
    return len(validos)


async def reminder_scheduler_loop():
    """Loop asíncrono para verificar y despachar recordatorios periódicos cada 6 horas."""
    logger.info(f"[SCHEDULER] Loop de recordatorios de Solicitud LTI activo (check cada {REMINDER_CHECK_SECONDS}s, umbral {REMINDER_INTERVAL_HOURS}h).")
    while True:
        try:
            await asyncio.sleep(REMINDER_CHECK_SECONDS)
            run_reminder_cycle()
        except asyncio.CancelledError:
            logger.info("[SCHEDULER] Tarea de recordatorios cancelada limpiamente.")
            break
        except Exception as e:
            logger.error(f"[SCHEDULER] Error inesperado en el ciclo de recordatorios: {e}", exc_info=True)


def notificar_creacion_solicitud_bg(proyecto_data: dict, solicitante_user: Optional[dict] = None):
    """Tarea en segundo plano para notificar a los coordinadores al crear una nueva solicitud LTI."""
    try:
        solicitante_nombre = None
        if solicitante_user:
            solicitante_nombre = solicitante_user.get("nombre_completo") or solicitante_user.get("username")
        send_solicitud_creada_email(proyecto_data, solicitante_nombre=solicitante_nombre)
    except Exception as e:
        logger.error(f"Error en tarea en segundo plano notificar_creacion_solicitud_bg: {e}", exc_info=True)


def notificar_asignacion_lti_bg(
    proyecto_data: dict,
    prev_lt: Optional[str] = None,
    new_lt: Optional[str] = None,
    actor_user: Optional[dict] = None
):
    """Tarea en segundo plano para notificar al PM y al LTI al producirse la asignación."""
    try:
        lt_val = new_lt or proyecto_data.get("LT_Asignado")
        pm_ident = proyecto_data.get("Solicitante")
        pm_email = resolve_user_email(pm_ident)
        lt_email = resolve_user_email(lt_val)
        send_solicitud_asignada_email(
            proyecto_data=proyecto_data,
            pm_email=pm_email,
            lti_email=lt_email,
            lt_nombre=lt_val
        )
    except Exception as e:
        logger.error(f"Error en tarea en segundo plano notificar_asignacion_lti_bg: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _reminder_task
    try:
        seed_default_users()
    except Exception as e:
        print(f"[ERROR] Error al inicializar tablas y usuarios: {e}")
    try:
        init_bitacora_tables()
    except Exception as e:
        logger.error(f"Error al inicializar las tablas de bitácora y adjuntos: {e}")

    # Iniciar worker de recordatorios en background
    _reminder_task = asyncio.create_task(reminder_scheduler_loop())
    logger.info("[SCHEDULER] Worker de recordatorios de Solicitud LTI iniciado en lifespan.")

    yield

    # Shutdown: cancelación limpia del worker
    if _reminder_task and not _reminder_task.done():
        logger.info("[SCHEDULER] Cancelando worker de recordatorios...")
        _reminder_task.cancel()
        try:
            await _reminder_task
        except asyncio.CancelledError:
            logger.info("[SCHEDULER] Worker de recordatorios finalizado correctamente.")

# Desactivar documentación interactiva en producción (Observación 6)
_is_dev = os.getenv("ENV", "").lower() in ("dev", "development") or os.getenv("APP_ENV", "").lower() in ("dev", "development")
app = FastAPI(
    title="App LTI - Seguimiento Líderes TI",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None
)

# Enable CORS with credentials for SSO Portal de Acceso and local environments
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response

BITACORA_TEXTO_MAX = 20000

# Schemas
class TicketCreationRequest(BaseModel):
    contacto: str = "ALEJANDRO JAVIER AGUILAR MORALES"
    titulo: str
    descripcion: str
    area: str = "Proyectos"
    subarea: str = "Apoyo habilitacion cliente"
    detalle: str = "Apoyo habilitacion cliente"
    grupo: str = "Lideres Tecnicos"
    impacto: Optional[str] = "3 - Menor (Existen WorkAround)"
    urgencia: Optional[str] = "3 - Media (Resolución a mediano plazo)"
    usuario_peticion: Optional[str] = "Alejandro.Aguilar"
    headless: Optional[bool] = True

class SolicitudCreacionRequest(BaseModel):
    cliente: str
    numero_proyecto: str
    lt_asignado: Optional[str] = None
    estado: Optional[str] = "Generado"
    fecha_solicitud: str  # Formato YYYY-MM-DD o ISO
    detalle: str
    tipo_servicio: Optional[str] = "Otros"

class ProyectoUpdateRequest(BaseModel):
    cliente: str
    lt_asignado: Optional[str] = None
    estado: str
    detalle: str
    tipo_servicio: Optional[str] = "Otros"
    comentario: Optional[str] = None
    nota_estado: Optional[str] = None

class BitacoraCreateRequest(BaseModel):
    texto: Optional[str] = None

class AsociacionCreateRequest(BaseModel):
    numero: Optional[str] = None

class BacklogAsignacionRequest(BaseModel):
    numero_proyecto: str
    lt_asignado: Optional[str] = None

class UserUpdateRequest(BaseModel):
    nombre_completo: str
    lt_asignado: Optional[str] = None
    rol: str
    activo: bool = True


# Health Check Endpoint
@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "app": "HALO — App Líderes TI",
        "version": "2.0.0"
    }

# Auth Endpoints (SSO Portal de Acceso)
@app.get("/api/auth/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "nombre_completo": current_user["nombre_completo"],
        "lt_asignado": current_user.get("lt_asignado"),
        "rol": current_user["rol"],
        "is_super_admin": current_user.get("is_super_admin", False),
        "portal_access": current_user.get("portal_access", "lectura"),
        "ve_todos_proyectos": ve_todos_los_proyectos(current_user)
    }

# Business Endpoints
@app.get("/api/lideres")
def list_lideres(current_user: dict = Depends(get_current_user)):
    return get_lideres_list()

@app.get("/api/estados")
def list_estados(current_user: dict = Depends(require_lti_or_admin)):
    return get_estados_list()

@app.get("/api/kpis")
def get_kpis(
    lt: Optional[str] = None,
    current_user: dict = Depends(require_lti_or_admin)
):
    lt_to_use, sin_acceso = resolver_lt_scope(current_user, lt)
    if sin_acceso:
        return kpis_vacios()

    return get_dashboard_kpis(lt_filter=lt_to_use, restringido=not ve_todos_los_proyectos(current_user))

@app.get("/api/proyectos")
def list_proyectos(
    lt: Optional[str] = None,
    search: Optional[str] = None,
    estado_sp: Optional[str] = None,
    estado_sga: Optional[str] = None,
    current_user: dict = Depends(require_lti_or_admin)
):
    lt_to_use, sin_acceso = resolver_lt_scope(current_user, lt)
    if sin_acceso:
        return []

    proyectos = get_proyectos(
        lt_filter=lt_to_use,
        search=search,
        estado_sp=estado_sp,
        estado_sga=estado_sga
    )
    return proyectos

def _get_proyecto_or_404(proyecto_id: int, current_user: dict, detail: str = "Proyecto no encontrado") -> dict:
    """
    Punto único de existencia y alcance de un proyecto: 404 si no existe o si el usuario no lo puede ver
    (usuarios sin visibilidad total solo acceden a proyectos con su LT_Asignado). Ambos casos devuelven el mismo 404.
    """
    proyecto = get_proyecto_by_id(proyecto_id)
    if not proyecto or not proyecto_en_alcance(current_user, proyecto):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return proyecto

def _verificar_alcance_proyecto(proyecto_id: int, current_user: dict) -> None:
    """
    Para endpoints cuya función de datos ya resuelve la existencia (diagnóstico, ficha, timeline):
    los usuarios con visibilidad total no requieren lectura previa; el resto verifica el alcance.
    """
    if not ve_todos_los_proyectos(current_user):
        _get_proyecto_or_404(proyecto_id, current_user, detail=f"Proyecto con ID {proyecto_id} no fue encontrado.")

@app.get("/api/proyectos/{proyecto_id}")
def get_proyecto(
    proyecto_id: int,
    current_user: dict = Depends(require_lti_or_admin)
):
    return _get_proyecto_or_404(proyecto_id, current_user)

@app.get("/api/proyectos/{proyecto_id}/solots")
def get_solots(
    proyecto_id: int,
    current_user: dict = Depends(require_lti_or_admin)
):
    proyecto = _get_proyecto_or_404(proyecto_id, current_user)

    solots = get_solots_by_proyecto(proyecto_id, proyecto.get("Numero_Proyecto"), con_asociados=True)
    return solots

@app.get("/api/proyectos/{proyecto_id}/tickets")
def get_tickets(
    proyecto_id: int,
    current_user: dict = Depends(require_lti_or_admin)
):
    proyecto = _get_proyecto_or_404(proyecto_id, current_user)

    tickets = get_tickets_by_proyecto(proyecto_id, proyecto.get("Numero_Proyecto"), con_asociados=True)
    return tickets

@app.get("/api/proyectos/{proyecto_id}/rfcs")
def get_rfcs(
    proyecto_id: int,
    current_user: dict = Depends(require_lti_or_admin)
):
    proyecto = _get_proyecto_or_404(proyecto_id, current_user)

    rfcs = get_rfcs_by_proyecto(proyecto_id, proyecto.get("Numero_Proyecto"), con_asociados=True)
    return rfcs

@app.get("/api/proyectos/{proyecto_id}/diagnostico")
def obtener_diagnostico_proyecto(
    proyecto_id: int,
    current_user: dict = Depends(require_lti_or_admin)
):
    """
    Genera en tiempo real el diagnóstico ejecutivo operacional de un proyecto (1 Clic).
    Analiza solots, tickets, RFCs y formula cuellos de botella y recomendaciones.
    """
    _verificar_alcance_proyecto(proyecto_id, current_user)
    diagnostico = get_diagnostico_proyecto(proyecto_id)
    if not diagnostico:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proyecto con ID {proyecto_id} no fue encontrado."
        )
    return diagnostico

@app.get("/api/proyectos/{proyecto_id}/ficha-ejecutiva")
def obtener_ficha_ejecutiva_proyecto(
    proyecto_id: int,
    current_user: dict = Depends(require_lti_or_admin)
):
    """
    Retorna el JSON estructurado consolidado para la Ficha Ejecutiva del proyecto.
    """
    _verificar_alcance_proyecto(proyecto_id, current_user)
    username = current_user.get("username") or "sistema"
    data = get_ficha_ejecutiva_data(proyecto_id, username=username)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proyecto con ID {proyecto_id} no fue encontrado."
        )
    return data

@app.get("/api/proyectos/{proyecto_id}/ficha-html", response_class=HTMLResponse)
def obtener_ficha_html_proyecto(
    proyecto_id: int,
    auto_print: bool = Query(False),
    current_user: dict = Depends(require_lti_or_admin)
):
    """
    Retorna el documento HTML A4 corporativo Claro HALO de la Ficha Ejecutiva,
    listo para previsualizar o imprimir como PDF.
    """
    _verificar_alcance_proyecto(proyecto_id, current_user)
    username = current_user.get("username") or "sistema"
    data = get_ficha_ejecutiva_data(proyecto_id, username=username)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proyecto con ID {proyecto_id} no fue encontrado."
        )
    html_content = generar_ficha_ejecutiva_html(data, auto_print=auto_print)
    return HTMLResponse(content=html_content, media_type="text/html; charset=utf-8")

@app.get("/api/proyectos/{proyecto_id}/timeline")
def obtener_timeline_proyecto(
    proyecto_id: int,
    current_user: dict = Depends(require_lti_or_admin)
):
    """
    Retorna el JSON estructurado consolidado para la Línea de Tiempo Visual del proyecto.
    Unifica cronológicamente SharePoint, Solots SGA, Tickets HPSM y RFCs.
    """
    _verificar_alcance_proyecto(proyecto_id, current_user)
    data = get_timeline_proyecto(proyecto_id)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proyecto con ID {proyecto_id} no fue encontrado."
        )
    return data

@app.get("/api/alertas/sla")
def get_alertas_sla_endpoint(
    lider: Optional[str] = Query(None, description="Filtro opcional por Líder TI"),
    severidad: Optional[str] = Query("todas", description="Filtro por severidad: todas, critica, advertencia"),
    tipo: Optional[str] = Query("todos", description="Filtro por tipo: todos, ticket, solot, proyecto"),
    limite: Optional[int] = Query(100, ge=1, le=1000, description="Límite de registros en la lista"),
    current_user: dict = Depends(require_lti_or_admin)
):
    """
    Centro de Alertas Tempranas SLA & Escalamiento Rápido (Funcionalidad 5).
    Retorna métricas consolidadas, lista priorizada de alertas y minuta ejecutiva.
    """
    if not ve_todos_los_proyectos(current_user):
        # Alcance forzado a su LTI; sin lt_asignado no ve alertas
        lider, sin_acceso = resolver_lt_scope(current_user, None)
        if sin_acceso:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=procesar_alertas_sla([], [], lider=None, severidad=severidad, tipo=tipo, limite=limite)
            )
    try:
        data = get_alertas_tempranas_sla(
            lider=lider,
            severidad=severidad,
            tipo=tipo,
            limite=limite
        )
        return JSONResponse(status_code=status.HTTP_200_OK, content=data)
    except Exception as e:
        logger.error(f"Error al obtener alertas SLA: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al procesar el centro de alertas tempranas SLA."
        )

@app.put("/api/proyectos/{proyecto_id}")
def actualizar_proyecto(
    proyecto_id: int,
    req: ProyectoUpdateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_lti_or_admin)
):
    cliente = (req.cliente or "").strip()
    estado = (req.estado or "").strip()
    detalle = (req.detalle or "").strip()
    lt_asignado = req.lt_asignado.strip() if req.lt_asignado and req.lt_asignado.strip() else None
    tipo_servicio = req.tipo_servicio.strip() if req.tipo_servicio and req.tipo_servicio.strip() else "Otros"
    comentario = req.comentario.strip() if req.comentario and req.comentario.strip() else None
    nota_estado = req.nota_estado.strip() if req.nota_estado and req.nota_estado.strip() else None

    if not cliente or not estado or not detalle:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los campos 'cliente', 'estado' y 'detalle' son obligatorios"
        )
    if nota_estado and len(nota_estado) > BITACORA_TEXTO_MAX:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La nota no puede superar {BITACORA_TEXTO_MAX} caracteres"
        )

    # Usuarios sin visibilidad total: solo pueden editar proyectos de su alcance (404 si no)
    actual = None
    if not ve_todos_los_proyectos(current_user):
        actual = _get_proyecto_or_404(proyecto_id, current_user)

    estado_normalizado = normalizar_estado_proyecto(estado)
    if estado_normalizado is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Estado inválido. Los estados permitidos son: {', '.join(CANONICAL_ESTADOS_SHAREPOINT)}"
        )
    estado = estado_normalizado

    # La nota de revisión / cierre solo se exige cuando el estado cambia hacia En revision o Cerrado.
    # 'Atendido' (legado) equivale a 'Cerrado' al decidir si hubo cambio.
    estado_anterior = None
    if estado in ("En revision", "Cerrado"):
        if actual is None:
            actual = _get_proyecto_or_404(proyecto_id, current_user)
        estado_anterior = normalizar_estado_proyecto(actual.get("Estado")) or actual.get("Estado")
        if estado_anterior != estado and not nota_estado:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Debe documentar el motivo para pasar el proyecto a 'En revisión'"
                    if estado == "En revision"
                    else "Debe documentar la información de cierre para pasar el proyecto a 'Cerrado'"
                )
            )
    # La nota se guarda como entrada de bitácora (REVISION / CIERRE) en la misma transacción del UPDATE
    bitacora = None
    if estado_anterior is not None and estado_anterior != estado and nota_estado:
        bitacora = {
            "tipo": "REVISION" if estado == "En revision" else "CIERRE",
            "texto": nota_estado,
            "estado_anterior": estado_anterior,
            "estado_nuevo": estado,
            "autor_username": current_user.get("username"),
            "autor_nombre": current_user.get("nombre_completo") or current_user.get("username"),
        }

    # Un proyecto 'Generado' con LTI asignado pasa automáticamente a 'En ejecucion'
    estado = resolver_estado_por_asignacion(estado, lt_asignado)

    update_kwargs = dict(
        proyecto_id=proyecto_id,
        cliente=cliente,
        lt_asignado=lt_asignado,
        estado=estado,
        detalle=detalle,
        tipo_servicio=tipo_servicio,
        comentario=comentario
    )
    if bitacora:
        update_kwargs["bitacora"] = bitacora
    result = update_proyecto(**update_kwargs)

    if not result.get("success"):
        if result.get("error") == "not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "Error al actualizar el proyecto")
        )

    # Detectar si pasó de sin asignar a asignado y despachar correo en background
    if result.get("was_assigned"):
        logger.info(
            f"Asignación detectada para Proyecto ID {proyecto_id}: Asignado a '{result.get('new_lt')}'. "
            "Programando despacho asíncrono de notificación..."
        )
        background_tasks.add_task(
            notificar_asignacion_lti_bg,
            proyecto_data=result.get("data"),
            prev_lt=result.get("prev_lt"),
            new_lt=result.get("new_lt"),
            actor_user=current_user
        )

    return {
        "message": "Proyecto actualizado exitosamente",
        "data": result.get("data"),
        "bitacora_entry_id": result.get("bitacora_entry_id")
    }

# -----------------------------------------------------------------------------
# BITÁCORA Y ADJUNTOS DE PROYECTOS
# -----------------------------------------------------------------------------
ADJUNTOS_CHUNK_BYTES = 1024 * 1024

@app.get("/api/proyectos/{proyecto_id}/bitacora")
def listar_bitacora(
    proyecto_id: int,
    current_user: dict = Depends(require_lti_or_admin)
):
    _get_proyecto_or_404(proyecto_id, current_user)
    return get_bitacora_by_proyecto(proyecto_id)

@app.post("/api/proyectos/{proyecto_id}/bitacora", status_code=status.HTTP_201_CREATED)
def crear_entrada_bitacora(
    proyecto_id: int,
    req: BitacoraCreateRequest,
    current_user: dict = Depends(require_lti_or_admin)
):
    texto = (req.texto or "").strip()
    if not texto:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El texto de la bitácora es obligatorio")
    if len(texto) > BITACORA_TEXTO_MAX:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El texto de la bitácora no puede superar {BITACORA_TEXTO_MAX} caracteres"
        )
    _get_proyecto_or_404(proyecto_id, current_user)
    return create_bitacora_entry(
        proyecto_id=proyecto_id,
        texto=texto,
        autor_username=current_user.get("username"),
        autor_nombre=current_user.get("nombre_completo") or current_user.get("username")
    )

def _nombre_original_seguro(filename: Optional[str]) -> str:
    """Solo el nombre del archivo, sin rutas ni caracteres de control."""
    nombre = os.path.basename((filename or "").replace("\\", "/"))
    return re.sub(r"[\x00-\x1f\x7f]", "", nombre).strip()

@app.post("/api/proyectos/{proyecto_id}/bitacora/{entry_id}/adjuntos", status_code=status.HTTP_201_CREATED)
def subir_adjunto(
    proyecto_id: int,
    entry_id: int,
    archivo: UploadFile = File(...),
    current_user: dict = Depends(require_lti_or_admin)
):
    _get_proyecto_or_404(proyecto_id, current_user)
    if not get_bitacora_entry(proyecto_id, entry_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entrada de bitácora no encontrada")

    nombre_completo = _nombre_original_seguro(archivo.filename)
    extension = nombre_completo.rsplit(".", 1)[-1].lower() if "." in nombre_completo else ""
    nombre_original = nombre_completo[:255]
    permitidas = app_config.ADJUNTOS_EXTENSIONES_PERMITIDAS
    if extension not in permitidas:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de archivo no permitido. Formatos aceptados: {', '.join(permitidas)}"
        )

    # Se copia en bloques y se corta apenas se supera el límite; el archivo parcial se borra
    directorio = get_adjuntos_dir()
    os.makedirs(directorio, exist_ok=True)
    nombre_almacenado = f"{uuid.uuid4().hex}.{extension}"
    destino = directorio / nombre_almacenado
    tamano = 0
    try:
        with open(destino, "wb") as salida:
            while True:
                bloque = archivo.file.read(ADJUNTOS_CHUNK_BYTES)
                if not bloque:
                    break
                tamano += len(bloque)
                if tamano > app_config.ADJUNTOS_MAX_BYTES:
                    break
                salida.write(bloque)
    except Exception:
        remove_adjunto_files([nombre_almacenado])
        raise
    if tamano > app_config.ADJUNTOS_MAX_BYTES:
        remove_adjunto_files([nombre_almacenado])
        raise HTTPException(
            status_code=413,
            detail="El archivo supera el máximo de 9 MB"
        )
    if tamano == 0:
        remove_adjunto_files([nombre_almacenado])
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo está vacío")

    try:
        return create_adjunto(
            bitacora_id=entry_id,
            proyecto_id=proyecto_id,
            nombre_original=nombre_original,
            nombre_almacenado=nombre_almacenado,
            content_type=(archivo.content_type or "")[:150] or None,
            tamano_bytes=tamano,
            autor_username=current_user.get("username")
        )
    except Exception as e:
        remove_adjunto_files([nombre_almacenado])
        logger.error(f"Error al registrar el adjunto del proyecto {proyecto_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al guardar el adjunto"
        )

@app.get("/api/proyectos/{proyecto_id}/adjuntos/{adjunto_id}")
def descargar_adjunto(
    proyecto_id: int,
    adjunto_id: int,
    current_user: dict = Depends(require_lti_or_admin)
):
    _get_proyecto_or_404(proyecto_id, current_user)
    adjunto = get_adjunto(proyecto_id, adjunto_id)
    ruta = adjunto_path(adjunto.get("Nombre_Almacenado")) if adjunto else None
    if not ruta or not ruta.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Adjunto no encontrado")
    return FileResponse(
        ruta,
        media_type="application/octet-stream",
        filename=adjunto.get("Nombre_Original") or ruta.name,
        headers={"X-Content-Type-Options": "nosniff"}
    )

# -----------------------------------------------------------------------------
# ASOCIACIÓN DE PROYECTOS POR N° DE PROYECTO
# -----------------------------------------------------------------------------
ASOCIACION_NUMERO_RE = re.compile(r"[A-Za-z0-9-]{1,30}")

@app.get("/api/proyectos/{proyecto_id}/asociaciones")
def listar_asociaciones(
    proyecto_id: int,
    current_user: dict = Depends(require_lti_or_admin)
):
    proyecto = _get_proyecto_or_404(proyecto_id, current_user)
    return get_asociaciones_proyecto(proyecto_id, proyecto.get("Numero_Proyecto"))

@app.post("/api/proyectos/{proyecto_id}/asociaciones", status_code=status.HTTP_201_CREATED)
def crear_asociacion(
    proyecto_id: int,
    req: AsociacionCreateRequest,
    current_user: dict = Depends(require_lti_or_admin)
):
    proyecto = _get_proyecto_or_404(proyecto_id, current_user)
    bruto = (req.numero or "").strip()
    if not bruto:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El N° de proyecto es obligatorio")
    if not ASOCIACION_NUMERO_RE.fullmatch(bruto):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El N° de proyecto solo puede contener letras, números y guiones (máx. 30 caracteres)"
        )
    numero = normalizar_numero_asociado(bruto)
    numero_propio = proyecto.get("Numero_Proyecto")
    if numero == normalizar_numero_asociado(numero_propio):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes asociar un proyecto consigo mismo")
    result = create_asociacion(proyecto_id, numero_propio, numero, current_user.get("username"))
    if result["status"] == "duplicate":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El N° de proyecto ya está asociado a este grupo")
    return result["data"]

@app.delete("/api/proyectos/{proyecto_id}/asociaciones/{asociacion_id}")
def eliminar_asociacion(
    proyecto_id: int,
    asociacion_id: int,
    current_user: dict = Depends(require_lti_or_admin)
):
    proyecto = _get_proyecto_or_404(proyecto_id, current_user)
    if not delete_asociacion(proyecto_id, proyecto.get("Numero_Proyecto"), asociacion_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asociación no encontrada")
    return {"message": "Asociación eliminada", "id": asociacion_id}

@app.delete("/api/proyectos/{proyecto_id}")
def eliminar_proyecto(
    proyecto_id: int,
    current_user: dict = Depends(require_admin)
):
    if not ve_todos_los_proyectos(current_user):
        _get_proyecto_or_404(proyecto_id, current_user)
    result = delete_proyecto(proyecto_id)
    if not result.get("success"):
        if result.get("error") == "not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "Error al eliminar el proyecto")
        )

    return {
        "message": "Proyecto eliminado exitosamente",
        "id": result.get("id"),
        "numero_proyecto": result.get("numero_proyecto"),
        "cliente": result.get("cliente")
    }

@app.post("/api/backlog/asignar-lti")
def asignar_lti_desde_backlog(
    req: BacklogAsignacionRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_lti_or_admin)
):
    """Asigna un LTI a un proyecto del backlog de operaciones (crea el proyecto si no existe)."""
    # Puede tocar proyectos de cualquier LTI: solo para usuarios con visibilidad total
    if not ve_todos_los_proyectos(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los coordinadores de Líderes TI pueden asignar LTI desde el backlog"
        )
    numero_proyecto = (req.numero_proyecto or "").strip()
    lt_asignado = (req.lt_asignado or "").strip()

    # Un número solo con ceros equivale a vacío y matchearía filas sin N° de proyecto
    if not numero_proyecto.lstrip('0'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe indicar el N° de proyecto"
        )
    lideres = get_lideres_list()
    if lt_asignado not in lideres:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Líder TI inválido. Los líderes permitidos son: {', '.join(lideres)}"
        )

    result = assign_lti_from_backlog(
        numero_proyecto=numero_proyecto,
        lt_asignado=lt_asignado,
        actor_nombre=current_user.get("nombre_completo") or current_user.get("username")
    )
    if not result.get("success"):
        if result.get("error") == "not_found_backlog":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El proyecto no existe en el backlog de operaciones"
            )
        logger.error(f"Error al asignar LTI desde backlog ({numero_proyecto}): {result.get('message')}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al asignar el LTI en la base de datos"
        )

    if result.get("was_assigned"):
        background_tasks.add_task(
            notificar_asignacion_lti_bg,
            proyecto_data=result.get("data"),
            prev_lt=result.get("prev_lt"),
            new_lt=result.get("new_lt"),
            actor_user=current_user
        )

    created = result.get("action") == "created"
    return JSONResponse(
        status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        content={
            "message": "Proyecto creado y LTI asignado" if created else "LTI asignado al proyecto",
            "action": result.get("action"),
            "data": result.get("data")
        }
    )

# Direct Multi-Tag Search Endpoint (Sin considerar relaciones)
@app.get("/api/search/direct")
def direct_search(
    q: Optional[str] = Query(None, description="Término o tags separados por coma"),
    tags: Optional[List[str]] = Query(None, description="Lista de tags"),
    table: str = Query("all", description="Tabla destino: all, proyectos, solots, tickets, rfcs"),
    limit: int = Query(150, ge=1, le=500),
    current_user: dict = Depends(require_lti_or_admin)
):
    search_tags = []
    if tags:
        search_tags.extend(tags)
    if q:
        # Split by comma or json list
        parts = [p.strip() for p in q.split(",") if p.strip()]
        for p in parts:
            if p not in search_tags:
                search_tags.append(p)

    if not search_tags:
        raise HTTPException(status_code=400, detail="Debe ingresar al menos un parámetro o tag de búsqueda")

    return search_direct_tables(tags=search_tags, target_table=table, limit=limit)

# -----------------------------------------------------------------------------
# Mantenedor de Usuarios (CRUD API - Exclusivo ADMIN)
# -----------------------------------------------------------------------------
@app.get("/api/usuarios")
def list_usuarios(
    search: Optional[str] = None,
    rol: Optional[str] = None,
    activo: Optional[str] = None,
    current_user: dict = Depends(require_admin)
):
    act_filter = None
    if activo is not None and activo != "":
        if str(activo).lower() in ("true", "1", "yes"):
            act_filter = True
        elif str(activo).lower() in ("false", "0", "no"):
            act_filter = False
    return get_all_usuarios(search=search, rol=rol, activo=act_filter)

@app.get("/api/usuarios/{user_id}")
def get_usuario(
    user_id: int,
    current_user: dict = Depends(require_admin)
):
    user = get_usuario_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return user

@app.put("/api/usuarios/{user_id}")
def actualizar_usuario_endpoint(
    user_id: int,
    req: UserUpdateRequest,
    current_user: dict = Depends(require_admin)
):
    nombre_completo = (req.nombre_completo or "").strip()
    rol = (req.rol or "").strip().upper()
    lt_asignado = (req.lt_asignado or "").strip() or None
    activo = bool(req.activo)

    if not nombre_completo or not rol:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los campos 'nombre_completo' y 'rol' son obligatorios"
        )
    if rol not in ("PM", "LTI", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El rol debe ser PM, LTI o ADMIN"
        )

    result = update_usuario(
        user_id=user_id,
        nombre_completo=nombre_completo,
        lt_asignado=lt_asignado,
        rol=rol,
        activo=activo
    )
    if not result.get("success"):
        if result.get("error") == "not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message", "Error al actualizar usuario"))

    return result.get("data")

@app.patch("/api/usuarios/{user_id}/toggle-status")
def toggle_status_endpoint(
    user_id: int,
    current_user: dict = Depends(require_admin)
):
    target_user = get_usuario_by_id(user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    if target_user.get("username") == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permite bloquear la cuenta principal de administrador 'admin'"
        )
    if int(target_user.get("id")) == int(current_user.get("id")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permite bloquear la propia cuenta de administrador en sesión"
        )

    result = toggle_user_status(user_id)
    if not result.get("success"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message", "Error al alternar estado"))

    return {
        "message": "Estado de usuario actualizado",
        "id": result.get("id"),
        "activo": result.get("activo")
    }

@app.delete("/api/usuarios/{user_id}")
def eliminar_usuario_endpoint(
    user_id: int,
    current_user: dict = Depends(require_admin)
):
    target_user = get_usuario_by_id(user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    if target_user.get("username") == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permite eliminar la cuenta principal de administrador 'admin'"
        )
    if int(target_user.get("id")) == int(current_user.get("id")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permite auto-eliminar la propia cuenta en sesión"
        )

    result = delete_usuario(user_id)
    if not result.get("success"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message", "Error al eliminar usuario"))

    return {
        "message": "Usuario eliminado exitosamente",
        "id": result.get("id"),
        "username": result.get("username")
    }

# -----------------------------------------------------------------------------
# Solicitud LTI Endpoints
# -----------------------------------------------------------------------------
@app.get("/api/solicitudes/catalogos")
def get_catalogos_solicitud(current_user: dict = Depends(get_current_user)):
    return get_solicitud_catalogos()

@app.get("/api/solicitudes/autocomplete-proyectos")
def autocomplete_proyectos(
    q: str = Query(..., min_length=2, description="Término de búsqueda para autocompletar"),
    current_user: dict = Depends(get_current_user)
):
    return search_backlog_proyectos_autocomplete(q)

@app.get("/api/solicitudes/solots-liray")
def get_solots_liray_endpoint(
    nro_proyecto: str = Query(..., min_length=1, description="N° de proyecto para buscar Solots Liray"),
    current_user: dict = Depends(get_current_user)
):
    solots = get_solots_liray_by_proyecto(nro_proyecto)
    formatted = format_solots_liray_text(solots)
    return {
        "nro_proyecto": nro_proyecto,
        "total_solots_liray": len(solots),
        "total_solots": len(solots),
        "solots": solots,
        "formatted_text": formatted,
        "detalle_sugerido": formatted
    }

@app.post("/api/solicitudes/crear", status_code=status.HTTP_201_CREATED)
def crear_solicitud(
    req: SolicitudCreacionRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    cliente = (req.cliente or "").strip()
    numero_proyecto = (req.numero_proyecto or "").strip()
    lt_asignado = (req.lt_asignado or "").strip() or None
    # Regla de Negocio Inmutable: El estado de toda nueva solicitud es siempre 'Generado'
    estado = "Generado"
    fecha_solicitud = (req.fecha_solicitud or "").strip()
    detalle = (req.detalle or "").strip()
    # Regla de Negocio Fija: El tipo de servicio es siempre 'Otros'
    tipo_servicio = "Otros"

    if not cliente or not numero_proyecto or not fecha_solicitud or not detalle:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Todos los campos marcados con (*) son obligatorios y no pueden estar vacíos"
        )

    solicitante = current_user.get("nombre_completo") or current_user.get("username")
    result = create_solicitud_lti(
        cliente=cliente,
        numero_proyecto=numero_proyecto,
        lt_asignado=lt_asignado,
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

    created_data = result.get("data")

    # Despachar notificación formal de creación en background (no bloquea UI)
    background_tasks.add_task(
        notificar_creacion_solicitud_bg,
        proyecto_data=created_data,
        solicitante_user=current_user
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "message": "Solicitud LTI creada exitosamente",
            "data": created_data
        }
    )

# -----------------------------------------------------------------------------
# ENDPOINTS ADMINISTRATIVOS: RECORDATORIOS DE SOLICITUD LTI
# -----------------------------------------------------------------------------
@app.get("/api/solicitudes/recordatorios/estado")
def get_recordatorios_estado(current_user: dict = Depends(require_admin)):
    """Audita el estado del worker de recordatorios y lista de solicitudes pendientes."""
    is_active = bool(_reminder_task and not _reminder_task.done())
    pendientes = get_proyectos_pendientes_recordatorio(intervalo_minutos=REMINDER_INTERVAL_MINUTES)
    todos_sin_asignar = get_proyectos_pendientes_recordatorio(intervalo_minutos=0)

    return {
        "scheduler_active": is_active,
        "check_interval_seconds": REMINDER_CHECK_SECONDS,
        "check_interval_minutes": round(REMINDER_CHECK_SECONDS / 60, 1),
        "reminder_threshold_hours": REMINDER_INTERVAL_HOURS,
        "total_proyectos_sin_asignar": len(todos_sin_asignar),
        "total_proyectos_requieren_recordatorio": len(pendientes),
        "destinatarios_coordinadores": COORDINADORES_LTI_EMAILS,
        "proyectos_pendientes": [
            {
                "id": p.get("ID"),
                "numero_proyecto": p.get("Numero_Proyecto"),
                "cliente": p.get("Cliente"),
                "creado": p.get("Creado"),
                "ultimo_recordatorio": p.get("Ultimo_Recordatorio"),
                "contador_recordatorios": p.get("Contador_Recordatorios"),
                "minutos_desde_creacion": p.get("Minutos_Desde_Creacion"),
                "solicitante": p.get("Solicitante")
            }
            for p in pendientes
        ]
    }

@app.post("/api/solicitudes/recordatorios/ejecutar-manual")
def ejecutar_recordatorios_manual(current_user: dict = Depends(require_admin)):
    """Dispara un chequeo forzado manual de recordatorios para verificación o contingencia."""
    pendientes = get_proyectos_pendientes_recordatorio(intervalo_minutos=REMINDER_INTERVAL_MINUTES)
    if not pendientes:
        return {
            "success": True,
            "message": "No hay solicitudes pendientes que requieran recordatorio en este momento.",
            "recordatorios_enviados": 0,
            "detalles": []
        }

    email_res = send_solicitud_recordatorio_email(pendientes, horas_transcurridas=REMINDER_INTERVAL_HOURS)
    # Con EMAIL_REDIRECT_TO (desarrollo) no se marca en BD: producción debe seguir enviando el recordatorio real
    registrar_en_bd = not is_email_redirect_active()
    detalles = []
    for p in pendientes:
        if registrar_en_bd:
            registrar_recordatorio_enviado(p["ID"])
        detalles.append({
            "id": p.get("ID"),
            "numero_proyecto": p.get("Numero_Proyecto"),
            "cliente": p.get("Cliente"),
            "recordatorio_num": int(p.get("Contador_Recordatorios") or 0) + 1,
            "destinatarios": COORDINADORES_LTI_EMAILS
        })

    return {
        "success": True,
        "message": f"Chequeo manual ejecutado exitosamente. Se notificaron {len(pendientes)} solicitudes.",
        "recordatorios_enviados": len(pendientes),
        "email_delivery": email_res.get("success", False),
        "registrado_en_bd": registrar_en_bd,
        "detalles": detalles
    }

# Automation Endpoints
@app.post("/api/automation/create-ticket")
@app.post("/api/automation/create-ticket/", include_in_schema=False)
async def create_ticket(
    req: TicketCreationRequest,
    current_user: dict = Depends(require_lti_or_admin)
):
    request_data = req.model_dump()
    return StreamingResponse(
        stream_ticket_creation(request_data),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/api/automation/send-ticket-email")
@app.post("/api/automation/send-ticket-email/", include_in_schema=False)
async def send_ticket_email(
    request: Request,
    to_email: Optional[str] = Form(None),
    para: Optional[str] = Form(None),
    subject: Optional[str] = Form(None),
    asunto: Optional[str] = Form(None),
    body: Optional[str] = Form(None),
    cuerpo: Optional[str] = Form(None),
    ticket_id: Optional[str] = Form(None),
    peticion_id: Optional[str] = Form(None),
    attachment: Optional[UploadFile] = File(None),
    adjunto: Optional[UploadFile] = File(None),
    current_user: dict = Depends(require_lti_or_admin)
):
    content_type = request.headers.get("content-type", "").lower()
    
    target_recipient = None
    target_subject = None
    target_body = None
    target_ticket_id = ticket_id
    target_peticion_id = peticion_id
    attachment_bytes = None
    attachment_filename = None
    attachment_content_type = None

    HTTP_413 = getattr(status, "HTTP_413_CONTENT_TOO_LARGE", 413)

    if content_type.startswith("application/json"):
        try:
            json_data = await request.json()
        except Exception:
            json_data = {}
        
        target_recipient = (
            json_data.get("to_email")
            or json_data.get("para")
            or json_data.get("destinatario")
            or json_data.get("to_emails")
            or ""
        )
        if isinstance(target_recipient, list):
            target_recipient = ", ".join(str(r) for r in target_recipient)
        else:
            target_recipient = str(target_recipient)

        target_subject = str(
            json_data.get("subject")
            or json_data.get("asunto")
            or json_data.get("titulo")
            or ""
        )
        target_body = str(
            json_data.get("body")
            or json_data.get("cuerpo")
            or json_data.get("descripcion")
            or ""
        )
        target_ticket_id = (
            json_data.get("ticket_id")
            or json_data.get("id_ticket")
            or json_data.get("ticket")
            or ticket_id
        )
        target_peticion_id = (
            json_data.get("peticion_id")
            or json_data.get("id_peticion")
            or json_data.get("peticion")
            or peticion_id
        )

        # Base64 attachment support
        b64_data = (
            json_data.get("attachment_base64")
            or json_data.get("adjunto_base64")
            or json_data.get("base64")
            or json_data.get("archivo_base64")
        )
        if b64_data and isinstance(b64_data, str):
            if "," in b64_data:
                b64_data = b64_data.split(",", 1)[1]
            try:
                attachment_bytes = base64.b64decode(b64_data, validate=True)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El archivo adjunto en Base64 es inválido: {e}"
                )
            if len(attachment_bytes) > 15 * 1024 * 1024:
                raise HTTPException(
                    status_code=HTTP_413,
                    detail="El archivo adjunto supera el tamaño máximo permitido de 15 MB."
                )
            attachment_filename = (
                json_data.get("attachment_filename")
                or json_data.get("adjunto_nombre")
                or json_data.get("filename")
                or json_data.get("nombre_archivo")
                or "adjunto.dat"
            )
            attachment_content_type = (
                json_data.get("attachment_content_type")
                or json_data.get("content_type")
                or json_data.get("tipo_contenido")
            )
    else:
        # Form / Multipart / URL-Encoded
        target_recipient = to_email or para
        target_subject = subject or asunto
        target_body = body or cuerpo
        target_ticket_id = ticket_id
        target_peticion_id = peticion_id
        file_upload = attachment or adjunto

        # Fallback to direct form parsing if aliases were sent in form without matching parameters
        try:
            form_data = await request.form()
            target_recipient = (
                target_recipient
                or form_data.get("destinatario")
                or form_data.get("to_emails")
                or form_data.get("para")
                or form_data.get("to_email")
            )
            target_subject = (
                target_subject
                or form_data.get("asunto")
                or form_data.get("titulo")
                or form_data.get("subject")
            )
            target_body = (
                target_body
                or form_data.get("cuerpo")
                or form_data.get("descripcion")
                or form_data.get("body")
            )
            target_ticket_id = (
                target_ticket_id
                or form_data.get("id_ticket")
                or form_data.get("ticket")
                or form_data.get("numero_ticket")
            )
            target_peticion_id = (
                target_peticion_id
                or form_data.get("id_peticion")
                or form_data.get("peticion")
                or form_data.get("numero_peticion")
            )
            if not file_upload:
                raw_file = form_data.get("file") or form_data.get("archivo") or form_data.get("attachment") or form_data.get("adjunto")
                if hasattr(raw_file, "filename") and raw_file.filename:
                    file_upload = raw_file
        except Exception:
            pass

        if file_upload and hasattr(file_upload, "filename") and file_upload.filename:
            attachment_bytes = await file_upload.read()
            if len(attachment_bytes) > 15 * 1024 * 1024:
                raise HTTPException(
                    status_code=HTTP_413,
                    detail="El archivo adjunto supera el tamaño máximo permitido de 15 MB."
                )
            attachment_filename = file_upload.filename
            attachment_content_type = getattr(file_upload, "content_type", None)

    target_recipient = (target_recipient or "").strip()
    target_subject = (target_subject or "").strip()
    target_body = (target_body or "").strip()
    target_ticket_id = str(target_ticket_id).strip() if target_ticket_id else None
    target_peticion_id = str(target_peticion_id).strip() if target_peticion_id else None

    if not target_recipient:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La dirección de destinatario es requerida."
        )

    if not target_subject:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El asunto del correo es requerido."
        )

    if not target_body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El cuerpo del correo es requerido."
        )

    try:
        result = send_ticket_notification_email(
            to_email=target_recipient,
            subject=target_subject,
            body=target_body,
            attachment_bytes=attachment_bytes,
            attachment_filename=attachment_filename,
            attachment_content_type=attachment_content_type,
            ticket_id=target_ticket_id,
            peticion_id=target_peticion_id
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=result
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)
        )
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error no controlado en endpoint send_ticket_email: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al procesar el envío de correo. Por favor contacte al administrador."
        )

# Mount Frontend Static Files
frontend_dir = os.path.join(BASE_DIR, "frontend")
if os.path.exists(frontend_dir):
    app.mount("/css", StaticFiles(directory=os.path.join(frontend_dir, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(frontend_dir, "js")), name="js")

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

@app.get("/{full_path:path}")
def serve_catch_all(full_path: str):
    if not _is_dev and full_path in ("docs", "redoc", "openapi.json"):
        raise HTTPException(status_code=404, detail="Not Found")
    file_path = os.path.join(frontend_dir, full_path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    return FileResponse(os.path.join(frontend_dir, "index.html"))
