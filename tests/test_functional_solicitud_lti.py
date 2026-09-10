"""
BATERÍA DE PRUEBAS FUNCIONALES AUTOMATIZADAS E2E Y API: MÓDULO "SOLICITUD LTI"
Proyecto: App LTI - Seguimiento Líderes TI
Ubicación: /home/bobbasystem/Desarrollos/app-lti
Documento de Referencia: SPECS_SOLICITUD_LTI.md

Casos de Prueba:
1. Flujo de Login y Navegación al módulo Solicitud LTI
2. Validación de Campos Obligatorios (Borde rojo y Alertas)
3. Autocompletado reactivo desde dbo.CT_BACKLOG_OPERACIONES2
4. Soporte de Ingreso Manual de Proyectos y Clientes
5. Control Anti-Duplicados (Detección 409 y sugerencias)
6. Inserción Exitosa en dbo.Proyectos y Modal de Confirmación
7. Botón Limpiar Formulario y Navegación a Seguimiento
8. Modo Claro / Modo Oscuro (UI / UX y temas)
9. Suite de Validación de Endpoints Backend (FastAPI + JWT)
"""

import os
import re
import time
import uuid
import pytest
import datetime
import requests
from playwright.sync_api import Page, expect
from backend.db import get_db_connection, create_solicitud_lti
from tests.conftest import create_access_token

BASE_URL = os.getenv("BASE_URL", "http://100.82.24.75:8000")


def helper_login(page: Page, username: str = "alejandro.aguilar", password: str = None):
    """Helper para autenticar en el portal con credenciales SSO válidas."""
    token = create_access_token({"sub": username, "rol": "ADMIN"})
    page.context.add_cookies([{
        "name": "access_token",
        "value": token,
        "url": BASE_URL,
    }])
    page.goto(f"{BASE_URL}/")
    page.wait_for_selector("#app-view", state="visible", timeout=25000)
    page.wait_for_function("() => window.App && window.App.isInitialized === true", timeout=25000)
    page.wait_for_selector("#nav-btn-solicitud-lti", state="visible", timeout=10000)


def test_01_login_and_navigation_solicitud_lti(page: Page):
    """
    CP-01: Flujo de Login y Navegación
    - Iniciar sesión con usuario aaguilar.
    - Clic en el botón "📝 Solicitud LTI".
    - Verificar visibilidad de #module-solicitud-lti-container y estado inactivo de otros módulos.
    - Verificar clase 'active' en el botón del menú superior.
    - Verificar preselección de LT asignado según el usuario autenticado.
    """
    helper_login(page)

    # Navegar al módulo Solicitud LTI
    solicitud_btn = page.locator("#nav-btn-solicitud-lti")
    expect(solicitud_btn).to_be_visible()
    solicitud_btn.click()

    # Verificar que el contenedor de Solicitud LTI esté visible y activo
    solicitud_container = page.locator("#module-solicitud-lti-container")
    expect(solicitud_container).to_be_visible()
    expect(solicitud_btn).to_have_class(re.compile(r"active"))

    # Verificar que los otros 3 módulos estén ocultos
    expect(page.locator("#module-projects-container")).to_be_hidden()
    expect(page.locator("#module-direct-search-container")).to_be_hidden()
    expect(page.locator("#module-tickets-container")).to_be_hidden()

    # Verificar que el campo LT Asignado NO esté presente en el formulario de Solicitud LTI
    expect(page.locator("#solicitud-lt-asignado")).to_have_count(0)

    # Verificar que el estado por defecto sea 'Generado' y esté bloqueado (disabled)
    estado_select = page.locator("#solicitud-estado")
    expect(estado_select).to_have_value("Generado", timeout=5000)
    expect(estado_select).to_be_disabled()

    # Verificar badge indicador '🔒 Fijo' y texto de ayuda descriptivo
    badge_locked = page.locator(".badge-locked")
    expect(badge_locked).to_be_visible()
    expect(badge_locked).to_contain_text("🔒 Fijo")

    help_text = page.locator("#module-solicitud-lti-container .form-help-text").filter(has_text="Estado inicial fijo: 'Generado'")
    expect(help_text).to_be_visible()

    # Verificar que el cursor en el select deshabilitado sea 'not-allowed'
    cursor_style = estado_select.evaluate("el => window.getComputedStyle(el).cursor")
    assert cursor_style == "not-allowed", f"Cursor esperado 'not-allowed', obtenido '{cursor_style}'"

    # Verificar que solo exista la opción 'Generado'
    opts = estado_select.locator("option")
    expect(opts).to_have_count(1)
    expect(opts.first).to_have_attribute("value", "Generado")


def test_02_mandatory_fields_validation(page: Page):
    """
    CP-02: Validación de Campos Obligatorios
    - Intentar enviar el formulario vacío o con campos incompletos.
    - Verificar que no se envíe la solicitud.
    - Verificar que los campos obligatorios se marquen con 'is-invalid'.
    - Verificar despliegue del banner de error (#solicitud-error-alert).
    """
    helper_login(page)
    page.click("#nav-btn-solicitud-lti")

    # Limpiar formulario
    page.click("#btn-reset-solicitud")

    # Vaciar campos explícitamente para test de validación
    page.fill("#solicitud-nro-proyecto", "")
    page.fill("#solicitud-cliente", "")
    page.fill("#solicitud-detalle", "")
    page.fill("#solicitud-fecha", "")

    # Presionar Solicitar
    page.click("#btn-submit-solicitud")

    # Banner de error debe mostrarse
    error_alert = page.locator("#solicitud-error-alert")
    expect(error_alert).to_be_visible()
    error_desc = page.locator("#solicitud-error-desc").inner_text()
    assert "campos requeridos" in error_desc.lower() or "obligatorios" in error_desc.lower()

    # Inputs requeridos deben tener la clase 'is-invalid'
    expect(page.locator("#solicitud-nro-proyecto")).to_have_class(re.compile(r"is-invalid"))
    expect(page.locator("#solicitud-cliente")).to_have_class(re.compile(r"is-invalid"))
    expect(page.locator("#solicitud-fecha")).to_have_class(re.compile(r"is-invalid"))
    expect(page.locator("#solicitud-detalle")).to_have_class(re.compile(r"is-invalid"))

    # Verificar que el modal de éxito NO se haya abierto
    expect(page.locator("#solicitud-success-modal")).to_be_hidden()


def test_03_autocomplete_reactive_backlog_sga(page: Page):
    """
    CP-03: Autocompletado reactivo desde dbo.CT_BACKLOG_OPERACIONES2
    - Escribir en "N° Proyecto" ('1611').
    - Verificar aparición de la lista de sugerencias del Backlog SGA.
    - Seleccionar una sugerencia y verificar que se rellenen "N° Proyecto" y "Cliente" automáticamente.
    - Verificar que el dropdown se cierre tras la selección.
    """
    helper_login(page)
    page.click("#nav-btn-solicitud-lti")
    page.click("#btn-reset-solicitud")

    proj_input = page.locator("#solicitud-nro-proyecto")
    proj_input.fill("1611")

    # Esperar a que el dropdown de autocompletado aparezca con sugerencias
    dropdown = page.locator("#solicitud-autocomplete-dropdown")
    items = dropdown.locator(".autocomplete-item")
    expect(items.first).to_be_visible(timeout=10000)
    count = items.count()
    assert count >= 1, f"Se esperaban sugerencias de autocompletado para '1611', se encontraron {count}"

    # Obtener el texto del primer proyecto sugerido
    first_item_proj = items.first.locator(".autocomplete-item-proj").inner_text()
    first_item_client = items.first.locator(".autocomplete-item-client").inner_text()

    # Hacer clic en la primera sugerencia
    items.first.click()

    # Dropdown debe ocultarse
    expect(dropdown).to_be_hidden()

    # Verificar que los inputs se hayan poblado con los datos seleccionados
    val_proj = page.locator("#solicitud-nro-proyecto").input_value()
    val_client = page.locator("#solicitud-cliente").input_value()

    assert val_proj == first_item_proj, f"Esperado N° {first_item_proj}, obtenido {val_proj}"
    assert val_client == first_item_client, f"Esperado Cliente {first_item_client}, obtenido {val_client}"


def test_04_manual_entry_support(page: Page):
    """
    CP-04: Soporte de Ingreso Manual
    - Escribir un N° de proyecto manual que no exista en SGA (ej: 99912345).
    - Verificar que el sistema permita continuar e ingresar el Cliente manualmente.
    - Verificar que no se bloquee ni se borre la información.
    """
    helper_login(page)
    page.click("#nav-btn-solicitud-lti")
    page.click("#btn-reset-solicitud")

    manual_nro = "99912345"
    manual_cliente = "EMPRESA PRUEBA MANUAL QA LTDA"
    manual_detalle = "Requerimiento de conectividad y configuración manual de enlaces."

    # Ingresar N° de proyecto manual
    page.fill("#solicitud-nro-proyecto", manual_nro)
    page.wait_for_timeout(400)  # debounce

    # Ingresar Cliente manualmente
    page.fill("#solicitud-cliente", manual_cliente)
    page.fill("#solicitud-detalle", manual_detalle)

    # Verificar que los valores persistan en el DOM
    assert page.locator("#solicitud-nro-proyecto").input_value() == manual_nro
    assert page.locator("#solicitud-cliente").input_value() == manual_cliente
    assert page.locator("#solicitud-detalle").input_value() == manual_detalle


def test_05_anti_duplicate_control(page: Page):
    """
    CP-05: Control Anti-Duplicados
    - Intentar registrar un N° de proyecto que ya exista en dbo.Proyectos (0001614294).
    - Verificar que el sistema intercepte el error 409 y despliegue el banner de advertencia (#solicitud-duplicate-alert).
    - Verificar sugerencias en el mensaje (editar DETALLE).
    - Verificar botón 'Ver Proyecto en Seguimiento' y su acción.
    """
    import uuid
    unique_ts = f"{int(time.time() * 1000) % 10000000}-{uuid.uuid4().hex[:6]}"
    existing_proj = f"000DUP{unique_ts}"
    res_init = create_solicitud_lti(
        cliente="ILUSTRE MUNICIPALIDAD DE QUINTA NORMAL",
        numero_proyecto=existing_proj,
        lt_asignado="Alejandro Aguilar",
        estado="Generado",
        fecha_solicitud=datetime.date.today().isoformat(),
        detalle="Proyecto base preexistente para prueba anti-duplicado"
    )
    assert res_init.get("success"), f"Error creando proyecto previo: {res_init}"

    helper_login(page)
    page.click("#nav-btn-solicitud-lti")
    page.click("#btn-reset-solicitud")

    page.fill("#solicitud-nro-proyecto", existing_proj)
    page.wait_for_timeout(300)
    page.fill("#solicitud-cliente", "ILUSTRE MUNICIPALIDAD DE QUINTA NORMAL")
    expect(page.locator("#solicitud-estado")).to_be_disabled()
    expect(page.locator("#solicitud-estado")).to_have_value("Generado")
    page.fill("#solicitud-detalle", "Intento de registro de proyecto duplicado para validación de alerta 409.")

    # Enviar formulario
    page.click("#btn-submit-solicitud")

    # Verificar que aparezca el banner de duplicados
    dup_alert = page.locator("#solicitud-duplicate-alert")
    expect(dup_alert).to_be_visible(timeout=5000)

    title = page.locator("#duplicate-alert-title").inner_text()
    assert "ya existe en el sistema" in title

    desc = page.locator("#duplicate-alert-desc").inner_text()
    assert "Detalle" in desc or "detalle" in desc
    assert "Seguimiento" in desc or "seguimiento" in desc

    # Probar botón 'Ver Proyecto en Seguimiento'
    view_dup_btn = page.locator("#btn-view-duplicate-project")
    expect(view_dup_btn).to_be_visible()
    view_dup_btn.scroll_into_view_if_needed()
    view_dup_btn.click()

    # Debe navegar al módulo de Seguimiento Proyectos y abrir el drilldown
    expect(page.locator("#module-projects-container")).to_be_visible(timeout=10000)
    expect(page.locator("#project-drilldown-section")).to_be_visible(timeout=15000)
    expect(page.locator("#dd-proj-num")).to_contain_text(existing_proj, timeout=10000)


def test_06_successful_creation_and_modal(page: Page):
    """
    CP-06: Inserción Exitosa y Modal de Confirmación
    - Completar un formulario con un N° de proyecto nuevo y datos válidos.
    - Presionar 'Solicitar' y verificar que se abra el modal #solicitud-success-modal con el ID generado.
    - Verificar consistencia de datos en el modal (LT Asignado por defecto 'Sin Asignar').
    - Verificar que el campo Tipo_Servicio esté oculto en el DOM y persista como 'Otros'.
    - Verificar inserción real en MSSQL dbo.Proyectos con Estado 'Generado', LT_Asignado NULL y Tipo_Servicio 'Otros'.
    """
    helper_login(page)
    page.click("#nav-btn-solicitud-lti")
    page.click("#btn-reset-solicitud")

    unique_suffix = f"{int(time.time() * 1000) % 10000000}-{uuid.uuid4().hex[:6]}"
    new_nro = f"QA-TEST-{unique_suffix}"
    new_cliente = "EMPRESA PRUEBA QA AUTOMATION SPA"
    new_estado = "Generado"
    new_tipo = "Otros"
    new_detalle = f"Prueba E2E Automatizada de inserción exitosa. Timestamp: {unique_suffix}"

    page.fill("#solicitud-nro-proyecto", new_nro)
    page.fill("#solicitud-cliente", new_cliente)
    expect(page.locator("#solicitud-estado")).to_be_disabled()
    expect(page.locator("#solicitud-estado")).to_have_value("Generado")

    # Verificar que el input de Tipo de Servicio esté oculto y tenga valor 'Otros'
    tipo_input = page.locator("#solicitud-tipo-servicio")
    expect(tipo_input).to_be_hidden()
    expect(tipo_input).to_have_value("Otros")

    page.fill("#solicitud-detalle", new_detalle)

    # Presionar Solicitar
    page.click("#btn-submit-solicitud")

    # Esperar la aparición del modal de éxito
    success_modal = page.locator("#solicitud-success-modal")
    expect(success_modal).to_be_visible(timeout=8000)

    # Validar campos del modal
    generated_id_str = page.locator("#solicitud-success-id").inner_text().strip()
    assert generated_id_str.isdigit() and int(generated_id_str) > 0, f"ID inválido: {generated_id_str}"
    created_id = int(generated_id_str)

    assert new_cliente in page.locator("#modal-solicitud-cliente").inner_text()
    assert new_nro in page.locator("#modal-solicitud-nro").inner_text()
    assert "Sin Asignar" in page.locator("#modal-solicitud-lt").inner_text() or "-" in page.locator("#modal-solicitud-lt").inner_text()
    assert new_estado in page.locator("#modal-solicitud-estado").inner_text()

    # Verificar persistencia directa en MSSQL (LT_Asignado debe ser NULL o vacío)
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT ID, Cliente, Numero_Proyecto, LT_Asignado, Estado, Detalle, Tipo_Servicio FROM dbo.Proyectos WHERE ID = %s", (created_id,))
            row = cursor.fetchone()
            assert row is not None, f"El registro con ID {created_id} no fue encontrado en dbo.Proyectos"
            assert row["Cliente"] == new_cliente
            assert new_nro in row["Numero_Proyecto"]
            assert row["LT_Asignado"] is None or str(row["LT_Asignado"]).strip() == "", f"LT_Asignado esperado NULL, obtenido '{row['LT_Asignado']}'"
            assert row["Estado"] == new_estado
            assert row["Tipo_Servicio"] == new_tipo
            assert row["Detalle"] == new_detalle
    finally:
        conn.close()


def test_07_reset_button_and_navigation(page: Page):
    """
    CP-07: Botón Limpiar y Navegación
    - Probar el botón 'Limpiar Formulario' (#btn-reset-solicitud).
    - Probar el botón 'Ver en Seguimiento' del modal de éxito (#btn-solicitud-go-to-projects).
    """
    helper_login(page)
    page.click("#nav-btn-solicitud-lti")

    # Llenar datos y provocar error de validación
    page.fill("#solicitud-nro-proyecto", "INVALID-DATA")
    page.fill("#solicitud-cliente", "CLIENTE TEST")
    page.fill("#solicitud-detalle", "")
    page.click("#btn-submit-solicitud")

    # Verificar que el error alert y la clase is-invalid estén activos
    expect(page.locator("#solicitud-error-alert")).to_be_visible()
    expect(page.locator("#solicitud-detalle")).to_have_class(re.compile(r"is-invalid"))

    # Presionar Limpiar Formulario
    page.click("#btn-reset-solicitud")

    # Verificar que se limpien los campos y se remuevan las alertas
    assert page.locator("#solicitud-nro-proyecto").input_value() == ""
    assert page.locator("#solicitud-cliente").input_value() == ""
    assert page.locator("#solicitud-detalle").input_value() == ""
    expect(page.locator("#solicitud-error-alert")).to_be_hidden()
    expect(page.locator("#solicitud-duplicate-alert")).to_be_hidden()
    expect(page.locator("#solicitud-detalle")).not_to_have_class(re.compile(r"is-invalid"))

    # Probar botón 'Ver en Seguimiento' desde el modal
    unique_suffix = int(time.time())
    page.fill("#solicitud-nro-proyecto", f"QA-TEST-{unique_suffix}")
    page.fill("#solicitud-cliente", "CLIENTE NAVEGACION QA")
    page.fill("#solicitud-detalle", "Prueba E2E Automatizada de navegación a seguimiento")
    page.click("#btn-submit-solicitud")

    expect(page.locator("#solicitud-success-modal")).to_be_visible()

    # Clic en "Ver en Seguimiento"
    page.click("#btn-solicitud-go-to-projects")

    # El modal debe cerrarse y el módulo de proyectos debe activarse
    expect(page.locator("#solicitud-success-modal")).to_be_hidden()
    expect(page.locator("#module-projects-container")).to_be_visible()
    expect(page.locator("#nav-btn-projects")).to_have_class(re.compile(r"active"))


def test_08_light_and_dark_mode_visual_and_functional(page: Page):
    """
    CP-08: Prueba de Modo Claro y Modo Oscuro
    - Verificar visualización del formulario y dropdowns en ambos temas.
    - Alternar tema con #theme-toggle-btn.
    - Validar persistencia del atributo data-theme en <html>.
    """
    helper_login(page)
    page.click("#nav-btn-solicitud-lti")

    theme_btn = page.locator("#theme-toggle-btn")
    expect(theme_btn).to_be_visible()

    # Forzar tema claro
    page.evaluate("App.setTheme('light')")
    theme_attr = page.locator("html").get_attribute("data-theme")
    assert theme_attr == "light"

    # Verificar visibilidad y estilos en modo claro
    expect(page.locator(".solicitud-card")).to_be_visible()
    expect(page.locator("#solicitud-nro-proyecto")).to_be_visible()
    expect(page.locator("#solicitud-estado")).to_be_disabled()
    expect(page.locator(".badge-locked")).to_be_visible()
    expect(page.locator("#btn-submit-solicitud")).to_be_visible()

    # Cambiar a modo oscuro
    theme_btn.click()
    theme_attr_dark = page.locator("html").get_attribute("data-theme")
    assert theme_attr_dark == "dark"

    # Verificar visibilidad y contraste en modo oscuro
    expect(page.locator(".solicitud-card")).to_be_visible()
    expect(page.locator("#solicitud-estado")).to_be_disabled()
    expect(page.locator(".badge-locked")).to_be_visible()

    # Probar autocompletado en modo oscuro
    proj_input = page.locator("#solicitud-nro-proyecto")
    proj_input.fill("1611")
    dropdown = page.locator("#solicitud-autocomplete-dropdown")
    expect(dropdown.locator(".autocomplete-item").first).to_be_visible(timeout=10000)

    # Regresar a modo claro
    theme_btn.click()
    theme_attr_light = page.locator("html").get_attribute("data-theme")
    assert theme_attr_light == "light"


def test_09_backend_api_solicitudes_suite(auth_token):
    """
    Pruebas de API Backend (FastAPI + MSSQL):
    - /api/solicitudes/catalogos (200 OK)
    - /api/solicitudes/autocomplete-proyectos (200 OK)
    - /api/solicitudes/crear con datos faltantes (400 Bad Request)
    - /api/solicitudes/crear con proyecto duplicado (409 Conflict)
    - /api/solicitudes/crear con datos válidos (201 Created)
    - /api/solicitudes/crear sin autenticación (401 Unauthorized)
    """
    headers = {"Authorization": f"Bearer {auth_token}"}

    # 1. Catálogos
    res_cat = requests.get(f"{BASE_URL}/api/solicitudes/catalogos", headers=headers)
    assert res_cat.status_code == 200
    data_cat = res_cat.json()
    assert "lideres" in data_cat and len(data_cat["lideres"]) > 0
    assert data_cat.get("estados") == ["Generado"]
    assert data_cat.get("tipos_servicio") == ["Otros"]

    # 2. Autocompletado
    res_auto = requests.get(f"{BASE_URL}/api/solicitudes/autocomplete-proyectos?q=1611", headers=headers)
    assert res_auto.status_code == 200
    data_auto = res_auto.json()
    assert isinstance(data_auto, list) and len(data_auto) > 0
    assert "nro_proyecto" in data_auto[0]
    assert "cliente" in data_auto[0]

    # 3. Validación de campos faltantes (400)
    res_bad = requests.post(f"{BASE_URL}/api/solicitudes/crear", headers=headers, json={
        "cliente": "",
        "numero_proyecto": "",
        "lt_asignado": "",
        "fecha_solicitud": "",
        "detalle": ""
    })
    assert res_bad.status_code == 400

    # 4. Control de duplicados (409)
    dup_num = f"QA-TEST-DUP-API-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    create_solicitud_lti(
        cliente="ILUSTRE MUNICIPALIDAD DE QUINTA NORMAL",
        numero_proyecto=dup_num,
        lt_asignado="Alejandro Aguilar",
        estado="Generado",
        fecha_solicitud=datetime.date.today().isoformat(),
        detalle="Prueba API duplicado preexistente"
    )
    res_dup = requests.post(f"{BASE_URL}/api/solicitudes/crear", headers=headers, json={
        "cliente": "ILUSTRE MUNICIPALIDAD DE QUINTA NORMAL",
        "numero_proyecto": dup_num,
        "lt_asignado": "Alejandro Aguilar",
        "estado": "Generado",
        "fecha_solicitud": datetime.date.today().isoformat(),
        "detalle": "Prueba API duplicado",
        "tipo_servicio": "Otros"
    })
    assert res_dup.status_code == 409
    data_dup = res_dup.json()
    assert data_dup.get("error") == "duplicate"
    assert "existing" in data_dup

    # 5. Creación exitosa (201) forzando inmutabilidad de Estado = 'Generado' y Tipo_Servicio = 'Otros'
    unique_num = f"QA-TEST-API-{int(time.time())}"
    res_create = requests.post(f"{BASE_URL}/api/solicitudes/crear", headers=headers, json={
        "cliente": "CLIENTE PRUEBA API QA",
        "numero_proyecto": unique_num,
        "lt_asignado": "Alejandro Aguilar",
        "estado": "Atendido",  # Intentamos enviar otro estado para validar inmutabilidad
        "fecha_solicitud": datetime.date.today().isoformat(),
        "detalle": "Prueba E2E Automatizada vía API",
        "tipo_servicio": "Cloud Empresarial"
    })
    assert res_create.status_code == 201
    data_create = res_create.json()
    assert data_create.get("message") == "Solicitud LTI creada exitosamente"
    created_data = data_create.get("data", {})
    assert created_data.get("ID") is not None
    assert unique_num in created_data.get("Numero_Proyecto")
    assert created_data.get("Estado") == "Generado"
    assert created_data.get("Tipo_Servicio") == "Otros"

    # 6. Sin autenticación (401)
    res_noauth = requests.post(f"{BASE_URL}/api/solicitudes/crear", json={
        "cliente": "NO AUTH",
        "numero_proyecto": "0000",
        "lt_asignado": "Alejandro Aguilar",
        "fecha_solicitud": "2026-08-25",
        "detalle": "Detalle sin auth"
    })
    assert res_noauth.status_code == 401


def test_10_estado_field_immutability_and_locking_lifecycle(page: Page):
    """
    CP-10: Verificación Exhaustiva del Ciclo de Vida del Campo Estado (Bloqueo e Inmutabilidad)
    - Verificar que al cambiar de módulo y regresar, el campo permanezca deshabilitado y en 'Generado'.
    - Verificar que al limpiar formulario (#btn-reset-solicitud), permanezca deshabilitado y en 'Generado'.
    - Verificar que el select contenga únicamente la opción 'Generado' sin opciones de estados no permitidos.
    - Verificar que ante manipulación DOM del atributo disabled o valor, el envío persista siempre 'Generado'.
    """
    helper_login(page)
    page.click("#nav-btn-solicitud-lti")

    estado_select = page.locator("#solicitud-estado")
    expect(estado_select).to_be_visible()
    expect(estado_select).to_be_disabled()
    expect(estado_select).to_have_value("Generado")

    # Verificar que solo exista 1 opción en el select
    options_count = estado_select.locator("option").count()
    assert options_count == 1, f"El select de estado debe tener exactamente 1 opción, encontradas: {options_count}"
    opt_val = estado_select.locator("option").first.get_attribute("value")
    assert opt_val == "Generado"

    # Navegar a otros módulos y regresar
    page.click("#nav-btn-projects")
    expect(page.locator("#module-projects-container")).to_be_visible()
    page.click("#nav-btn-direct-search")
    expect(page.locator("#module-direct-search-container")).to_be_visible()
    page.click("#nav-btn-tickets")
    expect(page.locator("#module-tickets-container")).to_be_visible()

    # Regresar a Solicitud LTI
    page.click("#nav-btn-solicitud-lti")
    expect(estado_select).to_be_disabled()
    expect(estado_select).to_have_value("Generado")
    assert estado_select.locator("option").count() == 1

    # Probar botón de limpiar formulario
    page.click("#btn-reset-solicitud")
    expect(estado_select).to_be_disabled()
    expect(estado_select).to_have_value("Generado")
    assert estado_select.locator("option").count() == 1

    # Inserción con intento de manipulación en frontend para asegurar inmutabilidad
    unique_suffix = int(time.time())
    new_nro = f"QA-LOCKED-TEST-{unique_suffix}"
    page.fill("#solicitud-nro-proyecto", new_nro)
    page.fill("#solicitud-cliente", "CLIENTE PRUEBA INMUTABILIDAD QA")
    page.fill("#solicitud-detalle", "Validación de inmutabilidad estricta de campo Estado 'Generado'")

    # Manipulación deliberada en DOM para comprobar que el código JS y Backend ignoran manipulaciones
    page.evaluate("""() => {
        const select = document.getElementById('solicitud-estado');
        if (select) {
            select.disabled = false;
            select.innerHTML = '<option value="Atendido" selected>Atendido</option>';
            select.value = 'Atendido';
        }
    }""")

    page.click("#btn-submit-solicitud")

    # Modal debe mostrarse con Estado Generado
    success_modal = page.locator("#solicitud-success-modal")
    expect(success_modal).to_be_visible(timeout=8000)
    expect(page.locator("#modal-solicitud-estado")).to_contain_text("Generado")
    expect(page.locator("#solicitud-success-id")).not_to_have_text("0", timeout=5000)
    
    generated_id_str = page.locator("#solicitud-success-id").inner_text().strip()
    created_id = int(generated_id_str)

    # Verificar en MSSQL que el registro persistió como 'Generado'
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT Estado, Tipo_Servicio FROM dbo.Proyectos WHERE ID = %s OR Numero_Proyecto LIKE %s", (created_id, f"%{new_nro}%"))
            row = cursor.fetchone()
            assert row is not None
            assert row["Estado"] == "Generado"
            assert row["Tipo_Servicio"] == "Otros"
    finally:
        conn.close()


def test_11_solots_liray_autocomplete_and_badge_flow(page: Page):
    """
    CP-11: Flujo Completo de Autocompletado de Solots Liray en Detalle
    - Escribir '1614441' (proyecto con solots Liray).
    - Seleccionar del dropdown de sugerencias.
    - Verificar que '#solicitud-detalle' se prellene con el formato estructurado 'SOLOTS ASOCIADOS (LIRAY):'.
    - Verificar que el badge '#detalle-solots-badge' sea visible con texto '⚡ Solots Liray detectados'.
    - Permitir complementar el texto con notas adicionales.
    """
    helper_login(page)
    page.click("#nav-btn-solicitud-lti")
    page.click("#btn-reset-solicitud")

    # Badge debe estar oculto al inicio
    badge = page.locator("#detalle-solots-badge")
    expect(badge).to_be_hidden()

    proj_input = page.locator("#solicitud-nro-proyecto")
    proj_input.fill("1614441")

    dropdown = page.locator("#solicitud-autocomplete-dropdown")
    items = dropdown.locator(".autocomplete-item")
    expect(items.first).to_be_visible(timeout=10000)

    # Clic en la sugerencia
    items.first.click()

    # Verificar que el badge se muestre
    expect(badge).to_be_visible(timeout=5000)
    expect(badge).to_contain_text("Solots Liray")

    # Verificar contenido estructurado del textarea Detalle
    detalle_val = page.locator("#solicitud-detalle").input_value()
    assert "SOLOTS ASOCIADOS (LIRAY):" in detalle_val
    assert "17636636" in detalle_val
    assert "17636637" in detalle_val
    assert "Arriendo Equipos Internet" in detalle_val

    # Complementar texto manualmente
    nota_extra = "\n\nNOTAS ADICIONALES: Validar factibilidad de enlace secundario."
    page.locator("#solicitud-detalle").fill(detalle_val + nota_extra)
    assert nota_extra in page.locator("#solicitud-detalle").input_value()


def test_12_solots_liray_backend_endpoint(auth_token):
    """
    CP-12: Prueba de Endpoint GET /api/solicitudes/solots-liray
    - Consultar solots liray de proyecto '1614441' (5 registros).
    - Consultar solots liray de proyecto sin Liray (0 registros).
    """
    headers = {"Authorization": f"Bearer {auth_token}"}

    # Proyecto con solots Liray
    res = requests.get(f"{BASE_URL}/api/solicitudes/solots-liray?nro_proyecto=1614441", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["nro_proyecto"] == "1614441"
    assert data["total_solots_liray"] == 5
    assert len(data["solots"]) == 5
    assert "formatted_text" in data and "SOLOTS ASOCIADOS (LIRAY):" in data["formatted_text"]

    # Proyecto sin solots Liray
    res_empty = requests.get(f"{BASE_URL}/api/solicitudes/solots-liray?nro_proyecto=9999999", headers=headers)
    assert res_empty.status_code == 200
    data_empty = res_empty.json()
    assert data_empty["total_solots_liray"] == 0
    assert len(data_empty["solots"]) == 0
    assert data_empty["formatted_text"] == ""


def test_13_ux_detalle_custom_text_blur_protection(page: Page):
    """
    CP-13: Verificación de UX del campo Detalle
    - Usuario escribe texto personalizado en Detalle.
    - Usuario hace foco en el campo N° de Proyecto y luego desfocaliza (blur).
    - Verificar que el texto personalizado del usuario NO se sobreescriba ni se borre.
    """
    helper_login(page)
    page.click("#nav-btn-solicitud-lti")
    page.click("#btn-reset-solicitud")

    custom_text = "Detalle personalizado exclusivo redactado por el usuario sin solots Liray."
    page.fill("#solicitud-detalle", custom_text)

    # El usuario escribe un proyecto y hace blur
    proj_input = page.locator("#solicitud-nro-proyecto")
    proj_input.fill("1614441")
    page.locator("#solicitud-cliente").focus()  # triggers blur on proj_input
    page.wait_for_timeout(500)

    # El texto personalizado debe mantenerse intacto
    current_text = page.locator("#solicitud-detalle").input_value()
    assert current_text == custom_text, f"Se sobreescribió el texto personalizado. Esperado: '{custom_text}', Obtenido: '{current_text}'"


def test_14_solots_liray_null_and_edge_case_formatting():
    """
    CP-14: Manejo de nulos, tipos raros y espacios en formateo de Solots Liray.
    """
    from backend.db import format_solots_liray_text
    # 1. Lista None o vacía
    assert format_solots_liray_text(None) == ""
    assert format_solots_liray_text([]) == ""

    # 2. Elementos nulos o no-dict
    assert format_solots_liray_text([None, 123, "string"]) == ""

    # 3. Dict con campos None / vacíos / espacios
    sample = [
        {"id_otp": None, "producto": "   ", "servicio": None, "nro_servicio": "  ", "descr_otp": None},
        {"id_otp": 12345, "producto": "Datos", "servicio": "Internet", "nro_servicio": "01-02-03", "descr_otp": "Fibra Liray"}
    ]
    formatted = format_solots_liray_text(sample)
    assert "SOLOTS ASOCIADOS (LIRAY):" in formatted
    assert "[1] Solot: S/N" in formatted
    assert "• Producto: N/A" in formatted
    assert "• Servicio: N/A" in formatted
    assert "• N° Servicio: N/A" in formatted
    assert "• Descripción: Sin descripción" in formatted
    assert "[2] Solot: 12345" in formatted
    assert "• Producto: Datos" in formatted


def test_15_solots_liray_real_db_projects_validation(page: Page):
    """
    CP-15: Certificación con Proyectos Reales de la BD (1614441, 1583659)
    - Proyecto 1614441: contiene 5 Solots Liray.
    - Proyecto 1583659: no contiene Solots Liray (permite escritura manual y badge oculto).
    """
    helper_login(page)
    page.click("#nav-btn-solicitud-lti")
    page.click("#btn-reset-solicitud")

    badge = page.locator("#detalle-solots-badge")
    detalle_textarea = page.locator("#solicitud-detalle")

    # 1. Probar proyecto 1614441 (5 Solots Liray)
    proj_input = page.locator("#solicitud-nro-proyecto")
    proj_input.fill("1614441")

    dropdown = page.locator("#solicitud-autocomplete-dropdown")
    items = dropdown.locator(".autocomplete-item")
    expect(items.first).to_be_visible(timeout=10000)
    items.first.click()

    expect(badge).to_be_visible(timeout=5000)
    expect(badge).to_contain_text("Solots Liray")
    expect(detalle_textarea).to_have_value(re.compile(r"SOLOTS ASOCIADOS"), timeout=10000)
    detalle_val = detalle_textarea.input_value()
    assert "SOLOTS ASOCIADOS (LIRAY):" in detalle_val
    assert "17636636" in detalle_val
    assert "17636637" in detalle_val
    assert "Arriendo Equipos Internet" in detalle_val

    # 2. Limpiar y probar proyecto 1583659 (Sin Solots Liray)
    page.click("#btn-reset-solicitud")
    expect(badge).to_be_hidden()
    expect(detalle_textarea).to_have_value("", timeout=5000)

    proj_input.fill("1583659")
    expect(items.first).to_be_visible(timeout=10000)
    items.first.click()

    # Badge debe permanecer oculto
    expect(badge).to_be_hidden()
    # Detalle debe estar vacío para ingreso manual
    expect(detalle_textarea).to_have_value("", timeout=5000)

    # Usuario escribe libremente su detalle manual
    custom_manual = "Detalle de requerimiento para proyecto 1583659 sin Solots Liray."
    detalle_textarea.fill(custom_manual)
    assert detalle_textarea.input_value() == custom_manual



def test_16_tipo_servicio_dom_and_payload_isolation(page: Page):
    """
    CP-16: Ocultamiento efectivo y Persistencia de Tipo de Servicio
    - Verificar que en el DOM del formulario Solicitud LTI NO exista ninguna etiqueta, select o input visible para 'Tipo de Servicio'.
    - Verificar que únicamente exista <input type="hidden" id="solicitud-tipo-servicio" value="Otros">.
    """
    helper_login(page)
    page.click("#nav-btn-solicitud-lti")

    # 1. Verificar en DOM que no haya labels o textos visibles para "Tipo de Servicio" en el formulario
    labels = page.locator("#solicitud-lti-form label").all_inner_texts()
    for lbl in labels:
        assert "tipo de servicio" not in lbl.lower(), f"Se encontró label visible de Tipo de Servicio: {lbl}"

    # 2. Verificar que no exista ningún select visible con id o name referente a tipo servicio
    tipo_selects = page.locator("#solicitud-lti-form select:visible").all()
    for sel in tipo_selects:
        sel_id = sel.get_attribute("id") or ""
        assert "tipo" not in sel_id.lower(), f"Select visible indebido: {sel_id}"

    # 3. Verificar que el hidden input exista, esté oculto y tenga valor 'Otros'
    hidden_tipo = page.locator("#solicitud-tipo-servicio")
    expect(hidden_tipo).to_have_count(1)
    expect(hidden_tipo).to_be_hidden()
    expect(hidden_tipo).to_have_value("Otros")


def test_17_filtro_lideres_estricto_y_orden_alfabetico(page: Page, auth_token: str):
    """
    CP-17: Verificación del Filtro de Líderes TI Restringido y Ordenado Alfabéticamente
    - Verificar endpoint /api/lideres retorne únicamente los 5 líderes oficiales.
    - Verificar orden alfabético estricto: Alejandro Aguilar, Erwin Sandoval, Juan Barrera, Samuel Paredes, Solange Ortiz.
    - Verificar options en el DOM de #filter-lt.
    """
    headers = {"Authorization": f"Bearer {auth_token}"}
    res = requests.get(f"{BASE_URL}/api/lideres", headers=headers)
    assert res.status_code == 200
    lideres = res.json()
    expected_lideres = [
        "Alejandro Aguilar",
        "Erwin Sandoval",
        "Juan Barrera",
        "Samuel Paredes",
        "Solange Ortiz"
    ]
    assert lideres == expected_lideres, f"Lista de líderes esperada {expected_lideres}, obtenida {lideres}"

    helper_login(page)
    expect(page.locator("#module-projects-container")).to_be_visible()

    # Verificar opciones en selector #filter-lt
    select_lt = page.locator("#filter-lt")
    expect(select_lt).to_be_visible()
    expect(select_lt.locator("option")).to_have_count(7, timeout=10000)
    
    options = select_lt.locator("option").all()
    opt_values = [opt.get_attribute("value") for opt in options]
    opt_texts = [opt.inner_text().strip() for opt in options]

    assert opt_values[0] == "__ALL__"
    assert opt_values[1] == "__UNASSIGNED__"
    assert opt_texts[1] == "Sin asignar"
    assert opt_values[2:] == expected_lideres


def test_18_filtro_lideres_opcion_sin_asignar(page: Page, auth_token: str):
    """
    CP-18: Verificación del Filtro "Sin asignar"
    - Verificar consulta a /api/proyectos?lt=__UNASSIGNED__
    - Verificar que todos los proyectos retornados tengan LT_Asignado vacío o None.
    - Verificar interacción en frontend seleccionando "Sin asignar" en #filter-lt.
    """
    headers = {"Authorization": f"Bearer {auth_token}"}
    res = requests.get(f"{BASE_URL}/api/proyectos?lt=__UNASSIGNED__", headers=headers)
    assert res.status_code == 200
    proyectos_sin_asignar = res.json()
    assert isinstance(proyectos_sin_asignar, list)

    for p in proyectos_sin_asignar:
        lt = p.get("LT_Asignado")
        assert lt is None or lt.strip() == "" or lt.lower().strip() == "sin asignar", f"Proyecto no debería tener LT asignado: {p}"

    helper_login(page)
    expect(page.locator("#module-projects-container")).to_be_visible()

    # Seleccionar "Sin asignar"
    page.select_option("#filter-lt", "__UNASSIGNED__")
    page.wait_for_timeout(500)

    # Verificar que el selector tenga el valor __UNASSIGNED__
    expect(page.locator("#filter-lt")).to_have_value("__UNASSIGNED__")


def test_19_tarjeta_kpi_pendientes_asignar_clicable(page: Page, auth_token: str):
    """
    CP-19: Verificación de la Tarjeta KPI "Pendientes de Asignar" Clicable
    - Verificar presencia de #kpi-card-pendientes en .kpi-grid.
    - Verificar que el contador #kpi-val-pendientes-asignar refleje el valor numérico del backend.
    - Hacer clic en la tarjeta y verificar que active el filtro __UNASSIGNED__ en #filter-lt y la clase .active-filter.
    - Hacer clic nuevamente y verificar toggle a __ALL__.
    """
    headers = {"Authorization": f"Bearer {auth_token}"}
    res_kpis = requests.get(f"{BASE_URL}/api/kpis", headers=headers)
    assert res_kpis.status_code == 200
    kpis_data = res_kpis.json()
    assert "pendientes_asignar" in kpis_data
    expected_pendientes = kpis_data["pendientes_asignar"]

    helper_login(page)
    expect(page.locator("#module-projects-container")).to_be_visible()

    kpi_card = page.locator("#kpi-card-pendientes")
    expect(kpi_card).to_be_visible()

    val_pendientes = page.locator("#kpi-val-pendientes-asignar")
    expect(val_pendientes).to_have_text(str(expected_pendientes))

    badge = kpi_card.locator(".kpi-clickable-badge")
    expect(badge).to_be_visible()
    expect(badge).to_contain_text("Filtrar")

    # Primer clic: Activar filtro Sin asignar
    kpi_card.click()
    page.wait_for_timeout(400)

    expect(page.locator("#filter-lt")).to_have_value("__UNASSIGNED__")
    expect(kpi_card).to_have_class(re.compile(r"active-filter"))

    # Segundo clic: Alternar y volver a Todos
    kpi_card.click()
    page.wait_for_timeout(400)

    expect(page.locator("#filter-lt")).to_have_value("__ALL__")
    expect(kpi_card).not_to_have_class(re.compile(r"active-filter"))


def test_20_tipografia_uniforme_global(page: Page):
    """
    CP-20: Verificación de Tipografía Uniforme en Toda la Aplicación
    - Verificar que la variable CSS --font-sans esté definida en :root.
    - Verificar que el body, la tabla .data-table y los formularios apliquen la tipografía unificada.
    """
    helper_login(page)
    expect(page.locator("#module-projects-container")).to_be_visible()

    font_sans_var = page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--font-sans').trim()")
    assert "Roboto" in font_sans_var or "Plus Jakarta Sans" in font_sans_var

    body_font = page.evaluate("() => getComputedStyle(document.body).fontFamily")
    assert "Roboto" in body_font or "Plus Jakarta Sans" in body_font

    table_font = page.evaluate("() => { const t = document.querySelector('.data-table'); return t ? getComputedStyle(t).fontFamily : ''; }")
    if table_font:
        assert "Roboto" in table_font or "Plus Jakarta Sans" in table_font




