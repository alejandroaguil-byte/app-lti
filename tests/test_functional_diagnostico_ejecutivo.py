"""
PRUEBAS FUNCIONALES AUTOMATIZADAS E2E: DIAGNÓSTICO EJECUTIVO EN 1 CLIC & KILL-SWITCH
Especificación: SPECS_DIAGNOSTICO_EJECUTIVO.md
"""

import pytest
from playwright.sync_api import Page, expect
from tests.conftest import (
    create_portal_jwt,
    open_user_menu,
    close_user_menu,
    click_user_menu_control,
    open_project_row,
)


def _first_row_menu_diag(halo_page: Page):
    """Opens the first row's "⋯" menu and returns the diagnosis action locator."""
    halo_page.locator("#projects-table-body tr.project-row").first.locator(".btn-row-menu").click()
    return halo_page.locator("#row-actions-menu .btn-action-diag")


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
    halo_page.evaluate("() => localStorage.removeItem('halo_executive_diagnosis_enabled')")
    halo_page.reload()
    halo_page.wait_for_selector("#app-view", state="visible", timeout=25000)
    halo_page.wait_for_function("() => window.App && window.App.isInitialized === true", timeout=25000)
    halo_page.wait_for_selector("#projects-table-body tr", state="visible", timeout=15000)


def test_diagnostico_ejecutivo_toggle_ui_and_killswitch(halo_page: Page, base_url: str):
    """
    CP-DIAG-E2E-01: Validar toggle UI, Kill-Switch y persistencia localStorage.
    """
    _setup_app_session(halo_page, base_url)

    # 1. Validar presencia del botón toggle y estado inicial ON
    toggle_btn = halo_page.locator("#diag-toggle-btn")
    open_user_menu(halo_page)
    expect(toggle_btn).to_be_visible()
    close_user_menu(halo_page)
    expect(halo_page.locator("#diagnosis-toggle-label")).to_have_text("Diagnóstico: ON")
    assert "is-off" not in (toggle_btn.get_attribute("class") or "")

    # 2. Validar que el menú "⋯" de la fila ofrece la acción rápida de diagnóstico
    expect(_first_row_menu_diag(halo_page)).to_be_visible()
    halo_page.keyboard.press("Escape")

    # 3. Apagar Kill-Switch (Toggle OFF)
    click_user_menu_control(halo_page, "#diag-toggle-btn")
    halo_page.wait_for_timeout(300)
    expect(halo_page.locator("#diagnosis-toggle-label")).to_have_text("Diagnóstico: OFF")
    assert "is-off" in (toggle_btn.get_attribute("class") or "")

    # Verificar que la acción .btn-action-diag desaparece del menú de la fila
    expect(_first_row_menu_diag(halo_page)).to_have_count(0)
    halo_page.keyboard.press("Escape")

    # Verificar que las columnas estándar de la tabla siguen operativas
    first_row_cells = halo_page.locator("#projects-table-body tr").first.locator("td")
    assert first_row_cells.count() in (8, 9)

    # 4. Comprobar persistencia tras F5 (recarga)
    halo_page.reload()
    halo_page.wait_for_selector("#app-view", state="visible", timeout=25000)
    halo_page.wait_for_function("() => window.App && window.App.isInitialized === true", timeout=25000)
    halo_page.wait_for_selector("#projects-table-body tr", state="visible", timeout=15000)

    expect(halo_page.locator("#diagnosis-toggle-label")).to_have_text("Diagnóstico: OFF")
    expect(_first_row_menu_diag(halo_page)).to_have_count(0)
    halo_page.keyboard.press("Escape")

    # 5. Reactivar con Kill-Switch (Toggle ON)
    toggle_btn_re = halo_page.locator("#diag-toggle-btn")
    click_user_menu_control(halo_page, "#diag-toggle-btn")
    halo_page.wait_for_timeout(300)
    expect(halo_page.locator("#diagnosis-toggle-label")).to_have_text("Diagnóstico: ON")
    assert "is-off" not in (toggle_btn_re.get_attribute("class") or "")
    expect(_first_row_menu_diag(halo_page)).to_be_visible()
    halo_page.keyboard.press("Escape")


def test_diagnostico_ejecutivo_modal_launch_and_content(halo_page: Page, base_url: str):
    """
    CP-DIAG-E2E-02: Validar apertura del modal y renderizado de cuellos de botella, recomendaciones y minuta.
    """
    _setup_app_session(halo_page, base_url)

    modal = halo_page.locator("#modal-executive-diagnosis")
    expect(modal).not_to_be_visible()

    # Abrir modal mediante la acción rápida del menú "⋯" de la primera fila
    _first_row_menu_diag(halo_page).click()

    # Modal debe ser visible
    expect(modal).to_be_visible()
    expect(halo_page.locator("#modal-diag-title")).to_have_text("Diagnóstico Ejecutivo en 1 Clic")

    # Esperar que cargue el contenido y se oculte el spinner
    content_wrapper = halo_page.locator("#diag-content-wrapper")
    expect(content_wrapper).to_be_visible(timeout=15000)

    # Validar campos de la ficha ejecutiva
    cliente_val = halo_page.locator("#diag-val-cliente").inner_text()
    assert len(cliente_val.strip()) > 0 and cliente_val != "-"

    num_val = halo_page.locator("#diag-val-num").inner_text()
    assert len(num_val.strip()) > 0 and num_val != "-"

    expect(halo_page.locator("#diag-val-salud-badge")).to_be_visible()
    expect(halo_page.locator("#diag-progress-pct")).to_be_visible()

    # Validar secciones operacionales
    expect(halo_page.locator("#diag-cuellos-container")).to_be_visible()
    expect(halo_page.locator("#diag-recs-container")).to_be_visible()

    # Validar preview de minuta
    minuta_text = halo_page.locator("#diag-minuta-text").inner_text()
    assert "DIAGNÓSTICO EJECUTIVO HALO" in minuta_text
    assert num_val in minuta_text

    # Cerrar modal con botón de cierre
    halo_page.locator("#btn-close-diag-modal").click()
    expect(modal).not_to_be_visible()


def test_diagnostico_ejecutivo_copy_minuta_button(halo_page: Page, base_url: str):
    """
    CP-DIAG-E2E-03: Validar funcionamiento y feedback visual del botón Copiar Minuta.
    """
    _setup_app_session(halo_page, base_url)

    # Abrir diagnóstico del primer proyecto
    _first_row_menu_diag(halo_page).click()
    expect(halo_page.locator("#diag-content-wrapper")).to_be_visible(timeout=15000)

    copy_btn = halo_page.locator("#btn-copy-diag-minuta")
    expect(copy_btn).to_be_visible()

    # Clic en copiar minuta
    copy_btn.click()
    halo_page.wait_for_timeout(300)

    # Validar feedback visual (cambio de texto / clase de éxito o toast)
    assert "¡Minuta Copiada!" in copy_btn.inner_text() or "btn-success" in (copy_btn.get_attribute("class") or "")

    # Cerrar modal
    halo_page.locator("#btn-close-diag-footer").click()
    expect(halo_page.locator("#modal-executive-diagnosis")).not_to_be_visible()


def test_diagnostico_ejecutivo_email_minuta_modal(halo_page: Page, base_url: str):
    """
    CP-DIAG-E2E-04: Validar integración con el modal de envío de correo Office 365.
    """
    _setup_app_session(halo_page, base_url)

    # Abrir diagnóstico
    _first_row_menu_diag(halo_page).click()
    expect(halo_page.locator("#diag-content-wrapper")).to_be_visible(timeout=15000)

    num_val = halo_page.locator("#diag-val-num").inner_text()

    # Clic en "Enviar Minuta por Correo"
    halo_page.locator("#btn-email-diag-minuta").click()
    halo_page.wait_for_timeout(300)

    # Modal de diagnóstico se cierra y se abre el modal de correo
    expect(halo_page.locator("#modal-executive-diagnosis")).not_to_be_visible()
    email_modal = halo_page.locator("#email-ticket-modal")
    expect(email_modal).to_be_visible()

    # Validar campos precargados
    destinatario = halo_page.locator("#email-destinatario").input_value()
    assert "alejandro.aguilarm@clarovtr.cl" in destinatario

    asunto = halo_page.locator("#email-asunto").input_value()
    assert "[HALO]" in asunto and "Diagnóstico" in asunto

    cuerpo = halo_page.locator("#email-cuerpo").input_value()
    assert "DIAGNÓSTICO EJECUTIVO HALO" in cuerpo
    assert num_val in cuerpo

    # Cerrar modal de correo
    halo_page.locator("#btn-close-email-modal-icon").click()
    expect(email_modal).not_to_be_visible()


def test_diagnostico_ejecutivo_drilldown_integration(halo_page: Page, base_url: str):
    """
    CP-DIAG-E2E-05: Validar botón de Diagnóstico Ejecutivo en vista Drill Down y comportamiento Kill-Switch.
    """
    _setup_app_session(halo_page, base_url)

    # Entrar a drilldown en el primer proyecto
    open_project_row(halo_page.locator("#projects-table-body tr.project-row").first)
    expect(halo_page.locator("#project-drilldown-section")).to_be_visible(timeout=10000)

    # Botón en toolbar de drilldown visible cuando Diagnóstico está ON
    btn_dd_diag = halo_page.locator("#btn-drilldown-diagnostico")
    expect(btn_dd_diag).to_be_visible()

    # Clic en Diagnóstico Ejecutivo desde drilldown
    btn_dd_diag.click()
    diag_modal = halo_page.locator("#modal-executive-diagnosis")
    expect(diag_modal).to_be_visible()
    expect(halo_page.locator("#diag-content-wrapper")).to_be_visible(timeout=15000)

    # Cerrar modal
    halo_page.locator("#btn-close-diag-modal").click()
    expect(diag_modal).not_to_be_visible()

    # Volver a lista de proyectos
    halo_page.locator("#back-to-projects-btn").click()
    expect(halo_page.locator("#project-drilldown-section")).not_to_be_visible()
    expect(halo_page.locator("#projects-table-body")).to_be_visible()

    # Apagar Kill-Switch y volver a drilldown
    click_user_menu_control(halo_page, "#diag-toggle-btn")
    halo_page.wait_for_timeout(300)

    open_project_row(halo_page.locator("#projects-table-body tr.project-row").first)
    expect(halo_page.locator("#project-drilldown-section")).to_be_visible(timeout=10000)

    # En Kill-Switch OFF, el botón de diagnóstico en drilldown debe estar oculto
    expect(btn_dd_diag).not_to_be_visible()
