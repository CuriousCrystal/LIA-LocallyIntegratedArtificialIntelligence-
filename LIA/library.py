"""
Lia's library -- documents you want her to have read.

Drop files into LIA/library/ and she indexes them: the text is split into
passages, each passage is embedded, and relevant ones are handed to her when
they bear on what you're asking about.

Supported: .pdf, .txt, .md, .markdown

Deliberately separate from her memories. What you *said* to her and what she
*read* are different kinds of knowing, and blurring them is how an assistant
starts claiming a document's opinions as your own.
"""

import json
import re
import unicodedata
from pathlib import Path

import numpy as np

import db
import llm
from config import (
    LIBRARY_DIR,
    LIBRARY_TOP_K,
    CHUNK_CHARS,
    CHUNK_OVERLAP,
    LIBRARY_MIN_SCORE,
)

SUPPORTED = {".pdf", ".txt", ".md", ".markdown"}


# ------------------------------------------------------------- extraction ---

def _strip_running_heads(pages: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Drop the title banner repeated on every page.

    Left in, that boilerplate dominates the embedding of every chunk, and a
    search for anything at all starts matching page headers instead of content.
    """
    if len(pages) < 4:
        return pages

    counts: dict[str, int] = {}
    for _, text in pages:
        # Page numbers differ per page, so compare on the digit-stripped line.
        for line in {re.sub(r"\d+", "", ln).strip() for ln in text.splitlines()[:3]}:
            if len(line) > 8:
                counts[line] = counts.get(line, 0) + 1

    threshold = max(3, int(len(pages) * 0.4))
    boilerplate = {line for line, count in counts.items() if count >= threshold}
    if not boilerplate:
        return pages

    cleaned = []
    for number, text in pages:
        kept = [
            ln for ln in text.splitlines()
            if re.sub(r"\d+", "", ln).strip() not in boilerplate
        ]
        cleaned.append((number, "\n".join(kept)))
    return cleaned


def _read_pdf(path: Path) -> list[tuple[int, str]]:
    """(page_number, text) per page, so she can cite where something came from."""
    from pypdf import PdfReader

    pages = []
    reader = PdfReader(str(path))
    for number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            pages.append((number, text))
    return _strip_running_heads(pages)


def _read_text(path: Path) -> list[tuple[int, str]]:
    return [(0, path.read_text(encoding="utf-8", errors="replace"))]


def extract(path: Path) -> list[tuple[int, str]]:
    if path.suffix.lower() == ".pdf":
        return _read_pdf(path)
    return _read_text(path)


# --------------------------------------------------------------- chunking ---

def _tidy(text: str) -> str:
    # PDFs are full of typographic ligatures -- "ﬁ" and "ﬂ" arrive as single
    # characters that a speech engine reads oddly and a narrow console can't
    # even print. NFKC turns them back into ordinary letters.
    text = unicodedata.normalize("NFKC", text)
    # PDF extraction leaves hyphenated line breaks and ragged whitespace.
    text = re.sub(r"-\n(\w)", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk(text: str) -> list[str]:
    """Split on paragraph boundaries where possible, hard-split when not."""
    text = _tidy(text)
    if not text:
        return []

    chunks, current = [], ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 <= CHUNK_CHARS:
            current = f"{current}\n\n{para}" if current else para
            continue
        if current:
            chunks.append(current)
        while len(para) > CHUNK_CHARS:
            chunks.append(para[:CHUNK_CHARS])
            para = para[CHUNK_CHARS - CHUNK_OVERLAP:]
        current = para
    if current:
        chunks.append(current)

    return [c for c in chunks if len(c.strip()) > 40]


# ---------------------------------------------------------------- indexing ---

def files() -> list[Path]:
    folder = Path(LIBRARY_DIR)
    if not folder.is_dir():
        return []
    return sorted(
        p
        for p in folder.rglob("*")
        if p.suffix.lower() in SUPPORTED
        and p.is_file()
        # The folder's own instructions aren't something you asked her to read.
        and not (p.name.lower() == "readme.md" and p.parent == folder)
    )


def _key(path: Path) -> str:
    """Identify a document by its path *within* the library folder.

    Absolute paths would make the index worthless the moment the folder moves --
    running the packaged .exe re-read a whole PDF from scratch purely because it
    lived under dist\\Lia\\library instead of LIA\\library.
    """
    try:
        return path.resolve().relative_to(Path(LIBRARY_DIR).resolve()).as_posix()
    except ValueError:
        return path.name


def pending() -> list[Path]:
    """Files that are new or have changed since they were indexed."""
    known = db.indexed_documents()
    out = []
    for path in files():
        if known.get(_key(path)) != path.stat().st_mtime:
            out.append(path)
    return out


def ingest_file(path: Path, on_progress=None) -> int:
    """Index one file, replacing any previous version of it. Returns chunk count."""
    key = _key(path)
    db.forget_document(key)

    mtime = path.stat().st_mtime
    rows = []
    for page, text in extract(path):
        for index, piece in enumerate(chunk(text)):
            vector = llm.embed(piece)
            rows.append((key, path.stem, page or None, index, piece, json.dumps(vector), mtime))
            if on_progress is not None:
                on_progress(len(rows))

    if rows:
        db.insert_document_chunks(rows)
    return len(rows)


def sync(on_progress=None) -> tuple[int, int]:
    """Index anything new or changed. Returns (files_done, chunks_added)."""
    todo = pending()
    total = 0
    for path in todo:
        total += ingest_file(path, on_progress=on_progress)
    return len(todo), total


# --------------------------------------------------------------- retrieval ---

def search(query: str, top_k: int = LIBRARY_TOP_K) -> list[tuple[str, int | None, str]]:
    """Most relevant passages as (title, page, text)."""
    rows = db.all_document_chunks()
    if not rows:
        return []

    query_vec = np.array(llm.embed(query))
    query_norm = np.linalg.norm(query_vec) or 1e-8

    scored = []
    for row in rows:
        vec = np.array(json.loads(row["embedding"]))
        denom = (np.linalg.norm(vec) * query_norm) or 1e-8
        score = float(np.dot(query_vec, vec) / denom)
        if score >= LIBRARY_MIN_SCORE:
            scored.append((score, row["title"], row["page"], row["content"]))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [(title, page, text) for _, title, page, text in scored[:top_k]]


def titles() -> list[tuple[str, int]]:
    return db.document_titles()
