# Track Tamer — Project Context

This file is auto-loaded when a Claude Code session starts in this folder. It is
the handoff brief so a fresh session continues the work with full context. The
detailed plan lives in [docs/ROADMAP.md](../docs/ROADMAP.md) — read it before building.

## Where files are (user, 2026-11-10)
The project folder shows only what a user needs: the six launchers
(`Open` / `Install` / `Uninstall Track Tamer` `.command` and `.bat`),
`README.md`, `INSTALL.md`, `TESTING.md` and `LICENSE`. **Keep it that way:
new program files go in `app/`, new documents in `docs/`**
(`app/tests/test_layout.py` checks). Everything else:
- `app/`: the program (`gui.py` and the other windows, `core/`, `tests/`,
  `requirements.txt`, `environment.yml`, `find_conda.sh` / `.bat`), plus,
  not in git, `config.json`, `.venv` and the `ezTrack/` reference copy.
  The launchers `cd` into `app` first, so paths inside them are as before.
- `docs/`: `ROADMAP.md`, `metadata_standard.md`.
- `.claude/CLAUDE.md`: this file.
- `Examples/` (not in git): the user's test videos, beside `app`.
File names below such as `core/...`, `gui.py` and `tests/...` are inside
`app/`. A `config.json` left in the project folder by an older version is
moved into `app/` the first time the app runs.

## What this is
A desktop app ("Track Tamer") that analyzes video-based rodent locomotion
tracking CSVs (`*_LocationOutput.csv`, one row per video frame) and produces
summary metrics, time-binned tables, path plots, and heatmaps. Supports
**Elevated Plus Maze (EPM)**, **Open Field** and **Object Recognition**, and
tracks videos itself (adapted from ezTrack).

## Hard constraints (from the user)
- **Do NOT compile/bundle the app (PyInstaller etc.) until explicitly told.**
  End goal is a standalone app, but we build & run from source for now.
- Keep the **`.command` launcher** that opens the GUI working.
- **Must run on both macOS and Windows PCs.** Avoid Mac-specific features
  entirely, using one portable approach on both. The user tests on a real PC, so
  give them a PC test checklist after cross-platform changes. See ROADMAP §10
  for at-risk pieces (launcher, dialog styling, DnD, fonts).
- **Never run `pip install --upgrade pip` in the venv** — it corrupted pip before
  and required a venv rebuild. Install deps straight from `requirements.txt`.
- **The install files name the exact package versions that were tested**
  (user, 2026-11-11, a rule for every app in the suite: "the install file
  should request and build the environment with version of the packages
  that have been tested. That is the whole point of having them install
  their own environments"). `environment.yml` and `requirements.txt` pin
  every package to one version, the same in both (the regression test
  checks, and checks the running environment has them). A release that
  needs new or newer packages changes the pins, and Install updates the
  **existing** environment to match (`conda env update --prune`); it never
  needs rebuilding from scratch. Never leave a package unpinned. Run the
  tests in both environments before changing a pin.

## Current state (what's built)
- `core/`: GUI-free engine. `loader.py` (read CSV, detect region columns),
  `metrics.py` (summary + time bins + summary column groups), `plotting.py`
  (path, heatmap, region map), `regions.py` (role mapping, per-frame roles,
  polygon matching, overlap check), `config.py` (`config.json`).
- `gui.py`: tkinter app. File list (Add File/Folder/drop, Clear, Analyze
  Selected/All). Test type, fps, and bin size lock at the first Analyze, and
  unlock at Clear. Path/Heatmap controls never lock. Summary
  (File, Status, checkbox column groups); the selected row drives the Time
  Bins / Path / Heatmap tabs (per-tab plot controls). Center/periphery overlap
  warning at Analyze.
- `tooltip.py`: portable hover tooltips.
- `dialogs.py`: **use this for every pop-up** (show_info/show_warning/
  show_error/ask_yes_no), never `tkinter.messagebox`. It renders the first
  sentence bold on both Mac and Windows, so write messages whose first
  sentence says what happened.
- `Open Track Tamer.bat`: Windows launcher (CRLF via `.gitattributes`).
- `core/export.py`: writes each analyzed file's `_analysis.xlsx` (Summary,
  Time Bins, Settings sheets), `_path.png`, and `_heatmap.png` next to its CSV.
- `region_dialog.py`: the Match regions dialog.
- **Saving (code review, 2026-11-10):** every file written beside the user's
  data goes through `core/safe_write.py` (`replacing`, `write_csv`): written
  whole under a temporary name, then put in place, so a failed or cancelled
  save never damages the earlier file. Never write a result file directly.
  The tracking file's `Crop` is recorded exactly (`tracking.crop_text`).
- **Object scoring** is placed by **video frame** (`Start_VideoFrame` in
  `_ObjectScoring.csv`), so it stays on the same moments when a video is
  tracked again from another start; "no interaction" marks belong to the
  visit that contains them (they survive a change of zone distance);
  scoring that can't be saved is kept in memory and used by the results
  (`core/objects.py`). The Review tab and scoring file use the analysis
  frame rate (the Frame rate box), as the results do.
- **Session length:** a video keeps the test's standard length until the
  user types one or sets the end (`VideoSetup.length_default`); a standard
  length follows the test type when it changes. An end placed with "Set end
  here" stays on its frame when the start moves (`end_placed`); an end past
  the test's session length asks first.
- **Decided 2026-11-11 (ROADMAP "Code review"):** time bins are cut true to
  the clock (`metrics._bin_ranges`); a reference image made from an older
  trim, crop, downsampling or frame count unticks setup steps 3 and 4
  (`VideoSetup.untick_stale_reference`); Track and Export stop and name files
  that would write the same result files; Export runs with a progress bar
  and Cancel; the Zone distance box applies once typing stops; a video save
  in progress is asked about before it's stopped; Cancel start (Esc) in
  object scoring.
- **Portable GUI helpers in `dialogs.py`:** `ask_choice` (several buttons;
  closing the window cancels: use it when neither answer is safe to
  assume), `bold_font` (never write `("TkDefaultFont", 11, "bold")`: that
  names a typeface that doesn't exist) and `fit_window` (window sizes that
  fit small screens). Errors nothing else catches are shown on screen
  (`report_callback_exception` in `gui.py`).
- **Tests:** run all of `app/tests/test_*.py` and `regress_gui.py` after
  changes, in both `app/.venv` and the `track-tamer` conda environment (the
  launcher uses the conda one). The practice video for the GUI tests is cut
  from the plus maze example (`tests/samples.py` `practice_clip`; ezTrack's
  practice videos are gone, user 2026-11-10). `test_saving.py`,
  `test_edge_cases.py` and `test_gui_fixes.py` hold one check per bug fixed
  in the 2026-11-10 review; ROADMAP "Code review (2026-11-10)" lists what
  was fixed and what was left for the user to decide.
- `tests/regress_gui.py`: workflow regression test. Run it after GUI changes
  (`app/.venv/bin/python app/tests/regress_gui.py`); it needs the Examples files.
- **Jumping to a video frame:** never use `cap.set(cv2.CAP_PROP_POS_FRAMES)`
  for a frame that must match tracking. The camera videos have uneven frame
  timing, so OpenCV's jump lands a frame off in places. Use
  `VideoReader.read_at` / `core.video.grab_frame` (checked against the
  frames' own timestamps, `frame_times`), and `FrameSource` for a tracking
  file's rows. Tracking starts on exactly the start frame chosen in setup
  (`VideoReader.frames`; user, 2026-11-10), so row r is frame start + r.
  Files tracked before that with a start after 0 may be a frame off and
  should be re-tracked (the Open Field example is one). Only the reference
  image keeps OpenCV's own jump (`read_near`). `tests/test_seek.py` checks it.
  A damaged video's timestamp list stops at the damage; a list much shorter
  than the file's frame count is not used (2026-11-11), or tracking would
  silently stop there. Tracking reports frames it couldn't read at the end
  of a session (`TrackResult.missing_at_end`) and the app warns about them.
- **Anaconda install (ROADMAP §14, built 2026-11-03):** `environment.yml`
  (env `track-tamer`, conda-forge only; `tkinterdnd2` via its `pip:`
  section), `find_conda.sh` / `find_conda.bat` (shared conda finders),
  `Install` / `Uninstall Track Tamer` `.command` / `.bat`. The `Open`
  launchers use the conda env when installed (Windows activates it first),
  note when `environment.yml` changed since install (stamp copy inside the
  env), and fall back to `.venv` without Anaconda. Keep `requirements.txt`
  and `environment.yml` in step (the regression test checks). `.sh` and
  `.command` are LF via `.gitattributes`.
- `Open Track Tamer.command`: Mac double-click launcher.
- Project folder: `/Volumes/AI Files/Track Tamer` (moved there by the user
  2026-11-07; before that `Desktop/Tracker Tamer`, originally `EZanalyze`).
  The path has spaces, so always quote it.
- Git repo pushed to GitHub `vtbrak/TrackTamer` (**public**, GPL-3.0; renamed from
  `EZAnalyze` 2026-11-05, and the old URL redirects). `*.csv`,
  `config.json`, and export outputs (`*_analysis.xlsx`, `*_path.png`,
  `*_heatmap.png`) are gitignored.

## Locked design decisions
- **Trust the file's own region columns** (one True/False column per region)
  rather than recomputing zones from X/Y. The exception is open-field sides,
  which files don't have, so they come from X/Y judged against **that file's
  own drawn center-ROI lines** (as drawn, tilt and all; never straightened).
- **Each file has its own ROI lines; always analyze a file against its own.**
  Never share or cache ROI geometry between files. Only the region-name → role
  mapping is shared.
- **Region names and order vary between files**, so there's a **region-role
  mapping**: auto-classified by keyword or code (EPM `ol/or`→open, `ct/cb`→
  closed, `mid`→center), user-overridable, **saved**. Unrecognized names
  prompt the user with a dropdown.
- **Overlaps count as center** (EPM arm+mid), and **a shared border point
  counts for the center only** (user, 2026-11-05): one region per frame
  (`core/regions.py` `frame_regions`) drives every per-region, per-role and
  per-bin number, so the same quantity is never two different numbers;
  tracking writes non-center regions minus the center; no ROI-label
  (`Time_ROI_*`) columns. Only the center may share; other shared frames are
  reported (`SharedRegionFrames`, Analyze warning).
- **Frames outside every drawn region still count** (user, 2026-11-05):
  Open Field = periphery (anything not center); EPM = nearest region (head
  dips count for that arm). Stretches outside are listed in the **Review tab**
  and flagged at a per-test cutoff (config `review_cutoff_s`, OF 1 s / EPM
  5 s) as "tracker may be lost". The Review tab (list + "Open playback
  window"; a row click opens the window at that frame) replaced the Play
  video… buttons; the video plays in its own window (in-tab was too cramped,
  and a window suits future manual scoring such as object recognition). **Center/periphery must never
  overlap**: that's a file error, so warn the user.
- **Test type** chosen via a **dropdown** (EPM / Open Field); no auto-detect.
- **All thresholds** are **input boxes in the UI, persisted to `config.json`**.

## Resolved analysis specs (see ROADMAP §4–§5 for full detail)
- **Entry rule**: counts only after the point stays inside a region ≥ N frames (saved).
- **EPM**: open vs closed arm time; report %open time, %open entries, composite
  Anxiety Index, AND closed/open time ratio; latency to first entry; time in
  center; arm entry counts.
- **Immobility: deferred** (user, 2026-10-29: don't calculate it for this data
  for now). Spec and jitter findings are kept in ROADMAP §11 for later.
- **Open field**: center entries (min-frames + min time-between-entries); time/% in
  center; latency; **crossings** across center — opposite sides (L↔R, T↔B) and
  adjoining sides (counted only if ≥ min time in center between sides); **crossing
  speed** reported as both average and peak.

## Build order and progress
Steps 1–3, ROADMAP §7 (file-input workflow), and the §10 groundwork (shared
dialogs + Windows launcher), §8 display fixes, and EPM and open-field metrics (§4–§5)
and §9 export are done. Immobility is deferred (ROADMAP §11). Everything in
the current build order is built; next steps come from the user (and the
first PC test when they're ready). **ROADMAP "Build order" is
the source of truth.**
**What to build next:** see "Priority order for what's next" in ROADMAP
"Build order" (user, 2026-11-09). Nothing on it starts until the user asks.
**Version 0.9.3** (2026-11-12; 0.9.2 was 2026-11-09, 0.9 was 2026-11-05, the testing release; user chose 0.x): `core/version.py`
holds `VERSION` (About window, exported Settings sheet); git tags `v0.9`, `v0.9.1`, `v0.9.2`, `v0.9.3`
(GitHub pre-release). Fixes from testers go out as 0.9.1, 0.9.2, …; 1.0 comes
after testing. Bump `VERSION` and tag for each release.
**Every GitHub release is tagged** (user, 2026-11-12: "make sure that all
github releases are tagged starting with this one"): bump `VERSION`, commit,
make an annotated tag `v<VERSION>` on that commit, push the commit and the
tag, and only then create the release from that tag (API `tag_name`
`v<VERSION>`, never a branch name). Check afterwards that the release's tag
is on GitHub (`git ls-remote --tags origin`). v0.9, v0.9.1 and v0.9.2 were
checked on 2026-11-12: each release has its annotated tag.
**`video-tracking` was merged into `main` on 2026-11-05** (fast-forward) for
the user's first outside testers; work continues on `main`, and the
`video-tracking` branch was deleted (local and GitHub) the same day. Tester guide:
`TESTING.md` (keep it in step with the UI).
**Video analysis (ROADMAP §12) was built on the `video-tracking` branch**
(started 2026-10-30): adapting ezTrack (GPL-3.0, github.com/denisecailab/ezTrack;
local reference copy in `ezTrack/`, gitignored) for location tracking (freeze
analysis is logged for later; it will use ezTrack's thresholds instead of the
planned immobility). **Walkthrough of ezTrack's functions with the user, stage by
stage** (Location Tracking: load/crop → reference → tracking → ROIs → scale →
summaries/playback → batch; then Freeze Analysis), deciding keep / drop /
change for each. **Location Tracking Stages 1–7 are decided (ROADMAP
§12). Freeze Analysis decisions are logged but EXCLUDED from the current
build (Location Tracking first). The GUI review is decided (ROADMAP §12, end):
settings panel, always-visible file list, Track / Analyze / Export acting on
the selected files with a Select all button, one video setup window.
**Video build (ROADMAP §12, "Video build progress" checklist):**
C0–C9 (with C5b) done: **Location Tracking is complete**. Next steps come from the user (PC test with ROADMAP §10's video checklist, then Freeze Analysis / ASR when asked). Each chunk is committed and pushed when done.
**Object recognition (ROADMAP §15) is built** (2026-11-05, on
`video-tracking`, O1–O4): test type "Object Recognition"; setup step 5
"Objects" (circles, Familiar/Novel/Moved, day, phase); Zone distance box
(never locks); Review tab lists zone visits; scoring in the playback window
(`<name>_ObjectScoring.csv`); results `OR_*` (`core/objects.py`). Object
types, day and phase can be edited after tracking (Review tab, `update_trial_info`
rewrites only those columns of the tracking file). Tested on
the user's object trial `Examples/1_2026-06-26_14-03-15.mp4`
(`tests/test_objects_video.py`).
**Anaconda install (ROADMAP §14) is built** (2026-11-03, on `main`, merged
here); tested on Mac, PC test pending.
**Video metadata standard (ROADMAP §16):** `docs/metadata_standard.md`. Track
Tamer is the **master** for metadata: every app that records video for it
(first: the user's Creature Capture) writes `<date>_<time>_<arena>_info.json`
per this standard, with `assay` from its fixed list. The user adds other
apps' pieces over time (an "Apps" section per app).
**Reading it was moved up by the user on 2026-11-11 and is being built on
`main`** (ROADMAP §16, "One file per video"). The design the user chose:
- **One JSON per video, which Track Tamer adds to**: its own `track_tamer`
  object inside the video's `cameras` entry (test, setup, tracking settings,
  analysis settings, its file names). Never change what the recording app
  wrote; a video with no info file gets `<name>_info.json`.
  `core/info_file.py` is the file on disk; `core/info.py` what it means.
- **The tracking file is slim** (`_LocationOutput.csv` and startle's
  `_MotionIndex.csv`): only per-frame columns on disk. Everything
  it used to repeat on every row is in the info file, and
  `loader.load_csv` / `asr.load_motion` put it back in memory. Startle's
  stimuli aren't copied (read from the info file's `stimuli`, or the typed
  frames kept there). What varies per stimulus (dB etc.) stays on every row
  of the Trials table. Never write settings into the
  tracking file again; older files that hold their own still load.
- **A video added again comes back with its setup and tracking file**
  (`VideoSetup.to_saved` / `restore`, `gui._restore_setup`).
- **Where the info file and the setup disagree, the experimenter chooses**
  in a side-by-side window (`dialogs.ask_side_by_side`); the same window
  offers a returning video's saved tracking settings. The setup is saved
  when the setup window closes as well as at Track (`gui._save_setup`).
- **Videos with no info file** are asked about when added
  (`info_dialog.show_missing_info`): choose an info file (picker opens in
  the video's folder; copied into the video's own file, `info_file.adopt`)
  or type the animal's information (`info_dialog.ask_animal`,
  `info_file.write_fields`, `app_name` "Track Tamer"). Done gives each one
  an info file. **GUI tests must stub `gui.show_missing_info`,
  `gui.ask_side_by_side` and `gui.ask_animal`**, or a real window opens on
  the user's screen and waits (that happened on 2026-11-11).
- **Repeated frames** (the recording app wrote the frame before again):
  marked per frame (`Frame_Repeated`), counted, speed worked out across
  them (`metrics.spread_repeats`), and flagged above `repeated_warn_pct`.
  Never treat them as unreadable: their positions are right to a frame.
- **Workbook sheets:** Experiment (animal and task, down the page), Summary
  (File, `animal_id`, measures: no tracking settings, no other animal
  columns), Time Bins, Settings, Setup. Each video keeps its own files (no
  combined table).
- **The same words in every app**: the standard's field names. No `room` or
  `app_name` columns. The capture apps keep a running log (24 fixed
  columns) and no per-trial `_info.csv`.
- **Puzzle Box** and conditioned place preference are **after 1.0** (user,
  2026-11-11; Puzzle Box's measures are decided, ROADMAP "Build order").
**Nose and rear end (ROADMAP §17) is built on the `head-tail` branch only**
(2026-11-10; not in `main`, not released): `core/pose.py`; tracking writes
`Nose_X`, `Nose_Y`, `Rear_X`, `Rear_Y` beside X and Y (the center, unchanged);
the playback window and saved video show nose (red), center (yellow), rear
end (blue). The points are "nose", "center", "rear end" (the tail is not
reported). **Only x, y for now; measures come later (user).** Good in open
arenas, still weak on the plus maze (ROADMAP §17 has the trial numbers).
Tests: `tests/test_pose.py`.
**Startle by sound level is built** (2026-11-11; ROADMAP §13): for sessions
whose pulse-alone trials step through levels, the mean per level, a startle
threshold (lowest level from which it and every louder one beat the
baseline windows + `asr_threshold_sd` SD) and the largest response, per
sound when there are several, and the Startle by Level plot
(`_levels.png`). **Habituation is waiting on more calculations from the
user; don't change it until they send them.**
**Acoustic startle (ROADMAP §13) is built** (2026-11-09, on `main`, not released;
the target for 1.0): test type "Acoustic Startle Response", `core/asr.py`, setup steps
Threshold and Stimuli, `<name>_MotionIndex.csv`. Waiting on real chamber videos to
validate. The user cites papers outside the app (no in-app citation for ASR). Freeze Analysis
decisions are recorded only; **don't build it until the user says so.** Adapted ezTrack code (core/video.py, tracking.py, playback.py) keeps the
GPL-3.0 license and credits ezTrack at the top of each file; keep doing so.
Video-side modules: `core/video_setup.py`, `core/track_run.py`,
`setup_window.py`, `review_panel.py` (Review tab; see README Layout).
**Test data = the `Examples/` folder** (gitignored; user, 2026-11-05): real
videos tracked in this app with their tracking files (EPM
`6_2024-04-01_11-49-23`, Open Field `1_2026-08-17_13-27-03`) and the object
trial video. Paths live in `tests/samples.py`; every test uses them. The old
`EPM.csv` / `Open Field.csv` samples are gone (ROADMAP "Sample data findings"
describes them).

## How to run
```bash
cd "/Volumes/AI Files/Track Tamer/app" && ./.venv/bin/python gui.py
```
Or double-click `Open Track Tamer.command`.
