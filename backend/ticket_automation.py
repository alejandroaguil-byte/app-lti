"""
Módulo de automatización para la creación de tickets (interacciones) y peticiones relacionadas
en Micro Focus Service Manager (HPSM).
Provee ejecución desatendida mediante Playwright Async, estrategias de resiliencia avanzadas,
cierre de sesión seguro y emisión de eventos en tiempo real (Server-Sent Events - SSE).
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from typing import AsyncGenerator, Dict, Any, Optional, Tuple, Callable

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
DEFAULT_TITULO = ""
DEFAULT_DESCRIPCION = ""
DEFAULT_AREA = "Proyectos"
DEFAULT_SUBAREA = "Apoyo habilitacion cliente"
DEFAULT_DETALLE = "Apoyo habilitacion cliente"
DEFAULT_GRUPO = "Lideres Tecnicos"
DEFAULT_IMPACTO = "3 - Menor (Existen WorkAround)"
DEFAULT_URGENCIA = "3 - Media (Resolución a mediano plazo)"
DEFAULT_USUARIO_PETICION = "Alejandro.Aguilar"

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


def _frame_label(target: Any) -> str:
    """Genera una etiqueta descriptiva para un Frame o Page."""
    name = getattr(target, "name", None)
    return name if name else getattr(target, "url", target.__class__.__name__)


async def wait_context(context: BrowserContext, timeout_ms: int) -> None:
    """Pausa la ejecución en el contexto activo usando el temporizador del navegador."""
    pages = list(context.pages)
    if pages:
        await pages[0].wait_for_timeout(timeout_ms)
    else:
        await asyncio.sleep(timeout_ms / 1000.0)


# ==============================================================================
# FASE 1: AUTENTICACIÓN DEFENSIVA CONTRA ROBO DE FOCO
# ==============================================================================
async def set_login_value(locator: Any, value: str, label: str, timeout_ms: int = DEFAULT_TIMEOUT) -> None:
    """
    Fija el valor de un campo de login mediante asignación directa en JS y despacho de eventos.
    Previene que el portal robe el foco y concatene la contraseña dentro del campo de usuario.
    """
    await locator.wait_for(state="visible", timeout=timeout_ms)
    await locator.scroll_into_view_if_needed(timeout=timeout_ms)
    await locator.evaluate(
        """(el, value) => {
            el.focus();
            el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.blur();
        }""",
        value,
    )
    current_value = await locator.input_value(timeout=timeout_ms)
    if current_value != value:
        raise RuntimeError(f"No se pudo fijar {label}: esperado {value!r}, obtenido {current_value!r}")


async def fill_login_credentials(page: Page, username: str, password: str, timeout_ms: int = DEFAULT_TIMEOUT) -> None:
    """Llena las credenciales con validación y doble chequeo contra foco desfasado."""
    user_field = page.get_by_role("textbox", name="Nombre de usuario", exact=True).first
    if await user_field.count() == 0:
        user_field = page.locator("input[name*='user' i], input[id*='user' i], #username").first

    password_field = page.get_by_role("textbox", name="Contraseña", exact=True).first
    if await password_field.count() == 0:
        password_field = page.locator("input[type='password'], input[name*='pass' i]").first

    await set_login_value(user_field, username, "usuario", timeout_ms=timeout_ms)
    await set_login_value(password_field, password, "contraseña", timeout_ms=timeout_ms)

    # Defensa explícita contra concatenación tardía por robo de foco
    user_value = await user_field.input_value(timeout=timeout_ms)
    password_value = await password_field.input_value(timeout=timeout_ms)
    if user_value != username or password_value != password:
        logger.warning("Detección de foco desfasado en login; reaplicando valores...")
        await set_login_value(user_field, username, "usuario", timeout_ms=timeout_ms)
        await set_login_value(password_field, password, "contraseña", timeout_ms=timeout_ms)


# ==============================================================================
# FASE 2: LOCALIZACIÓN Y NAVEGACIÓN EN FORMULARIO DE INTERACCIÓN
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
# FASE 2.1: ESTRATEGIAS RESILIENTES EN DESCRIPCIÓN (#X57 / #X57View)
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
    Llena el campo de descripción ejecutando en cascada las 7 estrategias resilientes:
    (0) Fill en control real oculto #X57
    (a) Clic + fill directo en #X57View
    (b) Clic + fill en descendientes [contenteditable]
    (c) Clic + fill en textarea/input descendiente
    (d) press_sequentially simulando teclado físico
    (e) Inyección en portapapeles y atajos de pegado
    (f) Asignación directa DOM vía JavaScript
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
# FASE 2.2: ESTRATEGIAS RESILIENTES EN GRUPO DE ASIGNACIÓN (POPUP MODAL)
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
# FASE 3: GUARDADO DE INTERACCIÓN Y CAPTURA DE ID (SD)
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
                        field = frame.get_by_role("textbox", name=re.compile(r"ID de la interacci[oó]n", re.I))
                        if await field.count() == 0:
                            field = frame.locator(
                                "input[aria-label*='ID de la interacci' i], "
                                "input[title*='ID de la interacci' i], "
                                "input[aria-label*='interacci' i], "
                                "#X3"
                            ).first
                            if await field.count() == 0:
                                continue
                        value = await field.first.input_value()
                        if value:
                            last_value = value.strip()
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
# FASE 4: VINCULACIÓN DE PETICIÓN RELACIONADA
# ==============================================================================
async def find_registros_relacionados_frame(context: BrowserContext, timeout_ms: int = 20_000) -> Tuple[Frame, Any]:
    """Busca en todos los frames del contexto la pestaña 'Registros relacionados'."""
    deadline = time.time() + (timeout_ms / 1000.0)
    tab_re = re.compile(r"Registros relacionados", re.I)
    while time.time() < deadline:
        for p in list(context.pages):
            for frame in p.frames:
                try:
                    tab = frame.get_by_role("tab", name=tab_re).first
                    if await tab.count() > 0:
                        return frame, tab
                except Exception:
                    continue
        await asyncio.sleep(0.5)
    raise TimeoutError("No se encontró la pestaña 'Registros relacionados' en ningún frame")


async def click_button_in_context(context: BrowserContext, name_regex: re.Pattern, error_label: str) -> None:
    """Hace clic en un botón en cualquier página o frame del contexto usando accesibilidad y texto."""
    last_error = None
    for p in list(context.pages):
        targets = [("page", p)] + [(f"frame {f.name!r}", f) for f in p.frames]
        for label, target in targets:
            try:
                buttons = await target.get_by_role("button", name=name_regex).all()
            except Exception as exc:
                last_error = exc
                continue
            for btn in buttons:
                try:
                    if not await btn.is_visible():
                        continue
                except Exception:
                    pass
                try:
                    await btn.scroll_into_view_if_needed(timeout=5_000)
                    await btn.click(timeout=10_000, force=True)
                    logger.info(f"Clic exitoso en botón '{error_label}' en {label}")
                    return
                except Exception as exc:
                    last_error = exc

    # Fallback para botones ExtJS cuyo nombre accesible varía
    for p in list(context.pages):
        targets = [("page", p)] + [(f"frame {f.name!r}", f) for f in p.frames]
        for label, target in targets:
            try:
                buttons = await target.get_by_role("button").all()
            except Exception as exc:
                last_error = exc
                continue
            for btn in buttons:
                try:
                    text = ""
                    try:
                        text = (await btn.inner_text() or "").strip()
                    except Exception:
                        pass
                    data = " ".join([
                        text,
                        await btn.get_attribute("aria-label") or "",
                        await btn.get_attribute("title") or "",
                    ])
                    if not name_regex.search(data):
                        continue
                    if not await btn.is_visible():
                        continue
                    await btn.scroll_into_view_if_needed(timeout=5_000)
                    await btn.click(timeout=10_000, force=True)
                    logger.info(f"Clic exitoso por fallback en '{error_label}' en {label}")
                    return
                except Exception as exc:
                    last_error = exc

    raise TimeoutError(f"No se encontró o no se pudo hacer clic en '{error_label}': {last_error}")


async def click_expandir_lista_registros(frame: Frame) -> None:
    """Expande la lista desplegable en la sección de Registros Relacionados."""
    strategies = [
        ("img role exact", lambda: frame.get_by_role("img", name="Expandir lista").first),
        ("button role exact", lambda: frame.get_by_role("button", name="Expandir lista").first),
        ("img alt", lambda: frame.locator('img[alt="Expandir lista"]').first),
        ("img title", lambda: frame.locator('img[title="Expandir lista"]').first),
        ("any title/alt expandir", lambda: frame.locator('img[alt*="Expandir"], img[title*="Expandir"], button[title*="Expandir"]').first),
    ]
    last_error = None
    for label, make_loc in strategies:
        try:
            loc = make_loc()
            if await loc.count() == 0:
                continue
            try:
                await loc.scroll_into_view_if_needed(timeout=2_000)
            except Exception:
                pass
            await loc.click(timeout=5_000, force=True)
            logger.info(f"Expandir lista exitoso con estrategia '{label}'")
            return
        except Exception as exc:
            last_error = exc

    # Fallback ExtJS vía JavaScript
    try:
        clicked = await frame.evaluate(
            """() => {
                const candidates = Array.from(document.querySelectorAll('img,button,a,div,span'))
                    .filter(el => /Expandir lista/i.test(
                        [el.getAttribute('alt'), el.getAttribute('title'), el.getAttribute('aria-label'), el.textContent]
                            .filter(Boolean).join(' ')
                    ));
                for (const el of candidates) {
                    const target = el.closest('a,button,[role="button"],.image-link,.x-form-trigger,.x-btn,.x-btn-text') || el;
                    try {
                        target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                        target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                        target.click();
                        return { ok: true, id: el.id || target.id || '', tag: el.tagName, targetTag: target.tagName };
                    } catch (e) {}
                }
                return { ok: false };
            }"""
        )
        if clicked and clicked.get("ok"):
            await frame.wait_for_timeout(800)
            logger.info(f"Expandir lista exitoso con JS fallback: {clicked}")
            return
    except Exception as exc:
        last_error = exc

    raise TimeoutError(f"No se pudo hacer clic en 'Expandir lista': {last_error}")


async def click_vincular_nuevo_registro(context: BrowserContext) -> None:
    """Hace clic en el control 'Vincular nuevo registro'."""
    await wait_context(context, 1500)
    pat = re.compile(r"Vincular nuevo registro", re.I)
    last_error = None
    try:
        await click_button_in_context(context, pat, "Vincular nuevo registro")
        return
    except Exception as exc:
        last_error = exc

    for p in list(context.pages):
        targets = [("page", p)] + [(f"frame {f.name!r}", f) for f in p.frames]
        for label, target in targets:
            for role in ("link", "img"):
                try:
                    els = await target.get_by_role(role, name=pat).all()
                except Exception as exc:
                    last_error = exc
                    continue
                for el in els:
                    try:
                        if not await el.is_visible():
                            continue
                        await el.scroll_into_view_if_needed(timeout=5_000)
                        await el.click(timeout=10_000, force=True)
                        logger.info(f"Vincular nuevo registro exitoso en {label} role={role}")
                        return
                    except Exception as exc:
                        last_error = exc

            try:
                clicked = await target.evaluate(
                    """() => {
                        const pat = /Vincular nuevo registro/i;
                        const els = Array.from(document.querySelectorAll('button,a,img,span,div'));
                        for (const el of els) {
                            const data = [el.textContent, el.getAttribute('aria-label'), el.getAttribute('title'), el.getAttribute('alt')]
                                .filter(Boolean).join(' ');
                            if (!pat.test(data)) continue;
                            const target = el.closest('a,button,[role="button"],.x-btn,.x-btn-text,.image-link') || el;
                            target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                            target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                            target.click();
                            return { ok: true, tag: el.tagName, id: el.id || '', targetTag: target.tagName, targetId: target.id || '' };
                        }
                        return { ok: false };
                    }"""
                )
                if clicked and clicked.get("ok"):
                    logger.info(f"Vincular nuevo registro exitoso con JS fallback en {label}")
                    await wait_context(context, 1000)
                    return
            except Exception as exc:
                last_error = exc

    raise TimeoutError(f"No se pudo hacer clic en 'Vincular nuevo registro': {last_error}")


async def click_alejandro_aguilar_option(context: BrowserContext, user_target: str = DEFAULT_USUARIO_PETICION) -> None:
    """Selecciona el usuario responsable (Alejandro.Aguilar) en el formulario de petición."""
    pat = re.compile(re.escape(user_target), re.I)
    last_error = None
    for p in list(context.pages):
        targets = [("page", p)] + [(f"frame {f.name!r}", f) for f in p.frames]
        for label, target in targets:
            for role in ("option", "listitem", "row", "cell", "gridcell"):
                try:
                    els = await target.get_by_role(role, name=pat).all()
                except Exception as exc:
                    last_error = exc
                    continue
                for el in els:
                    try:
                        if not await el.is_visible():
                            continue
                        await el.scroll_into_view_if_needed(timeout=5_000)
                        await el.click(timeout=10_000, force=True)
                        logger.info(f"Usuario {user_target} seleccionado en {label} role={role}")
                        return
                    except Exception as exc:
                        last_error = exc

            try:
                els = await target.get_by_text(pat).all()
            except Exception as exc:
                last_error = exc
                continue
            for el in els:
                try:
                    if not await el.is_visible():
                        continue
                    await el.scroll_into_view_if_needed(timeout=5_000)
                    await el.click(timeout=10_000, force=True)
                    logger.info(f"Usuario {user_target} seleccionado por texto en {label}")
                    return
                except Exception as exc:
                    last_error = exc

            # Fallback ExtJS DOM y asignación directa a #X59
            try:
                result = await target.evaluate(
                    """(targetUser) => {
                        const pat = new RegExp(targetUser.replace('.', '[.]'), 'i');
                        const els = Array.from(document.querySelectorAll('div,span,td,tr,li,a'));
                        for (const el of els) {
                            if (!pat.test(el.textContent || '')) continue;
                            const target = el.closest('[role="option"],li,tr,td,a,.x-combo-list-item,.x-boundlist-item,.x-grid3-row,.x-grid-row') || el;
                            target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                            target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                            target.click();
                            return { ok: true, mode: 'dom-click', tag: el.tagName, targetTag: target.tagName, text: (el.textContent || '').trim().slice(0, 120) };
                        }
                        const field = document.querySelector('#X59, input[name="X59"], textarea[name="X59"]');
                        if (field) {
                            field.focus();
                            field.value = targetUser;
                            field.dispatchEvent(new Event('input', { bubbles: true }));
                            field.dispatchEvent(new Event('change', { bubbles: true }));
                            field.dispatchEvent(new Event('blur', { bubbles: true }));
                            return { ok: true, mode: 'set-X59', tag: field.tagName, id: field.id || '' };
                        }
                        return { ok: false };
                    }""",
                    user_target
                )
                if result and result.get("ok"):
                    logger.info(f"Usuario {user_target} seleccionado con JS fallback en {label}: {result}")
                    await wait_context(context, 800)
                    return
            except Exception as exc:
                last_error = exc

    raise TimeoutError(f"No se pudo seleccionar el usuario '{user_target}': {last_error}")


async def click_guardar_peticion(context: BrowserContext) -> None:
    """Presiona Guardar (Alt+F1) en el formulario de la Petición."""
    await click_button_in_context(
        context,
        re.compile(r"Guardar \(Alt\+F1\)", re.I),
        "Guardar (Alt+F1)",
    )


async def get_peticion_id(context: BrowserContext, timeout_ms: int = 30_000) -> str:
    """Monitorea los frames y páginas para capturar el valor generado en 'ID de la petición:'."""
    deadline = time.time() + (timeout_ms / 1000.0)
    last_value = ""
    while time.time() < deadline:
        for p in list(context.pages):
            try:
                for frame in p.frames:
                    try:
                        field = frame.get_by_role("textbox", name=re.compile(r"ID de la petici[oó]n", re.I))
                        if await field.count() == 0:
                            field = frame.locator(
                                "input[aria-label*='ID de la petici' i], "
                                "input[title*='ID de la petici' i], "
                                "input[aria-label*='petici' i], "
                                "#X3"
                            ).first
                            if await field.count() == 0:
                                continue
                        value = await field.first.input_value()
                        if value:
                            last_value = value.strip()
                    except Exception:
                        continue
                    if value and value.strip():
                        peticion_val = value.strip()
                        copy_id_to_clipboard(peticion_val)
                        return peticion_val
            except Exception:
                continue
        await asyncio.sleep(1)

    if last_value and last_value.strip():
        copy_id_to_clipboard(last_value.strip())
        return last_value.strip()

    raise TimeoutError(f"No se capturó el ID de la petición dentro del timeout ({timeout_ms / 1000:.0f}s)")


async def click_guardar_registro_y_salir(context: BrowserContext) -> None:
    """Hace clic en 'Guardar registro y salir ('."""
    await click_button_in_context(
        context,
        re.compile(r"Guardar registro y salir \(", re.I),
        "Guardar registro y salir (",
    )


async def click_guardar_y_salir_final(context: BrowserContext) -> None:
    """Hace clic en 'Guardar y salir' para cerrar el formulario intermedio."""
    await wait_context(context, 1500)
    await click_button_in_context(
        context,
        re.compile(r"Guardar y salir", re.I),
        "Guardar y salir",
    )
    await wait_context(context, 1500)


async def has_guardar_y_salir_visible(context: BrowserContext) -> bool:
    """Verifica si aún existe algún formulario abierto con botón 'Guardar y salir' visible."""
    pat = re.compile(r"Guardar y salir", re.I)
    for p in list(context.pages):
        targets = [("page", p)] + [(f"frame {f.name!r}", f) for f in p.frames]
        for _, target in targets:
            try:
                buttons = await target.get_by_role("button", name=pat).all()
                for btn in buttons:
                    try:
                        if await btn.is_visible():
                            return True
                    except Exception:
                        continue
            except Exception:
                continue
    return False


async def close_visible_final_forms(context: BrowserContext, max_clicks: int = 3) -> None:
    """Cierra en cascada formularios visibles antes de realizar logout."""
    for i in range(max_clicks):
        if not await has_guardar_y_salir_visible(context):
            return
        logger.info(f"Formulario abierto detectado; cerrando con 'Guardar y salir' ({i + 1}/{max_clicks})")
        try:
            await click_guardar_y_salir_final(context)
        except Exception:
            pass


# ==============================================================================
# FASE 5: LOGOUT LIMPIO Y CIERRE DE SESIÓN SEGURO
# ==============================================================================
async def click_text_action(context: BrowserContext, text_regex: re.Pattern, label: str) -> None:
    """Hace clic en una acción por texto o nombre accesible en el menú superior / diálogo."""
    last_error = None
    for p in list(context.pages):
        targets = [("page", p)] + [(f"frame {f.name!r}", f) for f in p.frames]
        for target_label, target in targets:
            for role in ("button", "menuitem", "link"):
                try:
                    els = await target.get_by_role(role, name=text_regex).all()
                except Exception as exc:
                    last_error = exc
                    continue
                for el in els:
                    try:
                        if not await el.is_visible():
                            continue
                        await el.click(timeout=10_000, force=True)
                        logger.info(f"Clic exitoso en {label} en {target_label} role={role}")
                        return
                    except Exception as exc:
                        last_error = exc

            try:
                els = await target.get_by_text(text_regex).all()
            except Exception as exc:
                last_error = exc
                continue
            for el in els:
                try:
                    if not await el.is_visible():
                        continue
                    await el.click(timeout=10_000, force=True)
                    logger.info(f"Clic exitoso en {label} por texto en {target_label}")
                    return
                except Exception as exc:
                    last_error = exc

            try:
                clicked = await target.evaluate(
                    """pattern => {
                        const re = new RegExp(pattern, 'i');
                        const els = Array.from(document.querySelectorAll('button,a,span,div,td,li'));
                        for (const el of els) {
                            const text = [el.textContent, el.getAttribute('aria-label'), el.getAttribute('title')]
                                .filter(Boolean).join(' ').trim();
                            if (!re.test(text)) continue;
                            const rect = el.getBoundingClientRect();
                            if (rect.width === 0 || rect.height === 0) continue;
                            const target = el.closest('button,a,[role="button"],[role="menuitem"],.x-menu-item,.x-btn,.x-btn-text') || el;
                            target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                            target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                            target.click();
                            return { ok: true, tag: el.tagName, text: text.slice(0, 120), targetTag: target.tagName, targetClass: target.className || '' };
                        }
                        return { ok: false };
                    }""",
                    text_regex.pattern,
                )
                if clicked and clicked.get("ok"):
                    logger.info(f"Clic exitoso en {label} con JS fallback en {target_label}: {clicked}")
                    return
            except Exception as exc:
                last_error = exc

    raise TimeoutError(f"No se pudo hacer clic en '{label}': {last_error}")


async def logout(page: Page, context: BrowserContext) -> None:
    """Ejecuta el cierre de sesión completo en Micro Focus Service Manager."""
    logger.info("Iniciando secuencia de Logout...")
    await close_visible_final_forms(context)

    await page.get_by_role("button", name="Info. del usuario").click(timeout=10_000, force=True)
    await wait_context(context, 1000)

    try:
        await click_text_action(context, re.compile(r"Cerrar sesi[oó]n|logout", re.I), "Cerrar sesión")
    except Exception:
        if await has_guardar_y_salir_visible(context):
            logger.warning("Formulario residual detectado durante logout; cerrando y reintentando...")
            await close_visible_final_forms(context)
            await page.get_by_role("button", name="Info. del usuario").click(timeout=10_000, force=True)
            await wait_context(context, 1000)
            await click_text_action(context, re.compile(r"Cerrar sesi[oó]n|logout", re.I), "Cerrar sesión")
        else:
            raise

    await wait_context(context, 1000)
    await click_text_action(context, re.compile(r"^S[ií]$", re.I), "Sí")
    logger.info("Logout completado exitosamente.")


# ==============================================================================
# SUBFLUJO: VINCULACIÓN DE PETICIÓN RELACIONADA ORQUESTADA
# ==============================================================================
async def vincular_peticion_relacionada(
    context: BrowserContext,
    emit_log_fn: Optional[Callable[[str, str, int], Any]] = None
) -> str:
    """
    Orquesta el flujo completo de vinculación de Petición Relacionada:
    1. Acceso a pestaña 'Registros relacionados'
    2. Expansión y selección de 'Peticiones relacionadas'
    3. Clic en 'Vincular nuevo registro'
    4. Selección del usuario 'Alejandro.Aguilar'
    5. Guardado de la petición y captura de su ID
    6. Cierre seguro de formularios
    """
    if emit_log_fn:
        await emit_log_fn("Buscando pestaña 'Registros relacionados'...", "step", 80)

    frame, tab = await find_registros_relacionados_frame(context)
    await tab.click(timeout=10_000, force=True)
    await frame.wait_for_timeout(1500)

    if emit_log_fn:
        await emit_log_fn("Expandiendo lista y seleccionando 'Peticiones relacionadas'...", "step", 82)

    frame, _ = await find_registros_relacionados_frame(context, timeout_ms=10_000)
    await click_expandir_lista_registros(frame)
    await frame.get_by_role("option", name="Peticiones relacionadas").click(timeout=10_000, force=True)
    await wait_context(context, 1000)

    if emit_log_fn:
        await emit_log_fn("Haciendo clic en 'Vincular nuevo registro'...", "step", 84)

    await click_vincular_nuevo_registro(context)

    if emit_log_fn:
        await emit_log_fn("Abriendo selector de usuario y asignando 'Alejandro.Aguilar'...", "step", 86)

    # Búsqueda tolerante del disparador de selección de usuario
    user_btn_clicked = False
    for p in list(context.pages):
        for f in p.frames:
            try:
                loc = f.locator("#X59ButtonDiv > .image-link, #X59ButtonDiv img, img[alt*='Rellenar campo Usuario'], img[title*='Rellenar campo Usuario']").first
                if await loc.count() > 0:
                    await loc.click(timeout=8_000, force=True)
                    user_btn_clicked = True
                    break
            except Exception:
                continue
        if user_btn_clicked:
            break

    if not user_btn_clicked:
        try:
            await frame.locator("#X59ButtonDiv > .image-link").click(timeout=8_000, force=True)
        except Exception:
            pass

    await wait_context(context, 1000)
    await click_alejandro_aguilar_option(context)

    if emit_log_fn:
        await emit_log_fn("Guardando formulario de la Petición...", "step", 88)

    await click_guardar_peticion(context)

    if emit_log_fn:
        await emit_log_fn("Capturando ID de la Petición generada...", "step", 89)

    peticion_id = await get_peticion_id(context)

    if emit_log_fn:
        await emit_log_fn(f"¡Petición generada exitosamente! ID: {peticion_id}", "success", 90)

    if emit_log_fn:
        await emit_log_fn("Cerrando formularios de registro y confirmación...", "step", 93)

    await click_guardar_registro_y_salir(context)
    await click_guardar_y_salir_final(context)

    return peticion_id


# ==============================================================================
# GENERADOR ASÍNCRONO PRINCIPAL PARA SERVER-SENT EVENTS (SSE)
# ==============================================================================
async def stream_ticket_creation(params: Dict[str, Any]) -> AsyncGenerator[str, None]:
    """
    Generador asíncrono para Server-Sent Events (SSE).
    Ejecuta el ciclo de vida completo de automatización en Service Manager:
    - Autenticación defensiva
    - Apertura de Interacción (SD) con 7 estrategias en descripción y modal search en grupo
    - Guardado y captura del ID de interacción (SD)
    - Vinculación de Petición Relacionada con asignación a Alejandro.Aguilar
    - Guardado y captura del ID de petición
    - Cierre en cascada de formularios y Logout seguro con confirmación
    """
    url = params.get("url") or params.get("portal_url") or PORTAL_URL
    username = params.get("username") or params.get("portal_user") or PORTAL_USER
    password = params.get("password") or params.get("portal_pass") or PORTAL_PASS
    
    headless_raw = params.get("headless", True)
    if isinstance(headless_raw, str):
        headless = headless_raw.lower() in ("true", "1", "yes")
    else:
        headless = bool(headless_raw)

    contacto = params.get("contacto") or DEFAULT_CONTACTO
    titulo = params.get("titulo") or DEFAULT_TITULO
    descripcion = params.get("descripcion") or DEFAULT_DESCRIPCION
    area = params.get("area") or DEFAULT_AREA
    subarea = params.get("subarea") or DEFAULT_SUBAREA
    detalle = params.get("detalle") or DEFAULT_DETALLE
    grupo = params.get("grupo") or DEFAULT_GRUPO
    impacto = params.get("impacto") or DEFAULT_IMPACTO
    urgencia = params.get("urgencia") or DEFAULT_URGENCIA
    usuario_peticion = params.get("usuario_peticion") or params.get("user_target") or DEFAULT_USUARIO_PETICION

    playwright: Optional[Playwright] = None
    browser: Optional[Browser] = None
    context: Optional[BrowserContext] = None
    page: Optional[Page] = None

    ticket_id: Optional[str] = None
    peticion_id: Optional[str] = None

    try:
        yield format_sse({
            "type": "log",
            "message": "Iniciando proceso de automatización de ticket y petición...",
            "level": "info",
            "progress": 5
        })

        yield format_sse({
            "type": "log",
            "message": f"Iniciando navegador Chromium (headless={headless})...",
            "level": "info",
            "progress": 12
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

        # Manejador automático de diálogos JS nativos tolerante a sync/async
        async def _handle_dialog(dialog: Any):
            try:
                msg = getattr(dialog, "message", "")
                logger.info(f"Diálogo JS interceptado: {msg}")
                if hasattr(dialog, "accept"):
                    res = dialog.accept()
                    if asyncio.iscoroutine(res):
                        await res
            except Exception as exc:
                logger.debug(f"Error al aceptar diálogo JS: {exc}")

        context.on("dialog", lambda d: asyncio.create_task(_handle_dialog(d)))

        page = await context.new_page()

        yield format_sse({
            "type": "log",
            "message": f"Conectando a portal Service Manager: {url}...",
            "level": "step",
            "progress": 22
        })

        await page.goto(url, timeout=TIMEOUT, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass

        yield format_sse({
            "type": "log",
            "message": f"Autenticando usuario '{username}' (modo defensivo contra robo de foco)...",
            "level": "step",
            "progress": 30
        })

        await fill_login_credentials(page, username, password, timeout_ms=TIMEOUT)
        await page.get_by_role("button", name="Iniciar sesión").click()

        yield format_sse({
            "type": "log",
            "message": "Navegando a 'Centro de Servicios' > 'Crear nueva interacción'...",
            "level": "step",
            "progress": 40
        })

        await page.get_by_text("Centro de Servicios").click(timeout=TIMEOUT)
        await page.get_by_role("treeitem", name="Crear nueva interacción").click(timeout=TIMEOUT)

        yield format_sse({
            "type": "log",
            "message": "Abriendo sección 'Servicios Internos'...",
            "level": "step",
            "progress": 45
        })

        frame = await click_servicios_internos(context, page)

        # Llenado de formulario de interacción
        yield format_sse({
            "type": "log",
            "message": f"Ingresando Contacto: '{contacto}'...",
            "level": "step",
            "progress": 48
        })
        try:
            await frame.get_by_role("textbox", name="Contacto:", exact=True).fill(contacto)
            await frame.get_by_role("img", name="Rellenar campo Contacto").click(timeout=10_000)
            await frame.wait_for_timeout(1500)
        except Exception as exc:
            yield format_sse({
                "type": "log",
                "message": f"Aviso al completar contacto: {exc}",
                "level": "info",
                "progress": 49
            })

        yield format_sse({
            "type": "log",
            "message": "Estableciendo Estado: 'Abierto'...",
            "level": "step",
            "progress": 50
        })
        try:
            await frame.locator("#X23Border a").click()
            await frame.get_by_role("option", name="Abierto").click()
        except Exception as exc:
            yield format_sse({
                "type": "log",
                "message": f"Aviso al seleccionar estado: {exc}",
                "level": "info",
                "progress": 51
            })

        yield format_sse({
            "type": "log",
            "message": f"Ingresando Título: '{titulo}'...",
            "level": "step",
            "progress": 52
        })
        await frame.get_by_role("textbox", name="Título:").fill(titulo)

        yield format_sse({
            "type": "log",
            "message": "Ingresando Descripción (aplicando cascada de 7 estrategias)...",
            "level": "step",
            "progress": 55
        })
        await fill_descripcion(frame, descripcion)

        yield format_sse({
            "type": "log",
            "message": f"Configurando Clasificación: Área='{area}', Sub-área='{subarea}', Detalle='{detalle}'...",
            "level": "step",
            "progress": 58
        })
        await fill_by_label(frame, "^Área", area)
        await fill_by_label(frame, "^Sub-área", subarea)
        await fill_by_label(frame, "^Detalle", detalle)

        yield format_sse({
            "type": "log",
            "message": f"Asignando Grupo mediante modal: '{grupo}'...",
            "level": "step",
            "progress": 60
        })
        await fill_grupo(frame, context, grupo)

        yield format_sse({
            "type": "log",
            "message": f"Configurando Impacto='{impacto}' y Urgencia='{urgencia}'...",
            "level": "step",
            "progress": 65
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
            "level": "step",
            "progress": 70
        })
        await click_guardar(page, context)

        yield format_sse({
            "type": "log",
            "message": "Esperando generación y captura de ID de Interacción (SD)...",
            "level": "step",
            "progress": 72
        })

        ticket_id = await get_ticket_id(context, timeout_ms=35_000)

        yield format_sse({
            "type": "log",
            "message": f"¡Interacción generada exitosamente! ID: {ticket_id}",
            "level": "success",
            "progress": 75
        })

        # FASE 4: Vinculación Directa de Petición Relacionada (Secuencial y Lineal)
        yield format_sse({"type": "log", "message": "Buscando pestaña 'Registros relacionados'...", "level": "step", "progress": 80})
        frame, tab = await find_registros_relacionados_frame(context)
        await tab.click(timeout=10_000, force=True)
        await frame.wait_for_timeout(1500)

        yield format_sse({"type": "log", "message": "Expandiendo lista y seleccionando 'Peticiones relacionadas'...", "level": "step", "progress": 82})
        frame, _ = await find_registros_relacionados_frame(context, timeout_ms=10_000)
        await click_expandir_lista_registros(frame)
        await frame.get_by_role("option", name="Peticiones relacionadas").click(timeout=10_000, force=True)
        await wait_context(context, 1000)

        yield format_sse({"type": "log", "message": "Haciendo clic en 'Vincular nuevo registro'...", "level": "step", "progress": 84})
        await click_vincular_nuevo_registro(context)

        yield format_sse({"type": "log", "message": f"Abriendo selector de usuario y asignando '{usuario_peticion}'...", "level": "step", "progress": 86})
        user_btn_clicked = False
        for p in list(context.pages):
            for f in p.frames:
                try:
                    loc = f.locator("#X59ButtonDiv > .image-link, #X59ButtonDiv img, img[alt*='Rellenar campo Usuario'], img[title*='Rellenar campo Usuario']").first
                    if await loc.count() > 0:
                        await loc.click(timeout=8_000, force=True)
                        user_btn_clicked = True
                        break
                except Exception:
                    continue
            if user_btn_clicked:
                break
        if not user_btn_clicked:
            try:
                await frame.locator("#X59ButtonDiv > .image-link").click(timeout=8_000, force=True)
            except Exception:
                pass
        await wait_context(context, 1000)
        await click_alejandro_aguilar_option(context, user_target=usuario_peticion)

        yield format_sse({"type": "log", "message": "Guardando formulario de la Petición (Guardar Alt+F1)...", "level": "step", "progress": 88})
        await click_guardar_peticion(context)

        yield format_sse({"type": "log", "message": "Capturando ID de la Petición generada...", "level": "step", "progress": 89})
        peticion_id = await get_peticion_id(context)

        yield format_sse({"type": "log", "message": f"¡Petición generada exitosamente! ID: {peticion_id}", "level": "success", "progress": 90})

        yield format_sse({"type": "log", "message": "Cerrando formularios de registro y confirmación...", "level": "step", "progress": 93})
        await click_guardar_registro_y_salir(context)
        await click_guardar_y_salir_final(context)

        # FASE 5: Logout Seguro
        yield format_sse({
            "type": "log",
            "message": "Cerrando formularios residuales y ejecutando Logout seguro...",
            "level": "step",
            "progress": 95
        })

        try:
            await logout(page, context)
            yield format_sse({
                "type": "log",
                "message": "Sesión finalizada limpiamente en Service Manager (Logout OK).",
                "level": "success",
                "progress": 98
            })
        except Exception as exc:
            yield format_sse({
                "type": "log",
                "message": f"Aviso durante el cierre de sesión: {exc}",
                "level": "warn",
                "progress": 98
            })

        # FASE 6: Eventos Finales de Completitud
        yield format_sse({
            "type": "log",
            "message": f"Flujo completado exitosamente. Interacción: {ticket_id} | Petición: {peticion_id}",
            "level": "success",
            "progress": 100
        })

        yield format_sse({
            "type": "complete",
            "status": "success",
            "ticket_id": ticket_id,
            "peticion_id": peticion_id,
            "message": "Interacción y Petición creadas con éxito",
            "data": {
                "ticket_id": ticket_id,
                "peticion_id": peticion_id,
                "contacto": contacto,
                "titulo": titulo,
                "grupo": grupo,
                "area": area,
                "subarea": subarea,
                "detalle": detalle,
                "usuario_peticion": usuario_peticion
            }
        })

    except Exception as exc:
        err_msg = str(exc)
        logger.exception("Error durante la automatización de ticket y petición")
        yield format_sse({
            "type": "log",
            "message": f"Error en la automatización: {err_msg}",
            "level": "error",
            "progress": 0
        })
        yield format_sse({
            "type": "error",
            "message": err_msg,
            "ticket_id": ticket_id,
            "peticion_id": peticion_id
        })

    finally:
        # Limpieza estricta y garantizada de recursos Playwright para evitar procesos huérfanos
        if context:
            try:
                await context.close()
            except Exception as exc:
                logger.debug(f"Aviso al cerrar context Playwright: {exc}")
        if browser:
            try:
                await browser.close()
            except Exception as exc:
                logger.debug(f"Aviso al cerrar browser Playwright: {exc}")
        if playwright:
            try:
                await playwright.stop()
            except Exception as exc:
                logger.debug(f"Aviso al detener playwright: {exc}")
