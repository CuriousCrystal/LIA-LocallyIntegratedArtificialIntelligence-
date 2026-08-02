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

## Giving her things to read

Drop `.pdf`, `.txt` or `.md` files into `LIA\library\` (or `dist\Lia\library\`
for the packaged app). She indexes them on startup, or right away with
`/library scan`. `/library` lists what she's read.

She retrieves *passages*, not whole documents, and cites the file and page. Ask
about something specific and she'll find it; ask her to summarise a 300-page book
and she'll only see the few passages that matched. Indexing costs about half a
second per passage, once per file. Scanned PDFs won't work — there's no OCR.

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

**Music** needs nothing at all — it uses Windows' own System Media Transport
Controls, the same thing behind your keyboard's media keys, so it works with
whatever's actually playing (Spotify, a browser tab, Windows Media Player)
without her needing to know which. It's a remote, not a jukebox — it can't
start a track from nothing, and she'll say so honestly rather than guess:

```
"play music" / "pause music" / "next song" / "previous song"
"what song is this" / "what's playing"
```

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
it. This alone is a soft comfort signal, not a lock: a clear mismatch means she
won't use your name and won't share what she remembers about you, but she never
simply refuses to talk. The harder lock is the access gate below.

`/whoami` shows enrollment progress and the last confidence score; `/whoami forget`
clears the profile and starts over. **Real-world accuracy is unverified from
development** — it was only tested against synthetic TTS voices, which likely
*understates* how well it discriminates real human voices (see
`speaker_id.py`'s docstring). `SPEAKER_MATCH_THRESHOLD` in `config.py` is a
starting point, not a calibrated answer — expect to retune it once there's real
usage data.

## The access gate

Every session starts locked. Say the identity phrase ("Lia, it's Wade") within
the first exchange, or she asks for a spoken passcode instead of acting on
anything. Get it right and the session unlocks for good; get it wrong and she
**stops listening entirely** — recoverable only by hand (the tray menu, or typing
`/mic on`), deliberately not by voice, or the lock would be trivial to talk past.

The passcode is read from an environment variable, the same pattern as the API
keys — never hardcoded in `config.py`, since that file may end up in a public
repo:

```powershell
[Environment]::SetEnvironmentVariable('LIA_PASSCODE', 'your-word', 'User')
```

**Left unset, the gate quietly doesn't engage** — every session is treated as
already unlocked, with a one-time log line saying so, rather than locking you
out with a passcode that can never be typed correctly.

A second, separate phrase — set in `config.py` as `PASSCODE_EXPLAIN` — works
independently of the gate, any time, unlocked or not: say it and she reads out
and explains `LIA/docs/Lia - Tools We Used.pdf` in her own words. It doesn't
grant access to anything, so it stays a plain constant rather than an
environment variable.

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
