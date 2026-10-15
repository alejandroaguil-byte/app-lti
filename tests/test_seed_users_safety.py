"""
PRUEBAS DE SEGURIDAD: SEED DE USUARIOS CANÓNICOS (backend/seed_users.py)
Especificación: odd/tasks/test-safety-dev-email.md (S8)

El seed corre en cada arranque de la app (desarrollo y producción) sobre la base productiva.
Usa una conexión simulada: nunca toca la BD.

- CP-SEED-01: Una cuenta canónica existente no se modifica (rol, LT, nombre ni activo).
- CP-SEED-02: Una cuenta canónica existente sin email solo recibe el email oficial.
- CP-SEED-03: Una cuenta canónica inexistente se crea con sus valores canónicos.
"""

from unittest.mock import MagicMock, patch

from backend import seed_users
from backend.seed_users import USERS_CANONICAL_SEED

TARGET = "juan.barrera"


def _run_seed(existing_rows: dict):
    """Ejecuta el seed con una BD simulada; existing_rows: username -> fila existente."""
    executed = []
    cursor = MagicMock()
    state = {"last_select": None}

    def execute(sql, params=None):
        executed.append((" ".join(sql.split()), params))
        if sql.strip().upper().startswith("SELECT"):
            state["last_select"] = params[0]

    cursor.execute.side_effect = execute
    cursor.fetchone.side_effect = lambda: existing_rows.get(state["last_select"])
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor

    with patch.object(seed_users, "init_auth_tables"), patch.object(seed_users, "get_db_connection", return_value=conn):
        seed_users.seed_default_users()
    return [(sql, params) for sql, params in executed if not sql.upper().startswith("SELECT")]


def _all_existing(email="x@clarovtr.cl"):
    return {
        u[2]: {"id": i, "username": u[2], "rol": "PM", "lt_asignado": "Otro", "email": email}
        for i, u in enumerate(USERS_CANONICAL_SEED)
    }


def test_seed_01_existing_accounts_are_not_modified():
    writes = _run_seed(_all_existing())

    assert writes == []


def test_seed_02_existing_account_without_email_only_gets_email():
    existing = _all_existing()
    existing[TARGET]["email"] = None

    writes = _run_seed(existing)

    assert len(writes) == 1
    sql, params = writes[0]
    assert sql.upper().startswith("UPDATE DBO.APP_USUARIOS SET EMAIL = %S")
    assert "EMAIL IS NULL" in sql.upper()
    for column in ("ROL", "LT_ASIGNADO", "NOMBRE_COMPLETO", "ACTIVO"):
        assert f"{column} =" not in sql.upper()
    assert params == ("juan.barrera@clarovtr.cl", TARGET)


def test_seed_03_missing_account_is_created():
    existing = _all_existing()
    del existing[TARGET]

    writes = _run_seed(existing)

    assert len(writes) == 1
    sql, params = writes[0]
    assert sql.upper().startswith("INSERT INTO DBO.APP_USUARIOS")
    assert params == (TARGET, "Juan Barrera", "Juan Barrera", "LTI", "juan.barrera@clarovtr.cl")
