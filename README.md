# UK NOTAM archive

An automatic, timestamped archive of the UK NATS Pre-flight Information Bulletin (PIB).

Every 30 minutes a GitHub Actions workflow downloads the public bulletin and saves it as
[`data/PIB.xml`](data/PIB.xml). A new commit is made only when the NOTAMs change, so the commit
history is the archive: the bulletin as it was at any moment can be read back from the commit made
at that time.

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
| `data/PIB.xml` | The latest saved bulletin, exactly as published (XML) |
| `data/notams/` | One record per NOTAM ever seen: its details, when it first appeared and when it left the bulletin |
| `fetch_pib.py` | Downloads and checks the bulletin; saves it only when the NOTAMs changed |
| `build_site.py` | Updates the NOTAM records and builds the website (search, NOTAM and location pages, sitemap) |
| `.github/workflows/archive.yml` | Runs both every 30 minutes, commits changes and publishes the website |

A download is saved only if it is a valid bulletin (well-formed XML with at least 50 NOTAMs), so an
error or maintenance page never replaces a good copy.

## Reading past bulletins

List the commits that changed the bulletin during a period (times in UTC):

```
https://api.github.com/repos/minaduddin/uk-notam-archive/commits?path=data/PIB.xml&since=2026-11-09T00:00:00Z&until=2026-11-10T00:00:00Z
```

Download the bulletin as it was at a commit:

```
https://raw.githubusercontent.com/minaduddin/uk-notam-archive/<commit-sha>/data/PIB.xml
```

Or browse the [history of `data/PIB.xml`](https://github.com/minaduddin/uk-notam-archive/commits/main/data/PIB.xml).

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
