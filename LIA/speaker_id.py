"""
Recognises whether whoever's talking sounds like the enrolled voice.

Say "Hey Lia, it's Wade" a few times and she builds a voiceprint -- a 512
number vector representing vocal characteristics, via a small local model
(3D-Speaker's CAM++, run through sherpa-onnx / onnxruntime, CPU only, no
PyTorch). Every later utterance is compared against that profile with cosine
similarity, the same technique memory.py already uses for text, just applied
to raw audio instead.

This is a soft comfort signal, not a lock. It runs on a laptop microphone in
an ordinary room, not a security device, so treat "doesn't match" as "be a
little more careful" -- not "refuse to engage." Enrollment quality (and real
accuracy) can only really be judged once there's actual voice data from real
use; SPEAKER_MATCH_THRESHOLD is deliberately easy to retune in config.py.
"""

import numpy as np

import db
from config import SPEAKER_MODEL_PATH, SPEAKER_MATCH_THRESHOLD, SPEAKER_ENROLL_TARGET

_extractor = None
_unavailable = False


def _ensure_extractor():
    global _extractor, _unavailable
    if _extractor is not None or _unavailable:
        return _extractor
    try:
        import sherpa_onnx

        config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(SPEAKER_MODEL_PATH), num_threads=1, provider="cpu"
        )
        _extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)
    except Exception as exc:
        print(f"[speaker_id] unavailable: {exc}")
        _unavailable = True
    return _extractor


def available() -> bool:
    return _ensure_extractor() is not None


def embed(audio_i16: np.ndarray, sample_rate: int = 16000) -> np.ndarray | None:
    """A voiceprint for one utterance, or None if extraction failed."""
    extractor = _ensure_extractor()
    if extractor is None or audio_i16 is None or len(audio_i16) == 0:
        return None
    try:
        audio_f32 = audio_i16.astype("float32") / 32768.0
        stream = extractor.create_stream()
        stream.accept_waveform(sample_rate=sample_rate, waveform=audio_f32)
        stream.input_finished()
        return np.array(extractor.compute(stream))
    except Exception:
        return None


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0


def is_enrolled() -> bool:
    return db.get_voice_profile() is not None


def enrollment_progress() -> int:
    """How many samples have folded into the profile so far."""
    profile = db.get_voice_profile()
    return profile["sample_count"] if profile else 0


def is_stable() -> bool:
    return enrollment_progress() >= SPEAKER_ENROLL_TARGET


def enroll(audio_i16: np.ndarray, sample_rate: int = 16000) -> bool:
    """Fold one more sample into the profile -- averaged in, not replaced, so
    it becomes more representative rather than jumping around between takes."""
    embedding = embed(audio_i16, sample_rate)
    if embedding is None:
        return False

    existing = db.get_voice_profile()
    if existing is None:
        db.save_voice_profile(embedding.tolist(), 1)
    else:
        old = np.array(existing["embedding"])
        n = existing["sample_count"]
        averaged = (old * n + embedding) / (n + 1)
        db.save_voice_profile(averaged.tolist(), n + 1)
    return True


def forget_profile():
    db.clear_voice_profile()


def confidence(audio_i16: np.ndarray, sample_rate: int = 16000) -> float | None:
    """Similarity to the enrolled voice, 0..1. None if there's nothing to
    compare against yet, or extraction failed -- callers should treat that as
    "can't tell," never as "not a match.\""""
    profile = db.get_voice_profile()
    if profile is None:
        return None
    embedding = embed(audio_i16, sample_rate)
    if embedding is None:
        return None
    return _cosine(np.array(profile["embedding"]), embedding)


def sounds_enrolled(audio_i16: np.ndarray, sample_rate: int = 16000) -> bool | None:
    """True/False against the threshold, or None if undecidable (not enrolled
    yet, or the embedding failed) -- distinct from False on purpose, so a
    caller never treats "unknown" the same as "confirmed someone else.\""""
    score = confidence(audio_i16, sample_rate)
    if score is None:
        return None
    return score >= SPEAKER_MATCH_THRESHOLD
