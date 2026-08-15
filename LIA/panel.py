"""A small typed-input window, styled after Claude Code's terminal -- white
with warm orange accents. Exists so Lia can be talked to and taught things by
typing, with no microphone and no console window, while the tray app runs
alongside it exactly as it always has.

Deliberately not a new input mechanism. This is a drop-in replacement for two
things that already exist:

- Keyboard (main.py): same .pending()/.take() interface, backed by a
  Tkinter Entry instead of stdin. read_input() cannot tell the difference.
- TeeLog's "also" stream (app.py): same .write()/.flush() interface, so
  everything she already prints reaches this window too, unchanged.

Nothing about the conversation pipeline needed to change for this to work.
"""

import queue
import threading
import tkinter as tk
from tkinter import font as tkfont

WHITE = "#ffffff"
PANEL_BG = "#fdfbf9"
ORANGE = "#d97757"       # Claude Code's own warm orange
ORANGE_DIM = "#e8a87c"   # the tone Lia's tray dot already uses -- see app.py's make_icon
INK = "#1c1a20"          # same dark ink the tray dot uses when she's speaking
MUTED = "#8a8078"


class Panel:
    """The training window. Construct on the main thread, before any
    background thread starts -- Tkinter's mainloop has to own the thread
    that created the root window."""

    def __init__(self):
        self._input_queue: queue.Queue = queue.Queue()
        self._output_queue: queue.Queue = queue.Queue()
        # Set from the tray icon's own thread (its Quit menu item), read back
        # here on the GUI thread -- Event is the thread-safe part, root.quit()
        # itself only ever runs from _poll_output, i.e. on the thread that
        # owns it.
        self.quit_requested = threading.Event()
        self.root = tk.Tk()
        self._build()
        self.root.after(50, self._poll_output)

    def _build(self):
        self.root.title("Lia")
        self.root.geometry("580x440")
        self.root.minsize(420, 300)
        self.root.configure(bg=PANEL_BG)
        # The X button hides rather than closes -- the tray icon is still the
        # real "is she running" switch (see app.py), this is just a window.
        self.root.protocol("WM_DELETE_WINDOW", self._hide)

        mono_family = "Consolas"
        if mono_family not in tkfont.families():
            mono_family = "Courier New"
        mono = tkfont.Font(family=mono_family, size=10)

        header = tk.Frame(self.root, bg=ORANGE, height=36)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)
        tk.Label(
            header, text="  LIA", bg=ORANGE, fg=WHITE,
            font=(mono_family, 11, "bold"), anchor="w",
        ).pack(side="left", fill="y")
        tk.Label(
            header, text="typed, while listening is off  ", bg=ORANGE, fg=WHITE,
            font=(mono_family, 9), anchor="e",
        ).pack(side="right", fill="y")

        body = tk.Frame(self.root, bg=PANEL_BG)
        body.pack(side="top", fill="both", expand=True, padx=10, pady=(8, 4))

        self._output = tk.Text(
            body, bg=WHITE, fg=INK, insertbackground=ORANGE,
            font=mono, wrap="word", relief="flat", state="disabled",
            highlightthickness=1, highlightbackground=ORANGE_DIM,
            highlightcolor=ORANGE, padx=8, pady=8,
        )
        self._output.pack(side="top", fill="both", expand=True)

        input_row = tk.Frame(self.root, bg=PANEL_BG)
        input_row.pack(side="bottom", fill="x", padx=10, pady=(4, 10))

        tk.Label(
            input_row, text=">", bg=PANEL_BG, fg=ORANGE,
            font=(mono_family, 12, "bold"),
        ).pack(side="left", padx=(0, 6))

        self._entry = tk.Entry(
            input_row, bg=WHITE, fg=INK, insertbackground=ORANGE,
            font=mono, relief="flat", highlightthickness=1,
            highlightbackground=ORANGE_DIM, highlightcolor=ORANGE,
        )
        self._entry.pack(side="left", fill="x", expand=True, ipady=6, ipadx=4)
        self._entry.bind("<Return>", self._submit)
        self._entry.focus_set()

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
        # Called from the conversation thread. Tkinter widgets may only be
        # touched from the thread that created them, so this only ever
        # queues the text -- _poll_output(), running on the GUI thread via
        # root.after(), is what actually touches the widget.
        if text:
            self._output_queue.put(text)

    def flush(self):
        pass

    def isatty(self):
        return False

    # -- internals -----------------------------------------------------------

    def _poll_output(self):
        if self.quit_requested.is_set():
            self.root.quit()
            return
        try:
            while True:
                text = self._output_queue.get_nowait()
                self._append(text)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_output)

    def _append(self, text: str):
        self._output.configure(state="normal")
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

    def _hide(self):
        self.root.withdraw()

    def show(self):
        self.root.deiconify()
        self.root.lift()

    def mainloop(self):
        self.root.mainloop()
