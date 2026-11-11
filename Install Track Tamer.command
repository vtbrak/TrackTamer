#!/bin/bash
# Double-click installer for Track Tamer (macOS, Anaconda).
# Builds the conda environment from environment.yml, or updates it to match
# if it's already installed, so it's safe to run again after an update.
# (Windows equivalent: "Install Track Tamer.bat")

# Move to the program's "app" folder beside this script (handles spaces in the path).
cd "$(dirname "$0")/app" || { echo "The program's \"app\" folder is missing. Download Track Tamer again."; read -r -p "Press Return to close this window." _; exit 1; }
. ./find_conda.sh

finish() {
    echo
    read -r -p "Press Return to close this window." _
    exit "$1"
}

if ! find_conda; then
    echo "Anaconda wasn't found on this computer."
    echo "Install Anaconda or Miniconda (https://www.anaconda.com/download),"
    echo "then double-click this installer again."
    finish 1
fi
echo "Using conda at $CONDA_BASE"
echo

if env_exists; then
    echo "Updating the \"$ENV_NAME\" environment (this can take a few minutes)…"
    conda env update -n "$ENV_NAME" -f environment.yml --prune
else
    echo "Creating the \"$ENV_NAME\" environment (this can take a few minutes)…"
    conda env create -f environment.yml
fi
if [ $? -ne 0 ]; then
    echo
    echo "Install failed. See the messages above."
    finish 1
fi

conda activate "$ENV_NAME" || { echo "Couldn't activate \"$ENV_NAME\"."; finish 1; }
if ! python -c "import pandas, numpy, matplotlib, openpyxl, tkinter, tkinterdnd2, cv2, PIL"; then
    echo
    echo "The environment was built but a package won't load. See the messages above."
    finish 1
fi
# Remember which environment.yml this was built from (see the Open launcher).
cp environment.yml "$CONDA_PREFIX/$STAMP_NAME"

echo
echo "Done. Double-click \"Open Track Tamer.command\" to start the app."
finish 0
