"""Writing a file's results to disk (GUI-free).

For each analyzed file, three outputs go next to its source CSV, named after
it, overwriting anything already there:

  <name>_analysis.xlsx   sheets: Summary (its row), Time Bins, Settings
  <name>_path.png        the Path plot
  <name>_heatmap.png     the Heatmap (cells never entered stay transparent
                         unless the background option is on)
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from .safe_write import replacing

IMAGE_DPI = 200  # the default 5 x 4.5 in figure saves at 1000 x 900 px


def output_paths(source_path: str) -> dict[str, str]:
    """Where a source CSV's outputs go: alongside it, with suffixes added."""
    base = os.path.splitext(source_path)[0]
    return {
        "analysis": base + "_analysis.xlsx",
        "path": base + "_path.png",
        "heatmap": base + "_heatmap.png",
    }


def write_analysis_workbook(
    xlsx_path: str, summary: dict, bins: pd.DataFrame | None, settings: pd.DataFrame,
    interactions: pd.DataFrame | None = None, bins_sheet: str = "Time Bins",
    experiment: pd.DataFrame | None = None, setup: pd.DataFrame | None = None,
) -> None:
    """One workbook, each table on its own sheet: Experiment (the animal and
    the task, listed down the page), Summary (its row), Interactions (Object
    Recognition's logged scoring), Time Bins, Settings, and Setup (the crop,
    regions, exclusions and scale as numbers: a backup of the video's info
    file). Blank cells mean a value wasn't recorded or couldn't be computed
    (e.g. a latency to a region never entered)."""
    sheets = {
        "Experiment": experiment,
        "Summary": pd.DataFrame([summary]),
        "Interactions": interactions,
        bins_sheet: bins if bins is not None else pd.DataFrame(),
        "Settings": settings,
        "Setup": setup,
    }
    sheets = {name: table for name, table in sheets.items() if table is not None}
    # Written whole before it replaces an earlier workbook (`replacing`).
    with replacing(xlsx_path) as tmp:
        with pd.ExcelWriter(tmp, engine="openpyxl") as writer:
            for name, df in sheets.items():
                df.to_excel(writer, sheet_name=name, index=False)
                _fit_columns(writer.sheets[name], df)


def _fit_columns(sheet, df: pd.DataFrame) -> None:
    """Rough auto-width so headers and values are readable when opened."""
    for i, col in enumerate(df.columns, start=1):
        values = [str(col)] + [str(v) for v in df[col].dropna().head(200)]
        width = min(60, max(8, max(len(v) for v in values) + 2))
        sheet.column_dimensions[sheet.cell(row=1, column=i).column_letter].width = width


def save_figure(fig: Figure, png_path: str) -> None:
    """Save a plot as PNG, with a transparent background unless it's drawn
    over a reference image (`fig.opaque`)."""
    FigureCanvasAgg(fig)  # figures built for the GUI may not have a canvas yet
    # "tight" sizes the image to everything drawn (labels, colorbar, region
    # names outside the plot), so nothing is clipped at the edges.
    with replacing(png_path) as tmp:
        fig.savefig(tmp, dpi=IMAGE_DPI, transparent=not getattr(fig, "opaque", False),
                    bbox_inches="tight", pad_inches=0.1)


def settings_table(sections: dict[str, dict], heading: str = "Setting") -> pd.DataFrame:
    """{section: {setting: value}} -> a Section / Setting / Value table
    (`heading` names the middle column: "Field" on the Experiment sheet)."""
    def show(value):
        # On/off settings read as Yes/No (Excel would show them as 1/0 here).
        if isinstance(value, (bool, np.bool_)):
            return "Yes" if value else "No"
        return value

    rows = [
        {"Section": section, heading: name, "Value": show(value)}
        for section, items in sections.items()
        for name, value in items.items()
    ]
    return pd.DataFrame(rows, columns=["Section", heading, "Value"])


def _points(shape: dict) -> str:
    """A drawn shape's corners as "x, y; x, y; ..." (one decimal)."""
    return "; ".join(f"{x:.1f}, {y:.1f}" for x, y in zip(shape["xs"], shape["ys"]))


def setup_sections(saved: dict) -> dict[str, dict]:
    """A video's setup (`VideoSetup.to_saved`) as {section: {setting: value}}
    for the Setup sheet. Positions are in full-size video pixels."""
    number = lambda v: "" if v is None else v          # noqa: E731
    size = saved.get("frame_size") or ["", ""]
    sections = {"Session": {
        "Frame size (px)": f"{size[0]} x {size[1]}",
        "Start frame": number(saved.get("start_frame")),
        "End frame (first frame after the session)": number(saved.get("end_frame")),
        "Session length (s)": number(saved.get("length_s")),
        "Positions below are in": "full-size video pixels (x, y)",
    }}
    crop = saved.get("crop")
    sections["Crop"] = {"Crop (x0, y0, x1, y1)":
                        ", ".join(f"{v:.1f}" for v in crop) if crop else "none"}
    regions = saved.get("regions") or {}
    sections["Regions"] = ({name: _points(shape) for name, shape in regions.items()}
                           or {"Regions": "none"})
    shapes = saved.get("exclusions") or []
    sections["Exclusions"] = ({f"Shape {n}": _points(shape) for n, shape in enumerate(shapes, 1)}
                              or {"Exclusion shapes": "none"})
    points = saved.get("scale_points") or []
    sections["Scale"] = {
        "Scale points": "; ".join(f"{x:.1f}, {y:.1f}" for x, y in points) or "none",
        "Scale length (cm)": number(saved.get("scale_cm")),
    }
    circles, kinds = saved.get("objects") or {}, saved.get("object_kinds") or {}
    if circles:
        sections["Objects"] = {
            name: (f"center {c[0]:.1f}, {c[1]:.1f}; radius {c[2]:.1f}; "
                   f"{kinds.get(name, 'Familiar')}")
            for name, c in circles.items()}
    if saved.get("stimulus_frames"):
        sections["Stimuli (typed)"] = {
            "Video frames": ", ".join(str(f) for f in saved["stimulus_frames"])}
    return sections
