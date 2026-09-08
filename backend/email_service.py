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


def build_mime_message(
    from_addr: str,
    to_addrs: List[str],
    subject: str,
    body: str,
    attachment_bytes: Optional[bytes] = None,
    attachment_filename: Optional[str] = None,
    attachment_content_type: Optional[str] = None,
) -> MIMEMultipart:
    """
    Construye un mensaje MIME multipart ('mixed') con texto plano y adjunto opcional.
    Aplica sanitización estricta de cabeceras y nombres de archivos.
    """
    clean_from = sanitize_header_value(from_addr)
    clean_recipients = [sanitize_header_value(r) for r in to_addrs if sanitize_header_value(r)]
    clean_subject = sanitize_header_value(subject)

    msg = MIMEMultipart("mixed")
    msg["From"] = clean_from
    msg["To"] = ", ".join(clean_recipients)
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = clean_subject

    # Cuerpo del correo en UTF-8
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

