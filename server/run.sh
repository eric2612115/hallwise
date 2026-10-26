#!/bin/sh
# Start the Hallwise server on the local network; the badge app connects to ws://<this Mac's address>:8790.
# Reads MODEL_API_KEY from ../.env. HALLWISE_ASR=fake runs offline.
cd "$(dirname "$0")" || exit 1
set -a
[ -f ../.env ] && . ../.env
set +a
export HALLWISE_ASR="${HALLWISE_ASR:-meta}"
# HALLWISE_LANGUAGE_BIAS=en,fr,ja would tell the transcriber which languages to expect when the badge names none.
# Off: in rehearsal it cost Siddharth's name and still did not bring back Kenji's Japanese (see recording.py).
# HALLWISE_LEVELER=off sends the recogniser the mix as it came.
exec uv run uvicorn hallwise.app:app --host 0.0.0.0 --port "${PORT:-8790}"
