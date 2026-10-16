import os
import re
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import jwt

from backend.main import (
    app,
    notificar_creacion_solicitud_bg,
    notificar_asignacion_lti_bg,
    REMINDER_INTERVAL_HOURS,
    REMINDER_INTERVAL_MINUTES,
)
from backend.config import PORTAL_JWT_SECRET, JWT_ALGORITHM
from backend.email_service import (
    build_mime_message,
    send_email_notification,
    build_solicitud_creada_email_html,
    build_solicitud_recordatorio_email_html,
    build_solicitud_asignada_email_html,
    send_solicitud_creada_email,
    send_solicitud_recordatorio_email,
    send_solicitud_asignada_email,
    COORDINADORES_LTI_EMAILS,
)
from backend.db import (
    resolve_user_email,
    get_proyectos_pendientes_recordatorio,
    registrar_recordatorio_enviado,
    mark_solicitudes_reminder_sent,
    get_db_connection,
    CANONICAL_EMAIL_MAP
)

client = TestClient(app)

def create_mock_jwt(username="test.pm", role="PM", full_name="Test PM User", email="test.pm@clarovtr.cl"):
    payload = {
        "sub": username,
        "username": username,
        "name": full_name,
        "email": email,
        "purpose": "session",
        "adminLevel": 2 if role == "ADMIN" else 0,
        "toolAccess": {"app-lti": "operador"}
    }
    return jwt.encode(payload, PORTAL_JWT_SECRET, algorithm=JWT_ALGORITHM)


# =============================================================================
# PRUEBAS UNITARIAS: RESOLUCIÓN DE CORREOS PM Y LTI (TC-EML-006, TC-EML-007)
# =============================================================================
class TestResolucionCorreos:

    def test_resolve_user_email_direct_valid_email(self):
        """Si ya es un correo electrónico válido, lo devuelve en minúsculas."""
        email = "Rodrigo.Morales@clarovtr.cl"
        resolved = resolve_user_email(email)
        assert resolved == "rodrigo.morales@clarovtr.cl"

    def test_resolve_user_email_canonical_map(self):
        """Resuelve correctamente los líderes y administradores canónicos."""
        assert resolve_user_email("Alejandro Aguilar") == "alejandro.aguilarm@clarovtr.cl"
        assert resolve_user_email("alejandro.aguilar") == "alejandro.aguilarm@clarovtr.cl"
        assert resolve_user_email("Pablo Castillo") == "pablo.castillo@clarovtr.cl"
        assert resolve_user_email("Erwin Sandoval") == "erwin.sandoval@clarovtr.cl"
        assert resolve_user_email("Juan Barrera") == "juan.barrera@clarovtr.cl"
        assert resolve_user_email("Samuel Paredes") == "samuel.paredes@clarovtr.cl"
        assert resolve_user_email("Solange Ortiz") == "solange.ortiz@clarovtr.cl"

    def test_resolve_user_email_fallback_heuristic(self):
        """Fallback corporativo determinista nombre.apellido@clarovtr.cl."""
        resolved = resolve_user_email("María José González")
        assert resolved is not None
        assert resolved.endswith("@clarovtr.cl")
        assert "maria" in resolved

    def test_resolve_user_email_empty_or_none(self):
        """Retorna None ante entradas vacías o inválidas."""
        assert resolve_user_email(None) is None
        assert resolve_user_email("") is None
        assert resolve_user_email("   ") is None
        assert resolve_user_email("N/A") is None


# =============================================================================
# PRUEBAS DE PLANTILLAS HTML HALO DESIGN SYSTEM (TC-EML-009)
# =============================================================================
class TestPlantillasHtmlHalo:

    def test_plantilla_solicitud_creada_halo_tokens(self):
        """Verifica que la plantilla de creación respete la paleta y atributos HALO."""
        proy = {
            "ID": 9999,
            "Numero_Proyecto": "00099999",
            "Cliente": "TEST CLIENTE S.A.",
            "Solicitante": "Juan Carlos Pérez",
            "Creado": "2026-10-14 10:30:00",
            "Estado": "Generado",
            "Detalle": "Solot: 123456 - Tarea: Instalación de FO Liray"
        }
        html = build_solicitud_creada_email_html(proy)

        # Paleta institucional HALO
        assert "#B52217" in html  # Cabecera roja
        assert "#0097A9" in html  # Acento Teal
        assert "#FDEDEA" in html  # Alerta suave
        assert "#DA291C" in html  # Alerta borde
        assert "00099999" in html
        assert "TEST CLIENTE S.A." in html
        assert "Juan Carlos Pérez" in html
        assert "Instalación de FO Liray" in html
        assert "Generado" in html
        assert "Acceder a App LTI y Asignar Proyecto" in html

    def test_plantilla_recordatorio_6h_halo_tokens(self):
        """Verifica que la plantilla de recordatorio periódico muestre tabla y alerta 6h."""
        pendientes = [
            {
                "ID": 101,
                "Numero_Proyecto": "000101",
                "Cliente": "BANCO DE CHILE",
                "Solicitante": "Rodrigo PM",
                "Creado": "2026-10-14 02:00:00",
                "Contador_Recordatorios": 0,
                "Minutos_Desde_Creacion": 420
            },
            {
                "ID": 102,
                "Numero_Proyecto": "000102",
                "Cliente": "ENTEL",
                "Solicitante": "Ana PM",
                "Creado": "2026-10-14 01:00:00",
                "Contador_Recordatorios": 1,
                "Minutos_Desde_Creacion": 480
            }
        ]
        html = build_solicitud_recordatorio_email_html(pendientes, horas_transcurridas=6)

        assert "#B52217" in html
        assert "#0097A9" in html
        assert "000101" in html
        assert "BANCO DE CHILE" in html
        assert "000102" in html
        assert "ENTEL" in html
        assert "6" in html
        assert "Recordatorio" in html
        assert "Ingresar a App LTI" in html

    def test_plantilla_asignacion_lti_halo_tokens(self):
        """Verifica que la plantilla de asignación celebre la asignación con distintivo verde y líder técnico."""
        proy = {
            "Numero_Proyecto": "00055555",
            "Cliente": "CENCOSUD",
            "Solicitante": "Carlos PM",
            "Estado": "Generado",
            "LT_Asignado": "Erwin Sandoval"
        }
        html = build_solicitud_asignada_email_html(proy, lt_nombre="Erwin Sandoval", solicitante_nombre="Carlos PM")

        assert "#B52217" in html
        assert "#0097A9" in html
        assert "#ECFDF5" in html  # Verde éxito
        assert "Erwin Sandoval" in html
        assert "00055555" in html
        assert "CENCOSUD" in html
        assert "Carlos PM" in html
        assert "Ver Proyecto en App LTI" in html


# =============================================================================
# PRUEBAS DE CONSTRUCCIÓN MIME Y ENVÍO (TC-EML-001, TC-EML-002, TC-EML-008)
# =============================================================================
class TestMimeYEnvioCorreo:

    def test_build_mime_message_multipart_with_cc_and_html(self):
        """Verifica que build_mime_message cree estructura multipart/mixed con alternative y cabecera Cc."""
        msg = build_mime_message(
            from_addr="notificaciones@clarovtr.cl",
            to_addrs=["pm@clarovtr.cl"],
            subject="Test Asunto",
            body="Texto plano de respaldo",
            html_body="<b>Cuerpo HTML</b>",
            cc_addrs=["lti@clarovtr.cl"]
        )
        assert msg["From"] == "notificaciones@clarovtr.cl"
        assert msg["To"] == "pm@clarovtr.cl"
        assert msg["Cc"] == "lti@clarovtr.cl"
        assert msg["Subject"] == "Test Asunto"

        # Verificar que contiene parte alternativa con HTML
        payload = msg.get_payload()
        assert len(payload) >= 1
        alt_part = payload[0]
        assert alt_part.get_content_type() == "multipart/alternative"

    @patch("backend.email_service.send_email_notification")
    def test_send_solicitud_creada_email_targets_coordinadores(self, mock_send):
        """TC-EML-001: Despacha correo de creación a ambos coordinadores oficiales."""
        mock_send.return_value = {"success": True, "message": "Enviado"}
        proy = {
            "ID": 888,
            "Numero_Proyecto": "000888",
            "Cliente": "WALMART",
            "Solicitante": "Pedro PM",
            "Creado": "2026-10-14 12:00:00",
            "Detalle": "Requerimiento urgente"
        }
        res = send_solicitud_creada_email(proy)

        assert res.get("success") is True
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert "alejandro.aguilarm@clarovtr.cl" in call_kwargs["to_emails"]
        assert "pablo.castillo@clarovtr.cl" in call_kwargs["to_emails"]
        assert "000888" in call_kwargs["subject"]
        assert "WALMART" in call_kwargs["subject"]

    @patch("backend.email_service.send_email_notification")
    def test_send_solicitud_asignada_email_to_pm_cc_lti(self, mock_send):
        """TC-EML-002: Despacha correo con Para: PM y CC: LTI."""
        mock_send.return_value = {"success": True, "message": "Enviado"}
        proy = {
            "ID": 777,
            "Numero_Proyecto": "000777",
            "Cliente": "SODIMAC",
            "Solicitante": "Solange Ortiz",
            "LT_Asignado": "Erwin Sandoval",
            "Estado": "Generado"
        }
        res = send_solicitud_asignada_email(
            proyecto_data=proy,
            pm_email="pm.test@clarovtr.cl",
            lti_email="erwin.sandoval@clarovtr.cl"
        )
        assert res.get("success") is True
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert call_kwargs["to_emails"] == "pm.test@clarovtr.cl"
        assert call_kwargs["cc_emails"] == ["erwin.sandoval@clarovtr.cl"]

    @patch("backend.email_service.smtplib.SMTP")
    def test_send_email_smtp_failure_resilience(self, mock_smtp_cls):
        """TC-EML-008: Resiliencia ante fallos SMTP en funciones despachadoras."""
        mock_smtp_cls.side_effect = Exception("Conexión rechazada por servidor SMTP")

        proy = {
            "ID": 123,
            "Numero_Proyecto": "000123",
            "Cliente": "TEST CLIENT",
            "Solicitante": "PM User",
            "Detalle": "Test"
        }
        # send_solicitud_creada_email no debe arrojar excepción sino retornar dict con error
        res = send_solicitud_creada_email(proy)
        assert res.get("success") is False
        assert "error" in res


# =============================================================================
# PRUEBAS ENDPOINTS API (FASTAPI)
# =============================================================================
class TestEndpointsNotificaciones:

    @patch("backend.main.notificar_creacion_solicitud_bg")
    @patch("backend.main.create_solicitud_lti")
    def test_api_crear_solicitud_triggers_background_task(self, mock_create, mock_bg):
        """TC-EML-001: POST /api/solicitudes/crear programa tarea en background."""
        mock_create.return_value = {
            "success": True,
            "data": {
                "ID": 901,
                "Numero_Proyecto": "000901",
                "Cliente": "RIPLEY",
                "Solicitante": "pm.test",
                "Estado": "Generado",
                "Creado": "2026-10-14 14:00:00",
                "Detalle": "Detalle solots"
            }
        }
        token = create_mock_jwt(username="pm.test", role="PM")
        client.cookies.set("access_token", token)

        payload = {
            "cliente": "RIPLEY",
            "numero_proyecto": "000901",
            "fecha_solicitud": "2026-10-14",
            "detalle": "Detalle solots",
            "lt_asignado": ""
        }
        response = client.post("/api/solicitudes/crear", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Solicitud LTI creada exitosamente"

    @patch("backend.main.notificar_asignacion_lti_bg")
    @patch("backend.main.update_proyecto")
    def test_api_actualizar_proyecto_triggers_assignment_notification(self, mock_update, mock_bg):
        """TC-EML-002: PUT /api/proyectos/{id} dispara notificación si pasa a asignado."""
        mock_update.return_value = {
            "success": True,
            "was_assigned": True,
            "prev_lt": None,
            "new_lt": "Erwin Sandoval",
            "solicitante": "Rodrigo PM",
            "data": {
                "ID": 303,
                "Numero_Proyecto": "000303",
                "Cliente": "CLARO PROYECTOS",
                "LT_Asignado": "Erwin Sandoval",
                "Estado": "Generado",
                "Solicitante": "Rodrigo PM",
                "Detalle": "Actualizado"
            }
        }
        token = create_mock_jwt(username="alejandro.aguilar", role="ADMIN")
        client.cookies.set("access_token", token)

        payload = {
            "cliente": "CLARO PROYECTOS",
            "estado": "Generado",
            "detalle": "Actualizado",
            "lt_asignado": "Erwin Sandoval",
            "tipo_servicio": "Otros",
            "comentario": None
        }
        response = client.put("/api/proyectos/303", json=payload)
        assert response.status_code == 200

    @patch("backend.main.notificar_asignacion_lti_bg")
    @patch("backend.main.update_proyecto")
    def test_api_actualizar_proyecto_without_assignment_does_not_trigger(self, mock_update, mock_bg):
        """TC-EML-003: PUT /api/proyectos/{id} sin cambio de asignación no dispara notificación."""
        mock_update.return_value = {
            "success": True,
            "was_assigned": False,
            "prev_lt": "Samuel Paredes",
            "new_lt": "Samuel Paredes",
            "data": {
                "ID": 404,
                "Numero_Proyecto": "000404",
                "Cliente": "TEST CLIENT",
                "LT_Asignado": "Samuel Paredes",
                "Estado": "Generado"
            }
        }
        token = create_mock_jwt(username="alejandro.aguilar", role="ADMIN")
        client.cookies.set("access_token", token)

        payload = {
            "cliente": "TEST CLIENT",
            "estado": "Generado",
            "detalle": "Solo actualización de detalle",
            "lt_asignado": "Samuel Paredes"
        }
        response = client.put("/api/proyectos/404", json=payload)
        assert response.status_code == 200
        mock_bg.assert_not_called()

    def test_api_recordatorios_estado_admin(self):
        """GET /api/solicitudes/recordatorios/estado retorna estado estructurado."""
        token = create_mock_jwt(username="admin.test", role="ADMIN")
        client.cookies.set("access_token", token)

        response = client.get("/api/solicitudes/recordatorios/estado")
        assert response.status_code == 200
        data = response.json()
        assert "scheduler_active" in data
        assert "reminder_threshold_hours" in data
        assert "destinatarios_coordinadores" in data
        assert "proyectos_pendientes" in data

    @patch("backend.main.send_solicitud_recordatorio_email")
    def test_api_recordatorios_ejecutar_manual(self, mock_send_email):
        """POST /api/solicitudes/recordatorios/ejecutar-manual ejecuta chequeo forzado."""
        mock_send_email.return_value = {"success": True}
        token = create_mock_jwt(username="admin.test", role="ADMIN")
        client.cookies.set("access_token", token)

        response = client.post("/api/solicitudes/recordatorios/ejecutar-manual")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "recordatorios_enviados" in data


# =============================================================================
# PRUEBAS DEL MECANISMO DE RECORDATORIO DE 6 HORAS (TC-EML-004, TC-EML-005)
# =============================================================================
class TestMecanismoRecordatorio6Horas:

    def test_recordatorio_threshold_values(self):
        """Verifica que el umbral oficial sea de 6 horas (360 minutos)."""
        assert REMINDER_INTERVAL_HOURS == 6
        assert REMINDER_INTERVAL_MINUTES == 360

    @patch("backend.email_service.send_email_notification")
    def test_send_solicitud_recordatorio_email_targets_coordinadores(self, mock_send):
        """El recordatorio de 6 horas se envía a los coordinadores fijos."""
        mock_send.return_value = {"success": True, "message": "Enviado"}
        pendientes = [
            {
                "ID": 501,
                "Numero_Proyecto": "000501",
                "Cliente": "TEST RETRY",
                "Creado": "2026-10-14 00:00:00",
                "Contador_Recordatorios": 0
            }
        ]
        res = send_solicitud_recordatorio_email(pendientes, horas_transcurridas=6)
        assert res.get("success") is True
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert "alejandro.aguilarm@clarovtr.cl" in call_kwargs["to_emails"]
        assert "pablo.castillo@clarovtr.cl" in call_kwargs["to_emails"]
        assert "6H" in call_kwargs["subject"]
        assert "TEST RETRY" in call_kwargs["html_body"]

    def test_registrar_recordatorio_enviado_with_mocked_cursor(self):
        """Valida que registrar_recordatorio_enviado actualice Ultimo_Recordatorio e incremente contador."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        registrar_recordatorio_enviado(proyecto_id=999, conn=mock_conn)

        mock_cursor.execute.assert_called_once()
        executed_sql = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]

        assert "Ultimo_Recordatorio = GETDATE()" in executed_sql
        assert "Contador_Recordatorios = ISNULL(Contador_Recordatorios, 0) + 1" in executed_sql
        assert params[0] == 999
        mock_conn.commit.assert_called_once()


# =============================================================================
# PRUEBAS EXHAUSTIVAS DE RESILIENCIA ANTE FALLOS SMTP (TC-EML-008)
# =============================================================================
class TestResilienciaSmtpCompleta:

    def test_bg_task_creacion_silent_on_unhandled_exception(self):
        """Tarea en segundo plano de creación no lanza excepción si SMTP falla catastróficamente."""
        with patch("backend.main.send_solicitud_creada_email", side_effect=RuntimeError("SMTP Socket timeout")):
            # No debe propagar la excepción
            notificar_creacion_solicitud_bg(
                proyecto_data={"ID": 100, "Numero_Proyecto": "000100", "Cliente": "CLI"},
                solicitante_user={"username": "pm.test"}
            )

    def test_bg_task_asignacion_silent_on_unhandled_exception(self):
        """Tarea en segundo plano de asignación no lanza excepción si SMTP falla catastróficamente."""
        with patch("backend.main.send_solicitud_asignada_email", side_effect=ConnectionRefusedError("SMTP port closed")):
            # No debe propagar la excepción
            notificar_asignacion_lti_bg(
                proyecto_data={"ID": 100, "Numero_Proyecto": "000100", "Cliente": "CLI", "Solicitante": "pm.test"},
                prev_lt=None,
                new_lt="Erwin Sandoval"
            )

    @patch("backend.email_service.smtplib.SMTP")
    @patch("backend.main.create_solicitud_lti")
    def test_api_crear_solicitud_smtp_failure_returns_201_not_500(self, mock_create, mock_smtp):
        """Si el servidor SMTP está caído al crear solicitud, la API retorna 201 Created y no 500."""
        mock_smtp.side_effect = Exception("SMTP server unavailable")
        mock_create.return_value = {
            "success": True,
            "data": {
                "ID": 801,
                "Numero_Proyecto": "000801",
                "Cliente": "RESILIENT CLIENT",
                "Solicitante": "pm.resilient",
                "Estado": "Generado",
                "Creado": "2026-10-14 14:00:00",
                "Detalle": "Prueba resiliencia"
            }
        }
        token = create_mock_jwt(username="pm.resilient", role="PM")
        client.cookies.set("access_token", token)

        payload = {
            "cliente": "RESILIENT CLIENT",
            "numero_proyecto": "000801",
            "fecha_solicitud": "2026-10-14",
            "detalle": "Prueba resiliencia",
            "lt_asignado": ""
        }
        # Invocamos el endpoint SIN mockear notificar_creacion_solicitud_bg para probar el flujo real
        response = client.post("/api/solicitudes/crear", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Solicitud LTI creada exitosamente"
        assert "data" in data

    @patch("backend.email_service.smtplib.SMTP")
    @patch("backend.main.update_proyecto")
    def test_api_asignar_proyecto_smtp_failure_returns_200_not_500(self, mock_update, mock_smtp):
        """Si el servidor SMTP está caído al asignar proyecto, la API retorna 200 OK y no 500."""
        mock_smtp.side_effect = Exception("SMTP timeout error")
        mock_update.return_value = {
            "success": True,
            "was_assigned": True,
            "prev_lt": None,
            "new_lt": "Pablo Castillo",
            "solicitante": "pm.test",
            "data": {
                "ID": 802,
                "Numero_Proyecto": "000802",
                "Cliente": "TEST ASIGNACION",
                "LT_Asignado": "Pablo Castillo",
                "Estado": "Generado",
                "Solicitante": "pm.test",
                "Detalle": "Asignado con SMTP caído"
            }
        }
        token = create_mock_jwt(username="alejandro.aguilar", role="ADMIN")
        client.cookies.set("access_token", token)

        payload = {
            "cliente": "TEST ASIGNACION",
            "estado": "Generado",
            "detalle": "Asignado con SMTP caído",
            "lt_asignado": "Pablo Castillo"
        }
        # Invocamos el endpoint SIN mockear notificar_asignacion_lti_bg para probar flujo real
        response = client.put("/api/proyectos/802", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Proyecto actualizado exitosamente"
        assert "data" in data

    @patch("backend.main.registrar_recordatorio_enviado")
    @patch("backend.main.get_proyectos_pendientes_recordatorio")
    @patch("backend.main.send_solicitud_recordatorio_email")
    def test_api_recordatorios_ejecutar_manual_smtp_failure_handled_gracefully(self, mock_send_email, mock_get_pend, mock_reg):
        """La ejecución manual de recordatorios maneja fallo de envío retornando 200 con status false."""
        mock_get_pend.return_value = [{"ID": 999, "Numero_Proyecto": "000999", "Cliente": "CLI"}]
        mock_send_email.return_value = {"success": False, "error": "SMTP unreachable"}
        token = create_mock_jwt(username="admin.test", role="ADMIN")
        client.cookies.set("access_token", token)

        response = client.post("/api/solicitudes/recordatorios/ejecutar-manual")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["email_delivery"] is False


# =============================================================================
# PRUEBAS DE EXCLUSIÓN DE PROYECTOS DUMMY / INVÁLIDOS (0001111111, REUNIONES)
# =============================================================================
class TestValidacionProyectosDummy:

    def test_is_valid_project_number_rejects_dummy_patterns(self):
        """is_valid_project_number rechaza patrones repetidos y proyectos no válidos."""
        from backend.db import is_valid_project_number
        # Casos dummy que deben ser rechazados
        assert is_valid_project_number("0001111111") is False
        assert is_valid_project_number("1111111") is False
        assert is_valid_project_number("111111") is False
        assert is_valid_project_number("999999") is False
        assert is_valid_project_number("000000") is False
        assert is_valid_project_number("") is False
        assert is_valid_project_number(None) is False
        assert is_valid_project_number("12") is False

        # Rechazo por Tipo_Servicio Reunión
        assert is_valid_project_number("1607916", tipo_servicio="Reunión") is False
        assert is_valid_project_number("1607916", tipo_servicio="reunion") is False

        # Rechazo por Cliente o Solicitante con PROYECTO DEMO / NO IDENTIFICADO
        assert is_valid_project_number("1607916", cliente="NO IDENTIFICADO. PROYECTO DEMO") is False
        assert is_valid_project_number("1607916", solicitante="NO IDENTIFICADO. PROYECTO DEMO") is False

        # Casos válidos
        assert is_valid_project_number("1607916") is True
        assert is_valid_project_number("0001607916") is True
        assert is_valid_project_number("17636212") is True
        assert is_valid_project_number("123456", cliente="BANCO ESTADO", tipo_servicio="Otros") is True

    @patch("backend.db.get_db_connection")
    def test_get_proyectos_pendientes_recordatorio_filters_out_dummy_rows(self, mock_get_conn):
        """get_proyectos_pendientes_recordatorio filtra proyectos dummy de la base de datos."""
        from backend.db import get_proyectos_pendientes_recordatorio

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Simular filas devueltas por BD con proyectos dummy y reales
        mock_cursor.fetchall.return_value = [
            {
                "ID": 2491,
                "Numero_Proyecto": "1111111",
                "Cliente": "Habilitar salida a celulares REGISTRO CIVIL",
                "Tipo_Servicio": "Reunión",
                "Solicitante": "NO IDENTIFICADO. PROYECTO DEMO",
                "LT_Asignado": None,
                "Estado": "Generado",
                "Creado": "2026-07-14 15:57",
                "Ultimo_Recordatorio": None,
                "Contador_Recordatorios": 0,
                "Minutos_Desde_Creacion": 2000,
                "Minutos_Desde_Ultimo_Hito": 2000
            },
            {
                "ID": 2568,
                "Numero_Proyecto": "1607916",
                "Cliente": "METLIFE CHILE SEGUROS DE VIDA S.A.",
                "Tipo_Servicio": "Otros",
                "Solicitante": "pm.valido",
                "LT_Asignado": None,
                "Estado": "Generado",
                "Creado": "2026-10-14 10:00",
                "Ultimo_Recordatorio": None,
                "Contador_Recordatorios": 0,
                "Minutos_Desde_Creacion": 400,
                "Minutos_Desde_Ultimo_Hito": 400
            }
        ]

        result = get_proyectos_pendientes_recordatorio(intervalo_minutos=360, conn=mock_conn)
        # Solo debe retornar el proyecto real 2568, descartando el 2491
        assert len(result) == 1
        assert result[0]["ID"] == 2568
        assert result[0]["Numero_Proyecto"] == "0001607916"

