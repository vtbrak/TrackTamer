"""Every heading in every exported table carries its unit (user, 2026-11-12):
a measurement's heading ends in (or contains) its unit, and only counts,
ratios, indexes, labels and settings named for what they count go without.
Also: exclusion shapes are trimmed to the video frame.

Run from the project folder:  .venv/bin/python tests/test_units.py
"""
import scratch  # noqa: F401  (first: temporary files go in app/tests/.tmp, removed after the run)
import json
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from samples import EPM, OF, require
from core.asr import TRIAL_COLUMNS, asr_summary, session_measures
from core.loader import TrackingData, load_csv
from core.metrics import (binned_metrics, drop_duplicates, epm_binned, epm_metrics, of_binned,
                          of_metrics, order_bins, order_summary, summary_metrics)
from core.regions import resolve_roles
from core.video import VideoInfo
from core.video_setup import VideoSetup, clip_to_frame
require(EPM, OF)

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)


# A heading has a unit if it ends with one of these (before nothing else), or
# names its unit inside it.
UNIT = re.compile(r"(_s|_ms|_min|_cm|_px|_cm_s|_pct|_dB|_kHz|_SD|_trials|_frames|_graylevels|_cm_per_px)$")
NAMED = re.compile(r"(Percent_|Pct|Frames?$|Frame$|FPS$|FrameNo$)")
# Counts, ratios, indexes and labels: nothing to measure in.
UNITLESS = re.compile(
    r"^(File|animal_id|trial_day|session_number|Test|Bin|Trial|Type|Note|Pulse_Kind|Status|StimulusSource|SharedRegions|"
    r"FillGaps|OR_Phase|OR_NovelObjects|OR_ZoneDistance|"
    r"Entries_.*|Region_transitions|OutsideEvents|EPM_.*Entries|EPM_.*Ratio|EPM_AnxietyIndex|"
    r"OF_.*Entries|OF_Crossings_.*|OR_Bouts_.*|OR_ZoneVisits_.*|OR_VisitsNotReviewed|"
    r"OR_DiscriminationIndex|ASR_Trials.*|ASR_N_.*)$")

def without_unit(columns):
    return [c for c in columns if not (UNIT.search(c) or NAMED.search(c) or UNITLESS.match(c))]

for test, path, extra, binned in (("Elevated Plus Maze", EPM, epm_metrics, epm_binned),
                                  ("Open Field", OF, of_metrics, of_binned)):
    data = load_csv(path); roles = resolve_roles(data.regions, {})
    kw = dict(fps=20.0, min_entry_frames=5)
    if test == "Open Field":
        kw.update(min_between_entries_s=1.0, min_center_adjoining_s=0.5, speed_smoothing_frames=5)
    row = summary_metrics(data, fps=20.0, roles=roles, min_entry_frames=5)
    row.update(extra(data, roles, **kw))
    row.update({"Test": test, "MinEntryFrames": 5, "FillGaps": False, "FillGapsMaxFrames": 5,
                "MinBetweenCenterEntries_s": 1.0, "MinCenterAdjoiningCrossing_s": 0.5,
                "SpeedSmoothing_frames": 5, "RepeatedFrames": 0})
    row = order_summary(drop_duplicates(row, roles, test), test)
    bins = binned_metrics(data, fps=20.0, bin_seconds=60.0, roles=roles)
    bins = bins.merge(binned(data, roles, bin_seconds=60.0, **kw), on="Bin", how="left")
    bins = order_bins(drop_duplicates(bins, roles, test), test)
    check(f"{test}: every Data Summary heading has its unit (missing: {without_unit(row)})",
          without_unit(row) == [])
    check(f"{test}: every Time Bins heading has its unit (missing: {without_unit(bins.columns)})",
          without_unit(bins.columns) == [])

# Acoustic startle: a made-up session with every kind of trial and two levels.
n = 600
df = pd.DataFrame({"Frame": range(n), "Time_s": np.arange(n) / 30, "MotionIndex_pct": 0.1,
                   "AboveThreshold_px": 10, "Total_px": 1000, "Frame_Unreadable": False,
                   "Repeated": False})
stimuli = [{"frame": 60, "type": "pulse", "pulse_db": 100, "pulse_freq_hz": 8000, "pulse_stimulus": "tone"},
           {"frame": 120, "type": "pulse", "pulse_db": 120, "pulse_freq_hz": 8000, "pulse_stimulus": "tone"},
           {"frame": 180, "type": "prepulse+pulse", "pulse_db": 120, "prepulse_db": 74, "interval_ms": 100},
           {"frame": 240, "type": "prepulse", "prepulse_db": 74}, {"frame": 300, "type": "none"},
           {"frame": 360, "type": "pulse", "pulse_db": 100, "pulse_freq_hz": 8000, "pulse_stimulus": "tone"},
           {"frame": 420, "type": "pulse", "pulse_db": 120, "pulse_freq_hz": 8000, "pulse_stimulus": "tone"}]
data = TrackingData("x_MotionIndex.csv", df, {"Stimuli": json.dumps(stimuli), "Intensity_Threshold": 15,
                                               "Stimulus_Source": "info file"}, [])
row, trials = asr_summary(data, block_trials=2, habituation=True)
check(f"Startle: every Data Summary heading has its unit (missing: {without_unit(row)})",
      without_unit(row) == [] and "ASR_ShortTermHabituation_pct" in row
      and "ASR_Mean_pulse_100dB_pct" in row and "ASR_PPI_Overall_pct" in row)
check(f"Startle: every Trials heading has its unit (missing: {without_unit(trials.columns)})",
      without_unit(trials.columns) == [] and "Prepulse_dB" in trials.columns)
check("the check itself would catch a heading with no unit",
      without_unit(["ASR_Mean_pulse", "Startle amplitude", "EPM_Center", "Time.startle"])
      == ["ASR_Mean_pulse", "Startle amplitude", "EPM_Center", "Time.startle"])

# --- exclusion shapes are trimmed to the frame --------------------------------
xs, ys = clip_to_frame([1015.3, 1058.8, 1310.8, 1305.4], [557.6, 708.1, 691.8, 481.5], 1280, 720)
check("a shape drawn past the right edge is cut at the edge",
      max(xs) == 1280 and min(xs) > 1000 and max(ys) <= 720 and len(xs) >= 4
      and sum(1 for x in xs if x == 1280) == 2)
xs2, ys2 = clip_to_frame([931.9, 922.8, 1329.0, 1285.4], [-29.8, 86.2, 77.2, -86.0], 1280, 720)
check("one past the top and the right is cut at both, keeping the corner of the frame",
      min(ys2) == 0 and max(xs2) == 1280 and (1280.0, 0.0) in list(zip(xs2, ys2)))
inside = ([10.0, 50.0, 50.0], [10.0, 10.0, 60.0])
check("a shape inside the frame is left exactly as drawn",
      clip_to_frame(*inside, 1280, 720) == inside)
check("a shape wholly outside the frame leaves nothing",
      clip_to_frame([1300, 1400, 1400], [10, 10, 80], 1280, 720) == ([], []))
setup = VideoSetup(path="v.mp4", info=VideoInfo("v.mp4", 100, 30.0, 1280, 720))
check("adding one to a video's setup keeps the trimmed shape; one outside isn't added",
      setup.add_exclusion([1200, 1400, 1400, 1200], [600, 600, 800, 800])
      and setup.exclusions == [([1200.0, 1280.0, 1280.0, 1200.0], [600.0, 600.0, 720.0, 720.0])]
      and not setup.add_exclusion([1300, 1400, 1400], [10, 10, 80]) and len(setup.exclusions) == 1)
mask = setup.exclusion_mask(1.0)
check("the excluded pixels are the same as for the shape as drawn",
      int(mask.sum()) > 0 and bool(mask[700, 1270]) and not bool(mask[500, 1270]))
old = VideoSetup(path="v.mp4", info=VideoInfo("v.mp4", 100, 30.0, 1280, 720))
old.restore({"frame_size": [1280, 720], "exclusions": [{"xs": [1200, 1400, 1400, 1200],
                                                         "ys": [-50, -50, 100, 100]}]}, "")
check("a setup saved before this is trimmed when it's restored",
      len(old.exclusions) == 1 and sorted(zip(*old.exclusions[0]))
      == [(1200.0, 0.0), (1200.0, 100.0), (1280.0, 0.0), (1280.0, 100.0)])

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
