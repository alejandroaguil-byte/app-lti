"""
E2E: project rows in the Proyectos module (odd/tasks/fixes-proyectos-alertas.md).

- CP-FILA-01 (S1): a normal left click on a row opens the project detail.
- CP-FILA-02 (S1): a right click on a row does not open the detail.
- CP-FILA-03 (S1): selecting text in a row with a mouse drag (to copy an ID) does not open the detail.
- CP-FILA-04 (S1): Enter on a focused row still opens the detail.
- CP-FILA-05 (S3): every body cell lines up with its header column (Fecha Solicitud LTI and Detalle included),
  with a long multi-line Detalle.

The project list is simulated with page.route (no database access) and App.drillDownById is replaced by a spy.
"""

import json
import os

from playwright.sync_api import Page, expect
from tests.conftest import create_portal_jwt

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")

LONG_DETALLE = ("SOLOTS ASOCIADOS (LIRAY): " + "Enlace dedicado de 1 Gbps con respaldo y firewall gestionado. " * 6)

PROYECTOS = [
    {"ID": 9101 + i, "Cliente": f"CLIENTE QA FILA {i}", "Numero_Proyecto": f"000QA-FILA-{i}",
     "LT_Asignado": "Juan Barrera", "Solicitante": "Pm Qa", "Estado": "En ejecucion",
     "Creado": "2026-10-16 10:00:00", "Detalle": LONG_DETALLE if i % 2 == 0 else "Detalle corto",
     "Tipo_Servicio": "Otros", "Comentario": None, "total_solots": 0, "solots_vencidos": 0,
     "solots_por_vencer": 0, "total_tickets": 0, "total_rfcs": 0}
    for i in range(6)
]


def _open_projects(page: Page):
    token = create_portal_jwt(username="pm.e2e.user", admin_level=2, tool_access={"app-lti": "operador"},
                              name="Pm E2e User")
    page.context.add_cookies([{"name": "access_token", "value": token, "url": BASE_URL}])

    def proyectos(route):
        if route.request.method == "GET" and "/api/proyectos?" in route.request.url or route.request.url.endswith("/api/proyectos"):
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(PROYECTOS))
        return route.continue_()

    page.route("**/api/proyectos*", proyectos)
    page.goto(f"{BASE_URL}/")
    page.wait_for_selector("#app-view", state="visible", timeout=25000)
    expect(page.locator("#projects-table-body tr.project-row")).to_have_count(len(PROYECTOS))
    page.evaluate("""() => {
        window.__drill = [];
        App.drillDownById = (id) => { window.__drill.push(id); };
    }""")


def _cell(page: Page, row: int, col: int):
    return page.locator("#projects-table-body tr.project-row").nth(row).locator("td").nth(col)


def test_cp_fila_01_left_click_opens_detail(page: Page):
    _open_projects(page)
    _cell(page, 1, 0).click()
    assert page.evaluate("window.__drill") == [PROYECTOS[1]["ID"]]


def test_cp_fila_02_right_click_does_not_open_detail(page: Page):
    _open_projects(page)
    _cell(page, 1, 1).click(button="right")
    _cell(page, 2, 1).click(button="middle")
    assert page.evaluate("window.__drill") == []


def test_cp_fila_03_text_selection_drag_does_not_open_detail(page: Page):
    _open_projects(page)
    cell = _cell(page, 1, 1)
    b = cell.bounding_box()
    page.mouse.move(b["x"] + 4, b["y"] + b["height"] / 2)
    page.mouse.down()
    page.mouse.move(b["x"] + b["width"] - 4, b["y"] + b["height"] / 2, steps=8)
    page.mouse.up()
    assert page.evaluate("window.getSelection().toString().length") > 0
    assert page.evaluate("window.__drill") == []
    # After the selection is cleared a normal click works again
    page.evaluate("window.getSelection().removeAllRanges()")
    _cell(page, 1, 0).click()
    assert page.evaluate("window.__drill") == [PROYECTOS[1]["ID"]]


def test_cp_fila_04_enter_opens_detail(page: Page):
    _open_projects(page)
    page.locator("#projects-table-body tr.project-row").nth(2).focus()
    page.keyboard.press("Enter")
    assert page.evaluate("window.__drill") == [PROYECTOS[2]["ID"]]


def test_cp_fila_05_cells_line_up_with_headers(page: Page):
    _open_projects(page)
    misaligned = page.evaluate("""() => {
        const ths = Array.from(document.querySelectorAll('#projects-table-body')[0]
            .closest('table').querySelectorAll('thead th'))
            .filter(th => th.getClientRects().length > 0);
        const out = [];
        document.querySelectorAll('#projects-table-body tr.project-row').forEach((tr, r) => {
            const tds = Array.from(tr.children);
            if (tds.length !== ths.length) out.push(`row ${r}: ${tds.length} cells vs ${ths.length} headers`);
            tds.forEach((td, i) => {
                const th = ths[i];
                if (!th) return;
                const a = td.getBoundingClientRect(), h = th.getBoundingClientRect();
                if (Math.abs(a.left - h.left) > 1 || Math.abs(a.width - h.width) > 1) {
                    out.push(`row ${r} col ${i} (${th.textContent.trim()}): td ${a.left.toFixed(0)}/${a.width.toFixed(0)} th ${h.left.toFixed(0)}/${h.width.toFixed(0)}`);
                }
            });
            const display = getComputedStyle(tr.querySelector('.col-project-detalle')).display;
            if (display !== 'table-cell') out.push(`row ${r}: Detalle cell display=${display}`);
        });
        return out;
    }""")
    assert misaligned == []
