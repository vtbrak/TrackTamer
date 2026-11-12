"""Acoustic startle response from video (GUI-free; ROADMAP §13).

The motion index follows Shivashankar, Agee, Wilson, Salamone and Drew's
method, which the user cites outside the app: for each pair of successive
frames, count the pixels whose intensity changed by more than a threshold
(default 15), as a percentage of the pixels analyzed.

Per stimulus (user's document, 2026-11-09):
    startle amplitude = highest motion index in the startle window (200 ms
    after the stimulus) - highest motion index in the baseline window (200 ms
    before it).

A motion index at frame k is the change from frame k-1 to k, so it belongs to
the time of frame k: the startle window is the frames after the stimulus up
to the window's end, and the baseline window is the frames up to and
including the stimulus. On prepulse+pulse trials the baseline ends where the
prepulse starts (user, 2026-11-09), so it measures the animal before any
sound. Frames the recording app marks as repeated are copies, so they're left
out of the peaks. Times come from the frame-time file when the
recording app wrote one, since those are what was measured.

Stimuli come from the recording app's info file (the `stimuli` list, see
docs/metadata_standard.md) or are typed in as video frames.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime

import cv2
import numpy as np
import pandas as pd

from . import info_file
from .info import find_info as trial_info_for
from .loader import TrackingData
from .safe_write import replacing
from .tracking import crop_text
from .video import Prep, VideoReader
from .version import VERSION
from .video_setup import ASR_TEST, VideoSetup

MOTION_SUFFIX = "_MotionIndex.csv"
PULSE, PREPULSE_PULSE, PREPULSE, NO_STIMULUS = "pulse", "prepulse+pulse", "prepulse", "none"
PPI_COLUMNS = ["Prepulse_dB", "Interval_ms"]    # in the Trials table only for PPI sessions
HABITUATION_VARIANT = "Startle Habituation"     # the standard's assay_variant
SETTING_COLUMNS = ("File", "Intensity_Threshold", "Start_Frame", "Crop", "Exclusion_Shapes",
                   "Video_FPS", "Stimulus_Source", "Stimuli")


# --- the motion index -----------------------------------------------------
def changed_pixels(previous: np.ndarray, current: np.ndarray, threshold: float,
                   mask: np.ndarray | None = None) -> np.ndarray:
    """True where the intensity changed by more than `threshold` between two
    grayscale frames. Pixels in `mask` (exclusion shapes) never count."""
    above = cv2.absdiff(current, previous) > threshold
    if mask is not None:
        above = above & ~mask
    return above


def analyzed_pixels(frame: np.ndarray, mask: np.ndarray | None = None) -> int:
    return int(frame.size - (int(mask.sum()) if mask is not None else 0))


def motion_table(path: str, prep: Prep, start: int, end: int, threshold: float,
                 mask: np.ndarray | None = None, times: dict | None = None, fps: float = 0.0,
                 progress=None, should_cancel=None,
                 repeated: set | None = None) -> pd.DataFrame | None:
    """One row per frame: Frame (the video's own frame number, from 0), Time_s,
    MotionIndex_pct, AboveThreshold_px, Total_px, Frame_Unreadable. The first
    frame, an unreadable frame and the frame after one have no pair to compare,
    so their motion index is blank. None if cancelled."""
    rows, previous, total = [], None, 0
    count = max(end - start, 1)
    with VideoReader(path, prep) as reader:
        for k, (index, frame) in enumerate(reader.frames(start, end)):
            if should_cancel and should_cancel():
                return None
            bad = frame is None
            value, above = float("nan"), float("nan")
            if not bad:
                total = analyzed_pixels(frame, mask)
                if previous is not None and total:
                    above = int(changed_pixels(previous, frame, threshold, mask).sum())
                    value = round(100.0 * above / total, 4)
            when = (times or {}).get(index)
            rows.append({"Frame": index,
                         "Time_s": round(when if when is not None
                                         else (index / fps if fps else 0.0), 4),
                         "MotionIndex_pct": value, "AboveThreshold_px": above,
                         "Total_px": total, "Frame_Unreadable": bad,
                         "Repeated": index in (repeated or ())})
            previous = None if bad else frame
            if progress and k % 25 == 0:
                progress(k, count)
    if progress:
        progress(count, count)
    return pd.DataFrame(rows)


# --- what the recording app wrote -----------------------------------------
def find_info(video_path: str) -> tuple[dict, dict] | None:
    """(info file contents, this video's `cameras` entry) from the `*_info.json`
    beside the video that lists it by exact name; None if there isn't one."""
    found = trial_info_for(video_path)
    if found is None or found.renamed:
        return None
    return found.raw, found.camera


def frame_times(video_path: str, camera: dict | None) -> dict | None:
    """{video frame: measured time in seconds} from the camera's `_frames.csv`,
    the record of timing (metadata standard, section 4); None if there's none."""
    name = (camera or {}).get("timestamps_csv")
    if not name:
        return None
    path = os.path.join(os.path.dirname(os.path.abspath(video_path)), name)
    try:
        table = pd.read_csv(path, usecols=["frame", "video_time_s"]).dropna()
        return dict(zip(table["frame"].astype(int), table["video_time_s"].astype(float)))
    except (OSError, ValueError, TypeError):
        return None     # missing, or not a usable frames file


def repeated_frames(video_path: str, camera: dict | None) -> set:
    """The frames the camera's `_frames.csv` marks as repeated copies."""
    name = (camera or {}).get("timestamps_csv")
    if not name:
        return set()
    path = os.path.join(os.path.dirname(os.path.abspath(video_path)), name)
    try:
        table = pd.read_csv(path, usecols=["frame", "repeated"]).dropna(subset=["frame"])
        copies = table["repeated"].astype(str).str.strip().str.lower() == "true"
        return set(table.loc[copies, "frame"].astype(int))
    except (OSError, ValueError, TypeError):
        return set()


def stimuli_from_info(info: dict | None) -> list[dict]:
    """The usable entries of the info file's `stimuli` list (each needs a
    frame), keeping only the fields the analysis reads. Boom Box 1.1 keeps
    the tone frequency and kind in `boom_box.trials` (same order as `stimuli`),
    so they're taken from there when `stimuli` doesn't have them."""
    out = []
    details = ((info or {}).get("boom_box") or {}).get("trials") or []
    for n, s in enumerate((info or {}).get("stimuli") or []):
        if not isinstance(s, dict) or s.get("frame") is None:
            continue
        try:
            entry = {"frame": int(s["frame"]), "type": str(s.get("type") or PULSE)}
        except (TypeError, ValueError):
            continue
        for key in ("video_time_s", "pulse_db", "prepulse_db", "interval_ms", "pulse_freq_hz"):
            if isinstance(s.get(key), (int, float)):
                entry[key] = s[key]
        detail = details[n] if n < len(details) and isinstance(details[n], dict) else {}
        if "pulse_freq_hz" not in entry:
            try:
                entry["pulse_freq_hz"] = float(detail["pulse_freq_hz"])
            except (KeyError, TypeError, ValueError):
                pass
        kind = s.get("pulse_stimulus") or detail.get("pulse_stimulus")
        if kind:
            entry["pulse_stimulus"] = str(kind)
        out.append(entry)
    return out


def parse_frames(text: str) -> list[int]:
    """Stimulus frames typed or pasted: numbers separated by commas, spaces or
    new lines, in order with repeats removed. ValueError names a bad entry."""
    frames = []
    for piece in text.replace(",", " ").split():
        try:
            value = float(piece)
        except ValueError:
            raise ValueError(f'"{piece}" isn\'t a frame number.') from None
        if value < 0 or value != int(value):
            raise ValueError(f'"{piece}" isn\'t a whole frame number.')
        if int(value) not in frames:
            frames.append(int(value))
    return sorted(frames)


# --- running one video ----------------------------------------------------
@dataclass
class AsrJob:
    """Everything needed to process one video, copied from its setup."""
    path: str
    prep: Prep
    start: int
    end: int
    mask: np.ndarray | None
    threshold: float
    fps: float
    exclusion_count: int
    typed_frames: list[int]
    # For the video's info file: the test and the setup as run, and the
    # camera label of a renamed video's entry in that file.
    record: dict | None = None
    label: str | None = None


def make_asr_job(setup: VideoSetup, threshold: float) -> AsrJob:
    """Snapshot a video's setup. Always full size: the method and its
    threshold were set on full frames."""
    return AsrJob(path=setup.path, prep=setup.prep(1.0), start=setup.start,
                  end=setup.end_frame, mask=setup.exclusion_mask(1.0),
                  threshold=float(threshold), fps=float(setup.info.fps or 0),
                  exclusion_count=len(setup.exclusions),
                  typed_frames=list(setup.stimulus_frames),
                  record={"test": ASR_TEST, "setup": setup.to_saved(ASR_TEST)})


def motion_path(video_path: str) -> str:
    return os.path.splitext(video_path)[0] + MOTION_SUFFIX


def run_asr_job(job: AsrJob, progress=None, should_cancel=None):
    """Work out the motion index of one video and save `<name>_MotionIndex.csv`
    beside it. Returns (loaded data, csv path), or None if cancelled."""
    found = find_info(job.path)
    info, camera = found if found else (None, None)
    table = motion_table(job.path, job.prep, job.start, job.end, job.threshold, job.mask,
                         frame_times(job.path, camera), job.fps, progress, should_cancel,
                         repeated_frames(job.path, camera))
    if table is None:
        return None
    if table.empty or not (~table["Frame_Unreadable"]).any():
        raise ValueError("No frames could be read between the start and the end.")
    stimuli = stimuli_from_info(info)
    source = "info file" if stimuli else "typed in"
    if not stimuli:
        stimuli = [{"frame": f, "type": PULSE} for f in job.typed_frames]
    path = motion_path(job.path)
    # The motion file keeps what differs from frame to frame. What is one
    # value for the whole video is saved once, in the video's info file
    # (user, 2026-11-11), with the setup, so the video can be added again as
    # it was. The stimuli aren't copied: they're read from the info file's
    # own `stimuli` list, or, when they were typed in, from the frames kept
    # here.
    constants = {
        "File": os.path.basename(job.path), "Intensity_Threshold": job.threshold,
        "Start_Frame": job.start, "Crop": crop_text(job.prep.crop),
        "Exclusion_Shapes": job.exclusion_count, "Video_FPS": job.fps,
        "Stimulus_Source": source if stimuli else "none",
        "Total_px": int(table["Total_px"].max()),
    }
    if source == "typed in" and stimuli:
        constants["Stimulus_Frames"] = [int(s["frame"]) for s in stimuli]
    info_path, text = info_file.prepare(job.path, {
        **(job.record or {}), "version": VERSION,
        "saved": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "setup_changed_since_tracking": False,
        "tracking": constants,
        "files": {"tracking": os.path.basename(path)}}, job.label)
    # Both are written whole before either earlier file is replaced.
    with replacing(info_path) as info_tmp:
        with open(info_tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        with replacing(path) as tmp:
            table.drop(columns=["Total_px"]).to_csv(tmp, index=False)
    return load_motion(path), path


def _saved_stimuli(path: str, source, typed) -> list[dict]:
    """A slim motion file's stimuli: the info file's own list, or the frames
    that were typed in."""
    if source == "info file":
        found = info_file.for_output(path)
        return stimuli_from_info(found[1]) if found else []
    try:
        return [{"frame": int(f), "type": PULSE} for f in typed or []]
    except (TypeError, ValueError):
        return []


def load_motion(path: str) -> TrackingData:
    """Read a `_MotionIndex.csv`. What is one value for the whole video (the
    settings, the pixels analyzed) comes back from the video's info file; an
    older file that holds its own settings and stimuli is read as it is."""
    df = pd.read_csv(path, low_memory=False, keep_default_na=True)
    saved = info_file.saved_columns(path)
    typed = saved.pop("Stimulus_Frames", None)
    for column, value in saved.items():
        if column not in df.columns:
            df[column] = np.nan if value is None else value
    missing = [c for c in ("Frame", "Time_s", "MotionIndex_pct") if c not in df.columns]
    if missing:
        raise ValueError(f"{os.path.basename(path)} is missing required column(s): "
                         f"{', '.join(missing)}")
    for column in ("Frame_Unreadable", "Repeated"):
        if column in df.columns:
            df[column] = df[column].astype(str).str.lower() == "true"
    settings = {c: df[c].iloc[0] for c in SETTING_COLUMNS if c in df.columns and len(df)}
    if "Stimuli" not in settings:
        settings["Stimuli"] = json.dumps(
            _saved_stimuli(path, settings.get("Stimulus_Source"), typed))
    return TrackingData(path=path, df=df, settings=settings, regions=[])


def is_motion_file(path: str) -> bool:
    return path.lower().endswith(MOTION_SUFFIX.lower())


def file_stimuli(data: TrackingData) -> list[dict]:
    text = data.settings.get("Stimuli")
    if not isinstance(text, str) or not text.strip():
        return []
    try:
        return json.loads(text)
    except ValueError:
        return []


# --- trials and the session ------------------------------------------------
TRIAL_COLUMNS = ["Trial", "Type", "Pulse_kHz", "Pulse_Kind", "Prepulse_dB", "Pulse_dB",
                 "Interval_ms", "Stimulus_Frame",
                 "Stimulus_s", "Pixel.change_px", "motion.index.before_pct", "motion.index.after_pct",
                 "FrameNo", "Time.startle_s", "ReactionTime_ms", "Startle amplitude_pct", "Note"]


def _window_peak(df: pd.DataFrame, inside: np.ndarray):
    """(peak motion index, its row), or (nan, None) if nothing usable.
    Repeated frames are copies, so they can't be a peak."""
    usable = df["MotionIndex_pct"].to_numpy(dtype=float).copy()
    if "Repeated" in df.columns:
        usable[df["Repeated"].to_numpy(dtype=bool)] = np.nan
    values = usable[inside]
    if values.size == 0 or np.all(np.isnan(values)):
        return float("nan"), None
    return float(np.nanmax(values)), int(np.flatnonzero(inside)[int(np.nanargmax(values))])


def trial_table(data: TrackingData, startle_ms: float = 200.0,
                baseline_ms: float = 200.0) -> pd.DataFrame:
    """One row per stimulus, in time order. Every heading carries its unit
    (user, 2026-11-12). Pixel.change_px is the above-threshold pixel count at
    the peak, FrameNo and Time.startle_s the peak's video frame and time,
    ReactionTime_ms the milliseconds from stimulus to peak. The prepulse
    columns (Prepulse_dB, Interval_ms) are there only when the session has
    prepulse trials, so a plain startle table has no empty PPI headings. Any window
    that doesn't lie fully inside the recording, or has no usable frames,
    leaves the amplitude blank with a note saying why."""
    df = data.df
    frames = df["Frame"].to_numpy(dtype=int)
    times = df["Time_s"].to_numpy(dtype=float)
    bad = df["Frame_Unreadable"].to_numpy(dtype=bool)
    above = df["AboveThreshold_px"].to_numpy(dtype=float)
    copies = (df["Repeated"].to_numpy(dtype=bool) if "Repeated" in df.columns
              else np.zeros(len(df), dtype=bool))
    rows = []
    stimuli = sorted(file_stimuli(data), key=lambda s: s["frame"])
    for n, s in enumerate(stimuli, start=1):
        hz = s.get("pulse_freq_hz")
        row = {"Trial": n, "Type": s.get("type", PULSE),
               "Pulse_kHz": round(hz / 1000, 3) if hz else None,
               "Pulse_Kind": s.get("pulse_stimulus"), "Prepulse_dB": s.get("prepulse_db"),
               "Pulse_dB": s.get("pulse_db"), "Interval_ms": s.get("interval_ms"),
               "Stimulus_Frame": s["frame"], "Note": ""}
        at = np.flatnonzero(frames == s["frame"])
        if at.size == 0:
            row["Note"] = "stimulus is outside the analyzed frames"
            rows.append(row)
            continue
        t0 = float(s["video_time_s"]) if s.get("video_time_s") is not None else float(times[at[0]])
        row["Stimulus_s"] = round(t0, 4)
        tiny = 1e-6
        after = (times > t0 + tiny) & (times <= t0 + startle_ms / 1000 + tiny)
        # With a prepulse, the baseline ends where the prepulse starts.
        end = t0
        if row["Type"] == PREPULSE_PULSE and s.get("interval_ms"):
            end = t0 - float(s["interval_ms"]) / 1000
        before = (times > end - baseline_ms / 1000 + tiny) & (times <= end + tiny)
        notes = []
        complete = True     # both windows lie inside the recording
        if t0 + startle_ms / 1000 > times[-1] + tiny:
            notes.append("startle window runs past the end")
            complete = False
        if end - baseline_ms / 1000 < times[0] - tiny:
            notes.append("baseline window starts before the recording")
            complete = False
        lost = int(bad[after | before].sum())
        if lost:
            notes.append(f"{lost} unreadable frame(s) in the windows")
        same = int(copies[after | before].sum())
        if same:
            notes.append(f"{same} repeated frame(s) left out")
        high_after, peak = _window_peak(df, after)
        high_before, _ = _window_peak(df, before)
        row["Note"] = "; ".join(notes)
        if peak is not None:
            row.update({"Pixel.change_px": int(above[peak]), "motion.index.after_pct": round(high_after, 4),
                        "FrameNo": int(frames[peak]), "Time.startle_s": round(float(times[peak]), 4),
                        "ReactionTime_ms": round((float(times[peak]) - t0) * 1000, 1)})
        if not math.isnan(high_before):
            row["motion.index.before_pct"] = round(high_before, 4)
        if peak is not None and not math.isnan(high_before) and complete:
            row["Startle amplitude_pct"] = round(high_after - high_before, 4)
        rows.append(row)
    table = pd.DataFrame(rows, columns=TRIAL_COLUMNS)
    if not table["Type"].isin([PREPULSE_PULSE, PREPULSE]).any() \
            and table[PPI_COLUMNS].isna().all().all():
        table = table.drop(columns=PPI_COLUMNS)
    return table


def _mean(values) -> float:
    return round(sum(values) / len(values), 4) if len(values) else float("nan")


def _median(values) -> float:
    return round(float(np.median(values)), 4) if len(values) else float("nan")


def _level(value) -> str:
    return "" if value is None or pd.isna(value) else f"{float(value):g}"


def _pulse_label(row) -> str:
    """"4kHz" for a tone, "noise" for noise, "" if the file doesn't say."""
    khz = row.get("Pulse_kHz")
    if khz is not None and not pd.isna(khz):
        return f"{float(khz):g}kHz"
    return str(row.get("Pulse_Kind") or "") if row.get("Pulse_Kind") == "noise" else ""


# --- startle by sound level -------------------------------------------------
def level_curves(trials: pd.DataFrame) -> dict[str, list[dict]]:
    """The pulse-alone trials grouped by sound, then by pulse level:
    {sound: [{"db", "n", "mean", "sem", "peak"}, ...]} with the levels in
    rising order. `sound` is "8kHz", "noise", or "" when the file doesn't
    say; `mean` and `sem` are of the startle amplitude, and `peak` is the
    mean of the startle-window peaks (what the threshold is judged on).
    Only trials with an amplitude and a level are used."""
    if trials is None or trials.empty or "Pulse_dB" not in trials.columns:
        return {}
    used = trials[(trials["Type"] == PULSE)].dropna(subset=["Startle amplitude_pct", "Pulse_dB"])
    if used.empty:
        return {}
    sounds = used.apply(_pulse_label, axis=1)
    out: dict[str, list[dict]] = {}
    for sound in sorted(set(sounds), key=_sound_order):
        part = used[sounds == sound]
        rows = []
        for db in sorted(set(part["Pulse_dB"].astype(float))):
            at = part[part["Pulse_dB"].astype(float) == db]
            values = at["Startle amplitude_pct"].astype(float).to_numpy()
            rows.append({"db": db, "n": len(values), "mean": _mean(values.tolist()),
                         "sem": (float(values.std(ddof=1) / math.sqrt(len(values)))
                                 if len(values) > 1 else 0.0),
                         "peak": float(at["motion.index.after_pct"].astype(float).mean())})
        out[sound] = rows
    return out


def baseline_criterion(trials: pd.DataFrame, sd: float = 2.0) -> float | None:
    """The motion index a level's response has to beat: the mean of every
    trial's baseline-window peak plus `sd` standard deviations of them
    (user, 2026-11-11). None with fewer than two baseline windows."""
    if trials is None or trials.empty or "motion.index.before_pct" not in trials.columns:
        return None
    before = trials["motion.index.before_pct"].dropna().astype(float).to_numpy()
    if len(before) < 2:
        return None
    return float(before.mean() + float(sd) * before.std(ddof=1))


def startle_threshold(levels: list[dict], criterion: float | None) -> float | None:
    """The lowest level from which that level and every louder one gives a
    response (its mean startle-window peak is above `criterion`), so a
    chance response at one quiet level doesn't set it (user, 2026-11-11).
    None if the loudest level doesn't respond, or there's no criterion."""
    if criterion is None or not levels:
        return None
    threshold = None
    for row in reversed(levels):            # from the loudest down
        if not row["peak"] > criterion:
            break
        threshold = row["db"]
    return threshold


def _sound_order(label: str):
    """Sounds in a sensible order: tones by rising frequency, then noise,
    then anything unnamed (not "12kHz" before "4kHz", as plain sorting gives)."""
    try:
        return (0, float(label[:-3])) if label.endswith("kHz") else (1, 0.0)
    except ValueError:
        return (2, 0.0)


def level_measures(trials: pd.DataFrame, threshold_sd: float = 2.0) -> dict:
    """The Summary's startle-by-level columns, for sessions whose pulse-alone
    trials use more than one level (Boom Box's Hearing Test and I/O): the
    count and mean at each level (and at each sound-and-level pair when the
    sound varies too), then the startle threshold and the largest of those
    means with its level. Per sound when there's more than one, since
    different sounds make different curves. {} for a one-level session.
    Amplitudes are in % of pixels (`_pct`)."""
    curves = level_curves(trials)
    if not any(len(rows) > 1 for rows in curves.values()):
        return {}
    out: dict = {}
    several = len(curves) > 1
    used = trials[(trials["Type"] == PULSE)].dropna(subset=["Startle amplitude_pct", "Pulse_dB"])
    for db in sorted(set(used["Pulse_dB"].astype(float))):      # each level, sounds pooled
        values = used[used["Pulse_dB"].astype(float) == db]["Startle amplitude_pct"]
        out[f"ASR_N_{PULSE}_{_level(db)}dB"] = len(values)
        out[f"ASR_Mean_{PULSE}_{_level(db)}dB_pct"] = _mean(values.astype(float).tolist())
    if several:                                                 # each sound-and-level pair
        for sound, rows in curves.items():
            for row in rows:
                tag = "_".join(x for x in (sound, f"{_level(row['db'])}dB") if x)
                out[f"ASR_N_{PULSE}_{tag}"] = row["n"]
                out[f"ASR_Mean_{PULSE}_{tag}_pct"] = row["mean"]
    criterion = baseline_criterion(trials, threshold_sd)
    out["ASR_ThresholdCriterion_pct"] = (round(criterion, 4) if criterion is not None
                                         else float("nan"))
    for sound, rows in curves.items():
        if len(rows) < 2:
            continue
        name = f"_{sound}" if several and sound else ""
        best = max(rows, key=lambda r: r["mean"])
        threshold = startle_threshold(rows, criterion)
        out[f"ASR_Threshold{name}_dB"] = threshold if threshold is not None else float("nan")
        out[f"ASR_Max_{PULSE}{name}_pct"] = best["mean"]
        out[f"ASR_Max_{PULSE}{name}_dB"] = best["db"]
    return out


TYPE_ORDER = (PULSE, PREPULSE_PULSE, PREPULSE, NO_STIMULUS)


def session_measures(trials: pd.DataFrame, block_trials: int = 10,
                     threshold_sd: float = 2.0, habituation: bool = False) -> dict:
    """The Summary's startle columns, every one from the trials' startle
    amplitudes as shown (% of pixels, `_pct`). **Each group's numbers sit
    together** (user, 2026-11-12): for each trial type its count, mean and
    median, then the same per sound; for pulse-alone trials that step through
    levels, per level (`level_measures`); then prepulse inhibition; then
    short-term habituation.

    %PPI = 100 x (1 - mean prepulse+pulse amplitude / mean pulse-alone
    amplitude), per prepulse level and interval and overall.

    Short-term habituation (within one session; across days is worked out
    outside the app, user 2026-11-12) is only reported for a habituation
    session (`habituation`): the pulse-alone trials are split into blocks of
    `block_trials`, in order (a shorter last block is left out), and it is
    100 x (1 - last block's mean / first block's)."""
    out: dict = {"ASR_Trials": len(trials)}
    scored = trials.dropna(subset=["Startle amplitude_pct"])
    out["ASR_TrialsUsed"] = len(scored)
    out["ASR_TrialsNotUsed"] = len(trials) - len(scored)
    kinds = [k for k in TYPE_ORDER if (scored["Type"] == k).any()] + sorted(
        set(scored["Type"].astype(str)) - set(TYPE_ORDER))
    for kind in kinds:
        group = scored[scored["Type"] == kind]
        values = group["Startle amplitude_pct"].astype(float).tolist()
        out[f"ASR_N_{kind}"] = len(values)
        out[f"ASR_Mean_{kind}_pct"] = _mean(values)
        out[f"ASR_Median_{kind}_pct"] = _median(values)
        # The same per pulse frequency (or noise), when the file records it.
        if "Pulse_kHz" in group.columns:
            label = group.apply(_pulse_label, axis=1)
            for name in sorted((x for x in set(label) if x), key=_sound_order):
                part = group[label == name]["Startle amplitude_pct"].astype(float).tolist()
                out[f"ASR_N_{kind}_{name}"] = len(part)
                out[f"ASR_Mean_{kind}_{name}_pct"] = _mean(part)
        if kind == PULSE:
            out.update(level_measures(trials, threshold_sd))
    pulses = scored[scored["Type"] == PULSE]["Startle amplitude_pct"].astype(float).tolist()
    primed = scored[scored["Type"] == PREPULSE_PULSE]
    if pulses and len(primed):
        pulse_mean = _mean(pulses)
        ppi = lambda m: round(100.0 * (1 - m / pulse_mean), 1) if pulse_mean else float("nan")
        out["ASR_PPI_Overall_pct"] = ppi(_mean(primed["Startle amplitude_pct"].astype(float).tolist()))
        keys = primed.apply(lambda r: (_level(r["Prepulse_dB"]), _level(r["Interval_ms"])), axis=1)
        for (db, gap) in sorted(set(keys), key=lambda k: (k[0], k[1])):
            part = primed[keys == (db, gap)]["Startle amplitude_pct"].astype(float).tolist()
            label = "_".join(x for x in ((f"{db}dB" if db else ""), (f"{gap}ms" if gap else "")) if x)
            out[f"ASR_PPI_{label or 'unlabeled'}_pct"] = ppi(_mean(part))
    if habituation:
        block_trials = max(1, int(block_trials))
        blocks = [_mean(pulses[i:i + block_trials])
                  for i in range(0, len(pulses) - block_trials + 1, block_trials)]
        for k, value in enumerate(blocks, start=1):
            out[f"ASR_ShortTermHabituation_Block{k}_Mean_pct"] = value
        if len(blocks) >= 2:
            out["ASR_ShortTermHabituation_pct"] = (
                round(100.0 * (1 - blocks[-1] / blocks[0]), 1) if blocks[0] else float("nan"))
    return out


def repeated_count(data: TrackingData) -> int:
    """How many of the file's frames the recording app marked as copies."""
    if "Repeated" not in data.df.columns:
        return 0
    return int(data.df["Repeated"].to_numpy(dtype=bool).sum())


def real_frame_rate(summary: dict) -> float | None:
    """The frames a second that aren't copies, when MOST of a file's frames
    are copies (the camera ran slower than the video's frame rate, as Boom Box
    did on a Mac before 1.3.4); None for any other file."""
    frames, copies = summary.get("Frames") or 0, summary.get("RepeatedFrames") or 0
    length = summary.get("Duration_s") or 0
    if not frames or copies <= frames / 2 or not length:
        return None
    return (frames - copies) / length


def asr_summary(data: TrackingData, startle_ms: float = 200.0, baseline_ms: float = 200.0,
                block_trials: int = 10, threshold_sd: float = 2.0,
                habituation: bool = False) -> tuple[dict, pd.DataFrame]:
    """(the Data Summary row, the Trials table) for one file. `habituation`:
    the session is a habituation session (its info file's variant is
    Startle Habituation), so short-term habituation is reported."""
    trials = trial_table(data, startle_ms, baseline_ms)
    times = data.df["Time_s"].to_numpy(dtype=float)
    length = float(times[-1] - times[0]) if len(times) > 1 else 0.0
    values = data.df["MotionIndex_pct"].to_numpy(dtype=float)
    row: dict = {"File": data.name}
    row.update(session_measures(trials, block_trials, threshold_sd, habituation))
    row.update({
        "Frames": data.n_frames, "Duration_s": round(length, 2),
        "FPS": round((len(times) - 1) / length, 3) if length else float("nan"),
        "UnreadableFrames": int(data.unreadable.sum()),
        "RepeatedFrames": repeated_count(data),
        "MotionIndex_SessionMean_pct": round(float(np.nanmean(values)), 4)
        if np.any(~np.isnan(values)) else float("nan"),
        # (blank for a motion file whose info file is gone)
        "AnalyzedPixels_px": (int(data.df["Total_px"].max())
                              if "Total_px" in data.df.columns else None),
        "IntensityThreshold_graylevels": data.settings.get("Intensity_Threshold"),
        "StartleWindow_ms": startle_ms, "BaselineWindow_ms": baseline_ms,
    })
    if habituation:
        row["ShortTermHabituationBlock_trials"] = block_trials
    row.update({
        "ThresholdCriterion_SD": threshold_sd,
        "StimulusSource": data.settings.get("Stimulus_Source"),
        "Test": ASR_TEST,
    })
    return row, trials
