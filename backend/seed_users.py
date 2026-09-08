import os
import zipfile
import unicodedata
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional

from .config import DB_CONFIG, BASE_DIR
from .auth import hash_password
from .db import init_auth_tables, get_db_connection

DEFAULT_PASSWORD = "Lti2026!"

CANONICAL_LIDERES = {
    "Alejandro Aguilar": "Alejandro Aguilar",
    "Erwin Sandoval": "Erwin Sandoval",
    "Juan Barrera": "Juan Barrera",
    "Samuel Paredes": "Samuel Paredes",
    "Solange Ortiz": "Solange Ortiz"
}

# Tabla de mapeo canónica oficial según SPECS-LTI-MOD-006
USERS_CANONICAL_SEED = [
    # 31 PMs
    ("Albornoz Pacheco Cesar Augusto", "PM", "calbornoz", None),
    ("Cardozo Garces Grace Alejandra", "PM", "gcardozo", None),
    ("Castillo Calderon Jaime Carmelo", "PM", "jcastillo", None),
    ("Castillo Meulén Maribel", "PM", "mcastillo", None),
    ("Catalan Maldonado Paola Constanza", "PM", "pcatalan", None),
    ("Cordova Concha Katherine Johana", "PM", "kcordova", None),
    ("Curutchet Villegas Paulina Fernanda", "PM", "pcurutchet", None),
    ("Díaz Urzúa Francisco Javier", "PM", "fdiaz", None),
    ("Fuentes Riquelme Marcelo Antonio", "PM", "mfuentes", None),
    ("Gonzalez Valenzuela Rodrigo Nolasco", "PM", "rgonzalez", None),
    ("Gutierrez Sánchez Adrián Omar", "PM", "agutierrez", None),
    ("Herrera Quiroz Fernando Adolfo", "PM", "fherrera", None),
    ("Inayado Figueroa Paulina Alejandra", "PM", "pinayado", None),
    ("Jose Gregorio Laboren Alvarez", "PM", "jlaboren", None),
    ("Lagos Alvarez Rolando Pedro", "PM", "rlagos", None),
    ("Lillo Bolivar Victoria Del Carmen", "PM", "vlillo", None),
    ("Loubies Cordova Karina", "PM", "kloubies", None),
    ("Perez Cerezo Oswaldo Vicente", "PM", "operez", None),
    ("Perez Ojeda Jessica Walleska", "PM", "jperez", None),
    ("Pincheira Medina Luis Eduardo", "PM", "lpincheira", None),
    ("Pozo Galvez Gustavo Andres", "PM", "gpozo", None),
    ("Reyes Sanhueza Elizabeth Valeska", "PM", "ereyes", None),
    ("Riquelme Tobar Rodolfo Andres", "PM", "rriquelme", None),
    ("Rodriguez Loyola Daniel Alexis", "PM", "drodriguez", None),
    ("Romero Aguilar Richard Josue", "PM", "rromero", None),
    ("Saavedra Sepulveda Jorge Antonio", "PM", "jsaavedra", None),
    ("San Juan Gonzalez Davis Alfredo", "PM", "dsanjuan", None),
    ("Takahashi Griffith Pablo Antonio", "PM", "ptakahashi", None),
    ("Torreblanca Villalon Renato", "PM", "rtorreblanca", None),
    ("Ulloa Alvarado Francisco Javier", "PM", "fulloa", None),
    ("Villar Mohor Pablo Andrés", "PM", "pvillar", None),
    # 2 ADMINs
    ("Aguilar Morales Alejandro Javier", "ADMIN", "aaguilar", "Alejandro Aguilar"),
    ("Castillo Campos Pablo Ignacio", "ADMIN", "pcastillo", None),
    # 4 LTIs
    ("Barrera Ramos Juan Francisco", "LTI", "jbarrera", "Juan Barrera"),
    ("Paredez Saez Samuel Jacob", "LTI", "sparedes", "Samuel Paredes"),
    ("Ortiz Virolde Solange Angélica", "LTI", "sortiz", "Solange Ortiz"),
    ("Sandoval Cadiz Erwin Patricio", "LTI", "esandoval", "Erwin Sandoval"),
    # Superadmin raíz
    ("Administrador del Sistema", "ADMIN", "admin", None),
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
    """Inicializa y sincroniza idempotentemente los 38 usuarios en dbo.App_Usuarios."""
    init_auth_tables()
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            hashed_default = hash_password(DEFAULT_PASSWORD)
            
            # Buscar usuarios del seed canónico
            inserted_count = 0
            updated_count = 0

            for nombre, rol, username, lt_asignado in USERS_CANONICAL_SEED:
                cursor.execute("SELECT id, username, rol, lt_asignado FROM dbo.App_Usuarios WHERE username = %s", (username,))
                existing = cursor.fetchone()
                
                if not existing:
                    cursor.execute("""
                        INSERT INTO dbo.App_Usuarios (username, password_hash, nombre_completo, lt_asignado, rol, activo, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, 1, GETDATE(), GETDATE())
                    """, (username, hashed_default, nombre, lt_asignado, rol))
                    inserted_count += 1
                else:
                    # Actualizar rol y lt_asignado si difieren (p. ej. migración de LIDER_TI a LTI/ADMIN)
                    cursor.execute("""
                        UPDATE dbo.App_Usuarios
                        SET nombre_completo = %s,
                            rol = %s,
                            lt_asignado = %s,
                            activo = 1,
                            updated_at = GETDATE()
                        WHERE username = %s
                    """, (nombre, rol, lt_asignado, username))
                    updated_count += 1

            # Eliminar cuentas obsoletas de semillas antiguas ('LIDER_TI') que no están en el listado oficial
            valid_usernames = [u[2] for u in USERS_CANONICAL_SEED]
            placeholders = ', '.join(['%s'] * len(valid_usernames))
            cursor.execute(f"DELETE FROM dbo.App_Usuarios WHERE username NOT IN ({placeholders})", tuple(valid_usernames))

            conn.commit()
            print(f"[SEED] Sincronización de usuarios completada: {inserted_count} insertados, {updated_count} actualizados.")
    finally:
        conn.close()

if __name__ == '__main__':
    seed_default_users()
