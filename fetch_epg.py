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
        "MX": "Mexico",
        "US2": "United States",
        "US_SPORTS": "United States (Sports)",
        "CR": "Costa Rica",
        "PA": "Panama",
        "SV": "El Salvador",
    },
    "caribbean": {
        "BB": "Barbados",
        "DO": "Dominican Republic",
        "JM": "Jamaica",
    },
    "south_america": {
        "AR": "Argentina",
        "BR": "Brazil",
        "BR2": "Brazil (alt. source)",
        "CL": "Chile",
        "CO": "Colombia",
        "EC": "Ecuador",
        "PE": "Peru",
        "UY": "Uruguay",
    },
    "europe": {
        "AL": "Albania",
        "AT": "Austria",
        "BA": "Bosnia and Herzegovina",
        "BE2": "Belgium",
        "BG": "Bulgaria",
        "CH": "Switzerland",
        "CY": "Cyprus",
        "CZ": "Czechia",
        "DE": "Germany",
        "DK": "Denmark",
        "ES": "Spain",
        "FI": "Finland",
        "FR": "France",
        "GR": "Greece",
        "HR": "Croatia",
        "HU": "Hungary",
        "IE": "Ireland",
        "IT": "Italy",
        "LT": "Lithuania",
        "LU": "Luxembourg",
        "LV": "Latvia",
        "MT": "Malta",
        "NL": "Netherlands",
        "NO": "Norway",
        "PL": "Poland",
        "PT": "Portugal",
        "RO": "Romania",
        "RO2": "Romania (alt. source)",
        "RS": "Serbia",
        "SE": "Sweden",
        "SK": "Slovakia",
        "TR": "Turkey",
        "TR3": "Turkey (alt. source)",
        "UK": "United Kingdom",
        "viva-russia.ru": "Russia",
    },
    "africa": {
        "EG": "Egypt",
        "KE": "Kenya",
        "NG": "Nigeria",
        "ZA": "South Africa",
    },
    "asia": {
        "AE": "United Arab Emirates",
        "ASIANTELEVISION": "Asian Television (multi-country)",
        "HK": "Hong Kong",
        "ID": "Indonesia",
        "IL": "Israel",
        "IN": "India",
        "IN2": "India (alt. source 2)",
        "IN4": "India (alt. source 4)",
        "JP": "Japan",
        "JP2": "Japan (alt. source)",
        "KR": "South Korea",
        "MN": "Mongolia",
        "MY": "Malaysia",
        "PH": "Philippines",
        "PH2": "Philippines (alt. source)",
        "PK": "Pakistan",
        "SA": "Saudi Arabia",
        "SA2": "Saudi Arabia (alt. source)",
        "SG": "Singapore",
        "TH": "Thailand",
        "VN": "Vietnam",
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
            if ok:
                print(f"  OK   {region}/{code} ({name}) - {human_size(size)}")
            else:
                print(f"  FAIL {region}/{code} ({name}) - {err}")

    write_index(results)

    ok_count = sum(1 for r in results if r[4])
    print(f"\nDone: {ok_count}/{len(results)} sources fetched successfully.")


if __name__ == "__main__":
    main()
