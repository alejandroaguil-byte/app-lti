"""
PRUEBAS DE SEGURIDAD: MONITOR DE 6 HORAS EN AMBIENTES CON EMAIL_REDIRECT_TO
Especificación: odd/tasks/test-safety-dev-email.md (S6)

Desarrollo y producción comparten la base de datos. Un servidor con EMAIL_REDIRECT_TO no debe
consumir recordatorios (marcarlos en BD), o producción dejaría de enviarlos a los coordinadores.

- CP-REM-01: Con EMAIL_REDIRECT_TO, un ciclo del monitor no envía ni marca recordatorios.
- CP-REM-02: Sin EMAIL_REDIRECT_TO, un ciclo del monitor envía y marca los recordatorios válidos.
- CP-REM-03: Con EMAIL_REDIRECT_TO, el chequeo manual envía (redirigido) pero no marca en BD.
- CP-REM-04: Sin EMAIL_REDIRECT_TO, el chequeo manual envía y marca en BD.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main
from tests.conftest import create_access_token

PENDIENTE = {
    "ID": 9001,
    "Numero_Proyecto": "0001612999",
    "Cliente": "CLIENTE REAL",
    "Tipo_Servicio": "Otros",
    "Solicitante": "Pm Real",
    "Contador_Recordatorios": 0,
}


def _admin_headers():
    return {"Authorization": f"Bearer {create_access_token({'sub': 'alejandro.aguilar', 'rol': 'ADMIN'})}"}


@patch("backend.main.registrar_recordatorio_enviado")
@patch("backend.main.send_solicitud_recordatorio_email")
@patch("backend.main.get_proyectos_pendientes_recordatorio", return_value=[PENDIENTE])
def test_rem_01_cycle_skipped_with_redirect(mock_get, mock_send, mock_reg, monkeypatch):
    monkeypatch.setenv("EMAIL_REDIRECT_TO", "alejandro.aguilarm@clarovtr.cl")

    processed = main.run_reminder_cycle()

    assert processed == 0
    mock_get.assert_not_called()
    mock_send.assert_not_called()
    mock_reg.assert_not_called()


@patch("backend.main.registrar_recordatorio_enviado")
@patch("backend.main.send_solicitud_recordatorio_email", return_value={"success": True})
@patch("backend.main.get_proyectos_pendientes_recordatorio", return_value=[PENDIENTE])
def test_rem_02_cycle_sends_and_marks_without_redirect(mock_get, mock_send, mock_reg, monkeypatch):
    monkeypatch.delenv("EMAIL_REDIRECT_TO", raising=False)

    processed = main.run_reminder_cycle()

    assert processed == 1
    mock_send.assert_called_once()
    mock_reg.assert_called_once_with(9001)


@patch("backend.main.registrar_recordatorio_enviado")
@patch("backend.main.send_solicitud_recordatorio_email", return_value={"success": True})
@patch("backend.main.get_proyectos_pendientes_recordatorio", return_value=[PENDIENTE])
def test_rem_03_manual_check_does_not_mark_with_redirect(mock_get, mock_send, mock_reg, monkeypatch):
    monkeypatch.setenv("EMAIL_REDIRECT_TO", "alejandro.aguilarm@clarovtr.cl")
    client = TestClient(main.app)

    res = client.post("/api/solicitudes/recordatorios/ejecutar-manual", headers=_admin_headers())

    assert res.status_code == 200
    mock_send.assert_called_once()
    mock_reg.assert_not_called()
    assert res.json()["registrado_en_bd"] is False


@patch("backend.main.registrar_recordatorio_enviado")
@patch("backend.main.send_solicitud_recordatorio_email", return_value={"success": True})
@patch("backend.main.get_proyectos_pendientes_recordatorio", return_value=[PENDIENTE])
def test_rem_04_manual_check_marks_without_redirect(mock_get, mock_send, mock_reg, monkeypatch):
    monkeypatch.delenv("EMAIL_REDIRECT_TO", raising=False)
    client = TestClient(main.app)

    res = client.post("/api/solicitudes/recordatorios/ejecutar-manual", headers=_admin_headers())

    assert res.status_code == 200
    mock_send.assert_called_once()
    mock_reg.assert_called_once_with(9001)
    assert res.json()["registrado_en_bd"] is True
