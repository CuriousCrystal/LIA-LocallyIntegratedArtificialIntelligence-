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
import intent
import internet
import judge
import library
import llm
import media
import memory
import music
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
    AUTO_EXTRACT_FACTS,
    DIARY_ENABLED,
    LIBRARY_DIR,
    MUSIC_DIR,
    LIBRARY_AUTO_READ,
    BARGE_IN,
    ECHO_MATCH_RATIO,
    BARGE_IN_MIN_WORDS,
    SPOKEN_COMMANDS,
    RELEASE_MODELS_WHEN_IDLE,
    PREWARM_ON_SPEECH,
    RETRIEVAL_MIN_WORDS,
    REMEMBER_CONVERSATION,
    INTERNET_ENABLED,
    WEATHER_ENABLED,
    WEATHER_TRIGGER_WORDS,
    INTERNET_TRIGGER_PHRASES,
    VOLUME_STEP,
    SPEAKER_ENROLL_TARGET,
)

HELP = """
  /voice on|off   speak replies out loud
  /mic on|off     listen to you at all
  /openmic on|off open mic (just talk) vs push-to-talk (Enter to record)
  /wake on|off    only answer when you say her name
  /track [n|name|list|stop]         play her own music from LIA/music/
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

# Set by --no-save. When on, nothing from the session reaches the database: no
# stored turns, no fact extraction, no diary. For testing her without leaving
# invented history behind.
NO_SAVE = False


def status(text: str):
    """Transient one-line indicator, overwritten in place."""
    print(f"  ...{text}".ljust(40), end="\r", flush=True)


def clear_status():
    print(" " * 40, end="\r", flush=True)


def build_system_message(state: dict | None = None) -> dict:
    facts = db.get_all_facts()
    content = SYSTEM_PROMPT

    # A language model has no clock and no way to read the system volume, so
    # asked either question it invents an answer -- observed live, confidently
    # reporting a time an hour off and a volume of "15" that matched nothing.
    # Handing it the real values costs nothing and fixes every phrasing at
    # once, rather than needing a matching phrase for each way of asking.
    now = dt.datetime.now()
    facts_now = [f"The current time is {now.strftime('%I:%M %p').lstrip('0')} "
                 f"on {now.strftime('%A, %d %B %Y')}."]
    level = media.get_volume() if media.volume_available() else None
    if level is not None:
        facts_now.append(f"The system volume is currently at {level} percent.")
    content += (
        "\n\nTrue right now, checked at this moment -- use these exact values if asked, "
        "and never guess at them:\n- " + "\n- ".join(facts_now)
    )

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

    # Notes are things they asked her to keep, in their words. Listed apart
    # from the rest so they don't read as "note 1: ..." trivia, and so it's
    # clear these were given rather than worked out.
    notes = [v for k, v in facts.items() if k.startswith("note_")]
    others = {k: v for k, v in facts.items()
              if k != "name" and not k.startswith("note_")}
    if others:
        fact_lines = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in others.items())
        content += f"\n\nThings I remember about you:\n{fact_lines}"
    if notes:
        content += ("\n\nThings they asked you to remember, in their own words:\n"
                    + "\n".join(f"- {n}" for n in notes))

    return {"role": "system", "content": content}


def trim_repeated_name(sentence: str, name: str, already_used: bool) -> str:
    """Drop your name from a sentence if she's already used it this reply.

    The system prompt asks her to use it sparingly and a 3B ignores that --
    observed live saying "How about you, Wade?" and "What would you like to
    talk about now, Wade?" in consecutive sentences, which is how a call centre
    talks, not a friend. Only the vocative forms are removed (", Wade" and
    "Wade, ..."), so "Wade's birthday" or a genuine mention survives.
    """
    if not name or not already_used:
        return sentence
    escaped = re.escape(name)
    sentence = re.sub(rf",\s*{escaped}\b(?=[\s.!?,]|$)", "", sentence)
    # Recapitalise: removing a leading "Wade, " leaves the sentence starting on
    # a lowercase word, which Piper reads with a noticeably flat opening.
    stripped = re.sub(rf"^\s*{escaped},\s*", "", sentence)
    if stripped is not sentence and stripped[:1].islower():
        stripped = stripped[0].upper() + stripped[1:]
    sentence = stripped
    sentence = re.sub(rf"\b{escaped}\b\s*([.!?])", r"\1", sentence)
    return re.sub(r"\s+([.!?,])", r"\1", sentence).strip()


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


def build_internet_context(user_input: str) -> dict | None:
    """Weather or a looked-up answer, if the input asks for one and she's online.

    Kept as a system note she phrases in her own words, same as the library --
    she's told plainly where it came from and not to pretend it's her own
    knowledge or something you told her.
    """
    # Fully offline: weather words and "look that up" are ordinary conversation
    # again, not a request she reaches out for. Returning None rather than a
    # "no connection" note on purpose -- there is no connection to be missing.
    if not INTERNET_ENABLED:
        return None

    lowered = user_input.lower()

    if WEATHER_ENABLED and any(w in lowered for w in WEATHER_TRIGGER_WORDS):
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


# Set for as long as a library scan is running. The idle watchdog reads it:
# closing out a quiet conversation releases the models, and a book takes far
# longer to read than the twelve minutes of silence that triggers that -- so an
# unattended scan was having nomic-embed-text pulled out of VRAM underneath it.
_indexing = threading.Event()


def indexing_now() -> bool:
    """Is anything being read right now, by her or by anything else?

    The event covers her own background thread. The database check covers a scan
    running in a separate process, which the event cannot see -- and that is not
    hypothetical: reading a novel was stalled nine minutes at a stretch because
    she released the models while an external indexer was mid-book.
    """
    if _indexing.is_set():
        return True
    try:
        return db.any_unfinished_documents()
    except Exception:
        # Never let a database hiccup wedge the models in VRAM forever.
        return False


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

    _indexing.set()
    try:
        files_done, chunks = library.sync(on_progress=progress)
    finally:
        _indexing.clear()
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
            # Asked out loud ("what's the volume?"), so it has to answer out
            # loud too. Printing only meant she said nothing at all and the
            # model filled the silence with an invented number.
            level = media.get_volume()
            if level is not None:
                print(f"[volume: {level}%]\n")
                speaker.say(f"It's at {level} percent.")
            else:
                print("[couldn't read the volume]\n")
                speaker.say("I couldn't read the volume just now.")

    elif name == "/track":
        if not music.available():
            print("[music playback needs sounddevice and soundfile]\n")
            speaker.say("I can't play music right now -- something's missing on my side.")
            return True

        listing = music.tracks()
        if arg == "stop":
            was = music.now_playing()
            music.stop()
            print(f"[stopped {was}]\n" if was else "[nothing was playing]\n")
            speaker.say(f"Stopped {was}." if was else "Nothing was playing.")
            return True

        if not listing:
            print(f"[no music yet -- put files in {MUSIC_DIR}]\n")
            speaker.say("I haven't got any music yet. Put some files in my music folder "
                        "and I'll play them.")
            return True

        if arg in ("list", ""):
            print("[her music]")
            for index, path in enumerate(listing, start=1):
                print(f"  {index}. {music.describe(path)}")
            print()
            names = "; ".join(f"number {i}, {music.describe(p)}"
                              for i, p in enumerate(listing[:5], start=1))
            more = f", and {len(listing) - 5} more" if len(listing) > 5 else ""
            speaker.say(f"I have {len(listing)}: {names}{more}.")
            return True

        chosen = music.find(int(arg)) if arg.isdigit() else music.search(arg)
        if chosen is None:
            print(f"[no track {arg} -- she has {len(listing)}]\n")
            speaker.say(f"I don't have that one. There are {len(listing)} to pick from.")
            return True

        if music.play(chosen):
            print(f"[playing: {music.describe(chosen)}]\n")
            speaker.say(f"Playing {music.describe(chosen)}.")
        else:
            print(f"[couldn't play {chosen.name}]\n")
            speaker.say("I couldn't open that one.")

    elif name == "/library":
        # A voice-triggered scan ("Lia, read my files") used to only print its
        # result -- silent on anything you can't see, i.e. exactly when you
        # said it out loud. Every other spoken command speaks its result; this
        # one didn't, so it looked like she ignored the request entirely.
        scanned = arg in ("scan", "refresh", "reload", "read")
        if scanned:
            waiting = library.pending()
            if not waiting:
                print("[nothing new to read]\n")
                speaker.say("There's nothing new to read -- I've already read everything in there.")
            else:
                # Indexed on a background thread, never inline. A full novel is
                # ~590 embedding calls at roughly a second each: run here, it
                # held the whole conversation loop for twenty minutes and she
                # simply stopped answering, which is exactly how it looked from
                # the outside -- she'd frozen. Startup already backgrounded this
                # (start_library_sync); the on-demand path was the one that
                # didn't, so the freeze only ever showed up when you *asked*.
                names = ", ".join(p.stem[:40] for p in waiting[:2])
                more = f" and {len(waiting) - 2} more" if len(waiting) > 2 else ""
                # Counting first costs a fraction of a second and turns "this
                # takes a while" into an actual number, so you can decide
                # whether to wait rather than watching a silent counter.
                wait = library.describe_wait(library.estimate_seconds(waiting))
                print(f"[reading {names}{more} in the background -- {wait}]\n")
                if wait == "a moment":
                    speaker.say("On it.")
                else:
                    speaker.say(
                        f"On it -- that'll take {wait}. I'll keep talking meanwhile and tell "
                        f"you when I'm done."
                    )

                def read_in_background():
                    try:
                        files_done, chunks = sync_library(announce=False, quiet=True)
                    except requests.RequestException:
                        print("\n[couldn't reach Ollama -- try /library scan again later]\n")
                        return
                    if chunks:
                        print(f"\n[finished reading {files_done} file(s), {chunks} passages]\n")
                        speaker.say(
                            f"Finished reading -- {chunks} passages. Ask me about it whenever."
                        )

                threading.Thread(target=read_in_background, daemon=True).start()

        shelf = library.titles()
        if shelf:
            print("[in her library]")
            for title, count in shelf:
                print(f"  - {title} ({count} passages)")
            print(f"  drop more files in {LIBRARY_DIR}, then /library scan\n")
        elif not scanned:
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
    if not words:
        return None

    for command, phrases in SPOKEN_COMMANDS.items():
        for phrase in phrases:
            # Word-boundary matching, not character-substring: "unmute" must
            # never match a phrase like "mute" just because the characters
            # happen to appear at the end of the word. A prior version of
            # this used cleaned.endswith(phrase) on raw strings, and "unmute"
            # matched "mute" every time -- found by testing "unmute" and
            # getting "/volume mute" back instead of "/volume unmute".
            #
            # Matched anywhere in the utterance, not just at the very start or
            # end of it, and with no length cap. A prior version only checked
            # whether the phrase was the whole utterance, its exact prefix, or
            # its exact suffix, and gave up past 6 words -- so a real request
            # wrapped in context ("I've opened YouTube Music on a browser tab,
            # can you play the music?", 14 words) was silently rejected before
            # it ever reached a phrase check. That fell through to ordinary
            # conversation, where the local model has no idea whether
            # anything actually happened and confabulates "sure, playing it
            # now" regardless -- found by testing the exact phrasing and
            # confirming the underlying media control worked fine on its own,
            # but was simply never being called.
            phrase_words = phrase.split()
            n = len(phrase_words)
            if any(words[i:i + n] == phrase_words for i in range(len(words) - n + 1)):
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


# "Remember that the wifi password is hunter2", "don't forget I hate coriander".
# Stored verbatim rather than passed to the model to summarise into a key and a
# value: the whole point of this is that she keeps what you actually said, and
# a 3B paraphrasing it is how "sister_name" and "visiting_sister_name" both
# ended up in the database meaning the same thing.
_REMEMBER_THIS = re.compile(
    r"^(?:lia[,\s]+)?(?:please\s+)?(?:remember|note|don'?t forget)\s+"
    r"(?:that\s+|this[:,]?\s+|about\s+)?(.+)",
    re.IGNORECASE,
)


def remember_explicitly(text: str) -> str | None:
    """Store something she was directly told to keep. Returns confirmation."""
    match = _REMEMBER_THIS.match(text.strip())
    if not match:
        return None
    note = re.sub(r"[\s.]+$", "", match.group(1).strip())
    if len(note) < 3:
        return None

    if NO_SAVE:
        return f"Got it -- though I'm not saving anything this session."

    existing = db.get_all_facts()
    # Telling her the same thing twice shouldn't fill her head with copies of
    # it -- the duplicate-facts problem this whole change was meant to end.
    for key, value in existing.items():
        if key.startswith("note_") and value.strip().lower() == note.lower():
            return f"I already have that one -- {note}."

    numbers = [int(k.split("_")[1]) for k in existing if k.startswith("note_")
               and k.split("_")[-1].isdigit()]
    db.upsert_fact(f"note_{max(numbers, default=0) + 1}", note)
    # "remember to buy milk" doesn't take "that" -- "I'll remember that to buy
    # milk" is the kind of small wrongness that makes her sound like software.
    joiner = ":" if note.lower().startswith("to ") else " that"
    return f"Got it -- I'll remember{joiner} {note}."


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


# "play number 1", "play song three", "play track 2" -- her own music, by
# position. Numbers are spelled out as often as not, so the words are accepted
# too rather than making you say the digit.
_SPOKEN_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}
_PLAY_NUMBER = re.compile(
    r"\bplay\s+(?:the\s+)?(?:number|song|track|song number|track number|no\.?)?\s*"
    r"([0-9]+|" + "|".join(_SPOKEN_NUMBERS) + r")\b(?:\s+song)?",
    re.IGNORECASE,
)


def track_request(text: str) -> int | None:
    """Which numbered track they asked for, if any."""
    match = _PLAY_NUMBER.search(text)
    if not match:
        return None
    token = match.group(1).lower()
    return int(token) if token.isdigit() else _SPOKEN_NUMBERS.get(token)


def as_instruction(text: str) -> str:
    """Turn a spoken instruction into its command form, if it is one.

    Two layers, in this order for a reason: the phrase matcher is instant and
    deterministic, so it handles the everyday wordings; only what it doesn't
    recognise is worth spending a model round-trip on. See intent.py.
    """
    if text.startswith("/"):
        return text

    # Alarms get first refusal, because they're the most specific thing here:
    # scheduling one needs an explicit keyword AND a parseable time, where a
    # spoken command needs only a phrase. Without this, "wake me by saying
    # please wake up in 5 minutes" matched the "wake up" phrasing of /mic on
    # -- since phrases match anywhere in a sentence now -- and toggled the
    # microphone instead of setting the alarm. Bare "wake up" still reaches
    # /mic on below, because with no time in it there's no alarm to schedule.
    if alarms.would_schedule(text):
        return text

    # Before the phrase matcher, because "play number 3" would otherwise be
    # claimed by /media play and resume someone else's browser tab instead.
    number = track_request(text)
    if number is not None:
        intent.log_matched(text, f"/track {number}")
        return f"/track {number}"

    matched = spoken_command(text)
    if matched:
        intent.log_matched(text, matched)
        return matched
    guessed = intent.route(text)
    if guessed:
        print(f"  [took that as: {guessed}]")
        return guessed
    return text


def prewarm():
    """Begin loading the model as soon as you start speaking."""
    if PREWARM_ON_SPEECH:
        llm.warm_up()


def speech_hint() -> str:
    """Names Whisper should expect, so it doesn't spell them phonetically."""
    names = {v for k, v in db.get_all_facts().items() if "name" in k}
    return "This is a conversation with Lia. " + " ".join(sorted(names))


def _is_own_echo(heard: str, speaker: "voice.Speaker | None") -> bool:
    """Did the mic just pick up her own voice coming back?

    Checked on every transcript, not only while she's mid-sentence. Her spoken
    confirmations were being heard a moment after she finished and stored as
    things *you* had said -- her real memory ended up holding "There's nothing
    new to read, I've already read everything in there" as a line of Wade's,
    which she then quoted back at him as his own words.
    """
    if speaker is None or not speaker.enabled:
        return False
    if speaker.sounds_like_me(heard, ratio=ECHO_MATCH_RATIO):
        print(f'  [ignored my own voice: "{heard[:60]}"]'.ljust(70), end="\r", flush=True)
        return True
    return False


def read_input(
    listener: voice.Listener | None,
    state: dict,
    keys: "Keyboard | None",
    controls: "Controls | None" = None,
    speaker: "voice.Speaker | None" = None,
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
            if spoken and _is_own_echo(spoken, speaker):
                spoken = None
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
            return as_instruction(typed)
        if not state["listening"] or listener is None:
            return typed

        spoken = listener.listen(hint=speech_hint())
        if not spoken or _is_own_echo(spoken, speaker):
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
            return as_instruction(typed) if typed else typed
        if spoken and _is_own_echo(spoken, speaker):
            continue
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
    if free_memory and RELEASE_MODELS_WHEN_IDLE and not indexing_now():
        # The conversation is over and the diary is written -- nothing more will
        # be asked of the models until you come back, so give the VRAM up.
        #
        # Unless she's still reading something. "Nothing more will be asked of
        # the models" is only true of the conversation; a scan running in the
        # background is asking the embedding model for a passage every couple of
        # seconds, and unloading underneath it stalls the read it was told to do.
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
            # Spoken exactly as stored: alarms.py already decided the words,
            # because "please wake up" and "your 5 minute timer is up" don't
            # fit one template, and asking for specific words should get them.
            for message in alarms.check_due():
                print(f"\n[{message}]")
                speaker.say(message)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread


def end_session(session_id: str, short_term: list[dict]):
    if not short_term:
        return
    if NO_SAVE:
        print("\n[--no-save: skipping diary and fact extraction]\n")
        return
    if not (DIARY_ENABLED or AUTO_EXTRACT_FACTS):
        return
    transcript = format_transcript(short_term)

    if DIARY_ENABLED:
        print("\nLIA is writing in her diary...")
        entry = diary.write_entry(session_id, transcript)
        print(f"\n[diary entry]\n{entry}\n")

    if AUTO_EXTRACT_FACTS:
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
                user_input = read_input(listener, state, keys, controls, speaker)
        except (EOFError, KeyboardInterrupt):
            user_input = "bye"

        session.touch()

        if not user_input:
            continue

        # Ending the session always has to work, whatever else is going on --
        # anything that traps you in the conversation instead of letting you
        # leave is a much worse bug than whatever it was guarding against.
        if user_input.lower() in {"bye", "exit", "quit"}:
            stop_watchdog.set()
            close_out(session)
            print("LIA: Take care. I'll be here.")
            speaker.say("Take care. I'll be here.")
            speaker.wait()
            break

        if handle_command(user_input, speaker, state):
            if state["listening"] and listener is None:
                listener = voice.Listener()
            continue

        # Stored word for word, before the model can rephrase it into something
        # she'd rather have heard.
        remembered = remember_explicitly(user_input)
        if remembered is not None:
            print(f"LIA: {remembered}\n")
            speaker.say(remembered)
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


        # Short acknowledgements ("yeah", "okay", "no") are common and retrieval
        # never has anything useful to say about them -- skip the ~2s embedding
        # call entirely rather than spend it for nothing.
        #
        # The same reasoning now covers a second empty case. With the
        # conversation no longer stored, that embedding exists only to search
        # the library -- so with nothing in the library either, there is
        # nothing for it to search and every turn was paying for it anyway.
        if (len(user_input.split()) >= RETRIEVAL_MIN_WORDS
                and (REMEMBER_CONVERSATION or db.document_titles())):
            status("remembering")
            # Embedded once and reused for both searches -- these used to each
            # embed the same sentence separately, paying for it twice a turn.
            try:
                query_vec = llm.embed(user_input)
            except requests.RequestException:
                query_vec = None

            # Skipped entirely when she isn't keeping the conversation: the old
            # turns already in the database would otherwise keep surfacing long
            # after she stopped adding to them, which is the confusion this was
            # turned off to end.
            if REMEMBER_CONVERSATION:
                mem_context = build_memory_context(user_input, query_vec=query_vec)
                if mem_context:
                    messages.append(mem_context)

            # Asked before searching, not after. The similarity floor can only
            # rank passages once it has them; it cannot tell that the question
            # was never about a book in the first place -- and with a novel
            # indexed, every ordinary sentence found something.
            if judge.wants_library(user_input):
                status("checking her reading")
                lib_context = build_library_context(user_input, query_vec=query_vec)
                if lib_context:
                    messages.append(lib_context)

        messages.extend(session.recent(SHORT_TERM_TURNS))
        messages.append({"role": "user", "content": user_input})

        status("thinking")
        pieces = []
        sentences = voice.SentenceBuffer()
        her_name_for_you = db.get_all_facts().get("name", "")
        used_your_name = False
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
                    spoken_line = trim_repeated_name(sentence, her_name_for_you, used_your_name)
                    if her_name_for_you and re.search(rf"\b{re.escape(her_name_for_you)}\b",
                                                      spoken_line):
                        used_your_name = True
                    speaker.say(spoken_line)
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
        speaker.say(trim_repeated_name(sentences.flush(), her_name_for_you, used_your_name))
        reply = "".join(pieces).strip()
        print("\n")

        session.add("user", user_input)
        session.add("assistant", reply)

        if not NO_SAVE and REMEMBER_CONVERSATION:
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
    # --no-save exists because testing her wrote into her real memory. A dozen
    # piped "hello"s became stored turns, and each run ended with her writing a
    # diary entry reflecting on a conversation that never happened -- one of
    # which mused on the person "moving between unrelated topics", which was
    # only ever a list of test commands. Reflections should come from being
    # talked to, not from being checked.
    if "--no-save" in sys.argv:
        NO_SAVE = True
        print("[--no-save: nothing this session will be remembered]\n")
    main()
