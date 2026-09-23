import pytest
import datetime
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.main import app
from backend.db import (
    compilar_minuta_texto_plano,
    compilar_minuta_markdown,
    compilar_minuta_html,
    get_diagnostico_proyecto
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
# PRUEBAS UNITARIAS: COMPILACIÓN DE MINUTAS
# ==============================================================================
def test_compilar_minuta_texto_plano():
    proyecto = {
        "Numero_Proyecto": "0000108920",
        "Cliente": "BANCO DE CHILE",
        "LT_Asignado": "ALEJANDRO AGUILAR",
        "Solicitante": "CARLOS PEREZ",
        "Estado": "En revision"
    }
    salud = {
        "score": "CRITICAL",
        "color": "red",
        "label": "Crítico",
        "motivos": ["1 Solot vencida"]
    }
    cuellos = [{
        "id": "CB-01",
        "tipo": "SOLOT_VENCIDA",
        "severidad": "ALTA",
        "identificador": "OTP-1001",
        "descripcion": "Solot vencida hace 10 días.",
        "responsable_area": "Operaciones SGA"
    }]
    recs = [{
        "orden": 1,
        "prioridad": "ALTA",
        "destinatario_escalamiento": "Operaciones SGA",
        "accion": "Reprogramar Solot OTP-1001",
        "canal_sugerido": "Correo formal"
    }]

    texto = compilar_minuta_texto_plano(
        proyecto=proyecto,
        salud=salud,
        antiguedad_dias=25,
        porcentaje_avance=50.0,
        solots_ejecutadas=1,
        total_solots=2,
        cuellos_de_botella=cuellos,
        recomendaciones=recs
    )

    assert "DIAGNÓSTICO EJECUTIVO HALO" in texto
    assert "PROYECTO: 0000108920" in texto
    assert "CLIENTE: BANCO DE CHILE" in texto
    assert "🔴 Crítico" in texto
    assert "OTP-1001" in texto
    assert "Reprogramar Solot OTP-1001" in texto


def test_compilar_minuta_markdown():
    proyecto = {
        "Numero_Proyecto": "0000108920",
        "Cliente": "BANCO DE CHILE",
        "LT_Asignado": "ALEJANDRO AGUILAR",
        "Solicitante": "CARLOS PEREZ",
        "Estado": "En revision"
    }
    salud = {"score": "HEALTHY", "color": "green", "label": "Saludable", "motivos": []}
    
    md = compilar_minuta_markdown(
        proyecto=proyecto,
        salud=salud,
        antiguedad_dias=10,
        porcentaje_avance=100.0,
        solots_ejecutadas=3,
        total_solots=3,
        cuellos_de_botella=[],
        recomendaciones=[]
    )

    assert "### ⚡ DIAGNÓSTICO EJECUTIVO — HALO Líderes TI" in md
    assert "**Proyecto:** `0000108920`" in md
    assert "**Cliente:** **BANCO DE CHILE**" in md
    assert "🟢 **Saludable**" in md
    assert "No se detectaron cuellos de botella" in md


def test_compilar_minuta_html():
    proyecto = {
        "Numero_Proyecto": "0000108920",
        "Cliente": "BANCO DE CHILE",
        "LT_Asignado": "ALEJANDRO AGUILAR",
        "Solicitante": "CARLOS PEREZ",
        "Estado": "En revision"
    }
    salud = {"score": "WARNING", "color": "yellow", "label": "En Riesgo", "motivos": ["1 Solot por vencer"]}
    
    html = compilar_minuta_html(
        proyecto=proyecto,
        salud=salud,
        antiguedad_dias=15,
        porcentaje_avance=66.7,
        solots_ejecutadas=2,
        total_solots=3,
        cuellos_de_botella=[],
        recomendaciones=[]
    )

    assert "<div style=" in html
    assert "⚡ Diagnóstico Ejecutivo — HALO Líderes TI" in html
    assert "0000108920" in html
    assert "BANCO DE CHILE" in html
    assert "En Riesgo" in html


# ==============================================================================
# PRUEBAS DEL MOTOR get_diagnostico_proyecto
# ==============================================================================
@patch("backend.db.get_proyecto_by_id")
@patch("backend.db.get_solots_by_proyecto")
@patch("backend.db.get_tickets_by_proyecto")
@patch("backend.db.get_rfcs_by_proyecto")
def test_diagnostico_motor_proyecto_critico(mock_rfcs, mock_tickets, mock_solots, mock_proy):
    hoy = datetime.date.today()
    mock_proy.return_value = {
        "ID": 100,
        "Numero_Proyecto": "000012345",
        "Cliente": "EMPRESA TEST CRITICA",
        "LT_Asignado": "Líder Alpha",
        "Solicitante": "Juan Pérez",
        "Estado": "En revision",
        "Tipo_Servicio": "Cloud",
        "Creado": (hoy - datetime.timedelta(days=40)).isoformat(),
        "salud": {
            "score": "CRITICAL",
            "color": "red",
            "label": "Crítico",
            "motivos": ["2 Solots vencidas", "1 Ticket crítico"]
        }
    }

    # 2 Solots: 1 vencida hace 20 días (CRITICA), 1 vencida hace 10 días (ALTA)
    mock_solots.return_value = [
        {
            "ID_OTP": 501,
            "DESCR_OTP": "Instalación de Fibra",
            "ESTADO_OTP": "Pendiente",
            "FECHA_COMPROMETIDA": (hoy - datetime.timedelta(days=20)).isoformat(),
            "GRUPO_ASIGNADO_OTP": "Operaciones SGA"
        },
        {
            "ID_OTP": 502,
            "DESCR_OTP": "Configuración Router",
            "ESTADO_OTP": "En Proceso",
            "FECHA_COMPROMETIDA": (hoy - datetime.timedelta(days=10)).isoformat(),
            "GRUPO_ASIGNADO_OTP": "Operaciones SGA"
        },
        {
            "ID_OTP": 503,
            "DESCR_OTP": "Revisión Factibilidad",
            "ESTADO_OTP": "Cerrada",
            "FECHA_COMPROMETIDA": (hoy - datetime.timedelta(days=30)).isoformat(),
            "GRUPO_ASIGNADO_OTP": "Operaciones SGA"
        }
    ]

    # 1 Ticket crítico detenido hace 18 días en Torre Linux
    mock_tickets.return_value = [
        {
            "CC_INCIDENT_ID": "SD1098234",
            "BRIEF_DESCRIPTION": "Configuración VLAN",
            "STATUS": "Asignado",
            "SUBMIT_DATE": (hoy - datetime.timedelta(days=18)).isoformat(),
            "ASSIGNED_GROUP": "Torre Linux",
            "ASSIGNED_TO": "Operador 1"
        },
        {
            "CC_INCIDENT_ID": "SD1098200",
            "BRIEF_DESCRIPTION": "Ticket previo resuelto",
            "STATUS": "Cerrado",
            "SUBMIT_DATE": (hoy - datetime.timedelta(days=30)).isoformat(),
            "ASSIGNED_GROUP": "Torre Linux",
            "ASSIGNED_TO": "Operador 1"
        }
    ]

    mock_rfcs.return_value = []

    res = get_diagnostico_proyecto(100)
    assert res is not None
    assert res["proyecto_id"] == 100
    assert res["numero_proyecto"] == "000012345"
    assert res["cliente"] == "EMPRESA TEST CRITICA"
    assert res["salud"]["score"] == "CRITICAL"
    assert res["antiguedad_dias"] >= 40

    # Resumen operacional
    ro = res["resumen_operacional"]
    assert ro["total_solots"] == 3
    assert ro["solots_ejecutadas"] == 1
    assert ro["solots_pendientes"] == 2
    assert ro["solots_vencidas"] == 2
    assert ro["porcentaje_avance_solots"] == 33.3
    assert ro["total_tickets"] == 2
    assert ro["tickets_abiertos"] == 1
    assert ro["tickets_criticos"] == 1

    # Cuellos de botella: 2 solots + 1 ticket = 3
    cuellos = res["cuellos_de_botella"]
    assert len(cuellos) == 3
    
    # Validar que hay un cuello con Torre Linux
    linux_cb = [c for c in cuellos if c["tipo"] == "TICKET_DETENIDO"]
    assert len(linux_cb) == 1
    assert linux_cb[0]["responsable_area"] == "Torre Linux"
    assert linux_cb[0]["severidad"] == "CRITICA"

    # Validar recomendaciones
    recs = res["recomendaciones_escalamiento"]
    assert len(recs) >= 2
    assert any("Torre Linux" in r["destinatario_escalamiento"] for r in recs)
    assert any(r["prioridad"] == "URGENTE" for r in recs)

    # Validar minutas
    assert res["minuta_ejecutiva"]["texto_plano"] != ""
    assert res["minuta_ejecutiva"]["markdown"] != ""
    assert res["minuta_ejecutiva"]["html"] != ""


@patch("backend.db.get_proyecto_by_id")
@patch("backend.db.get_solots_by_proyecto")
@patch("backend.db.get_tickets_by_proyecto")
@patch("backend.db.get_rfcs_by_proyecto")
def test_diagnostico_motor_proyecto_saludable(mock_rfcs, mock_tickets, mock_solots, mock_proy):
    hoy = datetime.date.today()
    mock_proy.return_value = {
        "ID": 200,
        "Numero_Proyecto": "000055555",
        "Cliente": "EMPRESA VERDE SPA",
        "LT_Asignado": "Líder Beta",
        "Solicitante": "María González",
        "Estado": "Atendido",
        "Tipo_Servicio": "Conectividad",
        "Creado": (hoy - datetime.timedelta(days=10)).isoformat(),
        "salud": {"score": "HEALTHY", "color": "green", "label": "Saludable", "motivos": []}
    }
    mock_solots.return_value = [
        {
            "ID_OTP": 601,
            "DESCR_OTP": "Activación Servicio",
            "ESTADO_OTP": "5- Ejecutada",
            "FECHA_COMPROMETIDA": (hoy + datetime.timedelta(days=10)).isoformat(),
            "GRUPO_ASIGNADO_OTP": "Operaciones SGA"
        }
    ]
    mock_tickets.return_value = []
    mock_rfcs.return_value = []

    res = get_diagnostico_proyecto(200)
    assert res is not None
    assert res["salud"]["score"] == "HEALTHY"
    assert len(res["cuellos_de_botella"]) == 0
    assert res["resumen_operacional"]["porcentaje_avance_solots"] == 100.0
    
    # Recomendación preventiva
    assert len(res["recomendaciones_escalamiento"]) == 1
    assert res["recomendaciones_escalamiento"][0]["prioridad"] == "BAJA"
    assert "operación regular" in res["recomendaciones_escalamiento"][0]["accion"]


# ==============================================================================
# PRUEBAS DEL ENDPOINT HTTP GET /api/proyectos/{id}/diagnostico
# ==============================================================================
@patch("backend.main.get_diagnostico_proyecto")
def test_endpoint_diagnostico_200_ok(mock_diag, auth_headers):
    mock_diag.return_value = {
        "proyecto_id": 142,
        "numero_proyecto": "0000108920",
        "cliente": "BANCO DE CHILE",
        "lt_asignado": "ALEJANDRO AGUILAR",
        "solicitante": "CARLOS PEREZ",
        "estado_sp": "En revision",
        "tipo_servicio": "Cloud",
        "fecha_creacion_lti": "2026-08-10T14:30:00",
        "antiguedad_dias": 43,
        "salud": {"score": "CRITICAL", "color": "red", "label": "Crítico", "motivos": ["Solot vencida"]},
        "resumen_operacional": {
            "total_solots": 5,
            "solots_ejecutadas": 3,
            "solots_pendientes": 2,
            "solots_vencidas": 2,
            "solots_por_vencer": 0,
            "porcentaje_avance_solots": 60.0,
            "total_tickets": 3,
            "tickets_abiertos": 1,
            "tickets_cerrados": 2,
            "tickets_criticos": 1,
            "tickets_atencion": 0,
            "total_rfcs": 1,
            "rfcs_abiertas": 1
        },
        "cuellos_de_botella": [],
        "recomendaciones_escalamiento": [],
        "minuta_ejecutiva": {
            "asunto_sugerido": "[HALO] Diagnóstico",
            "texto_plano": "Texto",
            "markdown": "MD",
            "html": "<p>HTML</p>"
        },
        "timestamp_generacion": "2026-09-22T23:35:00"
    }

    response = client.get("/api/proyectos/142/diagnostico", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["proyecto_id"] == 142
    assert data["cliente"] == "BANCO DE CHILE"
    assert data["resumen_operacional"]["porcentaje_avance_solots"] == 60.0


def test_endpoint_diagnostico_401_unauthorized():
    response = client.get("/api/proyectos/142/diagnostico")
    assert response.status_code == 401


@patch("backend.main.get_diagnostico_proyecto")
def test_endpoint_diagnostico_404_not_found(mock_diag, auth_headers):
    mock_diag.return_value = None
    response = client.get("/api/proyectos/999999/diagnostico", headers=auth_headers)
    assert response.status_code == 404
    assert "no fue encontrado" in response.json()["detail"]


@patch("backend.main.get_diagnostico_proyecto")
def test_endpoint_diagnostico_lti_role_allowed(mock_diag, lti_headers):
    mock_diag.return_value = {
        "proyecto_id": 142,
        "cliente": "CLIENTE LTI",
        "minuta_ejecutiva": {}
    }
    response = client.get("/api/proyectos/142/diagnostico", headers=lti_headers)
    assert response.status_code == 200


@patch("backend.main.get_diagnostico_proyecto")
def test_endpoint_diagnostico_pm_role_forbidden(mock_diag, pm_headers):
    response = client.get("/api/proyectos/142/diagnostico", headers=pm_headers)
    assert response.status_code == 403


@patch("backend.db.get_proyecto_by_id")
@patch("backend.db.get_solots_by_proyecto")
@patch("backend.db.get_tickets_by_proyecto")
@patch("backend.db.get_rfcs_by_proyecto")
def test_diagnostico_avance_solots_y_rfcs(mock_rfcs, mock_tickets, mock_solots, mock_proy):
    hoy = datetime.date.today()
    mock_proy.return_value = {
        "ID": 300,
        "Numero_Proyecto": "000077777",
        "Cliente": "CLIENTE MIXTO",
        "LT_Asignado": "Líder Gamma",
        "Solicitante": "Pedro Gómez",
        "Estado": "En revision",
        "salud": {"score": "WARNING", "color": "yellow", "label": "En Riesgo"}
    }
    # 10 Solots: 4 ejecutadas, 6 pendientes
    mock_solots.return_value = [
        {"ID_OTP": 1, "ESTADO_OTP": "Cerrada"},
        {"ID_OTP": 2, "ESTADO_OTP": "5- Ejecutada"},
        {"ID_OTP": 3, "ESTADO_OTP": "Abortado"},
        {"ID_OTP": 4, "ESTADO_OTP": "Aprobado"},
        {"ID_OTP": 5, "ESTADO_OTP": "En Asignacion"},
        {"ID_OTP": 6, "ESTADO_OTP": "En Revision"},
        {"ID_OTP": 7, "ESTADO_OTP": "Pendiente"},
        {"ID_OTP": 8, "ESTADO_OTP": "Pendiente"},
        {"ID_OTP": 9, "ESTADO_OTP": "Pendiente"},
        {"ID_OTP": 10, "ESTADO_OTP": "Pendiente"}
    ]
    # Ticket entre 7 y 14 días (atención)
    mock_tickets.return_value = [
        {
            "CC_INCIDENT_ID": "SD88888",
            "BRIEF_DESCRIPTION": "Ticket en advertencia",
            "STATUS": "En Curso",
            "SUBMIT_DATE": (hoy - datetime.timedelta(days=9)).isoformat(),
            "ASSIGNED_GROUP": "Torre Microsoft"
        }
    ]
    # RFC abierta
    mock_rfcs.return_value = [
        {
            "NUMBER": "RFC9999",
            "BRIEF_DESCRIPTION": "RFC Cambio de Switch",
            "CLOSE_TIME": None,
            "ASSIGN_DEPT": "Infraestructura Redes"
        }
    ]

    res = get_diagnostico_proyecto(300)
    assert res["resumen_operacional"]["porcentaje_avance_solots"] == 40.0
    assert res["resumen_operacional"]["tickets_atencion"] == 1
    assert res["resumen_operacional"]["rfcs_abiertas"] == 1

    # Verificar cuellos de botella para ticket en riesgo y RFC pendiente
    cuellos = res["cuellos_de_botella"]
    assert any(c["tipo"] == "TICKET_EN_RIESGO" and c["severidad"] == "MEDIA" for c in cuellos)
    assert any(c["tipo"] == "RFC_PENDIENTE" and c["severidad"] == "MEDIA" for c in cuellos)

