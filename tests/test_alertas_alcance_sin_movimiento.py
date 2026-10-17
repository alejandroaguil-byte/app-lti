"""
Alert scope and "project without movement" alert (odd/tasks/fixes-proyectos-alertas.md, T4: S5).

- Scope: a full-visibility user WITH lt_asignado sees only the alerts of their own projects (an explicit `lider`
  query param is still honored); a full-visibility user WITHOUT lt_asignado keeps seeing everything; every other
  user is unchanged (forced to their own LTI, no LTI -> empty).
- New alert: 'En ejecucion' / 'En revision' projects whose latest movement is more than 7 calendar days old
  (bitácora, linked Solot / ticket / RFC, project creation).

The test database is production: all data access here is simulated (fake connections).
"""

import datetime

import pytest
from fastapi.testclient import TestClient

import backend.auth as auth_module
import backend.db as db_module
import backend.main as main_module
from backend.main import app
from tests.conftest import create_portal_jwt

client = TestClient(app)

HOY = datetime.date.today()


def _dt(days_ago, hour=12):
    return datetime.datetime.combine(HOY - datetime.timedelta(days=days_ago), datetime.time(hour, 0))


def _proyecto(pid=100, dias=10, estado="En ejecucion", lider="Juan Barrera", tipo_servicio="Otros", cliente="Cliente SA"):
    return {
        "p_id": pid,
        "p_numero": f"000{pid}",
        "p_cliente": cliente,
        "p_lider": lider,
        "p_estado": estado,
        "p_tipo_servicio": tipo_servicio,
        "ultimo_movimiento": _dt(dias),
    }


def _sin_mov(res):
    return [a for a in res["alertas"] if a.get("codigo") == "PROYECTO_SIN_MOVIMIENTO"]


# ---------------------------------------------------------------------------
# Scope: GET /api/alertas/sla
# ---------------------------------------------------------------------------

USERS = {
    "alejandro.aguilar": ("ADMIN", "Alejandro Aguilar"),
    "pablo.castillo": ("LTI", None),
    "juan.perez": ("LTI", "Juan Barrera"),
    "sin.lt": ("LTI", None),
}


@pytest.fixture
def alertas_env(monkeypatch):
    def fake_jit(username, nombre_completo=None, default_rol="PM", email=None):
        rol, lt = USERS.get(username, ("PM", None))
        return {"id": 900, "username": username, "nombre_completo": username.title(),
                "email": f"{username}@clarovtr.cl", "rol": rol, "lt_asignado": lt, "activo": 1}

    monkeypatch.setattr(auth_module, "get_or_create_jit_user", fake_jit)
    llamadas = []

    def fake_alertas(**kwargs):
        llamadas.append(kwargs)
        return {"alertas": []}

    monkeypatch.setattr(main_module, "get_alertas_tempranas_sla", fake_alertas)
    return llamadas


def _h(username):
    token = create_portal_jwt(username=username, admin_level=0, tool_access={"app-lti": "operador"})
    return {"Authorization": f"Bearer {token}"}


def test_s5_alcance_visibilidad_total_con_lti_ve_solo_sus_proyectos(alertas_env):
    res = client.get("/api/alertas/sla", headers=_h("alejandro.aguilar"))
    assert res.status_code == 200
    assert alertas_env[0]["lider"] == "Alejandro Aguilar"


def test_s5_alcance_visibilidad_total_con_lti_respeta_el_parametro_lider_explicito(alertas_env):
    client.get("/api/alertas/sla", params={"lider": "Erwin Sandoval"}, headers=_h("alejandro.aguilar"))
    assert alertas_env[0]["lider"] == "Erwin Sandoval"


def test_s5_alcance_visibilidad_total_con_lti_puede_pedir_todos_explicitamente(alertas_env):
    client.get("/api/alertas/sla", params={"lider": "todos"}, headers=_h("alejandro.aguilar"))
    assert alertas_env[0]["lider"] == "todos"


def test_s5_alcance_visibilidad_total_sin_lti_sigue_viendo_todo(alertas_env):
    client.get("/api/alertas/sla", headers=_h("pablo.castillo"))
    client.get("/api/alertas/sla", params={"lider": "Erwin Sandoval"}, headers=_h("pablo.castillo"))
    assert alertas_env[0]["lider"] is None
    assert alertas_env[1]["lider"] == "Erwin Sandoval"


@pytest.mark.parametrize("param", [None, "Erwin Sandoval", "todos"])
def test_s5_alcance_usuario_restringido_sigue_forzado_a_su_lti(alertas_env, param):
    params = {"lider": param} if param else {}
    res = client.get("/api/alertas/sla", params=params, headers=_h("juan.perez"))
    assert res.status_code == 200
    assert alertas_env[0]["lider"] == "Juan Barrera"


def test_s5_alcance_restringido_sin_lti_devuelve_vacio_sin_consultar_la_bd(alertas_env):
    res = client.get("/api/alertas/sla", headers=_h("sin.lt"))
    assert res.status_code == 200
    assert alertas_env == []
    assert res.json()["alertas"] == []
    assert res.json()["resumen"]["proyectos_con_alertas"] == 0


def test_s5_alcance_se_mantienen_los_filtros_de_severidad_tipo_y_limite(alertas_env):
    client.get("/api/alertas/sla", params={"severidad": "advertencia", "tipo": "proyecto", "limite": 7},
               headers=_h("alejandro.aguilar"))
    llamada = alertas_env[0]
    assert (llamada["severidad"], llamada["tipo"], llamada["limite"]) == ("advertencia", "proyecto", 7)


# ---------------------------------------------------------------------------
# New alert: processing (boundary, states, payload)
# ---------------------------------------------------------------------------

def test_s5_sin_movimiento_se_alerta_con_mas_de_7_dias_calendario():
    res = db_module.procesar_alertas_sla([], [], raw_proyectos=[_proyecto(dias=8)])
    alertas = _sin_mov(res)
    assert len(alertas) == 1
    a = alertas[0]
    assert a["tipo"] == "proyecto"
    assert a["severidad"] == "WARNING"
    assert a["badge_color"] == "amber"
    assert a["proyecto_id"] == 100
    assert a["numero_proyecto"] == "000100"
    assert a["cliente"] == "Cliente SA"
    assert a["lt_asignado"] == "Juan Barrera"
    assert a["detalle_sla"].startswith("Sin movimiento hace 8 días")
    assert a["fecha_referencia"] == _dt(8).strftime("%Y-%m-%d")
    assert a["dias_fuera_sla"] == 1
    assert a["dias_sin_movimiento"] == 8
    assert a["codigo"] == "PROYECTO_SIN_MOVIMIENTO"


def test_s5_sin_movimiento_limite_exacto_de_7_dias_no_alerta():
    res = db_module.procesar_alertas_sla([], [], raw_proyectos=[_proyecto(pid=1, dias=7), _proyecto(pid=2, dias=0), _proyecto(pid=3, dias=1)])
    assert _sin_mov(res) == []
    assert res["resumen"]["total_alertas"] == 0
    assert res["proyectos"] == []


def test_s5_sin_movimiento_el_limite_se_mide_en_dias_calendario_sin_importar_la_hora():
    inicio_dia = _proyecto(pid=1, dias=7)
    inicio_dia["ultimo_movimiento"] = datetime.datetime.combine(HOY - datetime.timedelta(days=7), datetime.time(0, 0))
    fin_dia = _proyecto(pid=2, dias=8)
    fin_dia["ultimo_movimiento"] = datetime.datetime.combine(HOY - datetime.timedelta(days=8), datetime.time(23, 59))
    res = db_module.procesar_alertas_sla([], [], raw_proyectos=[inicio_dia, fin_dia])
    assert [a["proyecto_id"] for a in _sin_mov(res)] == [2]


def test_s5_sin_movimiento_el_mensaje_informa_los_dias_transcurridos():
    res = db_module.procesar_alertas_sla([], [], raw_proyectos=[_proyecto(dias=30)])
    assert _sin_mov(res)[0]["detalle_sla"].startswith("Sin movimiento hace 30 días")


@pytest.mark.parametrize("estado", ["En ejecucion", "En revision"])
def test_s5_sin_movimiento_aplica_a_en_ejecucion_y_en_revision(estado):
    res = db_module.procesar_alertas_sla([], [], raw_proyectos=[_proyecto(estado=estado, dias=9)])
    assert len(_sin_mov(res)) == 1


@pytest.mark.parametrize("estado", ["Generado", "Cerrado", "Atendido", None])
def test_s5_sin_movimiento_no_aplica_a_otros_estados(estado):
    res = db_module.procesar_alertas_sla([], [], raw_proyectos=[_proyecto(estado=estado, dias=60)])
    assert _sin_mov(res) == []


def test_s5_sin_movimiento_excluye_reuniones():
    res = db_module.procesar_alertas_sla([], [], raw_proyectos=[_proyecto(tipo_servicio="Reunión", dias=60)])
    assert _sin_mov(res) == []


def test_s5_sin_movimiento_ignora_filas_sin_fecha_de_movimiento():
    fila = _proyecto(dias=60)
    fila["ultimo_movimiento"] = None
    assert _sin_mov(db_module.procesar_alertas_sla([], [], raw_proyectos=[fila])) == []


def test_s5_sin_movimiento_cuenta_en_metricas_y_agrupacion_por_proyecto():
    res = db_module.procesar_alertas_sla([], [], raw_proyectos=[_proyecto(pid=1, dias=9), _proyecto(pid=2, dias=20)])
    r = res["resumen"]
    assert r["total_alertas"] == 2
    assert r["advertencias"] == 2
    assert r["criticas"] == 0
    assert r["proyectos_sin_movimiento"] == 2
    assert r["proyectos_con_alertas"] == 2
    assert r["proyectos_alerta_advertencia"] == 2
    assert r["proyectos_alerta_criticos"] == 0
    grupos = {g["proyecto_id"]: g for g in res["proyectos"]}
    assert grupos[2]["sin_movimiento"] is True and grupos[2]["advertencias"] == 1
    assert grupos[2]["dias_sin_movimiento"] == 20 and grupos[1]["dias_sin_movimiento"] == 9
    assert grupos[2]["max_dias_fuera_sla"] == 0  # inactivity is not an SLA delay
    assert [g["proyecto_id"] for g in res["proyectos"]] == [2, 1]  # more stale first


def test_s5_sin_movimiento_convive_con_otras_alertas_del_mismo_proyecto():
    hoy = datetime.date.today()
    ticket = {
        "CC_INCIDENT_ID": "SD1", "STATUS": "Abierto",
        "SUBMIT_DATE": (hoy - datetime.timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S"),
        "p_id": 100, "p_numero": "000100", "p_cliente": "Cliente SA", "p_lider": "Juan Barrera",
    }
    res = db_module.procesar_alertas_sla([ticket], [], raw_proyectos=[_proyecto(pid=100, dias=12)])
    assert res["resumen"]["total_alertas"] == 2
    assert res["resumen"]["proyectos_con_alertas"] == 1
    assert res["proyectos"][0]["total_alertas"] == 2
    assert res["proyectos"][0]["severidad"] == "CRITICAL"
    assert res["proyectos"][0]["sin_movimiento"] is True


@pytest.mark.parametrize("severidad,esperadas", [
    ("todas", 1), ("advertencia", 1), ("warning", 1), ("critica", 0), ("info", 0),
])
def test_s5_sin_movimiento_respeta_el_filtro_de_severidad(severidad, esperadas):
    res = db_module.procesar_alertas_sla([], [], severidad=severidad, raw_proyectos=[_proyecto(dias=10)])
    assert len(res["alertas"]) == esperadas
    assert res["resumen"]["proyectos_sin_movimiento"] == 1  # summary is independent of the filters


@pytest.mark.parametrize("tipo,esperadas", [
    ("todos", 1), ("proyecto", 1), ("proyectos", 1), ("ticket", 0), ("solot", 0),
])
def test_s5_sin_movimiento_respeta_el_filtro_de_tipo(tipo, esperadas):
    res = db_module.procesar_alertas_sla([], [], tipo=tipo, raw_proyectos=[_proyecto(dias=10)])
    assert len(res["alertas"]) == esperadas


def test_s5_sin_movimiento_respeta_el_limite():
    filas = [_proyecto(pid=i, dias=10 + i) for i in range(1, 6)]
    res = db_module.procesar_alertas_sla([], [], limite=2, raw_proyectos=filas)
    assert len(res["alertas"]) == 2
    assert res["resumen"]["total_alertas"] == 5


def test_s5_sin_movimiento_respeta_el_filtro_de_lider():
    filas = [_proyecto(pid=1, dias=10, lider="Juan Barrera"), _proyecto(pid=2, dias=10, lider="Erwin Sandoval")]
    res = db_module.procesar_alertas_sla([], [], lider="Juan Barrera", raw_proyectos=filas)
    assert [a["proyecto_id"] for a in _sin_mov(res)] == [1]


def test_s5_sin_movimiento_aparece_en_la_minuta():
    res = db_module.procesar_alertas_sla([], [], raw_proyectos=[_proyecto(dias=10)])
    assert "Proyectos sin movimiento (>7 días): 1" in res["minuta_escalamiento"]["texto_plano"]


def test_s5_preserva_alertas_sla_existentes_sin_condicion_de_inactividad():
    ticket = {
        "CC_INCIDENT_ID": "SD2", "STATUS": "Abierto",
        "SUBMIT_DATE": (HOY - datetime.timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S"),
        "p_id": 100, "p_numero": "000100", "p_cliente": "Cliente SA", "p_lider": "Juan Barrera",
    }
    con = db_module.procesar_alertas_sla([ticket], [], raw_proyectos=[_proyecto(pid=100, dias=3)])
    base = db_module.procesar_alertas_sla([ticket], [])
    for res in (con, base):
        res.pop("timestamp")
        res["minuta_escalamiento"].pop("texto_plano")
    assert con["alertas"] == base["alertas"]
    assert con["proyectos"][0]["total_alertas"] == base["proyectos"][0]["total_alertas"] == 1
    assert con["resumen"]["total_alertas"] == base["resumen"]["total_alertas"] == 1
    assert _sin_mov({"alertas": con["alertas"]}) == []


# ---------------------------------------------------------------------------
# New alert: SQL (one aggregated query; movement sources; filters)
# ---------------------------------------------------------------------------

class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        sql = " ".join(sql.split())
        self.conn.executed.append((sql, params))
        self._rows = self.conn.responder(sql, params)

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self, responder=None):
        self.executed = []
        self.responder = responder or (lambda sql, params: [])

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        pass


def _sql_sin_movimiento(conn):
    sqls = [(s, p) for s, p in conn.executed if "Proyecto_Bitacora" in s]
    assert len(sqls) == 1, "the stale-project check must be a single aggregated query"
    return sqls[0]


def test_s5_sql_una_sola_consulta_agregada_con_las_fuentes_de_movimiento(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    db_module.get_alertas_tempranas_sla()
    assert len(conn.executed) == 3  # tickets, solots, projects without movement (no N+1)
    sql, params = _sql_sin_movimiento(conn)
    assert params == ()
    assert "p.Estado IN ('En ejecucion', 'En revision')" in sql
    assert "p.Tipo_Servicio <> 'Reunión'" in sql
    assert "OUTER APPLY" not in sql  # keeps the SLA queries identifiable
    for col in ("bi.Creado", "b.FECHA_INSERT", "b.FECHA_CAMBIO_ESTADO_OTP", "b.FECHA_REALIZACION", "b.FECHACIERRE",
                "sd.SUBMIT_DATE", "sd.CLOSE_DATE", "rfc.ORIG_DATE_ENTERED", "rfc.CLOSE_TIME", "p.Creado"):
        assert col in sql
    for tabla, alias in (("CT_BACKLOG_OPERACIONES2", "b"), ("registrosRF_SD_SM", "sd"), ("registrosSM_RFC", "rfc")):
        assert f"dbo.{tabla} {alias} WITH (NOLOCK)" in sql
        assert f"{alias}.ID_Proyecto = p.ID" in sql
        assert f"INNER JOIN dbo.{{}} {alias} WITH (NOLOCK) ON {alias}.Numero_Proyecto_Limpio = pn.numero".format(tabla) in sql
    assert f"SELECT {db_module._SQL_P_NUMERO_TRIM} AS numero" in sql  # same number linking as the detail
    assert db_module._SQL_P_NUMERO_SIN_PREFIJO in sql
    assert "ultimo_movimiento" in sql


def test_s5_sql_no_cuenta_fechas_futuras_como_movimiento(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    db_module.get_alertas_tempranas_sla()
    sql, _ = _sql_sin_movimiento(conn)
    assert "<= GETDATE()" in sql


def test_s5_sql_filtra_por_lider_con_parametro(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    db_module.get_alertas_tempranas_sla(lider="Alejandro Aguilar")
    sql, params = _sql_sin_movimiento(conn)
    assert "LOWER(LTRIM(RTRIM(p.LT_Asignado))) = LOWER(LTRIM(RTRIM(%s)))" in sql
    assert params == ("Alejandro Aguilar",)


@pytest.mark.parametrize("lider", [None, "", "todos", "TODAS", "all"])
def test_s5_sql_sin_lider_no_agrega_filtro(monkeypatch, lider):
    conn = FakeConn()
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    db_module.get_alertas_tempranas_sla(lider=lider)
    sql, params = _sql_sin_movimiento(conn)
    assert "%s" not in sql
    assert params == ()


def test_s5_get_alertas_integra_las_filas_de_la_consulta_con_el_resultado(monkeypatch):
    def responder(sql, params):
        if "Proyecto_Bitacora" in sql:
            return [_proyecto(pid=7, dias=15), _proyecto(pid=8, dias=2)]
        return []

    monkeypatch.setattr(db_module, "get_db_connection", lambda: FakeConn(responder))
    res = db_module.get_alertas_tempranas_sla(severidad="advertencia", tipo="proyecto", limite=10)
    assert [a["proyecto_id"] for a in res["alertas"]] == [7]
    assert res["resumen"]["proyectos_sin_movimiento"] == 1
    assert res["resumen"]["proyectos_con_alertas"] == 1
