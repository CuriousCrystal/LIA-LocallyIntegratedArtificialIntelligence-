import ctypes
import datetime as dt
import os
import queue
import sys
import threading
import time

# Measured: the VAD model (via onnxruntime's OpenMP backend) defaults to a
# spinning thread pool that burns CPU waiting for the next chunk instead of
# sleeping between them -- 389% of one core, continuously, just from Lia
# sitting there listening to silence. PASSIVE drops that to ~94% with no
# measurable effect on real-time detection (32ms chunks only need ~31
# calls/sec; even passive-waited throughput is far above that). Must be set
# before onnxruntime/ctranslate2 initialize, so this runs before any other
# import in the whole process.
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")

import re
import uuid

import requests

# The model is fond of em-dashes and ellipses. On Windows, writing those to a
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

import intent
import llm
import notes
import voice
from config import (
    SYSTEM_PROMPT,
    STARTUP_GREETING,
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
    NOTES_DIR,
    SPOKEN_COMMANDS,
    CLOUD_HISTORY_TURNS,
)

HELP = """
  /voice on|off   speak replies out loud
  /mic on|off     listen to you at all
  /openmic on|off open mic (just talk) vs push-to-talk (Enter to record)
  /wake on|off    only answer when you say her name
  /notes          what she knows from your sticky notes
  /notes reload   re-read the notes folder
  /notes where    where her memory (your notes app) lives
  /help           this list
  bye             end the session
"""

# Whatever read_input() last advertised as the way in, so a transient line
# printed from another thread can restore the prompt beneath itself.
PROMPT_HINT = "You: "


def status(text: str):
    """Transient one-line indicator, overwritten in place."""
    print(f"  ...{text}".ljust(40), end="\r", flush=True)


def clear_status():
    print(" " * 40, end="\r", flush=True)


def build_system_message() -> dict:
    content = SYSTEM_PROMPT

    # A language model has no clock, so asked the time it invents an answer --
    # observed live, confidently reporting a time an hour off. Handing it the
    # real value costs nothing and fixes every phrasing at once.
    now = dt.datetime.now()
    content += (
        f"\n\nTrue right now, checked at this moment -- use this exact value if "
        f"asked, and never guess at it: the current time is "
        f"{now.strftime('%I:%M %p').lstrip('0')} on {now.strftime('%A, %d %B %Y')}."
    )

    # Her memory, read fresh this turn: their sticky notes, their words, the
    # only record of them that exists. Not included when there are none -- the
    # system prompt already tells her she starts knowing nothing, and an empty
    # block would read as a bug rather than a fact.
    try:
        note_context = notes.as_context()
    except OSError:
        note_context = None  # unreadable folder; notes.all_notes() already printed why
    if note_context:
        content += f"\n\n{note_context}"

    return {"role": "system", "content": content}


class Controls:
    """Switches something outside the loop can flip while it runs.

    The tray app has no console to type into, so pausing and quitting both
    have to be reachable from another thread.
    """

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.quit = threading.Event()
        # Set while a reply is being generated but before the first word is
        # spoken -- the desktop avatar reads it to show a "thinking" pose.
        self.thinking = threading.Event()
        self.speaker: "voice.Speaker | None" = None
        # Set by app.py before main() starts, when the typed training panel
        # is up: anything with the same .pending()/.take() shape as Keyboard
        # works here, so main() can't tell a GUI entry box from stdin.
        self.panel_keys = None
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
            # matched "mute" every time.
            #
            # Matched anywhere in the utterance, not just at the very start or
            # end of it. A prior version only checked whether the phrase was
            # the whole utterance, its exact prefix, or its exact suffix, and
            # gave up past 6 words -- so a real request wrapped in context was
            # silently rejected before it ever reached a phrase check.
            phrase_words = phrase.split()
            n = len(phrase_words)
            if any(words[i:i + n] == phrase_words for i in range(len(words) - n + 1)):
                return command
    return None


def speech_hint() -> str:
    """Vocabulary Whisper should expect, so it doesn't spell it phonetically.

    Deliberately just her own name now: anything else the person calls
    themselves or their people lives in their notes, and pulling names out of
    free text to bias the recogniser risked more than it saved -- a note word
    misheard once is worse than a name spelled phonetically that the model
    can usually still make sense of.
    """
    return "This is a conversation with Lia."


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
                abort=(lambda: bool(controls and (controls.quit.is_set()))),
            )
            if spoken:
                meant_for_her = accept_spoken(spoken, state)
                if meant_for_her:
                    print(f"  heard: {spoken}")
                    return as_instruction(meant_for_her)
                # Logged, because with no console this is the only way to tell
                # "she can't hear me" from "she heard me and ignored it".
                print(f'  [heard "{spoken}" -- say her name to get her attention]')
            if controls and controls.quit.is_set():
                raise EOFError("stopped")
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
            return as_instruction(typed)
        if not state["listening"] or listener is None:
            return typed

        spoken = listener.listen()
        if not spoken:
            print("  [didn't catch that]\n")
            return ""
        print(f"  heard: {spoken}\n")
        # Run through as_instruction() like every other way in. This path once
        # returned the raw transcript, so switching to push-to-talk (/openmic
        # off, which /help advertises) silently turned off every spoken
        # command: "stop listening" and "reload your notes" became ordinary
        # conversation, where she says she has done it and hasn't.
        #
        # No accept_spoken() here on purpose, unlike the open-mic and headless
        # paths: you pressed Enter to record, so you were plainly talking to
        # her and the wake word has nothing left to decide.
        return as_instruction(spoken)

    # Open mic: she's listening. Let her hear the room until either speech
    # lands or a keystroke takes over.
    PROMPT_HINT = "You (just talk, or type): "
    print(PROMPT_HINT, end="", flush=True)

    while True:
        spoken = listener.listen_open(hint=speech_hint(), abort=keys.pending)

        typed = keys.take()
        if typed is not None:
            return as_instruction(typed) if typed else typed
        if spoken:
            meant_for_her = accept_spoken(spoken, state)
            if meant_for_her is None:
                print(f'  [heard "{spoken}" -- not addressed to me]'.ljust(60), end="\r", flush=True)
                continue
            print(f"\n  heard: {spoken}\n")
            return as_instruction(meant_for_her)


class Session:
    """One conversation.

    Nothing is written at a session's end any more -- there is no database --
    but the rollover still matters: after long enough silence the context
    window resets, so an always-on day doesn't grow a prompt that outlives
    her attention.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.id = str(uuid.uuid4())
        self.turns: list[dict] = []
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

    def detach(self):
        """Start a fresh session, discarding what came before."""
        with self._lock:
            self.id = str(uuid.uuid4())
            self.turns = []
            self.last_activity = time.monotonic()


def start_idle_watchdog(session: Session, stop: threading.Event) -> threading.Thread:
    """Roll the conversation over once it's been quiet long enough."""
    idle_limit = IDLE_MINUTES * 60

    def loop():
        while not stop.wait(30):
            if session.idle_seconds() >= idle_limit:
                session.detach()

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread


def _handle_notes_command(arg: str, speaker: voice.Speaker) -> bool:
    """/notes and its subcommands -- her only memory, read out loud."""
    if arg == "reload":
        found = notes.reload()
        print(f"[re-read the notes folder -- {len(found)} note(s)]\n")
        speaker.say(f"Re-read my notes -- {len(found)} of them.")
        return True

    if arg == "where":
        print(f"[her memory is your notes app: {NOTES_DIR}]\n")
        speaker.say("My memory is your sticky notes app -- that's where I read from.")
        return True

    try:
        found = notes.all_notes()
    except OSError as exc:
        print(f"[couldn't read the notes folder: {exc}]\n")
        speaker.say("I couldn't read your notes folder just now.")
        return True

    if not found:
        print(f"[no notes yet -- she knows only this conversation. "
              f"Put notes in {NOTES_DIR}]\n")
        speaker.say("There's nothing in my notes yet -- I only know what you "
                    "tell me right now.")
        return True

    print("[her memory -- your sticky notes]")
    for i, text in enumerate(found, start=1):
        print(f"  {i}. {text}")
    print(f'  "/notes reload" picks up changes\n')
    spoken = "; ".join(found[:5])
    more = f" -- and {len(found) - 5} more" if len(found) > 5 else ""
    speaker.say(f"I have {len(found)} notes: {spoken}{more}.")
    return True


def handle_command(cmd: str, speaker: voice.Speaker, state: dict) -> bool:
    """Returns True if the input was a command and has been handled."""
    parts = cmd.lower().split()
    if not parts or not parts[0].startswith("/"):
        return False

    name, arg = parts[0], (parts[1] if len(parts) > 1 else "")

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
            print(f'[say "Lia" to get her attention -- then {CONVERSATION_WINDOW_SECONDS}s of free conversation]\n')
        else:
            print("[wake word off -- she answers anything she hears]\n")

    elif name == "/notes":
        _handle_notes_command(arg, speaker)

    elif name == "/help":
        print(HELP)

    else:
        print(f"[unknown command {name} -- try /help]\n")

    return True


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
    """Turn a spoken instruction into its command form, if it is one.

    Two layers, in this order for a reason: the phrase matcher is instant and
    deterministic, so it handles the everyday wordings; only what it doesn't
    recognise is worth spending a model round-trip on. See intent.py.
    """
    if text.startswith("/"):
        return text

    matched = spoken_command(text)
    if matched:
        intent.log_matched(text, matched)
        return matched
    guessed = intent.route(text)
    if guessed:
        print(f"  [took that as: {guessed}]")
        return guessed
    return text


def main(controls: "Controls | None" = None):
    if _already_running():
        print("[Lia is already running -- check your system tray, or Task Manager for a Lia.exe process]")
        return

    session = Session()
    headless = bool(controls and controls.headless)
    # The tray app has always forced listening on in headless mode, because
    # voice used to be the only way to reach her with no console open. The
    # training panel is a second typing surface without a console, so that
    # forcing no longer applies when one is attached -- LISTEN_ENABLED
    # decides instead, same as it already does in the console app.
    have_panel = bool(controls and controls.panel_keys)

    speaker = voice.Speaker(enabled=SPEAK_ENABLED)
    listener = voice.Listener() if (LISTEN_ENABLED or headless) else None
    state = {
        "listening": LISTEN_ENABLED if (have_panel or not headless) else True,
        "open_mic": True if headless else OPEN_MIC,
        "wake_word": WAKE_WORD_ENABLED,
        "window_until": 0.0,
    }
    keys = controls.panel_keys if have_panel else (None if headless else Keyboard())

    # Published before anything that can block, so the tray menu always has
    # state to read -- otherwise Listening/Speaking sit unchecked until the
    # first slow thing at startup finishes.
    if controls is not None:
        controls.speaker = speaker
        controls.state = state

    # She thinks, hears and speaks over a hosted API now. With no key set she
    # still runs -- the mic and the wake word work -- but she can't answer and
    # can't transcribe. Said once, here, rather than as a failure on the first
    # thing you say to her.
    if not llm.have_key():
        print("[no API key set -- she can hear the mic, but can't think or transcribe]")
        print("[put GROQ_API_KEY in LIA/.env (free at console.groq.com), or an "
              "OPENAI_API_KEY with OPENAI_BASE_URL repointed, then restart]")

    # Her memory is read-only and external, so there is nothing to migrate and
    # nothing to open at startup: the notes folder is checked lazily, on the
    # first turn that asks for it (see notes.all_notes). A bad path surfaces
    # then, once, in brackets.

    stop_watchdog = threading.Event()
    start_idle_watchdog(session, stop_watchdog)

    print("LIA is here. Say 'bye' to end the session, /help for commands.")
    print(f"[her memory is your sticky notes in {NOTES_DIR}]")
    if state["listening"] and state["open_mic"]:
        print("[open mic -- just talk, she answers when you stop]")
    print()

    if speaker.enabled:
        speaker.preload()
        print(f"[speaking with: {speaker.voice_name}]\n")

    # Load the speech model before greeting, not after. Otherwise the greeting
    # opens the conversation window while she's still deaf, and by the time she
    # can hear you the window has closed and she ignores you.
    if listener is not None and state["listening"]:
        listener.warm_up()

    if GREET_ON_START and STARTUP_GREETING:
        hello = STARTUP_GREETING
        print(f"LIA: {hello}\n")
        speaker.say(hello)
        speaker.wait()
        # She just asked you something -- you shouldn't have to say her name
        # to answer. Short window, so an empty room doesn't keep her
        # listening to everything for a full minute.
        state["window_until"] = time.monotonic() + GREETING_WINDOW_SECONDS
        print(f'[answer her within {GREETING_WINDOW_SECONDS}s, or say "Lia" any time after]\n')

    while True:
        if controls is not None and controls.quit.is_set():
            stop_watchdog.set()
            speaker.drop_pending()
            break

        try:
            user_input = read_input(listener, state, keys, controls)
        except (EOFError, KeyboardInterrupt):
            user_input = "bye"

        if not user_input:
            continue

        # Ending the session always has to work, whatever else is going on --
        # anything that traps you in the conversation instead of letting you
        # leave is a much worse bug than whatever it was guarding against.
        if user_input.lower() in {"bye", "exit", "quit"}:
            stop_watchdog.set()
            print("LIA: Take care. I'll be here.")
            speaker.say("Take care. I'll be here.")
            speaker.wait()
            break

        if handle_command(user_input, speaker, state):
            if state["listening"] and listener is None:
                listener = voice.Listener()
            continue

        messages = [build_system_message()]

        # A shorter history when the turn is billed by the token. Four turns is
        # still a conversation that knows what it's about, at half the prompt --
        # and prompt size, not reply size, is where the spend actually goes.
        messages.extend(session.recent(CLOUD_HISTORY_TURNS))
        messages.append({"role": "user", "content": user_input})

        status("thinking")
        if controls is not None:
            controls.thinking.set()
        pieces = []
        sentences = voice.SentenceBuffer()
        try:
            for piece in llm.chat_stream(messages):
                if controls is not None and controls.quit.is_set():
                    break
                if not pieces:
                    clear_status()
                    if controls is not None:
                        controls.thinking.clear()
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
        except (requests.RequestException, llm.CloudError) as exc:
            # The model went away -- no key, rate limited, dropped connection.
            # There is no local model to fall back to, so say so plainly and
            # let her carry on rather than dying and taking the tray icon with
            # us. If anything was already spoken this turn it stands.
            clear_status()
            if pieces:
                print("\n  [that reply may be cut short -- lost contact with the model]\n")
                speaker.say("Sorry, I lost my train of thought there.")
            elif isinstance(exc, llm.QuotaExhausted):
                print("\n  [the API account is out of credit -- add some at "
                      "platform.openai.com/settings/organization/billing]\n")
                speaker.say("The API account is out of credit -- that's a billing thing, "
                            "not something that'll clear on its own.")
            elif isinstance(exc, llm.RateLimited):
                print("\n  [model is rate limited right now -- per-minute, or the "
                      "daily free cap]\n")
                speaker.say("I'm being rate limited right now -- give it a bit and try again.")
            elif not llm.have_key():
                print("\n  [no API key set -- I can't answer]\n")
                speaker.say("There's no API key set, so I can't think right now.")
            else:
                print(f"\n  [couldn't reach the model: {exc}]\n")
                speaker.say("I couldn't reach the model just now. Try me again in a bit.")
            continue
        finally:
            if controls is not None:
                controls.thinking.clear()

        clear_status()
        speaker.say(sentences.flush())
        reply = "".join(pieces).strip()
        print("\n")

        # The conversation is kept only for this session's context window --
        # nothing is written down anywhere. What survives between sessions is
        # exactly what's in the notes, nothing more.
        session.add("user", user_input)
        session.add("assistant", reply)

        # Let her finish speaking before the mic reopens. Without barge-in
        # (removed) this just blocks until playback ends.
        speaker.wait()
        if state["listening"] and state["open_mic"]:
            time.sleep(MIC_SETTLE_SECONDS)

        # The conversation window starts when she stops talking, not when she
        # started -- otherwise a long reply eats most of it.
        state["window_until"] = time.monotonic() + CONVERSATION_WINDOW_SECONDS


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


if __name__ == "__main__":
    main()
