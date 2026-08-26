"""
Módulo de automatización para la creación de tickets (interacciones) en Service Manager.
Provee ejecución desatendida mediante Playwright Async y emisión de eventos en tiempo real (SSE).
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from typing import AsyncGenerator, Dict, Any, Optional, Tuple

from playwright.async_api import (
    async_playwright,
    Page,
    Frame,
    BrowserContext,
    Browser,
    Playwright,
    Dialog,
)

logger = logging.getLogger("ticket_automation")

# ==============================================================================
# CONSTANTES Y VALORES POR DEFECTO
# ==============================================================================
DEFAULT_PORTAL_URL = "https://portalti.clarocloud.cl:8443/smwebtier/index.do?lang=es"
DEFAULT_PORTAL_USER = "Alejandro.Aguilar"
DEFAULT_PORTAL_PASS = "Cl4r0.2026**"
DEFAULT_TIMEOUT = 30_000

PORTAL_URL = os.getenv("PORTAL_URL", DEFAULT_PORTAL_URL)
PORTAL_USER = os.getenv("PORTAL_USER", DEFAULT_PORTAL_USER)
PORTAL_PASS = os.getenv("PORTAL_PASS", DEFAULT_PORTAL_PASS)
TIMEOUT = int(os.getenv("PORTAL_TIMEOUT", str(DEFAULT_TIMEOUT)))

DEFAULT_CONTACTO = "ALEJANDRO JAVIER AGUILAR MORALES"
DEFAULT_TITULO = "Creacion test automatizacion"
DEFAULT_DESCRIPCION = "Prueba test automatización"
DEFAULT_AREA = "Proyectos"
DEFAULT_SUBAREA = "Apoyo habilitacion cliente"
DEFAULT_DETALLE = "Apoyo habilitacion cliente"
DEFAULT_GRUPO = "Lideres Tecnicos"
DEFAULT_IMPACTO = "3 - Menor (Existen WorkAround)"
DEFAULT_URGENCIA = "3 - Media (Resolución a mediano plazo)"

_SEARCH_INPUT_RE = re.compile(r"find|buscar|b[uú]squeda|search|consulta|filtrar|query", re.I)
_SEARCH_BUTTON_RE = re.compile(
    r"buscar|b[uú]squeda|search|find|aceptar|aplicar|\bok\b|filtrar|consultar|\bir\b|\bgo\b|seleccionar",
    re.I,
)
_GRUPO_RELACIONADO_RE = re.compile(r"grupo|asignaci[oó]n|buscar|rellenar|find|fill", re.I)


# ==============================================================================
# UTILIDADES SSE Y PORTAPAPELES
# ==============================================================================
def format_sse(data: Dict[str, Any]) -> str:
    """Formatea un diccionario como mensaje SSE (Server-Sent Events)."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def copy_id_to_clipboard(value: str) -> None:
    """Intenta copiar el ID generado al portapapeles de forma tolerante."""
    try:
        import pyperclip
        pyperclip.copy(value)
        logger.info(f"ID copiado al portapapeles: {value}")
    except Exception as exc:
        logger.debug(f"No se pudo copiar al portapapeles (ignorable en headless): {exc}")


def _is_page(target: Any) -> bool:
    """Determina si un objetivo es una Page o un Frame."""
    return hasattr(target, "close") and hasattr(target, "title")


# ==============================================================================
# LOCALIZACIÓN Y NAVEGACIÓN EN FRAMES
# ==============================================================================
async def find_servicios_internos(
    context: BrowserContext,
    timeout_ms: int = 15_000
) -> Tuple[Frame, Any]:
    """Busca el enlace 'Servicios Internos' dentro de cualquier frame de las páginas abiertas."""
    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        for p in context.pages:
            for frame in p.frames:
                try:
                    link = frame.get_by_role("link", name="Servicios Internos")
                    if await link.count() > 0:
                        return frame, link
                except Exception:
                    continue
        await asyncio.sleep(0.5)
    raise TimeoutError("No se encontró el enlace 'Servicios Internos' en ningún frame")


async def click_servicios_internos(
    context: BrowserContext,
    page: Page
) -> Frame:
    """Hace clic en 'Servicios Internos' y espera a que el formulario se cargue."""
    frame, link = await find_servicios_internos(context)
    await link.first.scroll_into_view_if_needed()
    await link.first.click(timeout=10_000, force=True)
    await page.wait_for_timeout(3000)
    return frame


async def fill_by_label(frame: Frame, label_regex: str, value: str) -> None:
    """Llena un campo combobox o textbox buscando por regex en su aria-label/name."""
    for role in ("combobox", "textbox"):
        try:
            loc = frame.get_by_role(role, name=re.compile(label_regex, re.I)).first
            if await loc.count() > 0:
                await loc.fill(value)
                return
        except Exception:
            continue
    raise RuntimeError(f"No se encontró campo con patrón {label_regex}")


# ==============================================================================
# ESTRATEGIAS RESILIENTES: DESCRIPCIÓN (#X57 / #X57View)
# ==============================================================================
async def _read_descripcion(frame: Frame) -> str:
    """Lee el texto actual del campo de descripción (#X57View o #X57)."""
    try:
        root = frame.locator("#X57View").first
        if await root.count() > 0:
            txt = await root.evaluate("el => (el.innerText || el.textContent || '').trim()")
            if txt:
                return txt
    except Exception:
        pass
    try:
        x57 = frame.locator("#X57").first
        if await x57.count() > 0:
            v = await x57.evaluate("el => el.value !== undefined ? el.value : ''")
            if v:
                return v
    except Exception:
        pass
    return ""


async def fill_descripcion(frame: Frame, descripcion: str) -> None:
    """
    Llena el campo de descripción ejecutando en cascada todas las estrategias resilientes
    probadas en portal_login.py.
    """
    root = frame.locator("#X57View").first
    await root.wait_for(timeout=5_000)

    try:
        await root.click(timeout=4_000)
        await frame.wait_for_timeout(400)
    except Exception:
        pass

    # (0) Textarea/Input real subyacente #X57
    x57 = frame.locator("#X57").first
    if await x57.count() > 0:
        try:
            tag = await x57.evaluate("el => el.tagName")
            if tag in ("INPUT", "TEXTAREA"):
                await x57.fill(descripcion, timeout=4_000, force=True)
                await frame.wait_for_timeout(300)
                read_val = await _read_descripcion(frame)
                if descripcion in read_val:
                    logger.info("Descripción llenada mediante estrategia (0) #X57")
                    return
        except Exception:
            pass

    await frame.wait_for_timeout(250)

    # (a) Clic + fill directo en #X57View
    try:
        await root.click(timeout=4_000, force=True)
        await frame.wait_for_timeout(300)
        await root.fill(descripcion)
        await frame.wait_for_timeout(300)
        if descripcion in await _read_descripcion(frame):
            logger.info("Descripción llenada mediante estrategia (a) #X57View")
            return
    except Exception:
        pass

    await frame.wait_for_timeout(250)

    # (b) Clic + fill en descendiente [contenteditable]
    for sel in ("#X57View [contenteditable]", "#X57View [contenteditable='true']"):
        try:
            loc = frame.locator(sel).first
            if await loc.count() > 0:
                await loc.click(timeout=4_000)
                await frame.wait_for_timeout(300)
                await loc.fill(descripcion)
                await frame.wait_for_timeout(300)
                if descripcion in await _read_descripcion(frame):
                    logger.info(f"Descripción llenada mediante estrategia (b) {sel}")
                    return
        except Exception:
            continue

    await frame.wait_for_timeout(250)

    # (c) Clic + fill en textarea/input descendiente
    for sel in ("#X57View textarea", "#X57View input"):
        try:
            loc = frame.locator(sel).first
            if await loc.count() > 0:
                await loc.click(timeout=4_000)
                await frame.wait_for_timeout(300)
                await loc.fill(descripcion)
                await frame.wait_for_timeout(300)
                if descripcion in await _read_descripcion(frame):
                    logger.info(f"Descripción llenada mediante estrategia (c) {sel}")
                    return
        except Exception:
            continue

    await frame.wait_for_timeout(250)

    # (d) press_sequentially (teclado real simulado)
    for sel in (
        "#X57View [contenteditable]",
        "#X57View textarea",
        "#X57View input",
        "#X57View",
    ):
        try:
            loc = frame.locator(sel).first
            if await loc.count() > 0:
                await loc.click(timeout=4_000)
                await frame.wait_for_timeout(300)
                await loc.press_sequentially(descripcion, delay=20)
                await frame.wait_for_timeout(400)
                if descripcion in await _read_descripcion(frame):
                    logger.info(f"Descripción llenada mediante estrategia (d) {sel}")
                    return
        except Exception:
            continue

    await frame.wait_for_timeout(250)

    # (e) Clipboard: copiar y pegar con atajos de teclado
    targets = [root]
    if await x57.count() > 0:
        targets.append(x57)
    for target in targets:
        try:
            await target.click(timeout=4_000, force=True)
            await frame.wait_for_timeout(300)
            await frame.evaluate("t => navigator.clipboard.writeText(t)", descripcion)
            await frame.wait_for_timeout(300)
            for combo in (("Control+a", "Control+v"), ("Meta+a", "Meta+v")):
                try:
                    await target.press(combo[0])
                    await target.press(combo[1])
                    await frame.wait_for_timeout(300)
                    if descripcion in await _read_descripcion(frame):
                        logger.info("Descripción llenada mediante estrategia (e) clipboard")
                        return
                except Exception:
                    continue
        except Exception:
            continue

    # (f) Inyección por Javascript y disparo de eventos input/change
    for sel in ("#X57", "#X57View"):
        try:
            loc = frame.locator(sel).first
            if await loc.count() == 0:
                continue
            tag = await loc.evaluate("el => el.tagName")
            if tag in ("INPUT", "TEXTAREA"):
                ok = await loc.evaluate(
                    """(el, t) => {
                        el.value = t;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        return el.value;
                    }""",
                    descripcion,
                )
                await frame.wait_for_timeout(300)
                if descripcion in (ok or "") or descripcion in await _read_descripcion(frame):
                    logger.info(f"Descripción llenada mediante estrategia (f) JS value en {sel}")
                    return
            elif tag in ("DIV", "SPAN", "P"):
                ok = await loc.evaluate(
                    """(el, t) => {
                        el.focus();
                        el.innerHTML = '<p>' + t + '</p>';
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        return el.innerText || el.innerHTML;
                    }""",
                    descripcion,
                )
                await frame.wait_for_timeout(300)
                if descripcion in (ok or "") or descripcion in await _read_descripcion(frame):
                    logger.info(f"Descripción llenada mediante estrategia (f) JS innerHTML en {sel}")
                    return
        except Exception:
            continue

    current_val = await _read_descripcion(frame)
    if current_val:
        logger.warning(f"Descripción asignada con valor parcial/alternativo: {current_val!r}")
        return

    raise RuntimeError("No se pudo llenar el campo Descripción (#X57View / #X57)")


# ==============================================================================
# ESTRATEGIAS RESILIENTES: GRUPO DE ASIGNACIÓN (POPUP MODAL)
# ==============================================================================
async def _read_grupo(frame: Frame) -> str:
    """Lee el valor actual de Grupo de asignación en el formulario."""
    for role in ("combobox", "textbox"):
        try:
            locs = frame.get_by_role(role, name=re.compile("Grupo de asignación", re.I))
            count = await locs.count()
            for i in range(count):
                el = locs.nth(i)
                try:
                    v = await el.evaluate(
                        """el => {
                            if (el.tagName === 'SELECT') {
                                const opt = el.options[el.selectedIndex];
                                return opt ? (opt.text || opt.value || '') : '';
                            }
                            if ('value' in el) return el.value || '';
                            return (el.innerText || el.textContent || '').trim();
                        }"""
                    )
                    if v:
                        return v
                except Exception:
                    continue
        except Exception:
            continue
    return ""


async def _find_search_field(target: Any) -> Any:
    """Busca el campo de texto o searchbox dentro del popup modal."""
    try:
        for el in await target.get_by_role("searchbox").all():
            if await el.is_visible():
                return el
    except Exception:
        pass
    for sel in ("input[type='search']", "input[type='text']"):
        try:
            for el in await target.locator(sel).all():
                if await el.is_visible():
                    return el
        except Exception:
            continue
    try:
        for el in await target.locator("input").all():
            try:
                if not await el.is_visible():
                    continue
            except Exception:
                continue
            for attr in ("name", "id", "placeholder", "title"):
                try:
                    v = await el.get_attribute(attr) or ""
                except Exception:
                    v = ""
                if _SEARCH_INPUT_RE.search(v):
                    return el
    except Exception:
        pass
    try:
        for el in await target.get_by_role("textbox").all():
            if await el.is_visible():
                return el
    except Exception:
        pass
    try:
        for el in await target.locator("input").all():
            if await el.is_visible():
                return el
    except Exception:
        pass
    return None


async def _find_search_button(target: Any) -> Any:
    """Busca el botón de buscar/filtrar en el popup modal."""
    try:
        for b in await target.get_by_role("button").all():
            try:
                if not await b.is_visible():
                    continue
            except Exception:
                continue
            try:
                aria = await b.get_attribute("aria-label") or ""
                inner = await b.inner_text() or ""
                name = (aria or inner).strip()
            except Exception:
                continue
            if name and _SEARCH_BUTTON_RE.search(name):
                return b
    except Exception:
        pass
    return None


async def _check_grupo_filled(frame: Frame, grupo: str) -> bool:
    """Verifica si el grupo esperado ya está presente en el input #X89 o en combobox."""
    target_match = grupo.lower()
    try:
        v = await frame.locator("#X89").input_value()
        if v and target_match in v.lower():
            return True
    except Exception:
        pass
    try:
        v = await _read_grupo(frame)
        if v and target_match in v.lower():
            return True
    except Exception:
        pass
    return False


async def _click_grupo_result(target: Any, value: str) -> bool:
    """Selecciona la fila/elemento correspondiente al grupo dentro del modal."""
    pat = re.compile(re.escape(value), re.I)
    try:
        for el in await target.get_by_text(pat).all():
            try:
                if not await el.is_visible():
                    continue
            except Exception:
                continue
            await el.scroll_into_view_if_needed()
            await el.click(timeout=4_000, force=True)
            return True
    except Exception:
        pass

    for role in ("option", "link", "treeitem", "listitem", "row", "gridcell", "cell"):
        try:
            loc = target.get_by_role(role, name=pat).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.scroll_into_view_if_needed()
                await loc.click(timeout=4_000, force=True)
                return True
        except Exception:
            continue

    try:
        loc = target.get_by_text(pat).first
        if await loc.count() > 0:
            await loc.scroll_into_view_if_needed()
            await loc.dblclick(timeout=4_000, force=True)
            return True
    except Exception:
        pass

    try:
        for tr in await target.locator("tr").all():
            try:
                inner = await tr.inner_text() or ""
                if value.lower() not in inner.lower():
                    continue
            except Exception:
                continue
            try:
                if not await tr.is_visible():
                    continue
            except Exception:
                continue
            await tr.scroll_into_view_if_needed()
            await tr.click(timeout=4_000, force=True)
            return True
    except Exception:
        pass

    return False


async def _click_grupo_accept(target: Any) -> None:
    """Intenta hacer clic en un botón de aceptar / seleccionar dentro del modal."""
    try:
        for b in await target.get_by_role("button").all():
            try:
                if not await b.is_visible():
                    continue
            except Exception:
                continue
            try:
                name = (await b.get_attribute("aria-label") or await b.inner_text() or "").strip()
            except Exception:
                continue
            if name and _SEARCH_BUTTON_RE.search(name):
                try:
                    await b.click(timeout=4_000, force=True)
                    return
                except Exception:
                    continue
    except Exception:
        pass


async def _click_grupo_fill_button(frame: Frame) -> None:
    """Hace clic en el botón/icono que despliega el modal de búsqueda de Grupo."""
    try:
        img = frame.get_by_role("img", name="Rellenar campo Grupo de asignación").first
        if await img.count() > 0:
            await img.wait_for(timeout=5_000)
            await img.click(timeout=5_000, force=True)
            return
    except Exception:
        pass

    for sel in (
        "img[alt*='Rellenar']",
        "img[title*='Rellenar']",
        "img[alt*='Grupo de asignación']",
        "img[title*='Grupo de asignación']",
        "img[alt*='Grupo de asignacion']",
        "img[title*='Grupo de asignacion']",
    ):
        try:
            loc = frame.locator(sel).first
            if await loc.count() > 0:
                await loc.click(timeout=5_000, force=True)
                return
        except Exception:
            continue

    for name in ("Buscar campo Grupo de asignación", "Buscar campo Grupo de asignacion"):
        try:
            btn = frame.get_by_role("button", name=name).first
            if await btn.count() > 0:
                await btn.click(timeout=5_000, force=True)
                return
        except Exception:
            continue


async def _detect_popup(
    context: BrowserContext,
    frame: Frame,
    pages_before: set,
    frames_before: set,
    grupo: str,
    timeout: float = 12.0
) -> Tuple[Optional[Any], str]:
    """Detecta la apertura de una nueva ventana, nuevo frame u overlay para el modal de grupo."""
    deadline = time.time() + timeout
    pat = re.compile(re.escape(grupo), re.I)
    while time.time() < deadline:
        for p in context.pages:
            if p not in pages_before:
                return p, "página nueva"
        for p in context.pages:
            for f in p.frames:
                if f not in frames_before:
                    return f, "frame nuevo"
        for p in context.pages:
            for f in p.frames:
                if f is frame:
                    continue
                try:
                    if await f.get_by_role("searchbox").count() > 0:
                        return f, "overlay (searchbox)"
                except Exception:
                    continue
        for p in context.pages:
            for f in p.frames:
                if f is frame:
                    continue
                try:
                    if await f.get_by_text(pat).count() > 0:
                        return f, f"overlay (texto '{grupo}')"
                except Exception:
                    continue
        await asyncio.sleep(0.5)
    return None, ""


async def fill_grupo(frame: Frame, context: BrowserContext, grupo: str) -> None:
    """Ejecuta el flujo completo de selección de Grupo de asignación mediante modal."""
    pages_before = set(context.pages)
    frames_before = {f for p in context.pages for f in p.frames}

    await _click_grupo_fill_button(frame)

    popup, popup_kind = await _detect_popup(
        context, frame, pages_before, frames_before, grupo=grupo, timeout=12.0
    )
    if popup is None:
        raise RuntimeError("No se detectó el popup modal de Grupo de asignación")

    logger.info(f"Modal de Grupo detectado ({popup_kind})")

    # Búsqueda en el modal
    search = await _find_search_field(popup)
    if search is not None:
        try:
            await search.fill(grupo)
            await popup.wait_for_timeout(500)
            try:
                await search.press("Enter")
            except Exception:
                pass
        except Exception:
            pass

    btn = await _find_search_button(popup)
    if btn is not None:
        try:
            await btn.click(timeout=4_000, force=True)
        except Exception:
            pass

    await popup.wait_for_timeout(2500)

    # Selección del resultado
    clickeado = await _click_grupo_result(popup, grupo)
    await popup.wait_for_timeout(800)

    if not await _check_grupo_filled(frame, grupo):
        try:
            await _click_grupo_accept(popup)
            await popup.wait_for_timeout(800)
        except Exception:
            pass

    if not await _check_grupo_filled(frame, grupo) and not clickeado:
        try:
            for el in await popup.get_by_text(re.compile(re.escape(grupo), re.I)).all():
                try:
                    if not await el.is_visible():
                        continue
                except Exception:
                    continue
                await el.scroll_into_view_if_needed()
                await el.dblclick(timeout=4_000, force=True)
                break
        except Exception:
            pass
        await popup.wait_for_timeout(800)

    # Cierre tolerante del popup modal
    try:
        if _is_page(popup):
            await popup.close()
        else:
            await popup.page.keyboard.press("Escape")
    except Exception:
        pass

    # Verificación final
    if await _check_grupo_filled(frame, grupo):
        return

    valor = await _read_grupo(frame)
    try:
        x89_val = await frame.locator("#X89").input_value()
    except Exception:
        x89_val = ""

    if grupo.lower() in (x89_val or "").lower() or grupo.lower() in (valor or "").lower():
        return

    raise RuntimeError(
        f"No se pudo seleccionar el Grupo de asignación '{grupo}' "
        f"(valor #X89: {x89_val!r}, combobox: {valor!r})"
    )


# ==============================================================================
# GUARDADO Y CAPTURA DE ID DE TICKET
# ==============================================================================
async def click_guardar(page: Page, context: BrowserContext) -> None:
    """Busca y presiona el botón 'Guardar (Alt+F1)' en la página o en cualquiera de sus frames."""
    candidates = [page]
    for p in context.pages:
        for frame in p.frames:
            if frame not in candidates:
                candidates.append(frame)

    # (a) Página principal
    try:
        btn = page.get_by_role("button", name="Guardar (Alt+F1)").first
        await btn.wait_for(timeout=5_000)
        await btn.scroll_into_view_if_needed()
        await btn.click(timeout=5_000, force=True)
        return
    except Exception:
        pass

    # (b) Frames hijos
    for target in candidates[1:]:
        try:
            btn = target.get_by_role("button", name="Guardar (Alt+F1)").first
            if await btn.count() == 0:
                continue
            await btn.scroll_into_view_if_needed()
            await btn.click(timeout=5_000, force=True)
            return
        except Exception:
            continue

    # (c) Fallback por texto "Guardar"
    for target in candidates:
        try:
            loc = target.get_by_text(re.compile(r"^Guardar\b", re.I)).first
            if await loc.count() == 0:
                continue
            await loc.scroll_into_view_if_needed()
            await loc.click(timeout=5_000, force=True)
            return
        except Exception:
            continue

    await page.wait_for_timeout(1000)
    raise RuntimeError("No se encontró el botón 'Guardar (Alt+F1)' en la página ni en ningún frame")


async def get_ticket_id(context: BrowserContext, timeout_ms: int = 30_000) -> str:
    """
    Monitorea los frames y páginas para capturar el valor generado en 'ID de la interacción:'.
    """
    deadline = time.time() + (timeout_ms / 1000.0)
    last_value = ""
    while time.time() < deadline:
        for p in list(context.pages):
            try:
                for frame in p.frames:
                    try:
                        field = frame.get_by_role("textbox", name="ID de la interacción:")
                        if await field.count() == 0:
                            continue
                        value = await field.first.input_value()
                    except Exception:
                        continue
                    if value and value.strip():
                        ticket_val = value.strip()
                        copy_id_to_clipboard(ticket_val)
                        return ticket_val
            except Exception:
                continue
        await asyncio.sleep(1)

    if last_value and last_value.strip():
        copy_id_to_clipboard(last_value.strip())
        return last_value.strip()

    raise TimeoutError(f"No se capturó el ID de la interacción dentro del timeout ({timeout_ms / 1000:.0f}s)")


# ==============================================================================
# GENERADOR ASÍNCRONO PARA SERVER-SENT EVENTS (SSE)
# ==============================================================================
async def stream_ticket_creation(params: Dict[str, Any]) -> AsyncGenerator[str, None]:
    """
    Generador asíncrono para Server-Sent Events (SSE).
    Ejecuta el flujo completo de creación de ticket en Service Manager emitiendo logs
    y eventos de estado en tiempo real.
    """
    # Extracción de parámetros con valores por defecto
    url = params.get("url") or params.get("portal_url") or PORTAL_URL
    username = params.get("username") or params.get("portal_user") or PORTAL_USER
    password = params.get("password") or params.get("portal_pass") or PORTAL_PASS
    headless = params.get("headless", True)

    contacto = params.get("contacto") or DEFAULT_CONTACTO
    titulo = params.get("titulo") or DEFAULT_TITULO
    descripcion = params.get("descripcion") or DEFAULT_DESCRIPCION
    area = params.get("area") or DEFAULT_AREA
    subarea = params.get("subarea") or DEFAULT_SUBAREA
    detalle = params.get("detalle") or DEFAULT_DETALLE
    grupo = params.get("grupo") or DEFAULT_GRUPO
    impacto = params.get("impacto") or DEFAULT_IMPACTO
    urgencia = params.get("urgencia") or DEFAULT_URGENCIA

    playwright: Optional[Playwright] = None
    browser: Optional[Browser] = None
    context: Optional[BrowserContext] = None
    page: Optional[Page] = None

    try:
        yield format_sse({
            "type": "log",
            "message": "Iniciando proceso de automatización de ticket...",
            "level": "info"
        })

        yield format_sse({
            "type": "log",
            "message": f"Iniciando navegador Chromium (headless={headless})...",
            "level": "info"
        })

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ]
        )

        context = await browser.new_context()

        # Manejador automático de diálogos JS
        async def _handle_dialog(dialog: Dialog):
            try:
                logger.info(f"Diálogo JS interceptado: {dialog.message}")
                await dialog.accept()
            except Exception as exc:
                logger.debug(f"Error al aceptar diálogo JS: {exc}")

        context.on("dialog", lambda d: asyncio.create_task(_handle_dialog(d)))

        page = await context.new_page()

        yield format_sse({
            "type": "log",
            "message": f"Conectando a portal Service Manager: {url}...",
            "level": "step"
        })

        await page.goto(url, timeout=TIMEOUT, wait_until="domcontentloaded")

        yield format_sse({
            "type": "log",
            "message": f"Autenticando usuario '{username}'...",
            "level": "step"
        })

        await page.get_by_role("textbox", name="Nombre de usuario").fill(username)
        await page.get_by_role("textbox", name="Contraseña").fill(password)
        await page.get_by_role("button", name="Iniciar sesión").click()

        yield format_sse({
            "type": "log",
            "message": "Navegando a 'Centro de Servicios' > 'Crear nueva interacción'...",
            "level": "step"
        })

        await page.get_by_text("Centro de Servicios").click(timeout=TIMEOUT)
        await page.get_by_role("treeitem", name="Crear nueva interacción").click(timeout=TIMEOUT)

        yield format_sse({
            "type": "log",
            "message": "Abriendo sección 'Servicios Internos'...",
            "level": "step"
        })

        frame = await click_servicios_internos(context, page)

        # Llenado de formulario
        yield format_sse({
            "type": "log",
            "message": f"Ingresando Contacto: '{contacto}'...",
            "level": "step"
        })
        try:
            await frame.get_by_role("textbox", name="Contacto:", exact=True).fill(contacto)
            await frame.get_by_role("img", name="Rellenar campo Contacto").click(timeout=10_000)
            await frame.wait_for_timeout(1500)
        except Exception as exc:
            yield format_sse({
                "type": "log",
                "message": f"Aviso al completar contacto: {exc}",
                "level": "info"
            })

        yield format_sse({
            "type": "log",
            "message": "Estableciendo Estado: 'Abierto'...",
            "level": "step"
        })
        try:
            await frame.locator("#X23Border a").click()
            await frame.get_by_role("option", name="Abierto").click()
        except Exception as exc:
            yield format_sse({
                "type": "log",
                "message": f"Aviso al seleccionar estado: {exc}",
                "level": "info"
            })

        yield format_sse({
            "type": "log",
            "message": f"Ingresando Título: '{titulo}'...",
            "level": "step"
        })
        await frame.get_by_role("textbox", name="Título:").fill(titulo)

        yield format_sse({
            "type": "log",
            "message": "Ingresando Descripción (aplicando estrategias resilientes)...",
            "level": "step"
        })
        await fill_descripcion(frame, descripcion)

        yield format_sse({
            "type": "log",
            "message": f"Configurando Clasificación: Área='{area}', Sub-área='{subarea}', Detalle='{detalle}'...",
            "level": "step"
        })
        await fill_by_label(frame, "^Área", area)
        await fill_by_label(frame, "^Sub-área", subarea)
        await fill_by_label(frame, "^Detalle", detalle)

        yield format_sse({
            "type": "log",
            "message": f"Asignando Grupo mediante modal: '{grupo}'...",
            "level": "step"
        })
        await fill_grupo(frame, context, grupo)

        yield format_sse({
            "type": "log",
            "message": f"Configurando Impacto='{impacto}' y Urgencia='{urgencia}'...",
            "level": "step"
        })
        try:
            await frame.locator("#X71ButtonDiv > .image-link").click()
            await frame.get_by_role("option", name=impacto).click()
        except Exception:
            pass

        try:
            await frame.locator("#X78ButtonDiv > .image-link").click()
            await frame.get_by_role("option", name=urgencia).click()
        except Exception:
            pass

        yield format_sse({
            "type": "log",
            "message": "Formulario completado. Guardando interacción (Guardar Alt+F1)...",
            "level": "step"
        })
        await click_guardar(page, context)

        yield format_sse({
            "type": "log",
            "message": "Esperando generación y captura de ID de Ticket...",
            "level": "step"
        })

        ticket_id = await get_ticket_id(context, timeout_ms=35_000)

        yield format_sse({
            "type": "log",
            "message": f"¡Ticket generado exitosamente! ID: {ticket_id}",
            "level": "success"
        })

        yield format_sse({
            "type": "complete",
            "status": "success",
            "ticket_id": ticket_id,
            "message": "Ticket generado con éxito"
        })

    except Exception as exc:
        err_msg = str(exc)
        logger.exception("Error durante la automatización de ticket")
        yield format_sse({
            "type": "log",
            "message": f"Error en la automatización: {err_msg}",
            "level": "error"
        })
        yield format_sse({
            "type": "error",
            "message": err_msg
        })

    finally:
        # Limpieza estricta de recursos Playwright
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright:
            try:
                await playwright.stop()
            except Exception:
                pass
