# Track Tamer — Project Context

This file is auto-loaded when a Claude Code session starts in this folder. It is
the handoff brief so a fresh session continues the work with full context. The
detailed plan lives in [ROADMAP.md](ROADMAP.md) — read it before building.

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
- `tests/regress_gui.py`: workflow regression test. Run it after GUI changes
  (`.venv/bin/python tests/regress_gui.py`); it needs the Examples files.
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
**Version 0.9.2** (2026-11-09; 0.9 was 2026-11-05, the testing release; user chose 0.x): `core/version.py`
holds `VERSION` (About window, exported Settings sheet); git tags `v0.9`, `v0.9.1`, `v0.9.2`
(GitHub pre-release). Fixes from testers go out as 0.9.1, 0.9.2, …; 1.0 comes
after testing. Bump `VERSION` and tag for each release.
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
apps' pieces over time (an "Apps" section per app). Reading it in Track Tamer
is planned for after 1.0; don't build before 1.0.
**Acoustic startle (ASR) from video** is planned in ROADMAP §13 (motion
index with an adjustable 0–255 intensity threshold, default 15; PPI and
habituation); not built. **When ASR work starts, first remind the user to put
a sample ASR video and its stimulus logs in the project folder.** The user
cites papers outside the app (no in-app citation for ASR). Freeze Analysis
and ASR decisions are recorded only; **don't build them until the user says
so.** Adapted ezTrack code (core/video.py, tracking.py, playback.py) keeps the
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
cd "/Volumes/AI Files/Track Tamer" && ./.venv/bin/python gui.py
```
Or double-click `Open Track Tamer.command`.
