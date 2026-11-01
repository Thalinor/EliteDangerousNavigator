# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Navigation: neutron and route planning, route progress, and click-a-name copy or galaxy-map plotting for EDMC."""
from __future__ import annotations

import csv
import io
import json
import math
import queue
import urllib.error
import urllib.parse
import urllib.request
import os
import re
import shutil
import tempfile
import time
from datetime import datetime, timezone
from typing import Any

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from tkinter import filedialog, messagebox, simpledialog
from EDMCLogging import get_main_logger
from config import config

logger = get_main_logger()
TITLE = "(N) Navigation"            # plugin name (About, EDMC plugin list, logs)
HEADER = "Navigation"   # panel header: the same in every edition
INTERNAL_BANNER = ""
VERSION = "0.43.9"
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.basename(PLUGIN_DIR)         # the key (N) Interface keeps this plugin's copy/auto choice under
DATA_DIR = PLUGIN_DIR
STATE_PATH = os.path.join(DATA_DIR, "cockpit_state.json")
ROUTE_PATH = os.path.join(DATA_DIR, "active_route.json")
STATUS_PATH: str | None = None   # Elite's Status.json, found at startup

TABS = ("Highway", "Missions", "Expedition", "Rescue")   # second row under the header
OPTIONAL_TABS = {"Missions": "show_missions_tab",   # tabs that only show while their setting is on (Missions: not built yet)
                 "Rescue": "show_rescue_tab"}
# Saved places are a separate tool that will work with Navigation (Jonathan, 1 Nov), so there is no Saved tab here.
_tab_pages: dict = {}          # tab name -> its page (Neutron Highway holds everything Navigation did before)
_app_frame = None
_page = None                   # the selected tab's page (the route lines live here)
_tab_row = None
_tab_font = None
_tab_widgets: dict = {}
_current_label = None
_jump_label = None
_next_label = None
_done_label = None
_left_label = None
_systems_popup = None
_end_label = None
_title_label = None
_collapse_button = None
_mode_button = None            # (N) Interface's copy/auto toggle, beside the collapse button
_shortcut_bar = None           # the optional row of shortcut buttons between the header and the tabs
_shortcut_buttons: list = []
_shortcut_state = None         # what the row last looked like, so a journal event redraws nothing new
_shortcut_toggle_button = None  # the S in the header stack that hides or shows the row
_compass = None                # the Auto-Route toggle in the header (an R box)
_header_frame = None
_route_rows: list = []
_route_systems: list[str] = []
_route_legs: list[int] = []     # jumps to reach each waypoint from the one before (0 for the first)
_route_index = -1
_left_extra = None             # the blue "(4 neutrons)" after the jumps left
_trail: list[str] = []          # systems actually jumped to since this route was loaded
_leg_jumps = 0                 # jumps made since the last waypoint (the leg in progress)
_snapshot: dict[str, Any] = {
    "schema_version": 1, "source": "EDMarketConnector", "updated_at_utc": None,
    "location": {}, "ship": {}, "cockpit": {}, "route": {},
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_safe(value: Any) -> bool:
    try:
        json.dumps(value, allow_nan=False)
        return True
    except (TypeError, ValueError):
        return False


def _copy_present(source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: source[key] for key in keys if key in source and _json_safe(source[key])}


def _write_json(path: str, data: dict[str, Any]) -> None:
    fd, temporary = tempfile.mkstemp(prefix="neutron_nav_", suffix=".tmp", dir=DATA_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        # Windows refuses to replace a file another program has open (Explorer
        # preview, an editor, a scanner), so retry briefly, then fall back to
        # writing in place, which works when the other program only reads.
        for attempt in range(5):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                time.sleep(0.1 * (attempt + 1))
        with open(temporary, encoding="utf-8") as source, \
                open(path, "w", encoding="utf-8", newline="\n") as target:
            target.write(source.read())
        os.unlink(temporary)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _current_system() -> str | None:
    return _route_systems[_route_index] if 0 <= _route_index < len(_route_systems) else None


def _next_system() -> str | None:
    index = _route_index + 1
    return _route_systems[index] if 0 <= index < len(_route_systems) else None


def _end_system() -> str | None:
    return _route_systems[-1] if _route_systems else None


def _waypoint_counts() -> tuple[int, int]:
    """Waypoints (neutron stars, stops...) reached and still ahead."""
    if not _route_systems:
        return 0, 0
    done = max(0, _route_index)
    return done, max(0, len(_route_systems) - 1 - done)


_navroute_cache: dict[str, Any] = {"stamp": None, "names": [], "classes": {}}


def _navroute_names() -> list[str]:
    """Every system on the route plotted in the game (NavRoute.json), in order; empty if there is none."""
    try:
        directory = _journal_dir()
        path = os.path.join(directory, "NavRoute.json") if directory else None
        stamp = (os.path.getmtime(path), os.path.getsize(path)) if path and os.path.isfile(path) else None
    except OSError:
        stamp = None
    if stamp is None:
        _navroute_cache.update(stamp=None, names=[], classes={})
    elif stamp != _navroute_cache["stamp"]:
        data = _read_journal_json("NavRoute.json") or {}
        items = [item for item in data.get("Route") or [] if isinstance(item, dict)]
        _navroute_cache.update(stamp=stamp, names=[str(item.get("StarSystem") or "") for item in items],
                               classes={str(item.get("StarSystem") or "").casefold(): str(item.get("StarClass") or "")
                                        for item in items if item.get("StarClass")})
    return list(_navroute_cache["names"])


_star_classes: dict[str, str] = {}      # star class of systems jumped to (from the journal), by lower-case name


def _note_star_class(entry: dict[str, Any]) -> None:
    if entry.get("event") in ("FSDJump", "StartJump") and entry.get("StarClass") and entry.get("StarSystem"):
        _star_classes[str(entry["StarSystem"]).casefold()] = str(entry["StarClass"])
        while len(_star_classes) > 3000:
            del _star_classes[next(iter(_star_classes))]


def _star_class_of(name: str) -> str:
    """The star class of a system when it is certain: the game's plotted route, or a jump you made. A neutron route's own
    waypoints (not its start or end) are neutron stars. Otherwise '' (not known)."""
    key = name.casefold()
    _navroute_names()
    known = _star_classes.get(key) or _navroute_cache["classes"].get(key)
    if known:
        return known
    if _route_kind == "neutron" and len(_route_systems) > 2:
        if any(system.casefold() == key for system in _route_systems[1:-1]):
            return "N"
    return ""


def _fuel_distance(name: str) -> float | None:
    """Light seconds from the arrival star to the nearest scoopable star of a system: 0 when you arrive at one, else what
    (N) Cartography has on record. None when not known (never guessed)."""
    star = _star_class_of(name)
    if star and star[:1] in SCOOPABLE:
        return 0.0
    distance = _cartography("navigator_fuel_distance", name)
    return float(distance) if isinstance(distance, (int, float)) else None


def _class_tags(systems: list[str]) -> dict[str, str]:
    """(N) for a neutron star, (D) for a white dwarf, (F) for a system with a star you can scoop (KGBFOAM) - the arrival
    star, or one Cartography has seen. Systems not known for sure get no tag."""
    tags: dict[str, str] = {}
    for name in systems:
        star = _star_class_of(name)
        if star[:1] == "N":
            tags[name.casefold()] = "(N)"
        elif star[:1] == "D":
            tags[name.casefold()] = "(D)"                # a white dwarf: boosts too, by less than a neutron star
        elif _fuel_distance(name) is not None:
            tags[name.casefold()] = "(F)"
    return tags


def _tag_colour(name: str, tag: str, dark: bool) -> str | None:
    """The colour of a route tag from (N) Interface: N blue, D pale blue, F green / yellow / red by how far the scoopable
    star is from arrival. None (theme colours) when Interface is missing or its accessibility setting is on."""
    if tag == "(F)":
        return _interface("navigator_fuel_colour", _fuel_distance(name), dark)
    return _interface("navigator_tag_colour", tag, dark)


def _next_jump_system() -> str | None:
    """The very next system to jump to, neutron or not. From the route plotted in the game; with no such route it is the
    next waypoint only when that is one jump away."""
    nxt = _next_system()
    if nxt is None:
        return None
    _, _, _, ahead = _leg_view()
    if ahead:
        return ahead[0]
    legs = _route_legs if len(_route_legs) == len(_route_systems) else [0] + [1] * (len(_route_systems) - 1)
    return nxt if legs[max(0, _route_index) + 1] <= 1 else None


def _fuel_summary(ahead: list[str]) -> str:
    """For the Jumps Left list: how far the fuel goes, and how far away the next scoopable star is."""
    status = _read_journal_json("Status.json") or {}
    try:
        fuel = float((status.get("Fuel") or {}).get("FuelMain"))
    except (TypeError, ValueError):
        return ""
    if not _fuel_used:
        return ""
    per_jump = max(sum(_fuel_used[-4:]) / len(_fuel_used[-4:]), 0.01)
    jumps = int(fuel // per_jump)
    gap = next((number for number, name in enumerate(ahead, start=1)
                if (_star_class_of(name) or " ")[:1] in SCOOPABLE), None)
    text = f"Fuel: about {jumps} jump{'s' if jumps != 1 else ''}. "
    if gap is None:
        return text + "No scoopable star known ahead yet."
    return text + f"Next scoopable star: jump {gap}" + (" - further than your fuel reaches." if gap > jumps else ".")


def _leg_view() -> tuple[int, int, list[str], list[str]]:
    """The leg from the last waypoint to the next one: (jumps done in it, jumps left in it, the systems jumped
    through, the systems still to jump to). The route only lists waypoints (neutron stars), so the systems in
    between come from the route plotted in the game (NavRoute.json) when it leads to the next waypoint; otherwise
    from counting your own jumps since the last waypoint."""
    nxt = _next_system()
    if not _route_systems or nxt is None:
        return 0, 0, [], []
    index = max(0, _route_index)
    legs = _route_legs if len(_route_legs) == len(_route_systems) else [0] + [1] * (len(_route_systems) - 1)
    leg_length = max(1, legs[index + 1])
    here = str(_snapshot.get("location", {}).get("system_name") or "").casefold()
    names = _navroute_names()
    folded = [name.casefold() for name in names]
    if names and folded[-1] == nxt.casefold() and here in folded:
        current = folded.index(here)
        left_names = names[current + 1:]
        previous = _route_systems[index].casefold()
        start = folded.index(previous) if previous in folded and folded.index(previous) <= current else None
        if start is not None:
            return current - start, len(left_names), names[start + 1:current + 1], left_names
        done = min(_leg_jumps, leg_length)
        return done, len(left_names), (_trail[-done:] if done else []), left_names
    done = min(_leg_jumps, leg_length)
    return done, max(0, leg_length - done), (_trail[-done:] if done else []), []


def _jump_counts() -> tuple[int, int]:
    """Real jumps made and still to make along the whole route (not waypoints). The plotter says how many jumps
    each leg takes; the leg in progress is read from your own jumps and the game's route, so the numbers move with
    every jump, not only when you reach a neutron star."""
    if not _route_systems:
        return 0, 0
    legs = _route_legs if len(_route_legs) == len(_route_systems) else [0] + [1] * (len(_route_systems) - 1)
    index = max(0, _route_index)
    done_in_leg, left_in_leg, _, _ = _leg_view()
    return sum(legs[1:index + 1]) + done_in_leg, left_in_leg + sum(legs[index + 2:])


def _note_jump(system: str) -> None:
    """Record a jump made while a route is loaded (for the Done list and the jumps-in-this-leg count)."""
    global _leg_jumps
    if _trail and _trail[-1].casefold() == system.casefold():
        return
    _trail.append(system)
    del _trail[:-300]
    reached = _find_system_index(system, _route_systems, _route_index)
    if reached > _route_index or (_current_system() or "").casefold() == system.casefold():
        _leg_jumps = 0                          # arrived at a waypoint: a new leg begins
    else:
        _leg_jumps += 1


NEUTRON_KINDS = ("neutron", "trip")      # routes whose waypoints are neutron stars (the stops you entered are not)


def _neutrons_ahead() -> list[str]:
    """The boost stars still ahead on a neutron route or trip: neutron stars, and white dwarfs (they boost too, by less). The
    game's own route says which stars they are where it has one (LHS 483 can be a white dwarf in the middle of a leg). A
    waypoint the game says nothing about counts as a neutron, except the destination and the stops you entered (Sol, say)."""
    if not _route_systems:
        return []
    major, last = _major_names(), len(_route_systems) - 1
    waypoint = {name.casefold(): index for index, name in enumerate(_route_systems)}
    found = []
    for name in _remaining_systems():
        star = _star_class_of(name)
        index = waypoint.get(name.casefold())
        if star:
            if star[:1] in ("N", "D"):
                found.append(name)
        elif index is not None and index > _route_index and index != last and name.casefold() not in major:
            found.append(name)
    return found


def _next_neutron_text() -> str:
    """The Next Neutron line's value: the system, and (D) after it when that star is a white dwarf."""
    name = _next_neutron_system()
    if not name:
        return "—"
    return name + (" (D)" if _star_class_of(name)[:1] == "D" else "")

def _next_neutron_system() -> str | None:
    """The line under Next Jump: the next neutron where the route has them, else simply the next waypoint."""
    if _route_kind in NEUTRON_KINDS:
        ahead = _neutrons_ahead()
        return ahead[0] if ahead else None
    return _next_system()


def _waypoints_left_text() -> str:
    """\" (4 neutrons)\" after the jumps left, only when the waypoints differ from the jumps."""
    _, jumps_left = _jump_counts()
    waypoints_left = len(_neutrons_ahead()) if _route_kind in NEUTRON_KINDS else _waypoint_counts()[1]
    if not _route_systems or waypoints_left == jumps_left:
        return ""
    word = _waypoint_word()
    label = "N" if word == "Neutron" else f"{word}s"      # N is the suite's short form for neutrons
    return f" ({label}: {waypoints_left})"          # same shape as "Left: 5": a label, a colon, a number


def _tab_label(name: str) -> str:
    return name


def _visible_tabs() -> list[str]:
    return [name for name in TABS if name not in OPTIONAL_TABS or _settings.get(OPTIONAL_TABS[name])]


def _current_tab() -> str:
    tab, visible = _settings.get("tab"), _visible_tabs()
    return tab if tab in visible else visible[0]


def _select_tab(name: str) -> None:
    if name in _visible_tabs():
        _settings["tab"] = name
        _save_settings()
        _refresh_route_label()
        _theme_event()


def _fit_tab_font(width: int):
    """The tab row's font: the header's own, made smaller only as far as needed for every tab to fit."""
    try:
        base = tkfont.Font(font=_title_label.cget("font"))
    except (tk.TclError, AttributeError):
        return None
    labels = [_tab_label(name) for name in _visible_tabs()]
    padding = 16 * len(labels) + 12       # cell gaps, label padding and borders
    size = int(base.cget("size"))
    pixels = abs(size) if size < 0 else round(size * float(_app_frame.tk.call("tk", "scaling")))
    fitted = tkfont.Font(font=base)
    for step in range(max(1, pixels), 5, -1):
        fitted.configure(size=-step)
        if sum(fitted.measure(name) for name in labels) + padding <= max(1, width - 2):
            break
    return fitted


def _refresh_tabs(background, highlight) -> None:
    """Tabs are clickable (Highlighted Text); the chosen one is underlined. Hidden ones leave no gap."""
    global _tab_font
    if _tab_row is None or not _widget_alive(_tab_row):
        return
    collapsed = bool(_settings.get("collapsed"))
    _tab_row.grid_remove() if collapsed else _tab_row.grid()
    visible = _visible_tabs()
    width = _app_frame.winfo_width()
    if width <= 1:
        width = _app_frame.master.winfo_width() if _app_frame.master is not None else 1
    _tab_font = _fit_tab_font(width)           # kept in a global so Tk does not drop the font
    for name, (label, line) in _tab_widgets.items():
        cell = label.master
        cell.grid() if name in visible else cell.grid_remove()
        label.configure(text=_tab_label(name), foreground=highlight, background=background)
        if _tab_font is not None:
            label.configure(font=_tab_font)
        line.configure(background=background)
        line.delete("all")
        if name == _current_tab():
            line.create_rectangle(0, 0, max(1, label.winfo_reqwidth()), 2, fill=highlight, outline=highlight)


def _refresh_route_label() -> None:
    if _title_label is not None and not _widget_alive(_title_label):
        return      # the panel was never built (or EDMC has destroyed it)
    current, next_system, end = _current_system(), _next_system(), _end_system()
    done, left = _jump_counts()
    if _title_label is not None:
        _title_label.configure(text=HEADER + " (Hidden)" if _settings.get("collapsed") else HEADER)
    _update_header_spacing()
    _refresh_position()
    _refresh_scan()
    for name, frame in _tab_pages.items():
        if _widget_alive(frame):
            frame.grid() if name == _current_tab() and not _settings.get("collapsed") else frame.grid_remove()
    if _tab_row is not None and _widget_alive(_tab_row):
        normal, highlight, background = _palette()
        _refresh_tabs(background, highlight)
    show = bool(_route_systems) and not _settings.get("collapsed")
    for widget in _route_rows:
        if show:
            widget.grid()
        else:
            widget.grid_remove()
    if _collapse_button is not None:          # always there: the tabs and shortcut bar fold away with or without a route
        _collapse_button["text"] = "🔽" if _settings.get("collapsed") else "🔼"
        _collapse_button.grid()
    if _current_label is not None:
        _current_label.configure(text=f"Current: {current or '—'}")
        _jump_label.configure(text=f"Next Jump: {_next_jump_system() or '—'}")
        _next_label.configure(text=f"Next {_waypoint_word()}: {_next_neutron_text() if _route_kind in NEUTRON_KINDS else (next_system or '—')}")
        if _route_kind == "carrier":                 # a carrier's waypoints are its jumps: one line says it
            _jump_label.master.grid_remove()
        _end_label.configure(text=f"End: {end or '—'}")
        _done_label.configure(text=f": {done}{SEP}")
        _left_label.configure(text=f": {left}")
        if _left_extra is not None:
            _left_extra.configure(text=_waypoints_left_text(), foreground=_status_colours().get("info", "#4da6ff"))
    _refresh_parked()
    _refresh_expedition()
    _refresh_missions()
    _sync_shortcuts()
    if _mode_button is not None:
        # The copy/auto toggle only shows while there is a route (the collapse button is always there).
        _mode_button.navigator_hidden = not _route_systems
        _interface("navigator_sync_mode_buttons")
    _sync_header_buttons()


def _sync_route_snapshot() -> None:
    done, left = _jump_counts()
    _snapshot["route"] = {
        "loaded": bool(_route_systems), "waypoints_total": len(_route_systems),
        "current_index": _route_index, "current_system": _current_system(),
        "next_system": _next_system(), "end_system": _end_system(),
        "jumps_done": done, "jumps_left": left,
        "waypoints_left": _waypoint_counts()[1],
    }


def _persist_route() -> None:
    _write_json(ROUTE_PATH, {"schema_version": 3, "systems": _route_systems, "current_index": _route_index,
                             "kind": _route_kind, "bodies": _route_bodies, "legs": _route_legs,
                             "trail": _trail[-300:], "leg_jumps": _leg_jumps})


def _load_saved_route() -> None:
    global _route_systems, _route_index, _route_kind, _route_bodies, _route_legs, _trail, _leg_jumps
    try:
        with open(ROUTE_PATH, encoding="utf-8-sig") as stream:
            saved = json.load(stream)
        systems = saved.get("systems", [])
        if not isinstance(systems, list) or not all(isinstance(name, str) and name.strip() for name in systems):
            raise ValueError("Saved route contains invalid system names.")
        index = int(saved.get("current_index", 0))
        _route_systems = systems
        trail = saved.get("trail")
        _trail = [n for n in trail if isinstance(n, str)] if isinstance(trail, list) else []
        try:
            _leg_jumps = max(0, int(saved.get("leg_jumps", 0)))
        except (TypeError, ValueError):
            _leg_jumps = 0
        legs = saved.get("legs")
        _route_legs = ([max(0, int(n)) for n in legs] if isinstance(legs, list) and len(legs) == len(systems)
                       and all(isinstance(n, (int, float)) for n in legs) else [])
        _route_kind = saved.get("kind") if saved.get("kind") in ROUTE_KINDS else "neutron"
        bodies = saved.get("bodies")
        _route_bodies = bodies if isinstance(bodies, dict) else {}
        # With no reached stop yet, the first CSV system is the route's join point.
        _route_index = max(0, min(index, len(systems) - 1)) if systems else -1
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError, AttributeError):
        logger.exception("Could not restore neutron route")


_saved_key: str | None = None


def _save(changed_only: bool = False, refresh: bool = True) -> None:
    """Refresh the panel and write the status snapshot.

    Journal and cockpit-status updates pass changed_only=True: the snapshot file
    is then rewritten (and the panel redrawn) only when location, ship or route
    actually changed, not on every event or Status.json tick.
    """
    global _saved_key
    _sync_route_snapshot()
    key = json.dumps({k: v for k, v in _snapshot.items()
                      if k not in ("updated_at_utc", "last_journal_event", "cockpit")},
                     sort_keys=True, default=str)
    if changed_only and key == _saved_key:
        return
    _saved_key = key
    if refresh:
        _refresh_route_label()
    _snapshot["updated_at_utc"] = _utc_now()
    try:
        _write_json(STATE_PATH, _snapshot)
    except Exception:
        logger.exception("Could not save neutron route snapshot")


def _copy_system(system: str | None) -> None:
    if system and _app_frame is not None:
        try:
            _app_frame.clipboard_clear()
            _app_frame.clipboard_append(system)
            _app_frame.update_idletasks()
        except tk.TclError:
            logger.exception("Could not copy route system")


def _copy_next_waypoint() -> None:
    _copy_system(_next_system())


def _copy_current_waypoint() -> None:
    # Copy the most recently reached route system, retained during a fuel detour.
    _copy_system(_current_system())


def _copy_clicked(getter) -> None:
    system = getter()
    _copy_system(system)
    if system:
        _set_status(f"Copied: {system}")


def _read_route_csv(path: str) -> list[str]:
    return _read_route_csv_with_jumps(path)[0]


def _read_route_csv_with_jumps(path: str) -> tuple[list[str], list[int]]:
    """System names, plus the plotter's jumps per leg when the CSV has a Jumps column (else empty)."""
    with open(path, encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        normalized = {re.sub(r"[^a-z0-9]", "", name.lower()): name
                      for name in (reader.fieldnames or []) if name}
        column = next((normalized[key] for key in ("systemname", "system", "starsystem", "waypoint")
                       if key in normalized), None)
        if column is None:
            raise ValueError("The CSV needs a System Name, System, StarSystem, or Waypoint column.")
        jumps_column = normalized.get("jumps")
        names, legs = [], []
        for row in reader:
            name = (row.get(column) or "").strip()
            if not name:
                continue
            names.append(name)
            try:
                legs.append(max(0, int(float(row.get(jumps_column) or 0))) if jumps_column else 1)
            except ValueError:
                legs.append(1)
    systems = names
    if not systems:
        raise ValueError("The route contains no system names.")
    if jumps_column:
        legs[0] = 0                                  # the first system is where the route starts
    return systems, (legs if jumps_column else [])


def _find_system_index(current_system: str | None, systems: list[str], after: int) -> int:
    if current_system:
        for index in range(max(0, after + 1), len(systems)):
            if systems[index].casefold() == current_system.casefold():
                return index
    return after


def _set_route(systems: list[str], live_system: str | None, kind: str = "neutron",
               bodies: dict[str, list[dict[str, Any]]] | None = None, legs: list[int] | None = None,
               source: str = "", major: list[str] | None = None) -> None:
    global _route_systems, _route_index, _pace_anchor, _route_kind, _route_bodies, _route_legs, _leg_jumps
    _trail.clear()
    _leg_jumps = 0
    _route_kind, _route_bodies = kind, dict(bodies or {})
    _settings["route_source"] = source
    _settings["route_major"] = [str(name) for name in (major or [])]
    _route_legs = ([max(0, int(n)) for n in legs] if legs and len(legs) == len(systems) else [])
    if _route_legs:
        _route_legs[0] = 0
    _pace_anchor = None
    _pace_samples.clear()
    _route_systems = list(systems)
    matched = _find_system_index(live_system, systems, -1)
    _route_index = max(0, matched) if systems else -1
    _persist_route()
    _save()


def _load_route_dialog() -> None:
    path = filedialog.askopenfilename(title="Load Route", parent=_app_frame,
                                     filetypes=(("CSV route", "*.csv"), ("All files", "*.*")))
    if not path:
        return
    try:
        systems, legs = _read_route_csv_with_jumps(path)
        _set_route(systems, _snapshot.get("location", {}).get("system_name"), legs=legs)
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        logger.exception("Could not load neutron route")
        messagebox.showerror("Load Route", str(error), parent=_app_frame)


def _clear_route() -> None:
    """Forget the loaded route (no question asked)."""
    global _route_systems, _route_index, _route_kind, _route_bodies, _route_legs, _leg_jumps
    _route_systems = []
    _route_legs = []
    _trail.clear()
    _leg_jumps = 0
    _route_index = -1
    _route_kind, _route_bodies = "neutron", {}
    _settings["route_major"] = []
    _save()


LONG_PLOT_STOPS = 4        # this many stops or more: say it will take a while


def _long_plot_notice(count: int, parent=None) -> bool:
    """Many stops are plotted one leg at a time, so it can take minutes (40 stops took about 4.5). Say so before it starts,
    with a tick box to stop showing it. True = go ahead, False = cancelled."""
    if count < LONG_PLOT_STOPS or _settings.get("hide_long_plot_notice"):
        return True
    parent = parent or _app_frame
    window = tk.Toplevel(parent)
    window.title("This Takes a While")
    _attach_popup(window, "long_plot")
    try:
        window.transient(parent.winfo_toplevel())
    except tk.TclError:
        pass
    answer = {"go": False}
    hide_var = tk.BooleanVar(window, value=False)
    buttons = tk.Frame(window)
    buttons.pack(side=tk.BOTTOM, pady=(4, 10))             # first in the pack order: never squeezed out
    body = tk.Frame(window)
    body.pack(fill=tk.BOTH, expand=True, padx=14, pady=(12, 0))
    tk.Label(body, justify=tk.LEFT, anchor=tk.W, wraplength=360, text=(
        "Plotting long routes with many stops can take a while, depending on your computer and the number of stops.\n\n"
        "Please wait and do not close EDMC until the route appears.")).pack(anchor=tk.W)
    tk.Checkbutton(body, text="Do not show this again", variable=hide_var, anchor=tk.W).pack(anchor=tk.W, pady=(10, 0))

    def finish(go: bool) -> None:
        answer["go"] = go
        if hide_var.get():
            _settings["hide_long_plot_notice"] = True
            _save_settings()
        window.destroy()

    ttk.Button(buttons, text="Plot", width=10, command=lambda: finish(True)).pack(side=tk.LEFT, padx=6)
    ttk.Button(buttons, text="Cancel", width=10, command=lambda: finish(False)).pack(side=tk.LEFT, padx=6)
    window.protocol("WM_DELETE_WINDOW", lambda: finish(False))
    _fit_window(window)
    try:
        window.grab_set()
    except tk.TclError:
        pass
    window.wait_window()
    return answer["go"]


def _confirm_replace_route(parent=None) -> bool:
    """Before plotting a new route: if one is already loaded, say so and ask. True = go ahead (the old route
    is cleared), False = keep it. Plotting over a loaded route used to mix the two up."""
    if not _route_systems:
        return True
    done, left = _jump_counts()
    kind = ROUTE_TYPES[ROUTE_KINDS.index(_route_kind)] if _route_kind in ROUTE_KINDS else "route"
    answer = messagebox.askyesno(
        "Route Already Loaded",
        f"You are on a {kind} route: {_route_systems[0]} to {_end_system()}, {left} jump{'' if left == 1 else 's'} left.\n\n"
        "Clear it and plot a new route?\n\nYes: clear this route and continue.\nNo: keep this route.",
        parent=parent or _app_frame)
    if answer:
        _clear_route()
        try:
            _persist_route()
        except OSError:
            logger.exception("Could not save the cleared route")
    return bool(answer)


def _cancel_route() -> None:
    if not _route_systems or not messagebox.askyesno(
            "Cancel Route", "Cancel the current route?", parent=_app_frame):
        return
    _clear_route()
    try:
        _persist_route()
    except OSError as error:
        logger.exception("Could not save cancelled route")
        messagebox.showerror("Cancel Route", str(error), parent=_app_frame)


def _update_route_progress(current_system: str | None, on_jump: bool = False) -> bool:
    global _route_index
    if not current_system or not _route_systems:
        return False
    if on_jump:
        _note_jump(current_system)
    # Arrival at the retained waypoint refreshes the clipboard without moving
    # progress; ordinary events in that system leave the clipboard alone.
    if (_current_system() or "").casefold() == current_system.casefold():
        if on_jump:
            _copy_next_waypoint()
        return False
    index = _find_system_index(current_system, _route_systems, _route_index)
    if index <= _route_index:
        if not on_jump:
            return False
        # A jump can rejoin anywhere on the route, including an earlier stop.
        index = _find_system_index(current_system, _route_systems, -1)
        if index < 0:
            return False
    global _pace_anchor
    now = time.monotonic()
    if on_jump and index == _route_index+1 and _pace_anchor is not None:
        interval = now-_pace_anchor
        if 15 <= interval <= _idle_limit():      # longer gaps were idle time (a break), not travel
            _pace_samples.append(interval)
            del _pace_samples[:-8]
    elif index != _route_index+1:
        _pace_samples.clear()
    _pace_anchor = now if on_jump else None
    _route_index = index
    _sync_route_snapshot()
    _refresh_route_label()
    try:
        _persist_route()
    except OSError:
        logger.exception("Could not save neutron route progress")
    if _next_system():
        _copy_next_waypoint()
    return True


# ---------------------------------------------------------------------------
# In-game galaxy map automation (Windows only)
#
# Sequence: open map -> click search box -> Ctrl+V -> Enter -> (click first
# result) -> click Plot Route -> close map. Mouse targets are stored as
# fractions (0-1) of the game window's client area so they survive resolution
# changes. Use "Calibrate Clicks" once to record them on your own screen.
# Keys are sent as hardware scan codes because Elite ignores virtual-key input.
# ---------------------------------------------------------------------------
import ctypes
import xml.etree.ElementTree as ET
import sys
import threading
from ctypes import wintypes

SETTINGS_PATH = os.path.join(DATA_DIR, "automation.json")
GAME_TITLE = "Elite - Dangerous (CLIENT)"
SC_ESC, SC_ENTER, SC_CTRL, SC_A, SC_V, SC_M = 0x01, 0x1C, 0x1D, 0x1E, 0x2F, 0x32

DEFAULT_SETTINGS: dict[str, Any] = {
    "auto_route": False,
    "plot_efficiency": 70,      # Plot New Route: Spansh efficiency (%)
    "plot_type": "neutron",     # Plot New Route: last route type (neutron / riches)
    "riches_radius": 25,        # Road to Riches: search radius (ly)
    "riches_max_systems": 25,   # Road to Riches: most systems in a route
    "riches_min_value": 500000, # Road to Riches: least value per body (credits)
    "riches_max_ls": 50000,     # Road to Riches: furthest body from arrival (ls)
    "fuel_safety": "normal",    # Fuel warnings: off / relaxed / normal / cautious
    "galaxy_algorithm": "optimistic",   # Galaxy Plotter: Spansh routing method
    "parked": {},               # a route set aside for a rescue or a pause (see _park_route)
    "route_major": [],          # systems the user entered (Expedition stops, Rescue cases): marked with * in the lists
    "route_source": "",         # where the loaded route came from: "expedition", "rescue" or "" (Highway)
    "rescue": {},               # Rescue tab: {"cases": [{place, system, done}], "backup": [{place, system}]}
    "rescue_best": True,        # Rescue: Plot Route reorders the list by the most efficient route (off: plots as listed)
    "hide_long_plot_notice": False,   # the "this takes a while" notice before a many-stop plot
    "rescue_strike": True,      # Settings page: finished rescue cases are struck through (off: dimmed)
    "expedition": {},           # Expedition tab: stops (names), order ("efficient" / "entered"), loop, keep_last
    "expedition_dots": 8,       # Expedition bar: how many stops show at once (0 = all of them)
    "carrier_used": 0,          # Fleet Carrier router: tonnes of carrier space already used
    "trade_station": "",        # Trade Router: the station you start from
    "trade_capital": 1000000,   # Trade Router: credits to trade with
    "trade_cargo": 100,         # Trade Router: tonnes of cargo space
    "trade_hops": 5,            # Trade Router: most trades in the route
    "trade_ls": 1000,           # Trade Router: furthest station from its arrival star (ls)
    "show_missions_tab": True,  # Settings page: show the Missions tab
    "missions": {},             # Missions tab: your active missions by id (see _note_missions)
    "exp_stats": {},            # Expedition tab: {"ly": jumped so far, "sec": time travelled, without pauses}
    "show_rescue_tab": False,   # Settings page: show the Rescue tab (last tab, for Fuel Rats and Hull Seals)
    "show_progress_bar": True,  # Settings page: route progress bar under the Jumps line
    "eta_minutes_per_jump": 2.0,  # Settings page: ETA pace used until yours is learned (minutes)
    "saved_trips": {},          # Plot New Route > Multi-Stop Trip: saved stop lists, by name
    "plot_last_end": "",        # Plot New Route: last End System, remembered
    "tab": "Highway",   # which tab under the header is showing
    "collapsed": False,         # route lines folded away under the header (arrow button)
    "shortcuts_on": False,      # Settings page: show the shortcut bar under the header
    "shortcuts_hidden": False,  # the S button: the bar folded away (the right-hand arrow hides everything)
    "shortcut_count": 3,        # Settings page: how many shortcut buttons (3, 4 or 5)
    "shortcuts": [],            # Settings page: [{"name", "target"}] per button, as typed (up to 5 are kept)
    "map_scancode": SC_M,       # your Galaxy Map binding (default M)
    "settings_version": 7,
    "map_modifiers": [],        # modifier scan codes held with the map key (from your binds)
    "map_key_name": "M",        # display name of the map key
    "binds_path": "",           # set when you pick a bindings file by hand
    "esc_presses": 3,           # max Esc presses to back out of the map (stops early once closed)
    "esc_gap": 0.8,             # seconds between Esc presses
    "calibrate_countdown": 15,  # seconds per step of Calibrate Routing / Jet-Cone Clicks
    # Fractions of the game client area. THESE ARE GUESSES - run Calibrate Clicks.
    "search_box": [0.17, 0.12],
    "first_result": [0.17, 0.20],   # set to null in automation.json to skip
    "plot_button": [0.80, 0.82],
    "jetcone_tab": None,        # route-settings panel tab (set by Calibrate Jet-Cone Clicks)
    "jetcone_toggle": None,     # jet-cone boost toggle in that panel
    "map_open_delay": 2.0,
    "step_delay": 0.8,
    "supercharge_delay": 5.0,   # seconds to wait after JetConeBoost before opening the map
    "plot_route_delay": 1.0,    # extra wait after the Plot Route click (long plots need time)
    "click_extra_delay": 0.5,   # extra pause after every click
    "map_scroll_delay": 2.0,    # extra wait after selecting the system, while the map pans
    "input_method": "paste",    # "paste" (Ctrl+V, worked in testing) or "type" (key by key)
    "type_delay": 0.05,         # seconds per key while typing
}
_settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
_plot_lock = threading.Lock()
_user32 = ctypes.windll.user32 if sys.platform == "win32" else None
_status_label = None
_cog_button = None
_auto_var = None
_pending_upgrade: list[bool] = []
_cal: dict[str, Any] = {"step": 0, "left": 0, "ready": False, "error": "", "missed": [], "steps": ()}
_CAL_STEPS = (
    ("search_box", "Hover over the SEARCH BOX"),
    ("first_result", "Search a system, then hover over the first RESULT"),
    ("plot_button", "Click that result, then hover over PLOT ROUTE"),
)
_JETCONE_STEPS = (
    ("jetcone_tab", "Hover over the ROUTE SETTINGS panel tab"),
    ("jetcone_toggle", "Click that tab, then hover over the JET-CONE BOOST toggle (don't click it)"),
)

if _user32 is not None:
    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    _user32.GetKeyboardLayout.restype = ctypes.c_void_p
    _user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
    _user32.VkKeyScanExW.restype = ctypes.c_short
    _user32.VkKeyScanExW.argtypes = [wintypes.WCHAR, ctypes.c_void_p]
    _user32.MapVirtualKeyExW.restype = wintypes.UINT
    _user32.MapVirtualKeyExW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p]


def _set_status(text: str) -> None:
    if _status_label is None or _app_frame is None:
        return

    def apply() -> None:
        if text:
            _status_label.configure(text=text)
            _status_label.grid()
            # Clear it later unless something newer replaced it.
            failed = text.startswith("Plot Failed")
            _status_label.configure(cursor="hand2" if failed else "",foreground=_palette()[1] if failed else _palette()[0])
            if failed:
                _status_label.bind("<Button-1>",lambda e:_start_plot())
                _status_label.configure(foreground=_palette()[1])
            else:
                _status_label.unbind("<Button-1>")
                _app_frame.after(8000, lambda: _status_label.winfo_exists() and _status_label.cget("text") == text and _set_status(""))
        else:
            _status_label.grid_remove()

    try:
        _app_frame.after(0, apply)
    except (RuntimeError, tk.TclError):
        pass


def _load_settings() -> None:
    _settings.clear()
    _settings.update(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, encoding="utf-8-sig") as stream:
            saved = json.load(stream)
        if isinstance(saved, dict):
            if "auto_plot" in saved and "auto_route" not in saved:   # renamed in 0.7.4
                saved["auto_route"] = saved["auto_plot"]
                _pending_upgrade.append(True)
            _settings.update({k: v for k, v in saved.items() if k in DEFAULT_SETTINGS})
            if set(saved) - set(DEFAULT_SETTINGS):
                _pending_upgrade.append(True)   # rewrite without options this edition does not have
            if int(saved.get("settings_version", 1)) < 3:
                # v3: Esc-based close and a longer post-supercharge delay
                _settings["supercharge_delay"] = DEFAULT_SETTINGS["supercharge_delay"]
                _settings["settings_version"] = 3
                _pending_upgrade.append(True)
            if int(saved.get("settings_version", 1)) < 5:
                # v5: 15-second calibration steps (custom values are kept)
                if int(saved.get("calibrate_countdown", 10)) == 10:
                    _settings["calibrate_countdown"] = DEFAULT_SETTINGS["calibrate_countdown"]
                _settings["settings_version"] = 5
                _pending_upgrade.append(True)
            if int(saved.get("settings_version", 1)) < 6:
                # v6: one more second for the map to pan before Plot Route (custom values kept)
                if float(saved.get("map_scroll_delay", 1.0)) == 1.0:
                    _settings["map_scroll_delay"] = DEFAULT_SETTINGS["map_scroll_delay"]
                _settings["settings_version"] = 6
                _pending_upgrade.append(True)
            if int(saved.get("settings_version", 1)) < 7:
                # v7: the Missions tab exists now, so it shows (it can be switched off in Settings)
                _settings["show_missions_tab"] = True
                _settings["settings_version"] = 7
                _pending_upgrade.append(True)
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        logger.exception("Could not read automation settings")


def _save_settings() -> bool:
    if _auto_var is not None:
        _settings["auto_route"] = bool(_auto_var.get())
    try:
        _write_json(SETTINGS_PATH, _settings)
        logger.info("Saved automation settings to %s", SETTINGS_PATH)
        return True
    except Exception:
        logger.exception("Could not save automation settings to %s", SETTINGS_PATH)
        _set_status("Could not save settings - see EDMC log.")
        return False


def _open_data_folder() -> None:
    try:
        os.startfile(DATA_DIR)  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        logger.exception("Could not open data folder")
        _set_status(f"Folder: {DATA_DIR}")


def _send(inputs: list) -> None:
    array = (_INPUT * len(inputs))(*inputs)
    _user32.SendInput(len(inputs), array, ctypes.sizeof(_INPUT))


def _key_event(scan: int, up: bool) -> Any:
    flags = 0x0008 | (0x0002 if up else 0)  # KEYEVENTF_SCANCODE [| KEYUP]
    return _INPUT(1, _INPUTUNION(ki=_KEYBDINPUT(0, scan, flags, 0, 0)))


def _tap(scan: int, hold: float = 0.07, gap: float = 0.08) -> None:
    _send([_key_event(scan, False)])
    time.sleep(hold)
    _send([_key_event(scan, True)])
    time.sleep(gap)


def _type_text(text: str, delay: float) -> None:
    """Type text key by key, using the active keyboard layout's scan codes."""
    layout = _user32.GetKeyboardLayout(0)
    for char in text:
        result = _user32.VkKeyScanExW(char, layout)
        if result == -1:
            logger.warning("No key for character %r; skipped", char)
            continue
        vk, shift = result & 0xFF, bool(result & 0x100)
        scan = _user32.MapVirtualKeyExW(vk, 0, layout)  # MAPVK_VK_TO_VSC
        if shift:
            _send([_key_event(0x2A, False)])
            time.sleep(0.03)
        _tap(scan, hold=delay, gap=delay)
        if shift:
            _send([_key_event(0x2A, True)])
            time.sleep(0.03)


_KEY_SCANCODES: dict[str, int] = {
    "escape": 0x01, "minus": 0x0C, "equals": 0x0D, "backspace": 0x0E, "tab": 0x0F,
    "leftbracket": 0x1A, "rightbracket": 0x1B, "enter": 0x1C, "leftcontrol": 0x1D,
    "semicolon": 0x27, "apostrophe": 0x28, "grave": 0x29, "leftshift": 0x2A,
    "backslash": 0x2B, "comma": 0x33, "period": 0x34, "slash": 0x35, "rightshift": 0x36,
    "leftalt": 0x38, "space": 0x39,
}
for _i, _c in enumerate("qwertyuiop"):
    _KEY_SCANCODES[_c] = 0x10 + _i
for _i, _c in enumerate("asdfghjkl"):
    _KEY_SCANCODES[_c] = 0x1E + _i
for _i, _c in enumerate("zxcvbnm"):
    _KEY_SCANCODES[_c] = 0x2C + _i
for _i, _c in enumerate("1234567890"):
    _KEY_SCANCODES[_c] = 0x02 + _i
for _i in range(1, 11):
    _KEY_SCANCODES[f"f{_i}"] = 0x3A + _i
_KEY_SCANCODES.update({"f11": 0x57, "f12": 0x58})
for _name, _code in (("7", 0x47), ("8", 0x48), ("9", 0x49), ("4", 0x4B), ("5", 0x4C),
                     ("6", 0x4D), ("1", 0x4F), ("2", 0x50), ("3", 0x51), ("0", 0x52)):
    _KEY_SCANCODES[f"numpad{_name}"] = _code


def _bindings_dir() -> str:
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                        "Frontier Developments", "Elite Dangerous", "Options", "Bindings")


def _key_scancode(name: str) -> int | None:
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    key = key[3:] if key.startswith("key") else key
    return _KEY_SCANCODES.get(key)


def _parse_map_binding(path: str) -> tuple[int, list[int], str] | None:
    """Read the Galaxy Map keyboard binding from an Elite .binds file."""
    return _parse_binding(path, ("GalaxyMapOpen",))


def _parse_binding(path: str, controls: tuple[str, ...]) -> tuple[int, list[int], str] | None:
    """First keyboard binding found for the given controls in an Elite .binds file."""
    root = ET.parse(path).getroot()
    for control in controls:
        result = _keyboard_binding(root.find(control))
        if result is not None:
            return result
    return None


def _keyboard_binding(node: Any) -> tuple[int, list[int], str] | None:
    if node is None:
        return None
    for slot in ("Primary", "Secondary"):
        binding = node.find(slot)
        if binding is None or binding.get("Device") != "Keyboard":
            continue
        scan = _key_scancode(binding.get("Key", ""))
        modifiers: list[int] | None = []
        names: list[str] = []
        for modifier in binding.findall("Modifier"):
            code = _key_scancode(modifier.get("Key", "")) if modifier.get("Device") == "Keyboard" else None
            if code is None:
                modifiers = None
                break
            modifiers.append(code)
            names.append(modifier.get("Key", "").replace("Key_", ""))
        if scan is None or modifiers is None:
            continue
        names.append(binding.get("Key", "").replace("Key_", ""))
        return scan, modifiers, "+".join(names)
    return None


def _find_binds_file() -> str | None:
    base = _bindings_dir()
    if not os.path.isdir(base):
        return None
    try:
        with open(os.path.join(base, "StartPreset.start"), encoding="utf-8-sig") as stream:
            preset = next((line.strip() for line in stream if line.strip()), "")
    except OSError:
        preset = ""
    for name in (f"{preset}.4.0.binds", f"{preset}.3.0.binds", f"{preset}.binds"):
        candidate = os.path.join(base, name)
        if preset and os.path.isfile(candidate):
            return candidate
    files = [os.path.join(base, f) for f in os.listdir(base) if f.lower().endswith(".binds")]
    return max(files, key=os.path.getmtime) if files else None


def _apply_binds(path: str) -> str | None:
    """Apply the Galaxy Map key from a binds file.
    Returns the map key's display name, or None if the map key isn't bound."""
    result = _parse_map_binding(path)
    if result is None:
        return None
    scan, modifiers, name = result
    _settings.update({"map_scancode": scan, "map_modifiers": modifiers, "map_key_name": name})
    return name


def _refresh_keybinding() -> None:
    """At startup, pick up the Galaxy Map key from the player's binds automatically."""
    path = _settings.get("binds_path") or _find_binds_file()
    if not path or not os.path.isfile(path):
        return
    try:
        keys = ("map_scancode", "map_modifiers")
        before = tuple(_settings.get(key) for key in keys)
        name = _apply_binds(path)
        if name and before != tuple(_settings.get(key) for key in keys):
            logger.info("Keys from %s: galaxy map %s", path, name)
            _save_settings()
    except (OSError, ET.ParseError):
        logger.exception("Could not read keybindings from %s", path)


def _load_binds_dialog() -> None:
    base = _bindings_dir()
    path = filedialog.askopenfilename(
        title="Load Keybindings", parent=_app_frame,
        initialdir=base if os.path.isdir(base) else None,
        filetypes=(("Elite bindings", "*.binds"), ("All files", "*.*")))
    if not path:
        return
    try:
        name = _apply_binds(path)
    except (OSError, ET.ParseError) as error:
        logger.exception("Could not read keybindings")
        messagebox.showerror("Load Keybindings", f"Could not read that file: {error}", parent=_app_frame)
        return
    if name is None:
        messagebox.showerror("Load Keybindings",
                             "No keyboard binding for the Galaxy Map was found in that file.",
                             parent=_app_frame)
        return
    _settings["binds_path"] = path
    if _save_settings():
        _set_status(f"Galaxy map key: {name}")


def _set_autoroute_delay() -> None:
    current = float(_settings.get("supercharge_delay", 5.0))
    value = simpledialog.askfloat(
        "Auto-Route Delay", "Seconds to wait after a supercharge before the map opens:",
        parent=_app_frame, initialvalue=current, minvalue=0.0, maxvalue=60.0)
    if value is None:
        return
    _settings["supercharge_delay"] = round(value, 2)
    if _save_settings():
        _set_status(f"Auto-route delay: {value:g}s")


def _press_combo(scancode: int, modifiers: list) -> None:
    held = [int(code) for code in modifiers or []]
    for code in held:
        _send([_key_event(code, False)])
        time.sleep(0.05)
    _tap(int(scancode))
    for code in reversed(held):
        _send([_key_event(code, True)])
        time.sleep(0.05)


def _press_map_key() -> None:
    _press_combo(_settings["map_scancode"], _settings.get("map_modifiers"))


ABOUT_TEXT = (
    "Plugin coded collaboratively with Claude, ChatGPT and Gemini by Commander Thalinor.\n"
    "\n"
    "Elite Dangerous Commander Name: Thalinor\n"
    "eMail: thalinor @ gmail.com\n"
    "\n"
    "You can use this plugin freely for your own personal, non-commercial use. "
    "You can distribute it freely as long as the code has not been modified and you do "
    "not claim it's your own work. You may NOT sell this plugin, use this plugin for "
    "commercial use, or use its code in your projects without prior authorization.\n"
    "\n"
    "Plot New Route uses Spansh's plotters (spansh.co.uk) - thank you, CMDR Spansh.\n"
    "Galaxy Plotter FSD stats: coriolis-data (EDCD). Game data (c) Frontier Developments plc.\n"
    "\n"
    "Human + AI = Future"
)


def _show_about() -> None:
    """About box. An internal build shows its banner in bold at the top."""
    window = tk.Toplevel(_app_frame)
    window.title(f"About {TITLE}")
    _attach_popup(window, "about")
    try:
        window.transient(_app_frame.winfo_toplevel())
    except tk.TclError:
        pass
    ok = ttk.Button(window, text="OK", width=12, command=window.destroy)
    ok.pack(side=tk.BOTTOM, pady=(0, 12))               # first in the pack order: never squeezed out
    body = tk.Frame(window, padx=16, pady=12)
    body.pack(fill=tk.BOTH, expand=True)
    bold = tkfont.nametofont("TkDefaultFont").copy()
    bold.configure(weight="bold")
    window._bold_font = bold                    # keep the font alive with the window
    if INTERNAL_BANNER:
        tk.Label(body, text=INTERNAL_BANNER, font=bold, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 8))
    tk.Label(body, text=f"{TITLE}  -  version {VERSION}", justify=tk.LEFT).pack(anchor=tk.W)
    tk.Label(body, text=ABOUT_TEXT, justify=tk.LEFT, wraplength=440).pack(anchor=tk.W, pady=(8, 0))
    ok.focus_set()
    for sequence in ("<Return>", "<Escape>"):
        window.bind(sequence, lambda _event: window.destroy())
    _fit_window(window)


def _fill_menu(menu: tk.Menu, items) -> None:
    """items: (label, command, enabled), None for a separator."""
    for item in items:
        if item is None:
            menu.add_separator()
        else:
            menu.add_command(label=item[0], command=item[1], state=tk.NORMAL if item[2] else tk.DISABLED)


def _rescue_menu_items() -> list[tuple[str, Any, bool] | None]:
    return [("Add Rescue Cases…", _open_rescue_editor, True),
            ("Show Cases…", _open_cases_window, bool(_cases())),
            ("Case Done", _rescue_case_done, bool(_open_cases()))]


def _show_settings_menu() -> None:
    """The one Navigation menu (the header, or the cog). Highway's items are at the top as they always were; Expedition and
    Rescue have their own drop-downs below, so every plotting action is in one place and the tabs stay plain data."""
    menu = tk.Menu(_app_frame, tearoff=0)
    menu.add_command(label="Plot New Route…", command=_open_plot_popup)
    menu.add_separator()
    menu.add_command(label="Load Route", command=_load_route_dialog)
    menu.add_command(label="Cancel Route", command=_cancel_route,
                     state=tk.NORMAL if _route_systems else tk.DISABLED)
    _add_fuel_menu(menu)
    menu.add_separator()
    menu.add_command(label="Toggle Jet-Cone Routing", command=_start_jetcone_toggle)
    menu.add_separator()                          # Train Map Clicks lives in Settings (N) Interface, not here
    expedition = tk.Menu(menu, tearoff=0)
    _fill_menu(expedition, _expedition_menu_items())
    menu.add_cascade(label="Expedition", menu=expedition)
    submenus = [expedition]
    if _settings.get("show_missions_tab"):
        missions = tk.Menu(menu, tearoff=0)
        _fill_menu(missions, _missions_menu_items())
        menu.add_cascade(label="Missions", menu=missions)
        submenus.append(missions)
    if _settings.get("show_rescue_tab"):
        rescue = tk.Menu(menu, tearoff=0)
        _fill_menu(rescue, _rescue_menu_items())
        menu.add_cascade(label="Rescue", menu=rescue)
        submenus.append(rescue)
    for sub in submenus:
        _interface("navigator_style_menu", sub)
    _interface("navigator_style_menu", menu)      # dark/transparent themes: no white menu
    try:
        anchor = _cog_button if (_cog_button is not None and _cog_button.winfo_manager()) else _title_label
        menu.tk_popup(anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height())
    finally:
        menu.grab_release()


def _interface(function: str, *args: Any) -> Any:
    """Call a shared (N) Interface service; None when Interface is not loaded or not ready."""
    try:
        from plug import invoke
        return invoke("(N) Interface", "Navigator Interface", function, *args)
    except Exception:
        logger.debug("Interface service %s unavailable", function, exc_info=True)
        return None


def _cartography(function: str, *args: Any) -> Any:
    """Call a service of (N) Cartography; None when it is not loaded or has nothing to say."""
    try:
        from plug import invoke
        return invoke("(N) Cartography", None, function, *args)
    except Exception:
        logger.debug("Cartography service %s unavailable", function, exc_info=True)
        return None


def _waypoint_clicked(getter) -> None:
    """A clicked Current/Next/End name: copy it, or (header button on auto) plot a route to it in the
    galaxy map, as (N) Interface decides."""
    _goto_name(getter())


def _goto_name(system: str | None) -> None:
    """Copy a name, or (header button on auto) plot a route to it in the galaxy map: what a click on a waypoint
    does, and what a shortcut button does."""
    if not system:
        return
    result = _interface("navigator_goto", system, FOLDER, False)
    if result == "mapped":
        _set_status(f"Plotting {system} in the galaxy map…")
    elif result == "copied-untrained":
        _set_status(f"Copied: {system} (train the map clicks to plot it)")
    else:
        _copy_clicked(lambda: system)          # copied by Interface, or Interface is not available


def _open_training() -> None:
    """Map click training now lives in (N) Interface and is shared by every plugin."""
    try:
        from plug import invoke
        window = invoke("(N) Interface", "Navigator Interface", "navigator_open_training", _app_frame)
    except ImportError:
        window = None
    if window is None:
        _set_status("Map training needs (N) Interface turned on.")


def _sync_map_points() -> None:
    """Use the map key and click positions trained in (N) Interface's shared training window."""
    try:
        from plug import invoke
        shared = invoke("(N) Interface", "Navigator Interface", "navigator_map_settings")
    except ImportError:
        return
    if not isinstance(shared, dict):
        return
    for key in ("map_scancode", "map_modifiers", "map_key_name"):
        if key in shared:
            _settings[key] = shared[key]
    trained = set(shared.get("trained") or [])
    for key in ("search_box", "first_result", "plot_button", "jetcone_tab", "jetcone_toggle"):
        if key in trained and shared.get(key):
            _settings[key] = shared[key]


def _chord(modifier: int, scan: int) -> None:
    _send([_key_event(modifier, False)])
    time.sleep(0.08)
    _tap(scan)
    _send([_key_event(modifier, True)])
    time.sleep(0.08)


def _find_game() -> int:
    return int(_user32.FindWindowW(None, GAME_TITLE) or 0) if _user32 else 0


def _client_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect, origin = wintypes.RECT(), wintypes.POINT(0, 0)
    _user32.GetClientRect(hwnd, ctypes.byref(rect))
    _user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top


def _focus_game(hwnd: int) -> bool:
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    _user32.SetForegroundWindow(hwnd)
    for _ in range(20):
        if _user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.1)
    return False


def _click_fraction(hwnd: int, point: list[float]) -> None:
    left, top, width, height = _client_rect(hwnd)
    x, y = int(left + point[0] * width), int(top + point[1] * height)
    _user32.SetCursorPos(x - 3, y - 3)   # move in steps so the game registers hover
    time.sleep(0.08)
    _user32.SetCursorPos(x, y)
    time.sleep(0.15)
    _send([_INPUT(0, _INPUTUNION(mi=_MOUSEINPUT(0, 0, 0, 0x0002, 0, 0)))])  # left down
    time.sleep(0.08)
    _send([_INPUT(0, _INPUTUNION(mi=_MOUSEINPUT(0, 0, 0, 0x0004, 0, 0)))])  # left up
    time.sleep(0.1 + float(_settings.get("click_extra_delay", 0.5)))


def _find_status_file() -> str | None:
    """Locate Elite's Status.json (EDMC's journal folder first, then the default)."""
    candidates = []
    try:
        from config import config
        journal = config.get_str("journaldir") or getattr(config, "default_journal_dir", "")
        if journal:
            candidates.append(os.path.join(os.fspath(journal), "Status.json"))
    except Exception:
        pass
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    candidates.append(os.path.join(home, "Saved Games", "Frontier Developments", "Elite Dangerous",
                                   "Status.json"))
    return next((path for path in candidates if os.path.isfile(path)), None)


def _live_gui_focus() -> int | None:
    """Which screen the game reports right now, read straight from Status.json.
    None if it can't be read (the game rewrites it often, so retry briefly)."""
    if not STATUS_PATH:
        return None
    for _ in range(3):
        try:
            with open(STATUS_PATH, encoding="utf-8") as stream:
                return int(json.load(stream).get("GuiFocus") or 0)
        except (OSError, ValueError, TypeError, AttributeError):
            time.sleep(0.05)
    return None


def _snapshot_gui_focus() -> int:
    return int(_snapshot.get("cockpit", {}).get("GuiFocus") or 0)


def _gui_focus() -> int:
    """Current screen (6 = galaxy map, 0 = cockpit): live from the game, else EDMC's copy."""
    live = _live_gui_focus()
    return live if live is not None else _snapshot_gui_focus()


def _open_galaxy_map(label: str) -> None:
    """Open the galaxy map unless it is already open, logging what the game reported."""
    live, copy = _live_gui_focus(), _snapshot_gui_focus()
    logger.info("%s: screen at start - Status.json GuiFocus=%s, EDMC copy=%s", label, live, copy)
    if _gui_focus() == 6:
        logger.info("%s: galaxy map already open, not pressing the map key", label)
        return
    _press_map_key()
    for _ in range(40):                  # wait up to ~4 s for the game to report the map
        if _gui_focus() == 6:
            break
        time.sleep(0.1)
    logger.info("%s: after the map key, GuiFocus=%s", label, _gui_focus())
    time.sleep(float(_settings["map_open_delay"]))


def _close_map() -> None:
    """Back out of the map with Esc, but stop as soon as the game reports the
    cockpit (GuiFocus 0) so a spare press never opens the system menu."""
    for _ in range(int(_settings.get("esc_presses", 3))):
        if _gui_focus() == 0:
            break
        _tap(SC_ESC)
        time.sleep(float(_settings.get("esc_gap", 0.8)))
    logger.info("Leaving the map: GuiFocus=%s afterwards", _gui_focus())


def _plot_sequence(initial_delay: float, target: str) -> None:
    try:
        time.sleep(initial_delay)
        hwnd = _find_game()
        if not hwnd:
            _set_status("Elite window not found.")
            return
        if not _focus_game(hwnd):
            _set_status("Could not focus Elite.")
            return
        step = float(_settings["step_delay"])
        _set_status("Plotting…")
        _open_galaxy_map("Plot")
        _click_fraction(hwnd, _settings["search_box"])
        time.sleep(0.3)
        _chord(SC_CTRL, SC_A)        # select any previous search text
        _tap(0x0E)                   # Backspace deletes the selection
        if _settings.get("input_method") == "paste":
            _chord(SC_CTRL, SC_V)
        else:
            _type_text(target, float(_settings.get("type_delay", 0.05)))
        logger.info("Galaxy map automation entered %r via %s", target, _settings.get("input_method"))
        time.sleep(0.4)
        _tap(SC_ENTER)
        time.sleep(step + 0.4)       # wait for results
        if _settings.get("first_result"):
            _click_fraction(hwnd, _settings["first_result"])
            time.sleep(step + float(_settings.get("map_scroll_delay", 2.0)))
        _click_fraction(hwnd, _settings["plot_button"])
        time.sleep(step + float(_settings.get("plot_route_delay", 1.0)))
        _close_map()
        confirmed = _wait_for_navroute(target)
        if confirmed is False:
            _set_status(f"Plot not confirmed - the game shows no route to {target}.")
        else:
            _set_status("Route plotted.")
    except Exception:
        logger.exception("Galaxy map automation failed")
        _set_status("Plot Failed - Click To Retry (See Log)")
    finally:
        _plot_lock.release()


def _jumps_left_to(target: str) -> int | None:
    """Jumps left on the game's plotted route if it ends at target AND you are on it, else None.
    Checked against NavRoute.json itself, so a stale memory can never block a plot."""
    data = _read_journal_json("NavRoute.json") or {}
    names = [str(item.get("StarSystem") or "").casefold()
             for item in data.get("Route") or [] if isinstance(item, dict)]
    if len(names) < 2 or names[-1] != target.casefold():
        return None
    here = str(_snapshot.get("location", {}).get("system_name") or "").casefold()
    if here not in names:
        return None
    left = len(names) - 1 - names.index(here)
    return left if left > 0 else None


def _already_plotted(target: str) -> bool:
    return _jumps_left_to(target) is not None


def _start_plot(initial_delay: float = 0.0, target: str | None = None) -> None:
    """Plot to target (default: the next waypoint) through the galaxy map."""
    if _user32 is None:
        _set_status("Automation needs Windows.")
        return
    _sync_map_points()
    target = target or _next_system()
    if not target:
        _set_status("No waypoint to plot.")
        return
    if _already_plotted(target):
        # Pressing Plot Route on the destination that is already plotted makes Elite remove
        # the route. This happens when the game routes a leg through an extra neutron and you
        # supercharge there: Next is still the plotted destination (bug found 24 Oct).
        left = _jumps_left_to(target)
        logger.info("Plot: the game's route already ends at %s (%s jump(s) left) - not plotting it again", target, left)
        _set_status(f"Route still set: {left} jump{'s' if left != 1 else ''} to {target}. Just jump.")
        return
    if not _plot_lock.acquire(blocking=False):
        _set_status("Busy - try again in a moment.")
        return
    _copy_system(target)  # keeps the clipboard in sync; also used by paste mode
    threading.Thread(target=_plot_sequence, args=(initial_delay, target), daemon=True).start()


def _start_jetcone_toggle() -> None:
    if _user32 is None:
        _set_status("Automation needs Windows.")
        return
    _sync_map_points()
    if not (_settings.get("jetcone_tab") and _settings.get("jetcone_toggle")):
        _set_status("Train the jet-cone clicks first (Train Map Clicks).")
        return
    if not _plot_lock.acquire(blocking=False):
        _set_status("Busy - try again in a moment.")
        return
    threading.Thread(target=_jetcone_sequence, daemon=True).start()


def _jetcone_sequence() -> None:
    """Open the map, open the route-settings panel, click the jet-cone toggle, back out."""
    try:
        hwnd = _find_game()
        if not hwnd:
            _set_status("Elite window not found.")
            return
        if not _focus_game(hwnd):
            _set_status("Could not focus Elite.")
            return
        step = float(_settings["step_delay"])
        _set_status("Toggling jet-cone routing…")
        _open_galaxy_map("Jet-cone toggle")
        _click_fraction(hwnd, _settings["jetcone_tab"])
        time.sleep(step)
        _click_fraction(hwnd, _settings["jetcone_toggle"])
        time.sleep(step)
        _close_map()                     # Esc back to the map, then Esc out to the cockpit
        _set_status("Jet-cone routing toggled. Check the panel if unsure.")
    except Exception:
        logger.exception("Jet-cone toggle failed")
        _set_status("Jet-cone toggle error - see log.")
    finally:
        _plot_lock.release()


def _calibrate_start(steps: tuple = _CAL_STEPS) -> None:
    if _user32 is None:
        _set_status("Automation needs Windows.")
        return
    if not _plot_lock.acquire(blocking=False):
        _set_status("Busy - try again in a moment.")
        return
    _cal.update(step=0, left=0, ready=False, error="", missed=[], steps=steps)
    _set_status("Opening the galaxy map…")
    threading.Thread(target=_calibrate_open_map, daemon=True).start()
    _calibrate_wait()


def _calibrate_open_map() -> None:
    try:
        hwnd = _find_game()
        if not hwnd:
            _cal["error"] = "Elite window not found."
        elif not _focus_game(hwnd):
            _cal["error"] = "Could not focus Elite."
        elif _gui_focus() == 0:
            _press_map_key()
            for _ in range(40):          # wait up to ~4 s for the game to report the map
                if _gui_focus() == 6:
                    break
                time.sleep(0.1)
            time.sleep(float(_settings["map_open_delay"]))
            if _gui_focus() != 6:
                _cal["error"] = "The map did not open - check the map key."
        elif _gui_focus() != 6:
            _cal["error"] = "Return to the cockpit view first."
    except Exception as error:
        logger.exception("Could not open the galaxy map for calibration")
        _cal["error"] = f"Could not open the map: {type(error).__name__}: {error}"
    _cal["ready"] = True


def _calibrate_wait() -> None:
    if not _cal["ready"]:
        _app_frame.after(200, _calibrate_wait)
        return
    if _cal["error"]:
        _calibrate_finish(str(_cal["error"]), close_map=False)
        return
    _cal["left"] = int(_settings.get("calibrate_countdown", 15))
    _calibrate_tick()


def _calibrate_tick() -> None:
    step = _cal["step"]
    steps = _cal["steps"]
    if step >= len(steps):
        if _save_settings():
            missed = _cal["missed"]
            _calibrate_finish("Calibration saved." if not missed else
                              f"Saved, but missed: {', '.join(missed)}. Try again.", close_map=True)
        else:
            _calibrate_finish("", close_map=True)
        return
    key, label = steps[step]
    if _cal["left"] > 0:
        _set_status(f"{step + 1}/{len(steps)}: {label} ({_cal['left']}s)")
        _cal["left"] -= 1
        _app_frame.after(1000, _calibrate_tick)
        return
    hwnd = _find_game()
    if not hwnd:
        _calibrate_finish("Elite window not found.", close_map=False)
        return
    left, top, width, height = _client_rect(hwnd)
    cursor = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(cursor))
    fx, fy = (cursor.x - left) / width, (cursor.y - top) / height
    if 0 <= fx <= 1 and 0 <= fy <= 1:
        _settings[key] = [round(fx, 4), round(fy, 4)]
    else:
        _cal["missed"].append(key.replace("_", " "))
    _cal["step"] += 1
    _cal["left"] = int(_settings.get("calibrate_countdown", 15))
    _calibrate_tick()


def _calibrate_finish(message: str, close_map: bool) -> None:
    if message:
        _set_status(message)

    def worker() -> None:
        try:
            if close_map:
                _close_map()
        except Exception:
            logger.exception("Could not close the galaxy map after calibration")
        finally:
            _plot_lock.release()

    threading.Thread(target=worker, daemon=True).start()


_theme_pending = None
_theme_bindings = []
_theme_controls = []
_pace_anchor = None
_pace_samples = []


def _widget_alive(widget) -> bool:
    try:
        return widget is not None and bool(widget.winfo_exists())
    except tk.TclError:
        return False


def _palette():
    """Normal, highlight and background colours. Never raises: EDMC may call
    drawing code before its theme palette exists, and a failure here would stop
    the whole panel from being created."""
    try:
        from theme import theme
        palette = getattr(theme, "current", None) or {}
    except Exception:
        palette = {}

    def label_colour(option, fallback):
        try:
            if _widget_alive(_title_label):
                return _title_label.cget(option) or fallback
        except tk.TclError:
            pass
        return fallback

    try:
        default_highlight = config.get_str("dark_highlight", default="#ff8000") or "#ff8000"
    except Exception:
        default_highlight = "#ff8000"
    normal = palette.get("foreground") or label_colour("foreground", "black")
    highlight = palette.get("highlight") or default_highlight
    background = palette.get("background") or label_colour("background", "white")
    return normal, highlight, background



def _attach_popup(window, name):
    """Required Interface styles suite popups and remembers their size and position."""
    window.navigator_window_id = "Navigation:" + name
    try:
        from plug import invoke
        invoke("(N) Interface", "Navigator Interface", "navigator_attach_window", window)
    except ImportError:
        pass

def _width_event(event=None):
    """Refit the tabs only when the panel width really changed (a font change cannot loop back here)."""
    global _last_width
    width = getattr(event, "width", 0)
    if width and width != _last_width:
        _last_width = width
        _theme_event()


_last_width = 0


def _theme_event(event=None):
    global _theme_pending
    if _app_frame is not None and _theme_pending is None:
        _theme_pending = _app_frame.after_idle(_apply_theme)


def _apply_theme():
    global _theme_pending
    _theme_pending = None
    if _app_frame is None or not _app_frame.winfo_exists(): return
    normal,highlight,background = _palette()
    for widget in list(_theme_controls):
        if not widget.winfo_exists():
            _theme_controls.remove(widget)
        elif hasattr(widget,"redraw"):
            widget.configure(background=background)
            widget.redraw()
        else:
            widget.configure(foreground=highlight,background=background)
    _sync_header_buttons()
    _apply_header_spacing()
    _sync_shortcuts()
    _refresh_tabs(background, highlight)
    _refresh_position()
    _refresh_expedition_bar()
    if _left_extra is not None and _widget_alive(_left_extra):
        _left_extra.configure(foreground=_status_colours().get("info", "#4da6ff"), background=background)


def prefs_changed(cmdr=None,is_beta=False):
    # EDMC calls this after Settings > OK (Appearance changes too). One idle lets its theme finish.
    _apply_prefs_page()
    _theme_event()


# --- Route position lamp -------------------------------------------------
# Added by Claude (route editions, 22 Oct 2026).
# Replaces the separate bottom line from 0.14.0 ("Route Loaded" / "Detour" /
# "On Route" / ETA). The state now sits at the end of the Jumps line as a small
# lamp: green On Route, red Off Route, green Arrived. Nothing is shown until
# EDMC has told us where the ship is.
#
# Neutron routes list only the neutron waypoints, so ordinary travel often
# passes through systems that are not on the list. Those count as On Route
# while the game's own plotted route ends at a waypoint still ahead. Off Route
# means you are away from the route and not plotted back onto it (for
# example a fuel stop).
LAMP_ON = "#33cc33"
LAMP_OFF = "#d93636"      # red (Jonathan, 23 Oct; was amber)
SEP = "  |  "
_plotted_destination: str | None = None   # casefolded end of the game's plotted route
_plot_seen = False
_in_hyperspace = False     # between StartJump (Hyperspace) and arrival
_route_ending = False      # NavRouteClear arrived mid-jump: the plotted route is finishing
_lamp = None
_position_frame = None
_position_label = None


def _note_plotted_route(entry: dict, state: dict) -> None:
    """Follow where the game's plotted route ends (NavRoute / NavRouteClear / FSDTarget)."""
    global _plotted_destination, _plot_seen, _in_hyperspace, _route_ending
    event = entry.get("event")
    route = None
    if event == "StartJump":
        _in_hyperspace = entry.get("JumpType") == "Hyperspace"
        return
    if event in ("FSDJump", "Location", "CarrierJump"):
        _in_hyperspace = False
        if _route_ending:
            _plotted_destination, _route_ending = None, False
        return
    if event == "NavRouteClear":
        # The game clears a route as its final jump starts. Keep the destination
        # until we arrive, so leaving a fuel stop for a waypoint stays On Route.
        _plot_seen = True
        if _in_hyperspace:
            _route_ending = True
        else:
            _plotted_destination = None
        return
    if event == "FSDTarget":
        # One jump left in the plotted route: the target is its destination.
        if entry.get("RemainingJumpsInRoute") == 1 and entry.get("Name"):
            _plotted_destination, _plot_seen = str(entry["Name"]).casefold(), True
        return
    if event == "NavRoute":
        _route_ending = False
        saved = state.get("NavRoute") if isinstance(state, dict) else None
        route = entry.get("Route") or (saved.get("Route") if isinstance(saved, dict) else None)
    elif not _plot_seen:
        saved = state.get("NavRoute") if isinstance(state, dict) else None
        if not isinstance(saved, dict):
            return
        route = saved.get("Route") or []          # EDMC's copy of NavRoute.json at startup
    else:
        return
    if isinstance(route, list):
        _plot_seen = True
        last = route[-1] if route and isinstance(route[-1], dict) else {}
        _plotted_destination = str(last.get("StarSystem") or "").casefold() or None


def _route_position() -> str | None:
    """'arrived', 'on', 'off', or None when there is nothing to show yet."""
    if not _route_systems:
        return None
    if _route_index >= len(_route_systems) - 1:
        return "arrived"
    physical = str(_snapshot.get("location", {}).get("system_name") or "").casefold()
    if not physical:
        return None
    ahead = [name.casefold() for name in _route_systems[max(_route_index, 0):]]
    if physical in ahead:
        return "on"
    if _plotted_destination and _plotted_destination in ahead:
        return "on"
    return "off"


def _default_pace() -> float:
    """Settings page: minutes per jump to assume until your own pace is learned."""
    try:
        return min(60.0, max(0.25, float(_settings.get("eta_minutes_per_jump", 2.0))))
    except (TypeError, ValueError):
        return 2.0


def _idle_limit() -> float:
    """Seconds between waypoints above which the gap counts as idle (3x the default, at least 6 min)."""
    return max(360.0, _default_pace() * 60 * 3)


def _eta_text() -> str:
    """Average waypoint-to-waypoint time so far x waypoints left (from 0.14.0)."""
    left = _jump_counts()[1]
    if left <= 0:
        return ""
    if _pace_samples:
        seconds = sum(_pace_samples) / len(_pace_samples)
    else:
        seconds = _default_pace() * 60       # until your own pace is learned
    minutes = max(1, round(seconds * left / 60))
    return f"~{minutes} min" if minutes < 60 else f"~{minutes // 60}h {minutes % 60:02d}m"


class _Lamp(tk.Canvas):
    """A small filled circle sized to the text beside it."""

    def __init__(self, parent, reference) -> None:
        super().__init__(parent, width=10, height=10, highlightthickness=0, bd=0)
        self._reference = reference
        self._colour = LAMP_ON
        self.bind("<Map>", self.redraw)

    def set_colour(self, colour: str) -> None:
        self._colour = colour
        self.redraw()

    def redraw(self, _event=None) -> None:
        try:
            line = int(tkfont.Font(font=self._reference.cget("font")).metrics("linespace"))
        except (tk.TclError, ValueError):
            line = 16
        size = max(8, round(line * 0.55))
        if int(self.cget("width")) != size + 2:
            tk.Canvas.configure(self, width=size + 2, height=size + 2)
        if (self._colour, size) == getattr(self, "_drawn", None) and self.find_all():
            return                          # unchanged: don't repaint
        self._drawn = (self._colour, size)
        self.delete("all")
        self.create_oval(1, 1, size + 1, size + 1, fill=self._colour, outline=self._colour)


def _refresh_position() -> None:
    if not _widget_alive(_position_frame):
        return
    position = _route_position()
    _refresh_route_bar(position)
    if position is None:
        _position_frame.pack_forget()
        return
    word = {"arrived": "Arrived", "on": "On Route", "off": "Off Route"}[position]
    eta = _eta_text() if position == "on" else ""
    _position_label.configure(text=word + (SEP + eta if eta else ""))
    on_colour, off_colour = _route_colours()
    _lamp.set_colour(off_colour if position == "off" else on_colour)
    if _route_bar_on():
        # The progress bar shows On Route / Off Route / Arrived; the Jumps line keeps only the ETA.
        _lamp.pack_forget()
        _position_label.configure(text=eta)
        if not eta:
            _position_frame.pack_forget()
            return
    elif not _lamp.winfo_manager():
        _lamp.pack(side=tk.LEFT, padx=(0, 4), before=_position_label)
    if not _position_frame.winfo_manager():
        _position_frame.pack(side=tk.LEFT)


def _build_position(progress) -> None:
    """The lamp group at the end of the Jumps line: '  |  (lamp) On Route  |  ~12 min'."""
    global _position_frame, _position_label, _lamp
    _position_frame = tk.Frame(progress)
    tk.Label(_position_frame, text=SEP, padx=0, bd=0).pack(side=tk.LEFT)
    _position_label = tk.Label(_position_frame, padx=0, bd=0)
    _lamp = _Lamp(_position_frame, _position_label)
    _lamp.pack(side=tk.LEFT, padx=(0, 4))
    _position_label.pack(side=tk.LEFT)


def _status_colours() -> dict:
    """The status button colours from (N) Interface (green/red, or the theme's Highlighted/Normal text
    colours with its accessibility setting); local defaults if Interface is not available."""
    colours = _interface("navigator_status_colours")
    if isinstance(colours, dict):
        return colours
    normal, highlight, background = _palette()
    return {"on": LAMP_ON, "off": LAMP_OFF, "plain": normal, "highlight": highlight,
            "background": background, "forced": False, "info": "#4da6ff"}


class _RouteButton(tk.Button):
    """The Auto-Route toggle: an R, the same size and font as the copy/auto A beside it. On: the R in the 'on'
    colour (green, or your Highlighted Text colour). Off: the R in the 'off' colour (red, or your Normal Text
    colour) with a strikethrough, so the state reads without colour. Colours come from (N) Interface's setting."""

    def __init__(self, parent: tk.Misc, variable: tk.BooleanVar, command) -> None:
        super().__init__(parent, text="R", takefocus=False, command=self._clicked)
        self._variable, self._command = variable, command
        self._struck = None            # the strikethrough font (kept so Tk does not discard it)

    def _clicked(self) -> None:
        self._variable.set(not self._variable.get())
        self._command()
        self.redraw()

    def redraw(self) -> None:
        if not _widget_alive(self):
            return
        colours = _status_colours()
        on = bool(self._variable.get())
        colour = colours["on"] if on else colours["off"]
        try:
            base = tkfont.Font(font=self.cget("font"))
            base.configure(overstrike=not on)
            self._struck = base
            self.configure(font=base, foreground=colour, activeforeground=colour)
        except tk.TclError:
            logger.exception("Could not style the Auto-Route button")


def _title_clicked() -> None:
    """The header opens the settings menu only when the cog box is switched off (otherwise the cog does)."""
    wanted = _interface("navigator_header_cog_enabled")
    if not (wanted is None or bool(wanted)):
        _show_settings_menu()


SHORTCUT_SLOTS = 5                 # the most buttons; Settings chooses 3, 4 or 5 of them
SHORTCUT_NAME_CHARS = 10           # a button label is never longer than this
SHORTCUT_BOXES = 2.5               # every button is this many header boxes (the collapse button) wide
SHORTCUT_MIN_BOXES = 2.0           # ...and never narrower than this, even with five of them
SHORTCUT_GAP = 2                   # pixels each side of a button


def _shortcut_count() -> int:
    try:
        return min(SHORTCUT_SLOTS, max(3, int(_settings.get("shortcut_count", 3))))
    except (TypeError, ValueError):
        return 3


def _shortcut_items() -> list[tuple[str, str]]:
    """(label, destination) for the buttons that have a destination, in order, within the chosen count.
    A button with a destination but no name is labelled with the destination."""
    items = []
    for entry in list(_settings.get("shortcuts") or [])[:_shortcut_count()]:
        if not isinstance(entry, dict):
            continue
        target = str(entry.get("target") or "").strip()
        if target:
            items.append((str(entry.get("name") or "").strip()[:SHORTCUT_NAME_CHARS] or target, target))
    return items


def _fit_label(font: tkfont.Font, text: str, room: int) -> str:
    if font.measure(text) <= room:
        return text
    while text and font.measure(text + "…") > room:
        text = text[:-1]
    return text.rstrip() + "…"


def _pixel_size(button: tk.Button, width: int, height: int) -> None:
    """Give a button an exact size in pixels (an invisible one-pixel image with the text centred over it)."""
    if not getattr(button, "navigator_pixel", None):
        button.navigator_pixel = tk.PhotoImage(master=button, width=1, height=1)
    button.configure(image=button.navigator_pixel, compound="center", width=width, height=height)
    extra_w, extra_h = button.winfo_reqwidth() - width, button.winfo_reqheight() - height
    if extra_w or extra_h:                       # borders and padding come on top of the size: take them off
        button.configure(width=max(1, width - extra_w), height=max(1, height - extra_h))


def _shortcuts_available() -> bool:
    """The bar is switched on and has a button to show. The panel's own collapse arrow does not matter: the S button
    works on its own, folded panel or not."""
    return bool(_settings.get("shortcuts_on")) and bool(_shortcut_items())


def _shortcut_toggle_room() -> int:
    """Pixels the cog and the S button take between the collapse box and the A (for (N) Interface, which keeps the A
    clear of them)."""
    room = 0
    for button in (_cog_button, _shortcut_toggle_button):
        if button is not None and _widget_alive(button) and button.winfo_manager():
            room += button.winfo_reqwidth() + 2
    return room


def _toggle_shortcuts() -> None:
    _settings["shortcuts_hidden"] = not _settings.get("shortcuts_hidden")
    _save_settings()
    _sync_shortcuts()


def _sync_shortcuts() -> None:
    """Show, hide, size and colour the shortcut bar and its S button. Cheap to call: it does nothing unless
    something it depends on has changed, so a journal event never redraws it."""
    global _shortcut_state
    like = _collapse_button
    if _shortcut_bar is None or like is None or not _widget_alive(_shortcut_bar) or not _widget_alive(like):
        return
    items = _shortcut_items()
    available = _shortcuts_available()
    shown = available and not _settings.get("shortcuts_hidden")
    normal, highlight, background = _palette()
    box_w, box_h = like.winfo_reqwidth(), like.winfo_reqheight()
    body = _current_label if _current_label is not None and _widget_alive(_current_label) else _title_label
    body_font = str(body.cget("font")) if body is not None else str(like.cget("font"))
    width = _app_frame.winfo_width()
    if width <= 1 and _app_frame.master is not None:
        width = _app_frame.master.winfo_width()
    look = tuple(str(like.cget(option)) for option in ("font", "padx", "pady", "borderwidth", "relief",
                                                      "highlightthickness", "highlightbackground"))
    outline = _interface("navigator_flat_colour")         # the thin Normal Text outline every flat suite button has
    state = (available, shown, tuple(items), normal, highlight, background, box_w, box_h, width, look, body_font, outline)
    if state == _shortcut_state:
        return
    previous, _shortcut_state = _shortcut_state, state
    if previous is None or previous[0] != available or previous[1] != shown:
        _sync_header_buttons()                          # the S button comes, goes or changes colour
        _interface("navigator_sync_mode_buttons")       # ...and the A keeps clear of it
    if not shown:
        _shortcut_bar.grid_remove()
        return
    if box_w < 8 or box_h < 8:
        return
    font = tkfont.Font(font=body_font)                  # the same text size as the rest of the panel
    edge = like.winfo_pixels(like.cget("padx")) + like.winfo_pixels(like.cget("highlightthickness"))
    needed = max(font.measure(label) for label, _target in items) + 2 * edge + 8
    each = max(round(box_w * SHORTCUT_BOXES), needed)
    if width > 1:
        each = min(each, width // len(items) - 2 * SHORTCUT_GAP)
    each = max(each, round(box_w * SHORTCUT_MIN_BOXES))
    tall = max(box_h, font.metrics("linespace") + 2 * (like.winfo_pixels(like.cget("pady")) + 1) + 4)
    for index, button in enumerate(_shortcut_buttons):
        if index >= len(items):
            button.grid_remove()
            continue
        label, target = items[index]
        try:
            for option in ("padx", "pady", "borderwidth", "relief", "highlightthickness",
                           "highlightbackground", "highlightcolor"):
                button.configure(**{option: like.cget(option)})
            if outline:
                button.configure(relief="flat", borderwidth=0, highlightthickness=1,
                                 highlightbackground=outline, highlightcolor=outline)
            button.configure(font=font)
            button.navigator_font = font                # Tk drops a font nothing refers to
            _pixel_size(button, each, tall)
            room = each - 2 * (int(str(button.cget("borderwidth"))) + int(str(button.cget("padx")))) - 4
            button.configure(text=_fit_label(font, label, room), foreground=highlight, background=background,
                             activeforeground=highlight, activebackground=background, disabledforeground=highlight,
                             command=lambda name=target: _goto_name(name))
        except tk.TclError:
            logger.exception("Could not style a shortcut button")
        button.grid(row=0, column=index, padx=SHORTCUT_GAP)
    _shortcut_bar.grid(row=1, column=0)


def _sync_header_buttons() -> None:
    """Lay out the header's right-hand stack and the clickable title. From the right edge: the collapse box,
    the optional cog (so it lines up with the Commander Profile cog), the S (shortcut bar, when there is one), the
    copy/auto box (when shown), the R (Auto-Route), then the optional cog. All the same size as the collapse
    box. With the cog on, the header itself is plain text (the cog opens the menu); with it off, the header (still Normal Text colour)
    is the clickable settings menu."""
    if _title_label is None or not _widget_alive(_title_label):
        return
    normal, highlight, background = _palette()
    wanted = _interface("navigator_header_cog_enabled")
    cog_on = wanted is None or bool(wanted)
    gap = 2
    right = 0
    if _collapse_button is not None and _collapse_button.winfo_manager():
        right = _collapse_button.winfo_reqwidth() + gap
    if _cog_button is not None and _widget_alive(_cog_button):
        if cog_on:
            if _collapse_button is not None:
                _interface("navigator_match_button", _cog_button, _collapse_button, ("\u2699",))
            _cog_button.configure(foreground=normal, background=background, activeforeground=normal,
                                  activebackground=background, disabledforeground=normal)
            _cog_button.grid(row=0, column=0, sticky=tk.NE, padx=(0, right))
            right += _cog_button.winfo_reqwidth() + gap
        else:
            _cog_button.grid_remove()
    toggle = _shortcut_toggle_button
    if toggle is not None and _widget_alive(toggle):
        if _shortcuts_available():
            if _collapse_button is not None:
                _interface("navigator_match_button", toggle, _collapse_button, ("S",))
            colour = highlight if _settings.get("shortcuts_hidden") else normal    # Highlighted while the bar is hidden
            toggle.configure(foreground=colour, activeforeground=colour, background=background,
                             activebackground=background, disabledforeground=colour)
            toggle.grid(row=0, column=0, sticky=tk.NE, padx=(0, right))
            right += toggle.winfo_reqwidth() + gap
        else:
            toggle.grid_remove()
    if _mode_button is not None and _mode_button.winfo_manager():
        right += _mode_button.winfo_reqwidth() + gap
    if _compass is not None and _widget_alive(_compass):
        if _route_systems:
            if _collapse_button is not None:
                _interface("navigator_match_button", _compass, _collapse_button, ("R",))
            _compass.grid(row=0, column=0, sticky=tk.NE, padx=(0, right))
            _compass.redraw()
            right += _compass.winfo_reqwidth() + gap
        else:
            _compass.grid_remove()
    # The clickable header: only when the cog box is off (then the header IS the settings button).
    try:
        if cog_on:
            _title_label.configure(cursor="", takefocus=False, foreground=normal)
        else:
            # Suite rule: a plugin header is always Normal Text, even when it is clickable (no other plugin's header is
            # highlighted, and the suite should look like the rest of EDMC). The cog box is the visible cue.
            _title_label.configure(cursor="hand2", takefocus=True, foreground=normal)
    except tk.TclError:
        pass


# ---------------------------------------------------------------------------
# Plot New Route: current ship from the journal + Spansh neutron plotter
# ---------------------------------------------------------------------------
SPANSH_ROUTE_URL = "https://spansh.co.uk/api/route"
SPANSH_RESULTS_URL = "https://spansh.co.uk/api/results/"
SPANSH_NAMES_URL = "https://spansh.co.uk/api/systems/field_values/system_names"
SPANSH_STATIONS_URL = "https://spansh.co.uk/api/stations/search"
SPANSH_TIMEOUT = 15          # seconds per request
SPANSH_MAX_WAIT = 120        # seconds to wait for Spansh to finish a route
MAX_SANE_RANGE = 150.0       # ly; a recorded range above this is treated as a bad reading
_last_loadout: dict[str, Any] | None = None   # newest Loadout seen through EDMC
_plot_popup = None


class _PlotCancelled(Exception):
    pass


def _journal_dir() -> str | None:
    path = STATUS_PATH or _find_status_file()
    return os.path.dirname(path) if path else None


def _read_journal_json(name: str) -> dict[str, Any] | None:
    """Read one of the game's small JSON files (NavRoute.json, Cargo.json...).
    The game rewrites them often, so retry briefly if one is caught mid-write."""
    folder = _journal_dir()
    if not folder:
        return None
    path = os.path.join(folder, name)
    for _ in range(3):
        try:
            with open(path, encoding="utf-8") as stream:
                data = json.load(stream)
            return data if isinstance(data, dict) else None
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            time.sleep(0.05)
    return None


def _navroute_destination() -> str | None:
    """Last system of the route the game has plotted ("" if none; None if unreadable)."""
    data = _read_journal_json("NavRoute.json")
    if data is None:
        return None
    route = data.get("Route") or []
    last = route[-1] if isinstance(route, list) and route else None
    return str(last.get("StarSystem") or "") if isinstance(last, dict) else ""


def _wait_for_navroute(target: str, timeout: float = 5.0) -> bool | None:
    """True if the game's plotted route ends at target, False if it doesn't,
    None if NavRoute.json can't be read at all."""
    deadline = time.monotonic() + timeout
    destination = None
    while True:
        destination = _navroute_destination()
        if destination is not None and destination.casefold() == target.casefold():
            logger.info("Route check: the game's route ends at %s - confirmed", target)
            return True
        if time.monotonic() >= deadline:
            break
        time.sleep(0.25)
    if destination is None:
        logger.info("Route check: NavRoute.json could not be read; route to %s not confirmed", target)
        return None
    logger.info("Route check: the game's route ends at %r, expected %r - not confirmed",
                destination, target)
    return False


def _cargo_count() -> int:
    data = _read_journal_json("Cargo.json")
    if not data or data.get("Vessel", "Ship") != "Ship":
        return 0
    try:
        return int(data.get("Count") or 0)
    except (TypeError, ValueError):
        return 0


def _read_latest_loadout() -> dict[str, Any] | None:
    """The game writes a Loadout record whenever you board, switch or outfit a ship
    (not when you supercharge). Read the newest one from the newest journal files."""
    best = None
    folder = _journal_dir()
    if folder:
        try:
            files = sorted((os.path.join(folder, name) for name in os.listdir(folder)
                            if name.startswith("Journal") and name.endswith(".log")),
                           key=os.path.getmtime, reverse=True)[:5]
        except OSError:
            files = []
        for path in files:
            found = None
            try:
                with open(path, encoding="utf-8", errors="replace") as stream:
                    for line in stream:
                        if "Loadout" not in line:
                            continue
                        try:
                            record = json.loads(line)
                        except ValueError:
                            continue
                        if record.get("event") == "Loadout":
                            found = record
            except OSError:
                continue
            if found:
                best = found
                break
    cached = _last_loadout
    if cached and (best is None or str(cached.get("timestamp", "")) > str(best.get("timestamp", ""))):
        best = cached
    return best


_RECENT_SHIPS = {          # in case an older EDMC doesn't know the newest ships yet
    "explorer_nx": "Caspian Explorer", "python_nx": "Python Mk II", "mandalay": "Mandalay",
    "corsair": "Corsair", "cobramkv": "Cobra Mk V", "panthermkii": "Panther Clipper Mk II",
    "type8": "Type-8 Transporter", "smallcombat01_nx": "Kestrel Mk II",
    "mediumtransport01": "Lynx Highliner", "lakonminer": "Type-11 Prospector",
    "typex_2": "Alliance Crusader",
}


def _ship_model_name(ship: str) -> str:
    key = ship.lower()
    try:
        from edmc_data import ship_name_map
        if key in ship_name_map:
            return ship_name_map[key]
    except Exception:
        pass
    if key in _RECENT_SHIPS:
        return _RECENT_SHIPS[key]
    # Brand-new ships: the game's own shipyard list has their display names
    # (Shipyard.json is written whenever you open a shipyard).
    shipyard = _read_journal_json("Shipyard.json") or {}
    for entry in shipyard.get("PriceList") or []:
        if isinstance(entry, dict) and str(entry.get("ShipType", "")).lower() == key \
                and entry.get("ShipType_Localised"):
            return str(entry["ShipType_Localised"])
    return ship.replace("_", " ").title()


def _ship_profile() -> dict[str, Any]:
    """Jump range and supercharge multiplier for the ship you are flying right now."""
    loadout = _read_latest_loadout()
    if not loadout:
        return {"ok": False, "range": 0.0, "multiplier": 4,
                "label": "No ship data found in your game journal yet."}
    fsd = next((str(module.get("Item", "")) for module in loadout.get("Modules", [])
                if module.get("Slot") == "FrameShiftDrive"), "")
    multiplier = 6 if "mkii" in fsd.lower() else 4        # SCO Mk II drive: x6, any other: x4
    try:
        jump_range = float(loadout.get("MaxJumpRange") or 0)
    except (TypeError, ValueError):
        jump_range = 0.0
    model = _ship_model_name(str(loadout.get("Ship", "")))
    name = str(loadout.get("ShipName") or "").strip()
    label = f"{name} ({model})" if name else model
    ok = 0 < jump_range <= MAX_SANE_RANGE
    planning, note = _planning_range(loadout, jump_range) if ok else (jump_range, "")
    logger.info("Plot New Route ship check: %s, FSD %s, game range %.2f, planning range %.2f (%s), x%d",
                label, fsd, jump_range, planning, note or "game figure", multiplier)
    return {"ok": ok, "range": planning, "best_range": jump_range, "range_note": note,
            "multiplier": multiplier, "label": label, "fsd": fsd}


def _spansh_request(url: str, data: dict[str, Any] | None = None, as_json: bool = False) -> Any:
    """GET (data=None) or POST a Spansh API call and return the JSON reply.
    Uses requests (bundled with EDMC, with its own certificate store) when available;
    Python's urllib inside a packaged app often cannot verify https certificates."""
    headers = {"User-Agent": f"NeutronHighwayNavigatorAuto/{VERSION} (EDMC plugin)", "Accept": "application/json"}
    try:
        import requests
    except ImportError:
        requests = None
    if requests is not None:
        try:
            if data is None:
                reply = requests.get(url, headers=headers, timeout=SPANSH_TIMEOUT)
            else:
                reply = (requests.post(url, json=data, headers=headers, timeout=SPANSH_TIMEOUT) if as_json
                         else requests.post(url, data=data, headers=headers, timeout=SPANSH_TIMEOUT))
        except requests.exceptions.RequestException as error:
            logger.warning("Spansh request to %s failed: %r", url, error)
            raise RuntimeError(f"Could not reach Spansh ({type(error).__name__}) - see the EDMC log.") from error
        if reply.status_code >= 400:
            try:
                detail = reply.json().get("error")
            except Exception:
                detail = None
            logger.warning("Spansh replied HTTP %s to %s: %s", reply.status_code, url, reply.text[:300])
            raise RuntimeError(str(detail) if detail else f"Spansh returned an error (HTTP {reply.status_code}).")
        try:
            return reply.json()
        except ValueError as error:
            logger.warning("Spansh reply from %s was not JSON: %s", url, reply.text[:300])
            raise RuntimeError("Spansh sent a reply the plugin could not read.") from error

    # Fallback without requests: urllib, with certifi's certificates if available.
    context = None
    try:
        import ssl
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    if data is not None and as_json:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    else:
        body = urllib.parse.urlencode(data, doseq=True).encode("utf-8") if data is not None else None
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=SPANSH_TIMEOUT, context=context) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read().decode("utf-8")).get("error")
        except Exception:
            detail = None
        logger.warning("Spansh replied HTTP %s to %s", error.code, url)
        raise RuntimeError(str(detail) if detail else f"Spansh returned an error (HTTP {error.code}).") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        logger.warning("Spansh request to %s failed: %r", url, error)
        raise RuntimeError(f"Could not reach Spansh ({type(getattr(error, 'reason', error)).__name__})"
                           " - see the EDMC log.") from error
    except ValueError as error:
        raise RuntimeError("Spansh sent a reply the plugin could not read.") from error


def _spansh_names(text: str) -> list[str]:
    """System name suggestions for what has been typed so far (Spansh's prefix lookup)."""
    reply = _spansh_request(SPANSH_NAMES_URL + "?" + urllib.parse.urlencode({"q": text}))
    values = reply.get("min_max", reply.get("values", [])) if isinstance(reply, dict) else reply
    names = []
    for value in values or []:
        name = value.get("name") if isinstance(value, dict) else value
        if isinstance(name, str) and name not in names:
            names.append(name)
    return names[:8]


def _spansh_stations_detail(text: str) -> list[tuple[str, str, str]]:
    """Stations and carriers whose name matches what was typed: [(station, system, type), ...] (a live lookup,
    nothing kept; a carrier is found by its callsign, and its system is only as fresh as Spansh's last sighting)."""
    reply = _spansh_request(SPANSH_STATIONS_URL, {"filters": {"name": {"value": text}}, "size": 8, "page": 0},
                            as_json=True)
    found: list[tuple[str, str, str]] = []
    for item in (reply.get("results") if isinstance(reply, dict) else None) or []:
        name, system = item.get("name"), item.get("system_name")
        if isinstance(name, str) and isinstance(system, str) and (name, system) not in [(n, s) for n, s, _ in found]:
            found.append((name, system, str(item.get("type") or "")))
    return found[:8]


def _spansh_stations(text: str) -> list[tuple[str, str]]:
    return [(name, system) for name, system, _kind in _spansh_stations_detail(text)]


def _spansh_plot(start: str, end: str, jump_range: float, efficiency: int, multiplier: int,
                 cancelled) -> list[tuple[str, int]]:
    """Ask Spansh's neutron plotter for a route; returns [(system, jumps), ...]."""
    params = {"from": start, "to": end, "range": f"{jump_range:.2f}",
              "efficiency": efficiency, "supercharge_multiplier": multiplier}
    logger.info("Plot New Route: asking Spansh %s", params)
    reply = _spansh_request(SPANSH_ROUTE_URL, params)
    job = reply.get("job") if isinstance(reply, dict) else None
    if not job:
        error = reply.get("error") if isinstance(reply, dict) else None
        raise RuntimeError(str(error) if error else "Spansh did not accept the request.")
    deadline = time.monotonic() + SPANSH_MAX_WAIT
    while True:
        if cancelled():
            raise _PlotCancelled()
        result = _spansh_request(SPANSH_RESULTS_URL + urllib.parse.quote(str(job)))
        if isinstance(result, dict):
            if result.get("error"):
                raise RuntimeError(str(result["error"]))
            body = result.get("result")
            jumps = body.get("system_jumps") if isinstance(body, dict) else None
            if isinstance(jumps, list):
                route = [(str(step["system"]), int(step.get("jumps") or 0))
                         for step in jumps if isinstance(step, dict) and step.get("system")]
                if len(route) < 2:
                    raise RuntimeError("Spansh returned an empty route.")
                logger.info("Plot New Route: Spansh returned %d waypoints", len(route))
                return route
        if time.monotonic() > deadline:
            raise RuntimeError("Spansh is still calculating - try again in a moment.")
        time.sleep(1.5)


# ---------------------------------------------------------------------------
# Uncharted space: when Spansh doesn't know your system, bridge to one it does.
# The game always writes your exact coordinates (StarPos) to the journal, so we
# ask Spansh for known neutron stars near them and route from the best one.
# ---------------------------------------------------------------------------
SPANSH_BODIES_URL = "https://spansh.co.uk/api/bodies/search"
SPANSH_NEAREST_URL = "https://spansh.co.uk/api/nearest"
SPANSH_SEARCH_URL = "https://spansh.co.uk/api/search/systems"
BRIDGE_CANDIDATES = 12       # nearest known neutrons to compare
BRIDGE_MIN_REACH = 500.0     # ly; always consider neutrons at least this far away
BRIDGE_REACH_JUMPS = 20      # ...or this many normal jumps, if that is further
_star_pos: tuple[str, tuple[float, float, float]] | None = None   # (system, StarPos)


def _note_star_pos(system: str | None, entry: dict[str, Any], state: dict[str, Any]) -> None:
    """Remember the coordinates of the system you are in (works in unexplored space)."""
    global _star_pos
    if entry.get("event") in ("Location", "FSDJump", "CarrierJump") and entry.get("StarPos"):
        name, position = entry.get("StarSystem") or system, entry.get("StarPos")
    else:
        name, position = system or state.get("SystemName"), state.get("StarPos")
    try:
        x, y, z = (float(value) for value in position)
    except (TypeError, ValueError):
        return
    if name:
        _star_pos = (str(name), (x, y, z))


def _journal_star_pos(name: str) -> tuple[float, float, float] | None:
    """Coordinates of a system you have been to, from the newest journal files."""
    folder = _journal_dir()
    if not folder:
        return None
    try:
        files = sorted((os.path.join(folder, item) for item in os.listdir(folder)
                        if item.startswith("Journal") and item.endswith(".log")),
                       key=os.path.getmtime, reverse=True)[:3]
    except OSError:
        return None
    for path in files:
        found = None
        try:
            with open(path, encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    if '"StarPos"' not in line:
                        continue
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if str(record.get("StarSystem", "")).casefold() == name.casefold():
                        found = record.get("StarPos")
        except OSError:
            continue
        if found:
            try:
                x, y, z = (float(value) for value in found)
                return (x, y, z)
            except (TypeError, ValueError):
                pass
    return None


def _start_coordinates(name: str) -> tuple[float, float, float] | None:
    if _star_pos is not None and _star_pos[0].casefold() == name.casefold():
        return _star_pos[1]
    return _journal_star_pos(name)


def _unknown_start(error: Exception) -> bool:
    return "could not find starting system" in str(error).casefold()


def _spansh_coordinates(name: str) -> tuple[float, float, float] | None:
    """Coordinates of a system Spansh knows (exact name match), or None."""
    reply = _spansh_request(SPANSH_SEARCH_URL + "?" + urllib.parse.urlencode({"q": name}))
    for item in (reply.get("results") if isinstance(reply, dict) else None) or []:
        if isinstance(item, dict) and str(item.get("name", "")).casefold() == name.casefold():
            try:
                return (float(item["x"]), float(item["y"]), float(item["z"]))
            except (KeyError, TypeError, ValueError):
                return None
    return None


def _neutron_candidates(position: tuple[float, float, float], target: str, jump_range: float, multiplier: int,
                        reach_factor: float = 1.0) -> list[dict[str, Any]]:
    """Known neutron stars (main star only) within reach, best first: normal jumps to get there plus
    boosted jumps from there to the destination."""
    x, y, z = position
    query = {"filters": {"subtype": {"value": ["Neutron Star"]}, "is_main_star": {"value": True}},
             "sort": [{"distance": {"direction": "asc"}}], "size": BRIDGE_CANDIDATES, "page": 0,
             "reference_coords": {"x": x, "y": y, "z": z}}
    reply = _spansh_request(SPANSH_BODIES_URL, query, as_json=True)
    reach = max(BRIDGE_MIN_REACH, jump_range * BRIDGE_REACH_JUMPS) * reach_factor
    candidates, seen = [], set()
    for item in (reply.get("results") if isinstance(reply, dict) else None) or []:
        try:
            name, distance = str(item["system_name"]), float(item["distance"])
            coords = (float(item["system_x"]), float(item["system_y"]), float(item["system_z"]))
        except (KeyError, TypeError, ValueError):
            continue
        if distance <= reach and name.casefold() not in seen:
            seen.add(name.casefold())
            candidates.append({"system": name, "distance": distance, "coords": coords, "neutron": True})
    if candidates:
        try:
            goal = _spansh_coordinates(target) if target else None
        except RuntimeError:
            goal = None

        def cost(candidate: dict[str, Any]) -> float:
            onward = math.dist(candidate["coords"], goal) / (jump_range * multiplier) if goal else 0.0
            return candidate["distance"] / jump_range + onward
        candidates.sort(key=cost)
        logger.info("Plot New Route: %d bridge neutrons within %.0f ly (goal %s)",
                    len(candidates), reach, "known" if goal else "unknown")
    return candidates


def _nearest_known(position: tuple[float, float, float]) -> list[dict[str, Any]]:
    """The nearest system Spansh knows (a plain star, not a neutron), as a bridge candidate."""
    x, y, z = position
    try:
        reply = _spansh_request(SPANSH_NEAREST_URL + "?" + urllib.parse.urlencode({"x": x, "y": y, "z": z}))
    except RuntimeError:
        return []
    system = reply.get("system") if isinstance(reply, dict) else None
    if isinstance(system, dict) and system.get("name"):
        try:
            coords = (float(system["x"]), float(system["y"]), float(system["z"]))
        except (KeyError, TypeError, ValueError):
            coords = None
        return [{"system": str(system["name"]), "distance": float(system.get("distance") or 0),
                 "coords": coords, "neutron": False}]
    return []


def _find_bridge(position: tuple[float, float, float], target: str, jump_range: float,
                 multiplier: int) -> dict[str, Any]:
    """A known neutron near you (main star only, on the way to target), else the nearest known system."""
    candidates = _neutron_candidates(position, target, jump_range, multiplier)
    if candidates:
        best = candidates[0]
        logger.info("Plot New Route: bridge neutron %s at %.1f ly (of %d candidates)",
                    best["system"], best["distance"], len(candidates))
        return best
    nearest = _nearest_known(position)
    if nearest:
        logger.info("Plot New Route: no known neutron nearby; bridging via %s", nearest[0]["system"])
        return nearest[0]
    raise RuntimeError("Spansh doesn't know any systems near you yet.")


# ---------------------------------------------------------------------------
# Limp-home mode (Jonathan, 31 Oct 2026): a route must always come out, even in the worst case, because this
# tool is also used for rescues (Fuel Rats, Hull Seals). The steps run fastest first; each one is tried only
# when the one before it failed:
#   1. the normal neutron plot (unchanged)
#   2. unknown start: the next best known neutron stars as the bridge, one after another
#   3. the same search with a wider reach (2x, 4x, then every candidate), then the nearest known system
#   4. unknown end: plot to the nearest known system to it; the last few jumps are yours to fly
#   5. Spansh's Galaxy Plotter (no neutron boosts, but it plans fuel stops)
#   6. a straight line at your jump range: the destination as one waypoint, with the jump count
# ---------------------------------------------------------------------------
LIMP_MAX_TRIES = 6                  # bridge candidates plotted before moving on to the next kind of fallback
BRIDGE_REACH_FACTORS = (1.0, 2.0, 4.0, 1000.0)
EDSM_SYSTEM_URL = "https://www.edsm.net/api-v1/system"


def _edsm_coordinates(name: str) -> tuple[float, float, float] | None:
    """Coordinates of a system EDSM knows (a second source when Spansh does not), or None."""
    reply = _spansh_request(EDSM_SYSTEM_URL + "?" + urllib.parse.urlencode({"systemName": name, "showCoordinates": 1}))
    coords = reply.get("coords") if isinstance(reply, dict) else None
    try:
        return (float(coords["x"]), float(coords["y"]), float(coords["z"]))
    except (KeyError, TypeError, ValueError):
        return None


def _any_coordinates(name: str) -> tuple[float, float, float] | None:
    """Where a system is: your own position or journals first, then Spansh, then EDSM. Never raises."""
    if not name:
        return None
    position = _start_coordinates(name)
    if position:
        return position
    for lookup in (_spansh_coordinates, _edsm_coordinates):
        try:
            position = lookup(name)
        except RuntimeError:
            position = None
        if position:
            return position
    return None


def _bridge_ladder(position: tuple[float, float, float], target: str, jump_range: float, multiplier: int):
    """Bridge candidates in the order to try them: best neutron first, then wider searches, then the nearest star."""
    seen: set[str] = set()
    for factor in BRIDGE_REACH_FACTORS:
        try:
            found = _neutron_candidates(position, target, jump_range, multiplier, factor)
        except RuntimeError:
            found = []
        for candidate in found:
            if candidate["system"].casefold() not in seen:
                seen.add(candidate["system"].casefold())
                yield candidate
    for candidate in _nearest_known(position):
        if candidate["system"].casefold() not in seen:
            seen.add(candidate["system"].casefold())
            yield candidate


def _unreachable(error: Exception) -> bool:
    return "could not reach spansh" in str(error).casefold()


def _limp_notes(origin: str, target: str, bridge: dict[str, Any] | None, plot_end: str, tail_miles: float,
                plain: bool) -> str:
    parts = []
    if bridge:
        parts.append(_bridge_text(bridge))
    if plot_end.casefold() != target.casefold():
        parts.append(f"{target} isn't charted either, so the route goes to {plot_end}, "
                     f"{tail_miles:,.0f} ly short of it. The last jumps are yours to fly.")
    if plain:
        parts.append("No neutron route was possible, so this is a plain route without neutron boosts"
                     " (the Galaxy Plotter, with fuel stops).")
    return "\n".join(parts)


def _limp_home(origin: str, target: str, jump_range: float, efficiency: int, multiplier: int, cancelled,
               failure: Exception) -> tuple[list[tuple[str, int]], dict[str, Any]]:
    """Find some route no matter what went wrong with the first plot; see the steps above."""
    spansh_down = _unreachable(failure)
    start_charted = not _unknown_start(failure)
    start_pos = _any_coordinates(origin)
    end_pos = _any_coordinates(target)
    end_charted = True
    if not spansh_down:
        try:
            end_charted = _spansh_coordinates(target) is not None
        except RuntimeError as error:
            spansh_down = _unreachable(error)

    plot_end, tail_jumps, tail_miles = target, 0, 0.0
    if not end_charted and end_pos is not None and not spansh_down:
        near = _nearest_known(end_pos)
        if near:
            plot_end = near[0]["system"]
            tail_miles = near[0]["distance"]
            tail_jumps = max(1, math.ceil(tail_miles / max(jump_range, 1)))
            logger.info("Limp home: %s is uncharted, plotting to %s (%.0f ly short)", target, plot_end, tail_miles)

    def starts():
        if start_charted:
            if plot_end != target:
                yield origin, None
        elif start_pos is not None:
            for bridge in _bridge_ladder(start_pos, plot_end, jump_range, multiplier):
                yield bridge["system"], bridge

    def finish(route, bridge, plain=False):
        if bridge:
            first_leg = max(1, math.ceil(bridge["distance"] / max(jump_range, 1)))
            route = [(origin, 0), (route[0][0], first_leg)] + route[1:]
        if tail_jumps:
            route = route + [(target, tail_jumps)]
        note = _limp_notes(origin, target, bridge, plot_end, tail_miles, plain)
        info = {"system": (bridge or {}).get("system") or plot_end, "distance": float((bridge or {}).get("distance") or 0),
                "neutron": bool((bridge or {}).get("neutron", True)), "note": note}
        return route, info

    first_start, tries, unreachable = None, 0, 0
    if not spansh_down:
        for start, bridge in starts():
            if cancelled():
                raise _PlotCancelled()
            tries += 1
            if tries > LIMP_MAX_TRIES:
                break
            first_start = first_start or (start, bridge)
            try:
                route = _spansh_plot(start, plot_end, jump_range, efficiency, multiplier, cancelled)
            except RuntimeError as error:
                logger.info("Limp home: plotting from %s failed (%s); trying the next one", start, error)
                if _unreachable(error):
                    unreachable += 1
                    if unreachable >= 2:
                        spansh_down = True
                        break
                continue
            return finish(route, bridge)

    if not spansh_down:
        # The Galaxy Plotter: from the best start there was (or yours if it is charted).
        if first_start is None and start_charted:
            first_start = (origin, None)
        if first_start is not None:
            try:
                ship = _galaxy_ship(_read_latest_loadout())
                route, _stops = _spansh_galaxy(first_start[0], plot_end, ship,
                                               {"galaxy_algorithm": "optimistic", "use_injections": False}, cancelled)
                logger.info("Limp home: the Galaxy Plotter found a plain route")
                return finish(route, first_start[1], plain=True)
            except _PlotCancelled:
                raise
            except RuntimeError as error:
                logger.info("Limp home: the Galaxy Plotter could not help either (%s)", error)

    # Last resort, and it always works: one waypoint, the destination, with the straight-line jump count.
    miles = math.dist(start_pos, end_pos) if start_pos is not None and end_pos is not None else 0.0
    jumps = max(1, math.ceil(miles / max(jump_range, 1))) if miles else 1
    how = (f"about {jumps} jumps in a straight line ({miles:,.0f} ly)" if miles
           else "the distance is not known")
    note = (f"Limp-home mode: no route could be calculated right now, so this is a straight line to {target}: "
            f"{how}. Plot each hop with the game's own galaxy map and Navigation will keep count.")
    logger.info("Limp home: straight line to %s (%s)", target, how)
    return [(origin, 0), (target, jumps)], {"system": target, "distance": miles, "neutron": False, "note": note}


def _plot_with_bridge(origin: str, target: str, jump_range: float, efficiency: int, multiplier: int,
                      cancelled) -> tuple[list[tuple[str, int]], dict[str, Any] | None]:
    """Plot normally; if that fails for any reason, go into limp-home mode (see above): a route always comes out."""
    try:
        return _spansh_plot(origin, target, jump_range, efficiency, multiplier, cancelled), None
    except RuntimeError as error:
        failure = error
    logger.info("Plot New Route: the first plot failed (%s); limp-home mode", failure)
    return _limp_home(origin, target, jump_range, efficiency, multiplier, cancelled, failure)


# ---------------------------------------------------------------------------
# Multi-stop trips (Jonathan, 31 Oct 2026): like a car GPS with several stops. Stops marked Fixed stay in the
# order they were listed; Flexible stops are placed wherever the whole trip is shortest. The Rescue tab
# will reuse this to order several rescues. Straight-line distance orders the stops (instant, works offline);
# the plotter then routes each leg.
# ---------------------------------------------------------------------------
ORDER_EXACT_LIMIT = 11          # flexible stops sorted exactly (every order considered); more use nearest-first


def _stop_distance(a: tuple | None, b: tuple | None) -> float:
    """Straight-line ly between two positions; a stop whose position is unknown costs nothing."""
    return math.dist(a, b) if a is not None and b is not None else 0.0


def _order_stops(start: tuple[float, float, float] | None, stops: list[dict[str, Any]],
                 return_to_start: bool = False, keep_last: bool = False) -> tuple[list[dict[str, Any]], float]:
    """Order stops for the shortest trip from start. Each stop is {"name", "fixed", "pos"}; Fixed stops (and any
    stop whose position is unknown) keep their listed order. keep_last pins the last listed stop to the end.
    Returns (the stops in travel order, total ly)."""
    items = [dict(stop) for stop in stops]
    if keep_last and items:
        items[-1]["fixed"] = True
    pinned = [bool(s.get("fixed") or s.get("pos") is None) for s in items]
    fixed = [s for s, is_fixed in zip(items, pinned) if is_fixed]
    flex = [s for s, is_fixed in zip(items, pinned) if not is_fixed]
    k, m = len(fixed), len(flex)
    last_pinned = bool(keep_last and items)
    nodes = flex + fixed                      # ids: 0..m-1 flexible, m..m+k-1 fixed in listed order
    pos = lambda node: start if node < 0 else nodes[node].get("pos")
    full = (1 << m) - 1

    def allowed_fixed(mask: int, i: int) -> bool:
        return i < k and not (last_pinned and i == k - 1 and mask != full)

    if m <= ORDER_EXACT_LIMIT:
        best = {(0, 0, -1): (0.0, None)}
        layers = [[(0, 0, -1)]]
        for _step in range(m + k):
            nxt: dict[tuple[int, int, int], tuple[float, tuple]] = {}
            for state in layers[-1]:
                mask, i, last = state
                cost = best[state][0]
                moves = [(mask | (1 << j), i, j) for j in range(m) if not mask & (1 << j)]
                if allowed_fixed(mask, i):
                    moves.append((mask, i + 1, m + i))
                for move in moves:
                    new_cost = cost + _stop_distance(pos(last), pos(move[2]))
                    if move not in best or new_cost < best[move][0] - 1e-9:
                        best[move] = (new_cost, state)
                        nxt[move] = best[move]
            layers.append(list(nxt))
        finals = [(best[s][0] + (_stop_distance(pos(s[2]), start) if return_to_start else 0.0), s)
                  for s in layers[-1] if s[0] == full and s[1] == k]
        total, state = min(finals, key=lambda item: item[0]) if finals else (0.0, None)
        order: list[int] = []
        while state is not None and state[2] != -1:
            order.append(state[2])
            state = best[state][1]
        order.reverse()
        return [nodes[n] for n in order], total

    # Many flexible stops: go to the nearest allowed stop each time (still honours the order of the Fixed ones).
    mask, i, last, order, total = 0, 0, -1, [], 0.0
    while len(order) < m + k:
        options = [j for j in range(m) if not mask & (1 << j)]
        if allowed_fixed(mask, i):
            options.append(m + i)
        choice = min(options, key=lambda n: _stop_distance(pos(last), pos(n)))
        total += _stop_distance(pos(last), pos(choice))
        order.append(choice)
        if choice >= m:
            i += 1
        else:
            mask |= 1 << choice
        last = choice
    if return_to_start:
        total += _stop_distance(pos(last), start)
    return [nodes[n] for n in order], total


def _plot_trip(origin: str, stops: list[dict[str, Any]], return_to_start: bool, keep_last: bool,
               jump_range: float, efficiency: int, multiplier: int, cancelled, progress=None
               ) -> tuple[list[tuple[str, int]], dict[str, Any]]:
    """Order the stops (Fixed ones keep their place), then plot each leg and join them into one route."""
    start_pos = _any_coordinates(origin)
    items = []
    for stop in stops:
        if cancelled():
            raise _PlotCancelled()
        system = str(stop.get("system") or stop.get("name"))
        items.append({"name": str(stop.get("name") or system), "system": system,
                      "fixed": bool(stop.get("fixed")), "pos": _any_coordinates(system)})
    ordered, miles = _order_stops(start_pos, items, return_to_start, keep_last)
    path = [origin] + [stop["system"] for stop in ordered] + ([origin] if return_to_start else [])
    legs = [(a, b) for a, b in zip(path, path[1:]) if a.casefold() != b.casefold()]
    route: list[tuple[str, int]] = []
    notes: list[str] = []
    for number, (a, b) in enumerate(legs, start=1):
        if cancelled():
            raise _PlotCancelled()
        if progress:
            progress(f"Plotting leg {number} of {len(legs)}: {a} to {b}")
        leg, bridge = _plot_with_bridge(a, b, jump_range, efficiency, multiplier, cancelled)
        if bridge and bridge.get("note"):
            notes.append(f"{a} to {b}: {bridge['note']}")
        route = list(leg) if not route else route + list(leg)[1:]
    if not route:
        raise RuntimeError("Every stop is the system you are already in.")
    names = [origin] + [stop["name"] for stop in ordered] + ([origin] if return_to_start else [])
    unknown = sum(1 for stop in ordered if stop["pos"] is None)
    text = "Trip order: " + " > ".join(names) + (f" ({miles:,.0f} ly in a straight line)" if miles else "")
    if unknown:
        text += f"\n{unknown} stop{'s' if unknown != 1 else ''} with no known position stayed where you listed {'them' if unknown != 1 else 'it'}."
    info = {"system": origin, "distance": float(miles), "neutron": True,
            "note": "\n".join([text] + notes)}
    return route, info


def _bridge_text(bridge: dict[str, Any], kind: str = "neutron") -> str:
    if bridge.get("note"):
        return bridge["note"]
    if kind in KIND_NAMES:
        return (f"Uncharted space, Commander. Spansh doesn't know this system yet.\n"
                f"Your {KIND_NAMES[kind]} starts from {bridge['system']} ({bridge['distance']:.0f} ly).")
    if bridge["neutron"]:
        return (f"Uncharted space, Commander. Spansh doesn't know this system yet.\n"
                f"Bridging via {bridge['system']} ({bridge['distance']:.0f} ly) onto the Neutron Highway.")
    return (f"Uncharted space, Commander. No known neutron nearby, so the route starts from\n"
            f"{bridge['system']} ({bridge['distance']:.0f} ly), the nearest system Spansh knows.")


# ---------------------------------------------------------------------------
# Road to Riches (Spansh): systems with valuable bodies to scan, near you or on
# the way to a destination. The panel's Scan line lists the bodies at each stop.
# ---------------------------------------------------------------------------
SPANSH_RICHES_URL = "https://spansh.co.uk/api/riches/route"
ROUTE_TYPES = ("Neutron Highway", "Road to Riches", "Ammonia Worlds", "Earth-like Worlds", "Rocky and HMC Worlds",
               "Exomastery", "Galaxy Plotter", "Fleet Carrier", "Trade Router", "Multi-Stop Trip")
ROUTE_KINDS = ("neutron", "riches", "ammonia", "earth", "rocky", "exo", "galaxy", "carrier", "trade", "trip")
# Spansh runs these through its Road to Riches search, limited to some kinds of world.
BODY_FILTERS = {"ammonia": ["Ammonia world"], "earth": ["Earth-like world"],
                "rocky": ["Rocky body", "High metal content world"]}
RICHES_LIKE = ("riches",) + tuple(BODY_FILTERS)
KIND_NAMES = {"riches": "Road to Riches", "ammonia": "Ammonia Worlds route", "earth": "Earth-like Worlds route",
              "rocky": "Rocky and HMC Worlds route", "exo": "Exomastery route", "galaxy": "galaxy route",
              "carrier": "Fleet Carrier route", "trade": "Trade route"}
MAX_TRIP_STOPS = 20
MAX_SAVED_TRIPS = 30
SCAN_KINDS = ("riches", "ammonia", "earth", "rocky", "exo")      # route types with bodies to scan (they share the four settings)
RICHES_FIELDS = (("riches_radius", "Search Radius (ly)"), ("riches_max_systems", "Max Systems"),
                 ("riches_min_value", "Min Value (cr)"), ("riches_max_ls", "Max Distance (ls)"))
RICHES_ENOUGH = 5             # fewer systems than this: widen the search by itself
RICHES_MAX_RADIUS = 200       # ly; the widest automatic search
_riches_radius_used = 0.0     # radius of the last Road to Riches search (after widening)
SCAN_SHOWN = 5                # bodies listed on the Scan line before "+N more"
BODY_SHORT = {"Earth-like world": "ELW", "Water world": "WW", "Ammonia world": "AW",
              "High metal content world": "HMC", "Metal-rich body": "Metal-rich",
              "Rocky body": "Rocky", "Rocky Ice world": "Rocky ice", "Icy body": "Icy"}
_route_kind = "neutron"       # "neutron" or "riches"
_route_bodies: dict[str, list[dict[str, Any]]] = {}   # casefolded system -> bodies to scan
_scan_label = None


def _credits(value: float) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    return f"{value / 1000:.0f}k"


def _has_dss() -> bool:
    """Body values include mapping when a Detailed Surface Scanner is fitted (assume yes if unknown)."""
    loadout = _read_latest_loadout()
    if not loadout:
        return True
    return any("detailedsurfacescanner" in str(module.get("Item", "")).lower()
               for module in loadout.get("Modules", []) if isinstance(module, dict))


def _spansh_result(job: Any, cancelled) -> Any:
    """Wait for a queued Spansh job and return its result."""
    deadline = time.monotonic() + SPANSH_MAX_WAIT
    while True:
        if cancelled():
            raise _PlotCancelled()
        reply = _spansh_request(SPANSH_RESULTS_URL + urllib.parse.quote(str(job)))
        if isinstance(reply, dict):
            if reply.get("error"):
                raise RuntimeError(str(reply["error"]))
            if reply.get("status") == "ok" and reply.get("result") is not None:
                return reply["result"]
        if time.monotonic() > deadline:
            raise RuntimeError("Spansh is still calculating - try again in a moment.")
        time.sleep(1.5)


def _spansh_riches(start: str, end: str, jump_range: float, options: dict[str, float], mapping: bool,
                   cancelled, body_types: list[str] | None = None
                   ) -> tuple[list[tuple[str, int]], dict[str, list[dict[str, Any]]]]:
    """Ask Spansh's Road to Riches for systems worth scanning; returns (route, bodies).
    body_types limits it to some kinds of world (Ammonia, Earth-like, Rocky and HMC): any value will do there."""
    params: dict[str, Any] = {"from": start, "range": f"{jump_range:.2f}",
              "radius": int(options["riches_radius"]), "max_results": int(options["riches_max_systems"]),
              "max_distance": int(options["riches_max_ls"]), "min_value": int(options["riches_min_value"]),
              "use_mapping_value": 1 if mapping else 0, "loop": 0}
    if body_types:
        params.update({"body_types": list(body_types), "min_value": 1, "avoid_thargoids": 1})
    if end:
        params["to"] = end
    logger.info("Plot New Route: asking Spansh Road to Riches %s", params)
    reply = _spansh_request(SPANSH_RICHES_URL, params)
    job = reply.get("job") if isinstance(reply, dict) else None
    if not job:
        error = reply.get("error") if isinstance(reply, dict) else None
        raise RuntimeError(str(error) if error else "Spansh did not accept the request.")
    result = _spansh_result(job, cancelled)
    route, bodies = [], {}
    for stop in result if isinstance(result, list) else []:
        if not isinstance(stop, dict) or not stop.get("name"):
            continue
        name = str(stop["name"])
        route.append((name, int(stop.get("jumps") or 0)))
        found = []
        for body in stop.get("bodies") or []:
            if not isinstance(body, dict):
                continue
            full = str(body.get("name") or "")
            short = full[len(name):].strip() if full.casefold().startswith(name.casefold()) else full
            kind = BODY_SHORT.get(str(body.get("subtype") or ""), str(body.get("subtype") or "Body"))
            if body.get("is_terraformable"):
                kind += " (T)"
            value = body.get("estimated_mapping_value" if mapping else "estimated_scan_value") or 0
            try:
                found.append({"name": short or full, "type": kind, "value": int(value),
                              "ls": int(float(body.get("distance_to_arrival") or 0))})
            except (TypeError, ValueError):
                continue
        if found:
            bodies[name.casefold()] = sorted(found, key=lambda item: item["ls"])
    if len(route) < 2 or not bodies:
        raise RuntimeError("Spansh found no systems that match - try a larger radius or a lower value.")
    logger.info("Plot New Route: Road to Riches returned %d systems, %d with bodies", len(route), len(bodies))
    return route, bodies


def _riches_search(start: str, end: str, jump_range: float, options: dict[str, float], mapping: bool,
                   cancelled, fetch=None) -> tuple[list[tuple[str, int]], dict[str, list[dict[str, Any]]]]:
    """Road to Riches that widens its own search radius (up to 200 ly) when too little comes back,
    as in sparsely explored space, so nobody has to guess a radius."""
    global _riches_radius_used
    wanted = min(RICHES_ENOUGH, int(options["riches_max_systems"]))
    radius, best = float(options["riches_radius"]), None
    while True:
        try:
            route, bodies = (fetch or _spansh_riches)(start, end, jump_range, dict(options, riches_radius=radius),
                                           mapping, cancelled)
            best = (route, bodies, radius)
        except RuntimeError as error:
            if _unknown_start(error) or "found no systems" not in str(error):
                raise
        if (best is not None and len(best[1]) >= wanted) or radius >= RICHES_MAX_RADIUS:
            break
        radius = min(RICHES_MAX_RADIUS, radius * 2)
        logger.info("Plot New Route: few riches found; widening the search to %.0f ly", radius)
    if best is None:
        raise RuntimeError("Spansh found no systems that match, even within 200 ly - try a lower value.")
    _riches_radius_used = best[2]
    return best[0], best[1]


SPANSH_EXO_URL = "https://spansh.co.uk/api/exobiology/route"


def _spansh_exo(start: str, end: str, jump_range: float, options: dict[str, float], _mapping: bool,
                cancelled) -> tuple[list[tuple[str, int]], dict[str, list[dict[str, Any]]]]:
    """Spansh's Exomastery: bodies with valuable biology. Thargoid systems are always avoided."""
    params = {"from": start, "range": f"{jump_range:.2f}",
              "radius": int(options["riches_radius"]), "max_results": int(options["riches_max_systems"]),
              "max_distance": int(options["riches_max_ls"]), "min_value": int(options["riches_min_value"]),
              "avoid_thargoids": 1, "loop": 0}
    if end:
        params["to"] = end
    logger.info("Plot New Route: asking Spansh Exomastery %s", params)
    reply = _spansh_request(SPANSH_EXO_URL, params)
    job = reply.get("job") if isinstance(reply, dict) else None
    if not job:
        error = reply.get("error") if isinstance(reply, dict) else None
        raise RuntimeError(str(error) if error else "Spansh did not accept the request.")
    result = _spansh_result(job, cancelled)
    route, bodies = [], {}
    for stop in result if isinstance(result, list) else []:
        if not isinstance(stop, dict) or not stop.get("name"):
            continue
        name = str(stop["name"])
        route.append((name, int(stop.get("jumps") or 0)))
        found = []
        for body in stop.get("bodies") or []:
            if not isinstance(body, dict):
                continue
            full = str(body.get("name") or "")
            short = full[len(name):].strip() if full.casefold().startswith(name.casefold()) else full
            species = []
            for landmark in body.get("landmarks") or []:
                if isinstance(landmark, dict):
                    try:
                        species.append((str(landmark.get("subtype") or landmark.get("type") or "Species"),
                                        int(landmark.get("value") or 0)))
                    except (TypeError, ValueError):
                        continue
            if species:
                species.sort(key=lambda item: -item[1])
                found.append({"name": short or full, "type": "", "value": sum(value for _, value in species),
                              "ls": int(float(body.get("distance_to_arrival") or 0)), "species": species})
        if found:
            bodies[name.casefold()] = sorted(found, key=lambda item: item["ls"])
    if len(route) < 2 or not bodies:
        raise RuntimeError("Spansh found no systems that match - try a larger radius or a lower value.")
    logger.info("Plot New Route: Exomastery returned %d systems, %d with biology", len(route), len(bodies))
    return route, bodies


def _fetch_for(kind: str):
    """The search function for a route kind (None: the plain Road to Riches)."""
    if kind == "exo":
        return _spansh_exo
    if kind in BODY_FILTERS:
        return lambda *args: _spansh_riches(*args, body_types=BODY_FILTERS[kind])
    return None


def _plot_riches(origin: str, end: str, jump_range: float, multiplier: int, options: dict[str, float],
                 cancelled, fetch=None) -> tuple[list[tuple[str, int]], dict[str, Any] | None, dict[str, list[dict[str, Any]]]]:
    """Road to Riches, with the uncharted-space bridge when Spansh doesn't know the start."""
    mapping = _has_dss()
    try:
        route, bodies = _riches_search(origin, end, jump_range, options, mapping, cancelled, fetch)
        return route, None, bodies
    except RuntimeError as error:
        if not _unknown_start(error):
            raise
    position = _start_coordinates(origin)
    if position is None:
        raise RuntimeError(f"Spansh doesn't know {origin} yet. A bridge route needs your"
                           " current system as the Start System.")
    bridge = _find_bridge(position, end, jump_range, multiplier)
    if cancelled():
        raise _PlotCancelled()
    route, bodies = _riches_search(bridge["system"], end, jump_range, options, mapping, cancelled, fetch)
    first_leg = max(1, math.ceil(bridge["distance"] / jump_range))
    return [(origin, 0), (route[0][0], first_leg)] + route[1:], bridge, bodies


def _count(number: int, one: str, many: str | None = None) -> str:
    return f"{number} {one if number == 1 else (many or one + 's')}"


def _route_summary(route: list[tuple[str, int]], kind: str, bodies: dict[str, list[dict[str, Any]]]) -> str:
    total = sum(jumps for _, jumps in route)
    if kind == "galaxy":
        refuels = sum(1 for item in bodies.values() if isinstance(item, dict) and item.get("refuel"))
        boosts = sum(1 for item in bodies.values() if isinstance(item, dict) and item.get("neutron"))
        injects = sum(1 for item in bodies.values() if isinstance(item, dict) and item.get("inject"))
        line = (f"{len(route)} waypoints, {total} jumps: {boosts} neutron boost{'s' if boosts != 1 else ''}, "
                f"{refuels} refuel stop{'s' if refuels != 1 else ''}"
                + (f", {injects} FSD injection{'s' if injects != 1 else ''}." if injects else "."))
        have = _injections_available()[0]
        if injects and 0 <= have < injects:
            line += f"\nNot enough materials: the route needs {injects} premium injections, you can make {have}."
        if _galaxy_last_ship.get("check", 0) > 0.5:
            line += (f"\nNote: the plugin's jump range for your ship ({_galaxy_last_ship['range']:.2f} ly)"
                     f" differs from the game's ({_galaxy_last_ship['game_range']:.2f} ly).")
        if not _galaxy_last_ship.get("scoop", True):
            line += "\nNo fuel scoop fitted: Spansh plans refuels at scoopable stars."
        return line
    if kind == "exo":
        species = sum(len(item.get("species", [])) for items in bodies.values() for item in items)
        planets = sum(len(items) for items in bodies.values())
        value = sum(item["value"] for items in bodies.values() for item in items)
        return (f"{_count(len(bodies), 'system')}, {_count(planets, 'body', 'bodies')}, {species} species to scan, "
                f"about {total} jumps.\n"
                f"Estimated value: {_credits(value)} cr (before any first-footfall bonus)"
                + (f"\nSearch widened to {_riches_radius_used:.0f} ly to find enough systems."
                   if _riches_radius_used > float(_settings.get("riches_radius", 25)) else ""))
    if kind == "carrier":
        used = sum(float(item.get("fuel_used") or 0) for item in bodies.values() if isinstance(item, dict))
        stops = [item for item in bodies.values() if isinstance(item, dict) and item.get("restock")]
        return (f"{_count(max(0, len(route) - 1), 'carrier jump')}, about {used:.0f} t of tritium used.\n"
                f"{_count(len(stops), 'restock stop')}: buy tritium there before you jump on.")
    if kind == "trade":
        profit = sum(int(item.get("profit") or 0) for item in bodies.values() if isinstance(item, dict))
        trades = sum(1 for item in bodies.values() if isinstance(item, dict) and item.get("sell"))
        return (f"{_count(trades, 'trade')}, about {_credits(profit)} cr profit.\n"
                "Jump counts are estimates; prices change, so check the market when you arrive.")
    if kind not in RICHES_LIKE:
        return f"{len(route)} waypoints, about {total} jumps."
    count = sum(len(items) for items in bodies.values())
    value = sum(item["value"] for items in bodies.values() for item in items)
    return (f"{_count(len(bodies), 'system')}, {_count(count, 'body', 'bodies')} to scan, about {total} jumps.\n"
            f"Estimated value: {_credits(value)} cr" + ("" if _has_dss() else " (scan only, no DSS fitted)")
            + (f"\nSearch widened to {_riches_radius_used:.0f} ly to find enough systems."
               if _riches_radius_used > float(_settings.get("riches_radius", 25)) else ""))


def _waypoint_word() -> str:
    return {"exo": "Stop", "galaxy": "Waypoint", "carrier": "Jump", "trade": "Stop"}.get(_route_kind, "Stop" if _route_kind in RICHES_LIKE else "Neutron")


def _build_scan_label(row: int) -> None:
    global _scan_label
    _scan_label = tk.Label(_page, anchor=tk.W, justify=tk.LEFT, wraplength=320)
    _scan_label.grid(row=row, column=0, sticky=tk.W)
    _scan_label.grid_remove()


def _refresh_scan() -> None:
    """Road to Riches: list the bodies at this stop (when you are there), else at the next one."""
    if not _widget_alive(_scan_label):
        return
    text = ""
    if _route_kind == "galaxy" and _route_systems and not _settings.get("collapsed"):
        physical = str(_snapshot.get("location", {}).get("system_name") or "").casefold()
        current, following = _current_system(), _next_system()
        here = _route_bodies.get(current.casefold()) if current else None
        ahead = _route_bodies.get(following.casefold()) if following else None
        at_here = isinstance(here, dict) and physical == current.casefold()
        if at_here and here.get("refuel") and here.get("inject"):
            text = "Refuel and inject here: scoop, then synthesise a premium FSD injection before jumping."
        elif at_here and here.get("inject"):
            text = "Inject here: synthesise a premium FSD injection before your next jump."
        elif at_here and here.get("refuel"):
            text = "Refuel here: scoop before your next jump."
        elif isinstance(ahead, dict) and ahead.get("inject"):
            text = f"FSD injection next: synthesise one at {following} before jumping on."
        elif isinstance(ahead, dict) and ahead.get("refuel"):
            text = f"Refuel stop next: scoop at {following}."
    if _route_kind in ("carrier", "trade") and _route_systems and not _settings.get("collapsed"):
        physical = str(_snapshot.get("location", {}).get("system_name") or "").casefold()
        current, following = _current_system(), _next_system()
        here = _route_bodies.get(current.casefold()) if current else None
        ahead = _route_bodies.get(following.casefold()) if following else None
        at_here = isinstance(here, dict) and physical == current.casefold()
        if _route_kind == "carrier":
            if at_here and here.get("restock"):
                text = f"Restock tritium here: {int(here['restock'])} t."
            elif isinstance(ahead, dict) and ahead.get("restock"):
                text = f"Restock tritium next: {int(ahead['restock'])} t at {following}."
        elif at_here:
            text = _trade_text("Trade here", here)
        elif isinstance(ahead, dict):
            text = _trade_text("Next trade", ahead)
    if _route_kind in SCAN_KINDS and _route_systems and not _settings.get("collapsed"):
        physical = str(_snapshot.get("location", {}).get("system_name") or "").casefold()
        current, following = _current_system(), _next_system()
        if current and physical == current.casefold() and _route_bodies.get(physical):
            word, items = "Scan here", _route_bodies[physical]
        elif following and _route_bodies.get(following.casefold()):
            word, items = "Next scan", _route_bodies[following.casefold()]
        else:
            items = []
        if items and _route_kind == "exo":
            # Exomastery: the nearest body with biology, then its species (most valuable first).
            body = items[0]
            species = body.get("species") or []
            shown = ", ".join(f"{name} {_credits(value)}" for name, value in species[:3])
            more = len(species) - 3 + sum(len(item.get("species") or []) for item in items[1:])
            text = f"{word}: {body['name']}: {shown}" + (f", +{more} more" if more > 0 else "")
        elif items:
            shown = ", ".join(f"{item['name']} {item['type']} {_credits(item['value'])}"
                              for item in items[:SCAN_SHOWN])
            more = f", +{len(items) - SCAN_SHOWN} more" if len(items) > SCAN_SHOWN else ""
            text = f"{word}: {shown}{more}"
    if text:
        _scan_label.configure(text=text)
        _scan_label.grid()
    else:
        _scan_label.grid_remove()


# ---------------------------------------------------------------------------
# Fuel warnings: the game writes your fuel after every jump and the star class
# of every jump in a plotted route, so the plugin can warn before fuel runs out.
# ---------------------------------------------------------------------------
SCOOPABLE = "KGBFOAM"
FUEL_MARGINS = {"relaxed": 1, "normal": 2, "cautious": 4}   # spare jumps of fuel wanted
FUEL_CHOICES = (("off", "Off"), ("relaxed", "Relaxed"), ("normal", "Normal"), ("cautious", "Cautious"))
_fuel_used: list[float] = []      # fuel used by recent jumps (t)
_next_star_class = ""             # from StartJump: the star you are jumping to
_arrival_star_class = ""          # the star you arrived at
_fuel_last_warning: tuple[str, str] | None = None


def _add_fuel_menu(menu: tk.Menu) -> None:
    sub = tk.Menu(menu, tearoff=0)
    choice = tk.StringVar(menu, value=str(_settings.get("fuel_safety", "normal")))
    menu._fuel_choice = choice            # keep the variable alive with the menu
    for value, label in FUEL_CHOICES:
        sub.add_radiobutton(label=label, value=value, variable=choice,
                            command=lambda chosen=value: _set_fuel_safety(chosen))
    menu.add_cascade(label="Fuel Warnings", menu=sub)


def _set_fuel_safety(value: str) -> None:
    _settings["fuel_safety"] = value
    _save_settings()
    _set_status("Fuel warnings off." if value == "off" else f"Fuel warnings: {value.title()}.")


def _note_fuel(entry: dict[str, Any]) -> None:
    global _next_star_class, _arrival_star_class
    event = entry.get("event")
    if event == "StartJump" and entry.get("JumpType") == "Hyperspace":
        _next_star_class = str(entry.get("StarClass") or "")
    elif event == "FSDJump":
        _arrival_star_class, _next_star_class = _next_star_class, ""
        try:
            used = float(entry.get("FuelUsed") or 0)
        except (TypeError, ValueError):
            used = 0.0
        if used > 0:
            _fuel_used.append(used)
            del _fuel_used[:-6]
        _fuel_check(str(entry.get("StarSystem") or ""), entry.get("FuelLevel"))
    elif event == "NavRoute":
        _fuel_check(str(_snapshot.get("location", {}).get("system_name") or ""), None)
    elif event in ("Location", "CarrierJump"):
        _arrival_star_class = ""
    if event == "JetConeBoost":
        _galaxy_state["supercharged"] = True
    elif event in ("FSDJump", "Location", "CarrierJump", "Died"):
        _galaxy_state["supercharged"] = False


def _fuel_warning(system: str, fuel: float | None, route: list[dict[str, Any]], margin: int) -> str:
    """The warning to show for this fuel level and plotted route ('' when all is well)."""
    if fuel is None or not _fuel_used:
        return ""
    per_jump = max(sum(_fuel_used[-4:]) / len(_fuel_used[-4:]), 0.01)
    jumps = int(fuel // per_jump)
    names = [str(item.get("StarSystem") or "") for item in route]
    folded = [name.casefold() for name in names]
    here = folded.index(system.casefold()) if system.casefold() in folded else -1
    ahead = route[here + 1:] if here >= 0 else []     # a route that doesn't include you is stale
    if not ahead and not _route_systems:
        return ""                       # nothing plotted and no route loaded
    loadout = _read_latest_loadout() or {}
    scoop = any("fuelscoop" in str(module.get("Item", "")).lower()
                for module in loadout.get("Modules", []) if isinstance(module, dict))
    left = f"about {jumps} jump{'s' if jumps != 1 else ''} of fuel"
    if not loadout:
        scoop = True                    # unknown ship: only warn about low fuel below
    if not scoop:
        if jumps <= margin or (ahead and jumps < len(ahead) + margin):
            return f"Fuel check: {left} and no fuel scoop fitted. Plan a refuelling stop."
        return ""
    next_scoop = next((index for index, item in enumerate(ahead, start=1)
                       if str(item.get("StarClass") or "")[:1] in SCOOPABLE and str(item.get("StarClass") or "")), None)
    if _arrival_star_class[:1] in SCOOPABLE and _arrival_star_class:
        gap = next_scoop or len(ahead)
        if jumps <= margin or jumps < gap + margin:
            where = (f"the next scoopable star is {gap} jump{'s' if gap != 1 else ''} away" if next_scoop
                     else "no scoopable star is left on this leg")
            return f"Fuel check: top up here ({_arrival_star_class} star). {left[0].upper() + left[1:]}, and {where}."
        return ""
    if next_scoop is None:
        if ahead and jumps < len(ahead) + margin:
            return f"Fuel check: {left} and no scoopable star on this leg. Re-plot via a scoopable star."
    elif jumps < next_scoop:
        return (f"Fuel check: {left}, but the next scoopable star ({names[here + next_scoop]})"
                f" is {next_scoop} jumps away. Re-plot via a closer scoopable star.")
    elif jumps < next_scoop + margin:
        return f"Fuel check: {left}. Top up at {names[here + next_scoop]} ({next_scoop} jumps ahead)."
    if jumps <= margin:
        return f"Fuel check: {left}. Top up at the next scoopable star."
    return ""


def _fuel_check(system: str, fuel_level: Any) -> None:
    global _fuel_last_warning
    margin = FUEL_MARGINS.get(str(_settings.get("fuel_safety", "normal")))
    if margin is None or not system:
        return
    fuel = None
    try:
        fuel = float(fuel_level) if fuel_level is not None else None
    except (TypeError, ValueError):
        fuel = None
    if fuel is None:
        status = _read_journal_json("Status.json") or {}
        try:
            fuel = float((status.get("Fuel") or {}).get("FuelMain"))
        except (TypeError, ValueError):
            fuel = None
    navroute = _read_journal_json("NavRoute.json") or {}
    route = [item for item in navroute.get("Route") or [] if isinstance(item, dict)]
    message = _fuel_warning(system, fuel, route, margin)
    if message and _fuel_last_warning != (system.casefold(), message):
        _fuel_last_warning = (system.casefold(), message)
        logger.info("%s", message)
        _set_status(message)


# ---------------------------------------------------------------------------
# Galaxy Plotter (Spansh's exact plotter): every jump, fuel-aware, using your
# ship's real FSD. The ship is read from the game's Loadout record; FSD stats
# come from coriolis-data (EDCD). The game data is (c) Frontier Developments plc.
# ---------------------------------------------------------------------------
SPANSH_GALAXY_URL = "https://spansh.co.uk/api/generic/route"
GALAXY_ALGORITHMS = (("Optimistic (fastest)", "optimistic"), ("Pessimistic", "pessimistic"),
                     ("Guided", "guided"), ("Fewest refuels", "fuel"), ("Fewest refuels and jumps", "fuel_jumps"))
GUARDIAN_BOOST = {1: 4.0, 2: 6.0, 3: 7.75, 4: 9.25, 5: 10.5}   # ly, by Guardian FSD Booster size
GALAXY_RESERVE_JUMPS = {"off": 0, "relaxed": 0, "normal": 1, "cautious": 2}   # fuel kept back, in max jumps
_galaxy_state: dict[str, Any] = {"supercharged": False}
_galaxy_last_ship: dict[str, Any] = {}
FSD_STATS = {   # symbol -> [(optimal mass, max fuel per jump, fuel multiplier, fuel power), ...]
    "int_hyperdrive_overcharge_size2_class1": [(60, 0.6, 0.008, 2.0)],
    "int_hyperdrive_overcharge_size2_class2": [(90, 0.9, 0.012, 2.0)],
    "int_hyperdrive_overcharge_size2_class3": [(90, 0.9, 0.012, 2.0)],
    "int_hyperdrive_overcharge_size2_class4": [(90, 0.9, 0.012, 2.0)],
    "int_hyperdrive_overcharge_size2_class5": [(100, 1, 0.013, 2.0)],
    "int_hyperdrive_overcharge_size3_class1": [(100, 1.2, 0.008, 2.15)],
    "int_hyperdrive_overcharge_size3_class2": [(150, 1.8, 0.012, 2.15)],
    "int_hyperdrive_overcharge_size3_class3": [(150, 1.8, 0.012, 2.15)],
    "int_hyperdrive_overcharge_size3_class4": [(150, 1.8, 0.012, 2.15)],
    "int_hyperdrive_overcharge_size3_class5": [(167, 1.9, 0.013, 2.15)],
    "int_hyperdrive_overcharge_size4_class1": [(350, 2, 0.008, 2.3)],
    "int_hyperdrive_overcharge_size4_class2": [(525, 3, 0.012, 2.3)],
    "int_hyperdrive_overcharge_size4_class3": [(525, 3, 0.012, 2.3)],
    "int_hyperdrive_overcharge_size4_class4": [(525, 3, 0.012, 2.3)],
    "int_hyperdrive_overcharge_size4_class5": [(585, 3.2, 0.013, 2.3)],
    "int_hyperdrive_overcharge_size5_class1": [(700, 3.3, 0.008, 2.45)],
    "int_hyperdrive_overcharge_size5_class2": [(1050, 5, 0.012, 2.45)],
    "int_hyperdrive_overcharge_size5_class3": [(1050, 5, 0.012, 2.45)],
    "int_hyperdrive_overcharge_size5_class4": [(1050, 5, 0.012, 2.45)],
    "int_hyperdrive_overcharge_size5_class5": [(1175, 5.2, 0.013, 2.45), (1175, 5.2, 0.012, 2.45)],
    "int_hyperdrive_overcharge_size6_class1": [(1200, 5.3, 0.008, 2.6)],
    "int_hyperdrive_overcharge_size6_class2": [(1800, 8, 0.012, 2.6)],
    "int_hyperdrive_overcharge_size6_class3": [(1800, 8, 0.012, 2.6)],
    "int_hyperdrive_overcharge_size6_class4": [(1800, 8, 0.012, 2.6)],
    "int_hyperdrive_overcharge_size6_class5": [(2000, 8.3, 0.013, 2.6)],
    "int_hyperdrive_overcharge_size7_class1": [(1800, 8.5, 0.008, 2.75)],
    "int_hyperdrive_overcharge_size7_class2": [(2700, 12.8, 0.012, 2.75)],
    "int_hyperdrive_overcharge_size7_class3": [(2700, 12.8, 0.012, 2.75)],
    "int_hyperdrive_overcharge_size7_class4": [(2700, 12.8, 0.012, 2.75)],
    "int_hyperdrive_overcharge_size7_class5": [(3000, 13.1, 0.013, 2.75)],
    "int_hyperdrive_overcharge_size8_class1": [(2800, 13.6, 0.008, 2.9)],
    "int_hyperdrive_overcharge_size8_class2": [(4200, 20.4, 0.012, 2.9)],
    "int_hyperdrive_overcharge_size8_class3": [(4200, 20.4, 0.012, 2.9)],
    "int_hyperdrive_overcharge_size8_class4": [(4200, 20.4, 0.012, 2.9)],
    "int_hyperdrive_overcharge_size8_class5": [(4670, 20.7, 0.013, 2.9)],
    "int_hyperdrive_overcharge_size8_class5_overchargebooster_mkii": [(4670, 6.8, 0.011, 2.5025)],
    "int_hyperdrive_size2_class1": [(48, 0.6, 0.011, 2)],
    "int_hyperdrive_size2_class2": [(54, 0.6, 0.01, 2)],
    "int_hyperdrive_size2_class3": [(60, 0.6, 0.008, 2)],
    "int_hyperdrive_size2_class4": [(75, 0.8, 0.01, 2)],
    "int_hyperdrive_size2_class5": [(90, 0.9, 0.012, 2)],
    "int_hyperdrive_size3_class1": [(80, 1.2, 0.011, 2.15)],
    "int_hyperdrive_size3_class2": [(90, 1.2, 0.01, 2.15)],
    "int_hyperdrive_size3_class3": [(100, 1.2, 0.008, 2.15)],
    "int_hyperdrive_size3_class4": [(125, 1.5, 0.01, 2.15)],
    "int_hyperdrive_size3_class5": [(150, 1.8, 0.012, 2.15)],
    "int_hyperdrive_size4_class1": [(280, 2, 0.011, 2.3)],
    "int_hyperdrive_size4_class2": [(315, 2, 0.01, 2.3)],
    "int_hyperdrive_size4_class3": [(350, 2, 0.008, 2.3)],
    "int_hyperdrive_size4_class4": [(437.5, 2.5, 0.01, 2.3)],
    "int_hyperdrive_size4_class5": [(525, 3, 0.012, 2.3)],
    "int_hyperdrive_size5_class1": [(560, 3.3, 0.011, 2.45)],
    "int_hyperdrive_size5_class2": [(630, 3.3, 0.01, 2.45)],
    "int_hyperdrive_size5_class3": [(700, 3.3, 0.008, 2.45)],
    "int_hyperdrive_size5_class4": [(875, 4.1, 0.01, 2.45)],
    "int_hyperdrive_size5_class5": [(1050, 5, 0.012, 2.45)],
    "int_hyperdrive_size6_class1": [(960, 5.3, 0.011, 2.6)],
    "int_hyperdrive_size6_class2": [(1080, 5.3, 0.01, 2.6)],
    "int_hyperdrive_size6_class3": [(1200, 5.3, 0.008, 2.6)],
    "int_hyperdrive_size6_class4": [(1500, 6.6, 0.01, 2.6)],
    "int_hyperdrive_size6_class5": [(1800, 8, 0.012, 2.6)],
    "int_hyperdrive_size7_class1": [(1440, 8.5, 0.011, 2.75)],
    "int_hyperdrive_size7_class2": [(1620, 8.5, 0.01, 2.75)],
    "int_hyperdrive_size7_class3": [(1800, 8.5, 0.008, 2.75)],
    "int_hyperdrive_size7_class4": [(2250, 10.6, 0.01, 2.75)],
    "int_hyperdrive_size7_class5": [(2700, 12.8, 0.012, 2.75)],
}


def _galaxy_ship(loadout: dict[str, Any] | None) -> dict[str, Any]:
    """The ship numbers Spansh's Galaxy Plotter needs, from the game's Loadout record.
    Checked against the game's own MaxJumpRange; engineered FSD values are used as recorded."""
    if not loadout:
        raise RuntimeError("Galaxy Plotter needs your ship's details. Board your ship, then try again.")
    modules = [module for module in loadout.get("Modules") or [] if isinstance(module, dict)]
    fsd = next((module for module in modules if str(module.get("Slot", "")).lower() == "frameshiftdrive"), None)
    item = str((fsd or {}).get("Item", "")).lower()
    variants = FSD_STATS.get(item)
    if not variants:
        raise RuntimeError(f"Galaxy Plotter doesn't know this FSD yet ({(fsd or {}).get('Item', 'none')}).\n"
                           "Neutron Highway still works with any FSD.")
    engineered = {}
    for modifier in ((fsd or {}).get("Engineering") or {}).get("Modifiers") or []:
        if isinstance(modifier, dict):
            try:
                engineered[str(modifier.get("Label", "")).lower()] = float(modifier.get("Value"))
            except (TypeError, ValueError):
                pass
    boost = 0.0
    for module in modules:
        found = re.match(r"int_guardianfsdbooster_size(\d)", str(module.get("Item", "")).lower())
        if found:
            boost = GUARDIAN_BOOST.get(int(found.group(1)), 0.0)
    capacity = loadout.get("FuelCapacity") or {}
    try:
        unladen = float(loadout.get("UnladenMass") or 0)
        tank, reserve = float(capacity.get("Main") or 0), float(capacity.get("Reserve") or 0)
        game_range = float(loadout.get("MaxJumpRange") or 0)
    except (TypeError, ValueError, AttributeError):
        unladen = tank = reserve = game_range = 0.0
    if unladen <= 0 or tank <= 0:
        raise RuntimeError("Galaxy Plotter could not read your ship's mass and fuel tank. Board your ship, then try again.")
    best = None
    for optmass, maxfuel, fuelmul, fuelpower in variants:      # some drives have two listed variants
        optmass = engineered.get("fsdoptimalmass", optmass)
        maxfuel = engineered.get("maxfuelperjump", maxfuel)
        reach = optmass / (unladen + maxfuel) * (maxfuel / fuelmul) ** (1 / fuelpower) + boost
        check = abs(reach - game_range) if game_range > 0 else 0.0
        if best is None or check < best["check"]:
            best = {"optimal_mass": optmass, "max_fuel_per_jump": maxfuel, "fuel_multiplier": fuelmul,
                    "fuel_power": fuelpower, "range": reach, "check": check}
    best.update(base_mass=unladen + reserve, tank_size=tank, internal_tank_size=reserve, range_boost=boost,
                game_range=game_range, multiplier=6 if "mkii" in item else 4,
                scoop=any("fuelscoop" in str(module.get("Item", "")).lower() for module in modules))
    logger.info("Galaxy Plotter ship: %s, %.2f ly by formula vs %.2f ly in game", item, best["range"], game_range)
    return best


PREMIUM_INJECTION = ("carbon", "germanium", "arsenic", "niobium", "yttrium", "polonium")   # 1 of each
_materials_raw: dict[str, int] = {}     # Raw materials, kept current by EDMC's state


def _note_materials(state: dict[str, Any]) -> None:
    raw = state.get("Raw") if isinstance(state, dict) else None
    if isinstance(raw, dict) and raw:
        _materials_raw.clear()
        for name, count in raw.items():
            try:
                _materials_raw[str(name).lower()] = int(count)
            except (TypeError, ValueError):
                pass


def _journal_materials() -> dict[str, int]:
    """Fallback: the newest Materials event in the game journal."""
    folder = _journal_dir()
    if not folder:
        return {}
    try:
        files = sorted((os.path.join(folder, item) for item in os.listdir(folder)
                        if item.startswith("Journal") and item.endswith(".log")),
                       key=os.path.getmtime, reverse=True)[:3]
    except OSError:
        return {}
    for path in files:
        found = None
        try:
            with open(path, encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    if '"Materials"' in line:
                        try:
                            record = json.loads(line)
                        except ValueError:
                            continue
                        if record.get("event") == "Materials":
                            found = record
        except OSError:
            continue
        if found:
            return {str(item.get("Name", "")).lower(): int(item.get("Count") or 0)
                    for item in found.get("Raw") or [] if isinstance(item, dict)}
    return {}


def _injections_available() -> tuple[int, str]:
    """(premium FSD injections your materials allow, the material that runs out first); -1 if unknown."""
    stock = dict(_materials_raw) or _journal_materials()
    if not stock:
        return -1, ""
    counts = {name: int(stock.get(name, 0)) for name in PREMIUM_INJECTION}
    limit = min(counts, key=counts.get)
    return counts[limit], limit


def _injection_note() -> str:
    have, limit = _injections_available()
    if have < 0:
        return "Your materials aren't known yet (they load when the game starts)."
    if have == 0:
        return f"Not enough materials for a premium FSD injection (no {limit.title()})."
    return f"Your materials make {have} premium injection{'s' if have != 1 else ''} ({limit.title()} runs out first)."


def _planning_range(loadout: dict[str, Any], game_range: float) -> tuple[float, str]:
    """The jump range routes are planned with: a FULL fuel tank plus the cargo aboard now.
    The game's MaxJumpRange is the best case (almost no fuel), so legs planned with it can be a few
    ly too long once the tank is full, and Elite then adds an extra jump (found 24 Oct: IR-N d6-254
    to GA-A d39 was 531.5 ly; with 58.6 t of fuel the supercharged reach was about 529 ly)."""
    try:
        ship = _galaxy_ship(loadout)
    except RuntimeError:
        return game_range, ""          # FSD not in the table: keep the game's own figure
    cargo = _cargo_count()             # cargo and limpets, 1 t each
    unladen = ship["base_mass"] - ship["internal_tank_size"]
    mass = unladen + ship["tank_size"] + cargo
    reach = (ship["optimal_mass"] / mass * (ship["max_fuel_per_jump"] / ship["fuel_multiplier"])
             ** (1 / ship["fuel_power"]) + ship["range_boost"])
    if not 0 < reach <= MAX_SANE_RANGE or reach > game_range + 0.5:
        return game_range, ""
    return reach, "full tank" + (f" + {cargo} t cargo" if cargo else "")


def _spansh_galaxy(start: str, end: str, ship: dict[str, Any], options: dict[str, Any], cancelled
                   ) -> tuple[list[tuple[str, int]], dict[str, dict[str, Any]]]:
    """Ask Spansh's Galaxy Plotter for an exact route. Keeps the jumps that matter as waypoints:
    neutron boosts, refuel stops and the destination (the game plots the jumps between)."""
    reserve = ship["max_fuel_per_jump"] * GALAXY_RESERVE_JUMPS.get(str(_settings.get("fuel_safety", "normal")), 1)
    params = {"source": start, "destination": end,
              "is_supercharged": 1 if _galaxy_state.get("supercharged") else 0, "use_supercharge": 1,
              "use_injections": 1 if options.get("use_injections") else 0,
              # Tested 24 Oct (Sag A* to Beagle Point): use_injections alone = 114 jumps / 26 injections;
              # adding use_injections_when_required gave 249 injections, and that flag alone gave none.
              "use_injections_when_required": 0,
              "exclude_secondary": 1, "refuel_every_scoopable": 1,
              "fuel_power": ship["fuel_power"], "fuel_multiplier": ship["fuel_multiplier"],
              "optimal_mass": round(ship["optimal_mass"], 4), "base_mass": round(ship["base_mass"], 4),
              "tank_size": ship["tank_size"], "internal_tank_size": ship["internal_tank_size"],
              "reserve_size": round(reserve, 2), "max_fuel_per_jump": ship["max_fuel_per_jump"],
              "range_boost": ship["range_boost"], "max_time": 60, "cargo": _cargo_count(),
              "algorithm": str(options.get("galaxy_algorithm") or "optimistic"),
              "supercharge_multiplier": ship["multiplier"],
              "injection_multiplier": 2 if options.get("use_injections") else 0}   # 2 = premium
    logger.info("Plot New Route: asking Spansh Galaxy Plotter %s", params)
    reply = _spansh_request(SPANSH_GALAXY_URL, params)
    job = reply.get("job") if isinstance(reply, dict) else None
    if not job:
        error = reply.get("error") if isinstance(reply, dict) else None
        raise RuntimeError(str(error) if error else "Spansh did not accept the request.")
    result = _spansh_result(job, cancelled)
    jumps = [jump for jump in (result.get("jumps") if isinstance(result, dict) else None) or []
             if isinstance(jump, dict) and jump.get("name")]
    if isinstance(result, dict) and result.get("incomplete"):
        # Spansh ran out of search time and returned only the closest it got.
        try:
            short = f" (it got within {float(jumps[-1].get('distance_to_destination') or 0):,.0f} ly)"
        except (IndexError, TypeError, ValueError):
            short = ""
        logger.info("Galaxy Plotter: Spansh returned an incomplete route%s", short)
        raise RuntimeError(f"Spansh couldn't finish this galaxy route in time{short}.\n"
                           + ("Try again without FSD injections, " if options.get("use_injections") else "Try ")
                           + "a closer destination, or the Neutron Highway route type.")
    if len(jumps) < 2:
        raise RuntimeError("Spansh returned an empty route.")
    route, stops, count = [(str(jumps[0]["name"]), 0)], {}, 0
    if jumps[0].get("must_inject") or jumps[0].get("must_refuel"):
        stops[str(jumps[0]["name"]).casefold()] = {"refuel": bool(jumps[0].get("must_refuel")), "neutron": False,
                                                   "scoopable": bool(jumps[0].get("is_scoopable")),
                                                   "inject": bool(jumps[0].get("must_inject"))}
    for index, jump in enumerate(jumps[1:], start=1):
        count += 1
        # Spansh marks "inject" on the system where you synthesise it, before jumping on
        # (like "refuel"), so keep that system and the one the boosted jump reaches.
        after_inject = bool(jumps[index - 1].get("must_inject"))
        if (jump.get("has_neutron") or jump.get("must_refuel") or jump.get("must_inject") or after_inject
                or index == len(jumps) - 1):
            name = str(jump["name"])
            route.append((name, count))
            count = 0
            stops[name.casefold()] = {"refuel": bool(jump.get("must_refuel")), "neutron": bool(jump.get("has_neutron")),
                                      "scoopable": bool(jump.get("is_scoopable")),
                                      "inject": bool(jump.get("must_inject"))}
    logger.info("Plot New Route: Galaxy Plotter returned %d jumps, kept %d waypoints", len(jumps) - 1, len(route))
    return route, stops


def _plot_galaxy(origin: str, end: str, jump_range: float, options: dict[str, Any], cancelled
                 ) -> tuple[list[tuple[str, int]], dict[str, Any] | None, dict[str, dict[str, Any]]]:
    """Galaxy Plotter with the uncharted-space bridge. Spansh answers an unknown start only with
    "Unable to find route", so ask first whether it knows the start system."""
    global _galaxy_last_ship
    ship = _galaxy_last_ship = _galaxy_ship(_read_latest_loadout())
    start, bridge = origin, None
    if _spansh_coordinates(origin) is None:
        position = _start_coordinates(origin)
        if position is None:
            raise RuntimeError(f"Spansh doesn't know {origin} yet. A bridge route needs your"
                               " current system as the Start System.")
        bridge = _find_bridge(position, end, ship["range"] or jump_range, ship["multiplier"])
        start = bridge["system"]
    if cancelled():
        raise _PlotCancelled()
    route, stops = _spansh_galaxy(start, end, ship, options, cancelled)
    if bridge:
        first_leg = max(1, math.ceil(bridge["distance"] / max(ship["range"] or jump_range, 1)))
        route = [(origin, 0), (route[0][0], first_leg)] + route[1:]
    return route, bridge, stops


# ---------------------------------------------------------------------------
# Route progress bar (Jonathan's design, 23 Oct): a thin bar under the Jumps line,
# filled to your progress. It also carries On Route / Off Route / Arrived, so the
# lamp on the Jumps line hides while the bar is shown. Colours: green / red with a black
# empty part; with "Force EDMC theme colours", only EDMC's Highlighted / Normal Text are used
# (suite rule: never force colours beyond those two without a setting to turn it off).
# ---------------------------------------------------------------------------
_route_bar = None
_prefs_vars: dict[str, Any] = {}


def _route_colours() -> tuple[str, str]:
    """(on route, off route) colours for the lamp and the progress bar (shared status colours)."""
    colours = _status_colours()
    return colours["on"], colours["off"]


def _route_bar_on() -> bool:
    return bool(_settings.get("show_progress_bar", True)) and _widget_alive(_route_bar)


class _RouteBar(tk.Canvas):
    """Thin progress bar. Off Route and Arrived are written in the middle of the bar."""

    def __init__(self, parent: tk.Misc, line: tk.Misc) -> None:
        super().__init__(parent, width=1, height=12, highlightthickness=0, bd=0)
        self._line = line               # the Jumps line: its font and width set the bar's size
        self._state: tuple[str | None, float] = (None, 0.0)
        self.bind("<Configure>", self.redraw)

    def font(self) -> Any:
        label = next((child for child in self._line.winfo_children() if child.winfo_class() == "Label"), None)
        try:
            return tkfont.Font(font=label.cget("font")) if label is not None else tkfont.nametofont("TkDefaultFont")
        except tk.TclError:
            return tkfont.nametofont("TkDefaultFont")

    def show(self, position: str | None, fraction: float) -> None:
        self._state = (position, max(0.0, min(1.0, fraction)))
        self.redraw()

    def redraw(self, _event: Any = None) -> None:
        if not _widget_alive(self):
            return
        font = self.font()
        line = int(font.metrics("linespace"))
        height = line + 2
        if int(self.cget("height")) != height:
            tk.Canvas.configure(self, height=height)
        width = self.winfo_width()
        background = _palette()[2]
        tk.Canvas.configure(self, bg=background)
        position, fraction = self._state
        signature = (position, fraction, width, height, background, _route_colours(),
                     bool(_status_colours()["forced"]), _palette()[0], tuple(sorted(font.actual().items())))
        if signature == getattr(self, "_drawn", None) and self.find_all():
            return                          # nothing changed: don't repaint (avoids flicker)
        self._drawn = signature
        self.delete("all")
        if width <= 4:
            return
        on_colour, off_colour = _route_colours()
        colour = off_colour if position == "off" else on_colour
        filled = width if position == "arrived" else round(width * fraction)
        thick = max(4, round(line * 0.3))
        top = (height - thick) // 2
        # A thin border in EDMC's Normal Text colour, so the ends of the bar show against the black of space (transparent
        # theme). Forced theme colours: the empty part is the panel background; otherwise black.
        self.create_rectangle(0, top, width - 1, top + thick, fill=background if _status_colours()["forced"] else "black",
                              outline=_palette()[0])
        if filled > 0:                       # the progress sits inside the border
            self.create_rectangle(1, top + 1, max(2, min(filled, width - 2)), top + thick - 1, fill=colour, outline=colour)
        words = {"off": "Off Route", "arrived": "Arrived"}.get(position or "")
        if words:
            gap = font.measure(words) + font.measure("  ") * 2
            middle = width / 2
            self.create_rectangle(middle - gap / 2, 0, middle + gap / 2, height, fill=background, outline=background)
            self.create_text(middle, height / 2, text=words, fill=colour, font=font)


def _build_route_bar(block: tk.Frame, line: tk.Frame) -> None:
    """The bar is wider than the Jumps line but stops short of the panel edges (halfway between)."""
    global _route_bar
    _route_bar = _RouteBar(block, line)

    def fit(_event: Any = None) -> None:
        if not _widget_alive(_route_bar):
            return
        total, used = block.winfo_width(), line.winfo_reqwidth()
        if total <= 1:
            return
        wanted = max(used, int(used + (total - used) / 2))
        if int(_route_bar.cget("width")) != wanted:
            tk.Canvas.configure(_route_bar, width=wanted)
    block.bind("<Configure>", fit, add="+")
    line.bind("<Configure>", fit, add="+")


def _refresh_route_bar(position: str | None) -> None:
    if not _widget_alive(_route_bar):
        return
    if not _route_bar_on() or not _route_systems:
        _route_bar.pack_forget()
        return
    if not _route_bar.winfo_manager():
        _route_bar.pack(pady=(1, 2))
    done, left = _jump_counts()
    _route_bar.show(position, done / (done + left) if done + left else 0.0)


# ---------------------------------------------------------------------------
# Plugin settings page (File > Settings, this plugin's tab). Settings that are
# not needed mid-flight live here; the gear menu keeps the route actions.
# ---------------------------------------------------------------------------
PREFS_BUTTONS = (("Auto-Route Delay…", "_set_autoroute_delay"),
                 ("Load Keybindings…", "_load_binds_dialog"), ("Open Data Folder", "_open_data_folder"),
                 ("About", "_show_about"))


def _toplevels(widget: tk.Misc) -> list[tk.Misc]:
    found = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Toplevel):
            found.append(child)
        found.extend(_toplevels(child))
    return found


def _prefs_action(command, page: tk.Misc):
    """EDMC's Settings window holds the input grab, so a window opened from it must take
    the grab over (and give it back when it closes), or it would not accept clicks."""
    def run() -> None:
        settings = page.winfo_toplevel()
        root = settings.nametowidget(".")
        before = set(_toplevels(root))
        command()
        for window in set(_toplevels(root)) - before:
            try:
                if not window.winfo_exists():
                    continue
                window.transient(settings)
                window.lift()
                window.grab_set()

                def give_back(event: Any, window: tk.Misc = window) -> None:
                    if event.widget is window and settings.winfo_exists():
                        try:
                            settings.grab_set()
                        except tk.TclError:
                            pass
                window.bind("<Destroy>", give_back, add="+")
            except tk.TclError:
                pass
    return run


def plugin_prefs(parent: Any, cmdr: Any = None, is_beta: bool = False) -> Any:
    import myNotebook as nb
    try:
        from plug import invoke
        outer = invoke("(N) Interface", "Navigator Interface", "navigator_scroll_settings", parent)
        page = getattr(outer, "navigator_settings_content", None)
    except ImportError:
        outer = None
        page = None
    if page is None:
        outer = nb.Frame(parent)
        page = outer
    page.columnconfigure(0, weight=1)
    # EDMC's nb.Frame grids its own spacer in row 0, so everything here uses grid, from row 1.
    nb.Label(page, text=f"{TITLE} {VERSION}").grid(row=1, column=0, sticky=tk.W, padx=10, pady=(4, 8))
    _prefs_vars.clear()
    rows = (("show_missions_tab", "Show the Missions tab",
             "Your active missions, grouped by the system they go to, ready to plot as one trip."),
            ("rescue_strike", "Strike through finished rescue cases",
             "Off: finished cases are only dimmed. Either way they stay on the list and can be reopened."),
            ("show_rescue_tab", "Show the Rescue tab",
             "A last tab for Fuel Rats and Hull Seals: your list of rescues, ready to plot as one trip."),
            ("show_progress_bar", "Show progress bar",
             "A thin bar under the Jumps line that fills as you go and shows On Route / Off Route.\n"
             "Its colours (and the lamp, Auto-Route and A buttons) follow the colour setting in (N) Interface."),)
    row = 2
    for key, label, hint in rows:
        variable = tk.BooleanVar(page, value=bool(_settings.get(key, DEFAULT_SETTINGS[key])))
        _prefs_vars[key] = variable
        nb.Checkbutton(page, text=label, variable=variable).grid(row=row, column=0, sticky=tk.W, padx=10)
        nb.Label(page, text=hint, justify=tk.LEFT).grid(row=row + 1, column=0, sticky=tk.W, padx=30, pady=(0, 8))
        row += 2
    _build_shortcut_editor(page, nb)
    _interface("navigator_header_options", page, FOLDER)     # the header cog option: its code lives in Interface
    row = page.grid_size()[1]
    pace = nb.Frame(page)
    pace.grid(row=row, column=0, sticky=tk.W, padx=10, pady=(0, 8))
    nb.Label(pace, text="Minutes per jump for the time estimate, until your pace is learned:").grid(
        row=1, column=0, sticky=tk.W)
    pace_var = tk.StringVar(page, value=f"{_default_pace():g}")
    _prefs_vars["eta_minutes_per_jump"] = pace_var
    entry_class = getattr(nb, "EntryMenu", None) or ttk.Entry
    entry_class(pace, textvariable=pace_var, width=6).grid(row=1, column=1, sticky=tk.W, padx=(6, 0))
    nb.Label(pace, text="Gaps between waypoints longer than three times this count as a break,\n"
             "so time spent idle does not slow the estimate down.", justify=tk.LEFT).grid(
        row=2, column=0, columnspan=2, sticky=tk.W, padx=20)
    row += 1
    buttons = nb.Frame(page)
    buttons.grid(row=row, column=0, sticky=tk.W, padx=10, pady=(4, 10))
    column = 0
    for label, name in PREFS_BUTTONS:
        command = globals().get(name)
        if callable(command):
            ttk.Button(buttons, text=label, command=_prefs_action(command, page)).grid(row=1, column=column, padx=(0, 6))
            column += 1
    # Required Interface owns the shared contrast preference and rendering.
    try:
        from plug import invoke
        invoke("(N) Interface", "Navigator Interface", "navigator_background_preferences",
               page, FOLDER)
    except ImportError:
        pass
    return outer


_shortcut_edit: dict[str, Any] = {}
SHORTCUT_LOOKUP_MS = 400           # wait for a pause in typing before asking Spansh
SHORTCUT_LOOKUP_MIN = 3            # letters needed before a lookup


def _clean_name(text: str) -> str:
    """Stray, leading, trailing and doubled spaces removed (a pasted name often carries them)."""
    return " ".join(str(text).split())


def _build_shortcut_editor(page: tk.Misc, nb: Any) -> None:
    """Settings: how many shortcut buttons, then a name and a destination for each. Typing a destination looks it
    up (systems, stations and carriers) and offers a list: tap one and the box is filled in with the exact spelling.
    A button with a destination is shown; a blank row is hidden. Rows are saved with Settings > OK; Clear empties one."""
    _shortcut_edit.clear()
    entry_class = getattr(nb, "EntryMenu", None) or ttk.Entry
    # The switch sits right above the places it switches on, not up with the other tick-boxes.
    on_var = tk.BooleanVar(page, value=bool(_settings.get("shortcuts_on")))
    _prefs_vars["shortcuts_on"] = on_var
    top = page.grid_size()[1]
    nb.Checkbutton(page, text="Show the shortcut bar", variable=on_var).grid(row=top, column=0, sticky=tk.W, padx=10)
    nb.Label(page, text="A row of buttons under the header, each one a place to go: tap it and it is copied, or plotted in the\n"
             "galaxy map, exactly like tapping a waypoint (the A button decides).", justify=tk.LEFT).grid(
        row=top + 1, column=0, sticky=tk.W, padx=30, pady=(0, 4))
    frame = nb.Frame(page)
    frame.grid(row=top + 2, column=0, sticky=tk.W, padx=30, pady=(0, 10))
    nb.Label(frame, text="Buttons:").grid(row=0, column=0, sticky=tk.W)
    count = tk.StringVar(page, value=str(_shortcut_count()))
    _shortcut_edit["count"] = count
    box = ttk.Combobox(frame, textvariable=count, values=[str(n) for n in range(3, SHORTCUT_SLOTS + 1)],
                       state="readonly", width=3)
    box.grid(row=0, column=1, sticky=tk.W, padx=(6, 0))
    nb.Label(frame, text="Name (10 letters)").grid(row=1, column=1, sticky=tk.W, padx=(0, 6), pady=(8, 0))
    nb.Label(frame, text="Where to: type a few letters, then pick from the list").grid(
        row=1, column=2, sticky=tk.W, pady=(8, 0))
    saved = list(_settings.get("shortcuts") or [])
    rows, lists, found, targets, timers = [], [], {}, [], {}
    lookups: queue.Queue = queue.Queue()

    def hide(index: int) -> None:
        lists[index].grid_remove()

    def pick(index: int, _event=None) -> None:
        chosen = lists[index].curselection()
        if chosen and chosen[0] < len(found.get(index, [])):
            targets[index].set(found[index][chosen[0]][1])
        hide(index)

    def start(index: int, text: str) -> None:
        def work() -> None:
            try:
                names = _spansh_names(text)
            except Exception:
                names = []
            try:
                stations = _spansh_stations_detail(text)
            except Exception:
                stations = []
            lookups.put((index, text, names, stations))
        threading.Thread(target=work, daemon=True).start()

    def changed(index: int, _event=None) -> None:
        text = _clean_name(targets[index].get())
        if timers.get(index):
            frame.after_cancel(timers[index])
            timers[index] = None
        if len(text) < SHORTCUT_LOOKUP_MIN:
            hide(index)
            return
        timers[index] = frame.after(SHORTCUT_LOOKUP_MS, lambda: start(index, text))

    def pump() -> None:
        try:
            if not frame.winfo_exists():
                return
            while True:
                index, text, names, stations = lookups.get_nowait()
                if _clean_name(targets[index].get()) != text:
                    continue                                   # typed on since: a newer lookup is coming
                options = [(name, name) for name in names]
                options += [(f"{name}  ({system})", name) for name, system, _kind in stations if name not in names]
                found[index] = options
                lists[index].delete(0, tk.END)
                for label, _value in options:
                    lists[index].insert(tk.END, label)
                if options:
                    lists[index].configure(height=min(6, len(options)))
                    lists[index].grid()
                else:
                    hide(index)
        except queue.Empty:
            pass
        except tk.TclError:
            return
        frame.after(250, pump)

    for index in range(SHORTCUT_SLOTS):
        entry = saved[index] if index < len(saved) and isinstance(saved[index], dict) else {}
        name = tk.StringVar(page, value=str(entry.get("name") or ""))
        target = tk.StringVar(page, value=str(entry.get("target") or ""))
        name.trace_add("write", lambda *_a, var=name: var.get()[SHORTCUT_NAME_CHARS:] and
                       var.set(var.get()[:SHORTCUT_NAME_CHARS]))
        _shortcut_edit[index] = (name, target)
        targets.append(target)
        where = entry_class(frame, textvariable=target, width=34)
        where.bind("<KeyRelease>", lambda event, i=index: changed(i, event), add="+")
        widgets = (nb.Label(frame, text=str(index + 1)), entry_class(frame, textvariable=name, width=12), where,
                   ttk.Button(frame, text="Use target", command=lambda var=target, i=index: (var.set(_target_here()), hide(i))),
                   ttk.Button(frame, text="Clear", command=lambda a=name, b=target, i=index: (a.set(""), b.set(""), hide(i))))
        for column, widget in enumerate(widgets):
            widget.grid(row=2 + 2 * index, column=column, sticky=tk.W, padx=(0, 6), pady=1)
        listbox = tk.Listbox(frame, height=5, activestyle="none", exportselection=False)
        listbox.grid(row=3 + 2 * index, column=2, sticky=tk.EW)
        listbox.grid_remove()
        listbox.bind("<<ListboxSelect>>", lambda event, i=index: pick(i, event))
        lists.append(listbox)
        rows.append(widgets)

    def show_rows(_event=None) -> None:
        wanted = int(count.get() or 3)
        for index, widgets in enumerate(rows):
            for widget in widgets:
                widget.grid() if index < wanted else widget.grid_remove()
            if index >= wanted:
                hide(index)

    box.bind("<<ComboboxSelected>>", show_rows)
    show_rows()
    nb.Label(frame, text="Use target fills the box from the system you have targeted or plotted in the game, or the system you are in.",
             justify=tk.LEFT).grid(row=2 + 2 * SHORTCUT_SLOTS, column=0, columnspan=5, sticky=tk.W, pady=(6, 0))
    _shortcut_edit["changed"], _shortcut_edit["lists"], _shortcut_edit["found"] = changed, lists, found
    frame.after(250, pump)


def _target_here() -> str:
    """The game's targeted or plotted system, else the one you are in (for the shortcut editor's Use target)."""
    return _game_destination() or str(_snapshot.get("location", {}).get("system_name") or "")


def _apply_shortcut_editor() -> bool:
    """Settings > OK: keep the count and the rows. True when anything changed."""
    if not _shortcut_edit:
        return False
    changed = False
    try:
        count = min(SHORTCUT_SLOTS, max(3, int(_shortcut_edit["count"].get())))
        rows = [{"name": _clean_name(_shortcut_edit[i][0].get())[:SHORTCUT_NAME_CHARS],
                 "target": _clean_name(_shortcut_edit[i][1].get())} for i in range(SHORTCUT_SLOTS)]
    except (tk.TclError, ValueError, KeyError):
        _shortcut_edit.clear()
        return False
    if _settings.get("shortcut_count") != count:
        _settings["shortcut_count"] = count
        changed = True
    if _settings.get("shortcuts") != rows:
        _settings["shortcuts"] = rows
        changed = True
    _shortcut_edit.clear()
    return changed


def _apply_prefs_page() -> None:
    """Settings > OK: keep what was ticked on our page."""
    changed = False
    for key, variable in list(_prefs_vars.items()):
        try:
            if key == "eta_minutes_per_jump":
                value = min(60.0, max(0.25, float(str(variable.get()).strip())))
            else:
                value = bool(variable.get())
        except (tk.TclError, ValueError):
            continue
        if _settings.get(key) != value:
            _settings[key] = value
            changed = True
    _prefs_vars.clear()
    changed = _apply_shortcut_editor() or changed
    if changed:
        _save_settings()
        _refresh_route_label()


def _save_plotted_csv(route: list[tuple[str, int]]) -> str | None:
    """Keep a CSV copy of every plotted route (to reload after a Cancel Route, or to share)."""
    folder = os.path.join(DATA_DIR, "plotted_routes")
    clean = lambda name: re.sub(r"[^A-Za-z0-9 _.-]", "", name).strip().replace(" ", "_")[:40] or "system"
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = os.path.join(folder, f"{stamp}_{clean(route[0][0])}_to_{clean(route[-1][0])}.csv")
    try:
        os.makedirs(folder, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["System Name", "Jumps"])
            writer.writerows(route)
        return path
    except OSError:
        logger.exception("Could not save the plotted route CSV")
        return None


def _ship_line(profile: dict[str, Any], jump_range: float | None = None) -> str:
    if jump_range is None and not profile["ok"]:
        line = f"{profile['label']} Enter your jump range below."
    else:
        shown = profile["range"] if jump_range is None else jump_range
        note = profile.get("range_note") if jump_range is None or jump_range == profile["range"] else ""
        detail = f" ({note}; best case {profile['best_range']:.2f})" if note else ""
        line = f"{profile['label']} · {shown:.2f} ly{detail} · x{profile['multiplier']} boost"
    cargo = _cargo_count()
    if cargo > 0 and not profile.get("range_note"):
        line += (f"\nCarrying {cargo} t of cargo: your real jump range is lower,"
                 " so the route may need extra jumps.")
    return line


def _game_destination() -> str:
    """The system you have targeted or plotted to in Elite, as the default End System.
    The end of the game's plotted route wins; otherwise the FSD target from Status.json, only when
    it is a whole system (Body 0, so not a station, body or carrier). Never the system you are in,
    and never a system on the route already loaded (mid-route the game targets our own Next)."""
    here = str(_snapshot.get("location", {}).get("system_name") or "").casefold()
    ours = {name.casefold() for name in _route_systems}
    candidates = []
    route = [item for item in (_read_journal_json("NavRoute.json") or {}).get("Route") or [] if isinstance(item, dict)]
    if route:
        candidates.append(str(route[-1].get("StarSystem") or ""))
    target = (_read_journal_json("Status.json") or {}).get("Destination")
    if isinstance(target, dict) and not target.get("Body"):
        candidates.append(str(target.get("Name") or ""))
    for name in candidates:
        if name and name.casefold() != here and name.casefold() not in ours:
            return name
    return ""


def _open_plot_popup() -> None:
    """Gear > Plot New Route: Start / End / Efficiency, ship read automatically."""
    global _plot_popup
    if not _confirm_replace_route():
        return                                       # keep the loaded route; no new plot
    if _plot_popup is not None:
        try:
            _plot_popup.destroy()
        except tk.TclError:
            pass
    profile = _ship_profile()
    window = _plot_popup = tk.Toplevel(_app_frame)
    window.title("Plot New Route")
    _attach_popup(window, "plot")
    try:
        window.transient(_app_frame.winfo_toplevel())
    except tk.TclError:
        pass
    state: dict[str, Any] = {"stage": "input", "route": None, "cancelled": False,
                             "lookup": None, "profile": profile}
    results: queue.Queue = queue.Queue()

    body = tk.Frame(window)
    body.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)
    body.columnconfigure(1, weight=1)
    info = tk.Label(body, text=_ship_line(profile), justify=tk.CENTER, anchor=tk.CENTER, wraplength=380)
    info.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 8))
    _autowrap(info)

    def field(row: int, label: str, value: str) -> tk.Entry:
        tk.Label(body, text=label, anchor=tk.W).grid(row=row, column=0, sticky=tk.W, padx=(0, 8), pady=3)
        entry = tk.Entry(body, width=34)
        entry.insert(0, value)
        entry.grid(row=row, column=1, sticky=tk.EW, pady=3)
        return entry

    start = field(1, "Start System", str(_snapshot.get("location", {}).get("system_name") or ""))
    end = field(2, "End System", _game_destination() or str(_settings.get("plot_last_end") or ""))
    suggestions = tk.Listbox(body, height=5, activestyle="none", exportselection=False)
    suggestions.grid(row=3, column=1, sticky=tk.EW)
    suggestions.grid_remove()
    # Station (optional): find the system a station or carrier is in; picking one fills in End System.
    station = field(4, "Station (optional)", "")
    station_hits = tk.Listbox(body, height=5, activestyle="none", exportselection=False)
    station_hits.grid(row=5, column=1, sticky=tk.EW)
    station_hits.grid_remove()
    efficiency = field(6, "Efficiency (%)", str(_settings.get("plot_efficiency", 70)))
    range_entry = None
    if not profile["ok"]:
        range_entry = field(7, "Jump Range (ly)", f"{profile['range']:.2f}" if profile["range"] > 0 else "")
    status = tk.Label(body, text="", justify=tk.CENTER, anchor=tk.CENTER, wraplength=380)
    status.grid(row=40, column=0, columnspan=2, sticky=tk.EW, pady=(8, 0))
    _autowrap(status)
    # Route Type: Neutron Highway or Road to Riches (its own settings, shown only for it).
    saved_kind = _settings.get("plot_type")
    kind_var = tk.StringVar(window, value=ROUTE_TYPES[ROUTE_KINDS.index(saved_kind)]
                            if saved_kind in ROUTE_KINDS else ROUTE_TYPES[0])
    typebar = tk.Frame(window)
    typebar.pack(fill=tk.X, padx=12, pady=(10, 0), before=body)
    tk.Label(typebar, text="Route Type", anchor=tk.W).pack(side=tk.LEFT, padx=(0, 8))
    # The suite's standard dropdown: a read-only ttk.Combobox (as in Radio, Docking, Interface, Voice).
    ttk.Combobox(typebar, textvariable=kind_var, values=ROUTE_TYPES, state="readonly",
                 width=max(len(name) for name in ROUTE_TYPES) + 2).pack(side=tk.LEFT)
    riches_entries = {key: field(10 + offset, label, str(_settings.get(key, DEFAULT_SETTINGS[key])))
                      for offset, (key, label) in enumerate(RICHES_FIELDS)}
    end_caption = body.grid_slaves(row=2, column=0)[0]
    neutron_only = body.grid_slaves(row=6)
    end_widgets = body.grid_slaves(row=2)
    station_widgets = body.grid_slaves(row=4)
    riches_only = [widget for row in range(10, 10 + len(RICHES_FIELDS)) for widget in body.grid_slaves(row=row)]
    algorithm_names = [name for name, _ in GALAXY_ALGORITHMS]
    saved_algorithm = next((name for name, code in GALAXY_ALGORITHMS
                            if code == _settings.get("galaxy_algorithm")), algorithm_names[0])
    algorithm_var = tk.StringVar(window, value=saved_algorithm)
    galaxy_only = [tk.Label(body, text="Routing", anchor=tk.W),
                   ttk.Combobox(body, textvariable=algorithm_var, values=algorithm_names, state="readonly",
                                width=max(len(name) for name in algorithm_names) + 2)]
    galaxy_only[0].grid(row=15, column=0, sticky=tk.W, padx=(0, 8), pady=3)
    galaxy_only[1].grid(row=15, column=1, sticky=tk.W, pady=3)
    # FSD injections are rare (far reaches of the galaxy only): opt-in, off every time the window opens.
    inject_var = tk.BooleanVar(window, value=False)
    inject_box = tk.Checkbutton(body, text="Use FSD injections when needed (premium)", variable=inject_var,
                                anchor=tk.W)
    inject_note = tk.Label(body, text=_injection_note(), anchor=tk.W, justify=tk.LEFT, wraplength=380)
    inject_box.grid(row=16, column=0, columnspan=2, sticky=tk.W, pady=(4, 0))
    inject_note.grid(row=17, column=0, columnspan=2, sticky=tk.EW, padx=(22, 0))
    _autowrap(inject_note, 22)
    galaxy_only += [inject_box, inject_note]

    # Fleet Carrier: one extra number. Trade Router: where you start and what you trade with.
    carrier_entry = field(22, "Carrier Space Used (t)", str(_settings.get("carrier_used", 0)))
    carrier_only = body.grid_slaves(row=22)
    trade_entries = {key: field(24 + offset, label, str(_settings.get(key, DEFAULT_SETTINGS[key])))
                     for offset, (key, label) in enumerate((("trade_station", "Start Station"),
                                                            ("trade_capital", "Starting Capital (cr)"),
                                                            ("trade_cargo", "Cargo Space (t)"),
                                                            ("trade_hops", "Most Trades"),
                                                            ("trade_ls", "Furthest Station (ls)")))}
    trade_only = [widget for row in range(24, 29) for widget in body.grid_slaves(row=row)]

    # Multi-Stop Trip: a list of stops, each Fixed (keeps its place in the list) or Flexible (placed wherever the
    # whole trip is shortest). Saved trips live here in the window, never on the main panel.
    trip: dict[str, Any] = {"stops": [], "resolved": {}}
    trip_box = tk.Frame(body)
    trip_box.grid(row=8, column=0, columnspan=2, sticky=tk.EW, pady=(6, 0))
    trip_box.columnconfigure(0, weight=1)
    saved_row = tk.Frame(trip_box)
    saved_row.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 4))
    tk.Label(saved_row, text="Saved Trips", anchor=tk.W).pack(side=tk.LEFT, padx=(0, 6))
    saved_var = tk.StringVar(window)
    saved_box = ttk.Combobox(saved_row, textvariable=saved_var, values=sorted(_settings.get("saved_trips") or {}), width=22)
    saved_box.pack(side=tk.LEFT)
    tk.Label(trip_box, text="Stops (first in the list is the first place to go)", anchor=tk.W).grid(
        row=1, column=0, columnspan=2, sticky=tk.W)
    trip_list = tk.Listbox(trip_box, height=6, activestyle="none", exportselection=False)
    trip_list.grid(row=2, column=0, sticky=tk.EW)
    trip_buttons = tk.Frame(trip_box)
    trip_buttons.grid(row=2, column=1, sticky=tk.N, padx=(6, 0))
    stop_entry = tk.Entry(trip_box, width=30)
    stop_entry.grid(row=3, column=0, sticky=tk.EW, pady=3)
    add_button = ttk.Button(trip_box, text="Add Stop", width=10)
    add_button.grid(row=3, column=1, padx=(6, 0))
    stop_hits = tk.Listbox(trip_box, height=5, activestyle="none", exportselection=False)
    stop_hits.grid(row=4, column=0, sticky=tk.EW)
    stop_hits.grid_remove()
    return_var = tk.BooleanVar(window, value=False)
    keep_var = tk.BooleanVar(window, value=False)
    tk.Checkbutton(trip_box, text="Come back to the Start System at the end", variable=return_var, anchor=tk.W).grid(
        row=5, column=0, columnspan=2, sticky=tk.W)
    tk.Checkbutton(trip_box, text="Keep the last stop last", variable=keep_var, anchor=tk.W).grid(
        row=6, column=0, columnspan=2, sticky=tk.W)

    def show_kind(*_args: Any) -> None:
        chosen = ROUTE_KINDS[ROUTE_TYPES.index(kind_var.get())] if kind_var.get() in ROUTE_TYPES else "neutron"
        riches = chosen in SCAN_KINDS
        trip_mode = chosen == "trip"
        no_end = trip_mode or chosen == "trade"
        for widget in neutron_only:
            widget.grid() if chosen in ("neutron", "trip") else widget.grid_remove()
        for widget in end_widgets + station_widgets:
            widget.grid_remove() if no_end else widget.grid()
        for widget in carrier_only:
            widget.grid() if chosen == "carrier" else widget.grid_remove()
        for widget in trade_only:
            widget.grid() if chosen == "trade" else widget.grid_remove()
        if no_end:
            suggestions.grid_remove()
            station_hits.grid_remove()
        trip_box.grid() if trip_mode else trip_box.grid_remove()
        _fit_window(window)
        for widget in riches_only:
            widget.grid() if riches else widget.grid_remove()
        for widget in galaxy_only:
            widget.grid() if chosen == "galaxy" else widget.grid_remove()
        end_caption.configure(text="End System (optional)" if riches else "End System")
        back_to_input()
    buttons = tk.Frame(window)
    buttons.pack(side=tk.BOTTOM, pady=(4, 10), before=typebar)     # first in the pack order: never squeezed out
    plot_button = ttk.Button(buttons, text="Plot Route", width=12)
    plot_button.pack(side=tk.LEFT, padx=6)
    ttk.Button(buttons, text="Cancel", width=12,
               command=lambda: close()).pack(side=tk.LEFT, padx=6)

    def close() -> None:
        state["cancelled"] = True
        try:
            window.destroy()
        except tk.TclError:
            pass

    def back_to_input(_event: Any = None) -> None:
        if state["stage"] == "result":
            state["stage"], state["route"] = "input", None
            plot_button.configure(text="Plot Route", state=tk.NORMAL)
            status.configure(text="")

    # End System suggestions: 3+ letters, looked up in the background.
    def lookup_later(_event: Any = None) -> None:
        back_to_input()
        if state["lookup"] is not None:
            window.after_cancel(state["lookup"])
        state["lookup"] = window.after(400, lookup_now)

    def lookup_now() -> None:
        state["lookup"] = None
        text = end.get().strip()
        if len(text) < 3:
            suggestions.grid_remove()
            return

        def worker() -> None:
            try:
                results.put(("names", text, _spansh_names(text)))
            except Exception as error:
                logger.info("Plot New Route: no suggestions for %r (%s)", text, error)
        threading.Thread(target=worker, daemon=True).start()

    def pick_suggestion(_event: Any = None) -> None:
        chosen = suggestions.curselection()
        if chosen:
            end.delete(0, tk.END)
            end.insert(0, suggestions.get(chosen[0]))
            suggestions.grid_remove()

    # Station suggestions: 3+ letters, same pattern. The hits are (station, system) pairs.
    def station_later(_event: Any = None) -> None:
        back_to_input()
        if state.get("station_lookup") is not None:
            window.after_cancel(state["station_lookup"])
        state["station_lookup"] = window.after(400, station_now)

    def station_now() -> None:
        state["station_lookup"] = None
        text = station.get().strip()
        if len(text) < 3:
            station_hits.grid_remove()
            return

        def worker() -> None:
            try:
                results.put(("stations", text, _spansh_stations(text)))
            except Exception as error:
                logger.info("Plot New Route: no station matches for %r (%s)", text, error)
        threading.Thread(target=worker, daemon=True).start()

    def pick_station(_event: Any = None) -> None:
        chosen = station_hits.curselection()
        if chosen and chosen[0] < len(state.get("station_found", [])):
            name, system = state["station_found"][chosen[0]]
            station.delete(0, tk.END)
            station.insert(0, name)
            end.delete(0, tk.END)
            end.insert(0, system)
            station_hits.grid_remove()
            suggestions.grid_remove()
            back_to_input()

    # --- Multi-Stop Trip: the stop list ---
    def refresh_stops(select: int | None = None) -> None:
        trip_list.delete(0, tk.END)
        for number, stop in enumerate(trip["stops"], start=1):
            where = f"  ({stop['system']})" if stop["system"].casefold() != stop["name"].casefold() else ""
            trip_list.insert(tk.END, f"{number}. {stop['name']}{where}  [{'Fixed' if stop['fixed'] else 'Flexible'}]")
        if select is not None and trip["stops"]:
            index = min(max(select, 0), len(trip["stops"]) - 1)
            trip_list.selection_set(index)
            trip_list.see(index)
        back_to_input()

    def chosen_stop() -> int | None:
        picked = trip_list.curselection()
        return picked[0] if picked and picked[0] < len(trip["stops"]) else None

    def add_stop(_event: Any = None) -> None:
        text = stop_entry.get().strip()
        if not text:
            return
        if len(trip["stops"]) >= MAX_TRIP_STOPS:
            status.configure(text=f"A trip can have up to {MAX_TRIP_STOPS} stops.")
            return
        trip["stops"].append({"name": text, "system": trip["resolved"].get(text, text), "fixed": False})
        stop_entry.delete(0, tk.END)
        stop_hits.grid_remove()
        refresh_stops(len(trip["stops"]) - 1)

    def remove_stop() -> None:
        index = chosen_stop()
        if index is not None:
            del trip["stops"][index]
            refresh_stops(index)

    def move_stop(step: int) -> None:
        index = chosen_stop()
        if index is not None and 0 <= index + step < len(trip["stops"]):
            trip["stops"][index], trip["stops"][index + step] = trip["stops"][index + step], trip["stops"][index]
            refresh_stops(index + step)

    def toggle_fixed() -> None:
        index = chosen_stop()
        if index is not None:
            trip["stops"][index]["fixed"] = not trip["stops"][index]["fixed"]
            refresh_stops(index)

    for label, command in (("Fixed / Flexible", toggle_fixed), ("Move Up", lambda: move_stop(-1)),
                           ("Move Down", lambda: move_stop(1)), ("Remove", remove_stop)):
        ttk.Button(trip_buttons, text=label, width=15, command=command).pack(pady=1)
    add_button.configure(command=add_stop)
    stop_entry.bind("<Return>", add_stop)

    # Stop suggestions: stations and carriers first, then systems (3+ letters, looked up in the background).
    def stop_later(_event: Any = None) -> None:
        if state.get("stop_lookup") is not None:
            window.after_cancel(state["stop_lookup"])
        state["stop_lookup"] = window.after(400, stop_now)

    def stop_now() -> None:
        state["stop_lookup"] = None
        text = stop_entry.get().strip()
        if len(text) < 3:
            stop_hits.grid_remove()
            return

        def worker() -> None:
            found: list[tuple[str, str]] = []
            try:
                found += _spansh_stations(text)[:4]
            except Exception as error:
                logger.info("Plot New Route: no station matches for %r (%s)", text, error)
            try:
                found += [(name, name) for name in _spansh_names(text)[:4]]
            except Exception as error:
                logger.info("Plot New Route: no suggestions for %r (%s)", text, error)
            results.put(("stopnames", text, found))
        threading.Thread(target=worker, daemon=True).start()

    def pick_stop(_event: Any = None) -> None:
        chosen = stop_hits.curselection()
        if chosen and chosen[0] < len(state.get("stop_found", [])):
            name, system = state["stop_found"][chosen[0]]
            trip["resolved"][name] = system
            stop_entry.delete(0, tk.END)
            stop_entry.insert(0, name)
            stop_hits.grid_remove()

    stop_entry.bind("<KeyRelease>", stop_later)
    stop_hits.bind("<<ListboxSelect>>", pick_stop)

    # Saved trips: the stop list and the two options, under a name you type or pick in the box.
    def save_trip() -> None:
        name = saved_var.get().strip()
        if not name:
            status.configure(text="Type a name in the Saved Trips box, then press Save.")
            return
        if not trip["stops"]:
            status.configure(text="Add some stops first.")
            return
        saved = dict(_settings.get("saved_trips") or {})
        if name not in saved and len(saved) >= MAX_SAVED_TRIPS:
            status.configure(text=f"Up to {MAX_SAVED_TRIPS} trips can be saved. Delete one first.")
            return
        saved[name] = {"stops": [dict(stop) for stop in trip["stops"]], "return": bool(return_var.get()),
                       "keep_last": bool(keep_var.get())}
        _settings["saved_trips"] = saved
        _save_settings()
        saved_box.configure(values=sorted(saved))
        status.configure(text=f"Saved the trip \u201c{name}\u201d.")

    def load_trip(_event: Any = None) -> None:
        item = (_settings.get("saved_trips") or {}).get(saved_var.get().strip())
        if not isinstance(item, dict):
            return
        trip["stops"] = [{"name": str(s.get("name")), "system": str(s.get("system") or s.get("name")),
                          "fixed": bool(s.get("fixed"))} for s in item.get("stops") or [] if isinstance(s, dict)]
        return_var.set(bool(item.get("return")))
        keep_var.set(bool(item.get("keep_last")))
        refresh_stops(0)
        status.configure(text=f"Loaded the trip \u201c{saved_var.get().strip()}\u201d: {len(trip['stops'])} stops.")

    def delete_trip() -> None:
        name = saved_var.get().strip()
        saved = dict(_settings.get("saved_trips") or {})
        if name in saved and messagebox.askyesno("Delete Saved Trip", f"Delete the saved trip \u201c{name}\u201d?", parent=window):
            del saved[name]
            _settings["saved_trips"] = saved
            _save_settings()
            saved_box.configure(values=sorted(saved))
            saved_var.set("")
            status.configure(text="Deleted.")

    for label, command in (("Load", load_trip), ("Save", save_trip), ("Delete", delete_trip)):
        ttk.Button(saved_row, text=label, width=7, command=command).pack(side=tk.LEFT, padx=(4, 0))
    saved_box.bind("<<ComboboxSelected>>", load_trip)

    end.bind("<KeyRelease>", lookup_later)
    suggestions.bind("<<ListboxSelect>>", pick_suggestion)
    station.bind("<KeyRelease>", station_later)
    station_hits.bind("<<ListboxSelect>>", pick_station)
    for entry in (start, efficiency) + ((range_entry,) if range_entry is not None else ()):
        entry.bind("<KeyRelease>", back_to_input)

    def plot_or_load() -> None:
        if state["stage"] == "result":
            load_route()
            return
        origin, target = start.get().strip(), end.get().strip()
        kind = ROUTE_KINDS[ROUTE_TYPES.index(kind_var.get())] if kind_var.get() in ROUTE_TYPES else "neutron"
        if kind == "trip":
            target = ""
            if origin and not trip["stops"]:
                status.configure(text="Add at least one stop.")
                return
        if not origin or (not target and kind not in SCAN_KINDS and kind not in ("trip", "trade")):
            status.configure(text="Enter both a Start System and an End System." if kind not in SCAN_KINDS
                             else "Enter a Start System.")
            return
        options: dict[str, float] = {}
        if kind in SCAN_KINDS:
            try:
                options = {key: float(riches_entries[key].get().replace(",", "").strip())
                           for key, _ in RICHES_FIELDS}
            except ValueError:
                options = {}
            if len(options) != len(RICHES_FIELDS) or min(options.values()) <= 0:
                status.configure(text="The search settings must be numbers above 0.")
                return
        elif kind == "carrier":
            try:
                options = {"carrier_used": float(carrier_entry.get().replace(",", "").strip())}
            except ValueError:
                options = {}
            if not options or not 0 <= options["carrier_used"] <= CARRIER_CAPACITY:
                status.configure(text=f"Carrier space used must be a number from 0 to {CARRIER_CAPACITY:,}.")
                return
        elif kind == "trade":
            try:
                options = {key: float(trade_entries[key].get().replace(",", "").strip())
                           for key in trade_entries if key != "trade_station"}
            except ValueError:
                options = {}
            station_name = trade_entries["trade_station"].get().strip()
            if not station_name or len(options) != len(trade_entries) - 1 or min(options.values()) <= 0:
                status.configure(text="Enter the Start Station, and numbers above 0 for the rest.")
                return
            options["trade_station"] = station_name
        elif kind == "galaxy":
            options = {"galaxy_algorithm": dict(GALAXY_ALGORITHMS).get(algorithm_var.get(), "optimistic"),
                       "use_injections": bool(inject_var.get())}
        try:
            percent = int(float(efficiency.get().strip()))
        except ValueError:
            percent = -1
        if kind not in ("neutron", "trip"):
            percent = int(_settings.get("plot_efficiency", 70))   # neutron plotter only
        elif not 1 <= percent <= 100:
            status.configure(text="Efficiency must be a number from 1 to 100.")
            return
        fresh = _ship_profile()                 # re-check the ship on every request
        state["profile"] = fresh
        if kind == "carrier":
            jump_range = CARRIER_JUMP                 # carriers jump 500 ly whatever your ship is
        elif fresh["ok"]:
            jump_range = fresh["range"]
        else:
            try:
                jump_range = float((range_entry.get() if range_entry is not None else "").strip())
            except ValueError:
                jump_range = 0.0
            if not 0 < jump_range <= MAX_SANE_RANGE:
                status.configure(text="Ship data not found - enter your jump range (ly).")
                return
        info.configure(text=_ship_line(fresh, jump_range))
        if kind == "trip" and not _long_plot_notice(len(trip["stops"]), window):
            return
        plot_button.configure(state=tk.DISABLED)
        status.configure(text="Asking Spansh to plot the route…")
        state["stage"] = "plotting"
        multiplier = fresh["multiplier"]

        def worker() -> None:
            try:
                if kind == "galaxy":
                    route, bridge, bodies = _plot_galaxy(origin, target, jump_range, options,
                                                         lambda: state["cancelled"])
                elif kind in SCAN_KINDS:
                    route, bridge, bodies = _plot_riches(origin, target, jump_range, multiplier, options,
                                                         lambda: state["cancelled"], _fetch_for(kind))
                elif kind == "carrier":
                    route, bodies = _plot_carrier(origin, target, options["carrier_used"], lambda: state["cancelled"])
                    bridge = None
                elif kind == "trade":
                    route, bodies = _plot_trade(origin, options, jump_range, lambda: state["cancelled"])
                    bridge = None
                elif kind == "trip":
                    route, bridge = _plot_trip(origin, [dict(stop) for stop in trip["stops"]], bool(return_var.get()),
                                               bool(keep_var.get()), jump_range, percent, multiplier,
                                               lambda: state["cancelled"],
                                               lambda text: results.put(("progress", text, None)))
                    bodies = {}
                else:
                    route, bridge = _plot_with_bridge(origin, target, jump_range, percent, multiplier,
                                                      lambda: state["cancelled"])
                    bodies = {}
                results.put(("route", route, (target, percent, bridge, kind, bodies, options)))
            except _PlotCancelled:
                pass
            except RuntimeError as error:
                results.put(("error", str(error), None))
            except Exception:
                logger.exception("Plot New Route failed")
                results.put(("error", "Unexpected error - see the EDMC log.", None))
        threading.Thread(target=worker, daemon=True).start()

    def load_route() -> None:
        route = state["route"]
        if not route:
            return
        if _route_systems and not messagebox.askyesno(
                "Replace Route", "Replace the current route with the new one?", parent=window):
            return
        saved = _save_plotted_csv(route)
        target, percent = state["inputs"]
        kind = state.get("kind") or "neutron"
        if target or kind == "neutron":
            _settings["plot_last_end"] = target
        _settings["plot_efficiency"] = percent
        _settings["plot_type"] = kind
        for key, value in (state.get("options") or {}).items():
            if key == "use_injections":
                continue                     # never remembered: injections are a one-off choice
            _settings[key] = int(value) if isinstance(value, float) and value.is_integer() else value
        _save_settings()
        _set_route([system for system, _ in route], _snapshot.get("location", {}).get("system_name"),
                   kind=kind, bodies=state.get("bodies"), legs=[jumps for _, jumps in route])
        logger.info("Plot New Route: loaded %d waypoints (CSV copy: %s)", len(route), saved)
        close()
        bridge = state.get("bridge")
        if kind == "galaxy":
            refuels = sum(1 for item in _route_bodies.values() if isinstance(item, dict) and item.get("refuel"))
            injects = sum(1 for item in _route_bodies.values() if isinstance(item, dict) and item.get("inject"))
            _set_status(f"Galaxy route loaded: {sum(jumps for _, jumps in route)} jumps, "
                        f"{refuels} refuel stop{'s' if refuels != 1 else ''}"
                        + (f", {injects} FSD injection{'s' if injects != 1 else ''}." if injects else ".")
                        + (f" Starts via {bridge['system']} ({bridge['distance']:.0f} ly)." if bridge else ""))
        elif bridge and kind in SCAN_KINDS:
            _set_status(f"Uncharted space: your {KIND_NAMES.get(kind, 'route')} starts from {bridge['system']} "
                        f"({bridge['distance']:.0f} ly).")
        elif bridge and bridge.get("note"):
            _set_status(bridge["note"].split("\n")[0])
        elif bridge:
            _set_status(f"Uncharted space: bridging via {bridge['system']} "
                        f"({bridge['distance']:.0f} ly) onto the Neutron Highway.")
        elif kind in ("carrier", "trade"):
            _set_status(f"{KIND_NAMES[kind]} loaded: {len(route)} stops.")
        elif kind in SCAN_KINDS:
            _set_status(f"{KIND_NAMES.get(kind, 'Route')} loaded: {_count(len(_route_bodies), 'system')} to scan.")
        else:
            _set_status(f"Route loaded: {len(route)} waypoints.")

    plot_button.configure(command=plot_or_load)
    kind_var.trace_add("write", show_kind)
    algorithm_var.trace_add("write", lambda *_args: back_to_input())
    inject_var.trace_add("write", lambda *_args: back_to_input())
    for entry in riches_entries.values():
        entry.bind("<KeyRelease>", back_to_input)
    show_kind()

    # Results from the background threads are handled here, on EDMC's own thread.
    def pump() -> None:
        if state["cancelled"]:
            return
        try:
            while True:
                kind, payload, extra = results.get_nowait()
                if kind == "names":
                    if payload == end.get().strip() and extra:
                        suggestions.delete(0, tk.END)
                        for name in extra:
                            suggestions.insert(tk.END, name)
                        suggestions.grid()
                    elif payload == end.get().strip():
                        suggestions.grid_remove()
                elif kind == "stations":
                    if payload == station.get().strip() and extra:
                        state["station_found"] = extra
                        station_hits.delete(0, tk.END)
                        for name, system in extra:
                            station_hits.insert(tk.END, f"{name}  ({system})")
                        station_hits.grid()
                    elif payload == station.get().strip():
                        station_hits.grid_remove()
                elif kind == "stopnames":
                    if payload == stop_entry.get().strip() and extra:
                        state["stop_found"] = extra
                        stop_hits.delete(0, tk.END)
                        for name, system in extra:
                            stop_hits.insert(tk.END, f"{name}  ({system})" if name != system else name)
                        stop_hits.grid()
                    elif payload == stop_entry.get().strip():
                        stop_hits.grid_remove()
                elif kind == "progress":
                    status.configure(text=payload)
                elif kind == "route":
                    state["stage"], state["route"] = "result", payload
                    state["inputs"], state["bridge"] = extra[:2], extra[2]
                    state["kind"], state["bodies"], state["options"] = extra[3], extra[4], extra[5]
                    lead = _bridge_text(extra[2], extra[3]) + "\n\n" if extra[2] else ""
                    status.configure(text=lead + f"{payload[0][0]} → {payload[-1][0]}\n"
                                          + _route_summary(payload, extra[3], extra[4]))
                    plot_button.configure(text="Load Route", state=tk.NORMAL)
                elif kind == "error":
                    state["stage"] = "input"
                    status.configure(text="Plot Failed: "+payload+"\nYour Loaded Route Is Unchanged.")
                    plot_button.configure(text="Retry Plot", state=tk.NORMAL)
        except queue.Empty:
            pass
        window.after(200, pump)

    window.protocol("WM_DELETE_WINDOW", close)
    window.bind("<Escape>", lambda _event: close())
    window.after(200, pump)
    _fit_window(window)
    root = _app_frame.winfo_toplevel()
    width, height = window.winfo_reqwidth(), window.winfo_reqheight()
    x = min(max(0, root.winfo_rootx() + 40), max(0, window.winfo_screenwidth() - width))
    y = min(max(0, root.winfo_rooty() + 40), max(0, window.winfo_screenheight() - height - 40))
    window.geometry(f"+{x}+{y}")
    (end if start.get() else start).focus_set()


def plugin_start3(plugin_dir: str) -> str:
    global PLUGIN_DIR, DATA_DIR, STATE_PATH, ROUTE_PATH, SETTINGS_PATH, STATUS_PATH
    PLUGIN_DIR = os.path.abspath(plugin_dir)
    try:
        from config import config
        root = os.fspath(getattr(config, "app_dir_path", None) or config.app_dir)
    except (ImportError, AttributeError, TypeError):
        root = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "EDMarketConnector")
    # Keep the same writable location as earlier plugin versions to preserve progress.
    DATA_DIR = os.path.join(root, "NeutronHighwayNavigatorAuto")
    earlier = os.path.join(root, "CockpitCompanion")
    for name in ("automation.json", "active_route.json"):
        mine, theirs = os.path.join(DATA_DIR, name), os.path.join(earlier, name)
        if not os.path.exists(mine) and os.path.isfile(theirs):
            try:
                os.makedirs(DATA_DIR, exist_ok=True)
                shutil.copy2(theirs, mine)   # one-time copy; the earlier folder is never changed
            except OSError:
                logger.exception("Could not copy %s from the earlier plugin data", name)
    os.makedirs(DATA_DIR, exist_ok=True)
    STATE_PATH = os.path.join(DATA_DIR, "cockpit_state.json")
    ROUTE_PATH = os.path.join(DATA_DIR, "active_route.json")
    STATUS_PATH = _find_status_file()
    logger.info("Status.json for live screen state: %s", STATUS_PATH or "not found (using EDMC's copy)")
    SETTINGS_PATH = os.path.join(DATA_DIR, "automation.json")
    _load_settings()
    _refresh_keybinding()
    if _pending_upgrade or not os.path.exists(SETTINGS_PATH):
        _pending_upgrade.clear()
        _save_settings()  # create/upgrade the file up front so it is easy to find
    legacy = os.path.join(PLUGIN_DIR, "active_route.json")
    if not os.path.exists(ROUTE_PATH) and os.path.isfile(legacy):
        try:
            shutil.copy2(legacy, ROUTE_PATH)
        except OSError:
            logger.exception("Could not migrate saved neutron route")
    _load_saved_route()
    _save()
    return TITLE



def _update_header_spacing() -> None:
    """The title carries no extra padding or border (the button stack sits beside it, not in it)."""
    if _title_label is None or _header_frame is None:
        return
    try:
        _title_label.configure(padx=0, borderwidth=0)
    except tk.TclError:
        logger.exception("Could not space the header")


def _completed_systems() -> list[str]:
    """Every system jumped through since the route was loaded, in order; before the first jump, the waypoints already
    reached plus the systems jumped through since the last one."""
    if not _route_systems:
        return []
    if _trail:
        return list(_trail)
    _, _, in_leg, _ = _leg_view()
    return _route_systems[1:max(0, _route_index) + 1] + in_leg


def _remaining_systems() -> list[str]:
    """The systems still ahead. Once the route to the next waypoint is plotted in the game, that includes every
    system in between; otherwise just the waypoints (the plotter only lists those)."""
    if not _route_systems:
        return []
    _, _, _, in_leg = _leg_view()
    if in_leg:
        return in_leg + _route_systems[_route_index + 2:]
    return _route_systems[_route_index + 1:]


def _major_names() -> set[str]:
    """The systems the user entered themselves on the loaded route (casefolded)."""
    return {str(name).casefold() for name in _settings.get("route_major") or []}


def _show_systems_popup(title: str, systems: list[str], empty_text: str, marked: set[str] | None = None,
                        tags: dict[str, str] | None = None, header: str = "") -> None:
    """A small scrollable list with a large OK button, sized to fit the screen. tags: (N) / (F) in front of the stars we
    know for certain, so a stretch with no scoopable star can be seen at a glance. header: one line above the list."""
    global _systems_popup
    if _systems_popup is not None:
        try:
            _systems_popup.destroy()
        except tk.TclError:
            pass
    window = _systems_popup = tk.Toplevel(_app_frame)
    window.title(title)
    _attach_popup(window, "systems")
    try:
        window.transient(_app_frame.winfo_toplevel())
    except tk.TclError:
        pass
    marked = marked or set()
    # Stops the user entered start with "* " in the highlighted colour; the stars the plotter added in between are plain.
    flags = [name.casefold() in marked for name in systems]
    tags = tags or {}
    prefixes = [(tags.get(name.casefold(), "").ljust(3) + " " if tags else "") for name in systems]
    lines = ([prefix + ("* " if flag else ("  " if marked else "")) + name
              for prefix, name, flag in zip(prefixes, systems, flags)] or [empty_text])
    if header:
        _autowrap(tk.Label(window, text=header, justify=tk.CENTER, anchor=tk.CENTER, wraplength=300)).pack(
            side=tk.TOP, fill=tk.X, padx=8, pady=(8, 0))
    body = tk.Frame(window)
    body.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))
    # A Text (read only) rather than a Listbox, so the (N) / (F) / (D) tag can have its own colour.
    listbox = tk.Text(body, wrap="none", cursor="arrow", exportselection=False, highlightthickness=0, borderwidth=1,
                      relief=tk.SUNKEN, padx=3, pady=1, takefocus=False, spacing1=1, spacing3=1)
    try:
        line_height = int(tkfont.Font(font=listbox.cget("font")).metrics("linespace"))
    except (tk.TclError, ValueError):
        line_height = 16
    max_rows = max(5, int(window.winfo_screenheight() * 0.6 / max(line_height, 1)))
    rows_shown = max(6, min(len(lines), max_rows, 25))
    listbox.configure(height=rows_shown, width=min(max(20, max(len(line) for line in lines) + 2), 45))
    try:
        background = listbox.cget("background")
        red, green, blue = listbox.winfo_rgb(background)
        dark = (0.299 * red + 0.587 * green + 0.114 * blue) / 65535 < 0.5
    except tk.TclError:
        dark = False
    highlight = _palette()[1]
    listbox.tag_configure("mark", foreground=highlight)
    listbox.tag_configure("picked", background=listbox.cget("selectbackground"), foreground=listbox.cget("selectforeground"))
    for index, line in enumerate(lines):
        listbox.insert(tk.END, line + ("\n" if index < len(lines) - 1 else ""))
        row = index + 1
        if index < len(systems):
            tag = tags.get(systems[index].casefold(), "")
            colour = _tag_colour(systems[index], tag, dark) if tag else None
            if colour:
                label = f"tag{index}"
                listbox.tag_configure(label, foreground=colour)
                listbox.tag_add(label, f"{row}.0", f"{row}.{len(tag)}")
            if flags[index]:
                listbox.tag_add("mark", f"{row}.{len(prefixes[index])}", f"{row}.end")
    listbox.configure(state=tk.DISABLED)
    if len(lines) > rows_shown:
        scrollbar = tk.Scrollbar(body, orient=tk.VERTICAL, command=listbox.yview,
                                 width=max(16, line_height))   # wide enough for a finger
        listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # Tap a name to copy it; press and drag to scroll (touch-friendly).
    copied = tk.Label(window, text="Tap a system to copy it", anchor=tk.CENTER)
    press = {"y": 0, "dragging": False}

    def on_press(event: Any) -> str:
        press["y"], press["dragging"] = event.y, False
        listbox.scan_mark(event.x, event.y)
        return "break"

    def on_motion(event: Any) -> str:
        if press["dragging"] or abs(event.y - press["y"]) > 6:
            press["dragging"] = True
            listbox.scan_dragto(event.x, event.y)
        return "break"

    def on_release(event: Any) -> str:
        if not press["dragging"] and systems:
            position = listbox.index(f"@{event.x},{event.y}")
            index = int(position.split(".")[0]) - 1
            box = listbox.bbox(position)    # a tap below the last row lands on it: only a tap on the text counts
            if 0 <= index < len(systems) and box and box[1] <= event.y <= box[1] + box[3]:
                _copy_system(systems[index])
                listbox.tag_remove("picked", "1.0", tk.END)
                listbox.tag_add("picked", f"{index + 1}.0", f"{index + 1}.end")
                copied.configure(text=f"Copied: {systems[index]}")
                _set_status(f"Copied: {systems[index]}")
        return "break"

    listbox.bind("<Button-1>", on_press)
    listbox.bind("<B1-Motion>", on_motion)
    listbox.bind("<ButtonRelease-1>", on_release)

    ok = ttk.Button(window, text="OK", width=12, command=window.destroy)
    # Pack the bottom row before the list so OK always keeps its space on small screens:
    # OK at the very bottom, the "Copied" line just above it, the list takes the rest.
    ok.pack(side=tk.BOTTOM, pady=(4, 10), before=body)
    if systems:
        copied.pack(side=tk.BOTTOM, pady=(0, 2), before=body)
    ok.focus_set()
    window.bind("<Return>", lambda _event: window.destroy())
    window.bind("<Escape>", lambda _event: window.destroy())

    # Place it next to EDMC, kept fully on screen.
    window.update_idletasks()
    root = _app_frame.winfo_toplevel()
    width, height = window.winfo_reqwidth(), window.winfo_reqheight()
    x = min(max(0, root.winfo_rootx() + 40), max(0, window.winfo_screenwidth() - width))
    y = min(max(0, root.winfo_rooty() + 40), max(0, window.winfo_screenheight() - height - 40))
    window.geometry(f"+{x}+{y}")
    # A size remembered from an earlier (empty) list must never shrink the window below what it needs.
    window.minsize(max(260, width), min(max(height, 240), window.winfo_screenheight() - 80))


# ---------------------------------------------------------------------------
# Expedition tab (Jonathan, 1 Nov 2026): import several destinations, then plot them in the order entered or in
# the most efficient order (the same ordering and leg plotting as the Multi-Stop Trip). It follows Highway's habits:
# clickable Highlighted words that open the same scrollable list pop-up or switch a setting, and one window for edits.
# ---------------------------------------------------------------------------
MAX_EXPEDITION_STOPS = 40
_exp_ui: dict[str, Any] = {}
_exp_editor = None
_exp_busy = False


def _exp() -> dict[str, Any]:
    saved = _settings.get("expedition")
    saved = saved if isinstance(saved, dict) else {}
    stops = [str(item).strip() for item in saved.get("stops") or [] if _looks_like_place(str(item).strip())]
    systems = saved.get("systems") if isinstance(saved.get("systems"), dict) else {}
    return {"stops": stops[:MAX_EXPEDITION_STOPS], "order": "entered" if saved.get("order") == "entered" else "efficient",
            "loop": bool(saved.get("loop")), "keep_last": saved.get("keep_last", True) is not False,
            "systems": {str(k): str(v) for k, v in systems.items() if str(v).strip()}}


def _exp_save(**changes: Any) -> None:
    data = _exp()
    data.update(changes)
    _settings["expedition"] = data
    _save_settings()
    _refresh_expedition()


def _csv_place_names(text: str) -> list[str] | None:
    """Names from a CSV with a header row (EDD route or expedition export, Spansh, ours): the System / System Name /
    StarSystem / Waypoint column. Quoted notes that run over several lines stay inside their cell. None when the text
    is not such a CSV, so plain lines are read the simple way."""
    first = text.lstrip("﻿").lstrip().split("\n", 1)[0]
    if "," not in first and "\t" not in first:
        return None
    try:
        rows = list(csv.reader(io.StringIO(text.lstrip("﻿"), newline=""),
                               delimiter="\t" if first.count("\t") > first.count(",") else ","))
    except csv.Error:
        return None
    if not rows:
        return None
    keys = [re.sub(r"[^a-z0-9]", "", cell.lower()) for cell in rows[0]]
    column = next((keys.index(key) for key in ("systemname", "system", "starsystem", "waypoint", "name")
                   if key in keys), None)
    if column is None:
        return None
    return [row[column].strip() for row in rows[1:] if len(row) > column and row[column].strip()]


def _looks_like_place(name: str) -> bool:
    """A system, station or carrier name: short, no web address, no sentence punctuation. Keeps notes and links
    that sit beside the names in an export from ever becoming stops."""
    return (0 < len(name) <= 50 and "http" not in name.casefold() and "://" not in name and len(name.split()) <= 6
            and re.fullmatch(r"[\w .'’()*&-]+", name) is not None)


def _parse_stop_lines(text: str) -> list[str]:
    """One destination per line. Numbering and bullets are dropped; a CSV with a header gives its system column,
    any other CSV line its first column."""
    named = _csv_place_names(text)
    if named is not None:
        stops, seen = [], set()
        for name in named:
            if name.casefold() not in seen and _looks_like_place(name):
                seen.add(name.casefold())
                stops.append(name)
        return stops[:MAX_EXPEDITION_STOPS]
    stops, seen = [], set()
    for line in text.replace("\r", "\n").split("\n"):
        name = re.sub(r"^\s*(?:\d+[.)]\s+|[-*\u2022]\s+)", "", line)
        name = name.split(",")[0].strip().strip(";\t \"")
        if (not name or name.casefold() in ("system name", "name", "system") or name.casefold() in seen
                or not _looks_like_place(name)):
            continue
        seen.add(name.casefold())
        stops.append(name)
    return stops[:MAX_EXPEDITION_STOPS]


def _resolve_stop(name: str) -> dict[str, Any]:
    """A line can be a system, a station or a carrier: a known system is used as it is, otherwise a station
    or carrier of that name gives its system."""
    if _any_coordinates(name) is not None:
        return {"name": name, "system": name}
    try:
        for station, system in _spansh_stations(name):
            if station.casefold() == name.casefold():
                return {"name": name, "system": system}
    except RuntimeError:
        pass
    return {"name": name, "system": name}


def _exp_say(text: str) -> None:
    label = _exp_ui.get("status")
    if label is not None and _widget_alive(label):
        label.configure(text=text)
        label.grid() if text else label.grid_remove()


def _refresh_expedition() -> None:
    """The Expedition tab shows data only (and Pause): everything that changes the expedition is in its menu."""
    if not _exp_ui or not _widget_alive(_exp_ui.get("page")):
        return
    parked = _parked()
    paused = bool(parked) and parked.get("source") == "expedition"
    loaded = bool(_route_systems) and _settings.get("route_source") == "expedition"
    _exp_ui["pause"].configure(text="Plotting…" if _exp_busy else ("Resume" if paused else "Pause"))
    if loaded or paused or _exp_busy:
        _exp_ui["pause_row"].grid()                     # only while there is an expedition to pause or resume
    else:
        _exp_ui["pause_row"].grid_remove()
    points = _expedition_points() if loaded else []
    passed = sum(1 for index, _ in points if index <= max(0, _route_index))
    if loaded and points:
        done, left = _jump_counts()
        following = points[passed][1] if passed < len(points) else ""
        _exp_ui["next_name"], _exp_ui["final_name"] = following, points[-1][1]
        _exp_ui["next"].configure(text=f"Next stop: {following or 'none, you have arrived'}")
        _exp_ui["final"].configure(text=f"Final stop: {points[-1][1]}")
        _exp_ui["done"].configure(text=f": {done}{SEP}")
        _exp_ui["left"].configure(text=f": {left}")
        stats = _exp_stats()
        ahead = _exp_left_ly([name for _, name in points[passed:]])
        _exp_ui["travel"].configure(text=f"Travelled: {float(stats.get('ly') or 0):,.0f} Ly"
                                         f"{SEP}Left: {'~' + format(ahead, ',.0f') + ' Ly' if ahead is not None else '…'}")
        _exp_ui["clock"].configure(text=f"Time: {_span_text(float(stats.get('sec') or 0))} (without pauses)")
        _exp_ui["data"].grid()
    else:
        _exp_ui["next_name"] = _exp_ui["final_name"] = ""
        _exp_ui["data"].grid_remove()
    if paused:
        left_stops = len(parked.get("stops_left") or [])
        _exp_ui["hint"].configure(text=f"Expedition paused at {parked.get('at') or 'your last position'}"
                                       f"{', ' + str(left_stops) + ' stops left' if left_stops else ''}. Press Resume.")
        _exp_ui["hint"].grid()
    elif not loaded:
        _exp_ui["hint"].configure(text="None Loaded\nUse the Navigation Menu, then Expedition.")
        _exp_ui["hint"].grid()
    else:
        _exp_ui["hint"].grid_remove()
    _refresh_expedition_bar()


EXP_BAR_WIDTH, EXP_BAR_HEIGHT = 300, 34
EXP_BAR_MIN, EXP_BAR_STEP = 3, 2


def _exp_dots_change(delta: int) -> None:
    """The - and + beside the bar: show fewer or more stops at once (two at a time) so a long expedition fits."""
    now = int(_settings.get("expedition_dots", 8) or 0) or MAX_EXPEDITION_STOPS
    _settings["expedition_dots"] = min(MAX_EXPEDITION_STOPS, max(EXP_BAR_MIN, now + delta * EXP_BAR_STEP))
    _save_settings()
    _refresh_expedition_bar()


def _expedition_points() -> list[tuple[int, str]]:
    """The stops you entered, in route order: (position in the route, name)."""
    major, seen, points = _major_names(), set(), []
    for index, name in enumerate(_route_systems):
        key = name.casefold()
        if key in major and key not in seen:
            seen.add(key)
            points.append((index, name))
    return points


# What the expedition has cost so far: light years jumped and time travelled, both counted only while an expedition route
# is loaded (a pause or a rescue stops the count; the game being closed overnight is not counted either). Distance left is
# a straight line through your remaining stops, looked up in the background (Spansh / EDSM / your journals).
EXP_GAP_LIMIT = 1800.0          # seconds: a longer quiet gap between journal events was not travel
_exp_clock: float | None = None
_exp_left: dict[str, Any] = {"key": None, "ly": None, "busy": False}
_coord_cache: dict[str, tuple[float, float, float] | None] = {}


def _exp_stats() -> dict[str, Any]:
    stats = _settings.get("exp_stats")
    return stats if isinstance(stats, dict) else {}


def _exp_stats_reset() -> None:
    global _exp_clock
    _settings["exp_stats"] = {"ly": 0.0, "sec": 0.0}
    _exp_clock = None


def _span_text(seconds: float) -> str:
    minutes = int(seconds // 60)
    days, rest = divmod(minutes, 1440)
    hours, minutes = divmod(rest, 60)
    if days:
        return f"{days}d {hours}h {minutes:02d}m"
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def _event_time(entry: dict[str, Any]) -> float | None:
    try:
        return datetime.fromisoformat(str(entry["timestamp"]).replace("Z", "+00:00")).timestamp()
    except (KeyError, ValueError):
        return None


def _note_expedition_travel(entry: dict[str, Any]) -> None:
    """Called for every journal event: add the jump and the time since the last event to the expedition's totals."""
    global _exp_clock
    if _settings.get("route_source") != "expedition" or not _route_systems:
        _exp_clock = None
        return
    stats = dict(_exp_stats())
    when = _event_time(entry)
    if when is not None:
        if _exp_clock is not None and 0 < when - _exp_clock <= EXP_GAP_LIMIT:
            stats["sec"] = float(stats.get("sec") or 0) + when - _exp_clock
        _exp_clock = when
    jumped = entry.get("event") == "FSDJump"
    if jumped:
        try:
            stats["ly"] = float(stats.get("ly") or 0) + float(entry.get("JumpDist") or 0)
        except (TypeError, ValueError):
            pass
    _settings["exp_stats"] = stats
    if jumped:
        _save_settings()


def _stop_coordinates(name: str) -> tuple[float, float, float] | None:
    if name.casefold() not in _coord_cache:
        _coord_cache[name.casefold()] = _any_coordinates(name)
    return _coord_cache[name.casefold()]


def _exp_left_ly(stops: list[str]) -> float | None:
    """Light years left in a straight line from here through the stops still ahead. The numbers come in on a background
    thread; until then the last answer (or None) is shown."""
    here = str(_snapshot.get("location", {}).get("system_name") or "")
    key = (here.casefold(), tuple(name.casefold() for name in stops))
    if _exp_left["key"] == key or _exp_left["busy"] or not stops or not here:
        return _exp_left["ly"] if stops else 0.0
    _exp_left["busy"] = True

    def worker() -> None:
        total, position, found = 0.0, _stop_coordinates(here), False
        for name in stops:
            ahead = _stop_coordinates(name)
            if position and ahead:
                total += math.dist(position, ahead)
                found = True
            if ahead:
                position = ahead

        def apply() -> None:
            _exp_left.update(key=key, ly=total if found else None, busy=False)
            _refresh_expedition()
        try:
            _app_frame.after(0, apply)
        except (tk.TclError, RuntimeError):
            _exp_left["busy"] = False
    threading.Thread(target=worker, daemon=True).start()
    return _exp_left["ly"]


def _expedition_dot_clicked(name: str) -> None:
    """A dot copies its system to the clipboard. It never plots: you may only want to look at it."""
    _copy_system(name)
    _exp_say(f"Copied: {name}")


def _refresh_expedition_bar() -> None:
    """The Expedition's progress bar: a line with a dot for each stop you entered, a marker for where you are between
    them. A long expedition slides: the window follows you (the last stop passed, then the ones ahead)."""
    bar, caption, barrow = _exp_ui.get("bar"), _exp_ui.get("caption"), _exp_ui.get("barrow")
    if not _widget_alive(bar):
        return
    points = _expedition_points()
    if _settings.get("route_source") != "expedition" or not points or not _route_systems:
        barrow.grid_remove()
        caption.grid_remove()
        return
    normal, highlight, background = _palette()
    bar.configure(background=background)
    caption.configure(background=background, foreground=normal)
    for label in (_exp_ui.get("minus"), _exp_ui.get("plus")):
        label.configure(background=background, foreground=highlight)
    barrow.grid()
    caption.grid()
    bar.delete("all")
    here = max(0, _route_index)
    passed = sum(1 for index, _ in points if index <= here)          # stops already reached
    size = int(_settings.get("expedition_dots", 8) or 0) or len(points)
    first = max(0, min(passed - 1, len(points) - size))
    visible = points[first:first + size]
    left, right, y = 16, EXP_BAR_WIDTH - 16, 18
    step = (right - left) / max(1, len(visible) - 1)
    xs = [left + step * n for n in range(len(visible))] if len(visible) > 1 else [EXP_BAR_WIDTH / 2]
    bar.create_line(xs[0], y, xs[-1], y, fill=normal, width=2)
    if passed:                                                       # the part already travelled
        reached_x = [xs[n] for n, (index, _) in enumerate(visible) if index <= here]
        if reached_x:
            bar.create_line(xs[0], y, reached_x[-1], y, fill=highlight, width=3)
    for n, (index, name) in enumerate(visible):
        number = first + n
        done, upcoming = index <= here, first + n == passed
        radius = 5
        if upcoming:
            bar.create_oval(xs[n] - 8, y - 8, xs[n] + 8, y + 8, outline=highlight, width=1)
        tag = f"dot{number}"
        bar.create_oval(xs[n] - radius, y - radius, xs[n] + radius, y + radius, tags=(tag,),
                        fill=highlight if done else background, outline=highlight if (done or upcoming) else normal, width=2)
        bar.tag_bind(tag, "<Button-1>", lambda _event, system=name: _expedition_dot_clicked(system))
        bar.tag_bind(tag, "<Enter>", lambda _event: bar.configure(cursor="hand2"))
        bar.tag_bind(tag, "<Leave>", lambda _event: bar.configure(cursor=""))
    # where you are, between the stop before and the stop after
    if passed == 0:
        marker = max(4, xs[0] - 10)
    elif passed >= len(points):
        marker = xs[-1]
    else:
        before, after = visible[passed - 1 - first], visible[passed - first]
        span = max(1, after[0] - before[0])
        marker = xs[passed - 1 - first] + (xs[passed - first] - xs[passed - 1 - first]) * min(1.0, (here - before[0]) / span)
    bar.create_polygon(marker - 4, y - 14, marker + 4, y - 14, marker, y - 7, fill=highlight, outline=highlight)
    if first > 0:
        bar.create_text(3, y + 11, text="\u25c0", fill=normal, anchor=tk.W, font=("TkDefaultFont", 7))
    if first + size < len(points):
        bar.create_text(EXP_BAR_WIDTH - 3, y + 11, text="\u25b6", fill=normal, anchor=tk.E, font=("TkDefaultFont", 7))
    text = f"Stop {min(passed + 1, len(points))} of {len(points)}" if passed < len(points) else f"All {len(points)} stops reached"
    if passed < len(points):
        text += f": {points[passed][1]}"
    caption.configure(text=text)


def _build_expedition_page(page: tk.Frame) -> None:
    """Data only, so nothing can be tapped by accident on a six-month expedition. Pause is the one button. Plotting, the
    stops, the order, the loop and cancelling live in the Expedition menu (click Expedition)."""
    _exp_ui.clear()
    _exp_ui["page"] = page
    _exp_ui["next_name"] = _exp_ui["final_name"] = ""

    def piece(parent: tk.Frame, text: str = "", command=None) -> tk.Label:
        label = tk.Label(parent, text=text, anchor=tk.W, padx=0, bd=0)
        label.pack(side=tk.LEFT)
        if command is not None:
            label.configure(cursor="hand2", takefocus=True)
            _theme_controls.append(label)
            for sequence in ("<Button-1>", "<Return>", "<space>"):
                label.bind(sequence, lambda _event: command())
        return label

    page.columnconfigure(0, weight=1)
    hint = tk.Label(page, anchor=tk.CENTER, justify=tk.CENTER, wraplength=320)      # a short notice: centred, as few words as possible
    hint.grid(row=0, column=0, sticky=tk.EW)
    _exp_ui["hint"] = hint
    data = tk.Frame(page)
    data.grid(row=1, column=0, sticky=tk.W)
    _exp_ui["data"] = data
    _exp_ui["next"] = piece(tk.Frame(data), "", None)
    _exp_ui["next"].master.pack(anchor=tk.W)
    for label, key in ((_exp_ui["next"], "next_name"),):
        label.configure(cursor="hand2", takefocus=True)
        _theme_controls.append(label)
        for sequence in ("<Button-1>", "<Return>", "<space>"):
            label.bind(sequence, lambda _event, k=key: _exp_ui.get(k) and _expedition_dot_clicked(_exp_ui[k]))
    final_row = tk.Frame(data)
    final_row.pack(anchor=tk.W)
    _exp_ui["final"] = piece(final_row)
    _exp_ui["final"].configure(cursor="hand2", takefocus=True)
    _theme_controls.append(_exp_ui["final"])
    for sequence in ("<Button-1>", "<Return>", "<space>"):
        _exp_ui["final"].bind(sequence, lambda _event: _exp_ui.get("final_name") and _expedition_dot_clicked(_exp_ui["final_name"]))
    jumps = tk.Frame(data)
    jumps.pack(anchor=tk.W)
    piece(jumps, "Jumps ")
    piece(jumps, "Done", _show_completed)
    _exp_ui["done"] = piece(jumps)
    piece(jumps, "Left", _show_remaining)
    _exp_ui["left"] = piece(jumps)
    travel = tk.Frame(data)
    travel.pack(anchor=tk.W)
    _exp_ui["travel"] = piece(travel)
    clock = tk.Frame(data)
    clock.pack(anchor=tk.W)
    _exp_ui["clock"] = piece(clock)

    # The bar, with a small - on the left and + on the right: a fixed-size square that never changes with its words.
    barrow = tk.Frame(page)
    barrow.grid(row=2, column=0, pady=(4, 0))
    _exp_ui["barrow"] = barrow

    def small_button(column: int, text: str, delta: int) -> tk.Label:
        box = tk.Frame(barrow, width=22, height=22, bd=2, relief=tk.RAISED)
        box.grid(row=0, column=column, padx=4)
        box.pack_propagate(False)
        label = tk.Label(box, text=text, cursor="hand2", takefocus=True)
        label.pack(fill=tk.BOTH, expand=True)
        for widget in (box, label):
            widget.bind("<Button-1>", lambda _event, d=delta: _exp_dots_change(d))
        return label

    _exp_ui["minus"] = small_button(0, "\u2212", -1)
    bar = tk.Canvas(barrow, width=EXP_BAR_WIDTH, height=EXP_BAR_HEIGHT, highlightthickness=0, borderwidth=0)
    bar.grid(row=0, column=1)
    _exp_ui["bar"] = bar
    _exp_ui["plus"] = small_button(2, "+", 1)
    caption = tk.Label(page, anchor=tk.CENTER, justify=tk.CENTER, wraplength=320)
    caption.grid(row=3, column=0)
    _exp_ui["caption"] = caption
    pause = tk.Frame(page)
    pause.grid(row=4, column=0, sticky=tk.W)
    _exp_ui["pause_row"] = pause
    _exp_ui["pause"] = piece(pause, "Pause", _expedition_pause)
    status = tk.Label(page, anchor=tk.W, justify=tk.LEFT, wraplength=320)
    status.grid(row=5, column=0, sticky=tk.W)
    status.grid_remove()
    _exp_ui["status"] = status
    _refresh_expedition()


# ---- the Expedition menu (click Expedition, or the header / cog while on the tab) -----------------------------------
def _exp_toggle_order() -> None:
    _exp_save(order="efficient" if _exp()["order"] == "entered" else "entered")


def _exp_toggle_loop() -> None:
    _exp_save(loop=not _exp()["loop"])


def _exp_toggle_last() -> None:
    _exp_save(keep_last=not _exp()["keep_last"])


def _expedition_cancel() -> None:
    """Cancel the expedition route (and a paused one). The list of stops stays, so it can be plotted again."""
    parked = _parked()
    loaded = bool(_route_systems) and _settings.get("route_source") == "expedition"
    paused = bool(parked) and parked.get("source") == "expedition"
    if not (loaded or paused):
        _exp_say("There is no expedition to cancel.")
        return
    if not messagebox.askyesno("Cancel Expedition", "Cancel the expedition? Your list of stops stays, but the route and "
                               "your place on it are cleared.", parent=_app_frame):
        return
    if loaded:
        _clear_route()
        try:
            _persist_route()
        except OSError:
            logger.exception("Could not save cancelled expedition")
    if paused:
        _settings["parked"] = {}
    _exp_stats_reset()
    _save_settings()
    _refresh_route_label()
    _refresh_expedition()
    _exp_say("Expedition cancelled. Your stops are kept.")


def _expedition_menu_items() -> list[tuple[str, Any, bool] | None]:
    """(label, command, enabled), None for a separator."""
    data = _exp()
    parked = _parked()
    paused = bool(parked) and parked.get("source") == "expedition"
    loaded = bool(_route_systems) and _settings.get("route_source") == "expedition"
    items: list[tuple[str, Any, bool] | None] = [
        ("Plot Expedition", _expedition_plot, not _exp_busy),
        (f"Edit Stops ({len(data['stops'])})…", _open_expedition_editor, True),
        ("Show Stops", _exp_show_stops, bool(data["stops"])),
        None,
        (f"Order: {'As entered' if data['order'] == 'entered' else 'Efficient'}", _exp_toggle_order, True),
        (f"Loop: {'On' if data['loop'] else 'Off'}", _exp_toggle_loop, True)]
    if data["order"] != "entered" and not data["loop"]:
        items.append((f"Last stop stays last: {'Yes' if data['keep_last'] else 'No'}", _exp_toggle_last, True))
    items += [None,
              ("Resume Expedition" if paused else "Pause Expedition", _expedition_pause, paused or loaded),
              ("Cancel Expedition…", _expedition_cancel, paused or loaded)]
    return items


def _exp_show_stops() -> None:
    stops = _exp()["stops"]
    _show_systems_popup(f"Expedition Stops ({len(stops)})", stops, "No stops yet. Use Edit to add some.")


def _fit_window(window) -> None:
    """Suite rule: a window's buttons (OK, Save, Cancel...) are never hidden when it opens. The window never
    gets smaller than what shows everything, even if a smaller size was remembered or dragged to."""
    try:
        window.update_idletasks()
        window.minsize(window.winfo_reqwidth(), window.winfo_reqheight())
    except tk.TclError:
        pass


def _place_choices(text: str) -> list[dict[str, str]]:
    """What a typed name could mean: stations and carriers (with their system and type), then systems."""
    choices: list[dict[str, str]] = []
    try:
        for name, system, kind in _spansh_stations_detail(text)[:6]:
            choices.append({"name": name, "system": system,
                            "label": f"{name}  ({system}{', ' + kind if kind else ''})"})
    except RuntimeError as error:
        logger.info("No station matches for %r (%s)", text, error)
    try:
        for name in _spansh_names(text)[:4]:
            if not any(c["name"].casefold() == name.casefold() and c["system"].casefold() == name.casefold() for c in choices):
                choices.append({"name": name, "system": name, "label": f"{name}  (system)"})
    except RuntimeError as error:
        logger.info("No system matches for %r (%s)", text, error)
    return choices


def _open_place_editor(title: str, intro: str, items: list[dict[str, str]], on_save, window_id: str,
                       extra_buttons=(), option=None, plot=None):
    """One window for building a list of places, used by Expedition and Rescue: type a name, pick what you meant
    from what is found (three different Jamesons are three lines), press Add. items are {"place", "system"};
    Save hands the finished list to on_save. extra_buttons: (label, function(add_places, window)).
    option: (text, value, on_change(bool)) is a checkbox under Remove. plot: function(option value) adds a Plot Route
    button: it saves the list like Save, closes the window and plots."""
    window = tk.Toplevel(_app_frame)
    window.title(title)
    _attach_popup(window, window_id)
    try:
        window.transient(_app_frame.winfo_toplevel())
    except tk.TclError:
        pass
    state: dict[str, Any] = {"items": [dict(item) for item in items], "found": [], "picked": None,
                             "lookup": None, "busy": False}
    results: queue.Queue = queue.Queue()
    window.navigator_places = lambda: [dict(item) for item in state["items"]]      # for Save File
    buttons = tk.Frame(window)
    buttons.pack(side=tk.BOTTOM, pady=(4, 10))             # first in the pack order: never squeezed out
    body = tk.Frame(window)
    body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(10, 0))
    _autowrap(tk.Label(body, text=intro, justify=tk.CENTER, anchor=tk.CENTER, wraplength=380)).pack(fill=tk.X)
    row = tk.Frame(body)
    row.pack(fill=tk.X, pady=(6, 0))
    entry = tk.Entry(row, width=34)
    entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    add_button = ttk.Button(row, text="Add", width=8)
    add_button.pack(side=tk.LEFT, padx=(6, 0))
    hits = tk.Listbox(body, height=5, activestyle="none", exportselection=False)
    tk.Label(body, text="Your list (the first one is first)", anchor=tk.W).pack(anchor=tk.W, pady=(8, 0))
    middle = tk.Frame(body)
    middle.pack(fill=tk.BOTH, expand=True)
    listbox = tk.Listbox(middle, height=8, activestyle="none", exportselection=False)
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    side = tk.Frame(middle)
    side.pack(side=tk.RIGHT, anchor=tk.N, padx=(6, 0))
    note = tk.Label(body, text="", anchor=tk.CENTER, justify=tk.CENTER, wraplength=380)
    note.pack(fill=tk.X)
    _autowrap(note)
    optrow =tk.Frame(body)
    optrow.pack(before=note, pady=(6, 0))                  # the On / Off option sits centred under the list

    def label(item: dict[str, str]) -> str:
        system = item.get("system") or ""
        return f"{item['place']}  ({system})" if system and system.casefold() != item["place"].casefold() else item["place"]

    def refresh(select: int | None = None) -> None:
        listbox.delete(0, tk.END)
        for number, item in enumerate(state["items"], start=1):
            listbox.insert(tk.END, f"{number}. {label(item)}")
        if select is not None and state["items"]:
            index = min(max(select, 0), len(state["items"]) - 1)
            listbox.selection_set(index)
            listbox.see(index)

    def hide_hits() -> None:
        state["found"], state["picked"] = [], None
        hits.pack_forget()

    def add_places(places: list[str]) -> None:
        """Names added as typed (a pasted list or a file): no picking, the system is looked up later."""
        for place in places:
            if len(state["items"]) < 40 and not any(i["place"].casefold() == place.casefold() for i in state["items"]):
                state["items"].append({"place": place, "system": ""})
        refresh(len(state["items"]) - 1)

    def add(_event: Any = None) -> None:
        text = entry.get().strip()
        if not text:
            return
        if state["busy"] or state["lookup"] is not None:
            note.configure(text="Still searching… press Add again in a moment.")
            return
        picked = state["picked"] if state["picked"] and state["picked"]["name"].casefold() == text.casefold() else None
        if picked is None:
            exact = [c for c in state["found"] if c["name"].casefold() == text.casefold()]
            if len(exact) == 1:
                picked = exact[0]                      # only one thing has exactly this name
            elif state["found"]:
                note.configure(text="Make a selection from the list above first.")
                return
        item = {"place": text, "system": picked["system"] if picked else ""}
        if len(state["items"]) >= 40:
            note.configure(text="A list can have up to 40 places.")
            return
        if any(i["place"].casefold() == item["place"].casefold() and i["system"].casefold() == item["system"].casefold()
               for i in state["items"]):
            entry.delete(0, tk.END)
            hide_hits()
            note.configure(text="That one is already in the list.")
            return
        state["items"].append(item)
        entry.delete(0, tk.END)
        hide_hits()
        note.configure(text="")
        refresh(len(state["items"]) - 1)

    def chosen() -> int | None:
        picked = listbox.curselection()
        return picked[0] if picked and picked[0] < len(state["items"]) else None

    def move(step: int) -> None:
        index = chosen()
        if index is not None and 0 <= index + step < len(state["items"]):
            items_ = state["items"]
            items_[index], items_[index + step] = items_[index + step], items_[index]
            refresh(index + step)

    def remove() -> None:
        index = chosen()
        if index is not None:
            del state["items"][index]
            refresh(index)

    def clear_all() -> None:
        if state["items"] and messagebox.askyesno("Clear List", "Remove every place from this list?", parent=window):
            state["items"].clear()
            refresh(0)

    for text_, command in (("Move Up", lambda: move(-1)), ("Move Down", lambda: move(1)), ("Remove", remove),
                           ("Clear List", clear_all)):
        ttk.Button(side, text=text_, width=12, command=command).pack(pady=1)
    option_var = tk.BooleanVar(window, value=bool(option[1])) if option else None
    if option:
        # An On / Off toggle under the words: highlighted when On, plain when Off, and it says which.
        tk.Label(optrow, text=option[0], anchor=tk.E).pack(side=tk.LEFT, padx=(0, 8))
        # A button never changes size with its words: a fixed box, and the same font for On and Off (only the colour
        # changes), so the toggle cannot move or grow when it is switched.
        box = tk.Frame(optrow, width=84, height=26, bd=1, relief=tk.RAISED)
        box.pack(side=tk.LEFT)
        box.pack_propagate(False)
        toggle = tk.Label(box, anchor=tk.CENTER, cursor="hand2", takefocus=True)
        toggle.pack(fill=tk.BOTH, expand=True)
        toggle.bind("<Button-1>", lambda _event: flip())

        def paint() -> None:
            normal, highlight, background = _palette()
            on = bool(option_var.get())
            toggle.configure(text="On" if on else "Off", foreground=highlight if on else normal, background=background)

        def flip(_event: Any = None) -> None:
            option_var.set(not option_var.get())
            paint()
            option[2](bool(option_var.get()))

        for sequence in ("<Button-1>", "<Return>", "<space>"):
            toggle.bind(sequence, flip)
        paint()

    def later(_event: Any = None) -> None:
        state["picked"] = None
        if state["lookup"] is not None:
            window.after_cancel(state["lookup"])
        state["lookup"] = window.after(400, search)

    def search() -> None:
        state["lookup"] = None
        text = entry.get().strip()
        if len(text) < 3:
            hide_hits()
            return
        state["busy"] = True

        def worker() -> None:
            results.put((text, _place_choices(text)))
        threading.Thread(target=worker, daemon=True).start()

    def pick(_event: Any = None) -> None:
        index = hits.curselection()
        if index and index[0] < len(state["found"]):
            state["picked"] = state["found"][index[0]]
            entry.delete(0, tk.END)
            entry.insert(0, state["picked"]["name"])
            hits.pack_forget()
            note.configure(text=f"Selected: {state['picked']['label']}. Press Add.")

    def pump() -> None:
        if not _widget_alive(window):
            return
        try:
            while True:
                text, found = results.get_nowait()
                state["busy"] = False
                if text != entry.get().strip():
                    continue
                state["found"] = found
                if found:
                    hits.delete(0, tk.END)
                    for choice in found:
                        hits.insert(tk.END, choice["label"])
                    hits.pack(fill=tk.X, after=row)
                    note.configure(text="Make a selection.")
                else:
                    hide_hits()
                    note.configure(text="Nothing found with that name. Add keeps it as typed.")
        except queue.Empty:
            pass
        window.after(200, pump)

    for text_, command in (("Save", None), ("Cancel", window.destroy)):
        if text_ == "Save":
            def save() -> None:
                on_save([dict(item) for item in state["items"]])
                window.destroy()
            command = save
        ttk.Button(buttons, text=text_, width=10, command=command).pack(side=tk.LEFT, padx=4)
    for text_, function in extra_buttons:
        ttk.Button(buttons, text=text_, width=10,
                   command=lambda f=function: f(add_places, window)).pack(side=tk.LEFT, padx=4)
    if plot is not None:
        def plot_route() -> None:
            on_save([dict(item) for item in state["items"]])
            window.destroy()
            plot(bool(option_var.get()) if option_var is not None else False)
        ttk.Button(buttons, text="Plot Route", width=10, command=plot_route).pack(side=tk.LEFT, padx=4)
    add_button.configure(command=add)
    entry.bind("<Return>", add)
    entry.bind("<KeyRelease>", lambda event: later() if event.keysym not in ("Return", "Tab") else None)
    hits.bind("<<ListboxSelect>>", pick)
    window.bind("<Escape>", lambda _event: window.destroy())
    window.after(200, pump)
    refresh(0)
    _fit_window(window)
    root = _app_frame.winfo_toplevel()
    width, height = window.winfo_reqwidth(), window.winfo_reqheight()
    x = min(max(0, root.winfo_rootx() + 40), max(0, window.winfo_screenwidth() - width))
    y = min(max(0, root.winfo_rooty() + 40), max(0, window.winfo_screenheight() - height - 40))
    window.geometry(f"+{x}+{y}")
    entry.focus_set()
    return window


def _paste_places(add_places, window) -> None:
    try:
        add_places(_parse_stop_lines(window.clipboard_get()))
    except tk.TclError:
        pass


def _save_places_file(add_places, window) -> None:
    """Save the list as a CSV that Load File (and the Highway's Load Route) reads straight back: one place per row
    under System Name, with the system it is in beside it."""
    items = window.navigator_places()
    if not items:
        messagebox.showinfo("Save File", "The list is empty.", parent=window)
        return
    path = filedialog.asksaveasfilename(parent=window, title="Save List", defaultextension=".csv",
                                        filetypes=[("CSV list", "*.csv"), ("All files", "*.*")])
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["System Name", "Located In"])
            for item in items:
                writer.writerow([item["place"], item.get("system") or item["place"]])
    except OSError as error:
        messagebox.showerror("Save File", f"Could not save that file: {error}", parent=window)


def _load_places_file(add_places, window) -> None:
    path = filedialog.askopenfilename(
        parent=window, title="Load Places", filetypes=[("Text or CSV", "*.txt *.csv"), ("All files", "*.*")])
    if not path:
        return
    try:
        with open(path, encoding="utf-8-sig") as stream:
            add_places(_parse_stop_lines(stream.read()))
    except (OSError, UnicodeError) as error:
        messagebox.showerror("Load Places", f"Could not read that file: {error}", parent=window)


def _open_expedition_editor() -> None:
    global _exp_editor
    if _exp_editor is not None:
        try:
            _exp_editor.destroy()
        except tk.TclError:
            pass
    data = _exp()
    items = [{"place": name, "system": data["systems"].get(name.casefold(), "")} for name in data["stops"]]

    def save(done: list[dict[str, str]]) -> None:
        _exp_save(stops=[i["place"] for i in done],
                  systems={i["place"].casefold(): i["system"] for i in done if i["system"]})
    _exp_editor = _open_place_editor(
        "Expedition Stops", "Type a system, a station, or a carrier by its callsign (like H7H-7TZ), make a selection "
        "from the matches, and press Add. The list is the order entered.", items, save, "expedition",
        (("Paste", _paste_places), ("Save File", _save_places_file), ("Load File", _load_places_file)))


def _rescue_best_changed(value: bool) -> None:
    _settings["rescue_best"] = value
    _save_settings()


def _open_rescue_editor() -> None:
    global _resc_editor
    if _resc_editor is not None:
        try:
            _resc_editor.destroy()
        except tk.TclError:
            pass
    existing = _cases()
    items = [{"place": c["place"], "system": c["system"]} for c in existing if not c["done"]]

    def save(done: list[dict[str, str]]) -> None:
        opened = [{"place": i["place"], "system": i["system"], "done": False} for i in done]
        _cases_save(opened + [c for c in _cases() if c["done"]], backup=_rescue_snapshot())
        _rescue_resolve()
    _resc_editor = _open_place_editor(
        "Add Rescue Cases", "Type a system, a station, or a carrier by its callsign (like H7H-7TZ), make a selection "
        "from the matches, and press Add. The first one on the list is Now.", items, save, "rescue",
        (("Paste", _paste_places), ("Save File", _save_places_file), ("Load File", _load_places_file)),
        option=("Reorder the list by the most efficient route when plotting", bool(_settings.get("rescue_best", True)),
                _rescue_best_changed),
        plot=lambda best: _rescue_plot("efficient" if best else "listed"))


def _expedition_plot() -> None:
    """Plot the whole expedition as one route: efficient order, or the order entered; a loop comes back to the start."""
    global _exp_busy
    if _exp_busy:
        return
    data = _exp()
    if not data["stops"]:
        _exp_say("Add some stops first (Edit).")
        return
    origin = str(_snapshot.get("location", {}).get("system_name") or "")
    if not origin:
        _exp_say("Waiting for the game to say where you are. Try again in a moment.")
        return
    profile = _ship_profile()
    if not profile["ok"]:
        _exp_say("Ship data not found. Board your ship, then try again.")
        return
    if not _long_plot_notice(len(data["stops"])) or not _confirm_replace_route():
        return
    _exp_busy = True
    _refresh_expedition()
    _exp_say("Looking up your stops…")
    entered = data["order"] == "entered"
    efficiency = int(_settings.get("plot_efficiency", 70))

    def later(function) -> None:
        try:
            _app_frame.after(0, function)
        except (tk.TclError, RuntimeError):
            pass

    def worker() -> None:
        try:
            stops = []
            for name in data["stops"]:
                picked = data["systems"].get(name.casefold())
                stop = {"name": name, "system": picked} if picked else _resolve_stop(name)    # a picked one is not looked up again
                stop["fixed"] = entered
                stops.append(stop)
            route, info = _plot_trip(origin, stops, data["loop"], bool(data["keep_last"] and not entered),
                                     profile["range"], efficiency, profile["multiplier"], lambda: False,
                                     lambda text: later(lambda: _exp_say(text)))
            later(lambda: _expedition_done(route, info, origin, [s["system"] for s in stops]))
        except Exception as error:
            logger.exception("Expedition plot failed")
            message = str(error) if isinstance(error, RuntimeError) else "Unexpected error - see the EDMC log."
            later(lambda: _expedition_failed(message))
    threading.Thread(target=worker, daemon=True).start()


def _expedition_failed(text: str) -> None:
    global _exp_busy
    _exp_busy = False
    _refresh_expedition()
    _exp_say("Plot Failed: " + text + "\nYour loaded route is unchanged.")


def _expedition_done(route: list[tuple[str, int]], info: dict[str, Any], origin: str,
                     major: list[str] | None = None) -> None:
    """Load it like any other route and go to Highway, where Done/Left and the waypoints work as usual."""
    global _exp_busy
    _exp_busy = False
    _save_plotted_csv(route)
    _exp_stats_reset()                          # a new expedition starts its own count
    _set_route([system for system, _ in route], origin, kind="trip", legs=[jumps for _, jumps in route],
               source="expedition", major=major)
    _settings["tab"] = TABS[0]
    _save_settings()
    _refresh_expedition()
    _exp_say("")
    _refresh_route_label()
    _theme_event()
    _set_status(str(info.get("note") or "Expedition loaded.").split("\n")[0])


# ---------------------------------------------------------------------------
# Fleet Carrier and Trade routers (Spansh). Both are asked for in Plot New Route like the other types. The carrier route is
# a list of 500 ly carrier jumps with the tritium you must restock; the trade route is a chain of buy-here, sell-there stops.
# ---------------------------------------------------------------------------
SPANSH_CARRIER_URL = "https://spansh.co.uk/api/fleetcarrier/route"
SPANSH_TRADE_URL = "https://spansh.co.uk/api/trade/route"
CARRIER_CAPACITY = 25000       # every fleet carrier holds 25,000 t
CARRIER_JUMP = 500.0           # ly per carrier jump


def _plot_carrier(origin: str, end: str, used: float, cancelled) -> tuple[list[tuple[str, int]], dict[str, Any]]:
    """Spansh's Fleet Carrier router: the jumps, and where tritium must be restocked."""
    params = {"source": origin, "destinations": end, "capacity": CARRIER_CAPACITY, "capacity_used": int(used),
              "calculate_starting_fuel": 1}
    logger.info("Plot New Route: asking Spansh Fleet Carrier router %s", params)
    reply = _spansh_request(SPANSH_CARRIER_URL, params)
    job = reply.get("job") if isinstance(reply, dict) else None
    if not job:
        error = reply.get("error") if isinstance(reply, dict) else None
        raise RuntimeError(str(error) if error else "Spansh did not accept the request.")
    result = _spansh_result(job, cancelled)
    jumps = result.get("jumps") if isinstance(result, dict) else None
    route, bodies = [], {}
    for item in jumps or []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        name = str(item["name"])
        route.append((name, 0 if not route else 1))
        bodies[name.casefold()] = {"fuel_used": float(item.get("fuel_used") or 0),
                                   "restock": int(item.get("restock_amount") or 0) if item.get("must_restock") else 0}
    if len(route) < 2:
        raise RuntimeError("Spansh found no carrier route between those systems.")
    return route, bodies


def _plot_trade(origin: str, options: dict[str, Any], jump_range: float, cancelled
                ) -> tuple[list[tuple[str, int]], dict[str, Any]]:
    """Spansh's Trade router from a station: a chain of trades. The jump counts are estimates (distance / your range)."""
    params = {"system": origin, "station": str(options["trade_station"]), "starting_capital": int(options["trade_capital"]),
              "max_hops": int(options["trade_hops"]), "max_hop_distance": f"{jump_range:.2f}",
              "max_cargo": int(options["trade_cargo"]), "max_price_age": 86400,
              "max_system_distance": int(options["trade_ls"])}
    logger.info("Plot New Route: asking Spansh Trade router %s", params)
    reply = _spansh_request(SPANSH_TRADE_URL, params)
    job = reply.get("job") if isinstance(reply, dict) else None
    if not job:
        error = reply.get("error") if isinstance(reply, dict) else None
        raise RuntimeError(str(error) if error else "Spansh did not accept the request.")
    result = _spansh_result(job, cancelled)
    route, bodies = [], {}
    previous: dict[str, Any] | None = None
    for leg in result if isinstance(result, list) else []:
        if not isinstance(leg, dict) or not isinstance(leg.get("source"), dict) or not isinstance(leg.get("destination"), dict):
            continue
        source, destination = leg["source"], leg["destination"]
        goods = [(str(c.get("name") or "?"), int(c.get("amount") or 0))
                 for c in leg.get("commodities") or [] if isinstance(c, dict)]
        if not route:
            route.append((str(source.get("system") or origin), 0))
            bodies[route[0][0].casefold()] = {"station": str(source.get("station") or ""), "sell": [], "buy": goods,
                                              "profit": 0}
        elif previous is not None:
            bodies[route[-1][0].casefold()]["buy"] = goods
        miles = float(leg.get("distance") or 0)
        route.append((str(destination.get("system") or "?"), max(1, math.ceil(miles / max(jump_range, 1.0)))))
        bodies[route[-1][0].casefold()] = {"station": str(destination.get("station") or ""), "sell": goods, "buy": [],
                                           "profit": int(leg.get("total_profit") or 0)}
        previous = leg
    if len(route) < 2:
        raise RuntimeError("Spansh found no profitable trades from there. Try more hops, more cargo or a bigger distance.")
    return route, bodies


def _trade_text(label: str, item: dict[str, Any]) -> str:
    def goods(entries) -> str:
        return ", ".join(f"{amount} {name}" for name, amount in entries[:3]) + (", ..." if len(entries) > 3 else "")
    parts = []
    if item.get("sell"):
        parts.append("sell " + goods(item["sell"]))
    if item.get("buy"):
        parts.append("buy " + goods(item["buy"]))
    return f"{label} at {item.get('station') or '?'}: " + "; ".join(parts) if parts else f"{label} at {item.get('station') or '?'}."


# ---------------------------------------------------------------------------
# Parked routes (Jonathan, 1 Nov 2026): a rescue, or a pause on an expedition, sets the loaded route aside instead of
# throwing it away. When the rescue is over (or you press Resume) you choose: go back to where you left the route and carry
# on, or plot to the next waypoint the most efficient way. The same two choices for a Highway route and an Expedition.
# ---------------------------------------------------------------------------
_parked_label = None
_parked_busy = False
_resume_win = None


def _parked() -> dict[str, Any] | None:
    saved = _settings.get("parked")
    if isinstance(saved, dict) and isinstance(saved.get("systems"), list) and saved["systems"]:
        return saved
    return None


def _park_route(reason: str) -> bool:
    """Set the loaded route aside, remembering where you were on it. reason: "rescue" or "pause"."""
    if not _route_systems:
        return False
    systems, index = list(_route_systems), max(0, _route_index)
    source = str(_settings.get("route_source") or "")
    stops_left: list[str] = []
    if source == "expedition":
        data = _exp()
        reached = {name.casefold() for name in systems[:index + 1]}
        stops_left = [name for name in data["stops"]
                      if (data["systems"].get(name.casefold()) or name).casefold() not in reached]
    _settings["parked"] = {
        "systems": systems, "legs": list(_route_legs), "index": index, "kind": _route_kind,
        "bodies": dict(_route_bodies), "source": source, "reason": reason, "stops_left": stops_left,
        "major": list(_settings.get("route_major") or []),
        "at": str(_snapshot.get("location", {}).get("system_name") or systems[index])}
    _clear_route()
    _save_settings()
    _refresh_route_label()
    _refresh_expedition()
    return True


def _unpark_restore() -> None:
    """Put the parked route back exactly as it was."""
    global _route_index
    parked = _parked()
    if not parked:
        return
    _set_route(list(parked["systems"]), None, kind=parked.get("kind") or "neutron", bodies=parked.get("bodies"),
               legs=parked.get("legs"), source=str(parked.get("source") or ""), major=parked.get("major"))
    _route_index = min(max(0, int(parked.get("index") or 0)), len(parked["systems"]) - 1)
    _persist_route()
    _settings["parked"] = {}
    _save_settings()
    _refresh_route_label()
    _refresh_expedition()


def _rescue_make_room() -> bool:
    """A rescue is about to plot: a Highway or Expedition route is parked (not discarded). A rescue route already loaded
    is replaced after the usual question."""
    if not _route_systems:
        return True
    if _settings.get("route_source") == "rescue":
        return _confirm_replace_route()
    what = "expedition" if _settings.get("route_source") == "expedition" else "route"
    _park_route("rescue")
    _resc_say(f"Your {what} is parked. When the rescue is over you can carry on with it.")
    return True


def _parked_summary(parked: dict[str, Any]) -> str:
    left = max(0, len(parked["systems"]) - 1 - int(parked.get("index") or 0))
    what = "Expedition" if parked.get("source") == "expedition" else "Route"
    return f"{what} Parked at {parked.get('at') or parked['systems'][0]}: {left} Waypoint{'s' if left != 1 else ''} Left"


def _refresh_parked() -> None:
    parked = _parked()
    if _widget_alive(_parked_label):
        if parked and not _route_systems and not _settings.get("collapsed"):
            _parked_label.configure(text=f"{_parked_summary(parked)} | Resume")
            _parked_label.grid()
        else:
            _parked_label.grid_remove()


def _expedition_pause() -> None:
    """Pause: set the expedition route aside to study an area or do something else. With one already paused: resume."""
    parked = _parked()
    if parked and parked.get("source") == "expedition":
        _offer_resume()
        return
    if not _route_systems or _settings.get("route_source") != "expedition":
        _exp_say("No expedition route is loaded. Plot Expedition first.")   # a Highway route is not an expedition: leave it be
        return
    at = _current_system() or ""
    if _park_route("pause"):
        _exp_say(f"Expedition paused{' at ' + at if at else ''}. Press Resume when you are ready to go on.")


def _offer_resume(rescue_over: bool = False) -> None:
    """Ask how to carry on with the parked route."""
    global _resume_win
    parked = _parked()
    if not parked:
        return
    if _resume_win is not None:
        try:
            _resume_win.destroy()
        except tk.TclError:
            pass
    window = _resume_win = tk.Toplevel(_app_frame)
    window.title("Carry On")
    _attach_popup(window, "resume")
    try:
        window.transient(_app_frame.winfo_toplevel())
    except tk.TclError:
        pass
    buttons = tk.Frame(window)
    buttons.pack(side=tk.BOTTOM, pady=(4, 10))             # first in the pack order: never squeezed out
    body = tk.Frame(window)
    body.pack(fill=tk.BOTH, expand=True, padx=14, pady=(12, 0))
    what = "expedition" if parked.get("source") == "expedition" else "route"
    intro = (f"Your rescue cases are done. Would you like to resume your {what}?\n\n" if rescue_over else "") \
        + _parked_summary(parked) + ".\n\n"
    _autowrap(tk.Label(body, justify=tk.CENTER, anchor=tk.CENTER, wraplength=380, text=intro +
                       "Go Back: plot to where you left it, then carry on from there.\n"
                       "Next Waypoint: plot straight to the next waypoint, the most efficient way.")).pack(fill=tk.X)

    def choose(mode: str) -> None:
        window.destroy()
        _resume_plot(mode)

    ttk.Button(buttons, text="Go Back", width=14, command=lambda: choose("back")).pack(side=tk.LEFT, padx=4)
    ttk.Button(buttons, text="Next Waypoint", width=14, command=lambda: choose("next")).pack(side=tk.LEFT, padx=4)
    ttk.Button(buttons, text="Not Now", width=10, command=window.destroy).pack(side=tk.LEFT, padx=4)
    _fit_window(window)


def _resume_plot(mode: str) -> None:
    """mode "back": a leg to where you left the route, then the rest of it. mode "next": a leg to the next waypoint, then
    the rest (an expedition re-orders its remaining stops the most efficient way from where you are now)."""
    global _parked_busy
    parked = _parked()
    if not parked or _parked_busy:
        return
    origin = str(_snapshot.get("location", {}).get("system_name") or "")
    profile = _ship_profile()
    if not origin:
        _set_status("Waiting for the game to say where you are. Try again in a moment.")
        return
    if not profile["ok"]:
        _set_status("Ship data not found. Board your ship, then try again.")
        return
    if _route_systems and not _confirm_replace_route():
        return
    _parked_busy = True
    _set_status("Plotting your way back…" if mode == "back" else "Plotting to the next waypoint…")
    efficiency = int(_settings.get("plot_efficiency", 70))
    systems, index = list(parked["systems"]), int(parked.get("index") or 0)
    legs = list(parked.get("legs") or [])
    if len(legs) != len(systems):
        legs = [1] * len(systems)

    def later(function) -> None:
        try:
            _app_frame.after(0, function)
        except (tk.TclError, RuntimeError):
            pass

    def worker() -> None:
        try:
            if mode == "next" and parked.get("source") == "expedition" and parked.get("stops_left"):
                data = _exp()
                entered = data["order"] == "entered"
                stops = []
                for name in parked["stops_left"]:
                    picked = data["systems"].get(name.casefold())
                    stop = {"name": name, "system": picked} if picked else _resolve_stop(name)
                    stop["fixed"] = entered
                    stops.append(stop)
                route, _info = _plot_trip(origin, stops, False, bool(data["keep_last"] and not entered), profile["range"],
                                          efficiency, profile["multiplier"], lambda: False, lambda text: None)
                names, steps = [name for name, _ in route], [jumps for _, jumps in route]
            else:
                if mode == "back":
                    target = str(parked.get("at") or systems[index])
                    tail_from = index
                else:
                    tail_from = min(index + 1, len(systems) - 1)
                    target = systems[tail_from]
                    tail_from += 1
                if origin.casefold() == target.casefold():
                    leg = [(origin, 0)]
                else:
                    leg, _bridge = _plot_with_bridge(origin, target, profile["range"], efficiency, profile["multiplier"],
                                                     lambda: False)
                names, steps = [name for name, _ in leg], [jumps for _, jumps in leg]
                for name, jumps in zip(systems[tail_from:], legs[tail_from:]):
                    if name.casefold() != names[-1].casefold():
                        names.append(name)
                        steps.append(jumps)
            major = [s["system"] for s in stops] if mode == "next" and parked.get("source") == "expedition" \
                and parked.get("stops_left") else list(parked.get("major") or [])
            later(lambda: _resume_done(names, steps, parked, origin, major))
        except Exception as error:
            logger.exception("Resume plot failed")
            message = str(error) if isinstance(error, RuntimeError) else "Unexpected error - see the EDMC log."
            later(lambda: _resume_failed(message))
    threading.Thread(target=worker, daemon=True).start()


def _resume_failed(text: str) -> None:
    global _parked_busy
    _parked_busy = False
    _set_status("Plot Failed: " + text + " Your parked route is still saved.")


def _resume_done(names: list[str], steps: list[int], parked: dict[str, Any], origin: str,
                 major: list[str] | None = None) -> None:
    global _parked_busy
    _parked_busy = False
    kind = parked.get("kind") or "neutron"
    _save_plotted_csv(list(zip(names, steps)))
    _set_route(names, origin, kind=kind, bodies=parked.get("bodies"), legs=steps, source=str(parked.get("source") or ""),
               major=major)
    _settings["parked"] = {}
    _settings["tab"] = TABS[0]
    _save_settings()
    _refresh_expedition()
    _exp_say("")
    _refresh_route_label()
    _theme_event()
    _set_status(f"{'Expedition' if parked.get('source') == 'expedition' else 'Route'} resumed: {len(names)} waypoints.")


# ---------------------------------------------------------------------------
# Rescue tab (Jonathan, 1 Nov 2026), for Fuel Rats and Hull Seals: your open cases, a few at a time. A case is just a
# place (system, station or carrier): the game cannot search by commander name, so there is no client field. It looks like
# Highway (Now / Next / counts, clickable names) and is edited in one text window like Expedition. Plot Run puts the open
# cases in the shortest order (the Multi-Stop Trip engine), plots every leg and loads it as one route.
# ---------------------------------------------------------------------------
MAX_RESCUE_CASES = 30
_resc_ui: dict[str, Any] = {}
_resc_editor = None
_resc_win: dict[str, Any] = {}
_resc_busy = False


def _cases() -> list[dict[str, Any]]:
    saved = _settings.get("rescue")
    saved = saved if isinstance(saved, dict) else {}
    cases = []
    for item in saved.get("cases") or []:
        if isinstance(item, dict) and str(item.get("place") or "").strip():
            cases.append({"place": str(item["place"]).strip(), "system": str(item.get("system") or "").strip(),
                          "done": bool(item.get("done"))})
    return cases[:MAX_RESCUE_CASES]


def _cases_save(cases: list[dict[str, Any]], backup: list[dict[str, str]] | None = None) -> None:
    saved = _settings.get("rescue")
    kept = saved.get("backup") if isinstance(saved, dict) and isinstance(saved.get("backup"), list) else []
    _settings["rescue"] = {"cases": cases[:MAX_RESCUE_CASES], "backup": kept if backup is None else backup}
    _save_settings()
    _refresh_rescue()


def _rescue_snapshot() -> list[dict[str, str]]:
    """The list order as it is now, kept so Restore Order can bring it back after a recalculation."""
    return [{"place": c["place"], "system": c["system"]} for c in _cases()]


def _rescue_restore() -> bool:
    saved = _settings.get("rescue")
    backup = saved.get("backup") if isinstance(saved, dict) else None
    if not backup:
        return False
    pool, restored = _cases(), []
    for item in backup:
        for case in pool:
            if case["place"].casefold() == str(item.get("place", "")).casefold() \
                    and case["system"].casefold() == str(item.get("system", "")).casefold():
                restored.append(case)
                pool.remove(case)
                break
    _cases_save(restored + pool)          # cases added since then go at the end
    return True


def _case_system(case: dict[str, Any]) -> str:
    return case.get("system") or case["place"]


def _case_label(case: dict[str, Any]) -> str:
    """The place; a station or carrier also shows the system it is in, once that is known."""
    system = case.get("system")
    return f"{case['place']} ({system})" if system and system.casefold() != case["place"].casefold() else case["place"]


def _open_cases() -> list[dict[str, Any]]:
    return [case for case in _cases() if not case["done"]]


def _autowrap(label: tk.Label, margin: int = 0) -> tk.Label:
    """A window's text uses all the width the window has: it re-wraps whenever its container is resized, instead of
    sitting in a small box with empty space beside it."""
    def fit(event: Any) -> None:
        try:
            label.configure(wraplength=max(120, event.width - margin))
        except tk.TclError:
            pass
    label.master.bind("<Configure>", fit, add="+")
    return label


def _clear_waiting_notes() -> None:
    """The game has said where you are: an old "Waiting for the game…" note must not stay on screen."""
    for ui in (_exp_ui, _resc_ui):
        label = ui.get("status")
        if label is not None and _widget_alive(label):
            try:
                if str(label.cget("text")).startswith("Waiting for the game"):
                    label.configure(text="")
                    label.grid_remove()
            except tk.TclError:
                pass


def _resc_say(text: str) -> None:
    label = _resc_ui.get("status")
    if label is not None and _widget_alive(label):
        label.configure(text=text)
        label.grid() if text else label.grid_remove()


def _refresh_rescue() -> None:
    _render_cases()
    if not _resc_ui or not _widget_alive(_resc_ui.get("page")):
        return
    cases = _cases()
    open_cases = [c for c in cases if not c["done"]]
    _resc_ui["now"].configure(text=f"Now: {_case_label(open_cases[0])}" if open_cases else "No open cases.")
    _resc_ui["next"].configure(text=f"Next: {_case_label(open_cases[1])}" if len(open_cases) > 1 else "")
    _resc_ui["next_row"].grid() if len(open_cases) > 1 else _resc_ui["next_row"].grid_remove()
    finished = len(cases) - len(open_cases)
    _resc_ui["cases"].configure(text=f"Cases: {len(cases)}" + (f" ({finished} done)" if finished else ""))


def _build_rescue_page(page: tk.Frame) -> None:
    _resc_ui.clear()
    _resc_ui["page"] = page

    def line(row: int) -> tk.Frame:
        frame = tk.Frame(page)
        frame.grid(row=row, column=0, sticky=tk.W)
        return frame

    def piece(parent: tk.Frame, text: str = "", command=None) -> tk.Label:
        label = tk.Label(parent, text=text, anchor=tk.W, padx=0, bd=0)
        label.pack(side=tk.LEFT)
        if command is not None:
            label.configure(cursor="hand2", takefocus=True)
            _theme_controls.append(label)
            for sequence in ("<Button-1>", "<Return>", "<space>"):
                label.bind(sequence, lambda _event: command())
        return label

    def goto(index: int) -> None:
        open_cases = _open_cases()
        if index < len(open_cases):
            _waypoint_clicked(lambda: _case_system(open_cases[index]))

    _resc_ui["now"] = piece(line(0), "", lambda: goto(0))
    _resc_ui["next_row"] = row = line(1)
    _resc_ui["next"] = piece(row, "", lambda: goto(1))
    _resc_ui["cases"] = piece(line(2), "Cases", _open_cases_window)
    actions = line(3)
    piece(actions, "Case Done", _rescue_case_done)
    piece(actions, SEP)
    piece(actions, "Add Case", _open_rescue_editor)
    status = tk.Label(page, anchor=tk.W, justify=tk.LEFT, wraplength=320)
    status.grid(row=4, column=0, sticky=tk.W)
    status.grid_remove()
    _resc_ui["status"] = status
    _refresh_rescue()


def _rescue_case_done() -> None:
    """The case you are on is finished: it is crossed off where it stands and the next one becomes Now."""
    cases = _cases()
    for case in cases:
        if not case["done"]:
            case["done"] = True
            _cases_save(cases)
            _resc_say("")
            if _parked() and not _open_cases():
                _offer_resume(rescue_over=True)             # the last case: ask how to carry on
            return
    _resc_say("No open cases.")


def _dim_colour(foreground: str, background: str) -> str:
    try:
        r1, g1, b1 = _app_frame.winfo_rgb(foreground)
        r2, g2, b2 = _app_frame.winfo_rgb(background)
        return "#%02x%02x%02x" % (((r1 + r2) // 2) >> 8, ((g1 + g2) // 2) >> 8, ((b1 + b2) // 2) >> 8)
    except (tk.TclError, AttributeError):
        return "#808080"


def _render_cases() -> None:
    """Draw the Cases window's list: finished cases stay in place, struck through or dimmed (a setting)."""
    window, text = _resc_win.get("window"), _resc_win.get("text")
    if window is None or not _widget_alive(window) or not _widget_alive(text):
        return
    normal, _highlight, background = _palette()
    cases = _cases()
    selected = _resc_win.get("selected")
    text.configure(state=tk.NORMAL, background=background, foreground=normal)
    text.delete("1.0", tk.END)
    for number, case in enumerate(cases, start=1):
        text.insert(tk.END, f"{'✓ ' if case['done'] else ''}{number}. {_case_label(case)}\n", ("done",) if case["done"] else ())
    text.tag_configure("done", foreground=_dim_colour(normal, background), overstrike=bool(_settings.get("rescue_strike", True)))
    text.tag_configure("pick", background=normal, foreground=background)
    if selected is not None and 0 <= selected < len(cases):
        text.tag_add("pick", f"{selected + 1}.0", f"{selected + 1}.end")
    text.configure(state=tk.DISABLED)


def _open_cases_window() -> None:
    """Rescue Cases: the whole list, finished ones crossed off. The buttons are never hidden (suite rule)."""
    if _resc_win.get("window") is not None and _widget_alive(_resc_win["window"]):
        _resc_win["window"].lift()
        _render_cases()
        return
    window = tk.Toplevel(_app_frame)
    window.title("Rescue Cases")
    _attach_popup(window, "rescue_list")
    try:
        window.transient(_app_frame.winfo_toplevel())
    except tk.TclError:
        pass
    _resc_win.clear()
    _resc_win.update(window=window, selected=None)
    bar = tk.Frame(window)
    bar.pack(side=tk.BOTTOM, pady=(4, 10))                 # first in the pack order: never squeezed out
    body = tk.Frame(window)
    body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(10, 0))
    _autowrap(tk.Label(body, text="Click a case to select it. Done / Reopen crosses it off, or brings it back.",
                       justify=tk.CENTER, anchor=tk.CENTER, wraplength=380)).pack(fill=tk.X)
    holder = tk.Frame(body)
    holder.pack(fill=tk.BOTH, expand=True, pady=6)
    text = tk.Text(holder, width=44, height=10, wrap="none", cursor="arrow", takefocus=False)
    scroll = ttk.Scrollbar(holder, orient=tk.VERTICAL, command=text.yview)
    text.configure(yscrollcommand=scroll.set, state=tk.DISABLED)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)
    text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    note = tk.Label(body, text="", anchor=tk.CENTER, justify=tk.CENTER, wraplength=380)
    note.pack(fill=tk.X)
    _autowrap(note)
    _resc_win["text"], _resc_win["note"] = text, note

    def select(event: Any) -> str:
        line = int(text.index(f"@{event.x},{event.y}").split(".")[0]) - 1
        _resc_win["selected"] = line if 0 <= line < len(_cases()) else None
        _render_cases()
        return "break"
    text.bind("<Button-1>", select)

    def say(message: str) -> None:
        note.configure(text=message)

    def toggle() -> None:
        cases, index = _cases(), _resc_win.get("selected")
        if index is None or index >= len(cases):
            say("Click a case first.")
            return
        cases[index]["done"] = not cases[index]["done"]
        _cases_save(cases)
        say("")

    def restore() -> None:
        say("Put back the order you had before the last recalculation." if _rescue_restore() else "Nothing to restore yet.")

    def clear_done() -> None:
        _cases_save([c for c in _cases() if not c["done"]])
        _resc_win["selected"] = None
        say("")

    commands = (("Add Case", _open_rescue_editor), ("Done / Reopen", toggle), ("Clear Done", clear_done),
                ("Restore Order", restore), ("Close", window.destroy))
    for number, (label, command) in enumerate(commands):
        ttk.Button(bar, text=label, width=15, command=command).grid(row=number // 3, column=number % 3, padx=3, pady=2)
    window.bind("<Escape>", lambda _event: window.destroy())
    _render_cases()
    _fit_window(window)
    root = _app_frame.winfo_toplevel()
    width, height = window.winfo_reqwidth(), window.winfo_reqheight()
    x = min(max(0, root.winfo_rootx() + 40), max(0, window.winfo_screenwidth() - width))
    y = min(max(0, root.winfo_rooty() + 40), max(0, window.winfo_screenheight() - height - 40))
    window.geometry(f"+{x}+{y}")


def _rescue_resolve() -> None:
    """In the background, give each new case its system (a station or carrier name becomes the system it is in)."""
    pending = [c for c in _cases() if not c["system"]]
    if not pending:
        return

    def worker() -> None:
        found = {c["place"].casefold(): _resolve_stop(c["place"])["system"] for c in pending}

        def apply() -> None:
            cases = _cases()
            for case in cases:
                case["system"] = case["system"] or found.get(case["place"].casefold(), "")
            _cases_save(cases)
        try:
            _app_frame.after(0, apply)
        except (tk.TclError, RuntimeError):
            pass
    threading.Thread(target=worker, daemon=True).start()


def _rescue_plot(mode: str = "efficient") -> None:
    """Plot Best / Plot Listed: the open cases plotted as one route, in the shortest order from where you are
    ("efficient"), or in the order they are listed ("listed"). The order before the change is kept for Restore Order."""
    global _resc_busy
    if _resc_busy:
        return
    open_cases = _open_cases()
    if not open_cases:
        _resc_say("No open cases. Use Edit to add some.")
        return
    origin = str(_snapshot.get("location", {}).get("system_name") or "")
    if not origin:
        _resc_say("Waiting for the game to say where you are. Try again in a moment.")
        return
    profile = _ship_profile()
    if not profile["ok"]:
        _resc_say("Ship data not found. Board your ship, then try again.")
        return
    if not _long_plot_notice(len(open_cases)) or not _rescue_make_room():
        return
    _resc_busy = True
    _cases_save(_cases(), backup=_rescue_snapshot())
    _refresh_rescue()
    _resc_say("Looking up your cases…")
    efficiency = int(_settings.get("plot_efficiency", 70))

    def later(function) -> None:
        try:
            _app_frame.after(0, function)
        except (tk.TclError, RuntimeError):
            pass

    def worker() -> None:
        try:
            items = []
            for case in open_cases:
                system = case["system"] or _resolve_stop(case["place"])["system"]
                items.append({"name": case["place"], "system": system, "fixed": False,
                              "pos": _any_coordinates(system), "case": dict(case, system=system)})
            ordered = (_order_stops(_any_coordinates(origin), items, False, False)[0] if mode == "efficient" else items)
            stops = [{"name": s["name"], "system": s["system"], "fixed": True} for s in ordered]
            route, info = _plot_trip(origin, stops, False, False, profile["range"], efficiency, profile["multiplier"],
                                     lambda: False, lambda text: later(lambda: _resc_say(text)))
            later(lambda: _rescue_done(route, info, origin, [s["case"] for s in ordered]))
        except Exception as error:
            logger.exception("Rescue plot failed")
            message = str(error) if isinstance(error, RuntimeError) else "Unexpected error - see the EDMC log."
            later(lambda: _rescue_failed(message))
    threading.Thread(target=worker, daemon=True).start()


def _rescue_failed(text: str) -> None:
    global _resc_busy
    _resc_busy = False
    parked = _parked()
    if parked and parked.get("reason") == "rescue" and not _route_systems:
        _unpark_restore()                       # the rescue did not plot: your route comes straight back
    _refresh_rescue()
    _resc_say("Plot Failed: " + text + "\nYour loaded route is unchanged.")


def _rescue_done(route: list[tuple[str, int]], info: dict[str, Any], origin: str, ordered: list[dict[str, Any]]) -> None:
    """The cases are now in plotted order (Now is the first stop); the route runs on Highway."""
    global _resc_busy
    _resc_busy = False
    _save_plotted_csv(route)
    _set_route([system for system, _ in route], origin, kind="trip", legs=[jumps for _, jumps in route],
               source="rescue", major=[case.get("system") or case["place"] for case in ordered])
    _cases_save(ordered + [c for c in _cases() if c["done"]])
    _settings["tab"] = TABS[0]
    _save_settings()
    _resc_say("")
    _refresh_route_label()
    _theme_event()
    order = " > ".join(case["place"] for case in ordered)
    _set_status(f"Rescue order: {order}. Restore Order in the Cases window undoes it." if order else
                str(info.get("note") or "Rescue run loaded.").split("\n")[0])


# ---------------------------------------------------------------------------
# Missions tab (Jonathan, 1 Nov 2026). The game's journal tells us about every mission as it happens: accepted (with where
# it goes, what it pays and when it expires), redirected, completed, failed, abandoned. They are kept in settings by mission
# id, so the tab shows your active missions grouped by the system they go to. Missions accepted before this plugin was
# running only arrive as a short list at game start (name and expiry): their details are looked up in the newest journal
# files on your own PC. Plot Missions Route plots one trip through every destination, the same engine Rescue uses.
# ---------------------------------------------------------------------------
MISSION_JOURNALS = 150          # newest journal files searched for missions accepted before the plugin saw them
MISSION_EVENTS = {"MissionAccepted", "MissionCompleted", "MissionFailed", "MissionAbandoned", "MissionRedirected", "Missions"}
_miss_ui: dict[str, Any] = {}
_miss_win: dict[str, Any] = {}
_miss_busy = False


def _missions() -> dict[str, dict[str, Any]]:
    saved = _settings.get("missions")
    return saved if isinstance(saved, dict) else {}


def _miss_save(data: dict[str, dict[str, Any]]) -> None:
    _settings["missions"] = data
    _save_settings()


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _mission_title(name: str) -> str:
    """The game's own words when it gives them; else its code name made readable (Mission_Delivery_Boom_name)."""
    text = re.sub(r"_name$", "", str(name or "Mission"))
    text = re.sub(r"^Mission_", "", text).replace("_", " ").strip()
    return text or "Mission"


RETURN_RE = re.compile(r"Massacre|Assassinat|Mining|Collect|Salvage|OnFoot|Altruism", re.I)


def _mission_returns(mission: dict[str, Any]) -> bool:
    """Missions that are handed in where they were taken (checked against 102 completed missions in a real journal: kills,
    on-foot jobs and donations did; couriers, deliveries and passengers finished at their destination). Mining, collecting
    and salvage are included from how the game works."""
    return bool(RETURN_RE.search(str(mission.get("code") or "")))


def _mission_target(mission: dict[str, Any]) -> tuple[str, str]:
    """Where this mission needs you now: its destination, or (for a donation, which has none) where it was taken."""
    if mission.get("system"):
        return str(mission["system"]), str(mission.get("station") or "")
    if _mission_returns(mission) and mission.get("from_system"):
        return str(mission["from_system"]), str(mission.get("from_station") or "")
    return "", ""


def _mission_from_accepted(entry: dict[str, Any], origin: tuple[str, str] | None = None) -> dict[str, Any]:
    detail, count = "", 0
    if entry.get("Commodity_Localised") or entry.get("Commodity"):
        detail, count = str(entry.get("Commodity_Localised") or entry.get("Commodity")), _to_int(entry.get("Count"))
    elif entry.get("PassengerCount"):
        detail, count = str(entry.get("PassengerType") or "Passengers"), _to_int(entry.get("PassengerCount"))
    elif entry.get("KillCount"):
        detail, count = str(entry.get("TargetType_Localised") or entry.get("TargetType") or "Targets"), _to_int(entry.get("KillCount"))
    return {"name": str(entry.get("LocalisedName") or _mission_title(entry.get("Name"))),
            "faction": str(entry.get("Faction") or ""),
            "system": str(entry.get("DestinationSystem") or ""), "station": str(entry.get("DestinationStation") or ""),
            "expiry": _event_time({"timestamp": entry["Expiry"]}) if entry.get("Expiry") else None,
            "reward": _to_int(entry.get("Reward")), "detail": detail, "count": count, "wing": bool(entry.get("Wing")),
            "code": str(entry.get("Name") or ""), "from_system": (origin or ("", ""))[0], "from_station": (origin or ("", ""))[1]}


def _note_missions(entry: dict[str, Any]) -> None:
    """Called for every journal event: keep the list of active missions up to date."""
    event = entry.get("event")
    if event not in MISSION_EVENTS:
        return
    data = {key: dict(value) for key, value in _missions().items()}
    mission_id = str(entry.get("MissionID", ""))
    if event == "MissionAccepted" and mission_id:
        here = _snapshot.get("location", {})
        data[mission_id] = _mission_from_accepted(entry, (str(here.get("system_name") or ""), str(here.get("station_name") or "")))
    elif event in ("MissionCompleted", "MissionFailed", "MissionAbandoned"):
        data.pop(mission_id, None)
    elif event == "MissionRedirected" and mission_id in data:
        data[mission_id]["system"] = str(entry.get("NewDestinationSystem") or data[mission_id]["system"])
        data[mission_id]["station"] = str(entry.get("NewDestinationStation") or "")
        data[mission_id]["handin"] = True
        place = data[mission_id]["station"] or data[mission_id]["system"]
        _set_status(f"Mission objective done: hand in at {place} in {data[mission_id]['system']}.")
    elif event == "Missions":
        active = {str(m["MissionID"]): m for m in entry.get("Active") or [] if isinstance(m, dict) and "MissionID" in m}
        for key in [key for key in data if key not in active]:
            del data[key]                                  # no longer active (finished while the plugin was not looking)
        start = _event_time(entry) or time.time()
        for key, item in active.items():
            if key not in data:
                expires = item.get("Expires")
                data[key] = {"name": _mission_title(item.get("Name")), "code": str(item.get("Name") or ""), "faction": "",
                             "system": "", "station": "", "from_system": "", "from_station": "",
                             "expiry": start + float(expires) if expires else None, "reward": 0, "detail": "",
                             "count": 0, "wing": False, "stub": True}
    else:
        return
    if data != _missions():
        _miss_save(data)
    if any(mission.get("stub") for mission in data.values()):
        _miss_backfill()
    _refresh_missions()


def _miss_backfill(announce: bool = False) -> None:
    """Missions we only know by name: find their MissionAccepted (and any redirect) in the newest journal files."""
    global _miss_busy
    wanted = {key for key, mission in _missions().items() if mission.get("stub")}
    folder = _journal_dir()
    if _miss_busy or not wanted or not folder:
        if announce:
            _miss_say("Every mission's details are known." if not wanted else "The journal folder was not found.")
        return
    _miss_busy = True
    if announce:
        _miss_say("Looking in your journals…")

    def worker() -> None:
        found: dict[str, tuple[dict[str, Any], tuple[str, str]]] = {}
        moved: dict[str, dict[str, Any]] = {}
        try:
            files = sorted((n for n in os.listdir(folder) if n.startswith("Journal") and n.endswith(".log")),
                           reverse=True)[:MISSION_JOURNALS]
        except OSError:
            files = []
        for name in files:
            if len(found) == len(wanted):
                break
            events: list[tuple[dict[str, Any], tuple[str, str]]] = []
            here = ("", "")                                # where you were: a journal starts with a Location event
            try:
                with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as stream:
                    for line in stream:
                        if not any(word in line for word in ('"MissionAccepted"', '"MissionRedirected"', '"Docked"',
                                                             '"Location"', '"Undocked"', '"FSDJump"')):
                            continue
                        try:
                            record = json.loads(line)
                        except ValueError:
                            continue
                        event = record.get("event")
                        if event in ("MissionAccepted", "MissionRedirected"):
                            events.append((record, here))
                        elif event == "Docked":
                            here = (str(record.get("StarSystem") or ""), str(record.get("StationName") or ""))
                        elif event == "Location":
                            here = (str(record.get("StarSystem") or ""),
                                    str(record.get("StationName") or "") if record.get("Docked") else "")
                        elif event in ("Undocked", "FSDJump"):
                            here = (str(record.get("StarSystem") or here[0]), "")
            except OSError:
                continue
            for record, origin in reversed(events):        # newest first: the first redirect seen is the latest one
                key = str(record.get("MissionID", ""))
                if key not in wanted or key in found:
                    continue
                if record.get("event") == "MissionRedirected":
                    moved.setdefault(key, record)
                else:
                    found[key] = (record, origin)

        def apply() -> None:
            global _miss_busy
            _miss_busy = False
            data = {key: dict(value) for key, value in _missions().items()}
            for key, (record, origin) in found.items():
                if key in data:
                    kept = data[key].get("expiry")
                    data[key] = _mission_from_accepted(record, origin)
                    data[key]["expiry"] = data[key]["expiry"] or kept
                    if key in moved:
                        data[key]["system"] = str(moved[key].get("NewDestinationSystem") or data[key]["system"])
                        data[key]["station"] = str(moved[key].get("NewDestinationStation") or "")
                        data[key]["handin"] = True
            for key in wanted:
                if key in data and key not in found:
                    data[key]["stub"] = False              # looked for and not found: do not search again every start
            _miss_save(data)
            _refresh_missions()
            if announce:
                _miss_say(f"Found details for {len(found)} of {len(wanted)} mission{'s' if len(wanted) != 1 else ''}.")
        try:
            _app_frame.after(0, apply)
        except (tk.TclError, RuntimeError):
            pass
    threading.Thread(target=worker, daemon=True).start()


def _left_text(expiry: Any) -> str:
    if not expiry:
        return "no time limit"
    seconds = float(expiry) - time.time()
    return "expired" if seconds <= 0 else _span_text(seconds)


def _money_text(credits: int) -> str:
    if credits >= 1_000_000:
        return f"{credits / 1_000_000:.1f}M Cr"
    return f"{credits:,} Cr" if credits < 10_000 else f"{credits / 1000:.0f}K Cr"


def _mission_groups() -> list[tuple[str, list[dict[str, Any]]]]:
    """Active missions by destination system, the one expiring soonest first. Missions with no known system go last."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for mission in _missions().values():
        groups.setdefault(_mission_target(mission)[0], []).append(mission)
    for items in groups.values():
        items.sort(key=lambda m: m.get("expiry") or 1e18)
    known = sorted((item for item in groups.items() if item[0]), key=lambda item: item[1][0].get("expiry") or 1e18)
    return known + ([("", groups[""])] if "" in groups else [])


def _mission_stops() -> list[str]:
    """The systems worth a visit: every destination that is known and not expired."""
    now = time.time()
    return [system for system, items in _mission_groups()
            if system and any(not m.get("expiry") or m["expiry"] > now for m in items)]


def _miss_say(text: str) -> None:
    label = _miss_ui.get("status")
    if label is not None and _widget_alive(label):
        label.configure(text=text)
        label.grid() if text else label.grid_remove()


def _refresh_missions() -> None:
    _render_missions()
    if not _miss_ui or not _widget_alive(_miss_ui.get("page")):
        return
    data = _missions()
    groups = [group for group in _mission_groups() if group[0]]
    if not data:
        _miss_ui["hint"].configure(text="No Active Missions")
        _miss_ui["hint"].grid()
        _miss_ui["data"].grid_remove()
        return
    _miss_ui["hint"].grid_remove()
    _miss_ui["data"].grid()
    _miss_ui["count"].configure(text=f"Missions: {len(data)}")
    _miss_ui["systems"].configure(text=f"{SEP}Systems: {len(groups)}")
    soonest = min((m["expiry"] for m in data.values() if m.get("expiry")), default=None)
    _miss_ui["soon"].configure(text=f"Expires First: {_left_text(soonest)}" if soonest else "")
    reward = sum(_to_int(m.get("reward")) for m in data.values())
    _miss_ui["reward"].configure(text=f"Rewards: {_money_text(reward)}" if reward else "")
    following = ""
    if _settings.get("route_source") == "missions" and _route_systems:
        points = _expedition_points()
        passed = sum(1 for index, _ in points if index <= max(0, _route_index))
        following = points[passed][1] if passed < len(points) else ""
    _miss_ui["next_name"] = following
    _miss_ui["next"].configure(text=f"Next stop: {following}" if following else "")
    for key, shown in (("soon", bool(soonest)), ("reward", bool(reward)), ("next", bool(following))):
        _miss_ui[key].master.pack_forget()              # re-packed in order, so the lines never swap places
    for key, shown in (("soon", bool(soonest)), ("reward", bool(reward)), ("next", bool(following))):
        if shown:
            _miss_ui[key].master.pack(anchor=tk.W)


def _missions_menu_items() -> list[tuple[str, Any, bool] | None]:
    data = _missions()
    return [("Plot Missions Route", _missions_plot, bool(_mission_stops()) and not _miss_busy),
            ("Show Missions…", _open_missions_window, bool(data)),
            ("Look Up Missing Details", lambda: _miss_backfill(True), any(m.get("stub") for m in data.values())),
            None,
            ("Forget All Missions…", _missions_forget, bool(data))]


def _missions_forget() -> None:
    if _missions() and messagebox.askyesno("Forget All Missions", "Clear the list of missions? It fills again as the game "
                                           "reports them (at the next game start, or as you accept new ones).", parent=_app_frame):
        _miss_save({})
        _refresh_missions()


def _build_missions_page(page: tk.Frame) -> None:
    """Data only, like Expedition: what you have, where it goes, what runs out first. The actions are in the Navigation menu."""
    _miss_ui.clear()
    _miss_ui.update(page=page, next_name="")

    def piece(parent: tk.Frame, text: str = "", command=None) -> tk.Label:
        label = tk.Label(parent, text=text, anchor=tk.W, padx=0, bd=0)
        label.pack(side=tk.LEFT)
        if command is not None:
            label.configure(cursor="hand2", takefocus=True)
            _theme_controls.append(label)
            for sequence in ("<Button-1>", "<Return>", "<space>"):
                label.bind(sequence, lambda _event: command())
        return label

    page.columnconfigure(0, weight=1)
    hint = tk.Label(page, anchor=tk.CENTER, justify=tk.CENTER, wraplength=320)      # a short notice: centred, as few words as possible
    hint.grid(row=0, column=0, sticky=tk.EW)
    _miss_ui["hint"] = hint
    data = tk.Frame(page)
    data.grid(row=1, column=0, sticky=tk.W)
    _miss_ui["data"] = data

    def row() -> tk.Frame:
        frame = tk.Frame(data)
        frame.pack(anchor=tk.W)
        return frame

    top = row()
    _miss_ui["count"] = piece(top, "", _open_missions_window)
    _miss_ui["systems"] = piece(top)
    _miss_ui["soon"] = piece(row())
    _miss_ui["reward"] = piece(row())
    _miss_ui["next"] = piece(row(), "", lambda: _miss_ui.get("next_name") and _copy_system(_miss_ui["next_name"]))
    status = tk.Label(page, anchor=tk.W, justify=tk.LEFT, wraplength=320)
    status.grid(row=2, column=0, sticky=tk.W)
    status.grid_remove()
    _miss_ui["status"] = status
    _refresh_missions()


def _render_missions() -> None:
    """Draw the Missions window: each destination system with what is waiting there. A system's name copies when clicked."""
    window, text = _miss_win.get("window"), _miss_win.get("text")
    if window is None or not _widget_alive(window) or not _widget_alive(text):
        return
    normal, highlight, background = _palette()
    text.configure(state=tk.NORMAL, background=background, foreground=normal)
    text.delete("1.0", tk.END)
    for tag in text.tag_names():
        if tag.startswith("sys"):
            text.tag_delete(tag)
    groups = _mission_groups()
    if not groups:
        text.insert(tk.END, "No active missions.")
    for number, (system, items) in enumerate(groups):
        title = system or "Destination not known yet"
        tag = f"sys{number}"
        text.insert(tk.END, f"{title}", (tag,) if system else ())
        text.insert(tk.END, f"  ({len(items)} mission{'s' if len(items) != 1 else ''})\n")
        if system:
            text.tag_configure(tag, foreground=highlight, underline=True)
            text.tag_bind(tag, "<Button-1>", lambda _event, name=system: _waypoint_clicked(lambda: name))
            text.tag_bind(tag, "<Enter>", lambda _event: text.configure(cursor="hand2"))
            text.tag_bind(tag, "<Leave>", lambda _event: text.configure(cursor="arrow"))
        for mission in items:
            what = f" - {mission['count']} x {mission['detail']}" if mission.get("detail") and mission.get("count") else \
                   (f" - {mission['detail']}" if mission.get("detail") else "")
            station = _mission_target(mission)[1]
            where = (("hand in at " if mission.get("handin") else "") + f"{station}, ") if station else ""
            extra = " · ".join(part for part in (_left_text(mission.get("expiry")),
                                                 _money_text(_to_int(mission.get("reward"))) if mission.get("reward") else "",
                                                 "wing" if mission.get("wing") else "") if part)
            text.insert(tk.END, f"   {mission['name']}{what}\n      {where}{extra}\n")
            if mission.get("system") and not mission.get("handin") and _mission_returns(mission) and mission.get("from_system"):
                back = ", ".join(part for part in (mission.get("from_station"), mission["from_system"]) if part)
                text.insert(tk.END, f"      then hand in at {back}\n")           # taken there, and handed in there
        text.insert(tk.END, "\n")
    text.configure(state=tk.DISABLED)


def _open_missions_window() -> None:
    """Active missions by destination. The buttons are never hidden (suite rule)."""
    if _miss_win.get("window") is not None and _widget_alive(_miss_win["window"]):
        _miss_win["window"].lift()
        _render_missions()
        return
    window = tk.Toplevel(_app_frame)
    window.title("Active Missions")
    _attach_popup(window, "missions_list")
    try:
        window.transient(_app_frame.winfo_toplevel())
    except tk.TclError:
        pass
    _miss_win.clear()
    _miss_win["window"] = window
    bar = tk.Frame(window)
    bar.pack(side=tk.BOTTOM, pady=(4, 10))                 # first in the pack order: never squeezed out
    body = tk.Frame(window)
    body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(10, 0))
    _autowrap(tk.Label(body, text="Click a system to copy it. Missions that go to the same system are together.",
                       justify=tk.CENTER, anchor=tk.CENTER, wraplength=380)).pack(fill=tk.X)
    holder = tk.Frame(body)
    holder.pack(fill=tk.BOTH, expand=True, pady=6)
    text = tk.Text(holder, width=52, height=16, wrap="word", cursor="arrow", takefocus=False)
    scroll = ttk.Scrollbar(holder, orient=tk.VERTICAL, command=text.yview)
    text.configure(yscrollcommand=scroll.set, state=tk.DISABLED)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)
    text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    _miss_win["text"] = text
    commands = (("Plot Route", lambda: (window.destroy(), _missions_plot())),
                ("Look Up Details", lambda: _miss_backfill(True)), ("Close", window.destroy))
    for number, (label, command) in enumerate(commands):
        ttk.Button(bar, text=label, width=15, command=command).grid(row=0, column=number, padx=3, pady=2)
    window.bind("<Escape>", lambda _event: window.destroy())
    _render_missions()
    _fit_window(window)
    root = _app_frame.winfo_toplevel()
    width, height = window.winfo_reqwidth(), window.winfo_reqheight()
    x = min(max(0, root.winfo_rootx() + 40), max(0, window.winfo_screenwidth() - width))
    y = min(max(0, root.winfo_rooty() + 40), max(0, window.winfo_screenheight() - height - 40))
    window.geometry(f"+{x}+{y}")


def _missions_plot() -> None:
    """Plot Missions Route: every destination you still have time for, in the shortest order from where you are."""
    global _miss_busy
    if _miss_busy:
        return
    stops = _mission_stops()
    if not stops:
        _miss_say("No mission has a known destination yet. Look Up Missing Details may find them." if _missions()
                  else "No active missions.")
        return
    origin = str(_snapshot.get("location", {}).get("system_name") or "")
    if not origin:
        _miss_say("Waiting for the game to say where you are. Try again in a moment.")
        return
    profile = _ship_profile()
    if not profile["ok"]:
        _miss_say("Ship data not found. Board your ship, then try again.")
        return
    if not _long_plot_notice(len(stops)) or (_route_systems and not _confirm_replace_route()):
        return
    _miss_busy = True
    _miss_say("Looking up your missions…")
    efficiency = int(_settings.get("plot_efficiency", 70))

    def later(function) -> None:
        try:
            _app_frame.after(0, function)
        except (tk.TclError, RuntimeError):
            pass

    def worker() -> None:
        try:
            items = [{"name": system, "system": system, "fixed": False, "pos": _any_coordinates(system)} for system in stops]
            ordered = _order_stops(_any_coordinates(origin), items, False, False)[0]
            chosen = [{"name": item["name"], "system": item["system"], "fixed": True} for item in ordered]
            route, info = _plot_trip(origin, chosen, False, False, profile["range"], efficiency, profile["multiplier"],
                                     lambda: False, lambda note: later(lambda: _miss_say(note)))
            later(lambda: _missions_done(route, info, origin, [item["system"] for item in ordered]))
        except Exception as error:
            logger.exception("Missions plot failed")
            message = str(error) if isinstance(error, RuntimeError) else "Unexpected error - see the EDMC log."
            later(lambda: _missions_failed(message))
    threading.Thread(target=worker, daemon=True).start()


def _missions_failed(text: str) -> None:
    global _miss_busy
    _miss_busy = False
    _miss_say("Plot Failed: " + text + "\nYour loaded route is unchanged.")


def _missions_done(route: list[tuple[str, int]], info: dict[str, Any], origin: str, ordered: list[str]) -> None:
    """The route runs on Highway, with your mission systems marked * in its lists."""
    global _miss_busy
    _miss_busy = False
    _save_plotted_csv(route)
    _set_route([system for system, _ in route], origin, kind="trip", legs=[jumps for _, jumps in route],
               source="missions", major=ordered)
    _settings["tab"] = TABS[0]
    _save_settings()
    _miss_say("")
    _refresh_route_label()
    _theme_event()
    _set_status("Missions order: " + " > ".join(ordered))


def _show_completed() -> None:
    done = _completed_systems()
    _show_systems_popup(f"Jumps Done ({len(done)})", done, "No jumps done yet.", _major_names(), _class_tags(done))


def _show_waypoints_left() -> None:
    """The blue count after Left: only the waypoints (neutron stars, stops...) still ahead, not every jump."""
    if not _route_systems or not _waypoints_left_text():
        return
    ahead = _neutrons_ahead() if _route_kind in NEUTRON_KINDS else _route_systems[max(0, _route_index) + 1:]
    word = _waypoint_word()
    _show_systems_popup(f"{word}s Left ({len(ahead)})", ahead, f"No {word.lower()}s left - you have arrived.",
                        _major_names(), _class_tags(ahead))


def _show_remaining() -> None:
    left = _remaining_systems()
    _show_systems_popup(f"Jumps Left ({len(left)})", left, "No jumps left - you have arrived.", _major_names(),
                        _class_tags(left), _fuel_summary(left) if left else "")


def _apply_header_spacing() -> None:
    """Re-measure the header spacing once EDMC has applied its theme font (no underline)."""
    _update_header_spacing()


def plugin_app(parent):
    """Build the panel. If anything goes wrong, show a one-line notice instead of
    letting EDMC drop the panel silently (the 0.14.0 "missing panel" symptom)."""
    try:
        return _build_panel(parent)
    except Exception:
        logger.exception("%s could not build its panel", TITLE)
    global _app_frame
    global _title_label, _cog_button, _collapse_button, _header_frame, _status_label, _mode_button, _compass
    global _current_label, _next_label, _end_label, _done_label, _left_label
    try:
        if _app_frame is not None:
            _app_frame.destroy()
    except tk.TclError:
        pass
    _title_label = _cog_button = _collapse_button = _header_frame = _mode_button = _compass = None
    _status_label = None
    global _shortcut_bar, _shortcut_state, _shortcut_toggle_button
    _shortcut_bar = _shortcut_state = _shortcut_toggle_button = None
    _shortcut_buttons.clear()
    global _position_frame, _position_label, _lamp
    _position_frame = _position_label = _lamp = None
    _current_label = _next_label = _end_label = _done_label = _left_label = None
    _route_rows.clear()
    _theme_controls.clear()
    _app_frame = tk.Frame(parent)
    tk.Label(_app_frame, text=f"{TITLE} {VERSION}: panel failed to start.\nSee the EDMC debug log.",
             justify=tk.CENTER).grid(row=0, column=0)
    _app_frame.columnconfigure(0, weight=1)
    return _app_frame


def _build_panel(parent: tk.Frame) -> tk.Frame:
    global _app_frame, _current_label, _next_label, _end_label, _done_label, _left_label
    global _status_label, _auto_var, _cog_button, _title_label, _mode_button, _compass
    _app_frame = tk.Frame(parent)
    _route_rows.clear()
    global _header_frame, _page, _tab_row
    header = _header_frame = tk.Frame(_app_frame)
    # Centre the header like other EDMC plugins: the column spans the panel width,
    # the header sits in the middle; the lines below stay left-aligned.
    _app_frame.columnconfigure(0, weight=1)
    header.grid(row=0, column=0)

    def toggle_collapsed() -> None:
        _settings["collapsed"] = not _settings.get("collapsed")
        _save_settings()
        _refresh_route_label()
    # The header itself is the settings menu (Highlighted, since it is clickable); the cog box beside it is
    # optional (an (N) Interface setting) for people who would not know to click the name.
    _title_label = tk.Label(header, text=HEADER, anchor=tk.W, cursor="hand2", takefocus=True)
    _title_label.pack(side=tk.LEFT)
    for sequence in ("<Button-1>", "<Return>", "<space>"):
        _title_label.bind(sequence, lambda _event: _title_clicked())
    # The cog box (optional) lives in the right-hand button stack, laid out by _sync_header_buttons.
    _cog_button = tk.Button(_app_frame, text="\u2699", command=_show_settings_menu)
    global _collapse_button
    # Stock EDMC button with the same 🔼/🔽 text as BioScan and Pioneer, so EDMC's theme
    # (and any plugin that restyles those buttons) treats it the same way.
    _collapse_button = tk.Button(_app_frame, text="🔼", command=toggle_collapsed)
    _collapse_button.grid(row=0, column=0, sticky=tk.NE)  # same row as the title, pinned right
    global _shortcut_toggle_button
    _shortcut_toggle_button = tk.Button(_app_frame, text="S", command=_toggle_shortcuts, takefocus=False)
    # The shared copy/auto toggle from (N) Interface, just left of the collapse button; it shows only
    # while Interface's galaxy-map setting is on and there is a route.
    _mode_button = _interface("navigator_mode_button", _app_frame, FOLDER, _collapse_button, True,
                              {"row": 0, "column": 0, "sticky": tk.NE}, _shortcut_toggle_room)
    _auto_var = tk.BooleanVar(value=bool(_settings.get("auto_route")))
    # Auto-Route: an R box in the header (it used to be a line at the bottom), left of the copy/auto A.
    _compass = _RouteButton(_app_frame, _auto_var, _save_settings)
    _update_header_spacing()
    # Space the header after EDMC applies its theme font.
    # Tab row (like Cartography's): each tab is its own page; Neutron Highway is the first.
    global _shortcut_bar, _shortcut_state
    _shortcut_state = None
    _shortcut_bar = tk.Frame(_app_frame)               # between the header and the tabs; _sync_shortcuts shows it
    _shortcut_buttons.clear()
    for _slot in range(SHORTCUT_SLOTS):
        _shortcut_buttons.append(tk.Button(_shortcut_bar, text="", takefocus=False))
    _tab_row = tk.Frame(_app_frame)
    _tab_row.grid(row=2, column=0)
    _tab_widgets.clear()
    for column, name in enumerate(TABS):
        cell = tk.Frame(_tab_row)
        cell.grid(row=0, column=column, padx=4)
        label = tk.Label(cell, text=_tab_label(name), cursor="hand2", takefocus=True)
        label.pack()
        line = tk.Canvas(cell, height=2, width=1, highlightthickness=0, borderwidth=0)
        line.pack(fill=tk.X)
        for sequence in ("<Button-1>", "<Return>", "<space>"):
            label.bind(sequence, lambda _event, tab=name: _select_tab(tab))
        _tab_widgets[name] = (label, line)
    _tab_pages.clear()
    for name in TABS:
        frame = tk.Frame(_app_frame)
        frame.grid(row=3, column=0, sticky=tk.EW)         # full width, so the Jumps line can centre
        frame.columnconfigure(0, weight=1)
        if name == "Expedition":
            _build_expedition_page(frame)
        elif name == "Rescue":
            _build_rescue_page(frame)
        elif name == "Missions":
            _build_missions_page(frame)
        elif name != TABS[0]:
            tk.Label(frame, text="Coming soon.", anchor=tk.W).pack(anchor=tk.W)
        _tab_pages[name] = frame
    _page = _tab_pages[TABS[0]]

    def waypoint_row(row: int, getter) -> tk.Label:
        # The whole line is the clickable name (Highlighted Text, like the other suite panels).
        frame = tk.Frame(_page)
        frame.grid(row=row, column=0, sticky=tk.W)
        label = tk.Label(frame, anchor=tk.W, cursor="hand2", takefocus=True)
        label.pack(side=tk.LEFT)
        _theme_controls.append(label)
        for sequence in ("<Button-1>", "<Return>", "<space>"):
            label.bind(sequence, lambda _event, g=getter: _waypoint_clicked(g))
        _route_rows.append(frame)
        return label

    global _jump_label
    _current_label = waypoint_row(2, _current_system)
    _jump_label = waypoint_row(3, _next_jump_system)
    _next_label = waypoint_row(4, _next_neutron_system)
    _end_label = waypoint_row(5, _end_system)
    _build_scan_label(7)                # Road to Riches: bodies to scan
    block = tk.Frame(_page)        # Jumps line + progress bar, centred under the header
    block.grid(row=1, column=0)                       # centred under the tabs, like the header
    _route_rows.append(block)
    progress = tk.Frame(block)
    progress.pack()
    _build_route_bar(block, progress)

    def piece(text: str = "", command=None) -> tk.Label:
        label = tk.Label(progress, text=text, anchor=tk.W, padx=0, bd=0)
        label.pack(side=tk.LEFT)
        if command is not None:
            label.configure(cursor="hand2",takefocus=True)
            _theme_controls.append(label)
            for sequence in ("<Button-1>","<Return>","<space>"):
                label.bind(sequence, lambda _event: command())
        return label

    piece("Jumps ")
    piece("Done", _show_completed)        # same length as "Left", so the line stays short
    _done_label = piece()
    piece("Left", _show_remaining)
    _left_label = piece()
    global _left_extra
    _left_extra = piece("", _show_waypoints_left)       # " (4 Neutrons)" in the info colour: tap it for just those
    _build_position(progress)
    global _parked_label
    _parked_label = tk.Label(_page, anchor=tk.W, cursor="hand2", takefocus=True)
    _parked_label.grid(row=6, column=0)
    _theme_controls.append(_parked_label)
    for sequence in ("<Button-1>", "<Return>", "<space>"):
        _parked_label.bind(sequence, lambda _event: _offer_resume())
    _status_label = tk.Label(_page, anchor=tk.W, justify=tk.LEFT, wraplength=320)
    _status_label.grid(row=8, column=0, sticky=tk.W)
    _status_label.grid_remove()
    top = _app_frame.winfo_toplevel()
    for sequence in ("<<ThemeChanged>>","<<NavigatorThemeChanged>>"):
        _theme_bindings.append((top,sequence,top.bind(sequence,_theme_event,add="+")))
    _app_frame.bind("<Map>",_theme_event,add="+")
    _app_frame.bind("<Configure>", _width_event, add="+")      # the panel can be resized: refit the tab row
    _theme_event()
    _refresh_route_label()
    return _app_frame


def journal_entry(
    cmdr: str,
    is_beta: bool,
    system: str | None,
    station: str | None,
    entry: dict[str, Any],
    state: dict[str, Any],
) -> None:
    """Capture location and ship context as journal events arrive."""
    global _last_loadout
    if entry.get("event") == "Loadout":
        _last_loadout = dict(entry)
    _note_plotted_route(entry, state)
    _note_star_pos(system, entry, state)
    _note_fuel(entry)
    _note_materials(state)
    location = _copy_present(
        state,
        (
            "SystemName",
            "SystemAddress",
            "SystemPopulation",
            "StarPos",
            "Body",
            "BodyID",
            "BodyType",
            "StationName",
            "StationType",
            "IsDocked",
            "OnFoot",
        ),
    )
    if system:
        location["SystemName"] = system
    if station:
        location["StationName"] = station

    # The event is reduced to fields useful for interpreting the latest update.
    event_summary = _copy_present(entry, ("event", "timestamp", "StarSystem", "BodyName", "Docked"))
    _snapshot["location"] = {
        "system_name": location.get("SystemName"),
        "system_address": location.get("SystemAddress"),
        "system_population": location.get("SystemPopulation"),
        "star_coordinates": location.get("StarPos"),
        "body_name": location.get("Body"),
        "body_id": location.get("BodyID"),
        "body_type": location.get("BodyType"),
        "station_name": location.get("StationName"),
        "station_type": location.get("StationType"),
        "docked": location.get("IsDocked", location.get("Docked")),
        "on_foot": location.get("OnFoot"),
    }
    _snapshot["ship"] = _copy_present(state, ("ShipType", "ShipName", "ShipIdent"))
    _snapshot["last_journal_event"] = event_summary
    _snapshot["game"] = {"is_beta": bool(is_beta)}
    _update_route_progress(location.get("SystemName"), on_jump=entry.get("event") == "FSDJump")
    _note_missions(entry)
    _note_expedition_travel(entry)
    _note_star_class(entry)
    if location.get("SystemName"):
        _clear_waiting_notes()
    _refresh_route_label()
    # JetConeBoost is written when the FSD finishes supercharging, so the map's
    # range check now sees the boosted jump range. Only fire from the cockpit.
    if entry.get("event") == "JetConeBoost" and _settings.get("auto_route"):
        if _gui_focus() == 0:
            logger.info("Supercharge detected (BoostValue=%s); plotting next waypoint", entry.get("BoostValue"))
            _start_plot(initial_delay=float(_settings.get("supercharge_delay", 5.0)))
    _save(changed_only=True, refresh=False)   # refreshed above


def dashboard_entry(cmdr: str, is_beta: bool, entry: dict[str, Any]) -> None:
    """Capture a small allowlisted cockpit-status sample as it changes."""
    _snapshot["cockpit"] = _copy_present(
        entry,
        (
            "Flags",
            "Flags2",
            "Pips",
            "FireGroup",
            "GuiFocus",
            "Latitude",
            "Longitude",
            "Altitude",
            "Heading",
            "BodyName",
            "PlanetRadius",
        ),
    )
    _snapshot["game"] = {"is_beta": bool(is_beta)}
    _save(changed_only=True, refresh=False)   # Status.json ticks: write only on change


def plugin_stop() -> None:
    global _theme_pending
    if _theme_pending is not None and _app_frame is not None:
        try: _app_frame.after_cancel(_theme_pending)
        except tk.TclError: pass
    _theme_pending = None
    for top,sequence,binding in _theme_bindings:
        try: top.unbind(sequence,binding)
        except tk.TclError: pass
    _theme_bindings.clear()
    _theme_controls.clear()
