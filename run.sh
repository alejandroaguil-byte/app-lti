#!/usr/bin/env bash
# ==============================================================================
# Script de inicio para App LTI (Servidor Web y API FastAPI)
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="/home/bobbasystem/Desarrollos/Carga Data SM/venv/bin/python3"
VENV_UVICORN="/home/bobbasystem/Desarrollos/Carga Data SM/venv/bin/uvicorn"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "[INFO] Usando python3 del sistema..."
    VENV_PYTHON="python3"
    VENV_UVICORN="uvicorn"
fi

echo "=================================================="
echo "Iniciando App LTI - Portal de Líderes TI"
echo "Directorio: $DIR"
echo "=================================================="

# Poblar usuarios y tablas si es necesario
echo "[MSSQL] Verificando tablas de autenticación y usuarios..."
PYTHONPATH="$DIR" "$VENV_PYTHON" -m backend.seed_users

# Iniciar servidor Uvicorn
PORT=8000
echo "[WEB] Servidor disponible en: http://localhost:$PORT"
echo "Presione Ctrl+C para detener el servidor."

PYTHONPATH="$DIR" "$VENV_UVICORN" backend.main:app --host 0.0.0.0 --port "$PORT" --reload
