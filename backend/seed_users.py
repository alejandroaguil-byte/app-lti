import pymssql
from .config import DB_CONFIG
from .auth import hash_password
from .db import init_auth_tables, get_db_connection

def seed_default_users():
    init_auth_tables()
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Check how many users exist
            cursor.execute("SELECT COUNT(1) as total FROM dbo.App_Usuarios")
            res = cursor.fetchone()
            if res and res['total'] > 0:
                print("[SEED] Ya existen usuarios en dbo.App_Usuarios.")
                return

            print("[SEED] Creando usuarios iniciales para Líderes TI y Administrador...")
            
            # Default password for initial setup: Lti2026!
            default_pass = "Lti2026!"
            hashed = hash_password(default_pass)

            # Get distinct Líderes TI from Proyectos table
            cursor.execute("""
                SELECT DISTINCT LT_Asignado 
                FROM dbo.Proyectos 
                WHERE LT_Asignado IS NOT NULL AND LTRIM(RTRIM(LT_Asignado)) <> ''
            """)
            lts = cursor.fetchall()

            users_to_insert = [
                # Admin account
                ('admin', hashed, 'Administrador del Sistema', None, 'ADMIN')
            ]

            for lt in lts:
                nombre = lt['LT_Asignado'].strip()
                parts = nombre.lower().split()
                if len(parts) >= 2:
                    username = parts[0][0] + parts[1]
                else:
                    username = parts[0]
                # Avoid duplicates
                if not any(u[0] == username for u in users_to_insert):
                    users_to_insert.append((username, hashed, nombre, nombre, 'LIDER_TI'))

            for u in users_to_insert:
                cursor.execute("""
                    INSERT INTO dbo.App_Usuarios (username, password_hash, nombre_completo, lt_asignado, rol)
                    VALUES (%s, %s, %s, %s, %s)
                """, u)

            conn.commit()
            print(f"[SEED] Se crearon {len(users_to_insert)} usuarios exitosamente. Contraseña por defecto: '{default_pass}'.")
    finally:
        conn.close()

if __name__ == '__main__':
    seed_default_users()
