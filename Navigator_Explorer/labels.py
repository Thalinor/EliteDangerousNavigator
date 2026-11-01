# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
#
# Adapted from Pioneer (src/pioneer/util.py), a plugin for EDMC.
# Source: https://github.com/Silarn/EDMC-Pioneer
# Copyright 2024 Jeremy Rimpo. Licensed under the GNU General Public License, version 2 or (at your option) any later
# version; used here under version 3 or later. Changes: no emoji (plain text tags), takes plain journal values instead of
# database objects, a trailing (F) marks a scoopable star like the rest of the suite.
"""Plain-text names and short tags for stars and planets."""
from __future__ import annotations

PLANET_TAGS = {
    "Icy body": "I", "Rocky body": "R", "Rocky ice body": "RI", "Metal rich body": "MR", "High metal content body": "HMC",
    "Earthlike body": "ELW", "Water world": "WW", "Ammonia world": "AW", "Water giant": "G-W",
    "Water giant with life": "G-W-L", "Gas giant with water based life": "G-WL", "Gas giant with ammonia based life": "G-AL",
    "Sudarsky class I gas giant": "G-I", "Sudarsky class II gas giant": "G-II", "Sudarsky class III gas giant": "G-III",
    "Sudarsky class IV gas giant": "G-IV", "Sudarsky class V gas giant": "G-V", "Helium rich gas giant": "G-He+",
    "Helium gas giant": "G-He",
}


SMALL_WORDS = ("of", "the", "and", "with", "a", "an", "in", "on", "to", "for")


def _capital(part: str) -> str:
    if not part or any(ch.isdigit() for ch in part) or (len(part) > 1 and part.isupper()):
        return part                        # K2, II, HMC stay as they are
    return part[0].upper() + part[1:]


def title_case(text: str) -> str:
    """The suite's rule for names: every word capitalised (each part of Yellow-Orange and Ae/Be too), but not the small
    joining words (of, the, and, with...) unless they come first. Sentences are not run through this."""
    words = []
    for index, word in enumerate(text.split(" ")):
        if index and word.lower() in SMALL_WORDS:
            words.append(word.lower())
            continue
        words.append("/".join("-".join(_capital(piece) for piece in part.split("-")) for part in word.split("/")))
    return " ".join(words)


def planet_tag(planet_class: str) -> str:
    return PLANET_TAGS.get(planet_class, "")


def star_label(star_class: str = "", subclass: int = 0, luminosity: str = "", show_descriptors: bool = False) -> str:
    """For example 'Yellow-orange main-sequence star (K2 Va) (F)'."""
    name = "Star"
    star_type = ""
    fuel = False
    if luminosity == "Ia0":
        star_type = "hypergiant"
    elif luminosity.startswith("VI"):
        star_type = "compact"
    elif luminosity.startswith("V"):
        star_type = "main-sequence"
    elif luminosity.startswith("IV"):
        star_type = "subgiant"
    elif luminosity.startswith("III"):
        star_type = "giant"
    elif luminosity.startswith("II"):
        star_type = "bright giant"
    elif luminosity.startswith("I"):
        star_type = "supergiant"

    def dwarf() -> None:
        nonlocal star_type
        if star_type == "main-sequence":
            star_type = "dwarf"
        elif star_type == "compact":
            star_type = "subdwarf"

    if star_class.startswith("D"):
        descriptors, modifier = [], ""
        for letter, text in (("A", "hydrogen-rich"), ("B", "helium-rich"), ("C", "continuous-spectrum"),
                             ("O", "ionized helium"), ("Q", "carbon-rich"), ("Z", "metallic")):
            if letter in star_class:
                descriptors.append(text)
        if "V" in star_class:
            modifier = "variable"
        if "X" in star_class:
            modifier = "atypical"
        name = ("{}{}white dwarf".format(modifier + " " if modifier else "",
                                         ", ".join(descriptors) + " " if descriptors else "")).capitalize()
    elif star_class == "H":
        name, show_descriptors = "black hole", False
    elif star_class == "SupermassiveBlackHole":
        star_class, name, show_descriptors = "H", "supermassive black hole", False
    elif star_class == "N":
        name, show_descriptors = "neutron star", False
    elif star_class == "O":
        name, fuel = "blue {} star", True
    elif star_class in ("B", "B_BlueWhiteSuperGiant"):
        star_class, name, fuel = "B", "blue-white {} star", True
    elif star_class in ("A", "A_BlueWhiteSuperGiant"):
        star_class, name, fuel = "A", "white-blue {} star", True
    elif star_class in ("F", "F_WhiteSuperGiant"):
        star_class, name, fuel = "F", "white {} star", True
    elif star_class in ("G", "G_WhiteSuperGiant"):
        star_class, name, fuel = "G", "white-yellow {} star", True
    elif star_class in ("K", "K_OrangeGiant"):
        star_class, name, fuel = "K", "yellow-orange {} star", True
    elif star_class.startswith("W"):
        descriptor = {"C": "carbon-rich ", "N": "nitrogen and helium-rich ", "NC": "carbon and nitrogen-rich ",
                      "O": "carbon and oxygen-rich "}.get(star_class[1:], "")
        name = "{}Wolf-Rayet {} star".format(descriptor, star_type)
    elif star_class.startswith("C"):
        descriptor = {"N": "deep red ", "J": "carbon-13 rich ", "H": "metal-poor ", "Hd": "hydrogen-poor ",
                      "S": "early-stage ", "R": "red "}.get(star_class[1:], "")
        name = "{}{} carbon star".format(descriptor, star_type).capitalize()
    elif star_class in ("M", "M_RedSuperGiant", "M_RedGiant"):
        star_class = "M"
        dwarf()
        name, fuel = "red {} star", True
    elif star_class == "AeBe":
        dwarf()
        name = "Herbig Ae/Be {} star"
    elif star_class == "TTS":
        name = "T Tauri star"
    elif star_class == "L":
        dwarf()
        name = "dark red {} star"
    elif star_class == "T":
        dwarf()
        name = "methane {} star"
    elif star_class == "Y":
        dwarf()
        name = "brown {} star"
    elif star_class == "MS":
        name = "cooling red {} star"
    elif star_class == "S":
        name = "cool {} star"

    descriptors = ""
    if show_descriptors:
        first, second = luminosity_descriptor(luminosity), subclass_descriptor(subclass)
        descriptors = f"{first}, {second}" if first and second else f"{first}{second}"
    final = name.format(star_type) if "{}" in name else name
    final = title_case(final)
    tail = f" ({star_class}{subclass} {luminosity})".replace("  )", ")").replace(" )", ")")
    return f"{final}{tail}{' (F)' if fuel else ''}" + (f" [{descriptors}]" if descriptors else "")


def luminosity_descriptor(luminosity: str) -> str:
    if luminosity.endswith("ab"):
        return "more bright"
    if luminosity.endswith("a0"):
        return "incredibly bright"
    if luminosity.endswith("a"):
        return "very bright"
    if luminosity.endswith("b"):
        return "dim"
    if luminosity.endswith("z"):
        return "ionized-helium banding"
    return ""


def subclass_descriptor(subclass: int) -> str:
    if subclass == 9:
        return "low-temp"
    if subclass in (7, 8):
        return "cooler-temp"
    if subclass in (4, 5, 6):
        return "average-temp"
    if subclass in (2, 3):
        return "warmer-temp"
    if subclass in (0, 1):
        return "high-temp"
    return ""
