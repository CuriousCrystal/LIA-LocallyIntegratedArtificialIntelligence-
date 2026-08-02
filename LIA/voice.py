"""
Voice for Lia -- speaking (TTS) and listening (STT).

Everything here degrades gracefully. If a dependency is missing or a model
fails to load, Lia falls back to plain text instead of crashing: a companion
that goes quiet is better than one that dies mid-sentence.

Adding your own voice
---------------------
Drop a Piper voice into LIA/voices/ as a matching pair:

    voices/my_voice.onnx
    voices/my_voice.onnx.json

Then set VOICE_NAME = "my_voice" in config.py (or leave it on "auto" to pick
up whatever is in the folder). Nothing else needs to change.
"""

import collections
import queue
import re
import sys
import threading
from pathlib import Path

from config import (
    SPEAK_ENABLED,
    VOICES_DIR,
    VOICE_NAME,
    VOICE_LENGTH_SCALE,
    VOICE_VOLUME,
    VOICE_NOISE_SCALE,
    VOICE_NOISE_W,
    SYSTEM_VOICE_MATCH,
    WHISPER_MODEL,
    VAD_THRESHOLD,
    VAD_SILENCE_SECONDS,
    VAD_MIN_SPEECH_SECONDS,
    VAD_MAX_SECONDS,
)

SAMPLE_RATE_IN = 16000  # what Whisper expects


# --------------------------------------------------------------- helpers ---

def _play(audio, sample_rate):
    import sounddevice as sd

    sd.play(audio, sample_rate)
    try:
        sd.wait()
    except KeyboardInterrupt:
        sd.stop()
        raise


# Small models like to emit stage directions -- "*soft, gentle tone*" -- and a
# TTS engine will happily read the asterisks out loud.
_STAGE_DIRECTION = re.compile(r"\*[^*]{0,80}\*")
_MARKDOWN = re.compile(r"[*_`#]")
_WORDS_ONLY = re.compile(r"[a-z']+")


def speakable(text: str) -> str:
    """Strip anything that shouldn't be read aloud."""
    text = _STAGE_DIRECTION.sub(" ", text)
    text = _MARKDOWN.sub("", text)
    return " ".join(text.split())


# "hey lia", "ok lia," -- strip the summons, keep the sentence.
_WAKE_PREFIX = re.compile(
    r"^\W*(?:hey|hi|hello|ok|okay|yo|um|uh)?[\s,]*(?:{names})\b[\s,.:;!?-]*",
    re.IGNORECASE,
)
_WORDS = re.compile(r"[a-z']+")


def detect_wake(text: str, names) -> tuple[bool, str]:
    """Was she addressed by name, and what's left once the name is removed?

    The name counts anywhere in the sentence -- "are you there, Lia?" is being
    spoken to just as much as "Lia, are you there?" -- but it's only stripped
    from the front, where it isn't part of the sentence.
    """
    spoken = set(_WORDS.findall(text.lower()))
    if not spoken.intersection(n.lower() for n in names):
        return False, text

    pattern = _WAKE_PREFIX.pattern.format(names="|".join(re.escape(n) for n in names))
    stripped = re.sub(pattern, "", text, count=1, flags=re.IGNORECASE).strip()
    return True, (stripped or text)


def available_voices() -> list[str]:
    """Names of Piper voices sitting in the voices folder."""
    if not Path(VOICES_DIR).is_dir():
        return []
    return sorted(p.stem for p in Path(VOICES_DIR).glob("*.onnx"))


def _resolve_voice_file() -> Path | None:
    """Pick which .onnx to load, honouring VOICE_NAME."""
    if VOICE_NAME == "system":
        return None

    voices_dir = Path(VOICES_DIR)
    if not voices_dir.is_dir():
        return None

    if VOICE_NAME != "auto":
        candidate = voices_dir / f"{VOICE_NAME}.onnx"
        if candidate.exists():
            return candidate
        print(f"[voice] '{VOICE_NAME}' not found in {voices_dir}, falling back.")

    found = sorted(voices_dir.glob("*.onnx"))
    return found[0] if found else None


# --------------------------------------------------------------- engines ---

class PiperEngine:
    """Local neural TTS. This is the one that takes your own voice files."""

    def __init__(self, model_path: Path):
        from piper import PiperVoice, SynthesisConfig

        self.name = model_path.stem
        self._voice = PiperVoice.load(model_path)
        self._syn_config = SynthesisConfig(
            length_scale=VOICE_LENGTH_SCALE,
            volume=VOICE_VOLUME,
            noise_scale=VOICE_NOISE_SCALE,
            noise_w_scale=VOICE_NOISE_W,
        )
        self.sample_rate = self._voice.config.sample_rate

    def say(self, text: str):
        import numpy as np

        chunks = [
            c.audio_int16_array
            for c in self._voice.synthesize(text, syn_config=self._syn_config)
        ]
        if chunks:
            _play(np.concatenate(chunks), self.sample_rate)


class SystemEngine:
    """Built-in Windows SAPI voice. Always available, no downloads."""

    def __init__(self):
        import pyttsx3

        self._engine = pyttsx3.init()
        self.name = "system"

        if SYSTEM_VOICE_MATCH:
            for v in self._engine.getProperty("voices"):
                if SYSTEM_VOICE_MATCH.lower() in v.name.lower():
                    self._engine.setProperty("voice", v.id)
                    self.name = v.name
                    break

        # SAPI defaults to ~200 wpm, which reads as brisk. Lia is not brisk.
        self._engine.setProperty("rate", int(200 / VOICE_LENGTH_SCALE) - 20)

    def say(self, text: str):
        self._engine.say(text)
        self._engine.runAndWait()


def _build_engine():
    """Best available engine, or None if the machine can't speak at all."""
    model_path = _resolve_voice_file()

    if model_path is not None:
        try:
            return PiperEngine(model_path)
        except Exception as exc:
            print(f"[voice] couldn't load {model_path.name}: {exc}")

    try:
        return SystemEngine()
    except Exception as exc:
        print(f"[voice] no speech engine available: {exc}")
        return None


# --------------------------------------------------------------- speaker ---

class Speaker:
    """Speaks queued text on a background thread.

    Generation on a 3B model is slow, so we start speaking the first sentence
    while the rest of the reply is still being generated.
    """

    def __init__(self, enabled: bool = SPEAK_ENABLED):
        self.enabled = enabled
        self._engine = None
        self._queue: queue.Queue = queue.Queue()
        self._thread = None
        self._error_shown = False
        self._speaking = False
        # What she is saying right now, plus what she just said -- used to tell
        # her own voice coming back through the speakers from you talking.
        self._recent = collections.deque(maxlen=3)

    @property
    def voice_name(self) -> str:
        if self._engine is None:
            return "not loaded"
        return self._engine.name

    def _ensure_started(self) -> bool:
        if not self.enabled:
            return False
        if self._engine is None:
            self._engine = _build_engine()
            if self._engine is None:
                self.enabled = False
                return False
        if self._thread is None:
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()
        return True

    def is_busy(self) -> bool:
        """True while there's audio playing or queued."""
        return self._speaking or not self._queue.empty()

    def sounds_like_me(self, heard: str, ratio: float = 0.5) -> bool:
        """Is this the tail of her own voice, picked up through the speakers?

        Compares against what she is saying and just said. Cheap, and it makes
        interrupting her workable without headphones.
        """
        words = set(_WORDS_ONLY.findall(heard.lower()))
        if not words:
            return True

        mine = set()
        for line in list(self._recent):
            mine.update(_WORDS_ONLY.findall(line.lower()))
        if not mine:
            return False

        overlap = len(words & mine) / len(words)
        return overlap >= ratio

    def _worker(self):
        while True:
            text = self._queue.get()
            if text is None:
                self._speaking = False
                break
            try:
                self._speaking = True
                self._recent.append(text)
                self._engine.say(text)
            except KeyboardInterrupt:
                pass
            except Exception as exc:
                if not self._error_shown:
                    print(f"\n[voice] playback failed: {exc}")
                    self._error_shown = True
            finally:
                self._speaking = False
                self._queue.task_done()

    def say(self, text: str):
        text = speakable(text)
        if not text or not self._ensure_started():
            return
        self._queue.put(text)

    def wait(self):
        """Block until everything queued has finished playing."""
        if self._thread is not None:
            self._queue.join()

    def drop_pending(self):
        """Throw away anything not yet spoken (used when you interrupt her)."""
        try:
            while True:
                self._queue.get_nowait()
                self._queue.task_done()
        except queue.Empty:
            pass
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:
            pass

    def preload(self):
        """Load the engine now rather than on the first reply."""
        self._ensure_started()


# ----------------------------------------------------- sentence chunking ---

_SENTENCE_END = re.compile(r"[.!?…]['\")\]]*\s")


class SentenceBuffer:
    """Turns a token stream into speakable sentences.

    Very short fragments get held back -- feeding "Hi." and "Oh?" to a TTS
    engine one at a time sounds clipped and robotic.
    """

    MIN_CHARS = 25

    def __init__(self):
        self._buf = ""

    def feed(self, token: str) -> list[str]:
        self._buf += token
        out = []
        while True:
            match = None
            for m in _SENTENCE_END.finditer(self._buf):
                if m.end() >= self.MIN_CHARS:
                    match = m
                    break
            if match is None:
                break
            sentence, self._buf = self._buf[: match.end()], self._buf[match.end():]
            out.append(sentence.strip())
        return out

    def flush(self) -> str:
        rest, self._buf = self._buf.strip(), ""
        return rest


# -------------------------------------------------------------- listening ---

class Listener:
    """Push-to-talk speech recognition via faster-whisper (CPU)."""

    def __init__(self, model_size: str = WHISPER_MODEL):
        self.model_size = model_size
        self._model = None
        self._vad = None

    def _ensure_model(self) -> bool:
        if self._model is not None:
            return True
        try:
            from faster_whisper import WhisperModel

            print(f"  ...loading speech recognition ({self.model_size})".ljust(48), end="\r", flush=True)
            # int8 on CPU keeps the GPU free for Ollama.
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
            print(" " * 48, end="\r", flush=True)
            return True
        except Exception as exc:
            print(f"[voice] speech recognition unavailable: {exc}")
            return False

    def _record(self):
        import numpy as np
        import sounddevice as sd

        frames = []

        def callback(indata, _frames, _time, _status):
            frames.append(indata.copy())

        with sd.InputStream(
            samplerate=SAMPLE_RATE_IN, channels=1, dtype="int16", callback=callback
        ):
            print("  [recording -- press Enter to stop]", end="", flush=True)
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                pass

        if not frames:
            return None
        return np.concatenate(frames, axis=0).flatten()

    def warm_up(self) -> bool:
        """Load the models now, so the first thing you say isn't missed."""
        return self._ensure_model() and self._ensure_vad()

    def _ensure_vad(self) -> bool:
        if self._vad is not None:
            return True
        try:
            from pysilero_vad import SileroVoiceActivityDetector

            self._vad = SileroVoiceActivityDetector()
            return True
        except Exception as exc:
            print(f"[voice] open mic unavailable ({exc}) -- using push-to-talk.")
            return False

    def _record_until_silence(self, abort=None, on_speech_start=None):
        """Wait for speech, capture it, stop when they stop talking.

        Returns (audio, reason). reason is "speech" if we got something,
        "abort" if the caller interrupted, "quiet" if nobody spoke.
        """
        import numpy as np
        import sounddevice as sd

        if abort is not None and abort():
            return None, "abort"

        chunk = self._vad.chunk_samples()          # 512 samples = 32ms at 16kHz
        per_chunk = chunk / SAMPLE_RATE_IN
        silence_needed = int(VAD_SILENCE_SECONDS / per_chunk)
        min_speech = int(VAD_MIN_SPEECH_SECONDS / per_chunk)
        max_chunks = int(VAD_MAX_SECONDS / per_chunk)
        # Keep a moment of audio from before speech was detected, or the first
        # syllable gets clipped off every single time.
        preroll = collections.deque(maxlen=int(0.4 / per_chunk))

        speaking = False
        silent_run = 0
        frames = []
        announced = False

        with sd.InputStream(
            samplerate=SAMPLE_RATE_IN, channels=1, dtype="int16", blocksize=chunk
        ) as stream:
            for _ in range(max_chunks + int(60 / per_chunk)):
                if abort is not None and abort():
                    return None, "abort"

                block, _overflowed = stream.read(chunk)
                if len(block) < chunk:
                    continue

                is_speech = self._vad(block.tobytes()) >= VAD_THRESHOLD

                if not speaking:
                    preroll.append(block.copy())
                    if is_speech:
                        speaking = True
                        frames = list(preroll)
                    continue

                frames.append(block.copy())
                if not announced:
                    print("  [listening...]".ljust(40), end="\r", flush=True)
                    announced = True
                    if on_speech_start is not None:
                        on_speech_start()

                silent_run = 0 if is_speech else silent_run + 1
                if silent_run >= silence_needed:
                    break
                if len(frames) >= max_chunks:
                    break

        print(" " * 40, end="\r", flush=True)

        if not speaking:
            return None, "quiet"
        if len(frames) - silent_run < min_speech:
            return None, "quiet"
        return np.concatenate(frames, axis=0).flatten(), "speech"

    def listen_open(self, hint: str | None = None, abort=None, on_speech_start=None) -> str | None:
        """Wait for them to speak, then transcribe. No key press involved.

        `abort` is polled between 32ms chunks so a keystroke can take over.
        `on_speech_start` fires as soon as speech begins, which is the earliest
        useful moment to start warming the language model.
        """
        if not self._ensure_model() or not self._ensure_vad():
            return None

        try:
            audio, reason = self._record_until_silence(abort=abort, on_speech_start=on_speech_start)
        except Exception as exc:
            print(f"[voice] microphone unavailable: {exc}")
            return None

        if reason != "speech" or audio is None:
            return None
        return self._transcribe(audio, hint)

    def listen(self, hint: str | None = None) -> str | None:
        """Record until Enter, then transcribe. None if nothing was heard.

        `hint` is a short line of vocabulary Whisper should expect -- names it
        would otherwise spell phonetically ("Lia" as "Leah", "Anaya" as "Ania").
        """
        if not self._ensure_model():
            return None

        try:
            audio = self._record()
        except Exception as exc:
            print(f"[voice] microphone unavailable: {exc}")
            return None

        if audio is None or len(audio) < SAMPLE_RATE_IN // 4:
            return None

        return self._transcribe(audio, hint)

    def _transcribe(self, audio, hint: str | None) -> str | None:
        print("  ...transcribing".ljust(40), end="\r", flush=True)
        audio_f32 = audio.astype("float32") / 32768.0
        segments, _ = self._model.transcribe(
            audio_f32, beam_size=1, language="en", initial_prompt=hint
        )
        text = " ".join(s.text for s in segments).strip()
        print(" " * 40, end="\r", flush=True)
        return text or None
