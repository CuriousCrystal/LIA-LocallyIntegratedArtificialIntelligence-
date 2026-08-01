import db
import llm
from config import DIARY_PROMPT, GREETING_PROMPT


def recent_reflections(limit: int = 2) -> str:
    """Her last diary entries, for greeting you with some continuity."""
    rows = db.recent_diary_entries(limit)
    if not rows:
        return ""
    return "\n".join(f"- {row['entry']}" for row in rows)


def greeting(facts: dict) -> str:
    """A short hello, written from what she remembers rather than hardcoded."""
    parts = []

    # Spelled out separately: in a flat list of facts a 3B model happily greets
    # the dog, because "pet name: Biscuit" reads exactly like "name: Warlock".
    person = facts.get("name")
    if person:
        parts.append(f"The person you are greeting is called {person}. Greet {person} by that name.")

    others = {k: v for k, v in facts.items() if k != "name"}
    if others:
        parts.append(
            "Other things you know about them (these are NOT the person's name -- "
            "never greet anyone but " + (person or "them") + "):\n"
            + "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in others.items())
        )
    reflections = recent_reflections()
    if reflections:
        parts.append(f"Your last diary notes:\n{reflections}")

    context = "\n\n".join(parts) or "You have not met them before."
    hello = llm.chat(
        [
            {"role": "system", "content": GREETING_PROMPT},
            {"role": "user", "content": context},
        ]
    ).strip().strip('"')

    # She sometimes slips into narrating herself: 'Hey Warlock," I say, smiling'.
    # Everything from a stray quote onward is stage direction, not greeting.
    if '"' in hello:
        hello = hello.split('"', 1)[0].rstrip(" ,;:-")

    # She sometimes answers with just the name, which lands as a summons rather
    # than a welcome.
    if len(hello.split()) < 3:
        hello = f"{person}, you're back. Good to see you." if person else "You're back. Good to see you."
    return hello


def write_entry(session_id: str, transcript: str) -> str:
    messages = [
        {"role": "system", "content": DIARY_PROMPT},
        {"role": "user", "content": transcript},
    ]
    entry = llm.chat(messages)
    db.insert_diary_entry(session_id, entry)
    return entry
