"""Checks that saving never destroys what was already saved: every result
file is written whole under a temporary name before it replaces the earlier
one (core/safe_write.py), the crop is recorded exactly, and saving works in a
folder with accented letters in its name.

Run from the project folder:  app/.venv/bin/python app/tests/test_saving.py
"""
import os
import sys
import tempfile

import cv2
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import export, objects, playback, tracking
from core.loader import load_csv
from core.safe_write import replacing, saving_path, write_csv
from core.video import Prep

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)

def read(path):
    with open(path, "rb") as f:
        return f.read()

tmp = tempfile.mkdtemp()

# --- the helper ------------------------------------------------------------
target = os.path.join(tmp, "result.csv")
open(target, "w").write("earlier")
try:
    with replacing(target) as part:
        open(part, "w").write("half of the new")
        raise RuntimeError("the disk filled up")
except RuntimeError:
    pass
check("a save that fails partway leaves the earlier file as it was",
      read(target) == b"earlier" and not os.path.exists(saving_path(target)))
with replacing(target) as part:
    open(part, "w").write("new")
check("a save that finishes replaces it, leaving no temporary file",
      read(target) == b"new" and os.listdir(tmp) == ["result.csv"])
with replacing(target) as part:
    pass
check("nothing written: the earlier file stays", read(target) == b"new")
check("the temporary name keeps the file's ending (writers pick their format from it)",
      saving_path("a/b/clip_tracked.mp4").endswith(".mp4")
      and saving_path("x_analysis.xlsx").endswith(".xlsx"))
write_csv(pd.DataFrame({"a": [1, 2]}), target)
check("write_csv writes the table without an index column", read(target).split() == [b"a", b"1", b"2"])

# --- the tracking file and its reference image -------------------------------
folder = os.path.join(tmp, "Vidéos de José 東京")     # accented and non-English letters
os.mkdir(folder)
video = os.path.join(folder, "trial.mp4")
tracked = pd.DataFrame({"Frame": [0, 1], "X": [5.0, 6.0], "Y": [5.0, 5.0],
                        "Distance_px": [0.0, 1.0], "Frame_Unreadable": [False, False]})
crop = (119.96, 35.5, 534.31, 458.02)
out = tracking.assemble_output(video, tracked, tracking.TrackingParams(), Prep(1.0, crop), 3,
                               None, (422, 414), None, 50, 0, 10.0)
reference = np.full((422, 414), 200.0)
paths = tracking.save_outputs(video, out, reference)
data = load_csv(paths["csv"])
ref_back = playback.load_reference(data)
check("tracking file and reference image are saved in a folder with accented letters",
      data.n_frames == 2 and ref_back is not None and ref_back.shape == (422, 414)
      and int(ref_back[0, 0]) == 200)
check("only the two result files are left in the folder",
      sorted(os.listdir(folder)) == ["trial_LocationOutput.csv", "trial_reference.png"])
back = playback.prep_from_settings(data.settings)
check("the crop is recorded exactly, so playback cuts the same pixels as tracking did",
      back.crop == crop and back.dsmpl == 1.0)
check("an older file's crop (one decimal) is still read",
      playback.prep_from_settings({"Downsample": 1.0, "Crop": "80.0,20.8,502.4,439.6"}).crop
      == (80.0, 20.8, 502.4, 439.6))
check("no crop is recorded as blank", tracking.crop_text(None) == "")

before = read(paths["csv"]), read(paths["reference"])
class Unwritable(pd.DataFrame):
    """A table whose save dies partway: some of the file is written, then
    the disk is full."""
    def to_csv(self, path, *a, **k):
        with open(path, "w") as f:
            f.write("File,Frame\nhalf a")
        raise OSError("No space left on device")
try:
    tracking.save_outputs(video, Unwritable(out), np.zeros((422, 414)))
    raised = False
except OSError:
    raised = True
check("a tracking file that can't be written leaves the earlier file AND its reference",
      raised and (read(paths["csv"]), read(paths["reference"])) == before
      and len(os.listdir(folder)) == 2)

# --- scoring ---------------------------------------------------------------
scoring = objects.Scoring()
scoring.add_bout("object 1", 0, 1)
spath = objects.save_scoring(data, scoring, 10.0)
kept = read(spath)
real_table = objects.scoring_table
objects.scoring_table = lambda *a, **k: Unwritable(real_table(*a, **k))
try:
    scoring.add_bout("object 1", 5, 9)
    objects.save_scoring(data, scoring, 10.0)
    raised = False
except OSError:
    raised = True
finally:
    objects.scoring_table = real_table
check("a scoring file that can't be written leaves the earlier scoring file whole",
      raised and read(spath) == kept and not os.path.exists(saving_path(spath)))
check("scoring that couldn't be saved is still what the results and export use",
      objects.load_scoring(data) is scoring and len(objects.load_scoring(data).bouts) == 2)
objects.save_scoring(data, scoring, 10.0)       # the next change saves it
objects._unsaved.clear()
check("once a save works, the file holds everything",
      len(objects.load_scoring(data).bouts) == 2 and read(spath) != kept)

# --- the exported workbook and plots ---------------------------------------
xlsx = os.path.join(folder, "trial_analysis.xlsx")
settings = export.settings_table({"Tracking": {"Window": True}})
export.write_analysis_workbook(xlsx, {"File": "trial"}, None, settings)
kept = read(xlsx)
try:
    export.write_analysis_workbook(xlsx, {"File": "trial"}, "not a table", settings)
    raised = False
except Exception:
    raised = True
check("a workbook that fails partway leaves the earlier workbook whole",
      raised and read(xlsx) == kept and not os.path.exists(saving_path(xlsx)))
from matplotlib.figure import Figure
png = os.path.join(folder, "trial_path.png")
export.save_figure(Figure(), png)
check("plots are saved (also through a temporary file)",
      os.path.getsize(png) > 0 and not os.path.exists(saving_path(png)))

# --- the tracked video -------------------------------------------------------
writer = cv2.VideoWriter(video, cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (414, 422))
for i in range(12):
    writer.write(np.full((422, 414, 3), 10 * i, np.uint8))
writer.release()
long = pd.concat([tracked] * 6, ignore_index=True); long["Frame"] = range(12)
long_out = tracking.assemble_output(video, long, tracking.TrackingParams(), Prep(), 0,
                                    None, (422, 414), None, 50, 0, 10.0)
tracking.save_outputs(video, long_out, reference)
pb = playback.open_playback(load_csv(paths["csv"]))
made = playback.write_tracked_video(pb)
check("the tracked video is written", made == playback.tracked_video_path(video)
      and os.path.getsize(made) > 0)
kept = read(made)
calls = []
stopped = playback.write_tracked_video(pb, should_cancel=lambda: calls.append(1) or len(calls) > 4)
check("cancelling a save keeps the earlier tracked video and leaves nothing behind",
      stopped is None and read(made) == kept and not os.path.exists(saving_path(made)))
real_draw = playback.draw_tracking
def breaks(frame, pb_, row, *a, **k):
    if row == 5:
        raise RuntimeError("drawing failed")
    return real_draw(frame, pb_, row, *a, **k)
playback.draw_tracking = breaks
try:
    playback.write_tracked_video(pb)
    raised = False
except RuntimeError:
    raised = True
finally:
    playback.draw_tracking = real_draw
check("a save that fails partway keeps the earlier tracked video too",
      raised and read(made) == kept and not os.path.exists(saving_path(made)))

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
