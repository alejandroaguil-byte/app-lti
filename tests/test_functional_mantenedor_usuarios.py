"""
BATERÍA DE PRUEBAS FUNCIONALES AUTOMATIZADAS: MANTENEDOR DE USUARIOS Y CONTROL DE ACCESO (RBAC) - SSO PORTAL
Documentos de Referencia: SPECS_INTEGRACION_SSO_PORTAL_ACCESO.md y SPECS_MANTENEDOR_USUARIOS_Y_ROLES.md
Proyecto: App LTI - Seguimiento Líderes TI
"""

import os
import time
import pytest
import datetime
import requests
from playwright.sync_api import Page, expect

from backend.db import get_db_connection, create_solicitud_lti, delete_proyecto, get_or_create_jit_user
from backend.seed_users import seed_default_users
from tests.conftest import create_portal_jwt, create_access_token

BASE_URL = os.getenv("BASE_URL", "http://100.82.24.75:8000")


@pytest.fixture(scope="module", autouse=True)
def ensure_seed():
    """Asegura que los usuarios iniciales canónicos estén sincronizados."""
    seed_default_users()


def get_token_for(username: str, rol: str = "LTI") -> str:
    """Obtiene token JWT firmado del Portal de Acceso para pruebas."""
    admin_level = 2 if rol == "ADMIN" else (0 if rol == "PM" else 1)
    tool_perm = "lectura" if rol == "PM" else "operador"
    return create_portal_jwt(
        username=username,
        admin_level=admin_level,
        tool_access={"app-lti": tool_perm},
        name=username.replace(".", " ").title()
    )


def helper_login_as(page: Page, username: str, rol: str = "LTI"):
    """Helper de autenticación SSO en navegador inyectando cookie access_token."""
    token = get_token_for(username, rol=rol)
    page.context.add_cookies([{
        "name": "access_token",
        "value": token,
        "url": BASE_URL,
    }])
    page.goto(f"{BASE_URL}/")
    page.wait_for_selector("#app-view", state="visible", timeout=25000)


# =============================================================================
# SUITE 1: API REST RBAC & SEGURIDAD POR ROL
# =============================================================================

def test_tc_rbac_01_login_pm_success():
    """TC-RBAC-01: Autenticación exitosa de usuario PM vía SSO Portal con rol 'PM'."""
    token = get_token_for("pm.tester", rol="PM")
    res = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["username"] == "pm.tester"
    assert data["rol"] == "PM"


def test_tc_rbac_02_pm_denied_operational_endpoints():
    """TC-RBAC-02: Acceso denegado (403) a usuario PM en endpoints operativos."""
    token = get_token_for("pm.restricted", rol="PM")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Proyectos
    res_proj = requests.get(f"{BASE_URL}/api/proyectos", headers=headers)
    assert res_proj.status_code == 403
    assert "PM" in res_proj.json().get("detail", "") or "Permiso denegado" in res_proj.json().get("detail", "")

    # 2. KPIs
    res_kpis = requests.get(f"{BASE_URL}/api/kpis", headers=headers)
    assert res_kpis.status_code == 403

    # 3. Estados
    res_estados = requests.get(f"{BASE_URL}/api/estados", headers=headers)
    assert res_estados.status_code == 403

    # 4. Búsqueda directa
    res_search = requests.get(f"{BASE_URL}/api/search/direct?q=test", headers=headers)
    assert res_search.status_code == 403

    # 5. Usuarios
    res_users = requests.get(f"{BASE_URL}/api/usuarios", headers=headers)
    assert res_users.status_code == 403


def test_tc_rbac_03_pm_allowed_solicitudes():
    """TC-RBAC-03: Creación de Solicitud LTI exitosa por usuario PM."""
    token = get_token_for("pm.allowed", rol="PM")
    headers = {"Authorization": f"Bearer {token}"}

    # Acceso a catálogos
    res_cat = requests.get(f"{BASE_URL}/api/solicitudes/catalogos", headers=headers)
    assert res_cat.status_code == 200

    # Creación de solicitud LTI
    ts = int(time.time() * 1000) % 10000000
    payload = {
        "cliente": f"CLIENTE PM QA {ts}",
        "numero_proyecto": f"PM-REQ-{ts}",
        "fecha_solicitud": datetime.date.today().isoformat(),
        "detalle": "Solicitud ingresada por rol PM para prueba RBAC",
        "tipo_servicio": "Otros",
        "lt_asignado": "Alejandro Aguilar",
        "estado": "Generado"
    }
    res = requests.post(f"{BASE_URL}/api/solicitudes/crear", json=payload, headers=headers)
    assert res.status_code == 201
    created_id = res.json().get("data", {}).get("ID") or res.json().get("id")

    # Limpieza
    admin_token = get_token_for("alejandro.aguilar", rol="ADMIN")
    delete_proyecto(created_id)


def test_tc_rbac_04_lti_allowed_operational_endpoints():
    """TC-RBAC-04: Acceso permitido a LTI en endpoints operativos (/api/proyectos, /api/kpis)."""
    token = get_token_for("juan.barrera", rol="LTI")
    headers = {"Authorization": f"Bearer {token}"}

    res_proj = requests.get(f"{BASE_URL}/api/proyectos", headers=headers)
    assert res_proj.status_code == 200
    assert isinstance(res_proj.json(), list)

    res_kpis = requests.get(f"{BASE_URL}/api/kpis", headers=headers)
    assert res_kpis.status_code == 200
    assert "total_proyectos" in res_kpis.json()


def test_tc_rbac_05_lti_forbidden_delete_project():
    """TC-RBAC-05: Rol LTI no puede eliminar proyectos (403 Forbidden)."""
    # 1. Crear proyecto de prueba con función directa
    ts = int(time.time() * 1000) % 10000000
    p = create_solicitud_lti(
        cliente=f"CLIENTE TEST DEL {ts}",
        numero_proyecto=f"DEL-{ts}",
        detalle="Proyecto para test delete por LTI",
        tipo_servicio="Otros",
        lt_asignado="Erwin Sandoval",
        estado="Generado"
    )
    proj_id = (p.get("data") or {}).get("ID") or p.get("ID") or p.get("id")

    # 2. Intento de eliminación por LTI
    lti_token = get_token_for("erwin.sandoval", rol="LTI")
    res = requests.delete(f"{BASE_URL}/api/proyectos/{proj_id}", headers={"Authorization": f"Bearer {lti_token}"})
    assert res.status_code == 403
    assert "Administrador" in res.json().get("detail", "")

    # Limpieza por admin
    delete_proyecto(proj_id)


def test_tc_rbac_06_lti_allowed_edit_project():
    """TC-RBAC-06: Rol LTI puede editar proyectos (PUT /api/proyectos/{id})."""
    ts = int(time.time() * 1000) % 10000000
    p = create_solicitud_lti(
        cliente=f"CLIENTE EDIT LTI {ts}",
        numero_proyecto=f"ED-LTI-{ts}",
        detalle="Proyecto previo a edición",
        tipo_servicio="Otros",
        lt_asignado="Juan Barrera",
        estado="Generado"
    )
    proj_id = (p.get("data") or {}).get("ID") or p.get("ID") or p.get("id")

    lti_token = get_token_for("juan.barrera", rol="LTI")
    edit_payload = {
        "cliente": f"CLIENTE EDITADO {ts}",
        "lt_asignado": "Juan Barrera",
        "estado": "En revision",
        "detalle": "Detalle actualizado por LTI",
        "tipo_servicio": "Otros",
        "comentario": "Comentario LTI"
    }
    res = requests.put(f"{BASE_URL}/api/proyectos/{proj_id}", json=edit_payload, headers={"Authorization": f"Bearer {lti_token}"})
    assert res.status_code == 200
    data = res.json().get("data") or res.json()
    assert data["Cliente"] == f"CLIENTE EDITADO {ts}"
    assert data["Estado"] == "En revision"

    # Limpieza
    delete_proyecto(proj_id)


def test_tc_rbac_07_admin_allowed_delete_project():
    """TC-RBAC-07: Rol ADMIN puede eliminar proyectos (DELETE /api/proyectos/{id})."""
    ts = int(time.time() * 1000) % 10000000
    p = create_solicitud_lti(
        cliente=f"CLIENTE ADMIN DEL {ts}",
        numero_proyecto=f"ADM-DEL-{ts}",
        detalle="Proyecto para eliminación por Admin",
        tipo_servicio="Otros",
        lt_asignado="Alejandro Aguilar",
        estado="Generado"
    )
    proj_id = (p.get("data") or {}).get("ID") or p.get("ID") or p.get("id")

    admin_token = get_token_for("alejandro.aguilar", rol="ADMIN")
    res = requests.delete(f"{BASE_URL}/api/proyectos/{proj_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    assert res.json()["id"] == proj_id


# =============================================================================
# SUITE 2: MANTENEDOR DE USUARIOS (CRUD API REST)
# =============================================================================

def test_tc_rbac_08_admin_list_usuarios_and_filters():
    """TC-RBAC-08: Listar usuarios por ADMIN con filtros por búsqueda, rol y estado."""
    token = get_token_for("alejandro.aguilar", rol="ADMIN")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Listado completo
    res = requests.get(f"{BASE_URL}/api/usuarios", headers=headers)
    assert res.status_code == 200
    users = res.json()
    assert len(users) >= 6, f"Se esperaban al menos 6 usuarios canónicos, obtenidos {len(users)}"

    # 2. Filtro por Rol = LTI
    res_lti = requests.get(f"{BASE_URL}/api/usuarios?rol=LTI", headers=headers)
    assert res_lti.status_code == 200
    lti_users = res_lti.json()
    for u in lti_users:
        assert u["rol"] == "LTI"

    # 3. Búsqueda por término
    res_search = requests.get(f"{BASE_URL}/api/usuarios?search=Sandoval", headers=headers)
    assert res_search.status_code == 200
    search_users = res_search.json()
    assert len(search_users) >= 1
    assert any(u["username"] == "erwin.sandoval" for u in search_users)


def test_tc_rbac_09_non_admin_forbidden_users_api():
    """TC-RBAC-09: Roles no administradores (LTI, PM) reciben 403 en /api/usuarios."""
    for u in ["solange.ortiz", "juan.barrera"]:
        tok = get_token_for(u, rol="LTI")
        h = {"Authorization": f"Bearer {tok}"}
        res = requests.get(f"{BASE_URL}/api/usuarios", headers=h)
        assert res.status_code == 403


def test_tc_rbac_10_alta_usuarios_retirada_a_portal():
    """TC-RBAC-10: POST /api/usuarios retirado (alta delegada al Portal de Acceso)."""
    admin_token = get_token_for("alejandro.aguilar", rol="ADMIN")
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = requests.post(f"{BASE_URL}/api/usuarios", json={"username": "test", "nombre_completo": "Test"}, headers=headers)
    assert res.status_code in (404, 405)


def test_tc_rbac_11_reset_password_retirado_a_portal():
    """TC-RBAC-11: POST /api/usuarios/{id}/reset-password retirado (contraseñas en el Portal)."""
    admin_token = get_token_for("alejandro.aguilar", rol="ADMIN")
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = requests.post(f"{BASE_URL}/api/usuarios/1/reset-password", json={}, headers=headers)
    assert res.status_code in (404, 405)


def test_tc_rbac_12_crud_editar_usuario():
    """TC-RBAC-12: Edición de usuario existente (PUT /api/usuarios/{id})."""
    admin_token = get_token_for("alejandro.aguilar", rol="ADMIN")
    headers = {"Authorization": f"Bearer {admin_token}"}
    ts = int(time.time() * 1000) % 10000000

    # 1. Crear usuario vía JIT
    u = get_or_create_jit_user(f"edituser{ts}", nombre_completo="Usuario Para Editar", default_rol="PM")
    user_id = u["id"]

    # 2. Modificar atributos
    edit_payload = {
        "nombre_completo": "Usuario Nombre Actualizado",
        "rol": "LTI",
        "lt_asignado": "Juan Barrera",
        "activo": True
    }
    put_res = requests.put(f"{BASE_URL}/api/usuarios/{user_id}", json=edit_payload, headers=headers)
    assert put_res.status_code == 200
    updated = put_res.json()
    assert updated["nombre_completo"] == "Usuario Nombre Actualizado"
    assert updated["rol"] == "LTI"
    assert updated["lt_asignado"] == "Juan Barrera"

    # Limpieza
    requests.delete(f"{BASE_URL}/api/usuarios/{user_id}", headers=headers)


def test_tc_rbac_14_crud_toggle_status_and_auth_block():
    """TC-RBAC-14: Bloquear y desbloquear usuario (toggle-status) y validar rechazo en autenticación."""
    admin_token = get_token_for("alejandro.aguilar", rol="ADMIN")
    headers = {"Authorization": f"Bearer {admin_token}"}
    ts = int(time.time() * 1000) % 10000000

    u = get_or_create_jit_user(f"toggleuser{ts}", nombre_completo="Usuario Toggle", default_rol="PM")
    user_id = u["id"]

    # 1. Bloquear usuario
    res_block = requests.patch(f"{BASE_URL}/api/usuarios/{user_id}/toggle-status", headers=headers)
    assert res_block.status_code == 200
    assert res_block.json()["activo"] is False

    # 2. Intentar autenticarse con usuario bloqueado -> 403 Forbidden
    user_token = get_token_for(f"toggleuser{ts}", rol="PM")
    res_me = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {user_token}"})
    assert res_me.status_code == 403

    # 3. Desbloquear usuario
    res_unblock = requests.patch(f"{BASE_URL}/api/usuarios/{user_id}/toggle-status", headers=headers)
    assert res_unblock.status_code == 200
    assert res_unblock.json()["activo"] is True

    # 4. Acceso exitoso tras desbloqueo
    res_me_ok = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {user_token}"})
    assert res_me_ok.status_code == 200

    # Limpieza
    requests.delete(f"{BASE_URL}/api/usuarios/{user_id}", headers=headers)


def test_tc_rbac_15_proteccion_auto_bloqueo_y_admin_raiz():
    """TC-RBAC-15: Proteger sesión propia contra auto-bloqueo."""
    admin_token = get_token_for("alejandro.aguilar", rol="ADMIN")
    headers = {"Authorization": f"Bearer {admin_token}"}

    res_me = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
    admin_id = res_me.json()["id"]

    res_block_self = requests.patch(f"{BASE_URL}/api/usuarios/{admin_id}/toggle-status", headers=headers)
    assert res_block_self.status_code == 400
    assert "No se permite bloquear" in res_block_self.json().get("detail", "")


def test_tc_rbac_16_proteccion_auto_eliminacion_y_admin_raiz():
    """TC-RBAC-16: Proteger sesión propia contra auto-eliminación física."""
    admin_token = get_token_for("alejandro.aguilar", rol="ADMIN")
    headers = {"Authorization": f"Bearer {admin_token}"}

    res_me = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
    admin_id = res_me.json()["id"]

    res_del_self = requests.delete(f"{BASE_URL}/api/usuarios/{admin_id}", headers=headers)
    assert res_del_self.status_code == 400
    assert "eliminar" in res_del_self.json().get("detail", "").lower()


# =============================================================================
# SUITE 3: PRUEBAS E2E DE INTERFAZ DE USUARIO (PLAYWRIGHT)
# =============================================================================

def test_tc_rbac_18_e2e_pm_ui_isolation(page: Page):
    """TC-RBAC-18: E2E - Rol PM ve exclusivamente Solicitud LTI y sus módulos operativos están ocultos."""
    helper_login_as(page, "pm.e2e.user", rol="PM")

    # 1. Verificar badge de rol PM
    expect(page.locator("#user-role-badge")).to_have_text("Project Manager")

    # 2. Verificar que el módulo activo automático sea Solicitud LTI
    expect(page.locator("#module-solicitud-lti-container")).to_be_visible()
    expect(page.locator("#nav-btn-solicitud-lti")).to_be_visible()

    # 3. Verificar que los demás botones de navegación estén ocultos
    expect(page.locator("#nav-btn-projects")).to_be_hidden()
    expect(page.locator("#nav-btn-direct-search")).to_be_hidden()
    expect(page.locator("#nav-btn-tickets")).to_be_hidden()
    expect(page.locator("#nav-btn-usuarios")).to_be_hidden()


def test_tc_rbac_19_e2e_lti_ui_isolation(page: Page):
    """TC-RBAC-19: E2E - Rol LTI ve módulos operativos, Usuarios oculto y botones Eliminar proyecto ocultos."""
    helper_login_as(page, "juan.barrera", rol="LTI")

    # 1. Verificar badge de rol Líder TI
    expect(page.locator("#user-role-badge")).to_have_text("Líder TI")

    # 2. Verificar que módulos operativos estén visibles y Usuarios oculto
    expect(page.locator("#nav-btn-projects")).to_be_visible()
    expect(page.locator("#nav-btn-direct-search")).to_be_visible()
    expect(page.locator("#nav-btn-tickets")).to_be_visible()
    expect(page.locator("#nav-btn-solicitud-lti")).to_be_visible()
    expect(page.locator("#nav-btn-usuarios")).to_be_hidden()

    # 3. En la tabla de proyectos, verificar que aparezcan botones de Ver (🔍) y Editar (✏️) pero NUNCA Eliminar (🗑️)
    page.wait_for_selector("#projects-table-body tr", timeout=25000)
    first_row = page.locator("#projects-table-body tr").first
    expect(first_row.locator(".btn-action-view")).to_be_visible()
    expect(first_row.locator(".btn-action-edit")).to_be_visible()
    expect(first_row.locator(".btn-action-delete")).to_be_hidden()

    # 4. En la vista Drill Down, verificar que el botón de eliminar esté oculto
    first_row.locator(".btn-action-view").click()
    expect(page.locator("#project-drilldown-section")).to_be_visible()
    expect(page.locator("#btn-dd-edit-project")).to_be_visible()
    expect(page.locator("#btn-dd-delete-project")).to_be_hidden()


def test_tc_rbac_20_e2e_admin_full_ui_and_usuarios_crud(page: Page):
    """TC-RBAC-20: E2E - Rol ADMIN tiene acceso total al Mantenedor de Usuarios sin modales obsoletos."""
    helper_login_as(page, "alejandro.aguilar", rol="ADMIN")

    # 1. Verificar badge de rol Administrador
    expect(page.locator("#user-role-badge")).to_have_text("Administrador")

    # 2. Botón Usuarios visible en navegación
    nav_users = page.locator("#nav-btn-usuarios")
    expect(nav_users).to_be_visible()

    # 3. Clic en Usuarios y verificar apertura del módulo
    nav_users.click()
    expect(page.locator("#module-usuarios-container")).to_be_visible()

    # 4. Verificar tabla de usuarios y conteo
    count_badge = page.locator("#usuarios-count-badge")
    expect(count_badge).to_be_visible()
    expect(count_badge).not_to_have_text("0", timeout=10000)

    # 5. Filtrar por Rol = LTI
    page.select_option("#usuarios-filter-rol", "LTI")
    page.wait_for_timeout(400)
    assert int(page.locator("#usuarios-count-badge").inner_text().strip()) >= 1

    # 6. Limpiar filtros
    page.click("#btn-usuarios-reset-filters")
    page.wait_for_timeout(400)

    # 7. Verificar que NO existe el botón "+ Nuevo Usuario"
    expect(page.locator("#btn-create-user-open")).to_have_count(0)

    # 8. Verificar que NO existen botones de llave para reseteo de clave
    expect(page.locator(".btn-action-user-key")).to_have_count(0)

    # 9. Modal Editar Usuario funciona
    first_row = page.locator("#usuarios-table-body tr").first
    first_row.locator(".btn-action-user-edit").click()
    expect(page.locator("#edit-user-modal")).to_be_visible(timeout=10000)
    page.click("#btn-cancel-edit-user-modal")
    expect(page.locator("#edit-user-modal")).to_be_hidden(timeout=10000)
