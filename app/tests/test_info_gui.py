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
gui.ask_yes_no = lambda p, t, m, **k: (log.append(t), shown.append(m), True)[2]
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

check("there's an Experiment tab, showing the selected file's animal and task without Analyze",
      app.nb.tab(app.tab_experiment, "text") == "Experiment"
      and ("Animal", "Animal ID", "M7") in [tuple(app.experiment_tree.item(i, "values"))
                                            for i in app.experiment_tree.get_children()]
      and ("Task", "Assay", "Open Field") in [tuple(app.experiment_tree.item(i, "values"))
                                              for i in app.experiment_tree.get_children()]
      and "2026-11-12_09-15-00_OF2_info.json" in app.experiment_note.get())

clear(); ticks[:] = ["left"]
second = recording("2026-11-12_09-30-00", "OF2", "Open Field", duration_set_min=0.25)
app.add_files([second]); app.update()
check("a second video of the same test isn't asked about the test again; ticking Track "
      "Tamer's side keeps its value",
      [a[0] for a in asked] == ["The setup and the info file disagree"]
      and asked[0][1] == [("Session length", "60 min", "0.25 min")]
      and app.files[1].video.length_s == 3600 and app.files[1].video.length_default == "Open Field")

# The second video's setup starts from the first's (same arena and camera).
v.crop = (10.0, 20.0, 600.0, 500.0)
v.regions["center"] = ([200.0, 400.0, 400.0, 200.0], [150.0, 150.0, 350.0, 350.0])
v.scale_points, v.scale_cm = [(0.0, 0.0), (300.0, 0.0)], 40.0
app._set_selection([1], focus=1); app.open_setup(); app.update()
v2 = app.files[1].video
check("opening setup on a video with nothing drawn starts it from the last video set up in "
      "the same arena, as a draft with no step ticked",
      v2.crop == v.crop and list(v2.regions) == ["center"] and v2.scale_cm == 40.0
      and v2.draft_source == app.files[0].label and v2.steps_done == set()
      and v2.length_s == 3600 and "Started from" in app._setup_win.info_label.cget("text"))
v2.crop = (0.0, 0.0, 50.0, 50.0)
app._setup_win._show_video(); app.update()
check("the draft is taken once: what the user changes afterwards is kept",
      v2.crop == (0.0, 0.0, 50.0, 50.0))
app._close_setup_window(); app.update()
second_info = os.path.join(tmp, "2026-11-12_09-30-00_OF2_info.json")
kept = json.load(open(second_info, encoding="utf-8"))
own = kept["cameras"][0].get("track_tamer", {})
check("closing setup saves the video's setup in its info file, before any tracking",
      own.get("setup", {}).get("crop") == [0.0, 0.0, 50.0, 50.0]
      and own["setup"]["steps_done"] == [] and "tracking" not in own
      and "setup_changed_since_tracking" not in own
      and kept["animal_id"] == "M7" and kept["duration_set_min"] == 0.25)
check("a video whose setup was never opened has nothing saved",
      "track_tamer" not in json.load(open(os.path.join(tmp, "2026-11-12_09-15-00_OF2_info.json"),
                                          encoding="utf-8"))["cameras"][0])
app.open_setup(); app.update()
app._setup_win._mark("trim"); app._close_setup_window(); app.update()
app.clear_files(); clear(); ticks[:] = ["left"]
app.add_files([second]); app.update()
again = app.files[0]
check("added again, it comes back with what was drawn and only the steps that were done, "
      "not yet tracked, and isn't asked about again",
      again.restored and again.data is None and again.video.crop == (0.0, 0.0, 50.0, 50.0)
      and again.video.steps_done == {"trim"} and not asked
      and app.file_tree.item("0", "values")[2] == "Needs setup")
app.add_files([first]); app.update()
v = app.files[1].video

clear(); ticks[:] = [None]
third = recording("2026-11-12_09-45-00", "OF2", "Open Field", duration_set_min=0.75)
app.add_files([third]); app.update()
check("closing the window without choosing changes nothing",
      len(asked) == 1 and app.files[-1].video.length_s == 3600)

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
slow = recording("2026-11-12_11-00-00", "OF3", "Open Field", duration_set_min=60)
info_path = os.path.join(tmp, "2026-11-12_11-00-00_OF3_info.json")
raw = json.load(open(info_path)); raw["cameras"][0].update(fps_measured=15.0, width_px=800, height_px=600)
json.dump(raw, open(info_path, "w"))
was = app.fps_var.get()
app.add_files([slow]); app.update()
check("a measured frame rate that isn't the Frame rate setting is shown beside it, and the "
      "tick sets the box",
      asked and asked[-1][1] == [("Frame rate", f"{was} fps", "15 fps (measured)")]
      and app.fps_var.get() == "15" and app.config_data["fps"] == 15.0)
check("Track's own frame-rate check goes by the measured rate too",
      app._video_rate(app.files[0]) == 15.0)
said = shown[log.index("The info files report problems")] if "The info files report problems" in log else ""
check("a frame size in the info file that isn't the video's is reported",
      "800 x 600 px, the video's are 1280 x 720" in said)
app.fps_var.set(was); app.config_data["fps"] = float(was)

app.clear_files(); clear()
plain = os.path.join(tmp, "plain.mp4")
shutil.copy(PRACTICE, plain)
app.add_files([plain]); app.update()
check("a video with no info file is added without questions, with a blank ID",
      app.files[0].info is None and not asked and not log
      and app.summary_tree.item(app.summary_tree.get_children()[0], "values")[1] == "")
check("its Experiment tab says no info file was found, with the rows blank",
      "no recording app's info file" in app.experiment_note.get()
      and ("Animal", "Animal ID", "") in [tuple(app.experiment_tree.item(i, "values"))
                                          for i in app.experiment_tree.get_children()])

# Many repeated frames in a plus maze session: flagged after Analyze.
from samples import EPM
if os.path.exists(EPM):
    import pandas as pd
    table = pd.read_csv(EPM, low_memory=False)
    table["Frame_Repeated"] = [i % 10 == 3 for i in range(len(table))]
    table.to_csv(os.path.join(tmp, "repeats_LocationOutput.csv"), index=False)
    table["Frame_Repeated"] = [i == 3 for i in range(len(table))]
    table.to_csv(os.path.join(tmp, "few_LocationOutput.csv"), index=False)
    app.clear_files(); app.test_var.set("Elevated Plus Maze"); app._on_test_type(); clear()
    app.add_files([os.path.join(tmp, "repeats_LocationOutput.csv"),
                   os.path.join(tmp, "few_LocationOutput.csv")]); app.update()
    app.select_all(); app.analyze(); app.update()
    said = shown[log.index("Many frames are repeats")] if "Many frames are repeats" in log else ""
    check("a session with more repeated frames than the limit is flagged after Analyze; one "
          "with a few isn't",
          "(10.0%) are repeats" in said and said.count("•") == 1 and "above 5%" in said
          and app.files[0].summary["RepeatedFrames"] == sum(i % 10 == 3 for i in range(len(table)))
          and app.files[1].summary["RepeatedFrames"] == 1)
    check("the limit is a box in the settings panel, shown for this test",
          app.repeat_var.get() == "5" and bool(app.repeat_entry.winfo_manager())
          and str(app.repeat_entry.cget("state")) != "disabled")
    clear(); app.repeat_var.set("12"); app.analyze(); app.update()
    check("raising the limit above a session's share stops the flag, and the limit is saved",
          "Many frames are repeats" not in log and app.config_data["repeated_warn_pct"] == 12)
    clear(); app.repeat_var.set("lots"); app.analyze(); app.update()
    check("a limit that isn't a number keeps the last good one",
          "Many frames are repeats" not in log and app.config_data["repeated_warn_pct"] == 12)
else:
    print("skip the repeats warning (the plus maze example is missing)")

app.destroy()
shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
