# LIA — Locally Integrated Artificial Intelligence

A companion who lives on your machine. She talks, she listens, she says what she
thinks — and the **only** memory she has of you is your own sticky notes, read
straight from your notes app. There is no database of her own any more: nothing
she "learns" can exist anywhere you haven't written it down yourself.

Her **thinking and hearing** go to a hosted OpenAI-compatible API (Groq's free
tier by default). **Speaking is local Piper** — free, on the machine, no
graphics card needed. The only models that run locally are text-to-speech and
voice-activity detection.

What "local" means now: your notes never leave the machine *on her account* —
she reads them from disk and puts the relevant words into each request, exactly
like the text of the conversation. The posture is *transmitted, not retained*:
`store: false` on every request, and a no-retention / no-training agreement on
the provider side.

This page is the short version. [`LIA/README.md`](LIA/README.md) is the full
reference.

## Setup

1. Install the Python deps:
   ```
   pip install -r LIA/requirements.txt
   ```
2. Give her a key. Either as a real environment variable:
   ```powershell
   setx GROQ_API_KEY "gsk_..."
   ```
   or in a gitignored [`LIA/.env`](LIA/.env.example) file (`python-dotenv`
   loads it; a real environment variable always wins).
   The models are knobs in [`LIA/config.py`](LIA/config.py) —
   `OPENAI_CHAT_MODEL`, `OPENAI_TRANSCRIBE_MODEL`. The defaults are Groq's
   free tier; repoint `OPENAI_BASE_URL` (e.g. at `api.openai.com`) for paid,
   higher-quality ones.
3. Point her at your memory. Set `NOTES_DIR` in `LIA/config.py` to the folder
   your sticky-notes app saves into (JSON or XML files). Until it exists she
   runs fine — she just knows nothing about you, and says so.

Python 3.12 is the tested version. She needs a microphone and a network
connection; with no API key set she can hear the mic but can't think or
transcribe.

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
prints goes to `lia.log` in the project root.

There's also a packaged build (`LIA\build_exe.ps1` → `dist\Lia\Lia.exe`) for
machines with no Python. `GROQ_API_KEY` still has to be in its environment.

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

**Spoken instructions** do something rather than becoming conversation:

```
"Lia, stop listening"  / "go to sleep"    → mic off
"Lia, be quiet"        / "stop talking"   → voice off
"Lia, what do you remember"               → reads your sticky notes back
"Lia, reload your notes"                  → re-reads the notes folder
```

When your words don't match the phrase list, `intent.py` asks the model what you
meant from the actions she can actually take — which, since the trim, are
switching her mic/voice/wake-word and reading your notes. Everything else is
conversation, which is the point of her.

## What she can do

- **Talk, and mean it.** When you ask what she thinks, she takes a position and
  gives her reasons — no fence-sitting, no briefing-document summaries. See
  `SYSTEM_PROMPT` in `config.py` (`WHAT YOU THINK`).
- **Remember what you write down.** Her memory is your sticky notes,
  read-only. She can never add, edit or delete a note; if you want her to know
  something, you write it in your notes app — the same place you always have —
  and it simply becomes part of what she knows. Because nothing is stored on
  her side, the old invented-facts problem is structurally impossible rather
  than merely switched off.
- **Hear you and speak**, streamed sentence-by-sentence in a local Piper voice.

That's the whole list. No music, no volume control, no alarms, no document
library, no web search, no voice ID — those were removed by design, not lost.

## What she remembers

Exactly what your sticky notes contain, nothing more and nothing less. Within a
conversation she keeps the last `CLOUD_HISTORY_TURNS` (4) turns of context;
when a conversation sits idle past `IDLE_MINUTES` it rolls over. Nothing from
any session is ever written to disk — there is no database to write to.

The caps that keep a fat notes folder from crowding out the conversation:
`NOTES_MAX_NOTES` (200) and `NOTES_MAX_CHARS` (6000), both in `config.py`.

## What leaves the machine, and what doesn't

| stays here | goes to the API |
|---|---|
| your sticky notes (read from disk, never written) | the text of your conversation |
| your voice, as audio | a WAV of each utterance, to be transcribed |
| the wake word, voice-activity detection, the TTS voice | the last `CLOUD_HISTORY_TURNS` (4) turns, for continuity |

`store: false` is set on every request, so the provider does not keep the
completion for its own dashboards. Whether the request is retained beyond that is
an org-level setting on the provider side — OpenAI does not train on API data by
default, and Zero Data Retention is available to approved orgs.

### Cost and speed

Every turn bills: the reply and the transcription of what you said. The prompt
size is where most of the chat spend is, which is why `CLOUD_HISTORY_TURNS` is
kept at 4. `CLOUD_LOG_USAGE` prints the token count of each turn to the log as
it happens. Every failed request — rate limit, dropped stream, empty reply — is
recorded to `cloud_fallback_log.jsonl`; `python LIA\fallback_report.py` reads it
back over a window.

## The files

| file | what it does |
|---|---|
| `config.py` | every prompt and tunable. **Edit this first** if her tone feels off. `NOTES_DIR` points at your notes app's save folder. |
| `notes.py` | her memory — reads your sticky-notes app's JSON/XML files, read-only |
| `main.py` | the conversation loop |
| `app.py` | tray app wrapper for running her in the background |
| `llm.py` | the one path to the hosted API — chat, streaming chat, transcription |
| `voice.py` | speaking (Piper only) and listening (hosted STT + local VAD) |
| `intent.py` | works out what you meant when no phrase matches |
| `mascot.py` | the desktop character — idle / listening / thinking / speaking |
| `panel.py` | typed window for reaching her without a microphone — currently switched off (`TRAINING_PANEL_ENABLED`) |
| `fallback_report.py` | reads back `cloud_fallback_log.jsonl` |

## Tuning

| setting | when to change it |
|---|---|
| `NOTES_DIR` | **where her memory lives** — the folder your sticky-notes app saves JSON/XML into |
| `NOTES_MAX_NOTES` / `NOTES_MAX_CHARS` | caps so a big notes folder can't crowd out the conversation |
| `OPENAI_BASE_URL` | the API endpoint. `https://api.groq.com/openai/v1` by default; point it at OpenAI, an Azure gateway or a private proxy without touching code. |
| `GROQ_API_KEY` / `OPENAI_API_KEY` | read from the environment or `LIA/.env` (Groq checked first). No key = she hears the mic but can't think or transcribe. |
| `OPENAI_CHAT_MODEL` | `llama-3.3-70b-versatile` on Groq by default (`llama-3.1-8b-instant` is the quick one). |
| `OPENAI_TRANSCRIBE_MODEL` | `whisper-large-v3` by default; `whisper-large-v3-turbo` is faster, slightly weaker on names. |
| `VOICE_NAME` | which Piper voice in `LIA/voices/` (`en_US-amy-medium` by default; `auto` takes the first found). |
| `CLOUD_HISTORY_TURNS` | how much context a turn carries — the chat spend is in what's sent, not what returns |
| `VAD_SILENCE_SECONDS` | raise if she cuts you off mid-thought |
| `VAD_THRESHOLD` | raise if background noise triggers her |
| `MIC_SETTLE_SECONDS` | raise if she answers her own voice (headphones fix this outright) |
| `IDLE_MINUTES` | how long a silence rolls the conversation over |
| `SYSTEM_PROMPT` | her personality — including `WHAT YOU THINK`, the opinions section |

## Not built yet

- Writing notes back to your app (she is deliberately read-only; say the word
  and it can be built against your app's save format)
- A name in her vocabulary hint, pulled from your notes, so Whisper stops
  respelling it
- Anything the removed features did — by design, not omission
