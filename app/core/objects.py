"""Object recognition (GUI-free; ROADMAP §15, user 2026-11-05).

Novel object recognition / spatial object recognition scoring, semi-automated:
- Each object is a circle (center and radius) drawn in setup step 5, marked
  Familiar, Novel or Moved. Tracking writes the circles (in the tracking
  file's own prepared-frame pixels) and the trial's day and phase into the
  tracking file (`Objects`, `Trial_Day`, `Trial_Phase` columns).
- A **zone** surrounds each object, out to a set distance from its edge (the
  Zone distance box, in cm; pixels when the file has no scale). Zones are
  worked out from X/Y when analyzing, so the distance can be changed without
  re-tracking. Each stretch the point spends in a zone is a **zone visit**,
  listed in the Review tab for the experimenter to check.
- The experimenter logs **interactions** (start and end frame, which object)
  in the playback window, anywhere in the video, or marks a zone visit as
  **no interaction**. That scoring is saved beside the tracking file as
  `<name>_ObjectScoring.csv` and the results come from it.

Frames are the tracking file's rows (0-based here; shown 1-based).
"""

from __future__ import annotations

import json
import math
import os
import shutil
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .loader import TrackingData
from .metrics import carry_over_gaps, secs
from . import info_file
from .safe_write import replacing, write_csv

KINDS = ("Familiar", "Novel", "Moved")
PHASES = ("Habituation", "Training", "Test")
DEFAULT_OBJECTS = ("object 1", "object 2")
INTERACTION, NO_INTERACTION = "Interaction", "No interaction"
SCORING_SUFFIX = "_ObjectScoring.csv"


@dataclass
class TrialObject:
    """One object: a circle centered at (x, y) with radius r, in the
    tracking file's pixels, and whether it's familiar, novel or moved."""
    name: str
    x: float
    y: float
    r: float
    kind: str = "Familiar"

    @property
    def novel(self) -> bool:
        return self.kind in ("Novel", "Moved")


# --- objects in the tracking file -------------------------------------------
def objects_to_text(objects: list[TrialObject]) -> str:
    return json.dumps([{"name": o.name, "x": round(float(o.x), 2), "y": round(float(o.y), 2),
                        "r": round(float(o.r), 2), "kind": o.kind} for o in objects])


def objects_from_text(text) -> list[TrialObject]:
    """The objects a tracking file records ([] if none or unreadable)."""
    if not isinstance(text, str) or not text.strip():
        return []
    try:
        raw = json.loads(text)
        out = []
        for d in raw:
            kind = d.get("kind", "Familiar")
            out.append(TrialObject(str(d["name"]), float(d["x"]), float(d["y"]),
                                   float(d["r"]), kind if kind in KINDS else "Familiar"))
        return out
    except (ValueError, TypeError, KeyError):
        return []


def file_objects(data: TrackingData) -> list[TrialObject]:
    return objects_from_text(data.settings.get("Objects"))


def trial_info(data: TrackingData) -> tuple[str, str]:
    """(day, phase) as the tracking file records them ("" if not)."""
    def plain(v) -> str:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v).strip()
    return plain(data.settings.get("Trial_Day")), plain(data.settings.get("Trial_Phase"))


def update_trial_info(data: TrackingData, kinds: dict[str, str], day: str, phase: str) -> None:
    """Change each object's type, the trial day and the phase after tracking
    (ROADMAP §15). They're saved where tracking wrote them: the video's
    info file, or the tracking file itself if it's an older one that holds
    its own settings. Only those values change: every other value is written back
    exactly as it was read, and a failed save leaves the file as it was
    (OSError if it can't be saved, e.g. the file is open in Excel)."""
    objects = file_objects(data)
    for o in objects:
        if kinds.get(o.name) in KINDS:
            o.kind = kinds[o.name]
    values = {"Objects": objects_to_text(objects), "Trial_Day": str(day).strip(),
              "Trial_Phase": phase if phase in PHASES else ""}
    table = pd.read_csv(data.path, dtype=str, keep_default_na=False)
    if any(column in table.columns for column in values):
        for column, value in values.items():   # an older file: it holds them itself
            table[column] = value
        write_csv(table, data.path)
    else:
        # A slim tracking file: they're in the video's info file.
        update = info_file.update_saved_columns(data.path, values)
        if update is None:
            raise OSError("The video's info file wasn't found beside the tracking file.")
        with replacing(update[0]) as tmp:
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(update[1])
    data.settings.update(values)
    for column, value in values.items():
        data.df[column] = value


# --- zones --------------------------------------------------------------------
def distance_px(data: TrackingData, distance_cm: float) -> tuple[float, bool]:
    """The zone distance in the file's pixels, and whether a scale was used
    (without one, the distance is taken as pixels)."""
    try:
        per_px = float(data.settings.get("Scale_cm_per_px"))
    except (TypeError, ValueError):
        per_px = float("nan")
    if per_px and np.isfinite(per_px) and per_px > 0:
        return float(distance_cm) / per_px, True
    return float(distance_cm), False


def edge_distance(data: TrackingData, obj: TrialObject) -> np.ndarray:
    """Per frame: how far the point is from the object's edge, in pixels
    (negative inside the object, NaN with no position)."""
    x = data.df["X"].to_numpy(dtype=float)
    y = data.df["Y"].to_numpy(dtype=float)
    return np.hypot(x - obj.x, y - obj.y) - obj.r


def zone_masks(data: TrackingData, objects: list[TrialObject],
               zone_px: float) -> dict[str, np.ndarray]:
    """{object: per-frame True where the point is within `zone_px` of the
    object's edge (or on the object)}. Unreadable frames carry the frame
    before them, so a gap neither starts nor splits a visit."""
    bad = data.unreadable
    out = {}
    for o in objects:
        d = edge_distance(data, o)
        inside = np.nan_to_num(d, nan=np.inf) <= zone_px
        out[o.name] = carry_over_gaps(inside, bad) if bad.any() else inside
    return out


def zone_visits(data: TrackingData, objects: list[TrialObject], zone_px: float,
                fps: float, min_frames: int = 1) -> list[dict]:
    """Every stretch spent in an object's zone, in time order:
    {"object", "row" (first frame), "end" (last frame), "seconds"}.

    Nothing is dropped, however brief: the list is meant to catch every
    possible interaction for the experimenter to check (user, 2026-11-05).
    Stretches separated by an exit shorter than `min_frames` (boundary
    jitter) are joined into one visit."""
    visits = []
    for name, inside in zone_masks(data, objects, zone_px).items():
        runs = []
        k = np.flatnonzero(np.diff(np.concatenate([[0], inside.astype(np.int8), [0]])))
        for start, stop in zip(k[0::2], k[1::2]):          # stop is exclusive
            if runs and start - runs[-1][1] < max(1, min_frames):
                runs[-1][1] = stop                          # brief exit: same visit
            else:
                runs.append([start, stop])
        for start, stop in runs:
            visits.append({"object": name, "row": int(start), "end": int(stop) - 1,
                           "seconds": secs(int(stop - start), fps)})
    visits.sort(key=lambda v: (v["row"], v["object"]))
    return visits


def object_at(data: TrackingData, objects: list[TrialObject], zone_px: float,
              row: int) -> str:
    """The object whose zone the point is in at `row` (the nearest edge if in
    more than one), or ""."""
    best, best_d = "", float("inf")
    if not 0 <= row < data.n_frames:
        return ""
    x, y = data.df["X"].iat[row], data.df["Y"].iat[row]
    if pd.isna(x) or pd.isna(y):
        return ""
    for o in objects:
        d = math.hypot(float(x) - o.x, float(y) - o.y) - o.r
        if d <= zone_px and d < best_d:
            best, best_d = o.name, d
    return best


# --- scoring --------------------------------------------------------------------
@dataclass
class Bout:
    """An interaction with `object` from frame `start` to frame `end`
    (inclusive, 0-based rows)."""
    object: str
    start: int
    end: int

    def frames(self) -> int:
        return self.end - self.start + 1


@dataclass
class Scoring:
    """A file's manual scoring: interaction bouts, and zone visits marked
    as no interaction (by object and the visit's first frame)."""
    bouts: list[Bout] = field(default_factory=list)
    no_interaction: set[tuple[str, int]] = field(default_factory=set)
    # The saved scoring file was there but couldn't be read (e.g. saved from
    # a spreadsheet in another layout): it's copied aside before the first
    # save replaces it (`save_scoring`).
    unreadable: bool = False

    def add_bout(self, obj: str, start: int, end: int) -> Bout:
        """Log an interaction. One that overlaps or touches another with the
        same object joins it, so no frame is counted twice."""
        if end < start:
            start, end = end, start
        start, end = int(start), int(end)
        for other in [b for b in self.bouts if b.object == obj
                      and b.start <= end + 1 and start <= b.end + 1]:
            start, end = min(start, other.start), max(end, other.end)
            self.bouts.remove(other)
        b = Bout(obj, start, end)
        self.bouts.append(b)
        self.bouts.sort(key=lambda b: (b.start, b.object))
        return b

    def overlapping(self, obj: str, start: int, end: int) -> list[Bout]:
        return [b for b in self.bouts if b.object == obj and b.start <= end and start <= b.end]

    def marks_in(self, visit: dict) -> set[tuple[str, int]]:
        """The no-interaction marks that fall inside a zone visit. A mark is
        the frame its visit started on when it was made; a visit's first
        frame moves when the zone distance changes, so marks are matched by
        being inside the visit, not by its first frame."""
        return {(obj, row) for obj, row in self.no_interaction
                if obj == visit["object"] and visit["row"] <= row <= visit["end"]}

    def visit_status(self, visit: dict) -> str:
        """"scored" (has an interaction), "none" (marked no interaction) or
        "" (not reviewed yet)."""
        if self.overlapping(visit["object"], visit["row"], visit["end"]):
            return "scored"
        if self.marks_in(visit):
            return "none"
        return ""


def scoring_path(data: TrackingData) -> str:
    base = os.path.splitext(data.path)[0]
    if base.endswith("_LocationOutput"):
        base = base[: -len("_LocationOutput")]
    return base + SCORING_SUFFIX


# Scoring that couldn't be saved (the file open in another program, a full
# disk), by scoring file: kept here so the results, the export and a later
# visit to the file still use it, and the next change tries the save again.
_unsaved: dict[str, Scoring] = {}


def _scoring_key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def unreadable_copy_path(path: str) -> str:
    """Where a scoring file that couldn't be read is copied before it's
    replaced (a .txt, so it isn't taken for a tracking file)."""
    return os.path.splitext(path)[0] + "_unreadable.txt"


def save_scoring(data: TrackingData, scoring: Scoring, fps: float) -> str:
    """Write the scoring beside the tracking file (replacing it). A failed
    save leaves the earlier scoring file as it was and raises OSError; the
    scoring is then kept in memory (`load_scoring` returns it) until a save
    works. A scoring file that was there but couldn't be read is copied
    aside first, so nothing in it is lost."""
    path = scoring_path(data)
    try:
        if scoring.unreadable and os.path.exists(path):
            shutil.copyfile(path, unreadable_copy_path(path))
        write_csv(scoring_table(data, scoring, fps), path)
    except OSError:
        _unsaved[_scoring_key(path)] = scoring
        raise
    scoring.unreadable = False
    _unsaved.pop(_scoring_key(path), None)
    return path


def _start_frame(data: TrackingData) -> int:
    """The video frame of the tracking file's first row."""
    try:
        return int(float(data.settings.get("Start_Frame", 0)))
    except (TypeError, ValueError):
        return 0


def scoring_table(data: TrackingData, scoring: Scoring, fps: float) -> pd.DataFrame:
    """The scoring as a table (the scoring file, and the exported
    Interactions sheet). Frames are 1-based as shown, with the video's own
    frame and times, so it can be checked against the video by hand."""
    start = _start_frame(data)
    rows = []
    for b in scoring.bouts:
        rows.append({"Type": INTERACTION, "Object": b.object, "Start_Frame": b.start + 1,
                     "End_Frame": b.end + 1, "Start_VideoFrame": start + b.start,
                     "End_VideoFrame": start + b.end, "Start_s": secs(b.start, fps),
                     "End_s": secs(b.end + 1, fps), "Length_s": secs(b.frames(), fps)})
    for obj, row in sorted(scoring.no_interaction, key=lambda t: (t[1], t[0])):
        rows.append({"Type": NO_INTERACTION, "Object": obj, "Start_Frame": row + 1,
                     "End_Frame": "", "Start_VideoFrame": start + row, "End_VideoFrame": "",
                     "Start_s": secs(row, fps), "End_s": "", "Length_s": ""})
    cols = ["Type", "Object", "Start_Frame", "End_Frame", "Start_VideoFrame",
            "End_VideoFrame", "Start_s", "End_s", "Length_s"]
    return pd.DataFrame(rows, columns=cols)


def load_scoring(data: TrackingData) -> Scoring:
    """The file's scoring: what couldn't be saved earlier this session if
    there is any, else the saved file (empty if there's none).

    Each line is placed by its **video frame** (`Start_VideoFrame`), so
    scoring stays on the same moments of the video when the video is tracked
    again from a different start frame; a line outside the tracked frames is
    kept (it counts for nothing) rather than dropped. Files without those
    columns fall back to the row numbers. A file that's there but can't be
    read gives an empty scoring marked `unreadable`."""
    path = scoring_path(data)
    kept = _unsaved.get(_scoring_key(path))
    if kept is not None:
        return kept
    s = Scoring()
    if not os.path.exists(path):
        return s
    try:
        # sep=None: also reads a file saved from a spreadsheet with semicolons.
        df = pd.read_csv(path, sep=None, engine="python")
    except Exception:
        s.unreadable = os.path.getsize(path) > 0
        return s
    start = _start_frame(data)

    def row_of(r, shown: str, video: str) -> int:
        if video in df.columns and not pd.isna(r[video]):
            return int(float(r[video])) - start
        return int(float(r[shown])) - 1

    read = 0
    for _, r in df.iterrows():
        try:
            if r["Type"] == INTERACTION:
                s.add_bout(str(r["Object"]), row_of(r, "Start_Frame", "Start_VideoFrame"),
                           row_of(r, "End_Frame", "End_VideoFrame"))
            elif r["Type"] == NO_INTERACTION:
                s.no_interaction.add((str(r["Object"]),
                                      row_of(r, "Start_Frame", "Start_VideoFrame")))
            else:
                continue
            read += 1
        except (KeyError, TypeError, ValueError):
            continue
    s.unreadable = bool(len(df)) and not read
    return s


# --- results --------------------------------------------------------------------
def _ratio(a: float, b: float, digits: int) -> float:
    return round(a / b, digits) if b else float("nan")


def object_metrics(data: TrackingData, scoring: Scoring, fps: float,
                   zone_px: float, min_frames: int = 1,
                   lo: int = 0, hi: int | None = None) -> dict:
    """The object recognition results for frames lo..hi (the whole session by
    default; a bout counts for the frames of it inside the range).

    Per object: interaction time, bouts (counted where they start), latency
    to the first interaction (from the start of the range), zone time and
    zone visits. Then total interaction time, discrimination index =
    (novel - familiar) / (novel + familiar) and % preference = novel /
    (novel + familiar) x 100, where "novel" is every object marked Novel or
    Moved; both are formulas of the shown times, blank without a novel or
    familiar object."""
    objects = file_objects(data)
    n = data.n_frames
    hi = n if hi is None else min(hi, n)
    out: dict = {}
    times = {}
    for o in objects:
        mine = [b for b in scoring.bouts if b.object == o.name]
        frames = sum(max(0, min(b.end + 1, hi) - max(b.start, lo)) for b in mine)
        starts = [b.start for b in mine if lo <= b.start < hi]
        times[o.name] = secs(frames, fps)
        out[f"OR_Time_{o.name}_s"] = times[o.name]
        out[f"OR_Bouts_{o.name}"] = len(starts)
        out[f"OR_Latency_{o.name}_s"] = secs(min(starts) - lo, fps) if starts else float("nan")
    novel = round(sum(times[o.name] for o in objects if o.novel), 2)
    familiar = round(sum(times[o.name] for o in objects if not o.novel), 2)
    total = round(sum(times.values()), 2)
    out["OR_Total_s"] = total
    has_both = any(o.novel for o in objects) and any(not o.novel for o in objects)
    out["OR_Novel_s"] = novel if has_both else float("nan")
    out["OR_Familiar_s"] = familiar if has_both else float("nan")
    out["OR_DiscriminationIndex"] = (_ratio(novel - familiar, novel + familiar, 3)
                                     if has_both else float("nan"))
    out["OR_PctPreference"] = (round(100 * novel / (novel + familiar), 1)
                               if has_both and novel + familiar else float("nan"))
    out["OR_Bouts_Total"] = sum(out[f"OR_Bouts_{o.name}"] for o in objects)
    firsts = [out[f"OR_Latency_{o.name}_s"] for o in objects
              if not math.isnan(out[f"OR_Latency_{o.name}_s"])]
    out["OR_Latency_First_s"] = min(firsts) if firsts else float("nan")
    masks = zone_masks(data, objects, zone_px)
    visits = zone_visits(data, objects, zone_px, fps, min_frames)
    for o in objects:
        out[f"OR_ZoneTime_{o.name}_s"] = secs(int(masks[o.name][lo:hi].sum()), fps)
        out[f"OR_ZoneVisits_{o.name}"] = sum(1 for v in visits
                                             if v["object"] == o.name and lo <= v["row"] < hi)
    return out


def trial_summary(data: TrackingData, scoring: Scoring, fps: float, zone_cm: float,
                  min_frames: int = 1) -> dict:
    """The Summary row's object recognition columns: trial info, the results,
    and how far scoring has got (zone visits not reviewed yet)."""
    objects = file_objects(data)
    day, phase = trial_info(data)
    zone_px, scaled = distance_px(data, zone_cm)
    # The day goes out under the standard's own name, `trial_day`, the same
    # column every test's row has (user, 2026-11-12: "Keep trial day and
    # drop OR day"); no `OR_Day` beside it.
    out = {"trial_day": day, "OR_Phase": phase,
           "OR_NovelObjects": ", ".join(f"{o.name} ({o.kind.lower()})"
                                        for o in objects if o.novel) or "none"}
    out.update(object_metrics(data, scoring, fps, zone_px, min_frames))
    visits = zone_visits(data, objects, zone_px, fps, min_frames)
    out["OR_VisitsNotReviewed"] = sum(1 for v in visits if not scoring.visit_status(v))
    out["OR_ZoneDistance"] = f"{zone_cm:g} {'cm' if scaled else 'px (no scale)'}"
    return out
