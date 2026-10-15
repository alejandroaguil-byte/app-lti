"""
PRUEBAS UNITARIAS: CENTRO DE ALERTAS TEMPRANAS SLA & ESCALAMIENTO RÁPIDO (BACKEND)
Especificación: SPECS_ALERTAS_TEMPRANAS_SLA.md
Documento: SPECS-LTI-MOD-015
"""

import pytest
import datetime
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.db import (
    get_alertas_tempranas_sla,
    get_alertas_sla,
    procesar_alertas_sla,
    generar_minuta_escalamiento_sla
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
# UT-ALT-001: Clasificación de Ticket Crítico (>14 días abierto)
# ==============================================================================
def test_ut_alt_001_clasificacion_ticket_critico():
    hoy = datetime.date.today()
    fecha_submit = hoy - datetime.timedelta(days=15)
    raw_tickets = [
        {
            "CC_INCIDENT_ID": "SD2093878",
            "STATUS": "Abierto",
            "SUBMIT_DATE": fecha_submit.strftime("%Y-%m-%d %H:%M:%S"),
            "BRIEF_DESCRIPTION": "Upgrade de VDC // 1598268 Cliente Sirantic",
            "ASSIGNED_GROUP": "ProvisionVirtualizacionTI",
            "ASSIGNED_TO": "Sin Asignar",
            "p_id": 2035,
            "p_numero": "0001598268",
            "p_cliente": "Sirantic LTDA",
            "p_lider": "Alejandro Aguilar"
        }
    ]
    raw_solots = []

    res = procesar_alertas_sla(raw_tickets, raw_solots)
    assert res is not None
    assert res["resumen"]["criticas"] == 1
    assert res["resumen"]["tickets_sla_criticos"] == 1
    assert len(res["alertas"]) == 1

    alerta = res["alertas"][0]
    assert alerta["tipo"] == "ticket"
    assert alerta["severidad"] == "CRITICAL"
    assert alerta["badge_color"] == "red"
    assert alerta["dias_fuera_sla"] == 15
    assert "15 días abierto en torre" in alerta["detalle_sla"]
    assert alerta["proyecto_id"] == 2035
    assert alerta["cliente"] == "Sirantic LTDA"


# ==============================================================================
# UT-ALT-002: Clasificación de Ticket Advertencia (>7 y <=14 días)
# ==============================================================================
def test_ut_alt_002_clasificacion_ticket_advertencia():
    hoy = datetime.date.today()
    fecha_submit = hoy - datetime.timedelta(days=10)
    raw_tickets = [
        {
            "CC_INCIDENT_ID": "SD2093999",
            "STATUS": "Asignado a Grupo Resolutor",
            "SUBMIT_DATE": fecha_submit.strftime("%Y-%m-%d %H:%M:%S"),
            "BRIEF_DESCRIPTION": "Configuración Switch B2B",
            "ASSIGNED_GROUP": "Torre Redes",
            "ASSIGNED_TO": "Juan Perez",
            "p_id": 2050,
            "p_numero": "0001599000",
            "p_cliente": "Entel Corp",
            "p_lider": "Erwin Sandoval"
        }
    ]
    raw_solots = []

    res = procesar_alertas_sla(raw_tickets, raw_solots)
    assert res["resumen"]["advertencias"] == 1
    assert res["resumen"]["tickets_sla_advertencia"] == 1
    assert res["resumen"]["criticas"] == 0

    alerta = res["alertas"][0]
    assert alerta["severidad"] == "WARNING"
    assert alerta["badge_color"] == "amber"
    assert alerta["dias_fuera_sla"] == 10
    assert "10 días en atención" in alerta["detalle_sla"]


# ==============================================================================
# UT-ALT-003: Exclusión de Tickets Cerrados / Resueltos
# ==============================================================================
def test_ut_alt_003_exclusion_tickets_cerrados():
    hoy = datetime.date.today()
    fecha_submit = hoy - datetime.timedelta(days=60)
    raw_tickets = [
        {
            "CC_INCIDENT_ID": "SD1001",
            "STATUS": "Cerrado",
            "SUBMIT_DATE": fecha_submit.strftime("%Y-%m-%d %H:%M:%S"),
            "BRIEF_DESCRIPTION": "Ticket histórico cerrado"
        },
        {
            "CC_INCIDENT_ID": "SD1002",
            "STATUS": "Resuelto",
            "SUBMIT_DATE": fecha_submit.strftime("%Y-%m-%d %H:%M:%S"),
            "BRIEF_DESCRIPTION": "Ticket histórico resuelto"
        },
        {
            "CC_INCIDENT_ID": "SD1003",
            "STATUS": "Closed",
            "SUBMIT_DATE": fecha_submit.strftime("%Y-%m-%d %H:%M:%S"),
            "BRIEF_DESCRIPTION": "Ticket cerrado en inglés"
        },
        {
            "CC_INCIDENT_ID": "SD1004",
            "STATUS": "Resolved",
            "SUBMIT_DATE": fecha_submit.strftime("%Y-%m-%d %H:%M:%S"),
            "BRIEF_DESCRIPTION": "Ticket resuelto en inglés"
        }
    ]
    raw_solots = []

    res = procesar_alertas_sla(raw_tickets, raw_solots)
    assert res["resumen"]["total_alertas"] == 0
    assert len(res["alertas"]) == 0


# ==============================================================================
# UT-ALT-004: Clasificación de Solot Vencida (FECHA_COMPROMETIDA < hoy)
# ==============================================================================
def test_ut_alt_004_clasificacion_solot_vencida():
    hoy = datetime.date.today()
    fecha_comp = hoy - datetime.timedelta(days=20)
    raw_tickets = []
    raw_solots = [
        {
            "ID_OTP": 17522296,
            "ESTADO_OTP": "4- Revision",
            "FECHA_COMPROMETIDA": fecha_comp.strftime("%Y-%m-%d"),
            "FECHA_INSERT": (hoy - datetime.timedelta(days=35)).strftime("%Y-%m-%d %H:%M:%S"),
            "DESCR_OTP": "Instalacion | Paquete 23.000 minutos",
            "GRUPO_ASIGNADO_OTP": "Instalaciones",
            "ASIGNADO_OTP": "MICHAEL PEREZ",
            "p_id": 1954,
            "p_numero": "1594831",
            "p_cliente": "SOC DE RENTAS INMOBILIARIAS",
            "p_lider": "Alejandro Aguilar"
        }
    ]

    res = procesar_alertas_sla(raw_tickets, raw_solots)
    assert res["resumen"]["criticas"] == 1
    assert res["resumen"]["solots_vencidas"] == 1

    alerta = res["alertas"][0]
    assert alerta["tipo"] == "solot"
    assert alerta["severidad"] == "CRITICAL"
    assert alerta["badge_color"] == "red"
    assert alerta["dias_fuera_sla"] == 20
    assert "Vencida hace 20 días" in alerta["detalle_sla"]
    assert alerta["responsable_tipo"] == "Área SGA"


# ==============================================================================
# UT-ALT-005: Clasificación de Solot por Vencer (<= 48h)
# ==============================================================================
def test_ut_alt_005_clasificacion_solot_proxima_vencer():
    hoy = datetime.date.today()
    fecha_comp = hoy + datetime.timedelta(days=1)
    raw_tickets = []
    raw_solots = [
        {
            "ID_OTP": 17523000,
            "ESTADO_OTP": "2- En ejecucion",
            "FECHA_COMPROMETIDA": fecha_comp.strftime("%Y-%m-%d"),
            "FECHA_INSERT": (hoy - datetime.timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"),
            "DESCR_OTP": "Alta enlace FO 100M",
            "GRUPO_ASIGNADO_OTP": "Fibra Optica",
            "ASIGNADO_OTP": "Carlos Gomez",
            "p_id": 1960,
            "p_lider": "Juan Barrera"
        }
    ]

    res = procesar_alertas_sla(raw_tickets, raw_solots)
    assert res["resumen"]["advertencias"] == 1
    assert res["resumen"]["solots_proximas_vencer"] == 1
    assert res["resumen"]["criticas"] == 0

    alerta = res["alertas"][0]
    assert alerta["severidad"] == "WARNING"
    assert alerta["badge_color"] == "amber"
    assert "Vence mañana" in alerta["detalle_sla"] or "Próxima a vencer" in alerta["detalle_sla"]


# ==============================================================================
# UT-ALT-006: Solot Estancada sin Compromiso tras >10 días
# ==============================================================================
def test_ut_alt_006_solot_sin_compromiso_estancada():
    hoy = datetime.date.today()
    fecha_insert = hoy - datetime.timedelta(days=15)
    raw_tickets = []
    raw_solots = [
        {
            "ID_OTP": 17524000,
            "ESTADO_OTP": "1- Asignada",
            "FECHA_COMPROMETIDA": None,
            "FECHA_INSERT": fecha_insert.strftime("%Y-%m-%d %H:%M:%S"),
            "DESCR_OTP": "Orden sin fecha",
            "GRUPO_ASIGNADO_OTP": "Provision",
            "ASIGNADO_OTP": "Sin Asignar",
            "p_id": 1970,
            "p_lider": "Samuel Paredes"
        }
    ]

    res = procesar_alertas_sla(raw_tickets, raw_solots)
    assert res["resumen"]["advertencias"] == 1
    assert res["resumen"]["solots_sin_compromiso"] == 1

    alerta = res["alertas"][0]
    assert alerta["severidad"] == "WARNING"
    assert "Sin compromiso pactado tras 15 días" in alerta["detalle_sla"]


# ==============================================================================
# UT-ALT-007: Endpoint No Autenticado (401 Unauthorized)
# ==============================================================================
def test_ut_alt_007_endpoint_no_autenticado():
    res = client.get("/api/alertas/sla")
    assert res.status_code == 401


# ==============================================================================
# UT-ALT-008: Endpoint Autenticado con Rol LTI/ADMIN (200 OK)
# ==============================================================================
def test_ut_alt_008_endpoint_autenticado(lti_headers):
    res = client.get("/api/alertas/sla?limite=10", headers=lti_headers)
    assert res.status_code == 200
    data = res.json()
    assert "timestamp" in data
    assert "filtros_aplicados" in data
    assert "resumen" in data
    assert "alertas" in data
    assert "minuta_escalamiento" in data

    resumen = data["resumen"]
    for k in ["total_alertas", "criticas", "advertencias", "tickets_sla_criticos", "solots_vencidas", "proyectos_criticos"]:
        assert k in resumen


# ==============================================================================
# UT-ALT-009: Filtro por Líder TI
# ==============================================================================
def test_ut_alt_009_filtro_por_lider_ti(auth_headers):
    lider = "Alejandro Aguilar"
    res = client.get(f"/api/alertas/sla?lider={lider}&limite=20", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    for alerta in data["alertas"]:
        if alerta.get("lt_asignado") and alerta.get("lt_asignado") != "Sin Asignar":
            assert "alejandro" in alerta["lt_asignado"].lower() or "aguilar" in alerta["lt_asignado"].lower()


# ==============================================================================
# UT-ALT-010: Generación de Minuta de Escalamiento
# ==============================================================================
def test_ut_alt_010_generacion_minuta_escalamiento():
    resumen = {
        "total_alertas": 15,
        "criticas": 10,
        "advertencias": 5,
        "tickets_sla_criticos": 6,
        "tickets_sla_advertencia": 2,
        "solots_vencidas": 4,
        "solots_proximas_vencer": 2,
        "solots_sin_compromiso": 1,
        "proyectos_criticos": 3
    }
    alertas = [
        {
            "id": "TICKET-SD1234",
            "tipo": "ticket",
            "severidad": "CRITICAL",
            "titulo": "SD1234",
            "subtitulo": "Falla Core B2B",
            "numero_proyecto": "000123",
            "cliente": "Banco Chile",
            "lt_asignado": "Alejandro Aguilar",
            "responsable": "Torre Linux",
            "asignado_a": "Juan",
            "detalle_sla": "25 días abierto"
        }
    ]

    minuta = generar_minuta_escalamiento_sla(resumen, alertas)
    assert "asunto_sugerido" in minuta
    assert "texto_plano" in minuta
    assert "destinatarios_sugeridos" in minuta
    assert "[HALO ESCALAMIENTO]" in minuta["asunto_sugerido"]
    assert "CLARO HALO — MINUTA EJECUTIVA DE ESCALAMIENTO OPERACIONAL" in minuta["texto_plano"]
    assert "Total Alertas SLA: 15" in minuta["texto_plano"]
    assert "Alertas Críticas (🔴): 10" in minuta["texto_plano"]
    assert "SD1234 - Falla Core B2B" in minuta["texto_plano"]
    assert len(minuta["destinatarios_sugeridos"]) >= 2


# ==============================================================================
# S16: Agrupación de alertas por proyecto (contrato aditivo de procesar_alertas_sla)
# ==============================================================================
def _fecha_hace(dias):
    return (datetime.date.today() - datetime.timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")


def _ticket(inc, dias, pid, lider="Alejandro Aguilar", cliente="Cliente A", numero="0001"):
    return {
        "CC_INCIDENT_ID": inc,
        "STATUS": "Abierto",
        "SUBMIT_DATE": _fecha_hace(dias),
        "BRIEF_DESCRIPTION": f"Ticket {inc}",
        "p_id": pid,
        "p_numero": numero,
        "p_cliente": cliente,
        "p_lider": lider,
    }


def _solot(otp, dias_vencida, pid, lider="Alejandro Aguilar", cliente="Cliente A", numero="0001"):
    return {
        "ID_OTP": otp,
        "ESTADO_OTP": "4- Revision",
        "FECHA_COMPROMETIDA": _fecha_hace(dias_vencida),
        "FECHA_INSERT": _fecha_hace(dias_vencida + 10),
        "DESCR_OTP": f"Solot {otp}",
        "p_id": pid,
        "p_numero": numero,
        "p_cliente": cliente,
        "p_lider": lider,
    }


def _escenario_proyectos():
    """Proyecto 100: 2 solots críticas + 1 ticket crítico + 1 ticket warning.
    Proyecto 200: solo 1 ticket warning. Proyecto 300: 1 solot crítica (LT distinto).
    Dos alertas sin proyecto (una crítica, una warning)."""
    raw_tickets = [
        _ticket("T-100-C", 20, 100, cliente="Cliente A", numero="0100"),
        _ticket("T-100-W", 9, 100, cliente="Cliente A", numero="0100"),
        _ticket("T-200-W", 12, 200, lider="Erwin Sandoval", cliente="Cliente B", numero="0200"),
        _ticket("T-NOPROY-C", 30, None),
    ]
    raw_solots = [
        _solot(1001, 40, 100, cliente="Cliente A", numero="0100"),
        _solot(1002, 5, 100, cliente="Cliente A", numero="0100"),
        _solot(3001, 25, 300, lider="Erwin Sandoval", cliente="Cliente C", numero="0300"),
        {
            "ID_OTP": 9999,
            "ESTADO_OTP": "1- Asignada",
            "FECHA_COMPROMETIDA": None,
            "FECHA_INSERT": _fecha_hace(15),
            "DESCR_OTP": "Sin proyecto",
            "p_lider": "Alejandro Aguilar",
        },
    ]
    return raw_tickets, raw_solots


def test_ut_alt_011_proyectos_agrupa_conteos_y_peor_severidad():
    raw_tickets, raw_solots = _escenario_proyectos()
    res = procesar_alertas_sla(raw_tickets, raw_solots)

    assert "proyectos" in res
    por_id = {p["proyecto_id"]: p for p in res["proyectos"]}
    assert set(por_id) == {100, 200, 300}

    p100 = por_id[100]
    assert p100["numero_proyecto"] == "0100"
    assert p100["cliente"] == "Cliente A"
    assert p100["lt_asignado"] == "Alejandro Aguilar"
    assert p100["severidad"] == "CRITICAL"
    assert p100["total_alertas"] == 4
    assert p100["criticas"] == 3
    assert p100["advertencias"] == 1
    assert p100["solots"] == 2
    assert p100["tickets"] == 2
    assert p100["max_dias_fuera_sla"] == 40

    p200 = por_id[200]
    assert p200["severidad"] == "WARNING"
    assert p200["criticas"] == 0
    assert p200["advertencias"] == 1
    assert p200["tickets"] == 1
    assert p200["solots"] == 0
    assert p200["max_dias_fuera_sla"] == 12


def test_ut_alt_012_alertas_sin_proyecto_excluidas_y_contadas():
    raw_tickets, raw_solots = _escenario_proyectos()
    res = procesar_alertas_sla(raw_tickets, raw_solots)

    ids_en_proyectos = {a["id"] for p in res["proyectos"] for a in p["alertas"]}
    assert "TICKET-T-NOPROY-C" not in ids_en_proyectos
    assert "SOLOT-9999" not in ids_en_proyectos
    assert sum(p["total_alertas"] for p in res["proyectos"]) == res["resumen"]["total_alertas"] - 2
    assert res["resumen"]["alertas_sin_proyecto"] == 2


def test_ut_alt_013_proyectos_independientes_de_limite_severidad_y_tipo():
    raw_tickets, raw_solots = _escenario_proyectos()
    base = procesar_alertas_sla(raw_tickets, raw_solots)
    filtrado = procesar_alertas_sla(raw_tickets, raw_solots, severidad="advertencia", tipo="ticket", limite=1)

    assert len(filtrado["alertas"]) == 1
    assert filtrado["proyectos"] == base["proyectos"]
    assert filtrado["resumen"]["proyectos_con_alertas"] == base["resumen"]["proyectos_con_alertas"]
    assert filtrado["resumen"]["alertas_sin_proyecto"] == base["resumen"]["alertas_sin_proyecto"]


def test_ut_alt_014_proyectos_respetan_filtro_lider():
    raw_tickets, raw_solots = _escenario_proyectos()
    res = procesar_alertas_sla(raw_tickets, raw_solots, lider="Erwin Sandoval")

    assert {p["proyecto_id"] for p in res["proyectos"]} == {200, 300}
    assert res["resumen"]["proyectos_con_alertas"] == 2
    assert res["resumen"]["alertas_sin_proyecto"] == 0


def test_ut_alt_015_alertas_por_proyecto_top5_en_orden_canonico():
    raw_tickets = []
    raw_solots = [_solot(2000 + i, 10 + i, 500, numero="0500") for i in range(7)]
    raw_tickets.append(_ticket("T-500-W", 9, 500, numero="0500"))

    res = procesar_alertas_sla(raw_tickets, raw_solots)
    assert len(res["proyectos"]) == 1
    p = res["proyectos"][0]
    assert p["total_alertas"] == 8
    assert len(p["alertas"]) == 5
    # Orden canónico: severidad, días fuera de SLA desc, id desc
    assert [a["dias_fuera_sla"] for a in p["alertas"]] == [16, 15, 14, 13, 12]
    assert all(a["severidad"] == "CRITICAL" for a in p["alertas"])
    assert p["max_dias_fuera_sla"] == 16


def test_ut_alt_016_orden_de_proyectos():
    raw_tickets = [
        _ticket("T-A-W", 13, 10),      # WARNING, 13d
        _ticket("T-B-W", 9, 20),       # WARNING, 9d
        _ticket("T-C-C", 16, 30),      # CRITICAL x1, 16d
        _ticket("T-D-C", 30, 40),      # CRITICAL x1, 30d
        _ticket("T-E-C", 15, 50),      # CRITICAL x1, 15d (+ otra crítica => 2 críticas)
        _ticket("T-E2-C", 15, 50),
        _ticket("T-F-C", 30, 35),      # CRITICAL x1, 30d, empata con 40 => proyecto_id asc
        _ticket("T-G-W", 13, 5),       # WARNING, 13d, empata con 10 => proyecto_id asc
    ]
    res = procesar_alertas_sla(raw_tickets, [])
    orden = [p["proyecto_id"] for p in res["proyectos"]]
    # críticos primero (más críticas, luego mayor atraso, luego id), luego advertencias
    assert orden == [50, 35, 40, 30, 5, 10, 20]


def test_ut_alt_017_resumen_contadores_de_proyectos():
    raw_tickets, raw_solots = _escenario_proyectos()
    res = procesar_alertas_sla(raw_tickets, raw_solots)
    r = res["resumen"]
    assert r["proyectos_con_alertas"] == 3
    assert r["proyectos_alerta_criticos"] == 2      # 100 y 300
    assert r["proyectos_alerta_advertencia"] == 1   # 200
    assert r["alertas_sin_proyecto"] == 2


def test_ut_alt_018_resumen_existente_no_cambia_y_sin_alertas():
    raw_tickets, raw_solots = _escenario_proyectos()
    r = procesar_alertas_sla(raw_tickets, raw_solots)["resumen"]
    assert r["total_alertas"] == 8
    assert r["criticas"] == 5
    assert r["advertencias"] == 3
    assert r["tickets_sla_criticos"] == 2
    assert r["tickets_sla_advertencia"] == 2
    assert r["solots_vencidas"] == 3
    assert r["solots_proximas_vencer"] == 0
    assert r["solots_sin_compromiso"] == 1
    assert r["proyectos_criticos"] == 1

    vacio = procesar_alertas_sla([], [])
    assert vacio["proyectos"] == []
    assert vacio["resumen"]["proyectos_con_alertas"] == 0
    assert vacio["resumen"]["alertas_sin_proyecto"] == 0
