"""Region-role mapping: what each region in a file *means* for the test.

Files name their regions differently (EPM files use short codes like ol, or,
ct, cb, mid; open-field files use center, peripheral). Each region name is
auto-classified into a role; the user can override any of them, and overrides
are saved in config.json under "region_roles".
"""

from __future__ import annotations

import re

import numpy as np
from matplotlib.path import Path

from .loader import TrackingData, parse_roi_coordinates

TEST_TYPES = ["Elevated Plus Maze", "Open Field", "Object Recognition",
              "Acoustic Startle Response"]

# Role keys in display order, with their on-screen names. "" = not yet assigned.
ROLE_LABELS = {
    "open_arm": "Open arm",
    "closed_arm": "Closed arm",
    "center": "Center",
    "periphery": "Periphery",
    "ignore": "Ignore",
    "": "Unassigned",
}

# Whole-word keywords, checked before the short-code rules so "center" isn't
# mistaken for a closed-arm code starting with "c".
_KEYWORDS = [
    ("open_arm", ("open",)),
    ("closed_arm", ("closed", "close")),
    ("center", ("center", "centre", "mid", "middle")),
    ("periphery", ("peripheral", "periphery", "peri", "outer", "wall", "edge")),
]

# EPM short codes: o + side (ol, or, ot, ob, o1...) and c + side (ct, cb, cl, cr...).
_OPEN_CODE = re.compile(r"^o[a-z0-9]{0,2}$")
_CLOSED_CODE = re.compile(r"^c[a-z0-9]{0,2}$")


def auto_role(name: str) -> str:
    """Best-guess role for a region name, or "" if it can't be guessed."""
    n = name.strip().lower()
    words = [w for w in re.split(r"[^a-z0-9]+", n) if w]
    for role, keys in _KEYWORDS:
        if any(w.startswith(k) for w in words for k in keys):
            return role
    if _OPEN_CODE.match(n):
        return "open_arm"
    if _CLOSED_CODE.match(n):
        return "closed_arm"
    return ""


def resolve_roles(regions, overrides: dict) -> dict[str, str]:
    """Role for each region: the saved override if valid, else the auto guess."""
    roles = {}
    for r in regions:
        saved = overrides.get(r)
        roles[r] = saved if saved in ROLE_LABELS else auto_role(r)
    return roles


def check_roles(test_type: str, roles: dict[str, str]) -> list[str]:
    """Problems with this mapping for the chosen test; empty list = all good."""
    counts = {k: list(roles.values()).count(k) for k in ROLE_LABELS}
    problems = []
    if counts[""]:
        unassigned = ", ".join(r for r, k in roles.items() if k == "")
        problems.append(f"Unassigned: {unassigned}")
    if test_type == "Elevated Plus Maze":
        if not counts["open_arm"]:
            problems.append("No open arm assigned")
        if not counts["closed_arm"]:
            problems.append("No closed arm assigned")
        if not counts["center"]:
            problems.append("No center assigned")
    elif test_type == "Open Field":
        if not counts["center"]:
            problems.append("No center assigned")
    return problems


def _role_masks(data: TrackingData, roles: dict[str, str]) -> dict[str, np.ndarray]:
    """{role: per-frame bool} — True where any region with that role is True."""
    n = data.n_frames
    masks = {k: np.zeros(n, dtype=bool) for k in ROLE_LABELS if k}
    for region in data.regions:
        role = roles.get(region, "")
        if role:
            masks[role] |= data.df[region].to_numpy(dtype=bool)
    return masks


def frame_roles(data: TrackingData, roles: dict[str, str]) -> np.ndarray:
    """One role per frame ("" = in no assigned region).

    Where regions overlap, center wins: a frame in an arm *and* the middle
    (EPM or_mid, ct_mid, ...) counts as center, and so does a frame in an open
    and a closed arm at once, since arms only meet at the center. A frame in
    center and periphery (an open-field ROI error, see
    center_periphery_overlap) also counts as center.
    """
    m = _role_masks(data, roles)
    return np.select(
        [m["center"], m["open_arm"] & m["closed_arm"], m["open_arm"],
         m["closed_arm"], m["periphery"]],
        ["center", "center", "open_arm", "closed_arm", "periphery"],
        default="",
    )


def frame_regions(data: TrackingData, roles: dict[str, str]):
    """The one region the animal is in on each frame, by name ("" = none).

    A frame in several regions counts for the **center** when one of them is
    the center (a point on a border the center shares, or a drawn overlap;
    user's rule, 2026-11-05). The center is the only region that may share
    with others: a frame in two non-center regions goes to the first of them
    (file order) and is reported, as (labels, shared frame count,
    {"a + b": frames}).

    Every per-region and per-role measure is built from these labels, so the
    same quantity never comes out as two different numbers.
    """
    n = data.n_frames
    labels = np.full(n, "", dtype=object)
    centers = [r for r in data.regions if roles.get(r) == "center"]
    others = [r for r in data.regions if r not in centers]
    inside = {r: data.df[r].to_numpy(dtype=bool) for r in data.regions}
    in_center = np.zeros(n, dtype=bool)
    for r in centers:
        labels[inside[r] & ~in_center] = r
        in_center |= inside[r]
    taken = in_center.copy()
    shared: dict[str, int] = {}
    for i, r in enumerate(others):
        mine = inside[r] & ~in_center
        for later in others[i + 1:]:
            both = int((mine & inside[later]).sum())
            if both:
                shared[f"{r} + {later}"] = both
        labels[mine & ~taken] = r
        taken |= mine
    hits = sum((inside[r].astype(int) for r in others), np.zeros(n, dtype=int))
    count = int(((hits > 1) & ~in_center).sum())
    return labels.astype(str), count, shared


def center_periphery_overlap(data: TrackingData, roles: dict[str, str]) -> int:
    """Frames marked as both center and periphery. Center and periphery should
    never overlap, so any count above zero means the file's ROIs are wrong
    (e.g. the periphery ROI was drawn around the whole arena)."""
    m = _role_masks(data, roles)
    return int((m["center"] & m["periphery"]).sum())


def match_polygons(data: TrackingData) -> dict[str, tuple[list, list]]:
    """Pair each region column with its ROI polygon ({region: (xs, ys)}).

    The file doesn't promise polygons are listed in the same order as region
    columns, so each pairing is chosen by agreement: how often "point is inside
    polygon j" equals "region column r is True". Best-agreeing pairs are taken
    first. Regions with no polygon (or no usable data) are left out.
    """
    df = data.df
    if "ROI_coordinates" not in df.columns or not len(df) or not data.regions:
        return {}
    rois = parse_roi_coordinates(df["ROI_coordinates"].iloc[0])
    polys = [
        (xs, ys) for xs, ys in zip(rois.get("xs", []), rois.get("ys", []))
        if len(xs) >= 3 and len(xs) == len(ys)
    ]
    if not polys:
        return {}

    xy = df[["X", "Y"]].to_numpy(dtype=float)
    ok = ~np.isnan(xy).any(axis=1)
    if not ok.any():
        return {}
    xy = xy[ok]
    inside = [Path(np.column_stack(p)).contains_points(xy) for p in polys]

    scores = []
    for r in data.regions:
        flags = df[r].to_numpy(dtype=bool)[ok]
        for j, ins in enumerate(inside):
            scores.append((float(np.mean(ins == flags)), r, j))

    matched: dict[str, tuple[list, list]] = {}
    used: set[int] = set()
    for _, r, j in sorted(scores, reverse=True):
        if r not in matched and j not in used:
            matched[r] = polys[j]
            used.add(j)
    return matched


def describe_roles(roles: dict[str, str]) -> str:
    """Short tally, e.g. '2 Open arm, 2 Closed arm, 1 Center'."""
    parts = []
    for key, label in ROLE_LABELS.items():
        n = list(roles.values()).count(key)
        if n and key not in ("", "ignore"):
            parts.append(f"{n} {label}")
    return ", ".join(parts) or "nothing assigned"
