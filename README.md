# Mainstreams EPG Generator

This is a standalone automation tool to generate a custom, filtered XMLTV EPG file for the Mainstreams IPTV app.

## How to get this live on GitHub:

1.  **Create a new Repository**: Go to GitHub and create a new public repository named `mainstreams-epg`.
2.  **Upload these files**:
    *   `generate_epg.py`
    *   `.github/workflows/update_epg.yml`
3.  **Configure Channels**:
    *   Edit `generate_epg.py` and update the `TARGET_CHANNELS` list with the `tvg-id` values found in your M3U playlist.
4.  **Enable GitHub Pages**:
    *   Go to **Settings > Pages**.
    *   Under "Build and deployment", set Source to "Deploy from a branch".
    *   Select the `main` branch and `/ (root)` folder, then click **Save**.
5.  **Run the first update**:
    *   Go to the **Actions** tab in your repository.
    *   Select "Update EPG" on the left.
    *   Click "Run workflow".

## Your EPG URL:
Once the action finishes, your EPG will be available at:
`https://<your-username>.github.io/mainstreams-epg/epg.xml`

Enter this URL into the **Settings** screen of the Mainstreams app.
