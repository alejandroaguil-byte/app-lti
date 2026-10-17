"""
Linking projects to Solots / tickets / RFCs by project number.

dbo.Proyectos.Numero_Proyecto may carry the SGA '000' prefix ('0001609373') while
Numero_Proyecto_Limpio in the backlog, ticket and RFC tables never does ('1609373').
ID_Proyecto is no longer filled by any load process, so every lookup must match by
ID_Proyecto OR the project number with and without the prefix.

The test database is production: all data access here is simulated (fake connections).
"""

import pytest

import backend.db as db_module


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((" ".join(sql.split()), params))

    def fetchall(self):
        return []

    def fetchone(self):
        return {"total": 0}


class FakeConn:
    def __init__(self):
        self.executed = []

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        pass


@pytest.fixture
def conn(monkeypatch):
    fake = FakeConn()
    monkeypatch.setattr(db_module, "get_db_connection", lambda: fake)
    return fake


@pytest.mark.parametrize("numero, esperado", [
    ("0001609373", ("0001609373", "1609373")),
    (" 0001615172 ", ("0001615172", "1615172")),
    ("1609373", ("1609373", "1609373")),
])
def test_numero_proyecto_limpio_keys(numero, esperado):
    assert db_module._numero_proyecto_limpio_keys(numero) == esperado


@pytest.mark.parametrize("fn, alias", [
    ("get_solots_by_proyecto", "b"),
    ("get_tickets_by_proyecto", "sd"),
    ("get_rfcs_by_proyecto", "rfc"),
])
def test_detalle_vincula_por_numero_con_y_sin_prefijo(conn, fn, alias):
    getattr(db_module, fn)(2570, "0001609373")
    sql, params = conn.executed[0]
    assert f"WHERE {alias}.ID_Proyecto = %s OR {alias}.Numero_Proyecto_Limpio IN (%s, %s)" in sql
    assert params == (2570, "0001609373", "1609373")


@pytest.mark.parametrize("fn", ["get_solots_by_proyecto", "get_tickets_by_proyecto", "get_rfcs_by_proyecto"])
def test_detalle_sin_numero_vincula_solo_por_id(conn, fn):
    getattr(db_module, fn)(2570, None)
    sql, params = conn.executed[0]
    assert "Numero_Proyecto_Limpio" not in sql
    assert params == (2570,)


def test_sql_numero_limpio_compara_con_y_sin_prefijo():
    assert db_module._SQL_P_NUMERO_LIMPIO_IN == (
        "IN (LTRIM(RTRIM(p.Numero_Proyecto)), "
        "CASE WHEN LTRIM(RTRIM(p.Numero_Proyecto)) LIKE '000%' "
        "THEN SUBSTRING(LTRIM(RTRIM(p.Numero_Proyecto)), 4, 50) "
        "ELSE LTRIM(RTRIM(p.Numero_Proyecto)) END)"
    )


def test_listado_cuenta_vinculos_por_id_y_por_numero(conn):
    db_module.get_proyectos()
    sql, _ = conn.executed[0]
    assert "ProyectoNumeros AS (" in sql
    for tabla, alias in (("CT_BACKLOG_OPERACIONES2", "b"), ("registrosRF_SD_SM", "sd"), ("registrosSM_RFC", "rfc")):
        assert f"INNER JOIN dbo.{tabla} {alias} WITH (NOLOCK) ON {alias}.Numero_Proyecto_Limpio = pn.numero" in sql
    assert "FROM SolotVinculos GROUP BY ID_Proyecto" in sql
    assert "FROM TicketVinculos GROUP BY ID_Proyecto" in sql
    assert "FROM RFCVinculos GROUP BY ID_Proyecto" in sql


def test_listado_filtro_estado_sga_vincula_por_numero(conn):
    db_module.get_proyectos(estado_sga="En asignacion")
    sql, params = conn.executed[0]
    assert "b.Numero_Proyecto_Limpio " + db_module._SQL_P_NUMERO_LIMPIO_IN + ") AND b.ESTADO_OTP = %s" in sql
    assert params == ("En asignacion",)


def test_detalle_proyecto_cuenta_por_numero(conn):
    db_module.get_proyecto_by_id(2570)
    sql, params = conn.executed[0]
    assert "b.Numero_Proyecto_Limpio = p.Numero_Proyecto" not in sql
    assert sql.count("Numero_Proyecto_Limpio " + db_module._SQL_P_NUMERO_LIMPIO_IN) == 10
    assert params == (2570,)


def test_kpis_dashboard_vinculan_por_numero(conn):
    db_module.get_dashboard_kpis(lt_filter="Juan Barrera")
    sqls = [s for s, _ in conn.executed]
    for alias in ("sd", "rfc"):
        total = [s for s in sqls if s.startswith("SELECT COUNT(1) as total FROM dbo.registros") and f" {alias} " in s]
        assert len(total) == 1
        assert f"{alias}.Numero_Proyecto_Limpio " + db_module._SQL_P_NUMERO_LIMPIO_IN in total[0]
        assert total[0].endswith("AND p.LT_Asignado = %s)")
    salud = [s for s in sqls if "AS saludables" in s]
    assert len(salud) == 1 and "ProyectoNumeros AS (" in salud[0]


def test_alertas_sla_vinculan_por_numero(conn):
    db_module.get_alertas_tempranas_sla()
    sqls = [s for s, _ in conn.executed if "OUTER APPLY" in s]
    assert len(sqls) == 2
    for sql, alias in zip(sqls, ("sd", "b")):
        assert f"{alias}.Numero_Proyecto_Limpio " + db_module._SQL_P_NUMERO_LIMPIO_IN in sql
