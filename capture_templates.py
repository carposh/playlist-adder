"""Interactively capture the template screenshots for spotify_add_tracks.py.

Usage:
    python capture_templates.py

Open your playlist in Spotify with its "Add to playlist" panel showing, then run this.
For each picture you get a few seconds to point the mouse at the top-left corner of the
thing to crop, then at its bottom-right corner. Nothing is clicked; you only point.
"""

import json
import time

import pyautogui

from spotify_add_tracks import ADD_BUTTON, ANCHOR, SCRIPT_DIR, SEARCH_OFFSET_FILE

TEMPLATES = SCRIPT_DIR / "templates"
SECONDS = 5


def wait_for_point(prompt):
    print(f"  {prompt}")
    for s in range(SECONDS, 0, -1):
        print(f"    {s}...", end="\r", flush=True)
        time.sleep(1)
    x, y = pyautogui.position()
    print(f"    got ({x}, {y})  ")
    return x, y


def capture(name, setup):
    print(f"\n=== {name} ===")
    path = TEMPLATES / name
    if path.exists() and input("  Already captured. Keep it? [Y/n] ").strip().lower() != "n":
        return None
    print(setup)
    input("Press Enter here when ready (then you have a few seconds per point)... ")
    while True:
        x1, y1 = wait_for_point("Point at the TOP-LEFT corner of the area to crop")
        x2, y2 = wait_for_point("Point at the BOTTOM-RIGHT corner")
        left, top = min(x1, x2), min(y1, y2)
        w, h = abs(x2 - x1), abs(y2 - y1)
        if w >= 8 and h >= 8:
            break
        print("  That area is too small (under 8x8 px), try again.")
    # The mouse is still over the area, which can light it up (hover); let the user move it off first.
    print("  Now move the mouse AWAY from that area - capturing in 3 seconds...")
    time.sleep(3)
    pyautogui.screenshot(region=(left, top, w, h)).save(path)
    print(f"  saved {path} ({w}x{h})")
    return left, top, w, h


def main():
    TEMPLATES.mkdir(exist_ok=True)
    print("Keep this console beside Spotify so it doesn't cover the \"Add to playlist\" panel.")

    bell = capture(
        ANCHOR,
        "Crop the notifications (bell) icon in Spotify's top bar - just the bell.\n"
        "If it has a dot for new notifications, open and close notifications first so the dot is gone.",
    )
    if bell is None:
        # Kept the old bell picture: find it on screen to measure the search box from it.
        try:
            box = pyautogui.locateOnScreen(str(TEMPLATES / ANCHOR), confidence=0.85, grayscale=True)
        except pyautogui.ImageNotFoundException:
            box = None
        if box is None:
            raise SystemExit(f"Can't find the saved bell on screen. Delete templates\\{ANCHOR} and run again.")
        bell = (box.left, box.top, box.width, box.height)
    left, top, w, h = bell
    print("\nNow show me where the panel's search box is.")
    input("Press Enter, then point at the middle of the search box... ")
    sx, sy = wait_for_point("Point at the search box")
    offset = [sx - (left + w // 2), sy - (top + h // 2)]
    (TEMPLATES / SEARCH_OFFSET_FILE).write_text(json.dumps(offset))
    print(f"  saved search box offset {offset}")

    capture(
        ADD_BUTTON,
        "Crop one of the round (+) buttons at the right end of a song row - just the circle.",
    )
    print("\nDone. Now run:\n  .venv\\Scripts\\python spotify_add_tracks.py example_tracks.json")


if __name__ == "__main__":
    main()
