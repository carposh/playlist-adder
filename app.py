"""Playlist Adder: window app around spotify_add_tracks.

Load a song list (JSON, CSV, TXT, M3U) or paste one, set up the screen pictures once,
then press Start while the playlist's "Add to playlist" panel is open in Spotify.
"""

import json
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from types import SimpleNamespace

# pyautogui makes the process DPI-aware on import; do it before Tk so screen and window coordinates agree.
import pyautogui

import spotify_add_tracks as core

APP_NAME = "Playlist Adder"
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", core.SCRIPT_DIR))
COUNTDOWN = 5

FILE_TYPES = [
    ("Song lists", " ".join(f"*{s}" for s in core.SUPPORTED_SUFFIXES)),
    ("Text, one song per line", "*.txt"),
    ("CSV / spreadsheet export", "*.csv *.tsv"),
    ("JSON", "*.json"),
    ("Playlist file", "*.m3u *.m3u8"),
    ("All files", "*.*"),
]


def seed_templates(templates):
    """First run of the installed app: start from the pictures bundled with it, if any."""
    bundled = RESOURCE_DIR / "default_templates"
    templates.mkdir(parents=True, exist_ok=True)
    if bundled.is_dir() and not any(templates.iterdir()):
        for f in bundled.iterdir():
            shutil.copy2(f, templates / f.name)


class App:
    def __init__(self, root):
        self.root = root
        self.templates = core.default_templates_dir()
        seed_templates(self.templates)
        self.ui_queue = queue.Queue()
        self.running = False
        self.setup_window = None

        root.title(APP_NAME)
        root.minsize(560, 560)
        icon = RESOURCE_DIR / "icon.ico"
        if icon.exists():
            root.iconbitmap(default=str(icon))

        main = ttk.Frame(root, padding=12)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="In Spotify, open your playlist and its \"Add to playlist\" panel, then press Start.",
                  wraplength=520).pack(anchor="w")

        # Songs
        songs = ttk.LabelFrame(main, text="Songs", padding=8)
        songs.pack(fill="both", expand=True, pady=(10, 0))
        bar = ttk.Frame(songs)
        bar.pack(fill="x")
        ttk.Button(bar, text="Open file…", command=self.open_file).pack(side="left")
        ttk.Button(bar, text="Clear", command=lambda: self.songs_text.delete("1.0", "end")).pack(side="left", padx=6)
        self.count_label = ttk.Label(bar, text="")
        self.count_label.pack(side="right")
        ttk.Label(songs, text="TXT, CSV, JSON or M3U, or paste below: one song per line, like  Queen - Bohemian Rhapsody",
                  foreground="#666").pack(anchor="w", pady=(6, 2))
        self.songs_text = tk.Text(songs, height=12, wrap="none", undo=True)
        self.songs_text.pack(fill="both", expand=True)
        self.songs_text.bind("<<Modified>>", self._on_songs_changed)

        # Setup + options
        opts = ttk.Frame(main)
        opts.pack(fill="x", pady=(10, 0))
        self.setup_label = ttk.Label(opts, text="")
        self.setup_label.pack(side="left")
        ttk.Button(opts, text="Set up screen pictures…", command=self.open_setup).pack(side="right")

        opts2 = ttk.Frame(main)
        opts2.pack(fill="x", pady=(6, 0))
        ttk.Label(opts2, text="Wait for search results (seconds):").pack(side="left")
        self.settle = tk.DoubleVar(value=2.0)
        ttk.Spinbox(opts2, from_=0.5, to=10, increment=0.5, width=5, textvariable=self.settle).pack(side="left", padx=4)
        self.dry_run = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts2, text="Practice run (don't click anything)", variable=self.dry_run).pack(side="left", padx=12)

        run = ttk.Frame(main)
        run.pack(fill="x", pady=(10, 0))
        self.start_button = ttk.Button(run, text="Start", command=self.start)
        self.start_button.pack(side="left")
        ttk.Label(run, text="To stop: move the mouse to the top-left corner of the screen.",
                  foreground="#666").pack(side="left", padx=10)

        self.log_text = tk.Text(main, height=9, state="disabled", wrap="word", background="#f6f6f6")
        self.log_text.pack(fill="both", expand=True, pady=(10, 0))

        self.refresh_setup_status()
        self._on_songs_changed()
        self.root.after(100, self._drain_queue)

    # --- thread plumbing: workers post callables here, the Tk thread runs them ------------

    def post(self, fn, *args):
        self.ui_queue.put((fn, args))

    def _drain_queue(self):
        try:
            while True:
                fn, args = self.ui_queue.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_queue)

    # --- songs ------------------------------------------------------------------------------

    def open_file(self, path=None):
        path = path or filedialog.askopenfilename(title="Open song list", filetypes=FILE_TYPES)
        if not path:
            return
        try:
            _, tracks = core.read_tracks(path)
        except (OSError, ValueError) as e:
            messagebox.showerror(APP_NAME, f"Couldn't read that file:\n{e}")
            return
        if not tracks:
            messagebox.showwarning(APP_NAME, "No songs found in that file.")
            return
        self.songs_text.delete("1.0", "end")
        self.songs_text.insert("1.0", "\n".join(str(t) for t in tracks))
        self.songs_text.edit_reset()  # Ctrl+Z shouldn't undo the whole load
        self.log(f"Loaded {len(tracks)} songs from {Path(path).name}")

    def tracks(self):
        return core.parse_lines(self.songs_text.get("1.0", "end"))

    def _on_songs_changed(self, _event=None):
        self.songs_text.edit_modified(False)
        n = len(self.tracks())
        self.count_label.config(text=f"{n} song{'s' if n != 1 else ''}")

    # --- setup state ------------------------------------------------------------------------

    def settings(self):
        return SimpleNamespace(
            templates=self.templates, timeout=8.0, confidence=0.85,
            settle=float(self.settle.get()), search_offset=core.load_search_offset(self.templates),
        )

    def refresh_setup_status(self):
        missing = core.missing_setup(self.settings())
        if missing:
            self.setup_label.config(text="Screen pictures: missing " + ", ".join(missing), foreground="#b00020")
        else:
            self.setup_label.config(text="Screen pictures: ready ✓", foreground="#1a7f37")

    def open_setup(self):
        if self.setup_window and self.setup_window.win.winfo_exists():
            self.setup_window.win.lift()
        else:
            self.setup_window = SetupWindow(self)

    # --- running ----------------------------------------------------------------------------

    def log(self, line):
        self.log_text.config(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def start(self):
        if self.running:
            return
        tracks = self.tracks()
        if not tracks:
            messagebox.showinfo(APP_NAME, "Add some songs first: open a file or paste a list.")
            return
        try:
            settings = self.settings()
        except (tk.TclError, ValueError):
            messagebox.showerror(APP_NAME, "The wait time must be a number.")
            return

        if self.dry_run.get():
            self.log(f"--- Practice run: {len(tracks)} songs, nothing will be clicked ---")
            for i, t in enumerate(tracks, 1):
                self.log(f"[{i}/{len(tracks)}] {t}")
                for step in core.describe_plan(t, settings):
                    self.log(f"    - {step}")
            return

        missing = core.missing_setup(settings)
        if missing:
            messagebox.showwarning(APP_NAME, "Set up the screen pictures first.\nMissing: " + ", ".join(missing))
            return

        self.running = True
        self.start_button.config(state="disabled")
        self.log(f"--- Adding {len(tracks)} songs. Hands off the mouse and keyboard. ---")
        self.root.iconify()  # keep this window from covering Spotify
        threading.Thread(target=self._run, args=(tracks, settings), daemon=True).start()

    def _run(self, tracks, settings):
        try:
            added, failed = core.run_tracks(tracks, settings, log=lambda line: self.post(self.log, line))
            self.post(self._finished, added, failed, None)
        except Exception as e:  # keep the window usable whatever happens on screen
            self.post(self._finished, [], [], e)

    def _finished(self, added, failed, error):
        self.running = False
        self.start_button.config(state="normal")
        self.root.deiconify()
        self.root.lift()
        if error:
            self.log(f"Stopped by an error: {error}")
            messagebox.showerror(APP_NAME, f"Stopped by an error:\n{error}")
            return
        self.log(core.format_summary(added, failed))
        msg = f"Added {len(added)} of {len(added) + len(failed)} songs."
        if failed:
            msg += "\n\nNot added:\n" + "\n".join(f"• {t}: {r}" for t, r in failed[:15])
            if len(failed) > 15:
                msg += f"\n…and {len(failed) - 15} more (see the log)."
        messagebox.showinfo(APP_NAME, msg)


class SetupWindow:
    """Small always-on-top window that captures the screen pictures by mouse pointing."""

    def __init__(self, app):
        self.app = app
        self.busy = False
        win = self.win = tk.Toplevel(app.root)
        win.title("Set up screen pictures")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        # Bottom-left corner, away from Spotify's top bar and its right-hand panel.
        win.geometry(f"+20+{max(win.winfo_screenheight() - 420, 0)}")

        f = ttk.Frame(win, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Open your playlist's \"Add to playlist\" panel in Spotify first.\n"
                          "Don't let this window cover the bell or the panel (you can drag it).",
                  wraplength=380).pack(anchor="w")

        self.rows = {}
        for key, label, action in (
            (core.ANCHOR, "Notifications bell (top bar)", self.capture_bell),
            ("search", "Search box in the panel", self.point_search),
            (core.ADD_BUTTON, "(+) button on a song row", self.capture_add),
        ):
            row = ttk.Frame(f)
            row.pack(fill="x", pady=3)
            status = ttk.Label(row, width=3)
            status.pack(side="left")
            ttk.Label(row, text=label, width=30).pack(side="left")
            ttk.Button(row, text="Capture", command=action).pack(side="right")
            self.rows[key] = status

        ttk.Button(f, text="Check it can see them now", command=self.check).pack(anchor="w", pady=(8, 0))
        self.instructions = ttk.Label(f, text="", wraplength=380, font=("Segoe UI", 11, "bold"), foreground="#0b57d0")
        self.instructions.pack(anchor="w", pady=(10, 0))
        self.refresh()

    def refresh(self):
        settings = self.app.settings()
        done = {
            core.ANCHOR: (self.app.templates / core.ANCHOR).exists(),
            "search": settings.search_offset is not None,
            core.ADD_BUTTON: (self.app.templates / core.ADD_BUTTON).exists(),
        }
        for key, label in self.rows.items():
            label.config(text="✓" if done[key] else "✗", foreground="#1a7f37" if done[key] else "#b00020")
        self.app.refresh_setup_status()

    def say(self, text):
        self.app.post(self.instructions.config, {"text": text})

    def _in_thread(self, fn):
        if self.busy:
            return
        self.busy = True

        def run():
            try:
                fn()
            except Exception as e:
                self.say(f"Something went wrong: {e}")
            finally:
                self.busy = False
                self.app.post(self.refresh)

        threading.Thread(target=run, daemon=True).start()

    def _point(self, prompt):
        for s in range(COUNTDOWN, 0, -1):
            self.say(f"{prompt}… {s}")
            time.sleep(1)
        return pyautogui.position()

    def _crop(self, name, what):
        while True:
            x1, y1 = self._point(f"Point at the TOP-LEFT corner of {what}")
            x2, y2 = self._point(f"Now the BOTTOM-RIGHT corner of {what}")
            w, h = abs(x2 - x1), abs(y2 - y1)
            if w >= 8 and h >= 8:
                break
            self.say("That was too small (under 8×8 pixels). Again…")
            time.sleep(1.5)
        for s in range(3, 0, -1):
            self.say(f"Move the mouse AWAY from it… {s}")
            time.sleep(1)
        self.app.templates.mkdir(parents=True, exist_ok=True)
        pyautogui.screenshot(region=(min(x1, x2), min(y1, y2), w, h)).save(self.app.templates / name)
        self.say(f"Saved ({w}×{h}).")

    def capture_bell(self):
        self._in_thread(lambda: self._crop(
            core.ANCHOR, "the bell (no new-notification dot)"))

    def capture_add(self):
        self._in_thread(lambda: self._crop(core.ADD_BUTTON, "one (+) circle"))

    def _find_bell(self):
        try:
            box = pyautogui.locateOnScreen(str(self.app.templates / core.ANCHOR), confidence=0.85, grayscale=True)
        except (pyautogui.ImageNotFoundException, OSError, ValueError):
            box = None
        return box

    def point_search(self):
        def work():
            if not (self.app.templates / core.ANCHOR).exists():
                self.say("Capture the bell first.")
                return
            box = self._find_bell()
            if box is None:
                self.say("Can't see the bell on screen right now. Is Spotify visible? If so, capture the bell again.")
                return
            bx, by = pyautogui.center(box)
            sx, sy = self._point("Point at the middle of the panel's Search box")
            (self.app.templates / core.SEARCH_OFFSET_FILE).write_text(json.dumps([sx - bx, sy - by]))
            self.say("Saved the search box position.")

        self._in_thread(work)

    def check(self):
        def work():
            try:
                win = core.find_spotify_window()
            except core.StepFailed as e:
                self.say(str(e))
                return
            core.focus_window(win)
            bell = self._find_bell()
            if bell is None:
                self.say("✗ Can't find the bell. Capture it again.")
                return
            try:
                pluses = list(pyautogui.locateAllOnScreen(
                    str(self.app.templates / core.ADD_BUTTON), confidence=0.85))
            except (pyautogui.ImageNotFoundException, OSError, ValueError):
                pluses = []
            self.say(f"✓ Bell found. {len(pluses)} (+) button(s) visible"
                     + (" ✓" if pluses else " - open the panel, or capture the (+) again."))

        self._in_thread(work)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    app = App(root)
    if len(sys.argv) > 1:  # a song file dropped on the exe or opened with it
        app.open_file(sys.argv[1])
    root.mainloop()


if __name__ == "__main__":
    main()
