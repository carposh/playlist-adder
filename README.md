# Playlist Adder

Adds a list of songs to a Spotify playlist by clicking through the Spotify desktop app on Windows.
It uses the playlist's own **"Add to playlist" panel**: for each song it types the title and artist into
the panel's search box and clicks the (+) on the first result.

## Install

Run `dist\PlaylistAdder-Setup.exe`. It installs for your Windows user only (no admin prompt) into
`%LOCALAPPDATA%\Programs\Playlist Adder`, adds a Start Menu entry (and optionally a desktop icon),
and shows up in Settings > Apps for uninstalling. Screen pictures are kept in `%LOCALAPPDATA%\PlaylistAdder`;
the uninstaller removes those too.

## Use

1. In Spotify, open the playlist and open its "Add to playlist" panel (Search box with (+) buttons).
2. Open **Playlist Adder** and either click **Open file…** or paste songs into the box.
3. First time only: **Set up screen pictures…** (see below).
4. Press **Start** and keep your hands off the mouse and keyboard. To stop, move the mouse to the
   top-left corner of the screen.

When it finishes, it shows how many songs were added and why any failed.
**Practice run** lists what it would do without clicking anything.

## Song list formats

| Format | What it should look like |
| --- | --- |
| `.txt` | One song per line: `Queen - Bohemian Rhapsody`. Any text Spotify can search works; lines starting with `#` are skipped. |
| `.csv` / `.tsv` | Columns named `title`/`track`/`song`/`name` and `artist` in any order (Exportify exports work as they are). With no header: title in column 1, artist in column 2. Excel: *Save As > CSV*. |
| `.json` | `{"playlist": "Name", "tracks": [{"title": "...", "artist": "..."}]}`, or just the list, or a list of `"Artist - Title"` strings. |
| `.m3u` / `.m3u8` | Playlist files from music players (VLC, foobar2000, Winamp…). Uses the `#EXTINF` names, else the file names. |

You can also drop a song file onto the Playlist Adder shortcut to open it directly.

## Setting up the screen pictures

The installer comes with the pictures captured on the PC it was built on. On another PC, or after changing
display scaling, Spotify's zoom or window size, recapture them: open the playlist's "Add to playlist" panel,
then in Playlist Adder click **Set up screen pictures…**. A small window appears in the bottom-left corner:

| Row | What you do |
| --- | --- |
| Notifications bell | Point at the top-left, then bottom-right corner of the bell in Spotify's top bar (5 seconds each). Capture it without the new-notification dot. |
| Search box | Point at the middle of the panel's Search box. |
| (+) button | Point at the corners of one round (+) on any song row. |

After each crop, move the mouse away while it counts down, so the picture isn't caught lit up by the mouse.
**Check it can see them now** confirms it finds the bell and the (+) buttons.

## Things to know

- The script waits for search results (default 2 seconds) then clicks the topmost (+). If your results load
  slowly it could click an old result; raise the wait.
- The (+) is matched in colour, so if Spotify shows already-added songs with a different icon, they're skipped
  and reported as failed rather than added twice.
- The first result is Spotify's best match. Check the playlist after a run.

## For developers

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt pyinstaller
.venv\Scripts\python app.py                      # the window app from source
.venv\Scripts\python spotify_add_tracks.py songs.csv [--dry-run]   # command-line version
.\build.ps1                                      # builds dist\PlaylistAdder-Setup.exe (needs Inno Setup 6)
```

From source, pictures live in `templates\` next to the scripts (`capture_templates.py` is a console
capture helper). `build.ps1` bundles whatever is in `templates\` as the installer's starting pictures.
