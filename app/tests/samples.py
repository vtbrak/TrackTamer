"""The test data: real videos tracked in this app and their tracking files,
in the project's Examples folder (beside the app folder; gitignored; user, 2026-11-05).

- EPM: 6_2024-04-01_11-49-23 (Elevated Plus Maze, 16.64 fps)
- OF:  1_2026-08-17_13-27-03 (Open Field, 9.84 fps, 65 min)
- OBJECT_VIDEO: 1_2026-06-26_14-03-15.mp4 (object recognition, not tracked)

The practice clip (user, 2026-11-10: ezTrack's practice videos are gone, so
the plus maze example stands in): `practice_clip()` cuts a short clip from
the EPM example for the tests that set up and track a video in the GUI.
"""
import os
import sys

import scratch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the "app" folder
EXAMPLES = os.path.join(os.path.dirname(ROOT), "Examples")            # beside it
EPM = os.path.join(EXAMPLES, "6_2024-04-01_11-49-23_LocationOutput.csv")
OF = os.path.join(EXAMPLES, "1_2026-08-17_13-27-03_LocationOutput.csv")
EPM_VIDEO = os.path.join(EXAMPLES, "6_2024-04-01_11-49-23.mp4")
OF_VIDEO = os.path.join(EXAMPLES, "1_2026-08-17_13-27-03.mp4")
OBJECT_VIDEO = os.path.join(EXAMPLES, "1_2026-06-26_14-03-15.mp4")
ASR_CLIP = os.path.join(EXAMPLES, "ASR videos from paper",
                        "1-s2.0-S0165027025001384-mmc10.mp4")


def require(*paths) -> None:
    """Stop the test with a clear message if example files are missing."""
    missing = [os.path.basename(p) for p in paths if not os.path.exists(p)]
    if missing:
        sys.exit("Example files missing from the Examples folder: " + ", ".join(missing))


PRACTICE_FRAMES = 1000          # frames in the practice clip
PRACTICE_SIZE = (1280, 720)     # enlarged from 800 x 600 so shapes drawn at
                                # set places in the tests fit inside it


def practice_clip() -> str | None:
    """A short practice video for the tests that drive the setup window and
    Track: 1,000 frames of the plus maze example from just after the animal
    is placed, enlarged to 1280 x 720, at the example's own frame rate.
    Made once and kept in app/tests/.tmp/cache (remade if the
    example changes). Copy it before use: tests write their outputs beside
    the video. None if the example video is missing."""
    if not os.path.exists(EPM_VIDEO):
        return None
    import cv2
    stamp = int(os.stat(EPM_VIDEO).st_mtime)
    folder = scratch.CACHE      # on the project's drive, kept between runs
    path = os.path.join(folder, f"Practice_Clip_{stamp}.mp4")
    if os.path.exists(path):
        return path
    os.makedirs(folder, exist_ok=True)
    cap = cv2.VideoCapture(EPM_VIDEO)
    part = path + ".part.mp4"
    out = cv2.VideoWriter(part, cv2.VideoWriter_fourcc(*"mp4v"),
                          cap.get(cv2.CAP_PROP_FPS) or 20.0, PRACTICE_SIZE)
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 700)
        written = 0
        while written < PRACTICE_FRAMES:
            ok, frame = cap.read()
            if not ok:
                break
            out.write(cv2.resize(frame, PRACTICE_SIZE))
            written += 1
    finally:
        cap.release()
        out.release()
    if written < PRACTICE_FRAMES:
        os.remove(part)
        return None
    os.replace(part, path)
    return path
