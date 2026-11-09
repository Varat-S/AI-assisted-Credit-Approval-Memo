#!/usr/bin/env sh
# One-command launcher for the credit memo web app (macOS / Linux).
# Usage: ./run.sh [--port 8001] [--skip-install] [--no-browser]
set -eu
cd "$(dirname "$0")"

PORT=8001
INSTALL=1
OPEN="--open"
while [ $# -gt 0 ]; do
    case "$1" in
        --port) PORT="$2"; shift 2 ;;
        --skip-install) INSTALL=0; shift ;;
        --no-browser) OPEN=""; shift ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

# uv must never run from inside .venv: `uv sync` may need to rebuild that folder.
UV_BIN="$(command -v uv 2>/dev/null || true)"
case "$UV_BIN" in "$(pwd)/.venv/"*) UV_BIN="" ;; esac
if [ -n "$UV_BIN" ]; then
    UV="$UV_BIN"
else
    if ! python3 -m uv --version >/dev/null 2>&1; then
        echo "Installing uv..."
        python3 -m pip install --user "uv==0.12.23"
    fi
    UV="python3 -m uv"
fi

if [ "$INSTALL" = 1 ]; then
    echo "Installing locked dependencies into .venv..."
    $UV sync --locked --inexact --extra vertex --extra pdf
fi

if [ ! -f .env ]; then
    cp .env.example .env
    cat <<'EOF'

Created .env from .env.example. Before the first run, edit .env and set:
  SEC_USER_AGENT        your name and email (used to download 10-Ks from SEC EDGAR)
  GOOGLE_CLOUD_PROJECT  your Google Cloud project (or VERTEX_API_KEY instead)
  VERTEX_MODEL_NARROW   a Gemini model your project can use
For Vertex ADC also run: gcloud auth application-default login
Then run ./run.sh again.
EOF
    exit 1
fi

if ! $UV run --no-sync python -m app.doctor; then
    echo "Setup check failed (see above). The app will start, but new analyses will not run until it passes."
fi

echo ""
echo "Credit memo web app: http://127.0.0.1:$PORT/analysis/new   (Ctrl+C to stop)"
echo "Outputs: output/browser_demo/   Database: data/browser_demo.db"
# shellcheck disable=SC2086
exec $UV run --no-sync python -m app.preview --port "$PORT" $OPEN
