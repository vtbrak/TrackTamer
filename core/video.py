"""Reading video frames (GUI-free).

Adapted from ezTrack (https://github.com/denisecailab/ezTrack),
LocationTracking_Functions.py: `LoadAndCrop`, `cropframe`, `check_p_frames`
and `Mask_select`. Copyright (C) Zachary T. Pennington, Zhe Dong, Yu Feng,
Lauren M. Vetere, Lucia Page-Harley, Tristan Shuman, Denise J. Cai.
Licensed under the GNU General Public License v3.0 (see LICENSE).

Changes from ezTrack: no notebook/HoloViews tools (the GUI draws crops and
shapes and passes plain coordinates here); the unreadable-frame check returns
counts for a warning instead of raising an error; sequential reading keeps
going past an unreadable frame (reported as None) instead of stopping; a jump
to a frame is checked against the frames' own timestamps (see `frame_times`),
because OpenCV's own jump can land a frame or so off.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import cv2
import numpy as np

VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".wmv", ".mpg", ".mpeg", ".mkv", ".m4v")


def is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS


@dataclass
class VideoInfo:
    path: str
    frame_count: int  # as the file reports it; may overcount by a few frames
    fps: float
    width: int
    height: int


def video_info(path: str) -> VideoInfo:
    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            raise ValueError(f"Couldn't open the video {os.path.basename(path)}.")
        return VideoInfo(
            path=path,
            frame_count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            fps=float(cap.get(cv2.CAP_PROP_FPS)),
            width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
    finally:
        cap.release()


@dataclass
class Prep:
    """How each frame is prepared before tracking, as in ezTrack: grayscale,
    then downsample, then crop.

    dsmpl: scale factor (1.0 = full size; ezTrack only resizes when < 1).
    crop: (x0, y0, x1, y1) in downsampled pixels, or None for the whole frame.
    """
    dsmpl: float = 1.0
    crop: tuple[float, float, float, float] | None = None


def prepare(frame_bgr: np.ndarray, prep: Prep) -> np.ndarray:
    frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    if prep.dsmpl < 1:
        # ezTrack passes cv2.INTER_NEAREST positionally, where cv2.resize
        # expects `dst`, so its frames are actually resized with the default
        # (bilinear) interpolation. Kept that way so results match ezTrack.
        frame = cv2.resize(
            frame, (int(frame.shape[1] * prep.dsmpl), int(frame.shape[0] * prep.dsmpl))
        )
    return crop_frame(frame, prep.crop)


def crop_frame(frame: np.ndarray, crop) -> np.ndarray:
    if not crop:
        return frame
    x0, y0, x1, y1 = crop
    xmin, xmax = int(min(x0, x1)), int(max(x0, x1))
    ymin, ymax = int(min(y0, y1)), int(max(y0, y1))
    return frame[ymin:ymax, xmin:xmax]


# --- Jumping to a frame -----------------------------------------------------
# OpenCV jumps to frame N by turning N into a time with the video's average
# frame rate. Cameras that write each frame's real capture time give frames
# that aren't evenly spaced, so the jump lands on a neighbouring frame in some
# stretches of the video (seen on every camera recording in Examples: a frame
# early, mostly). Reading in order has no such problem, and that is how
# tracking reads. So a jump here is checked: the video's frames are listed by
# their own timestamps once (without decoding, so it's quick), and after a
# jump the frame's timestamp says which frame it really is.

_times_cache: dict = {}
_TIME_MATCH_MS = 0.001  # the same frame gives the same timestamp either way


def frame_times(path: str) -> np.ndarray | None:
    """Each frame's own timestamp (ms), in the order the frames are read, so
    `times[i]` belongs to the frame that reading in order from the start gives
    as frame i. None if the video can't give them (jumps then fall back to
    OpenCV's own). Worked out once per video file and kept."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    key = (os.path.abspath(path), stat.st_size, stat.st_mtime_ns)
    if key not in _times_cache:
        if len(_times_cache) >= 32:
            _times_cache.pop(next(iter(_times_cache)))
        _times_cache[key] = _read_frame_times(path)
    return _times_cache[key]


def _read_frame_times(path: str) -> np.ndarray | None:
    # CAP_PROP_FORMAT -1 hands back the stored packets without decoding them.
    try:
        cap = cv2.VideoCapture(path, cv2.CAP_FFMPEG, [cv2.CAP_PROP_FORMAT, -1])
    except (cv2.error, TypeError):
        return None
    try:
        if not cap.isOpened() or cap.get(cv2.CAP_PROP_FORMAT) != -1:
            return None
        stamps = []
        while cap.grab():
            stamps.append(cap.get(cv2.CAP_PROP_POS_MSEC))
    finally:
        cap.release()
    # Packets are stored in decoding order; frames come out in time order.
    times = np.sort(np.asarray(stamps, dtype=float))
    if len(times) < 2 or not np.all(np.diff(times) > 0):
        return None  # missing or repeated timestamps can't tell frames apart
    # Line the list up with the first frame that actually decodes.
    cap = cv2.VideoCapture(path)
    try:
        first = frame_at(cap, times) if cap.grab() else None
    finally:
        cap.release()
    return None if first is None else times[first:]


def frame_at(cap, times: np.ndarray | None) -> int | None:
    """Which frame (counted in order from the start) `cap` grabbed last, from
    its timestamp; None if that can't be told."""
    if times is None or not len(times):
        return None
    ms = cap.get(cv2.CAP_PROP_POS_MSEC)
    i = min(int(np.searchsorted(times, ms)), len(times) - 1)
    if i > 0 and ms - times[i - 1] < times[i] - ms:
        i -= 1
    return i if abs(times[i] - ms) <= _TIME_MATCH_MS else None


def grab_frame(cap, times: np.ndarray | None, index: int) -> bool:
    """Grab frame `index` as reading in order from the start counts it, so
    `cap.retrieve()` gives it. Jumps to a little before it, checks where the
    jump landed, and reads forward to the frame. False if it can't be read.
    Without `times` (see `frame_times`) this is OpenCV's own jump. A negative
    `index` gives the first frame, as OpenCV's jump does."""
    index = max(index, 0)
    if times is None:
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        return cap.grab()
    if index >= len(times):
        return False
    for back in (2, 12, 60, index):  # aim further back if a jump lands past it
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(index - back, 0))
        passed = False  # read forward from before the frame
        while cap.grab():
            at = frame_at(cap, times)
            if at is None:  # a timestamp not in the list: can't check
                cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                return cap.grab()
            if at == index:
                return True
            if at > index:
                if passed:
                    return False  # the frame itself doesn't decode
                break
            passed = True
        else:
            return False
    return False


def landing_frame(cap, times: np.ndarray | None, index: int) -> int:
    """The frame OpenCV's own jump to `index` really lands on. Tracking starts
    with that jump and reads on in order, so a tracking file's first row is
    this frame (`index` itself where that can't be told)."""
    if index <= 0 or times is None:
        return max(index, 0)
    cap.set(cv2.CAP_PROP_POS_FRAMES, index)
    at = frame_at(cap, times) if cap.grab() else None
    return index if at is None else at


class VideoReader:
    """Frames from one video, prepared (grayscale, downsampled, cropped).

    Use as a context manager. `read_at` jumps to any frame (for previews);
    `frames` reads a range in order (for tracking).
    """

    def __init__(self, path: str, prep: Prep | None = None):
        self.path = path
        self.prep = prep or Prep()
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise ValueError(f"Couldn't open the video {os.path.basename(path)}.")
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self) -> None:
        self.cap.release()

    def read_at(self, index: int, raw: bool = False) -> np.ndarray | None:
        """Frame `index` (0-based, as reading in order from the start counts
        it), or None if it can't be read. `raw` returns the original color
        frame without preparation (for display)."""
        if not grab_frame(self.cap, frame_times(self.path), index):
            return None
        ret, frame = self.cap.retrieve()
        if not ret:
            return None
        return frame if raw else prepare(frame, self.prep)

    def read_near(self, index: int) -> np.ndarray | None:
        """A frame at or right next to `index`, by OpenCV's own jump (which
        can land a frame or so off; see `frame_times`). For the reference
        image only: any frame nearby does there, and reading the same frames
        as before keeps references, and so tracking results, unchanged."""
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ret, frame = self.cap.read()
        return prepare(frame, self.prep) if ret else None

    def frames(self, start: int = 0, end: int | None = None):
        """Yield (index, frame) for start <= index < end, in order. An
        unreadable frame is yielded as None and reading continues after it.
        A run of unreadable frames at the very end is dropped: files often
        report a few more frames than they hold (ezTrack stops there too).

        The first frame is where OpenCV's own jump to `start` lands, which
        can be a neighbour of `start` when `start` isn't 0 (`landing_frame`).
        Left as it is so tracking results don't change; playback finds the
        same frame to line its rows up."""
        end = self.frame_count if end is None else min(end, self.frame_count)
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        pending = []  # unreadable indices not yet yielded
        for index in range(start, end):
            ret, frame = self.cap.read()
            if not ret:
                pending.append(index)
                # Step past the bad frame so the next read is the next frame.
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, index + 1)
                continue
            for bad in pending:
                yield bad, None
            pending = []
            yield index, prepare(frame, self.prep)


def check_readable(path: str, frames_checked: int = 300) -> tuple[int, int]:
    """(unreadable, checked) over the first `frames_checked` frames, read in
    order, as ezTrack's `check_p_frames` does. ezTrack refuses a video with
    more than 1% unreadable; the app warns instead (see UNREADABLE_WARN)."""
    cap = cv2.VideoCapture(path)
    try:
        checked = min(frames_checked, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        bad = sum(not cap.read()[0] for _ in range(checked))
        return bad, checked
    finally:
        cap.release()


UNREADABLE_WARN = 0.01  # ezTrack's limit: warn above 1% unreadable


def polygon_mask(shape: tuple[int, int], polygons) -> np.ndarray:
    """Boolean mask (True inside any polygon) for an image of `shape` (h, w).
    `polygons` is a list of (xs, ys) vertex lists, in the same pixels as the
    prepared frames. Filled as ezTrack does (cv2.fillPoly on truncated
    coordinates)."""
    mask = np.zeros(shape, dtype=np.uint8)
    for xs, ys in polygons:
        if len(xs) < 3:
            continue
        pts = np.column_stack((np.asarray(xs), np.asarray(ys))).astype(np.int32)
        cv2.fillPoly(mask, pts=[pts], color=1)
    return mask.astype(bool)
