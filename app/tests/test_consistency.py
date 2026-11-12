"""The same quantity is never reported as two different numbers (user's rule,
2026-11-05): a frame on a border the center shares counts for the center
only, per-region time / % / entries match the EPM and Open Field measures,
and role totals are the per-region values added up.

Runs on the example tracking files in Examples/ (tests/samples.py;
gitignored), plus a small made-up file.

Run from the project folder:  .venv/bin/python tests/test_consistency.py
"""
import scratch  # noqa: F401  (first: temporary files go in app/tests/.tmp, removed after the run)
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import load_csv, summary_metrics, epm_metrics, of_metrics, binned_metrics, epm_binned
from core.loader import TrackingData
from core.regions import resolve_roles
from samples import EPM, OF, require
require(EPM, OF)

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)


def close(a, b, tol=0.011):
    return abs(float(a) - float(b)) <= tol


def epm_checks(path, fps=None):
    d = load_csv(path)
    fps = fps or float(d.settings.get("Video_FPS", 20) or 20)
    roles = resolve_roles(d.regions, {})
    s = summary_metrics(d, fps, roles, 5)
    s.update(epm_metrics(d, roles, fps, 5))
    name = os.path.basename(path)
    by = lambda k: [r for r in d.regions if roles[r] == k]
    check(f"{name}: no ROI-label columns", not any(c.startswith(("Time_ROI_", "Percent_ROI_")) for c in s))
    for key, role in (("OpenArm", "open_arm"), ("ClosedArm", "closed_arm"), ("Center", "center")):
        check(f"{name}: EPM {key} time = its regions' times added up",
              close(s[f"EPM_{key}_s"], round(sum(s[f"Time_{r}_s"] for r in by(role)), 2), 1e-9))
    for key, role in (("Open", "open_arm"), ("Closed", "closed_arm"), ("Center", "center")):
        check(f"{name}: EPM % session {key} = its regions' % added up",
              close(s[f"EPM_PctSession_{key}"], round(sum(s[f"Percent_{r}"] for r in by(role)), 1), 1e-9))
        check(f"{name}: EPM {key} entries = its regions' entries added up",
              s[f"EPM_{key}Entries"] == sum(s[f"Entries_{r}"] for r in by(role)))
    check(f"{name}: region %s add up to at most 100",
          sum(s[f"Percent_{r}"] for r in d.regions) <= 100.0 + 0.05 * len(d.regions))
    # Formulas re-worked from the shown values give exactly the shown values.
    O, C, D = s["EPM_OpenArm_s"], s["EPM_ClosedArm_s"], s["Duration_s"]
    oe, ce = s["EPM_OpenEntries"], s["EPM_ClosedEntries"]
    check(f"{name}: % open / closed time, ratios, % open entries, anxiety index are "
          "formulas of the shown values",
          s["EPM_PctOpenTime"] == round(100 * O / (O + C), 1)
          and s["EPM_PctOpenTime"] + s["EPM_PctClosedTime"] == 100
          and s["EPM_ClosedOpenRatio"] == round(C / O, 3)
          and s["EPM_OpenClosedRatio"] == round(O / C, 3)
          and s["EPM_PctOpenEntries"] == round(100 * oe / (oe + ce), 1)
          and s["EPM_AnxietyIndex"] == round(1 - (s["EPM_PctOpenTime"]
                                                   + s["EPM_PctOpenEntries"]) / 200, 3))
    check(f"{name}: region % = region time / session length; mean speed = distance / duration",
          all(s[f"Percent_{r}"] == round(100 * s[f"Time_{r}_s"] / D, 1) for r in d.regions)
          and s["MeanSpeed_cm_s"] == round(s["TotalDistance_cm"] / D, 3)
          and s["Duration_min"] == round(D / 60, 3))
    bins = binned_metrics(d, fps, 60, roles).merge(epm_binned(d, roles, fps, 60, 5), on="Bin")
    check(f"{name}: per-bin closed time = its regions' bin times added up",
          all(close(row["EPM_ClosedArm_s"], sum(row[f"Time_{r}_s"] for r in by("closed_arm")))
              for _, row in bins.iterrows()))
    return d, s


ex = EPM
d, s = epm_checks(ex)
check("example: per-region center entries use the entry rule (equal EPM center entries)",
      s["Entries_center"] == s["EPM_CenterEntries"])

# Frames outside every drawn region (user, 2026-11-05): Open Field counts them
# as periphery, EPM as the nearest region; brief stretches are listed.
from core import outside_events
ofx = OF
if True:
    d = load_csv(ofx); roles = resolve_roles(d.regions, {}); fps = float(d.settings["Video_FPS"])
    s = summary_metrics(d, fps, roles, 5, min_gap_s=1.0)
    s.update(of_metrics(d, roles, fps, 5, min_between_entries_s=1.0))
    sides = s["OF_Left_s"] + s["OF_Right_s"] + s["OF_Top_s"] + s["OF_Bottom_s"]
    ev = outside_events(d, roles, fps)
    check("Open Field video: outside frames count as periphery (center + periphery = session; "
          "sides add up to periphery)",
          close(s["OF_Center_s"] + s["OF_Periphery_s"], s["Duration_s"], 0.02)
          and close(sides, s["OF_Periphery_s"], 0.02)
          and all(e["region"] == "periphery" for e in ev))
    check("Open Field video: outside stretches listed and summarized (brief: jumps)",
          s["OutsideEvents"] == len(ev) > 0 and s["OutsideEventMax_s"] < 1
          and close(s["OutsideEventMean_s"], s["OutsideTime_s"] / len(ev), 0.001))
if True:
    d = load_csv(ex); roles = resolve_roles(d.regions, {}); fps = float(d.settings["Video_FPS"])
    s = summary_metrics(d, fps, roles, 5); s.update(epm_metrics(d, roles, fps, 5))
    ev = outside_events(d, roles, fps)
    check("EPM example: outside frames go to the nearest region (every frame counted)",
          close(s["EPM_OpenArm_s"] + s["EPM_ClosedArm_s"] + s["EPM_Center_s"], s["Duration_s"], 0.03)
          and s["OutsideEvents"] == len(ev)
          and all(e["region"] in d.regions for e in ev))

# Open Field: per-region columns equal the OF_ measures.
d = load_csv(OF)
roles = resolve_roles(d.regions, {})
fps = float(d.settings["Video_FPS"])
s = summary_metrics(d, fps, roles, 5, min_gap_s=1.0)
s.update(of_metrics(d, roles, fps, 5, min_between_entries_s=1.0))
c = [r for r in d.regions if roles[r] == "center"][0]
p = [r for r in d.regions if roles[r] == "periphery"][0]
check("Open Field: center time / % / entries equal the OF_ measures",
      s[f"Time_{c}_s"] == s["OF_Center_s"] and s[f"Percent_{c}"] == s["OF_PctCenter"]
      and s[f"Entries_{c}"] == s["OF_CenterEntries"])
check("Open Field: periphery time / % equal the OF_ measures (center wins where they overlap)",
      s[f"Time_{p}_s"] == s["OF_Periphery_s"] and s[f"Percent_{p}"] == s["OF_PctPeriphery"])

check("Open Field: % center / periphery = their time / session length",
      s["OF_PctCenter"] == round(100 * s["OF_Center_s"] / s["Duration_s"], 1)
      and s["OF_PctPeriphery"] == round(100 * s["OF_Periphery_s"] / s["Duration_s"], 1)
      and s["OF_Crossings_Total"] == s["OF_Crossings_Opposite"] + s["OF_Crossings_Adjoining"]
      and s["OF_Crossings_Opposite"] == s["OF_Crossings_LeftRight"] + s["OF_Crossings_TopBottom"])
from core import drop_duplicates
kept = drop_duplicates(s, roles, "Open Field")
check("Open Field: per-region center / periphery columns that repeat OF_ measures are dropped",
      not {f"Time_{c}_s", f"Percent_{c}", f"Entries_{c}", f"Time_{p}_s", f"Percent_{p}"} & set(kept)
      and f"Entries_{p}" in kept and "OF_Center_s" in kept)

# A made-up file: frames on the center's border, and two arms sharing frames.
df = pd.DataFrame({
    "Frame": range(8), "X": np.arange(8.0), "Y": np.zeros(8),
    "center":       [0, 1, 1, 0, 0, 0, 0, 0],
    "open arm 1":   [1, 1, 0, 0, 1, 1, 0, 0],
    "closed arm 1": [0, 0, 1, 1, 0, 1, 1, 1],
}).astype({"center": bool, "open arm 1": bool, "closed arm 1": bool})
fake = TrackingData("fake.csv", df, {}, ["center", "open arm 1", "closed arm 1"])
roles = resolve_roles(fake.regions, {})
s = summary_metrics(fake, 1.0, roles, 1)
check("shared center frames count for the center only",
      s["Time_center_s"] == 2 and s["Time_open arm 1_s"] == 3 and s["Time_closed arm 1_s"] == 3)
check("frames in two non-center regions are reported",
      s["SharedRegionFrames"] == 1 and "open arm 1 + closed arm 1 (1 frames)" == s["SharedRegions"])

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
