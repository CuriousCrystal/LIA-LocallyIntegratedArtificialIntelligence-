"""
The system volume.

There was media control here too -- Windows' System Media Transport Controls,
the thing behind your keyboard's media keys -- letting her play and pause
whatever Spotify or a browser tab already had loaded. It was removed by
request. It could only ever operate someone else's player and never start
anything, which made it a confusing sibling to music.py, where she plays her
own files and genuinely can.

Volume uses the Windows Core Audio API (via pycaw), talking to the
system's master volume directly. Simulating the physical volume-up/down key
presses was tried first and rejected -- verified live that it silently did
nothing (volume unchanged, no error raised), almost certainly because a
simulated key needs a foregrounded window to route to. Setting the level
directly has no such dependency.

Entirely local -- nothing here touches the internet. If nothing is playing, or
there's no active media session, every function fails quietly and returns None
or False rather than raising.
"""

try:
    from pycaw.pycaw import AudioUtilities as _AudioUtilities
    _VOLUME_AVAILABLE = True
except ImportError:
    _VOLUME_AVAILABLE = False


def volume_available() -> bool:
    return _VOLUME_AVAILABLE


def _note(what: str, exc: Exception):
    """Say why something failed, instead of failing silently.

    Every function here returns None/False on error by design, so the caller
    can degrade gracefully -- but swallowing the reason entirely made a real
    bug (COM uninitialised on this thread in the packaged build) look
    identical to "nothing is playing", and cost a testing session to find.
    """
    print(f"  [media: {what} failed -- {type(exc).__name__}: {exc}]")


def _volume_endpoint():
    # COM has to be initialised on whichever thread touches it. The main
    # thread of the packaged app doesn't do that on its own the way a plain
    # python process does, so pycaw raised CoInitialize-not-called and every
    # volume call silently returned None -- working from source, broken as an
    # .exe. Safe to call repeatedly; it refcounts per thread.
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass
    return _AudioUtilities.GetSpeakers().EndpointVolume


def get_volume() -> int | None:
    """Current system volume, 0-100, or None if unavailable."""
    if not _VOLUME_AVAILABLE:
        return None
    try:
        return round(_volume_endpoint().GetMasterVolumeLevelScalar() * 100)
    except Exception as exc:
        _note("reading the volume", exc)
        return None


def set_volume(percent: int) -> bool:
    """Set system volume directly to an exact 0-100 level."""
    if not _VOLUME_AVAILABLE:
        return False
    try:
        level = max(0, min(100, percent)) / 100
        _volume_endpoint().SetMasterVolumeLevelScalar(level, None)
        return True
    except Exception as exc:
        _note("setting the volume", exc)
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
    except Exception as exc:
        _note("muting", exc)
        return False
