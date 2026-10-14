"""Turns approved tickets into one prompt for the programmer agent.

The intro comes from prompts/handoff.md, so you can change the instructions without touching code.
Paths in the prompt are absolute: the agent opens the screenshots itself.
"""
import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIND = {"bug": "Bug", "change": "Change", "polish": "Polish", "crash": "Crash", "idea": "Idea"}


def mmss(t):
    try:
        t = max(0, int(round(float(t))))
    except Exception:
        return "?"
    return f"{t // 60}:{t % 60:02d}"


def build_of(t):
    dev = t.get("device") or "phone"
    a = f", Android {t['android']}" if t.get("android") else ""
    return f"{t.get('version') or 'unknown version'} on {dev}{a}"


def ticket_block(t, inbox, show_build):
    lines = [f"## {t['id']} · {t['title']}",
             f"{KIND.get(t.get('kind'), 'Change')} · {t.get('priority', 'normal')} priority", ""]

    def add(label, val):
        val = (val or "").strip()
        if val:
            lines.append(f"- **{label}:** {val}")

    if show_build:
        add("Build", build_of(t))
    add("Where", t.get("where"))
    add("Now", t.get("now"))
    add("Want", t.get("want"))
    steps = [s for s in t.get("steps") or [] if s.strip()]
    if steps:
        lines.append("- **Steps:**")
        lines += [f"  {i}. {s.strip()}" for i, s in enumerate(steps, 1)]
    add("Done when", t.get("done_when"))
    q = t.get("quote") or {}
    if (q.get("text") or "").strip():
        lines.append(f"- **I said** ({mmss(q.get('t'))} in the clip): \"{q['text'].strip()}\"")
    add("My note", t.get("note"))
    for s in t.get("shots") or []:
        if s.get("use", True):
            cap = s.get("caption", "").strip().rstrip(".")
            cap = (cap + "." if cap else "") + (" The red box marks it." if s.get("box") else "")
            lines.append(f"- **Screenshot** ({mmss(s.get('t'))}): `{inbox / s['file']}` {cap}".rstrip())
    m = t.get("moment") or {}
    lines.append(f"- **Clip:** `{inbox / t['clip']}`, {mmss(m.get('from'))} to {mmss(m.get('to'))}")
    return "\n".join(lines)


def render(tickets, inbox):
    inbox = Path(inbox)
    first = tickets[0]
    builds = {build_of(t) for t in tickets}
    one_build = len(builds) == 1
    try:
        intro = (HERE / "prompts" / "handoff.md").read_text().strip()
    except Exception:
        intro = "These are QA tickets for {{game}}. I approved each one.\n\n{{build}}"
    n = len(tickets)
    fill = {
        "game": first["game"],
        "count": f"{n} ticket{'s' if n != 1 else ''}",
        "date": f"{datetime.date.today():%-d %b %Y}",
        "build": f"Build tested: {build_of(first)}." if one_build else "The build is listed on each ticket.",
        "ids": ", ".join(t["id"] for t in tickets),
    }
    for k, v in fill.items():
        intro = intro.replace("{{" + k + "}}", v)
    body = "\n\n---\n\n".join(ticket_block(t, inbox, not one_build) for t in tickets)
    return f"{intro}\n\n---\n\n{body}\n"
