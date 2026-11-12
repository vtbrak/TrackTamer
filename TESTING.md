# Testing Track Tamer

Thank you for testing version 0.9.2! This page covers getting the program, what to try, and
how to report problems. Plan on about 15 minutes to install, then as long as
you like to test.

Track Tamer tracks a mouse or rat in videos of an **Elevated Plus Maze**, an
**Open Field**, or an **Object Recognition** trial, and works out the results
(time in each area, entries, distance, interaction time with each object, and
so on).

**You'll need your own videos** (`.mp4`, `.avi`, `.mov` and similar). Research
videos aren't included in the download. The program never changes your
videos. It saves its results beside them, so testing on a **copy** of a video
in its own folder keeps things tidy.

---

## 1. Get the program and install it

1. **Install Anaconda** from https://www.anaconda.com/download, keeping the
   suggested choices (on Windows, pick **"Just Me"**). Skip this if you
   already have Anaconda or Miniconda.
2. **Download the program:** on the GitHub page, click the green **Code**
   button → **Download ZIP**. Unzip it and move the folder somewhere easy to
   find, such as Documents.
3. **Install:** in the folder, double-click **Install Track Tamer.command**
   (Mac) or **Install Track Tamer.bat** (Windows). Wait until it says
   **Done** (several minutes).
4. **Open:** double-click **Open Track Tamer.command** (Mac) or
   **Open Track Tamer.bat** (Windows).

If the computer blocks a file:
- **Mac** ("can't be opened" / "unidentified developer"): right-click the
  file → **Open** → **Open**. After that, double-clicking works.
- **Windows** ("Windows protected your PC"): click **More info** →
  **Run anyway**.

Stuck? [INSTALL.md](INSTALL.md) has more detail, including a way to install
on a Mac without an administrator password.

**Already installed an earlier version** (called "Behavior Tracker")? Run
**Install Track Tamer** again: the new version uses a new environment.

---

## 2. What to try

Do whichever parts fit your videos. Note anything confusing, slow or wrong,
not just crashes.

### A. Track a video (any test)
1. In the main window, choose the **Test** (Elevated Plus Maze, Open Field or
   Object Recognition).
2. **Add files…** and pick a video (or drag it onto the window).
3. Click **Set up videos…** and go through the six steps:
   1. **Trim and crop:** move the slider to when the animal is placed, click
      **Set start here**, and drag a box around the arena.
   2. **Exclusions:** optional; outline anything that moves but isn't the
      animal (e.g. a cable).
   3. **Reference:** click **Make reference** (a picture of the empty arena).
   4. **Tracking check:** scrub through; the red cross should sit on the
      animal.
   5. **Regions** (or **Objects** for Object Recognition): see B or C below.
   6. **Scale:** click both ends of something of known length and type its
      length in cm.
4. Click **Track** and wait for it to finish.
5. Click **Analyze**, then look at the **Summary**, **Time Bins**, **Path**
   and **Heatmap** tabs.
6. Click **Export**. Check the `_analysis.xlsx` and the two pictures saved
   beside the video. The workbook has Experiment, Summary, Time Bins,
   Settings and Setup sheets.
7. Click **Clear**, then add the same video again. It should come back
   already set up and tracked (status **Not analyzed**), with its regions as
   you drew them, and Analyze should work straight away. That comes from the
   `_info.json` file beside the video.

### B. Elevated Plus Maze or Open Field
- In step 5, draw each region by clicking around it (click the first point
  again to close it).
- After Analyze, open the **Review** tab. It lists moments when the tracked
  point was outside the drawn regions. Click one and check the video at that
  moment in the playback window.

### C. Object Recognition
1. In step 5 (**Objects**), press at the center of each object and drag out
   to its edge. Mark each one **Familiar**, **Novel** or **Moved**, and set
   the trial **day** and **phase**. The dashed ring is the zone around each
   object (the **Zone distance**, 4 cm unless you change it).
2. After tracking, open the **Review** tab. It lists every time the animal
   came within the zone of an object.
3. Click the first one. In the playback window:
   - Step through the video with ◀ ▶ (one frame) and ◀◀ ▶▶ (10 seconds), or
     **Play**.
   - When the animal starts interacting, click **Start interaction** (or
     press **S**); when it stops, **End interaction** (**E**).
   - If there was no interaction, click **No interaction** (**N**).
   - Click **Next visit ▶** (or press **]**) to go to the next one.
4. Click **Analyze** and look at the Summary: time with each object,
   discrimination index, % preference. These update as you score.
5. Click **Edit trial info…** in the Review tab, change an object's type, the
   day or the phase, and save. The Summary should update without tracking
   again.
6. In the playback window, click **Save as video…** and check that the
   objects and their zones show in the saved `_tracked.mp4`.
7. Close the program and open it again: your scoring should still be there
   (it's saved in `<video name>_ObjectScoring.csv`).

### D. Acoustic Startle Response
1. Choose **Acoustic Startle Response** as the Test and add a video.
2. In **Set up videos…**, step 3 (**Threshold**), scrub to a still moment and a
   moment of movement. Red shows the pixels counted as movement.
3. Step 4 (**Stimuli**) uses the recording's info file if it has one.
   Otherwise type the video frame of each stimulus.
4. Click **Track**, then **Analyze**, and look at **Trials**, **Motion Trace**
   and **Aligned Trials**. Then click **Export**.
5. Open the **Review** tab and click a startle. In the playback window, use
   **Next trial**, **Go to peak** and the frame buttons.

---

## 3. Reporting problems

If you see anything, just let the person who invited you know. These details
help:
- **What you did** (the steps), **what you expected**, and **what happened**.
- **Mac or Windows**, and which version (e.g. macOS 15, Windows 11).
- **Screenshot** of the window or message, if there is one.
- **The text in the black console window** (Windows) or Terminal window
  (Mac) that opens with the program. Errors appear there even when the
  program keeps going.
- If it's about one video: its length and size, and if you can, the video or
  its `_LocationOutput.csv` together with its `_info.json`.

### Known limitations
- Windows has had less testing than Mac, so Windows reports are especially
  useful.
