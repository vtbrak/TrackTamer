#!/bin/bash
# Double-click uninstaller for Track Tamer (macOS, Anaconda).
# Removes only the conda environment; the program folder and your data,
# results and settings are left untouched.
# (Windows equivalent: "Uninstall Track Tamer.bat")

# Move to the program's "app" folder beside this script (handles spaces in the path).
cd "$(dirname "$0")/app" || { echo "The program's \"app\" folder is missing. Download Track Tamer again."; read -r -p "Press Return to close this window." _; exit 1; }
. ./find_conda.sh

finish() {
    echo
    read -r -p "Press Return to close this window." _
    exit "$1"
}

if ! find_conda; then
    echo "Anaconda wasn't found, so there's no environment to remove."
    finish 1
fi
if ! env_exists; then
    echo "The \"$ENV_NAME\" environment isn't installed. Nothing to remove."
    finish 0
fi

read -r -p "Remove the \"$ENV_NAME\" environment? Your files are kept. [y/N] " answer
case "$answer" in
    [yY]*) ;;
    *) echo "Nothing removed."; finish 0 ;;
esac

if conda remove -n "$ENV_NAME" --all -y; then
    echo
    echo "Removed. Run \"Install Track Tamer.command\" to install it again."
    finish 0
fi
echo
echo "Removal failed. See the messages above."
finish 1
