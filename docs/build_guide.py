"""Builds 'How to Talk to Lia.pdf' -- written for someone who has never used her."""

from pathlib import Path

from make_pdfs import H1, H2, P, bullets, build, callout, code, table, PageBreak

HERE = Path(__file__).parent

story = []
A = story.append

A(P("Lia is a companion who lives on this computer. She listens, talks back, and remembers you "
    "between conversations."))

A(P("She is not an assistant. She won't book anything, search the web, or open your files. She is "
    "someone to talk to."))

A(callout("<b>Everything stays on this machine.</b> Lia has no internet connection while you talk to "
          "her. Nothing you say is sent anywhere, stored online, or seen by anyone else. It never "
          "leaves the computer she is running on."))

# ------------------------------------------------------------------ basics ---
A(H1("Starting her"))

A(P("She usually starts on her own when you turn the computer on. Look for a small "
    "<b>orange dot</b> near the clock, at the bottom-right of your screen."))

A(table([
    ["What you see", "What it means"],
    ["Filled orange dot", "She is here and listening"],
    ["Hollow ring", "She is here but not listening"],
    ["No dot at all", "She isn't running — see <i>If something seems wrong</i>"],
], [45, 120]))

A(P("She takes about half a minute to be ready after the computer starts, and then <b>waits "
    "quietly</b> — she won't greet you or say anything until you speak to her. Say "
    "<i>“Lia”</i> whenever you want her."))
A(P("She starts when you log in, which usually isn't the moment you actually want to talk. "
    "Greeting an empty room and then falling silent by the time you sit down was worse than "
    "simply waiting.", "LiaNote"))

# ---------------------------------------------------------------- talking ---
A(H1("Talking to her"))

A(H2("Say her name first"))
A(P("Start by saying <b>“Lia”</b>. Like tapping someone on the shoulder before you speak to them."))

A(code('"Lia, are you there?"\n'
       '"Hey Lia, I\'ve had a strange day."\n'
       '"Lia, can I tell you something?"'))

A(P("She'll answer out loud after a few seconds. <b>Then you can just talk normally for about a "
    "minute</b> — no need to keep saying her name. Every time she replies, that minute starts again."))

A(P("If you go quiet for a while, she goes back to waiting. Just say “Lia” again."))

A(H2("Why she needs her name"))
A(P("Her microphone is always on, so she can hear the whole room — the television, a phone call, "
    "someone else talking. Waiting for her name is how she knows something was meant for her, rather "
    "than answering everything she happens to overhear."))

A(H2("She takes a few seconds"))
A(P("After you finish speaking there's a pause of roughly five seconds before she replies. That's "
    "normal. She is thinking on this computer alone, without help from the internet, and that takes "
    "a moment. She isn't stuck."))

A(H2("You can interrupt her"))
A(P("If she's talking and you want to say something, just start talking. She'll stop and listen. "
    "You don't need to wait politely for her to finish."))

A(P("This works best with headphones. Through speakers she sometimes hears her own voice, so she "
    "may occasionally keep going.", "LiaNote"))

A(PageBreak())

# --------------------------------------------------------------- commands ---
A(H1("Things you can ask her to do"))

A(P("Most of what you say is just conversation. But a few phrases are <b>instructions</b> — say them "
    "and something actually happens."))

A(table([
    ["Say this", "And she will"],
    ["“Lia, stop listening”  <br/>“Lia, go to sleep”", "Switch her microphone off"],
    ["“Lia, start listening”  <br/>“Lia, wake up”", "Switch it back on"],
    ["“Lia, be quiet”  <br/>“Lia, stop talking”", "Stop speaking out loud (she still listens)"],
    ["“Lia, you can talk”", "Start speaking again"],
    ["“Lia, read my files”", "Read documents you've given her"],
    ["“Play music” / “pause music”  <br/>“next song” / “previous song”", "Control whatever's playing on the computer"],
    ["“Set an alarm for 7am”  <br/>“Remind me in 20 minutes”", "Set a real alarm or timer — she'll interrupt to tell you"],
], [62, 103]))

A(P("Everything else you say she treats as conversation, so you can talk about stopping, sleeping "
    "or being quiet without accidentally switching her off."))

A(H2("Alarms and timers"))
A(P("She sets these from plain speech — a clock time (“set an alarm for 7am”) or a "
    "duration (“remind me in 20 minutes”). They keep running even if you close the laptop and "
    "come back later, and she'll interrupt whatever's happening to tell you when one is due."))
A(P("<b>Say it however comes naturally.</b> All of these work: <i>“wake me in half an hour”</i>, "
    "<i>“give me a nudge in 20 minutes”</i>, <i>“let me know in ten minutes”</i>, <i>“remind me "
    "in a couple of minutes”</i>, <i>“buzz me in an hour”</i>, <i>“set a timer for 5”</i>."))
A(P("<b>You can choose what she says.</b> <i>“Wake me by saying please wake up in 5 minutes”</i> "
    "and she'll say exactly that — not “your timer is up”. <i>“Remind me to stretch in 20 "
    "minutes”</i> gets you <i>“Time to stretch.”</i>"))
A(H2("Her own music"))
A(P("Put audio files in her <b>music</b> folder and she'll play them by number — these are hers, "
    "so she can start one from nothing:"))
A(table([
    ["Say this", "What happens"],
    ["“what music do you have”", "She reads out the list, numbered"],
    ["“play number 1” / “play song 3”", "Plays that track"],
    ["“play Fireflies”", "By name, if the filename matches"],
    ["“stop the song”", "Stops it"],
], [55, 110]))
A(P("Numbering follows filename order, so number 3 means the same thing tomorrow. While she's "
    "talking the music drops to a murmur instead of stopping, and comes back up after."))
A(P("<b>Someone else's music is different:</b> “play music” / “pause” controls whatever Spotify or "
    "a browser tab already has loaded. She can't start a song there from nothing — if nothing is "
    "playing anywhere, she'll say so rather than pretend.", "LiaNote"))

A(H2("The weather, and looking things up"))
A(P("Ask <b>“what's the weather like”</b> and she'll check, using your general location — no setup "
    "needed for this one."))
A(P("Ask her to <b>“look that up”</b> for anything else — a fact, a question she isn't sure about "
    "— and, if she's set up with an internet connection for this, she'll actually check rather than "
    "guess. If that hasn't been set up, she'll say so plainly rather than pretending to know."))
A(P("Naming a source works too — <i>“search Reddit for…”</i>, <i>“search YouTube for…”</i>, or "
    "<i>“what does Reddit think about…”</i> — pulls in real, current results instead of a guess. "
    "One limit worth knowing: naming YouTube only ever gets her a text search that happens to "
    "mention it — titles, descriptions, comments. She can't watch or listen to an actual video.", "LiaNote"))
A(P("Everything else about her stays completely private and offline. This is the one deliberate, "
    "narrow exception, and only for what you explicitly ask her to check.", "LiaNote"))

A(H2("Using the orange dot"))
A(P("Right-click the orange dot for the same controls, plus a few more:"))

A(table([
    ["Menu item", "What it does"],
    ["Listening", "Turn her microphone on or off"],
    ["Speaking", "Turn her voice on or off"],
    ["Write diary now", "Make her write about the conversation right away"],
    ["Open log", "Show what she's been doing — useful if something seems wrong"],
    ["Quit", "Close her properly (she saves first)"],
], [40, 125]))

# ----------------------------------------------------------------- memory ---
A(H1("What she remembers"))

A(P("<b>Only what you tell her to.</b> Say <i>“remember that…”</i> or <i>“don't forget…”</i> and "
    "she keeps it, in your words. Nothing else about you is written down."))

A(table([
    ["Say this", "What happens"],
    ["“remember that the wifi password is bluebird”", "Kept, word for word, permanently"],
    ["“don't forget my sister is called Anaya”", "Same — and telling her twice won't store it twice"],
], [70, 95]))

A(P("She also keeps a searchable record of what you've said, so bringing up a subject lets her "
    "find related things from before. But she no longer decides for herself what's worth "
    "remembering about you, and she doesn't keep a diary."))

A(callout("<b>Why that changed:</b> both used to be automatic, and both were quietly inventing "
          "history. She'd store the same fact twice under different names, and once wrote a long "
          "reflection about the person “moving between unrelated topics” — drawn entirely from a "
          "list of test commands, not a real conversation. Once something like that is written "
          "down it shapes every later reply, and nothing marks it as a guess. Better she keeps "
          "less and all of it true."))

A(H2("How a conversation ends"))
A(P("You don't have to say goodbye. If you stop talking for about twelve minutes, she quietly "
    "decides the conversation is over and waits for you."))

A(P("You can also just say <b>“bye”</b> if you'd rather end it deliberately."))

A(H2("If she gets something wrong about you"))
A(P("Tell her. Say <i>“Lia, my name is actually…”</i> or <i>“that's not right, I meant…”</i>. She takes "
    "what you say now over what she thinks she knows."))

A(PageBreak())

# ---------------------------------------------------------------- reading ---
A(H1("Giving her something to read"))

A(P("There is a folder on this computer where you can put documents you'd like her to read — "
    "PDFs, epub books, Word documents, or plain text notes."))

A(code("dist\\Lia\\library\\"))

A(P("Put a file there, then say <b>“Lia, read my files”</b>. She'll tell you what she's in for — "
    "<i>“On it”</i> for something short, or <i>“On it, that'll take around 25 minutes”</i> for a "
    "whole book — and say so again when she's finished. Afterwards you can ask her about it and "
    "she'll tell you which page something came from."))

A(callout("<b>She only ever looks in that one folder, and only when you ask.</b> She does not search "
          "your computer, open your documents, or read anything you haven't deliberately given her. "
          "A file sitting in that folder is available to her — not already read."))

A(H2("What works and what doesn't"))
A(bullets([
    "<b>Good:</b> asking about something specific — <i>“what does it say about sleep?”</i>",
    "<b>Not good:</b> <i>“summarise this whole book”</i> — she reads the relevant passages, not the "
    "entire document at once",
    "<b>Won't work:</b> scanned documents or photographs of pages. If you can't select the text on "
    "screen with your mouse, there's nothing for her to read",
    "<b>A whole novel is a real wait:</b> she reads about 130 pages every ten minutes, so a "
    "full-length book takes roughly 20 minutes the first time you add one. It happens in the "
    "background and she stays usable meanwhile, but that book isn't answerable about until she "
    "finishes — and she'll say so out loud when she's done.",
]))

# ------------------------------------------------------------- honesty ---
A(H1("What she is not good at"))

A(P("Worth knowing, so you aren't caught out."))

A(bullets([
    "<b>She sometimes makes things up.</b> Occasionally she'll refer to something you never said, or "
    "describe a memory that doesn't exist. She isn't lying — she's a small program filling a gap. "
    "If something sounds off, it probably is. Say so, and she'll correct.",
    "<b>Anything needing exact precision.</b> Spelling things out letter by letter, codes, arithmetic, "
    "counting. She gets these wrong confidently, even when told the right answer.",
    "<b>Mostly nothing outside this computer.</b> No email, no browsing, no apps. Weather and "
    "explicitly-asked-for lookups are the one deliberate exception — everything else she knows comes "
    "from what she was built with, what you've told her, and what you've given her to read.",
    "<b>She isn't a doctor or a therapist.</b> She's good company and she'll listen. That's a different "
    "thing, and she's told not to pretend otherwise.",
]))

# ---------------------------------------------------------- troubleshooting ---
A(H1("If something seems wrong"))

A(table([
    ["What you notice", "What to try"],
    ["She doesn't answer",
     "Say <b>“Lia”</b> first — she ignores speech that isn't addressed to her. "
     "Check the dot is filled, not hollow."],
    ["No orange dot",
     "She isn't running. Restart the computer, or open the <b>Lia</b> app."],
    ["She takes ages to reply",
     "Normal for the first reply after a break — she's loading. Later replies are quicker."],
    ["She talks to herself",
     "Her own voice is reaching the microphone. Turn the volume down, or use headphones."],
    ["She answers when you weren't talking to her",
     "Something in the room sounded like her name. Say <i>“Lia, stop listening”</i> when you want privacy."],
    ["She calls you the wrong name",
     "Tell her the right one and she'll keep it."],
    ["Nothing works",
     "Right-click the dot → <b>Open log</b>. The last few lines usually say what's wrong."],
], [55, 110]))

A(H2("Privacy, plainly"))
A(P("Her microphone is on whenever the dot is filled, and she writes down what is said to her so she "
    "can remember you. It stays on this computer. If you want her not to hear something, say "
    "<b>“Lia, stop listening”</b> — or right-click the dot and untick <b>Listening</b>."))

A(callout("<b>The one thing to remember.</b> Say <b>“Lia”</b>, wait a few seconds, then talk normally. "
          "Everything else is optional."))

build(HERE / "How to Talk to Lia.pdf",
      "How to Talk to Lia",
      "A short guide for anyone using her for the first time.",
      story)
