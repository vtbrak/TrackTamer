"""Running tracking on several videos in the background (GUI-free).

The GUI builds one `TrackJob` per video from that video's setup when Track is
clicked (a snapshot, so editing a setup during a run can't change a video
that's queued), then a `TrackRunner` tracks them one at a time on a worker
thread. The worker never touches tkinter: it puts messages on a queue that the
GUI reads with `poll()` (ROADMAP §12, Stage 7).

Messages, as tuples whose first item is the kind:
    ("reference", i)              making video i's reference image
    ("progress", i, done, total)  frames tracked so far
    ("done", i, data, csv_path)   saved and loaded (TrackingData)
    ("failed", i, reason)         this video failed; the others carry on
    ("cancelled", i)              stopped during video i (nothing saved for it)
    ("finished",)                 the run is over (always last)
"""

from __future__ import annotations

import os
import queue
import threading
import traceback
from dataclasses import dataclass

import numpy as np

from .loader import TrackingData, load_csv
from .tracking import (Region, Scale, TrackingParams, assemble_output, make_reference,
                       save_outputs, track_video)
from .video import Prep
from .asr import ASR_TEST, MOTION_SUFFIX, AsrJob, run_asr_job
from .objects import objects_to_text
from .video_setup import OBJECT_TEST, VideoSetup


@dataclass
class TrackJob:
    """Everything needed to track one video, copied from its setup."""
    path: str
    params: TrackingParams
    prep: Prep
    start: int
    end: int
    mask: np.ndarray | None
    regions: list[Region]
    shape: tuple[int, int]
    scale: Scale | None
    reference: np.ndarray | None      # None: make it in the worker
    reference_frames: int
    exclusion_count: int
    fps: float
    extra: dict | None = None         # more settings columns (object recognition)


def make_job(setup: VideoSetup, params: TrackingParams, dsmpl: float,
             reference_frames: int, test: str) -> TrackJob:
    """Snapshot a video's setup for tracking. The setup window's reference is
    reused when it was made from the current trim, crop and settings."""
    reference = None
    if setup.reference_current(dsmpl, reference_frames):
        reference = setup.reference.copy()
    return TrackJob(
        path=setup.path,
        params=TrackingParams(**vars(params)),
        prep=setup.prep(dsmpl),
        start=setup.start,
        end=setup.end_frame,
        mask=setup.exclusion_mask(dsmpl),
        regions=setup.tracking_regions(dsmpl, test),
        shape=setup.prepared_shape(dsmpl),
        scale=setup.scale(dsmpl),
        reference=reference,
        reference_frames=int(reference_frames),
        exclusion_count=len(setup.exclusions),
        fps=float(setup.info.fps or 0),
        extra=object_settings(setup, dsmpl) if test == OBJECT_TEST else None,
    )


def object_settings(setup: VideoSetup, dsmpl: float) -> dict:
    """The tracking file's object recognition columns (ROADMAP §15)."""
    return {"Objects": objects_to_text(setup.tracking_objects(dsmpl)),
            "Trial_Day": setup.trial_day, "Trial_Phase": setup.trial_phase}


def run_job(job: TrackJob, progress=None, should_cancel=None,
            on_reference=None) -> tuple[TrackingData, str] | None:
    """Track one video and save `<name>_LocationOutput.csv` and
    `<name>_reference.png` next to it. Returns (loaded data, csv path), or
    None if cancelled (nothing is saved then)."""
    if isinstance(job, AsrJob):
        return run_asr_job(job, progress=progress, should_cancel=should_cancel)
    reference = job.reference
    if reference is None:
        if on_reference:
            on_reference()
        reference = make_reference(job.path, job.prep, job.start, job.end,
                                   num_frames=job.reference_frames)
    if should_cancel and should_cancel():
        return None
    result = track_video(job.path, reference, job.params, job.prep, job.start, job.end,
                         job.mask, progress=progress, should_cancel=should_cancel)
    if result.cancelled:
        return None
    if result.df is None or result.df.empty:
        raise ValueError("No frames could be tracked between the start and the end.")
    out = assemble_output(job.path, result.df, job.params, job.prep, job.start,
                          job.regions, job.shape, job.scale, job.reference_frames,
                          job.exclusion_count, job.fps, extra=job.extra)
    paths = save_outputs(job.path, out, reference)
    data = load_csv(paths["csv"])
    data.missing_at_end = result.missing_at_end     # for the finished message
    return data, paths["csv"]


class TrackRunner:
    """Tracks `jobs` in order on a daemon thread. Read messages with `poll()`;
    `cancel()` stops after the current frame and keeps finished videos."""

    def __init__(self, jobs: list[TrackJob]):
        self.jobs = jobs
        self.messages: queue.Queue = queue.Queue()
        self._cancel = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def alive(self) -> bool:
        return self._thread.is_alive()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def poll(self) -> list[tuple]:
        """Every message waiting, oldest first."""
        out = []
        while True:
            try:
                out.append(self.messages.get_nowait())
            except queue.Empty:
                return out

    def _run(self) -> None:
        put = self.messages.put
        try:
            for i, job in enumerate(self.jobs):
                if self._cancel.is_set():
                    break
                try:
                    got = run_job(
                        job,
                        progress=lambda done, total, i=i: put(("progress", i, done, total)),
                        should_cancel=self._cancel.is_set,
                        on_reference=lambda i=i: put(("reference", i)),
                    )
                except PermissionError:
                    put(("failed", i, "the tracking file is open in another program "
                                      "(e.g. Excel). Close it and track again."))
                    continue
                except Exception as exc:  # report it; carry on with the others
                    traceback.print_exc()
                    put(("failed", i, str(exc) or type(exc).__name__))
                    continue
                if got is None:
                    put(("cancelled", i))
                    break
                data, csv_path = got
                put(("done", i, data, csv_path))
        finally:
            put(("finished",))


def existing_output(video_path: str, test: str = "") -> str | None:
    """The video's `_LocationOutput.csv` (for startle, its `_MotionIndex.csv`)
    if one is beside it."""
    ending = MOTION_SUFFIX if test == ASR_TEST else "_LocationOutput.csv"
    path = os.path.splitext(video_path)[0] + ending
    return path if os.path.exists(path) else None
