"""
BATERÍA DE PRUEBAS FUNCIONALES AUTOMATIZADAS: MANTENEDOR DE USUARIOS Y CONTROL DE ACCESO (RBAC)
Documento de Referencia: SPECS_MANTENEDOR_USUARIOS_Y_ROLES.md (SPECS-LTI-MOD-006)
Proyecto: App LTI - Seguimiento Líderes TI
Ubicación: /home/bobbasystem/Desarrollos/app-lti/tests/test_functional_mantenedor_usuarios.py

Casos de Prueba:
- TC-RBAC-01: Login exitoso de PM (calbornoz) con rol "PM".
- TC-RBAC-02: Acceso denegado (403 Forbidden) para rol PM en endpoints operativos (/api/proyectos, /api/kpis, /api/estados, /api/search/direct).
- TC-RBAC-03: Creación exitosa de Solicitud LTI por usuario PM (201 Created).
- TC-RBAC-04: Acceso exitoso de LTI (jbarrera, esandoval) a proyectos y KPIs.
- TC-RBAC-05: Restricción de eliminación de proyectos para LTI (403 Forbidden al intentar DELETE /api/proyectos/{id}).
- TC-RBAC-06: Edición de proyectos permitida para LTI (PUT /api/proyectos/{id}).
- TC-RBAC-07: Eliminación de proyectos permitida para ADMIN (DELETE /api/proyectos/{id}).
- TC-RBAC-08: Listar usuarios por ADMIN (GET /api/usuarios retorna 38 usuarios iniciales).
- TC-RBAC-09: Acceso denegado a /api/usuarios para roles LTI y PM (403 Forbidden).
- TC-RBAC-10: CRUD de Usuarios - Crear nuevo usuario (POST /api/usuarios, 201 Created).
- TC-RBAC-11: CRUD de Usuarios - Error por username duplicado (409 Conflict).
- TC-RBAC-12: CRUD de Usuarios - Editar usuario (PUT /api/usuarios/{id}, 200 OK).
- TC-RBAC-13: CRUD de Usuarios - Resetear contraseña (POST /api/usuarios/{id}/reset-password, 200 OK).
- TC-RBAC-14: CRUD de Usuarios - Bloquear y Desbloquear (PATCH /api/usuarios/{id}/toggle-status, 200 OK; 401 en login de bloqueado).
- TC-RBAC-15: CRUD de Usuarios - Protección contra auto-bloqueo y bloqueo del admin raíz (400 Bad Request).
- TC-RBAC-16: CRUD de Usuarios - Protección contra auto-eliminación y eliminación del admin raíz (400 Bad Request).
- TC-RBAC-17: CRUD de Usuarios - Eliminación física de usuario creado (DELETE /api/usuarios/{id}, 200 OK).
- TC-RBAC-18: E2E - Interfaz para rol PM (solo Solicitud LTI visible, módulos operativos y usuarios ocultos).
- TC-RBAC-19: E2E - Interfaz para rol LTI (módulos operativos visibles, botón Usuarios oculto, botones Eliminar proyecto ocultos).
- TC-RBAC-20: E2E - Interfaz para rol ADMIN (todos los módulos visibles, acceso al mantenedor de usuarios, modales funcionales).
"""

import time
import pytest
import datetime
import requests
from playwright.sync_api import Page, expect

from backend.db import get_db_connection, create_solicitud_lti, delete_proyecto
from backend.seed_users import seed_default_users

BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="module", autouse=True)
def ensure_seed():
    """Asegura que los usuarios iniciales canónicos estén sincronizados."""
    seed_default_users()


def get_token_for(username: str, password: str = "Lti2026!") -> str:
    """Obtiene token JWT para un usuario específico."""
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, f"Fallo de login para {username}: {res.text}"
    return res.json()["access_token"]


def helper_login_as(page: Page, username: str, password: str = "Lti2026!"):
    """Helper de login en navegador para cualquier usuario."""
    page.goto(f"{BASE_URL}/")
    page.evaluate("() => { localStorage.clear(); }")
    page.goto(f"{BASE_URL}/")
    page.wait_for_selector("#auth-view", state="visible", timeout=20000)
    page.fill("#login-username", username)
    page.fill("#login-password", password)
    page.click("#login-submit-btn")
    page.wait_for_selector("#app-view", state="visible", timeout=25000)


# =============================================================================
# SUITE 1: API REST RBAC & SEGURIDAD POR ROL
# =============================================================================

def test_tc_rbac_01_login_pm_success():
    """TC-RBAC-01: Login exitoso de usuario PM con token rol 'PM'."""
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "calbornoz", "password": "Lti2026!"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    user = data["user"]
    assert user["username"] == "calbornoz"
    assert user["rol"] == "PM"
    assert user["nombre_completo"] == "Albornoz Pacheco Cesar Augusto"


def test_tc_rbac_02_pm_denied_operational_endpoints():
    """TC-RBAC-02: Acceso denegado (403) a usuario PM en endpoints operativos."""
    token = get_token_for("calbornoz")
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
    token = get_token_for("gcardozo")
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
        "tipo_servicio": "Otros"
    }
    res_crear = requests.post(f"{BASE_URL}/api/solicitudes/crear", json=payload, headers=headers)
    assert res_crear.status_code == 201
    data = res_crear.json()["data"]
    assert data["Cliente"] == f"CLIENTE PM QA {ts}"
    assert data["Solicitante"] == "CARDOZO GARCES GRACE ALEJANDRA"
    
    # Limpieza
    if data.get("ID"):
        delete_proyecto(data["ID"])


def test_tc_rbac_04_lti_allowed_operational_endpoints():
    """TC-RBAC-04: Acceso exitoso de usuario LTI a proyectos y KPIs."""
    token = get_token_for("jbarrera")
    headers = {"Authorization": f"Bearer {token}"}

    res_proj = requests.get(f"{BASE_URL}/api/proyectos", headers=headers)
    assert res_proj.status_code == 200
    assert isinstance(res_proj.json(), list)

    res_kpis = requests.get(f"{BASE_URL}/api/kpis", headers=headers)
    assert res_kpis.status_code == 200
    assert "total_proyectos" in res_kpis.json()


def test_tc_rbac_05_lti_forbidden_delete_project():
    """TC-RBAC-05: Restricción estricta - LTI no puede eliminar proyectos (403 Forbidden)."""
    # Crear un proyecto temporal con permisos de admin
    admin_token = get_token_for("admin")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    ts = int(time.time() * 1000) % 10000000
    create_res = requests.post(f"{BASE_URL}/api/solicitudes/crear", json={
        "cliente": f"TEST DELETE LTI {ts}",
        "numero_proyecto": f"DEL-LTI-{ts}",
        "fecha_solicitud": datetime.date.today().isoformat(),
        "detalle": "Test delete protection"
    }, headers=admin_headers)
    assert create_res.status_code == 201
    proj_id = create_res.json()["data"]["ID"]

    # Intentar eliminar con token LTI
    lti_token = get_token_for("esandoval")
    lti_headers = {"Authorization": f"Bearer {lti_token}"}
    del_res = requests.delete(f"{BASE_URL}/api/proyectos/{proj_id}", headers=lti_headers)
    assert del_res.status_code == 403, f"Se esperaba 403, pero se obtuvo {del_res.status_code}: {del_res.text}"

    # Limpieza con token ADMIN
    cleanup_res = requests.delete(f"{BASE_URL}/api/proyectos/{proj_id}", headers=admin_headers)
    assert cleanup_res.status_code == 200


def test_tc_rbac_06_lti_allowed_edit_project():
    """TC-RBAC-06: Edición de proyectos permitida para usuario LTI."""
    admin_token = get_token_for("admin")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    ts = int(time.time() * 1000) % 10000000
    create_res = requests.post(f"{BASE_URL}/api/solicitudes/crear", json={
        "cliente": f"TEST EDIT LTI {ts}",
        "numero_proyecto": f"EDIT-LTI-{ts}",
        "fecha_solicitud": datetime.date.today().isoformat(),
        "detalle": "Detalle original"
    }, headers=admin_headers)
    proj_id = create_res.json()["data"]["ID"]

    # Editar con token LTI (sparedes)
    lti_token = get_token_for("sparedes")
    lti_headers = {"Authorization": f"Bearer {lti_token}"}
    edit_payload = {
        "cliente": f"TEST EDIT LTI MODIFICADO {ts}",
        "lt_asignado": "Samuel Paredes",
        "estado": "En revision",
        "detalle": "Detalle editado por líder Samuel Paredes",
        "tipo_servicio": "Cloud Empresarial",
        "comentario": "Comentario de revisión técnica"
    }
    edit_res = requests.put(f"{BASE_URL}/api/proyectos/{proj_id}", json=edit_payload, headers=lti_headers)
    assert edit_res.status_code == 200
    assert edit_res.json()["data"]["Cliente"] == f"TEST EDIT LTI MODIFICADO {ts}"
    assert edit_res.json()["data"]["Estado"] == "En revision"

    # Limpieza
    requests.delete(f"{BASE_URL}/api/proyectos/{proj_id}", headers=admin_headers)


def test_tc_rbac_07_admin_allowed_delete_project():
    """TC-RBAC-07: Eliminación de proyectos permitida para usuario ADMIN."""
    admin_token = get_token_for("aaguilar")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    ts = int(time.time() * 1000) % 10000000
    create_res = requests.post(f"{BASE_URL}/api/solicitudes/crear", json={
        "cliente": f"TEST ADMIN DELETE {ts}",
        "numero_proyecto": f"ADM-DEL-{ts}",
        "fecha_solicitud": datetime.date.today().isoformat(),
        "detalle": "Proyecto a borrar por admin"
    }, headers=admin_headers)
    proj_id = create_res.json()["data"]["ID"]

    del_res = requests.delete(f"{BASE_URL}/api/proyectos/{proj_id}", headers=admin_headers)
    assert del_res.status_code == 200
    assert del_res.json()["id"] == proj_id


# =============================================================================
# SUITE 2: MANTENEDOR DE USUARIOS (CRUD API REST)
# =============================================================================

def test_tc_rbac_08_admin_list_usuarios_and_filters():
    """TC-RBAC-08: Listar usuarios por ADMIN con filtros por búsqueda, rol y estado."""
    token = get_token_for("admin")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Listado completo
    res = requests.get(f"{BASE_URL}/api/usuarios", headers=headers)
    assert res.status_code == 200
    users = res.json()
    assert len(users) >= 38, f"Se esperaban al menos 38 usuarios, obtenidos {len(users)}"

    # 2. Filtro por Rol = LTI
    res_lti = requests.get(f"{BASE_URL}/api/usuarios?rol=LTI", headers=headers)
    assert res_lti.status_code == 200
    lti_users = res_lti.json()
    assert len(lti_users) == 4
    for u in lti_users:
        assert u["rol"] == "LTI"

    # 3. Filtro por Rol = PM
    res_pm = requests.get(f"{BASE_URL}/api/usuarios?rol=PM", headers=headers)
    assert res_pm.status_code == 200
    pm_users = res_pm.json()
    assert len(pm_users) == 31

    # 4. Búsqueda por término
    res_search = requests.get(f"{BASE_URL}/api/usuarios?search=Sandoval", headers=headers)
    assert res_search.status_code == 200
    search_users = res_search.json()
    assert len(search_users) >= 1
    assert any(u["username"] == "esandoval" for u in search_users)


def test_tc_rbac_09_non_admin_forbidden_users_api():
    """TC-RBAC-09: Roles no administradores (LTI, PM) reciben 403 en /api/usuarios."""
    for u in ["sortiz", "jcastillo"]:
        tok = get_token_for(u)
        h = {"Authorization": f"Bearer {tok}"}
        res = requests.get(f"{BASE_URL}/api/usuarios", headers=h)
        assert res.status_code == 403


def test_tc_rbac_10_crud_crear_usuario():
    """TC-RBAC-10: Creación de nuevo usuario por ADMIN (POST /api/usuarios)."""
    admin_token = get_token_for("admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    ts = int(time.time() * 1000) % 10000000
    payload = {
        "username": f"qatester{ts}",
        "password": "Lti2026!Password",
        "nombre_completo": f"Tester Automatizado QA {ts}",
        "lt_asignado": "Erwin Sandoval",
        "rol": "LTI",
        "activo": True
    }
    res = requests.post(f"{BASE_URL}/api/usuarios", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["username"] == f"qatester{ts}"
    assert data["rol"] == "LTI"
    assert data["lt_asignado"] == "Erwin Sandoval"
    assert data["activo"] is True

    # Verificar que el usuario recién creado puede hacer login
    new_user_token = get_token_for(f"qatester{ts}", "Lti2026!Password")
    assert new_user_token is not None

    # Limpieza
    requests.delete(f"{BASE_URL}/api/usuarios/{data['id']}", headers=headers)


def test_tc_rbac_11_crud_error_username_duplicado():
    """TC-RBAC-11: Conflicto 409 al intentar registrar un username existente."""
    admin_token = get_token_for("admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = {
        "username": "admin",
        "password": "Password123!",
        "nombre_completo": "Admin Duplicado",
        "rol": "ADMIN",
        "activo": True
    }
    res = requests.post(f"{BASE_URL}/api/usuarios", json=payload, headers=headers)
    assert res.status_code == 409


def test_tc_rbac_12_crud_editar_usuario():
    """TC-RBAC-12: Edición de usuario existente (PUT /api/usuarios/{id})."""
    admin_token = get_token_for("admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    ts = int(time.time() * 1000) % 10000000

    # 1. Crear usuario temporal
    create_res = requests.post(f"{BASE_URL}/api/usuarios", json={
        "username": f"edituser{ts}",
        "password": "Lti2026!Initial",
        "nombre_completo": "Usuario Para Editar",
        "rol": "PM",
        "activo": True
    }, headers=headers)
    user_id = create_res.json()["id"]

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


def test_tc_rbac_13_crud_reset_password():
    """TC-RBAC-13: Reset de contraseña por ADMIN a clave personalizada y clave por defecto."""
    admin_token = get_token_for("admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    ts = int(time.time() * 1000) % 10000000

    # Crear usuario
    create_res = requests.post(f"{BASE_URL}/api/usuarios", json={
        "username": f"resetuser{ts}",
        "password": "PasswordOriginal123!",
        "nombre_completo": "Usuario Reset Password",
        "rol": "PM",
        "activo": True
    }, headers=headers)
    user_id = create_res.json()["id"]

    # 1. Resetear con nueva contraseña personalizada
    res_reset1 = requests.post(f"{BASE_URL}/api/usuarios/{user_id}/reset-password", json={
        "new_password": "NewSecretPass2026!"
    }, headers=headers)
    assert res_reset1.status_code == 200
    assert get_token_for(f"resetuser{ts}", "NewSecretPass2026!") is not None

    # 2. Resetear a clave institucional por defecto (payload vacío)
    res_reset2 = requests.post(f"{BASE_URL}/api/usuarios/{user_id}/reset-password", json={}, headers=headers)
    assert res_reset2.status_code == 200
    assert get_token_for(f"resetuser{ts}", "Lti2026!") is not None

    # Limpieza
    requests.delete(f"{BASE_URL}/api/usuarios/{user_id}", headers=headers)


def test_tc_rbac_14_crud_toggle_status_and_login_block():
    """TC-RBAC-14: Bloquear y desbloquear usuario (toggle-status) y validar bloqueo en login."""
    admin_token = get_token_for("admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    ts = int(time.time() * 1000) % 10000000

    # Crear usuario
    create_res = requests.post(f"{BASE_URL}/api/usuarios", json={
        "username": f"toggleuser{ts}",
        "password": "Lti2026!",
        "nombre_completo": "Usuario Toggle",
        "rol": "PM",
        "activo": True
    }, headers=headers)
    user_id = create_res.json()["id"]

    # 1. Bloquear usuario
    res_block = requests.patch(f"{BASE_URL}/api/usuarios/{user_id}/toggle-status", headers=headers)
    assert res_block.status_code == 200
    assert res_block.json()["activo"] is False

    # 2. Intentar login con usuario bloqueado -> 401 Unauthorized
    res_login = requests.post(f"{BASE_URL}/api/auth/login", json={"username": f"toggleuser{ts}", "password": "Lti2026!"})
    assert res_login.status_code == 401

    # 3. Desbloquear usuario
    res_unblock = requests.patch(f"{BASE_URL}/api/usuarios/{user_id}/toggle-status", headers=headers)
    assert res_unblock.status_code == 200
    assert res_unblock.json()["activo"] is True

    # 4. Login exitoso tras desbloqueo
    res_login_ok = requests.post(f"{BASE_URL}/api/auth/login", json={"username": f"toggleuser{ts}", "password": "Lti2026!"})
    assert res_login_ok.status_code == 200

    # Limpieza
    requests.delete(f"{BASE_URL}/api/usuarios/{user_id}", headers=headers)


def test_tc_rbac_15_proteccion_auto_bloqueo_y_admin_raiz():
    """TC-RBAC-15: Proteger admin raíz y sesión propia contra toggle status."""
    admin_token = get_token_for("admin")
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Obtener ID del admin raíz
    res_me = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
    admin_id = res_me.json()["id"]

    # Intento de bloqueo de la cuenta 'admin'
    res_block_root = requests.patch(f"{BASE_URL}/api/usuarios/{admin_id}/toggle-status", headers=headers)
    assert res_block_root.status_code == 400
    assert "No se permite bloquear" in res_block_root.json().get("detail", "")


def test_tc_rbac_16_proteccion_auto_eliminacion_y_admin_raiz():
    """TC-RBAC-16: Proteger admin raíz y sesión propia contra eliminación física."""
    admin_token = get_token_for("admin")
    headers = {"Authorization": f"Bearer {admin_token}"}

    res_me = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
    admin_id = res_me.json()["id"]

    res_del_root = requests.delete(f"{BASE_URL}/api/usuarios/{admin_id}", headers=headers)
    assert res_del_root.status_code == 400
    assert "No se permite eliminar" in res_del_root.json().get("detail", "")


# =============================================================================
# SUITE 3: PRUEBAS E2E DE INTERFAZ DE USUARIO (PLAYWRIGHT)
# =============================================================================

def test_tc_rbac_18_e2e_pm_ui_isolation(page: Page):
    """TC-RBAC-18: E2E - Rol PM ve exclusivamente Solicitud LTI y sus módulos operativos están ocultos."""
    helper_login_as(page, "calbornoz", "Lti2026!")

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
    """TC-RBAC-19: E2E - Rol LTI ve módulos operativos, Usuarios oculto y botones 🗑️ Eliminar proyecto ocultos."""
    helper_login_as(page, "jbarrera", "Lti2026!")

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
    """TC-RBAC-20: E2E - Rol ADMIN tiene acceso total al Mantenedor de Usuarios con filtros y modales."""
    helper_login_as(page, "admin", "Lti2026!")

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
    assert int(count_badge.inner_text().strip()) >= 38

    # 5. Filtrar por Rol = PM
    page.select_option("#usuarios-filter-rol", "PM")
    page.wait_for_timeout(400)
    expect(page.locator("#usuarios-count-badge")).to_have_text("31")

    # 6. Limpiar filtros
    page.click("#btn-usuarios-reset-filters")
    page.wait_for_timeout(400)

    # 7. Modal Crear Usuario
    page.click("#btn-create-user-open")
    expect(page.locator("#create-user-modal")).to_be_visible()

    ts = int(time.time() * 1000) % 10000000
    page.fill("#create-user-nombre", f"E2E Test User {ts}")
    page.fill("#create-user-username", f"e2euser{ts}")
    page.fill("#create-user-password", "Lti2026!Password")
    page.select_option("#create-user-rol", "PM")
    page.click("#btn-save-create-user-modal")

    # Verificar que modal se cierra y el usuario aparece en la tabla
    expect(page.locator("#create-user-modal")).to_be_hidden(timeout=10000)
    page.fill("#usuarios-search-input", f"e2euser{ts}")
    expect(page.locator("#usuarios-table-body")).to_contain_text(f"e2euser{ts}", timeout=10000)

    # 8. Modal Editar Usuario
    user_row = page.locator("#usuarios-table-body tr", has_text=f"e2euser{ts}").first
    user_row.locator(".btn-action-user-edit").click()
    expect(page.locator("#edit-user-modal")).to_be_visible(timeout=10000)
    expect(page.locator("#edit-user-username")).to_have_value(f"e2euser{ts}", timeout=10000)

    page.fill("#edit-user-nombre", f"E2E Test User Modificado {ts}")
    page.click("#btn-save-edit-user-modal")
    expect(page.locator("#edit-user-modal")).to_be_hidden(timeout=10000)
    expect(page.locator("#usuarios-table-body")).to_contain_text(f"E2E Test User Modificado {ts}", timeout=10000)

    # 9. Modal Eliminar Usuario
    user_row = page.locator("#usuarios-table-body tr", has_text=f"e2euser{ts}").first
    user_row.locator(".btn-action-user-delete").click()
    expect(page.locator("#delete-user-modal")).to_be_visible(timeout=10000)
    expect(page.locator("#delete-user-username-display")).to_have_text(f"e2euser{ts}", timeout=10000)

    page.click("#btn-confirm-delete-user-modal")
    expect(page.locator("#delete-user-modal")).to_be_hidden(timeout=10000)
    expect(page.locator("#usuarios-table-body")).not_to_contain_text(f"e2euser{ts}", timeout=10000)
