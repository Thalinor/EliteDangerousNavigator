# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""The current system as the journal tells it, and the text lines the Values tab shows. No Tk in here, so it is easy to test.

The rules for what counts toward the system value (the honk share riding with the main star, the fully scanned and fully
mapped bonuses, hiding mapped bodies from the valuable list) follow Pioneer by Jeremy Rimpo, GPL-2.0-or-later (see CREDITS.txt).
"""
from __future__ import annotations

import json
import os
from typing import Any

try:
    from . import labels, values
except ImportError:                      # loaded as a plain (non-package) plugin
    import labels
    import values

NEW_SYSTEM_EVENTS = ("FSDJump", "Location", "CarrierJump")
BIO_TYPE, GEO_TYPE = "$SAA_SignalType_Biological;", "$SAA_SignalType_Geological;"
FULL_SCAN_PER_BODY, FULL_MAP_PER_PLANET = 1000, 10000


class Body:
    def __init__(self, body_id: int, name: str) -> None:
        self.id, self.name = body_id, name
        self.star_type = ""
        self.subclass = 0
        self.luminosity = ""
        self.planet_class = ""
        self.terraform = ""
        self.mass = 0.0
        self.landable = False
        self.distance = None
        self.was_discovered = True      # nothing is assumed first-discovered until the game says so
        self.was_mapped = True
        self.mapped = False
        self.bio = 0
        self.geo = 0

    @property
    def is_star(self) -> bool:
        return bool(self.star_type)

    @property
    def is_planet(self) -> bool:
        return bool(self.planet_class) and not self.star_type

    @property
    def terraformable(self) -> bool:
        return self.terraform == "Terraformable"

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data: dict) -> "Body":
        body = cls(int(data.get("id", 0)), str(data.get("name", "")))
        for key, value in data.items():
            if key in body.__dict__:
                body.__dict__[key] = value
        return body

    def estimate(self) -> values.Estimate | None:
        if self.is_star:
            scan, honk = values.star_value(self.star_type, self.mass, not self.was_discovered)
            return values.Estimate(scan, scan, scan, scan, honk, honk)
        if self.is_planet:
            return values.body_estimate(self.planet_class, self.terraform, self.mass, not self.was_discovered,
                                        not self.was_mapped)
        return None

    def current(self) -> tuple[int, int]:
        estimate = self.estimate()
        if estimate is None:
            return 0, 0
        if self.is_planet and self.mapped:
            return estimate.map_low, estimate.map_high
        return estimate.scan_low, estimate.scan_high

    def maximum(self) -> tuple[int, int]:
        estimate = self.estimate()
        if estimate is None:
            return 0, 0
        if self.is_planet:
            return estimate.map_low, estimate.map_high
        return estimate.scan_low, estimate.scan_high


class SystemModel:
    def __init__(self) -> None:
        self.system = ""
        self.bodies: dict[int, Body] = {}
        self.honked = False
        self.body_count = 0
        self.non_body_count = 0
        self.all_found = False

    def reset(self, system: str) -> None:
        self.system = system
        self.bodies.clear()
        self.honked = self.all_found = False
        self.body_count = self.non_body_count = 0

    def feed(self, entry: dict) -> bool:
        """Takes one journal entry; True when something shown changed."""
        event = entry.get("event")
        if event in NEW_SYSTEM_EVENTS:
            system = entry.get("StarSystem")
            if system and system != self.system:
                self.reset(system)
                return True
            return False
        if event == "FSSDiscoveryScan":
            self.honked, self.body_count = True, int(entry.get("BodyCount") or 0)
            self.non_body_count = int(entry.get("NonBodyCount") or 0)
            return True
        if event == "FSSAllBodiesFound":
            self.all_found = True
            return True
        if event == "Scan":
            return self._scan(entry)
        if event == "SAAScanComplete":
            body = self.bodies.get(entry.get("BodyID"))
            if body is not None:
                body.mapped = True
                return True
            return False
        if event in ("FSSBodySignals", "SAASignalsFound"):
            body = self.bodies.get(entry.get("BodyID"))
            if body is None:
                return False
            for signal in entry.get("Signals") or ():
                if signal.get("Type") == BIO_TYPE:
                    body.bio = int(signal.get("Count") or 0)
                elif signal.get("Type") == GEO_TYPE:
                    body.geo = int(signal.get("Count") or 0)
            return True
        return False

    def _scan(self, entry: dict) -> bool:
        body_id, name = entry.get("BodyID"), entry.get("BodyName", "")
        if body_id is None or not (entry.get("StarType") or entry.get("PlanetClass")):
            return False                # belts, rings and barycentres carry no value
        if not self.system:
            self.system = entry.get("StarSystem") or self.system
        body = self.bodies.get(body_id) or Body(body_id, name)
        body.name = name
        body.star_type = entry.get("StarType") or ""
        body.subclass = int(entry.get("Subclass") or 0)
        body.luminosity = entry.get("Luminosity") or ""
        body.planet_class = entry.get("PlanetClass") or ""
        body.terraform = entry.get("TerraformState") or ""
        body.mass = float((entry.get("StellarMass") if body.star_type else entry.get("MassEM")) or 0.0)
        body.landable = bool(entry.get("Landable"))
        body.distance = entry.get("DistanceFromArrivalLS")
        body.was_discovered = bool(entry.get("WasDiscovered", True))
        body.was_mapped = bool(entry.get("WasMapped", True))
        self.bodies[body_id] = body
        return True

    # ---- derived figures
    def short(self, body: Body) -> str:
        name = body.name
        if self.system and name.startswith(self.system):
            name = name[len(self.system):].strip()
        return name or "Main star"

    def ordered(self) -> list[Body]:
        return sorted(self.bodies.values(), key=lambda b: (b.distance if b.distance is not None else 0.0, b.id))

    def planets(self) -> list[Body]:
        return [b for b in self.bodies.values() if b.is_planet]

    def main_star(self) -> Body | None:
        stars = [b for b in self.ordered() if b.is_star]
        return stars[0] if stars else None

    def previously_scanned(self) -> bool:
        return any(b.was_discovered for b in self.bodies.values())

    def previously_mapped(self) -> bool:
        return any(b.was_mapped for b in self.planets())

    def fully_scanned_bonus(self) -> int:
        return (self.body_count + self.non_body_count) * FULL_SCAN_PER_BODY if self.body_count else 0

    def fully_mapped_bonus(self) -> int:
        return len(self.planets()) * FULL_MAP_PER_PLANET

    def totals(self) -> dict[str, tuple[int, int]]:
        """now / max / honk, each (low, high). The honk share is paid with the main star, so it only counts once that star
        is scanned. The fully scanned and mapped bonuses count in max always, and in now once the system is complete."""
        now, top, honk = [0, 0], [0, 0], [0, 0]
        for body in self.bodies.values():
            estimate = body.estimate()
            if estimate is None:
                continue
            for total, pair in ((now, body.current()), (top, body.maximum()), (honk, (estimate.honk_low, estimate.honk_high))):
                total[0] += pair[0]
                total[1] += pair[1]
        counted_honk = honk if (self.honked and self.main_star() is not None) else [0, 0]
        for part in (0, 1):
            now[part] += counted_honk[part]
            top[part] += counted_honk[part]
        planets = self.planets()
        if not self.previously_scanned() and self.fully_scanned_bonus():
            for part in (0, 1):
                top[part] += self.fully_scanned_bonus()
                if self.all_found:
                    now[part] += self.fully_scanned_bonus()
        if planets and not self.previously_mapped():
            for part in (0, 1):
                top[part] += self.fully_mapped_bonus()
                if self.all_found and all(b.mapped for b in planets):
                    now[part] += self.fully_mapped_bonus()
        return {"now": tuple(now), "max": tuple(top), "honk": tuple(counted_honk)}

    def valuable(self, threshold: int) -> list[Body]:
        picked = [b for b in self.planets() if not b.mapped and b.maximum()[1] >= threshold]
        return sorted(picked, key=lambda b: b.distance if b.distance is not None else 0.0)

    def unmapped_signals(self) -> list[Body]:
        return [b for b in self.ordered() if b.is_planet and b.bio and not b.mapped]

    def with_signals(self) -> list[Body]:
        return [b for b in self.ordered() if b.bio or b.geo]

    def describe(self, body: Body, descriptors: bool = False) -> str:
        if body.is_star:
            return labels.star_label(body.star_type, body.subclass, body.luminosity, descriptors)
        tag = labels.planet_tag(body.planet_class)
        return labels.title_case(body.planet_class or "Body") + (" (T)" if body.terraformable else "") + (f" [{tag}]" if tag else "")

    def tag(self, body: Body) -> str:
        """Class letters, then the status tags: (T) terraformable; red (S) / (M) when someone had already scanned / mapped it."""
        tag = labels.planet_tag(body.planet_class)
        out = f" [{tag}]" if tag else ""
        if body.terraformable:
            out += " (T)"
        if body.was_discovered and body.is_planet:
            out += " {bad:(S)}"
        if body.was_mapped and body.is_planet:
            out += " {bad:(M)}"
        return out

    def system_tags(self) -> str:
        """(H) honked, (S) fully scanned, (M) fully mapped; green when you are the first, plain when it was known already."""
        tags = []
        if self.honked:
            tags.append("(H)")
        if self.all_found and self.body_count and len(self.bodies) >= self.body_count:
            tags.append("(S)" if self.previously_scanned() else "{good:(S)}")
        planets = self.planets()
        if self.all_found and planets and all(b.mapped for b in planets):
            tags.append("(M)" if self.previously_mapped() else "{good:(M)}")
        return " ".join(tags) + "   " if tags else ""

    def counts_line(self) -> str:
        shown = len(self.bodies)
        total = self.body_count if self.honked else "?"
        line = f"B#: {shown}/{total}"
        if self.honked:
            line += f"  NB#: {self.non_body_count}"
        planets = self.planets()
        if planets and sum(1 for b in planets if b.mapped) < len(planets):
            line += f"  Mapped: {sum(1 for b in planets if b.mapped)}/{len(planets)}"
        return line

    def lines(self, threshold: int, detail: bool = True, descriptors: bool = False) -> list[tuple[str, str]]:
        """(style, text) pairs for the Values tab. Styles: head, text, dim, good, rule."""
        if not self.system:
            return [("dim", "Waiting for a system. Jump or load a journal.")]
        if not self.bodies:
            if self.honked and self.body_count == 0:
                note = "Nothing here: no bodies to scan."               # honked already, so never ask to honk again
            elif self.honked:
                note = f"Honked: {self.body_count} bodies. Scan them to see values."
            else:
                note = "Nothing scanned yet. Honk, or check nav beacon data."
            return [("head", self.system), ("dim", note), ("dim", self.counts_line())]
        out: list[tuple[str, str]] = [("head", self.system)]
        out.append(("text", self.system_tags() + self.counts_line()))
        high = self.valuable(threshold)
        if high:
            out.append(("rule", ""))
            out.append(("head", f"Valuable Bodies (over {values.credits(threshold)})"))
            for body in high:
                ls = f", {body.distance:,.0f} ls" if body.distance is not None else ""
                first = ", First Map" if not body.was_mapped else ""
                out.append(("good", f"{self.short(body)}{self.tag(body)}  (Max {values.credits(body.maximum()[1])}{ls}{first})"))
        unmapped = self.unmapped_signals()
        if unmapped:
            out.append(("head", "Biological Signals (Unmapped)"))
            out.append(("text", "   ".join(f"{self.short(b)} ({b.bio})" for b in unmapped)))
        if detail:
            out.append(("rule", ""))
            main = self.main_star()
            sums = self.totals()
            for body in self.ordered():
                estimate = body.estimate()
                if estimate is None:
                    continue
                marks = []
                if not body.was_discovered:
                    marks.append("First Discovery")
                if body.is_planet and body.mapped:
                    marks.append("Mapped")
                elif body.is_planet and not body.was_mapped:
                    marks.append("First Map")
                if body.landable:
                    marks.append("Landable")
                suffix = f"   [{', '.join(marks)}]" if marks else ""
                out.append(("text", f"{self.short(body)} - {self.describe(body, descriptors)}{suffix}"))
                if body is main and self.honked:
                    out.append(("dim", f"   {values.credits(estimate.scan_high)} + {values.credit_range(*sums['honk'])} Honk "
                                       f"= {values.credit_range(estimate.scan_low + sums['honk'][0], estimate.scan_high + sums['honk'][1])}"))
                    continue
                parts = [f"Now {values.credit_range(*body.current())}"]
                if body.is_planet:
                    parts.append(f"Max {values.credit_range(*body.maximum())}")
                if body.bio or body.geo:
                    parts.append(" ".join(x for x in (f"Bio {body.bio}" if body.bio else "", f"Geo {body.geo}" if body.geo else "") if x))
                out.append(("dim", "   " + "   ".join(parts)))
        sums = self.totals()
        out.append(("rule", ""))
        if not self.previously_scanned() and self.fully_scanned_bonus():
            out.append(("dim", f"Fully Scanned Bonus: {values.credits(self.fully_scanned_bonus())}"
                               + ("" if self.all_found else " (when all bodies are found)")))
        if self.planets() and not self.previously_mapped():
            out.append(("dim", f"Fully Mapped Bonus: {values.credits(self.fully_mapped_bonus())} (when every planet is mapped)"))
        if sums["now"] == sums["max"]:
            out.append(("head", f"Estimated System Value (Max): {values.credit_range(*sums['now'])}"))
        else:
            out.append(("head", f"Estimated System Value: {values.credit_range(*sums['now'])}"))
            out.append(("head", f"Maximum System Value: {values.credit_range(*sums['max'])}"))
        return out

    # ---- keeping the last system over a restart
    def save(self, path: str) -> None:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = {"system": self.system, "honked": self.honked, "body_count": self.body_count,
                    "non_body_count": self.non_body_count, "all_found": self.all_found,
                    "bodies": [b.to_dict() for b in self.bodies.values()]}
            with open(path + ".tmp", "w", encoding="utf-8") as handle:
                json.dump(data, handle)
            os.replace(path + ".tmp", path)
        except OSError:
            pass

    def load(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as handle:
                data: Any = json.load(handle)
            self.reset(str(data.get("system") or ""))
            self.honked = bool(data.get("honked"))
            self.body_count = int(data.get("body_count") or 0)
            self.non_body_count = int(data.get("non_body_count") or 0)
            self.all_found = bool(data.get("all_found"))
            for item in data.get("bodies") or ():
                body = Body.from_dict(item)
                self.bodies[body.id] = body
        except (OSError, ValueError, TypeError, AttributeError):
            self.reset("")
