"""Windows for videos that came without an info file.

A video recorded before the recording apps wrote info files (or whose info
file was lost) has nothing saying whose it is. When such videos are added,
`show_missing_info` lists them and asks whether there's an info file for
each (chosen with a file picker that opens in the video's own folder) and,
if not, offers to type the animal's information in (`ask_animal`). Either
way the video ends up with an info file of its own (ROADMAP §16; user,
2026-11-11).

Plain tkinter, the same on Mac and Windows.
"""

from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import ttk

from dialogs import bold_font, show_warning

# (info file field, label on screen, hint shown in gray). The labels are the
# words the recording apps use.
ANIMAL_FIELDS = (
    ("animal_id", "Animal ID", ""),
    ("sex", "Sex", "F, M or U (unknown)"),
    ("strain", "Strain / genotype", ""),
    ("dob", "Date of birth", "YYYY-MM-DD"),
    ("treatment", "Treatment / group", ""),
    ("cohort", "Cohort / litter", ""),
    ("date", "Trial date", "YYYY-MM-DD"),
    ("experimenter", "Experimenter", ""),
    ("trial_day", "Trial day", "1, 2, ... for a test over several days"),
    ("session_number", "Session that day", "1, 2, ... when there's more than one a day"),
    ("notes", "Notes", ""),
)
SEXES = ("", "F", "M", "U")


def check_animal(values: dict) -> str:
    """What's wrong with typed animal information, as one sentence; "" if
    nothing is. Every field may be blank."""
    for key, label in (("dob", "Date of birth"), ("date", "Trial date")):
        text = str(values.get(key) or "").strip()
        if text:
            try:
                date.fromisoformat(text)
            except ValueError:
                return (f"{label} isn't a date. Write it as year-month-day, "
                        "for example 2026-09-01.")
    if str(values.get("sex") or "").strip().upper() not in SEXES:
        return "Sex is F, M or U (unknown), or left blank."
    for key, label in (("trial_day", "Trial day"), ("session_number", "Session that day")):
        number = str(values.get(key) or "").strip()
        if number and not number.isdigit():
            return f"{label} is a whole number (1, 2, ...), or left blank."
    return ""


class _AnimalDialog(tk.Toplevel):
    """One video's animal information. `result` is {field: text}, or None if
    cancelled."""

    def __init__(self, parent, video: str, values: dict):
        super().__init__(parent)
        self.withdraw()
        self.title("Animal information")
        self.resizable(False, False)
        self.transient(parent)
        self.result = None
        body = ttk.Frame(self, padding=(16, 14, 16, 12))
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text=f"Animal information for {video}", font=bold_font(),
                  wraplength=460, justify=tk.LEFT).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(body, text="Fill in what you know; anything can be left blank. It's saved "
                  "in an info file beside the video and shown on the Experiment tab and "
                  "the exported workbook.", wraplength=460, justify=tk.LEFT).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(6, 10))
        self.vars = {}
        for n, (key, label, hint) in enumerate(ANIMAL_FIELDS, start=2):
            ttk.Label(body, text=label).grid(row=n, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=str(values.get(key) or ""))
            self.vars[key] = var
            if key == "sex":
                box = ttk.Combobox(body, textvariable=var, values=SEXES, width=6)
            else:
                box = ttk.Entry(body, textvariable=var, width=44 if key == "notes" else 24)
            box.grid(row=n, column=1, sticky="w", padx=(10, 8), pady=2)
            if n == 2:
                box.focus_set()
            ttk.Label(body, text=hint, foreground="gray").grid(row=n, column=2, sticky="w")
        buttons = ttk.Frame(body)
        buttons.grid(row=len(ANIMAL_FIELDS) + 2, column=0, columnspan=3, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(buttons, text="Save", command=self._ok).pack(side=tk.LEFT, padx=(6, 0))
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        _place_over(self, parent)

    def values(self) -> dict:
        out = {key: var.get().strip() for key, var in self.vars.items()}
        out["sex"] = out["sex"].upper()
        return out

    def _ok(self) -> None:
        values = self.values()
        problem = check_animal(values)
        if problem:
            show_warning(self, "Check the information", problem)
            return
        self.result = values
        self._finish()

    def _cancel(self) -> None:
        self.result = None
        self._finish()

    def _finish(self) -> None:
        self.grab_release()
        self.destroy()


def _place_over(window, parent) -> None:
    """Show a window over its parent, modal."""
    window.update_idletasks()
    w, h = window.winfo_reqwidth(), window.winfo_reqheight()
    if parent is not None and parent.winfo_viewable():
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 3
    else:
        x = (window.winfo_screenwidth() - w) // 2
        y = (window.winfo_screenheight() - h) // 3
    window.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    window.deiconify()
    window.lift()
    window.grab_set()


def ask_animal(parent, video: str, values: dict) -> dict | None:
    """Ask for one video's animal information, starting from `values`.
    Returns {field: text} (blank for what was left out), or None if cancelled."""
    dlg = _AnimalDialog(parent, video, values)
    dlg.wait_window()
    return dlg.result


class _MissingInfoWindow(tk.Toplevel):
    """The videos added without an info file, one per row, with what has been
    done for each. `choose(key)` and `animal(key)` are called for the selected
    row and return the row's new status text (None: nothing changed).
    `result` is True once Done is clicked, None if the window was closed
    (the videos are asked about again next time)."""

    def __init__(self, parent, rows, choose, animal):
        super().__init__(parent)
        self.withdraw()
        self.title("Videos without an info file")
        self.transient(parent)
        self.result = None
        self._choose, self._animal = choose, animal
        body = ttk.Frame(self, padding=(16, 14, 16, 12))
        body.pack(fill=tk.BOTH, expand=True)
        many = len(rows) > 1
        ttk.Label(body, text=("These videos have no info file." if many
                              else "This video has no info file."),
                  font=bold_font()).pack(anchor=tk.W)
        ttk.Label(body, wraplength=560, justify=tk.LEFT, text=(
            "An info file is what a recording app saves with a video: whose it is and what "
            "was run. Is there one for " + ("any of these" if many else "it") + "? Select "
            "the video and choose the file. If there isn't, you can add the animal's "
            "information here instead, or leave it blank. Either way, Track Tamer keeps "
            "an info file beside the video from now on.")).pack(anchor=tk.W, pady=(6, 10))
        self.tree = ttk.Treeview(body, columns=("video", "status"), show="headings",
                                 height=min(max(len(rows), 3), 10), selectmode="browse")
        self.tree.heading("video", text="Video")
        self.tree.heading("status", text="Information")
        self.tree.column("video", width=300, anchor="w")
        self.tree.column("status", width=260, anchor="w")
        for key, label in rows:
            self.tree.insert("", "end", iid=str(key), values=(label, "none yet"))
        self.tree.pack(fill=tk.BOTH, expand=True)
        if rows:
            self.tree.selection_set(str(rows[0][0]))
        buttons = ttk.Frame(body)
        buttons.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(buttons, text="Choose Info File…",
                   command=lambda: self._act(self._choose)).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Add Animal Information…",
                   command=lambda: self._act(self._animal)).pack(side=tk.LEFT, padx=(6, 0))
        done = ttk.Button(buttons, text="Done", command=self._done)
        done.pack(side=tk.RIGHT)
        done.focus_set()
        self.bind("<Escape>", lambda _e: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)
        _place_over(self, parent)

    def _act(self, action) -> None:
        picked = self.tree.selection()
        if not picked:
            return
        status = action(picked[0])
        if status:
            self.tree.set(picked[0], "status", status)
        self.lift()

    def _done(self) -> None:
        self.result = True
        self._finish()

    def _close(self) -> None:
        self.result = None
        self._finish()

    def _finish(self) -> None:
        self.grab_release()
        self.destroy()


def show_missing_info(parent, rows: list[tuple], choose, animal) -> bool | None:
    """List the videos that have no info file (`rows`: (key, video name)) and
    let the user choose an info file or add the animal's information for
    each. True when the user clicks Done; None if they close the window
    without it (ask again next time)."""
    dlg = _MissingInfoWindow(parent, rows, choose, animal)
    dlg.wait_window()
    return dlg.result
