#!/usr/bin/env bash
# Launch the GeoTech Satellite app. Pass --demo to force offline sample data.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
[ "$1" = "--demo" ] && export GEOTECH_DEMO=1
echo "GeoTech Satellite -> http://127.0.0.1:8000"
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
