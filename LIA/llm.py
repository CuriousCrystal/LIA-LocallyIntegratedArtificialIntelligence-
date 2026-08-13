import json
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import requests


class Unavailable(RuntimeError):
    """Ollama isn't reachable. Recoverable -- she waits rather than dying."""


def is_up(timeout: float = 3.0) -> bool:
    try:
        requests.get(f"{OLLAMA_URL}/api/tags", timeout=timeout)
        return True
    except requests.RequestException:
        return False


def wait_until_ready(total_seconds: float = 180, try_launch: bool = True) -> bool:
    """Block until Ollama answers, optionally starting it.

    On autostart she'll almost always beat Ollama to the login -- without this
    she'd crash on her very first sentence every single boot.
    """
    if is_up():
        return True

    if try_launch:
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                # Start it somewhere neutral. Launched from inside a packaged
                # app, Ollama's llama-server workers pick up DLLs out of the
                # bundle's _internal folder and hold handles on them, which
                # locks the app's own files for as long as a model is loaded.
                cwd=str(Path.home()),
            )
        except Exception:
            pass  # not installed, or not on PATH -- fall through and keep waiting

    deadline = time.monotonic() + total_seconds
    while time.monotonic() < deadline:
        if is_up():
            return True
        time.sleep(2)
    return False

from config import (
    OLLAMA_URL, MODEL_CHAT, MODEL_EMBED, OLLAMA_KEEP_ALIVE, NUM_CTX,
    CLOUD_CHAT_ENABLED, CLOUD_MAX_TOKENS, CLOUD_LOG_USAGE, CLOUD_FALLBACK_LOG,
    OPENROUTER_API_KEY, OPENROUTER_MODEL, DATA_DIR,
)

OPTIONS = {"num_ctx": NUM_CTX}

# Every cloud fallback, appended as one JSON object per line -- same shape and
# same reasoning as intent.py's intent_log.jsonl. `lia.log` already shows each
# one as it happens, but as prose with no timestamp; this is what a "how often
# does this actually happen" question needs to be answered from data instead
# of a guess.
_FALLBACK_LOG_PATH = DATA_DIR / "cloud_fallback_log.jsonl"


def _log_fallback(reason: str, mid_stream: bool):
    if not CLOUD_FALLBACK_LOG:
        return
    try:
        _FALLBACK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_FALLBACK_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "at": datetime.now().isoformat(timespec="seconds"),
                "reason": reason,
                "mid_stream": mid_stream,
                "model": OPENROUTER_MODEL,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass  # logging must never be the reason a turn fails


def chat(messages: list[dict], json_mode: bool = False,
         model: str | None = None, num_predict: int | None = None,
         timeout: float = 120) -> str:
    """messages: list of {"role": "system"|"user"|"assistant", "content": str}

    json_mode constrains the model to emit valid JSON -- used for fact extraction,
    where a 3B model otherwise likes to wrap the object in explanatory prose.

    `model` runs the request against something other than MODEL_CHAT. That exists
    for the small classifiers (see judge.py): a yes/no question doesn't need the
    conversational model, and asking a 0.5B costs a fraction of the time.

    `num_predict` caps the reply length. A classifier that has answered "yes" has
    nothing further to say, and letting it run on is pure latency.
    """
    options = dict(OPTIONS)
    if num_predict is not None:
        options["num_predict"] = num_predict

    payload = {
        "model": model or MODEL_CHAT,
        "messages": messages,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": options,
    }
    if json_mode:
        payload["format"] = "json"

    resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def chat_tools(messages: list[dict], tools: list[dict], timeout: float = 30) -> list[dict]:
    """Let the model pick from a set of actions. Returns its tool_calls, which
    is empty when it didn't choose one.

    Shorter timeout than chat(): this sits between you speaking and anything
    happening, so waiting two minutes on it would be worse than not asking.
    """
    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL_CHAT,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": OPTIONS,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("message", {}).get("tool_calls") or []


class RateLimited(RuntimeError):
    """The hosted model refused this turn because of its free-tier limits."""


def using_cloud() -> bool:
    """Is the conversation going to a hosted model this turn?"""
    return bool(CLOUD_CHAT_ENABLED and OPENROUTER_API_KEY)


def _cloud_stream(messages: list[dict]):
    """Yield the reply from OpenRouter, a piece at a time.

    Streamed rather than fetched whole for the same reason the local path is:
    she starts speaking her first sentence while the rest is still arriving. A
    non-streaming cloud call would feel slower than the local model despite
    being faster, because nothing can be said until all of it lands.
    """
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://github.com/lia-companion",
            "X-Title": "Lia",
        },
        json={
            "model": OPENROUTER_MODEL,
            "messages": messages,
            "stream": True,
            "max_tokens": CLOUD_MAX_TOKENS,
            # Asks for the token counts in the final chunk, so the spend is
            # visible per turn instead of only on the dashboard.
            "stream_options": {"include_usage": True},
        },
        timeout=60,
        stream=True,
    )
    # Free models are rate limited rather than billed, so 429 is an ordinary
    # weather condition here, not an exception. Named so the log says which of
    # the two it was, since "slow" and "refused" want different responses.
    if resp.status_code == 429:
        raise RateLimited(f"{OPENROUTER_MODEL} is rate limited right now")
    resp.raise_for_status()

    said_anything = False
    for raw in resp.iter_lines():
        if not raw:
            continue
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        if not line.startswith("data: "):
            continue
        body = line[6:].strip()
        if body == "[DONE]":
            break
        try:
            chunk = json.loads(body)
        except ValueError:
            continue

        usage = chunk.get("usage")
        if usage and CLOUD_LOG_USAGE:
            print(f"\n[cloud: {usage.get('prompt_tokens')} in / "
                  f"{usage.get('completion_tokens')} out]", flush=True)

        for choice in chunk.get("choices", []):
            piece = (choice.get("delta") or {}).get("content") or ""
            if piece:
                said_anything = True
                yield piece

    if not said_anything:
        # An empty 200 is not a reply. Raise so the caller falls back to the
        # local model rather than leaving her silent.
        raise RuntimeError("cloud returned no content")


def chat_stream(messages: list[dict]):
    """Same as chat(), but yields token chunks as they arrive.

    A 3B model on 4GB VRAM takes tens of seconds per reply -- without streaming
    the terminal looks frozen the whole time.

    Goes to the cloud when one is configured, and falls back to Ollama on any
    failure. The fallback is the point: the network is the one part of this she
    does not own, so losing it should cost cleverness, not speech.
    """
    if using_cloud():
        try:
            spoke = False
            for piece in _cloud_stream(messages):
                spoke = True
                yield piece
            return
        except Exception as exc:
            if spoke:
                # Already part-way through saying something. Restarting on the
                # local model would splice two half-replies into one sentence,
                # so let it stand -- but say so, because a reply that simply
                # stops mid-thought is otherwise a mystery. Seen for real: a
                # free provider dropped the connection mid-stream.
                _log_fallback(type(exc).__name__, mid_stream=True)
                print("\n[cloud stream dropped -- that reply may be cut short]",
                      flush=True)
                return
            why = ("rate limited" if isinstance(exc, RateLimited)
                   else type(exc).__name__)
            _log_fallback(why, mid_stream=False)
            print(f"\n[cloud unavailable ({why}) -- answering locally]", flush=True)

    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL_CHAT,
            "messages": messages,
            "stream": True,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": OPTIONS,
        },
        timeout=120,
        stream=True,
    )
    resp.raise_for_status()

    for line in resp.iter_lines():
        if not line:
            continue
        chunk = json.loads(line)
        piece = chunk.get("message", {}).get("content", "")
        if piece:
            yield piece
        if chunk.get("done"):
            break


def unload():
    """Drop both models out of memory now.

    Called when a conversation ends rather than leaving OLLAMA_KEEP_ALIVE to
    expire on its own: she knows when you've stopped talking, so there's no
    reason to hold ~3.7GB of VRAM waiting for a timer.
    """
    try:
        requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": MODEL_CHAT, "messages": [], "keep_alive": 0},
            timeout=30,
        )
        requests.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": MODEL_EMBED, "input": "", "keep_alive": 0},
            timeout=30,
        )
    except requests.RequestException:
        pass  # nothing to free if Ollama isn't there


def warm_up():
    """Start loading the chat model without waiting for it.

    Fired the moment speech is detected, so the reload overlaps with
    transcription instead of running after it.
    """
    def go():
        try:
            requests.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": MODEL_CHAT,
                    "messages": [],
                    "keep_alive": OLLAMA_KEEP_ALIVE,
                    "options": OPTIONS,
                },
                timeout=120,
            )
        except requests.RequestException:
            pass

    threading.Thread(target=go, daemon=True).start()


def embed(text: str) -> list[float]:
    """Embed one string.

    Ollama 0.32 dropped /api/embeddings in favour of /api/embed, which takes
    "input" instead of "prompt" and returns a list of vectors. Try the current
    endpoint first and fall back, so Lia works on either side of that change.
    """
    resp = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": MODEL_EMBED, "input": text, "keep_alive": OLLAMA_KEEP_ALIVE},
        timeout=60,
    )

    if resp.status_code == 404:
        legacy = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": MODEL_EMBED, "prompt": text, "keep_alive": OLLAMA_KEEP_ALIVE},
            timeout=60,
        )
        legacy.raise_for_status()
        return legacy.json()["embedding"]

    resp.raise_for_status()
    return resp.json()["embeddings"][0]
