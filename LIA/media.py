"""
Controls whatever is currently playing on Windows, and the system volume.

Playback uses Windows' own System Media Transport Controls (SMTC) -- the same
system behind the media flyout next to the volume icon, and your keyboard's
media keys. That means it works with whatever app actually has something
playing (Spotify, a browser tab, Windows Media Player) without Lia needing to
know or care which one it is. It is a remote control, not a jukebox -- it
cannot start a track from nothing if no app has anything loaded.

Volume is separate: the Windows Core Audio API (via pycaw), talking to the
system's master volume directly. Simulating the physical volume-up/down key
presses was tried first and rejected -- verified live that it silently did
nothing (volume unchanged, no error raised), almost certainly because a
simulated key needs a foregrounded window to route to. Setting the level
directly has no such dependency.

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

try:
    from pycaw.pycaw import AudioUtilities as _AudioUtilities
    _VOLUME_AVAILABLE = True
except ImportError:
    _VOLUME_AVAILABLE = False


def available() -> bool:
    return _AVAILABLE


def volume_available() -> bool:
    return _VOLUME_AVAILABLE


def _volume_endpoint():
    return _AudioUtilities.GetSpeakers().EndpointVolume


def get_volume() -> int | None:
    """Current system volume, 0-100, or None if unavailable."""
    if not _VOLUME_AVAILABLE:
        return None
    try:
        return round(_volume_endpoint().GetMasterVolumeLevelScalar() * 100)
    except Exception:
        return None


def set_volume(percent: int) -> bool:
    """Set system volume directly to an exact 0-100 level."""
    if not _VOLUME_AVAILABLE:
        return False
    try:
        level = max(0, min(100, percent)) / 100
        _volume_endpoint().SetMasterVolumeLevelScalar(level, None)
        return True
    except Exception:
        return False


def adjust_volume(delta_percent: int) -> int | None:
    """Move the volume up or down by delta_percent, returning the new level."""
    current = get_volume()
    if current is None:
        return None
    new_level = max(0, min(100, current + delta_percent))
    return new_level if set_volume(new_level) else None


def mute(should_mute: bool = True) -> bool:
    if not _VOLUME_AVAILABLE:
        return False
    try:
        _volume_endpoint().SetMute(should_mute, None)
        return True
    except Exception:
        return False


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
