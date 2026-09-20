$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
$env:PYTHONPATH='api'
python scripts/seed_local.py
python api/local_server.py
