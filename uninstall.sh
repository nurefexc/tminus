#!/usr/bin/env bash
# Stop tminus and remove its user units without touching calendar data.
set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNITS=(tminus.service tminus-sweep.service tminus.timer)

PURGE=0
case "${1:-}" in
  "") ;;
  --purge) PURGE=1 ;;
  -h|--help)
    echo "usage: $0 [--purge]"
    echo "  --purge  also remove runtime state and the event log"
    exit 0
    ;;
  *)
    echo "unknown option: $1" >&2
    exit 2
    ;;
esac

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user disable --now tminus.service tminus.timer 2>/dev/null || true
  systemctl --user stop tminus-sweep.service 2>/dev/null || true
fi

for unit in "${UNITS[@]}"; do
  link="$UNIT_DIR/$unit"
  if [[ -L "$link" ]]; then
    target=$(readlink -f "$link" 2>/dev/null || true)
    if [[ "$target" == "$HERE"/systemd/$unit ]]; then
      rm -f "$link"
      echo "removed $link"
    else
      echo "kept $link (points elsewhere: $target)" >&2
    fi
  elif [[ -e "$link" ]]; then
    echo "kept $link (not a symlink)" >&2
  fi
done

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload
fi

if [[ $PURGE -eq 1 ]]; then
  rm -rf "${XDG_RUNTIME_DIR:-/tmp}/tminus" \
         "${XDG_STATE_HOME:-$HOME/.local/state}/tminus"
  echo "removed runtime state and event log"
else
  echo "runtime state and event log kept (use --purge to remove)"
fi
