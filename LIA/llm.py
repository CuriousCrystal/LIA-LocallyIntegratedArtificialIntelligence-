import json
import subprocess
import threading
import time
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

from config import OLLAMA_URL, MODEL_CHAT, MODEL_EMBED, OLLAMA_KEEP_ALIVE, NUM_CTX

OPTIONS = {"num_ctx": NUM_CTX}


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


def chat_stream(messages: list[dict]):
    """Same as chat(), but yields token chunks as they arrive.

    A 3B model on 4GB VRAM takes tens of seconds per reply -- without streaming
    the terminal looks frozen the whole time.
    """
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
