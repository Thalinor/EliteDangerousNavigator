# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Choose the text style for the dark and transparent themes.

EDMC picks the font while it builds a theme's colour table: the Transparent theme gets the all-capitals
Euro Caps font, Dark gets the normal one, and that changes how much room every plugin needs. This wraps
EDMC's own table-building step so the commander's choice (Follow EDMC / Normal / ALL CAPS) is put into
the same table, in the same pass EDMC already makes, so nothing extra is refreshed. The wrapper lives in
memory only and is removed when Interface stops.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from typing import Any

CFG_TEXT_STYLE = "NavInterface_TextStyle"
FOLLOW, NORMAL, CAPS = "follow", "normal", "caps"
CHOICES = ((FOLLOW, "Follow EDMC (dark: normal text, transparent: all capitals)"),
           (NORMAL, "Normal text in dark and transparent"),
           (CAPS, "ALL CAPITALS in dark and transparent"))


class ThemeFont:
    def __init__(self, config: Any, logger: Any) -> None:
        self.config = config
        self.logger = logger
        self._theme: Any = None
        self._caps: Any = None             # one Euro Caps font object, reused by every apply
        self._failed = False

    # ------------------------------------------------------------------ setting
    def style(self) -> str:
        try:
            value = self.config.get_str(CFG_TEXT_STYLE, default=FOLLOW)
        except TypeError:
            value = self.config.get_str(CFG_TEXT_STYLE)
        return value if value in (NORMAL, CAPS) else FOLLOW

    # ------------------------------------------------------------------ hook
    def install(self) -> bool:
        """Wrap EDMC's theme-table step (``theme._colors``). False if EDMC has no such step."""
        try:
            from theme import theme
        except Exception:
            return False
        original = getattr(theme, "_colors", None)
        if not callable(original) or getattr(theme, "_navigator_font_wrapped", False):
            return False
        self._theme = theme

        def colours(root: Any, theme_id: Any = None, *args: Any, **kwargs: Any) -> Any:
            result = original(root, theme_id, *args, **kwargs)
            self._override(root, theme_id)
            return result

        theme._colors = colours
        theme._navigator_font_wrapped = True
        return True

    def uninstall(self) -> None:
        theme = self._theme
        if theme is None:
            return
        theme.__dict__.pop("_colors", None)            # back to EDMC's own method
        theme.__dict__.pop("_navigator_font_wrapped", None)
        self._theme = None
        self._caps = None

    # ------------------------------------------------------------------ the override
    def _override(self, root: Any, theme_id: Any) -> None:
        style = self.style()
        theme = self._theme
        current = getattr(theme, "current", None)
        if style == FOLLOW or not isinstance(current, dict) or not theme_id:
            return                                    # Follow EDMC, or the Default theme: leave it alone
        try:
            if style == NORMAL:
                current["font"] = "TkDefaultFont"
            elif self._latin_ui():
                if self._caps is None:
                    self._caps = tkfont.Font(root=root, family="Euro Caps", size=10, weight=tkfont.NORMAL)
                current["font"] = self._caps
        except tk.TclError:
            if not self._failed:
                self._failed = True
                self.logger.exception("Could not set the theme text style")

    @staticmethod
    def _latin_ui() -> bool:
        """Euro Caps only has Latin letters; EDMC keeps the normal font for other scripts, so do we."""
        try:
            from l10n import translations as tr
            first = tr.tl("Cmdr")[0]
            return not 0x250 < ord(first) < 0x3000
        except Exception:
            return True
