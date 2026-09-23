"""Lia's memory: your sticky notes, read-only.

She no longer keeps a database of her own. Everything she knows about you
lives in your sticky-notes application, and this module is the one place that
reads it. Her side of the deal is strictly read-only: she can never add,
change or delete a note. If something should be remembered, you write it in
your notes app -- the same way you always have -- and it simply becomes part
of what she knows. Nothing she "learns" can exist anywhere you haven't written
it down yourself, which is the whole reason her invented-facts problem is now
structurally impossible rather than merely switched off.

The app this reads is a C# sticky-notes program of the user's own, which
saves its notes as JSON or XML files in one folder (NOTES_DIR in config.py).
Any layout fits: every matching file is opened, and readable text is pulled
from whatever shape it finds -- a list of note objects, a bare list of
strings, a single note object, a JSON string, or an XML element tree. Note
fields (title, body, text, content, ...) are joined and rendered as plain
text; ids, dates, window positions and the like are skipped.

Failures are surfaced, never swallowed silently: a folder that doesn't exist
and a file that won't parse are each printed in [brackets] -- once per state
change, not once per turn, so a problem you haven't fixed nags you without
spamming every reply. An empty or missing folder just means she has no notes:
she starts knowing nothing about you and says so when asked, rather than
guessing.
"""

import json
import re
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

from config import NOTES_DIR, NOTES_PATTERN, NOTES_MAX_NOTES, NOTES_MAX_CHARS

# Field names that carry the readable text of a note, checked longest-first so
# "notetext" wins over "text" and a "body" beats a "name". Case and separators
# are ignored, so "NoteText", "note_text" and "notetext" all hit.
_TEXT_FIELDS = (
    "notetext", "body", "text", "content", "note", "message", "description",
    "title", "name", "value",
)

# Keys that are metadata about a note rather than its text -- ids, dates,
# flags, window geometry. Skipped rather than rendered, so a note reads as its
# words instead of "3 2024-01-01 true 400 300".
_META_FIELDS = re.compile(
    r"^(id|uid|guid|key|index|idx|number|pos|position|order|seq|color|colour|"
    r"theme|created|createdat|createdon|updated|updatedat|modified|modifiedat|"
    r"edited|editedat|lastmodified|pinned|pinnedat|pinnedon|deleted|deletedat|"
    r"isdeleted|ispinned|ismodified|isvisible|visible|opacity|"
    r"left|top|x|y|width|height|window|screen|z|zindex)$",
    re.IGNORECASE,
)

# Timestamps and bare numbers are metadata about a note, never its content.
_ISO_DATE = re.compile(
    r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?)?$"
)
_NUM = re.compile(r"^-?\d+(\.\d+)?$")

_WS = re.compile(r"\s+")

# The two states reported to the user: which folder is missing, and which
# files won't parse. Kept between calls so each is printed once when it
# appears and once when it goes away -- not on every turn of the conversation.
_reported: dict = {"missing": False, "broken": frozenset()}

_lock = threading.Lock()
_cache: dict = {"stamps": None, "notes": []}


def _scalar_text(value) -> str:
    """The readable text of one leaf value, or "" for metadata."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return "" if _NUM.match(str(value)) else str(value)
    if isinstance(value, str):
        s = value.strip()
        return "" if (_NUM.match(s) or _ISO_DATE.match(s)) else s
    return ""


def _flatten(value, out: list):
    """Collect readable strings from any JSON shape, depth-first."""
    if value is None or isinstance(value, (bool, int, float, str)):
        text = _scalar_text(value)
        if text:
            out.append(text)
        return
    if isinstance(value, dict):
        # Named fields first (title, body, ...), in _TEXT_FIELDS order; then
        # the unnamed non-metadata leaves, in file order; then nested
        # structures, depth-first.
        named, rest = [], []
        seen = set()
        for key, item in value.items():
            k = re.sub(r"[^a-z]", "", str(key).lower())
            if _META_FIELDS.match(k):
                continue
            if k in _TEXT_FIELDS and k not in seen and not isinstance(item, (dict, list)):
                seen.add(k)
                text = _scalar_text(item)
                if text:
                    named.append((_TEXT_FIELDS.index(k), text))
            elif not isinstance(item, (dict, list)):
                text = _scalar_text(item)
                if text:
                    rest.append(text)
        named.sort(key=lambda pair: pair[0])
        for _, text in named:
            out.append(text)
        for text in rest:
            out.append(text)
        for item in value.values():
            if isinstance(item, (dict, list)):
                _flatten(item, out)
        return
    if isinstance(value, list):
        for item in value:
            _flatten(item, out)


def _texts_from_json(raw: str) -> list[str]:
    out: list[str] = []
    _flatten(json.loads(raw), out)
    return out


def _texts_from_xml(raw: str) -> list[str]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise ValueError("not well-formed XML") from None

    out: list[str] = []

    def walk(element):
        # An element carrying text is a field of a note; children are walked
        # too. Metadata names are skipped either way round the file lays it
        # out -- <id>3</id> is not a note.
        tag = re.sub(r"[^a-z]", "", element.tag.lower())
        text = (element.text or "").strip()
        if text and not _META_FIELDS.match(tag):
            value = _scalar_text(text)
            if value:
                out.append(value)
        for child in element:
            walk(child)

    walk(root)
    return out


def _file_texts(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".xml":
        return _texts_from_xml(raw)
    return _texts_from_json(raw)


def _matching_paths() -> list[Path]:
    folder = Path(NOTES_DIR)
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob(NOTES_PATTERN)
                  if p.suffix.lower() in (".json", ".xml"))


def _scan(paths: list[Path]) -> tuple[list[str], list[str]]:
    """Read every matching file fresh: (notes, broken-file reports).

    One unparsable file leaves its report behind but doesn't cost the notes
    that did read -- your app may simply be mid-save, and dropping everything
    because one file was half-written would make her memory flicker.
    """
    notes: list[str] = []
    broken: list[str] = []
    for path in paths:
        try:
            for text in _file_texts(path):
                text = _WS.sub(" ", text).strip()
                if len(text) >= 2:
                    notes.append(text)
        except (ValueError, OSError) as exc:
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
    time they fail and once more when they're fixed; whatever did parse is
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
