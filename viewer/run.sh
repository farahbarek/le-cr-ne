#!/usr/bin/env bash
# Lance l'interface web (macOS / Linux). À exécuter depuis n'importe où.
set -e
cd "$(dirname "$0")/.."

if [ ! -d venv ]; then
  echo "Création de l'environnement Python (première fois seulement)..."
  python3 -m venv venv
  ./venv/bin/pip install --upgrade pip
  ./venv/bin/pip install -r requirements.txt
  ./venv/bin/pip install -r viewer/requirements.txt
fi

URL="http://127.0.0.1:5000"
( sleep 2; (command -v xdg-open >/dev/null && xdg-open "$URL") || (command -v open >/dev/null && open "$URL") || true ) &
./venv/bin/python viewer/app.py
