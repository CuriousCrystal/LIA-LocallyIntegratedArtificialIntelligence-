"""Lia's one path to a hosted model.

Chat and speech-to-text go through an OpenAI-compatible HTTP API -- Groq
(api.groq.com) by default, anything else via OPENAI_BASE_URL. There is no local
model any more: Ollama, and every is-it-up / launch-it / warm-it / unload-it
function that used to manage one, are gone. A hosted model has no warm-up to
pay and no memory to free.

Every request here sends `store: false` where the API supports it. That does not
make the conversation stay on the machine -- sending it is what the request is --
but it keeps the provider from retaining the completion for its own dashboards.
The rest of the privacy posture is an org setting on the provider side.
"""

import base64
import io
import json
import wave
from datetime import datetime

import requests

from config import (
    OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_CHAT_MODEL,
    OPENAI_TRANSCRIBE_MODEL, OPENAI_TIMEOUT,
    CLOUD_LOG_USAGE, CLOUD_FALLBACK_LOG, DATA_DIR,
    GEMINI_API_KEY, GEMINI_REASONING_EFFORT, USING_GEMINI_STT,
    CLOUD_MAX_TOKENS,
)


class CloudError(RuntimeError):
    """A request to the hosted model failed and there is nowhere to fall back to.

    There is no local model behind this any more, so the caller's job is to say
    so plainly, not to retry against something else.
    """


class RateLimited(CloudError):
    """The model refused this turn for rate-limit reasons (HTTP 429) -- too many
    requests too fast. Waiting a moment and trying again is the right response."""


class QuotaExhausted(CloudError):
    """Also an HTTP 429, but `insufficient_quota` -- the API account is out of
    credit. Waiting does nothing; it needs money added at platform.openai.com.
    Its own class so the caller says that, not "rate limited, try again"."""


def _classify_429(resp) -> CloudError:
    """A 429 is either a real rate limit (wait, retry) or an exhausted account
    (waiting won't help). Tell them apart from the error body so the spoken
    reason is honest. Groq's free tier has no balance to exhaust, so its 429s
    always fall through to RateLimited -- correct, though the wait may be until
    the daily free limit resets rather than a few seconds."""
    try:
        kind = (resp.json().get("error") or {}).get("type", "")
    except Exception:
        kind = ""
    if kind == "insufficient_quota":
        return QuotaExhausted("the API account is out of credit")
    return RateLimited("the model is rate limited right now")


def _openai_url(path: str) -> str:
    return f"{OPENAI_BASE_URL}/{path.lstrip('/')}"


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {OPENAI_API_KEY}"}


def _sends_store() -> bool:
    """`store: false` is an OpenAI parameter -- it asks them not to keep the
    completion for their own dashboards. Other OpenAI-compatible servers (Groq,
    the default) can 400 on an unrecognised field, so only send it to OpenAI."""
    return "openai.com" in OPENAI_BASE_URL


def have_key() -> bool:
    """Is there an API key to talk to the model with at all?"""
    return bool(OPENAI_API_KEY)


# Every cloud error, appended as one JSON object per line to the same file
# fallback_report.py already reads. It used to record fallbacks to the local
# model; there is no local model now, so it records the failures themselves --
# "how often can she not reach the model" is the question a week of this
# answers and a single session can't.
_FALLBACK_LOG_PATH = DATA_DIR / "cloud_fallback_log.jsonl"

# Gemini's own API (not the OpenAI-compat one), used only for transcription --
# the compat layer has no route for it.
_GEMINI_NATIVE_URL = "https://generativelanguage.googleapis.com/v1beta"


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
                "model": OPENAI_CHAT_MODEL,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass  # logging must never be the reason a turn fails


# ------------------------------------------------------------------- chat ---

def chat(messages: list[dict], json_mode: bool = False,
         model: str | None = None, num_predict: int | None = None,
         timeout: float = OPENAI_TIMEOUT) -> str:
    """messages: list of {"role": "system"|"user"|"assistant", "content": str}

    json_mode constrains the reply to a single valid JSON object. (Unused by
    any caller right now -- fact extraction is gone with the database -- but
    kept because it is one flag the API already supports.)

    `model` runs the request against something other than OPENAI_CHAT_MODEL;
    `num_predict` caps the reply length (a classifier that has answered "yes"
    has nothing more to say). Both keep the same names the Ollama version had
    so intent.py did not need touching.
    """
    payload = {
        "model": model or OPENAI_CHAT_MODEL,
        "messages": messages,
        "stream": False,
    }
    if _sends_store():
        payload["store"] = False
    if num_predict is not None:
        payload["max_tokens"] = num_predict
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        resp = requests.post(_openai_url("chat/completions"),
                             headers=_auth_headers(), json=payload, timeout=timeout)
        if resp.status_code == 429:
            raise _classify_429(resp)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"] or ""
    except CloudError:
        raise
    except requests.RequestException as exc:
        raise CloudError(f"chat request failed: {exc}") from exc


def chat_stream(messages: list[dict]):
    """Same as chat(), but yields the reply a piece at a time.

    Streamed so she starts speaking her first sentence while the rest is still
    arriving -- a spoken paragraph fetched whole feels slower than one that
    begins right away, even when it isn't.

    Raises CloudError (or RateLimited) on any failure. There is no local model
    to fall back to; the caller says so and moves on.
    """
    payload = {
        "model": OPENAI_CHAT_MODEL,
        "messages": messages,
        "stream": True,
        "max_tokens": CLOUD_MAX_TOKENS,
        # Ask for the token counts in the final chunk, so the spend is visible
        # per turn instead of only on the dashboard.
        "stream_options": {"include_usage": True},
    }
    if _sends_store():
        payload["store"] = False
    # Gemini reasons before it speaks, and every second of that is silence
    # before her first word. "low" keeps the thinking short; other providers
    # never see the field.
    if GEMINI_REASONING_EFFORT:
        payload["reasoning_effort"] = GEMINI_REASONING_EFFORT

    try:
        resp = requests.post(_openai_url("chat/completions"), headers=_auth_headers(),
                             json=payload, timeout=OPENAI_TIMEOUT, stream=True)
        if resp.status_code == 429:
            raise _classify_429(resp)
        resp.raise_for_status()
    except CloudError as exc:
        _log_fallback(type(exc).__name__, mid_stream=False)
        raise
    except requests.RequestException as exc:
        _log_fallback(type(exc).__name__, mid_stream=False)
        raise CloudError(f"chat stream failed to start: {exc}") from exc

    said_anything = False
    try:
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
    except requests.RequestException as exc:
        # The connection dropped mid-reply. Whatever was already said stands --
        # restarting would splice two half-answers together -- so let the caller
        # know it may be cut short rather than pretending it finished.
        _log_fallback(type(exc).__name__, mid_stream=True)
        raise CloudError(f"cloud stream dropped: {exc}") from exc

    if not said_anything:
        _log_fallback("empty reply", mid_stream=False)
        raise CloudError("cloud returned no content")


# ------------------------------------------------------------ speech (STT) ---

def _wav_bytes(audio_i16, sample_rate: int) -> bytes:
    """Wrap raw int16 mono samples in a WAV container, in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio_i16.astype("<i2").tobytes())
    return buf.getvalue()


def _gemini_transcribe(audio_i16, sample_rate: int, prompt: str | None) -> str | None:
    """Her ears on Gemini: the native generateContent API with the utterance
    inlined as a WAV.

    The OpenAI-compatibility layer has no /audio/transcriptions route, so the
    compat path can't carry her hearing -- this is the one place that calls
    Gemini's own API shape instead. The vocabulary `prompt` rides along as a
    text instruction, which is what Whisper's prompt parameter meant anyway.
    Returns None on any failure, same contract as the Whisper path.
    """
    instruction = (
        "Transcribe the audio. Return only the words spoken, with no commentary."
    )
    if prompt:
        instruction = prompt + "\n\n" + instruction

    data = {
        "contents": [{
            "parts": [
                {"text": instruction},
                {"inline_data": {
                    "mime_type": "audio/wav",
                    "data": base64.b64encode(_wav_bytes(audio_i16, sample_rate)).decode("ascii"),
                }},
            ]
        }],
        "generationConfig": {
            # A transcription, not a chat: no reason for the model to think,
            # and no reason to keep going past the words it heard.
            "temperature": 0.0,
            "maxOutputTokens": 512,
        },
    }
    try:
        resp = requests.post(
            f"{_GEMINI_NATIVE_URL}/models/{OPENAI_TRANSCRIBE_MODEL}:generateContent",
            headers={"x-goog-api-key": OPENAI_API_KEY},
            json=data,
            timeout=OPENAI_TIMEOUT,
        )
        resp.raise_for_status()
        parts = (resp.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
    except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
        print(f"[voice] transcription failed: {exc}")
        return None
    return text or None


def transcribe(audio_i16, sample_rate: int = 16000, prompt: str | None = None) -> str | None:
    """One recorded utterance -> text.

    Gemini goes through its native generateContent API (see _gemini_transcribe);
    everywhere else speaks the OpenAI Whisper shape. `prompt` is the short
    vocabulary hint (names that would otherwise be spelled phonetically).
    Returns None on any failure -- a companion that hears nothing this once is
    better than one that raises mid-conversation.
    """
    if not OPENAI_API_KEY:
        print("[voice] no API key set -- can't transcribe")
        return None

    if USING_GEMINI_STT:
        return _gemini_transcribe(audio_i16, sample_rate, prompt)

    data = {"model": OPENAI_TRANSCRIBE_MODEL, "language": "en", "response_format": "text"}
    if prompt:
        data["prompt"] = prompt

    try:
        resp = requests.post(
            _openai_url("audio/transcriptions"),
            headers=_auth_headers(),
            data=data,
            files={"file": ("speech.wav", _wav_bytes(audio_i16, sample_rate), "audio/wav")},
            timeout=OPENAI_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[voice] transcription failed: {exc}")
        return None

    return (resp.text or "").strip() or None
