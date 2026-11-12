"""Checks for inputs at the edges: a file of one frame, a file with no
tracked position, and settings saved for a test the defaults don't list.

Run from the project folder:  app/.venv/bin/python app/tests/test_edge_cases.py
"""
import scratch  # noqa: F401  (first: temporary files go in app/tests/.tmp, removed after the run)
import json
import os
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import config, metrics, plotting
from core.loader import TrackingData

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)

def data(n, x=None):
    x = np.arange(n, dtype=float) if x is None else x
    df = pd.DataFrame({"Frame": np.arange(n), "X": x, "Y": x, "Distance_px": 1.0,
                       "Distance_cm": 0.1})
    return TrackingData("tiny_LocationOutput.csv", df, {}, [])

# A file so short its length shows as 0.00 s (one frame at a high frame rate).
row = metrics.summary_metrics(data(1), fps=240.0)
check("a one-frame file is summarized without an error, with no mean speed",
      row["Frames"] == 1 and row["Duration_s"] == 0.0 and "MeanSpeed_cm_s" not in row)
row = metrics.summary_metrics(data(100), fps=20.0)
check("mean speed = shown distance / shown length", row["MeanSpeed_cm_s"] == round(10.0 / 5.0, 3))
check("no frame rate: lengths are blank, nothing fails",
      np.isnan(metrics.summary_metrics(data(10), fps=0)["Duration_s"]))
check("an empty file gives no bins", metrics.binned_metrics(data(0), fps=20.0).empty)

# Time bins are true to the clock (user, 2026-11-11). 9.84 fps x 60 s is 590.4
# frames: cutting every bin at 590 frames put the last bin of a 65-minute
# session 2.6 s early.
fps, n = 9.84, 38376                       # 65 minutes
ranges = metrics._bin_ranges(n, fps, 60.0)
starts = np.array([lo for _b, lo, _hi in ranges])
check("every bin starts within half a frame of its time on the clock",
      np.all(np.abs(starts / fps - 60.0 * np.arange(len(ranges))) <= 0.5 / fps + 1e-9))
check("bins meet end to start, cover every frame once, and none is empty",
      ranges[0][1] == 0 and ranges[-1][2] == n
      and all(a[2] == b[1] for a, b in zip(ranges, ranges[1:]))
      and all(hi > lo for _b, lo, hi in ranges))
check("bins hold 590 or 591 frames (not all 590, drifting early)",
      {hi - lo for _b, lo, hi in ranges[:-1]} == {590, 591} and len(ranges) == 65)
check("a frame rate that divides evenly gives the same bins as before",
      metrics._bin_ranges(2500, 20.0, 60.0) == [(1, 0, 1200), (2, 1200, 2400), (3, 2400, 2500)])
check("no bins without a frame rate, a bin length or frames",
      metrics._bin_ranges(100, 0, 60) == [] and metrics._bin_ranges(100, 20, 0) == []
      and metrics._bin_ranges(0, 20, 60) == [])
long = data(n)
bins = metrics.binned_metrics(long, fps=fps, bin_seconds=60.0)
total = metrics.summary_metrics(long, fps=fps)
check("the Time Bins table shows the clock times and adds up to the session",
      list(bins["Start_s"][:3]) == [0.0, 60.0, 120.0] and bins["End_s"].iloc[-1] == round(n / fps, 2)
      and bins["Frames"].sum() == n
      and abs(bins["Distance_cm"].sum() - total["TotalDistance_cm"]) < 0.01)

# A video that can't be read to the end of the session: tracking says how
# many of the frames asked for are missing, instead of just being shorter.
import cv2
from core import tracking, video
with tempfile.TemporaryDirectory() as tmp:
    clip = os.path.join(tmp, "clip.mp4")
    writer = cv2.VideoWriter(clip, cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 48))
    for i in range(30):
        frame = np.full((48, 64, 3), 200, np.uint8); frame[20:28, 2 * i:2 * i + 8] = 30
        writer.write(frame)
    writer.release()
    ref = np.full((48, 64), 200.0)
    full = tracking.track_video(clip, ref, tracking.TrackingParams())
    check("a video read to its end has nothing missing",
          len(full.df) == 30 and full.missing_at_end == 0)
    real_frames = video.VideoReader.frames
    def stops_early(self, start=0, end=None):
        for index, frame in real_frames(self, start, end):
            if index >= 10:
                return              # nothing readable from frame 10 on
            yield index, frame
    video.VideoReader.frames = stops_early
    try:
        cut = tracking.track_video(clip, ref, tracking.TrackingParams())
    finally:
        video.VideoReader.frames = real_frames
    check("a video that can't be read past frame 10 reports the 20 frames it's short by",
          len(cut.df) == 10 and cut.missing_at_end == 20)

# A file where the animal was never found: the heatmap says so.
none = data(5, x=np.full(5, np.nan))
fig = plotting.heatmap_figure(none)
check("heatmap of a file with no tracked positions says so instead of failing",
      any("no tracked positions" in t.get_text() for t in fig.axes[0].texts))
fig = plotting.path_figure(none)
check("path plot of the same file is drawn (empty)", len(fig.axes) >= 1)
fig = plotting.heatmap_figure(data(50))
check("a normal heatmap still has its color bar", len(fig.axes) == 1 and fig.axes[0].child_axes)

# Per-test settings: a number saved for a test the defaults don't list is kept.
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "config.json")
    cfg = config.load_config(path)
    cfg["scale_cm"]["Object Recognition"] = 38.5           # as the setup window saves it
    cfg["session_minutes"]["Acoustic Startle Response"] = 12
    cfg["scale_cm"]["Open Field"] = 45.0
    config.save_config(cfg, path)
    back = config.load_config(path)
    check("the scale length typed for Object Recognition is remembered",
          back["scale_cm"].get("Object Recognition") == 38.5)
    check("a session length for a test without a default is remembered",
          back["session_minutes"].get("Acoustic Startle Response") == 12.0)
    check("listed tests are kept as before", back["scale_cm"]["Open Field"] == 45.0
          and back["scale_cm"]["Elevated Plus Maze"] == 75.0)
    raw = json.load(open(path))
    raw["scale_cm"]["Object Recognition"] = "wide"; raw["scale_cm"]["Made up"] = True
    raw["plot"]["not a setting"] = 1
    json.dump(raw, open(path, "w"))
    back = config.load_config(path)
    check("a value that isn't a number is dropped; other settings' unknown keys still are",
          "Object Recognition" not in back["scale_cm"] and "Made up" not in back["scale_cm"]
          and "not a setting" not in back["plot"])

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
