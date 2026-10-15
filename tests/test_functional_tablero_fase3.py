"""
BATERÍA DE PRUEBAS FUNCIONALES E2E: TABLERO, ATERRIZAJE POR ROL Y ALERTAS POR PROYECTO (FASE 3)
Proyecto: App LTI - Seguimiento Líderes TI
Especificación: odd/tasks/halo-ux-simplification.md (S14-S16)

Matriz de Cobertura:
- CP-DASH-01: El tablero muestra solo 4 KPI (asignados, en curso, pendientes de asignar, efectividad).
- CP-DASH-02: La salud es un filtro segmentado (Todos, Saludables, En riesgo, Críticos, Sin datos) ubicado
              entre la barra de filtros y la tabla.
- CP-DASH-03: Elegir un segmento filtra la tabla y marca el segmento; "Todos" vuelve a mostrar todo.
- CP-DASH-04: Con la preferencia Salud apagada, el filtro segmentado no se muestra.
- CP-DASH-05: "Pendientes de asignar" sigue filtrando al hacer clic.
- CP-ROLE-01: Un LTI aterriza en Proyectos con el filtro de Líder TI en su propio nombre.
- CP-ROLE-02: Un ADMIN aterriza en Proyectos con "Todos los Líderes TI".
- CP-ALR-01: La campana cuenta proyectos con alertas y el panel lista una tarjeta por proyecto.
- CP-ALR-02: Los filtros Críticos/Advertencias filtran proyectos por su peor severidad.
- CP-ALR-03: "Ver proyecto" abre el detalle del proyecto de la tarjeta.

Todas las pruebas son de solo lectura sobre la BD.
"""

import os

import requests
from playwright.sync_api import Page, expect
from tests.conftest import create_portal_jwt, click_user_menu_control

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
ADMIN_USER = "alejandro.aguilar"
LTI_USER = "erwin.sandoval"
LTI_NAME = "Erwin Sandoval"

KPI_TITLES = ["PROYECTOS ASIGNADOS", "PROYECTOS EN CURSO", "PENDIENTES DE ASIGNAR", "EFECTIVIDAD"]
SEGMENTS = [
    ("#health-card-all", "Todos"),
    ("#health-card-healthy", "Saludables"),
    ("#health-card-warning", "En riesgo"),
    ("#health-card-critical", "Críticos"),
    ("#health-card-neutral", "Sin datos"),
]


def token_for(username: str, rol: str) -> str:
    admin_level = 2 if rol == "ADMIN" else (0 if rol == "PM" else 1)
    tool_perm = "lectura" if rol == "PM" else "operador"
    return create_portal_jwt(
        username=username, admin_level=admin_level, tool_access={"app-lti": tool_perm},
        name=username.replace(".", " ").title(),
    )


def login_as(page: Page, username: str, rol: str):
    page.context.add_cookies([{"name": "access_token", "value": token_for(username, rol), "url": BASE_URL}])
    page.context.add_init_script(
        f"localStorage.setItem('halo_tour_solicitud_lti_seen:{username}', '1');"
        "['halo_health_score_enabled','halo_alerts_enabled'].forEach(k => localStorage.removeItem(k));"
    )
    page.goto(f"{BASE_URL}/")
    page.wait_for_selector("#projects-table-body tr.project-row", state="visible", timeout=30000)
    page.wait_for_function("() => window.App && window.App.isInitialized === true", timeout=30000)


def segment_count(page: Page, selector: str) -> int:
    return int(page.locator(f"{selector} .health-kpi-val").inner_text().strip())


def table_count(page: Page) -> int:
    return int(page.locator("#projects-count-badge").inner_text().strip())


# ---------------------------------------------------------------------------
# S14 - Tablero
# ---------------------------------------------------------------------------
def test_dash_01_only_four_kpis(page: Page):
    login_as(page, ADMIN_USER, "ADMIN")
    titles = [t.strip().upper() for t in page.locator(".kpi-grid .kpi-card .kpi-title").all_inner_texts()]
    assert titles == KPI_TITLES
    assert page.locator("#kpi-val-tickets").count() == 0
    assert page.locator("#kpi-val-rfcs").count() == 0


def test_dash_02_health_is_segmented_control_above_table(page: Page):
    login_as(page, ADMIN_USER, "ADMIN")
    group = page.locator("#health-kpi-grid")
    expect(group).to_be_visible()
    expect(group).to_have_attribute("role", "group")
    labels = [
        t.strip()
        for t in group.locator("button .health-segment-label").all_inner_texts()
    ]
    assert labels == [label for _, label in SEGMENTS]
    for selector, _ in SEGMENTS:
        expect(group.locator(selector)).to_have_count(1)
    order = page.evaluate("""() => {
        const bar = document.querySelector('#projects-list-section .filter-bar');
        const seg = document.getElementById('health-kpi-grid');
        const table = document.getElementById('projects-table-body');
        const F = Node.DOCUMENT_POSITION_FOLLOWING;
        return [Boolean(bar.compareDocumentPosition(seg) & F), Boolean(seg.compareDocumentPosition(table) & F)];
    }""")
    assert order == [True, True], "El filtro de salud debe estar entre la barra de filtros y la tabla"
    expect(page.locator("#health-card-all")).to_have_attribute("aria-pressed", "true")


def test_dash_03_segment_filters_table_and_all_resets(page: Page):
    login_as(page, ADMIN_USER, "ADMIN")
    total = table_count(page)
    parts = [segment_count(page, sel) for sel, _ in SEGMENTS[1:]]
    assert segment_count(page, "#health-card-all") == total == sum(parts)

    critical = page.locator("#health-card-critical")
    critical.click()
    expect(critical).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#health-card-all")).to_have_attribute("aria-pressed", "false")
    expected = segment_count(page, "#health-card-critical")
    expect(page.locator("#projects-count-badge")).to_have_text(str(expected))
    if expected:
        badges = page.locator("#projects-table-body tr.project-row .health-badge")
        assert badges.count() == expected
        assert all("Crítico" in t for t in badges.all_inner_texts())

    page.locator("#health-card-all").click()
    expect(page.locator("#health-card-all")).to_have_attribute("aria-pressed", "true")
    expect(critical).to_have_attribute("aria-pressed", "false")
    expect(page.locator("#projects-count-badge")).to_have_text(str(total))


def test_dash_04_segmented_hidden_when_health_off(page: Page):
    login_as(page, ADMIN_USER, "ADMIN")
    click_user_menu_control(page, "#health-score-toggle-btn")
    expect(page.locator("#health-kpi-grid")).to_be_hidden()
    click_user_menu_control(page, "#health-score-toggle-btn")
    expect(page.locator("#health-kpi-grid")).to_be_visible()


def test_dash_05_pending_assignment_kpi_still_filters(page: Page):
    login_as(page, ADMIN_USER, "ADMIN")
    card = page.locator("#kpi-card-pendientes")
    card.click()
    expect(card).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#filter-lt")).to_have_value("__UNASSIGNED__")
    card.click()
    expect(page.locator("#filter-lt")).to_have_value("__ALL__")


# ---------------------------------------------------------------------------
# S15 - Aterrizaje por rol
# ---------------------------------------------------------------------------
def test_role_01_lti_lands_on_own_projects(page: Page):
    login_as(page, LTI_USER, "LTI")
    expect(page.locator("#module-projects-container")).to_be_visible()
    expect(page.locator("#filter-lt")).to_have_value(LTI_NAME)
    lts = {
        t.strip()
        for t in page.locator("#projects-table-body tr.project-row td:nth-child(3)").all_inner_texts()
    }
    assert lts == {LTI_NAME}, f"Un LTI debe ver solo sus proyectos al entrar: {lts}"


def test_role_02_admin_lands_on_all_projects(page: Page):
    login_as(page, ADMIN_USER, "ADMIN")
    expect(page.locator("#module-projects-container")).to_be_visible()
    expect(page.locator("#filter-lt")).to_have_value("__ALL__")


# ---------------------------------------------------------------------------
# S16 - Alertas agrupadas por proyecto
# ---------------------------------------------------------------------------
def api_alerts():
    res = requests.get(
        f"{BASE_URL}/api/alertas/sla?limite=200",
        headers={"Authorization": f"Bearer {token_for(ADMIN_USER, 'ADMIN')}"},
        timeout=60,
    )
    assert res.status_code == 200
    return res.json()


def open_alerts(page: Page):
    page.locator("#alerts-bell-btn").click()
    expect(page.locator("#alerts-dropdown")).to_be_visible()
    page.wait_for_function(
        "() => document.getElementById('alerts-loading-state').style.display === 'none'", timeout=30000
    )


def test_alr_01_bell_counts_projects_and_panel_lists_project_cards(page: Page):
    data = api_alerts()
    n_projects = data["resumen"]["proyectos_con_alertas"]
    assert n_projects == len(data["proyectos"])
    assert all(p["proyecto_id"] for p in data["proyectos"])

    login_as(page, ADMIN_USER, "ADMIN")
    badge = page.locator("#alerts-badge-count")
    expect(badge).to_have_text("99+" if n_projects > 99 else str(n_projects))

    open_alerts(page)
    cards = page.locator("#alerts-items-list .alert-project-card")
    expect(cards).to_have_count(n_projects)
    expect(page.locator("#alerts-dropdown-total-badge")).to_contain_text(f"{n_projects} proyecto")
    first = data["proyectos"][0]
    card = cards.first
    expect(card).to_have_attribute("data-project-id", str(first["proyecto_id"]))
    expect(card).to_have_attribute("data-severity", first["severidad"])
    expect(card.locator(".alert-project-client")).to_contain_text((first["cliente"] or "").strip()[:20])
    expect(card.locator(".btn-alert-drilldown")).to_be_visible()
    assert card.locator(".alert-project-items li").count() == min(3, len(first["alertas"]))


def test_alr_02_severity_pills_filter_projects(page: Page):
    data = api_alerts()
    n_crit = data["resumen"]["proyectos_alerta_criticos"]
    n_warn = data["resumen"]["proyectos_alerta_advertencia"]

    login_as(page, ADMIN_USER, "ADMIN")
    open_alerts(page)
    cards = page.locator("#alerts-items-list .alert-project-card")

    page.locator("#alerts-filter-crit").click()
    expect(cards).to_have_count(n_crit)
    assert set(cards.evaluate_all("els => els.map(e => e.dataset.severity)")) <= {"CRITICAL"}

    page.locator("#alerts-filter-warn").click()
    expect(cards).to_have_count(n_warn)
    assert set(cards.evaluate_all("els => els.map(e => e.dataset.severity)")) <= {"WARNING"}

    page.locator("#alerts-filter-all").click()
    expect(cards).to_have_count(n_crit + n_warn)


def test_alr_03_view_project_opens_detail(page: Page):
    data = api_alerts()
    first = data["proyectos"][0]

    login_as(page, ADMIN_USER, "ADMIN")
    open_alerts(page)
    page.locator("#alerts-items-list .alert-project-card").first.locator(".btn-alert-drilldown").click()
    expect(page.locator("#project-drilldown-section")).to_be_visible(timeout=15000)
    expect(page.locator("#dd-client-title")).to_contain_text((first["cliente"] or "").strip()[:20])
