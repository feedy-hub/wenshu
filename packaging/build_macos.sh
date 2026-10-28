#!/bin/sh
# Run on macOS to produce a self-contained app from a native Python runtime.
set -eu
root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
python3 -m venv "$root/.build-venv"
"$root/.build-venv/bin/python" -m pip install --upgrade pip
"$root/.build-venv/bin/python" -m pip install -r "$root/requirements.txt" pyinstaller
"$root/.build-venv/bin/pyinstaller" --noconfirm --clean --windowed \
  --name "文枢" --icon "$root/packaging/Wenshu.icns" \
  --add-data "$root/static:static" --add-data "$root/samples:samples" \
  --distpath "$root/dist-macos" --workpath "$root/build-macos" \
  "$root/launch.py"
printf 'Built: %s\n' "$root/dist-macos/文枢.app"
