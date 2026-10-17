import os
import pytest
import datetime
import jwt
from playwright.sync_api import sync_playwright
from backend.db import get_db_connection
from backend.config import PORTAL_JWT_SECRET, JWT_ALGORITHM

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

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

# Todo N° de proyecto creado por las pruebas empieza con 'QA-' (el backend lo guarda como '000QA-'),
# lo que además evita que dispare correos (ver is_test_project_number en backend/email_service.py).
# La base de pruebas es la de producción: la limpieza nunca usa patrones sobre Cliente/Detalle.
TEST_PROJECT_PREFIXES = ("000QA-",)


def delete_test_projects(cursor, session_start_id) -> int:
    """Borra solo filas de prueba creadas en esta sesión (ID > inicio y prefijo de prueba).

    Sin ID de inicio de sesión no borra nada. Retorna la cantidad de filas borradas.
    """
    if session_start_id is None:
        return 0
    prefix_clause = " OR ".join(["Numero_Proyecto LIKE %s"] * len(TEST_PROJECT_PREFIXES))
    cursor.execute(
        f"DELETE FROM dbo.Proyectos WHERE ID > %s AND ({prefix_clause})",
        (session_start_id, *[f"{prefix}%" for prefix in TEST_PROJECT_PREFIXES]),
    )
    return cursor.rowcount


@pytest.fixture(scope="session")
def test_session_start_project_id():
    """MAX(ID) de dbo.Proyectos al iniciar la sesión; None si no se puede leer."""
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT ISNULL(MAX(ID), 0) AS max_id FROM dbo.Proyectos")
                return int(cursor.fetchone()["max_id"])
        finally:
            conn.close()
    except Exception as e:
        print(f"[CLEANUP WARNING] No se pudo leer el ID inicial; la limpieza de proyectos queda desactivada: {e}")
        return None


@pytest.fixture(autouse=True)
def isolate_email_redirect(monkeypatch):
    """Las pruebas en proceso validan el comportamiento productivo salvo que definan EMAIL_REDIRECT_TO.

    El .env de desarrollo define EMAIL_REDIRECT_TO; se quita del proceso de pytest (no del servidor).
    """
    monkeypatch.delenv("EMAIL_REDIRECT_TO", raising=False)


@pytest.fixture(autouse=True)
def clean_test_data(test_session_start_project_id):
    """Cleanup test records created during this test session only."""
    def _cleanup():
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                delete_test_projects(cursor, test_session_start_project_id)
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


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_tours: keep the guided module tours enabled (the default `page` fixture marks them as seen)",
    )


# Makes every guided-tour "seen" flag (halo_tour_*) read as true so the first-visit tours never
# cover the page in tests that are not about tours. Lives only in the test harness.
SUPPRESS_TOURS_INIT_SCRIPT = """
(() => {
  const originalGetItem = Storage.prototype.getItem;
  Storage.prototype.getItem = function (key) {
    if (typeof key === 'string' && key.indexOf('halo_tour_') === 0) return 'true';
    return originalGetItem.call(this, key);
  };
})();
"""


def suppress_tours(context):
    """Applies the tour-suppression init script to a browser context created outside the `page` fixture."""
    context.add_init_script(SUPPRESS_TOURS_INIT_SCRIPT)


@pytest.fixture(scope="function")
def page(request):
    """Playwright page fixture with isolated context (guided tours suppressed unless marked real_tours)."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        if request.node.get_closest_marker("real_tours") is None:
            suppress_tours(context)
        page = context.new_page()
        yield page
        context.close()
        browser.close()


# ---------------------------------------------------------------------------
# Navigation helpers (phase 1 UX): moved controls live in the user menu and
# in the per-row "⋯" menu, so tests open those menus before interacting.
# ---------------------------------------------------------------------------
def open_user_menu(page):
    """Opens the header user menu (theme, preferences, logout) if it is closed."""
    if not page.locator("#user-menu-dropdown").is_visible():
        page.locator("#user-menu-btn").click()
        page.locator("#user-menu-dropdown").wait_for(state="visible", timeout=5000)


def close_user_menu(page):
    if page.locator("#user-menu-dropdown").is_visible():
        page.keyboard.press("Escape")
        page.locator("#user-menu-dropdown").wait_for(state="hidden", timeout=5000)


def click_user_menu_control(page, selector: str):
    """Clicks a control inside the user menu (feature toggle or theme) and closes the menu."""
    open_user_menu(page)
    page.locator(f"#user-menu-dropdown {selector}").click()
    close_user_menu(page)


def open_project_row(row):
    """Opens the project detail by clicking the row (first cell)."""
    row.locator("td").first.click()


def click_row_action(page, row, action_class: str):
    """Opens the row "⋯" menu and clicks the action with the given class (e.g. btn-action-edit)."""
    row.locator(".btn-row-menu").click()
    page.locator(f"#row-actions-menu .{action_class}").click()
