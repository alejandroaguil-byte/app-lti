# Reglas del Proyecto y Flujo de Trabajo

## Skill Oficial: `flujo-5-agentes`
Siempre que el usuario solicite un requerimiento mencionando `@flujo-5-agentes`, `flujo-5-agentes` o invoque el ciclo de subagentes:
1. **Planificador de Specs (`planificador_specs`)**: Planificar y documentar en `SPECS_*.md`.
2. **Coder (`coder`)**: Implementar código respetando estrictamente las especificaciones (y corregir iterativamente si el Revisor reporta observaciones).
3. **Revisor de Código (`code_reviewer`)**: Auditar minuciosamente el código. Si encuentra errores/mejoras, los reporta y devuelve el flujo al **Coder (`coder`)** para su corrección; solo cuando esté 100% limpio y aprobado (0 errores), pasa el flujo a **QA Tester**.
4. **QA Tester (`qa_tester`)**: Ejecutar pruebas automatizadas garantizando el **100% de éxito (0 fallos)**.
5. **Validador de Specs (`specs_validator`)**: Auditar y certificar que no haya **"ni más ni menos"**.

## Regla de Identidad Institucional en Correos y Notificaciones
- En todos los correos, comunicados, firmas, recordatorios y notificaciones institucionales generadas por el sistema, donde se haga referencia al área u organización técnica, debe decir siempre **"PCDI"** y **NUNCA** "Dirección de Operaciones TI".

