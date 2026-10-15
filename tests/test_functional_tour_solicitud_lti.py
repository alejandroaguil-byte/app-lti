"""
BATERÍA DE PRUEBAS FUNCIONALES E2E: TOUR GUIADO DEL MÓDULO SOLICITUD LTI
Proyecto: App LTI - Seguimiento Líderes TI
Ubicación: tests/test_functional_tour_solicitud_lti.py

Matriz de Cobertura:
- CP-TOUR-01: Un PM que ingresa por primera vez ve el tour automáticamente (paso 1 de 8).
- CP-TOUR-02: Recorrido completo: cada paso resalta su elemento del formulario y Anterior/Siguiente navegan.
- CP-TOUR-03: Finalizar cierra el tour y no reaparece al recargar.
- CP-TOUR-04: Omitir cierra el tour y no reaparece al recargar.
- CP-TOUR-05: La tecla Escape cierra el tour y no reaparece al recargar.
- CP-TOUR-06: Un usuario ADMIN no recibe el tour automático, pero puede lanzarlo con "Ver tour".
- CP-TOUR-07: Un PM que ya vio el tour puede relanzarlo con "Ver tour".
- CP-TOUR-08: El estado "visto" es por usuario: otro PM en el mismo navegador sí ve el tour.
- CP-TOUR-09: La tarjeta del tour usa la superficie del Design System en modo claro y oscuro.
"""

import os
import pytest
from playwright.sync_api import Page, expect
from tests.conftest import create_portal_jwt

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")

PM_USER = "pm.e2e.user"
PM_USER_2 = "pm.e2e.user2"
ADMIN_USER = "alejandro.aguilar"
TOTAL_STEPS = 8

# Elemento resaltado por cada paso (None = paso centrado sin elemento)
STEP_TARGETS = [
    None,
    "#solicitud-nro-proyecto",
    "#solicitud-cliente",
    "#solicitud-fecha",
    "#solicitud-estado",
    "#solicitud-detalle",
    "#btn-submit-solicitud",
    None,
]

STEP_TITLES = [
    "¡Bienvenido a Solicitud LTI!",
    "N° de Proyecto",
    "Cliente",
    "Fecha de Solicitud",
    "Estado fijo: Generado",
    "Detalle del Requerimiento",
    "Envía tu solicitud",
    "¿Qué pasa después?",
]


def token_for(username: str, rol: str) -> str:
    admin_level = 2 if rol == "ADMIN" else 0
    tool_perm = "operador" if rol == "ADMIN" else "lectura"
    return create_portal_jwt(
        username=username,
        admin_level=admin_level,
        tool_access={"app-lti": tool_perm},
        name=username.replace(".", " ").title(),
    )


def login_as(page: Page, username: str, rol: str):
    page.context.add_cookies([{
        "name": "access_token",
        "value": token_for(username, rol),
        "url": BASE_URL,
    }])
    page.goto(f"{BASE_URL}/")
    page.wait_for_selector("#app-view", state="visible", timeout=25000)


def open_solicitud_module(page: Page):
    page.locator("#nav-btn-solicitud-lti").click()
    expect(page.locator("#module-solicitud-lti-container")).to_be_visible()


def wait_spotlight_covers(page: Page, selector: str):
    """Espera a que el recuadro resaltado contenga por completo al elemento objetivo."""
    page.wait_for_function(
        """(sel) => {
            const spot = document.getElementById('solicitud-tour-spotlight');
            const target = document.querySelector(sel);
            if (!spot || !target) return false;
            const s = spot.getBoundingClientRect();
            const t = target.getBoundingClientRect();
            return s.width > 0 && s.height > 0 &&
                s.left <= t.left + 1 && s.top <= t.top + 1 &&
                s.right >= t.right - 1 && s.bottom >= t.bottom - 1;
        }""",
        arg=selector,
        timeout=5000,
    )


def expect_step(page: Page, index: int):
    expect(page.locator("#solicitud-tour-progress")).to_have_text(f"Paso {index + 1} de {TOTAL_STEPS}")
    expect(page.locator("#solicitud-tour-title")).to_contain_text(STEP_TITLES[index])
    target = STEP_TARGETS[index]
    if target:
        expect(page.locator("#solicitud-tour-spotlight")).to_be_visible()
        wait_spotlight_covers(page, target)
    else:
        expect(page.locator("#solicitud-tour-spotlight")).to_be_hidden()


def expect_tour_closed(page: Page):
    expect(page.locator("#solicitud-tour")).to_have_count(0)


def reload_and_wait(page: Page):
    page.reload()
    page.wait_for_selector("#app-view", state="visible", timeout=25000)
    expect(page.locator("#module-solicitud-lti-container")).to_be_visible()
    # Margen para un eventual autoarranque diferido
    page.wait_for_timeout(1500)


def test_tour_01_pm_first_visit_shows_tour(page: Page):
    """CP-TOUR-01: Un PM nuevo en el navegador ve el tour automáticamente en el paso 1."""
    login_as(page, PM_USER, "PM")
    expect(page.locator("#module-solicitud-lti-container")).to_be_visible()
    tour = page.locator("#solicitud-tour")
    expect(tour).to_be_visible(timeout=5000)
    expect(tour).to_have_attribute("role", "dialog")
    expect(tour).to_have_attribute("aria-modal", "true")
    expect_step(page, 0)
    expect(page.locator("#solicitud-tour-prev")).to_be_disabled()
    expect(page.locator("#solicitud-tour-next")).to_have_text("Siguiente")


def test_tour_02_full_walkthrough_and_back_navigation(page: Page):
    """CP-TOUR-02: Cada paso resalta su elemento; Anterior vuelve al paso previo."""
    login_as(page, PM_USER, "PM")
    expect(page.locator("#solicitud-tour")).to_be_visible(timeout=5000)

    for index in range(TOTAL_STEPS):
        expect_step(page, index)
        if index < TOTAL_STEPS - 1:
            expect(page.locator("#solicitud-tour-next")).to_have_text("Siguiente")
            page.locator("#solicitud-tour-next").click()

    expect(page.locator("#solicitud-tour-next")).to_have_text("Finalizar")
    expect(page.locator("#solicitud-tour-prev")).to_be_enabled()

    page.locator("#solicitud-tour-prev").click()
    expect_step(page, TOTAL_STEPS - 2)
    page.keyboard.press("ArrowLeft")
    expect_step(page, TOTAL_STEPS - 3)
    page.keyboard.press("ArrowRight")
    expect_step(page, TOTAL_STEPS - 2)


def test_tour_03_finish_marks_seen(page: Page):
    """CP-TOUR-03: Finalizar cierra el tour y no reaparece al recargar."""
    login_as(page, PM_USER, "PM")
    expect(page.locator("#solicitud-tour")).to_be_visible(timeout=5000)
    for _ in range(TOTAL_STEPS - 1):
        page.locator("#solicitud-tour-next").click()
    page.locator("#solicitud-tour-next").click()
    expect_tour_closed(page)

    reload_and_wait(page)
    expect_tour_closed(page)


def test_tour_04_skip_marks_seen(page: Page):
    """CP-TOUR-04: Omitir cierra el tour y no reaparece al recargar."""
    login_as(page, PM_USER, "PM")
    expect(page.locator("#solicitud-tour")).to_be_visible(timeout=5000)
    page.locator("#solicitud-tour-skip").click()
    expect_tour_closed(page)

    reload_and_wait(page)
    expect_tour_closed(page)


def test_tour_05_escape_marks_seen(page: Page):
    """CP-TOUR-05: Escape cierra el tour y no reaparece al recargar."""
    login_as(page, PM_USER, "PM")
    expect(page.locator("#solicitud-tour")).to_be_visible(timeout=5000)
    page.keyboard.press("Escape")
    expect_tour_closed(page)

    reload_and_wait(page)
    expect_tour_closed(page)


def test_tour_06_admin_no_autostart_but_manual_launch(page: Page):
    """CP-TOUR-06: ADMIN no recibe tour automático; el botón Ver tour lo lanza desde el paso 1."""
    login_as(page, ADMIN_USER, "ADMIN")
    open_solicitud_module(page)
    page.wait_for_timeout(1500)
    expect_tour_closed(page)

    button = page.locator("#btn-solicitud-tour")
    expect(button).to_be_visible()
    expect(button).to_contain_text("Ver tour")
    button.click()
    expect(page.locator("#solicitud-tour")).to_be_visible()
    expect_step(page, 0)
    page.locator("#solicitud-tour-close").click()
    expect_tour_closed(page)


def test_tour_07_pm_relaunch_after_seen(page: Page):
    """CP-TOUR-07: Un PM que ya vio el tour puede relanzarlo con Ver tour."""
    login_as(page, PM_USER, "PM")
    expect(page.locator("#solicitud-tour")).to_be_visible(timeout=5000)
    page.locator("#solicitud-tour-skip").click()
    expect_tour_closed(page)

    page.locator("#btn-solicitud-tour").click()
    expect(page.locator("#solicitud-tour")).to_be_visible()
    expect_step(page, 0)


def test_tour_08_seen_state_is_per_user(page: Page):
    """CP-TOUR-08: Otro PM en el mismo navegador ve el tour aunque el primero ya lo haya visto."""
    login_as(page, PM_USER, "PM")
    expect(page.locator("#solicitud-tour")).to_be_visible(timeout=5000)
    page.locator("#solicitud-tour-skip").click()
    expect_tour_closed(page)

    login_as(page, PM_USER_2, "PM")
    expect(page.locator("#solicitud-tour")).to_be_visible(timeout=5000)
    expect_step(page, 0)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_tour_09_card_uses_design_system_surface(page: Page, theme: str):
    """CP-TOUR-09: La tarjeta del tour comparte superficie y radio con las tarjetas de la app."""
    page.add_init_script(f"localStorage.setItem('app_lti_theme', '{theme}');")
    login_as(page, PM_USER, "PM")
    card = page.locator("#solicitud-tour-card")
    expect(card).to_be_visible(timeout=5000)
    styles = page.evaluate(
        """() => {
            const card = getComputedStyle(document.getElementById('solicitud-tour-card'));
            const ref = getComputedStyle(document.querySelector('.solicitud-card'));
            return {
                theme: document.documentElement.getAttribute('data-theme'),
                cardBg: card.backgroundColor, refBg: ref.backgroundColor,
                cardRadius: card.borderTopLeftRadius, refRadius: ref.borderTopLeftRadius,
            };
        }"""
    )
    assert styles["theme"] == theme
    assert styles["cardBg"] == styles["refBg"]
    assert styles["cardRadius"] == styles["refRadius"]
