"""
Migración de estados de dbo.Proyectos (odd/tasks/estados-bitacora-proyectos.md, S4).

  Atendido                          -> Cerrado
  Generado con LTI asignado         -> En ejecucion
  Generado sin LTI / En revision    -> sin cambios

Por defecto es un dry-run: solo ejecuta SELECT e imprime los conteos por (estado actual -> estado destino).
Con --apply escribe primero un respaldo JSON de [{ID, Estado, LT_Asignado}] de TODAS las filas en
backups_iacdi/proyectos_estados_<timestamp>.json y luego ejecuta ambos UPDATE en UNA sola transacción
(rollback ante cualquier error). Es idempotente: una segunda ejecución no cambia filas.

La base configurada en .env es la de producción: revisar el dry-run antes de usar --apply.

Uso:
    python scripts/migrar_estados_proyectos.py            # dry-run
    python scripts/migrar_estados_proyectos.py --apply    # respalda y migra
"""

import argparse
import datetime
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db import get_db_connection  # noqa: E402

DEFAULT_BACKUP_DIR = ROOT / "backups_iacdi"

SQL_SELECT = "SELECT ID, Estado, LT_Asignado FROM dbo.Proyectos"
SQL_ATENDIDO_A_CERRADO = "UPDATE dbo.Proyectos SET Estado = 'Cerrado' WHERE Estado = 'Atendido'"
SQL_GENERADO_A_EN_EJECUCION = (
    "UPDATE dbo.Proyectos SET Estado = 'En ejecucion' "
    "WHERE Estado = 'Generado' "
    "AND LT_Asignado IS NOT NULL "
    "AND LTRIM(RTRIM(LT_Asignado)) <> '' "
    "AND LOWER(LTRIM(RTRIM(LT_Asignado))) <> 'sin asignar'"
)


def lt_asignado(lt_value) -> bool:
    """True si el LTI está realmente asignado (no NULL, no vacío, no 'sin asignar')."""
    lt_str = str(lt_value).strip() if lt_value is not None else ""
    return bool(lt_str) and lt_str.lower() != "sin asignar"


def target_estado(estado, lt_value) -> str:
    """Estado destino de un proyecto según las reglas de la migración (idempotente)."""
    if estado == "Atendido":
        return "Cerrado"
    if estado == "Generado" and lt_asignado(lt_value):
        return "En ejecucion"
    return estado


def write_backup(rows, backup_dir: Path) -> Path:
    """Guarda [{ID, Estado, LT_Asignado}] de todas las filas y retorna la ruta del archivo."""
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = backup_dir / f"proyectos_estados_{timestamp}.json"
    payload = [{"ID": r["ID"], "Estado": r["Estado"], "LT_Asignado": r["LT_Asignado"]} for r in rows]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_migration(conn, apply: bool = False, backup_dir=DEFAULT_BACKUP_DIR) -> dict:
    """Calcula el plan y, con apply=True, respalda y migra en una sola transacción."""
    with conn.cursor() as cursor:
        cursor.execute(SQL_SELECT)
        rows = cursor.fetchall()

        cambios = Counter()
        for row in rows:
            destino = target_estado(row["Estado"], row["LT_Asignado"])
            if destino != row["Estado"]:
                cambios[(row["Estado"], destino)] += 1
        total_a_cambiar = sum(cambios.values())

        print(f"Proyectos leídos: {len(rows)}")
        if cambios:
            for (actual, destino), cantidad in sorted(cambios.items()):
                print(f"  {actual} -> {destino}: {cantidad}")
        else:
            print("  Sin cambios pendientes")
        print(f"Total de filas a cambiar: {total_a_cambiar}")

        respaldo = None
        if apply:
            respaldo = write_backup(rows, backup_dir)
            print(f"Respaldo escrito en: {respaldo}")
            try:
                cursor.execute(SQL_ATENDIDO_A_CERRADO)
                cursor.execute(SQL_GENERADO_A_EN_EJECUCION)
                conn.commit()
            except Exception:
                conn.rollback()
                print("Error durante la migración: se hizo rollback, no se modificó ninguna fila")
                raise
            print(f"Migración aplicada: {total_a_cambiar} filas actualizadas")
        else:
            print("Modo dry-run: no se modificó ninguna fila (usar --apply para migrar)")

    return {
        "total_leidas": len(rows),
        "cambios": dict(cambios),
        "total_a_cambiar": total_a_cambiar,
        "respaldo": str(respaldo) if respaldo else None,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Migra los estados de dbo.Proyectos al nuevo catálogo (S4).")
    parser.add_argument("--apply", action="store_true", help="Escribe el respaldo y aplica la migración")
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR), help="Directorio del respaldo JSON")
    args = parser.parse_args(argv)

    conn = get_db_connection()
    try:
        run_migration(conn, apply=args.apply, backup_dir=Path(args.backup_dir))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
