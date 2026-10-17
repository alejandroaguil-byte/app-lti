# HALO — App Líderes TI 🚀

Aplicación web oficial integrada al ecosistema **HALO** (Portal de Acceso de Claro Chile) desarrollada para que los **Líderes TI** realicen el seguimiento integral y en tiempo real de sus proyectos asignados, Solots de backlog de operaciones (SGA), tickets de requerimientos/incidentes (HPSM) y Solicitudes de Cambio (RFCs).

Diseñada con la identidad visual corporativa de Claro Chile (cabecera institucional roja `#B52217`, isotipo HALO oficial, acentos `#DA291C` y `#0097A9`, y sub-barra de navegación modular con soporte nativo de Modo Claro y Modo Oscuro).

---

## 🌟 Características Principales

1. **Dashboard Personalizado por Líder TI**:
   - Al iniciar sesión, cada Líder TI visualiza automáticamente sus proyectos asignados.
   - Perfil Administrador (`admin`) con capacidad de auditar todos los proyectos y filtrar por cualquier Líder TI.
   - Indicadores ejecutivos en tiempo real (KPIs): Total Proyectos, Solots en Backlog, Tickets SD y RFCs asociadas.

2. **Vista Principal de Proyectos**:
   - **Campos mostrados**:
     - `Cliente (Título)`
     - `N° Proyecto`
     - `LT Asignado`
     - `Solicitante`
     - `Estado` (con badges dinámicos según avance)
     - `Creado` (Fecha de creación)
     - `Detalle`
     - `Acciones / Drill Down`

3. **Drill Down Interactivo (Tabs)**:
   - **📋 Pestaña 1: Resumen y Detalle Técnico**: Ficha técnica del proyecto, desglose de totales y detalle de configuración.
   - **⚡ Pestaña 2: Solot (`CT_BACKLOG_OPERACIONES2`)**:
     - *N° Cliente* (`ID_CLI`)
     - *N° Proyecto* (`NRO_PROYECTO`)
     - *Solot* (`ID_OTP`)
     - *Descripcion* (`DESCR_OTP`)
     - *Estado* (`ESTADO_OTP`)
     - *Fecha compromiso* (`FECHA_COMPROMETIDA`)
     - *Fecha creacion* (`FECHA_INSERT`)
     - *Contrato* (`PLAZO_CONTRATO`)
     - *Producto* (`PRODUCTO`)
     - *Servicio* (`SERVICIO`)
     - *N° Servicio* (`NRO_SERVICIO`)
   - **🎫 Pestaña 3: Tickets SD (`registrosRF_SD_SM`)**:
     - *ID* (`CC_INCIDENT_ID`)
     - *Solicitante* (`REQUESTOR_NAME`)
     - *Estado* (`STATUS`)
     - *Fecha creacion* (`SUBMIT_DATE`)
     - *Fecha cierre* (`CLOSE_DATE`)
     - *Titulo* (`BRIEF_DESCRIPTION`)
     - *Categoria* (`CATEGORY`)
     - *Servicio* (`CC_DETALLE_SERVICIO`)
     - *Grupo de Asignacion* (`ASSIGNED_GROUP`)
     - *Asignado* (`ASSIGNED_TO`)
     - *RF* (`RF_ID`)
   - **🔄 Pestaña 4: RFCs (`registrosSM_RFC`)**:
     - *ID* (`NUMBER`)
     - *Titulo* (`BRIEF_DESCRIPTION`)
     - *Descripción* (`DESCRIPTION`)
     - *Solicitante* (`REQUESTED_BY`)
     - *Fecha cierre* (`CLOSE_TIME`)
     - *N° Proyecto* (`CC_PROYECT_NUMBER`)
     - *Servicio Padre* (`CC_SERVICIO_PADRE`)
     - *Grupo de Asignación* (`ASSIGN_DEPT`)
     - *Asignado* (`ASSIGNED_TO`)

4. **Diseño & Experiencia de Usuario (UI/UX)**:
   - Soporte nativo para **Modo Claro** y **Modo Oscuro** con toggle persistente (`localStorage`).
   - Búsqueda en tiempo real (por Cliente, N° Proyecto o Detalle).
   - Filtro por Estado SharePoint con catálogo canónico oficial (`Generado`, `En revision`, `Atendido`) y selector de Líder TI.

5. **Generador Automatizado de Tickets y Peticiones (Service Manager Bot - v1.2.0)**:
   - **Catálogo Dinámico de Contactos**: Selección entre los 5 líderes técnicos oficiales (`ALEJANDRO JAVIER AGUILAR MORALES`, `JUAN BARRERA RAMOS`, `SAMUEL PAREDES SAEZ`, `SOLANGE ANGELICA ORTIZ VIROLDE`, `Erwin Patricio Sandoval Cadiz`).
   - **Catálogo Oficial de Grupos de Asignación**: 11 grupos y torres de soporte técnico (`Lideres Tecnicos`, `ProvisionConectividadTI`, `ProvisionVirtualizacionTI`, `Plataforma T3 / Soporte Especializado`, `Torre Linux`, `Torre Microsoft`, `Torre Monitoreo`, `Torre Plataformas Internas`, `Torre Respaldos`, `Torre SAP`, `Torre Virtualizacion`) con búsqueda modal desatendida.
   - **Niveles Normalizados de Impacto & Urgencia**: Mapeo exacto con los 3 niveles de Impacto (`1 - Alto (Perdida Total)`, `2 - Moderada (Perdida Parcial)`, `3 - Menor (Existen WorkAround)`) y los 4 niveles de Urgencia (`1 - Crítica (Atención Inmediata)`, `2 - Alta (Resolución a corto plazo)`, `3 - Media (Resolución a mediano plazo)`, `4 - Baja (No requiere urgencia)`).
   - **Formulario Limpio sin Hardcodes**: Campos de Título y Descripción limpios con placeholders guiados y validación obligatoria antes de la ejecución.
   - **Automatización Desatendida & SSE**: Async Playwright con streaming lineal en tiempo real, creación de Interacción (SD), vinculación de Petición Relacionada (`Alejandro.Aguilar`), captura de doble ID, logout limpio (`Info. del usuario` &rarr; `Cerrar sesión` &rarr; `Sí`) y modal interactivo de éxito con botón directo a notificación por correo.

6. **Envío Automatizado de Notificación por Correo (Office 365 SMTP - v1.2.0)**:
   - Botón directo **"📧 Enviar correo"** integrado en el popup de confirmación de tickets.
   - Modal de redacción con animación nativa y prellenado inteligente:
     * **Para**: `alejandro.aguilarm@clarovtr.cl` (editable, soporte multi-destinatario).
     * **Asunto**: Título ingresado en el generador de tickets (editable).
     * **Cuerpo**: Descripción detallada del ticket (editable).
     * **Adjunto**: Zona de carga para adjuntar archivos de soporte/evidencias (opcional, máx. 15MB).
   - Conexión segura estándar a través de **Microsoft Office 365 SMTP** (`smtp.office365.com`, puerto 587, STARTTLS).
   - Manejo defensivo de excepciones SMTP, timeouts y validación de variables de entorno sin interrumpir el flujo del usuario.

7. **Semáforo de Salud del Proyecto (Project Health Score) & Kill-Switch (v1.3.0)**:
   - **Evaluación Operacional Multivariable**: Motor de cálculo que evalúa en tiempo real el atraso de Solots SGA (`dbo.CT_BACKLOG_OPERACIONES2`), antigüedad de tickets SD (`dbo.registrosRF_SD_SM`) y estado de RFCs (`dbo.registrosSM_RFC`).
   - **Estados del Semáforo**:
     * 🟢 **Saludable**: Sin atrasos críticos, Solots dentro de plazo, tickets resueltos o en progreso normal (<= 7 días).
     * 🟡 **En Riesgo / Atención**: Tickets abiertos > 7 días, Solots próximas a vencer (< 5 días hacia la fecha comprometida) sin cierre, o RFCs en revisión prolongada.
     * 🔴 **Crítico**: Solots con fecha comprometida vencida, tickets abiertos > 14 días o incidencias mayores no resueltas.
     * ⚪ **Sin Datos / Neutro**: Proyectos sin Solots ni tickets vinculados (etapa inicial o documental).
   - **Diagnóstico Transparente (Tooltips)**: Cada badge incluye un tooltip explicativo interactivo detallando las razones exactas del color asignado (ej: *"🔴 Crítico: 2 Solots vencidas, 1 ticket abierto > 14 días"*).
   - **Tarjetas KPI de Salud con Filtrado Interactivo**: Grilla complementaria de KPIs de salud en el dashboard con capacidad de filtrar instantáneamente la tabla principal al hacer clic sobre cualquier tarjeta.
   - **Indicador en Drill Down**: Visualización destacada de la salud en la cabecera del proyecto y resumen en la ficha técnica.
   - **Interruptor de Apagado Rápido (Kill-Switch Mandatorio)**: Control toggle en la sub-barra (`🚦 Salud: ON / OFF`) y variable global (`window.HALO_CONFIG.ENABLE_HEALTH_SCORE`), con persistencia en `localStorage`. Si se desactiva, la funcionalidad se oculta por completo sin dejar rastros en la interfaz, volviendo de manera limpia a las 8 columnas y diseño estándar original.

8. **Diagnóstico Ejecutivo en 1 Clic & Kill-Switch (v1.4.0)**:
   - **Análisis Operacional Instantáneo**: Endpoint de alto rendimiento `GET /api/proyectos/{id}/diagnostico` que procesa en tiempo real las Solots de operaciones (`dbo.CT_BACKLOG_OPERACIONES2`), tickets de incidentes (`dbo.registrosRF_SD_SM`) y RFCs (`dbo.registrosSM_RFC`).
   - **Detección Automática de Cuellos de Botella**: Identificación de bloqueos operacionales clasificados por severidad (Crítica, Alta, Media), calculando días de atraso de Solots e individualizando las **Torres de Soporte Responsables** (ej. `Torre Linux`, `Torre Microsoft`, `ProvisionConectividadTI`) de tickets detenidos sin resolución.
   - **Recomendaciones de Escalamiento Accionables**: Generación algorítmica de planes de acción inmediatos priorizados (Urgente, Alta, Media) con sugerencia de canal y destinatario clave.
   - **Minuta Ejecutiva Multiformato & Acciones 1 Clic**:
     * Visor con minuta ejecutiva formateada lista para ser compartida.
     * Botón **"📋 Copiar Minuta"**: Copia inmediata al portapapeles con feedback visual en el botón y alerta Toast.
     * Botón **"📧 Enviar Minuta por Correo"**: Apertura directa del modal de notificación SMTP Office 365 prellenado con el diagnóstico y asunto formal del proyecto.
   - **Mecanismo de Desactivación Rápida (Kill-Switch)**: Botón toggle en sub-barra (`⚡ Diagnóstico: ON / OFF`), configuración maestra `window.HALO_CONFIG.ENABLE_EXECUTIVE_DIAGNOSIS` y persistencia en `localStorage` (`halo_executive_diagnosis_enabled`). Al apagarse, desaparece limpiamente de la tabla y del Drill Down con política de cero rastros.

9. **Exportación de 'Ficha Ejecutiva de Proyecto' a PDF Corporativo & Kill-Switch (v1.5.0)**:
   - **Descarga en 1 Clic**: Botón `📄 Exportar Ficha (PDF)` en la cabecera del Drill Down del proyecto, permitiendo a gerentes y líderes técnicos generar al instante un PDF corporativo listo para comités directivos.
   - **Identidad Visual Corporativa Claro HALO**: Membrete oficial con logotipo vectorizado SVG, paleta institucional Rojo Claro (`#B52217`), Acento Cyan/Teal HALO (`#0097A9`), tipografía estructurada y fecha/hora exacta de extracción de datos.
   - **Contenido Ejecutivo de Alto Valor**:
     * Ficha de resumen general (N° Proyecto, Cliente, Servicio, Líder TI, Solicitante, Estado SP, Antigüedad).
     * Indicador de Salud Operacional (badge 🟢🟡🔴⚪ con justificación sintética).
     * Métricas clave de avance (Solots SGA ejecutadas vs pendientes, % avance, Solots vencidas, Tickets HPSM detenidos >14d clasificados por torre operativa y RFCs).
     * Diagnóstico operacional y recomendaciones de escalamiento priorizadas.
     * Tablas de detalle técnico compactas: Solots SGA con fecha compromiso y días de atraso, Tickets HPSM con grupo/torre responsable y severidad, y RFCs asociadas.
     * Pie de página con folio único determinista (`HALO-FE-YYYY-XXXXXX-HASH`), bloques de firmas y leyenda de confidencialidad institucional.
   - **Arquitectura Desacoplada sin Dependencias C**: Motor cliente-servidor de alta fidelidad vía iframe aislado y CSS `@media print` A4, complementado con endpoints backend `/api/proyectos/{id}/ficha-ejecutiva` y `/api/proyectos/{id}/ficha-html`. Cero binarios nativos de Chromium o librerías C (`pango`/`cairo`), garantizando 100% de compatibilidad tanto en `bobbadeveloper` como en `iacdi` (producción).
   - **Kill-Switch Mandatorio & Política de Cero Rastros**: Botón toggle en sub-barra (`📄 Ficha PDF: ON / OFF`), flag global `window.HALO_CONFIG.ENABLE_PDF_EXPORT` y persistencia en `localStorage` (`halo_export_pdf_enabled`). Al desactivarse, el botón del Drill Down desaparece de forma invisible sin dejar espacios en blanco ni alterar la alineación de los otros controles.

10. **Timeline / Línea de Tiempo Visual del Proyecto (Visual Roadmap) & Kill-Switch (v1.6.0)**:
    - **Visual Roadmap Unificado**: Nueva pestaña interactiva en el Drill Down (`📈 Línea de Tiempo` / `data-tab="timeline"`) que consolida cronológicamente el ciclo de vida completo del proyecto unificando 4 fuentes maestras: SharePoint (`dbo.Proyectos`), Solots SGA (`dbo.CT_BACKLOG_OPERACIONES2`), Tickets Service Manager (`dbo.registrosRF_SD_SM`) y RFCs (`dbo.registrosSM_RFC`).
    - **Medición de Lapsos & Cuellos de Botella**: Cálculo automático de días transcurridos entre eventos consecutivos (`⏱️ +X d`), permitiendo a gerentes y líderes TI detectar visualmente retrasos entre la apertura de Solots, derivaciones a torres técnicas y ventanas de ejecución.
    - **Métricas Ejecutivas en Cabecera**: Tarjetas KPI en la pestaña con Total de Hitos, Lead Time Total (días desde el inicio), Último Hito Registrado y Próximo Compromiso (o alerta roja de atraso con días transcurridos).
    - **Filtros Rápidos por Categoría**: Píldoras de filtrado instantáneo (`🌟 Todos`, `📁 SharePoint`, `⚡ SGA Solots`, `🎫 Tickets SD`, `🔄 RFCs`) con conteos en caliente y recálculo dinámico de lapsos sin recarga.
    - **Alertas de Compromisos y Atrasos**: Destacado cromático diferenciado para hitos programados a futuro (`⏳`) y compromisos vencidos no cerrados (`⚠️ Vencido (+X d)` con borde rojo pulsante `#B52217`).
    - **Endpoint REST Dedicado**: `GET /api/proyectos/{id}/timeline` de alto rendimiento y ordenamiento cronológico ascendente.
    - **Mecanismo Mandatorio Kill-Switch & Cero Rastros**: Botón toggle en sub-barra (`⏱️ Timeline: ON / OFF`), variable global `window.HALO_CONFIG.ENABLE_TIMELINE` y persistencia en `localStorage` (`halo_timeline_enabled`). Si se desactiva, la pestaña desaparece de la vista con política estricta de Cero Rastros (auto-conmutando a la pestaña `📋 Resumen` si estaba activa).

11. **Centro de Alertas Tempranas y Escalamiento Rápido (SLA Warnings) & Kill-Switch (v1.7.0)**:
    - **Campana Institucional Reactiva**: Botón de acceso directo (`🔔` `#alerts-bell-btn`) en la cabecera corporativa Claro HALO (`.app-header .user-area`) con badge numérico en tiempo real (`#alerts-badge-count`).
    - **Animación Pulsante Suave**: Alerta visual roja (`#B52217`) pulsante cuando existen incidentes críticos, ámbar para advertencias y estado neutro/verde cuando la operación está en norma.
    - **Panel Flotante / Drawer de Alertas**: Dropdown interactivo de diseño ejecutivo que clasifica automáticamente todas las desviaciones de SLA en 3 niveles de severidad:
      * 🔴 **Críticas**: Tickets HPSM con más de 14 días abiertos en torres operativas (`Torre Linux`, `ProvisionVirtualizacionTI`, etc.) y Solots SGA con fecha de compromiso formalmente vencida.
      * 🟡 **Advertencias**: Tickets con más de 7 días sin resolución, Solots por vencer en menos de 48 horas y Solots estancadas sin fecha de compromiso tras 10 días de creación, y **proyectos sin movimiento**: proyectos en estado `En ejecucion` o `En revision` (excluye el tipo de servicio `Reunión`) cuyo último movimiento tiene más de 7 días calendario (se muestra como "Sin movimiento hace N días"; el día 7 exacto no alerta). Movimiento es lo más reciente entre: la última entrada de la Bitácora del proyecto; una Solot (`FECHA_INSERT`, `FECHA_CAMBIO_ESTADO_OTP`, `FECHA_REALIZACION`, `FECHACIERRE`), un ticket (`SUBMIT_DATE`, `CLOSE_DATE`) o un RFC (`ORIG_DATE_ENTERED`, `CLOSE_TIME`) vinculados por el mismo N° de proyecto que usa el detalle; y la fecha de creación del proyecto cuando no hay nada más. Cuenta en la campana, en las métricas (`proyectos_sin_movimiento`) y en la minuta, y respeta los filtros de severidad, tipo (`proyecto`) y límite.
      * ℹ️ **Informativas**: Notificaciones de hitos pendientes o reasignación.
    - **Alcance por usuario**: la campana muestra las alertas de los proyectos que lleva el LTI logueado. Los usuarios con visibilidad total que tienen LTI asignado (p. ej. `alejandro.aguilar`) ven solo los de su LTI (un parámetro `lider` explícito se respeta y `lider=todos` pide el alcance completo); los usuarios con visibilidad total sin LTI asignado (p. ej. `pablo.castillo`) ven todos los proyectos; el resto de usuarios queda limitado a su propio LTI y, sin LTI asignado, no ve alertas.
    - **Acción Inmediata 1 Clic ('Ver Proyecto')**: Cada tarjeta de alerta incluye acceso directo al modal Drill Down del proyecto correspondiente, cerrando suavemente el panel.
    - **Escalamiento Rápido Multicanal**:
      * Botón **"📋 Copiar Minuta"**: Genera una minuta ejecutiva formateada en texto plano lista para comités de operaciones (Daily Ops) y mensajería corporativa.
      * Botón **"📧 Escalar por Correo"**: Apertura directa del modal institucional Office 365 con asunto `[HALO ESCALAMIENTO] Alertas Críticas SLA` y cuerpo prellenado con la tabla de incidentes fuera de plazo.
    - **Endpoint REST de Alto Rendimiento**: `GET /api/alertas/sla` con agregación multivariable en motor MSSQL (`dbo.registrosRF_SD_SM`, `dbo.CT_BACKLOG_OPERACIONES2`, `dbo.Proyectos`) y protección JWT SSO (`Depends(require_lti_or_admin)`).
    - **Mecanismo Mandatorio Kill-Switch & Política de Cero Rastros**: Botón toggle en sub-barra (`🔔 Alertas: ON / OFF`), switch maestro `window.HALO_CONFIG.ENABLE_ALERTS` y persistencia en `localStorage` (`halo_alerts_enabled`). Al desactivarse, la campanita y el panel flotante se ocultan de inmediato con `display: none !important;` sin alterar el alineamiento ni el flexbox del área de usuario.

12. **Notificaciones y Recordatorios Automáticos por Correo para Solicitud LTI (v1.8.0)**:
    - **Notificación Instantánea de Ingreso**: Despacho automático y asíncrono vía `BackgroundTasks` de FastAPI a los coordinadores de líderes TI (`alejandro.aguilarm@clarovtr.cl` y `pablo.castillo@clarovtr.cl`) inmediatamente tras la creación de una solicitud LTI por un PM, con la ficha completa del requerimiento (N° Proyecto, Cliente, PM Solicitante, Estado 'Generado' y Detalle con Solots Liray).
    - **Worker Asíncrono de Recordatorio Periódico (Cada 6 Horas)**: Tarea programada en segundo plano integrada en el ciclo de vida de FastAPI (`lifespan`) que audita continuamente las solicitudes sin líder asignado (`LT_Asignado IS NULL` o sin asignar), despachando recordatorios a los coordinadores cada 6 horas con control de idempotencia y persistencia en MSSQL (`Ultimo_Recordatorio` y `Contador_Recordatorios` en `dbo.Proyectos`) para evitar duplicaciones ante reinicios del backend.
    - **Filtro Anti-Spam de Proyectos Dummy e Históricos**: Algoritmo `is_valid_project_number()` que omite automáticamente proyectos de prueba/demo o reuniones (ej. `0001111111`, `1111111`, tipo `Reunión`), asegurando que solo se notifiquen requerimientos operacionales legítimos.
    - **Notificación de Asignación de Líder Técnico**: Al asignar un líder técnico a una solicitud en `PUT /api/proyectos/{id}`, el sistema notifica de inmediato al PM solicitante con copia (**CC**) al Líder Técnico asignado, garantizando trazabilidad y cierre formal de la etapa de asignación.
    - **Resolución Inteligente de Correos (PM y LTI)**: Estrategia multicapa que sincroniza la identidad corporativa de Portal Halo con `dbo.App_Usuarios` vía JIT, catálogo canónico y fallback heurístico empresarial `@clarovtr.cl`.
    - **Herramienta de Difusión y Comunicados Masivos a PMs**: Script automatizado (`scripts/enviar_comunicado_pms.py`) para emisiones institucionales con soporte de destinatarios en `To` y copia oculta `BCC` respetando RFC SMTP, con URL corporativa oficial `https://200.14.222.162/login.html`.
    - **Estandarización de Identidad Institucional PCDI**: Firma, membretes y plantillas homologadas bajo la denominación oficial **PCDI • Claro Chile / VTR** (sustituyendo "Dirección de Operaciones TI").
    - **Plantillas HTML Corporativas HALO**: Diseño institucional con estilos CSS inline compatibles con Outlook desktop y web, header Rojo Claro `#B52217`, acentos Teal `#0097A9`, cajas de alerta `#FDEDEA` / `#DA291C` y enlaces directos de gestión en el portal.

13. **Asignación Directa de LTI e Interfaz HALO Simplificada (v1.9.0)**:
    - **Asignación desde el backlog**: botón **Asignar LTI** en Búsqueda → Solots (`POST /api/backlog/asignar-lti`); crea el proyecto en `dbo.Proyectos` si no existe o solo cambia su LTI.
    - **Asignadores autorizados**: `alejandro.aguilar` y `pablo.castillo` siempre pueden asignar LTI, sin importar su rol (ver sección RBAC).
    - **Interfaz simplificada**: navegación con 4 módulos, iconos de línea sin emojis, tablero con 4 KPI y alertas SLA agrupadas por proyecto.
    - **Protección de datos**: redirección de correos en desarrollo (`EMAIL_REDIRECT_TO`), sin correos para proyectos QA/TEST y pruebas que solo limpian sus propios datos. Detalle en [RELEASE_v1.9.0.md](RELEASE_v1.9.0.md).

14. **Ciclo de Vida de Proyectos, Bitácora y Visibilidad por LTI (v1.10.0)**:
    - **4 estados**: `Generado` (solicitud del PM sin LTI), `En ejecucion` (LTI asignado; el cambio es automático al asignar), `En revision` y `Cerrado`. El estado legado `Atendido` se trata como `Cerrado`; `scripts/migrar_estados_proyectos.py` migra los datos (dry-run por defecto, `--apply` con respaldo JSON en `backups_iacdi/`).
    - **Notas obligatorias**: al pasar a *En revisión* se exige el motivo y al pasar a *Cerrado* la información de cierre (`nota_estado` en `PUT /api/proyectos/{id}`); ambas quedan en la bitácora y admiten evidencias adjuntas.
    - **Bitácora del proyecto**: pestaña *Bitácora* en el detalle con entradas de texto libre (autor y fecha) y adjuntos. Endpoints `GET/POST /api/proyectos/{id}/bitacora`, `POST /api/proyectos/{id}/bitacora/{entrada}/adjuntos` (campo `archivo`) y `GET /api/proyectos/{id}/adjuntos/{adjunto}`. Tablas `dbo.Proyecto_Bitacora` y `dbo.Proyecto_Adjuntos` (se crean solas al iniciar).
    - **Adjuntos**: máximo 9 MB por archivo (nginx limita `/app-lti/` a 10 MB por request); PDF, imágenes, Office, MSG, EML, ZIP, TXT y CSV. Se guardan en `ADJUNTOS_DIR` (por defecto `data/adjuntos/`, fuera de git y excluido del despliegue).
    - **Visibilidad**: cada usuario ve solo los proyectos de su LTI; `alejandro.aguilar` y `pablo.castillo` ven todos (ver sección RBAC).
    - **Tarjetas KPI explicadas**: cada tarjeta muestra una burbuja con su significado al pasar el mouse o con el foco del teclado.

15. **Tours por Módulo, Búsqueda Navegable y Proyectos Asociados (v1.11.0)**:
    - **Tour guiado en cada módulo**: Proyectos, Búsqueda, Tickets SM y Usuarios muestran su recorrido la primera vez que cada usuario entra al módulo; el botón **Ver tour** lo repite. El estado "visto" se guarda por usuario y por módulo en el navegador (`halo_tour_<módulo>_seen:<usuario>`). Solicitudes LTI mantiene su comportamiento (automático solo para PM).
    - **Resultados de Búsqueda**: cada tabla tiene su propio scroll ajustado al alto de la ventana y encabezado fijo, así la barra horizontal queda siempre visible; además se puede hacer clic y arrastrar sobre la tabla para moverla hacia los lados.
    - **Tarjetas En revisión y Cerrados** en el tablero de Proyectos (`proyectos_en_revision` y `proyectos_cerrados` en `GET /api/kpis`).
    - **Proyectos asociados**: en el Resumen del detalle, un LTI asocia N° de proyecto (por ejemplo un proyecto hijo, aunque no exista en `dbo.Proyectos`). El grupo es simétrico y transitivo, y las pestañas Solots, Tickets y RFCs del detalle suman los registros de todo el grupo con la columna *Proyecto origen*. Listado, KPIs, alertas, diagnóstico, ficha y línea de tiempo no cambian. Endpoints `GET/POST /api/proyectos/{id}/asociaciones` (body `{"numero": "..."}`) y `DELETE /api/proyectos/{id}/asociaciones/{asociacion}`; tabla `dbo.Proyecto_Asociaciones` (se crea sola al iniciar). Detalle en [RELEASE_v1.11.0.md](RELEASE_v1.11.0.md).

---

## 🛠️ Stack Tecnológico

- **Backend**: Python 3.12 + FastAPI + Uvicorn + Playwright Async + PyMSSQL + PyJWT + SMTPLib (STARTTLS).
- **Autenticación**: Single Sign-On (SSO) corporativo vía Portal de Acceso (Cookies HttpOnly `access_token` / `refresh_token`, firma HS256).
- **Base de Datos**: Microsoft SQL Server (`Sharepoint_Proyectos`).
- **Frontend**: SPA con HTML5 Semántico, Vanilla JavaScript y CSS3 nativo con variables de diseño.

---

## 📁 Estructura del Proyecto

```text
app-lti/
├── backend/
│   ├── main.py              # API FastAPI, rutas REST, worker de recordatorios y servidor estático
│   ├── db.py                # Conexión MSSQL, serialización, filtros anti-dummy y aprovisionamiento JIT
│   ├── auth.py              # Verificación de JWT SSO del Portal, cookies HttpOnly y cálculo de roles
│   ├── config.py            # Carga de variables (.env) y configuración global
│   ├── email_service.py     # Servicio SMTP Office 365, soporte To/CC/BCC y plantillas HTML HALO
│   ├── seed_users.py        # Poblador idempotente de roles para líderes y administradores
│   └── ticket_automation.py # Automatización Playwright Async + SSE para Service Manager
├── frontend/
│   ├── index.html           # Estructura principal sin login propio, adaptada a sesión SSO
│   ├── css/
│   │   └── styles.css       # Sistema de diseño, consola terminal, dropzone y temas claro/oscuro
│   └── js/
│       ├── app.js           # Lógica de renderizado, streaming SSE, modales, clipboard y email
│       └── auth.js          # Manejo de sesión SSO por cookies con auto-refresh (/api/auth/refresh)
├── scripts/
│   ├── enviar_comunicado_pms.py # Script de difusión masiva con soporte To y BCC (PCDI)
│   └── deploy_to_iacdi.sh       # Script de sincronización rsync a producción iacdi
├── tests/
│   ├── test_notificaciones_solicitud_lti.py # Pruebas unitarias de eventos de correo y filtros
│   ├── test_email_service.py                # Pruebas de cliente SMTP, sanitización y adjuntos
│   └── ...                                  # Batería completa de pruebas de regresión y E2E
├── .env.example             # Plantilla de variables de entorno (SMTP, BD, PORTAL_JWT_SECRET)
├── requirements.txt         # Dependencias Python
├── run.sh                   # Script de inicio rápido del servidor
└── README.md                # Documentación oficial
```

---

## ⚙️ Configuración y Variables de Entorno (`.env`)

Para habilitar el envío de correos vía **Microsoft Office 365** y personalizar los accesos del sistema, cree un archivo `.env` en la raíz del proyecto basándose en `.env.example`:

```ini
# ==============================================================================
# CONFIGURACIÓN DEL SERVIDOR DE CORREO (OFFICE 365 SMTP)
# ==============================================================================
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USER=alejandro.aguilarm@clarovtr.cl
SMTP_PASS=TuPasswordDeOffice365
SMTP_FROM=alejandro.aguilarm@clarovtr.cl
SMTP_TIMEOUT=30
SMTP_DEFAULT_RECIPIENT=alejandro.aguilarm@clarovtr.cl

# Solo desarrollo/pruebas (NUNCA en produccion): redirige TODO correo a esta(s) direccion(es),
# sin CC/BCC y con prefijo [DEV] en el asunto, y el monitor de 6 horas no marca recordatorios
# (los atiende produccion). Un valor invalido bloquea el envio.
# EMAIL_REDIRECT_TO=alejandro.aguilarm@clarovtr.cl

# ==============================================================================
# CONFIGURACIÓN GENERAL Y BASE DE DATOS
# ==============================================================================
DB_SERVER=192.168.10.6
DB_PORT=1433
DB_USER=sa
DB_PASSWORD=
DB_NAME=Sharepoint_Proyectos

# ==============================================================================
# INTEGRACIÓN SSO PORTAL DE ACCESO (HS256)
# ==============================================================================
PORTAL_JWT_SECRET=tu-portal-jwt-secret-aqui
JWT_ACCESS_SECRET=tu-portal-jwt-secret-aqui
```

> [!NOTE]
> Si la cuenta de Office 365 tiene habilitada la autenticación multifactor (MFA), debe utilizar una **Contraseña de Aplicación (App Password)** generada desde el panel de seguridad de Microsoft 365.
> Si las credenciales no están configuradas en el archivo `.env`, el sistema informará al usuario de manera amigable sin interrumpir la operación de la plataforma.

---

## 🚀 Cómo Iniciar la Aplicación (Entorno Local `bobbadeveloper`)

Ejecuta el script de inicio en la terminal de desarrollo local:

```bash
cd /home/bobbasystem/Desarrollos/app-lti
./run.sh
```

El servidor iniciará en: **`http://localhost:8000`**

> [!CAUTION]
> ### Regla Estricta de Entorno
> La implementación y verificación activa se realiza **exclusivamente en `bobbadeveloper`** (`/home/bobbasystem/Desarrollos/app-lti`). Está estrictamente prohibido ejecutar `deploy_to_iacdi.sh` o realizar cambios directos en el servidor `iacdi` sin autorización explícita.

---

## 🌐 Topología y Acceso vía Portal de Acceso (Producción `iacdi`)

En el entorno integrado, App LTI corre detrás del reverse proxy Nginx del **Portal de Acceso** (`~/portal-acceso`), configurado bajo el mismo origen seguro:

- **Ruta Oficial de Acceso:** **`https://200.14.222.162/app-lti/`**
- **Slug de Herramienta en Portal:** `app-lti`
- **Host SSH Remoto (Producción):** `iacdi` (`100.82.24.75`, usuario `iacdi`)
- **Directorio Remoto:** `/home/iacdi/Desarrollos/app-lti`
- **Base de Datos:** Microsoft SQL Server `192.168.10.6:1433` (`Sharepoint_Proyectos`)

---

## 🔐 Control de Acceso Basado en Roles (RBAC) & SSO del Portal

App LTI utiliza autenticación federada **Single Sign-On (SSO)** mediante las cookies seguras HttpOnly (`access_token`, `refresh_token`) emitidas por el **Portal de Acceso**.

### 1. Formato Canónico de Cuentas
- Desaparecen las cuentas hardcodeadas anteriores.
- Se utiliza el formato corporativo oficial del Portal: **`nombre.apellido`** en minúsculas (ejemplos: `alejandro.aguilar`, `solange.ortiz`, `juan.barrera`, `samuel.paredes`, `erwin.sandoval`).
- **Aprovisionamiento Just-In-Time (JIT):** Cuando un usuario con sesión válida en el Portal accede por primera vez a App LTI, el sistema lo registra automáticamente en `dbo.App_Usuarios`, permitiendo que el Administrador de App LTI configure su rol operativo y Líder TI asignado sin necesidad de crear cuentas manuales.

### 2. Mapeo de `toolAccess` del Portal y Permisos Efectivos

El token JWT del Portal define la capacidad de escritura de la sesión:
- **Portal `"operador"` (o Super Admin `adminLevel >= 2`):** Permite ejecutar operaciones según el rol registrado en App LTI (`ADMIN` o `LTI`), habilitando edición de proyectos, creación de tickets Service Manager y gestión de solicitudes.
- **Portal `"lectura"` o sin asignación:** Restringe forzosamente la sesión al perfil **`PM` (Solo Lectura / Solicitud LTI)**, impidiendo cualquier acción de escritura o acceso al mantenedor de usuarios, independientemente del rol local.
- **Bloqueo Local:** Si el usuario tiene `activo = 0` en `dbo.App_Usuarios`, el backend deniega el acceso con `403 Forbidden`.
- **Asignadores autorizados (`LTI_ASSIGNER_USERNAMES` en `backend/config.py`):** `alejandro.aguilar` y `pablo.castillo` nunca quedan por debajo del rol `LTI`. Si el Portal (`"lectura"`) o el rol local los dejaría como `PM`, su rol efectivo pasa a `LTI` para que siempre puedan asignar LTI. Siguen necesitando acceso en el Portal y estar activos.

### 3. Visibilidad de Proyectos
- **Visibilidad total (`FULL_PROJECT_VISIBILITY_USERNAMES` en `backend/config.py`):** `alejandro.aguilar` y `pablo.castillo` ven todos los proyectos y pueden filtrar por cualquier Líder TI.
- **Resto de usuarios (cualquier rol, incluidos otros ADMIN):** solo ven proyectos cuyo `LT_Asignado` es su propio `lt_asignado`; sin `lt_asignado` no ven proyectos. El backend ignora el filtro `lt` en listado, KPIs y alertas, y responde `404` en el detalle, edición, eliminación y bitácora de proyectos ajenos. La búsqueda del módulo Búsqueda no cambia, pero su botón **Asignar LTI** queda solo para estos dos usuarios (`403` para el resto).
- `GET /api/auth/me` informa `ve_todos_proyectos`; el frontend bloquea el filtro de Líder TI cuando es `false`.

### 4. Asignación de LTI a Proyectos
- **Desde Proyectos:** menú "⋯" → **Editar** → "LT Asignado" (`PUT /api/proyectos/{id}`). Cubre las solicitudes que crean los PM.
- **Desde Búsqueda → Solots (`CT_BACKLOG_OPERACIONES2`):** botón **Asignar LTI** en cada fila (`POST /api/backlog/asignar-lti`, solo `alejandro.aguilar` y `pablo.castillo`). Si el proyecto ya existe en `dbo.Proyectos` solo cambia `LT_Asignado`; si no existe, se crea con el cliente y el PM del backlog y estado `En ejecucion`. La tabla del backlog nunca se modifica.
- En ambos casos, si el proyecto no tenía LTI se envía el correo de asignación.
- **Vinculación con Solots, Tickets y RFCs:** un registro pertenece al proyecto si su `ID_Proyecto` coincide o si su `Numero_Proyecto_Limpio` coincide con el `Numero_Proyecto` del proyecto, tal cual o sin el prefijo SGA `000` (`0001609373` ↔ `1609373`). Aplica al detalle, listado, KPIs, alertas SLA, diagnóstico, ficha y línea de tiempo; ningún proceso completa ya `ID_Proyecto`.

### 5. Centralización de Gestión de Identidades
- **Alta de cuentas y contraseñas:** Centralizadas al 100% en el Portal de Acceso. App LTI no almacena `password_hash` ni expone formularios de creación de cuentas o reseteo de claves.
- **Mantenedor Local de App LTI (`👥 Usuarios`):** Exclusivo para administradores locales, permitiendo asignar el rol del negocio (`PM`, `LTI`, `ADMIN`), vincular el Líder TI responsable (`lt_asignado`) y alternar el estado activo/bloqueado.

---

## 📚 Documentación y Especificaciones Técnicas (SPECS)

- [SPECS_NOTIFICACIONES_CORREO_SOLICITUD_LTI.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_NOTIFICACIONES_CORREO_SOLICITUD_LTI.md): **(v1.0.0 Ratificada)** Especificación técnica integral del sistema automatizado de notificaciones y recordatorios periódicos por correo para el módulo Solicitud LTI. Alertas inmediatas al crear solicitud LTI a coordinadores (`alejandro.aguilarm@clarovtr.cl` y `pablo.castillo@clarovtr.cl`), worker en segundo plano (FastAPI `lifespan` + `asyncio`) para recordatorios cada 6 horas con persistencia anti-spam en MSSQL (`Ultimo_Recordatorio` y `Contador_Recordatorios`), notificación automática al asignar LTI al PM solicitante con copia (CC) al Líder Técnico asignado, resolución inteligente de correos institucionales (@clarovtr.cl) conectada a Portal Halo y aprovisionamiento JIT, diseño de plantillas HTML corporativas con la paleta de colores oficial HALO (`#B52217`, `#0097A9`, `#DA291C`, `#FDEDEA`) compatibles con Outlook desktop/web, contratos REST y plan de pruebas para QA.
- [SPECS_REPLICACION_V_BACKLOG_SOLOT_TAREA.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_REPLICACION_V_BACKLOG_SOLOT_TAREA.md): **(v1.0.0 Ratificada)** Especificación técnica de Replicación y Enriquecimiento de Datos ETL desde la vista SGA `[blixter_prod].[dbo].[V_BACKLOG_SOLOT_TAREA]` (SGA) hacia `[Sharepoint_Proyectos].[dbo].[V_BACKLOG_SOLOT_TAREA]` (MSSQL destino). Esquema DDL canónico de 34 columnas (32 origen + `ID_Proyecto` y `Numero_Proyecto_Limpio`), estrategia de filtrado de datos Backlog 2025+ (~213.040 registros), matemática de inserción por lotes TDS (chunk_size = 50 rows = 1.700 parámetros < 2.100 límite TDS SQL Server), índices nonclustered de alto rendimiento, integración en el cron diario (09:00 y 14:45) en `Carga Data SM` y política de aislamiento estricto (cero modificaciones en `app-lti`).
- [SPECS_ALERTAS_TEMPRANAS_SLA.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_ALERTAS_TEMPRANAS_SLA.md): **(v1.0.0 Ratificada)** Especificación técnica integral de la Funcionalidad 5: 'Centro de Alertas Tempranas y Escalamiento Rápido (SLA Warnings) & Kill-Switch'. Endpoint REST optimizado `GET /api/alertas/sla`, motor de agregación multivariable en MSSQL (`dbo.registrosRF_SD_SM`, `dbo.CT_BACKLOG_OPERACIONES2`, `dbo.Proyectos`), campanita reactiva con badge y animación pulsante suave corporativa (`#B52217`), panel flotante dropdown/drawer con filtros interactivos (`🔴 Críticas`, `🟡 Advertencias`, `🌟 Todas`), botón directo 'Ver Proyecto' hacia el Drill Down, módulo de Escalamiento Rápido (copiado de minuta ejecutiva formateada y correo prellenado Office 365 hacia jefaturas de soporte), soporte dual Claro/Oscuro y Kill-Switch mandatorio (`🔔 Alertas: ON / OFF`) con política de Cero Rastros.
- [SPECS_TIMELINE_VISUAL_PROYECTO.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_TIMELINE_VISUAL_PROYECTO.md): **(v1.0.0 Ratificada)** Especificación técnica integral de la Funcionalidad 4: 'Timeline / Línea de Tiempo Visual del Proyecto (Visual Roadmap) & Kill-Switch'. Endpoint REST `GET /api/proyectos/{id}/timeline`, unificación cronológica de 4 subsistemas (SharePoint, SGA Solots, Tickets HPSM, RFCs), motor de cálculo de lapsos temporales (lead time total y días entre hitos consecutivos), tarjetas KPI ejecutivas en cabecera de pestaña, barra de filtros rápidos por categoría, visualización de hitos futuros y compromisos atrasados con alertas visuales corporativas Claro HALO (`#B52217`, `#0097A9`), soporte completo Modo Claro/Oscuro, Kill-Switch mandatorio en sub-barra (`⏱️ Timeline: ON / OFF`) con política de Cero Rastros y auto-switch a Resumen.
- [SPECS_FICHA_EJECUTIVA_PDF.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_FICHA_EJECUTIVA_PDF.md): **(v1.0.0 Ratificada)** Especificación técnica integral de la Funcionalidad 3: 'Exportación de Ficha Ejecutiva de Proyecto a PDF Corporativo' y Kill-Switch Desactivador. Endpoints REST (`/api/proyectos/{id}/ficha-ejecutiva` y `/api/proyectos/{id}/ficha-html`), motor de renderizado A4 con CSS `@media print` y cero binarios C pesados (máxima compatibilidad entre `bobbadeveloper` e `iacdi`), identidad oficial Claro HALO (`#B52217` y `#0097A9`), foliado determinista, tablas compactas de Solots SGA, Tickets HPSM y RFCs, mecanismo Kill-Switch con persistencia en `localStorage` y política estricta de Cero Rastros.
- [SPECS_DIAGNOSTICO_EJECUTIVO.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_DIAGNOSTICO_EJECUTIVO.md): **(v1.0.0 Ratificada)** Especificación técnica integral de la Funcionalidad 2: 'Diagnóstico Ejecutivo en 1 Clic' y Kill-Switch Desactivador. Motor operacional en tiempo real (`/api/proyectos/{id}/diagnostico`), detección multivariable de cuellos de botella (Solots vencidas y tickets detenidos identificando torres de soporte responsables), recomendaciones de escalamiento priorizadas, minuta multiformato (Texto, MD, HTML), modal interactivo con copiado al portapapeles y envío directo por correo Office 365 SMTP, y mecanismo Kill-Switch con fallback cero rastros para `bobbadeveloper` e `iacdi`.
- [SPECS_SEMAFORO_SALUD_PROYECTOS.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_SEMAFORO_SALUD_PROYECTOS.md): **(v1.0.0 Ratificada)** Especificación técnica del Semáforo de Salud del Proyecto (Project Health Score), reglas operacionales de clasificación (🟢 Saludable, 🟡 En Riesgo, 🔴 Crítico, ⚪ Sin Datos), badges con tooltip explicativo, KPIs de salud interactivos con filtrado directo en tabla, indicador en Drill Down y mecanismo mandatorio de desactivación rápida (Kill-Switch / Feature Toggle) con fallback limpio cero rastros.
- [SPECS_REDISENO_PORTAL_HALO.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_REDISENO_PORTAL_HALO.md): **(v1.0.0 Ratificada)** Especificación técnica de Homologación e Integración Visual al Diseño Corporativo HALO (Claro Chile), tokens `#B52217` / `#DA291C` / `#0097A9`, isotipo SVG oficial, arquitectura desacoplada de doble barra (`.app-header` y `.nav-subbar`), soporte dual Claro/Oscuro y sincronización con servidor `iacdi`.
- [SPECS_INTEGRACION_SSO_PORTAL_ACCESO.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_INTEGRACION_SSO_PORTAL_ACCESO.md): **(v2.0.0 Ratificada)** Especificación técnica definitiva de integración Single Sign-On (SSO) con el Portal de Acceso, cookies HttpOnly, mapeo de `toolAccess`, formato canónico `nombre.apellido`, aprovisionamiento JIT y arquitectura desacoplada sin contraseñas locales.
- [SPECS_DESPLIEGUE_IACDI_TAILSCALE.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_DESPLIEGUE_IACDI_TAILSCALE.md): **(v1.3.0 Ratificada)** Especificación técnica y de infraestructura para el despliegue formal a producción en servidor `iacdi` (IP Tailscale `100.82.24.75:8000`, MSSQL `192.168.10.6:1433`), servicio systemd de usuario con Linger, consolidación Git en rama `sso-portal-acceso`, sincronización rsync protegida de `.env`, validación de endpoints y plan de rollback.
- [SPECS_FILTRO_ESTADOS_SHAREPOINT.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_FILTRO_ESTADOS_SHAREPOINT.md): (v1.0.0) Especificación técnica de Catálogo Canónico y Corrección del Filtro de Estados SharePoint (`Generado`, `En revision`, `Atendido`), desacople de consultas dependientes de BD y renderizado defensivo con fallback en UI.
- [SPECS_TICKET_GENERATOR_CAMPOS_DINAMICOS.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_TICKET_GENERATOR_CAMPOS_DINAMICOS.md): (v1.0.0) Especificación técnica de Catálogo Dinámico de Contactos (5 líderes), Catálogo de Grupos de Asignación (11 torres), Normalización de Impacto y Urgencia con Service Manager, Limpieza de Valores de Prueba Hardcodeados y Placeholders Guiados.
- [SPECS_ENVIO_CORREO_TICKETS.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_ENVIO_CORREO_TICKETS.md): (v1.1.0) Especificación técnica de Envío Automatizado de Notificación por Correo tras la creación de Tickets y Peticiones vía Office 365 SMTP, integración REST dual `multipart/form-data` y JSON (`application/json`), corrección de `Auth.fetchWithAuth` para `FormData`, modal de redacción con adjuntos y parametrización `.env`.
- [SPECS_TICKET_GENERATOR_PETICIONES.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_TICKET_GENERATOR_PETICIONES.md): (v1.1.0) Especificación técnica de Automatización de Tickets e Interacciones, Vinculación de Peticiones Relacionadas, Cierre de Sesión Seguro (Logout), Arquitectura Directa Lineal SSE y Modal con Doble Identificador (SD + Petición).
- [SPECS_MANTENEDOR_USUARIOS_Y_ROLES.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_MANTENEDOR_USUARIOS_Y_ROLES.md): Especificación técnica de Gestión de Usuarios, RBAC (PM, LTI, ADMIN), Mantenedor de Usuarios (`👥 Usuarios`), Poblado desde Excel y Protección destructiva de Proyectos.
- [SPECS_EDIT_DELETE_PROYECTOS.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_EDIT_DELETE_PROYECTOS.md): Especificación técnica para edición y eliminación de proyectos en `dbo.Proyectos`.
- [SPECS_SOLICITUD_LTI.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_SOLICITUD_LTI.md): Especificación técnica del módulo Solicitud LTI con autocompletado SGA, solots Liray y creación desatendida.
- [SPECS_MEJORAS_SEGUIMIENTO_LIDERES_KPIS.md](file:///home/bobbasystem/Desarrollos/app-lti/SPECS_MEJORAS_SEGUIMIENTO_LIDERES_KPIS.md): Especificación técnica para tipografía uniforme, filtro líderes TI con opción 'Sin asignar' y KPI interactiva 'Pendientes de Asignar'.
