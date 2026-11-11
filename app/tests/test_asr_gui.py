"""Acoustic startle in the GUI (ROADMAP §13): setup, the motion index run,
Analyze, the tabs and Export, on a copy of a paper clip. Settings go to a
temporary config.

Run from the project folder:  .venv/bin/python tests/test_asr_gui.py
"""
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
log, yesno = [], []
for name in ("show_warning", "show_info", "show_error"):
    setattr(gui, name, lambda p, t, m, **k: log.append(t))
gui.ask_yes_no = lambda p, t, m, **k: (log.append(t), yesno.pop(0) if yesno else True)[1]
import setup_window, review_panel
for mod in (setup_window, review_panel):
    mod.show_info, mod.show_warning = gui.show_info, gui.show_warning
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
check("startle settings and tabs replace the others",
      bool(app.asr_bar.winfo_manager()) and not app.entries_section.winfo_manager()
      and tabs[:4] == ["Summary", "Trials", "Motion Trace", "Aligned Trials"]
      and not app.path_col.winfo_manager())
app.add_files([CLIP]); app.update()
e = app.files[0]; v = e.video
check("a startle video defaults to its whole length", v.end_frame == 101)
app.open_setup(); app.update()
win = app._setup_win
check("four setup steps", list(win.step_buttons) == ["trim", "exclusions", "threshold", "stimuli"])
win._go("threshold"); app.update()
win.scrub.set(51); win._load_scrub_frame(); app.update()
text15 = win.threshold_text.cget("text")
check("the preview reports the motion index for the frame shown", "0.8" in text15 and "of 357,120" in text15)
app.asr_threshold_var.set("60"); app.update()
check("changing the threshold updates the preview, and the slider follows",
      win.threshold_text.cget("text") != text15 and round(float(win.threshold_scale.get())) == 60
      and app.config_data["asr_threshold"] == 60)
app.asr_threshold_var.set("15"); app.update()
log.clear(); win.step = "threshold"; v.steps_done.update({"trim", "exclusions"})
win._step_by(1); app.update()
check("Next reaches the stimuli step, with a box to type frames (no info file)",
      win.step == "stimuli" and win.stimuli_text is not None)
win.stimuli_text.insert("1.0", "50, abc"); log.clear(); win._step_by(1); app.update()
check("a bad frame is refused", "Invalid stimulus frames" in log and "stimuli" not in v.steps_done)
win.stimuli_text.delete("1.0", "end"); win.stimuli_text.insert("1.0", "50"); win._step_by(1); app.update()
check("setup is complete", v.stimulus_frames == [50] and v.ready_for("Acoustic Startle Response")
      and not win.winfo_exists() or v.ready_for("Acoustic Startle Response"))
app._set_selection([0], focus=0); app.update()
app.track(); app.update()
t0 = time.time()
while app._runner is not None and time.time() - t0 < 60:
    app.update(); time.sleep(0.02)
check("Track writes the motion index file",
      e.data is not None and e.data.path.endswith("clip_MotionIndex.csv") and os.path.exists(e.data.path))
log.clear(); app.analyze(); app.update()
s = e.summary
check("Analyze fills the Summary and trials, with no frame-rate prompt",
      e.analyzed and s["ASR_Trials"] == 1 and s["ASR_TrialsUsed"] == 1 and len(e.bins) == 1
      and "ASR_Mean_pulse" in s and not log)
r = e.bins.iloc[0]
check("the paper clip's startle: peak on the frame after the stimulus, amplitude from the two windows",
      r["FrameNo"] == 51 and r["motion.index.after"] > r["motion.index.before"]
      and abs(r["Startle amplitude"] - (r["motion.index.after"] - r["motion.index.before"])) < 1e-3)
print(f"   after {r['motion.index.after']}  before {r['motion.index.before']}  amplitude {r['Startle amplitude']}  reaction {r['ReactionTime']} ms")
check("Summary shows the key measures by default",
      {"ASR_Trials", "ASR_Mean_pulse"} <= set(app.summary_tree["columns"]))
check("Trials tab lists the trial with your headings",
      "Startle amplitude" in app.bins_tree["columns"] and "Direction" not in app.bins_tree["columns"]
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
app.nb.select(app.tab_summary); app.update(); rv.unload()
check("startle settings lock at Analyze; threshold locked after Track",
      str(app.asr_startle_entry.cget("state")) == "disabled"
      and str(app.asr_threshold_entry.cget("state")) == "disabled")
log.clear(); app.export(); app.update()
files = sorted(f for f in os.listdir(tmp) if f.startswith("clip_"))
print("   files:", files)
check("export writes the workbook and two images",
      {"clip_analysis.xlsx", "clip_trace.png", "clip_aligned.png", "clip_MotionIndex.csv"} <= set(files)
      and "Export finished" in log)
sheets = pd.read_excel(os.path.join(tmp, "clip_analysis.xlsx"), sheet_name=None)
check("workbook has Summary, Trials and Settings",
      list(sheets) == ["Summary", "Trials", "Settings"] and "Startle amplitude" in sheets["Trials"])
got = dict(zip(sheets["Settings"]["Setting"], sheets["Settings"]["Value"]))
check("Settings records the threshold and windows",
      float(got["Intensity threshold"]) == 15 and float(got["Startle window (ms)"]) == 200
      and got["Stimuli from"] == "typed in")
app.fig_dump = (app._path_fig(e, app._plot_settings()), app._heat_fig(e, app._plot_settings()))
for fig, name in zip(app.fig_dump, ("asr_trace.png", "asr_aligned.png")):
    fig.savefig(os.path.join(os.environ.get("ASR_SHOTS", tmp), name))
log.clear(); app.test_var.set("Open Field"); app.files[0].summary = None; app._apply_lock(); app._on_test_type()
app.analyze(); app.update()
check("a startle file can't be analyzed as another test", "Some files don't fit this test" in log and not e.analyzed)
app.test_var.set("Acoustic Startle Response"); app._on_test_type()
app.clear_files(); app.add_files([os.path.join(tmp, "clip_MotionIndex.csv")]); app.update()
app._set_selection([0], focus=0); app.analyze(); app.update()
check("a saved motion index file can be added and analyzed without the video",
      app.files[0].analyzed and app.files[0].summary["ASR_Trials"] == 1)
app.destroy()
shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
