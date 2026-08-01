"""
Lia as a background app.

No console window. She sits in the system tray, listens on the open mic, and
answers out loud -- which only works because voice activity detection removed
the need for a keyboard.

    pythonw LIA\\app.py          run it now, windowless
    python  LIA\\app.py --debug  run it with a console and live logging

Everything she prints goes to LIA\\lia.log, since there's nowhere else for it.
"""

import argparse
import sys
import threading
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import main as lia
from config import IDLE_MINUTES, DATA_DIR

# DATA_DIR, not __file__: inside a packaged .exe __file__ lives in a temporary
# unpack folder that's deleted on exit, taking the log with it.
LOG_PATH = Path(DATA_DIR) / "lia.log"


# ------------------------------------------------------------------ logging ---

class TeeLog:
    """Write to the log file, and to the console too when there is one."""

    def __init__(self, path: Path, also=None):
        self._file = open(path, "a", encoding="utf-8", buffering=1)
        self._also = also

    def write(self, text):
        try:
            self._file.write(text)
        except Exception:
            pass
        if self._also is not None:
            try:
                self._also.write(text)
            except Exception:
                pass
        return len(text)

    def flush(self):
        try:
            self._file.flush()
        except Exception:
            pass
        if self._also is not None:
            try:
                self._also.flush()
            except Exception:
                pass

    def isatty(self):
        return False


# --------------------------------------------------------------------- icon ---

def make_icon(listening: bool, speaking: bool):
    """A small warm dot. Hollow when she isn't listening."""
    from PIL import Image, ImageDraw

    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    warm = (232, 168, 124, 255)
    dim = (232, 168, 124, 90)

    if listening:
        draw.ellipse((8, 8, size - 8, size - 8), fill=warm)
        if speaking:
            draw.ellipse((22, 22, size - 22, size - 22), fill=(28, 26, 32, 255))
    else:
        draw.ellipse((8, 8, size - 8, size - 8), outline=dim, width=5)

    return image


# ---------------------------------------------------------------------- app ---

class LiaApp:
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.controls = lia.Controls(headless=not debug)
        self.icon = None
        self._thread = None

    # -- menu actions ------------------------------------------------------

    def _listening(self) -> bool:
        return bool(self.controls.state.get("listening"))

    def _speaking(self) -> bool:
        return bool(self.controls.speaker and self.controls.speaker.enabled)

    def toggle_listening(self, *_):
        self.controls.state["listening"] = not self._listening()
        self._refresh()

    def toggle_voice(self, *_):
        speaker = self.controls.speaker
        if speaker is None:
            return
        speaker.enabled = not speaker.enabled
        if not speaker.enabled:
            speaker.drop_pending()
        self._refresh()

    def close_out(self, *_):
        self.controls.close_now.set()

    def open_log(self, *_):
        import os

        try:
            os.startfile(LOG_PATH)
        except Exception:
            pass

    def quit(self, *_):
        self.controls.stop()
        if self.icon is not None:
            self.icon.stop()

    def _refresh(self):
        if self.icon is not None:
            self.icon.icon = make_icon(self._listening(), self._speaking())
            self.icon.update_menu()

    # -- lifecycle ---------------------------------------------------------

    def _run_conversation(self):
        try:
            lia.main(self.controls)
        except Exception:
            traceback.print_exc()
        finally:
            # If the conversation loop dies, don't leave a zombie tray icon.
            if self.icon is not None:
                self.icon.stop()

    def run(self):
        from pystray import Icon, Menu, MenuItem

        self._thread = threading.Thread(target=self._run_conversation, daemon=True)
        self._thread.start()

        menu = Menu(
            MenuItem("Lia is here", None, enabled=False),
            Menu.SEPARATOR,
            MenuItem("Listening", self.toggle_listening, checked=lambda _: self._listening()),
            MenuItem("Speaking", self.toggle_voice, checked=lambda _: self._speaking()),
            Menu.SEPARATOR,
            MenuItem("Write diary now", self.close_out),
            MenuItem("Open log", self.open_log),
            Menu.SEPARATOR,
            MenuItem("Quit", self.quit),
        )

        self.icon = Icon("Lia", make_icon(True, False), "Lia", menu)
        self.icon.run()

        # Give her a moment to finish writing the diary on the way out.
        self.controls.stop()
        if self._thread is not None:
            self._thread.join(timeout=90)


def cli():
    parser = argparse.ArgumentParser(description="Run Lia in the system tray.")
    parser.add_argument("--debug", action="store_true", help="keep the console and log live")
    args = parser.parse_args()

    console = sys.stdout if args.debug else None
    log = TeeLog(LOG_PATH, also=console)
    sys.stdout = log
    sys.stderr = log

    print(f"\n=== Lia starting (idle rollover after {IDLE_MINUTES} min) ===")
    LiaApp(debug=args.debug).run()
    print("=== Lia stopped ===")


if __name__ == "__main__":
    cli()
