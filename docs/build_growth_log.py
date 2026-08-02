"""Builds 'Lia - Growth Log.pdf' -- a tracking document for the stages of her
growth, not a changelog of every fix. Meant to be added to as new stages happen."""

from pathlib import Path

from make_pdfs import H1, H2, P, bullets, build, callout, code, table, PageBreak

HERE = Path(__file__).parent

story = []
A = story.append

A(P("A record of Lia's growth in stages, not a log of every exchange or bug fix — those live in "
    "the Session Summary and Session Transcript. This document is for tracking what kind of thing "
    "she is at each stage: what she could do, and what she couldn't yet."))

A(callout("<b>The shape of it:</b> each stage she gained a new kind of relationship to the world — "
          "first just talking, then reading something you hand her, then perceiving and being "
          "perceived (voice), and now, starting to act on the world beyond just describing it."))

# ------------------------------------------------------------------ stage 1 ---
A(H1("Stage 1 — Making her"))
A(P("<b>What she gained:</b> existence. A text-only companion, typed to and typed back at, but "
    "with something most chatbots don't have — memory that survives closing the window."))
A(bullets([
    "A local brain: Ollama running <font face='Courier'>llama3.2:3b</font>, small enough for a "
    "4GB graphics card.",
    "Two-tier memory: a short-term rolling buffer for the live conversation, and a permanent "
    "SQLite database for facts and semantically searchable past turns "
    "(<font face='Courier'>nomic-embed-text</font> for the embeddings).",
    "A diary — a private reflection written at the end of each session.",
    "Six files: <font face='Courier'>config, db, llm, memory, diary, main</font>.",
]))
A(P("<b>What she couldn't do yet:</b> hear you, speak, read anything you hadn't typed directly "
    "into the conversation, or do anything beyond generating the next reply.", "LiaNote"))

A(PageBreak())

# ------------------------------------------------------------------ stage 2 ---
A(H1("Stage 2 — Controlling actions from a file explorer path"))
A(P("<b>What she gained:</b> her first action beyond conversation — reading something real, from "
    "a place on disk, on request."))
A(bullets([
    "A library folder (<font face='Courier'>LIA/library/</font>) you hand her documents through — "
    "PDFs, text, markdown.",
    "Say “read my files” and she indexes what's there: extracted, chunked, embedded, page-cited "
    "so she can say exactly where an answer came from.",
    "Deliberately on-demand, never automatic. She does not scan your drive, and a file sitting in "
    "the folder is <i>available</i> to her, not already read — a boundary kept even when it would "
    "have been easier to just read everything on startup.",
]))
A(P("<b>What she still couldn't do:</b> hear or speak a word, or touch anything outside that one "
    "folder.", "LiaNote"))

A(PageBreak())

# ------------------------------------------------------------------ stage 3 ---
A(H1("Stage 3 — Adding voices and ML models"))
A(P("<b>What she gained:</b> a body, in the only sense that matters for a companion — a voice, "
    "and ears. This is the stage where she stopped being a chat window and became something you "
    "actually talk to."))
A(bullets([
    "<b>Speaking:</b> Piper, a local neural text-to-speech engine, streamed sentence-by-sentence "
    "so she starts talking before the whole reply has even finished generating.",
    "<b>Listening:</b> faster-whisper for transcription, Silero VAD for detecting when you start "
    "and stop talking — together, an open microphone rather than push-to-talk.",
    "<b>A name to be called:</b> a wake word matched on the transcript itself, needing no trained "
    "model, tolerant of however her name actually gets misheard.",
    "<b>Presence without a window:</b> a system tray app, autostart at login, packaged as a "
    "standalone executable.",
    "A second voice engine (KittenTTS) was explored, got fully working, and was then removed by "
    "request — the seam for adding another one is still there in "
    "<font face='Courier'>voice.py</font> if it's ever wanted again.",
]))
A(P("<b>What she still couldn't do:</b> affect anything outside the conversation itself — no "
    "control over the machine she runs on, beyond her own voice and ears.", "LiaNote"))

A(PageBreak())

# ------------------------------------------------------------------ stage 4 ---
A(H1("Stage 4 — Controlling actions (in progress)"))
A(P("<b>What's changing:</b> the current frontier. Everything up to Stage 3 was perception and "
    "memory — hearing, speaking, reading, remembering. Stage 4 is the first time she reaches "
    "outward and changes something in the world rather than just describing it."))

A(H2("Built so far"))
A(bullets([
    "<b>Media control</b> — play, pause, skip whatever's already playing (Spotify, a browser tab, "
    "any app), via Windows' System Media Transport Controls. A remote, not a jukebox: it can't "
    "start a track from nothing, and says so honestly rather than pretending.",
    "<b>Volume control</b> — up, down, mute, unmute, via direct Core Audio access. (Simulating the "
    "physical volume keys was tried first and found to silently do nothing — fixed by talking to "
    "the audio API directly instead of imitating a keypress.)",
    "<b>Alarms and timers</b> — genuine ones, checked by a background watchdog every ten seconds "
    "and persisted across restarts, so “remind me in twenty minutes” survives even if the "
    "conversation, or the app itself, closes in the meantime.",
]))

A(H2("What she knows about herself"))
A(P("A real gap surfaced during this stage: she had no idea any of this existed. Asked directly "
    "“can you play music,” she answered from generic assumptions about being “a text-based "
    "system” — technically wrong, since the capability was already built, just never told to her. "
    "Fixed by adding an explicit, honest capability list to her own system prompt, so she reports "
    "what she can and can't do accurately instead of guessing."))

A(H2("Knowing who's asking: voice recognition"))
A(P("If actions are the risk this stage introduced, this is the safeguard for it. Say "
    "“Lia, it's Wade” a few times and she builds a voiceprint — a local model (3D-Speaker's "
    "CAM++, run through <font face='Courier'>sherpa-onnx</font>, no PyTorch) compares later speech "
    "against it. Where a clear mismatch doesn't grant a hard lock, it withholds the things that "
    "matter: she won't use your name, and won't share what she remembers about you."))
A(callout("<b>Honestly unverified:</b> real-world accuracy could only be tested against synthetic "
          "TTS voices from here, not an actual human voice on an actual microphone. The signal was "
          "confirmed real and correctly directioned, but likely <i>understates</i> true accuracy — "
          "synthetic speech probably lacks some of the natural acoustic texture the model was "
          "trained on. The match threshold is a documented starting point, not a calibrated answer, "
          "and <font face='Courier'>/whoami</font> exists specifically so it can be tuned against "
          "real use."))

A(H2("A harder gate: a spoken passcode"))
A(P("Voice recognition alone is a soft signal — useful, but not something to bet real access on "
    "given a laptop mic's reliability. So every session now opens locked: say the identity phrase "
    "within the first exchange, or she asks for a spoken passcode instead of acting on anything. "
    "Get it right and the session opens for good; get it wrong and she stops listening outright, "
    "recoverable only by hand (the tray menu, or typing it back on) — deliberately not "
    "recoverable by voice, since that would make the lock trivial to talk past."))
A(P("A second, separate passcode does something rather than unlocking anything: said at any time, "
    "unlocked or not, it has her read out and explain a specific reference document in her own "
    "words. Knowing the word is the point, the same as the first passcode.", "LiaNote"))
A(callout("<b>Two real bugs, found only by running it, not by reading the code:</b> the gate was "
          "checked before the “end the session” check, so once locked, saying goodbye "
          "got treated as a passcode guess instead of exiting — which combined with a second, "
          "unrelated bug (the keyboard reader spinning with no backoff once input ran out) into a "
          "genuine infinite loop, over 600,000 identical lines in under a minute. Separately, "
          "saying the identity phrase and a request in the same breath (“it's Wade, play some "
          "music”) silently dropped the identity phrase, because the request got rewritten into a "
          "command before the gate ever saw the original words. Both fixed and reverified live."))
A(P("The unlock passcode itself moved to an environment variable shortly after, the same reasoning "
    "as the API keys — a plaintext passcode in a file that might end up in a public repo isn't "
    "one. Left unset, the gate now disables itself with a one-time log line rather than locking "
    "anyone out with a word that could never be typed correctly.", "LiaNote"))

A(H2("Not yet built"))
A(bullets([
    "Opening or closing applications.",
    "Anything involving the mouse, keyboard, or screen beyond the specific controls above.",
    "Browsing the web or clicking anything on your behalf.",
    "Any action on Linux or macOS — everything in this stage is Windows-specific so far.",
]))
A(callout("<b>Where this goes next</b> is genuinely open. The pattern that's worked a few times now — "
          "find the narrowest real API for a specific capability (SMTC for media, Core Audio for "
          "volume, a local speaker-embedding model for identity) rather than reaching for something "
          "broad and risky — is the one to keep following as this stage grows."))

build(HERE / "Lia - Growth Log.pdf",
      "Lia — Growth Log",
      "The stages of her growth, kept for tracking what she can do at each one.",
      story)
