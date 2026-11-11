"""Trial of the app's own tracking path (make_job -> run_job) on the new videos."""
import sys, os, time, json, numpy as np, cv2
sys.path.insert(0, os.getcwd())
from core.tracking import TrackingParams
from core.track_run import make_job, run_job
from core.video import video_info
from core.video_setup import VideoSetup
from core.playback import open_playback, FrameSource
from core import pose
SP = sys.argv[1]; only = sys.argv[2:]
OF, EPM, OBJ = "Open Field", "Elevated Plus Maze", "Object Recognition"
VIDEOS = [  # name, test, crop (full-size x0,y0,x1,y1) or None, first frame, frames
    ("2_2023-01-29_10-56-37", OF, (183, 17, 742, 533), 1200, 5000),
    ("2_2023-02-09_11-04-32", OF, (183, 17, 742, 533), 1200, 5000),
    ("2_2023-03-30_11-11-53", OF, (183, 17, 742, 533), 1200, 5000),
    ("6_2023-03-26_15-19-33", EPM, (158, 0, 708, 600), 400, 99999),
    ("6_2023-11-01_10-43-52", EPM, None, 400, 99999),
    ("6_2024-03-30_09-37-12", EPM, None, 400, 99999),
    ("7_2023-08-28_12-49-34", OBJ, (158, 25, 733, 550), 400, 99999),
    ("7_2023-10-03_11-42-29", OBJ, (158, 25, 733, 550), 400, 99999),
    ("8_2023-06-06_10-32-11", OBJ, (83, 33, 667, 558), 400, 99999),
    ("8_2024-04-08_09-46-12", OBJ, (108, 42, 633, 550), 400, 99999),
]
for name, test, crop, start, n in VIDEOS:
    if only and name not in only: continue
    link = f"{SP}/trial/{name}.mp4"
    if not os.path.exists(link): os.symlink(os.path.abspath(f"Examples/{name}.mp4"), link)
    info = video_info(link)
    s = VideoSetup(link, info); s.start = start; s.end = min(start + n, info.frame_count); s.crop = crop
    if test == EPM:   # stand-in for drawn regions: the whole picture, kept to the bright floor
        w, h = info.width, info.height
        s.regions = {"center": ([0, w, w, 0], [0, 0, h, h])}
    job = make_job(s, TrackingParams(), 1.0, 50, test if test != OBJ else OF)
    t = time.time(); data, csv = run_job(job); dt = time.time() - t
    df = data.df; have = df.Nose_X.notna().to_numpy()
    L = np.hypot(df.Nose_X - df.Rear_X, df.Nose_Y - df.Rear_Y)
    jump = np.hypot(df.Nose_X.diff(), df.Nose_Y.diff()); Lm = float(np.nanmedian(L))
    step = np.hypot(df.X.diff(), df.Y.diff())
    # a swap shows as the nose and rear trading places between two frames
    swap = (np.hypot(df.Nose_X - df.Rear_X.shift(), df.Nose_Y - df.Rear_Y.shift()) < Lm * 0.3) & (jump > Lm * 0.6)
    print(f"{name} {test:19s} frames {len(df):5d} {len(df)/dt:4.0f} fps | points {100*have.mean():5.1f}% | "
          f"nose-rear median {Lm:4.0f} px (5-95%: {np.nanpercentile(L,5):.0f}-{np.nanpercentile(L,95):.0f}) | "
          f"nose jumps > half length {100*np.nanmean(jump > Lm/2):.2f}% | end swaps between frames {int(swap.sum())}", flush=True)
    pb = open_playback(data); src = FrameSource(pb); rng = np.random.default_rng(11)
    rows = np.sort(rng.choice(np.flatnonzero(df.X.notna().to_numpy()), 18, replace=False)); tiles = []
    W = int(max(50, Lm * 0.95)); S = max(2, 400 // (2 * W))
    for r in rows:
        img = src.frame(int(r)); pad = cv2.copyMakeBorder(img, W, W, W, W, cv2.BORDER_CONSTANT)
        cx, cy = int(df.X[r]), int(df.Y[r])
        t_ = cv2.resize(pad[cy:cy+2*W, cx:cx+2*W], None, fx=S, fy=S, interpolation=cv2.INTER_CUBIC)
        P = lambda x, y: (int((x - cx + W) * S), int((y - cy + W) * S))
        if have[r]:
            cv2.circle(t_, P(df.Nose_X[r], df.Nose_Y[r]), 7, (0, 0, 255), 2); cv2.circle(t_, P(df.Rear_X[r], df.Rear_Y[r]), 7, (255, 160, 0), 2)
        cv2.circle(t_, P(df.X[r], df.Y[r]), 3, (0, 230, 255), -1)
        cv2.putText(t_, f"{r+1}", (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2); tiles.append(t_)
    tiles = [cv2.resize(t, (400, 400)) for t in tiles]
    cv2.imwrite(f"{SP}/trial/{name}.png", np.vstack([np.hstack(tiles[i:i+6]) for i in range(0, 18, 6)]))
