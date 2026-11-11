"""Hover tooltips for tkinter widgets (tkinter has none built in).

Plain Toplevel + Label, so it looks and behaves the same on macOS and Windows.
The text can be a string or a function, so a tooltip can change with the app's
state (e.g. "locked until Clear").
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

_DELAY_MS = 500
_WRAP_PX = 320


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str | Callable[[], str]):
        self.widget = widget
        self.text = text
        self._job = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _current_text(self) -> str:
        return self.text() if callable(self.text) else self.text

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._job = self.widget.after(_DELAY_MS, self._show)

    def _cancel(self) -> None:
        if self._job is not None:
            self.widget.after_cancel(self._job)
            self._job = None

    def _show(self) -> None:
        self._job = None
        text = self._current_text()
        if not text or self._tip is not None:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)  # no title bar
        tip.wm_attributes("-topmost", True)  # never hidden behind the window
        tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tip, text=text, justify=tk.LEFT, wraplength=_WRAP_PX,
            background="#ffffe0", foreground="#000000",
            relief=tk.SOLID, borderwidth=1, padx=6, pady=4,
        ).pack()
        self._tip = tip

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None
