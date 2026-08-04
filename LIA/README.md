# LIA — Locally Integrated Artificial Intelligence

A companion that runs entirely on your machine. No accounts, and nothing leaves
the laptop once the models are pulled — with one deliberate, narrow exception:
if you give her an API key, she can check the weather and look things up
online. See [Weather, lookups and music](#weather-lookups-and-music). Leave
those keys unset and she never touches the internet at all.

## Setup

1. Install [Ollama](https://ollama.com)
2. Pull the models:
   ```
   ollama pull llama3.2:3b
   ollama pull nomic-embed-text
   ```
3. Install the Python deps:
   ```
   pip install -r LIA/requirements.txt
   ```

## Running her

**As a background app** — no window, lives in the system tray, listens on the
open mic:

```powershell
pythonw LIA\app.py
```

**In a terminal** — same companion, but you can type to her as well as talk:

```powershell
python LIA\main.py
```

**As a packaged .exe** — no Python needed on the machine:

```powershell
powershell -ExecutionPolicy Bypass -File LIA\build_exe.ps1
```

Builds `dist\Lia\Lia.exe` (~366 MB). Ollama still has to be installed separately;
the language model is far too large to bundle.

To have her start when you log in:

```powershell
powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 install       # tray app
powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 install -Exe  # packaged exe
powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 install -Console
```

`remove` and `status` do what you'd expect. With no console, everything she
prints goes to `lia.log` beside the exe (or in the project root from source).

She waits for Ollama on startup and launches it if it isn't running — at login
she almost always wins the race, and without that she'd crash every boot.

## Talking to her

**Say her name to start:** *"Lia, are you there?"* After she answers you have
`CONVERSATION_WINDOW_SECONDS` (60 by default) to keep talking normally without
repeating her name. Each reply resets the window; after it lapses she goes back
to ignoring the room until you say "Lia" again.

The wake word is matched on the transcript rather than a dedicated model, so it
needs no training and tolerates Whisper's spellings — "Leah", "Lea", "Liya" all
count. Say `/wake off` to make her answer everything she hears.

In the terminal you can type instead, and these commands work:

```
/voice on|off      speak replies out loud
/mic on|off        listen at all
/openmic on|off    open mic vs push-to-talk
/wake on|off       only answer when you say her name
/voices            list installed voices
/help              command list
bye                end the session
```

**Interrupting her:** just start talking. The mic stays open while she speaks,
and anything it hears is checked against what she's currently saying — her own
voice coming back through the speakers is ignored, yours cuts her off. Clean on
headphones; on speakers it depends on how much of her voice the mic picks up.
Set `BARGE_IN = False` to go back to letting her finish.

**Spoken instructions** do something rather than becoming conversation:

```
"Lia, stop listening"   /  "go to sleep"      → mic off
"Lia, start listening"  /  "wake up"          → mic on
"Lia, be quiet"         /  "stop talking"     → voice off
"Lia, you can talk"                           → voice on
```

Edit `SPOKEN_COMMANDS` in `config.py` to add your own phrasings.

### When your words aren't on the list

That list will always be incomplete — people don't say *"volume up"*, they say
*"could you push that up a bit, it's hard to hear."* So there are two layers,
in this order:

1. **The phrase list** — instant, free, completely predictable. Handles the
   everyday wordings.
2. **`intent.py`** — when nothing matched, the model is shown the actions she
   can actually take and asked which one, if any, you meant. It decides from
   meaning rather than remembered wordings.

The second layer only runs when your words look like they could plausibly be
about an action at all, so ordinary conversation never waits on it — measured
at 0.00s for anything conversational, versus roughly 3s when she does stop to
work out what you meant.

It's a fallback rather than a replacement on purpose: a 3B model is good at
this but not perfectly consistent, so the deterministic matcher stays in front
of it. Measured across repeated runs it got **30 of 32** right, including every
one of the "this is just conversation, don't act on it" cases — the weakest was
an ambiguous *"I'm done with this song, move on"*, which sometimes paused
instead of skipping.

Both failure directions are worth knowing about: she can miss an unusual
request (it falls through to conversation, exactly as it did before this
existed), or occasionally read a passing remark as a request. Say *"that's not
what I meant"* and carry on — nothing here does anything you can't immediately
undo, and when she does act on an interpretation she prints
`[took that as: …]` so it's never a mystery.

## Giving her things to read

Drop `.pdf`, `.epub`, `.docx`, `.txt` or `.md` files into `LIA\library\` (or `dist\Lia\library\`
for the packaged app). She indexes them on startup, or right away with
`/library scan`. `/library` lists what she's read.

She retrieves *passages*, not whole documents, and cites the file and page. Ask
about something specific and she'll find it; ask her to summarise a 300-page book
and she'll only see the few passages that matched. Scanned PDFs won't work —
there's no OCR.

Indexing costs one embedding call per passage, **measured at ~2.3s** on a 4GB
card: roughly 130 pages per ten minutes, so a full novel is about twenty
minutes. It happens once per file, runs in the background, and she stays usable
throughout.

Before she starts she counts the passages — a fraction of a second, no
embedding — and tells you what you're in for: *"On it"* for something short, or
*"On it, that'll take around 25 minutes"* for a book. She says so again when
she's finished.

`.docx` is Word's current format only — not the old binary `.doc`, and not
Kindle's `.mobi`/`.azw`. Converting those to `.epub` or `.docx` first works.

## Weather, lookups and music

The one deliberate exception to running fully offline — narrow on purpose, and
entirely optional. With no keys set, none of this activates and she never
makes a network call beyond talking to Ollama on your own machine.

**Weather** needs no key at all. Say *"what's the weather like"* and she checks
a live source (Open-Meteo) and answers in her own voice, geolocated from your
IP automatically.

**"Look that up"** answers a factual question from the internet instead of
guessing from what a 3B local model already knows. Needs one of:

```powershell
[Environment]::SetEnvironmentVariable('GROQ_API_KEY', 'your-key', 'User')
[Environment]::SetEnvironmentVariable('OPENROUTER_API_KEY', 'your-key', 'User')
```

Set as environment variables, never pasted into a file — `config.py` only ever
reads them via `os.environ.get(...)`. Restart her after setting one so the new
process picks it up.

If both are set, **OpenRouter is tried first**, because with
`OPENROUTER_ONLINE = True` (the default) it appends `:online` to the model
name, which makes OpenRouter run an actual web search before answering — a
real current answer, not a fluent guess. Groq is fast but is just a bigger
version of the same kind of model Lia already runs locally; a plain
chat-completions call to it has no more access to today's news than she does
already. It's the fallback, or the option if that's the only key you have.

Naming a source works too — *"search Reddit for..."* or *"what does Reddit think
about..."* pulls in real, current opinions rather than a guess. One caveat found
by testing it: search-engine operators like `site:reddit.com` make the
underlying search decline entirely (it answers as if it has no web access at
all) — plain natural language is what actually works.

**Music** needs nothing at all — it uses Windows' own System Media Transport
Controls, the same thing behind your keyboard's media keys, so it works with
whatever's actually playing (Spotify, a browser tab, Windows Media Player)
without her needing to know which. It's a remote, not a jukebox — it can't
start a track from nothing, and she'll say so honestly rather than guess:

```
"play music" / "pause music" / "next song" / "previous song"
"what song is this" / "what's playing"
```

**Alarms and timers** are parsed by regex, never by the model — a timer has to
fire at the right second, and precise extraction is exactly what a 3B is worst
at. Say it however it comes out:

```
"remind me in 5 min"          "wake me in half an hour"
"give me a nudge in 20 mins"  "let me know in ten minutes"
"buzz me in an hour"          "set a timer for 5"
"wake me up at 7am"           "wake me at half past 3"
```

Spoken numbers, vague durations ("a couple of minutes") and clock forms
("half past three") all work. **You can also choose the words she wakes you
with** — *"wake me by saying please wake up in 5 minutes"* and she says exactly
that, rather than "your timer is up". *"Remind me to stretch in 20 minutes"*
becomes *"Time to stretch."*

They survive restarts, and she interrupts whatever's happening to say them.
Ordinary conversation containing a time ("we talked for an hour yesterday")
deliberately doesn't schedule anything — that needs an explicit word like
*remind*, *wake* or *timer* as well.

**Volume** talks to Windows' Core Audio API directly (via `pycaw`), not to a
simulated key press — that was tried first and verified to silently do
nothing, since a simulated key needs a focused window to land on:

```
"volume up" / "turn it up" / "volume down" / "turn it down"
"mute" / "unmute"
```

## Recognising your voice

Say **"Lia, it's Wade"** a few times and she builds a voiceprint — a local model
(3D-Speaker's CAM++, via `sherpa-onnx`, no PyTorch) compares later speech against
it. This is a soft comfort signal, not a lock: a clear mismatch means she
won't use your name and won't share what she remembers about you, but she never
simply refuses to talk.

`/whoami` shows enrollment progress and the last confidence score; `/whoami forget`
clears the profile and starts over. **Real-world accuracy is unverified from
development** — it was only tested against synthetic TTS voices, which likely
*understates* how well it discriminates real human voices (see
`speaker_id.py`'s docstring). `SPEAKER_MATCH_THRESHOLD` in `config.py` is a
starting point, not a calibrated answer — expect to retune it once there's real
usage data.

## How she remembers

Three layers, all in `lia_memory.db` (plain SQLite, in the project root — inspect
it any time with `sqlite3 lia_memory.db`):

- **facts** — durable things about you, pulled out at the end of each session and
  injected into every system prompt
- **memories** — every turn, embedded, searched by cosine similarity. Only *your*
  turns are retrieved; hers competing for the same slots made her quote her own
  speculation back as fact.
- **diary** — a short private reflection she writes when a conversation ends

A conversation ends when you say `bye`, or on its own after `IDLE_MINUTES` of
silence — an always-on companion never gets a goodbye, and without the timeout
she'd never learn anything.

## The files

| file | what it does |
|---|---|
| `config.py` | every prompt and tunable. **Edit this first** if her tone feels off. |
| `db.py` | SQLite schema and queries |
| `llm.py` | Ollama wrapper — chat, streaming chat, embeddings |
| `memory.py` | embedding, retrieval, fact extraction and sanitising |
| `diary.py` | end-of-session reflection |
| `voice.py` | text-to-speech, speech recognition, voice activity detection |
| `main.py` | the conversation loop |
| `app.py` | tray app wrapper for running her in the background |
| `library.py` | reads PDFs and notes you drop in `library/` |
| `internet.py` | the one deliberate offline exception — weather, and online lookups |
| `media.py` | Windows media control (SMTC) and volume (Core Audio) |
| `alarms.py` | spoken alarms and timers — regex-parsed, never guessed by the model |
| `speaker_id.py` | voice recognition — is this the enrolled voice or not |
| `voices/` | drop your own voice files here — see `voices/README.md` |
| `library/` | drop PDFs here — see `library/README.md` |
| `models/` | the speaker-recognition model — see `models/README.md` |

## Tuning

| setting | when to change it |
|---|---|
| `NUM_CTX` | 8192 keeps her mostly on the GPU on a 4GB card. Ollama's 32k default spills 63% to CPU. Check with `ollama ps`. |
| `OLLAMA_KEEP_ALIVE` | `"30m"` avoids a 9s cold start; costs ~3.7GB of VRAM held. Lower it on battery. |
| `VAD_SILENCE_SECONDS` | raise if she cuts you off mid-thought |
| `VAD_THRESHOLD` | raise if background noise triggers her |
| `MIC_SETTLE_SECONDS` | raise if she answers her own voice (headphones fix this outright) |
| `WHISPER_MODEL` | `small.en` gets names right that `base.en` garbles |
| `IDLE_MINUTES` | how long a silence ends the conversation |
| `VOICE_ENGINE` | `"piper"` (default) / `"system"` for the built-in Windows voice |
| `RETRIEVAL_MIN_WORDS` | skips memory/library lookup below this many words — raise it if short replies still feel slow |
| `OPENROUTER_ONLINE` | live web search on "look that up", instead of a guess — see `internet.py` |

## Not built yet

- Merging duplicate facts (`sister_name` and `visiting_sister_name` both exist)
- Any way to make her forget something
- Voice cloning from a short recording — see [`voices/README.md`](voices/README.md#cloning-a-specific-persons-voice)
- Music playback control on anything but Windows
