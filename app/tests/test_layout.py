"""Checks that the project folder keeps its layout: only the files a user
needs at the top (launchers, README, INSTALL, TESTING, LICENSE), the program
in "app", and the settings file moved over from its old place.

Run from the project folder:  app/.venv/bin/python app/tests/test_layout.py
"""
import json
import os
import subprocess
import sys
import tempfile

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = os.path.dirname(APP)
sys.path.insert(0, APP)

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)

LAUNCHERS = [f"{action} Track Tamer.{ext}" for action in ("Open", "Install", "Uninstall")
             for ext in ("command", "bat")]
TOP_FILES = set(LAUNCHERS) | {"README.md", "INSTALL.md", "TESTING.md", "LICENSE",
                              ".gitignore", ".gitattributes"}
TOP_FOLDERS = {"app", "docs", ".claude"}

try:
    tracked = subprocess.run(["git", "ls-files"], cwd=PROJECT, capture_output=True,
                             text=True, check=True).stdout.splitlines()
except (OSError, subprocess.CalledProcessError):
    tracked = None      # a downloaded copy has no git; check what's on disk instead
if tracked is not None:
    tracked = [t.strip('"') for t in tracked]
    top_files = {t for t in tracked if "/" not in t}
    top_folders = {t.split("/", 1)[0] for t in tracked if "/" in t}
    check("only user files at the top of the project: " + ", ".join(sorted(top_files - TOP_FILES)),
          top_files <= TOP_FILES)
    check("only app, docs and .claude folders: " + ", ".join(sorted(top_folders - TOP_FOLDERS)),
          top_folders <= TOP_FOLDERS)
for name in sorted(TOP_FILES):
    check(f"{name} is at the top", os.path.exists(os.path.join(PROJECT, name)))
for name in ("gui.py", "core", "tests", "requirements.txt", "environment.yml",
             "find_conda.sh", "find_conda.bat"):
    check(f"{name} is in app", os.path.exists(os.path.join(APP, name)))

for name in LAUNCHERS:
    raw = open(os.path.join(PROJECT, name), "rb").read()
    text = raw.decode("utf-8")
    if name.endswith(".bat"):
        check(f"{name} goes to the app folder", 'cd /d "%~dp0app"' in text)
        check(f"{name} has Windows line endings", b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b""))
    else:
        check(f"{name} goes to the app folder", 'cd "$(dirname "$0")/app"' in text)
        check(f"{name} has Mac line endings", b"\r" not in raw)
        check(f"{name} can be double-clicked (executable)", os.access(os.path.join(PROJECT, name), os.X_OK))
    check(f"{name} doesn't ask for a package the program no longer uses", "scipy" not in text)

from about import ROOT as ABOUT_ROOT
check("the About window finds LICENSE", os.path.exists(os.path.join(ABOUT_ROOT, "LICENSE")))

# The settings file: in app/config, the one folder to copy when updating;
# one left in an old place is moved over, and nothing is ever replaced.
from core import config
check("settings are kept in app/config", config.CONFIG_DIR == os.path.join(APP, "config")
      and os.path.dirname(config.CONFIG_PATH) == config.CONFIG_DIR)
with tempfile.TemporaryDirectory() as tmp:
    folder = os.path.join(tmp, "app", "config")
    new = os.path.join(folder, "config.json")
    in_app, in_project = os.path.join(tmp, "app", "config.json"), os.path.join(tmp, "config.json")
    os.mkdir(os.path.join(tmp, "app"))
    keep = config.CONFIG_DIR, config.CONFIG_PATH, config._OLD_CONFIG_PATHS
    config.CONFIG_DIR, config.CONFIG_PATH = folder, new
    config._OLD_CONFIG_PATHS = (in_app, in_project)
    try:
        json.dump({"fps": 12.5}, open(in_app, "w"))
        config.load_config(os.path.join(tmp, "elsewhere.json"))   # some other file
        check("loading some other settings file moves nothing", os.path.exists(in_app))
        config.load_config(new)                                   # the program's own
        check("0.9.3's app/config.json is moved into app/config",
              not os.path.exists(in_app) and config.load_config(new)["fps"] == 12.5)
        json.dump({"fps": 12.5}, open(in_project, "w"))
        config._adopt_old_config()
        check("an identical copy left in an older place is dropped",
              not os.path.exists(in_project) and sorted(os.listdir(folder)) == ["config.json"])
        json.dump({"fps": 99.0}, open(in_project, "w"))
        json.dump({"fps": 88.0}, open(in_app, "w"))
        config._adopt_old_config()
        check("different ones are never written over: kept beside it as config_2, config_3",
              config.load_config(new)["fps"] == 12.5
              and sorted(os.listdir(folder)) == ["config.json", "config_2.json", "config_3.json"]
              and {json.load(open(os.path.join(folder, f)))["fps"]
                   for f in ("config_2.json", "config_3.json")} == {99.0, 88.0}
              and not os.path.exists(in_app) and not os.path.exists(in_project))
        fresh = os.path.join(tmp, "fresh", "config", "config.json")
        config.save_config({"fps": 7.0}, fresh)
        check("the first save makes app/config if it isn't there", json.load(open(fresh))["fps"] == 7.0)
    finally:
        config.CONFIG_DIR, config.CONFIG_PATH, config._OLD_CONFIG_PATHS = keep

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
