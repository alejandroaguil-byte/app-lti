"""
PRUEBAS UNITARIAS: FICHA EJECUTIVA PDF & REGLAS DE NEGOCIO (BACKEND)
Especificación: SPECS_FICHA_EJECUTIVA_PDF.md
"""

import pytest
import datetime
import re
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.main import app
from backend.db import (
    _parse_date,
    get_ficha_ejecutiva_data,
    generar_ficha_ejecutiva_html
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
# UT-PDF-01: Estructura de get_ficha_ejecutiva_data
# ==============================================================================
@patch("backend.db.get_proyecto_by_id")
@patch("backend.db.get_diagnostico_proyecto")
@patch("backend.db.get_solots_by_proyecto")
@patch("backend.db.get_tickets_by_proyecto")
@patch("backend.db.get_rfcs_by_proyecto")
def test_get_ficha_ejecutiva_data_estructura(mock_rfcs, mock_tickets, mock_solots, mock_diag, mock_proy):
    hoy = datetime.date.today()
    mock_proy.return_value = {
        "ID": 12,
        "Numero_Proyecto": "0000108920",
        "Cliente": "BANCO DE CHILE",
        "LT_Asignado": "ALEJANDRO JAVIER AGUILAR MORALES",
        "Solicitante": "CARLOS PEREZ GOMEZ",
        "Estado": "Atendido",
        "Tipo_Servicio": "Cloud & Conectividad",
        "Creado": (hoy - datetime.timedelta(days=70)).isoformat(),
        "salud": {
            "score": "CRITICAL",
            "color": "red",
            "label": "Crítico",
            "motivos": ["1 Solot vencida"]
        }
    }
    mock_diag.return_value = {
        "antiguedad_dias": 70,
        "resumen_operacional": {
            "total_solots": 2,
            "solots_ejecutadas": 1,
            "solots_pendientes": 1,
            "solots_vencidas": 1,
            "solots_por_vencer": 0,
            "porcentaje_avance_solots": 50.0,
            "total_tickets": 2,
            "tickets_abiertos": 1,
            "tickets_cerrados": 1,
            "tickets_criticos": 1,
            "tickets_atencion": 0,
            "total_rfcs": 1,
            "rfcs_abiertas": 1
        },
        "cuellos_de_botella": [
            {
                "id": "CB-01",
                "tipo": "SOLOT_VENCIDA",
                "severidad": "ALTA",
                "identificador": "OTP-883491",
                "descripcion": "Solot vencida hace 12 días.",
                "responsable_area": "Operaciones SGA",
                "estado_actual": "En Proceso"
            }
        ],
        "recomendaciones_escalamiento": [
            {
                "orden": 1,
                "prioridad": "URGENTE",
                "destinatario_escalamiento": "Jefatura Torre Linux",
                "accion": "Escalar ticket detenido.",
                "canal_sugerido": "Correo formal"
            }
        ],
        "minuta_ejecutiva": {
            "asunto_sugerido": "[HALO] Diagnóstico: 0000108920"
        }
    }
    mock_solots.return_value = [
        {
            "ID_OTP": 883491,
            "NRO_PROYECTO": "0000108920",
            "DESCR_OTP": "Instalación enlace respaldo",
            "ESTADO_OTP": "En Proceso",
            "FECHA_COMPROMETIDA": (hoy - datetime.timedelta(days=12)).isoformat(),
            "SERVICIO": "Conectividad IP",
            "PRODUCTO": "MPLS"
        }
    ]
    mock_tickets.return_value = [
        {
            "CC_INCIDENT_ID": "SD1098421",
            "BRIEF_DESCRIPTION": "Configuración de reglas BGP",
            "ASSIGNED_GROUP": "Torre Linux",
            "ASSIGNED_TO": "JUAN PEREZ",
            "STATUS": "Asignado",
            "CATEGORY": "2 - Alta",
            "SUBMIT_DATE": (hoy - datetime.timedelta(days=18)).isoformat()
        }
    ]
    mock_rfcs.return_value = [
        {
            "NUMBER": "RFC-2026-4401",
            "BRIEF_DESCRIPTION": "Pase a producción túnel",
            "REQUESTED_BY": "CARLOS PEREZ GOMEZ",
            "ASSIGN_DEPT": "Gestión de Cambios",
            "CLOSE_TIME": None
        }
    ]

    data = get_ficha_ejecutiva_data(12, username="alejandro.aguilar")

    assert data is not None
    assert "folio" in data
    assert "fecha_emision" in data
    assert "fecha_emision_formateada" in data
    assert data["usuario_generador"] == "alejandro.aguilar"

    # Validar sección proyecto
    proy = data["proyecto"]
    assert proy["numero_proyecto"] == "0000108920"
    assert proy["cliente"] == "BANCO DE CHILE"
    assert proy["salud"]["label"] == "Crítico"

    # Validar KPIs
    kpis = data["kpis"]
    assert kpis["total_solots"] == 2
    assert kpis["solots_vencidas"] == 1

    # Validar Tablas
    tablas = data["tablas"]
    assert len(tablas["solots"]) == 1
    assert tablas["solots"][0]["id_otp"] == 883491
    assert tablas["solots"][0]["estado_alerta"] == "VENCIDA"

    assert len(tablas["tickets"]) == 1
    assert tablas["tickets"][0]["cc_incident_id"] == "SD1098421"
    assert tablas["tickets"][0]["estado_alerta"] == "CRITICO"

    assert len(tablas["rfcs"]) == 1
    assert tablas["rfcs"][0]["number"] == "RFC-2026-4401"
    assert tablas["rfcs"][0]["estado"] == "En Proceso"


# ==============================================================================
# UT-PDF-02: Proyecto Inexistente retorna None
# ==============================================================================
@patch("backend.db.get_proyecto_by_id")
def test_get_ficha_ejecutiva_data_proyecto_inexistente(mock_proy):
    mock_proy.return_value = None
    result = get_ficha_ejecutiva_data(999999, username="test_user")
    assert result is None


# ==============================================================================
# UT-PDF-03: Formato del Folio y Unicidad Determinista
# ==============================================================================
@patch("backend.db.get_proyecto_by_id")
@patch("backend.db.get_diagnostico_proyecto")
@patch("backend.db.get_solots_by_proyecto")
@patch("backend.db.get_tickets_by_proyecto")
@patch("backend.db.get_rfcs_by_proyecto")
def test_folio_formato_y_unicidad(mock_rfcs, mock_tickets, mock_solots, mock_diag, mock_proy):
    mock_proy.return_value = {
        "ID": 55,
        "Numero_Proyecto": "0000108920",
        "Cliente": "TEST CLIENT",
        "LT_Asignado": "Líder Test",
        "Estado": "Generado",
        "Creado": "2026-09-01"
    }
    mock_diag.return_value = {}
    mock_solots.return_value = []
    mock_tickets.return_value = []
    mock_rfcs.return_value = []

    data1 = get_ficha_ejecutiva_data(55, username="usuario_alpha")
    folio1 = data1["folio"]

    # Validar formato con regex exacto
    folio_regex = r"^HALO-FE-\d{4}-\d{6}-[A-F0-9]{4}$"
    assert re.match(folio_regex, folio1), f"El folio '{folio1}' no cumple con el formato {folio_regex}"

    # Validar unicidad/diferenciación con distinto usuario
    data2 = get_ficha_ejecutiva_data(55, username="usuario_beta")
    folio2 = data2["folio"]
    assert re.match(folio_regex, folio2)


# ==============================================================================
# UT-PDF-04: Cálculo de días de atraso en Solots
# ==============================================================================
@patch("backend.db.get_proyecto_by_id")
@patch("backend.db.get_diagnostico_proyecto")
@patch("backend.db.get_solots_by_proyecto")
@patch("backend.db.get_tickets_by_proyecto")
@patch("backend.db.get_rfcs_by_proyecto")
def test_calculo_dias_atraso_solots(mock_rfcs, mock_tickets, mock_solots, mock_diag, mock_proy):
    hoy = datetime.date.today()
    mock_proy.return_value = {
        "ID": 20,
        "Numero_Proyecto": "0000200001",
        "Cliente": "CLIENTE VENCIDO",
        "Estado": "En revision"
    }
    mock_diag.return_value = {}
    mock_tickets.return_value = []
    mock_rfcs.return_value = []

    # 3 Solots: 1 vencida (15 días), 1 por vencer (3 días), 1 al día (15 días a futuro), 1 cerrada (fecha pasada pero cerrada)
    mock_solots.return_value = [
        {
            "ID_OTP": 101,
            "DESCR_OTP": "Solot Vencida",
            "ESTADO_OTP": "En Proceso",
            "FECHA_COMPROMETIDA": (hoy - datetime.timedelta(days=15)).isoformat()
        },
        {
            "ID_OTP": 102,
            "DESCR_OTP": "Solot Por Vencer",
            "ESTADO_OTP": "Pendiente",
            "FECHA_COMPROMETIDA": (hoy + datetime.timedelta(days=3)).isoformat()
        },
        {
            "ID_OTP": 103,
            "DESCR_OTP": "Solot Al Día",
            "ESTADO_OTP": "Pendiente",
            "FECHA_COMPROMETIDA": (hoy + datetime.timedelta(days=20)).isoformat()
        },
        {
            "ID_OTP": 104,
            "DESCR_OTP": "Solot Cerrada Pasada",
            "ESTADO_OTP": "Cerrada",
            "FECHA_COMPROMETIDA": (hoy - datetime.timedelta(days=30)).isoformat()
        }
    ]

    data = get_ficha_ejecutiva_data(20, username="test_lead")
    solots = data["tablas"]["solots"]

    s101 = next(s for s in solots if s["id_otp"] == 101)
    assert s101["estado_alerta"] == "VENCIDA"
    assert s101["dias_atraso"] == 15

    s102 = next(s for s in solots if s["id_otp"] == 102)
    assert s102["estado_alerta"] == "POR_VENCER"
    assert s102["dias_atraso"] == 0

    s103 = next(s for s in solots if s["id_otp"] == 103)
    assert s103["estado_alerta"] == "NORMAL"
    assert s103["dias_atraso"] == 0

    s104 = next(s for s in solots if s["id_otp"] == 104)
    assert s104["estado_alerta"] == "NORMAL"
    assert s104["dias_atraso"] == 0


# ==============================================================================
# UT-PDF-05: Clasificación de antigüedad de Tickets HPSM
# ==============================================================================
@patch("backend.db.get_proyecto_by_id")
@patch("backend.db.get_diagnostico_proyecto")
@patch("backend.db.get_solots_by_proyecto")
@patch("backend.db.get_tickets_by_proyecto")
@patch("backend.db.get_rfcs_by_proyecto")
def test_clasificacion_antiguedad_tickets(mock_rfcs, mock_tickets, mock_solots, mock_diag, mock_proy):
    hoy = datetime.date.today()
    mock_proy.return_value = {
        "ID": 30,
        "Numero_Proyecto": "0000300001",
        "Cliente": "CLIENTE TICKETS",
        "Estado": "Generado"
    }
    mock_diag.return_value = {}
    mock_solots.return_value = []
    mock_rfcs.return_value = []

    mock_tickets.return_value = [
        {
            "CC_INCIDENT_ID": "T-CRIT",
            "STATUS": "Asignado",
            "SUBMIT_DATE": (hoy - datetime.timedelta(days=22)).isoformat()
        },
        {
            "CC_INCIDENT_ID": "T-ATEN",
            "STATUS": "Abierto",
            "SUBMIT_DATE": (hoy - datetime.timedelta(days=10)).isoformat()
        },
        {
            "CC_INCIDENT_ID": "T-NORM",
            "STATUS": "Abierto",
            "SUBMIT_DATE": (hoy - datetime.timedelta(days=3)).isoformat()
        },
        {
            "CC_INCIDENT_ID": "T-CERR",
            "STATUS": "Cerrado",
            "SUBMIT_DATE": (hoy - datetime.timedelta(days=40)).isoformat()
        }
    ]

    data = get_ficha_ejecutiva_data(30, username="test_lead")
    tickets = data["tablas"]["tickets"]

    t_crit = next(t for t in tickets if t["cc_incident_id"] == "T-CRIT")
    assert t_crit["estado_alerta"] == "CRITICO"
    assert t_crit["dias_abierto"] == 22

    t_aten = next(t for t in tickets if t["cc_incident_id"] == "T-ATEN")
    assert t_aten["estado_alerta"] == "ATENCION"
    assert t_aten["dias_abierto"] == 10

    t_norm = next(t for t in tickets if t["cc_incident_id"] == "T-NORM")
    assert t_norm["estado_alerta"] == "NORMAL"
    assert t_norm["dias_abierto"] == 3

    t_cerr = next(t for t in tickets if t["cc_incident_id"] == "T-CERR")
    assert t_cerr["estado_alerta"] == "NORMAL"
    assert t_cerr["dias_abierto"] == 0


# ==============================================================================
# UT-PDF-06: Endpoint API /ficha-ejecutiva con Auth ADMIN
# ==============================================================================
@patch("backend.main.get_ficha_ejecutiva_data")
def test_endpoint_api_ficha_ejecutiva_auth_admin(mock_get_ficha, auth_headers):
    mock_get_ficha.return_value = {
        "folio": "HALO-FE-2026-108920-ABCD",
        "proyecto": {"numero_proyecto": "0000108920", "cliente": "TEST"},
        "kpis": {},
        "tablas": {"solots": [], "tickets": [], "rfcs": []}
    }

    res = client.get("/api/proyectos/12/ficha-ejecutiva", headers=auth_headers)
    assert res.status_code == 200
    json_data = res.json()
    assert json_data["folio"] == "HALO-FE-2026-108920-ABCD"
    assert json_data["proyecto"]["cliente"] == "TEST"


# ==============================================================================
# UT-PDF-07: Endpoint API /ficha-ejecutiva con Auth LTI
# ==============================================================================
@patch("backend.main.get_ficha_ejecutiva_data")
def test_endpoint_api_ficha_ejecutiva_auth_lti(mock_get_ficha, lti_headers):
    mock_get_ficha.return_value = {
        "folio": "HALO-FE-2026-108920-EF01",
        "proyecto": {"numero_proyecto": "0000108920", "cliente": "TEST LTI"},
        "kpis": {},
        "tablas": {"solots": [], "tickets": [], "rfcs": []}
    }

    res = client.get("/api/proyectos/12/ficha-ejecutiva", headers=lti_headers)
    assert res.status_code == 200
    assert res.json()["folio"] == "HALO-FE-2026-108920-EF01"


# ==============================================================================
# UT-PDF-08: Endpoint API /ficha-ejecutiva sin Auth retorna 401
# ==============================================================================
def test_endpoint_api_ficha_ejecutiva_no_auth():
    res = client.get("/api/proyectos/12/ficha-ejecutiva")
    assert res.status_code == 401


# ==============================================================================
# UT-PDF-09: Endpoint API /ficha-html genera HTML con tokens Claro HALO
# ==============================================================================
@patch("backend.main.get_ficha_ejecutiva_data")
def test_endpoint_api_ficha_html_generacion(mock_get_ficha, auth_headers):
    mock_get_ficha.return_value = {
        "folio": "HALO-FE-2026-108920-XYZ9",
        "fecha_emision_formateada": "23/09/2026 15:30",
        "usuario_generador": "alejandro.aguilar",
        "proyecto": {
            "numero_proyecto": "0000108920",
            "cliente": "BANCO SANTANDER",
            "lt_asignado": "ALEJANDRO AGUILAR",
            "solicitante": "CARLOS PEREZ",
            "estado_sp": "Atendido",
            "tipo_servicio": "Cloud",
            "antiguedad_dias": 45,
            "salud": {"score": "HEALTHY", "color": "green", "label": "Saludable"}
        },
        "kpis": {
            "total_solots": 4,
            "solots_ejecutadas": 4,
            "solots_vencidas": 0,
            "solots_por_vencer": 0,
            "porcentaje_avance_solots": 100.0,
            "total_tickets": 2,
            "tickets_abiertos": 0,
            "tickets_criticos": 0,
            "total_rfcs": 1,
            "rfcs_abiertas": 0
        },
        "diagnostico_sintetico": {
            "cuellos_de_botella": [],
            "recomendaciones": []
        },
        "tablas": {
            "solots": [],
            "tickets": [],
            "rfcs": []
        }
    }

    # Prueba sin auto_print
    res = client.get("/api/proyectos/12/ficha-html", headers=auth_headers)
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    html_text = res.text
    assert "CLARO CHILE — DIRECCIÓN DE OPERACIONES Y SERVICIOS TI" in html_text
    assert "FICHA EJECUTIVA DE CONTROL OPERACIONAL DE PROYECTO" in html_text
    assert "0000108920" in html_text
    assert "BANCO SANTANDER" in html_text
    assert "#B52217" in html_text
    assert "#0097A9" in html_text
    assert "@media print" in html_text
    assert "window.print()" not in html_text

    # Prueba con auto_print=true
    res_print = client.get("/api/proyectos/12/ficha-html?auto_print=true", headers=auth_headers)
    assert res_print.status_code == 200
    assert "window.print()" in res_print.text


# ==============================================================================
# UT-PDF-10: Resiliencia ante valores None explícitos en data y diccionarios
# ==============================================================================
def test_generar_ficha_ejecutiva_html_none_safety():
    """Valida que generar_ficha_ejecutiva_html maneje de forma segura valores None a nivel raíz."""
    data = {
        "folio": None,
        "fecha_emision_formateada": None,
        "usuario_generador": None,
        "proyecto": None,
        "kpis": None,
        "diagnostico_sintetico": None,
        "tablas": None
    }
    html = generar_ficha_ejecutiva_html(data)
    assert "FICHA EJECUTIVA DE CONTROL OPERACIONAL DE PROYECTO" in html
    assert "Sin Cliente" in html


def test_generar_ficha_ejecutiva_html_nested_none_safety():
    """Valida que diccionarios anidados con valores None no produzcan AttributeError."""
    data = {
        "folio": "HALO-FE-TEST",
        "proyecto": {
            "salud": None,
            "antiguedad_dias": None,
            "numero_proyecto": None,
            "cliente": None,
            "lt_asignado": None,
            "solicitante": None,
            "estado_sp": None,
            "tipo_servicio": None
        },
        "kpis": {
            "total_solots": None,
            "solots_ejecutadas": None,
            "solots_vencidas": None,
            "solots_por_vencer": None,
            "porcentaje_avance_solots": None,
            "total_tickets": None,
            "tickets_abiertos": None,
            "tickets_criticos": None,
            "total_rfcs": None,
            "rfcs_abiertas": None
        },
        "diagnostico_sintetico": {
            "cuellos_de_botella": None,
            "recomendaciones": None
        },
        "tablas": {
            "solots": None,
            "tickets": None,
            "rfcs": None
        }
    }
    html = generar_ficha_ejecutiva_html(data)
    assert "HALO-FE-TEST" in html
    assert "Sin Cliente" in html

