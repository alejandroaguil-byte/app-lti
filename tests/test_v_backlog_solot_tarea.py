"""
==============================================================================
SUITE DE PRUEBAS AUTOMATIZADAS DE QA: V_BACKLOG_SOLOT_TAREA
==============================================================================
Especificación Técnica: SPECS-LTI-ETL-009 (SPECS_REPLICACION_V_BACKLOG_SOLOT_TAREA.md)
Módulo: Replicación y Enriquecimiento de Datos ETL — Vista SGA V_BACKLOG_SOLOT_TAREA a MSSQL Sharepoint_Proyectos
Objetivo:
  Certificar al 100% (0 fallos) la disponibilidad, integridad estructural,
  enriquecimiento analítico, filtro temporal, índices de alto rendimiento e
  idempotencia del proceso de replicación de dbo.V_BACKLOG_SOLOT_TAREA en la base
  de datos de producción 'Sharepoint_Proyectos'.

Matriz de Cobertura de Casos de Prueba (TC-ETL-001 a TC-ETL-014):
  - TC-ETL-001: Existencia de la tabla física 'dbo.V_BACKLOG_SOLOT_TAREA' (U).
  - TC-ETL-002: Verificación de las 34 columnas exactas en el diccionario de datos.
  - TC-ETL-003: Verificación de los tipos de datos y nulabilidad de las 34 columnas.
  - TC-ETL-004: Existencia de los 3 índices nonclustered de aceleración.
  - TC-ETL-005: Verificación de estructura y predicados de filtro de los 3 índices.
  - TC-ETL-006: Conteo exacto de registros en producción (213.040 registros vigentes).
  - TC-ETL-007: Verificación del filtro temporal estricto (0 registros < 2025).
  - TC-ETL-008: Enriquecimiento con dbo.Proyectos (>= 16.000 registros con ID_Proyecto).
  - TC-ETL-009: Integridad referencial lógica (100% de ID_Proyecto existen en dbo.Proyectos).
  - TC-ETL-010: Formato y normalización de Numero_Proyecto_Limpio (sin ceros, 6-10 dígitos).
  - TC-ETL-011: Coherencia determinista entre NRO_PROYECTO y Numero_Proyecto_Limpio.
  - TC-ETL-012: Pruebas unitarias de extraer_numero_proyecto_limpio (casos válidos y bordes).
  - TC-ETL-013: Idempotencia de la función asegurar_tabla_backlog_solot_tarea_destino.
  - TC-ETL-014: Verificación matemática de seguridad del límite TDS (chunk_size=50 <= 2.100 params).
  - TC-ETL-015: Inmutabilidad estricta de la base de código de App LTI (backend/ y frontend/).
==============================================================================
"""

import os
import re
import sys
import subprocess
import pytest
from backend.db import get_db_connection

# Inclusión de ruta para importar módulos del pipeline ETL
ETL_DIR = "/home/bobbasystem/Desarrollos/Carga Data SM"
if ETL_DIR not in sys.path:
    sys.path.append(ETL_DIR)

from cargar_backlog_solot_tarea_inicial import (
    extraer_numero_proyecto_limpio,
    asegurar_tabla_backlog_solot_tarea_destino,
)

# ------------------------------------------------------------------------------
# CONSTANTES DE ESPECIFICACIÓN TÉCNICA (SPECS-LTI-ETL-009)
# ------------------------------------------------------------------------------
TABLA_DESTINO = "dbo.V_BACKLOG_SOLOT_TAREA"
NOMBRE_TABLA_RAW = "V_BACKLOG_SOLOT_TAREA"
CANTIDAD_COLUMNAS_ESPERADAS = 34
REGISTROS_ESPERADOS_PRODUCCION = 213040
MINIMO_REGISTROS_ENRIQUECIDOS = 16000

COLUMNAS_ESQUEMA_ESPERADO = {
    # 32 Columnas replicadas desde SGA (blixter_prod)
    "NRO_PROYECTO": {"tipo": "varchar", "max_len": 100},
    "CLI_CLIENTE": {"tipo": "varchar", "max_len": 150},
    "PRO_ING_PROYECTO": {"tipo": "varchar", "max_len": 100},
    "INICIO_PROY": {"tipo": "datetime2", "max_len": None},
    "FECHA_COMPROMETIDA_SOLOT": {"tipo": "datetime2", "max_len": None},
    "SOLOT_ID": {"tipo": "bigint", "max_len": None},
    "ESTADO_OTP": {"tipo": "varchar", "max_len": 100},
    "TIPO_SOLOT": {"tipo": "varchar", "max_len": 200},
    "TAREA_ID": {"tipo": "bigint", "max_len": None},
    "TAREA_TIPO": {"tipo": "varchar", "max_len": 100},
    "TAREA_AREA_RESPONSABLE": {"tipo": "varchar", "max_len": 100},
    "TAREA_USUARIO_RESPONSABLE": {"tipo": "varchar", "max_len": 100},
    "TAREA_FECHA_INICIO": {"tipo": "datetime2", "max_len": None},
    "TAREA_FECHA_COMPROMISO": {"tipo": "datetime2", "max_len": None},
    "TAREA_ESTADO": {"tipo": "varchar", "max_len": 30},
    "FACTOR": {"tipo": "varchar", "max_len": 1000},
    "FECHA_ACTUAL": {"tipo": "datetime2", "max_len": None},
    "DIAS_PROVISION_TAREA": {"tipo": "int", "max_len": None},
    "DIAS_COMPROMISO_TAREA": {"tipo": "int", "max_len": None},
    "FEC_INICIO": {"tipo": "datetime2", "max_len": None},
    "FEC_INICIO_SYS": {"tipo": "datetime2", "max_len": None},
    "FEC_REALIZACION": {"tipo": "datetime2", "max_len": None},
    "FEC_FIN_SYS": {"tipo": "datetime2", "max_len": None},
    "USUARIO_CIERRE_SIS": {"tipo": "varchar", "max_len": 1000},
    "USU_EJECUTOR_TAREA": {"tipo": "varchar", "max_len": 200},
    "ASIGNADO_OTP": {"tipo": "varchar", "max_len": 200},
    "OBSERVACION": {"tipo": "varchar", "max_len": 8000},
    "USUARIO_MODIFICO": {"tipo": "varchar", "max_len": 1000},
    "DIRECCION": {"tipo": "varchar", "max_len": 1000},
    "DISTRITO": {"tipo": "varchar", "max_len": 1000},
    "VALORTXT": {"tipo": "varchar", "max_len": -1},  # varchar(max) se representa con -1
    "id": {"tipo": "int", "max_len": None},
    # 2 Columnas de enriquecimiento analítico del ecosistema LTI
    "ID_Proyecto": {"tipo": "numeric", "max_len": None},
    "Numero_Proyecto_Limpio": {"tipo": "varchar", "max_len": 50},
}

INDICES_ESPERADOS = [
    "IX_V_BACKLOG_SOLOT_TAREA_ID_Proyecto",
    "IX_V_BACKLOG_SOLOT_TAREA_NumLimpio",
    "IX_V_BACKLOG_SOLOT_TAREA_SOLOT_TAREA",
]


# ==============================================================================
# FIXTURES
# ==============================================================================
@pytest.fixture(scope="module")
def db_conn():
    """Fixture de conexión a la base de datos Sharepoint_Proyectos."""
    conn = get_db_connection()
    yield conn
    conn.close()


# ==============================================================================
# 1. PRUEBAS DE ESTRUCTURA DDL Y METADATOS (TC-ETL-001 A TC-ETL-003)
# ==============================================================================
def test_tc_etl_001_tabla_fisica_v_backlog_solot_tarea_existe(db_conn):
    """TC-ETL-001: Valida que la tabla física 'dbo.V_BACKLOG_SOLOT_TAREA' existe en la BD."""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT type_desc 
            FROM sys.objects 
            WHERE object_id = OBJECT_ID('dbo.V_BACKLOG_SOLOT_TAREA')
        """)
        row = cur.fetchone()
        assert row is not None, "La tabla 'dbo.V_BACKLOG_SOLOT_TAREA' no existe en la BD destino."
        assert row['type_desc'] == "USER_TABLE", f"Se esperaba USER_TABLE pero se encontró {row['type_desc']}."


def test_tc_etl_002_total_columnas_exactas_34(db_conn):
    """TC-ETL-002: Valida que la tabla cuente con exactamente 34 columnas."""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) AS total_cols 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'V_BACKLOG_SOLOT_TAREA'
        """)
        row = cur.fetchone()
        assert row['total_cols'] == CANTIDAD_COLUMNAS_ESPERADAS, (
            f"Se esperaban {CANTIDAD_COLUMNAS_ESPERADAS} columnas, pero se encontraron {row['total_cols']}."
        )


def test_tc_etl_003_verificacion_tipos_datos_y_columnas(db_conn):
    """TC-ETL-003: Valida que cada una de las 34 columnas tenga el tipo de dato y longitud definidos en SPECS."""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'V_BACKLOG_SOLOT_TAREA'
        """)
        cols_db = {r['COLUMN_NAME']: r for r in cur.fetchall()}

        # 1. Comprobar que todas las columnas esperadas existan en la base de datos
        for col_name, spec in COLUMNAS_ESQUEMA_ESPERADO.items():
            assert col_name in cols_db, f"Columna requerida '{col_name}' no existe en la tabla destino."
            db_info = cols_db[col_name]
            
            # Validar tipo de dato
            assert db_info['DATA_TYPE'].lower() == spec['tipo'].lower(), (
                f"Columna '{col_name}': tipo esperado {spec['tipo']}, encontrado {db_info['DATA_TYPE']}."
            )
            
            # Validar longitud máxima si aplica
            if spec['max_len'] is not None:
                assert db_info['CHARACTER_MAXIMUM_LENGTH'] == spec['max_len'], (
                    f"Columna '{col_name}': longitud esperada {spec['max_len']}, "
                    f"encontrada {db_info['CHARACTER_MAXIMUM_LENGTH']}."
                )

        # 2. Comprobar que no existan columnas adicionales no especificadas
        assert len(cols_db) == len(COLUMNAS_ESQUEMA_ESPERADO), (
            f"Discrepancia en cantidad de columnas: BD={len(cols_db)} vs Esperado={len(COLUMNAS_ESQUEMA_ESPERADO)}"
        )


# ==============================================================================
# 2. PRUEBAS DE ÍNDICES DE ALTO RENDIMIENTO (TC-ETL-004 Y TC-ETL-005)
# ==============================================================================
def test_tc_etl_004_indices_requeridos_existen(db_conn):
    """TC-ETL-004: Valida la presencia de los 3 índices nonclustered en la tabla."""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT name 
            FROM sys.indexes 
            WHERE object_id = OBJECT_ID('dbo.V_BACKLOG_SOLOT_TAREA') 
              AND name IN (
                'IX_V_BACKLOG_SOLOT_TAREA_ID_Proyecto',
                'IX_V_BACKLOG_SOLOT_TAREA_NumLimpio',
                'IX_V_BACKLOG_SOLOT_TAREA_SOLOT_TAREA'
              )
        """)
        indices_existentes = {r['name'] for r in cur.fetchall()}
        for idx in INDICES_ESPERADOS:
            assert idx in indices_existentes, f"El índice requerido '{idx}' no existe en dbo.V_BACKLOG_SOLOT_TAREA."


def test_tc_etl_005_propiedades_y_filtros_de_indices(db_conn):
    """TC-ETL-005: Valida la estructura, ordinales de clave y predicados de filtro de los 3 índices."""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT 
                i.name AS index_name,
                i.type_desc,
                i.has_filter,
                i.filter_definition,
                c.name AS column_name,
                ic.key_ordinal
            FROM sys.indexes i
            INNER JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
            INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
            WHERE i.object_id = OBJECT_ID('dbo.V_BACKLOG_SOLOT_TAREA')
            ORDER BY i.name, ic.key_ordinal
        """)
        rows = cur.fetchall()

        # Agrupar por nombre de índice
        idx_map = {}
        for r in rows:
            name = r['index_name']
            if name not in idx_map:
                idx_map[name] = {
                    'type_desc': r['type_desc'],
                    'has_filter': r['has_filter'],
                    'filter_definition': r['filter_definition'],
                    'columns': []
                }
            idx_map[name]['columns'].append((r['key_ordinal'], r['column_name']))

        # 1. IX_V_BACKLOG_SOLOT_TAREA_ID_Proyecto
        idx_id_proy = idx_map.get('IX_V_BACKLOG_SOLOT_TAREA_ID_Proyecto')
        assert idx_id_proy is not None, "Falta índice IX_V_BACKLOG_SOLOT_TAREA_ID_Proyecto."
        assert idx_id_proy['type_desc'] == 'NONCLUSTERED'
        assert idx_id_proy['has_filter'] is True
        assert 'ID_Proyecto' in idx_id_proy['filter_definition']
        assert idx_id_proy['columns'] == [(1, 'ID_Proyecto')]

        # 2. IX_V_BACKLOG_SOLOT_TAREA_NumLimpio
        idx_num_limpio = idx_map.get('IX_V_BACKLOG_SOLOT_TAREA_NumLimpio')
        assert idx_num_limpio is not None, "Falta índice IX_V_BACKLOG_SOLOT_TAREA_NumLimpio."
        assert idx_num_limpio['type_desc'] == 'NONCLUSTERED'
        assert idx_num_limpio['has_filter'] is True
        assert 'Numero_Proyecto_Limpio' in idx_num_limpio['filter_definition']
        assert idx_num_limpio['columns'] == [(1, 'Numero_Proyecto_Limpio')]

        # 3. IX_V_BACKLOG_SOLOT_TAREA_SOLOT_TAREA
        idx_solot_tarea = idx_map.get('IX_V_BACKLOG_SOLOT_TAREA_SOLOT_TAREA')
        assert idx_solot_tarea is not None, "Falta índice IX_V_BACKLOG_SOLOT_TAREA_SOLOT_TAREA."
        assert idx_solot_tarea['type_desc'] == 'NONCLUSTERED'
        assert idx_solot_tarea['has_filter'] is False
        assert idx_solot_tarea['columns'] == [(1, 'SOLOT_ID'), (2, 'TAREA_ID')]


# ==============================================================================
# 3. PRUEBAS DE VOLUMETRÍA Y FILTRO TEMPORAL (TC-ETL-006 Y TC-ETL-007)
# ==============================================================================
def test_tc_etl_006_conteo_exacto_registros_produccion(db_conn):
    """TC-ETL-006: Valida la paridad numérica exacta de registros en producción (213.040)."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM dbo.V_BACKLOG_SOLOT_TAREA")
        row = cur.fetchone()
        assert row['total'] == REGISTROS_ESPERADOS_PRODUCCION, (
            f"Conteo de registros no coincide: esperado={REGISTROS_ESPERADOS_PRODUCCION}, obtenido={row['total']}"
        )


def test_tc_etl_007_filtro_temporal_vigencia_2025(db_conn):
    """TC-ETL-007: Valida que existan exactamente 0 registros con fechas < 2025 en las columnas de control."""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) AS total_fuera_filtro 
            FROM dbo.V_BACKLOG_SOLOT_TAREA 
            WHERE (INICIO_PROY < '2025-01-01' OR INICIO_PROY IS NULL)
              AND (FEC_INICIO < '2025-01-01' OR FEC_INICIO IS NULL)
              AND (FEC_INICIO_SYS < '2025-01-01' OR FEC_INICIO_SYS IS NULL)
        """)
        row = cur.fetchone()
        assert row['total_fuera_filtro'] == 0, (
            f"Se encontraron {row['total_fuera_filtro']} registros que violan el filtro temporal vigencia 2025+."
        )


# ==============================================================================
# 4. PRUEBAS DE ENRIQUECIMIENTO Y CONSISTENCIA REFERENCIAL (TC-ETL-008 A TC-ETL-011)
# ==============================================================================
def test_tc_etl_008_enriquecimiento_minimo_16000_registros(db_conn):
    """TC-ETL-008: Valida que al menos 16.000 tareas estén vinculadas a proyectos de dbo.Proyectos."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total_enlazados FROM dbo.V_BACKLOG_SOLOT_TAREA WHERE ID_Proyecto IS NOT NULL")
        row = cur.fetchone()
        assert row['total_enlazados'] >= MINIMO_REGISTROS_ENRIQUECIDOS, (
            f"Tareas enlazadas ({row['total_enlazados']}) por debajo del mínimo esperado ({MINIMO_REGISTROS_ENRIQUECIDOS})."
        )


def test_tc_etl_009_integridad_referencial_con_dbo_proyectos(db_conn):
    """TC-ETL-009: Valida que el 100% de los ID_Proyecto existentes en V_BACKLOG_SOLOT_TAREA sean IDs válidos en dbo.Proyectos."""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) AS huerfanos
            FROM dbo.V_BACKLOG_SOLOT_TAREA t
            LEFT JOIN dbo.Proyectos p ON t.ID_Proyecto = p.ID
            WHERE t.ID_Proyecto IS NOT NULL 
              AND p.ID IS NULL
        """)
        row = cur.fetchone()
        assert row['huerfanos'] == 0, (
            f"Se encontraron {row['huerfanos']} registros con ID_Proyecto huérfanos sin correspondencia en dbo.Proyectos."
        )


def test_tc_etl_010_formato_numero_proyecto_limpio(db_conn):
    """TC-ETL-010: Valida que Numero_Proyecto_Limpio no contenga ceros a la izquierda y tenga longitud entre 6 y 10 dígitos."""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT TOP 5000 Numero_Proyecto_Limpio 
            FROM dbo.V_BACKLOG_SOLOT_TAREA 
            WHERE Numero_Proyecto_Limpio IS NOT NULL
        """)
        rows = cur.fetchall()
        assert len(rows) > 0, "No se obtuvieron registros con Numero_Proyecto_Limpio."
        
        regex_valido = re.compile(r'^[1-9]\d{5,9}$')
        for r in rows:
            num = r['Numero_Proyecto_Limpio']
            assert regex_valido.match(num), (
                f"Formato inválido de Numero_Proyecto_Limpio: '{num}' (debe iniciar con [1-9] y tener 6 a 10 dígitos)."
            )


def test_tc_etl_011_coherencia_entre_nro_proyecto_y_numero_proyecto_limpio(db_conn):
    """TC-ETL-011: Valida que Numero_Proyecto_Limpio corresponda fielmente a la extracción desde NRO_PROYECTO."""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT TOP 1000 NRO_PROYECTO, Numero_Proyecto_Limpio 
            FROM dbo.V_BACKLOG_SOLOT_TAREA 
            WHERE Numero_Proyecto_Limpio IS NOT NULL
        """)
        rows = cur.fetchall()
        assert len(rows) > 0, "No se obtuvieron registros de muestra para validar coherencia de NRO_PROYECTO."
        
        for r in rows:
            raw_nro = r['NRO_PROYECTO']
            limpio_guardado = r['Numero_Proyecto_Limpio']
            calculado = extraer_numero_proyecto_limpio(raw_nro)
            assert limpio_guardado == calculado, (
                f"Incoherencia de normalización para '{raw_nro}': guardado='{limpio_guardado}', calculado='{calculado}'"
            )


# ==============================================================================
# 5. PRUEBAS UNITARIAS DE FUNCIONES ETL E IDEMPOTENCIA (TC-ETL-012 A TC-ETL-014)
# ==============================================================================
@pytest.mark.parametrize("entrada, esperado", [
    ("0001595247", "1595247"),
    ("000000123456", "123456"),
    ("1595247", "1595247"),
    ("000123456789", "123456789"),
    ("Proyecto 0001595247 corporativo", "1595247"),
    ("PROY-0001595247", "1595247"),
    ("", None),
    (None, None),
    ("12345", None),            # 5 dígitos: menor al rango mínimo de 6
    ("123", None),              # 3 dígitos: menor al rango mínimo
    ("TEXTO_SIN_NUMEROS", None),
    ("PROY-ABCD-XYZ", None),
])
def test_tc_etl_012_extraer_numero_proyecto_limpio_unitario(entrada, esperado):
    """TC-ETL-012: Valida la lógica de extracción regex de número limpio en casos estándar y bordes."""
    resultado = extraer_numero_proyecto_limpio(entrada)
    assert resultado == esperado, f"Para '{entrada}': esperado '{esperado}', obtenido '{resultado}'"


def test_tc_etl_013_idempotencia_asegurar_tabla_destino(db_conn):
    """TC-ETL-013: Valida que asegurar_tabla_backlog_solot_tarea_destino sea 100% idempotente."""
    # Se utiliza cursor con as_dict=False tal como lo instancian los scripts del pipeline ETL
    with db_conn.cursor(as_dict=False) as cur:
        cols_dummy = []
        try:
            asegurar_tabla_backlog_solot_tarea_destino(cur, cols_dummy)
            db_conn.commit()
        except Exception as e:
            pytest.fail(f"La función asegurar_tabla_backlog_solot_tarea_destino falló al reejecutarse: {e}")

    # Comprobar con cursor estándar que los índices no se hayan duplicado ni roto
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) AS total_indices
            FROM sys.indexes 
            WHERE object_id = OBJECT_ID('dbo.V_BACKLOG_SOLOT_TAREA') 
              AND name IN (
                'IX_V_BACKLOG_SOLOT_TAREA_ID_Proyecto',
                'IX_V_BACKLOG_SOLOT_TAREA_NumLimpio',
                'IX_V_BACKLOG_SOLOT_TAREA_SOLOT_TAREA'
              )
        """)
        row = cur.fetchone()
        assert row['total_indices'] == 3, f"Se esperaba conservar exactamente 3 índices, pero hay {row['total_indices']}."


def test_tc_etl_014_seguridad_limite_parametros_tds():
    """TC-ETL-014: Valida matemáticamente que el batching de 50 filas por statement no supere el límite TDS (2.100)."""
    tds_limit = 2100
    num_columnas = CANTIDAD_COLUMNAS_ESPERADAS  # 34
    chunk_size = 50
    parametros_por_statement = chunk_size * num_columnas  # 1700

    assert parametros_por_statement < tds_limit, (
        f"El tamaño de lote ({parametros_por_statement}) excede o iguala el límite TDS de SQL Server ({tds_limit})."
    )
    margen_seguridad = tds_limit - parametros_por_statement
    assert margen_seguridad >= 400, (
        f"El margen de seguridad ({margen_seguridad} parámetros) es inferior al mínimo requerido de 400 parámetros."
    )


# ==============================================================================
# 6. PRUEBAS DE INMUTABILIDAD DE LA APLICACIÓN APP LTI (TC-ETL-015)
# ==============================================================================
def test_tc_etl_015_inmutabilidad_codigo_app_lti():
    """TC-ETL-015: Valida que ningún archivo de backend/ ni frontend/ haya sido modificado (regla de alcance cerrado)."""
    git_dir = "/home/bobbasystem/Desarrollos/app-lti"
    res = subprocess.run(
        ["git", "status", "--porcelain", "backend/", "frontend/"],
        cwd=git_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    assert res.returncode == 0, f"Error al ejecutar git status: {res.stderr}"
    modificaciones = res.stdout.strip()
    assert modificaciones == "", (
        f"Se detectaron modificaciones no permitidas en backend/ o frontend/:\n{modificaciones}"
    )
