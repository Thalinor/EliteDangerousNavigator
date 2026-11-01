# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Ship Computer - journal reader for per-vessel stats (no GUI code; safe to run in a thread).

Per vessel: distance jumped, number of jumps, time spent and unique systems.
A separate commander-wide record holds logged on-foot time. A ship is identified by the game's
ShipID; a fleet carrier is its own vessel (identified by its MarketID) while you are docked
aboard it, and its jumps and the time spent aboard count to the carrier, not to your ship.
"""
from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable

RELEVANT = ("LoadGame", "Loadout", "ShipyardSwap", "ShipyardNew", "ShipyardBuy", "ShipyardSell", "SetUserShipName", "FSDJump", "CarrierJump",
            "Docked", "Undocked", "Location", "Music", "Shutdown", "Embark", "Disembark", "Died", "Resurrect")
_KEYS = tuple(f'"{name}"' for name in RELEVANT)
CACHE_VERSION = 3
FOOT_KEY = "commander:on_foot"
_TS = re.compile(r'"timestamp"\s*:\s*"([^"]{20})')


def parse_ts(value: Any) -> float | None:
    try:
        return datetime.strptime(str(value)[:20], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def _new_vessel(kind: str) -> dict[str, Any]:
    return {"kind": kind, "type": "", "name": "", "ly": 0.0, "jumps": 0, "seconds": 0.0, "systems": [], "aliases": []}


def system_key(entry: dict[str, Any]) -> str | None:
    """Names are stable across older journals that omit SystemAddress."""
    name = str(entry.get("StarSystem") or "").strip().casefold()
    return name or (f"address:{entry['SystemAddress']}" if entry.get("SystemAddress") is not None else None)


class Tracker:
    """Follows which vessel you are in and adds up distance, jumps and time per vessel."""

    def __init__(self, state: dict[str, Any] | None = None) -> None:
        state = state or {}
        self.ship = state.get("ship")          # {"id", "type", "name"}
        self.carrier = state.get("carrier")    # {"id", "name"} while docked aboard a carrier
        self.pos = state.get("pos")
        self.system = state.get("system")
        self.on_foot = bool(state.get("on_foot", False))
        self.taxi = bool(state.get("taxi", False))
        self._visited: dict[str, set[str]] = {}
        self.in_game = bool(state.get("in_game", False))
        self.seg_start: float | None = None
        self.vessels: dict[str, dict[str, Any]] = {}

    def state(self) -> dict[str, Any]:
        return {"ship": self.ship, "carrier": self.carrier, "pos": self.pos, "in_game": self.in_game,
                "system": self.system, "on_foot": self.on_foot, "taxi": self.taxi}

    def current_key(self) -> str | None:
        if self.carrier and self.carrier.get("id") is not None:
            return f"carrier:{self.carrier['id']}"
        if self.ship and self.ship.get("id") is not None:
            return f"ship:{self.ship['id']}"
        return None

    def _current(self) -> dict[str, Any] | None:
        key = self.current_key()
        if key is None:
            return None
        if key.startswith("carrier:"):
            vessel = self.vessels.setdefault(key, _new_vessel("carrier"))
            vessel["type"] = "fleetcarrier"
            vessel["name"] = self.carrier.get("name") or vessel["name"]
        else:
            vessel = self.vessels.setdefault(key, _new_vessel("ship"))
            vessel["type"] = self.ship.get("type") or vessel["type"]
            vessel["name"] = self.ship.get("name") or vessel["name"]
        alias = vessel.get("name")
        if alias and alias not in vessel.setdefault("aliases", []):
            vessel["aliases"].append(alias)
        return vessel

    def close(self, t: float | None) -> None:
        """Credit the time since the last change to the vessel you were in."""
        if t is None:
            return
        if self.seg_start is not None and self.in_game and t > self.seg_start:
            vessel = self._current() if not self.on_foot and not self.taxi else None
            if vessel is not None:
                vessel["seconds"] += t - self.seg_start
            if self.on_foot:
                foot = self.vessels.setdefault(FOOT_KEY, _new_vessel("commander"))
                foot["seconds"] += t - self.seg_start
        self.seg_start = t

    def _visit(self) -> None:
        if not self.in_game or self.on_foot or self.taxi or not self.system:
            return
        vessel = self._current()
        if vessel is not None:
            seen = self._visited.setdefault(self.current_key(), set())
            if self.system not in seen:
                seen.add(self.system)
                vessel["systems"].append(self.system)

    def feed(self, entry: dict[str, Any], t: float | None) -> None:
        event = entry.get("event")
        # A login starts a session; never bridge an unrecorded logout interval.
        if event == "LoadGame":
            self.in_game = False
        self.close(t)
        if event == "LoadGame":
            self.in_game = True
            self.carrier = None
            self.system = None
            kind = str(entry.get("Ship") or "").lower()
            self.on_foot = "suit" in kind or kind == "onfoot"
            self.taxi = False
            if not self.on_foot and entry.get("ShipID") is not None and entry.get("Ship"):
                self.ship = {"id": entry["ShipID"], "type": str(entry["Ship"]).lower(),
                             "name": str(entry.get("ShipName") or "")}
        elif event == "Location":
            self.in_game = True
            self.system = system_key(entry)
            self.on_foot = bool(entry.get("OnFoot", False))
            self.taxi = bool(entry.get("Taxi", False))
            if entry.get("StarPos"):
                self.pos = list(entry["StarPos"])
            if entry.get("Docked") and str(entry.get("StationType", "")).lower() == "fleetcarrier":
                self.carrier = {"id": entry.get("MarketID"), "name": str(entry.get("StationName") or "")}
            elif not entry.get("Docked"):
                self.carrier = None
        elif event == "Loadout":
            if entry.get("ShipID") is not None:
                self.ship = {"id": entry["ShipID"], "type": str(entry.get("Ship") or "").lower(),
                             "name": str(entry.get("ShipName") or "")}
        elif event == "ShipyardSell":
            key = "ship:" + str(entry.get("SellShipID"))
            if key in self.vessels:
                self.vessels[key]["sold"] = True
        elif event in ("ShipyardSwap", "ShipyardNew"):
            if entry.get("ShipID") is not None:
                self.ship = {"id": entry["ShipID"], "type": str(entry.get("ShipType") or "").lower(), "name": ""}
        elif event == "SetUserShipName":
            if self.ship and entry.get("ShipID") == self.ship.get("id"):
                self.ship["name"] = str(entry.get("UserShipName") or self.ship.get("name") or "")
        elif event == "FSDJump":
            self.carrier = None
            self.system = system_key(entry)
            self.taxi = bool(entry.get("Taxi", False))
            if not entry.get("Taxi") and self.ship and entry.get("JumpDist"):
                vessel = self._current()
                if vessel is not None:
                    vessel["ly"] += float(entry["JumpDist"])
                    vessel["jumps"] += 1
            if entry.get("StarPos"):
                self.pos = list(entry["StarPos"])
        elif event == "CarrierJump":
            self.system = system_key(entry)
            new = list(entry["StarPos"]) if entry.get("StarPos") else None
            if entry.get("MarketID") is not None:
                self.carrier = {"id": entry["MarketID"],
                                "name": str(entry.get("StationName") or (self.carrier or {}).get("name") or "")}
            if self.carrier and self.pos and new:
                vessel = self._current()
                distance = math.dist(self.pos, new)
                if vessel is not None and distance > 0:
                    vessel["ly"] += distance
                    vessel["jumps"] += 1
            if new:
                self.pos = new
        elif event == "Docked":
            if str(entry.get("StationType", "")).lower() == "fleetcarrier":
                self.carrier = {"id": entry.get("MarketID"), "name": str(entry.get("StationName") or "")}
            else:
                self.carrier = None
        elif event == "Undocked":
            self.carrier = None
        elif event == "Disembark":
            self.on_foot = True
            self.taxi = bool(entry.get("Taxi", False))
        elif event == "Embark":
            self.on_foot = False
            self.taxi = bool(entry.get("Taxi", False))
        elif event in ("Died", "Resurrect"):
            self.on_foot = False
        elif event == "Music" and entry.get("MusicTrack") == "MainMenu":
            self.in_game = False
        elif event == "Shutdown":
            self.in_game = False
        if event in ("Location", "Loadout", "ShipyardSwap", "FSDJump", "CarrierJump", "Docked", "Undocked", "Embark"):
            self._visit()

    def current_vessel_seconds(self, now: float) -> float:
        return self.current_seconds(now) if not self.on_foot and not self.taxi else 0.0

    def current_foot_seconds(self, now: float) -> float:
        return self.current_seconds(now) if self.on_foot else 0.0

    def current_seconds(self, now: float) -> float:
        """Time in the current vessel since the last journal event (not yet credited)."""
        if self.in_game and self.seg_start is not None and now > self.seg_start:
            return now - self.seg_start
        return 0.0


def scan_file(path: str, state: dict[str, Any] | None) -> tuple[dict, dict, float | None]:
    tracker = Tracker(state)
    last = None
    with open(path, encoding="utf-8", errors="replace") as stream:
        for line in stream:
            i = line.find('"timestamp":"')
            if i >= 0:
                stamp = line[i + 13:i + 33]
            else:                                   # tolerate '"timestamp": "..."' spacing
                match = _TS.search(line)
                if not match:
                    continue
                stamp = match.group(1)
            last = stamp
            if tracker.seg_start is None:
                tracker.seg_start = parse_ts(stamp)          # time counts from the file's first line
            if not any(key in line for key in _KEYS):
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            event = entry.get("event")
            if event not in RELEVANT or (event == "Music" and entry.get("MusicTrack") != "MainMenu"):
                continue
            tracker.feed(entry, parse_ts(entry.get("timestamp")))
    end = parse_ts(last) if last else None
    tracker.close(end)
    return tracker.vessels, tracker.state(), end


def merge(into: dict[str, dict], extra: dict[str, dict]) -> dict[str, dict]:
    for key, vessel in extra.items():
        total = into.setdefault(key, _new_vessel(vessel["kind"]))
        for field in ("ly", "jumps", "seconds"):
            total[field] += vessel[field]
        total["systems"] = sorted(set(total["systems"]).union(vessel.get("systems", [])))
        total["type"] = vessel["type"] or total["type"]
        total["name"] = vessel["name"] or total["name"]
        total["aliases"] = sorted(set(total.get("aliases",[])).union(vessel.get("aliases",[])))
        if "sold" in vessel:
            total["sold"] = vessel["sold"]
    return into


def journal_files(folder: str) -> list[str]:
    return sorted(name for name in os.listdir(folder) if name.startswith("Journal") and name.endswith(".log"))


def scan_all(folder: str, cache: dict[str, Any], progress: Callable[[int, int], None] | None = None,
             stop: Callable[[], bool] | None = None, commander: str | None = None) -> tuple[dict, dict, float | None, dict]:
    """Read every journal file in order, reusing cached results for files that haven't changed.
    Returns (totals per vessel, state at the end, time of the last line read, new cache)."""
    if not commander:
        # Pick the latest recorded commander once; never combine unrelated ShipIDs.
        for latest in reversed(journal_files(folder)):
            try:
                with open(os.path.join(folder,latest),encoding="utf-8-sig",errors="replace") as stream:
                    for _,line in zip(range(100),stream):
                        if '"Commander"' not in line and '"LoadGame"' not in line: continue
                        try: header=json.loads(line)
                        except ValueError: continue
                        if header.get("event")=="Commander": commander=header.get("Name")
                        elif header.get("event")=="LoadGame": commander=header.get("Commander")
                        if commander: break
            except OSError: pass
            if commander: break
    if cache.get("version") != CACHE_VERSION:
        cache = {"version": CACHE_VERSION, "files": {}}
    if cache.get("commander") != commander:
        cache = {"files": {}}
    old, files = cache.get("files", {}), journal_files(folder)
    new_files: dict[str, Any] = {}
    totals: dict[str, dict] = {}
    state: dict[str, Any] = {}
    last_end = None
    for number, name in enumerate(files, 1):
        if stop and stop():
            break
        path = os.path.join(folder, name)
        try:
            info = os.stat(path)
        except OSError:
            continue
        if commander:
            owner = None
            try:
                with open(path,encoding="utf-8-sig",errors="replace") as stream:
                    for _,line in zip(range(100),stream):
                        if '"Commander"' in line or '"LoadGame"' in line:
                            try:
                                header = json.loads(line)
                            except ValueError:
                                continue
                            if header.get("event") == "Commander": owner = header.get("Name")
                            elif header.get("event") == "LoadGame": owner = header.get("Commander")
                            if owner: break
            except OSError:
                continue
            if not owner or owner.casefold() != commander.casefold():
                continue
        key_in = json.dumps(state, sort_keys=True)
        entry = old.get(name)
        if not (entry and entry["size"] == info.st_size and entry["mtime"] == int(info.st_mtime)
                and entry["in"] == key_in):
            try:
                vessels, out, end = scan_file(path, state)
            except OSError:
                continue
            entry = {"size": info.st_size, "mtime": int(info.st_mtime), "in": key_in,
                     "vessels": vessels, "out": out, "end": end}
        new_files[name] = entry
        merge(totals, entry["vessels"])
        state = entry["out"]
        last_end = entry["end"] or last_end
        if progress:
            progress(number, len(files))
    return totals, state, last_end, {"version": CACHE_VERSION, "files": new_files, "commander": commander}


def recover_trip_travel(folder: str, jumps: int, last_ts: float, since: float, stop_limit) -> tuple[float, int, float]:
    """Travel time of an existing trip: (seconds, counted jumps, ly) from its jump-to-jump gaps.

    Reads the trip's own ship jumps (at most `jumps`, none before `since`, none after `last_ts`).
    A gap above stop_limit(BoostUsed) is a stop and is left out, matching the live counter.
    """
    found = {}
    remaining = max(0, int(jumps))
    for name in reversed(journal_files(folder)):
        if not remaining:
            break
        try:
            with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as stream:
                lines = stream.readlines()
        except OSError:
            continue
        for line in reversed(lines):
            if '"FSDJump"' not in line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            when = parse_ts(entry.get("timestamp"))
            if (entry.get("event") != "FSDJump" or entry.get("Taxi") or not entry.get("JumpDist")
                    or when is None or when > last_ts or when in found):
                continue
            if when < since:
                remaining = 0
                break
            found[when] = (float(entry["JumpDist"]), entry.get("BoostUsed"))
            remaining -= 1
            if not remaining:
                break
    seconds, counted, ly = 0.0, 0, 0.0
    times = sorted(found)
    for before, after in zip(times, times[1:]):
        distance, boost = found[after]
        if after - before <= stop_limit(boost):
            seconds += after - before
            counted += 1
            ly += distance
    return seconds, counted, ly


def recover_trip_systems(folder: str, jumps: int, last_ts: float) -> list[str]:
    """Migrate an existing trip using its saved jump count and last processed jump.

    Only destination systems count, matching the live Trip counter. Missing older
    journals limit reconstruction; never change the saved distance or jump count.
    """
    found = set()
    timestamps = set()
    remaining = max(0, int(jumps))
    for name in reversed(journal_files(folder)):
        if not remaining:
            break
        try:
            with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as stream:
                lines = stream.readlines()
        except OSError:
            continue
        for line in reversed(lines):
            if '"FSDJump"' not in line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            when = parse_ts(entry.get("timestamp"))
            if (entry.get("event") != "FSDJump" or entry.get("Taxi") or not entry.get("JumpDist")
                    or when is None or when > last_ts or when in timestamps):
                continue
            timestamps.add(when)
            destination = system_key(entry)
            if destination:
                found.add(destination)
            remaining -= 1
            if not remaining:
                break
    return sorted(found)
