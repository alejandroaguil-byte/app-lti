import os
import pytest
import datetime
import jwt
from playwright.sync_api import sync_playwright
from backend.db import get_db_connection
from backend.config import PORTAL_JWT_SECRET, JWT_ALGORITHM

BASE_URL = os.getenv("BASE_URL", "http://100.82.24.75:8000")

def create_portal_jwt(
    username: str = "alejandro.aguilar",
    admin_level: int = 2,
    tool_access: dict = None,
    name: str = "Alejandro Aguilar",
    purpose: str = "session",
    expires_in_hours: int = 1
) -> str:
    """Genera un JWT firmado con PORTAL_JWT_SECRET simulando el Portal de Acceso."""
    if tool_access is None:
        tool_access = {"app-lti": "operador"}
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": 15,
        "username": username,
        "email": f"{username}@clarovtr.cl",
        "name": name,
        "adminLevel": admin_level,
        "purpose": purpose,
        "toolAccess": tool_access,
        "iat": int(now.timestamp()),
        "exp": int((now + datetime.timedelta(hours=expires_in_hours)).timestamp())
    }
    return jwt.encode(payload, PORTAL_JWT_SECRET, algorithm=JWT_ALGORITHM)

def create_access_token(data: dict) -> str:
    """Helper para tests existentes: genera un token compatible con SSO Portal de Acceso."""
    username = str(data.get("username") or data.get("sub") or "alejandro.aguilar").lower()
    rol = (data.get("rol") or "ADMIN").upper()
    admin_level = 2 if rol == "ADMIN" else (0 if rol == "PM" else 1)
    tool_perm = "operador" if rol in ("ADMIN", "LTI") else "lectura"
    tool_access = data.get("toolAccess") or {"app-lti": tool_perm}
    name = data.get("nombre_completo") or username.replace(".", " ").title()
    purpose = data.get("purpose", "session")
    return create_portal_jwt(
        username=username,
        admin_level=admin_level,
        tool_access=tool_access,
        name=name,
        purpose=purpose
    )

@pytest.fixture(scope="session")
def base_url():
    return BASE_URL

@pytest.fixture(scope="session")
def auth_token():
    """Generates an authentication token for test user alejandro.aguilar."""
    return create_portal_jwt(username="alejandro.aguilar", admin_level=2, name="Alejandro Aguilar")

@pytest.fixture(autouse=True)
def clean_test_data():
    """Cleanup any test records created during test runs."""
    def _cleanup():
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM dbo.Proyectos 
                    WHERE Numero_Proyecto LIKE '%QA%' 
                       OR Numero_Proyecto LIKE '%TEST%'
                       OR Numero_Proyecto LIKE '%DUP%'
                       OR Cliente LIKE '%PRUEBA QA%' 
                       OR Cliente LIKE '%INMUTABILIDAD%'
                       OR Cliente LIKE '%MODIFICADO%' 
                       OR Cliente LIKE '%DRILLDOWN%' 
                       OR Detalle LIKE '%Prueba E2E Automatizada%'
                       OR Detalle LIKE '%QA%'
                       OR Detalle LIKE '%inmutabilidad%'
                       OR Detalle LIKE '%anti-duplicado%'
                """)
                cursor.execute("""
                    DELETE FROM dbo.App_Usuarios 
                    WHERE username LIKE 'e2euser%' 
                       OR username LIKE 'testuser%'
                       OR username LIKE 'testdbg%'
                """)
                conn.commit()
        except Exception as e:
            print(f"[CLEANUP WARNING] Error cleaning test data: {e}")
        finally:
            conn.close()

    yield
    _cleanup()

@pytest.fixture(scope="function")
def page():
    """Playwright page fixture with isolated context."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        yield page
        context.close()
        browser.close()
