"""Checks for failures in the windows: one file failing during Analyze,
roles changed after Analyze, setup work lost by a stray click, the setup
window reopened or left mid-shape, settings changed without being asked to,
and keys, fonts and sizes that differ between Mac and Windows.

Drives the real windows with pop-ups replaced by fakes, on the example files
and the practice clip (tests/samples.py). Settings go to a temporary config.

Run from the project folder:  app/.venv/bin/python app/tests/test_gui_fixes.py
"""
import os
import shutil
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp()
cfg = os.path.join(tmp, "config.json")
import gui, core, dialogs
gui.load_config = lambda: core.load_config(cfg)
gui.save_config = lambda c: core.save_config(c, cfg)
log, yesno = [], []
def said(p, t, m, **k): log.append(t)
def asked(p, t, m, **k):
    log.append(t)
    return yesno.pop(0) if yesno else True
def chose(p, t, m, choices, default=None, **k):
    log.append(t)
    answer = yesno.pop(0) if yesno else True
    return None if answer is None else choices[-1] if answer else choices[-2]
gui.show_warning = gui.show_info = gui.show_error = said
gui.ask_yes_no, gui.ask_choice = asked, chose
# The side-by-side choice: closed without choosing unless a side is queued.
sides = []
gui.ask_side_by_side = lambda p, t, m, rows, *a, **k: (
    log.append(t), [sides.pop(0)] * len(rows) if sides else None)[1]
import setup_window, review_panel
for mod in (setup_window, review_panel):
    mod.show_info = mod.show_warning = said
review_panel.ask_yes_no = asked
setup_window.ask_yes_no = asked
gui.TrackTamerApp.wait_window = lambda self, w=None: None
from samples import EPM, EPM_VIDEO, OF, practice_clip, require
require(EPM, OF, EPM_VIDEO)
CLIP = shutil.copy(practice_clip(), os.path.join(tmp, "Practice_Clip.mp4"))
SMALL = shutil.copy(EPM_VIDEO, os.path.join(tmp, "small.mp4"))      # 800 x 600

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)

app = gui.TrackTamerApp(); app.update()
app.test_var.set("Elevated Plus Maze"); app._on_test_type(); app.update()

# --- small portable helpers ------------------------------------------------
bold = dialogs.bold_font(11)
check("bold text uses the system's own typeface, not a made-up family name",
      bold.actual("family") == __import__("tkinter.font").font.nametofont("TkDefaultFont").actual("family")
      and bold.actual("weight") == "bold" and bold.actual("size") == 11
      and dialogs.bold_font(11) is bold)
import tkinter as tk
probe = tk.Toplevel(app); dialogs.fit_window(probe, 5000, 5000); probe.update_idletasks()
w, h = (int(v) for v in probe.geometry().split("+")[0].split("x"))
check("a window is never asked to open larger than the screen",
      w <= probe.winfo_screenwidth() and h <= probe.winfo_screenheight() - 100)
probe.destroy()
check("whole numbers show without .0, other values as they are, blanks as blank",
      [gui._shown(v) for v in (3.0, np.float64(4993.0), 2.5, float("nan"), "ct", 7)]
      == [3, 4993, 2.5, "", "ct", 7])
check("two list entries can be compared (the same file may be listed twice)",
      gui.FileEntry("a.csv", core.load_csv(EPM), "a") != gui.FileEntry("a.csv", core.load_csv(EPM), "a"))
box = app.test_box
check("the wheel over the Test box scrolls the panel instead of changing the test",
      all(box.bind(seq) for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>")))
mac = app.tk.call("tk", "windowingsystem") == "aqua"
check("Select-all key: Cmd+A only on a Mac (on Windows that binding is Num Lock + A)",
      bool(app.file_tree.bind("<Control-a>")) and bool(app.file_tree.bind("<Command-a>")) == mac)
check("Mac: Cmd+Q goes through the same closing checks as the window's close button",
      not mac or bool(app.tk.call("info", "commands", "::tk::mac::Quit")))
for good, want in (("60  (1 hour)", 60.0), ("7,5", 7.5), ("0.5", 0.5)):
    check(f'typed "{good}" is read as {want:g}', setup_window._number(good) == want)
for bad in ("2 hours", "1 000", "", "abc"):
    try:
        setup_window._number(bad); ok = False
    except ValueError:
        ok = True
    check(f'typed "{bad}" is refused, not quietly read as a number', ok)

# --- an error nothing else caught is shown, not just printed -----------------
log.clear()
try:
    raise RuntimeError("the disk went away")
except RuntimeError as exc:
    import io, contextlib
    with contextlib.redirect_stderr(io.StringIO()) as printed:
        app.report_callback_exception(type(exc), exc, exc.__traceback__)
check("an error in any button or timer is said on screen as well as written to the console",
      log == ["Something went wrong"] and "the disk went away" in printed.getvalue())

# --- a session cut short by an unreadable video is said, not left quietly short --
short = core.load_csv(EPM); short.missing_at_end = 5723
fine = core.load_csv(EPM); fine.missing_at_end = 3            # a few at the end is normal
log.clear()
app._warn_short_sessions([gui.FileEntry("damaged.mp4", short, "damaged"),
                          gui.FileEntry("fine.mp4", fine, "fine")])
check("tracking that stopped early because the video couldn't be read is warned about once",
      log == ["Some sessions are shorter than asked for"] and short.missing_at_end == 0)
log.clear(); app._warn_short_sessions([gui.FileEntry("fine.mp4", fine, "fine")])
check("a few frames short at the very end of a file is not", log == [])

# --- Analyze: one failing file doesn't stop the rest -----------------------
app.add_files([EPM]); app.add_files([EPM]); app.update()     # listed twice (Add Again)
app.select_all(); app.update()
real = app._analyze_entry
def flaky(e):
    if e is app.files[0]:
        raise KeyError("Frame_Unreadable")
    real(e)
app._analyze_entry = flaky
log.clear(); app.analyze(); app.update()
app._analyze_entry = real
check("a file that fails to analyze is reported and the others are still analyzed",
      "Some files couldn't be analyzed" in log and not app.files[0].analyzed
      and app.files[1].analyzed)
check("and the list shows it (the settings lock as usual)",
      app.file_tree.item("1", "values")[2] == "Analyzed"
      and app.file_tree.item("0", "values")[2] == "Not analyzed"
      and str(app.fps_entry.cget("state")) == "disabled")
values = app.summary_tree.item("1", "values")
cols = list(app.summary_tree["columns"])
entries = values[cols.index("EPM_OpenEntries")] if "EPM_OpenEntries" in cols else None
check("counts in the Summary read as whole numbers while another file has no results",
      entries is not None and "." not in str(entries))

# --- roles changed after Analyze: results follow ---------------------------
app.select_all(); app.analyze(); app.update()
before = dict(app.files[1].summary)
roles = app._current_roles([app.files[1]])
swap = {"open_arm": "closed_arm", "closed_arm": "open_arm"}
class Swapped:
    def __init__(self, parent, test, overview, current, preview=None, reason=""):
        self.result = {name: swap.get(role, role) for name, role in current.items()}
gui.RegionDialog = Swapped
app.open_region_dialog(); app.update()
after = app.files[1].summary
check("changing region roles after Analyze works the results out again",
      after["EPM_OpenArm_s"] == before["EPM_ClosedArm_s"]
      and after["EPM_ClosedArm_s"] == before["EPM_OpenArm_s"])
check("so the exported Settings sheet's roles are the ones the results used",
      app._current_roles([app.files[1]]) == {n: swap.get(r, r) for n, r in roles.items()})
app.config_data["region_roles"].clear()
app.clear_files(); app.update()

# --- Export: a progress bar, and Cancel stops after the file being written ----
one = shutil.copy(EPM, os.path.join(tmp, "one_LocationOutput.csv"))
two = shutil.copy(EPM, os.path.join(tmp, "two_LocationOutput.csv"))
app.add_files([one, two]); app.select_all(); app.analyze(); app.update()
seen = []
real_save = gui.save_figure
def watching(fig, path):
    seen.append((bool(app.export_bar.winfo_manager()), str(app.export_btn.cget("state")),
                 str(app.analyze_btn.cget("state")), str(app.clear_btn.cget("state")),
                 app.export_text.cget("text")))
    real_save(fig, path)
gui.save_figure = watching
log.clear(); app.export(); app.update()
gui.save_figure = real_save
made = lambda name: os.path.exists(os.path.join(tmp, name + "_LocationOutput_analysis.xlsx"))
check("Export shows a progress bar naming the file, and Export, Analyze and Clear wait meanwhile",
      seen and all(row[:4] == (True, "disabled", "disabled", "disabled") for row in seen)
      and "Exporting 1 of 2" in seen[0][4] and "Exporting 2 of 2" in seen[-1][4])
check("when it finishes the bar goes, the buttons come back, and both files are exported",
      not app.export_bar.winfo_manager() and str(app.export_btn.cget("state")) == "normal"
      and "Export finished" in log and made("one") and made("two"))
for name in ("one", "two"):
    os.remove(os.path.join(tmp, name + "_LocationOutput_analysis.xlsx"))
steps = []
real_update = app.update
def cancel_on_second():
    steps.append(1)
    if len(steps) == 2 and app._exporting:
        app.cancel_export()         # as clicking Cancel while the first file is done
    real_update()
app.update = cancel_on_second
log.clear(); app.export()
app.update = real_update; app.update()
check("Cancel stops after the file being written: the first is kept, the second isn't started",
      "Export stopped" in log and made("one") and not made("two")
      and not app._exporting and not app.export_bar.winfo_manager())
app.clear_files(); app.update()

# --- the Zone distance box applies once typing stops ------------------------
was = app.config_data["object_zone_cm"]
app.zone_var.set("1"); app.zone_var.set("12")              # typing "12"
check("typing in the Zone distance box doesn't apply each keystroke",
      app.config_data["object_zone_cm"] == was and app._zone_job is not None)
app._flush_zone_change()                                    # Return, leaving the box, or the wait
check("it applies once, with the finished number", app.config_data["object_zone_cm"] == 12
      and app._zone_job is None)
app.zone_var.set("9"); app.analyze(); app.update()          # (nothing selected: only the flush matters)
check("Analyze uses what is in the box even if the wait isn't over",
      app.config_data["object_zone_cm"] == 9)
app.zone_var.set(f"{was:g}"); app._flush_zone_change()

# --- a later Analyze warns about a file at a different frame rate -----------
app.test_var.set("Open Field"); app._on_test_type()
app.add_files([OF]); app._set_selection([0]); yesno[:] = [True]; app.analyze(); app.update()
used = app._fps_locked()
other = core.load_csv(OF); other.settings["Video_FPS"] = used * 2
app.files.append(gui.FileEntry("other.csv", other, "other")); app._refresh()
app._set_selection([1]); log.clear(); yesno[:] = [False]; app.analyze(); app.update()
check("a file recorded at another frame rate, added after the rate is fixed, is asked about",
      "Some files have a different frame rate" in log and not app.files[1].analyzed)
app.clear_files(); app.update()

# --- video setups: not lost by a stray click --------------------------------
app.test_var.set("Elevated Plus Maze"); app._on_test_type()
app.add_files([CLIP, SMALL]); app.update()
big, small = app.files[0].video, app.files[1].video
check("a new video gets its test's standard session length",
      big.length_s == 300 and big.length_default == "Elevated Plus Maze")
app.test_var.set("Open Field"); app._on_test_type(); app.update()
check("switching the test type moves an untouched video to that test's standard length",
      big.length_s == 3600 and big.length_default == "Open Field")
app.open_setup(); app.update()
win = app._setup_win
win.length_var.set("12"); win._apply_length(); app.update()
app.test_var.set("Elevated Plus Maze"); app._on_test_type(); app.update()
check("a session length the user typed is kept when the test type changes",
      big.length_s == 720 and big.length_default == "" and small.length_s == 300)
check("the open setup window follows the test type (no stale steps)",
      win.winfo_exists() and win.step in win._steps())
app.test_var.set("Acoustic Startle Response"); app._on_test_type(); app.update()
win._go("threshold"); app.update()
app.test_var.set("Elevated Plus Maze"); app.config_data["test_type"] = "Elevated Plus Maze"
win._step_by(1); app.update()      # the test changed under the window, without it being told
check("Next still works after the test type changed under the setup window",
      win.step == "trim")

scr = lambda x, y: type("E", (), dict(zip("xy", win.canvas.to_screen(x, y))))()
win._go("regions"); app.update()
first = win._current_region
for x, y in ((300, 200), (500, 200), (500, 400), (300, 400)):
    win._region_press(scr(x, y)); win._region_release(scr(x, y))
check("four points placed, shape not closed yet", len(win._points) == 4 and first not in big.regions)
win._go("scale"); app.update()
check("leaving the step keeps a region that was drawn but not closed",
      first in big.regions and len(big.regions[first][0]) == 4)
win._go("regions"); app.update()
win._current_region = first; win._fill_region_list(select=first)
win._mark("regions")
win.region_name_var.set("nest"); win._add_region()
for x, y in ((600, 100), (700, 100), (700, 200)):
    win._region_press(scr(x, y)); win._region_release(scr(x, y))
win._close_region(); app.update()
win._current_region = "nest"; win.region_name_var.set("nest box"); win._rename_region(); app.update()
names = list(win.region_list.get_children())
check("renaming an added region leaves no copy of the old name in the list",
      "nest box" in names and "nest" not in names)
win._mark("regions")
win._current_region = "nest box"; win._delete_region(); app.update()
check("deleting a region unticks the step", "regions" not in big.steps_done)

# "Set end here" places the end on a frame: it stays there when the start moves.
win._go("trim"); app.update()
fps = big.info.fps
big.start = 0
win.scrub.set(500); win._load_scrub_frame(); win._set_end(); app.update()
win.scrub.set(100); win._load_scrub_frame(); win._set_start(); app.update()
check("an end placed with Set end here stays on its frame when the start moves",
      (big.start, big.end_frame) == (100, 501) and abs(big.length_s - 401 / fps) < 1e-9)
check("the trim step names the trial's last frame (the one shown when the end was set)",
      win.end_text.cget("text").startswith("Last frame 500 "))
win.scrub.set(600); win._load_scrub_frame(); log.clear(); win._set_start(); app.update()
check("the start can't be moved past a placed end",
      "Start is after the end" in log and big.start == 100)
win.length_var.set("0.2"); win._apply_length(); app.update()      # 12 s, typed
win.scrub.set(50); win._load_scrub_frame(); win._set_start(); app.update()
check("a typed session length still follows the start",
      big.end_placed is None and big.end_frame == 50 + round(12 * fps))
# The session length selected for the test is 12 s now; an end past it asks.
win.scrub.set(800); win._load_scrub_frame()
log.clear(); yesno[:] = [False]; win._set_end(); app.update()
check("an end past the test's session length asks first, and Cancel leaves the end alone",
      "The end is past the session length" in log and big.end_frame == 50 + round(12 * fps))
yesno[:] = [True]; win._set_end(); app.update()
check("Use Anyway places it", big.end_frame == 801 and big.end_placed == 801)
win.scrub.set(232); win._load_scrub_frame()            # 11 s after the start
log.clear(); yesno[:] = [True]; win._set_end(); app.update()
check("an end inside the session length doesn't ask", log == [] and big.end_frame == 233)
app.config_data["session_minutes"]["Elevated Plus Maze"] = 5.0

# Start from previous video: asks before replacing; never copies shapes across sizes.
win._move(1); app.update()
small.regions["center"] = ([10, 60, 60], [10, 10, 60])
log.clear(); yesno[:] = [False]; win._copy_previous(); app.update()
check("Start from previous video asks before replacing what's drawn, and Cancel keeps it",
      "Replace what's drawn for this video?" in log and list(small.regions) == ["center"])
log.clear(); yesno[:] = [True]; win._copy_previous(); app.update()
check("from a video of another size only the session length is copied, with a note",
      "Only the session length was copied" in log and small.length_s == big.length_s
      and list(small.regions) == ["center"] and small.crop is None)
small.exclusions.append(([1, 9, 9], [1, 1, 9])); win._go("exclusions"); app.update()
log.clear(); yesno[:] = [False]; win._clear_shapes()
check("Clear all asks first", "Remove every shape?" in log and len(small.exclusions) == 1)
win._close(); app.update()

# Two different videos that would write the same result files are named and left out.
twin = shutil.copy(SMALL, os.path.join(tmp, "small.avi"))       # same name, another ending
app.add_files([twin]); app.update()
app.select_all(); log.clear(); app.track(); app.update()
check("Track names videos that would overwrite each other's tracking file, and tracks neither",
      "Some videos would overwrite each other's results" in log and app._runner is None
      and not os.path.exists(os.path.join(tmp, "small_LocationOutput.csv")))
a_, b_ = app.files[1], app.files[2]
kept, clash = app._split_same_results([a_, b_, app.files[0]],
                                      lambda e: os.path.splitext(e.path)[0], lambda e: e)
check("only the files that share result names are left out; the rest go ahead",
      kept == [app.files[0]] and clash == [a_, b_])
app._set_selection([2]); yesno[:] = [True]; app.remove_selected(); app.update()

# Clear / Remove ask before throwing setup work away.
log.clear(); yesno[:] = [False]; app.clear_files(); app.update()
check("Clear asks before losing video setups, and Cancel keeps the list",
      "Setup work will be lost" in log and len(app.files) == 2)
app._set_selection([0]); log.clear(); yesno[:] = [False]; app.remove_selected(); app.update()
check("Remove asks too", "Setup work will be lost" in log and len(app.files) == 2)
app.open_setup(); app.update()
open_win = app._setup_win
yesno[:] = [True]; app.clear_files(); app.update()
check("clearing the list closes the setup window (it would be editing videos that are gone)",
      not app.files and not open_win.winfo_exists())

# --- Object Recognition: reopening the setup window on drawn objects -----------
app.test_var.set("Object Recognition"); app._on_test_type()
log.clear(); app.add_files([CLIP]); app.update()
v = app.files[0].video
check("a video set up under another test comes back with that setup, and the test it was "
      "set up as is shown beside the current one (kept here)",
      app.files[0].restored and "Which test is this?" in log
      and app.test_var.get() == "Object Recognition" and "regions" not in v.steps_done)
v.objects["object 1"] = (300.0, 300.0, 40.0); v.objects["object 2"] = (700.0, 300.0, 40.0)
app.open_setup(); app.update()
win = app._setup_win
try:
    win._go("regions"); app.update(); opened = True
except AttributeError:
    opened = False
check("the Objects step opens on a video whose objects are already drawn",
      opened and list(win.object_list.get_children()) == ["object 1", "object 2"])
win._mark("regions")
ev = lambda x, y: type("E", (), dict(zip("xy", win.canvas.to_screen(x, y))))()
win._object_press(ev(300, 300)); win._object_release(ev(300, 300))
check("clicking an object without moving it doesn't untick the step", "regions" in v.steps_done)
win._close(); yesno[:] = [True]; app.clear_files(); app.update()

# --- startle: showing the Threshold step doesn't change the threshold ----------
app.test_var.set("Acoustic Startle Response"); app._on_test_type()
app.add_files([CLIP]); app.update()
app.asr_threshold_var.set("12.6"); app.update()
app.open_setup(); app.update()
win = app._setup_win
win._go("threshold"); app.update()
check("opening the Threshold step leaves a typed threshold exactly as it was",
      app.asr_threshold_var.get() == "12.6" and app.config_data["asr_threshold"] == 12.6)
win.threshold_scale.set(40); win._threshold_slid(40); app.update()
check("moving the slider still sets it", app.config_data["asr_threshold"] == 40)
s = app.files[0].video
win._go("trim"); app.update()
win.scrub.set(500); win._load_scrub_frame(); win._set_end(); app.update()
end = s.end_frame
win._go("exclusions"); app.update(); win._move(0); app.update()
check("startle: an end the user set is kept when the video is shown again",
      s.end_frame == end == 501)
win._close(); yesno[:] = [True]; app.clear_files(); app.update()

# --- playback window ---------------------------------------------------------
app.test_var.set("Open Field"); app._on_test_type()
app.add_files([OF]); app._set_selection([0], focus=0); app.update()
app.nb.select(app.review); app.update(); app._show_review(); app.update()
rv = app.review
pw = rv.open_window(0); app.update()
if pw is not None:
    hit = []
    class Ev: pass
    e = Ev(); e.widget = pw.speed_box if hasattr(pw, "speed_box") else next(
        w for w in pw.winfo_children()[0].winfo_children() + sum(
            (c.winfo_children() for c in pw.winfo_children()), [])
        if w.winfo_class() == "TCombobox")
    pw._key(e, lambda: hit.append(1))
    check("keys work while a dropdown has the focus", hit == [1])
    e.widget = tk.Entry(pw); pw._key(e, lambda: hit.append(2))
    check("but not while typing in a box", hit == [1])
    check("the window's buttons never keep the keyboard focus (Space would re-press them on Windows)",
          all(str(b.cget("takefocus")) in ("0", "False") for c in pw.winfo_children()
              for b in c.winfo_children() if b.winfo_class() == "TButton"))
    check("Space is handled by the window, wherever the focus is", bool(pw.bind("<space>")))
    rv.cutoff_var.set("abc"); rv._apply_cutoff()
    was = rv._cutoff_value
    check("a cutoff that isn't a number keeps the cutoff as it was", rv.cutoff_var.get() == f"{was:g}")
    rv.cutoff_var.set("2,5"); rv._apply_cutoff()
    check("a decimal comma is read as a point", rv._cutoff_value == 2.5)
    # A tracked video is being saved: letting go of the file asks first.
    pw._save = ("thread", "cancel", {})         # stands in for a save in progress
    check("showing the same file again never asks", rv.release(rv._data) and rv.saving_video())
    log.clear(); yesno[:] = [False]
    check("selecting another file while a video is being saved asks, and Keep Saving keeps it",
          rv.release(object()) is False and log == ["A video is still being saved"])
    log.clear(); yesno[:] = [False]; app.clear_files(); app.update()
    check("Clear is held back too", len(app.files) == 1 and pw.winfo_exists()
          and "A video is still being saved" in log)
    yesno[:] = [True]
    check("Stop Saving lets it go", rv.release(None) is True)
    pw._save = None
    check("with no save running nothing is asked", rv.release(None) and not rv.saving_video())
    pw.close()
else:
    check("playback window opens on the Open Field example", False)
class NoVideo:
    video = os.path.join(tmp, "gone.mp4"); n_frames = 5; fps = 10.0
    has_body_points = False
before = len(app.winfo_children())
try:
    review_panel.PlaybackWindow(app, NoVideo(), [], [], "gone"); raised = False
except Exception:
    raised = True
app.update()
check("a playback window that can't open its video leaves no blank window behind",
      raised and len(app.winfo_children()) == before)

app._setup_win = None
app.destroy()
print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
