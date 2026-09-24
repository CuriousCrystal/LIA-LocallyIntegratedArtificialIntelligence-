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
import panel as panel_module
from config import IDLE_MINUTES, DATA_DIR, TRAINING_PANEL_ENABLED, VRM_ENABLED
from make_icon import ensure_icon, ICO_PATH as ICON_FILE

# DATA_DIR, not __file__: inside a packaged .exe __file__ lives in a temporary
# unpack folder that's deleted on exit, taking the log with it.
LOG_PATH = Path(DATA_DIR) / "lia.log"


# ------------------------------------------------------------------ logging ---

class _Fanout:
    """Writes to every stream given, skipping the ones that are None.

    TeeLog only ever took a single "also" stream, which was fine when the
    console was the only optional second target -- now the training panel
    can be live at the same time as --debug's console, so both need to
    receive everything without TeeLog needing to know either exists.
    """

    def __init__(self, *streams):
        self._streams = [s for s in streams if s is not None]

    def write(self, text):
        for s in self._streams:
            try:
                s.write(text)
            except Exception:
                pass

    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass


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
    """Your icon -- assets/lia.ico if make_icon.py has built one from an image
    you dropped into LIA/assets/, else the drawn purple cat face. A small
    state dot is overlaid: green listening, purple speaking, dim neither.
    Outline only when she isn't listening; an open "meow" mouth in place of
    the old inner dot for speaking, since a circle-in-a-circle doesn't mean
    anything on a cat."""
    from PIL import Image, ImageDraw

    custom = None
    try:
        if ICON_FILE.is_file():
            custom = Image.open(ICON_FILE).convert("RGBA")
    except Exception:
        custom = None
    if custom is not None:
        size = 64
        custom = custom.resize((size, size), Image.LANCZOS)
        dot_color = (80, 220, 120, 255) if listening else (
            (155, 111, 217, 255) if speaking else (120, 120, 128, 160))
        d = ImageDraw.Draw(custom)
        d.ellipse((48, 48, 62, 62), fill=(30, 30, 34, 255), outline=dot_color, width=3)
        return custom

    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    purple = (155, 111, 217, 255)
    purple_dim = (155, 111, 217, 90)
    inner_ear = (196, 162, 232, 255)
    ink = (28, 26, 32, 255)

    head = (10, 18, 54, 58)
    left_ear = [(14, 24), (6, 4), (27, 17)]
    right_ear = [(50, 24), (58, 4), (37, 17)]
    left_ear_inner = [(15, 19), (10, 8), (23, 16)]
    right_ear_inner = [(49, 19), (54, 8), (41, 16)]

    if not listening:
        draw.polygon(left_ear, outline=purple_dim, width=3)
        draw.polygon(right_ear, outline=purple_dim, width=3)
        draw.ellipse(head, outline=purple_dim, width=4)
        return image

    draw.polygon(left_ear, fill=purple)
    draw.polygon(right_ear, fill=purple)
    draw.polygon(left_ear_inner, fill=inner_ear)
    draw.polygon(right_ear_inner, fill=inner_ear)
    draw.ellipse(head, fill=purple)

    # whiskers, drawn under the face so the head's fill covers their roots
    for y in (36, 42):
        draw.line([(0, y), (14, y - 2 if y == 36 else y + 2)], fill=ink, width=1)
        draw.line([(size, y), (size - 14, y - 2 if y == 36 else y + 2)], fill=ink, width=1)

    draw.ellipse((21, 30, 28, 39), fill=ink)
    draw.ellipse((36, 30, 43, 39), fill=ink)
    draw.polygon([(30, 41), (34, 41), (32, 45)], fill=(232, 168, 124, 255))

    if speaking:
        draw.ellipse((28, 46, 36, 54), fill=ink)
    else:
        draw.arc((26, 43, 38, 51), start=20, end=160, fill=ink, width=2)

    return image


# ---------------------------------------------------------------------- app ---

class LiaApp:
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.controls = lia.Controls(headless=not debug)
        self.icon = None
        self._thread = None
        self.panel = None
        self.avatar = None
        self.use_vrm = VRM_ENABLED
        if self.use_vrm:
            try:
                import vrm as vrm_module
                model = vrm_module.find_model()
            except ImportError:
                vrm_module, model = None, None
            if model is not None:
                self.avatar = vrm_module.VrmMascot(
                    model,
                    state_fn=self._avatar_state,
                    on_click=self.open_chat,
                    menu_fn=self._avatar_menu,
                )
            else:
                print("[avatar: no .vrm model in LIA/vrm/ -- drop one in and "
                      "restart, or see vrm/README.md]")
        # The chat panel (type, or its mic button for one recorded question)
        # is her only input surface now -- background listening is off by
        # default (LISTEN_ENABLED). Always created, not just under
        # TRAINING_PANEL_ENABLED: clicking her avatar opens it. The Panel
        # object itself is cheap (see panel.Panel) and made here, not in
        # run(): cli() needs it to exist before the log redirect is set up, so
        # the very first startup line printed already reaches it -- its
        # actual window is built later, in run(), on the thread that will own
        # it for its whole life.
        if TRAINING_PANEL_ENABLED or self.avatar is not None:
            self.panel = panel_module.Panel()
            self.controls.panel_keys = self.panel

    # -- menu actions ------------------------------------------------------

    def _listening(self) -> bool:
        return bool(self.controls.state.get("listening"))

    def _speaking(self) -> bool:
        return bool(self.controls.speaker and self.controls.speaker.enabled)

    def toggle_listening(self, *_):
        self.controls.state["listening"] = not self._listening()
        self._refresh()

    def open_chat(self, *_):
        """Her avatar's click action: show the chat panel instead of
        toggling background listening -- typing (or its mic button) is the
        way in now, not an always-open microphone."""
        if self.panel is not None:
            self.panel.show()

    def toggle_voice(self, *_):
        speaker = self.controls.speaker
        if speaker is None:
            return
        speaker.enabled = not speaker.enabled
        if not speaker.enabled:
            speaker.drop_pending()
        self._refresh()

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
        if self.panel is not None:
            self.panel.quit_requested.set()
        if self.avatar is not None:
            self.avatar.stop()

    def _refresh(self):
        if self.icon is not None:
            self.icon.icon = make_icon(self._listening(), self._speaking())
            self.icon.update_menu()

    # -- desktop avatar (VRM) ---------------------------------------------

    def _avatar_state(self) -> str:
        c = self.controls
        if c.speaker is not None and c.speaker.is_busy() and c.speaker.enabled:
            return "speaking"
        if c.thinking.is_set():
            return "thinking"
        if self._listening():
            return "listening"
        return "idle"

    def _avatar_menu(self):
        return [
            ("Open chat", self.open_chat),
            (f"Background listening: {'on' if self._listening() else 'off'}", self.toggle_listening),
            (f"Speaking: {'on' if self._speaking() else 'off'}", self.toggle_voice),
            ("-", None),
            ("Bigger", lambda: self.avatar and self.avatar.resize(40)),
            ("Smaller", lambda: self.avatar and self.avatar.resize(-40)),
            ("-", None),
            ("Open log", self.open_log),
            ("-", None),
            ("Hide avatar", lambda: self.avatar and self.avatar.hide()),
            ("Quit", self.quit),
        ]

    # -- lifecycle ---------------------------------------------------------

    def _run_conversation(self):
        try:
            lia.main(self.controls)
        except Exception:
            traceback.print_exc()
        finally:
            # If the conversation loop dies, don't leave a zombie tray icon,
            # panel window, or avatar behind.
            if self.icon is not None:
                self.icon.stop()
            if self.panel is not None:
                self.panel.quit_requested.set()
            if self.avatar is not None:
                self.avatar.stop()

    def run(self):
        from pystray import Icon, Menu, MenuItem

        self._thread = threading.Thread(target=self._run_conversation, daemon=True)
        self._thread.start()

        menu = Menu(
            MenuItem("Lia is here", None, enabled=False),
            Menu.SEPARATOR,
            MenuItem("Open chat", self.open_chat),
            MenuItem("Background listening", self.toggle_listening, checked=lambda _: self._listening()),
            MenuItem("Speaking", self.toggle_voice, checked=lambda _: self._speaking()),
            Menu.SEPARATOR,
            MenuItem("Open log", self.open_log),
            Menu.SEPARATOR,
            MenuItem("Quit", self.quit),
        )

        self.icon = Icon("Lia", make_icon(True, False), "Lia", menu)

        # The avatar's pywebview loop must own the main thread (WebView2 is an
        # STA loop) -- so the tray icon runs on a daemon thread instead;
        # pystray documents that as safe on Windows, where its backend is a
        # per-thread Win32 message loop. With no avatar, the training panel
        # (Tkinter, which Windows tolerates off the main thread too, unlike
        # WebView2) takes the main thread as it always has; with an avatar,
        # the panel instead runs on its own thread, since the avatar already
        # claimed the main one.
        if self.avatar is not None:
            threading.Thread(target=self.icon.run, daemon=True).start()
            if self.panel is not None:
                # Panel.run() does both Tk() and mainloop() -- Tcl requires
                # the same thread for each, and this thread is not the main
                # one (the avatar owns that), so it must all happen here.
                threading.Thread(target=self.panel.run, kwargs={"start_hidden": True},
                                 daemon=True).start()
            self.avatar.mainloop()
        elif self.panel is not None:
            threading.Thread(target=self.icon.run, daemon=True).start()
            self.panel.run()
        else:
            self.icon.run()

        # Give her a moment to close out cleanly on the way out.
        self.controls.stop()
        if self._thread is not None:
            self._thread.join(timeout=30)


def cli():
    parser = argparse.ArgumentParser(description="Run Lia in the system tray.")
    parser.add_argument("--debug", action="store_true", help="keep the console and log live")
    args = parser.parse_args()

    # Your image, if you dropped one into assets/: rebuilt only when it is
    # newer than the .ico from last time, so this costs one stat call and a
    # line in the log when nothing changed.
    icon_note = ensure_icon()
    if icon_note:
        print(f"[icon: {icon_note}]")

    # Built before the log redirect below, not after: cli() needs app.panel
    # to exist so the very first line printed reaches the window too, not
    # just the ones printed once run() gets called.
    app = LiaApp(debug=args.debug)

    console = sys.stdout if args.debug else None
    log = TeeLog(LOG_PATH, also=_Fanout(console, app.panel))
    sys.stdout = log
    sys.stderr = log

    print(f"\n=== Lia starting (idle rollover after {IDLE_MINUTES} min) ===")
    app.run()
    print("=== Lia stopped ===")


if __name__ == "__main__":
    cli()
