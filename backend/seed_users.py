import os
import zipfile
import unicodedata
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional

from .config import DB_CONFIG, BASE_DIR
from .db import init_auth_tables, get_db_connection

CANONICAL_LIDERES = {
    "Alejandro Aguilar": "Alejandro Aguilar",
    "Erwin Sandoval": "Erwin Sandoval",
    "Juan Barrera": "Juan Barrera",
    "Samuel Paredes": "Samuel Paredes",
    "Solange Ortiz": "Solange Ortiz"
}

# Usuarios iniciales canónicos con formato oficial del Portal de Acceso (nombre.apellido)
USERS_CANONICAL_SEED = [
    ("Alejandro Aguilar", "ADMIN", "alejandro.aguilar", "Alejandro Aguilar"),
    ("Pablo Castillo", "ADMIN", "pablo.castillo", None),
    ("Erwin Sandoval", "LTI", "erwin.sandoval", "Erwin Sandoval"),
    ("Juan Barrera", "LTI", "juan.barrera", "Juan Barrera"),
    ("Samuel Paredes", "LTI", "samuel.paredes", "Samuel Paredes"),
    ("Solange Ortiz", "LTI", "solange.ortiz", "Solange Ortiz"),
]

def normalize_ascii(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFKD', str(text))
    return ''.join([c for c in nfkd if not unicodedata.combining(c)]).strip()

def read_users_from_excel(filepath: str) -> List[Dict[str, str]]:
    """Lee registros del archivo Excel csv/Listado_Permisos_Usuarios.xlsx sin dependencias pesadas."""
    if not os.path.exists(filepath):
        return []
    try:
        with zipfile.ZipFile(filepath) as z:
            shared_strings = []
            if 'xl/sharedStrings.xml' in z.namelist():
                tree = ET.fromstring(z.read('xl/sharedStrings.xml'))
                for elem in tree.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si'):
                    shared_strings.append(''.join(elem.itertext()))

            sheet_tree = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            rows = []
            for row_elem in sheet_tree.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row'):
                row_vals = []
                for c in row_elem.findall('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c'):
                    t = c.get('t')
                    v = c.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
                    val = v.text if v is not None else ''
                    if t == 's' and val != '':
                        val = shared_strings[int(val)]
                    row_vals.append(val)
                rows.append(row_vals)

            users = []
            for r in rows:
                if len(r) >= 2:
                    nombre = r[0].strip()
                    rol = r[1].strip().upper()
                    if rol in ('PM', 'LTI', 'ADMIN') and nombre:
                        users.append({"nombre": nombre, "rol": rol})
            return users
    except Exception as e:
        print(f"[SEED] Aviso al leer excel: {e}")
        return []

def seed_default_users():
    """Inicializa y sincroniza idempotentemente los usuarios canónicos en dbo.App_Usuarios."""
    init_auth_tables()
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            inserted_count = 0
            updated_count = 0

            for nombre, rol, username, lt_asignado in USERS_CANONICAL_SEED:
                uname = username.strip().lower()
                cursor.execute("SELECT id, username, rol, lt_asignado FROM dbo.App_Usuarios WHERE LOWER(username) = %s", (uname,))
                existing = cursor.fetchone()

                if not existing:
                    cursor.execute("""
                        INSERT INTO dbo.App_Usuarios (username, nombre_completo, lt_asignado, rol, activo, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, 1, GETDATE(), GETDATE())
                    """, (uname, nombre, lt_asignado, rol))
                    inserted_count += 1
                else:
                    cursor.execute("""
                        UPDATE dbo.App_Usuarios
                        SET nombre_completo = %s,
                            rol = %s,
                            lt_asignado = %s,
                            activo = 1,
                            updated_at = GETDATE()
                        WHERE LOWER(username) = %s
                    """, (nombre, rol, lt_asignado, uname))
                    updated_count += 1

            # NOTA: Se eliminó definitivamente la sentencia destructiva DELETE FROM dbo.App_Usuarios
            # para no alterar cuentas provistas vía JIT ni otros usuarios existentes.

            conn.commit()
            print(f"[SEED] Sincronización de usuarios completada: {inserted_count} insertados, {updated_count} actualizados.")
    finally:
        conn.close()

if __name__ == '__main__':
    seed_default_users()
