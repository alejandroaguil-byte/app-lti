# Release v1.10.0 — Ciclo de Vida de Proyectos, Bitácora y Visibilidad por LTI

**Fecha de Lanzamiento:** 16 de Octubre de 2026  
**Rama Base:** `main`  
**Versión anterior:** `v1.9.0`

---

## Resumen de la Versión

Los proyectos pasan a un ciclo de vida de 4 estados con documentación obligatoria al entrar en revisión y al cerrarse, cada proyecto tiene una bitácora con adjuntos, cada usuario ve solo los proyectos de su LTI y las tarjetas del tablero explican su significado.

---

## Nuevas Funcionalidades

### 1. Estados del proyecto
| Estado | Significado |
|---|---|
| Generado | El PM pidió la asignación de un LTI. |
| En ejecución | Ya hay un LTI asignado (el cambio es automático al asignar). |
| En revisión | El LTI puso el proyecto en revisión. |
| Cerrado | Proyecto cerrado. |

- Al pasar a **En revisión** se exige documentar el motivo; al pasar a **Cerrado**, la información de cierre. Ambas notas admiten evidencias adjuntas y quedan en la bitácora.
- KPI *En curso* = En ejecución + En revisión; *Efectividad* = Cerrados / total.
- El estado legado `Atendido` se muestra y se cuenta como `Cerrado`.

### 2. Bitácora del proyecto
- Pestaña **Bitácora** en el detalle: entradas de texto libre con autor y fecha, más las notas de revisión y cierre.
- Adjuntos de hasta 9 MB por archivo (PDF, imágenes, Office, MSG, EML, ZIP, TXT, CSV), descargables solo por quien puede ver el proyecto.

### 3. Visibilidad por LTI
- Cada usuario ve solo los proyectos de su LTI; `alejandro.aguilar` y `pablo.castillo` ven todos y son los únicos que pueden usar **Asignar LTI** en Búsqueda → Solots.
- La restricción se aplica en el backend (listado, KPIs, alertas, detalle, edición, eliminación y bitácora).

### 4. Tarjetas KPI explicadas
- Burbuja explicativa al pasar el mouse o con el foco del teclado sobre cada tarjeta.

---

## Notas de Despliegue

1. `./deploy_to_iacdi.sh` (excluye `data/`, donde viven los adjuntos de producción).
2. `sudo systemctl restart app-lti.service` en `iacdi` (cambia el backend). Al iniciar se crean `dbo.Proyecto_Bitacora` y `dbo.Proyecto_Adjuntos` si no existen.
3. Migración de estados: `python scripts/migrar_estados_proyectos.py` (dry-run) y luego `--apply` (respaldo JSON en `backups_iacdi/` antes de escribir): `Atendido` → `Cerrado`; `Generado` con LTI asignado → `En ejecucion`.
