# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Playlist identities and migration for user-owned internet stations; no networking."""
import os
import re

CUSTOM = 'Custom Streams'


def playlist_name(path):
    name = os.path.splitext(os.path.basename(path))[0].strip()
    # Browser duplicate-download suffixes should not create duplicate groups.
    return re.sub(r'\s*\(\d+\)$', '', name).strip() or 'Imported Playlist'


def group_name(item):
    return str(item.get('playlist') or CUSTOM).strip() or CUSTOM


def normalize(streams):
    result, seen, names = [], set(), {}
    for item in streams:
        if not isinstance(item, dict) or not str(item.get('url') or '').lower().startswith(('http://', 'https://')):
            continue
        group = group_name(item)
        group = names.setdefault(group.casefold(), group)
        key = (group.casefold(), item['url'])
        if key not in seen:
            result.append(dict(item, playlist=group))
            seen.add(key)
    return result


def playlists(streams):
    result, seen = [], set()
    for item in streams:
        if item.get('url'):
            group = group_name(item)
            if group.casefold() not in seen:
                result.append(group)
                seen.add(group.casefold())
    return result


def import_playlist(library, path, stations):
    group = playlist_name(path)
    existing = playlists(library['streams'])
    group = next((name for name in existing if name.casefold() == group.casefold()), group)
    streams = normalize(library['streams'])
    # A legacy flattened station can be placed back into its original playlist
    # when that exact URL is re-imported. Never guess groups from station names.
    known = {i['url'] for i in streams if group_name(i).casefold() == group.casefold()}
    added = 0
    for station in stations:
        if station['url'] in known:
            continue
        legacy = next((i for i in streams if group_name(i) == CUSTOM and i['url'] == station['url']), None)
        if legacy is not None and group != CUSTOM:
            legacy['playlist'] = group
        else:
            streams.append(dict(station, playlist=group))
        known.add(station['url'])
        added += 1
    library['streams'] = normalize(streams)
    return group, added
