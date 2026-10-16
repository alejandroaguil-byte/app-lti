import pytest
from backend.db import calcular_salud_proyecto
from backend.main import app
from fastapi.testclient import TestClient
from tests.conftest import create_access_token

client = TestClient(app)

def test_salud_sin_datos_empty_row():
    res = calcular_salud_proyecto({})
    assert res["score"] == "NEUTRAL"
    assert res["color"] == "gray"
    assert res["label"] == "Sin Datos"
    assert "Proyecto sin Solots ni tickets vinculados" in res["motivos"][0]

def test_salud_sin_datos_zero_totals():
    row = {
        "total_solots": 0,
        "total_tickets": 0,
        "solots_vencidas": 0,
        "solots_por_vencer": 0,
        "tickets_criticos": 0,
        "tickets_atencion": 0
    }
    res = calcular_salud_proyecto(row)
    assert res["score"] == "NEUTRAL"
    assert res["color"] == "gray"
    assert res["label"] == "Sin Datos"

def test_salud_critica_por_solot_vencida():
    row = {
        "total_solots": 2,
        "total_tickets": 0,
        "solots_vencidas": 1,
        "solots_por_vencer": 0,
        "tickets_criticos": 0,
        "tickets_atencion": 0
    }
    res = calcular_salud_proyecto(row)
    assert res["score"] == "CRITICAL"
    assert res["color"] == "red"
    assert res["label"] == "Crítico"
    assert any("vencida" in m for m in res["motivos"])

def test_salud_critica_por_ticket_estancado():
    row = {
        "total_solots": 0,
        "total_tickets": 1,
        "solots_vencidas": 0,
        "solots_por_vencer": 0,
        "tickets_criticos": 1,
        "tickets_atencion": 0
    }
    res = calcular_salud_proyecto(row)
    assert res["score"] == "CRITICAL"
    assert res["color"] == "red"
    assert res["label"] == "Crítico"
    assert any("> 14 días" in m for m in res["motivos"])

def test_salud_riesgo_por_solot_proxima():
    row = {
        "total_solots": 1,
        "total_tickets": 0,
        "solots_vencidas": 0,
        "solots_por_vencer": 1,
        "tickets_criticos": 0,
        "tickets_atencion": 0
    }
    res = calcular_salud_proyecto(row)
    assert res["score"] == "WARNING"
    assert res["color"] == "yellow"
    assert res["label"] == "En Riesgo"
    assert any("por vencer (< 5 días)" in m for m in res["motivos"])

def test_salud_riesgo_por_ticket_atencion():
    row = {
        "total_solots": 0,
        "total_tickets": 1,
        "solots_vencidas": 0,
        "solots_por_vencer": 0,
        "tickets_criticos": 0,
        "tickets_atencion": 1
    }
    res = calcular_salud_proyecto(row)
    assert res["score"] == "WARNING"
    assert res["color"] == "yellow"
    assert res["label"] == "En Riesgo"
    assert any("> 7 días" in m for m in res["motivos"])

def test_salud_saludable():
    row = {
        "total_solots": 3,
        "total_tickets": 1,
        "solots_vencidas": 0,
        "solots_por_vencer": 0,
        "tickets_criticos": 0,
        "tickets_atencion": 0
    }
    res = calcular_salud_proyecto(row)
    assert res["score"] == "HEALTHY"
    assert res["color"] == "green"
    assert res["label"] == "Saludable"
    assert any("regular" in m for m in res["motivos"])

def test_precedencia_critico_sobre_riesgo():
    row = {
        "total_solots": 5,
        "total_tickets": 2,
        "solots_vencidas": 1,
        "solots_por_vencer": 2,
        "tickets_criticos": 0,
        "tickets_atencion": 1
    }
    res = calcular_salud_proyecto(row)
    assert res["score"] == "CRITICAL"
    assert res["color"] == "red"

def test_api_kpis_contains_health_summary():
    token = create_access_token({"username": "alejandro.aguilar", "rol": "ADMIN"})
    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/api/kpis", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "salud" in data
    salud = data["salud"]
    assert "saludables" in salud
    assert "en_riesgo" in salud
    assert "criticos" in salud
    assert "sin_datos" in salud
    assert isinstance(salud["saludables"], int)
    assert isinstance(salud["en_riesgo"], int)
    assert isinstance(salud["criticos"], int)
    assert isinstance(salud["sin_datos"], int)
    # Validar consistencia aritmética
    total_salud = salud["saludables"] + salud["en_riesgo"] + salud["criticos"] + salud["sin_datos"]
    assert total_salud == data["total_proyectos"]

def test_api_proyectos_contains_health_score():
    token = create_access_token({"username": "alejandro.aguilar", "rol": "ADMIN"})
    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/api/proyectos", headers=headers)
    assert res.status_code == 200
    proyectos = res.json()
    assert isinstance(proyectos, list)
    assert len(proyectos) > 0
    valid_scores = {"HEALTHY", "WARNING", "CRITICAL", "NEUTRAL"}
    for p in proyectos[:20]:
        assert "salud" in p
        salud = p["salud"]
        assert salud["score"] in valid_scores
        assert salud["color"] in {"green", "yellow", "red", "gray"}
        assert isinstance(salud["motivos"], list)
        assert len(salud["motivos"]) > 0

def test_api_proyecto_by_id_contains_health_score():
    token = create_access_token({"username": "alejandro.aguilar", "rol": "ADMIN"})
    headers = {"Authorization": f"Bearer {token}"}
    # Obtener el primer proyecto
    res = client.get("/api/proyectos", headers=headers)
    assert res.status_code == 200
    proyectos = res.json()
    assert len(proyectos) > 0
    first_id = proyectos[0]["ID"]

    res_detail = client.get(f"/api/proyectos/{first_id}", headers=headers)
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert "salud" in detail
    assert detail["salud"]["score"] in {"HEALTHY", "WARNING", "CRITICAL", "NEUTRAL"}
    assert isinstance(detail["salud"]["motivos"], list)
