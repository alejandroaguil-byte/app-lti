"""
BATERÍA DE PRUEBAS FUNCIONALES Y E2E: CATÁLOGO CANÓNICO Y FILTRO DE ESTADOS SHAREPOINT
Proyecto: App LTI - Seguimiento de Proyectos
Documento de Referencia: SPECS_FILTRO_ESTADOS_SHAREPOINT.md

Casos de Prueba:
- Backend / API Tests:
  - TC-EST-01: Catálogo Canónico Completo en /api/estados (['Generado', 'En revision', 'Atendido'])
  - TC-EST-02: Control RBAC en /api/estados (PM -> 403, ADMIN/LTI -> 200)
  - TC-EST-03: Filtrado por Estado 'Generado' (/api/proyectos?estado_sp=Generado)
  - TC-EST-04: Filtrado por Estado 'En revision' (/api/proyectos?estado_sp=En+revision)
  - TC-EST-05: Filtrado por Estado 'Atendido' (/api/proyectos?estado_sp=Atendido)
  - TC-EST-06: Comodín Todos los Estados (/api/proyectos)
  - TC-EST-07: Resiliencia de get_estados_list() ante excepción en consulta SGA
- Frontend / Playwright E2E Tests:
  - TC-E2E-01: Renderizado del selector #filter-estado-sp con las 4 opciones canónicas
  - TC-E2E-02: Filtrado Reactivo al Seleccionar 'Generado'
  - TC-E2E-03: Filtrado Reactivo al Seleccionar 'En revision'
  - TC-E2E-04: Filtrado Reactivo al Seleccionar 'Atendido'
  - TC-E2E-05: Fallback Defensivo ante Error de Red en /api/estados
  - TC-E2E-06: Preservación de Filtro al Conmutar Módulos
"""

import os
import re
import time
import uuid
import pytest
import requests
from unittest.mock import patch, MagicMock
from playwright.sync_api import Page, expect
from backend.db import (
    get_db_connection,
    get_estados_list,
    get_proyectos,
    create_solicitud_lti,
    update_proyecto,
    CANONICAL_ESTADOS_SHAREPOINT,
)
from tests.conftest import create_access_token

BASE_URL = os.getenv("BASE_URL", "http://100.82.24.75:8000")


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
    page.wait_for_selector("#projects-table", state="visible", timeout=10000)
    page.wait_for_selector("#projects-table-body tr", state="visible", timeout=10000)
    page.wait_for_selector("#projects-table-body tr:not(:has-text('Cargando proyectos'))", timeout=10000)
    page.wait_for_selector("#filter-estado-sp option[value='Atendido']", state="attached", timeout=10000)


def create_test_project_with_state(estado: str, prefix: str = "QA-TEST-EST") -> dict:
    """Crea un proyecto de prueba con un estado específico ('Generado', 'En revision', 'Atendido')."""
    unique_suffix = f"{int(time.time() * 1000) % 10000000}-{uuid.uuid4().hex[:6]}"
    res = create_solicitud_lti(
        cliente=f"CLIENTE PRUEBA QA ESTADO {unique_suffix}",
        numero_proyecto=f"{prefix}-{unique_suffix}",
        detalle=f"Prueba E2E Automatizada Estado {estado} {unique_suffix}",
        tipo_servicio="Instalación de Enlace",
        lt_asignado="Alejandro Aguilar"
    )
    assert res.get("success") is True, f"Error creando proyecto: {res}"
    proj_id = res["data"]["ID"]

    if estado != "Generado":
        up_res = update_proyecto(
            proyecto_id=proj_id,
            cliente=f"CLIENTE PRUEBA QA ESTADO {unique_suffix}",
            lt_asignado="Alejandro Aguilar",
            estado=estado,
            tipo_servicio="Instalación de Enlace",
            detalle=f"Prueba E2E Automatizada Estado {estado} {unique_suffix}",
            comentario=f"Comentario QA {unique_suffix}"
        )
        assert up_res.get("success") is True, f"Error actualizando estado: {up_res}"

    return {
        "id": proj_id,
        "cliente": f"CLIENTE PRUEBA QA ESTADO {unique_suffix}",
        "numero_proyecto": res["data"]["Numero_Proyecto"],
        "estado": estado
    }


# ==============================================================================
# 4.1. PRUEBAS BACKEND E INTEGRACIÓN DE API
# ==============================================================================

def test_tc_est_01_canonical_estados_endpoint(auth_token):
    """
    TC-EST-01: Catálogo Canónico Completo en /api/estados
    Verifica que la API retorne exactamente ['Generado', 'En revision', 'Atendido'] en ese orden.
    """
    headers = {"Authorization": f"Bearer {auth_token}"}
    resp = requests.get(f"{BASE_URL}/api/estados", headers=headers, timeout=5)
    assert resp.status_code == 200
    data = resp.json()

    assert "estados_sharepoint" in data
    assert data["estados_sharepoint"] == ["Generado", "En revision", "Atendido"]
    assert "estados_sga" in data
    assert isinstance(data["estados_sga"], list)


def test_tc_est_02_rbac_estados_endpoint():
    """
    TC-EST-02: Control RBAC en /api/estados
    - PM debe recibir 403 Forbidden.
    - LTI y ADMIN deben recibir 200 OK.
    """
    # 1. Token PM
    pm_token = create_access_token({
        "sub": "calbornoz",
        "nombre_completo": "Albornoz Pacheco Cesar Augusto",
        "lt_asignado": None,
        "rol": "PM"
    })
    resp_pm = requests.get(f"{BASE_URL}/api/estados", headers={"Authorization": f"Bearer {pm_token}"}, timeout=5)
    assert resp_pm.status_code == 403, f"PM debería tener 403, pero obtuvo {resp_pm.status_code}"

    # 2. Token LTI
    lti_token = create_access_token({
        "sub": "jbarrera",
        "nombre_completo": "Juan Barrera",
        "lt_asignado": "Juan Barrera",
        "rol": "LTI"
    })
    resp_lti = requests.get(f"{BASE_URL}/api/estados", headers={"Authorization": f"Bearer {lti_token}"}, timeout=5)
    assert resp_lti.status_code == 200
    assert resp_lti.json()["estados_sharepoint"] == ["Generado", "En revision", "Atendido"]

    # 3. Token ADMIN
    admin_token = create_access_token({
        "sub": "aaguilar",
        "nombre_completo": "Alejandro Aguilar",
        "lt_asignado": "Alejandro Aguilar",
        "rol": "ADMIN"
    })
    resp_admin = requests.get(f"{BASE_URL}/api/estados", headers={"Authorization": f"Bearer {admin_token}"}, timeout=5)
    assert resp_admin.status_code == 200
    assert resp_admin.json()["estados_sharepoint"] == ["Generado", "En revision", "Atendido"]


def test_tc_est_03_filter_by_estado_generado(auth_token):
    """
    TC-EST-03: Filtrado por Estado 'Generado'
    """
    p1 = create_test_project_with_state("Generado")
    headers = {"Authorization": f"Bearer {auth_token}"}
    params = {"estado_sp": "Generado", "search": p1["numero_proyecto"]}
    resp = requests.get(f"{BASE_URL}/api/proyectos", headers=headers, params=params, timeout=10)
    assert resp.status_code == 200
    projs = resp.json()
    assert len(projs) >= 1
    assert all(p["Estado"] == "Generado" for p in projs)
    assert any(p["ID"] == p1["id"] for p in projs)


def test_tc_est_04_filter_by_estado_en_revision(auth_token):
    """
    TC-EST-04: Filtrado por Estado 'En revision'
    """
    p2 = create_test_project_with_state("En revision")
    headers = {"Authorization": f"Bearer {auth_token}"}
    params = {"estado_sp": "En revision", "search": p2["numero_proyecto"]}
    resp = requests.get(f"{BASE_URL}/api/proyectos", headers=headers, params=params, timeout=10)
    assert resp.status_code == 200
    projs = resp.json()
    assert len(projs) >= 1
    assert all(p["Estado"] == "En revision" for p in projs)
    assert any(p["ID"] == p2["id"] for p in projs)


def test_tc_est_05_filter_by_estado_atendido(auth_token):
    """
    TC-EST-05: Filtrado por Estado 'Atendido'
    """
    p3 = create_test_project_with_state("Atendido")
    headers = {"Authorization": f"Bearer {auth_token}"}
    params = {"estado_sp": "Atendido", "search": p3["numero_proyecto"]}
    resp = requests.get(f"{BASE_URL}/api/proyectos", headers=headers, params=params, timeout=10)
    assert resp.status_code == 200
    projs = resp.json()
    assert len(projs) >= 1
    assert all(p["Estado"] == "Atendido" for p in projs)
    assert any(p["ID"] == p3["id"] for p in projs)


def test_tc_est_06_wildcard_all_estados(auth_token):
    """
    TC-EST-06: Comodín Todos los Estados
    Verifica que al no enviar estado_sp se devuelvan proyectos en diferentes estados.
    """
    p_gen = create_test_project_with_state("Generado")
    p_rev = create_test_project_with_state("En revision")
    p_ate = create_test_project_with_state("Atendido")

    headers = {"Authorization": f"Bearer {auth_token}"}
    resp = requests.get(f"{BASE_URL}/api/proyectos", headers=headers, timeout=10)
    assert resp.status_code == 200
    all_projs = resp.json()

    returned_ids = {p["ID"] for p in all_projs}
    assert p_gen["id"] in returned_ids
    assert p_rev["id"] in returned_ids
    assert p_ate["id"] in returned_ids


def test_tc_est_07_resilience_on_db_exception():
    """
    TC-EST-07: Resiliencia ante Excepción de BD en SGA
    Verifica que si la consulta de SGA falla, get_estados_list() retorna el catálogo
    canónico completo de SharePoint y estados_sga como lista vacía [].
    """
    with patch("backend.db.get_db_connection") as mock_conn:
        mock_conn.side_effect = Exception("Simulated MSSQL Connection Failure for SGA")
        result = get_estados_list()
        assert result["estados_sharepoint"] == ["Generado", "En revision", "Atendido"]
        assert result["estados_sga"] == []


# ==============================================================================
# 4.2. PRUEBAS FRONTEND E2E (PLAYWRIGHT)
# ==============================================================================

def test_tc_e2e_01_filter_estado_sp_rendered_options(page: Page):
    """
    TC-E2E-01: Renderizado del Selector #filter-estado-sp
    Verifica que el select contenga exactamente las 4 opciones requeridas:
    - — Estado Sharepoint (Todos) — (value="")
    - Generado (value="Generado")
    - En revision (value="En revision")
    - Atendido (value="Atendido")
    """
    helper_login(page)

    select = page.locator("#filter-estado-sp")
    expect(select).to_be_visible()

    options = select.locator("option")
    expect(options).to_have_count(4)

    expected_options = [
        {"value": "", "text": "— Estado Sharepoint (Todos) —"},
        {"value": "Generado", "text": "Generado"},
        {"value": "En revision", "text": "En revision"},
        {"value": "Atendido", "text": "Atendido"},
    ]

    for idx, exp in enumerate(expected_options):
        opt = options.nth(idx)
        expect(opt).to_have_attribute("value", exp["value"])
        expect(opt).to_have_text(exp["text"])


def helper_filter_by_estado(page: Page, nro: str, estado_val: str):
    target_row = page.locator(f"#projects-table-body tr:has-text('{nro}')").first
    for _ in range(8):
        page.evaluate("""async (data) => {
            const search = document.getElementById('filter-search');
            if (search) search.value = data.nro;
            const estado = document.getElementById('filter-estado-sp');
            if (estado) estado.value = data.estado;
            const lt = document.getElementById('filter-lt');
            if (lt) lt.value = '__ALL__';
            if (window.App && window.App.loadProjects) {
                await window.App.loadProjects();
            }
        }""", {"nro": nro, "estado": estado_val})
        page.wait_for_selector("#projects-table-body tr:not(:has-text('Cargando proyectos'))", timeout=10000)
        try:
            target_row.wait_for(state="visible", timeout=1500)
            return target_row
        except Exception:
            page.wait_for_timeout(500)
    target_row.wait_for(state="visible", timeout=15000)
    return target_row


def test_tc_e2e_02_filter_reactive_generado(page: Page):
    """
    TC-E2E-02: Filtrado Reactivo al Seleccionar 'Generado'
    """
    p_gen = create_test_project_with_state("Generado")
    helper_login(page)

    row = helper_filter_by_estado(page, p_gen["numero_proyecto"], "Generado")
    expect(row).to_be_visible(timeout=10000)
    expect(row.locator(".badge", has_text="Generado")).to_be_visible(timeout=10000)


def test_tc_e2e_03_filter_reactive_en_revision(page: Page):
    """
    TC-E2E-03: Filtrado Reactivo al Seleccionar 'En revision'
    """
    p_rev = create_test_project_with_state("En revision")
    helper_login(page)

    row = helper_filter_by_estado(page, p_rev["numero_proyecto"], "En revision")
    expect(row).to_be_visible(timeout=10000)
    expect(row.locator(".badge", has_text="En revision")).to_be_visible(timeout=10000)


def test_tc_e2e_04_filter_reactive_atendido(page: Page):
    """
    TC-E2E-04: Filtrado Reactivo al Seleccionar 'Atendido'
    """
    p_ate = create_test_project_with_state("Atendido")
    helper_login(page)

    row = helper_filter_by_estado(page, p_ate["numero_proyecto"], "Atendido")
    expect(row).to_be_visible(timeout=10000)
    expect(row.locator(".badge", has_text="Atendido")).to_be_visible(timeout=10000)


def test_tc_e2e_05_defensive_fallback_on_api_error(page: Page):
    """
    TC-E2E-05: Fallback Defensivo ante Error de Red en /api/estados
    Interpreta un fallo HTTP 500 simulado en /api/estados y verifica que el select
    mantenga las 4 opciones canónicas.
    """
    # Interceptar la ruta /api/estados antes de la navegación
    page.route("**/api/estados", lambda route: route.fulfill(
        status=500,
        content_type="application/json",
        body='{"detail": "Internal Server Error Simulation"}'
    ))

    helper_login(page)

    select = page.locator("#filter-estado-sp")
    expect(select).to_be_visible()

    options = select.locator("option")
    expect(options).to_have_count(4)
    expect(options.nth(1)).to_have_text("Generado")
    expect(options.nth(2)).to_have_text("En revision")
    expect(options.nth(3)).to_have_text("Atendido")


def test_tc_e2e_06_filter_preservation_on_module_switch(page: Page):
    """
    TC-E2E-06: Preservación de Filtro al Conmutar Módulos
    Selecciona 'En revision', navega a Búsqueda Directa y regresa a Seguimiento de Proyectos.
    El filtro debe conservar 'En revision'.
    """
    helper_login(page)

    select = page.locator("#filter-estado-sp")
    select.select_option("En revision")
    page.wait_for_timeout(300)
    expect(select).to_have_value("En revision")

    # Cambiar a Búsqueda Directa
    page.click("#nav-btn-direct-search")
    expect(page.locator("#module-direct-search-container")).to_be_visible()

    # Volver a Proyectos
    page.click("#nav-btn-projects")
    expect(page.locator("#module-projects-container")).to_be_visible()

    # Verificar que el valor se conservó
    expect(select).to_have_value("En revision")
