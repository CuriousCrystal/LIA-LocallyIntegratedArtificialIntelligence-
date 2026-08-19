# Test session — 2026-08-20

The first full pass on the **new machine**: a Core Ultra 7 255U with no discrete
graphics card, where the previous one had a 4GB card. Purpose: confirm nothing
broke in the move, and re-measure everything, because every timing recorded
before this was taken on hardware that no longer exists.

**Method.** Same as the 2026-08-16 pass. Every DB-writing call ran against a
scratch copy of the database (`db.DB_PATH` redirected before any write), never
the real `lia_memory.db`, and `LIBRARY_DIR` was redirected to a scratch folder
too. Real Ollama, real NPU, no mocks. Weather and internet were not exercised —
`WEATHER_ENABLED` / `INTERNET_ENABLED` are both `False` by standing choice.

This pass reaches further than the last one in three places it explicitly could
not before:

- **TTS, STT, wake word and the echo guard were exercised for real.** Test audio
  was synthesised with the Windows SAPI voice, so there is a known ground truth
  to check transcription against without a person in the room.
- **Document indexing and retrieval ran end to end**, against real files written
  into the scratch library folder — previously only the judge's *decision* was
  testable, not the retrieval it gates.
- **A whole spoken turn** was run twice: once down the deterministic path
  (hear → wake word → alarm branch, model never consulted) and once down the
  conversational one (hear → think → reply).

**Result: 104 of 104 checks passed, 34.3s wall time.** No failures.

Worth recording: the first run of this suite reported 5 failures, and all five
were the harness asserting the wrong thing, not the code. They are written up
under "Five false alarms" below rather than deleted, because a test that is
wrong in a plausible way is worth remembering.

## Timings

| section | checks | total | slowest check in it |
|---|---:|---:|---|
| config | 11 | 0.00s | — |
| database | 10 | 0.03s | `init_db` 0.01s |
| llm | 10 | 1.48s | `chat_stream` 0.75s |
| memory | 6 | 6.10s | `extract_and_store_facts` 5.99s |
| library | 13 | 0.72s | `ingest_file` 0.44s |
| judge | 3 | 7.63s | `wants_library` 2.60s |
| intent | 3 | 0.15s | `route()` 0.15s |
| alarms | 8 | 0.01s | all under 1ms |
| voice / speaking | 7 | 2.40s | Piper load 2.25s |
| voice / listening (NPU) | 8 | 2.99s | Whisper load 2.19s |
| music | 4 | 0.07s | `available()` 0.07s |
| volume | 2 | 0.21s | `set_volume` 0.14s |
| speaker id | 2 | 0.40s | `available()` 0.40s |
| internet / diary | 2 | 3.44s | `write_entry` 3.44s |
| fallback report | 1 | 0.00s | — |
| main | 12 | 0.23s | `as_instruction` 0.13s |
| end to end | 2 | 8.35s | hear→think→reply 8.13s |

### Speech recognition, now on the NPU

| | 2.3s clip | 5.4s clip | 14.9s clip |
|---|---:|---:|---:|
| faster-whisper, CPU int8 (the old path) | 0.55s | 0.59s | 0.69s |
| OpenVINO, CPU | 0.42s | 0.50s | 0.71s |
| OpenVINO, iGPU | 0.15s | 0.20s | 0.37s |
| **OpenVINO, NPU** | **0.11s** | **0.16s** | **0.31s** |

5.2x on short clips against the path it replaces, which is the case that
matters — almost everything said to her is a sentence, not a paragraph.

Note that OpenVINO *on the CPU* is barely better than faster-whisper and is
worse on the long clip. Moving to OpenVINO is not the win; moving off the CPU
is. The seconds it gives back are seconds the CPU keeps for the language model.

### The language model

| | |
|---|---|
| generation | 21 tok/s, steady across the session |
| prompt processing, cold | ~110 tok/s |
| turn 1 to first word | 7.68s before the fix, **2.35s** after |
| turns 2+ to first word | ~1.0s |

The delay was never the model writing, it was the model *reading*. Her
575-token system prompt at 110 tok/s is 5.3 seconds, paid once, because Ollama
caches the prefix. `llm.warm_up()` was sending `messages: []` — which loads the
weights but leaves the prompt unread — so `PREWARM_ON_SPEECH` was warming the
cheap half. It now takes the real system message, and `main()` calls it during
startup. Measured 7.46s → 2.35s.

Generation at 21 tok/s against speech's ~5 tok/s means her voice is the
bottleneck, not the model, which is the right way round.

### Piper

Synthesis runs at about **26x realtime** once warm — 0.18s to produce 4.7s of
speech. Cold, the first call is 5.8s. Both measured through `voice.Speaker`, not
a reimplementation.

## The judge, gated and then removed

The judge measured 2.3–2.9s per call across six phrasings, consistently, warm.
It was 0.47–0.53s on the old machine — a 15W CPU doing what a graphics card used
to, not the model getting worse.

It was first *gated*: `main()` reached it whenever `REMEMBER_CONVERSATION` was on,
regardless of whether anything was indexed, so an empty library paid ~2.5s every
turn to be told there was nothing to find. Adding `db.document_titles() and` in
front fixed that case.

Then it was **switched off entirely**, because the gate only helped an empty
library and the cost returned the moment real documents existed. Two things
decided it:

**It had quietly got less accurate.** `JUDGE_MODEL = MODEL_CHAT`, so dropping to
gemma2:2b took the judge with it — 11/12 here against the 35/36 measured for
llama3.2:3b. The miss fails *closed*: "how tall is the lighthouse" was answered
without opening the book, while retrieval itself found the passage 5/5. The judge
was the weak link, not the search.

**A score floor turned out to work after all, on this library.** `judge.py` argues
it cannot, and against a 671-passage novel it could not. Re-measured here on three
short documents, 8 real questions against 8 ordinary ones:

```
real questions     0.484 ─────────────────────── 0.675
small talk         0.390 ───────── 0.506
                                ^^^ overlap: 0.484-0.506, one question wide
```

They still overlap, but narrowly enough that a floor at **0.52** keeps 7 of 8 real
questions and blocks 8 of 8 small talk. `LIBRARY_MIN_SCORE` went 0.45 → 0.52 and
`JUDGE_ENABLED` went off.

| | correct | per turn |
|---|---:|---:|
| judge at `LIBRARY_MIN_SCORE = 0.45` | 11/12 | 2.5s |
| score floor at 0.52, no judge | **15/16** | **45ms** |

Across the 16 test turns the judge would have added 40 seconds. Leaving 0.45 in
place with the judge gone was measured too, and is the trap: four of six ordinary
sentences pulled the documents in, up to 1004 characters of a lighthouse story in
front of "I had a really long day at work."

**The caveat that matters:** this was measured on three short documents, not the
novel the original overlap came from. More text means more chances for an
unrelated passage to score well, so the trade gets worse as the library grows.
The question it already loses — "what did her father teach her", 0.484 — is the
shape to watch: about the contents, with none of the contents' vocabulary in it.
`JUDGE_ENABLED` is the way back.

## Five false alarms

The first run reported 104 checks with 5 failures. All five were the harness.

1. **`extract_and_store_facts`** and **`diary.write_entry`** — both asserted with
   `lambda: fn() or True`. Both functions return something truthy, so `x or True`
   evaluated to `x`, which is not `True`. The functions worked correctly; the
   assertion was nonsense. Rewritten as `(fn(), True)[1]` — "did not raise".
2. **`forget_document`** — called with an absolute path. Documents are keyed by
   `library._key()`, a path *relative* to the library folder, so the delete
   matched nothing. Checked the real caller: `library.py:330` passes the key
   correctly, and it is the only caller. No bug.
3. **`SentenceBuffer`** — fed `"One. Two. "` and expected a sentence out.
   `MIN_CHARS = 25` holds short fragments back on purpose, so that TTS doesn't
   sound clipped. Working exactly as designed. A second check was added for the
   held-back case, since that behaviour was previously untested.
4. **`claims_identity`** — tested with `"it's Wade"` while the stored `name` fact
   was `Saarthak`. The function builds its pattern from the current name, which
   is the whole point of it. Now sets the name first, and a second check
   confirms it rejects a different one.

None of these were bugs in Lia. All four are recorded because the failure modes
were plausible enough to waste a real half-hour, and would have again.

## What this confirms

- Every module imports and runs end to end on the new machine — `config`, `db`,
  `llm`, `memory`, `library`, `judge`, `intent`, `alarms`, `music`, `media`,
  `speaker_id`, `internet`, `diary`, `voice`, `panel`, `fallback_report`, `main`,
  `app` — including the switched-off paths (diary, fact extraction), which still
  work when called directly.
- Speech recognition on the NPU is correct as well as fast: "Anaya" came through
  right, and the wake word matched on "Leah", which `WAKE_WORDS` already lists.
- The whole deterministic ladder holds: wake word → spoken command → explicit
  remember → alarm regex, with the model consulted only when none of them match.
- `set_volume` restores exactly. The 2026-08-16 pass moved the real system volume
  and had to correct it by hand, because add-then-subtract is not a round trip at
  the 100 ceiling. This pass reads the value first and sets it back, rather than
  adjusting relatively.

## What this doesn't cover

- **A real microphone.** The mic array captures and the VAD loads and reports
  zero speech in a quiet room, but every transcription here was of synthesised
  speech, which is cleaner than a person in a room. The accuracy claims — in
  particular that dropping Whisper's vocabulary hint costs nothing — need
  re-testing against a live mic before they are settled.
- **Barge-in and playback interruption**, which need someone talking over her.
- **The cloud path.** `OPENROUTER_API_KEY` is not set on this machine, so
  `using_cloud()` is `False` and everything ran locally. `ask_agent`, the cloud
  chat stream, and the rate-limit fallback were not exercised.
- **Real music playback** — `LIA/music/` holds no files.
- **Voice-ID matching** — `speaker_id.available()` is `False` here; the model
  named in `models/README.md` has not been downloaded on this machine, so only
  the unavailable path was exercised.
- **Weather / internet lookups** — off by standing choice, not touched.
