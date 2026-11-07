#!/usr/bin/env python3
"""Download the UK NATS Pre-flight Information Bulletin (PIB.xml) and keep a copy in data/PIB.xml.

The file is only rewritten when the NOTAMs in it changed, so the git history holds one commit per real change.
Standard library only. Exit code 0 = finished (changed or not), 1 = download kept failing or the file was not a valid PIB.
Writes "changed=true|false" and "notams=N" to $GITHUB_OUTPUT when run inside GitHub Actions.
"""
import hashlib
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

PIB_URL = "https://pibs.nats.co.uk/operational/pibs/PIB.xml"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "PIB.xml")
MIN_NOTAMS = 50          # a real UK PIB holds thousands; fewer means an error or maintenance page
TRIES, WAIT = 3, 20      # attempts and seconds between them
UA = "notam-archive/1.0 (+https://github.com)"


def download():
    last = None
    for i in range(TRIES):
        try:
            req = urllib.request.Request(PIB_URL, headers={"User-Agent": UA, "Accept": "application/xml"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except Exception as e:  # network error, timeout, HTTP error
            last = e
            print(f"attempt {i + 1}/{TRIES} failed: {e}", file=sys.stderr)
            if i < TRIES - 1:
                time.sleep(WAIT)
    raise RuntimeError(f"download failed: {last}")


def notams(raw):
    """Parse and check the PIB. Returns the NOTAM elements, or raises ValueError."""
    root = ET.fromstring(raw)
    if not root.tag.endswith("Pib"):
        raise ValueError(f"unexpected root element <{root.tag}>")
    found = [n for n in root.iter() if n.tag.endswith("Notam")]
    if len(found) < MIN_NOTAMS:
        raise ValueError(f"only {len(found)} NOTAMs in the file")
    return found


def fingerprint(nodes):
    """Hash of the NOTAMs only (the header carries a fresh timestamp on every download)."""
    parts = sorted(ET.tostring(n, encoding="unicode") for n in nodes)
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def main():
    try:
        raw = download()
        new = notams(raw)
    except Exception as e:
        print(f"::warning::PIB not saved: {e}")
        output(changed="false", notams="0")
        return 1
    old_fp = None
    if os.path.exists(OUT):
        try:
            with open(OUT, "rb") as f:
                old_fp = fingerprint(notams(f.read()))
        except Exception:
            old_fp = None  # unreadable old copy: replace it
    changed = fingerprint(new) != old_fp
    if changed:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        tmp = OUT + ".tmp"
        with open(tmp, "wb") as f:
            f.write(raw)
        os.replace(tmp, OUT)
    print(f"{len(new)} NOTAMs · {'changed, saved' if changed else 'no change'}")
    output(changed=str(changed).lower(), notams=str(len(new)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
