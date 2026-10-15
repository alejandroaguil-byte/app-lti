"""
PRUEBAS DE SEGURIDAD: LIMPIEZA DE DATOS DE PRUEBA (tests/conftest.py)
Especificación: odd/tasks/test-safety-dev-email.md (S3)

La base de datos de pruebas es la misma que la de producción. Cada prueba inserta filas
dentro de una transacción y SIEMPRE hace rollback: nada queda persistido.

- CP-CLEAN-01: La limpieza borra filas de prueba creadas en la sesión y conserva filas reales
               (incluidas las que contienen 'inmutabilidad', 'MODIFICADO' o 'QA' en Cliente/Detalle).
- CP-CLEAN-02: Una fila con prefijo de prueba pero ID anterior al inicio de la sesión no se borra.
- CP-CLEAN-03: Sin ID de inicio de sesión la limpieza no borra nada.
- CP-CLEAN-04: El proyecto real ID 2496 (1612444, INNOVIT SPA) nunca coincide con la limpieza.
"""

import pytest
from backend.db import get_db_connection
from tests.conftest import delete_test_projects, TEST_PROJECT_PREFIXES


@pytest.fixture
def tx_cursor():
    """Cursor dentro de una transacción que siempre se revierte."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        yield cursor
    finally:
        conn.rollback()
        conn.close()


def _max_id(cursor) -> int:
    cursor.execute("SELECT ISNULL(MAX(ID), 0) AS max_id FROM dbo.Proyectos WITH (UPDLOCK, HOLDLOCK)")
    return int(cursor.fetchone()["max_id"])


def _insert(cursor, row_id: int, numero: str, cliente: str, detalle: str):
    cursor.execute(
        "INSERT INTO dbo.Proyectos (ID, Numero_Proyecto, Cliente, Detalle, Estado) VALUES (%s, %s, %s, %s, %s)",
        (row_id, numero, cliente, detalle, "Generado"),
    )


def _exists(cursor, row_id: int) -> bool:
    cursor.execute("SELECT COUNT(*) AS n FROM dbo.Proyectos WHERE ID = %s", (row_id,))
    return cursor.fetchone()["n"] == 1


def test_clean_01_deletes_session_test_rows_and_keeps_real_rows(tx_cursor):
    session_start = _max_id(tx_cursor)
    real_rows = [
        (session_start + 1, "0001999001", "INNOVIT SPA", "Respaldo inmutabilidad Semanal"),
        (session_start + 2, "0001999002", "CLIENTE MODIFICADO LTDA", "Migración QA de enlaces"),
        (session_start + 3, "Sin ID autorizado Roberto Zambrano", "PRUEBA QA REAL", "Prueba E2E Automatizada"),
    ]
    test_rows = [
        (session_start + 10 + i, f"{prefix}GUARD-{i}", "CLIENTE PRUEBA QA", "Detalle de prueba")
        for i, prefix in enumerate(TEST_PROJECT_PREFIXES)
    ]
    for row in real_rows + test_rows:
        _insert(tx_cursor, *row)

    deleted = delete_test_projects(tx_cursor, session_start)

    assert deleted == len(test_rows)
    for row in real_rows:
        assert _exists(tx_cursor, row[0]), f"Fila real borrada: {row}"
    for row in test_rows:
        assert not _exists(tx_cursor, row[0]), f"Fila de prueba no borrada: {row}"


def test_clean_02_keeps_test_prefixed_rows_older_than_session(tx_cursor):
    current_max = _max_id(tx_cursor)
    _insert(tx_cursor, current_max + 1, "000QA-TEST-OLD-GUARD", "CLIENTE PRUEBA QA", "Fila previa a la sesión")

    deleted = delete_test_projects(tx_cursor, current_max + 1)

    assert deleted == 0
    assert _exists(tx_cursor, current_max + 1)


def test_clean_03_without_session_start_deletes_nothing(tx_cursor):
    current_max = _max_id(tx_cursor)
    _insert(tx_cursor, current_max + 1, "000QA-TEST-NOSTART-GUARD", "CLIENTE PRUEBA QA", "Sin inicio de sesión")

    deleted = delete_test_projects(tx_cursor, None)

    assert deleted == 0
    assert _exists(tx_cursor, current_max + 1)


def test_clean_04_real_project_2496_never_matches(tx_cursor):
    tx_cursor.execute("SELECT ID FROM dbo.Proyectos WHERE ID = 2496")
    if not tx_cursor.fetchone():
        pytest.skip("El proyecto real 2496 ya no existe en la base")

    # Aun con el límite de ID más permisivo, el proyecto real no debe coincidir
    delete_test_projects(tx_cursor, 0)

    assert _exists(tx_cursor, 2496)
