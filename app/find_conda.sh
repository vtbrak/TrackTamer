# Finds Anaconda/Miniconda for the Mac launchers (sourced, not run).
#
# After `. ./find_conda.sh`:
#   ENV_NAME      the environment name from environment.yml
#   STAMP_NAME    copy of environment.yml kept inside the installed env, so
#                 the Open launcher can tell when the file has changed since
#   find_conda    returns 0 and sets CONDA_BASE once conda is found and
#                 `conda activate` works in this script; returns 1 otherwise
#   env_exists    returns 0 if the environment is installed

ENV_NAME="$(sed -n 's/^name:[[:space:]]*//p' environment.yml | head -n 1)"
STAMP_NAME="track-tamer-environment.yml"

find_conda() {
    local candidates=() base
    # Already known to this shell: CONDA_EXE is set by conda itself, and
    # `conda` is on PATH when the user ran `conda init`.
    if [ -n "$CONDA_EXE" ]; then
        candidates+=("$(dirname "$(dirname "$CONDA_EXE")")")
    fi
    if command -v conda >/dev/null 2>&1; then
        base="$(conda info --base 2>/dev/null)"
        [ -n "$base" ] && candidates+=("$base")
    fi
    # Otherwise, the usual install folders (just-me and all-users installs,
    # Intel and Apple Silicon, Homebrew casks).
    candidates+=(
        "$HOME/anaconda3" "$HOME/miniconda3" "$HOME/miniforge3" "$HOME/mambaforge"
        "$HOME/opt/anaconda3" "$HOME/opt/miniconda3"
        "/opt/anaconda3" "/opt/miniconda3" "/opt/miniforge3"
        "/opt/homebrew/anaconda3" "/opt/homebrew/miniconda3"
        "/opt/homebrew/Caskroom/miniconda/base" "/opt/homebrew/Caskroom/miniforge/base"
        "/usr/local/anaconda3" "/usr/local/miniconda3"
        "/usr/local/Caskroom/miniconda/base" "/usr/local/Caskroom/miniforge/base"
    )
    for base in "${candidates[@]}"; do
        if [ -f "$base/etc/profile.d/conda.sh" ]; then
            CONDA_BASE="$base"
            # Defines the `conda` shell function, which `conda activate` needs.
            . "$base/etc/profile.d/conda.sh"
            return 0
        fi
    done
    return 1
}

env_exists() {
    conda env list 2>/dev/null | awk -v n="$ENV_NAME" '$1 == n { found = 1 } END { exit !found }'
}
