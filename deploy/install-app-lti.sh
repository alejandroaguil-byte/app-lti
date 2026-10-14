#!/bin/bash
# Pasa App LTI de "proceso manual en 0.0.0.0:8000 con --reload" a servicio
# systemd (iacdi, 127.0.0.1:8000, sin --reload, con hardening).
#   sudo bash /home/iacdi/Desarrollos/app-lti/deploy/install-app-lti.sh
# Revertir: sudo bash /home/iacdi/Desarrollos/app-lti/deploy/rollback-app-lti.sh
#
# 1. Pruebas previas COMO iacdi y con el MISMO sandbox del servicio: que la app
#    importe y que Chromium (Playwright) arranque. Si algo falla, aborta sin
#    tocar nada (el proceso manual sigue corriendo).
# 2. Instala y habilita la unidad.
# 3. Detiene el proceso manual y arranca el servicio (corte de unos segundos).
# 4. Si el servicio no responde, vuelve solo a levantar el proceso manual.
set -euo pipefail

APP=/home/iacdi/Desarrollos/app-lti
UNIT=app-lti.service
SRC_UNIT=$APP/deploy/$UNIT
DEST_UNIT=/etc/systemd/system/$UNIT
MANUAL_PATTERN='/home/iacdi/Desarrollos/app-lti/venv/bin/uvicorn backend.main:app'

[ "$(id -u)" -eq 0 ] || { echo "Ejecutar con sudo." >&2; exit 1; }

props=()
while IFS= read -r line; do props+=(-p "$line"); done < <(
    grep -E '^(NoNewPrivileges|Protect|Private|Restrict)' "$SRC_UNIT"
)
run_as_service() {
    systemd-run --quiet --wait --pipe --collect --uid=iacdi -p WorkingDirectory="$APP" "${props[@]}" "$@"
}

echo "== 1/4 Pruebas previas (como iacdi, con el sandbox del servicio)"
echo "   - importar la app"
if ! run_as_service "$APP/venv/bin/python3" -c "import backend.main" >/dev/null; then
    echo "ABORTADO: la app no importa como iacdi. Nada cambió." >&2; exit 1
fi
echo "   - arrancar Chromium (Playwright)"
if ! run_as_service "$APP/venv/bin/python3" -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'])
    b.close()
"; then
    cat >&2 <<EOF
ABORTADO: Chromium no arranca como iacdi. Nada cambió.
Probablemente iacdi no tiene los navegadores de Playwright descargados. Instalar con:
  sudo -u iacdi $APP/venv/bin/playwright install chromium
y volver a correr este script.
EOF
    exit 1
fi
echo "   OK"

echo "== 2/4 Instalando unidad $DEST_UNIT"
install -o root -g root -m 0644 "$SRC_UNIT" "$DEST_UNIT"
systemctl daemon-reload
systemctl enable "$UNIT" >/dev/null

echo "== 3/4 Deteniendo proceso manual y arrancando el servicio"
pkill -f "$MANUAL_PATTERN" || true
for _ in $(seq 1 20); do
    ss -ltn '( sport = :8000 )' | grep -q LISTEN || break
    sleep 0.5
done
if ss -ltn '( sport = :8000 )' | grep -q LISTEN; then
    echo "El puerto 8000 sigue ocupado; forzando cierre del proceso manual."
    pkill -9 -f "$MANUAL_PATTERN" || true
    sleep 1
fi
systemctl start "$UNIT"

echo "== 4/4 Verificando"
ok=0
for _ in $(seq 1 30); do
    if curl -fsS -o /dev/null --max-time 3 http://127.0.0.1:8000/api/health; then ok=1; break; fi
    sleep 1
done
if [ "$ok" -ne 1 ]; then
    echo "ERROR: el servicio no responde. Volviendo al proceso manual..." >&2
    journalctl -u "$UNIT" -n 20 --no-pager -o cat >&2 || true
    bash "$APP/deploy/rollback-app-lti.sh"
    exit 1
fi
systemctl show "$UNIT" -p ActiveState -p MainPID -p User | sed 's/^/   /'
echo "   Escucha en:"; ss -ltn '( sport = :8000 )' | sed 's/^/   /'
echo "   Vía nginx (/app-lti/): $(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1/app-lti/)"
echo "Listo."
