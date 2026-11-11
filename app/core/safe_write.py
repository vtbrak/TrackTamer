"""Saving files so a failed save can't destroy what was there (GUI-free).

Every file the program writes beside the user's data (tracking files, motion
index files, scoring, the reference image, the tracked video, exports) is
written under a temporary name first and only then put in place of the real
one. If writing fails partway, or is cancelled, the earlier file is still
there, whole.
"""

from __future__ import annotations

import os
from contextlib import contextmanager


def saving_path(path: str) -> str:
    """The temporary name `path` is written under: beside it, with the same
    ending (video and workbook writers pick their format from it)."""
    stem, ext = os.path.splitext(path)
    return f"{stem}.saving{ext}"


@contextmanager
def replacing(path: str):
    """`with replacing(path) as tmp:` write the new file to `tmp`. Leaving
    the block normally puts it in place of `path` in one step. Leaving it by
    an error removes `tmp` and leaves `path` as it was. If nothing was
    written to `tmp`, `path` is left alone.

    Putting it in place can itself fail (on Windows, when `path` is open in
    another program such as Excel): that raises PermissionError, `tmp` is
    removed and `path` is untouched."""
    tmp = saving_path(path)
    try:
        yield tmp
        if os.path.exists(tmp):
            os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def write_csv(df, path: str) -> None:
    """Write a table as CSV (no index column) through `replacing`."""
    with replacing(path) as tmp:
        df.to_csv(tmp, index=False)


def image_bytes(image, ending: str = ".png") -> bytes:
    """An image encoded for a file with that ending. Encoding here and
    writing with Python's own file handling, rather than OpenCV's `imwrite`,
    works for folder names with accented or non-English letters on Windows,
    which `imwrite` can't be relied on for. ValueError if it can't be made."""
    import cv2
    ok, data = cv2.imencode(ending, image)
    if not ok:
        raise ValueError("Couldn't make the image.")
    return data.tobytes()
