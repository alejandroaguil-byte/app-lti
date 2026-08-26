import os
import pytest
import datetime
from playwright.sync_api import sync_playwright
from backend.db import get_db_connection
from backend.auth import create_access_token

BASE_URL = "http://localhost:8000"

@pytest.fixture(scope="session")
def base_url():
    return BASE_URL

@pytest.fixture(scope="session")
def auth_token():
    """Generates an authentication token for test user aaguilar."""
    token_data = {
        "sub": "aaguilar",
        "nombre_completo": "Alejandro Aguilar",
        "lt_asignado": "Alejandro Aguilar",
        "rol": "LIDER_TI"
    }
    return create_access_token(token_data)

@pytest.fixture(autouse=True)
def clean_test_data():
    """Cleanup any test records created during test runs."""
    def _cleanup():
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM dbo.Proyectos 
                    WHERE Numero_Proyecto LIKE '%QA%' 
                       OR Numero_Proyecto LIKE '%TEST%'
                       OR Cliente LIKE '%PRUEBA QA%' 
                       OR Cliente LIKE '%INMUTABILIDAD%'
                       OR Cliente LIKE '%MODIFICADO%' 
                       OR Cliente LIKE '%DRILLDOWN%' 
                       OR Detalle LIKE '%Prueba E2E Automatizada%'
                       OR Detalle LIKE '%QA%'
                       OR Detalle LIKE '%inmutabilidad%'
                """)
                conn.commit()
        except Exception as e:
            print(f"[CLEANUP WARNING] Error cleaning test data: {e}")
        finally:
            conn.close()

    _cleanup()
    yield
    _cleanup()

@pytest.fixture(scope="function")
def page():
    """Playwright page fixture with isolated context."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        yield page
        context.close()
        browser.close()
