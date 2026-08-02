"""
Builds 'Lia - Session Summary.pdf' -- the whole build conversation on a few
pages, one line of ask and a short account of what came of it.

Timestamps and tool counts are read from the real Claude Code session log; the
summaries are written.
"""

import datetime as dt
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

from build_transcript import SESSION, group_exchanges, read_session, when
from make_pdfs import ACCENT, RULE, S, build, H1, P, callout

HERE = Path(__file__).parent

# Keyed by exchange number. (what you asked, what came of it)
SUMMARIES = {
    1: ("Introduced the project; stuck because the editor's Run button can't take typed input.",
        "Confirmed the code was fine by running it end to end. The fix was a real terminal. "
        "Flagged that <font face='Courier'>DB_PATH</font> was relative, so launching from the wrong "
        "folder would silently create a second, empty memory."),
    2: ("Typed something and nothing came back.",
        "Not broken — <b>silent</b>. Replies were fetched whole before printing, so ~20s passed with a "
        "blank screen. Added token streaming and progress markers. Also found fact extraction was "
        "storing nothing, and made <font face='Courier'>DB_PATH</font> absolute."),
    3: ("Rename Aurora to LIA; add voice, with room to add my own voices later.",
        "Built the whole voice layer: Piper for speech, a <font face='Courier'>voices/</font> folder you "
        "drop <font face='Courier'>.onnx</font> files into, sentence-chunked speech so she starts talking "
        "before the reply finishes, and Whisper for listening."),
    4: ("Fix the two things you flagged.",
        "Diary was narrating as if it were the human — caused by <font face='Courier'>user:</font>/"
        "<font face='Courier'>assistant:</font> labels. Relabelled to <b>Them</b>/<b>Lia</b>. Added a "
        "deterministic filter so junk like <font face='Courier'>name: \"you\"</font> can't overwrite real facts."),
    5: ("Analyse the project.",
        "Found the biggest quality flaw: <b>half her recall was her own past replies</b>, unlabelled, "
        "which she read back as fact. Also: diary written but never read, no sense of time, "
        "embeddings stored as JSON (10&times; bloat). Measured the scan cost and said plainly it "
        "wasn't worth optimising yet."),
    6: ("Fix line 8, column 16.",
        "Type checker couldn't verify <font face='Courier'>sys.stdout.reconfigure</font>. Switched to "
        "<font face='Courier'>getattr</font>, which is also more honest about why the guard exists."),
    7: ("Is everything fine? Explain the directories.",
        "All modules compiled and ran. Caught her <b>confabulating</b> in that very run — inventing that "
        "you'd been nervous. Mapped the folder layout and the strict layering."),
    8: ("How do I run it?", "The command, what to expect, and why to type <i>bye</i> rather than closing the window."),
    9: ("Set it up so I can talk to her by voice.",
        "Upgraded to <font face='Courier'>small.en</font> after testing showed <font face='Courier'>base.en</font> "
        "heard <i>“Ania”</i> for <i>“Anaya”</i>. Biased recognition using names she already knows, which "
        "fixed her own name coming out as <i>“Leah”</i>."),
    10: ("What if she were an app I just open my laptop to?",
         "Measured the real gap: cold start 9.3s vs 2.4s warm. Laid out five things standing in the way "
         "and staged them, flagging that <b>sessions never ending</b> would mean an always-on Lia never learns."),
    11: ("Build stage 1.",
         "Models kept warm, sessions that close themselves after 12 quiet minutes, launcher and autostart "
         "script. Found the hidden bottleneck: Ollama's default 32k context was running <b>63% of her on "
         "CPU</b>. Pinning 8192 cut reply time by a quarter."),
    12: ("Do the retrieval fix, then stage 2.",
         "Retrieval limited to your words with timestamps. Added open-mic listening with Silero VAD, "
         "keyboard-vs-mic arbitration, and mic gating. Fixed her reading stage directions aloud."),
    13: ("Make her an app I can add to startup.",
         "Tray app with no window — only possible because voice detection removed the need for a keyboard. "
         "Verified quitting still writes her diary first."),
    14: ("Add a wake word, an exe, and tell me how to start.",
         "Wake word matched <b>on the transcript</b> rather than a trained model — no dataset needed, and it "
         "tolerates Whisper's spellings. Built the exe. Made paths survive being frozen."),
    15: ("How do I get her into startup?", "The one command, and what it actually does."),
    16: ("If I restart now, will she be there?",
         "<b>No</b> — I'd built the installer but deliberately not run it. Said so plainly."),
    17: ("Do it.",
         "Installed. Hit a real bug of my own: PowerShell variable names are case-insensitive, so my local "
         "<font face='Courier'>$exe</font> collided with the <font face='Courier'>-Exe</font> switch. Verified by "
         "launching the shortcut."),
    18: ("Confirm she'll be there after a restart.", "Yes — both she and Ollama were in the Startup folder."),
    19: ("Greet me, call me Warlock, and can she learn things like Morse code?",
         "Greeting generated from her diary, which finally made the diary useful. Tested Morse honestly: "
         "<b>she fails even with a perfect reference table in front of her</b>. Not a memory problem — "
         "tokenisation. The fix would be code, not teaching."),
    20: ("A folder for PDFs, and make her voice softer.",
         "Built the library with page-level citation. Stripped repeated page headers that were poisoning "
         "every search. Played four voice options rather than guessing."),
    21: ("Amy as she was, and make sure she says Warlock.",
         "Reverted the softening. Found the name had <b>reverted on its own</b> — extraction re-derived the "
         "old one from stored turns. Added protected facts and purged the stale references."),
    22: ("Thanks.", "—"),
    23: ("Can I say “Lia stop” to stop her listening?",
         "<b>No.</b> It would just become conversation. And she can't hear you at all while speaking. "
         "Said so rather than implying it half-worked."),
    24: ("What do you mean?", "Re-explained without jargon: what barge-in is, why speakers break it, why headphones don't."),
    25: ("I use both.",
         "Built spoken commands, and made interrupting work on speakers too — <b>she compares what she hears "
         "against what she's currently saying</b>, so her own voice is recognised and ignored."),
    26: ("She didn't respond after a restart, and the diary won't open.",
         "Three causes: she spent <b>four minutes re-reading a PDF</b> before speaking (absolute paths made it "
         "look new), speech recognition loaded after the greeting, and ignored speech was logged nowhere. "
         "The diary was fine — there was simply nothing to write yet."),
    27: ("I didn't want her going through PDFs on her own. And remove Anaya and Kamala.",
         "Made the library strictly on-demand. Removed all of it — and said plainly that <b>I had invented "
         "Anaya, Kamala, Maya and Biscuit during my own testing</b>. Undid my overreach of having her read "
         "your PDF unasked."),
    28: ("The tray boxes were unchecked and she's not responding.",
         "She'd asked how your day was, then ignored “hello” — my overcorrection from the previous fix. "
         "Gave the greeting a 30s reply window. The unchecked boxes were real: the Ollama wait blocked "
         "before the tray was told her state."),
    29: ("“Failed to import embedded python interpreter.”",
         "You'd launched her mid-rebuild — my fault for rebuilding while she was in your startup. Builds now "
         "stage and swap, so a failed build leaves the working app untouched."),
    30: ("Should Ollama stay in startup?",
         "Yes, and it's safer — when Windows starts it, it never touches her folder. Cost measured at "
         "~130&nbsp;MB RAM and no GPU while idle."),
    31: ("Is there a better approach than that trade-off?",
         "Yes — my framing was wrong. The keep-alive timer <b>resets on every request</b>, so it only governs "
         "idle time. She now releases the models when a conversation ends and starts reloading the moment "
         "you speak."),
    32: ("Make a PDF of the changes, and a beginner's guide.",
         "Both written, including the limitations rather than only the wins."),
    33: ("Is the project completed?",
         "Working and deployed, but not finished: no way to forget, still embroiders, no tests, drifting "
         "fact keys, and two of your original roadmap items unbuilt."),
    34: ("A PDF of just our chats, for tracking.",
         "Found Claude Code's own session log on disk and generated a 47-page transcript from the real "
         "record rather than from memory."),
    35: ("I wanted that summarised.", "This document."),
    36: ("(switched model to Fable 5)", "&mdash;"),
    37: ("(command output)", "&mdash;"),
    38: ("Three things: replies feel slow, she should say \"you\" rather than the name every "
        "time, and whether to add Groq for internet access given an unreliable connection.",
        "Measured the real per-turn cost and found a genuine bug: the same sentence was being "
        "embedded <b>twice</b> per turn (memory and library lookups). Fixed by sharing one "
        "embedding call, and skipping retrieval entirely on short replies like \"yeah\". Softened "
        "the system prompt to prefer \"you\". Built weather (Open-Meteo, no key needed) and an "
        "online-lookup path via Groq &mdash; with the honest caveat that a plain Groq call has no "
        "more live internet access than the local model does either."),
    39: ("(switched model to Opus 5)", "&mdash;"),
    40: ("(command output)", "&mdash;"),
    41: ("Handed over a Groq key, confirmed the media player is just \"Windows,\" and asked "
        "about adding custom voice files.",
        "Set the key as a Windows environment variable, never in a file. While wiring it in, "
        "found the key had been pasted directly into <font face='Courier'>internet.py</font> and "
        "something had already stripped it back out, leaving broken syntax that would have "
        "crashed the whole app on next launch &mdash; fixed and verified. Built Windows media "
        "control (play/pause/skip/now-playing) via System Media Transport Controls, verified "
        "against a real session already running on the machine."),
    42: ("Asked whether voice model files could be used, and whether an OpenRouter key would "
        "help &mdash; then linked KittenTTS specifically for its \"Bella\" voice.",
        "Built OpenRouter support: with both keys present she now prefers OpenRouter's "
        "<font face='Courier'>:online</font> mode &mdash; a genuine web search &mdash; over Groq's "
        "plain guess. Getting Bella working meant fixing three separate upstream packaging bugs "
        "in KittenTTS (a required dependency version that doesn't exist on PyPI, a hardcoded "
        "Windows path to eSpeak, a data path baked in from the CI machine that built it). Verified "
        "working end to end, but left the active voice on amy since that was already the "
        "confirmed choice."),
    51: ("Asked for a new \"growth log\" PDF tracking capability stages (making her, file-path "
        "reading, voices, and controlling actions as the current frontier) instead of a changelog "
        "— and, separately, whether she can actually control playback, since she'd told him her "
        "interactions were text-only.",
        "Built the Growth Log and removed the old \"What We Built\" PDF as asked. On the "
        "capability question, found the real cause: her system prompt never told her what she "
        "could do, so she answered from generic assumptions instead of her actual abilities — "
        "confirmed directly in his own session log, where she'd said almost exactly that. Fixed "
        "the prompt, then built volume control as the natural next step. Tried simulating the "
        "physical volume keys first; verified live that it silently did nothing. Switched to "
        "talking to Windows' Core Audio API directly instead, verified working. Also caught and "
        "fixed a real matching bug along the way: “unmute” was resolving to the wrong "
        "command because character-level substring matching treated it as ending in “mute.”"),
    52: ("Asked to keep the PDFs updated going forward without being asked each time, and raised "
        "voice differentiation as a possible next step — asking for an opinion before any "
        "changes.",
        "Saved the standing instruction. Recommended treating voice recognition as a soft comfort "
        "signal gating actions, not a hard lock — a laptop mic isn't reliable enough to bet "
        "security on, and a false lockout is worse than not having the feature at all."),
    53: ("Refined the idea: “hey Lia, it's Wade” as how she'd know him, and when she "
        "doesn't recognise the voice, she should be uneasy and decline actions.",
        "Agreed on the design and flagged two decisions before building: what “uneasy” "
        "should actually sound like (a decline, not a hard refusal), and whether this should also "
        "gate shared personal facts, not just actions."),
    54: ("Confirmed: gate personal details too, not just actions.",
        "Found a lightweight local model (3D-Speaker's CAM++ via sherpa-onnx, ~27MB, no PyTorch) "
        "and downloaded it. Building and testing it honestly took real debugging: an early result "
        "showed the enrolled voice scoring *worse* than a different one, traced through several "
        "false leads (averaging logic, database contamination) before finding the actual causes — "
        "Piper's TTS vocoder is stochastic by design, and a manual resampling step in the test "
        "harness was corrupting the signal. With those isolated, the model showed real, "
        "correctly-directioned discrimination, though weaker than expected — flagged clearly "
        "that synthetic test voices likely understate real accuracy, and it can't be fully "
        "verified without an actual human voice. Built enrollment (“it's Wade”, averaged "
        "over repetitions), gated media/volume/alarm actions and personal facts behind a match, "
        "and added <font face='Courier'>/whoami</font> so the threshold can be tuned against real "
        "use rather than guessed at."),
    55: ("Refined it further: a session-level passcode instead of a soft decline &mdash; "
        "\"ENCODE\" if she doesn't hear the identity phrase first, and stop listening entirely on "
        "a wrong answer. Separately, \"DECODE\" should have her explain the tools reference PDF.",
        "Rebuilt around exactly this. Flagged plainly that plain-text passcodes in "
        "<font face='Courier'>config.py</font> are visible to anyone if the repo is ever made "
        "public, the same caution as the earlier key leak. DECODE reads the PDF's full text "
        "directly rather than through the chunked library search, since \"explain the whole "
        "thing\" doesn't fit that retrieval pattern. Found and fixed two real bugs while testing "
        "live, not in theory: the new gate was intercepting \"bye\" before the exit check ever "
        "ran, which combined with a separate bug (the keyboard reader spinning with no backoff "
        "once stdin hit EOF) to produce a genuine infinite loop — over 600,000 identical lines in "
        "under a minute. Also caught that saying the identity phrase and a request in one breath "
        "(\"it's Wade, play some music\") silently lost the identity claim, because the "
        "command-rewriting step ran before the gate ever saw the original words."),
    56: ("Try again.", "Re-ran the interrupted step and finished verifying both fixes live."),
    57: ("Flag the passcode.",
        "Moved <font face='Courier'>PASSCODE_UNLOCK</font> to an environment variable "
        "(<font face='Courier'>LIA_PASSCODE</font>), the same pattern as the API keys, since a "
        "plaintext passcode in a possibly-public repo defeats its own purpose. Found a real edge "
        "case while fixing it: an <i>unset</i> passcode would have locked Wade out with something "
        "that could never be typed correctly &mdash; the gate now disables itself gracefully "
        "instead, with a one-time log line saying so. Verified both the configured and "
        "unconfigured cases live, and confirmed the fix didn't get recorded verbatim into git the "
        "way the original key leak did."),
    58: ("Checked in that everything was still working, and asked for the PDFs and "
        "<font face='Courier'>requirements.txt</font> to be brought current.",
        "Audited <font face='Courier'>requirements.txt</font> against every actual import in the "
        "codebase (including the lazily-loaded ones inside functions, not just top-level) and "
        "found a real gap: <font face='Courier'>pypdf</font> &mdash; used by the library reader "
        "and now by DECODE too &mdash; had never been listed at all. A fresh install would have "
        "been missing it silently until the first PDF was opened. Added it. This document, and "
        "the rest."),
    43: ("Provided the OpenRouter key, confirmed amy as the voice, and asked for a latency "
        "check plus updated PDFs.",
        "Verified OpenRouter's live search with a real, current, cited answer a local or "
        "Groq-only model couldn't have known. Measured all four internet paths cleanly: weather "
        "~1.2s, connectivity check ~0.3s, Groq ~0.4&ndash;0.8s (fast, guesses), OpenRouter "
        "~2.4&ndash;4.0s (slower, because it's actually searching). Confirmed the new trigger "
        "checks add no measurable cost to ordinary conversation. This document, and the three "
        "others."),
    44: ("Good work.", "&mdash;"),
    45: ("Asked when a restart is actually needed versus just running her file, and how long "
        "to wait before speaking after one.",
        "Found a real gap while answering: nothing stopped her running twice if launched by hand "
        "while the autostart copy was still up &mdash; two processes would fight over the same "
        "microphone. Added a Windows single-instance lock, tested across genuinely separate "
        "processes including surviving a forced kill, before answering the actual question: no "
        "restart needed, just run <font face='Courier'>Lia.exe</font>; wait for her audible "
        "greeting, that's the cue she's ready."),
    46: ("Provided two new keys after the leak, and asked to properly ensure the gitignore "
        "actually works.",
        "Set both new keys as environment variables and verified them working. Found the "
        "gitignore alone had done nothing, since <font face='Courier'>.claude/</font>, "
        "<font face='Courier'>build/</font> and <font face='Courier'>dist/</font> were already "
        "tracked in git &mdash; untracked 2019 files with <font face='Courier'>git rm --cached</font> "
        "without touching a single file on disk, so the gitignore could actually take effect from "
        "here on."),
    47: ("Five conclusions from actually living with her: CPU usage over 50%, music and alarms "
        "that didn't work, remove KittenTTS, rename her to Wade, and get web search genuinely "
        "working.",
        "Measured the CPU complaint rather than guessing at it &mdash; the voice-detection "
        "library's ONNX runtime was spinning at ~290% of one core, continuously, while sitting "
        "completely idle. One environment variable fixed it, verified down to ~4% on the real "
        "packaged app. Built alarms and timers from nothing, including a background watchdog and "
        "persistence across restarts &mdash; caught and fixed a real parsing bug "
        "(\"for 10 minutes\" misread as a clock time) before it shipped. Made music commands admit "
        "honestly when there's nothing to play, after catching her invent a fake jazz playlist "
        "once during testing. Removed KittenTTS entirely, dropping the packaged app by 112MB. "
        "Renamed her to Wade. Broadened and verified the web-search path end to end with the new "
        "keys."),
    48: ("(a tool call was interrupted mid-turn)", "&mdash;"),
    49: ("Try again.", "Re-ran the interrupted step and continued the same round of fixes."),
    50: ("Asked for the PDFs to be brought current, plus a new study reference covering the "
        "tools used in the project &mdash; NumPy and the rest.",
        "This document, and the other three."),
    51: ("Wanted a Growth Log PDF tracking her build stages &mdash; making her, file reading, "
        "voices and ML models, controlling actions &mdash; to replace the old \"what we built\" "
        "PDF. Asked in passing whether she can actually control playback and volume, since she "
        "can't \"phase out of the hypervisor\" to do it herself.",
        "Built <font face='Courier'>Lia - Growth Log.pdf</font> across those four stages and "
        "deleted the old <font face='Courier'>Lia - What We Built.pdf</font> and its generator. "
        "Play/pause already worked through Windows' own media transport, but volume control "
        "genuinely didn't exist &mdash; built it against the Core Audio API via "
        "<font face='Courier'>pycaw</font> after confirming a simulated key-press approach "
        "silently did nothing at all."),
    52: ("Asked to keep the docs current from here on without being asked each time, and floated "
        "the idea of her telling your voice apart from anyone else's before committing to it.",
        "Weighed it rather than jumping to code &mdash; a wrong call cuts both ways, refusing "
        "you or trusting an impostor. Agreed a local voiceprint model was worth trying before "
        "any of the actions built on top of it."),
    53: ("Sketched the behaviour: greet normally when it's really him, go cautious rather than "
        "act normally if the voice doesn't match.",
        "Built <font face='Courier'>speaker_id.py</font> &mdash; a local voice-embedding model "
        "(3D-Speaker's CAM++ via <font face='Courier'>sherpa-onnx</font>, no PyTorch), enrolled "
        "from a few repetitions of his name and compared against everything said after."),
    54: ("When she doesn't recognise the voice, she shouldn't share personal details, and every "
        "action should be gated &mdash; not just the ones that happen to touch a browser.",
        "Gated media and volume commands on a voice mismatch, and held personal facts back from "
        "the reply context on the same signal."),
    55: ("The actual spec: lock every session by default. Say \"it's Wade\" or get asked for a "
        "spoken passcode (\"ENCODE\") &mdash; get it wrong and she stops listening outright. A "
        "second passcode (\"DECODE\") makes her read and explain a specific reference PDF.",
        "Built the session-level access gate &mdash; <font face='Courier'>check_access_gate()</font>, "
        "a hard lockout on a wrong passcode recoverable only by hand, and "
        "<font face='Courier'>explain_document()</font> for DECODE. Found and fixed two real bugs "
        "along the way: saying \"bye\" while locked was treated as a wrong passcode guess instead "
        "of exiting, and a second, unrelated bug where the keyboard-input thread spun at full CPU "
        "once stdin hit EOF."),
    56: ("(a tool call was interrupted mid-turn) Try again.",
        "Re-ran the interrupted step and caught a real bug this pass: saying the identity phrase "
        "in the same breath as a request (\"it's Wade, play some music\") was losing the identity "
        "claim, because the request got rewritten to a command first. Fixed by checking for the "
        "claim on the raw words, before any rewriting happens."),
    57: ("Flag the passcode.",
        "Moved <font face='Courier'>PASSCODE_UNLOCK</font> out of <font face='Courier'>config.py</font> "
        "and into an environment variable, the same pattern as the API keys &mdash; a plaintext "
        "passcode sitting in a file headed for a public repo isn't a passcode. Left unset, the "
        "gate now disables itself gracefully with a one-time log line, rather than locking anyone "
        "out with something that can never match."),
    58: ("Asked if everything was in order, and for the PDFs and <font face='Courier'>requirements.txt</font> "
        "to be brought current.",
        "Audited <font face='Courier'>requirements.txt</font> against every actual import across "
        "the codebase, including the lazy, function-local ones &mdash; found a real gap, "
        "<font face='Courier'>pypdf</font> was used but never listed. Regenerated the PDFs."),
    59: ("Floated camera access, flagging the security angle himself before asking.",
        "Talked it through rather than building anything &mdash; a live camera is a much bigger "
        "step than anything shipped so far, and the concern he raised on his own was the right "
        "one to weigh first."),
    60: ("Refined the camera idea to \"look at something, discuss it, maybe search online\" &mdash; "
        "asked to be corrected if internet access isn't real, and whether a week of daily use is "
        "a good idea before more changes.",
        "Confirmed the internet path is real but narrow: weather needs no key at all, factual "
        "lookups go through Groq or OpenRouter's actual web search once a key is set, nothing "
        "beyond that. Agreed the week-of-real-use idea was the right next step before adding "
        "anything else, especially to calibrate the voice-match threshold against real speech "
        "instead of guesses."),
    61: ("Asked whether she can search Reddit specifically and how to phrase it, and whether a "
        "Harry Potter epub just dropped into the library folder actually works.",
        "Found Reddit searches were only catching half the phrasings tried, since none of them "
        "contained any existing trigger phrase as a literal substring &mdash; added "
        "<font face='Courier'>\"reddit\"</font> itself as a trigger, verified against all four. "
        "Confirmed <font face='Courier'>.epub</font> had never been a supported format, built "
        "extraction for it, and verified it end to end in the packaged executable &mdash; which "
        "also settled a real question, that pure-Python packages like "
        "<font face='Courier'>pypdf</font> don't appear as files in a frozen build, so running "
        "the exe rather than searching its folder was the only real test."),
    62: ("Confirmed she can read now, and noted he'd keep PDF formats in mind.",
        "Confirmed it, with the practical detail: <font face='Courier'>.epub</font>, "
        "<font face='Courier'>.pdf</font>, <font face='Courier'>.txt</font> and "
        "<font face='Courier'>.md</font> all work, and \"read my files\" is what actually starts "
        "the indexing. Also cleared up a stale editor tab pointing at a test file that had "
        "already been deleted."),
    63: ("Pointed out Reddit was only an example &mdash; asked about YouTube, and whether "
        "controlling YouTube Music would work.",
        "Two separate answers, both verified rather than assumed. Added "
        "<font face='Courier'>\"youtube\"</font> as a lookup trigger, the same fix as Reddit, "
        "tested against four phrasings plus two that should <i>not</i> trigger. For playback: no "
        "change was needed &mdash; the media control never knew which app it was talking to in "
        "the first place, it asks Windows for whatever session is active. Confirmed live by "
        "checking it correctly picked up a browser tab, which is what actually proves it's "
        "app-agnostic rather than just Spotify-shaped."),
    64: ("Confirmed search alone is enough &mdash; no need for her to summarise what's said "
        "inside a video.",
        "Agreed, and left it there rather than building toward it."),
    65: ("Asked for the docs to be brought current, and whether he could call this assistant Cia.",
        "This document and the others. On the name: yes &mdash; and worth noting it fits the "
        "pattern, since Lia was named the same way."),
}

PHASES = {
    1: "Getting her talking",
    9: "Giving her a voice",
    13: "Turning her into an app",
    19: "Making her yours",
    26: "Fixing what the real world broke",
    32: "Writing it down",
    38: "Connecting her to the world",
    45: "What daily use surfaced",
    51: "Learning to recognise her",
    57: "Locking the gate down",
    60: "Deciding what's next",
}


def entry(n, ex):
    ask, did = SUMMARIES.get(n, ("—", "—"))
    left = Paragraph(
        f"<b><font size='11' color='#b4653a'>{n}</font></b><br/>"
        f"<font size='7' color='#6b6672'>{when(ex['ts'])}</font><br/>"
        f"<font size='7' color='#6b6672'>{len(ex['tools'])} tools</font>",
        S["LiaCell"])
    right = [
        Paragraph(f"<b>{ask}</b>", S["LiaCell"]),
        Spacer(1, 3),
        Paragraph(did, S["LiaCell"]),
    ]
    t = Table([[left, right]], colWidths=[20 * mm, 145 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("LEFTPADDING", (1, 0), (1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, RULE),
    ]))
    return KeepTogether([t])


def main():
    exchanges = group_exchanges(read_session(SESSION))

    story = []
    story.append(P("Every exchange in the build of Lia, one line for what was asked and a short "
                   "account of what came of it. Times and tool counts come from Claude Code's session "
                   "log; the full wording is in <i>Lia — Session Transcript</i>."))

    total = sum(len(e["tools"]) for e in exchanges)
    start_dt = dt.datetime.fromisoformat(exchanges[0]["ts"].replace("Z", "+00:00"))
    end_dt = dt.datetime.fromisoformat(exchanges[-1]["ts"].replace("Z", "+00:00"))
    elapsed_hours = (end_dt - start_dt).total_seconds() / 3600

    story.append(Table(
        [[Paragraph(f"<b>{len(exchanges)}</b><br/><font size='8' color='#6b6672'>exchanges</font>", S["LiaCell"]),
          Paragraph(f"<b>{total}</b><br/><font size='8' color='#6b6672'>tool calls</font>", S["LiaCell"]),
          Paragraph(f"<b>{when(exchanges[0]['ts'])}</b><br/><font size='8' color='#6b6672'>started</font>", S["LiaCell"]),
          Paragraph(f"<b>~{elapsed_hours:.0f} hrs</b><br/><font size='8' color='#6b6672'>elapsed</font>", S["LiaCell"])]],
        colWidths=[41 * mm] * 4,
        style=TableStyle([
            ("LINEABOVE", (0, 0), (-1, 0), 1, ACCENT),
            ("LINEBELOW", (0, 0), (-1, -1), 1, ACCENT),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ])))
    story.append(Spacer(1, 10))

    for n, ex in enumerate(exchanges, start=1):
        if n in PHASES:
            story.append(H1(PHASES[n]))
        story.append(entry(n, ex))

    story.append(Spacer(1, 14))
    story.append(H1("What it came to"))
    story.append(callout(
        "A companion called Wade knows by name, that starts at login, greets him, listens on an "
        "open mic, answers out loud, remembers across days, reads what he hands her, sets real "
        "alarms and timers, controls whatever's playing and the system volume, recognises his "
        "voice, and now gates every session behind either that or a spoken passcode &mdash; and "
        "never sends a word off the machine except the one narrow, optional exception she'll "
        "admit to: weather, and a question explicitly asked of the web. Thirteen modules, "
        "single-instance protected, running at roughly 4% of one core while idle instead of "
        "290%.<br/><br/>"
        "Still open: no way to forget, she still occasionally invents small details, fact keys "
        "drift, there are no tests, and voice recognition's real-world accuracy is honestly "
        "unverified &mdash; tested only against synthetic voices, tunable via "
        "<font face='Courier'>/whoami</font> once there's real data to tune it against. Two real "
        "bugs (an access gate that could trap you in the conversation, an identity phrase silently "
        "lost when combined with a request) were found only by actually running the thing, not by "
        "reasoning about the code &mdash; the same lesson as the CPU issue and the alarm parsing "
        "bug before it."))

    build(HERE / "Lia - Session Summary.pdf",
          "Lia — Session Summary",
          "The whole build, one line at a time.",
          story)


if __name__ == "__main__":
    main()
