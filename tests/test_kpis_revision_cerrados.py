"""
S5: KPI cards for projects "En revisión" and "Cerrados" in the Proyectos module.

The test database is production: all data access here is simulated (fake connections).
"""

import pytest

import backend.db as db_module


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.last_sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.last_sql = " ".join(sql.split())
        self.conn.executed.append((self.last_sql, params))

    def fetchall(self):
        return []

    def fetchone(self):
        sql = self.last_sql
        if "COUNT(1) as total" in sql and "registrosRF_SD_SM" not in sql and "registrosSM_RFC" not in sql:
            if "p.Estado = 'En revision'" in sql:
                return {"total": 2}
            if "'Cerrado'" in sql:
                return {"total": 5}
            if "'En ejecucion'" in sql:
                return {"total": 7}
            return {"total": 20}
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


def test_s5_kpis_cuentan_proyectos_en_revision_y_cerrados(conn):
    kpis = db_module.get_dashboard_kpis()
    assert kpis["proyectos_en_revision"] == 2
    assert kpis["proyectos_cerrados"] == 5
    # Existing KPIs keep their values
    assert kpis["total_proyectos"] == 20
    assert kpis["proyectos_en_curso"] == 7
    assert kpis["efectividad"] == 25.0


def test_s5_kpi_en_revision_excluye_reuniones_y_respeta_filtro_lti(conn):
    db_module.get_dashboard_kpis(lt_filter="Juan Barrera")
    revision = [(sql, p) for sql, p in conn.executed if "p.Estado = 'En revision'" in sql]
    assert len(revision) == 1
    sql, params = revision[0]
    assert "p.Tipo_Servicio <> 'Reunión'" in sql
    assert "p.LT_Asignado = %s" in sql
    assert params == ("Juan Barrera",)


def test_s5_kpi_en_revision_filtro_sin_asignar(conn):
    db_module.get_dashboard_kpis(lt_filter="__UNASSIGNED__")
    sql, params = next((s, p) for s, p in conn.executed if "p.Estado = 'En revision'" in s)
    assert "p.LT_Asignado IS NULL" in sql
    assert params == ()


def test_s5_kpis_vacios_incluye_en_revision():
    vacios = db_module.kpis_vacios()
    assert vacios["proyectos_en_revision"] == 0
    assert vacios["proyectos_cerrados"] == 0
