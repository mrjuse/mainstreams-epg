import requests
import xml.etree.ElementTree as ET
import os

# CONFIGURATION: Map the tvg-id to the EXACT name in your M3U playlist.
# Syntax: "Official.ID": "Name in your App"
# You can search for valid IDs at https://iptv-org.github.io/epg/
CHANNEL_MAP = {
    "HBO.us": "HBO East",
    "CNN.us": "CNN HD",
    "ESPN.us": "ESPN",
    "AMC.us": "AMC",
    "Discovery.us": "Discovery Channel"
}

# Reliable EPG Sources from iptv-org
SOURCES = [
    "https://iptv-org.github.io/epg/guides/us/tvguide.com.xml",
    "https://iptv-org.github.io/epg/guides/us/beevids.com.xml"
]

def generate():
    print("Starting EPG generation...")
    root = ET.Element("tv", {
        "generator-info-name": "Mainstreams EPG Generator",
        "generator-info-url": "https://github.com/mrjuse/mainstreams-epg"
    })

    # 1. Add Channel Metadata
    for tvg_id, display_name in CHANNEL_MAP.items():
        chan_elem = ET.SubElement(root, "channel", id=display_name)
        ET.SubElement(chan_elem, "display-name").text = display_name

    # 2. Fetch and Filter Programmes
    found_channels = set()
    target_ids = list(CHANNEL_MAP.keys())

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
                    chan_id = prog.get("channel")
                    if chan_id in target_ids:
                        # Rename the channel in the program data to match our app name
                        prog.set("channel", CHANNEL_MAP[chan_id])
                        root.append(prog)
                        found_channels.add(chan_id)
                        count += 1
                print(f"Matched {count} programmes for our target channels.")
        except Exception as e:
            print(f"Error fetching {source_url}: {e}")

    # 3. Save Output
    print(f"Summary: Found data for {len(found_channels)}/{len(CHANNEL_MAP)} channels.")
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    tree.write("epg.xml", encoding="utf-8", xml_declaration=True)
    print("File 'epg.xml' generated successfully!")

if __name__ == "__main__":
    generate()
