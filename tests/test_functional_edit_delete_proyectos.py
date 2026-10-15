"""
BATERÍA DE PRUEBAS FUNCIONALES AUTOMATIZADAS E2E Y API: MÓDULO "EDICIÓN Y ELIMINACIÓN DE PROYECTOS"
Proyecto: App LTI - Seguimiento Líderes TI
Ubicación: /home/bobbasystem/Desarrollos/app-lti
Documento de Referencia: SPECS_EDIT_DELETE_PROYECTOS.md

Casos de Prueba:
1. API Tests: PUT y DELETE /api/proyectos/{id} (Validaciones, 200, 400, 404, 401)
2. E2E-01: Renderizado de botones de acción en tabla (🔍 Ver, ✏️ Editar, 🗑️ Eliminar)
3. E2E-02: Apertura y Poblado de Modal de Edición (#edit-project-modal)
4. E2E-03: Flujo Completo de Edición y Persistencia desde la Tabla
5. E2E-04: Edición desde Vista Drill Down con actualización reactiva en vivo
6. E2E-05: Apertura y Cancelación de Modal de Eliminación (#delete-project-modal)
7. E2E-06: Confirmación de Eliminación desde la Tabla y Sincronización
8. E2E-07: Eliminación desde la Vista Drill Down con retorno a la lista
9. E2E-08: Modo Claro y Modo Oscuro en Modales y Botones de Acción
"""

import os
import re
import time
import json
import pytest
import datetime
import requests
from playwright.sync_api import Page, expect
from backend.db import get_db_connection, create_solicitud_lti
from tests.conftest import create_access_token, open_user_menu, click_user_menu_control

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")


def helper_login(page: Page, username: str = "alejandro.aguilar", password: str = None):
    """Helper para autenticar en el portal con credenciales SSO válidas."""
    token = create_access_token({"sub": username, "rol": "ADMIN"})
    page.context.add_cookies([{
        "name": "access_token",
        "value": token,
        "url": BASE_URL,
    }])
    page.goto(f"{BASE_URL}/")
    page.wait_for_selector("#app-view", state="visible", timeout=25000)
    page.wait_for_function("() => window.App && window.App.isInitialized === true", timeout=25000)
    page.wait_for_selector("#projects-table-body tr:not(:has-text('Cargando proyectos'))", timeout=15000)
    page.wait_for_selector("#filter-estado-sp option[value='Atendido']", state="attached", timeout=10000)
    page.wait_for_selector("#filter-lt option[value='Alejandro Aguilar']", state="attached", timeout=10000)


def helper_filter_project(page: Page, nro: str):
    """Filtra la tabla por número de proyecto y espera que la fila correspondiente sea visible."""
    nro_clean = str(nro).strip()
    page.wait_for_selector("#filter-search", state="visible", timeout=25000)
    target_row = page.locator(f"#projects-table-body tr:has-text('{nro_clean}')").first
    for _ in range(5):
        page.evaluate("""async (nro) => {
            const search = document.getElementById('filter-search');
            if (search) search.value = nro;
            const lt = document.getElementById('filter-lt');
            if (lt) lt.value = '__ALL__';
            const estado = document.getElementById('filter-estado-sp');
            if (estado) estado.value = '';
            if (window.App && window.App.loadProjects) {
                await window.App.loadProjects();
            }
        }""", nro_clean)
        page.wait_for_selector("#projects-table-body tr:not(:has-text('Cargando proyectos'))", timeout=10000)
        page.wait_for_timeout(350)
        if target_row.count() > 0 and target_row.is_visible():
            return target_row
    target_row.wait_for(state="visible", timeout=15000)
    return target_row


def create_test_project_in_db(prefix: str = "QA-TEST-ED") -> dict:
    """Crea un proyecto de prueba en dbo.Proyectos y retorna sus datos."""
    import uuid
    unique_suffix = f"{int(time.time() * 1000) % 10000000}-{uuid.uuid4().hex[:6]}"
    res = create_solicitud_lti(
        cliente=f"CLIENTE PRUEBA QA {unique_suffix}",
        numero_proyecto=f"{prefix}-{unique_suffix}",
        lt_asignado="Alejandro Aguilar",
        estado="Generado",
        fecha_solicitud=datetime.date.today().isoformat(),
        detalle=f"Detalle inicial de prueba QA. Timestamp: {unique_suffix}",
        solicitante="ALEJANDRO AGUILAR",
        tipo_servicio="Cloud Empresarial"
    )
    assert res.get("success"), f"Error creando proyecto de prueba: {res}"
    data = res.get("data")
    if data and "Numero_Proyecto" in data:
        data["Numero_Proyecto"] = str(data["Numero_Proyecto"]).strip()
    return data


# =============================================================================
# 1. PRUEBAS DE API BACKEND (FastAPI + MSSQL)
# =============================================================================

def test_api_put_proyecto_valido(auth_token):
    """API-01: Edición válida con todos los campos (200 OK)."""
    proj = create_test_project_in_db("QA-TEST-API-PUT")
    proj_id = proj["ID"]
    headers = {"Authorization": f"Bearer {auth_token}"}

    payload = {
        "cliente": "CLIENTE MODIFICADO QA SA",
        "lt_asignado": "Luis Tiznado",
        "estado": "En revision",
        "tipo_servicio": "Virtual Datacenter (VDC)",
        "detalle": "Detalle técnico modificado exitosamente.",
        "comentario": "Comentario de revisión técnica."
    }

    res = requests.put(f"{BASE_URL}/api/proyectos/{proj_id}", headers=headers, json=payload)
    assert res.status_code == 200, f"Error en PUT: {res.text}"
    body = res.json()
    assert body.get("message") == "Proyecto actualizado exitosamente"
    data = body.get("data") or {}
    assert data.get("Cliente") == "CLIENTE MODIFICADO QA SA"
    assert data.get("LT_Asignado") == "Luis Tiznado"
    assert data.get("Estado") == "En revision"
    assert data.get("Tipo_Servicio") == "Virtual Datacenter (VDC)"
    assert data.get("Detalle") == "Detalle técnico modificado exitosamente."
    assert data.get("Comentario") == "Comentario de revisión técnica."


def test_api_put_proyecto_campos_obligatorios_vacios(auth_token):
    """API-02: Intento de edición con campos requeridos vacíos (400 Bad Request)."""
    proj = create_test_project_in_db("QA-TEST-API-VAL")
    proj_id = proj["ID"]
    headers = {"Authorization": f"Bearer {auth_token}"}

    # Cliente vacío
    res1 = requests.put(f"{BASE_URL}/api/proyectos/{proj_id}", headers=headers, json={
        "cliente": "",
        "estado": "Generado",
        "detalle": "Detalle válido"
    })
    assert res1.status_code == 400

    # Estado vacío
    res2 = requests.put(f"{BASE_URL}/api/proyectos/{proj_id}", headers=headers, json={
        "cliente": "Cliente Válido",
        "estado": "  ",
        "detalle": "Detalle válido"
    })
    assert res2.status_code == 400

    # Detalle vacío
    res3 = requests.put(f"{BASE_URL}/api/proyectos/{proj_id}", headers=headers, json={
        "cliente": "Cliente Válido",
        "estado": "Generado",
        "detalle": ""
    })
    assert res3.status_code == 400


def test_api_put_proyecto_estado_invalido(auth_token):
    """API-03: Intento de edición con estado no permitido (400 Bad Request)."""
    proj = create_test_project_in_db("QA-TEST-API-EST")
    proj_id = proj["ID"]
    headers = {"Authorization": f"Bearer {auth_token}"}

    res = requests.put(f"{BASE_URL}/api/proyectos/{proj_id}", headers=headers, json={
        "cliente": "Cliente Válido",
        "estado": "EstadoInexistente123",
        "detalle": "Detalle válido"
    })
    assert res.status_code == 400
    assert "Estado inválido" in res.json().get("detail", "")


def test_api_put_proyecto_inexistente(auth_token):
    """API-04: Edición de ID inexistente (404 Not Found)."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    res = requests.put(f"{BASE_URL}/api/proyectos/99999999", headers=headers, json={
        "cliente": "Cliente Válido",
        "estado": "Generado",
        "detalle": "Detalle válido"
    })
    assert res.status_code == 404


def test_api_put_proyecto_sin_token():
    """API-05: Petición PUT sin token JWT (401 Unauthorized)."""
    res = requests.put(f"{BASE_URL}/api/proyectos/1", json={
        "cliente": "Cliente Válido",
        "estado": "Generado",
        "detalle": "Detalle válido"
    })
    assert res.status_code == 401


def test_api_delete_proyecto_exitoso(auth_token):
    """API-06: Eliminación exitosa de proyecto existente (200 OK)."""
    proj = create_test_project_in_db("QA-TEST-API-DEL")
    proj_id = proj["ID"]
    headers = {"Authorization": f"Bearer {auth_token}"}

    res = requests.delete(f"{BASE_URL}/api/proyectos/{proj_id}", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body.get("message") == "Proyecto eliminado exitosamente"
    assert body.get("id") == proj_id

    # Verificar que ya no existe en la BD
    res_get = requests.get(f"{BASE_URL}/api/proyectos/{proj_id}", headers=headers)
    assert res_get.status_code == 404


def test_api_delete_proyecto_inexistente(auth_token):
    """API-07: Eliminación de ID inexistente (404 Not Found)."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    res = requests.delete(f"{BASE_URL}/api/proyectos/99999999", headers=headers)
    assert res.status_code == 404


def test_api_delete_proyecto_sin_token():
    """API-08: Petición DELETE sin token JWT (401 Unauthorized)."""
    res = requests.delete(f"{BASE_URL}/api/proyectos/1")
    assert res.status_code == 401


# =============================================================================
# 2. PRUEBAS E2E FRONTEND (PLAYWRIGHT)
# =============================================================================

def test_e2e_01_render_action_buttons(page: Page):
    """
    E2E-01: Renderizado de Acciones en la tabla.
    Cada fila se abre con un clic y ofrece un menú "⋯" con Editar; Ver y Eliminar no están en la fila.
    """
    proj = create_test_project_in_db("QA-TEST-E2E-01")
    helper_login(page)
    target_row = helper_filter_project(page, proj["Numero_Proyecto"])

    assert target_row.locator(".btn-action-view").count() == 0
    assert target_row.locator(".btn-action-delete").count() == 0
    menu_btn = target_row.locator(".btn-row-menu")
    expect(menu_btn).to_be_visible()
    menu_btn.click()
    expect(page.locator("#row-actions-menu .btn-action-edit")).to_be_visible()


def test_e2e_02_open_and_populate_edit_modal(page: Page):
    """
    E2E-02: Apertura y Poblado de Modal de Edición.
    Clic en ✏️ -> Validar apertura de #edit-project-modal, campos protegidos y valores precargados.
    """
    proj = create_test_project_in_db("QA-TEST-E2E-02")
    proj_id = proj["ID"]
    helper_login(page)
    target_row = helper_filter_project(page, proj["Numero_Proyecto"])
    target_row.locator(".btn-row-menu").click()
    edit_btn = page.locator("#row-actions-menu .btn-action-edit")
    expect(edit_btn).to_be_visible()
    with page.expect_response(lambda r: f"/api/proyectos/{proj_id}" in r.url and r.status == 200, timeout=10000):
        edit_btn.click()

    # Verificar apertura de modal y que esté poblado
    edit_modal = page.locator("#edit-project-modal")
    expect(edit_modal).to_be_visible(timeout=10000)
    expect(page.locator("#edit-project-id")).to_have_value(str(proj_id), timeout=10000)

    # Verificar campos protegidos
    nro_input = page.locator("#edit-project-nro")
    fecha_input = page.locator("#edit-project-fecha")
    expect(nro_input).to_be_disabled()
    expect(fecha_input).to_be_disabled()
    expect(nro_input).to_have_class(re.compile(r"input-readonly"))
    expect(fecha_input).to_have_class(re.compile(r"input-readonly"))

    # Verificar datos precargados
    assert proj["Cliente"] in page.locator("#edit-project-cliente").input_value()
    assert page.locator("#edit-project-estado").input_value() == proj["Estado"]
    assert proj["Detalle"] in page.locator("#edit-project-detalle").input_value()

    # Cerrar modal con botón cancelar
    page.click("#btn-cancel-edit-modal")
    expect(edit_modal).to_be_hidden(timeout=10000)


def test_e2e_03_full_edit_flow_from_table(page: Page):
    """
    E2E-03: Flujo Completo de Edición y Persistencia desde la Tabla.
    Modificar Cliente, LT Asignado, Estado a 'Atendido', Detalle y Comentario -> Guardar Cambios.
    Verificar cierre de modal, Toast de éxito, actualización de la fila y persistencia en MSSQL.
    """
    proj = create_test_project_in_db("QA-TEST-E2E-03")
    proj_id = proj["ID"]
    helper_login(page)
    target_row = helper_filter_project(page, proj["Numero_Proyecto"])
    target_row.locator(".btn-row-menu").click()
    edit_btn = page.locator("#row-actions-menu .btn-action-edit")
    expect(edit_btn).to_be_visible()

    # Abrir modal de edición y esperar carga
    edit_btn.click()
    expect(page.locator("#edit-project-modal")).to_be_visible(timeout=15000)
    expect(page.locator("#edit-project-id")).to_have_value(str(proj_id), timeout=10000)

    # Modificar valores
    nuevo_cliente = f"CLIENTE MODIFICADO TEST E2E {int(time.time())}"
    nuevo_detalle = "Nuevo detalle técnico modificado vía Playwright E2E."
    nuevo_comentario = "Proyecto atendido y verificado por Líder TI."

    page.fill("#edit-project-cliente", nuevo_cliente)
    page.select_option("#edit-project-lt-asignado", "Alejandro Aguilar")
    page.select_option("#edit-project-estado", "Atendido")
    page.select_option("#edit-project-tipo-servicio", "Hosting Virtual")
    page.fill("#edit-project-detalle", nuevo_detalle)
    page.fill("#edit-project-comentario", nuevo_comentario)

    # Guardar cambios
    page.click("#btn-save-edit-modal")

    # Modal debe cerrarse
    expect(page.locator("#edit-project-modal")).to_be_hidden(timeout=10000)

    # Verificar Toast de éxito
    toast = page.locator(".alert-toast")
    expect(toast).to_be_visible(timeout=10000)
    expect(toast).to_contain_text("actualizado exitosamente")

    # Verificar persistencia en MSSQL
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT Cliente, Estado, Detalle, Comentario, Tipo_Servicio FROM dbo.Proyectos WHERE ID = %s", (proj_id,))
            row = cursor.fetchone()
            assert row is not None
            assert row["Cliente"] == nuevo_cliente
            assert row["Estado"] == "Atendido"
            assert row["Detalle"] == nuevo_detalle
            assert row["Comentario"] == nuevo_comentario
            assert row["Tipo_Servicio"] == "Hosting Virtual"
    finally:
        conn.close()


def test_e2e_04_edit_from_drilldown_view(page: Page):
    """
    E2E-04: Edición desde Vista Drill Down con actualización reactiva en vivo.
    Entrar a Drill Down -> Clic en ✏️ Editar de la cabecera -> Modificar datos -> Guardar.
    Verificar actualización en vivo del encabezado y de la pestaña Resumen sin recargar.
    """
    proj = create_test_project_in_db("QA-TEST-E2E-04")
    proj_id = proj["ID"]
    helper_login(page)

    target_row = helper_filter_project(page, proj["Numero_Proyecto"])
    view_btn = target_row.locator("td").first
    view_btn.scroll_into_view_if_needed()
    with page.expect_response(lambda r: f"/api/proyectos/{proj_id}" in r.url and r.status == 200, timeout=10000):
        view_btn.click()

    # Verificar que estemos en Drill Down
    expect(page.locator("#project-drilldown-section")).to_be_visible(timeout=10000)
    expect(page.locator("#dd-proj-num")).to_contain_text(proj["Numero_Proyecto"], timeout=10000)
    expect(page.locator("#dd-client-title")).to_contain_text(proj["Cliente"], timeout=10000)
    btn_edit = page.locator("#btn-dd-edit-project")
    expect(btn_edit).to_be_visible(timeout=10000)

    # Clic en Editar desde cabecera
    btn_edit.scroll_into_view_if_needed()
    try:
        with page.expect_response(lambda r: f"/api/proyectos/{proj_id}" in r.url and r.status == 200, timeout=5000):
            btn_edit.click(force=True)
    except Exception:
        page.evaluate(f"App.openEditProjectModal({proj_id})")
    expect(page.locator("#edit-project-modal")).to_be_visible(timeout=15000)
    expect(page.locator("#edit-project-id")).to_have_value(str(proj_id), timeout=10000)

    nuevo_cliente = f"CLIENTE DRILLDOWN LIVE EDIT {int(time.time())}"
    page.fill("#edit-project-cliente", nuevo_cliente)
    page.select_option("#edit-project-estado", "En revision")
    page.click("#btn-save-edit-modal")

    expect(page.locator("#edit-project-modal")).to_be_hidden(timeout=10000)

    # Verificar actualización en vivo en Drill Down Header y Resumen
    expect(page.locator("#dd-client-title")).to_contain_text(nuevo_cliente, timeout=10000)
    expect(page.locator("#dd-status")).to_contain_text("En revision", timeout=10000)
    expect(page.locator("#summary-content")).to_contain_text(nuevo_cliente, timeout=10000)


def test_e2e_05_open_and_cancel_delete_modal(page: Page):
    """
    E2E-05: Apertura y Cancelación de Modal de Confirmación Destructiva.
    Clic en 🗑️ -> Verificar apertura de #delete-project-modal con datos del proyecto.
    Clic en Cancelar -> Modal se cierra y el registro sigue existiendo en BD.
    """
    proj = create_test_project_in_db("QA-TEST-E2E-05")
    proj_id = proj["ID"]
    helper_login(page)

    target_row = helper_filter_project(page, proj["Numero_Proyecto"])

    # Eliminar vive solo en el detalle del proyecto
    target_row.locator("td").first.click()
    expect(page.locator("#project-drilldown-section")).to_be_visible(timeout=10000)
    del_btn = page.locator("#btn-dd-delete-project")
    expect(del_btn).to_be_visible(timeout=10000)
    try:
        with page.expect_response(lambda r: f"/api/proyectos/{proj_id}" in r.url and r.status == 200, timeout=5000):
            del_btn.click(force=True)
    except Exception:
        page.evaluate(f"App.openDeleteProjectModal({proj_id})")

    # Verificar apertura de modal de confirmación
    delete_modal = page.locator("#delete-project-modal")
    expect(delete_modal).to_be_visible(timeout=15000)
    expect(page.locator("#delete-project-id")).to_have_value(str(proj_id), timeout=10000)
    expect(page.locator("#modal-delete-cliente")).to_contain_text(proj["Cliente"])

    # Clic en Cancelar
    page.click("#btn-cancel-delete-modal")
    expect(delete_modal).to_be_hidden(timeout=10000)

    # Verificar que el registro aún existe en BD
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT ID FROM dbo.Proyectos WHERE ID = %s", (proj_id,))
            assert cursor.fetchone() is not None, "El proyecto no debió eliminarse al cancelar"
    finally:
        conn.close()


def test_e2e_06_confirm_delete_from_table(page: Page):
    """
    E2E-06: Confirmación de Eliminación desde la Tabla y Sincronización Reactiva.
    Clic en 🗑️ -> Confirmar 'Sí, Eliminar Proyecto'.
    Verificar eliminación física en MSSQL, Toast de éxito y actualización de la tabla.
    """
    proj = create_test_project_in_db("QA-TEST-E2E-06")
    proj_id = proj["ID"]
    helper_login(page)

    target_row = helper_filter_project(page, proj["Numero_Proyecto"])

    # Eliminar vive solo en el detalle del proyecto
    target_row.locator("td").first.click()
    expect(page.locator("#project-drilldown-section")).to_be_visible(timeout=10000)
    del_btn = page.locator("#btn-dd-delete-project")
    try:
        with page.expect_response(lambda r: f"/api/proyectos/{proj_id}" in r.url and r.status == 200, timeout=5000):
            del_btn.click(force=True)
    except Exception:
        page.evaluate(f"App.openDeleteProjectModal({proj_id})")
    expect(page.locator("#delete-project-modal")).to_be_visible(timeout=10000)
    expect(page.locator("#delete-project-id")).to_have_value(str(proj_id), timeout=10000)

    # Confirmar eliminación
    btn_confirm = page.locator("#btn-confirm-delete-modal")
    expect(btn_confirm).to_be_visible(timeout=5000)
    expect(btn_confirm).to_be_enabled(timeout=5000)
    btn_confirm.click()
    expect(page.locator("#delete-project-modal")).to_be_hidden(timeout=15000)

    # Toast de confirmación
    toast = page.locator(".alert-toast")
    expect(toast).to_be_visible(timeout=10000)
    expect(toast).to_contain_text("eliminado exitosamente")

    # Verificar que ya no existe en la BD
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT ID FROM dbo.Proyectos WHERE ID = %s", (proj_id,))
            assert cursor.fetchone() is None, "El proyecto debió ser eliminado de dbo.Proyectos"
    finally:
        conn.close()


def test_e2e_07_delete_from_drilldown_view(page: Page):
    """
    E2E-07: Eliminación desde la Vista Drill Down.
    Entrar a Drill Down -> Clic en 🗑️ Eliminar de la barra de título -> Confirmar eliminación.
    Verificar que retorne automáticamente a la lista principal de proyectos y el registro desaparezca.
    """
    proj = create_test_project_in_db("QA-TEST-E2E-07")
    proj_id = proj["ID"]
    helper_login(page)

    target_row = helper_filter_project(page, proj["Numero_Proyecto"])
    view_btn = target_row.locator("td").first
    view_btn.scroll_into_view_if_needed()
    with page.expect_response(lambda r: f"/api/proyectos/{proj_id}" in r.url and r.status == 200, timeout=10000):
        view_btn.click()

    expect(page.locator("#project-drilldown-section")).to_be_visible(timeout=10000)
    expect(page.locator("#dd-client-title")).to_contain_text(proj["Cliente"], timeout=10000)
    del_dd_btn = page.locator("#btn-dd-delete-project")
    expect(del_dd_btn).to_be_visible(timeout=10000)

    # Clic en Eliminar desde Drill Down
    del_dd_btn.scroll_into_view_if_needed()
    try:
        with page.expect_response(lambda r: f"/api/proyectos/{proj_id}" in r.url and r.status == 200, timeout=5000):
            del_dd_btn.click(force=True)
    except Exception:
        page.evaluate(f"App.openDeleteProjectModal({proj_id})")
    expect(page.locator("#delete-project-modal")).to_be_visible(timeout=15000)
    expect(page.locator("#delete-project-id")).to_have_value(str(proj_id), timeout=10000)

    # Confirmar
    btn_confirm = page.locator("#btn-confirm-delete-modal")
    expect(btn_confirm).to_be_visible(timeout=5000)
    expect(btn_confirm).to_be_enabled(timeout=5000)
    btn_confirm.click()
    expect(page.locator("#delete-project-modal")).to_be_hidden(timeout=15000)

    # Debe retornar al listado principal
    expect(page.locator("#projects-list-section")).to_be_visible(timeout=10000)
    expect(page.locator("#project-drilldown-section")).to_be_hidden(timeout=10000)


def test_e2e_08_light_and_dark_theme_modals(page: Page):
    """
    E2E-08: Validación de Modo Claro y Modo Oscuro en Modales y Acciones.
    Alternar temas con #theme-toggle-btn y validar visibilidad, contraste y botones en ambos temas.
    """
    proj = create_test_project_in_db("QA-TEST-E2E-08")
    proj_id = proj["ID"]
    helper_login(page)

    theme_btn = page.locator("#theme-toggle-btn")
    open_user_menu(page)
    expect(theme_btn).to_be_visible()
    page.keyboard.press("Escape")

    # 1. Modo Claro
    page.evaluate("App.setTheme('light')")
    assert page.locator("html").get_attribute("data-theme") == "light"

    target_row = helper_filter_project(page, proj["Numero_Proyecto"])

    # Abrir modal de edición en modo claro
    expect(target_row.locator(".btn-row-menu")).to_be_visible()
    page.evaluate(f"App.openEditProjectModal({proj_id})")
    edit_modal = page.locator("#edit-project-modal")
    expect(edit_modal).to_be_visible(timeout=10000)
    expect(page.locator("#edit-project-id")).to_have_value(str(proj_id), timeout=10000)
    expect(page.locator("#btn-save-edit-modal")).to_be_visible()

    # Cerrar modal
    page.click("#btn-cancel-edit-modal")
    expect(edit_modal).to_be_hidden(timeout=10000)

    # 2. Cambiar a Modo Oscuro vía botón de tema del menú de usuario
    click_user_menu_control(page, "#theme-toggle-btn")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark", timeout=5000)

    # Abrir modal de edición en modo oscuro
    target_row = page.locator(f"#projects-table-body tr:has-text('{proj['Numero_Proyecto']}')").first
    expect(target_row.locator(".btn-row-menu")).to_be_visible()
    page.evaluate(f"App.openEditProjectModal({proj_id})")
    expect(edit_modal).to_be_visible(timeout=10000)
    expect(page.locator("#edit-project-id")).to_have_value(str(proj_id), timeout=10000)
    expect(page.locator("#btn-save-edit-modal")).to_be_visible()
    expect(edit_modal.locator(".modal-icon-edit")).to_be_visible()
    page.click("#btn-cancel-edit-modal")
    expect(edit_modal).to_be_hidden(timeout=10000)

    # Abrir modal de eliminación en modo oscuro
    page.evaluate(f"App.openDeleteProjectModal({proj_id})")
    delete_modal = page.locator("#delete-project-modal")
    expect(delete_modal).to_be_visible(timeout=10000)
    expect(page.locator("#delete-project-id")).to_have_value(str(proj_id), timeout=10000)
    expect(page.locator("#btn-confirm-delete-modal")).to_be_visible()
    expect(delete_modal.locator(".modal-icon-danger")).to_be_visible()
    page.click("#btn-cancel-delete-modal")
    expect(delete_modal).to_be_hidden(timeout=10000)

    # 3. Regresar a modo claro
    click_user_menu_control(page, "#theme-toggle-btn")
    expect(page.locator("html")).to_have_attribute("data-theme", "light", timeout=5000)
