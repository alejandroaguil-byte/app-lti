"""
Test Suite: Servicio de Notificación por Correo (Office 365 SMTP) y Endpoint REST
Valida el cumplimiento íntegro de SPECS_ENVIO_CORREO_TICKETS.md:
- Parseo y validación de destinatarios RFC / múltiples correos.
- Construcción de mensajes MIME multipart ('mixed') con texto plano UTF-8 y adjuntos Base64.
- Integración SMTP Office 365 con STARTTLS, timeouts y manejo de excepciones.
- Endpoint FastAPI POST /api/automation/send-ticket-email con JWT y multipart/form-data.
- Estructura DOM del modal de correo y botones en el frontend.
"""

import io
import os
import smtplib
import socket
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from backend.main import app
from tests.conftest import create_access_token
from backend.email_service import (
    parse_and_validate_recipients,
    build_mime_message,
    send_ticket_notification_email,
    MAX_ATTACHMENT_SIZE_BYTES,
)
from backend.config import get_smtp_config


@pytest.fixture
def auth_headers():
    """Generates valid JWT Authorization headers for testing endpoints."""
    token_data = {
        "sub": "aaguilar",
        "nombre_completo": "Alejandro Aguilar",
        "lt_asignado": "Alejandro Aguilar",
        "rol": "ADMIN"
    }
    token = create_access_token(token_data)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_smtp_config():
    """Mock SMTP configuration with valid Office 365 credentials."""
    return {
        "host": "smtp.office365.com",
        "port": 587,
        "user": "alejandro.aguilarm@clarovtr.cl",
        "password": "MockPassword123!",
        "from_email": "alejandro.aguilarm@clarovtr.cl",
        "timeout": 30,
        "default_recipient": "alejandro.aguilarm@clarovtr.cl",
    }


# ==============================================================================
# 1. PRUEBAS UNITARIAS: PARSEO Y VALIDACIÓN DE DESTINATARIOS
# ==============================================================================
def test_parse_and_validate_single_recipient():
    """Verifica el parseo de un correo único válido."""
    res = parse_and_validate_recipients("alejandro.aguilarm@clarovtr.cl")
    assert res == ["alejandro.aguilarm@clarovtr.cl"]


def test_parse_and_validate_multiple_recipients_comma_and_semicolon():
    """Verifica el soporte de múltiples correos separados por comas y puntos y coma."""
    raw = "usuario1@clarovtr.cl, usuario2@clarovtr.cl; usuario3@empresa.com"
    res = parse_and_validate_recipients(raw)
    assert res == ["usuario1@clarovtr.cl", "usuario2@clarovtr.cl", "usuario3@empresa.com"]


def test_parse_and_validate_recipients_deduplication_and_cleaning():
    """Verifica que se eliminen duplicados y espacios en blanco."""
    raw = "  test@claro.cl  , test@claro.cl ; otro@claro.cl "
    res = parse_and_validate_recipients(raw)
    assert res == ["test@claro.cl", "otro@claro.cl"]


def test_parse_and_validate_invalid_and_empty():
    """Verifica el filtrado de correos vacíos o inválidos."""
    assert parse_and_validate_recipients("") == []
    assert parse_and_validate_recipients("   ") == []
    assert parse_and_validate_recipients("invalido;sin-arroba;@sin-usuario.cl") == []


def test_parse_and_validate_list_input():
    """Verifica el soporte para listas de cadenas."""
    res = parse_and_validate_recipients(["a@b.com", "c@d.com, e@f.com"])
    assert res == ["a@b.com", "c@d.com", "e@f.com"]


# ==============================================================================
# 2. PRUEBAS UNITARIAS: CONSTRUCCIÓN DE MENSAJES MIME
# ==============================================================================
def test_build_mime_message_without_attachment():
    """Verifica la construcción de mensaje MIME multipart básico sin adjunto."""
    msg = build_mime_message(
        from_addr="remitente@claro.cl",
        to_addrs=["dest1@claro.cl", "dest2@claro.cl"],
        subject="Asunto de Prueba",
        body="Cuerpo del mensaje en UTF-8 con tildes: cancelación, interacción."
    )
    assert msg["From"] == "remitente@claro.cl"
    assert msg["To"] == "dest1@claro.cl, dest2@claro.cl"
    assert msg["Subject"] == "Asunto de Prueba"
    assert "Date" in msg

    # Verificar que el cuerpo esté presente
    payload = msg.get_payload()
    assert len(payload) == 1
    assert "cancelación, interacción." in payload[0].get_payload(decode=True).decode("utf-8")


def test_build_mime_message_with_attachment():
    """Verifica la inclusión correcta de adjuntos codificados en base64 con Content-Disposition."""
    sample_bytes = b"PDF-1.4 Mock binary content for testing"
    msg = build_mime_message(
        from_addr="remitente@claro.cl",
        to_addrs=["dest@claro.cl"],
        subject="Ticket con Adjunto",
        body="Detalle del ticket adjunto",
        attachment_bytes=sample_bytes,
        attachment_filename="evidencia_ticket.pdf",
        attachment_content_type="application/pdf"
    )

    payload = msg.get_payload()
    assert len(payload) == 2
    body_part, att_part = payload[0], payload[1]

    assert "attachment" in att_part.get("Content-Disposition", "")
    assert 'filename="evidencia_ticket.pdf"' in att_part.get("Content-Disposition", "")
    decoded_payload = att_part.get_payload(decode=True)
    assert decoded_payload == sample_bytes


# ==============================================================================
# 3. PRUEBAS UNITARIAS: SERVICIO send_ticket_notification_email
# ==============================================================================
def test_send_email_missing_configuration():
    """Verifica que se lance ValueError si SMTP_USER o SMTP_PASS no están configurados."""
    empty_cfg = {"host": "smtp.office365.com", "port": 587, "user": "", "password": ""}
    with pytest.raises(ValueError) as exc_info:
        send_ticket_notification_email(
            to_email="dest@claro.cl",
            subject="Test",
            body="Test",
            smtp_config_override=empty_cfg
        )
    assert "El servicio de correo no está configurado" in str(exc_info.value)


def test_send_email_validation_errors(mock_smtp_config):
    """Verifica validaciones de destinatario, asunto, cuerpo y tamaño de adjunto."""
    # 1. Destinatario vacío o inválido
    with pytest.raises(ValueError) as exc1:
        send_ticket_notification_email(to_email="", subject="Subj", body="Body", smtp_config_override=mock_smtp_config)
    assert "requerida" in str(exc1.value).lower()

    # 2. Asunto vacío
    with pytest.raises(ValueError) as exc2:
        send_ticket_notification_email(to_email="dest@claro.cl", subject="   ", body="Body", smtp_config_override=mock_smtp_config)
    assert "asunto" in str(exc2.value).lower()

    # 3. Cuerpo vacío
    with pytest.raises(ValueError) as exc3:
        send_ticket_notification_email(to_email="dest@claro.cl", subject="Subj", body="   ", smtp_config_override=mock_smtp_config)
    assert "cuerpo" in str(exc3.value).lower()

    # 4. Adjunto que excede los 15MB
    large_bytes = b"X" * (MAX_ATTACHMENT_SIZE_BYTES + 1024)
    with pytest.raises(ValueError) as exc4:
        send_ticket_notification_email(
            to_email="dest@claro.cl",
            subject="Subj",
            body="Body",
            attachment_bytes=large_bytes,
            attachment_filename="archivo_grande.zip",
            smtp_config_override=mock_smtp_config
        )
    assert "supera el tamaño máximo" in str(exc4.value)


@patch("smtplib.SMTP")
def test_send_email_success_with_mocked_smtp(mock_smtp_class, mock_smtp_config):
    """Verifica el flujo completo exitoso con STARTTLS y login en Office 365."""
    mock_server_instance = MagicMock()
    mock_smtp_class.return_value = mock_server_instance

    result = send_ticket_notification_email(
        to_email="alejandro.aguilarm@clarovtr.cl, lider@clarovtr.cl",
        subject="Creación Ticket SD0123456",
        body="Detalle de la interacción y petición creada",
        attachment_bytes=b"Sample PDF Content",
        attachment_filename="resumen.pdf",
        ticket_id="SD0123456",
        peticion_id="PET0098765",
        smtp_config_override=mock_smtp_config
    )

    # Verificar llamadas a smtplib.SMTP
    mock_smtp_class.assert_called_once_with("smtp.office365.com", 587, timeout=30)
    mock_server_instance.ehlo.assert_called()
    mock_server_instance.starttls.assert_called_once()
    mock_server_instance.login.assert_called_once_with("alejandro.aguilarm@clarovtr.cl", "MockPassword123!")
    mock_server_instance.sendmail.assert_called_once()
    mock_server_instance.quit.assert_called_once()

    # Verificar estructura del resultado
    assert result["success"] is True
    assert result["ticket_id"] == "SD0123456"
    assert result["peticion_id"] == "PET0098765"
    assert result["has_attachment"] is True
    assert result["attachment_name"] == "resumen.pdf"
    assert len(result["recipients"]) == 2


@patch("smtplib.SMTP")
def test_send_email_auth_error_handling(mock_smtp_class, mock_smtp_config):
    """Verifica el mapeo de SMTPAuthenticationError a PermissionError."""
    mock_server_instance = MagicMock()
    mock_server_instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"5.7.3 Authentication unsuccessful")
    mock_smtp_class.return_value = mock_server_instance

    with pytest.raises(PermissionError) as exc_info:
        send_ticket_notification_email(
            to_email="dest@claro.cl",
            subject="Test",
            body="Test",
            smtp_config_override=mock_smtp_config
        )
    assert "Fallo de autenticación" in str(exc_info.value)
    mock_server_instance.quit.assert_called_once()


@patch("smtplib.SMTP")
def test_send_email_timeout_and_connection_error_handling(mock_smtp_class, mock_smtp_config):
    """Verifica el mapeo de socket.timeout y SMTPConnectError a ConnectionError."""
    mock_smtp_class.side_effect = socket.timeout("timed out")

    with pytest.raises(ConnectionError) as exc_info:
        send_ticket_notification_email(
            to_email="dest@claro.cl",
            subject="Test",
            body="Test",
            smtp_config_override=mock_smtp_config
        )
    assert "No se pudo establecer conexión con el servidor SMTP" in str(exc_info.value)


# ==============================================================================
# 4. PRUEBAS DE INTEGRACIÓN: ENDPOINT REST FASTAPI
# ==============================================================================
def test_api_send_email_unauthorized():
    """Verifica que el endpoint rechace peticiones sin token JWT válido (HTTP 401)."""
    client = TestClient(app)
    response = client.post("/api/automation/send-ticket-email", data={"to_email": "dest@claro.cl", "subject": "Test", "body": "Test"})
    assert response.status_code == 401


def test_api_send_email_missing_fields(auth_headers):
    """Verifica que el endpoint valide campos requeridos (HTTP 400)."""
    client = TestClient(app)

    # Falta destinatario
    res1 = client.post(
        "/api/automation/send-ticket-email",
        headers=auth_headers,
        data={"to_email": "", "subject": "Test", "body": "Test"}
    )
    assert res1.status_code == 400

    # Falta asunto
    res2 = client.post(
        "/api/automation/send-ticket-email",
        headers=auth_headers,
        data={"to_email": "dest@claro.cl", "subject": "", "body": "Test"}
    )
    assert res2.status_code == 400

    # Falta cuerpo
    res3 = client.post(
        "/api/automation/send-ticket-email",
        headers=auth_headers,
        data={"to_email": "dest@claro.cl", "subject": "Test", "body": ""}
    )
    assert res3.status_code == 400


def test_api_send_email_payload_too_large(auth_headers):
    """Verifica que un adjunto mayor a 15MB retorne HTTP 413 Payload Too Large."""
    client = TestClient(app)
    large_content = b"A" * (16 * 1024 * 1024)  # 16 MB

    response = client.post(
        "/api/automation/send-ticket-email",
        headers=auth_headers,
        data={
            "to_email": "dest@claro.cl",
            "subject": "Test Payload Too Large",
            "body": "Prueba de adjunto pesado"
        },
        files={"attachment": ("archivo_pesado.zip", io.BytesIO(large_content), "application/zip")}
    )
    assert response.status_code == 413
    assert "supera el tamaño máximo permitido" in response.json()["detail"]


@patch("backend.main.send_ticket_notification_email")
def test_api_send_email_success(mock_send_fn, auth_headers):
    """Verifica respuesta HTTP 200 con payload estructurado tras envío exitoso."""
    mock_send_fn.return_value = {
        "success": True,
        "message": "Correo enviado exitosamente a alejandro.aguilarm@clarovtr.cl",
        "data": {
            "recipients": ["alejandro.aguilarm@clarovtr.cl"],
            "subject": "Creacion test automatizacion",
            "ticket_id": "SD1049281",
            "peticion_id": "PET001234",
            "has_attachment": True,
            "attachment_name": "evidencia.pdf",
            "sent_at": "2026-08-28T14:45:00Z"
        }
    }

    client = TestClient(app)
    sample_pdf = b"%PDF-1.4 sample file content"

    response = client.post(
        "/api/automation/send-ticket-email",
        headers=auth_headers,
        data={
            "to_email": "alejandro.aguilarm@clarovtr.cl",
            "subject": "Creacion test automatizacion",
            "body": "Prueba de automatización exitosa",
            "ticket_id": "SD1049281",
            "peticion_id": "PET001234"
        },
        files={"attachment": ("evidencia.pdf", io.BytesIO(sample_pdf), "application/pdf")}
    )

    assert response.status_code == 200
    json_data = response.json()
    assert json_data["success"] is True
    assert json_data["data"]["ticket_id"] == "SD1049281"
    assert json_data["data"]["peticion_id"] == "PET001234"
    assert json_data["data"]["has_attachment"] is True


@patch("backend.main.send_ticket_notification_email")
def test_api_send_email_smtp_error_propagation(mock_send_fn, auth_headers):
    """Verifica la propagación adecuada de errores PermissionError (502) y ConnectionError (504)."""
    client = TestClient(app)

    # 1. Error de autenticación -> HTTP 502
    mock_send_fn.side_effect = PermissionError("Fallo de autenticación con Office 365.")
    res_auth = client.post(
        "/api/automation/send-ticket-email",
        headers=auth_headers,
        data={"to_email": "dest@claro.cl", "subject": "Test", "body": "Body"}
    )
    assert res_auth.status_code == 502
    assert "Fallo de autenticación" in res_auth.json()["detail"]

    # 2. Error de conexión / timeout -> HTTP 504
    mock_send_fn.side_effect = ConnectionError("Tiempo de espera agotado al conectar con el servidor SMTP.")
    res_conn = client.post(
        "/api/automation/send-ticket-email",
        headers=auth_headers,
        data={"to_email": "dest@claro.cl", "subject": "Test", "body": "Body"}
    )
    assert res_conn.status_code == 504
    assert "Tiempo de espera agotado" in res_conn.json()["detail"]


# ==============================================================================
# 5. PRUEBAS DE ESTRUCTURA DOM DEL FRONTEND
# ==============================================================================
def test_frontend_dom_elements_present():
    """Verifica que index.html contenga los elementos del modal de éxito y del modal de correo."""
    index_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "index.html")
    assert os.path.exists(index_path)

    with open(index_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Botón en modal de éxito
    assert 'id="btn-open-email-modal"' in html_content
    assert 'btn-email-action' in html_content

    # Modal de correo
    assert 'id="email-ticket-modal"' in html_content
    assert 'id="modal-email-title"' in html_content
    assert 'id="btn-close-email-modal-icon"' in html_content
    assert 'id="email-status-alert"' in html_content
    assert 'id="email-badge-ticket-id"' in html_content
    assert 'id="email-badge-peticion-id"' in html_content

    # Formulario y campos
    assert 'id="email-ticket-form"' in html_content
    assert 'id="email-destinatario"' in html_content
    assert 'id="email-asunto"' in html_content
    assert 'id="email-cuerpo"' in html_content
    assert 'id="email-adjunto"' in html_content
    assert 'id="file-attachment-dropzone"' in html_content
    assert 'id="btn-remove-attachment"' in html_content

    # Footer modal
    assert 'id="btn-send-email"' in html_content
    assert 'id="btn-cancel-email"' in html_content
    assert 'id="email-spinner"' in html_content


# ==============================================================================
# 6. PRUEBAS DE SEGURIDAD: CRLF INJECTION, PATH TRAVERSAL Y SOCKET CLEANUP
# ==============================================================================
from backend.email_service import sanitize_header_value, sanitize_attachment_filename
from backend.config import _get_int_env


def test_sanitize_header_value_crlf_prevention():
    """Verifica la neutralización de CRLF Injection en cabeceras de correo."""
    malicious_subject = "Asunto legítimo\r\nBcc: victima@clarovtr.cl\r\nSubject: Inyección"
    clean = sanitize_header_value(malicious_subject)
    assert "\r" not in clean
    assert "\n" not in clean
    assert clean == "Asunto legítimo Bcc: victima@clarovtr.cl Subject: Inyección"


def test_sanitize_attachment_filename_path_traversal_and_length():
    """Verifica la neutralización de Path Traversal (Unix y Windows) y truncado seguro."""
    # Unix traversal
    assert sanitize_attachment_filename("../../../etc/shadow") == "shadow"
    # Windows traversal
    assert sanitize_attachment_filename(r"..\..\Windows\System32\cmd.exe") == "cmd.exe"
    # Null bytes y comillas
    assert sanitize_attachment_filename('evil"\x00test.pdf') == "eviltest.pdf"
    # Nombre vacío o puntos
    assert sanitize_attachment_filename("...") == "adjunto.dat"
    assert sanitize_attachment_filename(None) == "adjunto.dat"
    
    # Nombre excesivamente largo
    long_name = "a" * 200 + ".pdf"
    sanitized = sanitize_attachment_filename(long_name)
    assert len(sanitized) <= 120
    assert sanitized.endswith(".pdf")


def test_parse_recipients_crlf_handling():
    """Verifica que destinatarios con inyección CRLF sean sanitizados o validados correctamente."""
    raw = "test@claro.cl\r\n, legitimo@claro.cl"
    res = parse_and_validate_recipients(raw)
    assert "test@claro.cl" in res
    assert "legitimo@claro.cl" in res
    for email in res:
        assert "\r" not in email
        assert "\n" not in email


@patch("smtplib.SMTP")
def test_send_email_finally_server_close_fallback(mock_smtp_class, mock_smtp_config):
    """Verifica que si server.quit() lanza excepción, se ejecute server.close() en el bloque finally."""
    mock_server_instance = MagicMock()
    mock_server_instance.quit.side_effect = Exception("Quit connection broken")
    mock_smtp_class.return_value = mock_server_instance

    result = send_ticket_notification_email(
        to_email="alejandro.aguilarm@clarovtr.cl",
        subject="Prueba fallback cleanup",
        body="Contenido",
        smtp_config_override=mock_smtp_config
    )

    assert result["success"] is True
    mock_server_instance.quit.assert_called_once()
    mock_server_instance.close.assert_called_once()


def test_config_get_int_env_defensive_parsing():
    """Verifica que _get_int_env no falle con valores vacíos, nulos o no numéricos."""
    assert _get_int_env("NON_EXISTING_KEY_XYZ", 587) == 587
    with patch.dict(os.environ, {"TEST_INT_VAL": "465"}):
        assert _get_int_env("TEST_INT_VAL", 587) == 465
    with patch.dict(os.environ, {"TEST_INT_VAL": ""}):
        assert _get_int_env("TEST_INT_VAL", 587) == 587
    with patch.dict(os.environ, {"TEST_INT_VAL": "invalid_num"}):
        assert _get_int_env("TEST_INT_VAL", 587) == 587


# ==============================================================================
# 7. PRUEBAS DE SOPORTE DUAL: JSON PAYLOAD, BASE64 Y ALIASES (v1.1.0)
# ==============================================================================
import base64


def test_auth_js_formdata_handling():
    """Verifica que auth.js implemente detección de FormData y no fuerce application/json."""
    auth_js_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "js", "auth.js")
    assert os.path.exists(auth_js_path)

    with open(auth_js_path, "r", encoding="utf-8") as f:
        auth_js = f.read()

    assert "isFormData" in auth_js
    assert "FormData" in auth_js
    assert "delete headers['Content-Type']" in auth_js


@patch("backend.main.send_ticket_notification_email")
def test_api_send_email_json_payload(mock_send_fn, auth_headers):
    """Verifica envío exitoso con payload JSON puro (Content-Type: application/json)."""
    mock_send_fn.return_value = {
        "success": True,
        "message": "Correo enviado exitosamente",
        "data": {
            "recipients": ["alejandro.aguilarm@clarovtr.cl"],
            "subject": "Asunto JSON",
            "ticket_id": "SD998877",
            "peticion_id": "PET112233",
            "has_attachment": False,
            "attachment_name": None,
            "sent_at": "2026-08-28T15:00:00Z"
        }
    }

    client = TestClient(app)
    payload = {
        "to_email": "alejandro.aguilarm@clarovtr.cl",
        "subject": "Asunto JSON",
        "body": "Cuerpo en formato JSON",
        "ticket_id": "SD998877",
        "peticion_id": "PET112233"
    }

    response = client.post(
        "/api/automation/send-ticket-email",
        headers={**auth_headers, "Content-Type": "application/json"},
        json=payload
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    mock_send_fn.assert_called_once()
    call_kwargs = mock_send_fn.call_args.kwargs
    assert call_kwargs["to_email"] == "alejandro.aguilarm@clarovtr.cl"
    assert call_kwargs["subject"] == "Asunto JSON"
    assert call_kwargs["body"] == "Cuerpo en formato JSON"
    assert call_kwargs["ticket_id"] == "SD998877"
    assert call_kwargs["peticion_id"] == "PET112233"
    assert call_kwargs["attachment_bytes"] is None


@patch("backend.main.send_ticket_notification_email")
def test_api_send_email_json_with_base64_attachment(mock_send_fn, auth_headers):
    """Verifica envío JSON con archivo adjunto codificado en Base64."""
    mock_send_fn.return_value = {
        "success": True,
        "message": "Correo enviado exitosamente con adjunto Base64",
        "data": {"has_attachment": True, "attachment_name": "reporte.pdf"}
    }

    client = TestClient(app)
    raw_pdf_bytes = b"%PDF-1.4 Mock Base64 Attachment"
    b64_pdf = base64.b64encode(raw_pdf_bytes).decode("utf-8")

    payload = {
        "to_email": "alejandro.aguilarm@clarovtr.cl",
        "subject": "Ticket con PDF Base64",
        "body": "Adjunto PDF en Base64",
        "attachment_base64": b64_pdf,
        "attachment_filename": "reporte.pdf",
        "attachment_content_type": "application/pdf"
    }

    response = client.post(
        "/api/automation/send-ticket-email",
        headers=auth_headers,
        json=payload
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    mock_send_fn.assert_called_once()
    call_kwargs = mock_send_fn.call_args.kwargs
    assert call_kwargs["attachment_bytes"] == raw_pdf_bytes
    assert call_kwargs["attachment_filename"] == "reporte.pdf"
    assert call_kwargs["attachment_content_type"] == "application/pdf"


@patch("backend.main.send_ticket_notification_email")
def test_api_send_email_json_with_data_uri_base64(mock_send_fn, auth_headers):
    """Verifica que adjuntos con prefijo data URI (data:application/pdf;base64,...) sean decodificados correctamente."""
    mock_send_fn.return_value = {"success": True}

    client = TestClient(app)
    raw_bytes = b"Data URI content"
    b64_str = base64.b64encode(raw_bytes).decode("utf-8")
    data_uri = f"data:application/pdf;base64,{b64_str}"

    payload = {
        "to_email": "dest@claro.cl",
        "subject": "Test Data URI",
        "body": "Test Data URI content",
        "attachment_base64": data_uri,
        "attachment_filename": "doc.pdf"
    }

    response = client.post(
        "/api/automation/send-ticket-email",
        headers=auth_headers,
        json=payload
    )

    assert response.status_code == 200
    call_kwargs = mock_send_fn.call_args.kwargs
    assert call_kwargs["attachment_bytes"] == raw_bytes


def test_api_send_email_json_invalid_base64(auth_headers):
    """Verifica que un Base64 corrupto retorne HTTP 400 Bad Request."""
    client = TestClient(app)
    payload = {
        "to_email": "dest@claro.cl",
        "subject": "Test Invalid B64",
        "body": "Test",
        "attachment_base64": "!!!EstaCadenaNoEsBase64Valido===",
        "attachment_filename": "corrupto.pdf"
    }

    response = client.post(
        "/api/automation/send-ticket-email",
        headers=auth_headers,
        json=payload
    )

    assert response.status_code == 400
    assert "Base64 es inválido" in response.json()["detail"]


def test_api_send_email_json_base64_too_large(auth_headers):
    """Verifica que un adjunto Base64 > 15MB retorne HTTP 413 Content Too Large."""
    client = TestClient(app)
    large_bytes = b"Z" * (16 * 1024 * 1024)
    b64_large = base64.b64encode(large_bytes).decode("utf-8")

    payload = {
        "to_email": "dest@claro.cl",
        "subject": "Test Large B64",
        "body": "Test",
        "attachment_base64": b64_large,
        "attachment_filename": "grande.bin"
    }

    response = client.post(
        "/api/automation/send-ticket-email",
        headers=auth_headers,
        json=payload
    )

    assert response.status_code == 413
    assert "supera el tamaño máximo" in response.json()["detail"]


@patch("backend.main.send_ticket_notification_email")
def test_api_send_email_spanish_aliases_json(mock_send_fn, auth_headers):
    """Verifica soporte de alias en español (para, asunto, cuerpo, adjunto_base64, adjunto_nombre) en JSON."""
    mock_send_fn.return_value = {"success": True}

    client = TestClient(app)
    raw_bytes = b"Contenido adjunto espanol"
    b64_str = base64.b64encode(raw_bytes).decode("utf-8")

    payload = {
        "para": "lider@clarovtr.cl",
        "asunto": "Asunto en espanol",
        "cuerpo": "Cuerpo en espanol",
        "adjunto_base64": b64_str,
        "adjunto_nombre": "evidencia_es.pdf"
    }

    response = client.post(
        "/api/automation/send-ticket-email",
        headers=auth_headers,
        json=payload
    )

    assert response.status_code == 200
    call_kwargs = mock_send_fn.call_args.kwargs
    assert call_kwargs["to_email"] == "lider@clarovtr.cl"
    assert call_kwargs["subject"] == "Asunto en espanol"
    assert call_kwargs["body"] == "Cuerpo en espanol"
    assert call_kwargs["attachment_bytes"] == raw_bytes
    assert call_kwargs["attachment_filename"] == "evidencia_es.pdf"


@patch("backend.main.send_ticket_notification_email")
def test_api_send_email_spanish_aliases_form(mock_send_fn, auth_headers):
    """Verifica soporte de alias en español (para, asunto, cuerpo, adjunto) en multipart/form-data."""
    mock_send_fn.return_value = {"success": True}

    client = TestClient(app)
    sample_file = b"Contenido archivo form"

    response = client.post(
        "/api/automation/send-ticket-email",
        headers=auth_headers,
        data={
            "para": "lider_form@clarovtr.cl",
            "asunto": "Asunto Form Alias",
            "cuerpo": "Cuerpo Form Alias",
            "ticket_id": "SD8877",
            "peticion_id": "PET5544"
        },
        files={"adjunto": ("adjunto_alias.txt", io.BytesIO(sample_file), "text/plain")}
    )

    assert response.status_code == 200
    call_kwargs = mock_send_fn.call_args.kwargs
    assert call_kwargs["to_email"] == "lider_form@clarovtr.cl"
    assert call_kwargs["subject"] == "Asunto Form Alias"
    assert call_kwargs["body"] == "Cuerpo Form Alias"
    assert call_kwargs["ticket_id"] == "SD8877"
    assert call_kwargs["peticion_id"] == "PET5544"
    assert call_kwargs["attachment_bytes"] == sample_file
    assert call_kwargs["attachment_filename"] == "adjunto_alias.txt"


@patch("backend.main.send_ticket_notification_email")
def test_api_send_email_expanded_aliases_json(mock_send_fn, auth_headers):
    """Verifica soporte de alias extendidos (id_ticket, id_peticion, archivo_base64, nombre_archivo, tipo_contenido)."""
    mock_send_fn.return_value = {"success": True}

    client = TestClient(app)
    raw_bytes = b"Datos de prueba extendida"
    b64_str = base64.b64encode(raw_bytes).decode("utf-8")

    payload = {
        "destinatario": "soporte@clarovtr.cl",
        "titulo": "Incidencia en Servidor",
        "descripcion": "Detalle extendido del incidente",
        "id_ticket": "SD-554433",
        "id_peticion": "PET-998877",
        "archivo_base64": b64_str,
        "nombre_archivo": "log_servidor.txt",
        "tipo_contenido": "text/plain"
    }

    response = client.post(
        "/api/automation/send-ticket-email",
        headers=auth_headers,
        json=payload
    )

    assert response.status_code == 200
    call_kwargs = mock_send_fn.call_args.kwargs
    assert call_kwargs["to_email"] == "soporte@clarovtr.cl"
    assert call_kwargs["subject"] == "Incidencia en Servidor"
    assert call_kwargs["body"] == "Detalle extendido del incidente"
    assert call_kwargs["ticket_id"] == "SD-554433"
    assert call_kwargs["peticion_id"] == "PET-998877"
    assert call_kwargs["attachment_bytes"] == raw_bytes
    assert call_kwargs["attachment_filename"] == "log_servidor.txt"
    assert call_kwargs["attachment_content_type"] == "text/plain"


@patch("backend.main.send_ticket_notification_email")
def test_api_send_email_expanded_aliases_form(mock_send_fn, auth_headers):
    """Verifica soporte de alias extendidos (destinatario, titulo, descripcion, archivo) en Form."""
    mock_send_fn.return_value = {"success": True}

    client = TestClient(app)
    sample_file = b"Contenido log form"

    response = client.post(
        "/api/automation/send-ticket-email",
        headers=auth_headers,
        data={
            "destinatario": "admin@clarovtr.cl",
            "titulo": "Ticket desde Formulario",
            "descripcion": "Reporte de error en nodo",
            "id_ticket": "SD-112233",
            "id_peticion": "PET-445566"
        },
        files={"archivo": ("nodo_log.txt", io.BytesIO(sample_file), "text/plain")}
    )

    assert response.status_code == 200
    call_kwargs = mock_send_fn.call_args.kwargs
    assert call_kwargs["to_email"] == "admin@clarovtr.cl"
    assert call_kwargs["subject"] == "Ticket desde Formulario"
    assert call_kwargs["body"] == "Reporte de error en nodo"
    assert call_kwargs["ticket_id"] == "SD-112233"
    assert call_kwargs["peticion_id"] == "PET-445566"
    assert call_kwargs["attachment_bytes"] == sample_file
    assert call_kwargs["attachment_filename"] == "nodo_log.txt"



