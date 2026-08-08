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

**She won't quote herself back at you.** Two things used to end up stored as
things *you* had said, and she would later repeat them to you as your own
words:

- **Her own voice**, picked up through the speakers a moment after she finished
  speaking. Echo detection used to run only *while* she was talking, so her
  spoken confirmations landed in memory as yours — *"There's nothing new to
  read, I've already read everything in there"* was sitting in her memory as a
  line of Wade's.
- **Whisper's vocabulary hint.** Given near-silence, the recogniser hands its
  own prompt back as a transcript, so *"This is a conversation with Lia"*
  became a stored user turn.

Both are filtered now, on every input path.

**She uses your name once, not every sentence.** The system prompt asks for
that and a 3B ignores it, so it's enforced in code: vocative uses after the
first are removed from what she says. Genuine mentions ("Wade's birthday")
survive.

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

Files are read directly, every time. There is deliberately **no conversion
cache** — she doesn't keep a second, plain-text copy of your library. Convert
things yourself if you want them converted.

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

**Music** lives in `LIA\music\` (or `dist\Lia\music\`). Drop audio in and she
plays it by number:

```
"what music do you have"    →  she reads out the numbered list
"play number 1"  /  "play song 3"  /  "play the second song"
"play Fireflies"            →  by name, if the filename matches
"play some music"           →  she lists what she has, so you can pick
"stop the song"
```

Numbering follows filename order, so number 3 means the same thing tomorrow.
Playback goes through her own audio — no window opens — and while she speaks
the music drops to a murmur rather than stopping. `.mp3 .wav .flac .ogg .m4a
.aiff`. See [`music/README.md`](music/README.md).

She plays **only her own files**. Controlling Spotify or a browser tab through
Windows' media keys was built and then removed by request: it could operate
someone else's player but never start anything, which made it a confusing
sibling to a folder where she genuinely can.

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

**She only keeps what you tell her to.** Say *"remember that…"*, *"don't forget
I…"*, *"note that…"* and it's stored, word for word:

```
"remember that the wifi password is bluebird"
"don't forget my sister is called Anaya"
```

Nothing else about you is written down. She doesn't decide for herself what's
worth keeping, and she doesn't write a diary.

That's `AUTO_EXTRACT_FACTS = False` and `DIARY_ENABLED = False` in `config.py`.
Both used to be on, and both are off for the same reason: **she was inventing
history that read exactly like real history.** The extractor stored the same
fact twice under different keys, and the diary once reflected at length on the
person "moving between unrelated topics" — drawn entirely from a list of test
commands. Once that's in the database it colours every later reply, and there's
nothing marking it as a guess. Turn either back on if you'd rather have it.

Telling her the same thing twice doesn't store it twice — she says she already
has it.

What's still in `lia_memory.db` (plain SQLite — inspect it any time with
`sqlite3 lia_memory.db`):

- **facts** — your name, plus the notes you explicitly asked her to keep
- **memories** — every turn, embedded, searched by cosine similarity. Only
  *your* turns are retrieved; hers competing for the same slots made her quote
  her own speculation back as fact. A relevance floor (`MEMORY_MIN_SCORE`)
  drops weak matches rather than forcing in the closest thing available.

A conversation ends when you say `bye`, or on its own after `IDLE_MINUTES` of
silence.

### Testing her without leaving traces

```powershell
python LIA\main.py --no-save      # or: dist\Lia\Lia.exe --no-save
```

Nothing reaches the database — no stored turns, no notes, no facts. Alarms are
the deliberate exception: those are an action you asked for, not history she
wrote about you.

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
| `media.py` | system volume (Core Audio) |
| `alarms.py` | spoken alarms and timers — regex-parsed, never guessed by the model |
| `music.py` | her own music — files in `music/`, played by number |
| `intent.py` | works out what you meant when no phrase matches |
| `speaker_id.py` | voice recognition — is this the enrolled voice or not |
| `voices/` | drop your own voice files here — see `voices/README.md` |
| `library/` | drop PDFs here — see `library/README.md` |
| `music/` | drop audio here — see `music/README.md` |
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
