import ctypes
import datetime as dt
import os
from pathlib import Path

# Measured: the VAD model (via onnxruntime's OpenMP backend) defaults to a
# spinning thread pool that burns CPU waiting for the next chunk instead of
# sleeping between them -- 389% of one core, continuously, just from Lia
# sitting there listening to silence. PASSIVE drops that to ~94% with no
# measurable effect on real-time detection (32ms chunks only need ~31
# calls/sec; even passive-waited throughput is far above that). Must be set
# before onnxruntime/ctranslate2 initialize, so this runs before any other
# import in the whole process.
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")

import queue
import re
import sys
import threading
import time
import uuid

# llama3.2 is fond of em-dashes and ellipses. On Windows, writing those to a
# non-UTF-8 stdout raises mid-reply and kills the session, so pin it to UTF-8.
for _stream in (sys.stdout, sys.stderr):
    # getattr rather than a direct call: sys.stdout is typed as TextIO, which
    # has no reconfigure(), and it really is absent when output is redirected.
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

import requests

import alarms
import db
import diary
import internet
import library
import llm
import media
import memory
import speaker_id
import voice
from config import (
    SYSTEM_PROMPT,
    SHORT_TERM_TURNS,
    SPEAK_ENABLED,
    LISTEN_ENABLED,
    IDLE_MINUTES,
    OPEN_MIC,
    MIC_SETTLE_SECONDS,
    WAKE_WORD_ENABLED,
    WAKE_WORDS,
    CONVERSATION_WINDOW_SECONDS,
    GREETING_WINDOW_SECONDS,
    GREET_ON_START,
    LIBRARY_DIR,
    LIBRARY_AUTO_READ,
    BARGE_IN,
    ECHO_MATCH_RATIO,
    BARGE_IN_MIN_WORDS,
    SPOKEN_COMMANDS,
    RELEASE_MODELS_WHEN_IDLE,
    PREWARM_ON_SPEECH,
    RETRIEVAL_MIN_WORDS,
    WEATHER_TRIGGER_WORDS,
    INTERNET_TRIGGER_PHRASES,
    MEDIA_TRIGGER_PHRASES,
    VOLUME_STEP,
    SPEAKER_ENROLL_TARGET,
    PASSCODE_UNLOCK,
    PASSCODE_EXPLAIN,
    DECODE_DOCUMENT_PATH,
)

HELP = """
  /voice on|off   speak replies out loud
  /mic on|off     listen to you at all
  /openmic on|off open mic (just talk) vs push-to-talk (Enter to record)
  /wake on|off    only answer when you say her name
  /media play|pause|next|previous   control whatever's playing on Windows
  /volume up|down|mute|unmute       adjust the system volume
  /whoami [forget]                  voice-recognition status, or clear enrollment
  /alarms [cancel]                  list pending alarms/timers, or clear them
  /library [scan] what she has read; 'scan' picks up new files
  /voices         list voices found in LIA/voices/
  /help           this list
  bye             end the session
"""

# Kept in sync by read_input() so the idle watchdog can redraw the prompt after
# printing over it from its own thread.
PROMPT_HINT = "You: "


def status(text: str):
    """Transient one-line indicator, overwritten in place."""
    print(f"  ...{text}".ljust(40), end="\r", flush=True)


def clear_status():
    print(" " * 40, end="\r", flush=True)


def build_system_message(state: dict | None = None) -> dict:
    facts = db.get_all_facts()
    content = SYSTEM_PROMPT

    # False (not None) means a voice sample was actually compared and didn't
    # match -- only that specific, confirmed case withholds anything. None
    # (typed input, not yet enrolled, or no signal either way) stays open,
    # since "can't tell" must never be treated the same as "confirmed someone
    # else."
    voice_match = state.get("voice_match") if state else None

    if voice_match is False:
        # The facts/name block below is never reached in this branch -- not
        # "included but told to withhold," genuinely left out of context, so
        # there's nothing for the model to leak even by accident.
        content += (
            "\n\nSomething to be a little careful about right now: the voice talking to you "
            "doesn't match the person you know. It may still be them -- a rough mic day, "
            "background noise -- so don't refuse to talk or act suspicious, and don't mention "
            "that anything seems off. Just don't use their name, and don't volunteer anything "
            "personal about them unless they bring it up themselves first."
        )
        return {"role": "system", "content": content}

    # Stated separately and first. Buried in a list of facts it reads as trivia,
    # and she'll happily pick up an older name from a retrieved memory instead.
    name = facts.get("name")
    if name:
        content += (
            f"\n\nThe person you are talking with is called {name}. You may use their name "
            f"occasionally, the way a friend does -- at the start of a conversation, or to land "
            f"something important. Most replies should just say \"you\", the way people actually "
            f"talk; using their name in every single reply reads as stiff and repetitive, not warm."
            f" If anything in your memories or notes uses a different name for them, it is out"
            f" of date -- they are {name} now."
        )

    others = {k: v for k, v in facts.items() if k != "name"}
    if others:
        fact_lines = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in others.items())
        content += f"\n\nThings I remember about you:\n{fact_lines}"

    return {"role": "system", "content": content}


def build_memory_context(user_input: str, query_vec=None) -> dict | None:
    relevant = memory.retrieve_relevant(user_input, query_vec=query_vec)
    if not relevant:
        return None

    joined = "\n".join(f'- {when}, they said: "{content}"' for content, when in relevant)
    return {
        "role": "system",
        "content": (
            "Things this person has told you before, with when they said it:\n"
            f"{joined}\n\n"
            "These are their words, not yours. Treat them as the only record of the "
            "past you have -- do not invent anything else that was said or felt."
        ),
    }


def build_media_context(user_input: str) -> dict | None:
    """What's currently playing, if they asked -- entirely local, no network."""
    if not media.available():
        return None
    lowered = user_input.lower()
    if not any(p in lowered for p in MEDIA_TRIGGER_PHRASES):
        return None

    info = media.now_playing()
    if not info or not (info["title"] or info["artist"]):
        return {
            "role": "system",
            "content": "They just asked what's playing, but nothing seems to be playing right "
                       "now. Say so naturally.",
        }
    return {
        "role": "system",
        "content": f"Currently playing on their computer: \"{info['title']}\" by "
                   f"{info['artist'] or 'an unknown artist'}. Answer naturally, as though you "
                   f"noticed it yourself.",
    }


def build_internet_context(user_input: str) -> dict | None:
    """Weather or a looked-up answer, if the input asks for one and she's online.

    Kept as a system note she phrases in her own words, same as the library --
    she's told plainly where it came from and not to pretend it's her own
    knowledge or something you told her.
    """
    lowered = user_input.lower()

    if any(w in lowered for w in WEATHER_TRIGGER_WORDS):
        if not internet.is_online():
            return {
                "role": "system",
                "content": "They just asked about the weather. You have no internet connection "
                           "right now -- say so plainly and naturally, don't guess at an answer.",
            }
        report = internet.get_weather()
        if report is None:
            return {
                "role": "system",
                "content": "They just asked about the weather. The weather service didn't "
                           "respond -- say you couldn't check just now, don't guess.",
            }
        return {
            "role": "system",
            "content": f"Live weather right now: {report}. This is current, from a weather "
                       f"service, not something you already knew -- answer naturally, as "
                       f"though you just glanced outside for them.",
        }

    if any(p in lowered for p in INTERNET_TRIGGER_PHRASES):
        if not internet.is_online():
            return {
                "role": "system",
                "content": "They asked you to look something up, but you have no internet "
                           "connection right now. Say so plainly rather than guessing or "
                           "pretending to have checked.",
            }
        found = internet.look_up(user_input)
        if found is None:
            return {
                "role": "system",
                "content": "They asked you to look something up, but the lookup didn't work "
                           "(no key set, or the request failed). Say you couldn't check "
                           "rather than guessing.",
            }
        answer, was_live_search = found
        source = "a live web search just now" if was_live_search else "a quick online question just now"
        return {
            "role": "system",
            "content": f"You looked this up online and found: {answer}\n\nThis came from {source}, "
                       f"not from memory or something they told you -- say so if it's relevant, "
                       f"and answer naturally in your own voice.",
        }

    return None


def build_library_context(user_input: str, query_vec=None) -> dict | None:
    """Passages from your documents that bear on what you just asked."""
    try:
        found = library.search(user_input, query_vec=query_vec)
    except requests.RequestException:
        return None
    if not found:
        return None

    passages = []
    for title, page, text in found:
        where = f"{title}, page {page}" if page else title
        passages.append(f"[{where}]\n{text}")

    return {
        "role": "system",
        "content": (
            "Passages from documents in your library that may be relevant:\n\n"
            + "\n\n".join(passages)
            + "\n\nThis is something you read, not something they told you. Say which "
            "document a fact came from. If these passages don't actually answer the "
            "question, say you couldn't find it rather than guessing."
        ),
    }


def sync_library(announce: bool = True, quiet: bool = False) -> tuple[int, int]:
    """Index anything new in the library folder."""
    waiting = library.pending()
    if not waiting:
        return 0, 0

    if announce:
        names = ", ".join(p.name for p in waiting[:3])
        more = f" (+{len(waiting) - 3} more)" if len(waiting) > 3 else ""
        print(f"[reading {names}{more} -- this takes a moment]")

    def progress(count):
        if not quiet:
            status(f"reading, {count} passages so far")

    files_done, chunks = library.sync(on_progress=progress)
    if not quiet:
        clear_status()
    if announce and chunks:
        print(f"[read {files_done} file(s), {chunks} passages]")
    return files_done, chunks


def start_library_sync():
    """Index new documents in the background.

    A long PDF takes minutes to embed. Doing that before she'll say a word makes
    her look broken on every restart, which is exactly how it looked.
    """
    waiting = library.pending()
    if not waiting:
        return

    names = ", ".join(p.name for p in waiting[:2])
    print(f"[reading {names} in the background -- she's available meanwhile]")

    def run():
        try:
            files_done, chunks = sync_library(announce=False, quiet=True)
            if chunks:
                print(f"\n[finished reading {files_done} file(s), {chunks} passages]")
        except requests.RequestException:
            print("\n[couldn't reach Ollama to read the library -- try /library scan later]")

    threading.Thread(target=run, daemon=True).start()


# Commands that actually change something in the world, as opposed to just
# reporting status (bare "/media" or "/volume" with no arg) -- only these are
# gated on voice confidence, per (command, arg).
_GATED_ACTIONS = {
    ("/media", "play"), ("/media", "pause"), ("/media", "next"), ("/media", "previous"),
    ("/volume", "up"), ("/volume", "down"), ("/volume", "mute"), ("/volume", "unmute"),
}


def handle_command(cmd: str, speaker: voice.Speaker, state: dict) -> bool:
    """Returns True if the input was a command and has been handled."""
    parts = cmd.lower().split()
    if not parts or not parts[0].startswith("/"):
        return False

    name, arg = parts[0], (parts[1] if len(parts) > 1 else "")

    # Only an explicit False (a voice sample was actually compared and didn't
    # match) holds this back -- None (typed, unenrolled, no signal) goes
    # through as before. Declines rather than silently ignoring, so it's
    # obvious this isn't a bug if you ever hear it.
    if (name, arg) in _GATED_ACTIONS and state.get("voice_match") is False:
        print("[not doing that -- this doesn't sound like the voice I know]\n")
        speaker.say("That doesn't sound like you, so I'll hold off for now.")
        return True

    if name == "/voice":
        speaker.enabled = arg != "off"
        if speaker.enabled:
            speaker.preload()
            print(f"[speaking with: {speaker.voice_name}]\n")
        else:
            speaker.drop_pending()
            print("[voice off]\n")

    elif name == "/mic":
        state["listening"] = arg != "off"
        print(f"[mic {'on -- press Enter on an empty line to record' if state['listening'] else 'off'}]\n")

    elif name == "/openmic":
        state["open_mic"] = arg != "off"
        if state["open_mic"]:
            print("[open mic -- just talk, she answers when you stop]\n")
        else:
            print("[push-to-talk -- Enter on an empty line to record]\n")

    elif name == "/wake":
        state["wake_word"] = arg != "off"
        if state["wake_word"]:
            print(f"[say \"Lia\" to get her attention -- then {CONVERSATION_WINDOW_SECONDS}s of free conversation]\n")
        else:
            print("[wake word off -- she answers anything she hears]\n")

    elif name == "/whoami":
        if arg == "forget":
            speaker_id.forget_profile()
            print("[voice profile cleared -- say \"it's Wade\" a few times to re-enroll]\n")
        elif not speaker_id.available():
            print("[voice recognition isn't available -- see LIA/speaker_id.py]\n")
        elif not speaker_id.is_enrolled():
            print("[no voice enrolled yet -- say \"Lia, it's Wade\" a few times]\n")
        else:
            progress = speaker_id.enrollment_progress()
            score = state.get("voice_score")
            score_text = f"{score:.2f}" if score is not None else "n/a this turn"
            print(f"[voice profile: {progress} sample(s) folded in, "
                  f"threshold={speaker_id.SPEAKER_MATCH_THRESHOLD}, last score={score_text}]")
            print("  \"/whoami forget\" clears the profile and starts over\n")

    elif name == "/alarms":
        if arg == "cancel":
            n = db.cancel_all_alarms()
            print(f"[cancelled {n} alarm(s)]\n" if n else "[nothing to cancel]\n")
        else:
            pending = db.pending_alarms()
            if not pending:
                print("[no alarms set -- try \"set an alarm for 7am\" or \"remind me in 20 minutes\"]\n")
            else:
                print("[pending alarms]")
                for row in pending:
                    when = dt.datetime.fromisoformat(row["fire_at"]).strftime("%a %I:%M %p").lstrip("0").replace(" 0", " ")
                    print(f"  - {row['label']} at {when}")
                print("  \"/alarms cancel\" clears all of them\n")

    elif name == "/media":
        # Spoken feedback too, not just text -- a failed "play music" said out
        # loud needs to be heard, not just logged, or it looks like nothing
        # happened at all.
        def respond(ok: str, fail: str):
            print(f"[{ok if outcome else fail}]\n")
            speaker.say(ok if outcome else fail)

        if not media.available():
            print("[media control isn't available -- see LIA/media.py]\n")
        elif arg == "play":
            outcome = media.play()
            respond("playing", "There's nothing loaded anywhere for me to play -- "
                                "open something in Spotify or a browser tab first.")
        elif arg == "pause":
            outcome = media.pause()
            respond("paused", "Nothing seems to be playing right now.")
        elif arg == "next":
            outcome = media.next_track()
            respond("skipped", "There's nothing playing to skip.")
        elif arg == "previous":
            outcome = media.previous_track()
            respond("went back a track", "There's nothing playing to go back on.")
        else:
            info = media.now_playing()
            if info and (info["title"] or info["artist"]):
                state_word = "playing" if info["playing"] else "paused"
                print(f"[{state_word}: {info['title']} -- {info['artist']}]\n")
            else:
                print("[nothing seems to be playing]\n")

    elif name == "/volume":
        if not media.volume_available():
            print("[volume control isn't available -- see LIA/media.py]\n")
        elif arg == "up":
            new_level = media.adjust_volume(VOLUME_STEP)
            if new_level is not None:
                print(f"[volume: {new_level}%]\n")
                speaker.say(f"Volume's at {new_level} percent.")
            else:
                print("[couldn't change the volume]\n")
        elif arg == "down":
            new_level = media.adjust_volume(-VOLUME_STEP)
            if new_level is not None:
                print(f"[volume: {new_level}%]\n")
                speaker.say(f"Volume's at {new_level} percent.")
            else:
                print("[couldn't change the volume]\n")
        elif arg == "mute":
            outcome = media.mute(True)
            print("[muted]\n" if outcome else "[couldn't mute]\n")
            speaker.say("Muted." if outcome else "I couldn't mute that.")
        elif arg == "unmute":
            outcome = media.mute(False)
            print("[unmuted]\n" if outcome else "[couldn't unmute]\n")
            speaker.say("Unmuted." if outcome else "I couldn't unmute that.")
        else:
            level = media.get_volume()
            print(f"[volume: {level}%]\n" if level is not None else "[couldn't read the volume]\n")

    elif name == "/library":
        if arg in ("scan", "refresh", "reload", "read"):
            try:
                files_done, chunks = sync_library()
            except requests.RequestException:
                print("[couldn't reach Ollama -- try again in a moment]\n")
                return True
            if not chunks:
                print("[nothing new to read]\n")
        shelf = library.titles()
        if shelf:
            print("[in her library]")
            for title, count in shelf:
                print(f"  - {title} ({count} passages)")
            print(f"  drop more files in {LIBRARY_DIR}, then /library scan\n")
        else:
            print(f"[library is empty -- put PDFs in {LIBRARY_DIR}, then /library scan]\n")

    elif name == "/voices":
        found = voice.available_voices()
        if found:
            print("[voices in LIA/voices/]")
            for v in found:
                print(f"  - {v}")
            print("  set VOICE_NAME in config.py to pick one\n")
        else:
            print("[no voice files found -- see LIA/voices/README.md]\n")

    elif name == "/help":
        print(HELP)

    else:
        print(f"[unknown command {name} -- try /help]\n")

    return True


class Controls:
    """Switches something outside the loop can flip while it runs.

    The tray app has no console to type into, so pausing, closing out the
    conversation and quitting all have to be reachable from another thread.
    """

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.quit = threading.Event()
        self.close_now = threading.Event()
        self.speaker: "voice.Speaker | None" = None
        # Seeded rather than empty: the tray menu reads this to draw its
        # checkmarks, and it can be opened before the conversation loop has
        # started up.
        self.state: dict = {"listening": True, "open_mic": OPEN_MIC, "wake_word": WAKE_WORD_ENABLED}

    def stop(self):
        self.quit.set()


class Keyboard:
    """Reads stdin on its own thread.

    With an open mic there's nothing to block on -- she's listening, not waiting
    for Enter -- so typing has to be something we can check for rather than wait
    for. Whichever arrives first, voice or keys, wins the turn.
    """

    def __init__(self):
        self._lines: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _read(self):
        while True:
            try:
                line = sys.stdin.readline()
            except Exception:
                line = ""
            self._lines.put(line)
            if line == "":
                # EOF (or a real error) -- readline() returns "" immediately
                # forever after this, so without stopping here the thread
                # spins as fast as the CPU allows, flooding the queue with
                # empty strings. Found this by running with piped/redirected
                # input, where stdin genuinely does hit EOF.
                return

    def pending(self) -> bool:
        return not self._lines.empty()

    def take(self) -> str | None:
        try:
            line = self._lines.get_nowait()
        except queue.Empty:
            return None
        if line == "":          # stdin closed
            raise EOFError
        return line.strip()


def spoken_command(text: str) -> str | None:
    """Map a said-aloud instruction onto the typed command that does it.

    "Lia, stop listening" should switch the mic off, not become something she
    muses about.
    """
    cleaned = re.sub(r"[^a-z\s]", "", text.lower()).strip()
    words = cleaned.split()
    if not words or len(words) > 6:
        return None

    for command, phrases in SPOKEN_COMMANDS.items():
        for phrase in phrases:
            # Word-boundary matching, not character-substring: "unmute" must
            # never match a phrase like "mute" just because the characters
            # happen to appear at the end of the word. A prior version of
            # this used cleaned.endswith(phrase) on raw strings, and "unmute"
            # matched "mute" every time -- found by testing "unmute" and
            # getting "/volume mute" back instead of "/volume unmute".
            phrase_words = phrase.split()
            n = len(phrase_words)
            if words == phrase_words or words[:n] == phrase_words or words[-n:] == phrase_words:
                return command
    return None


def wait_for_her(speaker: voice.Speaker, listener, state: dict) -> str | None:
    """Let her finish speaking -- unless you talk over her.

    Returns what you said if you interrupted, otherwise None.
    """
    barge_in = (
        BARGE_IN
        and state.get("listening")
        and state.get("open_mic")
        and listener is not None
        and speaker.enabled
    )

    if not barge_in:
        speaker.wait()
        return None

    while speaker.is_busy():
        heard = listener.listen_open(hint=speech_hint(), abort=lambda: not speaker.is_busy())
        if not heard:
            continue
        if speaker.sounds_like_me(heard, ratio=ECHO_MATCH_RATIO):
            continue                       # that was her own voice coming back
        if len(heard.split()) < BARGE_IN_MIN_WORDS:
            continue                       # a cough, not an interruption
        speaker.drop_pending()
        print(f"\n  [you cut in: {heard}]\n")
        return heard

    return None


def _passcode_match(text: str, passcode: str) -> bool:
    """A passcode has to be said cleanly -- strip punctuation/case, but don't
    fuzzy-match it, or "on code" could slide through as "encode.\""""
    cleaned = re.sub(r"[^a-z]", "", text.lower())
    return cleaned == passcode.lower()


def is_unlock_passcode(text: str) -> bool:
    return _passcode_match(text, PASSCODE_UNLOCK)


def is_explain_passcode(text: str) -> bool:
    return _passcode_match(text, PASSCODE_EXPLAIN)


def explain_document(path, speaker: voice.Speaker, controls: "Controls | None" = None):
    """Read a document's full text and have her explain it in her own words --
    a one-off, isolated call, not routed through the normal library search
    (that's built for a targeted question, not "explain the whole thing")."""
    path = Path(path)
    if not path.exists():
        message = "I'm supposed to have a copy of that document, but I can't find it right now."
        print(f"LIA: {message}\n")
        speaker.say(message)
        return

    pages = library.extract(path)
    text = "\n\n".join(t for _, t in pages)
    if not text.strip():
        message = "I have the file, but I can't actually read any text out of it."
        print(f"LIA: {message}\n")
        speaker.say(message)
        return

    messages = [
        {
            "role": "system",
            "content": (
                "You are Lia. Explain the document below in your own words, as if walking a "
                "friend through it out loud -- warm, conversational, not a dry summary. Cover the "
                "main sections and what each tool is for. Keep it to a reasonable length for "
                "spoken conversation, not an exhaustive recitation."
            ),
        },
        {"role": "user", "content": text},
    ]

    status("reading it over")
    pieces = []
    sentences = voice.SentenceBuffer()
    try:
        for piece in llm.chat_stream(messages):
            if controls is not None and controls.quit.is_set():
                break
            if not pieces:
                clear_status()
                print("LIA: ", end="", flush=True)
            print(piece, end="", flush=True)
            pieces.append(piece)
            for sentence in sentences.feed(piece):
                speaker.say(sentence)
    except (KeyboardInterrupt, requests.RequestException) as exc:
        clear_status()
        print(f"\n  [couldn't finish explaining it: {exc}]\n")
        speaker.drop_pending()
        return

    clear_status()
    speaker.say(sentences.flush())
    print("\n")


def claims_identity(text: str) -> bool:
    """Does this sound like them confirming who they are -- "it's Wade"?

    Built from the current `name` fact rather than a hardcoded name, so a
    future rename doesn't silently break voice enrollment the way earlier
    hardcoded names once broke other things.
    """
    name = db.get_all_facts().get("name")
    if not name:
        return False
    pattern = re.compile(rf"\b(?:it'?s|this is|it is)\s+{re.escape(name)}\b", re.IGNORECASE)
    return bool(pattern.search(text))


def check_access_gate(user_input: str, state: dict, speaker: voice.Speaker) -> bool:
    """Gate the start of a session behind either the identity phrase or a
    passcode. Returns True if this turn was consumed by the gate (the caller
    should move on to the next turn), False if the turn should proceed as
    normal conversation.

    Deliberately stricter than the per-action voice-match gating elsewhere:
    getting the passcode wrong doesn't just decline one thing, it stops her
    listening outright, since this is the one check standing before anything
    happens at all.
    """
    if state.get("authenticated"):
        return False

    if not PASSCODE_UNLOCK:
        # No LIA_PASSCODE set -- treat the gate as switched off rather than
        # locking you out with a passcode that can never be typed correctly.
        # Printed once per session, not every turn, so it's noticeable without
        # being noisy.
        if not state.get("_warned_no_passcode"):
            print("[access gate: no LIA_PASSCODE set, so this session isn't locked -- "
                  "see config.py]\n")
            state["_warned_no_passcode"] = True
        state["authenticated"] = True
        return False

    if claims_identity(user_input):
        state["authenticated"] = True
        return False  # let the rest of this utterance, if any, proceed normally

    if state.get("awaiting_passcode"):
        state["awaiting_passcode"] = False
        if is_unlock_passcode(user_input):
            state["authenticated"] = True
            message = "Thanks -- go ahead."
            print(f"LIA: {message}\n")
            speaker.say(message)
        else:
            state["listening"] = False
            message = "That's not right, so I'll stop listening for now."
            print(f"LIA: {message}")
            # Voice genuinely can't reach her once listening is off -- saying
            # so would be misleading. Recovery has to be manual on purpose.
            print("[listening off -- type \"/mic on\", or use the tray menu]\n")
            speaker.say(message)
        return True

    state["awaiting_passcode"] = True
    message = "I don't recognise that voice. What's the passcode?"
    print(f"LIA: {message}\n")
    speaker.say(message)
    return True


def process_voice_sample(text: str, audio, state: dict):
    """Fold this turn's audio into voice enrollment if it was an identity
    claim, and otherwise update state['voice_match'] with how confidently the
    speaker matches the enrolled voice.

    state['voice_match'] is True / False / None. None means "no basis to
    judge" (not enrolled yet, no audio, or extraction failed) and must never
    be treated as a confirmed mismatch -- only an explicit False does that.
    """
    state["voice_match"] = None
    state["voice_score"] = None
    if audio is None or not speaker_id.available():
        return

    if claims_identity(text):
        if speaker_id.enroll(audio):
            progress = speaker_id.enrollment_progress()
            if progress <= SPEAKER_ENROLL_TARGET:
                print(f"[voice: learning your voice -- {progress}/{SPEAKER_ENROLL_TARGET}]")
        state["voice_match"] = True  # they just told her who they are -- trust this turn
        # Set here, on the raw utterance, not left to check_access_gate: if
        # this same breath also contains an action ("it's Wade, play some
        # music"), as_instruction() rewrites the text to "/media play" further
        # down the pipeline, and the identity phrase would be gone by the time
        # anything downstream tried to read it back out of the text.
        state["authenticated"] = True
        return

    if speaker_id.is_enrolled():
        # Computed once and reused for both -- confidence() and
        # sounds_enrolled() would otherwise each re-run the embedding
        # extraction on the same audio.
        score = speaker_id.confidence(audio)
        state["voice_score"] = score
        state["voice_match"] = None if score is None else score >= speaker_id.SPEAKER_MATCH_THRESHOLD


def accept_spoken(spoken: str, state: dict) -> str | None:
    """Decide whether something heard was actually meant for her.

    Returns the text to act on, or None to go on listening. Without this an open
    mic answers the television.
    """
    if not state.get("wake_word"):
        return spoken

    addressed, cleaned = voice.detect_wake(spoken, WAKE_WORDS)
    in_conversation = time.monotonic() < state.get("window_until", 0.0)

    if addressed:
        return cleaned
    if in_conversation:
        return spoken
    return None


def as_instruction(text: str) -> str:
    """Turn a spoken instruction into its command form, if it is one."""
    return spoken_command(text) or text


def prewarm():
    """Begin loading the model as soon as you start speaking."""
    if PREWARM_ON_SPEECH:
        llm.warm_up()


def speech_hint() -> str:
    """Names Whisper should expect, so it doesn't spell them phonetically."""
    names = {v for k, v in db.get_all_facts().items() if "name" in k}
    return "This is a conversation with Lia. " + " ".join(sorted(names))


def read_input(
    listener: voice.Listener | None,
    state: dict,
    keys: "Keyboard | None",
    controls: "Controls | None" = None,
) -> str:
    """The next turn, however it arrives -- spoken or typed."""
    global PROMPT_HINT

    open_mic = state["listening"] and state["open_mic"] and listener is not None

    # No console to type into: wait for her to be spoken to, nothing else.
    if keys is None:
        if not open_mic:
            raise EOFError("no input available")
        while not (controls and controls.quit.is_set()):
            spoken = listener.listen_open(
                hint=speech_hint(),
                abort=(lambda: bool(controls and (controls.quit.is_set() or controls.close_now.is_set()))),
                on_speech_start=prewarm,
            )
            if spoken:
                process_voice_sample(spoken, listener.last_audio, state)
                meant_for_her = accept_spoken(spoken, state)
                if meant_for_her:
                    print(f"  heard: {spoken}")
                    return as_instruction(meant_for_her)
                # Logged, because with no console this is the only way to tell
                # "she can't hear me" from "she heard me and ignored it".
                print(f'  [heard "{spoken}" -- say her name to get her attention]')
            if controls and controls.close_now.is_set():
                return ""
        raise EOFError("stopped")

    if not open_mic:
        PROMPT_HINT = "You (Enter to speak): " if state["listening"] and listener else "You: "
        print(PROMPT_HINT, end="", flush=True)
        while True:
            typed = keys.take()
            if typed is not None:
                break
            time.sleep(0.05)

        if typed:
            state["voice_match"] = None  # typed on your own keyboard -- no voice signal either way
            if claims_identity(typed):
                # Checked here, on the raw text, before as_instruction() gets
                # a chance to rewrite something like "it's Wade, play music"
                # down to just "/media play" and lose the identity phrase.
                state["authenticated"] = True
            return as_instruction(typed)
        if not state["listening"] or listener is None:
            return typed

        spoken = listener.listen(hint=speech_hint())
        if not spoken:
            print("  [didn't catch that]\n")
            return ""
        process_voice_sample(spoken, listener.last_audio, state)
        print(f"  heard: {spoken}\n")
        return spoken

    # Open mic: she's listening. Let her hear the room until either speech
    # lands or a keystroke takes over.
    PROMPT_HINT = "You (just talk, or type): "
    print(PROMPT_HINT, end="", flush=True)

    while True:
        spoken = listener.listen_open(hint=speech_hint(), abort=keys.pending, on_speech_start=prewarm)

        typed = keys.take()
        if typed is not None:
            state["voice_match"] = None
            if typed and claims_identity(typed):
                state["authenticated"] = True
            return as_instruction(typed) if typed else typed
        if spoken:
            process_voice_sample(spoken, listener.last_audio, state)
            meant_for_her = accept_spoken(spoken, state)
            if meant_for_her is None:
                print(f"  [heard \"{spoken}\" -- not addressed to me]".ljust(60), end="\r", flush=True)
                continue
            print(f"\n  heard: {spoken}\n")
            return as_instruction(meant_for_her)


def format_transcript(short_term: list[dict]) -> str:
    """Label turns by who said them.

    Raw "user:"/"assistant:" labels make a 3B model lose track of which side it
    was, and it starts writing the diary as if it were the human.
    """
    speaker = {"user": "Them", "assistant": "Lia"}
    return "\n".join(f"{speaker.get(t['role'], t['role'])}: {t['content']}" for t in short_term)


class Session:
    """One conversation.

    Lia is meant to be left running, so a session can't depend on you typing
    "bye" -- it rolls over on its own after a long enough silence, which is what
    makes the diary and fact extraction actually happen when you just walk away.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.id = str(uuid.uuid4())
        self.turns: list[dict] = []
        self.last_activity = time.monotonic()

    def touch(self):
        with self._lock:
            self.last_activity = time.monotonic()

    def add(self, role: str, content: str):
        with self._lock:
            self.turns.append({"role": role, "content": content})
            self.last_activity = time.monotonic()

    def recent(self, n: int) -> list[dict]:
        with self._lock:
            return list(self.turns[-n:])

    def idle_seconds(self) -> float:
        with self._lock:
            return time.monotonic() - self.last_activity

    def detach(self) -> tuple[str | None, list[dict]]:
        """Take the current turns and start a fresh session in their place."""
        with self._lock:
            if not self.turns:
                return None, []
            old_id, old_turns = self.id, self.turns
            self.id = str(uuid.uuid4())
            self.turns = []
            self.last_activity = time.monotonic()
            return old_id, old_turns


def close_out(session: Session, free_memory: bool = True) -> bool:
    """Write the diary + facts for whatever has been said so far."""
    session_id, turns = session.detach()
    if not turns:
        return False
    end_session(session_id, turns)
    if free_memory and RELEASE_MODELS_WHEN_IDLE:
        # The conversation is over and the diary is written -- nothing more will
        # be asked of the models until you come back, so give the VRAM up.
        llm.unload()
        print("[released the models -- she'll reload them when you speak]")
    return True


def start_idle_watchdog(session: Session, stop: threading.Event, state: dict) -> threading.Thread:
    """Close out the conversation once it's been quiet long enough."""
    idle_limit = IDLE_MINUTES * 60

    def loop():
        while not stop.wait(30):
            if session.idle_seconds() >= idle_limit:
                print(f"\n\n[quiet for {IDLE_MINUTES} minutes -- closing out the conversation]")
                close_out(session)
                # A new session starts locked again, same as a fresh process --
                # "at the start of every convo" means every one, not just the first.
                state["authenticated"] = False
                state["awaiting_passcode"] = False
                print("\n[still here whenever you are]")
                print(PROMPT_HINT, end="", flush=True)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread


def start_alarm_watchdog(speaker: voice.Speaker, stop: threading.Event) -> threading.Thread:
    """Speak any alarm/timer that comes due, regardless of what else is happening.

    Checked independently of the conversation loop -- an alarm has to fire
    whether or not you're mid-sentence with her, or she isn't listening at all.
    """
    def loop():
        while not stop.wait(10):
            for label in alarms.check_due():
                message = f"{label.capitalize()} is up."
                print(f"\n[{message}]")
                speaker.say(message)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread


def end_session(session_id: str, short_term: list[dict]):
    if not short_term:
        return
    transcript = format_transcript(short_term)

    print("\nLIA is writing in her diary...")
    entry = diary.write_entry(session_id, transcript)
    print(f"\n[diary entry]\n{entry}\n")

    facts = memory.extract_and_store_facts(transcript)
    if facts:
        print(f"[remembered: {', '.join(facts.keys())}]")


_SINGLE_INSTANCE_MUTEX = "Global\\Lia_Companion_SingleInstance"
_ERROR_ALREADY_EXISTS = 183

# Kept alive for the life of the process -- letting this be garbage collected
# doesn't close the underlying OS handle (ctypes HANDLEs aren't finalized by
# Python), but naming it makes the intent obvious rather than relying on that.
_instance_lock = None


def _already_running() -> bool:
    """True if another Lia is already running.

    She'd otherwise start twice if launched by hand while the autostart copy
    is still up -- two processes fighting over the same microphone and
    speakers, two tray icons for one companion. A Windows mutex is released
    automatically if the process dies or crashes, so a bad shutdown can never
    leave a stale lock behind.
    """
    global _instance_lock
    try:
        _instance_lock = ctypes.windll.kernel32.CreateMutexW(None, False, _SINGLE_INSTANCE_MUTEX)
        return ctypes.windll.kernel32.GetLastError() == _ERROR_ALREADY_EXISTS
    except (AttributeError, OSError):
        return False  # not on Windows, or the call failed -- don't block startup over it


def main(controls: "Controls | None" = None):
    if _already_running():
        print("[Lia is already running -- check your system tray, or Task Manager for a Lia.exe process]")
        return

    db.init_db()
    session = Session()
    headless = bool(controls and controls.headless)

    speaker = voice.Speaker(enabled=SPEAK_ENABLED)
    listener = voice.Listener() if (LISTEN_ENABLED or headless) else None
    state = {
        "listening": True if headless else LISTEN_ENABLED,
        "open_mic": True if headless else OPEN_MIC,
        "wake_word": WAKE_WORD_ENABLED,
        "window_until": 0.0,
        # Every new session starts locked -- reset on rollover in
        # start_idle_watchdog too, not just here at process start.
        "authenticated": False,
        "awaiting_passcode": False,
    }
    keys = None if headless else Keyboard()

    # Published before anything that can block. Waiting on Ollama can take a
    # couple of minutes at login, and until this is set the tray menu has no
    # state to read -- which showed as Listening/Speaking sitting unchecked.
    if controls is not None:
        controls.speaker = speaker
        controls.state = state

    # On autostart she wins the race against Ollama nearly every time.
    if not llm.is_up():
        print("[waiting for Ollama...]")
        if llm.wait_until_ready():
            print("[Ollama is up]")
        else:
            print("[Ollama unreachable -- she'll keep trying as you talk to her]")

    stop_watchdog = threading.Event()
    start_idle_watchdog(session, stop_watchdog, state)
    start_alarm_watchdog(speaker, stop_watchdog)

    print("LIA is here. Say 'bye' to end the session, /help for commands.")
    print(f"[she'll close out the conversation on her own after {IDLE_MINUTES} quiet minutes]")
    if state["listening"] and state["open_mic"]:
        print("[open mic -- just talk, she answers when you stop]")
    print()

    if speaker.enabled:
        speaker.preload()
        print(f"[speaking with: {speaker.voice_name}]\n")

    if LIBRARY_AUTO_READ:
        start_library_sync()
    else:
        waiting = library.pending()
        if waiting:
            names = ", ".join(p.name for p in waiting[:3])
            print(f'[{len(waiting)} new file(s) waiting: {names}]')
            print('[say "Lia, read my files" when you want her to]\n')

    # Load the speech model before greeting, not after. Otherwise the greeting
    # opens the conversation window while she's still deaf, and by the time she
    # can hear you the window has closed and she ignores you.
    if listener is not None and state["listening"]:
        listener.warm_up()

    if GREET_ON_START:
        status("waking up")
        try:
            hello = diary.greeting(db.get_all_facts())
        except requests.RequestException:
            hello = ""
        clear_status()
        if hello:
            print(f"LIA: {hello}\n")
            speaker.say(hello)
            speaker.wait()
            # She just asked you something -- you shouldn't have to say her name
            # to answer. Short window, so an empty room doesn't keep her
            # listening to everything for a full minute.
            state["window_until"] = time.monotonic() + GREETING_WINDOW_SECONDS
            print(f"[answer her within {GREETING_WINDOW_SECONDS}s, or say \"Lia\" any time after]\n")

    pending_input: str | None = None

    while True:
        if controls is not None and controls.quit.is_set():
            stop_watchdog.set()
            close_out(session)
            speaker.drop_pending()
            break

        if controls is not None and controls.close_now.is_set():
            controls.close_now.clear()
            if close_out(session):
                print("[closed out the conversation -- diary written]")
            else:
                print("[nothing to write about yet -- talk to her first]")

        try:
            if pending_input:
                # You cut her off last turn -- what you said is already waiting.
                user_input, pending_input = as_instruction(pending_input), None
            else:
                user_input = read_input(listener, state, keys, controls)
        except (EOFError, KeyboardInterrupt):
            user_input = "bye"

        session.touch()

        if not user_input:
            continue

        # Ending the session always has to work, authenticated or not -- an
        # access gate that traps you in the conversation instead of letting
        # you leave is a much worse bug than anything it's supposed to guard
        # against. (Found the hard way: with this check later, once
        # unauthenticated, "bye" got treated as a passcode guess instead of
        # exiting, and piped/EOF input spun forever re-triggering it.)
        if user_input.lower() in {"bye", "exit", "quit"}:
            stop_watchdog.set()
            close_out(session)
            print("LIA: Take care. I'll be here.")
            speaker.say("Take care. I'll be here.")
            speaker.wait()
            break

        # Available any time, unlocked or not -- knowing the word is itself
        # the point, same as the passcode below.
        if is_explain_passcode(user_input):
            explain_document(DECODE_DOCUMENT_PATH, speaker, controls)
            continue

        # Checked before commands, not after: "play some music" gets rewritten
        # to "/media play" by as_instruction() upstream, so if the gate ran
        # after handle_command, every gated action would reach it pre-converted
        # into a slash command and slip straight through untouched -- found
        # exactly this happening in testing.
        if check_access_gate(user_input, state, speaker):
            continue

        if handle_command(user_input, speaker, state):
            if state["listening"] and listener is None:
                listener = voice.Listener()
            continue

        # Checked deterministically, before the LLM ever sees it -- a timer
        # has to fire at the right second, not whatever a 3B model guesses.
        if alarms.would_schedule(user_input) and state.get("voice_match") is False:
            print("[not setting that -- this doesn't sound like the voice I know]\n")
            speaker.say("That doesn't sound like you, so I'll hold off on that for now.")
            continue

        alarm_reply = alarms.schedule(user_input)
        if alarm_reply is not None:
            print(f"LIA: {alarm_reply}\n")
            speaker.say(alarm_reply)
            speaker.wait()
            continue

        messages = [build_system_message(state)]

        net_context = build_internet_context(user_input)
        if net_context:
            messages.append(net_context)

        media_context = build_media_context(user_input)
        if media_context:
            messages.append(media_context)

        # Short acknowledgements ("yeah", "okay", "no") are common and retrieval
        # never has anything useful to say about them -- skip the ~2s embedding
        # call entirely rather than spend it for nothing.
        if len(user_input.split()) >= RETRIEVAL_MIN_WORDS:
            status("remembering")
            # Embedded once and reused for both searches -- these used to each
            # embed the same sentence separately, paying for it twice a turn.
            try:
                query_vec = llm.embed(user_input)
            except requests.RequestException:
                query_vec = None

            mem_context = build_memory_context(user_input, query_vec=query_vec)
            if mem_context:
                messages.append(mem_context)

            status("checking her reading")
            lib_context = build_library_context(user_input, query_vec=query_vec)
            if lib_context:
                messages.append(lib_context)

        messages.extend(session.recent(SHORT_TERM_TURNS))
        messages.append({"role": "user", "content": user_input})

        status("thinking")
        pieces = []
        sentences = voice.SentenceBuffer()
        try:
            for piece in llm.chat_stream(messages):
                if controls is not None and controls.quit.is_set():
                    break
                if not pieces:
                    clear_status()
                    print("LIA: ", end="", flush=True)
                print(piece, end="", flush=True)
                pieces.append(piece)
                # Start speaking sentence one while the rest is still generating.
                for sentence in sentences.feed(piece):
                    speaker.say(sentence)
        except KeyboardInterrupt:
            speaker.drop_pending()
            print("\n  [interrupted]\n")
            continue
        except requests.RequestException:
            # Ollama went away mid-conversation. Say so plainly and wait for it
            # rather than dying and taking the tray icon with us.
            clear_status()
            print("\n  [lost contact with Ollama -- waiting for it to come back]")
            if llm.wait_until_ready():
                print("  [back]\n")
            else:
                print("  [still unreachable -- check that Ollama is running]\n")
            continue

        clear_status()
        speaker.say(sentences.flush())
        reply = "".join(pieces).strip()
        print("\n")

        session.add("user", user_input)
        session.add("assistant", reply)

        status("saving")
        memory.remember_turn(session.id, "user", user_input)
        memory.remember_turn(session.id, "assistant", reply)
        clear_status()

        # Let her finish -- or let you talk over her. Without barge-in this just
        # blocks until playback ends, so she never hears her own tail.
        interruption = wait_for_her(speaker, listener, state)
        if not interruption and state["listening"] and state["open_mic"]:
            time.sleep(MIC_SETTLE_SECONDS)

        # The conversation window starts when she stops talking, not when she
        # started -- otherwise a long reply eats most of it.
        state["window_until"] = time.monotonic() + CONVERSATION_WINDOW_SECONDS
        pending_input = interruption


if __name__ == "__main__":
    main()
