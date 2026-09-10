"""
Test Suite: Automatización de Tickets y Peticiones Relacionadas con Logout Limpio
Valida el cumplimiento íntegro de SPECS_TICKET_GENERATOR_PETICIONES.md:
- Formateo y contrato de eventos SSE.
- Generador asíncrono `stream_ticket_creation` con doble identificador (SD + Petición).
- Integración de API en `/api/automation/create-ticket`.
- Estructura DOM del modal con doble ID y botones de copiado.
"""

import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from backend.main import app, TicketCreationRequest
from backend.ticket_automation import (
    format_sse,
    copy_id_to_clipboard,
    stream_ticket_creation,
    vincular_peticion_relacionada,
    DEFAULT_CONTACTO,
    DEFAULT_TITULO,
    DEFAULT_DESCRIPCION,
    DEFAULT_GRUPO,
    DEFAULT_AREA,
    DEFAULT_SUBAREA,
    DEFAULT_DETALLE,
)
from tests.conftest import create_access_token


@pytest.fixture
def auth_headers():
    """Generates an authorization header with a valid JWT token for an ADMIN user."""
    token_data = {
        "sub": "aaguilar",
        "nombre_completo": "Alejandro Aguilar",
        "lt_asignado": "Alejandro Aguilar",
        "rol": "ADMIN"
    }
    token = create_access_token(token_data)
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# 1. PRUEBAS UNITARIAS: FORMATEO Y PROTOCOLO SSE
# ==============================================================================
def test_format_sse_basic():
    """Verifica que format_sse formatee correctamente el prefijo data: y los saltos de línea."""
    payload = {"type": "log", "message": "Iniciando proceso...", "level": "info", "progress": 5}
    formatted = format_sse(payload)
    assert formatted.startswith("data: ")
    assert formatted.endswith("\n\n")
    data_content = formatted[len("data: "):-2]
    parsed = json.loads(data_content)
    assert parsed["type"] == "log"
    assert parsed["message"] == "Iniciando proceso..."
    assert parsed["level"] == "info"
    assert parsed["progress"] == 5


def test_format_sse_complete_event():
    """Verifica el payload completo de finalización con ambos identificadores (SD y Petición)."""
    complete_payload = {
        "type": "complete",
        "status": "success",
        "ticket_id": "SD1049281",
        "peticion_id": "PET001234",
        "message": "Interacción y Petición creadas con éxito",
        "data": {
            "ticket_id": "SD1049281",
            "peticion_id": "PET001234",
            "contacto": "ALEJANDRO JAVIER AGUILAR MORALES",
            "titulo": "Creacion test automatizacion",
            "grupo": "Lideres Tecnicos",
            "area": "Proyectos",
            "subarea": "Apoyo habilitacion cliente",
            "detalle": "Apoyo habilitacion cliente"
        }
    }
    formatted = format_sse(complete_payload)
    parsed = json.loads(formatted[len("data: "):-2])
    assert parsed["type"] == "complete"
    assert parsed["ticket_id"] == "SD1049281"
    assert parsed["peticion_id"] == "PET001234"
    assert parsed["data"]["ticket_id"] == "SD1049281"
    assert parsed["data"]["peticion_id"] == "PET001234"


def test_copy_id_to_clipboard_tolerant():
    """Verifica que copy_id_to_clipboard maneje excepciones silenciosamente sin fallar."""
    # Test when pyperclip is available but fails
    mock_pyperclip = MagicMock()
    mock_pyperclip.copy.side_effect = Exception("No display available")
    with patch.dict("sys.modules", {"pyperclip": mock_pyperclip}):
        copy_id_to_clipboard("SD1234567")
        mock_pyperclip.copy.assert_called_once_with("SD1234567")

    # Test when pyperclip is not available (normal in headless)
    with patch.dict("sys.modules", {"pyperclip": None}):
        copy_id_to_clipboard("SD1234567")


# ==============================================================================
# 2. PRUEBAS PYDANTIC Y CONTRATO DE ENTRADA
# ==============================================================================
def test_ticket_creation_request_defaults():
    """Verifica los valores por defecto del schema TicketCreationRequest."""
    req = TicketCreationRequest(
        titulo="Título de Prueba",
        descripcion="Descripción de Prueba"
    )
    assert req.contacto == DEFAULT_CONTACTO
    assert req.titulo == "Título de Prueba"
    assert req.descripcion == "Descripción de Prueba"
    assert req.area == DEFAULT_AREA
    assert req.subarea == DEFAULT_SUBAREA
    assert req.detalle == DEFAULT_DETALLE
    assert req.grupo == DEFAULT_GRUPO
    assert req.impacto == "3 - Menor (Existen WorkAround)"
    assert req.urgencia == "3 - Media (Resolución a mediano plazo)"
    assert req.usuario_peticion == "Alejandro.Aguilar"
    assert req.headless is True


def test_ticket_creation_request_validation():
    """Verifica que omitir título o descripción lance error de validación en Pydantic."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        TicketCreationRequest(titulo="Solo titulo")
    with pytest.raises(ValidationError):
        TicketCreationRequest(descripcion="Solo descripcion")


def test_ticket_creation_request_custom():
    """Verifica la asignación de campos personalizados en TicketCreationRequest."""
    custom_data = {
        "contacto": "JUAN PEREZ",
        "titulo": "Ticket Personalizado",
        "descripcion": "Descripción Detallada",
        "area": "Redes",
        "subarea": "Conectividad",
        "detalle": "Enlace Caído",
        "grupo": "Soporte N2",
        "impacto": "1 - Crítico",
        "urgencia": "1 - Alta",
        "usuario_peticion": "Juan.Perez",
        "headless": False
    }
    req = TicketCreationRequest(**custom_data)
    assert req.contacto == "JUAN PEREZ"
    assert req.titulo == "Ticket Personalizado"
    assert req.grupo == "Soporte N2"
    assert req.usuario_peticion == "Juan.Perez"
    assert req.headless is False


# ==============================================================================
# 3. PRUEBAS ASÍNCRONAS: GENERADOR DE STREAMING CON PLAYWRIGHT MOCKEADO
# ==============================================================================
@pytest.mark.asyncio
async def test_stream_ticket_creation_full_lifecycle():
    """
    Ejecuta el ciclo de vida completo de stream_ticket_creation con Playwright simulado
    y valida la emisión de eventos de progreso, captura de SD, Petición y Logout.
    """
    # Configuración de Mocks de Playwright
    mock_playwright = AsyncMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_frame = AsyncMock()

    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.pages = [mock_page]
    mock_context.on = MagicMock()
    mock_page.frames = [mock_frame]

    # Simulación de elementos y acciones en página y frames
    mock_loc = AsyncMock()
    mock_loc.first = mock_loc
    mock_loc.count = AsyncMock(return_value=1)
    mock_loc.input_value = AsyncMock(side_effect=["Alejandro.Aguilar", "Cl4r0.2026**", "Alejandro.Aguilar", "Cl4r0.2026**"])
    mock_loc.evaluate = AsyncMock(return_value="OK")
    mock_loc.is_visible = AsyncMock(return_value=True)

    mock_page.get_by_role = MagicMock(return_value=mock_loc)
    mock_page.get_by_text = MagicMock(return_value=mock_loc)
    mock_frame.get_by_role = MagicMock(return_value=mock_loc)
    mock_frame.locator = MagicMock(return_value=mock_loc)

    with patch("backend.ticket_automation.async_playwright") as mock_ap, \
         patch("backend.ticket_automation.click_servicios_internos", new_callable=AsyncMock) as mock_csi, \
         patch("backend.ticket_automation.fill_descripcion", new_callable=AsyncMock) as mock_fdesc, \
         patch("backend.ticket_automation.fill_by_label", new_callable=AsyncMock) as mock_fbl, \
         patch("backend.ticket_automation.fill_grupo", new_callable=AsyncMock) as mock_fgrupo, \
         patch("backend.ticket_automation.click_guardar", new_callable=AsyncMock) as mock_cg, \
         patch("backend.ticket_automation.get_ticket_id", new_callable=AsyncMock, return_value="SD1049999") as mock_gtid, \
         patch("backend.ticket_automation.find_registros_relacionados_frame", new_callable=AsyncMock, return_value=(mock_frame, mock_loc)) as mock_frr, \
         patch("backend.ticket_automation.click_expandir_lista_registros", new_callable=AsyncMock) as mock_celr, \
         patch("backend.ticket_automation.click_vincular_nuevo_registro", new_callable=AsyncMock) as mock_cvnr, \
         patch("backend.ticket_automation.click_alejandro_aguilar_option", new_callable=AsyncMock) as mock_caao, \
         patch("backend.ticket_automation.click_guardar_peticion", new_callable=AsyncMock) as mock_cgp, \
         patch("backend.ticket_automation.get_peticion_id", new_callable=AsyncMock, return_value="PET009988") as mock_gpid, \
         patch("backend.ticket_automation.click_guardar_registro_y_salir", new_callable=AsyncMock) as mock_cgrs, \
         patch("backend.ticket_automation.click_guardar_y_salir_final", new_callable=AsyncMock) as mock_cgsf, \
         patch("backend.ticket_automation.logout", new_callable=AsyncMock) as mock_lout:

        mock_ap.return_value.start = AsyncMock(return_value=mock_playwright)
        mock_csi.return_value = mock_frame

        events = []
        async for sse_chunk in stream_ticket_creation({
            "contacto": "ALEJANDRO JAVIER AGUILAR MORALES",
            "titulo": "Test E2E",
            "descripcion": "Detalle E2E",
            "area": "Proyectos",
            "subarea": "Apoyo",
            "detalle": "Apoyo",
            "grupo": "Lideres Tecnicos",
            "headless": True
        }):
            assert sse_chunk.startswith("data: ")
            payload = json.loads(sse_chunk[len("data: "):-2])
            events.append(payload)

        # Verificaciones del flujo completo
        event_types = [e["type"] for e in events]
        assert "log" in event_types
        assert "complete" in event_types

        # Validar evento final complete
        complete_event = next(e for e in events if e["type"] == "complete")
        assert complete_event["status"] == "success"
        assert complete_event["ticket_id"] == "SD1049999"
        assert complete_event["peticion_id"] == "PET009988"
        assert complete_event["data"]["ticket_id"] == "SD1049999"
        assert complete_event["data"]["peticion_id"] == "PET009988"

        # Validar llamadas a las funciones orquestadas de forma lineal directa
        mock_gtid.assert_awaited_once()
        assert mock_frr.await_count >= 1
        mock_celr.assert_awaited_once()
        mock_cvnr.assert_awaited_once()
        mock_caao.assert_awaited_once()
        mock_cgp.assert_awaited_once()
        mock_gpid.assert_awaited_once()
        mock_cgrs.assert_awaited_once()
        mock_cgsf.assert_awaited_once()
        mock_lout.assert_awaited_once()
        mock_context.close.assert_awaited_once()
        mock_browser.close.assert_awaited_once()
        mock_playwright.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_vincular_peticion_relacionada_helper():
    """Valida la ejecución del helper vincular_peticion_relacionada con emisión de logs opcional."""
    mock_context = AsyncMock()
    mock_frame = AsyncMock()
    mock_loc = AsyncMock()
    mock_loc.first = mock_loc
    mock_loc.count = AsyncMock(return_value=1)
    mock_frame.get_by_role = MagicMock(return_value=mock_loc)
    mock_frame.locator = MagicMock(return_value=mock_loc)
    mock_context.pages = []

    logs_emitted = []
    async def _emit_log(msg, lvl, prog):
        logs_emitted.append((msg, lvl, prog))

    with patch("backend.ticket_automation.find_registros_relacionados_frame", new_callable=AsyncMock, return_value=(mock_frame, mock_loc)), \
         patch("backend.ticket_automation.click_expandir_lista_registros", new_callable=AsyncMock) as mock_celr, \
         patch("backend.ticket_automation.click_vincular_nuevo_registro", new_callable=AsyncMock) as mock_cvnr, \
         patch("backend.ticket_automation.click_alejandro_aguilar_option", new_callable=AsyncMock) as mock_caao, \
         patch("backend.ticket_automation.click_guardar_peticion", new_callable=AsyncMock) as mock_cgp, \
         patch("backend.ticket_automation.get_peticion_id", new_callable=AsyncMock, return_value="PET001122") as mock_gpid, \
         patch("backend.ticket_automation.click_guardar_registro_y_salir", new_callable=AsyncMock) as mock_cgrs, \
         patch("backend.ticket_automation.click_guardar_y_salir_final", new_callable=AsyncMock) as mock_cgsf:

        res = await vincular_peticion_relacionada(mock_context, emit_log_fn=_emit_log)
        assert res == "PET001122"
        assert len(logs_emitted) >= 5
        mock_celr.assert_awaited_once()
        mock_cvnr.assert_awaited_once()
        mock_caao.assert_awaited_once()
        mock_cgp.assert_awaited_once()
        mock_gpid.assert_awaited_once()
        mock_cgrs.assert_awaited_once()
        mock_cgsf.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_ticket_creation_error_handling():
    """Verifica que las excepciones emitan un evento de error y liberen recursos en el bloque finally."""
    mock_playwright = AsyncMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()

    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.on = MagicMock()
    mock_context.new_page = AsyncMock(side_effect=RuntimeError("Error simulado de conexión"))

    with patch("backend.ticket_automation.async_playwright") as mock_ap:
        mock_ap.return_value.start = AsyncMock(return_value=mock_playwright)

        events = []
        async for sse_chunk in stream_ticket_creation({"headless": True}):
            payload = json.loads(sse_chunk[len("data: "):-2])
            events.append(payload)

        error_event = next((e for e in events if e["type"] == "error"), None)
        assert error_event is not None
        assert "Error simulado de conexión" in error_event["message"]

        # Verificación de cleanup
        mock_context.close.assert_awaited_once()
        mock_browser.close.assert_awaited_once()
        mock_playwright.stop.assert_awaited_once()


# ==============================================================================
# 4. PRUEBAS DE ENDPOINT API: /api/automation/create-ticket
# ==============================================================================
def test_create_ticket_api_auth_required():
    """Verifica que el endpoint rechace peticiones sin cabecera de autenticación JWT."""
    client = TestClient(app)
    response = client.post("/api/automation/create-ticket", json={})
    assert response.status_code == 401


def test_create_ticket_api_streaming(auth_headers):
    """
    Verifica que el endpoint autenticado responda con status 200 y media_type text/event-stream.
    """
    client = TestClient(app)

    async def _mock_stream(params):
        yield format_sse({"type": "log", "message": "Iniciando...", "level": "info", "progress": 5})
        yield format_sse({"type": "complete", "status": "success", "ticket_id": "SD8888888", "peticion_id": "PET7777777"})

    with patch("backend.main.stream_ticket_creation", side_effect=_mock_stream):
        response = client.post(
            "/api/automation/create-ticket",
            headers=auth_headers,
            json={
                "contacto": "ALEJANDRO JAVIER AGUILAR MORALES",
                "titulo": "Test API",
                "descripcion": "Descripción API",
                "area": "Proyectos",
                "subarea": "Apoyo",
                "detalle": "Apoyo",
                "grupo": "Lideres Tecnicos"
            }
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        lines = [line for line in response.text.split("\n") if line.startswith("data:")]
        assert len(lines) >= 2
        complete_json = json.loads(lines[-1][len("data: "):])
        assert complete_json["type"] == "complete"
        assert complete_json["ticket_id"] == "SD8888888"
        assert complete_json["peticion_id"] == "PET7777777"


# ==============================================================================
# 5. PRUEBAS DOM / FRONTEND: MODAL DE ÉXITO CON DOBLE ID
# ==============================================================================
def test_frontend_index_html_modal_structure():
    """
    Verifica que frontend/index.html contenga todos los elementos, IDs y clases requeridos
    para la visualización destacada de ambos identificadores (SD + Petición).
    """
    index_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Modal container
    assert 'id="ticket-success-modal"' in html

    # Dual ID grid layout
    assert 'class="ticket-dual-id-grid"' in html

    # Tarjeta 1: ID Interacción (SD)
    assert 'id="ticket-success-id"' in html
    assert 'id="btn-copy-ticket-id"' in html
    assert 'id="copy-ticket-btn-text"' in html
    assert 'id="ticket-copy-feedback"' in html

    # Tarjeta 2: ID Petición Relacionada
    assert "ticket-id-box-peticion" in html
    assert 'id="peticion-success-id"' in html
    assert 'id="btn-copy-peticion-id"' in html
    assert 'id="copy-peticion-btn-text"' in html
    assert 'id="peticion-copy-feedback"' in html

    # Resumen estructurado
    assert 'id="modal-summary-contacto"' in html
    assert 'id="modal-summary-titulo"' in html
    assert 'id="modal-summary-grupo"' in html
    assert 'id="modal-summary-area"' in html
    assert 'id="modal-summary-usuario-peticion"' in html
    assert 'id="modal-summary-logout-status"' in html

    # Botón de copiado integral y botón de cierre
    assert 'id="btn-copy-both-ids"' in html
    assert 'id="btn-close-success-modal"' in html
    assert 'id="btn-close-modal-icon"' in html


def test_frontend_css_styles():
    """
    Verifica que frontend/css/styles.css contenga las reglas para la cuadrícula dual,
    los estilos de petición, botones de éxito y compatibilidad con tema oscuro.
    """
    css_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "css", "styles.css")
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()

    assert ".ticket-dual-id-grid" in css
    assert ".ticket-id-box-peticion" in css
    assert ".peticion-value" in css
    assert ".btn-accent" in css
    assert ".btn-success" in css
    assert '[data-theme="dark"] .btn-success' in css
    assert '[data-theme="dark"] .ticket-id-box-peticion' in css
    assert '[data-theme="dark"] .ticket-id-value.peticion-value' in css


def test_frontend_js_app_methods():
    """
    Verifica que frontend/js/app.js implemente los métodos y enlaces para manejar
    el flujo de SD + Petición, copiado al portapapeles y accesibilidad de foco.
    """
    js_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "js", "app.js")
    with open(js_path, "r", encoding="utf-8") as f:
        js = f.read()

    assert "openTicketSuccessModal" in js
    assert "copyTicketIdToClipboard" in js
    assert "copyPeticionIdToClipboard" in js
    assert "copyBothIdsToClipboard" in js
    assert "btn-copy-peticion-id" in js
    assert "btn-copy-both-ids" in js
    assert "peticion_id" in js
    assert "btn-close-success-modal" in js


def test_frontend_index_html_accessibility():
    """
    Verifica que el modal de éxito tenga atributos ARIA de accesibilidad:
    aria-modal='true', role='dialog', aria-labelledby='modal-success-title', y tabindex='-1'.
    """
    index_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'aria-labelledby="modal-success-title"' in html
    assert 'tabindex="-1"' in html
    assert 'aria-label="Cerrar modal"' in html


def test_frontend_index_html_catalogs():
    """
    Verifica que el formulario de tickets contenga los catálogos oficiales completos
    y no contenga valores de prueba hardcodeados.
    """
    index_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Contactos (5)
    assert 'value="ALEJANDRO JAVIER AGUILAR MORALES"' in html
    assert 'value="JUAN BARRERA RAMOS"' in html
    assert 'value="SAMUEL PAREDES SAEZ"' in html
    assert 'value="SOLANGE ANGELICA ORTIZ VIROLDE"' in html
    assert 'value="Erwin Patricio Sandoval Cadiz"' in html

    # Grupos (11)
    assert 'value="Lideres Tecnicos"' in html
    assert 'value="ProvisionConectividadTI"' in html
    assert 'value="ProvisionVirtualizacionTI"' in html
    assert 'value="Plataforma T3 / Soporte Especializado"' in html
    assert 'value="Torre Linux"' in html
    assert 'value="Torre Microsoft"' in html
    assert 'value="Torre Monitoreo"' in html
    assert 'value="Torre Plataformas Internas"' in html
    assert 'value="Torre Respaldos"' in html
    assert 'value="Torre SAP"' in html
    assert 'value="Torre Virtualizacion"' in html

    # Impacto (3)
    assert 'value="1 - Alto (Perdida Total)"' in html
    assert 'value="2 - Moderada (Perdida Parcial)"' in html
    assert 'value="3 - Menor (Existen WorkAround)"' in html

    # Urgencia (4)
    assert 'value="1 - Crítica (Atención Inmediata)"' in html
    assert 'value="2 - Alta (Resolución a corto plazo)"' in html
    assert 'value="3 - Media (Resolución a mediano plazo)"' in html
    assert 'value="4 - Baja (No requiere urgencia)"' in html

    # Placeholders e inputs limpios (sin value="Creacion test...")
    assert 'placeholder="Ingresa el título o resumen del requerimiento' in html
    assert 'placeholder="Detalla el alcance, requerimiento técnico' in html
    assert 'value="Creacion test automatizacion"' not in html
    assert 'Prueba test automatización</textarea>' not in html


@pytest.mark.asyncio
async def test_stream_ticket_creation_cleanup_on_cancellation():
    """
    Verifica que si la ejecución es cancelada o interrumpida prematuramente,
    los recursos de Chromium y subprocesos se cierren correctamente.
    """
    mock_playwright = AsyncMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()

    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.on = MagicMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.pages = [mock_page]
    mock_page.frames = []

    with patch("backend.ticket_automation.async_playwright") as mock_ap, \
         patch("backend.ticket_automation.fill_login_credentials", side_effect=asyncio.CancelledError()):

        mock_ap.return_value.start = AsyncMock(return_value=mock_playwright)

        with pytest.raises(asyncio.CancelledError):
            async for _ in stream_ticket_creation({"headless": True}):
                pass

        # Validar que los recursos se limpian incluso en cancelación
        mock_context.close.assert_awaited_once()
        mock_browser.close.assert_awaited_once()
        mock_playwright.stop.assert_awaited_once()


# ==============================================================================
# 6. PRUEBAS E2E DE NAVEGADOR: GENERADOR DE TICKETS Y MODAL DUAL ID
# ==============================================================================
from playwright.sync_api import Page, expect

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
    page.wait_for_selector("#nav-btn-tickets", state="visible", timeout=10000)


def test_e2e_01_navigation_and_form_defaults(page: Page):
    """
    CP-E2E-01: Navegación al Generador de Tickets y Validación de Valores por Defecto
    - Autenticar y hacer clic en '🤖 Generador de Tickets'.
    - Verificar visibilidad del contenedor '#module-tickets-container'.
    - Verificar los valores prellenados del formulario (contacto, título, área, subárea, detalle, grupo, etc.).
    - Verificar estado inicial del botón de ejecución y la consola de logs.
    """
    helper_login(page)
    page.click("#nav-btn-tickets")

    container = page.locator("#module-tickets-container")
    expect(container).to_be_visible()

    # Campos por defecto y placeholders
    expect(page.locator("#ticket-contacto")).to_have_value("ALEJANDRO JAVIER AGUILAR MORALES")
    expect(page.locator("#ticket-titulo")).to_have_value("")
    expect(page.locator("#ticket-titulo")).to_have_attribute("placeholder", "Ingresa el título o resumen del requerimiento (ej: Habilitación enlace MPLS Cliente X)")
    expect(page.locator("#ticket-descripcion")).to_have_value("")
    expect(page.locator("#ticket-descripcion")).to_have_attribute("placeholder", "Detalla el alcance, requerimiento técnico, justificación y antecedentes necesarios...")
    expect(page.locator("#ticket-area")).to_have_value("Proyectos")
    expect(page.locator("#ticket-subarea")).to_have_value("Apoyo habilitacion cliente")
    expect(page.locator("#ticket-detalle")).to_have_value("Apoyo habilitacion cliente")
    expect(page.locator("#ticket-grupo")).to_have_value("Lideres Tecnicos")
    expect(page.locator("#ticket-impacto")).to_have_value("3 - Menor (Existen WorkAround)")
    expect(page.locator("#ticket-urgencia")).to_have_value("3 - Media (Resolución a mediano plazo)")

    # Verificar opciones de los dropdowns
    contacto_options = page.locator("#ticket-contacto option").all_inner_texts()
    assert len(contacto_options) == 5
    assert "ALEJANDRO JAVIER AGUILAR MORALES" in contacto_options
    assert "JUAN BARRERA RAMOS" in contacto_options
    assert "SAMUEL PAREDES SAEZ" in contacto_options
    assert "SOLANGE ANGELICA ORTIZ VIROLDE" in contacto_options
    assert "Erwin Patricio Sandoval Cadiz" in contacto_options

    grupo_options = page.locator("#ticket-grupo option").all_inner_texts()
    assert len(grupo_options) == 11
    assert "Lideres Tecnicos" in grupo_options
    assert "ProvisionConectividadTI" in grupo_options
    assert "ProvisionVirtualizacionTI" in grupo_options
    assert "Plataforma T3 / Soporte Especializado" in grupo_options
    assert "Torre Linux" in grupo_options
    assert "Torre Microsoft" in grupo_options
    assert "Torre Monitoreo" in grupo_options
    assert "Torre Plataformas Internas" in grupo_options
    assert "Torre Respaldos" in grupo_options
    assert "Torre SAP" in grupo_options
    assert "Torre Virtualizacion" in grupo_options

    impacto_options = page.locator("#ticket-impacto option").all_inner_texts()
    assert len(impacto_options) == 3
    assert "1 - Alto (Perdida Total)" in impacto_options
    assert "2 - Moderada (Perdida Parcial)" in impacto_options
    assert "3 - Menor (Existen WorkAround)" in impacto_options

    urgencia_options = page.locator("#ticket-urgencia option").all_inner_texts()
    assert len(urgencia_options) == 4
    assert "1 - Crítica (Atención Inmediata)" in urgencia_options
    assert "2 - Alta (Resolución a corto plazo)" in urgencia_options
    assert "3 - Media (Resolución a mediano plazo)" in urgencia_options
    assert "4 - Baja (No requiere urgencia)" in urgencia_options

    # Estado del botón y consola
    btn_exec = page.locator("#btn-execute-ticket")
    expect(btn_exec).to_be_visible()
    expect(btn_exec).to_be_enabled()
    expect(page.locator("#ticket-logs-console")).to_be_visible()
    expect(page.locator(".terminal-welcome-msg")).to_be_visible()


def test_e2e_02_console_controls_and_logs_interaction(page: Page):
    """
    CP-E2E-02: Interacción con Controles de la Consola de Logs
    - Verificar alternancia del botón de Auto-scroll (ON / OFF).
    - Insertar entradas de log de prueba en el DOM y verificar el contador de eventos.
    - Presionar botón de Limpiar Logs y verificar reseteo del contador y restauración del mensaje de bienvenida.
    """
    helper_login(page)
    page.click("#nav-btn-tickets")

    # 1. Probar alternancia de Auto-scroll
    btn_scroll = page.locator("#btn-toggle-autoscroll")
    expect(btn_scroll).to_contain_text("Auto-scroll: ON")
    btn_scroll.click()
    expect(btn_scroll).to_contain_text("Auto-scroll: OFF")
    btn_scroll.click()
    expect(btn_scroll).to_contain_text("Auto-scroll: ON")

    # 2. Agregar logs mediante la API frontend
    page.evaluate("""() => {
        window.App.appendLogEntry("Paso 1: Inicialización", "step");
        window.App.appendLogEntry("Paso 2: Formulario completado", "info");
        window.App.appendLogEntry("Ticket creado: SD1049281", "success");
    }""")

    counter = page.locator("#ticket-log-counter")
    expect(counter).to_contain_text("3 eventos")
    expect(page.locator(".log-entry")).to_have_count(3)

    # 3. Limpiar consola
    page.click("#btn-clear-logs")
    expect(counter).to_contain_text("0 eventos")
    expect(page.locator(".terminal-welcome-msg")).to_be_visible()


def test_e2e_03_modal_dual_id_display_and_clipboard_actions(page: Page):
    """
    CP-E2E-03: Visualización del Modal con Doble ID y Acciones de Copiado
    - Abrir el modal de éxito con identificadores SD1049555 y PET007788.
    - Validar que ambos identificadores se muestren en sus respectivas tarjetas.
    - Validar los datos del resumen (contacto, título, grupo, área, usuario petición y logout).
    - Probar los botones de copiado de SD, Petición y Ambos IDs verificando la retroalimentación visual.
    """
    helper_login(page)
    page.click("#nav-btn-tickets")

    modal = page.locator("#ticket-success-modal")
    expect(modal).to_be_hidden()

    # Abrir modal mediante App.openTicketSuccessModal
    page.evaluate("""() => {
        window.App.openTicketSuccessModal("SD1049555", "PET007788", {
            contacto: "ALEJANDRO JAVIER AGUILAR MORALES",
            titulo: "Automatización de Solicitud Técnica",
            grupo: "Lideres Tecnicos",
            area: "Proyectos",
            subarea: "Apoyo habilitacion cliente"
        });
    }""")

    expect(modal).to_be_visible()

    # Validar ambos identificadores
    expect(page.locator("#ticket-success-id")).to_have_text("SD1049555")
    expect(page.locator("#peticion-success-id")).to_have_text("PET007788")

    # Validar resumen
    expect(page.locator("#modal-summary-contacto")).to_have_text("ALEJANDRO JAVIER AGUILAR MORALES")
    expect(page.locator("#modal-summary-titulo")).to_have_text("Automatización de Solicitud Técnica")
    expect(page.locator("#modal-summary-grupo")).to_have_text("Lideres Tecnicos")
    expect(page.locator("#modal-summary-usuario-peticion")).to_have_text("Alejandro.Aguilar")
    expect(page.locator("#modal-summary-logout-status")).to_contain_text("Sesión Finalizada Limpiamente")

    # Probar copiado de Ticket SD
    page.click("#btn-copy-ticket-id")
    expect(page.locator("#copy-ticket-btn-text")).to_have_text("✓ ¡Copiado!")

    # Probar copiado de Petición
    page.click("#btn-copy-peticion-id")
    expect(page.locator("#copy-peticion-btn-text")).to_have_text("✓ ¡Copiado!")

    # Probar copiado de Ambos IDs
    page.click("#btn-copy-both-ids")
    expect(page.locator("#btn-copy-both-ids")).to_contain_text("¡Resumen Copiado!")

    # Cerrar modal con botón de confirmación
    page.click("#btn-close-success-modal")
    expect(modal).to_be_hidden()


def test_e2e_04_full_sse_streaming_simulation_to_modal(page: Page):
    """
    CP-E2E-04: Simulación E2E de Flujo Completo SSE y Apertura Automática del Modal
    - Interceptar la ruta POST /api/automation/create-ticket simulando el stream SSE del backend.
    - Llenar los campos requeridos de Título y Descripción.
    - Hacer clic en '🚀 Ejecutar'.
    - Verificar que los logs se reciben en la consola y la barra de progreso avanza.
    - Validar que al finalizar el stream ('complete'), el modal se abre automáticamente con los dos IDs generados.
    """
    helper_login(page)
    page.click("#nav-btn-tickets")

    # Limpiar consola antes de la prueba
    page.click("#btn-clear-logs")

    # Llenar título y descripción requeridos
    page.fill("#ticket-titulo", "Habilitación enlace MPLS Cliente X")
    page.fill("#ticket-descripcion", "Detalle técnico para habilitación de conectividad e infraestructura")

    # Interceptar endpoint de automatización con eventos SSE simulados
    sse_payload = (
        'data: {"type": "log", "message": "Iniciando navegación en Service Manager...", "level": "step", "progress": 10}\n\n'
        'data: {"type": "log", "message": "Guardando interacción en Service Manager...", "level": "info", "progress": 70}\n\n'
        'data: {"type": "log", "message": "Interacción generada exitosamente: SD1049999", "level": "success", "progress": 75}\n\n'
        'data: {"type": "log", "message": "Petición generada exitosamente: PET001234", "level": "success", "progress": 90}\n\n'
        'data: {"type": "log", "message": "Cerrando sesión en Service Manager (Logout)...", "level": "info", "progress": 95}\n\n'
        'data: {"type": "complete", "status": "success", "ticket_id": "SD1049999", "peticion_id": "PET001234", "message": "Completado con éxito", "data": {"ticket_id": "SD1049999", "peticion_id": "PET001234", "contacto": "ALEJANDRO JAVIER AGUILAR MORALES", "titulo": "Habilitación enlace MPLS Cliente X", "grupo": "Lideres Tecnicos", "area": "Proyectos", "subarea": "Apoyo habilitacion cliente"}}\n\n'
    )

    def handle_create_ticket(route):
        route.fulfill(
            status=200,
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
            body=sse_payload
        )

    page.route("**/api/automation/create-ticket", handle_create_ticket)

    # Iniciar ejecución
    page.click("#btn-execute-ticket")

    # Esperar apertura automática del modal de éxito
    modal = page.locator("#ticket-success-modal")
    expect(modal).to_be_visible(timeout=10000)

    # Validar IDs en modal
    expect(page.locator("#ticket-success-id")).to_have_text("SD1049999")
    expect(page.locator("#peticion-success-id")).to_have_text("PET001234")

    # Validar estado en status badge
    badge = page.locator("#ticket-status-badge")
    expect(badge).to_have_text("Completado")

    # Cerrar modal con el botón de icono (X)
    page.click("#btn-close-modal-icon")
    expect(modal).to_be_hidden()


def test_e2e_05_client_side_validation_empty_fields(page: Page):
    """
    CP-E2E-05: Validación en Frontend de Campos Obligatorios Vacíos
    - Navegar a la vista de tickets.
    - Intentar ejecutar la automatización sin completar título ni descripción.
    - Validar que se dispare una alerta de diálogo y no se inicie la ejecución.
    """
    helper_login(page)
    page.click("#nav-btn-tickets")

    dialog_messages = []
    page.on("dialog", lambda dialog: (dialog_messages.append(dialog.message), dialog.accept()))

    # Click sin llenar campos
    page.click("#btn-execute-ticket")

    # Verificar que se capturó la alerta de validación
    assert len(dialog_messages) > 0
    assert "campos obligatorios" in dialog_messages[0].lower() or "título" in dialog_messages[0].lower()

    # Verificar que el modal no se abrió
    modal = page.locator("#ticket-success-modal")
    expect(modal).to_be_hidden()


