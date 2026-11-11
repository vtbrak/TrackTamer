#!/bin/bash
# Double-click launcher for Track Tamer GUI (macOS).
# Uses the Anaconda environment from "Install Track Tamer.command" when
# it's installed. On computers without Anaconda it falls back to the
# program's own virtual environment (app/.venv), creating it on first run.

# Move to the program's "app" folder beside this script (handles spaces in the path).
cd "$(dirname "$0")/app" || { echo "The program's \"app\" folder is missing. Download Track Tamer again."; read -r -p "Press Return to close this window." _; exit 1; }
. ./find_conda.sh

if find_conda; then
    if env_exists && conda activate "$ENV_NAME"; then
        if ! cmp -s environment.yml "$CONDA_PREFIX/$STAMP_NAME"; then
            echo "Note: the program's package list has changed since it was installed."
            echo "Double-click \"Install Track Tamer.command\" to update."
            echo
        fi
        exec python gui.py
    fi
    if [ ! -x ".venv/bin/python" ]; then
        echo "Track Tamer isn't installed yet."
        echo "Double-click \"Install Track Tamer.command\" first."
        echo
        read -r -p "Press Return to close this window." _
        exit 1
    fi
fi

# No Anaconda environment: use the virtual environment instead.
VENV=".venv"
PY="$VENV/bin/python"

# First-run setup: build the venv and install dependencies.
if [ ! -x "$PY" ]; then
    echo "First run — setting up the environment (this can take a minute)…"
    python3 -m venv "$VENV" || { echo "Could not create virtual environment."; exit 1; }
    "$PY" -m pip install -r requirements.txt || { echo "Dependency install failed."; exit 1; }
fi

# Launch the app.
exec "$PY" gui.py
