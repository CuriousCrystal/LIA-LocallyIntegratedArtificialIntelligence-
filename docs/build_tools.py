"""Builds 'Lia - Tools We Used.pdf' -- a study reference for the libraries and
software behind the project, written to teach the concept, not just name-drop it."""

from pathlib import Path

from make_pdfs import H1, H2, P, bullets, build, callout, code, table, PageBreak

HERE = Path(__file__).parent

story = []
A = story.append

A(P("Every tool used to build Lia, grouped the way the project itself is laid out. Each entry "
    "explains the general idea first — the thing worth actually learning — then how Lia specifically "
    "uses it. Skip the parts you already know; this is meant to be looked things up in, not read "
    "start to finish."))

# ------------------------------------------------------------------- brain ---
A(H1("The brain: local language models"))

A(H2("Ollama"))
A(P("A program that runs large language models on your own machine and serves them over a small "
    "local web API (HTTP, on <font face='Courier'>localhost:11434</font>) — the same shape of "
    "interface as a cloud AI provider, except nothing leaves the computer. It handles loading the "
    "model into GPU/CPU memory, managing context windows, and streaming tokens back as they "
    "generate."))
A(P("<b>In Lia:</b> every one of her replies is a request to Ollama's "
    "<font face='Courier'>/api/chat</font> endpoint. <font face='Courier'>llm.py</font> is the "
    "thin wrapper around that API — nothing in the rest of the project talks to Ollama directly."))

A(H2("llama3.2:3b"))
A(P("The actual language model — a neural network with about 3 billion parameters, published by "
    "Meta, small enough to run on a 4GB graphics card. “3B” refers to its size; smaller models are "
    "faster and use less memory but are worse at nuance, precision, and following long instructions "
    "than bigger ones (70B+, which need serious hardware or a cloud host)."))
A(P("<b>In Lia:</b> this is why some things she does badly — precise text manipulation like Morse "
    "code — are a hardware-driven ceiling, not a bug to fix. A bigger model would do better; it "
    "wouldn't fit on this machine."))

A(H2("nomic-embed-text"))
A(P("A much smaller neural network that doesn't generate text — it converts a sentence into a list "
    "of a few hundred numbers (a <i>vector</i>) that captures its meaning. Two sentences with "
    "similar meaning produce vectors that point in similar directions, which is what makes semantic "
    "search possible: compare vectors instead of exact words."))
A(P("<b>In Lia:</b> every message you've ever sent is embedded and stored. When you bring up a "
    "topic, her past turns are compared by vector similarity (<i>cosine similarity</i>, a dot "
    "product) to find what's actually relevant — not by keyword matching."))

A(PageBreak())

# ----------------------------------------------------------------- memory ---
A(H1("Memory: data and math"))

A(H2("NumPy"))
A(P("The foundational Python library for working with arrays of numbers efficiently. Plain Python "
    "lists are slow for math — NumPy stores numbers in tight, contiguous memory blocks (like C "
    "arrays) and does operations like addition, multiplication, and dot products on entire arrays "
    "at once, in compiled code, rather than one Python object at a time. This is the single most "
    "widely used library in scientific/data Python — worth learning well beyond this project."))
A(P("<b>In Lia, two distinct uses:</b>"))
A(bullets([
    "<b>Embeddings.</b> Each embedding is a NumPy array of ~768 floats. Comparing your message to "
    "everything she remembers means computing a cosine similarity — "
    "<font face='Courier'>dot(a, b) / (norm(a) * norm(b))</font> — against every stored vector, "
    "which NumPy does fast even over thousands of memories.",
    "<b>Audio.</b> A sound clip is just a NumPy array too — one number per sample, 16,000 or 22,050 "
    "or 24,000 of them per second depending on the model. Piper's output chunks, silence for the "
    "voice detector, and microphone input are all NumPy int16/float32 arrays underneath.",
]))

A(H2("SQLite"))
A(P("A complete relational database that lives in a single file on disk — no server process, no "
    "setup, just a file you can copy, back up, or inspect with any SQLite browser. Built into "
    "Python's standard library (<font face='Courier'>sqlite3</font>), so it needed no separate "
    "install. The right choice whenever a project needs structured, queryable storage but doesn't "
    "have (or want) a database server running."))
A(P("<b>In Lia:</b> <font face='Courier'>lia_memory.db</font> holds five tables — facts, "
    "memories (with embeddings stored as JSON text), diary entries, indexed document passages, and "
    "alarms. <font face='Courier'>db.py</font> is the only module that touches SQL directly."))

A(H2("requests"))
A(P("The standard, simple way to make HTTP calls from Python — GET and POST requests, JSON bodies, "
    "headers, timeouts. Almost every Python project that talks to any web API uses this library; "
    "it's worth knowing well as a baseline skill."))
A(P("<b>In Lia:</b> every network call in the whole project goes through <font face='Courier'>requests</font>. "
    "With the internet features switched off, the only thing left for it to talk to is Ollama on "
    "this same machine — the weather and lookup calls are still written, just never made."))

A(PageBreak())

# ------------------------------------------------------------------ voice ---
A(H1("Speaking"))

A(H2("Piper"))
A(P("An open-source neural text-to-speech engine, small enough to run on CPU in real time. It "
    "converts text into phonemes (speech sounds) using eSpeak NG under the hood, then a neural "
    "vocoder turns those phonemes into an audio waveform. Voices are distributed as "
    "<font face='Courier'>.onnx</font> files (the trained model) plus a <font face='Courier'>.onnx.json</font> "
    "config (sample rate, phoneme mapping)."))
A(P("<b>In Lia:</b> the default voice, “amy”, at 22,050Hz. <font face='Courier'>voice.py</font>'s "
    "<font face='Courier'>PiperEngine</font> wraps it, with tunable pacing/volume/expressiveness "
    "parameters (<font face='Courier'>SynthesisConfig</font>)."))

A(H2("ONNX / onnxruntime"))
A(P("ONNX (Open Neural Network Exchange) is a standard file format for trained neural networks, "
    "designed so a model trained in one framework (PyTorch, TensorFlow) can run in a lightweight, "
    "portable runtime without needing the whole training framework installed. "
    "<font face='Courier'>onnxruntime</font> is Microsoft's runtime that actually executes those "
    "files, on CPU or GPU."))
A(P("<b>In Lia:</b> both Piper and the voice-activity detector are ONNX models. This also produced "
    "the project's single biggest bug: onnxruntime's CPU backend defaults to a <i>spinning</i> "
    "thread pool that burns CPU continuously rather than sleeping between calls — fixed with one "
    "environment variable, <font face='Courier'>OMP_WAIT_POLICY=PASSIVE</font>, after it was found "
    "consuming ~290% of a CPU core while completely idle.", "LiaNote"))

A(H2("pyttsx3"))
A(P("A thin Python wrapper around whatever text-to-speech engine your operating system already "
    "has built in — SAPI on Windows, NSSpeechSynthesizer on macOS. Lower quality than a neural "
    "voice, but it needs no download and never fails to exist."))
A(P("<b>In Lia:</b> the fallback if Piper can't load for any reason — the built-in Windows voice "
    "(“Zira” by default), so she can never end up completely silent."))

A(PageBreak())

# ------------------------------------------------------------------ listen ---
A(H1("Listening"))

A(H2("faster-whisper"))
A(P("A reimplementation of OpenAI's Whisper speech-recognition model, built on CTranslate2 (below) "
    "for significantly faster inference than the original, especially on CPU. Whisper itself is a "
    "model trained on a huge amount of multilingual audio, which is why it's robust to accents and "
    "background noise without any per-user training."))
A(P("<b>In Lia:</b> runs the <font face='Courier'>small.en</font> size, deliberately on CPU so it "
    "never competes with Ollama for the 4GB of GPU memory the language model needs. Verified during "
    "development that <font face='Courier'>small.en</font> gets names right "
    "(“Anaya”) that the smaller <font face='Courier'>base.en</font> garbles "
    "(“Ania”)."))

A(H2("CTranslate2"))
A(P("A C++ inference engine specifically optimised for transformer models (the neural network "
    "architecture behind almost every modern language and translation model), with aggressive "
    "quantisation support — running a model at lower numeric precision (int8 instead of float32) to "
    "trade a small amount of accuracy for a large amount of speed and memory savings."))
A(P("<b>In Lia:</b> the actual engine underneath faster-whisper. Not called directly anywhere in "
    "the project's own code — it's a transitive dependency, but the reason transcription is fast "
    "enough to run on CPU at all."))

A(H2("Silero VAD (via pysilero-vad)"))
A(P("VAD stands for Voice Activity Detection: a small, fast model whose only job is deciding "
    "whether a short chunk of audio (here, 32 milliseconds) contains speech or silence — much "
    "cheaper than running full speech recognition on every chunk just to find out if anyone is "
    "talking."))
A(P("<b>In Lia:</b> this is what makes the open microphone possible at all — it decides when you "
    "start and stop talking, so a full recording only gets sent to Whisper once you're actually "
    "done speaking, with a 0.4-second pre-roll buffer so the first syllable isn't clipped."))

A(H2("sounddevice"))
A(P("A Python binding for PortAudio, a cross-platform C library for real-time audio input and "
    "output. It's the layer that actually talks to your sound card — opening a microphone stream, "
    "playing back a buffer of samples, choosing devices."))
A(P("<b>In Lia:</b> both directions — recording your voice for the VAD/Whisper pipeline, and "
    "playing back whatever Piper (or the fallback voice) synthesises."))

A(H2("soundfile and PyAV"))
A(P("An audio <i>file</i> is not audio <i>samples</i>: an mp3 is compressed, and something has to "
    "turn it back into the raw numbers a sound card can play. soundfile wraps libsndfile, the "
    "long-standing C library for exactly that; PyAV wraps FFmpeg, which handles far more formats "
    "but is a much heavier dependency."))
A(P("<b>In Lia:</b> both, for her music folder, tried in that order. libsndfile covers mp3, wav, "
    "flac, ogg and aiff, but has no AAC decoder — so an <font face='Courier'>.m4a</font> was listed "
    "as a numbered track and then refused to open. PyAV covers that one case, and was already "
    "installed as a faster-whisper dependency, so it cost nothing to fall back to.", "LiaNote"))

A(PageBreak())

# --------------------------------------------------------------------- app ---
A(H1("Running as an app"))

A(H2("pystray"))
A(P("A small cross-platform library for putting an icon in the system tray (the icons next to the "
    "clock) with a right-click menu — the minimum needed to have a program live in the background "
    "without a normal window."))
A(P("<b>In Lia:</b> the cat in the tray. Filled when listening, hollow when muted, with a menu for "
    "toggling voice/mic, ending the conversation, opening the log, and quitting cleanly. Runs on its "
    "own background thread now rather than owning the main one, to share the process with Tkinter — "
    "see below.", "LiaNote"))

A(H2("Pillow (PIL)"))
A(P("The standard Python library for opening, creating, and manipulating images — resizing, "
    "drawing shapes, reading pixel data. The name PIL (Python Imaging Library) predates Pillow, "
    "which is the actively maintained fork almost everyone actually installs today."))
A(P("<b>In Lia:</b> draws the tray icon itself — a small cat face, filled or hollow — generated in "
    "code (circles, triangles, a handful of lines) rather than loaded from an image file."))

A(H2("Tkinter"))
A(P("Python's own built-in GUI toolkit — ships with the standard library, needs nothing installed. "
    "Not the most modern-looking option available, but the narrowest one that does the job: a "
    "window, a text area, an entry line, and enough control over color and font to look "
    "deliberate rather than default."))
A(P("<b>In Lia:</b> the typed training panel (<font face='Courier'>panel.py</font>) — white "
    "background, warm orange accents, styled after Claude Code's own terminal. Runs on the process's "
    "main thread, which is the one hard requirement Tkinter actually has; pystray's tray icon moved "
    "to a background thread to make room for it.", "LiaNote"))

A(H2("pycaw"))
A(P("A Python wrapper over the Windows Core Audio APIs — the COM interfaces Windows itself uses for "
    "volume, mute state and per-application audio sessions. COM is Windows' older object model, "
    "which is why this arrives with <font face='Courier'>comtypes</font> in tow."))
A(P("<b>In Lia:</b> “turn it up”, “mute”, and being able to say what the volume actually is. "
    "Simulated media-key presses were tried first and verified to do nothing at all — a synthetic "
    "key needs a focused window to land on, and she hasn't got one. Talking to the audio endpoint "
    "directly was the only thing that worked.", "LiaNote"))

A(H2("sherpa-onnx"))
A(P("A speech toolkit that runs recognition, synthesis and speaker-embedding models through ONNX "
    "Runtime, with no PyTorch anywhere. A speaker embedding is the same idea as a text embedding: a "
    "voice becomes a vector, and two recordings of the same person land near each other."))
A(P("<b>In Lia:</b> voice recognition — comparing what she just heard against an enrolled voiceprint "
    "with cosine similarity, the same maths the library search uses on text. A soft comfort signal, "
    "not a lock: a mismatch makes her more careful, never refuses to talk."))

A(H2("PyInstaller"))
A(P("A tool that bundles a Python program, the interpreter itself, and every library it depends on "
    "into a single folder (or executable) that runs on a machine with no Python installed at all. "
    "It works by statically analysing imports and copying in everything reachable, plus special "
    "“hooks” for packages that need extra data files."))
A(P("<b>In Lia:</b> produces <font face='Courier'>Lia.exe</font>. The build script stages into a "
    "temporary folder and swaps it in only on success, specifically because a half-written build "
    "sitting where Windows autostart points caused a real, confusing failure "
    "(“Failed to import the embedded python interpreter”) during development.", "LiaNote"))

A(PageBreak())

# ------------------------------------------------------------------- other ---
A(H1("Documents, the internet, and these PDFs"))

A(H2("pypdf"))
A(P("A pure-Python library for reading and manipulating PDF files — extracting text, splitting or "
    "merging pages, reading metadata. PDFs don't store text the way a plain text file does (they "
    "store drawing instructions for where each character glyph goes), so “extracting text” is "
    "actually reconstructing it from that lower-level description, which is why extraction quality "
    "varies between PDFs and libraries."))
A(P("<b>In Lia:</b> reads any PDF dropped into her library folder, page by page, before the text "
    "is chunked and embedded for later retrieval."))

A(H2("ebooklib and BeautifulSoup"))
A(P("An <font face='Courier'>.epub</font> file is a zip archive of small HTML files, one roughly per "
    "chapter, plus a table of contents describing their order. ebooklib unpacks that structure and "
    "hands back each chapter's raw HTML; BeautifulSoup, a library built for parsing HTML and pulling "
    "text or specific elements out of it, then strips the markup down to the plain words underneath."))
A(P("<b>In Lia:</b> together they let the library folder accept whole novels, not just PDFs and "
    "text files — added after a real book (a Harry Potter novel) turned out not to work yet. Each "
    "chapter is treated the same way a PDF page is: extracted, then chunked and embedded on its own."))

A(callout("<b>OpenRouter is now how she thinks; the other two are still off.</b> The conversation "
          "goes to a hosted model, because model capability is the one thing a 4GB card cannot fix. "
          "Everything else stays local — speech, embeddings, the library, memory, and every "
          "classifier. Weather and “look that up” remain switched off "
          "(<font face='Courier'>INTERNET_ENABLED = False</font>) and are unrelated to that."))

A(H2("Groq"))
A(P("A company that hosts open language models (like Meta's Llama family, at sizes far bigger than "
    "what fits on a home GPU) on custom chips (LPUs) built specifically for fast inference — its "
    "whole selling point is speed, not necessarily the newest or most capable models available."))
A(P("<b>In Lia:</b> one of two optional providers for “look that up.” Fast, but a plain "
    "chat-completion call to it has no more access to today's news than the local model does "
    "either — it can only answer from what it learned during training."))

A(H2("OpenRouter"))
A(P("A single API that proxies requests to many different hosted models (OpenAI, Anthropic, "
    "Google, Meta, and others) behind one key and one request format, billed per-use. Notably, "
    "appending <font face='Courier'>:online</font> to a model name makes OpenRouter run an actual "
    "web search before answering — genuinely current information, not a guess from training data."))
A(P("<b>In Lia:</b> now the conversation itself. Only <font face='Courier'>chat_stream()</font> "
    "goes out — the judge, intent.py and fact extraction stay on the local 3B, because they run on "
    "every turn and billing them would multiply the spend for work a small model already does well."))
A(P("Streamed rather than fetched whole, for the same reason the local path is: she starts speaking "
    "her first sentence while the rest arrives. A model with a "
    "<font face='Courier'>:free</font> suffix is rate limited rather than billed, so a 429 and the "
    "occasional dropped connection are ordinary weather here — both fall back to the local model, "
    "and both are announced rather than passed off as normal.", "LiaNote"))
A(P("Worth recording, because it inverted an earlier conclusion: a whole spoken turn measures "
    "2.19s on the local 3B, 2.51s on paid gpt-4o-mini, and 4.53s on a free model. <b>Local is the "
    "fastest of the three.</b> The cloud buys capability, not speed — which only became true after "
    "the OLLAMA_URL fix cut local first-token from 2.42s to 0.73s.", "LiaNote"))
A(P("<b>A second, separate use:</b> “ask cat/fox” reaches two more named models through the "
    "same API and key, purely on request (see the Growth Log). This path doesn't stream and "
    "doesn't hide latency behind a first sentence the way the conversation does — she collects the "
    "whole reply before saying any of it — so what was measured for these two is <i>total</i> "
    "time, not time to first word, and each is capped at 15 seconds of wall-clock time regardless "
    "of what the provider does. Two other names were tried and dropped rather than kept: one free "
    "model measured well once and then failed empty five times in a row on a re-test, another was "
    "fast when it worked but wrong close to a third of the time overall — both cost real waits for "
    "nothing rather than just being slow.", "LiaNote"))

A(H2("Open-Meteo"))
A(P("A free weather API that needs no signup or key at all — just a latitude/longitude and it "
    "returns current conditions and a forecast as JSON."))
A(P("<b>In Lia:</b> answered “what's the weather” directly from live data, deliberately without "
    "routing it through any language model — there's nothing for a model to usefully add to a "
    "number that's already correct."))
A(P("Worth knowing if it's ever switched back on: the connectivity check in front of it probes "
    "<font face='Courier'>https://1.1.1.1</font>, and some ISPs hijack that address with a "
    "self-signed certificate. The weather call itself works fine; the check in front of it fails, "
    "and she concludes she's offline when she isn't.", "LiaNote"))

A(H2("ReportLab"))
A(P("A Python library for generating PDF files programmatically — laying out paragraphs, tables, "
    "and page templates in code rather than a WYSIWYG editor. Lower-level than most people expect: "
    "you build a list of “flowable” objects (paragraphs, tables, spacers) and it handles pagination."))
A(P("<b>In Lia:</b> what generated this document, and the four others alongside it — "
    "<font face='Courier'>docs/make_pdfs.py</font> holds the shared styling, and a small script per "
    "document builds the actual content. It is the one dependency here she never imports herself: "
    "it builds the docs, it isn't part of her."))

build(HERE / "Lia - Tools We Used.pdf",
      "Lia — Tools We Used",
      "A study reference for the libraries and software behind the project.",
      story)
