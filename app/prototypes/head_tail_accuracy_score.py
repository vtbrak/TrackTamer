import sys, os, numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the app folder
from core import load_csv
from core.playback import open_playback
from core.video import prepare
SP = sys.argv[1]; z = np.load(f"{SP}/pts.npz"); H, R, C = z["H"], z["R"], z["C"]
W = 55; cm = 0.107
d = load_csv("Examples/1_2026-06-26_14-03-15_LocationOutput.csv"); cm = float(d.settings["Scale_cm_per_px"])
L = {757:(29,36,76,76), 822:(77,26,38,79), 865:(54.4,26.6,50,79), 950:(41,32.4,67.4,79),
     960:(22.6,58,83,55), 1053:(50.6,27,72,75), 1088:(67,25.6,66,77), 1165:(36.6,23.6,72,79),
     1238:(26,55,78,41), 1572:(51,78,64,41), 1582:(20,51.6,88,55), 1723:(90,53,29,52.4),
     1743:(90,49,25.6,59), 1945:(74.4,23.6,37.6,78), 1972:(86.4,55.6,32.4,64.4), 1975:(89,56.4,30.4,61.6),
     2007:(43,91,65,31), 2129:(61,17,56.4,82), 2187:(74,43,36.6,71), 2313:(55,19,52.4,81),
     2341:(60,78,44,33), 2438:(61,72.4,48,11), 2475:(44,77,60,30), 2510:(72,36,23.6,84),
     2630:(53,32,61.6,80), 2693:(89,72.4,25,37), 2739:(84.4,32.4,32.4,79), 2857:(21,49.6,87,60)}
EMPTY = [447,485,509,526,564,599,628,694]
print("empty frames with points reported:", [r for r in EMPTY if np.isfinite(H[r,0])], "of", len(EMPTY))
rows = []; 
for r,(nx,ny,rx,ry) in L.items():
    o = np.round(C[r]) - W
    tn, tr = o + (nx,ny), o + (rx,ry)
    if not np.isfinite(H[r,0]): rows.append((r,None,None,None)); continue
    en, er = np.hypot(*(H[r]-tn)), np.hypot(*(R[r]-tr))
    flip = np.hypot(*(H[r]-tr)) < en
    # facing direction error (center->nose)
    a = np.degrees(np.arctan2(*(H[r]-C[r])[::-1]) - np.arctan2(*(tn-C[r])[::-1])); a = abs((a+180)%360-180)
    rows.append((r,en*cm,er*cm,flip,a, np.hypot(*(tn-tr))*cm))
miss = [x[0] for x in rows if x[1] is None]; ok = [x for x in rows if x[1] is not None]
fl = [x for x in ok if x[3]]; good = [x for x in ok if not x[3]]
print(f"animal in picture: {len(rows)}; no points: {miss}; nose and rear swapped: {[x[0] for x in fl]}")
for x in ok: print(f"  row {x[0]:5d} nose err {x[1]:4.2f} cm  rear err {x[2]:4.2f} cm  facing err {x[4]:5.1f} deg {'SWAPPED' if x[3] else ''}")
en = np.array([x[1] for x in good]); er = np.array([x[2] for x in good]); fa = np.array([x[4] for x in good])
print(f"right way round: {len(good)}/{len(ok)}")
print(f"nose error cm: median {np.median(en):.2f} mean {en.mean():.2f} max {en.max():.2f}; within 0.5 cm {np.mean(en<=.5)*100:.0f}%, within 1 cm {np.mean(en<=1)*100:.0f}%")
print(f"rear error cm: median {np.median(er):.2f} mean {er.mean():.2f} max {er.max():.2f}; within 0.5 cm {np.mean(er<=.5)*100:.0f}%, within 1 cm {np.mean(er<=1)*100:.0f}%")
print(f"facing error deg: median {np.median(fa):.1f} max {fa.max():.1f}; within 15 deg {np.mean(fa<=15)*100:.0f}%")
print(f"true nose-to-rear length cm: median {np.median([x[5] for x in ok]):.1f}; scale {cm:.4f} cm/px")
# picture: program points (filled) vs hand marks (rings)
pb = open_playback(d); cap = cv2.VideoCapture(pb.video); tiles = []; S = 4
for r,(nx,ny,rx,ry) in L.items():
    cap.set(cv2.CAP_PROP_POS_FRAMES, pb.start + r); _, fr = cap.read()
    g = cv2.cvtColor(prepare(fr, pb.prep), cv2.COLOR_GRAY2BGR)
    pad = cv2.copyMakeBorder(g, W, W, W, W, cv2.BORDER_REPLICATE)
    c = np.round(C[r]).astype(int); t = cv2.resize(pad[c[1]:c[1]+2*W, c[0]:c[0]+2*W], None, fx=S, fy=S, interpolation=cv2.INTER_CUBIC)
    P = lambda p: tuple(int(v) for v in ((np.asarray(p) - (c - W)) * S))
    cv2.circle(t, (int(nx*S), int(ny*S)), 9, (0,0,255), 2); cv2.circle(t, (int(rx*S), int(ry*S)), 9, (255,160,0), 2)
    if np.isfinite(H[r,0]):
        cv2.circle(t, P(H[r]), 4, (0,0,255), -1); cv2.circle(t, P(R[r]), 4, (255,160,0), -1)
    cv2.circle(t, P(C[r]), 4, (0,230,255), -1)
    cv2.putText(t, f"frame {r+1}", (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,0), 2)
    tiles.append(t)
while len(tiles) % 7: tiles.append(np.full_like(tiles[0], 255))
cv2.imwrite(f"{SP}/accuracy.png", np.vstack([np.hstack(tiles[i:i+7]) for i in range(0, len(tiles), 7)]))
