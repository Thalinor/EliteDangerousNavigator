# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Galaxy-map engine for the Navigator suite (Windows): key and mouse input, finding and focusing the
game, the Elite key bindings, opening and closing the map, and the one-time click training.

Ported from the Neutron Highway Auto edition so every plugin shares one copy. It only searches and
clicks inside Elite's galaxy map when the commander asks (never ship controls). The search recipes
(select or plot a name) are added later; until then ``ready()`` is False and requests just copy.
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import sys
import threading
import time
import xml.etree.ElementTree as ET
from ctypes import wintypes
from typing import Any, Callable

GAME_TITLE = "Elite - Dangerous (CLIENT)"
SC_ESC, SC_M = 0x01, 0x32
WINDOWS = sys.platform == "win32"
_user32 = ctypes.windll.user32 if WINDOWS else None

ROUTING_STEPS = (
    ("search_box", "Hover over the SEARCH BOX"),
    ("first_result", "Search a system, then hover over the first RESULT"),
    ("plot_button", "Click that result, then hover over PLOT ROUTE"),
)
JETCONE_STEPS = (
    ("jetcone_tab", "Hover over the ROUTE SETTINGS panel tab"),
    ("jetcone_toggle", "Click that tab, then hover over the JET-CONE BOOST toggle (don't click it)"),
)
POINT_LABELS = {"search_box": "Search box", "first_result": "First result", "plot_button": "Plot Route button",
                "jetcone_tab": "Route settings tab", "jetcone_toggle": "Jet-cone boost toggle"}

DEFAULTS: dict[str, Any] = {
    "map_scancode": SC_M,        # Galaxy Map key (read from the Elite binds)
    "map_modifiers": [],
    "map_key_name": "M",
    "binds_path": "",            # set when a bindings file is picked by hand
    "calibrate_countdown": 15,   # seconds per training step
    "map_open_delay": 2.0,
    "settings_version": 2,       # 2: Esc presses raised 3 -> 6 (nested panels each eat one press)
    "esc_presses": 6,            # most Esc presses to back out of the map (stops once closed)
    "esc_gap": 0.8,
    "click_extra_delay": 0.5,    # extra pause after every click
    "step_delay": 0.8,
    "map_scroll_delay": 2.0,     # extra wait after selecting the system, while the map pans
    "plot_route_delay": 1.0,     # extra wait after the Plot Route click (long plots need time)
    "input_method": "paste",     # "paste" (Ctrl+V; worked in testing) or "type" (key by key)
    "type_delay": 0.05,          # seconds per key while typing
    # Fractions of the game client area. Guesses until trained: see "trained".
    "search_box": [0.17, 0.12],
    "first_result": [0.17, 0.20],
    "plot_button": [0.80, 0.82],
    "jetcone_tab": None,
    "jetcone_toggle": None,
    "trained": [],               # names of the click points the commander has trained
}

if WINDOWS:
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


def key_scancode(name: str) -> int | None:
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    key = key[3:] if key.startswith("key") else key
    return _KEY_SCANCODES.get(key)


def _keyboard_binding(node: Any) -> tuple[int, list[int], str] | None:
    if node is None:
        return None
    for slot in ("Primary", "Secondary"):
        binding = node.find(slot)
        if binding is None or binding.get("Device") != "Keyboard":
            continue
        scan = key_scancode(binding.get("Key", ""))
        modifiers: list[int] | None = []
        names: list[str] = []
        for modifier in binding.findall("Modifier"):
            code = key_scancode(modifier.get("Key", "")) if modifier.get("Device") == "Keyboard" else None
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


def parse_map_binding(path: str) -> tuple[int, list[int], str] | None:
    """The Galaxy Map keyboard binding from an Elite .binds file (None if it has none)."""
    return _keyboard_binding(ET.parse(path).getroot().find("GalaxyMapOpen"))


def bindings_dir() -> str:
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                        "Frontier Developments", "Elite Dangerous", "Options", "Bindings")


def find_binds_file() -> str | None:
    base = bindings_dir()
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


class MapEngine:
    ROUTING_STEPS = ROUTING_STEPS
    JETCONE_STEPS = JETCONE_STEPS
    POINT_LABELS = POINT_LABELS

    @staticmethod
    def bindings_dir() -> str:
        return bindings_dir()

    def __init__(self, root: Any, config: Any, logger: Any, data_dir: str | None = None) -> None:
        self.root = root
        self.config = config
        self.logger = logger
        app_dir = ""
        try:
            app_dir = os.fspath(getattr(config, "app_dir_path", None) or config.app_dir)
        except (AttributeError, TypeError):
            pass
        app_dir = app_dir or os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                                          "EDMarketConnector")
        self.app_dir = app_dir
        self.data_dir = data_dir or os.path.join(app_dir, "NavInterfaceMapMacros")
        self.path = os.path.join(self.data_dir, "map_macros.json")
        self.settings: dict[str, Any] = dict(DEFAULTS)
        self.lock = threading.Lock()          # one map action at a time
        self.last_message = ""                # what the last map macro did, for plugins that show it
        self._train: dict[str, Any] = {}
        self.load()

    # ------------------------------------------------------------------ settings
    def load(self) -> None:
        self.settings = dict(DEFAULTS)
        saved = self._read(self.path)
        if saved is not None:
            self.settings.update({k: v for k, v in saved.items() if k in DEFAULTS})
            if int(saved.get("settings_version", 1)) < 2:
                # Closing the map after route-settings clicks needs more than 3 Esc presses (each open
                # panel takes one); it still stops the moment the game reports the cockpit.
                self.settings["esc_presses"] = max(int(self.settings.get("esc_presses", 6)), 6)
                self.settings["settings_version"] = 2
                self.save()
            return
        imported = self._import_earlier()
        if imported is not None:
            self.settings.update({k: v for k, v in imported.items() if k in DEFAULTS})
            self.settings["esc_presses"] = max(int(self.settings.get("esc_presses", 6)), 6)
            self.settings["settings_version"] = 2
            self.save()
            return
        self.refresh_keybinding()      # first run: take the map key from the Elite binds

    def _read(self, path: str) -> dict | None:
        try:
            with open(path, encoding="utf-8-sig") as stream:
                data = json.load(stream)
            return data if isinstance(data, dict) else None
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            self.logger.exception("Could not read %s", path)
            return None

    def _import_earlier(self) -> dict | None:
        """One-time, read-only copy of the click positions and map key trained in the Neutron Highway
        Auto edition, so nobody has to train again. The earlier file is never changed."""
        for folder in ("NeutronHighwayNavigatorAuto", "CockpitCompanion"):
            earlier = self._read(os.path.join(self.app_dir, folder, "automation.json"))
            if earlier is None:
                continue
            imported = {k: v for k, v in earlier.items() if k in DEFAULTS and k != "trained"}
            imported["trained"] = [name for name in POINT_LABELS
                                   if earlier.get(name) and earlier.get(name) != DEFAULTS[name]]
            return imported
        return None

    def save(self) -> bool:
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as stream:
                json.dump(self.settings, stream, indent=2)
            return True
        except OSError:
            self.logger.exception("Could not save map macro settings to %s", self.path)
            return False

    def ready(self, select_only: bool = True) -> bool:
        """True when this recipe can run: Windows, and the clicks it needs are trained (the search box
        to select a name; also the Plot Route button to plot one)."""
        if not WINDOWS:
            return False
        needed = ("search_box",) if select_only else ("search_box", "plot_button")
        return all(self.trained(name) for name in needed)

    def trained(self, name: str) -> bool:
        return name in (self.settings.get("trained") or [])

    # ------------------------------------------------------------------ key bindings
    def apply_binds(self, path: str) -> str | None:
        """Take the Galaxy Map key from a binds file; the key's name, or None if it has no key."""
        result = parse_map_binding(path)
        if result is None:
            return None
        scan, modifiers, name = result
        self.settings.update({"map_scancode": scan, "map_modifiers": modifiers, "map_key_name": name})
        return name

    def refresh_keybinding(self) -> str | None:
        path = self.settings.get("binds_path") or find_binds_file()
        if not path or not os.path.isfile(path):
            return None
        try:
            name = self.apply_binds(path)
        except (OSError, ET.ParseError):
            self.logger.exception("Could not read keybindings from %s", path)
            return None
        if name:
            self.logger.info("Keys from %s: galaxy map %s", path, name)
            self.save()
        return name

    # ------------------------------------------------------------------ input
    def _send(self, inputs: list) -> None:
        array = (_INPUT * len(inputs))(*inputs)
        _user32.SendInput(len(inputs), array, ctypes.sizeof(_INPUT))

    @staticmethod
    def _key_event(scan: int, up: bool) -> Any:
        flags = 0x0008 | (0x0002 if up else 0)  # KEYEVENTF_SCANCODE [| KEYUP]
        return _INPUT(1, _INPUTUNION(ki=_KEYBDINPUT(0, scan, flags, 0, 0)))

    def tap(self, scan: int, hold: float = 0.07, gap: float = 0.08) -> None:
        self._send([self._key_event(scan, False)])
        time.sleep(hold)
        self._send([self._key_event(scan, True)])
        time.sleep(gap)

    def press_combo(self, scancode: int, modifiers: list) -> None:
        held = [int(code) for code in modifiers or []]
        for code in held:
            self._send([self._key_event(code, False)])
            time.sleep(0.05)
        self.tap(int(scancode))
        for code in reversed(held):
            self._send([self._key_event(code, True)])
            time.sleep(0.05)

    def press_map_key(self) -> None:
        self.press_combo(self.settings["map_scancode"], self.settings.get("map_modifiers"))

    # ------------------------------------------------------------------ the game window
    def find_game(self) -> int:
        return int(_user32.FindWindowW(None, GAME_TITLE) or 0) if _user32 else 0

    def client_rect(self, hwnd: int) -> tuple[int, int, int, int]:
        rect, origin = wintypes.RECT(), wintypes.POINT(0, 0)
        _user32.GetClientRect(hwnd, ctypes.byref(rect))
        _user32.ClientToScreen(hwnd, ctypes.byref(origin))
        return origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top

    def focus_game(self, hwnd: int) -> bool:
        if _user32.IsIconic(hwnd):
            _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        _user32.SetForegroundWindow(hwnd)
        for _ in range(20):
            if _user32.GetForegroundWindow() == hwnd:
                return True
            time.sleep(0.1)
        return False

    def cursor_pos(self) -> tuple[int, int]:
        point = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(point))
        return point.x, point.y

    def status_path(self) -> str | None:
        """Elite's Status.json (EDMC's journal folder first, then the default)."""
        candidates = []
        try:
            journal = self.config.get_str("journaldir") or getattr(self.config, "default_journal_dir", "")
            if journal:
                candidates.append(os.path.join(os.fspath(journal), "Status.json"))
        except Exception:
            pass
        home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        candidates.append(os.path.join(home, "Saved Games", "Frontier Developments", "Elite Dangerous",
                                       "Status.json"))
        return next((path for path in candidates if os.path.isfile(path)), None)

    def gui_focus(self) -> int | None:
        """The screen the game reports right now (6 = galaxy map, 0 = cockpit); None if unreadable."""
        path = self.status_path()
        if not path:
            return None
        for _ in range(3):
            try:
                with open(path, encoding="utf-8") as stream:
                    return int(json.load(stream).get("GuiFocus") or 0)
            except (OSError, ValueError, TypeError, AttributeError):
                time.sleep(0.05)
        return None

    def close_map(self) -> None:
        """Back out of the map with Esc, stopping as soon as the game reports the cockpit (0) so a
        spare press never opens the system menu."""
        # Status.json can lag a moment behind the game, so after each Esc wait (up to ~2 s) for the
        # cockpit to show before pressing again; a second press while it still looks "open" would hit
        # the pause menu.
        polls = max(10, int(max(float(self.settings.get("esc_gap", 0.8)), 2.0) / 0.1))
        for _ in range(int(self.settings.get("esc_presses", 6))):
            if self.gui_focus() == 0:
                break
            self.tap(SC_ESC)
            for _ in range(polls):
                time.sleep(0.1)
                if self.gui_focus() == 0:
                    break
            else:
                continue              # still not the cockpit after the wait: press Esc again
            break
        self.logger.info("Leaving the map: GuiFocus=%s afterwards", self.gui_focus())

    # ------------------------------------------------------------------ recipes
    def chord(self, modifier: int, scan: int) -> None:
        self._send([self._key_event(modifier, False)])
        time.sleep(0.08)
        self.tap(scan)
        self._send([self._key_event(modifier, True)])
        time.sleep(0.08)

    def click_fraction(self, hwnd: int, point: list[float]) -> None:
        left, top, width, height = self.client_rect(hwnd)
        x, y = int(left + point[0] * width), int(top + point[1] * height)
        _user32.SetCursorPos(x - 3, y - 3)   # move in steps so the game registers hover
        time.sleep(0.08)
        _user32.SetCursorPos(x, y)
        time.sleep(0.15)
        self._send([_INPUT(0, _INPUTUNION(mi=_MOUSEINPUT(0, 0, 0, 0x0002, 0, 0)))])  # left down
        time.sleep(0.08)
        self._send([_INPUT(0, _INPUTUNION(mi=_MOUSEINPUT(0, 0, 0, 0x0004, 0, 0)))])  # left up
        time.sleep(0.1 + float(self.settings.get("click_extra_delay", 0.5)))

    def type_text(self, text: str, delay: float) -> None:
        """Type text key by key, using the active keyboard layout's scan codes."""
        _user32.GetKeyboardLayout.restype = ctypes.c_void_p
        _user32.VkKeyScanExW.argtypes = [wintypes.WCHAR, ctypes.c_void_p]
        _user32.VkKeyScanExW.restype = ctypes.c_short
        _user32.MapVirtualKeyExW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p]
        _user32.MapVirtualKeyExW.restype = wintypes.UINT
        layout = _user32.GetKeyboardLayout(0)
        for char in text:
            result = _user32.VkKeyScanExW(char, layout)
            if result == -1:
                self.logger.warning("No key for character %r; skipped", char)
                continue
            vk, shift = result & 0xFF, bool(result & 0x100)
            scan = _user32.MapVirtualKeyExW(vk, 0, layout)  # MAPVK_VK_TO_VSC
            if shift:
                self._send([self._key_event(0x2A, False)])
                time.sleep(0.03)
            self.tap(scan, hold=delay, gap=delay)
            if shift:
                self._send([self._key_event(0x2A, True)])
                time.sleep(0.03)

    def open_map(self, label: str) -> None:
        """Open the galaxy map unless it is already open."""
        if self.gui_focus() == 6:
            self.logger.info("%s: galaxy map already open, not pressing the map key", label)
            return
        self.press_map_key()
        for _ in range(40):                  # wait up to ~4 s for the game to report the map
            if self.gui_focus() == 6:
                break
            time.sleep(0.1)
        self.logger.info("%s: after the map key, GuiFocus=%s", label, self.gui_focus())
        time.sleep(float(self.settings["map_open_delay"]))

    def navroute_destination(self) -> str | None:
        """Where the game's plotted route ends (NavRoute.json), or None if there is no route."""
        status = self.status_path()
        if not status:
            return None
        try:
            with open(os.path.join(os.path.dirname(status), "NavRoute.json"), encoding="utf-8") as stream:
                route = json.load(stream).get("Route") or []
        except (OSError, ValueError, AttributeError):
            return None
        names = [str(item.get("StarSystem") or "") for item in route if isinstance(item, dict)]
        return names[-1] if len(names) >= 2 else None

    def goto(self, name: str, select_only: bool = True) -> bool:
        """Search ``name`` in the galaxy map and select it (``select_only``) or also click Plot Route.
        The caller has already put ``name`` on the clipboard. Runs on its own thread; True if started
        (False: not ready, or not on Windows). Never sends ship controls."""
        if not self.ready(select_only):
            return False
        if not select_only and (self.navroute_destination() or "").casefold() == name.casefold():
            # Plot Route on a destination that is already plotted makes Elite remove the route.
            self.last_message = f"Route to {name} is already plotted."
            self.logger.info("Map macro: %s already plotted; not plotting it again", name)
            return True
        if not self.lock.acquire(blocking=False):
            self.last_message = "Busy - try again in a moment."
            return True
        threading.Thread(target=self._recipe, args=(name, select_only), daemon=True).start()
        return True

    def _recipe(self, name: str, select_only: bool) -> None:
        settings = self.settings
        try:
            hwnd = self.find_game()
            if not hwnd:
                self.last_message = "Elite window not found."
                return
            if not self.focus_game(hwnd):
                self.last_message = "Could not focus Elite."
                return
            step = float(settings["step_delay"])
            self.last_message = "Searching the galaxy map…"
            self.open_map("Select" if select_only else "Plot")
            self.click_fraction(hwnd, settings["search_box"])
            time.sleep(0.3)
            self.chord(0x1D, 0x1E)        # Ctrl+A: select any previous search text
            self.tap(0x0E)                # Backspace deletes the selection
            if settings.get("input_method") == "paste":
                self.chord(0x1D, 0x2F)    # Ctrl+V: the name is already on the clipboard
            else:
                self.type_text(name, float(settings.get("type_delay", 0.05)))
            self.logger.info("Galaxy map macro entered %r via %s", name, settings.get("input_method"))
            time.sleep(0.4)
            self.tap(0x1C)                # Enter
            time.sleep(step + 0.4)        # wait for results
            if settings.get("first_result"):
                self.click_fraction(hwnd, settings["first_result"])
                time.sleep(step + float(settings.get("map_scroll_delay", 2.0)))
            if select_only:
                self.last_message = "Selected in the galaxy map."
                return                    # leave the map open on the result
            self.click_fraction(hwnd, settings["plot_button"])
            time.sleep(step + float(settings.get("plot_route_delay", 1.0)))
            self.close_map()
            for _ in range(25):           # up to ~5 s for the game to write the route
                if (self.navroute_destination() or "").casefold() == name.casefold():
                    self.last_message = "Route plotted."
                    return
                time.sleep(0.2)
            self.last_message = f"Plot not confirmed - the game shows no route to {name}."
        except Exception:
            self.logger.exception("Galaxy map macro failed")
            self.last_message = "Map macro failed - see the EDMC log."
        finally:
            self.lock.release()

    # ------------------------------------------------------------------ training
    def start_training(self, steps: tuple, status: Callable[[str], None],
                       finished: Callable[[str], None]) -> bool:
        """Walk through ``steps``: open the map, then for each step wait the countdown while the
        commander hovers over the control, and record where the cursor is. ``status`` gets progress
        text; ``finished`` gets the final message (on the Tk thread)."""
        if not WINDOWS:
            status("Map shortcuts need Windows.")
            return False
        if not self.lock.acquire(blocking=False):
            status("Busy - try again in a moment.")
            return False
        self._train = {"step": 0, "left": 0, "ready": False, "error": "", "missed": [], "steps": steps,
                       "status": status, "finished": finished, "cancel": False, "active": True}
        status("Opening the galaxy map…")
        threading.Thread(target=self._train_open_map, daemon=True).start()
        self._after(200, self._train_wait)
        return True

    def cancel_training(self) -> None:
        if self._train:
            self._train["cancel"] = True

    def training_active(self) -> bool:
        return bool(self._train.get("active"))

    def _after(self, delay_ms: int, function: Callable[[], None]) -> None:
        try:
            self.root.after(delay_ms, function)
        except Exception:        # window closing, or the Tk thread is already gone
            pass

    def _train_open_map(self) -> None:
        train = self._train
        try:
            hwnd = self.find_game()
            focus = self.gui_focus() if hwnd else None
            if not hwnd:
                train["error"] = "Elite is not running (its window was not found). Start the game first."
            elif not self.focus_game(hwnd):
                train["error"] = "Could not focus Elite."
            elif focus is None:
                train["error"] = "Could not read the game's screen (Status.json). Is the game at the cockpit?"
            elif focus == 0:
                self.press_map_key()
                for _ in range(40):          # wait up to ~4 s for the game to report the map
                    if self.gui_focus() == 6:
                        break
                    time.sleep(0.1)
                time.sleep(float(self.settings["map_open_delay"]))
                if self.gui_focus() != 6:
                    train["error"] = "The map did not open - check the map key."
            elif focus != 6:
                train["error"] = "Return to the cockpit view first."
        except Exception as error:
            self.logger.exception("Could not open the galaxy map for training")
            train["error"] = f"Could not open the map: {type(error).__name__}: {error}"
        train["ready"] = True

    def _train_wait(self) -> None:
        train = self._train
        if not train["ready"]:
            self._after(200, self._train_wait)
            return
        if train["error"]:
            self._train_finish(str(train["error"]), close_map=False)
            return
        train["left"] = int(self.settings.get("calibrate_countdown", 15))
        self._train_tick()

    def _train_tick(self) -> None:
        train = self._train
        if train["cancel"]:
            self._train_finish("Training cancelled.", close_map=True)
            return
        step, steps = train["step"], train["steps"]
        if step >= len(steps):
            if self.save():
                missed = train["missed"]
                self._train_finish("Training saved." if not missed else
                                   f"Saved, but missed: {', '.join(missed)}. Try again.", close_map=True)
            else:
                self._train_finish("Could not save the training - see the EDMC log.", close_map=True)
            return
        key, label = steps[step]
        if train["left"] > 0:
            train["status"](f"{step + 1}/{len(steps)}: {label} ({train['left']}s)")
            train["left"] -= 1
            self._after(1000, self._train_tick)
            return
        hwnd = self.find_game()
        if not hwnd:
            self._train_finish("Elite window not found.", close_map=False)
            return
        left, top, width, height = self.client_rect(hwnd)
        x, y = self.cursor_pos()
        fx, fy = (x - left) / width, (y - top) / height
        if 0 <= fx <= 1 and 0 <= fy <= 1:
            self.settings[key] = [round(fx, 4), round(fy, 4)]
            self.settings["trained"] = sorted(set(self.settings.get("trained") or []) | {key})
        else:
            train["missed"].append(key.replace("_", " "))
        train["step"] += 1
        train["left"] = int(self.settings.get("calibrate_countdown", 15))
        self._train_tick()

    def _train_finish(self, message: str, close_map: bool) -> None:
        train = self._train
        train["status"](message)

        def worker() -> None:
            try:
                if close_map:
                    self.close_map()
            except Exception:
                self.logger.exception("Could not close the galaxy map after training")
            finally:
                train["active"] = False
                self.lock.release()
                self._after(0, lambda: train["finished"](message))

        threading.Thread(target=worker, daemon=True).start()
