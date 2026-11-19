#!/usr/bin/env bash
# Wire the tminus units into the user's systemd and start them.
set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

if ! command -v systemctl >/dev/null 2>&1; then
  echo "tminus: systemd is required for the timer" >&2
  exit 1
fi

mkdir -p "$UNIT_DIR"
for unit in tminus.service tminus-sweep.service tminus.timer; do
  ln -sfn "$HERE/systemd/$unit" "$UNIT_DIR/$unit"
  echo "linked $UNIT_DIR/$unit"
done

systemctl --user daemon-reload
systemctl --user enable --now tminus.service tminus.timer
echo
systemctl --user --no-pager status tminus.service tminus.timer --no-block || true
