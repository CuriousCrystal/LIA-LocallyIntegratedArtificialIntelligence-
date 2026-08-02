import datetime as dt
import json
import re

import numpy as np

import db
import llm
from config import MEMORY_TOP_K, FACT_EXTRACTION_PROMPT, PROTECTED_FACTS


def remember_turn(session_id: str, role: str, content: str):
    """Embed and store a single conversation turn for later semantic recall."""
    vec = llm.embed(content)
    db.insert_memory(session_id, role, content, vec)


def ago(timestamp: str) -> str:
    """Rough, human relative time -- 'yesterday', 'last week'.

    Without this every memory arrives in an eternal present and Lia can't tell
    something said five minutes ago from five weeks ago.
    """
    try:
        then = dt.datetime.fromisoformat(timestamp)
    except (TypeError, ValueError):
        return "at some point"

    days = (dt.datetime.now() - then).days
    if days <= 0:
        return "earlier today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 14:
        return "last week"
    if days < 60:
        return f"{days // 7} weeks ago"
    return f"{days // 30} months ago"


def retrieve_relevant(query: str, top_k: int = MEMORY_TOP_K, query_vec=None) -> list[tuple[str, str]]:
    """Most semantically similar things the person has said, newest scoring ties first.

    Returns (content, when) pairs. Only their turns are searched -- see
    db.all_memories().

    `query_vec` lets a caller that already embedded this turn's text (for the
    library search, say) hand it over instead of paying for a second identical
    embedding call.
    """
    rows = db.all_memories(role="user")
    if not rows:
        return []

    query_vec = np.array(query_vec) if query_vec is not None else np.array(llm.embed(query))
    query_norm = np.linalg.norm(query_vec) or 1e-8

    scored = []
    for row in rows:
        vec = np.array(json.loads(row["embedding"]))
        denom = (np.linalg.norm(vec) * query_norm) or 1e-8
        sim = float(np.dot(query_vec, vec) / denom)
        scored.append((sim, row["content"], row["created_at"]))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [(content, ago(created)) for _, content, created in scored[:top_k]]


# Values a small model reaches for when it has nothing real to say. Storing any
# of these is worse than storing nothing: "name: you" silently overwrites a real
# name, and Lia then greets you by it.
_JUNK_VALUES = {
    "you", "your", "yours", "me", "my", "i", "them", "they", "us", "we", "it",
    "user", "the user", "the person", "person", "human", "assistant",
    "lia", "aurora", "ai", "companion",
    "unknown", "not specified", "unspecified", "not mentioned", "not given",
    "none", "n/a", "na", "null", "nil", "nothing", "no", "yes", "true", "false",
    "example", "string", "value", "text", "todo",
}

_MAX_VALUE_LEN = 120
_MAX_KEY_LEN = 40


def _clean_key(key) -> str | None:
    key = re.sub(r"[^a-z0-9_]", "", str(key).strip().lower().replace(" ", "_")).strip("_")
    if not key or len(key) > _MAX_KEY_LEN or key in _JUNK_VALUES:
        return None
    return key


def _clean_value(value) -> str | None:
    # The model occasionally answers with a list, or nests another object.
    if isinstance(value, (list, tuple)):
        parts = [str(v).strip() for v in value if isinstance(v, (str, int, float))]
        value = ", ".join(p for p in parts if p)
    elif isinstance(value, dict):
        return None

    value = str(value).strip().strip('"').strip()
    if not value or len(value) > _MAX_VALUE_LEN:
        return None
    if value.lower() in _JUNK_VALUES:
        return None
    return value


def clean_facts(raw: dict) -> dict:
    """Drop keys and values that aren't real facts about the person."""
    cleaned = {}
    for key, value in raw.items():
        k, v = _clean_key(key), _clean_value(value)
        # "name: name" and friends -- the model echoing the schema back.
        if k and v and v.lower() != k.replace("_", " "):
            cleaned[k] = v
    return cleaned


def extract_and_store_facts(transcript: str):
    """Ask the model to pull durable facts out of a session and upsert them."""
    messages = [
        {"role": "system", "content": FACT_EXTRACTION_PROMPT},
        {"role": "user", "content": transcript},
    ]
    raw = llm.chat(messages, json_mode=True)

    try:
        # Small models sometimes wrap JSON in prose/backticks -- grab the {...} span.
        start, end = raw.index("{"), raw.rindex("}") + 1
        parsed = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return {}

    if not isinstance(parsed, dict):
        return {}

    facts = clean_facts(parsed)

    # Never let a session transcript rewrite what they've asked to be called.
    existing = db.get_all_facts()
    facts = {
        k: v for k, v in facts.items()
        if not (k in PROTECTED_FACTS and k in existing)
    }

    for key, value in facts.items():
        db.upsert_fact(key, value)

    return facts
