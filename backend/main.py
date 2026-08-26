import os
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from .config import BASE_DIR
from .auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user
)
from .db import (
    get_user_by_username,
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

app = FastAPI(title="App LTI - Seguimiento Líderes TI", version="1.3.0")

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup event
@app.on_event("startup")
def on_startup():
    try:
        seed_default_users()
    except Exception as e:
        print(f"[ERROR] Error al inicializar tablas y usuarios: {e}")

# Schemas
class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class TicketCreationRequest(BaseModel):
    contacto: str = "ALEJANDRO JAVIER AGUILAR MORALES"
    titulo: str = "Creacion test automatizacion"
    descripcion: str = "Prueba test automatización"
    area: str = "Proyectos"
    subarea: str = "Apoyo habilitacion cliente"
    detalle: str = "Apoyo habilitacion cliente"
    grupo: str = "Lideres Tecnicos"
    impacto: Optional[str] = None
    urgencia: Optional[str] = None
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

# Auth Endpoints
@app.post("/api/auth/login")
def login(req: LoginRequest):
    user = get_user_by_username(req.username.strip())
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos"
        )
    
    token_data = {
        "sub": user["username"],
        "nombre_completo": user["nombre_completo"],
        "lt_asignado": user["lt_asignado"],
        "rol": user["rol"]
    }
    token = create_access_token(token_data)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "nombre_completo": user["nombre_completo"],
            "lt_asignado": user["lt_asignado"],
            "rol": user["rol"]
        }
    }

@app.get("/api/auth/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "nombre_completo": current_user["nombre_completo"],
        "lt_asignado": current_user["lt_asignado"],
        "rol": current_user["rol"]
    }

@app.post("/api/auth/change-password")
def change_password(req: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    user = get_user_by_username(current_user["username"])
    if not user or not verify_password(req.current_password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual es incorrecta"
        )
    
    new_hash = hash_password(req.new_password)
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE dbo.App_Usuarios SET password_hash = %s WHERE id = %s",
                (new_hash, current_user["id"])
            )
            conn.commit()
    finally:
        conn.close()
        
    return {"message": "Contraseña actualizada exitosamente"}

# Business Endpoints
@app.get("/api/lideres")
def list_lideres(current_user: dict = Depends(get_current_user)):
    return get_lideres_list()

@app.get("/api/estados")
def list_estados(current_user: dict = Depends(get_current_user)):
    return get_estados_list()

@app.get("/api/kpis")
def get_kpis(
    lt: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
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
    current_user: dict = Depends(get_current_user)
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
    current_user: dict = Depends(get_current_user)
):
    proyecto = get_proyecto_by_id(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return proyecto

@app.get("/api/proyectos/{proyecto_id}/solots")
def get_solots(
    proyecto_id: int,
    current_user: dict = Depends(get_current_user)
):
    proyecto = get_proyecto_by_id(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    
    solots = get_solots_by_proyecto(proyecto_id, proyecto.get("Numero_Proyecto"))
    return solots

@app.get("/api/proyectos/{proyecto_id}/tickets")
def get_tickets(
    proyecto_id: int,
    current_user: dict = Depends(get_current_user)
):
    proyecto = get_proyecto_by_id(proyecto_id)
    if not proyecto:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    
    tickets = get_tickets_by_proyecto(proyecto_id, proyecto.get("Numero_Proyecto"))
    return tickets

@app.get("/api/proyectos/{proyecto_id}/rfcs")
def get_rfcs(
    proyecto_id: int,
    current_user: dict = Depends(get_current_user)
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
    current_user: dict = Depends(get_current_user)
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

    estados_permitidos = ["Generado", "En revision", "Atendido"]
    if estado not in estados_permitidos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Estado inválido. Los estados permitidos son: {', '.join(estados_permitidos)}"
        )

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
    current_user: dict = Depends(get_current_user)
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
    current_user: dict = Depends(get_current_user)
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
    req: TicketCreationRequest = TicketCreationRequest(),
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
