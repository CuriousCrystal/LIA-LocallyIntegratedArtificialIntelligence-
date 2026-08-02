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

Then set it explicitly in [`config.py`](../config.py):

```python
VOICE_NAME = "my_voice"
```

`VOICE_NAME` is deliberately pinned rather than left on `"auto"` — with `"auto"`,
downloading a second voice file would silently change which one Lia used the next
time she started. Explicit means adding a file here never changes her voice on
its own; you choose when to switch.

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

## A second engine: KittenTTS

[KittenTTS](https://github.com/KittenML/KittenTTS) is a different, much smaller
voice model (25–80MB, CPU-only, so it never competes with Ollama for VRAM) with
its own voice set: **Bella, Jasper, Luna, Bruno, Rosie, Hugo, Kiki, Leo.** It's
already wired in as `KittenEngine` in [`voice.py`](../voice.py) — switch to it with:

```python
VOICE_ENGINE = "kitten"
KITTEN_VOICE_NAME = "Bella"
```

**Installing it isn't a plain `pip install`.** The released wheel's own metadata
demands `misaki>=0.9.4`, which doesn't exist on PyPI (0.7.4 is latest) — but the
package works fine with the older version anyway. Install with `--no-deps`, then
the real dependencies by hand:

```powershell
pip install --no-deps https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl
pip install misaki espeakng_loader num2words spacy phonemizer
```

There's a second bug beyond that: `misaki` (its phonemizer) hardcodes a Windows
path to a system-wide eSpeak NG install that essentially nobody has
(`C:\Program Files\eSpeak NG\...`), and the `espeakng_loader` package that *does*
bundle a working copy has its data directory path baked in from the CI machine
that built it, so that fails too if used as-is. `KittenEngine.__init__` in
`voice.py` works around both by pointing `EspeakWrapper` at the real bundled
paths directly — you don't need to do anything extra beyond the two installs
above.

First use downloads the model itself from Hugging Face (~80MB for the `mini`
size), cached afterwards.

## Cloning a specific person's voice

Both Piper and KittenTTS voices are *trained*, not cloned — you can't hand either
one a ten-second clip and get that person back. Cloning from a short sample needs
a different class of model (XTTS, F5-TTS, Chatterbox), which is much heavier and
would contend with Ollama for your 4GB of VRAM.

If you want that later, the seam is already here: add a new engine class in
[`voice.py`](../voice.py) alongside `PiperEngine` and `KittenEngine` — anything
with a `.say(text)` method and a `.name` works — and have `_build_engine()`
return it.

**One caution:** cloning someone's voice from a recording is something to only do
with that person's knowledge and agreement. It's their voice, not just audio.

## Falling back to a system voice

No files here at all? Lia uses the built-in Windows voice, which needs no download.
You can also force it:

```python
VOICE_NAME = "system"
SYSTEM_VOICE_MATCH = "Zira"   # or "David"
```
