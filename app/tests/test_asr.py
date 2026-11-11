"""Acoustic startle (ROADMAP §13): the motion index, the trial measures,
prepulse inhibition and habituation, and reading what the recording app wrote.

Uses the paper's clips in Examples/ASR videos from paper (gitignored).

Run from the project folder:  .venv/bin/python tests/test_asr.py
"""
import json
import math
import os
import shutil
import sys
import tempfile

import cv2
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.asr import (asr_summary, find_info, frame_times, load_motion, motion_table,
                      parse_frames, session_measures, stimuli_from_info, trial_table)
from core.loader import TrackingData
from core.video import Prep
from samples import ASR_CLIP, require
require(ASR_CLIP)

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)


# The engine against an independent calculation on a real clip.
table = motion_table(ASR_CLIP, Prep(), 0, 101, 15, fps=30.0)
cap = cv2.VideoCapture(ASR_CLIP); frames = []
while True:
    ok, f = cap.read()
    if not ok: break
    frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(int))
cap.release()
hand = [100 * float((np.abs(b - a) > 15).mean()) for a, b in zip(frames, frames[1:])]
check("motion index matches a separate frame-by-frame calculation",
      len(table) == 101 and np.allclose(table["MotionIndex_pct"][1:], hand, atol=1e-3))
check("the first frame has no motion index; pixels are out of the whole frame",
      math.isnan(table["MotionIndex_pct"][0]) and table["Total_px"][1] == 744 * 480)
mask = np.zeros((480, 744), bool); mask[:240] = True
half = motion_table(ASR_CLIP, Prep(), 0, 5, 15, mask, fps=30.0)
check("exclusion shapes come out of both the count and the total",
      half["Total_px"][1] == 744 * 240)
crop = motion_table(ASR_CLIP, Prep(crop=(0, 0, 372, 240)), 0, 5, 15, fps=30.0)
check("cropping changes the pixels analyzed", crop["Total_px"][1] == 372 * 240)

# Trial measures on a made-up file at 10 fps: 200 ms = 2 frames.
values = [np.nan, 1, 2, 3, 9, 5, 7, 1, 1, 1, 1, 1]
df = pd.DataFrame({"Frame": range(100, 112), "Time_s": np.arange(12) / 10,
                   "MotionIndex_pct": values, "AboveThreshold_px": [0] * 12,
                   "Total_px": [1000] * 12, "Frame_Unreadable": [False] * 12})
df["AboveThreshold_px"] = [0, 10, 20, 30, 90, 50, 70, 10, 10, 10, 10, 10]
def fake(stimuli):
    return TrackingData("x_MotionIndex.csv", df.copy(), {"Stimuli": json.dumps(stimuli),
                        "Intensity_Threshold": 15}, [])
t = trial_table(fake([{"frame": 103, "type": "pulse"}]))
r = t.iloc[0]
check("baseline is the 2 frames up to the stimulus; startle is the 2 frames after it",
      r["motion.index.before"] == 3 and r["motion.index.after"] == 9)
check("amplitude = startle peak - baseline peak",
      r["Startle amplitude"] == 6)
check("peak frame, its time, its pixels and reaction time from the stimulus",
      r["FrameNo"] == 104 and r["Time.startle"] == 0.4 and r["Pixel.change"] == 90
      and r["ReactionTime"] == 100)
check("no Direction column (left out for now)", "Direction" not in t.columns)
t = trial_table(fake([{"frame": 103, "type": "pulse", "video_time_s": 0.25}]))
check("a measured stimulus time sets the windows (0.25 s: startle is 0.3-0.45)",
      t.iloc[0]["motion.index.after"] == 9 and t.iloc[0]["Stimulus_s"] == 0.25)
t = trial_table(fake([{"frame": 106, "type": "prepulse+pulse", "interval_ms": 200}]))
check("prepulse+pulse: the baseline ends at the prepulse (frames 103-104 here), not the pulse",
      t.iloc[0]["motion.index.before"] == 9 and t.iloc[0]["motion.index.after"] == 1)
t = trial_table(fake([{"frame": 106, "type": "pulse"}]))
check("pulse alone: the baseline is right before the pulse",
      t.iloc[0]["motion.index.before"] == 7)
copies = df.copy(); copies["Repeated"] = [i == 4 for i in range(12)]
t = trial_table(TrackingData("x", copies, {"Stimuli": json.dumps([{"frame": 103}])}, []))
check("a repeated frame can't be the peak, and the trial says so",
      t.iloc[0]["motion.index.after"] == 5 and "1 repeated" in t.iloc[0]["Note"])
t = trial_table(fake([{"frame": 100}, {"frame": 111}, {"frame": 500}]))
check("windows outside the recording leave the amplitude blank and say why",
      pd.isna(t["Startle amplitude"]).all()
      and "baseline" in t["Note"][0] and "startle" in t["Note"][1] and "outside" in t["Note"][2])
bad = df.copy(); bad.loc[5, "MotionIndex_pct"] = np.nan; bad.loc[5, "Frame_Unreadable"] = True
one = trial_table(TrackingData("x", bad, {"Stimuli": json.dumps([{"frame": 103}])}, []))
check("an unreadable frame is noted and left out of the peak",
      "1 unreadable" in one["Note"][0] and one["motion.index.after"][0] == 9)
check("an unreadable frame in a window is flagged, and the amplitude is still worked out",
      not pd.isna(one["Startle amplitude"][0])
      and one["Startle amplitude"][0] == one["motion.index.after"][0] - one["motion.index.before"][0])

# Session measures from the shown amplitudes.
rows = [("pulse", None, None, 10), ("pulse", None, None, 8), ("pulse", None, None, 6),
        ("pulse", None, None, 4), ("prepulse+pulse", 74, 100, 3), ("prepulse+pulse", 74, 100, 5),
        ("prepulse+pulse", 82, 100, 2), ("none", None, None, 0.5)]
trials = pd.DataFrame(rows, columns=["Type", "Prepulse_dB", "Interval_ms", "Startle amplitude"])
m = session_measures(trials, block_trials=2)
check("mean, median and count per trial type",
      m["ASR_Mean_pulse"] == 7 and m["ASR_Median_pulse"] == 7 and m["ASR_N_pulse"] == 4
      and m["ASR_Mean_prepulse+pulse"] == round(10 / 3, 4) and m["ASR_Mean_none"] == 0.5)
check("% PPI from startle amplitudes, overall and per level and interval",
      m["ASR_PPI_Overall_pct"] == round(100 * (1 - round(10 / 3, 4) / 7), 1)
      and m["ASR_PPI_74dB_100ms_pct"] == round(100 * (1 - 4 / 7), 1)
      and m["ASR_PPI_82dB_100ms_pct"] == round(100 * (1 - 2 / 7), 1))
check("habituation from pulse-alone blocks: first vs last",
      m["ASR_Block1_Mean"] == 9 and m["ASR_Block2_Mean"] == 5
      and m["ASR_Habituation_pct"] == round(100 * (1 - 5 / 9), 1))
short = session_measures(trials, block_trials=3)
check("a shorter last block is left out; one block gives no habituation",
      "ASR_Block2_Mean" not in short and "ASR_Habituation_pct" not in short)
freq = pd.DataFrame({"Type": ["pulse"] * 3, "Pulse_kHz": [4.0, 4.0, 12.0], "Pulse_Kind": ["tone"] * 3,
                     "Prepulse_dB": [None] * 3, "Interval_ms": [None] * 3,
                     "Startle amplitude": [2.0, 4.0, 9.0]})
f = session_measures(freq)
check("mean per pulse frequency as well as overall",
      f["ASR_Mean_pulse_4kHz"] == 3 and f["ASR_N_pulse_12kHz"] == 1 and f["ASR_Mean_pulse"] == 5)
check("no pulse-alone trials: no PPI",
      "ASR_PPI_Overall_pct" not in session_measures(trials[trials["Type"] != "pulse"]))

# Typed frames and the recording app's files.
check("typed stimulus frames: any separators, sorted, repeats dropped",
      parse_frames("50, 120\n90 50") == [50, 90, 120])
try:
    parse_frames("50, abc"); check("a bad entry is refused", False)
except ValueError as exc:
    check("a bad entry is refused and named", "abc" in str(exc))
tmp = tempfile.mkdtemp()
try:
    video = os.path.join(tmp, "2026-11-05_16-56-42_ASR1_Side.mp4")
    shutil.copy(ASR_CLIP, video)
    json.dump({"schema_version": 1, "cameras": [{"video": "other.mp4"}]},
              open(os.path.join(tmp, "2026-11-05_16-56-42_ASR2_info.json"), "w"))
    json.dump({"schema_version": 1, "assay": "Acoustic Startle Response",
               "cameras": [{"video": os.path.basename(video), "timestamps_csv": "t_frames.csv"}],
               "stimuli": [{"frame": 50, "video_time_s": 1.67, "type": "pulse", "pulse_db": 120},
                           {"bad": 1}]},
              open(os.path.join(tmp, "2026-11-05_16-56-42_ASR1_info.json"), "w"))
    pd.DataFrame({"frame": range(101), "video_time_s": np.arange(101) / 29.5,
                  "repeated": [i == 60 for i in range(101)]}).to_csv(
        os.path.join(tmp, "t_frames.csv"), index=False)
    boom = {"stimuli": [{"frame": 5, "type": "pulse"}],
            "boom_box": {"trials": [{"pulse_freq_hz": "4000.0", "pulse_stimulus": "tone"}]}}
    check("frequency and kind come from boom_box.trials when stimuli doesn't have them",
          stimuli_from_info(boom)[0]["pulse_freq_hz"] == 4000
          and stimuli_from_info(boom)[0]["pulse_stimulus"] == "tone")
    info, camera = find_info(video)
    check("a video finds the info file that lists it by exact name",
          info["assay"] == "Acoustic Startle Response")
    check("stimuli are read; entries without a frame are skipped",
          stimuli_from_info(info) == [{"frame": 50, "type": "pulse", "video_time_s": 1.67,
                                       "pulse_db": 120}])
    times = frame_times(video, camera)
    check("frame times come from the frames file", abs(times[59] - 2.0) < 1e-9)
    from core.asr import AsrJob, run_asr_job
    job = AsrJob(video, Prep(), 0, 101, None, 15.0, 30.0, 0, [])
    data, csv = run_asr_job(job)
    check("the motion index file is saved beside the video, with measured times",
          csv.endswith("_MotionIndex.csv") and abs(data.df["Time_s"][59] - 2.0) < 1e-3)
    check("repeated frames are recorded from the frames file",
          bool(data.df["Repeated"][60]) and not data.df["Repeated"][59])
    back = load_motion(csv)
    check("the file reloads with its stimuli and threshold",
          back.settings["Intensity_Threshold"] == 15 and back.regions == []
          and back.settings["Stimulus_Source"] == "info file")
    s, tt = asr_summary(back)
    check("summary row and trials from the file", s["ASR_Trials"] == 1 and len(tt) == 1
          and s["IntensityThreshold"] == 15 and tt["Pulse_dB"][0] == 120)
    other = os.path.join(tmp, "plain.mp4"); shutil.copy(ASR_CLIP, other)
    data, _ = run_asr_job(AsrJob(other, Prep(), 0, 101, None, 15.0, 30.0, 0, [50]))
    check("without an info file, typed frames are used",
          data.settings["Stimulus_Source"] == "typed in")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# A frames file that can't be used is ignored (times come from the frame
# rate), rather than failing the video.
from core.asr import repeated_frames
with tempfile.TemporaryDirectory() as folder:
    video = os.path.join(folder, "clip.mp4")
    camera = {"timestamps_csv": "clip_frames.csv"}
    with open(os.path.join(folder, "clip_frames.csv"), "w") as f:
        f.write("frame,video_time_s,repeated\n0,0.0,False\n1,0.05,True\n,,\n2,0.1,False\n")
    check("a frames file with a blank row is read without it",
          frame_times(video, camera) == {0: 0.0, 1: 0.05, 2: 0.1}
          and repeated_frames(video, camera) == {1})
    with open(os.path.join(folder, "clip_frames.csv"), "w") as f:
        f.write("frame,video_time_s,repeated\nzero,soon,maybe\n")
    check("a frames file that isn't numbers is ignored, not an error",
          frame_times(video, camera) is None and repeated_frames(video, camera) == set())
    check("no frames file: no times", frame_times(video, {"timestamps_csv": "missing.csv"}) is None
          and frame_times(video, None) is None)

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
