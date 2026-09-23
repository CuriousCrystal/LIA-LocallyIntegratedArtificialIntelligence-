# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

LIA ("Lia") is a Windows-only voice companion in Python 3.12. **Chat and
speech-to-text** go to a hosted **OpenAI-compatible API** (`OPENAI_BASE_URL`,
default `api.groq.com`). **Text-to-speech is local Piper** — free, on-machine,
the only TTS engine. Her **memory is the user's own sticky-notes application**:
a C# app that saves JSON/XML note files into one folder, which `notes.py` reads
**read-only**. There is no database, no actions (no alarms, music, volume,
library), and no speaker recognition — all removed by design; don't reintroduce
them without asking. No build system beyond `pip`, no package layout — `LIA/`
is a flat set of modules run as scripts.

Nothing here keeps the conversation on the machine — sending your words to the
API is what a reply *costs*. The privacy posture is "transmitted, not
retained": `store: false` on every request and small classifier prompts. The
notes themselves are read from disk and sent as context, which is the same
exposure as the conversation text.

## Commands

Setup:
```
pip install -r LIA/requirements.txt
# then provide a key (GROQ_API_KEY for the default provider), either way:
setx GEMINI_API_KEY "AIza..."                # default now: Google AI Studio, free
setx GROQ_API_KEY "gsk-..."                  # or Groq / OPENAI_API_KEY + OPENAI_BASE_URL, or
cp LIA/.env.example LIA/.env && edit it      # LIA/.env (gitignored, loaded by config.py via python-dotenv)
# and set NOTES_DIR in LIA/config.py to the sticky-notes app's save folder
```
Never put the key in `config.py` — it's committed; a key pushed to GitHub is
auto-revoked by OpenAI's secret scanning. Model ids are config knobs in
[config.py](LIA/config.py): `OPENAI_CHAT_MODEL`, `OPENAI_TRANSCRIBE_MODEL`.

Run:
```
python  LIA\main.py            # console: talk or type
pythonw LIA\app.py             # tray app, no console window (logs to lia.log)
python  LIA\app.py --debug     # tray app with a console and live logging
```

Package / deploy (Windows PowerShell):
```
powershell -ExecutionPolicy Bypass -File LIA\build_exe.ps1                 # -> dist\Lia\Lia.exe
powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 install         # run at login (tray)
powershell -ExecutionPolicy Bypass -File LIA\autostart.ps1 remove|status
```
`GROQ_API_KEY` (or `OPENAI_API_KEY` with the base URL repointed) must be in the
environment the packaged exe runs in too; it is never bundled.

Utilities:
```
python LIA\fallback_report.py [--days 30]   # how often the API is unreachable
```

Tests / lint: none configured. There is no test runner, linter, or formatter in
the repo. The `docs/test_session_*.md` files are hand-written records of manual
full-feature regression passes, not an executable suite.

## Architecture

### Entry points and the loop
- `main.py` owns the conversation loop (`main()`, `read_input()`,
  `handle_command()`, `as_instruction()`). It is single-threaded; everything
  else runs on daemon threads (keyboard reader, idle watchdog, TTS worker).
- `app.py` is the tray wrapper: fans stdout/stderr into `lia.log`, runs
  `main.main(controls)` on a daemon thread, shows the pystray icon, and — when
  `MASCOT_ENABLED` — runs `mascot.Mascot` (a Tkinter desktop character) on the
  main thread.
- `mascot.py` — frameless always-on-top window, sprite states idle / listening
  / thinking / speaking (from `LIA/mascot/`), drag to move, left-click toggles
  listening, right-click menu. `app.py._mascot_state()` picks the pose from
  `Controls.speaker.is_busy()` (→ `speaking`), `Controls.thinking`, and
  `Controls.state["listening"]`. A state with no art borrows `idle`'s frames;
  no art at all → a drawn cat face.
- `Controls` (in `main.py`) is the object other threads use to pause/quit and
  to read loop state (`thinking`, `speaker`). `panel.Panel` and `Keyboard`
  share a `.pending()/.take()` interface so `read_input()` can't tell stdin
  from the GUI box.

### Per-turn flow
1. `read_input()` returns the next utterance — from `voice.Listener` (local
   VAD → hosted transcription) or the keyboard. Voice input is gated by the
   wake word (`accept_spoken()`). There is no echo filter or barge-in any
   more: she must finish speaking before the mic reopens (`MIC_SETTLE_SECONDS`
   exists for the speaker tail).
2. `as_instruction()` is a **deterministic ladder**: `/`-prefixed passthrough →
   `SPOKEN_COMMANDS` phrase match (`spoken_command()`) → `intent.route()` (the
   only LLM step, and only when `intent.might_be_action()` says the words could
   plausibly be a request).
3. Slash commands go to `handle_command()` (`/voice`, `/mic`, `/openmic`,
   `/wake`, `/notes`, `/help`). Everything else is conversation:
   `build_system_message()` (SYSTEM_PROMPT + live time + the sticky-notes
   block) plus recent history, then `llm.chat_stream()`.

### Her memory — `notes.py`
- The user's own C# sticky-notes app saves notes as JSON/XML files in one
  folder (`NOTES_DIR` in config.py). `notes.all_notes()` reads it with an
  mtime-based cache, flattens whatever JSON/XML shape it finds into plain-text
  notes (skipping ids, dates, window geometry), caps the result
  (`NOTES_MAX_NOTES`, `NOTES_MAX_CHARS`), and `as_context()` renders it as a
  labelled system block: *their words, the only memory there is, never
  invent beyond it*.
- **Strictly read-only.** She has no way to write a note and must not gain
  one without the user asking.
- A missing folder is a normal state (empty memory, reported once); an
  unparsable file is reported once and never blanks the rest of the memory.
- Nothing else in the app persists anything. There is no `db.py`; the
  conversation lives only in the `Session` context window and rolls over
  after `IDLE_MINUTES`.

### Models — `llm.py` is the only module that calls the API
- `chat()` / `chat_stream()` — `POST {base}/chat/completions` (`chat_stream`
  streamed), `store: false`. **No fallback**: on failure they raise
  `llm.CloudError` and the caller in [main.py](LIA/main.py) says so plainly. A
  429 is split by error body into `RateLimited` (wait and retry) vs
  `QuotaExhausted` (`insufficient_quota` — account out of credit, waiting
  won't help), and main.py speaks the right one. Errors logged to
  `cloud_fallback_log.jsonl` (kept for `fallback_report.py`).
- `transcribe(audio_i16, sample_rate, prompt)` — WAV of the utterance → `POST
  {base}/audio/transcriptions`; returns `None` on failure.
- `have_key()` — just `bool(OPENAI_API_KEY)` (which itself prefers
  `GROQ_API_KEY`); with no key she hears the mic but can't think or
  transcribe.

### Configuration — `config.py`
Module-level constants: every prompt and tunable, each with a comment carrying
the reasoning. **Edit this first** for behavior/tone changes. `OPENAI_*` block
at the top holds the endpoint and per-capability model ids. Other behavior
flags: `LISTEN_ENABLED`, `OPEN_MIC`, `WAKE_WORD_ENABLED`,
`CONVERSATION_WINDOW_SECONDS` (0 = name required every turn), `NOTES_DIR` /
`NOTES_MAX_NOTES` / `NOTES_MAX_CHARS`, `GREET_ON_START` + `STARTUP_GREETING`
(static line; the diary-generated greeting is gone), `MASCOT_*`, and
`SYSTEM_PROMPT` — whose `WHAT YOU THINK` section is what makes her give real
opinions instead of fence-sitting.

### Voice — `voice.py`
- `Speaker`: local **Piper** only (`PiperEngine`, `.onnx` files in `voices/`).
  There is no cloud engine and no SAPI fallback; if Piper can't load, she is
  silent and says why once. `SentenceBuffer` splits the streamed reply into
  speakable sentences so speech starts before the reply finishes generating.
- `Listener`: records the utterance (int16 mono 16 kHz), sends it through
  `llm.transcribe()`. The only local model is `pysilero-vad` for open-mic turn
  detection; `warm_up()` just loads that.

### Narrow classifiers (kept local and cheap on purpose)
- `intent.py` — names which action (if any) an unmatched utterance meant; the
  only actions left are mic/voice/wake switching and the notes commands, plus
  `just_talk`. Logs every decision to `intent_log.jsonl` as raw material for a
  future fine-tune.

### Docs
`docs/*.pdf` are generated by `docs/build_*.py` with `reportlab`, which is
pip-installed separately and never imported by the app. **They describe the
older, bigger feature set** (library, music, alarms, speaker ID) and have not
been regenerated since the trim.

## Conventions to match when editing

- Prefer deterministic parsing (regex, phrase lists) over asking a model; the
  model is a fallback, not the first resort. See the `as_instruction()` ladder.
- Never invent memory, history, or facts about the person. The sticky notes are
  always presented as "their words, the only record there is" — never folded
  into Lia's own voice, and never extended by inference that isn't written
  there.
- Failures are surfaced plainly (spoken and/or printed in `[brackets]`), never
  silently swallowed — except logging, which must never be the reason a turn
  fails.
- Config comments are short essays with the reasons behind each constant. When
  you change a constant, update its comment.
- Windows-only APIs throughout (tray, PowerShell scripts); Python 3.12 is the
  tested version.
