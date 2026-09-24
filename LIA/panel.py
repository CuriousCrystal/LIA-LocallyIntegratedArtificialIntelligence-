"""The chat window, styled after Claude Code's terminal -- white with warm
orange accents, her own icon on the title bar (see _set_icon), no header of
its own beyond that. Her only input surface: type and press Enter, or press
the mic button for one recorded question at a time, no console window and no
background listening needed. Clicking her avatar opens this window (see
app.py's open_chat); it starts hidden and stays that way between uses.

Built as a drop-in replacement for two things that already exist, so nothing
about the conversation pipeline needed to change:

- Keyboard (main.py): same .pending()/.take() interface, backed by a
  Tkinter Entry instead of stdin. read_input() cannot tell the difference,
  and the mic button's transcribed text arrives through that same queue.
- TeeLog's "also" stream (app.py): same .write()/.flush() interface, so
  everything she already prints reaches this window too, unchanged.
"""

import ctypes
import queue
import threading
import tkinter as tk
from tkinter import font as tkfont

from make_icon import ASSETS_DIR

WHITE = "#ffffff"
PANEL_BG = "#fdf6f4"   # warm cream-pink, close to the reference mockup
ROSE = "#c9587a"       # header/accent rose
ROSE_DIM = "#e8a3b8"   # lighter rose, for borders/hover/scrollbar trough
INK = "#1c1a20"        # same dark ink the tray dot uses when she's speaking
MUTED = "#8a8078"
LIME = "#7ab317"       # her name, in every reply she prints

NAME_FONT_FILE = ASSETS_DIR / "JimNightshade-Regular.ttf"
NAME_FONT_FAMILY = "Jim Nightshade"


def _load_name_font() -> str:
    """Register NAME_FONT_FILE for this process only (FR_PRIVATE: no system
    install, no admin rights, gone when the app exits) and return the family
    name to use. Falls back to the monospace family already used everywhere
    else in the panel if the file is missing or the registration fails --
    same best-effort pattern as _set_icon."""
    try:
        if NAME_FONT_FILE.is_file():
            FR_PRIVATE = 0x10
            added = ctypes.windll.gdi32.AddFontResourceExW(
                str(NAME_FONT_FILE), FR_PRIVATE, 0)
            if added and NAME_FONT_FAMILY in tkfont.families():
                return NAME_FONT_FAMILY
    except Exception:
        pass
    return ""


class Panel:
    """The chat window.

    Tk() and mainloop() must run on the same thread -- Tcl enforces this
    ("Calling Tcl from different apartment" if they don't) -- but callers
    (Controls.panel_keys, TeeLog's "also" stream) need a Panel object to hand
    around before that thread necessarily exists yet. So construction is
    split: __init__ only makes the thread-safe queues/events, cheap enough to
    call from anywhere; run() does the real Tk() and _build(), and must be
    called from -- and blocks on mainloop() on -- the one thread that will
    own this window for its whole life.
    """

    def __init__(self):
        self._input_queue: queue.Queue = queue.Queue()
        self._output_queue: queue.Queue = queue.Queue()
        # Set from the tray icon's own thread (its Quit menu item), read back
        # here on the GUI thread -- Event is the thread-safe part, root.quit()
        # itself only ever runs from _poll_output, i.e. on the thread that
        # owns it.
        self.quit_requested = threading.Event()
        # Set from another thread (the avatar's click, on pywebview's own
        # thread) and read back here on the GUI thread by _poll_output --
        # same pattern as quit_requested, since Tkinter widgets are only
        # safe to touch from the thread that created them.
        self.show_requested = threading.Event()
        # Set once run() has built the window, so a caller on another thread
        # (app.py, right after starting the panel's thread) can wait for it
        # to exist before touching .root or relying on early write() calls
        # reaching a real widget.
        self.ready = threading.Event()
        self.root = None
        # write() buffers here until a full line is known, so a [bracketed]
        # diagnostic or the startup banner can be recognised and dropped
        # before it ever reaches the widget -- see write()'s docstring.
        self._line_buf = ""
        # Where a header drag started, in screen coordinates -- overrideredirect
        # drops the window manager's own drag handling, so the header binds
        # its own (see _drag_start/_drag_move).
        self._drag_origin: tuple[int, int] | None = None

    def run(self, start_hidden: bool = False):
        """Build the window and run its event loop. Blocks until quit.

        Must be called from the thread that will own this window -- Tk()
        itself, not just mainloop(), has to happen here. start_hidden is for
        when she opens on the avatar's click rather than at startup -- set
        before mainloop() runs rather than withdrawn after, since by the time
        a caller on another thread could call show()/hide() the window may
        not exist yet.
        """
        self.root = tk.Tk()
        self._build()
        if start_hidden:
            self.root.withdraw()
        self.root.after(50, self._poll_output)
        self.ready.set()
        self.root.mainloop()

    def _build(self):
        self.root.title("Lia")
        width, height = 580, 440
        # A window manager normally places an unpositioned window somewhere
        # sensible on its own; overrideredirect (below) opts out of the
        # window manager entirely, which means an unpositioned geometry
        # string really does mean the screen's top-left corner, pinned there
        # -- so the position has to be picked here instead. Centered, as a
        # window manager's own default placement would roughly approximate.
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x, y = (sw - width) // 2, (sh - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.configure(bg=PANEL_BG)
        # Frameless: Windows' native title bar cannot render a custom font,
        # full stop -- no API for it. This is the only way "Lia" in the
        # header gets the same Jim Nightshade treatment as her replies. The
        # cost: no native taskbar entry either (which -toolwindow used to buy
        # explicitly; a frameless window has no taskbar presence on its own),
        # no native close/drag/resize -- close and drag are hand-built below,
        # and the window is a fixed size instead of rebuilding resize too.
        self.root.overrideredirect(True)
        self.root.wm_attributes("-toolwindow", True)  # belt and braces
        # The header's own close button hides rather than closes -- the tray
        # icon is still the real "is she running" switch (see app.py), this
        # is just a window.
        self.root.protocol("WM_DELETE_WINDOW", self._hide)
        self._set_icon()

        mono_family = "Consolas"
        if mono_family not in tkfont.families():
            mono_family = "Courier New"
        mono = tkfont.Font(family=mono_family, size=10)
        name_family = _load_name_font() or mono_family

        header = tk.Frame(self.root, bg=PANEL_BG, height=40)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)
        name_label = tk.Label(
            header, text="Lia", bg=PANEL_BG, fg=ROSE,
            font=(name_family, 20 if name_family == NAME_FONT_FAMILY else 13, "bold"),
        )
        name_label.pack(side="left", padx=(14, 0))
        close_btn = tk.Label(
            header, text="✕", bg=PANEL_BG, fg=MUTED,
            font=(mono_family, 12), cursor="hand2",
        )
        close_btn.pack(side="right", padx=(0, 12))
        close_btn.bind("<Button-1>", lambda _e: self._hide())
        close_btn.bind("<Enter>", lambda _e: close_btn.configure(fg=ROSE))
        close_btn.bind("<Leave>", lambda _e: close_btn.configure(fg=MUTED))
        # Frameless means no native drag either -- the header itself (and its
        # own name label, the only other thing on it) becomes the drag handle.
        for widget in (header, name_label):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)

        # Packed (and height-locked, like header above) before body: a Text
        # widget's own natural size otherwise wins the packer's space fight
        # against a plain fill="x" frame, however that frame's own side is
        # set, and starves input_row down to nothing -- reproduced and
        # confirmed as the actual cause of the entry/mic box disappearing.
        input_row = tk.Frame(self.root, bg=PANEL_BG, height=48)
        input_row.pack(side="bottom", fill="x", padx=10, pady=(4, 10))
        input_row.pack_propagate(False)

        self._entry = tk.Entry(
            input_row, bg=WHITE, fg=INK, insertbackground=ROSE,
            font=mono, relief="flat", highlightthickness=1,
            highlightbackground=ROSE_DIM, highlightcolor=ROSE,
        )
        self._entry.pack(side="left", fill="both", expand=True, ipady=6, ipadx=4)
        self._entry.bind("<Return>", self._submit)
        self._entry.focus_set()

        self._mic_button = tk.Button(
            input_row, text="●", bg=PANEL_BG, fg=ROSE,
            activebackground=ROSE_DIM, font=(mono_family, 14),
            relief="flat", cursor="hand2", command=self._toggle_mic,
        )
        self._mic_button.pack(side="left", padx=(6, 0))
        self._recording = False

        body = tk.Frame(self.root, bg=PANEL_BG,
                        highlightthickness=1, highlightbackground=ROSE_DIM)
        body.pack(side="top", fill="both", expand=True, padx=10, pady=(4, 4))

        self._output = tk.Text(
            body, bg=WHITE, fg=INK, insertbackground=ROSE,
            font=mono, wrap="word", relief="flat", state="disabled",
            highlightthickness=1, highlightbackground=ROSE_DIM,
            highlightcolor=ROSE, padx=8, pady=8,
        )
        # "LIA" in her replies gets its own color and font, applied by name in
        # _append -- everything else in the reply stays the default ink and
        # monospace. Jim Nightshade (a handwriting-style face) reads smaller
        # than the monospace body text at the same point size, so it is sized
        # up to match visually rather than by the numbers.
        name_size = 16 if name_family == NAME_FONT_FAMILY else 10
        self._output.tag_configure("lia_name", foreground=LIME,
                                   font=(name_family, name_size, "bold"))
        scrollbar = tk.Scrollbar(body, command=self._output.yview,
                                 troughcolor=PANEL_BG, bg=ROSE_DIM)
        self._output.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._output.pack(side="left", fill="both", expand=True)

    # -- Keyboard-compatible interface, read by main.read_input() ----------

    def pending(self) -> bool:
        return not self._input_queue.empty()

    def take(self) -> str | None:
        try:
            return self._input_queue.get_nowait()
        except queue.Empty:
            return None

    # -- file-like interface, used as TeeLog's "also" stream ----------------

    def write(self, text: str):
        """Called from the conversation thread with every print() in the app
        -- her replies, but also startup diagnostics, [bracketed] status
        lines, and the bare "You: " prompt, none of which belong in a chat
        window. A reply streams in as many fragments with no newline between
        them ("LIA: ", then piece, piece, piece...), so filtering has to work
        line-by-line, not fragment-by-fragment: text is buffered here until a
        newline completes a line, that line is checked, and only lines worth
        showing are queued for the widget. Tkinter widgets may only be
        touched from the thread that created them, so this never touches
        _output directly -- _poll_output(), on the GUI thread via
        root.after(), is what actually does that.
        """
        if not text:
            return
        # Console-style progress spinners ("...transcribing", "[listening...]")
        # overwrite themselves with \r rather than ending in \n -- meant for a
        # terminal, meaningless in a text widget, where each one would just
        # pile up as its own line instead of vanishing. A \r means the whole
        # buffered line is about to be replaced, so it is dropped, not shown.
        if "\r" in text:
            text = text.rsplit("\r", 1)[1]
            self._line_buf = ""
            if not text:
                return
        self._line_buf += text
        while "\n" in self._line_buf:
            line, self._line_buf = self._line_buf.split("\n", 1)
            if self._worth_showing(line):
                self._output_queue.put(line + "\n")
        # Whatever remains (the in-progress line, e.g. "LIA: " or a reply
        # fragment with more still to come) is queued speculatively once it
        # looks like a real line rather than a status prefix -- see
        # _worth_showing's note on why "LIA: " alone must pass this check.
        if self._line_buf and self._worth_showing(self._line_buf):
            self._output_queue.put(self._line_buf)
            self._line_buf = ""

    @staticmethod
    def _worth_showing(line: str) -> bool:
        """Is this a line of actual conversation, not app noise?

        Everything printed for a human reading a console -- the startup
        banner, "[avatar: ...]" and other bracketed diagnostics, the bare
        "You: " prompt -- is filtered out; only her "LIA: " replies (and
        whatever the caller appends after them from _submit/_record) survive.
        A blank line is kept: it is the spacing print() calls put between
        turns, and dropping it would run every reply into the last.
        """
        stripped = line.strip()
        if not stripped:
            return True
        if stripped.startswith("===") or stripped.startswith("["):
            return False
        if stripped.startswith("You:") or stripped.startswith("You ("):
            return False
        # The one-line startup banner (main.py's "LIA is here...") -- notable
        # for "LIA " with a space, never "LIA:" with a colon, which is how an
        # actual reply always starts.
        if stripped.startswith("LIA ") and not stripped.startswith("LIA:"):
            return False
        return True

    def flush(self):
        pass

    def isatty(self):
        return False

    # -- internals -----------------------------------------------------------

    def _poll_output(self):
        if self.quit_requested.is_set():
            self.root.quit()
            return
        if self.show_requested.is_set():
            self.show_requested.clear()
            self._show_now()
        try:
            while True:
                text = self._output_queue.get_nowait()
                self._append(text)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_output)

    def _append(self, text: str):
        """Insert text, coloring a leading "LIA" (her reply prefix) with the
        lia_name tag; everything else in the same insert keeps the default
        color. Only checked at the very start of what's being inserted -- a
        reply streams in as "LIA: " once, then bare text fragments after, so
        this never re-matches mid-reply."""
        self._output.configure(state="normal")
        if text.startswith("LIA"):
            self._output.insert("end", "LIA", "lia_name")
            self._output.insert("end", text[3:])
        else:
            self._output.insert("end", text)
        self._output.see("end")
        self._output.configure(state="disabled")

    def _submit(self, _event=None):
        text = self._entry.get().strip()
        if not text:
            return
        self._entry.delete(0, "end")
        self._append(f"\n> {text}\n")
        self._input_queue.put(text)

    def _toggle_mic(self):
        if self._recording:
            self._recording = False   # picked up by listen_open's abort=
            return
        self._recording = True
        self._mic_button.configure(fg=INK, text="■")  # stop-square, recording
        threading.Thread(target=self._record, daemon=True).start()

    def _record(self):
        # A fresh Listener per press rather than one kept on self: cheap
        # (it only loads the VAD lazily on first use, same object voice.py
        # already caches for the console/open-mic path), and it means a mic
        # failure on one press can't leave a half-broken Listener for the next.
        import voice

        listener = voice.Listener()
        try:
            text = listener.listen_open(abort=lambda: not self._recording)
        except Exception:
            text = None
        self._recording = False
        self.root.after(0, lambda: self._mic_button.configure(fg=ROSE, text="●"))
        if text:
            # write(), not _append() directly -- this runs on the recording
            # thread, and _output is a Tkinter widget only _poll_output (GUI
            # thread) may touch. write() just queues; _poll_output drains it.
            self.write(f"\n> {text}\n")
            self._input_queue.put(text)

    def _set_icon(self):
        """Her icon (built by make_icon.py from whatever you dropped into
        assets/) on this window's title bar and taskbar entry, in place of
        Tk's default feather. Best effort: an unbuilt icon just leaves Tk's
        own default in place, same as the avatar window's fallback."""
        try:
            from make_icon import ICO_PATH
            if ICO_PATH.is_file():
                self.root.iconbitmap(str(ICO_PATH))
        except Exception:
            pass

    def _drag_start(self, event):
        self._drag_origin = (event.x_root, event.y_root)

    def _drag_move(self, event):
        if self._drag_origin is None:
            return
        ox, oy = self._drag_origin
        dx, dy = event.x_root - ox, event.y_root - oy
        self.root.geometry(f"+{self.root.winfo_x() + dx}+{self.root.winfo_y() + dy}")
        self._drag_origin = (event.x_root, event.y_root)

    def _hide(self):
        self.root.withdraw()

    def _show_now(self):
        """Actually raise the window. GUI-thread only -- see show()."""
        self.root.deiconify()
        self.root.lift()
        self._entry.focus_force()

    def show(self):
        """Thread-safe: callable from any thread (the avatar's click comes in
        on pywebview's own thread), picked up by _poll_output on the next
        tick."""
        self.show_requested.set()
