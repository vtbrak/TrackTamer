"""The recording app's info file in the main window (ROADMAP §16): the test
type and session length it names are shown side by side with Track Tamer's
when they differ, the experimenter's ticks are applied, problems the
recording app noted are reported, and the animal's ID shows in the list.

Run from the project folder:  .venv/bin/python tests/test_info_gui.py
"""
import scratch  # noqa: F401  (first: temporary files go in app/tests/.tmp, removed after the run)
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
# Videos without an info file: the window's rows are recorded, the queued
# actions are done for the first row ("choose" / "animal"), and the queued
# answer is returned (True = Done, None = closed).
missing, todo, answer = [], [], [None]
def missing_info(parent, rows, choose, animal):
    missing.append([label for _, label in rows])
    done = [(choose if what == "choose" else animal)(rows[0][0]) for what in todo]
    del todo[:]
    missing.append(done)
    return answer[0]
gui.show_missing_info = missing_info
picker = {"path": "", "opened_in": None}
def pick_file(**k):
    picker["opened_in"] = k.get("initialdir")
    return picker["path"]
gui.filedialog.askopenfilename = pick_file
typed = {}
gui.ask_animal = lambda parent, video, start: (typed.update(start=dict(start)), typed.get("values"))[1]
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

# --- videos that came without an info file -----------------------------------
app.clear_files(); clear(); del missing[:]
old_folder = os.path.join(tmp, "older"); os.makedirs(old_folder)
plain = os.path.join(old_folder, "6_2024-04-01_11-49-23.mp4")
shutil.copy(PRACTICE, plain)
own_json = os.path.join(old_folder, "6_2024-04-01_11-49-23_info.json")
answer[0] = None
app.add_files([plain]); app.update()
check("a video with no info file is asked about; closing the window leaves it as it is",
      missing[0] == ["6_2024-04-01_11-49-23.mp4"] and app.files[0].info is None
      and not os.path.exists(own_json) and not asked
      and app.summary_tree.item(app.summary_tree.get_children()[0], "values")[1] == "")
check("its Experiment tab says no info file was found, with the rows blank, and offers "
      "to add the animal's information",
      "no recording app's info file" in app.experiment_note.get()
      and ("Animal", "Animal ID", "") in [tuple(app.experiment_tree.item(i, "values"))
                                          for i in app.experiment_tree.get_children()]
      and str(app.animal_btn.cget("state")) == "normal")

# Choosing a file that isn't an info file, then cancelling the picker.
app.clear_files(); clear(); del missing[:]
junk = os.path.join(tmp, "notes.json"); open(junk, "w").write("[1, 2]")
picker["path"] = junk; todo[:] = ["choose"]; answer[0] = None
app.add_files([plain]); app.update()
check("the file picker opens in the video's own folder; a file that isn't an info file is "
      "refused with a note",
      picker["opened_in"] == old_folder and "Not an info file" in log
      and missing[1] == [None] and app.files[0].info is None)

# Choosing the real info file (kept in another folder, listing the video
# under the name it had when it was recorded).
app.clear_files(); clear(); del missing[:]
source = os.path.join(tmp, "from the recording computer_info.json")
with open(source, "w") as f:
    json.dump({"schema_version": 1, "app_name": "Creature Capture", "assay": "Open Field",
               "animal_id": "M6", "treatment": "drug A", "duration_set_min": 0.5,
               "cameras": [{"label": "Overhead", "video": "2024-04-01_11-49-23_OF_Overhead.mp4"}]}, f)
picker["path"] = source; todo[:] = ["choose"]; answer[0] = True
app.test_var.set("Open Field"); app._on_test_type(); clear()
app.add_files([plain]); app.update()
e = app.files[0]
check("the chosen info file is copied into the video's own info file, and used straight away",
      missing[1] == ["info file: from the recording computer_info.json"] and os.path.exists(own_json)
      and e.info.animal_id == "M6" and e.info.from_recording_app
      and app.summary_tree.item(app.summary_tree.get_children()[0], "values")[1] == "M6")
check("it goes through the same checks as any info file (its session length is shown "
      "beside Track Tamer's)",
      asked and asked[-1][1] == [("Session length", "60 min", "0.5 min")])
check("information from a recording app can't be changed by typing",
      str(app.animal_btn.cget("state")) == "disabled")
app.clear_files(); clear(); del missing[:]
app.add_files([plain]); app.update()
check("added again, the video has its info file and isn't asked about",
      missing == [] and app.files[0].info.animal_id == "M6")
os.remove(own_json)

# No info file: the animal's information is typed in instead.
app.clear_files(); clear(); del missing[:]
typed["values"] = {"animal_id": "M9", "sex": "F", "strain": "C57BL/6J", "dob": "2024-02-01",
                   "treatment": "saline", "cohort": "", "date": "2024-04-01",
                   "experimenter": "ES", "trial_day": "1", "notes": ""}
todo[:] = ["animal"]; answer[0] = True
app.add_files([plain]); app.update()
e = app.files[0]
saved = json.load(open(own_json, encoding="utf-8"))
check("the animal's information can be typed in, starting from the date in the file name",
      typed["start"]["date"] == "2024-04-01" and missing[1] == ["animal: M9"]
      and e.info.animal_id == "M9" and not e.info.from_recording_app)
check("it's saved as the standard's fields in an info file beside the video",
      saved["animal_id"] == "M9" and saved["dob"] == "2024-02-01" and saved["trial_day"] == 1
      and saved["start_time"] == "11:49:23" and saved["app_name"] == "Track Tamer"
      and "cohort" not in saved and saved["cameras"][0]["video"] == os.path.basename(plain))
rows_now = [tuple(app.experiment_tree.item(i, "values")) for i in app.experiment_tree.get_children()]
check("the Experiment tab shows it, with the age worked out, and it can be changed there",
      ("Animal", "Animal ID", "M9") in rows_now and ("Animal", "Age (days)", "60") in rows_now
      and str(app.animal_btn.cget("state")) == "normal")
typed["values"] = dict(typed["values"], animal_id="M9b", notes="ear notch")
app._set_selection([0], focus=0); app.edit_animal_info(); app.update()
check("changing it from the Experiment tab starts from what was saved and updates the list",
      typed["start"]["animal_id"] == "M9" and app.files[0].info.animal_id == "M9b"
      and app.summary_tree.item(app.summary_tree.get_children()[0], "values")[1] == "M9b"
      and json.load(open(own_json, encoding="utf-8"))["notes"] == "ear notch")
os.remove(own_json)

# Neither: Done with nothing chosen still leaves an info file, so it isn't asked again.
app.clear_files(); clear(); del missing[:]
answer[0] = True
app.add_files([plain]); app.update()
made = json.load(open(own_json, encoding="utf-8"))
check("Done with nothing added still gives the video an info file of its own",
      made["cameras"][0]["video"] == os.path.basename(plain)
      and made["cameras"][0]["track_tamer"] == {"asked_for_info": True}
      and app.files[0].info is not None and not app.files[0].info.recorded and not asked)
app.clear_files(); clear(); del missing[:]
app.add_files([plain]); app.update()
check("so it isn't asked about again, and its animal information can still be added later",
      missing == [] and str(app.animal_btn.cget("state")) == "normal")
answer[0] = None

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
