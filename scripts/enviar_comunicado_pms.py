#!/usr/bin/env python3
"""
Script de Difusión Oficial: Comunicado de Migración a App LTI para Project Managers (PM)
Proyecto: HALO — App Líderes TI
Uso:
    python scripts/enviar_comunicado_pms.py --test alejandro.aguilarm@clarovtr.cl
    python scripts/enviar_comunicado_pms.py --dry-run
    python scripts/enviar_comunicado_pms.py --send-all
"""

import sys
import os
import argparse
import time

# Agregar directorio raíz al PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db import get_db_connection, resolve_user_email
from backend.seed_users import read_users_from_excel
from backend.email_service import send_email_notification


def build_announcement_html(is_test: bool = False) -> str:
    test_banner = """
          <!-- Banner de Vista Previa / Prueba -->
          <tr>
            <td style="background-color: #FEF3C7; border-bottom: 2px solid #F59E0B; padding: 10px 20px; text-align: center;">
              <span style="font-size: 11px; font-weight: 800; color: #92400E; letter-spacing: 1px; text-transform: uppercase;">
                🧪 FORMATO DE PRUEBA / VISTA PREVIA PARA REVISIÓN
              </span>
              <div style="font-size: 11px; color: #B45309; margin-top: 2px;">
                Este correo es un borrador de prueba enviado para validación previa a la difusión masiva.
              </div>
            </td>
          </tr>
    """ if is_test else ""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Comunicado Oficial: Nuevo Canal para Solicitud de Líder Técnico (LTI)</title>
</head>
<body style="margin: 0; padding: 0; background-color: #F4F5F7; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; -webkit-font-smoothing: antialiased; color: #1E293B;">
  
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #F4F5F7; padding: 24px 0;">
    <tr>
      <td align="center">
        
        <!-- Contenedor Principal (máx 620px) -->
        <table width="620" cellpadding="0" cellspacing="0" border="0" style="max-width: 620px; width: 100%; background-color: #FFFFFF; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08); border: 1px solid #E2E8F0;">
          
          {test_banner}

          <!-- Cabecera Institucional HALO -->
          <tr>
            <td style="background-color: #B52217; padding: 22px 28px; border-bottom: 3px solid #0097A9;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td valign="middle">
                    <table cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td style="padding-right: 12px;">
                          <div style="width: 32px; height: 32px; background-color: #FDEDEA; border-radius: 6px; text-align: center; line-height: 32px; font-size: 18px;">
                            🎯
                          </div>
                        </td>
                        <td>
                          <div style="color: #FDEDEA; font-size: 20px; font-weight: 800; letter-spacing: 0.5px; line-height: 1.1;">
                            HALO
                          </div>
                          <div style="color: #0097A9; font-size: 12px; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; margin-top: 2px;">
                            App Líderes TI • Comunicado Oficial
                          </div>
                        </td>
                      </tr>
                    </table>
                  </td>
                  <td align="right" valign="middle">
                    <span style="background-color: rgba(253, 237, 234, 0.15); border: 1px solid rgba(253, 237, 234, 0.3); color: #FDEDEA; font-size: 11px; font-weight: 600; padding: 5px 10px; border-radius: 12px; text-transform: uppercase;">
                      Gestión de Proyectos
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Cuerpo Principal -->
          <tr>
            <td style="padding: 32px 32px 24px 32px;">
              
              <!-- Saludo y Título Principal -->
              <h1 style="color: #181B20; font-size: 20px; font-weight: 800; margin: 0 0 12px 0; line-height: 1.35;">
                Estimado(a) Project Manager (PM),
              </h1>
              <p style="color: #475569; font-size: 14px; line-height: 1.6; margin: 0 0 20px 0;">
                Nos comunicamos para informarte una importante actualización en el flujo operativo de asignación técnica para proyectos. Con el propósito de optimizar los tiempos de respuesta, garantizar trazabilidad 360° y automatizar el flujo de trabajo, se ha implementado el nuevo módulo institucional de <strong>Solicitud LTI</strong> en la plataforma <strong>HALO</strong>.
              </p>

              <!-- Alerta Destacada: Fecha Efectiva -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #FDEDEA; border-left: 4px solid #DA291C; border-radius: 4px; margin-bottom: 24px;">
                <tr>
                  <td style="padding: 16px 18px;">
                    <div style="font-size: 14px; font-weight: 800; color: #B52217; margin-bottom: 4px;">
                      📅 FECHA Y HORA DE ENTRADA EN VIGENCIA
                    </div>
                    <div style="font-size: 13px; color: #1E293B; line-height: 1.55;">
                      A contar de este <strong>Lunes a partir de las 08:30 AM</strong>, todas las peticiones de asignación de <strong>Líder Técnico de Integración (LTI)</strong> deberán realizarse <u>exclusivamente</u> a través de <strong>App LTI</strong>.<br>
                      <strong style="color: #B52217;">⚠️ El formulario histórico en SharePoint quedará inhabilitado para nuevos requerimientos.</strong>
                    </div>
                  </td>
                </tr>
              </table>

              <!-- Comparativa de Canales -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 24px; border-collapse: separate; border-spacing: 0; border: 1px solid #E2E8F0; border-radius: 6px; overflow: hidden;">
                <tr style="background-color: #F8FAFC;">
                  <th width="50%" style="padding: 10px 14px; font-size: 12px; font-weight: 700; color: #64748B; text-align: left; border-bottom: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0;">
                    🛑 CANAL ANTERIOR (CERRADO)
                  </th>
                  <th width="50%" style="padding: 10px 14px; font-size: 12px; font-weight: 700; color: #0097A9; text-align: left; border-bottom: 1px solid #E2E8F0; background-color: #F0FDFA;">
                    🚀 NUEVO CANAL OFICIAL (ACTIVO)
                  </th>
                </tr>
                <tr>
                  <td style="padding: 14px; font-size: 13px; color: #64748B; line-height: 1.5; border-right: 1px solid #E2E8F0; background-color: #FAFAFA; vertical-align: top;">
                    • Lista / Formulario en SharePoint<br>
                    • Ingreso manual y propenso a retrasos<br>
                    • Sin trazabilidad de correos automatizada
                  </td>
                  <td style="padding: 14px; font-size: 13px; color: #1E293B; line-height: 1.5; background-color: #FFFFFF; vertical-align: top;">
                    • <strong>HALO — App Líderes TI (Módulo Solicitud LTI)</strong><br>
                    • Autocompletado reactivo de Proyecto y Cliente desde SGA<br>
                    • Detección inteligente de Solots Liray estructurados<br>
                    • Notificaciones automáticas por correo al crear y al asignar LTI
                  </td>
                </tr>
              </table>

              <!-- Sección de Beneficios Clave -->
              <div style="font-size: 14px; font-weight: 800; color: #181B20; margin-bottom: 12px;">
                ✨ Principales Mejoras y Beneficios para el Project Manager:
              </div>
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 24px;">
                <tr>
                  <td style="padding: 8px 0; font-size: 13px; color: #334155; line-height: 1.5;">
                    <strong style="color: #0097A9;">1. Autocompletado SGA Inteligente:</strong> Al tipear 2 o más caracteres del N° de Proyecto, la app sugiere las coincidencias de SGA Backlog y autocompleta el Cliente.
                  </td>
                </tr>
                <tr>
                  <td style="padding: 8px 0; font-size: 13px; color: #334155; line-height: 1.5;">
                    <strong style="color: #0097A9;">2. Precarga de Solots Liray:</strong> Si la iniciativa contempla enlaces Liray, el sistema estructura automáticamente los Solots, productos y servicios en el detalle del requerimiento.
                  </td>
                </tr>
                <tr>
                  <td style="padding: 8px 0; font-size: 13px; color: #334155; line-height: 1.5;">
                    <strong style="color: #0097A9;">3. Trazabilidad Total y Notificaciones por Correo:</strong>
                    <ul style="margin: 4px 0 0 18px; padding: 0; color: #475569;">
                      <li>Recibirás confirmación automática formal cuando se registre tu solicitud.</li>
                      <li>Los coordinadores reciben alertas periódicas hasta asegurar la asignación del Líder.</li>
                      <li>En cuanto se asigne el Líder Técnico, <strong>recibirás un correo con copia al LTI responsable</strong> indicando todos los detalles para iniciar la coordinación.</li>
                    </ul>
                  </td>
                </tr>
                <tr>
                  <td style="padding: 8px 0; font-size: 13px; color: #334155; line-height: 1.5;">
                    <strong style="color: #0097A9;">4. Single Sign-On (SSO):</strong> Ingreso transparente y unificado con tus mismas credenciales corporativas mediante el Portal de Acceso HALO.
                  </td>
                </tr>
              </table>

              <!-- Paso a Paso para Solicitar -->
              <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 18px; margin-bottom: 28px;">
                <div style="font-size: 13px; font-weight: 800; color: #1E293B; margin-bottom: 8px;">
                  📌 ¿Cómo ingresar tu solicitud a partir del Lunes?
                </div>
                <ol style="margin: 0; padding-left: 20px; font-size: 13px; color: #475569; line-height: 1.6;">
                  <li>Ingresa a la plataforma <strong>HALO</strong> (<a href="https://200.14.222.162/login.html" style="color: #B52217; font-weight: 700; text-decoration: none;">https://200.14.222.162/login.html</a>).</li>
                  <li>Inicia sesión con tus credenciales de red habituales (Portal de Acceso).</li>
                  <li>Se abrirá directamente el módulo <strong>📝 Solicitud LTI</strong>.</li>
                  <li>Digita el N° de Proyecto, verifica los datos autocompletados y pulsa <strong>🚀 Solicitar</strong>.</li>
                </ol>
              </div>

              <!-- Botón de Llamado a la Acción (CTA) -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 28px;">
                <tr>
                  <td align="center">
                    <table cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td align="center" style="background-color: #B52217; border-radius: 6px;">
                          <a href="https://200.14.222.162/login.html" target="_blank" style="display: inline-block; padding: 14px 28px; font-size: 14px; font-weight: 700; color: #FFFFFF; text-decoration: none; border-radius: 6px;">
                            🚀 Ingresar a HALO App Líderes TI &rarr;
                          </a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- Mensaje de Cierre y Soporte -->
              <p style="color: #64748B; font-size: 13px; line-height: 1.5; margin: 0;">
                Agradecemos desde ya tu valiosa colaboración en esta adopción tecnológica que nos permitirá coordinar los proyectos con mayor agilidad y precisión. Ante cualquier duda o requerimiento de soporte, puedes contactar a los coordinadores generales del servicio:<br>
                • <strong>Alejandro Aguilar:</strong> <a href="mailto:alejandro.aguilarm@clarovtr.cl" style="color: #0097A9; text-decoration: none;">alejandro.aguilarm@clarovtr.cl</a><br>
                • <strong>Pablo Castillo:</strong> <a href="mailto:pablo.castillo@clarovtr.cl" style="color: #0097A9; text-decoration: none;">pablo.castillo@clarovtr.cl</a>
              </p>

            </td>
          </tr>

          <!-- Pie de Página Institucional -->
          <tr>
            <td style="background-color: #181B20; padding: 20px 32px; border-top: 1px solid #334155; text-align: center;">
              <div style="color: #FDEDEA; font-size: 13px; font-weight: 700; margin-bottom: 4px;">
                HALO — Ecosistema de Plataformas TI
              </div>
              <div style="color: #94A3B8; font-size: 11px; line-height: 1.4;">
                Dirección de Operaciones TI • Claro Chile / VTR<br>
                Este es un mensaje institucional automatizado generado por el sistema HALO App LTI.
              </div>
            </td>
          </tr>

        </table>

      </td>
    </tr>
  </table>

</body>
</html>"""


def get_pm_recipients():
    """Recopila y consolida la lista única de PMs con sus correos corporativos resueltos."""
    conn = get_db_connection()
    recipients_map = {}

    try:
        # 1. Extraer del Excel oficial (nómina corporativa de 31 PMs)
        excel_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'csv', 'Listado_Permisos_Usuarios.xlsx')
        if os.path.exists(excel_path):
            excel_users = read_users_from_excel(excel_path)
            for u in excel_users:
                if u.get('rol') == 'PM':
                    nombre = u.get('nombre')
                    email = resolve_user_email(nombre, conn)
                    if email:
                        recipients_map[email] = nombre

        # 2. Extraer de dbo.App_Usuarios cualquier otro PM activo no presente en el Excel
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, username, nombre_completo, email, rol 
                FROM dbo.App_Usuarios 
                WHERE rol='PM' AND activo=1
                  AND username NOT LIKE 'test%'
                  AND username NOT LIKE 'jit.user%'
                  AND username NOT LIKE 'edituser%'
                  AND username NOT LIKE 'toggleuser%'
                  AND username NOT LIKE 'target.user%'
                  AND username NOT LIKE 'pm.%'
            """)
            known_normalized_names = {
                ''.join(c for c in n.lower() if c.isalnum()): e 
                for e, n in recipients_map.items()
            }
            
            for row in cur.fetchall():
                nombre = (row.get('nombre_completo') or row.get('username') or "").strip()
                norm_key = ''.join(c for c in nombre.lower() if c.isalnum())
                # Si el usuario ya fue resuelto desde el Excel oficial, no duplicar con su username antiguo
                if norm_key in known_normalized_names:
                    continue
                email = row.get('email') or resolve_user_email(row.get('username') or nombre, conn)
                if email and email not in recipients_map:
                    recipients_map[email] = nombre
                    known_normalized_names[norm_key] = email
    finally:
        conn.close()

    return recipients_map


def main():
    parser = argparse.ArgumentParser(description="Envío de comunicado a PMs para migración a App LTI")
    parser.add_argument("--test", type=str, help="Enviar correo de prueba a una dirección específica")
    parser.add_argument("--dry-run", action="store_true", help="Listar destinatarios sin enviar")
    parser.add_argument("--send-all", action="store_true", help="Enviar formalmente a todos los PMs")

    args = parser.parse_args()

    if args.dry_run:
        pms = get_pm_recipients()
        print(f"==================================================")
        print(f"LISTADO DE DESTINATARIOS PM ({len(pms)} encontrados):")
        print(f"==================================================")
        for i, (email, name) in enumerate(sorted(pms.items()), 1):
            print(f"{i:02d}. {name} <{email}>")
        print(f"==================================================")
        return

    if args.test:
        target = args.test.strip()
        print(f"[TEST] Enviando correo de prueba a: {target}")
        html = build_announcement_html(is_test=True)
        res = send_email_notification(
            to_emails=target,
            subject="[PRUEBA / VISTA PREVIA] Nuevo Canal Exclusivo para Solicitud de Líder Técnico (LTI) — App LTI",
            html_body=html
        )
        print("Resultado:", res)
        return

    if args.send_all:
        pms = get_pm_recipients()
        print(f"⚠️ ATENCIÓN: Se enviará el comunicado a {len(pms)} Project Managers.")
        html = build_announcement_html(is_test=False)
        subject = "[COMUNICADO OFICIAL] Nuevo Canal Exclusivo para Solicitud de Líder Técnico (LTI) — Migración a App LTI"
        
        sent_count = 0
        error_count = 0
        for email, name in sorted(pms.items()):
            try:
                print(f"Enviando a: {name} <{email}>...")
                res = send_email_notification(
                    to_emails=email,
                    subject=subject,
                    html_body=html
                )
                if res.get("success"):
                    sent_count += 1
                else:
                    print(f"  ❌ Fallo: {res.get('error')}")
                    error_count += 1
                time.sleep(0.5)  # Breve pausa para no saturar SMTP
            except Exception as e:
                print(f"  ❌ Excepción enviando a {email}: {e}")
                error_count += 1

        print("==================================================")
        print(f"RESUMEN: Enviados: {sent_count} | Errores: {error_count}")
        print("==================================================")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
