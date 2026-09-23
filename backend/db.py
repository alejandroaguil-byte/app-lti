import pymssql
import datetime
from decimal import Decimal
from typing import List, Union, Optional
import logging
from .config import DB_CONFIG

import re

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
    """Ensures dbo.App_Usuarios table exists with updated_at column and nullable password_hash."""
    conn = get_db_connection()
    try:
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
                IF EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'App_Usuarios' AND COLUMN_NAME = 'password_hash' AND IS_NULLABLE = 'NO')
                BEGIN
                    ALTER TABLE dbo.App_Usuarios ALTER COLUMN password_hash VARCHAR(255) NULL;
                END
            END
            """)
            conn.commit()
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
    default_rol: str = "PM"
) -> dict:
    """Busca por LOWER(username) y si no existe lo inserta con activo=1 y rol=default_rol (JIT Provisioning)."""
    if not username:
        return None
    uname = username.strip().lower()
    full_name = (nombre_completo.strip() if nombre_completo and str(nombre_completo).strip() else uname.replace(".", " ").title())

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
                SELECT id, username, nombre_completo, lt_asignado, rol, activo, created_at, updated_at
                FROM dbo.App_Usuarios
                WHERE LOWER(username) = %s
            """, (uname,))
            existing = cursor.fetchone()
            if existing:
                return serialize_row(existing)

            # Insertar nuevo usuario JIT
            cursor.execute("""
                INSERT INTO dbo.App_Usuarios (username, nombre_completo, lt_asignado, rol, activo, created_at, updated_at)
                VALUES (%s, %s, %s, %s, 1, GETDATE(), GETDATE())
            """, (
                uname,
                full_name,
                canonical_lt,
                (default_rol.strip().upper() if default_rol else "PM")
            ))
            cursor.execute("""
                SELECT id, username, nombre_completo, lt_asignado, rol, activo, created_at, updated_at
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
                SELECT id, username, nombre_completo, lt_asignado, rol, activo, created_at, updated_at
                FROM dbo.App_Usuarios
                WHERE 1=1
            """
            params = []
            if search and search.strip():
                term = f"%{search.strip()}%"
                sql += " AND (username LIKE %s OR nombre_completo LIKE %s OR ISNULL(lt_asignado, '') LIKE %s)"
                params.extend([term, term, term])

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
                SELECT id, username, nombre_completo, lt_asignado, rol, activo, created_at, updated_at
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
    activo: bool = True
) -> dict:
    """Actualiza datos de un usuario existente sin contraseñas."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM dbo.App_Usuarios WHERE id = %s", (user_id,))
            if not cursor.fetchone():
                return {"success": False, "error": "not_found", "message": f"Usuario ID {user_id} no encontrado"}

            cursor.execute("""
                UPDATE dbo.App_Usuarios
                SET nombre_completo = %s,
                    lt_asignado = %s,
                    rol = %s,
                    activo = %s,
                    updated_at = GETDATE()
                WHERE id = %s
            """, (
                nombre_completo.strip(),
                (lt_asignado.strip() if lt_asignado and str(lt_asignado).strip() else None),
                rol.strip().upper(),
                1 if activo else 0,
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
    "En revision",
    "Atendido"
]

def get_estados_list() -> dict:
    """
    Retorna el catálogo canónico oficial de estados de proyectos SharePoint (dbo.Proyectos)
    y la lista de estados dinámicos de solots SGA (dbo.CT_BACKLOG_OPERACIONES2).
    
    Para SharePoint, devuelve siempre los 3 estados oficiales del ciclo de vida:
    ['Generado', 'En revision', 'Atendido'], evitando dependencias frágiles de los
    registros transitorios existentes en la tabla.
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

def get_proyectos(lt_filter=None, search=None, estado_sp=None, estado_sga=None):
    if lt_filter in (None, '', '__ALL__'):
        lt_filter = None
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                WITH SolotStats AS (
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
                    FROM dbo.CT_BACKLOG_OPERACIONES2 WITH (NOLOCK)
                    WHERE ID_Proyecto IS NOT NULL
                    GROUP BY ID_Proyecto
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
                    FROM dbo.registrosRF_SD_SM WITH (NOLOCK)
                    WHERE ID_Proyecto IS NOT NULL
                    GROUP BY ID_Proyecto
                ),
                RFCStats AS (
                    SELECT 
                        ID_Proyecto,
                        COUNT(1) AS total_rfcs
                    FROM dbo.registrosSM_RFC WITH (NOLOCK)
                    WHERE ID_Proyecto IS NOT NULL
                    GROUP BY ID_Proyecto
                ),
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
                sql += " AND p.Estado = %s"
                params.append(estado_sp)

            if estado_sga:
                sql += " AND EXISTS (SELECT 1 FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK) WHERE (b.ID_Proyecto = p.ID OR b.Numero_Proyecto_Limpio = p.Numero_Proyecto) AND b.ESTADO_OTP = %s)"
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
            sql = """
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
                        WHERE (b.ID_Proyecto = p.ID OR b.Numero_Proyecto_Limpio = p.Numero_Proyecto) AND b.FECHA_INSERT IS NOT NULL
                    ) AS fecha_creacion_sga,
                    (
                        SELECT MIN(b.FECHA_COMPROMETIDA) 
                        FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK)
                        WHERE (b.ID_Proyecto = p.ID OR b.Numero_Proyecto_Limpio = p.Numero_Proyecto) AND b.FECHA_COMPROMETIDA IS NOT NULL
                    ) AS fecha_compromiso_sga,
                    (
                        SELECT MAX(b.FECHA_REALIZACION) 
                        FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK)
                        WHERE (b.ID_Proyecto = p.ID OR b.Numero_Proyecto_Limpio = p.Numero_Proyecto) AND b.FECHA_REALIZACION IS NOT NULL
                    ) AS fecha_cierre_sga,
                    (SELECT COUNT(1) FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK) WHERE b.ID_Proyecto = p.ID OR b.Numero_Proyecto_Limpio = p.Numero_Proyecto) AS total_solots,
                    (SELECT COUNT(1) FROM dbo.registrosRF_SD_SM sd WITH (NOLOCK) WHERE sd.ID_Proyecto = p.ID OR sd.Numero_Proyecto_Limpio = p.Numero_Proyecto) AS total_tickets,
                    (SELECT COUNT(1) FROM dbo.registrosSM_RFC rfc WITH (NOLOCK) WHERE rfc.ID_Proyecto = p.ID OR rfc.Numero_Proyecto_Limpio = p.Numero_Proyecto) AS total_rfcs,
                    (
                        SELECT SUM(CASE 
                            WHEN b.ESTADO_OTP NOT IN ('Cerrada', '5- Ejecutada', '5- Ejecutada Tareas Pendientes', 'Abortado', 'En Aborcion', 'Eliminada', 'Aprobado') 
                                 AND b.FECHA_COMPROMETIDA < CAST(GETDATE() AS DATE) THEN 1 
                            ELSE 0 
                        END)
                        FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK)
                        WHERE (b.ID_Proyecto = p.ID OR b.Numero_Proyecto_Limpio = p.Numero_Proyecto)
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
                        WHERE (b.ID_Proyecto = p.ID OR b.Numero_Proyecto_Limpio = p.Numero_Proyecto)
                          AND b.FECHA_COMPROMETIDA IS NOT NULL
                    ) AS solots_por_vencer,
                    (
                        SELECT SUM(CASE 
                            WHEN sd.STATUS NOT IN ('Cerrado', 'Resuelto') 
                                 AND DATEDIFF(day, TRY_CAST(sd.SUBMIT_DATE AS DATETIME2), GETDATE()) > 14 THEN 1 
                            ELSE 0 
                        END)
                        FROM dbo.registrosRF_SD_SM sd WITH (NOLOCK)
                        WHERE (sd.ID_Proyecto = p.ID OR sd.Numero_Proyecto_Limpio = p.Numero_Proyecto)
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
                        WHERE (sd.ID_Proyecto = p.ID OR sd.Numero_Proyecto_Limpio = p.Numero_Proyecto)
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

def get_solots_by_proyecto(proyecto_id, numero_proyecto=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
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
                    b.GRUPO_ASIGNADO_OTP
                FROM dbo.CT_BACKLOG_OPERACIONES2 b WITH (NOLOCK)
                WHERE b.ID_Proyecto = %s
            """
            params = [proyecto_id]
            if numero_proyecto:
                sql += " OR b.Numero_Proyecto_Limpio = %s"
                params.append(numero_proyecto)

            sql += " ORDER BY b.FECHA_INSERT DESC, b.ID_OTP DESC"
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            return serialize_rows(rows)
    finally:
        conn.close()

def get_tickets_by_proyecto(proyecto_id, numero_proyecto=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
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
                    sd.SUBCATEGORY
                FROM dbo.registrosRF_SD_SM sd WITH (NOLOCK)
                WHERE sd.ID_Proyecto = %s
            """
            params = [proyecto_id]
            if numero_proyecto:
                sql += " OR sd.Numero_Proyecto_Limpio = %s"
                params.append(numero_proyecto)

            sql += " ORDER BY sd.SUBMIT_DATE DESC, sd.CC_INCIDENT_ID DESC"
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            return serialize_rows(rows)
    finally:
        conn.close()

def get_rfcs_by_proyecto(proyecto_id, numero_proyecto=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
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
                    rfc.ORIG_DATE_ENTERED
                FROM dbo.registrosSM_RFC rfc WITH (NOLOCK)
                WHERE rfc.ID_Proyecto = %s
            """
            params = [proyecto_id]
            if numero_proyecto:
                sql += " OR rfc.Numero_Proyecto_Limpio = %s"
                params.append(numero_proyecto)

            sql += " ORDER BY rfc.ORIG_DATE_ENTERED DESC, rfc.NUMBER DESC"
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            return serialize_rows(rows)
    finally:
        conn.close()

def get_dashboard_kpis(lt_filter=None):
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

            # 2. Proyectos En Curso (Estado = 'Generado')
            sql_en_curso = "SELECT COUNT(1) as total FROM dbo.Proyectos p WITH (NOLOCK) WHERE p.Estado = 'Generado' AND (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')"
            params_ec = []
            if lt_filter == "__UNASSIGNED__":
                sql_en_curso += " AND (p.LT_Asignado IS NULL OR LTRIM(RTRIM(p.LT_Asignado)) = '' OR LOWER(LTRIM(RTRIM(p.LT_Asignado))) = 'sin asignar')"
            elif lt_filter:
                sql_en_curso += " AND p.LT_Asignado = %s"
                params_ec.append(lt_filter)
            cursor.execute(sql_en_curso, tuple(params_ec))
            proyectos_en_curso = cursor.fetchone()['total']

            # 3. Proyectos Atendidos (Estado = 'Atendido')
            sql_atendidos = "SELECT COUNT(1) as total FROM dbo.Proyectos p WITH (NOLOCK) WHERE p.Estado = 'Atendido' AND (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')"
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
            cursor.execute(sql_pendientes)
            pendientes_asignar = cursor.fetchone()['total']

            # 5. Efectividad
            efectividad = round((proyectos_atendidos / total_proyectos * 100), 1) if total_proyectos > 0 else 0.0

            # 6. Total Tickets
            sql_tickets = """
                SELECT COUNT(1) as total 
                FROM dbo.registrosRF_SD_SM sd WITH (NOLOCK)
                INNER JOIN dbo.Proyectos p WITH (NOLOCK) ON sd.ID_Proyecto = p.ID
                WHERE (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')
            """
            params_t = []
            if lt_filter == "__UNASSIGNED__":
                sql_tickets += " AND (p.LT_Asignado IS NULL OR LTRIM(RTRIM(p.LT_Asignado)) = '' OR LOWER(LTRIM(RTRIM(p.LT_Asignado))) = 'sin asignar')"
            elif lt_filter:
                sql_tickets += " AND p.LT_Asignado = %s"
                params_t.append(lt_filter)
            cursor.execute(sql_tickets, tuple(params_t))
            total_tickets = cursor.fetchone()['total']

            # 7. Total RFCs
            sql_rfcs = """
                SELECT COUNT(1) as total 
                FROM dbo.registrosSM_RFC rfc WITH (NOLOCK)
                INNER JOIN dbo.Proyectos p WITH (NOLOCK) ON rfc.ID_Proyecto = p.ID
                WHERE (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')
            """
            params_r = []
            if lt_filter == "__UNASSIGNED__":
                sql_rfcs += " AND (p.LT_Asignado IS NULL OR LTRIM(RTRIM(p.LT_Asignado)) = '' OR LOWER(LTRIM(RTRIM(p.LT_Asignado))) = 'sin asignar')"
            elif lt_filter:
                sql_rfcs += " AND p.LT_Asignado = %s"
                params_r.append(lt_filter)
            cursor.execute(sql_rfcs, tuple(params_r))
            total_rfcs = cursor.fetchone()['total']

            # 8. KPIs de Salud Operacional
            sql_salud_kpis = """
                WITH SolotStats AS (
                    SELECT 
                        ID_Proyecto, 
                        COUNT(1) AS total_solots,
                        SUM(CASE WHEN ESTADO_OTP NOT IN ('Cerrada', '5- Ejecutada', '5- Ejecutada Tareas Pendientes', 'Abortado', 'En Aborcion', 'Eliminada', 'Aprobado') 
                                 AND FECHA_COMPROMETIDA IS NOT NULL AND FECHA_COMPROMETIDA < CAST(GETDATE() AS DATE) THEN 1 ELSE 0 END) AS solots_vencidas,
                        SUM(CASE WHEN ESTADO_OTP NOT IN ('Cerrada', '5- Ejecutada', '5- Ejecutada Tareas Pendientes', 'Abortado', 'En Aborcion', 'Eliminada', 'Aprobado') 
                                 AND FECHA_COMPROMETIDA IS NOT NULL AND FECHA_COMPROMETIDA >= CAST(GETDATE() AS DATE) 
                                 AND FECHA_COMPROMETIDA <= DATEADD(day, 5, CAST(GETDATE() AS DATE)) THEN 1 ELSE 0 END) AS solots_por_vencer
                    FROM dbo.CT_BACKLOG_OPERACIONES2 WITH (NOLOCK) 
                    WHERE ID_Proyecto IS NOT NULL 
                    GROUP BY ID_Proyecto
                ),
                TicketStats AS (
                    SELECT 
                        ID_Proyecto, 
                        COUNT(1) AS total_tickets,
                        SUM(CASE WHEN STATUS NOT IN ('Cerrado', 'Resuelto') 
                                 AND SUBMIT_DATE IS NOT NULL
                                 AND TRY_CAST(SUBMIT_DATE AS DATETIME2) < DATEADD(day, -14, GETDATE()) THEN 1 ELSE 0 END) AS tickets_criticos,
                        SUM(CASE WHEN STATUS NOT IN ('Cerrado', 'Resuelto') 
                                 AND SUBMIT_DATE IS NOT NULL
                                 AND TRY_CAST(SUBMIT_DATE AS DATETIME2) >= DATEADD(day, -14, GETDATE())
                                 AND TRY_CAST(SUBMIT_DATE AS DATETIME2) < DATEADD(day, -7, GETDATE()) THEN 1 ELSE 0 END) AS tickets_atencion
                    FROM dbo.registrosRF_SD_SM WITH (NOLOCK) 
                    WHERE ID_Proyecto IS NOT NULL 
                    GROUP BY ID_Proyecto
                )
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
                'proyectos_atendidos': proyectos_atendidos,
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
    """Inserta una nueva solicitud en dbo.Proyectos forzando Estado='Generado' y Tipo_Servicio='Otros'."""
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

            # 4. Inserción en dbo.Proyectos forzando Estado = 'Generado' y Tipo_Servicio = 'Otros'
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
                'Generado',  # Inmutable: Siempre 'Generado'
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
                    "Estado": "Generado",
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
# EDICIÓN Y ELIMINACIÓN DE PROYECTOS (dbo.Proyectos)
# -----------------------------------------------------------------------------
def update_proyecto(
    proyecto_id: int,
    cliente: str,
    lt_asignado: Optional[str] = None,
    estado: str = "Generado",
    detalle: str = "",
    tipo_servicio: Optional[str] = "Otros",
    comentario: Optional[str] = None
) -> dict:
    """Actualiza los campos operativos y estado de un proyecto en dbo.Proyectos."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Verificar existencia del proyecto
            cursor.execute("SELECT ID FROM dbo.Proyectos WHERE ID = %s", (proyecto_id,))
            if not cursor.fetchone():
                return {"success": False, "error": "not_found", "message": f"Proyecto ID {proyecto_id} no encontrado"}

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
                (lt_asignado.strip()[:50] if lt_asignado and str(lt_asignado).strip() else None),
                estado.strip(),
                detalle.strip(),
                (tipo_servicio.strip()[:30] if tipo_servicio and str(tipo_servicio).strip() else "Otros"),
                (comentario.strip() if comentario and str(comentario).strip() else None),
                proyecto_id
            ))
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
        "data": updated_data
    }

def delete_proyecto(proyecto_id: int) -> dict:
    """Elimina físicamente un proyecto de dbo.Proyectos."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Verificar existencia y capturar datos antes de borrar
            cursor.execute("SELECT ID, Numero_Proyecto, Cliente FROM dbo.Proyectos WHERE ID = %s", (proyecto_id,))
            existing = cursor.fetchone()
            if not existing:
                return {"success": False, "error": "not_found", "message": f"Proyecto ID {proyecto_id} no encontrado"}

            # 2. Ejecutar DELETE
            cursor.execute("DELETE FROM dbo.Proyectos WHERE ID = %s", (proyecto_id,))
            deleted_count = cursor.rowcount
            conn.commit()

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


