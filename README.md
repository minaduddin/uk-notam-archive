# UK NOTAM archive

An automatic, timestamped archive of the UK NATS Pre-flight Information Bulletin (PIB).

Every 30 minutes a GitHub Actions workflow downloads the public bulletin and keeps one small record
per NOTAM in [`data/notams/`](data/notams/): its details, when it first appeared and when it left the
bulletin. A new commit is made only when a NOTAM is new, changes or is withdrawn. One raw copy of the
bulletin per day is kept as a download in [Releases](https://github.com/minaduddin/uk-notam-archive/releases).

> **Unofficial copy.** This archive is not affiliated with or endorsed by NATS. It may be incomplete,
> delayed or out of date. Do not use it for flight planning or operational decisions: always check
> NOTAMs with the official source.

## Search

**[Search UK NOTAMs →](https://minaduddin.github.io/uk-notam-archive/)**

Search by NOTAM ID, location, Q-code or any words in the text, pick a day to see what was in force
then, or find NOTAMs within a distance of a point. Every NOTAM, current or past, also has its own page,
and there are pages per location and for current [cranes and obstacles](https://minaduddin.github.io/uk-notam-archive/obstacles.html).

## Source

[NATS Pre-flight Information Bulletin](https://pibs.nats.co.uk/operational/pibs/PIB.xml) (public).

## Contents

| Path | What it is |
|---|---|
| `data/notams/` | One record per NOTAM ever seen: its details, when it first appeared and when it left the bulletin |
| [Releases](https://github.com/minaduddin/uk-notam-archive/releases) | `snapshots-YYYY-MM`: one gzipped raw bulletin per day, `PIB-YYYY-MM-DD.xml.gz` |
| `fetch_pib.py` | Downloads and checks the bulletin |
| `build_site.py` | Updates the NOTAM records and builds the website (search, NOTAM and location pages, sitemap) |
| `.github/workflows/archive.yml` | Runs both every 30 minutes, commits record changes, saves the daily snapshot and publishes the website |

A download is saved only if it is a valid bulletin (well-formed XML with at least 50 NOTAMs), so an
error or maintenance page never replaces a good copy.

## Reading past NOTAMs

All records in one file (the website's search data):

```
https://minaduddin.github.io/uk-notam-archive/notams.json
```

One NOTAM (ID with `/` replaced by `-`):

```
https://raw.githubusercontent.com/minaduddin/uk-notam-archive/main/data/notams/A1234-26.json
```

The raw bulletin as it was on a day: download `PIB-YYYY-MM-DD.xml.gz` from the
`snapshots-YYYY-MM` release. Bulletins saved before 8 November 2026 are in the
[history of `data/PIB.xml`](https://github.com/minaduddin/uk-notam-archive/commits/main/data/PIB.xml).

The whole archive: **Code → Download ZIP** on the repository page.

## Run it yourself

Python 3.8 or newer, no packages needed:

```
python fetch_pib.py
python build_site.py      # website in _site/
```

## Notes

- Scheduled runs on GitHub can start a few minutes late. If the source cannot be reached, the run
  shows a warning and the next run tries again.
- The bulletin data belongs to NATS and is subject to its terms of use.
