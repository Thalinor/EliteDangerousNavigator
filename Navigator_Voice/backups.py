# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Portable, typed JSON backups; no runtime files are included in releases."""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import json
import re
from pathlib import Path
import shutil
from . import __version__
from .commands import validate

FORMAT = 'Voice Navigator Backup'
LABELS = {'settings': 'Settings', 'macros': 'Voice_Macros',
          'assistant': 'Assistant_Settings', 'everything': 'Everything'}
LIMIT = 2_000_000
LOCAL = {'backup_directory'}
SEPARATE = {'macros', 'assistant_settings'} | LOCAL


def backup_folder(plugin, settings):
    override = settings.get('backup_directory', '')
    return Path(override).expanduser() if override else Path(plugin) / 'Backups'


def write_backup(folder, kind, settings):
    if kind not in LABELS:
        raise ValueError('Choose plugin settings, voice macros, or everything.')
    settings = validate(copy.deepcopy(settings))
    if kind == 'settings':
        data = {key: value for key, value in settings.items() if key not in SEPARATE}
    elif kind == 'macros':
        data = {'macros': settings['macros']}
    elif kind == 'assistant':
        data = {'assistant_settings': copy.deepcopy(settings.get('assistant_settings', {}))}
    else:
        data = {key: value for key, value in settings.items() if key not in LOCAL}
    now = datetime.now(timezone.utc)
    document = dict(format=FORMAT, version=1, plugin_version=__version__,
                    created_utc=now.isoformat(), kind=kind, data=data)
    text = json.dumps(document, ensure_ascii=False, indent=2) + '\n'
    if len(text.encode('utf-8')) > LIMIT:
        raise ValueError('Backup is too large (maximum 2 MB).')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    name = 'Voice_Navigator_%s_%s.json' % (LABELS[kind], now.strftime('%Y%m%d_%H%M%S_%fZ'))
    path = folder / name
    # Exclusive creation protects any backup already at the same path.
    with path.open('x', encoding='utf-8') as stream:
        stream.write(text)
    return path


def restore_candidate(path, current):
    path = Path(path)
    if path.stat().st_size > LIMIT:
        raise ValueError('Backup is too large (maximum 2 MB).')
    document = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(document, dict):
        raise ValueError('This is not a Voice Navigator backup.')
    if document.get('format') == FORMAT:
        if document.get('version') != 1:
            raise ValueError('This backup format version is not supported.')
        kind, data = document.get('kind'), document.get('data')
        if kind not in LABELS or not isinstance(data, dict):
            raise ValueError('This backup has invalid contents.')
    elif document.get('schema') == 1:
        kind, data = 'everything', document  # Older Export Settings files.
    else:
        raise ValueError('This is not a Voice Navigator backup.')
    candidate = copy.deepcopy(current)
    if kind == 'macros':
        if set(data) != {'macros'}:
            raise ValueError('A voice macro backup must contain only macros.')
        candidate['macros'] = copy.deepcopy(data['macros'])
    elif kind == 'assistant':
        if set(data) != {'assistant_settings'}:
            raise ValueError('An Assistant backup must contain only Assistant settings')
        candidate['assistant_settings'] = copy.deepcopy(data['assistant_settings'])
    elif kind == 'settings':
        if any(key in data for key in SEPARATE) or data.get('schema') != 1:
            raise ValueError('A plugin settings backup cannot replace macros or Assistant settings.')
        candidate.update(copy.deepcopy(data))
    else:
        candidate = copy.deepcopy(data)
        candidate.pop('backup_directory', None)
        if 'backup_directory' in current:
            candidate['backup_directory'] = current['backup_directory']
    return kind, validate(candidate)


def move_backups(source, target):
    """Move this plugin's backups without touching unrelated folder contents."""
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target:
        return []
    if source in target.parents or target in source.parents:
        raise ValueError('Choose a separate folder, outside the current backup folder.')
    pattern = re.compile(r'Voice_Navigator_(?:Settings|Voice_Macros|Assistant_Settings|Everything)_\d{8}_\d{6}_\d{6}Z\.json')
    entries = [entry for entry in source.iterdir()
               if entry.is_file() and pattern.fullmatch(entry.name)] if source.exists() else []
    target.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        if (target / entry.name).exists():
            raise ValueError('The destination already contains ' + entry.name + '. Nothing was moved.')
    moved = []
    try:
        for entry in entries:
            shutil.move(str(entry), str(target / entry.name))
            moved.append(entry.name)
    except Exception:
        for name in reversed(moved):
            shutil.move(str(target / name), str(source / name))
        raise
    return moved
