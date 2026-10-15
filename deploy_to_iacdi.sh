#!/usr/bin/env bash
# ==============================================================================
# Script de Sincronización y Despliegue hacia Servidor IACDI vía Tailscale/SSH
# ==============================================================================

set -e

REMOTE_HOST="iacdi"
REMOTE_IP="100.82.24.75"
REMOTE_USER="bobbasystem"
REMOTE_DIR="/home/iacdi/Desarrollos/app-lti"

LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=================================================="
echo "Sincronizando App LTI hacia Servidor IACDI"
echo "Destino: $REMOTE_USER@$REMOTE_HOST ($REMOTE_IP):$REMOTE_DIR"
echo "=================================================="

# Sincronización con rsync excluyendo venv, git, cache y .env remoto
rsync -rtvz --no-o --no-g --omit-dir-times --progress \
    --exclude 'venv/' \
    --exclude '.git/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.pytest_cache/' \
    --exclude '.env' \
    --exclude '.DS_Store' \
    --exclude '.engram/' \
    --exclude 'odd/' \
    "$LOCAL_DIR/" "$REMOTE_HOST:$REMOTE_DIR/"

echo ""
echo "[INFO] Código sincronizado exitosamente."
echo "[INFO] Si el servicio app-lti.service está corriendo con --reload, los cambios ya están activos."
echo "[INFO] Para verificar logs remotos: ssh $REMOTE_HOST 'journalctl --user -u app-lti -n 20 --no-pager'"
echo "=================================================="
