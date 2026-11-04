#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Do not run apt update here: unrelated broken third-party repositories can
# otherwise prevent this app's dependencies from installing.
sudo apt install -y python3 python3-xlib python3-pil xinput xcursorgen libxi6 libxcursor1

mkdir -p "$HOME/.local/bin"
install -m 755 "$ROOT/funni_cursors.py" "$HOME/.local/bin/funni-cursors"

echo
echo "Installed. Run: funni-cursors"
echo "If ~/.local/bin is not on PATH, run: ~/.local/bin/funni-cursors"
