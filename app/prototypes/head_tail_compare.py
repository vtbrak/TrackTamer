"""Before (no ear clue) vs after: which frames changed which end is the nose,
and what happened to the frames judged by eye."""
import sys, os, numpy as np, pandas as pd
SP = sys.argv[1]
JUDGED = {  # frame numbers (1-based) judged by eye on the 'before' build: right / wrong
    "6_2023-11-01_10-43-52": ([156, 499, 707, 727, 2184, 2712, 2954, 4108, 4329, 5049, 5164, 3268], [384, 805, 3206]),
    "6_2024-03-30_09-37-12": ([151, 703, 778, 2112, 2553, 2623, 2858, 2883, 3101, 3973, 4187, 4995], [371, 4884]),
    "6_2023-03-26_15-19-33": ([1177, 3340, 3410, 3943, 4748, 4960, 5651], [5762]),
    "8_2023-06-06_10-32-11": ([203, 499, 909, 919, 945, 1046, 2840, 3433, 3528, 4170, 5340, 5631, 6566, 6714], [3875, 4251]),
    "2_2023-01-29_10-56-37": ([641, 649, 667, 2005, 2424, 2490, 2713, 2737, 2943, 3001, 3554, 3772, 3974, 4656, 4742], []),
}
for f in sorted(os.listdir(f"{SP}/before")):
    name = f.replace("_LocationOutput.csv", "")
    a = pd.read_csv(f"{SP}/before/{f}", low_memory=False); b = pd.read_csv(f"{SP}/trial/{f}", low_memory=False)
    both = a.Nose_X.notna() & b.Nose_X.notna()
    L = np.hypot(a.Nose_X - a.Rear_X, a.Nose_Y - a.Rear_Y)
    flipped = both & (np.hypot(b.Nose_X - a.Rear_X, b.Nose_Y - a.Rear_Y) < np.hypot(b.Nose_X - a.Nose_X, b.Nose_Y - a.Nose_Y))
    line = f"{name}: nose at the other end in {100*flipped[both].mean():5.1f}% of {int(both.sum())} frames"
    if name in JUDGED:
        right, wrong = JUDGED[name]
        kept = sum(not flipped[r - 1] for r in right if both[r - 1]); fixed = sum(bool(flipped[r - 1]) for r in wrong if both[r - 1])
        line += f" | judged right before: {kept} of {len(right)} still right | judged wrong before: {fixed} of {len(wrong)} now right"
        line += " | broke: " + str([r for r in right if both[r - 1] and flipped[r - 1]]) + " still wrong: " + str([r for r in wrong if both[r - 1] and not flipped[r - 1]])
    print(line)
