"""Pop-up messages that look the same on macOS and Windows.

tkinter's built-in messagebox uses each system's native dialog, which styles
text differently (macOS bolds the whole message; Windows bolds nothing). These
dialogs are drawn with tkinter itself, so every pop-up shows its first
sentence in bold and the rest in regular type, on both systems.

API mirrors messagebox: show_info / show_warning / show_error / ask_yes_no.
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
