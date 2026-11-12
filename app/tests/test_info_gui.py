"""The recording app's info file in the main window (ROADMAP §16): the test
type and session length it names are shown side by side with Track Tamer's
when they differ, the experimenter's ticks are applied, problems the
recording app noted are reported, and the animal's ID shows in the list.

Run from the project folder:  .venv/bin/python tests/test_info_gui.py
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from samples import practice_clip
PRACTICE = practice_clip()
if PRACTICE is None:
    sys.exit("The plus maze example video is missing from the Examples folder.")
tmp = tempfile.mkdtemp()
cfg = os.path.join(tmp, "config.json")
import gui, core
gui.load_config = lambda: core.load_config(cfg)
gui.save_config = lambda c: core.save_config(c, cfg)
log, shown, asked, ticks = [], [], [], []
for name in ("show_warning", "show_info", "show_error"):
    setattr(gui, name, lambda p, t, m, **k: (log.append(t), shown.append(m)))
gui.ask_yes_no = lambda p, t, m, **k: (log.append(t), True)[1]
def side_by_side(parent, title, message, rows, left, right, **k):
    """Records what was shown; ticks the queued side in every row."""
    asked.append((title, [(r[0], r[2], r[3]) for r in rows], (left, right)))
    side = ticks.pop(0) if ticks else "right"
    return None if side is None else [side] * len(rows)
gui.ask_side_by_side = side_by_side
gui.TrackTamerApp.wait_window = lambda self, w=None: None

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)


def recording(stamp, arena, assay, **more):
    """A video with its info file, as a recording app leaves them."""
    video = os.path.join(tmp, f"{stamp}_{arena}_Overhead.mp4")
    shutil.copy(PRACTICE, video)
    info = {"schema_version": 1, "app_name": "Creature Capture", "app_version": "0.2.0",
            "date": stamp[:10], "assay": assay, "arena": arena, "animal_id": "M7",
            "treatment": "saline", "duration_set_min": 0.5,
            "cameras": [{"label": "Overhead", "camera_position": "Camera5",
                         "camera_settings": {}, "video": os.path.basename(video)}], **more}
    with open(os.path.join(tmp, f"{stamp}_{arena}_info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
    return video


def clear():
    del log[:], shown[:], asked[:]


app = gui.TrackTamerApp(); app.update()
check("starts as an Elevated Plus Maze load", app.test_var.get() == "Elevated Plus Maze")
first = recording("2026-11-12_09-15-00", "OF2", "Open Field", stopped_early=True,
                  duration_actual_s=12.5)
app.add_files([first]); app.update()
e = app.files[0]; v = e.video
check("the test in the info file is shown beside Track Tamer's, and the tick is applied",
      asked[0] == ("Which test is this?", [("Test", "Elevated Plus Maze", "Open Field")],
                   ("Track Tamer", "Info file")) and app.test_var.get() == "Open Field")
check("then the session length: Open Field's standard beside the info file's",
      asked[1][1] == [("Session length", "60 min", "0.5 min")] and v.length_s == 30
      and v.length_default == "" and len(asked) == 2)
check("what the recording app noted is reported",
      "The info files report problems" in log
      and "stopped early (after 12.5 s)" in shown[log.index("The info files report problems")])
values = app.summary_tree.item(app.summary_tree.get_children()[0], "values")
check("the animal's ID shows beside the file as soon as it's added",
      list(app.summary_tree["columns"])[:3] == ["File", "animal_id", "Status"] and values[1] == "M7")

clear(); ticks[:] = ["left"]
second = recording("2026-11-12_09-30-00", "OF2", "Open Field", duration_set_min=0.25)
app.add_files([second]); app.update()
check("a second video of the same test isn't asked about the test again; ticking Track "
      "Tamer's side keeps its value",
      [a[0] for a in asked] == ["The setup and the info file disagree"]
      and asked[0][1] == [("Session length", "60 min", "0.25 min")]
      and app.files[1].video.length_s == 3600 and app.files[1].video.length_default == "Open Field")

clear(); ticks[:] = [None]
third = recording("2026-11-12_09-45-00", "OF2", "Open Field", duration_set_min=0.75)
app.add_files([third]); app.update()
check("closing the window without choosing changes nothing",
      len(asked) == 1 and app.files[2].video.length_s == 3600)

clear()
other = recording("2026-11-12_10-00-00", "EPM1", "Elevated Plus Maze")
app.add_files([other]); app.update()
check("a video from another test than the ones in the list is warned about, not switched to",
      "These files are from different tests" in log and app.test_var.get() == "Open Field"
      and not any(a[0] == "Which test is this?" for a in asked))

app.clear_files(); clear()
puzzle = recording("2026-11-12_10-15-00", "PuzzleBox", "Puzzle Box")
app.add_files([puzzle]); app.update()
check("an assay Track Tamer doesn't analyze leaves the test type for the user to choose",
      "Choose the test yourself" in log and app.test_var.get() == "Open Field"
      and not any(a[0] == "Which test is this?" for a in asked))

app.clear_files(); clear()
renamed = os.path.join(tmp, "2026-11-12_09-15-00_OF2_Overhead copy.mp4")
shutil.copy(PRACTICE, renamed)
app.add_files([renamed]); app.update()
check("a renamed video is matched to its info file only after asking",
      "Use these info files?" in log and app.files[0].info is not None
      and app.files[0].info.animal_id == "M7")

app.clear_files(); clear()
plain = os.path.join(tmp, "plain.mp4")
shutil.copy(PRACTICE, plain)
app.add_files([plain]); app.update()
check("a video with no info file is added without questions, with a blank ID",
      app.files[0].info is None and not asked and not log
      and app.summary_tree.item(app.summary_tree.get_children()[0], "values")[1] == "")

app.destroy()
shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
