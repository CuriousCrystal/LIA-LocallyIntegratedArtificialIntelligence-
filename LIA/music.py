"""Her own music -- files you give her, played by number.

Separate from media.py on purpose. That controls whatever *something else* is
already playing, through Windows' transport controls: a remote, unable to start
a track from nothing. This is the opposite -- a small collection she owns and
can actually start, stop and pick from, with no browser tab or Spotify involved.

Playback goes through the same audio stack as her voice (sounddevice, with
soundfile decoding), so nothing external opens and she can stop a track
mid-way. Decoded on a background thread and pushed out in blocks rather than
loaded whole: a five-minute song is around 50MB once decoded to raw samples,
and the pause before playback while that happened was audible.

She never plays over herself -- speaking ducks the music rather than talking
into it, since two voices at once is worse than either.
"""

import threading
from pathlib import Path

import numpy as np

from config import MUSIC_DIR, MUSIC_DUCK_VOLUME

SUPPORTED = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aiff"}

_BLOCK = 2048

_lock = threading.Lock()
_stream = None
_stop = threading.Event()
_thread: threading.Thread | None = None
_current: Path | None = None
_ducked = False


def available() -> bool:
    try:
        import sounddevice  # noqa: F401
        import soundfile  # noqa: F401
    except ImportError:
        return False
    return True


def tracks() -> list[Path]:
    """Everything she has, in a stable order so "number 3" means the same
    thing tomorrow as it does today."""
    folder = Path(MUSIC_DIR)
    if not folder.is_dir():
        return []
    return sorted(
        (p for p in folder.rglob("*") if p.suffix.lower() in SUPPORTED and p.is_file()),
        key=lambda p: p.name.lower(),
    )


def describe(path: Path) -> str:
    """A readable name -- the filename without its extension, tidied."""
    return path.stem.replace("_", " ").strip()


def find(number: int) -> Path | None:
    """The nth track, counting from 1 the way people do."""
    listing = tracks()
    if 1 <= number <= len(listing):
        return listing[number - 1]
    return None


def search(name: str) -> Path | None:
    """Best match by name, for "play Fireflies" rather than a number."""
    wanted = name.lower().strip()
    if not wanted:
        return None
    listing = tracks()
    for path in listing:  # exact stem first, so an exact name always wins
        if path.stem.lower() == wanted:
            return path
    for path in listing:
        if wanted in path.stem.lower():
            return path
    return None


def now_playing() -> str | None:
    return describe(_current) if (_current and is_playing()) else None


def is_playing() -> bool:
    return _thread is not None and _thread.is_alive()


def stop():
    """Stop playback and wait for the audio device to actually close."""
    global _thread, _current
    _stop.set()
    thread = _thread
    if thread is not None and thread.is_alive() and thread is not threading.current_thread():
        thread.join(timeout=3)
    _thread = None
    _current = None


def duck(quieter: bool):
    """Drop the music under her voice, rather than stopping it.

    Called around speech: interrupting a song to answer a question and then
    leaving it stopped is not what anyone means by "can you turn that down".
    """
    global _ducked
    _ducked = quieter


def play(path: Path) -> bool:
    """Start a track, replacing whatever was playing. False if it won't open."""
    global _thread, _current

    if not available() or not path.exists():
        return False

    import soundfile as sf

    try:
        sf.SoundFile(str(path)).close()  # fail fast on an unreadable file
    except Exception:
        return False

    stop()
    _stop.clear()
    _current = path

    def run():
        import sounddevice as sd
        import soundfile as sf

        try:
            with sf.SoundFile(str(path)) as audio:
                with sd.OutputStream(samplerate=audio.samplerate,
                                     channels=audio.channels,
                                     dtype="float32") as out:
                    while not _stop.is_set():
                        block = audio.read(_BLOCK, dtype="float32")
                        if not len(block):
                            break
                        if block.ndim == 1:
                            block = block.reshape(-1, 1)
                        if _ducked:
                            block = block * MUSIC_DUCK_VOLUME
                        out.write(np.ascontiguousarray(block))
        except Exception:
            pass  # a device that disappears mid-song shouldn't take her down

    with _lock:
        _thread = threading.Thread(target=run, daemon=True)
        _thread.start()
    return True
