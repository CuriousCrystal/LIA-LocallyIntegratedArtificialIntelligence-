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

Two decoders, tried in that order. libsndfile (via soundfile) handles
everything here except AAC -- it has no decoder for it, so an .m4a would be
listed as a numbered track and then refuse to open, which is worse than not
offering it. PyAV covers that gap and arrives with faster-whisper anyway, so
it costs nothing to fall back to.

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


def _read_soundfile(path: Path):
    """(sample rate, channels, blocks) via libsndfile. Raises if it can't open."""
    import soundfile as sf

    audio = sf.SoundFile(str(path))

    def blocks():
        with audio:
            while True:
                block = audio.read(_BLOCK, dtype="float32")
                if not len(block):
                    return
                yield block.reshape(-1, 1) if block.ndim == 1 else block

    return audio.samplerate, audio.channels, blocks()


def _read_av(path: Path):
    """Same, via PyAV -- the fallback for what libsndfile won't open (.m4a)."""
    import av

    container = av.open(str(path))
    stream = container.streams.audio[0]
    # Anything multi-channel is folded to stereo rather than passed through:
    # 5.1 out of a laptop speaker gains nothing and needs a matching device.
    channels = 2 if stream.channels > 1 else 1
    rate = stream.rate
    # "flt" is packed float32, which is what sounddevice wants -- the planar
    # default would come back as separate per-channel arrays instead.
    resampler = av.audio.resampler.AudioResampler(
        format="flt", layout="stereo" if channels == 2 else "mono", rate=rate)

    def blocks():
        with container:
            for frame in container.decode(audio=0):
                for chunk in resampler.resample(frame):
                    yield chunk.to_ndarray().reshape(-1, channels)

    return rate, channels, blocks()


def _open(path: Path):
    """Whichever decoder can read this file, or None if neither can."""
    for reader in (_read_soundfile, _read_av):
        try:
            return reader(path)
        except Exception:
            continue
    return None


def play(path: Path) -> bool:
    """Start a track, replacing whatever was playing. False if it won't open."""
    global _thread, _current

    if not available() or not path.exists():
        return False

    # Opened before anything is stopped, so a file that turns out to be
    # unreadable leaves the current track playing rather than killing it.
    opened = _open(path)
    if opened is None:
        return False
    rate, channels, blocks = opened

    stop()
    _stop.clear()
    _current = path

    def run():
        import sounddevice as sd

        try:
            with sd.OutputStream(samplerate=rate, channels=channels,
                                 dtype="float32") as out:
                for block in blocks:
                    if _stop.is_set():
                        break
                    if _ducked:
                        block = block * MUSIC_DUCK_VOLUME
                    out.write(np.ascontiguousarray(block))
        except Exception:
            pass  # a device that disappears mid-song shouldn't take her down
        finally:
            blocks.close()  # stopping early still releases the file

    with _lock:
        _thread = threading.Thread(target=run, daemon=True)
        _thread.start()
    return True
