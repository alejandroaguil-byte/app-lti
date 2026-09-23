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

---

## 🚀 ROADMAP PENDIENTE PARA MAÑANA (SESIÓN PREVIA A LA DEMO DEL JUEVES)

### 📄 Funcionalidad 3: Exportación de "Ficha Ejecutiva de Proyecto" a PDF Corporativo
- **Objetivo:** Permitir al gerente descargar con 1 clic un PDF estilizado de la ficha del proyecto con membrete y tipografía corporativa de Claro HALO (`#B52217` / `#0097A9`), resumen ejecutivo, tablas de Solots, Tickets SD y RFCs asociadas.
- **Valor para el Gerente:** Llevar la ficha lista para comités directivos o enviarla por correo sin armar PowerPoints a mano.
- **Requerimiento:** Botón `📄 Exportar Ficha (PDF)` en Drill Down y soporte de Kill-Switch para activar/desactivar.

### ⏱️ Funcionalidad 4: Timeline / Línea de Tiempo Visual del Proyecto (Visual Roadmap)
- **Objetivo:** Nueva pestaña en el Drill Down que unifique cronológicamente los hitos del proyecto: Creación en SharePoint ➔ Asignación de Líder ➔ Apertura de Solots SGA ➔ Generación de Tickets HPSM ➔ Creación de RFCs ➔ Hitos pendientes.
- **Valor para el Gerente:** Visibilidad histórica inmediata del ciclo de vida del proyecto en una sola gráfica interactiva.
- **Requerimiento:** Pestaña `📈 Línea de Tiempo` en modal de proyecto con Kill-Switch.

### 🔔 Funcionalidad 5: Centro de Alertas Tempranas y Escalamiento Rápido (SLA Warnings)
- **Objetivo:** Icono de campanita / panel flotante de alertas en la cabecera que resuma los incidentes que exceden SLAs operacionales (>14 días en torres, Solots vencidas sin fecha compromiso).
- **Valor para el Gerente:** Escalamiento proactivo en un solo panel consolidado para la reunión diaria de operaciones.
- **Requerimiento:** Panel de alertas con botón directo de notificación y Kill-Switch.

---

## 🛠️ INSTRUCCIONES PARA RETOMAR MAÑANA
1. En la nueva sesión, invocar `/flujo-5-agentes` indicando con cuál de las funcionalidades pendientes iniciar (por ejemplo: *"Retomemos con la Funcionalidad 3: Exportación a PDF Corporativo"*).
2. El agente orquestador leerá este archivo y activará la fase de planificación (`planificador_specs`) de inmediato.
