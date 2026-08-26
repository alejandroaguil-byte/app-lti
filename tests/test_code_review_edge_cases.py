import pytest
from backend.db import (
    clean_solicitante,
    format_numero_proyecto,
    get_lideres_list,
    UNMATCHED_SOLICITANTE,
    get_dashboard_kpis,
    get_proyectos,
    search_direct_tables
)
from backend.main import app
from fastapi.testclient import TestClient
from backend.auth import create_access_token

client = TestClient(app)

def test_clean_solicitante_edge_cases():
    """Valida la sanitización robusta del solicitante ante valores nulos, vacíos y prefijos Corp."""
    assert clean_solicitante(None) == UNMATCHED_SOLICITANTE
    assert clean_solicitante("") == UNMATCHED_SOLICITANTE
    assert clean_solicitante("   ") == UNMATCHED_SOLICITANTE
    assert clean_solicitante("N/A") == UNMATCHED_SOLICITANTE
    assert clean_solicitante("none") == UNMATCHED_SOLICITANTE
    assert clean_solicitante("NULL") == UNMATCHED_SOLICITANTE
    assert clean_solicitante("-") == UNMATCHED_SOLICITANTE
    assert clean_solicitante(UNMATCHED_SOLICITANTE) == UNMATCHED_SOLICITANTE
    
    # Prefijos Corp
    assert clean_solicitante("Corp1- JUAN PEREZ") == "JUAN PEREZ"
    assert clean_solicitante("corp2 - Maria Gomez") == "MARIA GOMEZ"
    assert clean_solicitante("Corp: Carlos Silva") == "CARLOS SILVA"
    assert clean_solicitante("Corp - ") == UNMATCHED_SOLICITANTE
    assert clean_solicitante("ERWIN SANDOVAL") == "ERWIN SANDOVAL"

def test_format_numero_proyecto_edge_cases():
    """Valida el formateo con prefijo '000' y preservación de valores centinela."""
    assert format_numero_proyecto(None) is None
    assert format_numero_proyecto("") == ""
    assert format_numero_proyecto("N/A") == "N/A"
    assert format_numero_proyecto("NULL") == "NULL"
    assert format_numero_proyecto("none") == "none"
    assert format_numero_proyecto("-") == "-"
    
    assert format_numero_proyecto("1614653") == "0001614653"
    assert format_numero_proyecto("0001614653") == "0001614653"
    assert format_numero_proyecto(1614653) == "0001614653"

def test_get_lideres_list_strict_ascending_order():
    """Valida que los 5 líderes activos estén estrictamente en orden alfabético ascendente."""
    lideres = get_lideres_list()
    assert len(lideres) == 5
    assert lideres == sorted(lideres)
    assert lideres == [
        "Alejandro Aguilar",
        "Erwin Sandoval",
        "Juan Barrera",
        "Samuel Paredes",
        "Solange Ortiz"
    ]

def test_kpis_and_proyectos_unassigned_filter_variants():
    """Valida que los endpoints de KPIs y Proyectos manejen variantes de 'sin asignar' de forma case-insensitive."""
    token = create_access_token({"sub": "admin", "rol": "ADMIN", "nombre_completo": "Admin", "lt_asignado": None})
    headers = {"Authorization": f"Bearer {token}"}

    for filter_val in ["__UNASSIGNED__", "Sin asignar", "sin asignar", "SIN ASIGNAR"]:
        res_kpis = client.get(f"/api/kpis?lt={filter_val}", headers=headers)
        assert res_kpis.status_code == 200
        data_kpis = res_kpis.json()
        assert "total_proyectos" in data_kpis

        res_proy = client.get(f"/api/proyectos?lt={filter_val}", headers=headers)
        assert res_proy.status_code == 200
        data_proy = res_proy.json()
        assert isinstance(data_proy, list)
        for p in data_proy:
            lt = p.get("LT_Asignado")
            assert lt is None or lt.strip() == "" or lt.strip().lower() == "sin asignar"

def test_direct_search_sql_injection_resilience():
    """Valida que entradas potencialmente maliciosas no causen inyección SQL."""
    token = create_access_token({"sub": "admin", "rol": "ADMIN", "nombre_completo": "Admin", "lt_asignado": None})
    headers = {"Authorization": f"Bearer {token}"}

    payloads = [
        "' OR '1'='1",
        "'; DROP TABLE dbo.Proyectos; --",
        "\" OR 1=1 --",
        "105; WAITFOR DELAY '0:0:1'--"
    ]
    for p in payloads:
        res = client.get(f"/api/search/direct?q={p}&table=proyectos", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "counts" in data
        assert "proyectos" in data
