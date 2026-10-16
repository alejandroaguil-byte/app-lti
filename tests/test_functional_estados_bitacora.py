"""
BATERÍA DE PRUEBAS FUNCIONALES E2E: ESTADOS, BITÁCORA, VISIBILIDAD Y TOOLTIPS DE PROYECTOS (T4)
Proyecto: App LTI - Seguimiento Líderes TI
Especificación: odd/tasks/estados-bitacora-proyectos.md (S1, S2, S3, S5, S6, S8)

Matriz de Cobertura:
- CP-EST-01: Filtro y modal de edición muestran los 4 estados con sus etiquetas.
- CP-EST-02: Insignias por estado (Generado gris, En ejecución teal, En revisión ámbar, Cerrado verde); Atendido = Cerrado.
- CP-NOT-01..06: Nota obligatoria al pasar a En revisión / Cerrado (aparece solo con cambio, mensaje exacto, payload).
- CP-EVI-01..04: Evidencias: subidas con el id de la entrada devuelta, fallo parcial y validación en el cliente.
- CP-BIT-01..05: Pestaña Bitácora (entradas, chips, adjuntos, descarga, formulario) y cierre en el Resumen.
- CP-VIS-01..03: Filtro de Líder TI bloqueado para quien no ve todo; libre para alejandro.aguilar y pablo.castillo.
- CP-TIP-01..04: Tooltips de las 4 tarjetas KPI (hover, foco, tema, movimiento reducido).

BASE DE DATOS DE PRODUCCIÓN: ninguna prueba guarda datos reales. Toda escritura (PUT de proyecto, POST de bitácora
y adjuntos) se intercepta con page.route y se responde con datos simulados; cualquier otra escritura se aborta y
hace fallar la prueba. Las lecturas de proyectos usan datos simulados (ID 99xx) salvo las pruebas de visibilidad y
tooltips, que leen datos reales (solo lectura).
"""

import json
import os
import re

import pytest
from playwright.sync_api import Page, expect
from tests.conftest import create_portal_jwt, click_row_action

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
ADMIN_USER = "alejandro.aguilar"
FULL_USER_2 = "pablo.castillo"
LTI_USER = "erwin.sandoval"
LTI_NAME = "Erwin Sandoval"

MSG_REVISION = "Debe documentar el motivo para pasar el proyecto a 'En revisión'"
MSG_CIERRE = "Debe documentar la información de cierre para pasar el proyecto a 'Cerrado'"
MAX_BYTES = 9 * 1024 * 1024

EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\u2600-\u26FF"
    "\u2700-\u2712\u2714\u2716-\u27BF"
    "\u2300-\u23FF"
    "\u2B00-\u2BFF"
    "\u2139\u24C2\u3030\u303D\u3297\u3299"
    "\uFE0F"
    "]"
)

SALUD = {"score": "NEUTRAL", "color": "gray", "label": "Sin datos", "motivos": ["Sin información operativa"]}


def project(pid, estado, lt, comentario=None):
    return {
        "ID": pid, "Cliente": f"CLIENTE FIXTURE {pid}", "Numero_Proyecto": f"000QA-FIX-{pid}",
        "LT_Asignado": lt, "Estado": estado, "Detalle": f"Detalle simulado {pid}", "Comentario": comentario,
        "Tipo_Servicio": "Otros", "Creado": "2026-10-01 10:00:00", "Solicitante": "Corp1- Pm Fixture",
        "salud": SALUD, "total_solots": 0, "total_tickets": 0, "total_rfcs": 0,
    }


P_EJEC = project(9901, "En ejecucion", LTI_NAME)
P_GEN = project(9902, "Generado", None)
P_LEGACY = project(9903, "Atendido", LTI_NAME, comentario="Entregado según acta histórica")
P_REV = project(9904, "En revision", LTI_NAME)
P_CERR = project(9905, "Cerrado", LTI_NAME)
ALL_PROJECTS = [P_EJEC, P_GEN, P_LEGACY, P_REV, P_CERR]

ENTRIES = [
    {"id": 3, "tipo": "CIERRE", "texto": "Cierre aceptado por el cliente.\nActa firmada.", "estado_anterior": "En revision",
     "estado_nuevo": "Cerrado", "autor_username": "erwin.sandoval", "autor_nombre": "Erwin Sandoval",
     "creado": "2026-10-16T09:30:00",
     "adjuntos": [{"id": 31, "nombre": "acta.pdf", "content_type": "application/pdf", "tamano_bytes": 1536000,
                   "creado": "2026-10-16T09:31:00"}]},
    {"id": 2, "tipo": "REVISION", "texto": "Falta validar el pase <b>productivo</b>", "estado_anterior": "En ejecucion",
     "estado_nuevo": "En revision", "autor_username": "erwin.sandoval", "autor_nombre": "Erwin Sandoval",
     "creado": "2026-10-15T08:05:00", "adjuntos": []},
    {"id": 1, "tipo": "BITACORA", "texto": "Reunión de arranque con el cliente.", "estado_anterior": None,
     "estado_nuevo": None, "autor_username": "alejandro.aguilar", "autor_nombre": "Alejandro Aguilar",
     "creado": "2026-10-14T16:45:00", "adjuntos": []},
]


class Harness:
    """Intercepta /api/proyectos*: lecturas simuladas (o reales) y TODA escritura simulada o abortada."""

    def __init__(self, page: Page, projects=None, bitacora=None, passthrough_reads=False):
        self.page = page
        self.projects = {p["ID"]: p for p in (projects if projects is not None else ALL_PROJECTS)}
        self.bitacora = list(bitacora if bitacora is not None else [])
        self.passthrough_reads = passthrough_reads
        self.puts = []
        self.bitacora_posts = []
        self.adjuntos = []          # {"path": ..., "filename": ..., "has_archivo_field": bool}
        self.bitacora_gets = 0
        self.downloads = []
        self.unexpected = []
        self.put_entry_id = 77
        self.fail_adjunto_names = set()
        self.next_entry_id = 50
        page.route(re.compile(r".*/api/proyectos(/.*|\?.*)?$"), self.handle)

    def _json(self, route, body, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    def handle(self, route):
        req = route.request
        path = re.sub(r"^https?://[^/]+", "", req.url).split("?")[0]
        method = req.method

        if method != "GET":
            return self.handle_write(route, req, path, method)
        if self.passthrough_reads:
            return route.continue_()

        m = re.match(r"^/api/proyectos/(\d+)/bitacora$", path)
        if m:
            self.bitacora_gets += 1
            return self._json(route, self.bitacora)
        m = re.match(r"^/api/proyectos/(\d+)/adjuntos/(\d+)$", path)
        if m:
            self.downloads.append(path)
            return route.fulfill(status=200, body=b"%PDF-1.4 fixture", headers={
                "Content-Type": "application/octet-stream", "Content-Disposition": "attachment; filename=\"x.pdf\"",
            })
        m = re.match(r"^/api/proyectos/(\d+)/(solots|tickets|rfcs)$", path)
        if m:
            return self._json(route, [])
        m = re.match(r"^/api/proyectos/(\d+)/", path)
        if m:
            return self._json(route, {"detail": "No disponible en pruebas"}, 404)
        m = re.match(r"^/api/proyectos/(\d+)$", path)
        if m:
            row = self.projects.get(int(m.group(1)))
            return self._json(route, row, 200) if row else self._json(route, {"detail": "Proyecto no encontrado"}, 404)
        if path == "/api/proyectos":
            return self._json(route, list(self.projects.values()))
        return route.continue_()

    def handle_write(self, route, req, path, method):
        if method == "PUT" and re.match(r"^/api/proyectos/(\d+)$", path):
            pid = int(path.rsplit("/", 1)[1])
            payload = json.loads(req.post_data or "{}")
            self.puts.append(payload)
            data = dict(self.projects.get(pid, {"ID": pid}))
            data["Estado"] = "En ejecucion" if payload.get("estado") == "Generado" and payload.get("lt_asignado") \
                else payload.get("estado")
            needs_entry = bool(payload.get("nota_estado"))
            return self._json(route, {
                "message": "Proyecto actualizado exitosamente", "data": data,
                "bitacora_entry_id": self.put_entry_id if needs_entry else None,
            })
        if method == "POST" and re.match(r"^/api/proyectos/(\d+)/bitacora$", path):
            payload = json.loads(req.post_data or "{}")
            self.bitacora_posts.append(payload)
            entry = {"id": self.next_entry_id, "tipo": "BITACORA", "texto": payload.get("texto"),
                     "estado_anterior": None, "estado_nuevo": None, "autor_username": "alejandro.aguilar",
                     "autor_nombre": "Alejandro Aguilar", "creado": "2026-10-16T12:00:00", "adjuntos": []}
            self.bitacora.insert(0, entry)
            return self._json(route, entry, 201)
        if method == "POST" and re.match(r"^/api/proyectos/(\d+)/bitacora/(\d+)/adjuntos$", path):
            body = req.post_data_buffer or b""
            fname = re.search(rb'filename="([^"]*)"', body)
            name = fname.group(1).decode() if fname else None
            self.adjuntos.append({"path": path, "filename": name, "has_archivo_field": b'name="archivo"' in body})
            if name in self.fail_adjunto_names:
                return self._json(route, {"detail": "Error al guardar el adjunto"}, 500)
            return self._json(route, {"id": 900 + len(self.adjuntos), "nombre": name, "content_type": None,
                                      "tamano_bytes": len(body), "creado": "2026-10-16T12:01:00"}, 201)
        self.unexpected.append(f"{method} {path}")
        return route.abort()


def login_as(page: Page, username: str, rol: str, harness_factory=None, wait_rows=True):
    admin_level = 2 if rol == "ADMIN" else (0 if rol == "PM" else 1)
    token = create_portal_jwt(
        username=username, admin_level=admin_level, tool_access={"app-lti": "lectura" if rol == "PM" else "operador"},
        name=username.replace(".", " ").title(),
    )
    harness = harness_factory(page) if harness_factory else None
    page.context.add_cookies([{"name": "access_token", "value": token, "url": BASE_URL}])
    page.context.add_init_script(
        f"localStorage.setItem('halo_tour_solicitud_lti_seen:{username}', '1');"
        "['halo_health_score_enabled','halo_alerts_enabled'].forEach(k => localStorage.removeItem(k));"
    )
    page.goto(f"{BASE_URL}/")
    page.wait_for_function("() => window.App && window.App.isInitialized === true", timeout=30000)
    if wait_rows:
        page.wait_for_selector("#projects-table-body tr.project-row", state="visible", timeout=30000)
    return harness


@pytest.fixture
def fx(page: Page):
    """Sesión ADMIN con proyectos y bitácora simulados."""
    h = login_as(page, ADMIN_USER, "ADMIN", lambda p: Harness(p, bitacora=ENTRIES))
    yield h
    assert h.unexpected == [], f"Escrituras no simuladas bloqueadas: {h.unexpected}"


def open_edit(page: Page, pid: int):
    row = page.locator(f"#projects-table-body tr.project-row[data-project-id='{pid}']")
    click_row_action(page, row, "btn-action-edit")
    expect(page.locator("#edit-project-modal")).to_be_visible()
    expect(page.locator("#edit-project-id")).to_have_value(str(pid))


def open_detail(page: Page, pid: int):
    page.locator(f"#projects-table-body tr.project-row[data-project-id='{pid}'] td").first.click()
    expect(page.locator("#project-drilldown-section")).to_be_visible()


def save_modal(page: Page):
    page.locator("#btn-save-edit-modal").click()


# ---------------------------------------------------------------------------
# S1 - Estados
# ---------------------------------------------------------------------------
def test_est_01_filter_has_four_states_with_labels(page: Page):
    h = login_as(page, ADMIN_USER, "ADMIN", lambda p: Harness(p, passthrough_reads=True))
    options = page.locator("#filter-estado-sp option")
    values = [o.get_attribute("value") for o in options.all()]
    labels = [t.strip() for t in options.all_inner_texts()]
    assert values[1:] == ["Generado", "En ejecucion", "En revision", "Cerrado"]
    assert labels[1:] == ["Generado", "En ejecución", "En revisión", "Cerrado"]
    assert h.unexpected == []


def test_est_01b_edit_modal_has_four_states_with_descriptions(page: Page, fx):
    open_edit(page, P_EJEC["ID"])
    options = page.locator("#edit-project-estado option")
    values = [o.get_attribute("value") for o in options.all()]
    texts = [t.strip() for t in options.all_inner_texts()]
    assert values == ["Generado", "En ejecucion", "En revision", "Cerrado"]
    for label, text in zip(["Generado", "En ejecución", "En revisión", "Cerrado"], texts):
        assert text.startswith(label) and len(text) > len(label), f"Falta la descripción corta: {text}"
    expect(page.locator("#edit-project-estado")).to_have_value("En ejecucion")


def test_est_02_badges_use_state_labels_and_colors(page: Page, fx):
    def badge(pid):
        return page.locator(f"#projects-table-body tr[data-project-id='{pid}'] td:nth-child(5) .badge")

    expect(badge(9902)).to_have_text("Generado")
    expect(badge(9902)).to_have_class(re.compile(r"badge-neutral"))
    expect(badge(9901)).to_have_text("En ejecución")
    expect(badge(9901)).to_have_class(re.compile(r"badge-info"))
    expect(badge(9904)).to_have_text("En revisión")
    expect(badge(9904)).to_have_class(re.compile(r"badge-warning"))
    expect(badge(9905)).to_have_text("Cerrado")
    expect(badge(9905)).to_have_class(re.compile(r"badge-success"))
    # Estado legado: se muestra como Cerrado
    expect(badge(9903)).to_have_text("Cerrado")
    expect(badge(9903)).to_have_class(re.compile(r"badge-success"))


def test_est_03_detail_header_and_summary_use_labels(page: Page, fx):
    open_detail(page, 9901)
    expect(page.locator("#dd-status .badge")).to_have_text("En ejecución")
    expect(page.locator("#summary-content .detail-row", has_text="Estado:").locator(".badge")).to_have_text("En ejecución")


def test_est_04_csv_export_uses_labels(page: Page, fx):
    with page.expect_download() as dl:
        page.locator("#export-btn").click()
    content = open(dl.value.path(), encoding="utf-8-sig").read()
    assert '"En ejecución"' in content and '"En revisión"' in content
    assert '"Atendido"' not in content and '"En ejecucion"' not in content
    assert content.count('"Cerrado"') == 2  # Cerrado + Atendido legado


def test_est_05_edit_modal_normalizes_legacy_atendido(page: Page, fx):
    open_edit(page, P_LEGACY["ID"])
    expect(page.locator("#edit-project-estado")).to_have_value("Cerrado")
    expect(page.locator("#edit-project-nota-group")).to_be_hidden()


def test_est_06_search_quick_tag_cerrado(page: Page, fx):
    chips = [t.strip() for t in page.locator(".quick-tag-chip").all_inner_texts()]
    assert "+ Cerrado" in chips and "+ Atendido" not in chips


def test_est_07_observaciones_label(page: Page, fx):
    open_edit(page, P_EJEC["ID"])
    label = page.locator("label[for='edit-project-comentario']")
    expect(label).to_have_text(re.compile(r"^\s*Observaciones\s*$"))
    help_text = page.locator("#edit-project-comentario ~ .form-help-text").inner_text()
    assert "Atendido" not in help_text


# ---------------------------------------------------------------------------
# S2 / S3 - Notas al cambiar de estado
# ---------------------------------------------------------------------------
def test_not_01_note_group_only_on_change_into_review_or_closed(page: Page, fx):
    open_edit(page, P_EJEC["ID"])
    group = page.locator("#edit-project-nota-group")
    expect(group).to_be_hidden()
    page.select_option("#edit-project-estado", "Generado")
    expect(group).to_be_hidden()
    page.select_option("#edit-project-estado", "En revision")
    expect(group).to_be_visible()
    expect(group.locator("label.form-label").first).to_contain_text("Motivo de la revisión")
    page.select_option("#edit-project-estado", "En ejecucion")
    expect(group).to_be_hidden()
    page.select_option("#edit-project-estado", "Cerrado")
    expect(group).to_be_visible()
    expect(group.locator("label.form-label").first).to_contain_text("Información de cierre")
    placeholder = page.locator("#edit-project-nota-estado").get_attribute("placeholder").lower()
    for hint in ("entregables", "validación del cliente", "ticket", "rfc", "aceptación"):
        assert hint in placeholder, f"El placeholder de cierre debe sugerir: {hint}"
    expect(page.locator("#edit-project-evidencias")).to_have_attribute("multiple", "")
    help_text = group.inner_text()
    assert "Evidencias opcionales. Máx. 9 MB por archivo. PDF, imágenes, Office, MSG, EML, ZIP, TXT, CSV." in help_text


def test_not_02_no_note_when_state_already_review_or_closed(page: Page, fx):
    open_edit(page, P_REV["ID"])
    expect(page.locator("#edit-project-nota-group")).to_be_hidden()
    save_modal(page)
    expect(page.locator("#edit-project-modal")).to_be_hidden()
    assert len(fx.puts) == 1
    assert not fx.puts[0].get("nota_estado")


@pytest.mark.parametrize("target,message", [("En revision", MSG_REVISION), ("Cerrado", MSG_CIERRE)])
def test_not_03_empty_note_blocks_submit_with_backend_message(page: Page, fx, target, message):
    open_edit(page, P_EJEC["ID"])
    page.select_option("#edit-project-estado", target)
    page.fill("#edit-project-nota-estado", "   ")
    save_modal(page)
    expect(page.locator("#edit-project-error-alert")).to_be_visible()
    expect(page.locator("#edit-project-error-desc")).to_have_text(message)
    expect(page.locator("#edit-project-modal")).to_be_visible()
    assert fx.puts == []


@pytest.mark.parametrize("target", ["En revision", "Cerrado"])
def test_not_04_put_payload_carries_nota_estado(page: Page, fx, target):
    open_edit(page, P_EJEC["ID"])
    page.select_option("#edit-project-estado", target)
    page.fill("#edit-project-nota-estado", "  Documentación completa y validada  ")
    save_modal(page)
    expect(page.locator("#edit-project-modal")).to_be_hidden()
    assert len(fx.puts) == 1
    assert fx.puts[0]["estado"] == target
    assert fx.puts[0]["nota_estado"] == "Documentación completa y validada"
    assert fx.adjuntos == []


def test_not_05_note_group_resets_between_openings(page: Page, fx):
    open_edit(page, P_EJEC["ID"])
    page.select_option("#edit-project-estado", "Cerrado")
    page.fill("#edit-project-nota-estado", "Texto previo")
    page.locator("#btn-cancel-edit-modal").click()
    open_edit(page, P_EJEC["ID"])
    expect(page.locator("#edit-project-nota-group")).to_be_hidden()
    expect(page.locator("#edit-project-nota-estado")).to_have_value("")


def test_not_06_unchanged_state_sends_no_note_even_if_group_was_used(page: Page, fx):
    open_edit(page, P_EJEC["ID"])
    page.select_option("#edit-project-estado", "Cerrado")
    page.fill("#edit-project-nota-estado", "Nota que ya no aplica")
    page.select_option("#edit-project-estado", "En ejecucion")
    save_modal(page)
    expect(page.locator("#edit-project-modal")).to_be_hidden()
    assert not fx.puts[0].get("nota_estado")


# ---------------------------------------------------------------------------
# S2 / S3 - Evidencias
# ---------------------------------------------------------------------------
def wait_until(page: Page, condition, timeout_ms=10000):
    """Espera activa sobre estado del lado Python (peticiones interceptadas)."""
    waited = 0
    while not condition() and waited < timeout_ms:
        page.wait_for_timeout(100)
        waited += 100
    assert condition(), "La condición esperada no se cumplió a tiempo"


def pdf(name, size=1024):
    return {"name": name, "mimeType": "application/pdf", "buffer": b"a" * size}


def test_evi_01_uploads_go_to_returned_entry_id_one_by_one(page: Page, fx):
    open_edit(page, P_EJEC["ID"])
    page.select_option("#edit-project-estado", "Cerrado")
    page.fill("#edit-project-nota-estado", "Cierre con evidencias")
    page.set_input_files("#edit-project-evidencias", [pdf("acta.pdf"), pdf("informe.pdf", 2048)])
    save_modal(page)
    expect(page.locator("#edit-project-modal")).to_be_hidden()
    wait_until(page, lambda: len(fx.adjuntos) == 2)
    assert [a["path"] for a in fx.adjuntos] == [f"/api/proyectos/9901/bitacora/77/adjuntos"] * 2
    assert sorted(a["filename"] for a in fx.adjuntos) == ["acta.pdf", "informe.pdf"]
    assert all(a["has_archivo_field"] for a in fx.adjuntos)


def test_evi_02_failed_upload_keeps_project_saved_and_names_the_file(page: Page, fx):
    fx.fail_adjunto_names = {"informe.pdf"}
    open_edit(page, P_EJEC["ID"])
    page.select_option("#edit-project-estado", "En revision")
    page.fill("#edit-project-nota-estado", "Motivo de la revisión")
    page.set_input_files("#edit-project-evidencias", [pdf("acta.pdf"), pdf("informe.pdf")])
    save_modal(page)
    toast = page.locator(".alert-toast")
    expect(toast).to_contain_text("informe.pdf")
    expect(toast).not_to_contain_text("acta.pdf")
    expect(toast).to_contain_text("quedó guardado")
    expect(page.locator("#edit-project-modal")).to_be_hidden()
    assert len(fx.puts) == 1 and len(fx.adjuntos) == 2


def test_evi_03_oversize_file_rejected_client_side(page: Page, fx):
    open_edit(page, P_EJEC["ID"])
    page.select_option("#edit-project-estado", "Cerrado")
    page.set_input_files("#edit-project-evidencias", [pdf("grande.pdf", MAX_BYTES + 1)])
    error = page.locator("#edit-project-evidencias-error")
    expect(error).to_be_visible()
    expect(error).to_contain_text("grande.pdf")
    expect(error).to_contain_text("9 MB")
    assert page.eval_on_selector("#edit-project-evidencias", "el => el.files.length") == 0
    assert fx.adjuntos == [] and fx.puts == []


def test_evi_03b_file_of_exactly_9mb_is_accepted(page: Page, fx):
    open_edit(page, P_EJEC["ID"])
    page.select_option("#edit-project-estado", "Cerrado")
    page.set_input_files("#edit-project-evidencias", [pdf("limite.pdf", MAX_BYTES)])
    expect(page.locator("#edit-project-evidencias-error")).to_be_hidden()
    assert page.eval_on_selector("#edit-project-evidencias", "el => el.files.length") == 1


def test_evi_04_disallowed_extension_rejected_client_side(page: Page, fx):
    open_edit(page, P_EJEC["ID"])
    page.select_option("#edit-project-estado", "Cerrado")
    page.set_input_files("#edit-project-evidencias", [{"name": "virus.exe", "mimeType": "application/x-msdownload",
                                                       "buffer": b"MZ"}])
    error = page.locator("#edit-project-evidencias-error")
    expect(error).to_be_visible()
    expect(error).to_contain_text("virus.exe")
    expect(error).to_contain_text("formato")
    assert page.eval_on_selector("#edit-project-evidencias", "el => el.files.length") == 0
    page.set_input_files("#edit-project-evidencias", [pdf("valido.PDF")])
    expect(error).to_be_hidden()


# ---------------------------------------------------------------------------
# S6 - Bitácora
# ---------------------------------------------------------------------------
def test_bit_01_tab_after_summary_with_count(page: Page, fx):
    open_detail(page, 9901)
    tabs = [t.strip().split("\n")[0].strip() for t in page.locator(".tabs-header .tab-btn").all_inner_texts()]
    assert tabs[0] == "Resumen" and tabs[1].startswith("Bitácora")
    expect(page.locator("#tab-count-bitacora")).to_have_text("3")


def test_bit_02_entries_newest_first_with_chips_author_date_text(page: Page, fx):
    open_detail(page, 9901)
    page.locator("#tab-btn-bitacora").click()
    expect(page.locator("#tab-pane-bitacora")).to_be_visible()
    entries = page.locator("#bitacora-list .bitacora-entry")
    expect(entries).to_have_count(3)
    chips = [c.strip() for c in entries.locator(".bitacora-chip").all_inner_texts()]
    assert chips == ["Cierre", "En revisión", "Bitácora"]
    expect(entries.nth(0).locator(".bitacora-chip")).to_have_class(re.compile(r"badge-success"))
    expect(entries.nth(1).locator(".bitacora-chip")).to_have_class(re.compile(r"badge-warning"))
    expect(entries.nth(2).locator(".bitacora-chip")).to_have_class(re.compile(r"badge-neutral"))
    expect(entries.nth(0).locator(".bitacora-author")).to_have_text("Erwin Sandoval")
    expect(entries.nth(0).locator(".bitacora-date")).to_have_text("16-10-2026 09:30")
    expect(entries.nth(2).locator(".bitacora-date")).to_have_text("14-10-2026 16:45")
    # El texto se escapa (sin HTML) y respeta saltos de línea
    expect(entries.nth(1).locator(".bitacora-text")).to_have_text("Falta validar el pase <b>productivo</b>")
    assert entries.nth(1).locator(".bitacora-text b").count() == 0
    assert page.eval_on_selector("#bitacora-list .bitacora-text", "el => getComputedStyle(el).whiteSpace") == "pre-wrap"


def test_bit_03_attachments_listed_and_downloaded_with_original_name(page: Page, fx):
    open_detail(page, 9901)
    page.locator("#tab-btn-bitacora").click()
    adjunto = page.locator("#bitacora-list .bitacora-adjunto").first
    expect(adjunto).to_contain_text("acta.pdf")
    expect(adjunto).to_contain_text("1.5 MB")
    with page.expect_download() as dl:
        adjunto.click()
    assert dl.value.suggested_filename == "acta.pdf"
    assert fx.downloads == ["/api/proyectos/9901/adjuntos/31"]


def test_bit_04_empty_state(page: Page):
    h = login_as(page, ADMIN_USER, "ADMIN", lambda p: Harness(p, bitacora=[]))
    open_detail(page, 9901)
    page.locator("#tab-btn-bitacora").click()
    expect(page.locator("#bitacora-list .bitacora-empty")).to_contain_text("Aún no hay registros en la bitácora")
    expect(page.locator("#tab-count-bitacora")).to_have_text("0")
    assert h.unexpected == []


def test_bit_05_add_entry_posts_text_uploads_files_and_reloads(page: Page, fx):
    open_detail(page, 9901)
    page.locator("#tab-btn-bitacora").click()
    gets_before = fx.bitacora_gets
    page.fill("#bitacora-nuevo-texto", "  Se instaló el pase en QA  ")
    page.set_input_files("#bitacora-nuevo-archivos", [pdf("evidencia.pdf")])
    expect(page.locator("#btn-bitacora-agregar")).to_have_text("Agregar a la bitácora")
    page.locator("#btn-bitacora-agregar").click()
    wait_until(page, lambda: len(fx.adjuntos) == 1)
    assert fx.bitacora_posts == [{"texto": "Se instaló el pase en QA"}]
    assert fx.adjuntos[0]["path"] == "/api/proyectos/9901/bitacora/50/adjuntos"
    assert fx.adjuntos[0]["has_archivo_field"] and fx.adjuntos[0]["filename"] == "evidencia.pdf"
    wait_until(page, lambda: fx.bitacora_gets > gets_before)
    expect(page.locator("#bitacora-list .bitacora-entry").first.locator(".bitacora-text")).to_have_text("Se instaló el pase en QA")
    expect(page.locator("#bitacora-nuevo-texto")).to_have_value("")


def test_bit_06_empty_text_is_blocked_without_request(page: Page, fx):
    open_detail(page, 9901)
    page.locator("#tab-btn-bitacora").click()
    page.fill("#bitacora-nuevo-texto", "   ")
    page.locator("#btn-bitacora-agregar").click()
    expect(page.locator("#bitacora-form-error")).to_have_text("El texto de la bitácora es obligatorio")
    assert fx.bitacora_posts == []


def test_bit_07_invalid_file_in_log_form_rejected(page: Page, fx):
    open_detail(page, 9901)
    page.locator("#tab-btn-bitacora").click()
    page.set_input_files("#bitacora-nuevo-archivos", [{"name": "script.sh", "mimeType": "text/x-sh", "buffer": b"#!"}])
    expect(page.locator("#bitacora-form-error")).to_contain_text("script.sh")
    assert page.eval_on_selector("#bitacora-nuevo-archivos", "el => el.files.length") == 0


def test_bit_08_summary_closure_shows_latest_cierre_entry(page: Page, fx):
    open_detail(page, 9901)
    expect(page.locator("#summary-cierre")).to_contain_text("Cierre aceptado por el cliente.")
    expect(page.locator("#summary-cierre")).to_contain_text("Acta firmada.")


def test_bit_09_summary_closure_falls_back_to_comentario_for_historic_closed(page: Page):
    h = login_as(page, ADMIN_USER, "ADMIN", lambda p: Harness(p, bitacora=[]))
    open_detail(page, 9903)
    expect(page.locator("#summary-cierre")).to_contain_text("Entregado según acta histórica")
    assert h.unexpected == []


def test_bit_10_summary_closure_empty_when_not_closed(page: Page):
    h = login_as(page, ADMIN_USER, "ADMIN", lambda p: Harness(p, bitacora=[ENTRIES[1], ENTRIES[2]]))
    open_detail(page, 9901)
    expect(page.locator("#summary-cierre")).to_contain_text("Sin comentarios de cierre")
    assert h.unexpected == []


def test_bit_11_no_emoji_in_rendered_modal_and_log(page: Page, fx):
    open_detail(page, 9901)
    page.locator("#tab-btn-bitacora").click()
    text = page.locator("#tab-pane-bitacora").inner_text()
    html = page.locator("#tab-pane-bitacora").inner_html()
    assert not EMOJI_RE.search(text) and not EMOJI_RE.search(html)
    page.locator("#btn-dd-edit-project").click()
    page.select_option("#edit-project-estado", "Cerrado")
    modal_text = page.locator("#edit-project-modal").inner_text() + page.locator("#edit-project-modal").inner_html()
    assert not EMOJI_RE.search(modal_text)


# ---------------------------------------------------------------------------
# S5 - Visibilidad
# ---------------------------------------------------------------------------
def test_vis_01_lti_filter_is_locked_on_own_lt(page: Page):
    h = login_as(page, LTI_USER, "LTI", lambda p: Harness(p, passthrough_reads=True))
    select = page.locator("#filter-lt")
    expect(select).to_be_disabled()
    expect(select).to_have_value(LTI_NAME)
    expect(select).to_have_attribute("title", "Solo puedes ver los proyectos asignados a ti")
    assert page.locator("#filter-lt option").count() == 1
    lts = {t.strip() for t in page.locator("#projects-table-body tr.project-row td:nth-child(3)").all_inner_texts()}
    assert lts <= {LTI_NAME}
    assert h.unexpected == []


@pytest.mark.parametrize("username", [ADMIN_USER, FULL_USER_2])
def test_vis_02_full_visibility_users_default_to_all_and_can_change(page: Page, username):
    h = login_as(page, username, "ADMIN", lambda p: Harness(p, passthrough_reads=True))
    select = page.locator("#filter-lt")
    expect(select).to_be_enabled()
    expect(select).to_have_value("__ALL__")
    assert page.evaluate("() => Auth.getUser().ve_todos_proyectos") is True
    select.select_option(LTI_NAME)
    expect(select).to_have_value(LTI_NAME)
    assert h.unexpected == []


def test_vis_03_pending_card_not_clickable_when_restricted(page: Page):
    h = login_as(page, LTI_USER, "LTI", lambda p: Harness(p, passthrough_reads=True))
    card = page.locator("#kpi-card-pendientes")
    assert "kpi-card-clickable" not in (card.get_attribute("class") or "")
    expect(card.locator(".kpi-clickable-badge")).to_have_count(0)
    assert card.get_attribute("role") != "button"
    assert card.get_attribute("aria-pressed") is None
    card.click()
    expect(page.locator("#filter-lt")).to_have_value(LTI_NAME)
    assert h.unexpected == []


def test_vis_03b_pending_card_clickable_for_full_visibility_user(page: Page):
    login_as(page, ADMIN_USER, "ADMIN", lambda p: Harness(p, passthrough_reads=True))
    card = page.locator("#kpi-card-pendientes")
    expect(card).to_have_class(re.compile(r"kpi-card-clickable"))
    expect(card.locator(".kpi-clickable-badge")).to_be_visible()
    card.click()
    expect(page.locator("#filter-lt")).to_have_value("__UNASSIGNED__")


# ---------------------------------------------------------------------------
# S8 - Tooltips KPI
# ---------------------------------------------------------------------------
KPI_TIPS = [
    ("kpi-card-proyectos", "Proyectos asignados",
     "Total de proyectos dentro del filtro de Líder TI actual, en cualquier estado."),
    ("kpi-card-en-curso", "Proyectos en curso",
     "Proyectos con trabajo activo: en ejecución (ya tienen Líder TI) o en revisión."),
    ("kpi-card-pendientes", "Pendientes de asignar",
     "Solicitudes de PM que todavía no tienen Líder TI asignado."),
    ("kpi-card-efectividad", "Efectividad",
     "Porcentaje de proyectos cerrados sobre el total del filtro actual."),
]


@pytest.fixture
def kpi_page(page: Page):
    h = login_as(page, ADMIN_USER, "ADMIN", lambda p: Harness(p, passthrough_reads=True))
    page.set_viewport_size({"width": 1400, "height": 900})
    yield page
    assert h.unexpected == []


def tip_of(page: Page, card_id: str):
    card = page.locator(f"#{card_id}")
    tip_id = card.get_attribute("aria-describedby")
    assert tip_id, f"{card_id} necesita aria-describedby"
    tip = page.locator(f"#{tip_id}")
    assert tip.get_attribute("role") == "tooltip"
    return card, tip


@pytest.mark.parametrize("card_id,title,text", KPI_TIPS)
def test_tip_01_visible_on_hover_only(kpi_page, card_id, title, text):
    page = kpi_page
    card, tip = tip_of(page, card_id)
    expect(tip).to_be_hidden()
    card.hover()
    expect(tip).to_be_visible()
    expect(tip).to_contain_text(title)
    expect(tip).to_contain_text(text)
    box, vp = tip.bounding_box(), page.viewport_size
    assert box["x"] >= 0 and box["y"] >= 0 and box["x"] + box["width"] <= vp["width"], "La burbuja no debe recortarse"
    assert box["width"] <= 290
    page.mouse.move(5, 5)
    expect(tip).to_be_hidden()


@pytest.mark.parametrize("card_id,title,text", KPI_TIPS)
def test_tip_02_visible_on_keyboard_focus(kpi_page, card_id, title, text):
    page = kpi_page
    card, tip = tip_of(page, card_id)
    page.mouse.move(5, 5)
    page.locator("#filter-search").focus()
    expect(tip).to_be_hidden()
    assert card.get_attribute("tabindex") == "0"
    # Las tarjetas preceden al buscador en el orden de tabulación: se retrocede con Shift+Tab
    for _ in range(8):
        page.keyboard.press("Shift+Tab")
        if page.evaluate("(id) => document.activeElement && document.activeElement.id === id", card_id):
            break
    assert page.evaluate("(id) => document.activeElement.id === id", card_id), "La tarjeta debe ser alcanzable con teclado"
    expect(tip).to_be_visible()
    expect(tip).to_contain_text(text)
    page.locator("#filter-search").focus()
    expect(tip).to_be_hidden()


def test_tip_03_cards_have_no_native_title(kpi_page):
    for card_id, _, _ in KPI_TIPS:
        assert kpi_page.locator(f"#{card_id}").get_attribute("title") is None, card_id


def test_tip_04_pending_tip_mentions_click_only_when_clickable(page: Page):
    h = login_as(page, ADMIN_USER, "ADMIN", lambda p: Harness(p, passthrough_reads=True))
    page.locator("#kpi-card-pendientes").hover()
    expect(page.locator("#kpi-tip-pendientes")).to_contain_text("Haz clic para filtrarlas.")
    assert h.unexpected == []


def test_tip_05_pending_tip_has_no_click_hint_when_restricted(page: Page):
    h = login_as(page, LTI_USER, "LTI", lambda p: Harness(p, passthrough_reads=True))
    page.locator("#kpi-card-pendientes").hover()
    expect(page.locator("#kpi-tip-pendientes")).to_be_visible()
    expect(page.locator("#kpi-tip-pendientes")).not_to_contain_text("Haz clic")
    assert h.unexpected == []


def test_tip_06_theme_aware_dark_and_light(kpi_page):
    page = kpi_page
    colors = {}
    for theme in ("light", "dark"):
        page.evaluate("(t) => App.setTheme(t)", theme)
        page.locator("#kpi-card-proyectos").hover()
        tip = page.locator("#kpi-tip-proyectos")
        expect(tip).to_be_visible()
        colors[theme] = page.evaluate(
            "() => { const s = getComputedStyle(document.getElementById('kpi-tip-proyectos')); return [s.backgroundColor, s.color]; }"
        )
        page.mouse.move(5, 5)
    assert colors["light"] != colors["dark"]
    page.evaluate("() => App.setTheme('light')")


def test_tip_07_respects_reduced_motion(kpi_page):
    page = kpi_page
    page.emulate_media(reduced_motion="reduce")
    duration = page.eval_on_selector("#kpi-tip-proyectos", "el => getComputedStyle(el).transitionDuration")
    assert set(duration.replace("s", "").split(", ")) <= {"0"}, duration
    page.emulate_media(reduced_motion="no-preference")
    duration = page.eval_on_selector("#kpi-tip-proyectos", "el => getComputedStyle(el).transitionDuration")
    assert set(duration.replace("s", "").split(", ")) != {"0"}, duration
