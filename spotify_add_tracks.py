"""Add tracks from a song list to a Spotify playlist by driving the Spotify desktop app.

Uses the playlist's own "Add to playlist" side panel: for each track it searches in the
panel's search box and clicks the (+) button on the first result.

Before running: open the playlist in Spotify and open its "Add to playlist" panel.

Usage:
    python spotify_add_tracks.py SONGS_FILE [--dry-run] [--templates DIR]

Song list formats (see read_tracks):
    .json  {"playlist": "...", "tracks": [{"title": ..., "artist": ...}]}  or just the list
    .csv   columns named title/track/song/name and artist (e.g. an Exportify export),
           or no header: title in column 1, artist in column 2
    .txt   one song per line, e.g. "Queen - Bohemian Rhapsody" (any text Spotify can search)
    .m3u   playlist files from music players (#EXTINF lines, else the file names)

Abort at any time by slamming the mouse into the top-left corner of the screen
(pyautogui failsafe).
"""

import argparse
import csv
import ctypes
import io
import json
import os
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# The panel's own heading disappears once you search, so anchor on the top bar's bell instead.
ANCHOR = "notifications.png"  # the notifications (bell) icon in Spotify's top bar
ADD_BUTTON = "add_button.png"  # the (+) button at the end of a result row
SEARCH_OFFSET_FILE = "search_offset.json"  # written by capture_templates.py: search box relative to the bell

# Rows start this far below the search box; anything above (the search box itself) is ignored.
ROWS_BELOW_SEARCH = 30

SUPPORTED_SUFFIXES = (".json", ".csv", ".tsv", ".txt", ".m3u", ".m3u8")


def default_templates_dir():
    """Next to the script when run from source; per-user app data when installed as an exe."""
    if getattr(sys, "frozen", False):
        return Path(os.environ["LOCALAPPDATA"]) / "PlaylistAdder" / "templates"
    return SCRIPT_DIR / "templates"


class StepFailed(Exception):
    pass


@dataclass
class Track:
    title: str
    artist: str = ""

    @property
    def query(self):
        return f"{self.title} {self.artist}".strip()

    def __str__(self):
        # Same "Artist - Title" shape that parse_lines reads back.
        return f"{self.artist} - {self.title}" if self.artist else self.title


# --- Reading song lists ---------------------------------------------------------------------

def _read_text(path):
    raw = Path(path).read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")  # Excel's default "CSV" on Windows


def _split_artist_title(line):
    """'Artist - Title' is the usual way people write songs down. Order doesn't matter for
    Spotify's search, so this only affects how the song is displayed."""
    for sep in (" - ", " – ", " — "):
        if sep in line:
            artist, title = line.split(sep, 1)
            return Track(title.strip(), artist.strip())
    return Track(line.strip())


def parse_lines(text):
    tracks = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            tracks.append(_split_artist_title(line))
    return tracks


def _parse_json(text):
    data = json.loads(text)
    playlist = None
    if isinstance(data, dict):
        playlist = data.get("playlist") if isinstance(data.get("playlist"), str) else None
        data = data.get("tracks")
    if not isinstance(data, list):
        raise ValueError('JSON must be a list of songs or an object with a "tracks" list')
    tracks = []
    for i, t in enumerate(data, 1):
        if isinstance(t, str):
            tracks.append(_split_artist_title(t))
        elif isinstance(t, dict) and str(t.get("title", "")).strip():
            tracks.append(Track(str(t["title"]).strip(), str(t.get("artist", "")).strip()))
        else:
            raise ValueError(f'song #{i} needs a non-empty "title"')
    return playlist, tracks


TITLE_COLUMNS = ("title", "track", "track name", "song", "song name", "name")
ARTIST_COLUMNS = ("artist", "artists", "artist name", "artist name(s)", "artist(s)")


def _parse_csv(text, delimiter=None):
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:4096], delimiters=",;\t").delimiter
        except csv.Error:
            delimiter = ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if any(c.strip() for c in r)]
    if not rows:
        return []
    header = [c.strip().lower() for c in rows[0]]
    ti = next((header.index(c) for c in TITLE_COLUMNS if c in header), None)
    if ti is None:  # no recognisable header: title, artist
        ti, ai, body = 0, 1, rows
    else:
        ai = next((header.index(c) for c in ARTIST_COLUMNS if c in header), None)
        body = rows[1:]
    tracks = []
    for r in body:
        title = r[ti].strip() if ti < len(r) else ""
        # Exportify joins multiple artists with commas; the first is enough for searching.
        artist = r[ai].split(",")[0].strip() if ai is not None and ai < len(r) else ""
        if title:
            tracks.append(Track(title, artist))
    return tracks


def _parse_m3u(text):
    tracks, pending = [], None
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("#EXTINF:"):
            pending = line.split(",", 1)[1] if "," in line else None
        elif line and not line.startswith("#"):
            name = pending or Path(line.replace("\\", "/")).stem
            tracks.append(_split_artist_title(name))
            pending = None
    return tracks


def read_tracks(path):
    """Return (playlist name or None, tracks) for any supported song list file."""
    path = Path(path)
    suffix = path.suffix.lower()
    text = _read_text(path)
    if suffix == ".json":
        return _parse_json(text)
    if suffix in (".csv", ".tsv"):
        return None, _parse_csv(text, "\t" if suffix == ".tsv" else None)
    if suffix in (".m3u", ".m3u8"):
        return None, _parse_m3u(text)
    return None, parse_lines(text)  # .txt and anything else


# --- Spotify window -------------------------------------------------------------------------

def _exe_name_for_hwnd(hwnd):
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return Path(buf.value).name.lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def find_spotify_window():
    """Spotify's title changes with the playing song, so match on the owning process instead."""
    import pygetwindow as gw

    candidates = [
        w for w in gw.getAllWindows()
        if w.title and w.width > 200 and w.height > 200 and _exe_name_for_hwnd(w._hWnd) == "spotify.exe"
    ]
    if not candidates:
        raise StepFailed("Spotify window not found - is the desktop app open?")
    return max(candidates, key=lambda w: w.width * w.height)


def focus_window(win):
    import pyautogui

    if win.isMinimized:
        win.restore()
    for _ in range(3):
        try:
            win.activate()
        except Exception:
            pass  # pygetwindow raises "error 0" even when it worked; check the result instead
        time.sleep(0.3)
        if win.isActive:
            time.sleep(0.1)
            return
        # Windows refuses SetForegroundWindow unless we "own" input; an Alt tap unlocks it.
        pyautogui.press("alt")
    raise StepFailed("couldn't bring the Spotify window to the front")


# --- Screen matching ------------------------------------------------------------------------

def _template(settings, name):
    path = settings.templates / name
    if not path.exists():
        raise StepFailed(f'template file missing: "{name}" (see README.md)')
    return str(path)


def find_anchor(settings, region):
    import pyautogui

    tpl = _template(settings, ANCHOR)
    deadline = time.monotonic() + settings.timeout
    while True:
        try:
            box = pyautogui.locateOnScreen(tpl, confidence=settings.confidence, region=region, grayscale=True)
        except pyautogui.ImageNotFoundException:
            box = None
        if box:
            return box
        if time.monotonic() >= deadline:
            raise StepFailed(f"notifications bell not found within {settings.timeout:g}s (template \"{ANCHOR}\")")
        time.sleep(0.25)


def find_first_add_button(settings, region):
    """Topmost (+) in the result list. Matched in colour so the green 'already added' tick doesn't count."""
    import pyautogui

    tpl = _template(settings, ADD_BUTTON)
    deadline = time.monotonic() + settings.timeout
    while True:
        try:
            boxes = list(pyautogui.locateAllOnScreen(tpl, confidence=settings.confidence, region=region))
        except pyautogui.ImageNotFoundException:
            boxes = []
        if boxes:
            return pyautogui.center(min(boxes, key=lambda b: b.top))
        if time.monotonic() >= deadline:
            raise StepFailed(f"no (+) add button in the results within {settings.timeout:g}s (no match, or already added)")
        time.sleep(0.25)


def load_search_offset(templates):
    try:
        return tuple(json.loads((templates / SEARCH_OFFSET_FILE).read_text()))
    except (OSError, ValueError):
        return None


def missing_setup(settings):
    """Human-readable list of what still has to be captured before a real run."""
    missing = [n for n in (ANCHOR, ADD_BUTTON) if not (settings.templates / n).exists()]
    if settings.search_offset is None:
        missing.append("search box position")
    return missing


# --- Main flow ------------------------------------------------------------------------------

def add_track(track, settings):
    import pyautogui
    import pyperclip

    win = find_spotify_window()
    focus_window(win)
    win_region = (max(win.left, 0), max(win.top, 0), win.width, win.height)

    ax, ay = pyautogui.center(find_anchor(settings, win_region))
    sx, sy = ax + settings.search_offset[0], ay + settings.search_offset[1]

    pyautogui.click(sx, sy)
    pyautogui.hotkey("ctrl", "a")
    pyperclip.copy(track.query)
    pyautogui.hotkey("ctrl", "v")
    # The list shows the previous results/suggestions until the new search loads; don't click those.
    time.sleep(settings.settle)

    # The (+) buttons sit right of the search box's middle; looking only there keeps the
    # playlist's own track list (left of the panel) out of the match.
    rows_top = sy + ROWS_BELOW_SEARCH
    rows_left = sx
    rows_region = (rows_left, rows_top, win.left + win.width - rows_left, win.top + win.height - rows_top)
    pyautogui.click(*find_first_add_button(settings, rows_region))
    pyautogui.moveTo(sx, sy)  # get off the row so its hover styling doesn't confuse the next match
    time.sleep(0.5)


def describe_plan(track, settings):
    return [
        "bring Spotify window to front",
        f"find {ANCHOR}, click the panel's search box (offset {settings.search_offset})",
        "Ctrl+A, paste " + json.dumps(track.query, ensure_ascii=False),
        f"wait {settings.settle:g}s, find topmost {ADD_BUTTON} in the results, click it",
    ]


def run_tracks(tracks, settings, log=print):
    """Add every track; returns (added, failed) where failed is a list of (track, reason)."""
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.15
    added, failed = [], []
    try:
        for i, t in enumerate(tracks, 1):
            try:
                add_track(t, settings)
            except StepFailed as e:
                failed.append((t, str(e)))
                log(f"[{i}/{len(tracks)}] {t}: FAILED - {e}")
            else:
                added.append(t)
                log(f"[{i}/{len(tracks)}] {t}: added")
    except pyautogui.FailSafeException:
        log("Aborted by failsafe (mouse in top-left corner).")
        done = {id(t) for t in added} | {id(t) for t, _ in failed}
        failed += [(t, "not attempted: run aborted") for t in tracks if id(t) not in done]
    return added, failed


def format_summary(added, failed):
    lines = ["=== Summary ===", f"Added:  {len(added)}"]
    lines += [f"  + {t}" for t in added]
    lines.append(f"Failed: {len(failed)}")
    lines += [f"  - {t}: {reason}" for t, reason in failed]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("songs_file", help="song list: " + ", ".join(SUPPORTED_SUFFIXES))
    parser.add_argument("--dry-run", action="store_true", help="print planned actions without touching the screen")
    parser.add_argument("--templates", type=Path, default=default_templates_dir(), help="template folder")
    parser.add_argument("--timeout", type=float, default=8.0, help="seconds to wait for each template (default 8)")
    parser.add_argument("--confidence", type=float, default=0.85, help="OpenCV match threshold 0-1 (default 0.85)")
    parser.add_argument("--settle", type=float, default=2.0, help="seconds to wait after pasting before matching")
    parser.add_argument("--search-offset", type=int, nargs=2, metavar=("DX", "DY"),
                        help=f"search box position relative to the bell icon's center "
                             f"(default: templates/{SEARCH_OFFSET_FILE})")
    parser.add_argument("--playlist", help="playlist name shown in messages (default: from the JSON)")
    args = parser.parse_args()
    # Track names may contain characters the console code page can't show; never crash on print.
    sys.stdout.reconfigure(errors="replace")

    try:
        playlist, tracks = read_tracks(args.songs_file)
    except (OSError, ValueError) as e:
        sys.exit(f"Cannot read {args.songs_file}: {e}")
    if not tracks:
        sys.exit(f"No songs found in {args.songs_file}")
    playlist = args.playlist or playlist or "the open playlist"
    if args.search_offset is None:
        args.search_offset = load_search_offset(args.templates)

    missing = missing_setup(args)
    for m in missing:
        print(f"WARNING: missing {m} - see README.md")

    print(f'{"[DRY RUN] " if args.dry_run else ""}Adding {len(tracks)} track(s) to "{playlist}"')
    print(f'Make sure "{playlist}" is open in Spotify with its "Add to playlist" panel showing.')

    if args.dry_run:
        for i, t in enumerate(tracks, 1):
            print(f"\n[{i}/{len(tracks)}] {t}")
            for step in describe_plan(t, args):
                print(f"  - {step}")
        print("\nDry run: nothing was clicked.")
        return
    if missing:
        sys.exit("Capture the templates first: python capture_templates.py")

    print("Move the mouse to the top-left corner of the screen to abort.")
    added, failed = run_tracks(tracks, args)
    print("\n" + format_summary(added, failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
