"""
Controls whatever is currently playing on Windows.

Uses Windows' own System Media Transport Controls (SMTC) -- the same system
behind the media flyout next to the volume icon, and your keyboard's media
keys. That means this works with whatever app actually has something playing
(Spotify, a browser tab, Windows Media Player, the Movies & TV app) without
Lia needing to know or care which one it is.

Entirely local -- nothing here touches the internet. If nothing is playing, or
there's no active media session, every function fails quietly and returns None
or False rather than raising.
"""

import asyncio

try:
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as _Manager,
    )
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as _PlaybackStatus,
    )
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


def available() -> bool:
    return _AVAILABLE


def _run(coro):
    """winsdk's API is async; every call here is a single quick round-trip."""
    try:
        return asyncio.run(coro)
    except Exception:
        return None


async def _session():
    manager = await _Manager.request_async()
    return manager.get_current_session()


def now_playing() -> dict | None:
    """{'title', 'artist', 'playing': bool}, or None if nothing is active."""
    if not _AVAILABLE:
        return None

    async def go():
        session = await _session()
        if session is None:
            return None
        info = await session.try_get_media_properties_async()
        status = session.get_playback_info().playback_status
        return {
            "title": info.title or "",
            "artist": info.artist or "",
            "playing": status == _PlaybackStatus.PLAYING,
        }

    return _run(go())


def _control(method_name: str) -> bool:
    """Call a play/pause/skip method on whatever session is active."""
    if not _AVAILABLE:
        return False

    async def go():
        session = await _session()
        if session is None:
            return False
        method = getattr(session, method_name)
        return bool(await method())

    result = _run(go())
    return bool(result)


def play() -> bool:
    return _control("try_play_async")


def pause() -> bool:
    return _control("try_pause_async")


def toggle() -> bool:
    """Play if paused, pause if playing. Falls back to play if state is unknown."""
    info = now_playing()
    if info and info["playing"]:
        return pause()
    return play()


def next_track() -> bool:
    return _control("try_skip_next_async")


def previous_track() -> bool:
    return _control("try_skip_previous_async")
