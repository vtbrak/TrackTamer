"""Acoustic startle in the GUI (ROADMAP §13): setup, the motion index run,
Analyze, the tabs and Export, on a copy of a paper clip. Settings go to a
temporary config.

Run from the project folder:  .venv/bin/python tests/test_asr_gui.py
"""
import scratch  # noqa: F401  (first: temporary files go in app/tests/.tmp, removed after the run)
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from samples import ASR_CLIP, require
require(ASR_CLIP)
tmp = tempfile.mkdtemp()
cfg = os.path.join(tmp, "config.json")
import numpy as np
import pandas as pd
import gui, core
gui.load_config = lambda: core.load_config(cfg)
gui.save_config = lambda c: core.save_config(c, cfg)
log, yesno, everything = [], [], []         # (`everything` is never cleared)
for name in ("show_warning", "show_info", "show_error"):
    setattr(gui, name, lambda p, t, m, **k: (log.append(t), everything.append(t)))
gui.ask_yes_no = lambda p, t, m, **k: (log.append(t), yesno.pop(0) if yesno else True)[1]
# A several-button question: a queued True picks the last button, False the
# one before it, None closes the window (which cancels).
def _choice(p, t, m, choices, default=None, **k):
    log.append(t)
    answer = yesno.pop(0) if yesno else True
    return None if answer is None else choices[-1] if answer else choices[-2]
gui.ask_choice = _choice
# Videos without an info file: the window isn't shown (closed without Done).
gui.show_missing_info = lambda *a, **k: None
import setup_window, review_panel
for mod in (setup_window, review_panel):
    mod.show_info, mod.show_warning = gui.show_info, gui.show_warning
review_panel.ask_yes_no = gui.ask_yes_no
setup_window.ask_yes_no = gui.ask_yes_no
gui.TrackTamerApp.wait_window = lambda self, w=None: None

CLIP = os.path.join(tmp, "clip.mp4")
shutil.copy(ASR_CLIP, CLIP)
fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)


app = gui.TrackTamerApp(); app.update()
app.test_var.set("Acoustic Startle Response"); app._on_test_type(); app.update()
tabs = [app.nb.tab(t, "text") for t in app.nb.tabs()]
check("the Startle by Level tab shows for startle only, with the threshold criterion box",
      app.nb.tab(app.tab_level, "state") == "normal" and app.asr_sd_var.get() == "2"
      and bool(app.asr_sd_entry.winfo_manager()))
check("startle settings and tabs replace the others",
      bool(app.asr_bar.winfo_manager()) and not app.entries_section.winfo_manager()
      and tabs[:4] == ["Data Summary", "Trials", "Motion Trace", "Aligned Trials"]
      and not app.path_col.winfo_manager())
app.add_files([CLIP]); app.update()
e = app.files[0]; v = e.video
check("a startle video defaults to its whole length", v.end_frame == 101)
app.open_setup(); app.update()
win = app._setup_win
check("two setup steps: no crop and no exclusions for startle (the motion index is always "
      "of the whole picture), and no Stimuli step (they come from the recording's info file)",
      list(win.step_buttons) == ["trim", "threshold"]
      and [win._title(k) for k in win.step_buttons] == ["1  Trim", "2  Threshold"]
      and "no crop" in win.instructions.cget("text")
      and not win.canvas.bind("<B1-Motion>"))
v.crop = (0.0, 0.0, 372.0, 240.0)           # (as left by another test type)
v.exclusions.append(([0.0, 100.0, 100.0], [0.0, 0.0, 100.0]))
win._go("threshold"); app.update()
win.scrub.set(51); win._load_scrub_frame(); app.update()
text15 = win.threshold_text.cget("text")
check("the preview reports the motion index for the frame shown", "0.8" in text15 and "of 357,120" in text15)
app.asr_threshold_var.set("60"); app.update()
check("changing the threshold updates the preview, and the slider follows",
      win.threshold_text.cget("text") != text15 and round(float(win.threshold_scale.get())) == 60
      and app.config_data["asr_threshold"] == 60)
app.asr_threshold_var.set("15"); app.update()
check("the Threshold step says where the stimuli come from: none here (no info file)",
      "No stimuli were found" in win.stimuli_note.cget("text"))
log.clear(); win.step = "threshold"; v.steps_done.update({"trim"})
win._step_by(1); app.update()
check("Threshold is the last step: setup is complete after it",
      v.ready_for("Acoustic Startle Response") and "threshold" in v.steps_done)
app._set_selection([0], focus=0); app.update()
log.clear(); yesno.append(False); app.track(); app.update()
check("Track names a video with no stimuli and asks before working out a motion index with "
      "no trials; Cancel tracks nothing",
      "Some videos have no stimuli" in log and app._runner is None and e.data is None)
# Stimulus frames typed in for a video in an earlier version (kept in its saved setup) still count.
v.stimulus_frames = [50]
from core.asr import stimulus_note
check("frames typed in an earlier version are still used, and said so",
      stimulus_note(CLIP, v.stimulus_frames)[0] == 1
      and "typed in" in stimulus_note(CLIP, v.stimulus_frames)[1])
log.clear(); app.track(); app.update()
check("a video with stimuli is tracked without the question", "Some videos have no stimuli" not in log)
t0 = time.time()
while app._runner is not None and time.time() - t0 < 60:
    app.update(); time.sleep(0.02)
check("Track writes the motion index file",
      e.data is not None and e.data.path.endswith("clip_MotionIndex.csv") and os.path.exists(e.data.path))
log.clear(); app.analyze(); app.update()
s = e.summary
check("Analyze fills the Summary and trials, with no frame-rate prompt",
      e.analyzed and s["ASR_Trials"] == 1 and s["ASR_TrialsUsed"] == 1 and len(e.bins) == 1
      and "ASR_Mean_pulse_pct" in s and not log
      and not any("Habituation" in k for k in s)
      and not {"Prepulse_dB", "Interval_ms"} & set(e.bins.columns))
r = e.bins.iloc[0]
check("the paper clip's startle: peak on the frame after the stimulus, amplitude from the two windows",
      r["FrameNo"] == 51 and r["motion.index.after_pct"] > r["motion.index.before_pct"]
      and abs(r["Startle amplitude_pct"] - (r["motion.index.after_pct"] - r["motion.index.before_pct"])) < 1e-3)
print(f"   after {r['motion.index.after_pct']}  before {r['motion.index.before_pct']}  amplitude {r['Startle amplitude_pct']}  reaction {r['ReactionTime_ms']} ms")
check("a startle row says which day and session it is (blank here: the clip has no info file)",
      list(s)[:4] == ["File", "animal_id", "trial_day", "session_number"] and s["trial_day"] == ""
      and list(app.summary_tree["columns"])[:5] == ["File", "animal_id", "trial_day",
                                                    "session_number", "Status"])
check("Summary shows the key measures by default",
      {"ASR_Trials", "ASR_N_pulse", "ASR_Mean_pulse_pct"} <= set(app.summary_tree["columns"]))
check("Trials tab lists the trial with your headings",
      "Startle amplitude_pct" in app.bins_tree["columns"] and "Direction" not in app.bins_tree["columns"]
      and len(app.bins_tree.get_children()) == 1 and "1 trial" in app.bins_note.get())
# The startles listed in the Review tab, jumped to in the playback window.
from core.asr import AsrJob, run_asr_job, trial_table
from core.video import Prep
app.nb.select(app.review); app.update(); app._show_review(); app.update()
rv = app.review
check("Review tab lists the startles", rv.heading.cget("text") == "Startles"
      and len(rv.tree.get_children()) == 1 and not rv.cutoff_entry.winfo_manager()
      and rv.tree.item("0", "values")[3] == "50")
rv.tree.selection_set("0"); app.update()
pw = rv.window
check("clicking a startle opens the playback window at its stimulus",
      pw is not None and pw.row == 50 and pw.trial == 0 and "motion index" in pw.info.cget("text")
      and "+0 ms from the stimulus" in pw.info.cget("text"))
words = lambda: [pw.canvas.itemcget(i, "text") for i in pw.canvas.find_all() if pw.canvas.type(i) == "text"]
check("the stimulus frame is marked on the video", "STIMULUS" in words())
pw.go_peak(); app.update()
check("Go to peak shows the peak frame, marked, in the startle window",
      pw.row == 51 and "STARTLE PEAK" in words() and "startle window" in pw.info.cget("text"))
pw.step(-2); app.update()
check("the info line says when a frame is in the baseline window", "baseline window" in pw.info.cget("text"))
other = shutil.copy(CLIP, os.path.join(tmp, "many.mp4"))
many, _ = run_asr_job(AsrJob(other, Prep(), 0, 101, None, 15.0, 30.0, 0, [30, 50, 70, 500]))
rv.load(many, other, {}, 1.0, title="many", trials=trial_table(many)); app.update()
check("every stimulus is listed, and one outside the video is flagged",
      len(rv.tree.get_children()) == 4 and "outside" in rv.tree.item("3", "values")[-1])
rv.tree.selection_set("0"); app.update(); pw = rv.window
pw.go_trial(1); app.update()
check("Next trial jumps to the next stimulus and the list follows",
      pw.row == 50 and pw.trial == 1 and rv.tree.selection() == ("1",)
      and "Trial 2 of 4" in pw.trial_text.cget("text"))
pw.go_trial(-1); app.update()
check("Previous trial goes back", pw.row == 30 and rv.tree.selection() == ("0",))
pw.go_trial(1); pw.go_trial(1); pw.go_trial(1); app.update()
check("Next stops at the last trial in the video and says so",
      pw.row == 70 and "last trial" in pw.trial_text.cget("text"))
rv.tree.selection_set("3"); app.update()
check("a stimulus outside the video doesn't move the frame, and says why",
      pw.row == 70 and "outside" in pw.trial_text.cget("text"))
# A file from 0.9.4 or earlier that was tracked with a crop and exclusions.
from types import SimpleNamespace
from core.asr import load_motion, part_of_frame
older = shutil.copy(CLIP, os.path.join(tmp, "older.mp4"))
half = np.zeros((240, 372), bool); half[:120] = True
cropped, _ = run_asr_job(AsrJob(older, Prep(crop=(0, 0, 372, 240)), 0, 101, half, 15.0, 30.0, 2, [50]))
check("a file tracked on part of the picture says what was left out; a whole-frame one doesn't",
      part_of_frame(load_motion(cropped.path)) == "a crop and 2 exclusion shapes"
      and part_of_frame(many) == "" and part_of_frame(e.data) == "")
log.clear(); app._warn_part_of_frame([SimpleNamespace(label="older", data=cropped), e]); app.update()
check("Analyze warns about such files (their motion index isn't comparable until tracked again)",
      log == ["Some videos were tracked on part of the picture"])
app.nb.select(app.tab_summary); app.update(); rv.unload()
check("the habituation score's boxes start at the first 10 and last 40 responses, and lock "
      "at Analyze with the other startle settings",
      app.asr_first_var.get() == "10" and app.asr_last_var.get() == "40"
      and str(app.asr_first_entry.cget("state")) == "disabled"
      and str(app.asr_last_entry.cget("state")) == "disabled")
check("startle settings lock at Analyze; threshold locked after Track",
      str(app.asr_startle_entry.cget("state")) == "disabled"
      and str(app.asr_threshold_entry.cget("state")) == "disabled")
log.clear(); app.export(); app.update()
files = sorted(f for f in os.listdir(tmp) if f.startswith("clip_"))
print("   files:", files)
check("export writes the workbook and three images",
      {"clip_analysis.xlsx", "clip_trace.png", "clip_aligned.png", "clip_levels.png",
       "clip_MotionIndex.csv"} <= set(files)
      and "Export finished" in log)
sheets = pd.read_excel(os.path.join(tmp, "clip_analysis.xlsx"), sheet_name=None)
check("workbook has Experiment, Data Summary, Trials, Settings and Setup",
      list(sheets) == ["Experiment", "Data Summary", "Trials", "Settings", "Setup"]
      and "Startle amplitude_pct" in sheets["Trials"])
import json
saved = json.load(open(os.path.join(tmp, "clip_info.json")))["cameras"][0]
check("a video with no info file gets one, with the startle setup and the typed stimuli",
      saved["video"] == "clip.mp4" and saved["track_tamer"]["test"] == "Acoustic Startle Response"
      and saved["track_tamer"]["setup"]["stimulus_frames"] == [50]
      and saved["track_tamer"]["files"]["tracking"] == "clip_MotionIndex.csv"
      and saved["track_tamer"]["files"]["analysis"] == "clip_analysis.xlsx"
      and saved["track_tamer"]["files"]["trace"] == "clip_trace.png"
      and saved["track_tamer"]["files"]["aligned"] == "clip_aligned.png"
      and not {"path", "heatmap"} & set(saved["track_tamer"]["files"]))
check("a startle setup is saved with what startle uses (no regions, scale or objects), and "
      "the trial day and phase as every test's is",
      set(saved["track_tamer"]["setup"]) == {"frame_size", "start_frame", "end_frame", "length_s",
                                             "end_placed",
                                             "stimulus_frames", "steps_done", "trial_day",
                                             "trial_phase"})
check("a crop and exclusions the setup held from another test weren't used or recorded: the "
      "whole frame was analyzed",
      e.summary["AnalyzedPixels_px"] == 744 * 480
      and not {"Crop", "Exclusion_Shapes"} & set(saved["track_tamer"]["tracking"])
      # (warned about once only: the older file handed to it on purpose above)
      and everything.count("Some videos were tracked on part of the picture") == 1)
check("and its Setup sheet lists the session and stimuli only",
      list(sheets["Setup"]["Section"].drop_duplicates()) == ["Session", "Stimuli (typed)"])
setup_rows = dict(zip(sheets["Setup"]["Setting"], sheets["Setup"]["Value"]))
check("the Setup sheet lists the typed stimulus frames", str(setup_rows["Video frames"]) == "50")
got = dict(zip(sheets["Settings"]["Setting"], sheets["Settings"]["Value"]))
check("Settings records the threshold and windows",
      float(got["Intensity threshold (grey levels, 0-255)"]) == 15
      and float(got["Startle window (ms)"]) == 200
      and not any("Habituation" in str(k) for k in got)
      and list(sheets["Settings"]["Setting"]).count("Repeated frames") == 1
      and float(got["Threshold criterion (SD)"]) == 2
      and got["Stimuli from"] == "typed in")
app.fig_dump = (app._path_fig(e, app._plot_settings()), app._heat_fig(e, app._plot_settings()))
for fig, name in zip(app.fig_dump, ("asr_trace.png", "asr_aligned.png")):
    fig.savefig(os.path.join(os.environ.get("ASR_SHOTS", tmp), name))
log.clear(); app.test_var.set("Open Field"); app.files[0].summary = None; app._apply_lock(); app._on_test_type()
app.analyze(); app.update()
check("the Startle by Level tab is hidden for other tests",
      app.nb.tab(app.tab_level, "state") == "hidden")
check("a startle file can't be analyzed as another test", "Some files don't fit this test" in log and not e.analyzed)
app.test_var.set("Acoustic Startle Response"); app._on_test_type()
app.clear_files(); app.add_files([os.path.join(tmp, "clip_MotionIndex.csv")]); app.update()
app._set_selection([0], focus=0); app.analyze(); app.update()
check("a saved motion index file can be added and analyzed without the video",
      app.files[0].analyzed and app.files[0].summary["ASR_Trials"] == 1)
check("a video with no repeated frames isn't warned about", "Most frames are repeats" not in log)
# A camera that really ran at a third of the video's rate (Boom Box on a Mac
# before 1.3.4): two of every three frames are copies.
slow = pd.read_csv(os.path.join(tmp, "clip_MotionIndex.csv"))
check("the motion file on disk keeps only per-frame columns",
      list(slow.columns) == ["Frame", "Time_s", "MotionIndex_pct", "AboveThreshold_px",
                             "Frame_Unreadable", "Repeated"])
slow["Repeated"] = [i % 3 != 0 for i in range(len(slow))]
slow.to_csv(os.path.join(tmp, "clip_MotionIndex.csv"), index=False)
app.clear_files(); app.add_files([os.path.join(tmp, "clip_MotionIndex.csv")]); app.update()
shown = []
gui.show_warning = lambda p, t, m, **k: (log.append(t), shown.append(m))
log.clear(); app._set_selection([0], focus=0); app.analyze(); app.update()
row = app.files[0].summary
check("most frames repeated: Analyze warns, with the share and the real frame rate",
      "Most frames are repeats" in log and row["RepeatedFrames"] == sum(slow["Repeated"])
      and "(66%)" in shown[-1] and "real frames a second" in shown[-1])
print("   " + shown[-1].split("\n\n")[1] if shown else "")
check("the repeat count is in the Summary", "RepeatedFrames" in app.files[0].summary)
app.destroy()
shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
