"""Playing back a tracked video, and saving it with the tracking drawn on
(GUI-free; ROADMAP §12, Stage 6).

Adapted from ezTrack (https://github.com/denisecailab/ezTrack),
LocationTracking_Functions.py: `PlayVideo` and `PlayVideo_ext`. Copyright (C)
Zachary T. Pennington, Zhe Dong, Yu Feng, Lauren M. Vetere, Lucia
Page-Harley, Tristan Shuman, Denise J. Cai. Licensed under the GNU General
Public License v3.0 (see LICENSE).

Changes from ezTrack: frames are matched to the tracking file through its own
recorded start frame, downsampling and crop (so any tracked file plays back
from its own settings); an unreadable frame or a blank position shows no
marker instead of crashing; the saved video uses the video's real frame rate
(ezTrack always writes 20 fps), is named after the video
(`<name>_tracked.mp4`, ezTrack always writes `video_output.avi`), and is
MPEG-4 so it plays on Mac and Windows without extra software.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cached_property

import cv2
import numpy as np
import pandas as pd

from .loader import TrackingData
from .objects import object_at
from .regions import match_polygons
from .safe_write import replacing
from .video import (VIDEO_EXTENSIONS, Prep, crop_frame, frame_times, grab_frame,
                    video_info)

MARKER_BGR = (40, 40, 255)      # red
TRAIL_BGR = (40, 200, 255)      # amber
ROI_BGR = (90, 220, 90)         # green
OBJECT_BGR = (26, 159, 255)     # orange, as in the playback window
ZONE_BGR = (255, 255, 255)      # white


def find_video(data: TrackingData, hint: str | None = None) -> str | None:
    """The video a tracking file came from: `hint` if it exists, else the
    file named in its File column beside the CSV, else a video with the CSV's
    name minus `_LocationOutput`."""
    if hint and os.path.exists(hint):
        return hint
    folder = os.path.dirname(os.path.abspath(data.path))
    if "File" in data.df.columns and len(data.df):
        named = os.path.join(folder, str(data.df["File"].iloc[0]))
        if os.path.exists(named):
            return named
    base = os.path.splitext(os.path.abspath(data.path))[0]
    if base.endswith("_LocationOutput"):
        base = base[: -len("_LocationOutput")]
        for ext in VIDEO_EXTENSIONS:
            for e in (ext, ext.upper()):
                if os.path.exists(base + e):
                    return base + e
    return None


def reference_path(data: TrackingData) -> str | None:
    """`<name>_reference.png` beside a `<name>_LocationOutput.csv`, if there."""
    base = os.path.splitext(data.path)[0]
    if not base.endswith("_LocationOutput"):
        return None
    path = base[: -len("_LocationOutput")] + "_reference.png"
    return path if os.path.exists(path) else None


def load_reference(data: TrackingData) -> np.ndarray | None:
    """The file's reference image (grayscale), or None if it has none."""
    path = reference_path(data)
    if path is None:
        return None
    # imdecode reads paths with non-ASCII characters on Windows too.
    raw = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE) if raw.size else None
    return img


def prep_from_settings(settings: dict) -> Prep | None:
    """How the file's frames were prepared, from its recorded settings; None
    if it doesn't record them (e.g. ezTrack's own files, whose crop is
    unknown, so positions can't be lined up with the video)."""
    if "Downsample" not in settings and "Crop" not in settings:
        # A startle motion file is of the whole frame unless it says
        # otherwise (no crop since 2026-11-12), and has no positions to line up.
        return Prep() if "Intensity_Threshold" in settings else None
    try:
        dsmpl = float(settings.get("Downsample", 1.0))
    except (TypeError, ValueError):
        dsmpl = 1.0
    crop = None
    text = settings.get("Crop", "")
    if isinstance(text, str) and text.strip():
        try:
            crop = tuple(float(v) for v in text.split(","))
            if len(crop) != 4:
                crop = None
        except ValueError:
            crop = None
    return Prep(dsmpl=dsmpl if np.isfinite(dsmpl) else 1.0, crop=crop)


def prepare_color(frame_bgr: np.ndarray, prep: Prep) -> np.ndarray:
    """A color frame prepared like tracking's grayscale ones (downsample,
    then crop), so tracked positions line up with it."""
    if prep.dsmpl < 1:
        frame_bgr = cv2.resize(frame_bgr, (int(frame_bgr.shape[1] * prep.dsmpl),
                                           int(frame_bgr.shape[0] * prep.dsmpl)))
    return crop_frame(frame_bgr, prep.crop)


@dataclass
class Playback:
    """A tracking file matched to its video."""
    data: TrackingData
    video: str
    prep: Prep
    start: int           # video frame of the file's first row
    fps: float           # the video's real frame rate

    @property
    def n_frames(self) -> int:
        return self.data.n_frames

    def video_frame(self, row: int) -> int:
        return self.start + row

    def position(self, row: int) -> tuple[float, float] | None:
        if "X" not in self.data.df.columns:     # a startle motion index file
            return None
        x, y = self.data.df["X"].iat[row], self.data.df["Y"].iat[row]
        return (float(x), float(y)) if pd.notna(x) and pd.notna(y) else None

    @cached_property
    def _unreadable(self) -> np.ndarray:
        return self.data.unreadable

    def unreadable(self, row: int) -> bool:
        return bool(self._unreadable[row])

    def region(self, row: int) -> str:
        if "ROI_location" not in self.data.df.columns:
            return ""
        v = self.data.df["ROI_location"].iat[row]
        return "" if pd.isna(v) or v == "non_roi" else str(v)

    def trail(self, row: int, frames: int) -> list[tuple[float, float] | None]:
        if "X" not in self.data.df.columns:
            return []
        lo = max(0, row - frames)
        xs = self.data.df["X"].iloc[lo:row + 1].to_numpy()
        ys = self.data.df["Y"].iloc[lo:row + 1].to_numpy()
        return [(x, y) if np.isfinite(x) and np.isfinite(y) else None for x, y in zip(xs, ys)]

    @cached_property
    def _regions(self) -> dict[str, tuple[list, list]]:
        return match_polygons(self.data)

    def regions(self) -> dict[str, tuple[list, list]]:
        """{region: polygon} in the file's own pixels (worked out once)."""
        return self._regions

    def time_text(self, row: int) -> str:
        s = row / self.fps if self.fps else 0
        return f"{int(s // 60)}:{s % 60:05.2f}"


def open_playback(data: TrackingData, video_hint: str | None = None) -> Playback:
    """Match a tracking file to its video. ValueError says why it can't be."""
    video = find_video(data, video_hint)
    if video is None:
        raise ValueError("The video this file came from wasn't found. Put the video "
                         "in the same folder as the tracking file.")
    prep = prep_from_settings(data.settings)
    if prep is None:
        raise ValueError("This file doesn't record how its video was cropped, so the "
                         "positions can't be lined up with the video. Files tracked "
                         "in this app record it.")
    try:
        start = int(float(data.settings.get("Start_Frame", 0)))
    except (TypeError, ValueError):
        start = 0
    fps = 0.0
    try:
        fps = float(data.settings.get("Video_FPS", 0))
    except (TypeError, ValueError):
        pass
    if not fps or not np.isfinite(fps):
        fps = video_info(video).fps
    if not fps or not np.isfinite(fps) or fps <= 0:
        fps = 20.0      # a video that doesn't give its rate: times are then nominal
    return Playback(data, video, prep, start, fps)


class FrameSource:
    """Reads a playback's color frames, fast when moving forward (sequential
    reads, skipped frames grabbed without decoding) and by jumping otherwise.

    Row r is video frame start + r, the frame tracking read for that row. A
    jump goes to exactly that frame (`grab_frame`), where OpenCV's own could
    land on a neighbour and put the marks on the wrong frame."""

    def __init__(self, pb: Playback):
        self.pb = pb
        self.cap = cv2.VideoCapture(pb.video)
        if not self.cap.isOpened():
            raise ValueError(f"Couldn't open the video {os.path.basename(pb.video)}.")
        self._times = frame_times(pb.video)
        self._next = None   # frame the next grab() gives, counted in order

    def close(self) -> None:
        self.cap.release()

    def frame(self, row: int) -> np.ndarray | None:
        target = self.pb.video_frame(row)
        if self._next is not None and 0 <= target - self._next <= 30:
            ok = True
            while ok and self._next <= target:
                ok = self.cap.grab()
                self._next += 1
        else:
            ok = grab_frame(self.cap, self._times, target)
        if ok:
            ok, frame = self.cap.retrieve()
        if not ok:
            self._next = None
            return None
        self._next = target + 1
        return prepare_color(frame, self.pb.prep)


def _draw_objects(img: np.ndarray, objects, zone_px: float, here: str) -> None:
    """Each object's circle, its dashed zone ring (heavier while the point is
    in that zone) and its name and type, as in the playback window."""
    width = img.shape[1]
    for o in objects:
        center = (int(round(o.x)), int(round(o.y)))
        ring = int(round(o.r + zone_px))
        cv2.circle(img, center, max(1, int(round(o.r))), OBJECT_BGR, 2, cv2.LINE_AA)
        for start in range(0, 360, 18):
            cv2.ellipse(img, center, (ring, ring), 0, start, start + 10, ZONE_BGR,
                        2 if o.name == here else 1, cv2.LINE_AA)
        label = f"{o.name} ({o.kind.lower()})"
        (text_w, _h), _base = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
        spot = (max(2, min(center[0] - text_w // 2, width - text_w - 2)),
                max(30, center[1] - ring - 5))    # below the time in the corner
        for color, thickness in (((0, 0, 0), 3), ((255, 255, 255), 1)):
            cv2.putText(img, label, spot, cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, thickness,
                        cv2.LINE_AA)


def draw_tracking(frame: np.ndarray, pb: Playback, row: int, trail_frames: int = 0,
                  show_regions: bool = True, objects=None,
                  zone_px: float = 0.0) -> np.ndarray:
    """The frame with ROIs, any objects and their zones, a short trail and
    the position marker drawn on, plus time and region (or the object zone
    the point is in) in the corner (for the saved video)."""
    img = frame.copy()
    here = object_at(pb.data, objects, zone_px, row) if objects else ""
    if objects:
        _draw_objects(img, objects, zone_px, here)
    if show_regions:
        for xs, ys in pb.regions().values():
            pts = np.column_stack([xs, ys]).round().astype(np.int32)
            cv2.polylines(img, [pts], True, ROI_BGR, 1, cv2.LINE_AA)
    if trail_frames:
        pts = pb.trail(row, trail_frames)
        for a, b in zip(pts, pts[1:]):
            if a and b:
                cv2.line(img, tuple(int(round(v)) for v in a), tuple(int(round(v)) for v in b),
                         TRAIL_BGR, 1, cv2.LINE_AA)
    pos = pb.position(row)
    if pos:
        r = max(3, int(round(min(img.shape[:2]) / 80)))
        cv2.circle(img, (int(round(pos[0])), int(round(pos[1]))), r, MARKER_BGR, -1,
                   cv2.LINE_AA)
    text = pb.time_text(row) + ("  unreadable" if pb.unreadable(row) else
                                f"  {pb.region(row)}" if pb.region(row) else
                                f"  {here} zone" if here else "")
    for color, width in (((0, 0, 0), 3), ((255, 255, 255), 1)):
        cv2.putText(img, text, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, width,
                    cv2.LINE_AA)
    return img


def tracked_video_path(video: str) -> str:
    return os.path.splitext(video)[0] + "_tracked.mp4"


def write_tracked_video(pb: Playback, out_path: str | None = None, trail_frames: int = 0,
                        show_regions: bool = True, progress=None,
                        should_cancel=None, objects=None,
                        zone_px: float = 0.0) -> str | None:
    """Write the session with the tracking drawn on, at the video's real
    frame rate, as `<name>_tracked.mp4` beside the video (overwriting).
    `objects` (Object Recognition) are drawn with zones `zone_px` out from
    their edges. Returns the path, or None if cancelled (nothing is left
    behind, and an earlier tracked video stays as it was)."""
    out_path = out_path or tracked_video_path(pb.video)
    # Written under a temporary name and put in place only when complete, so
    # cancelling or a failure partway keeps an earlier tracked video.
    kept = None
    with replacing(out_path) as tmp:
        if not _write_tracked(pb, tmp, trail_frames, show_regions, progress,
                              should_cancel, objects, zone_px):
            if os.path.exists(tmp):
                os.remove(tmp)      # cancelled: nothing is put in place
            return None
        # The earlier video may be open in a player (Windows then refuses to
        # replace it): keep the finished one under another name rather than
        # throw the whole render away.
        try:
            os.replace(tmp, out_path)
        except PermissionError:
            kept = os.path.splitext(out_path)[0] + " (new).mp4"
            os.replace(tmp, kept)
    if kept:
        raise ValueError(f"The video was made, but {os.path.basename(out_path)} is open in "
                         f"another program and couldn't be replaced. The new one is saved "
                         f"as {os.path.basename(kept)}.")
    return out_path


def _write_tracked(pb: Playback, out_path: str, trail_frames, show_regions, progress,
                   should_cancel, objects, zone_px) -> bool:
    """Write the video to `out_path`. True when finished, False if cancelled."""
    cap = cv2.VideoCapture(pb.video)
    writer = None
    try:
        times = frame_times(pb.video)
        n = pb.n_frames
        size = None
        jump = True   # go to the frame itself: at the start, and past a bad frame
        for row in range(n):
            if should_cancel and should_cancel():
                break
            # The same frames, found the same way, as tracking read.
            ok = grab_frame(cap, times, pb.video_frame(row)) if jump else cap.grab()
            if ok:
                ok, frame = cap.retrieve()
            jump = not ok
            if ok:
                frame = prepare_color(frame, pb.prep)
            if size is None:
                if not ok:
                    continue  # size comes from the first readable frame
                h, w = frame.shape[:2]
                size = (w - w % 2, h - h % 2)  # MPEG-4 wants even sides
                writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"),
                                         pb.fps or 20.0, size)
                if not writer.isOpened():
                    raise ValueError("The video file couldn't be created.")
            if not ok:
                frame = np.zeros((size[1], size[0], 3), np.uint8)  # keep the timing
            img = draw_tracking(frame, pb, row, trail_frames, show_regions, objects, zone_px)
            writer.write(np.ascontiguousarray(img[:size[1], :size[0]]))
            if progress and row % 25 == 0:
                progress(row, n)
        else:
            if progress:
                progress(n, n)
            if writer is None:
                raise ValueError("No frames of the video could be read.")
            return True
    finally:
        cap.release()
        if writer is not None:
            writer.release()
    return False
