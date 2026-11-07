#!/usr/bin/env python3
"""Keep a record of every NOTAM ever seen and build the public website from it.

1. records: reads data/PIB.xml and keeps one small JSON file per NOTAM in data/notams/<ID>.json
   (first time seen, and when it left the bulletin). A file is written only when a NOTAM is new,
   changes, or leaves the bulletin, so the history stays small.
2. site: writes a static website to _site/ that search engines can read:
     index.html            search page + links to every location and the newest NOTAMs
     notam/<ID>.html       one page per NOTAM (current and past)
     location/<ICAO>.html  current and past NOTAMs for each location
     obstacles.html        current cranes and other obstacles
     notams.json           data for the search box
     sitemap.xml, robots.txt, 404.html
Usage: python build_site.py            (update records, then build)
       python build_site.py --build    (build only)
Standard library only. Writes "records_changed=true|false" to $GITHUB_OUTPUT inside GitHub Actions.
"""
import datetime as dt
import glob
import html
import json
import os
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
PIB = os.path.join(ROOT, "data", "PIB.xml")
REC_DIR = os.path.join(ROOT, "data", "notams")
OUT = os.path.join(ROOT, "_site")
_repo = os.environ.get("GITHUB_REPOSITORY", "minaduddin/uk-notam-archive")
OWNER, REPO = _repo.split("/", 1)
BASE = f"https://{OWNER.lower()}.github.io/{REPO}"
SITE_NAME = "UK NOTAM Archive"
NATS_URL = "https://pibs.nats.co.uk/operational/pibs/PIB.xml"
NOW = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
FIELDS = ("type", "loc", "fir", "q", "from", "to", "est", "sched", "lower", "upper", "coord", "radius", "text")


# ───────────────────────── helpers ─────────────────────────
def iso(t):
    return t.strftime("%Y-%m-%dT%H:%MZ") if t else None


def parse_iso(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc) if s else None


def notam_time(s):
    """'YYMMDDhhmm' (UTC) -> ISO; 'PERM' -> 'PERM'."""
    s = (s or "").strip()
    if s.upper().startswith("PERM"):
        return "PERM"
    if len(s) >= 10 and s[:10].isdigit():
        return iso(dt.datetime(2000 + int(s[:2]), int(s[2:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]), tzinfo=dt.timezone.utc))
    return None


def coord(s):
    s = (s or "").strip().upper()
    if len(s) == 11 and s[4] in "NS" and s[10] in "EW":
        try:
            lat = (int(s[0:2]) + int(s[2:4]) / 60) * (-1 if s[4] == "S" else 1)
            lon = (int(s[5:8]) + int(s[8:10]) / 60) * (-1 if s[10] == "W" else 1)
            return [round(lat, 4), round(lon, 4)]
        except ValueError:
            return None
    return None


def slug(nid):
    return nid.replace("/", "-")


def e(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def fmt(s):
    if s == "PERM":
        return "PERM"
    return s.replace("T", " ") if s else "?"


def short(text, n):
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


# ───────────────────────── 1. records ─────────────────────────
def read_pib():
    root = ET.parse(PIB).getroot()
    out = {}
    for n in root.iter():
        if not n.tag.endswith("Notam"):
            continue
        def v(tag):
            for c in n.iter():
                if c.tag.endswith(tag):
                    return (c.text or "").strip()
            return ""
        nid = f"{v('Series')}{v('Number')}/{v('Year')}"
        if nid in out or not v("Number"):
            continue   # the bulletin lists some NOTAMs twice (aerodrome and FIR section)
        locs = [(c.text or "").strip() for c in n if c.tag.endswith("ItemA") and (c.text or "").strip()]
        end = v("EndValidity")
        out[nid] = {"id": nid, "type": v("Type"), "loc": locs, "fir": v("FIR"), "q": v("Code23") + v("Code45"),
                    "from": notam_time(v("StartValidity")), "to": notam_time(end), "est": "EST" in end.upper(),
                    "sched": v("ItemD"), "lower": v("ItemF"), "upper": v("ItemG"), "coord": coord(v("Coordinates")),
                    "radius": int(v("Radius")) if v("Radius").isdigit() else 0, "text": v("ItemE")}
    return out


def load_records():
    recs = {}
    for f in glob.glob(os.path.join(REC_DIR, "*.json")):
        with open(f, encoding="utf-8") as fh:
            r = json.load(fh)
        recs[r["id"]] = r
    return recs


def save(r):
    os.makedirs(REC_DIR, exist_ok=True)
    with open(os.path.join(REC_DIR, slug(r["id"]) + ".json"), "w", encoding="utf-8") as fh:
        json.dump(r, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")


def update_records():
    if not os.path.exists(PIB):
        return False
    current, recs, changed = read_pib(), load_records(), 0
    for nid, n in current.items():
        r = recs.get(nid)
        if r is None:
            r = dict(n, first_seen=iso(NOW), removed=None)
        elif any(r.get(k) != n[k] for k in FIELDS) or r.get("removed"):
            r.update(n)
            r["removed"] = None
        else:
            continue
        recs[nid] = r
        save(r)
        changed += 1
    for nid, r in recs.items():
        if nid not in current and not r.get("removed"):
            r["removed"] = iso(NOW)
            save(r)
            changed += 1
    print(f"records: {len(current)} in the bulletin, {len(recs)} in total, {changed} written")
    return changed > 0


# ───────────────────────── 2. site ─────────────────────────
CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#14181f;--muted:#5b6573;--line:#e2e6eb;--accent:#0a66e8;--soft:#e8f1fe;--warn:#8a5300;--warn-bg:#fff4e0;--mark:#ffe58a;--ok:#0f7b4b;--ok-bg:#e4f5ec;--fut:#6c4fd1;--fut-bg:#efeafd;--old:#6b7280;--old-bg:#eef0f3}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0d1117;--card:#161b22;--ink:#e6edf3;--muted:#9aa6b2;--line:#2a313c;--accent:#4c9bff;--soft:#14243b;--warn:#f0b45a;--warn-bg:#2b2112;--mark:#6b5a12;--ok:#4cd38f;--ok-bg:#10291c;--fut:#a993ff;--fut-bg:#221b3d;--old:#9aa3ad;--old-bg:#1f252d}}
*{box-sizing:border-box}[hidden]{display:none!important}
html,body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent)}.wrap{max-width:980px;margin:0 auto;padding:24px 16px 48px}
header.top{display:flex;gap:16px;align-items:baseline;flex-wrap:wrap;margin-bottom:6px}header.top a.brand{font-weight:800;text-decoration:none;color:var(--ink);font-size:18px}
nav.crumbs{font-size:13px;color:var(--muted);margin:0 0 10px}nav.crumbs a{color:var(--muted)}
h1{font-size:26px;margin:4px 0 6px;letter-spacing:-.01em;line-height:1.25}h2{font-size:19px;margin:28px 0 10px}
.sub{color:var(--muted);margin:0 0 16px}.note{background:var(--warn-bg);color:var(--warn);border-radius:10px;padding:10px 14px;font-size:13px;margin:0 0 18px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:16px}
.row{display:flex;gap:12px;flex-wrap:wrap;align-items:end}.row+.row{margin-top:12px}
label{display:flex;flex-direction:column;gap:4px;font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
input,select{font:inherit;color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:9px;padding:9px 11px;min-width:0}
input:focus,select:focus{outline:2px solid var(--accent);outline-offset:1px;border-color:transparent}
.grow{flex:1 1 320px}.grow input{width:100%}
button{font:inherit;font-weight:600;border:0;border-radius:9px;padding:10px 16px;background:var(--accent);color:#fff;cursor:pointer}button.ghost{background:transparent;color:var(--accent);border:1px solid var(--line)}
.status{color:var(--muted);font-size:13px;margin:0 0 10px;min-height:20px}.status b{color:var(--ink)}
.list{display:flex;flex-direction:column;gap:10px}.n{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.n-head{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:baseline;margin-bottom:6px}.id{font-weight:700;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.n-head a.id{color:var(--ink)}.loc{font-weight:600}.meta{color:var(--muted);font-size:13px}
.tag{font-size:11px;font-weight:700;padding:2px 8px;border-radius:99px;text-transform:uppercase;letter-spacing:.04em;white-space:nowrap}
.t-current{color:var(--ok);background:var(--ok-bg)}.t-later{color:var(--fut);background:var(--fut-bg)}.t-ended{color:var(--old);background:var(--old-bg)}
.txt{white-space:pre-wrap;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px;line-height:1.55;overflow-wrap:anywhere;margin:0}
mark{background:var(--mark);color:inherit;border-radius:3px;padding:0 1px}.more{display:block;margin:14px auto 0}
.help{color:var(--muted);font-size:13px;margin-top:10px}.help code{background:var(--soft);color:var(--ink);padding:1px 5px;border-radius:5px}
table.kv{border-collapse:collapse;width:100%;font-size:14px}table.kv th{text-align:left;color:var(--muted);font-weight:600;padding:7px 12px 7px 0;vertical-align:top;width:190px}table.kv td{padding:7px 0;border-top:1px solid var(--line)}table.kv tr:first-child td{border-top:0}
ul.links{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:6px}ul.links li{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 12px}
.grid{display:flex;flex-wrap:wrap;gap:8px}.grid a{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:5px 10px;text-decoration:none;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px}
.grid a span{color:var(--muted);margin-left:6px}footer{color:var(--muted);font-size:12px;margin-top:32px;text-align:center}
@media (max-width:600px){.wrap{padding:16px 16px 40px}h1{font-size:22px}button{width:100%}table.kv th{width:120px}}
"""

DISCLAIMER = ('<div class="note"><b>Unofficial.</b> Not affiliated with or endorsed by NATS. This archive may be incomplete or delayed. '
              'Do not use it for flight planning or operational decisions: always check NOTAMs with the official source.</div>')


def page(title, desc, path, body, depth, jsonld=None, extra_head=""):
    up = f"/{REPO}/" if depth < 0 else "../" * depth   # -1: absolute links (404 page is served at any address)
    canon = f"{BASE}/{path}" if path else f"{BASE}/"
    ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canon)}">
<meta property="og:type" content="website"><meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{e(canon)}">
<meta name="twitter:card" content="summary">
<link rel="stylesheet" href="{up}style.css">
{ld}{extra_head}
</head>
<body>
<div class="wrap">
<header class="top"><a class="brand" href="{up}">{SITE_NAME}</a><a href="{up}obstacles.html">Cranes &amp; obstacles</a><a href="{up}locations.html">Locations</a></header>
{body}
<footer>Data: <a href="{NATS_URL}">NATS Pre-flight Information Bulletin</a> (© NATS). Unofficial archive, updated every 30 minutes · <a href="https://github.com/{OWNER}/{REPO}">GitHub</a></footer>
</div>
</body>
</html>
"""


def status(r):
    if r.get("removed"):
        return "ended", "no longer in force"
    if r.get("from") and r["from"] != "PERM" and parse_iso(r["from"]) > NOW:
        return "later", "starts later"
    return "current", "current"


def locs(r):
    return r.get("loc") or ([r["fir"]] if r.get("fir") else [])


def card(r, depth):
    st, label = status(r)
    up = "../" * depth
    alt = f" · {e(r.get('lower') or 'SFC')} – {e(r.get('upper') or '?')}" if r.get("lower") or r.get("upper") else ""
    loc = " ".join(f'<a href="{up}location/{e(x)}.html">{e(x)}</a>' for x in locs(r))
    return (f'<article class="n"><div class="n-head"><a class="id" href="{up}notam/{slug(r["id"])}.html">{e(r["id"])}</a>'
            f'<span class="loc">{loc}</span><span class="tag t-{st}">{label}</span>'
            f'<span class="meta">{fmt(r.get("from"))} → {fmt(r.get("to"))}{" (est)" if r.get("est") else ""}{alt}</span></div>'
            f'<p class="txt">{e(short(r.get("text"), 400))}</p></article>')


def title_of(r):
    where = " ".join(locs(r))
    return f'NOTAM {r["id"]} {where}: {short(r.get("text"), 70)}'


def notam_page(r):
    st, label = status(r)
    rows = [("Location", " ".join(f'<a href="../location/{e(x)}.html">{e(x)}</a>' for x in locs(r)) or "—"),
            ("Status", f'<span class="tag t-{st}">{label}</span>'),
            ("Valid from (UTC)", fmt(r.get("from"))),
            ("Valid to (UTC)", fmt(r.get("to")) + (" (estimated)" if r.get("est") else ""))]
    if r.get("sched"):
        rows.append(("Schedule", e(r["sched"])))
    if r.get("lower") or r.get("upper"):
        rows.append(("Vertical limits", f'{e(r.get("lower") or "SFC")} – {e(r.get("upper") or "?")}'))
    if r.get("q"):
        rows.append(("Q-code", "Q" + e(r["q"])))
    if r.get("fir"):
        rows.append(("FIR", e(r["fir"])))
    if r.get("coord"):
        lat, lon = r["coord"]
        rows.append(("Position", f'{lat:.4f}, {lon:.4f}' + (f' · radius {r["radius"]} NM' if r.get("radius") else "")
                     + f' · <a href="https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=11/{lat}/{lon}" rel="nofollow">map</a>'))
    rows.append(("First seen in archive", fmt(r.get("first_seen"))))
    if r.get("removed"):
        rows.append(("Left the bulletin", fmt(r["removed"])))
    table = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)
    title = title_of(r) + f" | {SITE_NAME}"
    desc = f'NOTAM {r["id"]} ({" ".join(locs(r))}), valid {fmt(r.get("from"))} to {fmt(r.get("to"))}: {short(r.get("text"), 130)}'
    crumbs = f'<nav class="crumbs"><a href="../">Home</a> › ' + (f'<a href="../location/{e(locs(r)[0])}.html">{e(locs(r)[0])}</a> › ' if locs(r) else "") + f'{e(r["id"])}</nav>'
    body = (f'{crumbs}<h1>NOTAM {e(r["id"])} · {e(" ".join(locs(r)))}</h1>'
            f'<p class="sub">{e(short(r.get("text"), 160))}</p>{DISCLAIMER}'
            f'<div class="panel"><pre class="txt">{e(r.get("text"))}</pre></div>'
            f'<div class="panel"><table class="kv">{table}</table></div>'
            f'<p class="meta">Always check the current NOTAM with the official source: <a href="{NATS_URL}">NATS Pre-flight Information Bulletin</a>.</p>')
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "name": title_of(r), "description": desc, "url": f"{BASE}/notam/{slug(r['id'])}.html",
         "datePublished": (r.get("first_seen") or "").replace("Z", ":00Z"), "dateModified": (r.get("removed") or r.get("first_seen") or "").replace("Z", ":00Z"),
         "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": BASE + "/"}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE + "/"}]
            + ([{"@type": "ListItem", "position": 2, "name": locs(r)[0], "item": f"{BASE}/location/{locs(r)[0]}.html"}] if locs(r) else [])
            + [{"@type": "ListItem", "position": 3 if locs(r) else 2, "name": r["id"]}]}]}
    return page(title, desc, f"notam/{slug(r['id'])}.html", body, 1, ld)


def sort_key(r):
    return (r.get("from") or "", r["id"])


def location_page(loc, items):
    cur = sorted([r for r in items if not r.get("removed")], key=sort_key, reverse=True)
    old = sorted([r for r in items if r.get("removed")], key=lambda r: r.get("removed") or "", reverse=True)
    title = f"{loc} NOTAMs: current and past | {SITE_NAME}"
    desc = f"{len(cur)} current and {len(old)} past NOTAMs for {loc}, from the archived UK NATS Pre-flight Information Bulletin. Search cranes, obstacles, airspace and aerodrome NOTAMs."
    body = (f'<nav class="crumbs"><a href="../">Home</a> › <a href="../locations.html">Locations</a> › {e(loc)}</nav>'
            f'<h1>{e(loc)} NOTAMs</h1><p class="sub">Current and past NOTAMs for {e(loc)}.</p>{DISCLAIMER}'
            f'<h2>Current ({len(cur)})</h2><div class="list">{"".join(card(r, 1) for r in cur) or "<p class=meta>None in the latest bulletin.</p>"}</div>'
            f'<h2>Past ({len(old)})</h2><div class="list">{"".join(card(r, 1) for r in old) or "<p class=meta>None archived yet.</p>"}</div>')
    return page(title, desc, f"location/{loc}.html", body, 1)


SEARCH_JS = r"""
(() => {
  'use strict';
  const PAGE = 100, $ = (id) => document.getElementById(id);
  const els = { f: $('f'), q: $('q'), day: $('day'), near: $('near'), nm: $('nm'), show: $('show'), status: $('status'), list: $('list'), more: $('more'), clear: $('clear') };
  let DATA = null, results = [], shown = 0, terms = [];
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const todayUTC = () => new Date().toISOString().slice(0, 10);
  const ms = (s) => s === 'PERM' ? Infinity : s ? Date.parse(s.replace('Z', ':00Z')) : null;
  const fmt = (s) => s === 'PERM' ? 'PERM' : s ? s.replace('T', ' ') : '?';
  const icaoCoord = (s) => { const m = String(s || '').toUpperCase().match(/^(\d{2})(\d{2})([NS])(\d{3})(\d{2})([EW])$/); if (!m) return null;
    return [(+m[1] + m[2] / 60) * (m[3] === 'S' ? -1 : 1), (+m[4] + m[5] / 60) * (m[6] === 'W' ? -1 : 1)]; };
  const parseNear = (s) => { s = s.trim(); if (!s) return null; const c = icaoCoord(s.replace(/\s/g, '')); if (c) return c;
    const m = s.match(/^(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)$/); return m ? [+m[1], +m[2]] : undefined; };
  const nmBetween = ([a, b], [c, d]) => { const R = 3440.065, r = Math.PI / 180, dl = (c - a) * r, dg = (d - b) * r;
    const h = Math.sin(dl / 2) ** 2 + Math.cos(a * r) * Math.cos(c * r) * Math.sin(dg / 2) ** 2; return 2 * R * Math.asin(Math.sqrt(h)); };
  const tokens = (q) => { const out = []; q.replace(/"([^"]+)"|(\S+)/g, (_, a, b) => { out.push((a || b).toUpperCase()); }); return out; };
  async function data() {
    if (DATA) return DATA;
    const r = await fetch('notams.json', { cache: 'no-cache' }); if (!r.ok) throw new Error('could not load the NOTAM list (HTTP ' + r.status + ')');
    const j = await r.json();
    DATA = { updated: j.updated, list: j.notams.map(([id, loc, q, from, to, est, removed, seen, lower, upper, sched, lat, lon, radius, text]) => {
      const n = { id, loc, q, from, to, est, removed, seen, lower, upper, sched, coord: lat == null ? null : [lat, lon], radius, text,
        a: ms(from), b: Math.min(ms(to) ?? Infinity, removed ? ms(removed) : Infinity) };
      n.hay = [id, loc, q ? 'Q' + q : '', sched, text].join(' ').toUpperCase(); return n; }) };
    return DATA;
  }
  async function run(ev) {
    if (ev) ev.preventDefault();
    const day = els.day.value || todayUTC(), near = parseNear(els.near.value), nm = Math.max(0, +els.nm.value || 0);
    terms = tokens(els.q.value.trim());
    if (near === undefined) { els.status.textContent = 'Near: enter "lat, lon" (e.g. 51.4700, -0.4543) or 5128N00027W.'; return; }
    const p = new URLSearchParams(); if (els.q.value.trim()) p.set('q', els.q.value.trim()); if (els.day.value) p.set('day', els.day.value);
    if (els.near.value.trim()) { p.set('near', els.near.value.trim()); p.set('nm', nm); } if (els.show.value !== 'day') p.set('show', els.show.value);
    history.replaceState(null, '', p.toString() ? '?' + p : location.pathname);
    els.status.textContent = 'Loading…'; els.list.innerHTML = ''; els.more.hidden = true;
    let D; try { D = await data(); } catch (err) { els.status.textContent = 'Sorry: ' + err.message + '.'; return; }
    const t0 = Date.parse(day + 'T00:00:00Z'), t1 = t0 + 864e5 - 1, now = Date.now();
    results = D.list.filter((n) => {
      if (els.show.value === 'day' && (n.a > t1 || n.b < t0)) return false;
      if (els.show.value === 'current' && n.removed) return false;
      if (terms.length && !terms.every((t) => n.hay.includes(t))) return false;
      if (near) { if (!n.coord) return false; n.dist = nmBetween(near, n.coord); if (n.dist > nm + n.radius) return false; } else n.dist = null;
      return true;
    }).sort((a, b) => near ? a.dist - b.dist : (b.a - a.a) || a.id.localeCompare(b.id));
    shown = 0;
    els.status.innerHTML = '<b>' + results.length + '</b> NOTAM' + (results.length === 1 ? '' : 's') + (els.show.value === 'day' ? ' active on ' + esc(day) + ' UTC' : '') + ' · archive updated ' + esc(fmt(D.updated));
    render(now);
  }
  function hl(s) { const h = esc(s); if (!terms.length) return h;
    const re = new RegExp('(' + terms.map((t) => esc(t).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')', 'gi'); return h.replace(re, '<mark>$1</mark>'); }
  function render(now) {
    const frag = document.createDocumentFragment();
    results.slice(shown, shown + PAGE).forEach((n) => {
      const st = n.removed ? ['ended', 'no longer in force'] : n.a > now ? ['later', 'starts later'] : ['current', 'current'];
      const alt = n.lower || n.upper ? ' · ' + esc(n.lower || 'SFC') + ' – ' + esc(n.upper || '?') : '', slug = n.id.replace('/', '-');
      const d = document.createElement('article'); d.className = 'n';
      d.innerHTML = '<div class="n-head"><a class="id" href="notam/' + esc(slug) + '.html">' + hl(n.id) + '</a><span class="loc">' + hl(n.loc) + '</span>'
        + '<span class="tag t-' + st[0] + '">' + st[1] + '</span><span class="meta">' + fmt(n.from) + ' → ' + fmt(n.to) + (n.est ? ' (est)' : '') + alt
        + (n.q ? ' · Q' + esc(n.q) : '') + (n.dist != null ? ' · ' + n.dist.toFixed(1) + ' NM away' : '') + '</span></div>'
        + (n.sched ? '<div class="meta">Schedule: ' + hl(n.sched) + '</div>' : '') + '<p class="txt">' + hl(n.text) + '</p>';
      frag.appendChild(d);
    });
    els.list.appendChild(frag); shown = Math.min(results.length, shown + PAGE);
    els.more.hidden = shown >= results.length; els.more.textContent = 'Show more (' + (results.length - shown) + ' left)';
    els.more.onclick = () => render(now);
  }
  els.f.addEventListener('submit', run);
  els.clear.addEventListener('click', () => { els.q.value = ''; els.day.value = ''; els.near.value = ''; els.nm.value = 10; els.show.value = 'day'; run(); });
  const P = new URLSearchParams(location.search);
  els.q.value = P.get('q') || ''; els.day.value = P.get('day') || ''; els.near.value = P.get('near') || ''; els.nm.value = P.get('nm') || 10;
  els.show.value = ['all', 'current'].includes(P.get('show')) ? P.get('show') : 'day';
  run();
})();
"""


def home_page(recs, by_loc):
    newest = sorted(recs.values(), key=lambda r: (r.get("first_seen") or "", r["id"]), reverse=True)[:40]
    cur = sum(1 for r in recs.values() if not r.get("removed"))
    top = sorted(by_loc.items(), key=lambda kv: -sum(1 for r in kv[1] if not r.get("removed")))[:60]
    grid = "".join(f'<a href="location/{e(k)}.html">{e(k)}<span>{sum(1 for r in v if not r.get("removed"))}</span></a>' for k, v in top)
    body = f"""<h1>UK NOTAM search: current and past NOTAMs</h1>
<p class="sub">Search {cur:,} current UK NOTAMs and {len(recs) - cur:,} archived ones from the NATS Pre-flight Information Bulletin: cranes, obstacles, airspace, aerodromes and more. Updated every 30 minutes.</p>
{DISCLAIMER}
<form class="panel" id="f" autocomplete="off" role="search">
 <div class="row">
  <label class="grow">Search NOTAMs<input id="q" type="search" placeholder="e.g. crane · EGLL · wind turbine · drone" autofocus></label>
  <label>Day (UTC)<input id="day" type="date"></label>
 </div>
 <div class="row">
  <label>Near (lat, lon or 5128N00027W)<input id="near" placeholder="51.4700, -0.4543" size="22"></label>
  <label>Within (NM)<input id="nm" type="number" min="0" step="0.5" value="10" style="width:90px"></label>
  <label>Show<select id="show"><option value="day">Active on that day</option><option value="current">Current only</option><option value="all">Everything archived</option></select></label>
  <button type="submit">Search</button><button type="button" class="ghost" id="clear">Clear</button>
 </div>
 <div class="help">All words must match (NOTAM ID, location, Q-code or text). Phrases in quotes: <code>"wind turbine"</code>. Pick a past day to see what was in force then.</div>
</form>
<p class="status" id="status">Loading…</p>
<div class="list" id="list"></div>
<button class="ghost more" id="more" hidden>Show more</button>
<h2>Browse by location</h2>
<div class="grid">{grid}</div>
<p class="meta"><a href="locations.html">All locations →</a> · <a href="obstacles.html">Current cranes and obstacles →</a></p>
<h2>Newest NOTAMs</h2>
<ul class="links">{"".join(f'<li><a href="notam/{slug(r["id"])}.html">{e(title_of(r))}</a></li>' for r in newest)}</ul>
<script>{SEARCH_JS}</script>"""
    ld = {"@context": "https://schema.org", "@type": "WebSite", "name": SITE_NAME, "url": BASE + "/",
          "description": "Unofficial searchable archive of current and past UK NOTAMs from the NATS Pre-flight Information Bulletin.",
          "potentialAction": {"@type": "SearchAction", "target": BASE + "/?q={search_term_string}&show=all", "query-input": "required name=search_term_string"}}
    return page("UK NOTAM Search: current and past NOTAMs, cranes and obstacles", f"Search {cur:,} current and {len(recs) - cur:,} past UK NOTAMs from the NATS PIB: cranes, obstacles, airspace and aerodromes. Unofficial archive, updated every 30 minutes.", "", body, 0, ld)


def build():
    recs = load_records()
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    for d in ("notam", "location"):
        os.makedirs(os.path.join(OUT, d))
    def write(rel, text):
        with open(os.path.join(OUT, rel), "w", encoding="utf-8") as fh:
            fh.write(text)
    write("style.css", CSS.strip() + "\n")
    by_loc = {}
    for r in recs.values():
        for x in locs(r):
            by_loc.setdefault(x, []).append(r)
        write(f"notam/{slug(r['id'])}.html", notam_page(r))
    for loc, items in by_loc.items():
        write(f"location/{loc}.html", location_page(loc, items))
    write("locations.html", page(f"All NOTAM locations | {SITE_NAME}", "Every UK aerodrome and FIR with NOTAMs in the archive, with current and past NOTAMs for each.", "locations.html",
                                 '<nav class="crumbs"><a href="./">Home</a> › Locations</nav><h1>NOTAM locations</h1>' + DISCLAIMER + '<div class="grid">'
                                 + "".join(f'<a href="location/{e(k)}.html">{e(k)}<span>{len(v)}</span></a>' for k, v in sorted(by_loc.items())) + "</div>", 0))
    obst = sorted([r for r in recs.values() if not r.get("removed") and (r.get("q") or "").startswith("OB")], key=sort_key, reverse=True)
    write("obstacles.html", page(f"Current UK crane and obstacle NOTAMs ({len(obst)}) | {SITE_NAME}",
                                 f"{len(obst)} current UK NOTAMs for cranes, masts, wind turbines and other obstacles, with position and height, from the NATS Pre-flight Information Bulletin.",
                                 "obstacles.html", '<nav class="crumbs"><a href="./">Home</a> › Cranes &amp; obstacles</nav><h1>Current crane and obstacle NOTAMs</h1>'
                                 f'<p class="sub">{len(obst)} current NOTAMs for cranes, masts, wind turbines and other obstacles across the UK.</p>' + DISCLAIMER
                                 + '<div class="list">' + "".join(card(r, 0) for r in obst) + "</div>", 0))
    write("index.html", home_page(recs, by_loc))
    write("404.html", page(f"Page not found | {SITE_NAME}", "Page not found.", "404.html", '<h1>Page not found</h1><p><a href="/' + REPO + '/">Search UK NOTAMs</a></p>', -1, extra_head='<meta name="robots" content="noindex">'))
    rows = []
    for r in sorted(recs.values(), key=lambda r: r["id"]):
        c = r.get("coord") or [None, None]
        rows.append([r["id"], " ".join(locs(r)), r.get("q") or "", r.get("from"), r.get("to"), bool(r.get("est")), r.get("removed"), r.get("first_seen"),
                     r.get("lower") or "", r.get("upper") or "", r.get("sched") or "", c[0], c[1], r.get("radius") or 0, r.get("text") or ""])
    write("notams.json", json.dumps({"updated": iso(NOW), "notams": rows}, ensure_ascii=False, separators=(",", ":")))
    urls = [(f"{BASE}/", iso(NOW)), (f"{BASE}/obstacles.html", iso(NOW)), (f"{BASE}/locations.html", iso(NOW))]
    urls += [(f"{BASE}/location/{k}.html", iso(NOW)) for k in sorted(by_loc)]
    urls += [(f"{BASE}/notam/{slug(r['id'])}.html", r.get("removed") or r.get("first_seen")) for r in sorted(recs.values(), key=lambda r: r["id"])]
    maps = [urls[i:i + 40000] for i in range(0, len(urls), 40000)] or [[]]
    for i, chunk in enumerate(maps):
        write(f"sitemap-{i + 1}.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
              + "".join(f"<url><loc>{e(u)}</loc><lastmod>{(m or iso(NOW))[:10]}</lastmod></url>\n" for u, m in chunk) + "</urlset>\n")
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          + "".join(f"<sitemap><loc>{BASE}/sitemap-{i + 1}.xml</loc><lastmod>{iso(NOW)[:10]}</lastmod></sitemap>\n" for i in range(len(maps))) + "</sitemapindex>\n")
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")
    for f in glob.glob(os.path.join(ROOT, "google*.html")):   # Google Search Console verification file, if added to the repo
        shutil.copy(f, OUT)
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    print(f"site: {len(recs)} NOTAM pages, {len(by_loc)} location pages, {len(obst)} obstacles, {len(urls)} URLs in the sitemap")


def main():
    changed = False
    if "--build" not in sys.argv:
        changed = update_records()
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as fh:
                fh.write(f"records_changed={str(changed).lower()}\n")
    if "--records" not in sys.argv:
        build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
