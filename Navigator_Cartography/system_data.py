# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Journal/EDSM facts and presentation for the current system; no GUI code."""
from __future__ import annotations

import copy
import math
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

SCOOPABLE = frozenset("OBAFGKM")
EVENTS = frozenset(("Location", "FSDJump", "CarrierJump", "Scan", "FSSDiscoveryScan",
                    "FSSAllBodiesFound", "NavBeaconScan", "DiscoveryScan", "StartJump", "FSDTarget", "NavRoute"))


def number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError):
        return None


def data_time(value) -> float | None:
    """Observation/update timestamp, never a download or discovery-credit date."""
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def merge_observation(first: dict, second: dict) -> dict:
    """Second has local priority unless first has a strictly newer known date."""
    a, b = first.get("updated"), second.get("updated")
    first_newer = a is not None and b is not None and a > b
    preferred, fallback = (first, second) if first_newer else (second, first)
    result = {k:v for k,v in fallback.items() if v is not None}
    result.update({k:v for k,v in preferred.items() if v is not None})
    if preferred:
        result["updated"] = preferred.get("updated")
    return result


def star_code(body: dict) -> str | None:
    if body.get("StarType"):
        return str(body["StarType"])
    subtype = str(body.get("subType") or "")
    low = subtype.lower()
    if "neutron" in low:
        return "N"
    if "supermassive" in low and "black hole" in low:
        return "SupermassiveBlackHole"
    if "black hole" in low:
        return "H"
    if "white dwarf" in low:
        match = re.search(r"\((D[A-Z]*)\)", subtype)
        return match.group(1) if match else "D"
    if "herbig" in low:
        return "AeBe"
    if "t tauri" in low:
        return "TTS"
    if "wolf-rayet" in low:
        match = re.search(r"\b(WNC|WN|WC|WO)\b", subtype)
        if match:
            return match.group(1)
        return {"n": "WN", "c": "WC", "o": "WO"}.get(low.split("wolf-rayet", 1)[1].strip().split(" ")[0], "W")
    spectral = str(body.get("spectralClass") or "")
    match = re.match(r"^(CHd|WNC|TTS|AeBe|WN|WC|WO|CH|CJ|CN|CS|MS|D[A-Z]*|[OBAFGKMLTYNSCHWX])(?:[0-9 .]|$)", spectral)
    if match:
        return match.group(1)
    match = re.match(r"^(CHd|WNC|TTS|AeBe|WN|WC|WO|CH|CJ|CN|CS|MS|D[A-Z]*|[OBAFGKMLTYNSCHWX])(?:[ (]|$)", subtype)
    return match.group(1) if match else None


def scoopable(star: dict) -> bool | None:
    code = star.get("code")
    if code:
        return str(code).split("_", 1)[0] in SCOOPABLE
    explicit = star.get("scoopable")
    return explicit if isinstance(explicit, bool) else None


def new_record() -> dict:
    return {"stars": {}, "bodies": [], "resolved": [], "expected": None,
            "honk": False, "full": False, "discovered": False, "first": False, "primary": {}, "updated": None}


def merge_records(first: dict | None, second: dict | None) -> dict:
    result = copy.deepcopy(first or new_record())
    other = second or new_record()
    for key in ("bodies", "resolved"):
        result[key] = sorted(set(result.get(key, [])).union(other.get(key, [])))
    for key in ("honk", "full", "discovered", "first"):
        result[key] = bool(result.get(key) or other.get(key))
    result["expected"] = max(filter(lambda x: x is not None,
                                    (result.get("expected"), other.get("expected"))), default=None)
    result["primary"] = merge_observation(result.get("primary", {}), other.get("primary", {}))
    times = [t for t in (result.get("updated"), other.get("updated")) if t is not None]
    result["updated"] = max(times, default=None)
    for name, star in other.get("stars", {}).items():
        result["stars"][name] = merge_observation(result["stars"].get(name, {}), star)
    return result


class SystemBook:
    def __init__(self, records: dict | None = None):
        self.records = records or {}

    @staticmethod
    def key(commander: str, beta: bool, system: str) -> str:
        return ("beta:" if beta else "live:") + commander.casefold() + ":" + system.casefold()

    def record(self, commander: str, beta: bool, system: str | None) -> dict:
        if not system:
            return new_record()
        return self.records.get(self.key(commander, beta, system), new_record())

    def navigation(self, commander: str, beta: bool, entry: dict, state: dict | None = None):
        """Route classes describe primary stars, not visits or complete inventories."""
        event = entry.get("event")
        candidates = []
        if event == "StartJump" and entry.get("JumpType") == "Hyperspace":
            candidates.append(entry)
        elif event == "FSDTarget":
            candidates.append(dict(entry, StarSystem=entry.get("Name")))
        elif event in ("NavRoute", "StartUp", "Location", "FSDJump", "CarrierJump"):
            route = entry.get("Route") if event == "NavRoute" else None
            if route is None and state:
                saved = state.get("NavRoute")
                if isinstance(saved, dict) and saved.get("event") != "NavRouteClear":
                    route = saved.get("Route")
            if isinstance(route, list):
                candidates.extend(r for r in route if isinstance(r, dict))
        for item in candidates:
            name, code = item.get("StarSystem"), item.get("StarClass")
            if name and code:
                record = self.records.setdefault(self.key(commander, beta, name), new_record())
                record["primary"] = merge_observation(record.get("primary", {}),
                    {"code": str(code), "address": item.get("SystemAddress"),
                     "updated": data_time(entry.get("timestamp"))})
        if event == "StartJump" and candidates:
            return candidates[0].get("StarSystem"), candidates[0].get("SystemAddress")
        return None

    def feed(self, commander: str, beta: bool, system: str | None, entry: dict) -> None:
        event = entry.get("event")
        if event not in EVENTS or not system:
            return
        named = entry.get("StarSystem") or entry.get("SystemName")
        if named and named.casefold() != system.casefold():
            return
        record = self.records.setdefault(self.key(commander, beta, system), new_record())
        observed = data_time(entry.get("timestamp"))
        if observed is not None and event in ("Scan", "FSSDiscoveryScan", "FSSAllBodiesFound", "NavBeaconScan"):
            record["updated"] = max(record.get("updated") or observed, observed)
        if event == "FSDJump" and entry.get("Body") and entry.get("BodyType", "Star") == "Star":
            record.setdefault("primary", {})["name"] = entry["Body"]
        if event in ("FSSDiscoveryScan", "NavBeaconScan"):
            count = number(entry.get("BodyCount") if event == "FSSDiscoveryScan" else entry.get("NumBodies"))
            if count is not None and count.is_integer():
                record["expected"] = int(count)
            if event == "FSSDiscoveryScan":
                record["honk"] = True
                progress = number(entry.get("Progress"))
                if progress is not None and progress >= 1:
                    record["full"] = True
        elif event == "FSSAllBodiesFound":
            record["full"] = True
            count = number(entry.get("Count"))
            if count is not None:
                record["expected"] = int(count)
        elif event == "Scan":
            name = str(entry.get("BodyName") or "")
            if not name:
                return
            is_body = bool(entry.get("StarType") or entry.get("PlanetClass"))
            if is_body and name not in record["bodies"]:
                record["bodies"].append(name)
            # Star discovery on arrival/honk is not proof of a deliberate FSS body scan.
            if is_body and (entry.get("PlanetClass") or entry.get("ScanType") in ("NavBeacon", "NavBeaconDetail")) and entry.get("ScanType") in ("Detailed", "NavBeacon", "NavBeaconDetail"):
                if name not in record["resolved"]:
                    record["resolved"].append(name)
            if entry.get("WasDiscovered") is True:
                record["discovered"] = True
            elif entry.get("WasDiscovered") is False and entry.get("StarType"):
                record["first"] = True        # nobody had discovered this star: first discovery
            if entry.get("StarType"):
                star = {"code": str(entry["StarType"]), "distance": number(entry.get("DistanceFromArrivalLS")), "id": entry.get("BodyID"), "updated": observed}
                record["stars"][name] = merge_observation(record["stars"].get(name, {}), star)

    def merge(self, other: "SystemBook") -> None:
        for key, record in other.records.items():
            self.records[key] = merge_records(self.records.get(key), record)


def edsm_record(payload: dict, system: str, address: int | None = None) -> dict:
    """Validate the response before allowing it into this system's cache."""
    if not isinstance(payload, dict):
        raise ValueError("EDSM did not return a system object")
    if not payload:
        return {"known": False, "record": new_record(), "complete": False}
    if str(payload.get("name") or "").casefold() != system.casefold():
        raise ValueError("EDSM returned a different system")
    if address is not None and payload.get("id64") is not None and str(payload["id64"]) != str(address):
        raise ValueError("EDSM returned a different system address")
    bodies = payload.get("bodies")
    if not isinstance(bodies, list):
        raise ValueError("EDSM response is missing bodies")
    record = new_record()
    for body in bodies:
        if not isinstance(body, dict) or body.get("type") not in ("Star", "Planet"):
            continue
        name = str(body.get("name") or "")
        if not name:
            continue
        if name not in record["bodies"]:
            record["bodies"].append(name)
        if body.get("type") == "Star":
            distance = number(body.get("distanceToArrival"))
            if distance is None and body.get("isMainStar") is True:
                distance = 0.0
            updated = data_time(body.get("updateTime") or body.get("updatedAt"))
            record["stars"][name] = {"code": star_code(body), "distance": distance,
                                     "scoopable": body.get("isScoopable"), "updated": updated}
        updated = data_time(body.get("updateTime") or body.get("updatedAt"))
        if updated is not None:
            record["updated"] = max(record.get("updated") or updated, updated)
    count = number(payload.get("bodyCount"))
    if count is not None and count > 0 and count.is_integer():
        record["expected"] = int(count)
    complete = bool(record["expected"] and len(record["bodies"]) >= record["expected"])
    return {"known": True, "record": record, "complete": complete}


class Values(tuple):
    """The six Overview values, plus what the clickable Fuel Star lines copy."""
    entry_star: str | None = None
    fuel_targets: list = []
    fuel_distances: list = []       # light seconds from the arrival star, one per fuel_targets line


def group_values(system: str | None, local: dict | None = None, external: dict | None = None,
                 online_status: str = "", history_pending: bool = False) -> tuple[str, ...]:
    if not system:
        return ("—", "Unknown", "Unknown", "Unknown", "N/A", "Unknown")   # same order as the labels
    local = local or new_record()
    external = external or {}
    # Local observations are more authoritative than third-party values.
    combined = merge_records(external.get("record"), local)
    expected = local.get("expected")
    local_complete = bool(local.get("full") or (expected and len(local.get("bodies", [])) >= expected))
    complete = bool(local_complete or external.get("complete"))
    primary = combined.get("primary", {})
    code = primary.get("code")
    if code:
        primary_name = primary.get("name")
        match_name = primary_name if primary_name in combined["stars"] else None
        if match_name is None:
            match_name = next((name for name, star in combined["stars"].items()
                               if star.get("distance") == 0), None)
        hint = {"code": code, "distance": 0.0, "updated": primary.get("updated")}
        if match_name is None:
            combined["stars"]["@primary"] = hint
        elif match_name not in local.get("stars", {}):
            # An undated/stale database primary must not erase a fresh game hint.
            combined["stars"][match_name] = merge_observation(combined["stars"][match_name], hint)
    stars = list(combined["stars"].values())
    classes = Counter(s["code"] for s in stars if s.get("code"))
    # The stars known so far: their types, plus a "?" for each star known to exist whose
    # type isn't known yet. No tags. (Before a honk only the primary is known; the honk
    # scans every star at once.)
    types = ", ".join(code if count == 1 else f"{code} ×{count}" for code, count in sorted(classes.items()))
    untyped = sum(1 for s in stars if not s.get("code"))
    if untyped:
        types = ", ".join(filter(None, [types] + ["?"] * untyped))
    statuses = [scoopable(s) for s in stars]
    fuel = "Yes" if True in statuses else "No" if complete and stars and None not in statuses else "Unknown"
    # Honked and every star we know of is a non-scoopable one: say so instead of "Unknown".
    # "None found" (not "No") because the journal does not list companion stars after a honk.
    if fuel == "Unknown" and local.get("honk") and stars and None not in statuses:
        fuel = "None found"
    # You arrive at the arrival star, so a star's distance from arrival is how far it is
    # from you the moment you drop in (e.g. from the neutron to the nearest fuel star).
    fuel_stars = [(name, s) for name, s in combined["stars"].items()
                  if scoopable(s) is True and s.get("distance") is not None]
    # The star you arrive at (the entry point): what the clickable Fuel Star value copies.
    entry_star = primary.get("name") or next(
        (n for n, s in combined["stars"].items() if s.get("distance") == 0 and not n.startswith("@")), None) or system
    # Every scoopable star, nearest first, as (text, name to copy); the panel shows one per line.
    fuel_targets: list[tuple[str, str]] = []
    if fuel_stars:
        for star_name, best in sorted(fuel_stars, key=lambda item: item[1]["distance"]):
            if best["distance"] == 0:
                fuel_targets.append(("Primary Star", entry_star))
                continue
            # The full star name, so you can see (and copy) where it is.
            ls = best["distance"]
            fuel_targets.append((f"{star_name} · " + (f"{ls:,.1f} Ls" if ls < 100 else f"{ls:,.0f} Ls"), star_name))
        distance = "\n".join(text for text, _ in fuel_targets)
    elif fuel == "No":
        distance = "None"
    elif fuel == "None found":
        distance = "None found"
    elif not complete and not local.get("honk"):
        distance = "Unknown – honk to find stars"
    else:
        distance = "Unknown"
    # The primary (the star you arrive at, reported before arrival) decides it: you can
    # only supercharge there on arrival. A rare companion neutron is shown with its
    # designation and distance, like Fuel Distance.
    primary_code = primary.get("code") or next(
        (s.get("code") for s in stars if s.get("distance") == 0 and s.get("code")), None)
    companions = [(name, s) for name, s in combined["stars"].items()
                  if s.get("code") == "N" and s.get("distance") not in (None, 0)]
    if primary_code == "N":
        neutron = "Yes"
    elif companions:
        star_name, best = min(companions, key=lambda item: item[1]["distance"])
        short = star_name[len(system):].strip() if star_name.casefold().startswith(system.casefold()) else star_name
        ls = best["distance"]
        neutron = f"{short or 'Companion'} · " + (f"{ls:,.1f} Ls" if ls < 100 else f"{ls:,.0f} Ls")
    elif primary_code:
        neutron = "No"
    else:
        neutron = "Unknown"
    online_time = external.get("record", {}).get("updated")
    local_time = local.get("updated")
    local_status = local_complete or local.get("resolved") or local.get("honk") or local.get("discovered")
    online_status_allowed = not local_status or (online_time is not None and local_time is not None and online_time > local_time)
    # "Known:" - how much of this system was already known. A star scan (including the
    # automatic ones from a honk) with WasDiscovered=false means nobody found it before you.
    if local.get("first"):
        visited = "First Discovery!"
    elif local_complete or (online_status_allowed and external.get("complete")):
        visited = "Fully Scanned"
    elif local.get("resolved") or (online_status_allowed and external.get("known")
                                   and external.get("record", {}).get("bodies")):
        visited = "Partially Scanned"
    elif local.get("honk"):
        visited = "Honked"
    elif local.get("discovered") or (online_status_allowed and external.get("known")):
        # WasDiscovered/EDSM knowledge says this system is known, not that this
        # commander honked it during the current visit.
        visited = "Known"
    elif history_pending:
        visited = "Reading Journals…"
    elif online_status == "loading":
        visited = "Checking EDSM…"
    else:
        visited = "Unknown"
    result = Values((system, types or "Unknown", neutron, fuel, distance, visited))   # same order as the labels
    result.entry_star = entry_star
    result.fuel_targets = fuel_targets
    result.fuel_distances = [best["distance"] for _, best in sorted(fuel_stars, key=lambda item: item[1]["distance"])]
    return result


def nearest_fuel_distance(record: dict | None) -> float | None:
    """Light seconds from the arrival star to the nearest scoopable star we know of in this system (0 when you arrive at
    one), or None when no scoopable star with a known distance is on record. Never a guess."""
    distances = [star["distance"] for star in (record or {}).get("stars", {}).values()
                 if scoopable(star) is True and star.get("distance") is not None]
    primary = (record or {}).get("primary") or {}
    if primary.get("code") and str(primary["code"]).split("_", 1)[0] in SCOOPABLE:
        distances.append(0.0)
    return min(distances) if distances else None
