"""Builds 'Lia - Phase Roadmap.pdf' -- a living status tracker: what's done, what's
next, and what's explicitly not happening right now, and why. Distinct from the
Growth Log, which is a historical narrative of stages already completed. This one
is meant to be edited in place as phases finish and priorities change, not added
to as a running log."""

from pathlib import Path

from make_pdfs import H1, H2, P, bullets, build, callout, table, PageBreak

HERE = Path(__file__).parent

story = []
A = story.append

A(P("What's actually done, what's next, and what's deliberately not scheduled — kept here so a "
    "decision doesn't have to be re-derived from memory or git log next time. Rebuilt whenever a "
    "phase finishes; see the Growth Log for the narrative version of how she got here."))

# --------------------------------------------------------------------- phase 1 ---
A(H1("Phase 1 — Polish what's built  ·  done"))
A(P("Three small, independent items, chosen over widening her actions or chasing raw intelligence "
    "first. All three landed."))

A(H2("1.1 — Instrument the cloud fallback"))
A(P("So the free/paid/local model choice gets decided from a week of real data instead of one "
    "session's impression. Every rate-limit and every mid-stream drop now writes a timestamped "
    "line to <font face='Courier'>cloud_fallback_log.jsonl</font>, and "
    "<font face='Courier'>fallback_report.py</font> reads it back as a plain count."))
A(P("<b>Already earning its keep:</b> one real fallback landed within days of shipping this — a "
    "rate limit on the free conversation model, announced and absorbed rather than left silent.",
    "LiaNote"))

A(H2("1.2 — Voice-ID status, spoken"))
A(P("<font face='Courier'>/whoami</font> was console-only, unreachable from the tray app most "
    "actual use happens in. “Do you know my voice”, “is that me” and similar now reach the same "
    "status out loud."))

A(H2("1.3 — Forget a single note"))
A(P("There was no way to remove one stored note short of touching the database directly. "
    "<font face='Courier'>db.delete_fact()</font> plus “what have you remembered” / “forget number "
    "2” — numbered list, pick by position, the same pattern already proven for music."))

A(PageBreak())

# ------------------------------------------------------------------ addition ---
A(H1("Asking someone else  ·  done, not originally scoped"))
A(P("Added mid-stream, at request, rather than planned in the phase above: “ask cat for a "
    "suggestion” reaches a second, named free model and relays the answer attributed. Two names "
    "today — cat, fox — each measured and picked for being fast <i>and</i> reliable, not for "
    "novelty."))
A(callout("<b>Not the multi-agent idea this plan shelved below.</b> That idea split <i>her own</i> "
          "reasoning across several small local models. This is the opposite shape: one cloud call, "
          "on request, to a model she isn't and doesn't pretend to be, at zero local VRAM cost. "
          "Closer to the “look that up” internet path than to anything rejected."))
A(P("Sixteen free OpenRouter models were catalogued directly and eight measured for real, twice. "
    "The metric mattered: this path collects the whole reply before speaking any of it, so total "
    "time is what a person waits on, not time to first word — the first pick (measured on the "
    "wrong metric) was heavier than it needed to be, and swapped once that was noticed. Two "
    "further names were tried and dropped rather than kept as a weak link: one lightest-on-paper "
    "replacement worked once and then failed empty five times in a row on a re-test; another was "
    "fast when it worked but wrong close to a third of the time across repeated real testing, each "
    "failure a real wait rather than an answer. Two names that have never once failed beat a "
    "bigger roster with a weak link in it."))
A(P("A real bug surfaced along the way, unrelated to model choice: a streamed request's timeout "
    "only bounds the gap between chunks, not the whole call, so a slow provider could hang far past "
    "it. Measured directly at 121 seconds, still empty. Every ask is now capped on wall-clock time "
    "regardless of provider behavior.", "LiaNote"))

A(PageBreak())

# ------------------------------------------------------------------ addition 2 ---
A(H1("A typed panel and a new icon  ·  done, not originally scoped"))
A(P("The tray app's first window. A small typed panel now opens alongside the tray icon, styled "
    "after Claude Code's own terminal — white and orange. Built as a second interface to the exact "
    "same conversation pipeline the console already had, not a new one: it satisfies the same "
    "typed-input and printed-output shapes <font face='Courier'>main.py</font> already knew how to "
    "use, so nothing about the conversation loop itself needed to change."))
A(P("<font face='Courier'>LISTEN_ENABLED</font> is off while this is the current way of working "
    "with her — a config flag, not commented-out code, specifically so the tray's own "
    "<b>Listening</b> checkbox keeps working live, no restart, the moment voice is wanted again."))
A(P("The tray icon changed too: a purple cat face, replacing the plain warm dot. Same two states "
    "(filled/listening, hollow/not) kept rather than reinvented; the mouth is the one new signal — "
    "open for speaking, closed for idle — doing the same job the old inner dot did, more legibly.",
    "LiaNote"))
A(callout("<b>The one real risk was threading, and it was checked, not assumed.</b> Tkinter and "
          "the tray icon's own loop both want the thread that started them. Verified before "
          "writing any of it rather than after something froze: the tray library documents running "
          "off the main thread as unsafe in general, safe specifically on Windows — which is what "
          "this project has been throughout, so that's the trade taken."))

A(PageBreak())

# --------------------------------------------------------------------- phase 2 ---
A(H1("Phase 2 — A background summarizer  ·  next"))
A(P("Of the three “raise the ceiling” ideas that came out of the intelligence conversation, this "
    "is the one with no architectural friction."))
A(P("<font face='Courier'>CLOUD_HISTORY_TURNS</font> is a hard cutoff — anything older than four "
    "turns just falls off the edge of what she sends. A summarizer removes that cliff cheaply "
    "because it reuses a pattern that already exists twice: the diary and fact-extraction both run "
    "<i>off the hot path</i>, once, locally, at session rollover — not on every turn."))
A(bullets([
    "A new <font face='Courier'>SUMMARY_PROMPT</font> in config.py, same shape as "
    "<font face='Courier'>DIARY_PROMPT</font>.",
    "A <font face='Courier'>session_summaries</font> table in db.py.",
    "A call from <font face='Courier'>end_session()</font>, alongside the diary and fact-extraction "
    "calls already there.",
    "A <font face='Courier'>build_summary_context()</font> injector — doesn't exist yet, since the "
    "diary has no equivalent — that folds the last summary into what "
    "<font face='Courier'>CLOUD_HISTORY_TURNS</font> sends.",
]))
A(P("Zero added latency on a live turn, as long as it stays scoped to session rollover the same "
    "way the diary already is.", "LiaNote"))

A(H2("How to know it worked"))
A(P("Hold a session past four turns, end it, confirm a new row in "
    "<font face='Courier'>session_summaries</font>. Start a fresh session and check — via "
    "<font face='Courier'>CLOUD_LOG_USAGE</font>'s token count, or a debug print — that the summary "
    "is actually part of what gets sent, not just written and ignored."))

# --------------------------------------------------------------------- phase 3 ---
A(H1("Phase 3 — Grounding check, log-only  ·  optional, lower priority"))
A(P("The other “raise the ceiling” idea, with a real conflict worth knowing before starting: "
    "replies stream to speech sentence-by-sentence on purpose — speaking sentence one while the "
    "rest still generates is exactly the latency-hiding win already measured and built. A verifier "
    "that blocks speech until it checks the whole reply undoes that directly. A per-sentence check "
    "has its own problem: a lone sentence like “yes, exactly” can't be judged alone, and it's a "
    "call per sentence, not per turn."))
A(P("<b>So: log-only first, if at all.</b> Check the completed reply against whatever memory or "
    "library context was already retrieved for that turn — no new retrieval needed, it's already "
    "materialized before the cloud call — <i>after</i> she's already spoken, and log a mismatch "
    "rather than gate on it. That's a real signal on how often the cloud model actually invents "
    "something, without touching the sentence streaming that already works. A blocking version, if "
    "it ever happens, is a separate decision made from what the log-only pass finds."))
A(H2("How to know it worked"))
A(P("Trigger a reply that draws on retrieved context, confirm a log line records the check. "
    "Separately: time-to-first-word before and after, to confirm it's unchanged — this phase's "
    "entire point is adding the check without paying the latency its own design is built to avoid."))

A(PageBreak())

# --------------------------------------------------------------- not doing now ---
A(H1("Explicitly not doing right now"))
A(table([
    ["Idea", "Why not, for now"],
    ["Duplicate-fact merging (sister_name vs\nvisiting_sister_name-style collisions)",
     "Only reachable through AUTO_EXTRACT_FACTS, which stays off by choice. Revisit only if that "
     "changes."],
    ["The multi-agent “small Lias” split\n(decomposing her own reasoning)",
     "No spare VRAM for stacked local calls on a 4GB card already near capacity. The role split it "
     "would add already exists — cloud for capability, judge.py/intent.py for narrow questions. A "
     "decomposed query that collapses to yes/no is just another judge.py. (Distinct from “Asking "
     "someone else” above, which is a different shape entirely.)"],
    ["Widening the action surface\n(opening/closing apps, broader OS control)",
     "Not a current priority. Two real prerequisites whenever it is picked up: intent.py's tools "
     "are deliberately parameterless, so this needs new argument-filling machinery, not just more "
     "entries; and voice-ID is the natural consent gate for it but is unenrolled and unvalidated "
     "against a real human voice today."],
    ["Platform/packaging reach\n(Linux, macOS)",
     "Single-machine, Windows-specific project today. Not raised as a priority."],
], [175, 270]))

A(H1("Open questions"))
A(bullets([
    "<b>Which model carries the actual conversation.</b> Local (2.19s, free, least capable), paid "
    "gpt-4o-mini (2.51s, ~$0.0001/turn), or the current free model (4.53s, rate-limited but no "
    "cost) — still an open call, not a settled one, revisit as real fallback data accumulates via "
    "1.1 above.",
    "<b>A third (or fourth) “ask” name.</b> Two were tried and dropped rather than kept as weak "
    "links. Worth revisiting if OpenRouter's free catalog turns up something both light and "
    "consistently reliable — re-measure on total time, the way cat and fox were, before adding "
    "one back.",
]))

build(HERE / "Lia - Phase Roadmap.pdf",
      "Lia — Phase Roadmap",
      "What's done, what's next, and what's deliberately not scheduled.",
      story)
