"""
PRUEBAS FUNCIONALES Y DE UI: EXPORTACIÓN DE FICHA EJECUTIVA A PDF & KILL-SWITCH
Especificación: SPECS_FICHA_EJECUTIVA_PDF.md
"""

import pytest
import datetime
from unittest.mock import patch
from fastapi.testclient import TestClient
from playwright.sync_api import Page, expect

from backend.main import app
from backend.db import generar_ficha_ejecutiva_html
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
    halo_page.evaluate("() => localStorage.removeItem('halo_export_pdf_enabled')")
    halo_page.reload()
    halo_page.wait_for_selector("#app-view", state="visible", timeout=25000)
    halo_page.wait_for_function("() => window.App && window.App.isInitialized === true", timeout=25000)
    halo_page.wait_for_selector("#projects-table-body tr", state="visible", timeout=15000)


@pytest.fixture
def auth_headers():
    token = create_access_token({"username": "alejandro.aguilar", "rol": "ADMIN"})
    return {"Cookie": f"access_token={token}"}


# ==============================================================================
# FT-PDF-01: Estado Inicial del Kill-Switch en HTML (ON por defecto)
# ==============================================================================
def test_kill_switch_pdf_default_on():
    """
    Verifica que en el HTML base el botón toggle de PDF esté presente con label 'Ficha PDF: ON'
    y sin la clase 'is-off'.
    """
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    assert 'id="pdf-export-toggle-btn"' in html
    assert 'aria-pressed="true"' in html
    assert 'id="pdf-toggle-label"' in html
    assert 'Ficha PDF: ON' in html
    assert 'id="btn-drilldown-export-pdf"' in html
    assert 'aria-label="Exportar Ficha Ejecutiva a PDF"' in html
    assert 'Exportar ficha (PDF)' in html


# ==============================================================================
# FT-PDF-02: Kill-Switch y Política de Cero Rastros
# ==============================================================================
def test_kill_switch_pdf_toggle_off_cero_rastros():
    """
    Verifica que las clases de estilo de Cero Rastros estén definidas en styles.css
    para #pdf-export-toggle-btn.is-off y .btn-pdf-export-action.
    """
    res = client.get("/css/styles.css")
    assert res.status_code == 200
    css = res.text

    assert ".btn-pdf-export-action" in css
    assert "#pdf-export-toggle-btn.is-off" in css
    assert "var(--primary)" in css


# ==============================================================================
# FT-PDF-03: HTML Imprimible Contiene Tokens HALO Institucionales
# ==============================================================================
def test_html_imprimible_contiene_tokens_halo():
    """
    Verifica que la plantilla HTML autónoma contenga la paleta institucional (#B52217, #0097A9),
    las reglas de diagramación A4 y los bloques de control.
    """
    sample_data = {
        "folio": "HALO-FE-2026-108920-F7A2",
        "fecha_emision_formateada": "23/09/2026 16:00",
        "usuario_generador": "alejandro.aguilar",
        "proyecto": {
            "numero_proyecto": "0000108920",
            "cliente": "BANCO DE CHILE",
            "lt_asignado": "ALEJANDRO AGUILAR",
            "solicitante": "CARLOS PEREZ",
            "estado_sp": "Atendido",
            "tipo_servicio": "Conectividad IP",
            "antiguedad_dias": 60,
            "salud": {"score": "CRITICAL", "color": "red", "label": "Crítico"}
        },
        "kpis": {
            "total_solots": 5,
            "solots_ejecutadas": 3,
            "solots_vencidas": 1,
            "solots_por_vencer": 1,
            "porcentaje_avance_solots": 60.0,
            "total_tickets": 4,
            "tickets_abiertos": 2,
            "tickets_criticos": 1,
            "total_rfcs": 2,
            "rfcs_abiertas": 1
        },
        "diagnostico_sintetico": {
            "cuellos_de_botella": [
                {
                    "severidad": "CRITICA",
                    "identificador": "OTP-883491",
                    "descripcion": "Solot vencida hace 12 días.",
                    "responsable_area": "Operaciones SGA"
                }
            ],
            "recomendaciones": [
                {
                    "prioridad": "URGENTE",
                    "destinatario": "Jefatura Torre Linux",
                    "accion": "Escalar ticket detenido."
                }
            ]
        },
        "tablas": {
            "solots": [
                {
                    "id_otp": 883491,
                    "nro_proyecto": "0000108920",
                    "descr_otp": "Enlace de contingencia",
                    "estado_otp": "En Proceso",
                    "fecha_compromiso_fmt": "11/09/2026",
                    "dias_atraso": 12,
                    "estado_alerta": "VENCIDA",
                    "servicio": "Datos"
                }
            ],
            "tickets": [
                {
                    "cc_incident_id": "SD1098421",
                    "brief_description": "Reglas de Firewall",
                    "assigned_group": "Torre Linux",
                    "assigned_to": "JUAN PEREZ",
                    "severity": "Alta",
                    "submit_date_fmt": "05/09/2026",
                    "dias_abierto": 18,
                    "estado_alerta": "CRITICO",
                    "status": "Asignado"
                }
            ],
            "rfcs": [
                {
                    "number": "RFC-2026-4401",
                    "brief_description": "Pase a producción túnel",
                    "requested_by": "CARLOS PEREZ",
                    "assign_dept": "Gestión de Cambios",
                    "estado": "En Proceso",
                    "close_time_fmt": "Pendiente"
                }
            ]
        }
    }

    doc_html = generar_ficha_ejecutiva_html(sample_data, auto_print=False)

    # 1. Colores institucionales
    assert "#B52217" in doc_html
    assert "#0097A9" in doc_html

    # 2. Directivas de impresión A4
    assert "@page" in doc_html
    assert "size: A4 portrait" in doc_html
    assert "@media print" in doc_html
    assert "-webkit-print-color-adjust: exact" in doc_html

    # 3. Membrete institucional y folio
    assert "CLARO CHILE — DIRECCIÓN DE OPERACIONES Y SERVICIOS TI" in doc_html
    assert "FICHA EJECUTIVA DE CONTROL OPERACIONAL DE PROYECTO" in doc_html
    assert "HALO-FE-2026-108920-F7A2" in doc_html
    assert "CONFIDENCIAL — USO INTERNO" in doc_html

    # 4. Datos del proyecto y tablas
    assert "0000108920" in doc_html
    assert "BANCO DE CHILE" in doc_html
    assert "ALEJANDRO AGUILAR" in doc_html
    assert "OTP-883491" in doc_html
    assert "SD1098421" in doc_html
    assert "RFC-2026-4401" in doc_html

    # 5. Firmas institucionales
    assert "JEFATURA DE OPERACIONES TI" in doc_html
    assert "Claro Chile S.A." in doc_html


# ==============================================================================
# FT-PDF-04: Regresión - Los Botones Adyacentes Mantienen su Jerarquía
# ==============================================================================
def test_regresion_no_afecta_botones_adyacentes():
    """
    Verifica que la integración de #btn-drilldown-export-pdf no altere
    la presencia ni la estructura de los botones adyacentes en el toolbar
    (btn-drilldown-diagnostico, btn-dd-edit-project, btn-dd-delete-project).
    """
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    assert 'id="btn-drilldown-export-pdf"' in html
    assert 'id="btn-drilldown-diagnostico"' in html
    assert 'id="btn-dd-edit-project"' in html
    assert 'id="btn-dd-delete-project"' in html

    # Verificar que el toolbar mantenga su contenedor flex
    assert 'class="drilldown-action-toolbar"' in html


# ==============================================================================
# FT-PDF-E2E-01: Toggle Kill-Switch UI & Ocultamiento Dinámico en Drill Down
# ==============================================================================
def test_e2e_pdf_export_toggle_ui_and_killswitch(halo_page: Page, base_url: str):
    """
    CP-PDF-E2E-01: Validar toggle UI, Kill-Switch y Cero Rastros en Drill Down.
    """
    _setup_app_session(halo_page, base_url)

    # 1. Validar presencia del botón toggle y estado inicial ON
    toggle_btn = halo_page.locator("#pdf-export-toggle-btn")
    open_user_menu(halo_page)
    expect(toggle_btn).to_be_visible()
    close_user_menu(halo_page)
    expect(halo_page.locator("#pdf-toggle-label")).to_have_text("Ficha PDF: ON")
    assert "is-off" not in (toggle_btn.get_attribute("class") or "")
    assert toggle_btn.get_attribute("aria-pressed") == "true"

    # 2. Apagar Kill-Switch (Toggle OFF)
    open_user_menu(halo_page)
    toggle_btn.click()
    close_user_menu(halo_page)
    halo_page.wait_for_timeout(300)
    expect(halo_page.locator("#pdf-toggle-label")).to_have_text("Ficha PDF: OFF")
    assert "is-off" in (toggle_btn.get_attribute("class") or "")
    assert toggle_btn.get_attribute("aria-pressed") == "false"

    # 3. Entrar a Drill Down de primer proyecto y validar CERO RASTROS
    halo_page.locator("#projects-table-body tr.project-row").first.locator("td").first.click()
    expect(halo_page.locator("#project-drilldown-section")).to_be_visible(timeout=10000)

    btn_dd_pdf = halo_page.locator("#btn-drilldown-export-pdf")
    expect(btn_dd_pdf).not_to_be_visible()

    # Botones adyacentes deben seguir visibles
    expect(halo_page.locator("#btn-drilldown-diagnostico")).to_be_visible()

    # 4. Volver a proyectos y reactivar Kill-Switch
    halo_page.locator("#back-to-projects-btn").click()
    expect(halo_page.locator("#project-drilldown-section")).not_to_be_visible()
    expect(halo_page.locator("#projects-table-body")).to_be_visible()

    open_user_menu(halo_page)
    toggle_btn.click()
    close_user_menu(halo_page)
    halo_page.wait_for_timeout(300)
    expect(halo_page.locator("#pdf-toggle-label")).to_have_text("Ficha PDF: ON")
    assert "is-off" not in (toggle_btn.get_attribute("class") or "")
    assert toggle_btn.get_attribute("aria-pressed") == "true"

    # 5. Volver a Drill Down y comprobar que el botón reaparece de forma reactiva
    halo_page.locator("#projects-table-body tr.project-row").first.locator("td").first.click()
    expect(halo_page.locator("#project-drilldown-section")).to_be_visible(timeout=10000)
    expect(btn_dd_pdf).to_be_visible()


# ==============================================================================
# FT-PDF-E2E-02: Exportación de Ficha a PDF mediante Iframe Oculto
# ==============================================================================
def test_e2e_pdf_export_drilldown_click_and_iframe_generation(halo_page: Page, base_url: str):
    """
    CP-PDF-E2E-02: Validar generación del iframe de impresión corporativo al pulsar exportar.
    """
    _setup_app_session(halo_page, base_url)

    # Entrar a drilldown
    halo_page.locator("#projects-table-body tr.project-row").first.locator("td").first.click()
    expect(halo_page.locator("#project-drilldown-section")).to_be_visible(timeout=10000)

    btn_dd_pdf = halo_page.locator("#btn-drilldown-export-pdf")
    expect(btn_dd_pdf).to_be_visible()

    # Interceptar print en iframe para evitar bloqueos en navegador headless
    halo_page.add_init_script("""
        window.__printInvoked = false;
        const originalPrint = window.print;
        window.print = function() { window.__printInvoked = true; };
    """)

    # Monitorear respuesta de red de ficha-html
    with halo_page.expect_response(lambda response: "/api/proyectos/" in response.url and "/ficha-html" in response.url) as response_info:
        btn_dd_pdf.click()

    response = response_info.value
    assert response.status == 200
    assert "text/html" in response.headers.get("content-type", "")

    # Verificar que el iframe oculto #halo-print-iframe fue creado en el DOM
    halo_page.wait_for_selector("#halo-print-iframe", state="attached", timeout=10000)

    # Validar contenido dentro del iframe
    frame = halo_page.frame_locator("#halo-print-iframe")
    expect(frame.locator("body")).to_contain_text("CLARO CHILE — DIRECCIÓN DE OPERACIONES Y SERVICIOS TI", timeout=10000)
    expect(frame.locator("body")).to_contain_text("FICHA EJECUTIVA DE CONTROL OPERACIONAL DE PROYECTO")

    # Validar toast de éxito
    expect(halo_page.locator("#toast-container")).to_contain_text("Ficha ejecutiva enviada al diálogo de impresión/PDF", timeout=10000)


# ==============================================================================
# FT-PDF-E2E-03: Accesibilidad ARIA y Navegación por Teclado
# ==============================================================================
def test_e2e_pdf_export_aria_and_keyboard_accessibility(halo_page: Page, base_url: str):
    """
    CP-PDF-E2E-03: Validar atributos ARIA y activación por teclado (Space/Enter).
    """
    _setup_app_session(halo_page, base_url)

    toggle_btn = halo_page.locator("#pdf-export-toggle-btn")
    open_user_menu(halo_page)
    expect(toggle_btn).to_be_visible()
    close_user_menu(halo_page)
    assert toggle_btn.get_attribute("aria-pressed") == "true"
    assert toggle_btn.get_attribute("aria-label") == "Toggle Exportación PDF"

    # Foco y pulsación con Space
    open_user_menu(halo_page)
    toggle_btn.focus()
    halo_page.keyboard.press("Space")
    halo_page.wait_for_timeout(300)
    expect(halo_page.locator("#pdf-toggle-label")).to_have_text("Ficha PDF: OFF")
    assert toggle_btn.get_attribute("aria-pressed") == "false"

    # Pulsación con Enter para reactivar
    open_user_menu(halo_page)
    toggle_btn.focus()
    halo_page.keyboard.press("Enter")
    halo_page.wait_for_timeout(300)
    expect(halo_page.locator("#pdf-toggle-label")).to_have_text("Ficha PDF: ON")
    assert toggle_btn.get_attribute("aria-pressed") == "true"

    # Verificar accesibilidad en drilldown
    halo_page.locator("#projects-table-body tr.project-row").first.locator("td").first.click()
    expect(halo_page.locator("#project-drilldown-section")).to_be_visible(timeout=10000)
    btn_dd_pdf = halo_page.locator("#btn-drilldown-export-pdf")
    expect(btn_dd_pdf).to_be_visible()
    assert btn_dd_pdf.get_attribute("aria-label") == "Exportar Ficha Ejecutiva a PDF"


# ==============================================================================
# FT-PDF-E2E-04: Persistencia en LocalStorage y Cero Rastros tras Recarga (F5)
# ==============================================================================
def test_e2e_pdf_export_persistence_and_cero_rastros_on_reload(halo_page: Page, base_url: str):
    """
    CP-PDF-E2E-04: Validar que si Kill-Switch está desactivado, tras recarga F5 se mantiene apagado y con Cero Rastros.
    """
    _setup_app_session(halo_page, base_url)

    # 1. Desactivar Kill-Switch
    toggle_btn = halo_page.locator("#pdf-export-toggle-btn")
    open_user_menu(halo_page)
    toggle_btn.click()
    close_user_menu(halo_page)
    halo_page.wait_for_timeout(300)
    expect(halo_page.locator("#pdf-toggle-label")).to_have_text("Ficha PDF: OFF")

    # 2. Recargar página (F5)
    halo_page.reload()
    halo_page.wait_for_selector("#app-view", state="visible", timeout=25000)
    halo_page.wait_for_function("() => window.App && window.App.isInitialized === true", timeout=25000)
    halo_page.wait_for_selector("#projects-table-body tr", state="visible", timeout=15000)

    # 3. Comprobar que persiste en estado OFF
    expect(halo_page.locator("#pdf-toggle-label")).to_have_text("Ficha PDF: OFF")
    assert "is-off" in (halo_page.locator("#pdf-export-toggle-btn").get_attribute("class") or "")

    # 4. Ir a Drill Down y comprobar Cero Rastros
    halo_page.locator("#projects-table-body tr.project-row").first.locator("td").first.click()
    expect(halo_page.locator("#project-drilldown-section")).to_be_visible(timeout=10000)
    expect(halo_page.locator("#btn-drilldown-export-pdf")).not_to_be_visible()

    # Limpiar localStorage al finalizar
    halo_page.evaluate("() => localStorage.removeItem('halo_export_pdf_enabled')")

