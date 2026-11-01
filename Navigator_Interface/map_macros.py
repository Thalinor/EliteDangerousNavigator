# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Shared map-macro service for the Navigator suite (framework).

Plugins call (N) Interface when the commander clicks a name and place the small mode button beside
their collapse button. Everything is off by default. The galaxy-map engine (keys, clicks, training)
is added later and plugs in as ``MapMacros.engine``; until a trained engine exists every request is a
plain copy to the clipboard, which is what a click did before.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import tkinter as tk
from pathlib import Path
from typing import Any


def _sibling(name: str) -> Any:
    """A module next to this one, whether Interface was loaded as a package or straight from load.py."""
    if __package__:
        return importlib.import_module("." + name, __package__)
    key = "_navigator_interface_" + name          # the same key load.py's helper loader uses
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, Path(__file__).with_name(name + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


CFG_ENABLED = "NavInterface_MapMacros"         # master switch, off by default
CFG_LINK = "NavInterface_MapLinkAll"           # one toggle controls every plugin's button
CFG_MODE = "NavInterface_MapMode_"             # + plugin folder: "copy" or "map"

COPY_TEXT = "⧉"          # copy mode
MAP_TEXT = "A"           # auto-map mode
MAP_COLOUR = "#33cc33"   # green while a click will go into the map
MATCH_OPTIONS = ("font", "padx", "pady", "borderwidth", "highlightthickness")


class MapMacros:
    def __init__(self, root: tk.Misc, config: Any, logger: Any) -> None:
        self.root = root
        self.config = config
        self.logger = logger
        self.engine: Any = None        # set by the engine module once it exists and is trained
        self.colours: Any = None       # callable -> status colours (set by load.py)
        self.buttons: dict[tk.Button, dict[str, Any]] = {}

    # ------------------------------------------------------------------ settings
    def _bool(self, key: str, default: bool = False) -> bool:
        try:
            value = self.config.get_bool(key, default=default)
        except TypeError:
            value = self.config.get_bool(key)
        return default if value is None else bool(value)

    def _str(self, key: str, default: str = "") -> str:
        try:
            value = self.config.get_str(key, default=default)
        except TypeError:
            value = self.config.get_str(key)
        return value or default

    def enabled(self) -> bool:
        return self._bool(CFG_ENABLED, False)

    def linked(self) -> bool:
        return self._bool(CFG_LINK, False)

    def mode(self, folder: str) -> str:
        """"map" only while macros are switched on and this plugin's button is set to it."""
        if not self.enabled():
            return "copy"
        key = CFG_MODE + ("*" if self.linked() else folder)
        return "map" if self._str(key, "copy") == "map" else "copy"

    def set_mode(self, folder: str, mode: str) -> None:
        mode = "map" if mode == "map" else "copy"
        if self.linked():
            for record in self.buttons.values():
                self.config.set(CFG_MODE + record["folder"], mode)
            self.config.set(CFG_MODE + "*", mode)
        else:
            self.config.set(CFG_MODE + folder, mode)
        self.sync()

    # ------------------------------------------------------------------ service
    def goto(self, name: str | None, folder: str, select_only: bool = True) -> str:
        """Put ``name`` into the galaxy map when this plugin is in map mode and an engine can do it
        (select_only: search and select; otherwise search and plot). Otherwise copy it.
        Returns "mapped", "copied" or "copied-untrained" (map mode but no trained engine yet)."""
        name = (name or "").strip()
        if not name:
            return "copied"
        try:                                   # always copied first: the map macro pastes from it
            self.root.clipboard_clear()
            self.root.clipboard_append(name)
        except (tk.TclError, AttributeError):
            self.logger.debug("Clipboard unavailable", exc_info=True)
        if self.mode(folder) != "map":
            return "copied"
        try:
            engine = self.get_engine()
            if engine.ready(select_only) and engine.goto(name, select_only):
                return "mapped"
        except Exception:
            self.logger.exception("Map macro failed; %r stays copied", name)
        return "copied-untrained"

    # ------------------------------------------------------------------ engine and training
    def get_engine(self) -> Any:
        """The shared galaxy-map engine, created on first use (so nothing loads while macros are off)."""
        if self.engine is None:
            self.engine = _sibling("map_engine").MapEngine(self.root, self.config, self.logger)
        return self.engine

    def open_training(self, owner: tk.Misc) -> Any:
        """Open the shared training window from a settings page; returns the new window."""
        training = _sibling("map_training").TrainingWindow(self.get_engine(), owner)
        return training.window

    # ------------------------------------------------------------------ header button
    def make_button(self, parent: tk.Misc, folder: str, like: tk.Misc | None = None,
                    beside: bool = False, extra: Any = None, **grid: Any) -> tk.Button:
        """The small copy/auto toggle. Pass the grid options to place it (it is shown only while
        macros are on) and ``like`` (the plugin's collapse button) so it stays the same size.
        ``beside``: grid it in the same cell as ``like`` and keep it immediately to its left, so the
        header's centring is not disturbed. ``extra``: a function giving more pixels to keep clear on the right
        (another box between this button and ``like``)."""
        # The width is set in sync() from the widest of the two icons and the collapse button, so the copy
        # and auto icons are exactly the same size, as big as the collapse box, and nothing shifts.
        button = tk.Button(parent, text=COPY_TEXT, takefocus=False)
        record = {"folder": folder, "like": like, "grid": dict(grid), "beside": bool(beside and like is not None),
                  "extra": extra}
        self.buttons[button] = record
        button.configure(command=lambda: self.set_mode(folder, "copy" if self.mode(folder) == "map" else "map"))
        button.bind("<Destroy>", lambda event, b=button: self.buttons.pop(b, None), add="+")
        self.sync()
        return button

    @staticmethod
    def _text_width(widget: tk.Misc, text: str) -> int:
        return int(widget.tk.call("font", "measure", widget.cget("font"), text))

    def match(self, button: tk.Button, like: tk.Misc | None, texts: tuple[str, ...]) -> None:
        """Copy the collapse button's font and padding onto ``button`` and fit its width to ``texts``."""
        if like is not None:
            try:
                for option in MATCH_OPTIONS:
                    if str(button.cget(option)) != str(like.cget(option)):
                        button.configure(**{option: like.cget(option)})
            except tk.TclError:
                pass
        self._fit_width(button, like, texts)

    def _fit_box(self, button: tk.Button, like: tk.Misc) -> bool:
        """Give ``button`` exactly the size of ``like`` (the collapse box), whatever its text: an
        invisible one-pixel image with the text centred over it lets width and height be set in pixels."""
        try:
            width, height = like.winfo_reqwidth(), like.winfo_reqheight()
            if width < 8 or height < 8:
                return False
            signature = (width, height, str(button.cget("font")), str(button.cget("padx")), str(button.cget("pady")),
                         str(button.cget("borderwidth")))
            if getattr(button, "navigator_box", None) == signature:
                return True                               # already this size: change nothing (no layout churn)
            if not getattr(button, "navigator_pixel", None):
                button.navigator_pixel = tk.PhotoImage(master=button, width=1, height=1)
            button.configure(image=button.navigator_pixel, compound="center", width=width, height=height)
            # Borders and padding are added on top of the pixel size; take them off again.
            extra_w, extra_h = button.winfo_reqwidth() - width, button.winfo_reqheight() - height
            if extra_w or extra_h:
                button.configure(width=max(1, width - extra_w), height=max(1, height - extra_h))
            button.navigator_box = signature
            return True
        except tk.TclError:
            return False

    def _fit_width(self, button: tk.Button, like: tk.Misc | None,
                   texts: tuple[str, ...] = (COPY_TEXT, MAP_TEXT)) -> None:
        if like is not None and self._fit_box(button, like):
            return
        """Make the button as wide as the widest of its icons (and the collapse button's text), in
        characters of its own font, so switching between them never resizes it."""
        widest = max([self._text_width(button, text) for text in texts] or [0])
        if like is not None:
            try:
                widest = max(widest, self._text_width(like, str(like.cget("text"))))
            except tk.TclError:
                pass
        unit = max(1, self._text_width(button, "0"))
        chars = max(2, -(-widest // unit))             # ceiling
        if int(button.cget("width")) != chars:
            button.configure(width=chars)

    def sync(self) -> None:
        """Show or hide the buttons, and refresh their icon, colour and size."""
        shown_setting = self.enabled()
        for button, record in list(self.buttons.items()):
            shown = shown_setting and not getattr(button, "navigator_hidden", False)
            try:
                if not button.winfo_exists():
                    self.buttons.pop(button, None)
                    continue
                mapped = self.mode(record["folder"]) == "map"
                button.configure(text=MAP_TEXT if mapped else COPY_TEXT)
                like = record["like"]
                if like is not None and like.winfo_exists():
                    for option in MATCH_OPTIONS:
                        if str(button.cget(option)) != str(like.cget(option)):
                            button.configure(**{option: like.cget(option)})
                    plain = like.cget("foreground")
                else:
                    plain = button.cget("foreground")
                self._fit_width(button, like if like is not None and like.winfo_exists() else None)
                on = MAP_COLOUR
                if self.colours is not None:
                    try:
                        on = self.colours().get("on") or MAP_COLOUR      # green, or the theme's Highlighted colour
                    except Exception:
                        pass
                button.configure(foreground=on if mapped else plain,
                                 activeforeground=on if mapped else plain)
                if shown:
                    if not button.winfo_manager() and record["grid"]:
                        button.grid(**record["grid"])
                    if record["beside"] and button.winfo_manager():
                        gap = like.winfo_reqwidth() + 2 if like is not None and like.winfo_exists() else 0
                        if record.get("extra") is not None:
                            gap += int(record["extra"]() or 0)
                        if record.get("gap") != gap:
                            record["gap"] = gap
                            button.grid_configure(padx=(0, gap))
                elif button.winfo_manager():
                    button.grid_remove()
            except tk.TclError:
                self.buttons.pop(button, None)

    def close(self) -> None:
        self.buttons.clear()
        self.engine = None
