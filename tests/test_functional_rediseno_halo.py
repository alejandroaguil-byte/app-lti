"""
BATERÍA DE PRUEBAS FUNCIONALES AUTOMATIZADAS: REDISEÑO INSTITUCIONAL HALO
Proyecto: App LTI - Seguimiento Líderes TI
Especificación: SPECS_REDISENO_PORTAL_HALO.md
Ubicación: tests/test_functional_rediseno_halo.py

Matriz de Cobertura de Pruebas:
- CP-HALO-01: Integridad y especificación del Isotipo Favicon SVG (frontend/favicon.svg).
- CP-HALO-02: Estructura HTML y semántica institucional en Head y Vista SSO (frontend/index.html).
- CP-HALO-03: Arquitectura y componentes de Cabecera Institucional .app-header (frontend/index.html).
- CP-HALO-04: Sub-barra de Navegación Modular .nav-subbar y Módulos de Aplicación (frontend/index.html).
- CP-HALO-05: Tokens de Diseño y Paleta Claro Chile en CSS (frontend/css/styles.css).
- CP-HALO-06: Inmutabilidad de Cabecera HALO y Comportamiento Responsive / Dark Mode (frontend/css/styles.css).
- CP-HALO-07: Verificación de Servicio y Endpoints Estáticos / Salud en Servidor Local (bobbadeveloper).
- CP-HALO-08: Verificación de Autenticación SSO y API Backend en Servidor Local.
- CP-HALO-09: Verificación de Servicio y Endpoints Estáticos / Salud en Servidor de Producción (IACDI).
- CP-HALO-10: Verificación de Autenticación SSO y API Backend en Servidor de Producción (IACDI).
- CP-HALO-11: Verificación E2E Playwright de Renderizado y Estilos Computados HALO.
- CP-HALO-12: Verificación E2E Playwright de Alternancia de Tema y Preservación de Identidad.
"""

import os
import re
import xml.etree.ElementTree as ET
import pytest
import requests
from playwright.sync_api import Page, expect
from tests.conftest import create_portal_jwt, open_user_menu, close_user_menu

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAVICON_PATH = os.path.join(BASE_DIR, "frontend", "favicon.svg")
INDEX_PATH = os.path.join(BASE_DIR, "frontend", "index.html")
STYLES_PATH = os.path.join(BASE_DIR, "frontend", "css", "styles.css")

LOCAL_URL = "http://127.0.0.1:8000"
IACDI_URL = "http://100.82.24.75:8000"


# ==============================================================================
# HELPERS
# ==============================================================================

def get_auth_headers(username: str = "alejandro.aguilar", rol: str = "ADMIN") -> dict:
    """Genera cabecera Authorization Bearer con token SSO firmado."""
    admin_level = 2 if rol == "ADMIN" else 1
    token = create_portal_jwt(username=username, admin_level=admin_level, name="Alejandro Aguilar")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def halo_page():
    """Playwright page fixture with safe fallback if browser binaries/shared libs are missing on remote server."""
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            yield page
            context.close()
            browser.close()
    except Exception as e:
        pytest.skip(f"Playwright chromium browser no disponible en este host: {e}")


# ==============================================================================
# SUITE 1: INTEGRIDAD DEL ARCHIVO FAVICON SVG (frontend/favicon.svg)
# ==============================================================================

def test_cp_halo_01_favicon_file_integrity():
    """
    CP-HALO-01: Presencia e integridad de frontend/favicon.svg
    - Verifica existencia del archivo y tamaño mayor a 0.
    - Valida que sea un XML/SVG bien formado.
    - Valida viewBox='0 0 120 120', width='32', height='32', role='img', aria-label='HALO'.
    - Valida anillo perimetral de 8 nodos circulares con color corporativo #DA291C y radio r='8'.
    - Valida coordenadas exactas de los 8 nodos en el plano 120x120.
    - Valida núcleo central rect con x='47', y='47', width='26', height='26', rx='8' y fill='#0097A9'.
    """
    assert os.path.exists(FAVICON_PATH), f"El archivo favicon.svg no existe en {FAVICON_PATH}"
    with open(FAVICON_PATH, "r", encoding="utf-8") as f:
        content = f.read().strip()
    assert len(content) > 0, "favicon.svg está vacío"

    # Parsear XML SVG
    root = ET.fromstring(content)
    tag_clean = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    assert tag_clean == "svg", f"Elemento raíz esperado 'svg', obtenido '{tag_clean}'"

    # Dimensiones y metadatos
    assert root.attrib.get("viewBox") == "0 0 120 120", "viewBox incorrecto en favicon.svg"
    assert root.attrib.get("width") == "32", "width incorrecto en favicon.svg"
    assert root.attrib.get("height") == "32", "height incorrecto en favicon.svg"
    assert root.attrib.get("role") == "img", "role esperado 'img' en favicon.svg"
    assert root.attrib.get("aria-label") == "HALO", "aria-label esperado 'HALO' en favicon.svg"

    # Anillo exterior de 8 nodos (grupo fill="#DA291C")
    group = None
    rect = None
    for child in root:
        child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if child_tag == "g":
            group = child
        elif child_tag == "rect":
            rect = child

    assert group is not None, "No se encontró el grupo <g> del anillo en favicon.svg"
    assert group.attrib.get("fill") == "#DA291C", "El color fill del grupo de nodos debe ser #DA291C"

    circles = [c for c in group if (c.tag.split("}")[-1] if "}" in c.tag else c.tag) == "circle"]
    assert len(circles) == 8, f"Se esperaban exactamente 8 círculos en el anillo, encontrados {len(circles)}"

    expected_coords = [
        ("60", "16"), ("91", "29"), ("104", "60"), ("91", "91"),
        ("60", "104"), ("29", "91"), ("16", "60"), ("29", "29")
    ]
    actual_coords = [(c.attrib.get("cx", "").strip(), c.attrib.get("cy", "").strip()) for c in circles]
    for exp_cx, exp_cy in expected_coords:
        assert (exp_cx, exp_cy) in actual_coords, f"Coordenada ({exp_cx}, {exp_cy}) no encontrada en anillo SVG"
        circle_node = next(c for c in circles if c.attrib.get("cx", "").strip() == exp_cx and c.attrib.get("cy", "").strip() == exp_cy)
        assert circle_node.attrib.get("r") == "8", f"El radio del nodo en ({exp_cx}, {exp_cy}) debe ser 8"

    # Núcleo central rect (#0097A9)
    assert rect is not None, "No se encontró el elemento <rect> del núcleo central en favicon.svg"
    assert rect.attrib.get("x") == "47", "Coordenada x del rect debe ser 47"
    assert rect.attrib.get("y") == "47", "Coordenada y del rect debe ser 47"
    assert rect.attrib.get("width") == "26", "Ancho del rect debe ser 26"
    assert rect.attrib.get("height") == "26", "Alto del rect debe ser 26"
    assert rect.attrib.get("rx") == "8", "Radio de curvatura rx debe ser 8"
    assert rect.attrib.get("fill") == "#0097A9", "El color del núcleo central debe ser #0097A9 (Teal HALO)"


# ==============================================================================
# SUITE 2: ESTRUCTURA Y SEMÁNTICA HTML (frontend/index.html)
# ==============================================================================

def test_cp_halo_02_html_head_and_auth_view():
    """
    CP-HALO-02: Metadatos en <head> y pantalla de verificación SSO (#auth-view)
    - Título del documento: 'HALO — App Líderes TI'.
    - Enlace a favicon SVG: <link rel="icon" type="image/svg+xml" href="favicon.svg">.
    - Contenedor #auth-view con .auth-card, isotipo HALO SVG con nodos #DA291C y núcleo #0097A9.
    - Tipografía y títulos corporativos 'HALO' y 'App Líderes TI'.
    - Mensaje de espera de verificación de sesión SSO en Portal de Acceso.
    - Indicador spinner .spinner-inline.
    """
    assert os.path.exists(INDEX_PATH), f"No existe {INDEX_PATH}"
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # Title & Favicon
    assert "<title>HALO — App Líderes TI</title>" in html, "Título <title>HALO — App Líderes TI</title> no encontrado"
    assert re.search(r'<link\s+rel="icon"\s+type="image/svg\+xml"\s+href="favicon\.svg">', html), "Enlace rel='icon' SVG no encontrado"

    # Auth View (#auth-view)
    assert 'id="auth-view"' in html, "Contenedor #auth-view no encontrado en index.html"
    assert 'class="auth-card"' in html, "Clase .auth-card no encontrada dentro de #auth-view"
    assert "Comprobando sesión en Portal de Acceso..." in html, "Texto de comprobación SSO no encontrado"
    assert 'class="spinner-inline"' in html, "Spinner .spinner-inline no encontrado en auth-view"

    # Isotipo en #auth-view
    auth_view_match = re.search(r'<div id="auth-view".*?</div>\s*</div>', html, re.DOTALL)
    assert auth_view_match is not None, "Bloque #auth-view no delimitado correctamente"
    auth_section = auth_view_match.group(0)
    assert '#DA291C' in auth_section, "Color #DA291C del isotipo HALO ausente en #auth-view"
    assert '#0097A9' in auth_section, "Color #0097A9 del núcleo HALO ausente en #auth-view"
    assert "HALO" in auth_section and "App Líderes TI" in auth_section, "Textos HALO y App Líderes TI ausentes en #auth-view"


def test_cp_halo_03_html_app_header_structure():
    """
    CP-HALO-03: Cabecera institucional <header class="app-header">
    - Contenedor <header class="app-header">.
    - Bloque de marca .brand-inline con isotipo SVG monocromático #FDEDEA.
    - .brand-name con texto 'HALO'.
    - .brand-sub con texto 'App Líderes TI'.
    - Bloque de usuario .user-area conteniendo .user-block con #user-avatar y #username-label.
    - Botón de cierre de sesión institucional #btn-logout accesible con icono SVG y título/aria-label.
    """
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    header_match = re.search(r'<header class="app-header">.*?</header>', html, re.DOTALL)
    assert header_match is not None, "Elemento <header class='app-header'> no encontrado"
    header_html = header_match.group(0)

    # Brand inline
    assert 'class="brand-inline"' in header_html, "Contenedor .brand-inline ausente en app-header"
    assert '#FDEDEA' in header_html, "Color monocromático #FDEDEA ausente en el isotipo de la cabecera"
    assert '<h1 class="brand-name">HALO</h1>' in header_html, "Elemento .brand-name 'HALO' no encontrado"
    assert '<p class="brand-sub">App Líderes TI</p>' in header_html, "Elemento .brand-sub 'App Líderes TI' no encontrado"

    # User area & Logout
    assert 'class="user-area"' in header_html, "Contenedor .user-area no encontrado en app-header"
    assert 'id="user-avatar"' in header_html, "Elemento #user-avatar ausente en app-header"
    assert 'id="username-label"' in header_html, "Elemento #username-label ausente en app-header"
    assert 'id="btn-logout"' in header_html, "Botón #btn-logout ausente en app-header"
    assert 'aria-label="Salir"' in header_html or 'title="Cerrar Sesión"' in header_html, "Atributos accesibles ausentes en #btn-logout"


def test_cp_halo_04_html_nav_subbar_structure():
    """
    CP-HALO-04: Sub-barra de navegación modular <nav class="nav-subbar">
    - Contenedor <nav class="nav-subbar" id="nav-subbar" aria-label="Navegación de módulos">.
    - Contenedor .nav-modules con los 5 botones de módulos identificados por id (nombres cortos, fase 1 UX):
      1. #nav-btn-projects ("Proyectos")
      2. #nav-btn-direct-search ("Búsqueda")
      3. #nav-btn-tickets ("Tickets SM")
      4. #nav-btn-solicitud-lti ("Solicitudes LTI")
      5. #nav-btn-usuarios ("Usuarios", bajo "Administración")
    - El badge de rol #user-role-badge y el conmutador de tema #theme-toggle-btn (#theme-icon) viven en el
      menú de usuario de la cabecera, no en la barra lateral.
    """
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    subbar_match = re.search(r'<nav class="nav-subbar"[^>]*>.*?</nav>', html, re.DOTALL)
    assert subbar_match is not None, "Elemento <nav class='nav-subbar'> no encontrado en index.html"
    subbar_html = subbar_match.group(0)

    # Módulos requeridos
    expected_buttons = [
        ("nav-btn-projects", "Proyectos"),
        ("nav-btn-direct-search", "Búsqueda"),
        ("nav-btn-tickets", "Tickets SM"),
        ("nav-btn-solicitud-lti", "Solicitudes LTI"),
        ("nav-btn-usuarios", "Usuarios")
    ]
    for btn_id, btn_text in expected_buttons:
        assert f'id="{btn_id}"' in subbar_html, f"Botón de módulo #{btn_id} no encontrado en nav-subbar"
        assert btn_text in subbar_html, f"Texto '{btn_text}' no encontrado para botón #{btn_id}"

    # Badge de rol y conmutador de tema: en el menú de usuario de la cabecera
    header_html = re.search(r'<header class="app-header">.*?</header>', html, re.DOTALL).group(0)
    for el_id in ("user-role-badge", "theme-toggle-btn", "theme-icon"):
        assert f'id="{el_id}"' not in subbar_html, f"#{el_id} no debe estar en nav-subbar"
        assert f'id="{el_id}"' in header_html, f"#{el_id} no encontrado en el menú de usuario de la cabecera"


# ==============================================================================
# SUITE 3: TOKENS DE DISEÑO Y REGLAS CSS (frontend/css/styles.css)
# ==============================================================================

def test_cp_halo_05_css_tokens_and_variables():
    """
    CP-HALO-05: Tokens corporativos Claro Chile en variables CSS
    - Variables :root para modo claro:
      * --primary: #DA291C
      * --primary-hover: #93190F
      * --primary-light: #FBE9E7
      * --halo-header: #B52217
      * --halo-teal: #0097A9
      * --halo-contrast: #FDEDEA
    - Variables [data-theme="dark"] para modo oscuro:
      * --primary: #E03B2F
      * --primary-hover: #DA291C
      * --halo-header: #B52217
      * --halo-teal: #0097A9
      * --halo-contrast: #FDEDEA
    """
    assert os.path.exists(STYLES_PATH), f"No existe {STYLES_PATH}"
    with open(STYLES_PATH, "r", encoding="utf-8") as f:
        css = f.read()

    # Tokens en :root
    assert "--primary: #DA291C" in css, "Token --primary: #DA291C ausente en styles.css"
    assert "--primary-hover: #93190F" in css, "Token --primary-hover: #93190F ausente en styles.css"
    assert "--primary-light: #FBE9E7" in css, "Token --primary-light: #FBE9E7 ausente en styles.css"
    assert "--halo-header: #B52217" in css, "Token --halo-header: #B52217 ausente en styles.css"
    assert "--halo-teal: #0097A9" in css, "Token --halo-teal: #0097A9 ausente en styles.css"
    assert "--halo-contrast: #FDEDEA" in css, "Token --halo-contrast: #FDEDEA ausente en styles.css"

    # Tokens en [data-theme="dark"]
    dark_block_match = re.search(r'\[data-theme="dark"\]\s*\{(.*?)\}', css, re.DOTALL)
    assert dark_block_match is not None, "Bloque [data-theme='dark'] ausente en styles.css"
    dark_css = dark_block_match.group(1)
    assert "--primary: #E03B2F" in dark_css, "--primary en dark theme debe ser #E03B2F"
    assert "--halo-header: #B52217" in dark_css, "--halo-header en dark theme debe permanecer #B52217"
    assert "--halo-teal: #0097A9" in dark_css, "--halo-teal en dark theme debe permanecer #0097A9"


def test_cp_halo_06_css_header_immutability_and_subbar_rules():
    """
    CP-HALO-06: Reglas de .app-header y .nav-subbar con inmutabilidad de la cabecera
    - .app-header con fondo fijo '#B52217 !important' (no muta en modo oscuro).
    - .app-header con flex layout, padding y z-index adecuado.
    - .nav-subbar con background dinámico var(--bg-surface).
    - Botones .nav-module-btn y estilos interactivos.
    """
    with open(STYLES_PATH, "r", encoding="utf-8") as f:
        css = f.read()

    # Regla de .app-header
    header_rule_match = re.search(r'\.app-header\s*\{([^}]+)\}', css)
    assert header_rule_match is not None, "Regla .app-header no encontrada en styles.css"
    header_props = header_rule_match.group(1)
    assert "background: #B52217 !important" in header_props, ".app-header debe tener 'background: #B52217 !important'"

    # Regla de .nav-subbar
    subbar_rule_match = re.search(r'\.nav-subbar\s*\{([^}]+)\}', css)
    assert subbar_rule_match is not None, "Regla .nav-subbar no encontrada en styles.css"
    subbar_props = subbar_rule_match.group(1)
    assert "background-color: var(--bg-surface)" in subbar_props, ".nav-subbar debe usar var(--bg-surface)"
    assert "position: sticky" in subbar_props, ".nav-subbar debe tener position: sticky"


# ==============================================================================
# SUITE 4: SERVICIOS Y ENDPOINTS EN VIVO - SERVIDOR LOCAL (bobbadeveloper)
# ==============================================================================

def test_cp_halo_07_local_static_and_health_endpoints():
    """
    CP-HALO-07: Verificación de entrega HTTP de recursos estáticos y endpoint de salud en Local
    - GET / -> HTTP 200 conteniendo título 'HALO — App Líderes TI'.
    - GET /favicon.svg -> HTTP 200 con Content-Type svg y contenido de isotipo HALO.
    - GET /css/styles.css -> HTTP 200 con Content-Type css y token --halo-header.
    - GET /js/app.js -> HTTP 200 con Content-Type javascript.
    - GET /api/health -> HTTP 200 con payload JSON {"status": "ok", "app": "HALO — App Líderes TI"}.
    """
    # 1. Root
    res_root = requests.get(f"{LOCAL_URL}/", timeout=5)
    assert res_root.status_code == 200, f"Local GET / devolvió código {res_root.status_code}"
    assert "HALO — App Líderes TI" in res_root.text, "El HTML local no contiene el título HALO"

    # 2. Favicon
    res_fav = requests.get(f"{LOCAL_URL}/favicon.svg", timeout=5)
    assert res_fav.status_code == 200, f"Local GET /favicon.svg devolvió {res_fav.status_code}"
    assert "image/svg" in res_fav.headers.get("content-type", "").lower(), "Content-Type del favicon no es SVG"
    assert "#DA291C" in res_fav.text and "#0097A9" in res_fav.text, "Contenido de favicon.svg local no tiene nodos HALO"

    # 3. CSS
    res_css = requests.get(f"{LOCAL_URL}/css/styles.css", timeout=5)
    assert res_css.status_code == 200, f"Local GET /css/styles.css devolvió {res_css.status_code}"
    assert "--halo-header: #B52217" in res_css.text, "Variable --halo-header ausente en styles.css servido localmente"

    # 4. JS
    res_js = requests.get(f"{LOCAL_URL}/js/app.js", timeout=5)
    assert res_js.status_code == 200, f"Local GET /js/app.js devolvió {res_js.status_code}"

    # 5. Health
    res_health = requests.get(f"{LOCAL_URL}/api/health", timeout=5)
    assert res_health.status_code == 200, f"Local GET /api/health devolvió {res_health.status_code}"
    data_health = res_health.json()
    assert data_health.get("status") == "ok", "Campo status no es 'ok' en /api/health local"
    assert "HALO" in data_health.get("app", ""), "Campo app no menciona HALO en /api/health local"


def test_cp_halo_08_local_auth_and_business_api():
    """
    CP-HALO-08: Verificación de autenticación y endpoints operativos en Local
    - GET /api/auth/me sin autenticación -> HTTP 401 Unauthorized.
    - GET /api/auth/me con JWT firmado SSO -> HTTP 200 con datos de usuario y rol ADMIN.
    - GET /api/lideres -> HTTP 200 retornando lista de líderes oficiales.
    - GET /api/estados -> HTTP 200 retornando estados operativos.
    - GET /api/kpis -> HTTP 200 retornando métricas cuantitativas del dashboard.
    - GET /api/proyectos -> HTTP 200 retornando colección de proyectos.
    """
    # Sin autenticación
    res_unauth = requests.get(f"{LOCAL_URL}/api/auth/me", timeout=5)
    assert res_unauth.status_code == 401, f"Se esperaba 401 sin auth, se obtuvo {res_unauth.status_code}"

    # Con autenticación
    headers = get_auth_headers("alejandro.aguilar", "ADMIN")
    res_me = requests.get(f"{LOCAL_URL}/api/auth/me", headers=headers, timeout=5)
    assert res_me.status_code == 200, f"Local GET /api/auth/me falló con {res_me.status_code}"
    me_data = res_me.json()
    assert me_data.get("username") == "alejandro.aguilar"
    assert me_data.get("rol") == "ADMIN"

    # Endpoints operativos
    for ep in ["/api/lideres", "/api/estados", "/api/kpis", "/api/proyectos"]:
        res_ep = requests.get(f"{LOCAL_URL}{ep}", headers=headers, timeout=5)
        assert res_ep.status_code == 200, f"Local {ep} devolvió {res_ep.status_code}"


# ==============================================================================
# SUITE 5: SERVICIOS Y ENDPOINTS EN VIVO - SERVIDOR DE PRODUCCIÓN (IACDI)
# ==============================================================================

def test_cp_halo_09_iacdi_static_and_health_endpoints():
    """
    CP-HALO-09: Verificación de entrega HTTP en Producción IACDI (100.82.24.75:8000)
    - GET / -> HTTP 200 conteniendo título 'HALO — App Líderes TI'.
    - GET /favicon.svg -> HTTP 200 con Content-Type svg y contenido de isotipo HALO.
    - GET /css/styles.css -> HTTP 200 con Content-Type css y token --halo-header.
    - GET /js/app.js -> HTTP 200 con Content-Type javascript.
    - GET /api/health -> HTTP 200 con payload JSON {"status": "ok", "app": "HALO — App Líderes TI"}.
    """
    # 1. Root
    res_root = requests.get(f"{IACDI_URL}/", timeout=6)
    assert res_root.status_code == 200, f"IACDI GET / devolvió código {res_root.status_code}"
    assert "HALO — App Líderes TI" in res_root.text, "El HTML en IACDI no contiene el título HALO"

    # 2. Favicon
    res_fav = requests.get(f"{IACDI_URL}/favicon.svg", timeout=6)
    assert res_fav.status_code == 200, f"IACDI GET /favicon.svg devolvió {res_fav.status_code}"
    assert "image/svg" in res_fav.headers.get("content-type", "").lower(), "Content-Type del favicon en IACDI no es SVG"
    assert "#DA291C" in res_fav.text and "#0097A9" in res_fav.text, "Contenido de favicon.svg en IACDI no tiene nodos HALO"

    # 3. CSS
    res_css = requests.get(f"{IACDI_URL}/css/styles.css", timeout=6)
    assert res_css.status_code == 200, f"IACDI GET /css/styles.css devolvió {res_css.status_code}"
    assert "--halo-header: #B52217" in res_css.text, "Variable --halo-header ausente en styles.css en IACDI"

    # 4. JS
    res_js = requests.get(f"{IACDI_URL}/js/app.js", timeout=6)
    assert res_js.status_code == 200, f"IACDI GET /js/app.js devolvió {res_js.status_code}"

    # 5. Health
    res_health = requests.get(f"{IACDI_URL}/api/health", timeout=6)
    assert res_health.status_code == 200, f"IACDI GET /api/health devolvió {res_health.status_code}"
    data_health = res_health.json()
    assert data_health.get("status") == "ok", "Campo status no es 'ok' en /api/health en IACDI"
    assert "HALO" in data_health.get("app", ""), "Campo app no menciona HALO en /api/health en IACDI"


def test_cp_halo_10_iacdi_auth_and_business_api():
    """
    CP-HALO-10: Verificación de autenticación y endpoints operativos en Servidor de Producción IACDI
    - GET /api/auth/me sin autenticación -> HTTP 401 Unauthorized.
    - GET /api/auth/me con JWT firmado SSO -> HTTP 200 con datos de usuario y rol ADMIN.
    - GET /api/lideres, /api/estados, /api/kpis, /api/proyectos -> HTTP 200 en IACDI.
    """
    # Sin autenticación
    res_unauth = requests.get(f"{IACDI_URL}/api/auth/me", timeout=6)
    assert res_unauth.status_code == 401, f"Se esperaba 401 sin auth en IACDI, se obtuvo {res_unauth.status_code}"

    # Con autenticación
    headers = get_auth_headers("alejandro.aguilar", "ADMIN")
    res_me = requests.get(f"{IACDI_URL}/api/auth/me", headers=headers, timeout=6)
    assert res_me.status_code == 200, f"IACDI GET /api/auth/me falló con {res_me.status_code}"
    me_data = res_me.json()
    assert me_data.get("username") == "alejandro.aguilar"
    assert me_data.get("rol") == "ADMIN"

    # Endpoints operativos en IACDI
    for ep in ["/api/lideres", "/api/estados", "/api/kpis", "/api/proyectos"]:
        res_ep = requests.get(f"{IACDI_URL}{ep}", headers=headers, timeout=6)
        assert res_ep.status_code == 200, f"IACDI {ep} devolvió {res_ep.status_code}"


# ==============================================================================
# SUITE 6: PLAYWRIGHT E2E INTERACTIVO - VERIFICACIÓN DE RENDERIZADO Y DOM
# ==============================================================================

def test_cp_halo_11_e2e_rendered_header_and_subbar(halo_page: Page, base_url: str):
    """
    CP-HALO-11: Verificación de renderizado de cabecera y sub-barra en navegador
    - Inyecta cookie de sesión SSO para autenticar.
    - Carga la página y verifica título 'HALO — App Líderes TI'.
    - Verifica visibilidad de .app-header y que su color computado de fondo sea rgb(181, 34, 23) (#B52217).
    - Verifica marca institucional: .brand-name ('HALO') y .brand-sub ('App Líderes TI').
    - Verifica que .nav-subbar esté visible con los botones de módulos operativos.
    - Verifica visibilidad de #user-avatar, #username-label y #btn-logout.
    """
    token = create_portal_jwt(username="alejandro.aguilar", admin_level=2, name="Alejandro Aguilar")
    halo_page.context.add_cookies([{
        "name": "access_token",
        "value": token,
        "url": base_url,
    }])

    halo_page.goto(f"{base_url}/")
    halo_page.wait_for_selector("#app-view", state="visible", timeout=25000)
    halo_page.wait_for_function("() => window.App && window.App.isInitialized === true", timeout=25000)

    # Validar título de pestaña
    assert halo_page.title() == "HALO — App Líderes TI", f"Título inesperado: {halo_page.title()}"

    # Validar .app-header
    header = halo_page.locator(".app-header")
    expect(header).to_be_visible()
    header_bg = header.evaluate("el => window.getComputedStyle(el).backgroundColor")
    assert header_bg == "rgb(181, 34, 23)", f"Color de fondo de .app-header esperado rgb(181, 34, 23), obtenido {header_bg}"

    # Validar textos de marca
    expect(halo_page.locator(".brand-name")).to_have_text("HALO")
    expect(halo_page.locator(".brand-sub")).to_have_text("App Líderes TI")

    # Validar user area
    expect(halo_page.locator("#user-avatar")).to_be_visible()
    expect(halo_page.locator("#username-label")).to_be_visible()
    open_user_menu(halo_page)
    expect(halo_page.locator("#btn-logout")).to_be_visible()
    close_user_menu(halo_page)

    # Validar sub-barra y módulos
    expect(halo_page.locator("#nav-subbar")).to_be_visible()
    expect(halo_page.locator("#nav-btn-projects")).to_be_visible()
    expect(halo_page.locator("#nav-btn-direct-search")).to_be_visible()
    expect(halo_page.locator("#nav-btn-tickets")).to_be_visible()
    expect(halo_page.locator("#nav-btn-solicitud-lti")).to_be_visible()


def test_cp_halo_12_e2e_theme_toggle_header_immutability(halo_page: Page, base_url: str):
    """
    CP-HALO-12: Alternancia de tema (Modo Claro / Modo Oscuro) e inmutabilidad de cabecera
    - Verifica que el tema inicial sea data-theme='light'.
    - Presiona el conmutador #theme-toggle-btn.
    - Valida que html cambie a data-theme='dark'.
    - Valida que el color de fondo de .app-header permanezca exactamente rgb(181, 34, 23).
    - Valida que el icono del conmutador de tema cambie de Luna a Sol.
    - Presiona nuevamente #theme-toggle-btn y valida regreso a modo claro (data-theme='light').
    """
    token = create_portal_jwt(username="alejandro.aguilar", admin_level=2, name="Alejandro Aguilar")
    halo_page.context.add_cookies([{
        "name": "access_token",
        "value": token,
        "url": base_url,
    }])

    halo_page.goto(f"{base_url}/")
    halo_page.wait_for_selector("#app-view", state="visible", timeout=25000)
    halo_page.wait_for_function("() => window.App && window.App.isInitialized === true", timeout=25000)

    # Estado inicial: light
    theme_btn = halo_page.locator("#theme-toggle-btn")
    open_user_menu(halo_page)
    expect(theme_btn).to_be_visible()

    initial_theme = halo_page.locator("html").get_attribute("data-theme")
    assert initial_theme in ("light", None), f"Tema inicial inesperado: {initial_theme}"

    # Alternar a modo oscuro
    theme_btn.click()
    halo_page.wait_for_timeout(300)
    assert halo_page.locator("html").get_attribute("data-theme") == "dark", "El atributo data-theme no cambió a 'dark'"

    # Verificar inmutabilidad del header en modo oscuro
    header_bg_dark = halo_page.locator(".app-header").evaluate("el => window.getComputedStyle(el).backgroundColor")
    assert header_bg_dark == "rgb(181, 34, 23)", f"El fondo del header cambió en dark mode: {header_bg_dark}"

    # Alternar de regreso a modo claro
    theme_btn.click()
    halo_page.wait_for_timeout(300)
    assert halo_page.locator("html").get_attribute("data-theme") == "light", "El atributo data-theme no regresó a 'light'"
    header_bg_light = halo_page.locator(".app-header").evaluate("el => window.getComputedStyle(el).backgroundColor")
    assert header_bg_light == "rgb(181, 34, 23)", f"El fondo del header cambió en light mode: {header_bg_light}"

