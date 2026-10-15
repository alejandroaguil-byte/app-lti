"""
BATERÍA DE PRUEBAS FUNCIONALES E2E: NAVEGACIÓN SIMPLIFICADA (FASE 1)
Proyecto: App LTI - Seguimiento Líderes TI
Especificación: odd/tasks/halo-ux-simplification.md (S1-S7)

Matriz de Cobertura:
- CP-NAV-01: ADMIN ve 4 módulos cortos y "Administración > Usuarios"; sin títulos MENÚ/MÓDULOS.
- CP-NAV-02: LTI ve los 4 módulos y no ve el grupo Administración.
- CP-NAV-03: PM ve solo "Solicitudes LTI", sin Administración ni Preferencias.
- CP-NAV-04: Un solo control para contraer el menú lateral, persistente al recargar.
- CP-NAV-05: Menú de usuario con nombre, rol, tema, preferencias y cerrar sesión; se cierra con Escape y clic afuera.
- CP-NAV-06: El tema se cambia desde el menú de usuario y persiste al recargar.
- CP-NAV-07: Preferencias (5 interruptores) solo para ADMIN y funcionales.
- CP-NAV-08: Un usuario no ADMIN usa las funciones por defecto aunque tenga preferencias guardadas.
- CP-NAV-09: Cerrar sesión desde el menú de usuario llama a /api/auth/logout.
- CP-NAV-10: Clic o Enter en una fila abre el detalle del proyecto.
- CP-NAV-11: Las filas no tienen ver/eliminar; el menú "⋯" ofrece Editar y Diagnóstico sin abrir el detalle.
- CP-NAV-12: Eliminar vive solo en el detalle y pide confirmación.
- CP-NAV-13: En el detalle hay una sola línea de tiempo: "Hitos del proyecto" en Resumen y pestaña "Historial".

Todas las pruebas son de solo lectura sobre la BD (no crean, editan ni eliminan proyectos).
"""

import os
import pytest
from playwright.sync_api import Page, expect
from tests.conftest import create_portal_jwt

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")

ADMIN_USER = "alejandro.aguilar"
LTI_USER = "erwin.sandoval"
PM_USER = "pm.e2e.user"

MAIN_MODULES = ["Proyectos", "Búsqueda", "Tickets SM", "Solicitudes LTI"]
FEATURE_TOGGLES = [
    "#health-score-toggle-btn",
    "#diag-toggle-btn",
    "#pdf-export-toggle-btn",
    "#timeline-toggle-btn",
    "#alerts-toggle-btn",
]


def login_as(page: Page, username: str, rol: str):
    # Mismo criterio que el portal: PM = lectura/nivel 0, LTI = operador/nivel 1, ADMIN = nivel 2
    admin_level = 2 if rol == "ADMIN" else (0 if rol == "PM" else 1)
    tool_perm = "lectura" if rol == "PM" else "operador"
    token = create_portal_jwt(
        username=username,
        admin_level=admin_level,
        tool_access={"app-lti": tool_perm},
        name=username.replace(".", " ").title(),
    )
    page.context.add_cookies([{"name": "access_token", "value": token, "url": BASE_URL}])
    page.context.add_init_script(
        f"localStorage.setItem('halo_tour_solicitud_lti_seen:{username}', '1')"
    )
    page.goto(f"{BASE_URL}/")
    page.wait_for_selector("#app-view", state="visible", timeout=25000)


def visible_module_labels(page: Page, container: str):
    return [
        t.strip()
        for t in page.locator(f"{container} .nav-module-btn:visible .module-text").all_inner_texts()
    ]


def open_user_menu(page: Page):
    page.locator("#user-menu-btn").click()
    expect(page.locator("#user-menu-dropdown")).to_be_visible()


def wait_first_project_row(page: Page):
    row = page.locator("#projects-table-body tr.project-row").first
    expect(row).to_be_visible(timeout=20000)
    return row


def open_first_project(page: Page):
    wait_first_project_row(page).locator("td").first.click()
    expect(page.locator("#project-drilldown-section")).to_be_visible(timeout=15000)


# ---------------------------------------------------------------------------
# S1 / S6 - Menú lateral
# ---------------------------------------------------------------------------
def test_nav_01_admin_sidebar_has_short_modules_and_admin_group(page: Page):
    login_as(page, ADMIN_USER, "ADMIN")

    assert visible_module_labels(page, "#sidebar-main-modules") == MAIN_MODULES
    admin_section = page.locator("#sidebar-admin-section")
    expect(admin_section).to_be_visible()
    expect(admin_section.locator(".sidebar-section-title")).to_have_text("Administración")
    assert visible_module_labels(page, "#sidebar-admin-section") == ["Usuarios"]

    sidebar_text = page.locator("#nav-subbar").inner_text().upper()
    assert "MENÚ" not in sidebar_text
    assert "MÓDULOS" not in sidebar_text
    assert "CONFIGURACIONES" not in sidebar_text


def test_nav_02_lti_sidebar_hides_admin_group(page: Page):
    login_as(page, LTI_USER, "LTI")

    assert visible_module_labels(page, "#sidebar-main-modules") == MAIN_MODULES
    expect(page.locator("#sidebar-admin-section")).to_be_hidden()


def test_nav_03_pm_sees_only_solicitudes_without_admin_or_preferences(page: Page):
    login_as(page, PM_USER, "PM")

    assert visible_module_labels(page, "#sidebar-main-modules") == ["Solicitudes LTI"]
    expect(page.locator("#sidebar-admin-section")).to_be_hidden()
    expect(page.locator("#module-solicitud-lti-container")).to_be_visible()

    open_user_menu(page)
    expect(page.locator("#user-menu-preferences")).to_be_hidden()
    expect(page.locator("#user-role-badge")).to_have_text("Project Manager")


def test_nav_04_single_sidebar_collapse_control_persists(page: Page):
    login_as(page, ADMIN_USER, "ADMIN")
    page.evaluate("localStorage.removeItem('halo_sidebar_collapsed')")
    page.reload()
    page.wait_for_selector("#app-view", state="visible", timeout=25000)

    assert page.locator("#sidebar-inner-toggle-btn").count() == 0
    sidebar = page.locator("#nav-subbar")
    expect(sidebar).not_to_have_class("nav-subbar collapsed")

    page.locator("#sidebar-toggle-btn").click()
    expect(sidebar).to_have_class("nav-subbar collapsed")

    page.reload()
    page.wait_for_selector("#app-view", state="visible", timeout=25000)
    expect(page.locator("#nav-subbar")).to_have_class("nav-subbar collapsed")

    page.locator("#sidebar-toggle-btn").click()
    expect(page.locator("#nav-subbar")).not_to_have_class("nav-subbar collapsed")


# ---------------------------------------------------------------------------
# S2 / S3 - Menú de usuario y Preferencias
# ---------------------------------------------------------------------------
def test_nav_05_user_menu_contents_and_closing(page: Page):
    login_as(page, ADMIN_USER, "ADMIN")
    sidebar = page.locator("#nav-subbar")
    for moved in ("#theme-toggle-btn", "#user-role-badge", "#btn-logout", *FEATURE_TOGGLES):
        assert sidebar.locator(moved).count() == 0, f"{moved} sigue en el menú lateral"

    dropdown = page.locator("#user-menu-dropdown")
    expect(dropdown).to_be_hidden()
    expect(page.locator("#user-menu-btn")).to_have_attribute("aria-expanded", "false")

    open_user_menu(page)
    expect(page.locator("#user-menu-btn")).to_have_attribute("aria-expanded", "true")
    expect(dropdown.locator("#user-menu-name")).to_have_text("Alejandro Aguilar")
    expect(dropdown.locator("#user-role-badge")).to_have_text("Administrador")
    expect(dropdown.locator("#theme-toggle-btn")).to_be_visible()
    expect(dropdown.locator("#user-menu-preferences")).to_be_visible()
    expect(dropdown.locator("#btn-logout")).to_be_visible()

    page.keyboard.press("Escape")
    expect(dropdown).to_be_hidden()
    expect(page.locator("#user-menu-btn")).to_have_attribute("aria-expanded", "false")

    open_user_menu(page)
    page.locator("#module-projects-container").click(position={"x": 5, "y": 5})
    expect(dropdown).to_be_hidden()


def test_nav_06_theme_from_user_menu_persists(page: Page):
    login_as(page, ADMIN_USER, "ADMIN")
    page.evaluate("localStorage.setItem('app_lti_theme', 'light')")
    page.reload()
    page.wait_for_selector("#app-view", state="visible", timeout=25000)

    open_user_menu(page)
    expect(page.locator("#theme-toggle-label")).to_have_text("Modo oscuro")
    page.locator("#theme-toggle-btn").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(page.locator("#theme-toggle-label")).to_have_text("Modo claro")

    page.reload()
    page.wait_for_selector("#app-view", state="visible", timeout=25000)
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")

    open_user_menu(page)
    page.locator("#theme-toggle-btn").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "light")


def test_nav_07_admin_preferences_toggles_work(page: Page):
    login_as(page, ADMIN_USER, "ADMIN")
    page.evaluate("localStorage.removeItem('halo_health_score_enabled')")
    page.reload()
    page.wait_for_selector("#app-view", state="visible", timeout=25000)

    open_user_menu(page)
    prefs = page.locator("#user-menu-preferences")
    for toggle in FEATURE_TOGGLES:
        expect(prefs.locator(toggle)).to_be_visible()

    health_btn = prefs.locator("#health-score-toggle-btn")
    expect(health_btn).not_to_have_class("btn-subbar-toggle sidebar-toggle-item is-off")
    health_btn.click()
    expect(page.locator("#th-col-salud")).to_be_hidden()
    expect(health_btn).to_have_class("btn-subbar-toggle sidebar-toggle-item is-off")

    health_btn.click()
    expect(page.locator("#th-col-salud")).to_be_visible()
    assert page.evaluate("localStorage.getItem('halo_health_score_enabled')") == "true"


def test_nav_08_non_admin_ignores_stored_feature_preferences(page: Page):
    login_as(page, LTI_USER, "LTI")
    page.evaluate("localStorage.setItem('halo_health_score_enabled', 'false')")
    page.reload()
    page.wait_for_selector("#app-view", state="visible", timeout=25000)
    wait_first_project_row(page)

    expect(page.locator("#th-col-salud")).to_be_visible()
    open_user_menu(page)
    expect(page.locator("#user-menu-preferences")).to_be_hidden()
    expect(page.locator("#user-role-badge")).to_have_text("Líder TI")


def test_nav_09_logout_from_user_menu(page: Page):
    calls = []
    page.route("**/api/auth/logout", lambda route: (calls.append(route.request.method), route.fulfill(status=200, body="{}")))
    login_as(page, ADMIN_USER, "ADMIN")

    open_user_menu(page)
    logout_btn = page.locator("#user-menu-dropdown #btn-logout")
    expect(logout_btn).to_have_attribute("aria-label", "Salir")
    logout_btn.click()
    page.wait_for_timeout(1500)
    assert calls == ["POST"]


# ---------------------------------------------------------------------------
# S4 - Filas de la tabla de proyectos
# ---------------------------------------------------------------------------
def test_nav_10_row_click_and_enter_open_detail(page: Page):
    login_as(page, ADMIN_USER, "ADMIN")

    row = wait_first_project_row(page)
    client = row.locator(".col-project-client").inner_text().strip()
    row.locator("td").first.click()
    expect(page.locator("#project-drilldown-section")).to_be_visible(timeout=15000)
    expect(page.locator("#dd-client-title")).to_have_text(client)

    page.locator("#back-to-projects-btn").click()
    row = wait_first_project_row(page)
    expect(row).to_have_attribute("tabindex", "0")
    row.focus()
    page.keyboard.press("Enter")
    expect(page.locator("#project-drilldown-section")).to_be_visible(timeout=15000)


def test_nav_11_row_menu_offers_edit_and_diagnosis_without_opening_detail(page: Page):
    login_as(page, ADMIN_USER, "ADMIN")
    page.evaluate("localStorage.removeItem('halo_executive_diagnosis_enabled')")
    page.reload()
    page.wait_for_selector("#app-view", state="visible", timeout=25000)

    row = wait_first_project_row(page)
    assert page.locator("#projects-table-body .btn-action-view").count() == 0
    assert page.locator("#projects-table-body .btn-action-delete").count() == 0

    menu = page.locator("#row-actions-menu")
    expect(menu).to_be_hidden()
    row.locator(".btn-row-menu").click()
    expect(menu).to_be_visible()
    expect(page.locator("#project-drilldown-section")).to_be_hidden()
    expect(menu.locator(".btn-action-edit")).to_have_text("Editar")
    expect(menu.locator(".btn-action-diag")).to_have_text("Diagnóstico ejecutivo")
    assert menu.locator(".btn-action-delete").count() == 0

    page.keyboard.press("Escape")
    expect(menu).to_be_hidden()

    row.locator(".btn-row-menu").click()
    menu.locator(".btn-action-edit").click()
    expect(page.locator("#edit-project-modal")).to_be_visible()
    expect(menu).to_be_hidden()


def test_nav_12_delete_lives_only_in_detail_with_confirmation(page: Page):
    login_as(page, ADMIN_USER, "ADMIN")

    open_first_project(page)
    delete_btn = page.locator("#btn-dd-delete-project")
    expect(delete_btn).to_be_visible()
    delete_btn.click()
    expect(page.locator("#delete-project-modal")).to_be_visible()


# ---------------------------------------------------------------------------
# S5 - Una sola línea de tiempo en el detalle
# ---------------------------------------------------------------------------
def test_nav_13_detail_has_single_timeline(page: Page):
    login_as(page, ADMIN_USER, "ADMIN")

    open_first_project(page)
    summary = page.locator("#tab-pane-summary")
    milestones = summary.locator("#project-timeline-container")
    expect(milestones).to_be_visible()
    expect(milestones.locator(".timeline-header")).to_contain_text("Hitos del proyecto")

    expect(page.locator("#tab-btn-timeline")).to_contain_text("Historial")
    detail_text = page.locator("#project-drilldown-section").inner_text()
    assert "Línea de Tiempo" not in detail_text
