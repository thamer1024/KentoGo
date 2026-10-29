#!/bin/bash
# Make KentoGo.app on macOS (see README.md). Run it in the KentoGo folder:
#
#   bash packaging/macos/build.sh
#
# It makes dist/KentoGo.app (open it, or move it to the Applications folder) and dist/KentoGo-macos.zip.

set -euo pipefail
cd "$(dirname "$0")/../.."

# The libraries, with those of the AI commentary and PyInstaller.
uv sync --extra ai --group build

uv run --no-sync pyinstaller --noconfirm --clean --distpath dist --workpath build packaging/macos/kentogo.spec

# ditto keeps the links and the attributes inside the app, as the Finder's "Compress" does.
ditto -c -k --keepParent dist/KentoGo.app dist/KentoGo-macos.zip
echo "Made dist/KentoGo.app and dist/KentoGo-macos.zip"
