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
    "<b>Media control</b> — play, pause and skip over whatever another app already had loaded, "
    "via Windows' System Media Transport Controls. Later <i>removed</i> by request: it could only "
    "ever operate someone else's player and never start anything, which made it a confusing "
    "sibling to her own music folder, where she genuinely can.",
    "<b>Volume control</b> — up, down, mute, unmute, via direct Core Audio access. (Simulating the "
    "physical volume keys was tried first and found to silently do nothing — fixed by talking to "
    "the audio API directly instead of imitating a keypress.)",
    "<b>Alarms and timers</b> — genuine ones, checked by a background watchdog every ten seconds "
    "and persisted across restarts, so “remind me in twenty minutes” survives even if the "
    "conversation, or the app itself, closes in the meantime. Later widened to how people "
    "actually speak — spoken numbers, “half an hour”, “a couple of minutes”, “give me a nudge”, "
    "“buzz me” — and taught to say <i>the words you asked for</i>: “wake me by saying please wake "
    "up” wakes you with those words, not with “your timer is up”.",
]))

A(H2("What she knows about herself"))
A(P("A real gap surfaced during this stage: she had no idea any of this existed. Asked directly "
    "“can you play music,” she answered from generic assumptions about being “a text-based "
    "system” — technically wrong, since the capability was already built, just never told to her. "
    "Fixed by adding an explicit, honest capability list to her own system prompt, so she reports "
    "what she can and can't do accurately instead of guessing."))

A(H2("Reaching outside the machine: real lookups, and a fuller library"))
A(P("Two separate systems, both narrow and optional by design. <b>Internet access</b> — weather "
    "needs no key at all (Open-Meteo, geolocated from your IP); “look that up” checks a live source "
    "instead of guessing, via Groq or OpenRouter's actual web-search mode, whichever key is set. "
    "Naming a source works too — “search Reddit for…” — though one caveat came out of testing: "
    "search-operator syntax like <font face='Courier'>site:reddit.com</font> makes the underlying "
    "search decline entirely, where plain natural language works. A later pass found the natural "
    "phrasings people actually use for Reddit weren't all being caught — fixed by adding "
    "<font face='Courier'>\"reddit\"</font> itself as a trigger word, rather than requiring an exact "
    "phrase match. YouTube got the same trigger word shortly after, for the same reason — with the "
    "same honest limit either way: it's still a text search that happens to mention the site, not "
    "anything that can watch or listen to what's actually there."))
A(P("<b>The library</b> now reads <font face='Courier'>.epub</font> and "
    "<font face='Courier'>.docx</font> as well as PDF, text and markdown — epub added after a real "
    "book (a Harry Potter novel) got dropped in and turned out not to work yet. Even once indexed "
    "she retrieves passages, not the whole text: she can discuss a specific scene or character, "
    "not narrate a book start to finish.", "LiaNote"))
A(P("Indexing speed was finally <i>measured</i> rather than estimated, and the figure in the docs "
    "turned out to be wrong by about four and a half times — 2.3 seconds per passage, not the "
    "half-second long claimed, or roughly 130 pages per ten minutes. Notably it isn't starved of "
    "VRAM: freeing 3.5GB by unloading the chat model moved the rate by 0.02s, so there's no easy "
    "speed-up to chase. Since counting the passages up front costs only a fraction of a second, "
    "she now says what she's in for before starting — <i>“On it”</i>, or <i>“On it, that'll take "
    "around 25 minutes”</i> — instead of going quiet.", "LiaNote"))

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

A(H2("A harder gate: built, lived with, removed"))
A(P("For a stretch this stage also had a spoken passcode in front of it: every session opened "
    "locked, and without the identity phrase she asked for a word before acting on anything — "
    "wrong word and she stopped listening outright. It worked, and two genuine bugs got found and "
    "fixed inside it (saying “goodbye” while locked was read as a wrong guess instead of an exit; "
    "an identity phrase said in the same breath as a request was silently dropped). The passcode "
    "was later moved out of the source file into an environment variable, on the same reasoning "
    "as the API keys."))
A(callout("<b>Then it was removed, on the strength of actually living with it.</b> A lock that "
          "opens every conversation is a real cost paid on every single exchange, against a threat "
          "that doesn't exist on a personal laptop that's already password-protected. It made a "
          "companion feel like a checkpoint. Voice recognition stays as the soft signal it always "
          "was; the hard gate is gone. Worth recording as a stage that was built properly, "
          "evaluated honestly, and then undone — not everything that works is worth keeping."))

A(H2("Understanding, not just matching"))
A(P("Every action above was reached through a list of remembered phrasings, and that list was "
    "always going to be incomplete — people don't say “volume up”, they say “could you push that "
    "up a bit, it's hard to hear.” Anything unlisted fell through to ordinary conversation, where "
    "the model, with no idea an action had been wanted, produced a confident “sure, doing that "
    "now” and did nothing. <b>That failure is worse than refusing outright, because it looks like "
    "it worked</b> — and it's exactly what a week of real use kept running into."))
A(P("So a second layer went in behind the first: when no phrase matches, the model is shown the "
    "actions she can actually take and asked which one, if any, was meant. It decides from "
    "meaning rather than from remembered wordings. The phrase matcher stays in front of it — "
    "instant, free and completely predictable for the everyday cases — and the model is only "
    "consulted when the words could plausibly be about an action at all, so ordinary conversation "
    "never waits on it."))
A(callout("<b>Measured, not assumed:</b> 30 of 32 across repeated runs, including every "
          "“this is just conversation” case. Getting there took two failed attempts worth "
          "recording — stated as abstract rules, the model turned the volume up on “I couldn't "
          "hear you properly earlier” five times out of five, and ignored “I've added a book, go "
          "have a look” five out of five. Concrete examples of the distinction fixed both "
          "outright, where the rules hadn't. A model this size generalises from cases, not "
          "principles."))

A(H2("Deciding what she's allowed to do on her own"))
A(P("A run of changes with one thing in common: she stopped doing things unprompted."))
A(bullets([
    "<b>She waits to be spoken to.</b> No greeting at login — she starts when the computer does, "
    "which is rarely when anyone wants to talk. Greeting an empty room and then going quiet by "
    "the time you sat down was worse than silence.",
    "<b>She remembers only what she's told to.</b> “Remember that…” keeps something, word for "
    "word. Automatic fact extraction and the diary are both off.",
    "<b>Her own music.</b> Files in a <font face='Courier'>music/</font> folder, played by number "
    "through her own audio — the first time she can <i>start</i> something rather than only "
    "operating a remote over another app. She ducks it under her voice instead of stopping it.",
    "<b>Documents convert once.</b> Every format becomes plain text on first read, so nothing "
    "downstream knows or cares what it started as; re-reading is 25&times; faster.",
    "<b>Every interpretation is logged.</b> What was said, what she took it to mean, and whether "
    "the phrase list or the model decided — the raw material for a future fine-tune on real "
    "phrasings rather than invented ones.",
]))
A(callout("<b>The reason the memory changes happened at all</b> is worth recording, because it "
          "wasn't a preference. Testing her had been writing into her real memory for days: a "
          "dozen piped “hello”s became stored turns, and each test run ended with her writing a "
          "diary entry about a conversation that never happened. One of those reflected on the "
          "person “moving between unrelated topics” — read off a list of test commands. Invented "
          "history is indistinguishable from real history once it's in the database, and it "
          "shapes every reply afterwards. A <font face='Courier'>--no-save</font> flag now exists "
          "so testing leaves no trace, and the fabricated entries were deleted."))

A(H2("Hearing herself"))
A(P("Reported from real use as two vague complaints — “she had trouble reading” and “she keeps "
    "calling me out” — which turned out to share one cause, found by reading her actual stored "
    "memories rather than guessing. <b>She was recording her own voice as things Wade had "
    "said</b>, then quoting them back to him as his own words."))
A(bullets([
    "<b>Her own speech, heard back.</b> Echo detection only ran <i>while</i> she was talking, to "
    "make interrupting her work. The moment she finished, her spoken confirmation came back "
    "through the speakers and was stored as his turn — “There's nothing new to read, I've already "
    "read everything in there” sat in her memory as a line of his.",
    "<b>The speech recogniser's own prompt.</b> Whisper is given a short vocabulary hint so it "
    "spells names correctly; handed near-silence, it returns that prompt as the transcript. "
    "“This is a conversation with Lia” was stored as something he'd said, five separate times.",
]))
A(P("Both are filtered now, on every input path rather than just the interrupt one, and the "
    "contaminated memories were deleted. The name repetition was a separate, smaller thing: the "
    "system prompt asks her to use it sparingly, a 3B ignores that, so it's enforced in code "
    "instead — vocative uses after the first are stripped from what she says, while genuine "
    "mentions survive.", "LiaNote"))
A(callout("<b>Worth noticing about the diagnosis:</b> neither complaint described what was "
          "actually wrong. “Trouble reading” and “calling me out” both sounded like the model "
          "being poor, and both were a microphone hearing the wrong thing. Reading her real "
          "stored memories took a minute and pointed straight at it; reasoning about the "
          "symptoms would not have."))

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
