# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Ship Radio: station sources. No Tk, no audio, safe to import anywhere.

Network calls are made from worker threads by load.py. Everything here returns
plain dicts/lists so it can be cached as JSON and tested without EDMC.
"""
from __future__ import annotations

import html
import json
import os
import random
import re
import urllib.parse
import urllib.request

USER_AGENT = "EDMC-ShipRadio"
TIMEOUT = 12
MAX_BYTES = 4 * 1024 * 1024

GALNET_URL = ("https://cms.zaonce.net/en-GB/jsonapi/node/galnet_article"
              "?sort=-published_at&page%5Blimit%5D={limit}")
DW3_API = "https://radio.distantworlds3.space/api"
DW3_CREDIT = "Distant Radio - the official radio of Distant Worlds 3 (distantworlds3.space/radio)"
# Used when the station list cannot be fetched. Public stream links published
# by Distant Radio; shared with the station's permission, credited in README.
DW3_FALLBACK = [
    {"id": "distant_radio", "name": "Distant Radio",
     "url": "https://distantradio.space/listen/distant_radio/distantradio.mp3",
     "saver": "https://distantradio.space/listen/distant_radio/drdatasaver.mp3"},
    {"id": "pulsarfm", "name": "PulsarFM",
     "url": "https://distantradio.space/listen/pulsarfm/pulsarfm.mp3",
     "saver": "https://distantradio.space/listen/pulsarfm/pfmdatasaver.mp3"},
    {"id": "hotline", "name": "Distant Radio Hotline",
     "url": "https://distantradio.space/listen/hotline/hotline.mp3",
     "saver": "https://distantradio.space/listen/hotline/hotlinedatasaver.mp3"},
]
AUDIO_EXTENSIONS = (".mp3", ".wma", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".mp4")


# --------------------------------------------------------------------------- privacy
def redact(url: str | None) -> str:
    """A URL safe for logs and the screen: scheme and host only.

    Listener keys usually live in the path or query, so both are dropped."""
    if not url:
        return ""
    try:
        parts = urllib.parse.urlsplit(str(url))
    except ValueError:
        return "(stream)"
    if not parts.scheme or not parts.hostname:
        return "(stream)"
    return f"{parts.scheme}://{parts.hostname}/…"


# --------------------------------------------------------------------------- network
def _get_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Response too large")
    return json.loads(data.decode("utf-8"))


def html_to_text(value: str) -> str:
    """Galnet bodies are lightly formatted HTML or plain text with CRLFs."""
    text = re.sub(r"(?i)<br\s*/?>|</p>", "\n", value or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def fetch_galnet(limit: int = 20) -> list[dict]:
    """Newest first: [{id, title, date, text}]."""
    data = _get_json(GALNET_URL.format(limit=int(limit)))
    articles = []
    for item in data.get("data", []) if isinstance(data, dict) else []:
        attributes = item.get("attributes", {}) if isinstance(item, dict) else {}
        title = str(attributes.get("title") or "").strip()
        body = attributes.get("body") or {}
        text = html_to_text(body.get("value", "") if isinstance(body, dict) else str(body))
        if not title or not text:
            continue
        articles.append({
            "id": str(attributes.get("field_galnet_guid") or item.get("id") or title),
            "title": title,
            "date": str(attributes.get("field_galnet_date") or "").strip(),
            "text": text,
        })
    return articles


def galnet_speech(article: dict) -> str:
    date = article.get("date", "")
    spoken_date = date.title() if date else ""
    head = f"{article.get('title', '')}." + (f" {spoken_date}." if spoken_date else "")
    return head + "\n" + article.get("text", "")


def fetch_dw3_stations() -> list[dict]:
    data = _get_json(DW3_API + "/stations")
    stations = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or not item.get("is_public", True):
            continue
        mounts = [m for m in item.get("mounts") or [] if isinstance(m, dict) and m.get("url")]
        main = next((m for m in mounts if m.get("is_default")), mounts[0] if mounts else None)
        saver = next((m for m in mounts if m is not main and (m.get("bitrate") or 999) < (main or {}).get("bitrate", 0)), None)
        url = (main or {}).get("url") or item.get("listen_url")
        if not url or not item.get("shortcode"):
            continue
        stations.append({"id": str(item["shortcode"]), "name": str(item.get("name") or item["shortcode"]),
                         "url": url, "saver": (saver or {}).get("url") or url})
    return stations


def fetch_dw3_now_playing(station_id: str) -> str:
    data = _get_json(f"{DW3_API}/nowplaying/{urllib.parse.quote(station_id)}")
    if not isinstance(data, dict):
        return ""
    song = (data.get("now_playing") or {}).get("song") or {}
    text = str(song.get("text") or " - ".join(p for p in (song.get("artist"), song.get("title")) if p) or "")
    live = data.get("live") or {}
    if live.get("is_live") and live.get("streamer_name"):
        return f"LIVE: {live['streamer_name']}" + (f"  |  {text}" if text else "")
    return text


# --------------------------------------------------------------------------- playlists
class PlaylistError(ValueError):
    pass


def parse_playlist(text: str, base_name: str = "Stream") -> list[dict]:
    """Internet stations from .m3u / .m3u8 / .pls text: [{name, url}]."""
    text = (text or "").lstrip("﻿")
    if "#EXT-X-" in text:
        raise PlaylistError("This is an HLS (segmented) playlist, which (N) Radio does not play. "
                            "Use the station's .m3u or .pls Icecast/Shoutcast link instead.")
    stations: list[dict] = []
    if re.search(r"(?im)^\s*\[playlist\]", text):
        files, titles = {}, {}
        for line in text.splitlines():
            match = re.match(r"\s*(File|Title)(\d+)\s*=\s*(.*)$", line, re.I)
            if match:
                (files if match.group(1).lower() == "file" else titles)[int(match.group(2))] = match.group(3).strip()
        for number in sorted(files):
            stations.append({"name": titles.get(number) or "", "url": files[number]})
    else:
        pending_name = ""
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.upper().startswith("#EXTINF"):
                pending_name = line.split(",", 1)[1].strip() if "," in line else ""
            elif line.startswith("#"):
                continue
            else:
                stations.append({"name": pending_name, "url": line})
                pending_name = ""
    result = []
    for number, station in enumerate(stations, 1):
        url = station["url"]
        if not re.match(r"(?i)^https?://", url):
            continue                       # local paths inside internet playlists are skipped
        name = station["name"] or (base_name if len(stations) == 1 else f"{base_name} {number}")
        result.append({"name": name[:80], "url": url})
    if not result:
        raise PlaylistError("No internet stream links (http:// or https://) were found in that playlist.")
    return result


def read_playlist_file(path: str) -> list[dict]:
    with open(path, "rb") as stream:
        raw = stream.read(256 * 1024)
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    base = os.path.splitext(os.path.basename(path))[0] or "Stream"
    return parse_playlist(text, base)


# --------------------------------------------------------------------------- music folders
def _natural_key(name: str):
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", name)]


def scan_folder(path: str, shuffle: bool = False, limit: int | None = None) -> list[str]:
    """Audio files in this folder and its subfolders, in natural order (or shuffled)."""
    found: list[str] = []
    if not os.path.isdir(path):
        raise FileNotFoundError('Music folder unavailable')
    errors = []
    def failed(error):
        errors.append(error)  # skip unreadable subfolders, retain playable files
    for root, dirs, files in os.walk(path, onerror=failed):
        dirs.sort(key=_natural_key)
        for name in sorted(files, key=_natural_key):
            if name.lower().endswith(AUDIO_EXTENSIONS):
                found.append(os.path.join(root, name))
                if limit is not None and len(found) >= limit:
                    break
        if limit is not None and len(found) >= limit:
            break
    if shuffle:
        random.shuffle(found)
    if errors and not found:
        raise errors[0]
    return found


def track_title(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0].replace("_", " ")
