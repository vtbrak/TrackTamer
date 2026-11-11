"""'Match regions' dialog: assign a role to each region found in the data.

Opens automatically when a loaded file's region names can't all be matched to
roles for the chosen test (unknown names, or a required role missing), and on
demand from the Regions… button. Shows a small labeled map so the user can see
which name is which area.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from core import ROLE_LABELS, auto_role, check_roles, regions_figure

_LABEL_TO_ROLE = {label: key for key, label in ROLE_LABELS.items()}


class RegionDialog(tk.Toplevel):
    """Modal dialog. After wait_window(), `result` is {region: role} or None
    if the user cancelled.

    regions: [(name, percent_of_session)] in display order.
    roles:   current {name: role}; preview: a TrackingData for the map (optional).
    """

    def __init__(self, parent, test_type, regions, roles, preview=None, reason=""):
        super().__init__(parent)
        self.title("Match regions")
        self.transient(parent)
        self.resizable(False, False)
        self.test_type = test_type
        self.result = None
        self._vars: dict[str, tk.StringVar] = {}

        body = ttk.Frame(self, padding=12)
        body.pack(fill=tk.BOTH, expand=True)

        intro = (
            f"Test: {test_type}\n"
            "Choose what each region in the file represents. "
            "Your choices are saved and reused for files with the same region names."
        )
        if reason:
            intro = f"{reason}\n\n{intro}"
        ttk.Label(body, text=intro, wraplength=640, justify=tk.LEFT).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        table = ttk.Frame(body)
        table.grid(row=1, column=0, sticky="nw", padx=(0, 16))
        for col, head in enumerate(("Region", "% of session", "Suggested", "Role")):
            ttk.Label(table, text=head, font=("TkDefaultFont", 0, "bold")).grid(
                row=0, column=col, sticky="w", padx=4, pady=(0, 4)
            )
        for i, (name, pct) in enumerate(regions, start=1):
            ttk.Label(table, text=name).grid(row=i, column=0, sticky="w", padx=4)
            ttk.Label(table, text=f"{pct:.1f}%").grid(row=i, column=1, sticky="e", padx=4)
            ttk.Label(table, text=ROLE_LABELS[auto_role(name)], foreground="gray").grid(
                row=i, column=2, sticky="w", padx=4
            )
            var = tk.StringVar(value=ROLE_LABELS[roles.get(name, "")])
            ttk.Combobox(
                table, textvariable=var, values=list(ROLE_LABELS.values()),
                state="readonly", width=12,
            ).grid(row=i, column=3, sticky="w", padx=4, pady=2)
            var.trace_add("write", lambda *_: self._refresh())
            self._vars[name] = var

        self._map_canvas = None
        self._preview = preview
        if preview is not None:
            self._map_frame = ttk.Frame(body)
            self._map_frame.grid(row=1, column=1, sticky="n")

        self.check_var = tk.StringVar()
        self.check_label = ttk.Label(body, textvariable=self.check_var, wraplength=640)
        self.check_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Reset to suggested", command=self._reset).pack(
            side=tk.LEFT, padx=(0, 16)
        )
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Save", command=self._save).pack(side=tk.LEFT, padx=(6, 0))

        self.bind("<Escape>", lambda _e: self.destroy())
        self._refresh()
        self.grab_set()

    def roles(self) -> dict[str, str]:
        return {name: _LABEL_TO_ROLE[var.get()] for name, var in self._vars.items()}

    def _refresh(self) -> None:
        roles = self.roles()
        problems = check_roles(self.test_type, roles)
        if problems:
            self.check_var.set("⚠ " + "; ".join(problems))
            self.check_label.configure(foreground="#b35900")
        else:
            self.check_var.set(f"✓ Ready for {self.test_type}.")
            self.check_label.configure(foreground="#2e7d32")
        if self._preview is not None:
            self._draw_map(roles)

    def _draw_map(self, roles) -> None:
        if self._map_canvas is not None:
            self._map_canvas.get_tk_widget().destroy()
        labels = {r: ROLE_LABELS[k] if k else "?" for r, k in roles.items()}
        canvas = FigureCanvasTkAgg(regions_figure(self._preview, labels), master=self._map_frame)
        canvas.draw()
        canvas.get_tk_widget().pack()
        self._map_canvas = canvas

    def _reset(self) -> None:
        for name, var in self._vars.items():
            var.set(ROLE_LABELS[auto_role(name)])

    def _save(self) -> None:
        self.result = self.roles()
        self.destroy()
