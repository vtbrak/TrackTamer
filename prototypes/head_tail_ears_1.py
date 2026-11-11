"""Do the lighter ears tell the nose end? Checked on frames where a long tail settles it."""
import sys, os, numpy as np, cv2
sys.path.insert(0, os.getcwd())
from core import load_csv, pose
from core.playback import open_playback, load_reference
from core.video import VideoReader
SP = sys.argv[1]

def ear_position(frame, ref, cx, cy, lo=0.15, hi=0.75):
    """(t, n, strength_of_tail, taper_says_nose) where t is where the lighter
    pixels inside the body sit along rear(0)->nose(1) as guessed from the tail."""
    mask, core, faint, (x0, y0) = pose.outline(frame, ref, cx, cy)
    if mask is None: return None
    s = pose._shape(mask, faint)
    if s is None: return None
    hh, ww = mask.shape
    f = frame[y0:y0+hh, x0:x0+ww].astype(np.float32); r = ref[y0:y0+hh, x0:x0+ww].astype(np.float32)
    dif = np.clip(r - f, 0, 255)
    body = s["body"]
    contrast = float(np.median(dif[body == 1]))
    # the body with its holes and notches filled, then shrunk so the blurred rim is left out
    k = pose._kernel(round(np.sqrt(s["area"]) * 0.3))
    filled = cv2.morphologyEx(body, cv2.MORPH_CLOSE, k)
    inner = cv2.erode(filled, np.ones((5, 5), np.uint8))
    light = (inner == 1) & (dif > lo * contrast) & (dif < hi * contrast)
    n = int(light.sum())
    ys, xs = np.nonzero(body); pts = np.column_stack([xs, ys]).astype(float)
    a, b = s["ends"]; axis = (a - b) / max(np.hypot(*(a - b)), 1e-6)
    t_all = (pts - b) @ axis; L = t_all.max() - t_all.min()
    if n < 4 or L < 5: return (None, n, s, None)
    ly, lx = np.nonzero(light)
    w = (hi * contrast - dif[ly, lx])            # lighter counts more
    t = float((((np.column_stack([lx, ly]) - b) @ axis - t_all.min()) * w).sum() / w.sum() / L)   # 0 at end b, 1 at end a
    return (t, n, s, (a, b))

VIDEOS = [("Examples/1_2026-06-26_14-03-15", 800, 2900), ("Examples/1_2026-08-17_13-27-03", 2000, 5000), ("Examples/6_2024-04-01_11-49-23", 0, 4900)] + \
         [(f"{SP}/trial/{n}", 0, 5000) for n in ("2_2023-01-29_10-56-37", "2_2023-03-30_11-11-53", "6_2023-03-26_15-19-33", "6_2023-11-01_10-43-52", "6_2024-03-30_09-37-12", "7_2023-08-28_12-49-34", "8_2023-06-06_10-32-11", "8_2024-04-08_09-46-12")]
for base, r0, r1 in VIDEOS:
    d = load_csv(base + "_LocationOutput.csv"); pb = open_playback(d); ref = load_reference(d).astype(float)
    X, Y = d.df.X.to_numpy(), d.df.Y.to_numpy(); r1 = min(r1, d.n_frames)
    res = []; seen = 0
    with VideoReader(pb.video, pb.prep) as rd:
        for i, fr in rd.frames(pb.start + r0, pb.start + r1):
            r = i - pb.start
            if fr is None or r % 3 or not np.isfinite(X[r]): continue
            hh, ww = min(fr.shape[0], ref.shape[0]), min(fr.shape[1], ref.shape[1])
            got = ear_position(fr[:hh, :ww], ref[:hh, :ww], X[r], Y[r])
            if got is None: continue
            t, n, s, ends = got; seen += 1
            if s["tail"] is None or s["tail_strength"] < 0.9 or t is None: 
                res.append((np.nan, np.nan, t is not None)); continue
            a, b = ends
            nose_is_a = np.hypot(*(a - s["tail_base"])) > np.hypot(*(b - s["tail_base"]))
            tn = t if nose_is_a else 1 - t          # 1 = at the nose end
            res.append((tn, n / s["area"], True))
    res = np.array(res, float); tn = res[:, 0]; ok = np.isfinite(tn)
    line = f"{os.path.basename(base)[:21]:21s} frames {seen:4d} | lighter spots found in {100*res[:,2].mean():3.0f}% | with a long tail: {int(ok.sum()):4d}"
    if ok.sum() > 20:
        line += f" | spots toward the nose end: {100*np.mean(tn[ok] > 0.5):5.1f}% (median position {np.median(tn[ok]):.2f})"
        for m in (0.08, 0.15):
            sure = ok & (np.abs(tn - 0.5) > m)
            line += f" | when off-center by >{m}: {100*np.mean(tn[sure] > 0.5):5.1f}% of {int(sure.sum())}"
    print(line, flush=True)
