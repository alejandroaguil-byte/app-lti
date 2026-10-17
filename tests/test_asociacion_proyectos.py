"""
Asociación de proyectos por N° de proyecto (odd/tasks/tours-busqueda-asociacion-kpis.md, T4: S4).

Una asociación es una arista entre un proyecto y un N° de proyecto normalizado (sin espacios ni prefijo '000');
el grupo es la componente conexa (simétrica y transitiva). Solo las pestañas Solots/Tickets/RFCs del detalle suman
los registros del grupo, con la columna Proyecto_Origen.

La base de pruebas es la de producción: todo acceso a datos está simulado (conexiones y cursores falsos).
"""

import ast
import datetime
import inspect
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.auth as auth_module
import backend.db as db_module
import backend.main as main_module
from backend.main import app
from tests.conftest import create_portal_jwt

client = TestClient(app)

MSG_OBLIGATORIO = "El N° de proyecto es obligatorio"
MSG_FORMATO = "El N° de proyecto solo puede contener letras, números y guiones (máx. 30 caracteres)"
MSG_SELF = "No puedes asociar un proyecto consigo mismo"
MSG_DUPLICADO = "El N° de proyecto ya está asociado a este grupo"
MSG_NO_ASOCIACION = "Asociación no encontrada"
MSG_NO_PROYECTO = "Proyecto no encontrado"

CREADO = datetime.datetime(2026, 10, 16, 9, 30, 0)

EDGES_SQL = "FROM dbo.Proyecto_Asociaciones a LEFT JOIN dbo.Proyectos p"
PROYECTOS_SQL = "FROM dbo.Proyectos WITH (NOLOCK) WHERE CASE WHEN"

# SQL exacto de hoy para el detalle sin asociaciones (mismo estilo que test_vinculacion_numero_proyecto)
DETALLE = [
    ("get_solots_by_proyecto", "b", "ID_OTP"),
    ("get_tickets_by_proyecto", "sd", "CC_INCIDENT_ID"),
    ("get_rfcs_by_proyecto", "rfc", "NUMBER"),
]


# ---------------------------------------------------------------------------
# Conexión falsa con un mini modelo de dbo.Proyecto_Asociaciones / dbo.Proyectos
# ---------------------------------------------------------------------------

class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        sql = " ".join(str(sql).split())
        self.conn.executed.append((sql, params))
        self._rows = list(self.conn.respond(sql, params))

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConn:
    """edges: filas de Proyecto_Asociaciones con Numero_Origen; proyectos: filas de dbo.Proyectos; detalle: filas del tab."""

    def __init__(self, edges=None, proyectos=None, detalle=None):
        self.edges = edges or []
        self.proyectos = proyectos or []
        self.detalle = detalle or []
        self.executed = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def respond(self, sql, params):
        if EDGES_SQL in sql:
            return self.edges
        if PROYECTOS_SQL in sql:
            wanted = set(params or ())
            return [p for p in self.proyectos if db_module.normalizar_numero_asociado(p["Numero_Proyecto"]) in wanted]
        if sql.startswith("INSERT INTO dbo.Proyecto_Asociaciones"):
            return [{"ID": Decimal(77), "Creado": CREADO}]
        if sql.startswith("SELECT ID, Proyecto_ID, Numero_Asociado FROM dbo.Proyecto_Asociaciones WHERE ID"):
            return [e for e in self.edges if e["ID"] == params[0]]
        if "FROM dbo.CT_BACKLOG_OPERACIONES2" in sql or "FROM dbo.registros" in sql:
            return self.detalle
        if sql.startswith("SELECT ID, Numero_Proyecto, Cliente FROM dbo.Proyectos WHERE ID"):
            return [{"ID": params[0], "Numero_Proyecto": "0001609373", "Cliente": "ACME"}]
        return []

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True

    def sqls(self):
        return [s for s, _ in self.executed]

    def writes(self, prefix):
        return [(s, p) for s, p in self.executed if s.startswith(prefix)]


def edge(id_, proyecto_id, numero_asociado, numero_origen, autor="alejandro.aguilar"):
    return {"ID": id_, "Proyecto_ID": Decimal(proyecto_id), "Numero_Asociado": numero_asociado,
            "Autor_Username": autor, "Creado": CREADO, "Numero_Origen": numero_origen}


def proyecto_row(id_, numero, cliente="ACME"):
    return {"ID": Decimal(id_), "Numero_Proyecto": numero, "Cliente": cliente}


@pytest.fixture
def make_conn(monkeypatch):
    def factory(**kwargs):
        conn = FakeConn(**kwargs)
        monkeypatch.setattr(db_module, "get_db_connection", lambda: conn)
        return conn
    return factory


# ---------------------------------------------------------------------------
# Usuario y proyecto
# ---------------------------------------------------------------------------

USERS = {
    "alejandro.aguilar": ("ADMIN", None),
    "juan.perez": ("LTI", "Juan Barrera"),
}


@pytest.fixture(autouse=True)
def app_user(monkeypatch):
    def fake_jit(username, nombre_completo=None, default_rol="PM", email=None):
        rol, lt = USERS.get(username, ("PM", None))
        return {"id": 900, "username": username, "nombre_completo": username.title(),
                "email": f"{username}@clarovtr.cl", "rol": rol, "lt_asignado": lt, "activo": 1}

    monkeypatch.setattr(auth_module, "get_or_create_jit_user", fake_jit)


def _h(username="alejandro.aguilar"):
    token = create_portal_jwt(username=username, admin_level=0, tool_access={"app-lti": "operador"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def proyecto(monkeypatch):
    state = {"row": {"ID": 123, "Numero_Proyecto": "0001609373", "LT_Asignado": "Juan Barrera", "Estado": "En ejecucion"}}
    monkeypatch.setattr(main_module, "get_proyecto_by_id", lambda pid: state["row"])
    return state


# ===========================================================================
# Normalización
# ===========================================================================

@pytest.mark.parametrize("bruto, esperado", [
    ("0001609373", "1609373"),
    (" 0001615172 ", "1615172"),
    ("1609373", "1609373"),
    ("ABC-12", "ABC-12"),
    ("abc-12", "ABC-12"),
    ("000", "000"),
    (None, ""),
    ("   ", ""),
])
def test_s4_normalizar_numero_asociado(bruto, esperado):
    assert db_module.normalizar_numero_asociado(bruto) == esperado


# ===========================================================================
# Tabla (idempotente, solo aditiva)
# ===========================================================================

def test_s4_init_crea_tabla_de_asociaciones_solo_si_no_existe(make_conn):
    conn = make_conn()
    db_module.init_bitacora_tables()
    texto = "\n".join(conn.sqls())
    assert "IF OBJECT_ID('dbo.Proyecto_Asociaciones', 'U') IS NULL" in texto
    for fragmento in (
        "CREATE TABLE dbo.Proyecto_Asociaciones",
        "ID INT IDENTITY(1,1) PRIMARY KEY",
        "Proyecto_ID NUMERIC(18,0) NOT NULL",
        "Numero_Asociado VARCHAR(50) NOT NULL",
        "Autor_Username VARCHAR(100) NULL",
        "Creado DATETIME NOT NULL DEFAULT GETDATE()",
        "CREATE UNIQUE INDEX UX_Proyecto_Asociaciones_Proyecto_Numero ON dbo.Proyecto_Asociaciones (Proyecto_ID, Numero_Asociado)",
    ):
        assert fragmento in texto, fragmento
    assert "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_Proyecto_Asociaciones_Proyecto_Numero'" in texto
    assert "DROP" not in texto.upper() and "DELETE" not in texto.upper() and "ALTER" not in texto.upper()
    assert conn.commits == 1 and conn.closed


# ===========================================================================
# POST /api/proyectos/{id}/asociaciones — validaciones (no se escribe nada)
# ===========================================================================

@pytest.mark.parametrize("body, status_esperado, mensaje", [
    ({}, 400, MSG_OBLIGATORIO),
    ({"numero": None}, 400, MSG_OBLIGATORIO),
    ({"numero": ""}, 400, MSG_OBLIGATORIO),
    ({"numero": "   "}, 400, MSG_OBLIGATORIO),
    ({"numero": "16 09"}, 400, MSG_FORMATO),
    ({"numero": "16_09"}, 400, MSG_FORMATO),
    ({"numero": "16;DROP"}, 400, MSG_FORMATO),
    ({"numero": "1" * 31}, 400, MSG_FORMATO),
    ({"numero": "1609373"}, 400, MSG_SELF),
    ({"numero": "0001609373"}, 400, MSG_SELF),
    ({"numero": " 0001609373 "}, 400, MSG_SELF),
])
def test_s4_post_validaciones_no_escriben(make_conn, proyecto, body, status_esperado, mensaje):
    conn = make_conn()
    res = client.post("/api/proyectos/123/asociaciones", json=body, headers=_h())
    assert res.status_code == status_esperado, res.text
    assert res.json() == {"detail": mensaje}
    assert conn.writes("INSERT") == [] and conn.commits == 0


def test_s4_post_acepta_30_caracteres(make_conn, proyecto):
    conn = make_conn()
    res = client.post("/api/proyectos/123/asociaciones", json={"numero": "A" * 30}, headers=_h())
    assert res.status_code == 201, res.text
    assert conn.writes("INSERT")[0][1] == (123, "A" * 30, "alejandro.aguilar")


@pytest.mark.parametrize("numero_en_grupo, edges", [
    # arista directa desde este proyecto
    ("1615172", [edge(1, 123, "1615172", "0001609373")]),
    # arista inversa: el otro proyecto apunta al N° de este
    ("1615172", [edge(1, 200, "1609373", "0001615172")]),
    # transitivo: 1609373 -> 1615172 -> 1700000
    ("1700000", [edge(1, 123, "1615172", "0001609373"), edge(2, 200, "1700000", "0001615172")]),
])
def test_s4_post_duplicado_en_el_grupo_responde_409(make_conn, proyecto, numero_en_grupo, edges):
    conn = make_conn(edges=edges)
    for bruto in (numero_en_grupo, "000" + numero_en_grupo):
        res = client.post("/api/proyectos/123/asociaciones", json={"numero": bruto}, headers=_h())
        assert res.status_code == 409, res.text
        assert res.json() == {"detail": MSG_DUPLICADO}
    assert conn.writes("INSERT") == [] and conn.commits == 0


def test_s4_post_duplicado_sin_distinguir_mayusculas_responde_409(make_conn, proyecto):
    # The database collation is case-insensitive (SQL_Latin1_General_CP1_CI_AS)
    conn = make_conn(edges=[edge(1, 123, "ABC-12", "0001609373")])
    res = client.post("/api/proyectos/123/asociaciones", json={"numero": "abc-12"}, headers=_h())
    assert res.status_code == 409, res.text
    assert res.json() == {"detail": MSG_DUPLICADO}
    assert conn.writes("INSERT") == [] and conn.commits == 0


def test_s4_post_concurrente_que_choca_con_el_indice_unico_responde_409(make_conn, proyecto):
    conn = make_conn()
    respond = conn.respond

    def respond_con_choque(sql, params):
        if sql.startswith("INSERT INTO dbo.Proyecto_Asociaciones"):
            raise db_module.pymssql.IntegrityError(2601, b"Cannot insert duplicate key row")
        return respond(sql, params)

    conn.respond = respond_con_choque
    res = client.post("/api/proyectos/123/asociaciones", json={"numero": "1615172"}, headers=_h())
    assert res.status_code == 409, res.text
    assert res.json() == {"detail": MSG_DUPLICADO}
    assert conn.commits == 0 and conn.rollbacks == 1 and conn.closed


def test_s4_post_crea_con_numero_normalizado_y_responde_201(make_conn, proyecto):
    conn = make_conn()
    res = client.post("/api/proyectos/123/asociaciones", json={"numero": " 0001615172 "}, headers=_h())
    assert res.status_code == 201, res.text
    assert res.json() == {"id": 77, "numero": "1615172", "autor_username": "alejandro.aguilar",
                          "creado": CREADO.isoformat()}
    insert, params = conn.writes("INSERT")[0]
    assert insert.startswith("INSERT INTO dbo.Proyecto_Asociaciones (Proyecto_ID, Numero_Asociado, Autor_Username)")
    assert params == (123, "1615172", "alejandro.aguilar")
    assert conn.commits == 1 and conn.closed


# ===========================================================================
# GET /api/proyectos/{id}/asociaciones — grupo simétrico y transitivo
# ===========================================================================

def _get_asociaciones(proyecto_id=123):
    res = client.get(f"/api/proyectos/{proyecto_id}/asociaciones", headers=_h())
    assert res.status_code == 200, res.text
    return res.json()


def test_s4_get_sin_asociaciones(make_conn, proyecto):
    make_conn()
    assert _get_asociaciones() == {"numero_propio": "1609373", "grupo": [], "asociaciones": []}


def test_s4_get_grupo_con_proyectos_existentes_y_externos(make_conn, proyecto):
    conn = make_conn(
        edges=[edge(1, 123, "1615172", "0001609373"), edge(2, 123, "1700000", "0001609373")],
        proyectos=[proyecto_row(456, "0001615172", "ACME Hijo")],
    )
    body = _get_asociaciones()
    assert body["numero_propio"] == "1609373"
    assert body["grupo"] == [
        {"numero": "1615172", "proyecto_id": 456, "cliente": "ACME Hijo"},
        {"numero": "1700000", "proyecto_id": None, "cliente": None},
    ]
    assert body["asociaciones"] == [
        {"id": 1, "numero": "1615172", "autor_username": "alejandro.aguilar", "creado": CREADO.isoformat()},
        {"id": 2, "numero": "1700000", "autor_username": "alejandro.aguilar", "creado": CREADO.isoformat()},
    ]
    assert all(isinstance(g["proyecto_id"], (int, type(None))) for g in body["grupo"])
    assert conn.writes("INSERT") == [] and conn.writes("DELETE") == []


def test_s4_grupo_simetrico_y_transitivo(make_conn, monkeypatch):
    # A (1609373) -> B (1615172) y A -> C (1700000): el grupo de B contiene a A y a C
    edges = [edge(1, 123, "1615172", "0001609373"), edge(2, 123, "1700000", "0001609373")]
    proyectos = [proyecto_row(123, "0001609373"), proyecto_row(456, "0001615172"), proyecto_row(789, "1700000")]
    make_conn(edges=edges, proyectos=proyectos)

    def grupo_de(pid, numero):
        monkeypatch.setattr(main_module, "get_proyecto_by_id",
                            lambda _pid: {"ID": pid, "Numero_Proyecto": numero, "LT_Asignado": None})
        return _get_asociaciones(pid)

    de_b = grupo_de(456, "0001615172")
    assert [g["numero"] for g in de_b["grupo"]] == ["1609373", "1700000"]
    assert de_b["asociaciones"] == [  # solo la arista que involucra a B; el otro lado es A
        {"id": 1, "numero": "1609373", "autor_username": "alejandro.aguilar", "creado": CREADO.isoformat()}
    ]
    de_c = grupo_de(789, "1700000")
    assert [g["numero"] for g in de_c["grupo"]] == ["1609373", "1615172"]
    assert [a["id"] for a in de_c["asociaciones"]] == [2]
    de_a = grupo_de(123, "0001609373")
    assert [g["numero"] for g in de_a["grupo"]] == ["1615172", "1700000"]
    assert [a["id"] for a in de_a["asociaciones"]] == [1, 2]


def test_s4_grupo_transitivo_en_cadena(make_conn, proyecto):
    # 1609373 -> 1615172 (arista del proyecto 123) y 1615172 -> 1700000 (arista del proyecto 456): sin arista directa
    make_conn(
        edges=[edge(1, 123, "1615172", "0001609373"), edge(2, 456, "1700000", "0001615172")],
        proyectos=[proyecto_row(456, "0001615172"), proyecto_row(789, "1700000")],
    )
    body = _get_asociaciones()
    assert [g["numero"] for g in body["grupo"]] == ["1615172", "1700000"]
    assert [a["id"] for a in body["asociaciones"]] == [1]  # la arista 2 no involucra a este proyecto


def test_s4_grupo_no_mezcla_componentes_distintas(make_conn, proyecto):
    make_conn(edges=[edge(1, 123, "1615172", "0001609373"), edge(2, 900, "5555555", "0004444444")])
    assert [g["numero"] for g in _get_asociaciones()["grupo"]] == ["1615172"]


# ===========================================================================
# DELETE /api/proyectos/{id}/asociaciones/{asociacion_id}
# ===========================================================================

def test_s4_delete_arista_propia_la_elimina(make_conn, proyecto):
    conn = make_conn(edges=[edge(5, 123, "1615172", "0001609373")])
    res = client.delete("/api/proyectos/123/asociaciones/5", headers=_h())
    assert res.status_code == 200, res.text
    assert res.json() == {"message": "Asociación eliminada", "id": 5}
    assert conn.writes("DELETE") == [("DELETE FROM dbo.Proyecto_Asociaciones WHERE ID = %s", (5,))]
    assert conn.commits == 1


def test_s4_delete_arista_que_llega_al_numero_del_proyecto(make_conn, proyecto):
    conn = make_conn(edges=[edge(5, 200, "1609373", "0001615172")])
    res = client.delete("/api/proyectos/123/asociaciones/5", headers=_h())
    assert res.status_code == 200, res.text
    assert len(conn.writes("DELETE")) == 1


@pytest.mark.parametrize("edges, asociacion_id", [
    ([edge(5, 200, "1700000", "0001615172")], 5),   # arista de otro par de proyectos
    ([], 99),                                       # no existe
])
def test_s4_delete_arista_ajena_o_inexistente_responde_404(make_conn, proyecto, edges, asociacion_id):
    conn = make_conn(edges=edges)
    res = client.delete(f"/api/proyectos/123/asociaciones/{asociacion_id}", headers=_h())
    assert res.status_code == 404, res.text
    assert res.json() == {"detail": MSG_NO_ASOCIACION}
    assert conn.writes("DELETE") == [] and conn.commits == 0


# ===========================================================================
# Alcance: proyecto fuera del alcance → 404 en los tres endpoints
# ===========================================================================

@pytest.mark.parametrize("metodo, ruta, kwargs", [
    ("get", "/api/proyectos/123/asociaciones", {}),
    ("post", "/api/proyectos/123/asociaciones", {"json": {"numero": "1615172"}}),
    ("post", "/api/proyectos/123/asociaciones", {"json": {"numero": ""}}),
    ("delete", "/api/proyectos/123/asociaciones/5", {}),
])
def test_s4_proyecto_fuera_de_alcance_responde_404_sin_tocar_datos(make_conn, proyecto, metodo, ruta, kwargs):
    proyecto["row"]["LT_Asignado"] = "Erwin Sandoval"  # juan.perez solo ve LT_Asignado = "Juan Barrera"
    conn = make_conn(edges=[edge(5, 123, "1615172", "0001609373")])
    res = getattr(client, metodo)(ruta, headers=_h("juan.perez"), **kwargs)
    assert res.status_code == 404, res.text
    assert res.json() == {"detail": MSG_NO_PROYECTO}
    assert conn.executed == []


def test_s4_proyecto_en_alcance_si_se_puede_asociar_para_usuario_restringido(make_conn, proyecto):
    conn = make_conn()
    res = client.post("/api/proyectos/123/asociaciones", json={"numero": "1615172"}, headers=_h("juan.perez"))
    assert res.status_code == 201, res.text
    assert conn.writes("INSERT")[0][1] == (123, "1615172", "juan.perez")


@pytest.mark.parametrize("metodo, ruta, kwargs", [
    ("get", "/api/proyectos/123/asociaciones", {}),
    ("post", "/api/proyectos/123/asociaciones", {"json": {"numero": "1615172"}}),
    ("delete", "/api/proyectos/123/asociaciones/5", {}),
])
def test_s4_endpoints_requieren_autenticacion(make_conn, proyecto, metodo, ruta, kwargs):
    conn = make_conn()
    res = getattr(client, metodo)(ruta, **kwargs)
    assert res.status_code in (401, 403)
    assert conn.executed == []


# ===========================================================================
# Pestañas Solots / Tickets / RFCs del detalle
# ===========================================================================

@pytest.mark.parametrize("fn, alias, id_col", DETALLE)
def test_s4_detalle_suma_numeros_e_ids_del_grupo_y_etiqueta_origen(make_conn, fn, alias, id_col):
    detalle = [
        {id_col: "propio-id", "_Numero_Limpio": None, "_ID_Proyecto": Decimal(10)},
        {id_col: "propio-num", "_Numero_Limpio": "1609373", "_ID_Proyecto": None},
        {id_col: "hijo-num", "_Numero_Limpio": "1615172", "_ID_Proyecto": None},
        {id_col: "hijo-id", "_Numero_Limpio": None, "_ID_Proyecto": Decimal(20)},
        {id_col: "externo-num", "_Numero_Limpio": "1700000", "_ID_Proyecto": None},
    ]
    conn = make_conn(
        edges=[edge(1, 10, "1615172", "0001609373"), edge(2, 10, "1700000", "0001609373")],
        proyectos=[proyecto_row(20, "0001615172")],
        detalle=detalle,
    )
    rows = getattr(db_module, fn)(10, "0001609373", con_asociados=True)
    sql, params = conn.executed[-1]
    assert (f"WHERE {alias}.ID_Proyecto = %s OR {alias}.Numero_Proyecto_Limpio IN (%s, %s)"
            f" OR {alias}.ID_Proyecto IN (%s) OR {alias}.Numero_Proyecto_Limpio IN (%s, %s)") in sql
    assert f"{alias}.Numero_Proyecto_Limpio AS _Numero_Limpio, {alias}.ID_Proyecto AS _ID_Proyecto" in sql
    assert params == (10, "0001609373", "1609373", 20, "1615172", "1700000")
    assert {r[id_col]: r["Proyecto_Origen"] for r in rows} == {
        "propio-id": "1609373", "propio-num": "1609373", "hijo-num": "1615172",
        "hijo-id": "1615172", "externo-num": "1700000",
    }
    assert all("_Numero_Limpio" not in r and "_ID_Proyecto" not in r for r in rows)


@pytest.mark.parametrize("fn, alias, id_col", DETALLE)
def test_s4_detalle_incluye_ids_de_proyectos_del_grupo_sin_numero(make_conn, fn, alias, id_col):
    # Un proyecto sin N° (nodo '#<ID>') también participa por su ID_Proyecto
    conn = make_conn(
        edges=[edge(1, 10, "1615172", "0001609373"), edge(2, 30, "1609373", None)],
        proyectos=[proyecto_row(20, "0001615172")],
    )
    getattr(db_module, fn)(10, "0001609373", con_asociados=True)
    sql, params = conn.executed[-1]
    assert f"OR {alias}.ID_Proyecto IN (%s, %s)" in sql
    assert params[3:5] == (20, 30)


@pytest.mark.parametrize("fn, alias, id_col", DETALLE)
def test_s4_detalle_sin_asociaciones_es_exactamente_el_de_hoy(make_conn, fn, alias, id_col):
    conn = make_conn(edges=[edge(1, 200, "1700000", "0001615172")], detalle=[{id_col: "x"}])
    rows = getattr(db_module, fn)(2570, "0001609373", con_asociados=True)
    assert rows == [{id_col: "x"}]  # sin Proyecto_Origen
    sql, params = conn.executed[-1]
    assert f"WHERE {alias}.ID_Proyecto = %s OR {alias}.Numero_Proyecto_Limpio IN (%s, %s) ORDER BY" in sql
    assert "_Numero_Limpio" not in sql and "ID_Proyecto IN" not in sql
    assert params == (2570, "0001609373", "1609373")

    # Idéntico a la consulta sin el flag
    base = make_conn(detalle=[{id_col: "x"}])
    getattr(db_module, fn)(2570, "0001609373")
    assert base.executed == [(sql, params)]


@pytest.mark.parametrize("fn, alias, id_col", DETALLE)
def test_s4_detalle_sin_flag_no_consulta_asociaciones(make_conn, fn, alias, id_col):
    conn = make_conn(edges=[edge(1, 10, "1615172", "0001609373")])
    getattr(db_module, fn)(10, "0001609373")
    assert len(conn.executed) == 1 and "Proyecto_Asociaciones" not in conn.executed[0][0]
    assert conn.executed[0][1] == (10, "0001609373", "1609373")


@pytest.mark.parametrize("fn", [d[0] for d in DETALLE])
def test_s4_detalle_si_falla_el_grupo_responde_como_hoy(make_conn, monkeypatch, fn):
    def falla(cursor, proyecto_id, numero):
        raise RuntimeError("tabla inexistente")

    conn = make_conn()
    monkeypatch.setattr(db_module, "_cargar_grupo_asociado", falla)
    getattr(db_module, fn)(10, "0001609373", con_asociados=True)
    assert conn.executed[-1][1] == (10, "0001609373", "1609373")


@pytest.mark.parametrize("ruta, funcion", [
    ("/api/proyectos/123/solots", "get_solots_by_proyecto"),
    ("/api/proyectos/123/tickets", "get_tickets_by_proyecto"),
    ("/api/proyectos/123/rfcs", "get_rfcs_by_proyecto"),
])
def test_s4_endpoints_del_detalle_piden_los_asociados(monkeypatch, proyecto, ruta, funcion):
    llamadas = []
    monkeypatch.setattr(main_module, funcion, lambda *a, **k: llamadas.append((a, k)) or [])
    res = client.get(ruta, headers=_h())
    assert res.status_code == 200, res.text
    assert llamadas == [((123, "0001609373"), {"con_asociados": True})]


def test_s4_diagnostico_ficha_y_timeline_no_agregan_asociados():
    """Solo las pestañas del detalle agregan el grupo: ningún otro llamador de db.py pasa con_asociados."""
    arbol = ast.parse(Path(inspect.getsourcefile(db_module)).read_text(encoding="utf-8"))
    nombres = {d[0] for d in DETALLE}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and getattr(nodo.func, "id", None) in nombres:
            assert all(k.arg != "con_asociados" for k in nodo.keywords), ast.dump(nodo)
    for fn in nombres:
        assert inspect.signature(getattr(db_module, fn)).parameters["con_asociados"].default is False


# ===========================================================================
# Eliminación del proyecto
# ===========================================================================

def test_s4_delete_proyecto_borra_sus_asociaciones(make_conn):
    conn = make_conn()
    res = db_module.delete_proyecto(123)
    assert res["success"] is True
    borrados = [s for s in conn.sqls() if s.startswith("DELETE")]
    assert borrados == [
        "DELETE FROM dbo.Proyecto_Adjuntos WHERE Proyecto_ID = %s",
        "DELETE FROM dbo.Proyecto_Bitacora WHERE Proyecto_ID = %s",
        "DELETE FROM dbo.Proyecto_Asociaciones WHERE Proyecto_ID = %s",
        "DELETE FROM dbo.Proyectos WHERE ID = %s",
    ]
    assoc = [p for s, p in conn.executed if s.startswith("DELETE FROM dbo.Proyecto_Asociaciones")]
    assert assoc == [(123,)]
    assert conn.commits == 1
