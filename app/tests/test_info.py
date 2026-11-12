"""Reading the recording apps' trial information (ROADMAP §16,
docs/metadata_standard.md): finding a video's info file, what it gives the
Summary and the Settings sheet, the problems it reports, and where it and a
video's setup disagree.

Run from the project folder:  .venv/bin/python tests/test_info.py
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import info_file
from core.info import (TrialInfo, apply_choice, differences, fill_blanks, find_info,
                       info_for_output, with_animal)
from core.video import VideoInfo
from core.video_setup import VideoSetup

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)


def setup(length_s=300.0):
    return VideoSetup(path="v.mp4", info=VideoInfo("v.mp4", 6000, 20.0, 800, 600),
                      length_s=length_s)


FULL = {
    "schema_version": 1, "app_name": "Creature Capture", "app_version": "0.2.0",
    "date": "2026-11-05", "start_time": "16:56:42", "assay": "Open Field", "arena": "OF2",
    "animal_id": "M7", "sex": "F", "strain": "C57", "dob": "2026-09-01",
    "treatment": "saline", "cohort": "A", "experimenter": "ES", "trial_day": 1,
    "session_number": 2, "duration_set_min": 60, "duration_actual_s": 3600.0,
    "stopped_early": False,
    "cameras": [
        {"label": "Side", "camera_position": "Camera2", "camera_settings": {},
         "video": "2026-11-05_16-56-42_OF2_Side.mp4"},
        {"label": "Overhead", "camera_position": "Camera5",
         "camera_settings": {"encoder": "libx264", "exposure": {"apply": True, "value": -5}},
         "video": "2026-11-05_16-56-42_OF2_Overhead.mp4",
         "timestamps_csv": "2026-11-05_16-56-42_OF2_Overhead_frames.csv",
         "fps_set": 20, "fps_measured": 20.0, "frames": 72000,
         "verified_frames_in_file": 72000, "repeated_frames": 4,
         "repeated_frame_indices": [5, 9, 100, 2000]},
    ],
    "creature_capture": {"experiment": "Open Field 60 min", "gpu": False},
}

tmp = tempfile.mkdtemp()
try:
    def write(name, contents):
        with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
            f.write(contents if isinstance(contents, str) else json.dumps(contents))
    write("2026-11-05_16-56-42_OF2_info.json", FULL)
    write("2026-11-05_17-30-00_EPM1_info.json", "{ not json")
    write("2026-11-05_18-00-00_OF1_info.json", ["a list, not an info file"])
    video = os.path.join(tmp, "2026-11-05_16-56-42_OF2_Overhead.mp4")

    info = find_info(video)
    check("a video finds the info file that lists its exact name, and its own camera",
          info is not None and not info.renamed and info.camera["label"] == "Overhead"
          and info.path.endswith("OF2_info.json"))
    check("files that aren't readable info files are passed over",
          find_info(os.path.join(tmp, "2026-11-05_17-30-00_EPM1_Overhead.mp4")) is None)
    check("a video with no info file has none", find_info(os.path.join(tmp, "other.mp4")) is None)
    renamed = find_info(os.path.join(tmp, "2026-11-05_16-56-42_OF2_Overhead copy.mp4"))
    check("a renamed video matches by the start of its name, marked as renamed",
          renamed is not None and renamed.renamed and renamed.camera == {})
    one = find_info(os.path.join(tmp, "2026-11-05_16-56-42_OF2_side.avi"))
    check("a renamed video's camera is the one whose label is in the name",
          one is not None and one.renamed and one.camera.get("label") == "Side")
    by_name = find_info(os.path.join(tmp, "x_LocationOutput.csv"),
                        name="2026-11-05_16-56-42_OF2_Overhead.mp4")
    check("a tracking file finds its video's info file by the video's name",
          by_name is not None and by_name.camera["label"] == "Overhead")

    check("the assay sets the test type", info.test == "Open Field" and info.arena == "OF2")
    check("matching ignores case and spaces at the ends",
          TrialInfo({"assay": "  elevated PLUS maze "}).test == "Elevated Plus Maze")
    check("an assay Track Tamer doesn't analyze gives no test type",
          TrialInfo({"assay": "Puzzle Box"}).test is None
          and TrialInfo({"assay": "Elevated Plus"}).test is None and TrialInfo({}).test is None)
    row = with_animal({"File": "v", "Frames": 10}, info)
    check("the Summary row carries the animal's ID right after File, and the camera's "
          "repeated-frame count",
          list(row) == ["File", "animal_id", "Frames", "RepeatedFrames"]
          and row["animal_id"] == "M7" and row["RepeatedFrames"] == 4)
    check("no info file: the ID column is there, blank",
          with_animal({"File": "v"}, None) == {"File": "v", "animal_id": ""})
    page = info.experiment_sections()
    check("the Experiment sheet lists the animal and the task, with the age on the test day",
          list(page) == ["Animal", "Task"] and page["Animal"]["Animal ID"] == "M7"
          and page["Animal"]["Age (days)"] == 65 and page["Animal"]["Treatment / group"] == "saline"
          and page["Task"]["Assay"] == "Open Field" and page["Task"]["Length set (min)"] == "60"
          and page["Task"]["Stopped early"] == "no" and page["Task"]["Session that day"] == "2")
    blank = TrialInfo({}).experiment_sections()
    check("every field is listed for every file, blank when nothing was recorded",
          {k: list(v) for k, v in blank.items()} == {k: list(v) for k, v in page.items()}
          and set(blank["Animal"].values()) == {""} and set(blank["Task"].values()) == {""}
          and page["Task"]["Phase"] == "")
    check("a file a recording app wrote is told from one Track Tamer made",
          info.recorded and not TrialInfo({"schema_version": 1}).recorded)

    # An older file: blanks instead of missing fields, numbers and yes/no as text.
    old = TrialInfo({"assay": "Elevated Plus", "animal_id": "human 1", "sex": "", "dob": "",
                     "trial_day": "", "duration_set_min": "5", "duration_actual_s": "57.50",
                     "stopped_early": "yes"},
                    {"frames": 1150, "verified_frames_in_file": 1150, "repeated_frames": 3,
                     "error": ""})
    check("an older file reads: blanks left out, numbers read from text",
          old.animal_id == "human 1" and old.experiment_sections()["Animal"]["Sex"] == ""
          and old.session_minutes == 5
          and old.repeated_frames == 3)
    check("stopped early is reported with how long it ran",
          old.problems(session_s=300) == ["the recording was stopped early (after 57.5 s)"])
    check("a clean recording reports nothing",
          info.problems(video_frames=72000, video_fps=20.0, session_s=3600) == [])
    bad = TrialInfo({"schema_version": 2, "duration_actual_s": 100},
                    {"error": "Encoder stopped", "frames": 500, "verified_frames_in_file": 480,
                     "fps_measured": 9.84})
    said = " | ".join(bad.problems(video_frames=480, video_fps=20.0, session_s=300))
    check("problems: newer standard, short recording, app error, frame counts, frame rate",
          all(x in said for x in ("newer version", "shorter than the session", "Encoder stopped",
                                  "wrote 500 frames but counted 480", "9.84 fps")))
    check("a frame size that isn't the video's is reported; the right one isn't",
          "800 x 600 px, the video's are 640 x 480"
          in " ".join(TrialInfo({}, {"width_px": 800, "height_px": 600}).problems(video_size=(640, 480)))
          and TrialInfo({}, {"width_px": 800, "height_px": 600}).problems(video_size=(800, 600)) == [])
    check("the video's own frame count is checked when the app didn't verify it",
          "the video has 480" in " ".join(TrialInfo({}, {"frames": 500}).problems(video_frames=480)))

    sections = info.settings_sections()
    check("Settings sheet: where it came from, the camera, and the app's own fields",
          sections["Recording"]["Recording app"] == "Creature Capture"
          and sections["Recording"]["Info file"] == "2026-11-05_16-56-42_OF2_info.json"
          and sections["Camera"]["Camera position"] == "Camera5"
          and sections["Camera"]["Setting: encoder"] == "libx264"
          and sections["Camera"]["Setting: exposure"] == '{"apply": true, "value": -5}'
          and sections["App fields (creature_capture)"] == {"experiment": "Open Field 60 min",
                                                            "gpu": False})
    long = TrialInfo({"boom_box": {"protocol_name": "I/O", "trials": [{"n": i} for i in range(200)]},
                      "stimuli": [{"frame": i} for i in range(200)]}, {"label": "Side"})
    check("a long app field is noted, not copied",
          long.settings_sections()["App fields (boom_box)"]["trials"] == "(long: see the info file)")

    # Track Tamer adds its own part to the same file, and nothing else changes.
    before = info_file.read(info.path)
    path = info_file.write(video, {"test": "Open Field", "setup": {"start_frame": 12},
                                   "files": {"tracking": "2026-11-05_16-56-42_OF2_Overhead_LocationOutput.csv"}})
    after = info_file.read(path)
    again = find_info(video)
    check("Track Tamer's part goes in the video's own camera entry of the same file",
          path == info.path and again.saved["test"] == "Open Field"
          and again.saved["setup"] == {"start_frame": 12}
          and "track_tamer" not in after["cameras"][0])
    after["cameras"][1].pop("track_tamer")
    check("nothing the recording app wrote is changed", after == before)
    info_file.write(video, {"analysis": {"Test": "Open Field"}, "files": {"analysis": "a.xlsx"}})
    again = find_info(video)
    check("a later save adds to it: other parts stay, file names add up",
          again.saved["setup"] == {"start_frame": 12} and again.saved["analysis"]["Test"] == "Open Field"
          and again.saved["files"] == {"tracking": "2026-11-05_16-56-42_OF2_Overhead_LocationOutput.csv",
                                       "analysis": "a.xlsx"})
    found = info_for_output(os.path.join(tmp, "2026-11-05_16-56-42_OF2_Overhead_LocationOutput.csv"))
    check("a tracking file finds its video's entry in the info file",
          found is not None and found.camera["label"] == "Overhead" and found.animal_id == "M7")
    lone = os.path.join(tmp, "old video.mp4")
    made = info_file.write(lone, {"test": "Elevated Plus Maze", "setup": {"start_frame": 3}})
    mine = find_info(lone)
    check("a video with no info file gets one, in the same layout",
          os.path.basename(made) == "old video_info.json" and mine is not None
          and not mine.renamed and mine.saved["setup"] == {"start_frame": 3}
          and not mine.recorded and mine.test is None)
    info_file.write(lone, {"tracking": {"Method": "dark", "ROI_coordinates": {"xs": [[1.0]], "ys": [[2.0]]}},
                           "files": {"tracking": "old video_LocationOutput.csv"}})
    columns = info_file.saved_columns(os.path.join(tmp, "old video_LocationOutput.csv"))
    check("the columns a slim tracking file leaves to the info file come back, with the video's name",
          columns == {"Method": "dark", "ROI_coordinates": "{'xs': [[1.0]], 'ys': [[2.0]]}",
                      "File": "old video.mp4"})
    check("a tracking file with nothing saved for it has none",
          info_file.saved_columns(os.path.join(tmp, "nobody_LocationOutput.csv")) == {})

    # Where the setup and the info file disagree.
    s = setup(300.0)
    d = differences(info, "Elevated Plus Maze", s)
    check("test type and session length that differ are listed side by side",
          [(x.what, x.setup_value, x.info_value) for x in d]
          == [("test", "Elevated Plus Maze", "Open Field"), ("length", "5 min", "60 min")])
    check("nothing listed when they agree", differences(info, "Open Field", setup(3600.0)) == [])
    check("without a setup only the test type is compared",
          [x.what for x in differences(info, "Elevated Plus Maze")] == ["test"])
    check("an assay Track Tamer doesn't analyze isn't a test-type difference",
          differences(TrialInfo({"assay": "Puzzle Box"}), "Open Field", setup()) == [])
    check("startle takes the whole video: its length isn't compared",
          differences(TrialInfo({"assay": "Acoustic Startle Response", "duration_set_min": 30}),
                      "Acoustic Startle Response", setup(600.0)) == [])
    apply_choice(info, s, "length")
    check("choosing the info file's length sets it as a chosen length",
          s.length_s == 3600 and s.length_default == "" and s.end_placed is None)

    obj = TrialInfo({"assay": "Object Recognition", "trial_day": 2, "phase": "test",
                     "objects": [{"name": "object 1", "kind": "familiar", "identity": "glass bottle",
                                  "position": "top left"},
                                 {"name": "object 2", "kind": "Novel", "identity": "lego tower"},
                                 {"name": "object 9", "kind": "Moved"}, "junk",
                                 {"name": "object 3", "kind": "strange"}]})
    check("object types and what each object is, for the names and kinds Track Tamer knows",
          obj.object_kinds == {"object 1": "Familiar", "object 2": "Novel", "object 9": "Moved"}
          and obj.object_identities == {"object 1": "glass bottle (top left)",
                                        "object 2": "lego tower"}
          and obj.phase == "Test" and obj.trial_day == "2")
    s = setup(600.0)
    fill_blanks(obj, s)
    check("a blank day and phase are filled in, not listed as differences",
          (s.trial_day, s.trial_phase) == ("2", "Test"))
    d = differences(obj, "Object Recognition", s)
    check("object types that differ are one row, for the objects both have",
          [(x.what, x.setup_value, x.info_value) for x in d]
          == [("kinds", "object 1: Familiar, object 2: Familiar",
               "object 1: Familiar, object 2: Novel")])
    apply_choice(obj, s, "kinds")
    check("choosing the info file's types sets them (an object Track Tamer doesn't have is skipped)",
          s.object_kinds == {"object 1": "Familiar", "object 2": "Novel"}
          and differences(obj, "Object Recognition", s) == [])
    s.trial_day, s.trial_phase = "3", "Training"
    d = differences(obj, "Object Recognition", s)
    check("a day and phase already set that differ are listed",
          [(x.what, x.setup_value, x.info_value) for x in d]
          == [("day", "3", "2"), ("phase", "Training", "Test")])
    apply_choice(obj, s, "day"); apply_choice(obj, s, "phase")
    check("and can be taken from the info file", (s.trial_day, s.trial_phase) == ("2", "Test"))

    # A draft setup from the last video tracked in the same arena.
    from core.info import arena_draft
    rig = os.path.join(tmp, "rig")
    def trial(day, stamp, arena, label, saved_at, size=(800, 600), crop=(10.0, 20.0, 300.0, 400.0)):
        folder = os.path.join(rig, day); os.makedirs(folder, exist_ok=True)
        name = f"{stamp}_{arena}_{label}.mp4"
        camera = {"label": label, "video": name}
        if saved_at:
            camera["track_tamer"] = {"saved": saved_at, "setup": {
                "frame_size": list(size), "start_frame": 40, "length_s": 77.0, "crop": list(crop),
                "regions": {"center": {"xs": [1.0, 2.0, 3.0], "ys": [4.0, 5.0, 6.0]}},
                "exclusions": [{"xs": [7.0, 8.0, 9.0], "ys": [1.0, 2.0, 3.0]}],
                "scale_points": [[0.0, 0.0], [100.0, 0.0]], "scale_cm": 40.0,
                "object_kinds": {"object 1": "Novel"}, "trial_day": "9"}}
        with open(os.path.join(folder, f"{stamp}_{arena}_info.json"), "w") as f:
            json.dump({"schema_version": 1, "assay": "Open Field", "arena": arena,
                       "animal_id": "M1", "cameras": [camera]}, f)
        return os.path.join(folder, name)
    trial("2026-11-10", "2026-11-10_09-00-00", "OF2", "Overhead", "2026-11-10 10:00:00")
    trial("2026-11-11", "2026-11-11_09-00-00", "OF2", "Overhead", "2026-11-11 10:00:00",
          crop=(11.0, 22.0, 333.0, 444.0))
    trial("2026-11-11", "2026-11-11_09-30-00", "OF1", "Overhead", "2026-11-11 11:00:00")
    trial("2026-11-11", "2026-11-11_10-00-00", "OF2", "Side", "2026-11-11 12:00:00")
    trial("2026-11-11", "2026-11-11_10-30-00", "OF2", "Overhead", "2026-11-11 13:00:00",
          size=(640, 480))
    new_video = trial("2026-11-12", "2026-11-12_09-00-00", "OF2", "Overhead", None)
    new_info = find_info(new_video)
    got = arena_draft(new_info, new_video, (800, 600))
    check("the draft is the most recently saved setup for the same arena, camera and frame size, "
          "from the day folders beside the video's",
          got is not None and got[0]["crop"] == [11.0, 22.0, 333.0, 444.0]
          and got[1] == "2026-11-11_09-00-00_OF2_Overhead.mp4")
    check("no draft for an arena or frame size nothing was saved for",
          arena_draft(TrialInfo({"arena": "OF9"}, {"label": "Overhead"}), new_video, (800, 600)) is None
          and arena_draft(new_info, new_video, (1280, 720)) is None
          and arena_draft(TrialInfo({}, {}), new_video, (800, 600)) is None)
    fresh = VideoSetup(path=new_video, info=VideoInfo(new_video, 6000, 20.0, 800, 600),
                       length_s=300.0, length_default="Open Field")
    took = fresh.draft_from(got[0])
    check("a draft brings the crop, shapes, regions and scale, and ticks nothing",
          took and fresh.crop == (11.0, 22.0, 333.0, 444.0) and list(fresh.regions) == ["center"]
          and len(fresh.exclusions) == 1 and fresh.scale_cm == 40.0
          and fresh.scale_points == [(0.0, 0.0), (100.0, 0.0)] and fresh.steps_done == set())
    check("the session, object types and trial details stay this video's own",
          (fresh.start, fresh.length_s, fresh.length_default) == (0, 300.0, "Open Field")
          and fresh.object_kinds == {} and fresh.trial_day == "")
    other_size = VideoSetup(path="v.mp4", info=VideoInfo("v.mp4", 6000, 20.0, 640, 480))
    check("nothing is taken from a setup drawn on another frame size",
          not other_size.draft_from(got[0]) and other_size.crop is None and not other_size.regions)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
