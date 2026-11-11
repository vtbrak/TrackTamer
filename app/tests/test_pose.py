"""Checks for core/pose.py (nose and rear end, ROADMAP §17) and the columns
tracking writes for them.

Run from the project folder:  .venv/bin/python tests/test_pose.py
"""
import os
import sys
import tempfile

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import load_csv, pose, tracking
from core.playback import draw_tracking, open_playback
from core.track_run import arena_parts
from core.video import Prep

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)

# --- a drawn animal: a dark oval body, a pointed nose, a thin tail ---------
def animal(cx, cy, angle, tail=True, shape=(200, 240)):
    """A frame with the animal's nose pointing along `angle` (degrees)."""
    img = np.full(shape, 220, np.uint8)
    a = np.radians(angle); u = np.array([np.cos(a), np.sin(a)])
    c = np.array([cx, cy], float)
    cv2.ellipse(img, (int(cx), int(cy)), (24, 12), angle, 0, 360, 30, -1)
    nose = c + u * 30
    side = np.array([-u[1], u[0]]) * 7
    cv2.fillPoly(img, [np.array([nose, c + u * 20 + side, c + u * 20 - side]).astype(np.int32)], 30)
    rear = c - u * 24
    if tail:
        cv2.line(img, tuple(rear.astype(int)), tuple((rear - u * 40).astype(int)), 30, 2)
    return img, nose, rear

ref = np.full((200, 240), 220.0)
worst = 0.0
for angle in (0, 35, 90, 160, 200, 270, 315):
    frame, nose, rear = animal(120, 100, angle)
    got = pose.find_points(frame, ref, 120, 100)
    ok = got is not None and got.source == "tail"
    if ok:
        worst = max(worst, np.hypot(*(np.array(got.nose) - nose)), np.hypot(*(np.array(got.rear) - rear)))
    check(f"nose and rear end found from the tail, facing {angle} degrees", ok)
check("both points within 4 px of where they were drawn", worst <= 4)

# Without a tail, one frame alone can't be sure; the whole video settles it.
def series(frames, centers):
    found = [pose.find_points(f, ref, cx, cy) for f, (cx, cy) in zip(frames, centers)]
    return pose.resolve(found, np.array(centers, float))

frame, nose, rear = animal(120, 100, 35, tail=False)
got = pose.find_points(frame, ref, 120, 100)
check("no tail: both ends are still found", got is not None and got.source == "shape"
      and min(np.hypot(*(np.array(got.nose) - e)) for e in (nose, rear)) <= 4)
still = animal(120, 100, 35, tail=False)[0]
blank = np.full((200, 240), 220, np.uint8); cv2.ellipse(blank, (120, 100), (24, 12), 35, 0, 360, 30, -1)
out = series([blank] * 12, [(120, 100)] * 12)
check("no clue at all (a plain oval, not moving): blank, not a guess", np.isnan(out[:, 0]).all())
# tail seen only in the first frames; the rest follow from it
made = [animal(120, 100, 35, tail=(i < 3)) for i in range(15)]
out = series([m[0] for m in made], [(120, 100)] * 15)
check("frames without a tail follow the frames that have one",
      np.isfinite(out[:, 0]).all() and np.hypot(out[:, 0] - nose[0], out[:, 1] - nose[1]).max() <= 4)
# tail seen only at the end: earlier frames are settled looking back
made = [animal(120, 100, 35, tail=(i > 11)) for i in range(15)]
out = series([m[0] for m in made], [(120, 100)] * 15)
check("and frames before the tail comes into view are settled from it too",
      np.hypot(out[:, 0] - nose[0], out[:, 1] - nose[1]).max() <= 4)
# an oval with no tail, moving: the end it moves toward
ovals, cents = [], []
for i in range(12):
    f = np.full((200, 240), 220, np.uint8); cv2.ellipse(f, (60 + 6 * i, 100), (24, 12), 0, 0, 360, 30, -1)
    ovals.append(f); cents.append((60 + 6 * i, 100))
out = series(ovals, cents)
check("no tail and no narrow end: the end facing the direction of travel",
      np.isfinite(out[:, 0]).all() and (out[:, 0] > out[:, 2]).all())
check("an empty frame gives no points", pose.find_points(ref.astype(np.uint8), ref, 120, 100) is None)

# A bar lying across the animal splits it; the pieces are joined.
frame, nose, rear = animal(120, 100, 90)
barred = frame.copy(); barred[104:111, :] = 220
got = pose.find_points(barred, ref, 120, 100)
check("an animal split by a bar is joined",
      got is not None and np.hypot(*(np.array(got.nose) - nose)) <= 5
      and np.hypot(*(np.array(got.rear) - rear)) <= 5)

# The arena limit: a wall beside the floor mirrors the animal; only the floor counts.
wall_ref = np.full((200, 240), 220.0); wall_ref[:, :100] = 130
frame, nose, rear = animal(112, 100, 90)
frame[:, :100] = np.minimum(frame[:, :100], 130)
frame[88:112, 78:100] = 0           # the reflection, touching the animal
parts = [([60, 180, 180, 60], [0, 0, 199, 199], "floor")]
arena = pose.arena_mask((200, 240), parts, 0, wall_ref)
check("the floor is told from the wall", arena[100, 150] and not arena[100, 80])
free = pose.find_points(frame, wall_ref, 112, 100)
kept = pose.find_points(frame, wall_ref, 112, 100, arena=arena)
check("with the limit, the reflection doesn't move the points",
      kept is not None and np.hypot(*(np.array(kept.nose) - nose)) <= 5
      and (free is None or free.area > kept.area))
wide = pose.arena_mask((200, 240), [([60, 180, 180, 60], [0, 0, 199, 199], "open")], 10, wall_ref)
check("an open region is widened by its margin", wide[100, 52] and not wide[100, 45])
check("no parts, no limit", pose.arena_mask((200, 240), [], 0, wall_ref) is None)
regions = [tracking.Region("open arm 1", [0, 1, 1], [0, 0, 1]), tracking.Region("center", [0, 1, 1], [0, 0, 1])]
check("only the plus maze has a limit", arena_parts(regions, "Open Field") is None
      and [p[2] for p in arena_parts(regions, "Elevated Plus Maze")] == ["open", "floor"])

# Ears: lighter spots near the nose. Measured against the tail in the same video.
def with_ears(angle, tail, cx=120, cy=100):
    f = np.full((200, 240), 220, np.uint8); a = np.radians(angle); u = np.array([np.cos(a), np.sin(a)])
    cv2.ellipse(f, (cx, cy), (26, 13), angle, 0, 360, 30, -1)
    c = np.array([cx, cy], float); side = np.array([-u[1], u[0]])
    for sgn in (-1, 1):
        cv2.circle(f, tuple((c + u * 14 + side * 6 * sgn).astype(int)), 2, 120, -1)
    if tail:
        cv2.line(f, tuple((c - u * 26).astype(int)), tuple((c - u * 66).astype(int)), 30, 2)
    return f, c + u * 26
got = pose.find_points(with_ears(20, True)[0], ref, 120, 100)
check("ears are seen toward the nose", got is not None and got.ears == 1.0)
got = pose.find_points(blank, ref, 120, 100)
check("no ears, no ear clue", got is not None and got.ears == 0.0)
frames = [with_ears(20, True)[0]] * 40 + [None] * 10 + [with_ears(200, False)[0]] * 8
found = [None if f is None else pose.find_points(f, ref, 120, 100) for f in frames]
weights = pose.clue_weights(found, np.zeros(len(found)))
check("ears that agree with the tail earn a weight", weights["ears"] >= 2)
out = pose.resolve(found, np.tile([120.0, 100.0], (len(found), 1)))
nose2 = with_ears(200, False)[1]
check("then ears alone settle a stretch with no tail",
      np.isfinite(out[-8:, 0]).all() and np.hypot(out[-8:, 0] - nose2[0], out[-8:, 1] - nose2[1]).max() <= 5)
# ears that disagree with the tail half the time count for nothing
mixed = [pose.find_points(with_ears(20, True)[0], ref, 120, 100) for _ in range(40)]
for k in range(0, 40, 2):
    mixed[k].ears = -1.0
check("ears that agree only half the time earn none",
      pose.clue_weights(mixed, np.zeros(40))["ears"] == 0.0)
check("too few frames to measure: ears left out, the others keep a small weight",
      pose.clue_weights(mixed[:5], np.zeros(5)) == {"taper": pose.TAPER_WEIGHT, "ears": 0.0, "travel": pose.TRAVEL_WEIGHT})
check("one misleading tail frame is outvoted", pose.SWITCH_COST > pose.TAIL_WEIGHT > pose.TAPER_WEIGHT + pose.TRAVEL_WEIGHT)
check("area check drops outlines far from the usual size",
      list(pose.area_filter(np.array([100.0] * 12 + [20.0, 400.0, np.nan]))) == [True] * 12 + [False] * 3)

# --- through tracking: a short video of the drawn animal -------------------
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "moving.mp4")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (240, 200))
    truth = []
    for i in range(30):
        frame, nose, rear = animal(60 + 4 * i, 100, 0)
        truth.append((nose, rear))
        writer.write(cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR))
    writer.release()
    res = tracking.track_video(path, ref, tracking.TrackingParams())
    df = res.df
    check("tracking adds the four columns", all(c in df.columns for c in tracking.BODY_POINT_COLUMNS))
    err = np.hypot(df["Nose_X"] - [t[0][0] for t in truth], df["Nose_Y"] - [t[0][1] for t in truth])
    check("the nose is found in every frame, within 5 px", err.notna().all() and err.max() <= 5)
    plain = tracking.track_video(path, ref, tracking.TrackingParams(), body_points=False).df
    check("X and Y are the same with and without the new points",
          np.allclose(plain[["X", "Y"]], df[["X", "Y"]]) and "Nose_X" not in plain.columns)
    out = tracking.assemble_output(path, df, tracking.TrackingParams(), Prep(), 0, None,
                                   (200, 240), None, 50, 0, 10.0)
    paths = tracking.save_outputs(path, out, ref)
    data = load_csv(paths["csv"])
    check("the tracking file loads, and the new columns are not taken for regions",
          data.regions == [] and data.df["Nose_X"].notna().all())
    pb = open_playback(data)
    check("playback reads the points", pb.has_body_points and pb.body_points(5) is not None)
    img = draw_tracking(np.full((200, 240, 3), 220, np.uint8), pb, 5)
    nx, ny = (int(round(v)) for v in pb.body_points(5)[0])
    check("the saved video draws the nose in red", tuple(img[ny, nx]) == (40, 40, 255))

# --- an older file without the columns still plays ------------------------
from tests import samples
if os.path.exists(samples.OF):
    old = open_playback(load_csv(samples.OF))
    if not old.has_body_points:
        check("a file without the columns has no body points", old.body_points(0) is None)

print("\nALL PASSED" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
