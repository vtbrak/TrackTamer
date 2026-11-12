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
# Startle has no crop and no exclusions (user, 2026-11-12): the motion index
# is the changed pixels divided by the pixels analyzed, so taking part of the
# picture out changes the number, differently wherever it's taken from. It is
# always worked out on the whole frame.
ASR_STEPS = ("trim", "threshold", "stimuli")


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


def clip_to_frame(xs, ys, width: float, height: float) -> tuple[list[float], list[float]]:
    """A drawn shape trimmed to the video frame (0..width, 0..height): the
    part of it inside the picture, corner by corner. It's easier to draw an
    exclusion past the edge to be sure it covers everything, and what is
    kept and recorded is exactly what lies in the frame (user, 2026-11-12).
    ([], []) if none of it does."""
    points = [(float(x), float(y)) for x, y in zip(xs, ys)]
    # Each edge of the frame in turn: keep what's on its inner side.
    edges = ((0, 0.0, 1), (0, float(width), -1), (1, 0.0, 1), (1, float(height), -1))
    for axis, limit, sign in edges:
        if not points:
            break
        inside = lambda p: sign * (p[axis] - limit) >= 0        # noqa: E731
        kept = []
        for a, b in zip(points, points[1:] + points[:1]):
            if inside(a):
                kept.append(a)
            if inside(a) != inside(b):                          # the edge is crossed here
                t = (limit - a[axis]) / (b[axis] - a[axis])
                cut = [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]
                cut[axis] = limit
                kept.append(tuple(cut))
        points = kept
    # corners that landed on top of each other add nothing
    tidy = [p for k, p in enumerate(points) if p != points[k - 1]] if len(points) > 1 else points
    if len(tidy) < 3:
        return [], []
    return [p[0] for p in tidy], [p[1] for p in tidy]


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
    # The video whose setup this one's draft was taken from (same arena, from
    # the info files), or "" if none; `draft_tried` so it's only looked for once.
    draft_source: str = ""
    draft_tried: bool = False

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

    def add_exclusion(self, xs, ys) -> bool:
        """Add an exclusion shape (full-size video pixels), trimmed to the
        frame. False if none of it is inside the picture (nothing is added)."""
        xs, ys = clip_to_frame(xs, ys, self.info.width, self.info.height)
        if not xs:
            return False
        self.exclusions.append((xs, ys))
        return True

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

    # --- kept in the video's info file --------------------------------------
    # What a startle setup has no use for: it tracks no position, so there
    # are no regions, scale or objects to save or list (user, 2026-11-12).
    # The trial day and phase stay: they are the trial's, whatever the test
    # (the recording apps write them for every assay).
    # Nor a crop or exclusions: the motion index is always of the whole frame.
    NOT_FOR_STARTLE = ("regions", "scale_points", "scale_cm", "object_names", "objects",
                       "object_kinds", "crop", "exclusions")

    def to_saved(self, test: str = "") -> dict:
        """Everything set up for this video, as the info file keeps it (plain
        numbers and lists; shapes in full-size video pixels), so the video
        can be added again with its setup as it was. For a startle video
        (`test`) what startle uses: the session, typed stimulus frames, and
        the trial day and phase as every test has them."""
        saved = self._saved()
        if test == ASR_TEST:
            for key in self.NOT_FOR_STARTLE:
                saved.pop(key, None)
        return saved

    def _saved(self) -> dict:
        shape = lambda xs, ys: {"xs": [float(x) for x in xs], "ys": [float(y) for y in ys]}  # noqa: E731
        return {
            "frame_size": [int(self.info.width), int(self.info.height)],
            "start_frame": int(self.start),
            "end_frame": int(self.end_frame),
            "length_s": None if self.length_s is None else float(self.length_s),
            "end_placed": self.end_placed,
            "crop": [float(v) for v in self.crop] if self.crop else None,
            "exclusions": [shape(xs, ys) for xs, ys in self.exclusions],
            "regions": {name: shape(xs, ys) for name, (xs, ys) in self.regions.items()},
            "scale_points": [[float(x), float(y)] for x, y in self.scale_points],
            "scale_cm": None if self.scale_cm is None else float(self.scale_cm),
            "object_names": list(self.object_names),
            "objects": {n: [float(v) for v in circle] for n, circle in self.objects.items()},
            "object_kinds": dict(self.object_kinds),
            "trial_day": self.trial_day, "trial_phase": self.trial_phase,
            "stimulus_frames": [int(f) for f in self.stimulus_frames],
            "steps_done": sorted(self.steps_done),
        }

    def restore(self, saved: dict, test: str) -> bool:
        """Take a setup back from the info file. The session and trial
        details always come back; the shapes only for a video of the frame
        size they were drawn on. The steps that were done come back done,
        except the reference image and tracking check, which need the
        reference (`use_reference`). False if `saved` isn't a setup this can read
        (nothing is changed then)."""
        try:
            pair = lambda p: (float(p[0]), float(p[1]))                 # noqa: E731
            poly = lambda s: ([float(x) for x in s["xs"]], [float(y) for y in s["ys"]])  # noqa: E731
            start = int(saved.get("start_frame") or 0)
            length = saved.get("length_s")
            length = None if length is None else float(length)
            end = saved.get("end_frame")
            placed = saved.get("end_placed")
            crop = saved.get("crop")
            crop = tuple(float(v) for v in crop) if crop else None
            if crop is not None and len(crop) != 4:
                return False
            exclusions = [clip_to_frame(*poly(s), self.info.width, self.info.height)
                          for s in saved.get("exclusions") or []]
            exclusions = [shape for shape in exclusions if shape[0]]
            regions = {str(n): poly(s) for n, s in (saved.get("regions") or {}).items()}
            points = [pair(p) for p in saved.get("scale_points") or []]
            cm = saved.get("scale_cm")
            cm = None if cm is None else float(cm)
            names = [str(n) for n in saved.get("object_names") or self.object_names]
            objects = {str(n): tuple(float(v) for v in c)
                       for n, c in (saved.get("objects") or {}).items()}
            kinds = {str(n): str(k) for n, k in (saved.get("object_kinds") or {}).items()
                     if k in KINDS}
            stimuli = [int(f) for f in saved.get("stimulus_frames") or []]
            size = saved.get("frame_size")
        except (TypeError, ValueError, KeyError, IndexError, AttributeError):
            return False
        self.start = max(0, min(start, max(self.info.frame_count - 1, 0)))
        self.length_s, self.length_default = length, ""
        self.end = None if length is not None or end is None else int(end)
        self.end_placed = int(placed) if placed is not None else None
        self.object_names, self.object_kinds = names, kinds
        self.trial_day = str(saved.get("trial_day") or "")
        self.trial_phase = str(saved.get("trial_phase") or "")
        self.stimulus_frames = stimuli
        done = {"trim"}
        if list(size or []) == [self.info.width, self.info.height]:
            self.crop, self.exclusions, self.regions = crop, exclusions, regions
            self.scale_points, self.scale_cm, self.objects = points, cm, objects
            done |= {"exclusions", "regions", "scale", "threshold", "stimuli"}
        else:
            self.scale_cm = cm
        self.reference, self.reference_key = None, None
        # The steps the user had been through (a setup saved before tracking
        # may be part done); an older file without them: every step it covers.
        kept = saved.get("steps_done")
        if isinstance(kept, list):
            done &= {str(step) for step in kept}
        self.steps_done = done & set(steps_for(test))
        return True

    def use_reference(self, image: np.ndarray, dsmpl: float, frames: int) -> bool:
        """Take a saved reference image (the one beside the video) as this
        setup's, if it's the size this setup's prepared frames are. Then
        the reference and tracking check steps count as done."""
        if image is None or tuple(image.shape[:2]) != tuple(self.prepared_shape(dsmpl)):
            return False
        self.reference = image.astype(float)
        self.reference_key = self._reference_inputs(dsmpl, frames)
        self.steps_done |= {"reference", "tracking"}
        return True

    def draft_from(self, saved: dict) -> bool:
        """Start from another video's saved crop, exclusion shapes, regions,
        scale and object circles, as a draft: no step is ticked, so the user
        looks at each one. The session, the object types and the trial
        details are this video's own and aren't touched. Only from a setup
        drawn on frames of this video's size. False if nothing was taken."""
        other = VideoSetup(path=self.path, info=self.info)
        if (list(saved.get("frame_size") or []) != [self.info.width, self.info.height]
                or not other.restore(saved, "")):
            return False
        self.crop, self.exclusions, self.regions = other.crop, other.exclusions, other.regions
        self.scale_points, self.scale_cm = other.scale_points, other.scale_cm
        self.objects = {n: c for n, c in other.objects.items() if n in self.object_names}
        self.reference, self.reference_key = None, None
        return True

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
