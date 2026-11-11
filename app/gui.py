"""
Track Tamer — GUI front end.

A tkinter desktop app over the `core` analysis engine. Files (added one at a
time, by folder, or by drag-and-drop) build up the file list, which stays
visible above the tabs. Analyze and Export act on the selected files (Select
all selects every one); the focused file drives the Time Bins, Path, and
Heatmap tabs. Nothing is computed until Analyze.

The settings in the left-hand panel can be changed after adding files, and
lock at the first Analyze, so every file in a load is analyzed the same way.
Clear empties the list and unlocks them. Plot styling (Path/Heatmap tabs) is
never locked. The list itself is not saved between sessions.

Run:  python gui.py     (or use the "Open Track Tamer.command" launcher)
"""

from __future__ import annotations

import os
import traceback
from datetime import datetime
import tkinter as tk
from dataclasses import dataclass
from tkinter import colorchooser, filedialog, ttk

# Drag-and-drop is optional: without tkinterdnd2 (or if its Tcl library won't
# load) the app still works through the Open File / Open Folder buttons.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DnDMixin = TkinterDnD.DnDWrapper
except ImportError:
    TkinterDnD = None
    _DnDMixin = object

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # figures are built off-screen, then embedded
# Plots saved from the toolbar keep a transparent background, so empty heatmap
# cells (and the area around each plot) can be recolored in an image editor.
matplotlib.rcParams["savefig.transparent"] = True
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,
    NavigationToolbar2Tk,
)

from core import (
    TrackingData,
    load_csv,
    summary_metrics,
    binned_metrics,
    epm_metrics,
    of_metrics,
    epm_binned,
    of_binned,
    path_figure,
    heatmap_figure,
    load_config,
    save_config,
    summary_column_groups,
    order_summary,
    order_bins,
    drop_duplicates,
    outside_events,
    ROLE_LABELS,
    TEST_TYPES,
    auto_role,
    center_periphery_overlap,
    check_roles,
    describe_roles,
    resolve_roles,
)
from core.export import output_paths, save_figure, settings_table, write_analysis_workbook
from core.gaps import fill_gaps
from core.video import (MISSING_STAMPS_ALLOWED, VIDEO_EXTENSIONS, UNREADABLE_WARN, check_readable, is_video,
                        video_info)
from core.version import VERSION
from core.video_setup import OBJECT_TEST, VideoSetup
from core.asr import (ASR_TEST, asr_summary, is_motion_file, load_motion, make_asr_job,
                      real_frame_rate, trial_table)
from core.plotting import aligned_figure, motion_figure
from core.objects import (distance_px, load_scoring, object_metrics, scoring_table,
                          trial_summary)
from core.metrics import _bin_ranges as bin_ranges
from core.tracking import TrackingParams
from core.track_run import TrackRunner, existing_output, make_job
from core.playback import load_reference
from about import AboutDialog
from region_dialog import RegionDialog
from setup_window import SetupWindow, use_default_length
from review_panel import ReviewPanel
from dialogs import ask_choice, ask_yes_no, show_error, show_info, show_warning
from tooltip import Tooltip

HEATMAP_CMAPS = ["inferno", "viridis", "magma", "plasma", "hot", "jet", "gray"]
PATH_BACKGROUNDS = {"none": "None", "reference": "Reference image"}
HEATMAP_BACKGROUNDS = {"none": "None", "color": "Flat color", "reference": "Reference image"}
NO_REFERENCE_TIP = ("Reference image: the empty arena behind the plot. Only files "
                    "tracked in this app have one (<name>_reference.png beside the "
                    "tracking file); for others the plot has no background.")

# Summary-table column groups, in checkbox order (keys match summary_column_groups).
SUMMARY_GROUP_LABELS = {
    "key": "Key measures",
    "basics": "Session basics",
    "test": "More test measures",
    "zones": "Zone time & %",
    "entries": "Entries & transitions",
    "details": "Details",
}

NOT_ANALYZED = "Not analyzed"
ANALYZED = "Analyzed"
# Status text color in the file list (readable on light and dark themes).
STATUS_COLORS = {"analyzed": "#2e7d32", "waiting": "#b26a00", "failed": "#c62828"}

NEEDS_SETUP = "Needs setup"
READY_TO_TRACK = "Ready to track"
WAITING_TO_TRACK = "Waiting to track"
FAILED = "Failed"

LOCKED_TRACKING_TIP = (
    "Locked because videos have been tracked, so every video in this load is "
    "tracked the same way. Click Clear to change it."
)

LOCKED_TIP = (
    "Locked because files have been analyzed, so every file in this load uses "
    "the same settings. Click Clear to change it."
)


ZONE_WAIT_MS = 500   # the Zone distance box applies this long after the last keystroke


class ScrollPanel(ttk.Frame):
    """A column whose contents (`inner`) scroll vertically when the window is
    too short for them. The mouse wheel scrolls it while the pointer is over
    it; the scrollbar shows only when needed."""

    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0,
                                background=parent.winfo_toplevel().cget("background"))
        self.bar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.grid(row=0, column=0, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.inner = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self._fit())
        self.canvas.bind("<Configure>", lambda _e: self._fit())
        self.bind("<Enter>", lambda _e: self._wheel_on(True))
        self.bind("<Leave>", lambda _e: self._wheel_on(self._pointer_inside()))

    def _fit(self) -> None:
        self.canvas.configure(width=self.inner.winfo_reqwidth(),
                              scrollregion=(0, 0, self.inner.winfo_reqwidth(),
                                            self.inner.winfo_reqheight()))
        needed = self.inner.winfo_reqheight() > self.canvas.winfo_height() > 1
        if needed and not self.bar.winfo_manager():
            self.bar.grid(row=0, column=1, sticky="ns")
        elif not needed and self.bar.winfo_manager():
            self.bar.grid_forget()
            self.canvas.yview_moveto(0)

    def _pointer_inside(self) -> bool:
        """True if the pointer is over this panel or anything in it (a Leave
        also fires when the pointer moves onto a child widget)."""
        w = self.winfo_containing(*self.winfo_pointerxy())
        while w is not None:
            if w is self:
                return True
            w = w.master
        return False

    def _wheel_on(self, on: bool) -> None:
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            if on:
                self.bind_all(seq, self._wheel)
            else:
                self.unbind_all(seq)

    def guard_wheel(self) -> None:
        """Stop the mouse wheel changing a dropdown's or number box's value
        when the pointer passes over it while scrolling the panel (it would
        change the test type without a click). The wheel scrolls the panel
        there instead. Call once the panel's widgets are built."""
        def over(widget):
            for child in widget.winfo_children():
                if isinstance(child, (ttk.Combobox, ttk.Spinbox, tk.Spinbox)):
                    for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                        child.bind(seq, lambda e: (self._wheel(e), "break")[1])
                over(child)
        over(self.inner)

    def _wheel(self, e) -> None:
        if not self.bar.winfo_manager():
            return
        if getattr(e, "num", None) in (4, 5):        # Linux
            step = -1 if e.num == 4 else 1
        elif self.tk.call("tk", "windowingsystem") == "aqua":
            step = -e.delta                           # Mac: small deltas
        else:
            step = -int(e.delta / 120) or (-1 if e.delta > 0 else 1)  # Windows
        self.canvas.yview_scroll(step, "units")


def _shown(value):
    """A table cell as shown: blank for a missing value, and a whole number
    without ".0" (a column of counts turns into decimals as soon as one file
    in the list has no value for it)."""
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():   # (numpy's float64 is a float)
        return int(value)
    return value


@dataclass(eq=False)   # entries are told apart by identity (one file can be listed twice)
class FileEntry:
    """One file in the list. `summary`/`bins` are filled in by Analyze.

    A video has `video` (its setup) and no `data` until it's tracked; a CSV
    has `data` from the start."""

    path: str
    data: TrackingData | None
    label: str                      # name shown in the Summary ("x (2)" for repeats)
    summary: dict | None = None
    bins: pd.DataFrame | None = None
    video: VideoSetup | None = None
    # While Track runs: "queued", "reference" or "tracking" (with track_pct);
    # "failed" (with track_error) after a failed run. "" otherwise.
    track_state: str = ""
    track_pct: int = 0
    track_error: str = ""

    @property
    def analyzed(self) -> bool:
        return self.summary is not None

    @property
    def kind(self) -> str:
        return "Video" if self.video is not None else "CSV"


class TrackTamerApp(tk.Tk, _DnDMixin):
    LOCKED_TRACKING_TIP = LOCKED_TRACKING_TIP

    def __init__(self):
        super().__init__()
        self.title("Track Tamer")
        self.geometry("1080x720")
        self.minsize(900, 600)

        self.config_data = load_config()
        p = self.config_data["plot"]
        if p["heatmap_bg_mode"] not in HEATMAP_BACKGROUNDS:
            p["heatmap_bg_mode"] = "none"
        if p["heatmap_bg_mode"] == "none" and p["heatmap_background"]:
            p["heatmap_bg_mode"] = "color"  # from before the background choice
        if p["path_background"] not in PATH_BACKGROUNDS:
            p["path_background"] = "none"
        self._references: dict[str, object] = {}    # tracking file -> reference image

        # The file list (not saved: it resets when the app closes).
        self.files: list[FileEntry] = []
        self._selected: int | None = None           # file the tabs show (index)
        self._sel: list[int] = []                   # selected files (indices)
        self._summary_df = None                     # last Summary table (for export)
        self._redraw_job = None                     # pending debounced plot redraw
        self._runner: TrackRunner | None = None     # tracking in progress

        self._build_controls()
        self._build_tabs()
        self._show_test_settings()
        self._enable_drop()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if self.tk.call("tk", "windowingsystem") == "aqua":
            # Mac: Cmd+Q and the app menu's Quit go through the same checks
            # and saving as closing the window (otherwise they just exit).
            self.createcommand("::tk::mac::Quit", self._on_close)
        # Settings are editable until Analyze, so keep the status bar current.
        for var in (self.fps_var, self.bin_var, self.entry_var, self.gap_var, self.adj_var,
                    self.smooth_var):
            var.trace_add("write", lambda *_: self._update_status())
        self._refresh()

    # ------------------------------------------------------------------ UI
    def _build_controls(self):
        """Layout (GUI review, option C): a left panel with the file and run
        buttons above the settings (it scrolls when it doesn't fit), and the
        file list over the tabs on the right. Each plot tab has its own
        controls in a column beside the plot."""
        self.status = tk.StringVar()
        status_bar = ttk.Label(
            self, textvariable=self.status, relief=tk.SUNKEN, anchor=tk.W, padding=4
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Tracking progress, above the status bar while Track runs.
        self.track_bar = ttk.Frame(self, padding=(8, 4))
        self.track_text = ttk.Label(self.track_bar, anchor=tk.W)
        self.track_text.pack(side=tk.LEFT)
        self.track_cancel_btn = ttk.Button(self.track_bar, text="Cancel",
                                           command=self.cancel_tracking)
        self.track_cancel_btn.pack(side=tk.RIGHT)
        Tooltip(self.track_cancel_btn, "Stop tracking. Videos already finished are "
                                       "kept; the one being tracked and the rest are "
                                       "left untracked.")
        self.track_progress = ttk.Progressbar(self.track_bar, mode="determinate",
                                              maximum=100)
        self.track_progress.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=8)

        # Export progress, in the same place while Export runs (user,
        # 2026-11-11): the window stays usable and Cancel stops after the
        # file being written.
        self._exporting = False
        self._export_cancel = False
        self._close_after_export = False
        self.export_bar = ttk.Frame(self, padding=(8, 4))
        self.export_text = ttk.Label(self.export_bar, anchor=tk.W)
        self.export_text.pack(side=tk.LEFT)
        self.export_cancel_btn = ttk.Button(self.export_bar, text="Cancel",
                                            command=self.cancel_export)
        self.export_cancel_btn.pack(side=tk.RIGHT)
        Tooltip(self.export_cancel_btn, "Stop exporting after the file being written. "
                                        "Files already exported are kept.")
        self.export_progress = ttk.Progressbar(self.export_bar, mode="determinate",
                                               maximum=100)
        self.export_progress.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=8)

        # Body: the left panel; the file list over the tabs on the right.
        body = self.body = ttk.Frame(self)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        scroller = ScrollPanel(body)
        scroller.grid(row=0, column=0, sticky="ns", pady=(8, 8))
        self.settings_panel = scroller.inner
        self.settings_panel.configure(padding=(8, 0, 6, 0))
        self._build_actions(self.settings_panel)
        self._build_settings_panel(self.settings_panel)
        scroller.guard_wheel()
        self.content = ttk.PanedWindow(body, orient=tk.VERTICAL)
        self.content.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)
        self._build_file_list(self.content)

    def _build_actions(self, panel) -> None:
        """The Files and Run buttons at the top of the left panel, full width,
        in working order. About sits at the bottom of the panel."""
        files = ttk.LabelFrame(panel, text="Files", padding=6)
        files.pack(side=tk.TOP, fill=tk.X, pady=(0, 8))
        add_file = ttk.Button(files, text="Add files…", command=self.open_file)
        add_file.pack(fill=tk.X)
        Tooltip(add_file, "Add tracking CSVs or videos to the list. You can also "
                          "drag files or folders onto the window.")
        add_folder = ttk.Button(files, text="Add folder…", command=self.open_folder)
        add_folder.pack(fill=tk.X, pady=(4, 0))
        Tooltip(add_folder, "Add every CSV and video in a folder to the list.")
        pair = ttk.Frame(files)
        pair.pack(fill=tk.X, pady=(4, 0))
        pair.columnconfigure((0, 1), weight=1, uniform="pair")
        remove = self.remove_btn = ttk.Button(pair, text="Remove", width=7,
                                              command=self.remove_selected)
        remove.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        Tooltip(remove, "Take the selected files out of the list. The files "
                        "themselves aren't touched.")
        self.clear_btn = ttk.Button(pair, text="Clear", width=7, command=self.clear_files)
        self.clear_btn.grid(row=0, column=1, sticky="ew", padx=(2, 0))
        Tooltip(self.clear_btn, "Clears the file list and unlocks the settings so you "
                                "can choose them again (e.g. after analyzing one file, "
                                "before running a folder).")

        run = self.run_section = ttk.LabelFrame(panel, text="Run", padding=6)
        run.pack(side=tk.TOP, fill=tk.X, pady=(0, 8))
        # Set up videos… and Track show only while videos are in the list.
        self.setup_btn = ttk.Button(run, text="Set up videos…", command=self.open_setup)
        Tooltip(self.setup_btn, "Trim, crop, and prepare each video for tracking, one "
                                "at a time.")
        self.select_all_btn = ttk.Button(run, text="Select all", command=self.toggle_select_all)
        self.select_all_btn.pack(fill=tk.X)
        Tooltip(self.select_all_btn, "Select every file in the list, so Track, Analyze "
                                     "and Export act on all of them. Ctrl+A (Cmd+A on a "
                                     "Mac) in the list does the same.")
        self.track_btn = ttk.Button(run, text="Track", command=self.track)
        Tooltip(self.track_btn, "Track the selected videos, one at a time in the "
                                "background. Each gets <name>_LocationOutput.csv and "
                                "<name>_reference.png next to it. The number shows how "
                                "many videos are selected.")
        self.analyze_btn = ttk.Button(run, text="Analyze", command=self.analyze)
        self.analyze_btn.pack(fill=tk.X, pady=(4, 0))
        Tooltip(self.analyze_btn, "Analyze the selected files. The number shows how "
                                  "many are selected.")
        self.export_btn = ttk.Button(run, text="Export", command=self.export)
        self.export_btn.pack(fill=tk.X, pady=(4, 0))
        Tooltip(self.export_btn, "Export the selected files that have been analyzed. "
                                 "Each gets <name>_analysis.xlsx, <name>_path.png, and "
                                 "<name>_heatmap.png next to its CSV (existing files "
                                 "are overwritten).")
        about = ttk.Button(panel, text="About", command=self.show_about)
        about.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 4))
        Tooltip(about, "Credits, citation, and license.")


    def _setting_row(self, section, row: int, label: str, widget) -> None:
        ttk.Label(section, text=label, wraplength=130, justify=tk.LEFT).grid(
            row=row, column=0, sticky="w", pady=2)
        widget.grid(row=row, column=1, sticky="e", padx=(8, 0), pady=2)
        section.columnconfigure(0, weight=1)

    def _build_settings_panel(self, panel) -> None:
        """Settings in sections. The analysis settings lock at the first Analyze
        of a load (so every file is analyzed the same way) and unlock at Clear."""
        self.lock_note = ttk.Label(panel, text="Locked. Clear to change.",
                                   foreground="gray")

        # Session.
        self.session_section = ttk.LabelFrame(panel, text="Session", padding=6)
        if self.config_data["test_type"] not in TEST_TYPES:  # hand-edited config
            self.config_data["test_type"] = TEST_TYPES[0]
        self.test_var = tk.StringVar(value=self.config_data["test_type"])
        self.test_box = ttk.Combobox(
            self.session_section, textvariable=self.test_var, values=TEST_TYPES,
            state="readonly", width=17,
        )
        self.test_box.bind("<<ComboboxSelected>>", lambda _e: self._on_test_type())
        self._setting_row(self.session_section, 0, "Test", self.test_box)
        self.fps_var = tk.StringVar(value=f"{self.config_data['fps']:g}")
        self.fps_entry = ttk.Entry(self.session_section, textvariable=self.fps_var, width=6)
        self._setting_row(self.session_section, 1, "Frame rate (fps)", self.fps_entry)
        self.bin_var = tk.StringVar(value=f"{self.config_data['bin_seconds']:g}")
        self.bin_entry = ttk.Entry(self.session_section, textvariable=self.bin_var, width=6)
        self._setting_row(self.session_section, 2, "Bin size (s)", self.bin_entry)

        # Entries and regions.
        self.entries_section = ttk.LabelFrame(panel, text="Entries and regions", padding=6)
        self.entry_var = tk.StringVar(value=str(self.config_data["min_entry_frames"]))
        self.entry_entry = ttk.Entry(self.entries_section, textvariable=self.entry_var, width=6)
        self._setting_row(self.entries_section, 0, "Min entry (frames)", self.entry_entry)
        regions_btn = ttk.Button(self.entries_section, text="Regions…",
                                 command=self.open_region_dialog)
        regions_btn.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        Tooltip(regions_btn, "Choose what each region in the files represents "
                             "(open arm, center, ...). Saved for next time.")

        # Open Field thresholds, shown only when the test is Open Field.
        self.of_bar = ttk.LabelFrame(panel, text="Open Field", padding=6)
        self.gap_var = tk.StringVar(value=f"{self.config_data['min_seconds_between_entries']:g}")
        self.gap_entry = ttk.Entry(self.of_bar, textvariable=self.gap_var, width=6)
        self._setting_row(self.of_bar, 0, "Min gap between center entries (s)", self.gap_entry)
        self.adj_var = tk.StringVar(value=f"{self.config_data['min_center_seconds_adjoining']:g}")
        self.adj_entry = ttk.Entry(self.of_bar, textvariable=self.adj_var, width=6)
        self._setting_row(self.of_bar, 1, "Min center time, adjoining (s)", self.adj_entry)
        self.smooth_var = tk.StringVar(value=str(self.config_data["speed_smoothing_frames"]))
        self.smooth_entry = ttk.Entry(self.of_bar, textvariable=self.smooth_var, width=6)
        self._setting_row(self.of_bar, 2, "Speed smoothing (frames)", self.smooth_entry)

        # Object Recognition (ROADMAP §15), shown only for that test. The zone
        # distance is being settled by experimenting, so it never locks: zones
        # are worked out from X/Y whenever results or the Review list update.
        self.or_bar = ttk.LabelFrame(panel, text="Object Recognition", padding=6)
        self.zone_var = tk.StringVar(value=f"{self.config_data['object_zone_cm']:g}")
        self.zone_entry = ttk.Entry(self.or_bar, textvariable=self.zone_var, width=6)
        self._setting_row(self.or_bar, 0, "Zone distance (cm)", self.zone_entry)
        Tooltip(self.zone_entry, "How far from each object's edge its zone reaches. Time "
                                 "with the tracked point in a zone is listed in the "
                                 "Review tab to score. Never locks: change it any time "
                                 "and the Review list and results follow.")
        # The zone distance takes effect once typing stops (user, 2026-11-11):
        # every analyzed file is worked out again, so not on each keystroke.
        self._zone_job = None
        self.zone_var.trace_add("write", lambda *_: self._zone_typed())
        for seq in ("<Return>", "<FocusOut>"):
            self.zone_entry.bind(seq, lambda _e: self._flush_zone_change())

        # Acoustic startle (ROADMAP §13), shown only for that test.
        self.asr_bar = ttk.LabelFrame(panel, text="Acoustic Startle", padding=6)
        c = self.config_data
        self.asr_threshold_var = tk.StringVar(value=f"{c['asr_threshold']:g}")
        self.asr_threshold_entry = ttk.Entry(self.asr_bar, textvariable=self.asr_threshold_var,
                                             width=6)
        self._setting_row(self.asr_bar, 0, "Intensity threshold (0-255)", self.asr_threshold_entry)
        self.asr_startle_var = tk.StringVar(value=f"{c['asr_startle_ms']:g}")
        self.asr_startle_entry = ttk.Entry(self.asr_bar, textvariable=self.asr_startle_var, width=6)
        self._setting_row(self.asr_bar, 1, "Startle window (ms)", self.asr_startle_entry)
        self.asr_baseline_var = tk.StringVar(value=f"{c['asr_baseline_ms']:g}")
        self.asr_baseline_entry = ttk.Entry(self.asr_bar, textvariable=self.asr_baseline_var,
                                            width=6)
        self._setting_row(self.asr_bar, 2, "Baseline window (ms)", self.asr_baseline_entry)
        self.asr_block_var = tk.StringVar(value=str(c["asr_block_trials"]))
        self.asr_block_entry = ttk.Entry(self.asr_bar, textvariable=self.asr_block_var, width=6)
        self._setting_row(self.asr_bar, 3, "Habituation block (trials)", self.asr_block_entry)
        Tooltip(self.asr_threshold_entry, "A pixel counts as movement when its brightness changes "
                "by more than this between frames. See its effect in Set up videos…, step 3. "
                "Locks at the first Track.")
        Tooltip(self.asr_startle_entry, "How long after each stimulus to look for the startle. "
                "Locks when you click Analyze.")
        Tooltip(self.asr_baseline_entry, "How long before each stimulus to measure movement "
                "(before the prepulse, on prepulse+pulse trials). Locks when you click Analyze.")
        Tooltip(self.asr_block_entry, "Pulse-alone trials per block, for habituation (first "
                "block vs last). Locks when you click Analyze.")
        self.asr_threshold_var.trace_add("write", lambda *_: self._on_asr_threshold())

        # Tracking settings, shown when videos are listed. They're changed in
        # the setup window's Tracking check step, where their effect shows.
        self.tracking_section = ttk.LabelFrame(panel, text="Tracking", padding=6)
        self.tracking_text = ttk.Label(self.tracking_section, justify=tk.LEFT,
                                       wraplength=210)
        self.tracking_text.grid(row=0, column=0, sticky="w")
        Tooltip(self.tracking_section, lambda: LOCKED_TRACKING_TIP if self._tracking_locked()
                else "Shared by every video. Change them in Set up videos…, step 4 "
                     "(Tracking check). They lock at the first Track.")

        # Unreadable video frames, shown only when a listed file has them marked.
        self.gaps_section = ttk.LabelFrame(panel, text="Unreadable video frames", padding=6)
        self.fill_var = tk.BooleanVar(value=self.config_data["fill_gaps"])
        self.fill_check = ttk.Checkbutton(self.gaps_section, text="Fill short gaps",
                                          variable=self.fill_var)
        self.fill_check.grid(row=0, column=0, columnspan=2, sticky="w")
        self.fill_max_var = tk.StringVar(value=str(self.config_data["fill_gaps_max_frames"]))
        self.fill_max_entry = ttk.Entry(self.gaps_section, textvariable=self.fill_max_var,
                                        width=6)
        self._setting_row(self.gaps_section, 1, "Up to (frames)", self.fill_max_entry)

        for widget, unlocked in (
            (self.test_box, "Which test these files are. Locks when you click Analyze."),
            (self.fps_entry, "Video frame rate. Locks when you click Analyze."),
            (self.bin_entry, "Time-bin length in seconds. Locks when you click Analyze."),
            (self.entry_entry, "Entry rule: the animal must stay in a region at least "
                               "this many frames for it to count as an entry (filters "
                               "boundary jitter). Locks when you click Analyze."),
            (self.gap_entry, "Returning to the center sooner than this after leaving "
                             "it counts as the same visit, not a new entry. Locks "
                             "when you click Analyze."),
            (self.adj_entry, "A crossing between adjoining sides (e.g. left to top) "
                             "only counts if the animal spent at least this long in "
                             "the center on the way. Opposite-side crossings always "
                             "count. Locks when you click Analyze."),
            (self.smooth_entry, "Crossing speeds use speed averaged over this many "
                                "frames, so a one-frame tracking jump can't set the "
                                "peak. 1 = no smoothing. Locks when you click Analyze."),
            (self.fill_check, "Video frames that couldn't be read have no position. "
                              "Off: they're left out (no time, distance, or entries). "
                              "On: short gaps get positions on a straight line between "
                              "the frames before and after. The saved tracking file is "
                              "never changed. Locks when you click Analyze."),
            (self.fill_max_entry, "Longest gap, in frames, that gets filled. Longer "
                                  "gaps stay blank. Locks when you click Analyze."),
        ):
            Tooltip(widget, lambda u=unlocked: LOCKED_TIP if self._locked() else u)
        self._layout_sections()

    def _layout_sections(self) -> None:
        """Show the settings sections that apply, in a fixed order."""
        sections = [
            (self.lock_note, self._locked()),
            (self.session_section, True),
            (self.entries_section, self.test_var.get() != ASR_TEST),
            (self.of_bar, self.test_var.get() == "Open Field"),
            (self.or_bar, self.test_var.get() == OBJECT_TEST),
            (self.asr_bar, self.test_var.get() == ASR_TEST),
            (self.tracking_section, self.test_var.get() != ASR_TEST and any(
                e.video is not None for e in getattr(self, "files", []))),
            (self.gaps_section, self.test_var.get() != ASR_TEST and any(e.video is not None or (
                e.data is not None and "Frame_Unreadable" in e.data.df.columns)
                for e in getattr(self, "files", []))),
        ]
        c = self.config_data
        self.tracking_text.configure(text=(
            f"Animal is {c['track_method']}, threshold {c['loc_thresh']:g}%\n"
            + (f"Window {c['window_size']} px, weight {c['window_weight']:g}\n"
               if c["use_window"] else "No window\n")
            + f"Downsample {c['video_downsample']:g}, reference {c['reference_frames']} frames\n"
            + ("Locked. Clear to change." if hasattr(self, "files") and self._tracking_locked() else
               "Change in Set up videos…, step 4.")))
        for widget, _ in sections:
            widget.pack_forget()
        for widget, show in sections:
            if show:
                widget.pack(side=tk.TOP, fill=tk.X, pady=(0, 8), anchor="n")

    def _build_file_list(self, parent) -> None:
        """The file list (always visible) above the tabs. Several files can be
        selected; the focused one drives the Time Bins, Path, and Heatmap tabs."""
        wrap = ttk.Frame(parent)
        parent.add(wrap, weight=1)
        self.file_tree = ttk.Treeview(wrap, columns=("File", "Type", "Status"),
                                      show="headings", selectmode="extended", height=6)
        for col, width, anchor in (("File", 360, tk.W), ("Type", 70, tk.CENTER),
                                   ("Status", 140, tk.CENTER)):
            self.file_tree.heading(col, text=col)
            self.file_tree.column(col, width=width, anchor=anchor,
                                  stretch=(col == "File"))
        for tag, color in STATUS_COLORS.items():
            self.file_tree.tag_configure(tag, foreground=color)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=vsb.set)
        self.file_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.file_tree.bind("<<TreeviewSelect>>", self._on_select)
        # Select all: Cmd+A on a Mac, Ctrl+A elsewhere. (<Command-a> must not be
        # bound on Windows: there it means Num Lock + A, so typing "a" with
        # Num Lock on would select every file.)
        mac = self.tk.call("tk", "windowingsystem") == "aqua"
        for seq in ("<Control-a>",) + (("<Command-a>",) if mac else ()):
            self.file_tree.bind(seq, lambda _e: (self.select_all(), "break")[1])

    CONTROL_WIDTH = 170  # the plot tabs' control column (wrap width for notes)

    def _plot_column(self, parent) -> ttk.Frame:
        """The control column on the right of a plot tab."""
        col = ttk.Frame(parent, padding=(8, 8, 4, 8))
        col.pack(side=tk.RIGHT, fill=tk.Y)
        col.columnconfigure(1, weight=1)
        return col

    @staticmethod
    def _col_row(col, row: int, label: str, widget) -> None:
        ttk.Label(col, text=label).grid(row=row, column=0, sticky="w", pady=2)
        widget.grid(row=row, column=1, sticky="e", padx=(6, 0), pady=2)

    @staticmethod
    def _col_heading(col, row: int, text: str) -> None:
        ttk.Label(col, text=text, foreground="gray").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(10 if row else 0, 2))

    def _color_pick_row(self, col, row: int, text: str, command, color: str):
        """A color button with a swatch (a plain tk.Label so its background
        can show the chosen color). Returns (button, swatch)."""
        frame = ttk.Frame(col)
        frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=2)
        btn = ttk.Button(frame, text=text, command=command)
        btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
        swatch = tk.Label(frame, width=2, background=color, relief=tk.SOLID, borderwidth=1)
        swatch.pack(side=tk.LEFT, padx=(4, 0))
        return btn, swatch

    def _labels_check(self, col, row: int, var) -> None:
        check = ttk.Checkbutton(col, text="Region labels", variable=var,
                                command=self._schedule_redraw)
        check.grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
        Tooltip(check, "Show each region's name on the plot (also in the exported "
                       "image).")

    def _build_path_controls(self, parent):
        """Path-tab controls, in a column beside the plot. Changes redraw it."""
        p = self.config_data["plot"]
        col = self.path_col = self._plot_column(parent)

        self._col_heading(col, 0, "Points")
        self.size_var = tk.StringVar(value=f"{p['point_size']:g}")
        self._col_row(col, 1, "Size", ttk.Spinbox(
            col, from_=0.5, to=50, increment=0.5, width=5, textvariable=self.size_var))
        self.alpha_var = tk.StringVar(value=f"{p['alpha']:g}")
        alpha = ttk.Spinbox(col, from_=0.05, to=1.0, increment=0.05, width=5,
                            textvariable=self.alpha_var)
        self._col_row(col, 2, "Transparency", alpha)
        Tooltip(alpha, "Alpha: 1 = solid, lower = see-through, so overlapping points "
                       "show where the animal spent more time.")
        self.speed_var = tk.BooleanVar(value=p["color_by_speed"])
        ttk.Checkbutton(col, text="Color by speed", variable=self.speed_var,
                        command=self._on_color_mode).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=2)
        self.point_color = p["point_color"]
        self.color_btn, self.color_swatch = self._color_pick_row(
            col, 4, "Point color…", self._pick_color, self.point_color)

        self._col_heading(col, 5, "Show")
        ttk.Label(col, text="Background").grid(row=6, column=0, columnspan=2, sticky="w")
        self.path_bg_var = tk.StringVar(value=PATH_BACKGROUNDS[p["path_background"]])
        box = ttk.Combobox(col, textvariable=self.path_bg_var, state="readonly", width=16,
                           values=list(PATH_BACKGROUNDS.values()))
        box.grid(row=7, column=0, columnspan=2, sticky="ew", pady=2)
        Tooltip(box, NO_REFERENCE_TIP)
        self.path_bg_note = ttk.Label(col, foreground="gray", wraplength=self.CONTROL_WIDTH)
        self.path_bg_note.grid(row=8, column=0, columnspan=2, sticky="w")
        self.path_labels_var = tk.BooleanVar(value=p["path_labels"])
        self._labels_check(col, 9, self.path_labels_var)

        for var in (self.size_var, self.alpha_var, self.path_bg_var):
            var.trace_add("write", lambda *_: self._schedule_redraw())
        self._on_color_mode(redraw=False)

    def _build_heatmap_controls(self, parent):
        """Heatmap-tab controls, in a column beside the plot. Changes redraw it."""
        p = self.config_data["plot"]
        col = self.heat_col = self._plot_column(parent)

        self._col_heading(col, 0, "Cells")
        self.hbins_var = tk.StringVar(value=str(p["heatmap_bins"]))
        bins = ttk.Spinbox(col, from_=5, to=300, increment=5, width=5,
                           textvariable=self.hbins_var)
        self._col_row(col, 1, "Bins", bins)
        Tooltip(bins, "Number of square cells along the longer side of the arena.")
        if p["heatmap_cmap"] not in HEATMAP_CMAPS:  # hand-edited config
            p["heatmap_cmap"] = HEATMAP_CMAPS[0]
        self.cmap_var = tk.StringVar(value=p["heatmap_cmap"])
        self._col_row(col, 2, "Colormap", ttk.Combobox(
            col, textvariable=self.cmap_var, values=HEATMAP_CMAPS, state="readonly",
            width=8))

        self._col_heading(col, 3, "Show")
        ttk.Label(col, text="Background").grid(row=4, column=0, columnspan=2, sticky="w")
        self.bg_var = tk.StringVar(value=HEATMAP_BACKGROUNDS[p["heatmap_bg_mode"]])
        bg_box = ttk.Combobox(col, textvariable=self.bg_var, state="readonly", width=16,
                              values=list(HEATMAP_BACKGROUNDS.values()))
        bg_box.grid(row=5, column=0, columnspan=2, sticky="ew", pady=2)
        bg_box.bind("<<ComboboxSelected>>", lambda _e: self._on_background())
        Tooltip(bg_box, "What shows in cells the animal never entered. None: empty "
                        "(transparent in a saved PNG). Flat color: one color, easy to "
                        "recolor in an image editor. " + NO_REFERENCE_TIP)
        self.bg_color = p["heatmap_bg_color"]
        self.bg_btn, self.bg_swatch = self._color_pick_row(
            col, 6, "Background color…", self._pick_bg_color, self.bg_color)
        self.heat_bg_note = ttk.Label(col, foreground="gray", wraplength=self.CONTROL_WIDTH)
        self.heat_bg_note.grid(row=7, column=0, columnspan=2, sticky="w")
        self.heat_labels_var = tk.BooleanVar(value=p["heatmap_labels"])
        self._labels_check(col, 8, self.heat_labels_var)

        for var in (self.hbins_var, self.cmap_var):
            var.trace_add("write", lambda *_: self._schedule_redraw())
        self._on_background(redraw=False)

    def _build_summary_controls(self, parent):
        """Checkboxes choosing which column groups the Summary table shows."""
        groups = self.config_data["summary_columns"]
        bar = ttk.Frame(parent, padding=(4, 6))
        bar.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(bar, text="Show:").grid(row=0, column=0, sticky="nw", padx=(0, 6))
        self.group_vars = {}
        # Two rows of four, so the checkboxes fit a narrow window.
        for n, (key, label) in enumerate(SUMMARY_GROUP_LABELS.items()):
            var = tk.BooleanVar(value=groups.get(key, False))
            ttk.Checkbutton(
                bar, text=label, variable=var, command=self._show_summary
            ).grid(row=n // 4, column=1 + n % 4, sticky="w", padx=(0, 10))
            self.group_vars[key] = var
        ttk.Label(
            bar, text="(Export includes all columns)", foreground="gray"
        ).grid(row=1, column=4, sticky="w")

    def _enable_drop(self) -> None:
        """Register the window as a drop target for files and folders."""
        if TkinterDnD is None:
            return
        try:
            TkinterDnD._require(self)
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
        except (RuntimeError, tk.TclError):
            traceback.print_exc()  # fall back to the Open buttons only

    def _build_tabs(self):
        self.nb = ttk.Notebook(self.content)
        self.content.add(self.nb, weight=3)

        # Summary tab (column-group checkboxes over a Treeview table). Clicking
        # a row selects that file in the file list.
        self.tab_summary = ttk.Frame(self.nb)
        self.nb.add(self.tab_summary, text="Summary")
        self._build_summary_controls(self.tab_summary)
        self.summary_tree = self._make_tree(self.tab_summary)

        self.summary_tree.bind("<<TreeviewSelect>>", self._on_summary_select)

        # Time-bins tab: a note line (which file / why empty) over the table.
        self.tab_bins = ttk.Frame(self.nb)
        self.nb.add(self.tab_bins, text="Time Bins")
        self.bins_note = tk.StringVar()
        ttk.Label(self.tab_bins, textvariable=self.bins_note, padding=(4, 6)).pack(
            side=tk.TOP, anchor=tk.W
        )
        self.bins_tree = self._make_tree(self.tab_bins)

        # Plot tabs: a control row on top, and an area the figure is redrawn into
        # (kept separate so redrawing never removes the controls).
        self.tab_path = ttk.Frame(self.nb)
        self.nb.add(self.tab_path, text="Path")
        self._build_path_controls(self.tab_path)
        self.path_area = ttk.Frame(self.tab_path)
        self.path_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tab_heat = ttk.Frame(self.nb)
        self.nb.add(self.tab_heat, text="Heatmap")
        self._build_heatmap_controls(self.tab_heat)
        self.heat_area = ttk.Frame(self.tab_heat)
        self.heat_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Review tab: the selected file's video with its tracking drawn on, and
        # the moments to check (outside the regions; long ones flagged).
        self.review = ReviewPanel(self.nb, on_cutoff=self._save_review_cutoff,
                                  on_scored=self._on_scored,
                                  on_trial_info=self._on_trial_info)
        self.nb.add(self.review, text="Review")
        self.nb.bind("<<NotebookTabChanged>>", lambda _e: self._on_tab_change())

    def _make_tree(self, parent) -> ttk.Treeview:
        wrap = ttk.Frame(parent)
        wrap.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(wrap, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        return tree

    # -------------------------------------------------------------- helpers
    def _fps(self) -> float:
        try:
            v = float(self.fps_var.get())
            if v <= 0:
                raise ValueError
            return v
        except ValueError:
            show_warning(self, "Invalid frame rate",
                         "The frame rate must be a number above 0. Using 20 fps instead.")
            self.fps_var.set("20")
            return 20.0

    def _bin_seconds(self) -> float:
        try:
            v = float(self.bin_var.get())
            if v <= 0:
                raise ValueError
            return v
        except ValueError:
            show_warning(self, "Invalid bin size",
                         "The bin size must be a number above 0. Using 60 s instead.")
            self.bin_var.set("60")
            return 60.0

    def _min_entry_frames(self) -> int:
        try:
            v = int(float(self.entry_var.get()))
            if v < 1:
                raise ValueError
            return v
        except ValueError:
            show_warning(self, "Invalid entry rule",
                         "The minimum entry length must be a whole number of frames, "
                         "1 or more. Using 5 frames instead.")
            self.entry_var.set("5")
            return 5

    def _min_entry_frames_quiet(self) -> int:
        """The entry rule in use (the locked one once analyzed), without a
        warning if the box isn't a number (for the Review list)."""
        if self._locked():
            return int(self.config_data["min_entry_frames"])
        try:
            return max(1, int(float(self.entry_var.get())))
        except ValueError:
            return int(self.config_data["min_entry_frames"])

    def _frames_setting(self, var, name: str, default: int) -> int:
        """A whole number of frames (1 or more), resetting to `default` if invalid."""
        try:
            v = int(float(var.get()))
            if v < 1:
                raise ValueError
            return v
        except ValueError:
            show_warning(self, f"Invalid {name}",
                         f"The {name} must be a whole number of frames, 1 or more. "
                         f"Using {default} frames instead.")
            var.set(str(default))
            return default

    def _seconds_setting(self, var, name: str, default: float) -> float:
        """A threshold in seconds (0 or more), resetting to `default` if invalid."""
        try:
            v = float(var.get())
            if v < 0:
                raise ValueError
            return v
        except ValueError:
            show_warning(self, f"Invalid {name}",
                         f"The {name} must be a number of seconds, 0 or more. "
                         f"Using {default:g} s instead.")
            var.set(f"{default:g}")
            return default

    def _plot_settings(self) -> dict:
        """Current plot style. A box that's mid-edit or invalid keeps its last good
        value instead of interrupting the user with a warning on every keystroke."""
        p = self.config_data["plot"]

        def read(var, cast, lo, hi, key):
            try:
                v = cast(float(var.get()))
            except ValueError:
                return p[key]
            return min(max(v, lo), hi)

        p["point_size"] = read(self.size_var, float, 0.5, 50, "point_size")
        p["alpha"] = read(self.alpha_var, float, 0.05, 1.0, "alpha")
        p["heatmap_bins"] = read(self.hbins_var, int, 5, 300, "heatmap_bins")
        p["heatmap_cmap"] = self.cmap_var.get() or p["heatmap_cmap"]
        p["color_by_speed"] = bool(self.speed_var.get())
        p["point_color"] = self.point_color
        p["heatmap_bg_mode"] = self._choice(HEATMAP_BACKGROUNDS, self.bg_var.get())
        p["heatmap_background"] = p["heatmap_bg_mode"] == "color"
        p["path_background"] = self._choice(PATH_BACKGROUNDS, self.path_bg_var.get())
        p["path_labels"] = bool(self.path_labels_var.get())
        p["heatmap_labels"] = bool(self.heat_labels_var.get())
        p["heatmap_bg_color"] = self.bg_color
        return p

    @staticmethod
    def _choice(choices: dict, label: str) -> str:
        return next((k for k, v in choices.items() if v == label), "none")

    def _reference(self, entry) -> "np.ndarray | None":
        """The file's reference image (cached), or None if it has none."""
        if entry is None or entry.data is None:
            return None
        key = entry.data.path
        if key not in self._references:
            try:
                self._references[key] = load_reference(entry.data)
            except Exception:
                traceback.print_exc()
                self._references[key] = None
        return self._references[key]

    def _schedule_redraw(self) -> None:
        """Redraw plots shortly after the last change, not on every keystroke."""
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
        self._redraw_job = self.after(400, self._redraw_plots)

    def _redraw_plots(self) -> None:
        self._redraw_job = None
        p = self._plot_settings()
        entry = self._selected_entry()
        if entry is None or not entry.analyzed:
            return
        missing = "(this file has no reference image)" if self._reference(entry) is None else ""
        self.path_bg_note.configure(
            text=missing if p["path_background"] == "reference" else "")
        self.heat_bg_note.configure(
            text=missing if p["heatmap_bg_mode"] == "reference" else "")
        # Each plot on its own: one failing never leaves another file's plot
        # on screen under this file's name.
        for area, make in ((self.path_area, self._path_fig), (self.heat_area, self._heat_fig)):
            try:
                self._show_figure(area, make(entry, p))
            except Exception as exc:
                traceback.print_exc()
                self._clear_tab(area, f"This plot couldn't be drawn.\n\n{exc}")

    # The same builders draw the on-screen plots and the exported images, so
    # exports always match what's shown.
    def _path_fig(self, entry, p):
        if self.test_var.get() == ASR_TEST:
            return motion_figure(entry.data, entry.bins)
        return path_figure(
            entry.data,
            color_by_speed=p["color_by_speed"],
            point_size=p["point_size"],
            point_color=p["point_color"],
            alpha=p["alpha"],
            reference=self._reference(entry) if p["path_background"] == "reference" else None,
            labels=p["path_labels"],
            zone_cm=self._zone_cm() if self.test_var.get() == OBJECT_TEST else None,
        )

    def _heat_fig(self, entry, p):
        if self.test_var.get() == ASR_TEST:
            c = self.config_data
            return aligned_figure(entry.data, entry.bins, c["asr_startle_ms"], c["asr_baseline_ms"])
        return heatmap_figure(
            entry.data, bins=p["heatmap_bins"], cmap=p["heatmap_cmap"],
            background=p["heatmap_bg_color"] if p["heatmap_bg_mode"] == "color" else None,
            reference=(self._reference(entry) if p["heatmap_bg_mode"] == "reference"
                       else None),
            labels=p["heatmap_labels"],
            zone_cm=self._zone_cm() if self.test_var.get() == OBJECT_TEST else None,
        )

    def _on_color_mode(self, redraw: bool = True) -> None:
        # The solid color only applies when not coloring by speed.
        state = tk.DISABLED if self.speed_var.get() else tk.NORMAL
        self.color_btn.configure(state=state)
        if redraw:
            self._schedule_redraw()

    def _on_background(self, redraw: bool = True) -> None:
        # The color only matters for a flat-color background.
        color = self.bg_var.get() == HEATMAP_BACKGROUNDS["color"]
        self.bg_btn.configure(state=tk.NORMAL if color else tk.DISABLED)
        if redraw:
            self._schedule_redraw()

    def _pick_bg_color(self) -> None:
        _, hex_color = colorchooser.askcolor(
            color=self.bg_color, title="Heatmap background color", parent=self
        )
        if hex_color:
            self.bg_color = hex_color
            self.bg_swatch.configure(background=hex_color)
            self._schedule_redraw()

    def _pick_color(self) -> None:
        _, hex_color = colorchooser.askcolor(
            color=self.point_color, title="Point color", parent=self
        )
        if hex_color:
            self.point_color = hex_color
            self.color_swatch.configure(background=hex_color)
            self._schedule_redraw()

    def _save_settings(self, fps: float, bin_s: float) -> None:
        self.config_data["fps"] = fps
        self.config_data["bin_seconds"] = bin_s
        self.config_data["asr_startle_ms"] = self._ms_setting(
            self.asr_startle_var, "startle window", 200.0)
        self.config_data["asr_baseline_ms"] = self._ms_setting(
            self.asr_baseline_var, "baseline window", 200.0)
        try:
            self.config_data["asr_block_trials"] = max(1, int(float(self.asr_block_var.get())))
        except ValueError:
            self.asr_block_var.set(str(self.config_data["asr_block_trials"]))
        self.config_data["fill_gaps"] = bool(self.fill_var.get())
        try:
            self.config_data["fill_gaps_max_frames"] = max(1, int(float(self.fill_max_var.get())))
        except ValueError:
            pass  # keep the last good value
        self._plot_settings()
        self.config_data["summary_columns"] = {
            k: bool(v.get()) for k, v in self.group_vars.items()
        }
        try:
            save_config(self.config_data)
        except OSError:
            traceback.print_exc()  # settings just won't persist this time

    def _on_close(self) -> None:
        if self._exporting:
            # Finish the file being written, then close (see `export`).
            self._close_after_export = True
            self.cancel_export()
            return
        self._flush_zone_change()
        if self._runner is not None:
            if not ask_yes_no(self, "Tracking is running",
                              "Tracking is still running. Stop it and close? Videos "
                              "already finished are saved; the rest aren't tracked.",
                              yes="Stop and Close", no="Keep Tracking"):
                return
            runner = self._runner       # (it may have finished while the question was up)
            if runner is not None:
                runner.cancel()
                runner.join(timeout=10)  # it stops after the current frame
            self._runner = None
        if not self._confirm_losing_setups(self.files, "Close"):
            return
        if not self.review.release():
            return
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
        self.review.unload()
        self._save_settings(self._fps(), self._bin_seconds())
        self.destroy()

    def report_callback_exception(self, exc, val, tb) -> None:
        """An error nothing else caught, in any button, key or timer of any
        window: write it to the console as before, and also say so on screen
        (one message at a time), instead of the action just silently not
        finishing."""
        traceback.print_exception(exc, val, tb)
        if getattr(self, "_error_showing", False):
            return
        self._error_showing = True
        try:
            show_error(self, "Something went wrong",
                       "Something went wrong, and the last action may not have "
                       f"finished.\n\n{exc.__name__}: {val}\n\nNothing saved earlier "
                       "is affected. If it keeps happening, the console window has "
                       "the details to report.")
        except Exception:
            traceback.print_exc()
        finally:
            self._error_showing = False

    def _build_summary_df(self) -> pd.DataFrame:
        """Every file in the list: File, Status, then its metrics (blank until
        analyzed). This is also what Export saves for the Summary."""
        rows = []
        for e in self.files:
            row = {"File": e.label, "Status": ANALYZED if e.analyzed else NOT_ANALYZED}
            if e.analyzed:
                row.update({k: v for k, v in e.summary.items() if k != "File"})
            rows.append(row)
        return pd.DataFrame(rows)

    def _show_summary(self) -> None:
        """Fill the Summary table: File and Status, then the checked groups."""
        df = self._summary_df = self._build_summary_df()
        if df.empty:
            self._fill_tree(self.summary_tree, df)
            return
        groups = summary_column_groups([c for c in df.columns if c != "Status"],
                                       self.test_var.get())
        cols = ["File", "Status"]
        for key, var in self.group_vars.items():
            if var.get():
                cols += groups.get(key, [])  # group order, so Details stay last
        self._fill_tree(self.summary_tree, df[cols], iids=[str(i) for i in df.index])
        self._sync_summary_selection()

    def _fill_tree(self, tree: ttk.Treeview, df, iids=None) -> None:
        tree.delete(*tree.get_children())
        if df is None or df.empty:
            tree["columns"] = ()
            return
        cols = list(df.columns)
        tree["columns"] = cols
        for c in cols:
            tree.heading(c, text=c)
            # Wide enough for the header and the longest value, so file names
            # (and the "(2)" on repeats) aren't cut off.
            longest = max([len(str(c))] + [len(str(v)) for v in df[c].dropna()])
            anchor = tk.W if c == "File" else tk.CENTER
            tree.column(c, width=max(80, min(420, 8 * longest + 16)), anchor=anchor,
                        stretch=False)
        for n, (_, row) in enumerate(df.iterrows()):
            tree.insert("", tk.END, iid=iids[n] if iids else None,
                        values=[_shown(row[c]) for c in cols])

    def _show_figure(self, parent, fig) -> None:
        # Clear whatever was in this tab before.
        for child in parent.winfo_children():
            child.destroy()
        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        toolbar = NavigationToolbar2Tk(canvas, parent, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def _clear_tab(self, parent, message: str) -> None:
        for child in parent.winfo_children():
            child.destroy()
        ttk.Label(parent, text=message, padding=20).pack()

    # ------------------------------------------------------------ selection
    def _selected_entry(self) -> FileEntry | None:
        """The file the tabs show: the focused one among those selected."""
        if self._selected is None or self._selected >= len(self.files):
            return None
        return self.files[self._selected]

    def _selected_entries(self) -> list[FileEntry]:
        """The files Analyze and Export act on."""
        return [self.files[i] for i in self._sel if i < len(self.files)]

    def _on_select(self, _event=None) -> None:
        sel = sorted(int(i) for i in self.file_tree.selection())
        focus = self.file_tree.focus()
        shown = int(focus) if focus and int(focus) in sel else (sel[0] if sel else None)
        self._sel = sel
        self._update_action_buttons()
        if shown != self._selected:
            self._selected = shown
            self._sync_summary_selection()
            self._show_selected()

    def _on_summary_select(self, _event=None) -> None:
        """Clicking a Summary row selects that file in the file list."""
        sel = self.summary_tree.selection()
        if sel and int(sel[0]) != self._selected:
            self._set_selection([int(sel[0])])

    def _set_selection(self, indices: list[int], focus: int | None = None) -> None:
        """Select these files in the list; `focus` (default: the first) is the
        one the tabs show."""
        self.file_tree.selection_set([str(i) for i in indices])
        shown = None
        if indices:
            shown = focus if focus in indices else indices[0]
            self.file_tree.focus(str(shown))
            self.file_tree.see(str(shown))
        self._sel = list(indices)
        self._update_action_buttons()
        if shown != self._selected:
            self._selected = shown
            self._show_selected()
        self._sync_summary_selection()

    def _sync_summary_selection(self) -> None:
        # The Summary table highlights the file the tabs show. Its selection
        # event is ignored because that file is already the shown one.
        if self._selected is not None and self.summary_tree.exists(str(self._selected)):
            self.summary_tree.selection_set(str(self._selected))
            self.summary_tree.see(str(self._selected))
        else:
            self.summary_tree.selection_set(())

    def _update_action_buttons(self) -> None:
        n = len(self._sel)
        self.analyze_btn.configure(text=f"Analyze ({n})" if n else "Analyze")
        videos = sum(self.files[i].video is not None for i in self._sel if i < len(self.files))
        self.track_btn.configure(text=f"Track ({videos})" if videos else "Track")
        self.export_btn.configure(text=f"Export ({n})" if n else "Export")
        everything = bool(self.files) and n == len(self.files)
        self.select_all_btn.configure(text="Select none" if everything else "Select all")

    def select_all(self) -> None:
        if self.files:
            self._set_selection(list(range(len(self.files))), focus=self._selected)

    def toggle_select_all(self) -> None:
        if self.files and len(self._sel) == len(self.files):
            self._set_selection([])
        else:
            self.select_all()

    # --------------------------------------------------------------- review
    def _review_cutoff(self, test: str | None = None) -> float:
        test = test or self.test_var.get()
        return float(self.config_data["review_cutoff_s"].get(test, 1.0))

    def _save_review_cutoff(self, value: float) -> None:
        self.config_data["review_cutoff_s"][self.test_var.get()] = value
        self._save_settings(self._fps_locked() if self._locked() else self._fps(),
                            self._bin_seconds_locked() if self._locked() else self._bin_seconds())

    def _on_tab_change(self) -> None:
        if self.nb.select() == str(self.review):
            self._show_review()
        else:
            self.review.pause()

    def _show_review(self) -> None:
        """Load the selected file into the Review tab (only while it's showing,
        so the video isn't opened for nothing)."""
        if self.nb.select() != str(self.review):
            return
        self._flush_zone_change()
        entry = self._selected_entry()
        if not self.review.release(entry.data if entry is not None else None):
            # A video is still being saved and the user chose to keep saving:
            # stay on that file.
            back = next((i for i, e in enumerate(self.files)
                         if e.data is self.review._data), None)
            if back is not None and back != self._selected:
                self._set_selection([back], focus=back)
            return
        startle = self.test_var.get() == ASR_TEST
        if (startle and entry is not None and entry.data is not None
                and is_motion_file(entry.data.path)):
            c = self.config_data
            startle_ms, baseline_ms = float(c["asr_startle_ms"]), float(c["asr_baseline_ms"])
            trials = (entry.bins if entry.analyzed
                      else trial_table(entry.data, startle_ms, baseline_ms))
            self.review.load(entry.data, entry.video.path if entry.video else None, {}, 1.0,
                             title=entry.label, trials=trials, startle_ms=startle_ms,
                             baseline_ms=baseline_ms)
        elif startle and entry is not None and entry.data is not None:
            self.review.show_message(f"{entry.label} is a tracking file, not a startle motion "
                                     "index file. Track its video with this test first.")
        elif entry is None:
            self.review.show_message("Select a tracked file in the file list to review "
                                     "its video.")
        elif entry.data is None:
            self.review.show_message(f"{entry.label} hasn't been tracked yet. Set it up "
                                     "and click Track, then review it here.")
        else:
            objects = self.test_var.get() == OBJECT_TEST
            self.review.load(entry.data, entry.video.path if entry.video else None,
                             self._current_roles([entry]), self._review_cutoff(),
                             title=entry.label,
                             zone_cm=self._zone_cm() if objects else None,
                             min_frames=self._min_entry_frames_quiet(),
                             fps=self._analysis_fps())

    def _analysis_fps(self) -> float | None:
        """The frame rate results are worked out with: the load's once it's
        fixed, else the Frame rate box if it holds one (no pop-up here)."""
        if self._locked():
            return float(self._fps_locked())
        try:
            v = float(self.fps_var.get())
            return v if v > 0 else None
        except ValueError:
            return None

    def _save_config_quietly(self) -> None:
        """Save the settings now; if the file can't be written they just
        don't persist this time (as in `_save_settings`)."""
        try:
            save_config(self.config_data)
        except OSError:
            traceback.print_exc()

    def _on_scored(self, data) -> None:
        """Scoring changed in the playback window: refresh that file's
        results if it's analyzed (ROADMAP §15)."""
        for e in self.files:
            if e.data is data and e.analyzed:
                self._object_results(e)
                self._refresh()

    def _on_trial_info(self, data, kinds: dict, day: str, phase: str) -> None:
        """Object types, day or phase were edited after tracking: keep the
        video's setup in step (so tracking again keeps them), then update the
        results."""
        for e in self.files:
            if e.data is data and e.video is not None:
                e.video.object_kinds.update(kinds)
                e.video.trial_day, e.video.trial_phase = day, phase
        self._on_scored(data)

    def _object_results(self, entry) -> None:
        """Work out an analyzed file's results again (its scoring or the
        zone distance changed)."""
        self._analyze_entry(entry)

    def _warn_lost(self, entries) -> None:
        """After Analyze: flag files where the point stayed outside the regions
        at least the review cutoff (the tracker may have lost the animal)."""
        cutoff = self._review_cutoff()
        found = []
        for e in entries:
            if not e.summary or not e.summary.get("OutsideEvents"):
                continue
            fps = self.config_data["fps"]
            long = [ev for ev in outside_events(e.data, self._current_roles([e]), fps)
                    if ev["seconds"] >= cutoff]
            if long:
                found.append(f"• {e.label}: {len(long)} time(s), longest "
                             f"{max(ev['seconds'] for ev in long):g} s")
        if found:
            show_warning(
                self, "The tracker may have lost the animal",
                "The tracked point stayed outside the drawn regions for a while in "
                f"these files (at least {cutoff:g} s).\n\n" + "\n".join(found)
                + "\n\nBrief stretches are usually jumps or head dips, but a long one "
                "can mean the tracker got stuck on a dark spot or a reflection. Select "
                "the file and open the Review tab to see each one in the video.")

    def _show_selected(self) -> None:
        """Point Time Bins, Path, Heatmap, and Review at the selected file."""
        self._show_review()
        entry = self._selected_entry()
        if entry is None:
            note = ("Add files, then select one in the file list." if not self.files
                    else "Select a file in the file list.")
        elif not entry.analyzed:
            note = f"{entry.label} isn't analyzed yet. Select it and click Analyze."
        else:
            note = None

        if note:
            self.bins_note.set(note)
            self._fill_tree(self.bins_tree, None)
            self._clear_tab(self.path_area, note)
            self._clear_tab(self.heat_area, note)
            return
        self.bins_note.set(
            f"{entry.label}: {len(entry.bins)} trial(s)" if self.test_var.get() == ASR_TEST
            else f"{entry.label}: {self._bin_seconds_locked():g} s bins")
        self._fill_tree(self.bins_tree, entry.bins)
        self._redraw_plots()

    # -------------------------------------------------------------- locking
    def _locked(self) -> bool:
        """Settings lock at the first Analyze of a load and stay locked until
        Clear (analyzed files only exist between those two points)."""
        return any(e.analyzed for e in self.files)

    def _apply_lock(self) -> None:
        """Grey out test type, fps, and bin size once anything is analyzed.
        The Path/Heatmap plot controls are never locked."""
        locked = self._locked()
        self.test_box.configure(state="disabled" if locked else "readonly")
        for entry in (self.fps_entry, self.bin_entry, self.entry_entry,
                      self.gap_entry, self.adj_entry, self.smooth_entry,
                      self.fill_check, self.fill_max_entry, self.asr_startle_entry,
                      self.asr_baseline_entry, self.asr_block_entry):
            entry.configure(state="disabled" if locked else "normal")
        self.asr_threshold_entry.configure(
            state="disabled" if self._tracking_locked() else "normal")
        self._layout_sections()  # shows or hides "Locked. Clear to change."

    def _fps_locked(self) -> float:
        return self.config_data["fps"]

    def _bin_seconds_locked(self) -> float:
        return self.config_data["bin_seconds"]

    def _lock_in_settings(self) -> None:
        """Validate and save the toolbar's test/fps/bin/entry values as this
        load's settings (called at Analyze, before anything is locked)."""
        self.config_data["test_type"] = self.test_var.get()
        self.config_data["min_entry_frames"] = self._min_entry_frames()
        self.config_data["min_seconds_between_entries"] = self._seconds_setting(
            self.gap_var, "time between center entries", 1.0)
        self.config_data["min_center_seconds_adjoining"] = self._seconds_setting(
            self.adj_var, "center time for adjoining crossings", 0.5)
        self.config_data["speed_smoothing_frames"] = self._frames_setting(
            self.smooth_var, "speed smoothing", 5)
        self.config_data["fill_gaps"] = bool(self.fill_var.get())
        self.config_data["fill_gaps_max_frames"] = self._frames_setting(
            self.fill_max_var, "gap length to fill", 5)
        self._save_settings(self._fps(), self._bin_seconds())

    # -------------------------------------------------------------- regions
    def _region_overview(self, entries=None) -> list[tuple[str, float]]:
        """Every region across the given files (first-seen order) with its
        share of their frames."""
        frames: dict[str, int] = {}
        total = 0
        for e in self.files if entries is None else entries:
            if e.data is None:
                continue  # a video not tracked yet
            total += e.data.n_frames
            for r in e.data.regions:
                frames[r] = frames.get(r, 0) + int(e.data.df[r].sum())
        return [(r, 100.0 * n / total if total else 0.0) for r, n in frames.items()]

    def _current_roles(self, entries=None) -> dict[str, str]:
        """Role of every region in these files: tracked files' region columns,
        plus regions drawn in the setup window for videos not tracked yet
        (named as tracking will write them)."""
        names = [r for r, _ in self._region_overview(entries)]
        test = self.test_var.get()
        dsmpl = float(self.config_data["video_downsample"])
        for e in self.files if entries is None else entries:
            if e.data is None and e.video is not None:
                names += [r.name for r in e.video.tracking_regions(dsmpl, test)
                          if r.name not in names]
        return resolve_roles(names, self.config_data["region_roles"])

    def _unfit(self, entries) -> list[tuple[FileEntry, list[str]]]:
        """Files whose own regions don't fit the chosen test, with the problems."""
        test = self.test_var.get()
        out = []
        for e in entries:
            problems = check_roles(test, self._current_roles([e]))
            if problems:
                out.append((e, problems))
        return out

    def _ready_to_analyze(self, entries) -> list[FileEntry]:
        """Before analyzing: check each file's regions fit the test, asking the
        user to match them if not. Returns the files that can be analyzed;
        any that still don't fit are skipped, with a message naming them."""
        unfit = self._unfit(entries)
        if not unfit:
            return list(entries)
        test = self.test_var.get()
        bad = [e for e, _ in unfit]
        if any("" in self._current_roles([e]).values() for e in bad):
            reason = ("Some region names in these files couldn't be matched "
                      "automatically. Please choose a role for each.")
        else:
            reason = (f"Some files' regions don't fit the {test} test "
                      f"({'; '.join(unfit[0][1])}). Adjust the roles, or if the "
                      "test is wrong, cancel and click Clear to choose it again.")
        self.open_region_dialog(reason=reason, entries=bad)

        still = self._unfit(entries)
        if still:
            lines = "\n".join(f"• {e.label}: {'; '.join(pr)}" for e, pr in still)
            show_warning(
                self, "Some files not analyzed",
                f"These files don't fit the {test} test and were skipped.\n\n"
                f"{lines}\n\nUse Regions… to assign their regions, or click "
                "Clear to choose a different test.",
            )
        skipped = {id(e) for e, _ in still}
        return [e for e in entries if id(e) not in skipped]

    def _warn_overlaps(self, entries) -> None:
        """Center and periphery should never overlap; warn about files where
        they do (the file's ROIs are wrong)."""
        roles = self._current_roles(entries)
        overlaps = []
        for e in entries:
            n = center_periphery_overlap(e.data, roles)
            if n:
                overlaps.append((e.label, n, 100.0 * n / e.data.n_frames))
        if not overlaps:
            return
        lines = "\n".join(
            f"• {name}: {n:,} frames ({pct:.1f}% of the session)"
            for name, n, pct in overlaps
        )
        show_warning(
            self, "Center and periphery overlap",
            "Center and periphery overlap in these files, which is an error "
            "in the file.\n\n"
            "Center and periphery should always be separate, but these frames "
            f"are marked as both:\n{lines}\n\n"
            "Usually the periphery ROI was drawn around the whole arena instead "
            "of only the outer ring. Re-drawing the ROIs in the tracking "
            "software is the real fix. Until then, these frames are counted as "
            "center (not periphery).",
        )

    def open_region_dialog(self, reason: str = "", entries=None) -> None:
        entries = self.files if entries is None else entries
        overview = self._region_overview(entries)
        if not overview:
            show_info(self, "No regions", "Add a file with region columns first.")
            return
        preview = next((e.data for e in entries if e.data is not None and e.data.regions),
                       None)
        dlg = RegionDialog(
            self, self.test_var.get(), overview, self._current_roles(entries),
            preview=preview, reason=reason,
        )
        self.wait_window(dlg)
        if dlg.result is None:
            return
        # Save only real overrides, so later improvements to the automatic
        # suggestions still reach names the user never changed.
        saved = self.config_data["region_roles"]
        for name, role in dlg.result.items():
            if role == auto_role(name):
                saved.pop(name, None)
            else:
                saved[name] = role
        self._save_settings(self._fps_locked(), self._bin_seconds_locked())
        self._update_status()
        # Files already analyzed were analyzed with the roles as they were:
        # work them out again, so the results (and the exported Settings
        # sheet, which lists the roles) all use the roles now saved.
        if any(e.analyzed for e in self.files):
            self._reanalyze([e for e in self.files if e.analyzed])
            self._refresh()

    def _on_test_type(self) -> None:
        # Only reachable while unlocked; regions are checked at Analyze.
        test = self.test_var.get()
        self.config_data["test_type"] = test
        self._save_settings(self._fps(), self._bin_seconds())
        # A video still on its standard session length takes the new test's
        # (5 min for a plus maze, 60 for an open field, the whole video for
        # startle); a length the user set is kept.
        for e in self.files:
            if e.video is not None and e.video.length_default not in ("", test):
                use_default_length(e.video, self.config_data, test)
        self._show_test_settings()
        win = getattr(self, "_setup_win", None)
        if win is not None and win.winfo_exists():
            win._show_video()       # its steps and lengths follow the test too
        self._refresh()

    def _show_test_settings(self) -> None:
        """Show the settings and tabs that apply to the chosen test."""
        self._layout_sections()
        asr = self.test_var.get() == ASR_TEST
        self.nb.tab(self.tab_bins, text="Trials" if asr else "Time Bins")
        self.nb.tab(self.tab_path, text="Motion Trace" if asr else "Path")
        self.nb.tab(self.tab_heat, text="Aligned Trials" if asr else "Heatmap")
        for col, area in ((self.path_col, self.path_area), (self.heat_col, self.heat_area)):
            if asr:
                col.pack_forget()
            elif not col.winfo_manager():
                col.pack(side=tk.RIGHT, fill=tk.Y, before=area)
        for row in (1, 2):      # frame rate and bin size don't apply to startle
            for widget in self.session_section.grid_slaves(row=row):
                widget.grid_remove() if asr else widget.grid()

    # --------------------------------------------------------------- status
    def _update_status(self) -> None:
        if not self.files:
            self.status.set("Add or drop files, choose the test, frame rate, and "
                            "bin size, then click Analyze.")
            return
        done = sum(e.analyzed for e in self.files)
        if self.test_var.get() == ASR_TEST:
            self.status.set(
                f"{len(self.files)} file(s), {done} analyzed — {ASR_TEST} — threshold "
                f"{self.asr_threshold_var.get()}, startle window {self.asr_startle_var.get()} "
                f"ms, baseline window {self.asr_baseline_var.get()} ms")
            return
        roles = self._current_roles()
        problems = check_roles(self.test_var.get(), roles)
        regions = f"⚠ {'; '.join(problems)}" if problems else describe_roles(roles)
        if not roles and any(e.video is not None for e in self.files):
            regions = "draw them in Set up videos…"  # nothing drawn or tracked yet
        if self.test_var.get() == OBJECT_TEST:
            regions = f"zone {self.zone_var.get()} cm from each edge"
        if self._locked():
            settings = (f"{self.test_var.get()}, {self._fps_locked():g} fps, "
                        f"{self._bin_seconds_locked():g} s bins, "
                        f"entry ≥ {self.config_data['min_entry_frames']} frames"
                        f"{self._of_status(locked=True)} (locked)")
        else:
            settings = (f"{self.test_var.get()}, {self.fps_var.get()} fps, "
                        f"{self.bin_var.get()} s bins, entry ≥ {self.entry_var.get()} "
                        f"frames{self._of_status(locked=False)} (locks at Analyze)")
        what = "Objects" if self.test_var.get() == OBJECT_TEST else "Regions"
        self.status.set(
            f"{len(self.files)} file(s), {done} analyzed — {settings} — "
            f"{what}: {regions}"
        )

    def _zone_cm(self) -> float:
        """The zone distance typed (the saved one if the box isn't a number)."""
        try:
            v = float(self.zone_var.get())
            if v >= 0:
                return v
        except ValueError:
            pass
        return float(self.config_data["object_zone_cm"])

    def _on_asr_threshold(self) -> None:
        """Save a valid intensity threshold."""
        try:
            value = float(self.asr_threshold_var.get())
        except ValueError:
            return
        if 0 <= value <= 255 and value != self.config_data["asr_threshold"]:
            self.config_data["asr_threshold"] = value
            self._save_config_quietly()
        self._update_status()

    def _ms_setting(self, var, name: str, default: float) -> float:
        """A window length in ms (above 0), resetting to `default` if invalid."""
        try:
            value = float(var.get())
            if value <= 0:
                raise ValueError
            return value
        except ValueError:
            show_warning(self, f"Invalid {name}",
                         f"The {name} must be a number of milliseconds above 0. "
                         f"Using {default:g} ms instead.")
            var.set(f"{default:g}")
            return default

    def _zone_typed(self) -> None:
        """A keystroke in the Zone distance box: apply it once typing has
        stopped for a moment."""
        if self._zone_job is not None:
            self.after_cancel(self._zone_job)
        self._zone_job = self.after(ZONE_WAIT_MS, self._flush_zone_change)

    def _flush_zone_change(self) -> None:
        """Apply the Zone distance box now (Return, leaving the box, or
        before anything that uses it: Analyze, Export, the Review tab)."""
        if self._zone_job is not None:
            self.after_cancel(self._zone_job)
            self._zone_job = None
            self._on_zone_change()

    def _on_zone_change(self) -> None:
        """Save a valid zone distance and update what depends on it."""
        try:
            v = float(self.zone_var.get())
        except ValueError:
            return
        if v < 0 or v == self.config_data["object_zone_cm"]:
            return
        self.config_data["object_zone_cm"] = v
        self._save_config_quietly()
        self._update_status()
        if hasattr(self, "review"):
            self.review.zone_changed(v)
        if self.test_var.get() == OBJECT_TEST and any(e.analyzed for e in self.files):
            self._reanalyze([e for e in self.files if e.analyzed])
            self._refresh()

    def _of_status(self, locked: bool) -> str:
        if self.test_var.get() != "Open Field":
            return ""
        if locked:
            gap = f"{self.config_data['min_seconds_between_entries']:g}"
            adj = f"{self.config_data['min_center_seconds_adjoining']:g}"
        else:
            gap, adj = self.gap_var.get(), self.adj_var.get()
        return f", entry gap {gap} s, adjoining center {adj} s"

    def _untick_stale_references(self) -> None:
        """Every video whose reference image no longer matches its trim, crop
        or the shared downsampling and frame count loses its Reference and
        Tracking check ticks (`VideoSetup.untick_stale_reference`)."""
        dsmpl = float(self.config_data["video_downsample"])
        frames = int(self.config_data["reference_frames"])
        changed = [e for e in self.files
                   if e.video is not None and e.video.untick_stale_reference(dsmpl, frames)]
        win = getattr(self, "_setup_win", None)
        if changed and win is not None and win.winfo_exists():
            win._update_step_list()

    def _refresh(self) -> None:
        """Re-sync everything that depends on the file list."""
        self._untick_stale_references()
        if any(e.video is not None for e in self.files):
            if not self.setup_btn.winfo_manager():
                self.setup_btn.pack(fill=tk.X, pady=(0, 4), before=self.select_all_btn)
            if not self.track_btn.winfo_manager():
                self.track_btn.pack(fill=tk.X, pady=(4, 0), before=self.analyze_btn)
        else:
            self.setup_btn.pack_forget()
            self.track_btn.pack_forget()
        running = self._runner is not None or self._exporting
        for btn in (self.clear_btn, self.remove_btn, self.track_btn):
            btn.configure(state="disabled" if running else "normal")
        for btn in (self.analyze_btn, self.export_btn):
            btn.configure(state="disabled" if self._exporting else "normal")
        self._apply_lock()
        self._fill_file_list()
        self._show_summary()
        self._show_selected()
        self._update_status()

    def _file_status(self, entry: FileEntry) -> tuple[str, str]:
        """(status text, color tag) for the file list."""
        if entry.track_state == "queued":
            return WAITING_TO_TRACK, "waiting"
        if entry.track_state == "reference":
            return "Making reference", "waiting"
        if entry.track_state == "tracking":
            return f"Tracking {entry.track_pct}%", "waiting"
        if entry.analyzed:
            return ANALYZED, "analyzed"
        if entry.track_state == "failed":
            return FAILED, "failed"
        if entry.data is None:  # a video, not tracked yet
            if entry.video is not None and entry.video.ready_for(self.test_var.get()):
                return READY_TO_TRACK, "waiting"
            return NEEDS_SETUP, "waiting"
        return NOT_ANALYZED, ""

    def _tracking_locked(self) -> bool:
        """Tracking settings lock at the first Track of a load (until Clear),
        and while a Track is running."""
        return self._runner is not None or any(
            e.video is not None and e.data is not None for e in self.files)

    def open_setup(self) -> None:
        """Open the video setup window at the selected video (or the first one
        that still needs setting up)."""
        videos = [e for e in self.files if e.video is not None]
        if not videos:
            show_info(self, "No videos", "Add a video first.")
            return
        win = getattr(self, "_setup_win", None)
        if win is not None and win.winfo_exists():
            if [id(e) for e in win.entries] == [id(e) for e in videos]:
                win.lift()
                return
            win._close()        # the list of videos changed: open it afresh
        chosen = [e for e in self._selected_entries() if e.video is not None]
        start = chosen[0] if chosen else next(
            (e for e in videos if e.data is None), videos[0])
        self._setup_win = None
        try:
            self._setup_win = SetupWindow(self, videos, videos.index(start))
        except Exception as exc:
            traceback.print_exc()
            show_error(self, "The setup window couldn't be opened",
                       f"The setup window couldn't be opened.\n\n{exc}")

    def _close_setup_window(self) -> None:
        win = getattr(self, "_setup_win", None)
        if win is not None and win.winfo_exists():
            win._close()
        self._setup_win = None

    def _confirm_losing_setups(self, entries, action: str) -> bool:
        """Video setups (trim, crop, shapes, regions, scale) aren't saved
        anywhere until the video is tracked. Before `action` throws away
        setup work on videos not tracked yet, ask. True to go ahead."""
        at_risk = [e for e in entries if e.video is not None and e.data is None
                   and (e.video.steps_done or e.video.has_drawn_work())]
        if not at_risk:
            return True
        return ask_yes_no(
            self, "Setup work will be lost",
            f"{len(at_risk)} video(s) have been set up but not tracked yet, and their "
            "setup isn't saved anywhere else.\n\n"
            f"{self._names(at_risk)}\n\n{action} anyway and lose that setup?",
            yes=f"{action} Anyway", no="Cancel")

    def _fill_file_list(self) -> None:
        self.file_tree.delete(*self.file_tree.get_children())
        for i, e in enumerate(self.files):
            status, tag = self._file_status(e)
            self.file_tree.insert("", tk.END, iid=str(i), values=(e.label, e.kind, status),
                                  tags=(tag,) if tag else ())
        keep = [i for i in self._sel if i < len(self.files)]
        self._set_selection(keep, focus=self._selected)

    # --------------------------------------------------------------- actions
    def open_file(self):
        videos = " ".join(f"*{ext}" for ext in VIDEO_EXTENSIONS)
        paths = filedialog.askopenfilenames(
            title="Add tracking CSVs or videos",
            filetypes=[("CSVs and videos", f"*.csv {videos}"), ("CSV files", "*.csv"),
                       ("Videos", videos), ("All files", "*.*")],
        )
        if paths:
            self.add_files(list(paths))

    def open_folder(self):
        folder = filedialog.askdirectory(title="Add a folder of CSVs or videos")
        if not folder:
            return
        found = self._files_in(folder)
        if not found:
            show_info(self, "Nothing to add", "That folder has no CSVs or videos.")
            return
        self.add_files(found)

    def _on_drop(self, event):
        """Dropped CSVs, videos, and folders (their CSVs and videos) are added
        to the list. Anything else is ignored."""
        found = []
        for p in self.tk.splitlist(event.data):
            if os.path.isdir(p):
                found.extend(self._files_in(p))
            elif os.path.isfile(p) and self._addable(p):
                found.append(p)
        if found:
            self.add_files(found)
        else:
            show_info(self, "Nothing to add",
                      "Nothing dropped was a CSV, a video, or a folder of them.")
        return event.action

    @staticmethod
    def _addable(path: str) -> bool:
        return path.lower().endswith(".csv") or is_video(path)

    # CSVs that sit beside videos but aren't tracking files: Track Tamer's own
    # object scoring, and Creature Capture's per-camera frame times and trial
    # info (ROADMAP §16). Adding a folder skips them.
    COMPANION_CSV_SUFFIXES = ("_objectscoring.csv", "_frames.csv", "_info.csv", "_trials.csv")

    @staticmethod
    def _load_output(path: str):
        """A tracking file, or a startle motion index file."""
        return load_motion(path) if is_motion_file(path) else load_csv(path)

    @classmethod
    def _files_in(cls, folder: str) -> list[str]:
        return sorted(
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if cls._addable(f) and not f.startswith(".")
            and not f.lower().endswith(cls.COMPANION_CSV_SUFFIXES)
        )

    @staticmethod
    def _same_file_key(path: str) -> str:
        # normcase: Windows paths are case-insensitive.
        return os.path.normcase(os.path.abspath(path))

    def add_files(self, paths: list[str]) -> None:
        """Add files to the list (never analyzes them; that waits for Analyze)."""
        # The same file twice in one add (e.g. a file and its folder) is just once.
        paths = list(dict.fromkeys(paths, None))
        in_list = {self._same_file_key(e.path) for e in self.files}
        repeats = [p for p in paths if self._same_file_key(p) in in_list]
        if repeats:
            names = "\n".join(f"• {os.path.basename(p)}" for p in repeats[:10])
            if len(repeats) > 10:
                names += f"\n…and {len(repeats) - 10} more"
            add_again = ask_yes_no(
                self, "Already in the list",
                f"{len(repeats)} file(s) are already in the list.\n\n{names}\n\n"
                "Add them again, or ignore them?",
                yes="Add Again", no="Ignore",
            )
            if not add_again:
                paths = [p for p in paths if p not in repeats]
        if not paths:
            return

        errors, hard_to_read = [], []
        first_new = len(self.files)
        new = []
        for p in paths:
            try:
                if is_video(p):
                    setup = VideoSetup(path=p, info=video_info(p))
                    use_default_length(setup, self.config_data, self.test_var.get())
                    setup.unreadable = check_readable(p)
                    bad, checked = setup.unreadable
                    if checked and bad / checked > UNREADABLE_WARN:
                        hard_to_read.append((p, bad, checked))
                    data, name = None, os.path.basename(p)
                else:
                    setup, data = None, self._load_output(p)
                    name = data.name
            except Exception as exc:  # report bad files, keep the good ones
                errors.append(f"{os.path.basename(p)}: {exc}")
                continue
            new.append((p, data, setup, name))

        if hard_to_read:
            lines = "\n".join(f"• {os.path.basename(p)}: {bad} of the first {checked} "
                              f"frames" for p, bad, checked in hard_to_read)
            keep = ask_yes_no(
                self, "Some videos are hard to read",
                "Some videos have frames that couldn't be read.\n\n"
                f"{lines}\n\nThese frames are kept as blank rows when tracking, but "
                "if there are many, converting the video (e.g. to .mp4 with H.264) "
                "usually fixes it. Add these videos anyway?",
                yes="Add Anyway", no="Skip Them",
            )
            if not keep:
                skip = {p for p, _, _ in hard_to_read}
                new = [n for n in new if n[0] not in skip]

        for p, data, setup, name in new:
            key = self._same_file_key(p)
            copies = sum(self._same_file_key(e.path) == key for e in self.files)
            label = name if not copies else f"{name} ({copies + 1})"
            self.files.append(FileEntry(path=p, data=data, label=label, video=setup))

        if not self._sel and len(self.files) > first_new:
            self._sel = [first_new]  # the first new file, ready for Analyze
            self._selected = first_new
        self._refresh()
        if errors:
            show_warning(
                self, "Some files weren't added",
                "Some files couldn't be read and weren't added.\n\n"
                + "\n".join(errors),
            )

    def clear_files(self) -> None:
        """Empty the list and unlock the per-load settings."""
        if self._runner is not None:
            return  # the button is disabled while tracking
        if not self._confirm_losing_setups(self.files, "Clear"):
            return
        if not self.review.release():
            return
        self._close_setup_window()
        self.files = []
        self._sel = []
        self._selected = None
        self._references.clear()
        self.review.unload()
        self._refresh()

    def show_about(self) -> None:
        AboutDialog(self)

    def remove_selected(self) -> None:
        """Take the selected files out of the list (the files aren't touched)."""
        if self._runner is not None:
            return  # the button is disabled while tracking
        if not self._sel:
            show_info(self, "No file selected", "Select files in the list first.")
            return
        gone = set(self._sel)
        if not self._confirm_losing_setups(
                [e for i, e in enumerate(self.files) if i in gone], "Remove"):
            return
        if any(self.files[i].data is self.review._data for i in gone
               if i < len(self.files)) and not self.review.release():
            return
        self._close_setup_window()
        self.files = [e for i, e in enumerate(self.files) if i not in gone]
        self._sel = [0] if self.files else []
        self._selected = 0 if self.files else None
        self._refresh()

    # -------------------------------------------------------------- tracking
    @staticmethod
    def _names(entries, limit: int = 10) -> str:
        lines = "\n".join(f"• {e.label}" for e in entries[:limit])
        if len(entries) > limit:
            lines += f"\n…and {len(entries) - limit} more"
        return lines

    def _split_same_results(self, items, result_base, entry_of):
        """(items to go ahead with, entries left out) where several different
        items would write the same result files: `result_base(item)` is the
        path their result names are built on. The same file listed twice
        isn't a clash (callers have already merged those)."""
        by_base: dict[str, list] = {}
        for item in items:
            by_base.setdefault(self._same_file_key(result_base(item)), []).append(item)
        keep = [group[0] for group in by_base.values() if len(group) == 1]
        clashing = [entry_of(i) for group in by_base.values() if len(group) > 1 for i in group]
        return [i for i in items if i in keep], clashing

    def track(self) -> None:
        """Track the selected videos in the background, one at a time
        (ROADMAP §12, Stage 7). Videos already tracked beside the file can
        use that tracking instead."""
        if self._runner is not None:
            return
        selected = self._selected_entries()
        if not selected:
            show_info(self, "No file selected",
                      "Select a video in the list first, or click Select all.")
            return
        videos = [e for e in selected if e.video is not None]
        if not videos:
            show_info(self, "No videos selected",
                      "Track works on videos. The selected files are CSVs, which "
                      "are already tracked.")
            return
        # A video added twice is tracked once; every copy gets the result.
        groups: dict[str, list[FileEntry]] = {}
        for e in videos:
            groups.setdefault(self._same_file_key(e.path), []).append(e)
        todo = list(groups.values())
        # Different videos that would write the same result files (X.avi and
        # X.mp4 both write X_LocationOutput.csv) are left out and named.
        todo, clashing = self._split_same_results(
            todo, lambda g: os.path.splitext(g[0].path)[0], lambda g: g[0])
        if clashing:
            show_warning(self, "Some videos would overwrite each other's results",
                         "Some videos have the same name with different endings, so "
                         "they would write the same tracking file. They weren't "
                         f"tracked.\n\n{self._names(clashing)}\n\nRemove the ones you "
                         "don't want from the list (or rename one), then click Track "
                         "again.")
            if not todo:
                return

        test = self.test_var.get()
        existing = [g for g in todo if existing_output(g[0].path, test)]
        if existing:
            ending = "_MotionIndex.csv" if test == ASR_TEST else "_LocationOutput.csv"
            choice = ask_choice(
                self, "Some videos are already tracked",
                f"Some videos already have a tracking file ({ending}) "
                f"beside them.\n\n{self._names([g[0] for g in existing])}\n\n"
                "Use that tracking, or track them again (replacing it)?",
                ["Cancel", "Track Again", "Use Existing Tracking"],
            )
            if choice in (None, "Cancel"):
                return      # closing the question never starts tracking
            if choice == "Use Existing Tracking":
                errors = []
                for g in existing:
                    path = existing_output(g[0].path, test)
                    if all(e.data is not None and self._same_file_key(e.data.path)
                           == self._same_file_key(path) for e in g):
                        todo.remove(g)      # already loaded: keep it and its results
                        continue
                    try:
                        data = self._load_output(existing_output(g[0].path, test))
                    except Exception as exc:
                        errors.append(f"• {g[0].label}: {exc}")
                        continue
                    for e in g:
                        e.data, e.summary, e.bins = data, None, None
                        e.track_state = e.track_error = ""
                    todo.remove(g)
                if errors:
                    show_warning(self, "Some tracking files couldn't be read",
                                 "Some tracking files couldn't be read, so those "
                                 "videos weren't loaded.\n\n" + "\n".join(errors))
                    todo = [g for g in todo if g not in existing]
                self._refresh()

        not_ready = [g for g in todo if not g[0].video.ready_for(test)]
        ready = [g for g in todo if g[0].video.ready_for(test)]
        if not_ready:
            show_info(self, "Some videos aren't set up yet",
                      "Some videos aren't set up yet, so they weren't tracked.\n\n"
                      f"{self._names([g[0] for g in not_ready])}\n\n"
                      "Finish all the steps in Set up videos… for them, then click "
                      "Track again.")
        if not ready:
            return

        dsmpl = float(self.config_data["video_downsample"])
        gaps = []
        for g in ready if test != ASR_TEST else []:
            v = g[0].video
            parts = []
            missing = v.missing_regions(test)
            if missing:
                parts.append(("objects" if test == OBJECT_TEST else "regions")
                             + " not drawn: " + ", ".join(missing))
            if v.scale(dsmpl) is None:
                parts.append("no scale")
            if parts:
                gaps.append(f"• {g[0].label}: {'; '.join(parts)}")
        if gaps and not ask_yes_no(
                self, "Some videos are missing regions or a scale",
                "Some videos are missing regions or a scale.\n\n"
                + "\n".join(gaps[:10]) + ("\n…" if len(gaps) > 10 else "")
                + "\n\nWithout their regions, those region measures will be missing. "
                "Without a scale, distances are in pixels only. Track anyway?",
                yes="Track Anyway", no="Cancel"):
            return
        if not self._check_frame_rates([g[0] for g in ready]):
            return

        c = self.config_data
        params = TrackingParams(loc_thresh=float(c["loc_thresh"]), method=c["track_method"],
                                use_window=bool(c["use_window"]),
                                window_size=int(c["window_size"]),
                                window_weight=float(c["window_weight"]))
        try:
            if test == ASR_TEST:
                jobs = [make_asr_job(g[0].video, float(c["asr_threshold"])) for g in ready]
            else:
                jobs = [make_job(g[0].video, params, dsmpl, int(c["reference_frames"]), test)
                        for g in ready]
        except Exception as exc:
            traceback.print_exc()
            show_error(self, "Tracking couldn't start", f"Tracking couldn't start.\n\n{exc}")
            return
        for g in ready:
            for e in g:
                e.track_state, e.track_pct, e.track_error = "queued", 0, ""
        self._track_groups = ready
        self._track_current = 0
        self._track_results = {"done": 0, "failed": [], "cancelled": False}
        self._runner = TrackRunner(jobs)
        self._runner.start()
        self.track_cancel_btn.configure(state="normal")
        self.track_progress["value"] = 0
        self.track_bar.pack(side=tk.BOTTOM, fill=tk.X, before=self.body)
        self._show_track_progress()
        self._refresh()
        win = getattr(self, "_setup_win", None)
        if win is not None and win.winfo_exists() and win.step == "tracking":
            win._go("tracking")  # show its settings locked
        self.after(150, self._poll_tracking)

    def _check_frame_rates(self, entries) -> bool:
        """Fill the frame-rate setting from the videos, or warn when they
        disagree with it or with each other. False if the user cancels."""
        if self.test_var.get() == ASR_TEST:
            other = [e for e in entries if abs((e.video.info.fps or 0) - 30) > 1]
            return not other or ask_yes_no(
                self, "Some videos aren't 30 fps",
                f"Some videos aren't 30 fps.\n\n{self._names(other)}\n\nThe motion index "
                "method and its threshold of 15 were set at 30 fps, so results at other "
                "frame rates may not compare. Track anyway?",
                yes="Track Anyway", no="Cancel")
        tracked = [e for e in self.files if e.video is not None and e.data is not None]
        rates = {}
        for e in entries + tracked:
            if e.video.info.fps:
                rates.setdefault(round(e.video.info.fps, 2), []).append(e)
        if not rates:
            return True
        locked = self._locked()
        try:
            setting = float(self.config_data["fps"] if locked else self.fps_var.get())
        except ValueError:
            setting = None
        if len(rates) > 1:
            lines = "\n".join(f"• {g[0].label}: {r:g} fps" + (
                f" (and {len(g) - 1} more)" if len(g) > 1 else "")
                for r, g in sorted(rates.items()))
            return ask_yes_no(
                self, "The videos have different frame rates",
                "The videos weren't all recorded at the same frame rate.\n\n"
                f"{lines}\n\nThe analysis uses one frame rate for every file "
                f"({self.fps_var.get()} fps), so times for the others will be off. "
                "Analyze videos with different rates in separate loads (Clear "
                "between them). Track anyway?",
                yes="Track Anyway", no="Cancel")
        rate = next(iter(rates))
        if setting is not None and abs(rate - setting) < 0.005:
            return True
        if locked:
            return ask_yes_no(
                self, "The video's frame rate isn't the analysis frame rate",
                f"The videos were recorded at {rate:g} fps, but the analysis frame "
                f"rate is locked at {setting:g} fps, so times will be off. Click Clear "
                "to change it. Track anyway?",
                yes="Track Anyway", no="Cancel")
        if ask_yes_no(
                self, "The video's frame rate isn't the frame rate setting",
                f"The videos were recorded at {rate:g} fps, but the Frame rate setting "
                f"is {self.fps_var.get()} fps. Use the videos' frame rate for the "
                "analysis?",
                yes=f"Use {rate:g} fps", no=f"Keep {self.fps_var.get()} fps"):
            self.fps_var.set(f"{rate:g}")
            self.config_data["fps"] = rate
        return True

    def _check_file_frame_rates(self, entries) -> bool:
        """Before the first Analyze: tracking files from this app record their
        video's frame rate. Offer it if the Frame rate box differs (times
        would be wrong otherwise). False if the user cancels."""
        if self.test_var.get() == ASR_TEST:
            return True      # startle uses each file's own frame times
        rates = {}
        for e in entries:
            try:
                fps = float(e.data.settings.get("Video_FPS", "nan"))
            except (TypeError, ValueError):
                continue
            if fps > 0:
                rates.setdefault(round(fps, 2), []).append(e)
        if not rates:
            return True
        try:
            setting = float(self.fps_var.get())
        except ValueError:
            setting = None
        if len(rates) > 1:
            lines = "\n".join(f"• {g[0].label}: {r:g} fps" for r, g in sorted(rates.items()))
            return ask_yes_no(
                self, "The files have different frame rates",
                "The selected files' videos weren't all recorded at the same frame "
                f"rate.\n\n{lines}\n\nThe analysis uses one frame rate for every file "
                f"({self.fps_var.get()} fps), so times for the others will be off. "
                "Analyze them in separate loads (Clear between them). Analyze anyway?",
                yes="Analyze Anyway", no="Cancel")
        rate = next(iter(rates))
        if setting is not None and abs(rate - setting) < 0.005:
            return True
        if ask_yes_no(
                self, "The video's frame rate isn't the frame rate setting",
                f"The tracking file says its video was recorded at {rate:g} fps, but the "
                f"Frame rate setting is {self.fps_var.get()} fps. Use {rate:g} fps for the "
                "analysis?", yes=f"Use {rate:g} fps", no=f"Keep {self.fps_var.get()} fps"):
            self.fps_var.set(f"{rate:g}")
        return True

    def _check_locked_frame_rate(self, entries) -> bool:
        """Later Analyzes of a load: the frame rate is already fixed, so warn
        about files whose own video was recorded at a different one (their
        times would be off). False if the user cancels."""
        if self.test_var.get() == ASR_TEST:
            return True
        used = float(self._fps_locked())
        off = []
        for e in entries:
            try:
                fps = float(e.data.settings.get("Video_FPS", "nan"))
            except (TypeError, ValueError):
                continue
            if fps > 0 and abs(fps - used) >= 0.005 and abs(round(fps, 2) - used) >= 0.005:
                off.append(f"• {e.label}: {fps:g} fps")
        if not off:
            return True
        return ask_yes_no(
            self, "Some files have a different frame rate",
            "Some files' videos weren't recorded at this load's frame rate "
            f"({used:g} fps), so their times would be off.\n\n" + "\n".join(off[:10])
            + ("\n…" if len(off) > 10 else "")
            + "\n\nAnalyze them in a separate load (Clear first). Analyze anyway?",
            yes="Analyze Anyway", no="Cancel")

    def cancel_tracking(self) -> None:
        if self._runner is not None:
            self._runner.cancel()
            self.track_cancel_btn.configure(state="disabled")
            self.track_text.configure(text="Stopping…")

    def _update_row(self, entry: FileEntry) -> None:
        """Refresh one file-list row's status (cheaper than rebuilding the list)."""
        for i, e in enumerate(self.files):
            if e is entry and self.file_tree.exists(str(i)):
                status, tag = self._file_status(e)
                self.file_tree.item(str(i), values=(e.label, e.kind, status),
                                    tags=(tag,) if tag else ())

    def _show_track_progress(self) -> None:
        groups = self._track_groups
        k = min(self._track_current, len(groups) - 1)
        e = groups[k][0]
        if self._runner is not None and self._runner.cancelled:
            return  # "Stopping…" stays until the worker stops
        what = ("making the reference image" if e.track_state == "reference"
                else f"{e.track_pct}%")
        self.track_text.configure(
            text=f"Tracking video {k + 1} of {len(groups)}: {e.label}, {what}")
        self.track_progress["value"] = e.track_pct

    def _poll_tracking(self) -> None:
        """Read the worker's messages (tkinter is only touched here, on the
        main thread)."""
        runner = self._runner
        if runner is None:
            return
        finished = False
        for msg in runner.poll():
            kind, i = msg[0], (msg[1] if len(msg) > 1 else None)
            group = self._track_groups[i] if i is not None else []
            if i is not None:
                self._track_current = i
            for e in group:
                if kind == "reference":
                    e.track_state = "reference"
                elif kind == "progress":
                    e.track_state = "tracking"
                    e.track_pct = int(100 * msg[2] / msg[3]) if msg[3] else 0
                elif kind == "done":
                    self._references.pop(msg[2].path, None)  # a new reference image
                    e.data, e.summary, e.bins = msg[2], None, None
                    e.track_state = ""
                    # The tracking file itself may be in the list too (added
                    # with its folder): it was just replaced, so it follows.
                    for other in self.files:
                        if (other.video is None and other is not e
                                and self._same_file_key(other.path)
                                == self._same_file_key(msg[2].path)):
                            other.data, other.summary, other.bins = msg[2], None, None
                elif kind == "failed":
                    e.track_state, e.track_error = "failed", msg[2]
                elif kind == "cancelled":
                    e.track_state = ""
                self._update_row(e)
            if kind == "done":
                self._track_results["done"] += 1
            elif kind == "failed":
                self._track_results["failed"].append(f"• {group[0].label}: {msg[2]}")
            elif kind == "cancelled":
                self._track_results["cancelled"] = True
            elif kind == "finished":
                finished = True
        if not finished:
            self._show_track_progress()
            self.after(150, self._poll_tracking)
            return
        self._finish_tracking()

    def _finish_tracking(self) -> None:
        results, groups = self._track_results, self._track_groups
        cancelled = results["cancelled"] or (self._runner is not None and self._runner.cancelled)
        left = len(groups) - results["done"] - len(results["failed"])
        for g in groups:
            for e in g:
                if e.track_state in ("queued", "reference", "tracking"):
                    e.track_state = ""
        self._runner = None
        self.track_bar.pack_forget()
        self._refresh()
        win = getattr(self, "_setup_win", None)
        if win is not None and win.winfo_exists() and win.step == "tracking":
            win._go("tracking")
        done = results["done"]
        self.status.set(f"Tracked {done} video(s)." + (" Stopped early." if cancelled else ""))
        if results["failed"]:
            show_warning(self, "Some videos couldn't be tracked",
                         f"{len(results['failed'])} video(s) couldn't be tracked.\n\n"
                         + "\n".join(results["failed"])
                         + ("\n\nThe others were tracked." if done else ""))
        if cancelled:
            show_info(self, "Tracking stopped",
                      f"Tracking stopped. {done} video(s) finished and are kept"
                      + (f"; {left} weren't tracked." if left else ".")
                      + " Select them and click Track to track them.")
        elif done:
            made = ("_MotionIndex.csv" if self.test_var.get() == ASR_TEST
                    else "_LocationOutput.csv and a _reference.png")
            show_info(self, "Tracking finished",
                      f"Tracking finished for {done} video(s). Each has a {made} next to "
                      "it. Select them and click Analyze.")
        self._warn_short_sessions([g[0] for g in groups])

    def _warn_short_sessions(self, entries) -> None:
        """A video that couldn't be read all the way to the end of its
        session was tracked only up to there: say so, with how much is
        missing, rather than leave a quietly shorter session."""
        short = []
        for e in entries:
            missing = int(getattr(e.data, "missing_at_end", 0) or 0) if e.data else 0
            fps = (e.video.info.fps if e.video is not None else 0) or 0
            # a few frames short at the very end of a file is normal
            if missing > max(MISSING_STAMPS_ALLOWED, fps):
                e.data.missing_at_end = 0       # say it once
                got = e.data.n_frames
                short.append(f"• {e.label}: {got:,} of {got + missing:,} frames tracked"
                             + (f" ({got / fps:.0f} s of {(got + missing) / fps:.0f} s)"
                                if fps else ""))
        if short:
            show_warning(self, "Some sessions are shorter than asked for",
                         "Some videos couldn't be read to the end of the session, so "
                         "their tracking stops early.\n\n" + "\n".join(short)
                         + "\n\nThe video may be damaged or shorter than its file "
                         "says. Converting it to a new .mp4 often repairs it; then "
                         "track it again.")

    def analyze(self) -> None:
        """Analyze the selected files."""
        self._flush_zone_change()
        if not self.files:
            show_info(self, "No files", "Add files first.")
            return
        targets = self._selected_entries()
        if not targets:
            show_info(self, "No file selected",
                      "Select a file in the list first, or click Select all.")
            return
        untracked = [e for e in targets if e.data is None]
        targets = [e for e in targets if e.data is not None]
        if untracked:
            names = "\n".join(f"• {e.label}" for e in untracked[:10])
            show_info(self, "Videos not tracked yet",
                      "These videos haven't been tracked, so they can't be analyzed "
                      f"yet.\n\n{names}\n\nSet them up and track them first.")
        if not targets:
            return
        # A startle file can't be analyzed as another test, or the reverse.
        startle = self.test_var.get() == ASR_TEST
        wrong = [e for e in targets if is_motion_file(e.data.path) != startle]
        if wrong:
            kind = "startle motion index files" if not startle else "tracking files"
            show_warning(self, "Some files don't fit this test",
                         f"Some files are {kind}, so they weren't analyzed as "
                         f"{self.test_var.get()}.\n\n{self._names(wrong)}\n\nChoose the "
                         "matching test, or track the video for this test.")
            targets = [e for e in targets if e not in wrong]
            if not targets:
                return

        if not self._locked():
            if not self._check_file_frame_rates(targets):
                return
            self._lock_in_settings()  # the first Analyze of a load sets them
        elif not self._check_locked_frame_rate([e for e in targets if not e.analyzed]):
            return
        targets = self._ready_to_analyze(targets)
        if not targets:
            self._update_status()
            return
        self._warn_overlaps(targets)

        self.config(cursor="watch")
        self.update_idletasks()
        try:
            failed = self._reanalyze(targets)
        finally:
            self.config(cursor="")
        self._refresh()
        done = [e for e in targets if e.analyzed]
        self._warn_shared(done)
        self._warn_lost(done)
        self._warn_repeats(done)
        if failed:
            show_warning(self, "Some files couldn't be analyzed",
                         "Some files couldn't be analyzed, so they have no results. "
                         "The others were analyzed.\n\n" + "\n".join(failed))

    def _warn_repeats(self, entries) -> None:
        """After Analyze (startle): flag videos where most frames are copies
        of the frame before. The camera ran slower than the video's frame
        rate, so there are few real frames around each stimulus."""
        if self.test_var.get() != ASR_TEST:
            return
        window = float(self.config_data["asr_startle_ms"])
        found = []
        for e in entries:
            rate = real_frame_rate(e.summary or {})
            if rate is None:
                continue
            frames, copies = e.summary["Frames"], e.summary["RepeatedFrames"]
            found.append(f"• {e.label}: {copies:,} of {frames:,} frames "
                         f"({100 * copies / frames:.0f}%) are repeats, leaving about "
                         f"{rate:.0f} real frames a second ({rate * window / 1000:.0f} "
                         f"in each {window:g} ms startle window)")
        if found:
            show_warning(
                self, "Most frames are repeats",
                "Most of the frames in some videos are repeats. The camera recorded "
                "slower than the video's frame rate, and the recording app filled in "
                "with copies of the frame before.\n\n" + "\n".join(found[:10])
                + ("\n…" if len(found) > 10 else "")
                + "\n\nThe times and stimulus frames are still right, and repeats are "
                "left out when the startle peak is found. With so few real frames, "
                "though, a brief startle can fall between them: amplitudes can come "
                "out low, and reaction times are only as fine as the gap between "
                "real frames. Boom Box on a Mac recorded this way at 1280x720 before "
                "version 1.3.4.")

    def _reanalyze(self, entries) -> list[str]:
        """Analyze each entry. One that fails is left without results and
        reported, as a line of text per failure; the rest carry on."""
        failed = []
        for e in entries:
            try:
                self._analyze_entry(e)
            except Exception as exc:
                traceback.print_exc()
                e.summary = e.bins = None
                failed.append(f"• {e.label}: {type(exc).__name__}: {exc}")
        return failed

    def _analyze_entry(self, e) -> None:
        """Work out one file's Summary row and Time Bins with this load's
        (locked) settings."""
        fps, bin_s = self._fps_locked(), self._bin_seconds_locked()
        test = self.test_var.get()
        if test == ASR_TEST:
            c = self.config_data
            summary, e.bins = asr_summary(e.data, float(c["asr_startle_ms"]),
                                          float(c["asr_baseline_ms"]), int(c["asr_block_trials"]))
            e.summary = order_summary(summary, test)
            return
        min_entry = self.config_data["min_entry_frames"]
        fill = bool(self.config_data["fill_gaps"])
        fill_max = int(self.config_data["fill_gaps_max_frames"])
        # Gap filling works on a copy; the file's own data is untouched.
        data = fill_gaps(e.data, fill_max) if fill else e.data
        roles = self._current_roles([e])
        # Per-region numbers use the test's entry rule, so they match
        # the test measures (Open Field: also its "same visit" gap).
        summary = summary_metrics(
            data, fps=fps, roles=roles, min_entry_frames=min_entry,
            min_gap_s=(self.config_data["min_seconds_between_entries"]
                       if test == "Open Field" else 0.0))
        # Record the settings behind these numbers in the row itself, so
        # an exported table shows how it was produced.
        settings = {"Test": test, "MinEntryFrames": min_entry,
                    "FillGaps": fill, "FillGapsMaxFrames": fill_max}
        bins = binned_metrics(data, fps=fps, bin_seconds=bin_s, roles=roles)
        test_bins = None
        if test == "Elevated Plus Maze":
            summary.update(epm_metrics(
                data, roles, fps=fps, min_entry_frames=min_entry,
            ))
            test_bins = epm_binned(data, roles, fps=fps, bin_seconds=bin_s,
                                   min_entry_frames=min_entry)
        elif test == "Open Field":
            gap = self.config_data["min_seconds_between_entries"]
            adj = self.config_data["min_center_seconds_adjoining"]
            smooth = self.config_data["speed_smoothing_frames"]
            summary.update(of_metrics(
                data, roles, fps=fps, min_entry_frames=min_entry,
                min_between_entries_s=gap, min_center_adjoining_s=adj,
                speed_smoothing_frames=smooth,
            ))
            test_bins = of_binned(
                data, roles, fps=fps, bin_seconds=bin_s,
                min_entry_frames=min_entry, min_between_entries_s=gap,
                min_center_adjoining_s=adj, speed_smoothing_frames=smooth,
            )
            settings.update({"MinBetweenCenterEntries_s": gap,
                             "MinCenterAdjoiningCrossing_s": adj,
                             "SpeedSmoothing_frames": smooth})
        if test == OBJECT_TEST:
            # From the saved manual scoring (ROADMAP §15); updated as it's scored.
            zone = self._zone_cm()
            scoring = load_scoring(e.data)
            summary.update(trial_summary(data, scoring, fps, zone, min_entry))
            zone_px = distance_px(data, zone)[0]
            test_bins = pd.DataFrame([{"Bin": b, **object_metrics(
                data, scoring, fps, zone_px, min_entry, lo, hi)}
                for b, lo, hi in bin_ranges(data.n_frames, fps, bin_s)])
            settings["ZoneDistance_cm"] = zone
        summary.update(settings)
        e.summary = order_summary(drop_duplicates(summary, roles, test), test)
        # The test's measures per bin go after the general bin columns.
        if test_bins is not None and not bins.empty:
            bins = bins.merge(test_bins, on="Bin", how="left")
        e.bins = order_bins(drop_duplicates(bins, roles, test), test)

    def _warn_shared(self, entries) -> None:
        """Only the center may share frames with other regions (those frames
        count for the center). Warn about frames in two other regions."""
        found = [(e.label, e.summary.get("SharedRegions", ""))
                 for e in entries if e.summary and e.summary.get("SharedRegionFrames")]
        if not found:
            return
        lines = "\n".join(f"• {name}: {what}" for name, what in found)
        show_warning(
            self, "Some regions share frames",
            "Some frames are in two regions at once, and neither is the center.\n\n"
            f"{lines}\n\nOnly the center should share a border with other regions (a "
            "shared point counts for the center). These frames were counted for the "
            "first region listed. Redraw the regions so they meet only at the center "
            "(for a video: Set up videos…, step 5, then Track again).")

    def _settings_sheet(self, entry, plot: dict):
        """Everything that produced this file's numbers and images."""
        row = entry.summary
        test = row.get("Test", self.test_var.get())
        if test == ASR_TEST:
            return settings_table({
                "Source": {"Source file": entry.path, "Video (File column)": entry.data.name,
                           "Motion index file": entry.data.path,
                           "Exported": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                           "Track Tamer version": VERSION},
                "Analysis": {"Test": test,
                             "Intensity threshold": row.get("IntensityThreshold"),
                             "Startle window (ms)": row.get("StartleWindow_ms"),
                             "Baseline window (ms)": row.get("BaselineWindow_ms"),
                             "Habituation block (trials)": row.get("HabituationBlock_trials"),
                             "Stimuli from": row.get("StimulusSource"),
                             "Pixels analyzed": row.get("AnalyzedPixels"),
                             "Frames": row.get("Frames"),
                             "Unreadable frames": row.get("UnreadableFrames")},
            })
        analysis = {
            "Test": test,
            "Frame rate (fps)": row.get("FPS"),
            "Min entry (frames)": row.get("MinEntryFrames"),
            "Fill gaps of unreadable frames": bool(row.get("FillGaps", False)),
            "Fill gaps up to (frames)": row.get("FillGapsMaxFrames"),
        }
        if test == "Open Field":
            analysis.update({
                "Min gap between center entries (s)": row.get("MinBetweenCenterEntries_s"),
                "Min center time, adjoining crossings (s)":
                    row.get("MinCenterAdjoiningCrossing_s"),
                "Speed smoothing (frames)": row.get("SpeedSmoothing_frames"),
            })
        roles = self._current_roles([entry])
        return settings_table({
            "Source": {
                "Source file": entry.path,
                "Video (File column)": entry.data.name,
                "Exported": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Track Tamer version": VERSION,
            },
            "Analysis": analysis,
            "Region roles": {r: ROLE_LABELS.get(k, k) or "Unassigned"
                             for r, k in roles.items()},
            "Time Bins": {"Bin size (s)": self._bin_seconds_locked()},
            "Path": {
                "Point size": plot["point_size"],
                "Transparency (alpha)": plot["alpha"],
                "Color by speed": plot["color_by_speed"],
                "Point color": plot["point_color"],
                "Region labels": plot["path_labels"],
                "Background": PATH_BACKGROUNDS[plot["path_background"]]
                + ("" if plot["path_background"] != "reference"
                   or self._reference(entry) is not None else " (none for this file)"),
            },
            "Heatmap": {
                "Bins": plot["heatmap_bins"],
                "Colormap": plot["heatmap_cmap"],
                "Background": HEATMAP_BACKGROUNDS[plot["heatmap_bg_mode"]]
                + ("" if plot["heatmap_bg_mode"] != "reference"
                   or self._reference(entry) is not None else " (none for this file)"),
                "Background color": plot["heatmap_bg_color"],
                "Region labels": plot["heatmap_labels"],
            },
            **self._tracking_sections(entry),
        })

    # Readable names for the tracking settings a file records (ezTrack's
    # columns, then this app's additions), in this order.
    TRACKING_LABELS = {
        "Method": "Animal is (dark / light / abs = either)",
        "Location_Thresh": "Threshold (percentile of differences kept)",
        "Use_Window": "Window on",
        "Window_Size": "Window size (full-size video px)",
        "Window_Weight": "Window weight",
        "Downsample": "Downsampling (1 = full size)",
        "Crop": "Crop (x0, y0, x1, y1 in downsampled px)",
        "Reference_Frames": "Frames in the reference image",
        "Exclusion_Shapes": "Exclusion shapes",
        "Start_Frame": "Start frame (video frame of the first row)",
        "Video_FPS": "Video frame rate (fps)",
        "Scale_px": "Scale length (px)",
        "Scale_cm": "Scale length (cm)",
        "Scale_cm_per_px": "cm per pixel",
    }

    def _tracking_sections(self, entry) -> dict:
        """The Settings sheet's tracking part: how the file was tracked (from
        its own recorded settings) and, for a video tracked in this load,
        its session and setup."""
        def plain(v):
            v = v.item() if hasattr(v, "item") else v
            if isinstance(v, float) and pd.isna(v):
                return "none"
            return v

        recorded = dict(entry.data.settings)
        tracking = {label: plain(recorded.pop(key)) for key, label in self.TRACKING_LABELS.items()
                    if key in recorded}
        tracking.update({k: plain(v) for k, v in recorded.items()})  # anything else
        if "Scale_cm_per_px" not in entry.data.settings:
            tracking["Scale"] = ("none (distances in px only)"
                                 if "Distance_cm" not in entry.data.df.columns
                                 else "from the tracking software")
        unreadable = int(entry.data.unreadable.sum())
        tracking["Frames in the file"] = entry.data.n_frames
        tracking["Unreadable video frames"] = unreadable
        sections = {"Tracking (recorded in the file)": tracking}

        v = entry.video
        if v is not None:
            fps = v.info.fps or 0
            sections["Video"] = {
                "Video file": v.path,
                "Frame size (px)": f"{v.info.width} x {v.info.height}",
                "Video length (frames)": v.info.frame_count,
                "Session start (s)": round(v.start / fps, 3) if fps else "",
                "Session length (min)": (round((v.end_frame - v.start) / fps / 60, 3)
                                         if fps else ""),
                "Regions drawn": ", ".join(v.regions) or "none",
                "Tracking file": entry.data.path,
            }
        return sections

    def _begin_export(self) -> None:
        self._exporting, self._export_cancel = True, False
        self.export_progress["value"] = 0
        self.export_cancel_btn.configure(state="normal")
        self.export_bar.pack(side=tk.BOTTOM, fill=tk.X, before=self.body)
        self._refresh()        # Analyze, Export, Track, Clear and Remove wait

    def _end_export(self) -> None:
        self._exporting = self._export_cancel = False
        self.export_bar.pack_forget()
        self._refresh()

    def cancel_export(self) -> None:
        if self._exporting:
            self._export_cancel = True
            self.export_cancel_btn.configure(state="disabled")
            self.export_text.configure(text="Stopping after this file…")

    def _export_paths(self, e) -> dict[str, str]:
        """Where a file's workbook and two images go (beside the file)."""
        if self.test_var.get() != ASR_TEST:
            return output_paths(e.path)
        base = os.path.splitext(e.path)[0]
        if base.endswith("_MotionIndex"):
            base = base[: -len("_MotionIndex")]
        return {"analysis": base + "_analysis.xlsx", "path": base + "_trace.png",
                "heatmap": base + "_aligned.png"}

    def export(self) -> None:
        """Write each selected, analyzed file's _analysis.xlsx, _path.png, and
        _heatmap.png next to its source CSV, overwriting existing files."""
        if self._exporting:
            return
        self._flush_zone_change()
        selected = self._selected_entries()
        if not selected:
            show_info(self, "No file selected",
                      "Select a file in the list first, or click Select all.")
            return
        targets = [e for e in selected if e.analyzed]
        if not targets:
            show_info(self, "Not analyzed yet",
                      "The selected files haven't been analyzed. Click Analyze "
                      "first, then export.")
            return
        # A file added twice writes to the same names, so export it once.
        seen, unique = set(), []
        for e in targets:
            key = self._same_file_key(e.path)
            if key not in seen:
                seen.add(key)
                unique.append(e)
        # Different files that would write the same workbook and images
        # (X.avi and X.mp4 both write X_analysis.xlsx) are left out and named.
        unique, clashing = self._split_same_results(
            unique, lambda e: self._export_paths(e)["analysis"], lambda e: e)
        if clashing:
            show_warning(self, "Some files would overwrite each other's results",
                         "Some files would write the same result files, so they "
                         f"weren't exported.\n\n{self._names(clashing)}\n\nRemove the "
                         "ones you don't want from the list (or rename one), then "
                         "export again.")
            if not unique:
                return

        plot = dict(self._plot_settings())  # the on-screen plot settings, now
        written, errors, workbooks = [], [], []
        self._begin_export()
        try:
            for k, e in enumerate(unique):
                # Between files the window catches up (it stays usable and
                # the Cancel button works) and the bar moves on.
                self.export_text.configure(text=f"Exporting {k + 1} of {len(unique)}: {e.label}")
                self.export_progress["value"] = 100 * k / len(unique)
                self.update()
                if self._export_cancel:
                    break
                out = self._export_paths(e)
                startle = self.test_var.get() == ASR_TEST
                try:
                    write_analysis_workbook(
                        out["analysis"], {k: v for k, v in e.summary.items()},
                        e.bins, self._settings_sheet(e, plot),
                        bins_sheet="Trials" if startle else "Time Bins",
                        interactions=(scoring_table(e.data, load_scoring(e.data),
                                                    self._fps_locked())
                                      if self.test_var.get() == OBJECT_TEST else None),
                    )
                    save_figure(self._path_fig(e, plot), out["path"])
                    save_figure(self._heat_fig(e, plot), out["heatmap"])
                    written.append(e)
                    workbooks.append(out["analysis"])
                except PermissionError:
                    errors.append(f"• {e.label}: a file is open in another program "
                                  "(e.g. the workbook in Excel). Close it and try again.")
                except Exception as exc:  # report and carry on with the rest
                    errors.append(f"• {e.label}: {exc}")
                    traceback.print_exc()
        finally:
            stopped = self._export_cancel
            self._end_export()
        if self._close_after_export:      # the window was closed during the export
            self._close_after_export = False
            self._on_close()
            return
        if stopped:
            left = len(unique) - len(written) - len(errors)
            show_info(self, "Export stopped",
                      f"Export stopped. {len(written)} file(s) were exported and are "
                      f"kept; {left} weren't exported.")

        skipped = len(selected) - len(targets)
        if written:
            folders = sorted({os.path.dirname(e.path) for e in written})
            where = folders[0] if len(folders) == 1 else f"{len(folders)} folders"
            self.status.set(f"Exported {len(written)} file(s) → {where}")
        if errors:
            show_warning(
                self, "Some files weren't exported",
                f"{len(errors)} file(s) couldn't be exported.\n\n" + "\n".join(errors),
            )
        if written:
            names = "\n".join(f"• {os.path.basename(w)}" for w in workbooks[:10])
            if len(written) > 10:
                names += f"\n…and {len(written) - 10} more"
            note = ("" if not skipped
                    else f"\n\n{skipped} selected file(s) weren't analyzed, so "
                         "they weren't exported.")
            show_info(
                self, "Export finished",
                f"Exported {len(written)} file(s), each next to its own file.\n\n"
                + ("Each has an _analysis.xlsx workbook (Summary, Trials, and Settings "
                   "sheets) plus _trace.png and _aligned.png images.\n\n"
                   if self.test_var.get() == ASR_TEST else
                   "Each has an _analysis.xlsx workbook (Summary, Time Bins, and "
                   "Settings sheets) plus _path.png and _heatmap.png images.\n\n")
                + f"{names}{note}",
            )


def main():
    app = TrackTamerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
