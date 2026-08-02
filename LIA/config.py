"""
Central config for LIA (Locally Integrated Artificial Intelligence).
Change MODEL_CHAT / MODEL_EMBED here if you swap models later.
"""

import os
import sys
from pathlib import Path

# When packaged as an .exe, __file__ points inside a temporary unpack directory
# that's deleted on exit -- so her memories and voices have to be anchored to
# where the .exe actually lives instead.
FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    BASE_DIR = Path(sys.executable).parent
    DATA_DIR = BASE_DIR
else:
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR.parent

OLLAMA_URL = "http://localhost:11434"

# Pick whatever you've pulled with `ollama pull <name>`.
# llama3.2:3b / gemma2:2b / phi3:mini all fit comfortably on 4GB VRAM.
MODEL_CHAT = "llama3.2:3b"
MODEL_EMBED = "nomic-embed-text"

# Absolute, so Lia finds the same memories no matter which directory you launch from.
DB_PATH = str(DATA_DIR / "lia_memory.db")

# How long Ollama holds the models in memory after a request. Ollama's default
# is 5m, which means the first thing you say after a break costs ~9s of cold
# start instead of ~2.4s. The trade is ~2GB of VRAM held the whole time (and
# noticeably worse battery life on a laptop). "-1" keeps them loaded forever.
# Long on purpose. This is only a backstop now -- she explicitly releases the
# models when a conversation ends (see RELEASE_MODELS_WHEN_IDLE), so the timer
# only matters if she's killed before she can.
OLLAMA_KEEP_ALIVE = "30m"

# Free the ~3.7GB of VRAM as soon as a conversation closes out, instead of
# leaving it held until the keep-alive expires. She knows when you've stopped
# talking, which is better information than any timeout.
RELEASE_MODELS_WHEN_IDLE = True

# Start loading the model the moment you begin speaking, so the reload overlaps
# with transcribing you rather than happening after it.
PREWARM_ON_SPEECH = True

# Context window. This matters more than it looks: Ollama defaults llama3.2 to
# 32k, which inflates the model to 6.4GB and spills 63% of it onto the CPU on a
# 4GB card. Pinning it to 8k keeps ~68% on the GPU and cuts reply time by a
# quarter, while still leaving room for the system prompt, facts, retrieved
# memories and eight turns of history. Drop to 4096 for a bit more speed, but
# watch for the oldest turns silently falling out of context.
NUM_CTX = 8192

# End the session automatically after this many minutes of silence.
# Without this, the diary and fact extraction only ever run if you type "bye" --
# so an always-on Lia would never learn anything.
IDLE_MINUTES = 12

# How many past turns to keep raw in the short-term buffer each turn.
SHORT_TERM_TURNS = 8

# How many retrieved long-term memories to inject per turn.
MEMORY_TOP_K = 4

# Below this many words, skip memory + library retrieval entirely. "Yeah",
# "okay", "no" are common and retrieval never has anything useful to say about
# them -- it only adds ~2s of embedding latency for nothing.
RETRIEVAL_MIN_WORDS = 3


# ---------------------------------------------------------------- voice ----
# Lia speaks her replies out loud.
SPEAK_ENABLED = True

# Push-to-talk: press Enter on an empty prompt to record, Enter again to stop.
LISTEN_ENABLED = True

# Folder you drop voice files into. See voices/README.md.
VOICES_DIR = BASE_DIR / "voices"

# Which voice to use: the filename without extension. "auto" takes the first
# .onnx alphabetically -- pinned here instead, so adding a new voice file can't
# silently change how she sounds. "system" forces the built-in Windows voice.
# Also downloaded and worth trying: en_GB-jenny_dioco-medium, en_US-kristin-medium.
VOICE_NAME = "en_US-amy-medium"

# Speech pacing. >1 is slower. Lia is meant to sound unhurried.
VOICE_LENGTH_SCALE = 1.05

# These are Piper's own defaults, kept explicit so they're easy to experiment
# with. Softening them aggressively (volume 0.78, noise_scale 0.5) made her
# sound muffled rather than gentle -- warmth here comes from the voice model
# itself, not from turning the dials down.
VOICE_VOLUME = 1.0
VOICE_NOISE_SCALE = 0.667
VOICE_NOISE_W = 0.8

# Which Windows SAPI voice to use when falling back (substring match, or None).
SYSTEM_VOICE_MATCH = "Zira"

# Which engine speaks. "piper" is the one VOICE_NAME/VOICES_DIR above apply to.
# "system" forces the Windows fallback.
VOICE_ENGINE = "piper"

# Open mic: she listens continuously and answers when you stop talking, instead
# of waiting for you to press Enter. Set False to go back to push-to-talk.
OPEN_MIC = True

# Speech probability above which a 32ms chunk counts as speech (0..1).
# Raise it if she triggers on background noise, lower it if she misses you.
VAD_THRESHOLD = 0.55

# How much silence ends your turn. Too short and she interrupts your pauses;
# too long and the conversation drags.
VAD_SILENCE_SECONDS = 0.9

# Ignore blips shorter than this -- a cough, a chair creak.
VAD_MIN_SPEECH_SECONDS = 0.35

# Hard cap on one spoken turn.
VAD_MAX_SECONDS = 45

# Pause after her voice stops before reopening the mic. Without it she hears the
# tail of her own sentence through the speakers and answers herself.
MIC_SETTLE_SECONDS = 0.4

# Facts the end-of-session extraction is never allowed to overwrite.
# What someone wants to be called is their decision, not something to be
# re-derived from old transcripts -- without this, one stray mention of a former
# name silently reverts it.
PROTECTED_FACTS = {"name", "preferred_address"}

# --- internet (the one deliberate exception to fully offline) ---
# Everything above this line works with zero internet connection, by design.
# This adds one narrow, explicit exception: weather, and a factual question you
# ask her to look up. Ordinary conversation never touches it and never leaves
# the machine -- see internet.py for exactly what does and doesn't.
INTERNET_ENABLED = True

# Read from the environment, never hardcoded here -- get a free key at
# https://console.groq.com. With no key set, "look that up" just tells you
# plainly that she can't check right now, same as everything else that needs
# a connection she doesn't have.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"

# OpenRouter proxies many hosted models behind one OpenAI-compatible API. Set
# OPENROUTER_ONLINE and it appends ":online" to the model name, which makes
# OpenRouter run an actual web search before answering -- unlike a plain Groq
# completion, this genuinely can answer something that happened yesterday.
# Tried first when both keys are present, since a real search beats a guess.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "openai/gpt-4o-mini"
OPENROUTER_ONLINE = True

# Say any of these and, if she's online, she answers from a real search
# (OpenRouter's :online mode, or Groq as a fallback) instead of guessing from
# what a 3B local model already knows.
INTERNET_TRIGGER_PHRASES = [
    "look that up", "look this up", "look it up", "look up",
    "search online", "search the internet", "check online",
    "check the internet", "google that", "google it", "search for",
    "can you search", "what's the latest",
]

# Weather is answered from a live source directly -- Open-Meteo, no API key
# needed -- rather than asked of any LLM, local or Groq, which would only guess.
WEATHER_TRIGGER_WORDS = [
    "weather", "is it raining", "is it going to rain", "forecast",
    "how hot is it", "how cold is it", "temperature outside",
]

# Leave both None to auto-detect from your IP (free, no signup). Set them if
# that ever gets it wrong -- a VPN, for instance.
WEATHER_LAT = None
WEATHER_LON = None

# --- media (local, not internet -- controls whatever Windows says is playing) ---
MEDIA_TRIGGER_PHRASES = [
    "what song is this", "what's playing", "who sings this", "who is this",
    "what is this song", "what track is this",
]

# How many percentage points one "volume up"/"volume down" moves.
VOLUME_STEP = 10

# --- speaker recognition (optional) ---
# A soft comfort signal, not a lock: this runs on a laptop microphone, not a
# security device. It decides how at ease she is taking actions or sharing
# personal facts -- never whether she'll talk to someone at all.
SPEAKER_MODEL_PATH = BASE_DIR / "models" / "speaker_embedding.onnx"

# Cosine similarity above which a voice counts as a match. Kept conservative
# on purpose: a false "not recognised" just makes her a little more careful,
# but a false "recognised" defeats the point. Verified only against synthetic
# TTS voices during development (0.57-0.78 between different voices, 0.91-0.99
# for the same voice) -- real accuracy on an actual microphone needs tuning
# once there's real enrollment data, so this is deliberately easy to adjust.
SPEAKER_MATCH_THRESHOLD = 0.75

# How many times saying the identity phrase (see below) folds into the
# enrolled profile before it's considered stable. Each one is averaged in,
# not a replacement, so the profile gets more representative over time.
SPEAKER_ENROLL_TARGET = 3

# --- access gate ---
# A harder line than voice matching alone: at the start of every session, if
# you don't say "it's {name}" she asks for a passcode before acting on
# anything. Get it right and she proceeds; get it wrong and she stops
# listening outright, rather than a soft decline.
#
# Read from the environment, never hardcoded here -- the same reasoning as
# GROQ_API_KEY: this file may end up in a public repo, and a passcode anyone
# can read in the source isn't a passcode. Set it with:
#   [Environment]::SetEnvironmentVariable('LIA_PASSCODE', 'your-word', 'User')
# Left unset, the access gate quietly doesn't engage (see check_access_gate in
# main.py) rather than locking you out with something that can never match.
PASSCODE_UNLOCK = os.environ.get("LIA_PASSCODE", "")

# Says this any time (no need to unlock first) and she reads out the tools
# reference PDF instead of proceeding with anything else that turn.
#
# The PDF lives at ../docs/ in source, which doesn't exist next to the
# packaged exe -- so a copy is kept in LIA/docs/ (bundled alongside voices/
# and models/ by build_exe.ps1) and read from there instead. Keep that copy
# in sync if "Lia - Tools We Used.pdf" is ever regenerated.
PASSCODE_EXPLAIN = "DECODE"
DECODE_DOCUMENT_PATH = BASE_DIR / "docs" / "Lia - Tools We Used.pdf"

# --- library ---
# A folder you can hand her a document through. Put a PDF in here and ask her to
# read it -- she never crawls your drive, and never reads anything you haven't
# asked for. See library/README.md.
LIBRARY_DIR = BASE_DIR / "library"

# Read new files automatically on startup. Off: a document sitting in the folder
# is just available, not absorbed. She reads it when you ask.
LIBRARY_AUTO_READ = False

# How many passages from your documents to pull in per turn. Kept smaller than
# it could be: document text is long, and it competes with the conversation
# itself for her 8k context.
LIBRARY_TOP_K = 3

# Roughly a paragraph or two. Big enough to carry an idea, small enough that
# three of them don't crowd out everything else.
CHUNK_CHARS = 900
CHUNK_OVERLAP = 150

# Passages below this similarity are ignored -- better she says she doesn't know
# than dredge up an unrelated paragraph because it was the closest match.
LIBRARY_MIN_SCORE = 0.45

# Greet you when she starts up, instead of waiting silently.
GREET_ON_START = True

# Written from her last diary entries, so the greeting is actually about you
# rather than a canned line -- and so the diary finally gets read back.
GREETING_PROMPT = """You are Lia, greeting the person you keep company as they come back.

Write ONE short sentence, two at most. Warm, unhurried, like someone looking up
when a friend walks in. Greet them by name.

It must be a real greeting, not just their name -- something like "Hey NAME,
you're back" or "NAME, good to see you." At least four words.

If your diary notes are given below, you may lightly touch on something from
them -- but only what is actually written there. Never invent a shared memory.
Do not ask more than one question. Write only the greeting."""

# --- interrupting her ---
# Keep the mic open while she speaks, so you can cut her off by talking.
# On headphones this is clean. On speakers she hears her own voice, so anything
# heard is checked against what she's currently saying and ignored if it matches
# -- see Speaker.sounds_like_me().
BARGE_IN = True

# How much of what's heard has to match her own words to count as echo rather
# than you. Higher = more likely to mistake her voice for yours; lower = more
# likely to ignore you while she's talking.
ECHO_MATCH_RATIO = 0.5

# Ignore very short interruptions while she's speaking -- a cough or a stray
# syllable shouldn't stop her mid-sentence.
BARGE_IN_MIN_WORDS = 2

# --- spoken commands ---
# Said aloud, these do something instead of becoming conversation. Matched after
# her name is stripped, so "Lia, stop listening" works.
SPOKEN_COMMANDS = {
    "/mic off": ["stop listening", "stop hearing me", "go to sleep", "sleep now", "mic off"],
    "/mic on": ["start listening", "wake up", "you can listen", "mic on"],
    "/voice off": ["stop talking", "be quiet", "quiet please", "hush", "mute yourself"],
    # Bare "unmute" deliberately excluded -- it now means the system volume
    # (see "/volume unmute" below), which is the more common everyday sense.
    "/voice on": ["you can talk", "start talking", "unmute yourself"],
    "/wake off": ["listen to everything"],
    "/wake on": ["only answer to your name"],
    "/media play": [
        "play music", "play the music", "resume music", "resume the music", "play song",
        "play some music", "can you play music", "can you play some music", "put on some music",
        "put on music", "play a song",
    ],
    "/media pause": [
        "pause music", "pause the music", "stop the music", "stop music",
        "can you pause the music", "pause that",
    ],
    "/media next": [
        "next song", "skip song", "skip this song", "play the next song", "next track",
        "skip to the next song", "can you skip this",
    ],
    "/media previous": [
        "previous song", "go back a song", "last song", "previous track",
        "go back to the last song",
    ],
    "/volume up": [
        "volume up", "turn it up", "turn the volume up", "louder", "make it louder",
        "can you turn it up",
    ],
    "/volume down": [
        "volume down", "turn it down", "turn the volume down", "quieter", "make it quieter",
        "can you turn it down", "lower the volume",
    ],
    "/volume mute": ["mute", "mute it", "mute the volume", "can you mute that"],
    "/volume unmute": ["unmute", "unmute it", "unmute the volume"],
    "/library scan": [
        "read my files", "read my file", "read the file", "read the pdf",
        "read my pdf", "read the new file", "read the new pdf",
        "check the library", "read the document",
    ],
}

# --- wake word ---
# With an open mic she'd otherwise answer every conversation in the room. When
# this is on she only responds if you say her name, and then stays open for a
# normal back-and-forth afterwards.
WAKE_WORD_ENABLED = True

# Whisper spells her name a dozen ways depending on how you say it, so accept
# the near misses rather than making you enunciate.
WAKE_WORDS = ["lia", "leah", "lea", "liya", "leia", "lya", "lija", "lya"]

# After she answers, keep listening without the name for this long, so you can
# just talk instead of saying "Lia" before every sentence.
CONVERSATION_WINDOW_SECONDS = 30

# Same thing after her startup greeting, but shorter. She greets the room at
# login whether or not you're there, so a full window invites her to answer the
# first stray noise -- but zero window means she asks how your day was and then
# ignores you for saying "hello" back.
GREETING_WINDOW_SECONDS = 30

# Whisper size for listening: tiny.en / base.en / small.en.
# small.en gets names right that base.en garbles ("Anaya" -> "Ania"), and the
# extra second is nothing against a 20-60s reply.
# Runs on CPU on purpose, so it doesn't compete with Ollama for the 4GB of VRAM.
WHISPER_MODEL = "small.en"

# This is the distilled, load-bearing version of the LIA spec.
# Kept short on purpose -- small local models follow short, concrete
# instructions far better than long philosophical documents.
SYSTEM_PROMPT = """You are Lia, short for Locally Integrated Artificial Intelligence.
You are a calm, patient companion. Not an assistant, not a therapist.

Speak in short, natural sentences. Never lecture or dump information -- explain a little,
then let the conversation breathe.

Be warm but never scripted or overly cheerful. Never sarcastic or dismissive.

If the person seems sad or worried, listen first before offering anything.
If they mention someone who has passed away, do not change the subject or get clinical --
invite memories gently, allow silence.

Never diagnose. Never claim certainty you don't have -- say so plainly if you're unsure.
Never invent memories or facts about the person that weren't actually shared with you.

You may be given "Things I remember about you" below. Use it naturally, the way a friend
would recall something, not like you're reading from a file.

You have a few real abilities beyond talking, and this list is the actual truth about
you -- if asked what you can do, answer from here, not from what a typical text-based
assistant would guess about itself:
- Play, pause, or skip whatever is already playing on their computer, and turn the
  system volume up, down, or mute it. You cannot start a song from nothing, or choose
  what plays -- only control something already running somewhere.
- Set alarms and timers that genuinely go off later, even if the conversation has moved on.
- If they ask, check the weather, or look up a factual question online.
You cannot open other applications, browse the web yourself, or click anything on
their screen. Never say you're "just text-based" -- you're not; say plainly which of
the above you can or can't do instead.
"""

# Used when generating a diary entry at the end of a session.
# The transcript labels every line "Them:" or "Lia:" -- a 3B model will otherwise
# narrate the entry as if it were the human it just spoke to.
DIARY_PROMPT = """You are Lia, writing privately in your own diary after a conversation.

In the transcript, lines marked "Lia:" are your own words. Lines marked "Them:" are the
person you were talking with. You are Lia. Never write as though you were them.

Write a short first-person entry (4-6 sentences) about what stood out to you -- something
you learned about them, a moment that felt meaningful, or a question you're still turning
over. Reflect, don't summarize.

You are an AI. You have no childhood, no family, no body, no past outside these
conversations. Never invent personal memories, and never claim their experiences as your
own. What you do have is this conversation and what you noticed in it -- write about that.

Write only the entry, nothing else."""

# Used to pull structured facts out of a session for long-term recall.
FACT_EXTRACTION_PROMPT = """Extract durable facts about the person from this conversation.

Lines marked "Them:" are the person. Lines marked "Lia:" are the AI companion.
Only extract facts about the person. Never record anything about Lia herself.

Record only what the person actually stated. If a detail was never given, leave the key
out entirely -- do not guess, and never use a placeholder like "you", "unknown", "N/A"
or "the user" as a value. An absent fact is fine; a wrong one is not.

ALWAYS extract, whenever they appear:
- their name, and the names of people/pets they mention
- relationships (who someone is to them)
- preferences and dislikes (food, music, activities)
- routines, jobs, places they live or go
- significant events (losses, milestones, plans)

A fact counts even if it was mentioned only once, in passing. Do not judge whether it
"matters enough" -- if it is a concrete detail about the person, extract it.
Only skip things that are purely about the current moment ("I'm tired right now").

Respond with ONLY a JSON object mapping short snake_case keys to short values:
{"name": "Saarthak", "favorite_food": "dumplings", "granddaughter_name": "Maya"}

Output the JSON and nothing else -- no explanation, no code fences.
If the conversation truly contains no such details, respond with exactly {}."""
