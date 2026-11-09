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
) -> None:
    """One workbook, each table on its own sheet. Blank cells mean a value
    couldn't be computed (e.g. a latency to a region never entered)."""
    sheets = {
        "Summary": pd.DataFrame([summary]),
        bins_sheet: bins if bins is not None else pd.DataFrame(),
        "Settings": settings,
    }
    if interactions is not None:   # Object Recognition: the logged scoring
        sheets = {"Summary": sheets["Summary"], "Interactions": interactions,
                  bins_sheet: sheets[bins_sheet], "Settings": settings}
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
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
    fig.savefig(png_path, dpi=IMAGE_DPI, transparent=not getattr(fig, "opaque", False),
                bbox_inches="tight", pad_inches=0.1)


def settings_table(sections: dict[str, dict]) -> pd.DataFrame:
    """{section: {setting: value}} -> a Section / Setting / Value table."""
    def show(value):
        # On/off settings read as Yes/No (Excel would show them as 1/0 here).
        if isinstance(value, (bool, np.bool_)):
            return "Yes" if value else "No"
        return value

    rows = [
        {"Section": section, "Setting": name, "Value": show(value)}
        for section, items in sections.items()
        for name, value in items.items()
    ]
    return pd.DataFrame(rows, columns=["Section", "Setting", "Value"])
