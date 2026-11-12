"""A video's info file on disk (GUI-free): finding it, and Track Tamer's own
part of it.

The recording app writes `<date>_<time>_<arena>_info.json` beside its videos
(docs/metadata_standard.md). Track Tamer reads it and **adds to the same
file** (user, 2026-11-11: one JSON that tells everything about a video): an
object named `track_tamer` inside that video's `cameras` entry, holding the
setup drawn for the video, the settings it was tracked with, and the names
of the files Track Tamer made. Nothing the recording app wrote is changed.
A video with no info file gets `<video name>_info.json`, in the same layout.

With that, the tracking file itself holds only what differs from frame to
frame; everything it used to repeat on every row is read back from here
(`saved_columns`), and a video can be added again with its setup as it was.

This module knows nothing about what the fields mean (`core.info` does); it
is kept apart so the tracking file's loader can use it.
"""

from __future__ import annotations

import glob
import json
import os
import re

from .safe_write import replacing

INFO_ENDING = "_info.json"
OWN = "track_tamer"                 # Track Tamer's object in a `cameras` entry
TRACKING_ENDINGS = ("_LocationOutput.csv", "_MotionIndex.csv")


_SHORT_LIST = re.compile(r"\[[^\[\]{}]*\]")


def _text(raw: dict) -> str:
    """The info file as text: indented, with a list of plain values (a
    shape's x positions, a crop) on one line so the file reads easily."""
    text = json.dumps(raw, indent=2, ensure_ascii=False, default=str)
    one_line = lambda m: "[" + ", ".join(p.strip() for p in m.group(0)[1:-1].split(",\n")
                                         if p.strip()) + "]"         # noqa: E731
    short = _SHORT_LIST.sub(lambda m: one_line(m) if "\n" in m.group(0) else m.group(0), text)
    try:
        same = json.loads(short) == json.loads(text)
    except ValueError:
        same = False
    return (short if same else text) + "\n"     # never at the cost of the contents


def read(path: str) -> dict | None:
    """An info file's contents; None if it can't be read or isn't one."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def cameras(raw: dict) -> list[dict]:
    listed = raw.get("cameras")
    return [c for c in listed if isinstance(c, dict)] if isinstance(listed, list) else []


def _folder_files(folder: str) -> list[str]:
    return sorted(glob.glob(os.path.join(glob.escape(folder), "*" + INFO_ENDING)))


def find(video_path: str, name: str | None = None) -> tuple[str, dict, dict, bool] | None:
    """(info file path, its contents, this video's `cameras` entry, renamed)
    for a video: the `*_info.json` in its folder whose `cameras[].video`
    lists its exact file name (standard, section 1). A renamed video still
    matches an info file whose own name starts the video's name
    (`<date>_<time>_<arena>_`); that match is marked renamed, and is only
    for use once the user confirms it. `name` is the video's file name when
    `video_path` is another file in the same folder."""
    name = name or os.path.basename(video_path)
    folder = os.path.dirname(os.path.abspath(video_path))
    loose = None
    for path in _folder_files(folder):
        raw = read(path)
        if raw is None:
            continue
        listed = cameras(raw)
        for camera in listed:
            if camera.get("video") == name:
                return path, raw, camera, False
        start = os.path.basename(path)[:-len(INFO_ENDING)] + "_"
        if loose is None and name.startswith(start):
            # Which camera: the one whose label is in the name, or the only one.
            rest = os.path.splitext(name[len(start):])[0].lower()
            named = [c for c in listed if str(c.get("label", "")).strip().lower() == rest]
            camera = named[0] if named else listed[0] if len(listed) == 1 else {}
            loose = (path, raw, camera, True)
    return loose


def own_path(video_path: str) -> str:
    """The info file Track Tamer makes for a video that has none."""
    return os.path.splitext(video_path)[0] + INFO_ENDING


def prepare(video_path: str, update: dict, label: str | None = None) -> tuple[str, str]:
    """(info file path, its new text) with `update` merged into the video's
    `track_tamer` object: each key of `update` replaces that key (the file
    names under "files" are added to those already there), the others stay. The file is read fresh, so nothing else in it is lost. The video's
    entry is the one that lists it by name, or (a renamed video the user
    confirmed) the one with camera `label`; a video with no info file gets
    its own. Write the text with `core.safe_write.replacing`."""
    name = os.path.basename(video_path)
    found = find(video_path)
    path = raw = camera = None
    if found is not None:
        path, raw, camera, renamed = found
        if renamed:
            same = [c for c in cameras(raw) if label and c.get("label") == label]
            camera = same[0] if same else None
    if camera is None:
        path = own_path(video_path)
        raw = read(path) or {"schema_version": 1}
        listed = cameras(raw)
        camera = next((c for c in listed if c.get("video") == name), None)
        if camera is None:
            camera = {"video": name}
            raw["cameras"] = listed + [camera]
    own = camera.get(OWN)
    own = own if isinstance(own, dict) else {}
    merged = {**own, **update}
    if isinstance(own.get("files"), dict) and isinstance(update.get("files"), dict):
        merged["files"] = {**own["files"], **update["files"]}   # file names add up
    camera[OWN] = merged
    return path, _text(raw)


def write(video_path: str, update: dict, label: str | None = None) -> str:
    """Merge `update` into the video's `track_tamer` object and save the info
    file (whole, under a temporary name, then put in place). Returns its path."""
    path, text = prepare(video_path, update, label)
    with replacing(path) as tmp:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return path


# --- info files Track Tamer makes itself -------------------------------------
# A video from before the recording apps wrote info files (or whose info file
# was lost) gets `<video name>_info.json` in the standard's layout. It can
# hold a copy of an info file the experimenter points to, the animal's
# information typed into Track Tamer, or just Track Tamer's own part.
TYPED_FIELDS = ("animal_id", "sex", "strain", "dob", "treatment", "cohort", "date",
                "start_time", "experimenter", "trial_day", "session_number", "notes")
WHOLE_NUMBERS = ("trial_day", "session_number")     # numbers in the standard


def _own(video_path: str) -> tuple[str, dict, dict]:
    """(path, contents, this video's `cameras` entry) of the video's own info
    file, read from disk or started empty."""
    name = os.path.basename(video_path)
    path = own_path(video_path)
    raw = read(path) or {"schema_version": 1}
    listed = cameras(raw)
    camera = next((c for c in listed if c.get("video") == name), None)
    if camera is None:
        camera = {"video": name}
        raw["cameras"] = listed + [camera]
    return path, raw, camera


def _save(path: str, raw: dict) -> str:
    with replacing(path) as tmp:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(_text(raw))
    return path


def adopt(video_path: str, source_path: str, camera: dict | None = None) -> str:
    """Give a video the info file the experimenter chose for it: its contents
    are copied into the video's own `<video name>_info.json`, with the one
    `cameras` entry that is this video's (`camera`, from the chosen file;
    its `video` is set to this video's name so the two stay matched). The
    chosen file itself isn't touched. Anything Track Tamer had already saved
    for the video is kept. Returns the new file's path; ValueError if the
    chosen file isn't an info file."""
    source = read(source_path)
    if source is None:
        raise ValueError(f"{os.path.basename(source_path)} isn't an info file "
                         "(it couldn't be read as one).")
    path, mine, own_camera = _own(video_path)
    kept = own_camera.get(OWN)
    entry = {k: v for k, v in (camera or {}).items() if k != OWN}
    entry["video"] = os.path.basename(video_path)
    entry[OWN] = {**(kept if isinstance(kept, dict) else {}),
                  "info_copied_from": os.path.basename(source_path)}
    raw = {k: v for k, v in source.items() if k != "cameras"}
    raw["cameras"] = [entry]
    return _save(path, raw)


def write_fields(video_path: str, fields: dict, app_name: str, app_version: str) -> str:
    """Save information typed into Track Tamer (the animal, the trial date
    and so on: `TYPED_FIELDS`) in the video's own info file, as the standard's
    fields. A blank value takes the field out, as the standard asks. Only
    for a file Track Tamer made: `find` must not have matched a recording
    app's file for this video (ValueError if it has)."""
    found = find(video_path)
    if found is not None and not found[3] and found[0] != own_path(video_path):
        raise ValueError("This video's information comes from its recording app's info "
                         "file, which Track Tamer doesn't change.")
    path, raw, _camera = _own(video_path)
    for key in TYPED_FIELDS:
        value = fields.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            raw.pop(key, None)
        elif key in WHOLE_NUMBERS and str(value).strip().isdigit():
            raw[key] = int(str(value).strip())      # a number, as the standard has it
        else:
            raw[key] = value.strip() if isinstance(value, str) else value
    raw.setdefault("schema_version", 1)
    if not str(raw.get("app_name") or "").strip():
        # (a copied info file keeps its recording app's name)
        raw["app_name"], raw["app_version"] = app_name, app_version
    return _save(path, raw)


def _video_stem(output_path: str) -> str | None:
    base = os.path.basename(output_path)
    for ending in TRACKING_ENDINGS:
        if base.lower().endswith(ending.lower()):
            return base[:-len(ending)]
    return None


def for_output(output_path: str) -> tuple[str, dict, dict] | None:
    """(info file path, its contents, the video's `cameras` entry) for a
    tracking file: the entry whose `track_tamer` names this file, or whose
    video the file is named after."""
    base = os.path.basename(output_path)
    stem = _video_stem(output_path)
    by_name = None
    for path in _folder_files(os.path.dirname(os.path.abspath(output_path))):
        raw = read(path)
        if raw is None:
            continue
        for camera in cameras(raw):
            own = camera.get(OWN)
            files = own.get("files") if isinstance(own, dict) else None
            if isinstance(files, dict) and files.get("tracking") == base:
                return path, raw, camera
            video = camera.get("video")
            if (by_name is None and stem and isinstance(video, str)
                    and os.path.splitext(video)[0] == stem):
                by_name = (path, raw, camera)
    return by_name


def saved_columns(output_path: str) -> dict:
    """The columns a slim tracking file leaves to the info file: the same
    value on every row (the video's name, every tracking setting, the region
    outlines). {} if the info file has none for it."""
    found = for_output(output_path)
    own = found[2].get(OWN) if found else None
    columns = own.get("tracking") if isinstance(own, dict) else None
    if not isinstance(columns, dict):
        return {}
    out = dict(columns)
    if isinstance(out.get("ROI_coordinates"), dict):     # kept as real lists in the JSON
        out["ROI_coordinates"] = str(out["ROI_coordinates"])
    if "File" not in out and isinstance(found[2].get("video"), str):
        out["File"] = found[2]["video"]
    return out


def update_saved_columns(output_path: str, values: dict) -> tuple[str, str] | None:
    """(info file path, its new text) with `values` changed among the columns
    the info file keeps for a slim tracking file; None if it keeps none."""
    found = for_output(output_path)
    if found is None:
        return None
    path, raw, camera = found
    own = camera.get(OWN)
    if not isinstance(own, dict) or not isinstance(own.get("tracking"), dict):
        return None
    own["tracking"].update(values)
    return path, _text(raw)


def update_own(output_path: str, update: dict) -> tuple[str, str] | None:
    """(info file path, its new text) with `update` merged into the
    `track_tamer` object of the video a tracking file belongs to (each key of
    `update` replaces that key); None if no info file names the file. The
    file is read fresh, so nothing else in it is lost."""
    found = for_output(output_path)
    if found is None:
        return None
    path, raw, camera = found
    own = camera.get(OWN)
    camera[OWN] = {**(own if isinstance(own, dict) else {}), **update}
    return path, _text(raw)
