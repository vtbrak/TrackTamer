"""Tracking an animal's position in a video (GUI-free).

Adapted from ezTrack (https://github.com/denisecailab/ezTrack),
LocationTracking_Functions.py: `Reference`, `Locate`, `TrackLocation`,
`ROI_Location`, `ROI_linearize`, `ROI_transitions` and `ScaleDistance`.
Copyright (C) Zachary T. Pennington, Zhe Dong, Yu Feng, Lauren M. Vetere,
Lucia Page-Harley, Tristan Shuman, Denise J. Cai. Licensed under the GNU
General Public License v3.0 (see LICENSE).

Changes from ezTrack:
- Wire removal (`rmv_wire` / `wire_krn`) is dropped.
- The window size is given in full-size video pixels and scaled by the
  downsampling, so it covers the same area of the arena at any downsampling.
- An unreadable frame no longer ends tracking: it stays as a row with a blank
  position and `Frame_Unreadable` True, and the window uses the last good
  position. Distance is blank for that frame and for the first readable frame
  after it, so no step is drawn across a gap.
- Region columns are blank (not False) for unreadable frames. A region can
  exclude other regions (Open Field periphery = arena outline minus center).
- The scale is always in cm, and every setting used is written to the output.
- Progress and cancel are reported through callbacks, for a GUI progress bar.
- The center of mass is worked out with numpy (same formula as scipy's
  `ndimage.center_of_mass`), so scipy isn't needed: Windows 11 Smart App
  Control blocked scipy's compiled file on a tester's PC (2026-11-06).
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from . import info_file
from .safe_write import image_bytes, replacing
from .version import VERSION
from .video import Prep, VideoReader, polygon_mask

METHODS = ("dark", "light", "abs")  # animal darker / lighter / either


@dataclass
class TrackingParams:
    """ezTrack's tracking parameters, with the user's notebook values as
    defaults (ROADMAP §12, Stage 3)."""
    loc_thresh: float = 99.5      # keep only differences above this percentile
    method: str = "dark"
    use_window: bool = True       # favor the area around the last position
    window_size: int = 100        # side of that square, full-size video pixels
    window_weight: float = 0.9    # 1 = ignore everything outside the window


@dataclass
class Region:
    """A drawn region of interest. `xs`/`ys` are its vertices in prepared-frame
    pixels. `subtract` names regions whose area is removed from this one."""
    name: str
    xs: list[float]
    ys: list[float]
    subtract: list[str] = field(default_factory=list)


@dataclass
class Scale:
    """Two clicked points `px` pixels apart that are `cm` centimeters apart."""
    px: float
    cm: float

    @property
    def cm_per_px(self) -> float:
        return self.cm / self.px


def make_reference(path: str, prep: Prep, start: int = 0, end: int | None = None,
                   num_frames: int = 50, seed: int = 0) -> np.ndarray:
    """The empty arena: the median of `num_frames` frames spread evenly over
    start..end, so the animal (somewhere different in most of them) drops
    out. An unreadable frame is replaced by a random one, as in ezTrack
    (seeded here, so the same settings give the same reference)."""
    rng = np.random.default_rng(seed)
    with VideoReader(path, prep) as reader:
        end = reader.frame_count if end is None else min(end, reader.frame_count)
        collection = []
        for index in np.linspace(start, end, num_frames):
            frame = reader.read_near(int(index))
            tries = 0
            while frame is None and tries < 100:
                frame = reader.read_near(int(rng.integers(start, end)))
                tries += 1
            if frame is None:
                raise ValueError(f"Couldn't read frames from {os.path.basename(path)}.")
            collection.append(frame)
    return np.median(np.stack(collection), axis=0)


def difference(frame: np.ndarray, reference: np.ndarray, params: TrackingParams,
               mask: np.ndarray | None = None) -> np.ndarray:
    """How different each pixel is from the reference, in the direction the
    `method` looks for, with excluded areas zeroed (ezTrack `Locate`)."""
    if params.method == "abs":
        dif = np.absolute(frame - reference)
    elif params.method == "light":
        dif = frame - reference
    else:
        dif = reference - frame
    dif = dif.astype("int16")
    if mask is not None:
        dif[mask] = 0
    return dif


def locate(frame: np.ndarray, reference: np.ndarray, params: TrackingParams,
           mask: np.ndarray | None = None, prior: tuple[int, int] | None = None,
           dsmpl: float = 1.0) -> tuple[float, float, np.ndarray]:
    """The animal's position in one prepared frame, as (y, x), plus the
    thresholded difference image it was found from (for previews).

    `prior` is the previous position (rounded y, x); with the window on,
    differences outside a square around it are scaled by 1 - window_weight.
    The position is the center of mass of the differences left after keeping
    only those above the `loc_thresh` percentile."""
    dif = difference(frame, reference, params, mask)
    if prior is not None and params.use_window:
        half = int(round(params.window_size * (dsmpl if dsmpl < 1 else 1))) // 2
        ymin, ymax = prior[0] - half, prior[0] + half
        xmin, xmax = prior[1] - half, prior[1] + half
        dif = dif + (dif.min() * -1)  # shift so the lowest value is 0
        weights = np.ones(dif.shape) * (1 - params.window_weight)
        weights[slice(max(ymin, 0), max(ymax, 0)), slice(max(xmin, 0), max(xmax, 0))] = 1
        dif = dif * weights
    dif[dif < np.percentile(dif, params.loc_thresh)] = 0
    y, x = center_of_mass(dif)
    return y, x, dif


def center_of_mass(image: np.ndarray) -> tuple[float, float]:
    """(y, x) of the weighted center of `image`, as scipy's
    `ndimage.center_of_mass` computes it; NaN, NaN if it's all zero."""
    total = float(image.sum(dtype=np.float64))
    if total == 0:
        return float("nan"), float("nan")
    h, w = image.shape
    y = float(image.sum(axis=1, dtype=np.float64) @ np.arange(h)) / total
    x = float(image.sum(axis=0, dtype=np.float64) @ np.arange(w)) / total
    return y, x


@dataclass
class TrackResult:
    df: pd.DataFrame | None   # None if cancelled
    unreadable: int           # frames kept as blank rows
    cancelled: bool = False
    # Frames asked for that aren't in `df` at all: the video couldn't be
    # read from some point to the end of the session, so those rows were
    # dropped (a few at the very end of a file is normal; many is a damaged
    # or shorter video, and the session is shorter than asked for).
    missing_at_end: int = 0


def track_video(path: str, reference: np.ndarray, params: TrackingParams,
                prep: Prep | None = None, start: int = 0, end: int | None = None,
                mask: np.ndarray | None = None, progress=None,
                should_cancel=None) -> TrackResult:
    """Track frames start..end. `progress(done, total)` is called now and
    then; `should_cancel()` returning True stops early (result df is None).

    Returns ezTrack's per-frame columns (Frame counts from 0 at `start`):
    X, Y, Distance_px, plus Frame_Unreadable."""
    prep = prep or Prep()
    with VideoReader(path, prep) as reader:
        end = reader.frame_count if end is None else min(end, reader.frame_count)
        total = max(end - start, 0)
        xs, ys, bad = [], [], []
        prior = None
        for done, (_index, frame) in enumerate(reader.frames(start, end)):
            if should_cancel and should_cancel():
                return TrackResult(None, sum(bad), cancelled=True)
            if frame is None:
                xs.append(np.nan); ys.append(np.nan); bad.append(True)
            else:
                y, x, _ = locate(frame, reference, params, mask, prior, prep.dsmpl)
                xs.append(x); ys.append(y); bad.append(False)
                if np.isfinite(x) and np.isfinite(y):
                    prior = (int(np.around(y)), int(np.around(x)))
            if progress and done % 25 == 0:
                progress(done, total)
        if progress:
            progress(len(xs), total)

    x = np.array(xs); y = np.array(ys)
    step = np.sqrt(np.diff(x) ** 2 + np.diff(y) ** 2)  # NaN next to any gap
    distance = np.concatenate([[0.0], step]) if len(x) else np.array([])
    df = pd.DataFrame({
        "Frame": np.arange(len(x)),
        "X": x,
        "Y": y,
        "Distance_px": distance,
        "Frame_Unreadable": bad,
    })
    return TrackResult(df, int(sum(bad)), missing_at_end=max(total - len(x), 0))


def region_columns(df: pd.DataFrame, regions: list[Region],
                   shape: tuple[int, int]) -> pd.DataFrame:
    """One True/False column per region (ezTrack `ROI_Location`): whether the
    position's pixel is inside the region, blank for unreadable frames.
    Also ROI_coordinates, ROI_location (names of the regions the animal is
    in, joined by "_", or "non_roi") and ROI_transition (where that label
    changes), as ezTrack writes them."""
    out = pd.DataFrame(index=df.index)
    masks = {r.name: polygon_mask(shape, [(r.xs, r.ys)]) for r in regions}
    for r in regions:
        for other in r.subtract:
            masks[r.name] = masks[r.name] & ~masks[other]

    readable = df["X"].notna() & df["Y"].notna()
    h, w = shape
    yi = np.clip(df["Y"].fillna(0).astype(int).to_numpy(), 0, h - 1)
    xi = np.clip(df["X"].fillna(0).astype(int).to_numpy(), 0, w - 1)
    for r in regions:
        inside = pd.Series(masks[r.name][yi, xi], index=df.index, dtype=object)
        inside[~readable] = None
        out[r.name] = inside

    out["ROI_coordinates"] = str({"xs": [list(map(float, r.xs)) for r in regions],
                                  "ys": [list(map(float, r.ys)) for r in regions]})
    names = [r.name for r in regions]
    hits = np.column_stack([(out[n] == True).to_numpy() for n in names])  # noqa: E712
    label = pd.Series(["_".join(n for n, hit in zip(names, row) if hit) or "non_roi"
                       for row in hits], index=df.index, dtype=object)
    label[~readable] = None
    out["ROI_location"] = label
    previous = label.shift(1)
    transition = (label != previous) & label.notna() & previous.notna()
    out["ROI_transition"] = transition
    return out


def assemble_output(video_path: str, tracked: pd.DataFrame, params: TrackingParams,
                    prep: Prep, start: int, regions: list[Region] | None,
                    shape: tuple[int, int], scale: Scale | None,
                    reference_frames: int, exclusion_count: int,
                    fps: float, extra: dict | None = None,
                    repeated: set | None = None) -> pd.DataFrame:
    """The full `_LocationOutput.csv` table: ezTrack's columns in ezTrack's
    order, then this app's additions (Frame_Unreadable and every setting
    used)."""
    n = len(tracked)
    df = pd.DataFrame({
        "File": os.path.basename(video_path),
        "Location_Thresh": np.full(n, float(params.loc_thresh)),
        "Use_Window": str(params.use_window),
        "Window_Weight": np.full(n, float(params.window_weight)),
        "Window_Size": np.full(n, float(params.window_size)),
        "Start_Frame": np.full(n, float(start)),
        "Frame": tracked["Frame"],
        "X": tracked["X"],
        "Y": tracked["Y"],
    })
    if regions:
        df = pd.concat([df, region_columns(tracked, regions, shape)], axis=1)
    df["Distance_px"] = tracked["Distance_px"]
    if scale is not None:
        df["Distance_cm"] = tracked["Distance_px"] * scale.cm_per_px
    df["Frame_Unreadable"] = tracked["Frame_Unreadable"]
    if repeated is not None:
        # Video frames the recording app wrote as a copy of the one before
        # (its info file lists them). Frame counts from 0 at `start`.
        df["Frame_Repeated"] = (tracked["Frame"].astype(int) + int(start)).isin(repeated)
    df["Method"] = params.method
    df["Downsample"] = float(prep.dsmpl)
    df["Crop"] = crop_text(prep.crop)
    df["Reference_Frames"] = int(reference_frames)
    df["Exclusion_Shapes"] = int(exclusion_count)
    df["Scale_px"] = scale.px if scale else np.nan
    df["Scale_cm"] = scale.cm if scale else np.nan
    df["Scale_cm_per_px"] = scale.cm_per_px if scale else np.nan
    df["Video_FPS"] = float(fps)
    for key, value in (extra or {}).items():   # e.g. the objects drawn
        df[key] = value
    return df


def crop_text(crop) -> str:
    """The crop as the tracking file records it: the four numbers exactly as
    used (`repr`, so reading them back gives the same crop to the pixel;
    rounding them could shift playback by a pixel)."""
    return ",".join(repr(float(v)) for v in crop) if crop else ""


def output_paths(video_path: str) -> dict[str, str]:
    base = os.path.splitext(video_path)[0]
    return {"csv": base + "_LocationOutput.csv", "reference": base + "_reference.png"}


# What a tracking file used to repeat on every row: the video's name, every
# tracking setting and the region outlines. They're saved once, in the
# video's info file, and the tracking file keeps the per-frame columns
# (user, 2026-11-11). `loader.load_csv` puts them back when it reads one.
def constant_columns() -> tuple:
    from .loader import SETTINGS_COLUMNS
    return ("File", *SETTINGS_COLUMNS, "ROI_coordinates")


def split_constants(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """(the per-frame columns, {constant column: its value})."""
    constants = {}
    for column in constant_columns():
        if column not in df.columns or not len(df):
            continue
        value = df[column].iloc[0]
        value = value.item() if hasattr(value, "item") else value
        if isinstance(value, float) and np.isnan(value):
            value = None
        if column == "ROI_coordinates" and isinstance(value, str):
            try:
                value = ast.literal_eval(value)     # real lists read better in the JSON
            except (ValueError, SyntaxError):
                pass
        constants[column] = value
    return df.drop(columns=list(constants)), constants


def save_outputs(video_path: str, df: pd.DataFrame, reference: np.ndarray,
                 record: dict | None = None, label: str | None = None) -> dict[str, str]:
    """Write `<name>_LocationOutput.csv` and `<name>_reference.png` next to
    the video, in place of earlier ones, and save what the tracking file
    doesn't repeat (its settings and region outlines), with `record` (the
    test and the video's setup), in the video's info file. All three are
    written in full before any earlier file is touched, so a failed save (a
    full disk, the tracking file open in Excel on Windows) leaves the
    earlier files as they were, still matching each other. `label` is the
    camera label of a renamed video's entry in its info file."""
    paths = output_paths(video_path)
    image = image_bytes(np.clip(reference, 0, 255).astype(np.uint8), ".png")
    frames, constants = split_constants(df)
    info_path, text = info_file.prepare(video_path, {
        **(record or {}),
        "version": VERSION, "saved": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "setup_changed_since_tracking": False,
        "tracking": constants,
        "files": {"tracking": os.path.basename(paths["csv"]),
                  "reference": os.path.basename(paths["reference"])},
    }, label)
    paths["info"] = info_path
    # The tracking file is put in place first (it's the one likely to be
    # open elsewhere); if that fails the other two aren't replaced either.
    with replacing(paths["reference"]) as ref_tmp:
        with open(ref_tmp, "wb") as f:
            f.write(image)
        with replacing(info_path) as info_tmp:
            with open(info_tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            with replacing(paths["csv"]) as csv_tmp:
                frames.to_csv(csv_tmp, index=False)
    return paths
