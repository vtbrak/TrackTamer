"""Feasibility prototype: head and tail from the animal's silhouette."""
import os, sys, json
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the app folder
from core import load_csv
from core.playback import open_playback, load_reference
from core.video import prepare

def silhouette(gray, ref, cx, cy, win=70, thresh=None):
    """Binary mask of the animal in a window round the tracked point."""
    h, w = gray.shape
    x0, x1 = max(0, int(cx - win)), min(w, int(cx + win))
    y0, y1 = max(0, int(cy - win)), min(h, int(cy + win))
    diff = cv2.subtract(ref[y0:y1, x0:x1], gray[y0:y1, x0:x1])      # dark animal
    if thresh is None:
        thresh, _ = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        thresh = max(thresh, 18)
    mask = (diff > thresh).astype(np.uint8)
    n, lab, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
    if n < 2:
        return None, (x0, y0)
    # the component containing (or nearest to) the tracked point
    px, py = int(cx - x0), int(cy - y0)
    px, py = min(max(px, 0), mask.shape[1] - 1), min(max(py, 0), mask.shape[0] - 1)
    k = lab[py, px]
    if k == 0:
        d = np.hypot(cent[1:, 0] - px, cent[1:, 1] - py); big = stats[1:, cv2.CC_STAT_AREA] > 40
        if not big.any(): return None, (x0, y0)
        d[~big] = 1e9; k = 1 + int(np.argmin(d))
    return (lab == k).astype(np.uint8), (x0, y0)

def pose(mask):
    """Body ends, tail base and tip from a silhouette. None if unusable."""
    area = int(mask.sum())
    if area < 80: return None
    # body = silhouette with thin parts (tail) erased
    k = max(5, int(round(np.sqrt(area) * 0.32)) | 1)
    body = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(body, 8)
    if n < 2: return None
    body = (lab == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    ys, xs = np.nonzero(body)
    pts = np.column_stack([xs, ys]).astype(float); c = pts.mean(0)
    u, s, vt = np.linalg.svd(pts - c, full_matrices=False); axis = vt[0]
    proj = (pts - c) @ axis
    a, b = c + axis * proj.max(), c + axis * proj.min()
    elong = float(s[0] / max(s[1], 1e-6))
    # tail = thin pixels attached to the body
    grown = cv2.dilate(body, np.ones((3, 3), np.uint8))
    thin = (mask == 1) & (grown == 0)
    tail = None
    if thin.sum() >= 6:
        n2, lab2, st2, _ = cv2.connectedComponentsWithStats(thin.astype(np.uint8), 8)
        best = 1 + int(np.argmax(st2[1:, cv2.CC_STAT_AREA]))
        ty, tx = np.nonzero(lab2 == best)
        length = max(np.ptp(tx), np.ptp(ty)) + 1
        if st2[best, cv2.CC_STAT_AREA] >= 6 and length >= 0.25 * np.sqrt(area):
            tp = np.column_stack([tx, ty]).astype(float)
            dist_body = np.hypot(*(tp - c).T)
            base, tip = tp[np.argmin(dist_body)], tp[np.argmax(dist_body)]
            tail = (base, tip, int(len(tp)))
    return {"center": c, "ends": (a, b), "elong": elong, "tail": tail, "area": area,
            "body_len": float(proj.max() - proj.min())}

def run(csv, n_frames=3000, start_row=0, sheet=None, every=None):
    d = load_csv(csv); pb = open_playback(d)
    ref = load_reference(d)
    cap = cv2.VideoCapture(pb.video); cap.set(cv2.CAP_PROP_POS_FRAMES, pb.start + start_row)
    X, Y = d.df["X"].to_numpy(), d.df["Y"].to_numpy()
    rows = range(start_row, min(start_row + n_frames, d.n_frames))
    out = []; head_prev = None; tiles = []
    for r in rows:
        ok, fr = cap.read()
        if not ok: break
        gray = prepare(fr, pb.prep)
        hh, ww = min(gray.shape[0], ref.shape[0]), min(gray.shape[1], ref.shape[1])
        gray, refc = gray[:hh, :ww], ref[:hh, :ww]
        rec = {"row": r, "ok": False}
        if np.isfinite(X[r]):
            m, (x0, y0) = silhouette(gray, refc, X[r], Y[r])
            p = pose(m) if m is not None else None
            if p is not None:
                off = np.array([x0, y0], float)
                a, b = p["ends"][0] + off, p["ends"][1] + off
                rec.update(ok=True, elong=p["elong"], area=p["area"], body_len=p["body_len"], tail=p["tail"] is not None)
                # cue 1: tail
                head_tail = None
                if p["tail"] is not None:
                    base = p["tail"][0] + off
                    head_tail = a if np.hypot(*(a - base)) > np.hypot(*(b - base)) else b
                # cue 2: direction of travel over the next/prev 3 frames
                head_move = None
                r0, r1 = max(r - 2, 0), min(r + 2, d.n_frames - 1)
                v = np.array([X[r1] - X[r0], Y[r1] - Y[r0]])
                if np.all(np.isfinite(v)) and np.hypot(*v) > 8:
                    head_move = a if (a - b) @ v > 0 else b
                rec["agree"] = (None if head_tail is None or head_move is None
                                else bool(np.allclose(head_tail, head_move)))
                head = head_tail if head_tail is not None else head_move
                src = "tail" if head_tail is not None else "move" if head_move is not None else "prev"
                if head is None and head_prev is not None:
                    head = a if np.hypot(*(a - head_prev)) < np.hypot(*(b - head_prev)) else b
                if head is not None:
                    rear = b if np.allclose(head, a) else a
                    if head_prev is not None:
                        rec["jump"] = float(np.hypot(*(head - head_prev)))
                    rec.update(head=head.tolist(), rear=rear.tolist(), src=src)
                    head_prev = head
                if sheet and every and (r - start_row) % every == 0 and len(tiles) < 40:
                    t = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                    cx, cy = int(X[r]), int(Y[r]); w = 60
                    if rec.get("head"):
                        cv2.circle(t, tuple(int(v) for v in rec["head"]), 3, (0, 0, 255), -1)
                        cv2.circle(t, tuple(int(v) for v in rec["rear"]), 3, (255, 160, 0), -1)
                    if p["tail"] is not None:
                        cv2.circle(t, tuple(int(v) for v in (p["tail"][1] + off)), 2, (0, 220, 0), -1)
                    pad = cv2.copyMakeBorder(t, w, w, w, w, cv2.BORDER_CONSTANT)
                    crop = pad[cy:cy + 2 * w, cx:cx + 2 * w]
                    crop = cv2.resize(crop, (240, 240), interpolation=cv2.INTER_NEAREST)
                    cv2.putText(crop, f"{r} {src}", (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
                    tiles.append(crop)
        out.append(rec)
    cap.release()
    if sheet and tiles:
        while len(tiles) % 8: tiles.append(np.zeros_like(tiles[0]))
        cv2.imwrite(sheet, np.vstack([np.hstack(tiles[i:i + 8]) for i in range(0, len(tiles), 8)]))
    ok = [o for o in out if o["ok"]]
    tail = [o for o in ok if o["tail"]]
    both = [o for o in ok if o.get("agree") is not None]
    jumps = np.array([o["jump"] for o in ok if "jump" in o])
    bl = np.median([o["body_len"] for o in ok]) if ok else 0
    cm = float(d.settings.get("Scale_cm_per_px") or 0)
    print(os.path.basename(csv)[:22], f"rows {len(out)}  silhouette {100*len(ok)/max(len(out),1):.0f}%  "
          f"tail seen {100*len(tail)/max(len(ok),1):.0f}%  "
          f"tail vs travel agree {100*np.mean([o['agree'] for o in both]) if both else float('nan'):.0f}% (n={len(both)})  "
          f"head jumps > 1/2 body {100*np.mean(jumps > bl/2) if len(jumps) else 0:.1f}%  "
          f"body length {bl:.0f} px = {bl*cm:.1f} cm  median area {np.median([o['area'] for o in ok]) if ok else 0:.0f} px")
    return out

if __name__ == "__main__":
    SP = sys.argv[1]
    run("Examples/1_2026-06-26_14-03-15_LocationOutput.csv", 2500, 400, f"{SP}/sheet_object.png", 60)
    run("Examples/1_2026-08-17_13-27-03_LocationOutput.csv", 3000, 2000, f"{SP}/sheet_of.png", 75)
    run("Examples/6_2024-04-01_11-49-23_LocationOutput.csv", 3000, 300, f"{SP}/sheet_epm.png", 75)
