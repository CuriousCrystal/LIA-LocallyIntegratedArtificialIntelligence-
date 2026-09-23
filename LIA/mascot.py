"""A little desktop character that shows what Lia is doing.

Frameless, always-on-top, click-through where the sprite isn't. It reflects one
state -- idle / listening / thinking / speaking -- read every ~150ms from a
callback the app hands in. Drag it anywhere (the position is remembered);
left-click toggles listening; right-click opens a menu.

Art lives in MASCOT_DIR, one entry per state:

    idle.png                 a single still frame
    listening-1.png ...       numbered frames animate at MASCOT_FPS
    thinking.gif              an animated GIF is unpacked into frames
    greeting-1.png ...        optional -- plays once at startup, then idle

A state with no art of its own falls back to `idle`'s frames, so one `idle.png`
covers everything; with no art at all a plain drawn cat face is used. See
mascot/README.md.

Run it on its own to preview your art:

    python LIA\\mascot.py            cycles through the states
"""

import json
import time
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageDraw, ImageSequence, ImageTk

from config import (
    MASCOT_DIR, MASCOT_SIZE, MASCOT_FPS, MASCOT_CHROMA, MASCOT_POS_FILE,
)

STATES = ("idle", "listening", "thinking", "speaking")
_EXTS = (".png", ".gif", ".webp")

# The sprite is drawn a little smaller than the window so it never touches the
# edges, whatever its aspect ratio.
_MARGIN = max(6, round(MASCOT_SIZE * 0.10))


def _load_state_frames(state: str) -> list[Image.Image]:
    """Every frame for one state, as RGBA PIL images, or [] if there is no art.

    Looks for numbered frames (`state-1.png`, `state-2.png`, ...) first, then a
    single `state.png`, then an animated `state.gif`.
    """
    folder = Path(MASCOT_DIR)
    if not folder.is_dir():
        return []

    numbered = sorted(
        (p for p in folder.glob(f"{state}-*") if p.suffix.lower() in _EXTS),
        key=lambda p: _frame_number(p.stem),
    )
    if numbered:
        return [Image.open(p).convert("RGBA") for p in numbered]

    for ext in _EXTS:
        single = folder / f"{state}{ext}"
        if single.exists():
            im = Image.open(single)
            frames = [f.convert("RGBA") for f in ImageSequence.Iterator(im)]
            return frames or [im.convert("RGBA")]

    return []


def _frame_number(stem: str) -> int:
    tail = stem.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def _placeholder(state: str) -> Image.Image:
    """The drawn purple cat face, used for any state with no art. Same identity
    as the tray icon; the mouth and ears move with the state."""
    s = 128
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    purple = (155, 111, 217, 255)
    inner = (196, 162, 232, 255)
    ink = (28, 26, 32, 255)

    ears_up = state in ("listening", "thinking")
    lift = -6 if ears_up else 0
    d.polygon([(28, 48 + lift), (12, 8 + lift), (54, 34 + lift)], fill=purple)
    d.polygon([(100, 48 + lift), (116, 8 + lift), (74, 34 + lift)], fill=purple)
    d.polygon([(30, 40 + lift), (20, 16 + lift), (46, 33 + lift)], fill=inner)
    d.polygon([(98, 40 + lift), (108, 16 + lift), (82, 33 + lift)], fill=inner)
    d.ellipse((20, 36, 108, 116), fill=purple)

    for y in (74, 86):
        d.line([(0, y), (28, y - 3)], fill=ink, width=2)
        d.line([(s, y), (s - 28, y - 3)], fill=ink, width=2)

    if state == "thinking":                       # half-closed, looking up
        d.arc((42, 58, 60, 74), start=180, end=360, fill=ink, width=3)
        d.arc((72, 58, 90, 74), start=180, end=360, fill=ink, width=3)
    else:
        d.ellipse((44, 58, 58, 76), fill=ink)
        d.ellipse((74, 58, 88, 76), fill=ink)
    d.polygon([(60, 82), (68, 82), (64, 90)], fill=(232, 168, 124, 255))

    if state == "speaking":
        d.ellipse((56, 92, 72, 108), fill=ink)
    else:
        d.arc((52, 86, 76, 102), start=20, end=160, fill=ink, width=3)
    return im


class Mascot:
    def __init__(self, state_fn=None, on_click=None, menu_fn=None):
        """state_fn() -> one of STATES (or "greeting"). on_click() fires on a
        left click that wasn't a drag. menu_fn() -> list of (label, callback)
        or ("-", None) for a separator, rebuilt each right-click."""
        self._state_fn = state_fn or (lambda: "idle")
        self._on_click = on_click or (lambda: None)
        self._menu_fn = menu_fn or (lambda: [])

        self.root = tk.Tk()
        self.root.overrideredirect(True)              # no title bar / border
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-transparentcolor", MASCOT_CHROMA)
        except tk.TclError:
            pass                                     # non-Windows: no per-window chroma
        self.root.config(bg=MASCOT_CHROMA)

        self.canvas = tk.Canvas(
            self.root, width=MASCOT_SIZE, height=MASCOT_SIZE,
            bg=MASCOT_CHROMA, highlightthickness=0, bd=0,
        )
        self.canvas.pack()
        self._cx = self._cy = MASCOT_SIZE // 2
        self._img_id = self.canvas.create_image(self._cx, self._cy)

        # state name -> list of Tk PhotoImages, already matted onto the chroma
        # colour and scaled to MASCOT_SIZE. A state with no art of its own
        # borrows `idle`'s frames; with no art anywhere, the drawn cat face.
        raw = {name: _load_state_frames(name) for name in (*STATES, "greeting")}
        self._frames: dict[str, list[ImageTk.PhotoImage]] = {}
        for name in STATES:
            self._frames[name] = self._prepare(
                raw[name] or raw["idle"] or [_placeholder(name)])
        self._frames["greeting"] = self._prepare(raw["greeting"])   # empty is fine

        self._state = "greeting" if self._frames["greeting"] else self._state_fn()
        self._oneshot = self._state == "greeting"
        self._frame_i = 0

        self._place()
        self._bind()
        self.root.after(0, self._animate)
        self.root.after(150, self._poll_state)

    # -- image pipeline --------------------------------------------------------

    def _prepare(self, pil_frames: list[Image.Image]) -> list[ImageTk.PhotoImage]:
        out = []
        inner = MASCOT_SIZE - 2 * _MARGIN
        for im in pil_frames:
            w, h = im.size
            scale = inner / max(w, h)
            im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                           Image.LANCZOS)
            flat = Image.new("RGB", (MASCOT_SIZE, MASCOT_SIZE), MASCOT_CHROMA)
            off = ((MASCOT_SIZE - im.width) // 2, (MASCOT_SIZE - im.height) // 2)
            if im.mode == "RGBA":
                # A hard mask, not the soft resized alpha. Compositing a
                # feathered edge onto the magenta key leaves partly-magenta
                # pixels that -transparentcolor can't punch out, so the sprite
                # wears a pink halo on the desktop. A crisp edge scaled small
                # reads fine; the glow doesn't.
                flat.paste(im, off, im.split()[3].point(lambda v: 255 if v >= 128 else 0))
            else:
                flat.paste(im, off)
            out.append(ImageTk.PhotoImage(flat))
        return out

    # -- window placement ---------------------------------------------------

    def _place(self):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = sw - MASCOT_SIZE - 40, sh - MASCOT_SIZE - 80   # bottom-right by default
        try:
            saved = json.loads(Path(MASCOT_POS_FILE).read_text())
            x, y = int(saved["x"]), int(saved["y"])
        except Exception:
            pass
        x = max(0, min(x, sw - MASCOT_SIZE))          # never off-screen
        y = max(0, min(y, sh - MASCOT_SIZE))
        self.root.geometry(f"{MASCOT_SIZE}x{MASCOT_SIZE}+{x}+{y}")

    def _save_pos(self):
        try:
            Path(MASCOT_POS_FILE).write_text(json.dumps(
                {"x": self.root.winfo_x(), "y": self.root.winfo_y()}))
        except Exception:
            pass

    # -- input ------------------------------------------------------------

    def _bind(self):
        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Button-3>", self._popup)

    def _press(self, e):
        self._drag_from = (e.x, e.y)
        self._moved = 0

    def _drag(self, e):
        dx, dy = e.x - self._drag_from[0], e.y - self._drag_from[1]
        self._moved += abs(dx) + abs(dy)
        self.root.geometry(f"+{self.root.winfo_x() + dx}+{self.root.winfo_y() + dy}")

    def _release(self, _e):
        if self._moved < 5:
            self._on_click()
        else:
            self._save_pos()

    def _popup(self, e):
        menu = tk.Menu(self.root, tearoff=0)
        for label, cb in self._menu_fn():
            if label == "-" or cb is None:
                menu.add_separator()
            else:
                menu.add_command(label=label, command=cb)
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()

    # -- loops ----------------------------------------------------------

    def _poll_state(self):
        if not self._oneshot:
            want = self._state_fn()
            if want in self._frames and self._frames[want] and want != self._state:
                self._state = want
                self._frame_i = 0
        self.root.after(150, self._poll_state)

    def _animate(self):
        frames = self._frames.get(self._state) or self._frames["idle"]
        if frames:
            self._frame_i %= len(frames)
            self.canvas.itemconfig(self._img_id, image=frames[self._frame_i])
            self._frame_i += 1
            if self._oneshot and self._frame_i >= len(frames):
                self._oneshot = False
                self._state = self._state_fn()
                self._frame_i = 0

        # Every state sits still. (The dance bob went with the music player.)
        self.canvas.coords(self._img_id, self._cx, self._cy)

        self.root.after(int(1000 / max(1, MASCOT_FPS)), self._animate)

    # -- lifecycle ----------------------------------------------------

    def hide(self):
        self.root.withdraw()

    def show(self):
        self.root.deiconify()

    def stop(self):
        try:
            self._save_pos()
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def mainloop(self):
        self.root.mainloop()


# ---------------------------------------------------------------- preview ---

if __name__ == "__main__":
    import itertools

    cycle = itertools.cycle(STATES)
    current = {"s": next(cycle)}

    m = Mascot(
        state_fn=lambda: current["s"],
        on_click=lambda: print("click"),
        menu_fn=lambda: [("Next state", lambda: current.update(s=next(cycle))),
                         ("-", None), ("Quit", lambda: m.stop())],
    )
    print("mascot preview -- right-click to step through states, or wait")

    def step():
        current["s"] = next(cycle)
        print("state:", current["s"])
        m.root.after(2000, step)

    m.root.after(2000, step)
    m.mainloop()
