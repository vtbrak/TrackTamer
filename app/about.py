"""The About window: credits, citation, and license (GPL-3.0, from ezTrack)."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from dialogs import bold_font

from core.version import VERSION

# The project folder (this file is in its "app" folder); LICENSE is there.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CREDITS = (
    "Tracks rodents in video and analyzes the tracking (Elevated Plus Maze, "
    "Open Field and Object Recognition), turning it into summary measures, "
    "time bins, path plots, and heatmaps.\n\n"
    "Video tracking is adapted from ezTrack (github.com/denisecailab/ezTrack) "
    "by Zachary T. Pennington, Zhe Dong, Yu Feng, Lauren M. Vetere, Lucia "
    "Page-Harley, Tristan Shuman, and Denise J. Cai, used under the GNU General "
    "Public License v3.0. If you use the video tracking in published work, "
    "please cite:\n\n"
    "Pennington ZT, Dong Z, Feng Y, Vetere LM, Page-Harley L, Shuman T, Cai DJ "
    "(2019). ezTrack: An open-source video analysis pipeline for the "
    "investigation of animal behavior. Scientific Reports 9(1): 19979.\n\n"
    "This program is free software under the GNU General Public License v3.0: "
    "you can share and change it under those terms, and anyone who receives a "
    "copy must also be able to get its source code. It comes with no warranty."
)


class AboutDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("About Track Tamer")
        self.transient(parent)
        self.resizable(True, True)
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Track Tamer", font=bold_font(14)).pack(
            anchor="w")
        ttk.Label(frame, text=f"Version {VERSION}", foreground="gray").pack(
            anchor="w", pady=(0, 8))
        ttk.Label(frame, text=CREDITS, wraplength=460, justify=tk.LEFT).pack(anchor="w")

        self.license_frame = ttk.Frame(frame)
        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=(12, 0))
        self.license_btn = ttk.Button(buttons, text="Show license", command=self._toggle_license)
        self.license_btn.pack(side=tk.LEFT)
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side=tk.RIGHT)

        text = tk.Text(self.license_frame, wrap="word", height=18, width=70)
        scroll = ttk.Scrollbar(self.license_frame, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        try:
            with open(os.path.join(ROOT, "LICENSE"), encoding="utf-8") as f:
                text.insert("1.0", f.read())
        except OSError:
            text.insert("1.0", "The LICENSE file is missing. See "
                               "https://www.gnu.org/licenses/gpl-3.0.html")
        text.configure(state="disabled")
        self.bind("<Escape>", lambda _e: self.destroy())

    def _toggle_license(self) -> None:
        if self.license_frame.winfo_ismapped():
            self.license_frame.pack_forget()
            self.license_btn.configure(text="Show license")
        else:
            self.license_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0),
                                    before=self.license_btn.master)
            self.license_btn.configure(text="Hide license")
