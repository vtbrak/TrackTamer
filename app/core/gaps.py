"""Optional gap filling for unreadable video frames (off by default).

A short run of unreadable frames between two readable ones gets positions on
a straight line between the positions just before and after it. Longer gaps,
and gaps at the start or end of the session, stay blank. The saved
_LocationOutput.csv is never changed: filling makes an in-memory copy for
analysis, and filled rows keep Frame_Unreadable (plus Frame_Filled) so they
can always be identified.
"""

from __future__ import annotations

import dataclasses

import numpy as np
from matplotlib.path import Path

from .loader import TrackingData
from .regions import match_polygons


def fill_gaps(data: TrackingData, max_frames: int) -> TrackingData:
    """A copy of `data` with gaps of up to `max_frames` unreadable frames
    filled. Region columns for filled frames come from the filled position
    against the file's own ROIs; distances next to filled frames are
    recomputed from the positions."""
    bad = data.unreadable
    df = data.df.copy()
    df["Frame_Filled"] = False
    if not bad.any() or max_frames < 1:
        return dataclasses.replace(data, df=df)

    n = len(df)
    fill = np.zeros(n, dtype=bool)
    i = 0
    while i < n:
        if not bad[i]:
            i += 1
            continue
        j = i
        while j < n and bad[j]:
            j += 1
        # Run i..j-1 is unreadable; fill only if it's short and has readable
        # frames on both sides.
        if i > 0 and j < n and (j - i) <= max_frames:
            fill[i:j] = True
        i = j
    if not fill.any():
        return dataclasses.replace(data, df=df)

    frames = np.arange(n)
    good = ~bad
    for col in ("X", "Y"):
        values = df[col].to_numpy(dtype=float, copy=True)
        values[fill] = np.interp(frames[fill], frames[good], values[good])
        df[col] = values
    df.loc[fill, "Frame_Filled"] = True

    _fill_regions(data, df, fill)
    _fill_distances(df, fill)
    return dataclasses.replace(data, df=df)


def _fill_regions(data: TrackingData, df, fill: np.ndarray) -> None:
    polys = match_polygons(data)
    pts = df.loc[fill, ["X", "Y"]].to_numpy(dtype=float)
    inside = {}
    for region in data.regions:
        if region in polys:
            xs, ys = polys[region]
            inside[region] = Path(np.column_stack([xs, ys])).contains_points(pts)
        else:
            inside[region] = np.zeros(len(pts), dtype=bool)
    # A region drawn around another that the file never counts at the same
    # time (this app's Open Field periphery = outline minus center) excludes
    # the inner one here too.
    for outer in data.regions:
        for inner in data.regions:
            if outer == inner or outer not in polys or inner not in polys:
                continue
            both = (df[outer].to_numpy(dtype=bool) & df[inner].to_numpy(dtype=bool)).any()
            if not both and _contains(polys[outer], polys[inner]):
                inside[outer] = inside[outer] & ~inside[inner]
    for region, values in inside.items():
        df.loc[fill, region] = values
    if "ROI_location" in df.columns:
        labels = ["_".join(r for r in data.regions if inside[r][k]) or "non_roi"
                  for k in range(len(pts))]
        df.loc[fill, "ROI_location"] = labels


def _contains(outer, inner) -> bool:
    path = Path(np.column_stack(outer))
    return bool(path.contains_points(np.column_stack(inner)).all())


def _fill_distances(df, fill: np.ndarray) -> None:
    """Recompute steps into and out of filled frames (they were blank)."""
    x = df["X"].to_numpy(dtype=float)
    y = df["Y"].to_numpy(dtype=float)
    step = np.concatenate([[0.0], np.hypot(np.diff(x), np.diff(y))])
    touched = fill | np.concatenate([[False], fill[:-1]])  # filled + the frame after
    if "Distance_px" in df.columns:
        df.loc[touched, "Distance_px"] = step[touched]
    if "Distance_cm" in df.columns:
        if "Scale_cm_per_px" in df.columns and df["Scale_cm_per_px"].notna().any():
            factor = float(df["Scale_cm_per_px"].dropna().iloc[0])
        else:
            px, cm = df["Distance_px"], df["Distance_cm"]
            ok = px.notna() & cm.notna() & (px > 0)
            factor = float(cm[ok].sum() / px[ok].sum()) if ok.any() else np.nan
        df.loc[touched, "Distance_cm"] = step[touched] * factor
