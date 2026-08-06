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
ACTION_HINTS = {
    # music / playback
    "music", "song", "songs", "track", "album", "playlist", "play", "playing",
    "played", "pause", "paused", "resume", "skip", "next", "previous", "back",
    "stop", "spotify", "youtube", "player",
    # volume
    "volume", "loud", "louder", "loudly", "quiet", "quieter", "silent", "mute",
    "muted", "unmute", "sound", "audible", "hear", "hearing",
    # library
    "read", "reading", "file", "files", "book", "books", "document", "documents",
    "pdf", "epub", "library", "novel",
    # Generic verbs that carry a request when paired with the above -- "put
    # something on", "turn that down". Common enough in ordinary speech to cost
    # the occasional wasted round-trip, which is the cheaper mistake here.
    "put", "turn",
}

_WORD = re.compile(r"[a-z]+")

# One entry per thing she can actually do. Kept parameterless on purpose: a 3B
# model picking between simple named actions is far more reliable than one
# asked to also fill in arguments correctly.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "play_music",
            "description": (
                "Resume or start playing whatever music or video is already loaded in an app "
                "or browser tab. Use when they ask to play, resume, or put music on."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pause_music",
            "description": "Pause or stop whatever is currently playing.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "next_track",
            "description": "Skip forward to the next song or track.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "previous_track",
            "description": "Go back to the previous song or track.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "volume_up",
            "description": (
                "Turn the system volume up. Use whenever they want it louder, in any wording -- "
                "'turn it up', 'I can barely hear that', 'a bit more'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "volume_down",
            "description": (
                "Turn the system volume down. Use whenever they want it quieter, in any "
                "wording -- 'turn it down', 'that's too loud', 'bring it down a bit'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mute_sound",
            "description": "Mute the system sound completely.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unmute_sound",
            "description": "Unmute the system sound, turning it back on.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_volume",
            "description": (
                "Report what the volume is currently set to. Use when they ask what the volume "
                "is, rather than asking to change it."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_files",
            "description": (
                "Read and index new documents the person has put in her library folder, so she "
                "can answer questions about them afterwards. Use when they ask her to read "
                "their files, or mention having added a book or document for her."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "just_talk",
            "description": (
                "Use this for anything that is not one of the actions above: ordinary "
                "conversation, questions, feelings, opinions, or simply talking about music, "
                "books or sound without asking for anything to be done."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

TOOL_COMMANDS = {
    "play_music": "/media play",
    "pause_music": "/media pause",
    "next_track": "/media next",
    "previous_track": "/media previous",
    "volume_up": "/volume up",
    "volume_down": "/volume down",
    "mute_sound": "/volume mute",
    "unmute_sound": "/volume unmute",
    "check_volume": "/volume",
    "read_files": "/library scan",
    "just_talk": None,
}

INSTRUCTION = (
    "Decide what this person wants from you right now. If they are asking you to control "
    "music playback, change or check the volume, or read files they've added, call the "
    "function that matches. If they are just talking to you -- conversation, a question, a "
    "feeling, or merely mentioning music or books without asking for anything -- call "
    "just_talk. Call exactly one function.\n\n"
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
    # this size actually generalises from.
    "Examples:\n"
    "'I can barely hear this' -> volume_up (asking, right now)\n"
    "'I couldn't hear you properly earlier' -> just_talk (telling you about before)\n"
    "'I've added a book for you, go have a look' -> read_files (asking you to read it)\n"
    "'I read a really good book yesterday' -> just_talk (telling you about their day)\n"
    "'Could you put something on' -> play_music (asking)\n"
    "'The music at that party was so loud' -> just_talk (describing something)"
)


def might_be_action(text: str) -> bool:
    """Worth asking the model about, or obviously just conversation?"""
    words = set(_WORD.findall(text.lower()))
    return bool(words & ACTION_HINTS)


def log_matched(text: str, command: str):
    """Record a phrase the fast matcher already handled.

    Logged too, not just the model's guesses: a fine-tune needs the confident,
    correct cases as much as the uncertain ones, or it only ever sees the
    hard examples and learns that everything is ambiguous.
    """
    _log(text, command, "matcher")


def route(text: str) -> str | None:
    """The slash command they meant, or None to treat this as conversation.

    Never raises: if Ollama is unreachable or slow, this is an optional extra
    layer, and falling back to normal conversation is a better outcome than
    failing the turn outright.
    """
    if not text or not might_be_action(text):
        return None

    try:
        calls = llm.chat_tools(
            [
                {"role": "system", "content": INSTRUCTION},
                {"role": "user", "content": text},
            ],
            TOOLS,
        )
    except Exception:
        return None

    if not calls:
        _log(text, None, "model-no-call")
        return None

    name = (calls[0].get("function") or {}).get("name")
    command = TOOL_COMMANDS.get(name)
    _log(text, command, f"model:{name}")
    return command
