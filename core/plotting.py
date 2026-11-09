"""
Plot builders for a tracking file.

These return matplotlib Figures so the caller (GUI or script) decides whether
to embed, show, or save them. No plt.show() here.
"""

from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.path import Path

from .loader import TrackingData, parse_roi_coordinates
from .regions import match_polygons

# Default figure size (inches). Embedded figures stretch to fill their tab;
# constrained layout keeps titles and axis labels inside the canvas at any size.
FIGSIZE = (5, 4.5)


REFERENCE_ROI_COLOR = "#ffd23f"  # ROI lines on a reference image (gray on gray is hard to see)


def _draw_reference(ax, reference: np.ndarray) -> tuple[float, float, float, float]:
    """The arena's reference image in gray behind the plot, in the same pixels
    as X/Y (pixel i covers i-0.5..i+0.5, top of the video at the top).
    Returns its extent (left, right, bottom, top)."""
    h, w = reference.shape[:2]
    extent = (-0.5, w - 0.5, h - 0.5, -0.5)
    ax.imshow(reference, cmap="gray", vmin=0, vmax=255, extent=extent, zorder=0,
              interpolation="antialiased")
    return extent


def _show_whole(ax, extent) -> None:
    """Widen the view to at least the whole reference image."""
    left, right, bottom, top = extent
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()  # inverted: y0 is the bottom (larger)
    ax.set_xlim(min(x0, x1, left), max(x0, x1, right))
    ax.set_ylim(max(y0, y1, bottom), min(y0, y1, top))


def _draw_rois(ax, data: TrackingData, labels: bool = True, color: str = "0.6") -> None:
    """Overlay the ROI polygon outlines (closed), each labeled with its region."""
    if "ROI_coordinates" not in data.df.columns or not len(data.df):
        return
    rois = parse_roi_coordinates(data.df["ROI_coordinates"].iloc[0])
    for xs, ys in zip(rois.get("xs", []), rois.get("ys", [])):
        if xs and ys:
            ax.plot(list(xs) + [xs[0]], list(ys) + [ys[0]],
                    color=color, linewidth=1.0, zorder=1)
    if not labels:
        return
    for region, (cx, cy) in _label_points(match_polygons(data)).items():
        ax.text(cx, cy, region, ha="center", va="center", fontsize=9, zorder=4,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="0.5", alpha=0.75))


def _draw_objects(ax, data: TrackingData, zone_cm: float | None, labels: bool = True,
                  color: str = "0.4") -> None:
    """Object Recognition: each object's circle (solid) and its zone (dashed),
    labeled above the zone with its name and type (ROADMAP §15)."""
    from matplotlib.patches import Circle
    from .objects import distance_px, file_objects
    objects = file_objects(data)
    if not objects:
        return
    zone = distance_px(data, zone_cm)[0] if zone_cm is not None else 0.0
    for o in objects:
        ax.add_patch(Circle((o.x, o.y), o.r, fill=False, edgecolor=color, linewidth=1.5,
                            zorder=3))
        if zone:
            ax.add_patch(Circle((o.x, o.y), o.r + zone, fill=False, edgecolor=color,
                                linewidth=1.0, linestyle="--", zorder=3))
        if labels:
            ax.text(o.x, o.y - o.r - zone - 4, f"{o.name} ({o.kind.lower()})", ha="center",
                    va="bottom", fontsize=9, zorder=4,
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="0.5", alpha=0.75))


def _object_extent(data: TrackingData) -> list[np.ndarray]:
    """Points around each object's circle (so the heatmap grid covers them)."""
    from .objects import file_objects
    return [np.array([[o.x - o.r, o.y - o.r], [o.x + o.r, o.y + o.r]])
            for o in file_objects(data)]


def _label_points(polys: dict[str, tuple[list, list]]) -> dict[str, tuple[float, float]]:
    """Where to put each region's label: its middle, unless that middle falls
    inside another region's polygon (e.g. an open field's whole-arena
    'peripheral' contains 'center'), in which case near its top edge."""
    def area(xs, ys):  # shoelace formula
        return 0.5 * abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1)))

    shapes = {r: Path(np.column_stack(p)) for r, p in polys.items()}
    areas = {r: area(np.asarray(xs, float), np.asarray(ys, float))
             for r, (xs, ys) in polys.items()}
    points = {}
    for region, (xs, ys) in polys.items():
        # Middle of the distinct vertices (some files repeat a point).
        pts = np.unique(np.column_stack([xs, ys]), axis=0)
        cx, cy = pts.mean(axis=0)
        # Only the larger, enclosing shape moves its label out of the way.
        if any(shape.contains_point((cx, cy)) and areas[other] < areas[region]
               for other, shape in shapes.items() if other != region):
            top, bottom = pts[:, 1].min(), pts[:, 1].max()
            cy = top + 0.07 * (bottom - top)  # image coords: smaller y is higher
        points[region] = (cx, cy)
    return points


def _outside_labels(ax, polys: dict[str, tuple[list, list]], boxed: bool = False) -> None:
    """Label each region *outside* every ROI, with a thin line to its region,
    so labels never cover the data (used on the heatmap).

    Each label sits just past the outermost ROI edge, in the direction of its
    region from the arena's middle (EPM arms: past the arm's end). A region at
    the middle (EPM mid, open-field center) points out along a free diagonal.
    The axes are widened to make room.
    """
    if not polys:
        return
    anchors = _label_points(polys)
    all_pts = np.vstack([np.column_stack(p) for p in polys.values()]).astype(float)
    lo, hi = all_pts.min(axis=0), all_pts.max(axis=0)
    mid, size = (lo + hi) / 2, float(max(hi - lo))
    margin = 0.08 * size

    used: list[float] = []  # angles already taken (radians)

    def free_angle(angle: float) -> float:
        # Step around until no other label is within ~25 degrees.
        for _ in range(12):
            if all(abs(np.angle(np.exp(1j * (angle - u)))) > 0.44 for u in used):
                break
            angle += np.pi / 6
        used.append(angle)
        return angle

    placed = []
    # Off-center regions first, so central ones take whatever diagonal is free.
    order = sorted(anchors, key=lambda r: -np.hypot(*(np.subtract(anchors[r], mid))))
    for region in order:
        anchor = np.asarray(anchors[region], float)
        offset = anchor - mid
        if np.hypot(*offset) < 0.15 * size:
            angle = -np.pi / 4  # up-right in image coords (smaller y is higher)
        else:
            angle = float(np.arctan2(offset[1], offset[0]))
        angle = free_angle(angle)
        direction = np.array([np.cos(angle), np.sin(angle)])
        # Just past the farthest ROI point in this direction.
        reach = float(np.max((all_pts - mid) @ direction))
        pos = mid + direction * (reach + margin)
        placed.append(pos)
        # End the line where it first meets the region's edge, not at its
        # middle, so the line doesn't run across the data inside the region.
        shape = Path(np.column_stack(polys[region]).astype(float))
        along = pos + np.linspace(0, 1, 400)[:, None] * (anchor - pos)
        inside = np.flatnonzero(shape.contains_points(along))
        tip = along[inside[0]] if len(inside) else anchor
        ax.annotate(
            region, xy=tip, xytext=pos, fontsize=9, zorder=5,
            ha="left" if direction[0] > 0.3 else "right" if direction[0] < -0.3 else "center",
            va="top" if direction[1] > 0.3 else "bottom" if direction[1] < -0.3 else "center",
            arrowprops=dict(arrowstyle="-", color="0.35", linewidth=0.8),
            annotation_clip=False,
            bbox=(dict(boxstyle="round,pad=0.2", fc="white", ec="0.5", alpha=0.8)
                  if boxed else None),
        )

    # Widen the view so the labels (and a little text room) are on the plot.
    pts = np.vstack([all_pts, np.array(placed)])
    pad = 0.12 * size
    (x0, y0), (x1, y1) = pts.min(axis=0) - pad, pts.max(axis=0) + pad
    xl, yl = ax.get_xlim(), ax.get_ylim()
    ax.set_xlim(min(x0, *xl), max(x1, *xl))
    ax.set_ylim(max(y1, *yl), min(y0, *yl))  # keep y inverted (image coords)


def path_figure(
    data: TrackingData,
    color_by_speed: bool = True,
    point_size: float = 4,
    point_color: str = "#1f77b4",
    alpha: float = 0.8,
    reference: np.ndarray | None = None,
    labels: bool = True,
    zone_cm: float | None = None,
) -> Figure:
    """Trajectory plot of X/Y points, colored by speed or a single solid color.
    With `reference` (the arena's reference image), the plot sits on it and
    shows the whole image."""
    df = data.df
    fig = Figure(figsize=FIGSIZE, dpi=100, layout="constrained")
    fig.opaque = reference is not None  # export: not transparent over an image
    ax = fig.add_subplot(111)

    extent = _draw_reference(ax, reference) if reference is not None else None
    _draw_rois(ax, data, labels=labels, color=REFERENCE_ROI_COLOR if extent else "0.6")
    _draw_objects(ax, data, zone_cm, labels=labels,
                  color=REFERENCE_ROI_COLOR if extent else "0.3")

    x = df["X"].to_numpy()
    y = df["Y"].to_numpy()

    if color_by_speed and "Distance_px" in df.columns:
        speed = df["Distance_px"].to_numpy()
        sc = ax.scatter(
            x, y, c=speed, cmap="viridis", s=point_size, alpha=alpha,
            edgecolors="none", zorder=2,
        )
        fig.colorbar(sc, ax=ax, label="Speed (px/frame)", shrink=0.8)
    else:
        ax.scatter(
            x, y, color=point_color, s=point_size, alpha=alpha,
            edgecolors="none", zorder=2,
        )

    ax.set_title(f"Path — {data.name}")
    ax.set_xlabel("X (px)")
    ax.set_ylabel("Y (px)")
    if extent:
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])  # image coordinates: origin top-left
        ax.set_aspect("equal", adjustable="box")
    else:
        ax.set_aspect("equal", adjustable="datalim")
        ax.invert_yaxis()  # image coordinates: origin top-left
    return fig


def regions_figure(data: TrackingData, roles: dict[str, str] | None = None) -> Figure:
    """Small map of the ROI polygons, labeled by region (and role, if given),
    over a faint path — so a user can see which name is which area."""
    fig = Figure(figsize=(4, 4), dpi=100, layout="constrained")
    ax = fig.add_subplot(111)
    df = data.df
    ax.scatter(df["X"], df["Y"], s=1, color="0.8", edgecolors="none", zorder=0)
    _draw_rois(ax, data, labels=False)
    for region, (cx, cy) in _label_points(match_polygons(data)).items():
        text = region if not roles else f"{region}\n{roles.get(region) or '?'}"
        ax.text(cx, cy, text, ha="center", va="center", fontsize=8, zorder=4,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="0.5", alpha=0.85))
    ax.set_aspect("equal", adjustable="datalim")
    ax.invert_yaxis()
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("Regions in this file", fontsize=10)
    return fig


def heatmap_figure(
    data: TrackingData,
    bins: int = 50,
    cmap: str = "inferno",
    background: str | None = None,
    reference: np.ndarray | None = None,
    labels: bool = True,
    zone_cm: float | None = None,
) -> Figure:
    """Occupancy heatmap: where the animal spent the most time.

    With `reference` (the arena's reference image) it is drawn in gray under
    the cells, so it shows only where the animal never went, and the plot
    shows the whole image (`background` is then ignored).

    Cells the animal never entered are left empty, so they're transparent in a
    saved PNG. Pass `background` (a color) to fill those cells with one flat
    color instead, which is easy to select and recolor in an image editor.
    Region names are placed outside the ROIs so they don't cover the data.
    """
    df = data.df
    fig = Figure(figsize=FIGSIZE, dpi=100, layout="constrained")
    fig.opaque = reference is not None
    ax = fig.add_subplot(111)
    extent_ref = _draw_reference(ax, reference) if reference is not None else None
    if extent_ref:
        background = None

    x = df["X"].to_numpy()
    y = df["Y"].to_numpy()

    # Untracked frames come through as NaN; histogram2d can't bin them.
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]

    # The grid covers the whole arena (all ROIs) plus anywhere the animal went,
    # so "background" means every cell of the arena it never entered, not just
    # the gaps inside the area it happened to cover. Cells are square: `bins`
    # cells along the longer side.
    polys = match_polygons(data)
    pts = ([np.column_stack([x, y])] + [np.column_stack(p) for p in polys.values()]
           + _object_extent(data))
    pts = np.vstack([p for p in pts if len(p)]).astype(float)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    cell = max(float((hi - lo).max()), 1.0) / bins
    nx, ny = (np.ceil((hi - lo) / cell).astype(int) + 1)
    heat, xedges, yedges = np.histogram2d(
        x, y, bins=[nx, ny],
        range=[[lo[0], lo[0] + nx * cell], [lo[1], lo[1] + ny * cell]],
    )
    extent = [xedges[0], xedges[-1], yedges[-1], yedges[0]]
    if background:
        ax.add_patch(Rectangle(
            (xedges[0], yedges[0]), xedges[-1] - xedges[0], yedges[-1] - yedges[0],
            facecolor=background, edgecolor="none", zorder=0,
        ))
    # Transpose so array orientation matches x (cols) / y (rows). Zero cells
    # are masked, so they show nothing (or the background patch beneath).
    im = ax.imshow(
        np.ma.masked_equal(heat.T, 0),
        origin="upper",
        extent=extent,
        cmap=cmap,
        aspect="equal",
        zorder=1,
    )
    # Colorbar is attached to the axes (not the figure edge) so the square plot
    # and its bar stay together, centered, however wide the tab is.
    cax = ax.inset_axes([1.04, 0.1, 0.04, 0.8])
    cax.set_in_layout(True)  # so constrained layout leaves room for it
    fig.colorbar(im, cax=cax, label="Frames in cell")
    fig.get_layout_engine().set(w_pad=0.1)

    _draw_rois(ax, data, labels=False,
               color=REFERENCE_ROI_COLOR if extent_ref else "0.6")
    _draw_objects(ax, data, zone_cm, labels=labels,
                  color=REFERENCE_ROI_COLOR if extent_ref else "0.6")
    if labels:
        _outside_labels(ax, polys, boxed=extent_ref is not None)
    if extent_ref:
        _show_whole(ax, extent_ref)

    ax.set_title(f"Occupancy — {data.name}")
    ax.set_xlabel("X (px)")
    ax.set_ylabel("Y (px)")
    return fig


# --- acoustic startle (ROADMAP §13) ----------------------------------------
# One color per trial type, always in this order (Okabe-Ito: readable with
# color-vision differences).
TRIAL_COLORS = ("#0072B2", "#D55E00", "#009E73", "#CC79A7")
STARTLE_FIGSIZE = (9.0, 4.6)


def motion_figure(data: TrackingData, trials) -> Figure:
    """The motion index across the session, with each stimulus marked."""
    fig = Figure(figsize=STARTLE_FIGSIZE, dpi=100, layout="constrained")
    ax = fig.add_subplot(111)
    ax.plot(data.df["Time_s"], data.df["MotionIndex_pct"], color=TRIAL_COLORS[0], linewidth=1.0)
    onsets = [] if trials is None or trials.empty else trials["Stimulus_s"].dropna().tolist()
    for t in onsets:
        ax.axvline(t, color="0.55", linewidth=0.8, linestyle="--", zorder=0)
    ax.set_title(f"Motion index ({len(onsets)} stimuli marked) \u2014 {data.name}")
    ax.set_xlabel("Video time (s)")
    ax.set_ylabel("Motion index (% of pixels)")
    ax.spines[["top", "right"]].set_visible(False)
    return fig


def aligned_figure(data: TrackingData, trials, startle_ms: float, baseline_ms: float) -> Figure:
    """Every trial's motion index lined up on its stimulus: thin lines for
    trials, a heavy line for each trial type's mean."""
    fig = Figure(figsize=STARTLE_FIGSIZE, dpi=100, layout="constrained")
    ax = fig.add_subplot(111)
    ax.set_title(f"Trials aligned to the stimulus \u2014 {data.name}")
    ax.set_xlabel("Time from stimulus (ms)")
    ax.set_ylabel("Motion index (% of pixels)")
    ax.spines[["top", "right"]].set_visible(False)
    if trials is None or trials.empty:
        ax.text(0.5, 0.5, "This file has no stimuli to align.", transform=ax.transAxes,
                ha="center", va="center", color="0.4")
        return fig
    frames = data.df["Frame"].to_numpy(dtype=int)
    values = data.df["MotionIndex_pct"].to_numpy(dtype=float)
    times = data.df["Time_s"].to_numpy(dtype=float)
    step = float(np.median(np.diff(times))) if len(times) > 1 else 0.0
    if step <= 0:
        return fig
    before = int(np.ceil(baseline_ms / 1000 / step))
    after = int(np.ceil(startle_ms / 1000 / step))
    offsets = np.arange(-before + 1, after + 1)
    x = offsets * step * 1000
    kinds = sorted(trials["Type"].astype(str).unique())
    for k, kind in enumerate(kinds):
        color = TRIAL_COLORS[min(k, len(TRIAL_COLORS) - 1)]
        traces = []
        for frame in trials.loc[trials["Type"].astype(str) == kind, "Stimulus_Frame"]:
            at = np.flatnonzero(frames == int(frame))
            if at.size == 0:
                continue
            rows = at[0] + offsets
            trace = np.full(len(rows), np.nan)
            good = (rows >= 0) & (rows < len(values))
            trace[good] = values[rows[good]]
            traces.append(trace)
            ax.plot(x, trace, color=color, linewidth=0.7, alpha=0.3)
        if traces and np.any(~np.isnan(np.array(traces))):
            ax.plot(x, np.nanmean(np.array(traces), axis=0), color=color, linewidth=2.2,
                    label=f"{kind} (mean of {len(traces)})")
    ax.axvline(0, color="0.35", linewidth=1.0, linestyle="--", zorder=0)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(frameon=False, loc="upper left")
    return fig
