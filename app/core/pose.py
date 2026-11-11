"""The animal's nose and rear end in one frame, from its outline (GUI-free;
ROADMAP §17, branch `head-tail`).

Three points describe the animal: the **center** (the tracked position,
worked out as before in core/tracking.py and not changed here), the **nose**
and the **rear end** (where the body ends and the tail begins). The tail
itself is not reported; it is only used to tell which end is the rear.

Method (no trained model, so the app installs the same on Mac and Windows):
1. Outline: the pixels that differ from the reference image, in a square
   round the tracked position, thresholded (Otsu), with excluded areas and
   anything outside the drawn arena left out. Pieces of the animal split by
   something lying across it (a bar over a plus maze) are joined.
2. Body: the outline with thin parts worn away (morphological opening),
   which removes the tail.
3. Tail: the largest thin piece attached to the body. The rear end is where
   it joins the body.
4. Nose: the outline point farthest from the rear end (not counting the
   tail).
5. With no tail in view, the two ends of the outline are used.
6. Which end is the nose is settled over the whole video at once
   (`resolve`): the tail is the strong clue; the narrower end, the lighter
   ears and the direction of travel are weaker ones, each weighed by how
   well it agrees with the tail in that video; and the nose is expected to
   stay at the same end from one frame to the next.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

MIN_CONTRAST = 18        # gray levels; a fainter difference is not the animal
SHADOW_FRACTION = 0.5    # of the animal's own contrast; fainter is shadow
CORE_FRACTION = 0.75     # stricter cut for the nose: the shadow just ahead of the
                         # head is darker than the tail, so the tail is found on
                         # the looser outline and the nose on this one
MIN_AREA = 80            # pixels; a smaller outline is not used
OPEN_FRACTION = 0.32     # opening size, as a fraction of sqrt(outline area)
BRIDGE_FRACTION = 0.7    # largest gap joined, as a fraction of sqrt(area)
FAINT_FRACTION = 0.2     # of the animal's contrast: thin lines this faint count
TAIL_FULL_LENGTH = 1.0   # a tail this long (times sqrt(area)) is fully trusted
TAIL_MIN_LENGTH = 0.4    # shortest tail accepted, as a fraction of sqrt(area)
AREA_RANGE = (0.45, 2.2)  # outline area accepted, times the video's median
TRAVEL_MIN = 8.0         # pixels moved (over 4 frames) before travel is trusted
TAPER_RATIO = 0.8        # one end this much narrower than the other is a clue
# How the clues are weighed when settling nose vs rear over the video.
TAIL_WEIGHT = 4.0        # the tail is at this end
TAPER_WEIGHT = 1.0       # the narrower end, when it can't be measured (below)
TRAVEL_WEIGHT = 1.0      # moving toward this end, when it can't be measured
# The weak clues are weighed by how often they agree with a long tail in
# the video being tracked (`clue_weights`).
CALIBRATE_TAIL = 0.9     # tail strength that counts as settling a frame
CALIBRATE_MIN = 30       # frames needed to measure a clue
MAX_WEAK_WEIGHT = 3.0
# Ears (user's idea, 2026-11-10): lighter spots inside the body.
EAR_CONTRAST = 0.15      # lighter than the fur by this much of the animal's contrast
EAR_SIZE = 0.25          # largest spot width, times sqrt(area)
EAR_MAX_AREA = 0.06      # largest spot, as a share of the outline
EAR_OFF_CENTER = 0.1     # how far from the middle of the body before it counts
SWITCH_COST = 6.0        # the nose changing ends between two frames (so one
                         # misleading tail frame is outvoted: 2 switches > 2 tails)
MAX_GAP = 5              # frames without points before a stretch is cut


@dataclass
class BodyPoints:
    nose: tuple[float, float]      # x, y in prepared-frame pixels
    rear: tuple[float, float]
    area: int                      # outline pixels (for the sanity check)
    source: str                    # "tail" if a tail was seen, else "shape"
    tail: float = 0.0              # 0 to 1: a tail at the rear, and how long
    taper: float = 0.0             # +1 the nose end is the narrower one, -1 the rear
    ears: float = 0.0              # +1 lighter spots toward the nose, -1 toward the rear


def _kernel(size: int) -> np.ndarray:
    size = max(3, int(size) | 1)
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


def _component_at(mask: np.ndarray, px: int, py: int) -> np.ndarray | None:
    """The connected piece of `mask` at (px, py), or the nearest sizable one."""
    n, lab, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
    if n < 2:
        return None
    k = lab[py, px]
    if k == 0:
        big = stats[1:, cv2.CC_STAT_AREA] >= MIN_AREA // 2
        if not big.any():
            return None
        d = np.hypot(cent[1:, 0] - px, cent[1:, 1] - py)
        d[~big] = np.inf
        k = 1 + int(np.argmin(d))
    return (lab == k).astype(np.uint8)


def outline(frame: np.ndarray, reference: np.ndarray, cx: float, cy: float,
            method: str = "dark", half: int = 75, exclude: np.ndarray | None = None,
            arena: np.ndarray | None = None
            ) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None, tuple[int, int]]:
    """The animal's outline as a 0/1 image of a square round (cx, cy), its
    darker core (see CORE_FRACTION), the thin faint lines in the square (see
    FAINT_FRACTION), and the square's top-left corner in the frame. The
    outline is None if nothing is found.
    The square starts `half` pixels each way and is widened (up to twice)
    when the animal reaches its edge, so a large animal isn't cut off."""
    h, w = min(frame.shape[0], reference.shape[0]), min(frame.shape[1], reference.shape[1])
    for _attempt in range(3):
        x0, x1 = max(0, int(cx - half)), min(w, int(cx + half) + 1)
        y0, y1 = max(0, int(cy - half)), min(h, int(cy + half) + 1)
        if x1 - x0 < 8 or y1 - y0 < 8:
            return None, None, None, (x0, y0)
        main, core, faint = _outline_in(frame, reference, cx, cy, method, exclude, arena, x0, y0, x1, y1)
        if main is None:
            return None, None, None, (x0, y0)
        cut = ((x0 > 0 and main[:, 0].any()) or (x1 < w and main[:, -1].any())
               or (y0 > 0 and main[0].any()) or (y1 < h and main[-1].any()))
        if not cut:
            break
        half = int(half * 1.6)
    return main, core, faint, (x0, y0)


def _outline_in(frame, reference, cx, cy, method, exclude, arena, x0, y0, x1, y1):
    f = frame[y0:y1, x0:x1].astype(np.float32)
    r = reference[y0:y1, x0:x1].astype(np.float32)
    dif = np.abs(f - r) if method == "abs" else (f - r) if method == "light" else (r - f)
    dif = np.clip(dif, 0, 255).astype(np.uint8)
    allowed = np.ones(dif.shape, dtype=bool)
    if exclude is not None:
        allowed &= ~exclude[y0:y1, x0:x1]
    if arena is not None:
        allowed &= arena[y0:y1, x0:x1]
    values = dif[allowed]
    if values.size < MIN_AREA:
        return None, None, None
    thresh, _ = cv2.threshold(values.reshape(-1, 1), 0, 255,
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thresh = max(thresh, MIN_CONTRAST)
    px = min(max(int(round(cx)) - x0, 0), dif.shape[1] - 1)
    py = min(max(int(round(cy)) - y0, 0), dif.shape[0] - 1)
    main = _component_at(((dif > thresh) & allowed).astype(np.uint8), px, py)
    if main is None:
        return None, None, None
    # A soft shadow round the animal differs from the reference too, but far
    # less than the animal does: keep only what differs by a good part of
    # the animal's own contrast.
    contrast = float(np.median(dif[main == 1]))
    strong = contrast * SHADOW_FRACTION
    if strong > thresh:
        thresh = strong
    mask = ((dif > thresh) & allowed).astype(np.uint8)
    main = _component_at(mask, px, py)
    if main is None:
        return None, None, None
    # Join pieces split by something lying across the animal: close small
    # gaps, and keep the joined shape only if it adds a real second piece.
    area = int(main.sum())
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                              _kernel(round(np.sqrt(area) * BRIDGE_FRACTION)))
    ys, xs = np.nonzero(main)
    joined = _component_at(closed, int(xs[0]), int(ys[0]))
    if joined is not None and int((mask & joined).sum()) >= 1.1 * area:
        main = joined
    core = main & (dif > max(thresh, contrast * CORE_FRACTION)).astype(np.uint8)
    if int(core.sum()) < MIN_AREA // 2:
        core = main
    # A tail over a pale floor can be too faint for the outline. Thin lines
    # stand out once everything broad (the body, shadows) is taken away
    # (a top-hat), so they can be picked up at a much lower contrast.
    lines = cv2.morphologyEx(dif, cv2.MORPH_TOPHAT,
                             _kernel(round(np.sqrt(area) * OPEN_FRACTION)))
    faint = ((lines > max(MIN_CONTRAST * 0.6, contrast * FAINT_FRACTION)) & allowed).astype(np.uint8)
    return main, core, faint


def _shape(mask: np.ndarray, faint: np.ndarray | None = None) -> dict | None:
    """Body axis ends, and the tail's joining point if a tail is seen.
    `tail_strength` is 0 to 1: how long the tail piece is (a short thin piece
    may be a snout, an ear or a foot instead)."""
    area = int(mask.sum())
    if area < MIN_AREA:
        return None
    root = np.sqrt(area)
    body = cv2.morphologyEx(mask, cv2.MORPH_OPEN, _kernel(round(root * OPEN_FRACTION)))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(body, 8)
    if n < 2:
        return None
    body = (lab == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    ys, xs = np.nonzero(body)
    pts = np.column_stack([xs, ys]).astype(float)
    c = pts.mean(0)
    _u, _s, vt = np.linalg.svd(pts - c, full_matrices=False)
    proj = (pts - c) @ vt[0]
    ends = (pts[int(np.argmax(proj))], pts[int(np.argmin(proj))])

    near = cv2.dilate(body, np.ones((3, 3), np.uint8))
    thin = (mask == 1) if faint is None else ((mask == 1) | (faint == 1))
    thin = (thin & (near == 0)).astype(np.uint8)
    tail = None
    tail_base = None
    strength = 0.0
    if thin.sum() >= 6:
        n2, lab2, st2, _ = cv2.connectedComponentsWithStats(thin, 8)
        reach = cv2.dilate(body, np.ones((7, 7), np.uint8)) == 1
        best, best_len = 0, 0.0
        for k in range(1, n2):
            if not (reach & (lab2 == k)).any():
                continue                    # not joined to the body
            length = float(max(st2[k, cv2.CC_STAT_WIDTH], st2[k, cv2.CC_STAT_HEIGHT]))
            if length > best_len:
                best, best_len = k, length
        if best and best_len >= TAIL_MIN_LENGTH * root:
            tail = lab2 == best
            ty, tx = np.nonzero(tail)
            # where the tail meets the body: its pixel nearest the body
            dist = cv2.distanceTransform((body == 0).astype(np.uint8), cv2.DIST_L2, 3)
            k = int(np.argmin(dist[ty, tx]))
            tail_base = np.array([tx[k], ty[k]], float)
            strength = min(1.0, best_len / (TAIL_FULL_LENGTH * root))
    return {"area": area, "body": body, "center": c, "ends": ends, "tail": tail,
            "tail_base": tail_base, "tail_strength": strength}


def _farthest(mask: np.ndarray, from_pt: np.ndarray) -> np.ndarray:
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return np.asarray(from_pt, float)
    k = int(np.argmax((xs - from_pt[0]) ** 2 + (ys - from_pt[1]) ** 2))
    return np.array([xs[k], ys[k]], float)


def _ear_clue(gray: np.ndarray, dif: np.ndarray, s: dict, nose: np.ndarray,
              rear: np.ndarray) -> float:
    """+1 if the lighter spots inside the body (the ears, in videos where
    they show lighter than the fur) sit toward `nose`, -1 if toward `rear`,
    0 if there are none or they sit in the middle. Something light lying
    right across the animal (a bar) is too big to count."""
    body = s["body"]
    root = np.sqrt(s["area"])
    contrast = float(np.median(dif[body == 1]))
    filled = cv2.morphologyEx(body, cv2.MORPH_CLOSE, _kernel(round(root * 0.35)))
    inner = cv2.erode(filled, np.ones((3, 3), np.uint8))
    fur = float(np.median(gray[body == 1]))
    inside = np.where(filled == 1, gray, fur).astype(np.float32)   # the floor doesn't count
    spots = cv2.morphologyEx(inside, cv2.MORPH_TOPHAT, _kernel(round(root * EAR_SIZE)))
    light = ((spots > EAR_CONTRAST * contrast) & (inner == 1)).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(light, 8)
    keep = np.zeros(light.shape, dtype=bool)
    for k in range(1, n):
        if 3 <= st[k, cv2.CC_STAT_AREA] <= EAR_MAX_AREA * s["area"]:
            keep |= lab == k
    if keep.sum() < 3:
        return 0.0
    axis = (nose - rear) / max(float(np.hypot(*(nose - rear))), 1e-6)
    ys, xs = np.nonzero(body)
    t_body = (np.column_stack([xs, ys]) - rear) @ axis
    lo, length = float(t_body.min()), float(np.ptp(t_body))
    if length < 5:
        return 0.0
    ly, lx = np.nonzero(keep)
    w = spots[ly, lx]
    t = float(((((np.column_stack([lx, ly]) - rear) @ axis) - lo) * w).sum() / w.sum() / length)
    if abs(t - 0.5) <= EAR_OFF_CENTER:
        return 0.0
    return 1.0 if t > 0.5 else -1.0


def find_points(frame: np.ndarray, reference: np.ndarray, cx: float, cy: float,
                method: str = "dark", half: int = 75,
                exclude: np.ndarray | None = None,
                arena: np.ndarray | None = None) -> BodyPoints | None:
    """The animal's two ends in one prepared frame, as a first guess at
    which is the nose, with this frame's clues about that guess (`tail`,
    `taper`, `ears`: above 0 the guess is favored, below 0 the other way
    round, 0 no clue). `resolve` settles the guesses over the whole video.
    None when the outline can't be used."""
    mask, core, faint, (x0, y0) = outline(frame, reference, cx, cy, method, half,
                                          exclude, arena)
    if mask is None:
        return None
    s = _shape(mask, faint)
    if s is None:
        return None
    off = np.array([x0, y0], float)
    if s["tail"] is not None:
        rear = s["tail_base"]
        head = (core == 1) & ~s["tail"]
        nose = _farthest(head if head.any() else (mask == 1) & ~s["tail"], rear)
        tail = float(s["tail_strength"])
    else:
        a, b = s["ends"]        # ends of the worn-down body's long axis
        nose = _farthest(core == 1, b)
        rear = _farthest(core == 1, nose)
        tail = 0.0
    # The nose end of the body is usually the narrower one (a weaker clue).
    ys, xs = np.nonzero(s["body"])
    along = np.column_stack([xs, ys]).astype(float) - rear
    axis = (nose - rear) / max(float(np.hypot(*(nose - rear))), 1e-6)
    t = along @ axis
    lo, hi = float(t.min()), float(t.max())
    front = int((t > lo + (hi - lo) * 2 / 3).sum())
    back = int((t < lo + (hi - lo) / 3).sum())
    taper = 0.0
    if min(front, back) < TAPER_RATIO * max(front, back):
        taper = 1.0 if front < back else -1.0
    ears = 0.0
    if method == "dark":        # ears lighter than dark fur
        hh, ww = mask.shape
        gray = frame[y0:y0 + hh, x0:x0 + ww].astype(np.float32)
        dif = np.clip(reference[y0:y0 + hh, x0:x0 + ww].astype(np.float32) - gray, 0, 255)
        ears = _ear_clue(gray, dif, s, nose, rear)
    nose, rear = nose + off, rear + off
    return BodyPoints((float(nose[0]), float(nose[1])), (float(rear[0]), float(rear[1])),
                      s["area"], "tail" if s["tail"] is not None else "shape",
                      tail, taper, ears)


last_weights: dict[str, float] = {}     # the weights `resolve` last used


def _travel(found: list[BodyPoints | None], centers: np.ndarray) -> np.ndarray:
    """Per frame: +1 if the animal is moving toward the guessed nose, -1 if
    away from it, 0 if it is hardly moving (or there are no points)."""
    n = len(found)
    out = np.zeros(n)
    for i, f in enumerate(found):
        if f is None:
            continue
        v = centers[min(i + 2, n - 1)] - centers[max(i - 2, 0)]
        if np.all(np.isfinite(v)) and np.hypot(*v) >= TRAVEL_MIN:
            out[i] = 1.0 if np.subtract(f.nose, f.rear) @ v > 0 else -1.0
    return out


def clue_weights(found: list[BodyPoints | None], travel: np.ndarray) -> dict[str, float]:
    """How much each weak clue counts in this video, measured on the video
    itself: over the frames where a long tail settles which end is the nose,
    how often does the clue agree? A clue that agrees nearly always counts
    for a lot, one that agrees half the time (ears that don't show lighter
    in this video, say) counts for nothing. With too few long-tail frames to
    measure, the narrow end and travel keep a small fixed weight and the ears
    are left out."""
    sure = [i for i, f in enumerate(found) if f is not None and f.tail >= CALIBRATE_TAIL]

    def weight(values, default):
        votes = [v > 0 for v in values if v != 0]
        if len(votes) < CALIBRATE_MIN:
            return default
        p = min(max(float(np.mean(votes)), 0.02), 0.98)
        return float(min(max(np.log(p / (1 - p)), 0.0), MAX_WEAK_WEIGHT))

    return {"taper": weight([found[i].taper for i in sure], TAPER_WEIGHT),
            "ears": weight([found[i].ears for i in sure], 0.0),
            "travel": weight([travel[i] for i in sure], TRAVEL_WEIGHT)}


def resolve(found: list[BodyPoints | None], centers: np.ndarray) -> np.ndarray:
    """Settle which end is the nose in every frame, looking at the whole
    video at once. Returns an array of rows (nose x, nose y, rear x, rear y,
    outline area), NaN where there are no points.

    Each frame's own clues (the tail, the narrower end, the lighter ears,
    the direction of travel; see `clue_weights` for how much each counts)
    are weighed against keeping the nose at the same end from one frame to
    the next, and the best overall answer is taken (a shortest-path search).
    So a stretch with the tail out of sight is settled by the frames before
    and after it, and a single misleading frame is outvoted. A stretch with
    no clue at all is left blank rather than guessed."""
    n = len(found)
    out = np.full((n, 5), np.nan)
    centers = np.asarray(centers, float)
    travel = _travel(found, centers)
    w = clue_weights(found, travel)
    last_weights.clear()
    last_weights.update(w)      # for reports and tests
    start = 0
    while start < n:
        if found[start] is None:
            start += 1
            continue
        # a stretch: frames with points, no more than MAX_GAP frames apart
        idx = [start]
        k = start + 1
        while k < n and k - idx[-1] <= MAX_GAP:
            if found[k] is not None:
                idx.append(k)
            k += 1
        start = idx[-1] + 1
        ev = np.array([TAIL_WEIGHT * found[i].tail + w["taper"] * found[i].taper
                       + w["ears"] * found[i].ears + w["travel"] * travel[i] for i in idx])
        if np.abs(ev).sum() < 1:
            continue                        # nothing to tell the ends apart
        # state 0 = as guessed, 1 = the other way round
        cost = np.zeros((len(idx), 2))
        back = np.zeros((len(idx), 2), dtype=int)
        cost[0] = (-ev[0], ev[0])
        for m in range(1, len(idx)):
            p, q = found[idx[m - 1]], found[idx[m]]
            ends_p = (np.array(p.nose), np.array(p.rear))
            ends_q = (np.array(q.nose), np.array(q.rear))
            for state in (0, 1):
                best = None
                for prev in (0, 1):
                    # the nose jumping to the far end between frames costs
                    stay = np.hypot(*(ends_q[state] - ends_p[prev]))
                    jump = np.hypot(*(ends_q[1 - state] - ends_p[prev]))
                    c = cost[m - 1, prev] + (SWITCH_COST if stay > jump else 0.0)
                    if best is None or c < best:
                        best, back[m, state] = c, prev
                cost[m, state] = best + (-ev[m] if state == 0 else ev[m])
        state = int(np.argmin(cost[-1]))
        for m in range(len(idx) - 1, -1, -1):
            f = found[idx[m]]
            nose, rear = (f.nose, f.rear) if state == 0 else (f.rear, f.nose)
            out[idx[m]] = (*nose, *rear, f.area)
            state = int(back[m, state])
    out[~area_filter(out[:, 4]), :4] = np.nan
    return out


def arena_mask(shape: tuple[int, int], parts: list[tuple[list, list, str]],
               margin: float, reference: np.ndarray, method: str = "dark") -> np.ndarray | None:
    """Where the animal's outline may be (True), for arenas with walls that
    mirror the animal (the plus maze). `parts` are the drawn regions as
    (xs, ys, kind) in prepared-frame pixels:
    - "open": the region widened by `margin` pixels, so a head dipped over
      the edge is still seen;
    - "floor": only the region's floor, told from its walls by brightness in
      the reference image (the brighter part for a dark animal, the darker
      part for a light one). A drawn closed arm takes in its walls, where
      the animal's reflection shows; this leaves them out.
    None when there are no parts (no limit)."""
    if not parts:
        return None
    h, w = min(shape[0], reference.shape[0]), min(shape[1], reference.shape[1])
    ref = np.clip(reference[:h, :w], 0, 255).astype(np.uint8)
    arena = np.zeros(shape, dtype=bool)
    grow = _kernel(2 * int(round(margin)) + 1)
    for xs, ys, kind in parts:
        if len(xs) < 3:
            continue
        m = np.zeros(shape, dtype=np.uint8)
        cv2.fillPoly(m, [np.column_stack((np.asarray(xs), np.asarray(ys))).astype(np.int32)], 1)
        if kind == "open":
            if margin >= 1:
                m = cv2.dilate(m, grow)
        elif method != "abs":
            inside = m[:h, :w] == 1
            if inside.sum() >= MIN_AREA:
                cut, _ = cv2.threshold(ref[inside].reshape(-1, 1), 0, 255,
                                       cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                floor = (ref > cut) if method == "dark" else (ref <= cut)
                m[:h, :w] = (inside & floor).astype(np.uint8)
        arena |= m.astype(bool)
    return arena


def area_filter(areas: np.ndarray) -> np.ndarray:
    """True for frames whose outline area is plausible for this video's
    animal (within AREA_RANGE of the median area). Frames with no animal in
    the picture, or with something else merged in, fall outside."""
    areas = np.asarray(areas, float)
    ok = np.isfinite(areas)
    if ok.sum() < 10:
        return ok
    med = float(np.median(areas[ok]))
    return ok & (areas >= AREA_RANGE[0] * med) & (areas <= AREA_RANGE[1] * med)
