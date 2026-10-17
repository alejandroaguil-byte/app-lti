# Release v1.11.0 — Tours por Módulo, Búsqueda Navegable y Proyectos Asociados

**Fecha de Lanzamiento:** 17 de Octubre de 2026  
**Rama Base:** `main`  
**Versión anterior:** `v1.10.0`

---

## Resumen de la Versión

Cada módulo tiene su tour guiado, los resultados de Búsqueda se recorren hacia los lados sin bajar hasta el final de la página, el tablero de Proyectos muestra cuántos proyectos están en revisión y cerrados, y un LTI puede asociar números de proyecto (padre e hijos de una misma implementación) para ver juntos sus Solots, Tickets y RFCs.

---

## Nuevas Funcionalidades

### 1. Tour guiado en todos los módulos
- Proyectos, Búsqueda, Tickets SM y Usuarios muestran su recorrido la primera vez que cada usuario entra al módulo.
- El botón **Ver tour** de cada módulo lo repite cuando se quiera.
- El estado "visto" es por usuario y por módulo, y se guarda en el navegador.
- Solicitudes LTI no cambia: su tour arranca solo para PM.

### 2. Búsqueda: barra horizontal siempre accesible
- Cada tabla de resultados tiene su propio scroll, ajustado al alto de la ventana y con el encabezado fijo. La barra para moverse a los lados queda siempre a la vista.
- Además, se puede hacer clic y arrastrar sobre la tabla para moverla hacia los lados. Los botones de la tabla funcionan igual que antes.

### 3. Tarjetas En revisión y Cerrados
- El tablero de Proyectos suma dos tarjetas: **En revisión** y **Cerrados** (incluye el estado legado `Atendido`).
- Respetan el mismo filtro de LTI y la misma visibilidad que el resto de las tarjetas.

### 4. Proyectos asociados
- En el **Resumen** del detalle, el bloque **Proyectos asociados** permite asociar un N° de proyecto, por ejemplo un proyecto hijo de la misma implementación. Ese N° puede no existir en `dbo.Proyectos`.
- El N° se acepta con o sin el prefijo SGA `000` y sin importar mayúsculas.
- El grupo es simétrico y transitivo: si A se asocia con B y con C, cada uno ve a los otros dos.
- Las pestañas **Solots**, **Tickets** y **RFCs** del detalle suman los registros de todo el grupo y muestran la columna **Proyecto origen**.
- El listado, los KPIs, las alertas, el diagnóstico, la ficha y la línea de tiempo no cambian.
- Pueden asociar y quitar números los mismos usuarios que pueden ver el proyecto.
- Validaciones:
  - "El N° de proyecto es obligatorio".
  - "El N° de proyecto solo puede contener letras, números y guiones (máx. 30 caracteres)".
  - "No puedes asociar un proyecto consigo mismo".
  - "El N° de proyecto ya está asociado a este grupo" (409).
- Al eliminar un proyecto también se eliminan sus asociaciones.

---

## Notas de Despliegue

1. `./deploy_to_iacdi.sh`.
2. `sudo systemctl restart app-lti.service` en `iacdi`, porque cambia el backend. Al iniciar se crea `dbo.Proyecto_Asociaciones` si no existe. El cambio es solo aditivo: no modifica tablas existentes.
3. No requiere migración de datos.
