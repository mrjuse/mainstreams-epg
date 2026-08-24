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
field when adding a playlist profile:

- **One country/region only** — use that file's direct URL, e.g.
  `https://mrjuse.github.io/mainstreams-epg/north_america/US2.xml.gz`.
  Smallest, fastest download; pick this if your playlist's channels are all
  from a single country.
- **A playlist that mixes channels from multiple countries** — use the
  combined guide, which merges every region above into one file:

  `https://mrjuse.github.io/mainstreams-epg/all.xml.gz`

  This is a much larger download (roughly the same order of magnitude as
  all 78 individual files added together) since it contains every source's
  channels and programmes. It's the right choice for a single global
  playlist, but worth keeping an eye on device performance/refresh time on
  lower-end Android TV hardware — if it's too heavy, splitting your
  playlist into a few region-scoped profiles (each with its own smaller,
  region-specific EPG URL) is the lighter-weight alternative.

The app re-fetches its configured EPG URL every 6 hours, and the guide data
itself is regenerated daily by the GitHub Action, so no manual refresh step
is needed once a URL is set.

## Repo layout

- `fetch_epg.py` — fetches all sources, writes per-country files under
  `public/<region>/<code>.xml.gz`, builds the combined `public/all.xml.gz`,
  and generates `public/index.html` (the page linked above).
- `.github/workflows/update_epg_workflow.yml` — runs `fetch_epg.py` on a
  schedule and deploys the `public/` output to GitHub Pages.
