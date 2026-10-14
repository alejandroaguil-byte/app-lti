#!/bin/bash
# Vuelve App LTI a como estaba antes de install-app-lti.sh: sin servicio
# systemd y con el proceso uvicorn del desarrollador (bobbasystem) en
# 0.0.0.0:8000 con --reload. Se lanza como unidad transitoria para que no
# dependa de una sesión abierta (no sobrevive a un reinicio del servidor,
# igual que antes).
#   sudo bash /home/iacdi/Desarrollos/app-lti/deploy/rollback-app-lti.sh
set -uo pipefail

APP=/home/iacdi/Desarrollos/app-lti
UNIT=app-lti.service

[ "$(id -u)" -eq 0 ] || { echo "Ejecutar con sudo." >&2; exit 1; }

systemctl disable --now "$UNIT" 2>/dev/null
rm -f "/etc/systemd/system/$UNIT"
systemctl daemon-reload

systemctl stop app-lti-manual 2>/dev/null
systemctl reset-failed app-lti-manual 2>/dev/null
systemd-run --quiet --uid=bobbasystem --unit=app-lti-manual \
    -p WorkingDirectory="$APP" \
    "$APP/venv/bin/uvicorn" backend.main:app --host 0.0.0.0 --port 8000 --reload

for _ in $(seq 1 30); do
    curl -fsS -o /dev/null --max-time 3 http://127.0.0.1:8000/api/health && { echo "App LTI de vuelta como antes (proceso de bobbasystem, unidad app-lti-manual)."; exit 0; }
    sleep 1
done
echo "ERROR: App LTI no responde en el puerto 8000. Revisar: journalctl -u app-lti-manual" >&2
exit 1
