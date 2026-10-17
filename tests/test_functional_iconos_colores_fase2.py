"""
BATERÍA DE PRUEBAS FUNCIONALES E2E: ÍCONOS, COLORES Y JERGA (FASE 2)
Proyecto: App LTI - Seguimiento Líderes TI
Especificación: odd/tasks/halo-ux-simplification.md (S8-S13)

Matriz de Cobertura:
- CP-ICO-01: index.html y app.js no contienen emojis.
- CP-ICO-02: La página renderizada (todos los módulos, detalle, historial, alertas y menús) no muestra emojis,
             incluidos los íconos que envía el backend.
- CP-ICO-03: El menú lateral usa íconos de línea SVG en gris; solo el módulo activo usa el rojo HALO.
- CP-JAR-01: La interfaz no muestra jerga técnica (Playwright, SSE, dbo., "Base de Datos Conectada", etc.).
- CP-COL-01: Ningún elemento visible usa violeta o índigo.
- CP-COL-02: Los íconos de los KPI son neutros (todos del mismo gris).
- CP-COL-03: Los números de proyecto no se muestran en rojo (tabla y detalle).
- CP-COL-04: El estado informativo ("En ejecución") usa el teal de HALO, no azul.
- CP-COL-05: Cliente y solicitante de la tabla no van en negrita fuerte.

Todas las pruebas son de solo lectura sobre la BD.
"""

import colorsys
import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from tests.conftest import create_portal_jwt

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
ADMIN_USER = "alejandro.aguilar"

# Pictogramas emoji. Se permiten glifos tipográficos monocromos: ✓ ✕ × ← →
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

# Palabras completas: los nombres de clientes en mayúsculas contienen "SSE" (p. ej. "ASSESORÍAS")
JARGON = [
    r"\bPlaywright\b",
    r"\bSSE\b",
    r"Server-Sent Events",
    r"\bdbo\.",
    r"Base de Datos Conectada",
    r"Portal TI Conectado",
    r"Modo Desatendido",
    r"service-manager-bot",
]

HALO_RED = (218, 41, 28)


def login_admin(page: Page):
    token = create_portal_jwt(
        username=ADMIN_USER, admin_level=2, tool_access={"app-lti": "operador"}, name="Alejandro Aguilar"
    )
    page.context.add_cookies([{"name": "access_token", "value": token, "url": BASE_URL}])
    page.context.add_init_script(
        f"localStorage.setItem('halo_tour_solicitud_lti_seen:{ADMIN_USER}', '1');"
        "['halo_health_score_enabled','halo_executive_diagnosis_enabled','halo_export_pdf_enabled',"
        "'halo_timeline_enabled','halo_alerts_enabled'].forEach(k => localStorage.removeItem(k));"
    )
    page.goto(f"{BASE_URL}/")
    page.wait_for_selector("#projects-table-body tr.project-row", state="visible", timeout=30000)


def parse_rgb(css_color: str):
    m = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)", css_color or "")
    if not m:
        return None
    alpha = float(m.group(4)) if m.group(4) is not None else 1.0
    if alpha == 0:
        return None
    return tuple(int(m.group(i)) for i in range(1, 4))


def hue_sat(rgb):
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    return h * 360, s, l


def is_violet(rgb):
    h, s, l = hue_sat(rgb)
    return 250 <= h <= 320 and s > 0.35 and 0.15 < l < 0.92


def is_red(rgb):
    h, s, l = hue_sat(rgb)
    return (h <= 12 or h >= 345) and s > 0.5 and 0.2 < l < 0.8


VISIBLE_COLORS_JS = """
() => {
  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    const label = (el.id ? '#' + el.id : el.tagName.toLowerCase()) + '.' + (el.className && el.className.baseVal === undefined ? el.className : '');
    out.push([label, cs.color, cs.backgroundColor, cs.borderTopColor, cs.borderLeftColor]);
  }
  return out;
}
"""


def visit_all_views(page: Page):
    """Recorre cada vista y devuelve el texto visible acumulado."""
    texts = [page.locator("body").inner_text()]

    page.locator("#user-menu-btn").click()
    texts.append(page.locator("#user-menu-dropdown").inner_text())
    page.keyboard.press("Escape")

    page.locator("#projects-table-body tr.project-row .btn-row-menu").first.click()
    texts.append(page.locator("#row-actions-menu").inner_text())
    page.keyboard.press("Escape")

    page.locator("#alerts-bell-btn").click()
    expect(page.locator("#alerts-dropdown")).to_be_visible()
    page.wait_for_function(
        "() => document.getElementById('alerts-loading-state').style.display === 'none'", timeout=20000
    )
    texts.append(page.locator("#alerts-dropdown").inner_text())
    page.locator("#alerts-dropdown-close-btn").click()

    page.locator("#projects-table-body tr.project-row td").first.click()
    expect(page.locator("#project-drilldown-section")).to_be_visible(timeout=15000)
    texts.append(page.locator("#project-drilldown-section").inner_text())
    page.locator("#tab-btn-timeline").click()
    page.wait_for_function(
        "() => document.getElementById('timeline-loading-state').style.display === 'none'", timeout=20000
    )
    texts.append(page.locator("#project-drilldown-section").inner_text())
    page.locator("#back-to-projects-btn").click()

    for module, container in (
        ("direct-search", "#module-direct-search-container"),
        ("tickets", "#module-tickets-container"),
        ("solicitud-lti", "#module-solicitud-lti-container"),
        ("usuarios", "#module-usuarios-container"),
    ):
        page.locator(f"#nav-btn-{module}").click()
        expect(page.locator(container)).to_be_visible()
        page.wait_for_timeout(1500)
        texts.append(page.locator("body").inner_text())
        # Opciones de selects (no aparecen en innerText del body)
        texts.extend(page.locator(f"{container} option").all_inner_texts())
    return "\n".join(texts)


# ---------------------------------------------------------------------------
# S8 - Íconos
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("relpath", ["index.html", "js/app.js"])
def test_ico_01_source_files_have_no_emoji(relpath):
    text = (FRONTEND / relpath).read_text(encoding="utf-8")
    found = sorted({ch for ch in EMOJI_RE.findall(text)})
    assert found == [], f"{relpath} contiene emojis: {' '.join(found)}"


def test_ico_02_rendered_views_show_no_emoji(page: Page):
    login_admin(page)
    text = visit_all_views(page)
    found = sorted({ch for ch in EMOJI_RE.findall(text)})
    assert found == [], f"La interfaz muestra emojis: {' '.join(found)}"


def test_ico_03_sidebar_uses_gray_line_icons(page: Page):
    login_admin(page)
    buttons = page.locator("#nav-subbar .nav-module-btn:visible")
    count = buttons.count()
    assert count == 5
    for i in range(count):
        btn = buttons.nth(i)
        svg = btn.locator("svg.ui-icon")
        expect(svg).to_have_count(1)
        assert svg.get_attribute("fill") == "none"
        color = parse_rgb(svg.evaluate("el => getComputedStyle(el).color"))
        is_active = "active" in (btn.get_attribute("class") or "")
        if is_active:
            assert color == HALO_RED, f"El módulo activo debe usar el rojo HALO, usa {color}"
        else:
            _, sat, _ = hue_sat(color)
            assert sat < 0.2, f"Ícono de módulo inactivo con color {color}; debe ser gris"


# ---------------------------------------------------------------------------
# S11 - Jerga técnica
# ---------------------------------------------------------------------------
def test_jar_01_no_technical_jargon_in_ui(page: Page):
    login_admin(page)
    text = visit_all_views(page)
    found = [term for term in JARGON if re.search(term, text)]
    assert found == [], f"La interfaz muestra jerga técnica: {found}"


SOURCE_JARGON = [r"service-manager-bot", r"\bdbo\.[A-Za-z_]+", r"Server-Sent Events", r"\(SSE\)"]


@pytest.mark.parametrize("relpath", ["index.html", "js/app.js"])
def test_jar_02_no_technical_jargon_in_source_copy(relpath):
    # Textos que no aparecen en la vista inicial: consola reiniciada, tablas vacías, modales
    text = (FRONTEND / relpath).read_text(encoding="utf-8")
    found = sorted({m.group(0) for pat in SOURCE_JARGON for m in re.finditer(pat, text)})
    assert found == [], f"{relpath} contiene jerga técnica: {found}"


# ---------------------------------------------------------------------------
# S9 / S10 / S12 - Colores y pesos
# ---------------------------------------------------------------------------
def test_col_01_no_violet_or_indigo_visible(page: Page):
    login_admin(page)
    offenders = []

    def scan(view):
        for label, *colors in page.evaluate(VISIBLE_COLORS_JS):
            for c in colors:
                rgb = parse_rgb(c)
                if rgb and is_violet(rgb):
                    offenders.append(f"{view}: {label} {c}")

    scan("proyectos")
    page.locator("#user-menu-btn").click()
    scan("menu-usuario")
    page.keyboard.press("Escape")
    page.locator("#projects-table-body tr.project-row td").first.click()
    expect(page.locator("#project-drilldown-section")).to_be_visible(timeout=15000)
    page.wait_for_timeout(1500)
    scan("detalle")
    page.locator("#nav-btn-usuarios").click()
    page.wait_for_selector("#module-usuarios-container", state="visible")
    page.wait_for_timeout(2000)
    scan("usuarios")
    assert offenders == [], "Elementos en violeta/índigo:\n" + "\n".join(sorted(set(offenders))[:25])


def test_col_02_kpi_icons_are_neutral(page: Page):
    login_admin(page)
    icons = page.locator("#module-projects-container .kpi-card .kpi-icon")
    assert icons.count() == 6  # S14 dejó 4 KPI; S5 (2026-10-16) agrega En revisión y Cerrados
    styles = icons.evaluate_all(
        "els => els.map(e => [getComputedStyle(e).color, getComputedStyle(e).backgroundColor])"
    )
    assert len({tuple(s) for s in styles}) == 1, f"Los íconos KPI tienen colores distintos: {styles}"
    color = parse_rgb(styles[0][0])
    assert hue_sat(color)[1] < 0.2, f"Ícono KPI no es gris: {color}"


def test_col_03_project_numbers_are_not_red(page: Page):
    login_admin(page)
    num_cell = page.locator("#projects-table-body tr.project-row").first.locator("td").nth(1).locator("span")
    rgb = parse_rgb(num_cell.evaluate("el => getComputedStyle(el).color"))
    assert not is_red(rgb), f"N° de proyecto en rojo en la tabla: {rgb}"

    page.locator("#projects-table-body tr.project-row td").first.click()
    expect(page.locator("#project-drilldown-section")).to_be_visible(timeout=15000)
    rgb = parse_rgb(page.locator("#dd-proj-num").evaluate("el => getComputedStyle(el).color"))
    assert not is_red(rgb), f"N° de proyecto en rojo en el detalle: {rgb}"


def test_col_04_info_status_uses_halo_teal(page: Page):
    login_admin(page)
    page.locator("#nav-btn-solicitud-lti").click()
    badge_rgb = None
    page.locator("#nav-btn-projects").click()
    # El estado informativo es "En ejecución": se dibuja una fila simulada para no depender de los datos de la BD
    page.evaluate("""() => App.renderProjectsTable([{
        ID: 9901, Cliente: 'CLIENTE FIXTURE', Numero_Proyecto: '000QA-FIX-9901', LT_Asignado: 'Erwin Sandoval',
        Estado: 'En ejecucion', Detalle: 'Detalle', Creado: '2026-10-01 10:00:00', Solicitante: 'Corp1- Pm',
        salud: {score: 'NEUTRAL', color: 'gray', label: 'Sin datos', motivos: ['Sin datos']}
    }])""")
    badge = page.locator("#projects-table-body .badge-info").first
    expect(badge).to_be_visible(timeout=15000)
    badge_rgb = parse_rgb(badge.evaluate("el => getComputedStyle(el).color"))
    hue, sat, _ = hue_sat(badge_rgb)
    assert 175 <= hue <= 200 and sat > 0.4, f"Estado informativo no usa teal: {badge_rgb} (hue {hue:.0f})"


def test_col_05_table_client_and_requester_are_not_heavy(page: Page):
    login_admin(page)
    row = page.locator("#projects-table-body tr.project-row").first
    client_weight = int(row.locator(".col-project-client").evaluate("el => getComputedStyle(el).fontWeight"))
    requester = row.locator(".col-solicitante strong, .col-solicitante span").first
    requester_weight = int(requester.evaluate("el => getComputedStyle(el).fontWeight"))
    assert client_weight <= 600, f"Cliente con peso {client_weight}"
    assert requester_weight <= 500, f"Solicitante con peso {requester_weight}"
