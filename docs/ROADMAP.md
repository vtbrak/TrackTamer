# Track Tamer — Roadmap

**Where files are (since 2026-11-10):** the program is in the `app` folder
(`app/gui.py`, `app/core/`, `app/tests/`, the environment files and conda
finders), this file and the metadata standard are in `docs`, and the
project folder itself holds only the launchers, README, INSTALL, TESTING
and LICENSE. Paths in this document such as `core/...` and `tests/...` are
inside `app`.

Feature and analysis plan for the behavior-tracking analyzer. This is the design
doc: what's built, what was decided (and why), and what's next. Nothing new is
built until it's agreed here.

---

## Already built (current state, as of 2026-10-30)
- **Core engine** (`core/`, GUI-free): loads tracking CSVs, validates columns,
  detects **region columns** automatically (any True/False column, e.g. EPM
  `ol/or/ct/cb/mid`, open field `center/peripheral`), parses ROI polygons.
- **File list** (§7): Add File… / Add Folder… / drag-and-drop add files to a
  list in the Summary, each marked *Not analyzed* until **Analyze Selected** or
  **Analyze All**. **Clear** empties the list. Test type, fps, bin size, the
  entry rule, and the Open Field thresholds lock at the first Analyze and
  unlock at Clear. The selected Summary row drives Time Bins, Path, and
  Heatmap.
- **Test-type dropdown** (EPM / Open Field) and **region-role mapping**
  (auto-classified, user-overridable via the Match regions dialog, saved).
  Each file's regions are checked against the test at Analyze.
- **EPM measures** (§4) and **Open Field measures** (§5) in the Summary
  ("Test measures" group) and **per time bin** (§5b). Includes the entry rule,
  Open Field sides judged against each file's own drawn center lines,
  crossings, and smoothed crossing speed.
- **Summary table**: one row per file. File and Status are always shown; the
  other columns come in checkbox groups (Session basics and Test measures on
  by default; Zone time & %, Entries & transitions, ROI label time & %,
  Details). Choices are saved. Each analyzed row records the settings that
  produced it.
- **Time Bins table**: fixed bins (default 60 s) with distance, speed, region
  time, and the test's measures per bin.
- **Path plot** (color-by-speed or solid color; size, transparency) and
  **occupancy heatmap** (bins, colormap, region labels outside the ROIs, empty
  cells transparent, optional flat-color background). Each tab has its own
  controls, which never lock.
- **Center/periphery overlap warning** at Analyze.
- **Export Selected / Export All** (§9): per file, `_analysis.xlsx` (Summary,
  Time Bins, Settings) plus `_path.png` and `_heatmap.png` next to the source
  CSV.
- **Settings saved** to `config.json` (test type, fps, bin size, entry rule,
  Open Field thresholds, plot style, Summary columns, region roles).
- **Cross-platform groundwork** (§10): shared pop-up dialogs (`dialogs.py`),
  hover tooltips (`tooltip.py`), and launchers for Mac
  (`Open Behavior Tracker.command`) and Windows (`Open Behavior Tracker.bat`).
- **Regression test**: `tests/regress_gui.py` drives the app through the whole
  workflow on the sample files.
- Code is on GitHub (`vtbrak/EZAnalyze`, private). Data CSVs and export
  outputs are gitignored.

---

## Design decisions (locked in)
- **Zone/region membership**: trust the file's own **region columns** (one
  True/False column per region) rather than recomputing from X/Y. The one
  exception is open-field sides, which the file doesn't have, so they're
  judged against **that file's own drawn center-ROI lines** (§5).
- **Each file has its own ROI lines and is analyzed against its own.** ROI
  geometry is never shared or reused between files; only the region
  name → role mapping is shared.
- **Region identification**: region names vary between files (EPM uses short
  codes like `ol`, `ct`, `mid`; open field uses `center`, `peripheral`), and
  their order varies too. So the app keeps a **region-role mapping**: each
  region is auto-classified by keyword or code and can be overridden.
  Unrecognized names prompt the user with a dropdown. **Mapping is saved.**
- **Overlaps**: a frame in more than one region counts as **center**. Center
  and periphery must never overlap; if they do, the file is in error and the
  user is warned.
- **Test type**: a **dropdown** (Elevated Plus Maze / Open Field) selects which
  metric set runs. No auto-detection for now.
- **Thresholds** (entry rule, Open Field gap / adjoining time / speed
  smoothing): **input boxes** in the UI, **values persisted** to `config.json`,
  locked at Analyze, and **recorded with the results** (Summary row and the
  export's Settings sheet).

---

## Planned features

### 1. File input
- [x] **Drag-and-drop** files/folders onto the window, in addition to the
  Add File… / Add Folder… buttons.
- [x] Graceful fallback: if drag-and-drop can't initialize, buttons still work.

### 2. Plot controls (path & heatmap)
- [x] Adjustable **point size**.
- [x] Adjustable **point color** (used when not coloring by speed).
- [x] Adjustable **transparency (alpha)**.
- [x] Toggle: color-by-speed vs solid color; heatmap bin count.
- [x] Settings persisted in `config.json`.
- Later additions: controls moved into their own tabs (Path: size,
  transparency, speed coloring, point color; Heatmap: bins, colormap, Add
  background + color), and they never lock (§7, §8).

### 3. Test-type framework
- [x] Test-type dropdown (saved). It chooses which measures are computed
  (EPM §4 or Open Field §5) and what the region check expects.
- [x] Region-role mapping ("Match regions" dialog, also via **Regions…**):
  each region column is auto-classified (keywords + EPM codes like ol/ct/mid),
  user-overridable, saved. Opens automatically when names can't be matched or
  don't fit the chosen test.
- [x] ROI polygons are paired with regions by data agreement, not file order,
  and labeled on the plots (Path: on the region; Heatmap: outside it, §8).

### 4. Elevated Plus Maze (EPM) metrics (✅ built 2026-10-29; immobility deferred)
- [x] **Open-arm vs closed-arm time** (seconds and %).
- [x] **EPM anxiety measures** — report ALL of:
  - %open-arm time and %open-arm entries (separately)
  - Composite **Anxiety Index** = `1 − [ (open-arm time/total arm time +
    open-arm entries/total entries) / 2 ]` (higher = more anxious)
  - **Closed/open time ratio** = closed-arm time ÷ open-arm time
- [x] **Latency to first entry** — time to first open-arm entry (and closed-arm,
  center for reference).
- [x] **Time in center region** (the cross intersection). Arm+center
  overlap frames count as center (`core.regions.frame_roles`).
- [x] **Open- and closed-arm entry counts.**
- ⏸ **Immobility detection: deferred to a future item** (user, 2026-10-29: not
  calculated for this type of data for now). See §11.

**Entry rule (EPM & open field):** an entry counts only when the tracked point
stays inside the region for at least **N frames** (configurable, saved). Filters
boundary jitter. (A true "all four paws" rule isn't possible — data is a single
centroid.)
- ✅ Built as `core.metrics.held_entries`. The current region only changes
  after N consecutive frames somewhere new, so brief visits don't count and
  jitter doesn't split one stay into two entries. **Default N = 5 frames**
  (0.25 s at 20 fps), set in the toolbar's "Min entry (frames)" box, saved,
  and locked at Analyze with fps and bin size.
- ✅ **Starting region (decided 2026-10-29):** time spent in the region the
  animal starts in **counts toward that region's total time**, but **not
  toward latency**. Latency is the first time it *enters* the region after
  leaving. The starting stay also isn't counted as an entry. Example:
  `EPM.csv` starts on an open arm for 6.80 s; that time is included in open-arm
  time (23.65 s), while open latency is 75.5 s.
- **The rule is recorded with the results**: every analyzed Summary row
  carries `Test` and `MinEntryFrames` columns (Details group), and the §9
  export's Settings sheet lists it ("Min entry (frames)").
- Sample `EPM.csv` (20 fps): open entries are 22 with no rule, 6 at 5 frames,
  and 6 at 10 frames. So 5 frames filters boundary flicker without losing
  real visits.

**EPM columns** (Summary "Test measures" group, on by default):
`EPM_OpenArm_s`, `EPM_ClosedArm_s`, `EPM_Center_s`, `EPM_PctOpenTime` (% of
arm time), `EPM_OpenEntries`, `EPM_ClosedEntries`, `EPM_CenterEntries`,
`EPM_PctOpenEntries` (% of arm entries), `EPM_AnxietyIndex`,
`EPM_ClosedOpenRatio`, `EPM_Latency_Open_s` / `_Closed_s` / `_Center_s`, and
`EPM_PctSession_Open` / `_Closed` / `_Center`. Blank = can't be computed
(e.g. no open-arm time, or an arm never entered).

### 5. Open Field metrics (✅ built 2026-10-29; immobility deferred)
- [x] **Center-region entries** — count entries into the center, using the
  shared entry rule (min frames inside) plus a **minimum time-between-entries
  threshold** (debounce). Both configurable, saved.
- [x] **Time & % in center**, latency to first center entry.
- [x] **Field crossings** — a crossing is a traversal **across the center** that
  connects two sides. Counts in three categories:
  - **Opposite sides**: left↔right and top↔bottom.
  - **Adjoining sides**: e.g. left→top — counted **only if the path spends at
    least a minimum time in the center region** between the two sides
    (configurable, saved), so corner-cuts near an edge don't count.
  - Report counts per category (and a total). Center comes from the file's
    region column. **Sides come from X/Y** relative to the center ROI, with
    the top of the video as the top of the arena (the files have no side
    regions).
- [x] **Crossing speed** — report **both** average speed over the traversal
  (leaving one side → reaching the next) and **peak** speed during crossings.

**✅ Open Field definitions (decided 2026-10-29)**
- **Defaults:** min time between center entries **1 s**; min center time for an
  adjoining-side crossing **0.5 s**; speed smoothing **5 frames**. All three are
  input boxes on a third toolbar row that only shows when the test is Open
  Field. They're saved and lock at Analyze.
- **Center entries:** the entry rule (min frames) applies. Re-entering the
  center less than the minimum gap after leaving it continues the same visit.
  The starting region counts toward time, not entries or latency (as for EPM).
- **Sides follow the center ROI's drawn lines as they are in the file**
  (user, 2026-10-29: "Follow the lines of the ROIs from the file, not what
  would be assumed to be straight." The program doesn't draw ROI lines; it
  reports which side of the drawn line the point is on.) Each edge of the
  drawn center polygon is extended across the arena, and a point belongs to
  the side whose line it's furthest beyond: left of the drawn left edge =
  left, above the drawn top edge = top, and so on. **Corners split along the
  diagonal** between the two lines. An edge's side comes from the way it
  faces. Top of the video = top of the arena. A point inside the polygon but
  not in the center by the file's columns takes its nearest edge's side, so
  every frame is center or exactly one side. Built as
  `core.metrics.side_labels`.
- **Every file has its own ROI lines, and each file is analyzed against its
  own** (user, 2026-10-29). Center membership comes from that file's region
  columns; sides, crossings, and plot outlines/labels come from that file's
  own `ROI_coordinates`. Nothing geometric is shared or reused between files.
  Only the region *name → role* mapping is shared, since names mean the same
  thing across files. Verified with two files that have the same path but
  different center squares: each gets its own sides and crossings.
- **Crossings:** side A → center → side B with B ≠ A, using the entry rule's
  held places. Opposite sides (left↔right, top↔bottom) always count. Adjoining
  sides count only if the center visit lasted ≥ the minimum. Going around the
  edge without the center, or returning to the same side, isn't a crossing.
- **Crossing speed:** speed is **smoothed** first (user, 2026-10-29): a
  centered rolling mean over **Speed smoothing (frames)**, default **5**
  (0.25 s at 20 fps), saved, locked at Analyze, 1 = none. The average is the
  mean of each counted crossing's average speed from leaving side A to
  reaching side B. The peak is the fastest smoothed frame during any counted
  crossing.
- **Recorded with the results:** Open Field rows carry
  `MinBetweenCenterEntries_s`, `MinCenterAdjoiningCrossing_s`, and
  `SpeedSmoothing_frames` (plus `Test` and `MinEntryFrames`) in the Details
  group and every export.
- **Columns** (Summary "Test measures"): `OF_Center_s`, `OF_PctCenter`,
  `OF_Periphery_s`, `OF_PctPeriphery`, `OF_CenterEntries`,
  `OF_Latency_Center_s`, `OF_Left_s` / `_Right_s` / `_Top_s` / `_Bottom_s`,
  `OF_Crossings_Total`, `_Opposite`, `_LeftRight`, `_TopBottom`, `_Adjoining`,
  `OF_CrossingSpeed_Mean_cm_s`, `OF_CrossingSpeed_Peak_cm_s`.
- **Sample `Open Field.csv`:** center 21.5% (793 s), 227 center entries (250
  with no gap, 202 with 3 s), 197 crossings (66 opposite: 27 L↔R and 39 T↔B;
  131 adjoining), crossing speed 10.2 cm/s average and 36.1 cm/s peak with
  5-frame smoothing (42.8 unsmoothed). Center + sides = the full 3686.3 s
  session.
- ⏸ Immobility detection: deferred (see §11).

### 5b. Test measures per time bin (✅ built 2026-10-30)
- [x] The **EPM and Open Field measures are added to the Time Bins** table
  (on screen and in the exported Time Bins sheet), after the general bin
  columns (requested 2026-10-30).
- **EPM per bin:** open/closed/center time, % open time, open/closed/center
  entries, % open entries, Anxiety Index, closed/open ratio, and
  `EPM_PctBin_Open` / `_Closed` / `_Center` (% of the bin).
- **Open Field per bin:** center and periphery time and %, center entries,
  time per side, crossings (total, opposite, L↔R, T↔B, adjoining), and
  crossing speed (average and peak) for the crossings in that bin.
- **How bins are counted:** entries and crossings are found **once over the
  whole session**, then each is counted in the **bin where it starts** (a
  crossing starts when the animal leaves side A for the center). So bin
  values add up to the session totals, a visit or crossing that spans a bin
  edge isn't split or double-counted, and a bin's start isn't treated as a
  starting position. Verified on both samples at 60 s and 30 s bins: every
  entry and crossing count sums exactly to the session, and times match.
- **Latency is session-only** (time to the first entry), so it isn't in the
  bins.
- Built as `epm_binned` / `of_binned` in `core/metrics.py`, sharing one
  span calculation (`_epm_block` / `_of_block`) with the session summary.

### 6. Config / persistence
- [x] `config.json` holding fps, bin size, all thresholds, plot style, and the
  region-role mapping. Loaded on start, saved on change.

### 7. File-input workflow (requested 2026-10-23 — ✅ built 2026-10-23)
The larger concern: how the program handles files loaded one after another,
and multiple files from a folder.

**Problems before §7 was built**
- Loading a file **replaces** the previous one and **immediately computes**
  using whatever settings (test type etc.) are already selected.
- There's no chance to choose the test type and parameters for a file
  *before* it's analyzed — so loading an open-field file while EPM is selected
  triggers the "doesn't fit the test" warning before the user can say which
  test it is.
- After loading a **folder**, there's no way to pick one file from it and view
  its Time Bins, Path, or Heatmap (batch mode only shows the Summary table).

**Notes from building**
- Each file's regions are checked against the test **on its own** at Analyze
  time. Files that still don't fit after the Match regions dialog are skipped
  and named, while the rest are analyzed.
- Repeated files get "(2)", "(3)", ... after the name so their rows can be
  told apart.
- Export later became per file (§9), replacing the single-table export.

**Wanted**
- [x] A load step that lets the user **pick the test type and parameters for a
  file before computing**, without the EPM/open-field warning firing first.
- [x] A defined behavior for **loading files one after another** (rather than
  silently replacing and recomputing).
- [x] In folder/batch mode, a way to **select a single file** and view its Time
  Bins, Path, and Heatmap.

**✅ Decided 2026-10-23**
- [x] **New files are added to a list.** Loading (Add File…, Add Folder…,
  drag-and-drop) appends to the list instead of replacing what's there.
- [x] **Clear button** empties the list.
- [x] **The list resets when the app closes.** It isn't saved between
  sessions.
- [x] **Settings are chosen once per load session.** They stay editable after
  files are added, and **lock at the first Analyze**. They then apply to every
  file added afterward. **Clear** resets this, so settings can be chosen again
  for the next batch. (Changed 2026-10-23: originally locked at the first
  load, but the user wants to load a file *then* choose settings.)
  - A **tooltip** explains this, e.g. on Clear: "Clears the file list and
    lets you choose settings again."
- [x] **Analysis starts with an Analyze button**, not automatically on load.
  So the EPM/open-field warning can't fire before the test is chosen.
- [x] **Two ways to analyze:** **Analyze all** files in the list, or
  **Analyze selected**, the file selected in the Summary table.
- [x] **The file selected in the Summary table drives the Path and
  Heatmap** tabs. Clicking a row shows that file's plots. This is also how a
  single file is viewed in folder mode.

**✅ Details decided 2026-10-23**
- [x] **Locked for the whole load session** (until Clear): **test type**,
  **fps**, and **time-bin size** (later also the entry rule and the Open
  Field thresholds). Bin size stays consistent across every file
  in the load, and **is remembered when the app closes**, like fps.
- [x] **Plot style stays adjustable at any time** (point size, colors,
  transparency, colormap, heatmap bins, background), and whatever is selected
  **is remembered** (already saved in `config.json`).
- [x] **"Not analyzed" status in the Summary**, in a column **immediately
  after the file name**. It changes once the file is analyzed.
- [x] **Repeated file: ask the user** whether to ignore it or add it again.
- [x] **Always wait for Analyze.** Files added later are never analyzed
  automatically, even when settings are already chosen.
- [x] Files can be added **one at a time or via a folder**, mixed freely.

**Use case to support:** analyze **one file**, look at the results, adjust
the settings, then run a **larger set** of files. In practice: load one file
→ Analyze → **Clear** (resets the list and unlocks the settings) → choose new
settings → load a folder → Analyze all. The Clear tooltip should make this
clear.

- [x] **Time Bins, Path, and Heatmap all follow the file selected in the
  Summary table.**
- [x] **Locked settings live in the toolbar** (no separate dialog). Test
  type, fps, and bin size can be set before or after adding files. Once
  **Analyze** is clicked, they're **greyed out** with a tooltip explaining
  they're locked until Clear.
- [x] **Path and Heatmap controls never lock**, so plots can be restyled
  after a file is analyzed.

All §7 decisions are made (2026-10-23).

### 8. Layout / display changes (requested 2026-10-23 — ✅ built 2026-10-23)
- [x] **Heatmap: no region labels drawn on the plot** (both EPM and open field).
  The name boxes added in step 3 sit on top of the data and block the view.
  Keep the ROI outlines. (Path plot labels are not part of this request.)
  - ✅ Decided: **labels sit outside the bounds of the regions.** Each label
    goes just past the outermost ROI edge, in its region's direction (EPM
    arms: past the arm end; a central region: along a free diagonal), with a
    thin line that **stops at the region's edge** so it doesn't cross data
    inside the region.
- [x] **Heatmap: no background by default** (EPM and open field). Today
  every empty cell is drawn in the colormap's lowest color (black for
  inferno), so the whole rectangle around the maze is filled. Instead, cells
  with no occupancy should show nothing.
- [x] **"Add background" button** on the Heatmap tab (EPM and open field).
  ✅ Decided 2026-10-23:
  - **Background = any pixel the mouse never occupied.** In practice that's
    every heatmap cell with zero frames, so it follows the heatmap's bin size.
  - **Format: transparent PNG**, so the background can be recolored or
    replaced in Photoshop. With the button off, those cells are transparent;
    with it on, they're filled with a background color.
  - **The button's on/off state is saved** in `config.json` like the other
    plot settings.
  - ✅ Built as an "Add background" toggle plus a **Background color…** picker
    (default light gray `#cccccc`), both saved. The toolbar's save keeps
    transparency (`savefig.transparent`), verified by checking the PNG's
    pixels: empty cells have alpha 0, or a flat color when the background is on.
  - **Heatmap grid now covers the whole arena** (all ROIs plus wherever the
    animal went), with **square cells**: `bins` cells along the longer side.
    So "background" fills every arena cell the animal never entered, not just
    gaps within the area it covered. Side effect: for a narrow path like the
    EPM sample, cells are coarser than before at the same bin count. Raise
    Bins for finer detail.

- [x] **Dialog box text: only the first sentence in bold**, the rest in
  regular type, for every pop-up (warnings, errors, info, questions).
  ✅ Built 2026-10-23 as `dialogs.py`, a tkinter-drawn dialog, because native
  message boxes style text differently (macOS bolds the whole message;
  Windows bolds nothing). It looks the same on both (§10).

### 9. Exporting results (requested 2026-10-23 — ✅ built 2026-10-29)
- [x] Proper **export for a single file** and for **multiple files**
  (folder/batch).

**Built as:** **Export Selected** / **Export All** buttons (replacing Export
Table…), with `core/export.py` doing the writing. Notes:
- Only analyzed files are exported. Export All reports how many weren't
  analyzed; Export Selected on an unanalyzed file says to analyze first.
- A file added to the list twice is exported once (same output names).
- The **Settings sheet** has Section / Setting / Value rows: Source (file path,
  video name, export time), Analysis (test, fps, min entry frames, and for
  Open Field the entry gap, adjoining center time, and speed smoothing),
  Region roles, Time Bins (bin size), Path, Heatmap, and the file's own
  tracking settings. On/off values read Yes/No.
- Images are drawn by the same builders as the on-screen plots, using the
  plot settings at the moment of export, transparent, and cropped to their
  content so no label is clipped.
- **Exported plots are a fixed size: 5 × 4.5 in at 200 dpi** (about 1000 ×
  900 px before cropping), independent of the window. Matching the on-screen
  size was tried and **reverted** (user, 2026-10-29: the image must not resize
  with the window). Because the on-screen plot stretches to fill its tab,
  points can look denser in the export than on screen at the same point size.
- A file open in another program (e.g. the workbook in Excel, which locks
  files on Windows) is reported by name; the other files still export.
- Output files (`*_analysis.xlsx`, `*_path.png`, `*_heatmap.png`) are
  gitignored like the CSVs.

**What existed before**
- **Export Table…** saves whichever table tab is active (Summary or Time
  Bins) as CSV or Excel. It's one table at a time, and the Summary always
  includes every column.
- In batch mode, only the combined Summary can be exported. There are no
  per-file Time Bins.
- Plots can only be saved one at a time, through the matplotlib toolbar under
  each plot.

**✅ Decided 2026-10-23: export everything, per loaded file**
For each loaded file (one file, or every file in a folder), named after the
**loaded file's own name** (e.g. `EPM.csv` → `EPM_...`):
- [x] `<name>_analysis.xlsx`: one Excel workbook with **everything, each
  table on its own sheet**: Summary and Time Bins (both including the test's
  measures) plus Settings.
- [x] `<name>_path.png`: the Path plot image.
- [x] `<name>_heatmap.png`: the Heatmap image, keeping the transparent
  background (§8).

**✅ Details decided 2026-10-23**
- [x] **Saved next to each source CSV** (same folder as the file it came
  from).
- [x] **Existing output files are overwritten** without asking.
- [x] Each `_analysis.xlsx` **includes that file's Summary row** (its own
  sheet).
- [x] Each `_analysis.xlsx` includes a **settings sheet** recording every
  setting used to generate its results:
  - analysis: fps, test type, region roles, thresholds, **entry rule (min
    entry frames)**, and for Open Field the **min time between center entries**,
    **min center time for adjoining crossings**, and **speed smoothing**
  - **Time Bins**: bin size
  - **Path**: point size, transparency, color-by-speed, point color
  - **Heatmap**: bins, colormap, background on/off
- [x] Plot images use the **on-screen plot settings** (point size, colors,
  transparency, colormap, bins, background on/off).
- **No separate summary file.** The Summary row lives only in
  `_analysis.xlsx`, and there's no combined file either. (Decided 2026-10-23,
  replacing the earlier separate-CSV plan.)

### 10. Runs on both Mac and PC (requested 2026-10-23 — requirement)
- [ ] The program must **work on Windows PCs as well as macOS**. Groundwork
  built 2026-10-23 (shared dialogs + Windows launcher). **Awaiting the first PC
  test** (user not ready yet as of 2026-10-30). This applies to everything
  built from now on.

**PC test checklist** (for when the user tests): clone the repo, run
`Open Behavior Tracker.bat` (first run installs packages); add a file, change
the test/fps, Analyze, and check the settings grey out; hover a locked setting
for its tooltip; add the same file twice (bold first line, Add Again /
Ignore); drag a CSV or folder onto the window; analyze the Open Field file
(overlap warning); restyle Path and Heatmap; open Regions… (✓/⚠ line); Export
and open the workbook and images; check the left panel's buttons and the
plot control column fit (shrink the window: the left panel should scroll,
nothing cut off); close and reopen (settings remembered).

**PC test checklist, video tracking (C9, 2026-11-04):** on the
`video-tracking` branch, run the installer again (new packages: OpenCV,
SciPy, Pillow), then:
1. **Add a video** (an .mp4; also try an .avi or .wmv if you have one). It
   shows as Video / Needs setup. Drag a video onto the window too.
2. **Set up videos…:** the window fits the screen; scrub the slider; drag a
   crop rectangle; choose a session length.
3. **Zoom and pan:** mouse wheel zooms at the pointer; right-drag and
   Control-drag move around; − / + / Fit buttons.
4. **Exclusions and regions:** click points, close a shape on its first
   point, drag points; a white ring shows before a point locks onto another
   region; the lock checkbox turns it off.
5. **Reference and Tracking check:** the reference makes in a few seconds;
   the red cross follows the animal while scrubbing; Frame / Differences
   view; changing a setting re-previews.
6. **Scale**, then **Finish**: the video shows Ready to track.
7. **Track:** the window stays usable; the bottom bar and the file list show
   the percentage; **Cancel** stops within a moment; the frame-rate question
   appears if the setting differs; `_LocationOutput.csv` and
   `_reference.png` appear next to the video.
8. **Analyze**, then the **Background** choices on Path and Heatmap
   (Reference image lines up with the path).
9. **Play video…:** plays smoothly at 1x; speed, slider, frame steps, space
   bar; **Save as video…** writes `_tracked.mp4`, which plays in the Windows
   Media Player / Movies & TV app.
10. **Export:** open the workbook's Settings sheet (tracking, scale, crop,
    session rows).
11. **Close the app while tracking:** it asks first.
12. Paths with spaces or non-English letters in folder names.
13. **Frame jumps (2026-11-10):** in the playback window, drag the slider
    to several places, use ◀◀ / ▶▶ and the frame steps, and click Review
    rows: the red mark sits on the animal straight after each jump (not a
    frame behind) and a long video opens within a couple of seconds. With
    the Examples videos in place, `python tests\test_seek.py` (in the
    app's environment) ends with "all ok".

**Known Mac-only or at-risk pieces**
- ✅ **Launcher:** `Open Behavior Tracker.bat` added alongside the Mac
  `.command`. It builds `.venv` from `requirements.txt` (via `py -3`, falling
  back to `python`) and runs `.venv\Scripts\python.exe gui.py` in a console so
  errors stay visible. CRLF line endings are enforced by `.gitattributes`.
  Untested on Windows.
- ✅ **Dialog styling:** `dialogs.py` draws every pop-up with tkinter itself
  (bold first sentence, colored edge by kind, no icons/emoji), so it looks the
  same on both. Native file pickers and the color picker stay native, which is
  fine on both.
- **Drag-and-drop:** `tkinterdnd2` ships Windows builds, but this is
  untested on a PC.
- **Fonts and sizes:** fonts and widget sizes differ between macOS and
  Windows, so layouts (toolbar width, dialog wrapping) need checking on both.
  On the Mac the widest toolbar row is ~900 px, so the minimum window width is
  940 px. Windows fonts may run wider.
- **File paths:** keep using `os.path` and never hard-code `/` separators.
  Exports go "next to the source CSV" (§9), which also works on Windows paths.
- **Unicode symbols** in labels (⚠, ✓, —) should be checked on Windows
  fonts.

**Testing**
- ✅ **The user has a Windows PC to test on** (2026-10-23). After
  cross-platform work, hand over a short checklist of what to try on the PC.
- **Avoid Mac-specific features entirely**, even where a Mac-only option
  would look nicer. Prefer one portable approach used on both systems.
- Not part of this item: compiling/bundling (still on hold per CLAUDE.md).

### 11. Future items (deferred, not scheduled)
- ⏸ **Immobility detection** (EPM and open field). Deferred 2026-10-29: the
  user chose not to calculate immobility for this type of data for now.
  - **Superseded 2026-10-30:** freezing will come from **ezTrack's Freeze
    Analysis** (§12), using its thresholds instead of the speed-based plan
    below. It measures pixel change in the video, not the tracked point's
    speed, so tracking jitter doesn't affect it. It needs the video; data
    available only as a CSV still gets no freezing measure.
  - Original spec: immobile when speed stays below a threshold for at least a
    minimum duration (seeded at < 2 cm/s for ≥ 1 s, both input boxes, saved).
    Outputs: total immobile time, % immobile, bout count.
  - **Why it needs care — jitter measured in the samples:** while the animal
    is still, the tracked point wanders only ~0.07 cm (radius) and moves
    ~0.04–0.05 cm per frame (median; 95th pct ~0.13–0.15 cm). But at 20 fps
    that's an *apparent* speed of ~1 cm/s (95th pct 2.7–3.1 cm/s), so 10–14%
    of still frames read over 2 cm/s raw, and 8–9% with 5-frame smoothing.
    Larger windows (10–20 frames) were no better, because they blend in real
    movement. A single blip would break a bout, so bouts would be undercounted.
    (The tracking software's own smoothing is on in both files:
    `Use_Window = True`, weight 0.9, window 100. With one centroid, jitter
    can't be fully separated from small real movements like sniffing.)
  - Proposed when it's picked up: keep 2 cm/s / 1 s, share the 5-frame speed
    smoothing, and let a bout continue through a blip shorter than the entry
    rule. Each of these needs the user's OK.

### 12. Video analysis from ezTrack (branch `video-tracking`, started 2026-10-30)
Add video analysis to the app by adapting **ezTrack** (the open-source program
that produced these CSVs), so one tool goes video → tracking → analysis →
export. Development happens on the **`video-tracking` branch**; `main` stays
stable until it's merged.

**Source:** https://github.com/denisecailab/ezTrack (local reference copy in
`ezTrack/`, gitignored, including practice videos).

**License and credit (required; the user asked that they be kept):**
- ezTrack is **GPL-3.0**, so once its code is adapted in, the combined app is
  GPL-3.0. Add the GPL-3.0 license text to the repo; mark every file with
  adapted code ("adapted from ezTrack", authors, GPL-3.0, what was changed);
  credit and cite ezTrack in the README and an in-app About/credits screen.
  A distributed standalone app must also be GPL-3.0, with source available.
- **Citation:** Pennington ZT, Dong Z, Feng Y, Vetere LM, Page-Harley L,
  Shuman T, Cai DJ (2019). ezTrack: An open-source video analysis pipeline for
  the investigation of animal behavior. *Scientific Reports* 9(1): 19979.
- The ezTrack logo art is by Kathleen Wang; credit her if it's ever used.

**What ezTrack is:** two modules of Python functions driven by Jupyter
notebooks with HoloViews interactive tools (crop box, ROI drawing,
distance points). The notebook/HoloViews interface would be rebuilt as
tkinter windows; the processing uses OpenCV (works on Mac and PC, adds a
large dependency).

**✅ Decided 2026-10-30:**
- **Keep both modules:** Location Tracking *and* Freeze Analysis.
- **Freezing uses ezTrack's freeze thresholds**, replacing the planned
  speed-based immobility (§11). ezTrack's defaults: motion cutoff
  `mt_cutoff` = 10 (brightness change for a pixel to count as changed, after
  a light blur, `SIGMA` = 1); `FreezeThresh` = 200 (a frame is still if fewer
  pixels than this changed); `MinDuration` = 15 frames (0.75 s at 20 fps).
  Calibration from an empty-chamber video recommends `mt_cutoff` = 2 × the
  99.99th percentile of pixel change.

**Function catalog** (to go through with the user: keep / drop / rebuild):
- *Location Tracking:* `LoadAndCrop`, `cropframe`, `check_p_frames`,
  `Mask_select` (load/crop/exclude areas); `Reference` (empty-arena
  background); `Locate`, `TrackLocation`, `LocationThresh_View` (tracking and
  preview); `ROI_plot`, `ROI_Location`, `ROI_linearize`, `ROI_transitions`
  (draw ROIs and produce the region columns); `DistanceTool`, `setScale`,
  `ScaleDistance` (pixel → cm); `Summarize_Location`, `showtrace`, `Heatmap`,
  `PlayVideo` / `PlayVideo_ext` / `display_image` (summaries, figures,
  playback); `Batch_LoadFiles`, `Batch_Process` (folders).
- *Freeze Analysis:* `LoadAndCrop` / `cropframe` / `check_p_frames`;
  `Calibrate`; `Measure_Motion`; `Measure_Freezing`; `PlayVideo` /
  `PlayVideo_ext` / `display_image`; `SaveData`; `Summarize`;
  `Batch_LoadFiles` / `Batch`.
- Overlap with what this app already has: `Summarize_Location`, `Heatmap`,
  and `showtrace` (path) are already covered, in more detail.

**Useful for validation:** `ezTrack/PracticeVideos/6_2024-04-01_11-49-23.mp4`
is the video behind `EPM.csv`, so the adapted tracker can be checked against
an existing output.

**✅ Walkthrough, Stage 1 — Load and prepare the video (decided 2026-10-30;
not built).** Functions: `LoadAndCrop`, `cropframe`, `check_p_frames`,
`Mask_select`. Freeze Analysis has near-copies of the first three, so these
decisions apply to both modules. The user accepted all recommendations:
1. **Open videos and report their info** (frame count, frame rate, size):
   keep. **Fill the fps setting from the video's own frame rate
   automatically**, with an option to override it.
2. **Start/end trimming** (`start` / `end`): keep, set by **scrubbing through
   the video** to the trial's start and end frames, shown in seconds as well
   as frames (not only by typing frame numbers). Context: the user's ezTrack
   notebook tracked the EPM practice video from frame 460 to 6460, matching
   `Start_Frame = 460` in `EPM.csv`.
3. **Downsampling** (`dsmpl`): keep as an optional speed setting, **default
   full size (1.0)**.
4. **Display zoom** (`stretch`): **drop**. The app's window handles sizing.
5. **Crop rectangle**: keep as the main way to select the arena (tracking
   ignores everything outside it). `cropframe` stays as its helper.
6. **Crop for a folder of videos:** ezTrack applies one crop (drawn on the
   first video) to every video in a batch. Instead, **each new video starts
   from the previous video's crop, and can be adjusted per video**. This fits
   the rule that each file has its own geometry, and handles a camera that
   moved between sessions.
7. **Compatibility check** (`check_p_frames`: >1% of the first 300 frames
   unreadable): keep, but as a **warning naming the video, with an option to
   continue**, instead of ezTrack's hard stop.
8. **Exclusion shapes** (`Mask_select`, any number of drawn areas to ignore,
   e.g. cables or objects): keep for Location Tracking, and **optionally offer
   it in Freeze Analysis too** (ezTrack's freeze module only has the crop).

**✅ How videos fit the app (decided 2026-10-30; not built):** videos go into
the **same file list as CSVs**, with a **"Not tracked"** status. Tracking
(stages 1–5) produces the same per-frame data a CSV provides; from then on,
everything that already exists works unchanged: Analyze, Summary, Time Bins,
plots, and export.

**✅ Walkthrough, Stage 2 — Reference image (decided 2026-10-30; not built).**
Function: `Reference` (Location Tracking only; Freeze Analysis compares each
frame to the previous one and needs no reference). Tracking compares every
frame to a picture of the empty arena; this stage makes that picture.
1. **Only Option 1 is kept: build the reference from the video itself**, as
   the median of frames spread evenly across the trimmed trial (the animal is
   in a different place in most frames, so it drops out).
   - **Dropped:** Option 2 (a separate empty-box video) and Option 3 (a
     hand-picked list of frames).
   - Frame count: ezTrack's code defaults to 100; its notebook and batch mode
     use 50. Default and whether it's a setting are to confirm when building
     (recommendation was 50, changeable, saved).
   - Known limitation to keep in mind: if the animal stays in one spot for
     about half the trial or more, a "ghost" of it remains in the reference
     and tracking suffers there.
2. **Each video gets its own reference image** (as ezTrack's batch mode
   already does), never shared between videos.
3. **Unreadable frames** are replaced by another frame, as in ezTrack.
4. **The reference image is saved with the results**: kept with the tracked
   file and exported as `<name>_reference.png`, next to the other outputs.
5. **Reference as a plot background:** the **Path and Heatmap** plots (on
   screen and exported) get an **option to use the video's reference image as
   the background**. Details to settle in Stage 6, including:
   - how it combines with the Heatmap's current background choices (empty
     cells transparent, or "Add background" flat color), likely as a third
     choice;
   - alignment: X/Y and the reference must share the same crop and
     downsampling so the path sits exactly on the arena;
   - files loaded as CSVs have no reference image, so the option is
     unavailable for them.
- **Open question:** whether to show the reference for a check before
  tracking. Without Options 2 and 3, the remedies for a ghost would be
  changing the frame count or trim.

**✅ Walkthrough, Stage 3 — Tracking the animal (decided 2026-10-30; not
built).** Functions: `Locate` (finds the animal in one frame), `TrackLocation`
(runs it on every frame and builds the per-frame table) and
`LocationThresh_View` (preview on sample frames).
1. **Tracking math is kept as ezTrack does it**: grayscale → downsample →
   crop → difference from the reference (`dark` / `light` / `abs`) → zero the
   exclusion shapes → optional window around the previous position → keep the
   top `loc_thresh` percentile → position = center of mass. The only change is
   item 2.
2. **Wire removal is dropped** (`rmv_wire` / `wire_krn`, and with it ezTrack's
   per-frame wire warning). Note: the user's notebook had it on, so the
   practice video won't reproduce `EPM.csv` exactly; validation against it
   should expect close, not identical, positions.
3. **Settings are input boxes, saved to `config.json` and locked at Track**
   like the other settings, defaulting to the user's notebook values:
   `loc_thresh` 99.5; `method` dark; window on, `window_size` 100 px,
   `window_weight` 0.9.
4. **`window_size` scales automatically with downsampling**, so "100 px"
   always means the same area of the arena (in full-size video pixels).
5. **Preview, improved:** ezTrack's sample frames (red crosshair at the found
   position plus a color view of the differences), plus **scrub to any frame**
   and **re-preview after changing a setting**, before the full track.
6. **Progress bar with Cancel** while a video tracks (ezTrack only prints a
   text bar).
7. **Unreadable frames don't stop tracking** (ezTrack stops at the first one,
   silently dropping the rest of the video). The frame **stays in the data as
   a row** with a blank position, tracking continues (the window uses the last
   good position), and the user is told how many were unreadable.
   - **New column `Frame_Unreadable`** (True/False) in the tracking output
     marks these rows. ezTrack CSVs don't have it, so a file without the
     column is treated as all frames readable.
   - The loader must list it with the other non-region True/False columns
     (`ROI_transition`, `Use_Window`) so it's never taken for a region.
   - **Analysis adjusted for it** (details to confirm when building; these
     are the recommendations): the Summary reports the count (and %) of
     unreadable frames; those frames add no time to any region and no
     distance (no step is drawn across the gap); the entry rule treats them as
     a continuation of the place before, so a gap doesn't create or break an
     entry; Time Bins report unreadable frames per bin; plots skip them.
8. **Every setting used is recorded**: besides what ezTrack already writes
   (threshold, window on/size/weight, start frame), also method, crop,
   downsampling, reference frame count and whether exclusion shapes were
   used, in the tracking output and in the export's Settings sheet.
9. **A tracking CSV is saved**: `<name>_LocationOutput.csv` next to the
   video, in ezTrack's format (plus the new column and settings), so a video
   only needs tracking once and can be reloaded later like any CSV.

**✅ Walkthrough, Stage 4 — Regions of interest (decided 2026-11-03; not
built).** Functions: `ROI_plot` (draw named polygons on the reference),
`ROI_Location` (per-frame True/False column per region, plus
`ROI_coordinates`), `ROI_linearize` (`ROI_location` text label per frame) and
`ROI_transitions` (`ROI_transition`, where that label changes).
1. **Drawing tool rebuilt in tkinter** on the video's own reference image:
   click to place points and close the polygon, drag points to adjust,
   delete or redraw a region.
2. **Test type first, then the tool offers that test's regions to draw**, so
   each region knows its role as it's drawn (no "Match regions" step for
   videos). EPM: open arm 1, open arm 2, closed arm 1, closed arm 2, center.
   Names stay editable; extra regions can be added (role "ignore" or a chosen
   role).
3. **Open Field: draw the arena outline and the center**; periphery = inside
   the outline and not in the center, so the two can't overlap by
   construction. **Rule: a point in both center and periphery counts as
   center** (applies anywhere they could coincide, e.g. a shared edge or a
   center drawn partly outside the outline). The CSV side already resolves
   overlaps to center (`frame_roles` checks center first) while still warning
   that the file is in error.
4. **Each video gets its own ROIs, including in batch** (ezTrack's batch mode
   draws once and shares them; that's dropped). A new video can **start from
   the previous video's ROIs as a draft** that must be looked at and adjusted
   or confirmed; once confirmed, the lines belong to that video only.
5. **Checks while drawing:** warn right away if Open Field center and
   periphery would overlap; EPM arm/center overlaps stay allowed (count as
   center); warn before Track if a required region hasn't been drawn.
6. **Region test kept as ezTrack's** (pixel mask of each polygon, X/Y looked
   up in it), so video results match ezTrack CSVs. Unreadable frames get
   **blank** region values and a blank `ROI_location`.
   - ezTrack does **not** fill in a missing position from the frames around
     it (it stops tracking at the first unreadable frame).
   - **Decided:** the raw `_LocationOutput.csv` keeps unreadable frames
     blank. A **gap-filling option on the analysis side, off by default**,
     fills short gaps with a straight line between the positions just before
     and after (max gap length a saved setting, e.g. 5 frames); longer gaps
     stay blank. Filled rows stay marked by `Frame_Unreadable`, the saved
     data is never altered, and the option and max gap are recorded in the
     export's Settings sheet. Region values for filled frames come from the
     filled position against that file's own ROIs.
7. **Output format kept exactly as ezTrack's**: one True/False column per
   region, `ROI_coordinates`, `ROI_location`, `ROI_transition`, so the
   existing loader and analysis read video results unchanged.
8. **ROIs use the same coordinates as X/Y** (after crop and downsampling), so
   the path and reference background line up; crop and downsampling are
   recorded (Stage 3).
9. **Videos without regions are allowed** (distance and plots only), with a
   warning at Analyze since EPM and Open Field measures need regions.

**✅ Walkthrough, Stage 5 — Scale, pixels to cm (decided 2026-11-03; not
built).** Functions: `DistanceTool` (click two points on the reference, shows
the pixel length), `setScale` (real length and unit) and `ScaleDistance`
(cm per pixel = real ÷ pixel length; `Distance_cm` = `Distance_px` × factor).
Only distance is converted; X/Y and ROI coordinates stay in pixels.
1. **Measuring tool rebuilt in tkinter** on the video's reference image:
   click two points, drag to adjust, live pixel length, then type the real
   length.
   - **Guidance text above the drawing area** giving the arena sizes:
     **Open Field: 40 cm, inside corner to inside corner along one wall.
     EPM: 75 cm across** (end to end of opposite arms).
2. **Unit fixed to cm** (no free-text unit; ezTrack names the column after
   whatever is typed, which our analysis wouldn't find), so the output is
   always `Distance_cm`.
3. **Each video gets its own scale, including in batch** (ezTrack's batch
   mode measures once and shares it; dropped). A new video starts from the
   previous video's points and length as a draft to confirm or adjust.
4. **The real length is remembered** in `config.json` (per test type,
   starting at 40 cm for Open Field and 75 cm for EPM), so usually only the
   two points need clicking.
5. **The scale is recorded**: pixel length, real length and cm-per-pixel
   factor go in the tracking output and the export's Settings sheet.
6. **Missing scale: warn before Track**, with the option to go ahead; cm
   measures are then blank, as for a CSV without `Distance_cm`.
7. **Measured on the image tracking uses** (after crop and downsampling), so
   the factor always matches X/Y.
8. **One line, as in ezTrack.** A second (perpendicular) line could be added
   later if the camera angle makes horizontal and vertical lengths differ.

**✅ Walkthrough, Stage 6 — Summaries, plots and playback (decided
2026-11-03; not built).** Functions: `Summarize_Location`, `showtrace`,
`Heatmap`, `PlayVideo`, `PlayVideo_ext`, `display_image`.
1. **`Summarize_Location` dropped**: our Summary and Time Bins replace it.
2. **`showtrace` and `Heatmap` dropped**: our Path and Heatmap stay (the
   heatmap stays our square-cell grid, not ezTrack's blurred image). The
   one thing taken from them is the reference image as a background
   (Stage 2).
3. **Background choices**, saved in `config.json`: **Path** — *None* or
   *Reference image*; **Heatmap** — *None* (empty cells transparent), *Flat
   color* (the current "Add background") or *Reference image*.
4. **How the reference background looks:** grayscale; heatmap cells stay
   fully colored on top, so the reference shows only where the animal never
   went; with the reference on, the plot shows the whole reference image
   (the cropped arena) instead of fitting to the ROIs and data; the exported
   PNG is then not transparent.
5. **Alignment:** the reference sits in the same pixel coordinates as X/Y
   and the ROIs, top of the video at the top (guaranteed by Stage 4 item 8).
6. **Files without a reference** (loaded CSVs): *Reference image* is greyed
   out with a tooltip saying why; they fall back to *None*.
7. **Playback kept, rebuilt as a tkinter window** for the selected file:
   play/pause, scrub slider, speed choice; colored marker on the tracked
   position plus an optional short trail; optional ROI outlines; frame
   number, time and current region shown; unreadable frames marked (no
   marker) instead of crashing (ezTrack's playback crashes on a blank
   position). This is the main way to check the tracking.
8. **Saving the playback as a video: optional button, off by default**,
   writing `<name>_tracked.avi` next to the video at the video's **real**
   frame rate (ezTrack always writes 20 fps), with marker and ROIs drawn
   on, in a format that plays on Mac and Windows without extra software;
   overwrites like the other exports (ezTrack always writes
   `video_output.avi`, overwriting across videos).

**✅ Walkthrough, Stage 7 — Batch processing (decided 2026-11-03; not
built).** Functions: `Batch_LoadFiles` (videos of one type in one folder),
`Batch_Process` (per video: unreadable-frame check, own reference, track,
save `_LocationOutput.csv`, add to `BatchSummary.csv`; crop, exclusions,
ROIs and scale set once on the first video and reused) and `check_p_frames`
(refuses a video if >1% of its first 300 frames are unreadable).
1. **Adding videos:** Add File, Add Folder and drag-and-drop accept videos
   (`.mp4`, `.avi`, `.mov`, `.wmv`, `.mpg`, `.mkv`) as well as CSVs; mixed
   folders are fine; new videos show **"Not tracked"**.
2. **Already tracked:** if a video has a `_LocationOutput.csv` beside it,
   ask once for the batch: **Use existing tracking** (default) or **Track
   again**.
3. **"Set up each, then track all":** the interactive steps (trim, crop,
   exclusions, ROIs, scale) are done per video up front, each starting from
   the previous video's choices as a draft; then **Track All** runs every
   set-up video unattended. Videos not fully set up are skipped and named
   afterward. (ezTrack's shared first-video setup is dropped.)
4. **Running:** one video at a time in the background (window stays
   responsive); overall progress ("video 3 of 12") plus the current video's;
   **Cancel** stops after the current frame, keeps finished videos, leaves
   the rest "Not tracked"; a failure in one video doesn't stop the others and
   is reported at the end.
5. **After tracking:** each video becomes **"Not analyzed"**, like a loaded
   CSV, and the existing Analyze Selected/All step runs as now ("always wait
   for analyze"). Its `_LocationOutput.csv` and `_reference.png` are already
   saved.
6. **Tracking settings** (threshold, method, window, reference frame count,
   downsampling) **lock at the first Track** for the whole load and unlock at
   Clear, like test type, fps and bin size.
7. **Frame rate:** read from each video; warn before Track if it differs from
   the fps setting or from other videos in the load (option to continue);
   the rate used is recorded in the outputs.
8. **Unreadable-frame check kept as a warning, not a refusal**, when a video
   is added; the file list shows the % found, and the warning keeps ezTrack's
   suggestion to convert the video.
9. **`BatchSummary.csv` and the combined plot layout dropped** (no summary
   file, per the user; plots follow the selected file).

**⏸ Walkthrough — Freeze Analysis (recorded 2026-11-03; EXCLUDED from the
current build).** The user asked for these to be logged but **not built for
now**: the first video build is Location Tracking only. Nothing below goes
into the build order until the user brings it back. Any freezing hooks
mentioned elsewhere (e.g. FREEZING/ACTIVE in playback) are part of this
deferral.

ezTrack's module measures how much of the picture changes frame to frame (no
reference image). Functions: `LoadAndCrop` (same as Stage 1), `Measure_Motion`
(grayscale → downsample → crop → blur `SIGMA` → count pixels whose change >
`mt_cutoff` = the frame's Motion), `Measure_Freezing` (freezing = Motion below
`FreezeThresh` for ≥ `MinDuration` frames, back-filled to the bout start;
0/100 per frame), `SaveData` (`_FreezingOutput.csv`), `Summarize`,
`PlayVideo`/`PlayVideo_ext` (FREEZING/ACTIVE overlay), `Calibrate` (empty-arena
video; `mt_cutoff` = 2 × the 99.99th percentile of pixel change), and the
batch functions.

Problems found in ezTrack's code: stops at the first unreadable frame (and
drops a good one); the first frame can never be freezing; no exclusion shapes;
`FreezeThresh` is a pixel count (depends on resolution/downsampling/crop);
`MinDuration` is in frames (depends on fps); `Calibrate` ignores the crop.

Decisions (as recommended):
1. **Method kept as ezTrack's**, defaults `mt_cutoff` 10, `FreezeThresh` 200,
   `MinDuration` 15 frames, `SIGMA` 1; saved boxes that lock at Track. Only
   change to the math: fix the first-frame quirk.
2. **"Measure freezing" checkbox** (saved): measured in the **same pass
   through the video as tracking**; works for EPM and Open Field videos. New
   test type **"Freezing only"** (e.g. fear conditioning) skips tracking and
   regions.
3. **`<name>_FreezingOutput.csv` kept separate, in ezTrack's format**, plus a
   `Frame_Unreadable` column and all settings used; the loader joins it with
   `_LocationOutput.csv` by frame; reloadable without the video.
4. **Unreadable frames:** keep going, Motion blank, frame marked; a blank
   frame **breaks** a bout and is left out of the % freezing denominator.
5. **Stage 1 exclusion shapes also apply to motion** (addition to ezTrack).
6. **Units kept as ezTrack's** (pixels, frames) so thresholds match the
   published ones; each box shows its equivalent for the current video (e.g.
   "15 frames = 0.75 s"); warn if downsampling/crop changed since the
   thresholds were last used; all recorded in the export.
7. **Measures:** % time and total time freezing, bout count, mean and
   longest bout, latency to first freeze, mean Motion; in the Summary (new
   "Freezing" column group) and per time bin (bouts counted in the bin where
   they start).
8. **Freezing by region role** when both tracking and freezing ran (EPM open/
   closed/center; Open Field center/periphery).
9. **Freezing tab**: Motion over time, freezing shaded, threshold line;
   exported as `<name>_freezing.png`.
10. **Playback** (Stage 6 window): FREEZING/ACTIVE and current Motion, also in
    the optional saved video.
11. **`Calibrate` kept as an optional tool**: empty-arena video or a stretch
    with no animal; uses the crop; shows the histogram; suggested `mt_cutoff`
    to accept or ignore.
12. **Batch follows Stage 7** (one pass); `Summarize` dropped (our Summary and
    Time Bins replace it); `SaveData`'s file kept (item 3).

**Still to decide:** the details of the video windows (in the GUI review below).

**Last step of the planning, before building:** once every walkthrough stage
is decided, **review the GUI as a whole**: how the new video steps (load,
crop, reference, track, ROIs, scale, freeze, and ASR from §13) fit with the existing CSV
workflow, how windows, tabs, toolbars and settings are organized, and what
should be regrouped or simplified. Record the agreed layout here, then build.

**✅ GUI review (decided 2026-11-03; not built).** Problems found in the
current layout: the toolbar grows a row with each group of settings (three
rows already; tracking would add more, and the window's 940 px minimum width
comes from this); the file list is the Summary tab, so it's hidden on Time
Bins / Path / Heatmap; files can't be removed one at a time (only Clear);
greyed-out locked settings don't say why; there's nowhere for the GPL credits
and license ezTrack requires.
1. **Settings move to a left-hand panel** in sections: **Session** (Test,
   frame rate, bin size), **Entries and regions** (min entry, Regions…),
   **Open Field** (only for Open Field), **Tracking** (only when videos are
   listed). Each section shows a lock icon and "Locked. Clear to change."
   The toolbar becomes one row of buttons.
2. **File list always visible above the tabs**: File, Type (CSV / Video),
   Status, with a draggable divider between list and tabs. The **Summary
   tab** keeps the full table of measures.
3. **Status steps per file** with color tags: *Needs setup → Ready to track →
   Tracking 45% → Not analyzed → Analyzed*, plus *Failed* (with the reason).
   CSVs start at *Not analyzed*.
   **Changed 2026-11-04 (user, after C9):** buttons disappeared off the right
   of the toolbar in a narrow window. Of three mocked layouts (wrapping rows;
   two grouped rows; side panels) the user chose **side panels**: the Files
   (Add files / Add folder / Remove / Clear) and Run (Set up videos… / Select
   all / Track / Analyze / Export) buttons are full-width at the top of the
   left panel above the settings, About at its bottom; the panel scrolls
   (mouse wheel, scrollbar only when needed) when the window is short. The
   Path and Heatmap controls moved from a row above the plot to a **column
   on the right of the plot** (Points / Cells, then Show: Background, Region
   labels, Play video… at the bottom). New **Region labels** checkbox on
   both tabs (config `path_labels`, `heatmap_labels`; also in the Settings
   sheet) turns the region names on the plots on and off. The item below
   describes the original toolbar.
4. **Toolbar in working order:** Add files / Add folder / **Remove** / Clear |
   **Set up videos…** | **Select all** / **Track** / **Analyze** / **Export** |
   **About**. Set up videos… and Track show only when videos are listed.
   (Decided 2026-11-03 after mocking alternatives: separate Selected/All
   buttons, a shared "Apply to" dropdown, and per-button dropdowns were all
   considered; the user found "Apply to" unclear and chose this.)
   - **Track, Analyze and Export always act on the selected files**, and each
     button shows how many, e.g. **Analyze (1)**.
   - **Select all** selects every file in the list; once everything is
     selected it reads **Select none**. Ctrl+A (Windows) / Cmd+A (Mac) does
     the same.
   - With nothing selected, the buttons say "Select a file first" instead of
     doing nothing.
   - The first file added is selected automatically, so running one file at a
     time (the usual case for students) needs no extra clicks.
5. **Multi-select in the file list** (Shift-click, Ctrl/Cmd-click), so the
   buttons can act on a few chosen files.
6. **One video setup window** with a step list on the left (1 Trim and crop,
   2 Exclusions, 3 Reference, 4 Tracking check, 5 Regions, 6 Scale), each
   step's instructions above the image, Back / Next, a **video 2 of 3**
   switcher with arrows, **Start from previous video**, and a check mark on
   finished steps.
7. **Tracking settings are adjusted in step 4 (Tracking check)**, where their
   effect is visible, and shown in the main window's Tracking section. They
   are shared by every video in the load and lock at the first Track; step 4
   says they apply to all videos.
8. **Tracking progress in a bar at the bottom of the main window** with
   Cancel, not a pop-up, so the window stays usable.
9. **Path and Heatmap tabs** get the **Background** choice (Stage 6) and a
   **Play video…** button for the selected video. No new tabs for now.
10. **About button:** version, ezTrack credit and citation, and the GPL-3.0
    license text, as the license requires.
11. **Right-click menu on file rows** (Analyze, Export, Set up, Play video,
    Remove) as a shortcut, buttons kept; right-click or Control-click on
    Mac. Optional, low priority.
12. **Room for later:** freezing and ASR plug in as their own settings
    sections and tabs, shown by test type, without redoing this layout.

**Planning for the video build is complete.** Build started 2026-11-04.

**🔨 Video build progress (Location Tracking only; freezing and ASR excluded).**
Built in small chunks; **each chunk is committed and pushed when done** so the
work survives interruption (e.g. the laptop closing). A new session resumes at
the first unchecked chunk. Run `tests/regress_gui.py` (and the chunk's own
test) before each commit.
- [x] **C0. Groundwork:** OpenCV (`opencv-python-headless`), SciPy and Pillow
  in `requirements.txt` and `environment.yml`; GPL-3.0 `LICENSE`; ezTrack
  credit and citation in the README; this checklist.
- [x] **C1. Video reading (`core/video.py`):** open a video, report frame
  count / fps / size, read frame N as grayscale with downsampling and crop
  (ezTrack `LoadAndCrop` / `cropframe`), unreadable-frame check as a warning
  (`check_p_frames`), exclusion-shape mask from polygons (`Mask_select`).
  Built 2026-11-04, tested by `tests/test_video.py`. Notes: ezTrack's resize
  call actually uses bilinear interpolation (it passes `INTER_NEAREST` in the
  `dst` slot), kept for matching results; a run of unreadable frames at the
  very end of a video is dropped (files often report a few frames more than
  they hold), while unreadable frames before the end are kept as blank rows.
- [x] **C2. Tracking engine (`core/tracking.py`):** reference image
  (`Reference`, median of N evenly spaced frames, unreadable frames
  replaced), `locate` (`Locate` minus wire removal; window size scaled by
  downsampling), `track_video` generator (progress, cancel, unreadable frames
  kept as blank rows with `Frame_Unreadable`), region columns from polygons
  (`ROI_Location` etc., blank for unreadable frames; Open Field periphery =
  outline minus center), scale (`Distance_cm`), write
  `<name>_LocationOutput.csv` + `<name>_reference.png`. Validate on the
  practice video against `EPM.csv` (close, not identical: wire removal
  dropped).
  Built 2026-11-04, tested by `tests/test_video.py`. **Validation:** `EPM.csv`
  was tracked on a cropped frame (ezTrack coordinates start at the crop
  corner); the best-matching crop is (165, 5)–(745, 575). With it and the
  notebook settings, over the whole session: median position difference
  2.0 px (95th percentile 6 px); region membership agrees on 97.2–99.6% of
  frames per region; open-arm time 0.7% vs 1.4% (ol) and 5.9% vs 7.4% (or),
  closed and center within 0.7 points. The remaining difference fits the
  dropped wire removal and the unrecorded exclusion shapes and random
  reference frames. We keep one more row than ezTrack (it drops the last
  frame). Tracking speed: ~6,000 frames in 30–45 s on this Mac.
- [x] **C3. Analysis for unreadable frames:** loader treats `Frame_Unreadable`
  as a non-region column; unreadable frames add no time, distance or entries
  (entry rule carries the previous place through a gap); Summary and Time Bins
  report unreadable counts; plots skip them; optional gap filling (off by
  default, max gap saved, recorded in Settings).
  Built 2026-11-04, tested by `tests/test_unreadable.py` (gaps injected into
  both sample files: entries and crossings unchanged, time and distance
  reduced only by the gap). Gap filling lives in `core/gaps.py` (config
  `fill_gaps`, `fill_gaps_max_frames`; works on a copy, filled rows marked
  `Frame_Filled`); its on-screen control comes with the C4 settings panel.
  Summary gains `UnreadableFrames` (and `FilledFrames` when filling), in the
  Details group; Time Bins gain `UnreadableFrames`.
- [x] **C4. Main window re-layout (GUI review items 1–5, 10):** settings panel,
  file list above the tabs with Type and Status, Remove, Select all,
  Track/Analyze/Export on the selection with counts, multi-select, About
  (credits + GPL). CSV workflow unchanged; regression test updated.
  Built 2026-11-04 (`about.py` for the About window). The "Unreadable video
  frames" section (gap filling) appears only when a listed file has a
  `Frame_Unreadable` column. Set up videos… and Track buttons are added in
  C5/C7. Not yet checked by eye: screen capture isn't available to the
  assistant, so the user should look over the new layout.
- [x] **C5. Video setup window, steps 1–3:** trim (scrub), crop, exclusions,
  reference; video switcher; start from previous video; fps from the video.
  Built 2026-11-04: `setup_window.py` (window + drawing canvas),
  `core/video_setup.py` (each video's setup). Shapes are stored in full-size
  video pixels and converted at tracking time, so changing downsampling never
  invalidates them. Downsampling and reference frame count are shared
  settings (config `video_downsample`, `reference_frames`) that lock at the
  first Track. Videos join the file list as Video / "Needs setup"; adding a
  video with >1% unreadable frames asks "Add anyway / Skip". "Start from
  previous video" copies crop and exclusions as a draft (steps un-ticked).
  **Moved to C7:** filling the fps setting from the video and the fps
  mismatch warning (they belong with Track).
- [x] **C5b. Fixes from the user's first try of the setup window
  (2026-11-04; do these before C6):**
  1. **Start = time 0:** the start is set by scrubbing and becomes frame 0 of
     the analysis (as now; keep it).
  2. **End as a session length, not a scrubbed frame** (scrubbing isn't
     accurate enough for the end): Elevated Plus Maze defaults to **5 min**,
     with the option to scrub or type a different length; Open Field offers
     **1 hour** and **1.5 hours**, with the option to type another length.
     The end frame = start + length × the video's fps (clamped to the video's
     end, with a note if the video is shorter than the length).
  3. **Black border on all four sides** of every image drawn on (crop,
     exclusions, and C6's regions and scale), outside the video, so points
     can be placed past the edge and a zone reaches the video's edge.
     Currently there's only spare room left and right (from fitting the
     image), none above or below. Points outside the video are kept as
     placed (polygons are clipped to the frame when used).
  4. **Next is never a dead end:** every step's Next either moves on or says
     what's missing (e.g. "Make the reference first"). The user thought the
     program had stopped when Next was greyed out on the Reference step
     (steps 4–6 weren't built yet).
  Built 2026-11-04. Session length lives in each video's setup (`length_s`);
  the last length typed is remembered per test (config `session_minutes`, EPM
  5, Open Field 60); "Set end here" turns the scrubbed frame into a length.
  New videos start with the test's length. The black border is 40 screen px
  on every side. Next on the last step reads "Next video" (moves to the next
  video's step 1) or "Finish" (closes the window); the old Done button is now
  Close.
  **Fix (2026-11-04, from the user's try):** clicking Set end here with the
  slider still at the start made a one-frame trial, and the rounded length in
  the box (0.001 min) was then saved as the EPM default, so every reference,
  region image and tracking-check slider used only the start frame. Now a
  displayed length is never read back as a new one, a trial under 10 s asks
  first, lengths under 10 s are never remembered (a bad saved value falls back
  to 5 / 60 min), and the Reference step shows the trial length and warns if
  it's shorter than the frames used.
- [x] **C6. Setup steps 4–6:** tracking check (preview, scrub, settings),
  regions (draw/edit; EPM five regions, Open Field outline + center), scale
  (two points, guidance text, remembered length).
  Built 2026-11-04. **Tracking check:** scrub within the trial; red cross on
  the found position; Frame / Differences view (color map); window square
  shown (the 15 frames before are tracked first so the window has a last
  position, as in a real run); settings boxes (animal dark/light/abs,
  threshold %, window on/size/weight) saved to config (`track_method`,
  `loc_thresh`, `use_window`, `window_size`, `window_weight`) and locked at
  the first Track; the main window gains a read-only **Tracking** section
  summarizing them. **Regions:** list of the test's regions (EPM: open arm 1/2,
  closed arm 1/2, center; Open Field: arena outline, center), drawn on the
  reference; after closing one the next undrawn region is picked; drag points
  to move them; Redraw / Undo point / Delete / Rename / Add region (role set
  with Regions… in the main window); warning if the Open Field center goes
  outside the outline. Tracking writes the outline as "periphery" minus the
  center. Names auto-classify to roles. **Scale:** two points (drag to adjust;
  a third click starts again), live px length and cm per pixel, measured on
  the prepared frame; cm remembered per test (config `scale_cm`, 75 / 40).
  Regions and scale may be skipped after a yes/no; a video whose six steps
  are all done shows **Ready to track**. "Start from previous video" now also
  copies regions, scale and session length.
  **Added 2026-11-04 (user's request after trying regions):**
  - **Points lock onto each other** so neighboring regions share a border
    instead of overlapping: a region point placed or dragged within 10 screen
    px of another region's point lands exactly on it (else on the nearest
    edge within 10 px); a white ring shows where it will lock. Points at the
    same place move together when dragged. A checkbox ("Lock onto other
    regions' points and edges", on by default) turns this off, which also
    lets a locked point be moved on its own. A press on a point drags it
    only if the mouse moves; a plain click places a new locked point there.
  - **Zoom on every image drawn on** (all setup steps): mouse wheel /
    trackpad scroll zooms at the pointer (up to 16x), − / + / Fit buttons
    above the image; when zoomed, right-drag, Control-drag or the arrow keys
    move around. Only the visible part of the image is scaled, so high zoom
    stays fast; pixels show sharp from 4x.
- [x] **C7. Tracking runs:** Track on the selection in a background thread,
  bottom progress bar with Cancel, status steps, existing-tracking prompt,
  settings lock at first Track, fps mismatch warning, results loaded as
  "Not analyzed".
  Built 2026-11-04. `core/track_run.py` (GUI-free): `make_job` snapshots a
  video's setup when Track is clicked (editing a setup during a run can't
  change a queued video); `TrackRunner` tracks the jobs one at a time on a
  daemon thread and reports through a queue that the main window polls, so
  tkinter is only touched on the main thread. The setup window's reference is
  reused when current, else the run makes one ("Making reference" status).
  Main window: **Track (n)** button (videos only, shown while videos are
  listed); bottom bar "Tracking video 2 of 3: name, 45%" with a progress bar
  and Cancel; statuses Waiting to track → Making reference → Tracking 45% →
  Not analyzed, or Failed (reason listed at the end; the other videos carry
  on). Before a run: an existing `_LocationOutput.csv` asks once **Use
  Existing Tracking** / Track Again; videos not fully set up are skipped and
  named; missing regions or scale asks Track Anyway / Cancel; frame rate:
  if the videos share one rate that differs from the setting, offers "Use
  N fps" (fills the setting), or Track Anyway when the analysis is locked;
  different rates between videos ask Track Anyway / Cancel. Tracking settings
  lock from the moment Track starts; Clear, Remove and Track are disabled
  during a run; closing the app mid-run asks first. A video added twice is
  tracked once and every copy gets the result.
- [x] **C8. Plots and playback:** reference-image background for Path and
  Heatmap; playback window; optional `<name>_tracked.avi`.
  Built 2026-11-04. **Backgrounds:** Path tab "Background: None / Reference
  image"; Heatmap tab "Background: None / Flat color / Reference image"
  (replaces the Add background checkbox; old configs with it on become Flat
  color). Saved in config (`path_background`, `heatmap_bg_mode`). The
  reference is `<name>_reference.png` beside a `<name>_LocationOutput.csv`,
  so CSVs tracked earlier in this app get it too; files without one show
  "(this file has no reference image)" and draw without it. On the
  reference: gray image in the same pixels as X/Y, ROI lines yellow, the
  whole image shown, exported PNG not transparent; heatmap labels get a
  white box. The Settings sheet's "Add background" is now "Background".
  **Playback** (`playback_window.py`, `core/playback.py`): **Play video…** on
  the Path and Heatmap tabs, for any tracked file whose video is beside it
  (File column) and that records its crop/downsampling (ezTrack's own CSVs
  don't, so they're refused with the reason). Color frames prepared like
  tracking's (downsample, crop); play/pause (space), frame steps, slider,
  speed 0.25x–8x (frames skipped to keep time), red marker, 1 s trail,
  region outlines, zoom/pan (the setup window's canvas); info line: frame,
  time, video frame, region, or "unreadable frame (no position)".
  **Save as video…** writes **`<name>_tracked.mp4`** (changed from `.avi`:
  QuickTime can't open AVI; OpenCV's MPEG-4 `mp4v` writes on Mac and
  Windows and plays in QuickTime and Windows' player) at the video's real
  frame rate, with the marker, trail and regions as shown and time/region
  text, in the background with Cancel; a cancelled save is deleted.
- [x] **C9. Finish:** exported Settings sheet gains tracking/scale/crop
  settings; README and INSTALL updates; PC test checklist.
  Built 2026-11-04. The Settings sheet's "Tracking (from file)" raw columns
  became **"Tracking (recorded in the file)"** with readable names (animal
  dark/light/abs, threshold, window on/size/weight, downsampling, crop,
  reference frames, exclusion shapes, start frame, video fps, scale px / cm /
  cm per pixel, frames, unreadable frames; unknown columns kept as-is), plus
  a **"Video"** section for videos tracked in the load (video file, frame
  size, length, session start and length, regions drawn, tracking file).
  README: a "Tracking videos" section, Background choices, export contents,
  layout. INSTALL: troubleshooting for unreadable videos and unsaveable
  folders. PC checklist: §10, "PC test checklist, video tracking".
  **Location Tracking is complete**; next steps come from the user (PC test,
  merging `video-tracking` into `main`, Freeze Analysis, ASR).

### 13. Acoustic startle response (ASR) from video (requested 2026-11-03 — built 2026-11-09; see the end of this section)

Measure the startle response from video with a **motion index**, following a
method described in a paper the user supplied. **The user cites papers
outside the app**, so no citation is added in the app or exports for this.

**⏰ Reminder when ASR work starts:** remind the user to put a **sample ASR
video and its stimulus logs** into the project folder (gitignored like the
CSVs) before building.

**The method as described:**
- Videos are recorded at **30 fps**.
- For each pair of successive frames, subtract the later image from the
  earlier one; every pixel whose intensity changed is a candidate, from tiny
  changes (0 → 1) to large ones (0 → 255 and back).
- A **pixel intensity threshold** separates noise from movement: changes
  below it are noise, changes above it are the animal's movement. The paper
  chose **15** by manual inspection and trials.
- **Motion index** for a frame = above-threshold pixels ÷ total pixels in
  the frame, as a **percentage**.
- Sensitive to slight movements (a small head lift, minor limb movement), not
  to ultra-fine ones like breathing; suited to gross startle movements.
- **The ASR value is the maximum motion index** within the response period
  (the paper's wording, "computed between two frames", is read as the peak
  between the start and end frames of the response window; accepted by the
  user 2026-11-03).

**Plan:**
1. **Motion index engine** (`core/asr.py`, GUI-free): read each frame, convert
   to grayscale, absolute difference from the previous frame, count pixels
   whose change is above the threshold, divide by the pixels analyzed, ×100.
   Per frame, record the motion index (%), the above-threshold pixel count
   and the total pixel count. The first frame has no predecessor and is left
   blank.
   - This is the same frame-differencing idea as ezTrack's freezing
     `Measure_Motion` (§12, deferred). Share the reading/differencing code if
     freezing is built later, but ASR follows the paper: no blur by default,
     output as a percentage of pixels, threshold 15.
2. **Adjustable intensity threshold (required):**
   - A **threshold scale (slider) from 0 to 255 paired with an input box**,
     default **15**, saved to `config.json`, locked at Analyze like other
     settings, recorded in the export.
   - **Live preview**: pick any frame (scrub slider) and see that frame
     pair's difference image with **above-threshold pixels highlighted** in
     color over the frame, plus the resulting motion index, updating as the
     slider moves. A second view can show a histogram of pixel changes with
     the threshold marked, to see where noise ends.
   - Optional **noise check**: on a stretch where the animal is still, show
     what share of pixels exceed the threshold (should be near 0%).
3. **Area analyzed:** whole frame by default (as in the paper). Optional crop
   to the animal's enclosure and exclusion shapes (reuse §12 Stage 1 tools)
   so lights, timestamps or the chamber edge don't count; the percentage is
   then out of the **analyzed** pixels. The choice and pixel count are
   recorded, since they change the scale of the index.
4. **Frame rate:** read from the video; warn if it isn't 30 fps (the method
   and threshold were set at 30 fps). Note: at 30 fps one frame is 33 ms, so
   startle latency (onset often within ~10–20 ms in rodents) can only be
   resolved to the nearest frame.
5. **Trials and the response window:** ASR is measured per startle stimulus,
   so the app needs each stimulus's time. **Open question** (how stimulus
   times are known):
   - typed in or loaded from a file (e.g. the startle system's trial log:
     onset time, trial type);
   - a fixed schedule (first onset + interval);
   - or detected from the video (e.g. a cue light) or its audio track.
   For each trial: a **response window** after onset (start and length,
   saved settings) and an optional **baseline window** before onset.
6. **Per-trial measures:** **peak (maximum) motion index** in the response
   window (the ASR value), frame/latency of the peak, mean motion index in the
   window, baseline motion index, and peak minus baseline. Flag trials where
   the animal was already moving at baseline (above a saved level), and
   trials with unreadable frames in the window.
7. **Session measures (decided 2026-11-03: measure both PPI and
   habituation):**
   - mean and median ASR across trials, per trial type;
   - **Prepulse inhibition (PPI):** %PPI = 100 × (1 − mean prepulse+pulse ASR
     ÷ mean pulse-alone ASR), per prepulse level and overall;
   - **Habituation:** ASR across the session by trial number and by block
     (block size a saved setting), e.g. first block vs last block and %
     habituation = 100 × (1 − last-block ASR ÷ first-block ASR), plus the
     trial-by-trial trend;
   - trial types (pulse alone, prepulse + pulse at each level, no-stimulus)
     come from the stimulus log; details settled once the sample logs are in
     the folder.
8. **Unreadable frames:** same rule as §12 — keep going, leave the motion
   index blank, mark the frame (`Frame_Unreadable`), report the count.
9. **Outputs** (next to the video, overwriting, like other exports):
   - `<name>_MotionIndex.csv`: one row per frame (Frame, Time_s,
     MotionIndex_pct, AboveThreshold_px, Total_px, Frame_Unreadable, and the
     settings), so a video only needs processing once and can be reloaded;
   - `<name>_ASR_analysis.xlsx`: Trials, Summary and Settings sheets;
   - `<name>_ASR.png`: motion index over time with stimulus onsets and
     response windows marked, plus a plot of all trials' traces aligned to
     onset.
10. **GUI:** a new test type **"Acoustic startle (ASR)"**, with its own
    settings row (threshold scale, response window, baseline window, trial
    source) and tabs (motion trace, trials table, threshold preview). Video
    files are added and batched like §12 Stage 7. Exact placement is part of
    the GUI review.
11. **Validation:** check against a video the user has already scored by
    hand or with the paper's method; confirm the threshold-15 result and the
    peak values match.

**Still open (to settle from the sample video and logs):**
- How stimulus onset times and trial types are read from the logs (item 5),
  and the default response/baseline window lengths.
- PPI and habituation details that depend on the log format (prepulse
  levels, block structure).

**Built 2026-11-09** (`core/asr.py`, setup steps Threshold and Stimuli, tabs
Trials / Motion Trace / Aligned Trials; tests `test_asr.py`, `test_asr_gui.py`).
**Decided with the user, from their document and Boom Box 1.1's
`TRACK_TAMER_DATA.md`:**
- **Startle amplitude = peak motion index in the startle window (200 ms after
  the stimulus) - peak in the baseline window (200 ms before).** On
  prepulse+pulse trials the baseline ends at the prepulse onset.
- Motion index at frame k belongs to frame k's time, so the startle window
  is the frames after the stimulus. Windows run on measured times
  (`_frames.csv`, stimulus `video_time_s`). Repeated frames can't be a peak.
  The Summary counts them (`RepeatedFrames`), and Analyze warns when more
  than half of a video's frames are repeats, with the share and the real
  frames a second (user, 2026-11-11: Boom Box on a Mac before 1.3.4 really
  recorded 10 frames a second at 1280x720, so about 2 of every 3 frames are
  repeats and a 200 ms window holds only about 2 real frames).
- Output headings from the document: Pixel.change, motion.index.after, FrameNo,
  Time.startle, ReactionTime (ms, stimulus to peak), Startle amplitude; plus
  motion.index.before. **Direction left out** until its meaning is known.
- PPI and habituation use the startle amplitude. Means per trial type and
  per pulse frequency; `pulse_freq_hz` and `pulse_stimulus` added to the
  standard, read from `boom_box.trials` until Boom Box writes them in `stimuli`.
- Stimuli from the info file, or typed video frames (treated as pulses).
- **Startle by sound level (decided and built 2026-11-11)**, for sessions
  whose pulse-alone trials step through levels (Boom Box's Hearing Test and
  I/O). Decided with the user:
  - The **mean and count of startle amplitude at each dB level**
    (`ASR_Mean_pulse_70dB`, `ASR_N_pulse_70dB`), only when a session uses
    more than one level (a fixed-level session would just repeat its
    overall mean).
  - **Startle threshold** (`ASR_Threshold_dB`): the lowest level from which
    that level and every louder one gives a response. A level responds
    when its mean startle-window peak is above the mean of every trial's
    baseline-window peak plus 2 SD of them (`ASR_ThresholdCriterion_pct`);
    the 2 is the "Threshold criterion (SD)" box, which locks at Analyze.
    Blank when the loudest level doesn't respond.
  - **Maximum response** (`ASR_Max_pulse`, `ASR_Max_pulse_dB`): the largest
    level mean and its level. No slope.
  - **No-stimulus trials stay their own column** beside the levels
    (`ASR_Mean_none`); nothing is subtracted.
  - **Frequency and level both varying**: a mean for each pair
    (`ASR_Mean_pulse_8kHz_90dB`) as well as each alone; the threshold and
    maximum are then per sound (`ASR_Threshold_8kHz_dB`), since pooling
    different sounds would mix their curves.
  - A third plot, the **Startle by Level** tab: mean ± SEM against dB, one
    line per sound, the no-stimulus mean dashed, each threshold marked;
    exported as `<name>_levels.png`.
  - Sounds are listed by rising frequency, then noise (was alphabetical).
  - **Habituation is untouched for now**: the user has more calculations
    for it to come. Until then its blocks still run across every
    pulse-alone trial in order, which means little for a session that
    steps through levels.
  `core/asr.py` (`level_curves`, `baseline_criterion`, `startle_threshold`,
  `level_measures`), `plotting.level_figure`.
- **First check against a real Boom Box session (2026-11-12).** The user
  ran a Hearing Test with no animal (Boom Box 1.3.7; `Examples/2026-11-12_
  08-35-47_ASR1_mic-test`) to check the fields Track Tamer writes. The
  fields matched Boom Box's data: 36 trials for 36 stimuli, frame times from
  its frame file, the same 8 repeated frames in all three files, every
  sound's time inside its labelled frame. Two things in the recording:
  - **Compression bursts: Track Tamer is to stay aware of these.** Every
    250th frame (the video's keyframe, every 8.33 s) shows about 1.4% of
    pixels changing by more than 5 grey levels (session median 0.02%); all
    104 such frames, 104 of the session's 120 largest motion values. It fell
    in the windows of 7 of the 36 trials and gave false amplitudes of about
    ±1.4. The threshold had been set to 5; at the default 15 the burst is
    about 0.03 to 0.04%. Passed to Boom Box (user). **Nothing is changed in
    how Track Tamer measures for now** (user: "keep track tamer aware of the
    compression issues and we will see what happens when a mouse is added to
    the box"). If it still matters with an animal: leave keyframes out of
    the peaks as repeated frames are, and warn at low thresholds.
    **Boom Box 1.3.9 (reported 2026-11-12) records without those
    keyframes** (`camera_settings.encoder_params` is `intra-refresh=1`);
    videos from before it keep them (standard, Boom Box section).
  - Frame times are uneven (332 gaps over 50 ms, 40 under 10 ms, one
    repeated frame 3 ms earlier than the frame before). Track Tamer copes;
    reaction times carry up to about 30 ms of noise. Not passed on (the
    user didn't ask for it).
- **Changes from that check (user, 2026-11-12):**
  - The Summary is called **Data Summary** (the tab and the workbook sheet,
    for every test).
  - **Units on every column heading.** Startle: amplitudes, means, medians
    and the largest response end `_pct` (% of pixels); the Trials headings
    are `Pixel.change_px`, `motion.index.before_pct`, `motion.index.after_
    pct`, `Time.startle_s`, `ReactionTime_ms`, `Startle amplitude_pct`;
    `AnalyzedPixels_px`, `IntensityThreshold_graylevels`. A test checks
    that every exported heading of every test carries a unit or is a count,
    a ratio or a label (`tests/test_units.py`).
  - **The Trials table has the prepulse headings (`Prepulse_dB`,
    `Interval_ms`) only when the session has prepulse trials.**
  - **Habituation only for a habituation session** (the info file's variant
    is `Startle Habituation`), and called **short-term habituation**
    (`ASR_ShortTermHabituation_pct`, `..._Block1_Mean_pct`): within one
    session; across days is worked out outside the app for now. More
    calculations for it are to come from the user.
  - Frequency columns stay even with one frequency (user: fine to have both).
  - In the info file the startle images are named `trace` and `aligned`
    (they were under `path` and `heatmap`).
  - **Exclusion shapes are trimmed to the video frame** when drawn (and when
    an older setup is restored): it's easier to draw past the edge to cover
    everything (`video_setup.clip_to_frame`).
  - The Settings sheet lists repeated frames once (not again under Camera).
  - **Startle has no crop and no exclusions; the motion index is always of
    the whole frame** (user, 2026-11-12, with the first data from an animal:
    "take out the cropping part of the program. The motion index is
    calculated from a division involving total pixels so cropping will
    change that calculation unevenly depending on where you crop it. also
    take out exclusion drawing for startle for the same reason"). The
    startle setup then had three steps: Trim, Threshold, Stimuli
    (`video_setup.ASR_STEPS`; two since the Stimuli step went, below); a crop or exclusions a setup holds from
    another test are not used, saved or recorded (`asr.make_asr_job`), and
    the Setup sheet has no Crop or Exclusions section. Files tracked with
    them in 0.9.4 or earlier still load, and Analyze names them
    (`asr.part_of_frame`, `gui._warn_part_of_frame`): their index is a share
    of the part kept, so they need tracking again before they're compared.
    Location tests keep their crop and exclusions (they find a position;
    nothing is divided by the pixel count).
  - **Short-term habituation score** (user, 2026-11-12: "long term
    habitation will not be calculated in this app at the moment. For short
    term habituation you can write a score for the habituation varient .STH
    was calculated as difference between mean first 10 and mean last 40
    responses divided by the mean of all responses on the respective day").
    For a habituation session (info file variant `Startle Habituation`):
    `ASR_STH_Score` = (`ASR_STH_First10_Mean_pct` −
    `ASR_STH_Last40_Mean_pct`) ÷ `ASR_Mean_pulse_pct`, the responses being
    the pulse-alone trials' startle amplitudes in order, worked out from the
    means as shown. Above 0 = the startle got smaller. Blank with fewer
    than first + last responses. The 10 and 40 are settings boxes
    (`asr_sth_first`, `asr_sth_last`). "On the respective day" is read as
    the session the video holds (one file, one row).
    **It replaces** the earlier `ASR_ShortTermHabituation_pct` (100 × (1 −
    last block's mean ÷ first block's)), which was a stand-in until the
    user's calculation came. The per-block means the user asked about ("the
    'block calculation' in the sheet") are kept as the **habituation
    curve**, renamed so the sheet says what they are:
    `ASR_Habituation_Responses1to10_Mean_pct`, `11to20`, … (the mean of each
    run of `asr_block_trials` responses in order; not part of the score).
    Asked of the user: whether to keep the curve at all.
  - **The metadata standard is final** (user, 2026-11-12: "finalized the
    meta data sheet"). `docs/metadata_standard.md` is schema 1, final, as it
    stood that day; no field changed. From here an optional field, assay,
    variant or phase can be added without a new version, and a rename,
    removal or change of meaning makes schema 2 (which Track Tamer must
    then read alongside schema 1). `room` stays as an optional field no app
    needs to write. Creature Capture, Boom Box and Pellet Paparazzi were
    told.
  - **No Stimuli step** (user, 2026-11-12: "in the video set up panel there
    is a step for stimulus which doesn't do anything"; then "You can remove
    it"). With a Boom Box info file the step only reported how many stimuli
    it had found; the box for typing frames was for videos with no info
    file, and every startle video now comes from Boom Box. The startle
    setup is **Trim, Threshold**. The Threshold step says where the stimuli
    come from (`asr.stimulus_note`), in red when there are none; Track
    names videos with no stimuli and asks before working out a motion index
    with no trials. Frames typed in 0.9.4 or earlier, kept in a saved
    setup, are still used. Nothing in Track Tamer types stimuli now.
  - **Marking each startle real or not: built, then taken out the same day**
    (2026-11-12). The user asked for Yes / No buttons in the playback window
    to mark whether each startle was real (not a mouse already rearing or
    moving when the sound came), saved at each click, with a Done button and
    a written guide; trials marked No were left out of every result. It
    went out in commit 93e7ed9. After trying it on the first data from an
    animal the user took it back: "I think that the manual review of rating
    a startle yes or no isn't going to work. The data is too subjective.
    Revert that change." All of it is gone: the buttons, the `Startle_Real`
    column, the `ASR_TrialsMarkedNotReal` / `ASR_TrialsNotReviewed` /
    `ASR_ReviewDone` columns, and the guide. An info file that was reviewed
    in that build keeps a `startle_review` entry in its `track_tamer`
    object; nothing reads it. **Don't bring a per-trial human judgment back
    without the user asking**; if movement before the stimulus needs
    handling, it should be by a rule the data decides (for example a limit
    on the baseline window's motion index), which the user hasn't asked for.
  - **A startle setup holds only what startle uses** (user, 2026-11-12): the
    session and typed stimulus frames (the crop and exclusions went the
    same day, above). No regions, scale,
    objects or trial day in the info file's saved setup
    (`VideoSetup.to_saved(test)`), and no "Regions: none" or "Scale: none"
    rows on the Setup sheet (`export.setup_sections(startle=True)`). The
    (The trial day was taken out with them at first; that was wrong and
    is undone, next item.)
  - **The trial day and session are the trial's, whatever the test** (user,
    2026-11-12: "startle does have multi days of trial so it needs to have
    the information that is reported from boom box", then "make sure that
    track tamer is in alignment with the meta data being produced from the
    other apps"). Taking the trial day out of the startle setup that
    morning, and filling it only for object trials, treated a standard
    field as one test's; both are undone. The rule, checked field by field
    against Creature Capture's and Boom Box's writers (both write
    `trial_day` and `session_number` for every assay, and the same 24 log
    columns): **Track Tamer never handles a standard field for one test
    only.**
    - Every test's Data Summary row starts File, `animal_id`, `trial_day`,
      `session_number` (the standard's names; blank when the info file
      doesn't say, never left out), on screen as soon as a file is added and
      in the workbook (`info.with_animal`, `info.DAY_COLUMNS`). An object
      trial shows the day in use (the experimenter can correct it), so a
      row never shows two days.
    - Every test's saved setup keeps `trial_day` and `trial_phase`. Outside
      Object Recognition the day can't be set in Track Tamer, so the
      setup's copy always follows the info file (`info.follow_day`,
      `gui._follow_day`), and a change of day alone isn't taken for a new
      setup.
    - `session_number` can be typed for a video with no info file (Animal
      information), next to the trial day.
    - An error the recording app reported is listed on the Settings sheet
      (it was only a warning on screen).
    - The standard's section 4 now says where each field goes as built.
    - **`OR_Day` is gone** (user, 2026-11-12: "Keep trial day and drop OR
      day"): an object trial's day is in `trial_day` like every test's, and
      it is the day set in Track Tamer (`objects.trial_summary`,
      `gui._own_day`). `OR_Phase` is unchanged (the user wasn't asked to
      rename it and didn't).
    - Decided the same day, nothing to build: every startle video comes
      from Boom Box, so there is no need to mark a habituation session by
      hand ("there won't be a startle video without boom box"); the lab has
      no room to record ("There is no room"), so `room` is shown nowhere.
      `room` is still a field in the standard and a setting in Boom Box;
      taking it out of both is the user's call.
    - Creature Capture and Pellet Paparazzi were told to refresh their
      copies of the standard (both were behind).
  - **Each group's columns sit together in every exported table** ("pulse
    mean, pulse n, etc."): `metrics.group_together`. Startle: each trial
    type's count, mean and median, then per sound, per level, the threshold
    and largest response, PPI, short-term habituation. Location tests: a
    key measure is followed by the other numbers about the same thing (the
    plus maze's ratios; center; open arms; closed arms), each region's time,
    percent and entries together, each object's numbers together. **This
    changes the 2026-11-05 export order** (key measures first as one block);
    the on-screen Key measures view is unchanged.
  - **One name for the analysis file in every test**: `<video name>_
    analysis.xlsx`, whether the video or its tracking file was added (a
    tracking file used to give `<name>_LocationOutput_analysis.xlsx`). The
    workbook stays an Excel file with its tabs (the user considered CSV and
    kept the workbook: "keep ... so that multiple tabs can be saved. Makes
    this the standard").
- The threshold locks at the first Track; the windows and block size lock at
  Analyze. Always full size (no downsampling). The whole video by default.
**Checked:** the five paper clips (101 frames, 30 fps; stimulus frame 50
assumed, since they carry no stimulus information): the peak falls 1-2 frames
after it in every clip. The paper's own values aren't available to compare.
**Not built yet:** flag for animals already moving at baseline; histogram and
noise check in the threshold step; editing stimuli without re-running;
Direction. **Added (user, 2026-11-09):** the Review tab lists the startles;
clicking one opens the playback window at its stimulus, which has Previous /
Next trial, Go to stimulus and Go to peak, and marks the stimulus and peak
frames on the video. **Waiting on:** real chamber videos (validation,
window and threshold choices).

### 14. Anaconda install (requested 2026-11-03 — ✅ built 2026-11-03 on `main`, merged into `video-tracking`)

Goal: anyone with **Anaconda or Miniconda** on a Mac or Windows PC gets the
project folder, double-clicks **one install file** to build the program's
environment, then double-clicks the **Open** file from then on. Build it on
`main` and merge into `video-tracking`, so the installer is usable now and
later packages (OpenCV, SciPy for video) are one line each.

1. **`environment.yml`** (Anaconda's own format):
   - **conda-forge channel only** (not Anaconda's default channel, whose
     commercial terms can apply to larger institutions; conda-forge is free).
   - One fixed Python version; pandas, numpy, matplotlib, openpyxl; OpenCV and
     SciPy added when the video build needs them; `tkinterdnd2` through the
     file's `pip:` section (may not be on conda-forge).
   - One named environment, e.g. `behavior-tracker`, separate from anything
     else on the computer.
2. **Conda-finding helpers, one per system**, shared by the Install, Open and
   Uninstall files so the search lives in one place:
   - **`find_conda.sh` (Mac):** use `conda` if it already works or
     `CONDA_EXE` is set; otherwise look in the usual install folders
     (`anaconda3` / `miniconda3` in the home folder, `~/opt`, `/opt`,
     `/opt/homebrew`, …); then load `etc/profile.d/conda.sh` so
     `conda activate` works inside the script.
   - **`find_conda.bat` (Windows):** same idea in Windows terms (`where
     conda`, `%CONDA_EXE%`, `anaconda3` / `miniconda3` under
     `%USERPROFILE%`, `%ProgramData%` and `%LOCALAPPDATA%`, …); activate
     through `condabin\conda.bat`.
   - If nothing is found: a plain message saying Anaconda needs installing,
     then stop.
   - If the user copies the `find_conda.sh` from their other program into the
     folder, reuse what worked there (e.g. extra folders it checked).
   - Also searched: Miniforge/Mambaforge and Homebrew cask folders (Mac), and
     the older `%LOCALAPPDATA%\Continuum` location (Windows).
3. **Install files:** `Install Behavior Tracker.command` (Mac) and
   `Install Behavior Tracker.bat` (Windows). First run creates the
   environment from `environment.yml`; running again **updates** it to match
   (how new packages arrive later). **Never upgrades pip.** Ends with a clear
   Done/Failed message and keeps the window open.
4. **Open files** (the existing `Open Behavior Tracker` launchers): use the
   conda environment if it exists (on Windows, activate it properly first, or
   numpy can fail to load); **fall back to the current `.venv` setup** on
   computers without Anaconda; if the environment is missing, say "run the
   installer first" instead of crashing; if `environment.yml` changed since
   install (stored stamp), suggest re-running the installer.
5. **Optional Uninstall file:** `conda env remove` for the environment; the
   user's files are untouched.
6. **Keep `requirements.txt` (venv fallback) and `environment.yml` in sync**;
   the regression test fails if they list different packages.
7. **README:** install Anaconda; get the folder (zip from GitHub or clone; the
   repo is private, so others need access or a zip); double-click Install,
   then Open; Mac first time: right-click → Open (macOS blocks downloaded
   scripts); what to do if Windows SmartScreen warns.
8. **PC test checklist:** installer finds Anaconda installed "just me" and
   "all users"; works from a folder with spaces; re-running updates; Open
   uses the conda environment; drag-and-drop still works.

**Built as planned.** Notes: `tkinterdnd2` isn't on conda-forge, so it comes
through `environment.yml`'s `pip:` section; Python is pinned to 3.12; the
"changed since install" check compares `environment.yml` with a copy the
installer leaves inside the environment; with Anaconda present but the
environment not installed, Open still uses an existing `.venv` (so current
setups keep working) and otherwise says to run the installer.

New requests are added to this list as they come in.

---

### 15. Object recognition (requested 2026-11-05, on `video-tracking`)
Semi-automated novel object recognition / spatial object recognition
scoring from video.
**Decided (user, 2026-11-05):**
- New test type **Object Recognition**. Trim, crop, exclusions, reference,
  tracking check and scale work as usual.
- **Objects are circles**: in setup step 5 (named "Objects" for this test),
  press at the object's center and drag the radius out to its edge.
  **Two objects by default** (object 1, object 2); more only appear when the
  experimenter clicks **Add object**.
- Each object is marked **Familiar, Novel or Moved**. Each video records the
  trial **day** (number) and **phase** (Habituation / Training / Test).
- The app draws a **zone** around each object at a set distance from its
  edge: **Zone distance (cm)**, a type-in box (value TBD while the user
  experiments, so it never locks; default 2 cm). Zones are worked out from
  X/Y at analysis, so changing the distance needs no re-tracking.
- **Review tab**: every stretch the tracked point spends within a zone
  (object, first frame, session and video time, length, scored status).
  Clicking one opens the playback window at the frame the point first
  enters the zone.
- **Manual scoring in the playback window**: the experimenter scrolls
  through and logs the **start and end of an interaction** with an object,
  or marks a zone visit as **no interaction**. Interactions can be logged
  **anywhere in the video** (the object is picked from the zone the point
  is in, or chosen by hand). Scoring is saved as it's made, to
  `<name>_ObjectScoring.csv` beside the tracking file.
- **Results**: time interacting with each object, number of interactions
  (bouts) per object, latency to the first interaction per object,
  **discrimination index** = (novel − familiar) / (novel + familiar)
  interaction time, and **% preference** = novel / (novel + familiar) x 100
  ("novel" = objects marked Novel or Moved; blank when there's none, e.g.
  training). Also automatic zone time and zone visits per object, and the
  day, phase and novel object(s).

**Build plan:**
- O1: core (`core/objects.py`): objects in the tracking file, zones, zone
  visits, scoring file, results; test type; tests.
- O2: setup window: draw circles, object types, add object, day, phase,
  zone rings; Track writes the objects and trial info into the tracking file.
- O3: Review tab and playback window scoring.
- O4: Analyze / Summary / Time Bins / export, objects and zones on the
  plots; docs.

**Built 2026-11-05 (O1–O4).** `core/objects.py` (objects, zones, visits,
`Scoring`, `object_metrics`, `trial_summary`); setup step 5 becomes
"Objects" for this test; tracking files gain `Objects` (JSON circles in the
file's pixels, with type), `Trial_Day`, `Trial_Phase`; zone visits use the
entry rule (Min entry frames) so boundary jitter doesn't split them; bouts
with the same object that overlap or touch are joined; the playback window
gets a **Score interactions** panel (object follows the zone the point is
in; S / E / N keys; logged list with Delete; per-object totals); results
update as scoring is saved, and when the zone distance changes. Summary
key measures: day, phase, novel object(s), DI, % preference, total, then
per-object time, bouts, latency. Time Bins: interaction time, bouts and
zone time per bin. Export: Interactions sheet. Path / Heatmap draw the
objects and zones. No outside-region review for this test (no regions).
Tested on the user's object trial (`examples/1_2026-06-26_14-03-15.mp4`,
640x480, 9.84 fps, mouse placed about frame 320): with a 2 cm zone, 18 zone
visits (8 at object 1, 10 at object 2). The tracked point is the body
center, so while sniffing it sits a few cm from the object; a larger zone
may suit (to settle by experimenting).
**Changes (user, 2026-11-05, after reviewing the trial):** the playback
window gets **◀ Previous visit / Next visit ▶** (keys [ and ]), so the
experimenter works through the zone visits without going back to the list
(the list's selection follows; moving is refused while an interaction is
open). **Default zone distance 4 cm** (from the interactions the user
saw). The aim is to **catch every possible interaction**, with the
experimenter deciding which are real, so zone visits **no longer drop
brief stays** (the entry rule had dropped stays under 5 frames); only exits
shorter than Min entry frames join two stretches into one visit. On the
trial: 67 visits at 4 cm (37 at object 1, 30 at object 2).
**Built 2026-11-09:** **Edit trial info…** (Review tab, Object Recognition)
changes each object's type, the trial day and the phase after tracking.
Saved in the tracking file (`update_trial_info`: only the `Objects`,
`Trial_Day` and `Trial_Phase` columns change, every other value is written
back as read, via a temporary file so a failed save, e.g. the file open in
Excel, changes nothing). The video's setup follows, so tracking again keeps
the edit; results update at once; already-exported files need exporting
again. **Save as video…** draws the objects, dashed zones (heavier while the
point is in one) and labels on `_tracked.mp4`, following the Objects
checkbox and the current zone distance.
**Possible follow-up (not built):** draw the objects on the Scale step.

### 16. Experiment information from the capture software (requested 2026-11-05; after 1.0)
The user is writing capture software that records the videos. It will write
a JSON file beside each video (`<video name>.json`) with the experiment
information, and Track Tamer reads it when the video is added, filling in
what it can. **Not before 1.0** (the user's order). Draft field list, for the
user to hand to the capture-software project:
**[docs/metadata_standard.md](docs/metadata_standard.md)** (schema 1).
What it would fill in automatically:
- **Test type** (and a warning when videos in one load differ).
- **Frame rate** from the measured rate; **dropped frames** marked like
  unreadable frames so timing stays right.
- The **session length** from the planned duration. (The trial start stays
  a setup step: an "animal placed" keypress during recording isn't
  realistic in the lab; user, 2026-11-06.)
- **Object Recognition**: day, phase, each object's type (familiar / novel /
  moved) and identity; draft circles if the rig is calibrated.
- **Drafts for crop and scale** from a fixed rig's calibration, for the user
  to check (each video is still analyzed against its own setup; same idea as
  "Start from previous video").
- **Animal and experiment columns** in the Summary and export: animal ID,
  sex, strain, group/treatment, experimenter, rig, cohort and so on, so the
  exported table is ready for statistics by group.
- **Disturbances** marked during recording, listed in the Review tab.
- Later, **ASR stimuli** (§13) instead of separate stimulus logs.
Rules: every field optional except `schema_version` and `video.file`;
unknown fields ignored; units in field names; frames counted in the video
file from 0; exact strings for values Track Tamer acts on.
**Open questions for when it's built:** what wins when the JSON and the
user's setup disagree (proposed: JSON fills only what's empty or a draft,
and the user can always change it); whether the sidecar's information should
also be written into the tracking file (proposed: yes, so a tracking file
carries it without the JSON); gitignore the sidecars' real data (they hold
animal information).
**Update (2026-11-06): the user's capture software is "Creature Capture".**
Its real format: `<date>_<time>_<arena>_info.json` (plus `_info.csv`), one
per arena per trial, beside one MP4 and one `_frames.csv` per camera. The
spec was rewritten around it: a video is matched to its JSON by its exact
name in `cameras[].video` (not by a shared base name, since one JSON covers
several cameras); the import table and the asks for Creature Capture
(schema_version, time zone, 0-based frame numbering, fps and frame size
per camera, a fixed assay list, OR
`phase` and `objects`, optional extras) are in `docs/metadata_standard.md`.
**Update (2026-11-06): one standard for every video app.** The spec became
`docs/metadata_standard.md`, the **Track Tamer video metadata standard**:
Track Tamer is the master; any app that records video for it (Creature
Capture first, others as their analyses are added) follows it. It fixes the
**assay names**,
file naming (`<date>_<time>_<arena>_info.json`, videos
`<date>_<time>_<arena>_<camera>.mp4`, arena names without spaces or `_`),
reserved endings, common fields (Creature Capture's names kept), per-camera
fields, per-assay fields, app-specific fields under an object named after
the app, and how the standard changes (`schema_version`). An "Apps" section
lists each app's changes to match; the user will add other apps' pieces
over time.
**Revised with the user (2026-11-06), section by section:** no
separate assays for variants: then (user) **assay + `assay_variant` +
`phase`, each from a fixed list per assay**: `Object Recognition` with
variants `Novel Object Recognition` / `Spatial Object Recognition` (both use
the same analysis; the variant is recorded); `Acoustic Startle Response`
with `Prepulse Inhibition` / `Startle Habituation`; `Conditioned Place
Preference` planned (`Fear Conditioning` was listed too; removed
2026-11-10, user: it won't be captured). Variants will matter for ASR and
for more object and other variants later. Also removed (not recorded in the
lab): weight, cage, ear tag, dose, arena size, environment;
`cohort` labeled "Cohort / litter";
`phase` is a standard field with a list per assay; start date and time come
from the recording computer (no `start_wall_clock`); `trial_day` (day of a
multi-day trial) and `session_number` (sessions within a day);
`sex` may be `U`; `camera_position` (was `slot`) and `camera_settings` (with
`encoder`) are required for every camera; `_frames.csv` times are the
record of timing; Track Tamer reads only the JSON; camera labels follow the
arena-name rule. One camera over several arenas: not a concern for now
(user). Draft until the user says otherwise. Creature Capture had already
applied the first checklist (and confirmed frames count from 0); its section
lists what's done and what this revision changes.
Track Tamer's test dropdown keeps "Object Recognition" (it's the assay name).
**Fixed now (not waiting for 1.0):** Add folder tried to load
`_frames.csv`, `_info.csv` and Track Tamer's own `_ObjectScoring.csv` as
tracking files (each gave a "couldn't be read" error); it now skips them.
**Versioning:** the JSON has its own `schema_version`, separate from Track
Tamer's version, so either program can change on its own schedule; Track
Tamer reads every schema version it knows. Built on a feature branch
(`capture-metadata`) after 1.0 and released as **1.1**.

**Taken up before 1.0 (user, 2026-11-11), on `main`.** Decided with the
user the same day:
- **Scope: everything in this section's plan** (not a core-first cut).
- **When the info file and the setup disagree, the experimenter chooses**
  (user: "point out where there is a discrepancy for the task set up and the
  info file. bring up the discrepancies in a side by side like with check
  boxes and ask the experimenter to choose which one is correct"). So: a
  window lists each disagreement with the setup's value and the info file's
  value side by side, one box ticked per row. This replaces the earlier
  proposal (the file fills only what's empty).
- Still as proposed until the user says otherwise: the info file's
  information is also written into the tracking file, so a tracking file
  carries it without the JSON.
- **The same words in every app** (user, 2026-11-11, after seeing each
  app's info CSV beside Track Tamer's columns: "tell boombox not to leave
  columns out and make the word choice the same between all app"). The
  standard now fixes the `_info.csv` columns (section 1): Creature
  Capture's 24, always all written, an app's extras after them; Boom Box
  was told. Track Tamer's Summary uses the same names in the same order
  right after File (`date` … `notes`, with `age_days` worked out here),
  every one present and blank when not recorded; the recording details
  (`duration_set_min`, `frames`, `encoder` and so on) are on the Settings
  sheet. An object trial shows the app's `trial_day` and `phase` beside
  the `OR_Day` and `OR_Phase` its results used. (`OR_Day` was dropped on
  2026-11-12: the day is `trial_day` in every test's row.)
- **One file per video that tells everything (user, 2026-11-11).** The user
  found the saved data "a lot of repeated data" and wants "a simple way to
  have a file+json that allows the user to see everything about file", an
  "experiment info page which is the animal information and the basic task
  info", and a JSON that lets "the video [be] loaded back into track tamer
  ... so that if paths and maps weren't generated they could be", and
  "tracking could be done again with the regions and exclusions drawn";
  that setup "can be in the csv for backup but should be on it's own tab".
  No `room` or `app_name` columns anywhere. Decided from five questions:
  1. **One JSON that Track Tamer adds to**: its own `track_tamer` object
     inside the video's `cameras` entry of the capture app's info JSON
     (setup, tracking settings, analysis settings, its file names). It never
     changes what the capture app wrote. A video with no info file gets one
     made by Track Tamer in the same layout.
  2. **The Summary row carries `animal_id`** and the measures; everything
     else about the animal and task is on the workbook's new **Experiment**
     tab (vertical, like Settings). The tracking settings come off the
     Summary row (they're on Settings). A new **Setup** tab holds the crop,
     regions, exclusions and scale as numbers, as a backup of the JSON.
  3. **Each video keeps its own files** (no combined table for a load).
  4. **The tracking file is slimmed** to its per-frame columns; the
     settings and region outlines it repeated on every row live in the JSON
     (older files still load).
  5. **The capture apps drop the per-trial `_info.csv`** and keep the log
     (both were told; Boom Box's has no log yet as far as known).
  This replaces the plan to keep a copy of the trial information inside the
  tracking file, and it also gives priority item 5 (load a video together
  with its tracking file).
- **Built 2026-11-11 (uncommitted):**
  - `core/info_file.py`: the info file on disk (find, Track Tamer's
    `track_tamer` object, the columns a slim tracking file leaves to it).
    `core/info.py`: what the fields mean (test, session length, object
    details, problems, differences, the Experiment and Settings sheets).
  - Tracking writes the slim `_LocationOutput.csv`, the reference image and
    the info file together (`tracking.save_outputs`); `loader.load_csv`
    puts the saved columns back in memory, so the rest of the app is
    unchanged. Older files that hold their own settings still load.
  - Startle's `_MotionIndex.csv` is slimmed the same way (user, 2026-11-11:
    "go, move total_px and drop the stimuli copy"): on disk it has `Frame`,
    `Time_s`, `MotionIndex_pct`, `AboveThreshold_px`, `Frame_Unreadable`,
    `Repeated`. The video's name, threshold, start frame, crop, exclusion
    count, frame rate, stimulus source and `Total_px` (pixels analyzed) are
    in the info file. The stimuli aren't copied: they're read from the info
    file's own `stimuli`, or from the typed frames kept with the other
    constants (`Stimulus_Frames`). What varies from stimulus to stimulus
    (dB, kHz, type, interval) stays on every row of the Trials table, even
    when a session uses one value throughout (user).
  - `VideoSetup.to_saved` / `restore` / `use_reference`; adding a video
    whose info file has a saved setup restores it and attaches its tracking
    file (`gui._restore_setup`), without asking again about values the
    experimenter chose when it was tracked. A notice says when it was
    tracked with other tracking settings than the current ones.
  - The side-by-side window (`dialogs.ask_side_by_side`, the info file's
    side ticked to begin with) for the test type, then for session length
    and object details (`gui._use_info`).
  - Export: Experiment, Summary (File, `animal_id`, measures; no tracking
    settings), Time Bins, Settings, Setup sheets; the analysis settings and
    exported file names go in the info file. The animal's ID shows beside
    the file in the on-screen Summary from the moment it's added.
  - Tests: `test_info.py`, `test_info_gui.py`, and checks in
    `regress_gui.py`, `test_saving.py`, `test_asr_gui.py`.
  - **Added the same day (user: "build all of the not built items"):**
    a draft setup from the last video set up in the same arena with the
    same camera and frame size (`info.arena_draft`, `VideoSetup.draft_from`,
    `gui._arena_draft`: the list first, then the info files in the video's
    folder and the day folders beside it; applied once when setup opens on
    a video with nothing drawn, no step ticked); the info file's measured
    frame rate shown beside the Frame rate setting when they differ
    (`gui._info_rate`), and used by Track's frame-rate check and recorded
    as the tracking file's frame rate (`gui._video_rate`); a frame size in
    the info file that isn't the video's is reported; an **Experiment** tab
    on screen (the selected file's animal and task, before Analyze too).
  - **Four more decisions, built the same day:**
    - **Repeated frames in plus maze, open field and object videos: mark,
      fix speed, warn** (user, after the process was explained: the
      recording apps write the frame before again when the camera misses a
      tick, so the video keeps true time). Tracking writes a per-frame
      `Frame_Repeated` column from the info file's frame times file and
      its own list (`track_run.recorded_repeats`; no column when the
      recording app says nothing). The Summary counts them
      (`RepeatedFrames`). Speed is worked out across each repeat
      (`metrics.spread_repeats`: zero-then-double becomes the true speed;
      totals unchanged), for Open Field crossing speed and the Path's
      color by speed. After Analyze, a session with more than
      `repeated_warn_pct` of its frames repeated is flagged (5% to begin
      with; the "Warn at repeated frames (%)" box in the Session settings,
      which never locks since it changes no result).
      `tests/test_repeats.py`.
    - **A video tracked with other tracking settings than the current
      ones: both shown side by side** (`gui._use_saved_tracking`); ticking
      the saved ones sets them. Only while no other video in the list has
      been tracked and the returning videos agree; else a notice.
    - **The setup is saved when the setup window closes or moves to
      another video, as well as at Track** (`gui._save_setup`), with the
      steps that were done, so a part-finished setup comes back as it was.
      A video already tracked is marked `setup_changed_since_tracking`,
      and says so when added again (its reference image isn't reused).
    - **A test Track Tamer doesn't analyze: added with a notice, as it
      was.**
  - **Videos that came without an info file** (user, 2026-11-11: videos
    recorded before the new apps "will need to have a json created. if they
    are fed into the system without a json ask if there is a json
    associated and provide a file picker that starts with the location the
    video file came from. if there is not ask if the experimenter would
    like to add in animal informatoin. They will either be re-run or used
    as is."). When such videos are added, a window lists them
    (`info_dialog.show_missing_info`): for each, **Choose Info File…**
    (opens in the video's folder; the chosen file is copied into the
    video's own `<video name>_info.json` with its camera entry matched to
    this video, and isn't itself touched: `info_file.adopt`) or **Add
    Animal Information…** (`info_dialog.ask_animal`: animal ID, sex,
    strain, date of birth, treatment, cohort, trial date (taken from the
    file name when it has one), experimenter, trial day, notes; saved as
    the standard's fields with `app_name` "Track Tamer":
    `info_file.write_fields`). **Done** gives every one of them an info
    file, so they aren't asked about again; closing the window instead
    asks next time. The Experiment tab's **Animal information…** button
    adds or changes typed information later; a recording app's information
    is never changed. Videos tracked before today still need setting up
    again (their old tracking files load as they are); the user will
    re-track the example data at some point.
  **Still to build:** nothing in this section; the PC checklist is in the
  user's hands.
  **Dropped (user, 2026-11-11):** disturbances marked during recording
  (anything unusual goes in Notes), and draft object circles from a
  calibrated rig (the same-arena draft brings the last video's circles, and
  that's enough).
- (Dropped later the same day, see the end of this list.) Two parts of the
  plan had nothing to read: **disturbances** (no
  field in schema 1, and no app records them) and **draft circles from a
  calibrated rig** (no calibration fields). They wait for the standard.
  Draft crop, scale and regions come from that arena's last video
  (standard, section 4, `arena`).

## Open questions — RESOLVED (2026-10-09)
1. **EPM anxiety index** — ✅ report all three: %open time & %open entries, the
   composite Anxiety Index, and the closed/open time ratio. (See §4.)
2. **What counts as an "entry"** — ✅ minimum frames inside (configurable, saved).
3. **Open-field crossing** — ✅ traversal across center; opposite sides
   (left↔right, top↔bottom) and adjoining sides (e.g. left→top). (See §5.)
4. **Adjoining-side time filter** — ✅ require a minimum time in the center
   region between the two sides (configurable, saved).
5. **Crossing speed** — ✅ report both average (over traversal) and peak.
6. **Immobility defaults** — ✅ seed at <2 cm/s for ≥1 s; both configurable, saved.
   (Immobility itself was later deferred, §11.)

## Sample data findings (2026-10-23)
- **EPM** (`EPM.csv`): region columns `ol`, `or` (open left/right), `ct`, `cb`
  (closed top/bottom), `mid`. `ROI_location` also has overlap labels where the
  point is in two polygons at once (`or_mid`, `ol_mid`, `ct_mid`, `cb_mid`,
  `or_ct_mid`; ~1.3% of frames).
- **Open field** (`Open Field.csv`): region columns `center`, `peripheral`.
  `peripheral` is the *whole arena* (center frames read `center_peripheral`);
  `non_roi` = outside both. **There are no side regions** (left/right/top/
  bottom) — see decisions below.
- Both files are gitignored (`*.csv`) — research data stays off GitHub.

## Decisions from sample data — RESOLVED (2026-10-23)
1. **EPM overlap frames count as center.** A frame in an arm *and* the middle
   (or_mid, ct_mid, or_ct_mid, ...) is center; so is open+closed at once.
   Implemented in `core.regions.frame_roles` — §4 metrics must use it.
2. **Open-field sides come from X/Y**: the top of the video is the top of the
   arena (image coords: smaller Y = top). §5 crossings derive left/right/top/
   bottom from position relative to the file's own drawn center-ROI lines.
3. **Center and periphery must never overlap.** Any frame marked as both is a
   file/ROI error: the app warns the user when the file is analyzed (per file,
   frames + %), and counts those frames as center. `Open Field.csv` has this error (21.5% of
   frames — its periphery ROI covers the whole arena).

---

## Code review (2026-11-10)
A whole-codebase review for Windows and Mac (every source file read; fixes
each have a test in `tests/test_saving.py`, `test_edge_cases.py`,
`test_gui_fixes.py`, `test_objects.py` or `test_asr.py`).

**Fixed:**
- Saving: every result file is written whole under a temporary name and then
  put in place (`core/safe_write.py`), so a failed save, a cancelled video
  save, or a file open in Excel can't destroy the earlier file. The reference
  image is saved in a way that works in folders with accented letters on
  Windows. The crop is recorded exactly (it was rounded to one decimal, which
  could shift playback by a pixel).
- Object scoring: placed by video frame, so tracking a video again from
  another start doesn't shift it; "no interaction" marks survive a change of
  zone distance; scoring that can't be saved is kept and still used by the
  results; a scoring file that can't be read is copied aside before it's
  replaced; the Review tab and the scoring file use the analysis frame rate.
- Startle: a trial with an unreadable frame in its windows was left without
  an amplitude by accident (the note's wording matched a check meant for
  windows outside the recording); it's flagged and still measured. A frames
  file that can't be used no longer fails the video.
- Analyze: one failing file no longer stops the rest silently; region roles
  changed after Analyze re-work the results; a later Analyze warns about a
  file at a different frame rate; whole numbers in the Summary don't turn
  into "3.0".
- Setup window: reopening the Objects step on drawn objects crashed; a
  region drawn but not closed was thrown away on leaving the step; Start
  from previous video and Clear all replaced work without asking, and
  copied shapes between videos of different sizes; the session length kept
  the test type chosen when the video was added (an Open Field video could
  be tracked for 5 minutes); a startle end was reset to the whole video;
  opening the Threshold step rounded or zeroed the threshold; "2 hours" was
  read as 2 minutes.
- Main window: Clear, Remove and Close ask before losing video setups that
  aren't tracked yet; closing the "already tracked" question no longer
  starts tracking again; Cmd+Q on a Mac goes through the closing checks;
  the mouse wheel over the Test box no longer changes the test; Cmd+A is
  bound only on a Mac (on Windows it meant Num Lock + A).
- Windows-specific: bold text used a typeface name that doesn't exist;
  windows could open taller than a small laptop screen; Space re-pressed the
  last clicked button in the playback window.
- Settings: a scale length for Object Recognition (and a session length for
  startle) wasn't remembered between runs.

**Decided by the user and built (2026-11-11):**
1. **Time bins are true to the clock**: bin k starts at the frame nearest
   k x the bin length (`metrics._bin_ranges`), so Start_s / End_s are right
   however long the session. At 9.84 fps bins hold 590 or 591 frames in turn
   (before: always 590, 2.6 s early by the end of 65 minutes). Session totals
   are unchanged; per-bin numbers shift slightly from earlier exports.
2. **An end placed with "Set end here" stays on its frame** when the start
   moves (`VideoSetup.end_placed`); a typed or standard length still follows
   the start. An end that makes the session longer than the test's session
   length asks first (the user: "if an end is set that is outside of the
   selected time for the task give a warning"; read as longer than, not
   shorter than).
3. **A video save in progress is asked about** before another file is
   selected, or Clear, Remove or Close would stop it (`ReviewPanel.release`).
4. **Cancel start (Esc)** in the scoring panel drops an interaction started
   by mistake; nothing is logged.
5. **The trim step shows "Last frame N"** (the trial's last frame), not the
   frame after it.
6. **Package versions are pinned** to the exact tested ones in both install
   files (a rule for every app in the suite; see CLAUDE.md). Checked: the
   pinned Anaconda packages resolve for Windows and both kinds of Mac, every
   pinned pip package has a Windows download, and the Mac installer updated
   the existing environment from the pinned file. The no-Anaconda route now
   needs Python 3.12 or newer.

7. **Files that would write the same result files are stopped and named**
   at Track and at Export (X.avi and X.mp4 both write X_LocationOutput.csv
   and X_analysis.xlsx): those are left out until one is removed; the rest
   go ahead (`gui._split_same_results`).
8. **A reference image that's out of date unticks steps 3 and 4**
   (`VideoSetup.untick_stale_reference`): changing a video's start, end or
   session length, its crop, or the shared downsampling or "Frames to use"
   means Track would have to make a new reference the user never saw, so the
   video shows as needing setup until the reference is made again and the
   tracking check looked at. (Note: "Frames to use" is shared, so making one
   video's reference with a different count unticks the others'.)

9. **Nose and rear end is faster, with identical results** (branch
   `head-tail`). The first idea (start each frame from the last frame's
   search size) saved nothing when timed and was undone. Profiling showed
   the cost was the wide "join split pieces" step running on every frame; it
   now runs only when the search square holds a second piece to join. Every
   point was identical on five videos (12,500 frames); tracking with the
   points took about a third less time for large animals (30.6 s to 19.6 s
   for 2,500 frames) and a little less for small ones.
10. **Export shows a progress bar with Cancel** and keeps the window usable
    between files (Analyze, Export, Track, Clear and Remove wait meanwhile;
    Cancel stops after the file being written). **The Zone distance box
    applies once typing stops** (half a second, or at once on Return, on
    leaving the box, and before Analyze, Export or the Review tab).

All ten decisions from the review are settled.

**Found while doing them (2026-11-11), fixed:** since the frame-jump fix on
`main` (2026-11-10), a video with a damaged stretch was tracked only up to
the damage, with no warning: the damage cuts the video's timestamp list
short, and frames past the end of that list were taken not to exist
(`6_2023-03-26_15-19-33.mp4`: unreadable from frame 708 to 1,516, which the
user confirmed in the video itself, and 308 frames tracked of 6,031). A timestamp list much shorter than the file's
frame count is no longer used (`core/video.py`), so reading carries on past
the damage and those frames are kept as unreadable rows, as decided in §12.
Tracking also reports how many frames of the session couldn't be read at the
end (`TrackResult.missing_at_end`), and the app warns when that is more than
a few. **This fix is needed on `main` too.**

**Also pinned:** the exact Python version (3.12.16) in `environment.yml`.

## Build order
Done:
1. ✅ Config/persistence layer (`config.json`) — §6.
2. ✅ Plot controls + drag-and-drop — §1, §2.
3. ✅ Test-type dropdown + region-role mapping — §3.
4. ✅ **File-input workflow (§7).**
5. ✅ **Mac + PC groundwork (§10):** shared pop-up dialog and Windows
   launcher.
6. ✅ **Display fixes (§8).**
7. ✅ **EPM metrics (§4)**, validated against `EPM.csv`.
8. ✅ **Open-field metrics (§5)**, validated against `Open Field.csv`.
9. ⏸ ~~Shared immobility detection~~: deferred to future items (§11).
10. ✅ **Export (§9).**
11. ✅ **Test measures per time bin (§5b).**

**To look at later (user, 2026-11-12: "Mark that error for us to look at
later").** The workflow test (`tests/regress_gui.py`) failed two playback
checks once, on `head-tail` in the conda environment, right after `main`'s
startle review commit (93e7ed9) was merged in: "plays to the end and stops"
and "frame step back" (the second follows from the first: it steps back from
wherever playback stopped). The same merge passed in `.venv`, and the test
passed three times in a row when run again in conda. The check plays the
practice clip at 8x and gives it 20 seconds to reach the last frame, so a
busy computer or a window that lost its turn could do it; nothing in that
commit touches playback outside startle. **It happened again the same day
on `main` in `.venv`** (the full run after the startle review was taken
out), and again passed three times in a row when rerun, so it isn't
`head-tail`'s or one environment's. It isn't the time limit being a little
short either: a normal run finishes that playback in 0.5 s of the 20 s
allowed. So when it fails, playback either stood still for 20 s or was
stopped partway (the window's space bar pauses it; a key press or click
landing on the test's window while the user is at the computer would do
that, and so might the window being held back while it's hidden). The check
now prints how long playback took and which frame it was on, so the next
failure says which. The user, the same day: "I am often typing while you
are running screens so I think it is my input." That is the likely cause
(not yet confirmed by a failure with the new printout). It also means the
test windows sometimes take the user's keystrokes. Offered, not asked for
yet: make that check ignore the keyboard; and look for a way to keep test
windows from taking the keyboard at all.

**Priority order for what's next (user, 2026-11-09).** Nothing here starts
until the user asks; when they ask what's next, work from the top:
1. ✅ **Edit object type, trial day and phase after tracking** (built
   2026-11-09; §15).
2. ✅ **Show the objects on the saved `_tracked.mp4`** (built 2026-11-09; §15).
3. **Acoustic startle (ASR)** (§13): the target for the 1.0 release (user,
   2026-11-09). **Built 2026-11-09 on `main`, not released**; checking on real
   chamber videos is still to come.
4. **Reading the capture apps' info files** (§16): moved up by the user on
   2026-11-11 ("in main lets work on the puzzle box and the capture app
   into files. CPP can wait until after 1.0"; "into files" read as the info
   files), on `main`, before 1.0. Built the same day (§16).
5. **Load a video together with an existing tracking file** (entry below).
6. **Head and tail tracking** (requested 2026-11-09; on the `head-tail`
   branch, §17 there).
7. **Freezing analysis** (§12): lowest on the list.

After 1.0 (user, 2026-11-11): **conditioned place preference** (only its
assay name is reserved so far, `docs/metadata_standard.md`; needs its specs
decided), and **Puzzle Box** (moved up, then back the same day: "move
puzzle box to after 1.0. it isn't currently being run so can wait"; its
measures are decided, below), and **a results database** (user,
2026-11-11: "keep a database of results that would allow an inquiry to find
representative data to generate heatmaps, paths or other images from").
Nothing is specified yet. As a starting point when it's taken up: each
video's info file already holds its animal, task, setup and file names, and
its workbook the measures, so the database could be built by reading those
(e.g. one row per video: animal, treatment, test, the key measures, and
where its tracking file is), then asked for, say, the animal nearest its
group's median on a measure, and the Path or Heatmap made from that
video's tracking file. To decide then: where the database lives (one file
per experiment folder, or one for the lab), when it's updated (at Export,
or by scanning folders), what "representative" means (nearest the median,
the mean, or chosen by the user), and which images. Not ranked: the
standalone app (on hold).

**Puzzle Box (marker from 2026-11-10; after 1.0).** Creature Capture
records it (assay `Puzzle Box`, with trial days and several sessions a day;
arena `PuzzleBox`, camera `Overhead`), and the name is in the standard's
assay list. **Not analyzed in Track Tamer for now**, marked like Skilled
Reaching. Kept here so it isn't forgotten: if it's taken up, it needs its
measures decided first (nothing is specified yet).
**Decided with the user, 2026-11-11:** report the **time to reach the goal
box** (and whether the mouse got there before the session ended), plus
**time in the start area, distance travelled and speed before reaching the
goal**. **The goal box is covered**: the overhead camera can't see the mouse
inside it, so reaching the goal is judged from where and when the mouse
disappears from view at the doorway. Not built yet: it needs an example
video (none in `Examples/`) to see what the tracker does when the mouse
vanishes.

**Everything planned so far is built** (as of 2026-10-30). Still open:
- ✅ **Anaconda install (§14)**: built 2026-11-03 on `main`, merged into
  `video-tracking`. Tested on Mac (fresh install, clean environment, app
  launch, regression test inside the conda env); **PC test pending**.
- ✅ **Video analysis from ezTrack** (§12): Location Tracking built and on
  `main`. Freeze Analysis decisions are logged, not built (priority list above).
- **Acoustic startle (ASR) from video** (§13): planned, including PPI and
  habituation; not built. **When starting it, remind the user to add a sample
  video and stimulus logs to the folder.**
- ✅ **Order of results (requested 2026-11-04, decided and built 2026-11-05).**
  Elevated Plus Maze key measures, in this order: closed/open time ratio,
  center time, % center (of the session), open-arm time, % open (of arm
  time), closed-arm time, % closed (of arm time, new `EPM_PctClosedTime`),
  open entries, closed entries. They're the default on-screen Summary view
  (new first checkbox **Key measures**, the only one on by default; the old
  "Test measures" is now **More test measures**, the test's other columns)
  and come first in the exported Summary (after File) and Time Bins (after
  Bin / Start / End; bins use % of the bin for center). New
  `EPM_OpenClosedRatio` (open ÷ closed time) sits with the detailed measures.
  Speed, per-arm breakdowns and the rest follow. **Open Field left as is**
  (its default view is still basics + its measures; export order unchanged).
  Config key `summary_groups` became `summary_columns` so the new default
  reaches existing configs. Order lives in `KEY_MEASURES` (core/metrics.py).
- ✅ **One number per quantity (user, 2026-11-05).** In the example EPM file,
  `Time_closed arm 2_s` (108.77 s) differed from `Time_ROI_closed arm 2_s`
  (108.29 s): 8 frames sat exactly on the border closed arm 2 shares with the
  center, and polygon masks put border pixels in both regions. Also
  `Entries_center` (20) differed from `EPM_CenterEntries` (14): per-region
  entries counted every step in, without the entry rule. Fixed:
  `frame_regions` gives one region per frame (center wins; only the center
  may share, other shared frames are counted for the first region and
  reported in `SharedRegionFrames` / `SharedRegions` plus an Analyze
  warning); per-region time, %, entries (same entry rule, and Open Field's
  same-visit gap) and bins come from it; EPM role times / % / entries are the
  per-region values added up (rounded the same way), Open Field's center /
  periphery equal the per-region columns; `ROI_transitions` became
  `Region_transitions` (from the same labels); the ROI-label columns and the
  "ROI label time & %" checkbox are gone. Tracking writes every non-center
  region minus the center, so new files never mark a border frame twice.
  Checked by `tests/test_consistency.py`. `examples/` is gitignored.
  **Then (user):** EPM's center per-region columns (`Time_/Percent_/Entries_`
  of the center region) were exact repeats of `EPM_Center_s`,
  `EPM_PctSession_Center` / `EPM_PctBin_Center` and `EPM_CenterEntries`, so
  they're dropped from the Summary and Time Bins (`drop_duplicates`); the
  arms keep their per-arm columns. Open Field's center/periphery columns
  still repeat its OF_ measures (not asked to change).
  **Then (user):** Open Field done the same way (center time/%/entries and
  periphery time/% dropped; periphery entries kept, with no same-visit gap).
  Every derived measure is now a **formula of the shown values** (rounded
  inputs): % in a region = time / duration, % open = open / (open + closed),
  % closed = 100 − % open, ratios from the shown times, anxiety index =
  1 − (% open time + % open entries) / 200, mean speed = distance / duration,
  duration in minutes = Duration_s / 60. Counted from frames: times,
  entries, latencies, distances, crossings, sides. Reference chart published
  for the user (claude.ai artifact "Behavior Tracker Measures").
  **Open question for the user:** Open Field side times count every tracked
  non-center frame, so they add to 1.9 s more than periphery time in the
  sample; limit sides to periphery frames?
- ✅ **Setup window tweaks (user, 2026-11-05):** filled shapes (regions,
  exclusions) are **60% transparent**: tkinter can't draw partly transparent
  shapes, so `FrameCanvas` blends all fills into one RGBA image layer at 40%
  opacity just above the video image, with outlines, points and labels solid
  on top. A region whose middle is covered by another (the arena outline
  around the center) has its label near its top edge. Every scrub slider
  (trial start/end, Tracking check) gained **frame steps**: ◀◀ −10, ◀ −1,
  ▶ +1, ▶▶ +10, and the , and . keys step one frame (not while typing in a
  box).
- **Load a video with an existing tracking file (requested 2026-11-05; lower
  priority, not built).** The user closed the app and had to re-track. Wanted:
  bring in a video plus its tracking file to remake the Path/Heatmap and
  double-check the tracking (playback), with frames labeled from the right
  place in the full-length video. Already in place to build on: tracking
  files record `Start_Frame` (the video frame of row 1), `Crop` and
  `Downsample`, so playback lines rows up with the full video
  (`core/playback.py`); re-adding a video and clicking Track already offers
  **Use Existing Tracking** when `<name>_LocationOutput.csv` is beside it;
  adding the CSV itself, with the video in the same folder, already allows
  Play video… and the reference background. To do: make this one obvious
  step (e.g. adding a video that has a tracking file loads it as tracked,
  or an "Open tracked video" action), show the video frame and video time
  (not only the session row) in playback, and a "Go to frame" box.
- ✅ **DECIDED 2026-11-05 (see below): frames outside every drawn region (logged 2026-11-05;
  must be decided whatever the testing shows, as it will happen again).**
  In the Open Field sample 38 frames (1.9 s) have a position outside both
  regions, so the four side times add to 1.9 s more than periphery time
  (sides count every tracked non-center frame). Likely causes in a
  clear-walled box filmed at an angle: rearing/climbing (body over the
  wall), the mouse's reflection in the wall pulling the tracked point
  outward, and where the outline is drawn (floor edge vs top of walls).
  Options:
  - **A.** Outside frames count toward nothing (as now); center + periphery
    may total under 100%; limit sides to periphery frames so they add to
    periphery time.
  - **B.** Open Field: anything tracked that isn't center is periphery
    (outside frames count as periphery; center + periphery = 100%; sides
    add to periphery automatically). EPM unchanged (outside = no arm, e.g.
    head dips). **Assistant's lean.**
  - **C.** Outside frames go to the nearest region (B, extended to EPM).
  Test video for deciding together: `examples/1_2026-08-17_13-27-03.mp4`
  (Open Field, 65 min, 640x480, 9.84 fps, clear walls with reflections; the
  arena is empty at 1 min, so the start must be set when the mouse is
  placed). Plan: the user sets it up and tracks it; the assistant lists the
  outside-region stretches with times to review in Play video….
  **Review (user, 2026-11-05), second tracking (27 frames in 24 stretches,
  top and left walls only, mostly 1 frame and 1-4 px past the outline):**
  every stretch checked is the mouse **jumping at the wall**. Sometimes the
  tracker loses it for a moment as it goes up the wall (rows 4059, 8890,
  8918, 10300), but the point stays at the periphery; other jumps stay
  inside the outline and track well (9473, 10172). Also jumps: 10248,
  10716-10740 (several bouts), 17100, 29158 (a series), 29389. So the
  outside frames are a mouse at the edge, not time elsewhere, which supports
  option B.
  **Decision (user):** build B for Open Field, and count EPM outside frames
  too (a head dip that takes the point off an arm still counts): EPM uses the
  nearest region. The real problem to catch is the tracker getting **stuck**
  outside the bounds (a dark spot on the floor, the mouse's reflection), so
  time outside is measured as events. Event lengths from the examples: Open
  Field jumps average 0.11 s (longest 0.20 s; the sample file 0.15 s, longest
  0.35 s); EPM example 1.9 s (3 events, longest 2.34 s, look like head dips
  or pokes beside closed arm 1). Provisional "tracker may be lost" cutoffs:
  Open Field 1 s, EPM 5 s (config `review_cutoff_s`, editable in the Review
  tab, saved per test), for the user to settle.
  **Built:** `region_labels` assigns outside frames (`_outside_targets`:
  periphery when the file has one, else the nearest polygon edge);
  `outside_events` lists the stretches; Summary Details gain
  `OutsideEvents`, `OutsideTime_s`, `OutsideEventMean_s` (= time / events),
  `OutsideEventMax_s`; Analyze warns about stretches at or over the cutoff.
  **Review tab** (`review_panel.py`, next to Path and Heatmap; replaces the
  Play video… window and the Play video buttons): the playback (◀◀ / ▶▶ 10 s,
  ◀ / ▶ one frame, speed, trail, regions, Save as video…) with the info line
  showing session and video frame/time, and a **Points to review** list (one
  row per stretch: frame, session time, video frame, video time, length,
  counted as, px outside, flagged or brief); clicking a row shows that frame.
  With brief stretches handled, exclusion shapes can be drawn more liberally
  so real tracking continues through jumps. The setup window's ◀◀ / ▶▶ now
  skip 10 seconds (were 10 frames).
  **EPM review (user, 2026-11-05):** in the EPM example, outside stretches 1
  and 2 (0:22–0:26) are before the mouse was placed (that tracking starts at
  video frame 0), so they wouldn't exist with the start set at placement;
  stretch 3 (0:29.74, 2.34 s, beside open arm 2) is a head dip. **The EPM
  rules hold** (nearest region; 5 s cutoff).
  **Changed (user):** the video inside the Review tab was too cramped. The
  tab now holds the points-to-review list and an **Open playback window**
  button; the video plays in its own resizable window (`PlaybackWindow`),
  and clicking a row opens it (or brings it forward) at that frame. Loading
  another file closes the window. A separate window will also serve a future
  **object recognition** analysis that needs manual scoring (not planned
  yet; the user mentioned it 2026-11-05).
- ✅ **Object recognition (§15)**: decided and built 2026-11-05 (O1–O4).
- ✅ **Tester report (Windows 11, 2026-11-06): "An Application Control policy
  has blocked this file"** on scipy's `_nd_image` DLL (Smart App Control or an
  IT policy; other Windows testers were fine). scipy was only used for
  `ndimage.center_of_mass` in tracking, so that's now numpy
  (`core/tracking.center_of_mass`, identical to 1e-13; re-tracking the EPM
  example still matches its file exactly) and **scipy is no longer a
  dependency** (requirements.txt, environment.yml). INSTALL.md gained a
  troubleshooting entry. The EPM example was re-tracked by the user that
  morning (start frame 389) for a demo, without exclusion zones for the
  areas outside the maze, hence the 101.7 s outside stretch at the start; tests
  no longer hard-code that file's numbers. **Released as 0.9.1** (tag `v0.9.1`).
  **Confirmed (user, 2026-11-06): 0.9.1 opens on that tester's Windows 11 PC.**
  Other Windows testers had installed 0.9 successfully, so the Windows install
  and launch work in the field.
  At least one Windows tester has **loaded, tracked and analyzed** videos
  (2026-11-06); **export** not reported yet.
- **Experiment information from the capture software (§16)**: planned for
  after 1.0 (1.1); draft standard in `docs/metadata_standard.md`.
- ✅ **Version 0.9, the testing release (user, 2026-11-05):** `core/version.py`
  (`VERSION`), shown in About and recorded in each exported Settings sheet;
  tagged `v0.9` (GitHub pre-release). The user first asked for 1.0, then chose
  0.x since it's about to be tested: fixes become 0.9.1, 0.9.2, …, and 1.0
  follows testing.
- ✅ **Merged `video-tracking` into `main` (user, 2026-11-05)** for outside
  testers downloading from GitHub the next day; `TESTING.md` added (install,
  what to try for each test, how to report problems, known limitations).
  The repository is **public** (checked 2026-11-05; history holds no data
  files or tokens). The first Windows run is still open.
- ✅ **Renamed Track Tamer (user, 2026-11-05)** (was "Behavior Tracker"):
  window titles, About, docs, launchers (`Install` / `Open` / `Uninstall
  Track Tamer` `.command` / `.bat`), the Anaconda environment
  (`track-tamer`; run the installer once to create it), the GitHub
  repository (`vtbrak/TrackTamer`) and the project folder
  (`Desktop/Tracker Tamer`). Earlier entries below keep the old name as written then.
- ✅ **Tests use the Examples files (user, 2026-11-05).** The old
  `EPM.csv` / `Open Field.csv` samples were removed; every test now uses the
  real videos tracked in this app and their tracking files in `Examples/`
  (`tests/samples.py`). `test_video.py` re-tracks the start of the EPM example
  with the settings and reference its file recorded and matches it (median
  0.01 px), replacing the comparison with ezTrack's own EPM.csv.
- **Windows testing** (§10): testers have installed, tracked and analyzed on
  Windows (2026-11-06). Not yet reported there: export, object scoring, and
  0.9.2's Edit trial info and saved video.
- ✅ **Released 0.9.2 (2026-11-09):** Edit trial info after tracking, objects
  on the saved video, Add folder skips companion CSVs (tag `v0.9.2`).
- ✅ **Released 0.9.3 (2026-11-12, pre-release, tag `v0.9.3`):** everything
  built on `main` since 0.9.2: the code review fixes and the ten decisions,
  the damaged-video fix, pinned package versions, one info file per video
  (read from the recording apps and added to by Track Tamer), slim tracking
  files, videos coming back set up, the side-by-side choices, the
  Experiment sheet and tab, repeated frames, same-arena drafts, videos with
  no info file, startle repeats warning and startle by sound level.
  **From this release on, every GitHub release is made from a pushed
  annotated tag `v<version>`** (user, 2026-11-12).
- ✅ **Settings survive updates (2026-11-12, after 0.9.3).** Boom Box found
  that its users' own files sat among the program files, so updating lost
  them, and that it saved full paths into its own folder; the user asked
  every app in the suite to check ("let other apps in the suite know about
  this weakness and have them do the same thing"). Track Tamer had the
  first: `app/config.json` sat in the program folder the update guide said
  to replace. Now everything the user sets up is in `app/config/`
  (`core/config.py`: `CONFIG_DIR`; an old `app/config.json` or project-
  folder `config.json` is moved in at startup, never writing over one that's
  there: identical copies dropped, different ones kept as `config_2.json`),
  and INSTALL.md's update steps say to copy that folder. It had none of the
  second (no saved paths into its own folder). Tests in `test_layout.py`.
- ✅ **Released 0.9.4 (2026-11-12, pre-release, tag `v0.9.4`):** the settings
  fix above, on its own (user: "put out the settings fix as 0.9.4").
- ✅ **Jumps to a video frame match in-order reading (2026-11-10, not
  released).** The camera videos store each frame's real capture time, so
  their frames aren't evenly spaced (gaps of 34–123 ms in one EPM video).
  OpenCV jumps to frame N by turning N into a time with the average frame
  rate, so in some stretches it landed on the frame before (about half the
  sampled frames of every camera video in `Examples/`; the constant-rate ASR
  clips are exact). Tracking reads in order, so after a jump the playback
  window could draw the marks on the neighbouring frame. Now
  `core/video.py` lists each frame's timestamp once per video without
  decoding (`frame_times`; 0.1 s for a 6-minute video, 1.6 s for the
  65-minute one), and a jump aims a little early, checks by timestamp which
  frame it landed on, and reads forward to the exact one (`grab_frame`;
  same speed as before). `VideoReader.read_at` and the playback window's
  `FrameSource` use it; without timestamps (another video backend) they
  fall back to OpenCV's own jump. **Tracking starts on exactly the start
  frame chosen in setup (user, 2026-11-10):** `VideoReader.frames` goes to
  the start frame the checked way and reads on in order, so the frame setup
  shows as the start is the first tracked frame, and playback row r and the
  saved `_tracked.mp4` are frame start + r. Before, tracking started where
  OpenCV's jump landed, which could be the frame before. Trials that start
  at frame 0, or where the old jump was right, track exactly as before.
  **A file tracked before this with a start after 0 may have been tracked
  from the frame before its start, and then plays back one frame off:
  re-track it** (the user: nothing tracked so far needs keeping). Of the
  example files, the Open Field one (`1_2026-08-17_13-27-03`, start 730)
  was tracked from frame 729 and needs re-tracking; the EPM one (start
  674) and the object trial (start 0) are right. Say so in the notes of
  the release this goes out in. The reference image still reads the frames
  it always did (`read_near`: OpenCV's own jump, any frame nearby does), so
  references are unchanged.
  Checked by `tests/test_seek.py` (skips when the videos aren't there).
- **Future items** (§11): immobility, now to be covered by §12's freezing.
- **Standalone app** (bundling): on hold until the user says so.
- New requests from the user.

Throughout: keep everything working on both Mac and PC (§10), with a PC test
checklist after cross-platform changes.
