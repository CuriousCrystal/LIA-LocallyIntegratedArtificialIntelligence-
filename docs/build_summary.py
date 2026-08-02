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
    43: ("Provided the OpenRouter key, confirmed amy as the voice, and asked for a latency "
        "check plus updated PDFs.",
        "Verified OpenRouter's live search with a real, current, cited answer a local or "
        "Groq-only model couldn't have known. Measured all four internet paths cleanly: weather "
        "~1.2s, connectivity check ~0.3s, Groq ~0.4&ndash;0.8s (fast, guesses), OpenRouter "
        "~2.4&ndash;4.0s (slower, because it's actually searching). Confirmed the new trigger "
        "checks add no measurable cost to ordinary conversation. This document, and the three "
        "others."),
}

PHASES = {
    1: "Getting her talking",
    9: "Giving her a voice",
    13: "Turning her into an app",
    19: "Making her yours",
    26: "Fixing what the real world broke",
    32: "Writing it down",
    38: "Connecting her to the world",
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
        "A companion that starts at login, greets you by name, listens on an open mic, answers out "
        "loud, remembers across days, reads what you hand her, and never sends a word off the "
        "machine &mdash; except the one narrow, optional exception she'll now admit to: weather, "
        "and a question you explicitly ask her to look up online. Eleven modules.<br/><br/>"
        "Still open: no way to forget, she still occasionally invents small details, fact keys drift, "
        "there are no tests, and the packaged app is carrying ~77MB of a dependency "
        "(<font face='Courier'>spacy</font>) that nothing in it actually needs by default."))

    build(HERE / "Lia - Session Summary.pdf",
          "Lia — Session Summary",
          "The whole build, one line at a time.",
          story)


if __name__ == "__main__":
    main()
