"""
Loading and validation of LocationOutput tracking CSVs.

Each CSV holds one row per video frame for a single tracked animal/video.
This module reads the file, coerces column types, and exposes the analysis
settings that are constant across the file.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from . import info_file

# Columns we expect in a LocationOutput file. The program still runs if some
# optional ones are missing, but these are the ones the analyses rely on.
REQUIRED_COLUMNS = ["Frame", "X", "Y"]

# Columns that describe the tracking run and are identical on every row.
SETTINGS_COLUMNS = [
    "Location_Thresh",
    "Use_Window",
    "Window_Weight",
    "Window_Size",
    "Start_Frame",
    # Added by this app's own tracking (not in ezTrack's files).
    "Method",
    "Downsample",
    "Crop",
    "Reference_Frames",
    "Exclusion_Shapes",
    "Scale_px",
    "Scale_cm",
    "Scale_cm_per_px",
    "Video_FPS",
    # Object recognition (ROADMAP §15): the objects drawn, and the trial.
    "Objects",
    "Trial_Day",
    "Trial_Phase",
]

# True/False columns that are not regions (Use_Window is a tracking setting;
# Frame_Unreadable marks video frames that couldn't be read, Frame_Filled
# those given a position by gap filling, and Frame_Repeated those the
# recording app wrote as a copy of the frame before because the camera was
# late).
NON_REGION_BOOL_COLUMNS = {"ROI_transition", "Use_Window", "Frame_Unreadable", "Frame_Filled",
                           "Frame_Repeated"}

_BOOL_TEXT = {"true": True, "false": False, "1": True, "0": False}


@dataclass(eq=False)   # two loads of a file are different objects (and tables can't be compared with ==)
class TrackingData:
    """A single loaded tracking file, ready for analysis."""

    path: str
    df: pd.DataFrame
    settings: dict[str, Any]
    # Per-region True/False columns, in file order (e.g. center, peripheral for
    # open field; ol, or, ct, cb, mid for EPM). Their order matches the ROI
    # polygons in ROI_coordinates.
    regions: list[str] = field(default_factory=list)
    # Set when the file has just been tracked: frames of the session the
    # video couldn't give at the end (see `tracking.TrackResult`).
    missing_at_end: int = 0

    @property
    def name(self) -> str:
        """Short display name (the source video if present, else the file)."""
        if "File" in self.df.columns and len(self.df):
            return str(self.df["File"].iloc[0])
        return os.path.basename(self.path)

    @property
    def n_frames(self) -> int:
        return len(self.df)

    @property
    def repeated(self) -> np.ndarray:
        """Per-frame True where the recording app repeated the frame before
        (the camera hadn't delivered a new one in time). All False for a
        file that doesn't say."""
        if "Frame_Repeated" not in self.df.columns:
            return np.zeros(len(self.df), dtype=bool)
        return self.df["Frame_Repeated"].to_numpy(dtype=bool)

    @property
    def unreadable(self) -> np.ndarray:
        """Per-frame True where the video frame couldn't be read and has no
        position (gap-filled frames count as readable). Files without a
        Frame_Unreadable column (e.g. ezTrack's own) are all readable."""
        n = len(self.df)
        if "Frame_Unreadable" not in self.df.columns:
            return np.zeros(n, dtype=bool)
        bad = self.df["Frame_Unreadable"].to_numpy(dtype=bool)
        if "Frame_Filled" in self.df.columns:
            bad = bad & ~self.df["Frame_Filled"].to_numpy(dtype=bool)
        return bad


def _to_bool(series: pd.Series) -> pd.Series:
    """Coerce a 'True'/'False'/1/0 column to real booleans."""
    if series.dtype == bool:
        return series
    return series.astype(str).str.strip().str.lower().map(_BOOL_TEXT).fillna(False)


def _is_bool_column(series: pd.Series) -> bool:
    """True if every non-empty value reads as True/False."""
    if series.dtype == bool:
        return True
    values = series.dropna()
    if values.empty:
        return False
    return values.astype(str).str.strip().str.lower().isin(["true", "false"]).all()


def load_csv(path: str) -> TrackingData:
    """Read one LocationOutput CSV into a TrackingData object.

    Raises ValueError if the file is missing required position columns.
    """
    df = pd.read_csv(path, low_memory=False)  # blank region values mix types
    # A file tracked in this app keeps only its per-frame columns; what is
    # the same on every row (the video's name, the tracking settings, the
    # region outlines) is in the video's info file, and goes back in here so
    # the rest of the app sees the table as it always was.
    for column, value in info_file.saved_columns(path).items():
        if column not in df.columns:
            df[column] = np.nan if value is None else value

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"{os.path.basename(path)} is missing required column(s): "
            f"{', '.join(missing)}"
        )

    # Numeric position / distance columns.
    for col in ["Frame", "X", "Y", "Distance_px", "Distance_cm"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Pull the constant settings off the first row (before bool coercion, so
    # they show exactly as written in the file).
    settings: dict[str, Any] = {}
    for col in SETTINGS_COLUMNS:
        if col in df.columns and len(df):
            settings[col] = df[col].iloc[0]

    # Region flags: any True/False column that isn't a known non-region one.
    regions: list[str] = []
    for col in df.columns:
        if col in SETTINGS_COLUMNS or col in REQUIRED_COLUMNS:
            continue
        if col in NON_REGION_BOOL_COLUMNS:
            df[col] = _to_bool(df[col])
        elif _is_bool_column(df[col]):
            df[col] = _to_bool(df[col])
            regions.append(col)

    return TrackingData(path=path, df=df, settings=settings, regions=regions)


def parse_roi_coordinates(raw: str) -> dict[str, list]:
    """Parse the ROI_coordinates dict-string into {'xs': [...], 'ys': [...]}.

    The source stores a Python-literal dict as text; ast.literal_eval reads it
    safely (no code execution). Returns empty lists on any failure.
    """
    if not isinstance(raw, str) or not raw.strip():
        return {"xs": [], "ys": []}
    try:
        parsed = ast.literal_eval(raw)
        if isinstance(parsed, dict):
            return {"xs": parsed.get("xs", []), "ys": parsed.get("ys", [])}
    except (ValueError, SyntaxError):
        pass
    return {"xs": [], "ys": []}
