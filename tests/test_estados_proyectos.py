"""
Estados de proyectos (odd/tasks/estados-bitacora-proyectos.md, T1: S1, S3 400, S4).

S1: catálogo Generado / En ejecucion / En revision / Cerrado; 'Atendido' legado = 'Cerrado'.
S3: sin nota de cierre/revisión el PUT responde 400 y no modifica el proyecto.
S4: script de migración (dry-run por defecto, --apply con respaldo y transacción única).

La base de pruebas es la de producción: todo acceso a datos está simulado (conexiones y cursores falsos).
"""

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.auth as auth_module
import backend.db as db_module
import backend.main as main_module
from backend.main import app
from tests.conftest import create_portal_jwt

client = TestClient(app)

MSG_REVISION = "Debe documentar el motivo para pasar el proyecto a 'En revisión'"
MSG_CIERRE = "Debe documentar la información de cierre para pasar el proyecto a 'Cerrado'"


# ---------------------------------------------------------------------------
# Conexión falsa: registra SQL y responde con una función
# ---------------------------------------------------------------------------

class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((" ".join(str(sql).split()), params))
        self._rows = self.conn.responder(self, " ".join(str(sql).split()), params)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConn:
    def __init__(self, responder=None):
        self.executed = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.responder = responder or (lambda cur, sql, params: [{"total": 0}])

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True

    def sqls(self):
        return [sql for sql, _ in self.executed]


# ---------------------------------------------------------------------------
# Usuario / PUT
# ---------------------------------------------------------------------------

@pytest.fixture
def app_user(monkeypatch):
    def fake_jit(username, nombre_completo=None, default_rol="PM", email=None):
        return {
            "id": 900, "username": username, "nombre_completo": "Alejandro Aguilar",
            "email": f"{username}@clarovtr.cl", "rol": "ADMIN", "lt_asignado": None, "activo": 1,
        }

    monkeypatch.setattr(auth_module, "get_or_create_jit_user", fake_jit)


@pytest.fixture
def put_env(app_user, monkeypatch):
    """Mockea la lectura del estado actual y la escritura del PUT."""
    state = {"current": {"ID": 123, "Estado": "Generado", "LT_Asignado": None}, "updates": []}

    def fake_get(proyecto_id):
        return state["current"]

    def fake_update(**kwargs):
        state["updates"].append(kwargs)
        return {
            "success": True,
            "data": {"ID": kwargs["proyecto_id"], "Estado": kwargs["estado"], "LT_Asignado": kwargs["lt_asignado"]},
            "was_assigned": False,
        }

    monkeypatch.setattr(main_module, "get_proyecto_by_id", fake_get)
    monkeypatch.setattr(main_module, "update_proyecto", fake_update)
    monkeypatch.setattr(main_module, "notificar_asignacion_lti_bg", lambda **kw: None)
    return state


def _put(estado, nota_estado=None, lt_asignado=None, proyecto_id=123):
    body = {"cliente": "Cliente QA", "estado": estado, "detalle": "Detalle QA", "lt_asignado": lt_asignado}
    if nota_estado is not None:
        body["nota_estado"] = nota_estado
    token = create_portal_jwt(username="alejandro.aguilar", admin_level=2, tool_access={"app-lti": "operador"})
    return client.put(f"/api/proyectos/{proyecto_id}", json=body, headers={"Authorization": f"Bearer {token}"})


# --- S1: catálogo ---------------------------------------------------------

def test_s1_catalogo_canonico_tiene_cuatro_estados():
    assert db_module.CANONICAL_ESTADOS_SHAREPOINT == ["Generado", "En ejecucion", "En revision", "Cerrado"]


def test_s1_get_estados_list_devuelve_cuatro_estados(monkeypatch):
    conn = FakeConn(lambda cur, sql, params: [{"ESTADO_OTP": "Abierta"}])
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    res = db_module.get_estados_list()
    assert res["estados_sharepoint"] == ["Generado", "En ejecucion", "En revision", "Cerrado"]
    assert res["estados_sga"] == ["Abierta"]


# --- S1: PUT acepta y normaliza ------------------------------------------

@pytest.mark.parametrize("enviado,esperado,nota", [
    ("Generado", "Generado", None),
    ("generado", "Generado", None),
    ("En ejecucion", "En ejecucion", None),
    ("en ejecución", "En ejecucion", None),
    ("EN EJECUCIÓN", "En ejecucion", None),
    ("En revision", "En revision", "Falta validar el pase"),
    ("en revisión", "En revision", "Falta validar el pase"),
    ("Cerrado", "Cerrado", "Entregado y conforme"),
    ("cerrado", "Cerrado", "Entregado y conforme"),
    ("atendido", "Cerrado", "Entregado y conforme"),
    ("Atendido", "Cerrado", "Entregado y conforme"),
])
def test_s1_put_acepta_y_normaliza_estados(put_env, enviado, esperado, nota):
    res = _put(enviado, nota_estado=nota)
    assert res.status_code == 200, res.text
    assert len(put_env["updates"]) == 1
    assert put_env["updates"][0]["estado"] == esperado


def test_s1_put_estado_invalido_es_400_con_los_cuatro_permitidos(put_env):
    res = _put("Pausado")
    assert res.status_code == 400
    assert res.json()["detail"] == (
        "Estado inválido. Los estados permitidos son: Generado, En ejecucion, En revision, Cerrado"
    )
    assert put_env["updates"] == []


# --- S3: nota obligatoria -------------------------------------------------

@pytest.mark.parametrize("nota", [None, "", "   "])
def test_s3_en_revision_sin_nota_es_400(put_env, nota):
    res = _put("En revision", nota_estado=nota)
    assert res.status_code == 400
    assert res.json()["detail"] == MSG_REVISION
    assert put_env["updates"] == []


@pytest.mark.parametrize("nota", [None, "", "   "])
def test_s3_cerrado_sin_nota_es_400(put_env, nota):
    res = _put("Cerrado", nota_estado=nota)
    assert res.status_code == 400
    assert res.json()["detail"] == MSG_CIERRE
    assert put_env["updates"] == []


def test_s3_atendido_legado_hacia_cerrado_sin_nota_es_400(put_env):
    res = _put("atendido")
    assert res.status_code == 400
    assert res.json()["detail"] == MSG_CIERRE
    assert put_env["updates"] == []


def test_s3_con_nota_el_put_actualiza(put_env):
    res = _put("En revision", nota_estado="  Pendiente de validación del PM  ")
    assert res.status_code == 200, res.text
    assert len(put_env["updates"]) == 1
    assert put_env["updates"][0]["estado"] == "En revision"
    assert res.json()["data"]["Estado"] == "En revision"


@pytest.mark.parametrize("actual,enviado", [
    ("En revision", "En revision"),
    ("Cerrado", "Cerrado"),
    ("Atendido", "Cerrado"),
    ("Atendido", "atendido"),
])
def test_s3_sin_cambio_de_estado_no_exige_nota(put_env, actual, enviado):
    put_env["current"] = {"ID": 123, "Estado": actual, "LT_Asignado": "Juan Barrera"}
    res = _put(enviado, lt_asignado="Juan Barrera")
    assert res.status_code == 200, res.text
    assert len(put_env["updates"]) == 1


def test_s3_proyecto_inexistente_es_404_sin_actualizar(put_env):
    put_env["current"] = None
    res = _put("Cerrado", nota_estado="Cierre")
    assert res.status_code == 404
    assert res.json()["detail"] == "Proyecto no encontrado"
    assert put_env["updates"] == []


# --- S1 / L4-D3: En ejecucion automático ----------------------------------

def test_s1_put_generado_con_lti_asignado_queda_en_ejecucion(put_env):
    res = _put("Generado", lt_asignado="Juan Barrera")
    assert res.status_code == 200, res.text
    assert put_env["updates"][0]["estado"] == "En ejecucion"


@pytest.mark.parametrize("lt", [None, "", "   ", "Sin asignar", "sin asignar"])
def test_s1_put_generado_sin_lti_sigue_generado(put_env, lt):
    res = _put("Generado", lt_asignado=lt)
    assert res.status_code == 200, res.text
    assert put_env["updates"][0]["estado"] == "Generado"


def test_s1_put_no_degrada_en_revision_con_lti(put_env):
    put_env["current"] = {"ID": 123, "Estado": "En revision", "LT_Asignado": "Juan Barrera"}
    res = _put("En revision", lt_asignado="Juan Barrera")
    assert res.status_code == 200, res.text
    assert put_env["updates"][0]["estado"] == "En revision"


# --- S1: asignación desde el backlog --------------------------------------

def test_s1_backlog_crea_proyecto_en_ejecucion(monkeypatch):
    creates = []
    monkeypatch.setattr(db_module, "get_backlog_proyecto", lambda n: {"CLI_CLIENTE": "CLIENTE QA", "PRO_ING_PROYECTO": None})
    monkeypatch.setattr(db_module, "check_proyecto_exists", lambda n: None)

    def fake_create(**kwargs):
        creates.append(kwargs)
        return {"success": True, "data": {"ID": 1, "Estado": kwargs["estado"]}}

    monkeypatch.setattr(db_module, "create_solicitud_lti", fake_create)
    res = db_module.assign_lti_from_backlog("QA-777", "Juan Barrera", actor_nombre="Actor")
    assert res["success"] and res["action"] == "created"
    assert creates[0]["estado"] == "En ejecucion"


def test_s1_create_solicitud_lti_inserta_el_estado_pedido(monkeypatch):
    def responder(cur, sql, params):
        if "SELECT TOP 1" in sql:
            return []
        if "MAX(ID)" in sql:
            return [{"next_id": 5}]
        return [{"ID": 5}]

    conn = FakeConn(responder)
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    res = db_module.create_solicitud_lti(
        cliente="CLIENTE QA", numero_proyecto="QA-1", lt_asignado="Juan Barrera",
        estado="En ejecucion", fecha_solicitud="2026-10-16", detalle="D"
    )
    assert res["success"]
    inserts = [p for sql, p in conn.executed if sql.startswith("INSERT INTO dbo.Proyectos")]
    assert len(inserts) == 1
    assert inserts[0][4] == "En ejecucion"


def test_s1_create_solicitud_lti_sin_estado_sigue_generado(monkeypatch):
    def responder(cur, sql, params):
        if "SELECT TOP 1" in sql:
            return []
        if "MAX(ID)" in sql:
            return [{"next_id": 5}]
        return [{"ID": 5}]

    conn = FakeConn(responder)
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    db_module.create_solicitud_lti(
        cliente="CLIENTE QA", numero_proyecto="QA-1", fecha_solicitud="2026-10-16", detalle="D"
    )
    inserts = [p for sql, p in conn.executed if sql.startswith("INSERT INTO dbo.Proyectos")]
    assert inserts[0][4] == "Generado"


def test_s1_update_proyecto_lt_pasa_generado_a_en_ejecucion_sin_degradar(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    monkeypatch.setattr(db_module, "get_proyecto_by_id", lambda pid: {"ID": pid})
    db_module.update_proyecto_lt(55, "Juan Barrera")
    updates = [(sql, p) for sql, p in conn.executed if sql.startswith("UPDATE dbo.Proyectos")]
    assert len(updates) == 1
    sql, params = updates[0]
    assert "Estado = CASE WHEN Estado = 'Generado' THEN 'En ejecucion' ELSE Estado END" in sql
    assert params == ("Juan Barrera", 55)
    assert conn.commits == 1


# --- S1: tolerancia a 'Atendido' en KPIs, recordatorios y alertas ---------

def _kpi_responder(cur, sql, params):
    if "COUNT(1) as total" in sql and "registrosRF_SD_SM" not in sql and "registrosSM_RFC" not in sql:
        if "'Cerrado'" in sql:
            return [{"total": 1}]
        if "'En ejecucion'" in sql:
            return [{"total": 3}]
        return [{"total": 4}]
    return [{"total": 0}]


def test_s1_kpis_en_curso_y_efectividad_usan_los_estados_nuevos(monkeypatch):
    conn = FakeConn(_kpi_responder)
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    kpis = db_module.get_dashboard_kpis()
    sqls = conn.sqls()
    assert any("p.Estado IN ('En ejecucion', 'En revision')" in s for s in sqls)
    assert any("p.Estado IN ('Cerrado', 'Atendido')" in s for s in sqls)
    assert not any("p.Estado = 'Generado'" in s for s in sqls)
    assert kpis["proyectos_en_curso"] == 3
    assert kpis["proyectos_cerrados"] == 1
    assert kpis["proyectos_atendidos"] == 1
    assert kpis["efectividad"] == 25.0


def test_s1_kpis_en_curso_mantiene_el_filtro_de_lti(monkeypatch):
    conn = FakeConn(_kpi_responder)
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    db_module.get_dashboard_kpis(lt_filter="Juan Barrera")
    por_lti = {sql: p for sql, p in conn.executed if "p.Estado IN" in sql}
    assert len(por_lti) == 2
    for sql, params in por_lti.items():
        assert "p.LT_Asignado = %s" in sql
        assert params == ("Juan Barrera",)


def test_s1_recordatorios_excluyen_cerrado_y_atendido():
    conn = FakeConn(lambda cur, sql, params: [])
    db_module.get_proyectos_pendientes_recordatorio(conn=conn)
    sql = conn.sqls()[0]
    assert "ISNULL(p.Estado, '') NOT IN ('Cerrado', 'Atendido')" in sql
    assert "<> 'Atendido'" not in sql


def test_s1_alertas_sla_tratan_cerrado_y_atendido_como_cerrados(monkeypatch):
    conn = FakeConn(lambda cur, sql, params: [])
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    db_module.get_alertas_tempranas_sla()
    sqls = [s for s in conn.sqls() if "OUTER APPLY" in s]
    assert len(sqls) == 2
    for sql in sqls:
        assert "<> 'Atendido'" not in sql
        assert "p.Estado NOT IN ('Cerrado', 'Atendido')" in sql
        assert "CASE WHEN p.Estado NOT IN ('Cerrado', 'Atendido') THEN 0 ELSE 1 END" in sql


def test_s1_filtro_por_estado_cerrado_incluye_atendido_legado(monkeypatch):
    conn = FakeConn(lambda cur, sql, params: [])
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    db_module.get_proyectos(estado_sp="Cerrado")
    sql, params = [e for e in conn.executed if "FROM dbo.Proyectos" in e[0]][0]
    assert "p.Estado IN ('Cerrado', 'Atendido')" in sql
    assert "Cerrado" not in (params or ())


def test_s1_filtro_por_estado_normaliza_acentos(monkeypatch):
    conn = FakeConn(lambda cur, sql, params: [])
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    db_module.get_proyectos(estado_sp="En ejecución")
    sql, params = [e for e in conn.executed if "FROM dbo.Proyectos" in e[0]][0]
    assert "p.Estado = %s" in sql
    assert "En ejecucion" in params


# ---------------------------------------------------------------------------
# S4 — script de migración
# ---------------------------------------------------------------------------

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrar_estados_proyectos.py"


@pytest.fixture
def migracion():
    spec = importlib.util.spec_from_file_location("migrar_estados_proyectos", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MigrationConn(FakeConn):
    """Tabla en memoria que entiende los UPDATE del script (sin tocar ninguna BD)."""

    def __init__(self, rows):
        super().__init__()
        self.rows = rows
        self.fail_on_update = None
        self.log = []

    def commit(self):
        super().commit()
        self.log.append("commit")

    def rollback(self):
        super().rollback()
        self.log.append("rollback")

    def cursor(self):
        cur = FakeCursor(self)
        conn = self

        def responder(c, sql, params):
            if sql.startswith("SELECT"):
                conn.log.append("select")
                return [dict(r) for r in conn.rows]
            conn.log.append("update")
            if conn.fail_on_update and conn.fail_on_update in sql:
                raise RuntimeError("fallo simulado")
            if "SET Estado = 'Cerrado'" in sql:
                tocados = [r for r in conn.rows if r["Estado"] == "Atendido"]
                for r in tocados:
                    r["Estado"] = "Cerrado"
            else:
                tocados = [r for r in conn.rows if r["Estado"] == "Generado" and conn_asignado(r["LT_Asignado"])]
                for r in tocados:
                    r["Estado"] = "En ejecucion"
            c.rowcount = len(tocados)
            return []

        self.responder = responder
        return cur


def conn_asignado(lt):
    return bool(lt and str(lt).strip() and str(lt).strip().lower() != "sin asignar")


def _filas():
    return [
        {"ID": 1, "Estado": "Atendido", "LT_Asignado": "Juan Barrera"},
        {"ID": 2, "Estado": "Atendido", "LT_Asignado": None},
        {"ID": 3, "Estado": "Generado", "LT_Asignado": "Erwin Sandoval"},
        {"ID": 4, "Estado": "Generado", "LT_Asignado": None},
        {"ID": 5, "Estado": "Generado", "LT_Asignado": "  "},
        {"ID": 6, "Estado": "Generado", "LT_Asignado": "Sin Asignar"},
        {"ID": 7, "Estado": "En revision", "LT_Asignado": "Juan Barrera"},
        {"ID": 8, "Estado": "Cerrado", "LT_Asignado": "Juan Barrera"},
    ]


@pytest.mark.parametrize("estado,lt,esperado", [
    ("Atendido", "Juan Barrera", "Cerrado"),
    ("Atendido", None, "Cerrado"),
    ("Generado", "Erwin Sandoval", "En ejecucion"),
    ("Generado", None, "Generado"),
    ("Generado", "", "Generado"),
    ("Generado", "   ", "Generado"),
    ("Generado", "sin asignar", "Generado"),
    ("Generado", "SIN ASIGNAR", "Generado"),
    ("En revision", "Juan Barrera", "En revision"),
    ("En ejecucion", "Juan Barrera", "En ejecucion"),
    ("Cerrado", "Juan Barrera", "Cerrado"),
])
def test_s4_target_estado(migracion, estado, lt, esperado):
    assert migracion.target_estado(estado, lt) == esperado


def test_s4_dry_run_solo_lee_y_no_escribe(migracion, tmp_path, capsys):
    conn = MigrationConn(_filas())
    antes = [dict(r) for r in conn.rows]
    res = migracion.run_migration(conn, apply=False, backup_dir=tmp_path)
    assert conn.rows == antes
    assert all(s.startswith("SELECT") for s in conn.sqls())
    assert conn.commits == 0
    assert list(tmp_path.iterdir()) == []
    assert res["total_a_cambiar"] == 3
    assert res["cambios"] == {("Atendido", "Cerrado"): 2, ("Generado", "En ejecucion"): 1}
    out = capsys.readouterr().out
    assert "Atendido -> Cerrado: 2" in out
    assert "Generado -> En ejecucion: 1" in out
    assert "dry-run" in out.lower()


def test_s4_apply_respalda_antes_de_actualizar_y_hace_commit_unico(migracion, tmp_path):
    conn = MigrationConn(_filas())
    res = migracion.run_migration(conn, apply=True, backup_dir=tmp_path)
    archivos = list(tmp_path.glob("proyectos_estados_*.json"))
    assert len(archivos) == 1
    respaldo = json.loads(archivos[0].read_text(encoding="utf-8"))
    assert respaldo == _filas()  # estados originales de TODAS las filas
    assert conn.log == ["select", "update", "update", "commit"]
    estados = {r["ID"]: r["Estado"] for r in conn.rows}
    assert estados == {1: "Cerrado", 2: "Cerrado", 3: "En ejecucion", 4: "Generado",
                       5: "Generado", 6: "Generado", 7: "En revision", 8: "Cerrado"}
    assert res["total_a_cambiar"] == 3
    assert res["respaldo"] == str(archivos[0])


def test_s4_apply_crea_el_directorio_de_respaldo(migracion, tmp_path):
    destino = tmp_path / "nuevo" / "backups_iacdi"
    migracion.run_migration(MigrationConn(_filas()), apply=True, backup_dir=destino)
    assert len(list(destino.glob("proyectos_estados_*.json"))) == 1


def test_s4_apply_es_idempotente(migracion, tmp_path):
    conn = MigrationConn(_filas())
    primera = migracion.run_migration(conn, apply=True, backup_dir=tmp_path)
    segunda = migracion.run_migration(conn, apply=True, backup_dir=tmp_path)
    assert primera["total_a_cambiar"] == 3
    assert segunda["total_a_cambiar"] == 0
    assert segunda["cambios"] == {}


def test_s4_apply_con_error_hace_rollback_y_no_commit(migracion, tmp_path):
    conn = MigrationConn(_filas())
    conn.fail_on_update = "'En ejecucion'"
    with pytest.raises(RuntimeError):
        migracion.run_migration(conn, apply=True, backup_dir=tmp_path)
    assert conn.commits == 0
    assert conn.rollbacks == 1


def test_s4_main_por_defecto_es_dry_run(migracion, monkeypatch, tmp_path):
    conn = MigrationConn(_filas())
    monkeypatch.setattr(migracion, "get_db_connection", lambda: conn)
    assert migracion.main([]) == 0
    assert conn.commits == 0
    assert all(s.startswith("SELECT") for s in conn.sqls())
    assert conn.closed


def test_s4_main_apply_usa_el_directorio_de_respaldo_indicado(migracion, monkeypatch, tmp_path):
    conn = MigrationConn(_filas())
    monkeypatch.setattr(migracion, "get_db_connection", lambda: conn)
    assert migracion.main(["--apply", "--backup-dir", str(tmp_path)]) == 0
    assert conn.commits == 1
    assert len(list(tmp_path.glob("proyectos_estados_*.json"))) == 1
