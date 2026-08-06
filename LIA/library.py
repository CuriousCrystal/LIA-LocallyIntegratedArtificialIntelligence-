"""
Lia's library -- documents you want her to have read.

Drop files into LIA/library/ and she indexes them: the text is split into
passages, each passage is embedded, and relevant ones are handed to her when
they bear on what you're asking about.

Supported: .pdf, .epub, .txt, .md, .markdown

Deliberately separate from her memories. What you *said* to her and what she
*read* are different kinds of knowing, and blurring them is how an assistant
starts claiming a document's opinions as your own.

A note on whole books: she retrieves passages, not the book. A novel indexes
into hundreds of chunks (a ~300-page book runs well over an hour of embedding
calls at roughly a second each), and afterward she can discuss specific
scenes or characters you ask about -- she cannot recite the book start to
finish. That would mean reading the entire text through her voice, which is a
different feature from anything built here.
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
    EMBED_SECONDS_PER_PASSAGE,
)

SUPPORTED = {".pdf", ".epub", ".docx", ".txt", ".md", ".markdown"}


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


def _read_epub(path: Path) -> list[tuple[int, str]]:
    """(chapter_number, text) per document section -- reuses the PDF (page_number,
    text) convention so chunking/citation code doesn't need to know the
    difference. Most chapters announce their own name in the first line
    ("CHAPTER EIGHT"), so the imprecision of calling it a "page" in citations
    barely shows."""
    import ebooklib
    from bs4 import BeautifulSoup
    from ebooklib import epub

    book = epub.read_epub(str(path))
    chapters = []
    number = 0
    for item in book.get_items():
        if item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        number += 1
        text = BeautifulSoup(item.get_content(), "html.parser").get_text()
        if text.strip():
            chapters.append((number, text))
    return chapters


def _read_docx(path: Path) -> list[tuple[int, str]]:
    """A .docx has no fixed pages -- where a page breaks depends on the printer,
    the font, the margins. So there's no honest page number to cite, and it's
    returned as one block (page 0) the way a plain text file is. Headings are
    kept as their own paragraphs so chunking still splits on real boundaries.

    Only .docx, not the older .doc: that's a completely different, binary format
    that python-docx cannot read at all.
    """
    import docx

    document = docx.Document(str(path))
    parts = [p.text for p in document.paragraphs if p.text.strip()]

    # Tables hold real content in a lot of documents, and dropping them silently
    # is how a document reads as half-empty for no visible reason.
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))

    return [(0, "\n\n".join(parts))]


def _read_text(path: Path) -> list[tuple[int, str]]:
    return [(0, path.read_text(encoding="utf-8", errors="replace"))]


def extract(path: Path) -> list[tuple[int, str]]:
    """Text of a document, as (page_or_chapter, text).

    Read straight from the file every time. There was a conversion cache here
    briefly -- it kept a plain-text copy of everything so re-reading skipped
    the parsing libraries -- and it was removed by request: converting files is
    something to do by hand, not something she should be quietly keeping a
    second copy of your library for.
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix == ".epub":
        return _read_epub(path)
    if suffix == ".docx":
        return _read_docx(path)
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


def count_passages(paths: list[Path]) -> int:
    """How many passages these files will come to, without embedding any of them.

    Extracting and chunking is cheap -- measured at 0.18s for a whole novel,
    against ~23 minutes to actually index it -- so this can be run up front to
    tell someone how long they're in for, instead of leaving them watching a
    silent progress counter.
    """
    total = 0
    for path in paths:
        try:
            for _, text in extract(path):
                total += len(chunk(text))
        except Exception:
            # A file she can't parse shouldn't stop her quoting a number for the
            # rest; ingest_file will surface the real problem soon enough.
            continue
    return total


def estimate_seconds(paths: list[Path]) -> float:
    """Roughly how long indexing these will take, in seconds."""
    return count_passages(paths) * EMBED_SECONDS_PER_PASSAGE


def describe_wait(seconds: float) -> str:
    """A human phrase for a duration -- "about twenty minutes", not "1380s"."""
    if seconds < 45:
        return "a moment"
    minutes = round(seconds / 60)
    if minutes <= 1:
        return "about a minute"
    if minutes < 10:
        return f"about {minutes} minutes"
    # Past ten minutes the exact figure is false precision -- the rate varies
    # with what else is running -- so round to something a person would say.
    return f"around {int(round(minutes / 5.0) * 5)} minutes"


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

def search(query: str, top_k: int = LIBRARY_TOP_K, query_vec=None) -> list[tuple[str, int | None, str]]:
    """Most relevant passages as (title, page, text).

    `query_vec` avoids re-embedding text that memory retrieval already embedded
    this turn -- the same sentence was otherwise sent to the embedding model
    twice per turn.
    """
    rows = db.all_document_chunks()
    if not rows:
        return []

    query_vec = np.array(query_vec) if query_vec is not None else np.array(llm.embed(query))
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
