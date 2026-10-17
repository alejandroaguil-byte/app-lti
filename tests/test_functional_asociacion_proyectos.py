"""
BATERÍA DE PRUEBAS FUNCIONALES E2E: ASOCIACIÓN DE PROYECTOS (T5)
Proyecto: App LTI - Seguimiento Líderes TI
Especificación: odd/tasks/tours-busqueda-asociacion-kpis.md (S4)

Matriz de Cobertura:
- CP-ASO-01: el bloque "Proyectos asociados" es visible en el detalle (sin asociaciones muestra el estado vacío).
- CP-ASO-02: asociar un N° llama POST con el número, lo muestra en el grupo y recarga Solots/Tickets/RFCs y sus contadores.
- CP-ASO-03: el texto de error de la API (campo detail) se muestra en línea, sin tocar el grupo.
- CP-ASO-04: quitar pide confirmación; cancelar no llama a la API y confirmar llama DELETE.
- CP-ASO-05: la columna "Proyecto origen" aparece solo cuando el proyecto tiene asociaciones.
- CP-ASO-06: el autocompletado de SGA Backlog rellena el campo (reutiliza /api/solicitudes/autocomplete-proyectos).

BASE DE DATOS DE PRODUCCIÓN: solo se usa la cuenta E2E existente pm.e2e.user. Proyectos, asociaciones, Solots, Tickets,
RFCs y autocompletado se interceptan con page.route; cualquier otra escritura se aborta y hace fallar la prueba.
"""

import json
import os
import re

import pytest
from playwright.sync_api import Page, expect
from tests.conftest import create_portal_jwt

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
USERNAME = "pm.e2e.user"
PID = 9911
NUMERO = "000QA-ASOC-9911"

PROYECTO = {
    "ID": PID, "Cliente": "CLIENTE FIXTURE ASOC", "Numero_Proyecto": NUMERO, "LT_Asignado": "Erwin Sandoval",
    "Estado": "En ejecucion", "Detalle": "Detalle simulado", "Comentario": None, "Tipo_Servicio": "Otros",
    "Creado": "2026-10-01 10:00:00", "Solicitante": "Corp1- Pm Fixture",
    "salud": {"score": "NEUTRAL", "color": "gray", "label": "Sin datos", "motivos": ["Sin información operativa"]},
    "total_solots": 0, "total_tickets": 0, "total_rfcs": 0,
}

EDGE_HIJO = {"id": 5, "numero": "QA-HIJO-1", "autor_username": "pm.e2e.user", "creado": "2026-10-16T09:30:00"}
GRUPO_HIJO = {"numero": "QA-HIJO-1", "proyecto_id": 9912, "cliente": "CLIENTE HIJO FIXTURE"}

AUTOCOMPLETE = [
    {"nro_proyecto": "QA-SUG-0001", "numero_proyecto_limpio": "QA-SUG-0001", "cliente": "CLIENTE SUGERIDO UNO"},
    {"nro_proyecto": "QA-SUG-0002", "numero_proyecto_limpio": "QA-SUG-0002", "cliente": "CLIENTE SUGERIDO DOS"},
]


class Harness:
    """Intercepta /api/proyectos* y el autocompletado: lecturas simuladas, escrituras de asociaciones simuladas."""

    def __init__(self, page: Page, grupo=None, asociaciones=None):
        self.grupo = list(grupo or [])
        self.asociaciones = list(asociaciones or [])
        self.posts = []
        self.deletes = []
        self.gets = {"solots": 0, "tickets": 0, "rfcs": 0, "asociaciones": 0}
        self.post_error = None          # (status, detail)
        self.unexpected = []
        self.next_id = 50
        page.route(re.compile(r".*/api/proyectos(/.*|\?.*)?$"), self.handle)
        page.route(re.compile(r".*/api/solicitudes/autocomplete-proyectos.*"),
                   lambda route: self._json(route, AUTOCOMPLETE))

    @staticmethod
    def _json(route, body, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    def _rows(self, kind):
        base = {"solots": {"ID_OTP": 7001, "NRO_PROYECTO": NUMERO, "ESTADO_OTP": "EN EJECUCION"},
                "tickets": {"CC_INCIDENT_ID": "SD7001", "STATUS": "Open"},
                "rfcs": {"NUMBER": "RFC7001", "CC_PROYECT_NUMBER": NUMERO}}[kind]
        rows = [dict(base)]
        if self.grupo:
            rows[0]["Proyecto_Origen"] = "QA-ASOC-9911"
            hijo = dict(base)
            for key in ("ID_OTP", "CC_INCIDENT_ID", "NUMBER"):
                if key in hijo:
                    hijo[key] = f"{hijo[key]}-HIJO"
            hijo["Proyecto_Origen"] = self.grupo[0]["numero"]
            rows.append(hijo)
        return rows

    def handle(self, route):
        req = route.request
        path = re.sub(r"^https?://[^/]+", "", req.url).split("?")[0]
        method = req.method

        if method == "POST" and path == f"/api/proyectos/{PID}/asociaciones":
            payload = json.loads(req.post_data or "{}")
            self.posts.append(payload)
            if self.post_error:
                return self._json(route, {"detail": self.post_error[1]}, self.post_error[0])
            numero = payload["numero"].strip()
            self.next_id += 1
            self.asociaciones.append({"id": self.next_id, "numero": numero, "autor_username": USERNAME,
                                      "creado": "2026-10-16T12:00:00"})
            self.grupo.append({"numero": numero, "proyecto_id": None, "cliente": None})
            return self._json(route, self.asociaciones[-1], 201)
        m = re.match(rf"^/api/proyectos/{PID}/asociaciones/(\d+)$", path)
        if method == "DELETE" and m:
            self.deletes.append(path)
            eid = int(m.group(1))
            quitada = next((a for a in self.asociaciones if a["id"] == eid), None)
            self.asociaciones = [a for a in self.asociaciones if a["id"] != eid]
            if quitada:
                self.grupo = [g for g in self.grupo if g["numero"] != quitada["numero"]]
            return self._json(route, {"message": "Asociación eliminada", "id": eid})
        if method != "GET":
            self.unexpected.append(f"{method} {path}")
            return route.abort()

        if path == f"/api/proyectos/{PID}/asociaciones":
            self.gets["asociaciones"] += 1
            return self._json(route, {"numero_propio": "QA-ASOC-9911", "grupo": self.grupo,
                                      "asociaciones": self.asociaciones})
        m = re.match(rf"^/api/proyectos/{PID}/(solots|tickets|rfcs)$", path)
        if m:
            self.gets[m.group(1)] += 1
            return self._json(route, self._rows(m.group(1)))
        if re.match(rf"^/api/proyectos/{PID}$", path):
            return self._json(route, PROYECTO)
        if re.match(rf"^/api/proyectos/{PID}/", path):
            return self._json(route, [] if path.endswith("/bitacora") else {"detail": "No disponible en pruebas"},
                              200 if path.endswith("/bitacora") else 404)
        if path == "/api/proyectos":
            return self._json(route, [PROYECTO])
        return route.continue_()


def open_detail(page: Page, grupo=None, asociaciones=None):
    h = Harness(page, grupo, asociaciones)
    token = create_portal_jwt(username=USERNAME, admin_level=2, tool_access={"app-lti": "operador"},
                              name="Pm E2e User")
    page.context.add_cookies([{"name": "access_token", "value": token, "url": BASE_URL}])
    page.goto(f"{BASE_URL}/")
    page.wait_for_function("() => window.App && window.App.isInitialized === true", timeout=30000)
    page.locator("#nav-btn-projects").click()
    row = page.locator(f"#projects-table-body tr.project-row[data-project-id='{PID}'] td").first
    row.wait_for(state="visible", timeout=30000)
    row.click()
    expect(page.locator("#project-drilldown-section")).to_be_visible()
    return h


@pytest.fixture
def fx(page: Page):
    holder = {}

    def start(grupo=None, asociaciones=None):
        holder["h"] = open_detail(page, grupo, asociaciones)
        return holder["h"]

    yield start
    if "h" in holder:
        assert holder["h"].unexpected == [], f"Escrituras no simuladas bloqueadas: {holder['h'].unexpected}"


def asociar(page: Page, numero: str):
    page.fill("#asociados-input", numero)
    page.locator("#btn-asociados-agregar").click()


def origen_th(page: Page, tab: str):
    return page.locator(f"#{tab}-table-body").locator("xpath=ancestor::table").locator("th.col-origen")


def test_cp_aso_01_block_visible_in_detail(page: Page, fx):
    fx()
    block = page.locator("#asociados-block")
    expect(block).to_be_visible()
    expect(block.locator(".asociados-title")).to_have_text("Proyectos asociados")
    expect(page.locator("#asociados-list")).to_contain_text("Este proyecto no tiene proyectos asociados.")
    expect(page.locator("#asociados-input")).to_be_visible()
    expect(page.locator("#btn-asociados-agregar")).to_have_text("Asociar")
    expect(page.locator("#asociados-error")).to_be_hidden()


def test_cp_aso_01b_existing_group_is_listed_with_remove_only_on_direct_edges(page: Page, fx):
    indirecto = {"numero": "QA-NIETO-2", "proyecto_id": None, "cliente": None}
    fx(grupo=[GRUPO_HIJO, indirecto], asociaciones=[EDGE_HIJO])
    items = page.locator("#asociados-list .asociado-item")
    expect(items).to_have_count(2)
    expect(items.nth(0)).to_contain_text("QA-HIJO-1")
    expect(items.nth(0)).to_contain_text("CLIENTE HIJO FIXTURE")
    expect(items.nth(0).get_by_role("button", name="Quitar")).to_have_count(1)
    expect(items.nth(1)).to_contain_text("QA-NIETO-2")
    expect(items.nth(1)).to_contain_text("No figura en Proyectos")
    expect(items.nth(1).get_by_role("button")).to_have_count(0)


def test_cp_aso_02_add_number_posts_shows_it_and_reloads_tabs(page: Page, fx):
    h = fx()
    for tab in ("solots", "tickets", "rfcs"):
        expect(page.locator(f"#tab-count-{tab}")).to_have_text("1")
    before = dict(h.gets)

    asociar(page, " 0001615172 ")

    expect(page.locator("#asociados-list .asociado-item")).to_have_count(1)
    expect(page.locator("#asociados-list")).to_contain_text("0001615172")
    assert h.posts == [{"numero": "0001615172"}]  # el cliente envía el N° recortado; la API lo normaliza
    expect(page.locator("#asociados-input")).to_have_value("")
    expect(page.locator("#asociados-error")).to_be_hidden()
    for tab in ("solots", "tickets", "rfcs"):
        expect(page.locator(f"#tab-count-{tab}")).to_have_text("2")
        assert h.gets[tab] == before[tab] + 1
    assert h.gets["asociaciones"] == before["asociaciones"] + 1


def test_cp_aso_02b_enter_key_submits(page: Page, fx):
    h = fx()
    page.fill("#asociados-input", "QA-HIJO-1")
    page.press("#asociados-input", "Enter")
    expect(page.locator("#asociados-list")).to_contain_text("QA-HIJO-1")
    assert h.posts == [{"numero": "QA-HIJO-1"}]


@pytest.mark.parametrize("status, detail, numero", [
    (409, "El N° de proyecto ya está asociado a este grupo", "QA-HIJO-1"),
    (400, "No puedes asociar un proyecto consigo mismo", "QA-ASOC-9911"),
    (400, "El N° de proyecto solo puede contener letras, números y guiones (máx. 30 caracteres)", "no valido!"),
    (400, "El N° de proyecto es obligatorio", ""),
])
def test_cp_aso_03_api_error_text_is_shown_inline(page: Page, fx, status, detail, numero):
    h = fx(grupo=[GRUPO_HIJO], asociaciones=[EDGE_HIJO])
    h.post_error = (status, detail)
    asociar(page, numero)
    error = page.locator("#asociados-error")
    expect(error).to_be_visible()
    expect(error).to_have_text(detail)
    assert h.posts == [{"numero": numero}]
    expect(page.locator("#asociados-list .asociado-item")).to_have_count(1)
    # El error se limpia al volver a escribir
    page.fill("#asociados-input", "otro")
    expect(error).to_be_hidden()


def test_cp_aso_04_remove_asks_confirmation_then_deletes(page: Page, fx):
    h = fx(grupo=[GRUPO_HIJO], asociaciones=[EDGE_HIJO])
    item = page.locator("#asociados-list .asociado-item")

    item.get_by_role("button", name="Quitar").click()
    expect(item).to_contain_text("¿Quitar esta asociación?")
    assert h.deletes == []

    item.get_by_role("button", name="Cancelar").click()
    expect(item.get_by_role("button", name="Quitar")).to_be_visible()
    assert h.deletes == []

    item.get_by_role("button", name="Quitar").click()
    item.get_by_role("button", name="Confirmar").click()
    expect(page.locator("#asociados-list")).to_contain_text("Este proyecto no tiene proyectos asociados.")
    assert h.deletes == [f"/api/proyectos/{PID}/asociaciones/5"]
    expect(page.locator("#tab-count-solots")).to_have_text("1")


def test_cp_aso_05_origin_column_only_with_associations(page: Page, fx):
    h = fx()
    for tab in ("solots", "tickets", "rfcs"):
        expect(page.locator(f"#tab-count-{tab}")).to_have_text("1")
        expect(origen_th(page, tab)).to_be_hidden()
        assert page.locator(f"#{tab}-table-body td.col-origen").count() == 0

    asociar(page, "QA-HIJO-1")
    for tab in ("solots", "tickets", "rfcs"):
        expect(page.locator(f"#tab-count-{tab}")).to_have_text("2")
        page.locator(f".tab-btn[data-tab='{tab}']").click()
        expect(origen_th(page, tab)).to_be_visible()
        expect(origen_th(page, tab)).to_have_text("Proyecto origen")
        cells = page.locator(f"#{tab}-table-body td.col-origen")
        expect(cells).to_have_count(2)
        expect(cells.nth(0)).to_have_text("QA-ASOC-9911")
        expect(cells.nth(1)).to_have_text("QA-HIJO-1")

    page.locator(".tab-btn[data-tab='summary']").click()
    page.locator("#asociados-list .asociado-item").get_by_role("button", name="Quitar").click()
    page.locator("#asociados-list .asociado-item").get_by_role("button", name="Confirmar").click()
    expect(page.locator("#tab-count-solots")).to_have_text("1")
    for tab in ("solots", "tickets", "rfcs"):
        page.locator(f".tab-btn[data-tab='{tab}']").click()
        expect(origen_th(page, tab)).to_be_hidden()
        assert page.locator(f"#{tab}-table-body td.col-origen").count() == 0
    assert h.deletes


def test_cp_aso_05b_origin_column_visible_when_project_opens_with_associations(page: Page, fx):
    fx(grupo=[GRUPO_HIJO], asociaciones=[EDGE_HIJO])
    for tab in ("solots", "tickets", "rfcs"):
        page.locator(f".tab-btn[data-tab='{tab}']").click()
        expect(origen_th(page, tab)).to_be_visible()
        expect(page.locator(f"#{tab}-table-body td.col-origen").first).to_have_text("QA-ASOC-9911")


def test_cp_aso_06_autocomplete_fills_the_input(page: Page, fx):
    h = fx()
    page.locator("#asociados-input").press_sequentially("QA-SUG", delay=20)
    dropdown = page.locator("#asociados-autocomplete-dropdown")
    expect(dropdown).to_be_visible()
    expect(dropdown.locator(".autocomplete-item")).to_have_count(2)
    expect(dropdown).to_contain_text("CLIENTE SUGERIDO UNO")
    dropdown.locator(".autocomplete-item").nth(1).click()
    expect(page.locator("#asociados-input")).to_have_value("QA-SUG-0002")
    expect(dropdown).to_be_hidden()
    assert h.posts == []  # elegir una sugerencia no asocia hasta pulsar "Asociar"
    page.locator("#btn-asociados-agregar").click()
    expect(page.locator("#asociados-list")).to_contain_text("QA-SUG-0002")
    assert h.posts == [{"numero": "QA-SUG-0002"}]
