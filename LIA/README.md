# LIA — Locally Integrated Artificial Intelligence

A companion who lives on your machine. Chat runs on a small local model
through [Ollama](https://ollama.com); speech-to-text is local faster-whisper;
speech is local Piper. Nothing about a conversation leaves the machine — no
API key, no hosted provider, no network call.

Her memory is the `.txt` files you write yourself in `LIA/notes/`, read-only.
There's no database of her own: nothing she "learns" can exist anywhere you
haven't written it down.

A 3D avatar sits fixed in your screen's top-left corner (not always-on-top —
other windows can cover her). Click her to open a small chat window: type, or
press its mic button for one recorded question at a time.

## Setup

1. Install [Ollama](https://ollama.com), leave it running, and pull a model
   sized for CPU-only inference (3-4B parameters; bigger is noticeably
   slower without a discrete GPU):
   ```
   ollama pull phi3:mini
   ```
2. Install the Python deps:
   ```
   pip install -r LIA/requirements.txt
   ```
   faster-whisper (speech-to-text) downloads its own model automatically on
   first use.
3. Drop `.txt` files into `LIA/notes/` for her to remember. Empty is fine —
   she just knows nothing about you yet.

## Running her

**As a background app** — the tray icon, the avatar, and the chat panel
(hidden until you click her):

```powershell
pythonw LIA\app.py
```

**In a terminal** — same companion, with a console and live logging:

```powershell
python LIA\main.py --debug
```

**As a packaged .exe** — no Python needed on the machine (Ollama still is):

```powershell
powershell -ExecutionPolicy Bypass -File LIA\build_exe.ps1
```

Builds `dist\Lia\Lia.exe`. A GitHub Actions workflow
(`.github/workflows/release.yml`) does this automatically and publishes it as
a release on a `v*` tag push.

To have her start when you log in:

```powershell
powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 install       # tray app
powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 install -Exe  # packaged exe
```

`remove` and `status` do what you'd expect. With no console, everything she
prints goes to `lia.log` beside the exe (or in the project root from source).

## Talking to her

**Click her avatar** to open the chat panel — type and press Enter, or press
the mic button (●) to record one question; it stops on its own when you stop
talking, or click it again to cancel.

Background always-on listening is off by default (`LISTEN_ENABLED` in
`config.py`) — the chat panel is the primary way in now. Turn it on from her
tray menu or `config.py` if you'd rather talk without opening the panel each
time. With it on, **say her name and your question together, in one breath**:
*"Lia, are you there?"* Saying just "Lia" with the question in a separate
utterance means the question gets skipped (no wake word) and "Lia" alone
reaches her, which just gets acknowledged.

The wake word is matched on the transcript rather than a dedicated model, so
it needs no training and tolerates a few common mishearings — "Leah", "Lea",
"Liya", "Leia" all count (`WAKE_WORDS` in `config.py`).

**Slash commands** (typed or spoken) do something rather than becoming
conversation:

```
/voice on|off      speak replies out loud
/mic on|off        listen to you at all
/openmic on|off    open mic (just talk) vs push-to-talk
/wake on|off       only answer when you say her name
/notes             what she knows from your notes
/notes reload      re-read the notes folder
/notes where       where her memory lives
/help              this list
bye                end the session
```

Spoken equivalents work too — *"Lia, stop listening"*, *"go to sleep"*, *"be
quiet"*, *"what do you remember"*. When your words don't match a phrase,
`intent.py` asks the local model what you meant from the actions above —
never anything else, and never for ordinary conversation.

## What she can do

- **Talk, and mean it.** When you ask what she thinks, she takes a position
  and gives her reasons — no fence-sitting, no briefing-document summaries.
  See `SYSTEM_PROMPT` in `config.py` (`WHAT YOU THINK`).
- **Remember what you write down.** Her memory is your `.txt` notes,
  read-only. She can never add, edit or delete a note; write something
  yourself and it becomes part of what she knows. Because nothing is stored
  on her side, the invented-facts problem is structurally impossible.
- **React to what a note says**, not just recall it — a note about something
  you're stressed about shifts her tone, not just her answer to a direct
  question about it.
- **Hear you and speak**, streamed sentence-by-sentence in a local Piper
  voice.
- **Show a 3D avatar** with idle motion (breathing, blinking, gaze wander)
  and a state (idle/listening/thinking/speaking) that follows the
  conversation. Drag to move her within a session; drop your own `.vrm`
  model into `LIA/vrm/`.

That's the whole list. No music, no volume control, no alarms, no document
library, no web search, no voice ID — removed by design, not lost, and not
reintroduced without asking.

## What she remembers

Exactly what your `.txt` files in `LIA/notes/` contain — every non-blank line
is one note. Within a conversation she keeps the last `CLOUD_HISTORY_TURNS`
(4) turns of context; a conversation idle past `IDLE_MINUTES` rolls over.
Nothing from any session is written to disk — there is no database.

`NOTES_MAX_NOTES` (200) and `NOTES_MAX_CHARS` (6000) keep a fat notes folder
from crowding out the conversation.

## Speed, and why it's a real tradeoff

Going fully local means CPU-only inference (unless you have a discrete GPU
Ollama can use): a small model's first word arrives in a couple of seconds,
but a full reply can take several more, and it follows the brevity/persona
instructions in `SYSTEM_PROMPT` less reliably than a large hosted model
would. That's the accepted cost of nothing leaving the machine. Swap
`LOCAL_CHAT_MODEL` in `config.py` if you want to try a different balance of
size vs. speed vs. instruction-following (anything `ollama pull`-able).

Every failure to reach the model — Ollama not running, model not pulled, a
dropped stream — is recorded to `cloud_fallback_log.jsonl`;
`python LIA\fallback_report.py` reads it back over a window.

## The files

| file | what it does |
|---|---|
| `config.py` | every prompt and tunable. **Edit this first** if her tone feels off. |
| `notes.py` | her memory — reads `.txt` files from `LIA/notes/`, read-only |
| `main.py` | the conversation loop |
| `app.py` | tray app wrapper; wires the avatar and chat panel together |
| `llm.py` | the one path to the local model — chat/streaming via Ollama, transcription via faster-whisper |
| `voice.py` | speaking (Piper) and listening (local STT + local VAD) |
| `intent.py` | works out what you meant when no phrase matches |
| `vrm.py` | the 3D avatar window — see `vrm/README.md` |
| `panel.py` | the chat window (type, or its mic button); opens on the avatar's click |
| `make_icon.py` | builds her tray/window icon from an image in `LIA/assets/` |
| `fallback_report.py` | reads back `cloud_fallback_log.jsonl` |
| `notes/` | drop your `.txt` files here |
| `voices/` | Piper voice files — see `voices/README.md` |
| `vrm/` | your `.vrm` avatar model — see `vrm/README.md` |
| `assets/` | your tray/window icon source image — see `assets/README.md` |

## Tuning

| setting | when to change it |
|---|---|
| `NOTES_DIR` | where her memory lives — `LIA/notes/` by default |
| `NOTES_MAX_NOTES` / `NOTES_MAX_CHARS` | caps so a big notes folder can't crowd out the conversation |
| `OLLAMA_BASE_URL` | where Ollama is reached — `http://localhost:11434` by default |
| `LOCAL_CHAT_MODEL` | the pulled Ollama model to chat with; `phi3:mini` by default |
| `LOCAL_WHISPER_MODEL` | faster-whisper size (`tiny`/`base`/`small`/`medium`/`large-v3`); `base` by default |
| `LISTEN_ENABLED` | background always-on listening; off by default |
| `VAD_SILENCE_SECONDS` | raise if she cuts you off mid-thought |
| `VAD_THRESHOLD` | raise if background noise triggers her |
| `MIC_SETTLE_SECONDS` | raise if she answers her own voice (headphones fix this outright) |
| `IDLE_MINUTES` | how long a silence rolls the conversation over |
| `CLOUD_HISTORY_TURNS` | how much context a turn carries |
| `CLOUD_MAX_TOKENS` | ceiling on one reply's length |
| `VOICE_NAME` | which Piper voice in `LIA/voices/`; `auto` takes the first found |
| `VRM_ENABLED` / `VRM_DIR` / `VRM_SIZE` / `VRM_FRAMING` | the avatar — see `vrm/README.md` |
| `SYSTEM_PROMPT` | her personality, including `WHAT YOU THINK` (real opinions, not fence-sitting) |

## Not built yet

- Writing notes back to her notes folder (she is deliberately read-only)
- A name in her vocabulary hint, pulled from your notes, so transcription
  stops respelling it
- Anything the removed features (database, music, alarms, library, voice ID,
  weather/web search) did — by design, not omission
