# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Explicit history recovery. No startup networking, credentials or GUI dependencies."""
from __future__ import annotations

import json
import os
import copy
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
import urllib.parse
import urllib.request

try:
    from .journal_stats import Tracker, RELEVANT, parse_ts, _new_vessel
except ImportError:
    from journal_stats import Tracker, RELEVANT, parse_ts, _new_vessel

FORMAT = 'NavigatorDashboardBackup'
VERSION = 1


def owner(path):
    with open(path, encoding='utf-8-sig', errors='replace') as stream:
        for _, line in zip(range(100), stream):
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get('event') == 'Commander' and entry.get('Name'):
                return str(entry['Name'])
            if entry.get('event') == 'LoadGame' and entry.get('Commander'):
                return str(entry['Commander'])
    return None


def paths(folder):
    if not folder or not os.path.isdir(folder):
        return []
    return sorted(Path(folder).glob('Journal*.log'))


def latest_commander(folder):
    for path in reversed(paths(folder)):
        try:
            name = owner(path)
            if name:
                return name
        except OSError:
            pass
    return None


def journal_records(path, commander):
    if not commander or (owner(path) or '').casefold() != commander.casefold():
        return []
    result, last = [], None
    with open(path, encoding='utf-8-sig', errors='replace') as stream:
        for line in stream:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if parse_ts(entry.get('timestamp')) is None:
                continue
            last = entry['timestamp']
            if entry.get('event') in RELEVANT:
                result.append(entry)
    # Preserve the original reader's end-of-file time accounting, even when
    # the final line is not an event that changes vessels.
    if last:
        result.append({'event': 'HistoryBoundary', 'timestamp': last})
    return result


def validate_records(records):
    import math
    if not isinstance(records, list):
        raise ValueError('History records must be a list.')
    for entry in records:
        if (not isinstance(entry, dict) or entry.get('event') not in (*RELEVANT, 'HistoryBoundary')
                or parse_ts(entry.get('timestamp')) is None):
            raise ValueError('Invalid or unsupported journal history record.')
        if 'JumpDist' in entry and (not isinstance(entry['JumpDist'], (float, int))
                or not math.isfinite(entry['JumpDist']) or entry['JumpDist'] < 0):
            raise ValueError('Invalid travel distance in journal history.')
    return records


def event_key(entry):
    # Real jumps are identified independently of enriched/localized fields.
    if entry.get('event') in ('FSDJump', 'CarrierJump', 'Location'):
        return (entry['timestamp'], entry['event'], str(entry.get('StarSystem', '')).casefold())
    return json.dumps(entry, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def unique_records(*groups):
    seen = {}
    for records in groups:
        for entry in records:
            seen[event_key(entry)] = entry  # local records supplied last take precedence
    return sorted(seen.values(), key=lambda e: (e['timestamp'], e['event'] == 'HistoryBoundary'))


def collect(folder, commander, archive=(), cache=None, stop=lambda: False, progress=lambda *a: None):
    """Reuse per-file extracted records, then reconcile once in a worker."""
    cache = cache or {}
    old = cache.get('recovery_files', {}) if cache.get('commander') == commander else {}
    files, local = {}, []
    selected = paths(folder)
    for i, path in enumerate(selected, 1):
        if stop():
            raise InterruptedError('History recovery cancelled.')
        stat = path.stat()
        signature = [stat.st_size, stat.st_mtime_ns]
        previous = old.get(str(path))
        if previous and previous.get('signature') == signature:
            records = previous['records']
        else:
            records = journal_records(path, commander)
        files[str(path)] = {'signature': signature, 'records': records}
        local.extend(records)
        progress(i, len(selected))
    return unique_records(archive, local), {'commander': commander, 'recovery_files': files}


def totals_from_records(records, stop=lambda: False):
    tracker = Tracker()
    end = None
    for i, entry in enumerate(records):
        if i % 1000 == 0 and stop():
            raise InterruptedError('History recovery cancelled.')
        end = parse_ts(entry['timestamp'])
        tracker.feed(entry, end)
    tracker.close(end)
    return tracker.vessels, tracker.state(), end


def scan(folder, cache, commander, archive, visits, stop=lambda: False, progress=lambda *a: None):
    records, out = collect(folder, commander, archive, cache, stop, progress)
    def digest(count):
        return hashlib.sha256(json.dumps(records[:count], sort_keys=True,
            separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest()
    previous = cache.get('recovery_checkpoint', {}) if cache.get('commander') == commander else {}
    count = previous.get('count', 0)
    if count and count <= len(records) and previous.get('digest') == digest(count):
        tracker = Tracker(previous['state'])
        tracker.vessels = copy.deepcopy(previous['totals'])
        tracker._visited = {key: set(v.get('systems', [])) for key, v in tracker.vessels.items()}
        tracker.seg_start = previous['end']
    else:
        tracker, count = Tracker(), 0
    # Leave the final timestamp uncommitted so appended/changed last-file lines
    # can be replayed safely without rescanning a whole career each startup.
    cut = len(records)
    while cut and records[cut-1]['timestamp'] == records[-1]['timestamp']:
        cut -= 1
    checkpoint = None
    for i in range(count, len(records)):
        if i % 1000 == 0 and stop():
            raise InterruptedError('History recovery cancelled.')
        if i == cut:
            checkpoint = {'count': i, 'digest': digest(i), 'state': copy.deepcopy(tracker.state()),
                          'totals': copy.deepcopy(tracker.vessels), 'end': tracker.seg_start}
        entry = records[i]
        tracker.feed(entry, parse_ts(entry['timestamp']))
    totals, state, end = tracker.vessels, tracker.state(), tracker.seg_start
    if checkpoint is not None:
        out['recovery_checkpoint'] = checkpoint
    out['recovered_visits'] = visit_supplement(records, visits, totals)
    return totals, state, end, out


def normalize_visits(rows):
    if not isinstance(rows, list):
        raise ValueError('EDSM logs must be a list.')
    visits = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid EDSM visit.')
        timestamp = str(row.get('timestamp') or row.get('date') or '').replace(' ', 'T')
        if not timestamp.endswith('Z'):
            timestamp += 'Z'
        system = str(row.get('system') or '').strip()
        if not system or parse_ts(timestamp) is None:
            raise ValueError('An EDSM visit is missing its date or system.')
        sid = row.get('shipId')
        item = {'timestamp': timestamp, 'system': system, 'shipId': str(sid) if sid is not None else None}
        visits[(timestamp, system.casefold(), item['shipId'])] = item
    return sorted(visits.values(), key=lambda r: (r['timestamp'], r['system'], r['shipId'] or ''))


def visit_supplement(records, visits, totals):
    """Only assign remote visits when overlapping local jumps verify the ship ID.

    A flight-log visit is not proof of a jump, travel distance or session time.
    Unmapped visits remain saved for later reconciliation without inflating stats.
    """
    jumps, ship_id = {}, None
    for entry in records:
        if entry['event'] in ('LoadGame', 'Loadout', 'ShipyardSwap', 'ShipyardNew') and entry.get('ShipID') is not None:
            ship_id = entry['ShipID']
        if entry['event'] == 'FSDJump' and not entry.get('Taxi'):
            if ship_id is not None:
                jumps[(entry['timestamp'], str(entry.get('StarSystem', '')).casefold())] = f'ship:{ship_id}'
    candidates = {}
    for row in visits:
        key = jumps.get((row['timestamp'], row['system'].casefold()))
        if key and row['shipId'] is not None:
            candidates.setdefault(row['shipId'], set()).add(key)
    mapped = {sid: next(iter(keys)) for sid, keys in candidates.items() if len(keys) == 1}
    result = {}
    for row in visits:
        key = mapped.get(row['shipId'])
        if key and key in totals:
            vessel = result.setdefault(key, _new_vessel('ship'))
            vessel['type'] = totals[key]['type']
            vessel['name'] = totals[key]['name']
            vessel['systems'].append(row['system'].casefold())
    for vessel in result.values():
        vessel['systems'] = sorted(set(vessel['systems']))
    return result


def read_backup(path):
    with open(path, encoding='utf-8-sig') as stream:
        data = json.load(stream)
    if not isinstance(data, dict) or data.get('format') != FORMAT or data.get('version') != VERSION:
        raise ValueError('This is not a supported Dashboard backup.')
    if not isinstance(data.get('commander'), str) or not data['commander'].strip():
        raise ValueError('The backup has no commander identity.')
    validate_records(data.get('events'))
    if not isinstance(data.get('created'), str):
        raise ValueError('The backup has no creation date.')
    created = datetime.fromisoformat(data['created'])
    if created.tzinfo is None:
        raise ValueError('Backup creation date must include its time zone.')
    data['visits'] = normalize_visits(data.get('visits', []))
    # Full snapshots are intentionally local-only, never sent to EDSM.
    for key in ('odometer', 'stopwatch'):
        state = data.get(key, {})
        if not isinstance(state, dict):
            raise ValueError('Invalid saved Dashboard state.')
        for field, value in state.items():
            if field in ('trip_systems', 'laps'):
                if not isinstance(value, list):
                    raise ValueError('Invalid saved Dashboard list.')
            elif isinstance(value, (dict, list)):
                raise ValueError('Invalid saved Dashboard value.')
    return data


def atomic_json(path, data):
    import tempfile
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.dashboard-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def download_edsm(commander, api_key, start, finish, cancel, progress=lambda *a: None, opener=None):
    """Explicit date-bounded import. Weekly windows; <=1 request per 10.1 seconds."""
    opener = opener or urllib.request.urlopen
    begin = datetime.strptime(start, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    end = datetime.strptime(finish, '%Y-%m-%d').replace(tzinfo=timezone.utc) + timedelta(days=1)
    if begin >= end or end > datetime.now(timezone.utc) + timedelta(days=1):
        raise ValueError('Choose a valid past date range (YYYY-MM-DD).')
    if not commander.strip() or not api_key.strip():
        raise ValueError('Commander name and EDSM API key are required.')
    cursor, rows, windows = begin, [], 0
    total = (int((end - begin).total_seconds()) + 604799) // 604800
    while cursor < end:
        if cancel.is_set():
            return normalize_visits(rows), True
        if windows and cancel.wait(10.1):
            return normalize_visits(rows), True
        upper = min(cursor + timedelta(days=7), end)
        params = {'commanderName': commander, 'apiKey': api_key, 'showId': 1,
                  'startDateTime': cursor.strftime('%Y-%m-%d %H:%M:%S'),
                  'endDateTime': (upper - timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S')}
        request = urllib.request.Request('https://www.edsm.net/api-logs-v1/get-logs',
            data=urllib.parse.urlencode(params).encode('utf-8'),
            headers={'User-Agent': 'EDMC-ShipComputer/0.6.16', 'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            with opener(request, timeout=30) as response:
                data = json.load(response)
        except Exception:
            # Never interpolate the exception: it may contain request credentials.
            raise ValueError('EDSM could not be reached. No automatic retries were made.') from None
        if not isinstance(data, dict) or data.get('msgnum') != 100 or not isinstance(data.get('logs'), list):
            raise ValueError('EDSM rejected the request. Check the key, commander and service availability.')
        batch = normalize_visits(data['logs'])
        rows.extend(row for row in batch if begin.timestamp() <= parse_ts(row['timestamp']) < end.timestamp())
        windows += 1
        progress(windows, total)
        cursor = upper
    return normalize_visits(rows), False
