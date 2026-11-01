# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Systems Navigator foundation, based on Ship Computer's compact themed UI.

Part of the Navigator plugin suite by Commander Thalinor.
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import font as tkfont, ttk
from typing import Any

from config import appname, config
import myNotebook as nb
from theme import theme

try:
    from .system_state import SystemContext
    from .system_data import SystemBook, group_values, nearest_fuel_distance
    from .data_service import DataService
    from .atlas import Atlas, SEP, UNKNOWN, clean, field, distance, object_rows, powerplay_text
    from .landmarks import Landmarks, label as landmark_label
except ImportError:  # EDMC may load load.py outside a package.
    import importlib
    import sys
    import types
    from pathlib import Path
    _name = "_systems_navigator_runtime"
    if _name not in sys.modules:
        _package = types.ModuleType(_name)
        _package.__path__ = [str(Path(__file__).parent)]
        sys.modules[_name] = _package
    SystemContext = importlib.import_module(_name + ".system_state").SystemContext
    _data = importlib.import_module(_name + ".system_data")
    SystemBook, group_values, nearest_fuel_distance = _data.SystemBook, _data.group_values, _data.nearest_fuel_distance
    DataService = importlib.import_module(_name + ".data_service").DataService
    _atlas_module = importlib.import_module(_name + ".atlas")
    powerplay_text = _atlas_module.powerplay_text
    Atlas, SEP, UNKNOWN, clean, field, distance, object_rows = (_atlas_module.Atlas, _atlas_module.SEP, _atlas_module.UNKNOWN, _atlas_module.clean, _atlas_module.field, _atlas_module.distance, _atlas_module.object_rows)
    _landmarks_module = importlib.import_module(_name + ".landmarks")
    Landmarks, landmark_label = _landmarks_module.Landmarks, _landmarks_module.label

import os
from pathlib import Path
import queue

TITLE = "(N) Cartography"
HEADER_TITLE = "Cartography"
VERSION = "0.3.23"
PREFIX = "SystemsNavigator_"
COLLAPSE_UP, COLLAPSE_DOWN = "\U0001f53c", "\U0001f53d"
TABS = ("system", "exploration", "mining", "combat", "objects")
TAB_LABELS = {name: name.title() for name in TABS}
SUBTABS = {"exploration":("Overview","Bodies"), "mining":("Rings","Hotspots","Prospector","Traders"), "combat":("Conflicts","Zones","Signals","Wanted"), "objects":("Stations","Ports","Carriers","Other")}
TAB_PAD_X = 4
VISIBLE_LINES = 9
GROUP1_CAPTIONS = ("Current System:", "Star Types:", "Neutron:", "Fuel Star:", "Fuel Distance:", "Known:")
PLACEHOLDER_FIELDS = (("Field 1:", "—"), ("Field 2:", "—"), ("Field 3:", "—"))
logger = logging.getLogger(f"{appname}.Navigator_Cartography")
context = SystemContext()
_ui: dict[str, Any] = {}
_root: tk.Misc | None = None
_stopped = True
_theme_pending = None
_theme_bindings: list[tuple[str, str]] = []
_tab_font = None
_tab_font_key = None
_book = SystemBook()
_atlas = Atlas()
_traders = {}
_trader_attempts = set()
_required_pad = "Unknown"
_service = None
_pending = set()
_attempted = set()
_deferred_lookups = {}
_online = {}
_online_status = {}
_poll_id = None
_display_id = None
DISPLAY_BATCH_MS = 1500
_arrival_tabs = []
_ready_tabs = set(TABS)
_prefs = {}
# Engineers/traders/brokers: bundled engineers, learned stations, optional one-time download.
_landmarks = Landmarks()
_landmarks_loaded = False
_landmark_status = ""
_accents = {}   # (tab, caption) -> "engineer" | "service"
ACCENTS = {"engineer": ("#5ec8ff", "#0057b8"), "service": ("#7ddc8a", "#1b7a2e")}   # (dark bg, light bg)


def _get_bool(key: str, default: bool = False) -> bool:
    try:
        value = config.get_bool(PREFIX + key, default=default)
    except TypeError:
        value = config.get_bool(PREFIX + key)
    return default if value is None else bool(value)


def _current_tab() -> str:
    try:
        value = config.get_str(PREFIX + "TabId", default=TABS[0])
    except TypeError:
        value = config.get_str(PREFIX + "TabId")
    return value if value in TABS else TABS[0]


def _select_tab(name: str) -> None:
    if name in TABS:
        config.set(PREFIX + "TabId", name)
        _refresh_group1()
        _layout()


def _toggle_collapsed() -> None:
    config.set(PREFIX + "Collapsed", not _get_bool("Collapsed"))
    _layout()


def _layout() -> None:
    if not _ui:
        return
    collapsed = _get_bool("Collapsed")
    _ui["collapse"].configure(text=COLLAPSE_DOWN if collapsed else COLLAPSE_UP)
    _ui["header"].configure(text=HEADER_TITLE + " (Hidden)" if collapsed else HEADER_TITLE)
    for name, page in _ui["pages"].items():
        page.grid() if name == _current_tab() and not collapsed else page.grid_remove()
    _ui["tabs"].grid_remove() if collapsed else _ui["tabs"].grid()
    _schedule_theme()


def _scroll_view(view, event: Any) -> str:
    top, bottom = view.yview()
    if not (top <= 0 and bottom >= 1):
        up = getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0
        view.yview_scroll(-1 if up else 1, "units")
    return "break"


def _bind_scrolling(widget, view) -> None:
    for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        widget.bind(sequence, lambda event, v=view: _scroll_view(v, event))
    widget.bind("<ButtonPress-1>", lambda event: view.scan_mark(0, event.y_root-view.winfo_rooty()))
    widget.bind("<B1-Motion>", lambda event: view.scan_dragto(0, event.y_root-view.winfo_rooty(), gain=1))


def _size_scroll_area(view, inner, item) -> None:
    height = max(1, inner.winfo_reqheight())
    view.itemconfigure(item, height=height)
    view.configure(scrollregion=(0, 0, max(1, view.winfo_width()), height))


def _resize_fields(name,width):
    # Every row's text starts in the same column, the width of the widest caption: wrap to what is left of that
    # (a row with a short caption, like Allegiance:, must not wrap as if its own caption set the column).
    column=max([c.winfo_reqwidth() for c,v in _ui["fields"].get(name,[]) if c is not v and not getattr(c,"_compact",False)] or [0])
    for caption,value in _ui["fields"].get(name,[]):
        if getattr(caption,"_compact",False):
            font=tkfont.Font(font=caption.cget("font"))
            text=caption._full_text
            budget=max(40,int(width*.38))
            if font.measure(text)>budget:
                low,high=0,len(text)
                while low<high:
                    mid=(low+high+1)//2
                    if font.measure(text[:mid]+"…")<=budget: low=mid
                    else: high=mid-1
                text=text[:low]+"…"
            if caption.cget("text")!=text: caption.configure(text=text)
            if str(value.cget("wraplength"))!="0": value.configure(wraplength=0)
        else:
            wanted=max(1,width-max(caption.winfo_reqwidth(),column)-8)
            if str(value.cget("wraplength"))!=str(wanted): value.configure(wraplength=wanted)


def _scroll_area(parent, name):
    view = tk.Canvas(parent, width=1, height=1, highlightthickness=0, borderwidth=0)
    inner = tk.Frame(view)
    inner.columnconfigure(1, weight=1)
    item = view.create_window(0, 0, window=inner, anchor="nw")
    inner.bind("<Configure>", lambda _e: _size_scroll_area(view, inner, item))

    def resize(event):
        view.itemconfigure(item, width=event.width)
        _resize_fields(name,event.width)
        _size_scroll_area(view, inner, item)
    view.bind("<Configure>", resize)
    _bind_scrolling(view, view)
    _bind_scrolling(inner, view)
    _ui["scrolls"][name] = (view, inner, item)
    return view, inner


def _schedule_theme(event: Any = None) -> None:
    global _theme_pending
    if event is not None and getattr(event, "type", None) == tk.EventType.Configure:
        if event.widget not in (_root, _ui.get("frame")):
            return
    if not _stopped and _root is not None and _theme_pending is None:
        _theme_pending = _root.after_idle(_sync_theme)


def _sync_theme() -> None:
    """Match EDMC's normal text, fonts and transparency on actual UI events."""
    global _theme_pending, _tab_font, _tab_font_key
    _theme_pending = None
    if _stopped or not _ui:
        return
    reference = _ui["header"]
    background, foreground = reference.cget("background"), reference.cget("foreground")
    font_name = reference.cget("font")
    font = tkfont.Font(font=font_name)
    selected_font = tkfont.Font(font=font_name)
    selected_font.configure(underline=True)
    _ui["selected_font"] = selected_font   # keep the font alive while labels use it
    height = VISIBLE_LINES * font.metrics("linespace")
    for name, (view, inner, item) in _ui["scrolls"].items():
        page = _ui["pages"][name]
        if int(page.cget("height")) != height:
            page.configure(height=height)
        view.configure(background=background, yscrollincrement=max(1, height//4))
        inner.configure(background=background)
        frames=[inner]
        while frames:
            current=frames.pop()
            for child in current.winfo_children():
                if isinstance(child,tk.Frame):
                    child.configure(background=background)
                    frames.append(child)
        for caption, value in _ui["fields"][name]:
            for label in (caption, value):
                accent = getattr(label, "_accent", None)
                colour = (_accent_colour(accent, background) if accent else
                          ((_fuel_colour(label.cget("text"), background)
                            or (_visit_colour(label.cget("text"), background) if caption.cget("text") == "Visited:" else None))
                           if label is value else None) or
                          (_highlight() if getattr(label,"_copy_value",None) else foreground))
                label.configure(background=background, foreground=colour,
                                font=selected_font if getattr(label, "_selected", False) else font_name)
        _resize_fields(name,max(1,view.winfo_width()))
        _size_scroll_area(view, inner, item)
    # Keep the tab strip inside the available window width.
    width = max(1, _ui["frame"].winfo_width())
    if width <= 1:
        width = max(1, _ui["frame"].master.winfo_width())
    padding = sum(2*TAB_PAD_X + 2*label.winfo_pixels(label.cget("padx"))
                  + 2*label.winfo_pixels(label.cget("borderwidth"))
                  + 2*label.winfo_pixels(label.cget("highlightthickness"))
                  for label, _line in _ui["tab_widgets"].values())
    key = (tuple(sorted(font.actual().items())), width, padding)
    if key != _tab_font_key:
        _tab_font = tkfont.Font(font=font)
        pixels = abs(int(font.cget("size")))
        if int(font.cget("size")) > 0:
            pixels = round(pixels * float(_root.tk.call("tk", "scaling")))
        for size in range(max(1, pixels), 0, -1):
            _tab_font.configure(size=-size)
            if sum(_tab_font.measure(TAB_LABELS[name]) for name in TABS)+padding <= max(1, width-2):
                break
        _tab_font_key = key
    for name, (label, line) in _ui["tab_widgets"].items():
        label.configure(font=_tab_font, foreground=_highlight())   # tabs are clickable: Highlighted Text
        line.configure(background=label.cget("background"))
        line.delete("all")
        if name == _current_tab():
            colour = label.cget("foreground")
            line.create_rectangle(0, 0, label.winfo_reqwidth(), 2, fill=colour, outline=colour)


def plugin_start3(plugin_dir: str) -> str:
    global context, _landmarks, _landmarks_loaded
    context = SystemContext()
    _landmarks, _landmarks_loaded = Landmarks(plugin_dir), False
    logger.info("%s %s loaded", TITLE, VERSION)
    return TITLE


def plugin_app(parent: tk.Frame) -> tk.Frame:
    global _root, _stopped
    _root, _stopped = parent.winfo_toplevel(), False
    _ui.clear()
    frame = tk.Frame(parent)
    frame.columnconfigure(0, weight=1)
    _ui.update(frame=frame, pages={}, fields={}, scrolls={}, tab_widgets={})
    header = tk.Label(frame, text=HEADER_TITLE)
    header.grid(row=0, column=0)
    _ui["header"] = header
    collapse = tk.Button(frame, text=COLLAPSE_UP, command=_toggle_collapsed)
    collapse.grid(row=0, column=0, sticky=tk.NE)
    _ui["collapse"] = collapse
    tabs = tk.Frame(frame)
    tabs.grid(row=1, column=0, pady=(0, 8))
    _ui["tabs"] = tabs
    for column, name in enumerate(TABS):
        cell = tk.Frame(tabs)
        cell.grid(row=0, column=column, padx=TAB_PAD_X)
        label = tk.Label(cell, text=TAB_LABELS[name], cursor="hand2", takefocus=True)
        label.navigator_no_wrap = True
        label.pack()
        line = tk.Canvas(cell, height=2, width=1, highlightthickness=0, borderwidth=0)
        line.pack(fill=tk.X)
        for sequence in ("<Button-1>", "<Return>", "<space>"):
            label.bind(sequence, lambda _event, tab=name: _select_tab(tab))
        _ui["tab_widgets"][name] = (label, line)
        page = tk.Frame(frame, width=1, height=1)
        page.grid(row=2, column=0, sticky=tk.EW)
        page.pack_propagate(False)
        _ui["pages"][name] = page
        _ui["fields"][name] = []
        view, inner = _scroll_area(page, name)
        view.pack(fill=tk.BOTH, expand=True)
        theme.register(inner)  # EDMC's recursive traversal stops at canvas windows.
    _layout()
    for sequence in ("<<ThemeChanged>>", "<Configure>", "<Map>"):
        binding = _root.bind(sequence, _schedule_theme, add="+")
        _theme_bindings.append((sequence, binding))
    _schedule_theme()
    _start_data()
    _refresh_group1()
    _root.after(4000, _offer_landmarks)
    return frame


def journal_entry(cmdr: str, is_beta: bool, system: str | None, station: str | None,
                  entry: dict[str, Any], state: dict[str, Any]) -> None:
    global _required_pad
    _required_pad = state.get("LandingPadSize") or _required_pad
    ship=str(entry.get("Ship") or state.get("ShipType") or "").casefold()
    small={"sidewinder","eagle","empire_eagle","hauler","adder","viper","viper_mkiv","cobramkiii","cobramkiv","cobramkv","diamondback","diamondbackxl","empire_courier","kestrel","smallcombat01_nx"}
    medium={"asp","asp_scout","vulture","type6","type8","python","python_nx","krait_mkii","krait_light","ferdelance","mamba","federation_dropship","federation_dropship_mkii","federation_gunship","independant_trader","typex","typex_2","typex_3","mandalay"}
    large={"type7","anaconda","cutter","federation_corvette","belugaliner","orca","type9","type9_military","panthermkii"}
    if ship: _required_pad="S" if ship in small else "M" if ship in medium else "L" if ship in large else "Unknown"
    target = _book.navigation(cmdr, is_beta, entry, state)
    if target and target[0]:
        _request_lookup(*target)  # warm destination data during hyperspace countdown/transit
    previous_system = (context.commander, context.is_beta, context.name, context.address)
    context.update(cmdr, is_beta, system, station, entry)
    _atlas.feed(cmdr, is_beta, context.name, entry)
    address = entry.get("SystemAddress")
    if address is None or context.address is None or address == context.address:
        _book.feed(cmdr, is_beta, context.name, entry)
    _ensure_lookup()
    if entry.get("event") in {"Docked", "Location", "CarrierJump"}:
        _learn_current()
    if previous_system != (context.commander, context.is_beta, context.name, context.address):
        _cancel_display()
        _arrival_tabs[:] = TABS
        _ready_tabs.clear()
        _refresh_group1()  # never leave the previous system displayed on arrival
    _request_display()


def _data_dir() -> Path:
    base = getattr(config, "app_dir_path", None) or getattr(config, "app_dir", None)
    if not base:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "EDMarketConnector"
    return Path(base) / "Systems_Navigator"


def _journal_dir() -> str | None:
    try:
        value = config.get_str("journaldir", default="")
    except TypeError:
        value = config.get_str("journaldir")
    if value and Path(value).is_dir():
        return value
    fallback = Path.home()/"Saved Games"/"Frontier Developments"/"Elite Dangerous"
    return str(fallback) if fallback.is_dir() else None


def _start_data() -> None:
    global _service
    if _service is None:
        _service = DataService(_data_dir())
        _pending.add(("history",))
        _service.history(_journal_dir())
        _pending.add(("landmarks",))
        _service.landmarks_load()
    _ensure_lookup()
    _schedule_results()


def _ensure_lookup() -> None:
    if context.name:
        key=(context.name.casefold(),context.address)
        if key in _online:
            _atlas.online(context.commander,context.is_beta,context.name,_online[key].get("atlas",{}))
        _request_lookup(context.name, context.address)


def _request_lookup(name: str, address: int | None) -> None:
    if _stopped or _service is None or not _get_bool("UseEDSM", True):
        return
    key = (name.casefold(), address)
    if ("history",) in _pending:
        _deferred_lookups[key] = (name, address)
        return
    if key not in _attempted:
        _attempted.add(key)
        _pending.add(("edsm", *key))
        _online_status[key] = "loading"
        _service.lookup(name, address, refresh=True)
        _schedule_results()


def _schedule_results() -> None:
    global _poll_id
    if not _stopped and _root is not None and _pending and _poll_id is None:
        _poll_id = _root.after(100, _collect_results)


def _collect_results() -> None:
    """Only collect while jobs are outstanding; redraw fields only on changed data."""
    global _poll_id, _book, _atlas
    _poll_id = None
    if _stopped or _service is None:
        return
    changed = False
    while True:
        try:
            result = _service.results.get_nowait()
        except queue.Empty:
            break
        if result[0] == "history":
            history = result[1]
            history.merge(_book)  # journal callbacks received during replay are newer
            _book = history
            history_atlas = getattr(history,"atlas",Atlas())
            history_atlas.merge(_atlas)
            _atlas = history_atlas
            _pending.discard(("history",))
        elif result[0] in ("edsm_cached", "edsm"):
            _, name, address, item = result
            key = (name.casefold(), address)
            if result[0] == "edsm":
                _pending.discard(("edsm", *key))
            _online[key] = item.get("data", {})
            if name.casefold() == (context.name or "").casefold():
                _atlas.online(context.commander,context.is_beta,name,_online[key].get("atlas",{}))
                _learn_current()
            _online_status[key] = ("loading" if result[0] == "edsm_cached" else
                                   "unavailable" if item.get("error") else "ready")
        elif result[0] == "traders":
            _,name,item = result
            _traders[name.casefold()] = item
            _pending.discard(("traders",name.casefold()))
        elif result[0] == "landmarks_load":
            _landmarks_loaded_result(result[1])
        elif result[0] == "landmarks_download":
            _landmarks_downloaded(result[1])
        elif result[0] == "failed":
            if result[1].startswith("landmarks"):
                _pending.discard(("landmarks",))
            elif result[1] == "history":
                _pending.discard(("history",))
            elif result[1] == "traders":
                name = result[2][0]
                _pending.discard(("traders",name.casefold()))
                _traders[name.casefold()]={"data":{c:{"error":True} for c in ("Raw","Manufactured","Encoded")}}
            else:
                name, address = result[2]
                key = (name.casefold(), address)
                _pending.discard(("edsm", *key))
                _online_status[key] = "unavailable"
        changed = True
    if changed:
        _request_display()
    if ("history",) not in _pending:
        deferred = tuple(_deferred_lookups.values())
        _deferred_lookups.clear()
        _ensure_lookup()
        for name, address in deferred:
            _request_lookup(name, address)
    _schedule_results()


def _highlight():
    colours = getattr(theme,"current",{})
    return colours.get("highlight") or config.get_str("dark_highlight",default="#ff8000")


_fuel_ls = {}   # Fuel Star value text -> light seconds of its star from arrival (coloured green / yellow / red)


def _fuel_colour(text, background):
    """The colour for a Fuel Star line from (N) Interface (its accessibility setting turns colouring off), or None."""
    distance = _fuel_ls.get(text)
    if distance is None:
        return None
    try:
        from plug import invoke
        dark = _accent_colour("engineer", background) == ACCENTS["engineer"][0]
        return invoke("(N) Interface", None, "navigator_fuel_colour", distance, dark)
    except ImportError:
        return None


VISIT_LEVELS = {"First Discovery!": 0, "Honked": 0, "Known": 0, "Partially Scanned": 1, "Fully Scanned": 2}


def _visit_colour(text, background):
    """The Visited line's colour from (N) Interface: green while nothing is scanned yet, yellow partly scanned, red fully
    scanned (nothing left to do here). None for any other text, or with the accessibility setting on."""
    level = VISIT_LEVELS.get(text)
    if level is None:
        return None
    try:
        from plug import invoke
        dark = _accent_colour("engineer", background) == ACCENTS["engineer"][0]
        return invoke("(N) Interface", None, "navigator_scan_colour", level, dark)
    except ImportError:
        return None


class RightCopy(str):
    """A copy value whose clickable text is the value column (not the caption)."""


def _copy(text):
    # Cartography only copies: the galaxy map cannot select a body inside the system you are in, so there is
    # no map macro here (the copy/auto button belongs to plugins that deal in systems, like Navigation).
    if callable(text):
        text()
        return "break"
    if text and text != UNKNOWN and _root is not None:
        _root.clipboard_clear()
        _root.clipboard_append(text)
    return "break"


def _refresh_traders():
    key=(context.name or "").casefold()
    if not context.name or not _service or ("traders",key) in _pending or not _get_bool("UseEDSM",True): return
    _pending.add(("traders",key))
    _trader_attempts.add(key)
    _service.traders(context.name,refresh=True)
    _schedule_results()
    _refresh_group1()


def _learn_current():
    """Remember trader/broker stations in the current system; save only after the file has loaded."""
    if not context.name:
        return
    record = _atlas.record(context.commander, context.is_beta, context.name)
    coords = field(record["meta"], "coords", None)
    changed = False
    for row in record["objects"].values():
        changed = _landmarks.learn(context.name, row, coords) or changed
    if changed and _landmarks_loaded and _service is not None:
        _service.landmarks_save(_landmarks.snapshot())


def _landmarks_loaded_result(data):
    global _landmarks_loaded
    _pending.discard(("landmarks",))
    _landmarks.load(data)
    _landmarks_loaded = True
    _learn_current()   # anything seen before the file finished loading
    _update_landmark_prefs()


def _landmarks_downloaded(payload):
    global _landmark_status
    _pending.discard(("landmarks",))
    try:
        if isinstance(payload, dict) and payload.get("error"):
            raise ValueError(payload["error"])
        added = _landmarks.merge_download(payload)
    except ValueError as error:
        _landmark_status = "Download unavailable: " + str(error)[:80]
    else:
        _landmark_status = f"Downloaded: {added:,} new stations"
        config.set(PREFIX + "StationDataChoice", "download")
        if _service is not None:
            _service.landmarks_save(_landmarks.snapshot())
        for key in [k for k in _ui if k.startswith("rows_")]:
            _ui.pop(key)   # new codes for stations already on screen
    _update_landmark_prefs()


def _download_landmarks():
    """One-time download. Once the data is here it is never fetched again; play keeps it growing."""
    global _landmark_status
    if _landmarks.downloaded or ("landmarks",) in _pending or _service is None:
        return
    _landmark_status = "Downloading station data…"
    _pending.add(("landmarks",))
    _service.landmarks_download()
    _schedule_results()
    _update_landmark_prefs()


def _landmark_summary():
    if _landmark_status:
        return _landmark_status
    if not _landmarks_loaded:
        return "Loading station data…"
    if _landmarks.downloaded:
        return f"Station data downloaded ({_landmarks.downloaded}); {len(_landmarks):,} stations known"
    return f"Building as you go: {len(_landmarks):,} trader/broker stations learned"


def _update_landmark_prefs():
    status, button = _prefs.get("landmark_status"), _prefs.get("landmark_button")
    try:
        if status is not None:
            status.configure(text=_landmark_summary())
        if button is not None:
            busy = ("landmarks",) in _pending
            button.configure(state=tk.DISABLED if _landmarks.downloaded or busy else tk.NORMAL)
    except tk.TclError:
        pass   # settings window already closed
    _request_display()


def _offer_landmarks():
    """First run only: download the station data now, or build it as you go."""
    choice = config.get_str(PREFIX + "StationDataChoice", default="") or ""
    shown = _ui.get("offer")
    if (_stopped or _root is None or choice or _landmarks.downloaded
            or not _get_bool("UseEDSM", True) or ("landmarks",) in _pending
            or (shown is not None and shown.winfo_exists())):
        return
    window = tk.Toplevel(_root)
    _ui["offer"] = window
    window.title("Cartography station data")
    window.navigator_window_id = "cartography_station_data"
    window.transient(_root)
    window.resizable(False, False)
    tk.Label(window, justify=tk.LEFT, wraplength=420, padx=14, pady=12, text=(
        "Cartography can mark engineers (E), material traders (M) and technology brokers (T) "
        "in the Objects lists.\n\n"
        "Engineers are built in. For traders and brokers you can download the known stations "
        "once now from the Navigator GitHub page (about 300 KB, about 7,000 stations), "
        "or let Cartography learn them as you visit systems.\n\n"
        "Either way the list keeps growing from your own travels. You can download later from "
        "Cartography's settings.")).pack(fill=tk.X)
    buttons = tk.Frame(window, padx=14)
    buttons.pack(fill=tk.X, pady=(0, 12))

    def choose(value):
        config.set(PREFIX + "StationDataChoice", value)
        window.destroy()
        if value == "download":
            _download_landmarks()
    ttk.Button(buttons, text="Download (~300 KB)", command=lambda: choose("download")).pack(side=tk.RIGHT)
    ttk.Button(buttons, text="Build As I Go", command=lambda: choose("local")).pack(side=tk.RIGHT, padx=(0, 8))
    try:
        from plug import invoke
        invoke("(N) Interface", "Navigator Interface", "navigator_attach_window", window)
    except ImportError:
        pass


def _accent_colour(kind, background):
    try:
        red, green, blue = _root.winfo_rgb(background)
        dark = (0.299*red + 0.587*green + 0.114*blue) / 65535 < 0.5
    except (tk.TclError, AttributeError):
        dark = True
    return ACCENTS[kind][0 if dark else 1]


def _subgroup(tab):
    choices = SUBTABS.get(tab,())
    value = config.get_str(PREFIX+"Sub_"+tab,default=choices[0] if choices else "")
    return value if value in choices else (choices[0] if choices else "")


def _select_sub(tab,name):
    config.set(PREFIX+"Sub_"+tab,name)
    _refresh_group1()


def _uninhabited_rows(meta, name):
    """Compact presentation only: never infer absence from population alone."""
    rows = [("Current System:", name + SEP + "Uninhabited system", context.name)]
    def meaningful(value):
        return clean(value).strip().casefold() not in {"unknown", "none", "", "n/a"}
    for key, caption in (("allegiance", "Allegiance:"), ("faction", "Controlling Faction:"),
                         ("economy", "Economy:"), ("state", "State:")):
        value = field(meta, key)
        if meaningful(value):
            rows.append((caption, clean(value), None))
    power = powerplay_text(meta, _get_bool("TopTwoAcquisition", True))
    if power not in {UNKNOWN, "None"}:
        rows.append(("Powerplay:", power, None))
    security = field(meta, "security")
    if meaningful(security) and clean(security).casefold() not in {
            "anarchy", "galaxy map info state anarchy"}:
        rows.append(("Security:", clean(security), None))
    # Status.json is independent of population; never assume Clean or zero bounty.
    if meaningful(_atlas.legal):
        rows.append(("Legal:", _atlas.legal, None))
    rep = field(meta, "reputation")
    if meaningful(rep):
        rows.append(("Your Reputation:", f"{rep:+.1f}%" if isinstance(rep, (int, float)) else str(rep), None))
    return rows


def _rows(tab):
    name=context.name or UNKNOWN
    cmdr,beta=context.commander,context.is_beta
    record=_atlas.record(cmdr,beta,context.name)
    meta=record["meta"]
    rows=[("Current System:",name,name if context.name else None)] if tab == "system" else []
    group=_subgroup(tab)
    if tab == "system":
        population = field(meta, "population", None)
        if (not isinstance(population, bool) and isinstance(population, (int, float))
                and population == 0 and _get_bool("SimplifyUninhabited", True)):
            return _uninhabited_rows(meta, name)
        power=powerplay_text(meta, _get_bool("TopTwoAcquisition", True))
        pop=field(meta,"population")
        if isinstance(pop,(int,float)): pop=f"{pop:,}"
        rep=field(meta,"reputation")
        if isinstance(rep,(int,float)): rep=f"{rep:+.1f}%"
        rows += [("Allegiance:",clean(field(meta,"allegiance"))+SEP+"Powerplay: "+power,None),
                 ("Controlling Faction:",clean(field(meta,"faction")),None),
                 ("Economy:",clean(field(meta,"economy"))+SEP+"Population: "+str(pop)+SEP+"State: "+clean(field(meta,"state")),None),
                 ("Security:",clean(field(meta,"security"))+SEP+"Legal: "+_atlas.legal+SEP+"Bounty: "+UNKNOWN,None),
                 ("Your Reputation:",str(rep),None)]
    elif tab == "exploration" and group == "Overview":
        key=((context.name or "").casefold(),context.address)
        values=group_values(context.name,_book.record(cmdr,beta,context.name),_online.get(key),_online_status.get(key,""),("history",) in _pending)
        bodies=record["bodies"]
        mapped=sum(bool(field(b,"mapped",False)) for b in bodies.values())
        expected=_atlas.visit_expected if _atlas.visit_expected is not None else UNKNOWN
        targets=getattr(values,"fuel_targets",None) or []
        # Clickable values (RightCopy) copy a star name: each fuel star line copies that star's name.
        # With no fuel star there is nothing to copy, so the line is plain text.
        _fuel_ls.clear()
        _fuel_ls.update({(values[3]+SEP+"Fuel Distance: "+targets[0][0] if number == 0 else text): ls
                         for number, ((text, _), ls) in enumerate(zip(targets, getattr(values,"fuel_distances",None) or []))})
        rows += [("Star Types:",values[1]+SEP+"Neutron: "+values[2],None),
                 # One line: fuel yes/no plus the nearest fuel star; the whole text copies that star's name
                 ("Fuel Star:",values[3]+SEP+"Fuel Distance: "+(targets[0][0] if targets else values[4]),
                  RightCopy(targets[0][1]) if targets else None)]
        rows += [("",text,RightCopy(name)) for text,name in targets[1:]]   # more fuel stars, one line each, under the first
        rows += [("Visited:",values[5],None),
                 ("Scanned This Visit:",str(len(_atlas.visit_scans))+" / "+str(expected),None),
                 ("Mapped By You:",str(mapped) if bodies else UNKNOWN,None)]
    elif tab == "exploration":
        for body in sorted(record["bodies"].values(),key=lambda b:float(field(b,"distance",float("inf")))):
            bname=field(body,"name")
            land=field(body,"landable",None)
            details=SEP.join([clean(field(body,"type",field(body,"star"))),distance(field(body,"distance",None)),"Landable: "+("Yes" if land is True else "No" if land is False else UNKNOWN)])
            sites=[field(o,"name") for o in record["objects"].values() if clean(field(o,"body","")).casefold()==bname.casefold()]
            if sites: details+=SEP+"Sites: "+", ".join(sites)
            rows.append((bname,details,bname))
    elif tab == "objects":
        system=context.name or ""
        codes=_get_bool("ShowServiceCodes",True)
        for key in [k for k in _accents if k[0]==tab]: _accents.pop(key)
        for n,d,tags in object_rows(_atlas,cmdr,beta,system,group,_get_bool("CompatiblePads"),_required_pad,
                                    tagger=lambda row:_landmarks.tags(system,row)):
            caption=landmark_label(tags)+n if codes and tags else n
            if "E" in tags and _get_bool("HighlightEngineers",True):
                _accents[(tab,caption)]="engineer"
            elif any(t[0] in "MT" for t in tags) and _get_bool("HighlightServices",True):
                _accents[(tab,caption)]="service"
            rows.append((caption,d,n))
    elif tab == "mining":
        if group in {"Rings","Hotspots"}:
            for body in sorted(record["bodies"].values(),key=lambda b:float(field(b,"distance",float("inf")))):
                if group == "Rings":
                    for ring in field(body,"rings",[]) or []:
                        n=ring.get("Name") or ring.get("name") or UNKNOWN
                        d=SEP.join([clean(ring.get("RingClass") or ring.get("type")),"Reserves: "+clean(field(body,"reserves")),distance(field(body,"distance",None))])
                        rows.append((n,d,n))
                elif "ring" in str(field(body,"name","")).casefold():
                    for signal in field(body,"signals",[]):
                        n=field(body,"name")
                        rows.append((n,clean(signal.get("Type_Localised") or signal.get("Type"))+SEP+"Count: "+str(signal.get("Count",UNKNOWN)),n))
            if group == "Hotspots": rows.append(("Counts:","Reported Signals; Overlap Is Not Confirmed",None))
        elif group == "Prospector":
            p=_atlas.prospector or {}
            rows += [("Content:",clean(p.get("Content_Localised") or p.get("Content")),None),
                     ("Core:",clean(p.get("MotherlodeMaterial_Localised") or p.get("MotherlodeMaterial")),None),
                     ("Remaining:",str(p.get("Remaining",UNKNOWN))+"% (Last Report)",None)]
            rows += [(clean(m.get("Name_Localised") or m.get("Name")),str(m.get("Proportion",UNKNOWN))+"%",None) for m in p.get("Materials",[])]
        elif group == "Traders":
            key=(context.name or "").casefold()
            if context.name and key not in _trader_attempts and _service and _get_bool("UseEDSM",True):
                _trader_attempts.add(key)
                _pending.add(("traders",key))
                _service.traders(context.name)
                _schedule_results()
            item=_traders.get(key,{})
            for category in ("Raw","Manufactured","Encoded"):
                data=item.get("data",{}).get(category,{})
                result=data.get("results",[])
                if result:
                    trader=result[0]
                    station=trader.get("name",UNKNOWN)
                    system=trader.get("system_name",UNKNOWN)
                    pad="L" if trader.get("has_large_pad") else "M" if trader.get("medium_pads",0) else "S" if trader.get("small_pads",0) else UNKNOWN
                    marker=" [Turn-In]" if _atlas.turn_in(cmdr,beta,system,station) else ""
                    rows += [(category+":"+marker,station,station),
                             ("System:",system,system),
                             ("Nearest Known:",distance(trader.get("distance"),"Ly")+SEP+distance(trader.get("distance_to_arrival"))+SEP+"Pad: "+pad,None)]
                else:
                    rows.append((category+":","Unavailable" if data.get("error") else "Loading" if ("traders",key) in _pending else UNKNOWN,None))
            rows.append(("Lookup:","Refresh Traders",_refresh_traders))
            rows.append(("Access:","Check Permits And Docking Restrictions",None))
    elif tab == "combat":
        if group == "Conflicts":
            for conflict in field(meta,"conflicts",[]):
                a,b=conflict.get("Faction1",{}),conflict.get("Faction2",{})
                rows.append((clean(conflict.get("WarType")),clean(conflict.get("Status"))+SEP+clean(a)+" / "+clean(b)+SEP+str(a.get("WonDays",UNKNOWN))+" / "+str(b.get("WonDays",UNKNOWN)),None))
        elif group == "Wanted":
            for e in _atlas.encounters.values():
                n=clean(e.get("PilotName_Localised") or e.get("PilotName"))
                rows.append((n,SEP.join([clean(e.get("Ship_Localised") or e.get("Ship")),"Bounty: "+str(e.get("Bounty",UNKNOWN)),clean(e.get("Faction")),clean(e.get("PilotRank")),"Last Seen: "+str(e.get("timestamp",UNKNOWN))]),None))
            rows.append(("Contacts:","Observed This Visit; Location Not Tracked",None))
        else:
            for n,e in _atlas.signals.items():
                is_zone=any(w in n.casefold() for w in ("conflict","combat","resource extraction","nav beacon"))
                if (group=="Zones") != is_zone: continue
                expiry=__import__("time").time() - __import__("datetime").datetime.fromisoformat(e.get("timestamp","1970-01-01T00:00:00Z").replace("Z","+00:00")).timestamp()
                if e.get("TimeRemaining") is not None and expiry>e["TimeRemaining"]: continue
                rows.append((n,"Threat: "+str(e.get("ThreatLevel",UNKNOWN))+SEP+"Intensity: "+str(e.get("SignalType_Localised",UNKNOWN)),n))
    if not rows:
        rows.append(("", "No Known Entries",None))
    return rows


def _destroy_own_row(widget):
    # EDMC normally prunes destroyed registrations on its next theme apply.
    # These rows change with game data, so release only our own entries now.
    registry=getattr(theme,"widgets",None)
    pending=[widget]
    while pending:
        item=pending.pop()
        pending.extend(item.winfo_children())
        if isinstance(registry,dict): registry.pop(item,None)
        elif isinstance(registry,set): registry.discard(item)
    widget.destroy()


def _cancel_display():
    global _display_id
    if _display_id is not None and _root is not None:
        _root.after_cancel(_display_id)
    _display_id = None


def _request_display():
    """Wait for arrival requests, then present one complete tab at a time."""
    global _display_id
    if _stopped or _root is None:
        return
    if _arrival_tabs:
        key = ((context.name or '').casefold(), context.address)
        if ('history',) in _pending or ('edsm', *key) in _pending:
            return
        # Once presentation starts, finish its five tabs without restarting.
        if _ready_tabs:
            return
    # Later discoveries settle before changing the visible page, rather than
    # repeatedly rebuilding it throughout a scan burst.
    _cancel_display()
    if not _stopped:
        _display_id = _root.after(DISPLAY_BATCH_MS, _flush_display)


def _flush_display():
    global _display_id
    _display_id = None
    if not _stopped:
        if _arrival_tabs:
            key = ((context.name or '').casefold(), context.address)
            if ('history',) in _pending or ('edsm', *key) in _pending:
                return  # completion/error collection will schedule presentation
            tab = _arrival_tabs.pop(0)
            _ready_tabs.add(tab)
            _refresh_group1(tab)
            if _arrival_tabs:
                _display_id = _root.after(200, _flush_display)
            else:
                # Selected pages might have received newer observations while
                # the other pages were staged; settle those after the sequence.
                _request_display()
        else:
            _refresh_group1()


def _refresh_group1(only_tab=None):
    if not _ui:
        return
    for tab in (only_tab or _current_tab(),):
        rows=(_rows(tab) if tab in _ready_tabs else
              [("Current System:", context.name or UNKNOWN, None),
               ("Status:", "Loading…", None)])
        signature=(rows,_subgroup(tab))
        if _ui.get("rows_"+tab)==signature:
            continue
        previous = _ui.get("rows_"+tab)
        _ui["rows_"+tab]=signature
        view,inner,item=_ui["scrolls"][tab]
        # Values changing does not require destroying labels, bindings or focus.
        # Caption/copy-target changes still rebuild so click actions stay correct.
        structure = lambda values: [(caption, copy) for caption, value, copy in values]
        if previous and previous[1] == signature[1] and structure(previous[0]) == structure(rows):
            fields = _ui["fields"][tab][-len(rows):] if rows else []
            for (left, right), (_, value, _) in zip(fields, rows):
                if right.cget("text") != value:
                    right.configure(text=value)
            if _ui.get("header") is not None:
                _sync_theme()      # repaint: a Fuel Star line's colour follows its distance
            _resize_fields(tab, view.winfo_width())
            _size_scroll_area(view,inner,item)
            continue
        scroll = view.yview()[0]
        reference = _ui.get('header')
        initial_style = ({'background': reference.cget('background'),
                          'foreground': reference.cget('foreground'),
                          'font': reference.cget('font')} if reference is not None else {})
        for widget in inner.winfo_children(): _destroy_own_row(widget)
        _ui["fields"][tab]=[]
        row_index=0
        for index,(caption,value,copy) in enumerate(rows):
            if index==0 and tab in SUBTABS:
                bar=tk.Frame(inner, **({'background': initial_style['background']} if initial_style else {}))
                bar.grid(row=row_index,column=0,columnspan=2)
                for choice in SUBTABS[tab]:
                    label=tk.Label(bar,text=choice,padx=TAB_PAD_X,cursor="hand2",takefocus=True, **initial_style)
                    label.navigator_no_wrap=True
                    # Suite menu rule: every choice is Highlighted (clickable); the selected one is underlined.
                    label._copy_value=True
                    label._selected=choice==_subgroup(tab)
                    label.pack(side=tk.LEFT)
                    for sequence in ("<Button-1>","<Return>","<space>"):
                        label.bind(sequence,lambda e,t=tab,c=choice:_select_sub(t,c))
                    _ui["fields"][tab].append((label,label))
                row_index+=1
            left=tk.Label(inner,text=caption,anchor=tk.W,pady=0,borderwidth=0, **initial_style)
            left._accent=_accents.get((tab,caption))
            right=tk.Label(inner,text=value,anchor=tk.W,justify=tk.LEFT,pady=0,borderwidth=0, **initial_style)
            # This canvas owns column widths. Interface's whole-window wrapping
            # otherwise fights _resize_fields on every Configure event.
            left.navigator_no_wrap=right.navigator_no_wrap=True
            compact = (tab=="objects" or (tab=="exploration" and _subgroup(tab)=="Bodies")
                                  or (tab=="mining" and _subgroup(tab) in {"Rings","Hotspots"})
                                  or (tab=="combat" and _subgroup(tab) in {"Zones","Signals","Wanted"}))
            if compact:
                left._compact=True
                left._full_text=caption
                right.configure(width=1,wraplength=0)
            left.grid(row=row_index,column=0,sticky=tk.NW)
            right.grid(row=row_index,column=1,sticky=tk.EW,padx=(6,0))
            # System value is clickable; list entries use their name in the first column.
            target=right if ((tab=="system" and index==0) or (tab=="mining" and _subgroup(tab)=="Traders")
                             or isinstance(copy,RightCopy)) else left
            if copy and copy!=UNKNOWN:
                target._copy_value=copy
                target.configure(cursor="hand2",takefocus=True)
                for sequence in ("<Button-1>","<Return>","<space>"):
                    target.bind(sequence,lambda e,value=copy:_copy(value))
            _bind_scrolling(left,view)
            _bind_scrolling(right,view)
            # Mouse-wheel bindings must not replace the copy action with scan_mark.
            if copy and copy!=UNKNOWN:
                target.bind("<Button-1>",lambda e,value=copy:_copy(value))
            _ui["fields"][tab].append((left,right))
            row_index+=1
        theme.register(inner)
        _size_scroll_area(view,inner,item)
        view.yview_moveto(scroll)
    _schedule_theme()


def dashboard_entry(cmdr,is_beta,entry):
    legal=entry.get("LegalState")
    if legal and legal!=_atlas.legal:
        _atlas.legal=clean(legal)
        _request_display()


def navigator_fuel_distance(system: str):
    """For (N) Navigation's route tags: light seconds from the arrival star to the nearest scoopable star known in
    `system` (0 = you arrive at one), or None when not known. Only what the journal or EDSM has told us."""
    try:
        return nearest_fuel_distance(_book.record(context.commander, context.is_beta, system))
    except Exception:
        return None


def plugin_prefs(parent, cmdr: str | None, is_beta: bool):
    try:
        from plug import invoke
        outer = invoke("(N) Interface", "Navigator Interface", "navigator_scroll_settings", parent)
        frame = getattr(outer, "navigator_settings_content", None)
    except ImportError:
        outer = None
        frame = None
    if frame is None:
        outer = nb.Frame(parent)
        frame = outer
    nb.Label(frame, text=f"{TITLE} {VERSION}").grid(row=0, column=0, sticky=tk.W, padx=10, pady=(10, 6))
    _prefs["edsm"] = tk.BooleanVar(master=frame, value=_get_bool("UseEDSM", True))
    nb.Checkbutton(frame, text="Use EDSM system data and Spansh material-trader lookup",
                   variable=_prefs["edsm"]).grid(row=1, column=0, sticky=tk.W, padx=10)
    nb.Label(frame, text="Fuel distance is measured from the system arrival point.\n"
                         "Unknown to EDSM does not prove a system is unvisited.\n"
                         "Full scan means FSS identification, not surface mapping.").grid(
        row=2, column=0, sticky=tk.W, padx=10, pady=(6, 10))
    _prefs["pads"] = tk.BooleanVar(master=frame,value=_get_bool("CompatiblePads",False))
    nb.Checkbutton(frame,text="Hide objects known to have pads too small for your ship",variable=_prefs["pads"]).grid(row=3,column=0,sticky=tk.W,padx=10)
    _prefs["simplify"] = tk.BooleanVar(master=frame, value=_get_bool("SimplifyUninhabited", True))
    nb.Checkbutton(frame, text="Simplify uninhabited systems", variable=_prefs["simplify"]).grid(
        row=4, column=0, sticky=tk.W, padx=10, pady=(6, 0))
    nb.Label(frame, text="Hide empty/default system details when population is confirmed zero.\n"
                        "Keep reported factions, powers and legal status.").grid(
        row=5, column=0, sticky=tk.W, padx=10, pady=(0, 6))
    _prefs["top_two"] = tk.BooleanVar(master=frame, value=_get_bool("TopTwoAcquisition", True))
    nb.Checkbutton(frame, text="Show only the top two acquisition contenders",
                   variable=_prefs["top_two"]).grid(row=6, column=0, sticky=tk.W, padx=10, pady=(6, 0))
    nb.Label(frame, text="Rank contenders by reported acquisition progress.\n"
                        "Controlled systems always show their single controlling power.").grid(
        row=7, column=0, sticky=tk.W, padx=10, pady=(0, 6))
    for row, (key, setting, text) in enumerate((
            ("codes", "ShowServiceCodes", "Mark engineers (E), material traders (M-R/M-M/M-E) and tech brokers (T-G/T-H) in Objects"),
            ("hl_eng", "HighlightEngineers", "Highlight engineer names"),
            ("hl_svc", "HighlightServices", "Highlight stations with a material trader or technology broker")), start=8):
        _prefs[key] = tk.BooleanVar(master=frame, value=_get_bool(setting, True))
        nb.Checkbutton(frame, text=text, variable=_prefs[key]).grid(
            row=row, column=0, sticky=tk.W, padx=10, pady=(6 if row == 8 else 0, 0))
    station_data = nb.Frame(frame)
    station_data.grid(row=11, column=0, sticky=tk.W, padx=10, pady=(4, 6))
    _prefs["landmark_button"] = ttk.Button(station_data, text="Download station data (~300 KB, once)",
                                          command=_download_landmarks)
    _prefs["landmark_button"].grid(row=0, column=0, sticky=tk.W)
    _prefs["landmark_status"] = nb.Label(station_data, text="")
    _prefs["landmark_status"].grid(row=0, column=1, sticky=tk.W, padx=(8, 0))
    _update_landmark_prefs()
    # Required Interface owns the shared contrast preference and rendering.
    try:
        from plug import invoke
        invoke("(N) Interface", "Navigator Interface", "navigator_background_preferences",
               frame, "Navigator_Cartography")
    except ImportError:
        pass
    return outer


def prefs_changed(cmdr: str | None, is_beta: bool) -> None:
    if "top_two" in _prefs:
        config.set(PREFIX+"TopTwoAcquisition", _prefs["top_two"].get())
    if "simplify" in _prefs:
        config.set(PREFIX+"SimplifyUninhabited", _prefs["simplify"].get())
    if "pads" in _prefs:
        config.set(PREFIX+"CompatiblePads",_prefs["pads"].get())
    for key, setting in (("codes", "ShowServiceCodes"), ("hl_eng", "HighlightEngineers"), ("hl_svc", "HighlightServices")):
        if key in _prefs:
            config.set(PREFIX + setting, _prefs[key].get())
    for key in [k for k in _ui if k.startswith("rows_")]:
        _ui.pop(key)   # marker/highlight choices change captions and colours
    if "edsm" in _prefs:
        old = _get_bool("UseEDSM", True)
        value = _prefs["edsm"].get()
        config.set(PREFIX + "UseEDSM", value)
        if value and not old:
            _attempted.clear()
            _ensure_lookup()
    _refresh_group1()
    _schedule_theme()


def plugin_stop() -> None:
    global _stopped, _theme_pending, _root, _tab_font, _tab_font_key, _service, _poll_id
    _stopped = True
    _cancel_display()
    if _service is not None:
        _service.close()
        _service = None
    _pending.clear()
    _attempted.clear()
    _deferred_lookups.clear()
    if _poll_id is not None and _root is not None:
        _root.after_cancel(_poll_id)
        _poll_id = None
    if _root is not None:
        if _theme_pending is not None:
            _root.after_cancel(_theme_pending)
        for sequence, binding in _theme_bindings:
            _root.unbind(sequence, binding)
    _theme_bindings.clear()
    _theme_pending = None
    _root = None
    _tab_font = _tab_font_key = None
    _ui.clear()
