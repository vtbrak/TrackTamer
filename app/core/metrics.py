"""
Behavioral metrics computed from a loaded tracking file.

Families of output:
  * summary_metrics()  -> one dict of numbers for the whole session
  * epm_metrics()      -> Elevated Plus Maze measures (added to the summary)
  * of_metrics()       -> Open Field measures (added to the summary)
  * epm_binned() / of_binned() -> the same test measures per time bin
  * binned_metrics()   -> a DataFrame with one row per time bin

Frame rate (fps) is supplied by the caller so frames can be converted to
seconds; everything time-based flows from that single number.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .loader import TrackingData
from .regions import frame_regions, match_polygons, resolve_roles


def held_states(labels: np.ndarray, min_frames: int) -> list[tuple[str, int]]:
    """Where the animal is, under the entry rule: [(label, first frame), ...],
    starting with the place it starts in.

    The current place only changes once the animal has stayed somewhere new
    for at least `min_frames` consecutive frames; shorter visits (boundary
    jitter) are ignored and don't break up a stay.
    """
    n = len(labels)
    if n == 0:
        return []
    # Run-length encode: start index and label of each run of equal labels.
    change = np.flatnonzero(labels[1:] != labels[:-1]) + 1
    starts = np.concatenate([[0], change])
    lengths = np.diff(np.concatenate([starts, [n]]))
    states = []
    for start, length in zip(starts, lengths):
        label = str(labels[start])
        if length < max(1, min_frames) or (states and label == states[-1][0]):
            continue
        states.append((label, int(start)))
    return states


def held_entries(roles: np.ndarray, min_frames: int) -> list[tuple[str, int]]:
    """Entries under the entry rule: [(role, first frame of the entry), ...].

    Same as held_states, minus the starting place: the animal was put there,
    so it isn't counted as an entry (its time still counts toward the
    region's total). Being in no region ("" role) counts as a place too, so
    returning from it is a new entry.
    """
    return held_states(roles, min_frames)[1:]


def spread_repeats(distance: np.ndarray, repeated: np.ndarray) -> np.ndarray:
    """Per-frame distance with each repeated frame's gap shared out, for
    speed. A repeated frame is a copy of the one before, so the animal seems
    to stand still for it and then cover two frames' distance in the next:
    zero speed, then double. The distance covered over a run of repeats and
    the real frame after it is spread evenly over those frames, which is the
    speed the animal actually had (user, 2026-11-11). The total is unchanged,
    and so is every frame with no repeat beside it."""
    out = np.asarray(distance, dtype=float).copy()
    repeated = np.asarray(repeated, dtype=bool)
    n = len(out)
    i = 0
    while i < n:
        if not repeated[i]:
            i += 1
            continue
        j = i
        while j < n and repeated[j]:
            j += 1
        end = min(j, n - 1)                 # the real frame after the run
        part = out[i:end + 1]
        if not np.isnan(part).any():
            out[i:end + 1] = part.sum() / len(part)
        i = j + 1
    return out


def carry_over_gaps(labels: np.ndarray, unreadable: np.ndarray) -> np.ndarray:
    """`labels` with each unreadable frame given the label of the last
    readable frame before it (frames before the first readable one take its
    label). Used for entries and crossings, so a gap of unreadable video
    frames neither creates nor breaks up an entry."""
    if not unreadable.any() or unreadable.all():
        return labels
    idx = np.where(unreadable, -1, np.arange(len(labels)))
    np.maximum.accumulate(idx, out=idx)
    idx[idx < 0] = int(np.argmax(~unreadable))
    return labels[idx]


def secs(frames: int, fps: float) -> float:
    """Frames -> seconds, as every time column shows it (2 decimals)."""
    return round(frames / fps, 2) if fps else float("nan")


def pct(part: float, whole: float) -> float:
    """A percentage formula of two shown values (1 decimal). Percentages are
    always worked out from the numbers in the table (e.g. % in a region =
    its time / the session length), so they can be checked from them."""
    return round(100.0 * part / whole, 1) if whole else float("nan")


def _distance_to_polygon(xs, ys, px: np.ndarray, py: np.ndarray) -> np.ndarray:
    """Distance from each point to the nearest edge of a polygon."""
    pts = np.column_stack([px, py]).astype(float)
    a_all = np.column_stack([xs, ys]).astype(float)
    best = np.full(len(pts), np.inf)
    for a, b in zip(a_all, np.roll(a_all, -1, axis=0)):
        ab = b - a
        length = float(ab @ ab)
        t = np.clip(((pts - a) @ ab) / length, 0, 1) if length else np.zeros(len(pts))
        nearest = a + t[:, None] * ab
        best = np.minimum(best, np.hypot(*(pts - nearest).T))
    return best


def _outside_mask(data: TrackingData) -> np.ndarray:
    """Frames with a tracked position that's in none of the file's regions."""
    inside = np.zeros(data.n_frames, dtype=bool)
    if not data.regions:      # no regions drawn (e.g. Object Recognition)
        return inside
    for r in data.regions:
        inside |= data.df[r].to_numpy(dtype=bool)
    return ~inside & data.df["X"].notna().to_numpy() & data.df["Y"].notna().to_numpy()


def _outside_targets(data: TrackingData, roles: dict[str, str], rows: np.ndarray):
    """For frames outside every region: the region each counts for, and how
    far outside it the point was (pixels). Open Field (a file with a
    periphery region): the periphery, since anything that isn't center is
    periphery. EPM and others: the nearest region, so a head dip over the
    side of an arm counts for that arm (user, 2026-11-05)."""
    polys = match_polygons(data)
    candidates = [r for r in polys if roles.get(r) == "periphery"] or list(polys)
    if not candidates or not len(rows):
        return np.array([""] * len(rows), dtype=object), np.full(len(rows), np.nan)
    x = data.df["X"].to_numpy(dtype=float)[rows]
    y = data.df["Y"].to_numpy(dtype=float)[rows]
    dist = np.stack([_distance_to_polygon(*polys[r], x, y) for r in candidates])
    nearest = dist.argmin(axis=0)
    return np.array(candidates, dtype=object)[nearest], dist[nearest, np.arange(len(rows))]


def region_labels(data: TrackingData, roles: dict[str, str] | None = None):
    """The one region per frame (`frame_regions`: shared frames count for the
    center). A tracked frame outside every region counts for the region it
    belongs to (`_outside_targets`). Unreadable frames are marked
    "unreadable" so they count toward no region's time. Returns (labels,
    unreadable mask, shared frames, {"a + b": frames})."""
    roles = roles if roles is not None else resolve_roles(data.regions, {})
    labels, shared_n, shared = frame_regions(data, roles)
    labels = labels.astype(object)
    out = np.flatnonzero(_outside_mask(data))
    if len(out):
        target, _dist = _outside_targets(data, roles, out)
        labels[out] = target
    bad = data.unreadable
    if bad.any():
        labels[bad] = "unreadable"
    return labels.astype(str), bad, shared_n, shared


def outside_events(data: TrackingData, roles: dict[str, str] | None = None,
                   fps: float = 20.0) -> list[dict]:
    """Every stretch of consecutive frames where the tracked point was outside
    all the drawn regions (jumps at the wall, head dips, or the tracker
    stuck on a dark spot or a reflection): first row (0-based), frames,
    seconds, the region those frames counted for, and the farthest the point
    got outside it (pixels). A long one may mean the tracker lost the animal
    and the video should be reviewed."""
    roles = roles if roles is not None else resolve_roles(data.regions, {})
    rows = np.flatnonzero(_outside_mask(data))
    if not len(rows):
        return []
    target, dist = _outside_targets(data, roles, rows)
    events = []
    for run in np.split(np.arange(len(rows)), np.flatnonzero(np.diff(rows) > 1) + 1):
        first = int(rows[run[0]])
        events.append({"row": first, "frames": len(run), "seconds": secs(len(run), fps),
                       "region": str(target[run[0]]),
                       "px_outside": round(float(np.nanmax(dist[run])), 1)})
    return events


def region_entry_starts(inside: np.ndarray, bad: np.ndarray, min_frames: int,
                        min_gap_frames: float = 0) -> list[int]:
    """Frames where entries into an area start, under the entry rule (stay
    at least `min_frames`; unreadable gaps carry the place before them).
    Starting inside isn't an entry. A return within `min_gap_frames` of
    leaving continues the same visit (Open Field center rule). Every entry
    count in the app (per region, per role, per bin) comes from here."""
    states = held_states(carry_over_gaps(np.where(inside, "in", "out"), bad), min_frames)
    starts, last_exit = [], None
    for k, (label, start) in enumerate(states):
        if label == "out":
            if k > 0:
                last_exit = start
            continue
        if k == 0:
            continue  # started inside: time counts, not an entry
        if last_exit is not None and start - last_exit < min_gap_frames:
            continue  # came back too soon: same visit
        starts.append(start)
    return starts


def _roles_and_gaps(data: TrackingData, roles: dict[str, str]):
    """Per-frame roles (each frame's region's role; shared frames count for
    the center), with unreadable frames marked "unreadable", the unreadable
    mask, and the roles with the place before each gap carried through it."""
    labels, bad, _n, _shared = region_labels(data, roles)
    lookup = {r: roles.get(r, "") for r in data.regions}
    lookup["unreadable"] = "unreadable"
    per_frame = np.array([lookup.get(x, "") for x in labels], dtype=object).astype(str) \
        if len(labels) else np.array([], dtype=str)
    return per_frame, bad, carry_over_gaps(per_frame, bad)


def _epm_events(data: TrackingData, roles: dict[str, str], min_entry_frames: int):
    """Per-frame roles and the session's entries [(role, start frame), ...].
    Entries are counted per region (`region_entry_starts`) and given their
    region's role, so role totals are exactly the sums of the region counts
    (e.g. closed entries = closed arm 1 + closed arm 2)."""
    per_frame, bad, _carried = _roles_and_gaps(data, roles)
    labels, _bad, _n, _shared = region_labels(data, roles)
    entries = []
    for r in data.regions:
        role = roles.get(r, "")
        if role in ("open_arm", "closed_arm", "center"):
            entries += [(role, f) for f in region_entry_starts(labels == r, bad, min_entry_frames)]
    groups = {k: [r for r in data.regions if roles.get(r) == k]
              for k in ("open_arm", "closed_arm", "center")}
    return per_frame, sorted(entries, key=lambda e: e[1]), labels, groups


def _role_sums(labels, groups, lo: int, hi: int, fps: float) -> tuple[dict, dict]:
    """Seconds and % of frames [lo, hi) per role, as the sums of the
    per-region values as displayed (rounded the same way), so a role total
    always equals its regions added up (e.g. closed = closed arm 1 + 2)."""
    seg = labels[lo:hi]
    length = secs(hi - lo, fps)
    times, pcts = {}, {}
    for k, regions in groups.items():
        region_secs = [secs(int(np.sum(seg == r)), fps) for r in regions]
        times[k] = round(sum(region_secs), 2)
        pcts[k] = round(sum(pct(t, length) for t in region_secs), 1)
    return times, pcts


def _epm_block(per_frame: np.ndarray, entries, lo: int, hi: int, fps: float,
               labels=None, groups=None) -> dict:
    """EPM measures for frames [lo, hi): times from those frames, entries that
    start in them. Used for the whole session and for each time bin. Times
    are the sums of the per-region times (`_role_sums`)."""
    nan = float("nan")
    counts = {k: sum(1 for r, f in entries if r == k and lo <= f < hi)
              for k in ("open_arm", "closed_arm", "center")}
    # Times are counted from the frames (sums of the per-region times);
    # everything after them is a formula of the shown values.
    t, _pcts = _role_sums(labels, groups, lo, hi, fps)
    o, c = t["open_arm"], t["closed_arm"]
    oe, ce = counts["open_arm"], counts["closed_arm"]
    pct_open = pct(o, o + c)
    pct_open_entries = pct(oe, oe + ce)
    return {
        "EPM_OpenArm_s": o,
        "EPM_ClosedArm_s": c,
        "EPM_Center_s": t["center"],
        # % of time on the arms that was on the open (closed) arms; the two add to 100.
        "EPM_PctOpenTime": pct_open,
        "EPM_PctClosedTime": round(100 - pct_open, 1) if not np.isnan(pct_open) else nan,
        "EPM_OpenEntries": oe,
        "EPM_ClosedEntries": ce,
        "EPM_CenterEntries": counts["center"],
        # % of arm entries that were into the open arms.
        "EPM_PctOpenEntries": pct_open_entries,
        # 1 - mean(% open time, % open entries) / 100; higher = more anxious.
        "EPM_AnxietyIndex": round(1 - (pct_open + pct_open_entries) / 200, 3),
        "EPM_ClosedOpenRatio": round(c / o, 3) if o else nan,
        "EPM_OpenClosedRatio": round(o / c, 3) if c else nan,
    }


def epm_metrics(
    data: TrackingData, roles: dict[str, str], fps: float = 20.0, min_entry_frames: int = 5
) -> dict:
    """Elevated Plus Maze measures for one file, as EPM_* summary columns.

    Times, % and entries are the sums of the per-region values (one region
    per frame; a frame the center shares counts for the center), so they
    always equal the per-region columns added up. Entries and latencies use
    the entry rule (`region_entry_starts`).
    Values that can't be computed (e.g. a ratio with no open-arm time, or a
    latency to an arm never entered) are left blank.
    """
    per_frame, entries, labels, groups = _epm_events(data, roles, min_entry_frames)
    n = len(per_frame)
    nan = float("nan")
    out = _epm_block(per_frame, entries, 0, n, fps, labels, groups)
    for key, role in (("Open", "open_arm"), ("Closed", "closed_arm"), ("Center", "center")):
        first = next((f for r, f in entries if r == role), None)
        out[f"EPM_Latency_{key}_s"] = round(first / fps, 2) if first is not None and fps else nan
    _secs, pct = _role_sums(labels, groups, 0, n, fps)
    for key, role in (("Open", "open_arm"), ("Closed", "closed_arm"), ("Center", "center")):
        out[f"EPM_PctSession_{key}"] = pct[role]
    return out


def epm_binned(
    data: TrackingData, roles: dict[str, str], fps: float = 20.0,
    bin_seconds: float = 60.0, min_entry_frames: int = 5,
) -> pd.DataFrame:
    """EPM measures per time bin (latency is session-only, so it's left out).

    Entries are found once over the whole session and each is counted in the
    bin where it starts, so bins add up to the session totals and a visit
    that spans a bin edge isn't split into two entries.
    """
    per_frame, entries, labels, groups = _epm_events(data, roles, min_entry_frames)
    rows = []
    for b, lo, hi in _bin_ranges(len(per_frame), fps, bin_seconds):
        row = {"Bin": b, **_epm_block(per_frame, entries, lo, hi, fps, labels, groups)}
        _secs, pct = _role_sums(labels, groups, lo, hi, fps)
        for key, role in (("Open", "open_arm"), ("Closed", "closed_arm"), ("Center", "center")):
            row[f"EPM_PctBin_{key}"] = pct[role]
        rows.append(row)
    return pd.DataFrame(rows)


def _bin_ranges(n: int, fps: float, bin_seconds: float):
    """(bin number, first frame, end frame) for each time bin. Every table of
    time bins is cut here.

    Bins are true to the clock (user, 2026-11-11): bin k starts at the frame
    nearest k x `bin_seconds`, so each bin's start and end times are what the
    table says, however long the session. When the frame rate times the bin
    length isn't a whole number of frames (9.84 fps x 60 s = 590.4), bins hold
    590 or 591 frames in turn instead of all holding 590 and drifting early
    (2.6 s by the end of a 65-minute session)."""
    if n == 0 or not fps or not bin_seconds or fps <= 0 or bin_seconds <= 0:
        return []
    ranges, lo, k = [], 0, 0
    while lo < n:
        k += 1
        hi = min(max(int(round(k * bin_seconds * fps)), lo + 1), n)   # never an empty bin
        ranges.append((k, lo, hi))
        lo = hi
    return ranges


def summary_metrics(data: TrackingData, fps: float = 20.0,
                    roles: dict[str, str] | None = None, min_entry_frames: int = 1,
                    min_gap_s: float = 0.0) -> dict:
    """Compute whole-session summary metrics for one file.

    Per-region time, % and entries use one region per frame (a frame on a
    border the center shares counts for the center only) and the same entry
    rule as the test measures (`min_entry_frames`; `min_gap_s` is the Open
    Field "same visit" gap), so they always agree with them. Returns a flat
    dict suitable for a one-row-per-file results table.
    """
    df = data.df
    n = len(df)
    duration_s = n / fps if fps else float("nan")
    bad = data.unreadable

    dist_cm = float(df["Distance_cm"].sum()) if "Distance_cm" in df else float("nan")
    dist_px = float(df["Distance_px"].sum()) if "Distance_px" in df else float("nan")

    out: dict = {
        "File": data.name,
        "Frames": n,
        "FPS": fps,
        "Duration_s": secs(n, fps),
        "Duration_min": round(secs(n, fps) / 60.0, 3),
        "TotalDistance_cm": round(dist_cm, 2),
        "TotalDistance_px": round(dist_px, 1),
        # Video frames that couldn't be read: no position, so they add no
        # time, distance or entries (always 0 for ezTrack's own files).
        "UnreadableFrames": int(bad.sum()),
    }
    if "Frame_Repeated" in df.columns:
        # Frames the recording app wrote as a copy of the one before.
        out["RepeatedFrames"] = int(data.repeated.sum())
    if "Frame_Filled" in df.columns:
        out["FilledFrames"] = int(df["Frame_Filled"].sum())

    # Mean speed over the whole session.
    # (Duration_s is the shown, rounded length: 0 for a file of a frame or two.)
    if out["Duration_s"] and not np.isnan(out["Duration_s"]) and not np.isnan(dist_cm):
        out["MeanSpeed_cm_s"] = round(round(dist_cm, 2) / out["Duration_s"], 3)

    # Time and % of the session in each region, one region per frame.
    labels, bad, shared_n, shared = region_labels(data, roles)
    for zone in data.regions:
        out[f"Time_{zone}_s"] = secs(int(np.sum(labels == zone)), fps)
        out[f"Percent_{zone}"] = pct(out[f"Time_{zone}_s"], out["Duration_s"])

    # Entries into each region, under the entry rule (the Open Field "same
    # visit" gap applies to center entries only, as in OF_CenterEntries).
    roles_used = roles if roles is not None else resolve_roles(data.regions, {})
    gap = min_gap_s * fps if fps else 0
    for zone in data.regions:
        zone_gap = gap if roles_used.get(zone) == "center" else 0
        out[f"Entries_{zone}"] = len(region_entry_starts(labels == zone, bad,
                                                         min_entry_frames, zone_gap))

    # Moves from one region (or none) to another between readable frames.
    if n:
        carried = carry_over_gaps(labels, bad)
        out["Region_transitions"] = int(np.sum(carried[1:] != carried[:-1]))
    # Stretches outside every drawn region (counted for their region above):
    # brief ones are jumps or head dips; long ones may be the tracker lost.
    events = outside_events(data, roles, fps)
    total = sum(e["frames"] for e in events)
    out["OutsideEvents"] = len(events)
    out["OutsideTime_s"] = secs(total, fps)
    out["OutsideEventMean_s"] = (round(out["OutsideTime_s"] / len(events), 3)
                                 if events else 0.0)
    out["OutsideEventMax_s"] = max((e["seconds"] for e in events), default=0.0)
    # Frames in two regions neither of which is the center (shouldn't happen:
    # only the center may share; reported so the regions can be fixed).
    out["SharedRegionFrames"] = shared_n
    out["SharedRegions"] = "; ".join(f"{k} ({v} frames)" for k, v in shared.items())

    # The tracking settings aren't repeated here (user, 2026-11-11): they are
    # on the export's Settings sheet and in the video's info file.
    return out


SIDES = ("left", "right", "top", "bottom")


def _polygon_edges(xs, ys) -> list[tuple[np.ndarray, np.ndarray, str]]:
    """The polygon's edges as (start point, outward unit normal, side), with
    repeated points dropped. Each edge's side comes from which way it faces:
    an edge facing -x is the "left" edge, facing up (smaller y) is "top", etc.
    """
    pts = np.column_stack([xs, ys]).astype(float)
    keep = [pts[0]]
    for p in pts[1:]:
        if np.hypot(*(p - keep[-1])) > 1e-9:
            keep.append(p)
    if len(keep) > 1 and np.hypot(*(keep[-1] - keep[0])) < 1e-9:
        keep.pop()  # closing point repeats the first
    pts = np.array(keep)
    # Shoelace sign: > 0 means counter-clockwise in these (x, y) coordinates.
    area2 = np.dot(pts[:, 0], np.roll(pts[:, 1], -1)) - np.dot(pts[:, 1], np.roll(pts[:, 0], -1))
    edges = []
    for a, b in zip(pts, np.roll(pts, -1, axis=0)):
        dx, dy = b - a
        length = np.hypot(dx, dy)
        if length < 1e-9:
            continue
        # Right-hand normal points outward for a counter-clockwise polygon.
        normal = np.array([dy, -dx]) / length
        if area2 < 0:
            normal = -normal
        if abs(normal[0]) >= abs(normal[1]):
            side = "left" if normal[0] < 0 else "right"
        else:
            side = "top" if normal[1] < 0 else "bottom"  # image coords: smaller y is up
        edges.append((a, normal, side))
    return edges


def side_labels(x: np.ndarray, y: np.ndarray, center_xs, center_ys) -> np.ndarray:
    """Which side of the arena each point is on, judged against the center
    ROI's own drawn edges (as drawn in the file, tilt and all; nothing is
    straightened or redrawn).

    Each edge line is extended across the arena. A point belongs to the side
    whose line it's furthest beyond: left of the drawn left edge = "left",
    above the drawn top edge = "top", and so on. In a corner area (beyond two
    lines) the larger distance wins, which splits the corner along its
    diagonal. Image coordinates: the top of the video is the top of the arena.

    A point inside the polygon gets the side of its nearest edge. That only
    matters for points the file's region columns say aren't in the center.
    """
    edges = _polygon_edges(center_xs, center_ys)
    pts = np.column_stack([x, y])
    # Signed distance past each edge line (positive = outside that edge).
    dist = np.stack([(pts - a) @ n for a, n, _ in edges])
    names = np.array([side for _, _, side in edges])
    return names[np.argmax(dist, axis=0)]


def _of_events(
    data: TrackingData, roles: dict[str, str], fps: float, min_entry_frames: int,
    min_between_entries_s: float, min_center_adjoining_s: float,
    speed_smoothing_frames: int,
) -> dict:
    """Everything the Open Field measures are built from, found once over the
    whole session: per-frame center/periphery and place (center or side),
    the frames where counted center entries start, and the counted crossings
    as (start frame, kind, average speed, peak speed). Kind is "lr", "tb", or
    "adj"; a crossing starts when the animal leaves side A for the center."""
    per_frame, bad, _carried = _roles_and_gaps(data, roles)
    in_center = per_frame == "center"
    ev = {"n": len(per_frame), "in_center": in_center,
          "periphery": per_frame == "periphery", "place": None,
          "center_entries": [], "crossings": []}

    # Center entries, with the debounce: re-entering within the minimum gap
    # after leaving continues the same visit.
    ev["center_entries"] = region_entry_starts(in_center, bad, min_entry_frames,
                                               min_between_entries_s * fps)

    # Sides from X/Y against this file's own drawn center ROI.
    centers = [r for r, k in roles.items() if k == "center"]
    polys = match_polygons(data)
    center_polys = [polys[r] for r in centers if r in polys]
    if not center_polys:
        return ev  # no center ROI to measure sides from

    def poly_area(p):
        xs, ys = np.asarray(p[0], float), np.asarray(p[1], float)
        return abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1)))

    cxs, cys = max(center_polys, key=poly_area)  # the main center ROI if several
    x = data.df["X"].to_numpy(dtype=float)
    y = data.df["Y"].to_numpy(dtype=float)
    sides = side_labels(x, y, cxs, cys)
    # Center frames are "center"; others take their side ("" if untracked).
    place = np.where(in_center, "center", np.where(np.isnan(x) | np.isnan(y), "", sides))
    ev["place"] = place

    # Crossings: side A -> center -> side B, using held places.
    states = held_states(carry_over_gaps(place, bad), min_entry_frames)
    speed = None
    if "Distance_cm" in data.df.columns:
        # Per-frame speed, smoothed so a one-frame tracking jump can't set the peak.
        distance = spread_repeats(data.df["Distance_cm"].to_numpy(dtype=float), data.repeated)
        speed = (pd.Series(distance) * fps).rolling(
            max(1, int(speed_smoothing_frames)), center=True, min_periods=1
        ).mean().to_numpy()
    opposite = {frozenset(("left", "right")): "lr", frozenset(("top", "bottom")): "tb"}
    for (a, _), (c, c_start), (b, b_start) in zip(states, states[1:], states[2:]):
        if c != "center" or a not in SIDES or b not in SIDES or a == b:
            continue
        kind = opposite.get(frozenset((a, b)))
        if kind is None:
            if (b_start - c_start) < min_center_adjoining_s * fps:
                continue  # adjoining sides, but cut through the center too briefly
            kind = "adj"
        avg = peak = float("nan")
        if speed is not None:
            # The traversal: from leaving side A to reaching side B.
            seg = speed[c_start:b_start + 1]
            seg = seg[~np.isnan(seg)]
            if len(seg):
                avg, peak = float(seg.mean()), float(seg.max())
        ev["crossings"].append((c_start, kind, avg, peak))
    return ev


def _of_block(ev: dict, lo: int, hi: int, fps: float) -> dict:
    """Open Field measures for frames [lo, hi): times from those frames, and
    entries/crossings that start in them. Used for the session and each bin."""
    nan = float("nan")
    n = hi - lo

    center = ev["in_center"][lo:hi]
    periphery = ev["periphery"][lo:hi]
    length = secs(n, fps)
    center_s = secs(int(center.sum()), fps)
    periphery_s = secs(int(periphery.sum()), fps)
    out = {
        "OF_Center_s": center_s,
        "OF_PctCenter": pct(center_s, length),
        "OF_Periphery_s": periphery_s,
        "OF_PctPeriphery": pct(periphery_s, length),
        "OF_CenterEntries": sum(1 for f in ev["center_entries"] if lo <= f < hi),
    }
    side_cols = [f"OF_{side.capitalize()}_s" for side in SIDES]
    crossing_cols = ["OF_Crossings_Total", "OF_Crossings_Opposite",
                     "OF_Crossings_LeftRight", "OF_Crossings_TopBottom",
                     "OF_Crossings_Adjoining", "OF_CrossingSpeed_Mean_cm_s",
                     "OF_CrossingSpeed_Peak_cm_s"]
    if ev["place"] is None:
        out.update({c: nan for c in side_cols + crossing_cols})
        return out
    place = ev["place"][lo:hi]
    for side, col in zip(SIDES, side_cols):
        out[col] = secs(int(np.sum(place == side)), fps)
    here = [c for c in ev["crossings"] if lo <= c[0] < hi]
    lr = sum(1 for c in here if c[1] == "lr")
    tb = sum(1 for c in here if c[1] == "tb")
    adj = sum(1 for c in here if c[1] == "adj")
    avgs = [c[2] for c in here if not np.isnan(c[2])]
    peaks = [c[3] for c in here if not np.isnan(c[3])]
    out.update({
        "OF_Crossings_Total": lr + tb + adj,
        "OF_Crossings_Opposite": lr + tb,
        "OF_Crossings_LeftRight": lr,
        "OF_Crossings_TopBottom": tb,
        "OF_Crossings_Adjoining": adj,
        "OF_CrossingSpeed_Mean_cm_s": round(float(np.mean(avgs)), 3) if avgs else nan,
        "OF_CrossingSpeed_Peak_cm_s": round(max(peaks), 3) if peaks else nan,
    })
    return out


def of_metrics(
    data: TrackingData,
    roles: dict[str, str],
    fps: float = 20.0,
    min_entry_frames: int = 5,
    min_between_entries_s: float = 1.0,
    min_center_adjoining_s: float = 0.5,
    speed_smoothing_frames: int = 5,
) -> dict:
    """Open Field measures for one file, as OF_* summary columns.

    Center membership comes from the file's region columns (center+periphery
    overlap counts as center). Sides come from X/Y judged against the file's
    own drawn center-ROI edges (`side_labels`). Entries use the entry rule; a
    return to the center within `min_between_entries_s` of leaving it is the
    same visit. A crossing is side A -> center -> side B (B != A): opposite
    sides always count; adjoining sides only if the center visit lasted at
    least `min_center_adjoining_s`. Crossing speeds use speed smoothed with a
    centered rolling mean over `speed_smoothing_frames` frames.
    """
    ev = _of_events(data, roles, fps, min_entry_frames, min_between_entries_s,
                    min_center_adjoining_s, speed_smoothing_frames)
    out = _of_block(ev, 0, ev["n"], fps)
    first = ev["center_entries"][0] if ev["center_entries"] else None
    latency = round(first / fps, 2) if first is not None and fps else float("nan")
    # Keep latency next to the entry count, as in the session summary before.
    ordered = {}
    for k, v in out.items():
        ordered[k] = v
        if k == "OF_CenterEntries":
            ordered["OF_Latency_Center_s"] = latency
    return ordered


def of_binned(
    data: TrackingData,
    roles: dict[str, str],
    fps: float = 20.0,
    bin_seconds: float = 60.0,
    min_entry_frames: int = 5,
    min_between_entries_s: float = 1.0,
    min_center_adjoining_s: float = 0.5,
    speed_smoothing_frames: int = 5,
) -> pd.DataFrame:
    """Open Field measures per time bin (latency is session-only).

    Entries and crossings are found once over the whole session and counted
    in the bin where they start, so bins add up to the session totals.
    Crossing speeds in a bin are for the crossings that start in it.
    """
    ev = _of_events(data, roles, fps, min_entry_frames, min_between_entries_s,
                    min_center_adjoining_s, speed_smoothing_frames)
    return pd.DataFrame([
        {"Bin": b, **_of_block(ev, lo, hi, fps)}
        for b, lo, hi in _bin_ranges(ev["n"], fps, bin_seconds)
    ])


def binned_metrics(
    data: TrackingData, fps: float = 20.0, bin_seconds: float = 60.0,
    roles: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Break the session into fixed time bins and summarize each bin.

    One row per bin: distance, mean speed, and time/percent in each zone
    (one region per frame, as in the summary).
    """
    df = data.df
    ranges = _bin_ranges(len(df), fps, bin_seconds)
    if not ranges:
        return pd.DataFrame()
    zones = data.regions
    bad = data.unreadable
    region = region_labels(data, roles)[0]
    distance = (df["Distance_cm"].to_numpy(dtype=float) if "Distance_cm" in df.columns
                else None)
    session_s = len(df) / fps
    rows = []
    for number, lo, hi in ranges:
        frames = hi - lo
        dist_cm = float(np.nansum(distance[lo:hi])) if distance is not None else float("nan")
        length = secs(frames, fps)
        row = {
            "Bin": number,
            "Start_s": round((number - 1) * bin_seconds, 2),
            "End_s": round(min(number * bin_seconds, session_s), 2),
            "Frames": frames,
            "Distance_cm": round(dist_cm, 2),
            "MeanSpeed_cm_s": round(round(dist_cm, 2) / length, 3) if length else float("nan"),
            "UnreadableFrames": int(bad[lo:hi].sum()),
        }
        for zone in zones:
            row[f"Time_{zone}_s"] = secs(int(np.sum(region[lo:hi] == zone)), fps)
            row[f"Percent_{zone}"] = pct(row[f"Time_{zone}_s"], length)
        rows.append(row)

    return pd.DataFrame(rows)


_BASICS = ("Duration_min", "TotalDistance_cm", "MeanSpeed_cm_s")

# The measures shown first, in this order: on screen by default ("Key
# measures") and at the start of the exported Summary and Time Bins (user's
# order, 2026-11-05). Time Bins use each bin's own % of the bin for the center.
KEY_MEASURES = {
    "Elevated Plus Maze": ["EPM_ClosedOpenRatio", "EPM_Center_s", "EPM_PctSession_Center",
                           "EPM_OpenArm_s", "EPM_PctOpenTime", "EPM_ClosedArm_s",
                           "EPM_PctClosedTime", "EPM_OpenEntries", "EPM_ClosedEntries"],
}
_BIN_KEY_RENAMES = {"EPM_PctSession_Center": "EPM_PctBin_Center"}


_OBJECT_PARTS = (("OR_Time_", "_s"), ("OR_Bouts_", ""), ("OR_Latency_", "_s"),
                 ("OR_ZoneTime_", "_s"), ("OR_ZoneVisits_", ""))
_OBJECT_TOTALS = ("OR_Bouts_Total", "OR_Latency_First_s")


def _object_of(column: str) -> str | None:
    """The object a per-object column is about ("object 1"), else None."""
    if column in _OBJECT_TOTALS:
        return None
    for prefix, suffix in _OBJECT_PARTS:
        if column.startswith(prefix) and column.endswith(suffix):
            return column[len(prefix): len(column) - len(suffix)]
    return None


def _object_keys(columns, bins: bool = False) -> list[str]:
    """Object Recognition's key measures (ROADMAP §15): the trial, the
    discrimination index, % preference and total, then for each object in
    turn its interaction time, bouts and latency, together (object names
    vary, so these are found by prefix)."""
    columns = list(columns)
    head = ([] if bins else ["OR_Phase", "OR_NovelObjects"]) + [
        "OR_DiscriminationIndex", "OR_PctPreference", "OR_Total_s"]
    parts = _OBJECT_PARTS[:2] if bins else _OBJECT_PARTS[:3]
    names = list(dict.fromkeys(_object_of(c) for c in columns if c.startswith("OR_Time_")
                               and _object_of(c)))
    per_object = [f"{prefix}{name}{suffix}" for name in names for prefix, suffix in parts]
    return [c for c in head if c in columns] + [c for c in per_object if c in columns]


def _topic(column: str):
    """What a column is about, for keeping one group's numbers together in
    an exported table: a region, an object, or a part of the test (the plus
    maze's center, open arms, closed arms and ratios; the open field's
    center, periphery, sides, crossings and crossing speed). None for a
    column that stands on its own."""
    for prefix in ("Time_", "Percent_", "Entries_"):
        if column.startswith(prefix):
            name = column[len(prefix):]
            return ("region", name[:-2] if prefix == "Time_" and name.endswith("_s") else name)
    if column.startswith("OR_"):
        name = _object_of(column)
        return ("object", name) if name else None
    if column.startswith("EPM_"):
        body = column[4:]
        for part, words in (("ratio", ("Ratio", "Index")), ("center", ("Center",)),
                            ("open", ("Open",)), ("closed", ("Closed",))):
            if any(w in body for w in words):
                return ("epm", part)
    if column.startswith("OF_"):
        body = column[3:]
        for part, words in (("speed", ("CrossingSpeed",)), ("crossings", ("Crossings",)),
                            ("center", ("Center",)), ("periphery", ("Periphery",)),
                            ("sides", ("Left", "Right", "Top", "Bottom"))):
            if any(w in body for w in words):
                return ("of", part)
    return None


def group_together(columns) -> list[str]:
    """`columns` with each group's columns side by side (user, 2026-11-12:
    "put the data for one group all together instead of spread out"): the
    first column of a group brings the rest of its group up beside it, in
    their own order. So a region's time, percent and entries sit together,
    as do an object's numbers and each part of a test."""
    columns = list(columns)
    topics = {c: _topic(c) for c in columns}
    out, placed = [], set()
    for c in columns:
        if c in placed:
            continue
        members = [c] if topics[c] is None else [x for x in columns if topics[x] == topics[c]]
        out += [m for m in members if m not in placed]
        placed.update(members)
    return out


def _asr_keys(columns) -> list[str]:
    """Acoustic startle's key measures: every startle measure, in the order
    the engine builds them, which keeps each group's numbers together (a
    trial type's count, mean and median; then per sound; per level; then
    prepulse inhibition and short-term habituation)."""
    return [c for c in columns if c.startswith("ASR_")]


def key_measures(test: str, bins: bool = False, columns=()) -> list[str]:
    """The test's key measures, in order (empty if it has none set).
    Object Recognition's and startle's depend on names in `columns`."""
    if test == "Object Recognition":
        return _object_keys(columns, bins)
    if test == "Acoustic Startle Response":
        return [] if bins else _asr_keys(columns)
    keys = KEY_MEASURES.get(test, [])
    return [_BIN_KEY_RENAMES.get(k, k) for k in keys] if bins else list(keys)


def order_summary(row: dict, test: str) -> dict:
    """The row as exported: File first, then the test's key measures in
    their order, then the rest, **with each group's columns brought together**
    (`group_together`): a key measure is followed by the other numbers about
    the same thing (the center's entries and latency beside its time, say)."""
    keys = [k for k in key_measures(test, columns=row) if k in row]
    first = [k for k in ("File",) if k in row] + keys
    order = group_together(first + [k for k in row if k not in first])
    return {k: row[k] for k in order}


def drop_duplicates(table, roles: dict[str, str], test: str):
    """Remove per-region columns that repeat a test measure exactly, keeping
    the test's own (user, 2026-11-05). EPM: the center region's Time_ /
    Percent_ / Entries_ repeat EPM_Center_s, EPM_PctSession_Center
    (EPM_PctBin_Center in bins) and EPM_CenterEntries. Open Field: the center's
    repeat OF_Center_s, OF_PctCenter, OF_CenterEntries, and the periphery's
    time / % repeat OF_Periphery_s, OF_PctPeriphery. Works on a summary row
    (dict) or a Time Bins table."""
    centers = [r for r, k in roles.items() if k == "center"]
    dupes = set()
    if test in ("Elevated Plus Maze", "Open Field") and len(centers) == 1:
        c = centers[0]  # (several centers: each one's numbers differ from the total)
        dupes |= {f"Time_{c}_s", f"Percent_{c}", f"Entries_{c}"}
    peripheries = [r for r, k in roles.items() if k == "periphery"]
    if test == "Open Field" and len(peripheries) == 1:
        p = peripheries[0]  # its entries have no OF_ twin, so they stay
        dupes |= {f"Time_{p}_s", f"Percent_{p}"}
    if isinstance(table, dict):
        return {k: v for k, v in table.items() if k not in dupes}
    return table.drop(columns=[d for d in dupes if d in table.columns])


def order_bins(bins: pd.DataFrame, test: str) -> pd.DataFrame:
    """Time Bins with Bin / Start_s / End_s first, then the key measures,
    then the rest, each group's columns together (`group_together`)."""
    keys = [k for k in key_measures(test, bins=True, columns=bins.columns)
            if k in bins.columns]
    if bins.empty:
        return bins
    first = [c for c in ("Bin", "Start_s", "End_s") if c in bins.columns] + keys
    return bins[group_together(first + [c for c in bins.columns if c not in first])]


_DETAILS = ("Frames", "FPS", "Duration_s", "TotalDistance_px", "UnreadableFrames",
            "FilledFrames")


def summary_column_groups(columns, test: str = "") -> dict[str, list[str]]:
    """Sort summary-table columns into display groups (File is not grouped).

    Groups: key (the test's key measures, in their set order; for a test
    without a set, its usual default view: basics and the test's measures),
    basics, test (the test's other EPM_/OF_ measures), zones (per-region
    time/%), entries, details.
    Anything unrecognized lands in details so a new column is never silently
    lost from the on-screen table.
    """
    groups: dict[str, list[str]] = {
        "key": [], "basics": [], "test": [], "zones": [], "entries": [], "details": []
    }
    columns = list(columns)
    keys = [k for k in key_measures(test, columns=columns) if k in columns]
    if not keys:  # e.g. Open Field: key = what it showed by default before
        keys = [c for c in columns if c in _BASICS] + [
            c for c in columns if c.startswith(("EPM_", "OF_", "OR_", "ASR_"))]
    groups["key"] = keys
    for c in columns:
        if c in ("File", "animal_id", "trial_day", "session_number") or c in keys:
            continue    # shown beside every row, not in a group
        if c in _BASICS:
            groups["basics"].append(c)
        elif c.startswith(("EPM_", "OF_", "OR_", "ASR_")):
            groups["test"].append(c)  # the chosen test's own measures
        elif c.startswith("Entries_") or c in ("Region_transitions", "ROI_transitions"):
            groups["entries"].append(c)
        elif (c.startswith("Time_") and c.endswith("_s")) or c.startswith("Percent_"):
            groups["zones"].append(c)  # per-region columns: center, ol, mid, ...
        else:
            groups["details"].append(c)  # _DETAILS + tracking settings + unknown
    return groups


def batch_summary(datasets: list[TrackingData], fps: float = 20.0) -> pd.DataFrame:
    """Summary metrics for many files, one row each, aligned into a table."""
    return pd.DataFrame([summary_metrics(d, fps=fps) for d in datasets])
