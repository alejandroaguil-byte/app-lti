import os
import re
import socket
import smtplib
import mimetypes
import logging
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formatdate
from typing import Optional, List, Dict, Any, Union

from .config import get_smtp_config, SMTP_CONFIG

logger = logging.getLogger("email_service")

MAX_ATTACHMENT_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$")


def sanitize_header_value(value: Optional[str]) -> str:
    """
    Sanitiza valores de cabeceras de correo para prevenir ataques de Email Header Injection (CRLF Injection).
    Reemplaza saltos de línea y retornos de carro por espacios simples y remueve caracteres de control.
    """
    if not value:
        return ""
    # Eliminar retornos de carro, saltos de línea y caracteres nulos
    cleaned = re.sub(r"[\r\n\x00\x08\x0b\x0c]+", " ", str(value))
    return cleaned.strip()


def sanitize_attachment_filename(filename: Optional[str]) -> str:
    """
    Sanitiza de forma segura el nombre de archivo adjunto:
    - Previene Path Traversal tanto en sistemas Unix como Windows (reemplazo de barras).
    - Remueve caracteres de control, comillas y secuencias peligrosas.
    - Trunca nombres excesivamente largos preservando la extensión.
    - Provee un nombre por defecto seguro si el resultado queda vacío.
    """
    if not filename:
        return "adjunto.dat"

    # Normalizar separadores de ruta de Windows y Unix
    raw_name = str(filename).replace("\\", "/").split("/")[-1].strip()

    # Eliminar caracteres de control, comillas y caracteres no imprimibles
    cleaned_name = re.sub(r'[\r\n\x00-\x1f\x7f"\'<>:|?*]', "", raw_name).strip()

    # Si tras la limpieza quedó vacío o solo puntos, asignar nombre por defecto
    if not cleaned_name or cleaned_name in {".", "..", "..."}:
        return "adjunto.dat"

    # Truncar si es excesivamente largo (máx. 120 caracteres) preservando la extensión
    max_len = 120
    if len(cleaned_name) > max_len:
        parts = cleaned_name.rsplit(".", 1)
        if len(parts) == 2 and len(parts[1]) <= 15:
            stem, ext = parts[0], parts[1]
            stem_limit = max_len - len(ext) - 1
            cleaned_name = f"{stem[:stem_limit]}.{ext}"
        else:
            cleaned_name = cleaned_name[:max_len]

    return cleaned_name


def parse_and_validate_recipients(to_input: Union[str, List[str]]) -> List[str]:
    """
    Separa, limpia y valida los correos recibidos separados por coma o punto y coma.
    Previene inyección CRLF y valida la sintaxis estricta de cada correo.
    """
    if not to_input:
        return []

    raw_list: List[str] = []
    if isinstance(to_input, list):
        for item in to_input:
            if isinstance(item, str):
                # Rechazar / normalizar separadores
                raw_list.extend(item.replace(";", ",").split(","))
    elif isinstance(to_input, str):
        raw_list = to_input.replace(";", ",").split(",")
    else:
        return []

    cleaned: List[str] = []
    for item in raw_list:
        if not isinstance(item, str):
            continue
        # Descartar si contiene caracteres CRLF o de control
        if any(c in item for c in ("\r", "\n", "\x00", "\t")):
            # Limpiar CRLF si estuvieran en los extremos
            item = item.replace("\r", "").replace("\n", "").replace("\x00", "")

        email = item.strip()
        if not email:
            continue

        if EMAIL_REGEX.match(email):
            if email not in cleaned:
                cleaned.append(email)

    return cleaned


DEV_SUBJECT_PREFIX = "[DEV] "


def is_email_redirect_active() -> bool:
    """True si este servidor opera con EMAIL_REDIRECT_TO definido (ambiente no productivo)."""
    return bool((os.getenv("EMAIL_REDIRECT_TO") or "").strip())


def apply_email_redirect(
    to_addrs: List[str],
    cc_addrs: List[str],
    bcc_addrs: List[str],
    subject: str,
) -> tuple:
    """
    Ambientes no productivos: si EMAIL_REDIRECT_TO está definido, todo correo va solo a esa(s)
    dirección(es), sin CC/BCC y con prefijo [DEV]. Sin la variable, retorna los valores intactos.
    Un valor inválido bloquea el envío para nunca caer a los destinatarios reales.
    """
    raw_redirect = (os.getenv("EMAIL_REDIRECT_TO") or "").strip()
    if not raw_redirect:
        return to_addrs, cc_addrs, bcc_addrs, subject

    redirect_addrs = parse_and_validate_recipients(raw_redirect)
    if not redirect_addrs:
        raise ValueError(
            "EMAIL_REDIRECT_TO está definido pero no contiene correos válidos; envío bloqueado."
        )

    logger.warning(
        f"EMAIL_REDIRECT_TO activo: '{subject}' redirigido a {redirect_addrs} "
        f"(originales To={to_addrs}, CC={cc_addrs}, BCC={bcc_addrs})"
    )
    if not subject.startswith(DEV_SUBJECT_PREFIX.strip()):
        subject = f"{DEV_SUBJECT_PREFIX}{subject}"
    return redirect_addrs, [], [], subject


def build_mime_message(
    from_addr: str,
    to_addrs: List[str],
    subject: str,
    body: str,
    attachment_bytes: Optional[bytes] = None,
    attachment_filename: Optional[str] = None,
    attachment_content_type: Optional[str] = None,
    html_body: Optional[str] = None,
    cc_addrs: Optional[List[str]] = None,
) -> MIMEMultipart:
    """
    Construye un mensaje MIME multipart ('mixed') con texto plano, HTML alternativo, cabecera Cc y adjunto opcional.
    Aplica sanitización estricta de cabeceras y nombres de archivos.
    """
    clean_from = sanitize_header_value(from_addr)
    clean_recipients = [sanitize_header_value(r) for r in to_addrs if sanitize_header_value(r)]
    clean_subject = sanitize_header_value(subject)
    clean_cc = [sanitize_header_value(c) for c in (cc_addrs or []) if sanitize_header_value(c)]

    msg = MIMEMultipart("mixed")
    msg["From"] = clean_from
    msg["To"] = ", ".join(clean_recipients)
    if clean_cc:
        msg["Cc"] = ", ".join(clean_cc)
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = clean_subject

    # Contenido del cuerpo: si hay HTML, se usa estructura alternative (text/plain + text/html)
    if html_body:
        alt_part = MIMEMultipart("alternative")
        if body:
            alt_part.attach(MIMEText(body, "plain", "utf-8"))
        alt_part.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(alt_part)
    else:
        body_part = MIMEText(body or "", "plain", "utf-8")
        msg.attach(body_part)

    # Adjuntar archivo si existe
    if attachment_bytes and attachment_filename:
        safe_filename = sanitize_attachment_filename(attachment_filename)
        mime_type = attachment_content_type
        if not mime_type or "/" not in mime_type:
            mime_type, _ = mimetypes.guess_type(safe_filename)
            if not mime_type:
                mime_type = "application/octet-stream"

        maintype, subtype = mime_type.split("/", 1)
        part = MIMEBase(maintype, subtype)
        part.set_payload(attachment_bytes)
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{safe_filename}"'
        )
        msg.attach(part)

    return msg



def send_ticket_notification_email(
    to_email: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    attachment_bytes: Optional[bytes] = None,
    attachment_filename: Optional[str] = None,
    ticket_id: Optional[str] = None,
    peticion_id: Optional[str] = None,
    attachment_content_type: Optional[str] = None,
    to_emails: Optional[Union[str, List[str]]] = None,
    para: Optional[str] = None,
    asunto: Optional[str] = None,
    cuerpo: Optional[str] = None,
    adjunto_bytes: Optional[bytes] = None,
    adjunto_nombre: Optional[str] = None,
    smtp_config_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Envía un correo electrónico a través de SMTP Office 365 con STARTTLS y soporte para adjuntos.
    Retorna un diccionario estructurado de resultado o lanza excepciones controladas.
    """
    # 1. Cargar y resolver configuración SMTP
    config = smtp_config_override or get_smtp_config()
    smtp_host = config.get('host', 'smtp.office365.com')
    smtp_port = int(config.get('port', 587))
    smtp_user = config.get('user', '')
    smtp_pass = config.get('password', '')
    smtp_from = config.get('from_email') or smtp_user
    smtp_timeout = int(config.get('timeout', 30))

    # 2. Validar que el servicio esté configurado
    if not smtp_user or not smtp_pass:
        raise ValueError(
            "El servicio de correo no está configurado. Verifique que las variables "
            "SMTP_USER y SMTP_PASS estén definidas en el archivo .env del servidor."
        )

    # 3. Resolver y validar parámetros
    target_recipients_raw = to_email or to_emails or para
    if not target_recipients_raw:
        raise ValueError("La dirección de destinatario es requerida y no puede estar vacía.")

    recipients = parse_and_validate_recipients(target_recipients_raw)
    if not recipients:
        raise ValueError(f"La dirección de destinatario ingresada no es válida: '{target_recipients_raw}'")

    final_subject = (subject or asunto or '').strip()
    if not final_subject:
        raise ValueError("El asunto del correo no puede estar vacío.")

    final_body = (body or cuerpo or '').strip()
    if not final_body:
        raise ValueError("El cuerpo del correo no puede estar vacío.")

    final_att_bytes = attachment_bytes if attachment_bytes is not None else adjunto_bytes
    final_att_name = attachment_filename or adjunto_nombre

    recipients, _cc, _bcc, final_subject = apply_email_redirect(recipients, [], [], final_subject)

    # 4. Validar tamaño del archivo adjunto
    if final_att_bytes and len(final_att_bytes) > MAX_ATTACHMENT_SIZE_BYTES:
        raise ValueError(
            f"El archivo adjunto supera el tamaño máximo permitido de "
            f"{MAX_ATTACHMENT_SIZE_BYTES // (1024 * 1024)} MB."
        )

    # 5. Construir Mensaje MIME
    msg = build_mime_message(
        from_addr=smtp_from,
        to_addrs=recipients,
        subject=final_subject,
        body=final_body,
        attachment_bytes=final_att_bytes,
        attachment_filename=final_att_name,
        attachment_content_type=attachment_content_type,
    )

    has_attachment = bool(final_att_bytes and final_att_name)
    safe_filename = sanitize_attachment_filename(final_att_name) if has_attachment else None

    # 6. Conexión y Envío SMTP Office 365 con STARTTLS
    server = None
    try:
        logger.info(f"Conectando a servidor SMTP {smtp_host}:{smtp_port} (timeout={smtp_timeout}s)...")
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=smtp_timeout)
        server.ehlo()

        logger.info("Iniciando negociación STARTTLS...")
        server.starttls()
        server.ehlo()

        logger.info(f"Autenticando usuario SMTP '{smtp_user}'...")
        server.login(smtp_user, smtp_pass)

        logger.info(f"Enviando correo a {recipients}...")
        server.sendmail(smtp_from, recipients, msg.as_string())
        logger.info("¡Correo enviado exitosamente!")

        now_iso = datetime.now(timezone.utc).isoformat()
        return {
            "success": True,
            "message": f"Correo enviado exitosamente a {', '.join(recipients)}",
            "data": {
                "recipients": recipients,
                "subject": final_subject,
                "ticket_id": ticket_id,
                "peticion_id": peticion_id,
                "has_attachment": has_attachment,
                "attachment_name": safe_filename,
                "sent_at": now_iso,
            },
            "recipients": recipients,
            "subject": final_subject,
            "ticket_id": ticket_id,
            "peticion_id": peticion_id,
            "has_attachment": has_attachment,
            "attachment_name": safe_filename,
            "sent_at": now_iso,
        }

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"Error de autenticación SMTP: {e}")
        raise PermissionError(
            f"Fallo de autenticación con el servidor SMTP de Office 365 ({smtp_host}). "
            "Verifique usuario y contraseña en el archivo .env."
        ) from e
    except smtplib.SMTPRecipientsRefused as e:
        logger.error(f"Destinatario rechazado por el servidor: {e}")
        raise ValueError(f"El servidor SMTP rechazó los destinatarios: {e}") from e
    except (socket.timeout, TimeoutError, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected) as e:
        logger.error(f"Error de conexión SMTP / Timeout: {e}")
        raise ConnectionError(
            f"No se pudo establecer conexión con el servidor SMTP ({smtp_host}:{smtp_port}). "
            f"Detalle: {e}"
        ) from e
    except ValueError:
        raise
    except PermissionError:
        raise
    except ConnectionError:
        raise
    except Exception as e:
        logger.error(f"Error inesperado al enviar correo: {e}")
        raise RuntimeError(f"Ocurrió un error inesperado al enviar el correo: {e}") from e
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                try:
                    server.close()
                except Exception:
                    pass


# =============================================================================
# MÓDULO SOLICITUD LTI: NOTIFICACIONES, RECORDATORIOS Y PLANTILLAS HALO
# =============================================================================

PORTAL_BASE_URL = os.getenv("PORTAL_BASE_URL", "https://200.14.222.162").rstrip("/")
_COORDINADORES_DEFAULT = "alejandro.aguilarm@clarovtr.cl,pablo.castillo@clarovtr.cl"
COORDINADORES_LTI_RAW = os.getenv("COORDINADORES_LTI_EMAILS", _COORDINADORES_DEFAULT)
COORDINADORES_LTI_EMAILS = [e.strip() for e in COORDINADORES_LTI_RAW.split(",") if e.strip()]


def send_email_notification(
    to_emails: Union[str, List[str]],
    subject: str,
    html_body: Optional[str] = None,
    text_body: Optional[str] = None,
    cc_emails: Optional[Union[str, List[str]]] = None,
    bcc_emails: Optional[Union[str, List[str]]] = None,
    attachment_bytes: Optional[bytes] = None,
    attachment_filename: Optional[str] = None,
    attachment_content_type: Optional[str] = None,
    smtp_config_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Envía un correo electrónico con soporte para To, CC, BCC, HTML y texto plano multipart/alternative.
    Aplica STARTTLS sobre Microsoft Office 365 y sanitización contra Email Header Injection.
    """
    import html as html_lib

    # 1. Configuración SMTP
    config = smtp_config_override or get_smtp_config()
    smtp_host = config.get('host', 'smtp.office365.com')
    smtp_port = int(config.get('port', 587))
    smtp_user = config.get('user', '')
    smtp_pass = config.get('password', '')
    smtp_from = config.get('from_email') or smtp_user
    smtp_timeout = int(config.get('timeout', 30))

    if not smtp_user or not smtp_pass:
        raise ValueError(
            "El servicio de correo no está configurado (SMTP_USER y SMTP_PASS no definidos)."
        )

    # 2. Destinatarios To, CC y BCC
    clean_to = parse_and_validate_recipients(to_emails)
    if not clean_to:
        raise ValueError(f"Destinatario(s) inválido(s) o vacío(s): {to_emails}")

    clean_cc = parse_and_validate_recipients(cc_emails) if cc_emails else []
    clean_bcc = parse_and_validate_recipients(bcc_emails) if bcc_emails else []

    # 3. Asunto y Cuerpos
    clean_subject = (subject or "").strip()
    if not clean_subject:
        raise ValueError("El asunto del correo no puede estar vacío.")

    final_text = (text_body or "").strip()
    final_html = (html_body or "").strip()
    if not final_text and not final_html:
        raise ValueError("El cuerpo del correo no puede estar completamente vacío.")

    # Si falta texto plano, crear fallback básico
    if not final_text and final_html:
        final_text = re.sub(r"<[^>]+>", " ", final_html).strip()

    clean_to, clean_cc, clean_bcc, clean_subject = apply_email_redirect(
        clean_to, clean_cc, clean_bcc, clean_subject
    )

    # 4. Validar adjunto si existe
    if attachment_bytes and len(attachment_bytes) > MAX_ATTACHMENT_SIZE_BYTES:
        raise ValueError(
            f"El archivo adjunto supera el tamaño máximo de {MAX_ATTACHMENT_SIZE_BYTES // (1024 * 1024)} MB."
        )

    # 5. Construcción del mensaje MIME (BCC no se incluye en las cabeceras para mantenerlo oculto)
    msg = build_mime_message(
        from_addr=smtp_from,
        to_addrs=clean_to,
        subject=clean_subject,
        body=final_text,
        attachment_bytes=attachment_bytes,
        attachment_filename=attachment_filename,
        attachment_content_type=attachment_content_type,
        html_body=final_html if final_html else None,
        cc_addrs=clean_cc if clean_cc else None,
    )

    # 6. Envío SMTP en sobre a To + CC + BCC
    envelope_recipients = list(dict.fromkeys(clean_to + clean_cc + clean_bcc))
    server = None
    try:
        logger.info(f"Conectando a SMTP {smtp_host}:{smtp_port} para enviar '{clean_subject}'...")
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=smtp_timeout)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_from, envelope_recipients, msg.as_string())
        logger.info(f"Correo enviado exitosamente a To={clean_to}, CC={clean_cc}, BCC={clean_bcc}")

        now_iso = datetime.now(timezone.utc).isoformat()
        return {
            "success": True,
            "message": f"Correo enviado exitosamente a {', '.join(clean_to)}",
            "data": {
                "to": clean_to,
                "cc": clean_cc,
                "bcc": clean_bcc,
                "subject": clean_subject,
                "sent_at": now_iso,
            }
        }
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"Error de autenticación SMTP: {e}")
        raise PermissionError(f"Fallo de autenticación con el servidor SMTP ({smtp_host}): {e}") from e
    except (socket.timeout, TimeoutError, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected) as e:
        logger.error(f"Error de conexión SMTP / Timeout: {e}")
        raise ConnectionError(f"Error conectando con servidor SMTP ({smtp_host}:{smtp_port}): {e}") from e
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                try:
                    server.close()
                except Exception:
                    pass


# -----------------------------------------------------------------------------
# PLANTILLAS HTML HALO DESIGN SYSTEM
# -----------------------------------------------------------------------------

def _format_cell(label: str, value: Any, is_last: bool = False) -> str:
    import html as h
    val_str = h.escape(str(value if value is not None else "-"))
    lbl_str = h.escape(str(label))
    border_style = "" if is_last else "border-bottom: 1px solid #E2E8F0;"
    return f"""
    <tr>
        <td style="padding: 10px 14px; font-weight: 600; color: #475569; width: 35%; {border_style} background: #F8FAFC; font-size: 13px;">{lbl_str}</td>
        <td style="padding: 10px 14px; color: #1E293B; {border_style} font-size: 14px;">{val_str}</td>
    </tr>
    """


def build_solicitud_creada_email_html(proyecto_data: dict, solicitante_nombre: Optional[str] = None) -> str:
    """Genera la plantilla HTML corporativa HALO para notificar una nueva solicitud LTI ingresada."""
    import html as h

    num_proy = h.escape(str(proyecto_data.get("Numero_Proyecto") or "-"))
    cliente = h.escape(str(proyecto_data.get("Cliente") or "-"))
    solicitante = h.escape(str(solicitante_nombre or proyecto_data.get("Solicitante") or "-"))
    fecha_sol = h.escape(str(proyecto_data.get("Creado") or datetime.now().strftime("%Y-%m-%d %H:%M")))
    detalle = h.escape(str(proyecto_data.get("Detalle") or "(Sin detalle especificado)"))
    cta_url = f"{PORTAL_BASE_URL}/app-lti/"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Nueva Solicitud LTI</title>
</head>
<body style="margin: 0; padding: 0; background-color: #F4F5F7; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1E293B;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #F4F5F7; padding: 24px 0;">
        <tr>
            <td align="center">
                <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #FFFFFF; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border: 1px solid #E2E8F0;">
                    <!-- Cabecera Institucional HALO -->
                    <tr>
                        <td style="background-color: #B52217; padding: 24px 28px; text-align: left; border-top: 4px solid #0097A9;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td>
                                        <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; color: #FFFFFF; opacity: 0.85; font-weight: 700;">HALO • Seguimiento Líderes TI</div>
                                        <div style="font-size: 20px; font-weight: 700; color: #FFFFFF; margin-top: 4px;">Nueva Solicitud de Proyecto Ingresada</div>
                                        <div style="font-size: 13px; color: #FDEDEA; margin-top: 2px;">Se requiere asignación de Líder Técnico</div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Banner de Alerta Informativa -->
                    <tr>
                        <td style="padding: 20px 28px 10px 28px;">
                            <div style="background-color: #FDEDEA; border-left: 4px solid #DA291C; padding: 12px 16px; border-radius: 4px; font-size: 14px; color: #B52217; font-weight: 500;">
                                📢 <strong>Atención Coordinadores:</strong> Se ha registrado un nuevo requerimiento de proyecto esperando asignación de Líder Técnico.
                            </div>
                        </td>
                    </tr>

                    <!-- Atributos Clave del Proyecto -->
                    <tr>
                        <td style="padding: 10px 28px 16px 28px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: collapse; border: 1px solid #E2E8F0; border-radius: 6px; overflow: hidden;">
                                <tr>
                                    <td style="padding: 10px 14px; font-weight: 600; color: #475569; width: 35%; border-bottom: 1px solid #E2E8F0; background: #F8FAFC; font-size: 13px;">N° de Proyecto:</td>
                                    <td style="padding: 10px 14px; color: #1E293B; border-bottom: 1px solid #E2E8F0; font-size: 14px; font-weight: 700; color: #B52217;">{num_proy}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 14px; font-weight: 600; color: #475569; border-bottom: 1px solid #E2E8F0; background: #F8FAFC; font-size: 13px;">Cliente:</td>
                                    <td style="padding: 10px 14px; color: #1E293B; border-bottom: 1px solid #E2E8F0; font-size: 14px; font-weight: 600;">{cliente}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 14px; font-weight: 600; color: #475569; border-bottom: 1px solid #E2E8F0; background: #F8FAFC; font-size: 13px;">Solicitante (PM):</td>
                                    <td style="padding: 10px 14px; color: #1E293B; border-bottom: 1px solid #E2E8F0; font-size: 14px;">{solicitante}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 14px; font-weight: 600; color: #475569; border-bottom: 1px solid #E2E8F0; background: #F8FAFC; font-size: 13px;">Fecha de Solicitud:</td>
                                    <td style="padding: 10px 14px; color: #1E293B; border-bottom: 1px solid #E2E8F0; font-size: 14px;">{fecha_sol}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 14px; font-weight: 600; color: #475569; border-bottom: 1px solid #E2E8F0; background: #F8FAFC; font-size: 13px;">Estado Inicial:</td>
                                    <td style="padding: 10px 14px; color: #1E293B; border-bottom: 1px solid #E2E8F0; font-size: 14px;">
                                        <span style="background-color: #FEF3C7; color: #92400E; padding: 3px 8px; border-radius: 4px; font-weight: 700; font-size: 12px; display: inline-block;">Generado</span>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 14px; font-weight: 600; color: #475569; background: #F8FAFC; font-size: 13px;">Tipo de Servicio:</td>
                                    <td style="padding: 10px 14px; color: #1E293B; font-size: 14px;">Otros</td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Detalle Técnico / Solots Liray -->
                    <tr>
                        <td style="padding: 0 28px 20px 28px;">
                            <div style="font-size: 13px; font-weight: 700; color: #475569; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px;">Detalle del Requerimiento / Solots Liray:</div>
                            <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 4px; padding: 12px 14px; font-family: 'Consolas', 'Courier New', monospace; font-size: 13px; line-height: 1.5; color: #334155; white-space: pre-wrap; word-break: break-word;">{detalle}</div>
                        </td>
                    </tr>

                    <!-- Botón de Llamada a la Acción (CTA) -->
                    <tr>
                        <td align="center" style="padding: 10px 28px 28px 28px;">
                            <a href="{cta_url}" target="_blank" style="background-color: #B52217; color: #FFFFFF; font-size: 14px; font-weight: 700; text-decoration: none; padding: 12px 28px; border-radius: 6px; display: inline-block; box-shadow: 0 2px 4px rgba(181, 34, 23, 0.3);">
                                Acceder a App LTI y Asignar Proyecto &rarr;
                            </a>
                        </td>
                    </tr>

                    <!-- Footer Corporativo -->
                    <tr>
                        <td style="background-color: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 16px 28px; text-align: center; font-size: 12px; color: #64748B;">
                            <div>Este correo fue generado automáticamente por <strong>Portal HALO ClaroVTR — PCDI</strong>.</div>
                            <div style="margin-top: 4px;">Por favor, no responda directamente a este remitente desatendido.</div>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""


def build_solicitud_recordatorio_email_html(
    pendientes: Union[dict, List[dict]],
    horas_transcurridas: int = 6,
    recordatorio_num: int = 1
) -> str:
    """Genera la plantilla HTML corporativa HALO para el recordatorio periódico de proyectos sin asignar."""
    import html as h
    cta_url = f"{PORTAL_BASE_URL}/app-lti/"

    # Normalizar a lista de proyectos
    items = [pendientes] if isinstance(pendientes, dict) else list(pendientes)
    total_count = len(items)

    filas_html = []
    for p in items:
        p_num = h.escape(str(p.get("Numero_Proyecto") or "-"))
        p_cli = h.escape(str(p.get("Cliente") or "-"))
        p_pm = h.escape(str(p.get("Solicitante") or "-"))
        p_creado = h.escape(str(p.get("Creado") or "-")[:16])
        p_cont = int(p.get("Contador_Recordatorios") or 0) + 1
        p_mins = p.get("Minutos_Desde_Creacion")
        horas_calc = round(p_mins / 60, 1) if p_mins else horas_transcurridas

        filas_html.append(f"""
        <tr>
            <td style="padding: 10px 12px; border-bottom: 1px solid #E2E8F0; font-weight: 700; color: #B52217; font-size: 13px;">{p_num}</td>
            <td style="padding: 10px 12px; border-bottom: 1px solid #E2E8F0; color: #1E293B; font-size: 13px;">{p_cli}</td>
            <td style="padding: 10px 12px; border-bottom: 1px solid #E2E8F0; color: #475569; font-size: 13px;">{p_pm}</td>
            <td style="padding: 10px 12px; border-bottom: 1px solid #E2E8F0; color: #64748B; font-size: 12px;">{p_creado} ({horas_calc}h)</td>
            <td align="center" style="padding: 10px 12px; border-bottom: 1px solid #E2E8F0; font-size: 12px;">
                <span style="background-color: #FDEDEA; color: #DA291C; padding: 2px 6px; border-radius: 4px; font-weight: 700;">#{p_cont}</span>
            </td>
        </tr>
        """)

    filas_str = "\n".join(filas_html)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Recordatorio Solicitudes LTI Pendientes</title>
</head>
<body style="margin: 0; padding: 0; background-color: #F4F5F7; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1E293B;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #F4F5F7; padding: 24px 0;">
        <tr>
            <td align="center">
                <table border="0" cellpadding="0" cellspacing="0" width="650" style="background-color: #FFFFFF; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border: 1px solid #E2E8F0;">
                    <!-- Cabecera Institucional HALO con acento Teal -->
                    <tr>
                        <td style="background-color: #B52217; padding: 22px 28px; text-align: left; border-top: 4px solid #0097A9;">
                            <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; color: #FFFFFF; opacity: 0.85; font-weight: 700;">HALO • Alertas Operativas</div>
                            <div style="font-size: 20px; font-weight: 700; color: #FFFFFF; margin-top: 4px;">⏰ Recordatorio: Solicitudes LTI Sin Asignar</div>
                            <div style="font-size: 13px; color: #FDEDEA; margin-top: 2px;">{total_count} solicitud(es) pendiente(s) superando el umbral de {horas_transcurridas} horas</div>
                        </td>
                    </tr>

                    <!-- Banner de Alerta -->
                    <tr>
                        <td style="padding: 20px 28px 12px 28px;">
                            <div style="background-color: #FFFBEB; border-left: 4px solid #F59E0B; padding: 12px 16px; border-radius: 4px; font-size: 14px; color: #92400E; font-weight: 500;">
                                ⚠️ <strong>Recordatorio de Asignación:</strong> Las siguientes solicitudes de proyecto han cumplido <strong>&ge; {horas_transcurridas} horas</strong> desde su ingreso o último recordatorio sin registrar un Líder Técnico asignado.
                            </div>
                        </td>
                    </tr>

                    <!-- Tabla de Proyectos Pendientes -->
                    <tr>
                        <td style="padding: 10px 28px 20px 28px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: collapse; border: 1px solid #E2E8F0; border-radius: 6px; overflow: hidden;">
                                <tr style="background-color: #F8FAFC;">
                                    <th align="left" style="padding: 10px 12px; font-size: 12px; font-weight: 700; color: #475569; border-bottom: 2px solid #E2E8F0;">N° PROYECTO</th>
                                    <th align="left" style="padding: 10px 12px; font-size: 12px; font-weight: 700; color: #475569; border-bottom: 2px solid #E2E8F0;">CLIENTE</th>
                                    <th align="left" style="padding: 10px 12px; font-size: 12px; font-weight: 700; color: #475569; border-bottom: 2px solid #E2E8F0;">SOLICITANTE</th>
                                    <th align="left" style="padding: 10px 12px; font-size: 12px; font-weight: 700; color: #475569; border-bottom: 2px solid #E2E8F0;">INGRESO</th>
                                    <th align="center" style="padding: 10px 12px; font-size: 12px; font-weight: 700; color: #475569; border-bottom: 2px solid #E2E8F0;">AVISO</th>
                                </tr>
                                {filas_str}
                            </table>
                        </td>
                    </tr>

                    <!-- Botón CTA -->
                    <tr>
                        <td align="center" style="padding: 6px 28px 26px 28px;">
                            <a href="{cta_url}" target="_blank" style="background-color: #B52217; color: #FFFFFF; font-size: 14px; font-weight: 700; text-decoration: none; padding: 12px 28px; border-radius: 6px; display: inline-block; box-shadow: 0 2px 4px rgba(181, 34, 23, 0.3);">
                                Ingresar a App LTI y Asignar Líderes &rarr;
                            </a>
                        </td>
                    </tr>

                    <!-- Footer Corporativo -->
                    <tr>
                        <td style="background-color: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 16px 28px; text-align: center; font-size: 12px; color: #64748B;">
                            <div>Este recordatorio se emite automáticamente cada 6 horas hasta que cada requerimiento cuente con Líder Técnico.</div>
                            <div style="margin-top: 4px;">Plataforma HALO ClaroVTR • PCDI • Gestión y Asignación de Solicitudes LTI.</div>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""


def build_solicitud_asignada_email_html(
    proyecto_data: dict,
    lt_nombre: Optional[str] = None,
    solicitante_nombre: Optional[str] = None
) -> str:
    """Genera la plantilla HTML corporativa HALO para notificar al PM solicitante la asignación de su LTI (con CC al LTI)."""
    import html as h

    num_proy = h.escape(str(proyecto_data.get("Numero_Proyecto") or "-"))
    cliente = h.escape(str(proyecto_data.get("Cliente") or "-"))
    solicitante = h.escape(str(solicitante_nombre or proyecto_data.get("Solicitante") or "Estimado(a) PM"))
    lt_asignado = h.escape(str(lt_nombre or proyecto_data.get("LT_Asignado") or "Líder Técnico Asignado"))
    estado = h.escape(str(proyecto_data.get("Estado") or "Generado"))
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    cta_url = f"{PORTAL_BASE_URL}/app-lti/"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Líder Técnico Asignado</title>
</head>
<body style="margin: 0; padding: 0; background-color: #F4F5F7; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1E293B;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #F4F5F7; padding: 24px 0;">
        <tr>
            <td align="center">
                <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #FFFFFF; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border: 1px solid #E2E8F0;">
                    <!-- Cabecera Institucional HALO -->
                    <tr>
                        <td style="background-color: #B52217; padding: 24px 28px; text-align: left; border-top: 4px solid #0097A9;">
                            <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; color: #FFFFFF; opacity: 0.85; font-weight: 700;">HALO • Seguimiento Líderes TI</div>
                            <div style="font-size: 20px; font-weight: 700; color: #FFFFFF; margin-top: 4px;">✅ Líder Técnico Asignado Exitosamente</div>
                            <div style="font-size: 13px; color: #FDEDEA; margin-top: 2px;">Su solicitud de proyecto ha entrado en fase de gestión técnica</div>
                        </td>
                    </tr>

                    <!-- Banner de Éxito / Felicitación -->
                    <tr>
                        <td style="padding: 20px 28px 12px 28px;">
                            <div style="background-color: #ECFDF5; border-left: 4px solid #10B981; padding: 14px 16px; border-radius: 4px; font-size: 14px; color: #065F46; line-height: 1.5;">
                                Estimado(a) <strong>{solicitante}</strong>:<br>
                                Le informamos que su solicitud para el proyecto <strong>{num_proy}</strong> ({cliente}) ha sido asignada formalmente al Líder Técnico <strong>{lt_asignado}</strong>, quien coordinará las actividades y gestiones técnicas requeridas.
                            </div>
                        </td>
                    </tr>

                    <!-- Ficha Resumen de Asignación -->
                    <tr>
                        <td style="padding: 10px 28px 20px 28px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: collapse; border: 1px solid #E2E8F0; border-radius: 6px; overflow: hidden;">
                                <tr>
                                    <td style="padding: 12px 14px; font-weight: 600; color: #475569; width: 38%; border-bottom: 1px solid #E2E8F0; background: #F8FAFC; font-size: 13px;">Líder Técnico Responsable:</td>
                                    <td style="padding: 12px 14px; border-bottom: 1px solid #E2E8F0; font-size: 15px; font-weight: 700; color: #0097A9;">
                                        <span style="background-color: #E6FFFA; color: #0097A9; border: 1px solid #0097A9; padding: 4px 10px; border-radius: 4px; display: inline-block;">👤 {lt_asignado}</span>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 14px; font-weight: 600; color: #475569; border-bottom: 1px solid #E2E8F0; background: #F8FAFC; font-size: 13px;">N° de Proyecto:</td>
                                    <td style="padding: 10px 14px; color: #1E293B; border-bottom: 1px solid #E2E8F0; font-size: 14px; font-weight: 700; color: #B52217;">{num_proy}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 14px; font-weight: 600; color: #475569; border-bottom: 1px solid #E2E8F0; background: #F8FAFC; font-size: 13px;">Cliente:</td>
                                    <td style="padding: 10px 14px; color: #1E293B; border-bottom: 1px solid #E2E8F0; font-size: 14px; font-weight: 600;">{cliente}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 14px; font-weight: 600; color: #475569; border-bottom: 1px solid #E2E8F0; background: #F8FAFC; font-size: 13px;">Estado:</td>
                                    <td style="padding: 10px 14px; color: #1E293B; border-bottom: 1px solid #E2E8F0; font-size: 14px;">
                                        <span style="background-color: #E0E7FF; color: #3730A3; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 12px;">{estado}</span>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 14px; font-weight: 600; color: #475569; background: #F8FAFC; font-size: 13px;">Fecha de Asignación:</td>
                                    <td style="padding: 10px 14px; color: #64748B; font-size: 13px;">{now_str}</td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Botón CTA -->
                    <tr>
                        <td align="center" style="padding: 6px 28px 26px 28px;">
                            <a href="{cta_url}" target="_blank" style="background-color: #B52217; color: #FFFFFF; font-size: 14px; font-weight: 700; text-decoration: none; padding: 12px 28px; border-radius: 6px; display: inline-block; box-shadow: 0 2px 4px rgba(181, 34, 23, 0.3);">
                                Ver Proyecto en App LTI &rarr;
                            </a>
                        </td>
                    </tr>

                    <!-- Footer Corporativo -->
                    <tr>
                        <td style="background-color: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 16px 28px; text-align: center; font-size: 12px; color: #64748B;">
                            <div>Este correo fue despachado al PM solicitante con copia (CC) al Líder Técnico asignado.</div>
                            <div style="margin-top: 4px;">Suite HALO ClaroVTR • PCDI • Gestión Integrada de Proyectos TI.</div>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""


# Alias para compatibilidad de nomenclatura en Specs
generate_solicitud_creada_html = build_solicitud_creada_email_html
generate_recordatorio_6h_html = build_solicitud_recordatorio_email_html
generate_asignacion_lti_html = build_solicitud_asignada_email_html


# -----------------------------------------------------------------------------
# FUNCIONES DESPACHADORAS DE CORREO (RESILIENTES Y SIN BLOQUEO)
# -----------------------------------------------------------------------------

def is_test_project_number(numero_proyecto: Any) -> bool:
    """True si el N° de proyecto corresponde a datos de prueba (contiene 'QA' o 'TEST')."""
    num_upper = str(numero_proyecto or "").upper()
    return "QA" in num_upper or "TEST" in num_upper


def send_solicitud_creada_email(proyecto_data: dict, solicitante_nombre: Optional[str] = None) -> dict:
    """
    Despacha la notificación formal de ingreso de una nueva solicitud LTI a los coordinadores generales:
    - alejandro.aguilarm@clarovtr.cl
    - pablo.castillo@clarovtr.cl
    Captura excepciones para no romper la transacción ni el flujo del usuario.
    Los proyectos de prueba (N° con 'QA' o 'TEST') no se notifican en ningún ambiente.
    """
    try:
        num = proyecto_data.get("Numero_Proyecto") or "S/N"
        if is_test_project_number(num):
            logger.info(f"Notificación de creación omitida para proyecto de prueba {num}.")
            return {"success": False, "skipped": True, "error": "Proyecto de prueba (QA/TEST): notificación omitida"}

        cli = proyecto_data.get("Cliente") or "CLIENTE"
        asunto = f"[HALO LTI] Nueva Solicitud de Proyecto Ingresada — Proyecto N° {num} ({cli})"

        html_body = build_solicitud_creada_email_html(proyecto_data, solicitante_nombre=solicitante_nombre)
        pm_name = solicitante_nombre or proyecto_data.get("Solicitante") or "PM"
        text_body = (
            f"HALO LTI - Nueva Solicitud de Proyecto Ingresada\n\n"
            f"N° Proyecto: {num}\n"
            f"Cliente: {cli}\n"
            f"Solicitante: {pm_name}\n"
            f"Fecha: {proyecto_data.get('Creado')}\n"
            f"Estado: Generado\n"
            f"Tipo Servicio: Otros\n\n"
            f"Detalle:\n{proyecto_data.get('Detalle')}\n\n"
            f"Acceder a App LTI: {PORTAL_BASE_URL}/app-lti/\n"
        )

        result = send_email_notification(
            to_emails=COORDINADORES_LTI_EMAILS,
            subject=asunto,
            html_body=html_body,
            text_body=text_body,
        )
        logger.info(f"Notificación de creación enviada exitosamente para proyecto {num}.")
        return result
    except Exception as e:
        logger.error(f"Error al enviar notificación de creación para proyecto {proyecto_data.get('ID')}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def send_solicitud_recordatorio_email(
    pendientes: Union[dict, List[dict]],
    horas_transcurridas: int = 6
) -> dict:
    """
    Despacha el correo de recordatorio periódico a los coordinadores generales.
    Soporta lista consolidada de proyectos o proyecto único.
    """
    try:
        items = [pendientes] if isinstance(pendientes, dict) else list(pendientes)
        # Los proyectos de prueba (N° con 'QA' o 'TEST') no se notifican en ningún ambiente
        items = [p for p in items if not is_test_project_number(p.get("Numero_Proyecto"))]
        if not items:
            return {"success": True, "message": "No hay proyectos pendientes para notificar."}

        if len(items) == 1:
            num = items[0].get("Numero_Proyecto") or "S/N"
            cli = items[0].get("Cliente") or "CLIENTE"
            asunto = f"[RECORDATORIO {horas_transcurridas}H] Solicitud LTI Pendiente de Asignación — Proyecto N° {num} ({cli})"
        else:
            asunto = f"[RECORDATORIO {horas_transcurridas}H] {len(items)} Solicitudes LTI Pendientes de Asignación"

        html_body = build_solicitud_recordatorio_email_html(items, horas_transcurridas=horas_transcurridas)
        text_body = (
            f"HALO LTI - Recordatorio de Solicitudes Pendientes de Asignar ({horas_transcurridas} Horas)\n\n"
            f"Total de requerimientos esperando Líder Técnico: {len(items)}\n"
            + "\n".join([f"- N° {p.get('Numero_Proyecto')}: {p.get('Cliente')} (Solicitante: {p.get('Solicitante')})" for p in items])
            + f"\n\nAcceder a App LTI: {PORTAL_BASE_URL}/app-lti/\n"
        )

        result = send_email_notification(
            to_emails=COORDINADORES_LTI_EMAILS,
            subject=asunto,
            html_body=html_body,
            text_body=text_body,
        )
        logger.info(f"Recordatorio de {horas_transcurridas}h enviado para {len(items)} solicitudes.")
        return result
    except Exception as e:
        logger.error(f"Error al despachar recordatorio de solicitudes pendientes: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def send_solicitud_asignada_email(
    proyecto_data: dict,
    pm_email: Optional[str] = None,
    lti_email: Optional[str] = None,
    lt_nombre: Optional[str] = None
) -> dict:
    """
    Despacha la notificación formal de asignación:
    - Destinatario (Para): Email del PM Solicitante
    - Copia (CC): Email del Líder Técnico Asignado
    Resuelve los correos institucionales mediante resolve_user_email si no son provistos.
    """
    try:
        from .db import resolve_user_email

        num = proyecto_data.get("Numero_Proyecto") or "S/N"
        if is_test_project_number(num):
            logger.info(f"Notificación de asignación omitida para proyecto de prueba {num}.")
            return {"success": False, "skipped": True, "error": "Proyecto de prueba (QA/TEST): notificación omitida"}

        cli = proyecto_data.get("Cliente") or "CLIENTE"
        lt_final = lt_nombre or proyecto_data.get("LT_Asignado") or "Líder Técnico"
        pm_ident = proyecto_data.get("Solicitante")

        resolved_pm_email = pm_email or resolve_user_email(pm_ident)
        resolved_lt_email = lti_email or resolve_user_email(lt_final)

        if not resolved_pm_email:
            logger.warning(
                f"No se pudo resolver correo del PM solicitante '{pm_ident}' para proyecto {num}. "
                "Enviando notificación a coordinadores LTI como fallback."
            )
            resolved_pm_email = COORDINADORES_LTI_EMAILS[0]

        asunto = f"[HALO LTI] Líder Técnico Asignado — Proyecto N° {num} ({cli})"
        html_body = build_solicitud_asignada_email_html(
            proyecto_data=proyecto_data,
            lt_nombre=lt_final,
            solicitante_nombre=pm_ident
        )
        text_body = (
            f"HALO LTI - Líder Técnico Asignado\n\n"
            f"Estimado(a) {pm_ident}:\n"
            f"Su solicitud de proyecto ha sido asignada al Líder Técnico: {lt_final}.\n\n"
            f"N° Proyecto: {num}\n"
            f"Cliente: {cli}\n"
            f"Estado: {proyecto_data.get('Estado')}\n\n"
            f"Acceder a App LTI: {PORTAL_BASE_URL}/app-lti/\n"
        )

        cc_list = [resolved_lt_email] if (resolved_lt_email and resolved_lt_email != resolved_pm_email) else []

        result = send_email_notification(
            to_emails=resolved_pm_email,
            subject=asunto,
            html_body=html_body,
            text_body=text_body,
            cc_emails=cc_list if cc_list else None
        )
        logger.info(f"Notificación de asignación enviada para proyecto {num}: To={resolved_pm_email}, CC={cc_list}")
        return result
    except Exception as e:
        logger.error(f"Error al enviar notificación de asignación para proyecto {proyecto_data.get('ID')}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


