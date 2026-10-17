"""
E2E: Búsqueda results keep the horizontal scrollbar reachable (S2).

- CP-SCROLL-01: With many results the Solots table scrolls inside its own area, sized to the
  viewport, so its horizontal scrollbar is on screen without scrolling the page to the end.
- CP-SCROLL-02: The header row stays visible (sticky) while scrolling the results vertically.
- CP-SCROLL-03: Click and drag over a row moves the table sideways and does not trigger clicks.
- CP-SCROLL-04: A small mouse move (below the drag threshold) does not scroll the table.

Search responses are simulated with page.route: no database access.
"""

import json
import os

from playwright.sync_api import Page, expect
from tests.conftest import create_portal_jwt

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")


def _solot(i: int) -> dict:
    return {
        "ID_CLI": f"CLI{i}", "NRO_PROYECTO": f"000{1600000 + i}", "CLI_CLIENTE": f"CLIENTE QA {i} CON NOMBRE LARGO",
        "ID_OTP": 9000000 + i, "DESCR_OTP": "DESCRIPCION MUY LARGA DE LA SOLOT " * 4, "ESTADO_OTP": "EN EJECUCION",
        "FECHA_COMPROMETIDA": "2026-10-20 00:00:00", "FECHA_INSERT": "2026-10-16 10:00:00",
        "FECHA_REALIZACION": None, "PLAZO_CONTRATO": None, "PRODUCTO": "PRODUCTO DE PRUEBA EXTENSO",
        "SERVICIO": "SERVICIO DE PRUEBA EXTENSO", "NRO_SERVICIO": None, "ASIGNADO_OTP": "TECNICO DE PRUEBA QA",
        "GRUPO_ASIGNADO_OTP": None, "RUT_CLIENTE": "11.111.111-1", "ID_Proyecto": None,
    }


SEARCH_PAYLOAD = {
    "proyectos": [], "solots": [_solot(i) for i in range(120)], "tickets": [], "rfcs": [],
    "counts": {"proyectos": 0, "solots": 120, "tickets": 0, "rfcs": 0, "total": 120},
}


def _open_search_with_results(page: Page):
    page.set_viewport_size({"width": 1100, "height": 900})
    # Existing E2E account: the portal JIT must not create new rows in the shared database
    token = create_portal_jwt(username="pm.e2e.user", admin_level=2, tool_access={"app-lti": "operador"},
                              name="Pm E2e User")
    page.context.add_cookies([{"name": "access_token", "value": token, "url": BASE_URL}])
    page.route("**/api/search/direct**", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(SEARCH_PAYLOAD)))
    page.goto(f"{BASE_URL}/")
    page.wait_for_selector("#app-view", state="visible", timeout=25000)
    page.locator("#nav-btn-direct-search").click()
    expect(page.locator("#module-direct-search-container")).to_be_visible()
    page.fill("#direct-search-input-field", "QA")
    page.press("#direct-search-input-field", "Enter")
    page.locator("#direct-search-submit-btn").click()
    expect(page.locator("#direct-solots-table-body tr")).to_have_count(120)


def _scroller(page: Page):
    return page.locator("#direct-tab-pane-solots .direct-search-scroll")


def test_cp_scroll_01_horizontal_scrollbar_on_screen(page: Page):
    _open_search_with_results(page)
    box = _scroller(page).evaluate("""el => {
        const r = el.getBoundingClientRect();
        return { bottom: r.bottom, vh: window.innerHeight, sw: el.scrollWidth, cw: el.clientWidth,
                 sh: el.scrollHeight, ch: el.clientHeight };
    }""")
    assert box["sw"] > box["cw"], "the table must be wider than its area for this check"
    assert box["sh"] > box["ch"], "many rows scroll inside the table area"
    assert box["bottom"] <= box["vh"], "the bottom edge (horizontal scrollbar) is inside the viewport"


def test_cp_scroll_02_header_stays_visible(page: Page):
    _open_search_with_results(page)
    scroller = _scroller(page)
    scroller.evaluate("el => { el.scrollTop = 2000; }")
    gap = scroller.evaluate("""el => {
        const th = el.querySelector('thead th');
        return th.getBoundingClientRect().top - el.getBoundingClientRect().top;
    }""")
    assert abs(gap) <= 2


def test_cp_scroll_03_drag_moves_sideways(page: Page):
    _open_search_with_results(page)
    scroller = _scroller(page)
    cell = page.locator("#direct-solots-table-body tr").nth(1).locator("td").nth(2)
    b = cell.bounding_box()
    page.evaluate("window.__rowClicks = 0; document.getElementById('direct-solots-table-body')"
                  ".addEventListener('click', () => window.__rowClicks++);")
    page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
    page.mouse.down()
    page.mouse.move(b["x"] + b["width"] / 2 - 300, b["y"] + b["height"] / 2, steps=10)
    page.mouse.up()
    assert scroller.evaluate("el => el.scrollLeft") >= 250
    assert page.evaluate("window.__rowClicks") == 0
    expect(scroller).not_to_have_class("is-dragging")


def test_cp_scroll_04_small_move_does_not_scroll(page: Page):
    _open_search_with_results(page)
    scroller = _scroller(page)
    cell = page.locator("#direct-solots-table-body tr").first.locator("td").nth(2)
    b = cell.bounding_box()
    page.mouse.move(b["x"] + 10, b["y"] + 10)
    page.mouse.down()
    page.mouse.move(b["x"] + 12, b["y"] + 10)
    page.mouse.up()
    assert scroller.evaluate("el => el.scrollLeft") == 0
