"""
Bitácora y adjuntos de proyectos (odd/tasks/estados-bitacora-proyectos.md, T2: S2, S3, S6, S7).

S2/S3: la nota de revisión / cierre se guarda como entrada de bitácora en la MISMA transacción del UPDATE.
S6: entradas append-only (BITACORA / REVISION / CIERRE), más recientes primero.
S7: adjuntos en disco (máx 9 MB, lista blanca de extensiones, descarga autenticada).

La base de pruebas es la de producción: todo acceso a datos está simulado (conexiones y cursores falsos)
y los archivos viven en tmp_path.
"""

import datetime
import importlib.util
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.auth as auth_module
import backend.config as config_module
import backend.db as db_module
import backend.main as main_module
from backend.main import app
from tests.conftest import create_portal_jwt

client = TestClient(app)
ROOT = Path(__file__).resolve().parent.parent

MSG_NO_PROYECTO = "Proyecto no encontrado"
MSG_NO_ENTRADA = "Entrada de bitácora no encontrada"
MSG_NO_ADJUNTO = "Adjunto no encontrado"
EXT_LISTA = "pdf, png, jpg, jpeg, gif, webp, doc, docx, xls, xlsx, ppt, pptx, msg, eml, zip, txt, csv"
MAX_BYTES = 9 * 1024 * 1024


# ---------------------------------------------------------------------------
# Conexión falsa
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
        sql = " ".join(str(sql).split())
        self.conn.executed.append((sql, params))
        self._rows = self.conn.responder(self, sql, params) or []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConn:
    def __init__(self, responder=None):
        self.executed = []
        self.events = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.responder = responder or (lambda cur, sql, params: [])

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1
        self.events.append("commit")

    def rollback(self):
        self.rollbacks += 1
        self.events.append("rollback")

    def close(self):
        self.closed = True

    def sqls(self):
        return [sql for sql, _ in self.executed]


@pytest.fixture
def adjuntos_dir(tmp_path, monkeypatch):
    destino = tmp_path / "adjuntos"
    monkeypatch.setattr(config_module, "ADJUNTOS_DIR", str(destino))
    return destino


def _archivos(directorio):
    return [p for p in Path(directorio).rglob("*") if p.is_file()] if Path(directorio).exists() else []


# ---------------------------------------------------------------------------
# Usuario y proyecto
# ---------------------------------------------------------------------------

@pytest.fixture
def app_user(monkeypatch):
    roles = {}

    def fake_jit(username, nombre_completo=None, default_rol="PM", email=None):
        return {
            "id": 900, "username": username, "nombre_completo": "Alejandro Aguilar",
            "email": f"{username}@clarovtr.cl", "rol": roles.get(username, "ADMIN"),
            "lt_asignado": None, "activo": 1,
        }

    monkeypatch.setattr(auth_module, "get_or_create_jit_user", fake_jit)
    return roles


def _headers(username="alejandro.aguilar", admin_level=2, tool_perm="operador"):
    token = create_portal_jwt(username=username, admin_level=admin_level, tool_access={"app-lti": tool_perm})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def proyecto(app_user, monkeypatch):
    state = {"row": {"ID": 123, "Estado": "Generado", "LT_Asignado": None}}
    monkeypatch.setattr(main_module, "get_proyecto_by_id", lambda pid: state["row"])
    return state


# ===========================================================================
# Config (S7)
# ===========================================================================

def _load_config_copy():
    spec = importlib.util.spec_from_file_location("backend_config_copy", ROOT / "backend" / "config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_s7_config_valores_por_defecto(monkeypatch):
    monkeypatch.delenv("ADJUNTOS_DIR", raising=False)
    cfg = _load_config_copy()
    monkeypatch.delenv("ADJUNTOS_DIR", raising=False)
    assert cfg.ADJUNTOS_MAX_BYTES == MAX_BYTES
    assert ", ".join(cfg.ADJUNTOS_EXTENSIONES_PERMITIDAS) == EXT_LISTA
    if "ADJUNTOS_DIR" not in os.environ:
        assert cfg.ADJUNTOS_DIR == os.path.join(cfg.BASE_DIR, "data", "adjuntos")


def test_s7_config_adjuntos_dir_desde_variable_de_entorno(monkeypatch, tmp_path):
    monkeypatch.setenv("ADJUNTOS_DIR", str(tmp_path / "otro"))
    cfg = _load_config_copy()
    assert cfg.ADJUNTOS_DIR == str(tmp_path / "otro")


def test_s7_higiene_gitignore_deploy_y_env_example():
    assert "data/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "--exclude 'data/'" in (ROOT / "deploy_to_iacdi.sh").read_text(encoding="utf-8")
    assert "# ADJUNTOS_DIR=" in (ROOT / ".env.example").read_text(encoding="utf-8")


# ===========================================================================
# Tablas (idempotentes)
# ===========================================================================

def test_s6_init_bitacora_tables_crea_tablas_solo_si_no_existen(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    db_module.init_bitacora_tables()
    texto = "\n".join(conn.sqls())
    assert "IF OBJECT_ID('dbo.Proyecto_Bitacora', 'U') IS NULL" in texto
    assert "IF OBJECT_ID('dbo.Proyecto_Adjuntos', 'U') IS NULL" in texto
    # Bitácora, adjuntos and project associations (S4 of tours-busqueda-asociacion-kpis)
    assert texto.count("Proyecto_ID NUMERIC(18,0) NOT NULL") == 3
    for fragmento in (
        "ID INT IDENTITY(1,1) PRIMARY KEY",
        "Tipo VARCHAR(20) NOT NULL",
        "Texto NVARCHAR(MAX) NOT NULL",
        "Estado_Anterior NVARCHAR(50) NULL",
        "Estado_Nuevo NVARCHAR(50) NULL",
        "Autor_Username VARCHAR(100) NULL",
        "Autor_Nombre NVARCHAR(150) NULL",
        "Creado DATETIME NOT NULL DEFAULT GETDATE()",
        "Bitacora_ID INT NOT NULL",
        "Nombre_Original NVARCHAR(255) NOT NULL",
        "Nombre_Almacenado VARCHAR(100) NOT NULL",
        "Content_Type VARCHAR(150) NULL",
        "Tamano_Bytes INT NOT NULL",
    ):
        assert fragmento in texto, fragmento
    assert "IX_Proyecto_Bitacora_Proyecto_ID" in texto and "IX_Proyecto_Adjuntos_Bitacora_ID" in texto
    assert "DROP" not in texto.upper() and "DELETE" not in texto.upper()
    assert conn.commits == 1 and conn.closed


def test_s6_lifespan_inicializa_las_tablas_de_bitacora(monkeypatch):
    llamadas = []

    async def fake_scheduler():
        return None

    monkeypatch.setattr(main_module, "seed_default_users", lambda: llamadas.append("seed"))
    monkeypatch.setattr(main_module, "init_bitacora_tables", lambda: llamadas.append("bitacora"))
    monkeypatch.setattr(main_module, "reminder_scheduler_loop", fake_scheduler)
    with TestClient(app):
        pass
    assert llamadas == ["seed", "bitacora"]


def test_s6_lifespan_sobrevive_si_falla_init_de_bitacora(monkeypatch):
    async def fake_scheduler():
        return None

    def falla():
        raise RuntimeError("sin acceso")

    monkeypatch.setattr(main_module, "seed_default_users", lambda: None)
    monkeypatch.setattr(main_module, "init_bitacora_tables", falla)
    monkeypatch.setattr(main_module, "reminder_scheduler_loop", fake_scheduler)
    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 200


# ===========================================================================
# Capa de datos (S6)
# ===========================================================================

def test_s6_create_bitacora_entry_inserta_tipo_bitacora(monkeypatch):
    creado = datetime.datetime(2026, 10, 16, 9, 30, 0)
    conn = FakeConn(lambda cur, sql, params: [{"ID": 42, "Creado": creado}] if sql.startswith("INSERT") else [])
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    entry = db_module.create_bitacora_entry(123, "Reunión con el cliente", "alejandro.aguilar", "Alejandro Aguilar")
    insert_sql, params = conn.executed[0]
    assert insert_sql.startswith("INSERT INTO dbo.Proyecto_Bitacora")
    assert params == (123, "BITACORA", "Reunión con el cliente", None, None, "alejandro.aguilar", "Alejandro Aguilar")
    assert conn.commits == 1 and conn.closed
    assert entry == {
        "id": 42, "tipo": "BITACORA", "texto": "Reunión con el cliente",
        "estado_anterior": None, "estado_nuevo": None,
        "autor_username": "alejandro.aguilar", "autor_nombre": "Alejandro Aguilar",
        "creado": "2026-10-16T09:30:00", "adjuntos": [],
    }


def test_s6_create_bitacora_entry_error_hace_rollback(monkeypatch):
    def responder(cur, sql, params):
        raise RuntimeError("fallo simulado")

    conn = FakeConn(responder)
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    with pytest.raises(RuntimeError):
        db_module.create_bitacora_entry(123, "x", "u", "U")
    assert conn.commits == 0 and conn.rollbacks == 1 and conn.closed


def test_s6_get_bitacora_por_proyecto_mas_reciente_primero_con_adjuntos(monkeypatch):
    d1 = datetime.datetime(2026, 10, 15, 8, 0, 0)
    d2 = datetime.datetime(2026, 10, 16, 8, 0, 0)

    def responder(cur, sql, params):
        if "FROM dbo.Proyecto_Bitacora" in sql:
            return [
                {"ID": 2, "Tipo": "CIERRE", "Texto": "Cierre", "Estado_Anterior": "En revision",
                 "Estado_Nuevo": "Cerrado", "Autor_Username": "u", "Autor_Nombre": "U", "Creado": d2},
                {"ID": 1, "Tipo": "BITACORA", "Texto": "Inicio", "Estado_Anterior": None,
                 "Estado_Nuevo": None, "Autor_Username": "u", "Autor_Nombre": "U", "Creado": d1},
            ]
        if "FROM dbo.Proyecto_Adjuntos" in sql:
            return [{"ID": 7, "Bitacora_ID": 2, "Nombre_Original": "acta.pdf", "Content_Type": "application/pdf",
                     "Tamano_Bytes": 1234, "Creado": d2}]
        return []

    conn = FakeConn(responder)
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    result = db_module.get_bitacora_by_proyecto(123)
    bitacora_sql, bitacora_params = conn.executed[0]
    assert "ORDER BY Creado DESC, ID DESC" in bitacora_sql
    assert bitacora_params == (123,)
    assert [e["id"] for e in result] == [2, 1]
    assert result[0]["tipo"] == "CIERRE" and result[0]["estado_anterior"] == "En revision"
    assert result[0]["creado"] == "2026-10-16T08:00:00"
    assert result[0]["adjuntos"] == [{
        "id": 7, "nombre": "acta.pdf", "content_type": "application/pdf",
        "tamano_bytes": 1234, "creado": "2026-10-16T08:00:00",
    }]
    assert result[1]["adjuntos"] == []


def test_s7_get_bitacora_entry_filtra_por_proyecto(monkeypatch):
    conn = FakeConn(lambda cur, sql, params: [{"ID": 5, "Proyecto_ID": 123}])
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    assert db_module.get_bitacora_entry(123, 5)["ID"] == 5
    sql, params = conn.executed[0]
    assert "WHERE ID = %s AND Proyecto_ID = %s" in sql
    assert params == (5, 123)


def test_s7_get_adjunto_filtra_por_proyecto(monkeypatch):
    conn = FakeConn(lambda cur, sql, params: [])
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    assert db_module.get_adjunto(123, 9) is None
    sql, params = conn.executed[0]
    assert "WHERE ID = %s AND Proyecto_ID = %s" in sql
    assert params == (9, 123)


def test_s7_create_adjunto_inserta_metadatos(monkeypatch):
    creado = datetime.datetime(2026, 10, 16, 10, 0, 0)
    conn = FakeConn(lambda cur, sql, params: [{"ID": 8, "Creado": creado}])
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    meta = db_module.create_adjunto(5, 123, "acta.pdf", "abc.pdf", "application/pdf", 2048, "alejandro.aguilar")
    sql, params = conn.executed[0]
    assert sql.startswith("INSERT INTO dbo.Proyecto_Adjuntos")
    assert params == (5, 123, "acta.pdf", "abc.pdf", "application/pdf", 2048, "alejandro.aguilar")
    assert conn.commits == 1
    assert meta == {"id": 8, "nombre": "acta.pdf", "content_type": "application/pdf",
                    "tamano_bytes": 2048, "creado": "2026-10-16T10:00:00"}


# ===========================================================================
# S2 / S3 — nota de estado en la misma transacción del UPDATE
# ===========================================================================

def _responder_update(fail_on=None):
    def responder(cur, sql, params):
        if fail_on and fail_on in sql:
            raise RuntimeError("fallo simulado")
        if sql.startswith("SELECT ID, Cliente"):
            return [{"ID": 123, "Cliente": "C", "Numero_Proyecto": "000QA-1", "LT_Asignado": None,
                     "Estado": "Generado", "Detalle": "D", "Tipo_Servicio": "Otros", "Solicitante": "PM"}]
        if sql.startswith("INSERT INTO dbo.Proyecto_Bitacora"):
            return [{"ID": 31, "Creado": datetime.datetime(2026, 10, 16, 11, 0, 0)}]
        return []
    return responder


_BITACORA = {
    "tipo": "REVISION", "texto": "Falta validar el pase", "estado_anterior": "En ejecucion",
    "estado_nuevo": "En revision", "autor_username": "alejandro.aguilar", "autor_nombre": "Alejandro Aguilar",
}


def _update(**extra):
    return db_module.update_proyecto(
        proyecto_id=123, cliente="C", lt_asignado=None, estado="En revision", detalle="D",
        tipo_servicio="Otros", comentario=None, **extra
    )


def test_s2_update_proyecto_inserta_la_nota_en_la_misma_transaccion(monkeypatch):
    conn = FakeConn(_responder_update())
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    monkeypatch.setattr(db_module, "get_proyecto_by_id", lambda pid: {"ID": pid})
    result = _update(bitacora=dict(_BITACORA))
    verbos = [sql.split()[0] for sql in conn.sqls()]
    assert verbos == ["SELECT", "UPDATE", "INSERT"]
    assert conn.events == ["commit"] and conn.commits == 1
    insert_sql, params = conn.executed[2]
    assert "dbo.Proyecto_Bitacora" in insert_sql
    assert params == (123, "REVISION", "Falta validar el pase", "En ejecucion", "En revision",
                      "alejandro.aguilar", "Alejandro Aguilar")
    assert result["success"] and result["bitacora_entry_id"] == 31


def test_s2_update_proyecto_con_error_en_la_nota_hace_rollback_de_ambos(monkeypatch):
    conn = FakeConn(_responder_update(fail_on="INSERT INTO dbo.Proyecto_Bitacora"))
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    leido = []
    monkeypatch.setattr(db_module, "get_proyecto_by_id", lambda pid: leido.append(pid))
    result = _update(bitacora=dict(_BITACORA))
    assert conn.commits == 0 and conn.rollbacks == 1
    assert result["success"] is False and result["error"] == "db_error"
    assert leido == []


def test_s2_update_proyecto_con_error_en_el_update_no_inserta_la_nota(monkeypatch):
    conn = FakeConn(_responder_update(fail_on="UPDATE dbo.Proyectos"))
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    result = _update(bitacora=dict(_BITACORA))
    assert not any(s.startswith("INSERT") for s in conn.sqls())
    assert conn.commits == 0 and conn.rollbacks == 1
    assert result["success"] is False


def test_s2_update_proyecto_sin_nota_no_inserta_bitacora(monkeypatch):
    conn = FakeConn(_responder_update())
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    monkeypatch.setattr(db_module, "get_proyecto_by_id", lambda pid: {"ID": pid})
    result = _update()
    assert [s.split()[0] for s in conn.sqls()] == ["SELECT", "UPDATE"]
    assert conn.commits == 1
    assert result["success"] and result["bitacora_entry_id"] is None


# ===========================================================================
# S2 / S3 — PUT /api/proyectos/{id}
# ===========================================================================

@pytest.fixture
def put_env(proyecto, monkeypatch):
    state = {"updates": []}

    def fake_update(**kwargs):
        state["updates"].append(kwargs)
        return {
            "success": True,
            "data": {"ID": kwargs["proyecto_id"], "Estado": kwargs["estado"]},
            "was_assigned": False,
            "bitacora_entry_id": 77 if kwargs.get("bitacora") else None,
        }

    monkeypatch.setattr(main_module, "update_proyecto", fake_update)
    monkeypatch.setattr(main_module, "notificar_asignacion_lti_bg", lambda **kw: None)
    return state


def _put(estado, nota_estado=None, lt_asignado=None):
    body = {"cliente": "Cliente QA", "estado": estado, "detalle": "Detalle QA", "lt_asignado": lt_asignado}
    if nota_estado is not None:
        body["nota_estado"] = nota_estado
    return client.put("/api/proyectos/123", json=body, headers=_headers())


def test_s2_put_a_en_revision_con_nota_pasa_la_entrada_de_revision(put_env, proyecto):
    proyecto["row"] = {"ID": 123, "Estado": "En ejecucion", "LT_Asignado": "Juan Barrera"}
    res = _put("en revisión", nota_estado="  Falta validar el pase  ", lt_asignado="Juan Barrera")
    assert res.status_code == 200, res.text
    assert put_env["updates"][0]["bitacora"] == {
        "tipo": "REVISION", "texto": "Falta validar el pase", "estado_anterior": "En ejecucion",
        "estado_nuevo": "En revision", "autor_username": "alejandro.aguilar",
        "autor_nombre": "Alejandro Aguilar",
    }
    assert res.json()["bitacora_entry_id"] == 77


def test_s3_put_a_cerrado_con_nota_pasa_la_entrada_de_cierre(put_env, proyecto):
    proyecto["row"] = {"ID": 123, "Estado": "En revision", "LT_Asignado": "Juan Barrera"}
    res = _put("Cerrado", nota_estado="Entregado y conforme", lt_asignado="Juan Barrera")
    assert res.status_code == 200, res.text
    bitacora = put_env["updates"][0]["bitacora"]
    assert bitacora["tipo"] == "CIERRE"
    assert bitacora["estado_anterior"] == "En revision" and bitacora["estado_nuevo"] == "Cerrado"
    assert bitacora["texto"] == "Entregado y conforme"
    assert res.json()["bitacora_entry_id"] == 77


def test_s3_put_desde_atendido_legado_a_en_revision_registra_cerrado_como_anterior(put_env, proyecto):
    proyecto["row"] = {"ID": 123, "Estado": "Atendido", "LT_Asignado": "Juan Barrera"}
    res = _put("En revision", nota_estado="Se reabre", lt_asignado="Juan Barrera")
    assert res.status_code == 200, res.text
    assert put_env["updates"][0]["bitacora"]["estado_anterior"] == "Cerrado"


def test_s2_put_sin_cambio_de_estado_no_crea_entrada(put_env, proyecto):
    proyecto["row"] = {"ID": 123, "Estado": "En revision", "LT_Asignado": "Juan Barrera"}
    res = _put("En revision", nota_estado="Nota repetida", lt_asignado="Juan Barrera")
    assert res.status_code == 200, res.text
    assert "bitacora" not in put_env["updates"][0]
    assert res.json()["bitacora_entry_id"] is None


@pytest.mark.parametrize("estado,lt", [("Generado", None), ("En ejecucion", "Juan Barrera")])
def test_s2_put_a_otros_estados_con_nota_no_crea_entrada(put_env, estado, lt):
    res = _put(estado, nota_estado="Nota ignorada", lt_asignado=lt)
    assert res.status_code == 200, res.text
    assert "bitacora" not in put_env["updates"][0]
    assert res.json()["bitacora_entry_id"] is None


def test_s2_put_sin_nota_sigue_rechazado_y_no_crea_entrada(put_env):
    res = _put("En revision")
    assert res.status_code == 400
    assert put_env["updates"] == []


# ===========================================================================
# S6 — GET / POST /api/proyectos/{id}/bitacora
# ===========================================================================

def test_s6_get_bitacora_devuelve_la_lista(proyecto, monkeypatch):
    entradas = [{"id": 2, "tipo": "CIERRE", "adjuntos": []}, {"id": 1, "tipo": "BITACORA", "adjuntos": []}]
    pedidos = []
    monkeypatch.setattr(main_module, "get_bitacora_by_proyecto", lambda pid: pedidos.append(pid) or entradas)
    res = client.get("/api/proyectos/123/bitacora", headers=_headers())
    assert res.status_code == 200
    assert res.json() == entradas
    assert pedidos == [123]


def test_s6_get_bitacora_proyecto_inexistente_es_404(proyecto, monkeypatch):
    proyecto["row"] = None
    monkeypatch.setattr(main_module, "get_bitacora_by_proyecto", lambda pid: pytest.fail("no debe leer"))
    res = client.get("/api/proyectos/123/bitacora", headers=_headers())
    assert res.status_code == 404
    assert res.json()["detail"] == MSG_NO_PROYECTO


def test_s6_get_bitacora_rol_pm_es_403(proyecto, app_user):
    app_user["juan.perez"] = "PM"
    res = client.get("/api/proyectos/123/bitacora", headers=_headers("juan.perez", 0, "lectura"))
    assert res.status_code == 403


@pytest.fixture
def post_env(proyecto, monkeypatch):
    state = {"creates": []}

    def fake_create(proyecto_id, texto, autor_username, autor_nombre):
        state["creates"].append((proyecto_id, texto, autor_username, autor_nombre))
        return {"id": 50, "tipo": "BITACORA", "texto": texto, "adjuntos": []}

    monkeypatch.setattr(main_module, "create_bitacora_entry", fake_create)
    return state


def test_s6_post_bitacora_crea_entrada_con_autor(post_env):
    res = client.post("/api/proyectos/123/bitacora", json={"texto": "  Visita a terreno  "}, headers=_headers())
    assert res.status_code == 201, res.text
    assert res.json()["id"] == 50 and res.json()["tipo"] == "BITACORA"
    assert post_env["creates"] == [(123, "Visita a terreno", "alejandro.aguilar", "Alejandro Aguilar")]


@pytest.mark.parametrize("body", [{"texto": ""}, {"texto": "   "}, {"texto": None}, {}])
def test_s6_post_bitacora_texto_vacio_es_400(post_env, body):
    res = client.post("/api/proyectos/123/bitacora", json=body, headers=_headers())
    assert res.status_code == 400
    assert res.json()["detail"] == "El texto de la bitácora es obligatorio"
    assert post_env["creates"] == []


def test_s6_post_bitacora_texto_de_20000_caracteres_es_valido(post_env):
    res = client.post("/api/proyectos/123/bitacora", json={"texto": "a" * 20000}, headers=_headers())
    assert res.status_code == 201, res.text


def test_s6_post_bitacora_texto_de_mas_de_20000_caracteres_es_400(post_env):
    res = client.post("/api/proyectos/123/bitacora", json={"texto": "a" * 20001}, headers=_headers())
    assert res.status_code == 400
    assert res.json()["detail"] == "El texto de la bitácora no puede superar 20000 caracteres"
    assert post_env["creates"] == []


def test_s6_post_bitacora_proyecto_inexistente_es_404(post_env, proyecto):
    proyecto["row"] = None
    res = client.post("/api/proyectos/123/bitacora", json={"texto": "x"}, headers=_headers())
    assert res.status_code == 404
    assert res.json()["detail"] == MSG_NO_PROYECTO
    assert post_env["creates"] == []


# ===========================================================================
# S7 — POST /api/proyectos/{id}/bitacora/{entry_id}/adjuntos
# ===========================================================================

@pytest.fixture
def upload_env(proyecto, adjuntos_dir, monkeypatch):
    state = {"inserts": [], "entry": {"ID": 5, "Proyecto_ID": 123}, "fail_insert": False}

    def fake_entry(proyecto_id, entry_id):
        state["entry_lookup"] = (proyecto_id, entry_id)
        return state["entry"]

    def fake_create_adjunto(bitacora_id, proyecto_id, nombre_original, nombre_almacenado,
                            content_type, tamano_bytes, autor_username):
        if state["fail_insert"]:
            raise RuntimeError("fallo simulado")
        state["inserts"].append({
            "bitacora_id": bitacora_id, "proyecto_id": proyecto_id, "nombre_original": nombre_original,
            "nombre_almacenado": nombre_almacenado, "content_type": content_type,
            "tamano_bytes": tamano_bytes, "autor_username": autor_username,
        })
        return {"id": 9, "nombre": nombre_original, "content_type": content_type,
                "tamano_bytes": tamano_bytes, "creado": "2026-10-16T10:00:00"}

    monkeypatch.setattr(main_module, "get_bitacora_entry", fake_entry)
    monkeypatch.setattr(main_module, "create_adjunto", fake_create_adjunto)
    return state


def _upload(nombre, contenido, content_type="application/pdf", entry_id=5):
    return client.post(
        f"/api/proyectos/123/bitacora/{entry_id}/adjuntos",
        files={"archivo": (nombre, contenido, content_type)},
        headers=_headers(),
    )


def test_s7_subida_exitosa_guarda_archivo_y_metadatos(upload_env, adjuntos_dir):
    res = _upload("Acta Final.pdf", b"%PDF-1.4 contenido")
    assert res.status_code == 201, res.text
    assert res.json() == {"id": 9, "nombre": "Acta Final.pdf", "content_type": "application/pdf",
                          "tamano_bytes": 18, "creado": "2026-10-16T10:00:00"}
    archivos = _archivos(adjuntos_dir)
    assert len(archivos) == 1
    assert archivos[0].read_bytes() == b"%PDF-1.4 contenido"
    insertado = upload_env["inserts"][0]
    stem, ext = archivos[0].name.rsplit(".", 1)
    assert ext == "pdf" and len(stem) == 32 and int(stem, 16) >= 0  # uuid4 hex
    assert insertado["nombre_almacenado"] == archivos[0].name
    assert insertado["bitacora_id"] == 5 and insertado["proyecto_id"] == 123
    assert insertado["tamano_bytes"] == 18 and insertado["autor_username"] == "alejandro.aguilar"
    assert upload_env["entry_lookup"] == (123, 5)


def test_s7_extension_en_mayusculas_se_acepta_y_se_guarda_en_minusculas(upload_env, adjuntos_dir):
    res = _upload("INFORME.PDF", b"datos")
    assert res.status_code == 201, res.text
    assert _archivos(adjuntos_dir)[0].name.endswith(".pdf")


@pytest.mark.parametrize("ext", ["pdf", "png", "jpg", "jpeg", "gif", "webp", "doc", "docx", "xls", "xlsx",
                                 "ppt", "pptx", "msg", "eml", "zip", "txt", "csv"])
def test_s7_extensiones_permitidas(upload_env, adjuntos_dir, ext):
    res = _upload(f"archivo.{ext}", b"datos", content_type="application/octet-stream")
    assert res.status_code == 201, res.text


@pytest.mark.parametrize("nombre", ["virus.exe", "script.php", "pagina.html", "README", "archivo.pdf.exe", ".pdf.sh"])
def test_s7_extension_no_permitida_es_400_sin_efectos(upload_env, adjuntos_dir, nombre):
    res = _upload(nombre, b"datos")
    assert res.status_code == 400
    assert res.json()["detail"] == f"Tipo de archivo no permitido. Formatos aceptados: {EXT_LISTA}"
    assert _archivos(adjuntos_dir) == []
    assert upload_env["inserts"] == []


def test_s7_archivo_vacio_es_400_sin_efectos(upload_env, adjuntos_dir):
    res = _upload("vacio.pdf", b"")
    assert res.status_code == 400
    assert res.json()["detail"] == "El archivo está vacío"
    assert _archivos(adjuntos_dir) == []
    assert upload_env["inserts"] == []


def test_s7_archivo_de_exactamente_9_mb_se_acepta(upload_env, adjuntos_dir):
    res = _upload("limite.zip", b"a" * MAX_BYTES, content_type="application/zip")
    assert res.status_code == 201, res.text
    assert res.json()["tamano_bytes"] == MAX_BYTES
    assert _archivos(adjuntos_dir)[0].stat().st_size == MAX_BYTES


def test_s7_archivo_de_mas_de_9_mb_es_413_sin_archivo_parcial_ni_insert(upload_env, adjuntos_dir):
    res = _upload("grande.zip", b"a" * (MAX_BYTES + 1), content_type="application/zip")
    assert res.status_code == 413
    assert res.json()["detail"] == "El archivo supera el máximo de 9 MB"
    assert _archivos(adjuntos_dir) == []
    assert upload_env["inserts"] == []


def test_s7_entrada_de_otro_proyecto_es_404_sin_efectos(upload_env, adjuntos_dir):
    upload_env["entry"] = None
    res = _upload("acta.pdf", b"datos", entry_id=999)
    assert res.status_code == 404
    assert res.json()["detail"] == MSG_NO_ENTRADA
    assert _archivos(adjuntos_dir) == []
    assert upload_env["inserts"] == []


def test_s7_proyecto_inexistente_es_404(upload_env, proyecto, adjuntos_dir):
    proyecto["row"] = None
    res = _upload("acta.pdf", b"datos")
    assert res.status_code == 404
    assert res.json()["detail"] == MSG_NO_PROYECTO
    assert _archivos(adjuntos_dir) == []


def test_s7_si_falla_el_insert_se_borra_el_archivo(upload_env, adjuntos_dir):
    upload_env["fail_insert"] = True
    res = _upload("acta.pdf", b"datos")
    assert res.status_code == 500
    assert _archivos(adjuntos_dir) == []


def test_s7_nombre_original_se_reduce_a_basename(upload_env):
    res = _upload("..\\..\\etc/secreto/informe final.pdf", b"datos")
    assert res.status_code == 201, res.text
    assert upload_env["inserts"][0]["nombre_original"] == "informe final.pdf"


def test_s7_nombre_original_se_trunca_a_255_caracteres(upload_env):
    res = _upload("a" * 300 + ".pdf", b"datos")
    assert res.status_code == 201, res.text
    assert len(upload_env["inserts"][0]["nombre_original"]) == 255


def test_s7_subida_sin_rol_lti_o_admin_es_403(upload_env, adjuntos_dir, app_user):
    app_user["juan.perez"] = "PM"
    res = client.post(
        "/api/proyectos/123/bitacora/5/adjuntos",
        files={"archivo": ("acta.pdf", b"datos", "application/pdf")},
        headers=_headers("juan.perez", 0, "lectura"),
    )
    assert res.status_code == 403
    assert _archivos(adjuntos_dir) == []


# ===========================================================================
# S7 — GET /api/proyectos/{id}/adjuntos/{adjunto_id}
# ===========================================================================

@pytest.fixture
def download_env(proyecto, adjuntos_dir, monkeypatch):
    adjuntos_dir.mkdir(parents=True)
    state = {"row": {"ID": 9, "Proyecto_ID": 123, "Nombre_Original": "Informe Ñandú.pdf",
                     "Nombre_Almacenado": "abc123.pdf"}, "lookup": None}
    (adjuntos_dir / "abc123.pdf").write_bytes(b"%PDF contenido")

    def fake_get(proyecto_id, adjunto_id):
        state["lookup"] = (proyecto_id, adjunto_id)
        return state["row"]

    monkeypatch.setattr(main_module, "get_adjunto", fake_get)
    return state


def test_s7_descarga_devuelve_archivo_con_cabeceras_seguras(download_env):
    res = client.get("/api/proyectos/123/adjuntos/9", headers=_headers())
    assert res.status_code == 200, res.text
    assert res.content == b"%PDF contenido"
    assert res.headers["content-type"] == "application/octet-stream"
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["content-disposition"] == "attachment; filename*=utf-8''Informe%20%C3%91and%C3%BA.pdf"
    assert download_env["lookup"] == (123, 9)


def test_s7_descarga_con_nombre_ascii_usa_filename_simple(download_env):
    download_env["row"]["Nombre_Original"] = "informe.pdf"
    res = client.get("/api/proyectos/123/adjuntos/9", headers=_headers())
    assert res.headers["content-disposition"] == 'attachment; filename="informe.pdf"'


def test_s7_descarga_de_adjunto_de_otro_proyecto_es_404(download_env):
    download_env["row"] = None
    res = client.get("/api/proyectos/123/adjuntos/9", headers=_headers())
    assert res.status_code == 404
    assert res.json()["detail"] == MSG_NO_ADJUNTO


@pytest.mark.parametrize("almacenado", ["../secreto.txt", "../../etc/passwd", "/etc/passwd", "sub/../../secreto.txt"])
def test_s7_descarga_no_sale_del_directorio_de_adjuntos(download_env, adjuntos_dir, almacenado):
    (adjuntos_dir.parent / "secreto.txt").write_text("no se debe filtrar")
    download_env["row"]["Nombre_Almacenado"] = almacenado
    res = client.get("/api/proyectos/123/adjuntos/9", headers=_headers())
    assert res.status_code == 404
    assert res.json()["detail"] == MSG_NO_ADJUNTO
    assert "no se debe filtrar" not in res.text


def test_s7_descarga_con_archivo_faltante_en_disco_es_404(download_env, adjuntos_dir):
    (adjuntos_dir / "abc123.pdf").unlink()
    res = client.get("/api/proyectos/123/adjuntos/9", headers=_headers())
    assert res.status_code == 404
    assert res.json()["detail"] == MSG_NO_ADJUNTO


def test_s7_descarga_proyecto_inexistente_es_404(download_env, proyecto):
    proyecto["row"] = None
    res = client.get("/api/proyectos/123/adjuntos/9", headers=_headers())
    assert res.status_code == 404
    assert res.json()["detail"] == MSG_NO_PROYECTO


def test_s7_descarga_sin_token_es_401(download_env):
    assert client.get("/api/proyectos/123/adjuntos/9").status_code == 401


# ===========================================================================
# delete_proyecto en cascada
# ===========================================================================

def _responder_delete(fail_on=None, adjuntos=()):
    def responder(cur, sql, params):
        if fail_on and fail_on in sql:
            raise RuntimeError("fallo simulado")
        if sql.startswith("SELECT ID, Numero_Proyecto, Cliente"):
            return [{"ID": 123, "Numero_Proyecto": "000QA-1", "Cliente": "Cliente QA"}]
        if sql.startswith("SELECT Nombre_Almacenado"):
            return [{"Nombre_Almacenado": n} for n in adjuntos]
        if sql.startswith("DELETE FROM dbo.Proyectos"):
            cur.rowcount = 1
        return []
    return responder


def test_delete_proyecto_borra_adjuntos_y_bitacora_en_la_misma_transaccion(monkeypatch, adjuntos_dir):
    adjuntos_dir.mkdir(parents=True)
    (adjuntos_dir / "a1.pdf").write_bytes(b"x")
    (adjuntos_dir / "a2.png").write_bytes(b"y")
    (adjuntos_dir / "ajeno.pdf").write_bytes(b"z")
    conn = FakeConn(_responder_delete(adjuntos=["a1.pdf", "a2.png"]))
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    result = db_module.delete_proyecto(123)
    deletes = [(s, p) for s, p in conn.executed if s.startswith("DELETE")]
    assert [s for s, _ in deletes] == [
        "DELETE FROM dbo.Proyecto_Adjuntos WHERE Proyecto_ID = %s",
        "DELETE FROM dbo.Proyecto_Bitacora WHERE Proyecto_ID = %s",
        "DELETE FROM dbo.Proyecto_Asociaciones WHERE Proyecto_ID = %s",
        "DELETE FROM dbo.Proyectos WHERE ID = %s",
    ]
    assert all(p == (123,) for _, p in deletes)
    assert conn.events == ["commit"] and conn.commits == 1
    assert result == {"success": True, "id": 123, "numero_proyecto": "000QA-1",
                      "cliente": "Cliente QA", "deleted_count": 1}
    assert sorted(p.name for p in _archivos(adjuntos_dir)) == ["ajeno.pdf"]


def test_delete_proyecto_error_hace_rollback_y_conserva_los_archivos(monkeypatch, adjuntos_dir):
    adjuntos_dir.mkdir(parents=True)
    (adjuntos_dir / "a1.pdf").write_bytes(b"x")
    conn = FakeConn(_responder_delete(fail_on="DELETE FROM dbo.Proyectos WHERE", adjuntos=["a1.pdf"]))
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    result = db_module.delete_proyecto(123)
    assert conn.commits == 0 and conn.rollbacks == 1
    assert result["success"] is False and result["error"] == "db_error"
    assert [p.name for p in _archivos(adjuntos_dir)] == ["a1.pdf"]


def test_delete_proyecto_no_falla_si_no_puede_borrar_un_archivo(monkeypatch, adjuntos_dir):
    adjuntos_dir.mkdir(parents=True)
    (adjuntos_dir / "a1.pdf").write_bytes(b"x")
    conn = FakeConn(_responder_delete(adjuntos=["a1.pdf", "../fuera.pdf"]))
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)

    def falla(path):
        raise PermissionError("sin permiso")

    monkeypatch.setattr(db_module.os, "remove", falla)
    result = db_module.delete_proyecto(123)
    assert result["success"] is True and result["deleted_count"] == 1
    assert conn.commits == 1


def test_delete_proyecto_inexistente_mantiene_not_found(monkeypatch):
    conn = FakeConn(lambda cur, sql, params: [])
    monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
    result = db_module.delete_proyecto(123)
    assert result == {"success": False, "error": "not_found", "message": "Proyecto ID 123 no encontrado"}
    assert not any(s.startswith("DELETE") for s in conn.sqls())
    assert conn.commits == 0
