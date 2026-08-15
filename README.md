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
2. Pull the models:
   ```
   ollama pull llama3.2:3b
   ollama pull nomic-embed-text
   ```
3. Install the Python deps:
   ```
   pip install -r LIA/requirements.txt
   ```

Python 3.12 is the tested version. She needs a microphone; a GPU is optional but
a 4GB card runs `llama3.2:3b` at about 68% on-GPU with the default `NUM_CTX`.

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

**Say her name to start:** *"Lia, are you there?"* After she answers you have 30
seconds to keep talking normally without repeating her name. Each reply resets
the window.

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

Nothing else is written down. The conversation itself isn't stored, she doesn't
derive facts about you, and she doesn't keep a diary. Within a single
conversation she still has the last eight turns.

All three used to be automatic and all three are off for the same reason: **she
was inventing history that read exactly like real history.** The extractor
stored one fact twice under different keys; the diary once reflected at length
on the person "moving between unrelated topics", drawn entirely from a list of
test commands; and stored turns meant a half-finished thought from weeks ago
could resurface because it happened to score well against whatever you just
said. Once that's in the database it colours every later reply and nothing marks
it as a guess.

The switches are `REMEMBER_CONVERSATION`, `AUTO_EXTRACT_FACTS` and
`DIARY_ENABLED` in `config.py`. Turn any of them back on if you'd rather have it.

What's left in `lia_memory.db` (plain SQLite — inspect it with
`sqlite3 lia_memory.db`) is your name and the notes you explicitly asked her to
keep.

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

```
whole spoken turn      to first word
  local llama3.2:3b        2.19s     free, offline, least capable
  gpt-4o-mini (paid)       2.51s     ~$0.0001/turn
  gemma-4-26b (:free)      4.53s     free, rate limited
```

**Local is the fastest of the three.** The cloud is a quality trade, not a speed
one — that only became true after the `OLLAMA_URL` fix below cut local
first-token from 2.42s to 0.73s.

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

## Tuning

| setting | when to change it |
|---|---|
| `OLLAMA_URL` | **must be `127.0.0.1`, never `localhost`.** Ollama binds to IPv4; resolving `localhost` on Windows tries `::1` first and the failed attempt costs ~2s on *every* request. Measured: 2.38s vs 0.35s. |
| `CLOUD_CHAT_ENABLED` | off = fully local, faster, private, less capable |
| `CLOUD_HISTORY_TURNS` / `CLOUD_LIBRARY_TOP_K` | how much context a billed turn carries — the spend is in what's sent, not what returns |
| `JUDGE_ENABLED` | off = every turn searches your library again, which put 500 tokens of novel in front of "how was your day" |
| `NUM_CTX` | 8192 keeps her mostly on the GPU on a 4GB card. Ollama's 32k default spills 63% to CPU. Check with `ollama ps`. |
| `OLLAMA_KEEP_ALIVE` | `"30m"` avoids a 9s cold start; costs ~3.7GB of VRAM held. Lower it on battery. |
| `VAD_SILENCE_SECONDS` | raise if she cuts you off mid-thought |
| `VAD_THRESHOLD` | raise if background noise triggers her |
| `MIC_SETTLE_SECONDS` | raise if she answers her own voice (headphones fix this outright) |
| `WHISPER_MODEL` | `small.en` gets names right that `base.en` garbles |
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

## Not built yet

- Merging duplicate facts (`sister_name` and `visiting_sister_name` both exist)
- Voice cloning from a short recording — see [`voices/README.md`](LIA/voices/README.md)
- Music playback control on anything but Windows
- OCR, so scanned PDFs stay unreadable
