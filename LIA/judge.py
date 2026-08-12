"""Small, narrow classifiers that sit in front of the expensive work.

The pattern here is the one that already works in intent.py: a 3B is poor at
open-ended judgement and good at one closed question with concrete examples. So
rather than one model deciding everything, a tiny model answers a single yes/no
and the rest of the pipeline acts on it.

The first of these exists because a similarity threshold provably could not do
the job. Once a novel was indexed, every ordinary sentence pulled passages out
of it -- 7 of 7 measured, roughly 500 tokens of Harry Potter handed to her
before she answered "how are you doing today". The obvious fix is to raise
LIBRARY_MIN_SCORE, and the numbers say that cannot work:

    genuinely about the book        ordinary conversation
      0.519  platform nine and 3/4    0.583  I watched a film with my friend
      0.631  the Mirror of Erised     0.553  I couldn't sleep last night
      0.702  who is Hagrid            0.456  how are you doing today

The populations overlap. That is not a badly chosen number, it is the honest
result: a novel is *about* sleeping and eating and families, so small talk
genuinely resembles it. No floor separates them.

But "is this person asking about a document?" is an easy question, and a 0.5B
answers it in a fraction of the time the 3B would take to do anything at all.
"""

import llm
from config import JUDGE_MODEL, JUDGE_ENABLED

# Deliberately not "decide if the library is relevant" -- stated as an abstract
# rule, a small model applies it inconsistently. intent.py learned the same
# thing the hard way: as rules it got the volume case wrong five times out of
# five, and concrete examples fixed it outright. So the prompt is examples.
_LIBRARY_PROMPT = """You decide whether someone is asking about their saved documents.

Answer YES if they are asking about the contents of a book, file, PDF or something
they have given you to read.
Answer NO for ordinary conversation, small talk, feelings, plans, or requests to do
something.

Examples:
"who is Hagrid" -> YES
"what does the book say about wands" -> YES
"in the story, what happened at the lake" -> YES
"what did you read about Quidditch" -> YES
"remind me what chapter three was about" -> YES
"I had a really long day at work today" -> NO
"I couldn't sleep last night" -> NO
"my sister is coming to visit on Sunday" -> NO
"how are you doing today" -> NO
"can you turn the volume up" -> NO
"set a timer for ten minutes" -> NO
"remember that the wifi password is bluebird" -> NO

Answer with one word: YES or NO."""


def _ask(text: str, model: str) -> bool:
    """One yes/no, from whichever model is doing the judging.

    Fails open. If the judge is unreachable or says something unexpected, fall
    back to searching -- an occasional irrelevant passage is a poor answer, but
    silently losing the ability to quote a book she has read is a worse bug.
    """
    try:
        answer = llm.chat(
            [{"role": "system", "content": _LIBRARY_PROMPT},
             {"role": "user", "content": text}],
            model=model,
            # It has to say one word. Anything longer is the model narrating,
            # and every extra token is latency on the critical path.
            num_predict=3,
            timeout=20,
        )
    except Exception:
        return True

    verdict = answer.strip().upper()
    if verdict.startswith("NO"):
        return False
    return True


def wants_library(text: str) -> bool:
    """Is this a question about something she has read?"""
    if not JUDGE_ENABLED:
        return True
    return _ask(text, JUDGE_MODEL)
