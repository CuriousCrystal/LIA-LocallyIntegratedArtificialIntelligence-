"""Builds 'How to Talk to Lia.pdf' -- written for someone who has never used her."""

from pathlib import Path

from make_pdfs import H1, H2, P, bullets, build, callout, code, table, PageBreak

HERE = Path(__file__).parent

story = []
A = story.append

A(P("Lia is a companion who lives on this computer. She listens, talks back, and keeps hold of "
    "anything you ask her to remember."))

A(P("She is not an assistant. She won't book anything, search the web, or open your files. She is "
    "someone to talk to."))

A(callout("<b>What she hears, and where it goes.</b> Your voice never leaves this computer — it is "
          "turned into text here, by this machine. But to think of a reply, <b>the words of your "
          "conversation are sent to a service on the internet</b>, because the part of her that "
          "does the thinking is too large to run on this laptop. Her memory of you, your documents, "
          "and the recording itself all stay here."))

A(callout("<b>Right now, talking to her means typing.</b> A small window opens alongside the cat "
          "in the tray, and that's the current way in — type a line, press Enter, same conversation "
          "either way. Her microphone is off while this is how she's being worked with. Everything "
          "below about the tray icon and about voice describes how she behaves once listening is "
          "switched back on, which the tray's own <b>Listening</b> option does instantly."))

# ------------------------------------------------------------------ basics ---
A(H1("Starting her"))

A(P("She usually starts on her own when you turn the computer on. Look for a small "
    "<b>purple cat</b> near the clock, at the bottom-right of your screen."))

A(table([
    ["What you see", "What it means"],
    ["Filled purple cat", "She is here and listening"],
    ["Hollow cat outline", "She is here but not listening"],
    ["No cat at all", "She isn't running — see <i>If something seems wrong</i>"],
], [45, 120]))

A(P("Once listening is on: she takes about half a minute to be ready after the computer starts, "
    "and then <b>waits quietly</b> — she won't greet you or say anything until you speak to her. "
    "Say <i>“Lia”</i> whenever you want her."))
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
    ["“Play number 1” / “what music do you have”", "Play music from her own folder"],
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
A(H2("Music"))
A(P("Put audio files in her <b>music</b> folder and she'll play them by number:"))
A(table([
    ["Say this", "What happens"],
    ["“what music do you have”", "She reads out the list, numbered"],
    ["“play number 1” / “play song 3”", "Plays that track"],
    ["“play Fireflies”", "By name, if the filename matches"],
    ["“stop the song”", "Stops it"],
], [55, 110]))
A(P("Numbering follows filename order, so number 3 means the same thing tomorrow. While she's "
    "talking the music drops to a murmur instead of stopping, and comes back up after."))
A(P("She plays <b>only her own files</b>. She can't control Spotify, YouTube or anything else "
    "playing elsewhere on the computer — that was built once and removed, because it could "
    "operate someone else's player but never actually start anything.", "LiaNote"))

A(H2("A second opinion"))
A(P("She can put a question to a different, named model and tell you what it said — a second "
    "opinion, not a replacement for her own answer."))
A(table([
    ["Say this", "What happens"],
    ["“ask cat for a suggestion on X”", "Cat answers, and she relays it: “Cat says: …”"],
    ["“ask fox what she thinks about this”", "Same, from a different model"],
    ["“who can you ask”", "Lists who's available"],
], [70, 95]))
A(P("Two names today — cat, fox — each a different free model. She only does this when "
    "asked by name; it never happens on its own. See <i>Privacy, plainly</i> below for what "
    "that question actually costs.", "LiaNote"))

A(H2("Using the cat in the tray"))
A(P("Right-click the cat for the same controls, plus a few more:"))

A(table([
    ["Menu item", "What it does"],
    ["Listening", "Turn her microphone on or off"],
    ["Speaking", "Turn her voice on or off"],
    ["End conversation now", "Close out the current conversation"],
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

A(P("<b>The conversation itself isn't kept.</b> Once you've finished talking, what was said is gone "
    "— unless you asked her to remember a particular thing. She doesn't decide for herself what's "
    "worth keeping about you, and she doesn't write a diary."))

A(P("While you're still talking she does follow the thread, so you can say “what did I just say?” "
    "and she'll know. It's only between conversations that it doesn't carry over."))

A(callout("<b>Why it works this way:</b> all of it used to be automatic, and all of it was quietly "
          "inventing history. She'd store the same fact twice under different names, and once wrote "
          "a long reflection about the person “moving between unrelated topics” — drawn entirely "
          "from a list of test commands, not a real conversation. She also used to search old "
          "conversations, which meant a half-finished thought from weeks ago could resurface in a "
          "conversation it had nothing to do with. Once something like that is written down it "
          "shapes every later reply, and nothing marks it as a guess. Better she keeps less and "
          "all of it true."))

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
    "<b>She can't do things outside this computer.</b> No email, no browsing, no apps, no weather, "
    "no looking things up. She thinks with help from the internet, but she can't <i>use</i> it — "
    "she can't go and find something out for you. What she knows comes from what she was built "
    "with, what you've told her, and what you've given her to read.",
    "<b>She needs a connection to be at her best.</b> If the internet drops, she keeps talking, "
    "using the smaller version of herself that lives on this computer. She'll seem a little less "
    "sharp for a while. She'll say so in her log rather than pretending nothing happened.",
    "<b>She isn't a doctor or a therapist.</b> She's good company and she'll listen. That's a different "
    "thing, and she's told not to pretend otherwise.",
]))

# ---------------------------------------------------------- troubleshooting ---
A(H1("If something seems wrong"))

A(table([
    ["What you notice", "What to try"],
    ["She doesn't answer to typing",
     "Check the panel window is actually the one focused — click into its text line first."],
    ["She doesn't answer to voice",
     "Check listening is actually on right now (see the callout above) — "
     "say <b>“Lia”</b> first either way, she ignores speech that isn't addressed to her, "
     "and check the cat is filled, not hollow."],
    ["No cat in the tray",
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
     "Right-click the cat → <b>Open log</b>. The last few lines usually say what's wrong."],
], [55, 110]))

A(H2("Privacy, plainly"))
A(P("Her microphone is on whenever the cat is filled — right now, per the callout near the start "
    "of this guide, it may not be. This is the part worth reading properly regardless, because it "
    "changed."))
A(table([
    ["This stays on the computer", "This is sent away"],
    ["The recording of your voice — it is turned into text here, and the audio is never uploaded",
     "<b>The words of your conversation</b>, sent to an online service so it can work out a reply"],
    ["Everything she remembers about you", "The last few things said, so the reply makes sense in context"],
    ["Your documents, and the search through them", "Passages from a document, but only when you ask her about one"],
    ["Everything else you say to her", "Only a question you explicitly aim at “cat” or “fox” — "
     "sent to that specific model, and nothing else about the conversation goes with it"],
], [82, 83]))
A(P("The thinking happens online because that part of her is far too large to run on a laptop. "
    "Everything else — hearing you, her voice, her memory, your files — happens here."))
A(P("If you want her not to hear something at all, say <b>“Lia, stop listening”</b>, or right-click "
    "the cat and untick <b>Listening</b>. She can also be set back to thinking entirely on this "
    "computer, which is private but noticeably less clever — that is "
    "<font face='Courier'>CLOUD_CHAT_ENABLED</font> in her settings."))

A(callout("<b>The one thing to remember.</b> Type into the panel, or once listening is on say "
          "<b>“Lia”</b> and wait a few seconds, then talk normally. Everything else is optional."))

build(HERE / "How to Talk to Lia.pdf",
      "How to Talk to Lia",
      "A short guide for anyone using her for the first time.",
      story)
