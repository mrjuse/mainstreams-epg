# Mainstreams EPG

Automated daily XMLTV guide fetcher for the Mainstreams IPTV app.

A GitHub Actions workflow (`.github/workflows/update_epg_workflow.yml`) runs
`fetch_epg.py` every day at midnight UTC (and on manual dispatch), pulling 78
country/region guide sources — North America, the Caribbean, South America,
Europe (including Spain), Africa, and Asia — and publishing them as gzipped
XMLTV files via GitHub Pages.

Browse all available guides: https://mrjuse.github.io/mainstreams-epg/

## Using this in the Mainstreams app

On the app's Settings screen, paste one of these into the "XMLTV EPG URL"
field when adding a playlist profile.

**A playlist that mixes channels from several countries — start here:**

```
https://mrjuse.github.io/mainstreams-epg/all_48h.xml.gz
```

Every channel from every region, but only programmes airing in a rolling
−6h/+48h window. That trims the programme count by roughly 85% versus the
full merge while keeping the identical channel list, which is what makes it
realistic to parse on a set-top box or TV stick.

**A playlist covering one country:** use that country's own file, e.g.
`https://mrjuse.github.io/mainstreams-epg/north_america/US2.xml.gz`. This is
the smallest and fastest option — pick it when you can.

**The complete merged guide** is at `all.xml.gz`. It carries the full
multi-day schedule for every source and is very large (~1.1GB uncompressed).
Only reach for it if you actually need that schedule depth *and* the device
has the memory to stream it — on a typical Android heap, holding a programme
object per entry will run out of memory. `all_48h.xml.gz` exists precisely to
avoid that.

The app re-fetches its configured EPG URL every 6 hours, and the guide data
itself is regenerated daily by the GitHub Action, so no manual refresh step is
needed once a URL is set.

### A note on the window

The workflow regenerates once a day, so the trimmed file ages between runs: at
worst — just before the next run — it still holds a full 24 hours of forward
listings. Adjust `WINDOW_HOURS` / `LOOKBACK_HOURS` at the top of
`fetch_epg.py` if you want more or less headroom, trading file size for
schedule depth.

## Repo layout

- `fetch_epg.py` — fetches all sources in parallel, writes per-country files
  under `public/<region>/<code>.xml.gz`, then streams them into the two
  combined guides (`public/all.xml.gz` and `public/all_48h.xml.gz`) and
  generates `public/index.html` (the page linked above). The merge is
  element-streaming, so peak memory stays flat regardless of guide size.
- `.github/workflows/update_epg_workflow.yml` — runs `fetch_epg.py` on a
  schedule and deploys the `public/` output to GitHub Pages.
