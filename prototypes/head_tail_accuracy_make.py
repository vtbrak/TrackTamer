import os, sys, json, numpy as np, cv2
sys.path.insert(0, os.getcwd()); sys.path.insert(0, "prototypes")
import head_tail_feasibility as proto
from core import load_csv
from core.playback import open_playback
from core.video import prepare
SP = sys.argv[1]
csv = "Examples/1_2026-06-26_14-03-15_LocationOutput.csv"
d = load_csv(csv); n = d.n_frames
out = proto.run(csv, n, 0)
H = np.full((n, 2), np.nan); R = np.full((n, 2), np.nan)
for o in out:
    if o.get("head"): H[o["row"]] = o["head"]; R[o["row"]] = o["rear"]
C = d.df[["X", "Y"]].to_numpy(float)
np.savez(f"{SP}/pts.npz", H=H, R=R, C=C)
rng = np.random.default_rng(20261110)
cand = np.flatnonzero(np.isfinite(C[:, 0]))
cand = cand[cand >= 400]
picks = np.sort(rng.choice(cand, 36, replace=False))
json.dump([int(p) for p in picks], open(f"{SP}/picks.json", "w"))
pb = open_playback(d); cap = cv2.VideoCapture(pb.video)
W, S = 55, 5
tiles = []
for r in picks:
    cap.set(cv2.CAP_PROP_POS_FRAMES, pb.start + int(r)); ok, fr = cap.read()
    g = prepare(fr, pb.prep)
    pad = cv2.copyMakeBorder(g, W, W, W, W, cv2.BORDER_REPLICATE)
    cx, cy = int(round(C[r, 0])), int(round(C[r, 1]))
    t = pad[cy:cy + 2 * W, cx:cx + 2 * W]
    t = cv2.cvtColor(cv2.resize(t, None, fx=S, fy=S, interpolation=cv2.INTER_CUBIC), cv2.COLOR_GRAY2BGR)
    ov = t.copy()
    for k in range(0, 2 * W + 1, 10):
        cv2.line(ov, (k * S, 0), (k * S, 2 * W * S), (0, 255, 255), 1)
        cv2.line(ov, (0, k * S), (2 * W * S, k * S), (0, 255, 255), 1)
    t = cv2.addWeighted(ov, 0.35, t, 0.65, 0)
    for k in range(0, 2 * W + 1, 10):
        cv2.putText(t, str(k), (k * S + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
        cv2.putText(t, str(k), (2, k * S + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
    cv2.putText(t, f"row {r}", (200, 2 * W * S - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    cv2.rectangle(t, (0, 0), (2 * W * S - 1, 2 * W * S - 1), (255, 255, 255), 2)
    tiles.append(t)
for i in range(0, 36, 6):
    cv2.imwrite(f"{SP}/label_{i//6}.png", np.vstack([np.hstack(tiles[i:i+3]), np.hstack(tiles[i+3:i+6])]))
print(picks.tolist())
