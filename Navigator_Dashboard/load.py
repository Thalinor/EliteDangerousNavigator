# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Ship Computer - odometer, stopwatch and per-ship journal stats for EDMC.

Part of the Navigator plugin suite by Commander Thalinor.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import tempfile
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox
from tkinter import ttk
from typing import Any

import myNotebook as nb
from config import appname, config

try:
    from .journal_stats import Tracker, merge, parse_ts, scan_all, system_key, FOOT_KEY, recover_trip_systems, recover_trip_travel
    from . import history
    from .recovery_ui import Recovery
    from .cargo import CargoManifest
    from .synthesis import SynthesisInventory, GROUPS, RECIPES
except ImportError:                      # loaded as a plain (non-package) plugin
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from journal_stats import Tracker, merge, parse_ts, scan_all, system_key, FOOT_KEY, recover_trip_systems, recover_trip_travel
    import history
    from recovery_ui import Recovery
    from cargo import CargoManifest
    from synthesis import SynthesisInventory, GROUPS, RECIPES

TITLE = "(N) Dashboard"
HEADER_TITLE = "Dashboard"
VERSION = "0.6.19"
PREFIX = "ShipComputer_"
PLUGIN_NAME = os.path.basename(os.path.dirname(__file__))
logger = logging.getLogger(f"{appname}.{PLUGIN_NAME}")
TABS = ("trip", "odometer", "cargo", "synthesis", "stopwatch")
TAB_LABELS = {"trip": "Trip", "odometer": "Odometer", "cargo": "Cargo", "synthesis": "Synthesis", "stopwatch": "Stopwatch"}
OLD_TABS = {"Odometer": "trip", "Ship": "odometer", "Stats": "odometer", "Stopwatch": "stopwatch"}
BUTTON_SCALE = 0.88                     # button text (0.8 + 10%): all panel buttons match
# ~20% shorter buttons. The hand cursor makes EDMC's theme draw them in Highlighted Text (clickable).
BUTTON = {"pady": 0, "borderwidth": 1, "highlightthickness": 0, "cursor": "hand2"}
TAB_PAD_X = 4                         # one extra space between neighbouring tabs
BUTTON_WIDTH = 7                        # the same width for every button
LAPS_SHOWN = 30                         # newest laps kept in the scrolling list
LAPS_KEPT = 200
COLLAPSE_UP, COLLAPSE_DOWN = "🔼", "🔽"   # standard EDMC plugin collapse button

_RECENT_SHIPS = {
    "explorer_nx": "Caspian Explorer", "python_nx": "Python Mk II", "mandalay": "Mandalay",
    "corsair": "Corsair", "cobramkv": "Cobra Mk V", "panthermkii": "Panther Clipper Mk II",
    "type8": "Type-8 Transporter", "smallcombat01_nx": "Kestrel Mk II",
    "mediumtransport01": "Lynx Highliner", "lakonminer": "Type-11 Prospector",
    "typex_2": "Alliance Crusader",
}

# --------------------------------------------------------------------------- state
_ui: dict[str, Any] = {}
_root: tk.Misc | None = None
_stopped = True
_tick_id = None
_theme_pending = None
_theme_bindings: list[tuple[str, str]] = []
_clock_font = None
_button_font = None
_button_font_key = None
_clock_font_key = None
_tab_font = None
_tab_font_key = None
_cargo = CargoManifest()
_synthesis = SynthesisInventory()
_trip_last: float | None = None         # for Trip Time
_prefs: dict[str, Any] = {}

_odo: dict[str, Any] = {}             # trip/total, saved
_session: list[tuple[float, float]] = []   # (time, ly) of this EDMC session's jumps, for rates
_watch: dict[str, Any] = {}           # stopwatch, saved

_scan_queue: queue.Queue = queue.Queue()
_scan_thread: threading.Thread | None = None
_scan_stop = False
_scanning = False
_scan_progress = (0, 0)
_totals: dict[str, dict] = {}         # from the journal files
_live: Tracker | None = None          # events after the scan
_scan_end: float | None = None
_active_commander = None
_rescan_commander = False
_recovery = None
_recovered_visits = {}
_buffered: list[tuple[dict, float | None]] = []


# --------------------------------------------------------------------------- settings + files
def _get_bool(key: str, default: bool) -> bool:
    try:
        value = config.get_bool(PREFIX + key, default=default)
    except TypeError:
        value = config.get_bool(PREFIX + key)
    return default if value is None else bool(value)


def _get_str(key: str, default: str) -> str:
    try:
        value = config.get_str(PREFIX + key, default=default)
    except TypeError:
        value = config.get_str(PREFIX + key)
    return value or default


def _data_dir() -> str:
    try:
        base = os.fspath(getattr(config, "app_dir_path", None) or config.app_dir)
    except Exception:
        base = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "EDMarketConnector")
    folder = os.path.join(base, "Ship_Computer")
    os.makedirs(folder, exist_ok=True)
    return folder


def _load(name: str, default: dict) -> dict:
    try:
        with open(os.path.join(_data_dir(), name), encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else dict(default)
    except (OSError, ValueError):
        return dict(default)


def _save(name: str, data: dict) -> None:
    folder = _data_dir()
    path = os.path.join(folder, name)
    try:
        fd, temporary = tempfile.mkstemp(prefix="ship_computer_", suffix=".tmp", dir=folder)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
        for attempt in range(5):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:              # another program has the file open
                time.sleep(0.1 * (attempt + 1))
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
        os.unlink(temporary)
    except OSError:
        logger.exception("Could not save %s", name)


def _journal_dir() -> str | None:
    try:
        folder = config.get_str("journaldir") or getattr(config, "default_journal_dir", "")
    except Exception:
        folder = ""
    if folder and os.path.isdir(os.fspath(folder)):
        return os.fspath(folder)
    fallback = os.path.join(os.environ.get("USERPROFILE") or os.path.expanduser("~"),
                            "Saved Games", "Frontier Developments", "Elite Dangerous")
    return fallback if os.path.isdir(fallback) else None


# --------------------------------------------------------------------------- formatting
def _ship_model(ship_type: str) -> str:
    key = (ship_type or "").lower()
    try:
        from edmc_data import ship_name_map
        if key in ship_name_map:
            return ship_name_map[key]
    except Exception:
        pass
    return _RECENT_SHIPS.get(key) or key.replace("_", " ").title() or "Unknown ship"


def _ly(value: float) -> str:
    return f"{value:,.1f} Ly" if value < 100 else f"{value:,.0f} Ly"


def _jumps(count: int) -> str:
    return f"{count:,} Jump" + ("" if count == 1 else "s")


def _clock(seconds: float, tenths: bool = True) -> str:
    seconds = max(0.0, seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if tenths:
        return f"{int(hours):02d}:{int(minutes):02d}:{secs:04.1f}"
    return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d}"


def _duration(seconds: float) -> str:
    hours, rest = divmod(int(max(0, seconds)), 3600)
    return f"{hours:,} h {rest // 60:02d} m"


# --------------------------------------------------------------------------- odometer
def _odo_defaults() -> dict:
    return {"trip_ly": 0.0, "trip_jumps": 0, "trip_seconds": 0.0, "total_ly": 0.0, "total_jumps": 0,
            "last_ts": 0.0, "undock_ts": 0.0, "trip_systems": [], "trip_systems_ready": False, "trip_reset": 0.0, "trip_landings": 0, "landing_last_ts": 0.0, "landing_taxi": False,
            # Travel time: jump-to-jump gaps only; a gap over STOP_FACTOR x the standard is a stop.
            "trip_travel_seconds": 0.0, "trip_travel_jumps": 0, "trip_travel_ly": 0.0, "trip_travel_ready": False}


STOP_FACTOR = 3                       # same rule as Neutron Highway's ETA idle limit
STANDARD_JUMP = 80                    # seconds, arrival to arrival, normal star (user default 1:20)
STANDARD_NEUTRON = 120                # seconds with a neutron/white-dwarf boost (Neutron Highway default)


def _get_seconds(key: str, default: int) -> int:
    try:
        value = int(_get_str(key, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(20, min(600, value))


def _stop_limit(boost) -> float:
    """Seconds between two jumps above which the gap counts as a stop, not travel."""
    stellar = isinstance(boost, (int, float)) and not isinstance(boost, bool) and boost >= 4
    return STOP_FACTOR * (_get_seconds("StandardNeutronSeconds", STANDARD_NEUTRON) if stellar
                          else _get_seconds("StandardJumpSeconds", STANDARD_JUMP))


def _rates() -> tuple[float | None, float | None, bool]:
    """Trip averages (jumps/hr, Ly/hr, estimated).

    By default it divides by time actually spent jumping, so stops neither drag the rate down
    nor make it tick while you fly around a star. "Include stop time" (for trading and mining)
    divides by the whole Trip Time, so time spent docking and between stations shows.
    """
    if _get_bool("IncludeStopTime", False):
        hours = float(_odo.get("trip_seconds") or 0) / 3600
        if not _odo.get("trip_jumps") or hours < 1 / 60:
            return None, None, False
        return _odo["trip_jumps"] / hours, _odo["trip_ly"] / hours, False
    jumps = int(_odo.get("trip_travel_jumps") or 0)
    hours = float(_odo.get("trip_travel_seconds") or 0) / 3600
    if jumps >= 2 and hours > 0:
        return jumps / hours, float(_odo.get("trip_travel_ly") or 0) / hours, False
    if not _odo.get("trip_jumps"):
        return None, None, False
    # Until two jump-to-jump gaps are measured: your standard pace x this trip's average jump.
    per_hour = 3600 / _get_seconds("StandardJumpSeconds", STANDARD_JUMP)
    return per_hour, per_hour * _odo["trip_ly"] / _odo["trip_jumps"], True


def _in_game() -> bool:
    return _live is not None and _live.in_game


def _count_trip_time() -> None:
    """Trip Time runs only while you are logged into the game."""
    global _trip_last
    now = time.time()
    if _trip_last is not None and _in_game():
        _odo["trip_seconds"] = float(_odo.get("trip_seconds") or 0) + (now - _trip_last)
    _trip_last = now


def _count_jump(distance: float, when: float, destination: str | None = None, boost=None) -> None:
    """A ship FSD jump (not carrier, not taxi). Each jump is counted once, even across restarts."""
    previous = float(_odo.get("last_ts") or 0)
    if when <= previous:
        return
    # Travel time: the gap since the previous jump of this trip, unless it was a stop.
    if previous and previous >= float(_odo.get("trip_reset") or 0) and when - previous <= _stop_limit(boost):
        _odo["trip_travel_seconds"] = float(_odo.get("trip_travel_seconds") or 0) + (when - previous)
        _odo["trip_travel_jumps"] = int(_odo.get("trip_travel_jumps") or 0) + 1
        _odo["trip_travel_ly"] = float(_odo.get("trip_travel_ly") or 0) + distance
    _odo["last_ts"] = when
    _odo["trip_ly"] += distance
    _odo["trip_jumps"] += 1
    if destination and destination not in _odo["trip_systems"]:
        _odo["trip_systems"].append(destination)
    _odo["total_ly"] += distance
    _odo["total_jumps"] += 1
    _session.append((when, distance))
    _save("odometer.json", _odo)
    if _watch.get("running"):
        _watch["lap_jumps"] = int(_watch.get("lap_jumps", 0)) + 1
        _watch["lap_ly"] = float(_watch.get("lap_ly", 0.0)) + distance
        _save("stopwatch.json", _watch)


def _count_landing(entry, state, when):
    event = entry.get('event')
    if event in ('LoadGame', 'Embark', 'Disembark'):
        _odo['landing_taxi'] = bool(entry.get('Taxi', False))
    if event not in ('Docked', 'Touchdown') or not when:
        return
    if when <= max(float(_odo.get('landing_last_ts') or 0), float(_odo.get('trip_reset') or 0)):
        return
    _odo['landing_last_ts'] = when
    ship_type = str(state.get('ShipType') or entry.get('Ship') or '').casefold()
    taxi = bool(entry.get('Taxi') or _odo.get('landing_taxi') or getattr(_live, 'taxi', False))
    if taxi or ship_type in ('testbuggy', 'combat_multicrew_srv_01', 'srv', 'fighter'):
        return
    if event == 'Touchdown' and entry.get('PlayerControlled') is not True:
        return
    _odo['trip_landings'] = int(_odo.get('trip_landings') or 0) + 1
    _save('odometer.json', _odo)


def _clear_trip() -> None:
    _count_trip_time()
    _odo.pop("trip_undo", None)
    _odo["trip_landings"] = 0
    _odo["trip_ly"], _odo["trip_jumps"], _odo["trip_seconds"] = 0.0, 0, 0.0
    _odo["trip_travel_seconds"], _odo["trip_travel_jumps"], _odo["trip_travel_ly"] = 0.0, 0, 0.0
    _odo["trip_travel_ready"] = True
    _odo["trip_systems"] = []
    _odo["trip_systems_ready"] = True
    _odo["trip_reset"] = time.time()
    _session.clear()
    _save("odometer.json", _odo)
    _refresh()


def _reset_trip() -> None:
    if messagebox.askyesno("Reset Trip", "Reset the trip time, jumps, systems, distance and landings to zero?",
                           parent=_ui.get("frame")):
        _clear_trip()


# --------------------------------------------------------------------------- stopwatch
def _watch_defaults() -> dict:
    return {"running": False, "start": None, "elapsed": 0.0, "lap_base": 0.0,
            "lap_jumps": 0, "lap_ly": 0.0, "laps": []}


def _watch_elapsed(now: float | None = None) -> float:
    elapsed = float(_watch.get("elapsed", 0.0))
    if _watch.get("running") and _watch.get("start"):
        elapsed += (now or time.time()) - float(_watch["start"])
    return elapsed


def _start_stop() -> None:
    now = time.time()
    if _watch.get("running"):
        _watch["elapsed"] = _watch_elapsed(now)
        _watch["running"], _watch["start"] = False, None
    else:
        _watch["running"], _watch["start"] = True, now
    _save("stopwatch.json", _watch)
    _refresh()


def _lap() -> None:
    if not _watch.get("running"):
        return
    total = _watch_elapsed()
    laps = _watch.setdefault("laps", [])
    laps.append({"n": len(laps) + 1, "lap": total - float(_watch.get("lap_base", 0.0)), "total": total,
                 "jumps": int(_watch.get("lap_jumps", 0)), "ly": float(_watch.get("lap_ly", 0.0))})
    del laps[:-LAPS_KEPT]
    _watch["lap_base"], _watch["lap_jumps"], _watch["lap_ly"] = total, 0, 0.0
    _save("stopwatch.json", _watch)
    _refresh()
    try:
        _ui["laps_view"].yview_moveto(0)
    except (tk.TclError, KeyError):
        pass


def _reset_watch() -> None:
    if _watch.get("laps") or _watch_elapsed() > 0:
        if not messagebox.askyesno("Reset Stopwatch", "Reset the stopwatch and clear all laps?",
                                   parent=_ui.get("frame")):
            return
    _watch.clear()
    _watch.update(_watch_defaults())
    _save("stopwatch.json", _watch)
    _refresh()


# --------------------------------------------------------------------------- stats
def _start_scan(fresh: bool = False) -> None:
    global _scan_thread, _scanning, _scan_stop, _scan_progress, _live
    folder = _journal_dir()
    scan_commander = (_active_commander or history.latest_commander(folder)
                      or (_recovery.commander() if _recovery else None))
    recovery_record = _recovery.record(scan_commander) if _recovery else {}
    has_recovery = bool(recovery_record.get('events') or recovery_record.get('visits'))
    if folder is None and not has_recovery:
        logger.warning("Ship Computer: journal folder not found; Stats unavailable")
        return
    if _scanning:
        return
    _scanning, _scan_stop, _scan_progress = True, False, (0, 0)
    cache = {} if fresh else _load("stats_cache.json", {})
    # Continue buffering new events during a rebuild instead of discarding
    # the events that arrive after the worker's journal snapshot.
    _live = None
    _buffered.clear()
    trip_snapshot = (int(_odo.get("trip_jumps") or 0), float(_odo.get("last_ts") or 0),
                     _odo.get("trip_reset", 0.0), not _odo.get("trip_systems_ready", False))
    # Trips from before travel-time rates: rebuild their travel time once from the journals.
    travel_snapshot = (not _odo.get("trip_travel_ready", False), int(_odo.get("trip_jumps") or 0),
                       float(_odo.get("last_ts") or 0), float(_odo.get("trip_reset") or 0))
    limits = {boost: _stop_limit(boost) for boost in (None, 4)}   # read config on EDMC's thread

    def worker() -> None:
        try:
            if has_recovery:
                result = history.scan(folder, cache, scan_commander,
                    recovery_record.get('events', []), recovery_record.get('visits', []),
                    stop=lambda: _scan_stop,
                    progress=lambda done, total: _scan_queue.put(('progress', (done, total))))
            else:
                result = scan_all(folder, cache, progress=lambda done, total: _scan_queue.put(("progress", (done, total))),
                                  stop=lambda: _scan_stop, commander=scan_commander)
            if trip_snapshot[3] and not _scan_stop and folder:
                recovered = recover_trip_systems(folder, trip_snapshot[0], trip_snapshot[1])
                _scan_queue.put(("trip_systems", (trip_snapshot[2], recovered)))
            if travel_snapshot[0] and not _scan_stop and folder:
                stellar = lambda boost: isinstance(boost, (int, float)) and not isinstance(boost, bool) and boost >= 4
                travel = recover_trip_travel(folder, travel_snapshot[1], travel_snapshot[2], travel_snapshot[3],
                                             lambda boost: limits[4 if stellar(boost) else None])
                _scan_queue.put(("trip_travel", (travel_snapshot[3], travel)))
            _scan_queue.put(("done", result))
        except Exception:
            logger.exception("Ship Computer: reading the journals failed")
            _scan_queue.put(("failed", None))

    _scan_thread = threading.Thread(target=worker, name="ShipComputerScan", daemon=True)
    _scan_thread.start()


def _scan_results() -> None:
    """Handle the reader thread's messages on EDMC's own thread."""
    global _scanning, _scan_progress, _totals, _live, _scan_end, _rescan_commander, _recovered_visits
    while True:
        try:
            kind, payload = _scan_queue.get_nowait()
        except queue.Empty:
            return
        if kind == "progress":
            _scan_progress = payload
        elif kind == "trip_systems":
            reset, recovered = payload
            if _odo.get("trip_reset", 0.0) == reset:
                _odo["trip_systems"] = sorted(set(_odo["trip_systems"]).union(recovered))
                _odo["trip_systems_ready"] = True
                _save("odometer.json", _odo)
        elif kind == "trip_travel":
            reset, (seconds, counted, ly) = payload
            # Jumps made during the scan were already counted live (they are newer than its snapshot).
            if float(_odo.get("trip_reset") or 0) == reset and not _odo.get("trip_travel_ready"):
                _odo["trip_travel_seconds"] = float(_odo.get("trip_travel_seconds") or 0) + seconds
                _odo["trip_travel_jumps"] = int(_odo.get("trip_travel_jumps") or 0) + counted
                _odo["trip_travel_ly"] = float(_odo.get("trip_travel_ly") or 0) + ly
                _odo["trip_travel_ready"] = True
                _save("odometer.json", _odo)
        elif kind == "done":
            totals, state, end, cache = payload
            if _rescan_commander:
                _rescan_commander = False
                _scanning = False
                _start_scan()
                continue
            _totals, _scan_end = totals, end
            _recovered_visits = cache.get('recovered_visits', {})
            _live = Tracker(state)
            _live.seg_start = end
            if cache.get('recovery_files') is not None and end is not None and time.time() - end > 300:
                # Old recovered history is not evidence of a still-running session.
                _live.in_game = False
                _live.seg_start = None
            for entry, when in _buffered:
                if when is None or end is None or when > end:
                    _live.feed(entry, when)
            _buffered.clear()
            _scanning = False
            _save("stats_cache.json", cache)
            logger.info("Ship Computer: read %d journal files, %d vessels", len(cache.get("files", {})), len(totals))
            _refresh()
        else:
            _scanning = False
            _refresh()


STATS_SCOPES = ("ship", "type", "all")


def _stats_scope() -> str:
    scope = _get_str("StatsScope", "")
    if scope not in STATS_SCOPES:
        # One-time migration of the old checkbox; future clicks own this choice.
        scope = "type" if _get_bool("StatsByType", False) else "ship"
        config.set(PREFIX + "StatsScope", scope)
    return scope


def _cycle_stats_scope(_event: Any = None) -> str:
    scope = STATS_SCOPES[(STATS_SCOPES.index(_stats_scope()) + 1) % len(STATS_SCOPES)]
    config.set(PREFIX + "StatsScope", scope)
    _refresh()
    return "break"


def _stats_view() -> tuple[str, dict | None]:
    if _live is None:
        return "", None
    if hasattr(_live,"_current"):
        _live._current()  # include a newly selected ship before its first closed segment
    combined = merge(merge(merge({}, _totals), _recovered_visits), _live.vessels)
    key = _live.current_key()
    scope = _stats_scope()
    now = time.time()
    extra = _live.current_vessel_seconds(now)
    on_foot = combined.get(FOOT_KEY, {}).get("seconds", 0.0) + _live.current_foot_seconds(now)

    def aggregate(vessels):
        return {"ly": sum(v["ly"] for _, v in vessels),
                "jumps": sum(v["jumps"] for _, v in vessels),
                "seconds": sum(v["seconds"] for _, v in vessels) +
                           (extra if any(k == key for k, _ in vessels) else 0),
                "systems": len(set().union(*(v.get("systems", []) for _, v in vessels))),
                "on_foot": on_foot}

    if scope == "all":
        ships = [(k, v) for k, v in combined.items() if v["kind"] == "ship"]
        return "All Your Ships Combined", aggregate(ships)
    if key is None or key not in combined and not _live.in_game:
        return "No ship data yet", None
    current = combined.get(key) or {"kind": "carrier" if key.startswith("carrier:") else "ship",
                                    "type": "", "name": "", "ly": 0.0, "jumps": 0, "seconds": 0.0}
    if scope == "type":
        same = [(k, v) for k, v in combined.items()
                if v["kind"] == current["kind"] and v["type"] == current["type"]]
        title = "All Your fleet carriers" if current["kind"] == "carrier" else f"All Your {_ship_model(current['type'])}s"
        result = aggregate(same)
        if not any(k == key for k, _ in same):
            result["seconds"] += extra  # live vessel has not produced its first cached record
        return title, result
    result = {"ly": current["ly"], "jumps": current["jumps"], "seconds": current["seconds"] + extra,
              "systems": len(current.get("systems", [])), "on_foot": on_foot}
    if current["kind"] == "carrier":
        return f"Fleet carrier {current['name']}".strip(), result
    model = _ship_model(current["type"])
    return (f"{current['name']} ({model})" if current["name"] else model), result


# --------------------------------------------------------------------------- panel
def _current_tab() -> str:
    tab = _get_str("TabId", "")
    if tab not in TABS:                                # first run of 0.1.3: convert the old setting
        tab = OLD_TABS.get(_get_str("Tab", ""), TABS[0])
        config.set(PREFIX + "TabId", tab)
    return tab


def _select_tab(name: str) -> None:
    config.set(PREFIX + "TabId", name)
    _layout()


def _toggle_collapsed() -> None:
    config.set(PREFIX + "Collapsed", not _get_bool("Collapsed", False))
    _layout()


def _layout() -> None:
    if not _ui:
        return
    collapsed = _get_bool("Collapsed", False)
    tab = _current_tab()
    _ui["collapse"]["text"] = COLLAPSE_DOWN if collapsed else COLLAPSE_UP
    _ui["header"].configure(text=HEADER_TITLE + " (Hidden)" if collapsed else HEADER_TITLE)
    for name, page in _ui["pages"].items():
        page.grid() if (name == tab and not collapsed) else page.grid_remove()
    _ui["tabs"].grid_remove() if collapsed else _ui["tabs"].grid()
    _draw_underlines()
    _refresh()


def _apply_clock_font() -> None:
    """Fit the digits inside a fixed box, leaving about ten percent breathing room."""
    global _button_font, _clock_font, _button_font_key, _clock_font_key
    try:
        reference = tkfont.Font(font=_ui["rate"].cget("font"))
        key = tuple(sorted(reference.actual().items()))
        if key != _button_font_key:
            _button_font = tkfont.Font(font=reference)
            size = int(reference.cget("size")) or 10
            scaled = max(1, round(abs(size) * BUTTON_SCALE))
            _button_font.configure(size=-scaled if size < 0 else scaled)
            _button_font_key = key
        for widget in _ui.get("buttons", []):
            if str(widget.cget("font")) != str(_button_font):
                widget.configure(font=_button_font)
        box, clock = _ui["clock_box"], _ui["clock"]
        height = max(reference.metrics('linespace') + 6,
                     max(widget.winfo_reqheight() for widget in _ui["buttons"]))
        width = _button_font.measure('0') * 10 + 6
        box.configure(width=width, height=height)
        available_width = max(width, box.winfo_width()) - 2
        available_height = height - 2
        text = _clock(_watch_elapsed())
        sample = '8' * (len(text) - 8) + ':88:88.8'  # allow long-running clocks
        font_key = (key, available_width, available_height, len(text))
        if font_key != _clock_font_key:
            _clock_font = tkfont.Font(font=reference)
            for pixels in range(max(1, int(available_height * .9)), 0, -1):
                _clock_font.configure(size=-pixels)
                if (_clock_font.metrics('linespace') <= available_height * .9
                        and _clock_font.measure(sample) <= available_width * .9):
                    break
            _clock_font_key = font_key
        if str(clock.cget('font')) != str(_clock_font):
            clock.configure(font=_clock_font)
        colour = clock.cget("foreground")
        clock.configure(highlightbackground=colour, highlightcolor=colour)
    except (tk.TclError, ValueError, KeyError):
        pass


def _set_text(label: tk.Misc, text: str) -> None:
    """Change a label only when its text differs, so refreshes don't repaint it."""
    if str(label.cget("text")) != text:
        label.configure(text=text)


def _show_if(label: tk.Misc, text: str) -> None:
    """Set a line's text and only take up space when there is something to show."""
    _set_text(label, text)
    shown = bool(label.winfo_manager())
    if text and not shown:
        label.grid()
    elif not text and shown:
        label.grid_remove()


def _set_clock_text(text: str) -> None:
    clock = _ui['clock']
    current = str(clock.cget('text'))
    if text == current:
        return
    length_changed = len(text) != len(current)
    clock.configure(text=text)
    if length_changed:
        _schedule_theme()  # refit once when the hours gain another digit


def _scroll_laps(event: Any) -> str:
    return _scroll_view(_ui.get("laps_view"), event)


def _scroll_view(view, event: Any) -> str:
    if view is not None:
        top, bottom = view.yview()
        if not (top <= 0 and bottom >= 1):          # only when the laps don't all fit
            up = getattr(event, 'num', None) == 4 or getattr(event, 'delta', 0) > 0
            view.yview_scroll(-1 if up else 1, "units")
    return "break"


def _scroll_area(parent, name):
    view = tk.Canvas(parent, width=1, height=1, highlightthickness=0, borderwidth=0)
    inner = tk.Frame(view)
    inner.columnconfigure(0, weight=1)
    item = view.create_window(0, 0, window=inner, anchor='nw')
    _ui.setdefault('scroll_windows', {})[name] = item
    inner.bind('<Configure>', lambda _e: _size_scroll_area(view, inner, item))

    def resize(event):
        view.itemconfigure(item, width=event.width)
        if name == 'cargo':
            wrap = max(1, event.width - 55)
            for label, _count in _ui.get('cargo_rows', []):
                label.configure(wraplength=wrap)
        elif name == 'synthesis':
            _layout_synthesis_rows(event.width)
        _size_scroll_area(view, inner, item)
    view.bind('<Configure>', resize)
    _ui.setdefault('scrolls', {})[name] = (view, inner)
    _bind_scrolling(view, view)
    _bind_scrolling(inner, view)
    return view, inner


def _size_scroll_area(view, inner, item):
    # A canvas window scrolled completely off screen can retain its old size
    # while hidden. Use the frame's requested height even before it maps again.
    height = max(1, inner.winfo_reqheight())
    view.itemconfigure(item, height=height)
    view.configure(scrollregion=(0, 0, max(1, view.winfo_width()), height))


def _bind_scrolling(widget, view):
    for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
        widget.bind(sequence, lambda event, v=view: _scroll_view(v, event))
    widget.bind('<ButtonPress-1>', lambda event: view.scan_mark(0, event.y_root-view.winfo_rooty()))
    widget.bind('<B1-Motion>', lambda event: view.scan_dragto(0, event.y_root-view.winfo_rooty(), gain=1))


def _fit_heights() -> None:
    """All tabs share Trip's natural height; overflowing contents scroll."""
    view, row, trip = _ui.get("laps_view"), _ui.get("laps_row"), _ui.get("trip_inner")
    if view is None or row is None or trip is None:
        return
    try:
        page_height = max(trip.winfo_reqheight(), row.winfo_reqheight() + 12)
        page_width = max(trip.winfo_reqwidth(), row.winfo_reqwidth())
        for page in _ui['pages'].values():
            page.configure(width=page_width, height=page_height)
        target = max(1, page_height - row.winfo_reqheight() - 2)
        if int(float(view.cget("height"))) != target:
            view.configure(height=target, yscrollincrement=max(1, target // 3))
        for name in ('cargo', 'odometer', 'synthesis'):
            area = _ui['scrolls'][name][0]
            area.configure(yscrollincrement=max(1, page_height // 4))
    except (tk.TclError, ValueError, KeyError):
        pass


def _apply_lap_theme() -> None:
    """Theme all scrolling tab contents: EDMC stops at canvas boundaries.

    Use a normal data label as the reference, including EDMC's themed font.
    This also covers transparent mode's background colour key.
    """
    try:
        reference = _ui["rate"]
        background = reference.cget("background")
        foreground = reference.cget("foreground")
        font = reference.cget("font")
        for view, inner in _ui.get('scrolls', {}).values():
            view.configure(background=background)
            inner.configure(background=background)
            pending = list(inner.winfo_children())
            while pending:
                widget = pending.pop()
                options = widget.keys()
                styling = {'background': background}
                if 'foreground' in options:
                    styling['foreground'] = foreground
                if 'font' in options:
                    styling['font'] = font
                widget.configure(**styling)
                pending.extend(widget.winfo_children())
        highlight = _highlight_colour()
        if "trip_reset" in _ui:
            _ui["trip_reset"].configure(foreground=foreground)
        if "stats_title" in _ui:
            _ui["stats_title"].configure(foreground=highlight)
        for recipe_row in _ui.get("synthesis_rows",{}).values():
            recipe_row.name_label.configure(foreground=highlight)
        for row in _ui.get('synthesis_rows', {}).values():
            for number in row.numbers:
                number.configure(foreground=highlight)
        # Suite menu rule: every choice is clickable (Highlighted); the selected one is underlined.
        selected = _synthesis_group()
        underlined = tkfont.Font(font=font)
        underlined.configure(underline=True)
        _ui['synthesis_group_font'] = underlined   # keep the font alive while labels use it
        for name, label in _ui.get('synthesis_groups', {}).items():
            label.configure(background=background, foreground=highlight,
                            font=underlined if name == selected else font)
        _layout_synthesis_rows()
        popup = _ui.get("recipe_popup")
        if popup is not None:
            popup.sync_theme()
    except (tk.TclError, KeyError):
        pass


def _schedule_theme(_event: Any = None) -> None:
    """Coalesce actual theme/layout events; no theme polling or refresh timer."""
    global _theme_pending
    if not _stopped and _root is not None and _theme_pending is None:
        _theme_pending = _root.after_idle(_sync_theme)


def _sync_theme() -> None:
    global _theme_pending
    _theme_pending = None
    if not _stopped:
        _draw_underlines()


def _fit_tab_font() -> None:
    # Keep five tab names within the existing panel width, without growing EDMC.
    global _tab_font, _tab_font_key
    reference = tkfont.Font(font=_ui['rate'].cget('font'))
    width = _ui['frame'].winfo_width()
    if width <= 1:
        width = int(_ui['pages']['trip'].cget('width'))
    padding = sum(2 * TAB_PAD_X + 2 * label.winfo_pixels(label.cget('padx'))
                  + 2 * label.winfo_pixels(label.cget('borderwidth'))
                  + 2 * label.winfo_pixels(label.cget('highlightthickness'))
                  for label, _line in _ui['tab_widgets'].values())
    key = (tuple(sorted(reference.actual().items())), width, padding)
    if key != _tab_font_key:
        _tab_font = tkfont.Font(font=reference)
        pixels = abs(int(reference.cget('size')))
        if int(reference.cget('size')) > 0:
            pixels = round(pixels * float(_root.tk.call('tk', 'scaling')))
        for size in range(max(1, pixels), 0, -1):
            _tab_font.configure(size=-size)
            if sum(_tab_font.measure(TAB_LABELS[name]) for name in TABS) + padding <= max(1, width - 2):
                break
        _tab_font_key = key
    for label, _line in _ui['tab_widgets'].values():
        if str(label.cget('font')) != str(_tab_font):
            label.configure(font=_tab_font)


def _draw_underlines() -> None:
    _apply_clock_font()
    _fit_heights()
    _apply_lap_theme()
    _fit_tab_font()
    for name, (view, inner) in _ui.get('scrolls', {}).items():
        _size_scroll_area(view, inner, _ui['scroll_windows'][name])
    tab = _current_tab()
    highlight = _highlight_colour()
    for name, (label, line) in _ui.get("tab_widgets", {}).items():
        try:
            if str(label.cget("foreground")) != highlight:
                label.configure(foreground=highlight)   # tabs are clickable: Highlighted Text
            line.configure(background=label.cget("background"))
            line.delete("all")
            if name == tab:
                colour = label.cget("foreground")
                line.create_rectangle(0, 0, label.winfo_reqwidth(), 2, fill=colour, outline=colour)
        except tk.TclError:
            pass
    _apply_reset_mode()


def _refresh_cargo() -> None:
    rows = _cargo.rows()
    signature = (_cargo.summary(), tuple(rows))
    if _ui.get('cargo_signature') == signature:
        return
    _ui['cargo_signature'] = signature
    inner = _ui['scrolls']['cargo'][1]
    labels = _ui['cargo_rows']
    inner.columnconfigure(1, weight=0)
    while len(labels) < len(rows):
        name = tk.Label(inner, anchor=tk.W, justify=tk.LEFT, pady=0, borderwidth=0)
        name.navigator_no_wrap = True   # this canvas owns the wrap width (Interface skips it)
        count = tk.Label(inner, anchor=tk.E, pady=0, borderwidth=0)
        labels.append((name, count))
        for label in (name, count):
            _bind_scrolling(label, _ui['scrolls']['cargo'][0])
            try:
                from theme import theme
                theme.register(label)
            except ImportError:
                pass
    limpets = f"{_cargo.counts.get('drones', 0):,}" if _cargo.known else '—'
    _ui['cargo_summary'].configure(text=f'{_cargo.summary()}  |  Limpets: {limpets}')
    _ui['cargo_empty'].configure(text='' if _cargo.known else 'Waiting for ship cargo data')
    if rows or _cargo.known:
        _ui['cargo_empty'].grid_remove()
    else:
        _ui['cargo_empty'].grid(row=1, column=0, columnspan=2, sticky=tk.W)
    if not rows:
        _ui['scrolls']['cargo'][0].yview_moveto(0)
    width = max(1, _ui['scrolls']['cargo'][0].winfo_width() - 55)
    for index, (label, count) in enumerate(labels):
        if index < len(rows):
            name, amount = rows[index]
            label.configure(text=name, wraplength=width)
            count.configure(text=f'{amount:,} t')
            label.grid(row=index+1, column=0, sticky=tk.EW)
            count.grid(row=index+1, column=1, sticky=tk.NE, padx=(8, 0))
        else:
            label.grid_remove()
            count.grid_remove()
    _apply_lap_theme()
    _schedule_theme()


def _normal_colour() -> str:
    try:
        from theme import theme
        colour = (theme.current or {}).get('foreground')
        if colour:
            return colour
    except (ImportError, AttributeError):
        pass
    return 'black'


def _header_clicked(_event=None) -> str:
    """With the Reset Trip line hidden, the Dashboard header is the Reset Trip control."""
    if _get_bool("HideResetTrip", False):
        _reset_trip()
    return "break"


def _apply_reset_mode() -> None:
    """Reset Trip either shows as its own line, or (setting) is hidden and the header resets the trip:
    then the header is clickable but stays Normal Text (suite rule: plugin headers are never highlighted)."""
    link, header = _ui.get("trip_reset"), _ui.get("header")
    if link is None or header is None:
        return
    hidden = _get_bool("HideResetTrip", False)
    try:
        if hidden:
            link.grid_remove()
            # Suite rule: a plugin header is always Normal Text, even when clickable (like every other plugin's header).
            header.configure(cursor="hand2", takefocus=True, foreground=_normal_colour())
        else:
            link.grid()
            header.configure(cursor="", takefocus=False, foreground=_normal_colour())
    except tk.TclError:
        pass


def _highlight_colour() -> str:
    try:
        from theme import theme
        colour = (theme.current or {}).get('highlight')
        if colour:
            return colour
    except (ImportError, AttributeError):
        pass
    try:
        dark = config.get_int('theme')
    except (AttributeError, TypeError):
        dark = 0
    return config.get_str('dark_highlight', default='white') if dark else 'blue'


def _synthesis_group() -> str:
    group = _get_str('SynthesisGroup', 'Exploration')
    return group if group in GROUPS else 'Exploration'


def _select_synthesis_group(group: str) -> None:
    if group not in GROUPS:
        return
    config.set(PREFIX + 'SynthesisGroup', group)
    _refresh_synthesis()
    _ui['scrolls']['synthesis'][0].yview_moveto(0)


class RecipeScrollbar(tk.Canvas):
    """Small themed scrollbar; native Windows scrollbars ignore Tk colours."""
    def __init__(self,parent,command):
        super().__init__(parent,width=12,highlightthickness=0,borderwidth=0,takefocus=True)
        self.command=command
        self.first,self.last=0.0,1.0
        self.colour='white'
        self.drag=None
        self.bind('<Configure>',lambda _e:self.draw())
        self.bind('<Button-1>',self.press)
        self.bind('<B1-Motion>',self.move)
        self.bind('<ButtonRelease-1>',lambda _e:setattr(self,'drag',None))
        for key,direction in (('<Up>',-1),('<Down>',1)):
            self.bind(key,lambda _e,d=direction:self.command('scroll',d,'units'))

    def set(self,first,last):
        self.first,self.last=float(first),float(last)
        self.draw()

    def bounds(self):
        height=max(1,self.winfo_height())
        size=min(height,max(18,(self.last-self.first)*height))
        top=(height-size)*self.first/max(1e-9,1-(self.last-self.first))
        return top,size,height

    def draw(self):
        self.delete('all')
        if self.last-self.first < .999:
            top,size,_height=self.bounds()
            self.create_rectangle(3,top,max(4,self.winfo_width()-3),top+size,
                                  fill=self.colour,outline='')

    def press(self,event):
        top,size,height=self.bounds()
        if top<=event.y<=top+size:
            self.drag=event.y-top
        else:
            self.command('scroll',-1 if event.y<top else 1,'pages')

    def move(self,event):
        if self.drag is not None:
            _top,size,height=self.bounds()
            fraction=max(0,min(1,(event.y-self.drag)/max(1,height-size)))
            self.command('moveto',fraction*(1-(self.last-self.first)))


class RecipePopup(tk.Toplevel):
    """Scrollable recipe details with controls outside the scrolling content."""
    def __init__(self, owner):
        super().__init__(_root)
        self.withdraw()
        # Interface's window memory owns size and position (stable id across folder renames).
        self.navigator_window_id = 'Ship_Computer:recipe'
        self.owner = owner
        self.resources = []
        self.title(RECIPES[owner.recipe_key]['name'] + ' - Synthesis')
        self.transient(_root)
        self.attributes('-topmost', bool(_root.attributes('-topmost')))
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.bind('<Escape>', lambda _e: self.close())
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        tk.Label(self, text='Required amounts are per synthesis. Click a resource to copy its name.',
                 anchor=tk.W, justify=tk.LEFT, wraplength=460).grid(row=0, column=0, columnspan=2, sticky=tk.EW, padx=12, pady=8)
        self.view = tk.Canvas(self, highlightthickness=0, borderwidth=0, width=460, height=300)
        self.view.grid(row=1, column=0, sticky=tk.NSEW, padx=(12,0))
        self.scrollbar = RecipeScrollbar(self, command=self.view.yview)
        self.scrollbar.grid(row=1, column=1, sticky=tk.NS, padx=(0,12))
        self.view.configure(yscrollcommand=self.scrollbar.set)
        self.inner = tk.Frame(self.view)
        self.inner.columnconfigure(0, weight=1)
        self.item = self.view.create_window(0,0,window=self.inner,anchor='nw')
        self.view.bind('<Configure>', lambda e: self.view.itemconfigure(self.item,width=e.width))
        self.inner.bind('<Configure>', lambda _e: self.view.configure(scrollregion=self.view.bbox('all')))
        self.status = tk.Label(self, text='', anchor=tk.W)
        self.status.grid(row=2,column=0,columnspan=2,sticky=tk.EW,padx=12,pady=(8,0))
        self.close_button = tk.Button(self,text='Close',command=self.close)
        self.close_button.grid(row=3,column=0,columnspan=2,pady=8)
        row = 0
        for level, recipe in RECIPES[owner.recipe_key]['grades']:
            tk.Label(self.inner,text=('I','II','III')[level-1] + ' - Required Per Synthesis',anchor=tk.W).grid(
                row=row,column=0,columnspan=2,sticky=tk.EW,pady=(8,3))
            row += 1
            for (category,name),needed in recipe.items():
                resource = tk.Label(self.inner,text=name.title(),cursor='hand2',takefocus=True,anchor=tk.W)
                resource.grid(row=row,column=0,sticky=tk.EW,padx=(0,16))
                amount = tk.Label(self.inner,anchor=tk.E)
                amount.grid(row=row,column=1,sticky=tk.E,padx=(0,12))
                self.resources.append((resource,amount,category,name,needed,recipe))
                for sequence in ('<Button-1>','<Return>','<space>'):
                    resource.bind(sequence,lambda _e,n=name.title(): self.copy_resource(n))
                row += 1
        pending = [self.inner,self.view]
        while pending:
            widget = pending.pop()
            for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                widget.bind(sequence, lambda event: _scroll_view(self.view, event))
            pending.extend(widget.winfo_children())
        self.sync_theme()
        self.geometry("520x540")   # first-open default; Interface restores the saved geometry
        self.minsize(min(480,self.winfo_screenwidth()-40),180)
        self.deiconify()
        self.update_idletasks()
        self._native_window()
        self.close_button.focus_set()

    def copy_resource(self,name):
        try:
            self.clipboard_clear()
            self.clipboard_append(name)
            self.status.configure(text='Copied: ' + name)
        except tk.TclError:
            self.status.configure(text='Clipboard Busy. Please Try Again.')
        return 'break'

    def sync_theme(self):
        reference = _ui['rate']
        bg,fg,font = (reference.cget(key) for key in ('background','foreground','font'))
        highlight = _highlight_colour()
        pending = [self]
        while pending:
            widget = pending.pop()
            keys = widget.keys()
            options = {k:v for k,v in (('background',bg),('foreground',fg),('font',font),
                       ('activebackground',bg),('activeforeground',highlight),('troughcolor',bg)) if k in keys}
            widget.configure(**options)
            pending.extend(widget.winfo_children())
        self.close_button.configure(foreground=highlight)
        self.scrollbar.colour = highlight
        self.scrollbar.draw()
        self._native_window()
        for resource,amount,category,name,needed,recipe in self.resources:
            resource.configure(foreground=highlight)
            known = category in _synthesis.known
            have = _synthesis.materials.get(category,{}).get(name.casefold(),0)
            all_known = all(cat in _synthesis.known for cat,_ in recipe)
            limiting = min((_synthesis.materials.get(cat,{}).get(n.casefold(),0)//cost
                            for (cat,n),cost in recipe.items()), default=0) if all_known else None
            text = f"Have: {have:,}" if known else 'Have: Unknown'
            text += f"  |  Need: {needed:,}"
            if limiting is not None and have//needed == limiting:
                text += ' (Limiting)'
            amount.configure(text=text)

    def _native_window(self):
        """Colour the Windows title bar to match the panel palette (plugin-specific)."""
        if os.name != 'nt':
            return
        try:
            import ctypes
            from ctypes import wintypes
            user=ctypes.WinDLL('user32',use_last_error=True)
            user.GetParent.argtypes=[wintypes.HWND];user.GetParent.restype=wintypes.HWND
            hwnd=user.GetParent(self.winfo_id()) or self.winfo_id()
            dwm=ctypes.WinDLL('dwmapi')
            dwm.DwmSetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
            dwm.DwmSetWindowAttribute.restype=ctypes.c_long
            def colour(value):
                r,g,b=self.winfo_rgb(value)
                return (r//257)|((g//257)<<8)|((b//257)<<16)
            bg=self.cget('background');fg=_ui['rate'].cget('foreground')
            palette=(hwnd,bg,fg)
            if getattr(self,'_native_palette',None) != palette:
                for attribute,value in ((20,int(sum(self.winfo_rgb(bg))<3*32768)),(35,colour(bg)),(36,colour(fg))):
                    data=wintypes.DWORD(value)
                    dwm.DwmSetWindowAttribute(hwnd,attribute,ctypes.byref(data),ctypes.sizeof(data))
                self._native_palette=palette
        except (OSError,AttributeError,tk.TclError,ValueError):
            logger.debug('Recipe window native styling unavailable',exc_info=True)

    def close(self):
        self.owner.details = None
        if _ui.get('recipe_popup') is self:
            _ui.pop('recipe_popup',None)
        self.destroy()


class SynthesisRow(tk.Frame):
    """Normal recipe/grade text, with separately styled, non-clickable counts."""
    def __init__(self, parent, name, grades, view, recipe_key=None):
        super().__init__(parent, borderwidth=0)
        self.columnconfigure(0, weight=1)
        self.recipe_key = recipe_key
        self.details = None
        self.name_label = tk.Label(self, text=name + ': ', anchor=tk.W, justify=tk.LEFT,
                                   padx=0, pady=0, borderwidth=0)
        self.name_label.navigator_no_wrap = True   # arrange() owns the wrap width (Interface skips it)
        self.amounts = tk.Frame(self, borderwidth=0)
        self.numbers, self.parts = [], []
        for index, level in enumerate((1, 2, 3)):
            if index:
                slash = tk.Label(self.amounts, text=' / ', padx=0, pady=0, borderwidth=0)
                slash.grid(row=0, column=index * 2 - 1)
                self.parts.append(slash)
            number = tk.Label(self.amounts, padx=0, pady=0, borderwidth=0, cursor='arrow')
            number.grid(row=0, column=index * 2, sticky=tk.EW)
            self.numbers.append(number)
            self.parts.append(number)
        self.set_counts(grades)
        for widget in [self, self.name_label, self.amounts] + self.parts:
            _bind_scrolling(widget, view)
        if recipe_key:
            self.name_label.configure(cursor="hand2",takefocus=True)
            for sequence in ("<Button-1>","<Return>","<space>"):
                self.name_label.bind(sequence,self._toggle_details)
        try:
            from theme import theme
            theme.register(self)
        except ImportError:
            pass

    def _toggle_details(self,event=None):
        if self.details is not None:
            self.details.close()
        else:
            previous = _ui.get('recipe_popup')
            if previous is not None:
                previous.close()
            self.details = RecipePopup(self)
            _ui['recipe_popup'] = self.details
        return "break"

    def set_counts(self, grades):
        counts = dict(grades)
        for level, label in enumerate(self.numbers, 1):
            count = counts.get(level)
            label.configure(text='\u2014' if level not in counts else '?' if count is None else f'{count:,}')

    def line_text(self):
        return self.name_label.cget('text') + ''.join(str(label.cget('text')) for label in self.parts)

    def arrange(self, width, font, name_width, cell_width):
        amount_width = 3 * cell_width + 2 * font.measure(' / ')
        for column in (0, 2, 4):
            self.amounts.columnconfigure(column, minsize=cell_width)
        self.columnconfigure(0, minsize=name_width if name_width + amount_width <= width else 0)
        if name_width + amount_width <= width:
            self.name_label.configure(wraplength=0)
            self.name_label.grid(row=0, column=0, columnspan=1, sticky=tk.W)
            self.amounts.grid(row=0, column=1, columnspan=1, sticky=tk.E)
        else:
            self.name_label.configure(wraplength=max(1, width))
            self.name_label.grid(row=0, column=0, columnspan=3, sticky=tk.W)
            self.amounts.grid(row=1, column=0, columnspan=3, sticky=tk.E)


def _layout_synthesis_rows(width=None) -> None:
    if 'synthesis' not in _ui.get('scrolls', {}):
        return
    if width is None:
        width = _ui['scrolls']['synthesis'][0].winfo_width()
    if width <= 1:
        return
    font = tkfont.Font(font=_ui['rate'].cget('font'))
    rows = [row for row in _ui.get('synthesis_rows', {}).values() if row.grid_info()]
    header = _ui.get('synthesis_grade_header')
    if header is not None:
        rows.append(header)
    name_width = max((font.measure(row.name_label.cget('text')) for row in rows), default=0)
    cell_width = max([font.measure('III')] + [font.measure(label.cget('text')) for row in rows for label in row.numbers])
    for row in rows:
        row.arrange(width, font, name_width, cell_width)


def _refresh_synthesis() -> None:
    group = _synthesis_group()
    rows = _synthesis.group_rows(group)
    signature = (group, rows)
    if _ui.get('synthesis_signature') == signature:
        return
    _ui['synthesis_signature'] = signature
    view, inner = _ui['scrolls']['synthesis']
    cache = _ui['synthesis_rows']
    for row in cache.values():
        row.grid_remove()
    for index, (key, name, grades) in enumerate(rows):
        if key not in cache:
            cache[key] = SynthesisRow(inner, name, grades, view, key)
        row = cache[key]
        row.set_counts(grades)
        row.grid(row=index + 1, column=0, sticky=tk.EW)
    if 'fsd' in cache:
        _ui['synthesis_fsd'] = cache['fsd']
    _apply_lap_theme()
    _schedule_theme()


def _refresh() -> None:
    if not _ui:
        return
    try:
        rate, speed, estimated = _rates()
        u = _ui
        approx = "~" if estimated else ""   # standard pace, until two gaps are measured
        jumps_rate = f"{approx}{rate:,.1f} J/hr" if rate is not None else "- J/hr"
        ly_rate = f"{approx}{speed:,.0f} Ly/hr" if speed is not None else "- Ly/hr"
        _set_text(u["rate"], jumps_rate + "  |  " + ly_rate)
        _set_text(u["trip_time"], _clock(float(_odo.get("trip_seconds") or 0), False))
        _set_text(u["trip"], _jumps(_odo["trip_jumps"]))
        _set_text(u["systems"], f'{len(_odo["trip_systems"]):,}')
        _set_text(u["distance"], _ly(_odo["trip_ly"]))
        _set_text(u["landings"], f'{_odo.get("trip_landings", 0):,}')

        _set_clock_text(_clock(_watch_elapsed()))
        _set_text(u["start"], "Stop" if _watch.get("running") else "Start")
        laps = list(reversed(_watch.get("laps", [])))[:LAPS_SHOWN]
        for index, label in enumerate(u["laps"]):
            lap = laps[index] if index < len(laps) else None
            _show_if(label, (f"Lap {lap['n']}: {_clock(lap['lap'])}  (total {_clock(lap['total'], False)})"
                             f"  {_jumps(lap['jumps'])} · {_ly(lap['ly'])}") if lap else "")

        _refresh_cargo()
        _refresh_synthesis()

        if _scanning:
            done, total = _scan_progress
            _show_if(u["stats_title"], "Reading your journals…")
            _show_if(u["stats_status"], f"{done} of {total} files" if total else "")
            for key in ("stats_ly", "stats_jumps", "stats_time", "stats_systems", "stats_foot"):
                _show_if(u[key], "")
        else:
            title, result = _stats_view()
            _show_if(u["stats_title"], title or ("Journal folder not found" if _journal_dir() is None else ""))
            _show_if(u["stats_status"], "")
            _show_if(u["stats_ly"], f"Distance: {_ly(result['ly'])}" if result else "")
            _show_if(u["stats_jumps"], f"Jumps: {result['jumps']:,}" if result else "")
            _show_if(u["stats_time"], f"Time: {_duration(result['seconds'])}" if result else "")
            _show_if(u["stats_systems"], f"Systems: {result.get('systems', 0):,}" if result else "")
            _show_if(u["stats_foot"], f"On Foot: {_duration(result.get('on_foot', 0))}" if result else "")
    except (tk.TclError, KeyError):
        pass


def _tick() -> None:
    """Fast while the stopwatch runs; slow otherwise. Also collects reader results."""
    global _tick_id
    if _stopped or _root is None or config.shutting_down:
        return
    _scan_results()
    if _recovery is not None:
        _recovery.poll()
    _count_trip_time()
    if _current_tab() == "trip" and not _get_bool("Collapsed", False):
        try:
            _ui["trip_time"]["text"] = _clock(float(_odo.get("trip_seconds") or 0), False)
        except (tk.TclError, KeyError):
            pass
    if _watch.get("running") and _current_tab() == "stopwatch" and not _get_bool("Collapsed", False):
        try:
            _set_clock_text(_clock(_watch_elapsed()))
        except (tk.TclError, KeyError):
            pass
        delay = 100
    else:
        delay = 500 if _scanning else 1000
        _ui["slow"] = _ui.get("slow", 0) + delay
        if _ui["slow"] >= 30000:             # refresh time-in-ship etc. every 30 s
            _ui["slow"] = 0
            _save("odometer.json", _odo)     # keep Trip Time safe
            _refresh()
    _tick_id = _root.after(delay, _tick)


def plugin_start3(plugin_dir: str) -> str:
    global _cargo, _synthesis, _recovery
    import sys
    _recovery = Recovery(sys.modules[__name__])
    _cargo = CargoManifest()
    _synthesis = SynthesisInventory()
    _odo.clear()
    _odo.update(_odo_defaults())
    saved = _load("odometer.json", {})
    _odo.update(saved)
    _odo.pop("trip_undo", None)
    if 'trip_landings' not in saved:
        _odo['landing_last_ts'] = time.time()  # start now; do not count startup replay
        _save("odometer.json", _odo)
    _watch.clear()
    _watch.update(_watch_defaults())
    _watch.update(_load("stopwatch.json", {}))
    logger.info("%s %s loaded", TITLE, VERSION)
    return TITLE


def plugin_app(parent: tk.Frame) -> tk.Frame:
    global _root, _stopped, _tick_id
    _root = parent.winfo_toplevel()
    _stopped = False
    frame = tk.Frame(parent)
    frame.columnconfigure(0, weight=1)
    _ui.clear()
    _ui["frame"] = frame
    # Give the stock control its own cell: title growth cannot overlap it.
    header = tk.Frame(frame)
    header.grid(row=0, column=0, sticky=tk.EW)
    header.columnconfigure((0, 2), uniform="header_controls")
    header.columnconfigure(1, weight=1)
    _ui["header"] = tk.Label(header, text=HEADER_TITLE)
    _ui["header"].grid(row=0, column=1)
    for sequence in ("<Button-1>", "<Return>", "<space>"):
        _ui["header"].bind(sequence, _header_clicked)      # only acts while Reset Trip is hidden (setting)
    _ui["collapse"] = tk.Button(header, text=COLLAPSE_UP, command=_toggle_collapsed)
    _ui["collapse"].grid(row=0, column=2, sticky=tk.NE)

    tabs = tk.Frame(frame)
    tabs.grid(row=1, column=0, pady=(0, 8))      # space so buttons don't touch the tab underline
    _ui["tabs"] = tabs
    _ui["tab_widgets"] = {}
    for column, name in enumerate(TABS):
        cell = tk.Frame(tabs)
        cell.grid(row=0, column=column, padx=TAB_PAD_X)
        label = tk.Label(cell, text=TAB_LABELS[name], cursor="hand2")
        label.pack()
        line = tk.Canvas(cell, height=2, width=1, highlightthickness=0, bd=0)
        line.pack(fill=tk.X)
        label.bind("<Button-1>", lambda _event, tab=name: _select_tab(tab))
        _ui["tab_widgets"][name] = (label, line)

    pages = {name: tk.Frame(frame) for name in TABS}
    for page in pages.values():
        page.grid(row=2, column=0, sticky=tk.EW)
        page.configure(width=1, height=1)
        page.grid_propagate(False)
        page.columnconfigure(1, weight=1)
    _ui["pages"] = pages

    tight = {"pady": 0, "borderwidth": 0}           # no extra space between lines
    odo = tk.Frame(pages['trip'])
    # The page has a fixed size shared by every tab. Fill it exactly; the inner
    # grid supplies the natural height and positions Reset at the actual edge.
    odo.place(x=0, y=0, relwidth=1, relheight=1)
    odo.columnconfigure(1, weight=1)
    _ui['trip_inner'] = odo
    for row, (caption, key) in enumerate((("Jump Rate:", "rate"), ("Trip:", "trip"),
                                          ("Trip Time:", "trip_time"), ("Systems:", "systems"),
                                          ("Distance:", "distance"), ("Times Landed:", "landings"))):
        tk.Label(odo, text=caption, anchor=tk.W, **tight).grid(row=row, column=0, sticky=tk.W)
        _ui[key] = tk.Label(odo, anchor=tk.W, **tight)
        _ui[key].grid(row=row, column=1, sticky=tk.W, padx=(6, 0))
    reset_link = tk.Label(odo,text="Reset Trip",cursor="hand2",takefocus=True,**tight)
    reset_link.grid(row=6,column=0,columnspan=2)
    _ui["trip_reset"] = reset_link
    for sequence in ('<Button-1>', '<Return>', '<space>'):
        reset_link.bind(sequence, lambda _e: _reset_trip())

    watch = pages["stopwatch"]
    watch.rowconfigure(1, weight=1)
    row_frame = tk.Frame(watch)
    row_frame.grid(row=0, column=0, columnspan=3, sticky=tk.EW)   # full width: clock left, buttons right
    # The time, boxed in the theme colour and the same height as the buttons, on the left.
    _ui['clock_box'] = tk.Frame(row_frame, width=76, height=24)
    _ui['clock_box'].pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    _ui['clock_box'].pack_propagate(False)
    _ui["clock"] = tk.Label(_ui['clock_box'], anchor=tk.CENTER, padx=0, pady=0, borderwidth=0,
                            highlightthickness=1)
    _ui["clock"].place(x=0, y=0, relwidth=1, relheight=1)
    # Packed from the right edge, so they read Start, Lap, Reset left to right.
    watch_reset = tk.Button(row_frame, text="Reset", width=BUTTON_WIDTH, command=_reset_watch, **BUTTON)
    watch_reset.pack(side=tk.RIGHT, padx=(3, 0))
    lap_button = tk.Button(row_frame, text="Lap", width=BUTTON_WIDTH, command=_lap, **BUTTON)
    lap_button.pack(side=tk.RIGHT, padx=3)
    _ui["start"] = tk.Button(row_frame, text="Start", width=BUTTON_WIDTH, command=_start_stop, **BUTTON)
    _ui["start"].pack(side=tk.RIGHT, padx=3)
    _ui["buttons"] = [_ui["start"], lap_button, watch_reset]
    # Laps scroll inside a fixed-height area so this tab is exactly as tall as Trip.
    laps_view, laps_inner = _scroll_area(watch, 'stopwatch')
    laps_view.grid(row=1, column=0, columnspan=3, sticky=tk.NSEW, pady=(2, 0))
    _ui["laps_view"], _ui["laps_row"] = laps_view, row_frame
    _ui["laps_inner"] = laps_inner
    _ui["laps"] = []
    for row in range(LAPS_SHOWN):
        label = tk.Label(laps_inner, anchor=tk.W, **tight)
        label.grid(row=row, column=0, sticky=tk.W)
        label.grid_remove()                          # appears when there is a lap to show
        _ui["laps"].append(label)
        _bind_scrolling(label, laps_view)

    stats_view, stats = _scroll_area(pages['odometer'], 'odometer')
    stats_view.pack(fill=tk.BOTH, expand=True)
    # A packed child must not override the fixed height of its page either.
    pages['odometer'].pack_propagate(False)
    for row, key in ((0, 'stats_title'), (1, 'stats_ly'), (2, 'stats_jumps'),
                     (3, 'stats_time'), (4, 'stats_systems'), (5, 'stats_foot'), (6, 'stats_status')):
        heading = key == 'stats_title'
        _ui[key] = tk.Label(stats, anchor=tk.CENTER if heading else tk.W,
                            justify=tk.CENTER if heading else tk.LEFT, **tight)
        _ui[key].grid(row=row, column=0, columnspan=3, sticky=tk.EW if heading else tk.W)
        _bind_scrolling(_ui[key], stats_view)
        if heading:
            _ui[key].configure(cursor="hand2", takefocus=True)
            for sequence in ("<Button-1>", "<Return>", "<space>"):
                _ui[key].bind(sequence, _cycle_stats_scope)

    cargo_view, cargo_inner = _scroll_area(pages['cargo'], 'cargo')
    cargo_view.pack(fill=tk.BOTH, expand=True)
    pages['cargo'].pack_propagate(False)
    _ui['cargo_rows'] = []
    _ui['cargo_summary'] = tk.Label(cargo_inner, anchor=tk.CENTER, justify=tk.CENTER, pady=0, borderwidth=0)
    _ui['cargo_summary'].grid(row=0, column=0, columnspan=2, sticky=tk.EW)
    _ui['cargo_empty'] = tk.Label(cargo_inner, anchor=tk.W, pady=0, borderwidth=0)
    for label in (_ui['cargo_summary'], _ui['cargo_empty']):
        _bind_scrolling(label, cargo_view)

    synthesis_page = pages['synthesis']
    synthesis_page.columnconfigure(0, weight=1)
    synthesis_page.columnconfigure(1, weight=0)
    synthesis_page.rowconfigure(1, weight=1)
    group_bar = tk.Frame(synthesis_page)
    group_bar.grid(row=0, column=0, columnspan=2)  # center the selector strip as one unit
    _ui['synthesis_groups'] = {}
    _ui['synthesis_rows'] = {}
    for column, group in enumerate(GROUPS):
        label = tk.Label(group_bar, text=group, cursor='hand2', takefocus=True, pady=0)
        label.grid(row=0, column=column, sticky=tk.W, padx=TAB_PAD_X)
        def select(_event, name=group):
            _select_synthesis_group(name)
            return 'break'
        for sequence in ('<Button-1>', '<Return>', '<space>'):
            label.bind(sequence, select)
        _ui['synthesis_groups'][group] = label
    synthesis_view, synthesis_inner = _scroll_area(synthesis_page, 'synthesis')
    synthesis_view.grid(row=1, column=0, columnspan=2, sticky=tk.NSEW)
    grade_header = SynthesisRow(synthesis_inner, '', (), synthesis_view)
    grade_header.name_label.configure(text='')
    for label, grade in zip(grade_header.numbers, ('I', 'II', 'III')):
        label.configure(text=grade)
    grade_header.grid(row=0, column=0, sticky=tk.EW)
    _ui['synthesis_grade_header'] = grade_header

    # EDMC's theme traversal stops at canvas windows; register each inner tree.
    try:
        from theme import theme
        for _view, inner in _ui['scrolls'].values():
            theme.register(inner)
    except ImportError:
        pass

    _layout()
    for sequence in ("<<ThemeChanged>>", "<Configure>", "<Map>"):
        _theme_bindings.append((sequence, _root.bind(sequence, _schedule_theme, add="+")))
    _schedule_theme()                     # EDMC applies its theme after plugin_app
    _start_scan()
    _tick_id = _root.after(500, _tick)
    return frame


def journal_entry(cmdr: str, is_beta: bool, system: str | None, station: str | None,
                  entry: dict[str, Any], state: dict[str, Any]) -> None:
    global _active_commander, _rescan_commander, _live, _totals
    if cmdr and cmdr != _active_commander:
        previous = _active_commander
        _active_commander = cmdr
        if previous or (_live is not None):
            _live = None
            _totals = {}
            _buffered.clear()
            if _scanning: _rescan_commander = True
            else: _start_scan()
        elif _scanning:
            _rescan_commander = True
    _cargo.update(entry, state)
    _synthesis.update(entry, state)
    when = parse_ts(entry.get("timestamp"))
    _count_landing(entry, state, when)
    if (entry.get("event") == "Undocked" and when and _get_bool("ResetOnUndock", False)
            and when > float(_odo.get("undock_ts") or 0) and time.time() - when < 300):
        _odo["undock_ts"] = when                    # once per undock; never for replayed old events
        _clear_trip()
        logger.info("Ship Computer: trip reset on undocking")
    if entry.get("event") == "FSDJump" and entry.get("JumpDist") and not entry.get("Taxi") and when:
        _count_jump(float(entry["JumpDist"]), when, system_key(entry), entry.get("BoostUsed"))
    if _live is None:
        _buffered.append((dict(entry), when))      # the reader is still busy; apply afterwards
    elif when is None or _scan_end is None or when > _scan_end:
        _live.feed(entry, when)
    _refresh()


def plugin_stop() -> None:
    global _stopped, _scan_stop, _tick_id, _theme_pending
    _stopped, _scan_stop = True, True
    if _recovery is not None:
        _recovery.cancel.set()
        if _recovery.window is not None:
            try:
                _recovery.window.destroy()
            except tk.TclError:
                pass
    popup = _ui.get("recipe_popup")
    if popup is not None:
        popup.close()
    if _root is not None:
        for callback in (_tick_id, _theme_pending):
            if callback is not None:
                try:
                    _root.after_cancel(callback)
                except tk.TclError:
                    pass
        for sequence, binding in _theme_bindings:
            try:
                _root.unbind(sequence, binding)
            except tk.TclError:
                pass
    _tick_id = _theme_pending = None
    _theme_bindings.clear()
    if _odo:
        _count_trip_time()
        _save("odometer.json", _odo)
    if _watch:
        _save("stopwatch.json", _watch)


def plugin_prefs(parent: nb.Notebook, cmdr: str, is_beta: bool) -> tk.Frame:
    try:
        from plug import invoke
        outer = invoke("(N) Interface", "Navigator Interface", "navigator_scroll_settings", parent)
        frame = getattr(outer, "navigator_settings_content", None)
    except ImportError:
        outer = None
        frame = None
    if frame is None:
        outer = nb.Frame(parent)
        frame = outer
    _prefs["undock"] = tk.BooleanVar(value=_get_bool("ResetOnUndock", False))
    _prefs["hide_reset"] = tk.BooleanVar(value=_get_bool("HideResetTrip", False))
    # Suite settings order: title, everyday options, tools, accessibility, credit line.
    nb.Label(frame, text=f"{TITLE} {VERSION}").grid(row=0, column=0, sticky=tk.W, padx=10, pady=(10, 6))
    trip_options = nb.Frame(frame)
    trip_options.grid(row=1, column=0, sticky=tk.W, padx=10)
    nb.Checkbutton(trip_options, text="Trip tab: reset the trip automatically every time you undock",
                   variable=_prefs["undock"]).grid(row=0, column=0, sticky=tk.W)
    nb.Checkbutton(trip_options, text="Trip tab: hide the Reset Trip line (click the Dashboard header to "
                                      "reset the trip instead)",
                   variable=_prefs["hide_reset"]).grid(row=1, column=0, sticky=tk.W)
    _prefs["stops"] = tk.BooleanVar(value=_get_bool("IncludeStopTime", False))
    nb.Checkbutton(frame, text="Jump Rate: include stop time (trading and mining: see time spent docking and between stations)",
                   variable=_prefs["stops"]).grid(row=2, column=0, sticky=tk.W, padx=10, pady=(6, 0))
    nb.Label(frame, text="Off (default): only travel time between jumps counts, so the rate holds steady between jumps.").grid(
        row=3, column=0, sticky=tk.W, padx=10)
    paces = nb.Frame(frame)
    paces.grid(row=4, column=0, sticky=tk.W, padx=10, pady=(4, 0))
    Entry = getattr(nb, "Entry", ttk.Entry)
    for column, (key, setting, default, text) in enumerate((
            ("pace", "StandardJumpSeconds", STANDARD_JUMP, "Standard jump time (seconds)"),
            ("neutron_pace", "StandardNeutronSeconds", STANDARD_NEUTRON, "Standard neutron jump time (seconds)"))):
        _prefs[key] = tk.StringVar(value=str(_get_seconds(setting, default)))
        nb.Label(paces, text=text).grid(row=column, column=0, sticky=tk.W)
        Entry(paces, textvariable=_prefs[key], width=5).grid(row=column, column=1, sticky=tk.W, padx=(6, 0))
    nb.Label(frame, text=f"Arrival to arrival, 20–600. A gap over {STOP_FACTOR}× this counts as a stop. Until two gaps are\n"
                         "measured, Jump Rate shows ~ your standard pace × this trip's average jump.").grid(
        row=5, column=0, sticky=tk.W, padx=10)
    nb.Label(frame, text="Odometer: click its highlighted heading to cycle ship / type / all ships.").grid(
        row=6, column=0, sticky=tk.W, padx=10, pady=(6, 0))

    def rescan() -> None:
        _start_scan(fresh=True)
        _refresh()
    ttk.Button(frame, text="Re-read All Journals", command=rescan).grid(row=7, column=0, sticky=tk.W, padx=10, pady=8)
    nb.Label(frame, text="Odometer totals are read from your game journals; only new or changed files are read again.\n"
                         "Fleet carriers count as their own vessel while you are docked aboard.\n"
                         "Odometer and stopwatch count your ship's own jumps (not carrier or taxi jumps).").grid(
        row=8, column=0, sticky=tk.W, padx=10)
    if _recovery is not None:
        _recovery.build(frame, 9)
    # Required Interface owns the shared contrast preference and rendering.
    try:
        from plug import invoke
        invoke("(N) Interface", "Navigator Interface", "navigator_background_preferences",
               frame, "Navigator_Dashboard")
    except ImportError:
        pass
    nb.Label(frame, text="Part of the Navigator plugin suite by Commander Thalinor").grid(
        row=frame.grid_size()[1], column=0, sticky=tk.W, padx=10, pady=(12, 10))
    return outer


def prefs_changed(cmdr: str, is_beta: bool) -> None:
    if "undock" in _prefs:
        config.set(PREFIX + "ResetOnUndock", bool(_prefs["undock"].get()))
    if "hide_reset" in _prefs:
        config.set(PREFIX + "HideResetTrip", bool(_prefs["hide_reset"].get()))
    if "stops" in _prefs:
        config.set(PREFIX + "IncludeStopTime", bool(_prefs["stops"].get()))
    for key, setting, default in (("pace", "StandardJumpSeconds", STANDARD_JUMP),
                                  ("neutron_pace", "StandardNeutronSeconds", STANDARD_NEUTRON)):
        if key in _prefs:
            try:
                value = int(str(_prefs[key].get()).strip())
            except ValueError:
                value = _get_seconds(setting, default)
            config.set(PREFIX + setting, str(max(20, min(600, value))))
    _apply_reset_mode()
    _refresh()
