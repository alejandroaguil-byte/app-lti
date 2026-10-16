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


# ---------------------------------------------------------------------------
# S3 — POST /api/backlog/asignar-lti
# ---------------------------------------------------------------------------

import time

import backend.db as db_module

_BACKLOG_ROW = {
    "NRO_PROYECTO": "QA-777",
    "Numero_Proyecto_Limpio": "QA-777",
    "CLI_CLIENTE": "CLIENTE QA BACKLOG",
    "PRO_ING_PROYECTO": "Corp1- Juan Pm",
}


@pytest.fixture
def backlog(monkeypatch):
    """Mocks every data-access helper used by the backlog assignment."""
    state = {
        "backlog_row": dict(_BACKLOG_ROW),
        "existing": None,
        "create_result": None,
        "creates": [],
        "updates": [],
        "notifications": [],
    }

    def fake_get_backlog(numero):
        state["backlog_lookup"] = numero
        return state["backlog_row"]

    def fake_check(numero):
        return state["existing"]

    def fake_create(**kwargs):
        state["creates"].append(kwargs)
        if state["create_result"] is not None:
            return state["create_result"]
        return {"success": True, "data": {"ID": 901, "Numero_Proyecto": "000QA-777", **{
            "Cliente": kwargs["cliente"], "LT_Asignado": kwargs["lt_asignado"],
            "Solicitante": kwargs["solicitante"], "Estado": kwargs["estado"]}}}

    def fake_update_lt(proyecto_id, lt_asignado):
        state["updates"].append((proyecto_id, lt_asignado))
        return {"ID": proyecto_id, "LT_Asignado": lt_asignado}

    def fake_notify(**kwargs):
        state["notifications"].append(kwargs)

    monkeypatch.setattr(db_module, "get_backlog_proyecto", fake_get_backlog, raising=False)
    monkeypatch.setattr(db_module, "check_proyecto_exists", fake_check)
    monkeypatch.setattr(db_module, "create_solicitud_lti", fake_create)
    monkeypatch.setattr(db_module, "update_proyecto_lt", fake_update_lt, raising=False)
    monkeypatch.setattr(main_module, "notificar_asignacion_lti_bg", fake_notify)
    return state


def _assign(body, username="alejandro.aguilar", tool_perm="operador", admin_level=2):
    token = create_portal_jwt(username=username, admin_level=admin_level, tool_access={"app-lti": tool_perm})
    return client.post("/api/backlog/asignar-lti", json=body, headers={"Authorization": f"Bearer {token}"})


def _assert_nothing_written(state):
    assert state["creates"] == []
    assert state["updates"] == []
    assert state["notifications"] == []


def test_s3_creates_project_when_missing(app_user, backlog):
    res = _assign({"numero_proyecto": "QA-777", "lt_asignado": "Juan Barrera"})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["action"] == "created"
    assert body["message"] == "Proyecto creado y LTI asignado"
    assert body["data"]["LT_Asignado"] == "Juan Barrera"
    assert len(backlog["creates"]) == 1
    created = backlog["creates"][0]
    assert created["cliente"] == "CLIENTE QA BACKLOG"
    assert created["numero_proyecto"] == "QA-777"
    assert created["lt_asignado"] == "Juan Barrera"
    assert created["estado"] == "En ejecucion"
    assert created["tipo_servicio"] == "Otros"
    assert created["detalle"] == "Asignado directamente desde el backlog de operaciones SGA."
    assert created["solicitante"] == "JUAN PM"
    assert backlog["updates"] == []
    assert len(backlog["notifications"]) == 1
    assert backlog["notifications"][0]["new_lt"] == "Juan Barrera"
    assert backlog["notifications"][0]["prev_lt"] is None


def test_s3_created_solicitante_falls_back_to_actor(app_user, backlog):
    app_user["alejandro.aguilar"] = _app_user("alejandro.aguilar", rol="ADMIN")
    backlog["backlog_row"]["PRO_ING_PROYECTO"] = None
    res = _assign({"numero_proyecto": "QA-777", "lt_asignado": "Juan Barrera"})
    assert res.status_code == 201, res.text
    assert backlog["creates"][0]["solicitante"] == "Alejandro Aguilar"


def test_s3_updates_only_lt_when_project_exists_unassigned(app_user, backlog):
    backlog["existing"] = {"ID": 55, "Numero_Proyecto": "000QA-777", "LT_Asignado": None, "Cliente": "OTRO"}
    res = _assign({"numero_proyecto": "QA-777", "lt_asignado": "Solange Ortiz"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["action"] == "updated"
    assert body["message"] == "LTI asignado al proyecto"
    assert backlog["updates"] == [(55, "Solange Ortiz")]
    assert backlog["creates"] == []
    assert len(backlog["notifications"]) == 1
    assert backlog["notifications"][0]["new_lt"] == "Solange Ortiz"


def test_s3_reassign_existing_lt_does_not_notify(app_user, backlog):
    backlog["existing"] = {"ID": 55, "Numero_Proyecto": "000QA-777", "LT_Asignado": "Erwin Sandoval"}
    res = _assign({"numero_proyecto": "QA-777", "lt_asignado": "Solange Ortiz"})
    assert res.status_code == 200, res.text
    assert backlog["updates"] == [(55, "Solange Ortiz")]
    assert backlog["notifications"] == []


def test_s3_duplicate_race_falls_back_to_update(app_user, backlog):
    backlog["create_result"] = {
        "success": False, "error": "duplicate",
        "existing": {"ID": 77, "Numero_Proyecto": "000QA-777", "LT_Asignado": None},
    }
    res = _assign({"numero_proyecto": "QA-777", "lt_asignado": "Juan Barrera"})
    assert res.status_code == 200, res.text
    assert res.json()["action"] == "updated"
    assert backlog["updates"] == [(77, "Juan Barrera")]
    assert len(backlog["notifications"]) == 1


def test_s3_invalid_lider_is_400(app_user, backlog):
    res = _assign({"numero_proyecto": "QA-777", "lt_asignado": "Fulano De Tal"})
    assert res.status_code == 400
    assert res.json()["detail"] == (
        "Líder TI inválido. Los líderes permitidos son: "
        "Alejandro Aguilar, Erwin Sandoval, Juan Barrera, Samuel Paredes, Solange Ortiz"
    )
    _assert_nothing_written(backlog)


@pytest.mark.parametrize("lt", ["", "   ", None])
def test_s3_missing_lider_is_400(app_user, backlog, lt):
    res = _assign({"numero_proyecto": "QA-777", "lt_asignado": lt})
    assert res.status_code == 400
    assert res.json()["detail"].startswith("Líder TI inválido.")
    _assert_nothing_written(backlog)


@pytest.mark.parametrize("numero", ["", "   ", "0", "000", " 0000 "])
def test_s3_empty_project_number_is_400(app_user, backlog, numero):
    res = _assign({"numero_proyecto": numero, "lt_asignado": "Juan Barrera"})
    assert res.status_code == 400
    assert res.json()["detail"] == "Debe indicar el N° de proyecto"
    _assert_nothing_written(backlog)


def test_s3_project_not_in_backlog_is_404(app_user, backlog):
    backlog["backlog_row"] = None
    res = _assign({"numero_proyecto": "QA-404", "lt_asignado": "Juan Barrera"})
    assert res.status_code == 404
    assert res.json()["detail"] == "El proyecto no existe en el backlog de operaciones"
    _assert_nothing_written(backlog)


def test_s3_regular_pm_is_403(app_user, backlog):
    app_user["juan.perez"] = _app_user("juan.perez", rol="PM")
    res = _assign({"numero_proyecto": "QA-777", "lt_asignado": "Juan Barrera"},
                  username="juan.perez", tool_perm="lectura", admin_level=0)
    assert res.status_code == 403
    _assert_nothing_written(backlog)


def test_s3_assigner_with_pm_role_can_assign(app_user, backlog):
    app_user["pablo.castillo"] = _app_user("pablo.castillo", rol="PM")
    res = _assign({"numero_proyecto": "QA-777", "lt_asignado": "Juan Barrera"},
                  username="pablo.castillo", tool_perm="lectura", admin_level=0)
    assert res.status_code == 201, res.text


# Data-access helpers against the shared database: QA numbers only (cleaned by conftest).

def test_s3_get_backlog_proyecto_unknown_number_is_none():
    assert db_module.get_backlog_proyecto(f"QA-NO-EXISTE-{int(time.time())}") is None


def test_s3_update_proyecto_lt_changes_only_lt_and_estado(monkeypatch):
    """Mocked connection (the shared DB is production): only LT_Asignado and the Generado -> En ejecucion step are written."""
    executed = []

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            executed.append((" ".join(sql.split()), params))

    class _Conn:
        commits = 0

        def cursor(self):
            return _Cursor()

        def commit(self):
            _Conn.commits += 1

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(db_module, "get_db_connection", lambda: _Conn())
    monkeypatch.setattr(db_module, "get_proyecto_by_id", lambda pid: {"ID": pid, "LT_Asignado": "Juan Barrera"})

    updated = db_module.update_proyecto_lt(55, "Juan Barrera")

    assert updated["LT_Asignado"] == "Juan Barrera"
    assert executed == [(
        "UPDATE dbo.Proyectos SET LT_Asignado = %s, "
        "Estado = CASE WHEN Estado = 'Generado' THEN 'En ejecucion' ELSE Estado END WHERE ID = %s",
        ("Juan Barrera", 55),
    )]
    assert _Conn.commits == 1
