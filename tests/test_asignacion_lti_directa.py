"""
Direct LTI assignment (odd/tasks/asignacion-lti-directa.md).

S1/S2: authorized assigners (alejandro.aguilar, pablo.castillo) get an effective role of
at least LTI regardless of their App/Portal role.
S3: POST /api/backlog/asignar-lti creates the project in dbo.Proyectos or updates only its LTI.

The test database is shared with production: every DB access here is mocked.
"""

import pytest
from fastapi.testclient import TestClient

import backend.auth as auth_module
import backend.main as main_module
from backend.main import app
from tests.conftest import create_portal_jwt

client = TestClient(app)


def _app_user(username, rol="PM", activo=1, lt_asignado=None):
    return {
        "id": 900,
        "username": username,
        "nombre_completo": username.replace(".", " ").title(),
        "email": f"{username}@clarovtr.cl",
        "rol": rol,
        "lt_asignado": lt_asignado,
        "activo": activo,
    }


@pytest.fixture
def app_user(monkeypatch):
    """Replaces the JIT user lookup so no test touches App_Usuarios."""
    state = {}

    def fake_jit(username, nombre_completo=None, default_rol="PM", email=None):
        return state.get(username, _app_user(username, rol=default_rol))

    monkeypatch.setattr(auth_module, "get_or_create_jit_user", fake_jit)
    return state


def _me(username, tool_perm="operador", admin_level=0):
    token = create_portal_jwt(
        username=username,
        admin_level=admin_level,
        tool_access={"app-lti": tool_perm} if tool_perm else {},
    )
    return client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})


# ---------------------------------------------------------------------------
# S1 — role floor
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("username", ["alejandro.aguilar", "pablo.castillo"])
def test_s1_assigner_with_pm_role_gets_lti(app_user, username):
    app_user[username] = _app_user(username, rol="PM")
    res = _me(username, tool_perm="operador")
    assert res.status_code == 200, res.text
    assert res.json()["rol"] == "LTI"


@pytest.mark.parametrize("username", ["alejandro.aguilar", "pablo.castillo"])
def test_s1_assigner_downgraded_by_portal_lectura_gets_lti(app_user, username):
    app_user[username] = _app_user(username, rol="ADMIN")
    res = _me(username, tool_perm="lectura")
    assert res.status_code == 200, res.text
    assert res.json()["rol"] == "LTI"
    assert res.json()["portal_access"] == "lectura"


def test_s1_assigner_username_is_case_insensitive(app_user):
    app_user["pablo.castillo"] = _app_user("pablo.castillo", rol="PM")
    res = _me("Pablo.Castillo", tool_perm="lectura")
    assert res.status_code == 200, res.text
    assert res.json()["username"] == "pablo.castillo"
    assert res.json()["rol"] == "LTI"


def test_s1_assigner_admin_stays_admin(app_user):
    app_user["alejandro.aguilar"] = _app_user("alejandro.aguilar", rol="ADMIN")
    res = _me("alejandro.aguilar", tool_perm="operador")
    assert res.status_code == 200, res.text
    assert res.json()["rol"] == "ADMIN"


def test_s1_other_user_lectura_still_pm(app_user):
    app_user["juan.perez"] = _app_user("juan.perez", rol="LTI")
    res = _me("juan.perez", tool_perm="lectura")
    assert res.status_code == 200, res.text
    assert res.json()["rol"] == "PM"


def test_s1_other_user_pm_role_still_pm(app_user):
    app_user["juan.perez"] = _app_user("juan.perez", rol="PM")
    res = _me("juan.perez", tool_perm="operador")
    assert res.status_code == 200, res.text
    assert res.json()["rol"] == "PM"


def test_s1_other_user_lti_role_still_lti(app_user):
    app_user["juan.perez"] = _app_user("juan.perez", rol="LTI")
    res = _me("juan.perez", tool_perm="operador")
    assert res.status_code == 200, res.text
    assert res.json()["rol"] == "LTI"


def test_s1_assigner_without_portal_permission_still_403(app_user):
    app_user["pablo.castillo"] = _app_user("pablo.castillo", rol="ADMIN")
    res = _me("pablo.castillo", tool_perm=None)
    assert res.status_code == 403
    assert res.json()["detail"] == "No tienes permisos asignados para acceder a App LTI en el Portal de Acceso"


def test_s1_assigner_deactivated_still_403(app_user):
    app_user["pablo.castillo"] = _app_user("pablo.castillo", rol="ADMIN", activo=0)
    res = _me("pablo.castillo", tool_perm="operador")
    assert res.status_code == 403
    assert res.json()["detail"] == "Usuario desactivado en App LTI"


# ---------------------------------------------------------------------------
# S2 — assigners can use the existing Editar flow even with PM role
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_update(monkeypatch):
    calls = []

    def fake_update_proyecto(**kwargs):
        calls.append(kwargs)
        return {
            "success": True,
            "data": {"ID": kwargs["proyecto_id"], "LT_Asignado": kwargs["lt_asignado"]},
            "was_assigned": False,
        }

    monkeypatch.setattr(main_module, "update_proyecto", fake_update_proyecto)
    return calls


_EDIT_BODY = {
    "cliente": "Cliente QA",
    "lt_asignado": "Juan Barrera",
    "estado": "Generado",
    "detalle": "Detalle QA",
}


def test_s2_assigner_with_pm_role_can_assign_via_edit(app_user, fake_update):
    app_user["pablo.castillo"] = _app_user("pablo.castillo", rol="PM")
    token = create_portal_jwt(username="pablo.castillo", admin_level=0, tool_access={"app-lti": "lectura"})
    res = client.put("/api/proyectos/123", json=_EDIT_BODY, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.text
    assert len(fake_update) == 1
    assert fake_update[0]["lt_asignado"] == "Juan Barrera"


def test_s2_regular_pm_still_cannot_edit(app_user, fake_update):
    app_user["juan.perez"] = _app_user("juan.perez", rol="PM")
    token = create_portal_jwt(username="juan.perez", admin_level=0, tool_access={"app-lti": "operador"})
    res = client.put("/api/proyectos/123", json=_EDIT_BODY, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert fake_update == []
