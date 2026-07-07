#!/usr/bin/env sh
set -eu

PREFIX="${SONARGRID_PREFIX:-/opt/sonargrid}"
PURGE="${1:-}"
SERVICE_FILE="/etc/systemd/system/sonargrid.service"

if [ "$(id -u)" = "0" ] && command -v systemctl >/dev/null 2>&1; then
  systemctl stop sonargrid.service 2>/dev/null || true
  systemctl disable sonargrid.service 2>/dev/null || true
  rm -f "$SERVICE_FILE"
  systemctl daemon-reload
fi

if [ "$PURGE" = "--purge" ]; then
  rm -rf "$PREFIX"
  printf '%s\n' "SonarGrid uninstalled from $PREFIX and data purged."
else
  rm -rf "$PREFIX/.venv" "$PREFIX/run-sonargrid.sh" "$PREFIX/__pycache__" "$PREFIX/sonargrid/__pycache__"
  rm -f "$PREFIX/app.py" "$PREFIX/schema.sql" "$PREFIX/requirements.txt"
  rm -rf "$PREFIX/sonargrid"
  printf '%s\n' "SonarGrid uninstalled from $PREFIX. Data kept in $PREFIX/sonargrid.db."
  printf '%s\n' "Run './uninstall.sh --purge' to remove SQLite data too."
fi
