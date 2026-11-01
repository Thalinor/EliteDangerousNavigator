# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Exploration value estimates (credits), written from the community's published formula.

The constants and the formula come from MattG's "Exploration value formulae" forum thread (also the basis of the Economical
Cartographics and Pioneer plugins); this is our own code. Every figure is an estimate: the game does not publish its rules.
The terraform bonus is shown as a range because its exact size is not known.
"""
from __future__ import annotations

from typing import NamedTuple

Q = 0.56591828
FIRST_DISCOVERY = 2.6                 # everything is worth this much more to the first discoverer
MAP_FIRST_BOTH, MAP_FIRST_MAPPER, MAP_PLAIN = 3.699622554, 8.0956, 10 / 3
FLOOR = 500
ODYSSEY_MAP_BONUS, ODYSSEY_MAP_MIN = 0.3, 555

# planet class: (base k, terraform bonus k, share of the bonus still counted at the low end of the range)
PLANET_K = {
    "Metal rich body": (21790, 0, 1.0),
    "Ammonia world": (96932, 0, 1.0),
    "Sudarsky class I gas giant": (1656, 0, 1.0),
    "Sudarsky class II gas giant": (9654, 0, 1.0),
    "High metal content body": (9654, 100677, 0.9),
    "Water world": (64831, 116295, 0.75),
    "Earthlike body": (64831, 116295, 1.0),
}
DEFAULT_K = (300, 93328, 0.9)         # rocky, icy, rocky ice and the rest

CLASS_SHORT = {
    "Metal rich body": "Metal rich", "Ammonia world": "Ammonia world", "High metal content body": "High metal content",
    "Water world": "Water world", "Earthlike body": "Earth-like world", "Rocky body": "Rocky", "Icy body": "Icy",
    "Rocky ice body": "Rocky ice", "Sudarsky class I gas giant": "Gas giant I", "Sudarsky class II gas giant": "Gas giant II",
    "Sudarsky class III gas giant": "Gas giant III", "Sudarsky class IV gas giant": "Gas giant IV",
    "Sudarsky class V gas giant": "Gas giant V", "Water giant": "Water giant", "Gas giant with water based life":
    "Gas giant (water life)", "Gas giant with ammonia based life": "Gas giant (ammonia life)", "Helium rich gas giant":
    "Helium gas giant", "Helium gas giant": "Helium gas giant",
}


class Estimate(NamedTuple):
    """Low and high credit figures for one body: scanned only, mapped, and the honk (discovery scan) share."""
    scan_low: int
    scan_high: int
    map_low: int
    map_high: int
    honk_low: int
    honk_high: int


def star_k(star_type: str) -> int:
    if star_type in ("N", "H"):
        return 22628
    if star_type.startswith("D"):
        return 14057
    return 1200


def star_value(star_type: str, mass: float, first_discoverer: bool) -> tuple[int, int]:
    """Returns (scan value, honk share)."""
    value = star_k(star_type) * (1 + mass / 66.25)
    honk = value / 3
    if first_discoverer:
        value, honk = value * FIRST_DISCOVERY, honk * FIRST_DISCOVERY
    return round(value), round(honk)


def class_constants(planet_class: str, terraform_state: str) -> tuple[int, int, float]:
    """(k, terraform k, low-end share) after applying the terraform state."""
    base, bonus, low_share = PLANET_K.get(planet_class, DEFAULT_K)
    natural_earthlike = planet_class == "Earthlike body" and not terraform_state
    if terraform_state == "Terraformable":
        return base, bonus, low_share if planet_class != "Earthlike body" else 0.0
    if natural_earthlike:
        return base, bonus, 1.0
    return base, 0, 1.0                # terraformed, or no terraforming for this class


def body_estimate(planet_class: str, terraform_state: str, mass: float, first_discoverer: bool,
                  first_mapper: bool, current_game: bool = True) -> Estimate:
    base, bonus, low_share = class_constants(planet_class, terraform_state)
    if first_discoverer and first_mapper:
        multiplier = MAP_FIRST_BOTH
    elif first_mapper:
        multiplier = MAP_FIRST_MAPPER
    else:
        multiplier = MAP_PLAIN
    mass_term = Q * max(mass, 0.0) ** 0.2
    figures = []
    for k in (base + bonus * low_share, base + bonus):
        scan = k * (1 + mass_term)
        mapped = scan * multiplier
        if current_game:
            mapped += max(mapped * ODYSSEY_MAP_BONUS, ODYSSEY_MAP_MIN)
        honk = scan / 3
        figures.append([max(scan, FLOOR), max(mapped, FLOOR), max(honk, FLOOR)])
    if first_discoverer:
        figures = [[v * FIRST_DISCOVERY for v in row] for row in figures]
    (s0, m0, h0), (s1, m1, h1) = figures
    return Estimate(round(s0), round(s1), round(m0), round(m1), round(h0), round(h1))


def credits(value: float) -> str:
    """12,345 -> 12.3 kCr; 2,950,000 -> 2.9 MCr (the same short forms Pioneer uses)."""
    value = round(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f} MCr"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f} kCr"
    return f"{value} Cr"


def credit_range(low: float, high: float) -> str:
    return credits(low) if credits(low) == credits(high) else f"{credits(low)} - {credits(high)}"
