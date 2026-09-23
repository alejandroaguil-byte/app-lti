# 📌 TAREAS PENDIENTES — PRÓXIMA SESIÓN (DEMO JUEVES APP LTI / HALO)

**Fecha de Registro:** 2026-09-23 (Cierre de sesión nocturna)  
**Proyecto:** HALO — App Líderes TI (`/home/bobbasystem/Desarrollos/app-lti`)  
**Rama Git Activa:** `sso-portal-acceso`  
**Servidores Sincronizados:**
- Desarrollo: `bobbadeveloper` (Localhost:8000)
- Producción: `iacdi` (Tailscale `100.82.24.75:8000` / `https://200.14.222.162/app-lti/`)

---

## ✅ ESTADO ACTUAL: FUNCIONALIDADES YA COMPLETADAS Y DESPLEGADAS

1. **Funcionalidad 1: Semáforo de Salud Operacional (Health Score)**:
   - Clasificación cuádruple: 🟢 Saludable, 🟡 En Riesgo, 🔴 Crítico (con pulso sutil), ⚪ Sin Datos.
   - Tarjetas KPI interactivas con filtrado y desfiltrado al clic.
   - Tooltips flotantes con desglose de diagnóstico.
   - **Kill-Switch**: Botón `🚦 Salud: ON / OFF` en sub-barra, `localStorage` y política de Cero Rastros (8 vs 9 columnas).

2. **Funcionalidad 2: Diagnóstico Ejecutivo en 1 Clic & Minuta**:
   - Análisis multivariable en tiempo real de Solots (SGA), Tickets (HPSM) y RFCs.
   - Identificación de cuellos de botella por Torre Operativa (`Torre Linux`, etc.) y días de atraso.
   - Recomendaciones de escalamiento priorizadas por severidad.
   - Botón `📋 Copiar Minuta` (texto plano) y botón `📧 Enviar Minuta por Correo` (modal Office 365 prellenado).
   - **Kill-Switch**: Botón `⚡ Diagnóstico: ON / OFF` en sub-barra, `localStorage` y política de Cero Rastros.
   - **Pruebas Automatizadas:** 206/206 aprobadas (100% pass rate).

3. **Funcionalidad 3: Exportación de 'Ficha Ejecutiva de Proyecto' a PDF Corporativo & Kill-Switch**:
   - Descarga con 1 clic de documento PDF/imprimible A4 corporativo Claro HALO.
   - Membrete institucional con logotipo SVG oficial vectorizado, paleta `#B52217` / `#0097A9`, tipografía de alta fidelidad.
   - Indicador de Salud Operacional, KPIs de avance, resumen, diagnóstico sintético, cuellos de botella y recomendaciones.
   - Tablas compactas de Solots SGA (con días de atraso), Tickets HPSM/SD (con permanencia y alertas) y RFCs.
   - Generación de Folio determinista único (`HALO-FE-YYYY-XXXXXX-HASH`), firmas institucionales y disclaimer de confidencialidad.
   - Endpoints REST `/api/proyectos/{id}/ficha-ejecutiva` y `/api/proyectos/{id}/ficha-html`.
   - **Kill-Switch**: Botón `📄 Ficha PDF: ON / OFF` (`#pdf-export-toggle-btn`), switch maestro en runtime y política estricta de Cero Rastros.
   - **Pruebas Automatizadas:** Suite completa en `tests/test_ficha_ejecutiva_pdf.py` y `tests/test_functional_ficha_ejecutiva_pdf.py` (13/13 aprobadas).

4. **Funcionalidad 4: Timeline / Línea de Tiempo Visual del Proyecto (Visual Roadmap) & Kill-Switch**:
   - **Estado:** ✅ **IMPLEMENTADA, INTEGRADA Y VALIDADA (100%)**.
   - Pestaña interactiva `📈 Línea de Tiempo` (`data-tab="timeline"`) con unificación cronológica de 4 subsistemas (SharePoint, Solots SGA, Tickets HPSM, RFCs).
   - Medición visual de lapsos entre hitos consecutivos (`⏱️ +X d`) y cálculo de Lead Time Total.
   - Grilla de 4 tarjetas KPI en cabecera (Total Hitos, Lead Time, Último Hito, Próximo Compromiso / Alerta de Atraso con borde pulsante `#B52217`).
   - Barra de filtros rápidos por categoría tipo píldora (`🌟 Todos`, `📁 SharePoint`, `⚡ SGA Solots`, `🎫 Tickets SD`, `🔄 RFCs`).
   - Endpoint backend dedicado: `GET /api/proyectos/{id}/timeline` protegido con `Depends(require_lti_or_admin)`.
   - **Kill-Switch Mandatorio**: Botón `⏱️ Timeline: ON / OFF` en sub-barra, switch global `window.HALO_CONFIG.ENABLE_TIMELINE`, `localStorage` y política estricta de Cero Rastros (auto-conmutación inmediata a `📋 Resumen` si estaba activa al apagar).
   - **Pruebas Automatizadas:** 18/18 pruebas aprobadas (10 unitarias en `tests/test_timeline_visual.py` y 8 funcionales/E2E en `tests/test_functional_timeline_visual.py`). Total suite de regresión: 37/37 aprobadas.

---

## 🚀 ROADMAP PENDIENTE PARA MAÑANA (SESIÓN PREVIA A LA DEMO DEL JUEVES)

### 🔔 Funcionalidad 5: Centro de Alertas Tempranas y Escalamiento Rápido (SLA Warnings)
- **Objetivo:** Icono de campanita / panel flotante de alertas en la cabecera que resuma los incidentes que exceden SLAs operacionales (>14 días en torres, Solots vencidas sin fecha compromiso).
- **Valor para el Gerente:** Escalamiento proactivo en un solo panel consolidado para la reunión diaria de operaciones.
- **Requerimiento:** Panel de alertas con botón directo de notificación y Kill-Switch.

---

## 🛠️ INSTRUCCIONES PARA RETOMAR MAÑANA
1. En la nueva sesión, invocar `/flujo-5-agentes` indicando con cuál de las funcionalidades pendientes iniciar (por ejemplo: *"Retomemos con la Funcionalidad 3: Exportación a PDF Corporativo"*).
2. El agente orquestador leerá este archivo y activará la fase de planificación (`planificador_specs`) de inmediato.
