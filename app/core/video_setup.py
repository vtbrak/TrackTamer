"""One video's setup before tracking (GUI-free): trim, crop, exclusion shapes,
reference image, and (from setup step 4 on) regions and scale.

Each video has its own setup; nothing is shared between videos except by an
explicit "start from the previous video" copy, which the user then confirms
(ROADMAP §12, Stages 1 and 4).

All shapes are stored in **full-size video pixels**, and converted to the
prepared-frame pixels tracking uses (after downsampling, then cropping, as in
ezTrack) only when needed, so changing the downsampling never invalidates
anything drawn.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np

from .objects import DEFAULT_OBJECTS, KINDS, TrialObject
from .regions import auto_role
from .tracking import Region, Scale, make_reference
from .video import Prep, VideoInfo, polygon_mask

STEPS = ("trim", "exclusions", "reference", "tracking", "regions", "scale")
ASR_TEST = "Acoustic Startle Response"
ASR_STEPS = ("trim", "exclusions", "threshold", "stimuli")


def steps_for(test: str) -> tuple:
    """The setup steps a test uses."""
    return ASR_STEPS if test == ASR_TEST else STEPS

# The regions each test draws (ROADMAP §12, Stage 4), as (name, role). Open
# Field draws the arena outline and the center; periphery = outline minus
# center, so the two can't overlap.
OUTLINE = "arena outline"
REGION_TEMPLATES = {
    "Elevated Plus Maze": [("open arm 1", "open_arm"), ("open arm 2", "open_arm"),
                           ("closed arm 1", "closed_arm"), ("closed arm 2", "closed_arm"),
                           ("center", "center")],
    "Open Field": [(OUTLINE, "outline"), ("center", "center")],
}
# Object Recognition draws objects (circles) instead of regions (ROADMAP §15).
OBJECT_TEST = "Object Recognition"


def effective_dsmpl(dsmpl: float) -> float:
    """ezTrack only resizes when downsampling is below 1."""
    return dsmpl if dsmpl < 1 else 1.0


@dataclass
class VideoSetup:
    path: str
    info: VideoInfo
    start: int = 0
    end: int | None = None                   # exclusive; None = to the end
    length_s: float | None = None            # session length; sets the end when given
    # The test whose standard length `length_s` is ("" once the user types a
    # length or sets the end): a standard length follows the test type when
    # that changes, a length the user chose never does.
    length_default: str = ""
    # The end placed with "Set end here" (exclusive frame), or None when the
    # end comes from a typed or standard length. A placed end stays on its
    # frame when the start moves (user, 2026-11-11); a length follows the start.
    end_placed: int | None = None
    crop: tuple[float, float, float, float] | None = None   # full-size x0, y0, x1, y1
    exclusions: list[tuple[list, list]] = field(default_factory=list)  # full-size polygons
    reference: np.ndarray | None = None
    reference_key: tuple | None = None       # what the reference was made from
    unreadable: tuple[int, int] = (0, 0)     # (unreadable, checked) at add time
    steps_done: set[str] = field(default_factory=set)
    regions: dict[str, tuple[list, list]] = field(default_factory=dict)  # name -> full-size polygon
    scale_points: list[tuple[float, float]] = field(default_factory=list)  # two full-size points
    scale_cm: float | None = None
    # Object recognition (ROADMAP §15): circles as full-size (x, y, radius),
    # each marked Familiar / Novel / Moved; two objects unless more are added.
    object_names: list[str] = field(default_factory=lambda: list(DEFAULT_OBJECTS))
    objects: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    object_kinds: dict[str, str] = field(default_factory=dict)
    trial_day: str = ""
    trial_phase: str = ""
    # Acoustic startle (ROADMAP §13): stimulus frames typed in, for videos
    # without an info file listing them.
    stimulus_frames: list[int] = field(default_factory=list)

    @property
    def end_frame(self) -> int:
        """First frame after the trial (exclusive). With a session length, the
        end is start + length x fps, clamped to the video's end."""
        n = self.info.frame_count
        if self.length_s is not None and self.info.fps:
            return min(self.start + int(round(self.length_s * self.info.fps)), n)
        return n if self.end is None else min(self.end, n)

    def video_shorter_than_length(self) -> bool:
        """True if the video ends before start + session length."""
        return (self.length_s is not None and bool(self.info.fps)
                and self.start + int(round(self.length_s * self.info.fps)) > self.info.frame_count)

    # --- coordinates -----------------------------------------------------
    def _crop_origin(self, dsmpl: float) -> tuple[int, int]:
        """Top-left of the crop in downsampled pixels, as `crop_frame` cuts it."""
        if not self.crop:
            return 0, 0
        d = effective_dsmpl(dsmpl)
        x0, y0, x1, y1 = self.crop
        return int(min(x0 * d, x1 * d)), int(min(y0 * d, y1 * d))

    def prep(self, dsmpl: float) -> Prep:
        d = effective_dsmpl(dsmpl)
        crop = tuple(v * d for v in self.crop) if self.crop else None
        return Prep(dsmpl=dsmpl, crop=crop)

    def prepared_shape(self, dsmpl: float) -> tuple[int, int]:
        """(height, width) of a prepared frame."""
        d = effective_dsmpl(dsmpl)
        w = int(self.info.width * d) if d < 1 else self.info.width
        h = int(self.info.height * d) if d < 1 else self.info.height
        if self.crop:
            x0, y0, x1, y1 = (v * d for v in self.crop)
            xmin, xmax = int(min(x0, x1)), int(max(x0, x1))
            ymin, ymax = int(min(y0, y1)), int(max(y0, y1))
            w = min(xmax, w) - max(xmin, 0)
            h = min(ymax, h) - max(ymin, 0)
        return h, w

    def to_prepared(self, xs, ys, dsmpl: float) -> tuple[list[float], list[float]]:
        """Full-size pixel coordinates -> prepared-frame coordinates."""
        d = effective_dsmpl(dsmpl)
        ox, oy = self._crop_origin(dsmpl)
        return [x * d - ox for x in xs], [y * d - oy for y in ys]

    def from_prepared(self, xs, ys, dsmpl: float) -> tuple[list[float], list[float]]:
        d = effective_dsmpl(dsmpl)
        ox, oy = self._crop_origin(dsmpl)
        return [(x + ox) / d for x in xs], [(y + oy) / d for y in ys]

    def exclusion_mask(self, dsmpl: float) -> np.ndarray | None:
        if not self.exclusions:
            return None
        polys = [self.to_prepared(xs, ys, dsmpl) for xs, ys in self.exclusions]
        return polygon_mask(self.prepared_shape(dsmpl), polys)

    # --- reference -------------------------------------------------------
    def _reference_inputs(self, dsmpl: float, frames: int) -> tuple:
        return (self.start, self.end_frame, self.crop, effective_dsmpl(dsmpl), int(frames))

    def reference_current(self, dsmpl: float, frames: int) -> bool:
        """True if the reference was made from the current trim, crop,
        downsampling, and frame count."""
        return (self.reference is not None
                and self.reference_key == self._reference_inputs(dsmpl, frames))

    def untick_stale_reference(self, dsmpl: float, frames: int) -> bool:
        """The reference image was made from a start, end, crop, downsampling
        and frame count that have since changed, so Track would have to make
        a new one the user never saw: untick Reference and Tracking check,
        so the user makes it again and looks at the tracking check (user,
        2026-11-11). True if anything was unticked."""
        if self.reference is None or self.reference_current(dsmpl, frames):
            return False
        stale = self.steps_done & {"reference", "tracking"}
        self.steps_done -= stale
        return bool(stale)

    def build_reference(self, dsmpl: float, frames: int) -> np.ndarray:
        self.reference = make_reference(self.path, self.prep(dsmpl), self.start,
                                        self.end_frame, num_frames=int(frames))
        self.reference_key = self._reference_inputs(dsmpl, frames)
        return self.reference

    # --- regions and scale -----------------------------------------------
    def tracking_regions(self, dsmpl: float, test: str) -> list[Region]:
        """The drawn regions in prepared-frame pixels, as tracking writes
        them. Every region other than the center has the center's area removed,
        so a pixel on a border the center shares (or a drawn overlap) belongs
        to the center only (user's rule, 2026-11-05). Open Field's outline
        becomes "periphery" (outline minus center); other drawn names are
        written as they are."""
        if test == OBJECT_TEST:
            return []           # objects are written as circles, not regions
        centers = [n for n in self.regions if auto_role(n) == "center"]
        out = []
        for name, (xs, ys) in self.regions.items():
            px, py = self.to_prepared(xs, ys, dsmpl)
            minus = [] if name in centers else list(centers)
            if test == "Open Field" and name == OUTLINE:
                out.append(Region("periphery", px, py, subtract=minus))
            else:
                out.append(Region(name, px, py, subtract=minus))
        return out

    def missing_regions(self, test: str) -> list[str]:
        if test == OBJECT_TEST:
            return [n for n in self.object_names if n not in self.objects]
        return [n for n, _ in REGION_TEMPLATES.get(test, []) if n not in self.regions]

    def tracking_objects(self, dsmpl: float) -> list[TrialObject]:
        """The drawn objects in prepared-frame pixels, as tracking writes them."""
        d = effective_dsmpl(dsmpl)
        out = []
        for name in self.object_names:
            if name in self.objects:
                x, y, r = self.objects[name]
                (px,), (py,) = self.to_prepared([x], [y], dsmpl)
                kind = self.object_kinds.get(name, "Familiar")
                out.append(TrialObject(name, px, py, r * d, kind if kind in KINDS else "Familiar"))
        return out

    def scale_px(self, dsmpl: float) -> float | None:
        """Length between the two scale points on the prepared frame."""
        if len(self.scale_points) != 2:
            return None
        d = effective_dsmpl(dsmpl)
        (x0, y0), (x1, y1) = self.scale_points
        return float(np.hypot(x1 - x0, y1 - y0) * d)

    def scale(self, dsmpl: float) -> Scale | None:
        px = self.scale_px(dsmpl)
        if not px or not self.scale_cm or self.scale_cm <= 0:
            return None
        return Scale(px, float(self.scale_cm))

    @property
    def ready(self) -> bool:
        """Every setup step looked at (regions and scale may be skipped on
        purpose; Track warns about those)."""
        return all(s in self.steps_done for s in STEPS) and self.reference is not None

    def ready_for(self, test: str) -> bool:
        """Every step of this test's setup looked at."""
        if test == ASR_TEST:
            return all(s in self.steps_done for s in ASR_STEPS)
        return self.ready

    # --- drafts from another video ---------------------------------------
    def same_size(self, other: "VideoSetup") -> bool:
        return (self.info.width, self.info.height) == (other.info.width, other.info.height)

    def has_drawn_work(self) -> bool:
        """True if anything has been drawn or placed for this video."""
        return bool(self.crop or self.exclusions or self.regions or self.objects
                    or self.scale_points)

    def copy_from(self, other: "VideoSetup") -> None:
        """Start from another video's crop, shapes, regions, scale and session
        length, as a draft: the steps they belong to are marked not done, so
        the user looks at each one. Everything drawn is in the other video's
        pixels, so it's only copied from a video of the same frame size
        (`same_size`); from a different size only the session length, object
        names and types, and trial info come across."""
        if self.same_size(other):
            self.crop = copy.deepcopy(other.crop)
            self.exclusions = copy.deepcopy(other.exclusions)
            self.regions = copy.deepcopy(other.regions)
            self.scale_points = copy.deepcopy(other.scale_points)
            self.objects = copy.deepcopy(other.objects)
        self.scale_cm = other.scale_cm
        self.length_s = other.length_s
        self.length_default = other.length_default
        self.end_placed = None      # the other video's end frame isn't this one's
        self.object_names = list(other.object_names)
        self.object_kinds = dict(other.object_kinds)
        self.trial_day, self.trial_phase = other.trial_day, other.trial_phase
        self.steps_done -= {"trim", "exclusions", "reference", "regions", "scale"}
