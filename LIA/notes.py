"""Lia's memory: your own text files, read-only.

She keeps no database of her own. Everything she knows about you lives in
plain .txt files you write yourself -- in Notepad or anything else -- and
this module is the one place that reads them. Her side of the deal is
strictly read-only: she can never add, change or delete a note. If something
should be remembered, you write it in a .txt file in NOTES_DIR (config.py),
and it simply becomes part of what she knows. Nothing she "learns" can exist
anywhere you haven't written it down yourself, which is the whole reason her
invented-facts problem is structurally impossible rather than merely
switched off.

Every non-blank line of every .txt file in the folder is one note. No
format to match, no fields to parse -- you write a line, she can read it.

Failures are surfaced, never swallowed silently: a folder that doesn't exist
and a file that won't read are each printed in [brackets] -- once per state
change, not once per turn, so a problem you haven't fixed nags you without
spamming every reply. An empty or missing folder just means she has no notes:
she starts knowing nothing about you and says so when asked, rather than
guessing.
"""

import re
import threading
from pathlib import Path

from config import NOTES_DIR, NOTES_PATTERN, NOTES_MAX_NOTES, NOTES_MAX_CHARS

_WS = re.compile(r"\s+")

# The two states reported to the user: which folder is missing, and which
# files won't read. Kept between calls so each is printed once when it
# appears and once when it goes away -- not on every turn of the conversation.
_reported: dict = {"missing": False, "broken": frozenset()}

_lock = threading.Lock()
_cache: dict = {"stamps": None, "notes": []}


def _file_texts(path: Path) -> list[str]:
    """Every non-blank line of a .txt file, whitespace collapsed."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = []
    for line in raw.splitlines():
        line = _WS.sub(" ", line).strip()
        if line:
            lines.append(line)
    return lines


def _matching_paths() -> list[Path]:
    folder = Path(NOTES_DIR)
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob(NOTES_PATTERN) if p.suffix.lower() == ".txt")


def _scan(paths: list[Path]) -> tuple[list[str], list[str]]:
    """Read every matching file fresh: (notes, broken-file reports).

    One unreadable file leaves its report behind but doesn't cost the notes
    that did read -- you may simply be mid-save, and dropping everything
    because one file was half-written would make her memory flicker.
    """
    notes: list[str] = []
    broken: list[str] = []
    for path in paths:
        try:
            notes.extend(_file_texts(path))
        except OSError as exc:
            broken.append(f"{path.name} -- {exc}")

    # The cap keeps one runaway folder from pushing a thousand notes into
    # every prompt. Newest-last is arbitrary but stable.
    if len(notes) > NOTES_MAX_NOTES:
        notes = notes[-NOTES_MAX_NOTES:]
    return notes, broken


def _fingerprints(paths: list[Path]) -> dict:
    stamps = {}
    for path in paths:
        try:
            stamps[str(path)] = path.stat().st_mtime_ns
        except OSError:
            pass
    return stamps


def all_notes() -> list[str]:
    """Her memory, as plain text. Rescans only when a file's mtime changed.

    Returns [] when the folder is missing or has no notes yet -- a normal
    state, not an error. Unreadable files are reported in brackets the first
    time they fail and once more when they're fixed; whatever did read is
    still returned, so one bad file never blanks her memory.
    """
    global _reported
    with _lock:
        folder = Path(NOTES_DIR)
        # Path("") is the current directory, and an unconfigured NOTES_DIR is
        # exactly that -- without this guard the default config would quietly
        # read the whole install folder as her memory. "." is never a
        # deliberate notes folder either: the tray app's cwd is arbitrary.
        if str(folder).strip() in ("", "."):
            if not _reported["missing"]:
                print("[notes: NOTES_DIR in config.py is not set -- she has no "
                      "memory until it points at your notes folder]")
                _reported["missing"] = True
            _cache["stamps"], _cache["notes"] = None, []
            return []
        if not folder.is_dir():
            if not _reported["missing"]:
                print(f"[notes: no notes folder at {folder} -- she'll know only "
                      "what's in it once it exists]")
                _reported["missing"] = True
            _cache["stamps"], _cache["notes"] = None, []
            return []

        paths = _matching_paths()
        stamps = _fingerprints(paths)
        if stamps == _cache["stamps"]:
            return list(_cache["notes"])

        notes, broken = _scan(paths)
        _cache["stamps"], _cache["notes"] = stamps, notes

        if _reported["missing"]:
            print(f"[notes: found {folder}]")
            _reported["missing"] = False

        current = frozenset(broken)
        for line in current - _reported["broken"]:
            print(f"[notes: couldn't read {line}]")
        if _reported["broken"] and not current:
            print("[notes: unreadable files fixed -- reading everything again]")
        _reported["broken"] = current

        return list(notes)


def reload() -> list[str]:
    """Throw away the cache and read everything again."""
    with _lock:
        _cache["stamps"] = None
    return all_notes()


def as_context(notes: list[str] | None = None) -> str | None:
    """The notes as one labelled block for the system prompt, or None.

    The label matters as much as the content: these are the person's own
    written words -- the only record of them that exists -- so the prompt
    says exactly that and forbids inventing anything beside them.

    Trimmed to NOTES_MAX_CHARS so a fat notes folder can't crowd the
    conversation out of the context window. Lines are dropped from the
    *front* until it fits, so the most recently read notes survive -- the
    same newest-wins rule _scan's cap uses.
    """
    if notes is None:
        notes = all_notes()
    if not notes:
        return None
    block = "\n".join(f"- {n}" for n in notes)
    if len(block) > NOTES_MAX_CHARS:
        block = block[-NOTES_MAX_CHARS:]
        nl = block.find("\n")
        if nl != -1:
            block = block[nl + 1:]
    return (
        "Things they have written down for you, in their own words -- these are "
        "sticky notes they keep, and they are the only memory of them you have. "
        "Treat every line as true and theirs. Never invent anything about them "
        "that isn't written here:\n" + block
    )
