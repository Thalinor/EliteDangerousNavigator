# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""(N) Explorer - exploration values and a surface map for EDMC.

Part of the Navigator plugin suite by Commander Thalinor. Read-only: it reads the journal and the game's Status.json (through
EDMC) and draws its own panel. It sends nothing to the game and needs no web service.
"""
from __future__ import annotations

import logging
import math
import os
import re
import tkinter as tk
from tkinter import font as tkfont
from typing import Any

import myNotebook as nb
from config import appname, config

try:
    from . import model as model_mod, surface as surface_mod, values
except ImportError:                      # loaded as a plain (non-package) plugin
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import model as model_mod
    import surface as surface_mod
    import values

TITLE = "(N) Explorer"
HEADER_TITLE = "Explorer"
VERSION = "0.1.3"
PREFIX = "NavExplorer_"
PLUGIN_NAME = os.path.basename(os.path.dirname(__file__))
logger = logging.getLogger(f"{appname}.{PLUGIN_NAME}")
TABS = ("values", "surface")
TAB_LABELS = {"values": "Values", "surface": "Surface"}
COLLAPSE_UP, COLLAPSE_DOWN = "🔼", "🔽"   # standard EDMC plugin collapse button
BUTTON = {"pady": 0, "borderwidth": 1, "highlightthickness": 0, "cursor": "hand2"}   # same small buttons as the other panels
BUTTON_WIDTH = 6
TAB_PAD_X = 8
VALUE_LINES = 13
MAP_HEIGHT = 150
ZOOMS = (100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000)      # metres from the centre to the edge of the map
DEFAULT_ZOOM = 3
DEFAULT_THRESHOLD_K = 800                # kCr: a body counts as valuable when its maximum is at least this much
MARK_LIST = 4
SAVE_MS, MAP_MS, CONFIRM_MS = 4000, 400, 3000
IN_MAIN_SHIP, LANDED = 1 << 24, 1 << 1        # Status.json flag bits
TAG_RE = re.compile(r"\{(good|bad):([^}]*)\}")

_ui: dict[str, Any] = {}
_root: tk.Misc | None = None
_stopped = True
_model = model_mod.SystemModel()
_store: surface_mod.SurfaceStore | None = None
_after: dict[str, Any] = {}
_theme_pending = None
_theme_bindings: list[tuple[str, str]] = []
_state: dict[str, Any] = {"style": None, "page_height": 0, "body": "", "lat": None, "lon": None, "heading": None,
                          "radius": 0.0, "confirm": False, "notice": ""}


# --------------------------------------------------------------------------- settings + files
def _get_bool(key: str, default: bool) -> bool:
    try:
        value = config.get_bool(PREFIX + key, default=default)
    except TypeError:
        value = config.get_bool(PREFIX + key)
    return default if value is None else bool(value)


def _get_int(key: str, default: int) -> int:
    try:
        value = config.get_int(PREFIX + key, default=default)
    except TypeError:
        value = config.get_int(PREFIX + key)
    return default if value is None else int(value)


def _get_str(key: str, default: str) -> str:
    try:
        value = config.get_str(PREFIX + key, default=default)
    except TypeError:
        value = config.get_str(PREFIX + key)
    return value or default


def _data_dir() -> str:
    try:
        base = os.fspath(getattr(config, "app_dir_path", None) or config.app_dir)
    except Exception:
        base = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "EDMarketConnector")
    return os.path.join(base, "Navigator_Explorer")


def _threshold() -> int:
    return max(0, _get_int("ThresholdK", DEFAULT_THRESHOLD_K)) * 1000


# --------------------------------------------------------------------------- colours
def _theme_colours() -> dict[str, str]:
    try:
        from theme import theme
        current = dict(theme.current or {})
    except (ImportError, AttributeError):
        current = {}
    dark = False
    try:
        dark = bool(config.get_int("theme"))
    except (AttributeError, TypeError):
        pass
    current.setdefault("foreground", config.get_str("dark_text", default="#ff8000") if dark else "black")
    current.setdefault("highlight", config.get_str("dark_highlight", default="white") if dark else "blue")
    current.setdefault("background", "grey4" if dark else "white")
    current.setdefault("disabledforeground", "grey40")
    return current


def _scan_colour(level: int) -> str | None:
    """Green (0) or red (2) from (N) Interface, the same colours Cartography uses; None when it is absent or the
    accessibility setting turns colouring off."""
    try:
        from plug import invoke
        return invoke("(N) Interface", None, "navigator_scan_colour", level, bool(config.get_int("theme")))
    except Exception:
        return None


def _mix(first: str, second: str, share: float) -> str:
    try:
        a, b = _root.winfo_rgb(first), _root.winfo_rgb(second)
        return "#%02x%02x%02x" % tuple(int((x * share + y * (1 - share)) / 256) for x, y in zip(a, b))
    except (tk.TclError, AttributeError):
        return first


# --------------------------------------------------------------------------- tabs and layout
def _current_tab() -> str:
    tab = _get_str("TabId", TABS[0])
    return tab if tab in TABS else TABS[0]


def _select_tab(name: str) -> None:
    config.set(PREFIX + "TabId", name)
    _layout()
    _render()


def _toggle_collapsed() -> None:
    config.set(PREFIX + "Collapsed", not _get_bool("Collapsed", False))
    _layout()
    _render()


def _layout() -> None:
    if not _ui:
        return
    collapsed = _get_bool("Collapsed", False)
    tab = _current_tab()
    _ui["collapse"]["text"] = COLLAPSE_DOWN if collapsed else COLLAPSE_UP
    _ui["header"].configure(text=HEADER_TITLE + " (Hidden)" if collapsed else HEADER_TITLE)
    for name, page in _ui["pages"].items():
        page.grid() if (name == tab and not collapsed) else page.grid_remove()
    _ui["tabs"].grid_remove() if collapsed else _ui["tabs"].grid()
    _schedule_theme()


def _fit_heights() -> None:
    """Both tabs have the same height, so EDMC's window does not jump when you switch tabs."""
    try:
        wanted = max(inner.winfo_reqheight() for inner in _ui["inners"].values())
        if wanted > _state["page_height"]:
            _state["page_height"] = wanted
        for page in _ui["pages"].values():
            if int(float(page.cget("height"))) != _state["page_height"]:
                page.configure(height=_state["page_height"])
    except (tk.TclError, KeyError, ValueError):
        pass


def _draw_underlines(highlight: str) -> None:
    tab = _current_tab()
    for name, (label, line) in _ui.get("tab_widgets", {}).items():
        try:
            label.configure(foreground=highlight)                   # tabs are clickable: Highlighted Text
            line.configure(background=label.cget("background"))
            line.delete("all")
            if name == tab:
                line.create_rectangle(0, 0, label.winfo_reqwidth(), 2, fill=highlight, outline=highlight)
        except tk.TclError:
            pass


def _schedule_theme(_event: Any = None) -> None:
    """Coalesce theme/layout events into one pass; no polling."""
    global _theme_pending
    if not _stopped and _root is not None and _theme_pending is None:
        _theme_pending = _root.after_idle(_sync_theme)


def _sync_theme() -> None:
    global _theme_pending
    _theme_pending = None
    if _stopped or not _ui:
        return
    try:
        colours = _theme_colours()
        normal, highlight, background = colours["foreground"], colours["highlight"], colours["background"]
        border = colours["disabledforeground"]
        _fit_heights()
        signature = (normal, highlight, background, border, _current_tab(), str(_ui["header"].cget("font")))
        if signature == _state["style"]:
            return
        _state["style"] = signature
        reference = _ui["header"]
        text = _ui["text"]
        text.configure(background=background, foreground=normal, relief=tk.FLAT, highlightthickness=0, borderwidth=0,
                       font=reference.cget("font"), insertbackground=normal, selectbackground=border)   # no box, like Pioneer
        dim = _mix(normal, background, 0.62)
        good, bad = _scan_colour(0) or highlight, _scan_colour(2) or normal
        bold = tkfont.Font(font=reference.cget("font"))
        bold.configure(weight="bold")
        _ui["bold"] = bold
        text.tag_configure("head", foreground=normal, font=bold)          # Normal Text: Highlighted Text is only for what you can click
        text.tag_configure("text", foreground=normal)
        text.tag_configure("dim", foreground=dim)
        text.tag_configure("rule", foreground=border)
        text.tag_configure("good", foreground=good)
        text.tag_configure("bad", foreground=bad)
        canvas = _ui["canvas"]
        canvas.configure(background=background, highlightthickness=0, borderwidth=0)           # no box round the map either
        _ui["map_colours"] = {"background": background, "normal": normal, "highlight": normal, "border": border,
                              "dim": dim, "good": good, "bad": bad}
        for name in ("status", "marks", "zoom"):
            _ui[name].configure(background=background, foreground=normal)
        _draw_underlines(highlight)
        _render()
    except tk.TclError:
        pass


# --------------------------------------------------------------------------- Values tab
def _render_values() -> None:
    text = _ui["text"]
    lines = _model.lines(_threshold(), _get_bool("Details", True), _get_bool("Descriptors", False))
    width = max(20, int(text.winfo_width() / max(1, tkfont.Font(font=text.cget("font")).measure("─"))) - 2) \
        if text.winfo_width() > 1 else 40
    text.configure(state=tk.NORMAL)
    top = text.yview()[0]
    text.delete("1.0", tk.END)
    for style, line in lines:
        if style == "rule":
            text.insert(tk.END, "─" * width + "\n", "rule")
            continue
        position = 0
        for match in TAG_RE.finditer(line):
            text.insert(tk.END, line[position:match.start()], style)
            text.insert(tk.END, match.group(2), match.group(1))
            position = match.end()
        text.insert(tk.END, line[position:] + "\n", style)
    text.yview_moveto(top)
    text.configure(state=tk.DISABLED)


# --------------------------------------------------------------------------- Surface tab
def _body_key() -> str | None:
    return surface_mod.SurfaceStore.key(_model.system, _state["body"]) if _state["body"] else None


def _here() -> tuple[float, float] | None:
    return (_state["lat"], _state["lon"]) if _state["lat"] is not None and _state["lon"] is not None else None


def _centre(key: str | None) -> tuple[float, float] | None:
    """The map is centred on you; off the surface it stays on the last place you were."""
    if _here() is not None:
        return _here()
    if key and _store is not None:
        track = _store.body(key)["track"]
        if track:
            return track[-1][0], track[-1][1]
    return None


def _draw_map() -> None:
    _after["map"] = None
    canvas, colours = _ui.get("canvas"), _ui.get("map_colours")
    if _stopped or canvas is None or colours is None or _store is None:
        return
    canvas.delete("all")
    key = _body_key()
    width, height = max(canvas.winfo_width(), 60), max(canvas.winfo_height(), 60)
    zoom = ZOOMS[min(max(_get_int("Zoom", DEFAULT_ZOOM), 0), len(ZOOMS) - 1)]
    _ui["zoom"]["text"] = f"{surface_mod.distance_text(zoom)}"
    centre = _centre(key)
    record = _store.body(key) if key else None
    if centre is None or not record or not record["radius"]:
        canvas.create_text(width / 2, height / 2, fill=colours["dim"], justify=tk.CENTER, width=width - 20,
                           text="Drive or walk on a planet and your track appears here.")
        _update_marks(None, None)
        return
    radius, scale = record["radius"], (min(width, height) / 2 - 6) / zoom
    cx, cy = width / 2, height / 2
    canvas.create_line(0, cy, width, cy, fill=colours["border"], dash=(2, 6))                # faint crosshair instead of a frame
    canvas.create_line(cx, 0, cx, height, fill=colours["border"], dash=(2, 6))
    half = (min(width, height) / 2 - 6)
    canvas.create_oval(cx - half, cy - half, cx + half, cy + half, outline=colours["border"])  # the edge of the zoom range

    def point(lat: float, lon: float) -> tuple[float, float]:
        east, north = surface_mod.offset_m(centre[0], centre[1], lat, lon, radius)
        return width / 2 + east * scale, height / 2 - north * scale

    for sample in _store.rings(key):
        x, y = point(sample["lat"], sample["lon"])
        ring = surface_mod.colony_distance(sample["genus"]) * scale
        canvas.create_oval(x - ring, y - ring, x + ring, y + ring, outline=colours["bad"], dash=(4, 3))
        canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill=colours["bad"], outline=colours["bad"])
    for sample in record["samples"]:
        if sample["done"]:
            x, y = point(sample["lat"], sample["lon"])
            canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill=colours["good"], outline=colours["good"])
    for mode, run in surface_mod.segments(record["track"], _get_bool("ShowShip", False)):
        coords = [c for lat, lon in run for c in point(lat, lon)]
        if len(coords) < 4:
            continue
        if mode == surface_mod.GROUND:
            canvas.create_line(*coords, fill=colours["normal"], width=2, joinstyle=tk.ROUND)
        else:                              # the ship's flight path: dotted and dimmer, so it never reads as your own track
            canvas.create_line(*coords, fill=colours["dim"], width=1, dash=(2, 4))
    for number, mark in enumerate(record["marks"], 1):
        x, y = point(mark["lat"], mark["lon"])
        canvas.create_polygon(x, y - 6, x + 5, y, x, y + 6, x - 5, y, fill=colours["highlight"], outline=colours["highlight"])
        canvas.create_text(x + 8, y - 8, text=str(number), fill=colours["highlight"], anchor=tk.W)
    heading = math.radians(_state["heading"] or 0.0)
    tip = (cx + 9 * math.sin(heading), cy - 9 * math.cos(heading))
    left = (cx + 6 * math.sin(heading + 2.5), cy - 6 * math.cos(heading + 2.5))
    right = (cx + 6 * math.sin(heading - 2.5), cy - 6 * math.cos(heading - 2.5))
    canvas.create_polygon(*tip, *left, cx, cy, *right, fill=colours["highlight"] if _here() else colours["dim"],
                          outline=colours["highlight"] if _here() else colours["dim"])
    canvas.create_text(width - 8, 8, text="N", fill=colours["dim"], anchor=tk.NE)
    here = _here()
    _update_marks(key, here)


def _update_marks(key: str | None, here: tuple[float, float] | None) -> None:
    if key is None or _store is None:
        _ui["marks"]["text"] = ""
        _ui["status"]["text"] = _state["notice"] or "No surface position yet"
        return
    record = _store.body(key)
    lines = []
    if here is not None and record["radius"]:
        ranked = []
        for number, mark in enumerate(record["marks"], 1):
            distance, bearing = surface_mod.distance_bearing(here[0], here[1], mark["lat"], mark["lon"], record["radius"])
            ranked.append((distance, f"{mark['name']}   {surface_mod.distance_text(distance)}   {bearing:03.0f}°"))
        lines = [text for _d, text in sorted(ranked)[:MARK_LIST]]
    _ui["marks"]["text"] = "\n".join(lines)
    status = _state["notice"]
    if not status and here is not None:
        margin = _store.margin(key, here[0], here[1])
        if margin is None:
            status = ""
        elif margin[1] < 0:
            status = f"Too close: {margin[0]} ring, {abs(margin[1]):.0f} m to clear"
        else:
            status = f"Clear: {margin[0]} ring {margin[1]:.0f} m away"
    elif not status:
        status = "Not on the surface"
    _ui["status"]["text"] = status


def _schedule_map() -> None:
    if not _stopped and _root is not None and _after.get("map") is None:
        _after["map"] = _root.after(MAP_MS, _draw_map)


def _notice(text: str) -> None:
    _state["notice"] = text
    if _root is not None:
        if _after.get("notice") is not None:
            try:
                _root.after_cancel(_after["notice"])
            except tk.TclError:
                pass
        _after["notice"] = _root.after(2500, _clear_notice)
    _schedule_map()


def _clear_notice() -> None:
    _after["notice"] = None
    _state["notice"] = ""
    _schedule_map()


def _zoom(step: int) -> None:
    config.set(PREFIX + "Zoom", min(max(_get_int("Zoom", DEFAULT_ZOOM) + step, 0), len(ZOOMS) - 1))
    _schedule_map()


def _toggle_ship() -> None:
    shown = not _get_bool("ShowShip", False)
    config.set(PREFIX + "ShowShip", shown)
    _notice("Ship path shown (dotted)" if shown else "Ship path hidden")


def _add_mark() -> None:
    key, here = _body_key(), _here()
    if key is None or here is None or _store is None:
        _notice("No position to mark")
        return
    _notice(f"{_store.add_mark(key, *here)} added")


def _undo_mark() -> None:
    key = _body_key()
    if key is not None and _store is not None:
        _store.remove_last_mark(key)
        _notice("Last mark removed")


def _clear_body() -> None:
    key = _body_key()
    if key is None or _store is None:
        return
    if not _state["confirm"]:
        _state["confirm"] = True
        _ui["clear"]["text"] = "Sure?"
        _after["confirm"] = _root.after(CONFIRM_MS, _unconfirm)
        return
    _unconfirm()
    _store.clear(key)
    _notice("Map cleared")


def _unconfirm() -> None:
    _state["confirm"] = False
    if _ui.get("clear") is not None:
        _ui["clear"]["text"] = "Clear"


def _render() -> None:
    if _stopped or not _ui:
        return
    if _current_tab() == "values" and not _get_bool("Collapsed", False):
        _render_values()
    _schedule_map()


# --------------------------------------------------------------------------- EDMC hooks
def _save_soon() -> None:
    if not _stopped and _root is not None and _after.get("save") is None:
        _after["save"] = _root.after(SAVE_MS, _save_now)


def _save_now() -> None:
    _after["save"] = None
    _model.save(os.path.join(_data_dir(), "system.json"))
    if _store is not None:
        _store.save()


def plugin_start3(plugin_dir: str) -> str:
    global _store
    _store = surface_mod.SurfaceStore(os.path.join(_data_dir(), "surface.json"))
    _model.load(os.path.join(_data_dir(), "system.json"))
    logger.info("%s %s loaded", TITLE, VERSION)
    return TITLE


def journal_entry(cmdr: str, is_beta: bool, system: str | None, station: str | None, entry: dict, state: dict) -> None:
    event = entry.get("event")
    if event in model_mod.NEW_SYSTEM_EVENTS:
        _state["body"] = entry.get("Body") or ""
        _state["lat"] = _state["lon"] = None
    elif event in ("ApproachBody", "Touchdown", "Liftoff", "LeaveBody"):
        _state["body"] = entry.get("Body") or entry.get("BodyName") or ("" if event == "LeaveBody" else _state["body"])
    elif event == "ScanOrganic" and _store is not None and _here() is not None and _body_key():
        genus = entry.get("Genus_Localised") or entry.get("Genus") or ""
        species = entry.get("Species_Localised") or entry.get("Species") or ""
        _store.add_sample(_body_key(), genus, species, entry.get("ScanType") or "Log", *_here())
        _schedule_map()
    changed = _model.feed(entry)
    if changed and not _stopped:
        _render()
        _save_soon()


def dashboard_entry(cmdr: str, is_beta: bool, entry: dict) -> None:
    """EDMC passes on the game's Status.json: latitude, longitude and heading appear while you are near a surface."""
    if _stopped or _store is None:
        return
    lat, lon = entry.get("Latitude"), entry.get("Longitude")
    if lat is None or lon is None:
        if _state["lat"] is not None:
            _state["lat"] = _state["lon"] = None
            _schedule_map()
        return
    body = entry.get("BodyName") or _state["body"]
    if body and body != _state["body"]:
        _state["body"] = body
    radius = entry.get("PlanetRadius") or _state["radius"]
    _state.update(lat=float(lat), lon=float(lon), heading=entry.get("Heading"), radius=float(radius or 0.0))
    key = _body_key()
    flags = int(entry.get("Flags") or 0)
    flying = bool(flags & IN_MAIN_SHIP) and not flags & LANDED          # landed, in the SRV or on foot all count as ground
    if key and radius:
        _store.add_position(key, float(radius), float(lat), float(lon), surface_mod.SHIP if flying else surface_mod.GROUND)
        _save_soon()
    _schedule_map()


def _button(parent: tk.Misc, text: str, command: Any, width: int = BUTTON_WIDTH) -> tk.Button:
    return tk.Button(parent, text=text, width=width, command=command, **BUTTON)


def plugin_app(parent: tk.Frame) -> tk.Frame:
    global _root, _stopped
    _root = parent.winfo_toplevel()
    _stopped = False
    _state.update(page_height=0, style=None, confirm=False, notice="")
    frame = tk.Frame(parent)
    frame.columnconfigure(0, weight=1)
    _ui.clear()
    _ui["frame"] = frame

    header = tk.Frame(frame)                       # the same header cell layout as every suite panel
    header.grid(row=0, column=0, sticky=tk.EW)
    header.columnconfigure((0, 2), uniform="header_controls")
    header.columnconfigure(1, weight=1)
    _ui["header"] = tk.Label(header, text=HEADER_TITLE)
    _ui["header"].grid(row=0, column=1)
    _ui["collapse"] = tk.Button(header, text=COLLAPSE_UP, command=_toggle_collapsed)
    _ui["collapse"].grid(row=0, column=2, sticky=tk.NE)

    tabs = tk.Frame(frame)
    tabs.grid(row=1, column=0, pady=(0, 8))
    _ui["tabs"] = tabs
    _ui["tab_widgets"] = {}
    for column, name in enumerate(TABS):
        cell = tk.Frame(tabs)
        cell.grid(row=0, column=column, padx=TAB_PAD_X)
        label = tk.Label(cell, text=TAB_LABELS[name], cursor="hand2")
        label.pack()
        line = tk.Canvas(cell, height=2, width=1, highlightthickness=0, bd=0)
        line.pack(fill=tk.X)
        label.bind("<Button-1>", lambda _event, tab=name: _select_tab(tab))
        _ui["tab_widgets"][name] = (label, line)

    pages = {name: tk.Frame(frame, width=1, height=1) for name in TABS}
    for page in pages.values():
        page.grid(row=2, column=0, sticky=tk.EW)
        page.grid_propagate(False)
        page.columnconfigure(0, weight=1)
    _ui["pages"] = pages
    _ui["inners"] = {}

    # ---- Values
    values_page = tk.Frame(pages["values"])
    values_page.place(x=0, y=0, relwidth=1, relheight=1)
    values_page.columnconfigure(0, weight=1)
    _ui["inners"]["values"] = values_page
    text = tk.Text(values_page, height=VALUE_LINES, width=1, wrap=tk.WORD, state=tk.DISABLED, takefocus=False, padx=4,
                   pady=3, cursor="arrow", exportselection=False)
    text.grid(row=0, column=0, sticky=tk.EW)
    text.bind("<Configure>", lambda _e: _after.get("rule") or _after.update(rule=_root.after(250, _rule_redraw)))
    _ui["text"] = text

    # ---- Surface
    surface_page = tk.Frame(pages["surface"])
    surface_page.place(x=0, y=0, relwidth=1, relheight=1)
    surface_page.columnconfigure(0, weight=1)
    _ui["inners"]["surface"] = surface_page
    canvas = tk.Canvas(surface_page, height=MAP_HEIGHT, width=1, bd=0)
    canvas.grid(row=0, column=0, sticky=tk.EW)
    canvas.bind("<Configure>", lambda _e: _schedule_map())
    _ui["canvas"] = canvas
    buttons = tk.Frame(surface_page)
    buttons.grid(row=1, column=0, pady=(4, 2))
    _button(buttons, "-", lambda: _zoom(1), 3).grid(row=0, column=0, padx=2)
    _ui["zoom"] = tk.Label(buttons, text="", width=8)
    _ui["zoom"].grid(row=0, column=1)
    _button(buttons, "+", lambda: _zoom(-1), 3).grid(row=0, column=2, padx=2)
    _button(buttons, "Mark", _add_mark).grid(row=0, column=3, padx=(8, 2))
    _button(buttons, "Undo", _undo_mark).grid(row=0, column=4, padx=2)
    _ui["clear"] = _button(buttons, "Clear", _clear_body)
    _ui["clear"].grid(row=0, column=5, padx=2)
    _button(buttons, "Ship", _toggle_ship, 5).grid(row=0, column=6, padx=2)
    _ui["status"] = tk.Label(surface_page, text="", anchor=tk.CENTER)
    _ui["status"].grid(row=2, column=0, sticky=tk.EW)
    _ui["marks"] = tk.Label(surface_page, text="", anchor=tk.W, justify=tk.LEFT)
    _ui["marks"].grid(row=3, column=0, sticky=tk.EW)

    try:
        from theme import theme
        theme.register(text)
    except ImportError:
        pass

    _layout()
    for sequence in ("<<ThemeChanged>>", "<<NavigatorGlass>>", "<Configure>", "<Map>"):
        _theme_bindings.append((sequence, _root.bind(sequence, _schedule_theme, add="+")))
    _schedule_theme()                     # EDMC applies its theme after plugin_app
    return frame


def _rule_redraw() -> None:
    _after["rule"] = None
    _render()


def plugin_stop() -> None:
    global _stopped, _theme_pending
    _stopped = True
    _save_now_direct()
    if _root is not None:
        for key in list(_after):
            if _after[key] is not None:
                try:
                    _root.after_cancel(_after[key])
                except tk.TclError:
                    pass
            _after[key] = None
        if _theme_pending is not None:
            try:
                _root.after_cancel(_theme_pending)
            except tk.TclError:
                pass
        for sequence, binding in _theme_bindings:
            try:
                _root.unbind(sequence, binding)
            except tk.TclError:
                pass
    _theme_pending = None
    _theme_bindings.clear()


def _save_now_direct() -> None:
    _model.save(os.path.join(_data_dir(), "system.json"))
    if _store is not None:
        _store.dirty = True
        _store.save()


# --------------------------------------------------------------------------- settings page
def plugin_prefs(parent: nb.Notebook, cmdr: str, is_beta: bool) -> tk.Frame:
    frame = nb.Frame(parent)
    frame.columnconfigure(1, weight=1)
    _ui["pref_threshold"] = tk.StringVar(value=str(_get_int("ThresholdK", DEFAULT_THRESHOLD_K)))
    _ui["pref_details"] = tk.BooleanVar(value=_get_bool("Details", True))
    _ui["pref_descriptors"] = tk.BooleanVar(value=_get_bool("Descriptors", False))
    _ui["pref_ship"] = tk.BooleanVar(value=_get_bool("ShowShip", False))
    nb.Label(frame, text=f"{TITLE} {VERSION}").grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 4), sticky=tk.W)
    nb.Label(frame, text="Valuable body minimum (kCr):").grid(row=1, column=0, padx=10, sticky=tk.W)
    nb.EntryMenu(frame, textvariable=_ui["pref_threshold"], width=8).grid(row=1, column=1, padx=10, sticky=tk.W)
    nb.Checkbutton(frame, text="Show the list of every body", variable=_ui["pref_details"]).grid(
        row=2, column=0, columnspan=2, padx=10, sticky=tk.W)
    nb.Checkbutton(frame, text="Describe stars (brightness and temperature)", variable=_ui["pref_descriptors"]).grid(
        row=3, column=0, columnspan=2, padx=10, sticky=tk.W)
    nb.Checkbutton(frame, text="Show the ship's flight path on the surface map (dotted)", variable=_ui["pref_ship"]).grid(
        row=4, column=0, columnspan=2, padx=10, sticky=tk.W)
    nb.Label(frame, text="Values are estimates from the community's published formula.").grid(
        row=5, column=0, columnspan=2, padx=10, pady=(10, 0), sticky=tk.W)
    return frame


def prefs_changed(cmdr: str, is_beta: bool) -> None:
    try:
        config.set(PREFIX + "ThresholdK", max(0, int(float(_ui["pref_threshold"].get()))))
    except (ValueError, KeyError, tk.TclError):
        pass
    try:
        config.set(PREFIX + "Details", bool(_ui["pref_details"].get()))
        config.set(PREFIX + "Descriptors", bool(_ui["pref_descriptors"].get()))
        config.set(PREFIX + "ShowShip", bool(_ui["pref_ship"].get()))
    except (KeyError, tk.TclError):
        pass
    _render()
