import os, sys, numpy as np, cv2
sys.path.insert(0, os.getcwd()); sys.path.insert(0, sys.argv[1])
import proto
from core import load_csv
from core.objects import file_objects, distance_px, load_scoring
from core.playback import open_playback
from core.video import prepare
SP = sys.argv[1]
csv = "Examples/1_2026-06-26_14-03-15_LocationOutput.csv"
d = load_csv(csv); fps = 9.84; cm = float(d.settings["Scale_cm_per_px"])
out = proto.run(csv, d.n_frames, 0)
n = d.n_frames
H = np.full((n, 2), np.nan); R = np.full((n, 2), np.nan)
for o in out:
    if o.get("head"): H[o["row"]] = o["head"]; R[o["row"]] = o["rear"]
C = d.df[["X", "Y"]].to_numpy(float)
have = np.isfinite(H[:, 0]) & np.isfinite(C[:, 0])
print(f"frames {n}, with head {have.sum()} ({100*have.mean():.0f}%)")
hc = np.hypot(*(H - C).T) * cm
print(f"head to center distance: median {np.nanmedian(hc):.1f} cm, 5th-95th pct {np.nanpercentile(hc,5):.1f}-{np.nanpercentile(hc,95):.1f} cm")
objs = file_objects(d); zone = distance_px(d, 4.0)[0]; zone2 = distance_px(d, 2.0)[0]
sc = load_scoring(d)
def runs(mask):
    k = np.flatnonzero(np.diff(np.concatenate([[0], mask.astype(int), [0]])))
    return list(zip(k[0::2], k[1::2]))
for o in objs:
    dc = np.hypot(C[:, 0] - o.x, C[:, 1] - o.y) - o.r
    dh = np.hypot(H[:, 0] - o.x, H[:, 1] - o.y) - o.r
    c4, h4, h2 = (dc <= zone) & have, (dh <= zone) & have, (dh <= zone2) & have
    print(f"\n{o.name} ({o.kind}):")
    print(f"  center within 4 cm: {c4.sum()/fps:6.1f} s in {len(runs(c4)):3d} visits")
    print(f"  nose   within 4 cm: {h4.sum()/fps:6.1f} s in {len(runs(h4)):3d} visits")
    print(f"  nose   within 2 cm: {h2.sum()/fps:6.1f} s in {len(runs(h2)):3d} visits")
    print(f"  nose within 2 cm but center NOT within 4 cm: {(h2 & ~c4).sum()/fps:.1f} s  |  center within 4 cm but nose NOT within 4 cm: {(c4 & ~h4).sum()/fps:.1f} s")
    for b in [b for b in sc.bouts if b.object == o.name]:
        s = slice(b.start, b.end + 1)
        print(f"  your scored interaction frames {b.start+1}-{b.end+1}: nose {np.nanmedian(dh[s])*cm:5.1f} cm from the object (closest {np.nanmin(dh[s])*cm:.1f}), center {np.nanmedian(dc[s])*cm:5.1f} cm; nose within 2 cm in {100*np.nanmean(dh[s] <= zone2):.0f}% of its frames")
# picture: frames from the scored bouts and other approach moments, with center (yellow), nose (red), tail base (blue), zone rings
pb = open_playback(d); cap = cv2.VideoCapture(pb.video)
picks = [b.start + (b.end - b.start) // 2 for b in sc.bouts]
o2 = objs[1]; dh2 = np.hypot(H[:, 0] - o2.x, H[:, 1] - o2.y) - o2.r; dc2 = np.hypot(C[:, 0] - o2.x, C[:, 1] - o2.y) - o2.r
picks += list(np.flatnonzero((dh2 <= zone2) & (dc2 > zone))[::12][:5])
o1 = objs[0]; dh1 = np.hypot(H[:, 0] - o1.x, H[:, 1] - o1.y) - o1.r; dc1 = np.hypot(C[:, 0] - o1.x, C[:, 1] - o1.y) - o1.r
picks += list(np.flatnonzero((dc1 <= zone) & (dh1 > zone))[::10][:4])
tiles = []
for r in picks[:12]:
    cap.set(cv2.CAP_PROP_POS_FRAMES, pb.start + int(r)); ok, fr = cap.read()
    g = cv2.cvtColor(prepare(fr, pb.prep), cv2.COLOR_GRAY2BGR); g = cv2.resize(g, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    P = lambda p: (int(p[0] * 3), int(p[1] * 3))
    for o in objs:
        cv2.circle(g, P((o.x, o.y)), int(o.r * 3), (26, 159, 255), 2)
        cv2.circle(g, P((o.x, o.y)), int((o.r + zone) * 3), (255, 255, 255), 1)
        cv2.circle(g, P((o.x, o.y)), int((o.r + zone2) * 3), (200, 200, 200), 1)
    if np.isfinite(H[r, 0]):
        cv2.line(g, P(R[r]), P(H[r]), (255, 255, 255), 1)
        cv2.circle(g, P(H[r]), 7, (0, 0, 255), -1); cv2.circle(g, P(R[r]), 7, (255, 160, 0), -1)
    cv2.circle(g, P(C[r]), 7, (0, 230, 255), -1)
    cx, cy = P(C[r]); w = 190
    pad = cv2.copyMakeBorder(g, w, w, w, w, cv2.BORDER_CONSTANT)
    t = pad[cy:cy + 2 * w, cx:cx + 2 * w].copy()
    cv2.putText(t, f"frame {r+1}", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    tiles.append(t)
while len(tiles) % 4: tiles.append(np.zeros_like(tiles[0]))
cv2.imwrite(f"{SP}/compare.png", np.vstack([np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)]))
