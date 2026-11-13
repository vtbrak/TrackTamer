"""Persistent settings (config.json) for Track Tamer.

Everything the user can tune lives here so it carries over between sessions.
Loading is forgiving: a missing, unreadable, or partly-invalid file falls back
to defaults key by key, so a bad config can never stop the app from starting.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile

# Everything the user sets up lives in ONE folder, app/config, so updating to
# a new version is: replace the program folder, then copy app/config across
# (user, 2026-11-12, the same for every app in the suite).
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(_APP_DIR, "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
# Where older versions kept the file: app/config.json (0.9.3 and before) and,
# before the files were gathered into "app", the project folder. A file found
# there is moved into app/config the first time it's needed.
_OLD_CONFIG_PATHS = (os.path.join(_APP_DIR, "config.json"),
                     os.path.join(os.path.dirname(_APP_DIR), "config.json"))


def _same_file_contents(a: str, b: str) -> bool:
    try:
        with open(a, "rb") as fa, open(b, "rb") as fb:
            return fa.read() == fb.read()
    except OSError:
        return False


def _free_name(path: str) -> str:
    """`path`, or `<name>_2<ending>`, `_3`, ... if that's taken."""
    base, ending = os.path.splitext(path)
    n, candidate = 2, path
    while os.path.exists(candidate):
        candidate = f"{base}_{n}{ending}"
        n += 1
    return candidate


def _adopt_old_config() -> None:
    """Move a settings file from an old place into app/config. A file is
    never replaced: if app/config already has one, an identical old copy is
    dropped and a different one is kept beside it as config_2.json (and so
    on), unread, so nothing the user set is lost. Never stops the app: on
    any error the old file stays where it is."""
    for old in _OLD_CONFIG_PATHS:
        try:
            if not os.path.isfile(old):
                continue
            os.makedirs(CONFIG_DIR, exist_ok=True)
            if not os.path.exists(CONFIG_PATH):
                os.replace(old, CONFIG_PATH)
            elif _same_file_contents(old, CONFIG_PATH):
                os.remove(old)
            else:
                os.replace(old, _free_name(CONFIG_PATH))
        except OSError:
            pass

DEFAULTS: dict = {
    "fps": 20.0,
    "bin_seconds": 60.0,
    "test_type": "Elevated Plus Maze",  # or "Open Field"
    # Entry rule: point must stay in a region this many frames to count.
    "min_entry_frames": 5,
    # Immobility: speed below threshold for at least min duration.
    "immobility_speed_cm_s": 2.0,
    "immobility_min_seconds": 1.0,
    # Open field.
    "min_seconds_between_entries": 1.0,
    "min_center_seconds_adjoining": 0.5,
    # Crossing speed is smoothed with a rolling mean over this many frames.
    "speed_smoothing_frames": 5,
    # Gap filling for unreadable video frames (ROADMAP §12, Stage 4): off by
    # default; when on, gaps up to this many frames get straight-line positions.
    "fill_gaps": False,
    "fill_gaps_max_frames": 5,
    # Video tracking settings shared by every video in a load (ROADMAP §12,
    # Stage 7): downsampling (1 = full size) and frames in each reference image.
    "video_downsample": 1.0,
    "reference_frames": 50,
    # Tracking settings (ezTrack's, with the user's notebook values), shared by
    # every video in a load and locked at the first Track (ROADMAP §12, Stage 3).
    "loc_thresh": 99.5,
    "track_method": "dark",
    "use_window": True,
    "window_size": 100,
    "window_weight": 0.9,
    # Last session length used per test, in minutes (setup step 1).
    "session_minutes": {"Elevated Plus Maze": 5.0, "Open Field": 60.0,
                        "Object Recognition": 10.0},
    # Last real length typed for the scale, per test, in cm (setup step 6).
    "scale_cm": {"Elevated Plus Maze": 75.0, "Open Field": 40.0},
    # Review tab: an outside-the-regions stretch at least this long (seconds)
    # is flagged as the tracker possibly lost. From the examples (2026-11-05):
    # Open Field jumps average 0.11-0.15 s (longest 0.35 s); EPM head dips
    # about 1.9 s (longest 2.3 s). Provisional; the user may change them.
    "review_cutoff_s": {"Elevated Plus Maze": 5.0, "Open Field": 1.0},
    # Object recognition (ROADMAP §15): zone around each object, out to this
    # far from its edge (cm). 4 cm from the user's first object trial
    # (2026-11-05): wide enough to catch every possible interaction, which
    # the experimenter then confirms or rejects. Never locks.
    "object_zone_cm": 4.0,
    # Acoustic startle (ROADMAP §13): pixel intensity change that counts as
    # movement (0-255; locks at the first Track), and the analysis windows.
    "asr_threshold": 15.0,
    "asr_startle_ms": 200.0,
    "asr_baseline_ms": 200.0,
    "asr_block_trials": 10,
    # Short-term habituation score: (mean of the first N responses - mean of
    # the last M) / mean of all (user, 2026-11-12).
    "asr_sth_first": 10,
    "asr_sth_last": 40,
    # Startle threshold (sessions that step through sound levels): a level
    # responds when its mean startle-window peak is above the mean of the
    # session's baseline-window peaks plus this many standard deviations.
    "asr_threshold_sd": 2.0,
    # Plus maze, open field and object videos: warn after Analyze when more
    # than this percent of a session's frames are ones the recording app
    # repeated (the camera fell behind). Provisional; the user may change it.
    "repeated_warn_pct": 5.0,
    # Plot style.
    "plot": {
        "point_size": 4.0,  # float so sizes like 2.5 survive a reload
        "point_color": "#1f77b4",
        "alpha": 0.8,
        "color_by_speed": True,
        "heatmap_bins": 50,
        "heatmap_cmap": "inferno",
        # Fill cells the animal never entered with one flat color (off = those
        # cells are transparent in a saved PNG).
        "heatmap_background": False,
        "heatmap_bg_color": "#cccccc",
        # Backgrounds (ROADMAP §12, Stage 6): Path "none" / "reference";
        # Heatmap "none" / "color" / "reference" (heatmap_background above
        # is kept in step with "color" for older configs).
        "path_background": "none",
        "heatmap_bg_mode": "none",
        # Region names drawn on the Path and Heatmap plots.
        "path_labels": True,
        "heatmap_labels": True,
    },
    # Which Summary-table column groups are shown on screen (export has all).
    # (Was "summary_groups" before the Key measures group; renamed so the new
    # default view, key measures only, reaches existing configs.)
    "summary_columns": {
        "key": True,   # the test's key measures (EPM: the user's order)
        "basics": False,
        "test": False,  # the test's other measures
        "zones": False,
        "entries": False,
        "details": False,
    },
    # ROI_location label -> role (open_arm, closed_arm, center, periphery).
    "region_roles": {},
}


# Settings kept as one number per test type; the GUI adds a test's entry the
# first time the user sets it.
_PER_TEST = ("session_minutes", "scale_cm", "review_cutoff_s")


def _merge(defaults: dict, loaded: dict) -> dict:
    """Overlay `loaded` on `defaults`, keeping only values of a matching type."""
    out = copy.deepcopy(defaults)
    for key, default in defaults.items():
        if key not in loaded:
            continue
        value = loaded[key]
        if isinstance(default, dict):
            if isinstance(value, dict):
                # region_roles starts empty, so its user-defined keys are kept as-is.
                out[key] = _merge(default, value) if default else dict(value)
                if key in _PER_TEST:
                    # One number per test: keep it for tests the defaults
                    # don't list too (e.g. Object Recognition's scale length).
                    for name, number in value.items():
                        if (name not in default and isinstance(number, (int, float))
                                and not isinstance(number, bool)):
                            out[key][name] = float(number)
        elif isinstance(default, bool):
            if isinstance(value, bool):
                out[key] = value
        elif isinstance(default, (int, float)):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out[key] = type(default)(value)
        elif isinstance(value, type(default)):
            out[key] = value
    return out


def load_config(path: str = CONFIG_PATH) -> dict:
    """Return settings from `path`, filling anything missing with defaults."""
    if path == CONFIG_PATH:
        _adopt_old_config()
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except (OSError, ValueError):
        return copy.deepcopy(DEFAULTS)
    if not isinstance(loaded, dict):
        return copy.deepcopy(DEFAULTS)
    return _merge(DEFAULTS, loaded)


def save_config(config: dict, path: str = CONFIG_PATH) -> None:
    """Write settings atomically so a crash mid-save can't corrupt the file."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)       # app/config on a first run
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".config-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
