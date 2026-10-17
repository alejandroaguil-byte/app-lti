"""
PRUEBAS FUNCIONALES Y DE UI: CENTRO DE ALERTAS TEMPRANAS SLA & ESCALAMIENTO RÁPIDO & KILL-SWITCH
Especificación: SPECS_ALERTAS_TEMPRANAS_SLA.md
Documento: SPECS-LTI-MOD-015
"""

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import Page, expect

from backend.main import app
from tests.conftest import suppress_tours, create_access_token, create_portal_jwt, open_user_menu, close_user_menu

client = TestClient(app)

@pytest.fixture
def halo_page():
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                permissions=["clipboard-read", "clipboard-write"]
            )
            suppress_tours(context)
            page = context.new_page()
            yield page
            context.close()
            browser.close()
    except Exception as e:
        pytest.skip(f"Playwright chromium browser no disponible en este host: {e}")


def _setup_app_session(halo_page: Page, base_url: str):
    """Configura la sesión con token JWT de portal de acceso y asegura estado inicial limpio."""
    token = create_portal_jwt(username="alejandro.aguilar", admin_level=2, name="Alejandro Aguilar")
    halo_page.context.add_cookies([{
        "name": "access_token",
        "value": token,
        "url": base_url,
    }])
    halo_page.goto(f"{base_url}/")
    halo_page.evaluate("() => localStorage.removeItem('halo_alerts_enabled')")
    halo_page.reload()
    halo_page.wait_for_selector("#app-view", state="visible", timeout=25000)
    halo_page.wait_for_function("() => window.App && window.App.isInitialized === true", timeout=25000)
    halo_page.wait_for_selector("#projects-table-body tr", state="visible", timeout=15000)


# ==============================================================================
# FT-ALT-001: Estado Inicial del Kill-Switch y Campanita en HTML (ON por defecto)
# ==============================================================================
def test_ft_alt_001_html_default_structure():
    """
    Verifica que en el HTML base el botón toggle de Alertas esté presente con label 'Alertas: ON',
    aria-pressed='true', y la campanita #alerts-bell-btn en .user-area.
    """
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    # Kill-Switch toggle en subbarra
    assert 'id="alerts-toggle-btn"' in html
    assert 'aria-pressed="true"' in html
    assert 'id="alerts-toggle-label"' in html
    assert 'Alertas: ON' in html

    # Campanita en user-area
    assert 'id="alerts-wrapper"' in html
    assert 'id="alerts-bell-btn"' in html
    assert 'id="alerts-badge-count"' in html


# ==============================================================================
# FT-ALT-002: Estructura HTML del Dropdown Flotante de Alertas SLA
# ==============================================================================
def test_ft_alt_002_dropdown_html_structure():
    """
    Verifica que el panel flotante #alerts-dropdown contenga la cabecera, sub-resumen,
    las píldoras de filtro, acciones de escalamiento y el contenedor de lista.
    """
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    # Dropdown y cabecera
    assert 'id="alerts-dropdown"' in html
    assert 'id="alerts-dropdown-total-badge"' in html
    assert 'id="alerts-dropdown-close-btn"' in html
    assert 'id="alerts-summary-crit-count"' in html
    assert 'id="alerts-summary-warn-count"' in html

    # Píldoras de filtro
    assert 'id="alerts-filter-all"' in html
    assert 'id="alerts-filter-crit"' in html
    assert 'id="alerts-filter-warn"' in html

    # Botones ejecutivos de escalamiento
    assert 'id="btn-copy-alerts-minuta"' in html
    assert 'id="btn-escalar-alerts-email"' in html

    # Lista y estados
    assert 'id="alerts-list-container"' in html
    assert 'id="alerts-loading-state"' in html
    assert 'id="alerts-items-list"' in html
    assert 'id="alerts-empty-state"' in html
    assert 'id="btn-alerts-refresh"' in html


# ==============================================================================
# FT-ALT-003: Estilos CSS y Tokens Institucionales Claro HALO
# ==============================================================================
def test_ft_alt_003_css_tokens_and_classes():
    """
    Verifica que styles.css defina estilos para la campanita, animación pulsante,
    dropdown flotante, tarjetas de alerta y compatibilidad con modo oscuro.
    """
    res = client.get("/css/styles.css")
    assert res.status_code == 200
    css = res.text

    assert "#alerts-toggle-btn.is-off" in css
    assert ".alerts-wrapper" in css
    assert ".btn-alerts-bell" in css
    assert ".alerts-badge" in css
    assert ".alerts-badge.pulse-red" in css
    assert "@keyframes pulse-alerts" in css
    assert ".alerts-dropdown" in css
    assert ".alert-card-item" in css
    assert ".alert-card-item.critica" in css
    assert ".badge-sla-critical" in css
    assert ".badge-sla-warning" in css
    assert '[data-theme="dark"] .alerts-dropdown' in css


# ==============================================================================
# FT-ALT-004: Métodos y Variables JavaScript en app.js
# ==============================================================================
def test_ft_alt_004_js_methods_and_flags():
    """
    Verifica que app.js contenga la inicialización de ENABLE_ALERTS,
    los métodos del Kill-Switch, consulta de API, renderizado y escalamiento.
    """
    res = client.get("/js/app.js")
    assert res.status_code == 200
    js = res.text

    assert "ENABLE_ALERTS" in js
    assert "initAlerts()" in js
    assert "isAlertsActive()" in js
    assert "toggleAlerts()" in js
    assert "applyAlertsState(" in js
    assert "fetchAlertsSLA()" in js
    assert "updateAlertsUI()" in js
    assert "renderAlerts()" in js
    assert "toggleAlertsDropdown(" in js
    assert "closeAlertsDropdown()" in js
    assert "filterAlerts(" in js
    assert "copyAlertsMinuta()" in js
    assert "escalarAlertsEmail()" in js
    assert "openProjectFromAlert(" in js


# ==============================================================================
# FT-ALT-005: Regresión UI: Cabecera y Sub-barra Preservan Integridad
# ==============================================================================
def test_ft_alt_005_regresion_ui_elementos_adyacentes():
    """
    Verifica que los toggles previos (Salud, Diagnóstico, Ficha PDF, Timeline)
    y botones de usuario sigan existiendo sin distorsión.
    """
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    assert 'id="health-score-toggle-btn"' in html
    assert 'id="diag-toggle-btn"' in html
    assert 'id="pdf-export-toggle-btn"' in html
    assert 'id="timeline-toggle-btn"' in html
    assert 'id="alerts-toggle-btn"' in html
    assert 'id="user-avatar"' in html
    assert 'id="btn-logout"' in html


# ==============================================================================
# FT-ALT-E2E-001: Despliegue de Panel Flotante y Consulta (Playwright E2E)
# ==============================================================================
def test_ft_alt_e2e_001_despliegue_dropdown(halo_page: Page, base_url: str):
    """
    Validar que el clic en #alerts-bell-btn abra el panel flotante #alerts-dropdown,
    actualice aria-expanded y muestre los contadores.
    """
    _setup_app_session(halo_page, base_url)

    bell_btn = halo_page.locator("#alerts-bell-btn")
    expect(bell_btn).to_be_visible()

    # Dropdown inicialmente oculto
    dropdown = halo_page.locator("#alerts-dropdown")
    expect(dropdown).to_be_hidden()

    # Clic en campanita
    bell_btn.click()
    halo_page.wait_for_timeout(400)

    # Dropdown debe hacerse visible
    expect(dropdown).to_be_visible()
    expect(bell_btn).to_have_attribute("aria-expanded", "true")

    # Cabecera del dropdown debe tener título
    expect(halo_page.locator(".alerts-header-title")).to_have_text("Proyectos con atrasos SLA")


# ==============================================================================
# FT-ALT-E2E-002: Cierre por Clic Afuera y por Tecla Escape (Playwright E2E)
# ==============================================================================
def test_ft_alt_e2e_002_cierre_escape_y_clic_afuera(halo_page: Page, base_url: str):
    """
    Validar que presionar Escape o hacer clic fuera del panel cierre #alerts-dropdown.
    """
    _setup_app_session(halo_page, base_url)

    bell_btn = halo_page.locator("#alerts-bell-btn")
    dropdown = halo_page.locator("#alerts-dropdown")

    # 1. Abrir dropdown
    bell_btn.click()
    halo_page.wait_for_timeout(300)
    expect(dropdown).to_be_visible()

    # 2. Presionar Escape para cerrar
    halo_page.keyboard.press("Escape")
    halo_page.wait_for_timeout(300)
    expect(dropdown).to_be_hidden()
    expect(bell_btn).to_have_attribute("aria-expanded", "false")

    # 3. Volver a abrir
    bell_btn.click()
    halo_page.wait_for_timeout(300)
    expect(dropdown).to_be_visible()

    # 4. Clic afuera (sobre la tabla de proyectos)
    halo_page.locator("#projects-table-body").click()
    halo_page.wait_for_timeout(300)
    expect(dropdown).to_be_hidden()


# ==============================================================================
# FT-ALT-E2E-003: Filtrado Rápido por Píldoras (Playwright E2E)
# ==============================================================================
def test_ft_alt_e2e_003_filtrado_pildoras(halo_page: Page, base_url: str):
    """
    Validar que hacer clic en las píldoras 'Críticas' y 'Advertencias'
    actualice la clase activa y filtre el listado sin recargar la página.
    """
    _setup_app_session(halo_page, base_url)

    bell_btn = halo_page.locator("#alerts-bell-btn")
    bell_btn.click()
    halo_page.wait_for_timeout(400)

    pill_all = halo_page.locator("#alerts-filter-all")
    pill_crit = halo_page.locator("#alerts-filter-crit")
    pill_warn = halo_page.locator("#alerts-filter-warn")

    expect(pill_all).to_have_class("alerts-filter-pill active")

    # Clic en Críticas
    pill_crit.click()
    halo_page.wait_for_timeout(200)
    expect(pill_crit).to_have_class("alerts-filter-pill active")
    expect(pill_all).not_to_have_class("active")

    # Clic en Advertencias
    pill_warn.click()
    halo_page.wait_for_timeout(200)
    expect(pill_warn).to_have_class("alerts-filter-pill active")
    expect(pill_crit).not_to_have_class("active")


# ==============================================================================
# FT-ALT-E2E-004: Kill-Switch: Apagado y Cero Rastros (Playwright E2E)
# ==============================================================================
def test_ft_alt_e2e_004_kill_switch_cero_rastros(halo_page: Page, base_url: str):
    """
    Validar que apagar el Kill-Switch oculte inmediatamente la campanita
    sin distorsionar el área de usuario y persista en localStorage.
    """
    _setup_app_session(halo_page, base_url)

    toggle_btn = halo_page.locator("#alerts-toggle-btn")
    bell_wrapper = halo_page.locator("#alerts-wrapper")

    expect(toggle_btn).to_have_attribute("aria-pressed", "true")
    expect(halo_page.locator("#alerts-toggle-label")).to_have_text("Alertas: ON")
    expect(bell_wrapper).to_be_visible()

    # Apagar Kill-Switch
    open_user_menu(halo_page)
    toggle_btn.click()
    close_user_menu(halo_page)
    halo_page.wait_for_timeout(300)

    # Verificar estado OFF
    expect(toggle_btn).to_have_attribute("aria-pressed", "false")
    expect(halo_page.locator("#alerts-toggle-label")).to_have_text("Alertas: OFF")

    # Cero Rastros: campanita completamente oculta
    expect(bell_wrapper).to_be_hidden()

    # Validar persistencia en localStorage
    pref = halo_page.evaluate("() => localStorage.getItem('halo_alerts_enabled')")
    assert pref == "false"

    # Reactivar
    open_user_menu(halo_page)
    toggle_btn.click()
    close_user_menu(halo_page)
    halo_page.wait_for_timeout(300)
    expect(toggle_btn).to_have_attribute("aria-pressed", "true")
    expect(halo_page.locator("#alerts-toggle-label")).to_have_text("Alertas: ON")
    expect(bell_wrapper).to_be_visible()


# ==============================================================================
# FT-ALT-E2E-005: Kill-Switch: Auto-cierre de Panel al Apagar (Playwright E2E)
# ==============================================================================
def test_ft_alt_e2e_005_kill_switch_autocierre_panel(halo_page: Page, base_url: str):
    """
    Verifica que si el panel flotante está abierto y el usuario desactiva el Kill-Switch,
    el panel se cierra de inmediato sin artefactos residuales en la UI.
    """
    _setup_app_session(halo_page, base_url)

    bell_btn = halo_page.locator("#alerts-bell-btn")
    dropdown = halo_page.locator("#alerts-dropdown")
    toggle_btn = halo_page.locator("#alerts-toggle-btn")

    # Abrir panel
    bell_btn.click()
    halo_page.wait_for_timeout(300)
    expect(dropdown).to_be_visible()

    # Desactivar Kill-Switch mientras panel está abierto
    halo_page.evaluate("() => App.toggleAlerts()")
    halo_page.wait_for_timeout(300)

    # Tanto campanita como dropdown deben estar ocultos
    expect(dropdown).to_be_hidden()
    expect(halo_page.locator("#alerts-wrapper")).to_be_hidden()
