# Track Tamer

**Version 0.9.2** (November 2026): the testing release. See
[TESTING.md](TESTING.md) to try it.

Tracks a rodent's position in **videos** of an Elevated Plus Maze or Open
Field, and analyzes location tracking CSVs (`*_LocationOutput.csv`: one row per
video frame with position, region, and distance data, from this program or
from ezTrack), turning them into summary metrics, time-binned tables, path
plots, and occupancy heatmaps.

## Installing and running

For a step-by-step guide written for non-programmers, including a method
that needs no administrator password, see **[INSTALL.md](INSTALL.md)**.
Testers: **[TESTING.md](TESTING.md)** covers installing, what to try, and
how to report problems.

### With Anaconda (recommended, Mac or Windows)
1. Install [Anaconda or Miniconda](https://www.anaconda.com/download) if the
   computer doesn't have it.
2. Get the program folder: download the zip from GitHub (or `git clone`).
   The repository is public: github.com/vtbrak/TrackTamer. If you
   copy the folder from another computer, leave out `app/.venv`, if it has
   one.
3. Double-click **`Install Track Tamer.command`** (Mac) or
   **`Install Track Tamer.bat`** (Windows). It finds Anaconda, builds the
   program's own environment (`track-tamer`, from `app/environment.yml`,
   using the free conda-forge channel), and says Done or Failed. It only needs
   doing once; run it again after an update to bring the environment up to
   date.
4. From then on, double-click **`Open Track Tamer.command`** (Mac) or
   **`Open Track Tamer.bat`** (Windows). If the program's package list has
   changed since you installed, it says so; run the installer again.

**First time on a Mac:** macOS may block a downloaded script. Right-click the
file → **Open** → **Open**; after that, double-clicking works.
**On Windows:** if SmartScreen warns about the file, click **More info** →
**Run anyway**. A console window stays open while the app runs and shows any
error messages.

**Uninstall:** `Uninstall Track Tamer.command` / `.bat` removes the
environment only; the program folder and your data, results and settings
stay.

### Without Anaconda
The Open launchers fall back to a local Python environment (`app/.venv`), built
and filled automatically on the first run. This needs Python 3.12 or newer (the
program's packages are pinned to exact tested versions, which need it); on
Windows get it from [python.org](https://www.python.org/downloads/) (tick
"Add python.exe to PATH" during setup).

To run from a terminal instead:

```bash
cd app
conda activate track-tamer && python gui.py   # Anaconda
./.venv/bin/python gui.py                     # .venv, Mac
.venv\Scripts\python.exe gui.py                # .venv, Windows
```

## What it computes

**Elevated Plus Maze** (when Test is EPM): open/closed-arm and center time,
% open time (of arm time), arm and center entries, % open entries, Anxiety
Index, closed/open time ratio, and latency to first open/closed/center entry.
An entry only counts once the animal stays in a region for at least **Min
entry (frames)** (default 5), which filters jitter at region boundaries.

**Open Field** (when Test is Open Field): center time and %, center entries
(a return within **Min time between center entries**, default 1 s, is the
same visit), latency to the center, time on each side, field crossings
(opposite sides, and adjoining sides when the center visit lasted at least
the adjoining minimum, default 0.5 s), and crossing speed (average and
peak, smoothed over **Speed smoothing (frames)**, default 5). Sides are judged
against the center ROI's lines exactly as drawn in the file (each edge
extended across the arena), with the top of the video as the top of the
arena.

Every analyzed row records the settings that produced it (test, entry rule,
and the Open Field thresholds), so exported tables show how they were made.

**Key measures** come first, on screen and in exports. For the Elevated
Plus Maze they are, in order: closed/open time ratio, center time, % center
(of the session), open-arm time, % open (of arm time), closed-arm time, %
closed (of arm time), open entries, and closed entries. The Summary tab shows
only these by default; tick **More test measures**, **Session basics** and the
other boxes to add columns. Open Field shows its basics and test measures.

**Summary metrics** (one row per file):
- Total distance (cm / px), duration, mean speed
- Time and percent spent in each region (e.g. center / periphery, or each EPM
  arm), and entries into each region under the same entry rule as the test
  measures, plus region-to-region transitions
- **One region per frame:** a point on a border the center shares (or in a
  drawn overlap) counts for the **center only**, so each arm's time is exactly
  its own time and the per-region numbers always add up to the test totals
  (e.g. closed-arm time = closed arm 1 + closed arm 2). Only the center may
  share; frames in two other regions are counted for the first and reported
  in a warning. Tracking writes border pixels to the center only, too.
- **Outside every region:** a tracked point outside all the drawn regions
  still counts. In Open Field it's periphery, since anything that isn't center
  is periphery (usually the mouse jumping at the wall). In EPM it goes to the
  nearest region, so a head dip over the side of an arm counts for that arm.
  The Summary's Details reports how often this happened (`OutsideEvents`),
  for how long (`OutsideTime_s`), and the average and longest stretch.
- The tracking settings recorded in the file

**Object Recognition** (novel object recognition / spatial object recognition; videos tracked in
this program): in **Set up videos…**, step 5 (**Objects**), draw each object
as a circle: press at its center and drag out to its edge. Two objects are
listed; **Add object** adds more. Mark each **Familiar**, **Novel** or
**Moved**, and set the trial **day** and **phase**. A dashed **zone** rings
each object out to the **Zone distance (cm)** (main window, default 4 cm;
never locks, and needs the scale). After tracking, the **Review** tab lists every stretch the
tracked point spends in a zone. Click one to open the playback window at the
frame the point enters the zone, then step through and log each interaction
with **Start interaction (S)** / **End interaction (E)**, or mark the visit
**No interaction (N)**. **Next visit ▶** / **◀ Previous visit** (the ] and [
keys) move through the list without leaving the window. Every moment in a
zone is listed, however brief, so no possible interaction is missed; the
default zone is 4 cm. Interactions can be logged at any frame, with the
object picked by hand. Scoring is saved as you go to
`<name>_ObjectScoring.csv` beside the tracking file. Results: interaction
time, bouts and latency per object; total; **discrimination index** =
(novel − familiar) / (novel + familiar) time and **% preference** = novel /
(novel + familiar) × 100 (novel = objects marked Novel or Moved); zone time
and visits per object; day, phase and the novel object(s). They update as you
score. The export adds an **Interactions** sheet. **Edit trial info…** in the
Review tab changes each object's type, the trial day and the phase after
tracking, with no re-tracking. **Save as video…** draws the objects and zones
on the saved `_tracked.mp4`.

**Acoustic Startle Response** (videos): the motion index for each frame is the
share of pixels whose brightness changed by more than the **intensity
threshold** (default 15, previewed in setup step 3) from the frame before.
For each stimulus, **startle amplitude** = highest motion index in the startle
window (200 ms after it) minus highest in the baseline window (200 ms before
it, or before the prepulse on prepulse+pulse trials). Stimuli come from the
recording app's `_info.json`, or you type the video frames in setup step 4.
Frames marked as repeated are left out of the peaks. The **Trials** tab lists
Pixel.change, motion.index.before and .after, FrameNo, Time.startle,
ReactionTime (ms from stimulus to peak) and Startle amplitude. The **Review**
tab lists every startle; click one to open the video at its stimulus, and use
**Next trial** / **Previous trial** ([ and ]), **Go to stimulus** and **Go to
peak** in the playback window. The Summary
gives the mean amplitude per trial type and pulse frequency, **% PPI**
(overall and per prepulse level) and **% habituation** (first vs last block of
pulse-alone trials). Results save as `<name>_MotionIndex.csv`, and Export
writes `_analysis.xlsx`, `_trace.png` and `_aligned.png`.

**Time bins** (per file): the session split into fixed-length bins (default
60 s) with distance, mean speed, and time-in-zone per bin, plus the chosen
test's measures for each bin (EPM: arm/center time, entries, % open, Anxiety
Index, ratio; Open Field: center time and entries, side times, crossings, and
crossing speed). Entries and crossings are counted in the bin where they
start, so the bins add up to the session totals. Latency is session-only.

**Plots** (per file): path/trajectory (colored by speed or one solid color) and
occupancy heatmap, both with ROI outlines. The heatmap labels each region
outside the ROIs so the data stays visible. Each tab has a **Background**
choice:
- **None:** no background. Heatmap cells the animal never entered stay
  empty, which makes them transparent in a saved PNG.
- **Flat color** (Heatmap only): fills those cells with one color, which is
  easy to recolor in an image editor.
- **Reference image:** draws the plot on the arena's empty-arena image in
  gray. It is only available for files tracked in this program, which keep a
  `_reference.png` next to the tracking file.

## Tracking videos

Videos (`.mp4`, `.avi`, `.mov`, `.wmv`, `.mpg`, `.mkv`, `.m4v`) go in the same
file list as CSVs, marked **Video**. Tracking is adapted from ezTrack (see
Credits).

1. **Add the videos** as you would CSVs, and choose the **Test** first (the
   regions to draw depend on it). Each video starts as **Needs setup**. If a
   video has frames that can't be read, you're asked whether to add it
   anyway. Converting it (e.g. to .mp4 with H.264) usually fixes this.
2. **Set up videos…** opens one window for all of them, with six steps per
   video. **Next** moves on, or says what's missing. The arrows at the top
   switch videos, and **Start from previous video** copies the last video's
   choices as a draft to check. Scroll to zoom on any image, and right-drag
   or Control-drag to move around.
   1. **Trim and crop:** scrub to the trial's start, choose the session
      length (EPM 5 min; Open Field 1 or 1.5 h, or type one), and drag a
      rectangle around the arena.
   2. **Exclusions:** optionally outline areas to ignore, such as a cable
      or a reflection.
   3. **Reference:** make the empty-arena image from frames across the
      trial. The animal drops out because it's in a different place in
      most of them.
   4. **Tracking check:** scrub to any frame to see where the animal is
      found (red cross), and adjust the tracking settings. The settings are
      shared by every video and lock at the first Track.
   5. **Regions:** draw the test's regions on the reference.
      - Elevated Plus Maze: open arm 1 and 2, closed arm 1 and 2, center.
      - Open Field: the arena outline and the center. The periphery is the
        outline minus the center.
      - Points lock onto neighboring regions' points and edges, so regions
        share borders instead of overlapping.
   6. **Scale:** click two points a known distance apart and type that
      distance. EPM: 75 cm, from the end of one arm to the end of the
      opposite arm. Open Field: 40 cm along one wall.

   A video with every step done shows **Ready to track**.
3. **Track** works on the selected videos, one at a time in the background.
   - A bar at the bottom shows progress, and **Cancel** keeps the videos
     already finished.
   - If a video already has a tracking file beside it, you're asked whether
     to use it or track again.
   - If the videos' frame rate differs from the **Frame rate** setting, you
     can switch the setting to the videos' rate.
   - Each video gets `<name>_LocationOutput.csv` (ezTrack's format, plus
     every setting used and a `Frame_Unreadable` column) and
     `<name>_reference.png` next to it, and becomes **Not analyzed**.
4. **Analyze** and **Export** as for CSVs (below).
5. The **Review** tab lists the points to review for the selected file, and
   **Open playback window** plays its video, in its own resizable window,
   with the tracked position drawn on. Clicking a row in the list opens the
   window at that exact frame.
   - The window shows a red marker, a short trail, region outlines, and an info line
     with the session frame and time, the video's own frame and time, and the
     current region.
   - Controls: play/pause (space bar with the pointer on the video), ◀ ▶ one
     frame, ◀◀ ▶▶ 10 seconds, a slider, and a speed choice (0.25x to 8x).
   - **Points to review** lists every stretch where the tracked point was
     outside all the drawn regions, with its frame, session time, video frame
     and time, length, the region it counted for, and how far outside it
     went. Brief stretches are usually jumps
     at the wall or head dips. A stretch at least as long as the cutoff
     (**Flag stretches at least (s)**, saved per test; Open Field 1 s, EPM
     5 s) is flagged because the tracker may have got stuck on a dark spot
     or a reflection. Analyze also warns about these. Because brief ones are
     handled, exclusion shapes can be drawn generously.
   - **Save as video…** writes `<name>_tracked.mp4` next to the video, at
     its real frame rate. It plays on Mac and Windows.
   - It works for any file tracked in this program whose video is in the
     same folder.

**Unreadable frames** stay in the tracking file as rows with no position. By
default they add no time, distance or entries. Turning on **Fill short gaps**
in the settings panel instead joins gaps of up to the chosen length with a
straight line for the analysis. The saved file is never changed.

## Window layout

The **left panel** holds the **Files** buttons (Add files…, Add folder…,
Remove, Clear) and the **Run** buttons (Set up videos… and Track when videos
are listed, Select all, Analyze, Export), then the settings, with **About**
at the bottom. In a short window the panel scrolls. The file list sits above
the tabs. The **Path** and **Heatmap** tabs have their controls in a column
beside the plot: point or cell style, Background, **Region labels** (show or
hide the region names on the plot and in the exported image). The **Review**
tab lists the points to review and opens the selected file's video in a
playback window.

## Working with files
1. **Add files…**, **Add folder…**, or drag files/folders onto the window.
   Files build up the **file list** (always visible above the tabs), each
   marked **Not analyzed**. Adding a file that's already in the list asks
   whether to add it again. **Remove** takes the selected files out of the
   list (the files themselves aren't touched).
2. Choose the **Test** (Elevated Plus Maze / Open Field), **frame rate**
   (default 20 fps), and **bin size** in the settings panel on the left.
3. **Analyze** works on the **selected** files; its button shows how many
   (e.g. **Analyze (1)**). The first file added is selected for you. Click
   **Select all** (or Ctrl+A / Cmd+A in the list) to select every file, or
   Shift/Ctrl/Cmd-click to pick a few. Nothing is computed until you click
   Analyze. At the first Analyze, the settings panel **locks** ("Locked.
   Clear to change."), so every file in the load is analyzed the same way.
   Path and Heatmap styling never locks.
4. **Click a file** in the list (or a row in the Summary) to see its Time
   Bins, Path, and Heatmap.
5. **Clear** empties the list and unlocks the settings, e.g. to try one file,
   adjust the settings, then run a whole folder.

The file list resets when the app closes. Settings, plot style, Summary
columns, and region roles are remembered. **Regions…** sets what each region
in the files means (open arm, closed arm, center, periphery). **About** shows
credits, the ezTrack citation, and the license.

## Exporting

**Export** writes, for each selected file that has been analyzed, three
files **next to its source CSV**, named after it, overwriting any earlier
export:

- `<name>_analysis.xlsx`: **Summary** (the file's row), **Time Bins**, and
  **Settings** (everything used to produce the results: test, frame rate,
  entry rule, Open Field thresholds, gap filling, region roles, bin size, the
  Path and Heatmap plot settings, how the file was tracked (method,
  threshold, window, downsampling, crop, reference frames, exclusion shapes,
  start frame, frame rate, scale), and for videos the session's start and
  length and the regions drawn).
- `<name>_path.png` and `<name>_heatmap.png`: drawn with the current on-screen
  plot settings at a fixed size (5 × 4.5 in, 200 dpi), whatever the window
  size, with a transparent background (heatmap cells the animal never
  entered stay transparent unless the background is a flat color; over the
  reference image the PNG isn't transparent).

For a video, these go next to the video. Tracking already saved
`<name>_LocationOutput.csv` and `<name>_reference.png` there.

Only analyzed files are exported. If a workbook is open in Excel, close it
before exporting again.

## Layout
The project folder holds only what you use directly; the program itself is
in `app`.
```
TrackTamer/
├── Install Track Tamer.command / .bat     build or update the environment
├── Open Track Tamer.command / .bat        start the app
├── Uninstall Track Tamer.command / .bat   remove the environment
├── README.md, INSTALL.md, TESTING.md, LICENSE
├── app/             the program
│   ├── core/            analysis and tracking engine (no GUI dependencies)
│   │   ├── export.py    write _analysis.xlsx and plot images
│   │   ├── safe_write.py  save files whole before replacing the earlier one
│   │   ├── loader.py    read & validate CSVs, detect region columns
│   │   ├── metrics.py   summary + time-binned metrics
│   │   ├── gaps.py      optional filling of short unreadable-frame gaps
│   │   ├── plotting.py  path, heatmap & region-map figures
│   │   ├── regions.py   region-role mapping and checks
│   │   ├── video.py     read and prepare video frames, exact frame jumps (from ezTrack)
│   │   ├── tracking.py  reference image, tracking, region columns (from ezTrack)
│   │   ├── video_setup.py  one video's setup (trim, crop, shapes, regions, scale)
│   │   ├── track_run.py    Track: videos one at a time in the background
│   │   ├── playback.py     playback and the saved _tracked.mp4 (from ezTrack)
│   │   ├── objects.py      object recognition: objects, zones, scoring, results
│   │   ├── asr.py          acoustic startle: motion index, trials, PPI, habituation
│   │   └── config.py    saved settings (config.json)
│   ├── gui.py           tkinter front end
│   ├── setup_window.py  Set up videos… window
│   ├── review_panel.py  Review tab, playback window and object scoring
│   ├── about.py         About window (credits, citation, license)
│   ├── region_dialog.py Match regions dialog
│   ├── tooltip.py       hover tooltips
│   ├── dialogs.py       pop-up messages (same look on Mac and Windows)
│   ├── tests/           checks run during development
│   ├── environment.yml  Anaconda environment (keep in step with requirements.txt)
│   ├── requirements.txt packages for the .venv fallback
│   ├── find_conda.sh / find_conda.bat   locate Anaconda for the launchers
│   └── config.json      your saved settings (made when the app first runs)
└── docs/            roadmap and the video metadata standard
```

The engine in `app/core/` is deliberately GUI-free so it can be scripted or, later,
bundled into a standalone app (e.g. with PyInstaller).

## Credits and license

Video tracking is adapted from **ezTrack**
(https://github.com/denisecailab/ezTrack), by Zachary T. Pennington, Zhe Dong,
Yu Feng, Lauren M. Vetere, Lucia Page-Harley, Tristan Shuman and Denise J. Cai,
used under the GNU General Public License v3.0. Files containing adapted code
say so at the top, along with what was changed. If you use the video tracking
in published work, please cite ezTrack:

> Pennington ZT, Dong Z, Feng Y, Vetere LM, Page-Harley L, Shuman T, Cai DJ
> (2019). ezTrack: An open-source video analysis pipeline for the
> investigation of animal behavior. *Scientific Reports* 9(1): 19979.

Because it includes ezTrack's code, this program is distributed under the
**GNU General Public License v3.0** (see [LICENSE](LICENSE)). Anyone who
receives a copy, including a future standalone app, must also be able to get
its source code under the same license.
