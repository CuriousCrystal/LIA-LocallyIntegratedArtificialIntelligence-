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

A(H2("Rebuilt from nothing, then deliberately narrowed"))
A(P("The laptop was reformatted. The project files survived on a second drive, but the machine "
    "underneath them didn't — no Python, no Ollama, not even git. Standing her back up from a bare "
    "Windows install turned out to be the most honest test the setup instructions have had, because "
    "nothing was already installed to paper over a gap."))
A(P("<b>Two gaps showed up immediately</b>, both invisible on a machine that already worked:"))
A(bullets([
    "<font face='Courier'>soundfile</font> was missing from the requirements file entirely, though "
    "<font face='Courier'>music.py</font> imports it. Anyone following the README got a Lia whose "
    "music failed the first time it was asked for.",
    "<font face='Courier'>.m4a</font> was advertised in three places — the code, and both READMEs — "
    "but libsndfile has no AAC decoder. She would list an m4a as a numbered track and then refuse "
    "to open it. Offering something and then declining it is worse than never offering it, so PyAV "
    "went in behind libsndfile as a fallback rather than the format being dropped.",
]))
A(P("<b>An alarm bug hid behind a cosmetic one.</b> “Remind me to take my tablets in half an hour” "
    "produced “Time to take my tablets in.” — a dangling preposition, and the sort of thing that "
    "looks like a wording nit. Chasing it found that the duration rules were checked shortest-first, "
    "so the general “an hour” rule matched inside “quarter of an hour” before the specific rule ran. "
    "<b>A fifteen-minute reminder was being set for sixty minutes</b>, silently, and had been all "
    "along. The visible flaw was cosmetic; the one underneath it wasn't."))
A(callout("<b>Worth recording as method:</b> the fix for the wording could have been to strip "
          "trailing prepositions, which would have made the symptom disappear and left the timing "
          "bug in place — and broken “remind me to log in in five minutes” into “Time to log.” "
          "along the way. Fixing the cause instead of the symptom found the real defect and "
          "protected the edge case. 16 phrasings now verified, including the ones designed to stay "
          "conversation."))
A(P("<b>Then she was narrowed on purpose</b>, which is the part worth tracking. Three capabilities "
    "that worked were switched off because they weren't wanted, not because they were broken:"))
A(bullets([
    "<b>Weather</b> — off. It needed no key and answered from live data, but it was the only reason "
    "she touched the network at all.",
    "<b>Online lookups</b> — off. Groq and OpenRouter both still wired up, both keyless and idle.",
    "<b>The stored conversation</b> — off. Every turn used to be embedded and searched later. She "
    "never invented those quotes, but surfacing a half-finished thought from weeks ago in a "
    "conversation it had nothing to do with reads the same way from the outside, and unlike the "
    "diary or the fact extractor, <i>this one got worse as the database grew</i>.",
]))
A(P("What was left at that point was a companion that talks, listens, reads what she's given, plays "
    "what she's given, sets alarms, and keeps exactly the notes she was asked to keep — making no "
    "network call whatsoever beyond Ollama on the same machine. <i>(That last part held until the "
    "stage below, where the thinking moved off the machine.)</i>"))
A(callout("<b>Each of these is a flag, not a deletion.</b> <font face='Courier'>INTERNET_ENABLED</font>, "
          "<font face='Courier'>WEATHER_ENABLED</font> and <font face='Courier'>REMEMBER_CONVERSATION</font> "
          "all restore the old behaviour on their own. The code was left intact deliberately: "
          "“we don't want this now” and “this was a mistake” are different conclusions, and only "
          "the second one justifies throwing the work away."))
A(P("One side effect, unplanned and welcome: with nothing stored to search and an empty library, "
    "the per-turn embedding call had nothing left to do, so it's now skipped entirely. Replies come "
    "back about two seconds sooner. Removing features made her faster, which is not usually how "
    "that goes.", "LiaNote"))

A(H2("The two seconds that were never the model"))
A(P("She was slow — around eight seconds from finishing a sentence to hearing one back — and the "
    "diagnosis looked obvious: a 3B model spilling a third of itself onto the CPU of a 4GB card. "
    "That reading led to a long, sensible conversation about cloud models and what they would buy."))
A(P("<b>It was wrong.</b> Measuring where the time actually went, rather than where it obviously "
    "should have gone, found that a request to a 0.5B model cost the same as one to the 3B: about "
    "2.4 seconds either way. Model size changed nothing, prompt length changed nothing, context "
    "size changed nothing. That is not what inference looks like."))
A(callout("<font face='Courier'>OLLAMA_URL</font> was "
          "<font face='Courier'>http://localhost:11434</font>. Ollama binds to 127.0.0.1, and "
          "resolving “localhost” on Windows offers ::1 first — nothing is listening there, and the "
          "failed IPv6 attempt cost about two seconds before falling back. Measured on the same "
          "request: <b>localhost 2.38s, 127.0.0.1 0.35s.</b> It was being paid by every chat, every "
          "embedding, and every passage of every document indexed."))
A(bullets([
    "A spoken turn went from <b>7.89s to 1.83s</b>.",
    "Embedding a turn went from 2.13s to 0.11s.",
    "The novel that took 42 minutes to index would now take about five.",
    "It never showed up as a fault because a reused HTTP session hides it entirely — it only bites "
    "the one-shot requests the whole app is made of.",
]))
A(P("<b>What it invalidated is the useful part.</b> The case for moving embeddings to a cloud API "
    "rested on a 2.1s local cost that was almost entirely this. The case for a cloud chat model "
    "rested on a 2.4s first token that was mostly this. Both arguments were built on a measurement "
    "that was real, repeatable, and measuring the wrong thing.", "LiaNote"))

A(H2("A specialist, built and then thrown away"))
A(P("The idea was several small models rather than one: a tiny classifier answering “is this "
    "question about a document?” in front of the library search, because a similarity floor "
    "provably could not — a genuine question scored 0.519 and ordinary small talk 0.583, so the two "
    "populations overlap and no threshold separates them. A novel is <i>about</i> sleeping and "
    "eating and families; small talk genuinely resembles it."))
A(P("The judge worked. The 0.5B model chosen to run it did not: 24 of 36 against the 3B's 35 of 36, "
    "and it failed in the worse direction, dropping real questions about the book. It existed only "
    "to dodge latency that turned out to be the hostname above. Once a request cost 0.35s rather "
    "than 2.4s, the premise was gone, and the model was deleted rather than kept as dead weight on "
    "a 4GB card."))
A(callout("<b>The pattern survived; the implementation didn't.</b> Gating retrieval on one closed "
          "question took everyday conversation from leaking the novel 7 times out of 7 to 0, with "
          "every real question still answerable. That is the same shape intent.py already proved. "
          "What failed was the assumption underneath it — that a narrow job needs a small model — "
          "and that assumption was only ever holding up a latency bug."))

A(H2("Thinking somewhere else"))
A(P("With the wiring fixed, what remained was the ceiling itself, and no amount of tuning reaches "
    "past a 3B. So the conversation now goes to a hosted model and everything else stays here: "
    "speech, embeddings, the library, memory, and every classifier. That last part is most of the "
    "cost control — the judge runs on every single turn."))
A(P("The measurement that matters is the one that inverted the reasoning that led here:"))
A(bullets([
    "local llama3.2:3b — <b>2.19s</b> a turn, free, offline, least capable",
    "paid gpt-4o-mini — 2.51s, about $0.0001 a turn",
    "a free model — 4.53s, no cost, rate limited",
]))
A(P("<b>Local is the fastest of the three.</b> The cloud is a quality trade and nothing else, which "
    "was not true that morning and is entirely because of the two seconds above."))
A(callout("<b>And the promise had to change with it.</b> The guide told people, in plain language, "
          "that nothing they said ever left the computer. That is no longer true — the words of the "
          "conversation go to a hosted model, though the audio, the memory and the documents do "
          "not. A privacy claim that quietly stops being true is worse than never having made it, "
          "so the guide now sets out what leaves and what stays, in a table, rather than "
          "reassuring anyone."))

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
