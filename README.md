# LIA — Locally Integrated Artificial Intelligence

A companion who lives on your machine. She talks, she listens, she says what she
thinks — and the **only** memory she has of you is the `.txt` files you write
yourself. There is no database of her own: nothing she "learns" can exist
anywhere you haven't written it down.

**Chat, speech-to-text and speech are all local now.** Chat runs on a small
model through [Ollama](https://ollama.com); speech-to-text is local
faster-whisper; speaking is local Piper. Nothing about a conversation leaves
your machine — there is no API key, no hosted provider, no network call at all
for anything she says or hears.

A 3D avatar sits fixed in the top-left corner of your screen (not
always-on-top, so other windows can cover her); click her to open a small chat
window — type, or press its mic button for one recorded question at a time.

**Windows only, and not a short-term gap.** The avatar's transparency,
click-through and taskbar behavior are built directly on Win32 (`ctypes` calls
into `user32`/`gdi32`/`dwmapi`), the chat panel's custom font and icon loading
do the same, and the shortcut/autostart tooling writes real Windows `.lnk`
files. Porting to Linux or macOS means reworking the avatar window for each
platform's own windowing APIs and replacing the startup/shortcut tooling
entirely (`.desktop` files on Linux, an `.app` bundle or LaunchAgent on
macOS) — a real project, not a compatibility flag. The model, notes, and chat
logic underneath are already plain Python and would need little to no change;
it's specifically the desktop-integration layer that's Windows-specific.

This page is the short version. [`LIA/README.md`](LIA/README.md) is the full
reference.

## Setup

1. Install [Ollama](https://ollama.com) and leave it running, then pull a
   small model (CPU-only inference is slow above 3-4B parameters):
   ```
   ollama pull phi3:mini
   ```
2. Install the Python deps:
   ```
   pip install -r LIA/requirements.txt
   ```
   Speech-to-text (`faster-whisper`) downloads its own model automatically on
   first use — no separate pull step.
3. Drop `.txt` files into [`LIA/notes/`](LIA/notes/) for her to remember —
   every non-blank line becomes one thing she knows about you. Empty is fine;
   she just knows nothing about you yet, and says so.

Python 3.12 is the tested version. No microphone or network connection is
required to talk to her (type in the chat panel); a microphone is needed for
the mic button or always-on listening.

## Running her

```powershell
pythonw LIA\app.py     # tray app -- no window, avatar + chat panel, the normal way
python  LIA\main.py    # terminal -- same companion, but typing works without a panel
```

To have her start when you log in:

```powershell
powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 install
```

`remove` and `status` do what you'd expect. With no console, everything she
prints goes to `lia.log` in the project root.

There's also a packaged build (`LIA\build_exe.ps1` → `dist\Lia\Lia.exe`) for
machines with no Python installed. Ollama still has to be installed, running,
and have the model pulled on that machine — packaging her doesn't bundle a
model runtime. A GitHub Actions workflow
([`.github/workflows/release.yml`](.github/workflows/release.yml)) builds and
publishes this automatically on a `v*` tag push.

## Talking to her

**Click her avatar** to open the chat panel — type and press Enter, or press
the mic button (●) to record one question (it stops automatically when you
stop talking, or click it again to cancel).

Background always-on listening is off by default (`LISTEN_ENABLED` in
`config.py`). Turn it on from her tray menu or config if you'd rather talk to
her without opening the panel each time. With it on, **say her name to be
heard**: *"Lia, are you there?"* — say her name and your question together in
one breath, since a name said alone with nothing else just gets acknowledged.
The wake word is matched on the transcript rather than a dedicated model, so
it needs no training and tolerates a few common mishearings ("Leah", "Lea",
"Liya", "Leia").

**Spoken or typed instructions** do something rather than becoming
conversation:

```
"Lia, stop listening"  / "go to sleep"    → mic off
"Lia, be quiet"        / "stop talking"   → voice off
"Lia, what do you remember"               → reads your notes back
"Lia, reload your notes"                  → re-reads the notes folder
```

When your words don't match the phrase list, `intent.py` asks the local model
what you meant from the actions she can actually take — which are switching
her mic/voice/wake-word and reading your notes. Everything else is
conversation, which is the point of her.

## What she can do

- **Talk, and mean it.** When you ask what she thinks, she takes a position
  and gives her reasons — no fence-sitting, no briefing-document summaries.
  See `SYSTEM_PROMPT` in `config.py` (`WHAT YOU THINK`).
- **Remember what you write down.** Her memory is plain `.txt` files in
  `LIA/notes/`, read-only. She can never add, edit or delete a note; if you
  want her to know something, you write it yourself and it simply becomes
  part of what she knows. Because nothing is stored on her side, the
  invented-facts problem is structurally impossible rather than merely
  switched off.
- **Hear you and speak**, streamed sentence-by-sentence in a local Piper
  voice — all on-device, no API involved.

That's the whole list. No music, no volume control, no alarms, no document
library, no web search, no voice ID — those were removed by design, not lost.

## What she remembers

Exactly what your `.txt` notes contain, nothing more and nothing less. Within
a conversation she keeps the last `CLOUD_HISTORY_TURNS` (4) turns of context;
when a conversation sits idle past `IDLE_MINUTES` it rolls over. Nothing from
any session is ever written to disk — there is no database to write to.

The caps that keep a fat notes folder from crowding out the conversation:
`NOTES_MAX_NOTES` (200) and `NOTES_MAX_CHARS` (6000), both in `config.py`.

## Where things run

| local (always) |
|---|
| the model that answers you (Ollama, `LOCAL_CHAT_MODEL`) |
| speech-to-text (faster-whisper, `LOCAL_WHISPER_MODEL`) |
| speech (Piper), wake word, voice-activity detection |
| your notes (read from disk, never written) |

Nothing leaves the machine. There's no API key, no `store: false` setting to
rely on, and no provider terms to trust — the model and your words never go
anywhere but your own CPU.

### Speed

CPU-only inference is the real tradeoff for going fully local: a 3-4B model
(`phi3:mini`, the default) answers with its first word in a couple of seconds
but can take several more to finish a longer reply, and it follows the
brevity/personality instructions in `SYSTEM_PROMPT` less reliably than a large
hosted model would. `CLOUD_MAX_TOKENS` caps how long a runaway reply can run.
Every failure to reach the model — Ollama not running, the model not pulled,
a dropped stream — is recorded to `cloud_fallback_log.jsonl`;
`python LIA\fallback_report.py` reads it back over a window.

## The files

| file | what it does |
|---|---|
| `config.py` | every prompt and tunable. **Edit this first** if her tone feels off. `NOTES_DIR` points at your notes folder. |
| `notes.py` | her memory — reads `.txt` files, one note per non-blank line, read-only |
| `main.py` | the conversation loop |
| `app.py` | tray app wrapper for running her in the background |
| `llm.py` | the one path to the local model — chat, streaming chat (Ollama), transcription (faster-whisper) |
| `voice.py` | speaking (Piper only) and listening (local STT + local VAD) |
| `intent.py` | works out what you meant when no phrase matches |
| `vrm.py` | the 3D avatar — drop any `.vrm` into `LIA/vrm/` (see `vrm/README.md`) |
| `panel.py` | the chat window — type, or use its mic button; opens when you click her avatar |
| `make_icon.py` | builds her tray/window icon from an image dropped into `LIA/assets/` |
| `fallback_report.py` | reads back `cloud_fallback_log.jsonl` |

## Tuning

| setting | when to change it |
|---|---|
| `NOTES_DIR` | **where her memory lives** — defaults to `LIA/notes/` |
| `NOTES_MAX_NOTES` / `NOTES_MAX_CHARS` | caps so a big notes folder can't crowd out the conversation |
| `OLLAMA_BASE_URL` | where Ollama is reached; `http://localhost:11434` by default |
| `LOCAL_CHAT_MODEL` | `phi3:mini` by default; must be `ollama pull`ed first. `llama3.2:3b` is a similar-sized alternative. |
| `LOCAL_WHISPER_MODEL` | faster-whisper size: `base` by default; `small`/`medium` are more accurate and slower on CPU |
| `LISTEN_ENABLED` | background always-on listening; off by default now that the chat panel is the primary way in |
| `VOICE_NAME` | which Piper voice in `LIA/voices/` (`en_US-amy-medium` by default; `auto` takes the first found) |
| `CLOUD_HISTORY_TURNS` | how much context a turn carries — prompt size is what a CPU-only model pays for most directly |
| `CLOUD_MAX_TOKENS` | ceiling on one reply's length |
| `VAD_SILENCE_SECONDS` | raise if she cuts you off mid-thought |
| `VAD_THRESHOLD` | raise if background noise triggers her |
| `MIC_SETTLE_SECONDS` | raise if she answers her own voice (headphones fix this outright) |
| `IDLE_MINUTES` | how long a silence rolls the conversation over |
| `SYSTEM_PROMPT` | her personality — including `WHAT YOU THINK`, the opinions section |

## Not built yet

- Writing notes back to her notes folder (she is deliberately read-only; say
  the word and it can be built)
- A name in her vocabulary hint, pulled from your notes, so transcription
  stops respelling it
- Anything the removed features did — by design, not omission
