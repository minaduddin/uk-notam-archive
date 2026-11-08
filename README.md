# UK NOTAM archive

A free, searchable archive of UK NOTAMs, updated every 30 minutes from the public NATS Pre-flight
Information Bulletin (PIB). Current and past NOTAMs, including cranes and other obstacles.

> **Unofficial copy.** This archive is not affiliated with or endorsed by NATS. It may be incomplete,
> delayed or out of date. Do not use it for flight planning or operational decisions: always check
> NOTAMs with the official source.

## Search

**[Search UK NOTAMs →](https://minaduddin.github.io/uk-notam-archive/)**

- Search by NOTAM ID, location, Q-code or any words in the text
- Pick a day to see what was in force then
- Find NOTAMs within a distance of a point
- Every NOTAM, current or past, has its own page with a plain-English summary
  (generated automatically and may contain mistakes: always read the full NOTAM text)
- Pages per [location](https://minaduddin.github.io/uk-notam-archive/locations.html) and for current
  [cranes and obstacles](https://minaduddin.github.io/uk-notam-archive/obstacles.html)

## Download the data

| What | Where |
|---|---|
| All NOTAMs in one file (JSON) | [notams.json](https://minaduddin.github.io/uk-notam-archive/notams.json) |
| One NOTAM | `data/notams/<ID>.json`, with `/` replaced by `-`, e.g. `A1234-26.json` |
| Raw bulletin for a day | [Releases](https://github.com/minaduddin/uk-notam-archive/releases): `PIB-YYYY-MM-DD.xml.gz` |
| Everything | **Code → Download ZIP** |

## Source

[NATS Pre-flight Information Bulletin](https://pibs.nats.co.uk/operational/pibs/PIB.xml) (public).
The bulletin data belongs to NATS and is subject to its terms of use.
