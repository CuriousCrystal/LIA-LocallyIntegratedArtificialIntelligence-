"""Lia's one path to a model: Ollama, running locally.

Chat goes through Ollama's native HTTP API (localhost, see OLLAMA_BASE_URL) --
a local model, not a hosted one, so nothing about a conversation leaves the
machine. Speech-to-text is local faster-whisper. There is still no fallback:
if Ollama isn't running or the model named by LOCAL_CHAT_MODEL hasn't been
pulled, she says so and moves on, the same as a hosted API being unreachable
used to mean.
"""

import json
from datetime import datetime

import numpy as np
import requests

from config import (
    OLLAMA_BASE_URL, LOCAL_CHAT_MODEL, LOCAL_WHISPER_MODEL,
    LOCAL_WHISPER_COMPUTE_TYPE, LOCAL_TIMEOUT,
    CLOUD_LOG_USAGE, CLOUD_FALLBACK_LOG, DATA_DIR, CLOUD_MAX_TOKENS,
)


class CloudError(RuntimeError):
    """A request to the model failed and there is nowhere to fall back to.

    Named for the hosted-API era this project started in; kept so callers
    (main.py's except clauses) didn't need touching for a local model to
    raise the same shape of error a hosted one used to.
    """


class RateLimited(CloudError):
    """Ollama returned 429 -- concurrent request limits, if OLLAMA_NUM_PARALLEL
    or similar caps are set. Rare for a single-user local server, but the
    class stays so main.py's handling of it doesn't need to change."""


def _classify_429(resp) -> CloudError:
    return RateLimited("the model server is rate limited right now")


def _ollama_url(path: str) -> str:
    return f"{OLLAMA_BASE_URL}/{path.lstrip('/')}"


def have_key() -> bool:
    """Is there a model to talk to at all?

    No API key for a local server -- this now asks Ollama whether
    LOCAL_CHAT_MODEL is actually pulled, which is the local equivalent of "is
    there anything to answer with". A server that isn't running fails the
    same request and is reported the same way (see chat_stream).
    """
    try:
        resp = requests.get(_ollama_url("api/tags"), timeout=5)
        resp.raise_for_status()
        names = {m.get("name", "") for m in resp.json().get("models", [])}
        # Ollama's tags include a ":tag" suffix (":latest" if none was given
        # when pulling); LOCAL_CHAT_MODEL may or may not include one.
        wanted = LOCAL_CHAT_MODEL if ":" in LOCAL_CHAT_MODEL else f"{LOCAL_CHAT_MODEL}:latest"
        return wanted in names or any(n.startswith(LOCAL_CHAT_MODEL + ":") for n in names)
    except requests.RequestException:
        return False


# Every failure to reach the model, appended as one JSON object per line to
# the same file fallback_report.py already reads. Named cloud_fallback_log.jsonl
# from the hosted-API era; the question it answers -- "how often can she not
# reach the model" -- is the same question locally.
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
                "model": LOCAL_CHAT_MODEL,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass  # logging must never be the reason a turn fails


# ------------------------------------------------------------------- chat ---

def chat(messages: list[dict], json_mode: bool = False,
         model: str | None = None, num_predict: int | None = None,
         timeout: float = LOCAL_TIMEOUT) -> str:
    """messages: list of {"role": "system"|"user"|"assistant", "content": str}

    json_mode constrains the reply to a single valid JSON object (Ollama's
    format="json"). `model` runs the request against something other than
    LOCAL_CHAT_MODEL; `num_predict` caps the reply length (a classifier that
    has answered "yes" has nothing more to say) -- Ollama's own name for this,
    which is also why chat_stream below uses it instead of "max_tokens".
    """
    payload = {
        "model": model or LOCAL_CHAT_MODEL,
        "messages": messages,
        "stream": False,
    }
    options = {}
    if num_predict is not None:
        options["num_predict"] = num_predict
    if options:
        payload["options"] = options
    if json_mode:
        payload["format"] = "json"

    try:
        resp = requests.post(_ollama_url("api/chat"), json=payload, timeout=timeout)
        if resp.status_code == 429:
            raise _classify_429(resp)
        resp.raise_for_status()
        return (resp.json().get("message") or {}).get("content") or ""
    except CloudError:
        raise
    except requests.RequestException as exc:
        raise CloudError(f"chat request failed: {exc}") from exc


def chat_stream(messages: list[dict]):
    """Same as chat(), but yields the reply a piece at a time.

    Streamed so she starts speaking her first sentence while the rest is still
    generating -- on CPU-only local inference this matters even more than it
    did for a hosted API, since a full reply can take several seconds to
    finish.

    Raises CloudError (or RateLimited) on any failure. There is no fallback;
    the caller says so and moves on.
    """
    payload = {
        "model": LOCAL_CHAT_MODEL,
        "messages": messages,
        "stream": True,
        "options": {"num_predict": CLOUD_MAX_TOKENS},
    }

    try:
        resp = requests.post(_ollama_url("api/chat"), json=payload,
                             timeout=LOCAL_TIMEOUT, stream=True)
        if resp.status_code == 429:
            raise _classify_429(resp)
        resp.raise_for_status()
    except CloudError as exc:
        _log_fallback(type(exc).__name__, mid_stream=False)
        raise
    except requests.RequestException as exc:
        _log_fallback(type(exc).__name__, mid_stream=False)
        # Ollama not running is the most likely cause on a local setup --
        # connection refused, not a 4xx/5xx -- so it lands here, not above.
        raise CloudError(
            f"chat stream failed to start (is Ollama running? {exc})") from exc

    said_anything = False
    prompt_tokens = completion_tokens = None
    try:
        # Ollama streams newline-delimited JSON objects, not SSE ("data: "
        # lines) -- each line is a complete chunk on its own, no prefix to
        # strip.
        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
            try:
                chunk = json.loads(line)
            except ValueError:
                continue

            piece = (chunk.get("message") or {}).get("content") or ""
            if piece:
                said_anything = True
                yield piece

            if chunk.get("done"):
                prompt_tokens = chunk.get("prompt_eval_count")
                completion_tokens = chunk.get("eval_count")
                break
    except requests.RequestException as exc:
        # The connection dropped mid-reply. Whatever was already said stands --
        # restarting would splice two half-answers together -- so let the caller
        # know it may be cut short rather than pretending it finished.
        _log_fallback(type(exc).__name__, mid_stream=True)
        raise CloudError(f"stream dropped: {exc}") from exc

    if CLOUD_LOG_USAGE and (prompt_tokens is not None or completion_tokens is not None):
        print(f"\n[local: {prompt_tokens} in / {completion_tokens} out]", flush=True)

    if not said_anything:
        _log_fallback("empty reply", mid_stream=False)
        raise CloudError("model returned no content")


# ------------------------------------------------------------ speech (STT) ---

# Loaded lazily, once, on first use -- constructing a WhisperModel loads (and,
# on first run ever, downloads) the model weights, which has no reason to pay
# for itself before she is ever asked to transcribe anything.
_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel(
            LOCAL_WHISPER_MODEL, device="cpu",
            compute_type=LOCAL_WHISPER_COMPUTE_TYPE,
        )
    return _whisper_model


def transcribe(audio_i16, sample_rate: int = 16000, prompt: str | None = None) -> str | None:
    """One recorded utterance -> text, via local faster-whisper.

    `prompt` is the short vocabulary hint (names that would otherwise be
    spelled phonetically) -- faster-whisper's initial_prompt parameter means
    the same thing Whisper's hosted API prompt field did. Returns None on any
    failure -- a companion that hears nothing this once is better than one
    that raises mid-conversation.
    """
    try:
        model = _get_whisper_model()
    except Exception as exc:
        print(f"[voice] couldn't load the local speech model: {exc}")
        return None

    # faster-whisper wants float32 samples in [-1, 1], not raw int16 -- the
    # same audio voice.py already records, just rescaled.
    audio_f32 = audio_i16.astype(np.float32) / 32768.0

    try:
        segments, _info = model.transcribe(
            audio_f32, language="en", initial_prompt=prompt or None,
        )
        text = "".join(segment.text for segment in segments).strip()
    except Exception as exc:
        print(f"[voice] transcription failed: {exc}")
        return None

    return text or None
