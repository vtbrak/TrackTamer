"""Checks for core/video.py and core/tracking.py using the plus maze example
video (Examples/, gitignored, so this only runs where it exists).

Run from the project folder:  app/.venv/bin/python app/tests/test_video.py
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import video

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from samples import EPM_VIDEO, require
require(EPM_VIDEO)

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)

# --- core/video.py ---
info = video.video_info(EPM_VIDEO)
check("video info", (info.width, info.height, info.frame_count) == (800, 600, 6419)
      and abs(info.fps - 16.64) < 0.01)
check("is_video", video.is_video("a/b.MP4") and not video.is_video("a/b.csv"))

with video.VideoReader(EPM_VIDEO) as r:
    f = r.read_at(460)
    check("read_at gives a grayscale full-size frame", f is not None and f.shape == (600, 800))
    check("read_at past the end gives None", r.read_at(10_000) is None)
    got = list(r.frames(100, 105))
    check("frames() yields the range in order", [i for i, _ in got] == list(range(100, 105)))
    check("frames() matches read_at", np.array_equal(got[0][1], r.read_at(100)))

prep = video.Prep(dsmpl=0.5, crop=(10, 20, 210, 120))
with video.VideoReader(EPM_VIDEO, prep) as r:
    check("downsample then crop", r.read_at(0).shape == (100, 200))
    tail = list(r.frames(info.frame_count - 3, info.frame_count + 50))
    check("frames() stops at the real end", [i for i, _ in tail][-1] == info.frame_count - 1
          or all(fr is not None for _, fr in tail))

bad, checked = video.check_readable(EPM_VIDEO)
check("readability check", checked == 300 and bad == 0)

m = video.polygon_mask((10, 10), [([2, 7, 7, 2], [2, 2, 7, 7])])
check("polygon mask", m.dtype == bool and m[4, 4] and not m[0, 0] and not m[9, 9])
check("empty mask", not video.polygon_mask((5, 5), []).any())

# --- core/tracking.py ---
import pandas as pd
from core import tracking

# A dark square on a light floor is found at its center.
ref = np.full((60, 80), 200.0)
frame = np.full((60, 80), 200, dtype=np.uint8); frame[20:30, 50:60] = 40
y, x, _ = tracking.locate(frame, ref, tracking.TrackingParams(use_window=False))
check("locate finds a dark animal", abs(x - 54.5) < 0.6 and abs(y - 24.5) < 0.6)
y, x, _ = tracking.locate(frame, ref, tracking.TrackingParams(method="light", use_window=False))
check("light method ignores a dark animal", not (abs(x - 54.5) < 2 and abs(y - 24.5) < 2))
mask = video.polygon_mask(ref.shape, [([45, 65, 65, 45], [15, 15, 35, 35])])
frame[40:50, 10:20] = 60
y, x, _ = tracking.locate(frame, ref, tracking.TrackingParams(use_window=False), mask)
check("exclusion shapes are ignored", abs(x - 14.5) < 0.6 and abs(y - 44.5) < 0.6)

# Region columns: blank when unreadable; periphery excludes the center;
# labels and transitions as ezTrack writes them.
pos = pd.DataFrame({"X": [5, 50, np.nan, 50, 95], "Y": [5, 50, np.nan, 50, 95]})
regions = [tracking.Region("center", [30, 70, 70, 30], [30, 30, 70, 70]),
           tracking.Region("periphery", [0, 100, 100, 0], [0, 0, 100, 100], subtract=["center"])]
cols = tracking.region_columns(pos, regions, (101, 101))
check("region columns", list(cols["center"]) == [False, True, None, True, False]
      and list(cols["periphery"]) == [True, False, None, False, True])
check("ROI_location", list(cols["ROI_location"]) == ["periphery", "center", None, "center", "periphery"])
check("ROI_transition skips the gap", list(cols["ROI_transition"]) == [False, True, False, False, True])

# Real video: re-tracking the start of the EPM example (Examples/, tracked in
# this app) with the settings and reference its tracking file recorded gives
# the same positions.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from samples import EPM as EX_CSV, EPM_VIDEO as EX_VIDEO
if os.path.exists(EX_CSV) and os.path.exists(EX_VIDEO):
    from core.loader import load_csv
    from core.playback import load_reference, prep_from_settings
    exd = load_csv(EX_CSV)
    st = exd.settings
    prep = prep_from_settings(st)
    reference = load_reference(exd).astype(float)
    params = tracking.TrackingParams(
        loc_thresh=float(st["Location_Thresh"]), method=str(st["Method"]),
        use_window=str(st["Use_Window"]).lower() == "true",
        window_size=int(float(st["Window_Size"])), window_weight=float(st["Window_Weight"]))
    start = int(float(st["Start_Frame"]))
    calls = []
    res = tracking.track_video(EX_VIDEO, reference, params, prep, start=start,
                               end=start + 300, progress=lambda d, t: calls.append((d, t)))
    b = exd.df.iloc[:300]
    d = np.hypot(res.df.X.to_numpy() - b.X.to_numpy(), res.df.Y.to_numpy() - b.Y.to_numpy())
    check(f"re-tracking the EPM example matches its tracking file "
          f"(median {np.nanmedian(d):.2f} px, 95th percentile {np.nanpercentile(d, 95):.2f} px)",
          np.nanmedian(d) < 1 and np.nanpercentile(d, 95) < 3)
    check("progress reported", calls and calls[-1] == (300, 300))
    check("no unreadable frames", res.unreadable == 0 and not res.df.Frame_Unreadable.any())
    stopped = tracking.track_video(EX_VIDEO, reference, params, prep, start=start,
                                   end=start + 300, should_cancel=lambda: True)
    check("cancel", stopped.cancelled and stopped.df is None)
    out = tracking.assemble_output(EX_VIDEO, res.df, params, prep, start,
                                   regions[:1], reference.shape, tracking.Scale(100, 25), 50, 0,
                                   16.64)
    check("output starts with ezTrack's columns",
          list(out.columns[:9]) == ["File", "Location_Thresh", "Use_Window", "Window_Weight",
                                    "Window_Size", "Start_Frame", "Frame", "X", "Y"])
    check("cm distance", np.allclose(out.Distance_cm, out.Distance_px * 0.25, equal_nan=True))
else:
    print("skip the EPM example re-tracking (Examples/ files missing)")

# --- core/video_setup.py: full-size shapes line up with prepared frames ---
from core.video_setup import VideoSetup
vs = VideoSetup(path=EPM_VIDEO, info=info, crop=(101, 51, 701, 551),
                exclusions=[([201, 301, 301, 201], [151, 151, 251, 251])])
for d in (1.0, 0.5):
    with video.VideoReader(EPM_VIDEO, vs.prep(d)) as r:
        shape = r.read_at(0).shape
    check(f"prepared shape at downsample {d}", vs.prepared_shape(d) == shape)
    check(f"exclusion mask matches the frame at downsample {d}",
          vs.exclusion_mask(d).shape == shape)
    xs, ys = vs.to_prepared([301], [251], d)
    back = vs.from_prepared(xs, ys, d)
    check(f"coordinates round-trip at downsample {d}", np.allclose(back, [[301], [251]]))
check("crop corner maps to 0,0 at full size", vs.to_prepared([101], [51], 1.0) == ([0], [0]))


# Session length (C5b), regions and scale (C6).
vs2 = VideoSetup(path=EPM_VIDEO, info=info, start=100, length_s=60)
check("end = start + length x fps", vs2.end_frame == 100 + round(60 * info.fps))
vs2.length_s = 10_000
check("end clamped to the video", vs2.end_frame == info.frame_count
      and vs2.video_shorter_than_length())
vs2.regions = {"arena outline": ([0, 800, 800, 0], [0, 0, 600, 600]),
               "center": ([200, 600, 600, 200], [150, 150, 450, 450])}
check("no Open Field regions missing", vs2.missing_regions("Open Field") == [])
check("EPM arms missing (center is shared)", len(vs2.missing_regions("Elevated Plus Maze")) == 4)
half = {r.name: r for r in vs2.tracking_regions(0.5, "Open Field")}
check("regions scaled by downsampling", np.allclose(half["center"].xs, [100, 300, 300, 100]))
vs2.scale_points = [(0, 0), (300, 400)]; vs2.scale_cm = 40
check("scale measured on the prepared frame", vs2.scale_px(1.0) == 500
      and vs2.scale_px(0.5) == 250 and abs(vs2.scale(0.5).cm_per_px - 0.16) < 1e-9)
# A border the center shares belongs to the center only (2026-11-05).
vs2.regions = {"center": ([300, 400, 400, 300], [300, 300, 400, 400]),
               "closed arm 2": ([300, 400, 400, 300], [400, 400, 600, 600])}
regs = vs2.tracking_regions(1.0, "Elevated Plus Maze")
arm = next(r for r in regs if r.name == "closed arm 2")
check("arms are written minus the center", arm.subtract == ["center"]
      and next(r for r in regs if r.name == "center").subtract == [])
on_border = pd.DataFrame({"X": [350.0, 350.0], "Y": [400.0, 500.0]})
cols = tracking.region_columns(on_border, regs, (600, 800))
check("a point on the shared border is center only; inside the arm is the arm",
      list(cols["center"]) == [True, False] and list(cols["closed arm 2"]) == [False, True]
      and list(cols["ROI_location"]) == ["center", "closed arm 2"])
vs3 = VideoSetup(path=EPM_VIDEO, info=info, steps_done={"regions", "scale", "tracking"})
vs3.copy_from(vs2)
check("start from previous copies regions, scale, length as a draft",
      vs3.regions == vs2.regions and vs3.regions is not vs2.regions
      and vs3.scale_cm == 40 and vs3.length_s == vs2.length_s
      and vs3.steps_done == {"tracking"})

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
