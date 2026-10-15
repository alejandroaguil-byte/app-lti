"""
PRUEBAS DE SEGURIDAD DE CORREO EN DESARROLLO
Especificación: odd/tasks/test-safety-dev-email.md (S1, S2)

- CP-MAIL-01: Con EMAIL_REDIRECT_TO, send_email_notification envía solo a la redirección, sin CC/BCC y con prefijo [DEV].
- CP-MAIL-02: El prefijo [DEV] no se duplica.
- CP-MAIL-03: Con EMAIL_REDIRECT_TO, send_ticket_notification_email envía solo a la redirección con prefijo [DEV].
- CP-MAIL-04: EMAIL_REDIRECT_TO inválido bloquea el envío (nunca cae a los destinatarios originales).
- CP-MAIL-05: Sin EMAIL_REDIRECT_TO el envío no cambia (destinatarios y asunto originales).
- CP-MAIL-06: El correo de creación de solicitud no se envía para N° de proyecto con QA o TEST.
- CP-MAIL-07: El correo de creación de solicitud se sigue enviando para un proyecto real numérico.
- CP-MAIL-08: El correo de asignación de LTI no se envía para N° de proyecto con QA o TEST.
- CP-MAIL-09: El correo de asignación se sigue enviando para un proyecto real.
- CP-MAIL-10: El recordatorio de 6 horas excluye proyectos QA/TEST y no envía si solo hay de prueba.
- CP-MAIL-11: La selección del monitor de 6 horas (is_valid_project_number) descarta QA/TEST y conserva reales.
"""

import email
from email.header import decode_header, make_header
from unittest.mock import MagicMock, patch

import pytest

from backend.db import is_valid_project_number
from backend.email_service import (
    send_email_notification,
    send_ticket_notification_email,
    send_solicitud_creada_email,
    send_solicitud_asignada_email,
    send_solicitud_recordatorio_email,
)

REDIRECT = "alejandro.aguilarm@clarovtr.cl"

SMTP_CFG = {
    "host": "smtp.office365.com",
    "port": 587,
    "user": "remitente@clarovtr.cl",
    "password": "MockPassword123!",
    "from_email": "remitente@clarovtr.cl",
    "timeout": 30,
}


def _sent(mock_smtp_class):
    """Retorna (destinatarios_del_sobre, mensaje_parseado) del único sendmail ejecutado."""
    server = mock_smtp_class.return_value
    server.sendmail.assert_called_once()
    _from, envelope, raw = server.sendmail.call_args[0]
    return envelope, email.message_from_string(raw)


def _subject(msg) -> str:
    return str(make_header(decode_header(msg["Subject"])))


@patch("smtplib.SMTP")
def test_mail_01_redirect_replaces_all_recipients(mock_smtp_class, monkeypatch):
    mock_smtp_class.return_value = MagicMock()
    monkeypatch.setenv("EMAIL_REDIRECT_TO", REDIRECT)

    result = send_email_notification(
        to_emails=["pablo.castillo@clarovtr.cl"],
        cc_emails=["lider@clarovtr.cl"],
        bcc_emails=["oculto@clarovtr.cl"],
        subject="Nueva Solicitud",
        html_body="<p>Hola</p>",
        smtp_config_override=SMTP_CFG,
    )

    envelope, msg = _sent(mock_smtp_class)
    assert envelope == [REDIRECT]
    assert msg["To"] == REDIRECT
    assert msg["Cc"] is None
    assert _subject(msg) == "[DEV] Nueva Solicitud"
    assert result["data"]["to"] == [REDIRECT]
    assert result["data"]["cc"] == []
    assert result["data"]["bcc"] == []


@patch("smtplib.SMTP")
def test_mail_02_dev_prefix_not_duplicated(mock_smtp_class, monkeypatch):
    mock_smtp_class.return_value = MagicMock()
    monkeypatch.setenv("EMAIL_REDIRECT_TO", REDIRECT)

    send_email_notification(
        to_emails="pablo.castillo@clarovtr.cl",
        subject="[DEV] Recordatorio",
        text_body="Hola",
        smtp_config_override=SMTP_CFG,
    )

    _envelope, msg = _sent(mock_smtp_class)
    assert _subject(msg) == "[DEV] Recordatorio"


@patch("smtplib.SMTP")
def test_mail_03_redirect_applies_to_ticket_emails(mock_smtp_class, monkeypatch):
    mock_smtp_class.return_value = MagicMock()
    monkeypatch.setenv("EMAIL_REDIRECT_TO", REDIRECT)

    send_ticket_notification_email(
        to_email="pablo.castillo@clarovtr.cl, lider@clarovtr.cl",
        subject="Creación Ticket SD0123456",
        body="Detalle",
        smtp_config_override=SMTP_CFG,
    )

    envelope, msg = _sent(mock_smtp_class)
    assert envelope == [REDIRECT]
    assert msg["To"] == REDIRECT
    assert _subject(msg) == "[DEV] Creación Ticket SD0123456"


@patch("smtplib.SMTP")
def test_mail_04_invalid_redirect_blocks_sending(mock_smtp_class, monkeypatch):
    mock_smtp_class.return_value = MagicMock()
    monkeypatch.setenv("EMAIL_REDIRECT_TO", "no-es-un-correo")

    with pytest.raises(ValueError, match="EMAIL_REDIRECT_TO"):
        send_email_notification(
            to_emails="pablo.castillo@clarovtr.cl",
            subject="Nueva Solicitud",
            text_body="Hola",
            smtp_config_override=SMTP_CFG,
        )
    with pytest.raises(ValueError, match="EMAIL_REDIRECT_TO"):
        send_ticket_notification_email(
            to_email="pablo.castillo@clarovtr.cl",
            subject="Ticket",
            body="Detalle",
            smtp_config_override=SMTP_CFG,
        )
    mock_smtp_class.assert_not_called()


@patch("smtplib.SMTP")
def test_mail_05_without_redirect_behavior_unchanged(mock_smtp_class, monkeypatch):
    mock_smtp_class.return_value = MagicMock()
    monkeypatch.delenv("EMAIL_REDIRECT_TO", raising=False)

    send_email_notification(
        to_emails=["pablo.castillo@clarovtr.cl"],
        cc_emails=["lider@clarovtr.cl"],
        bcc_emails=["oculto@clarovtr.cl"],
        subject="Nueva Solicitud",
        html_body="<p>Hola</p>",
        smtp_config_override=SMTP_CFG,
    )

    envelope, msg = _sent(mock_smtp_class)
    assert envelope == ["pablo.castillo@clarovtr.cl", "lider@clarovtr.cl", "oculto@clarovtr.cl"]
    assert msg["To"] == "pablo.castillo@clarovtr.cl"
    assert msg["Cc"] == "lider@clarovtr.cl"
    assert _subject(msg) == "Nueva Solicitud"


@pytest.mark.parametrize("numero", [
    "000QA-TEST-1792060363",
    "000QA-LOCKED-TEST-1792060374",
    "000qa-e2e-flow-1",
    "TEST-123",
])
@patch("backend.email_service.send_email_notification")
def test_mail_06_creation_email_skips_qa_test_projects(mock_send, numero):
    result = send_solicitud_creada_email({"ID": 1, "Numero_Proyecto": numero, "Cliente": "CLIENTE PRUEBA QA"})

    mock_send.assert_not_called()
    assert result["success"] is False
    assert result["skipped"] is True


@patch("backend.email_service.send_email_notification")
def test_mail_07_creation_email_still_sent_for_real_project(mock_send):
    mock_send.return_value = {"success": True}

    send_solicitud_creada_email({"ID": 2496, "Numero_Proyecto": "0001612444", "Cliente": "INNOVIT SPA"})

    mock_send.assert_called_once()


@patch("backend.email_service.send_email_notification")
def test_mail_08_assignment_email_skips_qa_test_projects(mock_send):
    result = send_solicitud_asignada_email(
        {"ID": 1, "Numero_Proyecto": "000QA-TEST-ED-1", "Cliente": "CLIENTE PRUEBA QA", "Solicitante": "Alejandro Aguilar"},
        pm_email="alejandro.aguilarm@clarovtr.cl",
        lti_email="juan.barrera@clarovtr.cl",
        lt_nombre="Juan Barrera",
    )

    mock_send.assert_not_called()
    assert result["success"] is False
    assert result["skipped"] is True


@patch("backend.email_service.send_email_notification")
def test_mail_09_assignment_email_still_sent_for_real_project(mock_send):
    mock_send.return_value = {"success": True}

    send_solicitud_asignada_email(
        {"ID": 2496, "Numero_Proyecto": "0001612444", "Cliente": "INNOVIT SPA", "Solicitante": "Pm Real"},
        pm_email="pm.real@clarovtr.cl",
        lti_email="juan.barrera@clarovtr.cl",
        lt_nombre="Juan Barrera",
    )

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["to_emails"] == "pm.real@clarovtr.cl"


@patch("backend.email_service.send_email_notification")
def test_mail_10_reminder_excludes_qa_test_projects(mock_send):
    mock_send.return_value = {"success": True}
    real = {"ID": 2569, "Numero_Proyecto": "0001614931", "Cliente": "CLIENTE REAL", "Solicitante": "Pm Real"}
    qa = {"ID": 9002, "Numero_Proyecto": "000QA-T5-UNASSIGNED-1", "Cliente": "CLIENTE PRUEBA QA", "Solicitante": "Qa"}

    send_solicitud_recordatorio_email([real, qa])

    mock_send.assert_called_once()
    body = mock_send.call_args.kwargs["text_body"]
    assert "0001614931" in body
    assert "000QA-T5-UNASSIGNED-1" not in body
    assert "Total de requerimientos esperando Líder Técnico: 1" in body

    mock_send.reset_mock()
    result = send_solicitud_recordatorio_email([qa])
    mock_send.assert_not_called()
    assert result["success"] is True


@pytest.mark.parametrize("numero,expected", [
    ("0001614931", True),
    ("1607916", True),
    ("000QA-T5-UNASSIGNED-1", False),
    ("000qa-e2e-flow-1", False),
    ("TEST-123", False),
])
def test_mail_11_reminder_selection_discards_qa_test(numero, expected):
    assert is_valid_project_number(numero, "CLIENTE", "Otros", "Pm Real") is expected
