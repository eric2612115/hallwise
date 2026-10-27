#!/bin/sh
# Start the Hallwise server; the badge app connects to ws://<this Mac's address>:8790 with the server key.
#
# The server key: HALLWISE_TOKEN in ../.env (git-ignored, mode 600). If there is none, this script makes one
# (32 random bytes, URL-safe base64) and appends it to ../.env without printing it; copy it from there into the
# badge app's settings. The browser dashboard asks for it once and keeps it in a cookie. The server will not start
# without a key; HALLWISE_INSECURE=1 runs it open, for offline experiments only.
#
# Where it listens: HALLWISE_BIND, default 0.0.0.0 (every interface, as before), so anyone on the same Wi-Fi can
# reach the port and only the key keeps them out. Safer: the Mac's Tailscale IP (HALLWISE_BIND=100.x.y.z), or
# 127.0.0.1 when only this Mac uses it. The server answers only to localhost, this Mac's addresses (every
# interface, Tailscale's included while it is up) and name, and HALLWISE_HOSTS (comma-separated: a MagicDNS name).
#
# Files: umask 077 keeps what the server writes (recordings, faces, reports) readable by this user only. Data
# written before that was readable by every account on the Mac; fix it once with: chmod -R go-rwx server/data
#
# Reads MODEL_API_KEY from ../.env. HALLWISE_ASR=fake runs offline (and is the only mode that honours a
# hello's fake_script).
cd "$(dirname "$0")" || exit 1
umask 077
if [ -z "${HALLWISE_TOKEN:-}" ] && ! grep -q '^HALLWISE_TOKEN=.' ../.env 2>/dev/null; then
  token=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))' 2>/dev/null) \
    || token=$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n') || exit 1
  [ -n "$token" ] || exit 1
  printf '\nHALLWISE_TOKEN=%s\n' "$token" >> ../.env || exit 1
  unset token
  echo "run.sh: made a server key: HALLWISE_TOKEN in $(cd .. && pwd)/.env (not printed)"
fi
[ -f ../.env ] && chmod 600 ../.env
set -a
[ -f ../.env ] && . ../.env
set +a
export HALLWISE_ASR="${HALLWISE_ASR:-meta}"
export HALLWISE_BIND="${HALLWISE_BIND:-0.0.0.0}"
# HALLWISE_LANGUAGE_BIAS=en,fr,ja would tell the transcriber which languages to expect when the badge names none.
# Off: in rehearsal it cost Siddharth's name and still did not bring back Kenji's Japanese (see recording.py).
# HALLWISE_LEVELER=off sends the recogniser the mix as it came.
exec uv run uvicorn hallwise.app:app --host "$HALLWISE_BIND" --port "${PORT:-8790}"
