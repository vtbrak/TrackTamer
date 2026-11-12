"""Object recognition end to end on the user's object trial
(Examples/1_2026-06-26_14-03-15.mp4, gitignored): set up, track, list zone
visits, score, analyze, export. Works on a copy in a temporary folder.

Run from the project folder:  .venv/bin/python tests/test_objects_video.py
"""
import scratch  # noqa: F401  (first: temporary files go in app/tests/.tmp, removed after the run)
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from samples import OBJECT_VIDEO as SRC, require
require(SRC)
tmp = tempfile.mkdtemp()
cfg = os.path.join(tmp, "config.json")
import gui, core
gui.load_config = lambda: core.load_config(cfg)
gui.save_config = lambda c: core.save_config(c, cfg)
log = []
for name in ("show_warning", "show_info", "show_error"):
    setattr(gui, name, lambda p, t, m, **k: log.append(t))
gui.ask_yes_no = lambda p, t, m, **k: (log.append(t), True)[1]
# A several-button question: a queued True picks the last button, False the
# one before it, None closes the window (which cancels).
def _choice(p, t, m, choices, default=None, **k):
    log.append(t)
    answer = True
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
import pandas as pd
from core.track_run import make_job, run_job
from core.tracking import TrackingParams
from core.objects import load_scoring

VIDEO = os.path.join(tmp, os.path.basename(SRC))
shutil.copy(SRC, VIDEO)
fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)


app = gui.TrackTamerApp(); app.update()
app.test_var.set("Object Recognition"); app._on_test_type()
app.fps_var.set("9.84")
app.add_files([VIDEO]); app.update()
e = app.files[0]
v = e.video
v.start, v.length_s = 400, None           # the mouse is in from about frame 320
v.crop = (95, 25, 545, 455)
v.objects = {"object 1": (220, 150, 30), "object 2": (437, 356, 32)}
v.object_kinds = {"object 2": "Novel"}
v.trial_day, v.trial_phase = "2", "Test"
v.scale_points, v.scale_cm = [(145, 240), (515, 240)], 40.0
job = make_job(v, TrackingParams(method="dark"), 1.0, 50, "Object Recognition")
data, csv = run_job(job)
e.data = data
app._refresh(); app._set_selection([0], focus=0); app.update()
xs, ys = data.df["X"], data.df["Y"]
check(f"tracked {data.n_frames} frames, positions inside the crop",
      data.n_frames >= 4590 and xs.dropna().between(0, 450).all()
      and ys.dropna().between(0, 430).all())
app.nb.select(app.review); app.update(); app._show_review(); app.update()
sc = app.review.scorer
visits = sc.visits
per = {o: sum(1 for x in visits if x["object"] == o) for o in ("object 1", "object 2")}
print("   zone visits:", per, "first:", [(x["object"], x["row"] + 1, x["seconds"]) for x in visits[:5]])
check("zone visits found for both objects", per["object 1"] > 0 and per["object 2"] > 0)
# Score the first visit of each object as a 1 s interaction from its start.
for obj in ("object 1", "object 2"):
    x = next(x for x in visits if x["object"] == obj)
    sc.start(obj, x["row"]); sc.end(x["row"] + 9)
app.analyze(); app.update()
s = e.summary
check("the row starts with File and the animal's ID", list(s)[:2] == ["File", "animal_id"])
keys = list(s)[2:10]
print("   first columns:", keys)
check("Summary leads with the trial and object measures",
      keys[:6] == ["OR_Day", "OR_Phase", "OR_NovelObjects", "OR_DiscriminationIndex",
                   "OR_PctPreference", "OR_Total_s"])
check("results from the scoring: 1 s each, DI 0, preference 50%",
      s["OR_Time_object 1_s"] == 1.02 and s["OR_Time_object 2_s"] == 1.02
      and s["OR_DiscriminationIndex"] == 0 and s["OR_PctPreference"] == 50
      and s["OR_Day"] == "2" and s["OR_NovelObjects"] == "object 2 (novel)")
print("   lost-tracker warnings:", [t for t in log if "lost" in t])
check("no outside-region warning for Object Recognition (it has no regions)",
      not any("lost" in t for t in log) and "OutsideEvents" not in s or not s.get("OutsideEvents"))
x = [x for x in visits if x["object"] == "object 2"][1]   # its second visit
sc.start("object 2", x["row"]); sc.end(x["row"] + 19); app.update()
check("scoring after Analyze updates the results at once",
      e.summary["OR_Time_object 2_s"] == round(1.02 + 2.03, 2)
      and e.summary["OR_DiscriminationIndex"] > 0)
check("Time Bins carry interaction time per bin",
      abs(e.bins["OR_Time_object 2_s"].sum() - e.summary["OR_Time_object 2_s"]) < 0.03)
keep = e.summary["OR_Time_object 2_s"]
app.review._save_trial({"object 1": "Moved"}, "4", "Training"); app.update()
check("editing trial info after Analyze updates the results at once (no re-tracking)",
      e.summary["OR_Day"] == "4" and e.summary["OR_Phase"] == "Training"
      and "object 1 (moved)" in e.summary["OR_NovelObjects"]
      and e.summary["OR_Time_object 2_s"] == keep)
app.review._save_trial({"object 1": "Familiar"}, "2", "Test"); app.update()
app._set_selection([0], focus=0); app.export(); app.update()
xlsx = os.path.splitext(VIDEO)[0] + "_analysis.xlsx"
check("export writes the workbook", os.path.exists(xlsx))
if os.path.exists(xlsx):
    sheets = pd.read_excel(xlsx, sheet_name=None)
    print("   sheets:", list(sheets))
    check("export has the summary columns and an Interactions sheet",
          "OR_DiscriminationIndex" in sheets["Summary"].columns and "Interactions" in sheets)
    from core.version import VERSION
    st = dict(zip(sheets["Settings"]["Setting"], sheets["Settings"]["Value"]))
    check("the Settings sheet records the program version",
          str(st.get("Track Tamer version")) == VERSION)
from core.plotting import path_figure, heatmap_figure
for fig in (app._path_fig(e, app._plot_settings()), app._heat_fig(e, app._plot_settings())):
    ax = fig.axes[0]
    circles = [p for p in ax.patches if type(p).__name__ == "Circle"]
    check(f"{ax.get_title().split(' —')[0]}: objects and dashed zones drawn",
          len(circles) == 4 and any(t.get_text() == "object 2 (novel)" for t in ax.texts))
fig = app._path_fig(e, app._plot_settings())
fig.savefig(os.path.join(os.environ.get("OR_SHOTS", tmp), "or_path.png"))
fig = app._heat_fig(e, app._plot_settings())
fig.savefig(os.path.join(os.environ.get("OR_SHOTS", tmp), "or_heat.png"))
print(f"\n{fails} failure(s)")
app.destroy()
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if fails else 0)
