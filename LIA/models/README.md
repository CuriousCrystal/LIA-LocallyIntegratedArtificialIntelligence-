# Models

`speaker_embedding.onnx` is not checked in — it's a 28MB download, fetched once:

```powershell
curl -sL -o LIA\models\speaker_embedding.onnx https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx
```

This is 3D-Speaker's CAM++ model, trained on VoxCeleb (real recorded speech), run
locally through `sherpa-onnx` (onnxruntime underneath — no PyTorch). Used by
[`speaker_id.py`](../speaker_id.py) to tell whether the voice talking to Lia
matches the one enrolled with "Hey Lia, it's Wade."
