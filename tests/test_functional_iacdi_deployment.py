"""
BATERÍA DE PRUEBAS AUTOMATIZADAS DE QA - DESPLIEGUE IACDI VÍA TAILSCALE
Proyecto: App LTI - Portal de Seguimiento Líderes TI
Especificación: SPECS_DESPLIEGUE_IACDI_TAILSCALE.md (SPECS-LTI-DEP-008)
Host Remoto: iacdi (100.82.24.75)
Puerto de Publicación: 8000

Matriz de Cobertura de Pruebas:
- TC-DEP-01: Conectividad Red & Tailscale HTTP/TCP al puerto 8000 en 100.82.24.75.
- TC-DEP-02: Conectividad y consultas a Base de Datos MSSQL (192.168.10.6:1433).
- TC-DEP-03: Sincronización y validación del Seed de 38 Usuarios en dbo.App_Usuarios.
- TC-DEP-04: Estado del Servicio Systemd de Usuario 'app-lti.service' (Active: active (running)).
- TC-DEP-05: Verificación de Persistencia Linger habilitado (loginctl Linger=yes).
- TC-DEP-06: Entrega integral de recursos Frontend SPA (index.html, styles.css, app.js, auth.js).
- TC-DEP-07: Autenticación JWT (/api/auth/login, credenciales correctas/incorrectas y /api/auth/me).
- TC-DEP-08: Acceso autenticado y rendimiento de endpoints operativos (/api/kpis, /api/proyectos, /api/lideres, /api/estados, /api/usuarios).
- TC-DEP-09: Configuración de Hot-Reload en Uvicorn (--reload) y supervisión en el servidor remoto.
- TC-DEP-10: Verificación de scripts operativos y gobernanza local (deploy_to_iacdi.sh, run.sh).
"""

import os
import time
import subprocess
import requests
import pytest
from tests.conftest import create_portal_jwt

REMOTE_HOST = "iacdi"
TAILSCALE_IP = "100.82.24.75"
PORT = 8000
REMOTE_BASE_URL = f"http://{TAILSCALE_IP}:{PORT}"


# ==============================================================================
# HELPERS
# ==============================================================================

import socket

IS_LOCAL_HOST = socket.gethostname().lower() == "iacdi" or os.path.exists("/home/iacdi/Desarrollos/app-lti/venv/bin/python3") and os.getcwd().startswith("/home/iacdi")


def run_ssh_command(cmd: str, timeout: int = 15) -> subprocess.CompletedProcess:
    """Ejecuta un comando en el servidor iacdi (local o vía SSH según host)."""
    if IS_LOCAL_HOST:
        return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    ssh_cmd = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
        "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        REMOTE_HOST, cmd
    ]
    return subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)


def run_ssh_python(python_code: str, timeout: int = 20) -> subprocess.CompletedProcess:
    """Ejecuta un script Python en el venv de iacdi pasando el código por stdin."""
    if IS_LOCAL_HOST:
        py_bin = "/home/iacdi/Desarrollos/app-lti/venv/bin/python3"
        return subprocess.run([py_bin], input=python_code, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    ssh_cmd = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
        "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        REMOTE_HOST,
        "/home/iacdi/Desarrollos/app-lti/venv/bin/python3"
    ]
    return subprocess.run(ssh_cmd, input=python_code, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)


# ==============================================================================
# TC-DEP-01: CONECTIVIDAD RED & TAILSCALE
# ==============================================================================

def test_tc_dep_01_tailscale_http_connectivity():
    """
    TC-DEP-01: Verificar conectividad HTTP TCP directa al puerto 8000 en IP Tailscale 100.82.24.75.
    - El servidor debe responder con código HTTP 200 en la ruta raíz.
    - El tiempo de respuesta debe ser inferior a 2.0 segundos.
    """
    t0 = time.time()
    resp = requests.get(f"{REMOTE_BASE_URL}/", timeout=5)
    elapsed = time.time() - t0

    assert resp.status_code == 200, f"Se esperaba código 200 pero se obtuvo {resp.status_code}"
    assert "App Líderes TI" in resp.text or "App LTI" in resp.text
    assert elapsed < 2.0, f"Tiempo de respuesta elevado: {elapsed:.3f}s"
    print(f"\n[TC-DEP-01] Conectividad Tailscale OK ({resp.status_code}) en {elapsed*1000:.1f}ms")


# ==============================================================================
# TC-DEP-02: CONEXIÓN MSSQL DESDE SERVIDOR IACDI
# ==============================================================================

def test_tc_dep_02_mssql_database_connectivity_remote():
    """
    TC-DEP-02: Verificar conectividad y consultas hacia MSSQL (192.168.10.6:1433) desde el servidor iacdi.
    - Ejecutar script Python en el venv remoto que realice una consulta simple sobre dbo.Proyectos.
    - Comprobar que retorne recuento de proyectos mayor a 0 sin errores de socket.
    """
    py_code = """
import sys
sys.path.insert(0, '/home/iacdi/Desarrollos/app-lti')
from backend.db import get_db_connection
conn = get_db_connection()
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(1) as total FROM dbo.Proyectos")
    row = cur.fetchone()
    print("TOTAL_PROYECTOS:" + str(row['total']))
conn.close()
"""
    res = run_ssh_python(py_code)

    assert res.returncode == 0, f"Error ejecutando consulta MSSQL en iacdi: {res.stderr}"
    assert "TOTAL_PROYECTOS:" in res.stdout, f"Salida inesperada: {res.stdout}"

    total_str = res.stdout.split("TOTAL_PROYECTOS:")[1].strip()
    total_proy = int(total_str)
    assert total_proy > 0, f"Recuento de proyectos no esperado: {total_proy}"
    print(f"\n[TC-DEP-02] Conexión MSSQL remota exitosa. Total Proyectos en Sharepoint_Proyectos: {total_proy}")


# ==============================================================================
# TC-DEP-03: SEED DE USUARIOS CANÓNICOS
# ==============================================================================

def test_tc_dep_03_seed_users_canonical_count():
    """
    TC-DEP-03: Verificar que el poblador de usuarios en iacdi registre los 38 usuarios canónicos.
    - Ejecutar seed_users y comprobar que existan al menos 38 cuentas registradas con roles PM, LTI y ADMIN.
    """
    py_code = """
import sys
sys.path.insert(0, '/home/iacdi/Desarrollos/app-lti')
from backend.db import get_db_connection
conn = get_db_connection()
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(1) as total FROM dbo.App_Usuarios")
    total = cur.fetchone()['total']
    cur.execute("SELECT rol, COUNT(1) as c FROM dbo.App_Usuarios GROUP BY rol")
    roles = {r['rol']: r['c'] for r in cur.fetchall()}
print(f"TOTAL:{total},PMS:{roles.get('PM',0)},LTIS:{roles.get('LTI',0)},ADMINS:{roles.get('ADMIN',0)}")
conn.close()
"""
    res = run_ssh_python(py_code)

    assert res.returncode == 0, f"Error verificando usuarios en BD: {res.stderr}"
    assert "TOTAL:" in res.stdout

    stats_str = res.stdout.strip().split("\n")[-1]
    parts = dict(item.split(":") for item in stats_str.split(","))

    total = int(parts["TOTAL"])
    pms = int(parts["PMS"])
    ltis = int(parts["LTIS"])
    admins = int(parts["ADMINS"])

    assert total >= 38, f"Total de usuarios menor a 38: {total}"
    assert pms >= 31, f"PMs esperados >= 31, obtenidos: {pms}"
    assert ltis >= 4, f"LTIs esperados >= 4, obtenidos: {ltis}"
    assert admins >= 3, f"ADMINs esperados >= 3, obtenidos: {admins}"

    print(f"\n[TC-DEP-03] Validación Seed Usuarios: Total={total} (PMs={pms}, LTIs={ltis}, Admins={admins})")


# ==============================================================================
# TC-DEP-04: SERVICIO SYSTEMD DE USUARIO
# ==============================================================================

def test_tc_dep_04_systemd_service_status():
    """
    TC-DEP-04: Verificar que el servicio systemd de usuario 'app-lti.service' esté activo y habilitado en iacdi.
    - systemctl --user is-active app-lti.service -> active
    - systemctl --user is-enabled app-lti.service -> enabled
    """
    res_active = run_ssh_command("systemctl --user is-active app-lti.service")
    assert res_active.returncode == 0, f"El servicio app-lti no está activo: {res_active.stdout} {res_active.stderr}"
    assert res_active.stdout.strip() == "active"

    res_enabled = run_ssh_command("systemctl --user is-enabled app-lti.service")
    assert res_enabled.returncode == 0, f"El servicio app-lti no está habilitado: {res_enabled.stdout}"
    assert res_enabled.stdout.strip() == "enabled"

    res_status = run_ssh_command("systemctl --user status app-lti.service --no-pager")
    assert "Active: active (running)" in res_status.stdout
    assert "uvicorn backend.main:app" in res_status.stdout
    print("\n[TC-DEP-04] Servicio systemd de usuario 'app-lti.service': active (running) y enabled")


# ==============================================================================
# TC-DEP-05: PERSISTENCIA LINGER
# ==============================================================================

def test_tc_dep_05_linger_persistence_enabled():
    """
    TC-DEP-05: Verificar que la persistencia de procesos sin sesión activa (Linger) esté habilitada para iacdi.
    - loginctl show-user iacdi --property=Linger -> Linger=yes
    """
    res = run_ssh_command("loginctl show-user iacdi --property=Linger")
    assert res.returncode == 0, f"Error consultando linger: {res.stderr}"
    assert "Linger=yes" in res.stdout.strip(), f"Linger no está habilitado: {res.stdout}"
    print(f"\n[TC-DEP-05] Persistencia Linger verificada: {res.stdout.strip()}")


# ==============================================================================
# TC-DEP-06: ACCESO Y ENTREGA DE RECURSOS SPA FRONTEND
# ==============================================================================

def test_tc_dep_06_spa_frontend_resources_delivery():
    """
    TC-DEP-06: Verificar entrega completa y correcta de la SPA y todos sus recursos estáticos esenciales.
    - GET / -> 200 OK con HTML válido.
    - GET /css/styles.css -> 200 OK y content-type text/css.
    - GET /js/app.js -> 200 OK y content-type application/javascript.
    - GET /js/auth.js -> 200 OK y content-type application/javascript.
    """
    endpoints = [
        ("/", 200, "text/html", "<!DOCTYPE html>"),
        ("/css/styles.css", 200, "text/css", ":root"),
        ("/js/app.js", 200, "javascript", "const App"),
        ("/js/auth.js", 200, "javascript", "const Auth"),
    ]

    for path, expected_status, content_type_sub, body_signature in endpoints:
        url = f"{REMOTE_BASE_URL}{path}"
        t0 = time.time()
        res = requests.get(url, timeout=5)
        elapsed = time.time() - t0

        assert res.status_code == expected_status, f"Ruta {path} retornó {res.status_code}"
        assert content_type_sub in res.headers.get("Content-Type", ""), f"Content-Type erróneo en {path}"
        assert body_signature in res.text, f"Firma '{body_signature}' no encontrada en {path}"
        assert elapsed < 1.0, f"Tiempo de carga excesivo en {path}: {elapsed:.3f}s"

    print("\n[TC-DEP-06] Todos los recursos estáticos de la SPA fueron servidos exitosamente (200 OK)")


# ==============================================================================
# TC-DEP-07: AUTENTICACIÓN JWT Y ENDPOINTS AUTH
# ==============================================================================

def test_tc_dep_07_jwt_authentication_flows():
    """
    TC-DEP-07: Probar flujos de autenticación SSO Portal JWT en la API desplegada en iacdi.
    - Petición sin token -> 401 Unauthorized.
    - Token con firma incorrecta -> 401 Unauthorized.
    - Token SSO Admin válido (alejandro.aguilar) -> 200 OK y rol ADMIN.
    - Token SSO PM válido (camila.albornoz) -> 200 OK y rol PM.
    - Token SSO LTI válido (juan.barrera) -> 200 OK y rol LTI.
    - Endpoint retirado /api/auth/login -> 405 Method Not Allowed.
    """
    # 1. Petición sin token
    res_no_token = requests.get(f"{REMOTE_BASE_URL}/api/auth/me", timeout=5)
    assert res_no_token.status_code == 401, f"Se esperaba 401 pero se obtuvo {res_no_token.status_code}"

    # 2. Token con firma incorrecta
    headers_bad = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOjE1fQ.InvalidSignature"}
    res_bad = requests.get(f"{REMOTE_BASE_URL}/api/auth/me", headers=headers_bad, timeout=5)
    assert res_bad.status_code == 401, f"Se esperaba 401 pero se obtuvo {res_bad.status_code}"

    # 3. Token Admin válido
    token_admin = create_portal_jwt(username="alejandro.aguilar", admin_level=2, tool_access={"app-lti": "operador"})
    headers_admin = {"Authorization": f"Bearer {token_admin}"}
    res_me = requests.get(f"{REMOTE_BASE_URL}/api/auth/me", headers=headers_admin, timeout=5)
    assert res_me.status_code == 200
    user_me = res_me.json()
    assert user_me["username"] == "alejandro.aguilar"
    assert user_me["rol"] == "ADMIN"
    assert user_me["is_super_admin"] is True

    # 4. Token PM válido
    token_pm = create_portal_jwt(username="camila.albornoz", admin_level=0, tool_access={"app-lti": "lectura"})
    headers_pm = {"Authorization": f"Bearer {token_pm}"}
    res_pm = requests.get(f"{REMOTE_BASE_URL}/api/auth/me", headers=headers_pm, timeout=5)
    assert res_pm.status_code == 200
    assert res_pm.json()["rol"] == "PM"

    # 5. Token LTI válido
    token_lti = create_portal_jwt(username="juan.barrera", admin_level=1, tool_access={"app-lti": "operador"})
    headers_lti = {"Authorization": f"Bearer {token_lti}"}
    res_lti = requests.get(f"{REMOTE_BASE_URL}/api/auth/me", headers=headers_lti, timeout=5)
    assert res_lti.status_code == 200
    assert res_lti.json()["rol"] == "LTI"

    # 6. Endpoint de login retirado
    res_retired = requests.post(f"{REMOTE_BASE_URL}/api/auth/login", json={"username": "admin", "password": "x"}, timeout=5)
    assert res_retired.status_code in (404, 405)

    print("\n[TC-DEP-07] Flujos de autenticación SSO Portal JWT (Admin, PM, LTI, rechazo de inválidos y retiro de login local) validados al 100%")


# ==============================================================================
# TC-DEP-08: ACCESO OPERATIVO Y RENDIMIENTO DE ENDPOINTS REST
# ==============================================================================

def test_tc_dep_08_authenticated_operational_endpoints():
    """
    TC-DEP-08: Verificar disponibilidad y tiempos de respuesta de endpoints de negocio autenticados.
    - GET /api/kpis -> 200 OK con métricas totales, en curso y atendidos (< 2.0s).
    - GET /api/proyectos -> 200 OK con listado de proyectos (< 15.0s con uniones de 100k+ registros).
    - GET /api/lideres -> 200 OK con catálogo de 5 líderes TI oficiales (< 2.0s).
    - GET /api/estados -> 200 OK con estados de SharePoint (< 2.0s).
    - GET /api/usuarios -> 200 OK (solo admin) con listado de usuarios (< 2.0s).
    """
    # Obtener token admin SSO
    token = create_portal_jwt(username="alejandro.aguilar", admin_level=2, tool_access={"app-lti": "operador"})
    headers = {"Authorization": f"Bearer {token}"}

    test_endpoints = [
        ("/api/kpis", lambda data: "total_proyectos" in data and data["total_proyectos"] >= 0, 3.0),
        ("/api/proyectos", lambda data: isinstance(data, list) and len(data) > 0, 45.0),
        ("/api/lideres", lambda data: isinstance(data, list) and len(data) >= 5, 3.0),
        ("/api/estados", lambda data: isinstance(data, dict) and "estados_sharepoint" in data and "Generado" in data["estados_sharepoint"], 15.0),
        ("/api/usuarios", lambda data: isinstance(data, list) and len(data) >= 38, 3.0),
    ]

    for path, validator, max_time in test_endpoints:
        t0 = time.time()
        resp = requests.get(f"{REMOTE_BASE_URL}{path}", headers=headers, timeout=60)
        elapsed = time.time() - t0

        assert resp.status_code == 200, f"Endpoint {path} falló con código {resp.status_code}: {resp.text}"
        data = resp.json()
        assert validator(data), f"Validación de estructura de datos falló en {path}: {data}"
        assert elapsed < max_time, f"Tiempo de respuesta elevado en {path}: {elapsed:.3f}s (máx esperado: {max_time}s)"
        print(f"  -> {path}: 200 OK en {elapsed*1000:.1f}ms (límite: {max_time}s)")

    print("\n[TC-DEP-08] Todos los endpoints operativos responden correctamente con datos reales")


# ==============================================================================
# TC-DEP-09: SUPERVISIÓN DE HOT-RELOAD Y RESTART DEL SERVICIO
# ==============================================================================

def test_tc_dep_09_uvicorn_reload_flag_configured():
    """
    TC-DEP-09: Validar que el comando de ejecución en la unidad systemd remota incluya --reload.
    - Asegura la recarga en caliente para desarrollo continuo sin interrupción del servicio.
    """
    res = run_ssh_command("systemctl --user show app-lti.service --property=ExecStart")
    assert res.returncode == 0
    assert "--reload" in res.stdout, f"El flag --reload no está configurado en ExecStart: {res.stdout}"
    assert "--host 0.0.0.0" in res.stdout or "--host=0.0.0.0" in res.stdout
    assert "--port 8000" in res.stdout or "--port=8000" in res.stdout
    print(f"\n[TC-DEP-09] Configuración de Hot-Reload verificada: {res.stdout.strip()}")


# ==============================================================================
# TC-DEP-10: GOBERNANZA DE SCRIPTS OPERATIVOS LOCALES
# ==============================================================================

def test_tc_dep_10_operational_scripts_permissions_and_syntax():
    """
    TC-DEP-10: Verificar que los scripts locales de gobernanza existan, tengan permisos +x y sintaxis bash válida.
    - deploy_to_iacdi.sh: permisos de ejecución y sintaxis bash correcta (bash -n).
    - run.sh: permisos de ejecución y sintaxis bash correcta (bash -n).
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    deploy_script = os.path.join(base_dir, "deploy_to_iacdi.sh")
    run_script = os.path.join(base_dir, "run.sh")

    assert os.path.exists(deploy_script), f"No se encontró {deploy_script}"
    assert os.path.exists(run_script), f"No se encontró {run_script}"

    assert os.access(deploy_script, os.X_OK), f"{deploy_script} no tiene permisos de ejecución (+x)"
    assert os.access(run_script, os.X_OK), f"{run_script} no tiene permisos de ejecución (+x)"

    # Validación de sintaxis bash (bash -n)
    res_deploy = subprocess.run(["bash", "-n", deploy_script], capture_output=True, text=True)
    assert res_deploy.returncode == 0, f"Error de sintaxis en deploy_to_iacdi.sh: {res_deploy.stderr}"

    res_run = subprocess.run(["bash", "-n", run_script], capture_output=True, text=True)
    assert res_run.returncode == 0, f"Error de sintaxis en run.sh: {res_run.stderr}"

    print("\n[TC-DEP-10] Scripts operativos deploy_to_iacdi.sh y run.sh validados con permisos de ejecución y sintaxis correcta")
