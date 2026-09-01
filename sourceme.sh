#!/bin/bash
# sourceme.sh — Activate the project environment and load .env variables
# Usage: source sourceme.sh   (must be sourced, not executed)
#
# First-time setup:
#   uv venv              — create the virtual environment
#   uv sync              — install all dependencies from pyproject.toml

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHONPATH="$PROJECT_DIR/src:$PYTHONPATH"

export PROJECT_DIR
echo "PROJECT_DIR: $PROJECT_DIR"
echo "PYTHONPATH: $PYTHONPATH"

cd "$PROJECT_DIR" || exit

# Activate virtual environment
if [ -f ".venv/Scripts/activate" ]; then
    # Windows Git Bash path
    source ".venv/Scripts/activate"
elif [ -f ".venv/bin/activate" ]; then
    # Linux / macOS path
    source ".venv/bin/activate"
else
    echo "❌  Virtual environment not found. Run: uv venv"
    uv venv
fi


# Load .env variables into shell (skips comments and empty lines)
if [ -f ".env" ]; then
    while read -r line; do
        # Strip carriage return (Windows line endings)
        line="${line//$'\r'/}"
        # Skip comments and empty lines
        [[ "$line" =~ ^\s*# ]] && continue
        [[ -z "${line// }" ]] && continue
        # Split on first = only
        key="${line%%=*}"
        value="${line#*=}"
        # Strip surrounding quotes from value
        value="${value#\"}" ; value="${value%\"}"
        value="${value#\'}" ; value="${value%\'}"
        # Skip if key is empty or contains spaces (malformed)
        [[ -z "$key" || "$key" == *" "* ]] && continue
        export "$key=$value"
    done < .env
    echo "✅  .env loaded"
else
    echo "⚠️  .env file not found. Copy .env.example to .env and fill in your keys."
fi

echo "✅  Virtual environment activated: $(python --version)"
echo "📁  Working directory: $(pwd)"

# Sync dependencies from pyproject.toml
echo "🔄  Syncing dependencies with uv..."
uv sync --all-extras
echo "✅  Dependencies synced"
