# Mainstreams EPG

Automated XMLTV guide fetcher for the Mainstreams IPTV app.

A GitHub Actions workflow (`.github/workflows/update_epg_workflow.yml`) runs
`fetch_epg.py` every 6 hours (and on manual dispatch), pulling 78
country/region guide sources — North America, the Caribbean, South America,
Europe (including Spain), Africa, and Asia — and publishing them as gzipped
XMLTV files via GitHub Pages.

Browse all available guides: https://mrjuse.github.io/mainstreams-epg/

## Using this in the Mainstreams app

On the app's Settings screen, paste one of these into the "XMLTV EPG URL"
field when adding a playlist profile.

**A playlist that mixes channels from several countries — start here:**

```
https://mrjuse.github.io/mainstreams-epg/all_recent.xml.gz
```

Every channel from every region, but only programmes airing in a rolling
−3h/+18h window. The filename has no window in it on purpose, so the URL you
configure stays valid if the window is ever retuned.

**A playlist covering one country:** use that country's own file, e.g.
`https://mrjuse.github.io/mainstreams-epg/north_america/US2.xml.gz`. This is
the smallest and fastest option — pick it when you can.

**The complete merged guide** is at `all.xml.gz` — every source's full
multi-day schedule, ~123MB gzipped and ~1.1GB uncompressed. Only reach for it
if you genuinely need that schedule depth *and* the device has the memory for
it. On a typical Android heap, allocating an object per programme will run out
of memory long before the file finishes parsing.

## Sizing, and why the window is what it is

The upstream sources carry roughly **four days** of listings — not the week or
two you might assume — so trimming by time helps less than it first appears. A
48-hour window still retained about 57% of the 1.75M programmes.

The window is also evaluated **when the workflow runs**, not when a device
downloads the file. Worst-case forward coverage is therefore
`WINDOW_HOURS` minus the rebuild interval. That coupling is the reason the
workflow rebuilds every 6 hours instead of daily: it is what makes a small
window safe.

| Rebuild | Window     | Programmes | Size    | Worst-case forward coverage |
|---------|------------|-----------:|--------:|----------------------------:|
| daily   | −6h / +48h |    992,000 |  74.7MB |                         24h |
| 6-hly   | −3h / +18h |   ~386,000 |  ~29MB  |                         12h |
| daily   | −6h / +24h |    551,000 |  41.5MB |    0h — stale before rebuild |

The third row is the trap: with a daily rebuild, a 24-hour window leaves the
file with no forward listings at all just before the next run. `fetch_epg.py`
prints a warning if `WINDOW_HOURS` is not greater than
`REBUILD_INTERVAL_HOURS`; keep that constant in sync with the cron if you
change either.

### The bigger lever: channels

This guide carries **19,134 channels**, while a typical playlist uses a few
hundred. Discarding programmes whose `channel` is not in the loaded playlist —
during parsing, before allocating — cuts the working set by one to two orders
of magnitude. That is far more effective than any window change, and it is the
change most worth making on the app side.

## Repo layout

- `fetch_epg.py` — fetches all sources in parallel, writes per-country files
  under `public/<region>/<code>.xml.gz`, then streams them into the two
  combined guides (`public/all.xml.gz` and `public/all_recent.xml.gz`) and
  generates `public/index.html` (the page linked above). The merge is
  element-streaming, so peak memory stays flat regardless of guide size.
- `.github/workflows/update_epg_workflow.yml` — runs `fetch_epg.py` on the
  6-hourly schedule and deploys the `public/` output to GitHub Pages.
