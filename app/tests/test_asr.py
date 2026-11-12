"""Acoustic startle (ROADMAP §13): the motion index, the trial measures,
prepulse inhibition and habituation, and reading what the recording app wrote.

Uses the paper's clips in Examples/ASR videos from paper (gitignored).

Run from the project folder:  .venv/bin/python tests/test_asr.py
"""
import scratch  # noqa: F401  (first: temporary files go in app/tests/.tmp, removed after the run)
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
from core.asr import asr_summary, real_frame_rate
row, _ = asr_summary(TrackingData("x", copies, {"Stimuli": json.dumps([{"frame": 103}])}, []))
check("the Summary counts repeated frames; a few repeats aren't flagged",
      row["RepeatedFrames"] == 1 and real_frame_rate(row) is None)
row, _ = asr_summary(fake([{"frame": 103}]))
check("a file with no Repeated column has none", row["RepeatedFrames"] == 0
      and real_frame_rate(row) is None)
slow = df.copy(); slow["Repeated"] = [i % 3 != 0 for i in range(12)]
row, _ = asr_summary(TrackingData("x", slow, {"Stimuli": json.dumps([{"frame": 103}])}, []))
check("most frames repeated: flagged, with the real frames a second (4 in 1.1 s)",
      row["RepeatedFrames"] == 8 and abs(real_frame_rate(row) - 4 / 1.1) < 1e-9)
half = df.copy(); half["Repeated"] = [i % 2 == 0 for i in range(12)]
row, _ = asr_summary(TrackingData("x", half, {"Stimuli": json.dumps([{"frame": 103}])}, []))
check("exactly half repeated isn't 'most'", real_frame_rate(row) is None)
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
# Startle by sound level (sessions that step through levels).
from core.asr import (TRIAL_COLUMNS, baseline_criterion, level_curves, level_measures,
                      startle_threshold)
def session(spec, quiet=0):
    """Pulse-alone trials: spec is [(sound, dB, [startle-window peaks])]. Every
    baseline-window peak is 0.5, 0.6 or 0.7 in turn."""
    out, n = [], 0
    for sound, db, peaks in spec:
        for peak in peaks:
            before = (0.5, 0.6, 0.7)[n % 3]; n += 1
            out.append({"Type": "pulse", "Pulse_kHz": sound if sound != "noise" else None,
                        "Pulse_Kind": "noise" if sound == "noise" else "tone", "Pulse_dB": db,
                        "motion.index.before": before, "motion.index.after": peak,
                        "Startle amplitude": round(peak - before, 4)})
    for _ in range(quiet):
        out.append({"Type": "none", "motion.index.before": 0.6, "motion.index.after": 0.65,
                    "Startle amplitude": 0.05})
    return pd.DataFrame(out, columns=TRIAL_COLUMNS)

io = session([("noise", 70, [0.6, 0.7, 0.6]), ("noise", 80, [0.9, 1.0, 0.8]),
              ("noise", 90, [0.6, 0.5, 0.7]), ("noise", 100, [3.0, 3.6, 3.3]),
              ("noise", 110, [5.0, 5.6, 5.3]), ("noise", 120, [4.0, 4.6, 4.3])], quiet=3)
crit = baseline_criterion(io)
before = io["motion.index.before"].to_numpy(float)
check("the criterion is the mean of every trial's baseline peak plus 2 SD of them",
      abs(crit - (before.mean() + 2 * before.std(ddof=1))) < 1e-9
      and abs(baseline_criterion(io, 3) - (before.mean() + 3 * before.std(ddof=1))) < 1e-9
      and baseline_criterion(io.iloc[:1]) is None)
curve = level_curves(io)["noise"]
check("the pulse-alone trials are grouped by level, in rising order, with mean and spread",
      [r["db"] for r in curve] == [70, 80, 90, 100, 110, 120] and all(r["n"] == 3 for r in curve)
      and abs(curve[3]["peak"] - 3.3) < 1e-9 and curve[3]["sem"] > 0
      and list(level_curves(io)) == ["noise"])
check("the threshold is the lowest level from which it and every louder level respond: "
      "80 dB responds here but 90 doesn't, so it's 100",
      curve[1]["peak"] > crit > curve[2]["peak"] and startle_threshold(curve, crit) == 100)
check("no threshold when the loudest level doesn't respond, or there's no criterion",
      startle_threshold(curve[:3], crit) is None and startle_threshold(curve, None) is None)
m = level_measures(io)
check("the Summary gets the mean and count at each level, the threshold, and the largest "
      "mean with its level",
      [k for k in m if k.startswith("ASR_Mean_")] == [f"ASR_Mean_pulse_{d}dB" for d in
                                                      (70, 80, 90, 100, 110, 120)]
      and m["ASR_N_pulse_100dB"] == 3 and m["ASR_Threshold_dB"] == 100
      and m["ASR_Max_pulse_dB"] == 110 and abs(m["ASR_Max_pulse"] - 4.7) < 0.2
      and abs(m["ASR_ThresholdCriterion_pct"] - round(crit, 4)) < 1e-9)
whole = session_measures(io)
check("the no-stimulus trials stay their own column beside the levels (nothing subtracted)",
      whole["ASR_Mean_none"] == 0.05 and whole["ASR_N_none"] == 3
      and whole["ASR_Mean_pulse_100dB"] == m["ASR_Mean_pulse_100dB"])
from core.metrics import key_measures
keys = key_measures("Acoustic Startle Response", columns=whole)
check("the threshold and largest response come right after the means in the key measures",
      keys.index("ASR_Threshold_dB") == keys.index("ASR_Mean_pulse_120dB") + 1
      and keys[keys.index("ASR_Threshold_dB") + 1:][:2] == ["ASR_Max_pulse", "ASR_Max_pulse_dB"])
check("a higher criterion can move the threshold up",
      level_measures(io, threshold_sd=40)["ASR_Threshold_dB"] > 100
      or pd.isna(level_measures(io, threshold_sd=40)["ASR_Threshold_dB"]))
one_level = session([("noise", 120, [4.0, 4.5, 5.0])])
check("a session with one level gets no level columns", level_measures(one_level) == {}
      and not any("dB" in k for k in session_measures(one_level)))
both = session([(8.0, 70, [0.6, 0.6]), (8.0, 90, [3.0, 3.2]), (8.0, 110, [5.0, 5.2]),
                (16.0, 70, [0.6, 0.6]), (16.0, 90, [0.6, 0.7]), (16.0, 110, [2.0, 2.2])])
mb = level_measures(both)
check("frequency and level both varying: each pair, each level pooled, and a threshold and "
      "largest response for each sound",
      mb["ASR_N_pulse_90dB"] == 4 and mb["ASR_N_pulse_8kHz_90dB"] == 2
      and abs(mb["ASR_Mean_pulse_16kHz_110dB"] - 1.5) < 0.3
      and mb["ASR_Threshold_8kHz_dB"] == 90 and mb["ASR_Threshold_16kHz_dB"] == 110
      and mb["ASR_Max_pulse_8kHz_dB"] == 110 and "ASR_Threshold_dB" not in mb)
from core.plotting import level_figure
shown_fig = level_figure(fake([]), io)
flat_fig = level_figure(fake([]), one_level)
check("the level plot draws a curve with its threshold, or says there's none to draw",
      len(shown_fig.axes[0].lines) >= 2 and "threshold 100 dB" in
      [t.get_text() for t in shown_fig.axes[0].texts]
      and "no curve" in flat_fig.axes[0].texts[0].get_text())

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
    on_disk = pd.read_csv(csv)
    check("the motion file on disk holds only what differs from frame to frame",
          list(on_disk.columns) == ["Frame", "Time_s", "MotionIndex_pct", "AboveThreshold_px",
                                    "Frame_Unreadable", "Repeated"])
    own = json.load(open(os.path.join(tmp, "2026-11-05_16-56-42_ASR1_info.json"),
                         encoding="utf-8"))
    kept = own["cameras"][0]["track_tamer"]["tracking"]
    check("what is one value for the video is saved once in its info file, without a copy "
          "of the stimuli",
          kept["File"] == os.path.basename(video) and kept["Intensity_Threshold"] == 15
          and kept["Total_px"] == data.df["Total_px"].max() > 0
          and kept["Stimulus_Source"] == "info file" and "Stimuli" not in kept
          and "Stimulus_Frames" not in kept and len(own["stimuli"]) == 2)
    back = load_motion(csv)
    check("the file reloads with its stimuli, threshold and pixel count",
          back.settings["Intensity_Threshold"] == 15 and back.regions == []
          and back.settings["Stimulus_Source"] == "info file"
          and back.name == os.path.basename(video) and "Total_px" in back.df.columns)
    s, tt = asr_summary(back)
    check("summary row and trials from the file", s["ASR_Trials"] == 1 and len(tt) == 1
          and s["IntensityThreshold"] == 15 and tt["Pulse_dB"][0] == 120)
    other = os.path.join(tmp, "plain.mp4"); shutil.copy(ASR_CLIP, other)
    data, _ = run_asr_job(AsrJob(other, Prep(), 0, 101, None, 15.0, 30.0, 0, [50]))
    from core.asr import file_stimuli
    typed = json.load(open(os.path.join(tmp, "plain_info.json"), encoding="utf-8"))
    check("without an info file, typed frames are used, and kept in the info file made "
          "for the video",
          data.settings["Stimulus_Source"] == "typed in"
          and file_stimuli(data) == [{"frame": 50, "type": "pulse"}]
          and typed["cameras"][0]["track_tamer"]["tracking"]["Stimulus_Frames"] == [50])
    older = os.path.join(tmp, "older_MotionIndex.csv")
    full = data.df.copy(); full["Stimuli"] = ""
    full.loc[0, "Stimuli"] = json.dumps([{"frame": 70, "type": "pulse"}])
    full.to_csv(older, index=False)
    old_file = load_motion(older)
    check("an older motion file that holds its own settings and stimuli still loads",
          file_stimuli(old_file) == [{"frame": 70, "type": "pulse"}]
          and old_file.name == "plain.mp4" and asr_summary(old_file)[0]["ASR_Trials"] == 1)
    lone = os.path.join(tmp, "lone_MotionIndex.csv")
    pd.read_csv(os.path.join(tmp, "plain_MotionIndex.csv")).to_csv(lone, index=False)
    alone = load_motion(lone)
    check("a slim motion file without its info file still loads (no stimuli, no pixel count)",
          file_stimuli(alone) == [] and asr_summary(alone)[0]["AnalyzedPixels"] is None)
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
