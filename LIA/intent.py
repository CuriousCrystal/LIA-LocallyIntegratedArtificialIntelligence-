"""Working out what you meant, when your exact words don't match a command.

`SPOKEN_COMMANDS` in config.py is a list of phrasings, and it will always be
incomplete -- people don't say "volume up", they say "could you push that up a
bit, it's hard to hear." Every phrasing nobody thought to add used to fall
through to ordinary conversation, where the model, having no idea an action was
ever wanted, produced a confident "sure, doing that now" and did nothing at
all. That failure is worse than refusing outright, because it looks like it
worked.

So this is the fallback layer: when the phrase matcher finds nothing, the model
is shown the actions she can actually take and asked which one, if any, was
meant. It decides from meaning rather than from a list of remembered wordings.

Deliberately a *fallback*, not a replacement:

- The matcher is instant, free and completely deterministic. Measured against
  the same request eight times, the model alone chose correctly seven times and
  silently did nothing on the eighth -- fine as a safety net, not as the only
  thing standing between you and a command being heard.
- Asking the model costs a round-trip, so it only runs when the words look like
  they could plausibly be about an action at all (see `might_be_action`).
  Ordinary conversation never pays for it.

An explicit "just talking" option is offered alongside the real actions, and
that matters more than it looks: given only actions to choose from, a small
model will pick one for "tell me something calming" rather than admit none
apply. With somewhere to put ordinary conversation, it stops forcing the fit.
"""

import json
import re
from datetime import datetime

import llm
from config import DATA_DIR, INTENT_LOG

# Every decision, appended as one JSON object per line. Not for debugging --
# it's the training data a future fine-tune would need, and the only way to
# get it is from real use rather than invented examples. A few hundred rows of
# "this is what he actually said, this is what she did with it" is worth more
# than any amount of guessing at phrasings up front.
_LOG_PATH = DATA_DIR / "intent_log.jsonl"


def _log(text: str, decided: str | None, source: str):
    if not INTENT_LOG:
        return
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "at": datetime.now().isoformat(timespec="seconds"),
                "said": text,
                "decided": decided,
                "source": source,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass  # logging must never be the reason a turn fails

# Cheap pre-filter: is this even plausibly about something she can do? Wrong
# guesses here are cheap in one direction only -- a false positive costs one
# round-trip and the model then says "just talking", while a false negative
# means the request is silently never understood. So it's deliberately loose.
#
# The actions left in the menu after the trim are mic/voice/wake switching and
# the notes commands, so the hint words follow them. Music, volume and library
# vocabulary used to live here too and were removed with the actions they
# pointed at -- a leftover "volume" hint would have meant "louder" paid a model
# round-trip only to be told "just_talk", which is worse than never asking.
ACTION_HINTS = {
    # listening / speaking
    "listen", "listening", "hear", "hearing", "mic", "microphone", "voice",
    "speak", "speaking", "talk", "talking", "quiet", "hush", "mute", "unmute",
    "silent", "sleep", "wake",
    # her name / attention
    "name", "attention", "everything",
    # her memory (the sticky notes)
    "remember", "remembers", "note", "notes", "sticky", "memorize", "memorise",
    "forget", "know", "memory",
}

_WORD = re.compile(r"[a-z]+")

# One entry per thing she can actually do. Kept parameterless on purpose: a 3B
# model picking between simple named actions is far more reliable than one
# asked to also fill in arguments correctly.
#
# Asked for as one word rather than as a tool call. This used to go through
# Ollama's function-calling API, and that quietly stopped working the day
# MODEL_CHAT became gemma2:2b -- gemma2's chat template carries no tool
# handling at all (no .Tools, no .ToolCalls), so Ollama rejects a request with
# a tools array outright. route()'s own `except Exception: return None` then
# swallowed the 400, and this entire layer returned None for every input
# without ever saying so. It measured 30/32 on llama3.2:3b and 0/n here.
#
# A named-choice completion needs nothing from the template, so it works on
# whatever OPENAI_CHAT_MODEL happens to be -- which is the property this layer
# actually wants, given it exists to be a safety net.
ACTIONS = {
    "mic_off": "Stop listening entirely until they start you again.",
    "mic_on": "Start listening again after being put to sleep.",
    "voice_off": "Go silent -- stop speaking replies out loud, keep listening.",
    "voice_on": "Speak replies out loud again after being muted.",
    "wake_off": "Answer everything heard, not only sentences addressed to her by name.",
    "wake_on": "Only answer when they say her name first.",
    "read_notes": (
        "Read back what their sticky notes say -- the things they have written down "
        "for her. Use when they ask what she remembers or knows about them."
    ),
    "reload_notes": "Re-read the notes folder in case they added or changed notes.",
    "just_talk": (
        "Anything that is not one of the actions above: ordinary conversation, "
        "questions, feelings, opinions. Talking is what she is for."
    ),
}

TOOL_COMMANDS = {
    "mic_off": "/mic off",
    "mic_on": "/mic on",
    "voice_off": "/voice off",
    "voice_on": "/voice on",
    "wake_off": "/wake off",
    "wake_on": "/wake on",
    "read_notes": "/notes",
    "reload_notes": "/notes reload",
    "just_talk": None,
}

# Longest first, and it has to stay that way: "voice_off" is a substring of
# nothing now, but the scan reads an answer of "voice_off" correctly only while
# no other name contains it -- same class of bug as the one spoken_command()
# carries a comment about ("unmute" matching "mute"). Keep the sort even when
# every current name is safe; a future "voice_off_all" would otherwise break it.
_ACTION_NAMES = sorted(TOOL_COMMANDS, key=len, reverse=True)

_MENU = "\n".join(f"{name} -- {what}" for name, what in ACTIONS.items())

INSTRUCTION = (
    "Decide what this person wants from you right now, and answer with exactly one of "
    "these names and nothing else. No punctuation, no explanation, no sentence.\n\n"
    f"{_MENU}\n\n"
    "If they are asking you to switch your listening or speaking, change how you "
    "decide what's addressed to you, or read back their notes, answer with the name "
    "that matches. If they are just talking to you -- conversation, a question, a "
    "feeling, an opinion, anything else at all -- answer just_talk.\n\n"
    # The distinction that matters is asking-vs-telling, not present-vs-past.
    # An earlier version of this said "only if they want it to happen NOW",
    # which read "I've added a book, go have a look" as past-tense chatter and
    # ignored it every single time -- a real request lost to a rule meant to
    # stop "I couldn't hear you earlier" being taken as a live one.
    "The question is whether they are ASKING YOU TO DO something, or TELLING YOU ABOUT "
    "something. Reporting, remembering or commenting is just_talk, even when it mentions "
    "sound, music or books. But a sentence can describe something already done and still be "
    "a request -- 'I've put a book in your folder, take a look' is asking you to read it.\n\n"
    # Abstract rules alone didn't land: stated as principles, "I couldn't hear
    # you earlier" turned the volume up 5 times out of 5, and "I added a book,
    # go have a look" was ignored 5 out of 5. Concrete pairs are what a model
    # this size actually generalises from. The pairs kept below are the ones
    # that still have actions to map onto after the trim.
    "Examples:\n"
    "'Stop listening' -> mic_off (asking, right now)\n"
    "'I couldn't hear you properly earlier' -> just_talk (telling you about before)\n"
    "'I've written some things down for you, take a look' -> read_notes (asking her to read them)\n"
    "'I read a really good book yesterday' -> just_talk (telling you about their day)\n"
    "'You can talk now' -> voice_on (asking)\n"
    "'The music at that party was so loud' -> just_talk (describing something)"
)


def might_be_action(text: str) -> bool:
    """Worth asking the model about, or obviously just conversation?"""
    words = set(_WORD.findall(text.lower()))
    return bool(words & ACTION_HINTS)


def _chosen(answer: str) -> str | None:
    """Which action the model named, or None if it named nothing we know.

    Deliberately a scan rather than an equality check. Asked for one word, a
    small model still sometimes wraps it -- "volume_up.", "**volume_up**",
    "The answer is volume_up" -- and throwing all of those away would recreate
    the silent do-nothing this whole layer exists to prevent. Anything genuinely
    unrecognisable still returns None and is treated as conversation.
    """
    if not answer:
        return None
    lowered = answer.lower()
    return next((name for name in _ACTION_NAMES if name in lowered), None)


def log_matched(text: str, command: str):
    """Record a phrase the fast matcher already handled.

    Logged too, not just the model's guesses: a fine-tune needs the confident,
    correct cases as much as the uncertain ones, or it only ever sees the
    hard examples and learns that everything is ambiguous.
    """
    _log(text, command, "matcher")


def route(text: str) -> str | None:
    """The slash command they meant, or None to treat this as conversation.

    Never raises: if the model is unreachable or slow, this is an optional extra
    layer, and falling back to normal conversation is a better outcome than
    failing the turn outright.
    """
    if not text or not might_be_action(text):
        return None

    try:
        answer = llm.chat(
            [
                {"role": "system", "content": INSTRUCTION},
                {"role": "user", "content": text},
            ],
            # Long enough for the longest name: "unmute_sound" is four tokens
            # on its own, and a model that opens with a stray space or newline
            # needs the headroom or the name arrives truncated.
            num_predict=8,
            # Same reasoning as chat_tools' old 20s: this sits between someone
            # speaking and anything happening, so waiting two minutes on it
            # would be worse than not asking at all.
            timeout=20,
        )
    except Exception:
        # Model unreachable or slow. This is an optional extra layer, and
        # falling back to ordinary conversation beats failing the turn.
        return None

    name = _chosen(answer)
    if name is None:
        # It answered, but with nothing recognisable. Logged distinctly from a
        # clean "just_talk" -- one is the model deciding, the other is the
        # model wandering, and telling them apart is the whole point of having
        # this log at all.
        _log(text, None, "model-unparsed")
        return None

    command = TOOL_COMMANDS.get(name)
    _log(text, command, f"model:{name}")
    return command
