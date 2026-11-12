"""Repeated frames in location tracking (ROADMAP §16; user, 2026-11-11): a
recording app writes the frame before again when the camera is late, so the
video keeps true time. Tracking marks those frames, the Summary counts them,
and speed is worked out across them (zero-then-double becomes the true speed).

Run from the project folder:  .venv/bin/python tests/test_repeats.py
"""
import scratch  # noqa: F401  (first: temporary files go in app/tests/.tmp, removed after the run)
import json
import os
import shutil
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import tracking
from core.loader import load_csv
from core.metrics import of_metrics, spread_repeats, summary_metrics
from core.track_run import recorded_repeats
from core.video import Prep

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)


same = lambda a, b: np.allclose(a, b, equal_nan=True)          # noqa: E731
r = lambda *flags: np.array(flags, dtype=bool)                  # noqa: E731
check("a repeat's zero-then-double step is shared out; the total is unchanged",
      same(spread_repeats([1, 0, 2, 1], r(0, 1, 0, 0)), [1, 1, 1, 1]))
check("a run of repeats is shared with the real frame after it",
      same(spread_repeats([3, 0, 0, 6, 3], r(0, 1, 1, 0, 0)), [3, 2, 2, 2, 3]))
check("frames with no repeat beside them are untouched",
      same(spread_repeats([1, 5, 1, 0, 4, 9], r(0, 0, 0, 1, 0, 0)), [1, 5, 1, 2, 2, 9]))
check("a repeat at the very end, and no repeats at all, change nothing they shouldn't",
      same(spread_repeats([2, 2, 0], r(0, 0, 1)), [2, 2, 0])
      and same(spread_repeats([2, 7, 1], r(0, 0, 0)), [2, 7, 1]))
check("a run with an unreadable frame in it is left as it is",
      same(spread_repeats([1, 0, np.nan, 4], r(0, 1, 1, 0)), [1, 0, np.nan, 4]))

tmp = tempfile.mkdtemp()
try:
    video = os.path.join(tmp, "2026-11-12_09-15-00_OF2_Overhead.mp4")
    check("a video with no info file says nothing about repeats", recorded_repeats(video) is None)
    camera = {"label": "Overhead", "video": os.path.basename(video),
              "timestamps_csv": "2026-11-12_09-15-00_OF2_Overhead_frames.csv",
              "repeated_frames": 2, "repeated_frame_indices": [7, 30]}
    with open(os.path.join(tmp, "2026-11-12_09-15-00_OF2_info.json"), "w") as f:
        json.dump({"schema_version": 1, "assay": "Open Field", "arena": "OF2",
                   "animal_id": "M1", "cameras": [camera]}, f)
    check("without the frame times file, the info file's own list is used",
          recorded_repeats(video) == {7, 30})
    pd.DataFrame({"frame": range(40), "video_time_s": np.arange(40) / 20,
                  "repeated": [i in (7, 12) for i in range(40)]}).to_csv(
        os.path.join(tmp, camera["timestamps_csv"]), index=False)
    check("the frame times file's marks and the info file's list are put together",
          recorded_repeats(video) == {7, 12, 30})

    # A session starting at video frame 5: rows 0..9 are video frames 5..14.
    # The animal moves 2 px a frame; the repeats (video frames 7 and 12) show
    # it still, then 4 px on.
    xs = [0, 2, 2, 6, 8, 10, 12, 12, 16, 18]
    tracked = pd.DataFrame({"Frame": range(10), "X": np.array(xs, float), "Y": 5.0,
                            "Distance_px": np.r_[0, np.abs(np.diff(xs))].astype(float),
                            "Frame_Unreadable": False})
    box = tracking.Region("center", [0, 30, 30, 0], [0, 0, 30, 30])
    out = tracking.assemble_output(video, tracked, tracking.TrackingParams(), Prep(), 5,
                                   [box], (40, 40), tracking.Scale(10, 10), 50, 0, 20.0,
                                   repeated=recorded_repeats(video))
    check("tracking marks the session's rows that are repeated video frames",
          list(np.flatnonzero(out["Frame_Repeated"])) == [2, 7])
    paths = tracking.save_outputs(video, out, np.zeros((40, 40)))
    data = load_csv(paths["csv"])
    check("the mark is kept in the tracking file and isn't taken for a region",
          "Frame_Repeated" in pd.read_csv(paths["csv"]).columns and data.regions == ["center"]
          and list(np.flatnonzero(data.repeated)) == [2, 7])
    s = summary_metrics(data, fps=20.0)
    check("the Summary counts them; the total distance is as tracked",
          s["RepeatedFrames"] == 2 and s["TotalDistance_px"] == 18.0)
    check("speed across a repeat is the true 2 px a frame, not 0 then 4",
          same(spread_repeats(data.df["Distance_px"].to_numpy(), data.repeated),
               [0, 2, 2, 2, 2, 2, 2, 2, 2, 2]))
    plain = tracking.assemble_output(video, tracked, tracking.TrackingParams(), Prep(), 5,
                                     [box], (40, 40), None, 50, 0, 20.0)
    check("a video whose recording app says nothing gets no column and no count",
          "Frame_Repeated" not in plain.columns
          and "RepeatedFrames" not in summary_metrics(
              load_csv(tracking.save_outputs(os.path.join(tmp, "plain.mp4"), plain,
                                             np.zeros((40, 40)))["csv"]), fps=20.0))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
