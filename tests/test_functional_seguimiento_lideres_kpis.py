"""
BATERÍA DE PRUEBAS FUNCIONALES Y DE INTEGRACIÓN DE QA
Proyecto: App LTI - Seguimiento Líderes TI
Módulos: Seguimiento de Proyectos, Filtro de Líderes TI, KPIs Interactivos y Tipografía Uniforme
Documento de Referencia: SPECS_MEJORAS_SEGUIMIENTO_LIDERES_KPIS.md

Cobertura de Tareas:
- Tarea 1: Consistencia de tipografía en toda la app (variables CSS, herencia, tablas, modales, temas claro/oscuro).
- Tarea 2: Filtro de Líderes TI con opción 'Sin asignar' (SQL, API y Frontend reactivo).
- Tarea 3: Lista restringida y ordenada alfabéticamente de los 5 líderes TI oficiales.
- Tarea 4: Tarjeta KPI 'Pendientes de Asignar' interactiva / clicable (renderizado, estilos, click toggle, accesibilidad y sincronización bidireccional).
- Tarea 5: Ocultación del campo LT Asignado en Solicitud LTI, persistencia con LT_Asignado = NULL y flujo end-to-end de asignación posterior.
"""

import re
import time
import datetime
import pytest
import requests
from playwright.sync_api import Page, expect
from backend.db import get_db_connection, get_lideres_list, get_dashboard_kpis
from backend.auth import create_access_token

BASE_URL = "http://localhost:8000"


def helper_login(page: Page, username: str = "aaguilar", password: str = "Lti2026!"):
    """Helper para autenticar en el portal con credenciales válidas."""
    page.goto(f"{BASE_URL}/")
    page.wait_for_selector("#auth-view", state="attached")
    
    if page.locator("#app-view").is_visible():
        return

    page.fill("#login-username", username)
    page.fill("#login-password", password)
    page.click("#login-submit-btn")
    page.wait_for_selector("#app-view", state="visible", timeout=10000)
    page.wait_for_selector("#nav-btn-projects", state="visible", timeout=5000)


# ==============================================================================
# TAREA 1: CONSISTENCIA DE TIPOGRAFÍA EN TODA LA APP
# ==============================================================================

def test_t1_01_typography_design_system_css_variables(page: Page):
    """
    Tarea 1 / CP-01.1: Validación de Variables Tipográficas en el Design System (:root)
    - Verificar que --font-sans y --font-mono existan en el DOM.
    - Verificar que incluyan las familias estándar ('Roboto', 'Plus Jakarta Sans', etc.).
    """
    helper_login(page)

    font_sans = page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--font-sans').trim()")
    font_mono = page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--font-mono').trim()")

    assert "Roboto" in font_sans or "Plus Jakarta Sans" in font_sans, f"Familia sans inesperada: {font_sans}"
    assert "Mono" in font_mono or "Consolas" in font_mono or "Courier" in font_mono or "JetBrains" in font_mono, f"Familia mono inesperada: {font_mono}"


def test_t1_02_typography_global_elements_and_tables(page: Page):
    """
    Tarea 1 / CP-01.2: Validación de Tipografía Unificada en Elementos Globales y Tablas
    - Verificar que body, .data-table, th, td, inputs, selects y buttons utilicen la fuente sans.
    - Verificar consistencia en modo claro y modo oscuro.
    """
    helper_login(page)
    expect(page.locator("#module-projects-container")).to_be_visible()

    for theme in ["light", "dark"]:
        page.evaluate(f"App.setTheme('{theme}')")
        page.wait_for_timeout(200)

        # 1. Body
        body_font = page.evaluate("() => getComputedStyle(document.body).fontFamily")
        assert "Roboto" in body_font or "Plus Jakarta Sans" in body_font, f"[{theme}] Body font: {body_font}"

        # 2. Form controls
        input_font = page.evaluate("() => { const el = document.getElementById('filter-search'); return el ? getComputedStyle(el).fontFamily : ''; }")
        select_font = page.evaluate("() => { const el = document.getElementById('filter-lt'); return el ? getComputedStyle(el).fontFamily : ''; }")
        assert "Roboto" in input_font or "Plus Jakarta Sans" in input_font, f"[{theme}] Input font: {input_font}"
        assert "Roboto" in select_font or "Plus Jakarta Sans" in select_font, f"[{theme}] Select font: {select_font}"

        # 3. Data Table Headers & Cells
        th_font = page.evaluate("() => { const el = document.querySelector('.data-table th'); return el ? getComputedStyle(el).fontFamily : ''; }")
        td_font = page.evaluate("() => { const el = document.querySelector('.data-table td'); return el ? getComputedStyle(el).fontFamily : ''; }")
        if th_font:
            assert "Roboto" in th_font or "Plus Jakarta Sans" in th_font, f"[{theme}] Table TH font: {th_font}"
        if td_font:
            assert "Roboto" in td_font or "Plus Jakarta Sans" in td_font, f"[{theme}] Table TD font: {td_font}"


def test_t1_03_typography_modals_and_solicitud_form(page: Page):
    """
    Tarea 1 / CP-01.3: Tipografía Uniforme en Modales y Módulo Solicitud LTI
    """
    helper_login(page)

    # Navegar a Solicitud LTI
    page.click("#nav-btn-solicitud-lti")
    expect(page.locator("#module-solicitud-lti-container")).to_be_visible()

    solicitud_card_font = page.evaluate("() => { const el = document.querySelector('.solicitud-card'); return el ? getComputedStyle(el).fontFamily : ''; }")
    assert "Roboto" in solicitud_card_font or "Plus Jakarta Sans" in solicitud_card_font

    label_font = page.evaluate("() => { const el = document.querySelector('#solicitud-lti-form .form-label'); return el ? getComputedStyle(el).fontFamily : ''; }")
    assert "Roboto" in label_font or "Plus Jakarta Sans" in label_font


# ==============================================================================
# TAREA 2: FILTRO DE LÍDERES TI CON OPCIÓN 'SIN ASIGNAR'
# ==============================================================================

def test_t2_01_backend_unassigned_filter_api(auth_token: str):
    """
    Tarea 2 / CP-02.1: Endpoint /api/proyectos?lt=__UNASSIGNED__
    - Debe retornar registros donde LT_Asignado sea NULL, vacío o 'sin asignar'.
    - No debe retornar registros con líder asignado válido.
    """
    headers = {"Authorization": f"Bearer {auth_token}"}
    
    # Test __UNASSIGNED__
    res = requests.get(f"{BASE_URL}/api/proyectos?lt=__UNASSIGNED__", headers=headers)
    assert res.status_code == 200
    proyectos = res.json()
    assert isinstance(proyectos, list)

    for p in proyectos:
        lt = p.get("LT_Asignado")
        assert lt is None or lt.strip() == "" or lt.strip().lower() == "sin asignar", f"Proyecto {p.get('ID')} tiene LT no nulo: {lt}"

    # Test alias 'Sin asignar'
    res_alias = requests.get(f"{BASE_URL}/api/proyectos?lt=Sin asignar", headers=headers)
    assert res_alias.status_code == 200
    proyectos_alias = res_alias.json()
    assert len(proyectos_alias) == len(proyectos)


def test_t2_02_backend_kpis_unassigned_filter_api(auth_token: str):
    """
    Tarea 2 / CP-02.2: Endpoint /api/kpis?lt=__UNASSIGNED__
    - Debe calcular métricas filtradas exclusivamente para proyectos sin asignar.
    """
    headers = {"Authorization": f"Bearer {auth_token}"}
    res = requests.get(f"{BASE_URL}/api/kpis?lt=__UNASSIGNED__", headers=headers)
    assert res.status_code == 200
    kpis = res.json()
    assert "total_proyectos" in kpis
    assert "pendientes_asignar" in kpis
    assert kpis["total_proyectos"] >= 0


def test_t2_03_frontend_filter_unassigned_interaction(page: Page):
    """
    Tarea 2 / CP-02.3: Interacción en Frontend al seleccionar 'Sin asignar' en #filter-lt
    - Al seleccionar '__UNASSIGNED__', la tabla debe recargar y mostrar los proyectos pendientes.
    """
    helper_login(page)
    expect(page.locator("#module-projects-container")).to_be_visible()

    # Seleccionar 'Sin asignar'
    select = page.locator("#filter-lt")
    select.select_option("__UNASSIGNED__")
    page.wait_for_timeout(800)

    # Verificar que el select mantenga el valor
    expect(select).to_have_value("__UNASSIGNED__")

    # Esperar que la tabla cargue (desaparezca el mensaje 'Cargando...')
    page.wait_for_selector("#projects-table-body td:not(:has-text('Cargando'))", timeout=10000)

    # Verificar filas de la tabla
    rows = page.locator("#projects-table-body tr")
    count = rows.count()
    if count > 0:
        first_td_text = rows.first.locator("td").first.inner_text().strip()
        if not first_td_text.startswith("No se encontraron"):
            for i in range(count):
                row_tds = rows.nth(i).locator("td")
                if row_tds.count() >= 3:
                    lt_cell = row_tds.nth(2).inner_text().strip()
                    assert lt_cell in ["Sin Asignar", "No asignado", "-", "sin asignar", "no asignado", ""], f"Fila {i} tiene LT asignado inesperado: {lt_cell}"


# ==============================================================================
# TAREA 3: LISTA RESTRINGIDA Y ORDENADA ALFABÉTICAMENTE DE LOS 5 LÍDERES TI
# ==============================================================================

def test_t3_01_backend_lideres_official_catalog_and_order(auth_token: str):
    """
    Tarea 3 / CP-03.1: Validación de Endpoint /api/lideres
    - Exclusivamente 5 líderes.
    - Orden alfabético ascendente estricto.
    """
    headers = {"Authorization": f"Bearer {auth_token}"}
    res = requests.get(f"{BASE_URL}/api/lideres", headers=headers)
    assert res.status_code == 200
    lideres = res.json()

    expected_5 = [
        "Alejandro Aguilar",
        "Erwin Sandoval",
        "Juan Barrera",
        "Samuel Paredes",
        "Solange Ortiz"
    ]
    assert lideres == expected_5, f"Líderes obtenidos {lideres} no coinciden exactamente con {expected_5}"
    assert lideres == sorted(lideres), "La lista de líderes no está ordenada alfabéticamente"


def test_t3_02_frontend_filter_lt_options_structure(page: Page):
    """
    Tarea 3 / CP-03.2: Estructura exacta de opciones en el selector #filter-lt
    - Opción 1: __ALL__ (— Todos los Líderes TI —)
    - Opción 2: __UNASSIGNED__ (Sin asignar)
    - Opciones 3-7: Los 5 líderes oficiales en orden alfabético.
    """
    helper_login(page)
    expect(page.locator("#module-projects-container")).to_be_visible()

    options = page.locator("#filter-lt option").all()
    assert len(options) == 7, f"Se esperaban exactamente 7 opciones en #filter-lt, encontradas {len(options)}"

    values = [opt.get_attribute("value") for opt in options]
    texts = [opt.inner_text().strip() for opt in options]

    assert values[0] == "__ALL__"
    assert "Todos los Líderes" in texts[0]

    assert values[1] == "__UNASSIGNED__"
    assert texts[1] == "Sin asignar"

    expected_lideres = [
        "Alejandro Aguilar",
        "Erwin Sandoval",
        "Juan Barrera",
        "Samuel Paredes",
        "Solange Ortiz"
    ]
    assert values[2:] == expected_lideres
    assert texts[2:] == expected_lideres


def test_t3_03_edit_modal_lideres_catalog(page: Page):
    """
    Tarea 3 / CP-03.3: Catálogo de Líderes en el Modal de Edición de Proyectos
    - Al abrir el modal de edición (#edit-project-modal), el selector #edit-project-lt-asignado debe tener los 5 líderes.
    """
    helper_login(page)
    expect(page.locator("#module-projects-container")).to_be_visible()

    # Buscar el primer botón de editar en la tabla
    edit_btn = page.locator(".btn-action-edit").first
    if edit_btn.is_visible():
        edit_btn.click()
        expect(page.locator("#edit-project-modal")).to_be_visible(timeout=5000)

        modal_select = page.locator("#edit-project-lt-asignado")
        expect(modal_select).to_be_visible()

        modal_opts = modal_select.locator("option").all()
        modal_values = [o.get_attribute("value") for o in modal_opts if o.get_attribute("value")]
        
        expected_lideres = [
            "Alejandro Aguilar",
            "Erwin Sandoval",
            "Juan Barrera",
            "Samuel Paredes",
            "Solange Ortiz"
        ]
        for leader in expected_lideres:
            assert leader in modal_values, f"Líder {leader} falta en el modal de edición"

        page.click("#btn-cancel-edit-modal")
        expect(page.locator("#edit-project-modal")).to_be_hidden()


# ==============================================================================
# TAREA 4: TARJETA KPI 'PENDIENTES DE ASIGNAR' INTERACTIVA / CLICABLE
# ==============================================================================

def test_t4_01_kpi_card_render_and_accessibility(page: Page, auth_token: str):
    """
    Tarea 4 / CP-04.1: Renderizado, valor numérico y atributos de accesibilidad
    - Verificar presencia de #kpi-card-pendientes y #kpi-val-pendientes-asignar.
    - Verificar role="button", tabindex="0", title descriptivo y badge 'Filtrar ⚡'.
    """
    helper_login(page)
    expect(page.locator("#module-projects-container")).to_be_visible()

    headers = {"Authorization": f"Bearer {auth_token}"}
    res = requests.get(f"{BASE_URL}/api/kpis", headers=headers)
    assert res.status_code == 200
    kpis_data = res.json()
    expected_val = kpis_data.get("pendientes_asignar", 0)

    card = page.locator("#kpi-card-pendientes")
    expect(card).to_be_visible()
    expect(card).to_have_attribute("role", "button")
    expect(card).to_have_attribute("tabindex", "0")

    val_el = page.locator("#kpi-val-pendientes-asignar")
    expect(val_el).to_have_text(str(expected_val), timeout=10000)

    badge = card.locator(".kpi-clickable-badge")
    expect(badge).to_be_visible()
    assert "Filtrar" in badge.inner_text()


def test_t4_02_kpi_card_click_filtering_and_active_state(page: Page):
    """
    Tarea 4 / CP-04.2: Interactividad Click en Tarjeta KPI 'Pendientes de Asignar'
    - Clic en tarjeta -> activa clase .active-filter, actualiza #filter-lt a '__UNASSIGNED__' y refresca tabla.
    - Clic de nuevo (toggle) -> remueve clase .active-filter, vuelve a '__ALL__' y muestra todos los proyectos.
    """
    helper_login(page)
    expect(page.locator("#module-projects-container")).to_be_visible()

    card = page.locator("#kpi-card-pendientes")
    select_lt = page.locator("#filter-lt")

    # 1. Primer clic -> Activar filtro Sin asignar
    card.click()
    page.wait_for_timeout(400)

    expect(card).to_have_class(re.compile(r"active-filter"))
    expect(card).to_have_attribute("aria-pressed", "true")
    expect(select_lt).to_have_value("__UNASSIGNED__")

    # 2. Segundo clic -> Alternar a Todos los Líderes
    card.click()
    page.wait_for_timeout(400)

    expect(card).not_to_have_class(re.compile(r"active-filter"))
    expect(card).to_have_attribute("aria-pressed", "false")
    expect(select_lt).to_have_value("__ALL__")


def test_t4_03_bidirectional_sync_dropdown_and_kpi_card(page: Page):
    """
    Tarea 4 / CP-04.3: Sincronización Bidireccional Dropdown <-> Tarjeta KPI
    - Seleccionar 'Sin asignar' en dropdown -> Tarjeta adquiere clase .active-filter.
    - Seleccionar 'Alejandro Aguilar' en dropdown -> Tarjeta pierde clase .active-filter.
    - Seleccionar '— Todos los Líderes TI —' en dropdown -> Tarjeta sin .active-filter.
    """
    helper_login(page)
    expect(page.locator("#module-projects-container")).to_be_visible()

    card = page.locator("#kpi-card-pendientes")
    select = page.locator("#filter-lt")

    # Seleccionar Sin asignar
    select.select_option("__UNASSIGNED__")
    page.wait_for_timeout(300)
    expect(card).to_have_class(re.compile(r"active-filter"))

    # Seleccionar un líder específico
    select.select_option("Alejandro Aguilar")
    page.wait_for_timeout(300)
    expect(card).not_to_have_class(re.compile(r"active-filter"))

    # Seleccionar Todos
    select.select_option("__ALL__")
    page.wait_for_timeout(300)
    expect(card).not_to_have_class(re.compile(r"active-filter"))


def test_t4_04_kpi_card_keyboard_navigation(page: Page):
    """
    Tarea 4 / CP-04.4: Accesibilidad por teclado (Enter y Space) en la Tarjeta KPI
    """
    helper_login(page)
    expect(page.locator("#module-projects-container")).to_be_visible()

    card = page.locator("#kpi-card-pendientes")
    select = page.locator("#filter-lt")

    # Focus en la tarjeta y presionar Enter
    card.focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)

    expect(card).to_have_class(re.compile(r"active-filter"))
    expect(select).to_have_value("__UNASSIGNED__")

    # Presionar Espacio para alternar
    card.focus()
    page.keyboard.press("Space")
    page.wait_for_timeout(400)

    expect(card).not_to_have_class(re.compile(r"active-filter"))
    expect(select).to_have_value("__ALL__")


# ==============================================================================
# TAREA 5: MÓDULO SOLICITUD LTI SIN CAMPO LT ASIGNADO Y PERSISTENCIA NULL
# ==============================================================================

def test_t5_01_solicitud_form_dom_field_omission(page: Page):
    """
    Tarea 5 / CP-05.1: Ocultación efectiva del campo LT Asignado en Solicitud LTI
    - Verificar que #solicitud-lt-asignado NO exista en el DOM.
    - Verificar que no haya labels con texto 'LT Asignado' o 'Líder Técnico'.
    - Verificar que los campos restantes sean: N° Proyecto, Cliente, Fecha, Estado (locked) y Detalle.
    """
    helper_login(page)
    page.click("#nav-btn-solicitud-lti")
    expect(page.locator("#module-solicitud-lti-container")).to_be_visible()

    # Campo no debe existir
    expect(page.locator("#solicitud-lt-asignado")).to_have_count(0)

    # Ningún label debe mencionar Líder o LT Asignado
    labels = page.locator("#solicitud-lti-form label").all_inner_texts()
    for lbl in labels:
        assert "lider" not in lbl.lower() and "líder" not in lbl.lower() and "lt asignado" not in lbl.lower(), f"Label inesperado de LT: {lbl}"

    # Campos esenciales deben estar presentes
    expect(page.locator("#solicitud-nro-proyecto")).to_be_visible()
    expect(page.locator("#solicitud-cliente")).to_be_visible()
    expect(page.locator("#solicitud-fecha")).to_be_visible()
    expect(page.locator("#solicitud-estado")).to_be_visible()
    expect(page.locator("#solicitud-detalle")).to_be_visible()


def test_t5_02_solicitud_creation_persists_lt_null(page: Page, auth_token: str):
    """
    Tarea 5 / CP-05.2: Creación de Solicitud y Persistencia de LT_Asignado = NULL
    - Crear nueva solicitud desde la UI sin campo LT Asignado.
    - Verificar modal de confirmación con estado 'Sin Asignar'.
    - Verificar directamente en MSSQL dbo.Proyectos que LT_Asignado sea NULL.
    """
    helper_login(page)
    page.click("#nav-btn-solicitud-lti")
    page.click("#btn-reset-solicitud")

    ts = int(time.time())
    test_proj_num = f"QA-T5-UNASSIGNED-{ts}"
    test_cliente = "CLINICA CENTRAL QA AUTOMATION SPA"
    test_detalle = f"Prueba de creación desatendida sin LT Asignado. Timestamp {ts}"

    page.fill("#solicitud-nro-proyecto", test_proj_num)
    page.fill("#solicitud-cliente", test_cliente)
    page.fill("#solicitud-detalle", test_detalle)

    page.click("#btn-submit-solicitud")

    # Esperar modal de éxito
    success_modal = page.locator("#solicitud-success-modal")
    expect(success_modal).to_be_visible(timeout=8000)

    # Validar campos del modal
    created_id_str = page.locator("#solicitud-success-id").inner_text().strip()
    assert created_id_str.isdigit()
    created_id = int(created_id_str)

    modal_lt = page.locator("#modal-solicitud-lt").inner_text()
    assert "Sin Asignar" in modal_lt or "-" in modal_lt

    # Verificar en MSSQL dbo.Proyectos
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT ID, Cliente, Numero_Proyecto, LT_Asignado, Estado, Detalle FROM dbo.Proyectos WHERE ID = %s", (created_id,))
            row = cursor.fetchone()
            assert row is not None, f"Proyecto {created_id} no encontrado en base de datos"
            assert test_proj_num in row["Numero_Proyecto"]
            assert row["LT_Asignado"] is None or str(row["LT_Asignado"]).strip() == "", f"LT_Asignado debería ser NULL, obtenido: {row['LT_Asignado']}"
            assert row["Estado"] == "Generado"
    finally:
        conn.close()


def test_t5_03_end_to_end_lifecycle_creation_filter_and_assignment(page: Page, auth_token: str):
    """
    Tarea 5 / CP-05.3: Flujo End-to-End Completo
    1. Obtener conteo inicial de 'pendientes_asignar'.
    2. Crear nueva solicitud LTI (LT_Asignado = NULL).
    3. Navegar a Seguimiento Proyectos -> Verificar que KPI 'Pendientes de Asignar' incrementó en +1.
    4. Clic en tarjeta KPI -> Filtrar por 'Sin asignar' -> Verificar que el nuevo proyecto aparece en la lista.
    5. Clic en '✏️ Editar' -> Asignar a 'Erwin Sandoval' -> Guardar cambios.
    6. Verificar que el proyecto ya no aparece bajo el filtro 'Sin asignar' y que el KPI decrementó en -1.
    """
    headers = {"Authorization": f"Bearer {auth_token}"}
    res_init = requests.get(f"{BASE_URL}/api/kpis", headers=headers)
    initial_pendientes = res_init.json().get("pendientes_asignar", 0)

    helper_login(page)

    # 1. Crear Solicitud LTI
    page.click("#nav-btn-solicitud-lti")
    page.click("#btn-reset-solicitud")

    ts = int(time.time())
    proj_code = f"QA-E2E-FLOW-{ts}"
    client_name = "MINISTERIO DE CIENCIA QA LTDA"
    detalle_text = f"Flujo E2E completo de creación desatendida y posterior asignación de líder. TS: {ts}"

    page.fill("#solicitud-nro-proyecto", proj_code)
    page.fill("#solicitud-cliente", client_name)
    page.fill("#solicitud-detalle", detalle_text)
    page.click("#btn-submit-solicitud")

    expect(page.locator("#solicitud-success-modal")).to_be_visible(timeout=8000)
    created_id_str = page.locator("#solicitud-success-id").inner_text().strip()
    created_id = int(created_id_str)

    # 2. Navegar a Seguimiento Proyectos con botón del modal
    page.click("#btn-solicitud-go-to-projects")
    expect(page.locator("#module-projects-container")).to_be_visible()

    # 3. Validar incremento en KPI Pendientes (+1)
    val_pendientes_el = page.locator("#kpi-val-pendientes-asignar")
    # Esperar que se actualice el DOM con el nuevo conteo
    expect(val_pendientes_el).to_have_text(str(initial_pendientes + 1), timeout=5000)

    # 4. Clic en Tarjeta KPI 'Pendientes de Asignar'
    kpi_card = page.locator("#kpi-card-pendientes")
    kpi_card.click()
    page.wait_for_timeout(500)

    expect(page.locator("#filter-lt")).to_have_value("__UNASSIGNED__")

    # 5. Localizar fila del proyecto recién creado en la tabla
    row = page.locator(f"#projects-table-body tr").filter(has_text=proj_code).first
    expect(row).to_be_visible(timeout=5000)

    # 6. Clic en botón Editar de esa fila
    edit_btn = row.locator(".btn-action-edit")
    edit_btn.click()

    expect(page.locator("#edit-project-modal")).to_be_visible(timeout=10000)
    expect(page.locator("#edit-project-id")).to_have_value(str(created_id), timeout=10000)

    # 7. Asignar líder Erwin Sandoval y guardar
    page.select_option("#edit-project-lt-asignado", "Erwin Sandoval")
    page.click("#btn-save-edit-modal")

    # Modal debe cerrarse y mostrar toast de éxito
    expect(page.locator("#edit-project-modal")).to_be_hidden(timeout=10000)
    expect(page.locator(".alert-toast")).to_be_visible(timeout=10000)

    # 8. Al estar en la vista filtrada '__UNASSIGNED__', el proyecto ya NO debe estar en la tabla
    page.wait_for_timeout(800)
    row_after = page.locator(f"#projects-table-body tr").filter(has_text=proj_code)
    expect(row_after).to_have_count(0)

    # 9. KPI Pendientes debe haber decrementado de nuevo al valor inicial
    expect(val_pendientes_el).to_have_text(str(initial_pendientes), timeout=10000)

    # 10. Verificar en BD que la asignación persistió
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT LT_Asignado FROM dbo.Proyectos WHERE ID = %s", (created_id,))
            res_db = cursor.fetchone()
            assert res_db["LT_Asignado"] == "Erwin Sandoval"
    finally:
        conn.close()
