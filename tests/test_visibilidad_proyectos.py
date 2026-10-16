"""
Visibilidad de proyectos (odd/tasks/estados-bitacora-proyectos.md, T3: S5).

Solo alejandro.aguilar y pablo.castillo ven todos los proyectos; los demás (cualquier rol, incluidos otros ADMIN)
quedan limitados a LT_Asignado = su lt_asignado, forzado en el backend. Un proyecto fuera de alcance responde 404.

La base de pruebas es la de producción: todo acceso a datos está simulado.
"""

import pytest
from fastapi.testclient import TestClient

import backend.auth as auth_module
import backend.config as config_module
import backend.db as db_module
import backend.main as main_module
from backend.main import app
from tests.conftest import create_portal_jwt

client = TestClient(app)

USERS = {
    "alejandro.aguilar": ("ADMIN", "Alejandro Aguilar"),
    "pablo.castillo": ("LTI", None),
    "juan.perez": ("LTI", "Juan Barrera"),
    "admin": ("ADMIN", None),
    "aaguilar": ("ADMIN", "Alejandro Aguilar"),
    "pcastillo": ("ADMIN", None),
    "super.admin": ("ADMIN", None),
    "sin.lt": ("LTI", None),
}
FULL = ["alejandro.aguilar", "pablo.castillo"]
RESTRINGIDOS_CON_LT = [("juan.perez", "Juan Barrera"), ("aaguilar", "Alejandro Aguilar")]
RESTRINGIDOS_SIN_LT = ["admin", "pcastillo", "super.admin", "sin.lt"]


@pytest.fixture(autouse=True)
def app_user(monkeypatch):
    def fake_jit(username, nombre_completo=None, default_rol="PM", email=None):
        rol, lt = USERS.get(username, ("PM", None))
        return {"id": 900, "username": username, "nombre_completo": username.title(),
                "email": f"{username}@clarovtr.cl", "rol": rol, "lt_asignado": lt, "activo": 1}

    monkeypatch.setattr(auth_module, "get_or_create_jit_user", fake_jit)


def _h(username):
    token = create_portal_jwt(username=username, admin_level=0, tool_access={"app-lti": "operador"})
    return {"Authorization": f"Bearer {token}"}


def test_config_usuarios_con_visibilidad_total():
    assert config_module.FULL_PROJECT_VISIBILITY_USERNAMES == frozenset({"alejandro.aguilar", "pablo.castillo"})


# ---------------------------------------------------------------------------
# /api/auth/me
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("username,esperado", [(u, True) for u in FULL] + [
    ("juan.perez", False), ("admin", False), ("aaguilar", False), ("pcastillo", False), ("super.admin", False),
])
def test_s5_auth_me_expone_ve_todos_proyectos(username, esperado):
    res = client.get("/api/auth/me", headers=_h(username))
    assert res.status_code == 200, res.text
    assert res.json()["ve_todos_proyectos"] is esperado


def test_s5_auth_me_mantiene_los_campos_existentes():
    body = client.get("/api/auth/me", headers=_h("juan.perez")).json()
    assert {"id", "username", "nombre_completo", "lt_asignado", "rol", "is_super_admin", "portal_access"} <= set(body)
    assert body["lt_asignado"] == "Juan Barrera" and body["rol"] == "LTI"


# ---------------------------------------------------------------------------
# GET /api/proyectos
# ---------------------------------------------------------------------------

@pytest.fixture
def proyectos_env(monkeypatch):
    llamadas = []

    def fake_get_proyectos(**kwargs):
        llamadas.append(kwargs)
        return [{"ID": 1}]

    monkeypatch.setattr(main_module, "get_proyectos", fake_get_proyectos)
    return llamadas


@pytest.mark.parametrize("username", FULL)
def test_s5_usuarios_completos_sin_parametro_ven_todos(proyectos_env, username):
    res = client.get("/api/proyectos", headers=_h(username))
    assert res.status_code == 200 and res.json() == [{"ID": 1}]
    assert proyectos_env[0]["lt_filter"] is None


@pytest.mark.parametrize("username", FULL)
@pytest.mark.parametrize("param,esperado", [
    ("Erwin Sandoval", "Erwin Sandoval"),
    ("__ALL__", None),
    ("__UNASSIGNED__", "__UNASSIGNED__"),
    ("sin asignar", "__UNASSIGNED__"),
    ("sin_asignar", "__UNASSIGNED__"),
])
def test_s5_usuarios_completos_pueden_filtrar_por_lti(proyectos_env, username, param, esperado):
    res = client.get("/api/proyectos", params={"lt": param}, headers=_h(username))
    assert res.status_code == 200
    assert proyectos_env[0]["lt_filter"] == esperado


@pytest.mark.parametrize("username,lt", RESTRINGIDOS_CON_LT)
@pytest.mark.parametrize("param", [None, "Erwin Sandoval", "__ALL__", "__UNASSIGNED__", "sin asignar"])
def test_s5_restringidos_siempre_ven_solo_su_lti(proyectos_env, username, lt, param):
    params = {"lt": param} if param else {}
    res = client.get("/api/proyectos", params=params, headers=_h(username))
    assert res.status_code == 200
    assert proyectos_env[0]["lt_filter"] == lt


def test_s5_restringido_conserva_los_otros_filtros(proyectos_env):
    client.get("/api/proyectos", params={"search": "abc", "estado_sp": "Cerrado", "estado_sga": "X"},
               headers=_h("juan.perez"))
    assert proyectos_env[0] == {"lt_filter": "Juan Barrera", "search": "abc", "estado_sp": "Cerrado", "estado_sga": "X"}


@pytest.mark.parametrize("username", RESTRINGIDOS_SIN_LT)
@pytest.mark.parametrize("param", [None, "Erwin Sandoval", "__ALL__", "__UNASSIGNED__"])
def test_s5_sin_lti_asignado_no_ven_nada_ni_consultan_la_bd(proyectos_env, username, param):
    params = {"lt": param} if param else {}
    res = client.get("/api/proyectos", params=params, headers=_h(username))
    assert res.status_code == 200
    assert res.json() == []
    assert proyectos_env == []


# ---------------------------------------------------------------------------
# GET /api/kpis
# ---------------------------------------------------------------------------

@pytest.fixture
def kpis_env(monkeypatch):
    llamadas = []

    def fake_kpis(**kwargs):
        llamadas.append(kwargs)
        return {"total_proyectos": 5}

    monkeypatch.setattr(main_module, "get_dashboard_kpis", fake_kpis)
    return llamadas


@pytest.mark.parametrize("username", FULL)
def test_s5_kpis_usuarios_completos_sin_parametro_son_globales(kpis_env, username):
    res = client.get("/api/kpis", headers=_h(username))
    assert res.status_code == 200
    assert kpis_env == [{"lt_filter": None, "restringido": False}]


@pytest.mark.parametrize("username", FULL)
@pytest.mark.parametrize("param,esperado", [("Erwin Sandoval", "Erwin Sandoval"), ("__ALL__", None),
                                            ("__UNASSIGNED__", "__UNASSIGNED__")])
def test_s5_kpis_usuarios_completos_pueden_filtrar(kpis_env, username, param, esperado):
    client.get("/api/kpis", params={"lt": param}, headers=_h(username))
    assert kpis_env == [{"lt_filter": esperado, "restringido": False}]


@pytest.mark.parametrize("username,lt", RESTRINGIDOS_CON_LT)
@pytest.mark.parametrize("param", [None, "Erwin Sandoval", "__ALL__", "__UNASSIGNED__"])
def test_s5_kpis_restringidos_usan_su_lti(kpis_env, username, lt, param):
    params = {"lt": param} if param else {}
    res = client.get("/api/kpis", params=params, headers=_h(username))
    assert res.status_code == 200
    assert kpis_env == [{"lt_filter": lt, "restringido": True}]


@pytest.mark.parametrize("username", RESTRINGIDOS_SIN_LT)
def test_s5_kpis_sin_lti_asignado_son_cero_sin_consultar_la_bd(kpis_env, username):
    res = client.get("/api/kpis", params={"lt": "__ALL__"}, headers=_h(username))
    assert res.status_code == 200
    assert kpis_env == []
    body = res.json()
    assert body["total_proyectos"] == 0 and body["proyectos_en_curso"] == 0
    assert body["proyectos_atendidos"] == 0 and body["proyectos_cerrados"] == 0
    assert body["pendientes_asignar"] == 0 and body["efectividad"] == 0.0
    assert body["total_tickets"] == 0 and body["total_rfcs"] == 0
    assert body["salud"] == {"saludables": 0, "en_riesgo": 0, "criticos": 0, "sin_datos": 0}


class _Cur:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((" ".join(sql.split()), params))
        self.rows = [{"total": 0}]

    def fetchone(self):
        return self.rows[0]


class _Conn:
    def __init__(self):
        self.executed = []

    def cursor(self):
        return _Cur(self)

    def close(self):
        pass


def test_s5_kpis_vacios_tiene_las_mismas_claves_que_los_reales(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    reales = db_module.get_dashboard_kpis()
    vacios = db_module.kpis_vacios()
    assert set(vacios) == set(reales)
    assert set(vacios["salud"]) == set(reales["salud"])


def _pendientes(conn):
    return [(s, p) for s, p in conn.executed if "LOWER(LTRIM(RTRIM(p.LT_Asignado))) = 'sin asignar'" in s
            and "COUNT(1) as total" in s and "Tipo_Servicio" in s and "p.Estado" not in s
            and "registros" not in s]


def test_s5_pendientes_asignar_global_para_usuarios_completos(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    db_module.get_dashboard_kpis(lt_filter="Erwin Sandoval")
    pend = [(s, p) for s, p in conn.executed if s.startswith("SELECT COUNT(1) as total FROM dbo.Proyectos p WITH (NOLOCK) WHERE (p.LT_Asignado IS NULL")]
    assert len(pend) == 1
    assert "p.LT_Asignado = %s" not in pend[0][0]


def test_s5_pendientes_asignar_se_calcula_dentro_del_alcance_del_restringido(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    db_module.get_dashboard_kpis(lt_filter="Juan Barrera", restringido=True)
    pend = [(s, p) for s, p in conn.executed if s.startswith("SELECT COUNT(1) as total FROM dbo.Proyectos p WITH (NOLOCK) WHERE (p.LT_Asignado IS NULL")]
    assert len(pend) == 1
    sql, params = pend[0]
    assert "AND p.LT_Asignado = %s" in sql
    assert params == ("Juan Barrera",)


# ---------------------------------------------------------------------------
# GET /api/alertas/sla
# ---------------------------------------------------------------------------

@pytest.fixture
def alertas_env(monkeypatch):
    llamadas = []

    def fake_alertas(**kwargs):
        llamadas.append(kwargs)
        return {"alertas": []}

    monkeypatch.setattr(main_module, "get_alertas_tempranas_sla", fake_alertas)
    return llamadas


@pytest.mark.parametrize("username", FULL)
def test_s5_alertas_usuarios_completos_mantienen_el_parametro_lider(alertas_env, username):
    client.get("/api/alertas/sla", params={"lider": "Erwin Sandoval"}, headers=_h(username))
    assert alertas_env[0]["lider"] == "Erwin Sandoval"
    client.get("/api/alertas/sla", headers=_h(username))
    assert alertas_env[1]["lider"] is None


@pytest.mark.parametrize("username,lt", RESTRINGIDOS_CON_LT)
@pytest.mark.parametrize("param", [None, "Erwin Sandoval", "todos"])
def test_s5_alertas_restringidos_fuerzan_su_lider(alertas_env, username, lt, param):
    params = {"lider": param} if param else {}
    res = client.get("/api/alertas/sla", params=params, headers=_h(username))
    assert res.status_code == 200
    assert alertas_env[0]["lider"] == lt


@pytest.mark.parametrize("username", RESTRINGIDOS_SIN_LT)
def test_s5_alertas_sin_lti_asignado_devuelven_estructura_vacia_sin_consultar_la_bd(alertas_env, username):
    res = client.get("/api/alertas/sla", params={"lider": "Erwin Sandoval"}, headers=_h(username))
    assert res.status_code == 200
    assert alertas_env == []
    esperado = db_module.procesar_alertas_sla([], [], lider=None, severidad="todas", tipo="todos", limite=100)
    obtenido = res.json()
    assert set(obtenido) == set(esperado)
    assert {k: v for k, v in obtenido.items() if k != "timestamp"} == {k: v for k, v in esperado.items() if k != "timestamp"}
    assert obtenido["alertas"] == []


# ---------------------------------------------------------------------------
# Endpoints por proyecto
# ---------------------------------------------------------------------------

NF_PROY = "Proyecto no encontrado"
NF_ID = "Proyecto con ID 123 no fue encontrado."


@pytest.fixture
def datos(monkeypatch, tmp_path):
    """Simula el proyecto y todas las funciones de datos; registra cuáles se invocaron."""
    state = {"row": {"ID": 123, "LT_Asignado": "Juan Barrera", "Estado": "En ejecucion"}, "calls": []}
    adj_dir = tmp_path / "adjuntos"
    adj_dir.mkdir()
    (adj_dir / "abc.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(config_module, "ADJUNTOS_DIR", str(adj_dir))

    def rec(nombre, retorno):
        def fn(*a, **k):
            state["calls"].append(nombre)
            return retorno
        monkeypatch.setattr(main_module, nombre, fn)

    monkeypatch.setattr(main_module, "get_proyecto_by_id", lambda pid: state["row"])
    rec("get_solots_by_proyecto", [])
    rec("get_tickets_by_proyecto", [])
    rec("get_rfcs_by_proyecto", [])
    rec("get_diagnostico_proyecto", {"ok": 1})
    rec("get_ficha_ejecutiva_data", {"ok": 1})
    rec("generar_ficha_ejecutiva_html", "<html></html>")
    rec("get_timeline_proyecto", {"ok": 1})
    rec("update_proyecto", {"success": True, "data": {"ID": 123}, "was_assigned": False, "bitacora_entry_id": None})
    rec("delete_proyecto", {"success": True, "id": 123, "numero_proyecto": "1", "cliente": "C"})
    rec("get_bitacora_by_proyecto", [])
    rec("create_bitacora_entry", {"id": 1})
    rec("get_bitacora_entry", {"ID": 5})
    rec("create_adjunto", {"id": 1})
    rec("get_adjunto", {"ID": 9, "Proyecto_ID": 123, "Nombre_Original": "a.pdf", "Nombre_Almacenado": "abc.pdf"})
    monkeypatch.setattr(main_module, "notificar_asignacion_lti_bg", lambda **kw: None)
    return state


_PUT_BODY = {"cliente": "C", "estado": "Generado", "detalle": "D", "lt_asignado": "Erwin Sandoval"}

# nombre, método, ruta, kwargs, función de datos que NO debe invocarse fuera de alcance, 404 esperado
ENDPOINTS = [
    ("proyecto", "get", "/api/proyectos/123", {}, None, NF_PROY),
    ("solots", "get", "/api/proyectos/123/solots", {}, "get_solots_by_proyecto", NF_PROY),
    ("tickets", "get", "/api/proyectos/123/tickets", {}, "get_tickets_by_proyecto", NF_PROY),
    ("rfcs", "get", "/api/proyectos/123/rfcs", {}, "get_rfcs_by_proyecto", NF_PROY),
    ("diagnostico", "get", "/api/proyectos/123/diagnostico", {}, "get_diagnostico_proyecto", NF_ID),
    ("ficha-ejecutiva", "get", "/api/proyectos/123/ficha-ejecutiva", {}, "get_ficha_ejecutiva_data", NF_ID),
    ("ficha-html", "get", "/api/proyectos/123/ficha-html", {}, "get_ficha_ejecutiva_data", NF_ID),
    ("timeline", "get", "/api/proyectos/123/timeline", {}, "get_timeline_proyecto", NF_ID),
    ("put", "put", "/api/proyectos/123", {"json": _PUT_BODY}, "update_proyecto", NF_PROY),
    ("delete", "delete", "/api/proyectos/123", {}, "delete_proyecto", NF_PROY),
    ("bitacora-get", "get", "/api/proyectos/123/bitacora", {}, "get_bitacora_by_proyecto", NF_PROY),
    ("bitacora-post", "post", "/api/proyectos/123/bitacora", {"json": {"texto": "x"}}, "create_bitacora_entry", NF_PROY),
    ("adjunto-post", "post", "/api/proyectos/123/bitacora/5/adjuntos",
     {"files": {"archivo": ("a.pdf", b"datos", "application/pdf")}}, "create_adjunto", NF_PROY),
    ("adjunto-get", "get", "/api/proyectos/123/adjuntos/9", {}, "get_adjunto", NF_PROY),
]
IDS = [e[0] for e in ENDPOINTS]


def _call(metodo, ruta, kwargs, username):
    return getattr(client, metodo)(ruta, headers=_h(username), **kwargs)


@pytest.mark.parametrize("nombre,metodo,ruta,kwargs,funcion,nf", ENDPOINTS, ids=IDS)
@pytest.mark.parametrize("lt_proyecto", ["Erwin Sandoval", None, "", "sin asignar"])
def test_s5_proyecto_fuera_de_alcance_es_404_sin_datos(datos, nombre, metodo, ruta, kwargs, funcion, nf, lt_proyecto):
    datos["row"]["LT_Asignado"] = lt_proyecto
    # ADMIN restringido (sirve también para DELETE, que exige ADMIN)
    res = _call(metodo, ruta, kwargs, "aaguilar")
    assert res.status_code == 404, res.text
    assert res.json()["detail"] == nf
    if funcion:
        assert funcion not in datos["calls"]
    assert datos["calls"] == []


@pytest.mark.parametrize("nombre,metodo,ruta,kwargs,funcion,nf", ENDPOINTS, ids=IDS)
def test_s5_proyecto_en_alcance_responde_ok(datos, nombre, metodo, ruta, kwargs, funcion, nf, monkeypatch):
    datos["row"]["LT_Asignado"] = "  alejandro AGUILAR "  # recortado y sin distinguir mayúsculas
    res = _call(metodo, ruta, kwargs, "aaguilar")
    assert res.status_code in (200, 201), res.text
    if funcion:
        assert funcion in datos["calls"]


@pytest.mark.parametrize("nombre,metodo,ruta,kwargs,funcion,nf", ENDPOINTS, ids=IDS)
@pytest.mark.parametrize("username", FULL)
def test_s5_usuarios_completos_acceden_a_cualquier_proyecto(datos, nombre, metodo, ruta, kwargs, funcion, nf, username):
    datos["row"]["LT_Asignado"] = "Erwin Sandoval"
    if metodo == "delete" and username == "pablo.castillo":
        # Eliminar sigue exigiendo rol ADMIN (S5 no cambia roles): pablo.castillo es LTI
        assert _call(metodo, ruta, kwargs, username).status_code == 403
        return
    assert _call(metodo, ruta, kwargs, username).status_code in (200, 201)


@pytest.mark.parametrize("nombre,metodo,ruta,kwargs,funcion,nf", ENDPOINTS, ids=IDS)
@pytest.mark.parametrize("username", ["admin", "pcastillo", "super.admin"])
def test_s5_admin_sin_lti_no_accede_a_ningun_proyecto(datos, nombre, metodo, ruta, kwargs, funcion, nf, username):
    datos["row"]["LT_Asignado"] = None
    res = _call(metodo, ruta, kwargs, username)
    assert res.status_code == 404, res.text
    assert datos["calls"] == []


@pytest.mark.parametrize("ruta,funcion", [
    ("/api/proyectos/123/diagnostico", "get_diagnostico_proyecto"),
    ("/api/proyectos/123/ficha-ejecutiva", "get_ficha_ejecutiva_data"),
    ("/api/proyectos/123/timeline", "get_timeline_proyecto"),
])
def test_s5_usuario_completo_no_necesita_lectura_previa_del_proyecto(datos, monkeypatch, ruta, funcion):
    def falla(pid):
        raise AssertionError("no debe leer el proyecto")

    monkeypatch.setattr(main_module, "get_proyecto_by_id", falla)
    assert client.get(ruta, headers=_h("alejandro.aguilar")).status_code == 200


def test_s5_proyecto_inexistente_mantiene_el_404_de_cada_endpoint(datos):
    datos["row"] = None
    assert client.get("/api/proyectos/123", headers=_h("juan.perez")).json()["detail"] == NF_PROY
    assert client.get("/api/proyectos/123/diagnostico", headers=_h("juan.perez")).json()["detail"] == NF_ID


def test_s5_put_restringido_puede_reasignar_el_lti(datos):
    datos["row"]["LT_Asignado"] = "Juan Barrera"
    res = client.put("/api/proyectos/123", json=_PUT_BODY, headers=_h("juan.perez"))
    assert res.status_code == 200, res.text
    assert datos["calls"] == ["update_proyecto"]


def test_s5_rol_lti_restringido_ve_su_proyecto(datos):
    res = client.get("/api/proyectos/123", headers=_h("juan.perez"))
    assert res.status_code == 200 and res.json()["ID"] == 123


# ---------------------------------------------------------------------------
# PUT: tope de nota_estado
# ---------------------------------------------------------------------------

def test_s5_put_nota_de_mas_de_20000_caracteres_es_400_sin_modificar(datos):
    body = dict(_PUT_BODY, estado="En revision", nota_estado="a" * 20001)
    res = client.put("/api/proyectos/123", json=body, headers=_h("alejandro.aguilar"))
    assert res.status_code == 400
    assert res.json()["detail"] == "La nota no puede superar 20000 caracteres"
    assert datos["calls"] == []


def test_s5_put_nota_de_20000_caracteres_es_valida(datos):
    body = dict(_PUT_BODY, estado="En revision", nota_estado="a" * 20000)
    res = client.put("/api/proyectos/123", json=body, headers=_h("alejandro.aguilar"))
    assert res.status_code == 200, res.text
    assert datos["calls"] == ["update_proyecto"]
