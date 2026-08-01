import json
import subprocess
import time

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


def chat(messages: list[dict], json_mode: bool = False) -> str:
    """messages: list of {"role": "system"|"user"|"assistant", "content": str}

    json_mode constrains the model to emit valid JSON -- used for fact extraction,
    where a 3B model otherwise likes to wrap the object in explanatory prose.
    """
    payload = {
        "model": MODEL_CHAT,
        "messages": messages,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": OPTIONS,
    }
    if json_mode:
        payload["format"] = "json"

    resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


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
