"""
The one deliberate exception to Lia running fully offline.

Everything else in this project works with no internet connection at all.
This file is the whole of what doesn't, and it's narrow on purpose:

  - weather, from a live source, no API key needed
  - one factual question, answered online, only when you explicitly ask
    her to look something up

Ordinary conversation never touches this module and never leaves the machine.
If there's no connection, every function here fails quietly and main.py falls
back to saying so plainly -- the same honest pattern used when Ollama itself
isn't reachable.

Two lookup providers, and they are not equivalent:

  - Groq is a fast host for open models (Llama, here a much bigger one than
    the local 3B) -- not a search engine. A plain chat-completions call to it
    has no more access to today's news than the local model does; it just
    guesses more fluently.
  - OpenRouter, with OPENROUTER_ONLINE on, appends ":online" to the model
    name, which makes OpenRouter itself run a real web search before
    answering. That is a genuine, current answer, not a guess -- so
    look_up() prefers it when both are configured.
"""

import requests

from config import (
    INTERNET_ENABLED,
    GROQ_API_KEY,
    GROQ_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_ONLINE,
    WEATHER_LAT,
    WEATHER_LON,
)

_TIMEOUT = 4


def is_online() -> bool:
    """A fast, cheap connectivity check -- not a guarantee any given API is up."""
    if not INTERNET_ENABLED:
        return False
    try:
        requests.head("https://1.1.1.1", timeout=_TIMEOUT)
        return True
    except requests.RequestException:
        return False


def groq_available() -> bool:
    return INTERNET_ENABLED and bool(GROQ_API_KEY)


def openrouter_available() -> bool:
    return INTERNET_ENABLED and bool(OPENROUTER_API_KEY)


# ------------------------------------------------------------------ weather ---

_WEATHER_CODES = {
    0: "clear skies", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy with frost", 51: "light drizzle", 53: "drizzle",
    55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain",
    67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow",
    77: "snow grains", 80: "light rain showers", 81: "rain showers",
    82: "heavy rain showers", 85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorms", 96: "thunderstorms with hail", 99: "severe thunderstorms",
}


def _locate() -> tuple[float, float, str] | None:
    """Approximate location. Uses your saved coordinates if set, otherwise your
    public IP -- free, no signup, no key. Never sends anything but the request
    itself; nothing personal about you leaves through this path."""
    if WEATHER_LAT is not None and WEATHER_LON is not None:
        return WEATHER_LAT, WEATHER_LON, "your area"
    try:
        r = requests.get("http://ip-api.com/json/", timeout=_TIMEOUT)
        r.raise_for_status()
        d = r.json()
        if d.get("status") == "success":
            return d["lat"], d["lon"], d.get("city", "your area")
    except (requests.RequestException, KeyError, ValueError):
        pass
    return None


def get_weather() -> str | None:
    """A short factual line, e.g. '14°C and overcast in Pune'. None if unreachable.

    Deliberately not routed through an LLM -- Open-Meteo needs no API key and
    is a live source, so there is nothing for a model to guess at here.
    """
    if not INTERNET_ENABLED:
        return None
    loc = _locate()
    if loc is None:
        return None
    lat, lon, place = loc
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lon, "current_weather": True},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        cw = r.json()["current_weather"]
    except (requests.RequestException, KeyError, ValueError):
        return None

    condition = _WEATHER_CODES.get(cw.get("weathercode"), "changeable weather")
    return f"{cw['temperature']}°C and {condition} in {place}"


# --------------------------------------------------------------- ask_groq ---

def ask_groq(question: str) -> str | None:
    """One factual question, answered by Groq. None if unavailable.

    Deliberately sends only the question, not your conversation history or
    anything she remembers about you -- this is the one path in the whole
    project that leaves the machine, and it carries as little as possible.
    """
    if not groq_available():
        return None
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "Answer factually and concisely, two sentences or fewer. "
                                   "If you're not confident or the answer depends on very "
                                   "recent events, say so rather than guessing.",
                    },
                    {"role": "user", "content": question},
                ],
                "max_tokens": 200,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return None


# ---------------------------------------------------------- ask_openrouter ---

def ask_openrouter(question: str) -> str | None:
    """One factual question, answered by OpenRouter. None if unavailable.

    With OPENROUTER_ONLINE on, ":online" makes OpenRouter run a real web
    search first -- this is the one path here that can genuinely answer
    something that happened yesterday, not just guess fluently at it.
    """
    if not openrouter_available():
        return None
    model = f"{OPENROUTER_MODEL}:online" if OPENROUTER_ONLINE else OPENROUTER_MODEL
    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                # OpenRouter's own attribution headers -- not sent anywhere
                # personal, just identifies the app in their dashboard.
                "HTTP-Referer": "https://github.com/lia-companion",
                "X-Title": "Lia",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Answer factually and concisely, two sentences or fewer. "
                                   "If you're not confident, say so rather than guessing.",
                    },
                    {"role": "user", "content": question},
                ],
                "max_tokens": 200,
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return None


# --------------------------------------------------------------- look_up ---

def look_up(question: str) -> tuple[str, bool] | None:
    """One factual question, answered by whichever provider is configured.

    Returns (answer, was_live_search) or None if neither is available or both
    failed. OpenRouter is tried first when its web search is on, since an
    actual search beats a fast guess -- Groq is the fallback, or the only
    option if that's the one key you have.
    """
    if openrouter_available():
        answer = ask_openrouter(question)
        if answer is not None:
            return answer, OPENROUTER_ONLINE
    if groq_available():
        answer = ask_groq(question)
        if answer is not None:
            return answer, False
    return None
