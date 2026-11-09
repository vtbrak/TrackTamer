"""The test data: real videos tracked in this app and their tracking files,
in the project's Examples folder (gitignored; user, 2026-11-05).

- EPM: 6_2024-04-01_11-49-23 (Elevated Plus Maze, 16.64 fps)
- OF:  1_2026-08-17_13-27-03 (Open Field, 9.84 fps, 65 min)
- OBJECT_VIDEO: 1_2026-06-26_14-03-15.mp4 (object recognition, not tracked)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "Examples")
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
