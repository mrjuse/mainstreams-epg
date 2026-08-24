#!/usr/bin/env python3
"""
Fetches XMLTV EPG guide files (gzip-compressed) from epgshare01.online for a
curated set of countries/sources across North America, the Caribbean, South
America, Europe (including Spain), Africa, and Asia, and lays them out as
static files for GitHub Pages.

Three kinds of output:

* ``public/<region>/<code>.xml.gz`` - one small file per country/source.
  Best choice when a playlist only covers a single country.
* ``public/all.xml.gz``             - every source merged into one XMLTV file.
  For players that accept only one EPG URL, but very large.
* ``public/all_recent.xml.gz``     - the same merge trimmed to programmes
  airing in a rolling window (see WINDOW_HOURS / LOOKBACK_HOURS). Same
  channel list, far fewer programmes - this is the one to use on
  memory-constrained devices such as Android TV sticks. The filename is
  deliberately window-agnostic so the URL configured in a player stays
  valid if the window is ever retuned.

The merge streams element-by-element straight into the gzip writers, so peak
memory stays low no matter how large the combined guide gets.
"""

import concurrent.futures
import gzip
import io
import os
import shutil
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

BASE_URL = "https://epgshare01.online/epgshare01/epg_ripper_{}.xml.gz"
OUT_DIR = "public"
MAX_WORKERS = 8
RETRIES = 2
TIMEOUT = 60

# Rolling window kept in the trimmed combined guide.
#
# IMPORTANT: the window is evaluated when this script RUNS, not when a device
# downloads the file. Worst-case forward coverage, just before the next
# rebuild, is WINDOW_HOURS minus the rebuild interval - so WINDOW_HOURS must
# comfortably exceed how often the workflow runs, or the file goes stale
# between builds. The workflow rebuilds every 6 hours, so 18h here guarantees
# at least 12h of forward listings at any moment.
WINDOW_HOURS = 18
LOOKBACK_HOURS = 3  # keeps just-finished programmes, absorbs device clock skew
REBUILD_INTERVAL_HOURS = 6  # keep in sync with the cron in the workflow file

REGIONS = {
    "north_america": {
        "CA2": "Canada",
        "MX1": "Mexico",
        "US2": "United States",
        "US_SPORTS1": "United States (Sports)",
        "CR1": "Costa Rica",
        "PA1": "Panama",
        "SV1": "El Salvador",
    },
    "caribbean": {
        "BB1": "Barbados",
        "DO1": "Dominican Republic",
        "JM1": "Jamaica",
    },
    "south_america": {
        "AR1": "Argentina",
        "BR1": "Brazil",
        "BR2": "Brazil (alt. source)",
        "CL1": "Chile",
        "CO1": "Colombia",
        "EC1": "Ecuador",
        "PE1": "Peru",
        "UY1": "Uruguay",
    },
    "europe": {
        "AL1": "Albania",
        "AT1": "Austria",
        "BA1": "Bosnia and Herzegovina",
        "BE2": "Belgium",
        "BG1": "Bulgaria",
        "CH1": "Switzerland",
        "CY1": "Cyprus",
        "CZ1": "Czechia",
        "DE1": "Germany",
        "DK1": "Denmark",
        "ES1": "Spain",
        "FI1": "Finland",
        "FR1": "France",
        "GR1": "Greece",
        "HR1": "Croatia",
        "HU1": "Hungary",
        "IE1": "Ireland",
        "IT1": "Italy",
        "LT1": "Lithuania",
        "LU1": "Luxembourg",
        "LV1": "Latvia",
        "MT1": "Malta",
        "NL1": "Netherlands",
        "NO1": "Norway",
        "PL1": "Poland",
        "PT1": "Portugal",
        "RO1": "Romania",
        "RO2": "Romania (alt. source)",
        "RS1": "Serbia",
        "SE1": "Sweden",
        "SK1": "Slovakia",
        "TR1": "Turkey",
        "TR3": "Turkey (alt. source)",
        "UK1": "United Kingdom",
        "viva-russia.ru": "Russia",
    },
    "africa": {
        "EG1": "Egypt",
        "KE1": "Kenya",
        "NG1": "Nigeria",
        "ZA1": "South Africa",
    },
    "asia": {
        "AE1": "United Arab Emirates",
        "ASIANTELEVISION1": "Asian Television (multi-country)",
        "HK1": "Hong Kong",
        "ID1": "Indonesia",
        "IL1": "Israel",
        "IN1": "India",
        "IN2": "India (alt. source 2)",
        "IN4": "India (alt. source 4)",
        "JP1": "Japan",
        "JP2": "Japan (alt. source)",
        "KR1": "South Korea",
        "MN1": "Mongolia",
        "MY1": "Malaysia",
        "PH1": "Philippines",
        "PH2": "Philippines (alt. source)",
        "PK1": "Pakistan",
        "SA1": "Saudi Arabia",
        "SA2": "Saudi Arabia (alt. source)",
        "SG1": "Singapore",
        "TH1": "Thailand",
        "VN1": "Vietnam",
    },
}


def human_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def fetch_one(region, code, name):
    url = BASE_URL.format(code)
    dest_dir = os.path.join(OUT_DIR, region)
    dest = os.path.join(dest_dir, f"{code}.xml.gz")

    last_error = None
    for attempt in range(1, RETRIES + 2):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "mainstreams-epg/1.0"}
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = resp.read()

            # Sanity check: make sure we actually got a gzip'd XMLTV file,
            # not e.g. an HTML error page saved with a .gz extension.
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
                head = gz.read(256)
                if b"<tv" not in head and b"<?xml" not in head:
                    raise ValueError("response did not look like XMLTV")

            with open(dest, "wb") as out:
                out.write(data)

            return region, code, name, len(data), True, None
        except Exception as e:  # noqa: BLE001 - want to catch+record anything
            last_error = e
            if attempt <= RETRIES:
                time.sleep(2 * attempt)
    return region, code, name, 0, False, str(last_error)


def parse_xmltv_time(value):
    """Parse an XMLTV timestamp into an aware UTC datetime.

    Accepts the usual ``YYYYMMDDHHMMSS +0100`` form, a bare
    ``YYYYMMDDHHMMSS`` (treated as UTC), and shorter stamps such as
    ``YYYYMMDDHHMM`` which are zero-padded. Returns None if unparseable.
    """
    if not value:
        return None
    parts = value.strip().split()
    if not parts:
        return None
    stamp = parts[0]
    offset = parts[1] if len(parts) > 1 else None

    if len(stamp) < 14:
        stamp = stamp.ljust(14, "0")
    try:
        dt = datetime.strptime(stamp[:14], "%Y%m%d%H%M%S")
    except ValueError:
        return None

    if offset and len(offset) >= 5 and offset[0] in "+-":
        try:
            sign = 1 if offset[0] == "+" else -1
            delta = timedelta(hours=int(offset[1:3]), minutes=int(offset[3:5]))
            dt = dt - sign * delta  # local time -> UTC
        except ValueError:
            pass

    return dt.replace(tzinfo=timezone.utc)


def in_window(prog, win_start, win_end):
    """True if a <programme> overlaps the rolling window.

    Unparseable/absent start times are excluded - a programme with no usable
    time can't drive a 'now playing' banner anyway. Missing stop falls back to
    start so such entries are still judged on when they begin.
    """
    start = parse_xmltv_time(prog.get("start"))
    if start is None:
        return False
    stop = parse_xmltv_time(prog.get("stop")) or start
    return stop > win_start and start < win_end


def merge_all():
    """Stream every fetched per-country file into two combined guides:
    the full merge and a window-trimmed one."""
    if WINDOW_HOURS <= REBUILD_INTERVAL_HOURS:
        print(
            f"  WARNING: WINDOW_HOURS ({WINDOW_HOURS}) is not greater than the "
            f"rebuild interval ({REBUILD_INTERVAL_HOURS}h). The trimmed guide "
            f"will contain no forward listings just before the next rebuild."
        )

    now = datetime.now(timezone.utc)
    win_start = now - timedelta(hours=LOOKBACK_HOURS)
    win_end = now + timedelta(hours=WINDOW_HOURS)

    full_path = os.path.join(OUT_DIR, "all.xml.gz")
    trim_path = os.path.join(OUT_DIR, "all_recent.xml.gz")

    header = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<tv generator-info-name="mainstreams-epg" '
        'generator-info-url="https://github.com/mrjuse/mainstreams-epg">\n'
    )

    seen_channel_ids = set()
    channels = 0
    progs_full = 0
    progs_trim = 0
    no_time = 0
    included = 0

    with gzip.open(full_path, "wt", encoding="utf-8", compresslevel=6) as full, \
         gzip.open(trim_path, "wt", encoding="utf-8", compresslevel=6) as trim:
        full.write(header)
        trim.write(header)

        for region, codes in REGIONS.items():
            for code in codes:
                src = os.path.join(OUT_DIR, region, f"{code}.xml.gz")
                if not os.path.exists(src):
                    continue  # that source failed to fetch this run
                try:
                    with gzip.open(src, "rb") as f:
                        context = ET.iterparse(f, events=("start", "end"))
                        _, root = next(context)
                        for event, elem in context:
                            if event != "end" or elem.tag not in ("channel", "programme"):
                                continue
                            elem.tail = None
                            if elem.tag == "channel":
                                cid = elem.get("id")
                                if cid and cid in seen_channel_ids:
                                    elem.clear()
                                    root.clear()
                                    continue
                                if cid:
                                    seen_channel_ids.add(cid)
                                xml = ET.tostring(elem, encoding="unicode")
                                full.write(xml)
                                full.write("\n")
                                trim.write(xml)
                                trim.write("\n")
                                channels += 1
                            else:
                                xml = ET.tostring(elem, encoding="unicode")
                                full.write(xml)
                                full.write("\n")
                                progs_full += 1
                                if parse_xmltv_time(elem.get("start")) is None:
                                    no_time += 1
                                elif in_window(elem, win_start, win_end):
                                    trim.write(xml)
                                    trim.write("\n")
                                    progs_trim += 1
                            elem.clear()
                            root.clear()
                    included += 1
                except Exception as e:  # noqa: BLE001
                    print(f"  WARN: problem reading {src} during merge ({e})")

        full.write("</tv>\n")
        trim.write("</tv>\n")

    full_size = os.path.getsize(full_path)
    trim_size = os.path.getsize(trim_path)
    pct = (100.0 * progs_trim / progs_full) if progs_full else 0.0

    print(
        f"Merged {included} sources: {channels} channels, "
        f"{progs_full} programmes total"
    )
    if no_time:
        print(f"  ({no_time} programmes had no parseable start time)")
    print(f"  all.xml.gz     -> {human_size(full_size)} gzip (all programmes)")
    print(
        f"  all_recent.xml.gz -> {human_size(trim_size)} gzip "
        f"({progs_trim} programmes, {pct:.1f}% of total, "
        f"-{LOOKBACK_HOURS}h/+{WINDOW_HOURS}h window)"
    )
    return full_size, trim_size


def write_index(results, full_size=None, trim_size=None):
    by_region = {}
    for region, code, name, size, ok, err in results:
        by_region.setdefault(region, []).append((code, name, size, ok, err))

    total_ok = sum(1 for r in results if r[4])
    total_size = sum(r[3] for r in results if r[4])

    html = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>Mainstreams EPG</title>",
        "<style>",
        "body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:960px;",
        "margin:2rem auto;padding:0 1rem;color:#1a1a1a}",
        "h1{margin-bottom:.25rem}",
        ".sub{color:#666;margin-top:0}",
        "h2{margin-top:2.5rem;border-bottom:2px solid #eee;padding-bottom:.25rem}",
        "table{width:100%;border-collapse:collapse;margin-top:.5rem}",
        "td,th{padding:.4rem .5rem;text-align:left;border-bottom:1px solid #eee;font-size:.95rem}",
        "th{color:#666;font-weight:600}",
        "code{background:#f4f4f4;padding:.15rem .4rem;border-radius:4px;font-size:.9rem}",
        "a{color:#0969da;text-decoration:none}a:hover{text-decoration:underline}",
        ".fail{color:#b42318}",
        ".meta{color:#666;font-size:.9rem}",
        ".combined{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;",
        "padding:1rem 1.25rem;margin-top:1.5rem}",
        ".combined h3{margin:0 0 .5rem}",
        ".combined p{margin:.5rem 0}",
        ".rec{color:#1a7f37;font-weight:600}",
        "</style></head><body>",
        "<h1>Mainstreams EPG</h1>",
        (
            "<p class='sub'>Gzip-compressed XMLTV guide files, regenerated daily. "
            "Add whichever file URL(s) below to your player as an EPG/XMLTV source "
            "&mdash; only add the countries you actually need.</p>"
        ),
        f"<p class='meta'>{total_ok}/{len(results)} sources fetched successfully "
        f"&middot; {human_size(total_size)} total</p>",
    ]

    if full_size is not None:
        html.append("<div class='combined'>")
        html.append("<h3>Need every region in one file?</h3>")
        html.append(
            "<p><a href='all_recent.xml.gz'><code>all_recent.xml.gz</code></a> "
            f"({human_size(trim_size)}) <span class='rec'>&larr; recommended</span><br>"
            "Every channel from every region, but only programmes airing in a "
            f"rolling &minus;{LOOKBACK_HOURS}h/+{WINDOW_HOURS}h window. Use this "
            "one if your playlist mixes countries &mdash; it is small enough to "
            "parse comfortably on set-top boxes and TV sticks.</p>"
        )
        html.append(
            "<p><a href='all.xml.gz'><code>all.xml.gz</code></a> "
            f"({human_size(full_size)})<br>"
            "The same merge with the complete multi-day listings. Only worth it "
            "if you genuinely need the full schedule depth and your device has "
            "the memory for it.</p>"
        )
        html.append("</div>")

    for region in REGIONS:
        entries = sorted(by_region.get(region, []), key=lambda r: r[1])
        html.append(f"<h2>{region.replace('_', ' ').title()}</h2>")
        html.append("<table><tr><th>Country / source</th><th>File</th><th>Size</th></tr>")
        for code, name, size, ok, err in entries:
            path = f"{region}/{code}.xml.gz"
            if ok:
                html.append(
                    f"<tr><td>{name}</td><td><a href='{path}'><code>{path}</code></a></td>"
                    f"<td>{human_size(size)}</td></tr>"
                )
            else:
                html.append(
                    f"<tr><td>{name}</td><td class='fail' colspan='2'>"
                    f"unavailable today</td></tr>"
                )
        html.append("</table>")

    html.append("</body></html>")

    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write("\n".join(html))


def main():
    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    for region in REGIONS:
        os.makedirs(os.path.join(OUT_DIR, region), exist_ok=True)

    jobs = [
        (region, code, name)
        for region, codes in REGIONS.items()
        for code, name in codes.items()
    ]

    print(f"Fetching {len(jobs)} sources with {MAX_WORKERS} parallel workers...")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(fetch_one, *job) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            region, code, name, size, ok, err = future.result()
            results.append((region, code, name, size, ok, err))
            if ok:
                print(f"  OK   {region}/{code} ({name}) - {human_size(size)}")
            else:
                print(f"  FAIL {region}/{code} ({name}) - {err}")

    ok_count = sum(1 for r in results if r[4])
    print(f"\nDone: {ok_count}/{len(results)} sources fetched successfully.")

    print("\nMerging into combined files...")
    full_size, trim_size = merge_all()

    write_index(results, full_size=full_size, trim_size=trim_size)


if __name__ == "__main__":
    main()
