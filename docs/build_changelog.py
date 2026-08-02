"""Builds 'Lia - What We Built.pdf'."""

from pathlib import Path

from make_pdfs import H1, H2, P, bullets, build, callout, code, table, Spacer, PageBreak

HERE = Path(__file__).parent

story = []
A = story.append

A(P("Lia is a companion AI that runs entirely on one laptop. No cloud APIs, no accounts, "
    "no data leaving the machine. This document records what she is made of, what changed "
    "while building her, and — just as importantly — what is measured rather than assumed."))

A(callout("<b>The constraint that shaped everything.</b> A 4&nbsp;GB graphics card. It decided the "
          "model size, the context window, where speech recognition runs, and why several "
          "obvious-looking improvements were rejected."))

# ---------------------------------------------------------------- overview ---
A(H1("What she is"))

A(table([
    ["Piece", "Choice", "Why"],
    ["Brain", "Ollama + llama3.2:3b", "Fits in 4&nbsp;GB VRAM"],
    ["Memory", "SQLite + nomic-embed-text", "Facts, past turns, documents"],
    ["Voice out", "Piper (en_US-amy-medium)", "Local neural speech, swappable"],
    ["Voice in", "faster-whisper small.en + Silero VAD", "CPU, so it never competes for VRAM"],
    ["Interface", "System tray app, no window", "Always there, never in the way"],
], [26, 62, 77]))

A(H2("The files"))
A(table([
    ["File", "Role"],
    ["config.py", "Every prompt and tunable. The first file to edit."],
    ["db.py", "SQLite schema: facts, memories, diary, documents"],
    ["llm.py", "Ollama wrapper — chat, streaming, embeddings, load/unload"],
    ["memory.py", "Embedding, retrieval, fact extraction and sanitising"],
    ["diary.py", "End-of-session reflection, and the startup greeting"],
    ["library.py", "Reads PDFs and notes you hand her"],
    ["voice.py", "Speech out, speech in, voice detection, wake word"],
    ["main.py", "The conversation loop and session lifecycle"],
    ["app.py", "Tray app wrapper for running her in the background"],
], [34, 131]))

A(P("The layering is strict: <b>config</b> knows nothing; <b>db</b> and <b>llm</b> are the only "
    "modules that touch the outside world; <b>memory</b>, <b>diary</b> and <b>library</b> hold the "
    "judgement calls; <b>voice</b> and <b>main</b> are the interface. A future GUI can reuse "
    "everything below <b>main</b> untouched."))

A(PageBreak())

# ----------------------------------------------------------- measurements ---
A(H1("What was measured"))
A(P("Every number here came from running the thing, not from estimating it. Several "
    "contradicted what seemed obvious."))

A(H2("Context window — the biggest single find"))
A(P("Ollama defaults llama3.2 to a 32k context. On a 4&nbsp;GB card that inflates the model past "
    "what fits, and it silently runs most of it on the CPU. Nothing errors. It just feels slow."))
A(table([
    ["num_ctx", "Model size", "On GPU", "Speed", "Full reply"],
    ["32768 (default)", "6.4 GB", "37%", "14.5 tok/s", "6.28s"],
    ["8192 (chosen)", "3.4 GB", "68%", "16.9 tok/s", "4.72s"],
    ["4096", "2.9 GB", "80%", "17.4 tok/s", "4.13s"],
], [32, 28, 22, 30, 53]))
A(P("8192 was chosen over 4096 to leave room for the system prompt, remembered facts, retrieved "
    "memories and eight turns of history without silently dropping the oldest ones."))

A(H2("Latency, start to first sound"))
A(table([
    ["Stage", "Time"],
    ["Embedding your words for recall", "2.1s"],
    ["Ollama to first token (warm)", "2.4s"],
    ["Piper to first audio", "~1s"],
    ["<b>Total, warm</b>", "<b>~5.5s</b>"],
    ["Cold start, models unloaded", "9.4s to first token"],
], [110, 55]))

A(H2("Speech recognition size"))
A(P("base.en heard <i>“My sister Ania”</i> where small.en heard <i>“My sister Anaya”</i>. Names matter "
    "for a companion, and the extra 1.3s is nothing against a multi-second reply, so small.en won."))

A(H2("Voice activity detection"))
A(code("speech chunks:   max prob 1.00,  47/55 over threshold\n"
       "silence chunks:  max prob 0.00,   0/31 over threshold"))

A(H2("Document indexing"))
A(P("A 37-page PDF became 91 passages in about four minutes — roughly 2s per passage, all of it "
    "embedding calls. Once per file, unless the file changes."))

A(PageBreak())

# ----------------------------------------------------------------- fixes ---
A(H1("Bugs found and fixed"))
A(P("Grouped by what they broke. Most were silent — nothing crashed, the behaviour was just "
    "quietly wrong, which is the harder kind to notice."))

A(H2("She looked frozen"))
A(bullets([
    "<b>No streaming.</b> Replies were fetched whole before printing, so 20–60s passed with a blank "
    "terminal. Now tokens stream, with <font face='Courier'>...remembering</font> / "
    "<font face='Courier'>...thinking</font> / <font face='Courier'>...saving</font> markers over the silent stretches.",
    "<b>Unicode crash.</b> llama3.2 emits em-dashes constantly; writing one to a non-UTF-8 Windows "
    "console raised mid-reply and killed the session. stdout is now pinned to UTF-8.",
]))

A(H2("Her memory was quietly corrupting itself"))
A(bullets([
    "<b>Junk facts overwrote good ones.</b> Fact extraction stored <font face='Courier'>name: \"you\"</font> "
    "and <font face='Courier'>favourite_food: \"None\"</font>, silently replacing real values. A deterministic "
    "sanitiser now rejects pronouns, placeholders, nested objects and over-long values.",
    "<b>Half her recall was her own voice.</b> Retrieval searched every stored turn including her own "
    "replies, so two of four recall slots returned things <i>she</i> had said — unlabelled, which she then "
    "read back as fact. This produced an invented emotional memory. Retrieval is now limited to your turns.",
    "<b>No sense of time.</b> Timestamps were stored and never used. Memories now arrive as "
    "<i>“yesterday, they said…”</i> instead of floating in an eternal present.",
    "<b>Renaming didn't stick.</b> A name change reverted because end-of-session extraction re-derived the "
    "old one from stored turns. Protected facts can no longer be overwritten by extraction.",
]))

A(H2("The diary was writing fiction"))
A(bullets([
    "<b>Role confusion.</b> Transcripts were labelled <font face='Courier'>user:</font> / "
    "<font face='Courier'>assistant:</font>, and a 3B model doesn't reliably map <i>assistant</i> to itself — "
    "so it narrated entries as though it were the human. Turns are now labelled <b>Them</b> and <b>Lia</b>.",
    "<b>Invented a childhood.</b> She wrote about her grandfather bringing dumplings to family gatherings. "
    "The diary prompt now states plainly that she has no past outside these conversations.",
    "<b>Nobody ever read it.</b> Entries were written and never loaded again. Her startup greeting is now "
    "generated from her recent diary, which is what makes it feel like continuity rather than a canned line.",
]))

A(H2("Voice-specific"))
A(bullets([
    "<b>Stage directions read aloud.</b> She emitted <font face='Courier'>*soft, gentle tone*</font> and Piper "
    "read the asterisks. Speech is now stripped of stage directions and markdown; the text output keeps them.",
    "<b>She greeted the dog.</b> In a flat list of facts, <font face='Courier'>pet_name: Biscuit</font> reads "
    "exactly like <font face='Courier'>name: Warlock</font>. The person is now named separately and explicitly.",
    "<b>Adding voices changed her voice.</b> <font face='Courier'>VOICE_NAME = \"auto\"</font> picked the first "
    "file alphabetically, so downloading a new one silently replaced her. Now pinned by name.",
]))

A(H2("The packaged app"))
A(bullets([
    "<b>Frozen paths.</b> Inside a bundle <font face='Courier'>__file__</font> points at a temp folder deleted "
    "on exit. Her database, voices and log now anchor to the executable's own directory.",
    "<b>She locked her own files.</b> The app launched <font face='Courier'>ollama serve</font> as a child, which "
    "inherited her folder as its working directory — Ollama's workers then held handles inside it and blocked "
    "every rebuild. It now starts from a neutral directory.",
    "<b>Half-written builds.</b> Rebuilding wiped the folder Windows autostart pointed at, producing "
    "<i>“Failed to import embedded python interpreter”</i>. Builds now go to a staging folder and swap in only "
    "when complete, so a failed build leaves the working app untouched.",
    "<b>Re-reading everything on every start.</b> Document paths were absolute, so the same PDF under "
    "<font face='Courier'>dist\\Lia\\library</font> looked like a different file and was re-embedded from scratch — "
    "four minutes before she would say a word. Paths are now relative to the library folder.",
]))

A(PageBreak())

# ------------------------------------------------------------ capabilities ---
A(H1("What was added"))

A(H2("Voice, both directions"))
A(P("Piper for speech, faster-whisper for listening, Silero VAD for knowing when you start and stop. "
    "Replies are chunked by sentence and spoken as they generate, so she starts talking before the "
    "full reply exists — essential when generation takes seconds."))
A(P("Your own voices drop into <font face='Courier'>voices/</font> as a matched "
    "<font face='Courier'>.onnx</font> + <font face='Courier'>.onnx.json</font> pair. Any engine exposing "
    "<font face='Courier'>.say(text)</font> and <font face='Courier'>.name</font> can be added alongside Piper."))

A(H2("Wake word, without a wake-word model"))
A(P("“Lia” isn't in any pretrained wake-word model, and training one needs a dataset. Since Whisper "
    "already transcribes everything, the name is matched <b>on the transcript</b> instead — no new "
    "dependency, no training, and it tolerates the spellings Whisper actually produces (Leah, Lea, Liya)."))
A(P("After she replies you get 60 seconds of free conversation; after her startup greeting, 30. The "
    "shorter greeting window exists because she greets the room at login whether or not anyone is there."))

A(H2("Interrupting her, on speakers"))
A(P("The mic stays open while she speaks. Since <b>she knows what she is currently saying</b>, anything "
    "heard is compared against her own words — her voice returning through the speakers is recognised and "
    "ignored, yours cuts her off. Clean on headphones; on speakers it depends on how clearly the mic "
    "picks her up."))
A(code("heard 'your grandmother Kamala taught you to cook'  -> her own voice, ignored\n"
       "heard 'wait stop'                                   -> you, cuts her off"))

A(H2("Spoken instructions"))
A(P("A small phrase list is matched before anything reaches the model, so “Lia, stop listening” switches "
    "the mic off instead of becoming something she muses about."))

A(H2("A library, on your terms"))
A(P("A single folder you hand her documents through. She never crawls your drive and never reads "
    "anything you haven't asked for — a file sitting there is available, not absorbed. Say “Lia, read my "
    "files” and she indexes it, then cites the document and page when answering."))
A(P("Document passages are kept separate from her memories and labelled as things she <i>read</i>, not "
    "things you <i>told her</i>. Blur those and she starts attributing a document's opinions to you.", "LiaNote"))

A(H2("Running as an app"))
A(P("A tray icon with no window, autostart at login, and a packaged executable that needs no Python "
    "installed. This only became possible once voice detection removed the need for a keyboard — a "
    "windowless app can't read one."))
A(P("She waits for Ollama on startup and launches it if needed, because at login she wins that race "
    "nearly every time."))

A(H2("Memory that follows the conversation"))
A(P("The keep-alive timer resets on every request, so its value never affects an active conversation — "
    "it only decides how long ~3.7&nbsp;GB of VRAM sits idle afterwards. She now releases the models "
    "explicitly when a conversation closes, and starts reloading the moment you begin speaking, so the "
    "load overlaps with transcription."))
A(table([
    ["", "Fixed 30m timer", "Now"],
    ["During a conversation", "loaded", "loaded"],
    ["5 minutes after", "held", "held"],
    ["15 minutes after", "held", "released"],
    ["Returning cold", "2.9s", "6.9s"],
], [55, 55, 55]))

A(PageBreak())

# ------------------------------------------------------------- limitations ---
A(H1("What she still can't do"))
A(P("Recorded honestly, because a companion that overstates itself is worse than one with known gaps."))

A(H2("Precise symbolic tasks — and teaching her doesn't help"))
A(P("Asked for Morse code from her own knowledge, she gave <font face='Courier'>S = \".-\"</font> (wrong) and "
    "<font face='Courier'>CAT = \".-\"</font> (wrong). Given a <b>perfect reference table in context</b> — taught "
    "exactly as you'd teach a person — she still produced <font face='Courier'>CAT = \".- ..- -\"</font>."))
A(callout("<b>She fails while looking at the answer.</b> This is not a memory problem, so no amount of "
          "teaching fixes it. A 3B model doesn't resolve individual characters well enough for "
          "character-by-character lookup. The right fix for tasks like this is code she can call, not "
          "knowledge she is given."))

A(H2("She still embroiders"))
A(P("Speaker-filtered retrieval removed the largest source of invented memories, but not all of it. "
    "She has produced lines like <i>“I was starting to think you'd forgotten about your favourite spot "
    "here”</i> about things that never happened. Better, not solved."))

A(H2("Open items"))
A(bullets([
    "<b>No way to forget.</b> Every turn is stored in plain text with no expiry and no <font face='Courier'>/forget</font>. "
    "This matters most now that she starts at login.",
    "<b>Duplicate facts.</b> Keys drift — <font face='Courier'>sister_name</font> and "
    "<font face='Courier'>visiting_sister_name</font> both existed for the same person. Nothing merges them.",
    "<b>Wake word still transcribes everything.</b> She only <i>responds</i> to her name, but she processes "
    "all audible speech to check for it. A true wake word would gate before transcription.",
    "<b>No tests.</b> Notable because every real bug so far has been silent — nothing crashed, the data just "
    "quietly got worse.",
    "<b>Whole-document questions.</b> She retrieves passages, not books. “Summarise this 300-page PDF” "
    "will not work; “what does it say about X” will.",
]))

A(H2("Scanned PDFs"))
A(P("There is no OCR. If text isn't selectable in a PDF viewer, there is nothing to extract."))

A(PageBreak())

# ------------------------------------------------------------------ config ---
A(H1("The dials"))
A(P("All in <font face='Courier'>config.py</font>. These are the ones worth knowing about."))

A(table([
    ["Setting", "Default", "Change it when"],
    ["NUM_CTX", "8192", "Never, without checking <font face='Courier'>ollama ps</font> for the CPU/GPU split"],
    ["OLLAMA_KEEP_ALIVE", "30m", "Now only a backstop — release happens on idle"],
    ["RELEASE_MODELS_WHEN_IDLE", "True", "You'd rather hold VRAM than reload"],
    ["PREWARM_ON_SPEECH", "True", "You want no speculative loading at all"],
    ["IDLE_MINUTES", "12", "Conversations should close sooner or later"],
    ["WAKE_WORD_ENABLED", "True", "You want her to answer everything she hears"],
    ["CONVERSATION_WINDOW_SECONDS", "60", "You repeat her name too often, or too rarely"],
    ["GREETING_WINDOW_SECONDS", "30", "She answers noise after login (lower it)"],
    ["VAD_SILENCE_SECONDS", "0.9", "She cuts you off mid-thought (raise it)"],
    ["VAD_THRESHOLD", "0.55", "Background noise triggers her (raise it)"],
    ["BARGE_IN", "True", "She interrupts herself on speakers"],
    ["ECHO_MATCH_RATIO", "0.5", "She ignores you while talking (raise it)"],
    ["WHISPER_MODEL", "small.en", "Names come out wrong (go bigger)"],
    ["VOICE_NAME", "en_US-amy-medium", "You want a different voice"],
    ["LIBRARY_AUTO_READ", "False", "You want documents read without asking"],
], [56, 34, 75]))

A(H2("Rebuilding the app"))
A(code("powershell -ExecutionPolicy Bypass -File LIA\\build_exe.ps1\n"
       "powershell -ExecutionPolicy Bypass -File LIA\\autostart.ps1 install -Exe\n"
       "powershell -ExecutionPolicy Bypass -File LIA\\autostart.ps1 remove"))

A(P("The build stages into a temporary folder and swaps at the end, so a failed build never leaves you "
    "without a working app.", "LiaNote"))


build(HERE / "Lia - What We Built.pdf",
      "Lia — What We Built",
      "A record of the project: architecture, measurements, fixes, and honest limits.",
      story)
