"""Jumping to a frame must give the same frame as reading the video in order.

OpenCV's own jump (`cap.set(cv2.CAP_PROP_POS_FRAMES, n)`) lands a frame or so
off in stretches of videos whose frames aren't evenly spaced in time, which
is every camera recording in Examples. Tracking reads in order, so a jump
that is off puts the tracked marks on a neighbouring frame. This checks that
`VideoReader.read_at`, the first frame tracking reads (`VideoReader.frames`
from a start frame) and the playback window's `FrameSource` give exactly the
in-order frames, on the example videos that are there (skipped when none
are).

Run from the project folder:  .venv/bin/python tests/test_seek.py
"""
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import video
from core.playback import FrameSource, Playback
from samples import EPM_VIDEO, EXAMPLES

# The EPM example, and the three videos the problem was first seen on.
VIDEOS = [EPM_VIDEO] + [os.path.join(EXAMPLES, name) for name in (
    "8_2023-06-06_10-32-11.mp4", "6_2023-11-01_10-43-52.mp4", "2_2023-01-29_10-56-37.mp4")]
VIDEOS = [v for v in VIDEOS if os.path.exists(v)]
if not VIDEOS:
    print("skipped: none of the example videos are in the Examples folder")
    sys.exit(0)

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)


def in_order(path, wanted):
    """{index: grayscale frame} for the `wanted` frames, read in order from
    the first frame with no jump at all, and how many frames were read."""
    cap = cv2.VideoCapture(path)
    out, index, last = {}, 0, max(wanted)
    while index <= last and cap.grab():
        if index in wanted:
            out[index] = video.prepare(cap.retrieve()[1], video.Prep())
        index += 1
    cap.release()
    return out, index


def same(a, b):
    return a is not None and b is not None and np.array_equal(a, b)


for path in VIDEOS:
    name = os.path.basename(path)
    print(f"--- {name}")
    info = video.video_info(path)
    times = video.frame_times(path)
    check("the frames' own timestamps are listed, one per frame, in order",
          times is not None and abs(len(times) - info.frame_count) <= 2
          and bool(np.all(np.diff(times) > 0)))
    if times is None:
        continue
    rng = np.random.default_rng(0)
    last = len(times) - 2          # the very last stored frame often doesn't decode
    samples = sorted({int(i) for i in np.linspace(0, last, 60)})
    wanted = set(samples) | ({400, 401} if last > 401 else set())
    wanted |= {i + 1 for i in samples if i < last}
    truth, read = in_order(path, wanted)
    check("read in order to the last sampled frame", read == last + 1 and len(truth) == len(wanted))

    with video.VideoReader(path) as r:
        order = [samples[i] for i in rng.permutation(len(samples))]
        wrong = [i for i in order if not same(r.read_at(i), truth.get(i))]
        check(f"read_at gives the in-order frame at {len(samples)} jumps, back and forth"
              + (f" (wrong at {sorted(wrong)[:8]})" if wrong else ""), not wrong)
        check("read_at past the end gives None", r.read_at(info.frame_count + 50) is None)
        off = [i for i in samples if not same(r.read_near(i), truth.get(i))]
    print(f"     (OpenCV's own jump is off at {len(off)} of {len(samples)} of these frames)")

    # Tracking starts on exactly the start frame chosen in setup and reads on
    # in order; playback row r is frame start + r. Start where OpenCV's own
    # jump is off, when there is such a place.
    span = min(1500, last - 1)
    starts = [400] + [i for i in off if 0 < i <= last - span][:1]
    for start in starts:
        if start > last - span:
            continue
        with video.VideoReader(path) as r:
            tracked = dict(r.frames(start, start + span))     # what tracking reads
            shown = r.read_at(start)                           # what setup shows
        check(f"tracking from start frame {start} begins on that frame and the next follows",
              same(tracked.get(start), truth.get(start)) and same(shown, truth.get(start))
              and same(tracked.get(start + 1), truth.get(start + 1)))
        rows = ([0, 1, 2, 3, 20, 45, 46, 500, 499, 498, 530, 531, 900, 60, 1499 % span, 0]
                + [int(v) for v in rng.integers(0, span, 40)])
        rows = [row for row in rows if row < span]
        source = FrameSource(Playback(None, path, video.Prep(), start, info.fps))
        try:
            wrong = []
            for row in rows:
                frame = source.frame(row)
                gray = None if frame is None else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if not same(gray, tracked.get(start + row)):
                    wrong.append(row)
        finally:
            source.close()
        check(f"playback from start frame {start}: {len(rows)} rows shown on the frames "
              "tracking read" + (f" (wrong at rows {wrong[:8]})" if wrong else ""), not wrong)

# A damaged video: its timestamps stop at the damage (708 of 6,432 frames in
# this example). That short list must not be trusted, or every frame after
# the damage looks as if it doesn't exist and tracking silently stops there
# (it tracked 308 frames of a 6,000-frame session).
DAMAGED = os.path.join(EXAMPLES, "6_2023-03-26_15-19-33.mp4")
if os.path.exists(DAMAGED):
    info = video.video_info(DAMAGED)
    check("a damaged video's cut-short timestamp list isn't used",
          video.frame_times(DAMAGED) is None)
    with video.VideoReader(DAMAGED) as reader:
        rows = [(i, frame is not None) for i, frame in reader.frames(400, 2000)]
    readable = sum(ok for _i, ok in rows)
    check(f"reading carries on past the damage: {len(rows)} of 1,600 rows, "
          f"{readable} readable, the rest kept as unreadable rows",
          len(rows) == 1600 and rows[0][0] == 400 and rows[-1][0] == 1999
          and 0 < readable < 1600)
    from core import tracking
    blank = np.full((info.height, info.width), 128.0)
    result = tracking.track_video(DAMAGED, blank, tracking.TrackingParams(), start=400,
                                  end=2000)
    check("so tracking covers the whole stretch asked for, with the unreadable frames marked",
          len(result.df) == 1600 and result.missing_at_end == 0
          and result.unreadable == 1600 - readable)
    # A session that ends inside the damage: the unreadable run at its end is
    # dropped (as at the end of any file), and tracking says how much is missing.
    cut = tracking.track_video(DAMAGED, blank, tracking.TrackingParams(), start=400,
                               end=1400)
    check(f"a session ending inside the damage reports the frames it's short by "
          f"({cut.missing_at_end} of 1,000)",
          len(cut.df) + cut.missing_at_end == 1000 and cut.missing_at_end > 500)
else:
    print("skipped the damaged-video checks (that example isn't in the Examples folder)")
whole = video.frame_times(VIDEOS[0])
check("a whole video's timestamp list is still used (one per frame)",
      whole is not None and len(whole) == video.video_info(VIDEOS[0]).frame_count)

print("\nFAILED" if fails else "\nall ok", f"({fails} failed)" if fails else "")
sys.exit(1 if fails else 0)
