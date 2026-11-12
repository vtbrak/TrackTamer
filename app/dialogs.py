"""Pop-up messages that look the same on macOS and Windows.

tkinter's built-in messagebox uses each system's native dialog, which styles
text differently (macOS bolds the whole message; Windows bolds nothing). These
dialogs are drawn with tkinter itself, so every pop-up shows its first
sentence in bold and the rest in regular type, on both systems.

API mirrors messagebox: show_info / show_warning / show_error / ask_yes_no,
plus ask_choice (several named buttons, where closing the window cancels)
and ask_side_by_side (two values per row, one ticked in each).

Also here, because they are the same kind of portability helper: `bold_font`
(bold text in the system's own font) and `fit_window` (a window size that
fits the screen).
"""

from __future__ import annotations

import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

_WRAP_PX = 460
_MAX_DETAIL_LINES = 30  # longer details (big file lists) are trimmed

# Accent strip on the left edge, by kind (no icons or emoji: they render
# differently between systems' fonts).
_ACCENTS = {"info": "#2f6fb3", "warning": "#c77700", "error": "#b3261e", "question": "#2f6fb3"}


def split_first_sentence(text: str) -> tuple[str, str]:
    """('First sentence.', 'everything after') — split at the first line break
    or at sentence-ending punctuation followed by a space."""
    text = text.strip()
    line, _, after_line = text.partition("\n")
    m = re.search(r"[.!?](\s)", line)
    if m:
        cut = m.start() + 1
        first, rest = line[:cut], line[cut:].lstrip() + ("\n" + after_line if after_line else "")
    else:
        first, rest = line, after_line
    return first.strip(), rest.strip()


def _trim(detail: str) -> str:
    lines = detail.splitlines()
    if len(lines) <= _MAX_DETAIL_LINES:
        return detail
    shown = lines[:_MAX_DETAIL_LINES]
    return "\n".join(shown + [f"…and {len(lines) - len(shown)} more lines"])


class _MessageDialog(tk.Toplevel):
    """Modal message window. `result` holds the label of the button pressed
    (or the cancel button's label if the window is closed)."""

    def __init__(self, parent, title, message, kind, buttons, default, cancel):
        super().__init__(parent)
        self.withdraw()  # position before showing, to avoid a flash at 0,0
        self.title(title)
        self.resizable(False, False)
        if parent is not None:
            self.transient(parent)
        self.result = cancel

        first, rest = split_first_sentence(message)
        base = tkfont.nametofont("TkDefaultFont")
        bold = base.copy()
        bold.configure(weight="bold")
        self._bold = bold  # keep a reference so the font isn't garbage-collected

        outer = tk.Frame(self)
        outer.pack(fill=tk.BOTH, expand=True)
        tk.Frame(outer, width=6, background=_ACCENTS[kind]).pack(side=tk.LEFT, fill=tk.Y)
        body = ttk.Frame(outer, padding=(16, 14, 16, 12))
        body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(body, text=first, font=bold, wraplength=_WRAP_PX,
                  justify=tk.LEFT).pack(anchor=tk.W)
        if rest:
            ttk.Label(body, text=_trim(rest), font=base, wraplength=_WRAP_PX,
                      justify=tk.LEFT).pack(anchor=tk.W, pady=(8, 0))

        row = ttk.Frame(body)
        row.pack(anchor=tk.E, pady=(14, 0))
        for label in buttons:
            btn = ttk.Button(row, text=label, command=lambda l=label: self._close(l))
            btn.pack(side=tk.LEFT, padx=(6, 0))
            if label == default:
                btn.focus_set()

        self.bind("<Return>", lambda _e: self._close(default))
        self.bind("<Escape>", lambda _e: self._close(cancel))
        self.protocol("WM_DELETE_WINDOW", lambda: self._close(cancel))

        self._place_over(parent)
        self.deiconify()
        self.lift()
        self.grab_set()

    def _place_over(self, parent) -> None:
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        if parent is not None and parent.winfo_viewable():
            x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - h) // 3
        else:
            x = (self.winfo_screenwidth() - w) // 2
            y = (self.winfo_screenheight() - h) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _close(self, label: str) -> None:
        self.result = label
        self.grab_release()
        self.destroy()


def _run(parent, title, message, kind, buttons, default, cancel) -> str:
    dlg = _MessageDialog(parent, title, message, kind, buttons, default, cancel)
    dlg.wait_window()
    return dlg.result


def show_info(parent, title: str, message: str) -> None:
    _run(parent, title, message, "info", ["OK"], "OK", "OK")


def show_warning(parent, title: str, message: str) -> None:
    _run(parent, title, message, "warning", ["OK"], "OK", "OK")


def show_error(parent, title: str, message: str) -> None:
    _run(parent, title, message, "error", ["OK"], "OK", "OK")


def ask_yes_no(parent, title: str, message: str, yes: str = "Yes", no: str = "No") -> bool:
    """True if the user picks `yes`. Closing the window or Escape counts as `no`."""
    return _run(parent, title, message, "question", [no, yes], yes, no) == yes


def ask_choice(parent, title: str, message: str, choices: list[str],
               default: str | None = None) -> str | None:
    """The button the user picked, from `choices` (shown left to right;
    Return picks `default`, the last one unless given). None if the window
    was closed or Escape pressed: use this instead of ask_yes_no when neither
    answer is safe to assume."""
    return _run(parent, title, message, "question", list(choices),
                default or choices[-1], None)


class _SideBySideDialog(tk.Toplevel):
    """Rows of two values side by side, each with a check box; exactly one
    is ticked in every row. `result` is the side ticked per row ("left" or
    "right"), or None if the window was cancelled or closed."""

    SCROLL_ROWS = 8     # more rows than this scroll

    def __init__(self, parent, title, message, rows, left_title, right_title,
                 preselect, ok, cancel):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.resizable(False, False)
        if parent is not None:
            self.transient(parent)
        self.result = None
        first, rest = split_first_sentence(message)
        bold = bold_font()

        outer = tk.Frame(self)
        outer.pack(fill=tk.BOTH, expand=True)
        tk.Frame(outer, width=6, background=_ACCENTS["question"]).pack(side=tk.LEFT, fill=tk.Y)
        body = ttk.Frame(outer, padding=(16, 14, 16, 12))
        body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        wrap = _WRAP_PX + 180
        ttk.Label(body, text=first, font=bold, wraplength=wrap,
                  justify=tk.LEFT).pack(anchor=tk.W)
        if rest:
            ttk.Label(body, text=_trim(rest), wraplength=wrap,
                      justify=tk.LEFT).pack(anchor=tk.W, pady=(8, 0))

        holder = ttk.Frame(body)
        holder.pack(anchor=tk.W, fill=tk.X, pady=(12, 0))
        if len(rows) > self.SCROLL_ROWS:
            canvas = tk.Canvas(holder, highlightthickness=0, height=300, width=wrap)
            bar = ttk.Scrollbar(holder, orient=tk.VERTICAL, command=canvas.yview)
            canvas.configure(yscrollcommand=bar.set)
            bar.pack(side=tk.RIGHT, fill=tk.Y)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            table = ttk.Frame(canvas)
            canvas.create_window((0, 0), window=table, anchor="nw")
            table.bind("<Configure>",
                       lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        else:
            table = ttk.Frame(holder)
            table.pack(anchor=tk.W)
        ttk.Label(table, text=left_title, font=bold).grid(row=0, column=1, sticky="w",
                                                          padx=(14, 0))
        ttk.Label(table, text=right_title, font=bold).grid(row=0, column=2, sticky="w",
                                                           padx=(14, 0))
        self.vars = []      # per row: (left ticked, right ticked)
        for n, (label, detail, left, right) in enumerate(rows, start=1):
            name = ttk.Frame(table)
            name.grid(row=n, column=0, sticky="nw", pady=(8, 0))
            ttk.Label(name, text=label, font=bold).pack(anchor=tk.W)
            if detail:
                ttk.Label(name, text=detail, foreground="gray", wraplength=200,
                          justify=tk.LEFT).pack(anchor=tk.W)
            pair = (tk.BooleanVar(value=preselect == "left"),
                    tk.BooleanVar(value=preselect != "left"))
            self.vars.append(pair)
            for side, text in enumerate((left, right)):
                box = tk.Checkbutton(      # tk, not ttk: its text wraps
                    table, text=str(text), variable=pair[side], wraplength=210,
                    justify=tk.LEFT, anchor="w",
                    command=lambda pair=pair, side=side: self._tick(pair, side))
                box.grid(row=n, column=1 + side, sticky="nw", padx=(10, 0), pady=(6, 0))

        buttons = ttk.Frame(body)
        buttons.pack(anchor=tk.E, pady=(14, 0))
        ttk.Button(buttons, text=cancel, command=self._cancel).pack(side=tk.LEFT, padx=(6, 0))
        apply = ttk.Button(buttons, text=ok, command=self._ok)
        apply.pack(side=tk.LEFT, padx=(6, 0))
        apply.focus_set()
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        _MessageDialog._place_over(self, parent)
        self.deiconify()
        self.lift()
        self.grab_set()

    @staticmethod
    def _tick(pair, side: int) -> None:
        """One box per row is always ticked: ticking one unticks the other,
        and the ticked one can't be unticked on its own."""
        pair[side].set(True)
        pair[1 - side].set(False)

    def choices(self) -> list[str]:
        return ["left" if left.get() else "right" for left, _ in self.vars]

    def _ok(self) -> None:
        self.result = self.choices()
        self._finish()

    def _cancel(self) -> None:
        self.result = None
        self._finish()

    def _finish(self) -> None:
        self.grab_release()
        self.destroy()


def ask_side_by_side(parent, title: str, message: str, rows: list[tuple],
                     left_title: str, right_title: str, preselect: str = "right",
                     ok: str = "Use Ticked", cancel: str = "Cancel") -> list[str] | None:
    """Show values that disagree side by side and let the user tick the one
    that's right in each row. `rows` are (label, detail, left value, right
    value); `preselect` is the side ticked to begin with. Returns "left" or
    "right" for each row, or None if the window was cancelled or closed
    (nothing was chosen)."""
    dlg = _SideBySideDialog(parent, title, message, rows, left_title, right_title,
                            preselect, ok, cancel)
    dlg.wait_window()
    return dlg.result


_bold_fonts: dict = {}


def bold_font(size: int | None = None) -> tkfont.Font:
    """The system's default font in bold, at `size` points (its own size if
    not given). A copy of the named font, so it's the right typeface on both
    Mac and Windows; writing ("TkDefaultFont", 11, "bold") instead names a
    typeface that doesn't exist, and each system substitutes its own."""
    key = (id(tk._default_root), size)
    if key not in _bold_fonts:
        font = tkfont.nametofont("TkDefaultFont").copy()
        font.configure(weight="bold")
        if size:
            font.configure(size=size)
        _bold_fonts[key] = font
    return _bold_fonts[key]


def fit_window(window, width: int, height: int) -> None:
    """Size a window `width` x `height`, or smaller if the screen is smaller
    (a laptop at 1366 x 768, or Windows set to enlarge everything), so the
    buttons along its bottom edge can't start off the screen."""
    width = min(width, max(400, window.winfo_screenwidth() - 40))
    height = min(height, max(300, window.winfo_screenheight() - 110))
    window.geometry(f"{width}x{height}")
