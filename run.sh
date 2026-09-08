#!/usr/bin/env bash
# ==============================================================================
# Script de inicio para App LTI (Servidor Web y API FastAPI)
# Compatible con Entorno Local (bobbasystem) y Servidor Remoto (iacdi)
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Prioridad: Entorno virtual local del proyecto
if [ -f "$DIR/venv/bin/python3" ] && [ -f "$DIR/venv/bin/uvicorn" ]; then
    VENV_PYTHON="$DIR/venv/bin/python3"
    VENV_UVICORN="$DIR/venv/bin/uvicorn"
# 2. Fallback: Entorno virtual de desarrollo bobbasystem
elif [ -f "/home/bobbasystem/Desarrollos/Carga Data SM/venv/bin/python3" ]; then
    VENV_PYTHON="/home/bobbasystem/Desarrollos/Carga Data SM/venv/bin/python3"
    VENV_UVICORN="/home/bobbasystem/Desarrollos/Carga Data SM/venv/bin/uvicorn"
# 3. Fallback: Python y Uvicorn del sistema
else
    echo "[INFO] Usando python3 y uvicorn del sistema..."
    VENV_PYTHON="python3"
    VENV_UVICORN="uvicorn"
fi

echo "=================================================="
echo "Iniciando App LTI - Portal de Líderes TI"
echo "Directorio : $DIR"
echo "Python     : $VENV_PYTHON"
echo "Uvicorn    : $VENV_UVICORN"
echo "=================================================="

# Poblar usuarios y tablas si es necesario
echo "[MSSQL] Verificando tablas de autenticación y usuarios..."
PYTHONPATH="$DIR" "$VENV_PYTHON" -m backend.seed_users

# Iniciar servidor Uvicorn
PORT=8000
echo "[WEB] Servidor disponible en: http://0.0.0.0:$PORT"
echo "Presione Ctrl+C para detener el servidor."

PYTHONPATH="$DIR" "$VENV_UVICORN" backend.main:app --host 0.0.0.0 --port "$PORT" --reload
