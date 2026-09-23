"""
PRUEBAS UNITARIAS: TIMELINE / LÍNEA DE TIEMPO VISUAL DEL PROYECTO & REGLAS DE NEGOCIO (BACKEND)
Especificación: SPECS_TIMELINE_VISUAL_PROYECTO.md
Documento: SPECS-LTI-MOD-014
"""

import pytest
import datetime
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.main import app
from backend.db import (
    get_timeline_proyecto,
    _parse_timeline_dt
)
from tests.conftest import create_access_token

client = TestClient(app)

@pytest.fixture
def auth_headers():
    token = create_access_token({"username": "alejandro.aguilar", "rol": "ADMIN"})
    return {"Cookie": f"access_token={token}"}

@pytest.fixture
def lti_headers():
    token = create_access_token({"username": "alejandro.aguilar", "rol": "LTI"})
    return {"Cookie": f"access_token={token}"}

@pytest.fixture
def pm_headers():
    token = create_access_token({"username": "pm.test", "rol": "PM"})
    return {"Cookie": f"access_token={token}"}


# ==============================================================================
# UT-TL-01: test_get_timeline_proyecto_estructura
# ==============================================================================
@patch("backend.db.get_proyecto_by_id")
@patch("backend.db.get_solots_by_proyecto")
@patch("backend.db.get_tickets_by_proyecto")
@patch("backend.db.get_rfcs_by_proyecto")
def test_get_timeline_proyecto_estructura(mock_rfcs, mock_tickets, mock_solots, mock_proy):
    mock_proy.return_value = {
        "ID": 12,
        "Numero_Proyecto": "0000108920",
        "Cliente": "BANCO DE CHILE",
        "LT_Asignado": "ALEJANDRO JAVIER AGUILAR MORALES",
        "Solicitante": "CARLOS PEREZ GOMEZ",
        "Estado": "Atendido",
        "Tipo_Servicio": "Cloud & Conectividad",
        "Creado": "2026-06-30T10:00:00"
    }
    mock_solots.return_value = [
        {
            "ID_OTP": 104880,
            "DESCR_OTP": "Instalación Enlace",
            "ESTADO_OTP": "4- En curso",
            "FECHA_INSERT": "2026-07-05T09:30:00",
            "FECHA_COMPROMETIDA": "2026-08-15T00:00:00",
            "FECHA_REALIZACION": None,
            "SERVICIO": "Datos",
            "PRODUCTO": "Internet",
            "GRUPO_ASIGNADO_OTP": "Redes"
        }
    ]
    mock_tickets.return_value = [
        {
            "CC_INCIDENT_ID": "IM1001",
            "BRIEF_DESCRIPTION": "Falla en puerto",
            "STATUS": "Closed",
            "SUBMIT_DATE": "2026-07-10T14:00:00",
            "CLOSE_DATE": "2026-07-12T16:00:00",
            "ASSIGNED_GROUP": "Torre Redes",
            "REQUESTOR_NAME": "Juan",
            "CATEGORY": "incident"
        }
    ]
    mock_rfcs.return_value = [
        {
            "NUMBER": "RFC5001",
            "BRIEF_DESCRIPTION": "Ventana Mantenimiento",
            "STATUS": "Closed",
            "ORIG_DATE_ENTERED": "2026-07-15T11:00:00",
            "CLOSE_TIME": "2026-07-16T04:00:00",
            "ASSIGN_DEPT": "Sistemas",
            "REQUESTED_BY": "Pedro"
        }
    ]

    res = get_timeline_proyecto(12)
    assert res is not None
    assert res["proyecto_id"] == 12
    assert res["numero_proyecto"] == "0000108920"
    assert res["cliente"] == "BANCO DE CHILE"
    assert "lead_time_total_dias" in res
    assert "metricas" in res
    assert "eventos" in res
    assert isinstance(res["eventos"], list)
    assert len(res["eventos"]) >= 4

    m = res["metricas"]
    assert m["total_eventos"] == len(res["eventos"])
    assert m["eventos_sharepoint"] >= 1
    assert m["eventos_solot"] >= 2  # Insert + Compromiso
    assert m["eventos_ticket"] == 2  # Submit + Close
    assert m["eventos_rfc"] == 2     # Create + Close


# ==============================================================================
# UT-TL-02: test_get_timeline_orden_cronologico
# ==============================================================================
@patch("backend.db.get_proyecto_by_id")
@patch("backend.db.get_solots_by_proyecto")
@patch("backend.db.get_tickets_by_proyecto")
@patch("backend.db.get_rfcs_by_proyecto")
def test_get_timeline_orden_cronologico(mock_rfcs, mock_tickets, mock_solots, mock_proy):
    mock_proy.return_value = {
        "ID": 20,
        "Numero_Proyecto": "0000200000",
        "Creado": "2026-01-10T08:00:00"
    }
    mock_solots.return_value = [
        {
            "ID_OTP": 2001,
            "FECHA_INSERT": "2026-01-15T09:00:00",
            "FECHA_REALIZACION": "2026-02-20T18:00:00",
            "ESTADO_OTP": "5- ejecutada"
        }
    ]
    mock_tickets.return_value = [
        {
            "CC_INCIDENT_ID": "IM2001",
            "SUBMIT_DATE": "2026-01-20T12:00:00",
            "CLOSE_DATE": "2026-01-25T12:00:00"
        }
    ]
    mock_rfcs.return_value = [
        {
            "NUMBER": "RFC2001",
            "ORIG_DATE_ENTERED": "2026-02-01T10:00:00",
            "CLOSE_TIME": "2026-02-05T10:00:00"
        }
    ]

    res = get_timeline_proyecto(20)
    eventos = res["eventos"]
    assert len(eventos) >= 5

    # Validar que cada evento sea >= en fecha que el anterior
    for i in range(len(eventos) - 1):
        dt_current = _parse_timeline_dt(eventos[i]["fecha"])
        dt_next = _parse_timeline_dt(eventos[i+1]["fecha"])
        assert dt_current <= dt_next, f"Inconsistencia cronológica: {eventos[i]['id']} ({dt_current}) vs {eventos[i+1]['id']} ({dt_next})"


# ==============================================================================
# UT-TL-03: test_calculo_lapsos_entre_hitos
# ==============================================================================
@patch("backend.db.get_proyecto_by_id")
@patch("backend.db.get_solots_by_proyecto")
@patch("backend.db.get_tickets_by_proyecto")
@patch("backend.db.get_rfcs_by_proyecto")
def test_calculo_lapsos_entre_hitos(mock_rfcs, mock_tickets, mock_solots, mock_proy):
    mock_proy.return_value = {
        "ID": 30,
        "Numero_Proyecto": "0000300000",
        "Creado": "2026-03-01T10:00:00"
    }
    mock_solots.return_value = [
        {
            "ID_OTP": 3001,
            "FECHA_INSERT": "2026-03-06T10:00:00",  # +5 días
            "FECHA_REALIZACION": "2026-03-16T10:00:00",  # +10 días
            "ESTADO_OTP": "Cerrada"
        }
    ]
    mock_tickets.return_value = []
    mock_rfcs.return_value = []

    res = get_timeline_proyecto(30)
    eventos = res["eventos"]
    assert len(eventos) == 3

    # Evento 0: SharePoint Creado (lapso = 0)
    assert eventos[0]["lapso_dias"] == 0
    assert eventos[0]["fecha_formateada"] == "01/03/2026"

    # Evento 1: Apertura Solot (+5 días)
    assert eventos[1]["lapso_dias"] == 5
    assert eventos[1]["fecha_formateada"] == "06/03/2026"

    # Evento 2: Realización Solot (+10 días)
    assert eventos[2]["lapso_dias"] == 10
    assert eventos[2]["fecha_formateada"] == "16/03/2026"


# ==============================================================================
# UT-TL-04: test_clasificacion_hitos_futuros_y_vencidos
# ==============================================================================
@patch("backend.db.get_proyecto_by_id")
@patch("backend.db.get_solots_by_proyecto")
@patch("backend.db.get_tickets_by_proyecto")
@patch("backend.db.get_rfcs_by_proyecto")
def test_clasificacion_hitos_futuros_y_vencidos(mock_rfcs, mock_tickets, mock_solots, mock_proy):
    hoy = datetime.date.today()
    fecha_ayer = (hoy - datetime.timedelta(days=10)).isoformat()
    fecha_manana = (hoy + datetime.timedelta(days=15)).isoformat()

    mock_proy.return_value = {
        "ID": 40,
        "Numero_Proyecto": "0000400000",
        "Creado": (hoy - datetime.timedelta(days=30)).isoformat()
    }
    mock_solots.return_value = [
        # Compromiso vencido (no cerrada)
        {
            "ID_OTP": 4001,
            "FECHA_INSERT": (hoy - datetime.timedelta(days=25)).isoformat(),
            "FECHA_COMPROMETIDA": fecha_ayer,
            "ESTADO_OTP": "4- En curso"
        },
        # Compromiso futuro
        {
            "ID_OTP": 4002,
            "FECHA_INSERT": (hoy - datetime.timedelta(days=5)).isoformat(),
            "FECHA_COMPROMETIDA": fecha_manana,
            "ESTADO_OTP": "3- En asignacion"
        }
    ]
    mock_tickets.return_value = []
    mock_rfcs.return_value = []

    res = get_timeline_proyecto(40)
    m = res["metricas"]
    assert m["compromisos_vencidos"] == 1
    assert m["compromisos_pendientes"] == 1

    ev_vencido = next(e for e in res["eventos"] if e["id"] == "solot-comp-4001")
    assert ev_vencido["es_atrasado"] is True
    assert ev_vencido["es_futuro"] is False
    assert ev_vencido["dias_atraso"] == 10
    assert ev_vencido["estado"] == "Vencido"

    ev_futuro = next(e for e in res["eventos"] if e["id"] == "solot-comp-4002")
    assert ev_futuro["es_atrasado"] is False
    assert ev_futuro["es_futuro"] is True
    assert ev_futuro["dias_restantes"] == 15
    assert ev_futuro["estado"] == "Pendiente"

    # Priorización del compromiso vencido más crítico en el KPI
    assert m["proximo_compromiso"] is not None
    assert m["proximo_compromiso"]["es_atrasado"] is True
    assert m["proximo_compromiso"]["dias_atraso"] == 10


# ==============================================================================
# UT-TL-05: test_endpoint_api_timeline_auth_admin
# ==============================================================================
@patch("backend.db.get_proyecto_by_id")
@patch("backend.db.get_solots_by_proyecto")
@patch("backend.db.get_tickets_by_proyecto")
@patch("backend.db.get_rfcs_by_proyecto")
def test_endpoint_api_timeline_auth_admin(mock_rfcs, mock_tickets, mock_solots, mock_proy, auth_headers):
    mock_proy.return_value = {
        "ID": 50,
        "Numero_Proyecto": "0000500000",
        "Cliente": "CLARO CHILE",
        "Creado": "2026-01-01"
    }
    mock_solots.return_value = []
    mock_tickets.return_value = []
    mock_rfcs.return_value = []

    response = client.get("/api/proyectos/50/timeline", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["proyecto_id"] == 50
    assert data["cliente"] == "CLARO CHILE"
    assert "metricas" in data


# ==============================================================================
# UT-TL-06: test_endpoint_api_timeline_auth_lti
# ==============================================================================
@patch("backend.db.get_proyecto_by_id")
@patch("backend.db.get_solots_by_proyecto")
@patch("backend.db.get_tickets_by_proyecto")
@patch("backend.db.get_rfcs_by_proyecto")
def test_endpoint_api_timeline_auth_lti(mock_rfcs, mock_tickets, mock_solots, mock_proy, lti_headers):
    mock_proy.return_value = {
        "ID": 60,
        "Numero_Proyecto": "0000600000",
        "Cliente": "ENTEL PCS",
        "Creado": "2026-02-01"
    }
    mock_solots.return_value = []
    mock_tickets.return_value = []
    mock_rfcs.return_value = []

    response = client.get("/api/proyectos/60/timeline", headers=lti_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["proyecto_id"] == 60


# ==============================================================================
# UT-TL-07: test_endpoint_api_timeline_no_auth
# ==============================================================================
def test_endpoint_api_timeline_no_auth():
    response = client.get("/api/proyectos/1/timeline")
    assert response.status_code == 401


# ==============================================================================
# UT-TL-08: test_endpoint_api_timeline_proyecto_inexistente
# ==============================================================================
@patch("backend.db.get_proyecto_by_id")
def test_endpoint_api_timeline_proyecto_inexistente(mock_proy, auth_headers):
    mock_proy.return_value = None

    response = client.get("/api/proyectos/999999/timeline", headers=auth_headers)
    assert response.status_code == 404
    detail = response.json().get("detail", "")
    assert "999999" in detail


# ==============================================================================
# UT-TL-09: test_resiliencia_fechas_nulas_o_corruptas
# ==============================================================================
@patch("backend.db.get_proyecto_by_id")
@patch("backend.db.get_solots_by_proyecto")
@patch("backend.db.get_tickets_by_proyecto")
@patch("backend.db.get_rfcs_by_proyecto")
def test_resiliencia_fechas_nulas_o_corruptas(mock_rfcs, mock_tickets, mock_solots, mock_proy):
    mock_proy.return_value = {
        "ID": 90,
        "Numero_Proyecto": "0000900000",
        "Creado": None,
        "fecha_solicitud_lti": "Fecha Invalida",
        "Modificado": "NONE"
    }
    mock_solots.return_value = [
        {
            "ID_OTP": 9001,
            "FECHA_INSERT": "NULL",
            "FECHA_COMPROMETIDA": "",
            "FECHA_REALIZACION": None,
            "ESTADO_OTP": "Pendiente"
        }
    ]
    mock_tickets.return_value = [
        {
            "CC_INCIDENT_ID": "IM9001",
            "SUBMIT_DATE": None,
            "CLOSE_DATE": "invalid-str"
        }
    ]
    mock_rfcs.return_value = [
        {
            "NUMBER": "RFC9001",
            "ORIG_DATE_ENTERED": "",
            "CLOSE_TIME": None
        }
    ]

    # No debe arrojar excepción ni error 500
    res = get_timeline_proyecto(90)
    assert res is not None
    assert res["eventos"] == []
    assert res["lead_time_total_dias"] == 0
    assert res["metricas"]["total_eventos"] == 0


# ==============================================================================
# UT-TL-10: test_metricas_agregadas_cabecera
# ==============================================================================
@patch("backend.db.get_proyecto_by_id")
@patch("backend.db.get_solots_by_proyecto")
@patch("backend.db.get_tickets_by_proyecto")
@patch("backend.db.get_rfcs_by_proyecto")
def test_metricas_agregadas_cabecera(mock_rfcs, mock_tickets, mock_solots, mock_proy):
    hoy = datetime.date.today()
    mock_proy.return_value = {
        "ID": 100,
        "Numero_Proyecto": "0000100000",
        "Creado": (hoy - datetime.timedelta(days=50)).isoformat(),
        "Modificado": (hoy - datetime.timedelta(days=10)).isoformat()
    }
    mock_solots.return_value = [
        {
            "ID_OTP": 101,
            "FECHA_INSERT": (hoy - datetime.timedelta(days=40)).isoformat(),
            "ESTADO_OTP": "4- En curso"
        },
        {
            "ID_OTP": 102,
            "FECHA_INSERT": (hoy - datetime.timedelta(days=30)).isoformat(),
            "ESTADO_OTP": "5- ejecutada",
            "FECHA_REALIZACION": (hoy - datetime.timedelta(days=5)).isoformat()
        }
    ]
    mock_tickets.return_value = [
        {
            "CC_INCIDENT_ID": "IM101",
            "SUBMIT_DATE": (hoy - datetime.timedelta(days=20)).isoformat()
        }
    ]
    mock_rfcs.return_value = [
        {
            "NUMBER": "RFC101",
            "ORIG_DATE_ENTERED": (hoy - datetime.timedelta(days=15)).isoformat()
        }
    ]

    res = get_timeline_proyecto(100)
    assert res["lead_time_total_dias"] == 50
    m = res["metricas"]
    assert m["eventos_sharepoint"] == 2
    assert m["eventos_solot"] == 3
    assert m["eventos_ticket"] == 1
    assert m["eventos_rfc"] == 1
    assert m["total_eventos"] == 7
    assert m["ultimo_hito"] is not None
