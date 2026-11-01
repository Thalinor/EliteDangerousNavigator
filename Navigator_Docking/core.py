# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Docking journal state and pad reference layouts; no GUI or network access.

Pad layout tables adapted from bgol/LandingPad, Copyright 2018 Bernd Gollesch,
GPL-2.0-or-later. Combined work: GPL-3.0-or-later; see LICENSE and NOTICE.txt.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import math

REASONS = {
    "NoSpace": ("All suitable landing pads are occupied.", "Wait for a pad to clear, then request docking again."),
    "TooLarge": ("Your ship is too large for this station.", "Choose a station with a pad large enough for your ship."),
    "Hostile": ("The station considers you hostile.", "Check your local reputation and find another place to dock."),
    "Offences": ("Criminal offences detected.", "Check your local legal status and the station's access rules."),
    "Distance": ("You are outside docking-request range.", "Move within 7.5 km of the station and request docking again."),
    "ActiveFighter": ("Your ship-launched fighter is still deployed.", "Recall and recover your fighter before requesting docking."),
    "RestrictedAccess": ("This carrier's docking access is restricted.", "Check its owner, squadron and notoriety access rules."),
    "JumpImminent": ("The carrier is preparing to jump.", "Wait until the jump and docking lockdown have finished."),
    "NoReason": ("The station did not provide a reason.", "Check its access rules and try requesting again after a short wait."),
}
STARPORT_TYPES = {"bernal", "coriolis", "orbis", "asteroidbase", "ocellus", "dodec"}
COLONY_IDS = {129032183, 129032439, 129032695, 129032951, 129033207, 129033463}
PAD_RINGS = [(0, 0), (0, 0), (0, 2), (0, 2), (1, 0), (1, 0), (1, 1),
             (1, 2), (2, 0), (2, 2), (3, 0), (3, 0), (3, 1), (3, 2), (3, 2)]
SHELLS = (1.0, .625, .455, .25)


def layout_for(station_type: str, station: str, market_id=None) -> str:
    kind = str(station_type or "").casefold()
    if kind in STARPORT_TYPES:
        return "starport"
    if kind == "colonisationship" or (kind in {"surfacestation", "unknown", ""} and
            ((isinstance(market_id, int) and market_id in COLONY_IDS) or station.startswith("$EXT_PANEL_ColonisationShip"))):
        return "colony"
    if kind == "fleetcarrier":
        # LandingPad's journal-name convention: squadron carrier IDs have 4 chars.
        return "squadron" if len(station) == 4 else "carrier"
    return ""


def valid_pad(value, layout: str = "") -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        pad = int(value)
    except (TypeError, ValueError):
        return None
    maximum = {"starport": 45, "carrier": 16, "colony": 16, "squadron": 32}.get(layout, 999)
    return pad if 1 <= pad <= maximum else None


def starport_position(pad: int, reverse: bool = False) -> tuple[float, float, int, int]:
    if valid_pad(pad, "starport") is None:
        raise ValueError("Starport pads must be between 1 and 45")
    sector, ring = PAD_RINGS[(pad - 1) % 15]
    sector += ((pad - 1) // 15) * 4
    if reverse:
        sector = (sector + 6) % 12
    angle = math.radians(90 + sector * 30)
    radius = math.cos(math.radians(15)) * (SHELLS[ring] + SHELLS[ring + 1]) / 2
    return radius * math.cos(angle), radius * math.sin(angle), sector, ring


def carrier_boxes(layout: str, reverse: bool = False) -> list[tuple]:
    if layout not in {"carrier", "squadron", "colony"}:
        return []
    result = []
    for offset in ((26, -26) if layout == "squadron" else (0,)):
        boxes = [(x, y, x + 10, y + 16) for y in (22, 2, -18, -38) for x in (-12, 2)]
        boxes += [(x, y, x + 7, y + 11) for x in (-22, 15) for y in (25, 10)]
        small = (-24, 14, 20, -18) if layout == "carrier" else (-24, -18, 14, 20)
        boxes += [(x, 0, x + 4, 6) for x in small]
        for x1, y1, x2, y2 in boxes:
            x1, x2 = x1 + offset, x2 + offset
            if reverse:
                x1, y1, x2, y2 = -x2, -y2, -x1, -y1
            result.append((x1, y1, x2, y2))
    return result


def event_age(entry: dict, now=None) -> float:
    try:
        timestamp = datetime.fromisoformat(str(entry["timestamp"]).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return max(0, ((now or datetime.now(timezone.utc)) - timestamp).total_seconds())
    except (KeyError, ValueError, TypeError, OverflowError):
        return 0


@dataclass
class DockingState:
    phase: str = "idle"
    station: str = ""
    display_station: str = ""
    station_type: str = ""
    market_id: object = None
    layout: str = ""
    pad: int | None = None
    reason: str = ""
    message: str = ""
    hint: str = ""

    def reset(self):
        self.__dict__.update(DockingState().__dict__)

    def handle(self, entry: dict, now=None) -> bool:
        event = entry.get("event")
        if event in {"LoadGame", "Location", "Commander", "StartJump", "FSDJump", "CarrierJump",
                     "SupercruiseEntry", "Undocked", "Shutdown", "Died", "Resurrect"} or (
                event == "Music" and entry.get("MusicTrack") == "MainMenu"):
            self.reset()
            return True
        if event not in {"DockingRequested", "DockingGranted", "DockingDenied", "DockingCancelled", "DockingTimeout", "Docked"}:
            return False
        # Do not resurrect old permission/denial displays during journal catch-up.
        if event_age(entry, now) > (600 if event == "DockingGranted" else 60):
            self.reset()
            return True
        name = str(entry.get("StationName", self.station) or "")
        new_market = entry.get("MarketID", self.market_id)
        if name != self.station or new_market != self.market_id:
            self.station_type = ""
            self.display_station = name
        self.station, self.market_id = name, new_market
        self.station_type = str(entry.get("StationType", self.station_type) or "")
        self.layout = layout_for(self.station_type, self.station, self.market_id)
        self.display_station = str(entry.get("StationName_Localised") or self.display_station or name)
        if self.display_station.startswith("$EXT_PANEL_ColonisationShip"):
            self.display_station = "Colonisation ship"
        self.pad = None
        self.reason = ""
        self.hint = ""
        if event == "DockingRequested":
            self.phase, self.message = "pending", "Waiting for docking clearance…"
        elif event == "DockingGranted":
            self.phase = "granted"
            self.pad = valid_pad(entry.get("LandingPad"))
            self.message = "Docking clearance granted." if self.pad else "Clearance granted; pad number unavailable."
            if self.pad and valid_pad(self.pad, self.layout) is None:
                self.hint = "Pad is outside the verified diagram's range. Use the in-game pad marker."
            elif not self.layout:
                self.hint = "No verified diagram for this station type. Use the in-game pad marker."
        elif event == "DockingDenied":
            self.phase = "denied"
            self.reason = str(entry.get("Reason", "Unknown") or "Unknown")
            self.message, self.hint = REASONS.get(self.reason, (
                str(entry.get("Reason_Localised") or f"Reason reported by the game: {self.reason}"),
                "Check the station's access rules. This reason code is not yet mapped."))
        elif event == "Docked":
            self.phase, self.message = "docked", "Docking complete. Welcome aboard."
        elif event == "DockingTimeout":
            self.phase, self.message = "timeout", "Docking permission has expired."
            self.hint = "Request fresh clearance before entering or landing."
        else:
            self.phase, self.message = "cancelled", "Docking request cancelled."
        return True
