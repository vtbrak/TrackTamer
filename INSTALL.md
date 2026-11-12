# Installing Track Tamer

These steps set up Track Tamer on a Mac or Windows computer. No
programming is needed. Installing takes about 10–15 minutes, most of it
waiting, and needs an internet connection.

There are two ways to install:

- **Method 1: Double-click.** The easiest. Works on Mac and Windows.
- **Method 2: No password method.** For Macs that block the program's files
  and ask for an administrator password you don't have. You type two short
  commands into Terminal instead of double-clicking.

Try Method 1 first. Steps 1 and 2 are the same for both methods.

---

## Method 1: Double-click

### Step 1. Install Anaconda
- Go to **https://www.anaconda.com/download** and download the installer for
  your computer (Mac or Windows).
- Open the downloaded file and follow the prompts, keeping the suggested
  choices.
- On Windows, choose **"Just Me"** when asked who to install for.
- Skip this step if Anaconda or Miniconda is already installed.

### Step 2. Get the program folder
- Download the program as a **.zip** file. You can get it from whoever
  shared the program with you, or from GitHub (green **Code** button →
  **Download ZIP**).
- Double-click the .zip file to unzip it.
- Move the unzipped folder somewhere easy to find, such as **Documents**.

### Step 3. Run the installer
- Open the program folder.
- **Mac:** double-click **Install Track Tamer.command**.
- **Windows:** double-click **Install Track Tamer.bat**.
- A window with text opens. This is normal.

**If the Mac says the file "can't be opened"** or is from an unidentified
developer:
1. Right-click (or Control-click) the file and choose **Open**.
2. Click **Open** in the message that appears.

If that doesn't work, go to **System Settings → Privacy & Security**, scroll
down, and click **Open Anyway**. If it asks for a password you don't have,
use **Method 2** instead.

**If Windows shows "Windows protected your PC":** click **More info**, then
**Run anyway**.

### Step 4. Wait for "Done"
- The installer downloads what the program needs. This takes several
  minutes. Let it run.
- When it says **Done**, press **Return** (Mac) or any key (Windows) to close
  the window.
- If it says **Failed**, see *If something goes wrong* below.

### Step 5. Open the program
- **Mac:** double-click **Open Track Tamer.command**.
- **Windows:** double-click **Open Track Tamer.bat**.
- A text window opens first, then the program. **Leave the text window open**
  while you use the program. Closing it closes the program.
- From now on, this is the only step you need to start the program.

---

## Method 2: No password method (Mac)

This method runs the same files through **Terminal**, the Mac's built-in
text window, so macOS doesn't block them and no password is needed.

### Step 1. Install Anaconda
- Same as Method 1, Step 1.

### Step 2. Get the program folder
- Same as Method 1, Step 2.

### Step 3. Open Terminal
- Press **Command (⌘) + Space**, type **Terminal**, and press **Return**.
- A window opens where you can type.

### Step 4. Run the installer
- Type **`bash`** followed by **one space**. Don't press Return yet.
- Drag **Install Track Tamer.command** from the program folder into the
  Terminal window. Its location appears after `bash `.
- Press **Return**.

It should look similar to this (your location will differ):

```
bash /Users/yourname/Documents/Track\ Tamer/Install\ Track\ Tamer.command
```

### Step 5. Wait for "Done"
- The installer takes several minutes. Let it run.
- When it says **Done**, press **Return**.
- If it says **Failed**, see *If something goes wrong* below.

### Step 6. Open the program
- In Terminal, type **`bash`** followed by **one space**.
- Drag **Open Track Tamer.command** into the Terminal window.
- Press **Return**. The program opens.
- **Leave Terminal open** while you use the program. Closing it closes the
  program.
- Repeat this step whenever you want to start the program.

**Tip:** in Terminal, press the **up arrow (↑)** to bring back the last
command, then press **Return** to run it again. This saves dragging the file
each time.

### On Windows
Windows doesn't usually need a password for these files. If double-clicking
is blocked:
1. Open the **Start** menu, type **Anaconda Prompt**, and open it.
2. Drag **Install Track Tamer.bat** into the window and press **Enter**.
3. When it says Done, drag **Open Track Tamer.bat** in the same way to
   start the program.

---

## Updating the program
1. **Keep your settings:** in the old program folder, open `app` and copy
   the **`config`** folder somewhere safe. It holds everything you've set in
   Track Tamer (thresholds, tracking settings, the region matches you chose,
   remembered session and scale lengths, plot style).
   - Updating from **0.9.3 or earlier**: there's no `config` folder yet;
     copy the file **`config.json`** instead (in `app`, or for 0.9.2 and
     earlier in the program folder itself).
2. Replace the program folder with the new version.
3. Put what you copied back into the new folder's `app` folder: the
   `config` folder, or the `config.json` file (the program moves it into
   `app/config` the first time it opens).
4. Run the installer again (Step 3 of Method 1, or Step 4 of Method 2). It
   updates what's already installed, so it's faster the second time.

Your videos, tracking files, info files and results are kept beside your
videos, outside the program folder, so updating doesn't touch them. (Keep
them out of the program folder for that reason.) Without Anaconda, the
program's own Python environment (`app/.venv`) is rebuilt automatically the
first time the new version opens.
- If the program ever says *"the program's package list has changed since it
  was installed"*, that also means: run the installer again.

## Removing the program
- Run **Uninstall Track Tamer** the same way you ran the installer, and
  type **y** when asked.
- This removes only what the installer added. Your data files and results
  are kept.
- You can then delete the program folder.

## If something goes wrong
- **"Anaconda wasn't found on this computer"**
  - Install Anaconda (Step 1). If you just installed it, restart the computer
    and try again.
- **"Install failed"**
  - Check your internet connection and run the installer again.
- **"Track Tamer isn't installed yet"**
  - Run the installer first, then open the program.
- **"Some videos are hard to read," or a video won't open**
  - Convert the video to .mp4 (H.264), for example with HandBrake (free), and
    add the converted copy.
- **Tracking or Export says a file couldn't be saved**
  - Results are saved next to each video or CSV, so that folder must be one
    you can save into (not a read-only drive or a zip you haven't unzipped).
    If an `_analysis.xlsx` or `_LocationOutput.csv` is open in Excel, close
    it and try again.
- **Windows: "An Application Control policy has blocked this file"**
  - Windows 11's **Smart App Control** (or a work or school computer's IT
    policy) blocked one of the program's files. Version 0.9 used a package
    (scipy) that this happened to; newer versions don't need it, so download
    the program again and replace the old folder.
  - If it still happens with another file, check **Windows Security → App &
    browser control → Smart App Control**. On a work or school computer, ask
    IT to allow Python in the Anaconda folder. Turning Smart App Control off
    is a big change (Windows only lets you turn it back on by reinstalling),
    so it's your call, or IT's.
- **The program closes with an error**
  - Take a screenshot of the text window and send it to whoever shared the
    program with you.
