#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "\${BASH_SOURCE[0]}")" && pwd)"
sudo apt update
sudo apt install -y python3 python3-xlib xinput

mkdir -p "$HOME/.local/bin"
install -m 755 "$ROOT/funni_cursors.py" "$HOME/.local/bin/funni-cursors"
echo
echo "Installed. Run: funni-cursors"
echo "If ~/.local/bin is not on PATH, run: ~/.local/bin/funni-cursors"
