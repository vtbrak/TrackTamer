"""The trial information a recording app saves beside its videos (GUI-free).

Creature Capture, Boom Box and any other app that records video for Track
Tamer write `<date>_<time>_<arena>_info.json` per the video metadata standard
(docs/metadata_standard.md, ROADMAP §16). This module finds a video's info
file, reads it forgivingly (an older file with blanks and numbers written as
text still reads), and turns it into what the rest of the app uses: the test
type, the session length, the object trial's details, the animal and trial
columns of the Summary, the Settings sheet's rows, and the problems the
recording app reported.

Nothing here changes a video's setup. `differences` lists where the info file
and the setup disagree; the experimenter chooses which is right (user,
2026-11-11), and the GUI applies the choice.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date

from . import info_file
from .info_file import INFO_ENDING, OWN  # noqa: F401 (INFO_ENDING is re-exported)
from .objects import KINDS, PHASES

SCHEMA_VERSION = 1          # the newest version of the standard this reads

# `assay` (standard, section 3) -> Track Tamer's test type. Matching ignores
# upper/lower case and spaces at the ends.
ASSAY_TESTS = {
    "elevated plus maze": "Elevated Plus Maze",
    "open field": "Open Field",
    "object recognition": "Object Recognition",
    "acoustic startle response": "Acoustic Startle Response",
}

# A video file can report a few frames more than it holds, so its count is
# only said to disagree with the info file beyond this many.
FRAME_COUNT_SLACK = 5

# An app object's value longer than this (as text) is left out of the
# Settings sheet with a note: a startle schedule runs to hundreds of lines.
LONG_VALUE = 300


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _number(value) -> float | None:
    """A number, also when an older file wrote it as text; None otherwise."""
    if isinstance(value, bool) or _blank(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None     # not NaN


def _whole(value):
    """3.0 -> 3, so a day or session reads "3" and not "3.0"."""
    number = _number(value)
    if number is None:
        return None
    return int(number) if number == int(number) else number


def _text(value) -> str:
    if _blank(value) or isinstance(value, (dict, list)):
        return ""
    whole = _whole(value) if not isinstance(value, str) else None
    return str(whole if whole is not None else value).strip()


def _yes(value) -> bool:
    """true, or an older file's "yes"."""
    return value is True or (isinstance(value, str)
                             and value.strip().lower() in ("yes", "true"))


def _day(text: str) -> date | None:
    try:
        return date.fromisoformat(str(text).strip())
    except ValueError:
        return None


@dataclass
class TrialInfo:
    """One video's trial information: the info file's contents and this
    video's own `cameras` entry."""
    raw: dict
    camera: dict = field(default_factory=dict)
    path: str = ""              # the info file ("" when read from a tracking file)
    # Matched by the start of the video's name, not its exact name (the video
    # was renamed): only used once the user confirms.
    renamed: bool = False

    # --- Track Tamer's own part of the file --------------------------------
    @property
    def saved(self) -> dict:
        """What Track Tamer saved for this video (`track_tamer` in its
        `cameras` entry): "test", "setup", "tracking", "analysis", "files"."""
        own = self.camera.get(OWN)
        return own if isinstance(own, dict) else {}

    @property
    def recorded(self) -> bool:
        """True if a recording app wrote this file (it says what was run or
        on which animal); False for a file Track Tamer made for a video that
        had none, which holds only Track Tamer's own part."""
        return any(not _blank(self.raw.get(k)) for k in ("assay", "animal_id", "app_name"))

    # --- what was run ----------------------------------------------------
    @property
    def assay(self) -> str:
        return _text(self.raw.get("assay"))

    @property
    def test(self) -> str | None:
        """Track Tamer's test type for this assay; None if it isn't one Track
        Tamer analyzes (the user then chooses the test)."""
        return ASSAY_TESTS.get(self.assay.lower())

    @property
    def animal_id(self) -> str:
        return _text(self.raw.get("animal_id"))

    @property
    def arena(self) -> str:
        return _text(self.raw.get("arena"))

    @property
    def session_minutes(self) -> float | None:
        minutes = _number(self.raw.get("duration_set_min"))
        return minutes if minutes and minutes > 0 else None

    @property
    def trial_day(self) -> str:
        return _text(self.raw.get("trial_day"))

    @property
    def phase(self) -> str:
        """An Object Recognition phase from the standard's list, else ""."""
        phase = _text(self.raw.get("phase"))
        return next((p for p in PHASES if p.lower() == phase.lower()), "")

    @property
    def object_kinds(self) -> dict[str, str]:
        """{"object 1": "Novel", ...} from `objects`, for the kinds the
        standard lists. Names are matched as Track Tamer names its objects."""
        out = {}
        for entry in self.raw.get("objects") or []:
            if not isinstance(entry, dict):
                continue
            name, kind = _text(entry.get("name")).lower(), _text(entry.get("kind"))
            kind = next((k for k in KINDS if k.lower() == kind.lower()), "")
            if name and kind:
                out[name] = kind
        return out

    @property
    def object_identities(self) -> dict[str, str]:
        """{"object 1": "glass bottle (top left)", ...}: what each object is."""
        out = {}
        for entry in self.raw.get("objects") or []:
            if not isinstance(entry, dict):
                continue
            name, what = _text(entry.get("name")).lower(), _text(entry.get("identity"))
            where = _text(entry.get("position"))
            if name and (what or where):
                out[name] = what + (f" ({where})" if what and where else where)
        return out

    # --- the animal -----------------------------------------------------------
    def age_days(self) -> int | None:
        born, tested = _day(self.raw.get("dob", "")), _day(self.raw.get("date", ""))
        if born is None or tested is None or tested < born:
            return None
        return (tested - born).days

    # --- the recording ------------------------------------------------------
    @property
    def repeated_frames(self) -> int | None:
        count = _number(self.camera.get("repeated_frames"))
        return int(count) if count is not None else None

    @property
    def fps_measured(self) -> float | None:
        fps = _number(self.camera.get("fps_measured"))
        return fps if fps and fps > 0 else None

    def problems(self, video_frames: int | None = None, video_fps: float | None = None,
                 session_s: float | None = None,
                 video_size: tuple[int, int] | None = None) -> list[str]:
        """What the recording app's own record says went wrong, as short
        phrases: stopped early, shorter than the session, an encoder error,
        frame counts or a frame size that don't agree with the video, a
        frame rate that isn't the video's."""
        out = []
        version = _number(self.raw.get("schema_version"))
        if version is not None and version > SCHEMA_VERSION:
            out.append(f"written to a newer version of the standard ({version:g}); "
                       "update Track Tamer to read all of it")
        actual = _number(self.raw.get("duration_actual_s"))
        if _yes(self.raw.get("stopped_early")):
            out.append("the recording was stopped early"
                       + (f" (after {actual:g} s)" if actual is not None else ""))
        elif actual is not None and session_s and actual < session_s - 1:
            out.append(f"the recording is {actual:g} s long, shorter than the "
                       f"session length ({session_s:g} s)")
        error = _text(self.camera.get("error"))
        if error:
            out.append(f"the recording app reported an error: {error}")
        frames = _number(self.camera.get("frames"))
        checked = _number(self.camera.get("verified_frames_in_file"))
        if frames is not None and checked is not None and frames != checked:
            out.append(f"the app wrote {frames:g} frames but counted {checked:g} "
                       "in the finished video")
        elif (frames is not None and video_frames
              and abs(frames - video_frames) > FRAME_COUNT_SLACK):
            out.append(f"the info file says {frames:g} frames, the video has "
                       f"{video_frames:,}")
        wide, high = _number(self.camera.get("width_px")), _number(self.camera.get("height_px"))
        if (video_size and wide is not None and high is not None
                and (int(wide), int(high)) != tuple(video_size)):
            out.append(f"the info file says the frames are {wide:g} x {high:g} px, the "
                       f"video's are {video_size[0]} x {video_size[1]}")
        measured = self.fps_measured
        if measured and video_fps and abs(measured - video_fps) > 0.01 * video_fps:
            out.append(f"the measured frame rate ({measured:g} fps) isn't the video's "
                       f"({video_fps:g} fps), so times may be off")
        return out

    # --- the export's Experiment sheet ---------------------------------------
    def experiment_sections(self) -> dict[str, dict]:
        """{section: {field: value}} for the Experiment sheet: the animal and
        the task, every field listed (blank when the app didn't record it),
        under the words the recording apps use on screen."""
        get = lambda key: _text(self.raw.get(key))      # noqa: E731
        age = self.age_days()
        animal = {"Animal ID": get("animal_id"), "Sex": get("sex"),
                  "Strain / genotype": get("strain"), "Date of birth": get("dob"),
                  "Age (days)": "" if age is None else age,
                  "Treatment / group": get("treatment"), "Cohort / litter": get("cohort")}
        stopped = self.raw.get("stopped_early")
        task = {"Assay": get("assay"), "Variant": get("assay_variant"), "Phase": get("phase"),
                "Date": get("date"), "Start time": get("start_time"), "Arena": get("arena"),
                "Trial day": get("trial_day"), "Session that day": get("session_number"),
                "Experimenter": get("experimenter"),
                "Length set (min)": get("duration_set_min"),
                "Length recorded (s)": get("duration_actual_s"),
                "Stopped early": "" if _blank(stopped) else ("yes" if _yes(stopped) else "no"),
                "Notes": get("notes")}
        sections = {"Animal": animal, "Task": task}
        kinds, what = self.object_kinds, self.object_identities
        if kinds or what:
            sections["Objects (as recorded)"] = {
                name: " - ".join(x for x in (kinds.get(name, ""), what.get(name, "")) if x)
                for name in dict.fromkeys(list(kinds) + list(what))}
        return sections

    # --- the export's Settings sheet --------------------------------------
    def settings_sections(self) -> dict[str, dict]:
        """{section: {setting: value}} for the Settings sheet: where the
        information came from, the camera, and each app's own fields as they
        are (standard, section 2)."""
        raw, cam = self.raw, self.camera
        source = {"Info file": os.path.basename(self.path)}
        for label, key in (("Recording app", "app_name"), ("App version", "app_version"),
                           ("Standard version", "schema_version")):
            if not _blank(raw.get(key)):
                source[label] = raw[key]
        sections = {"Recording": source}
        camera = {}
        for label, key in (("Camera label", "label"), ("Camera position", "camera_position"),
                           ("Frame rate asked for (fps)", "fps_set"),
                           ("Frame rate measured (fps)", "fps_measured"),
                           ("Frames written", "frames"),
                           ("Repeated frames", "repeated_frames"),
                           ("Frame times file", "timestamps_csv")):
            if not _blank(cam.get(key)):
                camera[label] = cam[key]
        settings = cam.get("camera_settings")
        if isinstance(settings, dict):
            camera.update({f"Setting: {k}": _plain(v) for k, v in settings.items()})
        if camera:
            sections["Camera"] = camera
        for key, value in raw.items():        # app objects: creature_capture, boom_box, ...
            if isinstance(value, dict):
                sections[f"App fields ({key})"] = {k: _plain(v) for k, v in value.items()}
        return sections


def _plain(value):
    """A Settings sheet cell: numbers and text as they are, anything nested
    as compact JSON, or a note when that would run long."""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=str)
        return text if len(text) <= LONG_VALUE else "(long: see the info file)"
    return value


def find_info(video_path: str, name: str | None = None) -> TrialInfo | None:
    """The trial information for a video, from the info file beside it that
    lists it (`info_file.find`). A match by the start of a renamed video's
    name is marked `renamed`, for use only once the user confirms it."""
    found = info_file.find(video_path, name)
    if found is None:
        return None
    path, raw, camera, renamed = found
    return TrialInfo(raw=raw, camera=camera, path=path, renamed=renamed)


def info_for_output(output_path: str) -> TrialInfo | None:
    """The trial information for a tracking file whose video isn't in the list."""
    found = info_file.for_output(output_path)
    if found is None:
        return None
    path, raw, camera = found
    return TrialInfo(raw=raw, camera=camera, path=path)


# --- a draft setup from the same arena --------------------------------------
MAX_DRAFT_FILES = 400       # info files looked at when searching for a draft


def _drawn(saved) -> bool:
    return isinstance(saved, dict) and any(saved.get(k) for k in (
        "crop", "regions", "exclusions", "scale_points", "objects"))


def arena_draft(info: TrialInfo, video_path: str,
                frame_size: tuple[int, int]) -> tuple[dict, str] | None:
    """(saved setup, video name) from the last video tracked in the same
    arena with the same camera, for use as a draft: the rig hasn't moved, so
    its crop, regions and scale are a good start (the user still checks each
    step; every video is analyzed against its own setup). Looks in the
    video's folder and its sibling folders (the recording apps keep one
    folder per day), and takes the most recently saved setup drawn on frames
    of this size. None if there isn't one."""
    arena, label = info.arena, _text(info.camera.get("label"))
    if not arena:
        return None
    folder = os.path.dirname(os.path.abspath(video_path))
    parent = os.path.dirname(folder)
    folders = [folder]
    try:
        folders += sorted((os.path.join(parent, d) for d in os.listdir(parent)
                           if os.path.isdir(os.path.join(parent, d))
                           and os.path.join(parent, d) != folder), reverse=True)
    except OSError:
        pass
    best, seen = None, 0
    for place in folders:
        try:
            names = sorted(n for n in os.listdir(place) if n.endswith(INFO_ENDING))
        except OSError:
            continue
        for name in names:
            seen += 1
            if seen > MAX_DRAFT_FILES:
                break
            raw = info_file.read(os.path.join(place, name))
            if raw is None or _text(raw.get("arena")) != arena:
                continue
            for camera in info_file.cameras(raw):
                own = camera.get(OWN)
                saved = own.get("setup") if isinstance(own, dict) else None
                if (not _drawn(saved) or _text(camera.get("label")) != label
                        or (place == folder
                            and camera.get("video") == os.path.basename(video_path))
                        or list(saved.get("frame_size") or []) != list(frame_size)):
                    continue
                when = str(own.get("saved") or "")
                if best is None or when > best[0]:
                    best = (when, saved, str(camera.get("video") or name))
    return (best[1], best[2]) if best else None


# --- where the info file and the setup disagree ---------------------------
@dataclass
class Difference:
    """One thing the setup and the info file say differently. `what` is
    "test", "length", "day", "phase" or "kinds"; the values are as shown."""
    what: str
    label: str
    setup_value: str
    info_value: str


def _minutes(seconds: float | None) -> str:
    return "" if seconds is None else f"{seconds / 60:g} min"


def _kinds_text(names, kinds: dict) -> str:
    return ", ".join(f"{n}: {kinds.get(n, 'Familiar')}" for n in names)


def differences(info: TrialInfo, test: str, setup=None) -> list[Difference]:
    """Where a video's setup and its info file disagree, for the test in use
    (`test`: the session length and object details are compared as that test
    uses them). A value the setup doesn't have yet (a blank day or phase)
    isn't a disagreement: `fill_blanks` takes it from the info file. `setup`
    is the video's VideoSetup; without one only the test type is compared."""
    out = []
    if info.test and info.test != test:
        out.append(Difference("test", "Test", test, info.test))
    if setup is None:
        return out
    if test != "Acoustic Startle Response":      # startle takes the whole video
        minutes = info.session_minutes
        if minutes and (setup.length_s is None or abs(setup.length_s - minutes * 60) > 0.5):
            out.append(Difference("length", "Session length", _minutes(setup.length_s)
                                  or "to the end of the video", f"{minutes:g} min"))
    if test == "Object Recognition":
        if info.trial_day and setup.trial_day and info.trial_day != setup.trial_day:
            out.append(Difference("day", "Trial day", setup.trial_day, info.trial_day))
        if info.phase and setup.trial_phase and info.phase != setup.trial_phase:
            out.append(Difference("phase", "Phase", setup.trial_phase, info.phase))
        kinds = info.object_kinds
        names = [n for n in setup.object_names if n in kinds]
        if any(setup.object_kinds.get(n, "Familiar") != kinds[n] for n in names):
            out.append(Difference("kinds", "Object types",
                                  _kinds_text(names, setup.object_kinds),
                                  _kinds_text(names, kinds)))
    return out


def fill_blanks(info: TrialInfo, setup) -> None:
    """Give the setup what it doesn't have yet from the info file: the trial
    day and phase of an object trial."""
    if not setup.trial_day and info.trial_day:
        setup.trial_day = info.trial_day
    if not setup.trial_phase and info.phase:
        setup.trial_phase = info.phase


def apply_choice(info: TrialInfo, setup, what: str) -> None:
    """Take the info file's value for one difference (the test type is the
    whole load's, so the GUI sets that one)."""
    if what == "length" and info.session_minutes:
        setup.length_s = info.session_minutes * 60
        setup.length_default = ""       # a chosen length: it doesn't follow the test
        setup.end_placed = None
    elif what == "day":
        setup.trial_day = info.trial_day
    elif what == "phase":
        setup.trial_phase = info.phase
    elif what == "kinds":
        for name, kind in info.object_kinds.items():
            if name in setup.object_names:
                setup.object_kinds[name] = kind


def with_animal(summary: dict, info: TrialInfo | None) -> dict:
    """A Summary row with `animal_id` right after File (blank when it isn't
    known), so every row says whose it is; the rest about the animal and the
    task is on the workbook's Experiment sheet (user, 2026-11-11)."""
    first = {k: summary[k] for k in ("File",) if k in summary}
    rest = {k: v for k, v in summary.items() if k not in first and k != "animal_id"}
    if info is not None and info.repeated_frames is not None and "RepeatedFrames" not in rest:
        rest["RepeatedFrames"] = info.repeated_frames
    return {**first, "animal_id": info.animal_id if info is not None else "", **rest}
