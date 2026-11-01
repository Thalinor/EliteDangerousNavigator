# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Surface map data: where you have driven, bookmarks, and exobiology sample spots. Positions come from the game's own
Status.json (latitude, longitude, heading) as EDMC passes them on; nothing here touches the game."""
from __future__ import annotations

import json
import math
import os
from typing import Any

TRACK_STEP_M = 20.0                   # a new ground track point only when you have moved this far
SHIP_STEP_M = 60.0                    # the flight path needs fewer points
GROUND, SHIP = 0, 1
TRACK_MAX = 4000
# Minimum distance in metres between samples of the same species, by genus (published in-game).
COLONY_M = {"Aleoida": 150, "Amphora": 100, "Anemone": 100, "Bacterium": 500, "Bark": 100, "Brain": 100, "Cactoida": 300,
            "Clypeus": 150, "Concha": 150, "Crystalline": 100, "Electricae": 1000, "Fonticulua": 500, "Frutexa": 150,
            "Fumerola": 100, "Fungoida": 300, "Osseus": 800, "Recepta": 150, "Shrubs": 150, "Sinuous": 100, "Stratum": 500,
            "Tubus": 800, "Tussock": 200}
DEFAULT_COLONY_M = 150


def point_mode(point: list) -> int:
    """Older saved points have no mode; they were recorded in flight, so they count as the ship's path."""
    return int(point[2]) if len(point) > 2 else SHIP


def segments(track: list, show_ship: bool) -> list[tuple[int, list[tuple[float, float]]]]:
    """The track cut into unbroken runs of one mode: [(mode, [(lat, lon), ...]), ...]. Flight runs are left out unless wanted."""
    runs: list[tuple[int, list[tuple[float, float]]]] = []
    for point in track:
        mode = point_mode(point)
        if not runs or runs[-1][0] != mode:
            runs.append((mode, []))
        runs[-1][1].append((point[0], point[1]))
    return [run for run in runs if run[0] == GROUND or show_ship]


def genus_key(name: str) -> str:
    """Journal genus text such as '$Codex_Ent_Aleoider_Genus_Name;' or 'Aleoida' -> 'Aleoida'."""
    text = (name or "").strip()
    for key in COLONY_M:
        if key.lower() in text.lower():
            return key
    return text


def colony_distance(genus: str) -> int:
    return COLONY_M.get(genus_key(genus), DEFAULT_COLONY_M)


def offset_m(lat0: float, lon0: float, lat: float, lon: float, radius: float) -> tuple[float, float]:
    """(east, north) in metres of a point relative to a centre, flat-earth: fine for a few kilometres."""
    north = math.radians(lat - lat0) * radius
    east = math.radians((lon - lon0 + 180) % 360 - 180) * radius * math.cos(math.radians(lat0))
    return east, north


def distance_bearing(lat0: float, lon0: float, lat: float, lon: float, radius: float) -> tuple[float, float]:
    """Great-circle distance in metres and initial bearing in degrees from the first point to the second."""
    p0, p1 = math.radians(lat0), math.radians(lat)
    dl = math.radians(lon - lon0)
    a = math.sin((p1 - p0) / 2) ** 2 + math.cos(p0) * math.cos(p1) * math.sin(dl / 2) ** 2
    distance = 2 * radius * math.asin(min(1.0, math.sqrt(a)))
    y = math.sin(dl) * math.cos(p1)
    x = math.cos(p0) * math.sin(p1) - math.sin(p0) * math.cos(p1) * math.cos(dl)
    return distance, (math.degrees(math.atan2(y, x)) + 360) % 360


def distance_text(metres: float) -> str:
    return f"{metres:.0f} m" if metres < 1000 else f"{metres / 1000:.2f} km"


class SurfaceStore:
    """Per-body surface data, kept in one JSON file."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.bodies: dict[str, dict[str, Any]] = {}
        self.dirty = False
        self.load()

    @staticmethod
    def key(system: str, body: str) -> str:
        return f"{system}|{body}"

    def body(self, key: str, radius: float | None = None) -> dict[str, Any]:
        record = self.bodies.setdefault(key, {"radius": 0.0, "track": [], "marks": [], "samples": []})
        if radius:
            record["radius"] = float(radius)
        return record

    def add_position(self, key: str, radius: float, lat: float, lon: float, mode: int = GROUND) -> bool:
        """mode: GROUND (on foot, in the SRV or landed) or SHIP (flying). Points are [lat, lon, mode]."""
        record = self.body(key, radius)
        track = record["track"]
        if track and record["radius"] and point_mode(track[-1]) == mode:
            d, _b = distance_bearing(track[-1][0], track[-1][1], lat, lon, record["radius"])
            if d < (TRACK_STEP_M if mode == GROUND else SHIP_STEP_M):
                return False
        track.append([round(lat, 6), round(lon, 6), mode])      # a change of mode always starts a new point, so lines never join
        if len(track) > TRACK_MAX:
            del track[:len(track) - TRACK_MAX]
        self.dirty = True
        return True

    def add_mark(self, key: str, lat: float, lon: float) -> str:
        record = self.body(key)
        name = f"Mark {len(record['marks']) + 1}"
        record["marks"].append({"name": name, "lat": round(lat, 6), "lon": round(lon, 6)})
        self.dirty = True
        return name

    def remove_last_mark(self, key: str) -> None:
        record = self.body(key)
        if record["marks"]:
            record["marks"].pop()
            self.dirty = True

    def add_sample(self, key: str, genus: str, species: str, stage: str, lat: float, lon: float) -> None:
        """stage: Log, Sample (rings stay up) or Analyse (that species is finished, its rings come down)."""
        record = self.body(key)
        genus = genus_key(genus)
        if stage == "Analyse":
            for sample in record["samples"]:
                if sample["genus"] == genus and sample["species"] == species:
                    sample["done"] = True
        record["samples"].append({"genus": genus, "species": species, "stage": stage, "lat": round(lat, 6),
                                  "lon": round(lon, 6), "done": stage == "Analyse"})
        self.dirty = True

    def rings(self, key: str) -> list[dict[str, Any]]:
        return [s for s in self.body(key)["samples"] if not s["done"]]

    def clear(self, key: str) -> None:
        self.bodies.pop(key, None)
        self.dirty = True

    def margin(self, key: str, lat: float, lon: float) -> tuple[str, float] | None:
        """Tightest sample ring you are in or nearest to: (genus, metres to the ring edge; negative = inside)."""
        record = self.body(key)
        if not record["radius"]:
            return None
        best = None
        for sample in self.rings(key):
            d, _b = distance_bearing(sample["lat"], sample["lon"], lat, lon, record["radius"])
            gap = d - colony_distance(sample["genus"])
            if best is None or gap < best[1]:
                best = (sample["genus"], gap)
        return best

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
            self.bodies = {k: v for k, v in (data.get("bodies") or {}).items() if isinstance(v, dict)}
        except (OSError, ValueError, AttributeError):
            self.bodies = {}

    def save(self) -> None:
        if not self.dirty:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path + ".tmp", "w", encoding="utf-8") as handle:
                json.dump({"bodies": self.bodies}, handle)
            os.replace(self.path + ".tmp", self.path)
            self.dirty = False
        except OSError:
            pass
