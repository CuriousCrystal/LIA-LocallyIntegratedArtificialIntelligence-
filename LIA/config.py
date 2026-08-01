"""
Central config for LIA (Locally Integrated Artificial Intelligence).
Change MODEL_CHAT / MODEL_EMBED here if you swap models later.
"""

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
OLLAMA_KEEP_ALIVE = "30m"

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
    "/voice on": ["you can talk", "start talking", "unmute"],
    "/wake off": ["listen to everything"],
    "/wake on": ["only answer to your name"],
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
CONVERSATION_WINDOW_SECONDS = 60

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
