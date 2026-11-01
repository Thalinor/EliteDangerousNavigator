# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Navigator Interface - appearance control for the Navigator plugin suite (EDMC plugin).

Styles themed scrollbars, arranges plugin panels and constrains window sizes
in response to Tk events. No recurring refresh, journal polling or watchdog.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import sys
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from typing import Any

import myNotebook as nb
from config import appname, config

try:
    from tkinter import colorchooser
except ImportError:          # colour picker is optional
    colorchooser = None

# These helpers also support EDMC's direct load.py loader and isolated tests.
try:
    from .custom_headers import CustomHeaders
    from .settings_compat import SettingsCompat
    from .color_schemes import ColorSchemes
    from .window_memory import WindowMemory
    from .panel_backgrounds import PanelBackgrounds
    from .map_macros import MapMacros
    from .master_scroll import MasterScroll
    from .theme_font import ThemeFont, CHOICES as TEXT_STYLE_CHOICES, CFG_TEXT_STYLE
except ImportError:
    import importlib.util
    from pathlib import Path
    def _helper_module(name):
        key = '_navigator_interface_' + name
        if key not in sys.modules:
            spec = importlib.util.spec_from_file_location(key, Path(__file__).with_name(name+'.py'))
            module = importlib.util.module_from_spec(spec)
            sys.modules[key] = module
            spec.loader.exec_module(module)
        return sys.modules[key]
    CustomHeaders = _helper_module('custom_headers').CustomHeaders
    SettingsCompat = _helper_module('settings_compat').SettingsCompat
    ColorSchemes = _helper_module('color_schemes').ColorSchemes
    WindowMemory = _helper_module('window_memory').WindowMemory
    PanelBackgrounds = _helper_module('panel_backgrounds').PanelBackgrounds
    MapMacros = _helper_module('map_macros').MapMacros
    MasterScroll = _helper_module('master_scroll').MasterScroll
    ThemeFont = _helper_module('theme_font').ThemeFont
    TEXT_STYLE_CHOICES = _helper_module('theme_font').CHOICES
    CFG_TEXT_STYLE = _helper_module('theme_font').CFG_TEXT_STYLE

TITLE = "(N) Interface"
VERSION = "1.2.59"
PLUGIN_NAME = os.path.basename(os.path.dirname(__file__))
logger = logging.getLogger(f"{appname}.{PLUGIN_NAME}")

# Settings (stored in EDMC's own config, with a unique prefix)
CFG_ENABLED = "NavInterface_ScrollbarsEnabled"
CFG_COLOUR = "NavInterface_ScrollbarColour"
CFG_WIDTH = "NavInterface_ScrollbarWidth"
CFG_MODE = "NavInterface_ScrollbarMode"   # "hidden" (vanish completely) or "handle"
CFG_LOCK_W = "NavInterface_LockWidth"
CFG_WIDTH_PX = "NavInterface_WindowWidth"
CFG_LOCK_H = "NavInterface_LockHeight"
CFG_HEADER_SETTINGS = "NavInterface_HeaderSettingsButton"   # a Settings cog on the title bar while the menu is hidden
CFG_HEADER_GLASS = "NavInterface_HeaderGlass"               # Transparent: the title bar / Commander Profile header are see-through too
CFG_STAY_GLASS = "NavInterface_StayGlass"                   # Transparent: stay see-through even while the pointer is over EDMC
CFG_MASTER_SCROLL = "NavInterface_MasterScroll"          # scroll EDMC's window when the plugins make it taller than the screen
CFG_SCROLL_SIDE = "NavInterface_MasterScrollSide"      # "left" (default: clear of the buttons on the right) or "right"
CFG_SCROLL_BAR = "NavInterface_MasterScrollBar"        # "auto" (only while scrolling), or "never" (scroll without a bar)
CFG_HEIGHT_PX = "NavInterface_WindowHeight"
CFG_BIOSCAN_FIT = "NavInterface_BioScanFit"
CFG_COMPACT = "NavInterface_CompactButtons"
CFG_FORCE_THEME = "NavInterface_ForceThemeColours"   # accessibility: status buttons use theme colours, not red/green
CFG_HEADER_COG = "NavInterface_HeaderCog"            # show a cog box beside clickable plugin headers
CFG_HALF_WIDTH_DONE = "NavInterface_HalfWidthApplied"
CFG_GROW_WIDTH_DONE = "NavInterface_Width125Applied"
CFG_THEME_WIDTH = "NavInterface_ThemeWidth"
CFG_HIDE_EXPORT = "NavInterface_HideExport"
CFG_HIDE_UPDATE = "NavInterface_HideUpdate"
CFG_HIDE_FETCH = "NavInterface_HideBioScanFetch"
CFG_PANEL_ORDER = "NavInterface_PanelOrder"
CFG_HIDE_CHROME = "NavInterface_HideChromeUnfocused"
CFG_HIDE_MENU = "NavInterface_AltHideMenu"
CFG_HIDE_BOTH = "NavInterface_AltHideTitleAndMenu"
CFG_ALT_MIGRATED = "NavInterface_AltChromeMigrated"
CFG_CORE_COLLAPSED = "NavInterface_CoreFieldsCollapsed"
CFG_HEADER_ALIGN = "NavInterface_HeaderJustify"   # "center" (default), "left" or "mixed" (left when collapsed)
CFG_HIDE_HIDDEN = "NavInterface_HideHiddenSuffix"  # drop " (Hidden)" from collapsed headers (default off)
HIDDEN_SUFFIX = " (Hidden)"
CFG_COLLAPSE_MEMORY = "NavInterface_PanelCollapsed"   # JSON {panel identity: [collapsed, ...]}
# Suite panels remember their own state; Navigator Interface remembers the rest.
SUITE_FOLDERS = {"Navigator_Interface", "Navigator_Cartography", "Navigator_Dashboard", "Navigator_Navigation",
                 "Navigator_Docking", "Navigator_Radio", "Navigator_Voice", "Navigator_Tools",
                 # Folder names before 30 Oct 2026 (phase 3), still recognised:
                 "EDMC_Cockpit_Companion", "Ship_Radio", "Ship_Computer", "Systems_Navigator",
                 "Docking_Navigator", "Voice_Navigator"}
SUITE_PREFIXES = ("Navigator_Neutron_Highway", "Neutron_Highway_Navigator")   # every route edition
# Phase 3 folder renames: saved panel order, layout profiles, custom headers, collapse memory
# and contrast choices are keyed by folder and are carried over once (see _migrate_folders).
FOLDER_RENAMES = {"Systems_Navigator": "Navigator_Cartography", "Ship_Computer": "Navigator_Dashboard",
                  "Docking_Navigator": "Navigator_Docking", "Ship_Radio": "Navigator_Radio",
                  "Voice_Navigator": "Navigator_Voice",
                  "Neutron_Highway_Navigator": "Navigator_Navigation",
                  "Neutron_Highway_Navigator_Auto": "Navigator_Navigation",
                  "Navigator_Neutron_Highway": "Navigator_Navigation",
                  "Navigator_Neutron_Highway_Auto": "Navigator_Navigation"}
# The Standard and Auto route editions were merged into one Navigation plugin (31 Oct 2026); any other route
# edition name (Neutron_Highway_Navigator_X, Navigator_Neutron_Highway_X) maps to it too.


def _renamed_folder(name: str) -> str:
    if name in FOLDER_RENAMES:
        return FOLDER_RENAMES[name]
    if name.startswith(("Neutron_Highway_Navigator_", "Navigator_Neutron_Highway_")):
        return "Navigator_Navigation"
    return name
STATUS_TOAST_MS = 5000
DEFAULT_COLOUR = "#ff8c00"     # EDMC-style orange
DEFAULT_WIDTH = 5              # pixels
RESIZE_GRIP_SIZE = 11          # another 25% reduction, rounded from 11.25 px
CONTROL_SCALE = 0.625          # 25% larger than the previous half-size controls
ELEMENT_PREFIX = "NavIf"       # our cloned scrollbar parts

_settings_compat = None
_map_macros = None
_theme_font = None
_panel_backgrounds = None
_window_memory = None
_custom_headers = None
_color_schemes = None
_root: tk.Misc | None = None
_style: ttk.Style | None = None
_styles_by_bg: dict[str, str] = {}      # panel background colour -> our style name
_original_styles: dict[tk.Misc, str] = {}
_last_count = -1
_wrapped: dict[tk.Misc, Any] = {}
_prefs: dict[str, Any] = {}
_style_signatures: dict[str, tuple] = {}
_theme_name: str | None = None
_pending: str | None = None
_bindings: list[tuple[str, str]] = []
_stopped = True
_window_defaults: tuple | None = None
_constraint_signature: tuple | None = None
_bioscan_options: dict[tk.Misc, dict[str, Any]] = {}
_bioscan_windows: dict[tuple[tk.Canvas, int], str] = {}
_bioscan_pack: dict[tk.Misc, dict[str, Any]] = {}
_panel_style_signatures: dict[str, tuple] = {}
_panel_viewports: dict[tk.Canvas, int] = {}
_bar_grid: dict[tk.Misc, str] = {}
_control_options: dict[tk.Misc, dict[str, Any]] = {}
_control_fonts: dict[tk.Misc, tkfont.Font] = {}
_font_width_scales: dict[tuple, float] = {}
_resize_grip: tk.Label | None = None
_resize_space: tk.Frame | None = None
_resize_image: tk.PhotoImage | None = None
_resize_colour: str | None = None
_resize_drag: tuple | None = None
_manual_size: tuple[int, int] | None = None
_master_scroll: Any = None
_app_frame: tk.Misc | None = None
_hidden_controls: dict[tk.Misc, dict] = {}
_status_widget: tk.Misc | None = None
_status_trace: str | None = None
_status_timer: str | None = None
_status_grid: dict = {}
_status_options: dict = {}
_status_expired = False
_plugin_rows: dict[tk.Misc, int] = {}
_thumb_images: dict[tuple, tk.PhotoImage] = {}
_stretch_grid: dict[tk.Misc, str] = {}
_stretch_rows: dict[tuple[tk.Misc, int], int] = {}
_stretch_columns: dict[tuple[tk.Misc, int], int] = {}
_stretch_pack: dict[tk.Misc, dict] = {}
_chrome_widgets: dict[tk.Misc, tuple[str, dict]] = {}
_chrome_menu: str | None = None
_chrome_theme: tuple | None = None
_native_caption: tuple[int, int, tuple[int, int]] | None = None
_hover_bindings: dict[str, tuple[str, str]] = {}
_chrome_mode_seen: str | None = None
_chrome_revealed = False
_chrome_transparency: tuple[int, str] | None = None
_alt_down = False
_alt_used = False
_core_button: tk.Button | None = None
_core_placeholder: tk.Label | None = None
_hidden_text: dict = {}   # header label -> (text with suffix, text without)
_align_watch: set = set()   # collapse buttons that re-justify their header (mixed mode)
_collapse_seen: set = set()   # collapse buttons already restored and watched this session
_header_grid: dict = {}   # header widget -> (original grid options, original anchor)
_core_hidden: dict[tk.Misc, dict] = {}
_core_grid_guards: dict[tk.Misc, dict] = {}
_core_padding: tuple | None = None
_core_style_signature: tuple | None = None
_purpose_headers: dict[tk.Misc, dict] = {}


def _caption_api() -> tuple:
    """Typed Win32 calls, including pointer-sized HWND/style values on 64-bit."""
    import ctypes as c
    from ctypes import wintypes as w
    user = c.WinDLL("user32", use_last_error=True)
    user.GetAncestor.argtypes = [w.HWND, w.UINT]
    user.GetAncestor.restype = w.HWND
    get_style = getattr(user, "GetWindowLongPtrW", user.GetWindowLongW)
    set_style = getattr(user, "SetWindowLongPtrW", user.SetWindowLongW)
    get_style.argtypes, get_style.restype = [w.HWND, c.c_int], c.c_ssize_t
    set_style.argtypes, set_style.restype = [w.HWND, c.c_int, c.c_ssize_t], c.c_ssize_t
    user.GetClientRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
    user.GetWindowRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
    user.GetMenu.argtypes, user.GetMenu.restype = [w.HWND], w.HMENU
    user.SetWindowPos.argtypes = [w.HWND, w.HWND, c.c_int, c.c_int, c.c_int, c.c_int, w.UINT]
    return c, w, user, get_style, set_style


def _set_native_caption(hidden: bool) -> None:
    """Remove the native caption without changing Tk's theme or activation model.

    Keep the native resize border, client dimensions, z-order and focus. In
    particular, never use overrideredirect to implement optional header hiding.
    """
    global _native_caption
    if not hidden and _native_caption is None:
        return
    if sys.platform != "win32" or _root.overrideredirect():
        _native_caption = None
        return
    c, w, user, get_style, set_style = _caption_api()
    hwnd = user.GetAncestor(_root.winfo_id(), 2)  # GA_ROOT: Tk's outer WM window.
    style = get_style(hwnd, -16)  # GWL_STYLE
    caption_mask = 0x00C00000  # WS_CAPTION; leave WS_THICKFRAME available to resize.
    if hidden:
        if style & caption_mask:
            _native_caption = (hwnd, style & caption_mask,
                               (_root.winfo_width(), _root.winfo_height()))
        elif _native_caption is not None and _native_caption[0] == hwnd:
            _native_caption = (hwnd, _native_caption[1],
                               (_root.winfo_width(), _root.winfo_height()))
        wanted = style & ~caption_mask
    else:
        saved, _native_caption = _native_caption, None
        if saved is None or saved[0] != hwnd:
            return
        wanted = style | saved[1]
    if style == wanted:
        return
    before, after, outer = w.RECT(), w.RECT(), w.RECT()
    if not user.GetClientRect(hwnd, c.byref(before)):
        raise c.WinError(c.get_last_error())
    c.set_last_error(0)
    if not set_style(hwnd, -16, wanted) and c.get_last_error():
        raise c.WinError(c.get_last_error())
    flags = 0x0002 | 0x0004 | 0x0010  # NOMOVE | NOZORDER | NOACTIVATE
    if not user.SetWindowPos(hwnd, None, 0, 0, 0, 0, flags | 0x0001 | 0x0020):
        raise c.WinError(c.get_last_error())
    if _root.state() != "normal":
        return  # Shutdown while minimized must not change the restored size.
    # Measure the real non-client delta: AdjustWindowRectEx can disagree with
    # Windows' themed/DPI border metrics by a pixel on each side.
    if not user.GetClientRect(hwnd, c.byref(after)) or not user.GetWindowRect(hwnd, c.byref(outer)):
        raise c.WinError(c.get_last_error())
    width = outer.right - outer.left + before.right - after.right
    height = outer.bottom - outer.top + before.bottom - after.bottom
    if not user.SetWindowPos(hwnd, None, 0, 0, width, height, flags):
        raise c.WinError(c.get_last_error())


def _chrome_mode() -> str:
    if _get_bool(CFG_HIDE_BOTH, False):
        return "both"
    if _get_bool(CFG_HIDE_MENU, False):
        return "menu"
    # Neither box ticked: the title bar and menu are simply shown. In the dark and transparent themes EDMC would hide
    # them whenever the pointer leaves the window (transparent) - so keep them up, like a revealed Alt state.
    # The normal theme has its own native frame and menu: leave it alone.
    return "show" if _root is not None and _root.overrideredirect() else "off"


def _hover_inside() -> bool:
    """Is the mouse pointer over EDMC's window? (Keyboard focus does not count: EDMC keeps the focus while you play.)"""
    try:
        x, y = _root.winfo_pointerxy()
        return (_root.winfo_rootx() <= x < _root.winfo_rootx() + _root.winfo_width()
                and _root.winfo_rooty() <= y < _root.winfo_rooty() + _root.winfo_height())
    except tk.TclError:
        return False


def _wanted_key() -> str:
    """The Transparent theme's see-through colour. While the pointer is over the window it is dropped (the window turns
    solid, as EDMC itself does): over see-through pixels Windows hands the pointer to the game underneath, and the game hides
    the mouse cursor. The 'stay see-through' option keeps the glass at all times."""
    if _get_bool(CFG_STAY_GLASS, False) or not _hover_inside():
        return "grey4"
    return ""


def _hover_event(event: tk.Event) -> None:
    """Pointer or focus moved in or out: refresh only when the see-through colour has to change."""
    if _root is None or _stopped or event.widget is not _root and event.type != tk.EventType.Enter:
        return
    try:
        if _chrome_mode() != "off" and _get_int("theme", 0) == 2 and str(_root.attributes("-transparentcolor")) != _wanted_key():
            _schedule_refresh()
    except tk.TclError:
        pass


HOVER_POLL_MS = 250


_hover_timer: str | None = None


def _hover_poll() -> None:
    """Enter/Leave events are not reliable over see-through pixels (and a touch leaves the pointer parked), so the
    pointer position is also checked a few times a second. It only reads the pointer: nothing is redrawn unless the
    glass has to change."""
    global _hover_timer
    if _stopped or _root is None:
        return
    try:
        if (_get_int("theme", 0) == 2 and _chrome_mode() != "off"
                and str(_root.attributes("-transparentcolor")) != _wanted_key()):
            _schedule_refresh()
        _hover_timer = _root.after(HOVER_POLL_MS, _hover_poll)
    except tk.TclError:
        pass


def _sync_hover_bindings(enabled: bool) -> None:
    """Suspend only EDMC's registered onenter/onleave commands, not plugin events.

    EDMC binds these to both pointer and focus events. In transparent mode they
    swap the whole header and transparency key. Fighting those swaps after the
    event causes flashing, so remove those specific script lines up front.
    Keep the Tcl commands alive and retain any other plugins' added bindings.
    """
    if not enabled:
        for sequence, (original, filtered) in list(_hover_bindings.items()):
            current = _root.bind(sequence)
            if current.startswith(filtered):
                restored = original + current[len(filtered):]
            else:
                removed = [line for line in original.splitlines(True)
                           if re.search(r"\[\d+on(?:enter|leave)\s", line)]
                restored = "".join(line for line in removed if line not in current) + current
            _root.tk.call("bind", _root._w, sequence, restored)
        _hover_bindings.clear()
        return
    for sequence in ("<Enter>", "<Leave>", "<FocusIn>", "<FocusOut>"):
        if sequence in _hover_bindings:
            continue
        original = _root.bind(sequence)
        filtered = "".join(line for line in original.splitlines(True)
                           if not re.search(r"\[\d+on(?:enter|leave)\s", line))
        if filtered != original:
            _hover_bindings[sequence] = original, filtered
            _root.tk.call("bind", _root._w, sequence, filtered)


def _remember_chrome(widget: tk.Misc) -> None:
    if widget not in _chrome_widgets:
        manager = widget.winfo_manager()
        info = getattr(widget, f"{manager}_info")() if manager else {}
        info.pop("in", None)
        _chrome_widgets[widget] = manager, info


def _restore_chrome_widgets(keep: set | None = None, new_theme: bool = False) -> None:
    for widget, (manager, info) in list(_chrome_widgets.items()):
        if keep is not None and widget in keep:
            continue
        _chrome_widgets.pop(widget, None)
        try:
            if new_theme and widget.winfo_name() in ("alternate_menubar", "blank_menubar"):
                continue  # EDMC's new theme owns the container visibility.
            current = widget.winfo_manager()
            if manager:
                getattr(widget, manager)(**info)
            elif current:
                getattr(widget, "grid_remove" if current == "grid" else f"{current}_forget")()
        except tk.TclError:
            pass


def _sync_chrome(force_show: bool = False) -> None:
    global _chrome_menu, _chrome_theme, _chrome_mode_seen, _chrome_revealed
    global _chrome_transparency
    if not force_show and _root.state() != "normal":
        return
    mode = "off" if force_show else _chrome_mode()
    if mode != _chrome_mode_seen:
        _chrome_mode_seen, _chrome_revealed = mode, False
    _sync_hover_bindings(mode != "off")
    theme = (_get_int("theme", 0), bool(_root.overrideredirect()))
    if _chrome_theme is not None and theme != _chrome_theme:
        _restore_chrome_widgets(new_theme=True)
    _chrome_theme = theme
    if mode != "off" and theme[0] == 2 and sys.platform == "win32":
        key = str(_root.attributes("-transparentcolor"))
        if _chrome_transparency is None:
            _chrome_transparency = (2, key)
        wanted = _wanted_key()
        if key != wanted:
            _root.attributes("-transparentcolor", wanted)
            try:
                _root.event_generate("<<NavigatorGlass>>")      # plugins with typing boxes re-colour them
            except tk.TclError:
                pass
    elif _chrome_transparency is not None:
        old_theme, key = _chrome_transparency
        _chrome_transparency = None
        if theme[0] == old_theme:
            _root.attributes("-transparentcolor", key)
    hide_menu = mode in ("menu", "both") and not _chrome_revealed
    hide_title = mode == "both" and hide_menu
    if not hide_title:
        _set_native_caption(False)
    menu = str(_root.cget("menu"))
    if hide_menu and menu:
        _chrome_menu = menu
        _root.configure(menu="")
        _schedule_refresh()
        return
    if not hide_menu and _chrome_menu is not None:
        if not menu:
            _root.configure(menu=_chrome_menu)
        _chrome_menu = None
        if not force_show:
            _schedule_refresh()
            return
    if hide_title:
        _set_native_caption(True)
    if mode == "off":
        _restore_chrome_widgets()
        return
    hidden, frames = set(), []
    pending = list(_root.winfo_children())
    while pending:
        widget = pending.pop()
        if isinstance(widget, tk.Toplevel):
            continue
        name = widget.winfo_name()
        if name == "blank_menubar":
            hidden.add(widget)
        elif name == "alternate_menubar":
            frames.append(widget)
            if hide_title:
                hidden.add(widget)
            elif hide_menu:
                # Installed EDMC: title/minimize/close in row 0, menus in
                # row 1 and their separator in row 2, inside the SAME frame.
                hidden.update(child for child in widget.winfo_children()
                              if child.winfo_manager() == "grid"
                              and int(child.grid_info()["row"]) >= 1)
                hidden.update(child for child in _chrome_widgets
                              if child.master is widget and
                              int(_chrome_widgets[child][1].get("row", 0)) >= 1)
        else:
            pending.extend(widget.winfo_children())
    keep = hidden | set(frames)
    _restore_chrome_widgets(keep)
    for widget in hidden:
        manager = widget.winfo_manager()
        if manager:
            _remember_chrome(widget)
            getattr(widget, "grid_remove" if manager == "grid" else f"{manager}_forget")()
    if theme[1] and not hide_title:
        for frame in frames:
            if not frame.winfo_manager():
                _remember_chrome(frame)
                frame.grid(row=0, columnspan=2, sticky=tk.NSEW)


DRAG_BACKDROP = "#000000"          # pure black: reads as the dark game behind the glass, yet is not the see-through key (grey4, #0a0a0a), so it can be grabbed
_title_paint: dict = {}            # the title label -> its own background, to put back
_title_colour = [""]                 # what the title strip is painted right now (read by the repaint guard)
_title_geometry: dict = {}           # the title bar's own padding, restored when we stop painting it
_cogs: dict = {}                   # the Settings cogs: 'bar' (on the title bar) and 'core' (on the Commander Profile row)


def _find_widget(name: str) -> tk.Misc | None:
    pending = list(_root.winfo_children()) if _root is not None else []
    while pending:
        widget = pending.pop()
        if isinstance(widget, tk.Toplevel):
            continue
        try:
            if widget.winfo_name() == name:
                return widget
            pending.extend(widget.winfo_children())
        except tk.TclError:
            continue
    return None


_window_drag: list = []            # [x offset, y offset] while the window is being dragged by one of our header areas


def _drag_start(event: tk.Event) -> None:
    if _root is not None and _root.overrideredirect():
        _window_drag[:] = [event.x_root - _root.winfo_rootx(), event.y_root - _root.winfo_rooty()]


def _drag_move(event: tk.Event) -> None:
    if _window_drag and _root is not None:
        _root.geometry(f"+{event.x_root - _window_drag[0]}+{event.y_root - _window_drag[1]}")


def _drag_end(_event: tk.Event) -> None:
    _window_drag.clear()


def _make_drag_handle(widget: tk.Misc) -> None:
    """Let a header label move the whole (borderless) window, as EDMC's own title bar does."""
    if getattr(widget, "navigator_window_drag", False):
        return
    widget.navigator_window_drag = True          # the master scroll leaves presses here alone
    widget.configure(cursor="fleur")
    widget.bind("<ButtonPress-1>", _drag_start, add="+")
    widget.bind("<B1-Motion>", _drag_move, add="+")
    widget.bind("<ButtonRelease-1>", _drag_end, add="+")


def _open_edmc_settings(_event: tk.Event | None = None) -> str:
    """Open EDMC's own Settings: the File menu's third entry, found from the window's menu bar."""
    try:
        for menu in _root.winfo_children():
            if menu.winfo_class() != "Menu" or menu.index("end") is None:
                continue
            first = next((i for i in range(menu.index("end") + 1) if menu.type(i) == "cascade"), None)   # a tear-off may come first
            if first is not None:
                menu.nametowidget(menu.entrycget(first, "menu")).invoke(2)
                break
    except tk.TclError:
        logger.exception("Could not open EDMC's Settings from the title bar")
    return "break"


def _title_buttons(bar: tk.Misc | None) -> list[tk.Misc]:
    """EDMC's minimise and close buttons: the labels in the title row after the title itself (columns 3 and 4)."""
    found = []
    for child in (bar.winfo_children() if bar is not None else []):
        info = child.grid_info() if child.winfo_manager() == "grid" else {}
        if child.winfo_class() == "Label" and str(info.get("row")) == "0" and str(info.get("column")) in ("3", "4"):
            found.append(child)
    return sorted(found, key=lambda child: int(child.grid_info()["column"]))


_image_paint: dict = {}                # EDMC's minimise/close pictures -> their own background, to put back


def _paint_button_images(buttons: list[tk.Misc], colour: str | None) -> None:
    """EDMC draws the minimise and close buttons as little pictures whose own background is the see-through colour: left
    alone those two stay see-through, whatever colour their label is. Give the pictures the strip's colour too."""
    for widget in buttons:
        try:
            name = str(widget.cget("image"))
            if not name:
                continue
            if colour is not None:
                if name not in _image_paint:
                    _image_paint[name] = str(widget.tk.call(name, "cget", "-background"))
                if str(widget.tk.call(name, "cget", "-background")) != colour:
                    widget.tk.call(name, "configure", "-background", colour)
            elif name in _image_paint:
                widget.tk.call(name, "configure", "-background", _image_paint.pop(name))
        except tk.TclError:
            _image_paint.pop(name, None)


def _align_title(title: tk.Misc | None, buttons: list[tk.Misc], painting: bool) -> None:
    """While the title bar is painted solid it lines up with the rows beneath it: it starts and ends where they do, and
    the minimise, close (and cog) buttons sit flush against each other with no see-through slits between them."""
    parts = [widget for widget in (title, *buttons) if widget is not None]
    try:
        if not painting:
            for widget in parts:
                if widget in _title_geometry:
                    padx, inner, sticky = _title_geometry.pop(widget)
                    widget.grid_configure(padx=padx, sticky=sticky)
                    widget.configure(padx=inner)
            return
        left, right = _core_header_insets()
        wanted = {}
        if title is not None:
            wanted[title] = (left, 0)
        for number, widget in enumerate(buttons):
            wanted[widget] = (0, right if number == len(buttons) - 1 else 0)
        for widget, padx in wanted.items():
            _title_geometry.setdefault(widget, (widget.grid_info().get("padx", 0), widget.cget("padx"),
                                                widget.grid_info().get("sticky", "")))
            if _core_pad_pair(widget.grid_info().get("padx", 0)) != padx:
                widget.grid_configure(padx=padx)
            if widget is not title and str(widget.grid_info().get("sticky", "")) != "ns":
                widget.grid_configure(sticky=tk.NS)         # as tall as the title: no steps down to the small buttons
            if widget is not title and str(widget.cget("padx")) != "3":
                widget.configure(padx=3)
    except tk.TclError:
        pass


def _paint_colour(key: str) -> str | None:
    """The solid colour for the title bar strip: black while the window is see-through (the game behind is black, and the
    strip must not be the see-through colour or it could not be grabbed), and the window's own colour while the window is
    solid, so the strip and the rows match. None with the 'stay see-through' option: then nothing is painted at all."""
    if _get_bool(CFG_STAY_GLASS, False):
        return None
    if key:
        return None if _get_bool(CFG_HEADER_GLASS, False) else DRAG_BACKDROP     # the option: leave it see-through
    try:
        return str(_app_frame.cget("background"))
    except (tk.TclError, AttributeError):
        return DRAG_BACKDROP


def _sync_header_extras() -> None:
    """Dark and Transparent themes only. (1) In Transparent the title bar is see-through, and Windows passes clicks through
    see-through pixels, so only the letters themselves could be grabbed: give the title bar a solid, almost black backdrop so
    the whole bar drags the window. (2) Optionally a Settings cog on the title bar while the menu is hidden."""
    if _root is None:
        return
    title, bar = _find_widget("alternate_titlebar"), _find_widget("alternate_menubar")
    borderless = bool(_root.overrideredirect())
    try:
        key = str(_root.attributes("-transparentcolor"))
    except tk.TclError:
        key = ""
    mode = _chrome_mode()
    buttons = _title_buttons(bar)                  # EDMC's minimise and close buttons
    handles = [widget for widget in (title, *buttons, _core_placeholder) if widget is not None]
    if _core_placeholder is not None and _core_button is not None and _core_placeholder.winfo_manager() == "grid":
        handles.append(_core_button)                  # collapsed Commander Profile: its button joins the strip
    if title is not None:
        title.navigator_window_drag = True        # EDMC's own handlers move the window from here
    if _core_placeholder is not None:
        _make_drag_handle(_core_placeholder)      # the "Commander Profile" header drags the window too
    colour = _paint_colour(key)
    aligning = borderless and _get_int("theme", 0) == 2 and mode != "off"
    painting = aligning and colour is not None
    _title_colour[0] = colour or ""
    for widget in handles:
        try:
            if not getattr(widget, "navigator_black", False):
                widget.navigator_black = True
                original = widget.configure

                def configure(cnf=None, _original=original, _widget=widget, **kw):
                    # EDMC repaints its title bar when the window turns solid: keep it ours while we own the paint.
                    if _widget in _title_paint and _title_colour[0]:
                        if isinstance(cnf, dict):
                            cnf = dict(cnf, **({"background": _title_colour[0]} if "background" in cnf else {}))
                        if "background" in kw:
                            kw["background"] = _title_colour[0]
                    return _original(cnf, **kw)

                widget.configure = configure
                widget.config = configure
            if painting:                              # black also while the window is solid
                _title_paint.setdefault(widget, str(widget.cget("background")))
                if str(widget.cget("background")) != colour:
                    widget.configure(background=colour)
            elif widget in _title_paint:
                widget.configure(background=_title_paint.pop(widget))
        except tk.TclError:
            _title_paint.pop(widget, None)
    _align_title(title, buttons, aligning)         # same layout whether it is painted or not: nothing shifts as the glass changes
    _paint_button_images(buttons, colour if painting else None)
    wanted = _get_bool(CFG_HEADER_SETTINGS, True) and borderless and not _chrome_revealed
    try:
        from theme import theme
        highlight = (getattr(theme, "current", None) or {}).get("highlight")
    except Exception:
        highlight = None
    highlight = highlight or _get_str("dark_highlight", "#ff8000")

    # Menu hidden, title bar shown: the cog sits on the title bar beside the minimise button.
    _show_cog("bar", wanted and mode == "menu" and title is not None and bar is not None, bar, title, key, highlight)
    # Title bar hidden too: the cog sits on the Commander Profile row, beside its collapse button.
    _show_cog("core", wanted and mode == "both" and _core_button is not None and _core_button.winfo_manager() == "grid",
              _app_frame, _core_button, key, highlight)


def _show_cog(slot: str, visible: bool, parent: tk.Misc | None, like: tk.Misc | None, key: str, highlight: str) -> None:
    cog = _cogs.get(slot)
    if not visible or parent is None or like is None:
        if cog is not None and cog.winfo_exists():
            cog.grid_remove()
        return
    background = _paint_colour(key) or str(like.cget("background"))
    if slot == "bar":
        # On the title bar the cog is as small as EDMC's minimise and close buttons, and sits flush against them.
        buttons = _title_buttons(parent)
        height = max(8, buttons[0].winfo_reqheight() - 2) if buttons else 12
        if cog is None or not cog.winfo_exists():
            cog = _cogs[slot] = tk.Label(parent, name="navinterface_cog_bar", text="\u2699", cursor="hand2", takefocus=True,
                                         borderwidth=0, highlightthickness=0, pady=0, padx=3)
            for sequence in ("<Button-1>", "<Return>", "<space>"):
                cog.bind(sequence, _open_edmc_settings)
        font = tkfont.Font(font=like.cget("font"))
        font.configure(size=-height)
        cog.navigator_font = font                     # keep it alive while the label uses it
        cog.configure(foreground=highlight, background=background, font=font)
        spot = dict(row=0, column=2, sticky=tk.N + tk.S + tk.E, padx=0)     # full height, but not across the title
    else:
        if cog is None or not cog.winfo_exists():
            # A real button, boxed like the collapse button beside it (and registered with EDMC's theme in the same way).
            cog = _cogs[slot] = tk.Button(parent, name=f"navinterface_cog_{slot}", text="\u2699", cursor="hand2",
                                          command=_open_edmc_settings)
            try:
                from theme import theme
                theme.register(cog)
            except ImportError:
                pass
        cog.configure(foreground=highlight, activeforeground=highlight, font=like.cget("font"),
                      background=background, activebackground=background)
        # Same edges as every other small button (collapse, R, A): copy them from a real one, so the cog is not a full square.
        reference = like if isinstance(like, tk.Button) else next(iter(_collapse_buttons()), None)
        if reference is not None:
            for option in ("padx", "pady", "borderwidth", "relief", "highlightthickness", "highlightbackground", "highlightcolor"):
                try:
                    if str(cog.cget(option)) != str(reference.cget(option)):
                        cog.configure(**{option: reference.cget(option)})
                except tk.TclError:
                    pass
        info = like.grid_info()
        spot = dict(row=int(info.get("row", 0)), column=int(info.get("column", 1)), sticky=tk.NE,
                    padx=(0, _core_pad_pair(info.get("padx", 0))[1] + like.winfo_reqwidth() + 2))
    if cog.winfo_manager() != "grid" or getattr(cog, "navigator_spot", None) != spot:
        cog.grid(**spot)
        cog.navigator_spot = spot
    tk.Misc.lift(cog)


def _alt_press(event: tk.Event) -> str | None:
    global _alt_down, _alt_used
    if _chrome_mode() in ("off", "show") or event.state & 5:  # Ctrl/Shift+Alt, including AltGr.
        return None
    if not _alt_down:
        _alt_down, _alt_used = True, False
    return "break"


def _alt_other_key(event: tk.Event) -> None:
    global _alt_used
    if _alt_down:
        _alt_used = True  # Alt+Tab, Alt+F4, etc. are not a bare Alt toggle.


def _alt_release(event: tk.Event) -> str | None:
    global _alt_down, _alt_used, _chrome_revealed
    if not _alt_down:
        return None
    toggle = not _alt_used and not event.state & 5
    _alt_down, _alt_used = False, False
    if toggle:
        _chrome_revealed = not _chrome_revealed
        _schedule_refresh()
    return "break"


def _alt_focus_out(event: tk.Event) -> None:
    global _alt_down, _alt_used
    if event.widget is _root:
        _alt_down, _alt_used = False, False


def _saved_panel_order() -> list[str]:
    try:
        value = json.loads(_get_str(CFG_PANEL_ORDER, "[]"))
    except (ValueError, TypeError):
        return []
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(item for item in value if isinstance(item, str) and item))


def _plugin_panels() -> list[tuple[str, str, tk.Misc]]:
    """Match EDMC's plugin_N wrappers to its unchanged plug.PLUGINS list.

    Plugins without a main-window panel have their wrapper destroyed by EDMC.
    Separators stay in their original slots; only entire panel wrappers move.
    """
    panels = []
    module = sys.modules.get("plug")
    if _app_frame is None or module is None:
        return panels
    for index, plugin in enumerate(getattr(module, "PLUGINS", ()), start=1):
        widget = _app_frame.children.get(f"plugin_{index}")
        if widget is None or widget.winfo_manager() != "grid":
            continue
        row = int(widget.grid_info()["row"])
        _plugin_rows.setdefault(widget, row)
        name = str(getattr(plugin, "name", f"Plugin {index}"))
        folder = getattr(plugin, "folder", None)
        identity = f"folder:{folder}" if folder else f"name:{name}"
        panels.append((identity, name, widget))
    return sorted(panels, key=lambda panel: _plugin_rows[panel[2]])


def _ordered_panels(panels: list[tuple[str, str, tk.Misc]]) -> list[tuple[str, str, tk.Misc]]:
    rank = {identity: index for index, identity in enumerate(_saved_panel_order())}
    return sorted(panels, key=lambda panel: rank.get(panel[0], len(rank)))


def _restore_plugin_rows() -> None:
    for widget, row in list(_plugin_rows.items()):
        try:
            if widget.winfo_manager() == "grid" and int(widget.grid_info()["row"]) != row:
                widget.grid_configure(row=row)
        except tk.TclError:
            pass


def _sync_plugin_order() -> None:
    panels = _plugin_panels()
    if not _saved_panel_order():
        _restore_plugin_rows()
        return
    slots = sorted(_plugin_rows[panel[2]] for panel in panels)
    for slot, (_, _, widget) in zip(slots, _ordered_panels(panels)):
        if int(widget.grid_info()["row"]) != slot:
            widget.grid_configure(row=slot)


def _profile_buttons(widget):
    pending=[widget]
    while pending:
        item=pending.pop()
        try:
            if item.winfo_class()=="Button" and str(item.cget("text")).strip() in COLLAPSE_GLYPHS:
                yield item
            pending.extend(item.winfo_children())
        except tk.TclError:
            pass


def _layout_profiles():
    try:
        profiles=json.loads(_get_str("NavInterface_LayoutProfiles","{}"))
        return profiles if isinstance(profiles,dict) else {}
    except (ValueError,TypeError):
        return {}


def _save_profile(name):
    _save_panel_order()
    panels=_ordered_panels(_plugin_panels())
    profiles=_layout_profiles()
    profiles[name]={"order":[identity for identity,_,_ in panels],
                    "collapsed":{identity:[str(button.cget("text")).strip()==COLLAPSE_GLYPHS[1]
                                           for button in _profile_buttons(widget)]
                                 for identity,_,widget in panels}}
    config.set("NavInterface_LayoutProfiles",json.dumps(profiles))


def _load_profile(name):
    profile=_layout_profiles().get(name)
    if not profile: return
    config.set(CFG_PANEL_ORDER,json.dumps(profile.get("order",[])))
    _sync_plugin_order()
    for identity,_,widget in _plugin_panels():
        wanted=profile.get("collapsed",{}).get(identity,[])
        for button,collapsed in zip(_profile_buttons(widget),wanted):
            current=str(button.cget("text")).strip()==COLLAPSE_GLYPHS[1]
            if current!=collapsed: button.invoke()
    _save_collapse_memory()
    tree=_prefs.get("panel_order")
    if tree is not None and tree.winfo_exists():
        for index,(identity,_,_) in enumerate(_ordered_panels(_plugin_panels())):
            if tree.exists(identity): tree.move(identity,"",index)
        _prefs["order_default"]=False


def _panel_order_prefs(frame: tk.Misc) -> None:
    panels = _plugin_panels()
    _prefs["order_default"] = not bool(_saved_panel_order())
    area = ttk.Frame(frame)
    area.columnconfigure(0, weight=1)
    area.grid(row=32, column=0, columnspan=4, sticky=tk.EW, padx=10)
    tree = ttk.Treeview(area, show="tree", selectmode="browse", height=5)
    tree.column("#0", width=260, stretch=True)
    tree.grid(row=0, column=0, sticky=tk.NSEW)
    scroll = ttk.Scrollbar(area, orient=tk.VERTICAL, command=tree.yview)
    scroll.grid(row=0, column=1, sticky=tk.NS)
    tree.configure(yscrollcommand=scroll.set)
    _prefs["panel_order"] = tree
    for identity, name, _ in _ordered_panels(panels):
        tree.insert("", tk.END, iid=identity, text=name)
    controls = ttk.Frame(area)
    controls.grid(row=0, column=2, sticky=tk.N, padx=(8, 0))

    def move(direction: int) -> str:
        selection = tree.selection()
        if selection:
            identity = selection[0]
            index = tree.index(identity)
            target = max(0, min(len(tree.get_children()) - 1, index + direction))
            if target != index:
                tree.move(identity, "", target)
                tree.see(identity)
                _prefs["order_default"] = False
        return "break"

    def defaults() -> None:
        for index, (identity, _, _) in enumerate(panels):
            tree.move(identity, "", index)
        _prefs["order_default"] = True

    ttk.Button(controls, text="Move Up", command=lambda: move(-1)).pack(fill=tk.X)
    ttk.Button(controls, text="Move Down", command=lambda: move(1)).pack(fill=tk.X, pady=4)
    ttk.Button(controls, text="Default Order", command=defaults).pack(fill=tk.X)
    tree.bind("<Alt-Up>", lambda event: move(-1))
    tree.bind("<Alt-Down>", lambda event: move(1))
    if panels:
        tree.selection_set(tree.get_children()[0])


def _save_panel_order() -> None:
    tree = _prefs.get("panel_order")
    if tree is None:
        return
    if _prefs.get("order_default", False):
        config.set(CFG_PANEL_ORDER, "[]")
        return
    desired = list(tree.get_children())
    # Keep temporarily disabled plugins in their saved positions. Replace only
    # the positions belonging to currently visible panels, then append newcomers.
    remaining = iter(desired)
    merged = [next(remaining) if identity in desired else identity for identity in _saved_panel_order()]
    merged.extend(identity for identity in remaining if identity not in merged)
    config.set(CFG_PANEL_ORDER, json.dumps(merged, ensure_ascii=False))


def _cancel_status_timer() -> None:
    global _status_timer
    if _status_timer is not None and _root is not None:
        try:
            _root.after_cancel(_status_timer)
        except tk.TclError:
            pass
    _status_timer = None


def _expire_status() -> None:
    global _status_timer, _status_expired
    _status_timer = None
    _status_expired = True
    if not _stopped and _status_widget is not None and _status_widget.winfo_exists():
        _status_widget.grid_remove()  # Remove the row, including its grid padding.
        _schedule_refresh()


def _show_status_toast() -> None:
    global _status_timer, _status_expired
    _cancel_status_timer()
    _status_expired = not bool(str(_status_widget.cget("text")).strip())
    if _status_expired:
        _status_widget.grid_remove()
    else:
        if not _status_widget.winfo_manager():
            _status_widget.grid(**{**_status_grid, "sticky": tk.EW})
        _status_timer = _root.after(STATUS_TOAST_MS, _expire_status)
    _schedule_refresh()


def _status_written(command: str, code: str, result: str, operation: str) -> None:
    """Watch writes to EDMC's actual label, including repeated identical messages.

    Tk command traces see both label['text'] and configure(text=...) without
    replacing EDMC's widget methods or periodically checking its contents.
    """
    if _stopped or str(code) != "0":
        return
    args = _root.tk.splitlist(command)
    if len(args) > 3 and args[1] in ("configure", "config") and "-text" in args[2::2]:
        _show_status_toast()


def _height_floor(normal: int) -> int:
    """The shortest the window may be dragged to: with the master scroll on, short enough to scroll the content."""
    if _master_scroll is not None and not _master_scroll.broken and _get_bool(CFG_MASTER_SCROLL, True):
        return min(normal, 160)
    return normal


def _scroll_side() -> str:
    return "right" if _get_str(CFG_SCROLL_SIDE, "left") == "right" else "left"


def _scroll_bar() -> str:
    return "never" if _get_str(CFG_SCROLL_BAR, "auto") == "never" else "auto"


def _chosen_height() -> int | None:
    """The window height the user chose: the one they dragged the corner grip to, else a locked height; None if neither."""
    if _manual_size is not None:
        return int(_manual_size[1])
    _, _, lock_h, height = _size_settings()
    return height if lock_h and height > 0 else None


def _scroll_colour() -> str:
    """The master scroll bar: the theme's Normal Text colour (the Highlighted colour is too bright for something that is
    only a hint)."""
    try:
        from theme import theme
        colours = getattr(theme, "current", None) or {}
    except Exception:
        colours = {}
    return str(colours.get("foreground") or _get_str("dark_text", DEFAULT_COLOUR))


def _edmc_frame(parent: tk.Misc) -> tk.Misc:
    """EDMC passes a disposable plugin_N frame, not its main content frame.

    Capture the ancestor before EDMC destroys our unused wrapper. Identify
    EDMC's explicit frame name; never match arbitrary plugin label text.
    """
    ancestors = []
    candidate = parent
    while candidate is not None:
        ancestors.append(candidate)
        if candidate.winfo_name().casefold() == appname.casefold():
            return candidate
        candidate = candidate.master
    for candidate in ancestors:
        if "status" in candidate.children and "update_button" in candidate.children:
            return candidate
    return parent


def _core_fields() -> list[tk.Misc]:
    if _app_frame is None:
        return []
    names = ("cmdr", "ship", "suit", "system", "station")
    if not all(name in _app_frame.children for name in ("cmdr", "cmdr_label", "ship", "system", "station")):
        return []
    return [w for name in names for key in (name + "_label", name)
            if (w := _app_frame.children.get(key)) is not None]


def _core_pad_pair(value) -> tuple[int, int]:
    parts = (value,) if isinstance(value, (int, float)) else _root.tk.splitlist(value)
    pixels = tuple(_app_frame.winfo_pixels(part) for part in parts)
    return (pixels[0], pixels[-1]) if pixels else (0, 0)


def _toggle_core_fields() -> None:
    config.set(CFG_CORE_COLLAPSED, not _get_bool(CFG_CORE_COLLAPSED, False))
    _sync_core_fields()
    _schedule_refresh()


def _guard_core_grid(fields) -> None:
    """Keep EDMC journal updates from briefly re-showing collapsed core rows."""
    for widget in fields:
        if widget in _core_grid_guards:
            continue
        # Scope adapters to the named core widgets, and preserve existing adapters.
        _core_grid_guards[widget] = {
            name: widget.__dict__.get(name) for name in ("grid", "grid_configure")
        }
        native_grid = widget.grid

        def grid(cnf=None, _widget=widget, _native=native_grid, **kw):
            if not _get_bool(CFG_CORE_COLLAPSED, False):
                return _native(cnf or {}, **kw)
            options = dict(tk._cnfmerge((cnf or {}, kw)))
            if "in_" in options:
                options["in"] = options.pop("in_")
            # Retain EDMC's latest placement for expansion without mapping first.
            info = _core_hidden.setdefault(_widget, dict(_widget.grid_info()))
            info.update(options)
            return None

        widget.grid = widget.grid_configure = grid


def _release_core_grid_guards() -> None:
    for widget, methods in list(_core_grid_guards.items()):
        for name, original in methods.items():
            if original is None:
                widget.__dict__.pop(name, None)
            else:
                setattr(widget, name, original)
    _core_grid_guards.clear()


def _restore_core_fields(remove_button: bool = False) -> None:
    global _core_button, _core_placeholder, _core_padding, _core_style_signature
    _release_core_grid_guards()
    for widget, info in list(_core_hidden.items()):
        try:
            # EDMC hides/forgets Suit when its text is empty (Horizons/login).
            if widget.winfo_name() in ("suit", "suit_label"):
                suit = _app_frame.children.get("suit")
                if suit is not None and not str(suit.cget("text")):
                    continue
            widget.grid(**info)
        except tk.TclError:
            pass
    _core_hidden.clear()
    if remove_button:
        if _core_padding is not None and _app_frame is not None:
            cmdr = _app_frame.children.get("cmdr")
            if cmdr is not None:
                try:
                    cmdr.grid_configure(padx=_core_padding[0])
                except tk.TclError:
                    pass
        if _core_button is not None:
            try:
                _core_button.destroy()
            except tk.TclError:
                pass
        _core_button = None
        if _core_placeholder is not None:
            _core_placeholder.destroy()
            _core_placeholder = None
        _core_padding = _core_style_signature = None


def _core_header_insets() -> tuple[int, int]:
    """Use EDMC's plugin wrapper padding so core and plugin arrows line up."""
    for name, widget in _app_frame.children.items():
        if re.fullmatch(r"plugin_\d+", name) and widget.winfo_manager() == "grid":
            return _core_pad_pair(widget.grid_info().get("padx", 0))
    return (0, 0)


UNDOCKED_MARK = "×"       # what EDMC shows in the Station field when you are not at a station
UNDOCKED_TEXT = "Undocked"


def _undocked_text(kwargs: dict) -> dict:
    if str(kwargs.get("text", "")) == UNDOCKED_MARK:
        kwargs = dict(kwargs, text=UNDOCKED_TEXT)
    return kwargs


def _sync_undocked() -> None:
    """Say 'Undocked' where EDMC shows a bare multiplication sign in the Station field."""
    label = _app_frame.children.get("station") if _app_frame is not None else None
    if label is None:
        return
    if not getattr(label, "navigator_undocked", False):
        original = label.configure

        def configure(cnf=None, **kw):
            if isinstance(cnf, dict):
                cnf = _undocked_text(cnf)
            return original(cnf, **_undocked_text(kw))

        label.configure = configure       # EDMC's label["text"] = ... goes through configure
        label.config = configure
        label.navigator_undocked = True
    try:
        if str(label.cget("text")) == UNDOCKED_MARK:
            label.configure(text=UNDOCKED_TEXT)
    except tk.TclError:
        pass


def _sync_core_fields() -> None:
    """Collapse only EDMC's named core fields; leave all plugin wrappers alone."""
    global _core_button, _core_placeholder, _core_padding, _core_style_signature
    fields = _core_fields()
    if not fields:
        return
    cmdr = _app_frame.children["cmdr"]
    collapsed = _get_bool(CFG_CORE_COLLAPSED, False)
    left_inset, right_inset = _core_header_insets()
    if _core_button is None:
        row = int(_app_frame.children["cmdr_label"].grid_info().get("row", 1))
        _core_button = tk.Button(_app_frame, name="navinterface_core_collapse",
                                 text=COLLAPSE_GLYPHS[0], command=_toggle_core_fields)
        _core_button.grid(row=row, column=1, sticky=tk.NE)
        _core_placeholder = tk.Label(_app_frame, name="navinterface_core_placeholder",
                                      text="Commander Profile (Hidden)", anchor=tk.CENTER)
        _core_placeholder.grid(row=row, column=0, columnspan=2, sticky=tk.EW)
        _core_placeholder.grid_remove()
        try:
            from theme import theme
            theme.register(_core_button)
            theme.register(_core_placeholder)
        except ImportError:
            pass
    if _core_pad_pair(_core_button.grid_info().get("padx", 0)) != (0, right_inset):
        _core_button.grid_configure(padx=(0, right_inset))
    text = COLLAPSE_GLYPHS[1] if collapsed else COLLAPSE_GLYPHS[0]
    if _core_button.cget("text") != text:
        _core_button.configure(text=text)
    signature = tuple(str(cmdr.cget(key)) for key in ("background", "foreground", "font"))
    if signature != _core_style_signature:
        background, foreground, font = signature
        _core_button.configure(background=background, foreground=foreground, font=font,
                               activebackground=background, activeforeground=foreground)
        _core_placeholder.configure(background=background, foreground=foreground, font=font)
        _core_style_signature = signature
    if collapsed:
        _guard_core_grid(fields)
        margin = _core_button.winfo_reqwidth() + 4
        left = _get_str(CFG_HEADER_ALIGN, "center") in ("left", "mixed")   # only shown when collapsed
        title = "Commander Profile" + ("" if _get_bool(CFG_HIDE_HIDDEN, False) else HIDDEN_SUFFIX)
        if str(_core_placeholder.cget("text")) != title:
            _core_placeholder.configure(text=title)
        _core_placeholder.grid(padx=(left_inset + (0 if left else margin), right_inset + margin))
        if str(_core_placeholder.cget("anchor")) != (tk.W if left else tk.CENTER):
            _core_placeholder.configure(anchor=tk.W if left else tk.CENTER)
        for widget in fields:
            if widget.winfo_manager() == "grid":
                _core_hidden[widget] = dict(widget.grid_info())
                widget.grid_remove()
    else:
        _release_core_grid_guards()
        _core_placeholder.grid_remove()
        if _core_hidden:
            _restore_core_fields()
        info = cmdr.grid_info()
        if info:
            current = _core_pad_pair(info.get("padx", 0))
            if _core_padding is None or current != _core_padding[1]:
                _core_padding = (current, current)
            original = _core_padding[0]
            reserved = (original[0], original[1] + right_inset + _core_button.winfo_reqwidth() + 4)
            if current != reserved:
                cmdr.grid_configure(padx=reserved)
            _core_padding = (original, reserved)
    _core_button.lift()


def _bioscan_fetch_eligible(state: Any) -> bool:
    return state is None or (not getattr(state, "display_hidden", False)
                             and not getattr(state, "fetched_edsm", False)
                             and bool(getattr(state, "system", True)))


def _sync_footer() -> None:
    global _status_widget, _status_trace, _status_grid, _status_options
    if _app_frame is None:
        return
    status = _app_frame.children.get("status")
    if _status_widget is None and status is not None and status.winfo_manager() == "grid":
        _status_widget = status
        _status_grid = dict(status.grid_info())
        _status_options = {key: status.cget(key) for key in ("anchor", "justify")}
        _status_trace = _root.register(_status_written)
        _root.tk.call("trace", "add", "execution", str(status), "leave", _status_trace)
        _show_status_toast()
    elif _status_widget is not None and _status_expired and _status_widget.winfo_manager() == "grid":
        _status_widget.grid_remove()
    if _status_widget is not None:
        if any(str(_status_widget.cget(key)) != tk.CENTER for key in ("anchor", "justify")):
            _status_widget.configure(anchor=tk.CENTER, justify=tk.CENTER)
        if _status_widget.winfo_manager() == "grid" and str(_status_widget.grid_info()["sticky"]) != tk.EW:
            _status_widget.grid_configure(sticky=tk.EW)

    pioneer = _panel_state("pioneer.globals", "pioneer_globals")
    export = getattr(pioneer, "copy_button", None)
    bioscan = _bioscan_state()
    borderless = bool(_root.overrideredirect())
    for widget, hide, eligible in (
        (export, _get_bool(CFG_HIDE_EXPORT, False), True),
        (getattr(bioscan, "edsm_button", None), _get_bool(CFG_HIDE_FETCH, False), _bioscan_fetch_eligible(bioscan)),
        (_app_frame.children.get("update_button"), _get_bool(CFG_HIDE_UPDATE, False), not borderless),
        (_app_frame.children.get("themed_update_button"), _get_bool(CFG_HIDE_UPDATE, False), borderless),
    ):
        if widget is None or not widget.winfo_exists():
            continue
        if hide and widget.winfo_manager() == "grid":
            _hidden_controls.setdefault(widget, dict(widget.grid_info()))
            widget.grid_remove()
        elif not hide and widget in _hidden_controls:
            options = _hidden_controls.pop(widget)
            if eligible:
                widget.grid(**options)


def _restore_footer() -> None:
    global _status_widget, _status_trace, _status_grid, _status_options, _status_expired
    _cancel_status_timer()
    if _status_widget is not None:
        try:
            _root.tk.call("trace", "remove", "execution", str(_status_widget), "leave", _status_trace)
        except tk.TclError:
            pass
        try:
            if _status_widget.winfo_exists():
                _status_widget.configure(**_status_options)
                _status_widget.grid(**_status_grid)
        except tk.TclError:
            pass
    if _status_trace is not None:
        try:
            _root.deletecommand(_status_trace)
        except tk.TclError:
            pass
    for widget, options in list(_hidden_controls.items()):
        try:
            name = widget.winfo_name()
            if name == "update_button" and _root.overrideredirect():
                continue
            if name == "themed_update_button" and not _root.overrideredirect():
                continue
            bioscan = _bioscan_state()
            if widget is getattr(bioscan, "edsm_button", None) and not _bioscan_fetch_eligible(bioscan):
                continue
            widget.grid(**options)
        except tk.TclError:
            pass
    _hidden_controls.clear()
    _status_widget = _status_trace = None
    _status_grid = {}
    _status_options = {}
    _status_expired = False


# --------------------------------------------------------------------------- settings
def _get_bool(key: str, default: bool) -> bool:
    try:
        value = config.get_bool(key, default=default)
    except TypeError:
        value = config.get_bool(key)
    return default if value is None else bool(value)


def _get_str(key: str, default: str) -> str:
    try:
        value = config.get_str(key, default=default)
    except TypeError:
        value = config.get_str(key)
    return value or default


def _get_int(key: str, default: int) -> int:
    try:
        value = config.get_int(key, default=default)
    except TypeError:
        value = config.get_int(key)
    return int(value) if value else default


def _settings() -> tuple[bool, str, int]:
    colour = _get_str(CFG_COLOUR, DEFAULT_COLOUR)
    width = max(2, min(24, _get_int(CFG_WIDTH, DEFAULT_WIDTH)))
    return _get_bool(CFG_ENABLED, True), colour, width


# --------------------------------------------------------------------------- styling
def _ensure_elements() -> bool:
    """Borrow fully colourable scrollbar parts from Tk's built-in 'clam' theme.
    (Windows' native scrollbar ignores colours, which is why it stays white.)
    Checked every time: parts belong to the current Tk theme and vanish if it changes."""
    try:
        existing = set(_style.element_names())
        for part in ("trough", "thumb"):
            name = f"{ELEMENT_PREFIX}.Vertical.Scrollbar.{part}"
            if name not in existing:
                _style.element_create(name, "from", "clam", f"Vertical.Scrollbar.{part}")
        return True
    except tk.TclError:
        logger.exception("Could not create the scrollbar style parts")
        return False


def _background_of(widget: tk.Misc) -> str:
    """The colour behind a scrollbar (its panel), so the track can blend in."""
    # Windows colour-key transparency requires the exact key, not a similar
    # parent/theme background. This also works with EDMC's Transparent theme.
    try:
        key = _root.attributes("-transparentcolor")
        if key:
            return str(key)
    except tk.TclError:
        pass
    for candidate in (widget.master, _root):
        if candidate is None:
            continue
        try:
            return str(candidate.cget("background"))
        except tk.TclError:
            try:
                colour = _style.lookup(candidate.winfo_class(), "background")
                if colour:
                    return str(colour)
            except tk.TclError:
                pass
    return "black"


def _mode() -> str:
    mode = _get_str(CFG_MODE, "hidden")
    return mode if mode in ("hidden", "handle") else "hidden"


def _thumb_element(colour: str, width: int) -> str:
    """An image element gives the thin thumb a real minimum LENGTH, not width.

    Clam's thumb gets its tiny minimum from the arrow size. A solid stretchable
    image keeps the existing width while asking ttk for at least four widths
    of length (20 px at the default 5 px width). ttk still owns scrolling/drag.
    """
    rgb = _root.winfo_rgb(colour)
    height = max(20, width * 4)
    signature = (rgb, width, height)
    token = f"{width}_{height}_" + "".join(f"{component:04x}" for component in rgb)
    image_name = f"navif_thumb_{token}"
    element = f"{ELEMENT_PREFIX}.Image{token}.Vertical.Scrollbar.thumb"
    if signature not in _thumb_images:
        photo = tk.PhotoImage(master=_root, name=image_name, width=width, height=height)
        photo.put(colour, to=(0, 0, width, height))
        _thumb_images[signature] = photo
    if element not in _style.element_names():
        _style.element_create(element, "image", _thumb_images[signature], border=0, sticky="nsew")
    return element


def _configure_style(name: str, background: str) -> None:
    _, colour, width = _settings()
    signature = (_mode(), background, colour, width)
    if _style_signatures.get(name) == signature:
        return
    if _mode() == "hidden":
        # Draw no native scrollbar elements at all. Painting a native thumb
        # orange/black cannot hide its Windows borders and state effects.
        _style.layout(name, [])
        colour = background
    else:
        _style.layout(name, [(f"{ELEMENT_PREFIX}.Vertical.Scrollbar.trough", {
            "sticky": "nswe",
            "children": [(_thumb_element(colour, width), {
                "expand": "1", "sticky": "nswe"})],
        })])
    _style.configure(name, troughcolor=background, bordercolor=background,
                     background=colour, lightcolor=colour, darkcolor=colour,
                     arrowcolor=colour, gripcount=0, arrowsize=width, width=width, relief="flat", borderwidth=0)
    _style.map(name, background=[("pressed", colour), ("active", colour)],
               lightcolor=[("pressed", colour), ("active", colour)],
               darkcolor=[("pressed", colour), ("active", colour)])
    _style_signatures[name] = signature


def _style_for(background: str) -> str | None:
    global _theme_name
    theme_name = _style.theme_use()
    if theme_name != _theme_name:
        _styles_by_bg.clear()
        _style_signatures.clear()
        _theme_name = theme_name
    if not _ensure_elements():
        return None
    name = _styles_by_bg.get(background)
    if name is not None:
        try:
            _style.layout(name)                   # still defined in the current Tk theme?
        except tk.TclError:
            name = None
    if name is None:
        name = _styles_by_bg.get(background) or f"{ELEMENT_PREFIX}{len(_styles_by_bg) + 1}.Vertical.TScrollbar"
        _styles_by_bg[background] = name
    _configure_style(name, background)
    return name


def _main_window_scrollbars() -> list[tk.Misc]:
    """Themed vertical scrollbars in EDMC's main window (pop-up windows are left alone)."""
    found, pending = [], list(_root.winfo_children()) if _root is not None else []
    while pending:
        widget = pending.pop()
        try:
            kind = widget.winfo_class()
        except tk.TclError:
            continue
        if kind == "Toplevel":
            continue
        if kind == "TScrollbar":
            try:
                if str(widget.cget("orient")) == "vertical":
                    found.append(widget)
            except tk.TclError:
                pass
        pending.extend(widget.winfo_children())
    return found


def _apply() -> int:
    """Restyle (or restore, when switched off) every themed scrollbar. Returns how many are restyled."""
    global _last_count
    if _root is None or _style is None:
        return 0
    enabled, _, _ = _settings()
    count = 0
    for bar in _main_window_scrollbars():
        path = str(bar)
        try:
            current = str(bar.cget("style"))
            if not enabled:
                original = _original_styles.pop(bar, None)
                if original is not None and current.startswith(ELEMENT_PREFIX):
                    bar.configure(style=original)
                _restore_bar_grid(bar)
                continue
            wanted = _style_for(_background_of(bar))
            if wanted is None:
                continue
            if current != wanted:
                if not current.startswith(ELEMENT_PREFIX):
                    _original_styles[bar] = current
                bar.configure(style=wanted)
                logger.info("Restyled scrollbar %s", path)
            if bar.winfo_manager() == "grid":
                sticky = str(bar.grid_info().get("sticky", ""))
                _bar_grid.setdefault(bar, sticky)
                if sticky != "ns":
                    # NSEW stretches the bar to the width of the shared header
                    # button column. NS preserves its requested thin width.
                    bar.grid_configure(sticky=tk.NS)
            count += 1
        except tk.TclError:
            logger.debug("Scrollbar %s changed while restyling", path, exc_info=True)
    if count != _last_count:
        logger.info("Navigator Interface: %d scrollbar(s) restyled", count)
        _last_count = count
    return count


# --------------------------------------------------------------------------- window size
def _restore_bar_grid(bar: tk.Misc) -> None:
    sticky = _bar_grid.pop(bar, None)
    if sticky is None:
        return
    try:
        manager = bar.winfo_manager()
        if manager in ("grid", ""):
            bar.grid_configure(sticky=sticky)
            if not manager:
                bar.grid_remove()  # Preserve the owner's hidden state.
    except tk.TclError:
        pass


def _restore_controls() -> None:
    for widget, options in list(_control_options.items()):
        try:
            widget.configure(**options)
        except tk.TclError:
            pass
    _control_options.clear()
    _control_fonts.clear()


COLLAPSE_GLYPHS = ("🔼", "🔽")    # the standard EDMC plugin collapse/expand button text


def _collapse_buttons() -> list[tk.Misc]:
    """Every plugin collapse/expand button in EDMC's main window: any stock tk.Button whose
    text is 🔼 or 🔽 (BioScan, Pioneer, Neutron Highway Navigator, ...). BioScan's and
    Pioneer's own view_button are also looked up directly, as before."""
    found: list[tk.Misc] = []
    for module_name, state_name in (("bio_scan.globals", "bioscan_globals"),
                                    ("pioneer.globals", "pioneer_globals")):
        state = getattr(sys.modules.get(module_name), state_name, None)
        button = getattr(state, "view_button", None)
        if isinstance(button, tk.Button):
            found.append(button)
    pending = list(_root.winfo_children()) if _root is not None else []
    while pending:
        widget = pending.pop()
        try:
            kind = widget.winfo_class()
            if kind == "Toplevel":
                continue
            if kind == "Button" and str(widget.cget("text")).strip() in COLLAPSE_GLYPHS \
                    and widget not in found:
                found.append(widget)
            pending.extend(widget.winfo_children())
        except tk.TclError:
            continue
    return found


def _flat_colour() -> str | None:
    """The theme's Normal Text colour when a dark or transparent theme is on (the thin outline of a flat button);
    None on the Default theme, which keeps its native buttons."""
    if _get_int("theme", 0) == 0:
        return None
    try:
        from theme import theme
        return (getattr(theme, "current", None) or {}).get("foreground") or None
    except Exception:
        return None


def _sync_flat_buttons() -> None:
    """Every plain button in a plugin panel is flat with a 1-pixel outline in the Normal Text colour, not Tk's raised
    bevel (whose light top and left edges show white on a dark theme)."""
    colour = _flat_colour()
    if not colour:
        return
    wanted = {"relief": "flat", "borderwidth": 0, "highlightthickness": 1,
              "highlightbackground": colour, "highlightcolor": colour}
    for _identity, _name, panel in _plugin_panels():
        stack = [panel]
        while stack:
            widget = stack.pop()
            try:
                stack.extend(widget.winfo_children())
                if widget.winfo_class() != "Button":
                    continue
                changes = {key: value for key, value in wanted.items() if str(widget.cget(key)) != str(value)}
                if changes:
                    widget.configure(**changes)
            except tk.TclError:
                continue


def _compact_controls() -> None:
    """Compact every plugin's collapse/expand button, including glyph and padding."""
    if not _get_bool(CFG_COMPACT, True):
        if _control_options:
            _restore_controls()
        return
    flat = _flat_colour() is not None
    for button in _collapse_buttons():
        try:
            if button.winfo_toplevel() is not _root:
                continue
        except tk.TclError:
            continue
        options = _control_options.setdefault(button, {})
        for key in ("font", "padx", "pady", "borderwidth", "highlightthickness"):
            options.setdefault(key, button.cget(key))
        font = _control_fonts.get(button)
        if font is None or str(button.cget("font")) != str(font):
            if font is not None:
                options["font"] = button.cget("font")  # EDMC changed theme/font.
            font = tkfont.Font(root=_root, font=options["font"])
            size = int(font.cget("size"))
            scaled_size = max(1, round(abs(size) * CONTROL_SCALE))
            font.configure(size=-scaled_size if size < 0 else scaled_size)
            _control_fonts[button] = font
        wanted = {"font": str(font)}
        for key in ("padx", "pady", "borderwidth", "highlightthickness"):
            wanted[key] = max(0, round(button.winfo_pixels(options[key]) * CONTROL_SCALE))
        if flat:                                       # flat buttons keep their flat edge (see _sync_flat_buttons)
            wanted["borderwidth"], wanted["highlightthickness"] = 0, 1
        changes = {key: value for key, value in wanted.items() if str(button.cget(key)) != str(value)}
        if changes:
            button.configure(**changes)


def _purpose_header_text(native: str, state: Any, brand: str, purpose: str) -> str:
    """The custom header text: the commander's name for a plugin, plus (Hidden) while it is collapsed."""
    buttons = list(_profile_buttons(state.panel))
    hidden = ('(hidden)' in native.casefold() or any(
        str(button.cget('text')).strip()==COLLAPSE_GLYPHS[1] for button in buttons))
    return purpose + (' (Hidden)' if hidden else '')


def _remove_purpose_header(label: tk.Misc) -> None:
    record = _purpose_headers.pop(label)
    if label.configure is record["wrapper"]:
        label.configure = record["configure"]
    if label.config is record["wrapper"]:
        label.config = record["config"]
    try:
        if label.winfo_exists():
            record["configure"](text=record["native"])
    except tk.TclError:
        pass


def _sync_purpose_headers() -> None:
    """Adapt only loaded panel labels, including updates that don't resize them."""
    wanted = {}
    if _custom_headers is not None:
        wanted.update(_custom_headers.targets())
    for label in list(_purpose_headers):
        if label not in wanted:
            _remove_purpose_header(label)
    for label, (state, brand, purpose) in wanted.items():
        record = _purpose_headers.get(label)
        if record is None:
            _install_purpose_header(label, state, brand, purpose)
            record = _purpose_headers[label]
        record.update(state=state, brand=brand, purpose=purpose)
        text = _purpose_header_text(record["native"], state, brand, purpose)
        if str(label.cget("text")) != text:
            record["configure"](text=text)


def _install_purpose_header(label: tk.Misc, state: Any, brand: str, purpose: str) -> None:
    record = dict(native=str(label.cget("text")), configure=label.configure,
                  config=label.config, state=state, brand=brand, purpose=purpose)

    def configure(cnf=None, **kwargs):
        # Both label['text'] and label.configure(text=...) use this method.
        # Retain the owner's latest text so opting out restores it immediately.
        options = dict(cnf) if isinstance(cnf, dict) else cnf
        if isinstance(options, dict) and "text" in options:
            record["native"] = str(kwargs.get("text", options["text"]))
            options["text"] = _purpose_header_text(record["native"], record["state"], record["brand"], record["purpose"])
        if "text" in kwargs:
            record["native"] = str(kwargs["text"])
            kwargs["text"] = _purpose_header_text(record["native"], record["state"], record["brand"], record["purpose"])
        return record["configure"](options, **kwargs)

    record["wrapper"] = configure
    label.configure = label.config = configure
    _purpose_headers[label] = record


def _panel_headers() -> list[tuple[tk.Misc, tk.Misc | None]]:
    """Each plugin panel's header widget and its collapse button (if any).

    The header is the leftmost label/frame in the collapse button's grid row,
    at or left of the button: column 0 (BioScan, Pioneer, Neutron) or the
    middle of a symmetric layout (Radio, Ship Computer). Panels without a
    collapse button use the single frame at the top of their own panel.
    """
    found = []
    for _, _, wrapper in _plugin_panels():
        button = next(iter(_profile_buttons(wrapper)), None)
        parent = button.master if button is not None else None
        if parent is None:
            children = [c for c in wrapper.winfo_children() if c.winfo_manager() == "grid"]
            if len(children) != 1:
                continue
            parent = children[0]
        try:
            gridded = button is not None and button.winfo_manager() == "grid"
            row = int(button.grid_info()["row"]) if gridded else 0
            limit = int(button.grid_info()["column"]) if gridded else 0
            best = None
            for child in parent.winfo_children():
                if child is button or child.winfo_manager() != "grid":
                    continue
                if child.winfo_class() not in ("Label", "Frame"):
                    continue
                info = child.grid_info()
                column = int(info["column"])
                if int(info["row"]) == row and column <= limit and (best is None or column < best[0]):
                    best = (column, child)
            if best is not None:
                found.append((best[1], button))
        except (tk.TclError, KeyError, ValueError):
            continue
    return found


def _collapse_memory() -> dict:
    try:
        saved = json.loads(_get_str(CFG_COLLAPSE_MEMORY, "{}"))
        return saved if isinstance(saved, dict) else {}
    except (ValueError, TypeError):
        return {}


def _other_panels() -> list[tuple[str, tk.Misc]]:
    return [(identity, widget) for identity, _, widget in _plugin_panels()
            if identity.split(":", 1)[1] not in SUITE_FOLDERS
            and not identity.split(":", 1)[1].startswith(SUITE_PREFIXES)]


def _save_collapse_memory() -> None:
    """Remember the collapsed state of non-suite panels after the user toggles one."""
    if _stopped or config.shutting_down:
        return
    saved = _collapse_memory()
    for identity, widget in _other_panels():
        states = [str(button.cget("text")).strip() == COLLAPSE_GLYPHS[1] for button in _profile_buttons(widget)]
        if states:
            saved[identity] = states
    config.set(CFG_COLLAPSE_MEMORY, json.dumps(saved))


def _sync_collapse_memory() -> None:
    """Restore each non-suite panel's last collapsed state once, then watch its button."""
    saved = None
    for identity, widget in _other_panels():
        for index, button in enumerate(_profile_buttons(widget)):
            if button in _collapse_seen:
                continue
            _collapse_seen.add(button)
            if saved is None:
                saved = _collapse_memory()
            wanted = saved.get(identity, [])
            if index < len(wanted):
                current = str(button.cget("text")).strip() == COLLAPSE_GLYPHS[1]
                if current != bool(wanted[index]):
                    button.invoke()
            for sequence in ("<ButtonRelease-1>", "<KeyRelease-space>"):
                button.bind(sequence, lambda _event: _root.after_idle(_save_collapse_memory), add="+")


def _sync_header_alignment() -> None:
    """Centre every header on the full panel width, or left-justify them all.

    Center keeps each plugin's own centred layout; a header beside its collapse
    button (BioScan, Pioneer) is spanned under the button so it centres on the
    same line as the suite's headers. Left moves each header (as one block, so
    Radio's collapsed controls stay with its title) to the panel's left edge.
    """
    mode = _get_str(CFG_HEADER_ALIGN, "center")
    seen = set()
    for header, button in _panel_headers():
        seen.add(header)
        try:
            collapsed = button is not None and str(button.cget("text")).strip() == COLLAPSE_GLYPHS[1]
            left = mode == "left" or (mode == "mixed" and collapsed)
            if mode == "mixed" and button is not None and button not in _align_watch:
                # Re-justify right after the user opens or collapses this panel.
                _align_watch.add(button)
                for sequence in ("<ButtonRelease-1>", "<KeyRelease-space>"):
                    button.bind(sequence, lambda _event: _root.after_idle(_schedule_refresh), add="+")
            info = header.grid_info()
            if header not in _header_grid:
                anchor = str(header.cget("anchor")) if "anchor" in header.keys() else None
                _header_grid[header] = ({"column": int(info.get("column", 0)),
                                         "columnspan": int(info.get("columnspan", 1)),
                                         "sticky": str(info.get("sticky", ""))}, anchor)
            original, anchor = _header_grid[header]
            column, span, sticky = original["column"], original["columnspan"], original["sticky"]
            button_column = None
            if button is not None and button.winfo_manager() == "grid":
                button_column = int(button.grid_info()["column"])
            if left:
                if button_column is not None and button_column > column:
                    span = max(column + span, button_column)   # every cell left of the button
                column = 0
                sticky = sticky.replace("e", "").replace("w", "") + "w"
            elif column == 0 and button_column == 1:
                span = max(span, 2)                    # extend under the button, as the suite's headers do
            if (int(info.get("column", 0)) != column or int(info.get("columnspan", 1)) != span
                    or str(info.get("sticky", "")) != sticky):
                header.grid_configure(column=column, columnspan=span, sticky=sticky)
            if header.winfo_class() == "Label":
                wanted = tk.W if left else (anchor or tk.CENTER)
                if str(header.cget("anchor")) != str(wanted):
                    header.configure(anchor=wanted)
            if button is not None:
                button.lift()                          # keep the collapse button above a spanned header
        except (tk.TclError, KeyError, ValueError):
            continue
    for header in [h for h in _header_grid if h not in seen]:
        _restore_header(header)
    _sync_hidden_suffix(seen)


def _set_label_text(label: tk.Misc, text: str) -> None:
    # tk.Label.configure, not label.configure: purpose headers wrap the latter.
    tk.Label.configure(label, text=text)


def _sync_hidden_suffix(headers: set) -> None:
    """Optionally drop " (Hidden)" from collapsed headers, restoring it when turned off."""
    strip = _get_bool(CFG_HIDE_HIDDEN, False)
    labels = set()
    for header in headers:
        try:
            labels.update(w for w in [header] + list(header.winfo_children()) if w.winfo_class() == "Label")
        except tk.TclError:
            continue
    for label in list(_hidden_text):
        if label not in labels or not strip:
            _restore_hidden_text(label)
    if not strip:
        return
    for label in labels:
        try:
            text = str(label.cget("text"))
            if text.endswith(HIDDEN_SUFFIX):
                short = text[:-len(HIDDEN_SUFFIX)]
                _hidden_text[label] = (text, short)
                _set_label_text(label, short)
        except tk.TclError:
            _hidden_text.pop(label, None)


def _restore_hidden_text(label: tk.Misc) -> None:
    full, short = _hidden_text.pop(label)
    try:
        if label.winfo_exists() and str(label.cget("text")) == short:
            _set_label_text(label, full)
    except tk.TclError:
        pass


def _restore_header(header: tk.Misc) -> None:
    grid, anchor = _header_grid.pop(header)
    try:
        if header.winfo_exists():
            if header.winfo_manager() == "grid":
                header.grid_configure(**grid)
            if anchor is not None:
                header.configure(anchor=anchor)
    except tk.TclError:
        pass


def _bioscan_state() -> Any:
    """Use BioScan's already-loaded UI state; never import/start another plugin.

    These attributes are from the supplied EDMC-BioScan version. A missing or
    changed UI simply leaves the compatibility adjustment inactive.
    """
    return _panel_state("bio_scan.globals", "bioscan_globals")


def _panel_state(module_name: str, state_name: str) -> Any:
    module = sys.modules.get(module_name)
    state = getattr(module, state_name, None)
    frame = getattr(state, "frame", None)
    try:
        if frame is not None and frame.winfo_toplevel() is _root:
            return state
    except (tk.TclError, AttributeError):
        pass
    return None


def _bioscan_configure(widget: tk.Misc, **options: Any) -> None:
    for key, value in options.items():
        current = widget.cget(key)
        if str(current) != str(value):
            _bioscan_options.setdefault(widget, {}).setdefault(key, current)
            widget.configure(**{key: value})


def _restore_bioscan() -> None:
    _stretch_panels([])
    for widget, options in list(_bioscan_options.items()):
        try:
            widget.configure(**options)
        except tk.TclError:
            pass
    for (canvas, item), width in list(_bioscan_windows.items()):
        try:
            canvas.itemconfigure(item, width=width)
        except tk.TclError:
            pass
    for widget, options in list(_bioscan_pack.items()):
        try:
            if widget.winfo_manager() == "pack":
                widget.pack_configure(**options)
        except tk.TclError:
            pass
    _bioscan_options.clear()
    _bioscan_windows.clear()
    _bioscan_pack.clear()
    _panel_viewports.clear()


def _fit_bioscan() -> None:
    """Fit the supplied BioScan/Pioneer UI while leaving data and callbacks alone."""
    if not _get_bool(CFG_BIOSCAN_FIT, True):
        if _bioscan_options or _bioscan_windows:
            _restore_bioscan()
        return
    visible = []
    bio = _bioscan_state()
    # Pioneer hardcodes 100 px; use BioScan's existing height preference for both.
    height_var = getattr(bio, "box_height", None)
    height = max(40, min(2000, int(height_var.get()) if height_var is not None
                         else _get_int("bioscan_box_height", 100)))
    for state, name in ((bio, "BioScan"),
                        (_panel_state("pioneer.globals", "pioneer_globals"), "Pioneer")):
        if state is not None:
            _fit_scroll_panel(state, name)
            canvas = getattr(state, "scroll_canvas", None)
            if isinstance(canvas, tk.Canvas):
                _bioscan_configure(canvas, height=height)
                if canvas.winfo_manager():
                    visible.append(canvas)
    _stretch_panels(visible)


def _stretch_panels(canvases: list[tk.Canvas]) -> None:
    """Pass spare height through EDMC's wrappers to the visible data rows.

    Equal canvas requests and equal row weights share extra height evenly.
    Diff the desired layout so Configure events settle; never re-grid a hidden
    pane. Save and restore only the geometry options we own.
    """
    grids, rows, columns, packs = set(), set(), set(), set()
    for canvas in canvases:
        widget = canvas
        while widget is not _root:
            manager = widget.winfo_manager()
            if manager == "grid":
                grids.add(widget)
                info = widget.grid_info()
                rows.add((widget.master, int(info["row"])))
                start, span = int(info["column"]), int(info["columnspan"])
                # Preserve EDMC's weighted form column when a plugin spans it.
                if not any(int(widget.master.grid_columnconfigure(col)["weight"])
                           and (widget.master, col) not in _stretch_columns
                           for col in range(start, start + span)):
                    columns.add((widget.master, start))
            elif manager == "pack":
                packs.add(widget)
            else:
                break
            widget = widget.master
    for widget in set(_stretch_grid) - grids:
        value = _stretch_grid.pop(widget)
        try:
            manager = widget.winfo_manager()
            if manager in ("", "grid"):
                widget.grid_configure(sticky=value)
                if not manager:
                    widget.grid_remove()
        except tk.TclError:
            pass
    for key in set(_stretch_rows) - rows:
        value = _stretch_rows.pop(key)
        try:
            key[0].grid_rowconfigure(key[1], weight=value)
        except tk.TclError:
            pass
    for key in set(_stretch_columns) - columns:
        value = _stretch_columns.pop(key)
        try:
            key[0].grid_columnconfigure(key[1], weight=value)
        except tk.TclError:
            pass
    for widget in set(_stretch_pack) - packs:
        value = _stretch_pack.pop(widget)
        try:
            if widget.winfo_manager() == "pack":
                widget.pack_configure(**value)
        except tk.TclError:
            pass
    for widget in grids:
        value = str(widget.grid_info()["sticky"])
        _stretch_grid.setdefault(widget, value)
        if value != "nesw":
            widget.grid_configure(sticky="nsew")
    for parent, row in rows:
        weight = int(parent.grid_rowconfigure(row)["weight"])
        _stretch_rows.setdefault((parent, row), weight)
        if weight != 1:
            parent.grid_rowconfigure(row, weight=1)
    for parent, column in columns:
        weight = int(parent.grid_columnconfigure(column)["weight"])
        _stretch_columns.setdefault((parent, column), weight)
        if weight != 1:
            parent.grid_columnconfigure(column, weight=1)
    for widget in packs:
        value = widget.pack_info()
        _stretch_pack.setdefault(widget, {key: value[key] for key in ("expand", "fill")})
        if not bool(value["expand"]) or str(value["fill"]) != tk.BOTH:
            widget.pack_configure(expand=True, fill=tk.BOTH)


def _fit_scroll_panel(state: Any, name: str) -> None:
    if state is None:
        return
    canvas = getattr(state, "scroll_canvas", None)
    label = getattr(state, "values_label", None)
    inner = getattr(state, "scrollable_frame", None)
    if not isinstance(canvas, tk.Canvas) or label is None or inner is None:
        return
    # Column 1 is shared by BioScan's header toggle and the vertical scrollbar.
    # Reserve the wider control, not merely the scrollbar's visible thumb.
    reserve = 0
    for sibling in (getattr(state, "view_button", None), getattr(state, "scrollbar", None)):
        if sibling is not None and sibling.winfo_manager():
            reserve = max(reserve, sibling.winfo_reqwidth())
    border = canvas.winfo_pixels(canvas.cget("borderwidth"))
    highlight = canvas.winfo_pixels(canvas.cget("highlightthickness"))
    edges = 2 * (border + highlight)
    text_scale = _theme_text_scale(label)
    lock_w, width = _layout_width()
    if lock_w and width > 0:
        panel_left = max(0, state.frame.winfo_rootx() - _root.winfo_rootx())
        viewport = max(40, width - panel_left - reserve - edges - 8)
        _panel_viewports[canvas] = max(40, round(viewport / text_scale))
    else:
        base_viewport = _panel_viewports.get(canvas)
        if base_viewport is None:
            if not canvas.winfo_ismapped() or _root.winfo_width() <= 1:
                return  # Wait for a real allocation; no startup 1-pixel measurements.
            requested = canvas.winfo_pixels(canvas.cget("width"))
            wrap = label.cget("wraplength")
            preferred = max(requested, label.winfo_pixels(wrap) if str(wrap) else 0)
            left = max(0, canvas.winfo_rootx() - _root.winfo_rootx())
            available = max(40, _root.winfo_width() - left - reserve - edges)
            base_viewport = max(40, min(preferred, available))
            _panel_viewports[canvas] = base_viewport
        viewport = max(40, math.ceil(base_viewport * text_scale))
        # Never derive an automatic geometry request from the size it produced.
        # That feedback shrank the viewport on every Configure and could keep
        # EDMC's update_idletasks() in Settings from ever returning.
    request_width = viewport
    if not _root.overrideredirect() and canvas.winfo_ismapped():
        # Follow the allocation without feeding it back into the size request.
        viewport = max(40, canvas.winfo_width() - edges)
    panel_width = viewport + reserve + edges
    for attribute, available in (("label", viewport), ("total_label", panel_width - 4)):
        widget = getattr(state, attribute, None)
        if widget is not None:
            _bioscan_configure(widget, wraplength=max(36, available - 4))
    _bioscan_configure(label, wraplength=max(36, viewport - 4))
    _bioscan_configure(canvas, width=request_width)
    # BioScan packs the label on the left without expand=True. Once the canvas
    # window has a fixed width, that exposes the otherwise unused TFrame area
    # as a white strip beside the correctly styled orange scrollbar.
    if label.winfo_manager() == "pack":
        packing = label.pack_info()
        _bioscan_pack.setdefault(label, {key: packing[key] for key in ("expand", "fill")})
        if not bool(packing["expand"]) or str(packing["fill"]) != tk.BOTH:
            label.pack_configure(expand=True, fill=tk.BOTH)
    if isinstance(inner, ttk.Frame):
        background = str(canvas.cget("background"))
        signature = (_style.theme_use(), background)
        style_name = f"{ELEMENT_PREFIX}.{name}.TFrame"
        if signature != _panel_style_signatures.get(style_name):
            _style.configure(style_name, background=background, borderwidth=0, relief="flat")
            _style.map(style_name, background=[("disabled", background), ("active", background)])
            _panel_style_signatures[style_name] = signature
        _bioscan_configure(inner, style=style_name)
    for item in canvas.find_all():
        if canvas.type(item) == "window" and str(canvas.itemcget(item, "window")) == str(inner):
            current = canvas.itemcget(item, "width")
            if float(current) != viewport:
                _bioscan_windows.setdefault((canvas, item), str(current))
                canvas.itemconfigure(item, width=viewport)


def _theme_text_scale(label: tk.Misc) -> float:
    """Keep Euro Caps at EDMC's chosen size; compensate its wider glyphs.

    The cached viewport is a normal-theme pixel baseline. Font measurements
    produce a stable theme multiplier; live text and current window geometry
    do not feed back into it. An explicit width lock takes precedence.
    """
    if not _get_bool(CFG_THEME_WIDTH, True):
        return 1.0
    try:
        value = label.cget("font")
        if not str(value):
            style = str(label.cget("style")) or label.winfo_class()
            value = _style.lookup(style, "font") or "TkDefaultFont"
        if str(value) == "TkDefaultFont":
            return 1.0  # It is already the normal-theme baseline.
        current = tkfont.Font(root=_root, font=value)
        actual = current.actual()
        if str(actual["family"]).casefold() != "euro caps":
            return 1.0
        regular = tkfont.nametofont("TkDefaultFont", root=_root)
        baseline = regular.actual()
        signature = (tuple(sorted(actual.items())), tuple(sorted(baseline.items())),
                     str(_root.tk.call("tk", "scaling")))
        scale = _font_width_scales.get(signature)
        if scale is None:
            # Representative EDMC labels plus letters/numerals. Use a fixed
            # corpus so journal updates cannot change the window's scale.
            samples = (
                "Bacterium Acies - White: 5.00 MCr",
                "Biological Signals (Unmapped):",
                "Estimated System Value: 66.9 kCr",
                "Maximum System Value: 318.3 kCr",
                "Unsold System Value: 9.5 MCr to 10.0 MCr",
                "A 3 (1) ◇ A 4 (1) ◇ A 5 (1) ◇ B 1 (1)",
                "abcdefghijklmnopqrstuvwxyz 0123456789",
            )
            ratio = max(current.measure(text) / max(1, regular.measure(text)) for text in samples)
            scale = max(1.0, ratio * 1.02)  # Small allowance for pixel rounding.
            _font_width_scales[signature] = scale
            logger.info("Euro Caps pane width compensation: %.1f%%", (scale - 1) * 100)
        return scale
    except (tk.TclError, KeyError, ValueError):
        return 1.0


def _size_settings() -> tuple[bool, int, bool, int]:
    return (_get_bool(CFG_LOCK_W, False), _get_int(CFG_WIDTH_PX, 0),
            _get_bool(CFG_LOCK_H, False), _get_int(CFG_HEIGHT_PX, 0))


def _layout_width() -> tuple[bool, int]:
    if not _root.overrideredirect():
        # Native resizing owns normal-theme geometry, regardless of saved locks.
        return False, 0
    if _manual_size is not None:
        return True, _manual_size[0]
    lock_w, width, _, _ = _size_settings()
    return lock_w, width


def _main_window_labels() -> list[tk.Misc]:
    found, pending = [], list(_root.winfo_children()) if _root is not None else []
    while pending:
        widget = pending.pop()
        try:
            kind = widget.winfo_class()
        except tk.TclError:
            continue
        if kind == "Toplevel":
            continue
        if kind in ("Label", "TLabel"):
            found.append(widget)
        pending.extend(widget.winfo_children())
    return found


def _wrap_text(width: int | None) -> None:
    """Wrap every text label to fit the window (width None = undo our wrapping)."""
    if width is None:
        for label in _main_window_labels():
            if label in _wrapped:
                try:
                    label.configure(wraplength=_wrapped.pop(label))
                except tk.TclError:
                    _wrapped.pop(label, None)
        return
    left = _root.winfo_rootx()
    states = (_bioscan_state(), _panel_state("pioneer.globals", "pioneer_globals")) if _get_bool(CFG_BIOSCAN_FIT, True) else ()
    owned = tuple(getattr(state, name, None) for state in states for name in ("label", "values_label", "total_label"))
    for label in _main_window_labels():
        try:
            if label in owned:
                continue  # BioScan needs its column/viewport widths, not the full root width.
            if getattr(label, "navigator_no_wrap", False):
                continue  # plugins can mark one-line labels (e.g. Ship Radio titles) to keep them unwrapped
            if not label.winfo_ismapped():
                continue
            space = max(80, width - (label.winfo_rootx() - left) - 8)
            if _core_button is not None and _app_frame is not None and label is _app_frame.children.get("cmdr"):
                space = max(1, space - _core_button.winfo_reqwidth() - 4)
            current = label.cget("wraplength")
            if str(current) != str(space):
                _wrapped.setdefault(label, current)
                label.configure(wraplength=space)
        except tk.TclError:
            pass


def _resize_text_colour() -> str:
    """Use an ordinary EDMC field caption, rather than a link/scrollbar colour."""
    if _app_frame is not None:
        for name in ("cmdr_label", "ship_label", "system_label", "station_label"):
            label = _app_frame.children.get(name)
            if label is not None:
                return str(label.cget("foreground"))
        for label in _main_window_labels():
            if label is not _resize_grip:
                return str(label.cget("foreground"))
    return _get_str("dark_text", DEFAULT_COLOUR)


def _sync_resize_space(visible: bool) -> None:
    """Reserve a real bottom row below plugins and footers, in any panel order."""
    global _resize_space
    if _app_frame is None:
        return
    if not visible:
        if _resize_space is not None:
            _resize_space.grid_remove()
        return
    if _resize_space is None:
        _resize_space = tk.Frame(_app_frame, name="navinterface_resize_space",
                                 height=RESIZE_GRIP_SIZE, borderwidth=0, highlightthickness=0)
    row, columns = 0, 1
    for widget in _app_frame.winfo_children():
        if widget is _resize_space or widget.winfo_manager() != "grid":
            continue
        info = widget.grid_info()
        row = max(row, int(info["row"]) + int(info.get("rowspan", 1)))
        columns = max(columns, int(info["column"]) + int(info.get("columnspan", 1)))
    _resize_space.configure(background=_app_frame.cget("background"))
    line = getattr(_resize_space, "navigator_line", None)
    if line is None or not line.winfo_exists():
        # A thin line in the Normal Text colour across the top of the bottom row (the resize triangle sits in the row
        # below it), so the window is capped at the foot as it is at the head.
        line = _resize_space.navigator_line = tk.Frame(_resize_space, height=1, borderwidth=0, highlightthickness=0)
        line.place(x=0, y=0, relwidth=1, height=1)
    line.configure(background=_resize_text_colour())
    wanted = dict(row=row, column=0, columnspan=columns, sticky=tk.EW)
    current = _resize_space.grid_info()
    if not current or any(str(current.get(key)) != str(value) for key, value in wanted.items()):
        _resize_space.grid(**wanted)


def _update_resize_grip() -> None:
    """Borderless EDMC themes have no native resize border; supply a corner."""
    global _resize_grip, _resize_image, _resize_colour
    size = RESIZE_GRIP_SIZE
    if _resize_grip is None:
        _resize_image = tk.PhotoImage(master=_root, width=size, height=size)
        _resize_grip = tk.Label(_root, image=_resize_image, text="",
                                borderwidth=0, highlightthickness=0, padx=0, pady=0, cursor="size_nw_se" if sys.platform == "win32" else "bottom_right_corner")
        _resize_grip.bind("<ButtonPress-1>", _resize_start)
        _resize_grip.bind("<B1-Motion>", _resize_move)
        _resize_grip.bind("<ButtonRelease-1>", _resize_end)
    borderless = bool(_root.overrideredirect())
    # Keep the reservation while minimized so the requested size stays stable.
    _sync_resize_space(borderless)
    if borderless and _root.state() == "normal":
        colour = _resize_text_colour()
        if _resize_colour != colour:
            # PhotoImage needs RGB even when Tk labels use Windows system colours.
            paint = "#%02x%02x%02x" % tuple(v // 257 for v in _root.winfo_rgb(colour))
            _resize_image.blank()
            for y in range(size):
                _resize_image.put(paint, to=(size-1-y, y, size, y+1))
            _resize_colour = colour
        background = _background_of(_resize_grip)
        try:
            if not _root.attributes("-transparentcolor") and _app_frame is not None:
                background = str(_app_frame.cget("background"))
        except tk.TclError:
            pass
        _resize_grip.configure(background=background, foreground=colour)
        _resize_grip.place(relx=1, rely=1, anchor="se", width=size, height=size)
        _resize_grip.lift()
    else:
        if _resize_drag is not None:
            _resize_end()
        _resize_grip.place_forget()


def _resize_start(event: tk.Event) -> str:
    global _resize_drag
    if _root is None or not _root.overrideredirect() or _root.state() != "normal":
        return "break"
    low, high, _ = _window_defaults
    _resize_drag = (event.x_root, event.y_root, _root.winfo_width(), _root.winfo_height())
    # Explicit dragging can change a locked dimension. Reapply its new value
    # on release, rather than fighting the drag with the previous min/max.
    _root.minsize(1, 1)
    _root.maxsize(*high)
    _root.minsize(low[0], _height_floor(low[1]))
    _root.resizable(True, True)
    _resize_grip.grab_set()
    return "break"


def _resize_move(event: tk.Event) -> str:
    global _manual_size
    if _resize_drag is None:
        return "break"
    x, y, width, height = _resize_drag
    low, high, _ = _window_defaults
    width = max(max(150, low[0]), min(high[0], width + event.x_root - x))
    height = max(max(80, _height_floor(low[1])), min(high[1], height + event.y_root - y))
    _manual_size = (width, height)
    # A size-only request preserves the current position. Negative geometry
    # offsets mean distance from the far edge, not negative screen coordinates.
    _root.geometry(f"{width}x{height}")
    return "break"


def _resize_end(event: tk.Event | None = None) -> str:
    global _resize_drag
    if _resize_drag is None:
        return "break"
    if event is not None:
        _resize_move(event)
    _resize_drag = None
    try:
        _resize_grip.grab_release()
    except tk.TclError:
        pass
    if _manual_size is not None:
        lock_w, _, lock_h, _ = _size_settings()
        if lock_w:
            config.set(CFG_WIDTH_PX, _manual_size[0])
        if lock_h:
            config.set(CFG_HEIGHT_PX, _manual_size[1])
        # Settings may already be open when the main window is resized.
        try:
            if "width_px" in _prefs:
                _prefs["width_px"].set(str(_manual_size[0]))
        except tk.TclError:
            pass
    _schedule_refresh()
    return "break"


_constraint_target = None

def _constrain_size() -> None:
    """Let the window manager enforce locks, rather than correcting every 250 ms."""
    global _constraint_signature, _constraint_target
    if _root is None or _window_defaults is None or _resize_drag is not None:
        return
    if _master_scroll is not None and _master_scroll.active:
        return                       # the master scroll holds the window to the screen height
    # Default EDMC skin has a native frame. Do not apply the borderless resize
    # patch or its width/height locks there. Undo our previous constraints once
    # on a theme transition, then leave native geometry entirely to EDMC.
    if not _root.overrideredirect():
        if _constraint_signature is not None:
            low, high, resizable = _window_defaults
            _root.minsize(1, 1)
            _root.maxsize(*high)
            _root.minsize(*low)
            _root.resizable(*resizable)
            _constraint_signature = None
            _constraint_target = None
        return
    lock_w, width, lock_h, height = _size_settings()
    lock_w = lock_w and width > 0
    lock_h = lock_h and height > 0
    signature = (lock_w, width, lock_h, height)
    changed = signature != _constraint_signature
    if changed:
        was_locked = _constraint_signature is not None and (
            _constraint_signature[0] or _constraint_signature[2])
        low, high, resizable = _window_defaults
    else:
        low, high, resizable = _root.minsize(), _root.maxsize(), _root.resizable()
    wanted_min = (width if lock_w else low[0], height if lock_h else low[1])
    wanted_max = (width if lock_w else high[0], height if lock_h else high[1])
    wanted_resize = (False if lock_w else resizable[0], False if lock_h else resizable[1])
    # EDMC's theme.apply() writes minsize itself, including after our settings
    # callback. Check the actual constraints on layout events, not just config.
    # Otherwise conflicting min/max sizes can make geometry() generate an
    # endless chain of Configure events even without a repeating timer.
    if (_root.minsize() != wanted_min or _root.maxsize() != wanted_max
            or _root.resizable() != wanted_resize):
        # Reset first so transitions from one fixed size to another don't leave
        # minimum > maximum. Unlocked axes recover their original constraints.
        _root.minsize(1, 1)
        _root.maxsize(*wanted_max)
        _root.minsize(*wanted_min)
        _root.resizable(*wanted_resize)
    if changed:
        _constraint_signature = signature
        if was_locked and not lock_w and not lock_h:
            _root.geometry("")
    if (lock_w or lock_h) and _root.state() != "iconic":
        target_w = width if lock_w else (_manual_size[0] if _manual_size else _root.winfo_reqwidth())
        target_h = height if lock_h else (_manual_size[1] if _manual_size else _root.winfo_reqheight())
        target = (target_w,target_h)
        # A pending Windows geometry request can generate intermediate Configure
        # allocations. Reissuing it from every one of those events can oscillate
        # between the natural and locked size. Submit each target once.
        if changed or target != _constraint_target:
            _constraint_target = target
            if (_root.winfo_width(),_root.winfo_height()) != target:
                _root.geometry(f"{target_w}x{target_h}")


def _refresh() -> None:
    """One coalesced update after an actual layout/theme/settings event."""
    global _pending
    _pending = None
    if _stopped or config.shutting_down or _root is None:
        return
    try:
        _apply()
    except Exception:
        logger.exception("Scrollbar styling failed")
    try:
        _sync_chrome()
        _sync_core_fields()
        _sync_undocked()
        _sync_header_extras()
        _sync_purpose_headers()
        _sync_collapse_memory()
        _sync_header_alignment()
        _compact_controls()
        _sync_flat_buttons()
        if _map_macros is not None:
            _map_macros.sync()
        _sync_footer()
        _sync_plugin_order()
        _fit_bioscan()
        _update_resize_grip()
        if _master_scroll is not None:
            _master_scroll.sync(_get_bool(CFG_MASTER_SCROLL, True))
        lock_w, width = _layout_width()
        _wrap_text(width if lock_w and width > 0 else None)
        _constrain_size()
        if _panel_backgrounds is not None:
            _panel_backgrounds.sync(_plugin_panels())
    except Exception:
        logger.exception("Window layout update failed")


def _schedule_refresh(event: tk.Event | None = None) -> None:
    global _pending
    if _stopped or _root is None or config.shutting_down:
        return
    if event is not None:
        try:
            if event.widget.winfo_toplevel() is not _root:
                return  # Settings and other pop-ups have their own layout.
        except (tk.TclError, AttributeError):
            return
    if _pending is None:
        _pending = _root.after_idle(_refresh)


def _destroyed(event: tk.Event) -> None:
    global _status_widget, _status_trace, _status_grid, _status_options, _status_expired
    _hidden_controls.pop(event.widget, None)
    _chrome_widgets.pop(event.widget, None)
    _plugin_rows.pop(event.widget, None)
    if event.widget is _status_widget:
        _cancel_status_timer()
        if _status_trace is not None:
            try:
                _root.deletecommand(_status_trace)
            except tk.TclError:
                pass
        _status_widget = _status_trace = None
        _status_grid = {}
        _status_options = {}
        _status_expired = False
    _original_styles.pop(event.widget, None)
    _wrapped.pop(event.widget, None)
    _bioscan_options.pop(event.widget, None)
    _bioscan_pack.pop(event.widget, None)
    _panel_viewports.pop(event.widget, None)
    _bar_grid.pop(event.widget, None)
    _control_options.pop(event.widget, None)
    _control_fonts.pop(event.widget, None)
    for key in list(_bioscan_windows):
        if key[0] is event.widget:
            _bioscan_windows.pop(key, None)


# --------------------------------------------------------------------------- EDMC hooks
def plugin_start3(plugin_dir: str) -> str:
    if not _get_bool(CFG_ALT_MIGRATED, False):
        # Preserve a 1.0.4 user's compact look, with Alt control instead of focus.
        config.set(CFG_HIDE_BOTH, _get_bool(CFG_HIDE_BOTH, _get_bool(CFG_HIDE_CHROME, False)))
        config.set(CFG_HIDE_MENU, _get_bool(CFG_HIDE_MENU, False))
        config.set(CFG_HIDE_CHROME, False)
        config.set(CFG_ALT_MIGRATED, True)
    # The user requested half the previous scrollbar width. Convert an existing
    # setting once; subsequent starts and explicit preference edits keep it.
    if not _get_bool(CFG_HALF_WIDTH_DONE, False):
        old_width = _get_int(CFG_WIDTH, 8)
        config.set(CFG_WIDTH, max(2, min(24, round(old_width / 2))))
        config.set(CFG_HALF_WIDTH_DONE, True)
    if not _get_bool(CFG_GROW_WIDTH_DONE, False):
        old_width = _get_int(CFG_WIDTH, 4)
        config.set(CFG_WIDTH, max(2, min(24, round(old_width * 1.25))))
        config.set(CFG_GROW_WIDTH_DONE, True)
    _migrate_folders()
    global _map_macros
    # Created now (before any plugin builds its panel) so plugins can ask for their header button;
    # the window is attached in plugin_app.
    _map_macros = MapMacros(None, config, logger)
    _map_macros.colours = navigator_status_colours
    global _theme_font
    _theme_font = ThemeFont(config, logger)
    if not _theme_font.install():
        logger.info("EDMC's theme has no font step to wrap; the text style option has no effect")
    logger.info("%s %s loaded", TITLE, VERSION)
    return TITLE


def _migrate_folders() -> None:
    """Carry folder-keyed choices over to the phase 3 folder names. Safe to run every start:
    only old names are rewritten, and an existing new-name entry is never overwritten."""
    def renamed(identity):
        if isinstance(identity, str) and identity.startswith("folder:"):
            return "folder:" + _renamed_folder(identity[7:])
        return identity

    def rekey(mapping):
        result = {}
        for key, value in mapping.items():
            result.setdefault(renamed(key), value)
        for key, value in mapping.items():   # a new-name entry wins over its old-name twin
            if renamed(key) == key:
                result[key] = value
        return result

    order = _saved_panel_order()
    moved = list(dict.fromkeys(renamed(identity) for identity in order))
    if moved != order:
        config.set(CFG_PANEL_ORDER, json.dumps(moved))
    profiles = _layout_profiles()
    changed = False
    for profile in profiles.values():
        if not isinstance(profile, dict):
            continue
        if isinstance(profile.get("order"), list):
            new = list(dict.fromkeys(renamed(identity) for identity in profile["order"]))
            changed |= new != profile["order"]
            profile["order"] = new
        if isinstance(profile.get("collapsed"), dict):
            new = rekey(profile["collapsed"])
            changed |= new != profile["collapsed"]
            profile["collapsed"] = new
    if changed:
        config.set("NavInterface_LayoutProfiles", json.dumps(profiles))
    for key in (CFG_COLLAPSE_MEMORY, "NavInterface_CustomHeaders"):
        try:
            saved = json.loads(_get_str(key, "{}"))
        except (ValueError, TypeError):
            continue
        if isinstance(saved, dict) and rekey(saved) != saved:
            config.set(key, json.dumps(rekey(saved), ensure_ascii=False))
    for old, new in FOLDER_RENAMES.items():   # High Contrast Background choices
        if _get_bool("NavInterface_HighContrast_" + old, False) and not _get_bool("NavInterface_HighContrast_" + new, False):
            config.set("NavInterface_HighContrast_" + new, True)


def plugin_app(parent: tk.Frame) -> None:
    """Watch main-window events; no repeating timers or new visible panel."""
    global _root, _style, _stopped, _window_defaults, _app_frame, _settings_compat, _custom_headers
    global _color_schemes, _window_memory, _panel_backgrounds, _map_macros
    if _root is not None:
        return None
    _root = parent.winfo_toplevel()
    if _map_macros is None:
        _map_macros = MapMacros(_root, config, logger)
    _map_macros.root = _root
    _app_frame = _edmc_frame(parent)
    _style = ttk.Style(_root)
    _settings_compat = SettingsCompat(_root, config)
    _panel_backgrounds = PanelBackgrounds(_root, config)
    _window_memory = WindowMemory(_root, config)
    _custom_headers = CustomHeaders(globals())
    _color_schemes = ColorSchemes(config, logger)
    _window_defaults = (_root.minsize(), _root.maxsize(), _root.resizable())
    global _master_scroll, _hover_timer
    _master_scroll = MasterScroll(_root, lambda: _app_frame, _scroll_colour,
                                  _scroll_side, logger, RESIZE_GRIP_SIZE,
                                  _chosen_height, _scroll_bar)
    _stopped = False
    for sequence in ("<Configure>", "<Map>", "<Unmap>", "<<ThemeChanged>>"):
        _bindings.append((sequence, _root.bind(sequence, _schedule_refresh, add="+")))
    _bindings.append(("<Destroy>", _root.bind("<Destroy>", _destroyed, add="+")))
    for sequence in ("<Enter>", "<Leave>", "<FocusIn>", "<FocusOut>"):
        _bindings.append((sequence, _root.bind(sequence, _hover_event, add="+")))
    for sequence, handler in (("<KeyPress-Alt_L>", _alt_press), ("<KeyPress-Alt_R>", _alt_press),
                              ("<KeyRelease-Alt_L>", _alt_release), ("<KeyRelease-Alt_R>", _alt_release),
                              ("<KeyPress>", _alt_other_key), ("<FocusOut>", _alt_focus_out)):
        _bindings.append((sequence, _root.bind(sequence, handler, add="+")))
    _schedule_refresh()
    if _hover_timer is not None:
        try:
            _root.after_cancel(_hover_timer)
        except tk.TclError:
            pass
    _hover_timer = _root.after(HOVER_POLL_MS, _hover_poll)
    return None


def plugin_stop() -> None:
    """Remove only our handlers and cancel outstanding work on shutdown."""
    global _master_scroll, _hover_timer
    if _master_scroll is not None:
        _master_scroll.shutdown()
        _master_scroll = None
    global _stopped, _pending, _root, _style, _window_defaults, _constraint_signature, _theme_name
    global _resize_grip, _resize_space, _resize_drag, _manual_size, _resize_image, _resize_colour
    global _app_frame, _chrome_menu, _chrome_theme, _native_caption
    global _chrome_mode_seen, _chrome_revealed, _chrome_transparency, _alt_down, _alt_used
    global _settings_compat, _custom_headers, _window_memory, _panel_backgrounds, _map_macros, _hover_timer
    _stopped = True
    if _hover_timer is not None and _root is not None:
        try:
            _root.after_cancel(_hover_timer)
        except tk.TclError:
            pass
        _hover_timer = None
    if _theme_font is not None:
        _theme_font.uninstall()
    if _map_macros is not None:
        _map_macros.close()
        _map_macros = None
    if _panel_backgrounds is not None:
        _panel_backgrounds.close()
        _panel_backgrounds = None
    if _window_memory is not None:
        _window_memory.close()
        _window_memory = None
    if _settings_compat is not None:
        _settings_compat.close()
        _settings_compat = None
    _custom_headers = None
    root = _root
    if root is not None:
        resume_size = None
        try:
            if _native_caption is not None and root.state() == "iconic":
                resume_size = _native_caption[2]
            _sync_chrome(force_show=True)
        except tk.TclError:
            pass
        for label in list(_hidden_text):
            _restore_hidden_text(label)
        for label in list(_purpose_headers):
            _remove_purpose_header(label)
        for header in list(_header_grid):
            _restore_header(header)
        _restore_plugin_rows()
        _restore_core_fields(remove_button=True)
        _restore_footer()
        if _resize_space is not None:
            try:
                _resize_space.destroy()
            except tk.TclError:
                pass
        if _resize_grip is not None:
            try:
                _resize_grip.grab_release()
                _resize_grip.destroy()
            except tk.TclError:
                pass
        if _pending is not None:
            try:
                root.after_cancel(_pending)
            except tk.TclError:
                pass
        for sequence, binding in _bindings:
            try:
                root.unbind(sequence, binding)
            except tk.TclError:
                pass
        for bar, original in list(_original_styles.items()):
            try:
                if str(bar.cget("style")).startswith(ELEMENT_PREFIX):
                    bar.configure(style=original)
            except tk.TclError:
                pass
        for bar in list(_bar_grid):
            _restore_bar_grid(bar)
        _restore_bioscan()
        _restore_controls()
        try:
            _wrap_text(None)
        except tk.TclError:
            pass  # EDMC may already have destroyed the root during shutdown.
        if _window_defaults is not None:
            try:
                low, high, resizable = _window_defaults
                root.minsize(1, 1)
                root.maxsize(*high)
                root.minsize(*low)
                root.resizable(*resizable)
            except tk.TclError:
                pass
        if resume_size is not None:
            # Windows applies restored caption/menu extents only after a
            # minimized window maps. Finish this one restoration there; no
            # polling, activation or forced deiconification during shutdown.
            def restore_mapped_size(event: tk.Event) -> None:
                if event.widget is not root:
                    return
                root.unbind("<Map>", restore_binding)
                def finish() -> None:
                    try:
                        root.geometry(f"{resume_size[0]}x{resume_size[1]}")
                    except tk.TclError:
                        pass
                root.after_idle(finish)
            restore_binding = root.bind("<Map>", restore_mapped_size, add="+")
    _pending = None
    _bindings.clear()
    _hover_bindings.clear()
    _chrome_widgets.clear()
    _chrome_menu = _chrome_theme = _native_caption = None
    _chrome_mode_seen = _chrome_transparency = None
    _chrome_revealed = _alt_down = _alt_used = False
    _original_styles.clear()
    _wrapped.clear()
    _styles_by_bg.clear()
    _style_signatures.clear()
    _window_defaults = _constraint_signature = _theme_name = None
    _panel_style_signatures.clear()
    _font_width_scales.clear()
    _root = _style = None
    _resize_grip = _resize_space = _resize_drag = _manual_size = None
    _resize_image = _resize_colour = None
    _app_frame = None
    _plugin_rows.clear()
    _thumb_images.clear()


def navigator_scroll_settings(parent: tk.Misc, width: int = 660, height: int = 500) -> tk.Frame:
    """Create a shared scrollable settings page and return its outer frame.

    Plugins add their own settings to ``outer.navigator_settings_content`` and
    return ``outer`` from ``plugin_prefs``. Scrollbar styling and wheel handling
    stay here so suite pages do not carry their own implementations.
    """
    outer = nb.Frame(parent)
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(0, weight=1)
    canvas = tk.Canvas(outer, width=width, height=height, highlightthickness=0)
    canvas.grid(row=0, column=0, sticky=tk.NSEW)
    scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
    scrollbar.grid(row=0, column=1, sticky=tk.NS)
    canvas.configure(yscrollcommand=scrollbar.set)
    content = nb.Frame(canvas)
    item = canvas.create_window(0, 0, window=content, anchor=tk.NW)
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
    content.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
    try:
        from theme import theme
        theme.register(content)
    except (ImportError, AttributeError, tk.TclError):
        pass
    outer.navigator_settings_content = content
    outer.navigator_settings_canvas = canvas

    def wheel(event: Any) -> str:
        direction = -1 if getattr(event, "delta", 0) > 0 or getattr(event, "num", None) == 4 else 1
        canvas.yview_scroll(direction * 3, "units")
        return "break"

    def bind_wheel(widget: tk.Misc) -> None:
        if not isinstance(widget, (ttk.Treeview, tk.Text, tk.Listbox, tk.Scale,
                                   ttk.Scale, ttk.Combobox)):
            for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                widget.bind(sequence, wheel, add="+")
        for child in widget.winfo_children():
            bind_wheel(child)

    def bind_after_build() -> None:
        try:
            if content.winfo_exists():
                bind_wheel(content)
        except tk.TclError:
            pass

    # plugin_prefs populates this content frame synchronously after the hook
    # returns; one idle callback binds the completed widget tree.
    content.after_idle(bind_after_build)
    return outer


def plugin_prefs(parent: nb.Notebook, cmdr: str, is_beta: bool) -> tk.Frame:
    enabled, colour, width = _settings()
    outer = navigator_scroll_settings(parent)
    frame = outer.navigator_settings_content
    canvas = outer.navigator_settings_canvas
    frame.columnconfigure(1, weight=1)
    _prefs['settings_canvas'] = canvas
    _prefs["enabled"] = tk.BooleanVar(value=enabled)
    _prefs["colour"] = tk.StringVar(value=colour)
    _prefs["width"] = tk.StringVar(value=str(width))
    _prefs["compact"] = tk.BooleanVar(value=_get_bool(CFG_COMPACT, True))
    Entry = getattr(nb, "Entry", ttk.Entry)

    nb.Label(frame, text="* EDMC Limitation:  Some visual customization features will not work unless you switch "
                         "to the Dark or Transparent themes under Settings->Appearance->Theme *",
             wraplength=620, justify=tk.LEFT).grid(row=0, column=0, columnspan=4, sticky=tk.W, padx=10, pady=(10, 0))
    nb.Label(frame, text="Scrollbars").grid(row=2, column=0, columnspan=3, sticky=tk.W, padx=10, pady=(10, 2))
    nb.Checkbutton(frame, text="Restyle scrollbars in EDMC's window (all plugin panels)",
                   variable=_prefs["enabled"]).grid(row=3, column=0, columnspan=3, sticky=tk.W, padx=10)

    _prefs["mode"] = tk.StringVar(value=_mode())
    Radio = getattr(nb, "Radiobutton", ttk.Radiobutton)
    Radio(frame, text="Hide them completely (scroll with the mouse wheel over the list)",
          variable=_prefs["mode"], value="hidden").grid(row=10, column=0, columnspan=4, sticky=tk.W, padx=24)
    Radio(frame, text="Show a thin handle in the colour below",
          variable=_prefs["mode"], value="handle").grid(row=11, column=0, columnspan=4, sticky=tk.W, padx=24)
    nb.Label(frame, text="Handle colour").grid(row=12, column=0, sticky=tk.W, padx=10, pady=4)
    Entry(frame, textvariable=_prefs["colour"], width=10).grid(row=12, column=1, sticky=tk.W)
    swatch = tk.Label(frame, width=3, relief=tk.SOLID, bd=1)
    swatch.navigator_color_preview = True      # dark Settings styling must not repaint it
    swatch.grid(row=12, column=2, sticky=tk.W, padx=6)

    def refresh_swatch(*_args: Any) -> None:
        try:
            swatch.configure(background=_prefs["colour"].get().strip() or DEFAULT_COLOUR)
        except tk.TclError:
            pass                                  # half-typed colour; ignore until valid
    _prefs["colour"].trace_add("write", refresh_swatch)
    refresh_swatch()

    if colorchooser is not None:
        def pick() -> None:
            chosen = colorchooser.askcolor(color=_prefs["colour"].get(), parent=frame,
                                           title="Scrollbar handle colour")[1]
            if chosen:
                _prefs["colour"].set(chosen)
        ttk.Button(frame, text="Pick…", command=pick).grid(row=12, column=3, sticky=tk.W)

    nb.Label(frame, text="Handle width (px)").grid(row=13, column=0, sticky=tk.W, padx=10, pady=4)
    Entry(frame, textvariable=_prefs["width"], width=5).grid(row=13, column=1, sticky=tk.W)
    nb.Checkbutton(frame, text="Compact plugin collapse/expand buttons (🔼/🔽 on every plugin panel)",
                   variable=_prefs["compact"]).grid(row=14, column=0, columnspan=4, sticky=tk.W, padx=10)
    lock_w, width, lock_h, _ = _size_settings()
    _prefs["lock_w"] = tk.BooleanVar(value=lock_w)
    _prefs["width_px"] = tk.StringVar(value=str(width) if width > 0 else "")
    _prefs["lock_h"] = tk.BooleanVar(value=lock_h)
    _prefs["bioscan_fit"] = tk.BooleanVar(value=_get_bool(CFG_BIOSCAN_FIT, True))
    _prefs["theme_width"] = tk.BooleanVar(value=_get_bool(CFG_THEME_WIDTH, True))
    nb.Label(frame, text="Window").grid(row=20, column=0, columnspan=3, sticky=tk.W, padx=10, pady=(14, 2))
    dark_only: list = []      # (widget, enabled state): greyed out while the Default theme is chosen
    lock_w_box = nb.Checkbutton(frame, text="Keep dark/transparent window width fixed (text wraps to fit)",
                                variable=_prefs["lock_w"])
    lock_w_box.grid(row=21, column=0, columnspan=4, sticky=tk.W, padx=10)
    nb.Label(frame, text="Width (px)").grid(row=22, column=0, sticky=tk.W, padx=10, pady=4)
    width_entry = Entry(frame, textvariable=_prefs["width_px"], width=6)
    width_entry.grid(row=22, column=1, sticky=tk.W)
    nb.Label(frame, text="blank = use the current width").grid(row=22, column=2, columnspan=2, sticky=tk.W)
    lock_h_box = nb.Checkbutton(frame, text="Also keep dark/transparent height fixed (at current height)",
                                variable=_prefs["lock_h"])
    lock_h_box.grid(row=23, column=0, columnspan=4, sticky=tk.W, padx=10)
    dark_only.extend(((lock_w_box, tk.NORMAL), (width_entry, tk.NORMAL), (lock_h_box, tk.NORMAL)))
    if _bioscan_state() is not None or _panel_state("pioneer.globals", "pioneer_globals") is not None:
        nb.Checkbutton(frame, text="Fit BioScan/Pioneer panes and share available height equally",
                       variable=_prefs["bioscan_fit"]).grid(row=24, column=0, columnspan=4, sticky=tk.W,
                                                            padx=10, pady=(8, 0))
    theme_width_box = nb.Checkbutton(frame, text="Keep similar text wrapping in dark/transparent themes",
                                     variable=_prefs["theme_width"])
    theme_width_box.grid(row=25, column=0, columnspan=4, sticky=tk.W, padx=10)
    dark_only.append((theme_width_box, tk.NORMAL))
    if _color_schemes is not None:
        try:
            _color_schemes.build(frame, 16, dark_only)
        except Exception:
            logger.exception("Colour schemes section failed")
    _prefs["hide_export"] = tk.BooleanVar(value=_get_bool(CFG_HIDE_EXPORT, False))
    _prefs["hide_update"] = tk.BooleanVar(value=_get_bool(CFG_HIDE_UPDATE, False))
    _prefs["hide_fetch"] = tk.BooleanVar(value=_get_bool(CFG_HIDE_FETCH, False))
    pioneer_here = _panel_state("pioneer.globals", "pioneer_globals") is not None
    bioscan_here = _bioscan_state() is not None
    # Other developers' plugins: their options only appear while that plugin is installed.
    if pioneer_here:
        nb.Checkbutton(frame, text="Hide Export button (Pioneer)", variable=_prefs["hide_export"]).grid(
            row=26, column=0, columnspan=4, sticky=tk.W, padx=10)
    nb.Checkbutton(frame, text="Hide Update button (EDMC)", variable=_prefs["hide_update"]).grid(
        row=27, column=0, columnspan=4, sticky=tk.W, padx=10)
    if bioscan_here:
        nb.Checkbutton(frame, text="Hide Fetch EDSM Data button (BioScan)", variable=_prefs["hide_fetch"]).grid(
            row=28, column=0, columnspan=4, sticky=tk.W, padx=10)
    nb.Label(frame, text="Dark/transparent: drag the bottom-right triangle to resize.\n"
                        "Dragging keeps your chosen size and updates active locks.\n"
                        "Press OK to apply settings and return unlocked dimensions to automatic sizing.").grid(
        row=29, column=0, columnspan=3, sticky=tk.W, padx=10, pady=(8, 0))
    purpose_options = nb.Frame(frame)
    purpose_options.grid(row=35, column=0, columnspan=4, sticky=tk.W, padx=10, pady=(8, 10))
    nb.Label(purpose_options, text="Headers").grid(row=0, column=0, sticky=tk.W)
    justify = nb.Frame(purpose_options)
    justify.grid(row=4, column=0, sticky=tk.W, pady=(8, 0))
    _prefs["header_align"] = tk.StringVar(value=_get_str(CFG_HEADER_ALIGN, "center"))
    nb.Label(justify, text="Justify headers:").grid(row=0, column=0, sticky=tk.W)
    for column, (value, text) in enumerate((("center", "Center"), ("left", "Left"),
                                            ("mixed", "Left (Hidden) / Center (Open)")), start=1):
        nb.Radiobutton(justify, text=text, value=value, variable=_prefs["header_align"]).grid(
            row=0, column=column, sticky=tk.W, padx=(6, 0))
    nb.Label(purpose_options, text="Applies to every panel header, including collapsed (Hidden) ones.").grid(
        row=5, column=0, sticky=tk.W)
    _prefs["hide_hidden"] = tk.BooleanVar(value=_get_bool(CFG_HIDE_HIDDEN, False))
    nb.Checkbutton(purpose_options, text='Remove "(Hidden)" from collapsed headers',
                   variable=_prefs["hide_hidden"]).grid(row=6, column=0, sticky=tk.W, pady=(4, 0))

    if _custom_headers is not None:_custom_headers.prefs(purpose_options)
    nb.Label(frame, text="Plugin panel order (top to bottom)").grid(
        row=31, column=0, columnspan=4, sticky=tk.W, padx=10, pady=(12, 3))
    _prefs["hide_menu"] = tk.BooleanVar(value=_get_bool(CFG_HIDE_MENU, False))
    _prefs["hide_both"] = tk.BooleanVar(value=_get_bool(CFG_HIDE_BOTH, False))
    chrome = nb.Frame(frame)
    chrome.grid(row=30, column=0, columnspan=4, sticky=tk.W, padx=10, pady=(6, 0))
    def choose_chrome(which: str, other: str) -> None:
        if _prefs[which].get():
            _prefs[other].set(False)
    nb.Checkbutton(chrome, text="Hide File/Edit/Help menu (Alt shows/hides it)",
                   variable=_prefs["hide_menu"], command=lambda: choose_chrome("hide_menu", "hide_both")).grid(
        row=0, column=0, sticky=tk.W)
    nb.Checkbutton(chrome, text="Hide title bar and menu (Alt shows/hides both)",
                   variable=_prefs["hide_both"], command=lambda: choose_chrome("hide_both", "hide_menu")).grid(
        row=1, column=0, sticky=tk.W)
    _prefs["header_settings"] = tk.BooleanVar(value=_get_bool(CFG_HEADER_SETTINGS, True))
    nb.Checkbutton(chrome, text="When the menu is hidden, show a Settings button (\u2699) on the title bar",
                   variable=_prefs["header_settings"]).grid(row=2, column=0, sticky=tk.W)
    _prefs["stay_glass"] = tk.BooleanVar(value=_get_bool(CFG_STAY_GLASS, False))
    nb.Checkbutton(chrome, text="Transparent theme: stay see-through while the mouse is over EDMC "
                                "(the mouse cursor can vanish over the gaps)",
                   variable=_prefs["stay_glass"]).grid(row=3, column=0, sticky=tk.W)
    _prefs["header_glass"] = tk.BooleanVar(value=_get_bool(CFG_HEADER_GLASS, False))
    nb.Checkbutton(chrome, text="Transparent theme: make the title bar and Commander Profile header see-through too",
                   variable=_prefs["header_glass"]).grid(row=4, column=0, sticky=tk.W)
    nb.Label(chrome, text="WARNING: Windows passes the mouse straight through see-through pixels, so with this on you can only\n"
                          "drag the window by clicking exactly on the letters of the title or of 'Commander Profile'.").grid(
        row=5, column=0, sticky=tk.W, padx=(24, 0))
    _panel_order_prefs(frame)
    nb.Label(frame, text="Select a panel and move it up or down. Press OK to apply.\n"
                        "New panels appear at the bottom; Default Order restores EDMC's order.").grid(
        row=33, column=0, columnspan=4, sticky=tk.W, padx=10, pady=(4, 0))
    profiles=nb.Frame(frame)
    profiles.grid(row=36,column=0,columnspan=4,sticky=tk.W,padx=10,pady=(8,10))
    nb.Label(profiles,text="Manual Layout Profiles (save / apply now)").grid(row=0,column=0,columnspan=3,sticky=tk.W)
    for row,name in enumerate(("Bubble","Exploration","Mining"),start=1):
        nb.Label(profiles,text=name).grid(row=row,column=0,sticky=tk.W)
        ttk.Button(profiles,text="Save",command=lambda n=name:_save_profile(n)).grid(row=row,column=1,padx=4)
        ttk.Button(profiles,text="Apply",command=lambda n=name:_load_profile(n)).grid(row=row,column=2,padx=4)
    ttk.Button(profiles, text="Reset All Popup Windows to Defaults",
               command=lambda: _window_memory.reset() if _window_memory is not None else None).grid(
                   row=5,column=0,columnspan=3,sticky=tk.W,pady=(12,4))
    # Text style for the dark and transparent themes (EDMC gives transparent all capitals, dark normal text).
    text_style = nb.Frame(frame)
    text_style.grid(row=frame.grid_size()[1], column=0, columnspan=4, sticky=tk.W, padx=10, pady=(12, 0))
    _prefs["text_style"] = tk.StringVar(value=_get_str(CFG_TEXT_STYLE, "follow"))
    nb.Label(text_style, text="Text style (dark and transparent themes)").grid(row=0, column=0, sticky=tk.W)
    for index, (value, text) in enumerate(TEXT_STYLE_CHOICES, start=1):
        radio = nb.Radiobutton(text_style, text=text, value=value, variable=_prefs["text_style"])
        radio.grid(row=index, column=0, sticky=tk.W)
        dark_only.append((radio, tk.NORMAL))
    nb.Label(text_style, text="All capitals needs the most room; normal text suits a small screen.").grid(
        row=len(TEXT_STYLE_CHOICES) + 1, column=0, sticky=tk.W)
    # Map macros: off by default; plugins show a copy/auto button only while this is on.
    macros = nb.Frame(frame)
    macros.grid(row=frame.grid_size()[1], column=0, columnspan=4, sticky=tk.W, padx=10, pady=(12, 0))
    _prefs["map_macros"] = tk.BooleanVar(value=_get_bool("NavInterface_MapMacros", False))
    _prefs["map_link"] = tk.BooleanVar(value=_get_bool("NavInterface_MapLinkAll", False))
    nb.Label(macros, text="Galaxy map shortcuts (optional)").grid(row=0, column=0, sticky=tk.W)
    nb.Checkbutton(macros, text="Let plugins put a clicked name into the galaxy map (adds a copy/auto button "
                                "to each plugin header)", variable=_prefs["map_macros"]).grid(row=1, column=0, sticky=tk.W)
    nb.Checkbutton(macros, text="One copy/auto choice for every plugin (any button switches them all)",
                   variable=_prefs["map_link"]).grid(row=2, column=0, sticky=tk.W)
    nb.Label(macros, text="Map shortcuts only search the galaxy map for you. Train the map clicks once; "
                          "every plugin shares them.").grid(row=3, column=0, sticky=tk.W)
    ttk.Button(macros, text="Train Map Clicks…", command=_open_training).grid(row=4, column=0, sticky=tk.W, pady=(4, 0))
    # Suite settings order: accessibility (theme colours, forced contrast) and then the credit line, last.
    colours = nb.Frame(frame)
    colours.grid(row=frame.grid_size()[1], column=0, columnspan=4, sticky=tk.W, padx=10, pady=(12, 0))
    _prefs["force_theme"] = tk.BooleanVar(value=_get_bool(CFG_FORCE_THEME, False))
    nb.Checkbutton(colours, text="Use theme colours instead of red/green/blue for status buttons (colour-blind friendly)",
                   variable=_prefs["force_theme"]).grid(row=0, column=0, sticky=tk.W)
    nb.Label(colours, text="Covers the green A (auto) button, the Auto-Route compass, the route lamp and bar, and the blue "
                           "neutron count: on uses your Highlighted Text colour, off your Normal Text colour.").grid(
        row=1, column=0, sticky=tk.W)
    scroll = nb.Frame(frame)
    scroll.grid(row=frame.grid_size()[1], column=0, columnspan=4, sticky=tk.W, padx=10, pady=(12, 0))
    _prefs["master_scroll"] = tk.BooleanVar(value=_get_bool(CFG_MASTER_SCROLL, True))
    _prefs["scroll_side"] = tk.StringVar(value=_scroll_side())
    _prefs["scroll_hide"] = tk.BooleanVar(value=_scroll_bar() == "never")
    nb.Label(scroll, text="Small screens (Dark and Transparent themes)").grid(row=0, column=0, columnspan=2, sticky=tk.W)
    nb.Checkbutton(scroll, text="Scroll the window when the plugins are taller than the screen or than the window you set",
                   variable=_prefs["master_scroll"]).grid(row=1, column=0, columnspan=2, sticky=tk.W)
    nb.Label(scroll, text="Scroll bar side:").grid(row=2, column=0, sticky=tk.W)
    sides = nb.Frame(scroll)
    sides.grid(row=2, column=1, sticky=tk.W)
    nb.Radiobutton(sides, text="Left", variable=_prefs["scroll_side"], value="left").grid(row=0, column=0)
    nb.Radiobutton(sides, text="Right", variable=_prefs["scroll_side"], value="right").grid(row=0, column=1, padx=(8, 0))
    nb.Checkbutton(scroll, text="Never show the scroll bar (the wheel and swiping still scroll). Otherwise it appears only while scrolling.",
                   variable=_prefs["scroll_hide"]).grid(row=3, column=0, columnspan=2, sticky=tk.W)
    if _panel_backgrounds is not None:
        _panel_backgrounds.preferences(frame)
    nb.Label(frame, text=f"{TITLE} {VERSION} - part of the Navigator plugin suite by Commander Thalinor").grid(
        row=frame.grid_size()[1], column=0, columnspan=4, sticky=tk.W, padx=10, pady=(12, 10))
    _track_theme_choice(parent, frame, dark_only)
    if _settings_compat is not None:_settings_compat.attach(parent)
    return outer


def _track_theme_choice(parent: tk.Misc, page: tk.Misc, dark_only: list) -> None:
    """Grey out dark/transparent-only settings while Appearance has Default chosen.

    Follows the Settings dialog's own (unsaved) theme choice, so switching the
    theme in Appearance updates this page at once. Disabling keeps each value,
    ready for when Dark or Transparent is chosen again.
    """
    choice = getattr(parent.winfo_toplevel(), "theme", None)

    def sync(*_args: Any) -> None:
        try:
            dark = (choice.get() if isinstance(choice, tk.Variable) else _get_int("theme", 0)) != 0
        except (tk.TclError, ValueError):
            dark = _get_int("theme", 0) != 0
        for widget, enabled in dark_only:
            try:
                if not widget.winfo_exists():
                    continue
                if enabled is not None:
                    widget.configure(state=enabled if dark else tk.DISABLED)
                elif not dark:
                    widget.configure(state=tk.DISABLED)
            except tk.TclError:
                continue
        show = getattr(_color_schemes, "show", None)
        if dark and callable(show):
            try:
                show()             # re-decides whether Delete applies
            except tk.TclError:
                pass

    if isinstance(choice, tk.Variable):
        name = choice.trace_add("write", sync)
        # The trace lives on the dialog's variable; drop it with this page.
        page.bind("<Destroy>", lambda event: _untrace(choice, name) if event.widget is page else None, add="+")
    sync()


def _untrace(variable: tk.Variable, name: str) -> None:
    try:
        variable.trace_remove("write", name)
    except (tk.TclError, ValueError):
        pass


def prefs_changed(cmdr: str, is_beta: bool) -> None:
    global _manual_size, _chrome_mode_seen
    if _panel_backgrounds is not None:
        _panel_backgrounds.save_preferences()
    if _plugin_options:
        for key, variable in list(_plugin_options.items()):
            try:
                config.set(key, bool(variable.get()))
            except tk.TclError:
                pass                          # that settings page is already gone
        _plugin_options.clear()
        if _root is not None:
            _root.after_idle(_notify_theme)   # plugins re-read their header options
    if not _prefs:
        return
    _manual_size = None
    if _root is not None: _root.after_idle(_notify_theme)
    _chrome_mode_seen = None  # Applying preferences starts the selected mode hidden.
    _save_panel_order()
    if _custom_headers is not None:_custom_headers.save()
    if _settings_compat is not None:
        for window in list(_settings_compat.windows):_settings_compat.schedule(window)
    colour = _prefs["colour"].get().strip() or DEFAULT_COLOUR
    try:
        if _root is not None:
            _root.winfo_rgb(colour)                # reject colours Tk doesn't understand
    except tk.TclError:
        logger.warning("Ignoring invalid scrollbar colour %r", colour)
        colour = _get_str(CFG_COLOUR, DEFAULT_COLOUR)
    try:
        width = max(2, min(24, int(float(_prefs["width"].get()))))
    except ValueError:
        width = _get_int(CFG_WIDTH, DEFAULT_WIDTH)
    config.set(CFG_ENABLED, bool(_prefs["enabled"].get()))
    config.set(CFG_MODE, _prefs["mode"].get() if "mode" in _prefs else "hidden")
    config.set(CFG_COLOUR, colour)
    config.set(CFG_WIDTH, width)
    if "compact" in _prefs:
        config.set(CFG_COMPACT, bool(_prefs["compact"].get()))
    if "bioscan_fit" in _prefs:
        config.set(CFG_BIOSCAN_FIT, bool(_prefs["bioscan_fit"].get()))
    if "theme_width" in _prefs:
        config.set(CFG_THEME_WIDTH, bool(_prefs["theme_width"].get()))
    if "header_align" in _prefs:
        value = _prefs["header_align"].get()
        config.set(CFG_HIDE_HIDDEN, bool(_prefs["hide_hidden"].get()))
        config.set(CFG_HEADER_ALIGN, value if value in ("left", "mixed") else "center")
    for key, setting in (("hide_export", CFG_HIDE_EXPORT), ("hide_update", CFG_HIDE_UPDATE),
                         ("hide_fetch", CFG_HIDE_FETCH), ("hide_menu", CFG_HIDE_MENU),
                         ("hide_both", CFG_HIDE_BOTH),
                         ("map_macros", "NavInterface_MapMacros"), ("map_link", "NavInterface_MapLinkAll"),
                         ("force_theme", CFG_FORCE_THEME), ("master_scroll", CFG_MASTER_SCROLL),
                         ("header_settings", CFG_HEADER_SETTINGS), ("stay_glass", CFG_STAY_GLASS),
                         ("header_glass", CFG_HEADER_GLASS)):
        if key in _prefs:
            config.set(setting, bool(_prefs[key].get()))
    if "scroll_side" in _prefs:
        config.set(CFG_SCROLL_SIDE, "right" if _prefs["scroll_side"].get() == "right" else "left")
        config.set(CFG_SCROLL_BAR, "never" if _prefs["scroll_hide"].get() else "auto")
    if _map_macros is not None:
        _map_macros.sync()
    if "text_style" in _prefs:
        chosen = _prefs["text_style"].get()
        if chosen != _get_str(CFG_TEXT_STYLE, "follow"):
            config.set(CFG_TEXT_STYLE, chosen if chosen in ("normal", "caps") else "follow")
            _apply_edmc_theme()               # one EDMC theme pass, same as switching themes
    if "lock_w" in _prefs:
        lock_w = bool(_prefs["lock_w"].get())
        try:
            width = int(float(_prefs["width_px"].get().strip()))
        except ValueError:
            width = _root.winfo_width() if _root is not None else 0     # blank = current width
        lock_h = bool(_prefs["lock_h"].get())
        config.set(CFG_LOCK_W, lock_w)
        config.set(CFG_WIDTH_PX, max(150, width) if width > 0 else 0)
        config.set(CFG_LOCK_H, lock_h)
        if lock_h and _root is not None:
            config.set(CFG_HEIGHT_PX, _root.winfo_height())
        if not lock_w and _root is not None and _root.overrideredirect():
            _root.geometry("")          # hand sizing back to EDMC
        active, layout_width = _layout_width() if _root is not None else (False, 0)
        _wrap_text(layout_width if active and layout_width > 0 else None)
    _schedule_refresh()


def _apply_edmc_theme() -> None:
    """Ask EDMC to rebuild and apply its theme once (so a changed text style takes effect at once)."""
    if _root is None:
        return

    def run() -> None:
        try:
            from theme import theme
            theme.apply(_root)
        except Exception:
            logger.exception("Could not re-apply EDMC's theme for the new text style")
    _root.after_idle(run)


def _notify_theme():
    if _root is not None:
        _root.event_generate("<<NavigatorThemeChanged>>",when="tail")


def navigator_attach_window(window):
    """Shared popup service for suite/third-party windows; False if not ready."""
    if _settings_compat is None or _window_memory is None:
        return False
    _settings_compat.attach(window)
    _window_memory.attach(window)
    return True


def _open_training() -> None:
    """Settings > Train Map Clicks: the shared training window (needs the settings page to be open)."""
    page = _prefs.get("settings_canvas")
    if page is not None:
        navigator_open_training(page)


def navigator_status_colours():
    """Colours for the suite's few status buttons (the green A, the Auto-Route compass, the route lamp
    and bar). By default on is green and off is red; with the accessibility setting on, on is the theme's
    Highlighted Text colour and off its Normal Text colour. Always a dict: on, off, plain, background,
    forced."""
    try:
        from theme import theme
        colours = getattr(theme, "current", None) or {}
    except Exception:
        colours = {}
    normal = colours.get("foreground") or "#000000"
    highlight = colours.get("highlight") or _get_str("dark_highlight", "#ff8000")
    background = colours.get("background") or "#ffffff"
    forced = _get_bool(CFG_FORCE_THEME, False)
    return {"on": highlight if forced else "#33cc33", "off": normal if forced else "#d93636",
            "plain": normal, "highlight": highlight, "background": background, "forced": forced,
            "info": highlight if forced else "#4da6ff"}      # a third colour (blue) for informational counts


FUEL_NEAR_LS, FUEL_FAR_LS = 500, 2000        # scoopable star: green up to this far from arrival, yellow up to the other


def navigator_fuel_colour(distance, dark=True):
    """Colour for a scoopable star `distance` light seconds from the arrival star: green (near), yellow, red (far),
    in a shade that reads on a dark (or, dark=False, light) background. None when the distance is not known, or with
    the accessibility setting on (theme colours only)."""
    if distance is None or _get_bool(CFG_FORCE_THEME, False):
        return None
    near, middle, far = ("#4ddb4d", "#ffd24d", "#ff6b6b") if dark else ("#1b8a1b", "#a67c00", "#c62828")
    return near if distance <= FUEL_NEAR_LS else middle if distance <= FUEL_FAR_LS else far


def navigator_scan_colour(level, dark=True):
    """Colour for how much of a system is scanned: level 0 (not scanned yet) green, 1 (partly) yellow, 2 (fully)
    red - the same shades as the fuel distances. None with the accessibility setting on (theme colours only)."""
    if level not in (0, 1, 2) or _get_bool(CFG_FORCE_THEME, False):
        return None
    shades = ("#4ddb4d", "#ffd24d", "#ff6b6b") if dark else ("#1b8a1b", "#a67c00", "#c62828")
    return shades[level]


def navigator_tag_colour(tag, dark=True):
    """Colour for a route tag: (N) blue, (D) pale blue; None for any other tag or with the accessibility setting on."""
    if _get_bool(CFG_FORCE_THEME, False):
        return None
    return {"(N)": "#4da6ff" if dark else "#0057b8", "(D)": "#9fd0f5" if dark else "#3a7fb0"}.get(tag)

_plugin_options: dict = {}     # options shown on another plugin's own settings page: config key -> BooleanVar


def navigator_header_options(page, folder):
    """Add the header options to a plugin's own settings page (settings that affect one plugin live on that
    plugin's page; the code and the saving stay here). Saved when Settings > OK is pressed."""
    variable = tk.BooleanVar(master=page, value=_get_bool(CFG_HEADER_COG, True))
    _plugin_options[CFG_HEADER_COG] = variable
    nb.Checkbutton(page, text="Show a settings cog box next to the header (the header itself is always "
                              "clickable)", variable=variable).grid(
        row=page.grid_size()[1], column=0, sticky=tk.W, padx=10, pady=(0, 8))


def navigator_header_cog_enabled():
    """True when plugins should show a cog box beside their clickable header (default on)."""
    return _get_bool(CFG_HEADER_COG, True)


def navigator_flat_colour():
    """The outline colour of a flat suite button (the theme's Normal Text colour), or None on the Default theme."""
    return _flat_colour()


def navigator_match_button(button, like, texts=()):
    """Make a header button the same size and look as ``like`` (the plugin's collapse button): copies its
    font and padding, and widens the button to fit the widest of ``texts`` and the collapse text."""
    if _map_macros is not None:
        _map_macros.match(button, like, tuple(texts))


def navigator_style_menu(menu):
    """Give a popup menu (and its sub-menus) the EDMC dark/transparent theme colours, which tk menus
    otherwise ignore, leaving them white. Returns True if the colours were applied."""
    if _get_int("theme", 0) == 0:
        return False                      # Default theme: keep the normal menu look
    try:
        from theme import theme
        colours = getattr(theme, "current", None) or {}
    except Exception:
        return False
    normal, background = colours.get("foreground"), colours.get("background")
    if not normal or not background:
        return False
    highlight = colours.get("highlight") or normal

    def apply(target):
        try:
            target.configure(background=background, foreground=normal, activebackground=highlight,
                             activeforeground=background, disabledforeground=normal, borderwidth=1,
                             relief=tk.FLAT)
        except tk.TclError:
            return
        for child in target.winfo_children():
            if isinstance(child, tk.Menu):
                apply(child)

    apply(menu)
    return True


def navigator_sync_mode_buttons():
    """Re-check every plugin's copy/auto button (a plugin hides its own by setting
    ``button.navigator_hidden``, for example while it has nothing to show)."""
    if _map_macros is not None:
        _map_macros.sync()


def navigator_open_training(owner):
    """Open the shared map-click training window from any plugin; returns the window (None if not ready)."""
    if _map_macros is None:
        return None
    try:
        window = _map_macros.open_training(owner)
        navigator_attach_window(window)
        return window
    except Exception:
        logger.exception("Could not open the map training window")
        return None


def navigator_map_settings():
    """A copy of the shared map settings (map key, trained click positions) for plugins that still
    run their own map actions; None if Interface is not ready."""
    if _map_macros is None:
        return None
    try:
        return dict(_map_macros.get_engine().settings)
    except Exception:
        logger.exception("Could not read the shared map settings")
        return None


def navigator_goto(name, folder, select_only=True):
    """Shared click-a-name service: put ``name`` into the galaxy map when the macro setting is on and
    this plugin's button is in map mode, otherwise copy it. Returns "mapped", "copied" or
    "copied-untrained"; None if the service is not ready (the caller should copy the name itself)."""
    if _map_macros is None:
        return None
    return _map_macros.goto(name, folder, select_only)


def navigator_mode_button(parent, folder, like=None, beside=False, grid=None, extra=None):
    """The small copy/auto toggle for a plugin header (None if Interface is not ready). ``grid`` is a
    dict of grid options that places it; ``like`` is the plugin's collapse button (same size), and
    ``beside`` keeps it just left of that button (and of whatever ``extra()`` says is between). Shown only while
    macros are on."""
    if _map_macros is None:
        return None
    return _map_macros.make_button(parent, folder, like, beside, extra, **(grid or {}))


def navigator_background_preferences(page, folder):
    """Add a suite plugin's contrast setting; Interface owns save/application."""
    if _panel_backgrounds is not None:
        return _panel_backgrounds.preferences(page, folder)
    return None


def navigator_set_panel_contrast(folder, enabled):
    """Register a plugin that already persists its own individual preference."""
    if _panel_backgrounds is not None:
        value = bool(enabled)
        if _panel_backgrounds.local.get(folder) != value:
            _panel_backgrounds.local[folder] = value
            _schedule_refresh()
