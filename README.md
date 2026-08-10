# LIA — Locally Integrated Artificial Intelligence

A companion that runs entirely on your machine. No API keys, no accounts, no
network. Once the models are pulled, nothing she does leaves the laptop.

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

## Offline, completely

`INTERNET_ENABLED = False`. She makes no network calls at all beyond Ollama on
your own machine.

Weather and "look that up" were built and are still in `internet.py`, switched
off rather than deleted — weather needed no key, lookups needed a Groq or
OpenRouter one. Set `INTERNET_ENABLED = True` (and `WEATHER_ENABLED = True`) to
bring them back.

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
| `NUM_CTX` | 8192 keeps her mostly on the GPU on a 4GB card. Ollama's 32k default spills 63% to CPU. Check with `ollama ps`. |
| `OLLAMA_KEEP_ALIVE` | `"30m"` avoids a 9s cold start; costs ~3.7GB of VRAM held. Lower it on battery. |
| `VAD_SILENCE_SECONDS` | raise if she cuts you off mid-thought |
| `VAD_THRESHOLD` | raise if background noise triggers her |
| `MIC_SETTLE_SECONDS` | raise if she answers her own voice (headphones fix this outright) |
| `WHISPER_MODEL` | `small.en` gets names right that `base.en` garbles |
| `IDLE_MINUTES` | how long a silence ends the conversation |
| `VOICE_ENGINE` | `"piper"` (default) / `"system"` for the built-in Windows voice |

## Docs

`docs/` holds five generated PDFs, including
**How to Talk to Lia** — a plain-language guide for someone who has never used
her. Rebuild them with:

```powershell
pip install reportlab
python docs\build_guide.py
```

## Not built yet

- Merging duplicate facts (`sister_name` and `visiting_sister_name` both exist)
- Any way to make her forget a single note
- Voice cloning from a short recording — see [`voices/README.md`](LIA/voices/README.md)
- Music playback control on anything but Windows
- OCR, so scanned PDFs stay unreadable
