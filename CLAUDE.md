# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

LIA ("Lia") is a Windows-only desktop companion in Python 3.12, with a 3D
avatar you type or talk to through a chat panel (click her to open it;
always-on background listening is off by default). **Chat runs on a local
model through Ollama; speech-to-text is local faster-whisper.** Nothing about
a conversation leaves the machine — no API key, no hosted provider, no
network call. **Text-to-speech is local Piper** — the only TTS engine. Her
**memory is plain `.txt` files the user writes themselves** (Notepad or
anything else) in one folder, which `notes.py` reads **read-only**. There is
no database, no actions (no alarms, music, volume, library), and no speaker
recognition — all removed by design; don't reintroduce them without asking.
No build system beyond `pip`, no package layout — `LIA/` is a flat set of
modules run as scripts.

## Commands

Setup:
```
ollama pull phi3:mini                        # or LOCAL_CHAT_MODEL's default
pip install -r LIA/requirements.txt
# then drop .txt files into LIA/notes/ for her to remember -- or repoint
# NOTES_DIR in LIA/config.py at another folder
```
No API key needed. Model ids are config knobs in [config.py](LIA/config.py):
`LOCAL_CHAT_MODEL` (Ollama), `LOCAL_WHISPER_MODEL` (faster-whisper).

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
Ollama has to be installed, running, and have `LOCAL_CHAT_MODEL` pulled on
whatever machine runs the packaged exe too — packaging her doesn't bundle a
model runtime. `.github/workflows/release.yml` builds and publishes this
automatically on a `v*` tag push (GitHub's Windows runner, same build script).

Utilities:
```
python LIA\fallback_report.py [--days 30]   # how often the local model is unreachable
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
  `VRM_ENABLED` and a `.vrm` exists — starts `vrm.VrmMascot` (a transparent 3D
  avatar) on the main thread, alongside the chat panel on its own thread.
- `vrm.py` — the desktop avatar: a loopback HTTP server serves a vendored
  three.js + `@pixiv/three-vrm` viewer; pywebview shows it frameless,
  transparent, fixed in the screen's top-left corner (not always-on-top —
  other windows can cover her). States idle / listening / thinking / speaking
  from `app.py._avatar_state()` (same `Controls` reads as before); blink,
  breathing, sway and gaze wander are procedural; the mouth is driven by the
  loudness envelope `voice.set_audio_level_sink` publishes while Piper
  speaks. Drag to move within a session (position isn't remembered between
  runs), left-click opens the chat panel (`app.py.open_chat`), right-click
  menu. Drop any `.vrm` into `LIA/vrm/`; with none she runs tray-only and
  says so once.
- `Controls` (in `main.py`) is the object other threads use to pause/quit and
  to read loop state (`thinking`, `speaker`). `panel.Panel` and `Keyboard`
  share a `.pending()/.take()` interface so `read_input()` can't tell stdin
  from the GUI box. `panel.Panel` is her primary input surface now
  (`LISTEN_ENABLED` defaults off): a small, frameless, always-present window
  (its own header, since Windows' native title bar can't render a custom
  font), hidden until the avatar's clicked, with a text field and a mic
  button for one recorded question at a time — Tk() and its mainloop share
  one dedicated thread (`Panel.run()`), since Tcl requires both on the same
  thread and the avatar's pywebview loop already owns the main one.

### Per-turn flow
1. `read_input()` returns the next utterance — typed or mic-recorded through
   `panel.Panel` (the default now that `LISTEN_ENABLED` is off), or from
   `voice.Listener` (local VAD → local faster-whisper transcription) if
   always-on listening is turned back on. Voice input is gated by the wake
   word (`accept_spoken()`) either way. There is no echo filter or barge-in
   any more: she must finish speaking before the mic reopens
   (`MIC_SETTLE_SECONDS` exists for the speaker tail).
2. `as_instruction()` is a **deterministic ladder**: `/`-prefixed passthrough →
   `SPOKEN_COMMANDS` phrase match (`spoken_command()`) → `intent.route()` (the
   only LLM step, and only when `intent.might_be_action()` says the words could
   plausibly be a request).
3. Slash commands go to `handle_command()` (`/voice`, `/mic`, `/openmic`,
   `/wake`, `/notes`, `/help`). Everything else is conversation:
   `build_system_message()` (SYSTEM_PROMPT + live time + the notes block) plus
   recent history, then `llm.chat_stream()`.

### Her memory — `notes.py`
- Plain `.txt` files the user writes themselves (Notepad or anything else)
  in one folder (`NOTES_DIR` in config.py, default `LIA/notes/`).
  `notes.all_notes()` reads it with an mtime-based cache; every non-blank
  line of every file is one note, capped (`NOTES_MAX_NOTES`,
  `NOTES_MAX_CHARS`), and `as_context()` renders it as a labelled system
  block: *their words, the only memory there is, never invent beyond it*.
- **Strictly read-only.** She has no way to write a note and must not gain
  one without the user asking.
- A missing folder is a normal state (empty memory, reported once); an
  unreadable file is reported once and never blanks the rest of the memory.
- Nothing else in the app persists anything. There is no `db.py`; the
  conversation lives only in the `Session` context window and rolls over
  after `IDLE_MINUTES`.

### Models — `llm.py` is the only module that calls a model
- `chat()` / `chat_stream()` — `POST {OLLAMA_BASE_URL}/api/chat` (`chat_stream`
  streamed, newline-delimited JSON, not SSE). **No fallback**: on failure they
  raise `llm.CloudError` (named for the hosted-API era; still the shape every
  caller expects) and the caller in [main.py](LIA/main.py) says so plainly. A
  429 (rare — concurrent-request limits, if set) raises `RateLimited`.
  Failures logged to `cloud_fallback_log.jsonl` (kept for `fallback_report.py`).
- `transcribe(audio_i16, sample_rate, prompt)` — local faster-whisper
  (`LOCAL_WHISPER_MODEL`, loaded lazily on first use); returns `None` on
  failure. `prompt` maps to faster-whisper's `initial_prompt`.
- `have_key()` — asks Ollama's `/api/tags` whether `LOCAL_CHAT_MODEL` is
  actually pulled; with no model reachable she hears the mic but can't think.

### Configuration — `config.py`
Module-level constants: every prompt and tunable, each with a comment carrying
the reasoning. **Edit this first** for behavior/tone changes. The `LOCAL_*`
block near the top holds `OLLAMA_BASE_URL`, `LOCAL_CHAT_MODEL`,
`LOCAL_WHISPER_MODEL`, `LOCAL_WHISPER_COMPUTE_TYPE`, `LOCAL_TIMEOUT`. Other
behavior flags: `LISTEN_ENABLED` (off by default — the chat panel is
primary), `OPEN_MIC`, `WAKE_WORD_ENABLED`, `CONVERSATION_WINDOW_SECONDS` (0 =
name required every turn), `NOTES_DIR` / `NOTES_MAX_NOTES` /
`NOTES_MAX_CHARS`, `GREET_ON_START` + `STARTUP_GREETING` (static line; the
diary-generated greeting is gone), `VRM_ENABLED` / `VRM_DIR` / `VRM_SIZE` /
`VRM_FRAMING`, and `SYSTEM_PROMPT` — whose `WHAT YOU THINK` section is what
makes her give real opinions instead of fence-sitting, and whose `HOW YOU
TALK`/`HOW YOU FEEL` sections explicitly push back against a small local
model's habit of breaking character ("as an AI...") and writing long replies.

### Voice — `voice.py`
- `Speaker`: local **Piper** only (`PiperEngine`, `.onnx` files in `voices/`).
  There is no cloud engine and no SAPI fallback; if Piper can't load, she is
  silent and says why once. `SentenceBuffer` splits the streamed reply into
  speakable sentences so speech starts before the reply finishes generating.
- `Listener`: records the utterance (int16 mono 16 kHz), sends it through
  `llm.transcribe()` (local faster-whisper). `warm_up()` only loads
  `pysilero-vad` (open-mic turn detection); the whisper model itself loads
  lazily on first real transcription.

### Narrow classifiers (kept local and cheap on purpose)
- `intent.py` — names which action (if any) an unmatched utterance meant; the
  only actions left are mic/voice/wake switching and the notes commands, plus
  `just_talk`. Logs every decision to `intent_log.jsonl` as raw material for a
  future fine-tune.

### Packaging
- `build_exe.ps1` (PyInstaller) copies `voices/`, `vrm/`, `assets/` and
  `notes/` beside the built exe. `make_icon.py`'s `BASE_DIR` resolves via
  `sys.executable` when frozen (like `config.py`'s `BASE_DIR`/`DATA_DIR`) --
  `__file__` alone points inside PyInstaller's temporary unpack directory,
  which silently broke the tray/window icon and the chat panel's custom font
  in a packaged build until this was fixed.
- `.github/workflows/release.yml` runs the same `build_exe.ps1` on GitHub's
  `windows-latest` runner and publishes a zip as a GitHub Release on a `v*`
  tag push (or just builds, on any other push, to catch breakage early).

### Docs
`docs/*.pdf` are generated by `docs/build_*.py` with `reportlab`, which is
pip-installed separately and never imported by the app. **They describe the
older, bigger feature set** (library, music, alarms, speaker ID, a hosted
chat API) and have not been regenerated since the trim. Same caveat applies to
[LIA/models/README.md](LIA/models/README.md), which still documents a
`speaker_id.py` and speaker-embedding model that no longer exist in the repo.

## Conventions to match when editing

- Prefer deterministic parsing (regex, phrase lists) over asking a model; the
  model is a fallback, not the first resort. See the `as_instruction()` ladder.
- Never invent memory, history, or facts about the person. The notes are
  always presented as "their words, the only record there is" — never folded
  into Lia's own voice, and never extended by inference that isn't written
  there.
- Failures are surfaced plainly (spoken and/or printed in `[brackets]`), never
  silently swallowed — except logging, which must never be the reason a turn
  fails.
- Config comments are short essays with the reasons behind each constant. When
  you change a constant, update its comment.
- Windows-only APIs throughout (pycaw is gone with media.py; SAPI gone with
  the TTS fallback; tray and PowerShell scripts remain); Python 3.12 is the
  tested version.
- CPU-only inference is the assumed hardware (see the `no-graphics-card`
  branch name): a small (3-4B) local model is the deliberate ceiling, not an
  oversight — a bigger model measured 30-60s+ per reply here.
