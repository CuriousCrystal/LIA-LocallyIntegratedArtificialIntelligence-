"""
Builds 'Lia - Session Transcript.pdf' from the real Claude Code session log.

Reads the .jsonl Claude Code writes for this project, not a reconstruction, so
what lands in the PDF is what was actually said.
"""

import html
import json
import re
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

from make_pdfs import ACCENT, CODE_BG, INK, MUTED, RULE, S, build

HERE = Path(__file__).parent

# The build session this document and the Session Summary are made from was
# written under a different Windows account, which was lost when the laptop was
# reformatted in August 2026. Both PDFs are therefore frozen: the copies
# committed in this folder are the only surviving record of that conversation.
#
# Deliberately still a single named file rather than "whatever session log is
# present". Globbing the folder would find some other, unrelated conversation
# and cheerfully rebuild the transcript from it, overwriting the real one with
# something that only looks right. Failing loudly is the correct behaviour here.
SESSION = (Path.home() / ".claude" / "projects" / "d--Visuals-AI"
           / "ca0a2e3f-a2a4-45b0-9f00-0c3be7db4c08.jsonl")

USER_BG = colors.HexColor("#eef1f6")


# ------------------------------------------------------------- extraction ---

def read_session(path: Path):
    """Ordered (kind, timestamp, text, tool_names) entries."""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue

            kind, msg = d.get("type"), d.get("message")
            if kind not in ("user", "assistant") or not isinstance(msg, dict):
                continue

            content = msg.get("content")
            text, tools = "", []
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tools.append(block.get("name", "tool"))
                text = "\n".join(p for p in parts if p)

            if text.strip() or tools:
                out.append((kind, d.get("timestamp"), text.strip(), tools))
    return out


IDE_TAG = re.compile(r"<(ide_opened_file|ide_selection)>.*?</\1>", re.S)
REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
COMMAND = re.compile(r"<command-(name|message|args)>.*?</command-\1>", re.S)
# Claude Code inserts this whole-message preamble when context gets compacted --
# it's the harness resuming itself, not anything typed. It also runs to tens of
# thousands of characters, which is a single unsplittable table cell taller than
# a page and crashes the PDF layout, so it can't just be left in like a long
# real message would be.
CONTINUATION = re.compile(
    r"^This session is being continued from a previous conversation.*", re.S
)
# Local slash-commands (/model and friends) leave their own caveat banner and
# stdout in the log. The harness talking to itself, not anything typed.
LOCAL_CMD = re.compile(
    r"<local-command-(caveat|stdout)>.*?</local-command-\1>", re.S
)


def clean_user(text: str) -> tuple[str, list[str]]:
    """Strip editor noise, keeping a short note of what it was."""
    notes = []
    for m in IDE_TAG.finditer(text):
        blob = m.group(0)
        if "ide_opened_file" in blob:
            f = re.search(r"opened the file ([^\s]+)", blob)
            if f:
                notes.append(f"opened {Path(f.group(1)).name}")
        else:
            notes.append("had a selection in the editor")
    text = IDE_TAG.sub("", text)
    text = REMINDER.sub("", text)
    text = COMMAND.sub("", text)
    text = CONTINUATION.sub("", text)
    text = LOCAL_CMD.sub("", text)
    return text.strip(), notes


def group_exchanges(entries):
    """One entry per user turn, with everything Lia's build did in response."""
    exchanges, current = [], None
    for kind, ts, text, tools in entries:
        if kind == "user":
            body, notes = clean_user(text)
            if not body:
                continue                      # tool results, not something typed
            if current:
                exchanges.append(current)
            current = {"ts": ts, "user": body, "notes": notes, "reply": [], "tools": []}
        elif current is not None:
            if text:
                current["reply"].append(text)
            current["tools"].extend(tools)
    if current:
        exchanges.append(current)
    return exchanges


# ------------------------------------------------------------- formatting ---

INLINE_CODE = re.compile(r"`([^`]+)`")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
ITALIC = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def inline(text: str) -> str:
    text = html.escape(text)
    text = LINK.sub(r"\1", text)
    text = INLINE_CODE.sub(r"<font face='Courier' size='8.5'>\1</font>", text)
    text = BOLD.sub(r"<b>\1</b>", text)
    text = ITALIC.sub(r"<i>\1</i>", text)
    return text


def code_block(lines):
    body = "\n".join(lines)
    if not body.strip():
        return None
    # Long output lines would otherwise run off the page.
    body = "\n".join(ln[:110] for ln in body.splitlines()[:40])
    t = Table([[Paragraph(f"<font face='Courier' size='7.5'>"
                          f"{html.escape(body).replace(chr(10), '<br/>')}</font>", S["LiaCell"])]],
              colWidths=[160 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBEFORE", (0, 0), (0, -1), 1.5, ACCENT),
    ]))
    return t


def md_flowables(text: str):
    """Good-enough markdown rendering: headings, bullets, code, tables."""
    flow, para, fence, rows = [], [], None, []

    def flush_para():
        if para:
            flow.append(Paragraph(inline(" ".join(para)), S["LiaBody"]))
            para.clear()

    def flush_rows():
        if not rows:
            return
        header = [c.strip() for c in rows[0].strip("|").split("|")]
        body = [[c.strip() for c in r.strip("|").split("|")] for r in rows[2:]]
        width = 160 / max(len(header), 1)
        data = [[Paragraph(inline(c), S["LiaCellHead"]) for c in header]]
        data += [[Paragraph(inline(c), S["LiaCell"]) for c in r] for r in body if any(r)]
        if len(data) > 1:
            t = Table(data, colWidths=[width * mm] * len(header))
            t.setStyle(TableStyle([
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT),
                ("LINEBELOW", (0, 1), (-1, -2), 0.3, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            flow.append(t)
            flow.append(Spacer(1, 6))
        rows.clear()

    for raw in text.splitlines():
        line = raw.rstrip()

        if line.strip().startswith("```"):
            if fence is None:
                flush_para(); flush_rows()
                fence = []
            else:
                block = code_block(fence)
                if block is not None:
                    flow.extend([block, Spacer(1, 6)])
                fence = None
            continue
        if fence is not None:
            fence.append(line)
            continue

        if line.startswith("|"):
            flush_para()
            rows.append(line)
            continue
        flush_rows()

        if not line.strip():
            flush_para()
            continue

        if line.startswith("#"):
            flush_para()
            level = len(line) - len(line.lstrip("#"))
            flow.append(Paragraph(inline(line.lstrip("# ").strip()),
                                  S["LiaH2"] if level >= 3 else S["LiaH1"]))
            continue

        m = re.match(r"^\s*([-*]|\d+\.)\s+(.*)", line)
        if m:
            flush_para()
            flow.append(Paragraph(f"<bullet>&bull;</bullet>&nbsp;{inline(m.group(2))}",
                                  S["LiaBullet"]))
            continue

        para.append(line.strip())

    flush_para()
    flush_rows()
    if fence:
        block = code_block(fence)
        if block is not None:
            flow.append(block)
    return flow


def when(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%d %b, %H:%M")
    except Exception:
        return ""


def user_block(text: str, ts: str, notes: list[str], n: int):
    label = f"<b>#{n}</b> &nbsp; {when(ts)}"
    if notes:
        label += f" &nbsp;<font color='#6b6672'>({'; '.join(notes)})</font>"
    inner = [
        Paragraph(f"<font size='7.5' color='#6b6672'>{label}</font>", S["LiaCell"]),
        Spacer(1, 3),
        Paragraph(f"<b>{html.escape(text)}</b>", S["LiaBody"]),
    ]
    t = Table([[inner]], colWidths=[165 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), USER_BG),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, colors.HexColor("#5b6b8c")),
    ]))
    return KeepTogether([t, Spacer(1, 8)])


# ------------------------------------------------------------------ build ---

def main():
    if not SESSION.exists():
        raise SystemExit(f"session log not found: {SESSION}")

    exchanges = group_exchanges(read_session(SESSION))

    story = []
    story.append(Paragraph(
        "The full working session on Lia, taken from Claude Code's own session log rather than "
        "written from memory. Your messages are shown in full; replies are included as written, "
        "with the tool calls behind them summarised.", S["LiaBody"]))

    total_tools = sum(len(e["tools"]) for e in exchanges)
    first, last = exchanges[0]["ts"], exchanges[-1]["ts"]
    story.append(Table(
        [[Paragraph(f"<b>{len(exchanges)}</b><br/><font size='8' color='#6b6672'>exchanges</font>", S["LiaCell"]),
          Paragraph(f"<b>{total_tools}</b><br/><font size='8' color='#6b6672'>tool calls</font>", S["LiaCell"]),
          Paragraph(f"<b>{when(first)}</b><br/><font size='8' color='#6b6672'>started</font>", S["LiaCell"]),
          Paragraph(f"<b>{when(last)}</b><br/><font size='8' color='#6b6672'>last message</font>", S["LiaCell"])]],
        colWidths=[41 * mm] * 4,
        style=TableStyle([
            ("LINEABOVE", (0, 0), (-1, 0), 1, ACCENT),
            ("LINEBELOW", (0, 0), (-1, -1), 1, ACCENT),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ])))
    story.append(Spacer(1, 14))

    for n, ex in enumerate(exchanges, start=1):
        story.append(user_block(ex["user"], ex["ts"], ex["notes"], n))

        if ex["tools"]:
            counts = {}
            for t in ex["tools"]:
                counts[t] = counts.get(t, 0) + 1
            summary = ", ".join(f"{k}&times;{v}" if v > 1 else k
                                for k, v in sorted(counts.items(), key=lambda x: -x[1]))
            story.append(Paragraph(
                f"<font size='8' color='#6b6672'><i>{len(ex['tools'])} tool calls: {summary}</i></font>",
                S["LiaCell"]))
            story.append(Spacer(1, 6))

        for chunk in ex["reply"]:
            story.extend(md_flowables(chunk))

        story.append(Spacer(1, 4))
        story.append(Table([[""]], colWidths=[165 * mm],
                           style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE)])))
        story.append(Spacer(1, 12))

    build(HERE / "Lia - Session Transcript.pdf",
          "Lia — Session Transcript",
          "The complete build conversation, from Claude Code's session log.",
          story)


if __name__ == "__main__":
    main()
