# Lia's voices

Drop voice files in this folder. Lia picks them up on the next start — no code changes.

## Adding your own voice

A voice is a **matching pair** of files with the same base name:

```
voices/my_voice.onnx
voices/my_voice.onnx.json
```

Both are required. The `.json` describes the sample rate and phoneme set; without
it the `.onnx` can't be loaded.

Then either leave `VOICE_NAME = "auto"` in [`config.py`](../config.py) (uses the first
voice it finds, alphabetically) or name it explicitly:

```python
VOICE_NAME = "my_voice"
```

Run `/voices` inside a chat to see what Lia can currently find.

## Where to get more voices

These are [Piper](https://github.com/OHF-voice/piper1-gpl) voices. Around a hundred
are published across many languages, in `low` / `medium` / `high` quality tiers.
`medium` is the sweet spot — `high` is noticeably slower to synthesize and the
quality gain is small at conversational length.

To fetch one:

```powershell
cd d:\Visuals\AI
python -c "from pathlib import Path; from piper.download_voices import download_voice; download_voice('en_GB-jenny_dioco-medium', Path('LIA/voices'))"
```

Swap in any voice name from the [voice samples page](https://rhasspy.github.io/piper-samples/).
The download is a few tens of MB and, like everything else in Lia, is stored locally
and runs offline afterwards.

## Cloning a specific person's voice

Piper voices are *trained*, not cloned — you can't hand it a ten-second clip and get
that person back. Cloning from a short sample needs a different class of model
(XTTS, F5-TTS, Chatterbox), which is much heavier and would contend with Ollama for
your 4GB of VRAM.

If you want that later, the seam is already here: add a new engine class in
[`voice.py`](../voice.py) alongside `PiperEngine` — anything with a `.say(text)`
method and a `.name` works — and have `_build_engine()` return it.

**One caution:** cloning someone's voice from a recording is something to only do
with that person's knowledge and agreement. It's their voice, not just audio.

## Falling back to a system voice

No files here at all? Lia uses the built-in Windows voice, which needs no download.
You can also force it:

```python
VOICE_NAME = "system"
SYSTEM_VOICE_MATCH = "Zira"   # or "David"
```
