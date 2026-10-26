#!/bin/sh
# Start the Hallwise server on the local network; the badge app connects to ws://<this Mac's address>:8787.
# Reads MODEL_API_KEY from ../.env. HALLWISE_ASR=fake runs offline.
cd "$(dirname "$0")" || exit 1
set -a
[ -f ../.env ] && . ../.env
set +a
export HALLWISE_ASR="${HALLWISE_ASR:-meta}"
exec uv run uvicorn hallwise.app:app --host 0.0.0.0 --port "${PORT:-8787}"
