import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

URL = "https://portalti.clarocloud.cl:8443/smwebtier/index.do?lang=es"
USERNAME = os.getenv("PORTAL_USER", "Alejandro.Aguilar")
PASSWORD = os.getenv("PORTAL_PASS", "Cl4r0.2026*!?")
TIMEOUT = 30_000

CONTACTO = "ALEJANDRO JAVIER AGUILAR MORALES"
TITULO = "Creacion test automatizacion"
DESCRIPCION = "Prueba test automatización"
AREA = "Proyectos"
SUBAREA = "Apoyo habilitacion cliente"
DETALLE = "Apoyo habilitacion cliente"
GRUPO = "Lideres Tecnicos"


def find_servicios_internos(context, timeout_ms=15_000):
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        for p in context.pages:
            for frame in p.frames:
                link = frame.get_by_role("link", name="Servicios Internos")
                if link.count() > 0:
                    return frame, link
        time.sleep(0.5)
    raise TimeoutError("No se encontró el enlace 'Servicios Internos' en ningún frame")


def dump_form_fields(frame) -> None:
    for role in ("textbox", "combobox", "listbox"):
        for i, el in enumerate(frame.get_by_role(role).all()):
            print(
                f"{role}[{i}]: aria-label={el.get_attribute('aria-label')!r} "
                f"name={el.get_attribute('name')!r} placeholder={el.get_attribute('placeholder')!r}"
            )


def click_servicios_internos(context, page):
    context.on("dialog", lambda dialog: dialog.accept())
    frame, link = find_servicios_internos(context)
    link.first.scroll_into_view_if_needed()
    link.first.click(timeout=10_000, force=True)
    page.wait_for_timeout(3000)
    dump_form_fields(frame)
    return frame


def click_fill_numero(frame) -> None:
    strategies = [
        frame.get_by_role("img", name="Rellenar campo Número"),
        frame.locator('img[alt="Rellenar campo Número"]'),
        frame.get_by_role("button", name="Rellenar campo Número"),
    ]
    for loc in strategies:
        try:
            loc.first.wait_for(timeout=5_000)
            loc.first.scroll_into_view_if_needed()
            loc.first.click(timeout=5_000, force=True)
            frame.wait_for_timeout(1000)
            print("Campo Número rellenado.")
            return
        except Exception:
            continue
    raise TimeoutError("No se encontró 'Rellenar campo Número'")


def step(label, fn) -> None:
    try:
        fn()
        print(f"OK: {label}")
    except Exception as exc:
        print(f"SALTADO: {label} -> {exc}", file=sys.stderr)


def fill_by_label(frame, label_regex, value) -> None:
    for role in ("combobox", "textbox"):
        loc = frame.get_by_role(role, name=re.compile(label_regex, re.I)).first
        if loc.count() > 0:
            loc.fill(value)
            return
    raise RuntimeError(f"No se encontró campo {label_regex}")


def dump_descripcion_dom(frame) -> None:
    print("--- Diagnóstico DOM #X57View ---")
    el = frame.locator("#X57View")
    if el.count() == 0:
        print("  #X57View NO encontrado en el frame")
        print("--- Fin diagnóstico ---")
        return
    try:
        el.first.wait_for(timeout=3_000)
    except Exception:
        print("  #X57View no visible / no esperado (timeout)")
        print("--- Fin diagnóstico ---")
        return
    info = el.first.evaluate(
        """el => {
            const attrs = {};
            for (const a of el.attributes) attrs[a.name] = a.value;
            const cs = getComputedStyle(el);
            return {
                tagName: el.tagName, attrs,
                contentEditableProp: el.contentEditable,
                display: cs.display, visibility: cs.visibility,
                rect: el.getBoundingClientRect().toJSON(),
            };
        }"""
    )
    print(f"  #X57View: tag={info['tagName']} attrs={info['attrs']}")
    print(f"    contentEditable(prop)={info['contentEditableProp']} display={info['display']} visibility={info['visibility']} rect={info['rect']}")
    desc = frame.locator(
        "#X57View [contenteditable], #X57View textarea, #X57View input, #X57View iframe"
    ).all()
    print(f"  descendientes editables / iframes: {len(desc)}")
    for i, d in enumerate(desc):
        try:
            info = d.evaluate(
                """el => {
                    const attrs = {};
                    for (const a of el.attributes) attrs[a.name] = a.value;
                    return { tagName: el.tagName, attrs };
                }"""
            )
            print(f"    [{i}] tag={info['tagName']} attrs={info['attrs']}")
        except Exception as exc:
            print(f"    [{i}] error al inspeccionar: {exc}")
    try:
        html = el.first.evaluate("el => el.innerHTML")
        print(f"  innerHTML de #X57View ({len(html)} chars): {html[:2000]}")
    except Exception as exc:
        print(f"  innerHTML no disponible: {exc}")
    try:
        parent = el.first.evaluate(
            """el => {
                const p = el.parentElement;
                const sibs = [];
                let n = p ? p.firstElementChild : null;
                while (n) { sibs.push(n.id || n.tagName); n = n.nextElementSibling; }
                return { parentId: p ? p.id : null, parentTag: p ? p.tagName : null, siblings: sibs };
            }"""
        )
        print(f"  padre: {parent}")
    except Exception as exc:
        print(f"  info del padre no disponible: {exc}")

    x57 = frame.locator("#X57")
    print(f"  #X57 (hermano potencialmente real): count={x57.count()}")
    if x57.count() > 0:
        try:
            info = x57.first.evaluate(
                """el => {
                    const attrs = {};
                    for (const a of el.attributes) attrs[a.name] = a.value;
                    const cs = getComputedStyle(el);
                    return {
                        tagName: el.tagName, attrs,
                        value: el.value !== undefined ? el.value : null,
                        display: cs.display, visibility: cs.visibility,
                        rect: el.getBoundingClientRect().toJSON(),
                    };
                }"""
            )
            print(f"    #X57: tag={info['tagName']} attrs={info['attrs']}")
            print(f"      value={info['value']!r} display={info['display']} visibility={info['visibility']} rect={info['rect']}")
        except Exception as exc:
            print(f"    #X57: error al inspeccionar: {exc}")

    try:
        tas = frame.locator("textarea").count()
        ins = frame.locator("input").count()
        ceds = frame.locator("[contenteditable]").count()
        print(f"  frame-wide: textarea={tas} input={ins} [contenteditable]={ceds}")
    except Exception as exc:
        print(f"  frame-wide count no disponible: {exc}")
    print("--- Fin diagnóstico ---")


def _read_descripcion(frame) -> str:
    try:
        root = frame.locator("#X57View").first
        if root.count() > 0:
            txt = root.evaluate(
                "el => (el.innerText || el.textContent || '').trim()"
            )
            if txt:
                return txt
    except Exception:
        pass
    try:
        x57 = frame.locator("#X57").first
        if x57.count() > 0:
            v = x57.evaluate("el => el.value !== undefined ? el.value : ''")
            if v:
                return v
    except Exception:
        pass
    return ""


def fill_descripcion(frame) -> None:
    dump_descripcion_dom(frame)

    root = frame.locator("#X57View").first
    root.wait_for(timeout=5_000)

    try:
        root.click(timeout=4_000)
        frame.wait_for_timeout(400)
        kids = frame.locator("#X57View [contenteditable], #X57View textarea, #X57View input, #X57View iframe").count()
        print(f"  [post-click] descendientes editables/iframes en #X57View: {kids}")
        if kids:
            dump_descripcion_dom(frame)
    except Exception as exc:
        print(f"  [post-click] error: {exc}")

    # (0) textarea real oculto #X57 (control ligado: instance/description/description).
    #     #X57View es solo la vista decorativa; el valor se persiste en #X57.
    x57 = frame.locator("#X57").first
    if x57.count() > 0:
        tag = x57.evaluate("el => el.tagName")
        if tag in ("INPUT", "TEXTAREA"):
            try:
                x57.fill(DESCRIPCION, timeout=4_000, force=True)
                frame.wait_for_timeout(300)
                if DESCRIPCION in _read_descripcion(frame):
                    print(f"Descripción llenada por (0) fill en textarea real #X57 ({tag})")
                    return
            except Exception as exc:
                print(f"  (0) fill #X57 falló: {exc}")

    frame.wait_for_timeout(250)

    # (a) clic + fill() directo sobre #X57View
    try:
        root.click(timeout=4_000, force=True)
        frame.wait_for_timeout(300)
        root.fill(DESCRIPCION)
        frame.wait_for_timeout(300)
        if DESCRIPCION in _read_descripcion(frame):
            print("Descripción llenada por (a) fill directo en #X57View")
            return
    except Exception as exc:
        print(f"  (a) falló: {exc}")

    frame.wait_for_timeout(250)

    # (b) clic + fill() sobre descendiente contenteditable (con o sin '=true')
    for sel in ("#X57View [contenteditable]", "#X57View [contenteditable='true']"):
        loc = frame.locator(sel).first
        if loc.count() == 0:
            continue
        try:
            loc.click(timeout=4_000)
            frame.wait_for_timeout(300)
            loc.fill(DESCRIPCION)
            frame.wait_for_timeout(300)
            if DESCRIPCION in _read_descripcion(frame):
                print(f"Descripción llenada por (b) fill en {sel}")
                return
        except Exception as exc:
            print(f"  (b) {sel} falló: {exc}")

    frame.wait_for_timeout(250)

    # (c) clic + fill() sobre textarea/input descendiente
    for sel in ("#X57View textarea", "#X57View input"):
        loc = frame.locator(sel).first
        if loc.count() == 0:
            continue
        try:
            loc.click(timeout=4_000)
            frame.wait_for_timeout(300)
            loc.fill(DESCRIPCION)
            frame.wait_for_timeout(300)
            if DESCRIPCION in _read_descripcion(frame):
                print(f"Descripción llenada por (c) fill en {sel}")
                return
        except Exception as exc:
            print(f"  (c) {sel} falló: {exc}")

    frame.wait_for_timeout(250)

    # (d) press_sequentially (teclado real) sobre el editable
    for sel in (
        "#X57View [contenteditable]",
        "#X57View textarea",
        "#X57View input",
        "#X57View",
    ):
        loc = frame.locator(sel).first
        if loc.count() == 0:
            continue
        try:
            loc.click(timeout=4_000)
            frame.wait_for_timeout(300)
            loc.press_sequentially(DESCRIPCION, delay=20)
            frame.wait_for_timeout(400)
            if DESCRIPCION in _read_descripcion(frame):
                print(f"Descripción llenada por (d) press_sequentially en {sel}")
                return
        except Exception as exc:
            print(f"  (d) {sel} falló: {exc}")

    frame.wait_for_timeout(250)

    # (e) clipboard: copiar y pegar (Ctrl/Cmd+A + V) sobre el editable visible
    for target in (root, x57) if x57.count() else (root,):
        try:
            target.click(timeout=4_000, force=True)
            frame.wait_for_timeout(300)
            frame.evaluate("t => navigator.clipboard.writeText(t)", DESCRIPCION)
            frame.wait_for_timeout(300)
            for combo in (("Control+a", "Control+v"), ("Meta+a", "Meta+v")):
                try:
                    target.press(combo[0])
                    target.press(combo[1])
                    frame.wait_for_timeout(300)
                    if DESCRIPCION in _read_descripcion(frame):
                        print(f"Descripción llenada por (e) clipboard con {combo} en {target}")
                        return
                except Exception:
                    continue
        except Exception as exc:
            print(f"  (e) clipboard falló: {exc}")

    # (f) último recurso: setear valor por JS + eventos input/change
    for sel, tag in ((("#X57"), None), (("#X57View"), None)):
        loc = frame.locator(sel).first
        if loc.count() == 0:
            continue
        try:
            tag = loc.evaluate("el => el.tagName")
            if tag in ("INPUT", "TEXTAREA"):
                ok = loc.evaluate(
                    """(el, t) => {
                        el.value = t;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        return el.value;
                    }""",
                    DESCRIPCION,
                )
                frame.wait_for_timeout(300)
                if DESCRIPCION in (ok or "") or DESCRIPCION in _read_descripcion(frame):
                    print(f"Descripción llenada por (f) JS set value en {sel}")
                    return
            elif tag in ("DIV", "SPAN", "P"):
                ok = loc.evaluate(
                    """(el, t) => {
                        el.focus();
                        el.innerHTML = '<p>' + t + '</p>';
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        return el.innerText || el.innerHTML;
                    }""",
                    DESCRIPCION,
                )
                frame.wait_for_timeout(300)
                if DESCRIPCION in (ok or "") or DESCRIPCION in _read_descripcion(frame):
                    print(f"Descripción llenada por (f) JS innerHTML en {sel}")
                    return
        except Exception as exc:
            print(f"  (f) {sel} falló: {exc}")

    print(f"Descripción quedó con: {_read_descripcion(frame)!r} (esperado {DESCRIPCION!r})")
    raise RuntimeError("No se pudo llenar el campo Descripción (#X57View)")


def dump_grupo_dom(frame) -> None:
    print("--- Diagnóstico DOM 'Grupo de asignación' ---")
    for role in ("combobox", "textbox"):
        try:
            locs = frame.get_by_role(role, name=re.compile("Grupo de asignación", re.I)).all()
        except Exception as exc:
            print(f"  get_by_role({role!r}, name~'Grupo de asignación'): error {exc}")
            continue
        print(f"  get_by_role({role!r}, name~'Grupo de asignación'): count={len(locs)}")
        for i, el in enumerate(locs):
            try:
                info = el.evaluate(
                    """el => {
                        const attrs = {};
                        for (const a of el.attributes) attrs[a.name] = a.value;
                        const cs = getComputedStyle(el);
                        return {
                            tagName: el.tagName, attrs,
                            readonly: el.readOnly !== undefined ? el.readOnly : null,
                            display: cs.display, visibility: cs.visibility,
                            value: el.value !== undefined ? el.value : null,
                            text: (el.innerText || el.textContent || '').trim(),
                        };
                    }"""
                )
                print(f"    [{i}] tag={info['tagName']} attrs={info['attrs']}")
                print(f"      readonly={info['readonly']} display={info['display']} visibility={info['visibility']} value={info['value']!r} text={info['text']!r}")
            except Exception as exc:
                print(f"    [{i}] error al inspeccionar: {exc}")
    try:
        img = frame.get_by_role("img", name="Rellenar campo Grupo de asignación")
        print(f"  get_by_role('img', name='Rellenar campo Grupo de asignación'): count={img.count()}")
    except Exception as exc:
        print(f"  get_by_role('img', name='Rellenar campo Grupo de asignación'): error {exc}")
    print("--- Fin diagnóstico ---")


def _read_grupo(frame) -> str:
    for role in ("combobox", "textbox"):
        try:
            locs = frame.get_by_role(role, name=re.compile("Grupo de asignación", re.I))
        except Exception:
            continue
        for el in locs.all():
            try:
                v = el.evaluate(
                    """el => {
                        if (el.tagName === 'SELECT') {
                            const opt = el.options[el.selectedIndex];
                            return opt ? (opt.text || opt.value || '') : '';
                        }
                        if ('value' in el) return el.value || '';
                        return (el.innerText || el.textContent || '').trim();
                    }"""
                )
            except Exception:
                continue
            if v:
                return v
    return ""


_SEARCH_INPUT_RE = re.compile(r"find|buscar|b[uú]squeda|search|consulta|filtrar|query", re.I)
_SEARCH_BUTTON_RE = re.compile(
    r"buscar|b[uú]squeda|search|find|aceptar|aplicar|\bok\b|filtrar|consultar|\bir\b|\bgo\b|seleccionar",
    re.I,
)
_GRUPO_RELACIONADO_RE = re.compile(r"grupo|asignaci[oó]n|buscar|rellenar|find|fill", re.I)


def _dump_grupo_imagenes_botones(frame) -> None:
    print("--- Volcado de imágenes/botones/enlaces relacionados con 'Grupo de asignación' ---")
    try:
        x89 = frame.locator("#X89")
        print(f"  #X89: count={x89.count()}")
        if x89.count() > 0:
            info = x89.first.evaluate(
                """el => {
                    const a = {};
                    for (const x of el.attributes) a[x.name] = x.value;
                    return { tag: el.tagName, attrs: a };
                }"""
            )
            print(f"    #X89 tag={info['tag']} attrs={info['attrs']}")
    except Exception as exc:
        print(f"  #X89: error {exc}")

    for role, attrs in (
        ("img", ("alt", "title", "aria-label", "name", "src", "id", "class")),
        ("button", ("alt", "title", "aria-label", "name", "id", "class")),
        ("link", ("alt", "title", "aria-label", "name", "href", "id", "class")),
    ):
        try:
            els = frame.get_by_role(role).all()
        except Exception as exc:
            print(f"  get_by_role({role!r}) error: {exc}")
            continue
        for i, el in enumerate(els):
            try:
                datos = {}
                for a in attrs:
                    try:
                        datos[a] = el.get_attribute(a) or ""
                    except Exception:
                        datos[a] = ""
                try:
                    inner = el.inner_text() or ""
                except Exception:
                    inner = ""
            except Exception as exc:
                print(f"  {role}[{i}]: (error al leer atributos) {exc}")
                continue
            texto = " ".join([inner] + [datos.get(a, "") for a in attrs])
            if not _GRUPO_RELACIONADO_RE.search(texto):
                continue
            print(
                f"  {role}[{i}]: tag={role.upper()} inner_text={inner!r} "
                f"alt={datos.get('alt')!r} title={datos.get('title')!r} "
                f"aria-label={datos.get('aria-label')!r} name={datos.get('name')!r} "
                f"src/href={datos.get('src') or datos.get('href') or ''!r} "
                f"id={datos.get('id')!r} class={datos.get('class')!r}"
            )
    print("--- Fin volcado de imágenes/botones/enlaces ---")


def _is_page(target) -> bool:
    return hasattr(target, "close") and hasattr(target, "title")


def dump_popup_page(target) -> None:
    print("  === VOLCADO EXHAUSTIVO DEL POPUP/SUBFORM ===")
    if _is_page(target):
        try:
            print(f"  [popup] título={target.title()!r}")
        except Exception as exc:
            print(f"  [popup] (no se pudo leer title) {exc}")
        try:
            print(f"  [popup] url={target.url!r}")
        except Exception as exc:
            print(f"  [popup] (no se pudo leer url) {exc}")
    else:
        try:
            print(f"  [popup] frame.name={target.name!r}")
        except Exception as exc:
            print(f"  [popup] (no se pudo leer frame.name) {exc}")
        try:
            print(f"  [popup] frame.url={target.url!r}")
        except Exception as exc:
            print(f"  [popup] (no se pudo leer frame.url) {exc}")

    for sel in ("input", "textarea", "select"):
        try:
            els = target.locator(sel).all()
        except Exception as exc:
            print(f"  [popup] locator({sel!r}): error {exc}")
            continue
        for i, el in enumerate(els):
            try:
                if not el.is_visible():
                    continue
            except Exception:
                continue
            try:
                info = el.evaluate(
                    """el => {
                        const a = {};
                        for (const x of el.attributes) a[x.name] = x.value;
                        return {
                            tag: el.tagName, type: a.type, id: a.id, name: a.name,
                            placeholder: a.placeholder,
                            value: el.value !== undefined ? el.value : null,
                            ariaLabel: a['aria-label'],
                        };
                    }"""
                )
                print(
                    f"  [popup] {sel}[{i}]: tag={info['tag']} type={info['type']!r} "
                    f"id={info['id']!r} name={info['name']!r} placeholder={info['placeholder']!r} "
                    f"value={info['value']!r} aria-label={info['ariaLabel']!r}"
                )
            except Exception as exc:
                print(f"  [popup] {sel}[{i}]: (error al inspeccionar) {exc}")

    try:
        for i, b in enumerate(target.get_by_role("button").all()):
            try:
                if not b.is_visible():
                    continue
            except Exception:
                continue
            try:
                inner = b.inner_text() or ""
            except Exception:
                inner = ""
            try:
                aria = b.get_attribute("aria-label")
            except Exception:
                aria = None
            try:
                title = b.get_attribute("title")
            except Exception:
                title = None
            try:
                bid = b.get_attribute("id")
            except Exception:
                bid = None
            print(
                f"  [popup] button[{i}]: inner_text={inner[:120]!r} "
                f"aria-label={aria!r} title={title!r} id={bid!r}"
            )
    except Exception as exc:
        print(f"  [popup] botones: error {exc}")

    try:
        matches = target.get_by_text(re.compile(re.escape(GRUPO), re.I)).all()
        print(f"  [popup] elementos con texto {GRUPO!r}: {len(matches)}")
        for i, el in enumerate(matches[:10]):
            try:
                tag = el.evaluate("el => el.tagName")
            except Exception:
                tag = "?"
            try:
                txt = (el.inner_text() or "").strip()
            except Exception:
                txt = ""
            print(f"    [{i}] tag={tag} text={txt[:200]!r}")
    except Exception as exc:
        print(f"  [popup] texto {GRUPO!r}: error {exc}")

    for sel, label in (
        ("a", "enlaces <a>"),
        ("tr", "filas <tr>"),
        ("li", "elementos <li>"),
        ("[role='option']", "role=option"),
        ("[role='treeitem']", "role=treeitem"),
        ("[role='listitem']", "role=listitem"),
        ("[role='row']", "role=row"),
        ("[role='gridcell']", "role=gridcell"),
    ):
        try:
            print(f"  [popup] {label}: {target.locator(sel).count()}")
        except Exception as exc:
            print(f"  [popup] {label}: error {exc}")
    print("  === FIN VOLCADO DEL POPUP ===")


def _find_search_field(target):
    # (a) role searchbox (cualquier nombre)
    try:
        for el in target.get_by_role("searchbox").all():
            if el.is_visible():
                return el
    except Exception:
        pass
    # (b) input[type=search] / input[type=text] visibles
    for sel in ("input[type='search']", "input[type='text']"):
        try:
            for el in target.locator(sel).all():
                if el.is_visible():
                    return el
        except Exception:
            continue
    # (c) input cuyo name/id/placeholder/title case con la regex
    try:
        for el in target.locator("input").all():
            try:
                if not el.is_visible():
                    continue
            except Exception:
                continue
            for attr in ("name", "id", "placeholder", "title"):
                try:
                    v = el.get_attribute(attr) or ""
                except Exception:
                    v = ""
                if _SEARCH_INPUT_RE.search(v):
                    return el
    except Exception:
        pass
    # (d) primer input/textbox visible del popup
    try:
        for el in target.get_by_role("textbox").all():
            if el.is_visible():
                return el
    except Exception:
        pass
    try:
        for el in target.locator("input").all():
            if el.is_visible():
                return el
    except Exception:
        pass
    return None


def _find_search_button(target):
    try:
        for b in target.get_by_role("button").all():
            try:
                if not b.is_visible():
                    continue
            except Exception:
                continue
            try:
                name = (b.get_attribute("aria-label") or b.inner_text() or "").strip()
            except Exception:
                continue
            if name and _SEARCH_BUTTON_RE.search(name):
                return b
    except Exception:
        pass
    return None


def _check_grupo_filled(frame) -> bool:
    try:
        v = frame.locator("#X89").input_value()
        if v and GRUPO.lower() in v.lower():
            return True
    except Exception:
        pass
    try:
        v = _read_grupo(frame)
        if v and GRUPO.lower() in v.lower():
            return True
    except Exception:
        pass
    return False


def _click_grupo_result(target, value) -> bool:
    pat = re.compile(re.escape(value), re.I)
    # (a) get_by_text visible
    try:
        for el in target.get_by_text(pat).all():
            try:
                if not el.is_visible():
                    continue
            except Exception:
                continue
            el.scroll_into_view_if_needed()
            el.click(timeout=4_000, force=True)
            print("  resultado clicado vía get_by_text")
            return True
    except Exception as exc:
        print(f"  get_by_text falló: {exc}")
    # (b) roles con nombre que case el valor
    for role in ("option", "link", "treeitem", "listitem", "row", "gridcell", "cell"):
        try:
            loc = target.get_by_role(role, name=pat).first
            if loc.count() > 0 and loc.is_visible():
                loc.scroll_into_view_if_needed()
                loc.click(timeout=4_000, force=True)
                print(f"  resultado clicado vía role={role}")
                return True
        except Exception as exc:
            print(f"  role={role} falló: {exc}")
    # (c) doble clic sobre el texto/row
    try:
        loc = target.get_by_text(pat).first
        if loc.count() > 0:
            loc.scroll_into_view_if_needed()
            loc.dblclick(timeout=4_000, force=True)
            print("  resultado doble-clicado vía get_by_text")
            return True
    except Exception as exc:
        print(f"  doble clic get_by_text falló: {exc}")
    # (d) fila <tr> que contenga el valor
    try:
        for tr in target.locator("tr").all():
            try:
                if GRUPO.lower() not in (tr.inner_text() or "").lower():
                    continue
            except Exception:
                continue
            try:
                if not tr.is_visible():
                    continue
            except Exception:
                continue
            tr.scroll_into_view_if_needed()
            tr.click(timeout=4_000, force=True)
            print("  fila <tr> del resultado clicada")
            return True
    except Exception as exc:
        print(f"  fila <tr> falló: {exc}")
    return False


def _click_grupo_accept(target) -> None:
    """Tras seleccionar una fila, intenta clic en un botón aceptar/seleccionar/ok."""
    for b in target.get_by_role("button").all():
        try:
            if not b.is_visible():
                continue
        except Exception:
            continue
        try:
            name = (b.get_attribute("aria-label") or b.inner_text() or "").strip()
        except Exception:
            continue
        if name and _SEARCH_BUTTON_RE.search(name):
            try:
                b.click(timeout=4_000, force=True)
                print(f"  clic en botón de aceptar/seleccionar: {name[:80]!r}")
                return
            except Exception as exc:
                print(f"  clic en botón {name[:80]!r} falló: {exc}")


def _click_grupo_fill_button(frame) -> None:
    # (1) imagen exacta
    try:
        img = frame.get_by_role("img", name="Rellenar campo Grupo de asignación").first
        if img.count() > 0:
            img.wait_for(timeout=5_000)
            img.click(timeout=5_000, force=True)
            print("  clic en imagen 'Rellenar campo Grupo de asignación'")
            return
    except Exception as exc:
        print(f"  clic imagen 'Rellenar campo Grupo de asignación' falló: {exc}")
    # (2) img cuyo alt/title contenga 'Rellenar' o 'Grupo de asignación'
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
            if loc.count() > 0:
                loc.click(timeout=5_000, force=True)
                print(f"  clic en imagen vía {sel}")
                return
        except Exception as exc:
            print(f"  clic {sel} falló: {exc}")
    # (3) botón 'Buscar campo Grupo de asignación'
    for name in ("Buscar campo Grupo de asignación", "Buscar campo Grupo de asignacion"):
        try:
            btn = frame.get_by_role("button", name=name).first
            if btn.count() > 0:
                btn.click(timeout=5_000, force=True)
                print(f"  clic en botón {name!r}")
                return
        except Exception as exc:
            print(f"  clic botón {name!r} falló: {exc}")
    print("  NO se pudo hacer clic en el botón rellenar/buscar del campo Grupo")


def _detect_popup(context, frame, pages_before, frames_before, timeout=12.0):
    deadline = time.time() + timeout
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
                    if f.get_by_role("searchbox").count() > 0:
                        return f, "overlay (searchbox)"
                except Exception:
                    continue
        for p in context.pages:
            for f in p.frames:
                if f is frame:
                    continue
                try:
                    if f.get_by_text(re.compile(re.escape(GRUPO), re.I)).count() > 0:
                        return f, f"overlay (texto '{GRUPO}')"
                except Exception:
                    continue
        time.sleep(0.5)
    return None, ""


def fill_grupo(frame, context) -> None:
    print("=== LLENADO DEL CAMPO 'Grupo de asignación' ===")
    dump_grupo_dom(frame)
    _dump_grupo_imagenes_botones(frame)

    pages_before = set(context.pages)
    frames_before = {f for p in context.pages for f in p.frames}

    _click_grupo_fill_button(frame)

    popup, popup_kind = _detect_popup(context, frame, pages_before, frames_before, timeout=12.0)

    if popup is None:
        print("  NO se detectó popup (ni página nueva, ni frame nuevo, ni overlay)")
        try:
            dump_popup_page(frame)
        except Exception:
            pass
        raise RuntimeError("No se pudo llenar el campo 'Grupo de asignación' (no se detectó popup)")

    print(f"  popup detectado ({popup_kind})")
    try:
        dump_popup_page(popup)
    except Exception as exc:
        print(f"  dump_popup_page falló: {exc}")

    # Búsqueda del valor en el popup.
    search = _find_search_field(popup)
    if search is None:
        print("  NO se encontró campo de búsqueda en el popup")
    else:
        print("  campo de búsqueda encontrado; escribiendo valor...")
        try:
            search.fill(GRUPO)
            popup.wait_for_timeout(500)
            try:
                search.press("Enter")
                print("  Enter presionado en el campo de búsqueda")
            except Exception as exc:
                print(f"  Enter en el campo de búsqueda falló: {exc}")
        except Exception as exc:
            print(f"  fill del campo de búsqueda falló: {exc}")

    btn = _find_search_button(popup)
    if btn is not None:
        try:
            btn.click(timeout=4_000, force=True)
            print("  clic en botón de búsqueda/disparador")
        except Exception as exc:
            print(f"  clic en botón de búsqueda falló: {exc}")
    else:
        print("  no se encontró botón de búsqueda; confiando en Enter")

    popup.wait_for_timeout(2500)

    print("  buscando el resultado...")
    clickeado = _click_grupo_result(popup, GRUPO)
    popup.wait_for_timeout(800)

    if not _check_grupo_filled(frame):
        # Estrategia adicional: seleccionar fila + botón aceptar/seleccionar.
        try:
            _click_grupo_accept(popup)
            popup.wait_for_timeout(800)
        except Exception as exc:
            print(f"  clic en botón aceptar falló: {exc}")
    if not _check_grupo_filled(frame) and not clickeado:
        # Último intento: doble clic sobre la fila/texto del resultado.
        try:
            for el in popup.get_by_text(re.compile(re.escape(GRUPO), re.I)).all():
                try:
                    if not el.is_visible():
                        continue
                except Exception:
                    continue
                el.scroll_into_view_if_needed()
                el.dblclick(timeout=4_000, force=True)
                print("  doble clic sobre el texto del resultado (último intento)")
                break
        except Exception as exc:
            print(f"  doble clic (último intento) falló: {exc}")
        popup.wait_for_timeout(800)

    # Cierre tolerante del popup.
    try:
        if _is_page(popup):
            popup.close()
            print("  popup cerrado (close)")
        else:
            popup.keyboard.press("Escape")
            print("  popup cerrado (Escape)")
    except Exception as exc:
        print(f"  cierre del popup falló (tolerable): {exc}")

    # Verificación final estricta (sin fill directo a #X89).
    valor = _read_grupo(frame)
    try:
        x89_val = frame.locator("#X89").input_value()
    except Exception as exc:
        x89_val = ""
        print(f"  lectura de #X89 falló: {exc}")

    print(f"  verificación final: #X89={x89_val!r}, _read_grupo={valor!r}")
    if GRUPO.lower() in (x89_val or "").lower() or GRUPO.lower() in (valor or "").lower():
        print(f"  OK: 'Grupo de asignación' = {GRUPO!r}")
        return
    raise RuntimeError(
        f"No se pudo llenar el campo 'Grupo de asignación' "
        f"(valor final #X89={x89_val!r}, _read_grupo={valor!r}; se esperaba {GRUPO!r})"
    )


def fill_interaction_form(frame, context) -> None:
    step("Contacto", lambda: frame.get_by_role("textbox", name="Contacto:", exact=True).fill(CONTACTO))
    step("Rellenar Contacto", lambda: frame.get_by_role("img", name="Rellenar campo Contacto").click(timeout=10_000))
    step("Espera relleno Contacto", lambda: frame.wait_for_timeout(1500))
    step("Estado Abierto", lambda: frame.locator("#X23Border a").click())
    step("Selección Abierto", lambda: frame.get_by_role("option", name="Abierto").click())
    step("Título", lambda: frame.get_by_role("textbox", name="Título:").fill(TITULO))
    step("Descripción", lambda: fill_descripcion(frame))
    step("Área", lambda: fill_by_label(frame, "^Área", AREA))
    step("Sub-área", lambda: fill_by_label(frame, "^Sub-área", SUBAREA))
    step("Detalle", lambda: fill_by_label(frame, "^Detalle", DETALLE))
    step("Grupo de asignación", lambda: fill_grupo(frame, context))
    step("Impacto", lambda: frame.locator("#X71ButtonDiv > .image-link").click())
    step("Selección Impacto", lambda: frame.get_by_role("option", name="3 - Menor (Existen WorkAround)").click())
    step("Urgencia", lambda: frame.locator("#X78ButtonDiv > .image-link").click())
    step("Selección Urgencia", lambda: frame.get_by_role("option", name="3 - Media (Resolución a mediano plazo)").click())


def _frame_label(target) -> str:
    name = getattr(target, "name", None)
    return name if name else target.url or target.__class__.__name__


def click_guardar(page, context) -> None:
    candidates = [page]
    for p in context.pages:
        for frame in p.frames:
            if frame not in candidates:
                candidates.append(frame)

    print("Intentando hacer clic en 'Guardar (Alt+F1)'...")

    # (a) a nivel de página principal
    try:
        btn = page.get_by_role("button", name="Guardar (Alt+F1)").first
        btn.wait_for(timeout=5_000)
        btn.scroll_into_view_if_needed()
        btn.click(timeout=5_000, force=True)
        print("OK: Guardar (Alt+F1)")
        return
    except Exception as exc:
        print(f"  (a) página principal: no se encontró/falló -> {exc}")

    # (b) en TODOS los frames de TODAS las páginas del contexto
    for target in candidates[1:]:
        try:
            btn = target.get_by_role("button", name="Guardar (Alt+F1)").first
            if btn.count() == 0:
                continue
            print(f"  (b) botón encontrado en frame {target.name!r} ({target.url})")
            btn.scroll_into_view_if_needed()
            btn.click(timeout=5_000, force=True)
            print("OK: Guardar (Alt+F1)")
            return
        except Exception as exc:
            print(f"  (b) frame {target.name!r}: falló -> {exc}")

    # (c) fallback por texto "Guardar"
    for target in candidates:
        try:
            loc = target.get_by_text(re.compile("Guardar", re.I)).first
            if loc.count() == 0:
                continue
            print(f"  (c) fallback por texto en {_frame_label(target)} ({target.url})")
            loc.scroll_into_view_if_needed()
            loc.click(timeout=5_000, force=True)
            print("OK: Guardar (Alt+F1)")
            return
        except Exception as exc:
            print(f"  (c) fallback en {_frame_label(target)}: falló -> {exc}")

    page.wait_for_timeout(1000)
    raise RuntimeError("No se encontró el botón 'Guardar (Alt+F1)' en la página ni en ningún frame")


def find_ticket_id_field(context, timeout_ms=20_000):
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        for p in list(context.pages):
            try:
                for frame in p.frames:
                    try:
                        field = frame.get_by_role("textbox", name="ID de la interacción:")
                        if field.count() > 0:
                            return field
                    except Exception:
                        continue
            except Exception:
                continue
        time.sleep(1)
    raise TimeoutError("No se encontró el campo 'ID de la interacción:' en ningún frame")


def copy_id_to_clipboard(value) -> None:
    try:
        import pyperclip

        pyperclip.copy(value)
        print(f"ID copiado al portapapeles: {value}")
    except Exception as exc:
        print(f"No se pudo copiar al portapapeles: {exc}", file=sys.stderr)


def get_ticket_id(context, timeout_ms=30_000) -> str:
    deadline = time.time() + timeout_ms / 1000.0
    last_value = ""
    known = set(context.pages)
    while time.time() < deadline:
        for p in list(context.pages):
            try:
                if p not in known:
                    known.add(p)
                    try:
                        print(f"  [get_ticket_id] página/ventana nueva detectada: {p.url}")
                    except Exception:
                        pass
                for frame in p.frames:
                    try:
                        field = frame.get_by_role("textbox", name="ID de la interacción:")
                        if field.count() == 0:
                            continue
                        value = field.first.input_value()
                    except Exception:
                        continue
                    last_value = value or last_value
                    if value:
                        print(f'Ticket generado = "{value}"')
                        copy_id_to_clipboard(value)
                        return value
            except Exception:
                continue
        time.sleep(1)
    print(
        f"AVISO: no se capturó el ID de la interacción dentro de {timeout_ms / 1000:.0f}s "
        f"(último valor leído: {last_value!r})",
        file=sys.stderr,
    )
    print(f'Ticket generado = "{last_value}"')
    copy_id_to_clipboard(last_value)
    return last_value


def get_peticion_id(context, timeout_ms=30_000) -> str:
    deadline = time.time() + timeout_ms / 1000.0
    last_value = ""
    known = set(context.pages)
    while time.time() < deadline:
        for p in list(context.pages):
            try:
                if p not in known:
                    known.add(p)
                    try:
                        print(f"  [get_peticion_id] página/ventana nueva detectada: {p.url}")
                    except Exception:
                        pass
                for frame in p.frames:
                    try:
                        field = frame.get_by_role("textbox", name="ID de la petición:")
                        if field.count() == 0:
                            continue
                        value = field.first.input_value()
                    except Exception:
                        continue
                    last_value = value or last_value
                    if value:
                        print(f'Petición generada = "{value}"')
                        return value
            except Exception:
                continue
        time.sleep(1)
    print(
        f"AVISO: no se capturó el ID de la petición dentro de {timeout_ms / 1000:.0f}s "
        f"(último valor leído: {last_value!r})",
        file=sys.stderr,
    )
    print(f'Petición generada = "{last_value}"')
    return last_value


def find_registros_relacionados_frame(context, timeout_ms=20_000):
    deadline = time.time() + timeout_ms / 1000.0
    tab_re = re.compile(r"Registros relacionados", re.I)
    while time.time() < deadline:
        for p in list(context.pages):
            for frame in p.frames:
                try:
                    tab = frame.get_by_role("tab", name=tab_re).first
                    if tab.count() > 0:
                        return frame, tab
                except Exception:
                    continue
        time.sleep(0.5)
    raise TimeoutError("No se encontró la pestaña 'Registros relacionados' en ningún frame")


def dump_guardar_buttons(context) -> None:
    print("--- Diagnóstico botones Guardar ---")
    for p in list(context.pages):
        targets = [("page", p)] + [(f"frame {f.name!r}", f) for f in p.frames]
        for label, target in targets:
            try:
                buttons = target.get_by_role("button").all()
            except Exception as exc:
                print(f"  {label}: error leyendo botones -> {exc}")
                continue
            for i, btn in enumerate(buttons):
                try:
                    text = ""
                    try:
                        text = (btn.inner_text() or "").strip()
                    except Exception:
                        pass
                    attrs = {
                        "aria-label": btn.get_attribute("aria-label") or "",
                        "title": btn.get_attribute("title") or "",
                        "id": btn.get_attribute("id") or "",
                        "class": btn.get_attribute("class") or "",
                    }
                    data = " ".join([text] + list(attrs.values()))
                    if re.search(r"guardar|save|ctrl|shift|salir", data, re.I):
                        try:
                            visible = btn.is_visible()
                        except Exception:
                            visible = None
                        print(f"  {label} button[{i}]: visible={visible} text={text!r} attrs={attrs}")
                except Exception as exc:
                    print(f"  {label} button[{i}]: error -> {exc}")
    print("--- Fin diagnóstico botones Guardar ---")


def wait_context(context, timeout_ms) -> None:
    pages = list(context.pages)
    if pages:
        pages[0].wait_for_timeout(timeout_ms)
    else:
        time.sleep(timeout_ms / 1000.0)


def click_button_in_context(context, name_regex, error_label) -> None:
    last_error = None
    for p in list(context.pages):
        targets = [("page", p)] + [(f"frame {f.name!r}", f) for f in p.frames]
        for label, target in targets:
            try:
                buttons = target.get_by_role("button", name=name_regex).all()
            except Exception as exc:
                last_error = exc
                continue
            for i, btn in enumerate(buttons):
                try:
                    if not btn.is_visible():
                        continue
                except Exception:
                    pass
                try:
                    btn.scroll_into_view_if_needed(timeout=5_000)
                    btn.click(timeout=10_000, force=True)
                    print(f"  OK: click botón {error_label!r} en {label} button[{i}]")
                    return
                except Exception as exc:
                    last_error = exc
                    print(f"  click botón {error_label!r} falló en {label} button[{i}]: {exc}")

    # Fallback: algunos botones ExtJS no exponen el mismo accessible name que el recorder.
    for p in list(context.pages):
        targets = [("page", p)] + [(f"frame {f.name!r}", f) for f in p.frames]
        for label, target in targets:
            try:
                buttons = target.get_by_role("button").all()
            except Exception as exc:
                last_error = exc
                continue
            for i, btn in enumerate(buttons):
                try:
                    text = ""
                    try:
                        text = (btn.inner_text() or "").strip()
                    except Exception:
                        pass
                    data = " ".join(
                        [
                            text,
                            btn.get_attribute("aria-label") or "",
                            btn.get_attribute("title") or "",
                        ]
                    )
                    if not name_regex.search(data):
                        continue
                    if not btn.is_visible():
                        continue
                    btn.scroll_into_view_if_needed(timeout=5_000)
                    btn.click(timeout=10_000, force=True)
                    print(f"  OK: click botón {error_label!r} por fallback en {label} button[{i}]")
                    return
                except Exception as exc:
                    last_error = exc
                    print(f"  fallback botón {error_label!r} falló en {label} button[{i}]: {exc}")
    dump_guardar_buttons(context)
    raise TimeoutError(f"No se encontró/clickeó el botón {error_label!r}: {last_error}")


def dump_vincular_controls(context) -> None:
    print("--- Diagnóstico controles Vincular ---")
    pat = re.compile(r"vincular|nuevo registro|relacion", re.I)
    for p in list(context.pages):
        targets = [("page", p)] + [(f"frame {f.name!r}", f) for f in p.frames]
        for label, target in targets:
            for role in ("button", "link", "img"):
                try:
                    els = target.get_by_role(role).all()
                except Exception:
                    continue
                for i, el in enumerate(els):
                    try:
                        text = ""
                        try:
                            text = (el.inner_text() or "").strip()
                        except Exception:
                            pass
                        attrs = {
                            "alt": el.get_attribute("alt") or "",
                            "title": el.get_attribute("title") or "",
                            "aria-label": el.get_attribute("aria-label") or "",
                            "id": el.get_attribute("id") or "",
                            "class": el.get_attribute("class") or "",
                        }
                        data = " ".join([text] + list(attrs.values()))
                        if pat.search(data):
                            print(f"  {label} {role}[{i}]: visible={el.is_visible()} text={text!r} attrs={attrs}")
                    except Exception as exc:
                        print(f"  {label} {role}[{i}]: error -> {exc}")
    print("--- Fin diagnóstico controles Vincular ---")


def click_vincular_nuevo_registro(context) -> None:
    wait_context(context, 1500)
    pat = re.compile(r"Vincular nuevo registro", re.I)
    last_error = None
    try:
        click_button_in_context(context, pat, "Vincular nuevo registro")
        return
    except Exception as exc:
        last_error = exc
        print(f"  click botón Vincular nuevo registro falló; probando fallback amplio: {exc}")

    for p in list(context.pages):
        targets = [("page", p)] + [(f"frame {f.name!r}", f) for f in p.frames]
        for label, target in targets:
            for role in ("link", "img"):
                try:
                    els = target.get_by_role(role, name=pat).all()
                except Exception as exc:
                    last_error = exc
                    continue
                for i, el in enumerate(els):
                    try:
                        if not el.is_visible():
                            continue
                        el.scroll_into_view_if_needed(timeout=5_000)
                        el.click(timeout=10_000, force=True)
                        print(f"  OK: Vincular nuevo registro en {label} role={role}[{i}]")
                        return
                    except Exception as exc:
                        last_error = exc
                        print(f"  fallback Vincular falló en {label} role={role}[{i}]: {exc}")

            try:
                clicked = target.evaluate(
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
                    print(f"  OK: Vincular nuevo registro (JS fallback en {label}: {clicked})")
                    wait_context(context, 1000)
                    return
            except Exception as exc:
                last_error = exc
                print(f"  JS fallback Vincular falló en {label}: {exc}")

    dump_vincular_controls(context)
    raise TimeoutError(f"No se pudo hacer clic en 'Vincular nuevo registro': {last_error}")


def dump_alejandro_options(context) -> None:
    print("--- Diagnóstico opciones Alejandro.Aguilar ---")
    pat = re.compile(r"Alejandro\.Aguilar", re.I)
    for p in list(context.pages):
        targets = [("page", p)] + [(f"frame {f.name!r}", f) for f in p.frames]
        for label, target in targets:
            try:
                matches = target.get_by_text(pat).all()
                if matches:
                    print(f"  {label}: get_by_text matches={len(matches)}")
            except Exception:
                pass
            for role in ("option", "listitem", "row", "cell", "gridcell"):
                try:
                    els = target.get_by_role(role, name=pat).all()
                except Exception:
                    continue
                if not els:
                    continue
                print(f"  {label}: role={role} matches={len(els)}")
                for i, el in enumerate(els[:10]):
                    try:
                        print(f"    [{i}] visible={el.is_visible()} text={(el.inner_text() or '').strip()!r}")
                    except Exception as exc:
                        print(f"    [{i}] error={exc}")
    print("--- Fin diagnóstico opciones Alejandro.Aguilar ---")


def click_alejandro_aguilar_option(context) -> None:
    pat = re.compile(r"Alejandro\.Aguilar", re.I)
    last_error = None
    for p in list(context.pages):
        targets = [("page", p)] + [(f"frame {f.name!r}", f) for f in p.frames]
        for label, target in targets:
            for role in ("option", "listitem", "row", "cell", "gridcell"):
                try:
                    els = target.get_by_role(role, name=pat).all()
                except Exception as exc:
                    last_error = exc
                    continue
                for i, el in enumerate(els):
                    try:
                        if not el.is_visible():
                            continue
                        el.scroll_into_view_if_needed(timeout=5_000)
                        el.click(timeout=10_000, force=True)
                        print(f"  OK: Alejandro.Aguilar en {label} role={role}[{i}]")
                        return
                    except Exception as exc:
                        last_error = exc
                        print(f"  click Alejandro.Aguilar falló en {label} role={role}[{i}]: {exc}")
            try:
                els = target.get_by_text(pat).all()
            except Exception as exc:
                last_error = exc
                continue
            for i, el in enumerate(els):
                try:
                    if not el.is_visible():
                        continue
                    el.scroll_into_view_if_needed(timeout=5_000)
                    el.click(timeout=10_000, force=True)
                    print(f"  OK: Alejandro.Aguilar por texto en {label}[{i}]")
                    return
                except Exception as exc:
                    last_error = exc
                    print(f"  click texto Alejandro.Aguilar falló en {label}[{i}]: {exc}")

            # Fallback ExtJS: el texto existe pero puede estar dentro de un dropdown oculto
            # o sin rol accesible. Clickeamos por DOM y, como último recurso, seteamos #X59.
            try:
                result = target.evaluate(
                    """() => {
                        const pat = /Alejandro[.]Aguilar/i;
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
                            field.value = 'Alejandro.Aguilar';
                            field.dispatchEvent(new Event('input', { bubbles: true }));
                            field.dispatchEvent(new Event('change', { bubbles: true }));
                            field.dispatchEvent(new Event('blur', { bubbles: true }));
                            return { ok: true, mode: 'set-X59', tag: field.tagName, id: field.id || '' };
                        }
                        return { ok: false };
                    }"""
                )
                if result and result.get("ok"):
                    print(f"  OK: Alejandro.Aguilar (JS fallback en {label}: {result})")
                    wait_context(context, 800)
                    return
            except Exception as exc:
                last_error = exc
                print(f"  JS fallback Alejandro.Aguilar falló en {label}: {exc}")
    dump_alejandro_options(context)
    raise TimeoutError(f"No se pudo seleccionar Alejandro.Aguilar: {last_error}")


def click_guardar_peticion(context) -> None:
    click_button_in_context(
        context,
        re.compile(r"Guardar \(Alt\+F1\)", re.I),
        "Guardar (Alt+F1)",
    )


def click_guardar_registro_y_salir(context) -> None:
    click_button_in_context(
        context,
        re.compile(r"Guardar registro y salir \(", re.I),
        "Guardar registro y salir (",
    )


def click_guardar_y_salir_final(context) -> None:
    wait_context(context, 1500)
    click_button_in_context(
        context,
        re.compile(r"Guardar y salir", re.I),
        "Guardar y salir",
    )
    wait_context(context, 1500)


def has_guardar_y_salir_visible(context) -> bool:
    pat = re.compile(r"Guardar y salir", re.I)
    for p in list(context.pages):
        targets = [("page", p)] + [(f"frame {f.name!r}", f) for f in p.frames]
        for _, target in targets:
            try:
                for btn in target.get_by_role("button", name=pat).all():
                    try:
                        if btn.is_visible():
                            return True
                    except Exception:
                        continue
            except Exception:
                continue
    return False


def close_visible_final_forms(context, max_clicks=3) -> None:
    for i in range(max_clicks):
        if not has_guardar_y_salir_visible(context):
            return
        print(f"  formulario abierto detectado antes de logout; cerrando con Guardar y salir ({i + 1}/{max_clicks})")
        click_guardar_y_salir_final(context)
    if has_guardar_y_salir_visible(context):
        print("  AVISO: sigue visible 'Guardar y salir' después de intentar cerrar formularios", file=sys.stderr)


def dump_logout_controls(context) -> None:
    print("--- Diagnóstico controles Logout ---")
    pat = re.compile(r"info|usuario|cerrar sesi[oó]n|logout|salir|\bs[ií]\b", re.I)
    for p in list(context.pages):
        targets = [("page", p)] + [(f"frame {f.name!r}", f) for f in p.frames]
        for label, target in targets:
            for role in ("button", "menuitem", "link"):
                try:
                    els = target.get_by_role(role).all()
                except Exception:
                    continue
                for i, el in enumerate(els):
                    try:
                        text = ""
                        try:
                            text = (el.inner_text() or "").strip()
                        except Exception:
                            pass
                        attrs = {
                            "aria-label": el.get_attribute("aria-label") or "",
                            "title": el.get_attribute("title") or "",
                            "id": el.get_attribute("id") or "",
                            "class": el.get_attribute("class") or "",
                        }
                        data = " ".join([text] + list(attrs.values()))
                        if pat.search(data):
                            print(f"  {label} {role}[{i}]: visible={el.is_visible()} text={text!r} attrs={attrs}")
                    except Exception as exc:
                        print(f"  {label} {role}[{i}]: error -> {exc}")
    print("--- Fin diagnóstico controles Logout ---")


def click_text_action(context, text_regex, label) -> None:
    last_error = None
    for p in list(context.pages):
        targets = [("page", p)] + [(f"frame {f.name!r}", f) for f in p.frames]
        for target_label, target in targets:
            for role in ("button", "menuitem", "link"):
                try:
                    els = target.get_by_role(role, name=text_regex).all()
                except Exception as exc:
                    last_error = exc
                    continue
                for i, el in enumerate(els):
                    try:
                        if not el.is_visible():
                            continue
                        el.click(timeout=10_000, force=True)
                        print(f"  OK: {label} en {target_label} role={role}[{i}]")
                        return
                    except Exception as exc:
                        last_error = exc
                        print(f"  click {label} falló en {target_label} role={role}[{i}]: {exc}")
            try:
                els = target.get_by_text(text_regex).all()
            except Exception as exc:
                last_error = exc
                continue
            for i, el in enumerate(els):
                try:
                    if not el.is_visible():
                        continue
                    el.click(timeout=10_000, force=True)
                    print(f"  OK: {label} por texto en {target_label}[{i}]")
                    return
                except Exception as exc:
                    last_error = exc
                    print(f"  click texto {label} falló en {target_label}[{i}]: {exc}")

            try:
                clicked = target.evaluate(
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
                    print(f"  OK: {label} (JS fallback en {target_label}: {clicked})")
                    return
            except Exception as exc:
                last_error = exc
                print(f"  JS fallback {label} falló en {target_label}: {exc}")
    dump_logout_controls(context)
    raise TimeoutError(f"No se pudo hacer clic en {label!r}: {last_error}")


def logout(page, context) -> None:
    print("=== CERRAR SESIÓN ===")
    close_visible_final_forms(context)
    page.get_by_role("button", name="Info. del usuario").click(timeout=10_000, force=True)
    print("  OK: Info. del usuario")
    wait_context(context, 1000)
    try:
        click_text_action(context, re.compile(r"Cerrar sesi[oó]n|logout", re.I), "Cerrar sesión")
    except Exception:
        if has_guardar_y_salir_visible(context):
            print("  'Cerrar sesión' no apareció porque queda un formulario abierto; cerrándolo y reintentando logout")
            close_visible_final_forms(context)
            page.get_by_role("button", name="Info. del usuario").click(timeout=10_000, force=True)
            print("  OK: Info. del usuario")
            wait_context(context, 1000)
            click_text_action(context, re.compile(r"Cerrar sesi[oó]n|logout", re.I), "Cerrar sesión")
        else:
            raise
    wait_context(context, 1000)
    click_text_action(context, re.compile(r"^S[ií]$", re.I), "Sí")


def dump_registros_relacionados_controls(frame) -> None:
    print("--- Diagnóstico controles Registros relacionados ---")
    for role in ("img", "button", "option"):
        try:
            els = frame.get_by_role(role).all()
            print(f"  role={role}: count={len(els)}")
        except Exception as exc:
            print(f"  role={role}: error {exc}")
            continue
        for i, el in enumerate(els[:25]):
            try:
                text = ""
                try:
                    text = (el.inner_text() or "").strip()
                except Exception:
                    pass
                attrs = {
                    "alt": el.get_attribute("alt") or "",
                    "title": el.get_attribute("title") or "",
                    "aria-label": el.get_attribute("aria-label") or "",
                    "id": el.get_attribute("id") or "",
                    "class": el.get_attribute("class") or "",
                }
                visible = el.is_visible()
                data = " ".join([text] + list(attrs.values()))
                if re.search(r"expand|lista|peticiones|vincular|guardar|salir", data, re.I):
                    print(f"    {role}[{i}]: visible={visible} text={text!r} attrs={attrs}")
            except Exception as exc:
                print(f"    {role}[{i}]: error {exc}")
    print("--- Fin diagnóstico controles ---")


def click_expandir_lista_registros(frame) -> None:
    strategies = [
        ("img role exact", lambda: frame.get_by_role("img", name="Expandir lista").first),
        ("button role exact", lambda: frame.get_by_role("button", name="Expandir lista").first),
        ("img alt", lambda: frame.locator('img[alt="Expandir lista"]').first),
        ("img title", lambda: frame.locator('img[title="Expandir lista"]').first),
        ("any title/alt expandir", lambda: frame.locator('img[alt*=\"Expandir\"], img[title*=\"Expandir\"], button[title*=\"Expandir\"]').first),
    ]
    last_error = None
    for label, make_loc in strategies:
        try:
            loc = make_loc()
            if loc.count() == 0:
                continue
            try:
                loc.scroll_into_view_if_needed(timeout=2_000)
            except Exception:
                pass
            loc.click(timeout=5_000, force=True)
            print(f"  OK: Expandir lista ({label})")
            return
        except Exception as exc:
            last_error = exc
            print(f"  Expandir lista falló con {label}: {exc}")

    # Fallback ExtJS: a veces el recorder ve un img oculto (#X113Button), pero el
    # evento útil está en el contenedor/anchor padre. Disparamos el click en JS.
    try:
        clicked = frame.evaluate(
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
            frame.wait_for_timeout(800)
            print(f"  OK: Expandir lista (JS fallback {clicked})")
            return
    except Exception as exc:
        last_error = exc
        print(f"  Expandir lista JS fallback falló: {exc}")

    dump_registros_relacionados_controls(frame)
    raise TimeoutError(f"No se pudo hacer clic en 'Expandir lista': {last_error}")


def vincular_peticion_relacionada(context) -> str:
    print("=== VINCULAR PETICIÓN RELACIONADA ===")
    frame, tab = find_registros_relacionados_frame(context)
    print(f"  pestaña encontrada en frame {frame.name!r} ({frame.url})")
    tab.click(timeout=10_000, force=True)
    print("  OK: Registros relacionados")
    frame.wait_for_timeout(1500)
    frame, _ = find_registros_relacionados_frame(context, timeout_ms=10_000)
    click_expandir_lista_registros(frame)
    frame.get_by_role("option", name="Peticiones relacionadas").click(timeout=10_000, force=True)
    print("  OK: Peticiones relacionadas")
    wait_context(context, 1000)
    click_vincular_nuevo_registro(context)
    print("  OK: Vincular nuevo registro")
    frame.locator("#X59ButtonDiv > .image-link").click(timeout=10_000, force=True)
    print("  OK: abrir selector de usuario")
    wait_context(context, 1000)
    click_alejandro_aguilar_option(context)
    click_guardar_peticion(context)
    print("  OK: Guardar petición")
    print("Buscando ID de la petición después de guardar...")
    peticion_id = get_peticion_id(context)
    click_guardar_registro_y_salir(context)
    print("  OK: Guardar registro y salir petición")
    click_guardar_y_salir_final(context)
    print("  OK: Guardar y salir formulario final")
    return peticion_id


def diagnostic_login_fields(page) -> None:
    for i, tb in enumerate(page.get_by_role("textbox").all()):
        print(
            f"textbox[{i}]: aria-label={tb.get_attribute('aria-label')!r} "
            f"name={tb.get_attribute('name')!r} placeholder={tb.get_attribute('placeholder')!r}"
        )
    print(f"Usuario resuelto: {USERNAME}")
    print(f"Contraseña resuelta: {PASSWORD[:3]}***")


def set_login_value(locator, value: str, label: str) -> None:
    """Set login inputs without depending on whichever field has focus.

    The portal sometimes steals focus during the first cold load. Using JS value
    assignment plus input/change events avoids the password being typed into the
    username field when focus jumps at the wrong time.
    """
    locator.wait_for(state="visible", timeout=TIMEOUT)
    locator.scroll_into_view_if_needed(timeout=TIMEOUT)
    locator.evaluate(
        """(el, value) => {
            el.focus();
            el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.blur();
        }""",
        value,
        timeout=TIMEOUT,
    )
    current_value = locator.input_value(timeout=TIMEOUT)
    if current_value != value:
        raise RuntimeError(
            f"No se pudo fijar {label}: esperado {value!r}, obtenido {current_value!r}"
        )


def fill_login_credentials(page) -> None:
    user_field = page.get_by_role("textbox", name="Nombre de usuario", exact=True).first
    password_field = page.get_by_role("textbox", name="Contraseña", exact=True).first

    set_login_value(user_field, USERNAME, "usuario")
    set_login_value(password_field, PASSWORD, "contraseña")

    # Defensa explícita contra el fallo intermitente observado: usuario y clave
    # terminan concatenados en el campo USER si el portal cambia foco tarde.
    user_value = user_field.input_value(timeout=TIMEOUT)
    password_value = password_field.input_value(timeout=TIMEOUT)
    if user_value != USERNAME or password_value != PASSWORD:
        set_login_value(user_field, USERNAME, "usuario")
        set_login_value(password_field, PASSWORD, "contraseña")


def login_and_open_section(context, page) -> None:
    page.goto(URL, timeout=TIMEOUT, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass

    diagnostic_login_fields(page)
    fill_login_credentials(page)
    page.get_by_role("button", name="Iniciar sesión").click()

    page.get_by_text("Centro de Servicios").click(timeout=TIMEOUT)
    page.get_by_role("treeitem", name="Crear nueva interacción").click(timeout=TIMEOUT)

    frame = click_servicios_internos(context, page)
    fill_interaction_form(frame, context)
    print("OK: formulario completado")
    click_guardar(page, context)
    print("OK: Guardar (Alt+F1)")
    print("Buscando ID de la interacción...")
    ticket_id = get_ticket_id(context)
    peticion_id = vincular_peticion_relacionada(context)
    print(f"Resumen IDs: interacción={ticket_id!r}, petición={peticion_id!r}")
    logout(page, context)


def main() -> int:
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    try:
        login_and_open_section(context, page)
        print("Flujo completado correctamente.")
    except Exception as exc:
        print(f"Ocurrió un error, pero el navegador queda abierto: {exc}", file=sys.stderr)

    print("El navegador queda abierto. Pulsa Ctrl+C en esta terminal para cerrarlo...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        context.close()
        browser.close()
        playwright.stop()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)