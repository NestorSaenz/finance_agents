# Dev runner for the Safi backend with auto-reload.
# Usage:  .\run_dev.ps1
# Reruns the app automatically whenever a .py file under app/ changes,
# so you don't have to stop and start it after each edit.

Set-Location -Path $PSScriptRoot
uv run uvicorn app.main:app --port 8000 --reload --reload-dir app
