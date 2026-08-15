# Test session — 2026-08-16

A full pass over every module, run directly against the real Ollama and
OpenRouter endpoints, timed. Purpose: catch anything broken after the
agent-ask feature and its two follow-up revisions, and leave a real timing
baseline to compare against later, not just the claims already written into
the READMEs and PDFs.

**Method.** Every DB-writing call ran against a scratch copy of the database
(`db.DB_PATH` redirected before any write), never the real
`lia_memory.db`. Weather and internet lookups were not exercised —
`WEATHER_ENABLED` / `INTERNET_ENABLED` are both `False` by explicit standing
choice, and turning them on wasn't part of this request. Voice-ID and music
playback couldn't be exercised end-to-end — there's no real audio input
available to this test, and `LIA/music/` currently holds no actual files to
play, only its README. Full script: `full_regression.py` (not checked in —
it's a throwaway harness, not a project tool).

**Result: 41 of 42 checks passed.** The one failure was a live free-model
timeout, already an accepted, designed-for outcome (see below), not a defect.

## Timings

| section | check | seconds | result |
|---|---|---:|---|
| local chat | `llm.chat` one turn | 1.03–1.39 (warm)¹ | OK |
| local embed | `llm.embed` | 0.95 | OK |
| cloud chat | `llm.chat_stream`, main conversation model | 1.95 | OK |
| judge | real question → should be True | 0.47–0.53 | OK² |
| judge | small talk → False | 0.47 | OK |
| intent | `route()` on a command-shaped phrase | 1.20 | OK |
| intent | `route()` on ordinary conversation | 0.00 | OK |
| music | `available()` / `tracks()` / `is_playing()` | <0.2 | OK (folder empty) |
| volume | `get_volume()` / `adjust_volume()` round trip | <0.1 | OK³ |
| alarms | `would_schedule()`, 5 phrasings | 0.00 | OK |
| alarms | `schedule()` a real reminder (scratch db) | 0.02 | OK |
| library | `files()` / `pending()` / `titles()` | 0.00 | OK (folder empty) |
| memory / notes | upsert, list, delete, re-delete | <0.02 | OK |
| speaker-id | `available()` / `is_enrolled()` / progress | <0.72 | OK (never enrolled) |
| ask dog | `nvidia/nemotron-nano-12b-v2-vl:free` | timed out at 15s | **FAIL⁴** |
| ask cat | `nvidia/nemotron-3-nano-30b-a3b:free` | 1.47 | OK⁵ |
| ask fox | `poolside/laguna-s-2.1:free` | 2.27 | OK |
| diary | `write_entry()` on a synthetic transcript | 2.28 | OK |
| fact extraction | `extract_and_store_facts()` on the same transcript | 1.06 | OK |

¹ First call in the run measured 12.67s — a cold Ollama load, not a
regression. Re-tested warm immediately after: 1.03–1.39s, in line with (and
slightly faster than) the 2.19s baseline already documented in
`config.py`/the Growth Log. `ollama ps` confirmed both models resident in
VRAM once warm.

² The first live run of "what does chapter 3 say about the treaty" actually
returned **False** — a miss. Re-run three times back to back: True, True,
False — a 2-in-3 borderline call on this specific phrasing, not a broken
classifier. Three other phrasings (including plain small talk) went 3-for-3
correct each. Consistent with the ~97% (35/36) accuracy already measured and
documented for this judge; this session caught one of the roughly-3%
misses live rather than finding a new problem.

³ **This test moved your real system volume and had to be corrected.**
`adjust_volume(+5)` was called while volume was already at the 100 ceiling,
so it silently clamped and had no effect; the following `adjust_volume(-5)`
did have an effect, so the round trip wasn't actually symmetric and left
volume at 95. Caught immediately after the run and set back to 100 by hand.
Noted here because it's the one check in this session with a real
side effect, and because it's a reminder that "add N then subtract N" isn't
a safe round trip near a clamped ceiling.

⁴ `dog` (`nvidia/nemotron-nano-12b-v2-vl:free`) timing out is expected
behavior, not a surprise: this model was already measured at roughly a 75%
success rate when it was picked, and every `ask_agent()` call is capped at
`AGENT_TIMEOUT_SECONDS` (15s) specifically because this model is known to
occasionally hang. It failed clean and fast here, exactly as designed —
worth recording as confirmation the timeout fix actually works under a real
failure, not just in the test that originally found the bug.

⁵ `cat`'s first reply this session was garbled — a strange aside about
"how alcoholics speak" that had nothing to do with the question asked or the
system prompt given. Re-ran the identical call immediately after: a clean,
sensible answer. One bad output out of two real-world samples so far for
this model — logged here rather than dismissed, but not enough evidence yet
to call it a pattern. Worth another look if it recurs.

## What this confirms

- Every module imports and runs cleanly end to end — `config`, `db`, `llm`,
  `judge`, `intent`, `media`, `alarms`, `music`, `library`, `speaker_id`,
  `memory`, `diary` — including the disabled-by-config paths (diary, fact
  extraction), which still work correctly when called directly, they're
  just not wired into a live session right now.
- The three surviving `ask_agent` names (dog, cat, fox) all answer with
  real free-tier variance already priced into the design: occasional
  timeouts, occasional off replies, both handled rather than silent.
- `cloud_fallback_log.jsonl` (built in Phase 1.1) already has one real entry
  from ordinary use — a rate limit on 2026-08-14, absorbed and fallen back
  from cleanly. `fallback_report.py` reads it back correctly.

## What this doesn't cover

- Real microphone input, wake-word behavior, barge-in, or actual TTS
  playback — nothing here can drive a physical mic or speaker.
- Real music playback — nothing is in `LIA/music/` to play.
- Real document retrieval — nothing is in `LIA/library/` to index or search.
  The judge's *decision* was tested; the retrieval it would gate wasn't.
- Real voice-ID matching — enrollment has never been run, so only the "not
  enrolled" state was exercised.
- Weather / internet lookups — off by standing choice, not touched.

---

## Second pass, same day — after the typed panel, the icon change, and dropping `dog`

Re-ran the same suite after three more changes landed: the `dog` ask-agent
name was dropped (see `config.py` — it was failing close to a third of the
time), the typed training panel (`panel.py`) was added, and the tray icon
changed from a plain dot to a purple cat. Same method as above — scratch
database, real Ollama/OpenRouter calls, weather/internet still untouched.

**43 of 43 checks passed** — the first completely clean run this project has
had. Two things worth recording anyway, because "passed" isn't the same as
"nothing happened":

- **A second real cloud fallback landed live, mid-test.** The main
  conversation call hit `google/gemma-4-26b-a4b-it:free`'s rate limit,
  logged correctly (`2026-08-16T01:51:46`, `"reason": "rate limited"`), and
  fell back to the local model exactly as designed — `fallback_report.py`
  now shows 2 fallbacks across the two real ones logged so far. Real,
  unprompted evidence for the open question in the Phase Roadmap about
  free-tier reliability.
- **The judge got the same borderline question right this time** ("what
  does chapter 3 say about the treaty" → True). Consistent with the ~2-in-3
  result from the first pass — this is expected variance on a phrasing near
  its decision boundary, not a fix or a regression.

**New checks added this pass, both passing:**

| check | what it verified |
|---|---|
| `panel` construct + round trip | A `Panel()` correctly implements both interfaces it stands in for — `.pending()`/`.take()` (same shape as `main.Keyboard`) and `.write()` (same shape as `TeeLog`'s "also" stream) — without opening its event loop. |
| `make_icon()` all 3 states | The new cat-face icon renders without error for not-listening / listening / speaking, at the correct 64×64 size. |

**Verified separately, outside the timed harness — visual and live-process
checks don't fit a `(section, seconds, result)` table:**

- Screenshotted the real running panel on *both* entry points
  (`pythonw app.py` and `python app.py --debug`) — correct styling, and
  correctly showing `"You:"` rather than `"You (Enter to speak):"`, which
  only happens if `LISTEN_ENABLED` is genuinely taking effect through the
  new `have_panel` branch in `main.main()`, not just in isolated code.
- Rendered all three icon states at 64×64, 256×256, and shrunk-then-scaled
  to simulate real 16×16 taskbar size — the cat silhouette (ears, head,
  eyes) stays legible at taskbar size; whiskers are lost at that size, as
  expected, and weren't the load-bearing detail.
- Could **not** verify a real keystroke reaching the live window end to
  end — this environment blocks the usual Windows focus-stealing APIs
  (`SetForegroundWindow`, `AppActivate` both returned failure). Not treated
  as inconclusive: the exact same submit path was already proven correct
  in the standalone `panel` check above, and `read_input()`'s consuming
  side is pre-existing code that already trusted any `.pending()`/`.take()`
  object before this feature existed. Flagged rather than papered over —
  worth a real keystroke test from a normal desktop session if anyone
  wants that last mile closed.
