"""
GUARDAS DE SEGURIDAD DE LA SUITE DE PRUEBAS
Especificación: odd/tasks/test-safety-dev-email.md (S5, S7)

La base de pruebas es la de producción. Estas guardas son estáticas o con mocks: nunca tocan la BD.

- CP-GUARD-01: Ningún archivo de pruebas usa producción (100.82.24.75) como BASE_URL por defecto.
- CP-GUARD-02: Los N° de proyecto que crean las pruebas contienen 'QA' (no disparan correos y la limpieza los atrapa).
- CP-GUARD-03: Ninguna prueba ejecuta seed_default_users (no reescribe cuentas reales).
- CP-GUARD-04: El monitor de 6 horas nunca envía ni marca proyectos QA/TEST.
"""

import re
from pathlib import Path
from unittest.mock import patch

from backend import main

TESTS = Path(__file__).parent
PROD_IP = "100.82.24.75"
THIS_FILE = Path(__file__).name
# Pruebas explícitas de producción (solo lectura: GET/SELECT)
PRODUCTION_CHECKS = ("test_functional_iacdi_deployment.py", "test_functional_rediseno_halo.py")


def test_guard_01_base_url_defaults_never_point_to_production():
    for f in TESTS.glob("test_*.py"):
        if f.name in PRODUCTION_CHECKS or f.name == THIS_FILE:
            continue
        for m in re.finditer(r'getenv\(\s*"BASE_URL"\s*,\s*"([^"]+)"', f.read_text(encoding="utf-8")):
            assert PROD_IP not in m.group(1), f"{f.name} usa producción como BASE_URL por defecto"


def test_guard_02_created_project_numbers_carry_qa():
    pattern = re.compile(
        r'(?:numero_proyecto|new_nro|dup_num|unique_num|proj_code|test_proj_num|existing_proj|prefix)\s*[=:]\s*f?"([^"]*)"'
    )
    for f in TESTS.glob("test_functional_*.py"):
        for m in pattern.finditer(f.read_text(encoding="utf-8")):
            value = m.group(1)
            # Valores que nunca se persisten (validaciones vacías o sin submit) o lecturas de proyectos reales
            if not value.strip() or value in ("0000", "99912345") or value.startswith("{"):
                continue
            assert "QA" in value.upper(), f"{f.name}: N° de proyecto de prueba sin 'QA': {value}"


def test_guard_03_tests_do_not_seed_users():
    for f in TESTS.glob("test_*.py"):
        if f.name == THIS_FILE:
            continue
        source = f.read_text(encoding="utf-8")
        assert not re.search(r"seed_default_users\(|from\s+backend\.seed_users\s+import\s+seed_default_users", source), f.name


@patch("backend.main.registrar_recordatorio_enviado")
@patch("backend.main.send_solicitud_recordatorio_email", return_value={"success": True})
@patch("backend.main.get_proyectos_pendientes_recordatorio")
def test_guard_04_reminder_cycle_never_marks_qa_projects(mock_get, mock_send, mock_reg, monkeypatch):
    monkeypatch.delenv("EMAIL_REDIRECT_TO", raising=False)
    base = {"Cliente": "C", "Tipo_Servicio": "Otros", "Solicitante": "Pm"}
    mock_get.return_value = [
        {**base, "ID": 1, "Numero_Proyecto": "000QA-TEST-1"},
        {**base, "ID": 2, "Numero_Proyecto": "0001614931"},
    ]

    assert main.run_reminder_cycle() == 1
    assert [p["ID"] for p in mock_send.call_args.args[0]] == [2]
    mock_reg.assert_called_once_with(2)
