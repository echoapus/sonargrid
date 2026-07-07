#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PREFIX="${SONARGRID_PREFIX:-/opt/sonargrid}"
VENV_DIR="$PREFIX/.venv"
HOST="${SONARGRID_HOST:-127.0.0.1}"
PORT="${SONARGRID_PORT:-5000}"
SERVICE="${SONARGRID_SERVICE:-1}"
SERVICE_FILE="/etc/systemd/system/sonargrid.service"

cd "$ROOT_DIR"

mkdir -p "$PREFIX/sonargrid"
cp "$ROOT_DIR/app.py" "$ROOT_DIR/schema.sql" "$ROOT_DIR/requirements.txt" "$PREFIX/"
cp "$ROOT_DIR"/sonargrid/*.py "$PREFIX/sonargrid/"

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$PREFIX/requirements.txt"

cd "$PREFIX"
"$VENV_DIR/bin/python" app.py init-db

cat > "$PREFIX/run-sonargrid.sh" <<EOF
#!/usr/bin/env sh
set -eu
cd "$PREFIX"
exec "$VENV_DIR/bin/python" app.py serve --host "$HOST" --port "$PORT" --worker
EOF
chmod +x "$PREFIX/run-sonargrid.sh"

if [ "$SERVICE" = "1" ] && [ "$(id -u)" = "0" ] && command -v systemctl >/dev/null 2>&1; then
  cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=SonarGrid NMS
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$PREFIX
ExecStart=$PREFIX/run-sonargrid.sh
Restart=on-failure
RestartSec=5
Environment=SONARGRID_HOST=$HOST
Environment=SONARGRID_PORT=$PORT

[Install]
WantedBy=multi-user.target
EOF
  if systemctl daemon-reload && systemctl enable sonargrid.service && systemctl restart sonargrid.service; then
    SERVICE_STATUS="systemd service enabled and started: sonargrid.service"
  else
    SERVICE_STATUS="systemd unit written, but service could not be started; use: systemctl status sonargrid.service"
  fi
else
  SERVICE_STATUS="systemd service not installed; use run script"
  if [ "$(id -u)" = "0" ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    chown -R "$SUDO_USER":"$SUDO_USER" "$PREFIX"
  fi
fi

printf '%s\n' "SonarGrid installed."
printf '%s\n' "Install dir: $PREFIX"
printf '%s\n' "Run: $PREFIX/run-sonargrid.sh"
printf '%s\n' "$SERVICE_STATUS"
printf '%s\n' "URL: http://$HOST:$PORT/"
printf '%s\n' "Optional SNMP v2c: SONARGRID_SNMP_COMMUNITY=public $PREFIX/run-sonargrid.sh"
