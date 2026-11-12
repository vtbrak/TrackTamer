"""The Review tab and the playback window (user, 2026-11-05).

The Review tab lists the moments to check: every stretch where the tracked
point was outside all the drawn regions. Brief ones are jumps at the wall or
head dips, and they count for the region they belong to. A long one may mean
the tracker got stuck on a dark spot or a reflection, so stretches at least
as long as the cutoff are flagged. "Open playback window", or clicking a row,
opens the video in its own resizable window at that exact frame. (The video
was first built into the tab; it was too cramped there. A separate window
will also suit manual scoring, e.g. object recognition, later.)

The playback window: play/pause (space bar on the video), one-frame and
10-second steps, a scrub slider and a speed choice. It draws a red marker on
the tracked position, an optional short trail, and region outlines. The info
line shows the session frame and time, the video's own frame and time
(tracking files record the video frame of their first row), and the region
each frame counted for. "Save as video…" writes `<name>_tracked.mp4` beside
the video in the background.

Adapted from ezTrack's `PlayVideo` via core/playback.py (GPL-3.0, see LICENSE).
"""

from __future__ import annotations

import os
import threading
import time
import tkinter as tk
import traceback
from tkinter import ttk

from core.metrics import _outside_mask, outside_events, region_labels, secs
import numpy as np

from core.objects import (KINDS, PHASES, Bout, distance_px, file_objects, load_scoring,
                          object_at, save_scoring, scoring_path, trial_info,
                          unreadable_copy_path,
                          update_trial_info, zone_visits)
from core.asr import REAL_COLUMN, save_review, startle_review
from core.playback import FrameSource, open_playback, tracked_video_path, write_tracked_video
from dialogs import ask_yes_no, bold_font, fit_window, show_info, show_warning
from setup_window import FrameCanvas
from tooltip import Tooltip

SPEEDS = ("0.25x", "0.5x", "1x", "2x", "4x", "8x")
TRAIL_SECONDS = 1.0
SKIP_SECONDS = 10
MARKER_COLOR = "#ff2828"
TRAIL_COLOR = "#ffc828"
NOSE_COLOR = "#ff2828"      # nose, center and rear end (ROADMAP §17)
CENTER_COLOR = "#ffe600"
REAR_COLOR = "#00a0ff"
ROI_COLOR = "#5adc5a"
OBJECT_COLOR = "#ff9f1a"
ZONE_COLOR = "#ffffff"
ACTIVE_COLOR = "#39d353"
VISIT_COLUMNS = (("#", 34), ("Object", 90), ("Frame", 64), ("Session time", 84),
                 ("Video time", 78), ("Length (s)", 66), ("Scored", 110))
TRIAL_COLUMNS = (("#", 34), ("Type", 104), ("kHz", 48), ("Stimulus frame", 92),
                 ("Video time", 78), ("Before", 66), ("After", 66), ("Amplitude", 76),
                 ("Peak frame", 76), ("Reaction (ms)", 88), ("Real startle", 84),
                 ("Note", 150))
MARK_TEXT = {"yes": "yes", "no": "no", "": "to review"}
STIMULUS_COLOR = "#ffd23f"
PEAK_COLOR = "#ff5a5a"
STATUS_TEXT = {"scored": "interaction", "none": "no interaction", "": "to review"}
EVENT_COLUMNS = (("#", 34), ("Frame", 64), ("Session time", 84), ("Video frame", 78),
                 ("Video time", 78), ("Length (s)", 66), ("Counted as", 96),
                 ("Px outside", 70), ("Check", 70))


# How to review startles (user, 2026-11-12). Shown from the playback window
# ("How to review…") and kept in step with README "Reviewing startles".
STARTLE_GUIDE_TITLE = "How to review startles"
STARTLE_GUIDE = """\
Why review

Track Tamer measures a startle as a jump in movement on the video just \
after the sound. It can't tell a startle from any other movement. A mouse \
that is rearing or walking when the sound comes gives a "startle" that \
isn't one. So each trial is looked at, and marked real or not.

For each trial

1. Click the trial in the Review list, or Next trial. The video opens on \
the stimulus frame.
2. Go back about a second (the one-frame button, or Play at 0.25x) and \
watch the animal up to the stimulus and through it. Go to peak shows the \
frame Track Tamer measured.
3. Mark it Yes or No (the Y and N keys do the same).

Yes: a real trial

- The animal was still or settled when the sound came, and the movement \
after it is its reaction to the sound.
- The animal didn't react at all. No response is a real result: mark it \
Yes. Leaving those out would make the startle look larger than it is.

No: not a real startle

- The animal was already doing something else just before or during the \
stimulus: rearing or coming down from a rear, grooming, walking, turning, \
jumping, climbing, digging.
- The video would count that movement as a startle, or a real startle \
would be buried in it.

Not reasons for No: a small response, no response, or a late one. Judge \
only whether other movement was going on.

What the marks do

- A trial marked No stays in the Trials table with its numbers, marked \
no, and is left out of every result: the means, startle by level, \
prepulse inhibition and habituation. It's drawn dotted in the Aligned \
Trials plot.
- Each mark is saved at once in the video's info file, so closing the \
window loses nothing. Click the other button to change a mark.
- Trials with no amplitude (red in the list) aren't used and don't need \
a mark.

Done reviewing

When every trial is marked, click Done reviewing. It records that you \
have looked at every startle and judged that the ones marked Yes are not \
due to other movement before or during the stimulus. The Data Summary \
says so (ASR_ReviewDone), with how many trials were marked not real. If \
some trials aren't marked yet, Track Tamer says which and takes you to \
the first."""


def clock(seconds: float) -> str:
    """m:ss.ss"""
    return f"{int(seconds // 60)}:{seconds % 60:05.2f}"


class ObjectScorer:
    """A file's object recognition scoring while it's reviewed (ROADMAP §15):
    its objects, zones and zone visits, and the logged interactions, saved
    to `<name>_ObjectScoring.csv` after every change. `on_change` runs after
    each change (the Review list and results update)."""

    def __init__(self, data, fps: float, zone_cm: float, min_frames: int = 1,
                 on_change=None):
        self.data, self.fps, self.min_frames = data, fps, max(1, int(min_frames))
        self.objects = file_objects(data)
        self.scoring = load_scoring(data)
        self.on_change = on_change or (lambda: None)
        self.pending: tuple[str, int] | None = None   # (object, start row) of an open bout
        self.set_zone(zone_cm)

    def set_zone(self, zone_cm: float) -> None:
        if zone_cm == getattr(self, "zone_cm", None):
            return     # same zones: keep the visits (the window may be showing one)
        self.zone_cm = zone_cm
        self.zone_px, self.scaled = distance_px(self.data, zone_cm)
        self.visits = zone_visits(self.data, self.objects, self.zone_px, self.fps,
                                  self.min_frames)

    def object_at(self, row: int) -> str:
        return object_at(self.data, self.objects, self.zone_px, row)

    def visit_at(self, row: int, obj: str | None = None) -> dict | None:
        """The zone visit (of `obj`, if given) that `row` falls in."""
        for v in self.visits:
            if v["row"] <= row <= v["end"] and (obj is None or v["object"] == obj):
                return v
        return None

    def _changed(self) -> str | None:
        """Save, then tell the listeners. Returns an error message if the
        file couldn't be written (the scoring stays in memory)."""
        error = None
        try:
            save_scoring(self.data, self.scoring, self.fps)
        except OSError as exc:
            error = str(exc)
        self.on_change()
        return error

    def start(self, obj: str, row: int) -> None:
        self.pending = (obj, row)

    def end(self, row: int):
        """Close the open interaction at `row`. Returns (bout, save error)."""
        obj, start = self.pending
        self.pending = None
        bout = self.scoring.add_bout(obj, start, row)
        # A visit with an interaction is no longer "no interaction".
        for v in self.visits:
            if v["object"] == obj and v["row"] <= bout.end and bout.start <= v["end"]:
                self.scoring.no_interaction -= self.scoring.marks_in(v)
        return bout, self._changed()

    def toggle_none(self, visit: dict) -> str | None:
        marks = self.scoring.marks_in(visit)
        if marks:
            self.scoring.no_interaction -= marks
        else:
            self.scoring.no_interaction.add((visit["object"], visit["row"]))
        return self._changed()

    def delete(self, item) -> str | None:
        if isinstance(item, Bout):
            self.scoring.bouts.remove(item)
        else:
            self.scoring.no_interaction.discard(item)
        return self._changed()

    def totals(self) -> dict[str, tuple[float, int]]:
        """{object: (interaction seconds, bouts)}."""
        out = {}
        for o in self.objects:
            mine = [b for b in self.scoring.bouts if b.object == o.name]
            out[o.name] = (secs(sum(b.frames() for b in mine), self.fps), len(mine))
        return out


def _blank(value) -> bool:
    return value is None or (isinstance(value, float) and value != value)


class StartleTrials:
    """A startle file's trials, for the Review list and the playback window
    (ROADMAP §13): where each stimulus and peak falls in the file's rows."""

    def __init__(self, data, trials, startle_ms: float, baseline_ms: float):
        self.data, self.startle_ms, self.baseline_ms = data, startle_ms, baseline_ms
        self.frames = data.df["Frame"].to_numpy(dtype=int)
        self.times = data.df["Time_s"].to_numpy(dtype=float)
        self.values = data.df["MotionIndex_pct"].to_numpy(dtype=float)
        self.rows = trials.to_dict("records")
        # The experimenter's marks (real startle or not), shared with the
        # results: one object per loaded file.
        self.review = startle_review(data)

    def mark(self, k: int) -> str:
        """Trial k's mark: "yes", "no", or "" (not marked)."""
        return self.review.text(self.rows[k]["Stimulus_Frame"])

    def needs_mark(self, k: int) -> bool:
        """A trial with no amplitude isn't used, so it needs no mark."""
        return not _blank(self.rows[k].get("Startle amplitude_pct"))

    def unmarked(self) -> list[int]:
        return [k for k in range(len(self.rows)) if self.needs_mark(k) and not self.mark(k)]

    def set_mark(self, k: int, real: bool) -> None:
        frame = int(self.rows[k]["Stimulus_Frame"])
        self.review.marks[frame] = bool(real)
        self.rows[k][REAL_COLUMN] = self.review.text(frame)

    def progress(self) -> str:
        """ "12 of 36 marked, 2 not real", for the status lines."""
        need = [k for k in range(len(self.rows)) if self.needs_mark(k)]
        marked = [k for k in need if self.mark(k)]
        no = sum(self.mark(k) == "no" for k in range(len(self.rows)))
        return (f"{len(marked)} of {len(need)} marked"
                + (f", {no} not real" if no else ""))

    def row_of(self, frame) -> int | None:
        """The file row showing a video frame (None if it isn't analyzed)."""
        if _blank(frame):
            return None
        at = int(np.searchsorted(self.frames, int(frame)))
        return at if at < len(self.frames) and self.frames[at] == int(frame) else None

    def stimulus_row(self, k: int) -> int | None:
        return self.row_of(self.rows[k]["Stimulus_Frame"])

    def peak_row(self, k: int) -> int | None:
        return self.row_of(self.rows[k].get("FrameNo"))

    def describe(self, k: int, row: int) -> str:
        """Where a frame sits relative to trial k's stimulus and windows."""
        t = self.rows[k]
        zero = t.get("Stimulus_s")
        if _blank(zero):
            return f"trial {t['Trial']} ({t['Type']})"
        offset = (float(self.times[row]) - float(zero)) * 1000
        end = float(zero)
        if t["Type"] == "prepulse+pulse" and not _blank(t.get("Interval_ms")):
            end -= float(t["Interval_ms"]) / 1000
        now, tiny = float(self.times[row]), 1e-6
        place = ""
        if float(zero) + tiny < now <= float(zero) + self.startle_ms / 1000 + tiny:
            place = ", startle window"
        elif end - self.baseline_ms / 1000 + tiny < now <= end + tiny:
            place = ", baseline window"
        return f"trial {t['Trial']} ({t['Type']}): {offset:+.0f} ms from the stimulus{place}"


def _no_button_focus(widget) -> None:
    """Stop every button under `widget` taking the keyboard focus when
    clicked, so the window's keys (Space, S, E, N) keep working after a
    click and Space can't re-press the last button (it would on Windows)."""
    for child in widget.winfo_children():
        if isinstance(child, (ttk.Button, ttk.Checkbutton)):
            child.configure(takefocus=False)
        _no_button_focus(child)


class PlaybackWindow(tk.Toplevel):
    """A tracked file's video with its tracking drawn on, in its own window."""

    def __init__(self, parent, pb, labels, outside, title: str, scorer=None,
                 on_visit=None, startle=None, on_mark=None, on_done=None):
        super().__init__(parent)
        self.pb = pb
        self.scorer = scorer
        self.startle = startle
        self.trial: int | None = None     # the startle trial being viewed
        self.on_mark = on_mark or (lambda k, real: None)    # a trial marked real or not
        self.on_done = on_done or (lambda: None)            # Done reviewing clicked
        self._guide = None
        self.on_visit = on_visit or (lambda index: None)   # Review list follows
        try:
            self.source = FrameSource(pb)
        except Exception:
            self.destroy()      # don't leave a blank window behind
            raise
        self._labels, self._outside = labels, outside
        self.title(f"Playback: {title}")
        fit_window(self, 960, 900 if scorer else 840 if startle else 760)
        self.minsize(600, 480)
        self.row = 0
        self.playing = False
        self._job = None
        self._clock = None
        self._save = None
        self._setting = False
        try:
            self._build()
            _no_button_focus(self)
            self.protocol("WM_DELETE_WINDOW", self.close)
            self.show(0)
        except Exception:
            self.source.close()
            self.destroy()
            raise

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        # Controls are packed first, from the bottom, so a small window
        # shrinks the video instead of hiding them; two short rows fit narrow.
        bar2 = ttk.Frame(self, padding=(8, 0, 8, 8))
        bar2.pack(side=tk.BOTTOM, fill=tk.X)
        if self.scorer is not None:
            self._build_scoring()
        if self.startle is not None:
            self._build_startle()
        bar = ttk.Frame(self, padding=(8, 6, 8, 4))
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.slider = ttk.Scale(self, from_=0, to=max(self.pb.n_frames - 1, 0),
                                orient=tk.HORIZONTAL, command=self._on_slider)
        self.slider.pack(side=tk.BOTTOM, fill=tk.X, padx=8)
        self.info = ttk.Label(self, anchor=tk.W, padding=(8, 4), justify=tk.LEFT)
        self.info.pack(side=tk.BOTTOM, fill=tk.X)
        self.info.bind("<Configure>",
                       lambda e: self.info.configure(wraplength=max(200, e.width - 16)))
        self.canvas = FrameCanvas(self)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.canvas.redraw_overlay = self._overlay
        # Space plays and pauses wherever the focus is. (On Windows a clicked
        # button keeps the focus and Space would press it again, so the
        # buttons here never take it: see the end of __init__.)
        self.bind("<space>", lambda e: self._key(e, self.toggle))
        for text, cmd, tip in (
                ("◀◀", lambda: self.skip(-SKIP_SECONDS), "Back 10 seconds"),
                ("◀", lambda: self.step(-1), "Back 1 frame")):
            b = ttk.Button(bar, text=text, width=3, command=cmd)
            b.pack(side=tk.LEFT)
            Tooltip(b, tip)
        self.play_btn = ttk.Button(bar, text="Play", width=7, command=self.toggle)
        self.play_btn.pack(side=tk.LEFT, padx=4)
        Tooltip(self.play_btn, "Play or pause (space bar with the pointer on the video).")
        for text, cmd, tip in (
                ("▶", lambda: self.step(1), "Forward 1 frame"),
                ("▶▶", lambda: self.skip(SKIP_SECONDS), "Forward 10 seconds")):
            b = ttk.Button(bar, text=text, width=3, command=cmd)
            b.pack(side=tk.LEFT)
            Tooltip(b, tip)
        ttk.Label(bar, text="Speed:").pack(side=tk.LEFT, padx=(12, 4))
        self.speed_var = tk.StringVar(value="1x")
        speed = ttk.Combobox(bar, textvariable=self.speed_var, values=SPEEDS,
                             state="readonly", width=6)
        speed.pack(side=tk.LEFT)
        speed.bind("<<ComboboxSelected>>", lambda _e: self._restart_clock())
        self.trail_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar2, text="Trail", variable=self.trail_var,
                        command=self._redraw).pack(side=tk.LEFT)
        self.roi_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar2, text="Objects" if self.scorer else "Regions",
                        variable=self.roi_var,
                        command=self._redraw).pack(side=tk.LEFT, padx=(8, 0))
        self.body_var = tk.BooleanVar(value=True)
        if self.pb.has_body_points:
            body = ttk.Checkbutton(bar2, text="Nose and rear end", variable=self.body_var,
                                   command=self._redraw)
            body.pack(side=tk.LEFT, padx=(8, 0))
            Tooltip(body, "Show the nose (red) and the rear end (blue) beside the "
                          "center (yellow). They are blank in frames where they "
                          "couldn't be told.")
        self.save_btn = ttk.Button(bar2, text="Save as video…", command=self.save_video)
        self.save_btn.pack(side=tk.RIGHT)
        shown = "objects and their zones" if self.scorer else "regions"
        Tooltip(self.save_btn, f"Write {os.path.basename(tracked_video_path(self.pb.video))} "
                               "next to the video: the session with the marker (and the "
                               f"trail and {shown}, if shown) drawn on, at the video's own "
                               "frame rate. Replaces an earlier one.")
        self.save_text = ttk.Label(bar2, foreground="gray")
        self.save_text.pack(side=tk.RIGHT, padx=8)
        if self.startle is not None:   # no tracked position to show or save
            bar2.pack_forget()

    # ------------------------------------------------------------- showing
    def _trail_frames(self) -> int:
        if not self.trail_var.get():
            return 0
        return int(round(TRAIL_SECONDS * (self.pb.fps or 20)))

    def show(self, row: int) -> None:
        if not self.winfo_exists():
            return
        self.row = max(0, min(self.pb.n_frames - 1, row))
        try:
            frame = self.source.frame(self.row)
        except Exception:
            traceback.print_exc()
            frame = None
        if frame is not None:
            self.canvas.show(frame)
        else:
            self._redraw()  # keep the last image; the info line says why
        self._set_slider(self.row)
        self._update_info(frame is None)
        if self.scorer is not None:
            self._follow_object()

    def _redraw(self) -> None:
        self.canvas._render()

    def _overlay(self) -> None:
        if self.pb is None:
            return
        c, pb, row = self.canvas, self.pb, self.row
        if self.roi_var.get():
            for _name, (xs, ys) in pb.regions().items():
                pts = [v for x, y in zip(xs, ys) for v in c.to_screen(x, y)]
                if len(pts) >= 6:
                    c.create_polygon(*pts, outline=ROI_COLOR, fill="", width=1)
        if self.scorer is not None and self.roi_var.get():
            sc = self.scorer
            here = sc.object_at(row)
            pending = sc.pending[0] if sc.pending else None
            for o in sc.objects:
                sx, sy = c.to_screen(o.x, o.y)
                r, z = o.r * c.scale, (o.r + sc.zone_px) * c.scale
                color = ACTIVE_COLOR if o.name == pending else OBJECT_COLOR
                c.create_oval(sx - r, sy - r, sx + r, sy + r, outline=color, width=2)
                c.create_oval(sx - z, sy - z, sx + z, sy + z, outline=ZONE_COLOR,
                              dash=(6, 4), width=2 if o.name == here else 1)
                c.create_text(sx, sy - z - 10, text=f"{o.name} ({o.kind.lower()})",
                              fill="white", font=bold_font(11))
        if self.startle is not None and self.trial is not None:
            words = []
            if row == self.startle.stimulus_row(self.trial):
                words.append(("STIMULUS", STIMULUS_COLOR))
            if row == self.startle.peak_row(self.trial):
                words.append(("STARTLE PEAK", PEAK_COLOR))
            for k, (text, color) in enumerate(words):
                c.create_text(c.winfo_width() / 2, 24 + 28 * k, text=text, fill=color,
                              font=bold_font(18))
        trail = self._trail_frames()
        if trail:
            pts = pb.trail(row, trail)
            for a, b in zip(pts, pts[1:]):
                if a and b:
                    c.create_line(*c.to_screen(*a), *c.to_screen(*b), fill=TRAIL_COLOR,
                                  width=2)
        pos = pb.position(row)
        show_body = pb.has_body_points and self.body_var.get()
        body = pb.body_points(row) if show_body else None
        if body:
            (nx, ny), (rx, ry) = c.to_screen(*body[0]), c.to_screen(*body[1])
            c.create_line(rx, ry, nx, ny, fill="white", width=1)
            c.create_oval(rx - 5, ry - 5, rx + 5, ry + 5, fill=REAR_COLOR,
                          outline="white", width=1)
            c.create_oval(nx - 5, ny - 5, nx + 5, ny + 5, fill=NOSE_COLOR,
                          outline="white", width=1)
        if pos:
            sx, sy = c.to_screen(*pos)
            size = 5 if show_body else 6
            c.create_oval(sx - size, sy - size, sx + size, sy + size,
                          fill=CENTER_COLOR if show_body else MARKER_COLOR,
                          outline="white", width=1)

    def _update_info(self, unread_video: bool = False) -> None:
        pb, row = self.pb, self.row
        vf = pb.video_frame(row)
        parts = [f"Frame {row + 1:,} of {pb.n_frames:,}", f"session {clock(row / pb.fps)}",
                 f"video frame {vf:,}", f"video time {clock(vf / pb.fps)}"]
        if pb.unreadable(row):
            parts.append("unreadable frame (no position)")
        elif self.startle is None and pb.position(row) is None:
            parts.append("no position found")
        if pb.has_body_points and pb.position(row) is not None and pb.body_points(row) is None:
            parts.append("nose and rear end not found")
        if pb.unreadable(row) or (self.startle is None and pb.position(row) is None):
            pass    # said above; no region or zone to add
        elif self.startle is not None:
            value = self.startle.values[row]
            parts.append("no motion index" if value != value else f"motion index {value:.4f}%")
            if self.trial is not None:
                parts.append(self.startle.describe(self.trial, row))
        elif self.scorer is not None:
            here = self.scorer.object_at(row)
            parts.append(f"in the {here} zone" if here else "in no object zone")
        else:
            region = self._labels[row] if row < len(self._labels) else ""
            text = f"region: {region}" if region else "in no region"
            if row < len(self._outside) and self._outside[row]:
                text += " (outside the drawn regions)"
            parts.append(text)
        if self.scorer is not None and self.scorer.pending:
            obj, start = self.scorer.pending
            parts.append(f"interaction with {obj} open since frame {start + 1:,}")
        if unread_video:
            parts.append("the video frame couldn't be read")
        self.info.configure(text="   ·   ".join(parts))

    def _set_slider(self, row: int) -> None:
        self._setting = True
        self.slider.set(row)
        self._setting = False

    def _on_slider(self, value) -> None:
        if self._setting or self.pb is None:
            return
        row = int(float(value))
        if row != self.row:
            self.show(row)
            self._restart_clock()

    def step(self, delta: int) -> None:
        self.pause()
        self.show(self.row + delta)

    def skip(self, seconds: float) -> None:
        if self.pb is None:
            return
        self.show(self.row + int(round(seconds * (self.pb.fps or 20))))
        self._restart_clock()

    # ------------------------------------------------------------- playing
    def _speed(self) -> float:
        try:
            return float(self.speed_var.get().rstrip("x"))
        except ValueError:
            return 1.0

    def _restart_clock(self) -> None:
        self._clock = (time.perf_counter(), self.row)

    def toggle(self) -> None:
        self.pause() if self.playing else self.play()

    def play(self) -> None:
        if self.pb is None:
            return
        if self.row >= self.pb.n_frames - 1:
            self.show(0)
        self.playing = True
        self.play_btn.configure(text="Pause")
        self._restart_clock()
        self._tick()

    def pause(self) -> None:
        self.playing = False
        self.play_btn.configure(text="Play")
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None

    def _tick(self) -> None:
        """Show the frame the clock is at; frames are skipped if drawing can't
        keep up, so playback runs at the chosen speed."""
        self._job = None
        if not self.playing or self.pb is None or not self.winfo_exists():
            return
        t0, r0 = self._clock
        rate = (self.pb.fps or 20) * self._speed()
        target = r0 + int((time.perf_counter() - t0) * rate)
        if target >= self.pb.n_frames - 1:
            self.show(self.pb.n_frames - 1)
            self.pause()
            return
        if target != self.row:
            self.show(target)
        self._job = self.after(max(1, int(1000 / rate)), self._tick)

    # -------------------------------------------------------------- saving
    def save_video(self) -> None:
        if self.pb is None:
            return
        if self._save is not None:
            self._save[1].set()  # the button reads Cancel saving while saving
            return
        cancel = threading.Event()
        state = {"done": 0, "total": self.pb.n_frames, "result": None, "error": None}
        trail, rois, pb = self._trail_frames(), bool(self.roi_var.get()), self.pb
        show_body = bool(self.body_var.get())
        objects = list(self.scorer.objects) if self.scorer is not None and rois else None
        zone_px = self.scorer.zone_px if self.scorer is not None else 0.0

        def work():
            try:
                state["result"] = write_tracked_video(
                    pb, trail_frames=trail, show_regions=rois,
                    objects=objects, zone_px=zone_px, show_body=show_body,
                    progress=lambda d, t: state.update(done=d, total=t),
                    should_cancel=cancel.is_set)
            except Exception as exc:
                traceback.print_exc()
                state["error"] = str(exc) or type(exc).__name__

        thread = threading.Thread(target=work, daemon=True)
        self._save = (thread, cancel, state)
        self.save_btn.configure(text="Cancel saving")
        thread.start()
        self.after(200, self._poll_save)

    def _poll_save(self) -> None:
        if self._save is None or not self.winfo_exists():
            return
        thread, cancel, state = self._save
        if thread.is_alive():
            pct = int(100 * state["done"] / state["total"]) if state["total"] else 0
            self.save_text.configure(text="Stopping…" if cancel.is_set()
                                     else f"Saving video {pct}%")
            self.after(200, self._poll_save)
            return
        self._save = None
        self.save_btn.configure(text="Save as video…")
        self.save_text.configure(text="")
        if state["error"]:
            show_warning(self, "The video couldn't be saved",
                         f"The video couldn't be saved.\n\n{state['error']}")
        elif state["result"]:
            show_info(self, "Video saved",
                      f"Saved {os.path.basename(state['result'])} next to the video.")

    # ------------------------------------------------------------- startle
    def _build_startle(self) -> None:
        """Move between the startle trials (ROADMAP §13)."""
        box = ttk.LabelFrame(self, text="Startle trials", padding=(8, 4))
        box.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8))
        row = ttk.Frame(box)
        row.pack(fill=tk.X)
        for text, command, tip in (
                ("◀ Previous trial  [", lambda: self.go_trial(-1), "The previous trial (the [ key)."),
                ("Next trial ▶  ]", lambda: self.go_trial(1), "The next trial (the ] key)."),
                ("Go to stimulus", self.go_stimulus, "This trial's stimulus frame."),
                ("Go to peak", self.go_peak, "The frame with this trial's highest motion index.")):
            button = ttk.Button(row, text=text, command=command)
            button.pack(side=tk.LEFT, padx=(0, 6))
            Tooltip(button, tip)
        self.trial_text = ttk.Label(box, anchor=tk.W, justify=tk.LEFT)
        self.trial_text.pack(fill=tk.X, pady=(4, 0))
        self.bind("<KeyPress-bracketright>", lambda e: self.go_trial(1))
        self.bind("<KeyPress-bracketleft>", lambda e: self.go_trial(-1))
        self.trial_text.configure(text="Pick a trial in the Review list, or click Next trial.")
        # Is this trial a real startle? (user, 2026-11-12) A mouse already
        # rearing or moving when the sound comes isn't one; the experimenter
        # says, per trial, and each answer is saved as it's given.
        judge = ttk.Frame(box)
        judge.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(judge, text="Real startle?", font=bold_font()).pack(side=tk.LEFT)
        self.yes_btn = ttk.Button(judge, text="Yes  Y", width=8,
                                  command=lambda: self.mark_trial(True))
        self.yes_btn.pack(side=tk.LEFT, padx=(8, 0))
        Tooltip(self.yes_btn, "The animal was still or settled when the sound came (the Y "
                              "key). Also Yes when it didn't react at all: no response is "
                              "a real result.")
        self.no_btn = ttk.Button(judge, text="No  N", width=8,
                                 command=lambda: self.mark_trial(False))
        self.no_btn.pack(side=tk.LEFT, padx=(6, 0))
        Tooltip(self.no_btn, "The animal was already rearing, grooming, walking or moving "
                             "in some other way just before or during the stimulus (the N "
                             "key). The trial is left out of the results.")
        self.mark_text = ttk.Label(judge, anchor=tk.W)
        self.mark_text.pack(side=tk.LEFT, padx=(10, 0))
        self.done_btn = ttk.Button(judge, text="Done reviewing", command=self.finish_review)
        self.done_btn.pack(side=tk.RIGHT)
        Tooltip(self.done_btn, "Click when every trial is marked. It records that you have "
                               "looked at every startle and judged that the ones marked Yes "
                               "are not due to other movement before or during the stimulus.")
        guide = ttk.Button(judge, text="How to review…", command=self.show_guide)
        guide.pack(side=tk.RIGHT, padx=(0, 6))
        Tooltip(guide, "What to look for in each trial, and what Yes and No mean.")
        for key, real in (("y", True), ("Y", True), ("n", False), ("N", False)):
            self.bind(f"<KeyPress-{key}>",
                      lambda e, real=real: self._key(e, lambda: self.mark_trial(real)))
        self.show_mark()

    def show_mark(self) -> None:
        """The status beside the Yes and No buttons: this trial's mark, how
        far the review has got, and whether it's done."""
        st = self.startle
        if st is None or not self.winfo_exists():
            return
        if self.trial is None or self.trial >= len(st.rows):
            here = ""
        elif not st.needs_mark(self.trial):
            here = f"Trial {st.rows[self.trial]['Trial']}: no amplitude, no mark needed.   "
        else:
            mark = st.mark(self.trial)
            here = (f"Trial {st.rows[self.trial]['Trial']}: "
                    + (f"marked {mark.upper()}" if mark else "not marked yet") + ".   ")
        self.mark_text.configure(text=here + st.progress() + ".")
        self.done_btn.configure(text="Review done ✓" if st.review.done and not st.unmarked()
                                else "Done reviewing")

    def mark_trial(self, real: bool) -> None:
        """Mark the trial being viewed as a real startle or not."""
        st = self.startle
        if self.trial is None:
            self.mark_text.configure(text="Pick a trial first (the Review list, or Next trial).")
            return
        if not st.needs_mark(self.trial):
            self.show_mark()
            return
        self.on_mark(self.trial, real)
        self.show_mark()

    def finish_review(self) -> None:
        self.pause()
        self.on_done()
        self.show_mark()

    def show_guide(self) -> None:
        """The written guide, in its own window so it can stay open beside
        the video."""
        if self._guide is not None and self._guide.winfo_exists():
            self._guide.deiconify()
            self._guide.lift()
            return
        self._guide = GuideWindow(self, STARTLE_GUIDE_TITLE, STARTLE_GUIDE)

    def open_trial(self, k: int) -> None:
        """Show trial k at its stimulus frame."""
        st = self.startle
        self.pause()
        row = st.stimulus_row(k)
        t = st.rows[k]
        self.trial = k
        amplitude = t.get("Startle amplitude_pct")
        note = t.get("Note")
        self.trial_text.configure(text=(
            f"Trial {k + 1} of {len(st.rows)}: {t['Type']}, stimulus frame {t['Stimulus_Frame']:,}, "
            + ("no amplitude" if _blank(amplitude) else f"amplitude {amplitude:g}")
            + (f" ({note})" if isinstance(note, str) and note else "")))
        self.show_mark()
        if row is None:
            self._redraw()
            return
        self.show(row)
        self.on_visit(k)

    def go_trial(self, step: int) -> None:
        st = self.startle
        order = [k for k in range(len(st.rows)) if st.stimulus_row(k) is not None]
        if not order:
            return
        span = max(15, int(round(0.5 * (self.pb.fps or 30))))   # frames that belong to a trial
        current = self.trial if self.trial in order else None
        near = current is not None and abs(self.row - st.stimulus_row(current)) <= span
        anchor = st.stimulus_row(current) if near else self.row
        if step > 0:
            later = [k for k in order if st.stimulus_row(k) > anchor]
            target = later[0] if later else None
        else:
            earlier = [k for k in order if st.stimulus_row(k) < anchor]
            target = earlier[-1] if earlier else None
        if target is None:
            self.trial_text.configure(text="That was the last trial." if step > 0
                                      else "That was the first trial.")
            return
        self.open_trial(target)

    def go_stimulus(self) -> None:
        if self.trial is not None and self.startle.stimulus_row(self.trial) is not None:
            self.pause()
            self.show(self.startle.stimulus_row(self.trial))

    def go_peak(self) -> None:
        if self.trial is not None and self.startle.peak_row(self.trial) is not None:
            self.pause()
            self.show(self.startle.peak_row(self.trial))

    # ------------------------------------------------------------- scoring
    def _build_scoring(self) -> None:
        """Object recognition scoring (ROADMAP §15): log the start and end of
        each interaction, or mark a zone visit as no interaction."""
        sc = self.scorer
        box = ttk.LabelFrame(self, text="Score interactions", padding=(8, 4))
        box.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 4))
        row = ttk.Frame(box)
        row.pack(fill=tk.X)
        ttk.Label(row, text="Object:").pack(side=tk.LEFT)
        self.object_var = tk.StringVar()
        self.object_box = ttk.Combobox(row, textvariable=self.object_var, state="readonly",
                                       width=12, values=[o.name for o in sc.objects])
        self.object_box.pack(side=tk.LEFT, padx=(4, 8))
        self.object_box.bind("<<ComboboxSelected>>", lambda _e: self._picked_object())
        Tooltip(self.object_box, "The object being scored. It follows the zone the "
                                 "tracked point is in; pick one by hand if the point is "
                                 "elsewhere (e.g. the tracker missed it).")
        self.start_btn = ttk.Button(row, text="Start interaction (S)",
                                    command=self.mark_start)
        self.start_btn.pack(side=tk.LEFT)
        self.end_btn = ttk.Button(row, text="End interaction (E)", command=self.mark_end)
        self.end_btn.pack(side=tk.LEFT, padx=(6, 0))
        self.cancel_btn = ttk.Button(row, text="Cancel start (Esc)", command=self.cancel_start,
                                     state="disabled")
        self.cancel_btn.pack(side=tk.LEFT, padx=(6, 0))
        Tooltip(self.cancel_btn, "Drop an interaction that was started by mistake. Nothing "
                                 "is logged. (Only while an interaction is open.)")
        self.none_btn = ttk.Button(row, text="No interaction (N)", command=self.mark_none)
        self.none_btn.pack(side=tk.LEFT, padx=(6, 0))
        nav = ttk.Frame(box)
        nav.pack(fill=tk.X, pady=(4, 0))
        self.prev_visit_btn = ttk.Button(nav, text="◀ Previous visit  [",
                                         command=lambda: self.go_visit(-1))
        self.prev_visit_btn.pack(side=tk.LEFT)
        self.next_visit_btn = ttk.Button(nav, text="Next visit ▶  ]",
                                         command=lambda: self.go_visit(1))
        self.next_visit_btn.pack(side=tk.LEFT, padx=(6, 0))
        self.visit_text = ttk.Label(nav, foreground="gray")
        self.visit_text.pack(side=tk.LEFT, padx=(10, 0))
        Tooltip(self.next_visit_btn, "Go to the next zone visit in the list, at the frame "
                                     "the point enters the zone (the ] key).")
        Tooltip(self.prev_visit_btn, "Go back to the previous zone visit (the [ key).")
        Tooltip(self.start_btn, "The interaction starts on the frame shown. Step to the "
                                "frame it ends on, then click End interaction.")
        Tooltip(self.none_btn, "Mark the zone visit shown (or the last one opened) as "
                               "reviewed with no interaction. Click again to undo.")
        self.score_text = ttk.Label(box, foreground="#b26a00", anchor=tk.W, justify=tk.LEFT)
        self.score_text.pack(fill=tk.X, pady=(4, 0))
        self.score_text.bind("<Configure>", lambda e: self.score_text.configure(
            wraplength=max(200, e.width - 8)))
        lst = ttk.Frame(box)
        lst.pack(fill=tk.X, pady=(4, 0))
        self.bout_tree = ttk.Treeview(lst, columns=("type", "object", "start", "end", "length"),
                                      show="headings", height=4, selectmode="browse")
        for col, text, width in (("type", "Logged", 110), ("object", "Object", 90),
                                 ("start", "Start frame", 80), ("end", "End frame", 80),
                                 ("length", "Length (s)", 72)):
            self.bout_tree.heading(col, text=text)
            self.bout_tree.column(col, width=width, anchor=tk.CENTER)
        vsb = ttk.Scrollbar(lst, orient="vertical", command=self.bout_tree.yview)
        self.bout_tree.configure(yscrollcommand=vsb.set)
        self.bout_tree.pack(side=tk.LEFT, fill=tk.X, expand=True)
        vsb.pack(side=tk.LEFT, fill=tk.Y)
        self.bout_tree.bind("<<TreeviewSelect>>", lambda _e: self._bout_selected())
        side = ttk.Frame(lst)
        side.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0))
        ttk.Button(side, text="Delete", command=self.delete_logged).pack(anchor="n")
        self.totals_text = ttk.Label(side, justify=tk.LEFT)
        self.totals_text.pack(anchor="n", pady=(8, 0))
        self.bind("<KeyPress-bracketright>", lambda e: self._key(e, lambda: self.go_visit(1)))
        self.bind("<KeyPress-bracketleft>", lambda e: self._key(e, lambda: self.go_visit(-1)))
        self.bind("<Escape>", lambda e: self._key(e, self.cancel_start))
        for key, fn in (("s", self.mark_start), ("e", self.mark_end), ("n", self.mark_none)):
            for k in (key, key.upper()):
                self.bind(f"<KeyPress-{k}>", lambda e, fn=fn: self._key(e, fn))
        self._manual_object = False
        self.visit: dict | None = None     # the zone visit opened from the list
        self._logged: list = []
        self._fill_logged()

    def _key(self, e, fn) -> None:
        # Not while typing in a box. (A dropdown is an Entry too, but these
        # are pick-only, so the keys work with one focused.)
        w = e.widget
        if isinstance(w, (tk.Entry, ttk.Entry)) and str(w.cget("state")) != "readonly":
            return
        fn()

    def _picked_object(self) -> None:
        self._manual_object = True

    def _follow_object(self) -> None:
        """Pick the object whose zone the point is in, unless one was picked
        by hand or an interaction is open."""
        sc = self.scorer
        if sc.pending:
            self.object_var.set(sc.pending[0])
            return
        here = sc.object_at(self.row)
        if here and (not self._manual_object or here == self.object_var.get()):
            self.object_var.set(here)
            self._manual_object = False
        elif not self.object_var.get() and sc.objects:
            self.object_var.set(sc.objects[0].name)

    def _say(self, text: str, error: str | None = None) -> None:
        if error:
            show_warning(self, "Scoring not saved",
                         f"The scoring couldn't be saved to a file.\n\n{error}\n\nIt's "
                         "kept while the app is open.")
        self.score_text.configure(text=text)

    def mark_start(self) -> None:
        sc, obj = self.scorer, self.object_var.get()
        if not obj:
            self._say("Pick the object first.")
            return
        self.pause()
        sc.start(obj, self.row)
        self.cancel_btn.configure(state="normal")
        self._say(f"Interaction with {obj} started at frame {self.row + 1:,}. Step to the "
                  "frame it ends on and click End interaction (E).")
        self._redraw()

    def cancel_start(self) -> None:
        """Drop the open interaction without logging anything (a Start
        pressed by mistake; user, 2026-11-11)."""
        sc = self.scorer
        if not sc.pending:
            return
        obj, start = sc.pending
        sc.pending = None
        self.cancel_btn.configure(state="disabled")
        self._say(f"The start at frame {start + 1:,} ({obj}) was cancelled. Nothing was "
                  "logged.")
        self._redraw()
        self._update_info()

    def mark_end(self) -> None:
        sc = self.scorer
        if not sc.pending:
            self._say("Click Start interaction (S) at the frame the interaction starts "
                      "first.")
            return
        self.pause()
        bout, error = sc.end(self.row)
        self.cancel_btn.configure(state="disabled")
        self._say(f"Logged: {bout.object}, frames {bout.start + 1:,}–{bout.end + 1:,} "
                  f"({secs(bout.frames(), sc.fps):g} s).", error)
        self._fill_logged()
        self._redraw()

    def mark_none(self) -> None:
        sc = self.scorer
        visit = sc.visit_at(self.row, self.object_var.get() or None) or sc.visit_at(self.row)
        if visit is None:
            visit = self.visit
        if visit is None:
            self._say("This frame isn't in a zone visit. Open one from the Review list "
                      "to mark it as no interaction.")
            return
        if sc.scoring.visit_status(visit) == "scored":
            self._say(f"That {visit['object']} visit (from frame {visit['row'] + 1:,}) "
                      "already has an interaction logged. Delete it first to mark the "
                      "visit as no interaction.")
            return
        was = (visit["object"], visit["row"]) in sc.scoring.no_interaction
        error = sc.toggle_none(visit)
        self._say((f"Unmarked: {visit['object']} visit from frame {visit['row'] + 1:,}."
                   if was else
                   f"Marked: no interaction in the {visit['object']} visit from frame "
                   f"{visit['row'] + 1:,}."), error)
        self._fill_logged()

    def delete_logged(self) -> None:
        sel = self.bout_tree.selection()
        if not sel:
            self._say("Select a logged line to delete it.")
            return
        item = self._logged[int(sel[0])]
        error = self.scorer.delete(item)
        self._say("Deleted.", error)
        self._fill_logged()
        self._redraw()

    def _bout_selected(self) -> None:
        sel = self.bout_tree.selection()
        if sel:
            item = self._logged[int(sel[0])]
            self.pause()
            self.show(item.start if isinstance(item, Bout) else item[1])

    def _fill_logged(self) -> None:
        sc = self.scorer
        tree = self.bout_tree
        tree.delete(*tree.get_children())
        items = [(b.start, b) for b in sc.scoring.bouts]
        items += [(row, (obj, row)) for obj, row in sc.scoring.no_interaction]
        items.sort(key=lambda t: t[0])
        self._logged = [it for _r, it in items]
        for k, it in enumerate(self._logged):
            if isinstance(it, Bout):
                values = ("Interaction", it.object, f"{it.start + 1:,}", f"{it.end + 1:,}",
                          f"{secs(it.frames(), sc.fps):g}")
            else:
                values = ("No interaction", it[0], f"{it[1] + 1:,}", "", "")
            tree.insert("", tk.END, iid=str(k), values=values)
        if self._logged:
            tree.see(str(len(self._logged) - 1))
        self.totals_text.configure(text="\n".join(
            f"{name}: {t:g} s ({n})" for name, (t, n) in sc.totals().items()))

    def go_visit(self, step: int) -> None:
        """Move to the next (+1) or previous (-1) zone visit, counted from the
        visit being scored (or from the frame shown, if it's past that visit
        or none was opened)."""
        sc = self.scorer
        if sc.pending:
            self._say(f"An interaction with {sc.pending[0]} is still open (from frame "
                      f"{sc.pending[1] + 1:,}). End it (E) before moving to another visit.")
            return
        v = self.visit
        inside = v is not None and v["row"] <= self.row <= v["end"]
        anchor = v["row"] if inside else self.row
        if step > 0:
            later = [x for x in sc.visits if x["row"] > anchor]
            target = later[0] if later else None
        else:
            earlier = [x for x in sc.visits if x["row"] < anchor]
            target = earlier[-1] if earlier else None
        if target is None:
            self._say("That was the last zone visit." if step > 0 else
                      "That was the first zone visit.")
            return
        self.open_visit(target)
        self.on_visit(sc.visits.index(target))

    def open_visit(self, visit: dict) -> None:
        """Show a zone visit from its first frame, ready to score."""
        self.visit = visit
        sc = self.scorer
        k = next((i for i, x in enumerate(sc.visits) if x is visit), None)
        if k is not None:
            self.visit_text.configure(text=f"Visit {k + 1} of {len(sc.visits)}")
        self._manual_object = False
        self.object_var.set(visit["object"])
        self.pause()
        self.show(visit["row"])
        self._say(f"{visit['object']} zone visit: frames {visit['row'] + 1:,}–"
                  f"{visit['end'] + 1:,} ({visit['seconds']:g} s). Step through it and log "
                  "each interaction with Start and End, or click No interaction.")

    # --------------------------------------------------------------- close
    def close(self) -> None:
        self.pause()
        if self._save is not None:
            self._save[1].set()
            self._save[0].join(timeout=10)
            self._save = None
        self.source.close()
        self.destroy()


class GuideWindow(tk.Toplevel):
    """Written guidance in a window of its own (not modal: it can stay open
    beside the video). Lines that stand alone and end without a full stop
    are headings."""

    def __init__(self, parent, title: str, text: str):
        super().__init__(parent)
        self.title(title)
        fit_window(self, 560, 640)
        self.minsize(360, 300)
        body = ttk.Frame(self, padding=(12, 10, 12, 10))
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Button(body, text="Close", command=self.destroy).pack(side=tk.BOTTOM, anchor=tk.E,
                                                                   pady=(8, 0))
        bar = ttk.Scrollbar(body, orient="vertical")
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text = tk.Text(body, wrap="word", yscrollcommand=bar.set, borderwidth=0,
                            highlightthickness=0, padx=6, pady=4, spacing1=2, spacing3=4)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        bar.configure(command=self.text.yview)
        self.text.tag_configure("heading", font=bold_font(), spacing1=10)
        lines = text.split("\n")
        for n, line in enumerate(lines):
            alone = (line and (n == 0 or not lines[n - 1]) and (n + 1 == len(lines) or not lines[n + 1])
                     and not line.rstrip().endswith((".", ":", ")")) and len(line) < 40)
            self.text.insert(tk.END, line + "\n", ("heading",) if alone else ())
        self.text.configure(state="disabled")     # read-only (still selectable)
        self.bind("<Escape>", lambda _e: self.destroy())


class TrialInfoDialog(tk.Toplevel):
    """Change each object's type, the trial day and the phase after tracking
    (ROADMAP §15). `on_save(kinds, day, phase)` returns True once saved; if
    it couldn't save, the dialog stays open."""

    def __init__(self, parent, objects, day: str, phase: str, on_save):
        super().__init__(parent)
        self.title("Edit trial info")
        self.transient(parent)
        self.resizable(False, False)
        self.on_save = on_save
        body = ttk.Frame(self, padding=14)
        body.pack(fill=tk.BOTH, expand=True)
        self.day_var = tk.StringVar(value=day)
        ttk.Label(body, text="Trial day:").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(body, textvariable=self.day_var, width=6).grid(row=0, column=1, sticky="w")
        self.phase_var = tk.StringVar(value=phase)
        ttk.Label(body, text="Phase:").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Combobox(body, textvariable=self.phase_var, values=("",) + PHASES,
                     state="readonly", width=12).grid(row=1, column=1, sticky="w")
        self.kind_vars: dict[str, tk.StringVar] = {}
        for k, o in enumerate(objects, start=2):
            self.kind_vars[o.name] = tk.StringVar(value=o.kind)
            ttk.Label(body, text=f"{o.name}:").grid(row=k, column=0, sticky="w", pady=3,
                                                    padx=(0, 12))
            ttk.Combobox(body, textvariable=self.kind_vars[o.name], values=KINDS,
                         state="readonly", width=12).grid(row=k, column=1, sticky="w")
        row = len(objects) + 2
        ttk.Label(body, foreground="gray", wraplength=300, justify=tk.LEFT,
                  text="Saved in this video's tracking file. There's no need to track "
                       "again, and logged interactions stay as they are.").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
        buttons = ttk.Frame(body)
        buttons.grid(row=row + 1, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Save", command=self.save).pack(side=tk.RIGHT, padx=(0, 6))
        self.bind("<Escape>", lambda _e: self.destroy())
        try:
            self.grab_set()
        except tk.TclError:
            pass  # not on screen yet; it still works without the grab

    def save(self) -> None:
        kinds = {name: var.get() for name, var in self.kind_vars.items()}
        if self.on_save(kinds, self.day_var.get().strip(), self.phase_var.get()):
            self.destroy()


class ReviewPanel(ttk.Frame):
    """The Review tab: the points to review and the button that opens the
    playback window."""

    def __init__(self, parent, on_cutoff=None, on_scored=None, on_trial_info=None):
        super().__init__(parent)
        self.on_trial_info = on_trial_info or (lambda data, kinds, day, phase: None)
        self.trial_dialog: TrialInfoDialog | None = None
        self._made_with = None      # the roles, entry rule and frame rate the list was made with
        self.on_cutoff = on_cutoff or (lambda value: None)
        self.on_scored = on_scored or (lambda data: None)
        self.scorer: ObjectScorer | None = None
        self.startle: StartleTrials | None = None
        self._warned_unsaved = False    # told once that the startle review can't be saved
        self.pb = None
        self._data = None
        self._title = ""
        self.window: PlaybackWindow | None = None
        self.events: list[dict] = []
        self._build()
        self.show_message("Select a tracked file in the file list to review its video.")

    def _build(self) -> None:
        self.message = ttk.Label(self, padding=20, wraplength=520, justify=tk.LEFT)
        self.body = ttk.Frame(self, padding=(8, 8, 8, 4))
        head = ttk.Frame(self.body)
        head.pack(side=tk.TOP, fill=tk.X)
        self.open_btn = ttk.Button(head, text="Open playback window",
                                   command=lambda: self.open_window())
        self.open_btn.pack(side=tk.LEFT)
        Tooltip(self.open_btn, "Play the selected file's video with its tracked position "
                               "drawn on, in its own window. Clicking a row below opens "
                               "it at that moment.")
        self.trial_btn = ttk.Button(head, text="Edit trial info…", command=self.edit_trial)
        Tooltip(self.trial_btn, "Change each object's type (familiar, novel or moved), the "
                                "trial day and the phase, without tracking again.")
        self.cutoff_var = tk.StringVar()
        self._cutoff_value = 1.0    # the last valid cutoff (set by load)
        cutoff = ttk.Entry(head, textvariable=self.cutoff_var, width=5)
        cutoff.pack(side=tk.RIGHT)
        cutoff.bind("<Return>", lambda _e: self._apply_cutoff())
        cutoff.bind("<FocusOut>", lambda _e: self._apply_cutoff())
        self.cutoff_label = ttk.Label(head, text="Flag stretches at least (s):")
        self.cutoff_label.pack(side=tk.RIGHT, padx=(0, 4))
        self.cutoff_entry = cutoff
        Tooltip(cutoff, "A stretch outside the regions this long or longer may mean the "
                        "tracker lost the animal (stuck on a dark spot or a reflection), "
                        "so it's flagged for review. Brief ones are usually jumps or head "
                        "dips. Saved per test.")
        self.heading = ttk.Label(self.body, text="Points to review",
                                 font=bold_font())
        self.heading.pack(side=tk.TOP, anchor="w", pady=(10, 0))
        self.summary = ttk.Label(self.body, foreground="gray", anchor=tk.W, justify=tk.LEFT)
        self.summary.pack(side=tk.TOP, fill=tk.X, pady=(2, 6))
        self.summary.bind("<Configure>",
                          lambda e: self.summary.configure(wraplength=max(200, e.width - 8)))
        wrap = ttk.Frame(self.body)
        wrap.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(wrap, columns=[c for c, _ in EVENT_COLUMNS],
                                 show="headings", selectmode="browse")
        for col, width in EVENT_COLUMNS:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=width, minwidth=width, anchor=tk.CENTER,
                             stretch=col == "Check")
        self.tree.tag_configure("flag", foreground="#c62828")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._on_event)

    def saving_video(self) -> bool:
        """True while the playback window is writing a tracked video."""
        return (self.window is not None and self.window.winfo_exists()
                and self.window._save is not None)

    def release(self, data=None) -> bool:
        """Before the Review tab lets go of its file (another file selected,
        the list cleared, the app closed): if a tracked video is still being
        saved, ask before stopping it (user, 2026-11-11). True if the file
        can be let go; False to keep it, and the save, as they are. Showing
        the same file again (`data`) never asks."""
        if not self.saving_video() or (data is not None and data is self._data):
            return True
        return ask_yes_no(
            self, "A video is still being saved",
            "A video is still being saved. Stop saving it? What has been written so "
            "far is discarded (an earlier saved video is kept), and it would need "
            "saving again.", yes="Stop Saving", no="Keep Saving")

    def show_message(self, text: str) -> None:
        """Show a note instead of the list (no file, not tracked, no video)."""
        self.unload()
        self.body.pack_forget()
        self.message.configure(text=text)
        self.message.pack(side=tk.TOP, anchor="nw")

    def load(self, data, video_hint, roles: dict, cutoff: float, title: str = "",
             zone_cm: float | None = None, min_frames: int = 1, trials=None,
             startle_ms: float = 200.0, baseline_ms: float = 200.0,
             fps: float | None = None) -> None:
        """List this tracking file's points to review (the video opens on
        request). Says why instead if the video can't be matched to it.
        With `zone_cm` (Object Recognition), the list is the zone visits to
        score instead. With `trials` (Acoustic Startle), it's the startles to
        jump to. `fps` is the frame rate the analysis uses (the Frame rate
        box): every length and time worked out here uses it, so the list and
        the scoring file agree with the results. Without it, the video's own."""
        self.cutoff_var.set(f"{cutoff:g}")
        self._cutoff_value = float(cutoff)
        objects_mode = zone_cm is not None
        startle_mode = trials is not None
        if startle_mode and data is self._data and self.pb is not None and self.startle:
            keep = self.window.trial if self.window is not None and self.window.winfo_exists() else None
            self.startle = StartleTrials(data, trials, startle_ms, baseline_ms)
            if self.window is not None and self.window.winfo_exists():
                self.window.startle, self.window.trial = self.startle, keep
            self._fill_events()
            return
        if objects_mode and not file_objects(data):
            self.show_message("This tracking file has no objects drawn, so there's "
                              "nothing to score. Draw the objects in Set up videos… "
                              "(step 5) and track the video again.")
            return
        made_with = (tuple(sorted(roles.items())), int(min_frames), fps)
        if (data is self._data and self.pb is not None and not startle_mode and not self.startle
                and objects_mode == bool(self.scorer) and made_with == self._made_with):
            if self.scorer is not None:
                self.zone_changed(zone_cm)
            else:
                self._fill_events()   # same file: just re-flag with the cutoff
            return
        self.unload()
        try:
            pb = open_playback(data, video_hint)
        except ValueError as exc:
            self.show_message(f"This file's video can't be shown.\n\n{exc}")
            return
        self.pb, self._data, self._title = pb, data, title or os.path.basename(pb.video)
        self._made_with = made_with
        fps = fps or pb.fps
        self.scorer = (ObjectScorer(data, fps, zone_cm, min_frames,
                                    on_change=self._scored) if objects_mode else None)
        if self.scorer is not None and self.scorer.scoring.unreadable:
            show_warning(self, "The saved scoring couldn't be read",
                         "The saved scoring for this file couldn't be read, so the list "
                         "starts with nothing scored.\n\n"
                         f"{os.path.basename(scoring_path(data))} may have been saved "
                         "from a spreadsheet in a different layout. It won't be lost: "
                         "before new scoring replaces it, it's copied to "
                         f"{os.path.basename(unreadable_copy_path(scoring_path(data)))}.")
        self.startle = StartleTrials(data, trials, startle_ms, baseline_ms) if startle_mode else None
        self._set_mode()
        self.events = [] if objects_mode or startle_mode else outside_events(data, roles, fps)
        # The region each frame counted for (outside frames included) and
        # which frames were outside the drawn regions, for the info line.
        self._labels = [] if startle_mode else region_labels(data, roles)[0]
        self._outside = [] if startle_mode else _outside_mask(data)
        self.message.pack_forget()
        self.body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._fill_events()

    def open_window(self, row: int | None = None) -> PlaybackWindow | None:
        """Open the playback window (or bring it forward), at `row` if given."""
        if self.pb is None:
            return None
        if self.window is None or not self.window.winfo_exists():
            try:
                self.window = PlaybackWindow(self.winfo_toplevel(), self.pb, self._labels,
                                             self._outside, self._title, scorer=self.scorer,
                                             on_visit=self._select_visit,
                                             startle=self.startle,
                                             on_mark=self._mark_trial,
                                             on_done=self._finish_review)
            except Exception as exc:
                traceback.print_exc()
                show_warning(self, "The video couldn't be opened",
                             f"The video couldn't be opened.\n\n{exc}")
                return None
        else:
            self.window.deiconify()     # it may be minimized
            self.window.lift()
        if row is not None:
            self.window.pause()
            self.window.show(row)
        return self.window

    def pause(self) -> None:
        if self.window is not None and self.window.winfo_exists():
            self.window.pause()

    # ------------------------------------------------ reviewing startles
    def _save_review(self) -> None:
        """Save the marks in the video's info file, now (so closing a window
        by accident loses nothing). If that fails they're kept, and used,
        while the app is open; the user is told once."""
        try:
            save_review(self._data, self.pb.video if self.pb is not None else None)
        except OSError as exc:
            traceback.print_exc()
            if not self._warned_unsaved:
                self._warned_unsaved = True
                show_warning(self.window if self.window is not None and self.window.winfo_exists()
                             else self, "The review wasn't saved",
                             "The review couldn't be saved to the video's info file.\n\n"
                             f"{exc}\n\nYour marks are kept while Track Tamer is open and "
                             "are used in the results; they're saved with the next mark "
                             "that can be written.")
        else:
            self._warned_unsaved = False

    def _after_review(self) -> None:
        """The marks changed: show them in the list and the window, and let
        the results follow."""
        data, keep = self._data, self.window.trial if self.window is not None else None
        self._fill_events()
        self.on_scored(data)        # (an analyzed file's results are worked out again)
        if self.window is not None and self.window.winfo_exists():
            if self.window.trial is None:
                self.window.trial = keep
            self.window.show_mark()

    def _mark_trial(self, k: int, real: bool) -> None:
        """Trial k was marked a real startle (or not) in the playback window."""
        if self.startle is None or not 0 <= k < len(self.startle.rows):
            return
        self.startle.set_mark(k, real)
        self._save_review()
        self._after_review()

    def _finish_review(self) -> None:
        """Done reviewing: only once every trial with an amplitude is marked.
        Otherwise say which aren't, and go to the first."""
        st = self.startle
        if st is None:
            return
        win = self.window if self.window is not None and self.window.winfo_exists() else self
        left = st.unmarked()
        if left:
            numbers = ", ".join(str(st.rows[k]["Trial"]) for k in left[:30])
            more = f" and {len(left) - 30} more" if len(left) > 30 else ""
            one = len(left) == 1
            show_warning(win, "Not every startle is marked",
                         f"{len(left)} {'trial isn' if one else 'trials aren'}'t marked yet, "
                         "so the review isn't done.\n\n"
                         f"Not marked: trial{'' if one else 's'} {numbers}{more}.\n\n"
                         "Mark each one Yes or No (a trial with no response is a Yes), then "
                         "click Done reviewing again. The video is on the first of them.")
            if self.window is not None and self.window.winfo_exists():
                self.window.open_trial(left[0])
            return
        if not st.review.done:
            st.review.done = True
            self._save_review()
        self._after_review()

    def zone_changed(self, cm: float) -> None:
        """The zone distance changed (object recognition): work out the zone
        visits again (the logged interactions don't change)."""
        if self.scorer is None:
            return
        if cm != self.scorer.zone_cm and self.window is not None and self.window.winfo_exists():
            self.window.visit = None    # it was a visit of the old zones
        self.scorer.set_zone(cm)
        self._fill_events()
        if self.window is not None and self.window.winfo_exists():
            self.window._redraw()
            self.window._update_info()

    def edit_trial(self) -> None:
        """Open the dialog that changes the object types, day and phase."""
        if self.scorer is None:
            return
        if self.trial_dialog is not None and self.trial_dialog.winfo_exists():
            self.trial_dialog.lift()
            return
        day, phase = trial_info(self._data)
        self.trial_dialog = TrialInfoDialog(self.winfo_toplevel(), self.scorer.objects, day,
                                            phase, self._save_trial)

    def _save_trial(self, kinds: dict, day: str, phase: str) -> bool:
        """Save the edited trial info, then update everything that shows it."""
        try:
            update_trial_info(self._data, kinds, day, phase)
        except (OSError, ValueError) as exc:
            show_warning(self, "The trial info couldn't be saved",
                         "The trial info couldn't be saved, so nothing was changed. If "
                         f"the tracking file is open in another program, close it and "
                         f"try again.\n\n{exc}")
            return False
        self.scorer.objects = file_objects(self._data)
        self._fill_events()
        if self.window is not None and self.window.winfo_exists():
            self.window._redraw()
        self.on_trial_info(self._data, kinds, day, phase)
        return True

    def _scored(self) -> None:
        """The scoring changed: update the list, then the results."""
        self._fill_events()
        self.on_scored(self._data)

    def _set_mode(self) -> None:
        """Outside-region points (EPM, Open Field) or zone visits to score
        (Object Recognition): the columns, heading and cutoff box."""
        objects = self.scorer is not None
        startle = self.startle is not None
        cols = TRIAL_COLUMNS if startle else VISIT_COLUMNS if objects else EVENT_COLUMNS
        self.tree.configure(columns=[c for c, _ in cols])
        for col, width in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=width, minwidth=width, anchor=tk.CENTER,
                             stretch=col in ("Check", "Scored", "Note"))
        self.heading.configure(text="Startles" if startle else
                               "Zone visits to score" if objects else "Points to review")
        if objects:
            self.trial_btn.pack(side=tk.LEFT, padx=(6, 0))
        else:
            self.trial_btn.pack_forget()
        for w in (self.cutoff_entry, self.cutoff_label):
            if objects or startle:
                w.pack_forget()
        if not objects and not startle and not self.cutoff_entry.winfo_manager():
            self.cutoff_entry.pack(side=tk.RIGHT)
            self.cutoff_label.pack(side=tk.RIGHT, padx=(0, 4))

    def unload(self) -> None:
        if self.window is not None and self.window.winfo_exists():
            self.window.close()
        self.window = None
        if self.trial_dialog is not None and self.trial_dialog.winfo_exists():
            self.trial_dialog.destroy()
        self.trial_dialog = None
        self.pb = self._data = None
        self._made_with = None
        self.scorer = None
        self.startle = None
        self.events = []

    def _cutoff(self) -> float:
        """The cutoff in the box; what it was last if the box isn't a number
        above 0."""
        try:
            v = float(self.cutoff_var.get().replace(",", "."))
            return v if v > 0 else self._cutoff_value
        except ValueError:
            return self._cutoff_value

    def _apply_cutoff(self) -> None:
        value = self._cutoff()
        self.cutoff_var.set(f"{value:g}")
        if value == self._cutoff_value:
            return      # unchanged (e.g. the box only lost the focus): leave the list alone
        self._cutoff_value = value
        self.on_cutoff(value)
        self._fill_events()

    def _fill_trials(self) -> None:
        pb, st = self.pb, self.startle
        shown = lambda v, f="{:g}": "" if _blank(v) else f.format(v)
        used = 0
        for k, t in enumerate(st.rows):
            amplitude = t.get("Startle amplitude_pct")
            used += not _blank(amplitude)
            row = st.stimulus_row(k)
            frame = int(t["Stimulus_Frame"])
            when = "" if _blank(t.get("Stimulus_s")) else clock(float(t["Stimulus_s"]))
            note = t.get("Note") if isinstance(t.get("Note"), str) else ""
            self.tree.insert("", tk.END, iid=str(k), tags=("flag",) if _blank(amplitude) else (),
                             values=(t["Trial"], t["Type"], shown(t.get("Pulse_kHz")), f"{frame:,}",
                                     when, shown(t.get("motion.index.before_pct")),
                                     shown(t.get("motion.index.after_pct")), shown(amplitude),
                                     "" if _blank(t.get("FrameNo")) else f"{int(t['FrameNo']):,}",
                                     shown(t.get("ReactionTime_ms")),
                                     MARK_TEXT[st.mark(k)] if st.needs_mark(k) else "",
                                     note if row is not None else note or "outside the video"))
        if not st.rows:
            self.summary.configure(text="This file has no stimuli listed, so there are no "
                                        "startles to show.")
            return
        left = len(st.unmarked())
        state = ("Review done." if st.review.done and not left else
                 "All marked: click Done reviewing in the playback window." if not left else
                 "Review not done yet.")
        self.summary.configure(text=(
            f"{len(st.rows)} trials, {used} with an amplitude. Click a row to open the video "
            "at that stimulus; in the playback window, Previous and Next trial move "
            "between them. Rows in red have no amplitude; the Note says why. "
            "Mark each trial there as a real startle or not (How to review… explains): "
            f"{st.progress()}. {state}"))
        if self.window is not None and self.window.winfo_exists() and self.window.trial is not None:
            self._select_visit(self.window.trial)

    def _fill_visits(self) -> None:
        pb, sc = self.pb, self.scorer
        counts = {"scored": 0, "none": 0, "": 0}
        for n, v in enumerate(sc.visits):
            status = sc.scoring.visit_status(v)
            counts[status] += 1
            vf = pb.video_frame(v["row"])
            self.tree.insert("", tk.END, iid=str(n), tags=("flag",) if not status else (),
                             values=(n + 1, v["object"], f"{v['row'] + 1:,}",
                                     clock(v["row"] / pb.fps), clock(vf / pb.fps),
                                     f"{v['seconds']:g}", STATUS_TEXT[status]))
        win = self.window if self.window is not None and self.window.winfo_exists() else None
        if win is not None and win.visit is not None:
            k = next((i for i, x in enumerate(sc.visits) if x is win.visit), None)
            if k is not None:
                self._select_visit(k)
        zone = f"{sc.zone_cm:g} {'cm' if sc.scaled else 'px (this file has no scale)'}"
        totals = "; ".join(f"{name} {t:g} s ({k} interaction{'s' if k != 1 else ''})"
                           for name, (t, k) in sc.totals().items())
        if not sc.visits:
            text = f"The tracked point never came within {zone} of an object."
        else:
            text = (f"{len(sc.visits)} zone visits within {zone} of an object: "
                    f"{counts['scored']} with an interaction, {counts['none']} with none, "
                    f"{counts['']} to review (red). Click a row to open the video at the "
                    "frame the point enters the zone.")
        day, phase = trial_info(self._data)
        kinds = ", ".join(f"{o.name} {o.kind.lower()}" for o in sc.objects)
        trial = f"Trial day {day or 'not set'}, phase {phase or 'not set'}: {kinds}."
        self.summary.configure(text=f"{trial}\n{text}\nLogged so far: {totals}. Saved to "
                                    f"{os.path.basename(scoring_path(self._data))}.")

    def _fill_events(self) -> None:
        self.tree.delete(*self.tree.get_children())
        if self.pb is None:
            return
        if self.startle is not None:
            self._fill_trials()
            return
        if self.scorer is not None:
            self._fill_visits()
            return
        pb, cutoff = self.pb, self._cutoff()
        flagged = 0
        for n, e in enumerate(self.events):
            long = e["seconds"] >= cutoff
            flagged += long
            vf = pb.video_frame(e["row"])
            self.tree.insert("", tk.END, iid=str(n), tags=("flag",) if long else (), values=(
                n + 1, f"{e['row'] + 1:,}", clock(e["row"] / pb.fps), f"{vf:,}",
                clock(vf / pb.fps), f"{e['seconds']:g}", e["region"] or "none",
                f"{e['px_outside']:g}", "⚠ check" if long else "brief"))
        total = sum(e["seconds"] for e in self.events)
        if not self.events:
            self.summary.configure(text="The tracked point never left the drawn regions.")
        else:
            longest = max(e["seconds"] for e in self.events)
            self.summary.configure(text=(
                f"Outside the drawn regions {len(self.events)} times, {total:.2f} s in all "
                f"(average {total / len(self.events):.3f} s, longest {longest:g} s). "
                f"{flagged} at or over {cutoff:g} s. Each counts for the region shown; "
                "click a row to see it."))

    def _select_visit(self, index: int) -> None:
        """The playback window moved to another visit: select it in the list
        (without reopening it)."""
        if self.tree.exists(str(index)):
            self.tree.selection_set(str(index))
            self.tree.see(str(index))

    def _on_event(self, _e=None) -> None:
        sel = self.tree.selection()
        if sel and self.pb is not None and self.startle is not None:
            current = self.window if self.window is not None and self.window.winfo_exists() else None
            if current is None or current.trial != int(sel[0]):
                win = self.open_window()
                if win is not None:
                    win.open_trial(int(sel[0]))
            return
        win = self.window if self.window is not None and self.window.winfo_exists() else None
        if (sel and win is not None and self.scorer is not None
                and win.visit is self.scorer.visits[int(sel[0])]):
            return   # already showing it (the window moved there itself)
        if sel and self.pb is not None and self.scorer is not None:
            win = self.open_window()
            if win is not None:
                win.open_visit(self.scorer.visits[int(sel[0])])
        elif sel and self.pb is not None:
            self.open_window(self.events[int(sel[0])]["row"])

