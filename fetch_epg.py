#!/usr/bin/env python3
"""
Fetches XMLTV EPG guide files (gzip-compressed) from epgshare01.online for a
curated set of countries/sources across North America, the Caribbean, South
America, Europe (including Spain), Africa, and Asia, and lays them out as
static files for GitHub Pages.

Deliberately does NOT merge files together: per-country files stay small,
so a player only has to download the guide(s) it actually needs, and the
build stays fast and memory-light.
"""

import concurrent.futures
import gzip
import io
import os
import shutil
import time
import urllib.error
import urllib.request

BASE_URL = "https://epgshare01.online/epgshare01/epg_ripper_{}.xml.gz"
OUT_DIR = "public"
MAX_WORKERS = 8
RETRIES = 2
TIMEOUT = 60

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


def write_index(results):
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
            if ok:#!/usr/bin/env python3
"""
Fetches XMLTV EPG guide files (gzip-compressed) from epgshare01.online for a
curated set of countries/sources across North America, the Caribbean, South
America, Europe (including Spain), Africa, and Asia, and lays them out as
static files for GitHub Pages.

Per-country files stay small, so a player that only needs one country can
download just that file. For players/apps that only support a single EPG
URL and mix channels from many regions in one playlist, this also builds a
combined `all.xml.gz` merging every successfully-fetched source into one
XMLTV file.
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

BASE_URL = "https://epgshare01.online/epgshare01/epg_ripper_{}.xml.gz"
OUT_DIR = "public"
MAX_WORKERS = 8
RETRIES = 2
TIMEOUT = 60

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


def merge_all():
    """Merge every successfully-fetched per-country file into one combined
    XMLTV file, for players/apps that only support a single EPG URL and mix
    channels from multiple regions in one playlist."""
    root = ET.Element(
        "tv",
        {
            "generator-info-name": "mainstreams-epg",
            "generator-info-url": "https://github.com/mrjuse/mainstreams-epg",
        },
    )
    seen_channel_ids = set()
    channel_count = 0
    programme_count = 0
    included = 0

    for region, codes in REGIONS.items():
        for code in codes:
            src = os.path.join(OUT_DIR, region, f"{code}.xml.gz")
            if not os.path.exists(src):
                continue  # that source failed to fetch this run
            try:
                with gzip.open(src, "rb") as f:
                    src_root = ET.fromstring(f.read())
            except Exception as e:  # noqa: BLE001
                print(f"  WARN: skipping {src} in merge ({e})")
                continue
            included += 1
            for chan in src_root.findall("channel"):
                cid = chan.get("id")
                if cid and cid in seen_channel_ids:
                    continue
                if cid:
                    seen_channel_ids.add(cid)
                root.append(chan)
                channel_count += 1
            for prog in src_root.findall("programme"):
                root.append(prog)
                programme_count += 1

    tree = ET.ElementTree(root)
    buf = io.BytesIO()
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    uncompressed = buf.getvalue()

    out_path = os.path.join(OUT_DIR, "all.xml.gz")
    with gzip.open(out_path, "wb", compresslevel=6) as gz:
        gz.write(uncompressed)

    compressed_size = os.path.getsize(out_path)
    print(
        f"Merged {included} sources into all.xml.gz: "
        f"{channel_count} channels, {programme_count} programmes, "
        f"{human_size(len(uncompressed))} uncompressed / "
        f"{human_size(compressed_size)} gzip"
    )
    return compressed_size


def write_index(results, combined_size=None):
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
        ".combined{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:1rem;margin-top:1.5rem}",
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

    if combined_size is not None:
        html.append(
            "<div class='combined'><strong>Need everything in one file?</strong> "
            "<a href='all.xml.gz'><code>all.xml.gz</code></a> "
            f"({human_size(combined_size)}) merges every region above into a single "
            "XMLTV guide &mdash; use this if your playlist mixes channels from "
            "multiple countries and your player only accepts one EPG URL. "
            "It's a much larger download than any single-country file, so prefer "
            "the individual files above when you can.</div>"
        )

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

    print("\nMerging into a single combined file...")
    combined_size = merge_all()

    write_index(results, combined_size=combined_size)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Fetches XMLTV EPG guide files (gzip-compressed) from epgshare01.online for a
curated set of countries/sources across North America, the Caribbean, South
America, Europe (including Spain), Africa, and Asia, and lays them out as
static files for GitHub Pages.

Per-country files stay small, so a player that only needs one country can
download just that file. For players/apps that only support a single EPG
URL and mix channels from many regions in one playlist, this also builds a
combined `all.xml.gz` merging every successfully-fetched source into one
XMLTV file.
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

BASE_URL = "https://epgshare01.online/epgshare01/epg_ripper_{}.xml.gz"
OUT_DIR = "public"
MAX_WORKERS = 8
RETRIES = 2
TIMEOUT = 60

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


def merge_all():
    """Merge every successfully-fetched per-country file into one combined
    XMLTV file, for players/apps that only support a single EPG URL and mix
    channels from multiple regions in one playlist."""
    root = ET.Element(
        "tv",
        {
            "generator-info-name": "mainstreams-epg",
            "generator-info-url": "https://github.com/mrjuse/mainstreams-epg",
        },
    )
    seen_channel_ids = set()
    channel_count = 0
    programme_count = 0
    included = 0

    for region, codes in REGIONS.items():
        for code in codes:
            src = os.path.join(OUT_DIR, region, f"{code}.xml.gz")
            if not os.path.exists(src):
                continue  # that source failed to fetch this run
            try:
                with gzip.open(src, "rb") as f:
                    src_root = ET.fromstring(f.read())
            except Exception as e:  # noqa: BLE001
                print(f"  WARN: skipping {src} in merge ({e})")
                continue
            included += 1
            for chan in src_root.findall("channel"):
                cid = chan.get("id")
                if cid and cid in seen_channel_ids:
                    continue
                if cid:
                    seen_channel_ids.add(cid)
                root.append(chan)
                channel_count += 1
            for prog in src_root.findall("programme"):
                root.append(prog)
                programme_count += 1

    tree = ET.ElementTree(root)
    buf = io.BytesIO()
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    uncompressed = buf.getvalue()

    out_path = os.path.join(OUT_DIR, "all.xml.gz")
    with gzip.open(out_path, "wb", compresslevel=6) as gz:
        gz.write(uncompressed)

    compressed_size = os.path.getsize(out_path)
    print(
        f"Merged {included} sources into all.xml.gz: "
        f"{channel_count} channels, {programme_count} programmes, "
        f"{human_size(len(uncompressed))} uncompressed / "
        f"{human_size(compressed_size)} gzip"
    )
    return compressed_size


def write_index(results, combined_size=None):
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
        ".combined{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:1rem;margin-top:1.5rem}",
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

    if combined_size is not None:
        html.append(
            "<div class='combined'><strong>Need everything in one file?</strong> "
            "<a href='all.xml.gz'><code>all.xml.gz</code></a> "
            f"({human_size(combined_size)}) merges every region above into a single "
            "XMLTV guide &mdash; use this if your playlist mixes channels from "
            "multiple countries and your player only accepts one EPG URL. "
            "It's a much larger download than any single-country file, so prefer "
            "the individual files above when you can.</div>"
        )

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

    print("\nMerging into a single combined file...")
    combined_size = merge_all()

    write_index(results, combined_size=combined_size)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Fetches XMLTV EPG guide files (gzip-compressed) from epgshare01.online for a
curated set of countries/sources across North America, the Caribbean, South
America, Europe (including Spain), Africa, and Asia, and lays them out as
static files for GitHub Pages.

Per-country files stay small, so a player that only needs one country can
download just that file. For players/apps that only support a single EPG
URL and mix channels from many regions in one playlist, this also builds a
combined `all.xml.gz` merging every successfully-fetched source into one
XMLTV file.
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

BASE_URL = "https://epgshare01.online/epgshare01/epg_ripper_{}.xml.gz"
OUT_DIR = "public"
MAX_WORKERS = 8
RETRIES = 2
TIMEOUT = 60

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


def merge_all():
    """Merge every successfully-fetched per-country file into one combined
    XMLTV file, for players/apps that only support a single EPG URL and mix
    channels from multiple regions in one playlist."""
    root = ET.Element(
        "tv",
        {
            "generator-info-name": "mainstreams-epg",
            "generator-info-url": "https://github.com/mrjuse/mainstreams-epg",
        },
    )
    seen_channel_ids = set()
    channel_count = 0
    programme_count = 0
    included = 0

    for region, codes in REGIONS.items():
        for code in codes:
            src = os.path.join(OUT_DIR, region, f"{code}.xml.gz")
            if not os.path.exists(src):
                continue  # that source failed to fetch this run
            try:
                with gzip.open(src, "rb") as f:
                    src_root = ET.fromstring(f.read())
            except Exception as e:  # noqa: BLE001
                print(f"  WARN: skipping {src} in merge ({e})")
                continue
            included += 1
            for chan in src_root.findall("channel"):
                cid = chan.get("id")
                if cid and cid in seen_channel_ids:
                    continue
                if cid:
                    seen_channel_ids.add(cid)
                root.append(chan)
                channel_count += 1
            for prog in src_root.findall("programme"):
                root.append(prog)
                programme_count += 1

    tree = ET.ElementTree(root)
    buf = io.BytesIO()
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    uncompressed = buf.getvalue()

    out_path = os.path.join(OUT_DIR, "all.xml.gz")
    with gzip.open(out_path, "wb", compresslevel=6) as gz:
        gz.write(uncompressed)

    compressed_size = os.path.getsize(out_path)
    print(
        f"Merged {included} sources into all.xml.gz: "
        f"{channel_count} channels, {programme_count} programmes, "
        f"{human_size(len(uncompressed))} uncompressed / "
        f"{human_size(compressed_size)} gzip"
    )
    return compressed_size


def write_index(results, combined_size=None):
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
        ".combined{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:1rem;margin-top:1.5rem}",
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

    if combined_size is not None:
        html.append(
            "<div class='combined'><strong>Need everything in one file?</strong> "
            "<a href='all.xml.gz'><code>all.xml.gz</code></a> "
            f"({human_size(combined_size)}) merges every region above into a single "
            "XMLTV guide &mdash; use this if your playlist mixes channels from "
            "multiple countries and your player only accepts one EPG URL. "
            "It's a much larger download than any single-country file, so prefer "
            "the individual files above when you can.</div>"
        )

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

    print("\nMerging into a single combined file...")
    combined_size = merge_all()

    write_index(results, combined_size=combined_size)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Fetches XMLTV EPG guide files (gzip-compressed) from epgshare01.online for a
curated set of countries/sources across North America, the Caribbean, South
America, Europe (including Spain), Africa, and Asia, and lays them out as
static files for GitHub Pages.

Per-country files stay small, so a player that only needs one country can
download just that file. For players/apps that only support a single EPG
URL and mix channels from many regions in one playlist, this also builds a
combined `all.xml.gz` merging every successfully-fetched source into one
XMLTV file.
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

BASE_URL = "https://epgshare01.online/epgshare01/epg_ripper_{}.xml.gz"
OUT_DIR = "public"
MAX_WORKERS = 8
RETRIES = 2
TIMEOUT = 60

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


def merge_all():
    """Merge every successfully-fetched per-country file into one combined
    XMLTV file, for players/apps that only support a single EPG URL and mix
    channels from multiple regions in one playlist."""
    root = ET.Element(
        "tv",
        {
            "generator-info-name": "mainstreams-epg",
            "generator-info-url": "https://github.com/mrjuse/mainstreams-epg",
        },
    )
    seen_channel_ids = set()
    channel_count = 0
    programme_count = 0
    included = 0

    for region, codes in REGIONS.items():
        for code in codes:
            src = os.path.join(OUT_DIR, region, f"{code}.xml.gz")
            if not os.path.exists(src):
                continue  # that source failed to fetch this run
            try:
                with gzip.open(src, "rb") as f:
                    src_root = ET.fromstring(f.read())
            except Exception as e:  # noqa: BLE001
                print(f"  WARN: skipping {src} in merge ({e})")
                continue
            included += 1
            for chan in src_root.findall("channel"):
                cid = chan.get("id")
                if cid and cid in seen_channel_ids:
                    continue
                if cid:
                    seen_channel_ids.add(cid)
                root.append(chan)
                channel_count += 1
            for prog in src_root.findall("programme"):
                root.append(prog)
                programme_count += 1

    tree = ET.ElementTree(root)
    buf = io.BytesIO()
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    uncompressed = buf.getvalue()

    out_path = os.path.join(OUT_DIR, "all.xml.gz")
    with gzip.open(out_path, "wb", compresslevel=6) as gz:
        gz.write(uncompressed)

    compressed_size = os.path.getsize(out_path)
    print(
        f"Merged {included} sources into all.xml.gz: "
        f"{channel_count} channels, {programme_count} programmes, "
        f"{human_size(len(uncompressed))} uncompressed / "
        f"{human_size(compressed_size)} gzip"
    )
    return compressed_size


def write_index(results, combined_size=None):
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
        ".combined{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:1rem;margin-top:1.5rem}",
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

    if combined_size is not None:
        html.append(
            "<div class='combined'><strong>Need everything in one file?</strong> "
            "<a href='all.xml.gz'><code>all.xml.gz</code></a> "
            f"({human_size(combined_size)}) merges every region above into a single "
            "XMLTV guide &mdash; use this if your playlist mixes channels from "
            "multiple countries and your player only accepts one EPG URL. "
            "It's a much larger download than any single-country file, so prefer "
            "the individual files above when you can.</div>"
        )

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

    print("\nMerging into a single combined file...")
    combined_size = merge_all()

    write_index(results, combined_size=combined_size)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Fetches XMLTV EPG guide files (gzip-compressed) from epgshare01.online for a
curated set of countries/sources across North America, the Caribbean, South
America, Europe (including Spain), Africa, and Asia, and lays them out as
static files for GitHub Pages.

Per-country files stay small, so a player that only needs one country can
download just that file. For players/apps that only support a single EPG
URL and mix channels from many regions in one playlist, this also builds a
combined `all.xml.gz` merging every successfully-fetched source into one
XMLTV file.
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

BASE_URL = "https://epgshare01.online/epgshare01/epg_ripper_{}.xml.gz"
OUT_DIR = "public"
MAX_WORKERS = 8
RETRIES = 2
TIMEOUT = 60

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


def merge_all():
    """Merge every successfully-fetched per-country file into one combined
    XMLTV file, for players/apps that only support a single EPG URL and mix
    channels from multiple regions in one playlist."""
    root = ET.Element(
        "tv",
        {
            "generator-info-name": "mainstreams-epg",
            "generator-info-url": "https://github.com/mrjuse/mainstreams-epg",
        },
    )
    seen_channel_ids = set()
    channel_count = 0
    programme_count = 0
    included = 0

    for region, codes in REGIONS.items():
        for code in codes:
            src = os.path.join(OUT_DIR, region, f"{code}.xml.gz")
            if not os.path.exists(src):
                continue  # that source failed to fetch this run
            try:
                with gzip.open(src, "rb") as f:
                    src_root = ET.fromstring(f.read())
            except Exception as e:  # noqa: BLE001
                print(f"  WARN: skipping {src} in merge ({e})")
                continue
            included += 1
            for chan in src_root.findall("channel"):
                cid = chan.get("id")
                if cid and cid in seen_channel_ids:
                    continue
                if cid:
                    seen_channel_ids.add(cid)
                root.append(chan)
                channel_count += 1
            for prog in src_root.findall("programme"):
                root.append(prog)
                programme_count += 1

    tree = ET.ElementTree(root)
    buf = io.BytesIO()
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    uncompressed = buf.getvalue()

    out_path = os.path.join(OUT_DIR, "all.xml.gz")
    with gzip.open(out_path, "wb", compresslevel=6) as gz:
        gz.write(uncompressed)

    compressed_size = os.path.getsize(out_path)
    print(
        f"Merged {included} sources into all.xml.gz: "
        f"{channel_count} channels, {programme_count} programmes, "
        f"{human_size(len(uncompressed))} uncompressed / "
        f"{human_size(compressed_size)} gzip"
    )
    return compressed_size


def write_index(results, combined_size=None):
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
        ".combined{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:1rem;margin-top:1.5rem}",
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

    if combined_size is not None:
        html.append(
            "<div class='combined'><strong>Need everything in one file?</strong> "
            "<a href='all.xml.gz'><code>all.xml.gz</code></a> "
            f"({human_size(combined_size)}) merges every region above into a single "
            "XMLTV guide &mdash; use this if your playlist mixes channels from "
            "multiple countries and your player only accepts one EPG URL. "
            "It's a much larger download than any single-country file, so prefer "
            "the individual files above when you can.</div>"
        )

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

    print("\nMerging into a single combined file...")
    combined_size = merge_all()

    write_index(results, combined_size=combined_size)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Fetches XMLTV EPG guide files (gzip-compressed) from epgshare01.online for a
curated set of countries/sources across North America, the Caribbean, South
America, Europe (including Spain), Africa, and Asia, and lays them out as
static files for GitHub Pages.

Per-country files stay small, so a player that only needs one country can
download just that file. For players/apps that only support a single EPG
URL and mix channels from many regions in one playlist, this also builds a
combined `all.xml.gz` merging every successfully-fetched source into one
XMLTV file.
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

BASE_URL = "https://epgshare01.online/epgshare01/epg_ripper_{}.xml.gz"
OUT_DIR = "public"
MAX_WORKERS = 8
RETRIES = 2
TIMEOUT = 60

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


def merge_all():
    """Merge every successfully-fetched per-country file into one combined
    XMLTV file, for players/apps that only support a single EPG URL and mix
    channels from multiple regions in one playlist."""
    root = ET.Element(
        "tv",
        {
            "generator-info-name": "mainstreams-epg",
            "generator-info-url": "https://github.com/mrjuse/mainstreams-epg",
        },
    )
    seen_channel_ids = set()
    channel_count = 0
    programme_count = 0
    included = 0

    for region, codes in REGIONS.items():
        for code in codes:
            src = os.path.join(OUT_DIR, region, f"{code}.xml.gz")
            if not os.path.exists(src):
                continue  # that source failed to fetch this run
            try:
                with gzip.open(src, "rb") as f:
                    src_root = ET.fromstring(f.read())
            except Exception as e:  # noqa: BLE001
                print(f"  WARN: skipping {src} in merge ({e})")
                continue
            included += 1
            for chan in src_root.findall("channel"):
                cid = chan.get("id")
                if cid and cid in seen_channel_ids:
                    continue
                if cid:
                    seen_channel_ids.add(cid)
                root.append(chan)
                channel_count += 1
            for prog in src_root.findall("programme"):
                root.append(prog)
                programme_count += 1

    tree = ET.ElementTree(root)
    buf = io.BytesIO()
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    uncompressed = buf.getvalue()

    out_path = os.path.join(OUT_DIR, "all.xml.gz")
    with gzip.open(out_path, "wb", compresslevel=6) as gz:
        gz.write(uncompressed)

    compressed_size = os.path.getsize(out_path)
    print(
        f"Merged {included} sources into all.xml.gz: "
        f"{channel_count} channels, {programme_count} programmes, "
        f"{human_size(len(uncompressed))} uncompressed / "
        f"{human_size(compressed_size)} gzip"
    )
    return compressed_size


def write_index(results, combined_size=None):
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
        ".combined{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:1rem;margin-top:1.5rem}",
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

    if combined_size is not None:
        html.append(
            "<div class='combined'><strong>Need everything in one file?</strong> "
            "<a href='all.xml.gz'><code>all.xml.gz</code></a> "
            f"({human_size(combined_size)}) merges every region above into a single "
            "XMLTV guide &mdash; use this if your playlist mixes channels from "
            "multiple countries and your player only accepts one EPG URL. "
            "It's a much larger download than any single-country file, so prefer "
            "the individual files above when you can.</div>"
        )

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

    print("\nMerging into a single combined file...")
    combined_size = merge_all()

    write_index(results, combined_size=combined_size)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Fetches XMLTV EPG guide files (gzip-compressed) from epgshare01.online for a
curated set of countries/sources across North America, the Caribbean, South
America, Europe (including Spain), Africa, and Asia, and lays them out as
static files for GitHub Pages.

Per-country files stay small, so a player that only needs one country can
download just that file. For players/apps that only support a single EPG
URL and mix channels from many regions in one playlist, this also builds a
combined `all.xml.gz` merging every successfully-fetched source into one
XMLTV file.
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

BASE_URL = "https://epgshare01.online/epgshare01/epg_ripper_{}.xml.gz"
OUT_DIR = "public"
MAX_WORKERS = 8
RETRIES = 2
TIMEOUT = 60

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


def merge_all():
    """Merge every successfully-fetched per-country file into one combined
    XMLTV file, for players/apps that only support a single EPG URL and mix
    channels from multiple regions in one playlist."""
    root = ET.Element(
        "tv",
        {
            "generator-info-name": "mainstreams-epg",
            "generator-info-url": "https://github.com/mrjuse/mainstreams-epg",
        },
    )
    seen_channel_ids = set()
    channel_count = 0
    programme_count = 0
    included = 0

    for region, codes in REGIONS.items():
        for code in codes:
            src = os.path.join(OUT_DIR, region, f"{code}.xml.gz")
            if not os.path.exists(src):
                continue  # that source failed to fetch this run
            try:
                with gzip.open(src, "rb") as f:
                    src_root = ET.fromstring(f.read())
            except Exception as e:  # noqa: BLE001
                print(f"  WARN: skipping {src} in merge ({e})")
                continue
            included += 1
            for chan in src_root.findall("channel"):
                cid = chan.get("id")
                if cid and cid in seen_channel_ids:
                    continue
                if cid:
                    seen_channel_ids.add(cid)
                root.append(chan)
                channel_count += 1
            for prog in src_root.findall("programme"):
                root.append(prog)
                programme_count += 1

    tree = ET.ElementTree(root)
    buf = io.BytesIO()
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    uncompressed = buf.getvalue()

    out_path = os.path.join(OUT_DIR, "all.xml.gz")
    with gzip.open(out_path, "wb", compresslevel=6) as gz:
        gz.write(uncompressed)

    compressed_size = os.path.getsize(out_path)
    print(
        f"Merged {included} sources into all.xml.gz: "
        f"{channel_count} channels, {programme_count} programmes, "
        f"{human_size(len(uncompressed))} uncompressed / "
        f"{human_size(compressed_size)} gzip"
    )
    return compressed_size


def write_index(results, combined_size=None):
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
        ".combined{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:1rem;margin-top:1.5rem}",
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

    if combined_size is not None:
        html.append(
            "<div class='combined'><strong>Need everything in one file?</strong> "
            "<a href='all.xml.gz'><code>all.xml.gz</code></a> "
            f"({human_size(combined_size)}) merges every region above into a single "
            "XMLTV guide &mdash; use this if your playlist mixes channels from "
            "multiple countries and your player only accepts one EPG URL. "
            "It's a much larger download than any single-country file, so prefer "
            "the individual files above when you can.</div>"
        )

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

    print("\nMerging into a single combined file...")
    combined_size = merge_all()

    write_index(results, combined_size=combined_size)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Fetches XMLTV EPG guide files (gzip-compressed) from epgshare01.online for a
curated set of countries/sources across North America, the Caribbean, South
America, Europe (including Spain), Africa, and Asia, and lays them out as
static files for GitHub Pages.

Per-country files stay small, so a player that only needs one country can
download just that file. For players/apps that only support a single EPG
URL and mix channels from many regions in one playlist, this also builds a
combined `all.xml.gz` merging every successfully-fetched source into one
XMLTV file.
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

BASE_URL = "https://epgshare01.online/epgshare01/epg_ripper_{}.xml.gz"
OUT_DIR = "public"
MAX_WORKERS = 8
RETRIES = 2
TIMEOUT = 60

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


def merge_all():
    """Merge every successfully-fetched per-country file into one combined
    XMLTV file, for players/apps that only support a single EPG URL and mix
    channels from multiple regions in one playlist."""
    root = ET.Element(
        "tv",
        {
            "generator-info-name": "mainstreams-epg",
            "generator-info-url": "https://github.com/mrjuse/mainstreams-epg",
        },
    )
    seen_channel_ids = set()
    channel_count = 0
    programme_count = 0
    included = 0

    for region, codes in REGIONS.items():
        for code in codes:
            src = os.path.join(OUT_DIR, region, f"{code}.xml.gz")
            if not os.path.exists(src):
                continue  # that source failed to fetch this run
            try:
                with gzip.open(src, "rb") as f:
                    src_root = ET.fromstring(f.read())
            except Exception as e:  # noqa: BLE001
                print(f"  WARN: skipping {src} in merge ({e})")
                continue
            included += 1
            for chan in src_root.findall("channel"):
                cid = chan.get("id")
                if cid and cid in seen_channel_ids:
                    continue
                if cid:
                    seen_channel_ids.add(cid)
                root.append(chan)
                channel_count += 1
            for prog in src_root.findall("programme"):
                root.append(prog)
                programme_count += 1

    tree = ET.ElementTree(root)
    buf = io.BytesIO()
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    uncompressed = buf.getvalue()

    out_path = os.path.join(OUT_DIR, "all.xml.gz")
    with gzip.open(out_path, "wb", compresslevel=6) as gz:
        gz.write(uncompressed)

    compressed_size = os.path.getsize(out_path)
    print(
        f"Merged {included} sources into all.xml.gz: "
        f"{channel_count} channels, {programme_count} programmes, "
        f"{human_size(len(uncompressed))} uncompressed / "
        f"{human_size(compressed_size)} gzip"
    )
    return compressed_size


def write_index(results, combined_size=None):
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
        ".combined{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:1rem;margin-top:1.5rem}",
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

    if combined_size is not None:
        html.append(
            "<div class='combined'><strong>Need everything in one file?</strong> "
            "<a href='all.xml.gz'><code>all.xml.gz</code></a> "
            f"({human_size(combined_size)}) merges every region above into a single "
            "XMLTV guide &mdash; use this if your playlist mixes channels from "
            "multiple countries and your player only accepts one EPG URL. "
            "It's a much larger download than any single-country file, so prefer "
            "the individual files above when you can.</div>"
        )

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

    print("\nMerging into a single combined file...")
    combined_size = merge_all()

    write_index(results, combined_size=combined_size)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Fetches XMLTV EPG guide files (gzip-compressed) from epgshare01.online for a
curated set of countries/sources across North America, the Caribbean, South
America, Europe (including Spain), Africa, and Asia, and lays them out as
static files for GitHub Pages.

Per-country files stay small, so a player that only needs one country can
download just that file. For players/apps that only support a single EPG
URL and mix channels from many regions in one playlist, this also builds a
combined `all.xml.gz` merging every successfully-fetched source into one
XMLTV file.
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

BASE_URL = "https://epgshare01.online/epgshare01/epg_ripper_{}.xml.gz"
OUT_DIR = "public"
MAX_WORKERS = 8
RETRIES = 2
TIMEOUT = 60

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


def merge_all():
    """Merge every successfully-fetched per-country file into one combined
    XMLTV file, for players/apps that only support a single EPG URL and mix
    channels from multiple regions in one playlist."""
    root = ET.Element(
        "tv",
        {
            "generator-info-name": "mainstreams-epg",
            "generator-info-url": "https://github.com/mrjuse/mainstreams-epg",
        },
    )
    seen_channel_ids = set()
    channel_count = 0
    programme_count = 0
    included = 0

    for region, codes in REGIONS.items():
        for code in codes:
            src = os.path.join(OUT_DIR, region, f"{code}.xml.gz")
            if not os.path.exists(src):
                continue  # that source failed to fetch this run
            try:
                with gzip.open(src, "rb") as f:
                    src_root = ET.fromstring(f.read())
            except Exception as e:  # noqa: BLE001
                print(f"  WARN: skipping {src} in merge ({e})")
                continue
            included += 1
            for chan in src_root.findall("channel"):
                cid = chan.get("id")
                if cid and cid in seen_channel_ids:
                    continue
                if cid:
                    seen_channel_ids.add(cid)
                root.append(chan)
                channel_count += 1
            for prog in src_root.findall("programme"):
                root.append(prog)
                programme_count += 1

    tree = ET.ElementTree(root)
    buf = io.BytesIO()
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    uncompressed = buf.getvalue()

    out_path = os.path.join(OUT_DIR, "all.xml.gz")
    with gzip.open(out_path, "wb", compresslevel=6) as gz:
        gz.write(uncompressed)

    compressed_size = os.path.getsize(out_path)
    print(
        f"Merged {included} sources into all.xml.gz: "
        f"{channel_count} channels, {programme_count} programmes, "
        f"{human_size(len(uncompressed))} uncompressed / "
        f"{human_size(compressed_size)} gzip"
    )
    return compressed_size


def write_index(results, combined_size=None):
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
        ".combined{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:1rem;margin-top:1.5rem}",
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

    if combined_size is not None:
        html.append(
            "<div class='combined'><strong>Need everything in one file?</strong> "
            "<a href='all.xml.gz'><code>all.xml.gz</code></a> "
            f"({human_size(combined_size)}) merges every region above into a single "
            "XMLTV guide &mdash; use this if your playlist mixes channels from "
            "multiple countries and your player only accepts one EPG URL. "
            "It's a much larger download than any single-country file, so prefer "
            "the individual files above when you can.</div>"
        )

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

    print("\nMerging into a single combined file...")
    combined_size = merge_all()

    write_index(results, combined_size=combined_size)


if __name__ == "__main__":
    main()

                print(f"  OK   {region}/{code} ({name}) - {human_size(size)}")
            else:
                print(f"  FAIL {region}/{code} ({name}) - {err}")

    write_index(results)

    ok_count = sum(1 for r in results if r[4])
    print(f"\nDone: {ok_count}/{len(results)} sources fetched successfully.")


if __name__ == "__main__":
    main()
