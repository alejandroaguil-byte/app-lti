"""
PRUEBAS FUNCIONALES Y DE UI: TIMELINE VISUAL ROADMAP & KILL-SWITCH
Especificación: SPECS_TIMELINE_VISUAL_PROYECTO.md
Documento: SPECS-LTI-MOD-014
"""

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import Page, expect

from backend.main import app
from tests.conftest import create_access_token, create_portal_jwt

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
    halo_page.evaluate("() => localStorage.removeItem('halo_timeline_enabled')")
    halo_page.reload()
    halo_page.wait_for_selector("#app-view", state="visible", timeout=25000)
    halo_page.wait_for_function("() => window.App && window.App.isInitialized === true", timeout=25000)
    halo_page.wait_for_selector("#projects-table-body tr", state="visible", timeout=15000)


# ==============================================================================
# FT-TL-01: Estado Inicial del Kill-Switch en HTML (ON por defecto)
# ==============================================================================
def test_kill_switch_timeline_default_on():
    """
    Verifica que en el HTML base el botón toggle de Timeline esté presente con label 'Timeline: ON'
    y aria-pressed='true'.
    """
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    assert 'id="timeline-toggle-btn"' in html
    assert 'aria-pressed="true"' in html
    assert 'id="timeline-toggle-label"' in html
    assert 'Timeline: ON' in html
    assert 'id="tab-btn-timeline"' in html
    assert 'data-tab="timeline"' in html
    assert 'id="tab-count-timeline"' in html


# ==============================================================================
# FT-TL-02: Kill-Switch y Política de Cero Rastros en CSS
# ==============================================================================
def test_kill_switch_timeline_toggle_off_cero_rastros():
    """
    Verifica que las clases de estilo de Cero Rastros estén definidas en styles.css
    para #timeline-toggle-btn.is-off y los componentes del roadmap.
    """
    res = client.get("/css/styles.css")
    assert res.status_code == 200
    css = res.text

    assert "#timeline-toggle-btn.is-off" in css
    assert ".timeline-kpi-grid" in css
    assert ".timeline-kpi-card" in css
    assert ".timeline-kpi-card.is-critical" in css
    assert ".timeline-filters-bar" in css
    assert ".timeline-pill-btn" in css
    assert ".timeline-roadmap-track" in css
    assert ".roadmap-node-dot" in css
    assert ".roadmap-connector" in css
    assert ".roadmap-lapse-badge" in css


# ==============================================================================
# FT-TL-03: Estructura HTML de la Pestaña Línea de Tiempo y KPIs
# ==============================================================================
def test_tab_timeline_html_structure():
    """
    Verifica que el panel #tab-pane-timeline contenga las 4 tarjetas KPI,
    la barra de filtros tipo píldora y los contenedores de carga y roadmap.
    """
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    # Contenedor principal del tab
    assert 'id="tab-pane-timeline"' in html

    # 4 Tarjetas KPI
    assert 'id="timeline-metric-total"' in html
    assert 'id="timeline-metric-leadtime"' in html
    assert 'id="timeline-metric-ultimo"' in html
    assert 'id="timeline-card-compromiso"' in html
    assert 'id="timeline-metric-compromiso"' in html

    # 5 Filtros píldora
    assert 'data-timeline-filter="all"' in html
    assert 'data-timeline-filter="sharepoint"' in html
    assert 'data-timeline-filter="solot"' in html
    assert 'data-timeline-filter="ticket"' in html
    assert 'data-timeline-filter="rfc"' in html

    # Contenedores de estado
    assert 'id="timeline-loading-state"' in html
    assert 'id="timeline-roadmap-track"' in html
    assert 'id="timeline-empty-state"' in html


# ==============================================================================
# FT-TL-04: Paleta Claro HALO y Modo Oscuro en CSS
# ==============================================================================
def test_css_timeline_tokens_and_classes():
    """
    Verifica la integración de los colores corporativos #B52217 y #0097A9
    y las directivas [data-theme="dark"] para el Timeline.
    """
    res = client.get("/css/styles.css")
    assert res.status_code == 200
    css = res.text

    assert "#B52217" in css
    assert "#0097A9" in css
    assert '[data-theme="dark"] .timeline-kpi-card.is-critical' in css
    assert '[data-theme="dark"] .timeline-kpi-card.is-future' in css
    assert '[data-theme="dark"] .roadmap-item.item-overdue .roadmap-card' in css


# ==============================================================================
# FT-TL-05: Regresión - Pestañas Adyacentes Mantienen Integridad
# ==============================================================================
def test_regresion_no_afecta_pestanas_adyacentes():
    """
    Verifica que la integración de la pestaña Timeline no altere las pestañas
    adyacentes en el Drill Down (summary, solots, tickets, rfcs).
    """
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    assert 'data-tab="summary"' in html
    assert 'data-tab="timeline"' in html
    assert 'data-tab="solots"' in html
    assert 'data-tab="tickets"' in html
    assert 'data-tab="rfcs"' in html

    assert 'id="tab-pane-summary"' in html
    assert 'id="tab-pane-timeline"' in html
    assert 'id="tab-pane-solots"' in html
    assert 'id="tab-pane-tickets"' in html
    assert 'id="tab-pane-rfcs"' in html


# ==============================================================================
# FT-TL-06: Métodos y Variables JavaScript en app.js
# ==============================================================================
def test_js_timeline_methods_and_flags():
    """
    Verifica que app.js contenga la inicialización de ENABLE_TIMELINE,
    los métodos del Kill-Switch y el renderizador de eventos.
    """
    res = client.get("/js/app.js")
    assert res.status_code == 200
    js = res.text

    assert "ENABLE_TIMELINE" in js
    assert "isTimelineActive()" in js
    assert "toggleTimeline()" in js
    assert "applyTimelineState(" in js
    assert "loadTimeline(" in js
    assert "renderTimelineMetrics(" in js
    assert "renderTimelineEvents(" in js
    assert "updateTimelinePillCounts(" in js
    assert "renderTimelineMetadata(" in js


# ==============================================================================
# FT-TL-E2E-01: Toggle Kill-Switch UI & Cero Rastros (E2E con Playwright)
# ==============================================================================
def test_e2e_timeline_toggle_ui_and_killswitch(halo_page: Page, base_url: str):
    """
    Validar que el botón Kill-Switch alterne su estado visual y oculte completamente
    la pestaña '📈 Línea de Tiempo'.
    """
    _setup_app_session(halo_page, base_url)

    # 1. Validar presencia del botón toggle y estado inicial ON
    toggle_btn = halo_page.locator("#timeline-toggle-btn")
    expect(toggle_btn).to_be_visible()
    expect(toggle_btn).to_have_attribute("aria-pressed", "true")
    expect(halo_page.locator("#timeline-toggle-label")).to_have_text("Timeline: ON")

    # 2. Abrir Drill Down del primer proyecto
    halo_page.locator("#projects-table-body tr .btn-action-view").first.click()
    expect(halo_page.locator("#project-drilldown-section")).to_be_visible(timeout=10000)

    # 3. La pestaña Timeline debe ser visible
    tab_timeline = halo_page.locator("#tab-btn-timeline")
    expect(tab_timeline).to_be_visible()

    # 4. Apagar Kill-Switch desde la sub-barra
    toggle_btn.click()
    halo_page.wait_for_timeout(300)
    expect(toggle_btn).to_have_attribute("aria-pressed", "false")
    expect(halo_page.locator("#timeline-toggle-label")).to_have_text("Timeline: OFF")

    # 5. La pestaña Timeline debe desaparecer (Cero Rastros)
    expect(tab_timeline).to_be_hidden()

    # 6. Reactivar el Kill-Switch
    toggle_btn.click()
    halo_page.wait_for_timeout(300)
    expect(toggle_btn).to_have_attribute("aria-pressed", "true")
    expect(tab_timeline).to_be_visible()


# ==============================================================================
# FT-TL-E2E-02: Navegación de Tab y Filtros Rápidos (E2E con Playwright)
# ==============================================================================
def test_e2e_timeline_filter_pills_and_roadmap(halo_page: Page, base_url: str):
    """
    Validar la navegación a la pestaña Timeline, carga de KPIs y filtrado por píldoras.
    """
    _setup_app_session(halo_page, base_url)

    # 1. Abrir Drill Down
    halo_page.locator("#projects-table-body tr .btn-action-view").first.click()
    expect(halo_page.locator("#project-drilldown-section")).to_be_visible(timeout=10000)

    # 2. Clic en pestaña Timeline
    tab_timeline = halo_page.locator("#tab-btn-timeline")
    tab_timeline.click()
    expect(tab_timeline).to_have_class("tab-btn active")

    # 3. Verificar que el panel Timeline se muestre
    pane_timeline = halo_page.locator("#tab-pane-timeline")
    expect(pane_timeline).to_be_visible()

    # 4. Verificar presencia de tarjetas KPI
    expect(halo_page.locator("#timeline-metric-total")).to_be_visible()
    expect(halo_page.locator("#timeline-metric-leadtime")).to_be_visible()

    # 5. Probar clic en píldora de filtro 'SGA Solots'
    pill_solot = halo_page.locator('.timeline-pill-btn[data-timeline-filter="solot"]')
    expect(pill_solot).to_be_visible()
    pill_solot.click()
    expect(pill_solot).to_have_class("timeline-pill-btn active")

    # 6. Probar clic en 'Todos'
    pill_all = halo_page.locator('.timeline-pill-btn[data-timeline-filter="all"]')
    pill_all.click()
    expect(pill_all).to_have_class("timeline-pill-btn active")


# ==============================================================================
# FT-TL-07: Accesibilidad ARIA en Kill-Switch y Componentes de Timeline
# ==============================================================================
def test_timeline_aria_accessibility():
    """
    Verifica que el botón de Kill-Switch y los componentes del Timeline
    cumplan con los estándares de accesibilidad ARIA (aria-pressed, aria-label, roles).
    """
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    # Kill-Switch ARIA
    assert 'id="timeline-toggle-btn"' in html
    assert 'aria-label="Toggle Timeline Visual"' in html
    assert 'aria-pressed="true"' in html

    # Tab Timeline
    assert 'id="tab-btn-timeline"' in html
    assert 'data-tab="timeline"' in html
    assert 'id="tab-count-timeline"' in html


# ==============================================================================
# FT-TL-E2E-03: Auto-Switch a Pestaña 'Resumen' al Desactivar Kill-Switch (E2E)
# ==============================================================================
def test_e2e_timeline_autoswitch_to_summary_on_killswitch(halo_page: Page, base_url: str):
    """
    Verifica que si el usuario está visualizando la pestaña '📈 Línea de Tiempo'
    y desactiva el Kill-Switch, el sistema conmuta automáticamente y sin errores
    a la pestaña '📋 Resumen del Proyecto' garantizando Cero Rastros.
    """
    _setup_app_session(halo_page, base_url)

    # 1. Abrir Drill Down
    halo_page.locator("#projects-table-body tr .btn-action-view").first.click()
    expect(halo_page.locator("#project-drilldown-section")).to_be_visible(timeout=10000)

    # 2. Navegar a la pestaña Línea de Tiempo
    tab_timeline = halo_page.locator("#tab-btn-timeline")
    tab_timeline.click()
    expect(tab_timeline).to_have_class("tab-btn active")
    expect(halo_page.locator("#tab-pane-timeline")).to_be_visible()

    # 3. Desactivar el Kill-Switch mientras se está en la pestaña Timeline
    toggle_btn = halo_page.locator("#timeline-toggle-btn")
    toggle_btn.click()
    halo_page.wait_for_timeout(300)

    # 4. Validar política Cero Rastros: pestaña Timeline oculta
    expect(tab_timeline).to_be_hidden()

    # 5. Validar Auto-Switch a Resumen: pestaña 'summary' debe estar activa y su panel visible
    tab_summary = halo_page.locator('.tabs-header .tab-btn[data-tab="summary"]')
    expect(tab_summary).to_have_class("tab-btn active")
    expect(halo_page.locator("#tab-pane-summary")).to_be_visible()

    # 6. Reactivar Kill-Switch: la pestaña Timeline reaparece pero NO interrumpe la navegación actual
    toggle_btn.click()
    halo_page.wait_for_timeout(300)
    expect(tab_timeline).to_be_visible()
    expect(tab_summary).to_have_class("tab-btn active")

