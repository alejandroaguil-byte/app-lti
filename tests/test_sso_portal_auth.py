"""
BATERÍA DE PRUEBAS AUTOMATIZADAS: SSO PORTAL DE ACCESO (v2.0.0)
Especificación: SPECS_INTEGRACION_SSO_PORTAL_ACCESO.md
Proyecto: App LTI - Seguimiento Líderes TI
"""

import time
import datetime
import jwt
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import PORTAL_JWT_SECRET, JWT_ALGORITHM
from backend.db import get_db_connection, get_usuario_by_username, get_or_create_jit_user
from tests.conftest import create_portal_jwt

client = TestClient(app)


def test_decode_portal_token_valid_cookie():
    """1. Validar decodificación exitosa de cookie access_token con JWT_ACCESS_SECRET."""
    token = create_portal_jwt(
        username="alejandro.aguilar",
        admin_level=2,
        tool_access={"app-lti": "operador"},
        name="Alejandro Aguilar"
    )
    client.cookies.set("access_token", token)
    response = client.get("/api/auth/me")
    assert response.status_code == 200, f"Error: {response.text}"
    data = response.json()
    assert data["username"] == "alejandro.aguilar"
    assert data["is_super_admin"] is True
    assert data["portal_access"] == "operador"
    assert data["rol"] == "ADMIN"
    client.cookies.clear()


def test_decode_portal_token_bearer_header_fallback():
    """2. Validar soporte de fallback por header Authorization: Bearer <token>."""
    token = create_portal_jwt(
        username="alejandro.aguilar",
        admin_level=2,
        tool_access={"app-lti": "operador"}
    )
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "alejandro.aguilar"


def test_reject_token_invalid_purpose():
    """3. Validar rechazo (401) cuando purpose != 'session'."""
    now = datetime.datetime.now(datetime.timezone.utc)
    invalid_payload = {
        "sub": 99,
        "username": "usuario.test",
        "purpose": "password-reset",
        "adminLevel": 0,
        "toolAccess": {"app-lti": "operador"},
        "iat": int(now.timestamp()),
        "exp": int((now + datetime.timedelta(hours=1)).timestamp())
    }
    bad_token = jwt.encode(invalid_payload, PORTAL_JWT_SECRET, algorithm=JWT_ALGORITHM)
    client.cookies.set("access_token", bad_token)
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert "no autorizado para sesión" in response.json()["detail"].lower()
    client.cookies.clear()


def test_reject_expired_token():
    """4. Validar rechazo (401) cuando el token ha expirado."""
    now = datetime.datetime.now(datetime.timezone.utc)
    expired_payload = {
        "sub": 99,
        "username": "usuario.expirado",
        "purpose": "session",
        "adminLevel": 0,
        "toolAccess": {"app-lti": "operador"},
        "iat": int((now - datetime.timedelta(hours=2)).timestamp()),
        "exp": int((now - datetime.timedelta(hours=1)).timestamp())
    }
    expired_token = jwt.encode(expired_payload, PORTAL_JWT_SECRET, algorithm=JWT_ALGORITHM)
    client.cookies.set("access_token", expired_token)
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert "ha expirado" in response.json()["detail"].lower()
    client.cookies.clear()


def test_reject_invalid_signature():
    """5. Validar rechazo (401) con firma secreta incorrecta."""
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": 99,
        "username": "hacker.user",
        "purpose": "session",
        "adminLevel": 2,
        "iat": int(now.timestamp()),
        "exp": int((now + datetime.timedelta(hours=1)).timestamp())
    }
    tampered_token = jwt.encode(payload, "clave-falsa-invalida-12345", algorithm=JWT_ALGORITHM)
    client.cookies.set("access_token", tampered_token)
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert "inválido" in response.json()["detail"].lower()
    client.cookies.clear()


def test_super_admin_without_tool_access():
    """6. Super Admin (adminLevel=2) tiene acceso total aún sin toolAccess en JWT."""
    token = create_portal_jwt(
        username="super.admin",
        admin_level=2,
        tool_access={},
        name="Super Admin Portal"
    )
    client.cookies.set("access_token", token)
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["is_super_admin"] is True
    assert data["rol"] == "ADMIN"
    client.cookies.clear()


def test_reject_user_without_tool_access_or_admin():
    """7. Usuario sin adminLevel 2 y sin toolAccess en App LTI recibe 403 Forbidden."""
    token = create_portal_jwt(
        username="usuario.sin.acceso",
        admin_level=0,
        tool_access={"otra-app": "operador"},
        name="Usuario Sin Acceso"
    )
    client.cookies.set("access_token", token)
    response = client.get("/api/auth/me")
    assert response.status_code == 403
    assert "no tienes permisos" in response.json()["detail"].lower()
    client.cookies.clear()


def test_downgrade_to_pm_with_tool_access_lectura():
    """8. Usuario con toolAccess='lectura' (y no superadmin) es degradado forzosamente a rol PM."""
    jit_u = get_or_create_jit_user("usuario.lectura", nombre_completo="Usuario Lectura", default_rol="ADMIN")
    
    token = create_portal_jwt(
        username="usuario.lectura",
        admin_level=0,
        tool_access={"app-lti": "lectura"},
        name="Usuario Lectura"
    )
    client.cookies.set("access_token", token)
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["portal_access"] == "lectura"
    assert data["rol"] == "PM", "El rol efectivo debe ser forzado a PM por permiso de solo lectura del Portal"
    client.cookies.clear()


def test_jit_user_provisioning():
    """9. Aprovisionamiento JIT de nuevo usuario del portal al ingresar por primera vez."""
    new_uname = f"jit.user.{int(time.time())}"
    token = create_portal_jwt(
        username=new_uname,
        admin_level=0,
        tool_access={"app-lti": "operador"},
        name="JIT Provisioned User"
    )
    client.cookies.set("access_token", token)
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == new_uname
    assert data["rol"] == "PM"

    user_db = get_usuario_by_username(new_uname)
    assert user_db is not None
    assert user_db["username"] == new_uname
    assert user_db["activo"] in (1, True, b'\x01')
    client.cookies.clear()


def test_reject_deactivated_user():
    """10. Rechazo (403) de usuario desactivado en base de datos local (activo=0)."""
    uname = f"user.bloqueado.{int(time.time())}"
    u = get_or_create_jit_user(uname, nombre_completo="Usuario Bloqueado", default_rol="PM")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE dbo.App_Usuarios SET activo = 0 WHERE id = %s", (u["id"],))
            conn.commit()
    finally:
        conn.close()

    token = create_portal_jwt(
        username=uname,
        admin_level=0,
        tool_access={"app-lti": "operador"}
    )
    client.cookies.set("access_token", token)
    response = client.get("/api/auth/me")
    assert response.status_code == 403
    assert "desactivado" in response.json()["detail"].lower()
    client.cookies.clear()


def test_update_usuario_without_password():
    """11. Actualizar rol y lt_asignado mediante PUT /api/usuarios/{id} sin requerir contraseña."""
    admin_token = create_portal_jwt(username="alejandro.aguilar", admin_level=2)
    client.cookies.set("access_token", admin_token)

    target_uname = f"target.user.{int(time.time())}"
    target = get_or_create_jit_user(target_uname, nombre_completo="Target User", default_rol="PM")

    update_payload = {
        "nombre_completo": "Target User Modificado",
        "rol": "LTI",
        "lt_asignado": "Alejandro Aguilar",
        "activo": True
    }
    response = client.put(f"/api/usuarios/{target['id']}", json=update_payload)
    assert response.status_code == 200, f"Error: {response.text}"
    updated_data = response.json()
    assert updated_data["rol"] == "LTI"
    assert updated_data["lt_asignado"] == "Alejandro Aguilar"
    assert updated_data["nombre_completo"] == "Target User Modificado"
    client.cookies.clear()


def test_retired_endpoints_return_404_or_405():
    """12. Los endpoints retirados de login y contraseñas ya no existen."""
    res_login = client.post("/api/auth/login", json={"username": "a", "password": "b"})
    assert res_login.status_code in (404, 405)

    res_cp = client.post("/api/auth/change-password", json={"current_password": "a", "new_password": "b"})
    assert res_cp.status_code in (404, 405)

    admin_token = create_portal_jwt(username="alejandro.aguilar", admin_level=2)
    client.cookies.set("access_token", admin_token)
    res_cu = client.post("/api/usuarios", json={"username": "nuevo", "nombre_completo": "Nuevo"})
    assert res_cu.status_code in (404, 405)

    res_rp = client.post("/api/usuarios/1/reset-password", json={})
    assert res_rp.status_code in (404, 405)
    client.cookies.clear()
