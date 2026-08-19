# Models

`speaker_embedding.onnx` is not checked in — it's a 28MB download, fetched once:

```powershell
curl -sL -o LIA\models\speaker_embedding.onnx https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx
```

This is 3D-Speaker's CAM++ model, trained on VoxCeleb (real recorded speech), run
locally through `sherpa-onnx` (onnxruntime underneath — no PyTorch). Used by
[`speaker_id.py`](../speaker_id.py) to tell whether the voice talking to Lia
matches the one enrolled with "Hey Lia, it's Wade."

## `openvino/` — Whisper for the NPU

Also not checked in: ~154MB for `base.en`, fetched once.

```powershell
pip install openvino-genai huggingface_hub
huggingface-cli download OpenVINO/whisper-base.en-fp16-ov `
    --local-dir LIA\models\openvino\whisper-base.en-fp16
```

For `small.en`, swap `base` for `small` in both the repo id and the folder, and
point `WHISPER_OV_MODEL` at it.

These are pre-converted, which is the whole reason to use them. OpenVINO needs
its own IR format — an `.xml` graph beside a `.bin` of weights — and converting
a model locally means installing PyTorch and `optimum-intel` for a one-off job,
about 2.5GB of dependencies to produce 154MB of output. The published builds
skip all of it. `int8` and `int4` variants exist at the same repo ids if you
want them smaller.

**Which processor it runs on** is `WHISPER_DEVICE` in
[`config.py`](../config.py) — `NPU`, `GPU` (the integrated one), or `CPU`. The
measurements behind the default are in the comment there. Check what your
machine actually offers:

```powershell
python -c "import openvino as ov; print(ov.Core().available_devices)"
```

If that doesn't list `NPU`, either the chip hasn't got one or the driver is
missing — Intel ships it as "Intel(R) AI Boost" in Device Manager. Lia falls
back to `faster-whisper` on the CPU by herself either way, so a machine with
none of this still hears you; see `WHISPER_BACKEND`.

**One limitation, on the NPU only:** it cannot take Whisper's vocabulary hint.
The NPU compiles to fixed tensor shapes and a prompt changes the decoder's input
length, so asking for one raises rather than degrading. `WHISPER_HINT_ENABLED`
is off for that reason and carries the detail. CPU and iGPU both accept it.
