"""Parse NSDA national debate topics from https://www.speechanddebate.org/topics/.

    python -m scythe.topics_nsda topics.html > scythe/data/nsda_topics.json

Reads the "Past Topics - <event>" toggles (Policy, Lincoln-Douglas, Public Forum, Big Questions)
into records: {event, season, period, resolution, slug}. Stdlib only, so update tooling can reuse
`parse()` on freshly downloaded pages.
"""

import html
import json
import re
import sys

EVENTS = {
    "Policy Debate": "policy",
    "Lincoln-Douglas Debate": "ld",
    "Public Forum Debate": "pf",
    "Big Questions": "bq",
}
SLUG_MAX = 44
EVENT_SHORT = {"policy": "cx", "ld": "ld", "pf": "pf", "bq": "bq"}
_TAG = re.compile(r"<[^>]+>")
_SEASON = re.compile(r"(\d{4})\s*[-–]\s*(\d{4})")
_DASH = re.compile(r"\s+[–—-]\s+")
_STOP = {"the", "a", "an", "of", "in", "on", "to", "and", "or", "its", "should", "ought", "be", "is", "that",
         "resolved", "united", "states", "federal", "government", "substantially", "significantly", "increase",
         "for", "with", "by", "one", "more", "following", "than", "s"}


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", fragment))).strip()


def slugify(event: str, season: str, period: str, resolution: str) -> str:
    """Short, label-safe id, e.g. `ld-2024-25-novdec-wealth-tax` (<= 44 chars, so `topic:<slug>` fits a 50-char GitHub label)."""
    y = _SEASON.search(season)
    season_part = f"{y.group(1)}-{y.group(2)[2:]}" if y else re.sub(r"\W+", "", season)
    per = re.sub(r"[^a-z]", "", period.lower())
    per = {"septemberoctober": "sepoct", "novemberdecember": "novdec", "januaryfebruary": "janfeb",
           "marchapril": "marapr"}.get(per, per[:8])
    if per.startswith("nationals") or "national" in per:
        per = "nats"
    words = [w for w in re.findall(r"[a-z]+", resolution.lower().replace("resolved:", "")) if w not in _STOP]
    head = "-".join(p for p in (EVENT_SHORT[event], season_part, per) if p)
    tail = ""
    for w in words:
        nxt = f"{tail}-{w}" if tail else w
        if len(head) + 1 + len(nxt) > SLUG_MAX:
            break
        tail = nxt
    return f"{head}-{tail}" if tail else head


def _sections(page: str):
    for m in re.finditer(r"Past Topics - ([^<]+)</h5>", page):
        name = html.unescape(m.group(1)).strip()
        if name not in EVENTS:
            continue
        end = page.find("et_pb_toggle_title", m.end())
        yield EVENTS[name], page[m.end(): end if end > 0 else len(page)]


def _split(item: str) -> tuple[str, str]:
    text = _text(item).lstrip("°").strip()
    i = text.find("Resolved")
    if i > 0:
        return _DASH.sub(" ", text[:i]).strip(" –—-:"), text[i:].strip()
    return "", text


def parse(page: str) -> list[dict]:
    out, seen = [], set()
    for event, body in _sections(page):
        if event == "bq":
            for season, res in re.findall(r"<strong>\s*(\d{4}\s*-\s*\d{4})\s*</strong>\s*[–—-]\s*(.*?)(?:</p>|</div>)",
                                          html.unescape(body), re.S):
                out.append(_record(event, season.replace(" ", ""), "", _text(res)))
            continue
        for season, chunk in re.findall(r"<h5>\s*([^<]+?)\s*</h5>(.*?)(?=<h5>|$)", body, re.S):
            for item in re.findall(r"<(?:li|p)>(.*?)</(?:li|p)>", chunk, re.S):
                period, resolution = _split(item)
                if resolution.lower().startswith("resolved"):
                    out.append(_record(event, season, period, resolution))
    deduped = []
    for r in out:
        if r["slug"] in seen:  # identical resolution repeated on the page
            continue
        seen.add(r["slug"])
        deduped.append(r)
    return deduped


def _record(event: str, season: str, period: str, resolution: str) -> dict:
    resolution = re.sub(r"\s+", " ", resolution).strip()
    return {"event": event, "season": season.strip(), "period": period, "resolution": resolution,
            "slug": slugify(event, season, period, resolution)}


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        records = parse(f.read())
    json.dump(records, sys.stdout, ensure_ascii=False, indent=1)
    print(file=sys.stderr)
    print({e: sum(r["event"] == e for r in records) for e in EVENTS.values()}, file=sys.stderr)
