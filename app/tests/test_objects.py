"""Object recognition core (ROADMAP §15): objects in the tracking file,
zones, zone visits, the scoring file and the results.

Run from the project folder:  .venv/bin/python tests/test_objects.py
"""
import math
import os
import shutil
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core.loader import load_csv
from core.objects import (Scoring, TrialObject, distance_px, file_objects, load_scoring,
                          update_trial_info,
                          object_at, object_metrics, objects_from_text, objects_to_text,
                          save_scoring, scoring_path, trial_info, trial_summary, zone_visits)
from core.regions import TEST_TYPES

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)


tmp = tempfile.mkdtemp()
try:
    objs = [TrialObject("object 1", 20, 50, 5, "Familiar"),
            TrialObject("object 2", 80, 50, 5, "Novel")]
    check("objects round-trip through the tracking file's text",
          objects_from_text(objects_to_text(objs)) == objs and objects_from_text("bad") == [])
    check("Object Recognition is a test type", "Object Recognition" in TEST_TYPES)

    # 1 fps; the point walks along y = 50 from x = 0 to x = 99, one px a frame.
    # Scale: 0.5 cm per px, so a 2 cm zone is 4 px out from each edge:
    # object 1 zone covers x 11..29, object 2 zone x 71..89.
    n = 100
    df = pd.DataFrame({"Frame": range(n), "X": np.arange(n, dtype=float), "Y": np.full(n, 50.0),
                       "Distance_px": np.ones(n), "Frame_Unreadable": [False] * n})
    df["Objects"] = objects_to_text(objs)
    df["Trial_Day"] = 2
    df["Trial_Phase"] = "Test"
    df["Scale_cm_per_px"] = 0.5
    df["Start_Frame"] = 300
    path = os.path.join(tmp, "m1_LocationOutput.csv")
    df.to_csv(path, index=False)
    d = load_csv(path)
    check("the tracking file's objects and trial info load (and aren't regions)",
          file_objects(d) == objs and trial_info(d) == ("2", "Test") and d.regions == [])
    zpx, scaled = distance_px(d, 2.0)
    check("zone distance in px from the file's scale", scaled and zpx == 4.0)
    v = zone_visits(d, file_objects(d), zpx, 1.0)
    check("zone visits: first frame, last frame and length per object",
          [(x["object"], x["row"], x["end"], x["seconds"]) for x in v]
          == [("object 1", 11, 29, 19.0), ("object 2", 71, 89, 19.0)])
    # A 2-frame stay is kept; a 2-frame exit joins two stays (entry rule 3).
    df2 = df.copy()
    df2["X"] = [20.0 if i in (5, 6, 20, 21, 22, 25, 26) else 50.0 for i in range(n)]
    p2 = os.path.join(tmp, "m2_LocationOutput.csv"); df2.to_csv(p2, index=False)
    v2 = zone_visits(load_csv(p2), objs[:1], zpx, 1.0, min_frames=3)
    check("brief zone stays are never dropped; brief exits join visits",
          [(x["row"], x["end"]) for x in v2] == [(5, 6), (20, 26)])
    check("the object whose zone the point is in",
          object_at(d, objs, zpx, 15) == "object 1" and object_at(d, objs, zpx, 50) == ""
          and object_at(d, objs, zpx, 75) == "object 2")

    s = Scoring()
    s.add_bout("object 1", 15, 19)        # 5 s
    s.add_bout("object 2", 80, 74)        # given backwards: 74..80, 7 s
    s.add_bout("object 2", 85, 87)        # 3 s
    s.no_interaction.add(("object 1", 11))
    check("visit status: scored when an interaction overlaps it",
          s.visit_status(v[0]) == "scored" and s.visit_status(v[1]) == "scored")
    m = object_metrics(d, s, 1.0, zpx)
    check("time, bouts and latency per object",
          m["OR_Time_object 1_s"] == 5 and m["OR_Time_object 2_s"] == 10
          and m["OR_Bouts_object 1"] == 1 and m["OR_Bouts_object 2"] == 2
          and m["OR_Latency_object 1_s"] == 15 and m["OR_Latency_object 2_s"] == 74
          and m["OR_Latency_First_s"] == 15 and m["OR_Bouts_Total"] == 3)
    check("discrimination index and % preference are formulas of the shown times",
          m["OR_Total_s"] == 15 and m["OR_Novel_s"] == 10 and m["OR_Familiar_s"] == 5
          and m["OR_DiscriminationIndex"] == round((10 - 5) / 15, 3)
          and m["OR_PctPreference"] == round(100 * 10 / 15, 1))
    check("zone time and visits per object",
          m["OR_ZoneTime_object 1_s"] == 19 and m["OR_ZoneVisits_object 2"] == 1)
    b = object_metrics(d, s, 1.0, zpx, lo=78, hi=100)
    check("a bout counts for the part of it inside a time bin",
          b["OR_Time_object 2_s"] == 6 and b["OR_Bouts_object 2"] == 1)

    j = Scoring(); j.add_bout("object 1", 10, 20); j.add_bout("object 1", 18, 30)
    j.add_bout("object 1", 31, 33); j.add_bout("object 2", 15, 16)
    check("overlapping or touching bouts with the same object join (no frame twice)",
          [(x.object, x.start, x.end) for x in j.bouts]
          == [("object 1", 10, 33), ("object 2", 15, 16)])
    save_scoring(d, s, 1.0)
    check("scoring saved beside the tracking file",
          os.path.basename(scoring_path(d)) == "m1_ObjectScoring.csv"
          and os.path.exists(scoring_path(d)))
    back = load_scoring(d)
    check("scoring loads back the same",
          back.bouts == s.bouts and back.no_interaction == s.no_interaction)
    saved = pd.read_csv(scoring_path(d))
    check("scoring file shows frames 1-based with the video's own frame",
          saved.loc[0, "Start_Frame"] == 16 and saved.loc[0, "Start_VideoFrame"] == 315)

    t = trial_summary(d, s, 1.0, 2.0)
    check("summary: day, phase, novel object, visits not reviewed, zone distance",
          t["OR_Day"] == "2" and t["OR_Phase"] == "Test"
          and t["OR_NovelObjects"] == "object 2 (novel)"
          and t["OR_VisitsNotReviewed"] == 0 and t["OR_ZoneDistance"] == "2 cm")
    s2 = Scoring()
    t2 = trial_summary(d, s2, 1.0, 2.0)
    check("nothing scored: zero times, DI from zero total is blank",
          t2["OR_Total_s"] == 0 and math.isnan(t2["OR_DiscriminationIndex"])
          and t2["OR_VisitsNotReviewed"] == 2)

    # Editing the trial info after tracking changes only those columns.
    before = pd.read_csv(path, dtype=str, keep_default_na=False)
    update_trial_info(d, {"object 1": "Moved", "object 2": "Familiar", "nope": "Novel"}, " 5 ", "Training")
    after = pd.read_csv(path, dtype=str, keep_default_na=False)
    edited = ["Objects", "Trial_Day", "Trial_Phase"]
    check("editing trial info changes only those columns, exactly",
          after.drop(columns=edited).equals(before.drop(columns=edited))
          and list(after.columns) == list(before.columns))
    again = load_csv(path)
    check("edited types, day and phase are saved and show in memory too",
          [o.kind for o in file_objects(again)] == ["Moved", "Familiar"]
          and trial_info(again) == ("5", "Training") and trial_info(d) == ("5", "Training")
          and [o.kind for o in file_objects(d)] == ["Moved", "Familiar"]
          and [(o.x, o.y, o.r) for o in file_objects(again)] == [(20, 50, 5), (80, 50, 5)]
          and not os.path.exists(path + ".tmp"))
    check("edited types drive the results (moved counts as novel)",
          object_metrics(again, s, 1.0, zpx)["OR_Novel_s"] == 5)
    update_trial_info(d, {}, "", "Not a phase")
    check("a blank day and an unknown phase are written as blank",
          trial_info(load_csv(path)) == ("", ""))

    # --- scoring stays on the same moments of the video -------------------
    from core.objects import Scoring, unreadable_copy_path
    d = load_csv(path)                                   # Start_Frame 300
    sc = Scoring(); sc.add_bout("object 1", 15, 20); sc.no_interaction.add(("object 2", 71))
    save_scoring(d, sc, 1.0)
    table = pd.read_csv(scoring_path(d))
    check("the scoring file records the video's own frames",
          list(table["Start_VideoFrame"]) == [315, 371] and table["End_VideoFrame"][0] == 320)
    # The video is tracked again starting 10 frames later: rows shift by 10.
    later = df.iloc[10:].copy(); later["Frame"] = range(len(later)); later["Start_Frame"] = 310
    later.to_csv(path, index=False)
    d2 = load_csv(path)
    back = load_scoring(d2)
    check("after tracking again from a later start, scoring is still on the same video frames",
          [(b.object, b.start, b.end) for b in back.bouts] == [("object 1", 5, 10)]
          and back.no_interaction == {("object 2", 61)})
    # Tracked again from after the interaction: it's outside the file now.
    much = df.iloc[40:].copy(); much["Frame"] = range(len(much)); much["Start_Frame"] = 340
    much.to_csv(path, index=False)
    d3 = load_csv(path)
    out = load_scoring(d3)
    m3 = object_metrics(d3, out, 1.0, zpx)
    check("an interaction before the new start counts for nothing but isn't dropped",
          m3["OR_Time_object 1_s"] == 0 and m3["OR_Bouts_object 1"] == 0
          and [(b.start, b.end) for b in out.bouts] == [(-25, -20)])
    save_scoring(d3, out, 1.0)
    check("and saving keeps it on its video frames",
          pd.read_csv(scoring_path(d3))["Start_VideoFrame"][0] == 315)
    df.to_csv(path, index=False); d = load_csv(path)
    old = pd.read_csv(scoring_path(d)).drop(columns=["Start_VideoFrame", "End_VideoFrame"])
    old["Start_Frame"] = [16, 72]; old["End_Frame"] = [21, None]
    old.to_csv(scoring_path(d), index=False)
    check("a scoring file without video frames is read by its row numbers",
          [(b.start, b.end) for b in load_scoring(d).bouts] == [(15, 20)])

    # --- no-interaction marks survive a change of zone distance -----------
    sc = Scoring(); sc.no_interaction.add(("object 1", 11))      # the 2 cm visit starts at 11
    narrow = zone_visits(d, file_objects(d), zpx, 1.0)[0]
    wide = zone_visits(d, file_objects(d), distance_px(d, 4.0)[0], 1.0)[0]
    check("a wider zone starts the visit earlier", (narrow["row"], wide["row"]) == (11, 7))
    check("a visit marked no interaction stays marked when the zone distance changes",
          sc.visit_status(narrow) == "none" and sc.visit_status(wide) == "none")
    check("a mark for another object, or outside the visit, doesn't count",
          Scoring(no_interaction={("object 2", 11)}).visit_status(narrow) == ""
          and Scoring(no_interaction={("object 1", 40)}).visit_status(narrow) == "")

    # --- a scoring file that can't be read is never silently replaced -----
    semi = scoring_path(d)
    with open(semi, "w") as f:      # as a spreadsheet saves it with semicolons
        f.write("Type;Object;Start_Frame;End_Frame;Start_VideoFrame;End_VideoFrame\n"
                "Interaction;object 1;16;21;315;320\n")
    check("a scoring file saved with semicolons is read",
          [(b.start, b.end) for b in load_scoring(d).bouts] == [(15, 20)])
    with open(semi, "w") as f:
        f.write("Typ,Objekt,Von,Bis\nInteraktion,object 1,16,21\n")
    odd = load_scoring(d)
    check("a scoring file in another layout loads as empty and is marked unreadable",
          odd.unreadable and not odd.bouts)
    odd.add_bout("object 2", 72, 75)
    save_scoring(d, odd, 1.0)
    check("before new scoring replaces it, the unreadable file is copied aside",
          open(unreadable_copy_path(semi)).read().startswith("Typ,Objekt")
          and [(b.object, b.start) for b in load_scoring(d).bouts] == [("object 2", 72)]
          and not load_scoring(d).unreadable)

    # Training: every object familiar, so DI and % preference are blank.
    df["Objects"] = objects_to_text([TrialObject("object 1", 20, 50, 5),
                                     TrialObject("object 2", 80, 50, 5)])
    df.drop(columns=["Scale_cm_per_px"]).to_csv(path, index=False)
    d = load_csv(path)
    t = object_metrics(d, s, 1.0, distance_px(d, 2.0)[0])
    check("no novel object: DI and % preference blank; no scale: distance in px",
          math.isnan(t["OR_DiscriminationIndex"]) and math.isnan(t["OR_PctPreference"])
          and distance_px(d, 2.0) == (2.0, False))
finally:
    shutil.rmtree(tmp)

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
