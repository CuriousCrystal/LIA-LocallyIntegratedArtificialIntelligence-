# LIA — Locally Integrated Artificial Intelligence

A companion who lives on your machine. Her voice, her hearing, her memory and
your documents are all local. The **thinking** is not: the conversation goes to
a hosted model, because the one thing a 4GB card can't fix is how capable the
model is.

She falls back to a local model whenever the network isn't there, so losing the
connection costs cleverness, not speech. Set `CLOUD_CHAT_ENABLED = False` and
she runs entirely offline again — faster, private, and noticeably less bright.

This page is the short version. [`LIA/README.md`](LIA/README.md) is the full
reference — every feature, and the reasoning behind the choices.

## Setup

1. Install [Ollama](https://ollama.com)
2. Pull the models — whichever chat model you set as `MODEL_CHAT`:
   ```
   ollama pull gemma2:2b        # the current default
   ollama pull llama3.2:3b      # brighter, if you have the headroom
   ollama pull nomic-embed-text
   ```
3. Install the Python deps:
   ```
   pip install -r LIA/requirements.txt
   ```
4. Optional, for speech recognition on an Intel NPU — see
   [`LIA/models/README.md`](LIA/models/README.md). Without it she falls back to
   `faster-whisper` on the CPU by herself.

Python 3.12 is the tested version. She needs a microphone.

A GPU is optional and no longer assumed. She was built on a machine with a 4GB
card, where `llama3.2:3b` ran about 68% on-GPU at the default `NUM_CTX`; she now
runs on a Core Ultra 7 255U with no discrete card at all, generating about 21
tokens a second on the CPU — comfortably faster than she can speak them. What
the graphics card bought was never speed so much as somewhere to put the model
that wasn't competing with everything else.

## Running her

```powershell
pythonw LIA\app.py     # tray app -- no window, open mic, this is the normal way
python  LIA\main.py    # terminal -- same companion, but you can type to her too
```

To have her start when you log in:

```powershell
powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 install
```

`remove` and `status` do what you'd expect. With no console, everything she
prints goes to `lia.log` in the project root. She waits for Ollama on startup
and launches it if it isn't running — at login she almost always wins the race,
and without that she'd crash every boot.

There's also a packaged build (`LIA\build_exe.ps1` → `dist\Lia\Lia.exe`, ~366MB)
for machines with no Python. Ollama still has to be installed separately.

## Talking to her

**Say her name to start:** *"Lia, are you there?"* Every time — the follow-up
window is currently `0` (`CONVERSATION_WINDOW_SECONDS`), because with it open a
television in the same room was being transcribed in full and answered as though
it were you. Set it back to 20 or 30 if your room is quiet and you would rather
have the easy back-and-forth. Her startup greeting is the exception and still
gives you 30 seconds to answer.

The wake word is matched on the transcript rather than a dedicated model, so it
needs no training and tolerates Whisper's spellings — "Leah", "Lea", "Liya" all
count.

**Interrupting her:** just start talking. The mic stays open while she speaks,
and anything it hears is checked against what she's currently saying — her own
voice through the speakers is ignored, yours cuts her off.

**Spoken instructions** do something rather than becoming conversation:

```
"Lia, stop listening"  / "go to sleep"    → mic off
"Lia, be quiet"        / "stop talking"   → voice off
"Lia, read my files"                      → index the library folder
"play number 2"        / "stop the song"  → her own music
"turn it up"           / "mute"           → system volume
"remind me in 20 minutes"                 → a real alarm
```

When your words don't match the phrase list, `intent.py` asks the model what you
meant from the actions she can actually take. Measured at 30 of 32 correct,
including every "this is just conversation, don't act on it" case.

## What she can do

| | |
|---|---|
| **Read** | `.pdf` `.epub` `.docx` `.txt` `.md` dropped in `LIA\library\`. She cites the file and page. No OCR, so scanned pages won't work. |
| **Music** | `.mp3` `.wav` `.flac` `.ogg` `.m4a` `.aiff` in `LIA\music\`, played by number. Ducks under her voice instead of stopping. |
| **Volume** | Windows Core Audio directly, not a simulated key press. |
| **Alarms** | Regex-parsed, never guessed by the model — "wake me in half an hour", "set a timer for 5", "remind me to stretch in 20 minutes". |
| **Voice ID** | Says whether you sound like the enrolled voice. A comfort signal, not a lock. |

## What she remembers

**Only what you tell her to.** Say *"remember that…"*, *"don't forget…"*,
*"note that…"* and it's stored word for word:

```
"remember that the wifi password is bluebird"
"lia remember this — my sister is called Anaya"
```

She doesn't derive facts about you, and she doesn't keep a diary. Within a
single conversation she still has the last eight turns.

**The conversation itself is stored again** (`REMEMBER_CONVERSATION = True`).
That is a change from what this page used to say, and it is deliberate: with it
off she had no recollection of anything from an earlier session, which turned
out to be the thing underneath the complaint that she never seemed to grow. The
dial that actually governs the confusion it used to cause is
`MEMORY_MIN_SCORE`, raised to 0.55 after checking it against real stored turns —
not the storage itself. Set it back to `False` if you would rather she forgot.

Fact extraction and the diary stay off, for the same reason both were turned off
originally: **she was inventing history that read exactly like real history.**
The extractor
stored one fact twice under different keys, and the diary once reflected at
length on the person "moving between unrelated topics", drawn entirely from a
list of test commands. Once that's in the database it colours every later reply
and nothing marks it as a guess.

The switches are `REMEMBER_CONVERSATION`, `AUTO_EXTRACT_FACTS` and
`DIARY_ENABLED` in `config.py`. Turn any of them on or off as you'd rather.

`lia_memory.db` (plain SQLite — inspect it with `sqlite3 lia_memory.db`) holds
your name, the notes you explicitly asked her to keep, the documents she has
indexed, and — with `REMEMBER_CONVERSATION` on — the conversation itself.

### Testing her without leaving traces

```powershell
python LIA\main.py --no-save
```

Nothing reaches the database. Alarms are the deliberate exception: those are an
action you asked for, not history she wrote about you.

## What leaves the machine, and what doesn't

| stays here | goes to the hosted model |
|---|---|
| your audio — Whisper runs locally, the recording is never uploaded | the text of your conversation |
| everything she remembers about you | the last 4 turns, so a reply makes sense |
| your documents, and the search over them | up to 2 matched passages, and only when the judge says you asked about one |
| every classifier — the judge, `intent.py`, fact extraction | — |

Keeping the classifiers local is most of the cost control: the judge runs on
*every* turn, so billing it would multiply the spend for work a 3B does well.

Set `CLOUD_CHAT_ENABLED = False` to go back to fully local.

**Weather and "look that up"** remain switched off (`INTERNET_ENABLED = False`)
and are unrelated to the above — they're still in `internet.py`, waiting on a
flag.

### Cost and speed, measured

On the original machine, 4GB card, `llama3.2:3b`:

```
whole spoken turn      to first word
  local llama3.2:3b        2.19s     free, offline, least capable
  gpt-4o-mini (paid)       2.51s     ~$0.0001/turn
  gemma-4-26b (:free)      4.53s     free, rate limited
```

**Local is the fastest of the three.** The cloud is a quality trade, not a speed
one — that only became true after the `OLLAMA_URL` fix below cut local
first-token from 2.42s to 0.73s.

On the current machine, Core Ultra 7 255U, no discrete card, `gemma2:2b`:

```
                       to first word
  turn 1 of a session      2.35s     prompt read once, at startup
  every turn after         ~1.0s     prompt prefix cached
  generation             21 tok/s    against speech's ~5 tok/s
  hearing (NPU)         0.11-0.31s
```

The wait was never the model writing, it was the model *reading*: her 575-token
system prompt goes in at about 110 tok/s cold, which was 5.3 seconds before she
said a word. Ollama caches the prefix, so that is a once-per-session cost — and
`prewarm()` now pays it during startup, when nobody is waiting. Turn one went
from 7.46s to 2.35s.

Models with a `:free` suffix are rate limited rather than billed. A 429 or a
dropped stream falls back to the local model; both are announced in the log
rather than passed off as normal.

Set the key in the environment, never in a file:

```powershell
[Environment]::SetEnvironmentVariable('OPENROUTER_API_KEY', 'your-key', 'User')
```

## The files

| file | what it does |
|---|---|
| `config.py` | every prompt and tunable. **Edit this first** if her tone feels off. |
| `main.py` | the conversation loop |
| `app.py` | tray app wrapper for running her in the background |
| `llm.py` | Ollama wrapper — chat, streaming chat, embeddings |
| `db.py` | SQLite schema and queries |
| `memory.py` | embedding, retrieval, fact extraction and sanitising |
| `library.py` | reads documents you drop in `library/` |
| `voice.py` | text-to-speech, speech recognition, voice activity detection |
| `music.py` | her own music — files in `music/`, played by number |
| `media.py` | system volume (Core Audio) |
| `alarms.py` | spoken alarms and timers |
| `intent.py` | works out what you meant when no phrase matches |
| `speaker_id.py` | voice recognition — is this the enrolled voice or not |
| `internet.py` | weather and online lookups — currently switched off |
| `diary.py` | end-of-session reflection — currently switched off |
| `judge.py` | asks whether a question is about a document, before searching for one |
| `panel.py` | typed window for reaching her without a microphone — currently switched off (`TRAINING_PANEL_ENABLED`) |
| `fallback_report.py` | reads back `cloud_fallback_log.jsonl` |

## Tuning

| setting | when to change it |
|---|---|
| `OLLAMA_URL` | **must be `127.0.0.1`, never `localhost`.** Ollama binds to IPv4; resolving `localhost` on Windows tries `::1` first and the failed attempt costs ~2s on *every* request. Measured: 2.38s vs 0.35s. |
| `CLOUD_CHAT_ENABLED` | off = fully local, faster, private, less capable |
| `CLOUD_HISTORY_TURNS` / `CLOUD_LIBRARY_TOP_K` | how much context a billed turn carries — the spend is in what's sent, not what returns |
| `JUDGE_ENABLED` | **currently off.** It cost a model call on every turn — 2.3–2.9s on the 255U against 0.49s on the old machine — to decide whether to spend 0.05s searching. `LIBRARY_MIN_SCORE` does the job alone now. Turn it back on if she starts quoting a book at small talk. |
| `LIBRARY_MIN_SCORE` | raised to `0.52` to take over from the judge. Measured 15/16 against the judge's 11/12 on the same questions, at 45ms instead of 2.5s — but on a small library. Re-measure if yours grows. |
| `NUM_CTX` | 8192 keeps her mostly on the GPU on a 4GB card. Ollama's 32k default spills 63% to CPU. Check with `ollama ps`. On a CPU-only machine this is ordinary RAM instead, and 8192 is still a sensible size. |
| `OLLAMA_KEEP_ALIVE` | `-1` keeps her loaded indefinitely, avoiding a 9s cold start. With no discrete card that memory is your ordinary RAM, so `"30m"` is the kinder setting on a laptop. |
| `VAD_SILENCE_SECONDS` | raise if she cuts you off mid-thought |
| `VAD_THRESHOLD` | raise if background noise triggers her |
| `MIC_SETTLE_SECONDS` | raise if she answers her own voice (headphones fix this outright) |
| `WHISPER_MODEL` | currently `base.en`. `small.en` gets names right that `base.en` garbles, at roughly 1.7s more per turn on CPU — much less on the NPU. |
| `WHISPER_BACKEND` | `"openvino"` to hear on an Intel NPU, `"faster-whisper"` for the plain CPU path. Falls back on its own if OpenVINO or the model is missing. |
| `WHISPER_DEVICE` | `NPU` / `GPU` / `CPU`. On a Core Ultra 7 255U the NPU transcribes a short sentence in 0.11s against faster-whisper's 0.55s — and does it on silicon the language model isn't using. See [`LIA/models/README.md`](LIA/models/README.md). |
| `IDLE_MINUTES` | how long a silence ends the conversation |
| `VOICE_ENGINE` | `"piper"` (default) / `"system"` for the built-in Windows voice |

## Docs

`docs/` holds six generated PDFs:

| doc | what it's for |
|---|---|
| **How to Talk to Lia** | plain-language guide for someone who's never used her |
| **Lia - Tools We Used** | what every library/API/model is, and why it's here |
| **Lia - Growth Log** | historical narrative — what kind of thing she was, stage by stage |
| **Lia - Phase Roadmap** | *living* status — what's done, what's next, what's explicitly not scheduled |
| **Lia - Session Summary** / **Session Transcript** | frozen — from the original build session, not regenerated |

Rebuild the first four with:

```powershell
pip install reportlab
python docs\build_guide.py
python docs\build_tools.py
python docs\build_growth_log.py
python docs\build_phases.py
```

`docs/` also collects dated `test_session_*.md` files — plain-text snapshots
of a full feature regression pass with response times, kept for comparing
speed and reliability over time rather than trusting memory of "it felt
fine." Not regenerated; a new one is added per pass.

The latest is [`test_session_2026-08-20.md`](docs/test_session_2026-08-20.md):
104 of 104 checks in 34.3s, the first full pass on a machine with no graphics
card. Every timing recorded before it was measured on hardware that no longer
exists, so it is the one to compare against.

## Not built yet

- Merging duplicate facts (`sister_name` and `visiting_sister_name` both exist)
- Voice cloning from a short recording — see [`voices/README.md`](LIA/voices/README.md)
- Music playback control on anything but Windows
- OCR, so scanned PDFs stay unreadable
