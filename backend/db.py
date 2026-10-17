import pymssql
import datetime
from decimal import Decimal
from typing import List, Union, Optional
import logging
import os
from pathlib import Path
from .config import DB_CONFIG
from . import config as app_config

import re
import hashlib
import html

logger = logging.getLogger("db")

UNMATCHED_SOLICITANTE = "NO IDENTIFICADO. PROYECTO DEMO O NO HA LLEGADO PROYECTO A INSTALACIONES"

def clean_solicitante(name):
    """Strips 'Corp...' prefix and ensures uppercase formatting. Returns fallback text if empty or not identified."""
    if not name:
        return UNMATCHED_SOLICITANTE
    name_str = str(name).strip()
    if not name_str or name_str.upper() in ('N/A', 'NONE', 'NULL', '-'):
        return UNMATCHED_SOLICITANTE
    if name_str == UNMATCHED_SOLICITANTE:
        return UNMATCHED_SOLICITANTE
    # Remove Corp... prefix (e.g. Corp1-, Corp2-, Corp -, Corp1 -)
    cleaned = re.sub(r'^Corp[0-9]*\s*[-–—:]*\s*', '', name_str, flags=re.IGNORECASE).strip()
    return cleaned.upper() if cleaned else UNMATCHED_SOLICITANTE

def format_numero_proyecto(num):
    """Ensures project number starts with 000 if not already present."""
    if num is None:
        return num
    s = str(num).strip()
    if not s or s.upper() in ('N/A', 'NONE', 'NULL', '-'):
        return s
    if s.startswith('000'):
        return s
    return f"000{s}"

def get_db_connection():
    conn = pymssql.connect(
        server=DB_CONFIG['Server'],
        port=int(DB_CONFIG['Port']),
        user=DB_CONFIG['User'],
        password=DB_CONFIG['Password'],
        database=DB_CONFIG['Database'],
        as_dict=True
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;")
    except Exception:
        pass
    return conn

def serialize_row(row):
    """Serializes datetime, Decimal, and None values for JSON compatibility."""
    if not row:
        return row
    res = {}
    for k, v in row.items():
        if isinstance(v, (datetime.datetime, datetime.date)):
            res[k] = v.strftime('%Y-%m-%d %H:%M:%S') if isinstance(v, datetime.datetime) else v.strftime('%Y-%m-%d')
        elif isinstance(v, Decimal):
            res[k] = int(v) if v % 1 == 0 else float(v)
        else:
            res[k] = v

    if 'Solicitante' in res:
        res['Solicitante'] = clean_solicitante(res.get('Solicitante'))
    if 'Numero_Proyecto' in res and res['Numero_Proyecto']:
        res['Numero_Proyecto'] = format_numero_proyecto(res['Numero_Proyecto'])

    return res

def serialize_rows(rows):
    return [serialize_row(r) for r in rows]

def calcular_salud_proyecto(row: dict) -> dict:
    """Calcula el estado de salud operacional de un proyecto (Verde, Amarillo, Rojo, Gris) y motivos legibles."""
    if not row:
        return {
            "score": "NEUTRAL",
            "color": "gray",
            "label": "Sin Datos",
            "motivos": ["Proyecto sin Solots ni tickets vinculados"],
            "solots_vencidas": 0,
            "solots_por_vencer": 0,
            "tickets_criticos": 0,
            "tickets_atencion": 0
        }

    total_solots = int(row.get('total_solots') or 0)
    total_tickets = int(row.get('total_tickets') or 0)
    solots_vencidas = int(row.get('solots_vencidas') or 0)
    solots_por_vencer = int(row.get('solots_por_vencer') or 0)
    tickets_criticos = int(row.get('tickets_criticos') or 0)
    tickets_atencion = int(row.get('tickets_atencion') or 0)

    # 1. Sin datos vinculados
    if total_solots == 0 and total_tickets == 0:
        return {
            "score": "NEUTRAL",
            "color": "gray",
            "label": "Sin Datos",
            "motivos": ["Proyecto sin Solots ni tickets vinculados"],
            "solots_vencidas": 0,
            "solots_por_vencer": 0,
            "tickets_criticos": 0,
            "tickets_atencion": 0
        }

    motivos = []

    # 2. Criterio Crítico (Rojo)
    if solots_vencidas > 0:
        motivos.append(f"{solots_vencidas} Solot{'s' if solots_vencidas > 1 else ''} con fecha comprometida vencida")
    if tickets_criticos > 0:
        motivos.append(f"{tickets_criticos} Ticket{'s' if tickets_criticos > 1 else ''} abierto{'s' if tickets_criticos > 1 else ''} > 14 días")

    if motivos:
        return {
            "score": "CRITICAL",
            "color": "red",
            "label": "Crítico",
            "motivos": motivos,
            "solots_vencidas": solots_vencidas,
            "solots_por_vencer": solots_por_vencer,
            "tickets_criticos": tickets_criticos,
            "tickets_atencion": tickets_atencion
        }

    # 3. Criterio Riesgo / Atención (Amarillo)
    if solots_por_vencer > 0:
        motivos.append(f"{solots_por_vencer} Solot{'s' if solots_por_vencer > 1 else ''} por vencer (< 5 días)")
    if tickets_atencion > 0:
        motivos.append(f"{tickets_atencion} Ticket{'s' if tickets_atencion > 1 else ''} abierto{'s' if tickets_atencion > 1 else ''} > 7 días")

    if motivos:
        return {
            "score": "WARNING",
            "color": "yellow",
            "label": "En Riesgo",
            "motivos": motivos,
            "solots_vencidas": 0,
            "solots_por_vencer": solots_por_vencer,
            "tickets_criticos": 0,
            "tickets_atencion": tickets_atencion
        }

    # 4. Criterio Saludable (Verde)
    return {
        "score": "HEALTHY",
        "color": "green",
        "label": "Saludable",
        "motivos": ["Solots y tickets operando dentro de plazo regular"],
        "solots_vencidas": 0,
        "solots_por_vencer": 0,
        "tickets_criticos": 0,
        "tickets_atencion": 0
    }


def init_auth_tables():
    """Ensures dbo.App_Usuarios table exists with updated_at, email, and dbo.Proyectos has reminder tracking columns."""
    conn = get_db_connection()
    try:
        # 1. dbo.App_Usuarios
        with conn.cursor() as cursor:
            cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'App_Usuarios')
            BEGIN
                CREATE TABLE dbo.App_Usuarios (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    username VARCHAR(100) NOT NULL UNIQUE,
                    nombre_completo VARCHAR(150) NOT NULL,
                    lt_asignado VARCHAR(150) NULL,
                    rol VARCHAR(50) NOT NULL DEFAULT 'PM',
                    email VARCHAR(150) NULL,
                    activo BIT NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL DEFAULT GETDATE(),
                    updated_at DATETIME NOT NULL DEFAULT GETDATE()
                );
            END
            ELSE
            BEGIN
                IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'App_Usuarios' AND COLUMN_NAME = 'updated_at')
                BEGIN
                    ALTER TABLE dbo.App_Usuarios ADD updated_at DATETIME NOT NULL DEFAULT GETDATE();
                END
                IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'App_Usuarios' AND COLUMN_NAME = 'email')
                BEGIN
                    ALTER TABLE dbo.App_Usuarios ADD email VARCHAR(150) NULL;
                END
                IF EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'App_Usuarios' AND COLUMN_NAME = 'password_hash' AND IS_NULLABLE = 'NO')
                BEGIN
                    ALTER TABLE dbo.App_Usuarios ALTER COLUMN password_hash VARCHAR(255) NULL;
                END
            END
            """)
        conn.commit()

        # 2. Tracking de recordatorios en dbo.Proyectos
        with conn.cursor() as cursor:
            cursor.execute("""
            IF NOT EXISTS (
                SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'Proyectos' AND COLUMN_NAME = 'Ultimo_Recordatorio'
            )
            BEGIN
                ALTER TABLE dbo.Proyectos ADD Ultimo_Recordatorio DATETIME NULL;
            END

            IF NOT EXISTS (
                SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'Proyectos' AND COLUMN_NAME = 'Contador_Recordatorios'
            )
            BEGIN
                ALTER TABLE dbo.Proyectos ADD Contador_Recordatorios INT NOT NULL DEFAULT 0;
            END
            """)
        conn.commit()

        # 3. Índice para optimizar consulta periódica del scheduler cada 6 horas
        # Nota: En dbo.Proyectos, Estado es NVARCHAR(MAX) por lo que no puede ser key column; se usan LT_Asignado, Creado, Ultimo_Recordatorio.
        with conn.cursor() as cursor:
            try:
                cursor.execute("""
                IF NOT EXISTS (
                    SELECT 1 FROM sys.indexes 
                    WHERE name = 'IX_Proyectos_LT_Asignado_Ultimo_Recordatorio' 
                      AND object_id = OBJECT_ID('dbo.Proyectos')
                )
                BEGIN
                    CREATE NONCLUSTERED INDEX IX_Proyectos_LT_Asignado_Ultimo_Recordatorio
                    ON dbo.Proyectos (LT_Asignado, Creado, Ultimo_Recordatorio)
                    INCLUDE (ID, Cliente, Numero_Proyecto, Solicitante);
                END
                """)
                conn.commit()
            except Exception as idx_err:
                try:
                    conn.rollback()
                except Exception:
                    pass
                logger.warning(f"Advertencia al verificar/crear índice IX_Proyectos_LT_Asignado_Ultimo_Recordatorio: {idx_err}")
    finally:
        conn.close()

def get_user_by_username(username):
    """Obtiene usuario activo por username para autenticación."""
    if not username:
        return None
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM dbo.App_Usuarios WHERE LOWER(username) = LOWER(%s) AND activo = 1", (username.strip(),))
            user = cursor.fetchone()
            return serialize_row(user)
    finally:
        conn.close()

def get_usuario_by_username(username):
    """Obtiene usuario por username sin filtrar por activo."""
    if not username:
        return None
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM dbo.App_Usuarios WHERE LOWER(username) = LOWER(%s)", (username.strip(),))
            user = cursor.fetchone()
            return serialize_row(user)
    finally:
        conn.close()

def get_or_create_jit_user(
    username: str,
    nombre_completo: Optional[str] = None,
    default_rol: str = "PM",
    email: Optional[str] = None
) -> dict:
    """Busca por LOWER(username) y si no existe lo inserta con activo=1, email y rol=default_rol (JIT Provisioning)."""
    if not username:
        return None
    uname = username.strip().lower()
    full_name = (nombre_completo.strip() if nombre_completo and str(nombre_completo).strip() else uname.replace(".", " ").title())
    user_email = email.strip().lower() if email and str(email).strip() else None

    canonical_lt = None
    lideres_map = {
        "alejandro.aguilar": "Alejandro Aguilar",
        "aaguilar": "Alejandro Aguilar",
        "erwin.sandoval": "Erwin Sandoval",
        "esandoval": "Erwin Sandoval",
        "juan.barrera": "Juan Barrera",
        "jbarrera": "Juan Barrera",
        "samuel.paredes": "Samuel Paredes",
        "sparedes": "Samuel Paredes",
        "solange.ortiz": "Solange Ortiz",
        "sortiz": "Solange Ortiz",
    }
    if uname in lideres_map:
        canonical_lt = lideres_map[uname]

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, username, nombre_completo, lt_asignado, rol, activo, email, created_at, updated_at
                FROM dbo.App_Usuarios
                WHERE LOWER(username) = %s
            """, (uname,))
            existing = cursor.fetchone()
            if existing:
                # Si existe pero no tenía email (o viene un nuevo email válido), actualizarlo
                if user_email and (not existing.get('email') or existing.get('email').strip().lower() != user_email):
                    try:
                        cursor.execute("""
                            UPDATE dbo.App_Usuarios
                            SET email = %s, updated_at = GETDATE()
                            WHERE id = %s
                        """, (user_email, existing['id']))
                        conn.commit()
                        existing['email'] = user_email
                    except Exception as e:
                        logger.warning(f"Aviso actualizando email de usuario JIT {uname}: {e}")
                return serialize_row(existing)

            # Insertar nuevo usuario JIT
            cursor.execute("""
                INSERT INTO dbo.App_Usuarios (username, nombre_completo, lt_asignado, rol, email, activo, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, 1, GETDATE(), GETDATE())
            """, (
                uname,
                full_name,
                canonical_lt,
                (default_rol.strip().upper() if default_rol else "PM"),
                user_email
            ))
            cursor.execute("""
                SELECT id, username, nombre_completo, lt_asignado, rol, activo, email, created_at, updated_at
                FROM dbo.App_Usuarios
                WHERE LOWER(username) = %s
            """, (uname,))
            created = cursor.fetchone()
            conn.commit()
            return serialize_row(created)
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        raise e
    finally:
        conn.close()

def get_all_usuarios(search=None, rol=None, activo=None):
    """Listar usuarios con filtros opcionales de búsqueda, rol y estado."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT id, username, nombre_completo, lt_asignado, rol, email, activo, created_at, updated_at
                FROM dbo.App_Usuarios
                WHERE 1=1
            """
            params = []
            if search and search.strip():
                term = f"%{search.strip()}%"
                sql += " AND (username LIKE %s OR nombre_completo LIKE %s OR ISNULL(lt_asignado, '') LIKE %s OR ISNULL(email, '') LIKE %s)"
                params.extend([term, term, term, term])

            if rol and rol.strip():
                sql += " AND rol = %s"
                params.append(rol.strip().upper())

            if activo is not None:
                act_val = 1 if (activo is True or str(activo).lower() in ('1', 'true', 'yes')) else 0
                sql += " AND activo = %s"
                params.append(act_val)

            sql += " ORDER BY nombre_completo ASC"
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            return serialize_rows(rows)
    finally:
        conn.close()

def get_usuario_by_id(user_id: int):
    """Obtiene los detalles de un usuario por su ID."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, username, nombre_completo, lt_asignado, rol, email, activo, created_at, updated_at
                FROM dbo.App_Usuarios
                WHERE id = %s
            """, (user_id,))
            user = cursor.fetchone()
            return serialize_row(user)
    finally:
        conn.close()

def update_usuario(
    user_id: int,
    nombre_completo: str,
    lt_asignado: Optional[str] = None,
    rol: str = "PM",
    activo: bool = True,
    email: Optional[str] = None
) -> dict:
    """Actualiza datos de un usuario existente sin contraseñas."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM dbo.App_Usuarios WHERE id = %s", (user_id,))
            if not cursor.fetchone():
                return {"success": False, "error": "not_found", "message": f"Usuario ID {user_id} no encontrado"}

            user_email = email.strip().lower() if email and str(email).strip() else None

            cursor.execute("""
                UPDATE dbo.App_Usuarios
                SET nombre_completo = %s,
                    lt_asignado = %s,
                    rol = %s,
                    activo = %s,
                    email = COALESCE(%s, email),
                    updated_at = GETDATE()
                WHERE id = %s
            """, (
                nombre_completo.strip(),
                (lt_asignado.strip() if lt_asignado and str(lt_asignado).strip() else None),
                rol.strip().upper(),
                1 if activo else 0,
                user_email,
                user_id
            ))
            conn.commit()
            return {"success": True, "data": get_usuario_by_id(user_id)}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "error": "db_error", "message": str(e)}
    finally:
        conn.close()

def toggle_user_status(user_id: int) -> dict:
    """Alterna el estado activo/bloqueado de un usuario."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, username, activo FROM dbo.App_Usuarios WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                return {"success": False, "error": "not_found", "message": f"Usuario ID {user_id} no encontrado"}

            new_status = 0 if user.get('activo') in (1, True, b'\x01') else 1
            cursor.execute("""
                UPDATE dbo.App_Usuarios
                SET activo = %s,
                    updated_at = GETDATE()
                WHERE id = %s
            """, (new_status, user_id))
            conn.commit()
            return {
                "success": True,
                "id": user_id,
                "username": user.get('username'),
                "activo": bool(new_status)
            }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "error": "db_error", "message": str(e)}
    finally:
        conn.close()

def delete_usuario(user_id: int) -> dict:
    """Elimina físicamente un usuario."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, username, nombre_completo FROM dbo.App_Usuarios WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                return {"success": False, "error": "not_found", "message": f"Usuario ID {user_id} no encontrado"}

            cursor.execute("DELETE FROM dbo.App_Usuarios WHERE id = %s", (user_id,))
            conn.commit()
            return {
                "success": True,
                "id": user_id,
                "username": user.get('username'),
                "nombre_completo": user.get('nombre_completo')
            }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "error": "db_error", "message": str(e)}
    finally:
        conn.close()

def get_lideres_list():
    """
    Retorna la lista oficial y estricta de Líderes TI activos en orden alfabético ascendente.
    """
    return [
        "Alejandro Aguilar",
        "Erwin Sandoval",
        "Juan Barrera",
        "Samuel Paredes",
        "Solange Ortiz"
    ]

CANONICAL_ESTADOS_SHAREPOINT = [
    "Generado",
    "En ejecucion",
    "En revision",
    "Cerrado"
]

# Alias aceptados al normalizar (sin tildes, en minúsculas). 'Atendido' es el estado legado de 'Cerrado'.
_ESTADOS_ALIAS = {
    "generado": "Generado",
    "en ejecucion": "En ejecucion",
    "en revision": "En revision",
    "cerrado": "Cerrado",
    "atendido": "Cerrado",
}

def normalizar_estado_proyecto(estado) -> Optional[str]:
    """
    Normaliza un estado de proyecto ignorando mayúsculas y tildes ('en ejecución' -> 'En ejecucion').
    El estado legado 'Atendido' se normaliza a 'Cerrado'. Retorna None si no pertenece al catálogo.
    """
    if estado is None:
        return None
    import unicodedata
    nfkd = unicodedata.normalize('NFKD', str(estado))
    clave = ''.join(c for c in nfkd if not unicodedata.combining(c)).strip().lower()
    return _ESTADOS_ALIAS.get(clave)

def resolver_estado_por_asignacion(estado: str, lt_asignado) -> str:
    """Un proyecto 'Generado' con LTI asignado pasa a 'En ejecucion'; los demás estados no se alteran."""
    if estado == "Generado" and not _is_unassigned_lt(lt_asignado):
        return "En ejecucion"
    return estado

def get_estados_list() -> dict:
    """
    Retorna el catálogo canónico oficial de estados de proyectos SharePoint (dbo.Proyectos)
    y la lista de estados dinámicos de solots SGA (dbo.CT_BACKLOG_OPERACIONES2).
    
    Para SharePoint, devuelve siempre los 4 estados oficiales del ciclo de vida:
    ['Generado', 'En ejecucion', 'En revision', 'Cerrado'], evitando dependencias frágiles de los
    registros transitorios existentes en la tabla. El estado legado 'Atendido' se trata como 'Cerrado'.
    """
    estados_sp = list(CANONICAL_ESTADOS_SHAREPOINT)
    estados_sga = []

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT ESTADO_OTP 
                FROM dbo.CT_BACKLOG_OPERACIONES2 
                WHERE ESTADO_OTP IS NOT NULL 
                  AND LTRIM(RTRIM(ESTADO_OTP)) <> ''
                ORDER BY ESTADO_OTP ASC
            """)
            estados_sga = [r['ESTADO_OTP'] for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error al obtener lista de estados SGA desde BD: {e}")
        estados_sga = []
    finally:
        if conn:
            conn.close()

    return {
        "estados_sharepoint": estados_sp,
        "estados_sga": estados_sga
    }

# -----------------------------------------------------------------------------
# VINCULACIÓN PROYECTO ↔ SOLOTS / TICKETS / RFCs POR N° DE PROYECTO
# -----------------------------------------------------------------------------
# dbo.Proyectos.Numero_Proyecto puede venir con el prefijo SGA '000' ('0001609373'),
# mientras que Numero_Proyecto_Limpio en el backlog, tickets y RFCs nunca lo trae ('1609373').
# ID_Proyecto ya no lo completa ningún proceso de carga, por lo que toda vinculación
# considera ID_Proyecto O el N° de proyecto con y sin prefijo.
_SQL_P_NUMERO_TRIM = "LTRIM(RTRIM(p.Numero_Proyecto))"
_SQL_P_NUMERO_SIN_PREFIJO = (
    "CASE WHEN LTRIM(RTRIM(p.Numero_Proyecto)) LIKE '000%' "
    "THEN SUBSTRING(LTRIM(RTRIM(p.Numero_Proyecto)), 4, 50) "
    "ELSE LTRIM(RTRIM(p.Numero_Proyecto)) END"
)
# Uso: "<alias>.Numero_Proyecto_Limpio " + _SQL_P_NUMERO_LIMPIO_IN (requiere alias p = dbo.Proyectos)
_SQL_P_NUMERO_LIMPIO_IN = f"IN ({_SQL_P_NUMERO_TRIM}, {_SQL_P_NUMERO_SIN_PREFIJO})"

# CTEs SolotStats / TicketStats / RFCStats por proyecto (columna ID_Proyecto = p.ID).
# Cada registro se cuenta una sola vez por proyecto aunque coincida por ID y por número.
_SQL_STATS_CTES = f"""
                ProyectoNumeros AS (
                    SELECT p.ID AS ID_Proyecto, k.numero
                    FROM dbo.Proyectos p WITH (NOLOCK)
                    CROSS APPLY (
                        SELECT {_SQL_P_NUMERO_TRIM} AS numero
                        UNION
                        SELECT {_SQL_P_NUMERO_SIN_PREFIJO}
                    ) k
                    WHERE k.numero IS NOT NULL AND k.numero <> ''
                ),
                SolotVinculos AS (
                    SELECT b.ID_Proyecto, b.id, b.ESTADO_OTP, b.FECHA_COMPROMETIDA
                    FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK)
                    WHERE b.ID_Proyecto IS NOT NULL
                    UNION
                    SELECT pn.ID_Proyecto, b.id, b.ESTADO_OTP, b.FECHA_COMPROMETIDA
                    FROM ProyectoNumeros pn
                    INNER JOIN dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK) ON b.Numero_Proyecto_Limpio = pn.numero
                ),
                SolotStats AS (
                    SELECT 
                        ID_Proyecto,
                        COUNT(1) AS total_solots,
                        SUM(CASE 
                            WHEN ESTADO_OTP NOT IN ('Cerrada', '5- Ejecutada', '5- Ejecutada Tareas Pendientes', 'Abortado', 'En Aborcion', 'Eliminada', 'Aprobado') 
                                 AND FECHA_COMPROMETIDA IS NOT NULL AND FECHA_COMPROMETIDA < CAST(GETDATE() AS DATE) THEN 1 
                            ELSE 0 
                        END) AS solots_vencidas,
                        SUM(CASE 
                            WHEN ESTADO_OTP NOT IN ('Cerrada', '5- Ejecutada', '5- Ejecutada Tareas Pendientes', 'Abortado', 'En Aborcion', 'Eliminada', 'Aprobado') 
                                 AND FECHA_COMPROMETIDA IS NOT NULL AND FECHA_COMPROMETIDA >= CAST(GETDATE() AS DATE) 
                                 AND FECHA_COMPROMETIDA <= DATEADD(day, 5, CAST(GETDATE() AS DATE)) THEN 1 
                            ELSE 0 
                        END) AS solots_por_vencer
                    FROM SolotVinculos
                    GROUP BY ID_Proyecto
                ),
                TicketVinculos AS (
                    SELECT sd.ID_Proyecto, sd.CC_INCIDENT_ID, sd.STATUS, sd.SUBMIT_DATE
                    FROM dbo.registrosRF_SD_SM sd WITH (NOLOCK)
                    WHERE sd.ID_Proyecto IS NOT NULL
                    UNION
                    SELECT pn.ID_Proyecto, sd.CC_INCIDENT_ID, sd.STATUS, sd.SUBMIT_DATE
                    FROM ProyectoNumeros pn
                    INNER JOIN dbo.registrosRF_SD_SM sd WITH (NOLOCK) ON sd.Numero_Proyecto_Limpio = pn.numero
                ),
                TicketStats AS (
                    SELECT 
                        ID_Proyecto,
                        COUNT(1) AS total_tickets,
                        SUM(CASE 
                            WHEN STATUS NOT IN ('Cerrado', 'Resuelto') 
                                 AND SUBMIT_DATE IS NOT NULL
                                 AND TRY_CAST(SUBMIT_DATE AS DATETIME2) < DATEADD(day, -14, GETDATE()) THEN 1 
                            ELSE 0 
                        END) AS tickets_criticos,
                        SUM(CASE 
                            WHEN STATUS NOT IN ('Cerrado', 'Resuelto') 
                                 AND SUBMIT_DATE IS NOT NULL
                                 AND TRY_CAST(SUBMIT_DATE AS DATETIME2) >= DATEADD(day, -14, GETDATE())
                                 AND TRY_CAST(SUBMIT_DATE AS DATETIME2) < DATEADD(day, -7, GETDATE()) THEN 1 
                            ELSE 0 
                        END) AS tickets_atencion
                    FROM TicketVinculos
                    GROUP BY ID_Proyecto
                ),
                RFCVinculos AS (
                    SELECT rfc.ID_Proyecto, rfc.NUMBER
                    FROM dbo.registrosSM_RFC rfc WITH (NOLOCK)
                    WHERE rfc.ID_Proyecto IS NOT NULL
                    UNION
                    SELECT pn.ID_Proyecto, rfc.NUMBER
                    FROM ProyectoNumeros pn
                    INNER JOIN dbo.registrosSM_RFC rfc WITH (NOLOCK) ON rfc.Numero_Proyecto_Limpio = pn.numero
                ),
                RFCStats AS (
                    SELECT 
                        ID_Proyecto,
                        COUNT(1) AS total_rfcs
                    FROM RFCVinculos
                    GROUP BY ID_Proyecto
                )"""

def _numero_proyecto_limpio_keys(numero_proyecto) -> tuple:
    """N° de proyecto tal cual y sin el prefijo SGA '000', para comparar con Numero_Proyecto_Limpio."""
    num = str(numero_proyecto or "").strip()
    return (num, num[3:] if num.startswith("000") else num)

def get_proyectos(lt_filter=None, search=None, estado_sp=None, estado_sga=None):
    if lt_filter in (None, '', '__ALL__'):
        lt_filter = None
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                WITH """ + _SQL_STATS_CTES + """,
                SolotIngById AS (
                    SELECT 
                        ID_Proyecto, 
                        PRO_ING_PROYECTO,
                        ROW_NUMBER() OVER (
                            PARTITION BY ID_Proyecto 
                            ORDER BY 
                                CASE WHEN FECHA_INSERT IS NOT NULL THEN 0 ELSE 1 END,
                                FECHA_INSERT DESC, 
                                id DESC
                        ) as rn
                    FROM dbo.CT_BACKLOG_OPERACIONES2 WITH (NOLOCK)
                    WHERE ID_Proyecto IS NOT NULL 
                      AND PRO_ING_PROYECTO IS NOT NULL 
                      AND LTRIM(RTRIM(PRO_ING_PROYECTO)) <> ''
                ),
                SolotIngByNro AS (
                    SELECT 
                        Numero_Proyecto_Limpio,
                        PRO_ING_PROYECTO,
                        ROW_NUMBER() OVER (
                            PARTITION BY Numero_Proyecto_Limpio 
                            ORDER BY 
                                CASE WHEN FECHA_INSERT IS NOT NULL THEN 0 ELSE 1 END,
                                FECHA_INSERT DESC, 
                                id DESC
                        ) as rn
                    FROM dbo.CT_BACKLOG_OPERACIONES2 WITH (NOLOCK)
                    WHERE Numero_Proyecto_Limpio IS NOT NULL 
                      AND LTRIM(RTRIM(Numero_Proyecto_Limpio)) <> ''
                      AND PRO_ING_PROYECTO IS NOT NULL 
                      AND LTRIM(RTRIM(PRO_ING_PROYECTO)) <> ''
                ),
                SolotIngByOtp AS (
                    SELECT 
                        NRO_PROYECTO,
                        PRO_ING_PROYECTO,
                        ROW_NUMBER() OVER (
                            PARTITION BY NRO_PROYECTO 
                            ORDER BY 
                                CASE WHEN FECHA_INSERT IS NOT NULL THEN 0 ELSE 1 END,
                                FECHA_INSERT DESC, 
                                id DESC
                        ) as rn
                    FROM dbo.CT_BACKLOG_OPERACIONES2 WITH (NOLOCK)
                    WHERE NRO_PROYECTO IS NOT NULL 
                      AND LTRIM(RTRIM(NRO_PROYECTO)) <> ''
                      AND PRO_ING_PROYECTO IS NOT NULL 
                      AND LTRIM(RTRIM(PRO_ING_PROYECTO)) <> ''
                )
                SELECT 
                    p.ID,
                    p.Cliente,
                    p.Numero_Proyecto,
                    p.LT_Asignado,
                    p.Estado,
                    p.Detalle,
                    p.Comentario,
                    p.Tipo_Servicio,
                    p.Creado AS Creado,
                    ISNULL(ss.total_solots, 0) AS total_solots,
                    ISNULL(ts.total_tickets, 0) AS total_tickets,
                    ISNULL(rs.total_rfcs, 0) AS total_rfcs,
                    ISNULL(ss.solots_vencidas, 0) AS solots_vencidas,
                    ISNULL(ss.solots_por_vencer, 0) AS solots_por_vencer,
                    ISNULL(ts.tickets_criticos, 0) AS tickets_criticos,
                    ISNULL(ts.tickets_atencion, 0) AS tickets_atencion,
                    COALESCE(
                        si_id.PRO_ING_PROYECTO, 
                        si_limp.PRO_ING_PROYECTO,
                        si_limp2.PRO_ING_PROYECTO,
                        si_otp.PRO_ING_PROYECTO, 
                        si_otp2.PRO_ING_PROYECTO
                    ) AS Solicitante
                FROM dbo.Proyectos p WITH (NOLOCK)
                LEFT JOIN SolotStats ss ON p.ID = ss.ID_Proyecto
                LEFT JOIN TicketStats ts ON p.ID = ts.ID_Proyecto
                LEFT JOIN RFCStats rs ON p.ID = rs.ID_Proyecto
                LEFT JOIN SolotIngById si_id ON p.ID = si_id.ID_Proyecto AND si_id.rn = 1
                LEFT JOIN SolotIngByNro si_limp ON LTRIM(RTRIM(p.Numero_Proyecto)) = si_limp.Numero_Proyecto_Limpio AND si_limp.rn = 1
                LEFT JOIN SolotIngByNro si_limp2 ON (
                    CASE 
                        WHEN p.Numero_Proyecto LIKE '000%' THEN SUBSTRING(LTRIM(RTRIM(p.Numero_Proyecto)), 4, 50)
                        ELSE LTRIM(RTRIM(p.Numero_Proyecto))
                    END
                ) = si_limp2.Numero_Proyecto_Limpio AND si_limp2.rn = 1
                LEFT JOIN SolotIngByOtp si_otp ON LTRIM(RTRIM(p.Numero_Proyecto)) = si_otp.NRO_PROYECTO AND si_otp.rn = 1
                LEFT JOIN SolotIngByOtp si_otp2 ON ('000' + LTRIM(RTRIM(p.Numero_Proyecto))) = si_otp2.NRO_PROYECTO AND si_otp2.rn = 1
                WHERE (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')
            """
            params = []
            if lt_filter == "__UNASSIGNED__":
                sql += " AND (p.LT_Asignado IS NULL OR LTRIM(RTRIM(p.LT_Asignado)) = '' OR LOWER(LTRIM(RTRIM(p.LT_Asignado))) = 'sin asignar')"
            elif lt_filter:
                sql += " AND p.LT_Asignado = %s"
                params.append(lt_filter)

            if estado_sp:
                estado_sp_norm = normalizar_estado_proyecto(estado_sp) or estado_sp
                if estado_sp_norm == "Cerrado":
                    # 'Atendido' es el estado legado de 'Cerrado'
                    sql += " AND p.Estado IN ('Cerrado', 'Atendido')"
                else:
                    sql += " AND p.Estado = %s"
                    params.append(estado_sp_norm)

            if estado_sga:
                sql += (
                    " AND EXISTS (SELECT 1 FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK) WHERE (b.ID_Proyecto = p.ID OR b.Numero_Proyecto_Limpio "
                    + _SQL_P_NUMERO_LIMPIO_IN + ") AND b.ESTADO_OTP = %s)"
                )
                params.append(estado_sga)

            if search:
                sql += """ AND (
                    p.Cliente LIKE %s OR 
                    p.Numero_Proyecto LIKE %s OR 
                    p.Detalle LIKE %s OR 
                    p.Comentario LIKE %s OR
                    p.LT_Asignado LIKE %s OR
                    ISNULL(si_id.PRO_ING_PROYECTO, '') LIKE %s OR
                    ISNULL(si_limp.PRO_ING_PROYECTO, '') LIKE %s
                )"""
                term = f"%{search}%"
                params.extend([term, term, term, term, term, term, term])

            # Ordenado de mayor a menor (descendente) por la fecha de solicitud LTI (p.Creado)
            sql += """
                ORDER BY 
                    CASE WHEN p.Creado IS NOT NULL THEN 0 ELSE 1 END,
                    p.Creado DESC,
                    p.ID DESC
            """
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            serialized = serialize_rows(rows)
            for r in serialized:
                r['salud'] = calcular_salud_proyecto(r)
            return serialized
    finally:
        conn.close()

def get_proyecto_by_id(proyecto_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = f"""
                SELECT 
                    p.ID,
                    p.Cliente,
                    p.Numero_Proyecto,
                    p.LT_Asignado,
                    p.Estado,
                    p.Detalle,
                    p.Comentario,
                    p.Tipo_Servicio,
                    p.Creado AS Creado,
                    p.Creado AS fecha_solicitud_lti,
                    (
                        SELECT MIN(b.FECHA_INSERT) 
                        FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK)
                        WHERE (b.ID_Proyecto = p.ID OR b.Numero_Proyecto_Limpio {_SQL_P_NUMERO_LIMPIO_IN}) AND b.FECHA_INSERT IS NOT NULL
                    ) AS fecha_creacion_sga,
                    (
                        SELECT MIN(b.FECHA_COMPROMETIDA) 
                        FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK)
                        WHERE (b.ID_Proyecto = p.ID OR b.Numero_Proyecto_Limpio {_SQL_P_NUMERO_LIMPIO_IN}) AND b.FECHA_COMPROMETIDA IS NOT NULL
                    ) AS fecha_compromiso_sga,
                    (
                        SELECT MAX(b.FECHA_REALIZACION) 
                        FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK)
                        WHERE (b.ID_Proyecto = p.ID OR b.Numero_Proyecto_Limpio {_SQL_P_NUMERO_LIMPIO_IN}) AND b.FECHA_REALIZACION IS NOT NULL
                    ) AS fecha_cierre_sga,
                    (SELECT COUNT(1) FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK) WHERE b.ID_Proyecto = p.ID OR b.Numero_Proyecto_Limpio {_SQL_P_NUMERO_LIMPIO_IN}) AS total_solots,
                    (SELECT COUNT(1) FROM dbo.registrosRF_SD_SM sd WITH (NOLOCK) WHERE sd.ID_Proyecto = p.ID OR sd.Numero_Proyecto_Limpio {_SQL_P_NUMERO_LIMPIO_IN}) AS total_tickets,
                    (SELECT COUNT(1) FROM dbo.registrosSM_RFC rfc WITH (NOLOCK) WHERE rfc.ID_Proyecto = p.ID OR rfc.Numero_Proyecto_Limpio {_SQL_P_NUMERO_LIMPIO_IN}) AS total_rfcs,
                    (
                        SELECT SUM(CASE 
                            WHEN b.ESTADO_OTP NOT IN ('Cerrada', '5- Ejecutada', '5- Ejecutada Tareas Pendientes', 'Abortado', 'En Aborcion', 'Eliminada', 'Aprobado') 
                                 AND b.FECHA_COMPROMETIDA < CAST(GETDATE() AS DATE) THEN 1 
                            ELSE 0 
                        END)
                        FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK)
                        WHERE (b.ID_Proyecto = p.ID OR b.Numero_Proyecto_Limpio {_SQL_P_NUMERO_LIMPIO_IN})
                          AND b.FECHA_COMPROMETIDA IS NOT NULL
                    ) AS solots_vencidas,
                    (
                        SELECT SUM(CASE 
                            WHEN b.ESTADO_OTP NOT IN ('Cerrada', '5- Ejecutada', '5- Ejecutada Tareas Pendientes', 'Abortado', 'En Aborcion', 'Eliminada', 'Aprobado') 
                                 AND b.FECHA_COMPROMETIDA >= CAST(GETDATE() AS DATE) 
                                 AND b.FECHA_COMPROMETIDA <= DATEADD(day, 5, CAST(GETDATE() AS DATE)) THEN 1 
                            ELSE 0 
                        END)
                        FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK)
                        WHERE (b.ID_Proyecto = p.ID OR b.Numero_Proyecto_Limpio {_SQL_P_NUMERO_LIMPIO_IN})
                          AND b.FECHA_COMPROMETIDA IS NOT NULL
                    ) AS solots_por_vencer,
                    (
                        SELECT SUM(CASE 
                            WHEN sd.STATUS NOT IN ('Cerrado', 'Resuelto') 
                                 AND DATEDIFF(day, TRY_CAST(sd.SUBMIT_DATE AS DATETIME2), GETDATE()) > 14 THEN 1 
                            ELSE 0 
                        END)
                        FROM dbo.registrosRF_SD_SM sd WITH (NOLOCK)
                        WHERE (sd.ID_Proyecto = p.ID OR sd.Numero_Proyecto_Limpio {_SQL_P_NUMERO_LIMPIO_IN})
                          AND sd.SUBMIT_DATE IS NOT NULL
                    ) AS tickets_criticos,
                    (
                        SELECT SUM(CASE 
                            WHEN sd.STATUS NOT IN ('Cerrado', 'Resuelto') 
                                 AND DATEDIFF(day, TRY_CAST(sd.SUBMIT_DATE AS DATETIME2), GETDATE()) > 7 
                                 AND DATEDIFF(day, TRY_CAST(sd.SUBMIT_DATE AS DATETIME2), GETDATE()) <= 14 THEN 1 
                            ELSE 0 
                        END)
                        FROM dbo.registrosRF_SD_SM sd WITH (NOLOCK)
                        WHERE (sd.ID_Proyecto = p.ID OR sd.Numero_Proyecto_Limpio {_SQL_P_NUMERO_LIMPIO_IN})
                          AND sd.SUBMIT_DATE IS NOT NULL
                    ) AS tickets_atencion,
                    (
                        SELECT TOP 1 b.PRO_ING_PROYECTO 
                        FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK)
                        WHERE (
                            b.ID_Proyecto = p.ID
                            OR b.Numero_Proyecto_Limpio = LTRIM(RTRIM(p.Numero_Proyecto))
                            OR b.Numero_Proyecto_Limpio = (
                                CASE 
                                    WHEN p.Numero_Proyecto LIKE '000%' THEN SUBSTRING(LTRIM(RTRIM(p.Numero_Proyecto)), 4, 50)
                                    ELSE LTRIM(RTRIM(p.Numero_Proyecto))
                                end
                            )
                            OR b.NRO_PROYECTO = LTRIM(RTRIM(p.Numero_Proyecto))
                            OR b.NRO_PROYECTO = ('000' + LTRIM(RTRIM(p.Numero_Proyecto)))
                        )
                          AND b.PRO_ING_PROYECTO IS NOT NULL 
                          AND LTRIM(RTRIM(b.PRO_ING_PROYECTO)) <> ''
                        ORDER BY 
                            CASE WHEN b.FECHA_INSERT IS NOT NULL THEN 0 ELSE 1 END,
                            b.FECHA_INSERT DESC, 
                            b.id DESC
                    ) AS Solicitante
                FROM dbo.Proyectos p WITH (NOLOCK)
                WHERE p.ID = %s
            """
            cursor.execute(sql, (proyecto_id,))
            row = cursor.fetchone()
            if not row:
                return None
            res = serialize_row(row)
            res['salud'] = calcular_salud_proyecto(res)
            return res
    finally:
        conn.close()

def get_solots_by_proyecto(proyecto_id, numero_proyecto=None, con_asociados=False):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            grupo = _grupo_para_detalle(cursor, proyecto_id, numero_proyecto) if con_asociados else None
            sql = f"""
                SELECT 
                    b.ID_CLI,
                    b.NRO_PROYECTO,
                    b.ID_OTP,
                    b.DESCR_OTP,
                    b.ESTADO_OTP,
                    b.FECHA_COMPROMETIDA,
                    b.FECHA_INSERT,
                    b.FECHA_REALIZACION,
                    b.PLAZO_CONTRATO,
                    b.PRODUCTO,
                    b.SERVICIO,
                    b.NRO_SERVICIO,
                    b.TIPO_OTP,
                    b.STATUS_SOLOT,
                    b.ASIGNADO_OTP,
                    b.GRUPO_ASIGNADO_OTP{_sql_columnas_origen('b', grupo)}
                FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK)
                WHERE b.ID_Proyecto = %s
            """
            params = [proyecto_id]
            if numero_proyecto and str(numero_proyecto).strip():
                sql += " OR b.Numero_Proyecto_Limpio IN (%s, %s)"
                params.extend(_numero_proyecto_limpio_keys(numero_proyecto))
            if grupo:
                sql += _sql_clausulas_grupo('b', grupo, params)

            sql += " ORDER BY b.FECHA_INSERT DESC, b.ID_OTP DESC"
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            if grupo:
                _etiquetar_origen(rows, grupo)
            return serialize_rows(rows)
    finally:
        conn.close()

def get_tickets_by_proyecto(proyecto_id, numero_proyecto=None, con_asociados=False):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            grupo = _grupo_para_detalle(cursor, proyecto_id, numero_proyecto) if con_asociados else None
            sql = f"""
                SELECT 
                    sd.CC_INCIDENT_ID,
                    sd.REQUESTOR_NAME,
                    sd.STATUS,
                    sd.SUBMIT_DATE,
                    sd.CLOSE_DATE,
                    sd.BRIEF_DESCRIPTION,
                    sd.CATEGORY,
                    sd.CC_DETALLE_SERVICIO,
                    sd.ASSIGNED_GROUP,
                    sd.ASSIGNED_TO,
                    sd.RF_ID,
                    sd.CURRENT_PHASE,
                    sd.SUBCATEGORY{_sql_columnas_origen('sd', grupo)}
                FROM dbo.registrosRF_SD_SM sd WITH (NOLOCK)
                WHERE sd.ID_Proyecto = %s
            """
            params = [proyecto_id]
            if numero_proyecto and str(numero_proyecto).strip():
                sql += " OR sd.Numero_Proyecto_Limpio IN (%s, %s)"
                params.extend(_numero_proyecto_limpio_keys(numero_proyecto))
            if grupo:
                sql += _sql_clausulas_grupo('sd', grupo, params)

            sql += " ORDER BY sd.SUBMIT_DATE DESC, sd.CC_INCIDENT_ID DESC"
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            if grupo:
                _etiquetar_origen(rows, grupo)
            return serialize_rows(rows)
    finally:
        conn.close()

def get_rfcs_by_proyecto(proyecto_id, numero_proyecto=None, con_asociados=False):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            grupo = _grupo_para_detalle(cursor, proyecto_id, numero_proyecto) if con_asociados else None
            sql = f"""
                SELECT 
                    rfc.NUMBER,
                    rfc.BRIEF_DESCRIPTION,
                    rfc.DESCRIPTION,
                    rfc.REQUESTED_BY,
                    rfc.CLOSE_TIME,
                    rfc.CC_PROYECT_NUMBER,
                    rfc.CC_SERVICIO_PADRE,
                    rfc.ASSIGN_DEPT,
                    rfc.ASSIGNED_TO,
                    rfc.COORDINATOR,
                    rfc.ORIG_DATE_ENTERED{_sql_columnas_origen('rfc', grupo)}
                FROM dbo.registrosSM_RFC rfc WITH (NOLOCK)
                WHERE rfc.ID_Proyecto = %s
            """
            params = [proyecto_id]
            if numero_proyecto and str(numero_proyecto).strip():
                sql += " OR rfc.Numero_Proyecto_Limpio IN (%s, %s)"
                params.extend(_numero_proyecto_limpio_keys(numero_proyecto))
            if grupo:
                sql += _sql_clausulas_grupo('rfc', grupo, params)

            sql += " ORDER BY rfc.ORIG_DATE_ENTERED DESC, rfc.NUMBER DESC"
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            if grupo:
                _etiquetar_origen(rows, grupo)
            return serialize_rows(rows)
    finally:
        conn.close()

def kpis_vacios() -> dict:
    """KPIs en cero (misma estructura que get_dashboard_kpis) para usuarios sin proyectos en su alcance."""
    return {
        'total_proyectos': 0,
        'proyectos_en_curso': 0,
        'proyectos_en_revision': 0,
        'proyectos_atendidos': 0,
        'proyectos_cerrados': 0,
        'pendientes_asignar': 0,
        'efectividad': 0.0,
        'total_tickets': 0,
        'total_rfcs': 0,
        'salud': {'saludables': 0, 'en_riesgo': 0, 'criticos': 0, 'sin_datos': 0}
    }

def get_dashboard_kpis(lt_filter=None, restringido=False):
    """
    KPIs del dashboard. Con restringido=True (usuario con alcance limitado a su LTI) los pendientes de asignar
    también se calculan dentro de ese alcance; si no, se mantiene el conteo global.
    """
    if lt_filter in (None, '', '__ALL__'):
        lt_filter = None
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Total Proyectos
            sql_proy = "SELECT COUNT(1) as total FROM dbo.Proyectos p WITH (NOLOCK) WHERE (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')"
            params_proy = []
            if lt_filter == "__UNASSIGNED__":
                sql_proy += " AND (p.LT_Asignado IS NULL OR LTRIM(RTRIM(p.LT_Asignado)) = '' OR LOWER(LTRIM(RTRIM(p.LT_Asignado))) = 'sin asignar')"
            elif lt_filter:
                sql_proy += " AND p.LT_Asignado = %s"
                params_proy.append(lt_filter)
            cursor.execute(sql_proy, tuple(params_proy))
            total_proyectos = cursor.fetchone()['total']

            # 2. Proyectos En Curso (Estado = 'En ejecucion' o 'En revision')
            sql_en_curso = "SELECT COUNT(1) as total FROM dbo.Proyectos p WITH (NOLOCK) WHERE p.Estado IN ('En ejecucion', 'En revision') AND (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')"
            params_ec = []
            if lt_filter == "__UNASSIGNED__":
                sql_en_curso += " AND (p.LT_Asignado IS NULL OR LTRIM(RTRIM(p.LT_Asignado)) = '' OR LOWER(LTRIM(RTRIM(p.LT_Asignado))) = 'sin asignar')"
            elif lt_filter:
                sql_en_curso += " AND p.LT_Asignado = %s"
                params_ec.append(lt_filter)
            cursor.execute(sql_en_curso, tuple(params_ec))
            proyectos_en_curso = cursor.fetchone()['total']

            # 2b. Proyectos En Revisión (Estado = 'En revision')
            sql_en_revision = "SELECT COUNT(1) as total FROM dbo.Proyectos p WITH (NOLOCK) WHERE p.Estado = 'En revision' AND (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')"
            params_er = []
            if lt_filter == "__UNASSIGNED__":
                sql_en_revision += " AND (p.LT_Asignado IS NULL OR LTRIM(RTRIM(p.LT_Asignado)) = '' OR LOWER(LTRIM(RTRIM(p.LT_Asignado))) = 'sin asignar')"
            elif lt_filter:
                sql_en_revision += " AND p.LT_Asignado = %s"
                params_er.append(lt_filter)
            cursor.execute(sql_en_revision, tuple(params_er))
            proyectos_en_revision = cursor.fetchone()['total']

            # 3. Proyectos Cerrados (Estado = 'Cerrado'; 'Atendido' es el estado legado)
            sql_atendidos = "SELECT COUNT(1) as total FROM dbo.Proyectos p WITH (NOLOCK) WHERE p.Estado IN ('Cerrado', 'Atendido') AND (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')"
            params_at = []
            if lt_filter == "__UNASSIGNED__":
                sql_atendidos += " AND (p.LT_Asignado IS NULL OR LTRIM(RTRIM(p.LT_Asignado)) = '' OR LOWER(LTRIM(RTRIM(p.LT_Asignado))) = 'sin asignar')"
            elif lt_filter:
                sql_atendidos += " AND p.LT_Asignado = %s"
                params_at.append(lt_filter)
            cursor.execute(sql_atendidos, tuple(params_at))
            proyectos_atendidos = cursor.fetchone()['total']

            # 4. Proyectos Pendientes de Asignar (LT_Asignado NULL o vacío global)
            sql_pendientes = """
                SELECT COUNT(1) as total 
                FROM dbo.Proyectos p WITH (NOLOCK)
                WHERE (p.LT_Asignado IS NULL OR LTRIM(RTRIM(p.LT_Asignado)) = '' OR LOWER(LTRIM(RTRIM(p.LT_Asignado))) = 'sin asignar')
                  AND (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')
            """
            params_pend = []
            if restringido and lt_filter and lt_filter != "__UNASSIGNED__":
                sql_pendientes += " AND p.LT_Asignado = %s"
                params_pend.append(lt_filter)
            cursor.execute(sql_pendientes, tuple(params_pend))
            pendientes_asignar = cursor.fetchone()['total']

            # 5. Efectividad
            efectividad = round((proyectos_atendidos / total_proyectos * 100), 1) if total_proyectos > 0 else 0.0

            # 6. Total Tickets
            sql_tickets = f"""
                SELECT COUNT(1) as total 
                FROM dbo.registrosRF_SD_SM sd WITH (NOLOCK)
                WHERE EXISTS (
                    SELECT 1 FROM dbo.Proyectos p WITH (NOLOCK)
                    WHERE (sd.ID_Proyecto = p.ID OR sd.Numero_Proyecto_Limpio {_SQL_P_NUMERO_LIMPIO_IN})
                      AND (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')
            """
            params_t = []
            if lt_filter == "__UNASSIGNED__":
                sql_tickets += " AND (p.LT_Asignado IS NULL OR LTRIM(RTRIM(p.LT_Asignado)) = '' OR LOWER(LTRIM(RTRIM(p.LT_Asignado))) = 'sin asignar')"
            elif lt_filter:
                sql_tickets += " AND p.LT_Asignado = %s"
                params_t.append(lt_filter)
            sql_tickets += ")"
            cursor.execute(sql_tickets, tuple(params_t))
            total_tickets = cursor.fetchone()['total']

            # 7. Total RFCs
            sql_rfcs = f"""
                SELECT COUNT(1) as total 
                FROM dbo.registrosSM_RFC rfc WITH (NOLOCK)
                WHERE EXISTS (
                    SELECT 1 FROM dbo.Proyectos p WITH (NOLOCK)
                    WHERE (rfc.ID_Proyecto = p.ID OR rfc.Numero_Proyecto_Limpio {_SQL_P_NUMERO_LIMPIO_IN})
                      AND (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')
            """
            params_r = []
            if lt_filter == "__UNASSIGNED__":
                sql_rfcs += " AND (p.LT_Asignado IS NULL OR LTRIM(RTRIM(p.LT_Asignado)) = '' OR LOWER(LTRIM(RTRIM(p.LT_Asignado))) = 'sin asignar')"
            elif lt_filter:
                sql_rfcs += " AND p.LT_Asignado = %s"
                params_r.append(lt_filter)
            sql_rfcs += ")"
            cursor.execute(sql_rfcs, tuple(params_r))
            total_rfcs = cursor.fetchone()['total']

            # 8. KPIs de Salud Operacional
            sql_salud_kpis = """
                WITH """ + _SQL_STATS_CTES + """
                SELECT 
                    SUM(CASE 
                        WHEN ISNULL(ss.total_solots, 0) = 0 AND ISNULL(ts.total_tickets, 0) = 0 THEN 1 
                        ELSE 0 
                    END) AS sin_datos,
                    SUM(CASE 
                        WHEN (ISNULL(ss.total_solots, 0) > 0 OR ISNULL(ts.total_tickets, 0) > 0)
                             AND (ISNULL(ss.solots_vencidas, 0) > 0 OR ISNULL(ts.tickets_criticos, 0) > 0) THEN 1 
                        ELSE 0 
                    END) AS criticos,
                    SUM(CASE 
                        WHEN (ISNULL(ss.total_solots, 0) > 0 OR ISNULL(ts.total_tickets, 0) > 0)
                             AND (ISNULL(ss.solots_vencidas, 0) = 0 AND ISNULL(ts.tickets_criticos, 0) = 0)
                             AND (ISNULL(ss.solots_por_vencer, 0) > 0 OR ISNULL(ts.tickets_atencion, 0) > 0) THEN 1 
                        ELSE 0 
                    END) AS en_riesgo,
                    SUM(CASE 
                        WHEN (ISNULL(ss.total_solots, 0) > 0 OR ISNULL(ts.total_tickets, 0) > 0)
                             AND (ISNULL(ss.solots_vencidas, 0) = 0 AND ISNULL(ts.tickets_criticos, 0) = 0)
                             AND (ISNULL(ss.solots_por_vencer, 0) = 0 AND ISNULL(ts.tickets_atencion, 0) = 0) THEN 1 
                        ELSE 0 
                    END) AS saludables
                FROM dbo.Proyectos p WITH (NOLOCK)
                LEFT JOIN SolotStats ss ON p.ID = ss.ID_Proyecto
                LEFT JOIN TicketStats ts ON p.ID = ts.ID_Proyecto
                WHERE (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')
            """
            params_s = []
            if lt_filter == "__UNASSIGNED__":
                sql_salud_kpis += " AND (p.LT_Asignado IS NULL OR LTRIM(RTRIM(p.LT_Asignado)) = '' OR LOWER(LTRIM(RTRIM(p.LT_Asignado))) = 'sin asignar')"
            elif lt_filter:
                sql_salud_kpis += " AND p.LT_Asignado = %s"
                params_s.append(lt_filter)
            cursor.execute(sql_salud_kpis, tuple(params_s))
            salud_row = cursor.fetchone() or {}

            return {
                'total_proyectos': total_proyectos,
                'proyectos_en_curso': proyectos_en_curso,
                'proyectos_en_revision': proyectos_en_revision,
                'proyectos_atendidos': proyectos_atendidos,
                'proyectos_cerrados': proyectos_atendidos,
                'pendientes_asignar': pendientes_asignar,
                'efectividad': efectividad,
                'total_tickets': total_tickets,
                'total_rfcs': total_rfcs,
                'salud': {
                    'saludables': int(salud_row.get('saludables') or 0),
                    'en_riesgo': int(salud_row.get('en_riesgo') or 0),
                    'criticos': int(salud_row.get('criticos') or 0),
                    'sin_datos': int(salud_row.get('sin_datos') or 0)
                }
            }
    finally:
        conn.close()

# -----------------------------------------------------------------------------
# DIRECT TABLE SEARCH CON MULTI-TAGS / PARÁMETROS EN CADENA
# -----------------------------------------------------------------------------
def search_direct_tables(tags: Union[List[str], str], target_table: str = "all", limit: int = 150):
    if isinstance(tags, str):
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if not tag_list:
            tag_list = [tags.strip()]
    else:
        tag_list = [t.strip() for t in tags if t and str(t).strip()]

    if not tag_list:
        tag_list = [""]

    results = {
        "proyectos": [],
        "solots": [],
        "tickets": [],
        "rfcs": [],
        "counts": {
            "proyectos": 0,
            "solots": 0,
            "tickets": 0,
            "rfcs": 0,
            "total": 0
        }
    }

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. dbo.Proyectos
            if target_table in ("all", "proyectos"):
                conds = []
                params = []
                for t in tag_list:
                    conds.append("(Cliente LIKE %s OR Numero_Proyecto LIKE %s OR Detalle LIKE %s OR Comentario LIKE %s OR LT_Asignado LIKE %s OR Estado LIKE %s OR Tipo_Servicio LIKE %s)")
                    term = f"%{t}%"
                    params.extend([term, term, term, term, term, term, term])

                sql_p = f"""
                    SELECT TOP ({limit})
                        ID, Cliente, Numero_Proyecto, LT_Asignado, Estado, Detalle, Comentario, Tipo_Servicio, Creado
                    FROM dbo.Proyectos
                    WHERE {' AND '.join(conds)}
                    ORDER BY 
                        CASE WHEN Creado IS NOT NULL THEN 0 ELSE 1 END,
                        Creado DESC, 
                        ID DESC
                """
                cursor.execute(sql_p, tuple(params))
                results["proyectos"] = serialize_rows(cursor.fetchall())
                results["counts"]["proyectos"] = len(results["proyectos"])

            # 2. dbo.CT_BACKLOG_OPERACIONES2
            if target_table in ("all", "solots"):
                conds = []
                params = []
                for t in tag_list:
                    conds.append("(ID_OTP LIKE %s OR NRO_PROYECTO LIKE %s OR CLI_CLIENTE LIKE %s OR DESCR_OTP LIKE %s OR ID_CLI LIKE %s OR RUT_CLIENTE LIKE %s OR ASIGNADO_OTP LIKE %s OR PRODUCTO LIKE %s OR SERVICIO LIKE %s OR ESTADO_OTP LIKE %s OR GRUPO_ASIGNADO_OTP LIKE %s)")
                    term = f"%{t}%"
                    params.extend([term, term, term, term, term, term, term, term, term, term, term])

                sql_s = f"""
                    SELECT TOP ({limit})
                        ID_CLI, NRO_PROYECTO, CLI_CLIENTE, ID_OTP, DESCR_OTP, ESTADO_OTP, 
                        FECHA_COMPROMETIDA, FECHA_INSERT, FECHA_REALIZACION, PLAZO_CONTRATO, PRODUCTO, SERVICIO, 
                        NRO_SERVICIO, ASIGNADO_OTP, GRUPO_ASIGNADO_OTP, RUT_CLIENTE, ID_Proyecto
                    FROM dbo.CT_BACKLOG_OPERACIONES2
                    WHERE {' AND '.join(conds)}
                    ORDER BY FECHA_INSERT DESC, id DESC
                """
                cursor.execute(sql_s, tuple(params))
                results["solots"] = serialize_rows(cursor.fetchall())
                results["counts"]["solots"] = len(results["solots"])

            # 3. dbo.registrosRF_SD_SM
            if target_table in ("all", "tickets"):
                conds = []
                params = []
                for t in tag_list:
                    conds.append("(CC_INCIDENT_ID LIKE %s OR BRIEF_DESCRIPTION LIKE %s OR REQUESTOR_NAME LIKE %s OR RF_ID LIKE %s OR CC_DETALLE_SERVICIO LIKE %s OR ASSIGNED_TO LIKE %s OR ASSIGNED_GROUP LIKE %s OR STATUS LIKE %s OR CATEGORY LIKE %s)")
                    term = f"%{t}%"
                    params.extend([term, term, term, term, term, term, term, term, term])

                sql_t = f"""
                    SELECT TOP ({limit})
                        CC_INCIDENT_ID, REQUESTOR_NAME, STATUS, SUBMIT_DATE, CLOSE_DATE, 
                        BRIEF_DESCRIPTION, CATEGORY, CC_DETALLE_SERVICIO, ASSIGNED_GROUP, 
                        ASSIGNED_TO, RF_ID, CURRENT_PHASE, SUBCATEGORY, ID_Proyecto
                    FROM dbo.registrosRF_SD_SM
                    WHERE {' AND '.join(conds)}
                    ORDER BY SUBMIT_DATE DESC, CC_INCIDENT_ID DESC
                """
                cursor.execute(sql_t, tuple(params))
                results["tickets"] = serialize_rows(cursor.fetchall())
                results["counts"]["tickets"] = len(results["tickets"])

            # 4. dbo.registrosSM_RFC
            if target_table in ("all", "rfcs"):
                conds = []
                params = []
                for t in tag_list:
                    conds.append("(NUMBER LIKE %s OR BRIEF_DESCRIPTION LIKE %s OR DESCRIPTION LIKE %s OR REQUESTED_BY LIKE %s OR CC_PROYECT_NUMBER LIKE %s OR ASSIGNED_TO LIKE %s OR ASSIGN_DEPT LIKE %s OR CC_SERVICIO_PADRE LIKE %s)")
                    term = f"%{t}%"
                    params.extend([term, term, term, term, term, term, term, term])

                sql_r = f"""
                    SELECT TOP ({limit})
                        NUMBER, BRIEF_DESCRIPTION, DESCRIPTION, REQUESTED_BY, CLOSE_TIME, 
                        CC_PROYECT_NUMBER, CC_SERVICIO_PADRE, ASSIGN_DEPT, ASSIGNED_TO, 
                        COORDINATOR, ORIG_DATE_ENTERED, ID_Proyecto
                    FROM dbo.registrosSM_RFC
                    WHERE {' AND '.join(conds)}
                    ORDER BY ORIG_DATE_ENTERED DESC, NUMBER DESC
                """
                cursor.execute(sql_r, tuple(params))
                results["rfcs"] = serialize_rows(cursor.fetchall())
                results["counts"]["rfcs"] = len(results["rfcs"])

            results["counts"]["total"] = (
                results["counts"]["proyectos"] + 
                results["counts"]["solots"] + 
                results["counts"]["tickets"] + 
                results["counts"]["rfcs"]
            )
            return results
    finally:
        conn.close()

# -----------------------------------------------------------------------------
# MÓDULO SOLICITUD LTI
# -----------------------------------------------------------------------------
def get_solicitud_catalogos():
    """Retorna los catálogos necesarios para el formulario de Solicitud LTI."""
    lideres = get_lideres_list()
    estados = [
        "Generado"
    ]
    tipos_servicio = [
        "Otros"
    ]
    return {
        "lideres": lideres,
        "estados": estados,
        "tipos_servicio": tipos_servicio
    }

def get_solots_liray_by_proyecto(numero_proyecto: str) -> list:
    """
    Obtiene los solots asociados a un N° de proyecto desde dbo.CT_BACKLOG_OPERACIONES2
    cuya descripción (DESCR_OTP) contenga la palabra 'LIRAY' (case-insensitive),
    ordenados alfabéticamente por PRODUCTO y luego por ID_OTP.
    """
    if not numero_proyecto:
        return []
    
    num_clean = str(numero_proyecto).strip()
    num_without_zeros = num_clean.lstrip('0')
    num_with_zeros = f"000{num_without_zeros}" if num_without_zeros else num_clean

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    ID_OTP, 
                    DESCR_OTP, 
                    PRODUCTO, 
                    SERVICIO, 
                    NRO_SERVICIO 
                FROM dbo.CT_BACKLOG_OPERACIONES2 WITH (NOLOCK)
                WHERE (
                    LTRIM(RTRIM(NRO_PROYECTO)) IN (%s, %s, %s)
                    OR LTRIM(RTRIM(Numero_Proyecto_Limpio)) IN (%s, %s, %s)
                )
                AND UPPER(DESCR_OTP) LIKE '%LIRAY%'
                ORDER BY PRODUCTO ASC, ID_OTP ASC
            """, (num_clean, num_without_zeros, num_with_zeros, num_clean, num_without_zeros, num_with_zeros))
            rows = cursor.fetchall()
            results = []
            seen_otps = set()
            for r in rows:
                otp_id = r.get("ID_OTP")
                if otp_id is not None and otp_id in seen_otps:
                    continue
                if otp_id is not None:
                    seen_otps.add(otp_id)

                descr = str(r.get("DESCR_OTP") or "").strip()
                prod = str(r.get("PRODUCTO") or "").strip()
                serv = str(r.get("SERVICIO") or "").strip()
                nro_serv = str(r.get("NRO_SERVICIO") or "").strip()

                results.append({
                    "id_otp": otp_id,
                    "descr_otp": descr,
                    "producto": prod,
                    "servicio": serv if serv else None,
                    "nro_servicio": nro_serv if nro_serv else None
                })
            return results
    finally:
        conn.close()

def format_solots_liray_text(solots: list) -> str:
    """
    Formatea una lista de solots Liray en un texto estructurado para el textarea 'Detalle'.
    """
    if not solots:
        return ""
    
    valid_solots = [s for s in solots if isinstance(s, dict)]
    if not valid_solots:
        return ""

    lines = [
        "SOLOTS ASOCIADOS (LIRAY):",
        "=" * 50
    ]
    for idx, s in enumerate(valid_solots, 1):
        solot_num = s.get("id_otp") if s.get("id_otp") is not None else "S/N"
        producto = str(s.get("producto") or "").strip() or "N/A"
        servicio = str(s.get("servicio") or "").strip() or "N/A"
        nro_servicio = str(s.get("nro_servicio") or "").strip() or "N/A"
        descr = str(s.get("descr_otp") or "").strip() or "Sin descripción"
        
        lines.append(f"[{idx}] Solot: {solot_num}")
        lines.append(f"    • Producto: {producto}")
        lines.append(f"    • Servicio: {servicio}")
        lines.append(f"    • N° Servicio: {nro_servicio}")
        lines.append(f"    • Descripción: {descr}")
        if idx < len(valid_solots):
            lines.append("-" * 35)
            
    return "\n".join(lines)

def search_backlog_proyectos_autocomplete(query: str, limit: int = 12):
    """Busca proyectos en CT_BACKLOG_OPERACIONES2 por NRO_PROYECTO, Numero_Proyecto_Limpio o CLI_CLIENTE y pre-calcula los Solots Liray sugeridos."""
    if not query or len(str(query).strip()) < 2:
        return []
    
    term = f"%{str(query).strip()}%"
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT TOP (%s)
                    b.NRO_PROYECTO,
                    b.Numero_Proyecto_Limpio,
                    b.CLI_CLIENTE,
                    b.PRO_ING_PROYECTO,
                    b.RUT_CLIENTE
                FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK)
                WHERE 
                    b.NRO_PROYECTO LIKE %s 
                    OR b.Numero_Proyecto_Limpio LIKE %s 
                    OR b.CLI_CLIENTE LIKE %s
                ORDER BY b.NRO_PROYECTO DESC
            """, (limit * 2, term, term, term))
            rows = cursor.fetchall()
            results = []
            seen_projs = set()
            for r in rows:
                proj_num = (r.get("NRO_PROYECTO") or r.get("Numero_Proyecto_Limpio") or "").strip()
                if not proj_num:
                    continue
                proj_key = proj_num.lstrip('0') or proj_num
                if proj_key in seen_projs:
                    continue
                seen_projs.add(proj_key)

                solots_liray = get_solots_liray_by_proyecto(proj_num) if proj_num else []
                detalle_sug = format_solots_liray_text(solots_liray) if solots_liray else None
                
                results.append({
                    "nro_proyecto": r.get("NRO_PROYECTO"),
                    "numero_proyecto_limpio": r.get("Numero_Proyecto_Limpio"),
                    "cliente": r.get("CLI_CLIENTE"),
                    "solicitante": clean_solicitante(r.get("PRO_ING_PROYECTO")),
                    "rut_cliente": r.get("RUT_CLIENTE"),
                    "has_solots_liray": len(solots_liray) > 0,
                    "solots_liray_count": len(solots_liray),
                    "solots_liray": solots_liray,
                    "detalle_sugerido": detalle_sug
                })
                if len(results) >= limit:
                    break
            return results
    finally:
        conn.close()

# Alias for search function
search_backlog_autocomplete = search_backlog_proyectos_autocomplete

def check_proyecto_exists(numero_proyecto: str):
    """Verifica si un proyecto ya existe en dbo.Proyectos considerando prefijos con y sin '000'."""
    if not numero_proyecto:
        return None
    num_clean = str(numero_proyecto).strip()
    num_without_zeros = num_clean.lstrip('0')
    num_with_zeros = f"000{num_without_zeros}" if num_without_zeros else num_clean

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT TOP 1 ID, Cliente, Numero_Proyecto, LT_Asignado, Estado, Detalle, Comentario, Tipo_Servicio, Creado, Solicitante
                FROM dbo.Proyectos WITH (NOLOCK)
                WHERE LTRIM(RTRIM(Numero_Proyecto)) = %s 
                   OR LTRIM(RTRIM(Numero_Proyecto)) = %s
                   OR LTRIM(RTRIM(Numero_Proyecto)) = %s
            """, (num_clean, num_without_zeros, num_with_zeros))
            existing = cursor.fetchone()
            if existing:
                return serialize_row(existing)
            return None
    finally:
        conn.close()

def create_solicitud_lti(
    cliente: str, 
    numero_proyecto: str, 
    lt_asignado: Optional[str] = None, 
    estado: str = "Generado", 
    fecha_solicitud: str = None, 
    detalle: str = "", 
    solicitante: Union[str, None] = None, 
    tipo_servicio: Union[str, None] = "Otros"
) -> dict:
    """
    Inserta una nueva solicitud en dbo.Proyectos con Tipo_Servicio='Otros'.
    El Estado es 'Generado' salvo que se pida 'En ejecucion' (asignación directa de LTI desde el backlog).
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Normalizar y verificar duplicados
            num_clean = str(numero_proyecto).strip()
            num_without_zeros = num_clean.lstrip('0')
            num_with_zeros = f"000{num_without_zeros}" if num_without_zeros else num_clean

            cursor.execute("""
                SELECT TOP 1 ID, Cliente, Numero_Proyecto, LT_Asignado, Estado, Detalle, Comentario, Tipo_Servicio, Creado, Solicitante
                FROM dbo.Proyectos WITH (NOLOCK)
                WHERE LTRIM(RTRIM(Numero_Proyecto)) = %s 
                   OR LTRIM(RTRIM(Numero_Proyecto)) = %s
                   OR LTRIM(RTRIM(Numero_Proyecto)) = %s
            """, (num_clean, num_without_zeros, num_with_zeros))
            existing = cursor.fetchone()
            if existing:
                return {
                    "success": False,
                    "error": "duplicate",
                    "existing": serialize_row(existing)
                }

            # 2. Calcular nuevo ID secuencial con bloqueo exclusivo para prevenir condiciones de carrera
            cursor.execute("SELECT ISNULL(MAX(ID), 0) + 1 AS next_id FROM dbo.Proyectos WITH (UPDLOCK, HOLDLOCK)")
            next_id_row = cursor.fetchone()
            next_id = int(next_id_row['next_id'])

            # 3. Formatear fecha de solicitud
            try:
                now = datetime.datetime.now()
                parsed_date = datetime.datetime.strptime(str(fecha_solicitud)[:10], '%Y-%m-%d')
                dt_to_insert = parsed_date.replace(hour=now.hour, minute=now.minute, second=now.second)
            except Exception:
                dt_to_insert = datetime.datetime.now()

            # Normalizar número de proyecto formateado
            formatted_num = format_numero_proyecto(num_clean)
            lt_val = lt_asignado.strip()[:50] if (lt_asignado and str(lt_asignado).strip()) else None

            # 4. Inserción en dbo.Proyectos: Estado 'Generado' (o 'En ejecucion' si se asigna LTI) y Tipo_Servicio = 'Otros'
            estado_inicial = "En ejecucion" if estado == "En ejecucion" else "Generado"
            insert_sql = """
                INSERT INTO dbo.Proyectos (
                    ID,
                    Cliente,
                    Numero_Proyecto,
                    LT_Asignado,
                    Estado,
                    Detalle,
                    Tipo_Servicio,
                    Creado,
                    Solicitante
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_sql, (
                next_id,
                cliente.strip()[:100],
                formatted_num[:50],
                lt_val,
                estado_inicial,  # Solo 'Generado' o 'En ejecucion'
                detalle.strip(),
                'Otros',     # Fijo y Oculto: Siempre 'Otros'
                dt_to_insert,
                (solicitante.strip() if solicitante else None)[:50] if solicitante else None
            ))

            # 5. Obtener y retornar el registro insertado
            cursor.execute("SELECT * FROM dbo.Proyectos WHERE ID = %s", (next_id,))
            created_row = cursor.fetchone()
            conn.commit()

            if not created_row:
                created_row = {
                    "ID": next_id,
                    "Cliente": cliente.strip()[:100],
                    "Numero_Proyecto": formatted_num[:50],
                    "LT_Asignado": lt_val,
                    "Estado": estado_inicial,
                    "Detalle": detalle.strip(),
                    "Tipo_Servicio": "Otros",
                    "Creado": dt_to_insert,
                    "Solicitante": (solicitante.strip() if solicitante else None)[:50] if solicitante else None
                }

            return {
                "success": True,
                "data": serialize_row(created_row)
            }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {
            "success": False,
            "error": f"Error en base de datos: {str(e)}"
        }
    finally:
        conn.close()

# Alias for compatibility
crear_solicitud_proyecto = create_solicitud_lti

# -----------------------------------------------------------------------------
# BITÁCORA Y ADJUNTOS DE PROYECTOS (dbo.Proyecto_Bitacora / dbo.Proyecto_Adjuntos)
# -----------------------------------------------------------------------------
def init_bitacora_tables():
    """Crea de forma idempotente las tablas de bitácora, adjuntos y asociaciones de proyectos (solo aditivo, nunca borra ni altera)."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
            IF OBJECT_ID('dbo.Proyecto_Bitacora', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.Proyecto_Bitacora (
                    ID INT IDENTITY(1,1) PRIMARY KEY,
                    Proyecto_ID NUMERIC(18,0) NOT NULL,
                    Tipo VARCHAR(20) NOT NULL,
                    Texto NVARCHAR(MAX) NOT NULL,
                    Estado_Anterior NVARCHAR(50) NULL,
                    Estado_Nuevo NVARCHAR(50) NULL,
                    Autor_Username VARCHAR(100) NULL,
                    Autor_Nombre NVARCHAR(150) NULL,
                    Creado DATETIME NOT NULL DEFAULT GETDATE()
                );
            END
            """)
            cursor.execute("""
            IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Proyecto_Bitacora_Proyecto_ID' AND object_id = OBJECT_ID('dbo.Proyecto_Bitacora'))
            BEGIN
                CREATE INDEX IX_Proyecto_Bitacora_Proyecto_ID ON dbo.Proyecto_Bitacora (Proyecto_ID);
            END
            """)
            cursor.execute("""
            IF OBJECT_ID('dbo.Proyecto_Adjuntos', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.Proyecto_Adjuntos (
                    ID INT IDENTITY(1,1) PRIMARY KEY,
                    Bitacora_ID INT NOT NULL,
                    Proyecto_ID NUMERIC(18,0) NOT NULL,
                    Nombre_Original NVARCHAR(255) NOT NULL,
                    Nombre_Almacenado VARCHAR(100) NOT NULL,
                    Content_Type VARCHAR(150) NULL,
                    Tamano_Bytes INT NOT NULL,
                    Autor_Username VARCHAR(100) NULL,
                    Creado DATETIME NOT NULL DEFAULT GETDATE()
                );
            END
            """)
            cursor.execute("""
            IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Proyecto_Adjuntos_Bitacora_ID' AND object_id = OBJECT_ID('dbo.Proyecto_Adjuntos'))
            BEGIN
                CREATE INDEX IX_Proyecto_Adjuntos_Bitacora_ID ON dbo.Proyecto_Adjuntos (Bitacora_ID);
            END
            """)
            _init_asociaciones_table(cursor)
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

# -----------------------------------------------------------------------------
# ASOCIACIÓN DE PROYECTOS POR N° DE PROYECTO (dbo.Proyecto_Asociaciones)
# -----------------------------------------------------------------------------
# Una asociación es una arista entre un proyecto (Proyecto_ID) y un N° de proyecto normalizado
# (sin espacios ni prefijo SGA '000'; puede ser un hijo que no exista en dbo.Proyectos).
# El grupo de un proyecto es la componente conexa de esas aristas (simétrica y transitiva).
# Solo las pestañas Solots/Tickets/RFCs del detalle suman los registros del grupo.
def _init_asociaciones_table(cursor):
    """DDL aditivo e idempotente de dbo.Proyecto_Asociaciones; corre en la transacción de init_bitacora_tables."""
    cursor.execute("""
    IF OBJECT_ID('dbo.Proyecto_Asociaciones', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.Proyecto_Asociaciones (
            ID INT IDENTITY(1,1) PRIMARY KEY,
            Proyecto_ID NUMERIC(18,0) NOT NULL,
            Numero_Asociado VARCHAR(50) NOT NULL,
            Autor_Username VARCHAR(100) NULL,
            Creado DATETIME NOT NULL DEFAULT GETDATE()
        );
    END
    """)
    cursor.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_Proyecto_Asociaciones_Proyecto_Numero' AND object_id = OBJECT_ID('dbo.Proyecto_Asociaciones'))
    BEGIN
        CREATE UNIQUE INDEX UX_Proyecto_Asociaciones_Proyecto_Numero ON dbo.Proyecto_Asociaciones (Proyecto_ID, Numero_Asociado);
    END
    """)

def normalizar_numero_asociado(numero) -> str:
    """N° de proyecto sin espacios y sin el prefijo SGA '000' ('0001609373' -> '1609373')."""
    num = str(numero or "").strip()
    return num[3:] if num.startswith("000") and len(num) > 3 else num

def _cargar_grupo_asociado(cursor, proyecto_id, numero_proyecto) -> dict:
    """
    Grupo asociado de un proyecto: componente conexa de las aristas de dbo.Proyecto_Asociaciones.
    Los nodos son N° de proyecto normalizados (un proyecto sin N° es el nodo '#<ID>').
    """
    propio = normalizar_numero_asociado(numero_proyecto)
    cursor.execute("""
        SELECT a.ID, a.Proyecto_ID, a.Numero_Asociado, a.Autor_Username, a.Creado, p.Numero_Proyecto AS Numero_Origen
        FROM dbo.Proyecto_Asociaciones a
        LEFT JOIN dbo.Proyectos p WITH (NOLOCK) ON p.ID = a.Proyecto_ID
        ORDER BY a.Creado, a.ID
    """)
    aristas = []
    for r in cursor.fetchall() or []:
        pid = int(r["Proyecto_ID"])
        origen = normalizar_numero_asociado(r.get("Numero_Origen")) or f"#{pid}"
        aristas.append((r, pid, origen, normalizar_numero_asociado(r.get("Numero_Asociado"))))

    inicio = propio or f"#{int(proyecto_id)}"
    adyacentes = {}
    for _, _, origen, destino in aristas:
        adyacentes.setdefault(origen, set()).add(destino)
        adyacentes.setdefault(destino, set()).add(origen)
    nodos, pendientes = {inicio}, [inicio]
    while pendientes:
        for vecino in adyacentes.get(pendientes.pop(), ()):
            if vecino not in nodos:
                nodos.add(vecino)
                pendientes.append(vecino)

    numeros = sorted(n for n in nodos if not n.startswith("#") and n != propio)
    proyecto_ids = {int(n[1:]) for n in nodos if n.startswith("#")} - {int(proyecto_id)}
    proyectos = {}
    if numeros:
        marcadores = ", ".join(["%s"] * len(numeros))
        cursor.execute(f"""
            SELECT ID, Numero_Proyecto, Cliente
            FROM dbo.Proyectos WITH (NOLOCK)
            WHERE CASE WHEN LTRIM(RTRIM(Numero_Proyecto)) LIKE '000%' THEN SUBSTRING(LTRIM(RTRIM(Numero_Proyecto)), 4, 50)
                       ELSE LTRIM(RTRIM(Numero_Proyecto)) END IN ({marcadores})
            ORDER BY ID
        """, tuple(numeros))
        for r in cursor.fetchall() or []:
            pid = int(r["ID"])
            if pid == int(proyecto_id):
                continue
            proyecto_ids.add(pid)
            proyectos.setdefault(normalizar_numero_asociado(r.get("Numero_Proyecto")), []).append(
                {"id": pid, "cliente": r.get("Cliente")}
            )

    # Aristas que este proyecto puede quitar: las que parten de él o llegan a su N°
    directas = []
    for r, pid, origen, destino in aristas:
        if pid == int(proyecto_id):
            otro = destino
        elif propio and destino == propio:
            otro = f"ID {origen[1:]}" if origen.startswith("#") else origen
        else:
            continue
        directas.append({
            "id": int(r["ID"]),
            "numero": otro,
            "autor_username": r.get("Autor_Username"),
            "creado": _iso(r.get("Creado")),
        })

    id_numero = {pid: numero for numero, lista in proyectos.items() for pid in (p["id"] for p in lista)}
    id_numero[int(proyecto_id)] = propio
    return {
        "numero_propio": propio,
        "numeros": numeros,
        "proyectos": proyectos,
        "proyecto_ids": sorted(proyecto_ids),
        "id_numero": id_numero,
        "directas": directas,
    }

def _grupo_para_detalle(cursor, proyecto_id, numero_proyecto):
    """Grupo para las pestañas del detalle; None si el proyecto no tiene asociaciones (o la tabla no responde)."""
    try:
        grupo = _cargar_grupo_asociado(cursor, proyecto_id, numero_proyecto)
    except Exception as e:
        logger.error(f"No se pudo calcular el grupo asociado del proyecto {proyecto_id}: {e}")
        return None
    return grupo if (grupo["numeros"] or grupo["proyecto_ids"]) else None

def _sql_columnas_origen(alias, grupo) -> str:
    """Columnas auxiliares para etiquetar Proyecto_Origen (solo cuando hay grupo)."""
    if not grupo:
        return ""
    return f", {alias}.Numero_Proyecto_Limpio AS _Numero_Limpio, {alias}.ID_Proyecto AS _ID_Proyecto"

def _sql_clausulas_grupo(alias, grupo, params) -> str:
    """OR adicionales con los N° y los ID de proyecto del grupo; agrega sus valores a params."""
    sql = ""
    if grupo["proyecto_ids"]:
        sql += f" OR {alias}.ID_Proyecto IN ({', '.join(['%s'] * len(grupo['proyecto_ids']))})"
        params.extend(grupo["proyecto_ids"])
    if grupo["numeros"]:
        sql += f" OR {alias}.Numero_Proyecto_Limpio IN ({', '.join(['%s'] * len(grupo['numeros']))})"
        params.extend(grupo["numeros"])
    return sql

def _etiquetar_origen(rows, grupo):
    """Agrega Proyecto_Origen (N° del proyecto del grupo al que pertenece cada registro) y retira las columnas auxiliares."""
    numeros = set(grupo["numeros"]) | {grupo["numero_propio"]}
    for row in rows:
        limpio = str(row.pop("_Numero_Limpio", None) or "").strip()
        id_proyecto = row.pop("_ID_Proyecto", None)
        if limpio and limpio in numeros:
            origen = limpio
        else:
            origen = grupo["id_numero"].get(int(id_proyecto)) if id_proyecto is not None else None
        row["Proyecto_Origen"] = origen or grupo["numero_propio"] or None

def get_asociaciones_proyecto(proyecto_id, numero_proyecto) -> dict:
    """Grupo del proyecto (otros N° con su proyecto, si existe en dbo.Proyectos) y las asociaciones directas removibles."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            grupo = _cargar_grupo_asociado(cursor, proyecto_id, numero_proyecto)
        return {
            "numero_propio": grupo["numero_propio"],
            "grupo": [
                {
                    "numero": numero,
                    "proyecto_id": (grupo["proyectos"].get(numero) or [{}])[0].get("id"),
                    "cliente": (grupo["proyectos"].get(numero) or [{}])[0].get("cliente"),
                }
                for numero in grupo["numeros"]
            ],
            "asociaciones": grupo["directas"],
        }
    finally:
        conn.close()

def create_asociacion(proyecto_id, numero_proyecto, numero_asociado, autor_username) -> dict:
    """
    Asocia un N° de proyecto ya normalizado. Retorna {"status": "duplicate"} (sin escribir) si ya está en el grupo,
    o {"status": "created", "data": {...}}.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            grupo = _cargar_grupo_asociado(cursor, proyecto_id, numero_proyecto)
            if numero_asociado == grupo["numero_propio"] or numero_asociado in grupo["numeros"]:
                return {"status": "duplicate"}
            cursor.execute("""
                INSERT INTO dbo.Proyecto_Asociaciones (Proyecto_ID, Numero_Asociado, Autor_Username)
                OUTPUT INSERTED.ID, INSERTED.Creado
                VALUES (%s, %s, %s)
            """, (proyecto_id, numero_asociado, autor_username))
            row = cursor.fetchone()
        conn.commit()
        return {
            "status": "created",
            "data": {
                "id": int(row["ID"]),
                "numero": numero_asociado,
                "autor_username": autor_username,
                "creado": _iso(row["Creado"]),
            },
        }
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def delete_asociacion(proyecto_id, numero_proyecto, asociacion_id) -> bool:
    """Borra una arista que involucra al proyecto (su Proyecto_ID o su N°); False si no existe o no lo involucra."""
    propio = normalizar_numero_asociado(numero_proyecto)
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT ID, Proyecto_ID, Numero_Asociado FROM dbo.Proyecto_Asociaciones WHERE ID = %s",
                (asociacion_id,)
            )
            row = cursor.fetchone()
            involucra = bool(row) and (
                int(row["Proyecto_ID"]) == int(proyecto_id)
                or (bool(propio) and normalizar_numero_asociado(row.get("Numero_Asociado")) == propio)
            )
            if not involucra:
                return False
            cursor.execute("DELETE FROM dbo.Proyecto_Asociaciones WHERE ID = %s", (asociacion_id,))
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def _iso(value):
    return value.isoformat() if isinstance(value, (datetime.datetime, datetime.date)) else value

def _insert_bitacora_row(cursor, proyecto_id, tipo, texto, estado_anterior, estado_nuevo, autor_username, autor_nombre):
    """INSERT único de una entrada de bitácora; retorna (id, creado). No hace commit: lo decide el llamador."""
    cursor.execute("""
        INSERT INTO dbo.Proyecto_Bitacora (Proyecto_ID, Tipo, Texto, Estado_Anterior, Estado_Nuevo, Autor_Username, Autor_Nombre)
        OUTPUT INSERTED.ID, INSERTED.Creado
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (proyecto_id, tipo, texto, estado_anterior, estado_nuevo, autor_username, autor_nombre))
    row = cursor.fetchone()
    return int(row["ID"]), row["Creado"]

def _serialize_adjunto(row) -> dict:
    return {
        "id": int(row["ID"]),
        "nombre": row["Nombre_Original"],
        "content_type": row.get("Content_Type"),
        "tamano_bytes": row["Tamano_Bytes"],
        "creado": _iso(row["Creado"]),
    }

def create_bitacora_entry(proyecto_id: int, texto: str, autor_username: Optional[str], autor_nombre: Optional[str]) -> dict:
    """Agrega una entrada libre (Tipo BITACORA) a la bitácora del proyecto y la retorna serializada."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            entry_id, creado = _insert_bitacora_row(
                cursor, proyecto_id, "BITACORA", texto, None, None, autor_username, autor_nombre
            )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
    return {
        "id": entry_id, "tipo": "BITACORA", "texto": texto,
        "estado_anterior": None, "estado_nuevo": None,
        "autor_username": autor_username, "autor_nombre": autor_nombre,
        "creado": _iso(creado), "adjuntos": [],
    }

def get_bitacora_by_proyecto(proyecto_id: int) -> list:
    """Entradas de la bitácora del proyecto, las más recientes primero, con sus adjuntos."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT ID, Tipo, Texto, Estado_Anterior, Estado_Nuevo, Autor_Username, Autor_Nombre, Creado
                FROM dbo.Proyecto_Bitacora WITH (NOLOCK)
                WHERE Proyecto_ID = %s
                ORDER BY Creado DESC, ID DESC
            """, (proyecto_id,))
            entradas = cursor.fetchall()
            cursor.execute("""
                SELECT ID, Bitacora_ID, Nombre_Original, Content_Type, Tamano_Bytes, Creado
                FROM dbo.Proyecto_Adjuntos WITH (NOLOCK)
                WHERE Proyecto_ID = %s
                ORDER BY ID ASC
            """, (proyecto_id,))
            adjuntos = cursor.fetchall()
    finally:
        conn.close()

    por_entrada = {}
    for adj in adjuntos:
        por_entrada.setdefault(int(adj["Bitacora_ID"]), []).append(_serialize_adjunto(adj))
    return [
        {
            "id": int(e["ID"]),
            "tipo": e["Tipo"],
            "texto": e["Texto"],
            "estado_anterior": e.get("Estado_Anterior"),
            "estado_nuevo": e.get("Estado_Nuevo"),
            "autor_username": e.get("Autor_Username"),
            "autor_nombre": e.get("Autor_Nombre"),
            "creado": _iso(e["Creado"]),
            "adjuntos": por_entrada.get(int(e["ID"]), []),
        }
        for e in entradas
    ]

def get_bitacora_entry(proyecto_id: int, entry_id: int) -> Optional[dict]:
    """Entrada de bitácora solo si pertenece al proyecto indicado; None en caso contrario."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT ID, Proyecto_ID, Tipo FROM dbo.Proyecto_Bitacora WITH (NOLOCK) WHERE ID = %s AND Proyecto_ID = %s",
                (entry_id, proyecto_id)
            )
            return cursor.fetchone()
    finally:
        conn.close()

def create_adjunto(
    bitacora_id: int,
    proyecto_id: int,
    nombre_original: str,
    nombre_almacenado: str,
    content_type: Optional[str],
    tamano_bytes: int,
    autor_username: Optional[str]
) -> dict:
    """Registra los metadatos de un adjunto ya guardado en disco y los retorna serializados."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO dbo.Proyecto_Adjuntos (Bitacora_ID, Proyecto_ID, Nombre_Original, Nombre_Almacenado, Content_Type, Tamano_Bytes, Autor_Username)
                OUTPUT INSERTED.ID, INSERTED.Creado
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (bitacora_id, proyecto_id, nombre_original, nombre_almacenado, content_type, tamano_bytes, autor_username))
            row = cursor.fetchone()
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
    return {
        "id": int(row["ID"]), "nombre": nombre_original, "content_type": content_type,
        "tamano_bytes": tamano_bytes, "creado": _iso(row["Creado"]),
    }

def get_adjunto(proyecto_id: int, adjunto_id: int) -> Optional[dict]:
    """Adjunto solo si pertenece al proyecto indicado; None en caso contrario."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT ID, Proyecto_ID, Nombre_Original, Nombre_Almacenado, Content_Type, Tamano_Bytes
                FROM dbo.Proyecto_Adjuntos WITH (NOLOCK)
                WHERE ID = %s AND Proyecto_ID = %s
            """, (adjunto_id, proyecto_id))
            return cursor.fetchone()
    finally:
        conn.close()

def get_adjuntos_dir() -> Path:
    """Directorio de adjuntos configurado (se lee en cada llamada para respetar ADJUNTOS_DIR)."""
    return Path(app_config.ADJUNTOS_DIR)

def adjunto_path(nombre_almacenado) -> Optional[Path]:
    """Ruta resuelta del archivo almacenado, o None si queda fuera del directorio de adjuntos."""
    nombre = str(nombre_almacenado or "")
    if not nombre:
        return None
    base = get_adjuntos_dir().resolve()
    path = (base / nombre).resolve()
    return path if base in path.parents else None

def remove_adjunto_files(nombres_almacenados) -> None:
    """Borra archivos de adjuntos de forma best-effort: registra los errores y nunca los propaga."""
    for nombre in nombres_almacenados:
        try:
            path = adjunto_path(nombre)
            if path is None:
                logger.warning(f"Adjunto fuera del directorio permitido, no se borra: {nombre!r}")
            elif path.exists():
                os.remove(path)
        except Exception as e:
            logger.warning(f"No se pudo borrar el adjunto {nombre!r}: {e}")

# -----------------------------------------------------------------------------
# EDICIÓN Y ELIMINACIÓN DE PROYECTOS (dbo.Proyectos)
# -----------------------------------------------------------------------------
def update_proyecto(
    proyecto_id: int,
    cliente: str,
    lt_asignado: Optional[str] = None,
    estado: str = "Generado",
    detalle: str = "",
    tipo_servicio: Optional[str] = "Otros",
    comentario: Optional[str] = None,
    bitacora: Optional[dict] = None
) -> dict:
    """
    Actualiza los campos operativos y estado de un proyecto en dbo.Proyectos detectando asignaciones.

    Si se entrega `bitacora` (tipo, texto, estado_anterior, estado_nuevo, autor_username, autor_nombre), la entrada
    se inserta en la MISMA transacción que el UPDATE: o se guardan ambos o ninguno.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Verificar existencia del proyecto y capturar estado previo
            cursor.execute("""
                SELECT ID, Cliente, Numero_Proyecto, LT_Asignado, Estado, Detalle, Tipo_Servicio, Solicitante
                FROM dbo.Proyectos WHERE ID = %s
            """, (proyecto_id,))
            prev_row = cursor.fetchone()
            if not prev_row:
                return {"success": False, "error": "not_found", "message": f"Proyecto ID {proyecto_id} no encontrado"}

            prev_lt = prev_row.get("LT_Asignado")
            prev_lt_str = str(prev_lt).strip() if prev_lt and str(prev_lt).strip() else None
            new_lt_str = str(lt_asignado).strip() if lt_asignado and str(lt_asignado).strip() else None

            is_prev_unassigned = not prev_lt_str or prev_lt_str.lower() in ('sin asignar', 'none', 'null')
            is_new_assigned = bool(new_lt_str and new_lt_str.lower() not in ('sin asignar', 'none', 'null'))
            was_assigned = is_prev_unassigned and is_new_assigned
            solicitante_val = prev_row.get("Solicitante")

            # 2. Ejecutar UPDATE parametrizado
            sql_update = """
                UPDATE dbo.Proyectos
                SET 
                    Cliente = %s,
                    LT_Asignado = %s,
                    Estado = %s,
                    Detalle = %s,
                    Tipo_Servicio = %s,
                    Comentario = %s
                WHERE ID = %s
            """
            cursor.execute(sql_update, (
                cliente.strip()[:100],
                new_lt_str[:50] if new_lt_str else None,
                estado.strip(),
                detalle.strip(),
                (tipo_servicio.strip()[:30] if tipo_servicio and str(tipo_servicio).strip() else "Otros"),
                (comentario.strip() if comentario and str(comentario).strip() else None),
                proyecto_id
            ))

            bitacora_entry_id = None
            if bitacora:
                bitacora_entry_id, _ = _insert_bitacora_row(
                    cursor, proyecto_id, bitacora["tipo"], bitacora["texto"],
                    bitacora.get("estado_anterior"), bitacora.get("estado_nuevo"),
                    bitacora.get("autor_username"), bitacora.get("autor_nombre")
                )
            conn.commit()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "error": "db_error", "message": str(e)}
    finally:
        conn.close()

    # 3. Retornar el registro actualizado enriquecido tras liberar la transacción
    updated_data = get_proyecto_by_id(proyecto_id)
    return {
        "success": True,
        "data": updated_data,
        "was_assigned": was_assigned,
        "prev_lt": prev_lt_str,
        "new_lt": new_lt_str,
        "solicitante": solicitante_val,
        "bitacora_entry_id": bitacora_entry_id
    }

# -----------------------------------------------------------------------------
# ASIGNACIÓN DIRECTA DE LTI DESDE EL BACKLOG DE OPERACIONES (CT_BACKLOG_OPERACIONES2)
# -----------------------------------------------------------------------------
BACKLOG_ASSIGNMENT_DETALLE = "Asignado directamente desde el backlog de operaciones SGA."

def _numero_proyecto_variants(numero_proyecto: str) -> tuple:
    """N° de proyecto tal cual, sin ceros iniciales y con prefijo '000'."""
    num_clean = str(numero_proyecto).strip()
    num_without_zeros = num_clean.lstrip('0')
    num_with_zeros = f"000{num_without_zeros}" if num_without_zeros else num_clean
    return (num_clean, num_without_zeros, num_with_zeros)

def get_backlog_proyecto(numero_proyecto: str) -> Optional[dict]:
    """Primer registro de CT_BACKLOG_OPERACIONES2 del proyecto (solo lectura), o None."""
    if not numero_proyecto or not str(numero_proyecto).strip():
        return None
    variants = _numero_proyecto_variants(numero_proyecto)
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT TOP 1 NRO_PROYECTO, Numero_Proyecto_Limpio, CLI_CLIENTE, PRO_ING_PROYECTO
                FROM dbo.CT_BACKLOG_OPERACIONES2 WITH (NOLOCK)
                WHERE LTRIM(RTRIM(NRO_PROYECTO)) IN (%s, %s, %s)
                   OR LTRIM(RTRIM(Numero_Proyecto_Limpio)) IN (%s, %s, %s)
                ORDER BY FECHA_INSERT DESC
            """, variants + variants)
            row = cursor.fetchone()
            return serialize_row(row) if row else None
    finally:
        conn.close()

def update_proyecto_lt(proyecto_id: int, lt_asignado: str) -> Optional[dict]:
    """
    Actualiza LT_Asignado de un proyecto en dbo.Proyectos y retorna el registro.
    Un proyecto 'Generado' pasa a 'En ejecucion'; En revision / Cerrado no se degradan.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE dbo.Proyectos SET LT_Asignado = %s, "
                "Estado = CASE WHEN Estado = 'Generado' THEN 'En ejecucion' ELSE Estado END "
                "WHERE ID = %s",
                (str(lt_asignado).strip()[:50], proyecto_id)
            )
            conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
    return get_proyecto_by_id(proyecto_id)

def _is_unassigned_lt(lt_value) -> bool:
    lt_str = str(lt_value).strip() if lt_value is not None else ""
    return not lt_str or lt_str.lower() in ('sin asignar', 'none', 'null')

def assign_lti_from_backlog(numero_proyecto: str, lt_asignado: str, actor_nombre: Optional[str] = None) -> dict:
    """
    Asigna un LTI a un proyecto del backlog de operaciones.

    - Si el proyecto ya existe en dbo.Proyectos, cambia LT_Asignado y, si estaba 'Generado', lo pasa a
      'En ejecucion' (action='updated').
    - Si no existe, lo crea con los datos del backlog, Estado 'En ejecucion' (action='created').
    Nunca escribe en dbo.CT_BACKLOG_OPERACIONES2.
    """
    lt_val = str(lt_asignado).strip()
    try:
        backlog_row = get_backlog_proyecto(numero_proyecto)
        if not backlog_row:
            return {"success": False, "error": "not_found_backlog"}

        existing = check_proyecto_exists(numero_proyecto)
        action = "updated"
        if not existing:
            solicitante = clean_solicitante(backlog_row.get("PRO_ING_PROYECTO"))
            if solicitante == UNMATCHED_SOLICITANTE:
                solicitante = actor_nombre
            created = create_solicitud_lti(
                cliente=str(backlog_row.get("CLI_CLIENTE") or "").strip(),
                numero_proyecto=str(numero_proyecto).strip(),
                lt_asignado=lt_val,
                estado="En ejecucion",
                fecha_solicitud=datetime.date.today().isoformat(),
                detalle=BACKLOG_ASSIGNMENT_DETALLE,
                solicitante=solicitante,
                tipo_servicio="Otros"
            )
            if created.get("success"):
                return {
                    "success": True,
                    "action": "created",
                    "data": created.get("data"),
                    "was_assigned": True,
                    "prev_lt": None,
                    "new_lt": lt_val
                }
            if created.get("error") != "duplicate":
                return {"success": False, "error": "db_error", "message": created.get("error")}
            # Otro usuario lo creó entre la verificación y la inserción: se actualiza
            existing = created.get("existing")

        prev_lt = existing.get("LT_Asignado")
        updated = update_proyecto_lt(existing["ID"], lt_val)
        return {
            "success": True,
            "action": action,
            "data": updated,
            "was_assigned": _is_unassigned_lt(prev_lt),
            "prev_lt": None if _is_unassigned_lt(prev_lt) else str(prev_lt).strip(),
            "new_lt": lt_val
        }
    except Exception as e:
        return {"success": False, "error": "db_error", "message": str(e)}

# -----------------------------------------------------------------------------
# HELPERS DE CORREO Y RECORDATORIOS (MÓDULO SOLICITUD LTI)
# -----------------------------------------------------------------------------
CANONICAL_EMAIL_MAP = {
    "alejandro aguilar": "alejandro.aguilarm@clarovtr.cl",
    "alejandro.aguilar": "alejandro.aguilarm@clarovtr.cl",
    "aaguilar": "alejandro.aguilarm@clarovtr.cl",
    "pablo castillo": "pablo.castillo@clarovtr.cl",
    "pablo.castillo": "pablo.castillo@clarovtr.cl",
    "pcastillo": "pablo.castillo@clarovtr.cl",
    "erwin sandoval": "erwin.sandoval@clarovtr.cl",
    "erwin.sandoval": "erwin.sandoval@clarovtr.cl",
    "esandoval": "erwin.sandoval@clarovtr.cl",
    "juan barrera": "juan.barrera@clarovtr.cl",
    "juan.barrera": "juan.barrera@clarovtr.cl",
    "jbarrera": "juan.barrera@clarovtr.cl",
    "samuel paredes": "samuel.paredes@clarovtr.cl",
    "samuel.paredes": "samuel.paredes@clarovtr.cl",
    "sparedes": "samuel.paredes@clarovtr.cl",
    "solange ortiz": "solange.ortiz@clarovtr.cl",
    "solange.ortiz": "solange.ortiz@clarovtr.cl",
    "sortiz": "solange.ortiz@clarovtr.cl",
}

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$")

def normalize_text_for_username(text: str) -> str:
    """Normaliza un texto quitando tildes y caracteres especiales, separando palabras con punto."""
    if not text:
        return ""
    import unicodedata
    nfkd = unicodedata.normalize('NFKD', str(text))
    ascii_text = ''.join([c for c in nfkd if not unicodedata.combining(c)])
    clean = re.sub(r"[^a-zA-Z0-9.\s_-]", "", ascii_text).strip().lower()
    return re.sub(r"\s+", ".", clean)

def resolve_user_email(user_identifier: Optional[str], conn=None) -> Optional[str]:
    """
    Resuelve el correo institucional corporativo de un usuario (PM o LTI):
    1. Si ya tiene formato sintáctico de email -> sanitiza y retorna en minúsculas.
    2. Consulta en catálogo canónico de coordinadores y líderes TI.
    3. Consulta en dbo.App_Usuarios (por username, nombre_completo o lt_asignado).
    4. Heurística empresarial normalizada (nombre.apellido@clarovtr.cl).
    """
    if not user_identifier:
        return None

    raw_ident = str(user_identifier).strip()
    if not raw_ident or raw_ident.upper() in ('N/A', 'NONE', 'NULL', '-'):
        return None

    # 1. Si ya tiene formato de correo válido
    if EMAIL_REGEX.match(raw_ident):
        return raw_ident.lower()

    # Normalizar identificador
    ident_clean = raw_ident.lower()
    ident_normalized = normalize_text_for_username(raw_ident)

    # 2. Catálogo canónico estático
    if ident_clean in CANONICAL_EMAIL_MAP:
        return CANONICAL_EMAIL_MAP[ident_clean]
    if ident_normalized in CANONICAL_EMAIL_MAP:
        return CANONICAL_EMAIL_MAP[ident_normalized]

    # Quitar posibles prefijos de PM como "Corp1 - ", etc.
    cleaned_ident = clean_solicitante(raw_ident)
    if cleaned_ident and cleaned_ident != UNMATCHED_SOLICITANTE:
        cleaned_norm = normalize_text_for_username(cleaned_ident)
        if cleaned_norm in CANONICAL_EMAIL_MAP:
            return CANONICAL_EMAIL_MAP[cleaned_norm]

    # 3. Consulta a dbo.App_Usuarios
    should_close = False
    active_conn = conn
    if active_conn is None:
        try:
            active_conn = get_db_connection()
            should_close = True
        except Exception as conn_err:
            logger.warning(f"No se pudo conectar a BD para resolver email de '{raw_ident}': {conn_err}")
            active_conn = None

    if active_conn is not None:
        try:
            with active_conn.cursor() as cursor:
                cursor.execute("""
                    SELECT TOP 1 email, username, nombre_completo 
                    FROM dbo.App_Usuarios 
                    WHERE (LOWER(username) = %s OR LOWER(nombre_completo) = %s OR LOWER(lt_asignado) = %s)
                      AND email IS NOT NULL AND LTRIM(RTRIM(email)) <> ''
                """, (ident_clean, ident_clean, ident_clean))
                row = cursor.fetchone()
                if row and row.get('email'):
                    found_email = str(row['email']).strip().lower()
                    if EMAIL_REGEX.match(found_email):
                        return found_email
        except Exception as e:
            logger.warning(f"Error consultando dbo.App_Usuarios para resolver email de '{raw_ident}': {e}")
        finally:
            if should_close:
                try:
                    active_conn.close()
                except Exception:
                    pass

    # 4. Heurística Corporativa Fallback (@clarovtr.cl)
    parts = [p for p in ident_normalized.split('.') if p]
    if len(parts) >= 2:
        candidate_email = f"{parts[0]}.{parts[1]}@clarovtr.cl"
        if EMAIL_REGEX.match(candidate_email):
            return candidate_email
    elif len(parts) == 1 and len(parts[0]) > 2:
        candidate_email = f"{parts[0]}@clarovtr.cl"
        if EMAIL_REGEX.match(candidate_email):
            return candidate_email

    return None

def is_valid_project_number(
    numero_proyecto: Optional[Union[str, int]], 
    cliente: Optional[str] = None, 
    tipo_servicio: Optional[str] = None,
    solicitante: Optional[str] = None
) -> bool:
    """
    Valida si un proyecto es legítimo para asignación técnica de LTI y notificaciones/recordatorios.
    Descarta:
    - Proyectos con Tipo_Servicio = 'Reunión' o 'reunion' (reuniones históricas de SharePoint, no proyectos técnicos).
    - Números de proyecto nulos, vacíos o con longitud significativa inválida.
    - Números de prueba o dummy repetidos (ej: '0001111111', '1111111', '111111', '999999', '000000').
    - Registros donde Cliente o Solicitante contenga 'PROYECTO DEMO' o 'NO IDENTIFICADO'.
    - Proyectos de prueba automatizada (N° con 'QA' o 'TEST').
    """
    from .email_service import is_test_project_number
    if is_test_project_number(numero_proyecto):
        return False

    if tipo_servicio and str(tipo_servicio).strip().lower() in ('reunión', 'reunion'):
        return False

    if cliente:
        cli_upper = str(cliente).strip().upper()
        if 'PROYECTO DEMO' in cli_upper or 'NO IDENTIFICADO' in cli_upper:
            return False

    if solicitante:
        sol_upper = str(solicitante).strip().upper()
        if 'PROYECTO DEMO' in sol_upper or 'NO IDENTIFICADO' in sol_upper:
            return False

    if not numero_proyecto:
        return False

    raw = str(numero_proyecto).strip()
    clean = raw.lstrip('0')
    if not clean or len(clean) < 3:
        return False

    # Descartar si todos los dígitos son idénticos (ej: 111111, 1111111, 999999, 222222)
    if len(set(clean)) == 1:
        return False

    # Descartar secuencias dummy repetidas evidentes
    if '11111' in clean or '99999' in clean or '00000' in clean:
        return False

    return True

def get_proyectos_pendientes_recordatorio(intervalo_minutos: int = 360, conn=None) -> List[dict]:
    """
    Obtiene los proyectos válidos sin Líder Técnico asignado que requieren recordatorio:
    - Estado no cerrado (<> 'Cerrado' y <> 'Atendido', el estado legado)
    - Tipo_Servicio <> 'Reunión'
    - LT_Asignado IS NULL o vacío o 'sin asignar'
    - Proyecto válido (no dummy tipo 0001111111 ni demo)
    - Creado >= intervalo_minutos (si Ultimo_Recordatorio es NULL)
      O Ultimo_Recordatorio >= intervalo_minutos
    """
    should_close = False
    active_conn = conn
    if active_conn is None:
        active_conn = get_db_connection()
        should_close = True

    try:
        with active_conn.cursor() as cursor:
            sql = """
                SELECT 
                    p.ID,
                    p.Cliente,
                    p.Numero_Proyecto,
                    p.LT_Asignado,
                    p.Estado,
                    p.Detalle,
                    p.Tipo_Servicio,
                    p.Creado,
                    p.Solicitante,
                    p.Ultimo_Recordatorio,
                    ISNULL(p.Contador_Recordatorios, 0) AS Contador_Recordatorios,
                    DATEDIFF(MINUTE, p.Creado, GETDATE()) AS Minutos_Desde_Creacion,
                    CASE 
                        WHEN p.Ultimo_Recordatorio IS NULL THEN DATEDIFF(MINUTE, p.Creado, GETDATE())
                        ELSE DATEDIFF(MINUTE, p.Ultimo_Recordatorio, GETDATE())
                    END AS Minutos_Desde_Ultimo_Hito
                FROM dbo.Proyectos p WITH (NOLOCK)
                WHERE (p.LT_Asignado IS NULL OR LTRIM(RTRIM(p.LT_Asignado)) = '' OR LOWER(LTRIM(RTRIM(p.LT_Asignado))) = 'sin asignar')
                  AND ISNULL(p.Estado, '') NOT IN ('Cerrado', 'Atendido')
                  AND (p.Tipo_Servicio IS NULL OR LOWER(LTRIM(RTRIM(p.Tipo_Servicio))) NOT IN ('reunión', 'reunion'))
                  AND p.Numero_Proyecto NOT LIKE '%111111%'
                  AND p.Numero_Proyecto NOT LIKE '%999999%'
                  AND p.Numero_Proyecto NOT LIKE '%000000%'
                  AND ISNULL(p.Cliente, '') NOT LIKE '%NO IDENTIFICADO%'
                  AND ISNULL(p.Cliente, '') NOT LIKE '%PROYECTO DEMO%'
                  AND ISNULL(p.Solicitante, '') NOT LIKE '%NO IDENTIFICADO%'
                  AND ISNULL(p.Solicitante, '') NOT LIKE '%PROYECTO DEMO%'
                  AND (
                      (p.Ultimo_Recordatorio IS NULL AND DATEDIFF(MINUTE, p.Creado, GETDATE()) >= %s)
                      OR
                      (p.Ultimo_Recordatorio IS NOT NULL AND DATEDIFF(MINUTE, p.Ultimo_Recordatorio, GETDATE()) >= %s)
                  )
                ORDER BY p.Creado ASC;
            """
            cursor.execute(sql, (intervalo_minutos, intervalo_minutos))
            rows = cursor.fetchall()
            valid_rows = [
                r for r in rows 
                if is_valid_project_number(
                    r.get('Numero_Proyecto'), 
                    r.get('Cliente'), 
                    r.get('Tipo_Servicio'),
                    r.get('Solicitante')
                )
            ]
            return serialize_rows(valid_rows)
    finally:
        if should_close:
            active_conn.close()

# Alias de compatibilidad
get_unassigned_solicitudes_pending_reminder = get_proyectos_pendientes_recordatorio

def registrar_recordatorio_enviado(proyecto_id: int, conn=None) -> bool:
    """Actualiza Ultimo_Recordatorio a GETDATE() e incrementa Contador_Recordatorios para un proyecto."""
    should_close = False
    active_conn = conn
    if active_conn is None:
        active_conn = get_db_connection()
        should_close = True

    try:
        with active_conn.cursor() as cursor:
            cursor.execute("""
                UPDATE dbo.Proyectos
                SET Ultimo_Recordatorio = GETDATE(),
                    Contador_Recordatorios = ISNULL(Contador_Recordatorios, 0) + 1
                WHERE ID = %s
            """, (proyecto_id,))
            active_conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error registrando recordatorio enviado para proyecto ID {proyecto_id}: {e}")
        try:
            active_conn.rollback()
        except Exception:
            pass
        return False
    finally:
        if should_close:
            active_conn.close()

def mark_solicitudes_reminder_sent(project_ids: Union[int, List[int]], conn=None) -> bool:
    """Actualiza Ultimo_Recordatorio y Contador_Recordatorios para uno o varios proyectos."""
    if isinstance(project_ids, int):
        return registrar_recordatorio_enviado(project_ids, conn=conn)

    if not project_ids:
        return True

    clean_ids = [int(p) for p in project_ids if p is not None]
    if not clean_ids:
        return True

    should_close = False
    active_conn = conn
    if active_conn is None:
        active_conn = get_db_connection()
        should_close = True

    try:
        with active_conn.cursor() as cursor:
            placeholders = ", ".join(["%s"] * len(clean_ids))
            cursor.execute(f"""
                UPDATE dbo.Proyectos
                SET Ultimo_Recordatorio = GETDATE(),
                    Contador_Recordatorios = ISNULL(Contador_Recordatorios, 0) + 1
                WHERE ID IN ({placeholders})
            """, tuple(clean_ids))
            active_conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error actualizando recordatorios para proyectos {clean_ids}: {e}")
        try:
            active_conn.rollback()
        except Exception:
            pass
        return False
    finally:
        if should_close:
            active_conn.close()

def delete_proyecto(proyecto_id: int) -> dict:
    """
    Elimina físicamente un proyecto de dbo.Proyectos junto con su bitácora, adjuntos y asociaciones (misma transacción).
    Los archivos de los adjuntos se borran después del commit, best-effort.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Verificar existencia y capturar datos antes de borrar
            cursor.execute("SELECT ID, Numero_Proyecto, Cliente FROM dbo.Proyectos WHERE ID = %s", (proyecto_id,))
            existing = cursor.fetchone()
            if not existing:
                return {"success": False, "error": "not_found", "message": f"Proyecto ID {proyecto_id} no encontrado"}

            # 2. Ejecutar DELETE en cascada: adjuntos, bitácora y proyecto en una sola transacción
            cursor.execute("SELECT Nombre_Almacenado FROM dbo.Proyecto_Adjuntos WHERE Proyecto_ID = %s", (proyecto_id,))
            archivos = [r["Nombre_Almacenado"] for r in cursor.fetchall()]
            cursor.execute("DELETE FROM dbo.Proyecto_Adjuntos WHERE Proyecto_ID = %s", (proyecto_id,))
            cursor.execute("DELETE FROM dbo.Proyecto_Bitacora WHERE Proyecto_ID = %s", (proyecto_id,))
            cursor.execute("DELETE FROM dbo.Proyecto_Asociaciones WHERE Proyecto_ID = %s", (proyecto_id,))
            cursor.execute("DELETE FROM dbo.Proyectos WHERE ID = %s", (proyecto_id,))
            deleted_count = cursor.rowcount
            conn.commit()

            remove_adjunto_files(archivos)

            return {
                "success": True,
                "id": proyecto_id,
                "numero_proyecto": existing.get("Numero_Proyecto"),
                "cliente": existing.get("Cliente"),
                "deleted_count": deleted_count
            }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "error": "db_error", "message": str(e)}
    finally:
        conn.close()

# -----------------------------------------------------------------------------
# MOTOR DE DIAGNÓSTICO EJECUTIVO EN 1 CLIC (SPECS-LTI-MOD-012)
# -----------------------------------------------------------------------------
def compilar_minuta_texto_plano(
    proyecto: dict,
    salud: dict,
    antiguedad_dias: int,
    porcentaje_avance: float,
    solots_ejecutadas: int,
    total_solots: int,
    cuellos_de_botella: list,
    recomendaciones: list
) -> str:
    num_proy = proyecto.get("Numero_Proyecto") or "S/N"
    cliente = proyecto.get("Cliente") or "Sin Cliente"
    lt_asignado = proyecto.get("LT_Asignado") or "No asignado"
    solicitante = proyecto.get("Solicitante") or "No especificado"
    estado_sp = proyecto.get("Estado") or "Generado"
    salud_label = salud.get("label", "Sin Datos") if salud else "Sin Datos"
    salud_color = (salud.get("color") or "").lower() if salud else "gray"
    icono = "🔴" if salud_color == "red" else ("🟡" if salud_color == "yellow" else ("🟢" if salud_color == "green" else "⚪"))
    motivos_str = f" ({', '.join(salud.get('motivos', []))})" if salud and salud.get("motivos") else ""

    lines = [
        "=" * 60,
        "⚡ DIAGNÓSTICO EJECUTIVO HALO — APP LÍDERES TI",
        "=" * 60,
        f"PROYECTO: {num_proy}",
        f"CLIENTE: {cliente}",
        f"LÍDER TI: {lt_asignado}",
        f"SOLICITANTE: {solicitante}",
        f"ESTADO SHAREPOINT: {estado_sp}",
        f"SALUD OPERACIONAL: {icono} {salud_label}{motivos_str}",
        f"ANTIGÜEDAD: {antiguedad_dias} días",
        f"AVANCE SOLOTS: {porcentaje_avance}% ({solots_ejecutadas}/{total_solots} ejecutadas)",
        "",
        "-" * 60,
        "🚨 CUELLOS DE BOTELLA OPERATIVOS",
        "-" * 60,
    ]

    if cuellos_de_botella:
        for idx, cb in enumerate(cuellos_de_botella, 1):
            lines.append(f"{idx}. [{cb['severidad']}] {cb['identificador']}: {cb['descripcion']} Área: {cb['responsable_area']}.")
    else:
        lines.append("No se detectaron cuellos de botella ni bloqueos operacionales en este proyecto.")

    lines.extend([
        "",
        "-" * 60,
        "🎯 ACCIONES RECOMENDADAS DE ESCALAMIENTO",
        "-" * 60,
    ])

    if recomendaciones:
        for idx, rec in enumerate(recomendaciones, 1):
            lines.append(f"{idx}. [{rec['prioridad']}] {rec['accion']} (Destinatario: {rec['destinatario_escalamiento']} | Canal: {rec['canal_sugerido']})")
    else:
        lines.append("Sin recomendaciones adicionales de escalamiento.")

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.extend([
        "",
        f"Generado el: {now_str} | HALO App Líderes TI",
        "=" * 60
    ])

    return "\n".join(lines)


def compilar_minuta_markdown(
    proyecto: dict,
    salud: dict,
    antiguedad_dias: int,
    porcentaje_avance: float,
    solots_ejecutadas: int,
    total_solots: int,
    cuellos_de_botella: list,
    recomendaciones: list
) -> str:
    num_proy = proyecto.get("Numero_Proyecto") or "S/N"
    cliente = proyecto.get("Cliente") or "Sin Cliente"
    lt_asignado = proyecto.get("LT_Asignado") or "No asignado"
    solicitante = proyecto.get("Solicitante") or "No especificado"
    estado_sp = proyecto.get("Estado") or "Generado"
    salud_label = salud.get("label", "Sin Datos") if salud else "Sin Datos"
    salud_color = (salud.get("color") or "").lower() if salud else "gray"
    icono = "🔴" if salud_color == "red" else ("🟡" if salud_color == "yellow" else ("🟢" if salud_color == "green" else "⚪"))
    motivos_str = f" *({', '.join(salud.get('motivos', []))})*" if salud and salud.get("motivos") else ""

    md = [
        "### ⚡ DIAGNÓSTICO EJECUTIVO — HALO Líderes TI",
        "",
        f"- **Proyecto:** `{num_proy}`",
        f"- **Cliente:** **{cliente}**",
        f"- **Líder TI:** {lt_asignado}",
        f"- **Solicitante:** {solicitante}",
        f"- **Estado SharePoint:** `{estado_sp}`",
        f"- **Salud Operacional:** {icono} **{salud_label}**{motivos_str}",
        f"- **Antigüedad:** {antiguedad_dias} días",
        f"- **Avance Solots SGA:** **{porcentaje_avance}%** ({solots_ejecutadas} de {total_solots} ejecutadas)",
        "",
        "---",
        "",
        f"#### 🚨 Cuellos de Botella Detectados ({len(cuellos_de_botella)})",
        ""
    ]

    if cuellos_de_botella:
        for idx, cb in enumerate(cuellos_de_botella, 1):
            md.append(f"{idx}. **[{cb['severidad']}] `{cb['identificador']}`** — {cb['descripcion']} *(Área: {cb['responsable_area']})*")
    else:
        md.append("✅ *No se detectaron cuellos de botella ni bloqueos operacionales en este proyecto.*")

    md.extend([
        "",
        "---",
        "",
        f"#### 🎯 Acciones Recomendadas de Escalamiento ({len(recomendaciones)})",
        ""
    ])

    if recomendaciones:
        for idx, rec in enumerate(recomendaciones, 1):
            md.append(f"{idx}. **[{rec['prioridad']}]** {rec['accion']}  \n   *Destinatario:* **{rec['destinatario_escalamiento']}** | *Canal:* _{rec['canal_sugerido']}_")
    else:
        md.append("ℹ️ *Sin recomendaciones adicionales de escalamiento.*")

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    md.extend([
        "",
        "---",
        f"*Generado el: {now_str} | Plataforma HALO Líderes TI*"
    ])

    return "\n".join(md)


def compilar_minuta_html(
    proyecto: dict,
    salud: dict,
    antiguedad_dias: int,
    porcentaje_avance: float,
    solots_ejecutadas: int,
    total_solots: int,
    cuellos_de_botella: list,
    recomendaciones: list
) -> str:
    num_proy = proyecto.get("Numero_Proyecto") or "S/N"
    cliente = proyecto.get("Cliente") or "Sin Cliente"
    lt_asignado = proyecto.get("LT_Asignado") or "No asignado"
    solicitante = proyecto.get("Solicitante") or "No especificado"
    estado_sp = proyecto.get("Estado") or "Generado"
    salud_label = salud.get("label", "Sin Datos") if salud else "Sin Datos"
    salud_color = (salud.get("color") or "").lower() if salud else "gray"
    badge_bg = "#fee2e2" if salud_color == "red" else ("#fef3c7" if salud_color == "yellow" else ("#d1fae5" if salud_color == "green" else "#f3f4f6"))
    badge_fg = "#dc2626" if salud_color == "red" else ("#d97706" if salud_color == "yellow" else ("#059669" if salud_color == "green" else "#4b5563"))

    cuellos_html = ""
    if cuellos_de_botella:
        items = []
        for cb in cuellos_de_botella:
            sev_bg = "#fee2e2" if cb["severidad"] == "CRITICA" else ("#fef3c7" if cb["severidad"] == "ALTA" else "#e0f2fe")
            sev_fg = "#dc2626" if cb["severidad"] == "CRITICA" else ("#d97706" if cb["severidad"] == "ALTA" else "#0369a1")
            items.append(f"""
            <li style="margin-bottom: 8px;">
                <span style="display: inline-block; padding: 2px 6px; font-size: 11px; font-weight: bold; border-radius: 4px; background: {sev_bg}; color: {sev_fg};">{cb['severidad']}</span>
                <strong>{cb['identificador']}</strong>: {cb['descripcion']} <span style="color: #666; font-size: 12px;">(Área: {cb['responsable_area']})</span>
            </li>
            """)
        cuellos_html = f"<ul style='padding-left: 20px; margin: 8px 0;'>{''.join(items)}</ul>"
    else:
        cuellos_html = "<p style='color: #059669; font-weight: 500; margin: 8px 0;'>✅ No se detectaron cuellos de botella ni bloqueos operacionales en este proyecto.</p>"

    recs_html = ""
    if recomendaciones:
        items = []
        for r in recomendaciones:
            prio_bg = "#fee2e2" if r["prioridad"] == "URGENTE" else ("#fef3c7" if r["prioridad"] == "ALTA" else "#e0f2fe")
            prio_fg = "#dc2626" if r["prioridad"] == "URGENTE" else ("#d97706" if r["prioridad"] == "ALTA" else "#0369a1")
            items.append(f"""
            <li style="margin-bottom: 10px;">
                <span style="display: inline-block; padding: 2px 6px; font-size: 11px; font-weight: bold; border-radius: 4px; background: {prio_bg}; color: {prio_fg};">{r['prioridad']}</span>
                <strong>{r['accion']}</strong><br/>
                <span style="font-size: 12px; color: #555;">Destinatario: <strong>{r['destinatario_escalamiento']}</strong> | Canal: <em>{r['canal_sugerido']}</em></span>
            </li>
            """)
        recs_html = f"<ol style='padding-left: 20px; margin: 8px 0;'>{''.join(items)}</ol>"
    else:
        recs_html = "<p style='color: #555; margin: 8px 0;'>Sin recomendaciones adicionales de escalamiento.</p>"

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""
    <div style="font-family: Arial, Helvetica, sans-serif; font-size: 14px; color: #222; line-height: 1.5; max-width: 700px; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; background: #ffffff;">
        <div style="background: linear-gradient(135deg, #B52217 0%, #DA291C 100%); color: #ffffff; padding: 16px 20px;">
            <h2 style="margin: 0; font-size: 18px; font-weight: 700;">⚡ Diagnóstico Ejecutivo — HALO Líderes TI</h2>
            <p style="margin: 4px 0 0 0; font-size: 12px; opacity: 0.9;">Reporte Operacional en Tiempo Real</p>
        </div>
        <div style="padding: 20px;">
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 16px;">
                <tr>
                    <td style="padding: 6px 0; color: #64748b; width: 140px;"><strong>Proyecto:</strong></td>
                    <td style="padding: 6px 0; font-family: monospace; font-weight: bold; color: #DA291C;">{num_proy}</td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; color: #64748b;"><strong>Cliente:</strong></td>
                    <td style="padding: 6px 0; font-weight: bold;">{cliente}</td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; color: #64748b;"><strong>Líder TI:</strong></td>
                    <td style="padding: 6px 0;">{lt_asignado}</td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; color: #64748b;"><strong>Solicitante:</strong></td>
                    <td style="padding: 6px 0;">{solicitante}</td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; color: #64748b;"><strong>Estado SP:</strong></td>
                    <td style="padding: 6px 0;">{estado_sp}</td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; color: #64748b;"><strong>Salud Operacional:</strong></td>
                    <td style="padding: 6px 0;">
                        <span style="display: inline-block; padding: 3px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; background: {badge_bg}; color: {badge_fg};">
                            {salud_label}
                        </span>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; color: #64748b;"><strong>Antigüedad:</strong></td>
                    <td style="padding: 6px 0;">{antiguedad_dias} días</td>
                </tr>
                <tr>
                    <td style="padding: 6px 0; color: #64748b;"><strong>Avance Solots SGA:</strong></td>
                    <td style="padding: 6px 0;"><strong>{porcentaje_avance}%</strong> ({solots_ejecutadas} de {total_solots} ejecutadas)</td>
                </tr>
            </table>

            <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 16px 0;" />

            <h3 style="font-size: 15px; color: #0f172a; margin: 0 0 8px 0;">🚨 Cuellos de Botella Detectados ({len(cuellos_de_botella)})</h3>
            {cuellos_html}

            <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 16px 0;" />

            <h3 style="font-size: 15px; color: #0f172a; margin: 0 0 8px 0;">🎯 Recomendaciones de Escalamiento ({len(recomendaciones)})</h3>
            {recs_html}

            <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 16px 0;" />

            <p style="margin: 0; font-size: 11px; color: #94a3b8; text-align: right;">
                Generado el {now_str} | Plataforma HALO Líderes TI
            </p>
        </div>
    </div>
    """
    return html.strip()


def get_diagnostico_proyecto(proyecto_id: int):
    """
    Genera el diagnóstico ejecutivo y operacional de un proyecto en tiempo real,
    analizando datos de dbo.Proyectos, dbo.CT_BACKLOG_OPERACIONES2,
    dbo.registrosRF_SD_SM y dbo.registrosSM_RFC.
    """
    # 1. Obtener datos del proyecto base
    proyecto = get_proyecto_by_id(proyecto_id)
    if not proyecto:
        return None

    numero_proyecto = proyecto.get("Numero_Proyecto")
    cliente = proyecto.get("Cliente", "Sin Cliente")
    lt_asignado = proyecto.get("LT_Asignado", "Sin Asignar")
    solicitante = proyecto.get("Solicitante") or "No especificado"
    estado_sp = proyecto.get("Estado", "Generado")
    tipo_servicio = proyecto.get("Tipo_Servicio", "Otros")
    salud = proyecto.get("salud", {})
    fecha_creacion_lti = proyecto.get("Creado") or proyecto.get("fecha_solicitud_lti")

    # 2. Calcular antigüedad en días
    creado_dt = proyecto.get("Creado")
    antiguedad_dias = 0
    hoy = datetime.date.today()
    if creado_dt:
        try:
            if isinstance(creado_dt, str):
                clean_str = creado_dt.replace("Z", "")
                if " " in clean_str:
                    dt = datetime.datetime.strptime(clean_str[:19], '%Y-%m-%d %H:%M:%S').date()
                else:
                    dt = datetime.date.fromisoformat(clean_str[:10])
                antiguedad_dias = max(0, (hoy - dt).days)
            elif isinstance(creado_dt, datetime.datetime):
                antiguedad_dias = max(0, (hoy - creado_dt.date()).days)
            elif isinstance(creado_dt, datetime.date):
                antiguedad_dias = max(0, (hoy - creado_dt).days)
        except Exception:
            pass

    # 3. Obtener elementos asociados
    solots = get_solots_by_proyecto(proyecto_id, numero_proyecto)
    tickets = get_tickets_by_proyecto(proyecto_id, numero_proyecto)
    rfcs = get_rfcs_by_proyecto(proyecto_id, numero_proyecto)

    # Estados cerrados canónicos de Solots
    estados_cerrados_solot = {
        'cerrada', '5- ejecutada', '5- ejecutada tareas pendientes',
        'abortado', 'en aborcion', 'eliminada', 'aprobado'
    }

    # 4. Análisis de Solots
    total_solots = len(solots)
    solots_ejecutadas = 0
    solots_vencidas_list = []
    solots_por_vencer_list = []

    for s in solots:
        estado_otp = (s.get("ESTADO_OTP") or "").strip().lower()
        is_cerrada = estado_otp in estados_cerrados_solot
        if is_cerrada:
            solots_ejecutadas += 1
            continue

        fecha_comp = s.get("FECHA_COMPROMETIDA")
        if fecha_comp:
            try:
                if isinstance(fecha_comp, str):
                    fc = datetime.date.fromisoformat(fecha_comp[:10])
                elif isinstance(fecha_comp, datetime.datetime):
                    fc = fecha_comp.date()
                elif isinstance(fecha_comp, datetime.date):
                    fc = fecha_comp
                else:
                    fc = None

                if fc:
                    if fc < hoy:
                        dias_atraso = (hoy - fc).days
                        solots_vencidas_list.append({
                            "id_otp": s.get("ID_OTP"),
                            "descr": s.get("DESCR_OTP") or "Sin descripción",
                            "dias_atraso": dias_atraso,
                            "area": s.get("GRUPO_ASIGNADO_OTP") or s.get("ASIGNADO_OTP") or "Operaciones SGA",
                            "estado": s.get("ESTADO_OTP") or "Pendiente"
                        })
                    elif fc <= hoy + datetime.timedelta(days=5):
                        solots_por_vencer_list.append({
                            "id_otp": s.get("ID_OTP"),
                            "descr": s.get("DESCR_OTP") or "Sin descripción",
                            "dias_restantes": (fc - hoy).days,
                            "area": s.get("GRUPO_ASIGNADO_OTP") or s.get("ASIGNADO_OTP") or "Operaciones SGA"
                        })
            except Exception:
                pass

    porcentaje_avance = round((solots_ejecutadas / total_solots * 100), 1) if total_solots > 0 else 0.0

    # 5. Análisis de Tickets SD
    total_tickets = len(tickets)
    tickets_abiertos = 0
    tickets_cerrados = 0
    tickets_criticos_list = []
    tickets_atencion_list = []

    for t in tickets:
        status = (t.get("STATUS") or "").strip().lower()
        if status in ('cerrado', 'resuelto'):
            tickets_cerrados += 1
            continue

        tickets_abiertos += 1
        sub_date = t.get("SUBMIT_DATE")
        if sub_date:
            try:
                if isinstance(sub_date, str):
                    sd = datetime.date.fromisoformat(sub_date[:10])
                elif isinstance(sub_date, datetime.datetime):
                    sd = sub_date.date()
                elif isinstance(sub_date, datetime.date):
                    sd = sub_date
                else:
                    sd = None

                if sd:
                    dias_abierto = max(0, (hoy - sd).days)
                    ticket_info = {
                        "incident_id": t.get("CC_INCIDENT_ID"),
                        "brief_description": t.get("BRIEF_DESCRIPTION") or "Sin título",
                        "dias_abierto": dias_abierto,
                        "torre": t.get("ASSIGNED_GROUP") or "Sin Grupo Asignado",
                        "asignado": t.get("ASSIGNED_TO") or "No Asignado",
                        "status": t.get("STATUS") or "Abierto"
                    }
                    if dias_abierto > 14:
                        tickets_criticos_list.append(ticket_info)
                    elif dias_abierto > 7:
                        tickets_atencion_list.append(ticket_info)
            except Exception:
                pass

    # 6. Análisis de RFCs
    total_rfcs = len(rfcs)
    rfcs_abiertas = [r for r in rfcs if not r.get("CLOSE_TIME")]

    # 7. Construcción de Cuellos de Botella
    cuellos_de_botella = []
    cb_count = 1

    for sv in sorted(solots_vencidas_list, key=lambda x: x["dias_atraso"], reverse=True):
        severidad = "CRITICA" if sv["dias_atraso"] > 15 else "ALTA"
        cuellos_de_botella.append({
            "id": f"CB-{cb_count:02d}",
            "tipo": "SOLOT_VENCIDA",
            "severidad": severidad,
            "identificador": f"OTP-{sv['id_otp']}",
            "descripcion": f"Solot vencida hace {sv['dias_atraso']} días ({sv['descr']}).",
            "dias_atraso": sv["dias_atraso"],
            "responsable_area": sv["area"],
            "estado_actual": sv["estado"]
        })
        cb_count += 1

    for tc in sorted(tickets_criticos_list, key=lambda x: x["dias_abierto"], reverse=True):
        cuellos_de_botella.append({
            "id": f"CB-{cb_count:02d}",
            "tipo": "TICKET_DETENIDO",
            "severidad": "CRITICA",
            "identificador": str(tc["incident_id"]),
            "descripcion": f"Ticket detenido hace {tc['dias_abierto']} días sin resolución: '{tc['brief_description']}'.",
            "dias_antiguedad": tc["dias_abierto"],
            "responsable_area": tc["torre"],
            "estado_actual": tc["status"]
        })
        cb_count += 1

    for ta in sorted(tickets_atencion_list, key=lambda x: x["dias_abierto"], reverse=True):
        cuellos_de_botella.append({
            "id": f"CB-{cb_count:02d}",
            "tipo": "TICKET_EN_RIESGO",
            "severidad": "MEDIA",
            "identificador": str(ta["incident_id"]),
            "descripcion": f"Ticket abierto hace {ta['dias_abierto']} días (> 7 días): '{ta['brief_description']}'.",
            "dias_antiguedad": ta["dias_abierto"],
            "responsable_area": ta["torre"],
            "estado_actual": ta["status"]
        })
        cb_count += 1

    for r in rfcs_abiertas:
        cuellos_de_botella.append({
            "id": f"CB-{cb_count:02d}",
            "tipo": "RFC_PENDIENTE",
            "severidad": "MEDIA",
            "identificador": str(r.get("NUMBER")),
            "descripcion": f"RFC abierta sin fecha de cierre: '{r.get('BRIEF_DESCRIPTION') or 'Sin descripción'}'.",
            "dias_antiguedad": None,
            "responsable_area": r.get("ASSIGN_DEPT") or "Gestión de Cambios",
            "estado_actual": "En Proceso"
        })
        cb_count += 1

    # 8. Construcción de Recomendaciones de Escalamiento
    recomendaciones = []
    rec_count = 1

    # Recomendación por tickets críticos en torres
    torres_criticas = {}
    for tc in tickets_criticos_list:
        torre = tc["torre"]
        torres_criticas.setdefault(torre, []).append(tc)

    for torre, tks in torres_criticas.items():
        t_ids = ", ".join([str(t["incident_id"]) for t in tks[:3]])
        max_dias = max([t["dias_abierto"] for t in tks])
        recomendaciones.append({
            "orden": rec_count,
            "prioridad": "URGENTE",
            "destinatario_escalamiento": f"Jefatura / Coordinación de {torre}",
            "accion": f"Escalar de manera urgente la atención de ticket(s) {t_ids} detenido(s) hasta {max_dias} días sin resolución.",
            "canal_sugerido": "Mesa de seguimiento técnico diario / Notificación formal SM"
        })
        rec_count += 1

    # Recomendación por Solots vencidas
    if solots_vencidas_list:
        max_dias_s = max([s["dias_atraso"] for s in solots_vencidas_list])
        recomendaciones.append({
            "orden": rec_count,
            "prioridad": "ALTA",
            "destinatario_escalamiento": "Coordinación Operaciones SGA / Provisión",
            "accion": f"Solicitar reprogramación formal de compromisos o priorización de cuadrilla para {len(solots_vencidas_list)} Solot(s) vencida(s) (hasta {max_dias_s} días de atraso).",
            "canal_sugerido": "Correo formal a operaciones SGA con copia al Jefe de Proyectos"
        })
        rec_count += 1

    # Recomendación por Solicitante / Cliente
    if cuellos_de_botella:
        recomendaciones.append({
            "orden": rec_count,
            "prioridad": "MEDIA",
            "destinatario_escalamiento": f"Solicitante del Proyecto ({solicitante})",
            "accion": "Emitir minuta de estado reportando los bloqueos operacionales en curso y acordar fecha de corte.",
            "canal_sugerido": "Minuta ejecutiva por correo corporativo"
        })
        rec_count += 1
    else:
        recomendaciones.append({
            "orden": 1,
            "prioridad": "BAJA",
            "destinatario_escalamiento": "Líder Técnico Asignado",
            "accion": "Proyecto en operación regular. Mantener seguimiento preventivo de fechas comprometidas.",
            "canal_sugerido": "Revisión semanal de backlog"
        })

    # 9. Generación de Minuta Ejecutiva en Formatos (Texto, MD, HTML)
    minuta_texto = compilar_minuta_texto_plano(
        proyecto, salud, antiguedad_dias, porcentaje_avance,
        solots_ejecutadas, total_solots, cuellos_de_botella, recomendaciones
    )
    minuta_md = compilar_minuta_markdown(
        proyecto, salud, antiguedad_dias, porcentaje_avance,
        solots_ejecutadas, total_solots, cuellos_de_botella, recomendaciones
    )
    minuta_html = compilar_minuta_html(
        proyecto, salud, antiguedad_dias, porcentaje_avance,
        solots_ejecutadas, total_solots, cuellos_de_botella, recomendaciones
    )

    asunto = f"[HALO] Diagnóstico Ejecutivo: Proyecto {numero_proyecto or 'S/N'} - {cliente}"

    return {
        "proyecto_id": proyecto_id,
        "numero_proyecto": numero_proyecto,
        "cliente": cliente,
        "lt_asignado": lt_asignado,
        "solicitante": solicitante,
        "estado_sp": estado_sp,
        "tipo_servicio": tipo_servicio,
        "fecha_creacion_lti": fecha_creacion_lti,
        "antiguedad_dias": antiguedad_dias,
        "salud": salud,
        "resumen_operacional": {
            "total_solots": total_solots,
            "solots_ejecutadas": solots_ejecutadas,
            "solots_pendientes": total_solots - solots_ejecutadas,
            "solots_vencidas": len(solots_vencidas_list),
            "solots_por_vencer": len(solots_por_vencer_list),
            "porcentaje_avance_solots": porcentaje_avance,
            "total_tickets": total_tickets,
            "tickets_abiertos": tickets_abiertos,
            "tickets_cerrados": tickets_cerrados,
            "tickets_criticos": len(tickets_criticos_list),
            "tickets_atencion": len(tickets_atencion_list),
            "total_rfcs": total_rfcs,
            "rfcs_abiertas": len(rfcs_abiertas)
        },
        "cuellos_de_botella": cuellos_de_botella,
        "recomendaciones_escalamiento": recomendaciones,
        "minuta_ejecutiva": {
            "asunto_sugerido": asunto,
            "texto_plano": minuta_texto,
            "markdown": minuta_md,
            "html": minuta_html
        },
        "timestamp_generacion": datetime.datetime.now().isoformat()
    }


def _parse_date(date_val):
    """
    Normaliza valores de fecha provenientes de la base de datos (str, datetime, date)
    a un objeto datetime.date o None.
    """
    if not date_val:
        return None
    if isinstance(date_val, datetime.datetime):
        return date_val.date()
    if isinstance(date_val, datetime.date):
        return date_val
    if isinstance(date_val, str):
        clean_str = date_val.strip().replace("Z", "")
        try:
            return datetime.date.fromisoformat(clean_str[:10])
        except Exception:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
            try:
                return datetime.datetime.strptime(clean_str[:19], fmt).date()
            except Exception:
                pass
    return None


def get_ficha_ejecutiva_data(proyecto_id: int, username: str = "sistema") -> dict:
    """
    Consolida todos los datos del proyecto para la generación de la Ficha Ejecutiva PDF.
    Cruza información de dbo.Proyectos, dbo.CT_BACKLOG_OPERACIONES2,
    dbo.registrosRF_SD_SM y dbo.registrosSM_RFC.
    """
    proyecto = get_proyecto_by_id(proyecto_id)
    if not proyecto:
        return None

    numero_proyecto = proyecto.get("Numero_Proyecto") or "S/N"
    hoy = datetime.date.today()
    ahora = datetime.datetime.now()

    # Reutilizar el motor de diagnóstico existente para métricas y recomendaciones
    diag = get_diagnostico_proyecto(proyecto_id) or {}
    kpis = diag.get("resumen_operacional", {})
    cuellos = diag.get("cuellos_de_botella", [])
    recs = diag.get("recomendaciones_escalamiento", [])

    # Estados cerrados canónicos de Solots
    estados_cerrados_solot = {
        'cerrada', '5- ejecutada', '5- ejecutada tareas pendientes',
        'abortado', 'en aborcion', 'eliminada', 'aprobado'
    }

    # Obtener Solots y formatear para tabla ejecutiva
    solots_raw = get_solots_by_proyecto(proyecto_id, numero_proyecto)
    solots_table = []
    for s in solots_raw:
        fc = s.get("FECHA_COMPROMETIDA")
        fc_fmt = "-"
        dias_atraso = 0
        estado_alerta = "NORMAL"

        if fc:
            fc_date = _parse_date(fc)
            if fc_date:
                fc_fmt = fc_date.strftime("%d/%m/%Y")
                estado_otp_str = (s.get("ESTADO_OTP") or "").strip().lower()
                if fc_date < hoy and estado_otp_str not in estados_cerrados_solot:
                    dias_atraso = (hoy - fc_date).days
                    estado_alerta = "VENCIDA"
                elif fc_date <= hoy + datetime.timedelta(days=5) and estado_otp_str not in estados_cerrados_solot:
                    estado_alerta = "POR_VENCER"

        solots_table.append({
            "id_otp": s.get("ID_OTP"),
            "nro_proyecto": s.get("NRO_PROYECTO") or numero_proyecto,
            "descr_otp": s.get("DESCR_OTP") or "Sin descripción",
            "estado_otp": s.get("ESTADO_OTP") or "Pendiente",
            "fecha_compromiso": str(fc)[:10] if fc else None,
            "fecha_compromiso_fmt": fc_fmt,
            "dias_atraso": dias_atraso,
            "estado_alerta": estado_alerta,
            "servicio": s.get("SERVICIO") or "-",
            "producto": s.get("PRODUCTO") or "-"
        })

    # Obtener Tickets y formatear para tabla ejecutiva
    tickets_raw = get_tickets_by_proyecto(proyecto_id, numero_proyecto)
    tickets_table = []
    for t in tickets_raw:
        sd = t.get("SUBMIT_DATE")
        sd_fmt = "-"
        dias_abierto = 0
        estado_alerta = "NORMAL"

        if sd:
            sd_date = _parse_date(sd)
            if sd_date:
                sd_fmt = sd_date.strftime("%d/%m/%Y")
                if (t.get("STATUS") or "").strip().lower() not in ('cerrado', 'resuelto'):
                    dias_abierto = max(0, (hoy - sd_date).days)
                    if dias_abierto > 14:
                        estado_alerta = "CRITICO"
                    elif dias_abierto > 7:
                        estado_alerta = "ATENCION"

        tickets_table.append({
            "cc_incident_id": t.get("CC_INCIDENT_ID") or "S/I",
            "brief_description": t.get("BRIEF_DESCRIPTION") or "Sin título",
            "assigned_group": t.get("ASSIGNED_GROUP") or "Sin Asignar",
            "assigned_to": t.get("ASSIGNED_TO") or "No asignado",
            "status": t.get("STATUS") or "Abierto",
            "severity": t.get("CATEGORY") or "Normal",
            "submit_date": str(sd)[:10] if sd else None,
            "submit_date_fmt": sd_fmt,
            "dias_abierto": dias_abierto,
            "estado_alerta": estado_alerta
        })

    # Obtener RFCs y formatear para tabla ejecutiva
    rfcs_raw = get_rfcs_by_proyecto(proyecto_id, numero_proyecto)
    rfcs_table = []
    for r in rfcs_raw:
        ct = r.get("CLOSE_TIME")
        ct_fmt = "Pendiente"
        if ct:
            ct_date = _parse_date(ct)
            if ct_date:
                ct_fmt = ct_date.strftime("%d/%m/%Y")

        rfcs_table.append({
            "number": r.get("NUMBER") or "S/N",
            "brief_description": r.get("BRIEF_DESCRIPTION") or "Sin descripción",
            "requested_by": r.get("REQUESTED_BY") or "-",
            "assign_dept": r.get("ASSIGN_DEPT") or "Gestión de Cambios",
            "close_time": str(ct)[:10] if ct else None,
            "close_time_fmt": ct_fmt,
            "estado": "Cerrada" if ct else "En Proceso"
        })

    # Generación de Folio Único Determinista
    # Formato: HALO-FE-YYYY-XXXXXX-HASH (6 dígitos numéricos para satisfacer regex ^HALO-FE-\d{4}-\d{6}-[A-F0-9]{4}$)
    raw_hash_seed = f"{numero_proyecto}_{proyecto_id}_{ahora.strftime('%Y%m%d%H%M')}_{username}"
    checksum = hashlib.sha256(raw_hash_seed.encode('utf-8')).hexdigest()[:4].upper()
    digits = re.sub(r'\D', '', str(numero_proyecto))
    num_code = digits[-6:].zfill(6) if digits else str(proyecto_id).zfill(6)
    folio = f"HALO-FE-{ahora.year}-{num_code}-{checksum}"

    return {
        "folio": folio,
        "fecha_emision": ahora.isoformat(),
        "fecha_emision_formateada": ahora.strftime("%d/%m/%Y %H:%M"),
        "usuario_generador": username,
        "proyecto": {
            "id": proyecto.get("ID"),
            "numero_proyecto": numero_proyecto,
            "cliente": proyecto.get("Cliente") or "Sin Cliente",
            "lt_asignado": proyecto.get("LT_Asignado") or "No Asignado",
            "solicitante": proyecto.get("Solicitante") or "No Especificado",
            "estado_sp": proyecto.get("Estado") or "Generado",
            "tipo_servicio": proyecto.get("Tipo_Servicio") or "Servicios TI",
            "fecha_creacion_lti": proyecto.get("Creado"),
            "antiguedad_dias": diag.get("antiguedad_dias", 0),
            "salud": proyecto.get("salud", {})
        },
        "kpis": kpis,
        "diagnostico_sintetico": {
            "resumen": diag.get("minuta_ejecutiva", {}).get("asunto_sugerido", ""),
            "cuellos_de_botella": cuellos[:5],
            "recomendaciones": recs[:4]
        },
        "tablas": {
            "solots": solots_table,
            "tickets": tickets_table,
            "rfcs": rfcs_table
        }
    }


def generar_ficha_ejecutiva_html(data: dict, auto_print: bool = False) -> str:
    """
    Renderiza el documento HTML A4 corporativo Claro HALO de la Ficha Ejecutiva.
    Cumple con el estándar visual institucional (#B52217, #0097A9), tipografía,
    membrete, tablas compactas, firmas y estilos @media print.
    """
    folio = html.escape(str(data.get("folio", "")))
    fecha_emision = html.escape(str(data.get("fecha_emision_formateada", "")))
    usuario = html.escape(str(data.get("usuario_generador", "sistema")))

    proy = data.get("proyecto") or {}
    num_proy = html.escape(str(proy.get("numero_proyecto") or "S/N"))
    cliente = html.escape(str(proy.get("cliente") or "Sin Cliente"))
    lt_asignado = html.escape(str(proy.get("lt_asignado") or "No Asignado"))
    solicitante = html.escape(str(proy.get("solicitante") or "No Especificado"))
    estado_sp = html.escape(str(proy.get("estado_sp") or "Generado"))
    tipo_servicio = html.escape(str(proy.get("tipo_servicio") or "Servicios TI"))
    antiguedad_dias = proy.get("antiguedad_dias") or 0

    salud = proy.get("salud") or {}
    salud_label = html.escape(str(salud.get("label") or "Sin Datos"))
    salud_color = (salud.get("color") or "gray").lower()

    if salud_color == "red":
        badge_bg, badge_fg, badge_border = "#fee2e2", "#dc2626", "#fca5a5"
    elif salud_color == "yellow":
        badge_bg, badge_fg, badge_border = "#fef3c7", "#d97706", "#fcd34d"
    elif salud_color == "green":
        badge_bg, badge_fg, badge_border = "#ecfdf5", "#059669", "#6ee7b7"
    else:
        badge_bg, badge_fg, badge_border = "#f3f4f6", "#4b5563", "#d1d5db"

    kpis = data.get("kpis") or {}
    total_solots = kpis.get("total_solots") or 0
    solots_ejec = kpis.get("solots_ejecutadas") or 0
    solots_venc = kpis.get("solots_vencidas") or 0
    solots_por_venc = kpis.get("solots_por_vencer") or 0
    pct_avance = kpis.get("porcentaje_avance_solots") or 0.0

    total_tickets = kpis.get("total_tickets") or 0
    tickets_abiertos = kpis.get("tickets_abiertos") or 0
    tickets_criticos = kpis.get("tickets_criticos") or 0

    total_rfcs = kpis.get("total_rfcs") or 0
    rfcs_abiertas = kpis.get("rfcs_abiertas") or 0

    # Diagnóstico sintético
    diag_sintetico = data.get("diagnostico_sintetico") or {}
    cuellos = diag_sintetico.get("cuellos_de_botella") or []
    recs = diag_sintetico.get("recomendaciones") or []

    cuellos_rows = ""
    if cuellos:
        for cb in cuellos:
            sev = cb.get("severidad", "MEDIA")
            if sev == "CRITICA":
                c_bg, c_fg = "#fee2e2", "#dc2626"
            elif sev == "ALTA":
                c_bg, c_fg = "#fef3c7", "#d97706"
            else:
                c_bg, c_fg = "#e0f2fe", "#0284c7"

            ident = html.escape(str(cb.get("identificador", "")))
            descr = html.escape(str(cb.get("descripcion", "")))
            area = html.escape(str(cb.get("responsable_area", "-")))
            cuellos_rows += f"""
            <div style="display:flex; align-items:flex-start; gap:8px; margin-bottom:5px; font-size:8pt;">
                <span style="display:inline-block; padding:1px 5px; font-size:6.5pt; font-weight:700; border-radius:3px; background:{c_bg}; color:{c_fg};">{sev}</span>
                <span style="font-weight:700; color:#181B20;">{ident}:</span>
                <span style="color:#333; flex:1;">{descr} <em style="color:#666E7A; font-size:7.5pt;">({area})</em></span>
            </div>
            """
    else:
        cuellos_rows = "<p style='color:#059669; font-size:8pt; margin:4px 0;'>✅ No se registran cuellos de botella ni bloqueos operacionales críticos.</p>"

    recs_rows = ""
    if recs:
        for r in recs:
            prio = r.get("prioridad", "MEDIA")
            if prio == "URGENTE":
                p_bg, p_fg = "#fee2e2", "#dc2626"
            elif prio == "ALTA":
                p_bg, p_fg = "#fef3c7", "#d97706"
            else:
                p_bg, p_fg = "#e0f2fe", "#0284c7"

            dest = html.escape(str(r.get("destinatario", r.get("destinatario_escalamiento", ""))))
            accion = html.escape(str(r.get("accion", "")))
            recs_rows += f"""
            <div style="display:flex; align-items:flex-start; gap:8px; margin-bottom:5px; font-size:8pt;">
                <span style="display:inline-block; padding:1px 5px; font-size:6.5pt; font-weight:700; border-radius:3px; background:{p_bg}; color:{p_fg};">{prio}</span>
                <span style="color:#181B20; flex:1;"><strong>{dest}:</strong> {accion}</span>
            </div>
            """
    else:
        recs_rows = "<p style='color:#666E7A; font-size:8pt; margin:4px 0;'>Sin recomendaciones de escalamiento adicionales.</p>"

    # Tablas
    tablas = data.get("tablas") or {}
    solots = tablas.get("solots") or []
    tickets = tablas.get("tickets") or []
    rfcs = tablas.get("rfcs") or []

    solots_tbody = ""
    if solots:
        for s in solots:
            alerta = s.get("estado_alerta", "NORMAL")
            dias_at = s.get("dias_atraso", 0)
            if alerta == "VENCIDA":
                badge_td = f"<span style='background:#fee2e2; color:#dc2626; padding:1px 4px; border-radius:3px; font-weight:700; font-size:7pt;'>VENCIDA (+{dias_at}d)</span>"
            elif alerta == "POR_VENCER":
                badge_td = f"<span style='background:#fef3c7; color:#d97706; padding:1px 4px; border-radius:3px; font-weight:700; font-size:7pt;'>POR VENCER</span>"
            else:
                badge_td = "<span style='color:#059669; font-weight:600; font-size:7pt;'>Al día</span>"

            s_id = html.escape(str(s.get("id_otp") or "-"))
            s_nro = html.escape(str(s.get("nro_proyecto") or "-"))
            s_descr = html.escape(str(s.get("descr_otp") or "-"))
            s_est = html.escape(str(s.get("estado_otp") or "-"))
            s_fc = html.escape(str(s.get("fecha_compromiso_fmt") or "-"))
            s_serv = html.escape(str(s.get("servicio") or "-"))

            solots_tbody += f"""
            <tr>
                <td style="font-family:monospace; font-weight:600;">{s_id}</td>
                <td style="font-family:monospace;">{s_nro}</td>
                <td>{s_descr}</td>
                <td>{s_est}</td>
                <td>{s_fc}</td>
                <td>{badge_td}</td>
                <td>{s_serv}</td>
            </tr>
            """
    else:
        solots_tbody = "<tr><td colspan='7' style='text-align:center; color:#666E7A; font-style:italic;'>No registra Solots asociadas en SGA.</td></tr>"

    tickets_tbody = ""
    if tickets:
        for t in tickets:
            alerta = t.get("estado_alerta", "NORMAL")
            dias_ab = t.get("dias_abierto", 0)
            if alerta == "CRITICO":
                t_badge = f"<span style='background:#fee2e2; color:#dc2626; padding:1px 4px; border-radius:3px; font-weight:700; font-size:7pt;'>{dias_ab}d (Crítico)</span>"
            elif alerta == "ATENCION":
                t_badge = f"<span style='background:#fef3c7; color:#d97706; padding:1px 4px; border-radius:3px; font-weight:700; font-size:7pt;'>{dias_ab}d (Atención)</span>"
            else:
                t_badge = f"<span style='color:#333; font-size:7pt;'>{dias_ab}d</span>"

            t_id = html.escape(str(t.get("cc_incident_id") or "-"))
            t_brief = html.escape(str(t.get("brief_description") or "-"))
            t_grp = html.escape(str(t.get("assigned_group") or "-"))
            t_to = html.escape(str(t.get("assigned_to") or "-"))
            t_sev = html.escape(str(t.get("severity") or "-"))
            t_sub = html.escape(str(t.get("submit_date_fmt") or "-"))
            t_st = html.escape(str(t.get("status") or "-"))

            tickets_tbody += f"""
            <tr>
                <td style="font-family:monospace; font-weight:600;">{t_id}</td>
                <td>{t_brief}</td>
                <td>{t_grp}</td>
                <td>{t_to}</td>
                <td>{t_sev}</td>
                <td>{t_sub}</td>
                <td>{t_st} / {t_badge}</td>
            </tr>
            """
    else:
        tickets_tbody = "<tr><td colspan='7' style='text-align:center; color:#666E7A; font-style:italic;'>No registra Tickets de incidentes o requerimientos.</td></tr>"

    rfcs_tbody = ""
    if rfcs:
        for r in rfcs:
            r_num = html.escape(str(r.get("number") or "-"))
            r_brief = html.escape(str(r.get("brief_description") or "-"))
            r_by = html.escape(str(r.get("requested_by") or "-"))
            r_dept = html.escape(str(r.get("assign_dept") or "-"))
            r_st = html.escape(str(r.get("estado") or "-"))
            r_ct = html.escape(str(r.get("close_time_fmt") or "-"))

            rfcs_tbody += f"""
            <tr>
                <td style="font-family:monospace; font-weight:600;">{r_num}</td>
                <td>{r_brief}</td>
                <td>{r_by}</td>
                <td>{r_dept}</td>
                <td>{r_st} ({r_ct})</td>
            </tr>
            """
    else:
        rfcs_tbody = "<tr><td colspan='5' style='text-align:center; color:#666E7A; font-style:italic;'>No registra RFCs asociadas.</td></tr>"

    auto_print_script = """
    <script>
      window.addEventListener('load', function() {
        setTimeout(function() {
          window.focus();
          window.print();
        }, 350);
      });
    </script>
    """ if auto_print else ""

    document_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ficha Ejecutiva - {num_proy} - {cliente}</title>
  <style>
    @page {{
      size: A4 portrait;
      margin: 10mm 12mm 12mm 12mm;
    }}
    * {{
      box-sizing: border-box;
      -webkit-print-color-adjust: exact !important;
      print-color-adjust: exact !important;
      color-adjust: exact !important;
    }}
    body {{
      font-family: 'Roboto', 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
      font-size: 8.5pt;
      line-height: 1.35;
      color: #181B20;
      background: #ffffff;
      margin: 0;
      padding: 0;
    }}
    .sheet-container {{
      max-width: 210mm;
      margin: 0 auto;
      background: #ffffff;
      padding: 6px;
    }}
    /* Header Institucional */
    .header-band {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 2.5px solid #B52217;
      padding-bottom: 8px;
      margin-bottom: 8px;
    }}
    .brand-left {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .brand-titles h1 {{
      margin: 0;
      font-size: 11pt;
      font-weight: 800;
      color: #B52217;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }}
    .brand-titles h2 {{
      margin: 2px 0 0 0;
      font-size: 8.5pt;
      font-weight: 700;
      color: #0097A9;
      letter-spacing: 0.3px;
    }}
    .meta-band {{
      display: flex;
      justify-content: space-between;
      background: #F4F5F7;
      border-left: 3px solid #0097A9;
      padding: 4px 8px;
      font-size: 7.5pt;
      color: #666E7A;
      margin-bottom: 10px;
      border-radius: 2px;
    }}
    .meta-item strong {{
      color: #181B20;
    }}
    /* Secciones */
    .section-title {{
      font-size: 8.5pt;
      font-weight: 800;
      color: #B52217;
      text-transform: uppercase;
      margin: 8px 0 4px 0;
      padding-bottom: 2px;
      border-bottom: 1px solid #E3E6EB;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .section-title::before {{
      content: '';
      display: inline-block;
      width: 4px;
      height: 10px;
      background: #0097A9;
      border-radius: 1px;
    }}
    /* Ficha Resumen 2 Columnas */
    .info-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 6px;
      background: #F4F5F7;
      padding: 6px 10px;
      border-radius: 4px;
      border: 1px solid #E3E6EB;
      margin-bottom: 8px;
    }}
    .info-cell {{
      display: flex;
      flex-direction: column;
    }}
    .info-label {{
      font-size: 6.8pt;
      color: #666E7A;
      text-transform: uppercase;
      font-weight: 700;
    }}
    .info-val {{
      font-size: 8pt;
      font-weight: 600;
      color: #181B20;
    }}
    /* KPI Cards */
    .kpis-row {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 6px;
      margin-bottom: 8px;
    }}
    .kpi-card {{
      background: #F4F5F7;
      border: 1px solid #E3E6EB;
      border-radius: 4px;
      padding: 6px 8px;
      text-align: center;
    }}
    .kpi-title {{
      font-size: 6.8pt;
      font-weight: 700;
      color: #666E7A;
      text-transform: uppercase;
    }}
    .kpi-metric {{
      font-size: 11pt;
      font-weight: 800;
      color: #B52217;
      margin: 1px 0;
    }}
    .kpi-sub {{
      font-size: 6.8pt;
      color: #181B20;
    }}
    /* Tablas Compactas */
    .table-compact {{
      width: 100%;
      border-collapse: collapse;
      font-size: 7.2pt;
      margin-bottom: 8px;
    }}
    .table-compact th {{
      background: #0097A9;
      color: #ffffff;
      font-weight: 700;
      text-align: left;
      padding: 3px 5px;
      border: 1px solid #008797;
    }}
    .table-compact td {{
      padding: 3px 5px;
      border: 1px solid #E3E6EB;
      color: #181B20;
    }}
    .table-compact tr:nth-child(even) {{
      background: #F9FAFB;
    }}
    /* Bloque Diagnóstico */
    .diag-box {{
      background: #ffffff;
      border: 1px solid #E3E6EB;
      border-radius: 4px;
      padding: 6px 8px;
      margin-bottom: 8px;
    }}
    .diag-subtitle {{
      font-size: 7.5pt;
      font-weight: 700;
      color: #0097A9;
      margin: 4px 0 3px 0;
    }}
    /* Firmas y Cierre */
    .signatures-block {{
      display: flex;
      justify-content: space-around;
      margin-top: 14px;
      padding-top: 10px;
      page-break-inside: avoid;
      break-inside: avoid;
    }}
    .sign-box {{
      text-align: center;
      width: 42%;
    }}
    .sign-line {{
      border-top: 1px solid #181B20;
      margin-bottom: 4px;
    }}
    .sign-name {{
      font-size: 8pt;
      font-weight: 700;
      color: #181B20;
    }}
    .sign-role {{
      font-size: 7.2pt;
      color: #666E7A;
    }}
    .footer-band {{
      margin-top: 12px;
      border-top: 1px solid #E3E6EB;
      padding-top: 4px;
      display: flex;
      justify-content: space-between;
      font-size: 6.8pt;
      color: #666E7A;
      page-break-inside: avoid;
      break-inside: avoid;
    }}
    @media print {{
      body {{
        background: #ffffff !important;
      }}
      .sheet-container {{
        padding: 0;
      }}
      .page-break-avoid {{
        page-break-inside: avoid !important;
        break-inside: avoid !important;
      }}
    }}
  </style>
</head>
<body>
  <div class="sheet-container">
    <!-- Membrete Corporativo Claro HALO -->
    <header class="header-band">
      <div class="brand-left">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="44" height="44" role="img" aria-label="HALO">
          <g fill="#B52217">
            <circle cx="60" cy="16" r="8"/>
            <circle cx="91" cy="29" r="8"/>
            <circle cx="104" cy="60" r="8"/>
            <circle cx="91" cy="91" r="8"/>
            <circle cx="60" cy="104" r="8"/>
            <circle cx="29" cy="91" r="8"/>
            <circle cx="16" cy="60" r="8"/>
            <circle cx="29" cy="29" r="8"/>
          </g>
          <rect x="47" y="47" width="26" height="26" rx="8" fill="#0097A9"/>
        </svg>
        <div class="brand-titles">
          <h1>CLARO CHILE — DIRECCIÓN DE OPERACIONES Y SERVICIOS TI</h1>
          <h2>FICHA EJECUTIVA DE CONTROL OPERACIONAL DE PROYECTO</h2>
        </div>
      </div>
      <div style="text-align:right;">
        <span style="display:inline-block; padding:2px 8px; border-radius:3px; font-size:7pt; font-weight:800; background:#FDEDEA; color:#B52217; border:1px solid #fca5a5;">
          CONFIDENCIAL — USO INTERNO
        </span>
      </div>
    </header>

    <!-- Barra de Metadatos de Control -->
    <div class="meta-band">
      <div class="meta-item">FOLIO: <strong>{folio}</strong></div>
      <div class="meta-item">FECHA DE CORTE: <strong>{fecha_emision}</strong></div>
      <div class="meta-item">EMITIDO POR: <strong>{usuario}</strong></div>
      <div class="meta-item">PLATAFORMA: <strong>HALO LÍDERES TI</strong></div>
    </div>

    <!-- 1. Resumen General del Proyecto -->
    <div class="section-title">1. Resumen General del Proyecto</div>
    <div class="info-grid">
      <div class="info-cell">
        <span class="info-label">N° Proyecto</span>
        <span class="info-val" style="color:#B52217; font-family:monospace;">{num_proy}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Cliente / Razón Social</span>
        <span class="info-val">{cliente}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Tipo de Servicio</span>
        <span class="info-val">{tipo_servicio}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Solicitante</span>
        <span class="info-val">{solicitante}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Líder TI Responsable</span>
        <span class="info-val">{lt_asignado}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Estado SharePoint</span>
        <span class="info-val">{estado_sp}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Antigüedad</span>
        <span class="info-val">{antiguedad_dias} días</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Salud Operacional</span>
        <span class="info-val">
          <span style="display:inline-block; padding:1px 6px; border-radius:3px; font-size:7pt; font-weight:700; background:{badge_bg}; color:{badge_fg}; border:1px solid {badge_border};">
            {salud_label}
          </span>
        </span>
      </div>
    </div>

    <!-- 2. Indicadores Clave de Rendimiento (KPIs) -->
    <div class="section-title">2. Indicadores Clave de Rendimiento (KPIs)</div>
    <div class="kpis-row">
      <div class="kpi-card">
        <div class="kpi-title">Solots SGA</div>
        <div class="kpi-metric">{solots_ejec} / {total_solots}</div>
        <div class="kpi-sub">{pct_avance}% Avance Global</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">Solots Vencidas</div>
        <div class="kpi-metric" style="color:{'#dc2626' if solots_venc > 0 else '#059669'};">{solots_venc}</div>
        <div class="kpi-sub">{solots_por_venc} por vencer en &le;5d</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">Tickets HPSM / SD</div>
        <div class="kpi-metric">{tickets_abiertos} / {total_tickets}</div>
        <div class="kpi-sub" style="color:{'#dc2626' if tickets_criticos > 0 else '#666E7A'};">{tickets_criticos} Críticos (&gt;14d)</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">RFCs de Cambio</div>
        <div class="kpi-metric">{rfcs_abiertas}</div>
        <div class="kpi-sub">{total_rfcs} Asociadas</div>
      </div>
    </div>

    <!-- 3. Síntesis de Diagnóstico Operacional y Plan de Escalamiento -->
    <div class="section-title">3. Síntesis de Diagnóstico y Plan de Escalamiento</div>
    <div class="diag-box">
      <div class="diag-subtitle">🚨 Cuellos de Botella Detectados</div>
      {cuellos_rows}
      <div class="diag-subtitle" style="margin-top:6px;">🎯 Recomendaciones Ejecutivas de Escalamiento</div>
      {recs_rows}
    </div>

    <!-- 4. Detalle Técnico de Solots de Backlog (SGA) -->
    <div class="section-title">4. Detalle Técnico de Solots SGA</div>
    <table class="table-compact">
      <thead>
        <tr>
          <th style="width:75px;">ID OTP</th>
          <th style="width:75px;">N° Proyecto</th>
          <th>Descripción del Servicio</th>
          <th style="width:90px;">Estado OTP</th>
          <th style="width:75px;">Fecha Comp.</th>
          <th style="width:95px;">Alerta Atraso</th>
          <th style="width:110px;">Servicio</th>
        </tr>
      </thead>
      <tbody>
        {solots_tbody}
      </tbody>
    </table>

    <!-- 5. Detalle Técnico de Tickets HPSM / SD -->
    <div class="section-title">5. Detalle de Incidentes y Requerimientos (HPSM / SD)</div>
    <table class="table-compact">
      <thead>
        <tr>
          <th style="width:80px;">Incident ID</th>
          <th>Resumen Incidente</th>
          <th style="width:100px;">Torre Asignada</th>
          <th style="width:110px;">Responsable</th>
          <th style="width:65px;">Severidad</th>
          <th style="width:75px;">Apertura</th>
          <th style="width:105px;">Estado / Permanencia</th>
        </tr>
      </thead>
      <tbody>
        {tickets_tbody}
      </tbody>
    </table>

    <!-- 6. Solicitudes de Cambio (RFCs) -->
    <div class="section-title">6. Solicitudes de Cambio Asociadas (RFCs)</div>
    <table class="table-compact">
      <thead>
        <tr>
          <th style="width:90px;">N° RFC</th>
          <th>Descripción del Cambio</th>
          <th style="width:120px;">Solicitante</th>
          <th style="width:110px;">Área Asignada</th>
          <th style="width:110px;">Estado / Cierre</th>
        </tr>
      </thead>
      <tbody>
        {rfcs_tbody}
      </tbody>
    </table>

    <!-- 7. Validación y Firmas Institucionales -->
    <div class="page-break-avoid">
      <div class="section-title">7. Validación y Responsabilidad Técnica</div>
      <div class="signatures-block">
        <div class="sign-box">
          <div class="sign-line"></div>
          <div class="sign-name">{lt_asignado}</div>
          <div class="sign-role">Líder Técnico TI Responsable</div>
          <div class="sign-role">Dirección de Operaciones TI</div>
        </div>
        <div class="sign-box">
          <div class="sign-line"></div>
          <div class="sign-name">JEFATURA DE OPERACIONES TI</div>
          <div class="sign-role">Gestión de Proyectos & Servicios</div>
          <div class="sign-role">Claro Chile S.A.</div>
        </div>
      </div>

      <!-- Pie Institucional -->
      <footer class="footer-band">
        <div>Folio: <strong>{folio}</strong> | Clasificación: <strong>CONFIDENCIAL — USO INTERNO</strong></div>
        <div>Generado en Plataforma HALO Líderes TI | Claro Chile S.A.</div>
      </footer>
    </div>
  </div>
  {auto_print_script}
</body>
</html>"""
    return document_html


def _parse_timeline_dt(val):
    """
    Normaliza valores de fecha/hora heterogéneos (datetime, date, str ISO o formatos comunes)
    a un objeto datetime.datetime con resolución horaria o None si es inválido.
    """
    if not val:
        return None
    if isinstance(val, datetime.datetime):
        return val
    if isinstance(val, datetime.date):
        return datetime.datetime.combine(val, datetime.time.min)
    if isinstance(val, str):
        clean_str = val.strip().replace("Z", "")
        if not clean_str or clean_str.upper() in ("NONE", "NULL", "INVALID DATE", "N/A", "-"):
            return None
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%d",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y",
            "%Y/%m/%d",
            "%d-%m-%Y"
        ):
            try:
                return datetime.datetime.strptime(clean_str[:26], fmt)
            except Exception:
                pass
        try:
            d = datetime.date.fromisoformat(clean_str[:10])
            return datetime.datetime.combine(d, datetime.time.min)
        except Exception:
            pass
    return None


def get_timeline_proyecto(proyecto_id: int) -> dict | None:
    """
    Consolida, unifica y ordena cronológicamente todos los hitos del proyecto
    a partir de dbo.Proyectos, dbo.CT_BACKLOG_OPERACIONES2, dbo.registrosRF_SD_SM
    y dbo.registrosSM_RFC.
    """
    proyecto = get_proyecto_by_id(proyecto_id)
    if not proyecto:
        return None

    numero_proyecto = proyecto.get("Numero_Proyecto")
    solots = get_solots_by_proyecto(proyecto_id, numero_proyecto) or []
    tickets = get_tickets_by_proyecto(proyecto_id, numero_proyecto) or []
    rfcs = get_rfcs_by_proyecto(proyecto_id, numero_proyecto) or []

    hoy = datetime.date.today()
    eventos = []

    # 1. Extracción de Hitos de SharePoint (dbo.Proyectos)
    # 1.1 Creación / Solicitud LTI
    fecha_creacion = _parse_timeline_dt(proyecto.get("fecha_solicitud_lti") or proyecto.get("Creado"))
    if fecha_creacion:
        eventos.append({
            "id": f"sp-creacion-{proyecto_id}",
            "categoria": "sharepoint",
            "categoria_label": "SharePoint",
            "tipo_evento": "creacion",
            "titulo": "Ingreso de Proyecto / Solicitud LTI",
            "descripcion": f"Solicitud ingresada para {proyecto.get('Cliente', 'Sin Cliente')} por {proyecto.get('Solicitante') or 'Usuario LTI'}",
            "fecha": fecha_creacion.isoformat(),
            "estado": proyecto.get("Estado", "Generado"),
            "es_futuro": False,
            "es_atrasado": False,
            "icono": "📁",
            "color_tipo": "#B52217",
            "metadata": {
                "tipo_servicio": proyecto.get("Tipo_Servicio"),
                "lt_asignado": proyecto.get("LT_Asignado")
            }
        })

    # 1.2 Modificación de SharePoint (si es posterior y existe)
    fecha_mod = _parse_timeline_dt(proyecto.get("Modificado"))
    if fecha_mod and fecha_creacion and fecha_mod.date() > fecha_creacion.date():
        eventos.append({
            "id": f"sp-mod-{proyecto_id}",
            "categoria": "sharepoint",
            "categoria_label": "SharePoint",
            "tipo_evento": "actualizacion",
            "titulo": "Actualización en SharePoint",
            "descripcion": f"Última modificación registrada. Estado: {proyecto.get('Estado')}",
            "fecha": fecha_mod.isoformat(),
            "estado": proyecto.get("Estado", "En revision"),
            "es_futuro": False,
            "es_atrasado": False,
            "icono": "📝",
            "color_tipo": "#64748B",
            "metadata": {}
        })

    # 2. Extracción de Hitos de Solots SGA (dbo.CT_BACKLOG_OPERACIONES2)
    estados_cerrados_solot = {
        'cerrada', '5- ejecutada', '5- ejecutada tareas pendientes',
        'abortado', 'en aborcion', 'eliminada', 'aprobado'
    }

    for s in solots:
        otp_id = s.get("ID_OTP")
        descr = s.get("DESCR_OTP") or f"Solot {otp_id}"
        estado_otp = (s.get("ESTADO_OTP") or "").strip()
        is_cerrada = estado_otp.lower() in estados_cerrados_solot

        # 2.1 Apertura / Inserción Solot
        dt_insert = _parse_timeline_dt(s.get("FECHA_INSERT"))
        if dt_insert:
            eventos.append({
                "id": f"solot-insert-{otp_id}",
                "categoria": "solot",
                "categoria_label": "SGA Solots",
                "tipo_evento": "creacion",
                "titulo": f"Apertura Solot SGA #{otp_id}",
                "descripcion": descr,
                "fecha": dt_insert.isoformat(),
                "estado": estado_otp or "Ingresada",
                "es_futuro": False,
                "es_atrasado": False,
                "icono": "⚡",
                "color_tipo": "#0097A9",
                "metadata": {
                    "id_otp": otp_id,
                    "servicio": s.get("SERVICIO"),
                    "producto": s.get("PRODUCTO"),
                    "grupo_asignado": s.get("GRUPO_ASIGNADO_OTP")
                }
            })

        # 2.2 Fecha Compromiso Solot
        dt_comp = _parse_timeline_dt(s.get("FECHA_COMPROMETIDA"))
        if dt_comp:
            es_atrasado = (not is_cerrada) and (dt_comp.date() < hoy)
            es_futuro = dt_comp.date() >= hoy
            dias_atraso = (hoy - dt_comp.date()).days if es_atrasado else 0
            dias_restantes = (dt_comp.date() - hoy).days if es_futuro else 0

            eventos.append({
                "id": f"solot-comp-{otp_id}",
                "categoria": "solot",
                "categoria_label": "SGA Solots",
                "tipo_evento": "compromiso",
                "titulo": f"Compromiso Solot SGA #{otp_id}",
                "descripcion": f"Fecha comprometida: {descr}",
                "fecha": dt_comp.isoformat(),
                "estado": "Vencido" if es_atrasado else ("Pendiente" if not is_cerrada else "Cumplido"),
                "es_atrasado": es_atrasado,
                "es_futuro": es_futuro,
                "dias_atraso": dias_atraso,
                "dias_restantes": dias_restantes,
                "icono": "⚠️" if es_atrasado else ("⏳" if es_futuro else "📅"),
                "color_tipo": "#DC2626" if es_atrasado else ("#D97706" if es_futuro else "#0097A9"),
                "metadata": {
                    "id_otp": otp_id
                }
            })

        # 2.3 Fecha Realización / Cierre Solot
        dt_realiz = _parse_timeline_dt(s.get("FECHA_REALIZACION"))
        if dt_realiz:
            eventos.append({
                "id": f"solot-cierre-{otp_id}",
                "categoria": "solot",
                "categoria_label": "SGA Solots",
                "tipo_evento": "cierre",
                "titulo": f"Cierre / Realización Solot #{otp_id}",
                "descripcion": descr,
                "fecha": dt_realiz.isoformat(),
                "estado": estado_otp or "Cerrada",
                "es_futuro": False,
                "es_atrasado": False,
                "icono": "✅",
                "color_tipo": "#10B981",
                "metadata": {
                    "id_otp": otp_id
                }
            })

    # 3. Extracción de Hitos de Tickets HPSM / SD (dbo.registrosRF_SD_SM)
    estados_cerrados_tickets = {'closed', 'resolved', 'cerrado', 'resuelto'}
    for t in tickets:
        inc_id = t.get("CC_INCIDENT_ID") or t.get("RF_ID") or "SD"
        titulo_t = t.get("BRIEF_DESCRIPTION") or f"Incidente {inc_id}"
        estado_t = (t.get("STATUS") or "").strip()
        is_cerrado_t = estado_t.lower() in estados_cerrados_tickets

        # 3.1 Apertura / Reporte del Ticket
        dt_submit = _parse_timeline_dt(t.get("SUBMIT_DATE"))
        if dt_submit:
            eventos.append({
                "id": f"ticket-submit-{inc_id}",
                "categoria": "ticket",
                "categoria_label": "Tickets SD",
                "tipo_evento": "creacion",
                "titulo": f"Reporte Ticket SD #{inc_id}",
                "descripcion": f"{titulo_t} (Grupo: {t.get('ASSIGNED_GROUP') or 'Sin Grupo'})",
                "fecha": dt_submit.isoformat(),
                "estado": estado_t or "Open",
                "es_futuro": False,
                "es_atrasado": False,
                "icono": "🎫",
                "color_tipo": "#3B82F6",
                "metadata": {
                    "incident_id": inc_id,
                    "grupo_asignado": t.get("ASSIGNED_GROUP"),
                    "solicitante": t.get("REQUESTOR_NAME"),
                    "categoria": t.get("CATEGORY")
                }
            })

        # 3.2 Cierre del Ticket
        dt_close = _parse_timeline_dt(t.get("CLOSE_DATE"))
        if dt_close:
            eventos.append({
                "id": f"ticket-close-{inc_id}",
                "categoria": "ticket",
                "categoria_label": "Tickets SD",
                "tipo_evento": "cierre",
                "titulo": f"Resolución Ticket SD #{inc_id}",
                "descripcion": titulo_t,
                "fecha": dt_close.isoformat(),
                "estado": estado_t or "Closed",
                "es_futuro": False,
                "es_atrasado": False,
                "icono": "✅",
                "color_tipo": "#10B981",
                "metadata": {
                    "incident_id": inc_id
                }
            })

    # 4. Extracción de Hitos de RFCs (dbo.registrosSM_RFC)
    for r in rfcs:
        rfc_num = r.get("NUMBER") or "RFC"
        rfc_desc = r.get("BRIEF_DESCRIPTION") or r.get("DESCRIPTION") or f"Cambio {rfc_num}"

        # 4.1 Creación RFC
        dt_rfc_enter = _parse_timeline_dt(r.get("ORIG_DATE_ENTERED"))
        if dt_rfc_enter:
            eventos.append({
                "id": f"rfc-create-{rfc_num}",
                "categoria": "rfc",
                "categoria_label": "RFCs",
                "tipo_evento": "creacion",
                "titulo": f"Creación RFC #{rfc_num}",
                "descripcion": f"{rfc_desc} (Depto: {r.get('ASSIGN_DEPT') or 'Sin Depto'})",
                "fecha": dt_rfc_enter.isoformat(),
                "estado": r.get("STATUS") or "Ingresada",
                "es_futuro": False,
                "es_atrasado": False,
                "icono": "🔄",
                "color_tipo": "#8B5CF6",
                "metadata": {
                    "rfc_number": rfc_num,
                    "depto": r.get("ASSIGN_DEPT"),
                    "solicitante": r.get("REQUESTED_BY")
                }
            })

        # 4.2 Cierre RFC
        dt_rfc_close = _parse_timeline_dt(r.get("CLOSE_TIME"))
        if dt_rfc_close:
            eventos.append({
                "id": f"rfc-close-{rfc_num}",
                "categoria": "rfc",
                "categoria_label": "RFCs",
                "tipo_evento": "cierre",
                "titulo": f"Cierre / Implementación RFC #{rfc_num}",
                "descripcion": rfc_desc,
                "fecha": dt_rfc_close.isoformat(),
                "estado": r.get("STATUS") or "Cerrada",
                "es_futuro": False,
                "es_atrasado": False,
                "icono": "✅",
                "color_tipo": "#10B981",
                "metadata": {
                    "rfc_number": rfc_num
                }
            })

    # 5. Ordenamiento Cronológico Estricto (Fecha Ascendente) con desempate por ciclo natural
    tipo_prioridad = {
        ("sharepoint", "creacion"): 1,
        ("sharepoint", "actualizacion"): 2,
        ("solot", "creacion"): 3,
        ("ticket", "creacion"): 4,
        ("rfc", "creacion"): 5,
        ("solot", "compromiso"): 6,
        ("solot", "cierre"): 7,
        ("ticket", "cierre"): 8,
        ("rfc", "cierre"): 9
    }

    def sort_key(ev):
        raw_dt = _parse_timeline_dt(ev.get("fecha"))
        prio = tipo_prioridad.get((ev.get("categoria"), ev.get("tipo_evento")), 99)
        return (raw_dt or datetime.datetime.min, prio)

    eventos.sort(key=sort_key)

    # 6. Cálculo de Lapsos Temporales entre Hitos Consecutivos y Formateo DMY
    prev_dt = None
    first_dt = None

    for idx, ev in enumerate(eventos):
        ev_dt = _parse_timeline_dt(ev.get("fecha"))
        if ev_dt:
            if first_dt is None:
                first_dt = ev_dt

            # Formateo DD/MM/YYYY
            ev["fecha_formateada"] = ev_dt.strftime("%d/%m/%Y")

            # Cálculo de lapso con el hito anterior
            if prev_dt is not None:
                dias_diff = max(0, (ev_dt.date() - prev_dt.date()).days)
                ev["lapso_dias"] = dias_diff
            else:
                ev["lapso_dias"] = 0

            prev_dt = ev_dt
        else:
            ev["fecha_formateada"] = "Fecha no disponible"
            ev["lapso_dias"] = 0

    # 7. Cálculo de Lead Time Total
    lead_time_total_dias = 0
    if first_dt:
        lead_time_total_dias = max(0, (hoy - first_dt.date()).days)

    # 8. Consolidación de Métricas de Cabecera
    total_eventos = len(eventos)
    ev_sp = sum(1 for e in eventos if e["categoria"] == "sharepoint")
    ev_solot = sum(1 for e in eventos if e["categoria"] == "solot")
    ev_ticket = sum(1 for e in eventos if e["categoria"] == "ticket")
    ev_rfc = sum(1 for e in eventos if e["categoria"] == "rfc")

    comp_vencidos = sum(1 for e in eventos if e.get("es_atrasado"))
    comp_pendientes = sum(1 for e in eventos if e.get("es_futuro"))

    # Último hito pasado registrado
    hitos_pasados = [e for e in eventos if not e.get("es_futuro")]
    ultimo_hito = hitos_pasados[-1] if hitos_pasados else (eventos[-1] if eventos else None)

    # Próximo compromiso futuro o el más vencido
    hitos_vencidos = [e for e in eventos if e.get("es_atrasado")]
    hitos_futuros = [e for e in eventos if e.get("es_futuro")]

    proximo_compromiso = None
    if hitos_vencidos:
        # Priorizar alerta del compromiso con mayor atraso
        hitos_vencidos.sort(key=lambda x: x.get("dias_atraso", 0), reverse=True)
        critico = hitos_vencidos[0]
        proximo_compromiso = {
            "titulo": critico["titulo"],
            "categoria": critico["categoria"],
            "fecha": critico["fecha"],
            "fecha_formateada": critico["fecha_formateada"],
            "dias_atraso": critico.get("dias_atraso", 0),
            "es_atrasado": True
        }
    elif hitos_futuros:
        proximo_compromiso = {
            "titulo": hitos_futuros[0]["titulo"],
            "categoria": hitos_futuros[0]["categoria"],
            "fecha": hitos_futuros[0]["fecha"],
            "fecha_formateada": hitos_futuros[0]["fecha_formateada"],
            "dias_restantes": hitos_futuros[0].get("dias_restantes", 0),
            "es_atrasado": False
        }

    return {
        "proyecto_id": proyecto_id,
        "numero_proyecto": numero_proyecto,
        "cliente": proyecto.get("Cliente", "Sin Cliente"),
        "lt_asignado": proyecto.get("LT_Asignado", "Sin Asignar"),
        "lead_time_total_dias": lead_time_total_dias,
        "metricas": {
            "total_eventos": total_eventos,
            "eventos_sharepoint": ev_sp,
            "eventos_solot": ev_solot,
            "eventos_ticket": ev_ticket,
            "eventos_rfc": ev_rfc,
            "compromisos_pendientes": comp_pendientes,
            "compromisos_vencidos": comp_vencidos,
            "ultimo_hito": ultimo_hito,
            "proximo_compromiso": proximo_compromiso
        },
        "eventos": eventos
    }


# ==============================================================================
# MÓDULO 015: CENTRO DE ALERTAS TEMPRANAS SLA & ESCALAMIENTO RÁPIDO
# ==============================================================================

def generar_minuta_escalamiento_sla(resumen: dict, alertas: list) -> dict:
    """
    Genera la minuta ejecutiva en texto plano estructurado y el asunto
    para escalamiento rápido de alertas de SLA operacional a comités y jefaturas.
    """
    hoy = datetime.date.today()
    fecha_str = hoy.strftime('%d/%m/%Y')
    
    criticas = [a for a in alertas if a.get('severidad') == 'CRITICAL']
    top_criticas = criticas[:10]
    
    lineas_top = []
    for i, a in enumerate(top_criticas, 1):
        lineas_top.append(
            f"{i}. [{a.get('severidad')}] {a.get('titulo')} - {a.get('subtitulo')} | "
            f"Proyecto: {a.get('numero_proyecto') or 'S/N'} ({a.get('cliente') or 'S/C'}) | "
            f"Líder: {a.get('lt_asignado') or 'S/A'} | "
            f"Resp: {a.get('responsable')} ({a.get('asignado_a')}) | {a.get('detalle_sla')}"
        )
    top_txt = '\n'.join(lineas_top) if lineas_top else 'No se registran desviaciones críticas prioritarias en el periodo.'
    
    texto_plano = f"""======================================================================
CLARO HALO — MINUTA EJECUTIVA DE ESCALAMIENTO OPERACIONAL
Fecha de Emisión: {fecha_str}
======================================================================

1. RESUMEN DE SALUD OPERACIONAL
- Total Alertas SLA: {resumen.get('total_alertas', 0)}
- Alertas Críticas (🔴): {resumen.get('criticas', 0)}
- Advertencias (🟡): {resumen.get('advertencias', 0)}
- Proyectos Críticos Comprometidos: {resumen.get('proyectos_criticos', 0)}

2. DESGLOSE DE INCIDENTES
- Tickets SD Fuera de SLA (>14 días): {resumen.get('tickets_sla_criticos', 0)}
- Tickets SD en Atención Preventiva (>7 días): {resumen.get('tickets_sla_advertencia', 0)}
- Solots SGA Vencidas: {resumen.get('solots_vencidas', 0)}
- Solots Próximas a Vencer (<=48h): {resumen.get('solots_proximas_vencer', 0)}
- Solots Sin Fecha de Compromiso (>10d): {resumen.get('solots_sin_compromiso', 0)}

3. PRINCIPALES DESVIACIONES CRÍTICAS (TOP 10)
{top_txt}

======================================================================
Generado automáticamente por Claro HALO - App Líderes TI
======================================================================"""

    return {
        "asunto_sugerido": f"[HALO ESCALAMIENTO] Alertas Críticas de SLA Operacional - {fecha_str}",
        "texto_plano": texto_plano,
        "destinatarios_sugeridos": [
            "jefatura.operaciones@clarovtr.cl",
            "soporte.sga@clarovtr.cl"
        ]
    }


def procesar_alertas_sla(raw_tickets: list, raw_solots: list, lider: str = None, severidad: str = "todas", tipo: str = "todos", limite: int = 100) -> dict:
    """
    Aplica las reglas canónicas de clasificación de severidad para tickets HPSM y Solots SGA,
    calcula métricas de resumen, genera la minuta de escalamiento y retorna el payload estructurado.
    """
    hoy = datetime.date.today()
    alertas_todas = []

    # 1. Reglas de SLA para Tickets HPSM / SD
    estados_cerrados_tickets = {'cerrado', 'resuelto', 'closed', 'resolved'}
    for t in (raw_tickets or []):
        st = (t.get("STATUS") or "").strip().lower()
        if st in estados_cerrados_tickets:
            continue

        dt_submit = _parse_timeline_dt(t.get("SUBMIT_DATE"))
        if not dt_submit:
            continue

        dias_abierto = (hoy - dt_submit.date()).days
        if dias_abierto <= 7:
            continue  # Dentro de SLA preventivo y crítico

        if dias_abierto > 14:
            sev = "CRITICAL"
            badge_color = "red"
            detalle = f"{dias_abierto} días abierto en torre (>14d límite SLA)"
        else:
            sev = "WARNING"
            badge_color = "amber"
            detalle = f"{dias_abierto} días en atención (>7d límite preventivo)"

        inc_id = t.get("CC_INCIDENT_ID") or t.get("RF_ID") or "SD"
        pid = t.get("p_id") if t.get("p_id") is not None else (t.get("ID_Proyecto") or t.get("proyecto_id"))
        if pid is not None:
            try:
                pid = int(pid)
            except (ValueError, TypeError):
                pass

        num_proy = t.get("p_numero") or t.get("Numero_Proyecto_Limpio") or t.get("numero_proyecto")
        if num_proy:
            num_proy = str(num_proy).strip()

        cli = t.get("p_cliente") or t.get("cliente")
        lt = t.get("p_lider") or t.get("lt_asignado") or "Sin Asignar"
        resp = t.get("ASSIGNED_GROUP") or t.get("responsable") or "Sin Grupo"
        asig = t.get("ASSIGNED_TO") or t.get("asignado_a") or "Sin Asignar"
        subt = t.get("BRIEF_DESCRIPTION") or t.get("subtitulo") or f"Ticket SD {inc_id}"

        alertas_todas.append({
            "id": f"TICKET-{inc_id}",
            "tipo": "ticket",
            "severidad": sev,
            "icono": "🎫",
            "titulo": str(inc_id),
            "subtitulo": str(subt),
            "proyecto_id": pid,
            "numero_proyecto": num_proy,
            "cliente": cli,
            "lt_asignado": lt,
            "responsable": resp,
            "responsable_tipo": "Torre Operativa",
            "asignado_a": asig,
            "dias_fuera_sla": dias_abierto,
            "fecha_referencia": dt_submit.strftime("%Y-%m-%d"),
            "detalle_sla": detalle,
            "badge_color": badge_color
        })

    # 2. Reglas de SLA para Solots SGA
    estados_cerrados_solot = {
        'cerrada', '5- ejecutada', '5- ejecutada tareas pendientes',
        'abortado', 'en aborcion', 'eliminada', 'aprobado'
    }

    for s in (raw_solots or []):
        st_otp = (s.get("ESTADO_OTP") or "").strip().lower()
        if st_otp in estados_cerrados_solot:
            continue

        dt_comp = _parse_timeline_dt(s.get("FECHA_COMPROMETIDA"))
        dt_insert = _parse_timeline_dt(s.get("FECHA_INSERT"))

        sev = None
        badge_color = None
        detalle = ""
        dias_fuera = 0
        fecha_ref_str = ""

        if dt_comp:
            fecha_ref_str = dt_comp.strftime("%Y-%m-%d")
            if dt_comp.date() < hoy:
                # Solot vencida
                dias_atraso = (hoy - dt_comp.date()).days
                sev = "CRITICAL"
                badge_color = "red"
                dias_fuera = dias_atraso
                detalle = f"Vencida hace {dias_atraso} días (Compromiso: {fecha_ref_str})"
            elif dt_comp.date() <= hoy + datetime.timedelta(days=2):
                # Próxima a vencer en <= 48h
                dias_restantes = (dt_comp.date() - hoy).days
                sev = "WARNING"
                badge_color = "amber"
                dias_fuera = 0
                if dias_restantes == 0:
                    detalle = f"Vence hoy (Compromiso: {fecha_ref_str})"
                elif dias_restantes == 1:
                    detalle = f"Vence mañana (Compromiso: {fecha_ref_str})"
                else:
                    detalle = f"Próxima a vencer en {dias_restantes} días (Compromiso: {fecha_ref_str})"
        else:
            # Sin fecha comprometida
            if dt_insert:
                fecha_ref_str = dt_insert.strftime("%Y-%m-%d")
                dias_creacion = (hoy - dt_insert.date()).days
                if dias_creacion > 10:
                    sev = "WARNING"
                    badge_color = "amber"
                    dias_fuera = max(0, dias_creacion - 10)
                    detalle = f"Sin compromiso pactado tras {dias_creacion} días de ingreso"

        if not sev:
            continue

        otp_id = s.get("ID_OTP") or "SGA"
        pid = s.get("p_id") if s.get("p_id") is not None else (s.get("ID_Proyecto") or s.get("proyecto_id"))
        if pid is not None:
            try:
                pid = int(pid)
            except (ValueError, TypeError):
                pass

        num_proy = s.get("p_numero") or s.get("Numero_Proyecto_Limpio") or s.get("numero_proyecto")
        if num_proy:
            num_proy = str(num_proy).strip()

        cli = s.get("p_cliente") or s.get("cliente")
        lt = s.get("p_lider") or s.get("lt_asignado") or "Sin Asignar"
        resp = s.get("GRUPO_ASIGNADO_OTP") or s.get("responsable") or "Área SGA"
        asig = s.get("ASIGNADO_OTP") or s.get("asignado_a") or "Sin Asignar"
        subt = s.get("DESCR_OTP") or s.get("subtitulo") or f"Solot SGA {otp_id}"

        alertas_todas.append({
            "id": f"SOLOT-{otp_id}",
            "tipo": "solot",
            "severidad": sev,
            "icono": "⚡",
            "titulo": f"Solot {otp_id}",
            "subtitulo": str(subt),
            "proyecto_id": pid,
            "numero_proyecto": num_proy,
            "cliente": cli,
            "lt_asignado": lt,
            "responsable": resp,
            "responsable_tipo": "Área SGA",
            "asignado_a": asig,
            "dias_fuera_sla": dias_fuera,
            "fecha_referencia": fecha_ref_str,
            "detalle_sla": detalle,
            "badge_color": badge_color
        })

    # 3. Filtrar por Líder TI si aplica
    if lider and lider.strip() and lider.strip().lower() not in ("todos", "todas", "all"):
        lider_norm = lider.strip().lower()
        alertas_alcance = [
            a for a in alertas_todas
            if a.get("lt_asignado") and (
                lider_norm == a.get("lt_asignado").strip().lower() or
                lider_norm in a.get("lt_asignado").strip().lower()
            )
        ]
    else:
        alertas_alcance = alertas_todas

    # 4. Cálculo de Métricas y Resumen Global del Alcance
    criticas_count = sum(1 for a in alertas_alcance if a["severidad"] == "CRITICAL")
    warn_count = sum(1 for a in alertas_alcance if a["severidad"] == "WARNING")
    tickets_crit = sum(1 for a in alertas_alcance if a["tipo"] == "ticket" and a["severidad"] == "CRITICAL")
    tickets_warn = sum(1 for a in alertas_alcance if a["tipo"] == "ticket" and a["severidad"] == "WARNING")
    solots_venc = sum(1 for a in alertas_alcance if a["tipo"] == "solot" and a["severidad"] == "CRITICAL")
    solots_prox = sum(1 for a in alertas_alcance if a["tipo"] == "solot" and a["severidad"] == "WARNING" and ("Próxima" in a.get("detalle_sla", "") or "Vence" in a.get("detalle_sla", "")))
    solots_sin_comp = sum(1 for a in alertas_alcance if a["tipo"] == "solot" and a["severidad"] == "WARNING" and "Sin compromiso" in a.get("detalle_sla", ""))

    # Proyectos Críticos: Proyectos con >= 2 desviaciones críticas acumuladas
    crit_by_proj = {}
    for a in alertas_alcance:
        if a.get("severidad") == "CRITICAL" and a.get("proyecto_id"):
            crit_by_proj[a["proyecto_id"]] = crit_by_proj.get(a["proyecto_id"], 0) + 1
    proyectos_criticos = sum(1 for count in crit_by_proj.values() if count >= 2)

    # Agrupación por proyecto: alcance completo (post-filtro de líder), independiente de
    # severidad, tipo y límite. Solo alertas con proyecto_id.
    sev_order = {"CRITICAL": 1, "WARNING": 2, "INFO": 3}
    alertas_canonicas = sorted(
        alertas_alcance,
        key=lambda a: (
            sev_order.get(a.get("severidad"), 99),
            -int(a.get("dias_fuera_sla") or 0),
            str(a.get("id"))
        )
    )
    grupos_proy = {}
    alertas_sin_proyecto = 0
    for a in alertas_canonicas:
        pid = a.get("proyecto_id")
        if not pid:
            alertas_sin_proyecto += 1
            continue
        g = grupos_proy.get(pid)
        if g is None:
            g = grupos_proy[pid] = {
                "proyecto_id": pid,
                "numero_proyecto": None,
                "cliente": None,
                "lt_asignado": None,
                "severidad": a.get("severidad"),
                "total_alertas": 0,
                "criticas": 0,
                "advertencias": 0,
                "solots": 0,
                "tickets": 0,
                "max_dias_fuera_sla": 0,
                "alertas": []
            }
        for campo in ("numero_proyecto", "cliente", "lt_asignado"):
            if not g[campo] and a.get(campo):
                g[campo] = a.get(campo)
        g["total_alertas"] += 1
        if a.get("severidad") == "CRITICAL":
            g["criticas"] += 1
        elif a.get("severidad") == "WARNING":
            g["advertencias"] += 1
        if a.get("tipo") == "solot":
            g["solots"] += 1
        elif a.get("tipo") == "ticket":
            g["tickets"] += 1
        g["max_dias_fuera_sla"] = max(g["max_dias_fuera_sla"], int(a.get("dias_fuera_sla") or 0))
        if len(g["alertas"]) < 5:
            g["alertas"].append(a)

    def _clave_proyecto(g):
        pid = g["proyecto_id"]
        return (
            sev_order.get(g["severidad"], 99),
            -g["criticas"],
            -g["max_dias_fuera_sla"],
            (0, pid, "") if isinstance(pid, int) else (1, 0, str(pid))
        )

    proyectos = sorted(grupos_proy.values(), key=_clave_proyecto)

    resumen = {
        "total_alertas": len(alertas_alcance),
        "criticas": criticas_count,
        "advertencias": warn_count,
        "tickets_sla_criticos": tickets_crit,
        "tickets_sla_advertencia": tickets_warn,
        "solots_vencidas": solots_venc,
        "solots_proximas_vencer": solots_prox,
        "solots_sin_compromiso": solots_sin_comp,
        "proyectos_criticos": proyectos_criticos,
        "proyectos_con_alertas": len(proyectos),
        "proyectos_alerta_criticos": sum(1 for g in proyectos if g["severidad"] == "CRITICAL"),
        "proyectos_alerta_advertencia": sum(1 for g in proyectos if g["severidad"] == "WARNING"),
        "alertas_sin_proyecto": alertas_sin_proyecto
    }

    # 5. Filtrar por Severidad si se solicitó
    alertas_filtradas = alertas_alcance
    if severidad and severidad.strip().lower() not in ("todas", "todos", "all"):
        s_norm = severidad.strip().lower()
        if s_norm in ("critica", "critical", "criticas"):
            alertas_filtradas = [a for a in alertas_filtradas if a["severidad"] == "CRITICAL"]
        elif s_norm in ("advertencia", "warning", "advertencias"):
            alertas_filtradas = [a for a in alertas_filtradas if a["severidad"] == "WARNING"]
        elif s_norm in ("info", "informativa", "informativas"):
            alertas_filtradas = [a for a in alertas_filtradas if a["severidad"] == "INFO"]

    # 6. Filtrar por Tipo si se solicitó
    if tipo and tipo.strip().lower() not in ("todos", "todas", "all"):
        t_norm = tipo.strip().lower()
        if t_norm in ("ticket", "tickets"):
            alertas_filtradas = [a for a in alertas_filtradas if a["tipo"] == "ticket"]
        elif t_norm in ("solot", "solots"):
            alertas_filtradas = [a for a in alertas_filtradas if a["tipo"] == "solot"]
        elif t_norm in ("proyecto", "proyectos"):
            alertas_filtradas = [a for a in alertas_filtradas if a["tipo"] == "proyecto"]

    # 7. Ordenamiento Canónico:
    # 1º Severidad: CRITICAL (1) > WARNING (2) > INFO (3)
    # 2º Días fuera de SLA descendente
    # 3º ID descendente
    alertas_filtradas.sort(
        key=lambda a: (
            sev_order.get(a.get("severidad"), 99),
            -int(a.get("dias_fuera_sla") or 0),
            str(a.get("id"))
        )
    )

    # 8. Limitar cantidad devuelta en lista detallada
    if limite and limite > 0:
        alertas_result = alertas_filtradas[:limite]
    else:
        alertas_result = alertas_filtradas

    # 9. Minuta de Escalamiento
    minuta = generar_minuta_escalamiento_sla(resumen, alertas_alcance)

    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "filtros_aplicados": {
            "lider": lider,
            "severidad": severidad or "todas",
            "tipo": tipo or "todos"
        },
        "resumen": resumen,
        "alertas": alertas_result,
        "proyectos": proyectos,
        "minuta_escalamiento": minuta
    }


def get_alertas_tempranas_sla(lider: str = None, severidad: str = "todas", tipo: str = "todos", limite: int = 100) -> dict:
    """
    Punto de entrada principal para el Centro de Alertas Tempranas SLA.
    Ejecuta las consultas en la base de datos MSSQL con NOLOCK y procesa las desviaciones.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # 1. Consulta optimizada de Tickets HPSM en registrosRF_SD_SM
            sql_tickets = f"""
                SELECT 
                    sd.CC_INCIDENT_ID,
                    sd.RF_ID,
                    sd.STATUS,
                    sd.SUBMIT_DATE,
                    sd.BRIEF_DESCRIPTION,
                    sd.ASSIGNED_GROUP,
                    sd.ASSIGNED_TO,
                    sd.ID_Proyecto,
                    sd.Numero_Proyecto_Limpio,
                    p.ID AS p_id,
                    p.Numero_Proyecto AS p_numero,
                    p.Cliente AS p_cliente,
                    p.LT_Asignado AS p_lider,
                    p.Estado AS p_estado
                FROM dbo.registrosRF_SD_SM sd WITH (NOLOCK)
                OUTER APPLY (
                    SELECT TOP 1 p.ID, p.Numero_Proyecto, p.Cliente, p.LT_Asignado, p.Estado, p.Tipo_Servicio
                    FROM dbo.Proyectos p WITH (NOLOCK)
                    WHERE (sd.ID_Proyecto = p.ID OR (sd.Numero_Proyecto_Limpio IS NOT NULL AND sd.Numero_Proyecto_Limpio {_SQL_P_NUMERO_LIMPIO_IN}))
                      AND (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')
                    ORDER BY CASE WHEN p.Estado NOT IN ('Cerrado', 'Atendido') THEN 0 ELSE 1 END, p.ID DESC
                ) p
                WHERE sd.STATUS NOT IN ('Cerrado', 'Resuelto', 'Closed', 'Resolved')
                  AND TRY_CAST(sd.SUBMIT_DATE AS DATETIME2) IS NOT NULL
                  AND DATEDIFF(day, TRY_CAST(sd.SUBMIT_DATE AS DATETIME2), GETDATE()) > 7
                  AND (p.ID IS NULL OR p.Estado NOT IN ('Cerrado', 'Atendido'))
            """
            params_t = []
            if lider and lider.strip() and lider.strip().lower() not in ("todos", "todas", "all"):
                sql_tickets += " AND p.LT_Asignado IS NOT NULL AND LOWER(LTRIM(RTRIM(p.LT_Asignado))) = LOWER(LTRIM(RTRIM(%s)))"
                params_t.append(lider.strip())

            cur.execute(sql_tickets, tuple(params_t))
            raw_tickets = cur.fetchall()

            # 2. Consulta optimizada de Solots SGA en CT_BACKLOG_OPERACIONES2
            sql_solots = f"""
                SELECT 
                    b.ID_OTP,
                    b.DESCR_OTP,
                    b.ESTADO_OTP,
                    b.FECHA_COMPROMETIDA,
                    b.FECHA_INSERT,
                    b.ASIGNADO_OTP,
                    b.GRUPO_ASIGNADO_OTP,
                    b.ID_Proyecto,
                    b.Numero_Proyecto_Limpio,
                    p.ID AS p_id,
                    p.Numero_Proyecto AS p_numero,
                    p.Cliente AS p_cliente,
                    p.LT_Asignado AS p_lider,
                    p.Estado AS p_estado
                FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK)
                OUTER APPLY (
                    SELECT TOP 1 p.ID, p.Numero_Proyecto, p.Cliente, p.LT_Asignado, p.Estado, p.Tipo_Servicio
                    FROM dbo.Proyectos p WITH (NOLOCK)
                    WHERE (b.ID_Proyecto = p.ID OR (b.Numero_Proyecto_Limpio IS NOT NULL AND b.Numero_Proyecto_Limpio {_SQL_P_NUMERO_LIMPIO_IN}))
                      AND (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')
                    ORDER BY CASE WHEN p.Estado NOT IN ('Cerrado', 'Atendido') THEN 0 ELSE 1 END, p.ID DESC
                ) p
                WHERE b.ESTADO_OTP NOT IN ('Cerrada', '5- Ejecutada', '5- Ejecutada Tareas Pendientes', 'Abortado', 'En Aborcion', 'Eliminada', 'Aprobado')
                  AND (
                    (b.FECHA_COMPROMETIDA IS NOT NULL AND b.FECHA_COMPROMETIDA <= DATEADD(day, 2, CAST(GETDATE() AS DATE)))
                    OR
                    (b.FECHA_COMPROMETIDA IS NULL AND DATEDIFF(day, b.FECHA_INSERT, GETDATE()) > 10)
                  )
                  AND (p.ID IS NOT NULL OR b.ID_Proyecto IS NOT NULL)
                  AND (p.ID IS NULL OR p.Estado NOT IN ('Cerrado', 'Atendido'))
            """
            params_s = []
            if lider and lider.strip() and lider.strip().lower() not in ("todos", "todas", "all"):
                sql_solots += " AND p.LT_Asignado IS NOT NULL AND LOWER(LTRIM(RTRIM(p.LT_Asignado))) = LOWER(LTRIM(RTRIM(%s)))"
                params_s.append(lider.strip())

            cur.execute(sql_solots, tuple(params_s))
            raw_solots = cur.fetchall()

            return procesar_alertas_sla(
                raw_tickets=raw_tickets,
                raw_solots=raw_solots,
                lider=lider,
                severidad=severidad,
                tipo=tipo,
                limite=limite
            )
    finally:
        conn.close()

# Alias canónico
get_alertas_sla = get_alertas_tempranas_sla



