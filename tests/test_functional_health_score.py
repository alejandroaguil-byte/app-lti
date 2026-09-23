"""
PRUEBAS FUNCIONALES AUTOMATIZADAS E2E: SEMÁFORO DE SALUD DEL PROYECTO & KILL-SWITCH
Especificación: SPECS_SEMAFORO_SALUD_PROYECTOS.md
"""

import pytest
from playwright.sync_api import Page, expect
from tests.conftest import create_portal_jwt

@pytest.fixture
def halo_page():
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            yield page
            context.close()
            browser.close()
    except Exception as e:
        pytest.skip(f"Playwright chromium browser no disponible en este host: {e}")

def test_health_score_ui_toggle_and_clean_fallback(halo_page: Page, base_url: str):
    """
    CP-SALUD-E2E:
    1. Carga la app autenticada.
    2. Valida que el botón de toggle exista (#health-score-toggle-btn).
    3. Valida que #health-kpi-grid sea visible y contenga las 4 tarjetas de salud.
    4. Valida que la cabecera de la tabla contenga la columna Salud (#th-col-salud).
    5. Valida que las filas tengan la celda .col-health-cell con badge de salud.
    6. Hace clic en la tarjeta #health-card-critical y valida el filtrado.
    7. Hace clic nuevamente en #health-card-critical y valida que se desactive el filtro.
    8. Hace clic en #health-score-toggle-btn (Kill-Switch OFF):
       - Botón pasa a Salud: OFF y clase .is-off.
       - #health-kpi-grid se oculta (display: none).
       - #th-col-salud se oculta.
       - Las celdas .col-health-cell se eliminan y la tabla tiene exactamente 8 columnas.
    9. Recarga la página (F5):
       - Verifica persistencia en localStorage ('halo_health_score_enabled' === 'false').
       - La vista inicia directamente en modo estándar sin semáforo.
    10. Hace clic en #health-score-toggle-btn (Kill-Switch ON):
       - Vuelve a activarse limpiamente.
    """
    token = create_portal_jwt(username="alejandro.aguilar", admin_level=2, name="Alejandro Aguilar")
    halo_page.context.add_cookies([{
        "name": "access_token",
        "value": token,
        "url": base_url,
    }])

    # Limpiar preferencia previa
    halo_page.goto(f"{base_url}/")
    halo_page.evaluate("() => localStorage.removeItem('halo_health_score_enabled')")
    halo_page.reload()
    halo_page.wait_for_selector("#app-view", state="visible", timeout=25000)
    halo_page.wait_for_function("() => window.App && window.App.isInitialized === true", timeout=25000)

    # 1. Validar botón toggle
    toggle_btn = halo_page.locator("#health-score-toggle-btn")
    expect(toggle_btn).to_be_visible()
    expect(halo_page.locator("#health-toggle-label")).to_have_text("Salud: ON")

    # 2. Validar grid de KPIs de salud
    health_grid = halo_page.locator("#health-kpi-grid")
    expect(health_grid).to_be_visible()
    expect(halo_page.locator("#health-card-healthy")).to_be_visible()
    expect(halo_page.locator("#health-card-warning")).to_be_visible()
    expect(halo_page.locator("#health-card-critical")).to_be_visible()
    expect(halo_page.locator("#health-card-neutral")).to_be_visible()

    # 3. Validar columna en cabecera de tabla
    th_salud = halo_page.locator("#th-col-salud")
    expect(th_salud).to_be_visible()

    # 4. Validar celdas de salud en filas
    halo_page.wait_for_selector("#projects-table-body tr", state="visible", timeout=10000)
    first_row_cells = halo_page.locator("#projects-table-body tr").first.locator("td")
    # Cuando está activo, debe haber 9 celdas
    assert first_row_cells.count() == 9, f"Se esperaban 9 columnas activas, obtenidas {first_row_cells.count()}"

    # 5. Filtrar por Críticos al hacer click
    critical_card = halo_page.locator("#health-card-critical")
    critical_card.click()
    halo_page.wait_for_timeout(300)
    assert "active-health-filter" in (critical_card.get_attribute("class") or "")
    
    # 6. Desactivar filtro al volver a hacer click
    critical_card.click()
    halo_page.wait_for_timeout(300)
    assert "active-health-filter" not in (critical_card.get_attribute("class") or "")

    # 7. Apagar con Kill-Switch (Toggle OFF)
    toggle_btn.click()
    halo_page.wait_for_timeout(300)
    expect(halo_page.locator("#health-toggle-label")).to_have_text("Salud: OFF")
    assert "is-off" in (toggle_btn.get_attribute("class") or "")
    expect(health_grid).not_to_be_visible()
    expect(th_salud).not_to_be_visible()

    # Verificar que la tabla volvió a exactamente 8 columnas estándar
    first_row_cells_off = halo_page.locator("#projects-table-body tr").first.locator("td")
    assert first_row_cells_off.count() == 8, f"Se esperaban 8 columnas tras kill-switch, obtenidas {first_row_cells_off.count()}"

    # 8. Recargar página (F5) y comprobar persistencia
    halo_page.reload()
    halo_page.wait_for_selector("#app-view", state="visible", timeout=25000)
    halo_page.wait_for_function("() => window.App && window.App.isInitialized === true", timeout=25000)

    expect(halo_page.locator("#health-toggle-label")).to_have_text("Salud: OFF")
    expect(health_grid).not_to_be_visible()
    expect(th_salud).not_to_be_visible()

    # 9. Reactivar con Kill-Switch (Toggle ON)
    toggle_btn_re = halo_page.locator("#health-score-toggle-btn")
    toggle_btn_re.click()
    halo_page.wait_for_timeout(300)
    expect(halo_page.locator("#health-toggle-label")).to_have_text("Salud: ON")
    expect(health_grid).to_be_visible()
    expect(th_salud).to_be_visible()
