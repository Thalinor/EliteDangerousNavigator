# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Read Elite control presets without changing them."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import os
import re
import xml.etree.ElementTree as ET

PROFILES = ("general", "ship", "srv", "onfoot")
PROFILE_NAMES = dict(zip(PROFILES, ("General", "Ship", "SRV", "On Foot")))

@dataclass(frozen=True)
class Key:
    scan: int
    extended: bool = False
    name: str = ""

_CODES = {
    "escape": (1, False), "minus": (12, False), "equals": (13, False),
    "backspace": (14, False), "tab": (15, False),
    "leftbracket": (26, False), "rightbracket": (27, False),
    "enter": (28, False), "return": (28, False), "leftcontrol": (29, False),
    "semicolon": (39, False), "apostrophe": (40, False), "grave": (41, False),
    "leftshift": (42, False), "backslash": (43, False), "comma": (51, False),
    "period": (52, False), "slash": (53, False), "rightshift": (54, False),
    "numpadmultiply": (55, False), "multiply": (55, False),
    "leftalt": (56, False), "space": (57, False), "capslock": (58, False),
    "numlock": (69, False), "scrolllock": (70, False),
    "numpadsubtract": (74, False), "numpadadd": (78, False),
    "numpaddecimal": (83, False), "oem102": (86, False),
    "f11": (87, False), "f12": (88, False),
    "numpadenter": (28, True), "rightcontrol": (29, True),
    "numpaddivide": (53, True), "rightalt": (56, True),
    "home": (71, True), "uparrow": (72, True), "pageup": (73, True),
    "leftarrow": (75, True), "rightarrow": (77, True), "end": (79, True),
    "downarrow": (80, True), "pagedown": (81, True), "insert": (82, True),
    "delete": (83, True), "leftwin": (91, True), "rightwin": (92, True),
    "apps": (93, True),
}
for chars, start in (("1234567890", 2), ("qwertyuiop", 16), ("asdfghjkl", 30), ("zxcvbnm", 44)):
    _CODES.update({char: (start + i, False) for i, char in enumerate(chars)})
_CODES.update({"f" + str(i): (58 + i, False) for i in range(1, 11)})
_CODES.update({"numpad" + char: (code, False)
               for char, code in zip("7894561230", (71, 72, 73, 75, 76, 77, 79, 80, 81, 82))})

def key_code(name):
    normal = re.sub(r"[^a-z0-9]", "", name.lower())
    normal = normal[3:] if normal.startswith("key") else normal
    code = _CODES.get(normal)
    return Key(code[0], code[1], name.removeprefix("Key_")) if code else None

_LABELS = {
    "LandingGearToggle": "Landing Gear", "DeployHardpointToggle": "Hardpoints",
    "ShipSpotLightToggle": "Ship Lights", "NightVisionToggle": "Night Vision",
    "ToggleCargoScoop": "Cargo Scoop", "GalaxyMapOpen": "Galaxy Map",
    "SystemMapOpen": "System Map", "SetSpeedZero": "Throttle Zero",
    "SetSpeed75": "Throttle 75%", "SetSpeed100": "Throttle 100%",
    "UseBoostJuice": "Boost", "HyperSuperCombination": "Frame Shift Drive",
    "ExplorationFSSEnter": "Full Spectrum Scanner",
}

def action_label(name):
    return _LABELS.get(name, re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).replace("_", " "))

@dataclass(frozen=True)
class Binding:
    action: str
    profile: str
    keys: tuple[Key, ...]
    source: str
    slot: str = ""
    reason: str = ""
    @property
    def identifier(self):
        return self.profile + ":" + self.action
    @property
    def label(self):
        return action_label(self.action)
    @property
    def display(self):
        return " + ".join(key.name for key in self.keys) if self.keys else self.reason

def keyboard_binding(node):
    problems = []
    for slot_name in ("Primary", "Secondary"):
        slot = node.find(slot_name)
        if slot is None or slot.get("Device") != "Keyboard":
            continue
        keys = []
        for modifier in slot.findall("Modifier"):
            key = key_code(modifier.get("Key", "")) if modifier.get("Device") == "Keyboard" else None
            if key is None:
                problems.append("Unsupported modifier: " + modifier.get("Key", modifier.get("Device", "")))
                break
            if not any((key.scan, key.extended) == (k.scan, k.extended) for k in keys):
                keys.append(key)
        else:
            key = key_code(slot.get("Key", ""))
            if key is not None:
                if any((key.scan, key.extended) == (k.scan, k.extended) for k in keys):
                    problems.append("Main key is also a modifier")
                    continue
                return tuple(keys + [key]), slot_name, ""
            problems.append("Unsupported key: " + slot.get("Key", ""))
    return (), "", "; ".join(problems) or "No keyboard binding"

def default_bindings_dir():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Frontier Developments" / "Elite Dangerous" / "Options" / "Bindings"

def version_key(path):
    match = re.search(r"\.(\d+(?:\.\d+)*)\.(?:binds|start)$", path.name, re.I)
    return tuple(map(int, match.group(1).split("."))) if match else (0,)

class BindingCatalog:
    def __init__(self):
        self.bindings, self.sources, self.warnings = {}, {}, []
    def reload(self, directory=None, override=""):
        base = Path(directory) if directory else default_bindings_dir()
        self.bindings, self.sources, self.warnings = {}, {}, []
        if override:
            files = {profile: Path(override) for profile in PROFILES}
        else:
            starts = list(base.glob("StartPreset*.start")) if base.is_dir() else []
            starts.sort(key=lambda p: (version_key(p), p.stat().st_mtime), reverse=True)
            presets = starts[0].read_text(encoding="utf-8-sig").splitlines() if starts else []
            presets = [p.strip() for p in presets]
            if len(presets) == 1:
                presets *= 4
            if not presets:
                available = list(base.glob("*.binds")) if base.is_dir() else []
                available.sort(key=lambda p: (p.stat().st_mtime, version_key(p)), reverse=True)
                if not available:
                    self.warnings.append("No .binds files found. Save custom controls in Elite or choose a file.")
                    return
                files = dict.fromkeys(PROFILES, available[0])
                self.warnings.append("No active preset file; using " + available[0].name)
            else:
                files = {}
                for index, profile in enumerate(PROFILES):
                    preset = presets[index] if index < len(presets) else ""
                    if not preset or any(c in preset for c in ("/", "\\", ":")) or preset in (".", ".."):
                        self.warnings.append(PROFILE_NAMES[profile] + ": no valid selected preset")
                        continue
                    candidates = [p for p in base.glob("*.binds") if re.fullmatch(
                        re.escape(preset) + r"(?:\.\d+(?:\.\d+)*)?", p.stem, re.I)]
                    candidates.sort(key=lambda p: (version_key(p), p.stat().st_mtime), reverse=True)
                    if candidates:
                        files[profile] = candidates[0]
                    else:
                        self.warnings.append(PROFILE_NAMES[profile] + ": preset " + preset + " not found; choose its .binds file.")
        parsed = {}
        for profile, path in files.items():
            try:
                if path not in parsed:
                    if path.stat().st_size > 5_000_000:
                        raise ValueError("Binding file is unexpectedly large")
                    parsed[path] = ET.parse(path).getroot()
                self.sources[profile] = str(path)
                for node in parsed[path]:
                    if node.find("Primary") is None and node.find("Secondary") is None:
                        continue
                    keys, slot, reason = keyboard_binding(node)
                    binding = Binding(node.tag, profile, keys, str(path), slot, reason)
                    self.bindings[binding.identifier] = binding
            except (OSError, ET.ParseError, ValueError) as error:
                self.warnings.append(PROFILE_NAMES[profile] + ": " + str(error))
    def resolve(self, identifier):
        binding = self.bindings.get(identifier)
        if binding is None:
            raise ValueError("Action not found: " + identifier)
        if not binding.keys:
            raise ValueError(binding.label + ": " + binding.reason + ". Assign a keyboard binding in Elite.")
        return binding
    def rows(self, profile, query=""):
        query = query.casefold()
        return sorted((b for b in self.bindings.values() if b.profile == profile and
                       query in (b.action + " " + b.label + " " + b.display).casefold()),
                      key=lambda b: b.label.casefold())
