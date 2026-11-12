"""Where the tests put their temporary files (user, 2026-11-12: the tests had
left 15 GB of copied videos in the computer's temporary folder on the main
disk).

Importing this sends every temporary file and folder a test makes
(`tempfile.mkdtemp`, `TemporaryDirectory`, `gettempdir`) into a folder of its
own for this run, inside `app/tests/.tmp` on the project's drive, and removes
it when the run ends, however it ends short of being killed. A folder left
by a run that was killed is removed by a later run once it's a few hours old.
The practice clip, made once and reused, is kept in `.tmp/cache`.

Every test file imports this first, before anything makes a temporary file.
"""
import atexit
import os
import shutil
import tempfile
import time

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmp")
CACHE = os.path.join(BASE, "cache")
LEFT_OVER_S = 6 * 3600          # a run folder this old belongs to a run that was killed

os.makedirs(BASE, exist_ok=True)
for _name in os.listdir(BASE):
    _path = os.path.join(BASE, _name)
    try:
        if _name.startswith("run-") and time.time() - os.path.getmtime(_path) > LEFT_OVER_S:
            shutil.rmtree(_path, ignore_errors=True)
    except OSError:
        pass

RUN = tempfile.mkdtemp(prefix="run-", dir=BASE)
tempfile.tempdir = RUN
atexit.register(shutil.rmtree, RUN, True)
