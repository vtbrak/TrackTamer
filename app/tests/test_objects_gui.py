"""Object recognition in the GUI (ROADMAP §15): the setup window's Objects
step, the tracking file's object columns, the Review tab's zone visits and
scoring, and the results.

Uses the practice clip cut from the plus maze example (tests/samples.py),
copied to a temporary folder. Settings go to a temporary config.

Run from the project folder:  app/.venv/bin/python app/tests/test_objects_gui.py
"""
import os
import shutil
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tmp = tempfile.mkdtemp()
cfg = os.path.join(tmp, "config.json")
import gui, core
gui.load_config = lambda: core.load_config(cfg)
gui.save_config = lambda c: core.save_config(c, cfg)
log, yesno = [], []
gui.show_warning = lambda p, t, m, **k: log.append(t)
gui.show_info = lambda p, t, m, **k: log.append(t)
gui.show_error = lambda p, t, m, **k: log.append(t)
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from samples import practice_clip
SRC = practice_clip()
if SRC is None:
    sys.exit("The plus maze example video (for the practice clip) is missing from Examples.")
CLIP = os.path.join(tmp, "clip.mp4")
shutil.copy(SRC, CLIP)

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)


app = gui.TrackTamerApp(); app.update()
app.test_var.set("Object Recognition"); app._on_test_type(); app.update()
check("Object Recognition settings section with the zone distance box",
      bool(app.or_bar.winfo_manager()) and not app.of_bar.winfo_manager()
      and app.zone_var.get() == "4")
app.add_files([CLIP]); app.update()
app.open_setup(); app.update()
win = app._setup_win
v = app.files[0].video
win._go("regions"); app.update()
check("step 5 is Objects, listing two objects", win.step_buttons["regions"].cget("text").strip()
      .endswith("5  Objects") and list(win.object_list.get_children()) == ["object 1", "object 2"])
check("Remove is hidden for the first two objects", not win.remove_obj_btn.winfo_manager())
ev = lambda x, y: type("E", (), dict(zip("xy", win.canvas.to_screen(x, y))))()
win._object_press(ev(300, 300)); win._object_drag(ev(340, 300)); win._object_release(ev(340, 300))
check("press at the center and drag to the edge draws a circle",
      np.allclose(v.objects["object 1"], (300, 300, 40), atol=0.6)
      and win._current_object == "object 2")
win._object_press(ev(700, 300)); win._object_drag(ev(700, 330)); win._object_release(ev(700, 330))
win._object_press(ev(700, 300)); win._object_drag(ev(720, 310)); win._object_release(ev(720, 310))
check("drag a drawn object's center to move it", np.allclose(v.objects["object 2"][:2], (720, 310), atol=0.6))
win._object_press(ev(750, 310)); win._object_drag(ev(760, 310)); win._object_release(ev(760, 310))
check("drag its edge to resize it", np.allclose(v.objects["object 2"][2], 40, atol=0.6))
win._object_press(ev(100, 100)); win._object_release(ev(100, 100))
check("a click off the objects doesn't draw (object 2 already drawn)",
      set(v.objects) == {"object 1", "object 2"})
win.kind_var.set("Novel"); win._set_kind()
win.day_var.set("3"); win.phase_var.set("Test"); win._set_trial()
check("type, day and phase saved to the video's setup",
      v.object_kinds == {"object 2": "Novel"} and v.trial_day == "3" and v.trial_phase == "Test")
win._add_object(); app.update()
check("Add object lists a third, with Remove shown",
      v.object_names[-1] == "object 3" and bool(win.remove_obj_btn.winfo_manager()))
check("an undrawn third object counts as missing", v.missing_regions("Object Recognition") == ["object 3"])
win._remove_object()
check("Remove takes it off again", v.object_names == ["object 1", "object 2"]
      and not v.missing_regions("Object Recognition"))
app.update()
circles = [i for i in win.canvas.find_withtag("overlay") if win.canvas.type(i) == "oval"]
check("circles drawn with see-through fills", circles and win.canvas.find_withtag("fills"))
check("no zone ring before the scale (a note says why)", "scale is set" in win.object_note.cget("text"))
v.scale_points, v.scale_cm = [(100, 100), (500, 100)], 40.0   # 10 px per cm
app.zone_var.set("3"); app._flush_zone_change(); app.update()
dashed = [i for i in win.canvas.find_withtag("overlay")
          if win.canvas.type(i) == "oval" and win.canvas.itemcget(i, "dash")]
check("zone rings drawn once scaled, following the zone box", len(dashed) == 2
      and app.config_data["object_zone_cm"] == 3.0)
from core.track_run import make_job
job = make_job(v, core.tracking.TrackingParams() if hasattr(core, "tracking") else
               __import__("core.tracking", fromlist=["x"]).TrackingParams(), 1.0, 10,
               "Object Recognition")
check("Track writes the objects, day and phase (no regions)",
      job.regions == [] and job.extra["Trial_Day"] == "3" and job.extra["Trial_Phase"] == "Test"
      and '"kind": "Novel"' in job.extra["Objects"])
win._close()
app.update()

# --- Track a short stretch, then score it in the Review tab -----------------
import pandas as pd
from core.track_run import run_job
from core.loader import load_csv
from core.objects import TrialObject, objects_to_text, load_scoring, scoring_path
v.start, v.length_s = 0, 10.0
job = make_job(v, __import__("core.tracking", fromlist=["x"]).TrackingParams(), 1.0, 10,
               "Object Recognition")
data, csv = run_job(job)
df = pd.read_csv(csv)
check("the tracking file keeps only per-frame columns; the objects, day and phase are in the "
      "video's info file and come back when it's loaded", file_ok := (
    "Objects" not in df.columns and "Objects" in data.settings
    and str(data.settings["Trial_Day"]) == "3" and data.settings["Trial_Phase"] == "Test"))
# Put object 1 where the animal is at frame 100, so there's a zone visit.
x0, y0 = df["X"].iloc[100], df["Y"].iloc[100]
df["Objects"] = objects_to_text([TrialObject("object 1", x0 + 30, y0, 20, "Familiar"),
                                 TrialObject("object 2", 5, 5, 3, "Novel")])
df.to_csv(csv, index=False)
app.files[0].data = load_csv(csv)
app._refresh(); app.update()
app._set_selection([0], focus=0); app.update()
app.nb.select(app.review); app.update(); app._show_review(); app.update()
rv = app.review
check("Review tab lists zone visits to score", rv.scorer is not None and rv.scorer.visits
      and rv.heading.cget("text") == "Zone visits to score"
      and rv.tree.item("0", "values")[1] == "object 1"
      and rv.tree.item("0", "values")[-1] == "to review"
      and not rv.cutoff_entry.winfo_manager())
visit = rv.scorer.visits[0]
rv.tree.selection_set("0"); app.update()
pw = rv.window
check("clicking a visit opens the playback window at the frame the point enters the zone",
      pw is not None and pw.winfo_exists() and pw.row == visit["row"]
      and pw.object_var.get() == "object 1" and "object 1 zone" in pw.info.cget("text"))
pw.mark_end()
check("End before Start says what to do", "Start interaction" in pw.score_text.cget("text"))
# A Start pressed by mistake is dropped with Cancel start (Esc): nothing logged.
check("Cancel start is only available while an interaction is open",
      str(pw.cancel_btn.cget("state")) == "disabled" and bool(pw.bind("<Escape>")))
pw.mark_start()
check("Start opens an interaction and enables Cancel start",
      pw.scorer.pending == ("object 1", pw.row) and str(pw.cancel_btn.cget("state")) == "normal")
pw.cancel_start(); app.update()
check("Cancel start drops it: nothing logged, nothing saved, and the info line says so",
      pw.scorer.pending is None and not pw.scorer.scoring.bouts
      and not os.path.exists(scoring_path(app.files[0].data))
      and str(pw.cancel_btn.cget("state")) == "disabled"
      and "cancelled" in pw.score_text.cget("text")
      and "open since" not in pw.info.cget("text"))
pw.cancel_start()
check("Cancel start with nothing open does nothing", "cancelled" in pw.score_text.cget("text"))
pw.step(2); pw.mark_start(); pw.step(5); pw.mark_end(); app.update()
check("End closes the interaction and Cancel start goes back to unavailable",
      str(pw.cancel_btn.cget("state")) == "disabled")
sc = load_scoring(app.files[0].data)
check("Start / End logs an interaction and saves it",
      [(b.object, b.start, b.end) for b in sc.bouts] == [("object 1", visit["row"] + 2, visit["row"] + 7)]
      and os.path.exists(scoring_path(app.files[0].data)))
check("the visit shows as scored in the list",
      rv.tree.item("0", "values")[-1] == "interaction"
      # (lengths use the Frame rate box, as the results do)
      and f"object 1 {round(6 / float(app.fps_var.get()), 2):g} s (1 interaction)"
      in rv.summary.cget("text"))
pw.mark_none()
check("No interaction on a visit with an interaction is refused",
      "already has an interaction" in pw.score_text.cget("text"))
pw.bout_tree.selection_set("0"); app.update(); pw.delete_logged(); app.update()
check("Delete removes it", not load_scoring(app.files[0].data).bouts
      and rv.tree.item("0", "values")[-1] == "to review")
pw.show(visit["row"]); pw.mark_none(); app.update()
check("No interaction marks the visit", rv.tree.item("0", "values")[-1] == "no interaction"
      and load_scoring(app.files[0].data).no_interaction == {("object 1", visit["row"])})
pw.object_var.set("object 2"); pw._picked_object(); pw.show(0)
pw.mark_start(); pw.step(3)
check("an interaction can be logged anywhere, with the object picked by hand",
      pw.object_var.get() == "object 2")
pw.mark_end(); app.update()
check("…and is saved", ("object 2", 0, 3) in [(b.object, b.start, b.end)
                                               for b in load_scoring(app.files[0].data).bouts])
# Previous / Next visit in the playback window (user, 2026-11-05).
vis = rv.scorer.visits
pw.open_visit(vis[0]); app.update()
if len(vis) > 1:
    pw.go_visit(1); app.update()
    check("Next visit jumps to where the point enters the next zone visit, and the list follows",
          pw.row == vis[1]["row"] and pw.visit is vis[1] and rv.tree.selection() == ("1",)
          and "Visit 2 of" in pw.visit_text.cget("text"))
    pw.go_visit(-1); app.update()
    check("Previous visit goes back", pw.row == vis[0]["row"] and rv.tree.selection() == ("0",))
    pw.mark_start(); pw.go_visit(1)
    check("can't move to another visit with an interaction open",
          pw.row == vis[0]["row"] and "still open" in pw.score_text.cget("text"))
    pw.mark_end(); app.update()
pw.show(vis[-1]["end"] + 1 if vis[-1]["end"] + 1 < pw.pb.n_frames else vis[-1]["end"])
pw.visit = None; pw.go_visit(1)
check("Next after the last visit says so", "last zone visit" in pw.score_text.cget("text"))
n_before = len(rv.scorer.visits)
app.zone_var.set("0"); app._flush_zone_change(); app.update()
check("changing the zone distance updates the visit list (no re-tracking)",
      len(rv.scorer.visits) != n_before or rv.scorer.zone_cm == 0)
app.zone_var.set("3"); app._flush_zone_change(); app.update()

# Edit object types, day and phase after tracking (ROADMAP §15).
check("Edit trial info button shown for Object Recognition", bool(rv.trial_btn.winfo_manager()))
rv.edit_trial(); app.update()
dlg = rv.trial_dialog
check("the dialog starts from the file's own values",
      dlg.day_var.get() == "3" and dlg.phase_var.get() == "Test"
      and dlg.kind_vars["object 2"].get() == "Novel")
csv_before = pd.read_csv(csv, dtype=str, keep_default_na=False)
dlg.day_var.set("5"); dlg.phase_var.set("Training"); dlg.kind_vars["object 1"].set("Moved")
log.clear(); real_replace = os.replace
def locked(*a):
    raise PermissionError("the file is open")
os.replace = locked
dlg.save(); app.update()
os.replace = real_replace
check("if the file can't be saved it says so, stays open, and nothing changes",
      "The trial info couldn't be saved" in log and dlg.winfo_exists()
      and pd.read_csv(csv, dtype=str, keep_default_na=False).equals(csv_before)
      and rv.scorer.objects[0].kind == "Familiar"
      and not os.path.exists(csv + ".tmp"))
scored_before = load_scoring(app.files[0].data)
dlg.save(); app.update()
reread = load_csv(csv)
check("Save writes the tracking file and closes the dialog",
      not dlg.winfo_exists() and reread.settings["Trial_Phase"] == "Training"
      and str(int(reread.settings["Trial_Day"])) == "5" and '"kind": "Moved"' in reread.settings["Objects"])
check("the Review tab and the playback window show the new types at once",
      rv.scorer.objects[0].kind == "Moved" and "Trial day 5, phase Training" in rv.summary.cget("text")
      and "object 1 moved" in rv.summary.cget("text")
      and any("object 1 (moved)" == pw.canvas.itemcget(i, "text")
              for i in pw.canvas.find_all() if pw.canvas.type(i) == "text"))
check("logged interactions stay; the video's setup follows (tracking again keeps the edit)",
      load_scoring(app.files[0].data).bouts == scored_before.bouts
      and v.object_kinds["object 1"] == "Moved" and (v.trial_day, v.trial_phase) == ("5", "Training"))

# The saved video shows the objects and their zones.
import cv2, time as _time
from core.playback import draw_tracking, tracked_video_path
pw.roi_var.set(True); pw.save_video()
t0 = _time.time()
while pw._save is not None and _time.time() - t0 < 120:
    pw.update(); _time.sleep(0.02)
saved = tracked_video_path(pw.pb.video)
cap = cv2.VideoCapture(saved); ok, out = cap.read(); cap.release()
raw = pw.source.frame(0)
o1 = rv.scorer.objects[0]
angles = np.linspace(0, 2 * np.pi, 72, endpoint=False)
on_ring = [out[int(o1.y + o1.r * np.sin(a)), int(o1.x + o1.r * np.cos(a))].astype(int) for a in angles]
base = [raw[int(o1.y + o1.r * np.sin(a)), int(o1.x + o1.r * np.cos(a))].astype(int) for a in angles]
check("saved _tracked.mp4 has the object circles drawn on",
      ok and np.abs(np.array(on_ring) - np.array(base)).mean() > 25)
blank = np.zeros_like(raw)
plain = draw_tracking(blank, pw.pb, 0, 0, True)
drawn = draw_tracking(blank, pw.pb, 0, 0, True, rv.scorer.objects, rv.scorer.zone_px)
zone_r = o1.r + rv.scorer.zone_px
near_ring = drawn[max(int(o1.y - zone_r - 2), 0):int(o1.y + zone_r + 3),
                  max(int(o1.x - zone_r - 2), 0):int(o1.x + zone_r + 3)]
check("the objects and zones are only drawn when asked",
      (plain != drawn).any() and (near_ring == 255).any())
os.remove(saved)

folder = tempfile.mkdtemp()
for name in ("a.mp4", "a_LocationOutput.csv", "a_ObjectScoring.csv",
             "2026-11-05_16-56-42_EPM_Overhead_frames.csv", "2026-11-05_16-56-42_EPM_info.csv"):
    open(os.path.join(folder, name), "w").close()
check("Add folder skips companion CSVs (object scoring, capture frame times and info)",
      [os.path.basename(p) for p in app._files_in(folder)] == ["a.mp4", "a_LocationOutput.csv"])
shutil.rmtree(folder, ignore_errors=True)

print(f"\n{fails} failure(s)")
app.destroy()
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if fails else 0)
