# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Validated deterministic voice macros and their cancellable worker."""
from __future__ import annotations
import copy
import json
import math
import os
from pathlib import Path
import re
import threading
import time
import uuid
from .bindings import PROFILES
from .assistant import defaults as assistant_defaults, validate_options, ship_prefix

STATE_BITS = {"LandingGearToggle": 2, "DeployHardpointToggle": 6,
              "ShipSpotLightToggle": 8, "ToggleCargoScoop": 9, "NightVisionToggle": 28}
CONTEXTS = ("any", "ship", "srv", "onfoot")
CONTROL_PHRASES = ("cancel macro", "stop listening")

def normalise(text):
    return re.sub(r"\s+", " ", text).strip().casefold()

def new_macro(name, phrases, action="", desired=None):
    step = {"type": "action", "binding": action, "hold": .09, "gap": .15, "repeat": 1}
    if desired is not None:
        step["desired"] = desired
    return {"id": uuid.uuid4().hex, "name": name, "phrases": phrases, "enabled": True,
            "context": "ship", "reply": name, "speak_reply": False,
            "steps": [step] if action else []}

def defaults():
    definitions = [
        ("Landing gear down", ["landing gear down", "deploy landing gear"], "LandingGearToggle", True),
        ("Landing gear up", ["landing gear up", "retract landing gear"], "LandingGearToggle", False),
        ("Deploy hardpoints", ["deploy hardpoints", "weapons out"], "DeployHardpointToggle", True),
        ("Stow hardpoints", ["stow hardpoints", "retract hardpoints"], "DeployHardpointToggle", False),
        ("Toggle galaxy map", ["galaxy map", "toggle galaxy map"], "GalaxyMapOpen", None),
        ("Toggle system map", ["system map", "toggle system map"], "SystemMapOpen", None),
        ("Stop ship", ["stop ship", "zero throttle"], "SetSpeedZero", None),
        ("Throttle seventy five", ["seventy five percent", "approach speed"], "SetSpeed75", None),
        ("Night vision on", ["night vision on"], "NightVisionToggle", True),
        ("Night vision off", ["night vision off"], "NightVisionToggle", False),
    ]
    return {"schema": 1, "high_contrast_background": False, "confidence": .72, "wake_word": "", "culture": "",
            "binds_override": "", "bindings_cleared": False,
            "speak_replies": True, "activity_log_enabled": True,
            "listen_status_colors": False, "backup_directory": "", "collapsed": False,
            "tts_voice": "", "tts_rate": 0, "tts_pitch": "normal", "tts_volume": 100,
            "assistant_settings": assistant_defaults(),
            "macros": [new_macro(name, phrases, "ship:" + action, desired)
                       for name, phrases, action, desired in definitions]}

def number(value, minimum, maximum, name):
    if isinstance(value, bool):
        raise ValueError(name + " must be a number")
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(name + " must be a number")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError("%s must be between %s and %s" % (name, minimum, maximum))
    return value

def validate(settings):
    if not isinstance(settings, dict) or settings.get("schema") != 1:
        raise ValueError("This is not a supported Voice Navigator settings file")
    settings.pop("dry_run", None)  # Retire legacy global simulation; Preview remains explicit.
    validate_options(settings)
    number(settings.get("confidence", .72), .1, 1, "Recognition confidence")
    for key, default in (("high_contrast_background", False), ("speak_replies", True),
                         ("activity_log_enabled", True), ("bindings_cleared", False),
                         ("listen_status_colors", False), ("collapsed", False)):
        if not isinstance(settings.get(key, default), bool):
            raise ValueError(key + " must be true or false")
    for key in ("wake_word", "culture", "binds_override", "backup_directory"):
        if not isinstance(settings.get(key, ""), str):
            raise ValueError(key + " must be text")
    if not isinstance(settings.get("tts_voice", ""), str):
        raise ValueError("tts_voice must be text")
    if settings.get("tts_pitch", "normal") not in ("low", "normal", "high"):
        raise ValueError("TTS pitch must be low, normal, or high")
    rate = number(settings.get("tts_rate", 0), -10, 10, "TTS rate")
    volume = number(settings.get("tts_volume", 100), 0, 100, "TTS volume")
    if int(rate) != rate or int(volume) != volume:
        raise ValueError("TTS rate and volume must be whole numbers")
    macros = settings.get("macros")
    if not isinstance(macros, list) or len(macros) > 500:
        raise ValueError("Settings must contain a list of up to 500 macros")
    ids, phrases = set(), set()
    for macro in macros:
        if not isinstance(macro, dict):
            raise ValueError("Each macro must be an object")
        identity = macro.get("id")
        if not isinstance(identity, str) or not identity or identity in ids:
            raise ValueError("Each macro needs a unique ID")
        ids.add(identity)
        if not isinstance(macro.get("name"), str) or not macro["name"].strip():
            raise ValueError("Each macro needs a name")
        if macro.get("context", "any") not in CONTEXTS:
            raise ValueError("Unknown macro context")
        if not isinstance(macro.get("enabled", True), bool):
            raise ValueError("Enabled must be true or false")
        # Older settings files did not have a per-command spoken-reply switch.
        # Keep those commands silent until the user opts them in.
        macro.setdefault("speak_reply", False)
        if not isinstance(macro["speak_reply"], bool):
            raise ValueError("Spoken must be true or false")
        if not isinstance(macro.get("reply", ""), str) or len(macro.get("reply", "")) > 500:
            raise ValueError("A spoken reply must contain at most 500 characters")
        aliases = macro.get("phrases")
        if not isinstance(aliases, list) or not 1 <= len(aliases) <= 40:
            raise ValueError(macro["name"] + ": add between 1 and 40 spoken phrases")
        local = set()
        for phrase in aliases:
            if not isinstance(phrase, str) or not normalise(phrase) or len(phrase) > 150:
                raise ValueError("Each phrase needs between 1 and 150 characters")
            phrase = normalise(phrase)
            if phrase in CONTROL_PHRASES:
                raise ValueError("Reserved control phrase: " + phrase)
            if phrase in local:
                raise ValueError("Repeated phrase: " + phrase)
            local.add(phrase)
            if macro.get("enabled", True):
                if phrase in phrases:
                    raise ValueError("Two enabled commands use the phrase: " + phrase)
                phrases.add(phrase)
        steps = macro.get("steps")
        if not isinstance(steps, list) or not 1 <= len(steps) <= 64:
            raise ValueError(macro["name"] + ": add between 1 and 64 steps")
        duration = 0.
        for step in steps:
            if not isinstance(step, dict):
                raise ValueError("Each step must be an object")
            if step.get("type") == "wait":
                duration += number(step.get("seconds"), 0, 30, "Pause")
            elif step.get("type") == "action":
                binding = step.get("binding")
                if not isinstance(binding, str) or binding.count(":") != 1 or binding.split(":")[0] not in PROFILES:
                    raise ValueError("Choose a preset section and binding for each action")
                hold = number(step.get("hold", .09), .02, 10, "Hold time")
                gap = number(step.get("gap", .15), .02, 5, "Gap")
                repeat = number(step.get("repeat", 1), 1, 20, "Repeat count")
                if int(repeat) != repeat:
                    raise ValueError("Repeat count must be a whole number")
                if step.get("desired") is not None:
                    if not isinstance(step["desired"], bool) or binding.split(":")[1] not in STATE_BITS or repeat != 1:
                        raise ValueError("State checks require a supported toggle and one press")
                duration += (hold + gap) * repeat
            else:
                raise ValueError("Unknown macro step")
        if duration > 180:
            raise ValueError("A macro may last at most three minutes")
    return settings

def phrase_map(settings):
    validate(settings)
    wake = ship_prefix(settings)
    return {((wake + " ") if wake else "") + normalise(phrase): macro
            for macro in settings["macros"] if macro.get("enabled", True) for phrase in macro["phrases"]}

def load_settings(path):
    if not path.exists():
        return defaults(), ""
    try:
        if path.stat().st_size > 2_000_000:
            raise ValueError("Settings file is too large")
        return validate(json.loads(path.read_text(encoding="utf-8-sig"))), ""
    except (OSError, ValueError, TypeError) as error:
        return defaults(), "Settings could not be read; original preserved: " + str(error)

def save_settings(path, settings):
    validate(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()

class GameState:
    def __init__(self):
        self._lock, self._data = threading.Lock(), {}
    def update(self, data):
        with self._lock:
            self._data = dict(data)
    def snapshot(self):
        with self._lock:
            return dict(self._data)
    def clear(self):
        self.update({})
    @staticmethod
    def context(data):
        flags, flags2 = int(data.get("Flags", 0)), int(data.get("Flags2", 0))
        if flags2 & 1:
            return "onfoot"
        if flags & (1 << 26):
            return "srv"
        if flags & ((1 << 24) | (1 << 25)):
            return "ship"
        return "unknown"

class Cancelled(RuntimeError):
    pass

class MacroRunner:
    def __init__(self, sender, state, emit):
        self.sender, self.state, self.emit = sender, state, emit
        self._lock, self._cancel = threading.Lock(), threading.Event()
        self._busy = self._closed = False
        self._thread = None
    @property
    def busy(self):
        with self._lock:
            return self._busy
    def submit(self, macro, catalog, dry_run):
        validate({"schema": 1, "macros": [macro]})
        with self._lock:
            if self._closed or self._busy:
                return False
            self._busy, self._cancel = True, threading.Event()
        self._thread = threading.Thread(target=self._work, args=(
            copy.deepcopy(macro), catalog, dry_run, self._cancel), daemon=True)
        self._thread.start()
        return True
    def cancel(self):
        self._cancel.set()
    def close(self):
        with self._lock:
            self._closed = True
        self.cancel()
    def join(self, timeout=2):
        if self._thread:
            self._thread.join(timeout)
    def _check(self, cancel, dry):
        if cancel.is_set():
            raise Cancelled("Macro cancelled")
        if not dry and not self.sender.is_game_foreground():
            raise Cancelled("Elite lost focus; macro stopped")
    def _wait(self, seconds, cancel, dry):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self._check(cancel, dry)
            cancel.wait(min(.03, max(0., deadline - time.monotonic())))
    def _context(self, macro, dry):
        if not dry and macro.get("context", "any") != "any":
            if self.state.context(self.state.snapshot()) != macro["context"]:
                raise ValueError("This macro requires " + macro["context"] + " controls")
    def _work(self, macro, catalog, dry, cancel):
        try:
            resolved = {s["binding"]: catalog.resolve(s["binding"])
                        for s in macro["steps"] if s["type"] == "action"}
            self._check(cancel, dry)
            self._context(macro, dry)
            self.emit("log", ("DRY RUN: " if dry else "Running: ") + macro["name"])
            for step in macro["steps"]:
                self._check(cancel, dry)
                if step["type"] == "wait":
                    self.emit("log", "Pause " + str(step["seconds"]) + " seconds")
                    self._wait(float(step["seconds"]), cancel, dry)
                    continue
                binding = resolved[step["binding"]]
                desired, bit = step.get("desired"), STATE_BITS.get(binding.action)
                if desired is not None and not dry:
                    data = self.state.snapshot()
                    if "Flags" not in data:
                        raise ValueError("Waiting for Elite ship status before using this toggle")
                    if bool(int(data["Flags"]) & (1 << bit)) == desired:
                        self.emit("log", binding.label + " already has the requested state")
                        continue
                for _ in range(int(step.get("repeat", 1))):
                    self._check(cancel, dry)
                    self._context(macro, dry)
                    self.emit("log", binding.label + " -> " + binding.display)
                    if not dry:
                        self.sender.tap(binding.keys, float(step.get("hold", .09)), cancel)
                    self._wait(float(step.get("gap", .15)), cancel, dry)
                if desired is not None and not dry:
                    deadline = time.monotonic() + 4
                    while time.monotonic() < deadline:
                        self._check(cancel, dry)
                        data = self.state.snapshot()
                        if "Flags" in data and bool(int(data["Flags"]) & (1 << bit)) == desired:
                            break
                        cancel.wait(.05)
                    else:
                        raise ValueError("Key sent, but Elite did not confirm " + binding.label + ". No repeat toggle was sent.")
            self.emit("done", {"name": macro["name"], "reply": macro.get("reply", ""),
                                "speak_reply": macro.get("speak_reply", False), "dry_run": dry})
        except Exception as error:
            self.emit("error", str(error))
        finally:
            with self._lock:
                self._busy = False
