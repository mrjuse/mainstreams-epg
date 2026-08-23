import requests
import xml.etree.ElementTree as ET
import os

# CONFIGURATION: Add the tvg-ids from your M3U playlist here.
# You can search for valid IDs at https://iptv-org.github.io/epg/
TARGET_CHANNELS = [
    "HBO.us",
    "CNN.us",
    "ESPN.us",
    "AMC.us",
    "Discovery.us"
]

# Reliable EPG Sources from iptv-org
SOURCES = [
    "https://iptv-org.github.io/epg/guides/us/tvguide.com.xml",
    "https://iptv-org.github.io/epg/guides/us/beevids.com.xml"
]

def generate():
    print("Starting EPG generation...")
    root = ET.Element("tv", {
        "generator-info-name": "Mainstreams EPG Generator",
        "generator-info-url": "https://github.com/iptv-org/epg"
    })

    # 1. Add Channel Metadata
    for channel_id in TARGET_CHANNELS:
        chan_elem = ET.SubElement(root, "channel", id=channel_id)
        ET.SubElement(chan_elem, "display-name").text = channel_id

    # 2. Fetch and Filter Programmes
    found_channels = set()
    for source_url in SOURCES:
        print(f"Fetching from: {source_url}")
        try:
            response = requests.get(source_url, timeout=30)
            if response.status_code == 200:
                # Parse XML
                tree = ET.fromstring(response.content)
                programmes = tree.findall("programme")
                print(f"Found {len(programmes)} programmes in source.")

                count = 0
                for prog in programmes:
                    chan = prog.get("channel")
                    if chan in TARGET_CHANNELS:
                        root.append(prog)
                        found_channels.add(chan)
                        count += 1
                print(f"Matched {count} programmes for our target channels.")
        except Exception as e:
            print(f"Error fetching {source_url}: {e}")

    # 3. Save Output
    print(f"Summary: Found data for {len(found_channels)}/{len(TARGET_CHANNELS)} channels.")
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    tree.write("epg.xml", encoding="utf-8", xml_declaration=True)
    print("File 'epg.xml' generated successfully!")

if __name__ == "__main__":
    generate()
