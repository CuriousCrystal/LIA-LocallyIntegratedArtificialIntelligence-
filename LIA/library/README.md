# Lia's library

A folder to hand her a document through.

Working on something and want her to read it? Save it here and say **"Lia, read
my files"** (or type `/library scan`). She reads it then, and not before.

**She does not read this folder on her own**, and she never touches anything
outside it. Nothing is scanned, indexed, or absorbed until you ask. A file
sitting here is available to her, not already in her head.

**Supported:** `.pdf`, `.epub`, `.txt`, `.md`

Subfolders are fine — she looks all the way down, but only when asked.

## How it works

Each file is split into passages of roughly a paragraph or two, and each passage
is embedded. When you ask something, the closest few passages are handed to her
along with the question, and she's told which document they came from.

She reads *passages*, not whole books. Ask about a specific thing and she'll find
it. Ask "summarise this whole PDF" and she'll only see the handful of passages
that best matched those words — a 300-page book does not fit in an 8k context.

## What to expect

- **Indexing is slow.** Every passage costs an embedding call, about half a
  second. A long PDF can take several minutes the first time. It only happens
  once per file unless you edit it.
- **A full novel is a real wait, not a quick one.** A ~300-page book runs to
  several hundred passages — measured at ~590 for a single Harry Potter novel,
  around 20 minutes of embedding calls. It runs in the background, so she stays
  usable meanwhile, but the book itself won't be answerable until it finishes.
- **Scanned PDFs won't work.** If the text isn't selectable in a PDF viewer,
  there's nothing to extract — this reads text, it doesn't do OCR.
- **She'll say where things came from**, and she's told to admit when the
  passages don't answer your question rather than filling the gap.

## Removing something

Delete the file, then run `/library scan`. Her index of it is dropped and
rebuilt from whatever is actually in the folder.

## A note on what this is

Documents are kept separate from her memories on purpose. What you told her and
what she read are different kinds of knowing — if those blur together, she starts
attributing a document's opinions to you.
