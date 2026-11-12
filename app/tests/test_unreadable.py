"""Checks that unreadable video frames are handled in the analysis, using the
example tracking files in Examples/ (tests/samples.py; gitignored, so this
only runs where they exist) with gaps added the way this app's tracking writes them.

Run from the project folder:  .venv/bin/python tests/test_unreadable.py
"""
import scratch  # noqa: F401  (first: temporary files go in app/tests/.tmp, removed after the run)
import os
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import load_csv, summary_metrics, epm_metrics, of_metrics, binned_metrics
from core import resolve_roles
from core.gaps import fill_gaps

from samples import EPM as E, OF as O, require
require(E, O)

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)

tmp = tempfile.mkdtemp()

def with_gaps(path, gaps):
    """Copy of a sample file with the given (start, length) gaps made
    unreadable: blank position, regions and ROI label; blank distance for the
    gap and the frame after it; Frame_Unreadable True."""
    df = pd.read_csv(path)
    data = load_csv(path)
    bad = np.zeros(len(df), dtype=bool)
    for start, length in gaps:
        bad[start:start + length] = True
    after = np.concatenate([[False], bad[:-1]]) & ~bad
    df.loc[bad, ["X", "Y"]] = np.nan
    df[data.regions] = df[data.regions].astype(object)
    df.loc[bad, data.regions] = None
    df.loc[bad, "ROI_location"] = None
    df.loc[bad | after, ["Distance_px", "Distance_cm"]] = np.nan
    df["Frame_Unreadable"] = bad
    out = os.path.join(tmp, os.path.basename(path))
    df.to_csv(out, index=False)
    return load_csv(out), bad

for path, test in ((E, "Elevated Plus Maze"), (O, "Open Field")):
    base = load_csv(path)
    roles = resolve_roles(base.regions, {})
    gapped, bad = with_gaps(path, [(1000, 3), (2000, 50)])
    name = os.path.basename(path)
    check(f"{name}: Frame_Unreadable isn't taken for a region", gapped.regions == base.regions)
    check(f"{name}: plain files have no unreadable frames", not base.unreadable.any())
    s0, s1 = summary_metrics(base, 20), summary_metrics(gapped, 20)
    check(f"{name}: UnreadableFrames counted", s1["UnreadableFrames"] == 53 and s0["UnreadableFrames"] == 0)
    r0 = base.regions[0]
    lost = int(base.df[r0].to_numpy(bool)[bad].sum())
    check(f"{name}: unreadable frames add no region time",
          abs((s0[f"Time_{r0}_s"] - s1[f"Time_{r0}_s"]) - lost / 20) < 0.011)
    check(f"{name}: no distance across gaps", s1["TotalDistance_px"] < s0["TotalDistance_px"])
    check(f"{name}: gaps add no zone entries",
          all(s1[f"Entries_{z}"] <= s0[f"Entries_{z}"] for z in base.regions))
    if test == "Elevated Plus Maze":
        m0, m1 = epm_metrics(base, roles, 20), epm_metrics(gapped, roles, 20)
        keys = ("EPM_OpenEntries", "EPM_ClosedEntries", "EPM_CenterEntries")
    else:
        m0, m1 = of_metrics(base, roles, 20), of_metrics(gapped, roles, 20)
        keys = ("OF_CenterEntries", "OF_Crossings_Total")
    check(f"{name}: test entries aren't inflated by gaps " +
          str({k: (m0[k], m1[k]) for k in keys}),
          all(m1[k] <= m0[k] for k in keys))
    bins = binned_metrics(gapped, 20, 60)
    check(f"{name}: Time Bins report unreadable frames", bins["UnreadableFrames"].sum() == 53)

    filled = fill_gaps(gapped, 5)
    check(f"{name}: short gap filled, long gap left blank",
          int(filled.df["Frame_Filled"].sum()) == 3 and int(filled.unreadable.sum()) == 50)
    check(f"{name}: original data untouched", int(gapped.unreadable.sum()) == 53
          and "Frame_Filled" not in gapped.df.columns)
    x = filled.df["X"].to_numpy()
    check(f"{name}: filled positions lie between the neighbours",
          np.all(np.isfinite(x[1000:1003])) and
          min(x[999], x[1003]) - 1e-9 <= x[1001] <= max(x[999], x[1003]) + 1e-9)
    s2 = summary_metrics(filled, 20)
    check(f"{name}: filled summary", s2["UnreadableFrames"] == 50 and s2["FilledFrames"] == 3)
    check(f"{name}: filled frames get region values",
          filled.df.loc[1000:1002, base.regions].notna().all().all())
    check(f"{name}: filling off changes nothing",
          int(fill_gaps(gapped, 0).unreadable.sum()) == 53)

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
