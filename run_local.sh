#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHONPATH=api python3 scripts/seed_local.py
PYTHONPATH=api python3 api/local_server.py
