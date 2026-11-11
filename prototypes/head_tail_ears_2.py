"""Ear test, second pass: small light blobs inside the body (top-hat), blobs limited in size."""
import sys, os, numpy as np, cv2
sys.path.insert(0, os.getcwd())
from core import load_csv, pose
from core.playback import open_playback, load_reference
from core.video import VideoReader
SP = sys.argv[1]

def ear_t(frame, ref, cx, cy, level, max_blob, kern):
    mask, core, faint, (x0, y0) = pose.outline(frame, ref, cx, cy)
    if mask is None: return None
    s = pose._shape(mask, faint)
    if s is None: return None
    hh, ww = mask.shape
    f = frame[y0:y0+hh, x0:x0+ww].astype(np.float32); r = ref[y0:y0+hh, x0:x0+ww].astype(np.float32)
    dif = np.clip(r - f, 0, 255); body = s["body"]; root = np.sqrt(s["area"])
    contrast = float(np.median(dif[body == 1]))
    filled = cv2.morphologyEx(body, cv2.MORPH_CLOSE, pose._kernel(round(root * 0.35)))
    inner = cv2.erode(filled, np.ones((3, 3), np.uint8))
    dark = float(np.median(f[body == 1]))
    img = np.where(filled == 1, f, dark).astype(np.float32)        # the floor round the body doesn't count
    spots = cv2.morphologyEx(img, cv2.MORPH_TOPHAT, pose._kernel(round(root * kern)))
    light = ((spots > level * contrast) & (inner == 1)).astype(np.uint8)
    n, lab, st, cent = cv2.connectedComponentsWithStats(light, 8)
    keep = np.zeros_like(light)
    for k in range(1, n):
        if 3 <= st[k, cv2.CC_STAT_AREA] <= max_blob * s["area"]:
            keep[lab == k] = 1
    a, b = s["ends"]; axis = (a - b) / max(np.hypot(*(a - b)), 1e-6)
    ys, xs = np.nonzero(body); t_all = (np.column_stack([xs, ys]) - b) @ axis; L = t_all.max() - t_all.min()
    if keep.sum() < 3 or L < 5: return (None, s, a, b)
    ly, lx = np.nonzero(keep); w = spots[ly, lx]
    t = float((((np.column_stack([lx, ly]) - b) @ axis - t_all.min()) * w).sum() / w.sum() / L)
    return (t, s, a, b)

names = ["Examples/1_2026-06-26_14-03-15", "Examples/1_2026-08-17_13-27-03", "Examples/6_2024-04-01_11-49-23"] + [f"{SP}/trial/{n}" for n in
         ("6_2023-03-26_15-19-33", "6_2023-11-01_10-43-52", "6_2024-03-30_09-37-12", "2_2023-01-29_10-56-37", "2_2023-03-30_11-11-53", "7_2023-08-28_12-49-34", "8_2023-06-06_10-32-11", "8_2024-04-08_09-46-12")]
only = sys.argv[2:]
for base in names:
    if only and not any(o in base for o in only): continue
    d = load_csv(base + "_LocationOutput.csv"); pb = open_playback(d); ref = load_reference(d).astype(float)
    X, Y = d.df.X.to_numpy(), d.df.Y.to_numpy(); r0 = 800 if "06-26" in base else 0; r1 = min(r0 + 4500, d.n_frames)
    frames = []
    with VideoReader(pb.video, pb.prep) as rd:
        for i, fr in rd.frames(pb.start + r0, pb.start + r1):
            r = i - pb.start
            if fr is not None and r % 4 == 0 and np.isfinite(X[r]):
                hh, ww = min(fr.shape[0], ref.shape[0]), min(fr.shape[1], ref.shape[1]); frames.append((fr[:hh, :ww], X[r], Y[r]))
    refc = ref[:frames[0][0].shape[0], :frames[0][0].shape[1]]
    out = []
    for level, max_blob, kern in ((0.15, 0.06, 0.25), (0.25, 0.06, 0.25), (0.25, 0.04, 0.2), (0.4, 0.06, 0.25)):
        tn = []; found = 0; total = 0
        for fr, x, y in frames:
            got = ear_t(fr, refc, x, y, level, max_blob, kern)
            if got is None: continue
            t, s, a, b = got; total += 1; found += t is not None
            if t is None or s["tail"] is None or s["tail_strength"] < 0.9: continue
            nose_is_a = np.hypot(*(a - s["tail_base"])) > np.hypot(*(b - s["tail_base"]))
            tn.append(t if nose_is_a else 1 - t)
        tn = np.array(tn); sure = np.abs(tn - 0.5) > 0.1
        out.append(f"[{level},{max_blob},{kern}] found {100*found/max(total,1):3.0f}% nose-end {100*np.mean(tn>0.5):3.0f}% / sure {100*np.mean(tn[sure]>0.5):3.0f}% of {int(sure.sum())} (n={len(tn)})")
    print(os.path.basename(base)[:21], " | ".join(out), flush=True)
