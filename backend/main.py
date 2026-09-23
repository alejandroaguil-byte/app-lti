import os
import base64
import logging
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, status, Query, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("main")

from .config import BASE_DIR, CORS_ORIGINS
from .auth import (
    get_current_user,
    require_admin,
    require_lti_or_admin,
    require_non_pm
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
    get_proyectos,
    get_proyecto_by_id,
    get_solots_by_proyecto,
    get_tickets_by_proyecto,
    get_rfcs_by_proyecto,
    get_dashboard_kpis,
    search_direct_tables,
    get_db_connection,
    get_solicitud_catalogos,
    get_solots_liray_by_proyecto,
    format_solots_liray_text,
    search_backlog_proyectos_autocomplete,
    check_proyecto_exists,
    create_solicitud_lti,
    update_proyecto,
    delete_proyecto
)
from .seed_users import seed_default_users
from .ticket_automation import stream_ticket_creation
from .email_service import send_ticket_notification_email

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        seed_default_users()
    except Exception as e:
        print(f"[ERROR] Error al inicializar tablas y usuarios: {e}")
    yield

app = FastAPI(title="App LTI - Seguimiento Líderes TI", version="2.0.0", lifespan=lifespan)

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
        "portal_access": current_user.get("portal_access", "lectura")
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
    lt_to_use = lt
    if current_user["rol"] != "ADMIN" and not lt:
        lt_to_use = current_user["lt_asignado"]
    elif lt == "__ALL__":
        lt_to_use = None
    elif lt and (lt == "__UNASSIGNED__" or lt.strip().lower() in ("sin asignar", "__unassigned__", "sin_asignar")):
        lt_to_use = "__UNASSIGNED__"

    return get_dashboard_kpis(lt_filter=lt_to_use)

@app.get("/api/proyectos")
def list_proyectos(
    lt: Optional[str] = None,
    search: Optional[str] = None,
    estado_sp: Optional[str] = None,
    estado_sga: Optional[str] = None,
    current_user: dict = Depends(require_lti_or_admin)
):
    lt_to_use = lt
    if current_user["rol"] != "ADMIN" and not lt:
        lt_to_use = current_user["lt_asignado"]
    elif lt == "__ALL__":
        lt_to_use = None
    elif lt and (lt == "__UNASSIGNED__" or lt.strip().lower() in ("sin asignar", "__unassigned__", "sin_asignar")):
        lt_to_use = "__UNASSIGNED__"

    proyectos = get_proyectos(
        lt_filter=lt_to_use,
        search=search,
        estado_sp=estado_sp,
        estado_sga=estado_sga
    )
    return proyectos

@app.get("/api/proyectos/{proyecto_id}")
def get_proyecto(
    proyecto_id: int,
    current_user: dict = Depends(require_lti_or_admin)
):
    proyecto = get_proyecto_by_id(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return proyecto

@app.get("/api/proyectos/{proyecto_id}/solots")
def get_solots(
    proyecto_id: int,
    current_user: dict = Depends(require_lti_or_admin)
):
    proyecto = get_proyecto_by_id(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    
    solots = get_solots_by_proyecto(proyecto_id, proyecto.get("Numero_Proyecto"))
    return solots

@app.get("/api/proyectos/{proyecto_id}/tickets")
def get_tickets(
    proyecto_id: int,
    current_user: dict = Depends(require_lti_or_admin)
):
    proyecto = get_proyecto_by_id(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    
    tickets = get_tickets_by_proyecto(proyecto_id, proyecto.get("Numero_Proyecto"))
    return tickets

@app.get("/api/proyectos/{proyecto_id}/rfcs")
def get_rfcs(
    proyecto_id: int,
    current_user: dict = Depends(require_lti_or_admin)
):
    proyecto = get_proyecto_by_id(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    
    rfcs = get_rfcs_by_proyecto(proyecto_id, proyecto.get("Numero_Proyecto"))
    return rfcs

@app.put("/api/proyectos/{proyecto_id}")
def actualizar_proyecto(
    proyecto_id: int,
    req: ProyectoUpdateRequest,
    current_user: dict = Depends(require_lti_or_admin)
):
    cliente = (req.cliente or "").strip()
    estado = (req.estado or "").strip()
    detalle = (req.detalle or "").strip()
    lt_asignado = req.lt_asignado.strip() if req.lt_asignado and req.lt_asignado.strip() else None
    tipo_servicio = req.tipo_servicio.strip() if req.tipo_servicio and req.tipo_servicio.strip() else "Otros"
    comentario = req.comentario.strip() if req.comentario and req.comentario.strip() else None

    if not cliente or not estado or not detalle:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los campos 'cliente', 'estado' y 'detalle' son obligatorios"
        )

    estado_map = {
        "generado": "Generado",
        "en revision": "En revision",
        "en revisión": "En revision",
        "atendido": "Atendido"
    }
    estado_normalizado = estado_map.get(estado.lower(), estado)
    estados_permitidos = ["Generado", "En revision", "Atendido"]
    if estado_normalizado not in estados_permitidos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Estado inválido. Los estados permitidos son: {', '.join(estados_permitidos)}"
        )
    estado = estado_normalizado

    result = update_proyecto(
        proyecto_id=proyecto_id,
        cliente=cliente,
        lt_asignado=lt_asignado,
        estado=estado,
        detalle=detalle,
        tipo_servicio=tipo_servicio,
        comentario=comentario
    )

    if not result.get("success"):
        if result.get("error") == "not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "Error al actualizar el proyecto")
        )

    return {
        "message": "Proyecto actualizado exitosamente",
        "data": result.get("data")
    }

@app.delete("/api/proyectos/{proyecto_id}")
def eliminar_proyecto(
    proyecto_id: int,
    current_user: dict = Depends(require_admin)
):
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
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "message": "Solicitud LTI creada exitosamente",
            "data": result.get("data")
        }
    )

# Automation Endpoints
@app.post("/api/automation/create-ticket")
@app.post("/api/automation/create-ticket/", include_in_schema=False)
async def create_ticket(
    req: TicketCreationRequest,
    current_user: dict = Depends(get_current_user)
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
    current_user: dict = Depends(get_current_user)
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
    file_path = os.path.join(frontend_dir, full_path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    return FileResponse(os.path.join(frontend_dir, "index.html"))
