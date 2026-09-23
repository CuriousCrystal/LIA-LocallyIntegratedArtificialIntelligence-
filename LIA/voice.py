"""
Voice for Lia -- speaking (TTS) and listening (STT).

Speaking is local only: Piper neural TTS from the .onnx files in voices/.
There is no cloud voice and no Windows SAPI fallback any more -- both were
removed with the rest of her cloud-control features, and one honest failure
("couldn't load a voice") beats two code paths where one ever drifts.

Listening is a hosted API (llm.transcribe). Everything here degrades
gracefully: a failed transcription is treated as silence -- a companion that
goes quiet beats one that dies mid-sentence.

Voice activity detection (pysilero-vad) stays on this machine: it decides when
you have stopped talking, before any audio is sent anywhere.

Adding your own Piper voice
---------------------------
Drop a matching pair into LIA/voices/:

    voices/my_voice.onnx
    voices/my_voice.onnx.json

then set VOICE_NAME = "my_voice" in config.py (or "auto" to pick up whatever is
there).
"""

import collections
import llm
import queue
import re
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
    VAD_THRESHOLD,
    VAD_SILENCE_SECONDS,
    VAD_MIN_SPEECH_SECONDS,
    VAD_MAX_SECONDS,
)

SAMPLE_RATE_IN = 16000  # mic capture rate, and what the transcription API is sent


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


def _echoes_hint(text: str, hint: str) -> bool:
    """Is this transcript just the vocabulary hint handed back?

    Every word of it drawn from the hint, and no longer than the hint itself.
    Deliberately strict on both counts: "Lia" alone is a real thing to say, so
    a short utterance made only of hint words has to also be short enough to
    plausibly *be* the hint before it's thrown away.
    """
    said = _WORDS_ONLY.findall(text.lower())
    prompt = set(_WORDS_ONLY.findall(hint.lower()))
    if not said or not prompt:
        return False
    if len(said) < 4:
        return False  # too short to be the hint; let the wake word decide
    return all(word in prompt for word in said)


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


def _resolve_voice_file() -> Path | None:
    """Pick which .onnx Piper voice to load, honouring VOICE_NAME."""
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
    """Local neural TTS. Free, runs on the machine, flat delivery. Takes the
    .onnx voice files in voices/."""

    def __init__(self, model_path):
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


def _build_engine():
    """The local Piper voice, or None if the machine can't speak at all."""
    model_path = _resolve_voice_file()
    if model_path is not None:
        try:
            return PiperEngine(model_path)
        except Exception as exc:
            print(f"[voice] couldn't load {model_path.name}: {exc}")
    return None


# --------------------------------------------------------------- speaker ---

class Speaker:
    """Speaks queued text on a background thread.

    A hosted reply can stream faster than Piper speaks, so the first sentence
    starts while the rest is still arriving.
    """

    def __init__(self, enabled: bool = SPEAK_ENABLED):
        self.enabled = enabled
        self._engine = None
        self._queue: queue.Queue = queue.Queue()
        self._thread = None
        self._error_shown = False
        self._speaking = False

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

    def _worker(self):
        while True:
            text = self._queue.get()
            if text is None:
                self._speaking = False
                break
            try:
                self._speaking = True
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
        """Throw away anything not yet spoken."""
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
    """Speech recognition -- a hosted API (OPENAI_TRANSCRIBE_MODEL, via
    llm.transcribe). The recorded utterance is sent as a WAV and comes back as
    text.

    The only model that loads on this machine is the voice activity detector,
    which decides when you have stopped talking. Nothing else here needs
    warming up.
    """

    def __init__(self):
        self._vad = None

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
        """Load the VAD now, so the first thing you say isn't missed.

        Transcription is a hosted call with nothing to preload; this just brings
        up the one local model.
        """
        return self._ensure_vad()

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
        `on_speech_start` fires as soon as speech begins.
        """
        if not self._ensure_vad():
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

        `hint` is a short line of vocabulary the recogniser should expect --
        names it would otherwise spell phonetically ("Lia" as "Leah").
        """
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
        text = llm.transcribe(audio, SAMPLE_RATE_IN, prompt=hint)
        print(" " * 40, end="\r", flush=True)

        if not text:
            return None

        # The recogniser hands the prompt back verbatim when the audio is mostly
        # silence -- it has nothing to transcribe and the prompt is the likeliest
        # continuation. Found in her real memory: "This is a conversation with
        # Lia" was stored as a thing Wade had said, and she later quoted it back
        # at him as his own words. The hint is vocabulary, never speech.
        if hint and _echoes_hint(text, hint):
            return None
        return text
