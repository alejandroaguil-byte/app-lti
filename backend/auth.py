import datetime
from typing import Optional
import jwt
from fastapi import HTTPException, Security, status, Depends, Request
from .config import PORTAL_JWT_SECRET, JWT_ALGORITHM, LTI_ASSIGNER_USERNAMES
from .db import get_or_create_jit_user, get_user_by_username

def decode_portal_token(token: str) -> dict:
    """Decodifica y valida el token JWT emitido por el Portal de Acceso."""
    try:
        payload = jwt.decode(
            token,
            PORTAL_JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"verify_sub": False}
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión ha expirado en el Portal de Acceso. Inicia sesión nuevamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación del Portal inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("purpose") != "session":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no autorizado para sesión",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload

def get_current_user(request: Request) -> dict:
    """Extrae el token del cookie access_token (o header Bearer de fallback) y autentica contra SSO Portal."""
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado. Inicie sesión en el Portal de Acceso.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_portal_token(token)

    raw_username = payload.get("username") or payload.get("sub")
    if not raw_username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no contiene identificación de usuario válida",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = str(raw_username).strip().lower()

    # Evaluación de permisos en Portal
    admin_level = payload.get("adminLevel", 0)
    try:
        admin_level = int(admin_level)
    except (ValueError, TypeError):
        admin_level = 0

    is_super_admin = admin_level >= 2
    tool_access = payload.get("toolAccess") or {}
    tool_perm = str(tool_access.get("app-lti") or tool_access.get("app-lideres-ti") or "").strip().lower()

    has_operator = is_super_admin or (tool_perm == "operador")
    has_read = has_operator or (tool_perm == "lectura")

    if not (is_super_admin or has_read):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos asignados para acceder a App LTI en el Portal de Acceso"
        )

    # Aprovisionamiento Just-In-Time (JIT)
    full_name = payload.get("name") or payload.get("nombre") or username.replace(".", " ").title()
    default_rol = "ADMIN" if is_super_admin else "PM"
    user_email = payload.get("email") or payload.get("mail") or payload.get("correo")
    user = get_or_create_jit_user(
        username,
        nombre_completo=full_name,
        default_rol=default_rol,
        email=user_email
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al procesar el usuario en la base de datos"
        )

    # Validar estado activo en App LTI
    is_activo = user.get("activo") in (1, True, b'\x01')
    if not is_activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario desactivado en App LTI"
        )

    # Cálculo de Rol Efectivo
    # Si en el Portal tiene 'lectura' (y no es superadmin), se degrada forzosamente a PM
    if not is_super_admin and tool_perm == "lectura":
        effective_role = "PM"
    else:
        raw_rol = (user.get("rol") or "PM").upper()
        if is_super_admin and raw_rol == "PM":
            effective_role = "ADMIN"
        else:
            effective_role = raw_rol

    # Asignadores autorizados: pueden asignar LTI sin importar su rol (piso LTI)
    if username in LTI_ASSIGNER_USERNAMES and effective_role == "PM":
        effective_role = "LTI"

    return {
        "id": user["id"],
        "username": user["username"],
        "nombre_completo": user.get("nombre_completo") or username,
        "email": user.get("email") or user_email,
        "rol": effective_role,
        "raw_rol": user.get("rol"),
        "lt_asignado": user.get("lt_asignado"),
        "is_super_admin": is_super_admin,
        "portal_access": "operador" if has_operator else "lectura",
        "activo": 1
    }

def require_roles(allowed_roles: list[str]):
    def role_checker(current_user: dict = Depends(get_current_user)):
        user_role = (current_user.get("rol") or "").upper()
        allowed_upper = [r.upper() for r in allowed_roles]
        if user_role not in allowed_upper:
            if allowed_upper == ["ADMIN"]:
                detail_msg = "Permiso denegado. Se requiere rol de Administrador."
            elif "PM" not in allowed_upper:
                detail_msg = "Permiso denegado. Los usuarios con rol PM solo tienen acceso al módulo de Solicitud LTI."
            else:
                detail_msg = f"Permiso denegado. Se requiere uno de los siguientes roles: {', '.join(allowed_roles)}"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=detail_msg
            )
        return current_user
    return role_checker

require_admin = require_roles(["ADMIN"])
require_lti_or_admin = require_roles(["LTI", "ADMIN"])
require_non_pm = require_roles(["LTI", "ADMIN"])
