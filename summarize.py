#!/usr/bin/env python3
"""Add a short plain-English summary to each NOTAM record in data/notams/.

Only records without a summary, or whose NOTAM changed since it was summarised, are sent.
Summaries are written by an AI model (Anthropic API) from the NOTAM text and fields only.
They can contain mistakes: the website always shows them next to the full NOTAM text.

Needs the ANTHROPIC_API_KEY environment variable; without it, the script does nothing.
Standard library only. Writes "summaries_written=N" to $GITHUB_OUTPUT inside GitHub Actions.
"""
import glob
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
REC_DIR = os.path.join(ROOT, "data", "notams")
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("SUMMARY_MODEL", "claude-haiku-5-5")
BATCH = 25                                            # NOTAMs per request
MAX_PER_RUN = int(os.environ.get("SUMMARY_LIMIT", "400"))   # cost cap per run
MAX_LEN = 240                                         # characters per summary

PROMPT = """You write one-sentence plain-English summaries of UK NOTAMs for a public archive website.

Rules:
- One sentence, at most 25 words, British English, no abbreviations a member of the public would not know.
- Say what it is (e.g. crane, airspace restriction, runway closure, drone activity), where (use place or aerodrome names written in the NOTAM; otherwise the ICAO location code) and the key figure if any (height, radius, altitude).
- Do not add dates or times unless the NOTAM has a daily schedule worth mentioning.
- Use only facts in the NOTAM. Never guess a place name from coordinates. If something is unclear, leave it out.
- No advice, no opinions, no "This NOTAM".

Return only a JSON object mapping each NOTAM id to its summary, e.g. {"A1234/26": "Crane up to 145 ft near Prestwick Airport."}

NOTAMs:
"""


def fingerprint(r):
    """Changes when the NOTAM content changes, so the summary is redone."""
    src = json.dumps([r.get(k) for k in ("text", "loc", "q", "lower", "upper", "sched", "radius")], ensure_ascii=False)
    return hashlib.sha1(src.encode("utf-8")).hexdigest()[:12]


def path_of(r):
    return os.path.join(REC_DIR, r["id"].replace("/", "-") + ".json")


def ask(key, batch):
    items = [{"id": r["id"], "location": r.get("loc") or [r.get("fir")], "qcode": r.get("q"),
              "lower": r.get("lower"), "upper": r.get("upper"), "schedule": r.get("sched"),
              "radius_nm": r.get("radius"), "text": r.get("text")} for r in batch]
    body = {"model": MODEL, "max_tokens": 4000, "temperature": 0,
            "messages": [{"role": "user", "content": PROMPT + json.dumps(items, ensure_ascii=False, indent=1)}]}
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529) and attempt < 3:
                time.sleep(15 * (attempt + 1))
                continue
            raise RuntimeError(f"API error {e.code}: {e.read()[:300]!r}")
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON in the reply")
    return json.loads(text[start:end + 1])


def clean(s):
    s = " ".join(str(s).split()).strip()
    if not s or len(s) > MAX_LEN:
        return None
    return s if s.endswith((".", "!", "?")) else s + "."


def output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def main():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("summaries: no API key, skipped")
        output(summaries_written="0")
        return 0
    todo = []
    for f in sorted(glob.glob(os.path.join(REC_DIR, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            r = json.load(fh)
        if r.get("text") and (not r.get("summary") or r.get("summary_of") != fingerprint(r)):
            todo.append(r)
    todo.sort(key=lambda r: (r.get("removed") is not None, r.get("first_seen") or ""), reverse=False)
    todo = todo[:MAX_PER_RUN]   # current NOTAMs first, then older ones over the next runs
    written = failed = 0
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        try:
            got = ask(key, batch)
        except Exception as e:
            print(f"::warning::summaries batch failed: {e}")
            failed += len(batch)
            continue
        for r in batch:
            s = clean(got.get(r["id"], ""))
            if not s:
                failed += 1
                continue
            r["summary"], r["summary_of"] = s, fingerprint(r)
            with open(path_of(r), "w", encoding="utf-8") as fh:
                json.dump(r, fh, ensure_ascii=False, indent=1, sort_keys=True)
                fh.write("\n")
            written += 1
    print(f"summaries: {written} written, {failed} failed, {len(todo)} queued this run")
    output(summaries_written=str(written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
