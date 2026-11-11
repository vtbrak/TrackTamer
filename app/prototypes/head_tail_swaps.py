import sys, os, numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the app folder
from core import load_csv
from core.playback import open_playback, FrameSource
SP, name = sys.argv[1], sys.argv[2]
d = load_csv(f"{SP}/trial/{name}_LocationOutput.csv"); df = d.df; pb = open_playback(d); src = FrameSource(pb)
L = np.hypot(df.Nose_X - df.Rear_X, df.Nose_Y - df.Rear_Y); Lm = float(np.nanmedian(L))
jump = np.hypot(df.Nose_X.diff(), df.Nose_Y.diff())
swap = np.flatnonzero(((np.hypot(df.Nose_X - df.Rear_X.shift(), df.Nose_Y - df.Rear_Y.shift()) < Lm * 0.3) & (jump > Lm * 0.6)).to_numpy())
print(name, "swaps at", swap[:60].tolist())
pick = swap[np.linspace(0, len(swap) - 1, min(9, len(swap))).astype(int)]; tiles = []
W = int(max(50, Lm * 0.95)); S = 300 / (2 * W)
for r in pick:
    for q in (r - 1, r):
        img = src.frame(int(q)); pad = cv2.copyMakeBorder(img, W, W, W, W, cv2.BORDER_CONSTANT)
        cx, cy = int(df.X[r]), int(df.Y[r])
        t = cv2.resize(pad[cy:cy+2*W, cx:cx+2*W], (300, 300), interpolation=cv2.INTER_CUBIC)
        P = lambda x, y: (int((x - cx + W) * S), int((y - cy + W) * S))
        if np.isfinite(df.Nose_X[q]):
            cv2.circle(t, P(df.Nose_X[q], df.Nose_Y[q]), 6, (0, 0, 255), 2); cv2.circle(t, P(df.Rear_X[q], df.Rear_Y[q]), 6, (255, 160, 0), 2)
        cv2.putText(t, str(q + 1), (5, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2); tiles.append(t)
while len(tiles) % 6: tiles.append(np.zeros_like(tiles[0]))
cv2.imwrite(f"{SP}/swaps_{name}.png", np.vstack([np.hstack(tiles[i:i+6]) for i in range(0, len(tiles), 6)]))
