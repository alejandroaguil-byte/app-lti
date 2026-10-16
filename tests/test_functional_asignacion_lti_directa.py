"""
E2E: assign an LTI from Búsqueda > Solots (odd/tasks/asignacion-lti-directa.md, S1 and S4).

Runs against the local dev server (BASE_URL). The shared database is production, so the
assignment request is intercepted with page.route: these tests never write projects.
Only read-only searches hit the real backlog.
"""

import json

from playwright.sync_api import Page, expect

from tests.conftest import BASE_URL, create_portal_jwt

# Real backlog project used for read-only searches (CT_BACKLOG_OPERACIONES2).
BACKLOG_NRO = "0001616424"
BACKLOG_CLIENTE = "GTD TELEDUCTOS S A"


def _login(page: Page, username="alejandro.aguilar", admin_level=2, tool_perm="operador"):
    token = create_portal_jwt(username=username, admin_level=admin_level, tool_access={"app-lti": tool_perm})
    page.context.add_cookies([{"name": "access_token", "value": token, "url": BASE_URL}])
    page.goto(f"{BASE_URL}/")
    page.wait_for_selector("#app-view", state="visible", timeout=25000)
    page.wait_for_function("() => window.App && window.App.isInitialized === true", timeout=25000)


def _search_backlog(page: Page):
    page.click("#nav-btn-direct-search")
    expect(page.locator("#module-direct-search-container")).to_be_visible()
    page.select_option("#direct-search-table-select", "solots")
    page.fill("#direct-search-input-field", BACKLOG_NRO)
    page.press("#direct-search-input-field", "Enter")
    page.click("#direct-search-submit-btn")
    page.click("[data-search-tab='solots']")
    btn = page.locator("#direct-solots-table-body .btn-assign-lti").first
    expect(btn).to_be_visible(timeout=20000)
    return btn


def _intercept_assign(page: Page, status: int, body: dict):
    requests = []

    def handler(route):
        requests.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    page.route("**/api/backlog/asignar-lti", handler)
    return requests


def test_e2e_assign_lti_from_solots_row(page: Page):
    requests = _intercept_assign(page, 201, {
        "message": "Proyecto creado y LTI asignado", "action": "created", "data": {},
    })
    _login(page)
    _search_backlog(page).click()

    modal = page.locator("#assign-lti-modal")
    expect(modal).to_be_visible()
    expect(page.locator("#assign-lti-nro")).to_have_value(BACKLOG_NRO)
    expect(page.locator("#assign-lti-cliente")).to_have_value(BACKLOG_CLIENTE)
    expect(page.locator("#assign-lti-lider option")).to_have_count(6)

    # No Lider TI selected: inline error, no request
    page.click("#btn-save-assign-lti-modal")
    expect(page.locator("#assign-lti-error-desc")).to_have_text("Selecciona un Líder TI.")
    assert requests == []

    page.select_option("#assign-lti-lider", "Juan Barrera")
    page.click("#btn-save-assign-lti-modal")
    expect(page.locator(".alert-toast")).to_contain_text("Proyecto creado y LTI asignado")
    expect(modal).to_be_hidden()
    assert requests == [{"numero_proyecto": BACKLOG_NRO, "lt_asignado": "Juan Barrera"}]


def test_e2e_assign_lti_shows_api_error(page: Page):
    _intercept_assign(page, 404, {"detail": "El proyecto no existe en el backlog de operaciones"})
    _login(page)
    _search_backlog(page).click()

    page.select_option("#assign-lti-lider", "Solange Ortiz")
    page.click("#btn-save-assign-lti-modal")
    expect(page.locator("#assign-lti-error-desc")).to_have_text("El proyecto no existe en el backlog de operaciones")
    expect(page.locator("#assign-lti-modal")).to_be_visible()


def test_e2e_assigner_downgraded_to_lectura_still_sees_assignment_modules(page: Page):
    _login(page, username="alejandro.aguilar", admin_level=0, tool_perm="lectura")
    expect(page.locator("#nav-btn-projects")).to_be_visible()
    expect(page.locator("#nav-btn-direct-search")).to_be_visible()
    _search_backlog(page)


def test_e2e_restricted_lti_does_not_see_assign_button(page: Page):
    """S5/L6: only full-visibility users get the Asignar LTI button in Búsqueda > Solots."""
    _login(page, username="juan.barrera", admin_level=1, tool_perm="operador")
    page.click("#nav-btn-direct-search")
    page.select_option("#direct-search-table-select", "solots")
    page.fill("#direct-search-input-field", BACKLOG_NRO)
    page.press("#direct-search-input-field", "Enter")
    page.click("#direct-search-submit-btn")
    page.click("[data-search-tab='solots']")
    expect(page.locator("#direct-solots-table-body tr").first).to_be_visible(timeout=20000)
    expect(page.locator("#direct-solots-table-body .btn-assign-lti")).to_have_count(0)
