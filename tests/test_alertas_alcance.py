"""
Alert scope (odd/tasks/fixes-proyectos-alertas.md, T4: S5).

- Scope: a full-visibility user WITH lt_asignado sees only the alerts of their own projects (an explicit `lider`
  query param is still honored); a full-visibility user WITHOUT lt_asignado keeps seeing everything; every other
  user is unchanged (forced to their own LTI, no LTI -> empty).

The test database is production: all data access here is simulated (fake connections).
"""

import pytest
from fastapi.testclient import TestClient

import backend.auth as auth_module
import backend.main as main_module
from backend.main import app
from tests.conftest import create_portal_jwt

client = TestClient(app)

# ---------------------------------------------------------------------------
# Scope: GET /api/alertas/sla
# ---------------------------------------------------------------------------

USERS = {
    "alejandro.aguilar": ("ADMIN", "Alejandro Aguilar"),
    "pablo.castillo": ("LTI", None),
    "juan.perez": ("LTI", "Juan Barrera"),
    "sin.lt": ("LTI", None),
}


@pytest.fixture
def alertas_env(monkeypatch):
    def fake_jit(username, nombre_completo=None, default_rol="PM", email=None):
        rol, lt = USERS.get(username, ("PM", None))
        return {"id": 900, "username": username, "nombre_completo": username.title(),
                "email": f"{username}@clarovtr.cl", "rol": rol, "lt_asignado": lt, "activo": 1}

    monkeypatch.setattr(auth_module, "get_or_create_jit_user", fake_jit)
    llamadas = []

    def fake_alertas(**kwargs):
        llamadas.append(kwargs)
        return {"alertas": []}

    monkeypatch.setattr(main_module, "get_alertas_tempranas_sla", fake_alertas)
    return llamadas


def _h(username):
    token = create_portal_jwt(username=username, admin_level=0, tool_access={"app-lti": "operador"})
    return {"Authorization": f"Bearer {token}"}


def test_s5_alcance_visibilidad_total_con_lti_ve_solo_sus_proyectos(alertas_env):
    res = client.get("/api/alertas/sla", headers=_h("alejandro.aguilar"))
    assert res.status_code == 200
    assert alertas_env[0]["lider"] == "Alejandro Aguilar"


def test_s5_alcance_visibilidad_total_con_lti_respeta_el_parametro_lider_explicito(alertas_env):
    client.get("/api/alertas/sla", params={"lider": "Erwin Sandoval"}, headers=_h("alejandro.aguilar"))
    assert alertas_env[0]["lider"] == "Erwin Sandoval"


def test_s5_alcance_visibilidad_total_con_lti_puede_pedir_todos_explicitamente(alertas_env):
    client.get("/api/alertas/sla", params={"lider": "todos"}, headers=_h("alejandro.aguilar"))
    assert alertas_env[0]["lider"] == "todos"


def test_s5_alcance_visibilidad_total_sin_lti_sigue_viendo_todo(alertas_env):
    client.get("/api/alertas/sla", headers=_h("pablo.castillo"))
    client.get("/api/alertas/sla", params={"lider": "Erwin Sandoval"}, headers=_h("pablo.castillo"))
    assert alertas_env[0]["lider"] is None
    assert alertas_env[1]["lider"] == "Erwin Sandoval"


@pytest.mark.parametrize("param", [None, "Erwin Sandoval", "todos"])
def test_s5_alcance_usuario_restringido_sigue_forzado_a_su_lti(alertas_env, param):
    params = {"lider": param} if param else {}
    res = client.get("/api/alertas/sla", params=params, headers=_h("juan.perez"))
    assert res.status_code == 200
    assert alertas_env[0]["lider"] == "Juan Barrera"


def test_s5_alcance_restringido_sin_lti_devuelve_vacio_sin_consultar_la_bd(alertas_env):
    res = client.get("/api/alertas/sla", headers=_h("sin.lt"))
    assert res.status_code == 200
    assert alertas_env == []
    assert res.json()["alertas"] == []
    assert res.json()["resumen"]["proyectos_con_alertas"] == 0


def test_s5_alcance_se_mantienen_los_filtros_de_severidad_tipo_y_limite(alertas_env):
    client.get("/api/alertas/sla", params={"severidad": "advertencia", "tipo": "proyecto", "limite": 7},
               headers=_h("alejandro.aguilar"))
    llamada = alertas_env[0]
    assert (llamada["severidad"], llamada["tipo"], llamada["limite"]) == ("advertencia", "proyecto", 7)
