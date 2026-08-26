import pymssql
import datetime
from decimal import Decimal
from typing import List, Union, Optional
from .config import DB_CONFIG

import re

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
    return pymssql.connect(
        server=DB_CONFIG['Server'],
        port=int(DB_CONFIG['Port']),
        user=DB_CONFIG['User'],
        password=DB_CONFIG['Password'],
        database=DB_CONFIG['Database'],
        as_dict=True
    )

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

def init_auth_tables():
    """Ensures dbo.App_Usuarios table exists and has seed users."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'App_Usuarios')
            BEGIN
                CREATE TABLE dbo.App_Usuarios (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    username VARCHAR(100) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    nombre_completo VARCHAR(150) NOT NULL,
                    lt_asignado VARCHAR(150) NULL,
                    rol VARCHAR(50) DEFAULT 'LIDER_TI',
                    activo BIT DEFAULT 1,
                    created_at DATETIME DEFAULT GETDATE()
                );
            END
            """)
            conn.commit()
    finally:
        conn.close()

def get_user_by_username(username):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM dbo.App_Usuarios WHERE username = %s AND activo = 1", (username,))
            user = cursor.fetchone()
            return serialize_row(user)
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

def get_estados_list():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT Estado 
                FROM dbo.Proyectos 
                WHERE Estado IS NOT NULL 
                  AND LTRIM(RTRIM(Estado)) <> ''
                  AND (Tipo_Servicio IS NULL OR Tipo_Servicio <> 'Reunión')
                ORDER BY Estado ASC
            """)
            estados_sp = [r['Estado'] for r in cursor.fetchall()]

            cursor.execute("""
                SELECT DISTINCT ESTADO_OTP 
                FROM dbo.CT_BACKLOG_OPERACIONES2 
                WHERE ESTADO_OTP IS NOT NULL AND LTRIM(RTRIM(ESTADO_OTP)) <> ''
                ORDER BY ESTADO_OTP ASC
            """)
            estados_sga = [r['ESTADO_OTP'] for r in cursor.fetchall()]

            return {
                "estados_sharepoint": estados_sp,
                "estados_sga": estados_sga
            }
    finally:
        conn.close()

def get_proyectos(lt_filter=None, search=None, estado_sp=None, estado_sga=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                WITH SolotStats AS (
                    SELECT 
                        ID_Proyecto,
                        COUNT(1) AS total_solots
                    FROM dbo.CT_BACKLOG_OPERACIONES2
                    WHERE ID_Proyecto IS NOT NULL
                    GROUP BY ID_Proyecto
                ),
                TicketStats AS (
                    SELECT 
                        ID_Proyecto,
                        COUNT(1) AS total_tickets
                    FROM dbo.registrosRF_SD_SM
                    WHERE ID_Proyecto IS NOT NULL
                    GROUP BY ID_Proyecto
                ),
                RFCStats AS (
                    SELECT 
                        ID_Proyecto,
                        COUNT(1) AS total_rfcs
                    FROM dbo.registrosSM_RFC
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
                    FROM dbo.CT_BACKLOG_OPERACIONES2
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
                    FROM dbo.CT_BACKLOG_OPERACIONES2
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
                    FROM dbo.CT_BACKLOG_OPERACIONES2
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
                    COALESCE(
                        si_id.PRO_ING_PROYECTO, 
                        si_limp.PRO_ING_PROYECTO,
                        si_limp2.PRO_ING_PROYECTO,
                        si_otp.PRO_ING_PROYECTO, 
                        si_otp2.PRO_ING_PROYECTO
                    ) AS Solicitante
                FROM dbo.Proyectos p
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
                sql += " AND EXISTS (SELECT 1 FROM dbo.CT_BACKLOG_OPERACIONES2 b WHERE (b.ID_Proyecto = p.ID OR b.Numero_Proyecto_Limpio = p.Numero_Proyecto) AND b.ESTADO_OTP = %s)"
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
            return serialize_rows(rows)
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
            return serialize_row(row)
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
                FROM dbo.CT_BACKLOG_OPERACIONES2 b
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
                FROM dbo.registrosRF_SD_SM sd
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
                FROM dbo.registrosSM_RFC rfc
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
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Total Proyectos
            sql_proy = "SELECT COUNT(1) as total FROM dbo.Proyectos p WHERE (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')"
            params_proy = []
            if lt_filter == "__UNASSIGNED__":
                sql_proy += " AND (p.LT_Asignado IS NULL OR LTRIM(RTRIM(p.LT_Asignado)) = '' OR LOWER(LTRIM(RTRIM(p.LT_Asignado))) = 'sin asignar')"
            elif lt_filter:
                sql_proy += " AND p.LT_Asignado = %s"
                params_proy.append(lt_filter)
            cursor.execute(sql_proy, tuple(params_proy))
            total_proyectos = cursor.fetchone()['total']

            # 2. Proyectos En Curso (Estado = 'Generado')
            sql_en_curso = "SELECT COUNT(1) as total FROM dbo.Proyectos p WHERE p.Estado = 'Generado' AND (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')"
            params_ec = []
            if lt_filter == "__UNASSIGNED__":
                sql_en_curso += " AND (p.LT_Asignado IS NULL OR LTRIM(RTRIM(p.LT_Asignado)) = '' OR LOWER(LTRIM(RTRIM(p.LT_Asignado))) = 'sin asignar')"
            elif lt_filter:
                sql_en_curso += " AND p.LT_Asignado = %s"
                params_ec.append(lt_filter)
            cursor.execute(sql_en_curso, tuple(params_ec))
            proyectos_en_curso = cursor.fetchone()['total']

            # 3. Proyectos Atendidos (Estado = 'Atendido')
            sql_atendidos = "SELECT COUNT(1) as total FROM dbo.Proyectos p WHERE p.Estado = 'Atendido' AND (p.Tipo_Servicio IS NULL OR p.Tipo_Servicio <> 'Reunión')"
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
                FROM dbo.Proyectos p 
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
                FROM dbo.registrosRF_SD_SM sd
                INNER JOIN dbo.Proyectos p ON sd.ID_Proyecto = p.ID
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
                FROM dbo.registrosSM_RFC rfc
                INNER JOIN dbo.Proyectos p ON rfc.ID_Proyecto = p.ID
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

            return {
                'total_proyectos': total_proyectos,
                'proyectos_en_curso': proyectos_en_curso,
                'proyectos_atendidos': proyectos_atendidos,
                'pendientes_asignar': pendientes_asignar,
                'efectividad': efectividad,
                'total_tickets': total_tickets,
                'total_rfcs': total_rfcs
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
            conn.commit()

            # 5. Obtener y retornar el registro insertado
            cursor.execute("SELECT * FROM dbo.Proyectos WHERE ID = %s", (next_id,))
            created_row = cursor.fetchone()
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

            # 3. Retornar el registro actualizado enriquecido
            return {
                "success": True,
                "data": get_proyecto_by_id(proyecto_id)
            }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "error": "db_error", "message": str(e)}
    finally:
        conn.close()

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

