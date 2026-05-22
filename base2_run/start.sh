#!/usr/bin/env bash
# One-command startup for the base2 sweep viewer.
#
#   ./start.sh             — install everything (if needed) and launch on 127.0.0.1:8765
#   ./start.sh --port 8080 — pass any flag through to server.py
#
# Installs uv automatically if not found, then uses it to create a venv and
# install deps. On first run this takes ~10–15 seconds; subsequent runs are instant.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/webapp"

VENV_DIR=".venv"

# ── 1. Ensure uv is available ────────────────────────────────────────────────
if ! command -v uv >/dev/null 2>&1; then
    echo "[start] uv not found — installing via the official installer…"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # The installer adds uv to ~/.local/bin (or ~/.cargo/bin on some systems).
    # Source common shell init files so the new PATH takes effect immediately.
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv >/dev/null 2>&1; then
        echo "[start] ERROR: uv still not found after install. Try opening a new terminal and re-running."
        exit 1
    fi
    echo "[start] uv installed: $(uv --version)"
fi

# ── 2. Create venv with uv-managed Python (once) ────────────────────────────
if [[ ! -d "$VENV_DIR" ]]; then
    echo "[start] creating virtual environment…"
    uv venv --python 3.11 "$VENV_DIR"
fi

# ── 3. Install / sync deps (once, or when requirements.txt changes) ──────────
DEPS_STAMP="$VENV_DIR/.deps_installed"
REQ="requirements.txt"
if [[ ! -f "$DEPS_STAMP" ]] || [[ "$REQ" -nt "$DEPS_STAMP" ]]; then
    echo "[start] installing dependencies…"
    uv pip install --quiet -r "$REQ"
    touch "$DEPS_STAMP"
fi

# ── 4. Launch ────────────────────────────────────────────────────────────────
echo "[start] launching viewer — open http://127.0.0.1:8765"
exec uv run --python "$VENV_DIR/bin/python" server.py "$@"
