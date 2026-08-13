# LIA — Locally Integrated Artificial Intelligence

A companion who lives on your machine. Her voice, her hearing, her memory and
your documents are local. The **thinking** is not — the conversation goes to a
hosted model, because the one thing a 4GB card can't fix is how capable the
model is. See [What leaves the machine](#what-leaves-the-machine).

She falls back to the local model whenever the network isn't there, so a dropped
connection costs cleverness rather than speech. `CLOUD_CHAT_ENABLED = False`
puts her back to fully offline: faster, private, and noticeably less bright.

Weather and online lookups are a separate thing, still switched off.

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
"do you know my voice"  /  "is that me"       → speaks her voice-ID status
"what have you remembered"                    → reads back your notes, numbered
"forget number 2"                             → deletes that one note
"ask dog for a suggestion on X"               → a second opinion from a named model
"who can you ask"                             → lists who's available
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

## What leaves the machine

| stays here | goes to the hosted model |
|---|---|
| your audio — Whisper runs locally, nothing is uploaded | the text of your conversation |
| everything she remembers about you | the last `CLOUD_HISTORY_TURNS` (4) turns |
| your documents and the search over them | up to `CLOUD_LIBRARY_TOP_K` (2) passages, only when the judge says you asked about a document |
| the judge, `intent.py`, fact extraction | — |

Keeping the classifiers local is most of the cost control. The judge runs on
every turn and `intent.py` whenever a phrase doesn't match; billing those would
multiply the spend for work a 3B already does well. Only `chat_stream()` — what
you actually say to her — leaves.

**Measured, whole spoken turn:**

```
  local llama3.2:3b     2.19s    free, offline, least capable
  gpt-4o-mini (paid)    2.51s    ~$0.0001/turn
  gemma-4-26b (:free)   4.53s    free, rate limited
```

Local is the *fastest* of the three. The cloud is a quality trade and nothing
else — which only became true once the `OLLAMA_URL` fix cut local first-token
from 2.42s to 0.73s.

A `:free` model is rate limited rather than billed, so expect the occasional
429 and the occasional dropped stream. Both fall back to the local model and
both say so in the log; a reply that stops mid-thought is otherwise a mystery.

That table above is one afternoon's measurement, and free-tier reliability
isn't something one session can answer. Every fallback — rate limited, or
dropped mid-stream — is also recorded to `cloud_fallback_log.jsonl`
(`CLOUD_FALLBACK_LOG` in `config.py`). Run `python LIA\fallback_report.py`
after a week of real use to see how often it's actually happening before
deciding whether `:free` is worth staying on.

## Asking someone else

A second, separate cloud path — not the conversation itself, but a *named*
model, consulted on request:

```
"Lia, ask dog for a suggestion on remembering to drink water"
"ask cat what she thinks about this"
"who can you ask"                     → lists who's available
```

Three names, each a light, fast free-tier model on OpenRouter (`AGENTS` in
`config.py`):

| name | model | typical total time |
|---|---|---|
| `dog` | `nvidia/nemotron-nano-12b-v2-vl:free` | ~1–2s |
| `cat` | `nvidia/nemotron-3-nano-30b-a3b:free` | ~2s |
| `fox` | `poolside/laguna-s-2.1:free` | ~2s |

She relays the answer attributed — *"Dog says: ..."* — the same way she
cites a library passage rather than folding it into her own words. It's a
real second network call on top of her own reply, so like weather and
lookups, it only happens when asked by name, never automatically. A rate
limit, timeout, or empty reply gets said plainly ("Dog's rate limited right
now") rather than silence — and every call is capped at `AGENT_TIMEOUT_SECONDS`
(15s) regardless of what the model does, after one was measured hanging for
121s and still coming back empty.

Picked light on purpose, and measured on *total* time rather than time to
first word: `ask_agent()` collects the whole reply before she says any of
it, so unlike her own streamed replies, there's no first sentence to hide the
rest of the wait behind. The first pick for `dog` was
`google/gemma-4-26b-a4b-it:free` — answered correctly, just took 5.3s total,
heavier than a "second opinion" needs to be.

A fourth was tried and dropped rather than kept as the weak link. Every
lighter option for it either failed outright or turned out unreliable —
worked once, then failed empty five times in a row on a re-test — and the
one alternative that kept answering wasn't actually any lighter than what it
would have replaced. Three fast, genuinely reliable agents beat four with a
shaky one; a fourth can come back if something both light and consistent
turns up.

All three are `:free`, so this costs nothing to use — but free-tier
availability on OpenRouter's side changes over time and isn't always stable
run to run. Re-measure before swapping any of `AGENTS` — the comment above
it in `config.py` shows how, including *what* to measure: total time, not
first word, for this path specifically.

## Weather and lookups, still off

Unrelated to the above, and unchanged. `INTERNET_ENABLED = False`. Two things
used to reach out, and both are switched off rather than deleted:

- **Weather** — needed no key. Open-Meteo, geolocated from your IP, answered in
  her own voice. `WEATHER_ENABLED = True` and `INTERNET_ENABLED = True` bring it
  back.
- **"Look that up"** — needed a Groq or OpenRouter key, read from the
  environment and never pasted into a file. With OpenRouter and
  `OPENROUTER_ONLINE`, it ran a real web search rather than asking a bigger
  model to guess.

`internet.py` still holds all of it, unchanged. One caveat if you turn it back
on, found by testing: `is_online()` probes `https://1.1.1.1`, and some ISPs
hijack that address with a self-signed certificate — which makes her believe
she's offline when she isn't, and decline both features.

## Music

Music lives in `LIA\music\` (or `dist\Lia\music\`). Drop audio in and she
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

Two decoders sit behind that list. libsndfile (via `soundfile`) handles all of
it except AAC, which it has no decoder for — so `.m4a` was listed as a numbered
track and then refused to open, which is worse than not offering it. PyAV covers
that one, and arrives with `faster-whisper` anyway.

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
clears the profile and starts over. Ask out loud too — "do you know my voice",
"is that me" — and she answers the same thing spoken, which matters in the tray
app, where there's no console for `/whoami` to print to. "Forget" stays
typed-only on purpose: it isn't a phrase in `SPOKEN_COMMANDS`, so a profile
can't be cleared by anything merely overheard. **Real-world accuracy is unverified from
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

Nothing else is written down. The conversation itself isn't stored, she doesn't
decide for herself what's worth keeping, and she doesn't write a diary. Within a
single conversation she still has the last `SHORT_TERM_TURNS` turns as usual.

That's `REMEMBER_CONVERSATION = False`, `AUTO_EXTRACT_FACTS = False` and
`DIARY_ENABLED = False` in `config.py`. All three used to be on, and all three
are off for the same reason: **she was inventing history that read exactly like
real history.**

- The **extractor** stored the same fact twice under different keys.
- The **diary** once reflected at length on the person "moving between unrelated
  topics" — drawn entirely from a list of test commands.
- **Stored turns** meant a half-finished thought from three weeks ago could
  resurface because it scored well against whatever you just said. She never
  invented the quote, but pulling it into a conversation it had nothing to do
  with reads the same way from the outside — and unlike the other two, this one
  gets worse as the database grows.

Once any of that is in the database it colours every later reply, and there's
nothing marking it as a guess. Turn any of them back on if you'd rather have it.

Telling her the same thing twice doesn't store it twice — she says she already
has it.

**Forgetting one note** works the same way picking a track does: "what have
you remembered" reads every note back, numbered, and "forget number 2" removes
just that one. The number is a position in that list, not a database ID, so
it's only stable between a listing and the forget that follows it — same
guarantee `music.py`'s track numbers give.

What's left in `lia_memory.db` (plain SQLite — inspect it any time with
`sqlite3 lia_memory.db`) is **facts**: your name, plus the notes you explicitly
asked her to keep. The `memories` table still exists and is no longer read or
written; `MEMORY_TOP_K` and `MEMORY_MIN_SCORE` only matter if you switch
`REMEMBER_CONVERSATION` back on.

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
| `memory.py` | embedding, retrieval, fact extraction and sanitising — dormant while `REMEMBER_CONVERSATION` is off |
| `diary.py` | end-of-session reflection — switched off |
| `voice.py` | text-to-speech, speech recognition, voice activity detection |
| `main.py` | the conversation loop |
| `app.py` | tray app wrapper for running her in the background |
| `library.py` | reads PDFs and notes you drop in `library/` |
| `internet.py` | weather and online lookups — still switched off |
| `judge.py` | one closed question in front of the expensive work — "is this about a document?" |
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
| `OLLAMA_URL` | **`127.0.0.1`, never `localhost`.** Ollama binds to IPv4; resolving `localhost` on Windows tries `::1` first and the failed attempt costs ~2s on *every* request. Measured 2.38s vs 0.35s — it was the largest single cost in a spoken turn. |
| `CLOUD_CHAT_ENABLED` | off = fully local: faster, private, less capable |
| `OPENROUTER_MODEL` | a `:free` suffix means rate limited rather than billed |
| `JUDGE_ENABLED` | off = every turn searches the library again |
| `RETRIEVAL_MIN_WORDS` | skips library lookup below this many words — raise it if short replies still feel slow |
| `REMEMBER_CONVERSATION` | on: she stores and searches every turn again. Off by default — see [How she remembers](#how-she-remembers) |
| `INTERNET_ENABLED` | on: weather and "look that up" come back — see [Offline, completely](#offline-completely) |

## Not built yet

- Merging duplicate facts (`sister_name` and `visiting_sister_name` both exist)
  — only reachable through `AUTO_EXTRACT_FACTS`, which is off, so this is
  dormant rather than a live gap. Revisit if that flag comes back on.
- OCR, so scanned PDFs stay unreadable
- Voice cloning from a short recording — see [`voices/README.md`](voices/README.md#cloning-a-specific-persons-voice)
- Music playback control on anything but Windows
