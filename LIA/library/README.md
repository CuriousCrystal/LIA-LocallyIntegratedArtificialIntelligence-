# Lia's library

Put things here you want her to have read. She picks them up the next time she
starts, or immediately with `/library scan`.

**Supported:** `.pdf`, `.txt`, `.md`

Subfolders are fine — she looks all the way down.

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
