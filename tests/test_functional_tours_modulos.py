"""
E2E: guided tour in every module (S1) - Proyectos, Búsqueda, Tickets SM and Usuarios.

- CP-TM-01: first visit to each module auto-starts its tour (step 1 of N, correct title).
- CP-TM-02: full walkthrough: each step highlights its element (or is centered) and Anterior/Siguiente navigate.
- CP-TM-03: finishing or skipping marks the tour as seen (per user and module) and it does not come back
            after a reload + re-entering the module.
- CP-TM-04: "Ver tour" relaunches the tour of the module even after it was seen.
- CP-TM-05: the seen state is per module: seeing one tour does not suppress the others.
- CP-TM-06: only one tour at a time: switching module closes the open tour.
- CP-TM-07: Solicitud LTI is unchanged for a non-PM user (no auto-start, manual launch only).

Only the existing E2E account pm.e2e.user is used (the portal JIT writes to the shared database).
Every non-GET /api request is aborted so no test can write data.
"""

import os

import pytest
from playwright.sync_api import Page, expect
from tests.conftest import create_portal_jwt

pytestmark = pytest.mark.real_tours

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")

USERNAME = "pm.e2e.user"

# module -> nav button, container, "Ver tour" button and steps as (title, element that must be highlighted or None)
TOURS = {
    "projects": {
        "nav": "#nav-btn-projects",
        "container": "#module-projects-container",
        "button": "#btn-projects-tour",
        "steps": [
            ("¡Bienvenido a Proyectos!", None),
            ("Indicadores del portafolio", "#module-projects-container .kpi-grid"),
            ("En revisión y Cerrados", "#kpi-card-en-revision"),
            ("Filtros y búsqueda", "#filter-search"),
            ("Listado de proyectos", "#projects-list-section .card-table-wrapper"),
            ("Exporta tu vista", "#export-btn"),
            ("Detalle de cada proyecto", None),
        ],
    },
    "direct-search": {
        "nav": "#nav-btn-direct-search",
        "container": "#module-direct-search-container",
        "button": "#btn-direct-search-tour",
        "steps": [
            ("¡Bienvenido a Búsqueda!", None),
            ("Agrega tags", "#direct-search-input-field"),
            ("Elige la fuente", "#direct-search-table-select"),
            ("Buscar en BD", "#direct-search-submit-btn"),
            ("Sugerencias rápidas", "#quick-tags-box"),
            # Results area is hidden until a search runs: the engine falls back to a centered step
            ("Resultados por pestañas", None),
        ],
    },
    "tickets": {
        "nav": "#nav-btn-tickets",
        "container": "#module-tickets-container",
        "button": "#btn-tickets-tour",
        "steps": [
            ("¡Bienvenido al Generador de tickets!", None),
            ("Contacto", "#ticket-contacto"),
            ("Título y descripción", "#ticket-titulo"),
            ("Clasificación", "#ticket-area"),
            ("Impacto y urgencia", "#ticket-impacto"),
            ("Ejecuta la automatización", "#btn-execute-ticket"),
            ("Registro de ejecución", "#ticket-logs-console"),
        ],
    },
    "usuarios": {
        "nav": "#nav-btn-usuarios",
        "container": "#module-usuarios-container",
        "button": "#btn-usuarios-tour",
        "steps": [
            ("¡Bienvenido al Mantenedor de Usuarios!", None),
            ("Buscar usuarios", "#usuarios-search-input"),
            ("Filtros por rol y estado", "#usuarios-filter-rol"),
            ("Listado de usuarios", "#module-usuarios-container .table-card"),
            ("Acciones por usuario", "#usuarios-table thead th:last-child"),
        ],
    },
}
MODULES = list(TOURS)


def tour_id(module: str) -> str:
    return f"{module}-tour"


def login_as_admin(page: Page):
    """Admin session with the existing E2E account; any write request is aborted."""
    def guard(route):
        if route.request.method == "GET":
            route.continue_()
        else:
            route.abort()

    page.route("**/api/**", guard)
    token = create_portal_jwt(username=USERNAME, admin_level=2, tool_access={"app-lti": "operador"},
                              name="Pm E2e User")
    page.context.add_cookies([{"name": "access_token", "value": token, "url": BASE_URL}])
    page.goto(f"{BASE_URL}/")
    page.wait_for_selector("#app-view", state="visible", timeout=25000)


def go_to_module(page: Page, module: str):
    """Moves to the module as a user would: the initial module (Proyectos) already has its tour open."""
    if module != "projects":
        # The projects tour opens on login and blocks the page; dismiss it first
        dismiss_tour(page, "projects")
        page.locator(TOURS[module]["nav"]).click()
    expect(page.locator(TOURS[module]["container"])).to_be_visible()


def dismiss_tour(page: Page, module: str):
    expect(page.locator(f"#{tour_id(module)}")).to_be_visible(timeout=5000)
    page.locator(f"#{tour_id(module)}-skip").click()
    expect(page.locator(f"#{tour_id(module)}")).to_have_count(0)


def wait_spotlight_covers(page: Page, module: str, selector: str):
    page.wait_for_function(
        """([id, sel]) => {
            const spot = document.getElementById(id + '-spotlight');
            const target = document.querySelector(sel);
            if (!spot || !target) return false;
            const s = spot.getBoundingClientRect();
            const t = target.getBoundingClientRect();
            return s.width > 0 && s.height > 0 &&
                s.left <= t.left + 1 && s.top <= t.top + 1 &&
                s.right >= t.right - 1 && s.bottom >= t.bottom - 1;
        }""",
        arg=[tour_id(module), selector],
        timeout=5000,
    )


def expect_step(page: Page, module: str, index: int):
    steps = TOURS[module]["steps"]
    title, target = steps[index]
    prefix = tour_id(module)
    expect(page.locator(f"#{prefix}-progress")).to_have_text(f"Paso {index + 1} de {len(steps)}")
    expect(page.locator(f"#{prefix}-title")).to_have_text(title)
    if target:
        expect(page.locator(f"#{prefix}-spotlight")).to_be_visible()
        wait_spotlight_covers(page, module, target)
    else:
        expect(page.locator(f"#{prefix}-spotlight")).to_be_hidden()


def seen_key(module: str) -> str:
    return f"halo_tour_{module}_seen:{USERNAME}"


def read_seen(page: Page, module: str):
    return page.evaluate("key => localStorage.getItem(key)", seen_key(module))


@pytest.mark.parametrize("module", MODULES)
def test_tm_01_first_visit_autostarts(page: Page, module: str):
    """CP-TM-01: first visit shows the tour at step 1 of N, as a modal dialog."""
    login_as_admin(page)
    go_to_module(page, module)
    tour = page.locator(f"#{tour_id(module)}")
    expect(tour).to_be_visible(timeout=5000)
    expect(tour).to_have_attribute("role", "dialog")
    expect(tour).to_have_attribute("aria-modal", "true")
    expect_step(page, module, 0)
    expect(page.locator(f"#{tour_id(module)}-prev")).to_be_disabled()
    expect(page.locator(f"#{tour_id(module)}-next")).to_have_text("Siguiente")
    assert 4 <= len(TOURS[module]["steps"]) <= 8


@pytest.mark.parametrize("module", MODULES)
def test_tm_02_full_walkthrough(page: Page, module: str):
    """CP-TM-02: every step shows its title/target; Anterior and arrow keys navigate back and forth."""
    login_as_admin(page)
    go_to_module(page, module)
    total = len(TOURS[module]["steps"])
    prefix = tour_id(module)
    expect(page.locator(f"#{prefix}")).to_be_visible(timeout=5000)

    for index in range(total):
        expect_step(page, module, index)
        if index < total - 1:
            page.locator(f"#{prefix}-next").click()

    expect(page.locator(f"#{prefix}-next")).to_have_text("Finalizar")
    page.locator(f"#{prefix}-prev").click()
    expect_step(page, module, total - 2)
    page.keyboard.press("ArrowLeft")
    expect_step(page, module, total - 3)
    page.keyboard.press("ArrowRight")
    expect_step(page, module, total - 2)


@pytest.mark.parametrize("how", ["finish", "skip"])
@pytest.mark.parametrize("module", MODULES)
def test_tm_03_closing_marks_seen(page: Page, module: str, how: str):
    """CP-TM-03: finishing or skipping stores the per-user/module key; no tour after reload + re-entering."""
    login_as_admin(page)
    go_to_module(page, module)
    prefix = tour_id(module)
    if module != "projects":
        # Dismissing the projects tour first already marked it as seen
        assert read_seen(page, "projects") == "true"
    expect(page.locator(f"#{prefix}")).to_be_visible(timeout=5000)
    assert read_seen(page, module) is None

    if how == "skip":
        page.locator(f"#{prefix}-skip").click()
    else:
        for _ in range(len(TOURS[module]["steps"])):
            page.locator(f"#{prefix}-next").click()
    expect(page.locator(f"#{prefix}")).to_have_count(0)
    assert read_seen(page, module) == "true"

    page.reload()
    page.wait_for_selector("#app-view", state="visible", timeout=25000)
    if module != "projects":
        page.locator(TOURS[module]["nav"]).click()
    expect(page.locator(TOURS[module]["container"])).to_be_visible()
    page.wait_for_timeout(1500)
    expect(page.locator(".tour-root")).to_have_count(0)


@pytest.mark.parametrize("module", MODULES)
def test_tm_04_ver_tour_relaunches(page: Page, module: str):
    """CP-TM-04: the module's "Ver tour" button relaunches the tour from step 1 after it was seen."""
    login_as_admin(page)
    go_to_module(page, module)
    dismiss_tour(page, module)

    button = page.locator(TOURS[module]["button"])
    expect(button).to_be_visible()
    expect(button).to_contain_text("Ver tour")
    expect(button).to_have_class("btn btn-secondary btn-sm")
    button.click()
    expect(page.locator(f"#{tour_id(module)}")).to_be_visible()
    expect_step(page, module, 0)
    page.locator(f"#{tour_id(module)}-close").click()
    expect(page.locator(f"#{tour_id(module)}")).to_have_count(0)


def test_tm_05_seen_state_is_per_module(page: Page):
    """CP-TM-05: having seen Proyectos' tour does not suppress Búsqueda's, and vice versa."""
    login_as_admin(page)
    dismiss_tour(page, "projects")
    assert read_seen(page, "projects") == "true"
    assert read_seen(page, "direct-search") is None

    page.locator(TOURS["direct-search"]["nav"]).click()
    expect(page.locator("#direct-search-tour")).to_be_visible(timeout=5000)
    expect_step(page, "direct-search", 0)
    assert read_seen(page, "tickets") is None
    assert read_seen(page, "usuarios") is None


def test_tm_06_switching_module_closes_open_tour(page: Page):
    """CP-TM-06: only one tour at a time; a module switch closes the open one (and marks it seen as today)."""
    login_as_admin(page)
    expect(page.locator("#projects-tour")).to_be_visible(timeout=5000)

    page.evaluate("() => App.switchModule('tickets')")
    expect(page.locator("#projects-tour")).to_have_count(0)
    expect(page.locator("#tickets-tour")).to_be_visible(timeout=5000)
    assert page.locator(".tour-root").count() == 1
    assert read_seen(page, "projects") == "true"


def test_tm_07_solicitud_lti_unchanged_for_non_pm(page: Page):
    """CP-TM-07: Solicitud LTI keeps auto-start only for PM; a non-PM launches it with "Ver tour"."""
    login_as_admin(page)
    dismiss_tour(page, "projects")
    page.locator("#nav-btn-solicitud-lti").click()
    expect(page.locator("#module-solicitud-lti-container")).to_be_visible()
    page.wait_for_timeout(1500)
    expect(page.locator("#solicitud-tour")).to_have_count(0)
    assert page.evaluate("key => localStorage.getItem(key)", f"halo_tour_solicitud_lti_seen:{USERNAME}") is None

    page.locator("#btn-solicitud-tour").click()
    expect(page.locator("#solicitud-tour")).to_be_visible()
    expect(page.locator("#solicitud-tour-progress")).to_have_text("Paso 1 de 8")
    page.locator("#solicitud-tour-close").click()
    expect(page.locator("#solicitud-tour")).to_have_count(0)
