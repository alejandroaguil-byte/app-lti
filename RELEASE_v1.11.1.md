# Release v1.11.1 — Correcciones de Proyectos, Adjuntos y Alertas

**Fecha de Lanzamiento:** 17 de Octubre de 2026  
**Rama Base:** `main`  
**Versión anterior:** `v1.11.0`

---

## Resumen de la Versión

Esta versión corrige cuatro problemas del módulo Proyectos y agrega una alerta nueva:
- los adjuntos de la bitácora ya se guardan en producción;
- seleccionar texto en una fila ya no abre el detalle;
- las columnas del listado vuelven a quedar alineadas;
- las alertas se limitan a los proyectos del LTI que inició sesión;
- nueva alerta para proyectos con más de 7 días sin movimiento.

---

## Correcciones

### 1. Seleccionar texto en una fila no abre el detalle
- Un clic normal sobre la fila abre el detalle, igual que antes.
- Si se selecciona texto arrastrando el mouse (por ejemplo para copiar un ID), la fila no abre el detalle. Tampoco lo abren el clic derecho, el clic central ni un clic con Ctrl, Shift, Alt o Cmd.

### 2. Columnas alineadas en el listado de Proyectos
- La celda **Detalle** recortaba su texto a dos líneas con un estilo que la sacaba de la tabla, y por eso las columnas desde **Fecha Solicitud LTI** se veían corridas. Ahora el recorte se aplica a un elemento dentro de la celda.

### 3. Adjuntos de la bitácora en producción
- El servicio `app-lti.service` corre con un sistema de archivos de solo lectura (`ProtectSystem=strict` + `ProtectHome=read-only`), así que no podía crear `data/adjuntos`. Ningún adjunto se había guardado.
- Ahora `data/` es la única ruta con permiso de escritura (`ReadWritePaths`, en `deploy/app-lti.service`).
- Si el servidor no puede escribir el archivo, la API responde "No se pudo guardar el archivo en el servidor" y deja el error registrado en el log.
- Las notas de revisión y cierre que ya se habían registrado siguen en la bitácora (Detalle → **Bitácora**). Sus archivos no llegaron a guardarse, así que hay que volver a subirlos con una entrada nueva de "Registrar avance".

### 4. Alertas del LTI que inició sesión
- `alejandro.aguilar` y `pablo.castillo` (visibilidad total) veían las alertas de todos los proyectos.
- Ahora, si el usuario tiene un LTI asignado, la campana muestra solo las alertas de sus proyectos. Si no tiene LTI asignado (`pablo.castillo`), sigue viendo todas.
- El resto de los usuarios ya veía solo las suyas y no cambia.

---

## Nueva Funcionalidad

### Alerta "Proyecto sin movimiento"
- Se genera para los proyectos **En ejecución** o **En revisión** que llevan más de 7 días calendario sin movimiento. El día 7 todavía no alerta; el día 8, sí.
- Cuenta como movimiento cualquiera de estas fechas:
  - la última entrada de la bitácora;
  - un Solot, Ticket o RFC vinculado, nuevo o actualizado (Solots: inserción, cambio de estado, realización y cierre; Tickets: creación y cierre; RFCs: creación y cierre);
  - la fecha de creación del proyecto.
- Es una alerta de severidad advertencia, aparece en la campana con el texto "Sin movimiento hace N días" y se cuenta en el badge y en la minuta.

---

## Notas de Despliegue

1. `./deploy_to_iacdi.sh`.
2. En `iacdi` hay que crear el directorio de adjuntos, instalar el unit actualizado y reiniciar. El directorio tiene que existir antes del reinicio, porque si no el servicio no arranca:
   ```bash
   sudo install -d -o iacdi -g iacdi -m 0750 /home/iacdi/Desarrollos/app-lti/data /home/iacdi/Desarrollos/app-lti/data/adjuntos
   sudo install -o root -g root -m 0644 /home/iacdi/Desarrollos/app-lti/deploy/app-lti.service /etc/systemd/system/app-lti.service
   sudo systemctl daemon-reload
   sudo systemctl restart app-lti.service
   ```
3. No requiere migración de datos.
