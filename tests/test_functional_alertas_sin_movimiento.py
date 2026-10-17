"""
E2E: "project without movement" alert in the alerts bell (odd/tasks/fixes-proyectos-alertas.md, T4: S5).

- CP-SINMOV-01: the bell badge counts the project and the panel shows a card with the "sin movimiento" label.
- CP-SINMOV-02: the panel item is labelled and the "Ver proyecto" action opens that project.
- CP-SINMOV-03: the "En advertencia" filter keeps the stale project and "Críticos" hides it.

/api/alertas/sla is simulated with page.route (payload built by the real processor, no database access) and
App.openProjectFromAlert is replaced by a spy. Only the existing account pm.e2e.user is used.
"""

import json
import os
import datetime

from playwright.sync_api import Page, expect

from backend.db import procesar_alertas_sla
from tests.conftest import create_portal_jwt

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")


def _payload():
    ultimo = datetime.datetime.now() - datetime.timedelta(days=12)
    filas = [{
        "p_id": 9201, "p_numero": "000QA-SINMOV-1", "p_cliente": "CLIENTE QA SIN MOVIMIENTO",
        "p_lider": "Juan Barrera", "p_estado": "En ejecucion", "p_tipo_servicio": "Otros",
        "ultimo_movimiento": ultimo,
    }]
    return procesar_alertas_sla([], [], raw_proyectos=filas)


def _open_alerts(page: Page):
    token = create_portal_jwt(username="pm.e2e.user", admin_level=2, tool_access={"app-lti": "operador"},
                              name="Pm E2e User")
    page.context.add_cookies([{"name": "access_token", "value": token, "url": BASE_URL}])
    body = json.dumps(_payload())
    page.route("**/api/alertas/sla*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=body))
    page.goto(f"{BASE_URL}/")
    page.wait_for_selector("#app-view", state="visible", timeout=25000)
    page.wait_for_function("() => window.App && window.App.isInitialized === true", timeout=25000)
    expect(page.locator("#alerts-badge-count")).to_have_text("1")
    page.evaluate("""() => {
        window.__opened = [];
        App.openProjectFromAlert = (id) => { window.__opened.push(id); };
    }""")
    page.locator("#alerts-bell-btn").click()
    expect(page.locator("#alerts-dropdown")).to_be_visible()


def test_cp_sinmov_01_card_with_label_and_badge(page: Page):
    _open_alerts(page)
    card = page.locator("#alerts-items-list .alert-project-card")
    expect(card).to_have_count(1)
    expect(card).to_have_attribute("data-project-id", "9201")
    expect(card).to_have_attribute("data-severity", "WARNING")
    expect(card.locator(".alert-project-client")).to_have_text("CLIENTE QA SIN MOVIMIENTO")
    expect(card.locator(".alert-project-counts")).to_have_text("sin movimiento hace 12 días")
    expect(card.locator(".alert-card-sla-badge")).to_have_text("Advertencia")
    expect(page.locator("#alerts-dropdown-total-badge")).to_have_text("1 proyecto")
    expect(page.locator("#alerts-filter-count-warn")).to_have_text("1")
    expect(page.locator("#alerts-filter-count-crit")).to_have_text("0")


def test_cp_sinmov_02_item_label_and_open_project_action(page: Page):
    _open_alerts(page)
    item = page.locator("#alerts-items-list .alert-project-item-stale")
    expect(item).to_have_count(1)
    expect(item.locator(".alert-project-item-title")).to_have_text("Proyecto sin movimiento")
    expect(item.locator(".alert-project-item-detail")).to_contain_text("Sin movimiento hace 12 días")
    page.locator("#alerts-items-list .btn-alert-drilldown").click()
    assert page.evaluate("() => window.__opened") == [9201]


def test_cp_sinmov_03_severity_filters(page: Page):
    _open_alerts(page)
    page.locator("#alerts-filter-crit").click()
    expect(page.locator("#alerts-items-list")).to_be_hidden()
    expect(page.locator("#alerts-empty-state .empty-title")).to_have_text("Sin proyectos en esta categoría")
    page.locator("#alerts-filter-warn").click()
    expect(page.locator("#alerts-items-list .alert-project-card")).to_be_visible()
